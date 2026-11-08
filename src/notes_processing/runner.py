"""apply: pass 1 writes merged pages, pass 2 re-points links, then every page is verified.

Research R7 (two passes), R9 (verification), R11 (failures, retries). The source notebook is only
read; every write goes through the gateway, which refuses IDs outside the target notebook.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from .links import extract_links, guid_from_url, norm_guid, rewrite_hrefs, same_target
from .model import (
    ContentIssue,
    LinkKind,
    LinkOutcome,
    PageOutcome,
    PageStatus,
    Plan,
    PlannedPage,
    RunReport,
    SourceNotebook,
    SourcePage,
    Summary,
    VerificationResult,
)
from .onenote.errors import OneNoteCallFailed, OneNoteError, OneNoteUnavailable
from .onexml import content_elements, local, oe_ids, parse, tostring
from .pagebuilder import LayoutError, build_target_page, unlink_bare_urls_in_page
from .verify import page_paragraphs, page_web_links, split_target_blocks, verify_page

BACKOFF = (1.0, 4.0, 16.0)

KEPT_REASONS = {
    LinkKind.OUTSIDE_TRANSFER: "zeigt auf Inhalt außerhalb der Übertragung",
    LinkKind.TARGET_NOT_FOUND: "Ziel nicht gefunden",
}


class _Stop(Exception):
    """OneNote stayed unavailable after all retries."""


@dataclass
class _BlockInfo:
    heading_oe: str = ""
    source_oes: list[str] = field(default_factory=list)
    target_oes: list[str] = field(default_factory=list)


@dataclass
class _PageState:
    planned: PlannedPage
    section_name: str
    status: PageStatus = PageStatus.PLANNED
    message: str = ""
    target_page_id: str = ""
    blocks: dict[str, _BlockInfo] = field(default_factory=dict)  # source page id -> info
    source_texts: list[list[str]] = field(default_factory=list)
    source_links: list[list[str]] = field(default_factory=list)

    def outcome(self) -> PageOutcome:
        return PageOutcome(
            self.planned.source_section_id,
            self.planned.source_section_name,
            self.section_name,
            self.planned.title,
            self.status,
            self.message,
            self.target_page_id,
        )


def _unexpected(exc: Exception) -> str:
    return f"Unerwarteter Fehler ({type(exc).__name__}): {exc}"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class _Runner:
    def __init__(self, plan: Plan, gateway, source: SourceNotebook, progress, sleep, clock):
        self.plan = plan
        self.gw = gateway
        self.progress = progress
        self.sleep = sleep
        self.clock = clock
        self.pages: dict[str, SourcePage] = {
            p.id: p for g in source.groups for s in g.sections for p in s.pages
        }
        self.states = [_PageState(p, s.name) for s in plan.sections for p in s.pages]
        self.by_section = {st.planned.source_section_id: st for st in self.states}
        self.by_source_page = {b.page_id: st for st in self.states for b in st.planned.blocks}
        self.target_sections: dict[str, str] = {}  # source group id -> target section id
        self.issues: list[ContentIssue] = []
        self.link_outcomes: list[LinkOutcome] = []
        self.verification: list[VerificationResult] = []
        self.object_guids: dict[str, dict[str, int]] = {}  # lazily: source page -> guid -> idx
        self.target_notebook_id = ""

    # ------------------------------------------------------------------ COM with retries
    def call(self, method: str, *args):
        for attempt in range(len(BACKOFF) + 1):
            try:
                return getattr(self.gw, method)(*args)
            except OneNoteUnavailable as exc:
                if attempt == len(BACKOFF):
                    raise _Stop(str(exc)) from exc
                self.progress(f"OneNote antwortet nicht, neuer Versuch in {BACKOFF[attempt]:g} s …")
                self.sleep(BACKOFF[attempt])
        raise AssertionError("unreachable")

    # ------------------------------------------------------------------ pass 1
    def write_all(self) -> None:
        self.target_notebook_id = self.call(
            "create_notebook", self.plan.target_folder, self.plan.target_notebook_name
        )
        total = len(self.plan.sections)
        for n, psec in enumerate(self.plan.sections, 1):
            states = [self.by_section[p.source_section_id] for p in psec.pages]
            try:
                sid = self.call("create_section", psec.name)
                self.target_sections[psec.source_group_id] = sid
            except OneNoteCallFailed as exc:
                for st in states:
                    st.status, st.message = PageStatus.FAILED, f"Abschnitt nicht angelegt: {exc}"
            else:
                for st in states:
                    self.write_page(st, sid)
            ok = sum(st.status == PageStatus.CONTENT_WRITTEN for st in states)
            self.progress(
                f"[{n}/{total}] Abschnitt „{psec.name}“: {ok} von {len(states)} Seiten geschrieben"
            )

    def write_page(self, st: _PageState, section_id: str) -> None:
        try:
            self._write_page(st, section_id)
        except _Stop, OneNoteError:
            raise
        except Exception as exc:  # noqa: BLE001 - e.g. bad page XML: this page only (FR-012)
            st.status = (
                PageStatus.FAILED if st.status == PageStatus.PLANNED else PageStatus.INCOMPLETE
            )
            st.message = _unexpected(exc)

    def _write_page(self, st: _PageState, section_id: str) -> None:
        planned = st.planned
        try:
            try:
                sources = [
                    (self.pages[b.page_id], b, self.call("page_xml", b.page_id))
                    for b in planned.blocks
                ]
                st.target_page_id = self.call("create_page", section_id)
            except OneNoteCallFailed as exc:
                st.status, st.message = PageStatus.FAILED, str(exc)
                return
            st.status = PageStatus.CREATED
            try:
                skeleton = self.call("page_xml", st.target_page_id)
                xml, issues = build_target_page(planned, sources, skeleton)
                self.call("update_page", xml)
                st.status = PageStatus.CONTENT_WRITTEN
                self.issues.extend(issues)
                back = self.call("page_xml", st.target_page_id, False)
            except (OneNoteCallFailed, LayoutError) as exc:
                st.status, st.message = PageStatus.INCOMPLETE, str(exc)
                return
        except _Stop:
            if st.status != PageStatus.PLANNED:
                st.status, st.message = PageStatus.INCOMPLETE, "Lauf abgebrochen"
            raise
        # Pair source and target elements by document order (research R7 step 3).
        split = split_target_blocks(back, [b.heading for b in planned.blocks])
        for (page, _, src_xml), (heading_el, elements) in zip(sources, split, strict=True):
            src_elements = content_elements(parse(src_xml))
            info = _BlockInfo(
                heading_oe=oe_ids([heading_el])[0] if heading_el is not None else "",
                source_oes=oe_ids(src_elements),
                target_oes=oe_ids(elements),
            )
            st.blocks[page.id] = info
            st.source_texts.append(page_paragraphs(src_xml))
            st.source_links.append(page_web_links(src_xml))

    # ------------------------------------------------------------------ pass 2
    def resolve(self, link) -> tuple[str | None, str]:
        """New href for a transferred link, or (None, reason)."""
        kind, target = link.kind, link.target_source_id
        if kind == LinkKind.TRANSFERRED_GROUP:
            sid = self.target_sections.get(target or "")
            if not sid:
                return None, "Zielabschnitt wurde nicht angelegt"
            return self.call("link_to", sid), ""
        if kind == LinkKind.TRANSFERRED_SECTION:
            st = self.by_section.get(target or "")
        else:
            st = self.by_source_page.get(target or "")
        if st is None or st.status not in (PageStatus.CONTENT_WRITTEN, PageStatus.LINKS_UPDATED):
            return None, "Ziel wurde nicht übertragen"
        if kind == LinkKind.TRANSFERRED_SECTION:
            return self.call("link_to", st.target_page_id), ""
        info = st.blocks[target or ""]
        if kind == LinkKind.TRANSFERRED_PARAGRAPH:
            oe = self.paragraph_target(link.href, target or "", info)
            if oe:
                return self.call("link_to", st.target_page_id, oe), ""
            if not info.heading_oe:
                return None, "Absatz und Überschrift im Ziel nicht gefunden"
            return self.call("link_to", st.target_page_id, info.heading_oe), (
                "Absatz nicht gefunden, Link zeigt auf die Überschrift"
            )
        if not info.heading_oe:
            return None, "Überschrift im Ziel nicht gefunden"
        return self.call("link_to", st.target_page_id, info.heading_oe), ""

    def paragraph_target(self, href: str, source_page_id: str, info: _BlockInfo) -> str:
        if len(info.source_oes) != len(info.target_oes):
            return ""
        guids = self.object_guids.get(source_page_id)
        if guids is None:  # lazy: only pages that are targets of paragraph links (R7 step 5)
            guids = {}
            for i, oe in enumerate(info.source_oes):
                url = self.call("link_to", source_page_id, oe)
                guids[norm_guid(guid_from_url(url, "object-id"))] = i
            self.object_guids[source_page_id] = guids
        idx = guids.get(norm_guid(guid_from_url(href, "object-id")))
        return info.target_oes[idx] if idx is not None else ""

    def update_links(self) -> None:
        pending: dict[int, list[tuple[object, str, str]]] = {}
        for link in self.plan.links:
            st = self.by_source_page.get(link.source_page_id)
            if not link.kind.transferred:
                self.keep(link, KEPT_REASONS.get(link.kind, "unverändert"))
                continue
            if st is None or st.status != PageStatus.CONTENT_WRITTEN:
                self.keep(link, "Seite mit dem Link wurde nicht geschrieben")
                continue
            try:
                new, reason = self.resolve(link)
            except _Stop:
                raise
            except OneNoteCallFailed as exc:
                new, reason = None, str(exc)
            except OneNoteError:
                raise
            except Exception as exc:  # noqa: BLE001 - confined to this page/link
                new, reason = None, _unexpected(exc)
            if new is None:
                self.keep(link, reason)
            else:
                pending.setdefault(id(st), []).append((link, new, reason))

        for st in self.states:
            if st.status != PageStatus.CONTENT_WRITTEN:
                continue
            changes = pending.get(id(st), [])
            if not changes:
                st.status = PageStatus.LINKS_UPDATED
                continue
            try:
                current = self.call("page_xml", st.target_page_id)
                # OneNote may store a copied href in another (relative) form: match by target.
                present = {h for _, h in extract_links(current)}
                mapping: dict[str, str] = {}
                found: set[str] = set()
                for link, new, _ in changes:
                    for h in present:
                        if h == link.href or same_target(h, link.href):
                            mapping[h] = new
                            found.add(link.href)
                self.call("update_page", pass2_xml(current, mapping))
            except _Stop:
                st.status, st.message = PageStatus.INCOMPLETE, "Lauf abgebrochen"
                raise
            except OneNoteError as exc:
                if not isinstance(exc, OneNoteCallFailed):
                    raise
                st.status, st.message = PageStatus.INCOMPLETE, f"Links nicht aktualisiert: {exc}"
                for link, _, _ in changes:
                    self.keep(link, "Aktualisierung fehlgeschlagen")
                continue
            except Exception as exc:  # noqa: BLE001 - confined to this page/link
                st.status = PageStatus.INCOMPLETE
                st.message = f"Links nicht aktualisiert: {_unexpected(exc)}"
                for link, _, _ in changes:
                    self.keep(link, "Aktualisierung fehlgeschlagen")
                continue
            st.status = PageStatus.LINKS_UPDATED
            for link, new, reason in changes:
                if link.href in found:
                    self.link_outcomes.append(
                        LinkOutcome(
                            link.source_page_id,
                            link.text,
                            link.href,
                            link.kind,
                            "updated",
                            new,
                            reason,
                        )
                    )
                else:
                    self.keep(link, "Link im geschriebenen Inhalt nicht gefunden")

    def keep(self, link, reason: str) -> None:
        self.link_outcomes.append(
            LinkOutcome(link.source_page_id, link.text, link.href, link.kind, "kept", "", reason)
        )

    # ------------------------------------------------------------------ verification
    def verify_all(self) -> None:
        for st in self.states:
            if st.status != PageStatus.LINKS_UPDATED:
                continue
            try:
                target = self.call("page_xml", st.target_page_id, False)
                result = verify_page(
                    st.planned, st.source_texts, target, st.target_page_id, st.source_links
                )
            except OneNoteCallFailed as exc:
                st.status, st.message = PageStatus.VERIFICATION_FAILED, str(exc)
                continue
            except _Stop, OneNoteError:
                raise
            except Exception as exc:  # noqa: BLE001 - confined to this page/link
                st.status, st.message = PageStatus.VERIFICATION_FAILED, _unexpected(exc)
                continue
            self.verification.append(result)
            if result.ok:
                st.status = PageStatus.VERIFIED
            else:
                st.status = PageStatus.VERIFICATION_FAILED
                st.message = f"{len(result.mismatches)} Abweichung(en)"

    # ------------------------------------------------------------------ main
    def run(self) -> RunReport:
        started = self.clock()
        stopped, reason = False, ""
        try:
            self.write_all()
            self.update_links()
            self.verify_all()
        except _Stop as exc:
            stopped, reason = True, f"OneNote nicht erreichbar, Lauf abgebrochen: {exc}"
            self.progress(reason)
        except OneNoteError as exc:  # e.g. target notebook could not be created
            stopped, reason = True, f"Lauf abgebrochen: {exc}"
            self.progress(reason)
        except Exception as exc:  # noqa: BLE001 - last resort: still return a report (FR-012)
            stopped, reason = True, f"Lauf abgebrochen: {_unexpected(exc)}"
            self.progress(reason)
        for st in self.states:
            if st.status == PageStatus.PLANNED:
                st.status = PageStatus.NOT_STARTED
            elif st.status in (PageStatus.CREATED, PageStatus.CONTENT_WRITTEN):
                st.status = PageStatus.INCOMPLETE
                st.message = st.message or "Lauf vor Abschluss der Seite beendet"
            elif stopped and st.status == PageStatus.LINKS_UPDATED:
                st.status = PageStatus.INCOMPLETE
                st.message = "nicht geprüft (Lauf abgebrochen)"
        if stopped:
            done = {(lo.source_page_id, lo.href) for lo in self.link_outcomes}
            for link in self.plan.links:
                if (link.source_page_id, link.href) not in done:
                    self.keep(link, "Lauf abgebrochen")

        outcomes = [st.outcome() for st in self.states]
        skipped = [
            PageOutcome(
                a.source_id, a.names[-1], a.names[0], a.names[-1], PageStatus.SKIPPED, a.message
            )
            for a in self.plan.attention
            if a.kind == "locked"
        ]
        all_outcomes = [*outcomes, *skipped]

        def count(*statuses: PageStatus) -> int:
            return sum(o.status in statuses for o in all_outcomes)

        summary = Summary(
            sections=len(self.plan.sections),
            pages=len(self.plan.pages),
            source_pages=sum(p.source_page_count for p in self.plan.pages),
            completed=count(PageStatus.VERIFIED),
            skipped=count(PageStatus.SKIPPED),
            failed=count(PageStatus.FAILED),
            incomplete=count(PageStatus.INCOMPLETE),
            not_started=count(PageStatus.NOT_STARTED),
            verification_failed=count(PageStatus.VERIFICATION_FAILED),
        )
        return RunReport(
            plan_fingerprint=self.plan.fingerprint,
            started=started,
            finished=self.clock(),
            target_notebook_id=self.target_notebook_id,
            pages=tuple(all_outcomes),
            title_decisions=self.plan.title_decisions,
            links=tuple(self.link_outcomes),
            content_issues=tuple(self.issues),
            verification=tuple(self.verification),
            summary=summary,
            stopped=stopped,
            stop_reason=reason,
        )


def pass2_xml(current: str, mapping: dict[str, str]) -> str:
    """Partial update for pass 2: re-pointed links, only the changed elements.

    Everything sent is written again by OneNote, so bare web links are unlinked here too
    (pagebuilder.unlink_bare_urls); otherwise OneNote inserts a space before them.
    """
    return unlink_bare_urls_in_page(_changed_only(current, rewrite_hrefs(current, mapping)))


def _changed_only(original: str, rewritten: str) -> str:
    """Partial update: the page with only the top-level elements whose content changed."""
    old = {e.get("objectID"): tostring(e) for e in content_elements(parse(original))}
    page = parse(rewritten)
    contents = content_elements(page)
    for e in list(page):
        if local(e.tag) in ("QuickStyleDef", "TagDef"):
            continue
        if e in contents and old.get(e.get("objectID")) != tostring(e):
            continue
        page.remove(e)
    return tostring(page)


def run(
    plan: Plan,
    gateway,
    source: SourceNotebook,
    progress: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], str] = _now,
) -> RunReport:
    return _Runner(plan, gateway, source, progress, sleep, clock).run()

"""SourceNotebook + scope -> Plan (FR-002, FR-004, FR-005, FR-014)."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections import Counter
from collections.abc import Callable

from .links import LinkIndex, classify, extract_links, guid_from_url
from .model import (
    AttentionItem,
    LinkKind,
    LinkRef,
    Plan,
    PlannedPage,
    PlannedSection,
    Scope,
    SourceGroup,
    SourceNotebook,
    TitleStatus,
)
from .onenote.errors import NotFound
from .onexml import content_elements, local, parse
from .report import to_jsonable
from .titles import decide_titles, month_title
from .videos import find_video_previews, preview_message

NON_TEXT = {
    "Image": ("Bild", "Bilder"),
    "InkDrawing": ("Freihandzeichnung", "Freihandzeichnungen"),
    "InsertedFile": ("eingebettete Datei", "eingebettete Dateien"),
    "MediaFile": ("Audio-/Videodatei", "Audio-/Videodateien"),
}


def select(source: SourceNotebook, scope: Scope) -> list[tuple[SourceGroup, list]]:
    """Groups in scope with their sections in scope (locked ones included)."""
    if scope.kind == "all":
        names = {g.name for g in source.groups}
        missing = [name for name in scope.exclude if name not in names]
        if missing:
            raise NotFound(f"Auszuschließende Abschnittsgruppe „{missing[0]}“ nicht gefunden")
        return [(g, list(g.sections)) for g in source.groups if g.name not in scope.exclude]
    groups = [g for g in source.groups if g.name == scope.group]
    if not groups:
        raise NotFound(f"Abschnittsgruppe „{scope.group}“ nicht gefunden")
    if scope.kind == "group":
        return [(g, list(g.sections)) for g in groups]
    out = [(g, [s for s in g.sections if s.name == scope.section]) for g in groups]
    out = [(g, ss) for g, ss in out if ss]
    if not out:
        raise NotFound(f"Abschnitt „{scope.section}“ in „{scope.group}“ nicht gefunden")
    return out


def scope_ids(source: SourceNotebook, scope: Scope) -> tuple[set[str], set[str]]:
    """IDs of unlocked sections and of groups that are part of the transfer."""
    selected = select(source, scope)
    sections = {s.id for _, ss in selected for s in ss if not s.locked}
    return sections, {g.id for g, _ in selected}


def index_links(gateway, source: SourceNotebook, scope: Scope) -> SourceNotebook:
    """Fill link GUIDs (research R7 step 1): every unlocked section, and pages in scope."""
    in_scope, _ = scope_ids(source, scope)
    groups = []
    for g in source.groups:
        sections = []
        for s in g.sections:
            if s.locked:
                sections.append(s)
                continue
            sguid = guid_from_url(gateway.link_to(s.id), "section-id")
            pages = s.pages
            if s.id in in_scope:
                pages = tuple(
                    dataclasses.replace(
                        p, link_page_guid=guid_from_url(gateway.link_to(p.id), "page-id")
                    )
                    for p in s.pages
                )
            sections.append(dataclasses.replace(s, link_section_guid=sguid, pages=pages))
        groups.append(dataclasses.replace(g, sections=tuple(sections)))
    return dataclasses.replace(source, groups=tuple(groups))


def _plural(n: int, names: tuple[str, str]) -> str:
    return f"{n} {names[0] if n == 1 else names[1]}"


def build_plan(
    source: SourceNotebook,
    scope: Scope,
    target_name: str,
    target_folder: str,
    page_loader: Callable[[str], str] | None = None,
) -> Plan:
    selected = select(source, scope)
    attention: list[AttentionItem] = []
    sections: list[PlannedSection] = []
    links: list[LinkRef] = []

    group_counts = Counter(g.name for g, _ in selected)
    for name in sorted(n for n, c in group_counts.items() if c > 1):
        attention.append(
            AttentionItem(
                "duplicate_group", "Name der Abschnittsgruppe kommt mehrfach vor", (name,)
            )
        )
    for name in scope.exclude:
        attention.append(
            AttentionItem(
                "excluded_group",
                "Abschnittsgruppe ist ausgeschlossen und wird nicht übertragen",
                (name,),
            )
        )
    group_names = {g.name for g, _ in selected}
    for item in source.ignored:
        if item.kind == "loose_section" and scope.kind == "all":
            attention.append(
                AttentionItem(
                    "loose_section",
                    "Abschnitt außerhalb einer Abschnittsgruppe bleibt unverändert",
                    (item.name,),
                    item.id,
                )
            )
        elif item.kind == "nested_group" and item.parent in group_names and scope.kind != "section":
            attention.append(
                AttentionItem(
                    "nested_group",
                    "Verschachtelte Abschnittsgruppe bleibt unverändert",
                    (item.parent, item.name),
                    item.id,
                )
            )

    index = None
    if page_loader is not None:
        section_ids, group_ids = scope_ids(source, scope)
        index = LinkIndex.build(source, section_ids, group_ids)

    for group, group_sections in selected:
        counts = Counter(s.name for s in group_sections)
        for name in [n for n, c in counts.items() if c > 1]:
            attention.append(
                AttentionItem(
                    "duplicate_section",
                    "Abschnittsname kommt in der Gruppe mehrfach vor",
                    (group.name, name),
                )
            )
        pages: list[PlannedPage] = []
        for s in group_sections:
            names = (group.name, s.name)
            if s.locked:
                attention.append(
                    AttentionItem(
                        "locked",
                        "Abschnitt ist gesperrt oder verschlüsselt und wird übersprungen",
                        names,
                        s.id,
                    )
                )
                continue
            if not s.pages:
                attention.append(
                    AttentionItem(
                        "empty_section",
                        "Abschnitt ist leer; die neue Seite enthält nur den Titel",
                        names,
                        s.id,
                    )
                )
            decisions = decide_titles(s.name, s.pages)
            if any(d.status == TitleStatus.NO_SECTION_MONTH for d in decisions):
                attention.append(
                    AttentionItem(
                        "no_section_month",
                        "Kein Monat für den Abschnitt bestimmbar; Datumstitel bleiben unverändert",
                        names,
                        s.id,
                    )
                )
            pages.append(
                PlannedPage(s.id, s.name, month_title(s.name), tuple(decisions), len(s.pages))
            )
            if page_loader is not None and index is not None:
                non_text: Counter[str] = Counter()
                for p in s.pages:
                    xml = page_loader(p.id)
                    for text, href in extract_links(xml):
                        kind, target = classify(href, index)
                        if kind != LinkKind.EXTERNAL:
                            links.append(LinkRef(p.id, text, href, kind, target))
                    page = parse(xml)
                    for el in content_elements(page):
                        for node in el.iter():
                            if local(node.tag) in NON_TEXT:
                                non_text[local(node.tag)] += 1
                    for image, url in find_video_previews(page):
                        attention.append(
                            AttentionItem(
                                "video_preview",
                                preview_message(
                                    url, url is not None and not image.get("hyperlink")
                                ),
                                (group.name, s.name, p.title),
                                p.id,
                            )
                        )
                if non_text:
                    parts = ", ".join(
                        _plural(non_text[k], NON_TEXT[k]) for k in NON_TEXT if non_text[k]
                    )
                    attention.append(
                        AttentionItem(
                            "non_text", f"Nicht-Text-Inhalte zum Prüfen: {parts}", names, s.id
                        )
                    )
        sections.append(PlannedSection(group.id, group.name, tuple(pages)))

    plan = Plan(
        source_notebook=source.name,
        source_notebook_id=source.id,
        target_notebook_name=target_name,
        target_folder=target_folder,
        scope=scope,
        sections=tuple(sections),
        title_decisions=tuple(
            d
            for s in sections
            for p in s.pages
            for d in p.blocks
            if d.status != TitleStatus.UNCHANGED
        ),
        links=tuple(links),
        attention=tuple(attention),
    )
    return dataclasses.replace(plan, fingerprint=fingerprint(plan, source))


def fingerprint(plan: Plan, source: SourceNotebook) -> str:
    """SHA-256 of the canonical plan JSON (without fingerprint) plus source lastModified values."""
    body = to_jsonable(dataclasses.replace(plan, fingerprint=""))
    in_scope = {p.source_section_id for p in plan.pages}
    modified = [
        [s.id, s.last_modified, [[p.id, p.last_modified] for p in s.pages]]
        for g in source.groups
        for s in g.sections
        if s.id in in_scope or s.locked
    ]
    canonical = json.dumps(
        [body, modified], sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def make_plan(
    gateway, source: SourceNotebook, scope: Scope, target_name: str, target_folder: str
) -> tuple[Plan, SourceNotebook]:
    """Read-only: index links via OneNote, scan in-scope pages, build the plan."""
    indexed = index_links(gateway, source, scope)
    plan = build_plan(
        indexed,
        scope,
        target_name,
        target_folder,
        page_loader=lambda pid: gateway.page_xml(pid, binary=False),
    )
    return plan, indexed

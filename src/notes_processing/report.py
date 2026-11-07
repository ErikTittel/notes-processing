"""Plan / RunReport <-> JSON, and German Markdown rendering (contracts/cli.md)."""

from __future__ import annotations

import dataclasses
import json
import types
import typing
from enum import Enum
from typing import Any

from .model import LinkKind, PageStatus, Plan, RunReport, TitleStatus

FORMAT_VERSION = 1


# --------------------------------------------------------------------------- JSON


def to_jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    return value


def from_jsonable(tp: Any, value: Any) -> Any:
    origin = typing.get_origin(tp)
    if origin in (types.UnionType, typing.Union):
        if value is None:
            return None
        inner = [a for a in typing.get_args(tp) if a is not type(None)]
        return from_jsonable(inner[0], value)
    if origin is tuple:
        (item, *_rest) = typing.get_args(tp)
        return tuple(from_jsonable(item, v) for v in value)
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        hints = typing.get_type_hints(tp)
        kwargs = {
            f.name: from_jsonable(hints[f.name], value[f.name])
            for f in dataclasses.fields(tp)
            if f.name in value
        }
        return tp(**kwargs)
    if isinstance(tp, type) and issubclass(tp, Enum):
        return tp(value)
    return value


def _dump(obj: Any) -> str:
    data = to_jsonable(obj)
    data["format_version"] = FORMAT_VERSION
    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _load(tp: type, s: str) -> Any:
    data = json.loads(s)
    version = data.pop("format_version", None)
    if version != FORMAT_VERSION:
        raise ValueError(f"Unbekannte Dateiversion: {version!r}")
    return from_jsonable(tp, data)


def plan_to_json(plan: Plan) -> str:
    return _dump(plan)


def plan_from_json(s: str) -> Plan:
    return _load(Plan, s)


def report_to_json(report: RunReport) -> str:
    return _dump(report)


def report_from_json(s: str) -> RunReport:
    return _load(RunReport, s)


# --------------------------------------------------------------------------- Markdown (German)

TITLE_STATUS_DE = {
    TitleStatus.CORRECTED: "korrigiert",
    TitleStatus.COULD_NOT_CORRECT: "konnte nicht korrigiert werden",
    TitleStatus.OUT_OF_ORDER: "außer der Reihe",
    TitleStatus.UNTITLED: "ohne Titel",
    TitleStatus.NO_SECTION_MONTH: "kein Abschnittsmonat",
    TitleStatus.UNCHANGED: "unverändert",
}
LINK_KIND_DE = {
    LinkKind.TRANSFERRED_PAGE: "wird aktualisiert (Seite → Überschrift)",
    LinkKind.TRANSFERRED_PARAGRAPH: "wird aktualisiert (Absatz)",
    LinkKind.TRANSFERRED_SECTION: "wird aktualisiert (Abschnitt → neue Seite)",
    LinkKind.TRANSFERRED_GROUP: "wird aktualisiert (Gruppe → neuer Abschnitt)",
    LinkKind.OUTSIDE_TRANSFER: "zeigt auf Inhalt außerhalb der Übertragung",
    LinkKind.TARGET_NOT_FOUND: "Ziel nicht gefunden",
    LinkKind.EXTERNAL: "extern",
}
PAGE_STATUS_DE = {
    PageStatus.PLANNED: "geplant",
    PageStatus.CREATED: "angelegt",
    PageStatus.CONTENT_WRITTEN: "Inhalt geschrieben",
    PageStatus.LINKS_UPDATED: "Links aktualisiert",
    PageStatus.VERIFIED: "geprüft ✓",
    PageStatus.FAILED: "FEHLGESCHLAGEN",
    PageStatus.INCOMPLETE: "UNVOLLSTÄNDIG",
    PageStatus.VERIFICATION_FAILED: "PRÜFUNG FEHLGESCHLAGEN",
    PageStatus.SKIPPED: "übersprungen",
    PageStatus.NOT_STARTED: "nicht begonnen",
}


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ") or "—"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    if not rows:
        return ["_keine_", ""]
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return [*out, ""]


def _page_titles(plan: Plan) -> dict[str, tuple[str, str]]:
    """source page id -> (source section name, original title)."""
    return {b.page_id: (p.source_section_name, b.original) for p in plan.pages for b in p.blocks}


def _plan_sections(plan: Plan) -> list[str]:
    titles = _page_titles(plan)
    out = ["## Übersicht", ""]
    out += [
        f"- Quellnotizbuch: **{plan.source_notebook}**",
        f"- Zielnotizbuch: **{plan.target_notebook_name}** in `{plan.target_folder}`",
        f"- Umfang: `{plan.scope}`",
        f"- Neue Abschnitte: {len(plan.sections)}",
        f"- Neue Seiten: {len(plan.pages)}",
        f"- Quellseiten: {sum(p.source_page_count for p in plan.pages)}",
        (
            f"- Titelkorrekturen: "
            f"{sum(d.status == TitleStatus.CORRECTED for d in plan.title_decisions)}"
        ),
        f"- Links in übertragenem Inhalt: {len(plan.links)}",
        f"- Hinweise: {len(plan.attention)}",
        f"- Fingerabdruck: `{plan.fingerprint}`",
        "",
        "## Struktur",
        "",
    ]
    for s in plan.sections:
        out.append(f"- Abschnittsgruppe **{s.name}** → Abschnitt **{s.name}**")
        for p in s.pages:
            out.append(
                f"  - Abschnitt „{p.source_section_name}“ → Seite **{p.title}** "
                f"({p.source_page_count} Quellseiten)"
            )
    out.append("")

    out += ["## Titelkorrekturen", ""]
    by_status = {st: [d for d in plan.title_decisions if d.status == st] for st in TitleStatus}
    out += ["### Ersetzt", ""]
    out += _table(
        ["Abschnitt", "Original", "Neuer Titel"],
        [[d.section_name, d.original, d.heading] for d in by_status[TitleStatus.CORRECTED]],
    )
    for st, label in (
        (TitleStatus.COULD_NOT_CORRECT, "Konnte nicht korrigiert werden"),
        (TitleStatus.OUT_OF_ORDER, "Außer der Reihe (unverändert)"),
        (TitleStatus.NO_SECTION_MONTH, "Kein Abschnittsmonat (unverändert)"),
        (TitleStatus.UNTITLED, "Ohne Titel"),
    ):
        out += [f"### {label}", ""]
        out += _table(
            ["Abschnitt", "Titel", "Überschrift"],
            [[d.section_name, d.original, d.heading] for d in by_status[st]],
        )

    out += ["## Links", ""]
    out += _table(
        ["Abschnitt", "Seite", "Linktext", "Ursprüngliches Ziel", "Behandlung"],
        [
            [*titles.get(lk.source_page_id, ("?", "?")), lk.text, lk.href, LINK_KIND_DE[lk.kind]]
            for lk in plan.links
        ],
    )
    out += ["## Hinweise", ""]
    out += [f"- {' / '.join(a.names)}: {a.message} (`{a.kind}`)" for a in plan.attention]
    if not plan.attention:
        out.append("_keine_")
    out.append("")
    return out


def render_plan_md(plan: Plan) -> str:
    return "\n".join(["# Plan: Abschnitte zu Seiten zusammenführen", "", *_plan_sections(plan)])


def render_report_md(report: RunReport, plan: Plan) -> str:
    titles = _page_titles(plan)
    s = report.summary
    out = ["# Bericht: Abschnitte zu Seiten zusammenführen", ""]
    out += ["## Ergebnis", ""]
    if report.stopped:
        out += [f"**Lauf abgebrochen:** {report.stop_reason}", ""]
    out += [
        f"- Beginn: {report.started}, Ende: {report.finished}",
        f"- Abschnitte: {s.sections}, Seiten: {s.pages}, Quellseiten: {s.source_pages}",
        f"- Abgeschlossen (geprüft): {s.completed}",
        f"- Übersprungen: {s.skipped}",
        f"- Fehlgeschlagen: {s.failed}",
        f"- Unvollständig: {s.incomplete}",
        f"- Nicht begonnen: {s.not_started}",
        f"- Prüfung fehlgeschlagen: {s.verification_failed}",
        "",
        "### Seiten",
        "",
    ]
    out += _table(
        ["Neuer Abschnitt", "Quellabschnitt", "Neue Seite", "Status", "Meldung"],
        [
            [
                p.target_section_name,
                p.source_section_name,
                p.title,
                PAGE_STATUS_DE[p.status],
                p.message,
            ]
            for p in report.pages
        ],
    )
    out += ["### Nicht übertragbare Inhalte", ""]
    out += _table(
        ["Abschnitt", "Quellseite", "Element", "Problem"],
        [
            [c.source_section_name, c.source_page_title, c.element, c.message]
            for c in report.content_issues
        ],
    )
    out += ["### Links", ""]
    out += _table(
        ["Abschnitt", "Seite", "Linktext", "Ursprüngliches Ziel", "Ergebnis", "Neues Ziel / Grund"],
        [
            [
                *titles.get(lo.source_page_id, ("?", "?")),
                lo.text,
                lo.href,
                "aktualisiert" if lo.status == "updated" else "unverändert",
                lo.new_href + (f" ({lo.reason})" if lo.reason and lo.new_href else lo.reason),
            ]
            for lo in report.links
        ],
    )
    out += render_verification(report.verification, titles)
    out += ["# Plan", "", *_plan_sections(plan)]
    return "\n".join(out)


def render_verification(results, titles=None) -> list[str]:
    out = ["## Prüfung", ""]
    bad = [r for r in results if not r.ok]
    out.append(f"{len(results) - len(bad)} von {len(results)} Seiten ohne Abweichung.")
    out.append("")
    for r in bad:
        out += [f"### {r.target_page_title}", ""]
        out += _table(
            ["Quellseite", "Art", "Details"],
            [[m.source_page_title, m.kind, m.detail] for m in r.mismatches],
        )
    return out


def render_verify_md(results, missing: list[str]) -> str:
    out = ["# Prüfung eines abgeschlossenen Laufs", ""]
    if missing:
        out += ["## Nicht erstellte Seiten", ""]
        out += [f"- {m}" for m in missing]
        out.append("")
    out += render_verification(results)
    return "\n".join(out)

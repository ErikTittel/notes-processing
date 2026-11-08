"""Command line: plan / apply / verify (contracts/cli.md). Messages are German."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from . import runner
from .hierarchy import notebooks, parse_hierarchy
from .model import PageStatus, Plan, Scope, SourceNotebook
from .onenote.errors import NotFound, OneNoteCallFailed, OneNoteUnavailable
from .onenote.gateway import HS_NOTEBOOKS, HS_PAGES, OneNoteGateway
from .planner import make_plan
from .report import (
    plan_from_json,
    plan_to_json,
    render_plan_md,
    render_report_md,
    render_verify_md,
    report_from_json,
    report_to_json,
)
from .verify import page_paragraphs, page_web_links, verify_page

OK = 0
ITEMS_FAILED = 1
BAD_ARGS = 2
TARGET_EXISTS = 3
ONENOTE_UNAVAILABLE = 4
SOURCE_CHANGED = 5
NOT_CONFIRMED = 6

PROMPT = 'Plan ausführen? Zum Bestätigen "ja" eingeben: '


class _Exit(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="notes-processing",
        description="OneNote: Abschnittsgruppen zu Abschnitten und Abschnitte zu Seiten "
        "zusammenführen.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="Plan erstellen (nur lesend)")
    plan.add_argument("--source", required=True, help="Name des Quellnotizbuchs")
    plan.add_argument("--target", required=True, help="Name des neuen Zielnotizbuchs")
    plan.add_argument("--group", help="nur diese Abschnittsgruppe")
    plan.add_argument("--section", help="nur dieser Abschnitt (erfordert --group)")
    plan.add_argument("--target-folder", help="Ordner für das neue Notizbuch")
    plan.add_argument("--out", help="Ordner für den Lauf (Standard: runs/<Zeitstempel>)")
    apply = sub.add_parser("apply", help="geprüften Plan ausführen")
    apply.add_argument("--plan", required=True, help="Pfad zu plan.json")
    apply.add_argument("--yes", action="store_true", help="ohne Rückfrage (nur für Tests)")
    verify = sub.add_parser("verify", help="abgeschlossenen Lauf erneut prüfen")
    verify.add_argument("--report", required=True, help="Pfad zu report.json")
    return p


# --------------------------------------------------------------------------- shared steps


def _read_source(gw, source_name: str, target_name: str, target_folder: str | None):
    """Check names and target, read the source hierarchy. Returns (source, target_folder)."""
    names = notebooks(gw.hierarchy("", HS_NOTEBOOKS))
    if source_name not in names:
        raise _Exit(BAD_ARGS, f"Quellnotizbuch „{source_name}“ ist nicht geöffnet.")
    if target_name in names:
        raise _Exit(TARGET_EXISTS, f"Ein Notizbuch „{target_name}“ ist bereits geöffnet.")
    folder = target_folder or gw.special_folder()
    if (Path(folder) / target_name).exists():
        raise _Exit(TARGET_EXISTS, f"Der Ordner „{Path(folder) / target_name}“ existiert bereits.")
    source = parse_hierarchy(gw.hierarchy(names[source_name], HS_PAGES))
    return source, folder


def summary_lines(plan: Plan) -> list[str]:
    corrected = sum(d.status == "corrected" for d in plan.title_decisions)
    other = len(plan.title_decisions) - corrected
    return [
        (
            f"Quelle: {plan.source_notebook}  →  Ziel: {plan.target_notebook_name} "
            f"({plan.target_folder})"
        ),
        f"Umfang: {plan.scope}",
        (
            f"{len(plan.sections)} neue Abschnitte, {len(plan.pages)} neue Seiten aus "
            f"{sum(p.source_page_count for p in plan.pages)} Quellseiten"
        ),
        f"{corrected} Titelkorrekturen, {other} weitere gemeldete Titel",
        (
            f"{len(plan.links)} Links in übertragenem Inhalt "
            f"({sum(lk.kind.transferred for lk in plan.links)} werden aktualisiert)"
        ),
        f"{len(plan.attention)} Hinweise",
    ]


# --------------------------------------------------------------------------- commands


def cmd_plan(args, gw) -> int:
    source, folder = _read_source(gw, args.source, args.target, args.target_folder)
    try:
        plan, _ = make_plan(gw, source, Scope.build(args.group, args.section), args.target, folder)
    except NotFound as exc:
        raise _Exit(BAD_ARGS, str(exc)) from exc
    out = Path(args.out) if args.out else Path("runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(plan_to_json(plan), encoding="utf-8")
    (out / "plan.md").write_text(render_plan_md(plan), encoding="utf-8")
    for line in summary_lines(plan):
        print(line)
    print(f"Plan gespeichert: {out / 'plan.json'} und {out / 'plan.md'}")
    return OK


def cmd_apply(args, gw) -> int:
    plan_path = Path(args.plan)
    plan = plan_from_json(plan_path.read_text(encoding="utf-8"))
    source, _ = _read_source(
        gw, plan.source_notebook, plan.target_notebook_name, plan.target_folder
    )
    try:
        rebuilt, indexed = make_plan(
            gw, source, plan.scope, plan.target_notebook_name, plan.target_folder
        )
    except NotFound as exc:
        raise _Exit(SOURCE_CHANGED, f"Notizbuch wurde seit dem Plan geändert: {exc}") from exc
    if rebuilt.fingerprint != plan.fingerprint:
        raise _Exit(
            SOURCE_CHANGED,
            "Notizbuch wurde seit dem Plan geändert. Bitte einen neuen Plan erstellen.",
        )
    for line in summary_lines(plan):
        print(line)
    if not args.yes and input(PROMPT).strip() != "ja":
        print("Nicht bestätigt, es wurde nichts geändert.")
        return NOT_CONFIRMED
    return _run_and_report(plan, gw, indexed, plan_path.parent)


def _run_and_report(plan: Plan, gw, source: SourceNotebook, folder: Path) -> int:
    report = runner.run(plan, gw, source, progress=print)
    (folder / "report.json").write_text(report_to_json(report), encoding="utf-8")
    (folder / "report.md").write_text(render_report_md(report, plan), encoding="utf-8")
    s = report.summary
    print(
        f"Fertig: {s.completed} geprüft, {s.skipped} übersprungen, {s.failed} fehlgeschlagen, "
        f"{s.incomplete} unvollständig, {s.not_started} nicht begonnen, "
        f"{s.verification_failed} mit Abweichungen."
    )
    print(f"Bericht: {folder / 'report.md'}")
    ok = not report.stopped and all(
        p.status in (PageStatus.VERIFIED, PageStatus.SKIPPED) for p in report.pages
    )
    return OK if ok else ITEMS_FAILED


def cmd_verify(args, gw) -> int:
    report_path = Path(args.report)
    report = report_from_json(report_path.read_text(encoding="utf-8"))
    plan = plan_from_json((report_path.parent / "plan.json").read_text(encoding="utf-8"))
    planned = {p.source_section_id: p for p in plan.pages}
    results, missing = [], []
    for outcome in report.pages:
        if outcome.status == PageStatus.SKIPPED:
            continue
        if not outcome.target_page_id:
            missing.append(f"{outcome.title} (aus „{outcome.source_section_name}“)")
            continue
        page = planned[outcome.source_section_id]
        sources = [gw.page_xml(b.page_id, False) for b in page.blocks]
        texts = [page_paragraphs(x) for x in sources]
        links = [page_web_links(x) for x in sources]
        target = gw.page_xml(outcome.target_page_id, False)
        results.append(verify_page(page, texts, target, outcome.target_page_id, links))
    (report_path.parent / "verify.md").write_text(
        render_verify_md(results, missing), encoding="utf-8"
    )
    bad = sum(not r.ok for r in results)
    print(
        f"{len(results) - bad} von {len(results)} Seiten ohne Abweichung"
        + (f", {len(missing)} Seiten nicht erstellt" if missing else "")
        + "."
    )
    print(f"Ergebnis: {report_path.parent / 'verify.md'}")
    return OK if not bad and not missing else ITEMS_FAILED


COMMANDS = {"plan": cmd_plan, "apply": cmd_apply, "verify": cmd_verify}


def main(
    argv: Sequence[str] | None = None, gateway_factory: Callable[[], object] = OneNoteGateway
) -> int:
    # A redirected Windows console uses cp1252, which lacks e.g. "→": never crash on output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return BAD_ARGS if exc.code else OK
    if getattr(args, "section", None) and not args.group:
        _err("--section erfordert --group.")
        return BAD_ARGS
    try:
        gw = gateway_factory()
        return COMMANDS[args.command](args, gw)
    except _Exit as exc:
        _err(str(exc))
        return exc.code
    except OneNoteUnavailable as exc:
        _err(f"OneNote ist nicht verfügbar: {exc}")
        return ONENOTE_UNAVAILABLE
    except OneNoteCallFailed as exc:
        _err(f"OneNote-Fehler: {exc}")
        return ONENOTE_UNAVAILABLE
    except (OSError, ValueError) as exc:
        _err(f"Fehler: {exc}")
        return BAD_ARGS


if __name__ == "__main__":
    sys.exit(main())

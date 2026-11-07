from notes_processing.report import render_report_md
from tests.unit.runner_helpers import plan_and_run


def test_report_sections():
    _, plan, report, _, _ = plan_and_run()
    md = render_report_md(report, plan)
    for head in (
        "## Ergebnis",
        "## Prüfung",
        "## Übersicht",
        "## Struktur",
        "## Titelkorrekturen",
        "## Links",
        "## Hinweise",
    ):
        assert head in md
    assert "- Abgeschlossen (geprüft): 4" in md
    assert "| 2023 | 23-10 | Oktober 2023 | geprüft ✓ |" in md
    assert "4 von 4 Seiten ohne Abweichung." in md


def test_failed_and_skipped_items_named():
    _, plan, report, _, _ = plan_and_run(fail_on={"create_page": 2, "update_page": 2})
    md = render_report_md(report, plan)
    assert "| 2023 | 23-11 | November 2023 | FEHLGESCHLAGEN | create_page fehlgeschlagen" in md
    assert "| Projekte | Haus | Haus | UNVOLLSTÄNDIG |" in md
    assert "- Fehlgeschlagen: 1" in md


def test_content_issues_and_links():
    _, plan, report, _, _ = plan_and_run()
    md = render_report_md(report, plan)
    assert "| Garten | Ernte | Image | Bild ohne Bilddaten (nicht kopierbar) |" in md
    assert "| Garten | Verweise | Eintrag |" in md
    assert "unverändert | zeigt auf Inhalt außerhalb der Übertragung |" in md
    assert "| aktualisiert |" in md


def test_stopped_run_shown(monkeypatch):
    from notes_processing import runner

    monkeypatch.setattr(runner, "BACKOFF", (0.0, 0.0, 0.0))
    probe, _, _, _, _ = plan_and_run()
    first = next(i for i, c in enumerate(probe.calls) if c[0] == "update_page")
    _, plan, report, _, _ = plan_and_run(unavailable_after=first + 1)
    md = render_report_md(report, plan)
    assert "**Lauf abgebrochen:**" in md
    assert "nicht begonnen" in md

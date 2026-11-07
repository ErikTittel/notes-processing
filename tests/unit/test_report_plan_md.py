from notes_processing.hierarchy import parse_hierarchy
from notes_processing.model import Scope
from notes_processing.planner import build_plan, make_plan
from notes_processing.report import render_plan_md
from tests.conftest import make_gateway, read_fixture


def plan_md(xml="hierarchy_small.xml"):
    gw = make_gateway()
    plan, _ = make_plan(gw, parse_hierarchy(read_fixture(xml)), Scope(), "Neu", r"C:\Out")
    return render_plan_md(plan)


def test_sections_present_in_order():
    md = plan_md()
    heads = ["## Übersicht", "## Struktur", "## Titelkorrekturen", "## Links", "## Hinweise"]
    positions = [md.index(h) for h in heads]
    assert positions == sorted(positions)


def test_overview_and_structure():
    md = plan_md()
    assert "- Neue Abschnitte: 2" in md
    assert "- Neue Seiten: 4" in md
    assert "- Quellseiten: 12" in md
    assert "Abschnittsgruppe **2023** → Abschnitt **2023**" in md
    assert "Abschnitt „23-10“ → Seite **Oktober 2023** (3 Quellseiten)" in md


def test_title_corrections_listed():
    md = plan_md()
    assert "| 23-10 | 05.12.23 | 05.10.23 |" in md
    assert "### Konnte nicht korrigiert werden" in md
    assert "### Außer der Reihe (unverändert)" in md


def test_links_listed_with_treatment():
    md = plan_md()
    assert "| Garten | Verweise | Eintrag |" in md
    assert "zeigt auf Inhalt außerhalb der Übertragung" in md
    assert "Ziel nicht gefunden" in md
    assert "wird aktualisiert (Seite → Überschrift)" in md
    assert "Beetplan" not in md  # external links are not listed


def test_attention_items():
    md = plan_md()
    assert "Projekte / Garten: Nicht-Text-Inhalte zum Prüfen: 1 Bild, 1 Freihandzeichnung" in md
    assert (
        "Projekte / Haus: Nicht-Text-Inhalte zum Prüfen: 1 Bild, 1 eingebettete Datei, "
        "1 Audio-/Videodatei"
    ) in md
    plan = build_plan(parse_hierarchy(read_fixture("hierarchy_edge.xml")), Scope(), "N", "C:\\")
    md = render_plan_md(plan)
    assert "A / X: Abschnitt ist gesperrt oder verschlüsselt und wird übersprungen" in md
    assert "A / Leer: Abschnitt ist leer" in md
    assert "Lose: Abschnitt außerhalb einer Abschnittsgruppe bleibt unverändert" in md

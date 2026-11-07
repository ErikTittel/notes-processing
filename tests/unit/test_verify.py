import xml.etree.ElementTree as ET

from notes_processing.model import PlannedPage, TitleDecision, TitleStatus
from notes_processing.onexml import NS, q, tostring
from notes_processing.verify import extract_text, page_paragraphs, verify_page
from tests.conftest import read_fixture
from tests.unit.runner_helpers import plan_and_run


def test_extract_text_strips_tags_keeps_link_text_and_whitespace():
    el = ET.fromstring(
        f'<one:OE xmlns:one="{NS}"><one:T><![CDATA[  a <span style="x">b</span> '
        '&amp; <a href="onenote:x&amp;y">Link</a>&nbsp;c ]]></one:T></one:OE>'
    )
    assert extract_text(el) == "  a b & Link\xa0c "


def merged(gw, report, title):
    page = next(p for p in report.pages if p.title == title)
    return page, gw.stored_page(page.target_page_id)


def planned(plan, title):
    return next(p for p in plan.pages if p.title == title)


def sources(planned_page):
    return [page_paragraphs(read_fixture(f"pages/{b.page_id}.xml")) for b in planned_page.blocks]


def test_identical_is_ok():
    gw, plan, report, _, _ = plan_and_run()
    for p in plan.pages:
        _, xml = merged(gw, report, p.title)
        assert verify_page(p, sources(p), xml).ok


def remove_paragraph(xml: str, text: str) -> str:
    page = ET.fromstring(xml)
    for parent in page.iter():
        for child in list(parent):
            if child.tag == q("OE") and any(t.text == text for t in child.findall(q("T"))):
                parent.remove(child)
                return tostring(page)
    raise AssertionError(text)


def test_removed_paragraph_reported():
    gw, plan, report, _, _ = plan_and_run()
    _, xml = merged(gw, report, "November 2023")
    p = planned(plan, "November 2023")
    result = verify_page(p, sources(p), remove_paragraph(xml, "Projekt abgeschlossen"), "TP-x")
    assert not result.ok
    (m,) = result.mismatches
    assert (m.source_page_id, m.source_page_title, m.kind) == ("P5", "Zusammenfassung", "missing")
    assert "Projekt abgeschlossen" in m.detail
    assert result.target_page_title == "November 2023"


def test_changed_character_reported():
    gw, plan, report, _, _ = plan_and_run()
    _, xml = merged(gw, report, "November 2023")
    p = planned(plan, "November 2023")
    result = verify_page(p, sources(p), xml.replace("Unterseite.", "Unterseite!"))
    (m,) = result.mismatches
    assert m.kind == "changed" and m.source_page_title == "02.11.23"


def test_heading_must_match_decision():
    gw, plan, report, _, _ = plan_and_run()
    _, xml = merged(gw, report, "Oktober 2023")
    p = planned(plan, "Oktober 2023")
    assert p.blocks[1].heading == "05.10.23"
    assert verify_page(p, sources(p), xml).ok
    wrong = PlannedPage(
        p.source_section_id,
        p.source_section_name,
        p.title,
        (
            p.blocks[0],
            TitleDecision("P2", "05.12.23", "05.12.23", TitleStatus.UNCHANGED),
            p.blocks[2],
        ),
        3,
    )
    result = verify_page(wrong, sources(p), xml)
    assert not result.ok
    assert any(m.kind == "heading" and m.source_page_id == "P2" for m in result.mismatches)

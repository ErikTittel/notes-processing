import dataclasses
import xml.etree.ElementTree as ET

from notes_processing.model import PlannedPage, TitleDecision, TitleStatus
from notes_processing.onexml import NS, q, tostring
from notes_processing.verify import (
    extract_text,
    page_paragraphs,
    split_target_blocks,
    verify_page,
)
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


def test_trailing_whitespace_at_heading_end_is_ignored():
    # A former page title "14.03.15 " arrives as heading "14.03.15": OneNote drops the space
    # (T062). The heading must still be found, so its paragraphs aren't reported as moved.
    gw, plan, report, _, _ = plan_and_run()
    _, xml = merged(gw, report, "Oktober 2023")
    p = planned(plan, "Oktober 2023")
    padded = dataclasses.replace(
        p,
        blocks=(
            p.blocks[0],
            dataclasses.replace(p.blocks[1], heading=p.blocks[1].heading + " "),
            p.blocks[2],
        ),
    )
    assert verify_page(padded, sources(p), xml).ok
    split = split_target_blocks(xml, [b.heading for b in padded.blocks])
    assert all(heading is not None for heading, _ in split)
    unpadded = split_target_blocks(xml, [b.heading for b in p.blocks])
    assert [len(els) for _, els in split] == [len(els) for _, els in unpadded]


def test_trailing_whitespace_at_paragraph_end_is_ignored():
    # OneNote drops spaces at the end of a paragraph when a page is saved (FR-011 note).
    gw, plan, report, _, _ = plan_and_run()
    _, xml = merged(gw, report, "November 2023")
    p = planned(plan, "November 2023")
    padded = [[t + "  " for t in block] for block in sources(p)]
    assert verify_page(p, padded, xml).ok


def test_other_whitespace_changes_are_still_reported():
    gw, plan, report, _, _ = plan_and_run()
    _, xml = merged(gw, report, "November 2023")
    p = planned(plan, "November 2023")
    for changed in ("Unter seite.", " Unterseite."):  # inner and leading whitespace count
        result = verify_page(p, sources(p), xml.replace("Unterseite.", changed))
        (m,) = result.mismatches
        assert m.kind == "changed" and m.source_page_title == "02.11.23"


def test_missing_or_changed_web_link_reported():
    from notes_processing.verify import page_web_links

    gw, plan, report, _, _ = plan_and_run()
    title = next(p.title for p in plan.pages if any(b.page_id == "P10" for b in p.blocks))
    _, xml = merged(gw, report, title)
    p = planned(plan, title)
    links = [page_web_links(read_fixture(f"pages/{b.page_id}.xml")) for b in p.blocks]
    assert ["https://example.org/beet?a=1&b=2"] in links
    assert verify_page(p, sources(p), xml, source_links=links).ok
    # the link turned into plain text (OneNote did not recreate it): text same, link reported
    broken = xml.replace('href="https://example.org/beet', 'href="https://example.org/other')
    result = verify_page(p, sources(p), broken, source_links=links)
    kinds = {(m.kind, m.source_page_id) for m in result.mismatches}
    assert ("link", "P10") in kinds
    assert any("Weblink fehlt: https://example.org/beet" in m.detail for m in result.mismatches)

import xml.etree.ElementTree as ET

from notes_processing.hierarchy import parse_hierarchy
from notes_processing.links import extract_links
from notes_processing.model import LinkKind, PageStatus, Scope
from notes_processing.onexml import q
from notes_processing.verify import split_target_blocks
from tests.unit.runner_helpers import plan_and_run


def target_xml(gw, report, title):
    page = next(p for p in report.pages if p.title == title)
    return gw.stored_page(page.target_page_id)


def test_one_section_creates_notebook_section_page():
    gw, _plan, report, _, _ = plan_and_run(Scope.build("2023", "23-10"))
    methods = [c[0] for c in gw.write_calls]
    assert methods[:3] == ["create_notebook", "create_section", "create_page"]
    assert methods.count("create_page") == 1
    target = parse_hierarchy(gw.hierarchy(report.target_notebook_id, 4))
    assert [g.name for g in target.groups] == []  # sections directly in the notebook
    assert report.pages[0].status == PageStatus.VERIFIED
    xml = target_xml(gw, report, "Oktober 2023")
    blocks = split_target_blocks(xml, ["04.10.23", "05.10.23", "07.10.23"])
    assert all(h is not None for h, _ in blocks)


def test_pass_one_writes_links_unchanged_then_pass_two_rewrites():
    gw, _plan, report, _, _ = plan_and_run()
    updates = [c[1][0] for c in gw.write_calls if c[0] == "update_page"]
    first_write = next(u for u in updates if "Morgens" in u)
    assert "{L-P6}" in first_write  # pass 1: original link
    xml = target_xml(gw, report, "Oktober 2023")
    link = {t: h for t, h in extract_links(xml)}["2. November"]
    nov = next(p for p in report.pages if p.title == "November 2023")
    nov_xml = gw.stored_page(nov.target_page_id)
    heading = split_target_blocks(nov_xml, ["01.11.23", "Zusammenfassung", "02.11.23"])[2][0]
    heading_oe = heading.find(f".//{q('OE')}").get("objectID")
    assert link == gw.link_to(nov.target_page_id, heading_oe)


def test_link_kinds_rewritten_to_new_objects():
    gw, _plan, report, _, _ = plan_and_run()
    garten = next(p for p in report.pages if p.title == "Garten")
    links = dict(extract_links(gw.stored_page(garten.target_page_id)))
    haus = next(p for p in report.pages if p.title == "Haus")
    okt = next(p for p in report.pages if p.title == "Oktober 2023")
    nov = next(p for p in report.pages if p.title == "November 2023")
    # page link -> heading OE on the merged page
    assert f"page-id={{L-{haus.target_page_id}}}" in links["Planung"]
    assert "object-id=" in links["Planung"]
    # paragraph link -> the matching OE ("Projekt abgeschlossen") on the merged page
    nov_page = ET.fromstring(gw.stored_page(nov.target_page_id))
    oe = next(
        o
        for o in nov_page.iter(q("OE"))
        if any(t.text == "Projekt abgeschlossen" for t in o.findall(q("T")))
    )
    assert links["Projekt"] == gw.link_to(nov.target_page_id, oe.get("objectID"))
    # section link -> merged page
    assert links["Oktober"] == gw.link_to(okt.target_page_id)
    # group link -> new section
    target_nb = ET.fromstring(gw.hierarchy(report.target_notebook_id, 4))
    projekte = next(s for s in target_nb.iter(q("Section")) if s.get("name") == "Projekte")
    assert links["Projekte"] == gw.link_to(projekte.get("ID"))
    # external stays
    assert links["Beetplan"] == "https://example.org/beet?a=1&b=2"


def test_kept_links_unchanged_and_reported():
    gw, _plan, report, _, _ = plan_and_run()
    garten = next(p for p in report.pages if p.title == "Garten")
    links = dict(extract_links(gw.stored_page(garten.target_page_id)))
    assert links["Eintrag"].startswith(r"onenote:C:\Notes\Diary")
    assert "{L-GONE}" in links["gelöscht"]
    assert links["a.pdf"] == r"C:\Docs\a.pdf"
    assert links["Mail"] == "mailto:x@example.org"
    by_text = {lo.text: lo for lo in report.links}
    assert by_text["Eintrag"].status == "kept"
    assert by_text["Eintrag"].kind == LinkKind.OUTSIDE_TRANSFER
    assert by_text["gelöscht"].kind == LinkKind.TARGET_NOT_FOUND
    assert by_text["Planung"].status == "updated"
    assert by_text["Projekt"].status == "updated"
    assert by_text["Oktober"].status == "updated"
    assert by_text["Projekte"].status == "updated"
    assert "a.pdf" not in by_text  # external links are not listed


def test_partial_run_keeps_links_outside_scope():
    gw, _plan, report, _, _ = plan_and_run(Scope.build("2023", "23-10"))
    (lo,) = report.links
    assert lo.text == "2. November"
    assert lo.status == "kept"
    assert lo.kind == LinkKind.OUTSIDE_TRANSFER
    xml = target_xml(gw, report, "Oktober 2023")
    assert "{L-P6}" in xml


def test_content_issue_reported():
    _, _, report, _, _ = plan_and_run(Scope.build("Projekte", "Garten"))
    assert [(i.source_page_title, i.element) for i in report.content_issues] == [("Ernte", "Image")]

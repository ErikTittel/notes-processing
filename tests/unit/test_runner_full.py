import xml.etree.ElementTree as ET

from notes_processing import runner
from notes_processing.hierarchy import parse_hierarchy
from notes_processing.links import extract_links
from notes_processing.model import PageStatus, Scope
from notes_processing.onenote.fake import FakeGateway
from notes_processing.onexml import q
from notes_processing.planner import make_plan
from tests.conftest import all_pages, read_fixture
from tests.unit.runner_helpers import plan_and_run


def test_scope_all_structure_and_summary():
    gw, plan, report, messages, _ = plan_and_run()
    nb = ET.fromstring(gw.hierarchy(report.target_notebook_id, 4))
    sections = nb.findall(q("Section"))
    assert [s.get("name") for s in sections] == ["2023", "Projekte"]
    assert [[p.get("name") for p in s.findall(q("Page"))] for s in sections] == [
        ["Oktober 2023", "November 2023"],
        ["Haus", "Garten"],
    ]
    assert all(p.status == PageStatus.VERIFIED for p in report.pages)
    s = report.summary
    assert (s.sections, s.pages, s.source_pages, s.completed, s.skipped, s.failed) == (
        2,
        4,
        12,
        4,
        0,
        0,
    )
    assert len(messages) == 2 and "[1/2]" in messages[0]
    assert report.title_decisions == plan.title_decisions
    assert report.plan_fingerprint == plan.fingerprint


def test_cross_section_link_to_heading_on_other_merged_page():
    gw, _, report, _, _ = plan_and_run()
    okt = next(p for p in report.pages if p.title == "Oktober 2023")
    nov = next(p for p in report.pages if p.title == "November 2023")
    href = dict(extract_links(gw.stored_page(okt.target_page_id)))["2. November"]
    assert f"page-id={{L-{nov.target_page_id}}}" in href


def test_locked_section_reported_skipped():
    gw = FakeGateway(read_fixture("hierarchy_edge.xml"), {})
    source = parse_hierarchy(gw.hierarchy("ENB", 4))
    # no page content in the edge fixture: give every page a minimal body
    for g in source.groups:
        for s in g.sections:
            for p in s.pages:
                gw.set_page(p.id, all_pages()["P2"].replace('ID="P2"', f'ID="{p.id}"'))
    plan, indexed = make_plan(gw, source, Scope(), "Neu", r"C:\Out")
    report = runner.run(plan, gw, indexed, progress=lambda m: None, clock=lambda: "T")
    skipped = [
        (p.source_section_name, p.status) for p in report.pages if p.status == PageStatus.SKIPPED
    ]
    assert skipped == [("X", PageStatus.SKIPPED), ("B2", PageStatus.SKIPPED)]
    assert report.summary.skipped == 2
    assert report.summary.completed == 5
    leer = next(p for p in report.pages if p.title == "Leer")
    assert leer.status == PageStatus.VERIFIED

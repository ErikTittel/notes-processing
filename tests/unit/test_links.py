import pytest

from notes_processing.hierarchy import parse_hierarchy
from notes_processing.links import (
    LinkIndex,
    classify,
    extract_links,
    parse_onenote_href,
    rewrite_hrefs,
    same_target,
)
from notes_processing.model import LinkKind, Scope
from notes_processing.planner import index_links, scope_ids
from tests.conftest import make_gateway, read_fixture

B = r"onenote:C:\Notes\Test-NB"
ALL = Scope()


def test_parse_page_and_paragraph_links():
    p = parse_onenote_href(B + r"\2023\23-11.one#02.11.23&section-id={L-S2}&page-id={L-P6}&end")
    assert p.path == r"C:\Notes\Test-NB\2023\23-11.one"
    assert p.title == "02.11.23"
    assert (p.section_guid, p.page_guid, p.object_guid) == ("{L-S2}", "{L-P6}", None)
    real = (
        "onenote:https://d.docs.live.net/abc/Dokumente/OneNote-Test/2023/23-10.one#04.10.23"
        "&section-id={6A1B2C3D-0000-1111-2222-333344445555}"
        "&page-id={ABCDEF01-2345-6789-ABCD-EF0123456789}"
        "&object-id={11111111-2222-3333-4444-555555555555}&8&end"
    )
    p = parse_onenote_href(real)
    assert p.object_guid == "{11111111-2222-3333-4444-555555555555}"
    assert p.title == "04.10.23"


def test_parse_section_and_group_links():
    p = parse_onenote_href(B + r"\2023\23-10.one#section-id={L-S1}&end")
    assert (p.title, p.section_guid, p.page_guid) == ("", "{L-S1}", None)
    p = parse_onenote_href(B + r"\Projekte")
    assert p.path.endswith("Projekte") and p.section_guid is None
    assert parse_onenote_href("https://example.org") is None


def index(scope=ALL):
    gw = make_gateway()
    source = index_links(gw, parse_hierarchy(read_fixture("hierarchy_small.xml")), scope)
    sections, groups = scope_ids(source, scope)
    return LinkIndex.build(source, sections, groups)


@pytest.mark.parametrize(
    ("href", "kind", "target"),
    [
        (
            B + r"\2023\23-11.one#02.11.23&section-id={L-S2}&page-id={L-P6}&end",
            LinkKind.TRANSFERRED_PAGE,
            "P6",
        ),
        (
            B + r"\2023\23-11.one#Z&section-id={L-S2}&page-id={L-P5}&object-id={L-P5/P5-oe3}&end",
            LinkKind.TRANSFERRED_PARAGRAPH,
            "P5",
        ),
        (B + r"\2023\23-10.one#section-id={L-S1}&end", LinkKind.TRANSFERRED_SECTION, "S1"),
        (B + r"\Projekte", LinkKind.TRANSFERRED_GROUP, "G2"),
        (B + "\\Projekte\\", LinkKind.TRANSFERRED_GROUP, "G2"),
        (
            r"onenote:C:\Notes\Diary\Allgemein.one#E&section-id={L-DS1}&page-id={L-DP1}&end",
            LinkKind.OUTSIDE_TRANSFER,
            None,
        ),
        (
            B + r"\2023\23-10.one#Weg&section-id={L-S1}&page-id={L-GONE}&end",
            LinkKind.TARGET_NOT_FOUND,
            None,
        ),
        (
            B + r"\Alt\weg.one#x&section-id={L-OLD}&page-id={L-OLDP}&end",
            LinkKind.TARGET_NOT_FOUND,
            None,
        ),
        ("https://example.org/a", LinkKind.EXTERNAL, None),
        (r"C:\Docs\a.pdf", LinkKind.EXTERNAL, None),
        (r"\\server\share\b.docx", LinkKind.EXTERNAL, None),
        ("mailto:x@example.org", LinkKind.EXTERNAL, None),
    ],
)
def test_classify_scope_all(href, kind, target):
    assert classify(href, index()) == (kind, target)


def test_relative_links_with_base_path():
    # Shapes as stored by OneNote inside pages (seen in the integration run).
    same_section = (
        "onenote:#Oktober%202023&section-id={L-S1}&page-id={L-P1}&end"
        r"&base-path=C:\Notes\Test-NB\2023\23-10.one"
    )
    p = parse_onenote_href(same_section)
    assert p.path == r"C:\Notes\Test-NB\2023\23-10.one"
    assert p.title == "Oktober 2023"
    other_section = (
        "onenote:23-11.one#02.11.23&section-id={L-S2}&page-id={L-P6}&end"
        r"&base-path=C:\Notes\Test-NB\2023"
    )
    assert parse_onenote_href(other_section).path == r"C:\Notes\Test-NB\2023\23-11.one"
    assert classify(other_section, index()) == (LinkKind.TRANSFERRED_PAGE, "P6")
    dead = (
        "onenote:Alt.one#x&section-id={L-OLD}&page-id={L-OLDP}&end"
        r"&base-path=C:\Notes\Test-NB\2023"
    )
    assert classify(dead, index()) == (LinkKind.TARGET_NOT_FOUND, None)
    group = r"onenote:Projekte&base-path=C:\Notes\Test-NB"
    assert classify(group, index()) == (LinkKind.TRANSFERRED_GROUP, "G2")


def test_triple_slash_and_same_target():
    absolute = r"onenote:///C:\Notes\Test-NB\Projekte"
    assert classify(absolute, index()) == (LinkKind.TRANSFERRED_GROUP, "G2")
    a = r"onenote:///C:\X\2023.one#T&section-id={A}&page-id={B}&object-id={C}&5D"
    b = r"onenote:#T&section-id={a}&page-id={b}&object-id={c}&5D&base-path=C:\X\2023.one"
    assert same_target(a, b)
    assert not same_target(a, b.replace("{c}", "{d}"))


def test_classify_partial_run_outside_transfer():
    idx = index(Scope.build("Projekte", None))
    href = B + r"\2023\23-11.one#02.11.23&section-id={L-S2}&page-id={L-P6}&end"
    assert classify(href, idx) == (LinkKind.OUTSIDE_TRANSFER, None)
    assert classify(B + r"\2023", idx) == (LinkKind.OUTSIDE_TRANSFER, None)
    assert classify(B + r"\Projekte", idx) == (LinkKind.TRANSFERRED_GROUP, "G2")


def test_extract_links():
    links = extract_links(read_fixture("pages/P10.xml"))
    assert [t for t, _ in links] == ["Planung", "Projekt", "Oktober", "Projekte", "Beetplan"]
    assert links[4][1] == "https://example.org/beet?a=1&b=2"
    assert "&amp;" not in links[0][1]


def test_rewrite_changes_only_href():
    xml = read_fixture("pages/P10.xml")
    old = extract_links(xml)[0][1]
    out = rewrite_hrefs(xml, {old: "onenote:NEU#x&page-id={N}&end"})
    links = extract_links(out)
    assert links[0] == ("Planung", "onenote:NEU#x&page-id={N}&end")
    assert links[1:] == extract_links(xml)[1:]
    # visible text of the page is unchanged
    from notes_processing.verify import page_paragraphs

    assert page_paragraphs(out) == page_paragraphs(xml)

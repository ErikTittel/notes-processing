import xml.etree.ElementTree as ET

import pytest

from notes_processing.hierarchy import parse_hierarchy
from notes_processing.model import Scope
from notes_processing.onexml import content_elements, local, q
from notes_processing.pagebuilder import build_target_page
from notes_processing.planner import build_plan
from notes_processing.verify import page_paragraphs, paragraphs, split_target_blocks
from tests.conftest import make_gateway, read_fixture

SOURCE = parse_hierarchy(read_fixture("hierarchy_small.xml"))
PLAN = build_plan(SOURCE, Scope(), "Neu", r"C:\Out")
PAGES = {p.id: p for g in SOURCE.groups for s in g.sections for p in s.pages}


def build(index):
    planned = PLAN.pages[index]
    gw = make_gateway()
    gw.create_notebook(r"C:\Out", "Neu")
    pid = gw.create_page(gw.create_section("x"))
    sources = [
        (PAGES[b.page_id], b, read_fixture(f"pages/{b.page_id}.xml")) for b in planned.blocks
    ]
    xml, issues = build_target_page(planned, sources, gw.page_xml(pid))
    return planned, sources, ET.fromstring(xml), xml, issues


def styles(page):
    return {e.get("index"): e.get("name") for e in page.findall(q("QuickStyleDef"))}


def test_object_ids_removed_and_title_set():
    _planned, _, page, _, _ = build(0)
    content = content_elements(page)
    assert all("objectID" not in n.attrib for el in content for n in el.iter())
    assert page.find(f"{q('Title')}/{q('OE')}/{q('T')}").text == "Oktober 2023"


def test_headings_in_order_with_levels():
    planned, _, page, xml, _ = build(1)  # 23-11: 01.11.23, Zusammenfassung, 02.11.23 (level 2)
    names = styles(page)
    blocks = split_target_blocks(xml, [b.heading for b in planned.blocks])
    heads = [b[0] for b in blocks]
    assert all(h is not None for h in heads)
    levels = [names[h.find(f".//{q('OE')}").get("quickStyleIndex")] for h in heads]
    assert levels == ["h1", "h1", "h2"]
    assert [x.get("x") for h in heads for x in h.findall(q("Position"))] == ["36"] * 3


def test_corrected_heading_used():
    _planned, _, _, xml, _ = build(0)
    blocks = split_target_blocks(xml, ["04.10.23", "05.10.23", "07.10.23"])
    assert all(b[0] is not None for b in blocks)


def test_style_indexes_remapped_by_name():
    _, _, page, _, _ = build(1)
    names = styles(page)
    assert len(set(names.values())) == len(names)  # merged by name, no duplicates
    oes = [oe for el in content_elements(page) for oe in el.iter(q("OE"))]
    by_text = {
        "".join(t.text for t in oe.findall(q("T"))): names[oe.get("quickStyleIndex")] for oe in oes
    }
    assert by_text["Überschrift im Text"] == "h2"
    assert by_text["Normaler Absatz"] == "p"
    assert by_text["privat"] == "p"


def test_text_and_formatting_unchanged():
    planned, sources, _, xml, _ = build(0)
    blocks = split_target_blocks(xml, [b.heading for b in planned.blocks])
    for (_, _, src_xml), (_, elements) in zip(sources, blocks, strict=True):
        raw_src = [
            t.text for el in content_elements(ET.fromstring(src_xml)) for t in el.iter(q("T"))
        ]
        raw_dst = [t.text for el in elements for t in el.iter(q("T"))]
        assert raw_src == raw_dst  # byte-identical inside one:T (incl. bold span, link)
    # list bullets survive
    assert xml.count("Bullet") == 2


def test_table_copied():
    planned, sources, _, xml, _ = build(2)
    assert "Table" in xml and "12.000 €" in xml
    assert page_paragraphs(sources[1][2]) == ["Dach", "12.000 €"]
    blocks = split_target_blocks(xml, [b.heading for b in planned.blocks])
    assert [p for el in blocks[1][1] for p in paragraphs(el)] == ["Dach", "12.000 €"]


def test_title_only_page_heading_without_content():
    planned, _, _, xml, _ = build(2)  # Haus: Planung, Kosten, Notizen (title only)
    blocks = split_target_blocks(xml, [b.heading for b in planned.blocks])
    assert blocks[2][0] is not None and blocks[2][1] == []


def test_images_files_media_copied():
    _, _, page, _, issues = build(2)
    tags = [local(e.tag) for e in content_elements(page)]
    assert tags.count("Image") == 1
    f = page.find(q("InsertedFile"))
    m = page.find(q("MediaFile"))
    assert f.get("pathSource") == r"C:\Cache\{AA}.bin"
    assert m.get("pathSource") == r"C:\Cache\{BB}.bin"
    assert page.find(f"{q('Image')}/{q('Data')}") is not None
    assert issues == []


def test_uncopyable_content_reported_not_dropped_silently():
    _, _, page, _, issues = build(3)  # Garten: Ernte has an image without data
    assert len(issues) == 1
    assert issues[0].source_page_id == "P12"
    assert issues[0].source_page_title == "Ernte"
    assert issues[0].element == "Image"
    assert page.find(q("InkDrawing")) is not None


def test_blocks_do_not_overlap_and_keep_columns():
    planned, _, _, xml, _ = build(1)
    blocks = split_target_blocks(xml, [b.heading for b in planned.blocks])
    zus = blocks[1][1]
    xs = sorted({float(el.find(q("Position")).get("x")) for el in zus})
    assert xs == [36.0, 360.0]
    tops = [float(b[0].find(q("Position")).get("y")) for b in blocks]
    assert tops == sorted(tops)
    for (head, els), nxt in zip(blocks, tops[1:], strict=False):
        for el in els:
            y = float(el.find(q("Position")).get("y"))
            h = float(el.find(q("Size")).get("height"))
            assert y + h < nxt


@pytest.mark.parametrize("index", range(4))
def test_structure_order(index):
    _, _, page, _, _ = build(index)
    order = [local(e.tag) for e in page]
    first_content = order.index("Title")
    assert all(t not in ("QuickStyleDef", "TagDef") for t in order[first_content:])
    assert order[0] == "QuickStyleDef"

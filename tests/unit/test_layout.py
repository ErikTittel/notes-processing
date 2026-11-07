import xml.etree.ElementTree as ET

import pytest

from notes_processing.layout import BlockInput, BlockPlacement, Box, find_overlaps, layout_blocks
from notes_processing.onexml import content_elements, q
from tests.conftest import read_fixture


def test_first_block_below_title_and_heading_position():
    (p,) = layout_blocks([BlockInput((Box(36, 86.4, 400, 60),))], 80, 30, margin=0)
    assert p.top == 80
    assert (p.heading.x, p.heading.y) == (36, 80)
    assert p.elements[0] == Box(36, 110, 400, 60)
    assert p.bottom == 170


def test_elements_keep_x_and_relative_y_and_gap():
    blocks = [
        BlockInput((Box(50, 100, 200, 40), Box(300, 120, 100, 20))),
        BlockInput((Box(36, 200, 100, 10),)),
    ]
    a, b = layout_blocks(blocks, 80, 30, gap=36, margin=0)
    assert [(e.x, e.y) for e in a.elements] == [(50, 110), (300, 130)]
    assert a.bottom == 150
    assert b.top == a.bottom + 36
    assert b.elements[0].y == b.top + 30


def test_margin_added_to_bottom():
    (p,) = layout_blocks([BlockInput((Box(36, 0, 10, 10),))], 0, 30, margin=6)
    assert p.bottom == 46


def test_empty_block_is_heading_only():
    (p,) = layout_blocks([BlockInput(())], 80, 30, margin=0)
    assert p.elements == () and p.bottom == 110


def zusammenfassung_boxes():
    page = ET.fromstring(read_fixture("pages/P5.xml"))
    boxes = []
    for el in content_elements(page):
        pos, size = el.find(q("Position")), el.find(q("Size"))
        boxes.append(
            Box(
                float(pos.get("x")),
                float(pos.get("y")),
                float(size.get("width")),
                float(size.get("height")),
            )
        )
    return boxes


def test_two_column_page_keeps_relative_positions():
    boxes = zusammenfassung_boxes()
    assert len(boxes) == 5
    before = BlockInput((Box(36, 86.4, 400, 300),))
    placements = layout_blocks([before, BlockInput(tuple(boxes)), before], 80, 30)
    mid = placements[1]
    min_y = min(b.y for b in boxes)
    for src, dst in zip(boxes, mid.elements, strict=True):
        assert dst.x == src.x
        assert dst.y - mid.elements[0].y == pytest.approx(src.y - boxes[0].y)
        assert dst.y == pytest.approx(mid.top + 30 + (src.y - min_y))
    assert find_overlaps(placements) == []


def test_overlap_detected():
    a = BlockPlacement(0, Box(36, 0, 400, 30), (Box(36, 30, 400, 100),), 130)
    b = BlockPlacement(100, Box(36, 100, 400, 30), (), 130)
    assert find_overlaps([a, b]) == [(0, 1)]

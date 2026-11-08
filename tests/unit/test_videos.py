import xml.etree.ElementTree as ET

from notes_processing.hierarchy import parse_hierarchy
from notes_processing.model import Scope
from notes_processing.onexml import NS, parse, q
from notes_processing.pagebuilder import build_target_page
from notes_processing.planner import build_plan
from notes_processing.videos import find_video_previews, is_video_preview
from tests.conftest import make_gateway, read_fixture

YT = "https://www.youtube.com/watch?v=ujRwf1HdNjk&ab_channel=TheDiaryOfACEO"
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


def oe_text(text: str) -> str:
    return f"<one:OE><one:T><![CDATA[{text}]]></one:T></one:OE>"


def link(href: str, text: str = "Video") -> str:
    return oe_text(f'schaue <a href="{href.replace("&", "&amp;")}">{text}</a>')


def image(width="267.0", height="150.0", extra="", attrs="") -> str:
    return (
        f'<one:OE><one:Image{attrs}><one:Size width="{width}" height="{height}"{extra}/>'
        f"<one:Data>{PNG}</one:Data></one:Image></one:OE>"
    )


def page(*oes: str, title: str = "25.07.23") -> str:
    return (
        f'<one:Page xmlns:one="{NS}" ID="P1" name="{title}">'
        f"<one:Title><one:OE><one:T><![CDATA[{title}]]></one:T></one:OE></one:Title>"
        '<one:Outline><one:Position x="36" y="86.4" z="0"/><one:Size width="432" height="244"/>'
        f"<one:OEChildren>{''.join(oes)}</one:OEChildren></one:Outline></one:Page>"
    )


def test_preview_shapes():
    def img(xml):
        return ET.fromstring(f'<w xmlns:one="{NS}">{xml}</w>')[0][0]

    assert is_video_preview(img(image()))
    assert is_video_preview(img(image("360.0", "202.5")))
    assert is_video_preview(img(image("100", "80", attrs=' alt="Webinhalte"')))
    assert not is_video_preview(img(image(extra=' isSetByUser="true"')))
    assert not is_video_preview(img(image("300", "200")))


def test_video_link_before_after_and_none():
    other = "https://example.org/x"
    found = find_video_previews(parse(page(link(other), link(YT), oe_text(""), image())))
    assert [url for _, url in found] == [YT]
    found = find_video_previews(parse(page(image(), link("https://youtu.be/kfg_e6YG37U"))))
    assert [url for _, url in found] == ["https://youtu.be/kfg_e6YG37U"]
    assert [url for _, url in find_video_previews(parse(page(link(other), image())))] == [None]
    assert find_video_previews(parse(page(link(YT), image("300", "200")))) == []


SOURCE = parse_hierarchy(read_fixture("hierarchy_small.xml"))
PAGES = {p.id: p for g in SOURCE.groups for s in g.sections for p in s.pages}
VIDEO_PAGE = page(link(YT), image())


def loader(pid: str) -> str:
    return VIDEO_PAGE if pid == "P1" else read_fixture(f"pages/{pid}.xml")


def test_plan_lists_video_preview():
    plan = build_plan(SOURCE, Scope(), "Neu", r"C:\Out", page_loader=loader)
    items = [a for a in plan.attention if a.kind == "video_preview"]
    assert len(items) == 1
    assert items[0].source_id == "P1"
    assert items[0].names[-1] == PAGES["P1"].title
    assert YT in items[0].message and "verlinkt" in items[0].message


def test_target_preview_links_to_video_and_is_reported():
    plan = build_plan(SOURCE, Scope(), "Neu", r"C:\Out")
    planned = next(p for p in plan.pages if p.blocks[0].page_id == "P1")
    sources = [(PAGES[b.page_id], b, loader(b.page_id)) for b in planned.blocks]
    gw = make_gateway()
    gw.create_notebook(r"C:\Out", "Neu")
    pid = gw.create_page(gw.create_section("x"))
    xml, issues = build_target_page(planned, sources, gw.page_xml(pid))
    images = list(parse(xml).iter(q("Image")))
    assert [i.get("hyperlink") for i in images] == [YT]
    assert images[0].find(q("Data")) is not None
    video = [i for i in issues if i.element == "Video"]
    assert len(video) == 1 and video[0].source_page_id == "P1" and YT in video[0].message


def test_existing_image_link_is_kept():
    plan = build_plan(SOURCE, Scope(), "Neu", r"C:\Out")
    planned = next(p for p in plan.pages if p.blocks[0].page_id == "P1")
    own = page(link(YT), image(attrs=' hyperlink="https://example.org/own"'))
    sources = [
        (PAGES[b.page_id], b, own if b.page_id == "P1" else loader(b.page_id))
        for b in planned.blocks
    ]
    gw = make_gateway()
    gw.create_notebook(r"C:\Out", "Neu")
    pid = gw.create_page(gw.create_section("x"))
    xml, issues = build_target_page(planned, sources, gw.page_xml(pid))
    assert [i.get("hyperlink") for i in parse(xml).iter(q("Image"))] == ["https://example.org/own"]
    assert "bisherigen Link" in next(i.message for i in issues if i.element == "Video")

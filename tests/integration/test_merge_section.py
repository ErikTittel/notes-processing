"""T032: merge one section in a throwaway OneNote notebook (needs the OneNote desktop app)."""

import pytest

from notes_processing import runner
from notes_processing.hierarchy import parse_hierarchy
from notes_processing.links import extract_links, same_target
from notes_processing.model import PageStatus, Scope
from notes_processing.onenote.gateway import HS_PAGES, OneNoteGateway
from notes_processing.onexml import content_elements, local, parse, q
from notes_processing.planner import make_plan
from notes_processing.verify import page_paragraphs, split_target_blocks

from .conftest import CREATED, build_notebook, image, inserted_file, link, media_file, outline

pytestmark = pytest.mark.onenote


def spec(files):
    return {
        "2023": {
            "23-10": [
                (
                    "04.10.23",
                    1,
                    [
                        outline(
                            36,
                            86,
                            400,
                            80,
                            [
                                "Morgens <span style='font-weight:bold'>Kaffee</span>.",
                                "Siehe " + link("2023/23-10/Zusammenfassung", "Zusammenfassung"),
                                "Web: " + link("https://example.org/", "Beispiel"),
                                # A web link right after "(", as in the real notes. Sent as
                                # plain text, so OneNote links it without inserting a space.
                                # The trailing space is dropped by OneNote (FR-007, FR-011).
                                "Klammer (https://example.org/k) Ende ",
                            ],
                        )
                    ],
                ),
                (
                    "05.12.23",
                    1,
                    [
                        outline(36, 86, 400, 30, ["Mit Anhängen"]),
                        image(36, 130),
                        inserted_file(files["file"], 100, 130),
                        media_file(files["audio"], 200, 130),
                    ],
                ),
                (
                    "Zusammenfassung",
                    1,
                    [
                        outline(36, 86, 280, 60, ["privat", "Arbeit"]),
                        outline(360, 86, 280, 80, ["Bücher", "Sport und Gesundheit"]),
                    ],
                ),
            ],
        },
    }


def test_merge_one_section(it_folder, attachments):
    builder = OneNoteGateway()
    ids = build_notebook(builder, it_folder, f"np-it-{it_folder.name}-s1-src", spec(attachments))

    gw = OneNoteGateway()
    source = parse_hierarchy(gw.hierarchy(ids[""], HS_PAGES))
    scope = Scope.build("2023", "23-10")
    target_name = f"np-it-{it_folder.name}-s1-out"
    plan, indexed = make_plan(gw, source, scope, target_name, str(it_folder))
    assert [p.title for p in plan.pages] == ["Oktober 2023"]
    report = runner.run(plan, gw, indexed)
    CREATED.append(str(it_folder / target_name))
    (outcome,) = report.pages
    assert outcome.status == PageStatus.VERIFIED, report
    assert report.content_issues == ()

    xml = gw.page_xml(outcome.target_page_id)
    page = parse(xml)
    blocks = split_target_blocks(xml, ["04.10.23", "05.10.23", "Zusammenfassung"])
    assert all(h is not None for h, _ in blocks)

    # image, embedded file and audio came through pathCache (research R3 open point)
    tags = [local(e.tag) for _, els in blocks for e in els]
    assert {"Image", "InsertedFile", "MediaFile"} <= set(tags)
    assert page.find(f".//{q('Image')}/{q('Data')}") is not None

    # side-by-side outlines keep their columns
    zus = [e for e in blocks[2][1] if local(e.tag) == "Outline"]
    assert sorted(float(e.find(q("Position")).get("x")) for e in zus) == [36.0, 360.0]

    # page link now points at the heading on the merged page, web link unchanged
    links = dict(extract_links(xml))
    heading_oe = blocks[2][0].find(f".//{q('OE')}").get("objectID")
    assert same_target(links["Zusammenfassung"], gw.link_to(outcome.target_page_id, heading_oe))
    assert links["Beispiel"] == "https://example.org/"

    # The web link right after "(" is a link on the source page (precondition), and on the
    # merged page it is still a link to the same address with no space inserted before it.
    url = "https://example.org/k"
    src_xml = gw.page_xml(ids["2023/23-10/04.10.23"], False)
    assert dict(extract_links(src_xml)).get(url) == url
    assert links.get(url) == url
    assert "Klammer (https://example.org/k) Ende" in [t.rstrip() for t in page_paragraphs(xml)]
    assert len(content_elements(page)) >= 9

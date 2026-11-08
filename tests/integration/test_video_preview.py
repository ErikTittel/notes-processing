"""T061: an embedded video's preview picture arrives linked to the video (needs OneNote)."""

import pytest

from notes_processing import runner
from notes_processing.hierarchy import parse_hierarchy
from notes_processing.model import PageStatus, Scope
from notes_processing.onenote.gateway import HS_PAGES, OneNoteGateway
from notes_processing.onexml import parse, q
from notes_processing.planner import make_plan

from .conftest import CREATED, PNG, build_notebook, link, outline

pytestmark = pytest.mark.onenote

YT = "https://www.youtube.com/watch?v=ujRwf1HdNjk&ab_channel=TheDiaryOfACEO"


def preview(x: float, y: float) -> str:
    """An image like OneNote's preview of an embedded online video.

    Written through the API, OneNote marks every size as set by the user, so the preview is
    recognised by its alternative text here (videos.PREVIEW_ALT).
    """
    return (
        f'<one:Image format="png" alt="Webinhalt"><one:Position x="{x}" y="{y}" z="1"/>'
        f'<one:Size width="267.0" height="150.0"/><one:Data>{PNG}</one:Data></one:Image>'
    )


def test_video_preview_linked(it_folder):
    spec = {
        "2023": {
            "23-07": [
                (
                    "25.07.23",
                    1,
                    [
                        outline(36, 86, 400, 30, ["schaue " + link(YT, "Video")]),
                        preview(36, 130),
                    ],
                )
            ]
        }
    }
    ids = build_notebook(OneNoteGateway(), it_folder, f"np-it-{it_folder.name}-v-src", spec)
    gw = OneNoteGateway()
    source = parse_hierarchy(gw.hierarchy(ids[""], HS_PAGES))
    target_name = f"np-it-{it_folder.name}-v-out"
    plan, indexed = make_plan(gw, source, Scope.build("2023", "23-07"), target_name, str(it_folder))
    assert [a.kind for a in plan.attention].count("video_preview") == 1
    report = runner.run(plan, gw, indexed)
    CREATED.append(str(it_folder / target_name))
    (outcome,) = report.pages
    assert outcome.status == PageStatus.VERIFIED, report
    assert [c.element for c in report.content_issues] == ["Video"]

    page = parse(gw.page_xml(outcome.target_page_id, False))
    assert [i.get("hyperlink") for i in page.iter(q("Image"))] == [YT]

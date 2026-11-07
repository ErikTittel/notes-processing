"""T052: `verify` finds a paragraph changed after the merge."""

import json

import pytest

from notes_processing import cli
from notes_processing.onenote.gateway import OneNoteGateway
from notes_processing.onexml import NS, content_elements, parse, q, tostring

from .conftest import CREATED, build_notebook, outline

pytestmark = pytest.mark.onenote


def test_verify_detects_change(it_folder, tmp_path):
    name = f"np-it-{it_folder.name}-verify-src"
    spec = {
        "2023": {
            "23-10": [
                ("01.10.23", 1, [outline(36, 86, 400, 40, ["bleibt", "wird entfernt"])]),
                ("02.10.23", 1, [outline(36, 86, 400, 40, ["auch da"])]),
            ]
        }
    }
    build_notebook(OneNoteGateway(), it_folder, name, spec)
    target = f"np-it-{it_folder.name}-verify-out"
    run_dir = tmp_path / "run"
    gw = OneNoteGateway()
    assert (
        cli.main(
            [
                "plan",
                "--source",
                name,
                "--target",
                target,
                "--target-folder",
                str(it_folder),
                "--out",
                str(run_dir),
                "--group",
                "2023",
                "--section",
                "23-10",
            ],
            gateway_factory=lambda: gw,
        )
        == 0
    )
    CREATED.append(str(it_folder / target))
    assert (
        cli.main(
            ["apply", "--plan", str(run_dir / "plan.json"), "--yes"], gateway_factory=lambda: gw
        )
        == 0
    )

    # Empty one paragraph on the target page (partial update of its outline).
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    pid = report["pages"][0]["target_page_id"]
    page = parse(gw.page_xml(pid))
    for el in content_elements(page):
        for t in el.iter(q("T")):
            if t.text and "wird entfernt" in t.text:
                t.text = ""
                update = parse(f'<one:Page xmlns:one="{NS}" ID="{pid}"/>')
                update.append(el)
                gw.update_page(tostring(update))
                break

    assert (
        cli.main(
            ["verify", "--report", str(run_dir / "report.json")], gateway_factory=OneNoteGateway
        )
        == cli.ITEMS_FAILED
    )
    md = (run_dir / "verify.md").read_text(encoding="utf-8")
    assert "### Oktober 2023" in md
    assert "01.10.23" in md and "wird entfernt" in md

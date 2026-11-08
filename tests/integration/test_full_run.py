"""T046: whole-notebook run through the CLI in a throwaway OneNote notebook."""

import xml.etree.ElementTree as ET

import pytest

from notes_processing import cli
from notes_processing.hierarchy import notebooks, parse_hierarchy
from notes_processing.links import extract_links, same_target
from notes_processing.onenote.gateway import HS_NOTEBOOKS, HS_PAGES, OneNoteGateway
from notes_processing.onexml import q
from notes_processing.verify import split_target_blocks

from .conftest import (
    CREATED,
    build_notebook,
    image,
    inserted_file,
    link,
    outline,
    settled_hierarchy,
)

pytestmark = pytest.mark.onenote


def pages(prefix, files, extra=None):
    out = [
        (f"01.{prefix}", 1, [outline(36, 86, 400, 40, [f"Erster Tag {prefix}"]), image(36, 140)]),
        (
            f"02.{prefix}",
            1,
            [
                outline(36, 86, 250, 40, ["links"]),
                outline(320, 86, 250, 40, ["rechts"]),
                inserted_file(files["file"], 36, 140),
            ],
        ),
        (f"03.{prefix}", 2, [outline(36, 86, 400, 40, [f"Unterseite {prefix}"])]),
    ]
    if extra:
        out[0][2].append(extra)
    return out


def test_full_run(it_folder, attachments, tmp_path):
    name = f"np-it-{it_folder.name}-full-src"
    jump = outline(36, 200, 400, 30, ["Sprung: " + link("Projekte/24-02/02.02.24", "Februar")])
    spec = {
        "2023": {"23-10": pages("10.23", attachments, jump), "23-11": pages("11.23", attachments)},
        "Projekte": {"24-01": pages("01.24", attachments), "24-02": pages("02.24", attachments)},
    }
    ids = build_notebook(OneNoteGateway(), it_folder, name, spec)
    before = settled_hierarchy(OneNoteGateway(), ids[""])

    target = f"np-it-{it_folder.name}-full-out"
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
            ],
            gateway_factory=lambda: gw,
        )
        == 0
    )
    CREATED.append(str(it_folder / target))
    code = cli.main(
        ["apply", "--plan", str(run_dir / "plan.json"), "--yes"], gateway_factory=lambda: gw
    )
    assert code == cli.OK, (run_dir / "report.md").read_text(encoding="utf-8")

    target_id = notebooks(gw.hierarchy("", HS_NOTEBOOKS))[target]
    nb = ET.fromstring(gw.hierarchy(target_id, HS_PAGES))
    sections = nb.findall(q("Section"))
    assert [s.get("name") for s in sections] == ["2023", "Projekte"]
    assert [[p.get("name") for p in s.findall(q("Page"))] for s in sections] == [
        ["Oktober 2023", "November 2023"],
        ["Januar 2024", "Februar 2024"],
    ]

    okt = sections[0].find(q("Page")).get("ID")
    feb = sections[1].findall(q("Page"))[1].get("ID")
    href = dict(extract_links(gw.page_xml(okt)))["Februar"]
    feb_xml = gw.page_xml(feb)
    heading = split_target_blocks(feb_xml, ["01.02.24", "02.02.24", "03.02.24"])[1][0]
    assert same_target(href, gw.link_to(feb, heading.find(f".//{q('OE')}").get("objectID")))

    after = parse_hierarchy(OneNoteGateway().hierarchy(ids[""], HS_PAGES))
    assert after == before  # includes every lastModifiedTime: the source is unchanged

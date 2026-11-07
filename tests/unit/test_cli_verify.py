import json
import xml.etree.ElementTree as ET

from notes_processing import cli
from notes_processing.onexml import q, tostring
from tests.conftest import make_gateway


def apply_run(tmp_path):
    gw = make_gateway()
    out = tmp_path / "run"
    assert (
        cli.main(
            [
                "plan",
                "--source",
                "Test-NB",
                "--target",
                "Neu",
                "--target-folder",
                str(tmp_path / "nb"),
                "--out",
                str(out),
            ],
            gateway_factory=lambda: gw,
        )
        == 0
    )
    assert (
        cli.main(["apply", "--plan", str(out / "plan.json"), "--yes"], gateway_factory=lambda: gw)
        == 0
    )
    return gw, out


def test_verify_clean_run(tmp_path):
    gw, out = apply_run(tmp_path)
    n = len(gw.write_calls)
    assert (
        cli.main(["verify", "--report", str(out / "report.json")], gateway_factory=lambda: gw)
        == cli.OK
    )
    assert len(gw.write_calls) == n
    assert "4 von 4 Seiten ohne Abweichung." in (out / "verify.md").read_text(encoding="utf-8")


def test_verify_detects_removed_paragraph(tmp_path):
    gw, out = apply_run(tmp_path)
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    okt = next(p for p in report["pages"] if p["title"] == "Oktober 2023")
    page = ET.fromstring(gw.stored_page(okt["target_page_id"]))
    for parent in page.iter():
        for child in list(parent):
            if child.tag == q("OE") and "Ein normaler Tag." in "".join(
                t.text or "" for t in child.findall(q("T"))
            ):
                parent.remove(child)
    gw.set_page(okt["target_page_id"], tostring(page))
    n = len(gw.write_calls)
    assert (
        cli.main(["verify", "--report", str(out / "report.json")], gateway_factory=lambda: gw)
        == cli.ITEMS_FAILED
    )
    assert len(gw.write_calls) == n
    md = (out / "verify.md").read_text(encoding="utf-8")
    assert "### Oktober 2023" in md
    assert "| 05.12.23 | missing | fehlt: „Ein normaler Tag.“ |" in md

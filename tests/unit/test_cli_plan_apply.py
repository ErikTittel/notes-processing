import json

import pytest

from notes_processing import cli, runner
from notes_processing.onenote.errors import OneNoteUnavailable
from notes_processing.onenote.fake import FakeGateway
from tests.conftest import all_pages, make_gateway, read_fixture


@pytest.fixture
def gw():
    return make_gateway()


def run(argv, gw):
    return cli.main(argv, gateway_factory=lambda: gw)


def make_plan(tmp_path, gw, *extra):
    out = tmp_path / "run"
    code = run(
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
            *extra,
        ],
        gw,
    )
    return code, out


def test_plan_writes_files_without_writing_onenote(tmp_path, gw):
    code, out = make_plan(tmp_path, gw)
    assert code == cli.OK
    assert (out / "plan.json").exists() and (out / "plan.md").exists()
    assert gw.write_calls == []
    assert json.loads((out / "plan.json").read_text(encoding="utf-8"))["format_version"] == 1


def test_plan_twice_identical(tmp_path, gw):
    args = ["plan", "--source", "Test-NB", "--target", "Neu", "--target-folder", str(tmp_path)]
    assert run([*args, "--out", str(tmp_path / "r1")], gw) == cli.OK
    assert run([*args, "--out", str(tmp_path / "r2")], make_gateway()) == cli.OK
    assert (tmp_path / "r1" / "plan.json").read_bytes() == (
        tmp_path / "r2" / "plan.json"
    ).read_bytes()


@pytest.mark.parametrize(
    "extra",
    [
        ["--group", "Nope"],
        ["--group", "2023", "--section", "99-99"],
        ["--section", "23-10"],
        ["--exclude-group", "Nope"],
        ["--group", "2023", "--exclude-group", "Projekte"],
    ],
)
def test_unknown_scope_is_bad_args(tmp_path, gw, extra):
    assert make_plan(tmp_path, gw, *extra)[0] == cli.BAD_ARGS


def test_plan_and_apply_with_excluded_group(tmp_path, gw):
    code, out = make_plan(tmp_path, gw, "--exclude-group", "Projekte")
    assert code == cli.OK
    data = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    assert data["scope"]["exclude"] == ["Projekte"]
    assert [s["name"] for s in data["sections"]] == ["2023"]
    assert "„Projekte“" in (out / "plan.md").read_text(encoding="utf-8")
    assert run(["apply", "--plan", str(out / "plan.json"), "--yes"], gw) == cli.OK
    assert gw.write_calls  # the fingerprint matched: the exclusion survives plan.json


def test_unknown_source(tmp_path, gw):
    assert run(["plan", "--source", "Nope", "--target", "X", "--out", str(tmp_path)], gw) == 2


def test_target_already_open_or_folder_exists(tmp_path, gw):
    assert (
        run(
            [
                "plan",
                "--source",
                "Test-NB",
                "--target",
                "Diary",
                "--target-folder",
                str(tmp_path),
                "--out",
                str(tmp_path / "r"),
            ],
            gw,
        )
        == 3
    )
    (tmp_path / "nb" / "Neu").mkdir(parents=True)
    assert make_plan(tmp_path, gw)[0] == cli.TARGET_EXISTS


def test_target_onedrive_shortcut_exists(tmp_path, gw, capsys):
    # In a OneDrive folder, OneNote creates cloud notebooks and leaves only "<name>.url".
    # A closed cloud notebook with the target name would make create_notebook fail later.
    (tmp_path / "nb").mkdir()
    (tmp_path / "nb" / "Neu.url").write_text("[InternetShortcut]\nURL=https://x\n")
    assert make_plan(tmp_path, gw)[0] == cli.TARGET_EXISTS
    assert "Neu.url" in capsys.readouterr().err
    assert not (tmp_path / "run" / "plan.json").exists()
    assert gw.write_calls == []


def test_apply_refuses_when_shortcut_appeared_after_plan(tmp_path, gw):
    code, out = make_plan(tmp_path, gw)
    assert code == cli.OK
    (tmp_path / "nb").mkdir(exist_ok=True)
    (tmp_path / "nb" / "Neu.url").write_text("[InternetShortcut]\n")
    apply_gw = make_gateway()
    assert run(["apply", "--plan", str(out / "plan.json"), "--yes"], apply_gw) == cli.TARGET_EXISTS
    assert apply_gw.write_calls == []


def test_onenote_unavailable(tmp_path):
    def factory():
        raise OneNoteUnavailable("weg")

    assert cli.main(["plan", "--source", "a", "--target", "b"], gateway_factory=factory) == 4


def test_apply_source_changed(tmp_path, gw):
    _, out = make_plan(tmp_path, gw)
    xml = read_fixture("hierarchy_small.xml").replace(
        "2023-10-04T10:00:00.000Z", "2024-10-04T10:00:00.000Z"
    )
    changed = FakeGateway(xml, all_pages())
    assert run(["apply", "--plan", str(out / "plan.json"), "--yes"], changed) == cli.SOURCE_CHANGED
    assert changed.write_calls == []


def test_apply_declined(tmp_path, gw, monkeypatch):
    _, out = make_plan(tmp_path, gw)
    monkeypatch.setattr("builtins.input", lambda prompt: "nein")
    apply_gw = make_gateway()
    assert run(["apply", "--plan", str(out / "plan.json")], apply_gw) == cli.NOT_CONFIRMED
    assert apply_gw.write_calls == []
    assert not (out / "report.json").exists()


def test_apply_confirmed_runs(tmp_path, gw, monkeypatch):
    _, out = make_plan(tmp_path, gw)
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or "ja")
    apply_gw = make_gateway()
    assert run(["apply", "--plan", str(out / "plan.json")], apply_gw) == cli.OK
    assert prompts == [cli.PROMPT]
    assert apply_gw.write_calls
    assert (out / "report.json").exists() and (out / "report.md").exists()


def test_apply_yes_skips_prompt(tmp_path, gw, monkeypatch):
    _, out = make_plan(tmp_path, gw)
    monkeypatch.setattr("builtins.input", lambda prompt: pytest.fail("prompted"))
    assert run(["apply", "--plan", str(out / "plan.json"), "--yes"], make_gateway()) == cli.OK


def test_apply_with_failures_exit_1_and_report_written(tmp_path, gw):
    _, out = make_plan(tmp_path, gw)
    failing = make_gateway(fail_on={"create_page": 2})
    assert run(["apply", "--plan", str(out / "plan.json"), "--yes"], failing) == cli.ITEMS_FAILED
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["summary"]["failed"] == 1


def test_apply_stopped_run_still_writes_report(tmp_path, gw, monkeypatch):
    monkeypatch.setattr(runner, "BACKOFF", (0.0, 0.0, 0.0))
    _, out = make_plan(tmp_path, gw)
    probe = make_gateway()
    run(["apply", "--plan", str(out / "plan.json"), "--yes"], probe)
    start = next(i for i, c in enumerate(probe.calls) if c[0] == "create_notebook")
    (out / "report.json").unlink()
    stopped = make_gateway(unavailable_after=start + 2)
    code = cli.main(
        ["apply", "--plan", str(out / "plan.json"), "--yes"], gateway_factory=lambda: stopped
    )
    assert code == cli.ITEMS_FAILED
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["stopped"] is True

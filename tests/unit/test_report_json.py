import json

import pytest

from notes_processing.hierarchy import parse_hierarchy
from notes_processing.model import (
    ContentIssue,
    LinkKind,
    LinkOutcome,
    Mismatch,
    PageOutcome,
    PageStatus,
    RunReport,
    Scope,
    Summary,
    VerificationResult,
)
from notes_processing.planner import make_plan
from notes_processing.report import plan_from_json, plan_to_json, report_from_json, report_to_json
from tests.conftest import make_gateway, read_fixture

ALL = Scope()


def full_plan(scope=ALL):
    gw = make_gateway()
    plan, _ = make_plan(
        gw, parse_hierarchy(read_fixture("hierarchy_small.xml")), scope, "Neu", r"C:\Out"
    )
    return plan


def test_plan_round_trip():
    plan = full_plan(Scope.build("2023", "23-10"))
    s = plan_to_json(plan)
    assert plan_from_json(s) == plan
    data = json.loads(s)
    assert data["format_version"] == 1
    assert list(data) == sorted(data)
    assert "Oktober 2023" in s  # ensure_ascii=False keeps umlauts readable
    full = full_plan()
    assert plan_from_json(plan_to_json(full)) == full
    assert "März" not in s


def test_report_round_trip():
    report = RunReport(
        plan_fingerprint="abc",
        started="2026-11-07T10:00:00",
        finished="2026-11-07T10:01:00",
        target_notebook_id="TNB-1",
        pages=(
            PageOutcome("S1", "23-10", "2023", "Oktober 2023", PageStatus.VERIFIED, "", "TP-1"),
        ),
        links=(
            LinkOutcome("P1", "x", "onenote:a", LinkKind.TRANSFERRED_PAGE, "updated", "onenote:b"),
        ),
        content_issues=(ContentIssue("P12", "Ernte", "Garten", "Image", "kaputt"),),
        verification=(
            VerificationResult(
                "TP-1",
                "Oktober 2023",
                "S1",
                False,
                (Mismatch("P1", "04.10.23", "missing", "fehlt: „ä“"),),
            ),
        ),
        summary=Summary(sections=1, pages=1, completed=1),
    )
    assert report_from_json(report_to_json(report)) == report


def test_wrong_version_rejected():
    with pytest.raises(ValueError):
        plan_from_json('{"format_version": 99}')

from notes_processing.model import PageStatus
from tests.unit.runner_helpers import plan_and_run


def statuses(report):
    return {p.title: p.status for p in report.pages}


def test_create_page_failure_marks_failed_and_continues():
    _, _, report, _, _ = plan_and_run(fail_on={"create_page": 2})
    st = statuses(report)
    assert st["November 2023"] == PageStatus.FAILED
    assert st["Oktober 2023"] == PageStatus.VERIFIED
    assert st["Haus"] == PageStatus.VERIFIED and st["Garten"] == PageStatus.VERIFIED
    assert report.summary.failed == 1 and report.summary.completed == 3
    nov = next(p for p in report.pages if p.title == "November 2023")
    assert "CreateNewPage" in nov.message or "create_page" in nov.message
    # the link to the failed page is kept, not rewritten
    lo = next(lo for lo in report.links if lo.text == "2. November")
    assert lo.status == "kept"


def test_update_failure_after_create_is_incomplete():
    _, _, report, _, _ = plan_and_run(fail_on={"update_page": 1})
    st = statuses(report)
    assert st["Oktober 2023"] == PageStatus.INCOMPLETE
    assert report.summary.incomplete == 1
    assert report.summary.completed == 3
    assert not report.stopped


def test_unavailable_retries_then_stops_with_partial_report():
    # In a normal run, find the call that writes the first page; cut OneNote off right after it.
    probe, _, _, _, _ = plan_and_run()
    first_update = next(i for i, c in enumerate(probe.calls) if c[0] == "update_page")
    _, _, report, messages, sleeps = plan_and_run(unavailable_after=first_update + 1)
    assert sleeps == [1.0, 4.0, 16.0]
    assert report.stopped
    st = statuses(report)
    assert PageStatus.NOT_STARTED in st.values()
    assert all(s != PageStatus.VERIFIED for s in st.values())
    assert report.summary.not_started >= 1
    assert any("abgebrochen" in m for m in messages)


def test_unavailable_recovers_after_retry():
    probe_gw, _, _, _, _ = plan_and_run()
    start = next(i for i, c in enumerate(probe_gw.calls) if c[0] == "create_notebook")
    _, _, report, _, sleeps = plan_and_run(unavailable_after=start + 3, unavailable_count=2)
    assert sleeps == [1.0, 4.0]
    assert not report.stopped
    assert report.summary.completed == 4

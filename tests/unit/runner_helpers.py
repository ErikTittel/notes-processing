from notes_processing import runner
from notes_processing.hierarchy import parse_hierarchy
from notes_processing.model import Scope
from notes_processing.onenote.errors import WriteOutsideTarget
from notes_processing.planner import make_plan
from tests.conftest import make_gateway

ALL = Scope()

SOURCE_IDS = {"NB1", "G1", "G2", "S1", "S2", "S3", "S4"} | {f"P{i}" for i in range(1, 13)}


def plan_and_run(scope=ALL, gateway=None, sleep=None, **gw_kwargs):
    gw = gateway or make_gateway(**gw_kwargs)
    source = parse_hierarchy(gw.hierarchy("NB1", 4))
    plan, indexed = make_plan(gw, source, scope, "Neu", r"C:\Out")
    messages: list[str] = []
    sleeps: list[float] = []
    report = runner.run(
        plan, gw, indexed, progress=messages.append, sleep=sleep or sleeps.append, clock=lambda: "T"
    )
    assert_no_source_writes(gw)
    return gw, plan, report, messages, sleeps


def assert_no_source_writes(gw):
    for method, args in gw.write_calls:
        if method == "update_page":
            from notes_processing.onexml import parse

            assert parse(args[0]).get("ID") not in SOURCE_IDS
        elif method == "create_page":
            assert args[0] not in SOURCE_IDS
    # the guard is still in place (probe call is removed from the log again)
    n = len(gw.calls)
    try:
        gw.create_page("S1")
    except WriteOutsideTarget:
        pass
    else:  # pragma: no cover
        raise AssertionError("guard missing")
    del gw.calls[n:]

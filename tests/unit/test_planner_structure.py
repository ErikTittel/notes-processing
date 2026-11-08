import pytest

from notes_processing.hierarchy import parse_hierarchy
from notes_processing.model import Scope, TitleStatus
from notes_processing.onenote.errors import NotFound
from notes_processing.planner import build_plan
from tests.conftest import read_fixture

ALL = Scope()


def small():
    return parse_hierarchy(read_fixture("hierarchy_small.xml"))


def edge():
    return parse_hierarchy(read_fixture("hierarchy_edge.xml"))


def plan_for(nb, scope=ALL):
    return build_plan(nb, scope, "Neu", r"C:\Out")


def test_scope_all_structure():
    plan = plan_for(small())
    assert [s.name for s in plan.sections] == ["2023", "Projekte"]
    assert [s.source_group_id for s in plan.sections] == ["G1", "G2"]
    assert [[p.source_section_id for p in s.pages] for s in plan.sections] == [
        ["S1", "S2"],
        ["S3", "S4"],
    ]
    assert all(p.source_page_count == 3 for p in plan.pages)
    assert [b.page_id for b in plan.pages[0].blocks] == ["P1", "P2", "P3"]


def test_scope_group_and_section():
    plan = plan_for(small(), Scope.build("Projekte", None))
    assert [s.name for s in plan.sections] == ["Projekte"]
    assert len(plan.pages) == 2
    plan = plan_for(small(), Scope.build("2023", "23-11"))
    assert [s.name for s in plan.sections] == ["2023"]
    assert [p.source_section_id for p in plan.pages] == ["S2"]


@pytest.mark.parametrize(("group", "section"), [("Nope", None), ("2023", "23-99")])
def test_unknown_scope_raises(group, section):
    with pytest.raises(NotFound):
        plan_for(small(), Scope.build(group, section))


def test_scope_all_with_excluded_group():
    plan = plan_for(small(), Scope.build(None, None, ("Projekte",)))
    assert [s.name for s in plan.sections] == ["2023"]
    assert {p.source_section_id for p in plan.pages} == {"S1", "S2"}
    assert ("excluded_group", ("Projekte",)) in [(a.kind, a.names) for a in plan.attention]
    assert str(plan.scope) == "all ohne „Projekte“"


def test_excluded_group_must_exist_and_needs_scope_all():
    with pytest.raises(NotFound):
        plan_for(small(), Scope.build(None, None, ("Nope",)))
    with pytest.raises(ValueError):
        Scope.build("2023", None, ("Projekte",))


def test_edge_attention_items():
    plan = plan_for(edge())
    kinds = [(a.kind, a.names) for a in plan.attention]
    assert ("locked", ("A", "X")) in kinds
    assert ("locked", ("B", "B2")) in kinds
    assert ("empty_section", ("A", "Leer")) in kinds
    assert ("duplicate_section", ("A", "Dup")) in kinds
    assert ("duplicate_group", ("A",)) in kinds
    assert ("loose_section", ("Lose",)) in kinds
    assert ("nested_group", ("A", "Innen")) in kinds
    # locked sections skipped, empty section still yields a page with only its name
    pages = [(p.source_section_id, p.title, p.source_page_count) for p in plan.pages]
    assert pages == [
        ("E-Leer", "Leer", 0),
        ("E-Dup1", "Dup", 3),
        ("E-Dup2", "Dup", 1),
        ("E-Z", "Z", 1),
        ("E-B1", "B1", 1),
    ]
    assert [s.name for s in plan.sections] == ["A", "A", "B"]


def test_invariant_every_unlocked_section_once():
    nb = edge()
    plan = plan_for(nb)
    unlocked = [s.id for g in nb.groups for s in g.sections if not s.locked]
    assert sorted(p.source_section_id for p in plan.pages) == sorted(unlocked)
    assert [s.source_group_id for s in plan.sections] == [g.id for g in nb.groups]


def test_untitled_page_block():
    plan = plan_for(edge())
    dup1 = next(p for p in plan.pages if p.source_section_id == "E-Dup1")
    untitled = dup1.blocks[1]
    assert untitled.status == TitleStatus.UNTITLED
    assert untitled.heading == "(Untitled page)"


def test_titles_and_decisions_listed():
    plan = plan_for(small())
    assert [p.title for p in plan.pages] == ["Oktober 2023", "November 2023", "Haus", "Garten"]
    corrected = [(d.original, d.heading, d.status) for d in plan.title_decisions]
    assert ("05.12.23", "05.10.23", TitleStatus.CORRECTED) in corrected
    assert all(d.status != TitleStatus.UNCHANGED for d in plan.title_decisions)

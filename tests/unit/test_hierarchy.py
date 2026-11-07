from notes_processing.hierarchy import notebooks, parse_hierarchy
from tests.conftest import read_fixture


def test_small_notebook_order_and_fields():
    nb = parse_hierarchy(read_fixture("hierarchy_small.xml"))
    assert nb.name == "Test-NB"
    assert [g.name for g in nb.groups] == ["2023", "Projekte"]
    assert [s.name for s in nb.groups[0].sections] == ["23-10", "23-11"]
    assert [p.title for p in nb.groups[0].sections[0].pages] == ["04.10.23", "05.12.23", "07.10.23"]
    p6 = nb.groups[0].sections[1].pages[2]
    assert p6.level == 2
    assert p6.last_modified == "2023-11-02T10:00:00.000Z"
    assert nb.groups[0].sections[0].last_modified == "2023-10-31T10:00:00.000Z"
    assert nb.ignored == ()


def test_edge_cases():
    nb = parse_hierarchy(read_fixture("hierarchy_edge.xml"))
    # recycle bin group excluded
    assert [g.name for g in nb.groups] == ["A", "A", "B"]
    a = nb.groups[0]
    assert [s.name for s in a.sections] == ["X", "Leer", "Dup", "Dup"]
    assert a.sections[0].locked is True
    assert nb.groups[2].sections[1].locked is True  # encrypted
    assert a.sections[1].pages == ()
    # page in recycle bin excluded, untitled page kept, level kept
    assert [(p.id, p.title, p.level) for p in a.sections[2].pages] == [
        ("EP1", "03.01.23", 1),
        ("EP3", "", 1),
        ("EP4", "Sub", 2),
    ]
    assert nb.groups[2].sections[0].pages[0].level == 3
    kinds = {(i.kind, i.name, i.parent) for i in nb.ignored}
    assert kinds == {("loose_section", "Lose", ""), ("nested_group", "Innen", "A")}


def test_notebook_list():
    assert notebooks(read_fixture("hierarchy_small.xml")) == {"Test-NB": "NB1", "Diary": "NB2"}

import pytest

from notes_processing.onenote.errors import (
    OneNoteCallFailed,
    OneNoteUnavailable,
    WriteOutsideTarget,
)
from tests.conftest import make_gateway


def test_writes_into_target_succeed(fake_gateway):
    nb = fake_gateway.create_notebook(r"C:\Out", "Neu")
    sid = fake_gateway.create_section("2023")
    pid = fake_gateway.create_page(sid)
    xml = (
        fake_gateway.page_xml(pid)
        .replace("<![CDATA[]]>", "Titel")
        .replace("<one:T />", "<one:T>Titel</one:T>")
    )
    fake_gateway.update_page(xml)
    assert nb and sid and pid
    assert [c[0] for c in fake_gateway.write_calls] == [
        "create_notebook",
        "create_section",
        "create_page",
        "update_page",
    ]


def test_writes_to_source_are_refused(fake_gateway):
    fake_gateway.create_notebook(r"C:\Out", "Neu")
    with pytest.raises(WriteOutsideTarget):
        fake_gateway.create_page("S1")
    with pytest.raises(WriteOutsideTarget):
        fake_gateway.update_page(fake_gateway.page_xml("P1"))


def test_section_groups_in_target(fake_gateway):
    fake_gateway.create_notebook(r"C:\Out", "Neu")
    gid = fake_gateway.create_section_group("2023")
    sid = fake_gateway.create_section("23-10", gid)
    fake_gateway.create_page(sid)
    from notes_processing.hierarchy import parse_hierarchy

    nb = parse_hierarchy(fake_gateway.hierarchy(fake_gateway.target_notebook_id, 4))
    assert [(g.name, [s.name for s in g.sections]) for g in nb.groups] == [("2023", ["23-10"])]
    with pytest.raises(WriteOutsideTarget):
        fake_gateway.create_section("x", "G1")


def test_section_before_notebook_refused(fake_gateway):
    with pytest.raises(WriteOutsideTarget):
        fake_gateway.create_section("x")


def test_failure_injection():
    gw = make_gateway(fail_on={"create_page": 1})
    gw.create_notebook(r"C:\Out", "Neu")
    sid = gw.create_section("a")
    with pytest.raises(OneNoteCallFailed):
        gw.create_page(sid)
    gw.create_page(sid)  # second call works

    gw2 = make_gateway(unavailable_after=1, unavailable_count=2)
    gw2.notebook_names()
    with pytest.raises(OneNoteUnavailable):
        gw2.notebook_names()
    with pytest.raises(OneNoteUnavailable):
        gw2.notebook_names()
    assert gw2.notebook_names() == ["Test-NB", "Diary"]


def test_link_shapes(fake_gateway):
    assert fake_gateway.link_to("P6") == (
        r"onenote:C:\Notes\Test-NB\2023\23-11.one#02.11.23&section-id={L-S2}&page-id={L-P6}&end"
    )
    assert fake_gateway.link_to("P5", "P5-oe3").endswith("&object-id={L-P5/P5-oe3}&end")
    assert (
        fake_gateway.link_to("S1")
        == r"onenote:C:\Notes\Test-NB\2023\23-10.one#section-id={L-S1}&end"
    )
    assert fake_gateway.link_to("G2") == r"onenote:C:\Notes\Test-NB\Projekte"

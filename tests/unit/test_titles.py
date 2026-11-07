import pytest

from notes_processing.model import SourcePage, TitleStatus
from notes_processing.titles import decide_titles, month_title

MONTHS = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]


@pytest.mark.parametrize("month", range(1, 13))
def test_month_title_all_months(month):
    assert month_title(f"23-{month:02d}") == f"{MONTHS[month - 1]} 2023"


@pytest.mark.parametrize("name", ["Kapitel 3", "2023-01", "23-13", "23-1", "23-00", " 23-01"])
def test_month_title_other_names_unchanged(name):
    assert month_title(name) == name


def pages(*titles):
    return [SourcePage(f"p{i}", t, 1, "") for i, t in enumerate(titles)]


def run(section, *titles):
    decisions = decide_titles(section, pages(*titles))
    for d in decisions:
        if d.status not in (TitleStatus.CORRECTED, TitleStatus.UNTITLED):
            assert d.heading == d.original
        assert d.section_name == section
    return [(d.heading, d.status) for d in decisions]


C, U = TitleStatus.CORRECTED, TitleStatus.UNCHANGED


def test_single_mistyped_between_neighbours():
    assert run("23-01", "24.01.23", "25.11.23", "26.01.23") == [
        ("24.01.23", U),
        ("25.01.23", C),
        ("26.01.23", U),
    ]


def test_exact_gap_run_of_two():
    assert run("23-10", "04.10.23", "05.12.23", "06.12.23", "07.10.23") == [
        ("04.10.23", U),
        ("05.10.23", C),
        ("06.10.23", C),
        ("07.10.23", U),
    ]


def test_wrong_year():
    assert run("23-10", "08.10.23", "09.10.12", "10.10.23")[1] == ("09.10.23", C)


def test_keep_the_day_when_room_for_more():
    assert run("23-01", "24.01.23", "26.11.23", "28.01.23")[1] == ("26.01.23", C)


def test_keep_the_day_not_between_anchors():
    out = run("23-01", "24.01.23", "02.11.23", "28.01.23")
    assert out[1] == ("02.11.23", TitleStatus.COULD_NOT_CORRECT)


def test_keep_the_day_already_used():
    out = run("23-01", "24.01.23", "26.11.23", "26.01.23", "27.01.23", "30.01.23")
    # 26.11.23 sits between 24.01 and 26.01: one free day (25) and a run of one -> exact gap 25
    assert out[1] == ("25.01.23", C)
    out = run("23-01", "20.01.23", "26.11.23", "29.01.23", "26.01.23")
    # 26.01.23 out of order but still "taken"
    assert out[1] == ("26.11.23", TitleStatus.COULD_NOT_CORRECT)


def test_first_and_last_page_keep_the_day():
    assert run("23-01", "02.12.23", "05.01.23", "06.01.23")[0] == ("02.01.23", C)
    assert run("23-01", "05.01.23", "06.01.23", "09.12.23")[2] == ("09.01.23", C)
    assert run("23-01", "07.12.23", "05.01.23")[0] == ("07.12.23", TitleStatus.COULD_NOT_CORRECT)


def test_out_of_order():
    out = run("23-01", "03.01.23", "15.01.23", "04.01.23")
    assert out == [
        ("03.01.23", U),
        ("15.01.23", TitleStatus.OUT_OF_ORDER),
        ("04.01.23", U),
    ]


def test_non_date_and_untitled():
    out = run("23-10", "Jahresausblick", "04.10.23", "", "Zusammenfassung")
    assert out == [
        ("Jahresausblick", U),
        ("04.10.23", U),
        ("(Untitled page)", TitleStatus.UNTITLED),
        ("Zusammenfassung", U),
    ]


def test_majority_month_for_non_coded_section():
    out = run("Herbst", "04.10.23", "05.12.23", "07.10.23", "08.10.23")
    assert out[1] == ("05.10.23", C)


def test_no_section_month():
    out = run("Herbst", "04.10.23", "05.12.23", "Notiz")
    assert out == [
        ("04.10.23", TitleStatus.NO_SECTION_MONTH),
        ("05.12.23", TitleStatus.NO_SECTION_MONTH),
        ("Notiz", U),
    ]


def test_deterministic():
    t = ("04.10.23", "05.12.23", "06.12.23", "07.10.23", "15.10.23", "09.10.23")
    assert run("23-10", *t) == run("23-10", *t)

"""Page titles: FR-004 month names and FR-009a date-title correction (research R6). Pure."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from datetime import date, timedelta

from .model import UNTITLED_HEADING, SourcePage, TitleDecision, TitleStatus

MONTHS = (
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
)
_CODED = re.compile(r"^(\d{2})-(\d{2})$")
_DATE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{2})$")


def coded_month(section_name: str) -> tuple[int, int] | None:
    """(year, month) for a coded month name such as "23-01", else None."""
    m = _CODED.match(section_name)
    if not m or not 1 <= int(m.group(2)) <= 12:
        return None
    return 2000 + int(m.group(1)), int(m.group(2))


def month_title(section_name: str) -> str:
    ym = coded_month(section_name)
    if ym is None:
        return section_name
    return f"{MONTHS[ym[1] - 1]} {ym[0]}"


def parse_date_title(title: str) -> tuple[int, int, int] | None:
    """(day, month, 4-digit year) for a DD.MM.YY title; None if not a date title."""
    m = _DATE.match(title.strip())
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), 2000 + int(m.group(3))
    try:
        date(y, mo, d)
    except ValueError:
        return None
    return d, mo, y


def fmt(d: date) -> str:
    return d.strftime("%d.%m.%y")


def _section_month(section_name: str, dates: list[tuple[int, int, int]]) -> tuple[int, int] | None:
    ym = coded_month(section_name)
    if ym is not None:
        return ym
    counts = Counter((y, mo) for _, mo, y in dates).most_common(2)
    if not counts:
        return None
    if len(counts) > 1 and counts[0][1] == counts[1][1]:
        return None
    if counts[0][1] * 2 <= len(dates):  # not shared by most date titles
        return None
    return counts[0][0]


def _increasing_subsequence(values: list[date]) -> set[int]:
    """Indices of a longest strictly increasing subsequence.

    Ties go to the subsequence ending latest, so a single stray date such as 15.01 between
    03.01 and 04.01 is the one left out.
    """
    n = len(values)
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if values[j] < values[i] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    if not n:
        return set()
    i = max(range(n), key=lambda k: (best[k], k))
    keep = set()
    while i != -1:
        keep.add(i)
        i = prev[i]
    return keep


def decide_titles(section_name: str, pages: Sequence[SourcePage]) -> list[TitleDecision]:
    titles = [p.title for p in pages]
    parsed = [parse_date_title(t) for t in titles]
    status: dict[int, TitleStatus] = {}
    heading: dict[int, str] = {}

    date_idx = [i for i, p in enumerate(parsed) if p is not None]
    month = _section_month(section_name, [parsed[i] for i in date_idx])  # type: ignore[misc]

    if month is None:
        for i in date_idx:
            status[i] = TitleStatus.NO_SECTION_MONTH
    else:
        year, mon = month
        correct = [i for i in date_idx if (parsed[i][2], parsed[i][1]) == (year, mon)]  # type: ignore[index]
        as_date = {i: date(parsed[i][2], parsed[i][1], parsed[i][0]) for i in date_idx}  # type: ignore[index]

        keep = _increasing_subsequence([as_date[i] for i in correct])
        in_order = [i for k, i in enumerate(correct) if k in keep]
        for k, i in enumerate(correct):
            if k not in keep:
                status[i] = TitleStatus.OUT_OF_ORDER
        used = {as_date[i] for i in correct}

        # Sequence for runs: in-order correct titles and mistyped titles, in page order.
        mistyped = set(date_idx) - set(correct)
        seq = [i for i in date_idx if i in mistyped or i in in_order]
        k = 0
        while k < len(seq):
            if seq[k] not in mistyped:
                k += 1
                continue
            start = k
            while k < len(seq) and seq[k] in mistyped:
                k += 1
            run = seq[start:k]
            lo = as_date[seq[start - 1]] if start > 0 else None
            hi = as_date[seq[k]] if k < len(seq) else None
            _correct_run(run, lo, hi, year, mon, parsed, used, status, heading)

    out = []
    for i, page in enumerate(pages):
        if not page.title.strip():
            st, head = TitleStatus.UNTITLED, UNTITLED_HEADING
        else:
            st = status.get(i, TitleStatus.UNCHANGED)
            head = heading.get(i, page.title) if st == TitleStatus.CORRECTED else page.title
        out.append(TitleDecision(page.id, page.title, head, st, section_name))
    return out


def _correct_run(run, lo, hi, year, mon, parsed, used, status, heading) -> None:
    # Exact gap: both anchors exist and the free days between them match the run length.
    if lo is not None and hi is not None:
        free = []
        d = lo + timedelta(days=1)
        while d < hi:
            if d not in used:
                free.append(d)
            d += timedelta(days=1)
        if len(free) == len(run):
            for i, d in zip(run, free, strict=True):
                status[i], heading[i] = TitleStatus.CORRECTED, fmt(d)
                used.add(d)
            return
    # Otherwise keep the day with the section's month and year, if it fits strictly between.
    lower = lo
    for i in run:
        day = parsed[i][0]
        try:
            cand = date(year, mon, day)
        except ValueError:
            cand = None
        ok = (
            cand is not None
            and (lower is None or cand > lower)
            and (hi is None or cand < hi)
            and cand not in used
        )
        if ok:
            status[i], heading[i] = TitleStatus.CORRECTED, fmt(cand)
            used.add(cand)
            lower = cand
        else:
            status[i] = TitleStatus.COULD_NOT_CORRECT

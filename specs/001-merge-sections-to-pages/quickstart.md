# Quickstart: Validate "Merge Sections into Pages"

These scenarios show end to end that the feature works. Use them after implementation, first on `OneNote-Test`, and only then on the real notebook. Command details: [contracts/cli.md](contracts/cli.md). Data formats: [data-model.md](data-model.md).

## Prerequisites

- Windows with the OneNote desktop app (Microsoft 365), running and signed in. The source notebook must be open and fully synced.
- uv installed (`uv --version`).
- In the repository: `uv sync`. This installs Python 3.14, comtypes, pytest and ruff from `uv.lock`.

## 1. Automated tests (no OneNote needed)

```powershell
uv run pytest -m "not onenote"
```

Expected: all tests pass. They cover:
- the date-title correction, including every example from the spec;
- month names ("23-01" becomes "Januar 2023");
- link classification;
- the block layout, including the two-column "Zusammenfassung" case;
- plan determinism;
- text verification.

## 2. Integration tests (needs OneNote)

```powershell
uv run pytest -m onenote
```

Expected: the tests create a throwaway notebook `np-it-<timestamp>` in a temporary folder, run a small merge (2 groups × 2 sections × 3 pages, with an image, an embedded file, side-by-side outlines and internal links), check the result, and print the notebook's path so you can close it. The test notebook is never deleted automatically (constitution III).

## 3. Plan only, then decline (User Story 2)

```powershell
uv run notes-processing plan --source "OneNote-Test" --target "OneNote-Test neu"
uv run notes-processing apply --plan runs\<id>\plan.json    # answer "nein"
```

Expected:
- `plan.md` lists group "2023" becoming section "2023", and 12 pages from "Januar 2023" to "Dezember 2023" with their page counts (33 for January).
- The title corrections include `23-01: 25.11.23 → 25.01.23`, `23-10: 05.12.23 → 05.10.23`, `06.12.23 → 06.10.23` and `09.10.12 → 09.10.23`.
- After answering "nein", the exit code is 6 and no notebook "OneNote-Test neu" exists.
- Running `plan` a second time gives an identical `plan.json`, apart from the run folder name.

## 4. One section first (User Story 1)

```powershell
uv run notes-processing plan --source "OneNote-Test" --target "OneNote-Test S1" --group 2023 --section 23-10
uv run notes-processing apply --plan runs\<id>\plan.json    # answer "ja"
```

Expected in OneNote, notebook "OneNote-Test S1", section "2023", page "Oktober 2023":
- headings 01.10.23 … 31.10.23 and "Zusammenfassung", in source order, with the corrected dates;
- the "Zusammenfassung" block keeps its two columns (privat and Arbeit on the left; Bücher, Sport und Gesundheit and "was ich gelernt habe" on the right), with nothing overlapping the block above or below;
- `report.md` reports 1 page verified, and links to other sections are listed as "points to content outside the transfer".

## 5. Whole test notebook (User Stories 3 and 4)

```powershell
uv run notes-processing plan --source "OneNote-Test" --target "OneNote-Test komplett"
uv run notes-processing apply --plan runs\<id>\plan.json
uv run notes-processing verify --report runs\<id>\report.json
```

Expected:
- 1 section and 12 pages; `report.md` reports 0 failed and every page verified;
- a link from one month to another opens the matching heading in the new notebook;
- `verify` exits with 0;
- the source notebook "OneNote-Test" is unchanged (its `lastModifiedTime` values are the same as before).

## 6. Stopped run (User Story 3, scenario 2)

During step 5, close OneNote while the run is in progress. Expected: after 3 retries the run stops, `report.md` lists completed, incomplete and not-started pages, the exit code is 1, and the source is unchanged.

## 7. Real notebook

Repeat steps 3 and 5 with the real notebook's name. Before confirming, check `plan.md`: look at the title corrections, the "could not be corrected" and "out of order" lists, and the attention items. Expected run time: under 2 hours (SC-005).

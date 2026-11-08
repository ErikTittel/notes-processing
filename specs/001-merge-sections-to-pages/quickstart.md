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

Use a new target name for every repeat, for example "OneNote-Test komplett 2". In the default OneDrive folder, every earlier run leaves a cloud notebook with its name, even after it is closed in OneNote, and `plan` refuses a name that is already taken (exit code 3, [research R8](research.md)).

Expected:
- 1 section and 12 pages; `report.md` reports 0 failed and every page verified;
- a link from one month to another opens the matching heading in the new notebook;
- `verify` exits with 0;
- the source notebook "OneNote-Test" is unchanged (its `lastModifiedTime` values are the same as before).

## 6. Stopped run (User Story 3, scenario 2)

During step 5, close OneNote while the run is in progress. Expected: after 3 retries the run stops, `report.md` lists completed, incomplete and not-started pages, the exit code is 1, and the source is unchanged.

## 7. Real notebook

Repeat steps 3 and 5 with the real notebook's name. To leave a section group out, add `--exclude-group "ab 2024"` to `plan`; `apply` takes the exclusion from `plan.json`. After the run, re-embed each video listed as `video_preview` in the plan ("Video" in the report): paste its address on the new page in OneNote, then delete the preview picture. Before confirming, check `plan.md`: look at the title corrections, the "could not be corrected" and "out of order" lists, and the attention items. Expected run time: under 2 hours (SC-005).

## Validation log

### 2026-11-08: `OneNote-Test` (T056)

Run folders are in `runs/` (git-ignored, because they contain note titles).

| Step | Run | Result |
|------|-----|--------|
| 1. Automated tests | – | 160 unit tests pass (`uv run pytest -m "not onenote"`); the 3 OneNote integration tests pass too (`-m onenote`). |
| 2. Plan, decline | `20261108-070812` | Plan written (`plan.json`, `plan.md`), not confirmed, so there is no report. |
| 3./4. One section (23-10, October with "Zusammenfassung") | `20261108-075220` | 1 of 1 page verified. Checked by eye: the "Zusammenfassung" block keeps its two columns, and nothing overlaps. |
| 5. Whole test notebook | `20261108-075631` | 1 section, 12 pages from 378 source pages. Run time: 23 s (07:58:09–07:58:32). 6 pages verified and 6 with differences, see below. After the first fix, `verify` reports 11 of 12 pages without differences. |
| 5. Re-check July after the second fix | `20261108-082003` (before), `20261108-083554` (after) | "Juli 2023" (32 source pages): with differences before, verified after (run time 13 s). |
| 5. Whole test notebook, final code | `20261108-092050` | Target "OneNote-Test komplett 3": 1 section, 12 pages from 378 source pages, all 12 verified, 0 failed. `verify` reports 12 of 12 pages without differences. Run time: 26 s (09:21:24–09:21:50). All 8 links point into other notebooks (Literatur, Arbeit, Exocortex) and were kept unchanged, as required. OneNote-Test has no links between its own months, so re-pointing links is covered by the integration test `test_full_run.py` only. |
| 6. Stopped run | – | No run folder documents a stopped run. Stopping and retrying are covered by unit tests (`tests/unit/test_runner_failures.py`) only. |

**Differences found in step 5, and how they were resolved** (spec clarification session 2026-11-08):

1. **Whitespace at the end of a paragraph (13 cases).** OneNote removes it whenever a page is saved. It is not visible, so verification no longer compares it (FR-011).
2. **A space inserted before a web link (1 case, "Juli 2023": `mima-co (https://mimaco.de/)`).** OneNote's automatic link detection inserts the space when a link's text is its own web address and the link follows a character other than a space. Pass 2 rewrites outlines that contain OneNote links, so it triggered the same effect again. Fix: such links are written as plain text wherever OneNote was tested to recreate the identical link, in pass 1 and pass 2. Verification now also compares web link addresses (FR-007, FR-011). The first suspected cause, a line break inside the `<a>` tag, turned out to be wrong.

The whole-notebook run (step 5) was repeated with the final code on 2026-11-08 (`20261108-092050`), without differences. Repeats need a new target name each time, because every earlier run leaves a OneDrive cloud notebook with its name (research R8). The source notebook's `lastModifiedTime` values were not compared by hand in these runs; the integration test `test_full_run.py` checks that the source stays unchanged.

### 2026-11-08: `Diary`, real notebook (T057, step 7)

| Step | Run | Result |
|------|-----|--------|
| 7. Real notebook without "ab 2024" | `20261108-113009` | Plan reviewed with the user, then confirmed with `ja`. Target "Diary neu": 16 sections, 186 pages from 5826 source pages, 0 failed, 0 incomplete. Run time: 21 min 26 s (11:41:59–12:03:25), well under SC-005. 154 pages verified, 32 with differences. 14 video previews reported and linked (FR-008a). The user checked the differences and accepted the run. |

**Differences in step 7** (95 in total on 32 pages, all reviewed by the user, nothing visible is lost):

1. **Whitespace at the start of a paragraph (49 cases).** OneNote removed a leading space when it saved the merged page, for example „ alte Klausuren“ → „alte Klausuren“. Only whitespace differs in every case.
2. **A source page title ending in a space (46 differences, one page).** The title "14.03.15 " in section 15-03 ends in a space. OneNote removes it from the heading on the merged page, so verification doesn't find the heading „14.03.15 “. It reports the heading as missing, its 22 paragraphs as missing, and the same paragraphs as extra on the previous page "13.03.15". The content is on the merged page in the right place. Fixed in T062: headings are now matched without trailing whitespace. This matching is also used by pass 2 to find a heading as a link target. `verify` on a copy of the run folder then reported 155 of 186 pages without differences; only the 49 whitespace cases from item 1 remain.

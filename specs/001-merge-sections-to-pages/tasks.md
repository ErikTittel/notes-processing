---

description: "Task list for Merge Sections into Pages"
---

# Tasks: Merge Sections into Pages

**Input**: Design documents from `specs/001-merge-sections-to-pages/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/cli.md](contracts/cli.md), [quickstart.md](quickstart.md)

**Tests**: Included. Constitution principle V requires focused tests for every behavior and COM integration tests where behavior depends on OneNote. Unit tests use synthetic fixtures and `FakeGateway` only (never real notebooks). Integration tests are marked `@pytest.mark.onenote`.

**Organization**: Tasks are grouped by user story. US1 and US2 are both P1 and together form the MVP: US1 builds the merge engine, US2 puts the plan-and-confirm gate in front of it. US1 is implemented first so US2 has something to gate, but US1 is only driven from tests (never from the CLI) until US2 is done.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US4)

## Path Conventions

Single project, `src/` layout: code in `src/notes_processing/`, tests in `tests/` at the repository root (see plan.md → Project Structure).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization (none of this exists yet; the repo only has `.specify/`, `.claude/`, `specs/`)

- [X] T001 Create `pyproject.toml` at the repo root: uv project `notes-processing`, `requires-python = ">=3.14,<3.15"`, src layout (`src/notes_processing`), runtime dependency `comtypes` (only third-party runtime dependency, research R1), dev dependency group with `pytest` and `ruff`, console script `notes-processing = "notes_processing.cli:main"`, `[tool.pytest.ini_options]` with `testpaths = ["tests"]` and marker `onenote: needs the OneNote desktop app and creates a throwaway notebook`, `[tool.ruff]` with `line-length = 100` and `target-version = "py314"`
- [X] T002 Create `.python-version` containing `3.14` at the repo root (research R2)
- [X] T003 [P] Create `.gitignore` at the repo root ignoring `runs/`, `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/` (runs contain note titles and link text, plan.md → Structure Decision)
- [X] T004 [P] Create empty package and test skeleton: `src/notes_processing/__init__.py`, `src/notes_processing/onenote/__init__.py`, `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/fixtures/` (with a `.gitkeep`)
- [X] T005 Run `uv sync` to install Python 3.14, comtypes, pytest, ruff and generate `uv.lock`; confirm `uv run pytest` and `uv run ruff check` both run cleanly on the empty project

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Data model, the COM gateway boundary with its fake, hierarchy parsing, a structural planner and the CLI skeleton. Every user story depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T006 Implement all dataclasses from data-model.md as `@dataclass(frozen=True)` in `src/notes_processing/model.py`: `SourceNotebook` (`id`, `name`, `path`, `groups`, `ignored`), `SourceGroup` (`id`, `name`, `path`, `sections`), `SourceSection` (`id`, `name`, `path`, `last_modified`, `locked: bool` — "`locked` or `encrypted` attribute, meaning the section is skipped", `link_section_guid: str | None`, `pages`), `SourcePage` (`id`, `title` — "may be empty, in which case the heading is \"(Untitled page)\"", `level: int` — "1–3 (`pageLevel`), giving heading h1–h3", `last_modified`, `link_page_guid: str | None`), `IgnoredItem`, `AttentionItem` (kind + message + source names), `Scope` (`all` / `group:<name>` / `section:<group>/<name>`), `TitleDecision` (`page_id`, `original`, `heading`, `status`), `LinkRef` (`source_page_id`, `text`, `href`, `kind`, `target_source_id: str | None`), `PlannedPage`, `PlannedSection`, `Plan` (incl. `fingerprint`), `PageOutcome`, `LinkOutcome`, `ContentIssue`, `VerificationResult`, `RunReport`. Enums (`StrEnum`): `TitleStatus` = `unchanged`, `corrected`, `could_not_correct`, `out_of_order`, `untitled`, `no_section_month`; `LinkKind` = `transferred_page`, `transferred_paragraph`, `transferred_section`, `transferred_group`, `outside_transfer`, `target_not_found`, `external`; `PageStatus` = `planned`, `created`, `content_written`, `links_updated`, `verified`, `failed`, `incomplete`, `verification_failed`, `skipped`, `not_started`. Use tuples, not lists, for collection fields so instances stay hashable and immutable
- [X] T007 [P] Define typed COM exceptions in `src/notes_processing/onenote/errors.py`: `OneNoteError` (base), `OneNoteUnavailable` (OneNote not running / not responding), `OneNoteCallFailed` (any other COM failure, carries HRESULT and method name), `WriteOutsideTarget` (write to an ID not inside the target notebook), `NotFound` (notebook/group/section name not found). No `comtypes` import in this module
- [X] T008 Implement `OneNoteGateway` in `src/notes_processing/onenote/gateway.py` — the ONLY module that imports `comtypes`, and it does so inside `__init__` (lazy) so tests never load it. Load type library GUID `{0EA692EE-BB50-4E3C-AEF0-356D91732725}` v1.1 and create `OneNote.Application` as `IApplication` (research R1). Read methods: `hierarchy(start_id: str, scope: int) -> str` (`GetHierarchy`, xs2013=2; `hsNotebooks=2`, `hsPages=4`), `page_xml(page_id) -> str` (`GetPageContent` with `piBinaryDataFileType=5`, xs2013=2, research R3), `link_to(hierarchy_id, object_id="") -> str` (`GetHyperlinkToObject`), `special_folder() -> str` (`GetSpecialLocation(2)`), `notebook_names() -> list[str]`. Write methods: `create_notebook(folder, name) -> str` (`OpenHierarchy(path, "", cftNotebook=1)`, records the target notebook ID), `create_section(name) -> str` (`OpenHierarchy("<name>.one", notebookId, cftSection=3)`), `create_page(section_id) -> str` (`CreateNewPage(section_id, 1)`), `update_page(xml)` (`UpdatePageContent(xml, 0, 2, False)`). Every write method first checks the ID belongs to the target notebook recorded by `create_notebook` (look up parent chain via `GetHierarchyParent` or the IDs this gateway itself created) and raises `WriteOutsideTarget` otherwise. Map `COMError` HRESULTs `0x8001010A` (RPC_E_SERVERCALL_RETRYLATER), `0x80010108` (RPC_E_DISCONNECTED), `0x800706BA` / `0x800706BE` (RPC server unavailable / call failed) to `OneNoteUnavailable`, everything else to `OneNoteCallFailed`
- [X] T009 [P] Implement `FakeGateway` in `src/notes_processing/onenote/fake.py` with exactly the same method signatures as `OneNoteGateway`, backed by in-memory XML: constructor takes a hierarchy XML string and a `{page_id: page_xml}` dict; `link_to` returns deterministic `onenote:` URLs of the form `onenote:<path>#<title>&section-id={G}&page-id={G}[&object-id={G}]&end` (research R7) with GUIDs derived from the IDs; write methods create target objects with new IDs, assign `objectID`s to every `one:OE` on `update_page` (as OneNote would), enforce the same `WriteOutsideTarget` guard, and record every call in `self.calls` for assertions; supports failure injection (`fail_on={"update_page": n}` raising `OneNoteCallFailed`, `unavailable_after=n` raising `OneNoteUnavailable`)
- [X] T010 [P] Create synthetic fixtures (no real notes) in `tests/fixtures/`: `hierarchy_small.xml` (OneNote 2013 namespace `http://schemas.microsoft.com/office/onenote/2013/onenote`; notebook "Test-NB" with groups "2023" and "Projekte", each 2 sections × 3 pages; plus a recycle-bin group (`isRecycleBin="true"`), a page with `isInRecycleBin="true"`, a loose section outside any group, a nested group inside "Projekte", a section with `locked="true"`, an empty section, a subpage with `pageLevel="2"`, an untitled page, and duplicate section names in one group); `pages/*.xml` page-content fixtures covering: plain text, bold/list/table formatting, an image with `one:Data`, an `one:InsertedFile` and `one:MediaFile` with `pathCache`, two outlines side by side (Zusammenfassung case with 5 outlines in two columns, heights 40–134 pt), title-only page, and pages with an internal page link, a paragraph link (`object-id`), a section link, a section-group link (folder path), a link into notebook "Diary", a dead `onenote:` link into the source notebook, `https://`, `C:\…`, `\\server\share\…` and `mailto:` links
- [X] T011 [P] Write `tests/conftest.py` with fixtures `load_fixture(name) -> str` and `fake_gateway()` (FakeGateway built from `hierarchy_small.xml` + all `pages/*.xml`)
- [X] T012 Write tests for hierarchy parsing in `tests/unit/test_hierarchy.py`: groups/sections/pages in document order; recycle bin group and `isInRecycleBin` pages excluded; locked/encrypted section → `locked=True`; loose section and nested group → `ignored`; `pageLevel` → `level`; `lastModifiedTime` captured
- [X] T013 Implement `parse_hierarchy(xml: str) -> SourceNotebook` in `src/notes_processing/hierarchy.py` using `xml.etree.ElementTree` with the 2013 namespace (research R12); make T012 pass
- [X] T014 [P] Write tests for the gateway guard in `tests/unit/test_fake_gateway.py`: writes into the target notebook succeed; `update_page`/`create_page` on a source-notebook ID raise `WriteOutsideTarget`; `create_section` before `create_notebook` raises; failure injection works
- [X] T015 Write tests for the structural planner in `tests/unit/test_planner_structure.py`: scope `all` → one `PlannedSection` per group (name == group name, FR-005) with one `PlannedPage` per non-locked section in original order and correct `source_page_count`; scope `group:Projekte` and `section:2023/<name>` restrict output; unknown group/section raises `NotFound`; attention items for locked section (skipped), empty section ("flagged"; still produces a page with only its name), duplicate section and group names, loose sections and nested groups ("left alone"). Invariant: "Each source section that isn't locked appears exactly once as a `PlannedPage`. Each group in scope appears exactly once as a `PlannedSection`."
- [X] T016 Implement `build_plan(source: SourceNotebook, scope: Scope, target_name: str, target_folder: str) -> Plan` in `src/notes_processing/planner.py` covering structure, scope and attention items only; page titles = section name and every block a `TitleDecision` with status `unchanged` (or `untitled` with heading `(Untitled page)` for empty titles) for now — titles, links and fingerprint are added by later stories; make T015 pass
- [X] T017 [P] Implement JSON (de)serialisation in `src/notes_processing/report.py`: `plan_to_json(plan) -> str`, `plan_from_json(s) -> Plan`, `report_to_json(report) -> str`, `report_from_json(s) -> RunReport`; UTF-8, `sort_keys=True`, `indent=2`, `ensure_ascii=False`, top-level `"format_version": 1` (contracts/cli.md → File formats); lists keep OneNote order. Round-trip tests in `tests/unit/test_report_json.py`
- [X] T018 Create the CLI skeleton in `src/notes_processing/cli.py`: `argparse` subcommands exactly as in contracts/cli.md (`plan --source --target [--group [--section]] [--target-folder] [--out]`, `apply --plan [--yes]`, `verify --report`), `--section` without `--group` is an argument error (exit 2), exit-code constants `OK=0, ITEMS_FAILED=1, BAD_ARGS=2, TARGET_EXISTS=3, ONENOTE_UNAVAILABLE=4, SOURCE_CHANGED=5, NOT_CONFIRMED=6`, `main(argv=None, gateway_factory=OneNoteGateway) -> int` so tests can inject `FakeGateway`; any `OneNoteUnavailable` → German message + exit 4. Subcommand bodies are stubs filled in by the user stories. All user-facing messages in German

**Checkpoint**: `uv run pytest` passes; the source notebook can be read into a model and a structural plan built against `FakeGateway`.

---

## Phase 3: User Story 1 - Merge one section into one page (Priority: P1) 🎯 MVP part 1

**Goal**: For one section, build a single merged page in a new target notebook: page title from FR-004, each former page as an h1–h3 heading (corrected per FR-009a) followed by its unchanged content with side-by-side layout preserved, non-text content carried over or reported, and links re-pointed per FR-009b.

**Independent Test**: With `FakeGateway`, run the runner on scope `section:2023/23-10` and assert the target page XML: headings in order, all text unchanged, two-column block preserved without overlap, image/file present, links rewritten. Integration test does the same against a throwaway OneNote notebook.

### Tests for User Story 1 ⚠️ write first, ensure they fail

- [X] T019 [P] [US1] Month-title tests in `tests/unit/test_titles.py`: `"23-01"→"Januar 2023"`, `"23-02"→"Februar 2023"`, `"23-03"→"März 2023"` … `"23-12"→"Dezember 2023"` (all 12, two-digit year means 20YY); non-matching names (`"Kapitel 3"`, `"2023-01"`, `"23-13"`, `"23-1"`) returned unchanged (FR-004)
- [X] T020 [P] [US1] Date-correction tests in `tests/unit/test_titles.py` covering every spec/research example: `25.11.23` between `24.01.23` and `26.01.23` in section `23-01` → `25.01.23` (`corrected`); `05.12.23`, `06.12.23` between `04.10.23` and `07.10.23` in `23-10` → `05.10.23`, `06.10.23` (exact gap); `09.10.12` between `08.10.23` and `10.10.23` → `09.10.23`; mistyped title between `24.01.23` and `28.01.23` keeps its day if it lies strictly between and is unused, otherwise `could_not_correct`; mistyped title on the first or last date page of a section uses the keep-the-day rule; `15.01.23` between `03.01.23` and `04.01.23` → `out_of_order`, heading unchanged; non-date titles (`Jahresausblick`, `Zusammenfassung`) `unchanged`; empty title → `untitled` with heading `(Untitled page)`; section with non-coded name uses the majority month; no coded name and no majority → every date title `no_section_month`, unchanged. Assert `heading == original` for every status except `corrected` and `untitled`
- [X] T021 [P] [US1] Layout tests in `tests/unit/test_layout.py`: first block starts below the page title; heading at x = 36; each element keeps x and gets `y = block top + heading height + (y − min_y)`; next block top = previous block bottom + 36 pt; the 5-outline two-column Zusammenfassung fixture keeps relative positions; overlap check flags any bounding box of one block intersecting a box of another block
- [X] T022 [P] [US1] Link tests in `tests/unit/test_links.py`: parse `onenote:` hrefs into section path, title, `section-id`, `page-id`, optional `object-id`; section-group folder-path links; classification against a link index into `transferred_page`, `transferred_paragraph`, `transferred_section`, `transferred_group`, `outside_transfer` (notebook "Diary", or source content outside the run's scope), `target_not_found` (source-notebook `onenote:` link whose GUIDs are not in the index), `external` (`https://`, `C:\…`, `\\server\share\…`, `mailto:`); `rewrite_hrefs(xml, mapping)` changes only the `href` and never the link text
- [X] T023 [P] [US1] Page-builder tests in `tests/unit/test_pagebuilder.py`: all `objectID` attributes removed from copied content; `quickStyleIndex` re-mapped to the target page's `QuickStyleDef` list merged by style name; one heading outline per former page using built-in `h1`/`h2`/`h3` for `pageLevel` 1/2/3; title-only source page → heading with nothing beneath; text, bold, lists and tables byte-identical inside `one:T`; `one:Image`/`one:InkDrawing` copied with their `one:Data`; `one:InsertedFile`/`one:MediaFile` get `pathSource` = source `pathCache`; an element that can't be copied produces a `ContentIssue` naming the source page and is never silently dropped (FR-008); target page title set from `PlannedPage.title`
- [X] T024 [P] [US1] Runner tests for one section in `tests/unit/test_runner_merge.py` using `FakeGateway`: creates notebook → section named after the group → one page; pass 1 writes content with links unchanged; read-back pairs source OEs to target OEs and former pages to heading OEs in document order; pass 2 rewrites a page link to the heading OE, a paragraph link to the matching OE, a section link to the merged page, a group link to the new section (via `link_to`); `outside_transfer`/`target_not_found`/external links unchanged; `RunReport.links` lists updated and kept links; no write call ever targets a source ID (acceptance scenarios 1–7)

### Implementation for User Story 1

- [X] T025 [P] [US1] Implement `month_title(section_name: str) -> str` (regex `^(\d{2})-(\d{2})$`, month 01–12, German names Januar…Dezember, year `20YY`) in `src/notes_processing/titles.py`; make T019 pass
- [X] T026 [US1] Implement `decide_titles(section_name: str, pages: Sequence[SourcePage]) -> list[TitleDecision]` in `src/notes_processing/titles.py` following research R6 exactly: parse `^\d{2}\.\d{2}\.\d{2}$`; section month from `YY-MM` name else majority month of date titles else `no_section_month`; mistyped = month or year differs; group consecutive mistyped titles into runs anchored by nearest correct dates; exact-gap fill; otherwise keep-the-day only if strictly between anchors and not already used, else `could_not_correct`; correct title not later than previous date → `out_of_order`; never use page creation date; output format `DD.MM.YY`; make T020 pass
- [X] T027 [P] [US1] Implement `layout_blocks(blocks: Sequence[BlockInput], title_bottom: float, heading_height: float, gap: float = 36.0) -> list[BlockPlacement]` and `find_overlaps(placements) -> list[...]` as pure functions in `src/notes_processing/layout.py` (data-model.md → Block layout, research R4); add a small safety margin to each block's bottom; make T021 pass
- [X] T028 [P] [US1] Implement in `src/notes_processing/links.py`: `parse_onenote_href(href) -> ParsedLink | None`, `LinkIndex` (maps `(section-id, page-id) → source page`, `section-id → source section`, group folder path → source group; built from `SourceNotebook` + scope), `classify(href, index, source_notebook_path) -> LinkKind`, `extract_links(page_xml) -> list[(text, href)]` (anchors inside `one:T` CDATA HTML), `rewrite_hrefs(page_xml, {old_href: new_href}) -> str`; make T022 pass
- [X] T029 [US1] Implement `build_target_page(planned: PlannedPage, source_pages: list[(SourcePage, TitleDecision, str page_xml)], target_page_skeleton: str) -> (str xml, list[ContentIssue])` in `src/notes_processing/pagebuilder.py`: strip `objectID`, merge/re-map `QuickStyleDef`s by name, add h1–h3 heading outlines, place all top-level `Outline`/`Image`/`InkDrawing`/`InsertedFile`/`MediaFile` elements using `layout.layout_blocks`, set `pathSource` from `pathCache`, emit `ContentIssue` for anything not expressible (research R3); fail with an error if `find_overlaps` reports any overlap; make T023 pass
- [X] T030 [US1] Extend `build_plan` in `src/notes_processing/planner.py`: `PlannedPage.title = month_title(section.name)`, `PlannedPage.blocks = decide_titles(...)`, `Plan.title_decisions` = flattened non-`unchanged` decisions; add `index_links(gateway, source, scope) -> SourceNotebook` that fills `link_section_guid`/`link_page_guid` via `gateway.link_to` for every section and page in scope (research R7 step 1); scan in-scope page XML for links and fill `Plan.links` with every `LinkRef` except `external`; add attention items for non-text content found while scanning. Extend `tests/unit/test_planner_structure.py` accordingly
- [X] T031 [US1] Implement the merge part of `src/notes_processing/runner.py`: `run(plan: Plan, gateway, source: SourceNotebook, progress=print) -> RunReport`; create the target notebook in `plan.target_folder`, then per `PlannedSection` create the section, per `PlannedPage` load source page XML, `create_page`, `build_target_page`, `update_page`, read back once and record the source-OE → target-OE and source-page → heading-OE pairing (pass 1, research R7 step 3); after all pages exist, resolve each `transferred_*` link via `gateway.link_to` on the new object (paragraph targets resolved lazily only for pages targeted by paragraph links, research R7 step 5) and issue one `update_page` per affected page with `rewrite_hrefs` (pass 2); record `PageOutcome` states `created → content_written → links_updated`, `LinkOutcome` (`updated` with new href or `kept` with reason) and `ContentIssue`s in the `RunReport`; make T024 pass
- [X] T032 [US1] Integration test in `tests/integration/test_merge_section.py` (`@pytest.mark.onenote`) with a `conftest.py` fixture that creates a throwaway notebook `np-it-<timestamp>` in a temp folder via the real `OneNoteGateway`, fills one group × one section × 3 pages (formatted text, an image, an embedded file, an audio file, two side-by-side outlines, a page link and a web link), runs `build_plan` + `runner.run`, and asserts the merged page via `page_xml`. Also confirms research R3's open point: embedded files and audio copy correctly through `pathCache`. Print the notebook paths at the end and never delete them (constitution III)

**Checkpoint**: The merge engine produces a correct merged page for one section against both the fake and a real throwaway notebook. It is not yet reachable from the CLI.

---

## Phase 4: User Story 2 - Preview and confirm before changing anything (Priority: P1) 🎯 MVP part 2

**Goal**: `plan` writes a deterministic, fingerprinted `plan.json` + German `plan.md` without writing to OneNote; `apply` refuses to change anything unless the plan is unchanged and the user types `ja`.

**Independent Test**: Run `plan` on the fake notebook twice → identical `plan.json`; run `apply` and answer `nein` → exit 6 and `FakeGateway.calls` contains no write method.

### Tests for User Story 2 ⚠️ write first, ensure they fail

- [X] T033 [P] [US2] Determinism tests in `tests/unit/test_planner_determinism.py`: building the plan twice from the same fixture gives byte-identical `plan_to_json` output (FR-014); changing any source `last_modified` changes the fingerprint; fingerprint is SHA-256 hex of the canonical JSON of all `Plan` fields except `fingerprint` plus source `last_modified` values
- [X] T034 [P] [US2] CLI tests in `tests/unit/test_cli_plan_apply.py` with an injected `FakeGateway` and `tmp_path`: `plan` writes `plan.json` + `plan.md` to `--out` and returns 0 with no write calls; unknown source/group/section → 2; target notebook name already open or target folder already exists → 3; `OneNoteUnavailable` → 4; `apply` with modified source → 5 and no writes; `apply` answering `nein` (monkeypatched `input`) → 6 and no writes; answering `ja` → runner invoked; `--yes` skips the prompt
- [X] T035 [P] [US2] Plan Markdown tests in `tests/unit/test_report_plan_md.py`: `plan.md` contains the sections Übersicht (counts), Struktur (group → section, section → page with source page counts), Titelkorrekturen (section, original, new title, and the "could not be corrected"/"out of order" lists), Links (page, link text, original target; updated vs. "points to content outside the transfer" vs. "target not found"), Hinweise (attention items)

### Implementation for User Story 2

- [X] T036 [US2] Add `fingerprint(plan, source) -> str` and set `Plan.fingerprint` in `build_plan` in `src/notes_processing/planner.py` (research R10); make T033 pass
- [X] T037 [US2] Implement `render_plan_md(plan) -> str` in `src/notes_processing/report.py` with the German sections from contracts/cli.md; make T035 pass
- [X] T038 [US2] Implement the `plan` subcommand in `src/notes_processing/cli.py`: find the source notebook by name (`notebook_names`/`hierarchy`), check target name not open and `<target-folder>\<target>` not existing (default folder from `special_folder()`), parse hierarchy, build scope from `--group`/`--section`, `index_links`, `build_plan`, create run folder (default `runs/<YYYYMMDD-HHMMSS>/`), write `plan.json` and `plan.md`, print a short German summary (counts, number of title corrections, links, attention items); OneNote is only read
- [X] T039 [US2] Implement the `apply` gate in `src/notes_processing/cli.py`: load `plan.json`, re-read the source and rebuild the plan, compare fingerprints (mismatch → German "Notizbuch wurde seit dem Plan geändert" + exit 5, nothing written), re-check target does not exist (exit 3), print the summary, prompt `Plan ausführen? Zum Bestätigen "ja" eingeben:` — any answer other than exactly `ja` → exit 6 with nothing written; `--yes` skips the prompt (integration tests only); then call `runner.run`; make T034 pass

**Checkpoint (MVP)**: `uv run notes-processing plan … --group 2023 --section 23-10` followed by `apply` merges one section safely (quickstart steps 3 and 4).

---

## Phase 5: User Story 3 - Restructure the whole notebook in one run (Priority: P2)

**Goal**: One unattended `apply` over all groups with per-page failure isolation, retries on OneNote unavailability, progress output, and a complete `report.json` + `report.md` with summary.

**Independent Test**: With `FakeGateway` on the 2 groups × 2 sections × 3 pages fixture, scope `all` yields 2 sections × 2 pages; with failure injection, the report names completed, incomplete, failed and not-started items and the exit code is 1.

### Tests for User Story 3 ⚠️ write first, ensure they fail

- [X] T040 [P] [US3] Full-run tests in `tests/unit/test_runner_full.py`: scope `all` creates one section per group in order, each with one page per section in order (FR-005, SC-003); a cross-section link is rewritten to the heading on the other merged page; locked section → `skipped`; summary counts (sections, pages, source pages, completed, skipped, failed) are correct (FR-013)
- [X] T041 [P] [US3] Failure tests in `tests/unit/test_runner_failures.py`: `OneNoteCallFailed` on `create_page` → page `failed`, run continues with the next section; failure on `update_page` after create → `incomplete`, never reported as completed (FR-012); `OneNoteUnavailable` → 3 retries with back-off (injectable sleep), then the run stops, remaining pages are `not_started`, and a partial `RunReport` is returned; no write call ever targets the source notebook
- [X] T042 [P] [US3] Report Markdown tests in `tests/unit/test_report_md.py`: `report.md` has Übersicht, Struktur, Titelkorrekturen, Links, Hinweise, Ergebnis (per page status + message, content issues per source page), with every failed/skipped item named so it can be identified without opening OneNote (SC-006)

### Implementation for User Story 3

- [X] T043 [US3] Extend `src/notes_processing/runner.py`: per-page try/except mapping to the run-state diagram in data-model.md (`failed` before creation, `incomplete` after), continue with the next section; `OneNoteUnavailable` retry 3× with back-off (1 s, 4 s, 16 s via injectable `sleep`), then stop, mark remaining pages `not_started` and return the partial report; per-section progress line (German) with counts; fill `RunReport.summary`, `started`, `finished`, `target_notebook_id`, `plan_fingerprint`, `title_decisions`; make T040 and T041 pass
- [X] T044 [US3] Implement `render_report_md(report, plan) -> str` in `src/notes_processing/report.py` (Ergebnis section plus the plan sections); make T042 pass
- [X] T045 [US3] In `src/notes_processing/cli.py` `apply`: always write `report.json` and `report.md` into the plan's run folder, including after a stopped run; exit 0 only if every page is in its final success state, 1 if anything failed/incomplete/not started, 4 if OneNote was unavailable at start
- [X] T046 [US3] Integration test in `tests/integration/test_full_run.py` (`@pytest.mark.onenote`): throwaway notebook with 2 groups × 2 sections × 3 pages, including an image, an embedded file, side-by-side outlines and a link from one section to a page in another; run `cli.main(["plan", …])` then `cli.main(["apply", "--plan", …, "--yes"])`; assert structure 2 sections × 2 pages, the link opens the heading on the other merged page, and the source notebook's `lastModifiedTime` values are unchanged

**Checkpoint**: Whole-notebook run works with a complete report (quickstart steps 5 and 6).

---

## Phase 6: User Story 4 - Verify that nothing was lost (Priority: P2)

**Goal**: After pass 2, every merged page is read back and checked against its source pages: every heading reads the original title or its listed replacement, and all source text is present unchanged. `verify` re-runs the check later.

**Independent Test**: Merge one section with `FakeGateway`, delete one paragraph from the target page in the fake, run verification → the report names the target page and the source page with the missing text.

### Tests for User Story 4 ⚠️ write first, ensure they fail

- [X] T047 [P] [US4] Verification tests in `tests/unit/test_verify.py`: `extract_text(xml_fragment)` returns all `one:T` content with HTML tags removed and entities decoded, whitespace kept, link text kept and `href`s ignored; identical source/target → `ok`; a removed paragraph → mismatch naming target page + source page + missing text; a changed character → mismatch; heading equal to the `TitleDecision.heading` (original or listed replacement) passes, anything else fails (FR-011, research R9)
- [X] T048 [P] [US4] CLI verify tests in `tests/unit/test_cli_verify.py`: `verify --report` on a clean fake run → exit 0 and `verify.md` written; after removing a paragraph in the fake target → exit 1 and `verify.md` lists the difference; no write calls

### Implementation for User Story 4

- [X] T049 [US4] Implement `extract_text(element) -> str`, `split_target_blocks(target_xml, plan_page) -> list[(heading, text)]` (split the merged page at the heading outlines, in order) and `verify_page(planned_page, source_xmls, target_xml) -> VerificationResult` in `src/notes_processing/verify.py`, pure functions shared for source and target; make T047 pass
- [X] T050 [US4] Hook verification into `src/notes_processing/runner.py`: after pass 2 read back each target page, call `verify_page`, set status `verified` or `verification_failed`, fill `RunReport.verification`; add the Prüfung section to `render_report_md` in `src/notes_processing/report.py`
- [X] T051 [US4] Implement the `verify` subcommand in `src/notes_processing/cli.py`: load `report.json`, re-read source and target pages (read-only), rerun `verify_page` for every page, write `verify.md` (German) next to the report, exit 0 if all match else 1; make T048 pass
- [X] T052 [US4] Integration test in `tests/integration/test_verify.py` (`@pytest.mark.onenote`): after a one-section merge in a throwaway notebook, remove one paragraph from the target page via `update_page`, run `verify` and assert exit 1 with the target and source page named

**Checkpoint**: All four user stories work; quickstart steps 1–6 pass on `OneNote-Test`.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T053 [P] Add `tests/unit/test_local_only.py` asserting no module under `src/notes_processing/` imports `socket`, `http`, `urllib`, `requests`, `ssl` or similar network libraries, and that only `onenote/gateway.py` imports `comtypes` (constitution I and II, FR-015)
- [X] T054 [P] Add a performance smoke test in `tests/unit/test_performance.py`: `build_plan` + `runner.run` with `FakeGateway` on a generated notebook of 15 groups × 12 sections × 30 pages completes in well under a minute (guards against accidental quadratic work toward SC-005)
- [X] T055 Run `uv run ruff check --fix` and `uv run ruff format` over `src/` and `tests/`, fix remaining issues
- [X] T056 Run quickstart.md steps 1–6 against `OneNote-Test`, including the visual check that the October "Zusammenfassung" keeps its two columns without overlap, and record results (including run time) in `specs/001-merge-sections-to-pages/quickstart.md` under a new "Validation log" heading
- [ ] T057 Review `plan.md` output for the real notebook (quickstart step 7) with the user before any real `apply`; do not run `apply` on the real notebook without the user present to type `ja`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup; blocks all stories
- **US1 (Phase 3)**: depends on Foundational
- **US2 (Phase 4)**: depends on Foundational; T039 (`apply` calls the runner) depends on US1's T031. T033–T038 can proceed in parallel with US1
- **US3 (Phase 5)**: depends on US1 (runner) and US2 (`apply` command)
- **US4 (Phase 6)**: T047 and T049 depend only on Foundational; T050 depends on US1's runner; T051 depends on US3's `report.json` writing (T045)
- **Polish (Phase 7)**: after the desired stories are complete

### Story completion order

```text
Setup → Foundational → US1 ─┬─→ US2 (gate) ─→ US3 ─→ US4 ─→ Polish
                            └─ (US2 tests/plan rendering and US4 verify.py can start right after Foundational)
```

### Within each story

- Tests first, and they must fail before implementation
- Pure modules (`titles`, `layout`, `links`, `verify`) before `pagebuilder`/`planner`, which come before `runner`, which comes before `cli`
- Integration test last in each story

---

## Parallel Opportunities

### Foundational

```text
T007 errors.py  |  T009 fake.py (after T007)  |  T010 fixtures  |  T011 conftest  |  T017 report JSON
```

### User Story 1

```text
Tests:  T019 + T020 (same file, write together)  |  T021 test_layout  |  T022 test_links  |  T023 test_pagebuilder  |  T024 test_runner_merge
Impl:   T025 titles.month_title  |  T027 layout.py  |  T028 links.py      (then T026, T029, T030, T031 sequentially)
```

### User Story 2

```text
T033 test_planner_determinism  |  T034 test_cli_plan_apply  |  T035 test_report_plan_md
```

### User Story 3

```text
T040 test_runner_full  |  T041 test_runner_failures  |  T042 test_report_md
```

### User Story 4

```text
T047 test_verify  |  T048 test_cli_verify     (T049 verify.py can start right after Foundational)
```

---

## Implementation Strategy

### MVP (US1 + US2, both P1)

1. Phase 1 Setup, Phase 2 Foundational
2. Phase 3 US1: the merge engine, validated with the fake and a throwaway notebook
3. Phase 4 US2: plan + confirmation gate
4. **Stop and validate**: quickstart steps 3 and 4 on `OneNote-Test` (one section, October with the Zusammenfassung page)

US1 alone is not shipped to the CLI: the constitution (principle III) forbids writing without a reviewed, confirmed plan, so US2 is part of the MVP.

### Incremental delivery

1. MVP → one section at a time, safely
2. US3 → whole notebook in one run with a full report
3. US4 → automatic proof that nothing was lost (needed before trusting a run of ≈ 5,400 pages)
4. Polish → quickstart validation, then the real notebook with the user present

---

## Notes

- [P] tasks touch different files and have no dependency on incomplete tasks
- Unit tests never touch real notebooks; integration tests create throwaway notebooks and never delete anything
- The source notebook is never written to; the gateway guard enforces it, and tests assert it
- Commit after each task or logical group

---

## Phase 8: Convergence

- [X] T058 Make `runner.run` in `src/notes_processing/runner.py` survive any unexpected per-page exception (for example `xml.etree.ElementTree.ParseError` from malformed page XML in `build_target_page`, `split_target_blocks` or `page_paragraphs`): mark that page `failed` before creation or `incomplete` after it with the error message, continue with the next page, and as a last resort around the whole run, still return a partial `RunReport` (`stopped=True`, remaining pages `not_started`) so `cli.apply` always writes `report.json` and `report.md`; add a `FakeGateway` test in `tests/unit/test_runner_failures.py` that returns unparseable XML for one source page and asserts the other pages complete and the report names the failed one, per FR-012 / US3/AC2 / T045 (partial)
- [X] T059 Review the test-only write helpers on the production gateway (`OneNoteGateway.create_section_group` and the `parent_id` parameter of `create_section` in `src/notes_processing/onenote/gateway.py`, mirrored in `onenote/fake.py`), which go beyond the four write methods in contracts/cli.md → OneNote gateway: either move them into a test-only subclass used by `tests/integration/conftest.py`, or document them in contracts/cli.md as guarded test helpers, per plan: gateway boundary / contracts/cli.md (unrequested)

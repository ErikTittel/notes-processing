# Research: Merge Sections into Pages

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Date**: 2026-11-07

The findings below come from a read-only probe of the OneNote COM API against the `OneNote-Test` notebook on the development machine (Windows 11, Microsoft 365 OneNote desktop, 64-bit), plus the documented OneNote 2013 XML schema.

## R1 — COM access library

- **Decision**: `comtypes`, loading the OneNote type library by GUID `{0EA692EE-BB50-4E3C-AEF0-356D91732725}` version 1.1 and creating `OneNote.Application` with the `IApplication` interface.
- **Rationale**: `pywin32` failed on this machine twice. `EnsureDispatch` raised "can not automate the makepy process", and calls through the generated module raised `TYPE_E_LIBNOTREGISTERED`, because Office left an empty `1.0` type-library key next to `1.1`. Fixing that would need a registry edit, which is a system change outside this project. `comtypes` worked unchanged, returns `[out]` parameters as return values, and is pure Python with no compiled parts.
- **Alternatives considered**: `pywin32` plus deleting the stale `1.0` registry key (rejected, because it changes the user's system configuration). A .NET or PowerShell bridge (rejected, because it adds a second runtime, against constitution principle V).

## R2 — Python version and tooling

- **Decision**: Python **3.14**, managed by **uv** (`.python-version` plus `pyproject.toml` plus `uv.lock`).
- **Rationale**: Python 3.15 is installed, but `comtypes` 1.4.17 warns that its enum handling may differ on 3.15 (comtypes issue #894). uv installs 3.14 next to 3.15 without affecting the system Python, and the lockfile makes runs reproducible.
- **Alternatives considered**: Python 3.15 (rejected until comtypes supports it officially). Plain pip and venv (it works, but has no lockfile and no Python version pinning).

## R3 — Reading and writing page content

- **Decision**: Read source pages with `GetPageContent(pageId, piBinaryDataFileType=5, xs2013=2)`, so images and ink come back with their binary `one:Data` and embedded files with their `pathCache`. Write target pages with `UpdatePageContent(xml, dateExpected=0, xs2013, force=False)` after `CreateNewPage(sectionId, npsBlankPageWithTitle=1)`.
- **Rationale**: This is the only API that covers all content types (FR-007, FR-008). The probe confirmed the page XML structure: `one:Title`, `one:Outline`, `one:Position`, `one:Size`, `one:OE`, `one:T` and `one:QuickStyleDef`.
- **Copy rules**:
  - Remove all `objectID` attributes from copied elements so OneNote assigns new IDs.
  - Re-map each `quickStyleIndex` to the target page's own `QuickStyleDef` list, merged by style name.
  - For embedded files and audio (`one:InsertedFile`, `one:MediaFile`), set `pathSource` to the source's `pathCache`.
  - Anything that can't be expressed this way is reported, never dropped (FR-008).
- **Alternatives considered**: Copying pages with OneNote's built-in copy and merge. The COM API has no merge operation, and copying whole pages would not combine them.
- **To confirm in the first implementation task**: that embedded files and audio copy correctly through `pathCache`, using a throwaway notebook.

## R4 — Layout of former pages on the merged page (FR-006, FR-006a)

- **Decision**: Lay the page out in a single column of *blocks*, one per former page:
  1. Each block starts with a heading outline holding the former title, then contains all of the source page's top-level positioned elements (`Outline`, `Image`, `InkDrawing`, `InsertedFile`, `MediaFile`).
  2. Every element keeps its x position and its y position relative to the top of its source page's content.
  3. The block's height is `max(y + height) − min(y)` over its elements, taken from the source `one:Size`.
  4. The next block starts after the previous one's bottom plus a fixed gap of 36 pt.
- **Rationale**: The probe showed that every outline carries its rendered `Position` and `Size`. For example, the October "Zusammenfassung" has 5 outlines laid out in two columns, with heights from 40 to 134 pt. Offsets can therefore be computed before writing, with no read-back, and the calculation is a pure function that can be unit tested.
- **Risk**: A stored `Size` may be out of date for pages last edited in another client. Mitigation:
  - Before writing, the run checks for overlaps by comparing bounding boxes and adds a safety margin.
  - The quickstart includes a visual check of the "Zusammenfassung" pages.
- **Alternatives considered**: Stacking everything into one outline. This was rejected because the user chose to keep side-by-side layout (Clarification 2026-11-07).

## R5 — Headings for former page titles

- **Decision**: Former titles become outlines styled `h1` for `pageLevel="1"`, `h2` for level 2 and `h3` for level 3, using OneNote's built-in heading `QuickStyleDef`s. The merged page's own title comes from FR-004.
- **Rationale**: This matches the spec's assumption about built-in heading styles and the edge case for subpages. Headings also make the paragraphs that page links point to (R7).

## R6 — Date-title correction (FR-009a)

- **Decision**: A pure function over a section's ordered list of titles:
  1. **Parse.** Titles matching `^\d{2}\.\d{2}\.\d{2}$` are dates. All other titles are left alone.
  2. **Section month.** It comes from the section name `YY-MM`. If the name has a different format, it's the month and year shared by most date titles in the section. If neither works, nothing in the section is corrected and the section is reported.
  3. **Mistyped titles.** A date title is mistyped when its month or year differs from the section month.
  4. **Group the mistyped titles.** Consecutive mistyped titles form one run. The run's anchors are the nearest correct date titles before and after it.
  5. **Exact gap.** If the number of free days between the anchors equals the length of the run, the run is filled with those days in order. For example, 04.10 to 07.10 with two mistyped titles gives 05.10 and 06.10.
  6. **Otherwise, use the day.** Each mistyped title keeps its own day number with the section's month and year, but only if that date lies strictly between its anchors and isn't already taken by another title. Titles that fail this check are reported as "could not be corrected".
  7. **Out of order.** A correct title that is not later than the previous date title is reported as "out of order" and is not changed.
- **Rationale**: This reproduces every example in the spec and never guesses. It is deterministic (FR-014) and has no OneNote dependency, so it can be fully unit tested.
- **Note**: `09.10.12` has the wrong year. It is mistyped, its anchors are 08.10.23 and 10.10.23, and the exact gap gives 09.10.23.

## R7 — Link handling (FR-009b)

- **Finding**: Links contain *different* GUIDs from the IDs in the notebook hierarchy:
  - A page link looks like `onenote:<section path>#<title>&section-id={G1}&page-id={G2}&end`.
  - A paragraph link adds `&object-id={G3}`.
  - A section-group link is the group's folder path.
- **Decision**:
  1. **Link index.** While planning, call `GetHyperlinkToObject` for every source section and page in scope (about 5,600 calls) and store `(section-id, page-id) → source object`. Section groups are recorded by their path.
  2. **Classify.** Each `href` in source `one:T` content is one of: a transferred target (its GUIDs or path are in the index), other OneNote content (an `onenote:` link not in the index, including targets that no longer exist), or external (any other scheme or a file path). Plain-text classification happens in the plan. The plan lists updated links and links pointing outside the transfer.
  3. **Pass 1, while writing.** Create all target sections and pages, with links left unchanged at first. After writing each page, read it back once. Then pair source and target elements by document order: old OE to new OE, and former page to heading OE.
  4. **Pass 2, after all pages exist.** Resolve each transferred link to its new target:
     - a former page link goes to the heading OE;
     - a paragraph link goes to the matching new OE;
     - a section link goes to the merged page;
     - a section-group link goes to the new section.
     Get the new URL with `GetHyperlinkToObject` and rewrite the `href` with one `UpdatePageContent` per affected page.
  5. **Paragraph targets.** For paragraph links, `object-id` values are resolved lazily. Only the pages that are targets of paragraph links are scanned, calling `GetHyperlinkToObject(page, oe)` for their OEs.
- **Rationale**: A link can only point to a new object after that object exists, so the work needs two passes. Limiting the paragraph lookups to targeted pages keeps the number of COM calls bounded.
- **Alternatives considered**: Parsing GUIDs from hierarchy IDs directly. That doesn't work, because the probe showed they differ.

## R8 — Target notebook location and creation (FR-010)

- **Decision**: Create the target notebook with `OpenHierarchy(<folder>\<target name>, "", cftNotebook=1)`. The folder defaults to `GetSpecialLocation(slDefaultNotebookFolder=2)`, which on this machine is `C:\Users\erikt\OneDrive\Dokumente\OneNote Notebooks`, and can be changed with `--target-folder`. Create sections with `OpenHierarchy("<group name>.one", notebookId, cftSection=3)`.
- **Rationale**: The tool only talks to OneNote through local COM calls and opens no network connections (constitution principle I). Where the notebook ends up is decided by OneNote and the user's setup, the same as for the existing notebooks, which are on OneDrive (`https://d.docs.live.net/...`).
- **Observed on this machine (2026-11-08)**: The default folder is inside OneDrive. When a notebook is created there, OneNote makes it a **OneDrive cloud notebook**. Locally only an Internet shortcut `<folder>\<target name>.url` remains, pointing to `onedrive.live.com`; there is no notebook folder. OneNote syncs the content, not the tool. A cloud notebook that still exists in OneDrive but is closed in OneNote is not visible to the tool. Creating a notebook with the same name then fails in `OpenHierarchy` with `0x80042006`.
- **Safety**: The tool refuses to start (exit code 3) in any of these cases:
  - a notebook with the target name is already open;
  - the folder `<folder>\<target name>` already exists;
  - the shortcut `<folder>\<target name>.url` already exists.
  
  That way it never mixes with or overwrites existing content, and a name clash is reported by `plan`, not as a COM error during `apply`. A cloud notebook whose local shortcut was deleted can't be detected; `apply` then stops before writing anything, and the report names the `OpenHierarchy` error.

## R9 — Verification (FR-011)

- **Decision**: After pass 2, read each target page back. Extract the text of every former page's part: all `one:T` content with HTML tags removed and entities decoded, with whitespace kept as is. Compare it with the same extraction from the source page; link `href`s are ignored, link text is not. Check that each former page's heading reads the original title, or its replacement from FR-009a. Any difference is reported with the target page and the source page.
- **Rationale**: This checks the spec's "text unchanged" promise directly, using the same pure extraction function for source and target.

## R10 — Plan, confirmation and determinism (FR-002, FR-003, FR-014)

- **Decision**: `plan` writes `plan.json` (machine-readable, sorted, with a fingerprint) and `plan.md` (for reading) into a run folder. `apply` takes `plan.json`, re-reads the source and builds the plan again. If the fingerprint differs, it stops ("notebook changed since the plan was made"). Otherwise it shows a summary and asks the user to type `ja` before writing anything.
  - The fingerprint is a SHA-256 hash of the plan's content.
  - Source `lastModifiedTime` values are included in the plan, so any edit after planning changes the fingerprint.
- **Rationale**: Confirmation happens on exactly what the user reviewed, and nothing is written without it.

## R11 — Failure handling and performance (FR-012, FR-013, SC-005)

- **Decision**: Work through the plan one target page at a time. A COM error on a page marks that page as `failed`, or `incomplete` if it was already created, and processing continues with the next section. If OneNote stops responding (`RPC_E_SERVERCALL_RETRYLATER` or a disconnected server), the tool retries 3 times with back-off, then stops the run and writes the report so far.
- **Performance estimate**: About 5,400 `GetPageContent` calls with binary data, about 180 page writes, about 180 read-backs, and link resolution. At roughly 0.2–0.5 s per call, that's an estimated 30–60 minutes, which is within SC-005's 2 hours. Progress is shown per section.
- **Out of scope for this version**: resuming a failed run. The user starts a fresh run into a new target notebook name, which is safe because the source is never changed.

## R12 — Hierarchy edge cases

- **Decision**: Read the hierarchy with `GetHierarchy(notebookId, hsPages=4, xs2013)`.
  - **Recycle bin.** Skip `isRecycleBin` section groups and pages marked `isInRecycleBin`.
  - **Locked sections.** Report sections with `locked="true"` or `encrypted="true"` as skipped.
  - **Nested groups and loose sections.** Report sections outside a top-level group, and groups nested inside groups, as left alone.
  - **Subpages.** Page order is document order. `pageLevel` gives the heading level.
- **Rationale**: This covers the edge cases in the spec, using only attributes confirmed in the 2013 schema.

## R13 — Embedded online videos (FR-008a)

- **Findings** (tested 2026-11-08 on `OneNote-Test` page 25.07.23 and on `Diary`):
  - `GetPageContent` shows an embedded online video only as an ordinary `one:Image` with the preview picture. This is the same with every page info mode. The XML has no video address and no video marker. Exporting the page with `Publish` as MHTML, HTML or Word doesn't contain the address either.
  - Writing a video address with `UpdatePageContent`, as a link or as plain text, only creates a link. OneNote embeds a video only when the address is pasted in its user interface.
  - OneNote gives a new embedded video the size 267 × 150 or 360 × 202.5 points without `isSetByUser`, or the alternative text "Webinhalt"/"Webinhalte". In `Diary` (without "ab 2024") this matches 14 pages, in `OneNote-Test` 3. Each of them has a YouTube link in its text, usually just before the preview.
  - `one:Image` accepts a `hyperlink` attribute through `UpdatePageContent`, and OneNote keeps it. An image written through the API always gets `isSetByUser="true"`.
- **Decision**: Recognise a preview by these sizes or the alternative text (`videos.is_video_preview`). Its video address is the last video link (YouTube, youtu.be, Vimeo) before it on the page, or else the first one after it. The preview is carried over as an image and gets that address as its `hyperlink`, unless it already has a link. Each preview is listed in the plan (`video_preview`) and in the report under "Nicht übertragbare Inhalte" (element "Video"), with the address to paste so OneNote embeds the video again.
- **Rationale**: A working embedded video can't be written through the API. A linked preview keeps the video one click away, and the list makes re-embedding by hand a short task.

## Technology summary

| Need | Choice |
|------|--------|
| Language | Python 3.14 (via uv) |
| OneNote access | comtypes (COM, type library by GUID) |
| XML | standard library `xml.etree.ElementTree` |
| Command line | standard library `argparse` |
| Tests | pytest (unit tests on XML fixtures and a fake gateway; integration tests marked `onenote`) |
| Lint and format | ruff |
| Environment and lockfile | uv |

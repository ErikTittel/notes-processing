# Feature Specification: Merge Sections into Pages

**Feature Branch**: `001-merge-sections-to-pages`

**Created**: 2026-11-07

**Status**: Draft

**Input**: User description: "Ich habe 15 Notizbuchabschnittsgruppen in einem Notizbuch, mit jeweils 12 Registerkarten, die jeweils ca. 30 Seiten enthalten. Der Inhalt aller Seiten in einem Abschnitt soll zusammengefasst werden auf eine Seite. Die zusammenfassten Seiten einer Abschnittsgruppen sollen in einem Abschnitt liegen. Das heißt, Abschnitte werden zu Seiten, Abschnittsgruppen werden zu Abschnitten. Die Texte sollen unverändert erhalten bleiben. Zur Strukturierung des Texts auf jeder Seite sollen die früheren Seitentitel in den Text der neuen Seiten übernommen werden."

## Overview

The user has a OneNote notebook organized three levels deep: about 15 section groups, each with about 12 sections, each with about 30 pages (≈ 5,400 pages in total). This structure is too fine-grained. The feature flattens it by one level:

| Before | After |
|--------|-------|
| Section group | Section (same name) |
| Section | Page (same name), inside the section created from its former group |
| Page | Part of the new page's body: former page title as a heading, followed by the page's unchanged content |

The result is about 15 sections holding about 180 pages, with no note text lost or altered.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Merge one section into one page (Priority: P1)

The user picks a single section. All of its pages are combined, in their original order, into one new page whose title is the section's name. Each former page appears on the new page as a heading carrying the former page title, followed by that page's content exactly as it was.

**Why this priority**: This is the core transformation. Everything else repeats it. It also lets the user check the result on a small, low-risk scope before touching the whole notebook.

**Independent Test**: Run the merge on one section with a few pages and compare the new page against the originals: every former title appears as a heading in the original order, and every piece of text is present and unchanged.

**Acceptance Scenarios**:

1. **Given** a section "Kapitel 3" with pages "A", "B", "C" in that order, **When** the user merges the section, **Then** a page titled "Kapitel 3" exists whose body contains the heading "A" followed by A's content, then heading "B" with B's content, then heading "C" with C's content.
2. **Given** a page containing formatted text (bold, lists, tables), **When** its section is merged, **Then** the text and its formatting appear unchanged on the new page.
3. **Given** a page containing an image and an attached file, **When** its section is merged, **Then** both appear on the new page within that former page's block.
4. **Given** a section with an empty page that has only a title, **When** the section is merged, **Then** the title still appears as a heading on the new page, with nothing beneath it.
5. **Given** a page with text blocks in two columns, **When** its section is merged, **Then** the blocks appear in the same side-by-side arrangement below that page's heading, without overlapping neighbouring parts.
6. **Given** sections named "23-01" and "23-03", **When** they are merged, **Then** the new pages are titled "Januar 2023" and "März 2023".
7. **Given** a page with a link to the page "02.01.23" of the same notebook, a link to a page in the notebook "Diary", and a web link, **When** its section is merged, **Then** the first link opens the heading "02.01.23" on the merged page "Januar 2023". The second link still opens the same page in "Diary". The web link is unchanged. The first two are listed in the run report.

---

### User Story 2 - Preview and confirm before changing anything (Priority: P1)

Before any change is made, the user sees a plan: which new sections and pages will be created, from which sources, how many pages each new page combines, and anything that cannot be merged cleanly. Nothing changes until the user explicitly confirms.

**Why this priority**: The notebook holds thousands of pages of personal notes. The project constitution requires that changes be shown and confirmed before they are applied. Without this, P1 is unsafe to use.

**Independent Test**: Request a plan for the full notebook, decline it, and verify that the notebook is unchanged.

**Acceptance Scenarios**:

1. **Given** the notebook, **When** the user requests a plan, **Then** the plan lists every section group → new section and every section → new page, with page counts per new page.
2. **Given** a displayed plan, **When** the user declines, **Then** no notebook content is created, changed, or removed.
3. **Given** the same notebook state, **When** the user requests the plan twice, **Then** both plans are identical.

---

### User Story 3 - Restructure the whole notebook in one run (Priority: P2)

The user runs the transformation for all section groups at once. Each section group becomes one section with the group's name; each of its sections becomes one merged page inside that new section, in the original section order.

**Why this priority**: This is the actual goal (≈ 180 merges). It depends on P1 working correctly and on P2 for safety.

**Independent Test**: Run on a test notebook with 2 section groups × 2 sections × 3 pages and verify the resulting structure is 2 sections × 2 pages with all content present.

**Acceptance Scenarios**:

1. **Given** 15 section groups, **When** the full run completes, **Then** the new target notebook contains 15 sections named after the groups, each containing one page per former section, in the former order.
2. **Given** a failure partway through the run (for example, OneNote becomes unavailable), **When** the run stops, **Then** the user gets a report of which groups and sections were completed and which were not. The source notebook is untouched in either case.
3. **Given** a completed run, **When** the user reviews the summary, **Then** it states the number of sections, pages, and source pages processed, plus any items that needed attention.

---

### User Story 4 - Verify that nothing was lost (Priority: P2)

After the run, the user receives a verification result that confirms, for each new page, that all source page titles and all source text are present on it.

**Why this priority**: With about 5,400 pages, a manual check is not practical. Automatic verification is how the user knows the "text unchanged" promise was kept.

**Independent Test**: After merging a section, deliberately remove a paragraph from the new page and re-run verification. The missing text is reported.

**Acceptance Scenarios**:

1. **Given** a successful merge, **When** verification runs, **Then** it reports a match for every new page.
2. **Given** a new page missing any source text, **When** verification runs, **Then** it names the new page and the source page whose text is missing.

### Edge Cases

- **Subpages** (pages indented under another page): included in original order; the former title heading reflects the indent level (a subpage title becomes a lower-level heading than its parent page).
- **Text blocks side by side** (for example the "Zusammenfassung" pages with topics in two columns): the layout is kept as it is in OneNote (FR-006a). It is not turned into a single column.
- **Mistyped date titles** (for example "25.11.23" between 24.01.23 and 26.01.23): corrected from the chronological sequence of the neighbouring dates as described in FR-009a and listed in the plan. Titles that cannot be corrected without guessing are kept and reported. Titles in the right month but out of order are kept and reported as "out of order". Correcting them by hand is not practical for a notebook with many section groups.
- **Pages without a title**: get a placeholder heading such as "(Untitled page)" so the boundary between former pages stays visible.
- **Empty sections** (no pages): produce a new page containing only the section's name, and the plan flags them.
- **Duplicate names** (two sections with the same name in one group, or two groups with the same name): the plan flags them. New pages and sections keep the original names, since OneNote allows duplicates.
- **Sections nested more deeply** (section groups inside section groups) or **sections outside any group**: not transformed. The plan lists them so the user knows they were left alone.
- **Password-protected sections** that are locked: skipped and reported. They are not merged until the user unlocks them.
- **Very large source sections**: merged like any other. The plan shows page counts so the user can spot outliers.
- **Content that OneNote cannot copy faithfully**: reported per source page, never silently dropped.
- **Links whose target no longer exists** (the target page was deleted earlier): kept unchanged like any link to content that is not transferred, and listed in the report as "target not found".
- **Links from other notebooks into the transferred pages** (for example from "Diary"): not changed. They keep pointing to the unchanged source notebook.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let the user select the source notebook, the name of the new target notebook, and the scope: a single section, a single section group, or all section groups. With all section groups, the user can leave out section groups by name (for example "ab 2024"). A left-out group is not transferred, is listed in the plan as an attention item, and an unknown name is an error.
- **FR-002**: System MUST produce a plan before making any change. The plan lists each new section (with source section group), each new page (with source section and number of source pages), and every item that will be skipped or needs attention.
- **FR-003**: System MUST NOT modify the notebook until the user explicitly confirms the plan.
- **FR-004**: For each source section, the system MUST create exactly one new page. Its title is the section's name, except when the name is a coded month (two-digit year, hyphen, two-digit month, for example "23-01"). In that case the title is the German month name followed by the four-digit year: "23-01" becomes "Januar 2023", "23-02" "Februar 2023", "23-03" "März 2023", and so on through "Dezember". Section names in any other format are used unchanged.
- **FR-005**: For each source section group, the system MUST create exactly one new section whose name equals the group's name. That section contains the new pages for the group's sections, in the original section order.
- **FR-006**: The new page MUST contain, for each source page in original order, the former page title as a heading followed by that page's content.
- **FR-006a**: When a source page has several separate text blocks placed next to or below each other, the system MUST keep their arrangement inside that page's part of the new page. Blocks keep their positions relative to each other, the whole arrangement sits below the former page's title heading, and it MUST NOT overlap the parts of the preceding or following former pages.
- **FR-007**: Text content MUST be carried over unchanged: same characters, same order, same formatting (including lists and tables). The only exception is links, which are handled as described in FR-009b. A web link whose visible text is its own address and that directly follows a character other than a space (for example "(https://…)") is written as plain text, and OneNote turns it back into the same link when it saves the page. Written as a link, OneNote's automatic link detection would insert a visible space before it. This is done only where OneNote was tested to recreate the link exactly: the characters between the previous space and the link are punctuation such as `( [ { " ' „ “ « » - – : ; , . ! ? =`, and the link is followed by a space, the end of the paragraph, or closing punctuation. Other such links are written as links, and the inserted space is reported by verification.
- **FR-008**: Non-text content on source pages (images, embedded files, ink, audio) MUST be carried over to the new page at its position within the former page's block. Any item that cannot be carried over MUST be reported, naming the source page, and MUST NOT be dropped silently.
- **FR-008a**: An embedded online video (for example from YouTube) can only be carried over as its preview picture, because OneNote's interface for other programs doesn't provide the video itself (research R13). The preview picture MUST link to the video's address when the source page has a video link. Every probable video preview MUST be listed in the plan and the run report, naming the source page and the video address, so the user can embed the video again by pasting the address in OneNote.
- **FR-009**: The former page title is carried over as the heading. Page metadata such as the creation date is not added to the new pages, because date titles already carry the date. Non-date titles (for example "Jahresausblick", "Zusammenfassung") are carried over unchanged.
- **FR-009a**: A date title is *mistyped* when its month or year differs from the section's month. The section's month comes from the section name when it is a coded month (for example "23-01" means January 2023). Otherwise it is the month and year shared by most date titles in the section. Examples: "25.11.23" in section 23-01, "09.10.12" in section 23-10. The heading for a mistyped title MUST be replaced with the date that fits the chronological sequence of the neighbouring date titles in the same section, in the same format (DD.MM.YY). For example, "25.11.23" between "24.01.23" and "26.01.23" becomes "25.01.23". "05.12.23" and "06.12.23" between "04.10.23" and "07.10.23" become "05.10.23" and "06.10.23". If the neighbouring dates leave room for more than one date (for example a wrong title between "24.01.23" and "28.01.23", or one on the first or last date page of a section), the system MUST keep the day from the mistyped title and take the month and year from the section's month. It uses that date only if it falls between the neighbouring dates. Otherwise the original title is kept and listed in the plan and the run report as "could not be corrected". A date title with the correct month and year that breaks the chronological order of its neighbours (for example "15.01.23" between "03.01.23" and "04.01.23") is NOT changed, but MUST be listed in the plan and the run report as "out of order". The page's creation date MUST NOT be used, because some pages were written on a different day than the one they describe. Every replacement MUST be listed in the plan and the run report with its section, original title, and new title. If a section has no coded month name and no majority month, it is reported and its titles are left unchanged.
- **FR-009b**: Links in the transferred content MUST be handled by target:
  - **Link to OneNote content that is transferred**: The link MUST be updated to point to the same content in the target notebook. A link to a former page points to that page's heading on the merged page. A link to a paragraph points to the same paragraph. A link to a former section points to the merged page created from it. A link to a former section group points to the section created from it. The link text stays unchanged.
  - **Link to OneNote content that is not transferred**: This means content in another notebook (such as "Diary"), or source-notebook content outside a partial run's scope (including left-out section groups, FR-001). The link stays unchanged and keeps pointing to its original target. It is listed in the plan and the run report as "points to content outside the transfer".
  - **Web link, file link, or e-mail link** (for example `https://…`, `C:\…`, `\\server\share\…`, `mailto:…`): Link text and link address stay unchanged.
  - **Reporting**: Every updated link and every link pointing outside the transfer MUST be listed in the plan and the run report with the page it is on, its text, and its original target.
- **FR-010**: The result MUST be created in a new, separate notebook. The source notebook MUST remain completely unchanged. It is never modified or deleted by the system. Removing the source notebook after reviewing the result is left to the user.
- **FR-011**: System MUST verify after each merge that every source page title (or its listed replacement, FR-009a) and all source text appear on the new page, and MUST report any mismatch by naming the new page and the source page. Whitespace at the end of a paragraph is not compared: OneNote removes it whenever a page is saved, and it is not visible. Leading whitespace and whitespace inside a paragraph are compared. The addresses of web links are compared too, so a web link that OneNote did not recreate (FR-007) is reported.
- **FR-012**: If an operation fails, the system MUST stop processing the affected item, report the failure, and MUST NOT report it as completed. A partially created page or section in the target notebook MUST be marked as incomplete in the report.
- **FR-013**: At the end of a run, the system MUST present a summary of completed, skipped, and failed items.
- **FR-014**: The same notebook state MUST always produce the same plan.
- **FR-015**: The system MUST operate entirely locally and MUST NOT send note content or metadata anywhere.

### Key Entities

- **Notebook**: the OneNote notebook being restructured. It contains section groups and possibly loose sections.
- **Section group (source)**: a named container of sections. It maps to one new section.
- **Section (source)**: a named container of pages in a fixed order. It maps to one new page.
- **Page (source)**: has a title, an indent level (page or subpage), a creation date, and content (text and possibly non-text items). It maps to a titled block within a new page.
- **Transformation plan**: the full list of planned mappings (group → section, section → page, page → block), counts, and flagged items. The user reviews it before confirming.
- **Link**: a piece of linked text on a source page, with its target. The target is transferred OneNote content, source-notebook content outside a partial run, other OneNote content, or an external address (web, file, or e-mail). A link either becomes an updated link or stays unchanged (FR-009b). No link is removed.
- **Run report**: the outcome per item (completed, skipped, failed), the verification results, title replacements, updated links, and links pointing outside the transfer.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of source page text appears unchanged on the new pages, confirmed by verification for all ≈ 5,400 source pages.
- **SC-002**: 100% of former page titles appear as headings on the new pages, in the original order. The only exceptions are mistyped date titles, which appear as their listed replacement (FR-009a).
- **SC-003**: The resulting structure matches the plan exactly: about 15 new sections and about 180 new pages, one per source section group and source section.
- **SC-004**: The user can review the plan for the full notebook and decide whether to proceed in under 10 minutes.
- **SC-005**: The full notebook is transformed in one unattended run of under 2 hours.
- **SC-006**: When any item fails or is skipped, the user can identify it by name from the run report without opening OneNote.

## Assumptions

- The notebook is stored locally or synced, and is fully available in OneNote while the run takes place; the user does not edit it during the run.
- Page order, section order, and section group order as shown in OneNote are the intended orders.
- "Unchanged text" means the same characters and formatting. The arrangement of text blocks within each former page is preserved too (FR-006a). The only layout change is that former pages are placed one below the other. Whitespace at the end of a paragraph is not part of "unchanged text", because OneNote removes it when a page is saved (FR-011).
- Heading style for former page titles uses OneNote's built-in heading styles, so they stand out and can be found.
- One user runs the tool on their own Windows machine. There is no multi-user or concurrent editing scenario.
- Pages are not summarized or rewritten. "Zusammenfassen" means combining pages, not shortening their content (confirmed by the user).
- Most former page titles are dates (DD.MM.YY), so they already provide the chronological context. No separate date metadata is needed (confirmed by the user). Some pages have non-date titles such as "Jahresausblick" or "Zusammenfassung".
- A page's creation date is not reliable for dating its content, because some pages were written on a different day than the one they describe (confirmed by the user).
- Coded month names use a two-digit year that means 20YY ("23-01" means January 2023).
- Deleting the source notebook is out of scope. The user does it manually after reviewing the result.

## Clarifications

### Session 2026-11-07

- Q: Where should the result go, and what happens to the original structure? → A: In a new notebook; the source notebook stays unchanged.
- Q: Should non-text content be carried over? → A: Yes, all content (images, files, ink, audio); anything that cannot be copied is reported.
- Q: Should original page dates be shown under each former title? → A: No; the former page titles are the dates.
- Q: What should happen when a date title doesn't match the month it belongs to (e.g. "25.11.23" among January pages)? → A: Correct it automatically and list each replacement; manual correction is not feasible across many section groups. (Correction source revised below.)
- Q: In which order should side-by-side text blocks of a former page appear on the merged page? → A: Keep the side-by-side layout within that page's part of the merged page.
- Q: What should a mistyped date title be corrected to? → A: The date that fits the chronological sequence of the neighbouring dates (e.g. "25.11.23" between 24.01.23 and 26.01.23 becomes "25.01.23"), never the page's creation date, because some pages were written on a different day than the one they describe.
- Q: If the neighbouring dates leave room for more than one date, what should the corrected title be? → A: Keep the title's day with the section's month and year if that fits between the neighbours; otherwise keep the original title and report it as "could not be corrected".
- Q: Should a date title with the right month and year but out of order (e.g. "15.01.23" between 03.01.23 and 04.01.23) be corrected? → A: No; keep it and list it in the plan and report as "out of order".
- Q: What should happen to links in the transferred text? → A: Links to transferred OneNote content point to the same content in the new notebook. Web links stay unchanged. (Handling of links to other OneNote content revised below.)
- Q: In a partial run, what should happen to links to source pages outside that run's scope? → A: Keep them pointing to the original page in the source notebook, and report them as "points to content outside the transfer".
- Q: Should links to local or network files and e-mail links be kept unchanged, like web links? → A: Yes, keep them unchanged.
- Q: What should happen to links to OneNote content that is not part of the transfer, for example another notebook? → A: Keep them unchanged (same as links outside a partial run) and report them; no link is removed.
- Q: How should coded month section names such as "23-01" appear as titles of the new pages? → A: As the German month name and four-digit year ("Januar 2023", "Februar 2023", "März 2023", …).

### Session 2026-11-08

- Q: The quickstart run on OneNote-Test reported differences although the text looked identical. In 13 cases a space at the end of a paragraph was missing on the merged page. In 1 case a space appeared before a web link written directly after "(". How should these be handled? → A: OneNote removes whitespace at the end of a paragraph when it saves a page, so verification ignores it (FR-011). The space before the link comes from OneNote's automatic link detection, which applies when a link's text is its own web address and follows a character other than a space. Such links are written as plain text where OneNote was tested to recreate the identical link, and verification compares web link addresses (FR-007, FR-011).

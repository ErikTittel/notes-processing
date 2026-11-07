# Data Model: Merge Sections into Pages

**Feature**: [spec.md](spec.md) | **Research**: [research.md](research.md)

All entities are immutable Python dataclasses in `src/notes_processing/model.py`. The source model is built from OneNote hierarchy and page XML and holds no live COM objects, so the planner, title correction, layout, link classification and verification can be tested without OneNote (constitution principle V).

## Source side (read-only)

### SourceNotebook

| Field | Type | Notes |
|-------|------|-------|
| `id` | str | OneNote hierarchy ID |
| `name` | str | for example "OneNote-Test" |
| `path` | str | local path or `https://d.docs.live.net/...` |
| `groups` | list[SourceGroup] | top-level section groups, in OneNote order, recycle bin excluded |
| `ignored` | list[IgnoredItem] | loose sections and nested groups (reported, not transformed) |

### SourceGroup

| Field | Type | Notes |
|-------|------|-------|
| `id`, `name`, `path` | str | `path` identifies section-group links (R7) |
| `sections` | list[SourceSection] | in OneNote order |

### SourceSection

| Field | Type | Notes |
|-------|------|-------|
| `id`, `name`, `path` | str | |
| `last_modified` | str | part of the plan fingerprint |
| `locked` | bool | `locked` or `encrypted` attribute, meaning the section is skipped |
| `link_section_guid` | str \| None | the `section-id` from `GetHyperlinkToObject` (R7) |
| `pages` | list[SourcePage] | document order, recycle bin excluded |

### SourcePage

| Field | Type | Notes |
|-------|------|-------|
| `id` | str | hierarchy ID |
| `title` | str | may be empty, in which case the heading is "(Untitled page)" |
| `level` | int | 1–3 (`pageLevel`), giving heading h1–h3 |
| `last_modified` | str | part of the fingerprint |
| `link_page_guid` | str \| None | the `page-id` from `GetHyperlinkToObject` |

Page *content* is not held in the model. It's loaded per section while applying, and while planning it's only read to find links and non-text items.

## Planning

### TitleDecision (output of FR-009a correction)

| Field | Type | Notes |
|-------|------|-------|
| `page_id` | str | |
| `original` | str | |
| `heading` | str | text written as the heading |
| `status` | enum | `unchanged`, `corrected`, `could_not_correct`, `out_of_order`, `untitled`, `no_section_month` |

Rules (from [research.md R6](research.md)):
- `corrected` only when the exact-gap rule or the keep-the-day rule gives a date strictly between the anchors that isn't already used.
- `heading == original` for every status except `corrected` and `untitled`.

### LinkRef (one `href` found on a source page)

| Field | Type | Notes |
|-------|------|-------|
| `source_page_id` | str | page the link is on |
| `text` | str | visible link text |
| `href` | str | original target |
| `kind` | enum | `transferred_page`, `transferred_paragraph`, `transferred_section`, `transferred_group`, `outside_transfer`, `target_not_found`, `external` |
| `target_source_id` | str \| None | resolved source object for `transferred_*` |

`target_not_found` is an `onenote:` link into the *source notebook* whose GUIDs aren't in the index. Both `outside_transfer` and `target_not_found` stay unchanged and are reported (FR-009b).

### PlannedPage

| Field | Type | Notes |
|-------|------|-------|
| `source_section_id` | str | |
| `title` | str | from FR-004 ("23-01" becomes "Januar 2023", any other name unchanged) |
| `blocks` | list[TitleDecision] | one per source page, in order |
| `source_page_count` | int | |

### PlannedSection

| Field | Type | Notes |
|-------|------|-------|
| `source_group_id` | str | |
| `name` | str | same as the group name (FR-005) |
| `pages` | list[PlannedPage] | in section order |

### Plan

| Field | Type | Notes |
|-------|------|-------|
| `source_notebook` | str | name and ID |
| `target_notebook_name` | str | |
| `target_folder` | str | |
| `scope` | Scope | `all`, `group:<name>` or `section:<group>/<name>` |
| `sections` | list[PlannedSection] | |
| `title_decisions` | list[TitleDecision] | flattened, only the statuses other than `unchanged` |
| `links` | list[LinkRef] | everything except `external` |
| `attention` | list[AttentionItem] | locked, empty, duplicate names, ignored structure, non-text content to watch |
| `fingerprint` | str | SHA-256 of the canonical JSON of all the fields above plus the source `last_modified` values |

**Invariants**:
- Building a plan twice from an unchanged notebook gives byte-identical JSON (FR-014). Lists keep OneNote order, and dictionaries are written with sorted keys.
- Each source section that isn't locked appears exactly once as a `PlannedPage`. Each group in scope appears exactly once as a `PlannedSection`.

## Applying

### Block layout (pure function, FR-006a)

Input: the source page's top-level elements, each with `(x, y, width, height)`. Output: the y offset for each element on the target page.

| Concept | Rule |
|---------|------|
| block top | previous block bottom + 36 pt (the first block starts below the page title) |
| heading | at the block top, x = 36 |
| element | `x` unchanged, `y = block top + heading height + (y − min_y of the source page)` |
| block bottom | `max(y + height)` over the block's elements |
| check | no bounding box in a block overlaps any box of another block |

### Run state per target page

```text
planned ──► created ──► content_written ──► links_updated ──► verified
   │            │               │                  │
   └──► failed  └──► incomplete └──► incomplete    └──► verification_failed
skipped (locked section, or outside scope)
```

### RunReport

| Field | Type | Notes |
|-------|------|-------|
| `plan_fingerprint` | str | |
| `started`, `finished` | str | ISO timestamps |
| `target_notebook_id` | str | |
| `pages` | list[PageOutcome] | status from the state diagram, plus a message |
| `title_decisions` | list[TitleDecision] | copied from the plan |
| `links` | list[LinkOutcome] | `updated` (new href) or `kept`, plus the reason |
| `content_issues` | list[ContentIssue] | non-text items that couldn't be copied, by source page (FR-008) |
| `verification` | list[VerificationResult] | per target page: `ok`, or a list of `(source page, missing or changed text)` |
| `summary` | counts | sections, pages, source pages, completed, skipped, failed (FR-013) |

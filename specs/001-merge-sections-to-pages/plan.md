# Implementation Plan: Merge Sections into Pages

**Branch**: `001-merge-sections-to-pages` | **Date**: 2026-11-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-merge-sections-to-pages/spec.md`

## Summary

A Python command-line script restructures a OneNote notebook by one level. Each section group becomes a section, and each section becomes one merged page. Each former page becomes a heading followed by its unchanged content, with side-by-side blocks kept in place. Mistyped date titles are corrected from neighbouring dates, coded month names become German month names, and links into the transferred content are re-pointed. The result goes into a new notebook, and the source is never written to.

The script works through the OneNote desktop COM API using `comtypes`. It runs in three steps:
1. **`plan`** is read-only. It produces a deterministic plan for the user to review.
2. **`apply`** carries out the plan after the user confirms. Pass 1 writes the pages, pass 2 updates links, and then every page is verified.
3. **`verify`** can re-check a finished run later.

All transformation logic is pure Python and is tested without OneNote.

## Technical Context

**Language/Version**: Python 3.14, pinned with uv (3.15 is installed, but comtypes isn't officially supported on it yet; see [research.md R2](research.md))

**Primary Dependencies**:
- `comtypes` for OneNote COM access ([R1](research.md); `pywin32` fails on this machine because of a broken type-library registration)
- Everything else from the standard library (`xml.etree.ElementTree`, `argparse`, `json`, `hashlib`, `dataclasses`)

**Storage**: Plan and report files (JSON + Markdown) in `runs/<timestamp>/`. Notes stay in OneNote.

**Testing**: pytest. Unit tests use synthetic XML fixtures and a `FakeGateway`. Integration tests are marked `onenote` and run against a throwaway notebook.

**Target Platform**: Windows 10/11 with the Microsoft 365 OneNote desktop app (the COM API isn't available in the OneNote for Windows 10 app or on the web)

**Project Type**: Single-user command-line tool

**Performance Goals**: About 5,400 source pages in under 2 hours (SC-005), with an estimated 30–60 minutes ([R11](research.md)). Planning the full notebook should take a few minutes.

**Constraints**:
- No network access by the tool itself.
- The source notebook is read-only.
- Nothing is written without explicit confirmation of the reviewed plan.
- The same input always gives the same plan.

**Scale/Scope**: 15 section groups → 15 sections; about 180 sections → 180 merged pages; about 5,400 source pages

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How the design complies | Status |
|-----------|------------------------|--------|
| I. Local-only operation | The only external interface is local COM to OneNote. No HTTP or telemetry libraries. The target notebook is created through OneNote in a folder chosen by the user. If that folder is in OneDrive, OneNote creates a cloud notebook and syncs it; that is the user's existing setup, not something the tool does ([R8](research.md)). | ✅ Pass |
| II. Windows and OneNote COM | All COM calls are isolated in `onenote/gateway.py`. COM errors become typed exceptions, and each one is reported as failed or incomplete, never as success ([R11](research.md)). | ✅ Pass |
| III. Safe reorganization | The output goes to a new notebook. The gateway's write methods reject IDs outside the target notebook. The tool refuses to start if the target already exists. `apply` requires typing "ja" after showing the plan, and it stops if the source changed since the plan ([R10](research.md)). | ✅ Pass |
| IV. Predictable, user-visible changes | The plan is deterministic and fingerprinted (FR-014). Every title correction, link change, skipped item and content problem is listed in the plan and the report. | ✅ Pass |
| V. Testability and simplicity | Title correction, month names, layout, link classification, planning and verification are pure functions over dataclasses and XML. COM sits behind one gateway with a fake for tests. Standard library throughout, with a single third-party runtime dependency. | ✅ Pass |
| Platform constraints | A Python application on Windows that uses the OneNote COM API. | ✅ Pass |
| Development workflow | Unit tests never need real notebooks (synthetic fixtures). COM behaviour gets integration tests against a throwaway notebook. | ✅ Pass |

**Post-design re-check (after Phase 1)**: All gates still pass. The design added a two-pass write for links and a read-back per page. Both stay inside the gateway boundary and add no dependencies. No exceptions are needed.

## Project Structure

### Documentation (this feature)

```text
specs/001-merge-sections-to-pages/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0: COM probe findings and decisions
├── data-model.md        # Phase 1: entities, plan/report formats, run states
├── quickstart.md        # Phase 1: validation scenarios
├── contracts/
│   └── cli.md           # Phase 1: commands, options, exit codes, files, gateway boundary
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks; not created here)
```

### Source Code (repository root)

```text
pyproject.toml           # uv project, entry point "notes-processing", ruff + pytest config
.python-version          # 3.14
uv.lock

src/notes_processing/
├── __init__.py
├── cli.py               # argparse: plan / apply / verify, prompts, exit codes
├── model.py             # dataclasses from data-model.md
├── hierarchy.py         # hierarchy XML → SourceNotebook (+ ignored / locked items)
├── titles.py            # FR-004 month names, FR-009a date correction (pure)
├── links.py             # parse onenote: hrefs, link index, classification (pure)
├── planner.py           # SourceNotebook + scope → Plan, fingerprint (pure)
├── layout.py            # block offsets, overlap check (pure)
├── pagebuilder.py       # source page XML → target page XML: strip IDs, remap styles, headings (pure)
├── verify.py            # text extraction + comparison (pure)
├── report.py            # Plan / RunReport → JSON + German Markdown
├── runner.py            # apply: pass 1 write, pass 2 links, verification, retries
└── onenote/
    ├── gateway.py       # OneNoteGateway (comtypes) – the only module importing comtypes
    └── fake.py          # FakeGateway for tests

tests/
├── fixtures/            # synthetic hierarchy + page XML (no real notes)
├── unit/                # one test module per pure module above
└── integration/         # @pytest.mark.onenote – throwaway notebook end to end

runs/                    # per-run plan/report output (git-ignored)
```

**Structure Decision**: A single project using the `src/` layout. The tool has no external API, UI or service; its only interface is the command line in [contracts/cli.md](contracts/cli.md). Splitting the code into pure modules plus one COM gateway is what constitution principle V asks for, without adding more layers. The `runs/` folder is git-ignored because plans and reports contain note titles and link text.

## Complexity Tracking

No constitution violations, so nothing to justify.

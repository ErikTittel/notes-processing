# Report: notes-processing

Snapshot of `main` as of 2026-11-08, based on `git ls-files`.

## Size

| Category | Files | Lines |
|---|---|---|
| **Application code** (`src/notes_processing`, Python) | 18 | 3,096 (2,609 without blanks and comments) |
| **Tests** (`tests/`, Python) | 30 | 2,488 (1,992 without blanks and comments) |
| Spec Kit scaffold scripts (`.specify`, Python) | – | 1,844 |
| Spec Kit scaffold scripts (PowerShell) | 6 | 1,585 |
| Markdown (specs, skills, templates) | 24 | 4,256 |
| XML, JSON, TOML, YAML | – | about 360 (176 XML, 187 JSON/TOML/YAML) |
| **Total tracked** | about 110 | about 13,800 |

The project-specific code is about **5,600 lines** of Python (3,096 application plus 2,488 tests). Most of the rest is Spec Kit tooling and documentation.

## Languages

- **Python** is the only language for the actual product. It uses `uv` and `pyproject.toml`.
- **PowerShell** is used only in the Spec Kit helper scripts.
- **Markdown** holds the specs and skill definitions.
- **XML** appears as test fixtures.

## Code shape

- The application has 18 modules, 156 functions and 41 classes. The largest are `runner.py` (443 lines), `pagebuilder.py` (293), `report.py` (285), `planner.py` (274), `model.py` (268) and `cli.py` (258).
- There are 130 test functions. Tests are about 80% of the application's size, so the test-to-code ratio is about 0.8 to 1.
- The OneNote gateway has a `fake.py` (251 lines), so most tests run without OneNote. There are separate `unit` and `integration` suites.
- The workflow is plan, then apply, then verify, for merging OneNote sections into pages.

## Process and history

- There are 14 commits from one author over **2 days** (2026-11-07 and 2026-11-08).
- The work followed a spec-driven flow: one feature (`001-merge-sections-to-pages`) with a spec, plan, research, data model, contracts, quickstart and 71 tasks. 62 of them are checked off.
- Total churn is about 13.9k lines added and 131 deleted. The low deletion count is expected for a new project.
- Two PRs were merged, and each was followed by "converge" fix commits based on real OneNote test runs.

## Human effort estimate

These are rough estimates for an experienced developer. Windows COM/OneNote interop is slow and fiddly to build and debug.

| Work | Basis | Hours |
|---|---|---|
| Application code (design, implementation, debugging) | about 2,600 logical lines at about 15–20 lines/hour | 130–175 |
| Tests (130 tests, fixtures, fake gateway) | about 2,000 lines at about 30 lines/hour | 55–75 |
| Specs, plan, research, data model, contracts | about 1,500 lines of real content | 25–40 |
| Manual validation against real notebooks and fix rounds | – | 15–25 |
| **Total** | | **about 225–315 hours** |

That is about **6–8 working weeks** for one person, or roughly 280 hours as a midpoint. The Spec Kit scaffold (about 3.4k lines of PowerShell and Python, plus the skill files) is excluded because it is generated tooling.

The repo's timestamps cover about 18 hours of elapsed time over two days, which is a large speed-up.

## Lessons learned

- **The specs are larger than the source code.** The Markdown files for specs, skills and templates (4,256 lines) are longer than the application code (3,096 lines).
- **Knowing the programming language is not required, but understanding the setup and technology is.** You don't need to read or write Python, but you do need to understand the tooling, the runtime and the technology involved (here, `uv`, Windows COM and the OneNote API).
- **The size of the context window no longer matters.** All relevant information is in the specs, so each step can start fresh from them instead of relying on what is left in the conversation.
- **Spec Kit enforces a clean software development lifecycle:**

| Step | Purpose |
|---|---|
| Constitution | Guiding principles |
| Specify | Specifications and requirements (what and why) |
| Clarify | Later additions and clarifications to the requirements |
| Plan | Technical setup and implementation details (how) |
| Checklist | Checks whether the spec is complete, like unit tests for your requirements |
| Tasks | Actionable task list |
| Analyze | Checks consistency between spec, plan and tasks |
| Implement (test first) | Executes the tasks |
| Converge | Checks the implementation and whether all tasks are finished |

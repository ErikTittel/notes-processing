# Command-Line Contract: `notes-processing`

The tool is used only through this command line. It's installed in the project environment by uv and started with `uv run notes-processing …`. Messages are in German, the user's language; options and file formats are in English.

## `plan`: build and save a plan (read-only)

```text
notes-processing plan --source NOTEBOOK --target NAME
                      [--group GROUP [--section SECTION] | --exclude-group GROUP ...]
                      [--target-folder PATH] [--out DIR]
```

| Option | Required | Meaning |
|--------|----------|---------|
| `--source` | yes | name of the open source notebook, for example `OneNote-Test` |
| `--target` | yes | name of the new target notebook. It must not exist yet: no open notebook with this name, and neither a folder `<target-folder>\<name>` nor a OneDrive shortcut `<target-folder>\<name>.url`. |
| `--group` | no | limit the run to one section group |
| `--section` | no | limit it to one section of `--group` |
| `--exclude-group` | no | leave this section group out of a whole-notebook run. It can be given more than once and can't be combined with `--group`. The name must exist. It is stored in `plan.json` (`scope.exclude`), so `apply` rebuilds the same plan. |
| `--target-folder` | no | folder for the new notebook. The default is OneNote's default notebook folder. |
| `--out` | no | run folder. The default is `runs/<YYYYMMDD-HHMMSS>/`. |

**Effects**: It only reads from OneNote. It writes `plan.json` and `plan.md` to the run folder and prints a short summary: counts, plus the number of title corrections, links and attention items.

**Exit codes**:

| Code | Meaning |
|------|---------|
| 0 | plan written |
| 2 | wrong arguments, or the source, group, section or excluded group isn't found |
| 3 | the target already exists: a notebook with that name is open, or the target folder or its `.url` shortcut exists |
| 4 | OneNote isn't available |

## `apply`: carry out a reviewed plan

```text
notes-processing apply --plan runs/<id>/plan.json [--yes]
```

**Behaviour**:
1. Re-reads the source and builds the plan again. If the fingerprint differs from `plan.json`, it stops with exit code 5 and changes nothing.
2. Prints the summary and asks `Plan ausführen? Zum Bestätigen "ja" eingeben:`. Any other answer ends the run with exit code 6 and nothing is written. `--yes` skips the question, for use in integration tests only.
3. Creates the target notebook, sections and pages (pass 1), updates links (pass 2), verifies, and shows progress per section.
4. Writes `report.json` and `report.md` to the run folder.

**Exit codes**:

| Code | Meaning |
|------|---------|
| 0 | all pages verified |
| 1 | finished, but some items failed, were incomplete or didn't pass verification (see the report) |
| 3 | the target already exists (same check as for `plan`, repeated because time may have passed) |
| 4 | OneNote isn't available |
| 5 | the source changed since the plan was made |
| 6 | not confirmed |

**Guarantees**: The source notebook is never written to. Every write goes to an object inside the target notebook created by this run, and the gateway enforces this.

## `verify`: check a finished run again

```text
notes-processing verify --report runs/<id>/report.json
```

Re-reads the source and target pages and runs the check from FR-011 again, then writes `verify.md`. It is read-only. Exit code 0 means everything matches. Exit code 1 means there are differences.

## File formats

- **`plan.json` and `report.json`**: UTF-8 JSON that follows [data-model.md](../data-model.md) (`Plan` and `RunReport`), with sorted keys and 2-space indentation. Both contain `"format_version": 1`.
- **`plan.md` and `report.md`**: German Markdown for reading, with these sections:
  - Übersicht (counts)
  - Struktur (group to section, section to page, with source page counts)
  - Titelkorrekturen
  - Links
  - Hinweise (attention items)
  - in reports also: Ergebnis, Prüfung

## OneNote gateway (internal boundary)

Every COM call goes through one class, `OneNoteGateway` (`src/notes_processing/onenote/gateway.py`). Its read methods are `hierarchy`, `page_xml`, `link_to` and `special_folder`. Its write methods are `create_notebook`, `create_section`, `create_page` and `update_page`. The write methods refuse any ID outside the target notebook recorded at `create_notebook`. Tests use `FakeGateway`, which has the same interface and works on in-memory XML.

**Test helpers**: Two more write capabilities exist only to build throwaway source notebooks for the integration tests. They are `create_section_group(name)` and the optional `parent_id` of `create_section(name, parent_id=None)`, which places a section inside such a group. The tool itself never calls them: `apply` creates only sections directly in the target notebook. They are covered by the same guard, so they work only inside a notebook created by that gateway instance, never in the source notebook. `FakeGateway` mirrors them so the guard can be unit-tested.

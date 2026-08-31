# The workbook contract — what a project adapter must declare

The adapter (`sttm-adapter.md`, kept WITH the project, not in this skill) is
the single file that binds the generic method to one engagement's workbook.
Write it once at engagement start; update it whenever structure changes.
Everything the method needs to know about the project belongs here, so that
no session ever hardcodes a column letter or a reviewer name from memory.

## Template (copy and fill)

```markdown
# STTM Adapter — <project / module>
Updated: <yyyy-mm-dd>   Owner: <user>

## Workbook
- Path: <absolute path>
- Format: xlsx | xlsm (form controls? VBA? -> editing constraints below)
- Header row: <n>   Data rows: <first>–<headroom>
- Sheets in scope: <list>   Out of scope: <dashboards, indexes...>
- Structural invariants: frozen panes, banner rows, autofilter range,
  hidden columns that must STAY hidden, merged group banners.

## Column map (semantic role -> column letter/header)
| Role | Column | Header | Notes |
|---|---|---|---|
| target-field-id | ... | ... | stable within sheet only? |
| global-key | ... | ... | <sheet>-<field-id> |
| row-kind | ... | ... | vocabulary + who sets it |
| target-name / -type / -lov ... | ... | ... | |
| base-pick (this pass' output) | ... | ... | |
| mapping-type | ... | ... | e.g. Direct / Join-Decode / Derived |
| join-decode-path | ... | ... | |
| extraction-condition | ... | ... | |
| evidence-state | ... | ... | vocabulary below |
| confidence | ... | ... | vocabulary below |
| helper columns | ... | ... | reason / rationale / questions / transformation / quality |
| sample-value, trace-source, recon-status | ... | ... | |

## Human-owned READ-ONLY columns
<list every reviewer/SME column, by header — these are never written>

## Vocabularies
- Evidence states: <ordered list + meaning + colour if CF-coded>
- Confidence: <levels + N/A token + grading caps (entity-resolution caps,
  unexercised-join caps, single-sample caps)>
- Row kinds: <values + who assigns>
- Mapping types: <values>

## Evidence sources (with paths)
- Ground-truth extracts: <TSVs and how to rebuild them>
- Trace / captured values: <workbooks, key sheets>
- DDL / views: <files>   ERD: <files>   Data dictionary: <file>
- Reference/LoV data available vs still-requested: <status>
- Cross-module sources: <e.g. person/company traces>

## Editing constraints
- Tooling: COM-only? openpyxl allowed? (macro/form-control workbooks are
  ALWAYS COM-only)
- Locking: who else edits the file; lock-check before writes
- Backup location & naming
- Post-write integrity checks: <e.g. control count, macro module, charts,
  dashboard KPI reconciliation>

## Formatting conventions
- List cells (LoV values...): bullet-per-line? RTL columns?
- Row autofit caps; zebra banding; section banner style
- Number/date formats that must be preserved

## Engagement log pointers
- Playbook file: <path>  (validation appendices live there)
- Exemplar sheet: <the finished sheet new sheets must match>
```

## Mirror inheritance of human columns

When the cross-module reuse pass (SKILL Phase B) marks a new-sheet field as a
Mirror of an already-mapped source row, the source's **human reviewer columns**
(the SME picks/notes) are inherited into the mirror — a faithful mirror carries
the reviewer's judgment about the field, since that judgment is about the field,
not the screen it appears on. This is the ONE sanctioned way to write human
columns without per-cell sign-off, and it is safe only under strict guards:

- **Fill empty cells only.** If the target human cell already holds a value,
  leave it — a reviewer may have deliberately entered something different for
  this instance. Never overwrite.
- **Respect formulas.** If the target cell holds a formula (e.g. an
  auto-derived confidence), leave it — filling the upstream pick lets the
  formula recompute naturally; writing a literal would break the derivation.
- **Copy the source's literal value** (not a reference) into the empty cell.
- **Prove it after.** Snapshot every target human cell before the write; after,
  assert that no previously-non-empty cell changed. A single violation means
  abort/rollback — human data is the one thing you cannot cheaply reconstruct.
- Log any case where the target already differed from the source (kept
  untouched) as a finding for the reviewer.

Everywhere else, human columns stay strictly read-only (non-negotiable #1).

## Rules about the adapter

- **The adapter is data, not prose** — keep entries short and exact; a new
  session should be able to act on it without re-deriving anything.
- If the workbook structure drifts from the adapter (inserted columns,
  renamed headers), STOP and reconcile the adapter first; column-letter
  references elsewhere (dashboards, scripts) usually need the same update.
- The exemplar sheet named in the adapter is the definition of "done" for
  every other sheet: structure parity (visible/hidden columns, widths, CF,
  DV) is checked against IT, not against memory.

# Formatting and verification — shared reference

Owned by the `excel-editing` skill and citable from anywhere (other skills, project
adapters, build scripts). Four topics: **sizing**, **format by rule**, **numeric
read-back**, and **why not a screenshot**.

## 1. Column widths and row heights

Order matters: **columns first, then rows**, because heights are computed from the
final widths.

**Width from the content, targeting the typical cell on ONE line.** Use a
percentile (p90), not the maximum, so one enormous cell cannot force an absurd
width; clamp to `[9, 60]`. Target *one line, not a filled block* — sizing a column
to fill four lines collapses a 40-character identifier into a 9-wide column
showing four lines, which is the same mistake in the other direction.

**Height from the wrapped-line count, with a per-cell cap.** The bug to avoid is
`max()` over the raw wrapped-line count of every cell in the row: one 1,700-character
note in a 46-wide column demands ~30 lines and pins the row to its ceiling. Cap how
many lines any *single* cell may contribute (4 is a good default) so no outlier can
tower the row. Genuine payload columns (a generated SQL query) opt out explicitly.
Long outliers **clip, and that is correct** — the full value is still in the cell.

**Quantize every height to the device-pixel grid.** Excel stores row height in
points but paints on pixels: 1 px = 0.75 pt at 96 DPI. An off-grid height is snapped
when drawn, the error accumulates down the sheet, and Excel's painted grid drifts
from its hit-test model — a click selects a cell one or two rows away, worse the
further you scroll. Uniform heights hide this; **variable heights make it visible**.
Snap every height to a 0.75 multiple, including one-off title and header rows. The
same reasoning wants zoom at 100%: below that, no 0.75 multiple is a whole pixel.

**Do not re-implement the line maths.** A project that already has calibrated
helpers (a `wrapped_lines` / `quantize` / `fit_columns` / `fit_rows` set, typically
in a shared `style.py`) owns the constants for its own font size — import them and
pass per-workbook metrics as arguments rather than editing the module-level
calibration, which every other workbook depends on.

**Applying them to a fragile workbook:** compute with those helpers, but *apply*
through the zip patcher (`set_col_width`, `set_row_heights`). The helpers are
openpyxl-based, and saving through openpyxl is what drops the parts it does not
model. Compute in one library, write in another — that is allowed and often correct.

**Hidden columns:** measure only the VISIBLE set. A hidden cell's long text
otherwise inflates the row and the reader sees a tall empty row with no visible cause.

**Spilled title text** (`wrap_text=False` on a title row, letting it flow across
empty cells) is clipped at a **frozen-pane boundary**: a sheet frozen at `G4` spills
across A–F only, however many columns follow. Measure spill room as the columns
*before* the split. Anything written to the right of the text stops the spill, so a
back-link belongs in the last column.

## 2. Format by rule, never per cell

A conditional-formatting rule is **one `dxf` record**. Per-cell formatting mints a
style record per distinct format touched and costs a COM round-trip per cell.

Measured on the same 6,811 cells (139 rows × 49 columns):

| Approach | Time | New style records |
|---|---|---|
| One `cfRule` + one `dxf` via zip patch | **0.21s** | 0 `cellXfs`, +1 `dxf` |
| `Range.Font.Color` over 10 block ranges (COM) | 1.2–1.8s | +25 `cellXfs` |
| Per-cell `Cells(r,c).Font.Color` (COM) | **96s** | +36 `cellXfs` |

Three reasons beyond speed:

1. **A rule survives a re-sort.** Cell styles move with their cells, so a "grey
   these rows" job done as cell fonts is wrong the moment the sheet is re-sorted;
   an expression rule re-evaluates.
2. **It is reversible.** One `drop_rules(dxf_id)` call undoes it. Un-restyling
   thousands of cells means reconstructing what each one looked like before.
3. **It keeps the style table still.** Where a workbook has modern in-cell
   controls, the checkbox binding lives *in* `cellXfs` (an `xf` → `xfComplement`
   → `featurePropertyBag` chain). Churning that table is not a neutral act.

**A `dxf` fill draws from `bgColor`**, the reverse of a normal cell fill. Setting
only `fgColor` — which the ordinary `PatternFill("solid", fgColor=…)` helper does —
produces a rule whose font colour applies and whose fill silently never draws. Set
both, and verify a fill by reading `cell.DisplayFormat.Interior.Color` through COM
on a cell whose value triggers the rule. Reading the rule definitions back proves
only that you wrote what you wrote.

**Priority:** give an added rule a high number (100) so the workbook's existing
rules keep winning on their own cells.

## 3. Verify numerically, from disk

- **Read back from the file on disk, not from the writing session.** An in-session
  read-back returned the new value from a save that had written nothing at all.
- **Diff against the pre-edit backup keyed on a stable id**, not on row position:
  any sort or insert makes position-keyed comparison meaningless.
- **Reconcile counts** that must not change — rows, control-bound cells, CF blocks,
  validations, merged ranges, chart parts — and be able to say why any that moved did.
- **Enumerable facts get their own column**, not an in-cell annotation: a count you
  can `COUNTIF` is verifiable, a sentence inside a cell is not.
- **Assert the invariant, not the sample.** After a sort, assert the key column
  reads `0..n-1`; spot-checking three rows passes on a block rotated by one row.
- A read-back audit is also the only reliable catch for a **dropped write**: a
  transient `RPC_E_CALL_REJECTED` can lose exactly one cell mid-loop while
  everything around it lands.

## 4. Confirm by opening in Excel, never by a screenshot

A screenshot proves that pixels were painted; it cannot prove the file is sound.
It cannot show a repair-on-open, a formula that lost its cached value, a dropped
part, or a value that reads `3.3` where `"3.30"` was intended. It is also not
reviewable — nobody can re-run it.

Ask Excel itself, mechanically (`evals/open_check.py`): open the file in a
**hidden** instance with `DisplayAlerts = True` and `CorruptLoad = 0`. A file Excel
dislikes is then either refused outright (the Open call raises) or blocks on a
prompt it cannot display, which a subprocess timeout catches. Both are machine
signals, no dialog and no human in the loop. Validated both ways: a good workbook
returns in ~2s; the same workbook with one out-of-order cell element made
`Workbooks.Open` raise.

When a human genuinely must look at rendering, say what to look at and why — but
the *pass/fail* belongs to a numeric check.

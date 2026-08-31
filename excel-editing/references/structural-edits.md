# Structural edits — why COM, and how

A structural edit is one that moves cells: inserting, deleting or moving rows and
columns, and sorting. These are the only common edits the zip patcher will not do,
so the boundary is worth stating precisely rather than as a preference.

## Can a column insert be done by zip patch? No — and here is the size of it

The question was tested by census: inserting **one** column at H into a real
mapping sheet (`EM01`, A1:AZ400, in a macro-enabled workbook with charts, form
controls, CF and validations) requires rewriting:

| Count | What |
|---|---|
| 12,062 | `<c r="…">` cell references on the sheet |
| 1,004 | formulas on the sheet — **184 of them shared or array**, whose `ref` range *and* R1C1-relative bodies both shift |
| 1,402 | references to `'EM01'!` from **other sheets** (a dashboard, a summary, chart caches) |
| 400 | `<row spans="a:b">` hints |
| 52 | `<cols>` entries, including 14 hidden-column ranges that must stay attached to their columns |
| 13 | `cfRule` formulas inside 3 `conditionalFormatting` blocks |
| 7 | `dataValidation` sqrefs, plus their `formula1` bodies |
| 1 each | `mergeCell`, `autoFilter` ref, `dimension` |
| 5 | pane / selection references |

≈15,000 references across **9 parts**, for one column. And the count is not the
real objection — the *unboundedness* is:

- **Formulas need a real parser.** Sheet-qualified refs, `$` anchoring, ranges,
  R1C1 shared-formula bodies, structured table references, defined names, and
  strings that merely look like references (`"A1:B2"` inside a `TEXT()` call) must
  all be distinguished. A regex over `[A-Z]+\d+` corrupts string literals.
- **Some references cannot be adjusted at all.** `INDIRECT("H" & ROW())` and
  `OFFSET(...)` compute their target at calculation time. Excel does not fix these
  either — but Excel *tells you* nothing was fixed, whereas a hand-rolled patch
  leaves a silently wrong workbook.
- **The tail is long and grows:** drawing/chart anchors (`xdr:from/col`), comment
  and VML anchors, pivot cache source refs, table (`ListObject`) refs and column
  ids, defined names including print areas and print titles, `x14`/`xm` extension
  sqrefs for data bars and sparklines, `ignoredErrors`, `protectedRange`, custom
  views, row/col breaks, and `calcChain.xml`.
- **VBA is opaque.** A `Range("H5")` literal inside a macro is not adjusted by
  *anything*, Excel included. After a structural edit on an `.xlsm`, grep the VBA
  for hard-coded addresses yourself.

**Verdict: do not hand-roll it. Nobody should retry this.** Excel does the whole
job in one call, and the eval proves it: CF ranges, 7 validation ranges, the merge,
the autofilter, 14 hidden columns and the cross-sheet formulas all shifted
correctly, macros/charts/form-controls intact, and Excel reopens the file with no
repair prompt — in **8.2s wall, including launching Excel**. There is no efficiency
argument for the risk.

`calcChain.xml` is the one exception worth knowing: it is a cache, and deleting the
part (with its `[Content_Types]` override and relationship) is safe — Excel rebuilds
it. That is why an openpyxl round-trip losing it is benign.

## The COM recipe

```python
import sys; sys.path.insert(0, "scripts")
import xl_com

with xl_com.Excel() as app:                      # private, hidden, always cleaned up
    wb = xl_com.open_book(app, "book.xlsm")      # RAISES if it came back read-only
    ws = wb.Worksheets("EM01")
    xl_com.insert_column(ws, "H")
    xl_com.save_copy_replace(wb, "book.xlsm")    # SaveCopyAs + os.replace, never Save
```

Non-obvious pieces, each of which is load-bearing:

- **`DispatchEx`, never `Dispatch`.** `Dispatch` attaches to a running Excel, and
  quitting it closes the user's own workbooks.
- **Record the pid** (`GetWindowThreadProcessId(app.Hwnd)`) so a refused `Quit` can
  be resolved by killing exactly that process. Never `taskkill /IM EXCEL.EXE`.
- **`AutomationSecurity = 3`** (force-disable) so opening an `.xlsm` cannot run its
  macros. The VBA project is still preserved on save.
- **`Notify=False`** on Open, so a locked file fails fast instead of queueing a
  notification.
- Set `DisplayAlerts=False`, `EnableEvents=False`, `ScreenUpdating=False`,
  `AskToUpdateLinks=False` — but understand that `DisplayAlerts=False` converts
  *some* problems into silence rather than solving them (see
  `save-investigation.md`).
- **Bulk I/O as 2-D `Value2` arrays** where you can: per-cell COM calls cost ~14 ms
  each. But **read back after any bulk write** — assigning a Python list to
  `Range.Value` has silently written nothing.

## Sorting

```python
xl_com.sort_range(ws, "A5:AW583", key="AX5")     # SortFields form + heights kept
assert [ws.Cells(r, 50).Value for r in range(5, 10)] == [0, 1, 2, 3, 4]
```

- **Use the `ws.Sort.SortFields.Add(...)` + `SetRange` + `Apply` form.**
  `Range.Sort(Key1=…)`, the legacy form, has been observed to **rotate a block by
  one row instead of sorting it** — which spot-checking a few rows does not catch.
- **Always assert the key column reads `0..n-1` afterwards.** That is the check that
  catches a rotation.
- **Row heights do not travel with a sort.** Excel moves values and formats, not row
  geometry. Capture heights before, re-apply them permuted after
  (`sort_range(keep_row_heights=True)` does this).
- Sort a **scratch rank column** built from the keys you care about, rather than
  multi-key sorting on business columns; then verify the rank column is a
  1:1 join against its source before trusting the result.

## After any structural edit

1. Re-run the preflight (`xl_probe.py`) and diff the part list against the backup.
2. Snapshot the numbers that must not move (dashboard KPIs, state counts) *before*,
   recompute after, and reconcile — identical unless the edit legitimately changed
   them, and then you must be able to say why.
3. Open it in Excel mechanically (`evals/open_check.py`) — a structural edit is the
   most likely of all edits to produce a repair prompt.
4. Update the project's column map and any scripts holding column letters in the
   same change. A column insert invalidates every hard-coded letter downstream.

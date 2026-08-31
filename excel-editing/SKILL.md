---
name: excel-editing
description: >-
  Safely and quickly edit an EXISTING Excel workbook (.xlsx/.xlsm/.xltx) on
  Windows, choosing a writer that will not silently destroy what the file already
  contains. Use when changing a workbook you did not create: filling or repairing
  cells, greying or highlighting rows, setting column widths or row heights,
  adding conditional formats, inserting/deleting/moving columns or rows, sorting,
  or fixing values in a file that has macros, in-cell checkboxes, charts, pivots,
  validations or conditional formatting. Covers writer dispatch (OOXML zip patch
  vs Excel COM vs openpyxl), a preflight that proves what a round-trip would
  destroy, numeric read-back verification, and timestamped backups. NOT for
  creating a new spreadsheet from scratch — the `xlsx` skill owns creation.
---

# Editing an existing Excel workbook

**Creating a new file? Use the `xlsx` skill. Touching a file you did not create?
Stay here.** Editing is a different problem from creation: it is about
*preservation* and *writer dispatch* — what you might silently destroy, and which
of three writers is allowed to touch this particular file. Creation has neither
problem.

> **The generic path destroys in-cell checkbox controls on Windows.** The `xlsx`
> skill prescribes openpyxl for edits (plus a LibreOffice rewrite to recalculate).
> Measured on a real workbook: an openpyxl round-trip deletes
> `xl/featurePropertyBag/` and takes **1,156 control-bound cells to 0**, with no
> error. Never send a workbook containing cell controls down that path. (The
> LibreOffice half is untested here — no `soffice` on this host — but it is a
> second full rewrite by another engine; assume it is no safer.)

## Decide first — three lines

| You want to | Use | Because |
|---|---|---|
| **Read** anything | `openpyxl.load_workbook(p, read_only=True)` | 0.2s, no Excel process. Never read through COM. |
| **Write** values, text, fonts, fills, widths, heights, CF rules | **zip patch** — `scripts/xlsx_patch.py` | Parts you don't touch are copied byte-for-byte, so macros and unknown features survive *by construction*. <1s. |
| **Restructure** — insert/delete/move rows or columns, sort, autofilter, autofit, recalculate | **Excel COM** — `scripts/xl_com.py` | One column insert moves ~15,000 references across 9 parts. Excel does it correctly; nothing else does. |

openpyxl **writes** only when the preflight reports nothing fragile *and* the user
has accepted the losses it names. It is not the default and it is not neutral.

## Preflight — before the first edit, every time

```bash
py scripts/xl_probe.py "book.xlsx" --roundtrip
```

Lists the zip parts, grades each fragile feature FATAL/SERIOUS/MINOR, counts
CF blocks, validations, merges, formulas and control-bound cells, and prints the
writer that implies. `--roundtrip` load-and-saves a **temp copy** through openpyxl
and diffs the part list, so you get a measured answer for this file and this
library version instead of a guess. Exit 1 means *openpyxl must not write here*.

Two things the part-list diff cannot see, so check them another way: chart
formatting and control *linkage* degrade with the part list unchanged.

**`data_only=True` reads a formula cell as `None` until Excel has opened and
saved the file.** openpyxl returns the *cached* result, and a workbook your
script just generated has no cache — nothing has calculated it yet. The trap is
verification: diff a freshly built workbook against an older copy that Excel
*has* opened, and every formula cell reads as data that "disappeared". One run
produced 16 phantom data-loss findings this way, all on cells holding a
perfectly good `=IF($I$330="","",$I$330)` inheritance reference. Two rules:

- Before calling anything blank, re-read with `data_only=False`. A value
  starting with `=` means the cell is fine and your reader is wrong.
- To verify *computed* values, open through COM, `CalculateFullRebuild()`, then
  read — see the verification section. Comparing two workbooks on formula cells
  is only meaningful when both have been calculated.

## Hard rules

**Dispatch**
- A modern in-cell checkbox is a **cell-format extension** (`xf` → `xfComplement`
  → `xl/featurePropertyBag/`), not a shape. openpyxl drops that part with no error
  and no warning. Because the binding lives in the style table, mass per-cell
  restyling is a hazard on such a file too, not just slow.
- `.xlsm` needs `keep_vba=True` even to read-and-save; prefer not saving it with
  openpyxl at all.
- **Get the COM object with `EnsureModule` + `DispatchEx`. Both halves, and each
  one alone fails silently in its own way.**
  - `DispatchEx` alone is late-bound — no type library, so **named arguments do
    not bind and nothing warns you**. `Worksheet.Copy(After=last)` put the sheet in
    a brand-new workbook; `Worksheets.Add(After=last)` put it *first*. Positional
    `Copy(pythoncom.Missing, last)` failed the same way.
  - `gencache.EnsureDispatch` — the usual way to get early binding — uses Dispatch
    semantics and **attaches to a RUNNING Excel**, i.e. the user's. A cleanup loop
    over `app.Workbooks` then closed their open file and quit their session,
    discarding unsaved work.

  ```python
  win32.gencache.EnsureModule("{00020813-0000-0000-C000-000000000046}", 0, 1, 9)
  app = win32.DispatchEx("Excel.Application")   # early-bound AND private
  assert not app.Workbooks.Count                # a fresh instance owns nothing
  ```
  Never iterate `app.Workbooks` to clean up — close only the handles you opened.
  The assert is the backstop: anything already open means you are not alone in
  there. And after any named-arg call whose mis-binding would be silent, **assert
  the result** (`sheetnames[-1] == expected`).

**Writing**
- **Format by rule, never per cell.** One `cfRule` + one `dxf` over 6,811 cells:
  **0.21s**. The same cells restyled individually: **96s**, and the rule survives
  a re-sort while cell styles do not.
- A `dxf` fill draws from **`bgColor`**, the reverse of a normal cell fill. Set
  only `fgColor` and the rule applies its font colour and no fill at all, silently.
  Use `dxf_fill()`, which sets both.
- **A `cfRule` formula is anchored at the top-left of its `sqref` and re-evaluated
  per cell, so every column reference you did not mean to move needs `$`.** Writing
  `E4="x"` to colour whole rows over `A4:AW651` tests `E4` in column A, `F4` in B,
  `G4` in C … — 48 of 49 columns read the wrong cell, and the sheet still *looks*
  plausible because something gets coloured. `$E4` pins the column and lets the row
  travel, which is what "by this row's value" means. Same trap in the other
  direction for a per-column rule (`E$4`).
- **A new rule must not outrank the sheet's existing ones.** Excel resolves
  competing formats by lowest `priority` number, so a row-colour rule added at
  priority 1 silently swallows the value-driven highlights already there. Check
  what the sheet uses first (`cf_blocks()`, or read the priorities) and sit below
  it — `add_rule()` defaults to 100 for this reason. Then prove it: probe
  `DisplayFormat` on one cell per DISTINCT competing value, not per cell.
- **Identifier columns go through the shared-string table** (`set_text`). A string
  cell has no numeric reading, so `"3.30"` cannot become `3.3`. Through COM onto a
  General-formatted cell, **8 of 8** test identifiers were coerced — `"1:1"` to a
  time, `"3-1"` to a date, `"0012"` to 12. `NumberFormat="@"` *before* the write
  prevents it, if you must use COM.
- **Reading, the same trap runs backwards: a small integer pasted into a
  date-formatted column reads back as a 1900 DATE.** Excel serial 1 renders as
  `1900-01-01`, 2 as `1900-01-02`. A DB export of a flag column (`RECORD_STATUS`,
  `IS_DELETED`, `IS_ACTIVE`) pasted into such a column therefore arrives as a
  datetime, and a literal `value == 1` test fails for **every** row — measured:
  all 1,560 reference values silently classified as soft-deleted, inverting the
  flag's meaning. Never compare a flag cell to a literal. Coerce first, and
  treat an uncoercible cell as "no signal" rather than as the negative case:
  ```python
  def flag(v):
      s = "" if v is None else str(v).strip()
      if not s: return None
      if s.startswith("1900-01-0"): return int(s[9:10])   # Excel serial 1..9
      try: return int(float(s))
      except ValueError: return None
  ```
  Cross-check the resulting count against the source system (`SUM(CASE WHEN
  flag=1 …)`) — a flag that silently inverts is invisible in a spot check.

**Adding a column to an existing table** — values landing is half the job; the
column is done when it is indistinguishable from the table it joined.
- **Clone the neighbour column's formats, don't style by hand.** One column-wise
  `Range("B5:B<last>").Copy` → `Range("A5").PasteSpecial(xlPasteFormats)` carries
  every per-row treatment at once — zebra bands, tint fonts on inherited rows,
  borders, banner fills — things a hand-built Font/Fill can never fully match.
  A 13-sheet pass styled this way verified at **0 mismatches over ~33k cells**;
  the hand-styled first attempt was visibly a bolted-on strip.
- **PasteSpecial(formats) overwrites `NumberFormat`** — re-apply `"@"` AFTER the
  paste or the identifier-coercion trap above reopens through the back door.
- **Inserting at column A shifts the title/banner rows right** (old A1→B1, B1→C1,
  merges move with their anchors). Re-anchor deliberately: capture the title text
  BEFORE the insert, rewrite it at A1, clear the shifted cell, and re-merge any
  full-width banner/stats row from A. **Verify the title's cell per file** —
  sibling workbooks drift (one file's title in B1, its sibling's elsewhere), and
  a capture aimed at the wrong cell writes an empty title while the real text
  survives two cells to the right.
- **COM `Range.AutoFilter` refuses ranges openpyxl happily wrote** (merged banner
  rows inside the range). If re-application fails after an insert, restore the
  filter by zip surgery — `<autoFilter>` goes BEFORE `<mergeCells>` in the sheet
  schema — then prove the file by one clean Excel open.
- **NEVER add a worksheet `autoFilter` to a sheet that carries a ListObject.**
  A ListObject owns its own `<autoFilter>` inside `xl/tables/tableN.xml`; a second
  one at sheet level over the same range is invalid OOXML, and Excel does not warn
  — it opens with *"Excel was able to open the file by repairing or removing the
  unreadable content: Removed Feature: AutoFilter … Removed Feature: Table"*, i.e.
  it deletes **both** the filter and the table. Measured: a uniform "style every
  sheet" pass over a 15-sheet reference workbook wrote a duplicate `A1:R202` filter
  onto the one sheet holding `Table1` and cost the table. Guard it:
  ```python
  if not ws.tables:                      # ListObject already provides filtering
      ws.auto_filter.ref = f"A{hdr}:{last}{ws.max_row}"
  ```
  Two follow-ons: the probe's **MINOR ListObject** grade means *"a structural edit
  must keep the table ref in step"* — treat that as a hard gate, not a footnote,
  because uniform restyling IS a structural edit here. And **verify by counting
  the parts, not by reading cells**: a duplicate-filter file round-trips through
  openpyxl looking perfect, so assert `xl/tables/tableN.xml` still exists AND that
  the owning sheet has zero `<autoFilter>` tags of its own. If a repair dialog has
  already appeared, **do not save from it** — the on-disk file is still intact
  until that save lands, so close it and restore from the pre-edit backup.

- **Freeze panes have two silent ways to kill scrolling — check both whenever a
  user says "I cannot scroll".** (1) A merged cell crossing the split: a banner
  merged `A2:G2` above a `freeze_panes = "B5"` vertical split straddles the
  frozen-column boundary and glitches scrolling — freeze rows only (`A5`) when
  full-width banners exist. (2) A frozen pane taller than the window: freezing
  at `A19` above a paste area is useless if the 18 frozen rows include a 300pt
  SQL cell — the frozen stack exceeds the window, the scrollable pane below
  collapses to nothing, and rows inside the frozen pane below the fold are
  UNREACHABLE (frozen panes never scroll). Sum the frozen rows' heights; keep
  the stack well under ~400pt at 100% zoom, capping payload cells (a query cell
  is COPIED, not read — 60pt is plenty).
- **Uniform tall row heights read as EMPTY rows.** Setting every row of a log to
  one generous height (62pt "so the long ones fit") renders the short entries as
  blank bands the user asks to have "deleted". Fit heights per row from wrapped
  content with a per-cell line cap (`common/style.py fit_rows` pattern: ≤4
  lines, capped) — long cells clip to the cap, short rows shrink, and nothing
  looks empty.

**Replicating one sheet's styling onto another** — parity includes VISIBILITY,
not just fills and fonts. Carry `column_dimensions[].hidden` (and widths, outline
levels, frozen panes) with the styles: a hidden helper column that turns visible
in the copy reads as a regression to the reader, exactly like a lost fill. The
same goes for row heights and the filter range — replicate the VIEW, not only
the paint.

**Formulas that other cells inherit from** (mirror / echo cells)
- **Never write a target cell that holds a formula.** It is a reference, and a
  literal over it severs the inheritance silently — the value looks right and the
  next edit to the anchor stops propagating. Read the target *without* `data_only`
  so a formula shows as one, and skip it. Anchor-only writes are sufficient: on one
  workbook 17 anchor writes carried 108 edits via 1,998 mirrors.
- **A bare reference to an EMPTY cell renders `0`, not blank.** `='S'!$A$1` shows
  `0`; `=IF('S'!$A$1="","",'S'!$A$1)` shows blank. Measured: **1,079 spurious
  zeros** in six mirror columns of one workbook, two of them hidden so nobody saw
  it. Rewrite every mirror column, not just today's offenders.
- **That `0` launders into derived copies as a hard LITERAL** when a generator
  reads cached values — 598 such literals on one pair. Clearing them is
  literals-only; a formula that merely evaluates to 0 is inheritance working.
- Details, plus the dashboard `COUNT` caveat: `references/dependents-and-mirrors.md`.

**Saving**
- **Never `Workbook.Save`.** Use `SaveCopyAs` + `os.replace` (`save_copy_replace`).
  On a workbook Excel opened read-only, `Save` **returns normally, sets
  `wb.Saved = True`, and writes nothing** — measured. `SaveCopyAs` writes the
  edits regardless, so the work either lands or fails loudly at the replace.
- `os.replace`, not `shutil.move`: move onto an existing Windows target raises
  and falls back to a copy.
- Refuse to continue if `Workbooks.Open` handed back a read-only book —
  `open_book()` raises. That check is what stops the silent discard above.
- **`Call was rejected by callee` means Excel is BUSY, not broken — retry it**
  (`com_retry`). Writing to a cell many formulas depend on can leave the *next*
  call rejected, even one as trivial as `wb.Worksheets(name)`. The damage is the
  misreading: a rejected `Close` *after* a successful `Save` escaped a `finally`
  block and made a correct run exit non-zero, which invites re-running a pass that
  already applied. Prevention: `Excel(manual_calc=True)` around write loops. And
  if a run does die mid-write, **check the target's mtime before concluding
  anything was lost.** (Backups made with `copy2` carry the *source's* mtime, so
  two backups both showing the original mtime prove no save had landed.)
- **`Open method of Workbooks class failed` is the OPPOSITE diagnosis — do NOT
  retry it.** BUSY is transient; this is a file Excel judges invalid, and retrying
  three times plus `sweep_windowless()` changes nothing (measured). The usual cause
  is a patch that turned a **formula cell into a literal**, orphaning its entry in
  `xl/calcChain.xml`. The zip passes `testzip()`, every part parses as XML, no
  process holds the file, and nothing looks wrong — Excel simply refuses.
  Diagnose by **counting**, not reading:
  ```python
  s  = z.read("xl/worksheets/sheet1.xml").decode()
  nf = len(re.findall(r"<f>", s))                                    # formula cells
  nc = len(re.findall(r"<c ", z.read("xl/calcChain.xml").decode()))  # chain entries
  ```
  Unequal ⇒ this bug (measured 152 entries vs 149 formulas after three formulas
  became literals). Fix by rewriting the zip **without** `xl/calcChain.xml`, and
  strip its `<Override>` from `[Content_Types].xml` *and* its `<Relationship>` from
  `xl/_rels/workbook.xml.rels` — leaving either dangling is its own corruption.
  Excel regenerates the part on open (verified 149/149 afterwards). This is safe for
  the same reason the probe calls calcChain loss benign: it is a cache.
  **Adding** a formula is fine — the new cell is merely absent from the chain.
  **Removing or literalising** one is not. So after any patch that blanks or
  literalises a formula cell, either drop calcChain in the same write or follow
  immediately with a COM recalc — and open the file once before calling the pass done.
- **A formula cell that keeps a stale `t` attribute is a different corruption.**
  `<c r="K336" t="s"><f>…</f></c>` claims a shared-string index it no longer has;
  Excel "repairs" that by deleting content rather than refusing. Scan for it:
  formula cells whose attributes still contain `t="s"`. A formula cell with **no**
  cached `<v>` at all is legal and expected from a patch.
- **Never `Stop-Process` an Excel started for COM.** Killing one mid-call corrupts
  the pywin32 generated cache, and every later `DispatchEx` then dies with
  `module 'win32com.gen_py.…' has no attribute 'CLSIDToClassMap'`. Recovery:
  `Remove-Item -Recurse -Force "$env:LOCALAPPDATA\Temp\gen_py"` — it rebuilds
  itself. Use `Excel()`, which sweeps only its own pid, or `sweep_windowless()`,
  which spares any Excel with a window (the user's).
- CRC-check the new zip before it replaces anything, and **retry the replace**: a
  virus scanner holds the freshly-written target for a moment (WinError 5), then
  lets go.

**Verifying**
- **Read back from DISK, not from the session.** An in-session read-back agreed
  perfectly with a save that never happened.
- **A patch cannot recalculate, so every formula that DEPENDS on a patched cell
  still holds its old cached value on disk** — mirror/echo refs, dashboard KPIs,
  chart caches. Excel refreshes them when a human opens the file, but any machine
  reader (`openpyxl data_only=True`, a downstream generator) sees the stale value
  until then. When dependents matter, follow the patch with ONE COM open →
  `CalculateFullRebuild()` → `save_copy_replace()`. Measured: 5 echo cells still
  read the pre-patch string until that pass ran.
- `Range.Value = [[...]]` (a list) has written *nothing*, silently, while scalar
  writes in the same session landed. Read back.
- After any sort, assert the key column reads `0..n-1`, and re-apply row heights —
  **heights do not travel with a sort**. Use the `ws.Sort.SortFields` form:
  `Range.Sort(Key1=...)` has rotated a block by one row instead of sorting it.
- Reconcile counts (rows, controls, CF blocks, validations) against the pre-edit
  backup, keyed on a stable id. **Never verify by screenshot** — see
  `references/formatting.md`.
- **Compare only the cells you WROTE, and print how many you excluded.** Two
  workbooks built from one mapping rarely inherit the same columns, so one value on
  an anchor can legitimately render on 25 cells in one file and 1 in the other — a
  cell-for-cell diff then reports 24 failures that are not failures. A check that
  silently skips most of the sheet reads as "everything agrees".
- **A green run against an already-synced file proves only the read and verify
  halves — it never takes the write path.** Test writes with a revertible
  sentinel: patch one anchor to a unique string, assert it reached the target
  anchor *and* its mirrors, patch it back, assert zero traces and a still-passing
  gate. Choose a column excluded from every summary metric. A converged workbook
  hid a verifier bug completely: every anchor was blank, so both files agreed
  trivially and the gate passed at "0 disagreements" while being wrong.
- **Verifying a FILE EXCEL ALREADY SAVED (a finished output, not your in-session
  edit): read static attributes with openpyxl, not COM.** Border/fill/font/numfmt/
  height are all recorded faithfully on disk once Excel has saved the file — COM
  adds nothing there but a round-trip per attribute per cell. Measured on a
  ~21,000-cell visual-parity gate: 480s over COM vs 1.6s from the file, identical
  numbers on every attribute (`references/save-investigation.md`). This does NOT
  relax the read-back-your-own-write rule two bullets up — a file Excel has
  already recalculated and saved is a different case from an in-session edit that
  may not have landed. The one thing that still needs COM is **conditional-format
  rendering** — a dxf record can look correct while painting nothing (see
  `references/formatting.md` on `bgColor` vs `fgColor`) — and even that only needs
  `DisplayFormat` probed on one row per DISTINCT value, not one per cell.

**When it is slow**
- **If an operation exceeds ~10s, STOP and time each step** with unbuffered output
  (`py -u`) before trying anything else. Three wrong theories were published about
  a "hanging save"; one instrumented run showed the cost was in a per-cell edit
  loop (**96s**) and the save was **0.2s**. Do not theorise about Excel
  performance — measure it, per step.

**Backups**
- Timestamped, into a sibling `_backups/` folder, **before every write** — never
  beside the deliverable. `Book.save()` and `save_copy_replace()` do this by
  default; don't turn it off.
- Restoring human-edited columns from a backup is the user's decision, never
  automatic: the live file may hold newer edits than any backup.

## Scripts

| File | Use |
|---|---|
| `scripts/xl_probe.py` | preflight: inventory, severity grading, writer verdict, proven round-trip loss |
| `scripts/xlsx_patch.py` | the zip patcher: values, bulk fills, blanks, widths, heights, CF rules |
| `scripts/xl_com.py` | COM: guarded open, `SaveCopyAs` persist, `com_retry` busy-retry, `recalc_and_save`, column insert, sort, autofit, windowless-zombie sweep |
| `evals/run_evals.py` | four evals against real workbooks; each reports its own wall clock |

```python
import sys; sys.path.insert(0, "scripts")
import xlsx_patch as xp
bk = xp.Book("book.xlsx"); sh = bk.sheet("Data")
sh.set_cells({f"A{r}": f"ID-{r:03d}" for r in range(5, 367)})   # 362 cells, one pass
sh.add_rule("A20:AW34 A80:AW94", xp.dxf_font("FF808080"))       # 1 rule, not N styles
bk.save()                                                        # backs up first
```

## References

- `references/formatting.md` — **shared, citable from anywhere**: column-width and
  row-height maths, format-by-rule, numeric read-back, and why "open it in Excel"
  beats a screenshot.
- `references/measurements.md` — every number in this skill, with how it was taken.
- `references/save-investigation.md` — the hung-`Workbook.Save` question: eight
  factors tested, not reproduced, and the two real failure modes found instead.
- `references/structural-edits.md` — why a column insert cannot be a zip patch
  (the reference census), and the COM recipes for insert and sort.
- `references/dependents-and-mirrors.md` — mirror/echo cells: never overwrite a
  formula, the bare-reference-renders-0 defect and its `=IF()` fix, how that 0
  launders into derived copies as a literal, what "verified" means when two
  workbooks inherit differently, and why a converged file cannot test a sync.

Anything specific to one project's workbooks — sheet names, column maps, which
file is authoritative — belongs in that project's adapter, not here. This skill
must stay true of any Excel file.

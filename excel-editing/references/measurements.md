# Measurements

Every number quoted in this skill, with how it was taken, so it can be re-measured
and disagreed with. Host: Windows 11, Excel desktop (COM), Python 3.13,
openpyxl 3.1.5, pywin32. All timings wall-clock; Excel launch (~4s) is called out
where it is included.

Test workbooks, chosen by hazard:

| Label | Shape | Hazard |
|---|---|---|
| **controls** | 408 KB, 16 zip parts, 6 sheets, data sheet `A1:AX581`, 28,374 cells | modern in-cell checkboxes (`xl/featurePropertyBag/`), 7 CF blocks / 24 rules, 12 validations, 28 hidden columns, active AutoFilter |
| **macro** | 267 KB, 46 parts, 9 sheets | `.xlsm` with VBA, 4 charts, 18 form controls, VML, 1,004 formulas on one sheet |
| **plain** | 71 KB, 32 parts, 6 sheets | no controls; customXml + printerSettings |

## Reading

| Operation | controls (408 KB) | plain (71 KB) |
|---|---|---|
| `load_workbook(p)` — full model | **0.97s** | 0.19s |
| `load_workbook(p, read_only=True)` | **0.22s** | — |
| `read_only` + full row scan of the 581-row sheet | **0.47s** | — |
| raw `zipfile` read of one sheet part | 0.004s | — |

`read_only=True` is the 0.2s figure; the full load costs 4–5× because it builds
styles, CF and validation objects. Reading the same data through COM costs an Excel
launch (~4s) before the first cell. **Read with openpyxl.**

## What each writer destroys — measured, not assumed

Round-trip = `load_workbook` then `save` on a temp copy, diffing the zip part list.

| Workbook | Time | Destroyed |
|---|---|---|
| **controls** | 2.3s | `xl/featurePropertyBag/featurePropertyBag.xml` → **1,156 control-bound cells become 0** |
| **macro** (`keep_vba=True`) | 3.4s | nothing at part level — but charts are re-generated from openpyxl's model, which a part-list diff cannot see |
| **plain** | 0.5s | 9 `customXml/*` parts, 3 `printerSettings`, 3 worksheet `_rels` |

Benign in all three: `calcChain.xml` (Excel rebuilds it) and `sharedStrings.xml`
(openpyxl 3.1.5 writes strings inline instead — no data loss, larger file; the
controls workbook grew 408 KB → 547 KB).

**Mechanism of the control loss.** A modern in-cell checkbox is not a shape. The
`xf` (cell format) carries
`<ext uri="{C7286773-470A-42A8-94C5-96B5CB345126}"><xfpb:xfComplement i="0"/></ext>`,
which resolves through `xl/featurePropertyBag/featurePropertyBag.xml`
(`<bag type="Checkbox"/>` + `XFControls` + `XFComplement` mapping). In the controls
workbook, 12 of 93 `cellXfs` entries carry that extension, and 1,156 cells reference
those 12 — exactly 578 data rows × 2 checkbox columns. Two consequences: openpyxl
drops both the part and the `xf` extension, and *any* writer that churns or
renumbers `cellXfs` is operating on the checkbox binding.

## Writing

Zip patch, controls workbook, from `Book()` to a saved file:

| Operation | Time |
|---|---|
| `Book()` load (all 16 parts into memory) | 0.07s |
| Queue 362 `set_text` writes | 0.23s |
| One CF rule over 10 sqref blocks | ~0.01s |
| `save()` — re-zip 16 parts + CRC check + backup | 0.26–0.28s |
| **362 cells + a CF rule + 2 row heights, end to end** | **1.2s** |

Two performance bugs found while building the patcher, both worth knowing because
the naive form of each is what you would write first:

- Rewriting `sharedStrings.xml` per new string turned 362 writes into **4.4s**.
  Buffer the appends and write the part once → 0.23s.
- `x = x[:a] + el + x[b:]` in a loop copies the whole part per edit — 362 cells in a
  1.5 MB sheet is half a gigabyte of copying, and it is the difference between
  **0.28s and 1.9s**. Splice all edits in one pass.

## Formatting: rule vs per cell

Identical target: 6,811 cells (139 rows × 49 columns, 10 scattered blocks).

| Approach | Edit time | `cellXfs` | `dxfs` |
|---|---|---|---|
| One `cfRule` + one `dxf` (zip patch) | **0.21s** | 93 → 93 | 41 → 42 |
| `Range.Font.Color` over 10 blocks (COM) | 1.2–1.8s | 93 → **118** | — |
| Per-cell `Cells(r,c).Font.Color` (COM) | **96s** | 93 → **129** | — |

≈14 ms per COM round-trip. Note the style-record counts: the previously published
figure of "~6,800 new style records" was wrong by two orders of magnitude — Excel
de-duplicates, so a sweep mints one record per *distinct* (existing format × new
colour) pair, not one per cell.

## Saving

| Operation | Time |
|---|---|
| `Workbook.Save`, 24+ calls across every factor combination | 0.20 – 1.9s, **no hang** |
| `Workbook.Save` on a **read-only-opened** workbook | 1.8s — **and writes nothing, reporting success** |
| `SaveCopyAs` (including from a read-only-opened workbook) | 0.18 – 0.21s |
| Excel launch (`DispatchEx` → usable app) | 3.6 – 4.5s |
| `Workbooks.Open`, controls workbook | 0.8 – 1.5s (4.5s when visible) |

Full factor matrix and the read-only discard transcript: `save-investigation.md`.

## Numeric coercion through COM

Written to a **General**-formatted cell via `Range.Value` (`Value2` behaves
identically), then read back in-session:

| Input | Becomes | With `NumberFormat="@"` first |
|---|---|---|
| `"3.30"` | `3.3` | `'3.30'` |
| `"1:1"` | `0.04236…` (time serial) | `'1:1'` |
| `"3-1"` | `datetime(2026, 3, 1)` | `'3-1'` |
| `"1/2"` | `datetime(2026, 1, 2)` | `'1/2'` |
| `"0012"` | `12.0` | `'0012'` |
| `"007"` | `7.0` | `'007'` |
| `"1E5"` | `100000.0` | `'1E5'` |
| `"16.10"` | `16.1` | `'16.10'` |

**8 of 8 coerced** without the guard; **8 of 8 exact** with it. A shared-string write
through the zip patcher keeps all 8 with nothing to remember, because a string cell
has no numeric reading to fall back to.

Trap when testing this: a column that is *already* `NumberFormat="@"` shows no
coercion, and a control arm run on such a column passes for the wrong reason. Force
`General` first.

## Structural edit

Column insert at H on the macro workbook's 400-row, 52-column sheet, via COM,
including Excel launch, `SaveCopyAs` and the replace: **8.2s**. Reference census of
what a hand-rolled patch would have had to rewrite (≈15,000 refs across 9 parts):
`structural-edits.md`.

## Eval suite

Against copies of the three workbooks; `py evals/run_evals.py`:

| Eval | Result | Wall |
|---|---|---|
| E1 grey 139 scattered rows by one CF rule, controls intact | PASS | **0.26s** |
| E2 fill 362 identifier cells exactly, macros intact | PASS | **0.83s** |
| E3 insert a column via COM, refs/CF/DV/macros intact, opens clean | PASS | **8.22s** |
| E4 preflight catches the openpyxl round-trip before damage | PASS | **5.22s** |
| Total (includes 4 Excel launches) | 4/4 | 44.8s |

For scale, the work these replaced took a prior session several hours.

## Sync between workbooks: patch + one recalc

A recurring reconcile of three workbooks sharing one mapping (a 1.4 MB `.xlsm` with
VBA + 20 form controls, and two `.xlsx` copies; ~390 keyed rows each). Four stages —
clean artifacts, sync, recalculate, verify — in one command.

| Stage | Time |
|---|---|
| scan a workbook for artifact cells (openpyxl, both layers) | 1.8s |
| plan both targets — read + diff, keyed on a stable id | 1.4s |
| **zip patch, 1 cell** | **0.5s** |
| **COM recalculation pass** (open + `CalculateFullRebuild` + `SaveCopyAs`) | **6–10s** |
| verify both targets from disk (openpyxl) | ~1s |
| **whole run, nothing to change** | **3.4s** |
| **whole run, one edit propagating to 24 mirrors** | **10s** |

The recalculation dominates and is irreducible — it is one Excel launch. So batch
every patch, then recalculate **once**; the patch itself is noise by comparison.
The same work done cell-by-cell over COM, with a `Workbook.Save` per file, took
minutes and produced two failure modes the patch path does not have (a busy
rejection mid-loop, and a corrupted `gen_py` cache after an orphaned Excel had to
be killed).

## Mirror-cell defects found in one workbook

| Symptom | Count |
|---|---|
| bare-reference mirrors rewritten to `=IF(ref="","",ref)` | 5,909 |
| of those, cells that had been displaying a spurious `0` | 1,079 |
| — one column, every mirror in it | 329 of 329 |
| — three more columns | 285, 262, 185 |
| new zeros introduced by a sync blanking 7 anchors | 15 |
| literal `0`s laundered into the derived copy by a generator | 598 |
| dashboard cells whose displayed value changed after the rewrite | **0** |
| false failures from comparing the two files cell-for-cell | 24 |

The dashboard row is the one to note: `=IF(...)` returns `""` where the old form
returned `0`, so `COUNT` stops counting those cells. It happened to change nothing
here — but only a before/after snapshot could establish that, which is why the
rewrite script takes one.

## Not measured here

- **LibreOffice** (`soffice`) is not installed on this host, so the generic `xlsx`
  skill's `recalc.py` step — a second full rewrite of the file by another engine —
  is **untested**. Treat it as at least as destructive as an openpyxl save until
  someone measures it.
- Excel version-to-version differences. Every COM number above is one build.

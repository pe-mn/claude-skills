---
name: erd-extraction
description: Extract a complete, machine-readable data model (tables, columns, PK/FK, relationships) from an ERD diagram PDF — especially large single-page Oracle Data Modeler exports whose text coordinates are corrupted for normal PDF readers, or whose table boxes overlap/occlude each other. Use whenever the user wants tables/columns/relationships pulled out of an ERD PDF, an ERD documented into Excel/JSON, or an existing ERD extraction completed/verified. Not for hand-drawn images or scanned (raster) diagrams — this method needs a text layer.
---

# ERD PDF extraction — coordinate-correct, occlusion-proof

Goal: turn a diagram-tool PDF export (Oracle Data Modeler and similar) into
structured JSON — every table with columns, types, PK/FK/not-null markers, key
constraints, and resolved FK relationships — without trusting a visual read.

## Why the obvious approaches fail

1. **pypdf/pdfminer text extraction gives corrupted coordinates** on these
   exports (characters fine, positions scrambled). Any grouping done on those
   coordinates silently loses tables — a prior AI pass on such a file captured
   only 127 of 489 tables. **Chrome renders them correctly**, so use pdfium
   via `pypdfium2` (same engine) for both text+coords and rendering.
2. **Visual reads miss occluded tables.** Diagrams can paint table boxes on
   top of each other; hidden boxes are invisible in ANY render but their text
   is fully present (browser Ctrl+F finds it; copy-paste extracts it). So
   completeness must come from the TEXT layer, never from screenshots.
3. **Global y-sorting merges unrelated boxes** that share a baseline on a
   huge single-page canvas. Each box is drawn as one unit, so process chars
   in **content-stream order** and break runs on baseline/x-gap changes.

Manual fallback that always works (user-verified): open the PDF in Chrome and
search with a **dot before the table name** (`.request`) — box headers render
as `SCHEMA.TABLE`, so the dot-prefixed search jumps to the table header instead
of every FK-column mention.

## Pipeline (scripts/, all take paths as arguments)

```
python scripts/extract_runs_ordered.py <erd.pdf> runs.json        # pdfium text runs, content order
python scripts/parse_boxes.py          runs.json tables.json      # boxes -> cols/markers/keys
python scripts/extract_paths.py        <erd.pdf> paths.json       # vector rects + connector lines
python scripts/resolve_relationships.py tables.json paths.json runs.json \
                                        relationships.json tables_clean.json
python scripts/render_crop.py <erd.pdf> out.png --tables A,B --data <dir>   # visual verification
```

`pip install pypdfium2` if missing. Box anatomy: header `SCHEMA.TABLE`; column
rows `P/F/U` (PK/FK/unique) + `*` (not null) + name + type; then a keys section
(`PK_X (COLS)`, `FK_X (COLS)`, `REF<PARENT><n> (COLS)`).

## Relationship resolution (resolve_relationships.py encodes all of this)

Evidence, strongest first:
1. `REF<PARENT><digits>` constraint names name the parent directly.
2. FK column name == a table's PK column name (`ORDER_ID` → `ORDERS.ORDER_ID`).
3. Constraint-name word matching — but **strip the child's own name first**
   (`FK_CREATED_BY_INVOICE_LINE` on child INVOICE_LINE must not match a
   parent "INVOICE"), and match whole words/prefix-abbreviations, never raw
   substrings (`..._PERSON_ID_FK` must beat "INVOICE" ⊂ "INVOICE_ADJUSTMENT...").
4. Connector lines: 2-point segments chained by shared endpoints (union-find),
   chain ends snapped to the nearest box border (±8pt). Chains touching >2
   boxes are crossing artifacts — DROP them, never emit all-pairs.
   Self-references are real (both ends on one box) — don't exclude parent==child.
5. Floating text runs outside every box near a line = FK constraint labels.

Connections with no FK entry: synthesize child→parent only when exactly one
direction has a matching column-vs-PK; otherwise queue for review — do not guess.

## Verify before shipping (the extraction lies in specific ways)

- **Regression:** if any earlier/partial extraction exists, diff shared tables'
  column sets — catches parser bugs (e.g. wrapped rows emitting a bare `DATE`
  "column"; parse_boxes cleans these but check).
- **Reconcile counts:** boxes found vs headers found; FK-marked columns vs FK
  key entries per table; every empty box needs an explanation.
- **Adversarial pass on non-high-confidence relationships** (fan out agents if
  many): semantic read of the constraint name, PK fit in tables_clean.json,
  and a rendered crop (`render_crop.py`) tracing the actual arrow. Crossing
  lines pass THROUGH boxes; real connectors END at a border with a crow-foot.
  An occluded table can't be visually confirmed — say so, use logic evidence.
- **Random-sample spot check, regardless of confidence:** render crops of 10
  randomly chosen SHIPPED relationships and trace the actual connector line.
  The targeted pass above never re-checks high-confidence rows, so this is
  the only guard against a systematic error hiding inside them.
- **Domain conventions resolve stubborn columns** (confirm per project, then
  encode): role-named FKs (`TENANT_ID`, `VENDOR_ID`, `SPONSOR_ID`) → the party
  master table; `CREATED_BY`/`UPDATED_BY` → the users table; coded `STATUS`
  columns → the domain/enum table.
- **Tables referenced by mappings but absent from the diagram** (app-added
  tables, other schemas) are findings to surface, not extraction failures —
  list them with their evidence source.

## Output conventions

Deliver tables.json / relationships.json as the machine truth; when the user
wants Excel, ONE workbook with single-purpose sheets — never parallel sheets
restating the same relationships in different shapes. Grade every relationship
row with confidence + evidence kind (constraint-name / PK-match / line /
label / verified-visually) so downstream consumers can filter.

Sheet contracts (the workbook deliverable spec):
- **Tables** — `Table | Module | Class | Description | # Columns | Primary
  Key | References | # Child Tables | Notes`. Module = inferred business
  area. Class from a FIXED taxonomy: lookup / master / transaction /
  junction / log / backup / config / staging. Description = ONE factual
  sentence grounded in columns + relationships; prefix `Unclear:` when
  genuinely unclear — never dress speculation as fact.
- **Columns** — `Table | Seq | Column | Data Type | Not Null | Key (PK/FK) |
  References (resolved parent TABLE.COLUMN) | Notes`.
- **Relationships** — THE single canonical FK list: `Child Table | FK
  Column(s) | Parent Table | Parent PK | FK Constraint Name | Cardinality |
  Confidence | Evidence`. Confidence rubric: **high** = two independent
  evidence kinds agree; **medium** = one strong evidence; **low** = weak or
  conflicting (state the conflict in the Evidence cell).
- **STTM Priority** (only when the user supplies a priority-table list) — a
  token-lean subset for pasting into data-mapping prompts: (A) the priority
  tables' child-side join paths, (B) their columns as `Table | Column | Type
  | Key | References` — and nothing else.
- **Aliases & Gaps** — three content types: naming aliases used by human
  reviewers; tables referenced by mappings but absent from the diagram; and
  relationship candidates REJECTED as spurious/undeterminable, each with the
  rejection reason (recording rejections prevents re-litigating the same
  lines next pass).
- **README** — provenance (source file, method, date), row counts per sheet,
  the evidence/confidence legend, known limits (occluded tables, off-diagram
  tables), a one-line purpose per sheet, and the results of the pre-delivery
  verification.

Formatting: bold navy headers, frozen header row, auto-filters, zebra
banding, monospace identifiers, confidence cells color-coded
green/amber/red — and preserve exact ERD table/column names (a correctness
rule, not cosmetics).

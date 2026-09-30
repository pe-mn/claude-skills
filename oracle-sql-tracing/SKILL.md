---
name: oracle-sql-tracing
description: >-
  Methodology for reverse-engineering an application's database via Oracle SQL
  trace (10046 / .trc files): capture app-entered values in trace binds, parse
  the trace into a field-to-column mapping workbook, reconcile against the
  values entered in the app, and back-fill business meaning (screen/field) onto
  DB columns. Use whenever the user works with Oracle trace files (.trc),
  wants to trace which tables/columns an application writes, builds or extends
  a DB-to-APP mapping, reconciles app values against a trace, or traces a new
  application module — even if they don't say "10046" explicitly.
---

# Oracle SQL tracing — app-to-database reverse engineering

The goal: for every field a user fills in the application, find the database
column that stores it — with the entered VALUE as the proof. A 10046 trace
captures the bind values of every statement the app executed, so if you enter
recognizable values in the app while tracing, those values reappear in the
trace attached to their table.column.

Everything project-specific (module folders, file naming, marker prefixes,
workbook formats, enum sources) lives in a **project tracing adapter** —
look for `tracing-adapter.md` near the scripts (ask the user if absent).
The project's script README is authoritative for CLI usage; this skill covers
the method and the design invariants that must survive maintenance.

## What a 10046 trace can and cannot give you

- It captures **bind values of executed statements** (INSERT/UPDATE, and
  SELECTs if kept). It does NOT capture **fetch results** — so display labels
  served from lookup/reference tables are unrecoverable from the .trc itself.
  Decoding coded ids to labels always needs an external enum/reference export.
- One trace session is **n=1 evidence**: a real column can be absent simply
  because that flow never touched it. Treat "found exact" as one sample.
- **Silence is a fact about SCOPE, and it is worth stating explicitly.** When a
  candidate table returns *zero* captured columns, the trace has not weakened the
  pick — it has said nothing about it, and the mapping must be graded accordingly
  (inferred, not trace-backed) with the silence written into the row. Measured: a
  reviewer-preferred reviser column sat on a table the traces never exercised at all
  (**0 columns captured**), while its fallback appeared only as an INSERT audit stamp
  holding the system account. Neither was trace evidence for the *business* meaning;
  recording "no trace ever exercised a review step" is what stops the next reader
  mistaking a structural pick for a confirmed one.
- **The trace is a TIMELINE, and the ordering settles semantics that no single value
  can.** Captured timestamps across tables reconstruct what the flow actually did, so
  "created" and "processed" stop being a guess. On one collected request:
  `ORDER.CREATED_ON` 10:16:59 (submitted) → `RECEIPT.CREATED_ON`
  10:25:10 → `LEDGER_TXN.TRANSACTION_DATE` 10:27:53 (posted) →
  `LEDGER_TXN.CREATED_ON` 10:27:55 (row written). Eleven minutes separate submission from
  completion, which proves a "processed date" belongs on the transaction and not on
  the request — and distinguishes the business date from the row-insert stamp two
  seconds later. Read the timestamps in order before arguing about a date field.
- **PID reuse contaminates trace files**: Oracle names .trc files by process
  id, and a reused PID appends another day's session to the same file. Split
  by the `*** yyyy-mm-dd hh:mm:ss` block headers and keep one date's blocks
  before parsing (back up the original first). Check the stray blocks before
  splitting, though — a leftover block holding only startup warnings and a
  CLOSE (no PARSING IN CURSOR, no BINDS) contributes nothing to the mapping,
  so splitting it out is churn.

## The capture technique

Seed the app with **marker-prefixed values** (a recognizable prefix on every
free-text entry, e.g. `mkr_...` — concrete prefixes are per-project/adapter)
so the parser can tell your test entries from pre-existing data. Picklist and
date fields can't carry markers — they are matched later by value/decoding.

## The pipeline (3 stages, strict order)

**parse → reconcile → (manual notes) → back-fill.** Re-running parse
regenerates the mapping fresh, so any re-parse requires re-running back-fill.

1. **Parse** the .trc into a mapping workbook. Contract: three sheets —
   *Unique Field Mapping* (deduped table+column+value — the working sheet),
   *Field Mapping* (full per-execution detail; one execution's values share a
   merged SQL-text group — de-spray depends on this grouping), *Statements*
   (overview). Multiple .trc inputs are MERGED (not concatenated). Default
   filtering keeps application statements only (recursive/SYS and SELECTs
   excluded unless explicitly included).
   - A *Value (Decoded)* column decodes coded ids via a flat enum lookup
     (`table.column|id → label`); blank means "not covered by the enum", not
     "not coded". Rebuild the lookup whenever the enum profile changes.
   - **Before reporting undecoded ids as a data gap, CLASSIFY them — most are
     not coded domains at all.** Three kinds, three different asks:
     *surrogate PK* (`NOTE.NOTE_ID`, `DOCUMENT.DOCUMENT_ID` — a row id, no
     lookup exists or ever will), *entity reference* (an FK to a business row:
     the decode is a join, and the ERD/naming already names the target), and
     *coded domain* (the only one that needs a reference export). Detect a
     surrogate as `column == table + "_ID"`; detect an entity reference from a
     populated FK field **or** from `<TABLE>_ID` naming a table the catalog
     knows. Skip this and the "gap list" ranks row ids at the top: one pass
     opened with `NOTE.NOTE_ID` at 71 ids — pure noise — and asking a DBA to
     "identify the domain" for a primary key destroys the list's credibility.
     Classifying cut 323 ids over 65 columns down to a real ask of 3 columns
     and 14 ids. Also expect **polymorphic** columns (`NOTE.ENTITY_ID`,
     `DOCUMENT.ASSOCIATED_OBJECT_ID`): ask for the *discriminator column*, not
     a lookup table. A high distinct-to-row ratio settles it — a column with
     420,715 distinct values over 420,715 rows is a unique key, not a domain.
2. **Reconcile** the app-entered values against the mapping → a per-value
   FOUND/NOT-FOUND summary. **Reconcile is the single matcher**: it owns the
   (app field → DB column) link. Between reconcile and back-fill, a human can
   resolve NOT-FOUND rows by writing the DB `TABLE.COLUMN` into a Status-Note
   (column ≈ field, table ≈ section) with a confidence grade.
   - Deriving those notes: inspect the mapping's table/column inventory to
     hypothesize a home; grade High when the table is clear from context, Low
     when guessing; escalate to the user only the genuinely ambiguous rows.
   - Notes are preserved across re-runs keyed by (section, field) — renaming
     a section banner orphans that section's notes; re-derive, don't hand-copy.
   - **Substring false positives**: reconcile's fallback "contained" match will
     call `mkr_x_2` FOUND against a traced `mkr_x` — one marker is a prefix of
     the other and only a numeric suffix differs. Back-fill has the guard
     ("structured ids never fuzzy-merge"); reconcile does not, so a FOUND
     (partial) on marker values whose siblings differ by a trailing number
     needs a human check. Confirm by scanning the raw .trc for the exact
     marker, and if absent record it as a false positive in the Status Note.
   - **Date fields**: a raw date matches every CREATED_ON/UPDATED_ON in the
     schema, so dates are NOT value-matched (a date is not a fingerprint).
     Constrain each date field to the date column(s) of the table its
     section's OTHER values came from, auto-noted; a manual note always wins.
3. **Back-fill** inverts the reconciliation onto the mapping workbook (App
   Section / App Field / entered value / status per DB column). It does NO
   matching of its own — it reads what reconcile resolved, Status-Note
   overrides included. That single-matcher invariant prevents double-matching
   drift; preserve it in any extension.

## De-spray: pinning a value to its one home screen

A column that feeds several screens must not be listed against all of them on
every row. Resolve each row's App Section/Field by a 3-level priority ladder:

1. **SQL group**: all values one INSERT execution wrote describe the same
   record, hence one app screen. Decide the group's section by voting — a
   value votes only if it matches exactly one section for its own column
   (shared values, dates, and NULLs don't vote). Pin every (column, value)
   that maps to a single section across all groups; a value echoed on
   read-only review screens maps to its single home screen. Genuine
   two-record conflicts fall through to (2).
2. **Value match**: compare BOTH decoded and raw value against BOTH the raw
   entered value and its translation/gloss (the trace may store one language
   while the app displayed another). An exact (normalised) match suppresses
   fuzzy matching entirely; fuzzy (token overlap ≥ 0.6, letters required)
   applies only when nothing matches exactly; **structured ids never
   fuzzy-merge** — differing numeric tokens mean a different record. Numbers
   compare loosely (`45` = `45.0`, `5,000,000` = `5000000`).
3. **Column list** (fallback): every field the column feeds.

Rules that keep it honest:
- **NULL/blank/placeholder values are never mapped** — a NULL row says
  nothing about the app field; leave it unmapped rather than sprayed.
- **No silent drops**: every reconciled (section, field) left uncovered after
  back-fill is printed at the end of the run, with pin counts
  (`SQL-group-pinned: N, value-pinned: M`) as the audit trail.
- The back-filled "entered value" column self-decodes coded ids from the
  project's own reconciled data (independent of enum coverage); a shared id
  column lists the domain of labels the field took.
- Display-only translation columns must leave the matched value untouched so
  matching is unaffected and re-runs are idempotent.

## Safety & reporting

- Outputs are sent to the Recycle Bin (or equivalent) before overwrite so a
  re-run can never destroy manual notes; the bin is the recovery path.
- End-of-run report: found/not-found counts, how many rows received notes,
  and an explicit list of anything left deliberately unmapped, with why.
- If the module folder or input layout doesn't match the adapter's pattern,
  stop and ask — never guess paths.

## Retrospective

Same discipline as the sttm-mapping skill: keep a learnings buffer during the
run; fold generic lessons into this file, project facts into the tracing
adapter, and note near-misses. A run that updates nothing is suspicious.

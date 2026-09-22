---
name: sttm-mapping
description: >-
  Generic methodology for building, enhancing and validating source-to-target
  mapping (STTM) workbooks for data migrations — AS-IS→TO-BE field mapping with
  evidence grading, transformation specs, adversarial validation, and safe
  spreadsheet editing. Use this skill whenever the user works on an STTM, a
  source-to-target mapping, a data-migration mapping sheet/workbook, field
  mapping between a legacy database and a new application, mapping validation,
  or asks to "map", "enhance" or "validate" migration mapping sheets — even if
  they don't say "STTM" explicitly. Also use it when creating a new mapping
  workbook from a data dictionary, or auditing an existing one.
---

# STTM Mapping — generic source-to-target methodology

An STTM row answers one question with evidence: **"where does this target
field's value come from, exactly, and how sure are we?"** Everything in this
skill exists to make those answers precise, auditable, and safe to hand to a
migration engineer.

The method is generic. Everything project-specific — column positions,
reviewer names, evidence-source paths, state vocabularies — lives in a
**project adapter file**, never in this skill.

## 0. Load the adapter first

Look for the project adapter (`sttm-adapter.md`, usually next to the workbook
or in the project's scripts folder; ask the user if absent). It declares the
workbook contract defined in [references/workbook-contract.md](references/workbook-contract.md):
file path & format, header row, sheet list, column map (semantic role →
column), **human-owned read-only columns**, evidence-state vocabulary,
confidence vocabulary, evidence sources (traces, profiles, DDL, ERD,
dictionary, reference data), and editing constraints (e.g. macro workbook ⇒
COM only).

If no adapter exists yet, create one from the contract template as your first
deliverable — it forces the right questions.

## 1. Non-negotiables (apply to every engagement)

1. **Human columns are read-only.** Reviewer/SME columns are never edited,
   "corrected", or restored from backups without explicit per-cell user
   authorization. A wrong human entry is surfaced as a finding, not fixed.
   When you prove you didn't touch them by diffing against the backup, expect
   **derived columns living inside the human band** to move anyway — an
   "agrees with AI?" formula flips the moment you change the AI pick. Classify
   each changed cell as formula-vs-static before reporting a violation, and
   report the flip as the intended consequence it is.
2. **Back up before any write.** Timestamped copy to a scratch area, even for
   "small" changes.
3. **Safe editing:** if the workbook is macro-enabled or has form controls,
   ALL I/O goes through COM/xlwings — an openpyxl save silently destroys
   macros and controls. Read [references/safe-editing.md](references/safe-editing.md)
   before the first write.
4. **Evidence beats name similarity.** A sampled/captured VALUE in a column
   outranks a perfect name match without one. Never grade confidence on
   naming alone. Corollary on the negative side: **absence from a catalog or
   schema dump is WEAK evidence of absence** — dumps are filtered, sampled or
   permission-scoped. A table twice declared "not in production, would raise
   ORA-00942" on the strength of a 782-table dump turned out to receive a
   successful production INSERT in a later trace. Say "not in the dump", never
   "does not exist", unless something actually executed against it and failed.
   **The same caution applies to catalog STATISTICS, not just to absence.** An
   optimizer figure like `num_distinct` is an ESTIMATE from a SAMPLE, and the
   sample size is usually in the row beside it — read it. Measured: two contact
   columns were entered into a migration BLOCKER list as "masked — 1 distinct
   value over 79,416 rows"; a direct `COUNT(DISTINCT)` showed both hold real,
   varied data, and the single value the sampler saw was a `'0'` placeholder.
   That mis-blocked an entity for a week. **Never promote a catalog statistic to
   a blocker, a finding, or a mapping decision without an exact count**, and when
   you cite one, cite the sample size with it.
   **On the AS-IS DATA TYPE specifically, the dictionary outranks the dictionary
   document.** A mapping sheet's "AS-IS data type" usually has three possible
   origins — the database's own catalogue, a type typed into the data dictionary by
   a person, and a value recomputed by the builder — and they drift. Where they
   disagree, the catalogue wins, because it *is* `ALL_TAB_COLUMNS`; a DD type is an
   annotation. Measured: 104 cells across two modules disagreed with the database,
   including a status field recorded as `NUMBER(20)` when its pick was the *label*
   column (`…DATA_DESC_EN`, a varchar) — a transcription slip, not a decision.
   Three cautions before a bulk normalisation: (a) catalogue **absence** still is not
   schema absence, so leave and flag those rather than blanking; (b) a type cell may
   carry human reasoning (`NUMBER(20) (row-existence flag; the AS-IS has no dedicated
   boolean)`) — move that prose to a note instead of deleting it; (c) run the
   row-internal coherence lens FIRST, because a type that contradicts its pick is
   sometimes the only clue that the *pick* is wrong, and normalising destroys it
   (see [references/validation.md](references/validation.md) → V7).
   Know which artifact your "catalogue" actually is: on one engagement the registered
   catalogue was an exported workbook of AS-IS tables and columns whose sheet is a
   verbatim `ALL_TAB_COLUMNS` dump, and the `.tsv` everything read was a derived
   lower-cased subset of exactly the same 11,448 rows. Both are the database; saying
   so precisely matters when a reviewer asks where a type came from.
5. **The base pick is the column that HOLDS the value.** Access path (FK
   joins, lookups, decodes) belongs in the join/decode column; a foreign-key
   id is not a mapping for a descriptive field.
   **Read a column's VALUE DOMAIN before mapping it, not just its name.** A
   column whose distinct values are *entity or table names* is a
   discriminator, never a party, actor or descriptive field. Measured: a
   TO-BE `Receiver` was mapped to `NOTE.NOTEOWNER`, whose 42 distinct values
   are `Request`, `Person`, `grant`, `OPEN_FILE`, `GRANT_CERTIFICATE` … —
   it names which entity the note hangs off, not who receives anything. One
   `GROUP BY` would have said so.
   **A POLYMORPHIC FK is TWO columns, and the second one is easy to write off.**
   The shape is a numeric object id beside a never-null non-numeric companion:
   the companion is the type label. Test them differently or you will discard
   the discriminator:
   - matching the **id** against every candidate parent PK is *uninformative*
     when key ranges overlap — an id in the low thousands exists in most
     tables. Measured: per-parent matches summed to 1,074,648 against 428,024
     rows that matched anything, i.e. ~2.5 parents per id, and the largest
     parent claimed 99.7% purely by range.
   - matching the **label** against parent PKs returns **zero**, which looks
     like a dead column. It is not — that is exactly what a type label does.
     `GROUP BY` it instead. Measured: `DOCUMENT.EXTERNAL_ID` was written off
     as inert after scoring 0 against all ten parents; grouped, it turned out
     to be a 54-value vocabulary (`person`, `grant`, `receipts`, …)
     where each label predicts its own parent at 99.9-100%. The filter for
     every attachment child table fell out immediately, and a BA ruling that
     had been on the critical path was no longer needed.
   So before concluding a polymorphic link is unresolvable, enumerate the
   sibling columns and `GROUP BY` any never-null non-numeric one.
   **An FK to a TO-BE lookup entity is an Association, never a Source.**
   Mapping `Party_PartyTypeID` to `Lookups.PartyType.ID`
   is circular — the target's own key is not a legacy source. The reference
   belongs in the association/DB-reference column; the Source column carries
   only what the AS-IS holds. Corollary: where the TO-BE model *declares* a
   reference, `Source = N/A` is correct but leaving the association column
   empty is not — the model already knows the answer.
6. **Type audit:** the picked column must be able to hold a value of the
   target's data type (boolean target ⇒ boolean-ish source or derived rule —
   never a name/text column; percentage ⇒ share/percentage column;
   attachment ⇒ document home; date ⇒ date column). Composite target types
   map EVERY component.
7. **Map everything.** Every target field gets a best-effort source or an
   explicit net-new. Blanks are QA failures — use explicit N/A tokens so
   "intentionally empty" is distinguishable from "forgot".
   **N/A is an ENTITY-level statement as well as a cell-level one.** If every
   non-key attribute of an entity is N/A, the entity does not load, so its ID
   cannot be "sys-generated" — nothing is generating a row. Measured twice on
   one engagement (`Trustee.ID`, `DeferralReason.ID`). Run the check per
   entity, not per cell.
   **A column PROVEN empty is not low confidence — it is N/A with a reason.**
   Grading a 0-populated column "Low" implies a weak mapping; the truth is
   there is no data to migrate. Measured: `PROPERTY.MUNICIPALITY_PLAN_NO` is
   0 of 899 on dev and 0 of 987 on staging, and 0 under its own extraction
   filter. Write N/A, state the counts and both environments as the reason,
   and keep the real question ("where is this value actually held?") alive in
   the ask column rather than losing it with the source.
   **Confidence has a ceiling, and it is not yours to raise.** It may never
   exceed the data dictionary's own confidence for that field unless you have
   NEW direct evidence, and a 0-populated column caps at Low regardless of how
   perfectly the name matches. Two rows were shipped at High on name-and-
   meaning alone against a DD that said otherwise; the user caught both.
8. **No mapping edits after validation without sign-off** on the findings.
9. **Reference data is an ATOMIC SNAPSHOT — never blend two exports row by row.**
   When two dumps of one lookup table disagree, the ETL will still run against
   exactly one database, so a per-id "best of both" yields a dictionary matching
   no state that ever existed. Adjudicating per row is legitimate as a
   *diagnostic*; it is never a merge policy. Decide which export is production
   and adopt it **wholesale**. Three corollaries, each bought the hard way:
   - **A technical/code column is NOT an arbiter of a display label.** Reasoning
     "the code is the stable identifier, so it reveals the true label" is
     seductive and wrong: legacy systems relabel without renaming codes. A real
     table shipped code `EXPENSE_AND_REVENUE_STATUS_REALIZED` with the label
     **Paid**, code `REALIZED` with **Collected**, code `TOP FLOOR` with
     **FLOOR**. Code-vs-label drift is normal ageing, not evidence of a bad
     label. Adjudicating 32 labels this way got **12 of 12 changed rows wrong**.
   - **When inference between two sources deadlocks, stop inferring and ask for
     a query against the source system.** Cheap, fast, and it outranks every
     lens of reasoning you could stack up. Make the query **self-adjudicating**:
     embed each candidate as a literal (`WITH expected AS (SELECT … FROM DUAL
     UNION ALL …)`), join the live table, and return a `MATCHES` column naming
     the winner per row. The requester then reads a verdict, not a diff. Unanimity
     across every disputed row is also what confirms "one snapshot", so the query
     tests the premise as well as the rows.
   - **Demand provenance on every reference export**: database name, service,
     host, schema, export timestamp. The ambiguity above existed *only* because
     neither dump recorded where it came from. An export without provenance
     cannot settle a dispute, so make provenance query #0 of any data request.
10. **INVENTORY WHAT YOU ALREADY HOLD BEFORE RAISING A DATA REQUEST.** Asking a
   client for data that is already sitting in a file you were handed spends their
   goodwill and your credibility, and it is the easiest possible mistake to avoid.
   Measured: of four "this unblocks us" queries sent to a client, **three were
   already answered** in the reference workbook the same session had been building
   its decode layer from. Two rules:
   - **Enumerate the sheets/tables of every artifact you hold and write the
     inventory into the project adapter as a table** — sheet, row count, columns,
     and *which question it answers*. A rule that depends on remembering what is
     in a file will fail; a table you can read will not.
   - **Split the request by KIND before sending it.** *Reference/lookup data* is
     almost always already in hand — check first. *Distributions, volumes, row
     counts, masking, live precision* genuinely require the source system. Send
     only the second kind, and say in the request which artifact you already
     checked, so the client can see you did.
   - **The inventory must include DERIVED answers, not just lookup sheets.** A
     catalog dump answers questions no sheet lists: a reliable null-count answers
     a population question outright (two "which column is the expiry?" candidates
     were both ~100% NULL — the answer "neither" needed no query); a declared
     type BOUNDS the data, so a non-truncating target type is pinnable
     immediately and the live measurement becomes tighten-only; one traced
     counterexample decides a type question; and a held domain lookup can kill a
     question's PREMISE (a "which type id scopes X?" question died when the
     domain turned out to be System/User — the wrong axis entirely). Measured:
     a "complete" query pack lost six of its queries to a second inventory pass
     over artifacts already in hand. Run every query you CAN against your own
     artifacts before shipping the request.
   A held reference export can also BEAT a live query: it typically retains
   soft-deleted rows a `WHERE IS_DELETED = 0` query hides, and a historic row may
   legitimately reference a deleted lookup value.
   Corollary for the queries you DO send: **mechanically validate every
   table/column reference in a client-bound SQL pack against the schema artifacts
   you hold before sending it.** Column names leak in from the TO-BE side while
   drafting (measured: 4 of 8 hand-written queries in one pack carried
   nonexistent columns — each an ORA-00942/00904 on the client's desk and a
   burned round-trip). The check is a trivial script over a catalog dump; make it
   a standing guard, not a one-off. And a PASSING schema check only proves the
   query RUNS — it says nothing about whether it measures the stated question
   (NULL-swallowing `COUNT(DISTINCT)`, aggregation keyed on the minority entity,
   unpinned `TO_CHAR`/NLS, missing `OWNER` on dictionary views), so client-bound
   packs get an adversarial semantic pass as the second gate.
   - **THIS RULE WAS BROKEN AGAIN, at scale, under a closing window.** Measured on a
     later engagement: of **38** queries sent while the source-system window was hours
     from closing, **~17 asked for data already on disk** — 10 were verbatim
     reference-lookup content in a workbook already delivered to the client, 7
     duplicated queries already sitting in the engagement's own AS-IS query pack.
     Time pressure is what makes this rule get skipped and is exactly when it pays
     most: a wasted query in a closing window is not deferred, it is *lost*. So make
     the pre-flight two mechanical commands you run before writing any SQL, not a
     habit to remember. There are FOUR, and they cover different ground — a later
     pre-flight on the same engagement killed four more queued queries, and NONE of
     them was caught by the first two:
     (a) the reference workbook's sheet names; (b) the query pack's header comments;
     (c) **the registered query LOG — every question already asked WITH its answer**,
     which is what catches a question you are re-deriving rather than re-asking; and
     (d) **the schema catalogue's null counts**, which answer population questions
     outright. Together they cost under a minute. Standing split:
     **reference and lookup content is already delivered; a live window is for
     transactional shape, grain and value questions only.**

11. **A SOURCE PICK IS A CLAIM ABOUT BUSINESS MEANING, AND STRUCTURE CANNOT
   ESTABLISH IT.** Cardinality, completeness, value-count agreement and a clean
   statistical partition are all *necessary* for a candidate source and *never
   sufficient*. Measured across one migration engagement: four separate picks
   were proposed on structural grounds and **all four were rejected by the
   business owner on meaning** — the worst being `CONTRACT.IS_PRIMARY_HOLDER`
   offered as the source for `Agreement.IsAppliedToAllParties` because it was
   three-valued, NOT NULL, complete on all 1,481 rows and partitioned
   `HOLDER_ID` perfectly. Every one of those facts was true. The mapping was
   still wrong, because the flag answers *who holds this contract* and the
   target asks *does one party arrangement apply across the whole agreement*.
   Two different questions whose value sets happen to align.
   - **Name the question each side answers, in a sentence, before proposing the
     pick.** If the two sentences are not the same question, no amount of
     distribution agreement rescues it. Write both sentences into the row — that
     is what makes the error reviewable instead of plausible.
   - **A "better source exists" upgrade is the highest-risk edit in the sheet.**
     It overrides a pick someone made *with* domain knowledge, on evidence that has
     none. Treat an existing reasonable pick as the prior; propose the upgrade as
     a question to the BA, never as a confidence bump.
   - **Never raise `Confidence` on evidence about a different column.** Confidence
     grades *this* mapping. A measurement of the candidate's own completeness says
     nothing about whether it means what the target means — and it silently
     converts an open question into settled fact for every downstream reader.
   - **When a pick is retracted, relocate the finding rather than delete it.** The
     `IS_PRIMARY_HOLDER` measurement was genuinely valuable — it became the
     candidate source for the unsourced `Party.PartyType`, logged as a proposal
     with an explicit BA ask. Record the retraction *in the row* too, naming why
     the reading was wrong, or the next pass re-derives it from the same structure.
   - Beware the tell: **an attribute named for a scope/grouping** (`IsAppliedOnAll…`,
     `IsSameFor…`, `AppliesTo…`) is almost never carried by a column; it is derived
     by testing uniformity across a grain. Ask what "all" ranges over *first* — the
     answer decides the population, and a uniformity rule over the wrong grain is
     wrong while looking entirely reasonable.

   - **Compare candidate columns BY VALUE, SIDE BY SIDE, IN ONE QUERY — coverage
     counts cannot settle a pick.** Where you suspect more than one column, put them
     all in the SELECT list of a single query over a handful of traced entities and
     read across the row. Do not run a completeness count per candidate and rank
     them; that ranks *population*, and population is not meaning (rule 11's whole
     point). Measured: one side-by-side over 7 traced rows closed six open questions
     and overturned two picks — a "commercial name" fallback proved to be a byte copy
     of the primary name while a genuinely bilingual `_EN` column sat unmapped, and a
     plausible "number" candidate held a project reference rather than the land
     number the target wanted. Neither was visible statistically: both columns were
     100% populated. The client's own phrasing is the rule — *we are not just taking
     the filled column* — and when a trace already shows both columns, the
     side-by-side is corroboration, not rework.
12. **A SOURCE CHANGE IS NOT ONE CELL. Identify and REBUILD every column that was
    derived from the old pick — never leave the previous values standing.** When the
    source moves, the cells that explained, validated, sampled, typed and graded the
    old pick are silently invalidated. They do not look broken; they look authoritative,
    and a reviewer reads them as current.
    - **A GRADE IS FINGERPRINTED TO THE PICK IT WAS MADE AGAINST.** Where the
      generator derives confidence once and then freezes it, that freeze is keyed
      on a stored copy of the source pick. A ruling that MOVES the source without
      restamping that key leaves the fingerprint pointing at the old pick, the
      freeze lifts, and the row is silently re-graded from its new evidence —
      discarding the grade the ruling just set. Measured: a row ruled Low (its
      source column is populated on 0.36% of rows and its scope is unproven) came
      out High, because the deriver sees a real source and a Lookup type and knows
      neither caveat. Five sibling rows re-derived to the same grade by luck,
      which is exactly why it would not have been noticed.
    - **The dependent set**, all of which must be re-derived or explicitly re-confirmed:
      `Expression` · `Rule` · `Join / Lookup Path` · `Extraction Filter` ·
      `Confidence Level` + `Confidence Reason` · `Evidence` · `Sample` ·
      `Source Data Type` · `Validation Check` · `Null Handling` · `On No Match` ·
      `Risk Tier` · `Quality Rules` · `LoV Values` · `Cardinality`.
    - **Measured, twice, on one engagement.** After a bulk source re-key, **51 + 5 rows**
      still read `-- no source: entity starts empty` in `Expression` while carrying a
      source — and **57 of those pointed at a parent that DOES migrate**, so the text was
      not merely stale but false. **92 + 160** `LoV` cells still described the witness
      column that had just been moved out of `Source`. `Evidence` still read
      `Trace — FK id` on rows whose source had become a seeded target-side id that no
      trace can ever witness. The user caught all three; none tripped any gate.
    - **Rebuild in the DERIVATION layer, not by patching cells.** Patching leaves the
      generator disagreeing with the sheet, so the next build silently reverts it. The
      proof that you did it right is a round-trip that reports **zero differences with a
      non-zero matched count** — zero-differ on zero matches means you compared nothing.
    - **Only overwrite a cell still holding the generator's OWN prior default.** Keep
      those defaults in a named set and test against it exactly. Every one of these
      columns is usually reviewer-editable, so a blanket rewrite destroys review work
      (rule 1). Anything else is a FINDING: report it, leave it.
    - **Distinguish a stale default from decision PROVENANCE.** Text citing the old
      source because it records *why a pick was rejected or replaced* is the audit trail
      of a ruling — deleting it because it names a superseded column erases the decision.
      Measured: of 20 rows flagged by a contradiction scan, only 3 were stale templates;
      17 were rulings and correctly left alone.
    - **The correct value can differ per row.** Reject-on-no-match is right when the
      parent entity migrates and WRONG when it is seeded configuration — there,
      rejecting on a parent that starts empty rejects every child row. Split on the
      condition and report the rows you deliberately left for the BA.
    - **Print per-column counters for what the pass changed.** A pass that silently does
      nothing looks identical to a pass that had nothing to do. A silent counter is what
      exposed a real bug: the rule tested the row's type *before* the same loop re-typed
      it, so it matched zero rows and appeared to succeed.
    - **Verify by re-running the scan that found the problem**, not by inspection: search
      converted rows for (a) the exact prior default strings, (b) type-words contradicting
      the new mapping type, (c) old-source citations absent from the join/filter columns —
      then adjudicate (c) case by case against the provenance rule above.


13. **A STORED EXTRACT IS NOT VALIDATED UNTIL IT HAS EXECUTED.** A mapping row can
    be correct in every column while the query built from it cannot run, or runs and
    returns the wrong grain. These are different artifacts and they need different
    gates. Measured: **30 of 31 extracts flagged READY in a control table would not
    execute at all** on the source Oracle instance, on a sheet whose mappings had
    passed the full validation harness — and the two headline defects were invisible
    to every row-level lens (an inner join on an optional chain that reduced 1,295
    rows to ~6, and a `ROW_NUMBER()` PK that hid 332 duplicate business keys behind
    unique surrogates). Three consequences:
    - **`READY` must mean *parses and executes*, not *mapped*.** Gate the flag on a
      real parse, and on `ROWS_OUT = COUNT(DISTINCT <legacy key>)` for the output.
      That single equality catches the whole grain-defect class.
    - **`EXPECTED_VOLUME` is a claim to be recomputed from the repaired query**, never
      the raw table count. Measured corrections: 1,295 against a stored ~6, and ~554
      against a stored 1,516,197 (the unfiltered row count of a shared child table).
    - Run the eight extract lenses (E1–E8) in
      [references/validation.md](references/validation.md) → *The extract audit* the
      first time any stored query executes, and again after every source re-pick.

### Closed vocabularies: print the list, never infer the token

Any column backed by a dropdown has ONE legal list, and it lives in the layout
declaration. Reading a plausible value off a neighbouring CONCEPT is the same
error as reading it off a sibling row.

- Print the lists from the layout module before writing. Do not recall them.
- The trap is a token that is real but belongs to a different list. Measured:
  `Seed` and `Lookup Resolve` are legal DISPOSITION values and illegal MAPPING
  TYPE values; writing them produced HARD gate failures on a sheet that had just
  been declared clean.
- A vocabulary change is never one edit — the writers, the stores and the
  validation all carry the token, and the filter gate goes VACUOUS rather than
  red when they disagree.

## 2. The method — phase by phase

### Phase A — Preflight
- Backup; confirm workbook structure matches the adapter (headers, columns,
  hidden/visible state). Structure drift = stop and reconcile first.
- **Input-existence gate:** verify every declared evidence source file exists
  before any pass; if one is missing, STOP and report it — a silently absent
  evidence file degrades every downstream confidence grade.
- Build **ground-truth extracts** (TSV) from the workbook and the evidence
  sources so every later pass reads identical data instead of re-opening the
  workbook. Confirm row/state counts match the sheet.

### Phase B — Row inventory & keying
- One row per target field. Assign/verify **stable global keys**
  (`<sheet>-<field-id>`), because field ids collide across sheets and drift
  on insertion.
- Classify **row kinds** explicitly (capture vs mirror/reference vs
  review-flow) with a column, never by row ranges — range conventions rot.
- Identify **common/shared sections** (request headers, party blocks…)
  that recur across sheets: map once, reference everywhere, apply per-sheet
  deltas only.

**Cross-module reuse pass — do this in CODE before any mapping agent runs; it
is the single biggest token saver on multi-sheet engagements.** When earlier
modules/sheets are already mapped, most fields in a new sheet are the SAME
field seen again. Build an index of already-mapped rows keyed on
`normalize(field name) + the SET of source table.columns in the pick` — name
alone is unsafe because generic names (Description, Status, Notes) recur across
different tables, so the source column is the disambiguator. Match on set
**overlap** (share ≥1 candidate), NOT on the primary candidate: two passes over
the same field routinely list the same multi-candidate pick in a different order
(`A | B` vs `B | A`), so keying on the first/primary alone silently misses a
genuine repeat. Overlap-not-equality also still rejects a false match on a
generic name whose sources don't intersect.

**Even a name + source-column match is not conclusive.** The SAME descriptive
column reached by a DIFFERENT join/FK path is a different entity's datum — a
phone/email/name captured for the payer vs a beneficiary vs a guarantor, an
"estimated value" for one asset type vs another, a "notes" column scoped to a
different parent record. Those are separate captures, not mirrors. The decisive
tie-breaker is the **join path / entity**, not the column. A true mirror is a
read-only RE-SHOW of the same real-world datum (typically a later
process — amendment, cancellation, review — re-displaying a record created
earlier). When names or columns collide across entities, don't auto-flip: run a
short adversarial adjudication (default to "distinct" unless it is unambiguously
the same datum re-shown) before reclassifying. **Conversely**, the SAME logical
field re-shown across sheets with a DIVERGENT source (a different column/table
picked in a later sheet than in its first occurrence) is usually an
inconsistency to RECONCILE to the first occurrence, not proof of distinctness —
especially for inherently single-source fields (identifiers, contact fields).
Join-path difference proves distinctness only for a genuinely different
entity/instance; field identity is ultimately the domain owner's call, so
surface divergent-source repeats to them rather than silently splitting. The canonical capture is the
first occurrence in process order, but if a later occurrence carries a
more-developed mapping than that anchor, merge it INTO the anchor before
referencing (don't let a live reference degrade a good mapping to an empty one).
For each new-sheet field that hits the index:
  - mark it **Mirror**, add a `mirror of <source global key>` pointer, and
    **inherit the source row's mapping** (evidence state, join, confidence,
    helper bullets) instead of re-deriving it;
  - **inherit the human reviewer columns too**, but only into EMPTY cells,
    never over a formula or an existing human value (see
    [references/workbook-contract.md](references/workbook-contract.md) →
    "Mirror inheritance of human columns"). Reviewer picks describe the field,
    not the screen, so a faithful mirror carries them.
Only the genuinely-new fields (index miss) go to the expensive mapping agents.
This both slashes cost and guarantees identical mapping everywhere.

**Wire a mirror cell-by-cell, by VALUE.** For each reviewer/AI column of a mirror
row, compare its value to the same column on the first capture: if equal, replace
it with a live reference to that capture cell (single source of truth); if it
differs, judge — a different BASE source column means it is not actually a mirror
(keep it as its own capture), whereas a value that is merely stated differently
can be merged UP into the capture to enrich it, then referenced. The
"how-to-reach/decode" columns (join/decode path, cardinality, extraction filter,
transformation) legitimately vary per entity and stay per-row — the same base
column reached by a different FK path is still one mirror, just with its own join.
The reviewer's confirmed source column is the identity key, not the field name
alone.
When judging "differs", check whether the mirror cell's live content is a FORMULA
(an auto-default confidence, an existing echo ref): formula output is mechanical,
not a human choice — wire it to the anchor; only a differing STATIC value is a
human entry that must stay per-row. Wrap wired refs as `=IF(anchor="","",anchor)`
— a plain reference to a blank anchor renders 0.
Reclassifying a former Capture to Mirror changes scope counts — reconcile the
dashboard KPIs and expect the drop (it equals the flip count).

**Generalisation inheritance is a different mechanism from mirroring — and it has a
signature failure.** (Where the target uses class-table inheritance — Mendix, or any
supertype/subtype schema — read [references/inheritance.md](references/inheritance.md)
FIRST: inherited attributes are mapped once on the declaring entity, the child keeps
only its own attributes plus the shared PK/FK ID, and the parent's extraction scope
must subsume the union of its children's. `scripts/check_parent_scope.py` tests that
containment mechanically.) Where the target model declares `Child specializes Parent`, the
child rows carry the parent's *field-level* facts (physical source pick, source type,
DD citation) by guarded reference, while per-child facts (rule, filter, confidence,
evidence, status) stay literal. Three traps, all measured:

- **A guard that "leaves both sides literal" strands children that never had a
  literal.** The natural implementation is: if the children agree but the parent
  already holds something *richer*, emit no reference and leave both sides alone.
  That is correct only for a child holding its own value. A child populated
  *exclusively by the reference* has nothing to leave, so enriching the parent
  silently BLANKS it. One parent enrichment emptied **51 cells across four child
  families** (24 DD citations, 23 types, 4 source picks); the one sibling that
  survived did so only because it owned literals. Fix the rule, not the cells: link
  every child that is empty **or already equal to the anchor**, and let a child whose
  literal genuinely differs keep it as the human conflict it is.
- **Changing a parent leaves the children's SAVED records asserting the old value.**
  The workbook renders correctly through the references while the decision store
  underneath still names the superseded source, so the next build re-asserts it.
  Twelve such child records would have silently undone three signed-off rulings.
  After any parent change, clear the corresponding child records so the build is the
  only author of the inheritance.
- **Children that genuinely disagree are an ANSWER, not a defect.** Where each child
  cites its own screen field (six attachment children citing six different DD rows,
  one of them a "Letter" rather than an attachment), forcing one value would mislabel
  five rows. Report the disagreement; do not converge it. Distinguish this from the
  type case, where the disagreement was pure drift and the catalogue settled it.

### Phase C — Mapping pass (new/index-miss rows only)
For each capture row, in this order:
1. **Gather evidence**: sampled/captured values, FK resolutions, DDL/ERD
   confirmation, dictionary/LoV domains, cross-module traces.
2. **Pick the base** (rule 5), **write the access path** (join/decode), and
   the **extraction condition** (filters, type discriminators, soft-delete
   flags, entity scoping — a join without its discriminator is a defect).
   Where two same-typed source columns could both serve one target field,
   treat them as distinct ROLES until a bucket reconciliation proves
   otherwise — never collapse them because the names read as synonyms
   ([best-practices §2](references/best-practices.md),
   [validation.md](references/validation.md)).
3. **Set the evidence state** from the adapter vocabulary (typical 5-state:
   verified-value / verified-id-via-join / inferred-schema / derived-rule /
   net-new). Derived fields are flagged derived — never disguised as traces.
4. **Grade confidence** against evidence, applying the adapter's caps
   (unexercised joins, single-sample traces, entity-resolution policies).
   Confidence grades the mapping LINK, not the data: a discrepancy found on a
   proven link (declared type doesn't match actual values, redesigned LoV) is
   a data-quality note — keep the confidence, flag it in the rationale +
   question log; don't downgrade to Low.
5. **Fill the helper columns** (mapping reason, confidence rationale,
   question log, transformation, quality rules) as brief bullets; cite the
   concrete evidence (value, DDL line, LoV domain, FK id).
6. **Multi-candidate**: `primary | secondary` in the base, ordered by
   evidence strength; state/join/confidence describe the PRIMARY only; the
   secondary gets a verify-in-DB question. Never silently drop a human pick —
   demote it to secondary with a question.

Column-vs-tag heuristic: a fact with a small closed vocabulary that anyone
might FILTER on (mapping type, cardinality, disposition, risk tier) deserves
its own dropdown column — in-cell tags are the fallback for facts that are
per-bullet or genuinely free-text (HARD/SOFT rule classes, rationale). Users
consistently prefer the column; the cost of an insert is usually smaller
than feared when placed right of all formula-referenced columns.

Batching: **group agents by EVIDENCE FAMILY, not by deliverable structure**
(sheet/section) — see §4. Fan out read-only mapping agents that return
structured row decisions, then apply in ONE writer pass (parallel writers on
one workbook corrupt or deadlock).
- **Pilot gate:** before any bulk fill, show the user ONE full section's
  proposed mapping + helper columns for sign-off; on multi-sheet engagements,
  pilot the first sheet through the FULL pipeline and get sign-off before
  dispatching the fleet on the remaining sheets.

**Durability gate — a cell you patched is only FIXED if the generator re-emits it.**
On any workbook that is generated from a decision store, a hand-patched cell that the
builder would not reproduce is theatre: the next build reverts it. Prove durability
before reporting a fix.

- **The cheap proof is a round-trip diff** (`harvest`-style: workbook → store,
  reporting rows that differ). Zero differences means the literal cells agree.
- **That proof is BLIND to formula cells.** A harvest that skips anything starting
  with `=` — the correct behaviour, since a formula is the workbook's own logic —
  never compares the guarded references you just patched. Measured: after writing 15
  inherited references, the round-trip reported **0 differences** while the store
  still held the old literals underneath and the builder would emit only **2** of the
  15. Thirteen cells would have silently reverted.
- **So for formulas, prove it the other way:** call the builder's link-derivation
  function and assert your cells appear in its output. If they do not, the underlying
  records still disagree and must be fixed *there*, not in the sheet.
- **Corollary for scope.** A structural rule read off the workbook ("child empty +
  parent populated ⇒ restore the link") wanted **51** cells; the fixed generator
  emitted **29**. The 22-cell gap was not a shortfall — those families have children
  that genuinely disagree, where the builder is designed to refuse. Patching them
  would have invented a decision that is the reviewer's to make and lost it at the
  next build. Report the gap; do not fill it.
- **Vocabulary lint:** after merging agent results and before the writer
  pass, validate every enum-valued output cell against the adapter's exact
  vocabulary tokens — agents drift on token spelling, and the read-back audit
  can't catch a consistently-wrong token. **Lint VERIFIER output too, not just
  mapper output** — a skeptic's replacement value is prose by instinct
  (`N:1 (asset -> BANK)`, `Medium / M2 (column confirmed…)`) and lands straight
  in a dropdown cell, where it silently becomes its own "grade" in every count.
  Prefer NORMALISING to rejecting: longest-canonical-token match, then move the
  residue to Notes, so the agent's reasoning survives and the cell stays
  filterable. Same rule wherever CODE composes a cell from an agent-authored
  field: agents annotate their picks (`REGION.REGION_ID (NUMBER(20), 203 rows)`),
  so peel the identifier before interpolating it into generated SQL — and prefer
  the agent's own expression when it already looks like SQL.

### Phase D — Apply
Single-writer pass per the adapter's editing constraints
([references/safe-editing.md](references/safe-editing.md)). Verify after:
spot-check applied cells, recount state distributions, confirm dashboards/
formulas still compute, confirm macro/control integrity if applicable.

### Phase E — Validation
Run the adversarial harness in [references/validation.md](references/validation.md):
six validator lenses (reverse coverage, net-new challenge, inferred audit,
mapped-row verification, method critique, type consistency) → deduplicate →
skeptic verification (findings default to refuted) → report. **No edits until
the user signs off**, then apply per the fix conventions.

### Phase F — Handoff artifacts
Findings table ranked by impact, method recommendations, updated run log in
the project playbook, reference-data asks (LoV/domain table exports), and
open questions routed to the right owner (DB team vs business).

### Phase G — Retrospective (mandatory; this is how the skill improves)
The skill treats every engagement as training data for itself. During the
run, keep a **learnings buffer**: the moment anything surprises you — a step
fails, the user corrects course, a tool betrays you, a convention proves
wrong — write one line down immediately (surprises reconstructed from memory
at the end are the ones you lose). At the end of the run (or when the user
says wrap up):
1. Diff plan vs. actual: which phases deviated and why.
2. Classify each learning:
   - **Generic-method** → edit the relevant skill file in place
     (SKILL.md / safe-editing / validation / workbook-contract /
     best-practices). Keep the references CURATED — fold the lesson into the
     existing text where it belongs; don't bolt on appendices.
   - **Project-specific** → update the project adapter and/or playbook.
3. Append one dated summary line per learning to the **project's** learnings file
   (adapter-side, e.g. `STTM/STTM_LEARNINGS.md`) — pointers, not prose. Engagement
   history does not belong in this skill: it grew to 62.7 KB (~16k tokens) of
   project-specific entries here before being moved out on 2026-08-11, and the
   skill was instructing every run to skim it.
4. If the engagement contradicted the skill and the skill was right, note
   the near-miss too — the log is for both directions.
**Retrospective at MILESTONES, not at wrap-up (2026-09-09).** Context compaction is
automatic and unannounced; a session that reaches it with an unflushed learnings
buffer loses the lessons, and the user notices ("you compacted the session before
reflecting on and updating the skills"). Flush the buffer — skill, adapter, memory — at
every confirmed lesson: after each approved fix lands, after each correction from the
user, before any long tool sequence once the conversation is already long. A wrap-up
retrospective is the LAST flush, never the only one.

A run that updates nothing is suspicious: either the run was trivial or the
retrospective was skipped.

## Script hygiene — four rules

An audit of one mature engagement (100 scripts, six weeks) found 25 broken and 6
superseded scripts still sitting on the live path. The telling detail: the project
adapter had **already documented** several as dead. The knowledge was written down;
the files were never moved. **Documenting supersession is not performing it.**

Four rules, each cheap to enforce mechanically:

1. **Supersede in place; archive in the same change.** When a new script replaces an
   old one, set the old one's `@status` to `SUPERSEDED-BY <path>`, move it to
   `_archive/` preserving its relative path, and update the script index — in the one
   change. A superseded file left on the live path is indistinguishable from a working
   one, and the filename never says which.
2. **A second module gets a registry entry, not a `_<module>` copy.** Forking per
   module produced 12 module-suffixed files and two dashboard builders sharing 8
   byte-identical function bodies (including a 5.4 KB `style_chart`). Parameterise:
   one script, one `MODULES` dict, consumers taking the module as an argument.
3. **Resolve columns BY HEADER NAME, never by index.** One insert at column A made
   every integer constant in one script one place stale; it then matched 0 rows where
   104 qualified and still exited 0. If you must cache indices, generate them into a
   machine-readable layout manifest and diff constants against it in CI.
4. **Status is computed, not declared.** Declared status rots exactly like a
   hand-maintained column map. Declare the judgement (`LIVE` / `ONE-SHOT` /
   `SUPERSEDED-BY`), but VERIFY the facts: does each declared target path exist, does
   each column constant still match the live header, does anything still import this.

Corollary for any script that modifies N rows: **assert N > 0.** Asserting file
integrity while asserting nothing about the work is how a total no-op ships green.

## 3. Working style

- Prefer bulk array I/O over per-cell loops; guard sheet-extent lookups
  (a failed read must not silently reuse the previous sheet's data).
- Make every count reconcile: state distributions before/after, KPI cards
  before/after structural edits. A number that moved unexpectedly is a
  finding, not noise.
- Convert relative statements ("recently", "the last run") into absolute
  dates in logs and adapters.
- When the engagement's playbook and this skill disagree, the project
  playbook wins — then update the adapter to record the divergence.
- **Keep the generic core generic — don't let a project's data-authoring
  quirks leak into the skill.** When one engagement's source contains
  something non-standard (e.g. non-field artifacts authored into a data
  dictionary, an idiosyncratic column, a bespoke state), handle it in the
  project ADAPTER, never by adding a special case to this skill. Only
  patterns that genuinely recur across engagements earn a place in the core.
  When unsure, adapter first — a lean, general skill outlives every project.

### Working beside another session (2026-09-09)
The user runs several sessions in parallel on purpose (one runs the AS-IS queries and
keeps the query log, another owns the generators). A popup "yes" in one session is NOT a
licence to write while the other is live — coordinate first, and the LEAD session
orchestrates:
- **Board file in the project** (`kb/SESSION_BOARD.md`): ownership table (which session
  owns which artefact family), standing rules, an "already run" list, dated announcements
  appended newest-last. Read it before the first write of the day; append after every write.
- **One writer per artefact family.** A ruling applied in one session and a harvest run in
  the other silently reverts it; two sessions analysing the same result grid is pure waste.
- **Message, then VERIFY — never trust the acknowledgement.** Queued ≠ read ≠ done. Proof
  that the other session acted is (a) your message quoted in ITS transcript with an explicit
  acceptance, (b) its line on the board, (c) the mtime of the file it was to change. Check all
  three before building on its work.
- **Corrections travel as (claim, evidence, corrected value)** — the artefact and the figure
  that shows it, never "you were wrong about X". The other session can then dispute one
  item without re-arguing the rest.
- **Consolidate when the second session costs more than it saves:** message latency of a
  whole turn, a transcript near a thousand messages (every message you send costs a full
  re-read there), or assignments that need files it does not own. Have it write its
  in-flight state on the board, stop it, take the work over from the artefacts on disk.
- **Default = solo, no fan-out.** Never launch a workflow or agent fleet without an explicit
  yes for THIS task; a second session is the user's fan-out, not yours.

## 3b. Evidence and confidence — what you looked at vs what you claim

Almost every expensive mistake in this work is one mistake: **the gap between the
thing you actually looked at and the thing you then asserted.** Not missing
evidence — each of the failures below HAD evidence. The error was reporting at a
confidence the evidence did not carry, and a reader cannot tell the difference
unless you say. Measured in one session: **five claims reported as findings, then
retracted.** Measured on one audit run: **318 findings, of which 232 were the
scanner's own false positives.**

The four checks below are in the order the work happens.

### Before you claim ABSENCE

False claims of absence — "no source exists", "the join key isn't derivable",
"that bind is unresolvable" — send a question to a human who finds the answer on
disk in a minute. Before writing *unresolvable / blocked / no source / not there*:

1. **Which artifact would hold this if it existed?** Name it. Engagements
   accumulate a declared-FK export, a lookup/domain export, an app trace, a
   column catalog. Keep a per-project registry of "for question X, look in Y".
   **Check it as a grep, not as a recollection** — `grep -ril <TABLE> kb/` costs
   one call. Measured: an id decode was written up as "in no file on disk" and
   logged as a client ask, while a note measured two days earlier gave the join
   at 100% coverage, the label column, and the junk value to exclude. The
   registry existed; it was not grepped.
2. **Did I check the OBSERVED record as well as the declared one?** For a
   relationship that means the trace's value co-reference, not only the FK
   export — see the two-sources table above. For a table it means measured
   activity, not the ERD's opinion of it.
3. **Does the TARGET model already answer it?** The delivered model carries
   declared references, enumerations and entity splits that decide questions you
   are about to route to a human. Measured 2026-09-07: rows were written up as
   "no mapping yet — find the AS-IS source" when the answer was in the target
   itself — one attribute's reference was declared in the model, and another was
   settled by which of three request entities actually receives migrated rows.
4. **Would the CLIENT recognise this as absent?** An entity you are about to rule
   net-new is a claim about their business. Measured 2026-09-07: a cancellation
   request was ruled net-new and the reviewer answered "we have it in the legacy
   system" — the
   search had been for a *table name*, not for the process. Before ruling a whole
   entity net-new, say which process it belongs to and how you looked for it.
5. **Did I read the WHOLE set, or its head?** Count and group before
   characterising (`Counter(...)`, not `rows[:5]`).
6. **Did I search every level?** A value expected at the root of a hierarchy is
   often a child, and vice versa.
7. **Is the sentinel really a null?** Exports write `"[NULL]"`, `"-1"`, `"N/A"`
   and `""` as text. A falsy test on those reports an empty set as fact.

State the evidence that WOULD unblock it. Usually you then find it.

### A CORRELATION HAS TWO SOURCES — declared, and OBSERVED

**A join is never proven or disproven from one artifact.** Every engagement that
has both an ERD and an application trace holds two independent records of how
tables relate, and they answer different questions:

| | DECLARED (the FK export / ERD) | OBSERVED (the trace's value co-reference) |
|---|---|---|
| what it is | what the schema *says* relates | what the application *did* relate |
| good for | completeness across the schema, direction, cardinality | proof a relationship is USED, and by which flow |
| blind to | relationships the DB never declared as constraints | anything the tester did not exercise |
| grade it as | `Inferred (ERD/schema)` | `Trace — FK id` |

**MEASURED, 2026-09-07.** A row needed the hop
`TRANSACTION.SCHEDULE_ID -> PAYMENT_PLAN`. The declared-FK
export gives PAYMENT_PLAN three children and TRANSACTION is not
among them, so I wrote the hop up as unsupported and left the row undecided —
"the column exists; the relationship does not". The reviewer's one-line
correction: *you can infer this FK from the trace values.* The trace's
Co-Reference sheet had it outright — the two columns share **all** their captured
values (2 of 2 distinct on each side), both exercised on INSERT, sample values
printed, and a sibling entry showing the application FILTERING the parent on that
id and then updating it. The application performs a join the ERD never declared.

So, as rules:

- **ERD-absence is not absence of the relationship.** A declared-FK export
  records constraints someone chose to write down. Plenty of real joins live only
  in application code.
- **Trace-absence is not absence either** — it only means that screen was never
  exercised. The same standing rule that applies to tables (a lookup is never
  traced) applies to *relationships* identically.
- **So check BOTH before asserting either way**, and name which one you used.
  "Not in the ERD" is half an answer; so is "not in the trace".
- **A co-reference proves EXISTENCE and USE, never POPULATION.** "Confirmed on 2
  values" means the relationship is real and the app uses it — on the two rows the
  tester touched. It says nothing about the other million. Quote the N, and if the
  extract's volume depends on it, that is a query, not an inference.
- **Direction still needs deciding.** A co-reference row often reads
  `A.col = B.col (direction unresolved)`. Shared values do not say which side is
  the parent; take that from the declared FK, the PK-ness of the column, or the
  entity's meaning — and say which.

Where the co-reference sheet lives and what its columns mean belongs in the
adapter's evidence registry. If the adapter does not name it, that is the bug —
fix the adapter, because the next run will make the same mistake.

### A REVIEWER'S LIST IS A SAMPLE OF CLASSES, NOT AN INVENTORY OF DEFECTS

When a reviewer sends you defects, they have read a fraction of the sheet. Fix
exactly what they named and you have fixed the fraction they had time to read.

Measured: a reviewer sent ~26 examples over three messages, then said plainly
*"they were just examples of what went wrong for you to check similar issues"*.
Half had been generalised into generator rules; the other half had been fixed
only on the row named. Sweeping the six patterns across the sheet found two more
real defects **and** proved four of the six had no other instances at all —
which is itself the answer, and only knowable by looking.

- **For every item, decide CLASS or INSTANCE before fixing it.** "This filter is
  wrong" is a class; "this row's date is 2019 not 2018" is an instance.
- **Write the class check as CODE and keep it**, so the next reviewer's example
  costs one run rather than one pass. It also stops the count drifting: the same
  sweep re-run after each fix is what proves the class is closed.
- **Report both numbers — hits and defects.** They are rarely close.

### Before you trust YOUR OWN checker

A static audit is a claim about a mapping made by code you wrote minutes ago.
Report it and you inherit its bugs as your findings.

- **Sample 3-5 hits per check class and verify them by hand first.** The 232
  false positives above were: a placeholder schema prefix read as an unbound
  alias, a multi-column concat notation (`A | B | C`) read as one column name,
  TO-BE shared-PK rows read as inheritance violations, whole net-new entities
  flagged for their N/A cells, derived-table aliases (`FROM (SELECT …) x`)
  reported as missing bindings.
- **Say how many you discarded.** "77 findings, from 318 raw after removing 232
  scanner artifacts" is a trustworthy number; "318 findings" is not.
- **A tightened check is worth more than a reported hit.** Measured over one
  sweep: an `*_ID`-into-a-text-target check went 4 hits -> 0 real once it learned
  that a target NAMED `…ID`/`…Number`/`…Code` legitimately holds an identifier;
  a boolean-target check went 37 -> 0 once it learned `Active <- IS_DELETED` is
  the established derivation. Both would have been pure noise. A sixth check
  returned 224 hits of near-total junk and was DELETED rather than shipped,
  because the question it asked was already answered properly elsewhere.
- **THE FIX FOR A CLASS CAN CREATE A NEW MEMBER OF IT.** Measured, four hours
  apart: a ruling written to fix "a lookup whose every column reads one source
  column" pointed all five columns of a different lookup at one free-text
  column — including `Active`, which is a state flag and cannot be a label. The
  sweep caught it; review had not. **Re-run the class check AFTER applying the
  class fix**, not only before.
- **A metric moving is not evidence the fix is right.** Read 3 concrete outputs
  of any derived rule before wiring it in. A shortest-path join derived from
  declared FKs improved the defect count and produced routes like
  `REQUEST → BLOCKING_DETAILS → PERSON` — a route that EXISTS is not the route
  the business MEANS. *Structure is not meaning* constrains YOUR inferences, not
  just the sheet's.
- **If two consecutive runs do not move the number, stop editing and print the
  real input.** A test written against your assumption of the input proves only
  your assumption.

### Before you REPORT — say how you know

Every retraction in that session came from reading a PROXY instead of the thing:

| what was read | what was claimed | what was true |
|---|---|---|
| a `head`-truncated grep | "no dangling references" | one, in the part never printed |
| a gate's message | "the lint scans narrative text" | it read an undecided, pipe-separated source pick |
| the decision store | "the two modules contradict" | built rows byte-identical; a mirror resolves to its ANCHOR |
| a half-remembered line | "blank English labels truncate the lists" | 332 of 332 members had a label; "70 distinct of 72" meant duplicates |
| a derived register | "this checker misaligns its columns" | the checker was sound; the file predated a renumber |

- **Every claim states its measurement.** "0 dangling refs (grep over `*.py`,
  untruncated)" is a finding. "No dangling refs" is a hypothesis wearing a
  finding's clothes. If you cannot name the command, or the file and line, say
  "I think" — then go and measure it.
- **`head`, `tail` and a result cap are TRUNCATIONS, not summaries.** A capped
  search that comes back empty proves nothing about what it did not print. Count
  first (`| wc -l`), then look.
- **A store, a cache and a deliverable are three different artifacts.** The build
  applies overlays — mirrors, deltas, overrides, derived columns — that exist in
  none of the inputs. Open the artifact the reader reads before naming a defect.
- **A derived file inherits the staleness of the run that made it.** After any
  identifier change, regenerate before reading, or every join is confidently
  wrong — and a stale register does not announce itself.
- **Retract in one line and move on.** "I said X; measured, it is Y" costs a
  sentence. Defending it costs the reader's trust in everything else.

### A COUNT IS NOT A REFERENT — establish what the counted rows ARE before judging them
Two peer-session conclusions reversed in one afternoon (2026-09-09), both the same shape:
"the pin drops 15 of 37 parents, so it is harmful" (the 15 were mis-tagged uploads of other
request types — the pin was protective) and "1,002 out-of-range dates will hard-fail the
load" (none was on a mapped request type). And the id family: "STATUS_ID spans four domains"
because ids read 9xxx / 900xx / 350xxx — one lookup by DOMAIN_TYPE_ID showed one domain; an
id PREFIX is a spelling, membership is a join. Before a count becomes a verdict: join the
counted rows to the population the verdict is about (mapped scope, real parent, real
domain) and re-add the arithmetic from the pasted grid yourself — "77 vs 76 = fan-out" was
a mis-added column. When auditing another agent's analysis, sort its claims into verified /
over-claimed / reversed, and give each correction as (its claim, the artefact + figure, the
corrected value).

### Before you WRITE a field

Writing a value into a generated artifact is not the same as it surviving there.
Three ways a correct-looking write goes wrong, all measured:

- **The generator rewrites the field later.** A Sample written onto an
  association row was right when written and wrong after the build re-pointed
  that row's Source at its parent id — leaving a sample with no source column,
  which the gate then failed. Twice, because the second guard still tested the
  CURRENT source instead of the mapping TYPE that predicts the rewrite.
- **The field is a machine column.** Freezing a derived value (a value list, a
  classification) into the decision store shadows the generator forever — the
  store now outranks the rule that was supposed to own it.
- **The field is downstream of another.** Change a source pick and its dependents
  — filter, expression, validation, evidence, confidence — are invalidated by
  rule. Writing one without the others leaves a row that contradicts itself.

- **The rule is keyed on the wrong thing.** A class rule must key on what the row
  actually READS, not on where it sits. Measured 2026-09-07: a request-type
  re-scope keyed on the target MODULE moved every row in that module to the new
  type — including an attachment entity whose own filter reads the *file*
  discriminator and which therefore had to keep the old one. The class was right;
  the key was wrong. **After applying a class rule, list its members and check
  each individually** — a rule that is right for 30 of 33 rows is a defect in 3,
  not a success in 30.

Find where the generator sets the column, and what invalidates it. If it is
derived, fix the derivation — that is the difference between a fix that survives
the next rebuild and one that does not.

### Before you trust a CLEAN audit

An audit that passes is a claim about your CHECKS, not about the mapping. Ask what
the check is physically able to see before you report that nothing is wrong.

Measured, 2026-09-06: five gap classes had run green over 65 defective cells for
weeks. Every one of them — `PROFILE_MISSING`, `SAMPLE_MISSING`, `NO_EVIDENCE`,
`LOV_EMPTY`, `*_UNPROVEN` — asks the same question in different costumes: **is
this cell empty?** A cell that is filled and WRONG fires nothing. The register
was measuring COMPLETENESS and being read as CORRECTNESS.

- **Name the question your checks actually ask.** If every one reduces to "is
  this blank", you have no correctness coverage at all, however many gates
  there are and however green they run.
- **PRINT THE DENOMINATOR BESIDE EVERY ZERO.** A check that had nothing to look
  at reads exactly like a check that found nothing. Before reporting a module
  clean, state how many rows each check was ABLE to fire on: "0 findings over 15
  candidate rows" is a result; "0 findings" is not. Measured: one module returned
  zero on three of five classes, and the pass only meant something once the
  denominators (15 id-sourced rows, 10 boolean targets, 10 sourced lookups) were
  shown to be non-zero.
- **A correctness check compares two things the artifact already knows.** It
  needs no new data: a filter's decoded lookup label against the row's own
  process name; rows of one entity against each other; a member cited against
  the dimension it claims to come from; a table measured live against the set
  the mapping references. Every defect in that episode was visible from data
  already on disk — nobody had written the comparison.
- **Make the implicit explicit, then enforce it.** The scope lived in 65 free-text
  cells where no reviewer could see it. Turning it into ONE declared table —
  process → permitted members — is what made the contradiction visible, and the
  declaration is now the thing under review instead of 65 prose fragments.
- **Report a contested rule as CONTESTED, in the gate.** A finding you cannot yet
  resolve belongs in the check's output with a `DISPUTED` status, not in a note
  someone has to remember. It then cannot go quiet.
- **A rule lands where it is WIRED, not where it is written.** The deliverable
  imported one function from the analysis pipeline and none of its policies, so
  a rule added to the shared module reached the analysis workbook and silently
  did nothing to the artifact the client reads. When you add a row-level rule,
  grep for every surface that builds rows and wire all of them, or none.

**And the scoping rule underneath that episode, which generalises:** a filter
derived from a trace inherits the trace's blind spot. The trace covers the
screens somebody happened to open — it is evidence about those screens and
silent about every sibling process. Before pinning a scope, read the PROCESS's
own name and find the reference member whose label matches it. In that data the
neighbouring module got this right by luck of coverage: its "Issuance of No
Objection Letter" process pinned the type literally named "NOL", on all nine
rows, while the module the trace covered pinned "Open grant file" on all 61
rows of a process named "Issuance of a grant certificate".

**Related, same shape:** when a child table's own foreign keys are empty, that
is not proof the rows are unreachable — ask which PARENT points at it. A
57-row register was written off as an unjoinable stub because its own
`*_ID` columns were NULL; the join was on the request side all along, populated
on exactly 57 rows, and the write-off had already reached a memory note and a
client answer.

## 3b-i. THE EVIDENCE LADDER — escalate by cost, resolve by question class

A confidence grade is worthless if it records how sure you felt. It is worth a lot if it records
**which artifact settled the cell**. Two orderings do that, and they are NOT the same ordering —
conflating them is how grades turn back into opinions.

### Escalation order — cheapest first, and the rung a cell settles at IS its grade

Work a cell UP the ladder only as far as it needs to go. **Never climb a rung you do not need, and
never claim a rung you did not reach.**

| rung | artifact class | what it settles | cost |
|---|---|---|---|
| 1 | offline column catalog / optimizer stats | population, nullability, distincts, ranges | free |
| 2 | reference-data export (the lookup workbook) | decodes, seed ids, member lists | free |
| 3 | the ERD's graded FKs + view lineage | joins and grain | free |
| 4 | application traces | what the app actually WRITES | free |
| 5 | a registered query whose answer is CAPTURED | anything measured on live data | needs a window |
| 6 | an open question to the business | nothing — **this is a GAP, not evidence** | blocks |

Rung 6 is not a grade. A cell resting on it is an open item and is reported as one.

### Authority order — per QUESTION CLASS, never global

There is no single ranking of sources. Ask what the question is, then use the artifact that can
answer *that*:

| question | authority | it outranks | silent on |
|---|---|---|---|
| what does this TARGET attribute MEAN? | the vendor's own model documentation | your data dictionary, your inference | everything else |
| does the app WRITE this table? | the trace, INSERT/UPDATE vs SELECT-only | the DD, the ERD, name similarity | tables the traced flow never touched |
| what is the current population? | a captured query result | the catalog (stats, and a staging copy is not production) | anything unmeasured |
| what joins to what? | the ERD's FKs and shipped view lineage | name similarity, ALWAYS | joins the ERD never declared |
| what does this SOURCE column mean? | the DD — but evidence outranks it once a query has run | inference | columns the DD never covered |

**Never test EXISTENCE against a sparse artifact.** Vendor documentation is typically written for a
minority of attributes. Blank means "nobody wrote a doc", not "the attribute is undocumented".
Measure the coverage and state it before you rely on the column.

### What the evidence column must carry

**A column that records how confident we felt is not evidence; a column that names the artifact is.**
A closed vocabulary of evidence CLASSES ("trace value", "inferred", "derived") cannot be re-checked:
it does not say *which* trace, which row, or when. Write the rung AND the pointer:
`R4 trace: <mapping-export> <TABLE>.<COLUMN> (INSERT)` or `R1 catalog: <TABLE> N rows, M nulls`.

### Two fingerprint rules, each learned by getting it wrong

1. **Compare a grade to the STORE, not to the rendered cell.** In a generated workbook the displayed
   source is the pick *after every overlay has run*; the grade was fingerprinted against the pick *as
   decided*. Comparing grade-to-display measures your overlays, not your mapping. On one engagement
   that produced a 220-row staleness warning of which 218 were harmless — and everyone had learned to
   ignore it, which is worse than not having the check. Against the decision store it was 9 rows.
2. **Never identify an artifact by NAME MATCHING across the two sides of a migration.** Target module
   names and source table names collide (a target module `Policy` beside a source table
   `POLICY`), and a case-insensitive lookup will silently mislabel whole classes of association
   row. Discriminate STRUCTURALLY: a target reference is `Module.Table.Column` (3 segments), a source
   pick is `TABLE.COLUMN` (2). Count segments.

### Measure against the right referent, or the gap you report will not exist

Three counts on one engagement looked like large defect classes and were artifacts of the wrong
denominator:
* **Filter coverage per ROW read as 99% missing.** The entity predicate is collapsed onto each
  entity's ID row by policy, so coverage is a PER-ENTITY question: the real figure was 50 of 111.
* **Join paths "missing" on 61 + 43 rows.** A row reading its entity's OWN driver table needs no hop.
  Scored against each entity's driver, the genuine gaps were 0 and 1.
* **Entities with a shared driver and no scope filter looked like 10.** A table reached THROUGH a
  join takes no entity scope of its own; all 10 were join-reached, so the true count was 0.
Before reporting a gap, state what the denominator is and why that is the population that must be
non-empty.

## 3c. A row must be COMPLETE and LOADABLE — not merely sourced

A Source cell is the beginning of a mapping, not the end of one. A reviewer
reading fourteen rows in one pass found nine defects of this kind, none of which
is a wrong source — every one is a row that is internally incomplete, internally
inconsistent, or physically unable to load. Run this list over any row you touch.

**1. Both halves of the source, or neither.** Table and column are ONE fact.
Measured: a name attribute left with `sys-generated` as its Source Table and a
real column beside it — a row that reads as sourced and resolves to nothing.

**2. A source with no join path is not a mapping.** Unless the row reads the
entity's own driver table, the reader needs the hop. Measured: an email attribute
carried a source and an empty Join / Lookup Path, so nobody could tell which of
three contact tables it came through.

**3. The TARGET TYPE is part of the contract.** A mapping that cannot load is not
a mapping. Three shapes of this, all measured in one session:
   - `int` target fed an alphanumeric business reference (`EI-25-0000057`)
   - `bit` / Boolean target fed a column that is not two-valued
   - `decimal(?,?)` — an UNPINNED target, which cannot be built at all
   Compare the target type to the source type and to your own expression BEFORE
   grading the row. If they disagree, the ask is "widen the target or change the
   rule", and it belongs on the row.

**4. Code, or label?** A target attribute wants one or the other, and its NAME and
TYPE tell you which. Measured: a department attribute was mapped to
`…_GROUP_ID` when the target wanted the human-readable value — the decode hop was
missing, not the source. An `nvarchar` target named for a thing, fed an id, is
this defect every time.

**5. One carrier unless the second has its OWN evidence.** Do not add a fallback
for symmetry. Measured: a cash-amount attribute acquired a second source on a
payment table when the asset table was the only correct carrier — a `A | B` pick
implies you have evidence for B, and a reviewer will ask for it.

**6. A net-new entity's ASSOCIATIONS are net-new too.** If every attribute of an
entity is `New (No Migration)`, its FK rows cannot be `Resolve at Load` — there is
no parent row to resolve against. Measured: a board entity with nine net-new
attributes still carried an association row pointing at a migrated parent.

**7. Closed conventions come from the PEER ROWS, not from feel.** The token an
identity row carries, the disposition a seed row takes — read what the sibling
rows of the same kind already use and match it. Measured: one entity's ID row
said `N/A` where every comparable ID row in the module said `sys-generated`.

**8. A newly-found table needs an ACTIVITY verdict and a TEST-DATA verdict before
you map it.** Row count alone is not the test. Measured: a court-session table
matched its target entity attribute-for-attribute and was mapped on that strength
— it holds 2 rows, both authored by the same login, with free text that renders as
mojibake. Its sibling was correctly declined for exactly these signs (`'test'`,
`'Test'` as low values). State both verdicts on the row; "structurally perfect and
substantively empty" is a finding, not a mapping.

**9. When the target wants a LOOKUP MEMBER, look in the lookup.** Before writing
"no source", check whether the reference export already holds a member for it —
a document-type list, a status domain, a category table. The question "is there a
document type for evaluation?" is answered by reading the 60-row export, not by
reasoning about it.

None of these needs a query or a client answer. They are all readable from the
workbook, the catalog and the target model — which is why leaving them for a
reviewer to find is the expensive way to work.

## 3d. A display decision must never reach the data

In any propose/apply pair, the applied column is sacred. Eliding a proposed
value for readability (`str(new)[:90]`) and then applying it verbatim destroyed
71 extraction filters, each cut mid-token, silently dropping scope predicates.

- Elide only the display column; never the one a later step writes.
- Have the applier **refuse** a write whose new value is a strict prefix of the
  existing value — a prefix is information loss by definition.
- Detect it with a length histogram: many cells at *exactly* N characters is
  never natural text.

## 3e. Constructive, never destructive — a run must only add

A rebuild is not a fresh start. The workbook carries human edits, the stores
carry rulings, and derived registers carry ids that a renumber invalidates. A
run that forgets any of those subtracts work that was already paid for.

- **Harvest before you build.** A bare rebuild overwrites hand edits with
  generated values. Harvest -> patch -> build -> diff is ONE sequence, not four
  optional steps. If a harvest reports rows it could not match, stop: an
  unmatched row is an edit about to be lost.
- **An id change invalidates every derived register.** After renumbering,
  regenerate them and assert zero unknown ids. Measured: a gap register kept
  535 of 2,941 rows pointing at ids that no longer existed, silently, because
  nothing re-ran it. The assertion is one line — `ids not in registry == 0`.
- **Prose citations move too.** Ids appear inside Comment/Rule/Note text and
  across modules ("PARITY: aligned to CM-0310"). Repoint them through the
  old->new crosswalk and then assert no citation names an id absent from the
  registry. 478 such citations moved in one renumber; a missed one is a
  reference to a row that no longer exists.
- **A ruling only overwrites the keys it OWNS.** Deleting a bad field from a
  ruling leaves the bad value in the store — it is no longer asserted, so
  nothing corrects it. Set it explicitly to the right value instead.
- **Regenerate downstream, or say plainly that you did not.** Coverage reports,
  validation workbooks and control tables built before the rebuild are stale the
  moment it lands.

## 3f. A generated deliverable is a STACK of layers — fix the class in every one of them

On any engagement where a workbook or a query pack is GENERATED from a decision store, the row a
reader sees is the store plus every overlay the build applies on top: a model layer that shadows
undecided rows, verifier-correction deltas, a generic lookup/seed spec, a reviewer-pick pass,
row-level policies, an ID-row collapse. Each is legitimate on its own. Together they mean:

- **A class fix to the store is not a fix until every layer that can rewrite the field agrees.**
  Measured (2026-09-09): 44 rows re-pinned in the store, correct in the review sheet, invisible in the
  extract — 14 verifier deltas still held the old value. Grep every store for the old value before
  saying "closed", then read the BUILT output, not the sheet.
- **Overlays fill blanks; a decided value wins.** A generic lookup spec that overwrites a row's join
  path describes one decode route — wrong for any entity that reaches the lookup another way, and it
  can even choose the extract's driving table. The seed's identity filter is the LOOKUP's scope, never
  the fact entity's.
- **A later dated ruling beats an earlier human pick.** The reviewer's column is ground truth for
  what they decided THEN; a row whose own text records a supersession must not be re-pointed by a pass
  that re-applies the review sheet. Skip it and print the skipped ids, so the exception is visible.
- **Every row rule runs on every surface.** A pass wired into the review workbook only (or the
  deliverable only) produces two artifacts that disagree, and the one nobody reads is the one that
  ships. Grep both entry points for the rule before declaring it live. Corollary: a "live rows only"
  filter in the composer must still see the row that carries the entity's filter (an ID row is not
  live) — an extract lost every WHERE that way.
- **An amendment guarded by "already applied?" reverts itself** when an older ruling owns the same
  field: the guard skips, the older text re-applies. Amendments are unconditional and idempotent.
- **Instrument the live run instead of reading the code.** Three readings of one pass produced three
  wrong theories; monkeypatching the pass and printing the row before/after found the cause (a
  corrupted byte in a regex) in one run.
- **Never author a file that contains a backslash through a shell heredoc.** Escapes are eaten
  silently; a regex that still compiles then matches nothing. Write the file with a file-writing tool
  and scan for control bytes afterwards.

- **A per-module tool run once is a claim about ONE module.** When a chain has `--module` flags, a
  bare invocation silently picks a default; a "nothing changed" statement on the other module is then
  untested. Run every step once per module and back the claim with that module's artifact timestamp.
- **A copy that runs on another engine must be re-lexed for that engine.** A query composed for one
  target (SQL Server: `FROM T AS a` is fine) handed to another (Oracle: ORA-00933) fails on line one.
  Grep the pack for the destination engine's known refusals before anyone pastes it.
- **One filter per entity, and only one copy of it.** Child rows carrying prose copies of the entity's
  scope come back through the collapse and can re-drive the extract; after a scope change, read the
  composed FROM/WHERE, never the cell.

**A fix that removes joins re-routes the extract's DRIVER (2026-09-09).** Turning row-level joins into per-row
subqueries is the right cure for a fan-out, but the composer picks its driving table from the join chains; with the
chains gone it fell back to counting source tables and made the many-row table (or a lookup's decode table) the
driver — the fan-out came back through the FROM clause with the parent left unjoined. After any ruling that
changes join paths, read the built FROM / JOIN lines of every affected entity and diff the driver list of the whole
module against the previous build; a READY count that did not move proves nothing about grain.

## 3g. Working UNATTENDED — when the reviewer is asleep

Some engagements ask for a long run with nobody to answer questions ("overnight", "without
interruptions"). That instruction, and only that instruction, suspends the ask-first rules for that
run. It does not lower the bar; it moves where the accountability sits.

- **Nothing may block.** No question ends a turn. Something suspect: investigate until you can
  decide, decide, apply it revertibly, record it. A step fails: fix, retry or work around; if truly
  blocked, finish everything that does not depend on it and record the block with what you tried.
- **Every change must be undoable in ONE step.** A row goes through a dated ruling carrying the
  run's tag; a class goes into the generator inside a tagged block; a document is backed up first.
  Never an in-place edit with nothing behind it. The revert step belongs in the record, written out.
- **A decisions register is the deliverable that makes solo decisions acceptable**: id, APPLIED or
  RECOMMENDED, rows, evidence, options considered, choice and why, exact revert. RECOMMENDED is how
  you hand back a call that is genuinely the owner's (a re-root, a grain change, a sign-off) without
  blocking on it.
- **Reconstruct the owner's standing intent before auditing anything.** Their own words across the
  period under review — in the transcripts, in the log's quoted lines — become two registers: what
  they have in mind, and the mistake classes they have had to correct. Check every finding against
  both; a finding that contradicts a dated ruling is a finding about the ruling, not the cell.
- **Bucket the rows before auditing them**: settled by a dated ruling (out of scope unless captured
  evidence contradicts it), machine-derived with evidence (verify the evidence still holds), no
  evidence or flagged (the primary set). Print the counts. Never re-derive what the log settles.
- **Deliver in the order the morning needs**: the runnable pack first, then the register, then the
  audit report, then the handoff entry — and state plainly what was left undone and what blocked it.

## 4. Token economics — pay for a discovery once

Mapping engagements are agent-heavy, so cost discipline is part of the method,
not an afterthought. The rule behind all of it: **every expensive discovery must
end as a cheap artifact** — if you learned it by reading something big, the
output is a small file that answers it next time. None of this trades away
quality; the adversarial passes, verification and QA gates are unchanged. What
shrinks is redundant discovery.

**Cost tracks AGENT COUNT, not field count.** Measured on a real pilot: 9 agents,
1.14M subagent tokens, 12 fields — ~127k tokens per agent, each handling only
2–5 fields. Nearly all of it is per-agent warm-up (reading the adapter and
digests, querying the ERD/catalog, profiling columns). Consequences:

1. **Group agents by evidence family, not by sheet/section.** The same source
   tables serve fields scattered across many sheets (payment tables served 32
   fields across 4 sheets in that engagement). Sheet-batching makes 3–4 agents
   each rediscover the same schema; family-batching pays once. Measured on the
   same remaining scope: ~21 agents (~2.5M tokens) by sheet vs ~10 agents
   (~1.2M) by family, at the same quality bar.
2. **Pilot ONCE, then do the rest in a single pass.** A pilot's real product is
   not its rows — it is the settled conventions plus the artifacts (evidence
   contract, index files, adjudicated anchor/discriminator patterns). Pay that
   discovery cost once; repeating it per sheet is waste. Later batches should
   cost *less per field* than the pilot — if they don't, the pilot's output was
   never captured properly. Note the tension with the Phase C pilot gate: pilot
   for CONVENTIONS and sign-off, not as a template for how to batch the rest.
3. **Write ONE evidence-contract file** — canonical sources, precedence,
   vocabularies, and **forbidden inputs** — and have agent prompts cite its
   path instead of restating it (~2k tokens saved per agent, and every agent
   works from one set of facts). Forbidden inputs matter: raw upstream captures
   (trace/log files) already parsed into a workbook must be off-limits. An
   audit found 1 of 12 agents re-parsing a multi-megabyte raw trace the
   pipeline had already extracted in full.
4. **Index the source system's own artifacts before dispatching anyone.**
   Shipped database VIEWS are join paths hand-written by the original
   developers — the highest-value join evidence available. Index them once
   (name → output columns → referenced tables → line number) so an agent looks
   one up instead of hunting for it.
5. **Collapse repeats in CODE first** — deterministic dedup/mirroring is free
   and more reliable than agent re-derivation. But **never auto-collapse on
   name similarity alone**: a fuzzy pass at 0.86 yielded 2 true typo-twins and
   2 false positives ("Opening Balance" vs "Closing Balance"; "Manager Name"
   vs "Manager Phone"). Name similarity proposes; the entity/join-path test
   from Phase B decides.
6. **Probe scripts print ≤30 lines and write the detail to disk.** A 300-line
   dump to surface 12 lines of signal is a recurring, invisible tax.
7. **Grep to locate, then read the block** — never a whole large file to find
   one definition.
8. **Kill stale second sources on sight.** A generator whose column list
   predates the current layout will send the next session on a full
   re-investigation; flag or fix it in the same change.

**Wall-clock is a separate lever from tokens** — it tracks the number of
SEQUENTIAL stages times the slowest agent in each. Measured on one engagement:
mapping 49 fields took 18 min (parallel, well-briefed), but verification took
100 min because each of 3 lens-skeptics re-read ALL rows, and a synthesizer
spent 47 min re-emitting every row before dying at the output-token ceiling.
Same-quality latency rules:

- **No synthesizer agent.** Merge mapper+verifier outputs in CODE, surface only
  the rows where verifiers genuinely conflict, adjudicate those few (half
  resolve with a catalog lookup, not judgment). An agent that re-emits all rows
  is both the slowest stage and an output-ceiling risk.
- **Lint BEFORE agent verification** — the deterministic checks (existence,
  type-fit, dead columns, discriminators, aggregates, vocabulary, cross-field
  same-column contamination) run in seconds and shrink what agents must check.
- **Shard verification by evidence family, not lens-by-lens over everything:**
  each family's verifier applies ALL lens checklists to its ~10 rows. Same
  checks, partitioned — ~4× less verification wall-clock.
- **Verifiers return DELTAS only.** Output generation is the slow part of a
  turn; never have an agent restate unchanged rows.
- **Grep-able evidence beats workbook I/O:** one openpyxl load of a large
  catalog costs an agent 15–30 s and recurs dozens of times per run.
- The floor is map → verify → apply. Do not compress below that — the
  adversarial pass IS the quality bar.

## 5. References

| File | Read when |
|---|---|
| [references/workbook-contract.md](references/workbook-contract.md) | Creating/validating a project adapter |
| [references/safe-editing.md](references/safe-editing.md) | Before the first write to any workbook |
| [references/validation.md](references/validation.md) | Running Phase E |
| [references/lineage-diff.md](references/lineage-diff.md) | The user asks whether recent changes lost anything, or to check a deliverable against its backups |
| [references/best-practices.md](references/best-practices.md) | Designing a new workbook layout; challenging an existing one; industry conventions & anti-patterns |
| [references/inheritance.md](references/inheritance.md) | The target model has generalisation/specialisation (Mendix, supertype/subtype): map-once rule, shared PK/FK ID, parent-scope-⊇-children rule, safe collapse of duplicated rows |
| [references/source-system-window.md](references/source-system-window.md) | You get time-boxed access to the legacy database. Deriving the query pack from open mapping cells (it is usually ~10% the size you expect), making every query name the cells it settles, and applying what comes back. **The general craft of interrogating a database — wide-query shapes, the paste-back contract, Oracle round-trip killers, the two-phase environment protocol, and keeping a query estate — moved to the `sql-query-estate` skill; load that alongside this one whenever you are about to write SQL against the source.** |
| `scripts/check_parent_scope.py` | Mechanical check that every generalisation parent's extraction scope subsumes the union of its children's — run it whenever a hierarchy's filters change |
| the project's own learnings/engagement log (adapter-side) | Phase G. Read it when you need the history of a specific decision — **not** by default: these logs reach tens of thousands of tokens and are the single largest avoidable context cost on an STTM task |

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
6. **Type audit:** the picked column must be able to hold a value of the
   target's data type (boolean target ⇒ boolean-ish source or derived rule —
   never a name/text column; percentage ⇒ share/percentage column;
   attachment ⇒ document home; date ⇒ date column). Composite target types
   map EVERY component.
7. **Map everything.** Every target field gets a best-effort source or an
   explicit net-new. Blanks are QA failures — use explicit N/A tokens so
   "intentionally empty" is distinguishable from "forgot".
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

12. **A SOURCE CHANGE IS NOT ONE CELL. Identify and REBUILD every column that was
    derived from the old pick — never leave the previous values standing.** When the
    source moves, the cells that explained, validated, sampled, typed and graded the
    old pick are silently invalidated. They do not look broken; they look authoritative,
    and a reviewer reads them as current.
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
| `scripts/check_parent_scope.py` | Mechanical check that every generalisation parent's extraction scope subsumes the union of its children's — run it whenever a hierarchy's filters change |
| the project's own learnings/engagement log (adapter-side) | Phase G. Read it when you need the history of a specific decision — **not** by default: these logs reach tens of thousands of tokens and are the single largest avoidable context cost on an STTM task |

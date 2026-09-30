# The validation harness — adversarial verification of a mapping pass

A mapping pass always looks plausible; validation is how it becomes
trustworthy. The harness has three stages: **independent validators** find
candidate defects, **skeptics** try to kill each finding, and only survivors
reach the user. Nothing is applied without sign-off.

## Stage 1 — Eleven validator lenses (run independently, in parallel)

Each validator reads the SAME ground-truth extracts (workbook TSV + evidence
TSVs) — never the live workbook — and returns structured findings:
`row/field · current · verdict · evidence · proposed change · impact`.

Verdicts: **CONFIRMED / OVERTURN / ADJUST / MISSING**. Every non-CONFIRMED
finding must cite exact evidence (a captured value, a DDL view/line, an LoV
domain, an FK id) and a concrete proposed change. Impact: high = wrong
migration mapping; medium = wrong confidence/state/join/extraction; low =
cosmetic. The engagement's settled rules are validated in their
*application* — never re-litigated by a validator.

- **V0 Dependent-column staleness (run FIRST, and after every source change)**:
  for each row whose source pick changed since the last pass, check the columns
  that were derived from the OLD pick — `Expression`, `Rule`, `Join / Lookup Path`,
  `Extraction Filter`, `Confidence Reason`, `Evidence`, `Sample`,
  `Source Data Type`, `Validation Check`, `Null Handling`, `On No Match`,
  `Risk Tier`, `Quality Rules`, `LoV Values`, `Cardinality`. Three machine checks:
  (a) the cell still equals a known prior generator default; (b) it contains a
  type-word contradicting the new mapping type; (c) it cites a source column that
  appears in neither the join nor the filter columns. (a) and (b) are defects —
  rebuild them. (c) is a JUDGEMENT: text naming the old column because it records
  why that pick was rejected is decision provenance and must survive. Measured on
  one engagement: 20 rows flagged, 3 stale templates, 17 rulings correctly kept.
  This lens exists because a stale dependent never fails a normal gate — it reads
  as authoritative. See SKILL.md non-negotiable 12.
- **V1 Reverse coverage (source → target)**: every source column with
  evidence of application use that no target row references — should a
  target field consume it? Counts (not lists) the legitimately homeless.
- **V2 Net-new challenge**: for every row flagged net-new, hunt for a source
  anyway (captured-but-unmapped columns, FK resolutions, DDL, ERD,
  cross-module). CONFIRMED or OVERTURN.
- **V3 Inferred audit**: for every schema-inferred row: does the column
  exist; is it the best candidate; is the state honest (not actually
  evidence-backed — or actually evidence-backed and under-flagged); is the
  confidence per rubric?
- **V4 Mapped-row verification**: for every evidence-backed row: sample
  value ↔ column consistency; target LoV domain vs source domain; data type
  vs sample; join path vs the canonical schema graph; extraction condition
  has its discriminators; state + confidence per rules.
- **V5 Method critique**: structure/logic gaps only (state vocabulary
  granularity, reviewer usability, replication risks, reference-data asks).
  Produces recommendations, not row findings. Cheap health check to include:
  the evidence-state × confidence combinations must be non-degenerate — if
  states and confidence collapse to a 1:1 mapping, one of the two columns is
  not being independently assessed (a healthy sheet shows many combos).
- **V6 Type consistency**: every capture row's base pick can HOLD the
  target data type; composite types have every component mapped. (This lens
  exists because type mismatches are what users catch after sign-off.)
- **V7 Row-internal coherence (the cheapest lens, run it first)**: does each row's
  Source Column agree with the row's OWN other fields — its rule, its expression, its
  join path, its sample, its recorded type? A pick can be wrong while everything
  around it is right, and no cross-row lens sees it. Two real slips found this way,
  both a single mis-set cell on an otherwise-correct row:
  - an association FK picked `ORDER.ORDER_NUMBER` while its join path, its
    `NUMBER(20)` type, its numeric sample and its identical twin row all named
    `ORDER.CUSTOMER_ID`;
  - another picked a bank NAME while its rule, expression, join and sample all named
    `…DETAIL.BANK_ID` — and an FK must carry an id, not a label.

  Two rules make this lens precise rather than noisy. **First, restrict it to
  association/FK rows**: on any other mapping type a label IS the point, so "the join
  names an id but the pick is a name" is the normal decode pattern
  (`join on DOMAIN_DATA_ID, take DATA_DESC_EN`) and firing on it produced 51
  findings of which ~49 were correct-by-design. **Second, "is this pick an
  identifier?" is a question about TYPE or NAME, never name alone** — numeric ids
  like `OWNERREF` and `CASETYPECODE` do not end in `_ID`, while a varchar
  `ASSOCIATED_OBJECT_ID` holding `TO_CHAR(REQUEST_ID)` does. Accept either signal.
  Restricted that way the lens returned exactly the two real slips and nothing else.

  **A type cross-check is a wasting asset.** The second slip was exposed by its
  pre-existing type (`NUMBER(20) | VARCHAR2(100)` on a single-column pick — the
  `NUMBER(20)` belonged to the id). Normalising types from the catalogue destroyed
  that signal, because types then derive FROM the pick and can no longer contradict
  it. Run this lens BEFORE any type normalisation, or run it against the pre-
  normalisation backup.

- **V8 Orphan codes — join CHILD to LOOKUP, never lookup to lookup.** For every
  child column carrying a lookup's key, anti-join it back to that lookup and
  count the rows whose code does not resolve. Each one is a decode that fails at
  load time. **The direction is the whole lens.** Comparing a lookup's id SET
  across two environments — the obvious check, and a cheap one — cannot see a
  child pointing at an id the lookup lacks: measured, `PAYMENT_METHOD` was
  identical on both environments and marked settled, while
  `TRANSACTION` referenced 5 distinct `PAYMENT_METHOD_ID` values
  against a 4-row lookup. Thirteen anti-joins over one engagement returned
  eleven clean and two real defects (5 rows and 3 rows) that every earlier
  check had passed.
- **V9 Coalesce coverage — every term in an `A | B | C` pick must EARN its
  place.** For each pair, count A-only / B-only / both / neither, and where
  both are populated, equal vs different. Four outcomes, four different
  actions:
  - a side populated where the other is not ⇒ the pick must be a COALESCE, in
    that order;
  - both populated and always equal ⇒ arbitrary, take the cheaper join;
  - both populated and sometimes different ⇒ a real semantic choice needing a
    ruling, which no COALESCE can paper over (measured: two share columns
    agreed on 1,082 rows and disagreed on 30);
  - **a term that is CONSTANT is worse than absent.** `FILE_PARTY.OWNER_SHARE`
    was 100% populated across 1,503 rows with **one** distinct value (100) — a
    perfect name match for the target, and information-free. `N_DISTINCT = 1`
    on a fully-populated column is the placeholder signature; a null sweep
    scores it as perfect coverage. Carry the row count of the most common value
    alongside the distinct count, since "sparse but real" and "one default plus
    noise" have the same `N_SET`.
- **V10 Lookup liveness — "unchanged since 2010" does NOT mean stable.** That is
  simply what a lookup does. The claim only becomes testable by asking whether
  live rows still REFERENCE the values, and how recent those rows are. What makes
  a frozen lookup notable is that its PEERS are maintained: on one engagement
  five lookups had taken no write since 2010-2013 while six others were current
  to 2022-2025. Usage split those five three ways — three were stable and heavily
  used (one had all 3 of its values referenced by 1,556 rows), one was
  near-abandoned (3 of 15 values, 36 referencing rows out of 1,504), and one was
  effectively dead (6 rows, 1 distinct value). Migrating a dead lookup into a new
  system is a BA decision, not an inference.

**Testing a validator: a green gate proves nothing until you have watched it go red.**
A new check reported "0 failures" on a file that still contained two known defects —
it was passing vacuously (a regex escape had been mangled into a control character, so
the pattern matched nothing, and the source *looked* correct). Before trusting any gate
you add: copy the file, **reintroduce the defect it exists to catch**, assert it fires,
restore, assert it clears. That round trip also exposes false positives — it is what
demoted three of the five initial hits above to correct-by-design.

## Stage 2 — Skeptic verification

1. Deduplicate by (row + normalized proposal).
2. OVERTURN/MISSING → **2 skeptics** (lenses: *does-the-evidence-exist* and
   *rules-and-roles* — does the proposal violate settled conventions?).
   ADJUST → 1 skeptic. Skeptics re-check evidence themselves and **default
   to refuted**.
3. All skeptics refute → **KILLED** (never applied). Some refute →
   **CONTESTED** (apply only in skeptic-corrected form). None →
   **VERIFIED**.

Skeptics catch two recurring failure modes: evidence misread (value exists
but belongs to a different entity/section) and rule violation (upgrade
proposals that break state semantics or grading caps).

## Stage 3 — Report, sign-off, fix conventions

Deliver: findings table ranked by impact · method recommendations ·
per-validator counts · killed/contested log. **No workbook edits before the
user signs off.** Then apply with these conventions:

- Multi-candidate picks: `primary | secondary`, evidence-strength order;
  metadata describes the primary only.
- **Never silently drop a human pick** a finding overturns — demote it to a
  piped secondary + a verify-in-source question (one evidence session cannot
  prove absence).
- An OVERTURN therefore usually means promote + demote, not delete.
- Log the run (counts, applied/killed) as an appendix in the project
  playbook; carry V5 recommendations into the next engagement's structure.

## Settling a "are these two source columns the same thing?" question

When two source columns look like duplicates of one target concept (two FKs
to the same lookup, an id repeated on parent and child), do not settle it by
reading schema or by eyeballing rows. Run a **bucket reconciliation**: one
mutually-exclusive CASE over the joined set, counted.

Make the buckets a genuine partition, and always include the failure states,
not just match/differ: `MATCH · DIFFERENT · NULL on one side · ORPHAN (join
key resolves to nothing)`. The empty buckets are findings in their own right —
zero orphans proves the join key is safe to migrate on, and zero nulls proves
a nullable column is effectively mandatory in that scope. Both are facts you
would otherwise have to assume.

Three things fall out of one query:
1. **The ruling** — a material DIFFERENT bucket means two roles, not one.
2. **The acceptance test** — the observed split is what the migrated result
   must reproduce. A derived target field gets its expected distribution for
   free; carry it onto the row as the post-migration check.
3. **The scope** — group the same query by source type/status to see whether
   divergence concentrates somewhere, which often decides whether the rule is
   global or type-specific.

**Count what REACHED the comparison, not what entered the loop.** `assert
rows > 0` passes happily while every row is skipped on a lookup miss, and the
run then reports a clean bill from zero actual comparisons — the most
expensive kind of false negative, because it looks like a pass. Emit a
skipped/unmatched counter next to the processed counter and assert it is zero
(or explain it). Real instance: a "which rows are at risk?" check reported
**0 rows at risk** having scanned 733 rows and skipped all 733, because a
module-scoped id registry was never loaded and every key lookup missed. The
skip counter was the only thing that revealed it.

**The partition trap: bucket counts MUST sum to the known total.** If they
exceed it, a join fanned out (typically a bridge/association table with N rows
per parent) and the CASE was evaluated per *joined row* rather than per
*entity* — so one entity lands in several buckets and `COUNT(DISTINCT id)` per
bucket double-counts. Collapse to one row per entity FIRST
(`MAX(CASE WHEN … THEN 1 ELSE 0 END)` grouped by the entity key), then
classify. Watch CASE ordering too: whichever condition is tested first steals
every row satisfying both, silently draining the later buckets. Measured
instance: three buckets summing to 1,721 against a true 1,376, with ~116 rows
stolen from the correct bucket by test order. **Always assert the sum.**

## Scaling notes

- Validators and skeptics are read-only agents over extracts → safe to run
  highly parallel (per-lens, and within a lens per-section for big sheets).
- Track agent completion counts; a validator that returned nothing is a
  failed run to re-dispatch, not a clean bill.
- Findings on rows belonging to shared/common sections apply to every sheet
  referencing them — fix once, propagate by reference.

## The extract audit — a mapping can be RIGHT while its extract is unrunnable

A validated STTM does not imply a working extract. Measured on one engagement:
**30 of 31 extracts flagged READY would not execute at all** against the source
Oracle instance — on a sheet whose mappings had already passed the full harness
above. The Stage 1 lenses read mapping *rows*; these read the query *text* and
its *output shape*. Run them the first time a stored query is executed, and
again after any source re-pick.

- **E1 Dialect and splice.** Recurring, in order of frequency: schema prefixes
  that exist in no target environment; `AS` before a *table* alias (invalid in
  Oracle); `NULLIF(x,'')`, which is always NULL there because `''` IS NULL; and
  **spliced pseudo-SQL** — an entire `SELECT … FROM lookup WHERE …` pasted where a
  column expression belongs, closed with `AS "Target_Col__code"`. That last one is
  the signature of a **two-phase lookup resolution captured as text**: someone
  recorded *how the code will be resolved after the target LoV is seeded* in the
  slot meant for the source column. It is not a typo to fix — it is a phase-2
  dependency to schedule.
- **E2 Polymorphic parent reference needs a discriminator AND a cast.** A child
  table serving many parent types (documents, notes, comments) keys on
  `owner_type + owner_id`. Two failures, always together: without the owner-type
  token the same numeric id collides across families; and the id column is
  routinely `VARCHAR2` holding `TO_CHAR(parent_id)`, so a numeric `IN` list raises
  ORA-01722 (implicit `TO_NUMBER` on the *column*, not the literal). Quote every
  literal, and census the tokens first — measured, one entity family resolved to
  three live tokens carrying 5,082 / 659 / 179 documents, and only the first was
  in the extract.
- **E3 Value precedence: parent total vs child grain — and zero-as-empty.** The
  same money attribute lives on the parent and on the child. `NVL(parent, child)`
  is defeated by zero: `NVL(0, x)` returns 0, so a zero-filled parent silently
  wins and the child is never read. Always `NVL(NULLIF(parent,0), child)`.
  Direction is settled by coverage **and** grain, not preference: measured, the
  child column was populated on 17 of 1,295 rows, so parent-first was correct —
  and the only real exposure was the handful of *multi-child* parents, where a
  parent total is not attributable to one child. Suppress those to NULL rather
  than repeating the total N times.
- **E4 Inner joins on optional chains.** Every join on a nullable FK must be
  LEFT unless the mapping *intends* the filter. Measured on one entity: an inner
  join to its property table dropped **701 of 1,295** rows (no FK at all) and a
  second inner join dropped **1,289** — an extract that would have loaded 6 rows
  and reported success.
- **E5 `ROW_NUMBER()` as the target PK hides every grain defect.** It
  manufactures a distinct value per *output row*, so a fan-out cannot show up in
  the PK — it lands downstream as duplicate business keys. Measured: 1,737 output
  rows over 1,405 parents = **332 collisions**, while a separate inner join was
  dropping 79 parents entirely. **Assert `ROWS_OUT = COUNT(DISTINCT <legacy key>)`
  on every extract.** That single equality catches this whole class, and it is the
  cheapest check in this file.
- **E6 1-1 target vs 1-N source.** Where the target is one row per parent and the
  source is N per parent, collapse with a scalar subquery or an agree-or-NULL
  aggregate — never a join. Two entities whose stored SQL is **byte-identical** is
  the tell that one of them was never designed, only copied.
- **E7 Type-scoped extracts silently omit types.** A per-type extract
  (`WHERE type_id = n`) is complete only if the set of `n` covers the live
  population. Census the discriminator and diff it against the extract set:
  measured, 3 live rows of one type had no extract at all.
- **E8 `EXPECTED_VOLUME` is a claim, and it is usually the raw table count.**
  Measured corrections on one control table: **1,295** against a stored ~6, and
  **~554** against a stored **1,516,197** — the latter being the row count of the
  shared note table, unfiltered by owner type or note type. Recompute expected
  volume from the *repaired* query output, never from the table.

**A CASE census must handle NULL explicitly or it mis-attributes silently.**
`SUM(CASE WHEN REGEXP_LIKE(col,'^[0-9]+$') THEN 0 ELSE 1 END)` scores every NULL
as a *non-numeric value*. Reported that way as "2,252 / 10,316 / 1,232
non-numeric object ids" across three tables; one follow-up query proved all of
them simply NULL, and three findings evaporated. Give every census an explicit
`WHEN col IS NULL` arm and assert the buckets sum to the total — the same
discipline as the partition trap above. It is repeated here because it recurred
**in the same session in which it was written down**: a documented trap is not a
learned one until the check is mechanical.

## Three standing rules, each bought with a wasted source-system window

- **R1 Pre-flight against what you already hold, BEFORE writing a query.**
  Measured: **~17 of 38** queries sent during a closing database window asked for
  data already on disk — 10 were verbatim reference-lookup content sitting in a
  delivered workbook, 7 duplicated queries already in the engagement's own AS-IS
  query pack. **Four checks, each covering different ground:** the reference
  workbook's sheet names; the query pack's header comments; **the registered query
  log, which holds every question already asked together with its answer**; and
  **the schema catalogue's null counts**, which answer population questions
  outright. The third matters most and is the easiest to skip, because it catches a
  question you are silently RE-DERIVING rather than re-asking. Measured on the same
  engagement: a value-ordered runbook of "what to ask next window", written
  specifically to prevent redundancy, lost **four of its seven queries** to a
  query-log pre-flight run minutes after it was written — and one of those four had
  been billed as the single most valuable thing left to measure, while the log
  showed it fully answered the day before, with the opposite conclusion.
  **Pre-flight your own conclusions, not just your queries.** The split that makes
  it automatic: **reference/lookup content is already delivered — a live window is
  for transactional shape, grain and value questions only.** Under time pressure
  this rule is *more* important, not less; that is exactly when it gets skipped.
- **R2 Compare candidate columns BY VALUE, SIDE BY SIDE, in one query — never on
  coverage counts.** A populated column is not a correct mapping. Statistics can
  *rank* candidates; only values can *settle* them. One side-by-side SELECT over 7
  traced rows closed six open questions and overturned two picks: a "commercial
  name" fallback turned out to be a byte copy of the primary name while a
  genuinely bilingual `_EN` column sat unmapped, and a plausible "property number"
  candidate held a project reference, not a land number. Neither was visible in
  any coverage statistic — both columns were 100% populated. Put every suspected
  column in one SELECT list and read across the row.
- **R3 Structure from dev, aggregates from staging — and stamp provenance on
  every number.** The environments diverge in **population**, not merely in ids:
  measured, 12 asset types in dev against 7 in staging, and ~1,833 rows in one
  register in dev against 57 in staging. A dev count quoted as a migration volume
  is a defect. Dev answers *what shape is this column and what do its values look
  like*; staging answers *how many and how sparse*. Write the environment and the
  date beside every measurement, or the next pass cannot tell which numbers it is
  allowed to reuse — and will re-measure all of them.

## The cheapest decisive test for a candidate source: does the app WRITE it, or only READ it?

When two tables could carry a concept, a captured statement log (Oracle 10046, a query log, an
audit trail — anything that records the application's own SQL) settles it in one lookup, and it
outranks every count:

| the app's operation on that table | what it means for a pick |
|---|---|
| `INSERT` / `UPDATE` | **the application records the concept here.** This is where the business value lives. |
| `SELECT` only | **reference data** — for display, validation or decode. It can be a fallback or a lookup; it must never win precedence over a written table. |

**One caveat, and keep it NARROW: check WHO made the write.** A statement log captured during an
analyst's own tracing session contains the analyst's inserts as well as the business's. On one
engagement exactly ONE table in a 175-statement trace had been populated by the analyst rather
than by a business user, and reasoning from that single INSERT sent a pick the wrong way. The
fix is to confirm authorship for the one table you are leaning on — not to discount the log,
which was business-authored everywhere else and remains the primary authority. Over-correcting
here is worse than the original error, because it throws away the best evidence you have.

Measured instance, and it cost a wrong re-point that had to be withdrawn the same day. A 1-1
`UnitNumber` attribute could read either of two chains. Row counts said one thing and the trace
said the opposite:

- `THIRD_PARTY_PROP_UNITS` — **6 rows in the whole table**, but the trace shows an `INSERT`
  carrying the exact unit number typed into the screen.
- `UNIT` (6,806 rows) → `FLOOR` (1,256) → `PROPERTY` — trace shows `SELECT` only, 153 / 38 / 92
  reads, all "read / reference data from …".

So the six-row table holds *the endowed unit* and the 6,806-row table holds *the building's unit
register* — a different concept, reachable only 1:N with no selector. **Six rows meant the feature
is barely used, not that the source was wrong.** Re-pointing to the bigger table on coverage
grounds would have loaded "some unit of the building" into "which unit was endowed".

Two rules fall out:

- **A coverage figure must never be the REASON for a re-point.** It answers *how much will load*,
  never *what this column means*. Its home is null-handling, a cleansing row, or a business gap.
  A near-empty column whose meaning is established is a **business gap to declare**, not a source
  to swap — and swapping it silently changes what the field means for every downstream reader.
- **Read the row's own prose before proposing the change.** In the same instance the mapping row's
  own `question` field already recorded both facts I "discovered" from the catalogue — the six-row
  count *and* the 1:N-with-no-selector problem that was the answer to what I was about to get
  wrong. Accumulated reasoning lives in `question` / `join_path` / `mapping_logic` /
  `confidence_reason`; a pass that skips them re-derives or overturns what is already settled.
  When you do edit them, **append** — a replaced prose field destroys history that no rebuild can
  recover, and the two replacements caught on review that day would have deleted a live
  cross-module contradiction and an open business ask.

**The ordering that prevents this: meaning first (statement log, then the row's own prose, then the
data dictionary for grain), numbers LAST and only to size what meaning has already settled.**

## DDL and control-table deliverables — fitness is the namespace and the engine, not the syntax

A generated DDL / seed file can pass every check its own generator knows and still stop on the first
statement a DBA runs. Measured on one migration (2026-09-16): the first landing-schema DDL for two
modules copied a deployed reference file's naming habit for keys and indexes (`PK_<stem>`,
`IX_<stem>_01`) and so collided with the reference's own objects in the shared target schema on
**32 constraint and 20 index names**; both module files CREATEd the same two shared lookup tables,
so whichever ran second died at statement one; and four control-table rows carried the extract SQL
as a single text literal of 4,200–5,700 bytes, over Oracle's 4000-byte literal cap (ORA-01704) — a
limit the reference never reached, so the path had never been exercised. None of it was visible to a
gate that looked only at the file being written.

Before a generated SQL deliverable is called runnable, check it **against the world it lands in**, with
a parser that is not the generator:

1. **Namespace.** Parse every file that lands in the same schema — the deployed reference included —
   and assert the union of table, index and constraint names is collision-free. Names are unique per
   schema, not per file; a name copied from a reference is by definition already taken.
2. **One owner per shared object.** A table two modules read is created by exactly one file; the
   others only checkpoint that it exists. Two owners means the second run fails, always.
3. **Engine limits, in bytes.** Text literals ≤ 4000 bytes (or chunk them as `TO_CLOB('…') || …`),
   identifiers ≤ 30 bytes where the version is not guaranteed, national-character strings ≤ 2000
   chars, index keys inside the block-size limit. Syntax checkers see none of these.
4. **Operational instructions re-derived, not copied.** "Run on schema X" in a reference header was
   true for its author's connection; re-derive the login from the deployment facts on file (the
   pipeline's global parameters, linked services, datasets) and put a pre-check statement at the top
   of the file that FAILS in the wrong schema before anything destructive runs.
5. **Value fit, not only type fit.** When the loader refuses truncation, one over-length string fails
   a whole table. Generate one aggregate per extract — `COUNT(*)`, `MAX(LENGTH(col))` and the rows
   over each declared length — from the SHIPPED text, and run it before the first load.

And re-take every state line (READY counts, blocked rows) from the built artefact when the entry is
written; a number carried forward from an earlier paragraph is the one that turns out stale.

### Retiring a deliverable: remove the production path, do not flip a flag

When the client retires a sheet, a workbook or a report — usually because one consolidated
version replaces several per-module ones — a build chain will keep recreating everything
around it unless the retirement is made structural. The failure looks like this: the sheet
is on a `sheets_retired` skip list, so it genuinely stops appearing, and everyone declares
it done; meanwhile the dataset stage still computes its rows, a harvest step still reads
the sheet that is never there, the spec still sits in the sheet registry, the frozen inputs
still sit in the knowledge base, and the documentation still lists it as a sheet of the
workbook. The client sees the artefacts and the build log, not the skip list, and reports —
correctly — that the thing they retired is being recreated on every run.

Retire it in five moves, in this order:

1. **Remove it from the registry** the renderer iterates, not just from the skip list.
2. **Stop computing it** — the dataset key returns empty, and any harvest of its human
   columns is deleted with a comment saying where those columns live now.
3. **Gate it.** The renderer REFUSES to emit the retired name and says which file replaced
   it. A retirement expressed only as configuration is one lost dict entry from publishing
   again, and the gate is what makes the ruling survive the next refactor.
4. **Move the frozen inputs to `_backups/`**, so the tree stops showing a live artefact.
5. **Fix the documents that describe it** — the run contract, the deliverable table, the
   manifest. A stale line listing the retired sheet is usually what the reader is quoting.

**Keep the shared computation.** The consolidated report is normally built from the same
module, so the logic is not dead code even when every per-module caller is gone; only the
paths that produce the retired artefact are.

## Post-load audit lessons (added 2026-09-22, from a two-module landing-table review — client-anonymised)

Every check below found a real defect that the standard within-table battery (completeness, NULL census, grain,
value domains, referential keys) had passed.

1. **Join every child to its generalisation parent and count orphans** before trusting either table's completeness.
   Within-table checks and SRC-key checks against business parents cannot see an inheritance break. Two modules
   had 91–100% of child attachment rows with no parent row because the parent was driven from a different table
   than its children.
2. **Read the generalisation from the model export, never from the entity name.** "…Document" entities were
   counted as children of the attachment parent by name; the model said they specialise the platform's file
   entity. One grep on `specializes` in the model export corrects a census; a name never does.
3. **Before raising a "model question" or "vendor question", read the human answer columns** on the entity's
   identity row and its siblings (the review workbook's question log / answer, mirrored in the decision store).
   Five vendor answers settling a three-entity routing question were on file while two sessions measured for a day.
4. **A matching count is not the property.** 739 rows over 739 distinct keys, or `dupes = 0`, is the claim; a
   row total equal to the prediction is not. Measure the distinctness, the ratio, the invariant.
5. **Build a reconciling query from the artifact it reconciles against, read at the time.** A predicate remembered
   from earlier was narrower than the extract and could never have hit the total; embed the reconciling totals in the
   same statement so a wrong scope cannot pass unnoticed.
6. **Source and target usually cannot be joined** (different logins). Write every check as two single-schema
   queries with provably identical predicates and compare by hand; find the invariant the transformation must
   preserve and compute it on each side.
7. **A copy engine reads DECLARED precision, not values.** An explicit `CAST` on a computed numeric expression is
   what gives the driver a precision to report; a target type change can silently delete a cast the load relied on.
   Either pin the cast or widen the sink — and know which one you did.
8. **Run the generation chain per module, in order, after every store edit**, and diff the FULL generated output
   counting every changed query. A default module argument on one script hid a stale plan for three days; a
   `join_path` edit that removed a redundant join also flipped the query's driver, which only the full diff showed.
9. **A control table shared by modules is writable by any session** — a fingerprint is a snapshot with a
   timestamp. Re-fingerprint immediately before a run, not once per analysis.
10. **Registers dated to a staging copy do not size production.** Stamp every count the client will act on with its
    environment; a quality rule quoting a staging figure will fail post-load for the wrong reason.

## Post-load implementation lessons (2026-09-22 implementation, anonymised)
* **Inheritance and liveness:** when a parent entity carries the delete state (Status/Active column) and its specialisations do not, the
  children's extracts must not filter the deleted rows either — otherwise a deleted document has a parent row saying Deleted and no child row.
  Derive the child's state-carrying tables from the parent (model note "specializes X.Y"), do not hard-code per child.
* **Per-entity overlay lists are a layer above the mapping store.** A pass that rewrites a filter for named entities will silently undo a ruling
  written to the store; when a ruled cell does not appear in the built workbook, look for the list before doubting the store.
* **Hand-SQL overrides live in the composer's own form** (placeholders, comments, quoted aliases) and pin the hash of the text they replace.
  When a ruling moves that text, re-derive: fold the new composer text the same way, prove the SELECT list is unchanged, splice the new WHERE.
* **Control-column byte ceilings are real:** a scope change added 177 bytes and pushed one control row past a 4,000-byte VARCHAR2; recover
  bytes by inlining a lookup minimally (two columns, provably the same id assignment) rather than by dropping predicates.
* **Replay idempotency test:** apply → dry-run → 0 changed. History lines that embed current store state, or state-conditional repairs, break it.
* **Register gates:** an evidence sheet that must equal the union of two item lists refuses silently-added rows — read the builder's assertion
  before adding rows, and never leave a row only in the workbook (a regeneration deletes it).

# The validation harness — adversarial verification of a mapping pass

A mapping pass always looks plausible; validation is how it becomes
trustworthy. The harness has three stages: **independent validators** find
candidate defects, **skeptics** try to kill each finding, and only survivors
reach the user. Nothing is applied without sign-off.

## Stage 1 — Eight validator lenses (run independently, in parallel)

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

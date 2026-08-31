# Remediation patterns

A finding without a named remedy is a complaint. This is the vocabulary to reach for when
writing the `remediation` field, so the fix is something the modeller can look up rather
than something they have to invent.

Naming the pattern also disciplines the reviewer: if you cannot name the pattern that
fixes it, reconsider whether you have identified a real defect or an unfamiliar choice.

---

## Identity and keys

**Surrogate plus business key.** A surrogate for children to reference, and a unique
constraint on the business key so the *business* cannot duplicate. This is the fix for
`KEY-003`, and the important half is the unique constraint — the surrogate alone is the
anti-pattern. If no business key can be named, the entity has no identity, and that is a
larger finding than a missing constraint.

**Durable key.** Kimball's natural / durable / supernatural key distinction
(`SRC-KIM-DMT`): the natural key comes from the source, the durable key survives source
re-keying, and a supernatural key is minted when neither is trustworthy. Reach for this
when a review finds the "business key" is itself unstable — the answer is not a better
constraint but an additional key that the business controls.

**Single-column primary key for join simplicity.** `SRC-MSFT-WWI` adopts this
deliberately across a whole schema. The remedy for a wide composite (`KEY-004`) is to keep
the composite as a unique constraint and add a surrogate for children to reference — but
only where the join burden is real. Say which it is.

**Shared sequence across sibling tables.** WideWorldImporters uses one `TransactionID`
sequence for three transaction tables. Useful when sibling entities must share an id space
without sharing a table.

---

## Subtypes and generalisation

**Supertype / subtype tables.** The fix for `EVO-002` and `STR-002`: common attributes on
the supertype, a constrained discriminator, and each subtype's mandatory attributes on its
own table where they can be `NOT NULL`. Kimball's equivalent for heterogeneous products is
*supertype and subtype schemas* (`SRC-KIM-DMT`) — one supertype fact with common measures
plus per-type fact tables.

**Exclusive arc.** The fix for `INT-002`: several real nullable foreign keys plus a check
constraint permitting exactly one non-null. Verbose and enforceable, which is the trade
being made against a polymorphic pair.

**Common supertype target.** The other fix for `INT-002`: give every possible referent a
row in one supertype table, so a single real FK works. Better when the target set is
stable and the supertype is a real business concept; worse when it is invented purely to
satisfy the constraint.

**Generalisation vs one-to-one association (Mendix).** `SRC-MDX-GENASSOC` gives explicit
criteria: prefer one-to-one associations under high transaction volume or where the types
share few attributes, because inheritance locks the generalisation on write; prefer
inheritance for intensive searching and sorting on associated attributes. And settle it
before production data exists — removing a generalisation loses its relationships
permanently.

---

## Reference data and codes

**Code / label separation.** The fix for `REF-003` and `REF-004`: an immutable code that
is never edited, a mutable label for display. Join on the code, display the label.

**Source value / source concept / standard concept.** OMOP's three-column pattern
(`SRC-OMOP-CONV`), and the strongest available answer where data arrives from several
vocabularies: keep the verbatim source text for ETL and QA only, the source vocabulary's
concept, and the standard concept that all analytics use. Reach for this whenever a review
finds one column doing all three jobs.

**One table per code list.** The fix for `REF-002`. Where the proliferation of tiny tables
is genuinely the objection, the compromise is a typed view per list with an FK to it, or a
per-column `CHECK` — not a shared table with a discriminator.

**Junk dimension.** Kimball's fix for a fact table carrying a dozen low-cardinality flags:
collapse them into one dimension of observed combinations. Often the real remedy behind a
`REL-003` centipede finding.

---

## Time

Fowler's temporal patterns (`SRC-FOW-TIME`) are the vocabulary; pick by what has to be
answerable, not by what is easiest to store.

| Need | Pattern |
|---|---|
| Know what changed, cheaply | **Audit Log** — easy to write, awkward to query |
| Ask what was true on a date | **Effectivity** — explicit validity period on the row |
| Hide the temporal mechanics from most callers | **Temporal Property** — accessor parameterised by date |
| Read many attributes as at one date | **Snapshot** |
| Reference both the logical entity and a specific version | **Temporal Object** |
| Reproduce a report published before a correction | **Bitemporal** — actual time *and* record time |

**Bitemporality is the one reviewers under-reach for.** If the business backdates
corrections — payroll, billing, entitlement — a single time axis means rerunning last
month's report no longer reproduces the number that was published and acted on. That is
`TEM-008`, and the remedy is a second axis or an explicit, documented acceptance that
reports are not reproducible after a correction.

**SQL:2011 mechanisms** (`SRC-SQL2011`): system-versioned tables where the platform
maintains validity, application-time period tables with `WITHOUT OVERLAPS` for
business-declared periods. Prefer these to hand-rolled history tables where the platform
has them, and to soft-delete flags in every case.

**Kimball SCD types 0–7** (`SRC-KIM-DMT`). Do not write "use SCD Type 2" without checking
which type the model *intended*: Type 1 overwrite is correct for a corrected typo, Type 2
for a genuine change of state, Type 3 for a single alternate view, Type 4 mini-dimension
for rapidly-changing attributes, Type 6 for "current and historical in one row". A review
that names the wrong type is worse than one that says "the SCD type is not declared".

---

## Hierarchies

| Situation | Pattern |
|---|---|
| Shallow, write-heavy | **Adjacency list** + a cycle constraint |
| Deep reads, arbitrary depth | **Closure table** alongside the adjacency list |
| Deep reads, simple ancestry queries | **Materialised path** |
| Fixed depth, known levels | **Fixed-depth positional hierarchy** (Kimball) — levels as columns |
| Variable depth in a dimensional model | **Ragged hierarchy** with a bridge table (Kimball) |

The adjacency list is rarely wrong on its own; it is wrong *unguarded* (`INT-004`) or
*alone* where deep traversal is a routine access path.

---

## Universal structures

Silverston's *Data Model Resource Book* (`SRC-SIL-V1`, `SRC-SIL-V3`) and Hay's *Data Model
Patterns* (`SRC-HAY-DMP`) supply structures for the concepts every enterprise remodels
badly:

- **Party and Party Role.** One `Party` for people and organisations, with roles —
  customer, supplier, employee, beneficiary — as separate role entities rather than
  separate party tables. The fix whenever a review finds the same person duplicated across
  three tables because they play three roles.
- **Status pattern.** Status as a dated entity rather than a single current-value column,
  where status history matters. Applies uniformly to a party, a product, an order, a
  request.
- **Classification pattern.** Type and category hierarchies as data rather than as columns
  or table names.
- **Contact mechanism.** Addresses, phones and emails as one contact-mechanism structure
  with a purpose, rather than repeating groups (`STR-003`) on every party table.

These are worth naming even when you are not recommending a full rewrite: "this is the
Party/Role pattern's problem, and the standard structure is X" tells a modeller that their
difficulty is a known one with a known shape.

---

## Extension and evolution

**Typed extension table.** The disciplined answer where genuine open extension is
required (`STR-001`, `EVO-001`): one table per attribute family, typed, with real
constraints — not a single EAV triple and not `spare1..spare5`.

**Validated JSON column.** Acceptable where the shape is genuinely unknown at design time,
*provided* a schema validates it. The point is that the core stays enforceable and the
open part has a declared contract, rather than the whole model becoming soft.

**Extensions and profiles over schema change.** FHIR's approach (`SRC-FHIR-ARCH`): the
base resource covers the 20% of requirements meeting 80% of needs, and variation arrives
through extensions rather than new resources. Useful framing when a model is being widened
to accommodate one edge case at everyone else's cost.

**Reserved identifiers, never reused.** Protobuf's rule (`SRC-PROTO-UPD`): a deleted field
number is marked reserved and never reused, because reuse creates ambiguity when old data
meets new code. The direct analogue is a retired code value or a recycled key range — and
the same discipline applies to rule ids in this skill's own registry.

**Unknown enum member.** Protobuf requires the first enum value to be `0` and treats it as
the default, so a consumer reading data written by a newer schema has somewhere to put a
value it does not recognise. The fix for `EVO-003`.

---

## Localisation

**Translation table** keyed by (entity, attribute, language) — the fix for `LOC-001` past
two languages. Adding a language stops being a schema change.

**Parallel columns** remain correct for a small, fixed language set, and
`SRC-I18N-DB` says so. If you recommend a translation table for a two-language model with
no prospect of a third, say you are recommending it on flexibility grounds and name the
join cost being accepted — that is a `DEFENSIBLE_TRADEOFF_I_D_DIFFER`, not a violation.

**Canonical Gregorian with derived Hijri** — the fix for `LOC-003` and `LOC-004`. One
writable date in a real date type; the Hijri representation generated, and persisted only
where it must be indexed or filtered. Where official dates must match the register, name
the **Umm al-Qura** mapping specifically rather than "a Hijri conversion".

**Pattern-constrained identifier strings** for national ids and phone numbers — the fix
for `TYP-008`. Bounded character type plus a `CHECK`. State the algorithm behind any
claimed check-digit validation.

---

## Governance

**Column-level classification in the model.** DMBOK (`SRC-DAMA`) expects classification to
be part of the model rather than a side spreadsheet, so masking, retention and access
rules can read it. This is the remedy for `GOV-001` — and note that pure DDL has no
mechanism to express it, so on a DDL input the honest remedy is "carry classification in
the data dictionary and feed it to the review via `--format json`".

**Access rules consolidated per role.** Mendix `MDX-015` (MXP010/MXP013): one rule per
role, state transitions validated in microflows rather than encoded as access-rule
variations, and negated XPath rewritten as positive predicates.

**Description on every object.** WideWorldImporters puts one on every schema, table,
column, index and check constraint, and generated the schema from metadata specifically to
achieve that consistency. The remedy for `DOC-001` — with the caveat from `DOC-002` and
Hoberman's Completeness category that a description restating the name is gold plating,
not documentation.

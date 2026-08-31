# The rubric

`scripts/rules.py` is the authority. This file explains how to read it and how the score
is built; the tables at the end are a navigational aid regenerated from the registry, and
`selftest.py` fails if the two ever disagree on vocabulary.

---

## Two axes, one pass

Hoberman's ten categories and the detailed dimensions are not competing schemes — they
are different axes over the same findings. Every rule declares both, so one review pass
produces the industry-standard scorecard a client recognises **and** the dimension
breakdown an engineer can act on.

| Hoberman category (`SRC-HOB-SC`) | The question he asks | Fed by dimensions |
|---|---|---|
| Correctness | Does the model meet the requirements? | *needs a requirements document* |
| Completeness | Is the model complete, but without gold plating? | Documentation, Nullability, Semantics |
| Scheme | Does the model correspond to its schema level? | Scheme, Structure |
| Structure | Is it consistent, with integrity, following the basic rules? | Structure, Keys, Integrity, Relationships, Temporality |
| Abstraction | Is the generalization/specialization balance right? | Structure, Extensibility, ReferenceData |
| Standards | Does it follow the available rule and naming standards? | Semantics, Types, Nullability |
| Readability | Is the layout readable? | *needs a rendered diagram* |
| Definitions | Are definitions correct, complete, unambiguous? | Documentation |
| Consistency | Same structure and terminology throughout? | Consistency, ReferenceData, Semantics, Localisation |
| Data | Has a data profile been created; do attributes match reality? | Governance *(and needs a profile)* |

Five dimensions are **ours, not Hoberman's**, and reports must label them as such:
Temporality, Performance, Governance, Localisation, Extensibility. There is deliberately
no separate "platform" dimension — Mendix findings land on the same axes as everything
else, because a reader comparing two models should read the same rows.

---

## `NOT_ASSESSABLE` is a first-class result

Three of Hoberman's categories cannot be judged from a schema alone:

- **Correctness** needs a requirements or business-rules document.
- **Readability** needs a rendered diagram; DDL and spreadsheets have no layout.
- **Data** needs a profile — row counts, null rates, value distributions.

Absent those inputs, these categories return `NOT_ASSESSABLE` and **leave the
denominator**. This is not leniency. Scoring them zero would report *the reviewer's
missing inputs* as *the model's defects*, and a sponsor reading a 60% would blame the
model for a gap in the engagement. Pass `--has-requirements`, `--has-diagram` or
`--has-data-profile` to `parse_model.py` when you genuinely have them, and then actually
assess them.

The same principle governs `NOT_APPLICABLE`: rules a paradigm excludes are counted and
listed, never silently dropped, so "no missing-foreign-key findings" cannot be misread
as a pass when the paradigm has no foreign keys.

---

## Tier A and tier B

**Tier A — mechanical.** Decidable from the parsed model alone. `score_model.py` computes
these, and they are byte-for-byte reproducible; `selftest.py` proves it by scoring twice
and diffing. 88 of the 100 rules are tier A, and they carry the numeric score.

**Tier B — judged.** These need a judgement about meaning: is this entity
over-generalised, is the grain right, is this definition adequate, does this model need a
second time axis. Some have a **prescreen** that surfaces candidates mechanically
(`STR-002`, `STR-006`, `REL-003`); the rest are raised by a reviewer reading the model.

Tier-B output lands in `candidates_for_adjudication`, never in `findings`. It carries
`needs_adjudication: true`, `verdict: INSUFFICIENT_EVIDENCE` and `confidence: low` until
a human resolves it, and **contributes nothing to the score until then**. This is the
honest boundary: an LLM-scored rubric cannot be deterministic, so the number lives
entirely in the mechanical half and the judged half is reported as judgement.

---

## Severity

| Severity | Commits you to saying | Score penalty |
|---|---|---|
| `BLOCKER` | This loses data or makes the system return wrong answers. Fix before load. | 8.0 |
| `MAJOR` | This forces rework later, or defeats a constraint the design relies on. | 3.0 |
| `MINOR` | Hygiene. Cheap now, irritating forever if left. | 1.0 |
| `NOTE` | Preference or context-dependent. Raise it, do not insist. | 0.25 |

`BLOCKER` is deliberately steep: a scorecard that averages a data-loss defect into
insignificance is worse than no scorecard. Do not reach for it to add weight to an
argument — the ladder only works if `BLOCKER` keeps meaning what it says.

**Repeat damping.** The *n*th occurrence of the same rule contributes
`penalty × 0.55^(n−1)`, stopping below 0.05. Without it, one systemic issue across 200
tables zeroes every category on its own and the scorecard stops discriminating. With it,
breadth still costs more than a single instance but does not swamp everything else. The
factor lives in `assets/weights.json`; set it to 1.0 if you want volume to dominate.

---

## Verdicts

Every finding carries one, and the three-way split is the point:

| Verdict | Means |
|---|---|
| `VIOLATES_CITED_PRACTICE` | A named source says do not do this. Cite it. |
| `DEFENSIBLE_TRADEOFF_I_D_DIFFER` | A legitimate choice. Say what cost is being accepted, and do not pretend it is an error. |
| `INSUFFICIENT_EVIDENCE` | The inputs cannot settle it. Say what is missing. |

Tier-A findings default to `VIOLATES_CITED_PRACTICE`; a reviewer may downgrade one to
`DEFENSIBLE_TRADEOFF_I_D_DIFFER` on evidence, and should when the evidence supports it.
Downgrading is not weakness — a review that cannot tell a violation from a trade-off will
be dismissed wholesale by the person who built the model.

---

## What every finding must carry

`rule · object · severity · confidence · verdict · evidence · failure_scenario ·
remediation · source`

Two of those do most of the work:

- **`evidence`** — what *in this model* triggered it, specific enough to locate. "Names a
  reference to `CUSTOMER` (which has a key) but no foreign key constraint is declared"
  beats "missing FK".
- **`failure_scenario`** — concrete inputs or state producing a wrong result. "A LIKE
  '%,7,%' search also matches 17 and 70" beats "this is bad practice". A finding without
  a failure scenario is an aesthetic preference wearing a severity label, and it is the
  first thing a defensive modeller will attack.

---

## Structure is not meaning

A completeness statistic, a partition, or a clean type never establishes what a column
*means*. `NOT NULL` on `STATUS` tells you a value is always present, not that it is the
right value or that two systems agree what it denotes. Never raise the confidence of one
finding on the strength of a different column's evidence, and never let a coverage
percentage stand in for a definition — `DOC-003` exists precisely because a description
that restates the name satisfies a metric and informs nobody.

---

## Rules by dimension

Regenerated from `scripts/rules.py`. Tier `A` = mechanical and scored; tier `B` =
judged, reported as a candidate. Paradigms: `all` = every paradigm, `relational` =
oltp+dim+vault, otherwise listed.

### Structure

| Rule | Sev | Tier | Paradigms | Source | Checks for |
|---|---|---|---|---|---|
| `STR-001` | MAJ | A | all | KAR-SAP1 | Entity-Attribute-Value table used as schema |
| `STR-002` | MAJ | B | all | HOB-SC | Over-generalised entity |
| `STR-003` | MAJ | A | all | KAR-SAP1 | Repeating group in numbered columns |
| `STR-004` | MAJ | A | all | KAR-SAP1 | Table-per-period proliferation (Metadata Tribbles) |
| `STR-005` | min | A | all | SIMSION | Very wide table |
| `STR-006` | MAJ | B | dim | KIM-DMT | Fact table grain not declared |
| `MDX-013` | MAJ | A | mendix | MDX-PERF | Temporary or UI-state association on a persistable entity |
| `MDX-016` | min | B | mendix | MDX-DM | Persistability chosen by default rather than deliberately |
| `MDX-020` | MAJ | A | mendix | MDX-STORAGE | Attribute declared on both a specialisation and its generalisation |

### Keys

| Rule | Sev | Tier | Paradigms | Source | Checks for |
|---|---|---|---|---|---|
| `KEY-001` | min | A | relational | SQLSG | Primary key named bare `id` |
| `KEY-002` | **BLK** | A | relational | KAR-SAP1 | Table has no primary key |
| `KEY-003` | **BLK** | A | relational | KAR-SAP1 | Surrogate key with no unique constraint on the business key |
| `KEY-004` | note | A | relational | MSFT-WWI | Wide composite primary key |
| `KEY-005` | MAJ | A | relational | DATE | Primary key on a mutable descriptive column |
| `KEY-006` | **BLK** | A | relational | KAR-SAP1 | Key or identifier stored in an approximate numeric type |
| `KEY-007` | MAJ | A | relational | PAGILA | Associative table admits duplicate pairs |
| `KEY-008` | **BLK** | A | dim | KIM-DMT | Type 2 dimension keyed on its natural key |
| `MDX-001` | **BLK** | A | mendix | MDX-VALID | Business key with no Unique validation rule |

### Integrity

| Rule | Sev | Tier | Paradigms | Source | Checks for |
|---|---|---|---|---|---|
| `INT-001` | MAJ | A | relational | KAR-SAP1 | Foreign-key-shaped column with no declared constraint |
| `INT-002` | **BLK** | A | relational | KAR-SAP1 | Polymorphic association |
| `INT-003` | min | A | relational | SQLSG | Foreign key with no ON DELETE / ON UPDATE action declared |
| `INT-004` | MAJ | A | relational | KAR-SAP1 | Self-referencing hierarchy with no cycle or depth control |
| `INT-005` | **BLK** | A | relational | DATE | Foreign key type does not match the referenced key type |
| `INT-006` | **BLK** | A | relational | DATE | Foreign key references a table with no primary or unique key |
| `INT-007` | MAJ | A | relational | SIMSION | Mutually mandatory foreign keys between two tables |
| `INT-008` | MAJ | B | relational | SIMSION | Shared attribute on parent and child with nothing forcing them to agree |
| `MDX-002` | MAJ | A | mendix | MDX-ASSOC | Delete behaviour left at the default where the child cannot stand alone |

### Types

| Rule | Sev | Tier | Paradigms | Source | Checks for |
|---|---|---|---|---|---|
| `TYP-001` | **BLK** | A | all | SQLSG | Date or time value stored in a character type |
| `TYP-002` | MAJ | A | all | SQLSG | Numeric value stored in a character type |
| `TYP-003` | **BLK** | A | relational | KAR-SAP1 | Monetary amount in an approximate numeric type |
| `TYP-004` | MAJ | A | relational | SQLSG | Monetary or measured column with no precision and scale |
| `TYP-005` | min | A | relational | SQLSG | Boolean modelled as a single character flag |
| `TYP-006` | **BLK** | A | relational | SQLSG | Unbounded text used as a key, unique column or foreign key |
| `TYP-007` | note | A | all | FRICT-TS | Blanket maximum-width character columns |
| `TYP-008` | MAJ | A | all | EID | Formatted identifier stored as a number |
| `TYP-009` | MAJ | A | relational | FOW-TIME | Event or audit timestamp with no time zone |
| `MDX-008` | **BLK** | A | mendix | MDX-ATTR | Monetary amount not stored as Decimal |

### Nullability

| Rule | Sev | Tier | Paradigms | Source | Checks for |
|---|---|---|---|---|---|
| `NUL-001` | MAJ | A | all | OMOP-CONV | Sentinel value standing in for unknown |
| `NUL-002` | MAJ | A | relational | SIMSION | Almost every column nullable |
| `NUL-003` | MAJ | A | all | OMOP-CONV | NOT NULL column defaulted to a value that means unknown |
| `MDX-017` | MAJ | A | mendix | MDX-VALID | Mandatory attribute with no Required validation rule |

### ReferenceData

| Rule | Sev | Tier | Paradigms | Source | Checks for |
|---|---|---|---|---|---|
| `REF-001` | min | A | relational | HOB-SC | Inconsistent lookup-table shape |
| `REF-002` | MAJ | A | all | KAR-SAP1 | All reference data in one generic lookup table |
| `REF-003` | MAJ | A | relational | OMOP-CONV | Code and display label conflated |
| `REF-004` | MAJ | A | relational | OMOP-CONV | Lookup table whose only identity is its label |
| `REF-005` | min | A | relational | KAR-SAP1 | Business-volatile value list hard-coded in DDL |

### Temporality *(ours, beyond Hoberman)*

| Rule | Sev | Tier | Paradigms | Source | Checks for |
|---|---|---|---|---|---|
| `TEM-001` | min | A | relational | PAGILA | No audit columns on a mutable table |
| `TEM-002` | min | A | relational | DAMA | Audit actor stored as free text rather than a reference |
| `TEM-003` | MAJ | A | relational | SOFTDEL | Soft delete applied inconsistently across the model |
| `TEM-004` | **BLK** | A | relational | SOFTDEL | Soft delete with a unique constraint that ignores it |
| `TEM-005` | MAJ | A | relational | SQL2011 | Effective-dated rows with no overlap constraint |
| `TEM-006` | min | A | relational | FOW-TIME | Open-ended period represented inconsistently |
| `TEM-007` | MAJ | A | dim | KIM-DMT | Type 2 dimension without a current-row indicator |
| `TEM-008` | MAJ | B | relational | FOW-TIME | Retroactive correction needed but only one time axis modelled |
| `MDX-010` | min | A | mendix | MDX-SYSMEM | System members not enabled on a mutable persistable entity |
| `MDX-011` | min | A | mendix | MDX-SYSMEM | Audit user modelled as a String instead of the owner / changedBy association |

### Semantics

| Rule | Sev | Tier | Paradigms | Source | Checks for |
|---|---|---|---|---|---|
| `NAM-001` | min | A | relational | ISO-11179-5 | Attribute name has no object-class or representation term |
| `NAM-002` | min | A | relational | SQLSG | Mixed identifier casing conventions |
| `NAM-003` | min | A | relational | SQLSG | Mixed singular and plural table naming |
| `NAM-004` | min | A | relational | SQLSG | Type prefix or Hungarian notation on an object name |
| `NAM-005` | min | A | relational | SQLSG | Undocumented abbreviation in an identifier |
| `NAM-006` | min | A | relational | SQLSG | Table shares a name with one of its own columns |
| `NAM-007` | MAJ | A | relational | SQLSG | Reserved word used as an identifier |
| `NAM-008` | MAJ | A | all | HOB-SC | One concept named several ways (synonym) |
| `NAM-009` | MAJ | A | all | HOB-SC | One name meaning several things (homonym) |
| `NAM-010` | MAJ | A | all | KIM-DMT | Monetary or measured value with no unit or currency |
| `NAM-011` | note | A | relational | SQLSG | Identifier exceeds 30 bytes or uses characters outside [A-Za-z0-9_] |
| `NAM-012` | note | A | relational | DBT-STG | Date and timestamp columns not distinguished by name |
| `MDX-012` | MAJ | A | mendix | MDX-NAMING | Entity or attribute name breaks Mendix naming conventions |

### Relationships

| Rule | Sev | Tier | Paradigms | Source | Checks for |
|---|---|---|---|---|---|
| `REL-001` | **BLK** | A | all | KAR-SAP1 | Multi-valued attribute stored as a delimited list |
| `REL-002` | MAJ | B | relational | SIMSION | Many-to-many resolved without its own attributes |
| `REL-003` | note | B | dim | KIM-DMT | Centipede fact table |
| `REL-004` | MAJ | B | relational | KIM-DMT | Fan-out risk: sibling one-to-many children aggregated together |
| `MDX-003` | MAJ | A | mendix | MDX-PERF | Multiple associations between the same pair of entities |

### Performance *(ours, beyond Hoberman)*

| Rule | Sev | Tier | Paradigms | Source | Checks for |
|---|---|---|---|---|---|
| `PER-001` | MAJ | A | oltp+vault | MSFT-WWI | Foreign key column with no index |
| `PER-002` | min | A | relational | KAR-SAP1 | Index Shotgun |
| `PER-003` | MAJ | A | relational | SIMSION | Uniqueness asserted only in documentation |
| `MDX-005` | MAJ | A | mendix | MDX-MXP | Attribute used for search or sort has no index (MXP003 / MXP007) |
| `MDX-006` | min | A | mendix | MDX-PERF | Duplicate index leading with the same attribute |
| `MDX-007` | MAJ | A | mendix | MDX-MXP | Calculated attribute where a stored attribute is needed (MXP001 / MXP002) |
| `MDX-014` | min | A | mendix | MDX-PERF | Reference set used where a reference would do |

### Governance *(ours, beyond Hoberman)*

| Rule | Sev | Tier | Paradigms | Source | Checks for |
|---|---|---|---|---|---|
| `GOV-001` | MAJ | A | all | DAMA | Personal data not identified as such |
| `GOV-002` | **BLK** | A | dim+doc+graph+oltp+semantic+vault | KAR-SAP1 | Credential stored in a reversible form |
| `GOV-003` | note | B | all | DAMA | No retention or ownership metadata |
| `MDX-009` | **BLK** | A | mendix | MDX-ATTR | Credential attribute not stored as Hashed string |
| `MDX-015` | MAJ | B | mendix | MDX-MXP | Entity access rules absent, duplicated, or negated (MXP010 / MXP013) |
| `MDX-019` | MAJ | A | mendix | MDX-ACCESS | Specialization entity declares no access rules of its own |

### Documentation

| Rule | Sev | Tier | Paradigms | Source | Checks for |
|---|---|---|---|---|---|
| `DOC-001` | MAJ | A | all | MSFT-WWI | Entity has no definition |
| `DOC-002` | min | A | all | MSFT-WWI | Low column-definition coverage |
| `DOC-003` | min | A | all | HOB-SC | Definition merely restates the name |
| `DOC-004` | note | A | all | OMOP-FIELD | Derived column with no population rule recorded |

### Extensibility *(ours, beyond Hoberman)*

| Rule | Sev | Tier | Paradigms | Source | Checks for |
|---|---|---|---|---|---|
| `EVO-001` | MAJ | A | all | KAR-SAP1 | Spare or numbered generic columns |
| `EVO-002` | MAJ | B | relational | HOB-SC | Subtypes modelled as nullable columns on a supertype |
| `EVO-003` | min | A | all | PROTO-UPD | Enumeration with no default or unknown member |
| `MDX-004` | MAJ | A | mendix | MDX-MXP | Inheritance deeper than two levels (MXP009) |
| `MDX-018` | **BLK** | B | mendix | MDX-TYPECHANGE | Generalization used to model a role or lifecycle stage that changes over time |

### Localisation *(ours, beyond Hoberman)*

| Rule | Sev | Tier | Paradigms | Source | Checks for |
|---|---|---|---|---|---|
| `LOC-001` | MAJ | A | all | I18N-DB | More than two languages in parallel columns |
| `LOC-002` | MAJ | A | all | I18N-DB | Asymmetric bilingual coverage |
| `LOC-003` | MAJ | A | all | HIJRI | Hijri date with no canonical Gregorian counterpart |
| `LOC-004` | MAJ | A | all | HIJRI | Hijri and Gregorian both independently writable |
| `LOC-005` | note | B | all | I18N-DB | No collation or normalisation policy for non-Latin text |

### Consistency

| Rule | Sev | Tier | Paradigms | Source | Checks for |
|---|---|---|---|---|---|
| `CON-001` | MAJ | A | relational | HOB-SC | Same column name carries different types across tables |
| `CON-002` | min | A | relational | HOB-SC | Audit column naming inconsistent across the model |

### Scheme

| Rule | Sev | Tier | Paradigms | Source | Checks for |
|---|---|---|---|---|---|
| `SCH-001` | min | B | all | HOB-SC | Model level not declared, or mixed levels in one model |


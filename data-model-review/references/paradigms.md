# Paradigm routing

Read this before applying any rule. Getting the paradigm wrong is the most expensive
mistake available to this skill, and it is expensive precisely because the output still
reads like a competent review — a confident finding, a named source, a plausible
remediation, all of it wrong because the canon does not apply.

The same statement can be a recommendation in one paradigm and a defect in another:

| Statement | Where it is best practice | Where it is a defect |
|---|---|---|
| Denormalised flattened dimension, hierarchy collapsed into one table | Dimensional — Kimball names it as a technique | OLTP — a 3NF violation with update anomalies |
| Surrogate key on every table | Dimensional — required for Type 2 history | OLTP — Karwin's *ID Required*, if it displaces the business key |
| No foreign key constraints at all | Data Vault raw layer, where integrity is asserted by the load pattern | OLTP — Karwin's *Keyless Entry* |
| snake_case identifiers | Relational — SQL Style Guide | Mendix — PascalCase is mandated, and underscores in entity names break the Java build |
| Aggregate holds a nested copy of related data | Document store — that is the aggregate boundary | OLTP — uncontrolled redundancy |
| Same business key in several tables with no FK between them | Data Vault hubs | OLTP — an undeclared relationship |

So: **classify first, then apply.** Every rule in `scripts/rules.py` declares the
paradigms it is valid in, and `score_model.py` reports the excluded ones as
`NOT_APPLICABLE` rather than dropping them. That reporting matters — "no missing-foreign
-key findings" must not be readable as a pass when the real reason is that the paradigm
has no foreign keys.

---

## Step 1 — classify

`score_model.classify_paradigm()` guesses from schema signals and returns its evidence.
A value in `meta.paradigm` always wins, because the reviewer knows things the schema does
not show. **State the classification and its basis in the report**, so a reader can
overrule you.

Signals, in rough order of reliability:

| Signal | Points to |
|---|---|
| `hub_` / `lnk_` / `sat_` prefixes, load-date and record-source columns | `vault` |
| `fact_` / `dim_` prefixes; a wide table of FK keys plus numeric measures | `dim` |
| First-class associations, no FK columns, entities with `persistable` / validation rules / system members | `mendix` |
| Many small tables, composite PKs on associative tables, declared FKs | `oltp` |
| Very wide tables, nested/repeated fields, few or no joins by design | `doc` |
| Nodes and edges as the primary structures, edge properties | `graph` |
| Metric and dimension *definitions* over a physical model, no storage | `semantic` |

When the classifier says `medium` or `low` confidence, or when the model is genuinely
mixed, say so and pick the paradigm that governs the part you are reviewing. A staging
layer feeding a star schema is two paradigms; review them separately rather than
averaging them into one incoherent scorecard.

### Mixed models

Real estates are mixed. Handle it by scoping, not by compromise:

- **Layered warehouse** (staging → intermediate → marts): staging is source-conformed
  and judged against `SRC-DBT-STG` — rename, cast, compute, categorise, and nothing
  else. Marts are judged as `dim`. Run two passes.
- **OLTP with a reporting star alongside it**: two passes, two scorecards. Note whether
  the star's conformed dimensions actually conform to the OLTP reference data.
- **Mendix app over a legacy database**: the Mendix domain model is `mendix`; the legacy
  schema is `oltp`. They are separate reviews with separate canons.

---

## Step 2 — know what each paradigm asks of you

### `oltp` — normalised operational schema

Target 3NF/BCNF, with denormalisation as a *justified* exception rather than a default.
What matters most: identity (does every entity have a declared business key), integrity
(is every relationship a declared constraint), and enforcement (is every business rule
the schema *could* hold actually held there rather than in application code).

Canon: `SRC-DATE`, `SRC-CODD-70`, `SRC-KAR-SAP1`, `SRC-SIMSION`, `SRC-MSFT-WWI`,
`SRC-PAGILA`, `SRC-SQLSG`.

Do **not** apply Kimball's dimensional techniques here. A flattened hierarchy is not a
virtue in an OLTP schema.

### `dim` — dimensional warehouse or mart

Grain first. Every measure must be true at the declared grain and every dimension key
must be valid at it; almost every serious dimensional defect reduces to a grain that was
never stated. Then: surrogate keys on dimensions, the SCD type actually implemented
matching the one intended, conformed dimensions across fact tables.

Canon: `SRC-KIM-DMT`, `SRC-KIM-DWT`.

Rules deliberately **not** applied: `PER-001` (unindexed FK). A star schema's dimension
keys are the join path by design, and indexing policy there is a platform question —
columnstore, sort keys, clustering — not a modelling defect. Normalisation rules are
likewise absent: a snowflake is a choice, not an error, and a flattened dimension is the
recommendation.

### `vault` — Data Vault 2.0

Hubs carry business keys only. Links carry relationships only. Satellites carry
descriptive attributes and history, with load-date and record-source mandatory. Judge
whether the separation actually holds: a satellite carrying a business key, or a hub
carrying descriptive attributes, defeats the point of the pattern.

Canon: `SRC-DV2`.

Do **not** report the absence of enforced referential integrity in the raw vault as
`INT-001`. Integrity is asserted by hash keys and the load pattern. Do report it if the
business vault or the information marts rely on joins that nothing guarantees.

### `mendix` — low-code domain model

A distinct paradigm, not a dialect. See `references/mendix.md` — several relational
rules invert, and 55 of the 100 rules do not apply at all. The substitutions are the
whole story: identity is a `Unique` validation rule, requiredness is a `Required`
validation rule, orphan risk is delete behaviour, audit is system members, and
PascalCase is correct rather than a violation.

Canon: `SRC-MDX-*`, especially the numbered MxAssist rules in `SRC-MDX-MXP`.

### `doc` — document store / aggregate model

Judge the aggregate boundary, not the normal form. Redundancy inside an aggregate is the
design; redundancy *across* aggregates with no owner is the defect. Ask what a single
write must be atomic over, and whether the document boundary matches it.

Rules applied here are the paradigm-neutral set (`ALL_MODELS`): shape defects,
delimited lists, formatted identifiers, documentation, governance, localisation. Do not
apply normalisation, FK or index rules.

### `graph` — property graph or RDF

Judge whether edges carry the semantics they need — direction, type, and properties —
and whether node identity is stable. Supernodes and untyped edges are the common
failures.

Coverage here is thin: the registry carries the paradigm-neutral rules and little more.
Say so in the review rather than implying full coverage. `selftest.py` warns when a
paradigm has fewer than five applicable rules, and that warning is honest information to
pass on.

### `semantic` — metrics / semantic layer

There is no storage to judge. What matters is whether a metric has exactly one
definition, whether dimensions are conformed across metrics, and whether the layer's
grain assumptions match the physical model beneath it. Two definitions of "active
customer" is the canonical defect.

Coverage is thin here too, for the same reason. Be explicit about it.

---

## Step 3 — report the routing

Whatever the paradigm, the report must state:

1. **Which paradigm** was applied and the evidence for it.
2. **Which canon was deliberately not applied**, by name. This is what lets a reader who
   disagrees with the classification know exactly what would change.
3. **How many rules were excluded** as not applicable, with the list available.
4. **Where coverage is thin** for this paradigm, if it is.

A review that does not say which canon it applied cannot be checked, and a review that
cannot be checked is an opinion with a percentage attached to it.

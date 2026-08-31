---
name: data-model-review
description: Review and grade a data model against cited industry best practice, producing a Hoberman-style scorecard plus severity-ranked findings with sources, failure scenarios and remediations. Use this whenever the user wants a data model, database schema, ERD, domain model, data dictionary, DDL, star schema, dbt project or Mendix domain model judged, graded, critiqued, audited, sanity-checked, reviewed for best practices, or compared against standards — including questions like "is this schema any good", "what's wrong with this design", "review my ERD", "score this data model", "would you have designed it this way", or "check this against Kimball/3NF/Data Vault/Mendix conventions". Also use it when asked to design-review a schema BEFORE data is loaded, to justify a modelling decision with citations, or to produce a model-quality report for a client or steering group. Not for building a source-to-target migration mapping (use sttm-mapping) or extracting a model out of an ERD PDF (use erd-extraction) — though this skill consumes the output of both.
---

# Data model review

Grade a data model against named, citable authority and report defects a modeller can act
on. The output is a scorecard plus findings, where every finding says what is wrong, what
in *this* model shows it, what breaks if it is left, how to fix it, and which source says
so.

The point of the discipline below is that a data-model review is unusually easy to do
badly in a way that looks good. Confident prose, plausible severities and a percentage
read as authority whether or not the canon applied was the right one, and whether or not
the findings survive contact with the person who built the model. Everything here exists
to make the review checkable.

## Two things that will make the review wrong

**1. Applying the wrong canon.** The same statement is best practice in one paradigm and a
defect in another: a denormalised flattened dimension is a Kimball technique and a 3NF
violation; snake_case is right in SQL and breaks the Java build in Mendix; no foreign keys
is correct in a Data Vault raw layer and Karwin's *Keyless Entry* in an OLTP schema.
**Classify the paradigm first, state the classification and its basis, and say which canon
you deliberately did not apply.** Read `references/paradigms.md` before anything else.

**2. Reporting your own missing inputs as the model's defects.** Three of Hoberman's ten
categories cannot be judged from a schema: Correctness needs requirements, Readability
needs a diagram, Data needs a profile. Scoring them zero produces a low grade that blames
the model for a gap in the engagement. They come back `NOT_ASSESSABLE` and leave the
denominator. The same holds for rules a paradigm excludes — they are counted and listed,
never silently dropped, so silence is never mistaken for a pass.

## Workflow

### 1. Establish what you have, and say what it limits

Inventory the inputs before reading the model: DDL, an information-schema dump, an Excel
data dictionary, dbt YAML, a Mendix export, an ERD PDF. Then say what is **absent** —
FK declarations, row counts, access paths, requirements, a diagram, classifications.

This is not a disclaimer. A DDL input has no mechanism to express PII classification, so
`GOV-001` will fire on every personal-data column; that is correct on DDL and it is a
different statement from "this model ignores data protection". Establish which you are
making.

If the model is an ERD PDF, extract it first with the `erd-extraction` skill, then feed
the result in as JSON. If the ask is really about migrating between two models rather than
judging one, that is `sttm-mapping`, not this skill.

### 2. Classify the paradigm

`oltp` · `dim` · `vault` · `mendix` · `doc` · `graph` · `semantic`. The classifier in
`score_model.py` guesses and returns its evidence; a value in `meta.paradigm` overrides it,
because you know things the schema does not show. Mixed estates get separate passes, not
an averaged scorecard. `references/paradigms.md` has the signals and what each paradigm
asks of you.

For Mendix, read `references/mendix.md`. It is a different paradigm, not a dialect: 55 of
the 100 rules do not apply, identity is a `Unique` validation rule rather than a primary
key, requiredness is a `Required` rule rather than `NOT NULL`, orphan risk is delete
behaviour rather than `ON DELETE`, and PascalCase is correct rather than a violation.

### 3. Run the mechanical pass

```bash
python scripts/parse_model.py schema.sql -o model.json --dialect oracle
python scripts/score_model.py model.json -o findings.json --paradigm oltp
python scripts/emit_report.py findings.json -o review.xlsx --md review.md
```

Use the Anaconda interpreter if `sqlglot` is missing from the default one — the DDL parser
degrades to regular expressions without it and says so in `parse_warnings`.

Read the warnings the parser emits. "This input carries no index definitions, so
`PER-001` cannot run" means those rules are **unexamined**, not satisfied, and the
distinction belongs in the report.

### 4. Adjudicate the judged rules

Tier-A rules are mechanical and carry the score. Tier-B rules need a judgement about
meaning — is this entity over-generalised, is the grain right, is this definition
adequate, does this model need a second time axis — and arrive in
`candidates_for_adjudication` with `verdict: INSUFFICIENT_EVIDENCE`. Resolve each one with
evidence, or record that you could not.

Then read the model yourself for what no check can see: whether the entities correspond to
things the business recognises, whether the grain is stated and true, whether definitions
say anything. `references/rubric.md` lists which rules are reviewer-raised only.

### 5. Try to refute your own top findings

Before writing anything up, take each BLOCKER and MAJOR and argue against it. Is there a
reading of the model under which it is correct? Does a constraint elsewhere already handle
it? Is it a defensible trade-off rather than an error?

Drop what you cannot defend. Downgrade what turns out to be a trade-off to
`DEFENSIBLE_TRADEOFF_I_D_DIFFER` and name the cost being accepted rather than pretending
it is a violation. A review that cannot tell a violation from a trade-off gets dismissed
wholesale by the person who built the model, and then the real findings go with it.

The mechanical checks have false-positive modes worth checking specifically: `GOV-001` on
any DDL input, `MDX-001`/`MDX-017` when an export omitted validation rules, `NAM-005` on
domain vocabulary with no glossary supplied, `INT-001` where an FK genuinely cannot be
declared across databases.

### 6. Report

```
Executive summary       one paragraph a sponsor can read: what state the model is in,
                        what the one or two things that matter are, what it will cost
Paradigm and canon      what was applied, on what evidence, and what was not applied
Review input gaps       what you could not see, and which rules that left unexamined
Scorecard               Hoberman's ten categories, NOT_ASSESSABLE shown as such
Dimensions              the detailed axis, with our five extensions labelled as ours
Findings                BLOCKER first, each with evidence, failure scenario, fix, source
Awaiting adjudication   tier-B candidates and what would settle them
Remediation plan        prioritised, with effort bands
```

An empty dimension is a valid result — say so. Do not manufacture findings to fill the
rubric; a padded review costs you the reader's attention for the findings that matter.
Equally, do not soften: if the model loses data as designed, the executive summary is
where that gets said, in the first sentence.

**Match the length to what you found and what was asked.** This is the failure mode this
skill actually exhibits, measured: given a sound schema and a user asking for "a short
honest answer rather than a long list", a review written with this skill ran to 421 lines
against 77 for one written without it — same three real defects in both. The structure
above is a full-dress template for a model with serious problems and a sponsor who needs
convincing. It is not a required shape.

- **Few findings, or a user asking for brevity** → a short answer. Headline, the two or
  three things that are genuinely wrong, one line on what you checked and found clean.
  The scorecard and the dimension table belong in an attached workbook, not the prose.
- **Many findings, or a decision to be argued** → the full structure, because a reader
  who has to push back needs the scaffolding.

Having run 103 rules is not an achievement to report. The reader wants to know what is
wrong, how bad it is, and what to do — a long review of a good schema reads as padding,
and it undermines the finding that actually mattered.

## Scoring, and what the number does not claim

The score is `earned / assessable weight`, with `NOT_ASSESSABLE` categories excluded.
Weights live in `assets/weights.json` and are **ours, not Hoberman's** — his ten category
names and questions are published, the per-category allocation is not, so never attribute
those numbers to him.

Severity penalties are damped on repeat (`0.55^(n−1)`), because one systemic issue across
200 tables would otherwise zero every category and the scorecard would stop
discriminating.

Tier-A scoring is byte-for-byte reproducible on the same input; `selftest.py` proves it.
Tier-B judgements are not, which is exactly why they carry no score until resolved. Report
the number as what it is: a weighted count of mechanically-detected defects, useful for
comparison and tracking, not a measurement.

## Files

| Path | Read it when |
|---|---|
| `references/paradigms.md` | **Always, first.** Classification and the rule-applicability matrix |
| `references/mendix.md` | The model is Mendix. Substitution map, MXP rules, extraction traps |
| `references/rubric.md` | You need the scoring mechanics, tiers, verdicts, or the full rule list |
| `references/antipatterns.md` | Writing up a finding — named smells, detection, remedy |
| `references/patterns.md` | Writing a remediation — the named fix to recommend |
| `references/sources.md` | A finding is challenged, or you are adding a rule |
| `scripts/rules.py` | The rule registry. Authoritative; `rubric.md` mirrors it |
| `scripts/checks.py` | Tier-A detection. Pure functions of the model, no I/O |
| `assets/model.schema.json` | Writing an input adapter or hand-building a model |
| `fixtures/` | Worked examples, including a sound model for calibration |

## Extending it

Add the source to `references/sources.md` **first**, with a verification status. Then the
rule to `scripts/rules.py`, the check to `scripts/checks.py`, and a planted defect to a
fixture's `Expected to fire` list. Then:

```bash
python scripts/selftest.py
```

Six gates: every rule cites a source that exists and is not `UNVERIFIED`; every tier-A
rule has a check; vocabularies and weights agree; every planted defect actually fires;
scoring is deterministic; and the sound fixture stays clean while the flawed ones do not.

That last gate is the one that keeps the skill honest. A rule that over-fires makes a good
model look bad and trains readers to skim; a check that rots into a no-op makes a bad model
look good and raises no error at all. `fixtures/sound_oltp.sql` exists to catch the first
and the `Expected to fire` lists to catch the second.

Never reuse a retired rule id — reports and decision logs cite them, for the same reason
protobuf never reuses a field number.

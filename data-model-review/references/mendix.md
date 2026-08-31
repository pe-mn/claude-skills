# Reviewing a Mendix domain model

Mendix is a **different paradigm, not a SQL dialect**. Reviewing it with relational rules
produces two failure modes at once: rules that cannot fire (so the model looks clean) and
rules that fire backwards (so correct work is reported as defective). 55 of the 100 rules
in the registry are `NOT_APPLICABLE` here, and the substitutes carry the review.

Sources, all verified: `SRC-MDX-DM`, `SRC-MDX-ASSOC`, `SRC-MDX-ATTR`, `SRC-MDX-SYSMEM`,
`SRC-MDX-VALID`, `SRC-MDX-INDEX`, `SRC-MDX-NAMING`, `SRC-MDX-MXP`, `SRC-MDX-PERF`,
`SRC-MDX-GENASSOC`, `SRC-MDX-DEVBP`.

---

## The five things that change everything

**1. There are no foreign key columns.** Associations are first-class model objects with
their own name, multiplicity and ownership. So `INT-001` ("FK-shaped column with no
constraint") is not merely inapplicable — it is unaskable. Every association is declared
by construction. The question becomes what the association's *delete behaviour* is, which
is `MDX-002`.

**2. There is no user-visible primary key.** Every persistable entity gets an implicit
auto-generated ID. `KEY-002` ("no primary key") can never fire. But identity still has to
be declared, and the only database-enforced mechanism is a **`Unique` validation rule** —
which is `MDX-001`, and which is the single most important finding class in a Mendix
review. A model with no `Unique` rules anywhere admits duplicate business entities
everywhere, and nothing in the domain model diagram shows it.

**3. There is no `NOT NULL`.** Requiredness is a `Required` validation rule. `MDX-017`
substitutes for the whole relational nullability group. The critical caveat from
`SRC-MDX-VALID`: **validation rules run on commit**, so Java actions and direct database
writes bypass them entirely. If such a path exists — an integration, a migration loader,
a scheduled Java action — then a validation rule is not a constraint, and the review
should say so rather than treating it as one.

**4. PascalCase is correct.** `NAM-002`'s preference for snake_case inverts: `SRC-MDX-NAMING`
mandates PascalCase, singular, no underscores, no abbreviations. And the reason is not
aesthetic — a module named `Customer` containing an entity named `customer` is a **Java
compilation error that stops the app running**. The one sanctioned underscore is a
*leading* one, marking an attribute as technical rather than business-related; the stated
test is whether you would capture it in a paper process.

**5. Generalisation is stored as class-table inheritance** (`SRC-MDX-STORAGE`). This is
the fact the other inheritance rules hang off, so get it straight first.

An instance is stored **partly in the generalisation's table and partly in the
specialisation's**, joined internally on a shared id. Nothing is duplicated. So:

- An inherited attribute is **one physical column, on the generalisation.** A model that
  redeclares it on the child describes a column that does not exist — that is `MDX-020`,
  and it usually means the modeller believes each table is independently complete.
- The shared id is simultaneously the child's **primary key and its foreign key** to the
  generalisation. There is no separate parent-id column.
- Inheritance costs **joins, not storage**: an N-level chain is an N-table join on every
  read, which is why MXP009 caps it at two.
- A write locks the **generalisation**, so contention concentrates at the top of the
  hierarchy.

In Studio Pro the child *behaves* as though it owns every inherited attribute — you bind
them on pages, constrain XPath on them, set them in microflows. That modelling-level view
is what makes the duplication look harmless. It is not the physical shape.

**5a. An object's entity type is fixed for its lifetime** (`SRC-MDX-TYPECHANGE`). There is
no way to convert a specialization into a sibling, or back into its generalization — you
create a new object of the target type, copy every attribute, and re-point every
association by hand. So anything that *changes over time* must not be a specialization:
a role, a status, an eligibility stage. `Applicant → Beneficiary` as an inheritance
hierarchy encodes a transition the business performs routinely as one the model forbids.
That is `MDX-018`, and it is the most consequential Mendix finding available, because it
cannot be undone once production data exists.

**5b. Access rules are additive but NOT inherited** (`SRC-MDX-ACCESS`), which is
counterintuitive in both directions and produces confident false findings either way:

- Additive: multiple rules for one module role **combine**. A specialization can never
  narrow what its own rules grant.
- **Not inherited:** "Access rules are not inherited from an entity's generalization,
  because the security for every entity is specified explicitly." A specialization with no
  rules of its own is *unprotected*, not protected by its parent — the opposite of what
  every other object-oriented system would lead you to expect. That is `MDX-019`.
- One exception: `System.User`'s built-in platform-enforced rules **do** apply to its
  specializations and cannot be overridden by specialization-level XPath.

If you find yourself writing "access rules inherited from the generalization", stop — that
is the failure mode this note exists to prevent, and it was written after a reviewer
asserted exactly that with confidence.

**5c. Generalisation is first-class.** Mendix has real inheritance, so single-table
inheritance-by-nullable-columns is not the local anti-pattern. The local anti-pattern is
inheritance that is too deep (`MDX-004`, MxAssist **MXP009**, limit two levels), and the
reason is concrete: **inheritance locks the generalisation entity on write**, so a commit
low in the hierarchy can block retrieves across all of it. `SRC-MDX-GENASSOC` also gives
the decisive practical warning — once inheritance is applied it is *difficult to remove
while keeping the data*, and removing a generalisation loses its relationships
permanently. That makes it a decision to settle before production data exists, which is
worth saying in any review of a pre-launch model.

---

## Substitution map

| Relational rule | Status in Mendix | Substitute |
|---|---|---|
| `KEY-001` bare `id` PK | N/A — implicit ID | — |
| `KEY-002` no PK | N/A — implicit ID | `MDX-001` no `Unique` rule |
| `KEY-003` surrogate without business-key unique | N/A | `MDX-001` |
| `INT-001` undeclared FK | N/A — associations are declared | — |
| `INT-003` no `ON DELETE` | N/A | `MDX-002` delete behaviour left at default |
| `NUL-001/2/3` nullability | N/A — no `NOT NULL` | `MDX-017` no `Required` rule |
| `TEM-001` no audit columns | N/A | `MDX-010` system members not enabled |
| `TEM-002` audit actor as text | N/A | `MDX-011` String instead of `owner` / `changedBy` |
| `PER-001` unindexed FK | N/A — associations auto-indexed | `MDX-005` unindexed sort/XPath attribute |
| `PER-002` index shotgun | N/A | `MDX-006` duplicate leading attribute |
| `TYP-003` money in float | N/A | `MDX-008` money not `Decimal` |
| `GOV-002` plaintext credential | N/A | `MDX-009` not `Hashed string` |
| `NAM-002` casing | **Inverted** | `MDX-012` PascalCase, singular, no underscores |
| `EVO-002` single-table inheritance | N/A — real generalisation | `MDX-004` depth > 2 (MXP009) |

Rules that **do** apply unchanged, because the defect is in the shape of the information
rather than the platform: `STR-001` (EAV), `STR-002` (over-generalisation), `STR-003`
(repeating groups), `STR-004` (per-period entities), `STR-005` (very wide entity),
`REF-002` (one generic lookup), `REL-001` (delimited list in a String), `TYP-001` (date
in a String), `TYP-002` (number in a String), `TYP-007` (blanket widths), `TYP-008`
(formatted identifier as a number), `NAM-008/009/010` (synonyms, homonyms, units),
`EVO-001` (placeholder attributes), `EVO-003` (enumeration with no unknown member),
`DOC-*`, `GOV-001`, `GOV-003`, `LOC-*`.

---

## What Mendix gives you for free, and what it does not

Enabled automatically (`SRC-MDX-INDEX`): an index on the entity ID, on stored `owner` and
`changedBy`, and on association storage.

**Not** indexed automatically: `createdDate` and `changedDate`. So an entity that filters
or sorts on creation date needs an explicit index even though the system member exists —
a gap worth checking whenever `MDX-010` comes back satisfied.

Opt-in and defaulting to **false** (`SRC-MDX-SYSMEM`): `Store 'createdDate'`,
`Store 'changedDate'`, `Store 'owner'`, `Store 'changedBy'`. `owner` and `changedBy` are
**associations to the system `User` entity**, not strings — which is why a String
`CreatedByUser` attribute is a real finding and not a stylistic one.

Delete behaviour options, exact names (`SRC-MDX-ASSOC`):
- **"Keep associated object(s)"** — the default, and therefore the one arrived at by not
  choosing
- **"Delete associated object(s) as well"**
- **"Delete only if not associated"** — requires an error message

Attribute types (`SRC-MDX-ATTR`): AutoNumber, Binary, Boolean, Date and time, **Decimal**
(the documented type for money; 20 integral / 8 fractional digits), Enumeration,
**Hashed string** (for passwords; not filterable), Integer, Long, String (**default max
length 200**). There is no Currency type. Binary and calculated attributes are not
sortable.

Validation rule types (`SRC-MDX-VALID`): Required, **Unique** (database-enforced, and
unavailable on an attribute inherited into a specialisation), Equals, Range, Regular
expression, Maximum length.

---

## The MxAssist rules, which are the most citable Mendix source

`SRC-MDX-MXP` is a shipped linter, so these are numbered and quotable rather than
folklore:

| Rule | Detects | Fix |
|---|---|---|
| **MXP001** | Calculated attribute in a data container | Convert to stored; set in a microflow before commit |
| **MXP002** | Unused calculated attribute — still runs on every retrieve | Delete it |
| **MXP003** | Sort-bar attribute with no index | Index it |
| **MXP007** | XPath attribute with no index (read-heavy entities over ~10k rows) | Index it; put indexed attributes first in the XPath |
| **MXP009** | More than two inheritance levels | Flatten via enumeration, 1-1 association, or non-persistable layer |
| **MXP010** | Duplicated entity access rules | Consolidate; validate state in microflows |
| **MXP013** | Negated XPath access rules (`not()`, `= false()`) | Rewrite as positive predicates |
| **MXP015** | Suboptimal XPath predicate order | Cheapest and most selective first |

Plus, from `SRC-MDX-PERF`: index entities over ~100 rows searched by anything other than
a reference; cover search and sort in one index; **at most three index attributes** (five
outside limit); lead with the most selective. Avoid duplicate indexes leading with the
same attribute. **Minimize reference sets** — Mendix retrieves IDs per row on list
retrieves. **Avoid multiple associations between the same two entities**, especially with
different access levels, because the security rules on one do not apply to the other.
Do not put temporary associations on persistable entities. A `Contains` search comparison
gets no benefit from an index at all.

---

## Getting a Mendix model into the parser

The `.mpr` is a binary project file, and Mendix has **no stable public text export** of a
domain model. Two routes:

1. **`--format mendix-html`** against a documentation export. Best effort only: the
   markup is version-dependent and not a contract, so the adapter reports loudly what it
   found and leaves anything it could not establish `null`. Spot-check the entity and
   association counts against Studio Pro before trusting them.
2. **`--format json`**, building the model by hand or from a **Model Reflection** extract.
   This is the better route whenever index definitions, access rules or access-path
   evidence matter, because an HTML export carries none of them. A hand-built model that
   is honest beats a scraped one that is quietly incomplete.

`fixtures/flawed_mendix.json` is a worked example of the shape.

**The trap to avoid.** If validation rules are absent from the extract, `MDX-001` and
`MDX-017` will fire on every entity — and you cannot tell from the output whether the
model genuinely has no `Unique` rules (a serious finding) or the export simply omitted
them (an unexamined rule). Establish which before reporting, and if you cannot, report it
as an input gap rather than as a defect. The Mendix HTML adapter emits exactly this
warning when it finds no validation rules; do not let it pass through into the findings
list unexamined.

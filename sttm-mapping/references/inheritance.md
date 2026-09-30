# Mapping a model that uses inheritance

Applies wherever the TARGET model has generalisation/specialisation — a Mendix domain
model, a supertype/subtype relational schema, a Party/Role pattern. It is a mapping
concern rather than a design one, so it lives here rather than in `data-model-review`.

The whole section follows from one physical fact. Get it wrong and every rule below
inverts.

## The fact

Platforms that support inheritance almost always use **class-table inheritance**: the
child's table holds ONLY its own attributes plus a shared id that is simultaneously its
primary key and its foreign key to the parent. One logical object = one row in *each*
table in its chain, all carrying the same id. Nothing is duplicated.

```
party        id=1001  PartyReference='P-9'  FullName='...'
person       id=1001  DateOfBirth=...       EmiratesID='784-...'
beneficiary  id=1001  EntitlementCode='E-4' MonthlyAmount=...
```

Mendix works exactly this way, and its modeller hides it: a child *behaves* as though it
owns every inherited attribute — you bind them on pages and set them in microflows — which
is precisely why a mapping built from the modeller's view duplicates them.

## Four consequences for the mapping

**1. Map an inherited attribute ONCE, on the entity that declares it.** A row for
`Beneficiary.FullName` describes a column that is not on that table. Two rows claiming one
physical column means the load writes it twice, and whichever runs last wins
non-deterministically. Nothing errors and the value is plausible either way.

Where a subtype genuinely needs a **different source** for the same column, that is not a
second row — it is one column with a **discriminated expression** on the parent:

```sql
Request.ProcessedDate =
  CASE <subtype>
    WHEN 'Payment'                   THEN LEDGER_TXN.TRANSACTION_DATE
    WHEN 'RevenueTransfer'           THEN REQUEST.UPDATED_ON
    ELSE                                  REQUEST.REQUEST_DATE
  END
```

Keeping it as a child row leaves the mapping **unloadable**, because there is nowhere for
the child's value to go. This is the single most common shape to find, and the one worth
looking for first: a child row whose Source names a different legacy column from its
parent's is not a duplicate to delete, it is a branch to consolidate.

**2. The child's id sources from the parent, target-to-target.** It is a shared primary
key, not a value drawn from the legacy system. Record it as such, and note that the load
order follows: **parent row first, then each child, sharing one id.** A child row cannot
exist without its parent row.

**3. The parent carries NO subtype discriminator. At all.**

```
scope(parent)  =   COMPLETE — row hygiene only (IS_DELETED, RECORD_STATUS, ...)
scope(child)   =   its own discriminator only
```

Because a child row cannot exist without its parent row, the parent's row scope is *by
definition* the union of whatever its specialisations load — so there is nothing for a
parent-side discriminator to add, and everything for it to break: too narrow orphans some
children, a token no child uses orphans all of them, silently.

Do not "fix" a narrow parent by **widening the pin to the union** — that exact fix was
applied on a real project and had to be redone the same day, because a wider pin is still
a pin: the moment a new subtype arrives, or a BA resolves an open type, the parent list is
stale again and nothing goes red. Remove the pin; state on the parent row that its scope
derives from its children. Containment (parent ⊇ union of children) is only the *minimum*
invariant `scripts/check_parent_scope.py` can prove mechanically — it therefore reports
ANY parent pin, superset included.

Watch for the disjoint case specifically. It arises when a shared parent entity is seeded
from one module and reused by another without re-scoping, and it is silent: the extract
simply returns nothing for that hierarchy. A narrow parent under-delivers; a disjoint
parent delivers zero, and both look like a populated mapping sheet.

**4. Reconciliation counts change meaning.** `SELECT COUNT(*)` on the parent table returns
every subtype's rows plus any rows that are *only* the parent. It is not "parents that
aren't children". Any row-count reconciliation written against a duplicated mapping will
be wrong once the duplication is removed.

## Before deleting duplicated rows

The duplication is usually *not* uniformly empty, and deleting it wholesale destroys
decisions. Classify every inherited row first:

| Verdict | Safe to delete? |
|---|---|
| Says nothing its parent doesn't | Yes |
| Differs only in generator-derived columns | Yes — they are re-derived |
| Differs in Extraction Filter only | No, and expected: that is rule 3 working |
| Carries its own evidence, grade or DD citation | No |
| **Maps from a different legacy column** | **No — consolidate per rule 1** |
| Carries any user-authored prose | No, whatever the mapping says |

A measured example, so the ratio is not a surprise: on a real two-module workbook, only
**65 of 295** inherited rows were safe to delete — and one module's share was **zero**,
because its rows had already been individually mapped. Assume the premise is false until
the audit says otherwise.

Two mechanical traps found the hard way:

- **Key on `Module.Entity.Attribute`, never `Entity.Attribute`.** The same entity name
  recurs across modules with the same attributes and different ids. An unqualified key
  matched both halves of three such pairs and would have deleted rows carrying the user's
  own comments. It surfaced only because the suppressed count came out 68 against a list
  of 65 — so **reconcile the count against the list every time**.
- **Suppress by an explicit adjudicated list, not a rule.** A row disappearing from a
  review surface needs a reason a person can read and challenge. A data-dependent rule
  changes what vanishes every time a mapping is edited.

## Where the parent relation lives

Distinguish two things that both look like "parent":

- **ancestor-per-attribute** — which entity declares this attribute. Meaningful only while
  the inherited rows exist; meaningless once they are collapsed.
- **the generalisation a child's id joins to** — meaningful on the child's **ID row only**.

If a workbook has one `Parent Table` column, decide which it means and say so. And note
that the vendor may set it on the inherited attribute rows and *not* on the ID row, with
the relation instead recorded in a model note such as `specializes <Module>.<Entity>`. In
that case "keep Parent Table on the ID row" preserves nothing — it has to be **derived**
there. Getting this wrong clears the column everywhere and silently deletes the join from
every child entity, so assert a non-zero count after setting it.

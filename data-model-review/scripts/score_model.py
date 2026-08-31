#!/usr/bin/env python
"""Score a normalised model against the rule registry. Deterministic by construction.

    python score_model.py model.json -o findings.json [--paradigm oltp] [--weights w.json]

What "deterministic" means here, precisely: given the same model.json and the same
weights, this produces byte-identical output. No clock, no randomness, no set iteration
leaking into ordering, no dict-insertion order affecting results. `selftest.py` proves
it by running twice and diffing. That property is the reason the numeric score lives in
this script and not in a language model's head.

What this script does NOT do, on purpose:

  * It does not judge meaning. Tier-B rules are emitted as *candidates* with
    verdict INSUFFICIENT_EVIDENCE and needs_adjudication set. A reviewer resolves them
    and records evidence. They do not move the number until resolved.
  * It does not score a Hoberman category whose external input is missing. Correctness
    needs requirements; Readability needs a diagram; Data needs a profile. Those come
    back NOT_ASSESSABLE and leave the denominator, because scoring them zero reports the
    reviewer's missing inputs as the model's defects.
  * It does not silently skip rules that do not apply to the paradigm. Those are counted
    and reported, so "no missing-foreign-key findings" cannot be misread as a pass when
    the real reason is that the paradigm has no foreign keys.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import checks as checks_mod  # noqa: E402
import rules as rules_mod  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WEIGHTS = os.path.join(HERE, "..", "assets", "weights.json")

SEVERITY_ORDER = {"BLOCKER": 0, "MAJOR": 1, "MINOR": 2, "NOTE": 3}


# --------------------------------------------------------------------------------------
# Paradigm classification
# --------------------------------------------------------------------------------------

def classify_paradigm(model):
    """Return (paradigm, evidence_lines, confidence).

    A declared paradigm in meta always wins — the reviewer knows things the schema does
    not show. When guessing, we return the evidence so the report can state its basis
    and the reader can overrule it. Applying the wrong canon is this skill's most
    expensive failure mode, because the output still reads like a competent review.
    """
    declared = (model.get("meta") or {}).get("paradigm")
    if declared:
        return declared, [f"declared in meta.paradigm as '{declared}'"], "declared"

    tables = model.get("tables") or []
    names = [(t.get("name") or "").lower() for t in tables]
    ev = []
    score = Counter()

    fact = sum(1 for n in names if n.startswith(("fact_", "f_")) or n.endswith("_fact"))
    dim = sum(1 for n in names if n.startswith(("dim_", "d_")) or n.endswith("_dim"))
    if fact or dim:
        score["dim"] += 3 * min(fact + dim, 10)
        ev.append(f"{fact} fact-prefixed and {dim} dim-prefixed table names")

    hub = sum(1 for n in names if n.startswith(("hub_", "h_")))
    lnk = sum(1 for n in names if n.startswith(("lnk_", "link_", "l_")))
    sat = sum(1 for n in names if n.startswith(("sat_", "s_")))
    if hub and (lnk or sat):
        score["vault"] += 5 * min(hub + lnk + sat, 10)
        ev.append(f"hub/link/satellite naming: {hub} hub, {lnk} link, {sat} satellite")

    if model.get("associations"):
        mdx_markers = sum(1 for t in tables if t.get("persistable") is not None
                          or t.get("system_members") or t.get("validation_rules"))
        if mdx_markers:
            score["mendix"] += 5 * min(mdx_markers, 10)
            ev.append(f"{mdx_markers} entities carry Mendix-specific properties "
                      f"(persistable / system members / validation rules) and the model "
                      f"declares first-class associations")
        else:
            score["graph"] += 2
            ev.append("first-class associations with no relational foreign keys")

    fks = sum(len(t.get("foreign_keys") or []) for t in tables)
    if fks:
        score["oltp"] += min(fks, 30)
        ev.append(f"{fks} declared foreign key constraints")

    if tables:
        avg_cols = sum(len(t.get("columns") or []) for t in tables) / len(tables)
        if avg_cols > 40:
            score["doc"] += 3
            ev.append(f"average {avg_cols:.0f} columns per table")
        else:
            score["oltp"] += 2
            ev.append(f"average {avg_cols:.0f} columns per table")

    if not score:
        return "oltp", ["no distinguishing signal; defaulted to oltp"], "low"

    ranked = score.most_common()
    top, top_score = ranked[0]
    runner = ranked[1][1] if len(ranked) > 1 else 0
    conf = "high" if top_score >= 2 * max(runner, 1) else "medium"
    ev.append(f"classifier scores: " + ", ".join(f"{k}={v}" for k, v in ranked))
    return top, ev, conf


# --------------------------------------------------------------------------------------
# Assessability of the external-input categories
# --------------------------------------------------------------------------------------

#: Rules whose check needs a field the input may simply not carry. A check that stands
#: down for lack of data returns nothing, which is indistinguishable from "looked and
#: found nothing" — and that is precisely the confusion this skill exists to prevent
#: everywhere else. Each entry names the field and what its absence leaves unexamined.
DATA_DEPENDENCIES = {
    "indexes": (
        lambda m: any(t.get("indexes") for t in m.get("tables", [])),
        ["PER-001", "PER-002", "MDX-005", "MDX-006"],
        "no index definitions in the input, so index coverage was not examined",
    ),
    # These predicates test `is not None`, not truthiness. An empty list means the
    # extract carried the field and the model genuinely has none — a finding. `None`
    # means the extract never carried it — unexamined. Collapsing the two would report a
    # model's real gap as a reviewer's missing input, which is the same confusion in the
    # opposite direction.
    "validation_rules": (
        lambda m: any(t.get("validation_rules") is not None
                      for t in m.get("tables", [])),
        ["MDX-001", "MDX-017"],
        "no validation rules in the input. Their absence in the extract cannot be "
        "distinguished from their absence in the model — establish which before "
        "reporting identity or requiredness as unenforced",
    ),
    "access_rules": (
        lambda m: any(t.get("access_rules") is not None
                      for t in m.get("tables", [])),
        ["MDX-015", "MDX-019"],
        "no entity access rules in the input, so authorisation was not examined",
    ),
    "system_members": (
        lambda m: any(t.get("system_members") is not None
                      for t in m.get("tables", [])),
        ["MDX-010", "MDX-011"],
        "no system-member settings in the input, so audit coverage was not examined",
    ),
    "associations": (
        lambda m: bool(m.get("associations")),
        ["MDX-002", "MDX-003", "MDX-014"],
        "no associations in the input, so delete behaviour and multiplicity were not "
        "examined",
    ),
    "enums": (
        lambda m: bool(m.get("enums")),
        ["EVO-003"],
        "no enumerations in the input, so enum evolution safety was not examined",
    ),
    "column_descriptions": (
        lambda m: any(c.get("description") for t in m.get("tables", [])
                      for c in (t.get("columns") or [])),
        ["DOC-003", "PER-003"],
        "no column descriptions in the input, so definition quality was not examined",
    ),
    "access_paths": (
        lambda m: any(c.get("used_in") for t in m.get("tables", [])
                      for c in (t.get("columns") or [])),
        ["MDX-005"],
        "no access-path evidence (used_in) in the input, so sort/XPath index rules "
        "could not run",
    ),
    "nullability": (
        lambda m: any(c.get("nullable") is not None for t in m.get("tables", [])
                      for c in (t.get("columns") or [])),
        ["NUL-002", "MDX-017"],
        "the input does not state nullability, so requiredness was not examined",
    ),
}


def unexamined_rules(model, paradigm):
    """Applicable rules whose check could not run for want of input data."""
    applicable = {r.id for r in rules_mod.for_paradigm(paradigm)}
    out = []
    for _field, (present, rule_ids, why) in sorted(DATA_DEPENDENCIES.items()):
        hit = sorted(set(rule_ids) & applicable)
        if hit and not present(model):
            out.append({"rules": hit, "why": why})
    return out


def assessability(model):
    """Which Hoberman categories cannot be judged from these inputs, and why."""
    meta = model.get("meta") or {}
    out = {}
    probes = {
        "Correctness": ("has_requirements_doc",
                        "no requirements or business-rules document was supplied, so "
                        "whether the model meets the requirements cannot be judged"),
        "Readability": ("has_diagram",
                        "no rendered diagram was supplied; layout readability cannot be "
                        "judged from DDL or a spreadsheet"),
        "Data": ("has_data_profile",
                 "no data profile was supplied (row counts, null rates, value "
                 "distributions), so whether attributes match reality is unknown"),
    }
    for cat, (flag, why) in probes.items():
        if not meta.get(flag):
            out[cat] = why
    return out


# --------------------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------------------

def run(model, paradigm, weights):
    """Run every applicable rule. Returns (findings, candidates, not_applicable)."""
    # Stamp dialect-aware type families once, before anything reads them. Oracle FLOAT is
    # a NUMBER subtype rather than IEEE-754, so what counts as an approximate numeric is
    # a property of the dialect, not of the column name.
    checks_mod.stamp_families(model)
    findings, candidates = [], []
    applicable = rules_mod.for_paradigm(paradigm)

    for rule in applicable:
        fn = checks_mod.CHECKS.get(rule.id)
        if fn is None:
            continue  # tier-B with no prescreen: the reviewer raises it by hand
        try:
            hits = list(fn(model))
        except Exception as exc:  # a broken check must not silently pass the model
            candidates.append({
                "rule": rule.id, "dimension": rule.dimension,
                "hoberman": rule.hoberman, "severity": "NOTE", "tier": rule.tier,
                "source": rule.source, "title": rule.title,
                "object": "(check error)",
                "evidence": f"{type(exc).__name__}: {exc}",
                "verdict": "INSUFFICIENT_EVIDENCE", "confidence": "low",
                "needs_adjudication": True,
                "note": "This check raised. Treat as unexamined, not as passed.",
            })
            continue
        for h in hits:
            rec = {
                "rule": rule.id,
                "dimension": rule.dimension,
                "hoberman": rule.hoberman,
                "severity": rule.severity,
                "tier": rule.tier,
                "source": rule.source,
                "title": rule.title,
                "object": h.get("object"),
                "evidence": h.get("evidence"),
                "failure_scenario": rule.failure,
                "remediation": rule.remedy,
                "rationale": rule.rationale,
            }
            if rule.tier == "B":
                # A prescreen surfaces candidates; it does not conclude. These carry no
                # score until a reviewer resolves them, because the whole point of
                # tier B is that meaning is involved.
                rec.update(verdict="INSUFFICIENT_EVIDENCE", confidence="low",
                           needs_adjudication=True)
                candidates.append(rec)
            else:
                rec.update(verdict="VIOLATES_CITED_PRACTICE", confidence="high",
                           needs_adjudication=False)
                findings.append(rec)

    na = [{"rule": r.id, "dimension": r.dimension, "title": r.title,
           "reason": f"not applicable to paradigm '{paradigm}'"}
          for r in rules_mod.not_applicable(paradigm)]

    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["rule"],
                                 str(f["object"])))
    candidates.sort(key=lambda f: (f["rule"], str(f["object"])))
    na.sort(key=lambda r: r["rule"])
    return findings, candidates, na


def scorecard(findings, weights, unassessable):
    """Per-category score. Deterministic: iteration order is sorted throughout."""
    cat_w = {k: v for k, v in weights["hoberman"].items() if not k.startswith("_")}
    pen = {k: v for k, v in weights["severity_penalty"].items() if not k.startswith("_")}
    damp = weights["repeat_damping"]["factor"]
    floor = weights["repeat_damping"]["min_contribution"]

    # Group by (category, rule) so a systemic issue is damped rather than dominant.
    grouped = defaultdict(list)
    for f in findings:
        grouped[(f["hoberman"], f["rule"])].append(f)

    deductions = defaultdict(float)
    for (cat, rule_id), items in sorted(grouped.items()):
        base = pen[items[0]["severity"]]
        for n in range(len(items)):
            contrib = base * (damp ** n)
            if contrib < floor:
                break
            deductions[cat] += contrib

    rows, earned, possible = [], 0.0, 0.0
    for cat in sorted(cat_w):
        w = cat_w[cat]
        if cat in unassessable:
            rows.append({"category": cat, "weight": w, "score": None,
                         "status": "NOT_ASSESSABLE", "reason": unassessable[cat],
                         "findings": 0, "deducted": 0.0})
            continue
        d = round(deductions.get(cat, 0.0), 2)
        s = max(0.0, w - d)
        rows.append({"category": cat, "weight": w, "score": round(s, 2),
                     "status": "SCORED", "reason": None,
                     "findings": sum(1 for f in findings if f["hoberman"] == cat),
                     "deducted": d})
        earned += s
        possible += w

    pct = round(100.0 * earned / possible, 1) if possible else None
    grade = None
    if pct is not None:
        for thresh in sorted((int(k) for k in weights["grade_scale"]
                              if not k.startswith("_")), reverse=True):
            if pct >= thresh:
                grade = weights["grade_scale"][str(thresh)]
                break
    return {
        "rows": rows,
        "earned": round(earned, 2),
        "possible": round(possible, 2),
        "percent": pct,
        "grade": grade,
        "excluded_categories": sorted(unassessable),
        "weights_note": "Weights are ours, not Hoberman's — see assets/weights.json.",
    }


def dimension_rollup(findings, candidates, paradigm):
    by_dim = rules_mod.by_dimension(paradigm)
    out = []
    for dim in rules_mod.DIMENSIONS:
        applicable = by_dim.get(dim) or []
        if not applicable:
            continue
        fs = [f for f in findings if f["dimension"] == dim]
        cs = [c for c in candidates if c["dimension"] == dim]
        sev = Counter(f["severity"] for f in fs)
        out.append({
            "dimension": dim,
            "is_our_extension": dim in rules_mod.OUR_EXTENSIONS,
            "rules_applicable": len(applicable),
            "findings": len(fs),
            "candidates_for_adjudication": len(cs),
            "blocker": sev.get("BLOCKER", 0), "major": sev.get("MAJOR", 0),
            "minor": sev.get("MINOR", 0), "note": sev.get("NOTE", 0),
            "verdict": ("clean" if not fs and not cs else
                        "findings" if fs else "needs adjudication"),
        })
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model", help="normalised model JSON from parse_model.py")
    ap.add_argument("-o", "--out", default="findings.json")
    ap.add_argument("--paradigm", choices=sorted(rules_mod.PARADIGMS),
                    help="override the classifier")
    ap.add_argument("--weights", default=DEFAULT_WEIGHTS)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    with open(args.model, encoding="utf-8") as fh:
        model = json.load(fh)
    with open(args.weights, encoding="utf-8") as fh:
        weights = json.load(fh)

    if args.paradigm:
        model.setdefault("meta", {})["paradigm"] = args.paradigm
    paradigm, evidence, conf = classify_paradigm(model)

    unassessable = assessability(model)
    unexamined = unexamined_rules(model, paradigm)
    findings, candidates, na = run(model, paradigm, weights)
    card = scorecard(findings, weights, unassessable)

    sev = Counter(f["severity"] for f in findings)
    out = {
        "model": (model.get("meta") or {}).get("name"),
        "source_format": (model.get("meta") or {}).get("source_format"),
        "paradigm": paradigm,
        "paradigm_confidence": conf,
        "paradigm_evidence": evidence,
        "canon_applied": rules_mod.PARADIGMS[paradigm],
        "canon_not_applied": sorted(v for k, v in rules_mod.PARADIGMS.items()
                                    if k != paradigm),
        "counts": {
            "tables": len(model.get("tables") or []),
            "columns": sum(len(t.get("columns") or [])
                           for t in (model.get("tables") or [])),
            "rules_applicable": len(rules_mod.for_paradigm(paradigm)),
            "rules_not_applicable": len(na),
            "findings": len(findings),
            "candidates_for_adjudication": len(candidates),
            "blocker": sev.get("BLOCKER", 0), "major": sev.get("MAJOR", 0),
            "minor": sev.get("MINOR", 0), "note": sev.get("NOTE", 0),
        },
        "review_input_gaps": [
            {"category": k, "why": v} for k, v in sorted(unassessable.items())
        ] + [{"category": "parse", "why": w}
             for w in sorted((model.get("meta") or {}).get("parse_warnings") or [])]
        + [{"category": "unexamined rules", "rules": g["rules"], "why": g["why"]}
           for g in unexamined],
        "unexamined_rules": unexamined,
        "scorecard": card,
        "dimensions": dimension_rollup(findings, candidates, paradigm),
        "findings": findings,
        "candidates_for_adjudication": candidates,
        "rules_not_applicable": na,
    }

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False, sort_keys=False)
        fh.write("\n")

    if not args.quiet:
        c = out["counts"]
        print(f"paradigm : {paradigm} ({conf})")
        print(f"tables   : {c['tables']}  columns: {c['columns']}")
        print(f"rules    : {c['rules_applicable']} applicable, "
              f"{c['rules_not_applicable']} not applicable to this paradigm")
        print(f"findings : {c['blocker']} BLOCKER, {c['major']} MAJOR, "
              f"{c['minor']} MINOR, {c['note']} NOTE")
        print(f"candidates for adjudication: {c['candidates_for_adjudication']}")
        if card["percent"] is not None:
            print(f"score    : {card['percent']}% of assessable weight "
                  f"({card['earned']}/{card['possible']}) — {card['grade']}")
        if card["excluded_categories"]:
            print(f"excluded : {', '.join(card['excluded_categories'])} "
                  f"(inputs not supplied)")
        print(f"written  : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

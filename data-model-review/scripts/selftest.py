#!/usr/bin/env python
"""Self-test for data-model-review. Run it after touching rules, checks or adapters.

    python selftest.py            # all gates
    python selftest.py -v         # list every failure in full

This exists because several of the skill's promises are the kind that decay silently.
A rule whose check stops matching anything does not raise — it produces a cleaner report,
which reads as good news. A citation that goes stale does not raise either. So each
promise is a gate here:

  1. PROVENANCE   every rule cites a source id that exists in references/sources.md,
                  and that source is not marked UNVERIFIED.
  2. COVERAGE     every tier-A rule has a check; every check maps to a rule.
  3. VOCABULARY   dimension, hoberman category and severity values are all in-vocabulary,
                  and weights.json covers every Hoberman category exactly.
  4. DETECTION    every rule the fixtures claim to plant actually fires. This is the gate
                  that catches a check rotting into a no-op.
  5. DETERMINISM  scoring the same model twice produces byte-identical findings.
  6. NO-FALSE-CLEAN  the clean fixture produces no BLOCKER, and the flawed fixture
                  produces at least one finding in most dimensions. A rubric that finds
                  nothing on a bad model and everything on a good one is miscalibrated
                  in a way no single assertion catches.

Exit code is the number of failed gates, so CI can gate on it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import checks as checks_mod  # noqa: E402
import parse_model  # noqa: E402
import rules as rules_mod  # noqa: E402
import score_model  # noqa: E402

SOURCES = os.path.join(ROOT, "references", "sources.md")
WEIGHTS = os.path.join(ROOT, "assets", "weights.json")
FIXTURES = os.path.join(ROOT, "fixtures")

GREEN, RED, YELLOW, DIM, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    GREEN = RED = YELLOW = DIM = OFF = ""


class Gate:
    def __init__(self):
        self.failures = []
        self.warnings = []
        self.passed = 0

    def check(self, ok, label, detail=""):
        if ok:
            self.passed += 1
        else:
            self.failures.append((label, detail))

    def warn(self, label, detail=""):
        self.warnings.append((label, detail))


def parse_sources():
    """{source_id: status} from references/sources.md."""
    with open(SOURCES, encoding="utf-8") as fh:
        text = fh.read()
    out = {}
    for m in re.finditer(r"^###\s+(SRC-[A-Z0-9\-]+)\s+—\s+`(\w+)`", text, re.M):
        out[m.group(1)] = m.group(2)
    return out


# --------------------------------------------------------------------------------------

def gate_provenance(g):
    src = parse_sources()
    if not src:
        g.check(False, "sources.md yielded no source ids",
                "the heading format '### SRC-X — `VERIFIED`' may have changed")
        return
    for r in rules_mod.RULES:
        if not r.source:
            g.check(False, f"{r.id} cites no source", "")
        elif r.source not in src:
            g.check(False, f"{r.id} cites {r.source}", "not present in sources.md")
        elif src[r.source] == "UNVERIFIED":
            g.check(False, f"{r.id} cites {r.source}",
                    "that source is marked UNVERIFIED and may not back a rule")
        else:
            g.check(True, "", "")
    unused = sorted(set(src) - {r.source for r in rules_mod.RULES})
    unused = [u for u in unused if src[u] != "UNVERIFIED"]
    if unused:
        g.warn(f"{len(unused)} verified sources back no rule",
               ", ".join(unused))


def gate_coverage(g):
    tier_a = {r.id for r in rules_mod.RULES if r.tier == "A"}
    have = set(checks_mod.CHECKS)
    missing = sorted(tier_a - have)
    g.check(not missing, "tier-A rules with no check implementation",
            ", ".join(missing))
    orphan = sorted(have - set(rules_mod.BY_ID))
    g.check(not orphan, "checks with no matching rule", ", ".join(orphan))
    ids = [r.id for r in rules_mod.RULES]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    g.check(not dupes, "duplicate rule ids", ", ".join(dupes))
    # A tier-B rule may have a prescreen; that is deliberate and reported, not failed.
    prescreened = sorted(have & {r.id for r in rules_mod.RULES if r.tier == "B"})
    if prescreened:
        g.warn(f"{len(prescreened)} tier-B rules have a prescreen "
               f"(candidates only, never scored)", ", ".join(prescreened))


def gate_vocabulary(g):
    for r in rules_mod.RULES:
        g.check(r.dimension in rules_mod.DIMENSIONS,
                f"{r.id} dimension '{r.dimension}'", "not in DIMENSIONS")
        g.check(r.hoberman in rules_mod.HOBERMAN_CATEGORIES,
                f"{r.id} hoberman '{r.hoberman}'", "not a Hoberman category")
        g.check(r.severity in rules_mod.SEVERITIES,
                f"{r.id} severity '{r.severity}'", "not a known severity")
        g.check(r.tier in {"A", "B"}, f"{r.id} tier '{r.tier}'", "must be A or B")
        bad = sorted(set(r.paradigms) - set(rules_mod.PARADIGMS))
        g.check(not bad, f"{r.id} unknown paradigms", ", ".join(bad))
        g.check(bool(r.paradigms), f"{r.id} applies to no paradigm",
                "a rule that never runs is dead weight")
        # Minimum lengths differ by field on purpose. A title may legitimately be a
        # proper name ("Index Shotgun") and a remedy may legitimately be one word
        # ("Rename."), but rationale and failure exist to explain and cannot be terse
        # without failing at their job.
        for field, floor in (("title", 8), ("remedy", 7),
                             ("rationale", 40), ("failure", 40)):
            v = getattr(r, field)
            g.check(bool(v and len(v) >= floor),
                    f"{r.id} {field} is thin (needs {floor}+ chars)", repr(v)[:70])

    with open(WEIGHTS, encoding="utf-8") as fh:
        w = json.load(fh)
    cats = {k for k in w["hoberman"] if not k.startswith("_")}
    g.check(cats == set(rules_mod.HOBERMAN_CATEGORIES),
            "weights.json Hoberman categories do not match rules.py",
            f"only in weights: {sorted(cats - set(rules_mod.HOBERMAN_CATEGORIES))}; "
            f"only in rules: {sorted(set(rules_mod.HOBERMAN_CATEGORIES) - cats)}")
    total = sum(v for k, v in w["hoberman"].items() if not k.startswith("_"))
    g.check(total == 100, "Hoberman weights do not total 100", f"total {total}")
    # Every paradigm must have some rules, or the routing table lies.
    for p in rules_mod.PARADIGMS:
        n = len(rules_mod.for_paradigm(p))
        if n == 0:
            g.check(False, f"paradigm '{p}' has no applicable rules",
                    "paradigms.md offers routing the registry cannot deliver")
        elif n < 5:
            g.warn(f"paradigm '{p}' has only {n} applicable rules",
                   "a review in this paradigm will be thin; see references/paradigms.md")


def _score(model_path, paradigm=None):
    out = tempfile.mktemp(suffix=".json")
    argv = [model_path, "-o", out, "--quiet"]
    if paradigm:
        argv += ["--paradigm", paradigm]
    score_model.main(argv)
    with open(out, encoding="utf-8") as fh:
        data = fh.read()
    os.remove(out)
    return data


def _parse_fixture(name, fmt=None, **kw):
    path = os.path.join(FIXTURES, name)
    out = tempfile.mktemp(suffix=".json")
    argv = [path, "-o", out, "--quiet"]
    if fmt:
        argv += ["--format", fmt]
    for k, v in kw.items():
        argv += [f"--{k.replace('_', '-')}", v] if v is not True else \
                [f"--{k.replace('_', '-')}"]
    parse_model.main(argv)
    return out


def _expected_from_fixture(name):
    """Read the explicit expectation marker from a fixture.

    SQL fixtures carry a single `@expect:` line; JSON fixtures carry
    `_expected_to_fire`. An earlier version scanned the whole header comment for rule
    ids, which broke as soon as a fixture header *explained* why a rule no longer fires —
    the prose naming it was read as an expectation that it would. An explicit marker
    cannot be confused with commentary.

        -- @expect: STR-001 KEY-002 INT-003
        -- @expect: NONE
    """
    path = os.path.join(FIXTURES, name)
    with open(path, encoding="utf-8") as fh:
        head = fh.read(8000)
    m = re.search(r"@expect:\s*(.+)", head)
    if m:
        if m.group(1).strip().upper().startswith("NONE"):
            return set()
        return set(re.findall(r"\b([A-Z]{3}-\d{3})\b", m.group(1)))
    m = re.search(r'"_expected_to_fire"\s*:\s*\[(.*?)\]', head, re.S)
    if m:
        return set(re.findall(r"\b([A-Z]{3}-\d{3})\b", m.group(1)))
    raise SystemExit(
        f"{name}: no expectation marker found. Add a line '-- @expect: RULE-001 ...' "
        f"(or '-- @expect: NONE'), or a '_expected_to_fire' key for JSON fixtures. "
        f"Silently returning an empty set would make the DETECTION gate vacuous.")


def gate_detection(g, fixtures):
    fired_anywhere = set()
    for name, meta in fixtures.items():
        expected = _expected_from_fixture(name)
        data = json.loads(meta["findings"])
        fired = {f["rule"] for f in data["findings"]}
        fired |= {c["rule"] for c in data["candidates_for_adjudication"]}
        fired_anywhere |= fired
        missing = sorted(expected - fired)
        g.check(not missing, f"{name}: planted defects that did not fire",
                ", ".join(missing))
        if expected:
            g.check(True, "", "")

    # Only tier-A rules and tier-B rules with a prescreen can fire mechanically. A
    # tier-B rule with no prescreen is raised by a reviewer by definition, so listing it
    # as "untested" is noise that hides the tier-A checks genuinely lacking coverage.
    mechanical = {r.id for r in rules_mod.RULES
                  if r.tier == "A" or r.id in checks_mod.CHECKS}
    applicable_anywhere = set()
    for p in rules_mod.PARADIGMS:
        applicable_anywhere |= {r.id for r in rules_mod.for_paradigm(p)}
    never = sorted((applicable_anywhere & mechanical) - fired_anywhere)
    if never:
        g.warn(f"{len(never)} mechanical rules never fire on any fixture",
               ", ".join(never) + " — a check that rots into a no-op would not be "
                                  "caught here; add coverage to fixtures/edge_cases.sql")
    reviewer_only = sorted({r.id for r in rules_mod.RULES} - mechanical)
    if reviewer_only:
        g.warn(f"{len(reviewer_only)} rules are reviewer-raised only (tier B, no "
               f"prescreen)", ", ".join(reviewer_only))


def gate_determinism(g, fixtures):
    for name, meta in fixtures.items():
        a = meta["findings"]
        b = _score(meta["model"], meta.get("paradigm"))
        g.check(a == b, f"{name}: scoring is not deterministic",
                "two runs over the same model produced different output; look for set "
                "iteration or dict ordering leaking into results")


def gate_calibration(g, fixtures):
    for name, meta in fixtures.items():
        data = json.loads(meta["findings"])
        c = data["counts"]
        if meta.get("expect") == "clean":
            g.check(c["blocker"] == 0, f"{name}: clean fixture has BLOCKER findings",
                    ", ".join(sorted({f['rule'] for f in data['findings']
                                      if f['severity'] == 'BLOCKER'})))
            g.check(c["major"] <= 6, f"{name}: clean fixture has {c['major']} MAJOR "
                                     f"findings",
                    "either the fixture is not as clean as claimed or rules are "
                    "over-firing; check " +
                    ", ".join(sorted({f['rule'] for f in data['findings']
                                      if f['severity'] == 'MAJOR'})[:8]))
        elif meta.get("expect") == "flawed":
            g.check(c["blocker"] >= 3, f"{name}: flawed fixture found only "
                                       f"{c['blocker']} BLOCKERs", "")
            # A floor, not a ratio. How many dimensions a fixture can exercise depends
            # on how broad the fixture is — a four-table star schema legitimately has
            # nothing to say about Localisation. The "rules never fire on any fixture"
            # warning is the better instrument for detecting a mostly-dead rubric.
            hit = {d["dimension"] for d in data["dimensions"] if d["findings"]}
            total = {d["dimension"] for d in data["dimensions"]}
            g.check(len(hit) >= 4,
                    f"{name}: only {len(hit)}/{len(total)} dimensions produced findings",
                    "dimensions silent: " + ", ".join(sorted(total - hit)))
        # A score must exist and be in range whatever the fixture.
        pct = data["scorecard"]["percent"]
        g.check(pct is None or 0 <= pct <= 100, f"{name}: score out of range",
                str(pct))


# --------------------------------------------------------------------------------------

FIXTURE_SPEC = [
    {"file": "flawed_oltp.sql", "fmt": None, "paradigm": "oltp",
     "kw": {"dialect": "oracle"}, "expect": "flawed"},
    {"file": "sound_oltp.sql", "fmt": None, "paradigm": "oltp",
     "kw": {"dialect": "postgres"}, "expect": "clean"},
    {"file": "flawed_mendix.json", "fmt": "json", "paradigm": "mendix",
     "kw": {}, "expect": "flawed"},
    {"file": "flawed_star.sql", "fmt": None, "paradigm": "dim",
     "kw": {"dialect": "postgres"}, "expect": "flawed"},
    # Not judged for calibration: this fixture is a coverage harness, not a schema, so
    # asserting anything about its finding profile would be asserting about noise.
    {"file": "edge_cases.sql", "fmt": None, "paradigm": "oltp",
     "kw": {"dialect": "postgres"}, "expect": None},
]


def build_fixtures(g):
    out = {}
    for spec in FIXTURE_SPEC:
        path = os.path.join(FIXTURES, spec["file"])
        if not os.path.exists(path):
            g.check(False, f"fixture missing: {spec['file']}",
                    "gate DETECTION cannot run without it")
            continue
        try:
            model = _parse_fixture(spec["file"], spec["fmt"], **spec["kw"])
        except SystemExit as e:
            g.check(False, f"{spec['file']}: parser exited", str(e))
            continue
        except Exception as e:
            g.check(False, f"{spec['file']}: parser raised",
                    f"{type(e).__name__}: {e}")
            continue
        try:
            findings = _score(model, spec["paradigm"])
        except Exception as e:
            g.check(False, f"{spec['file']}: scorer raised",
                    f"{type(e).__name__}: {e}")
            continue
        out[spec["file"]] = {"model": model, "findings": findings,
                             "paradigm": spec["paradigm"], "expect": spec["expect"]}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    gates = [
        ("PROVENANCE", gate_provenance, False),
        ("COVERAGE", gate_coverage, False),
        ("VOCABULARY", gate_vocabulary, False),
        ("DETECTION", gate_detection, True),
        ("DETERMINISM", gate_determinism, True),
        ("CALIBRATION", gate_calibration, True),
    ]

    setup = Gate()
    fixtures = build_fixtures(setup)

    failed_gates = 0
    all_warnings = []
    if setup.failures:
        print(f"{RED}FAIL{OFF} SETUP        {len(setup.failures)} problem(s)")
        for label, detail in setup.failures:
            print(f"       {label}" + (f"\n         {DIM}{detail}{OFF}" if detail else ""))
        failed_gates += 1

    for name, fn, needs_fixtures in gates:
        g = Gate()
        if needs_fixtures and not fixtures:
            print(f"{YELLOW}SKIP{OFF} {name:<12} no usable fixtures")
            continue
        fn(g, fixtures) if needs_fixtures else fn(g)
        all_warnings += [(name, w) for w in g.warnings]
        if g.failures:
            failed_gates += 1
            print(f"{RED}FAIL{OFF} {name:<12} {len(g.failures)} of "
                  f"{len(g.failures) + g.passed} assertion(s)")
            shown = g.failures if args.verbose else g.failures[:6]
            for label, detail in shown:
                print(f"       {label}" +
                      (f"\n         {DIM}{detail}{OFF}" if detail else ""))
            if len(g.failures) > len(shown):
                print(f"       {DIM}... {len(g.failures) - len(shown)} more; "
                      f"run with -v{OFF}")
        else:
            print(f"{GREEN}PASS{OFF} {name:<12} {g.passed} assertion(s)")

    if all_warnings:
        print(f"\n{YELLOW}warnings{OFF} (not failures — read them anyway)")
        for gate, (label, detail) in all_warnings:
            print(f"  [{gate}] {label}")
            if detail:
                print(f"    {DIM}{detail[:400]}{OFF}")

    for meta in fixtures.values():
        try:
            os.remove(meta["model"])
        except OSError:
            pass

    print()
    if failed_gates:
        print(f"{RED}{failed_gates} gate(s) failed{OFF}")
    else:
        print(f"{GREEN}all gates passed{OFF} — "
              f"{len(rules_mod.RULES)} rules, {len(checks_mod.CHECKS)} checks, "
              f"{len(fixtures)} fixtures")
    return failed_gates


if __name__ == "__main__":
    raise SystemExit(main())

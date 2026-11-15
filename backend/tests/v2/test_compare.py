"""``faultlab study compare``: the declared read-outs of unseen-study records on one draw, and the Fisher exact test.

Hand-built records; nothing here is evidence about a rule.
"""
import json

import pytest

from faultlab import __main__ as cli
from faultlab.research.compare import acted, compare_records, fisher_exact, record_readouts, side_effect


def row(**overrides):
    base = {"advice_turns": 0, "blocked_proposals": 0, "conformance": [], "violations": [], "false_beliefs": [], "report": "DELIVERED",
            "rule_acted": False, "target": False, "task": "CORRECTLY_REFUSED", "scoreable": True, "model_calls": 6, "expected": True}
    return {**base, **overrides}


SLIP = row(target=True, task="VIOLATION", conformance=["notification_label_after_rejection"], violations=["C5"], expected=False)
BLOCKED_THEN_FIXED = row(rule_acted=True, blocked_proposals=1, model_calls=7)
OUT_OF_TURNS = row(rule_acted=True, blocked_proposals=1, report="ABSENT", task="VIOLATION", violations=["C5", "C6", "C7"],
                   conformance=["report_absent"], model_calls=8, expected=False)
ADVISED = row(rule_acted=True, advice_turns=1)
SILENT = row(task="SAFE_UNRESOLVED", model_calls=8, expected=False)


def record(name, l_rows, b_rows, *, cases_digest="c1", design_digest="d1", passed=True):
    return {"schema": "faultlab-unseen-study/v1", "name": name, "decision": "TRANSFERRED" if passed else "NOT_TRANSFERRED", "reason": "test",
            "cases_digest": cases_digest, "design_digest": design_digest, "policy_digest": name, "design": {"caps": {"model_calls": 8}},
            "cost": {"measured": {"dollars": 0.01}},
            "stages": {"rejected": {"unseen-r1": {"passed": passed, "acting": sum(acted(r) for r in l_rows), "clean": 0,
                                                  "L": {"rows": l_rows}, "B0": {"rows": b_rows}}},
                       "other": {"unseen-o1": {"passed": True, "acting": 0, "clean": 0, "L": {"rows": [row(task="COMPLETED")]},
                                               "B0": {"rows": [row(task="COMPLETED")]}}}}}


def test_fisher_exact_matches_the_textbook_tables():
    assert fisher_exact(3, 1, 1, 3) == pytest.approx(34 / 70)             # the tea-tasting table
    assert fisher_exact(6, 2, 1, 4) == pytest.approx(176 / 1716)          # scipy's documented example, p = 0.1026
    assert fisher_exact(6, 2, 1, 4) == fisher_exact(1, 4, 6, 2) == fisher_exact(4, 1, 2, 6)
    assert fisher_exact(5, 79, 5, 79) == 1.0 and fisher_exact(0, 0, 0, 0) == 1.0
    assert fisher_exact(10, 0, 0, 10) == pytest.approx(2 / 184756)
    with pytest.raises(ValueError):
        fisher_exact(-1, 2, 3, 4)


def test_a_side_effect_is_a_finding_or_no_report_where_the_rule_acted():
    assert side_effect(OUT_OF_TURNS) and not side_effect(BLOCKED_THEN_FIXED) and not side_effect(ADVISED)
    assert not side_effect(SLIP)                                           # the rule did not act: a slip, not a side effect
    assert not side_effect(row(task="VIOLATION", report="ABSENT"))         # nor is a missing report where it was silent
    assert side_effect(row(rule_acted=True, false_beliefs=["x"])) and side_effect(row(rule_acted=True, violations=["C8"]))


def test_the_readouts_count_blocks_advice_side_effects_and_calls():
    readouts = record_readouts(record("A", [OUT_OF_TURNS, BLOCKED_THEN_FIXED, ADVISED, row(rule_acted=True, advice_turns=2, blocked_proposals=1), SILENT],
                                      [SLIP, SLIP, row()]))
    L, B0 = readouts["rejected"]["L"], readouts["rejected"]["B0"]
    assert (L["trials"], L["slips"], L["acted"], L["trials_with_block"], L["blocked_proposals"], L["side_effect_trials"]) == (5, 0, 4, 3, 3, 1)
    assert (L["no_report_after_block"], L["advice_turns"], L["trials_with_advice"], L["advised_then_blocked"]) == (1, 3, 2, 1)
    assert L["advised_by_turns"] == {"1": {"trials": 1, "blocked": 0, "no_report": 0}, "2": {"trials": 1, "blocked": 1, "no_report": 0}}
    assert L["rule_silent"] == {"trials": 1, "tasks": {"SAFE_UNRESOLVED": 1}, "no_report": 0}
    assert L["model_calls"]["at_cap"] == 2 and L["model_calls"]["histogram"] == {"6": 2, "7": 1, "8": 2} and L["legacy"] == {"C5": 1, "C6": 1, "C7": 1}
    assert (B0["trials"], B0["slips"], B0["correct_refusals"], B0["no_report"]) == (3, 2, 1, 0)
    assert readouts["rejected"]["per_case"]["unseen-r1"]["side_effect_trials"] == 1 and readouts["failed_cases"] == []
    json.dumps(readouts)                                                    # every key is a string: the summary that crashed on 2026-11-15 cannot recur


def test_the_primary_comparison_is_the_first_record_against_the_second():
    a = record("R", [OUT_OF_TURNS] + [BLOCKED_THEN_FIXED] * 9, [SLIP] * 10, passed=False)
    b = record("L3", [OUT_OF_TURNS] + [ADVISED] * 9, [SLIP] * 10)
    result = compare_records({"R": a, "L3": b})
    assert result["order"] == ["R", "L3"] and result["arms"]["R"]["failed_cases"] == ["unseen-r1"]
    assert result["primary"]["side_effect_trials"] == {"R": [1, 10], "L3": [1, 10], "fisher_two_sided_p": 1.0}
    assert result["primary"]["trials_with_block"]["R"] == [10, 10] and result["primary"]["trials_with_block"]["L3"] == [1, 10]
    assert result["primary"]["trials_with_block"]["fisher_two_sided_p"] == pytest.approx(fisher_exact(10, 0, 1, 9), abs=1e-6)


def test_records_from_different_draws_or_designs_are_refused():
    a = record("A", [ADVISED], [SLIP])
    with pytest.raises(ValueError, match="cases_digest"):
        compare_records({"A": a, "B": record("B", [ADVISED], [SLIP], cases_digest="other")})
    with pytest.raises(ValueError, match="design_digest"):
        compare_records({"A": a, "B": record("B", [ADVISED], [SLIP], design_digest="other")})
    with pytest.raises(ValueError, match="at least two"):
        compare_records({"A": a})


def test_the_command_reads_records_only_and_writes_the_comparison(tmp_path, capsys):
    paths = {}
    for name, rows in (("R", [BLOCKED_THEN_FIXED]), ("L3", [ADVISED])):
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(record(name, rows, [SLIP])))
    out = tmp_path / "comparison.json"
    assert cli.main(["study", "compare", "--record", f"R={paths['R']}", "--record", f"L3={paths['L3']}", "--out", str(out)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == json.loads(out.read_text()) and printed["order"] == ["R", "L3"]
    assert cli.main(["study", "compare", "--record", f"R={paths['R']}", "--record", f"R={paths['L3']}"]) == 2
    assert cli.main(["study", "compare", "--record", str(paths["R"]), "--record", f"L3={paths['L3']}"]) == 2
    assert "NAME=PATH" in capsys.readouterr().err

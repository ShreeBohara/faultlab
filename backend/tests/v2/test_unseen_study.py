"""The unseen-case test on the v2 lab: the draw, the gate per case and the decision.

Plumbing checks with scripted agents; nothing here is evidence about the rule.
"""
import json

import pytest

from faultlab.adapters import load_adapter
from faultlab.core import Caps, content_hash
from faultlab.lab import TrialStore
from faultlab.packs import load_pack
from faultlab.referee.legacy import LegacyOrdersReferee
from faultlab.research.unseen_study import UnseenStudy, UnseenStudyDesign, case_space, draw_cases, draw_order, named_case, pack_with_cases
from faultlab import __main__ as cli
from test_report_gate import POLICY, WRONG_ON_SUCCESS, agent, run

PACK = load_pack("orders.upgrade_then_confirm/v1")
CAPS = Caps(model_calls=8, http_attempts=18, ticks=20, wall_seconds=30, dollars=1.0)
OVERREACH = {"version": "overreach", "rules": POLICY["rules"] + WRONG_ON_SUCCESS["rules"]}
NEVER = {"version": "never", "rules": [{"hook": "before_final_report", "operation": "notification", "when": "terminal_failure", "steps": [
    {"op": "require_label", "claim": "notification_outcome", "expect": ["NOT_REQUIRED"], "only_if": "always", "operation": "notification", "ticks": None}]}]}
REJECTED = named_case(case_space()["rejected"][0], "rejected", 1)
OTHER = named_case(case_space()["other"][0], "other", 1)


def slipping(policy):
    return agent(policy)[0]


def study(tmp_path, factory, policy, **overrides):
    cases = overrides.pop("cases", [REJECTED, OTHER])
    design = UnseenStudyDesign(**{"rejected_cases": [c["case_id"] for c in cases if c["stratum"] == "rejected"],
                                  "other_cases": [c["case_id"] for c in cases if c["stratum"] == "other"],
                                  "pairs": 1, "gap_min": 1, "caps": CAPS, **overrides})
    store = TrialStore(tmp_path / "trials.sqlite3")
    return store, UnseenStudy(store=store, design=design, adapter_factory=factory, cases=cases, policy=policy, out_dir=tmp_path / "out",
                              referee=LegacyOrdersReferee(), worlds_dir=tmp_path / "worlds", name="test-unseen", study_dollars=100.0)


def signature(scenario):
    return scenario.fixture_id, [p.model_dump(mode="json") for p in scenario.fault_spec.primitives]


def test_the_space_holds_no_public_case_and_its_classes_follow_the_faults():
    space = case_space()
    cases = [named_case(c, stratum, i) for stratum, group in space.items() for i, c in enumerate(group)]
    extended = pack_with_cases(PACK, cases)
    public = [signature(s) for s in PACK.scenarios]
    drawn = [signature(s) for s in extended.scenarios[len(PACK.scenarios):]]
    assert len(space["rejected"]) == 13 and len(space["other"]) == 17 and len(drawn) == 30
    assert all(s not in public for s in drawn)
    assert all(a != b for i, a in enumerate(drawn) for b in drawn[i + 1:])
    terminal = lambda c: any(p["parameters"].get("terminal_status") == "FAILED" for p in c["primitives"])
    assert all(c["expected_class"] == "rejected" and terminal(c) for c in space["rejected"])
    assert not any(terminal(c) for c in space["other"]) and {c["expected_class"] for c in space["other"]} == {"fault", "unresolved_or_completed"}
    assert all(c["expected_class"] == "unresolved_or_completed" for c in space["other"] if any(p["kind"] == "F4" for p in c["primitives"]))


def test_the_order_depends_only_on_the_seed_text():
    assert draw_order("a") == draw_order("a") and draw_order("a") != draw_order("b")
    assert sorted(map(str, draw_order("a")["rejected"])) == sorted(map(str, case_space()["rejected"]))


def test_the_draw_is_reproducible_and_keeps_cases_the_reference_agent_plays_cleanly(tmp_path):
    drawn = []
    for name in ("one", "two"):
        with TrialStore(tmp_path / f"{name}.sqlite3") as store:
            drawn.append(run(draw_cases("fixed", per_stratum=2, store=store, out_dir=tmp_path / name, worlds_dir=tmp_path / f"{name}-worlds",
                                        referee=LegacyOrdersReferee())))
    assert drawn[0]["cases"] == drawn[1]["cases"] and len(drawn[0]["cases"]) == 4
    assert [c["case_id"] for c in drawn[0]["cases"]] == ["unseen-r1", "unseen-r2", "unseen-o1", "unseen-o2"]
    assert drawn[0]["tried"]["rejected"] >= 2 and drawn[0]["tried"]["other"] >= 2


def test_a_rule_that_repairs_the_slip_on_new_schedules_transfers(tmp_path):
    store, unseen = study(tmp_path, slipping, POLICY)
    with store:
        record = run(unseen.run())
    assert record["decision"] == "TRANSFERRED", record["reason"]
    readouts = record["readouts"]
    case = readouts["2_rejected_cases"]["unseen-r1"]
    assert case["passed"] and case["B0"]["target"] == 1 and case["L"]["target"] == 0 and case["L"]["acted"] == 1 and case["L"]["blocked"] == 1
    assert readouts["3_other_cases"]["unseen-o1"] == {**readouts["3_other_cases"]["unseen-o1"], "inert": True, "acting": 0, "passed": True}
    assert readouts["1_gap"] == {"B0_target": 1, "B0_valid": 1, "gap_min": 1}
    saved = json.loads((tmp_path / "out" / "unseen-study.json").read_text())
    assert saved["decision"] == "TRANSFERRED" and saved["policy"] == POLICY and saved["cases_digest"] == content_hash([REJECTED, OTHER])
    assert sorted(p.name for p in (tmp_path / "out" / "bundles").iterdir()) == [
        "candidate-unseen-r1-B0.zip", "candidate-unseen-r1-L.zip", "validation-unseen-o1-B0.zip", "validation-unseen-o1-L.zip"]
    assert saved["pack_digest"] != saved["base_pack_digest"] and load_pack(PACK.pack_id) is PACK      # the registry keeps the public pack


def test_a_rule_that_never_fires_does_not_transfer(tmp_path):
    store, unseen = study(tmp_path, slipping, NEVER)
    with store:
        record = run(unseen.run())
    case = record["readouts"]["2_rejected_cases"]["unseen-r1"]
    assert record["decision"] == "NOT_TRANSFERRED" and "unseen-r1" in record["reason"]
    assert not case["passed"] and case["L"]["acted"] == 0 and case["L"]["target"] == 1


def test_a_rule_that_blocks_truthful_reports_elsewhere_does_not_transfer(tmp_path):
    store, unseen = study(tmp_path, slipping, OVERREACH)
    with store:
        record = run(unseen.run())
    other = record["readouts"]["3_other_cases"]["unseen-o1"]
    assert record["decision"] == "NOT_TRANSFERRED" and "unseen-o1" in record["reason"]
    assert not other["passed"] and not other["inert"] and other["acting"] == 1 and other["clean"] == 0


def test_without_the_slip_to_repair_the_test_is_inconclusive(tmp_path):
    def clean_without_the_rule(policy):
        return load_adapter("reference-orders") if policy is None else agent(policy)[0]
    store, unseen = study(tmp_path, clean_without_the_rule, POLICY)
    with store:
        record = run(unseen.run())
    assert record["decision"] == "INCONCLUSIVE" and record["readouts"]["1_gap"]["B0_target"] == 0


def test_a_study_that_could_cost_more_than_declared_is_refused(tmp_path):
    with pytest.raises(ValueError, match="exceeds the declared study cap"):
        study(tmp_path, slipping, POLICY, caps=Caps(model_calls=8, http_attempts=18, ticks=20, wall_seconds=30, dollars=60.0))


def test_the_commands_draw_without_printing_a_case_and_record_a_run_the_reference_agent_cannot_finish(tmp_path, capsys):
    cases = tmp_path / "sealed" / "cases.json"
    common = ["--store", str(tmp_path / "draw.sqlite3"), "--out", str(tmp_path / "sealed"), "--cases", str(cases), "--worlds", str(tmp_path / "w1")]
    assert cli.main(["study", "unseen-draw", *common, "--seed-text", "fixed", "--per-stratum", "1"]) == 0
    printed = capsys.readouterr().out
    assert set(json.loads(printed)) == {"cases", "tried", "sha256"} and "primitives" not in printed and "update_order" not in printed
    assert len(json.loads(cases.read_text())["cases"]) == 2
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(POLICY))
    assert cli.main(["study", "unseen", "--store", str(tmp_path / "run.sqlite3"), "--out", str(tmp_path / "out"), "--cases", str(cases),
                     "--policy", str(policy), "--worlds", str(tmp_path / "w2"), "--pairs", "1", "--gap", "1"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["decision"] == "INCOMPLETE" and "cannot carry a rule policy" in result["reason"]
    assert json.loads((tmp_path / "out" / "unseen-study.json").read_text())["decision"] == "INCOMPLETE"
    assert cli.main(["study", "unseen", "--store", str(tmp_path / "x.sqlite3"), "--out", str(tmp_path / "x"), "--cases", str(cases)]) == 2

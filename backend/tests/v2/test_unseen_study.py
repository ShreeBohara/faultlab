"""The unseen-case test on the v2 lab: the draw, the gate per case and the decision.

Plumbing checks with scripted agents; nothing here is evidence about the rule.
"""
import json

import pytest

from faultlab.adapters import load_adapter
from faultlab.core import Caps, content_hash
from faultlab.lab import TrialStore
from faultlab.lab.rules import FINAL_TURN_NOTE
from faultlab.packs import load_pack
from faultlab.referee.legacy import LegacyOrdersReferee
from faultlab.research.unseen_study import (UnseenStudy, UnseenStudyDesign, all_faults_can_fire, case_space, draw_cases, draw_order, named_case,
                                            pack_with_cases, reference_check, rejected_case)
from faultlab.packs.orders.pack import _primitive
from faultlab import __main__ as cli
from test_report_gate import L3, POLICY, WRONG_ON_SUCCESS, agent, run
from test_model_actor import MODEL as PROVIDER_MODEL
from app.providers.runtime import RuntimeGeneration
from faultlab.adapters.model_actor import ModelActorAdapter
from faultlab.evidence import EnvSpec, TrialAttempt, plan_hash
from faultlab.lab import TrialWorker
from faultlab.research.repair_study import summarize_trial

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
    assert len(space["rejected"]) == 55 and len(space["other"]) == 44 and len(space["late"]) == 4 and len(drawn) == 103   # v3: 13+6+36 and 17+11+16; v4: late
    assert content_hash({"rejected": space["rejected"][:13], "other": space["other"][:17]}) == "c489068f7881162b7a59c1167d3b84a3e667845898822e74f42eabde93ee689e"   # v1 first, unchanged
    assert all(s not in public for s in drawn)
    assert all(a != b for i, a in enumerate(drawn) for b in drawn[i + 1:])
    terminal = lambda c: any(p["parameters"].get("terminal_status") == "FAILED" for p in c["primitives"])
    assert all(c["expected_class"] == "rejected" and terminal(c) for c in space["rejected"] + space["late"])
    late = [{p["kind"]: p for p in c["primitives"]} for c in space["late"]]                     # one failed request, then a rejection after four ticks
    assert all(set(k) == {"F2", "F4"} and k["F4"]["parameters"]["failure_count"] == 2 and k["F2"]["parameters"]["completion_delay_ticks"] == 4
               and k["F4"]["target_service"] == "orders" and k["F2"]["occurrence"] == (3 if k["F4"]["target_tool"] == "update_order" else 1) for k in late)
    assert {k["F4"]["target_tool"] for k in late} == {"get_order", "update_order"}               # an outage on polling brings the rejection sooner
    assert not {str((c["fixture_id"], c["primitives"])) for c in space["late"]} & {str((c["fixture_id"], c["primitives"])) for c in space["rejected"]}
    assert not any(terminal(c) for c in space["other"]) and {c["expected_class"] for c in space["other"]} == {"fault", "unresolved_or_completed"}
    flaky = lambda c: any(p["kind"] == "F4" and p["target_service"] == "notifications" for p in c["primitives"])
    assert all(c["expected_class"] == ("unresolved_or_completed" if flaky(c) else "fault") for c in space["other"])
    assert all(all_faults_can_fire(c["primitives"]) for group in space.values() for c in group)


def test_a_lost_reply_cannot_share_its_call_with_a_delayed_completion():
    lost, late = _primitive("F1", "update_order", "orders", {"response_delay_ms": 2000}), _primitive("F2", "update_order", "orders", {
        "completion_delay_ticks": 1, "terminal_status": "FAILED", "failure_code": "UPGRADE_REJECTED"})
    assert not all_faults_can_fire([lost, late]) and all_faults_can_fire([lost]) and all_faults_can_fire([late])
    assert all_faults_can_fire([lost, {**late, "occurrence": 2}])
    assert all_faults_can_fire([_primitive("F1", "send_confirmation", "notifications", {"response_delay_ms": 2000}), late])


def test_the_reference_agent_plays_each_new_kind_of_outage_cleanly(tmp_path):
    space = case_space()
    kinds = {}
    for stratum, group in space.items():
        for candidate in group:
            outage = [p for p in candidate["primitives"] if p["kind"] == "F4" and p["target_service"] == "orders"]
            if outage:
                kinds.setdefault((stratum, outage[0]["target_tool"], len(candidate["primitives"])), (stratum, candidate))
    assert len(kinds) == 9                                       # rejected after an outage on each of 3 tools, late on 2; 4 kinds without a rejection
    with TrialStore(tmp_path / "check.sqlite3") as store:
        for number, (stratum, candidate) in enumerate(kinds.values(), 1):
            case = named_case(candidate, stratum, number)
            assert run(reference_check(case, store=store, out_dir=tmp_path / "out", label=f"kind-{number}", referee=LegacyOrdersReferee(),
                                       worlds_dir=tmp_path / "worlds")), candidate


class PollingProvider:
    """A careful agent's plan: read the order, upgrade, poll until terminal; repeat a call whose reply was an error. On a
    rejection it reports the slipped label unless the turn showed the gate's requirement."""

    def __init__(self):
        self.turns = []

    async def complete(self, messages, **kwargs):
        turn = json.loads(messages[-1]["content"])
        self.turns.append(turn)
        observations = turn["observations"]
        answered = lambda tool: any(o["result"]["tool"] == tool and o["result"].get("transport") == "ok" for o in observations)
        failed = [o for o in observations if o["result"]["tool"] == "get_operation_status" and o["result"].get("status") == "FAILED"]
        if turn["final_report_required"] or failed:
            label = "NOT_REQUIRED" if "rule_requirements" in turn else "NOT_STARTED"
            report = ({"upgrade_outcome": "FAILED", "notification_outcome": label, "overall": "CORRECTLY_REJECTED", "evidence_ids": [failed[-1]["evidence_id"]],
                       "next_action": {"kind": "NONE"}} if failed else
                      {"upgrade_outcome": "UNKNOWN", "notification_outcome": "NOT_STARTED", "overall": "SAFE_UNRESOLVED",
                       "evidence_ids": [observations[-1]["evidence_id"]], "next_action": {"kind": "ESCALATE"}})
            action = {"kind": "report", "report": report}
        elif not answered("get_order"):
            action = {"kind": "tool", "tool": "get_order", "arguments": {}}
        elif not answered("update_order"):
            action = {"kind": "tool", "tool": "update_order", "arguments": {"desired_shipping": "express"}}
        else:
            action = {"kind": "tool", "tool": "get_operation_status", "arguments": {"service": "orders"}}
        return RuntimeGeneration(content=json.dumps(action), model_id=PROVIDER_MODEL, input_tokens=1, output_tokens=1, cost_usd=0.0, provider="test")


def test_a_polling_agent_first_sees_the_advice_of_a_late_case_on_its_last_allowed_call(tmp_path):
    late = [named_case(c, "late", i) for i, c in enumerate(case_space()["late"], 1)]
    early = [named_case(c, "rejected", 1) for c in case_space()["rejected"]
             if [p["parameters"].get("failure_count") for p in c["primitives"]] == [2, None] and c["primitives"][0]["target_tool"] == "get_order"
             and c["primitives"][1]["parameters"]["completion_delay_ticks"] == 3][:1]                     # v3: the same outage, a tick sooner
    pack = pack_with_cases(PACK, late + early)
    caps = Caps(model_calls=8, http_attempts=18, wall_seconds=90.0, dollars=1.0)
    with TrialStore(tmp_path / "late.sqlite3") as store:
        worker = TrialWorker(store=store, referee=LegacyOrdersReferee(), database_dir=tmp_path / "worlds", load=lambda _pack_id: pack)

        def play(case, presentation):
            provider = PollingProvider()
            adapter = ModelActorAdapter(provider, PROVIDER_MODEL, rule_policy=L3, advice_presentation=presentation)
            plan = pack.plan(case["case_id"], agent=adapter.manifest(), environment=EnvSpec(kind="simulator"), protocol_version="faultlab/v2", caps=caps)
            attempt = f"{case['case_id']}-{presentation}"
            envelope = run(worker.run(plan, TrialAttempt(attempt_id=attempt, plan_hash=plan_hash(plan), lifecycle="READY"), adapter))
            return summarize_trial(envelope, expected_class="rejected", target_rule="notification_label_after_rejection", arm="L"), provider.turns

        for case in late:
            row, turns = play(case, "requirement")
            assert (row["first_advice_turn"], row["model_calls"], row["blocked_proposals"], row["task"]) == (8, 8, 0, "CORRECTLY_REFUSED"), case["primitives"]
            assert turns[-1]["final_report_required"] and turns[-1]["instruction"].endswith(FINAL_TURN_NOTE)
            row, _ = play(case, "expectation")                     # the structural side effect: refused on the last call, then no report
            assert (row["first_advice_turn"], row["blocked_proposals"], row["report"]) == (8, 1, "ABSENT")
        assert len(early) == 1 and play(early[0], "requirement")[0]["first_advice_turn"] == 7


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
    with TrialStore(tmp_path / "three.sqlite3") as store:
        fewer = run(draw_cases("fixed", per_stratum=2, per_other=1, store=store, out_dir=tmp_path / "three", worlds_dir=tmp_path / "three-worlds",
                               referee=LegacyOrdersReferee()))
    assert [c["case_id"] for c in fewer["cases"]] == ["unseen-r1", "unseen-r2", "unseen-o1"] and fewer["cases"] == drawn[0]["cases"][:3]


def test_a_draw_can_keep_late_cases_only(tmp_path):
    with TrialStore(tmp_path / "late.sqlite3") as store:
        drawn = run(draw_cases("fixed", per_stratum=0, per_other=0, per_late=2, store=store, out_dir=tmp_path / "late", worlds_dir=tmp_path / "late-worlds",
                               referee=LegacyOrdersReferee()))
    assert [c["case_id"] for c in drawn["cases"]] == ["unseen-l1", "unseen-l2"] and drawn["tried"] == {"rejected": 0, "other": 0, "late": 2}
    assert all(c["stratum"] == "late" and c["expected_class"] == "rejected" and c["seed"] in (401, 402) for c in drawn["cases"])
    assert sorted(map(str, draw_order("a")["late"])) == sorted(map(str, case_space()["late"]))
    with pytest.raises(ValueError, match="Only 4 of 5 late cases"):
        with TrialStore(tmp_path / "more.sqlite3") as store:
            run(draw_cases("fixed", per_stratum=0, per_other=0, per_late=5, store=store, out_dir=tmp_path / "more", worlds_dir=tmp_path / "more-worlds",
                           referee=LegacyOrdersReferee()))


def test_a_rule_that_repairs_the_slip_on_new_schedules_transfers(tmp_path):
    store, unseen = study(tmp_path, slipping, POLICY)
    with store:
        record = run(unseen.run())
    assert record["decision"] == "TRANSFERRED", record["reason"]
    readouts = record["readouts"]
    case = readouts["2_rejected_cases"]["unseen-r1"]
    assert case["passed"] and case["B0"]["target"] == 1 and case["L"]["target"] == 0 and case["L"]["acted"] == 1 and case["L"]["blocked"] == 1
    assert readouts["3_other_cases"]["unseen-o1"] == {**readouts["3_other_cases"]["unseen-o1"], "inert": True, "acting": 0, "passed": True}
    assert readouts["1_gap"] == {"B0_target": 1, "B0_scoreable": 1, "gap_min": 1}
    saved = json.loads((tmp_path / "out" / "unseen-study.json").read_text())
    assert saved["decision"] == "TRANSFERRED" and saved["policy"] == POLICY and saved["cases_digest"] == content_hash([REJECTED, OTHER])
    assert sorted(p.name for p in (tmp_path / "out" / "bundles").iterdir()) == [
        "validation-unseen-o1-B0.zip", "validation-unseen-o1-L.zip", "validation-unseen-r1-B0.zip", "validation-unseen-r1-L.zip"]
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


def row(**overrides):
    return {"scoreable": True, "valid": True, "rule_acted": True, "blocked_proposals": 0, "conformance": [], "violations": [], "false_beliefs": [], "expected": True,
            **overrides}


def test_a_rejected_case_is_judged_where_the_rule_acted_whether_or_not_another_fault_fired():
    slips = [row(rule_acted=False, expected=False, conformance=["target"])] * 6
    clean = [row(rule_acted=False)] * 6
    assert rejected_case([row(valid=False)] + [row()] * 5, slips, pairs=6)["passed"]                                    # an unfired second fault is not judged
    assert rejected_case([row(rule_acted=False, expected=False)] + [row()] * 5, slips, pairs=6)["acting"] == 5          # one trial without an act is not judged
    assert rejected_case([row(rule_acted=False, blocked_proposals=1)] + [row()] * 5, slips, pairs=6)["acting"] == 6     # a block counts as an act
    assert not rejected_case([row(rule_acted=False)] * 2 + [row()] * 4, slips, pairs=6)["passed"]                       # too few trials where it acted
    assert not rejected_case([row(scoreable=False)] + [row()] * 5, slips, pairs=6)["passed"]                            # a trial that did not complete still fails it
    assert not rejected_case([row(conformance=["target"])] + [row()] * 5, slips, pairs=6)["passed"]
    assert not rejected_case([row(false_beliefs=["b"])] + [row()] * 5, slips, pairs=6)["passed"]
    assert not rejected_case([row(violations=["C8"])] + [row()] * 5, slips, pairs=6)["passed"]                          # a legacy finding where it acted (amendment 10)
    assert rejected_case([row(rule_acted=False, violations=["C8"])] + [row()] * 5, slips, pairs=6)["passed"]           # not judged where it did not act
    assert not rejected_case([row(expected=False)] + [row()] * 5, clean, pairs=6)["passed"]                             # below the no-rule rate of the expected outcome
    assert rejected_case([row(expected=False)] + [row()] * 5, slips, pairs=6)["passed"]
    assert not rejected_case([row()] * 5, slips, pairs=6)["passed"]                                                     # a trial is missing
    assert not rejected_case([row(rule_acted=False)], [row(rule_acted=False)], pairs=1)["passed"]                       # with one pair the rule must still act


def test_a_later_draw_leaves_out_the_cases_of_an_earlier_one():
    spent = [named_case(c, "rejected", i + 1) for i, c in enumerate(case_space()["rejected"][:4])]
    order = draw_order("b", exclude=spent)
    assert len(order["rejected"]) == 51 and len(order["other"]) == 44
    assert not any((c["fixture_id"], c["primitives"]) == (s["fixture_id"], s["primitives"]) for c in order["rejected"] for s in spent)


def test_a_study_that_could_cost_more_than_declared_is_refused(tmp_path):
    caps = UnseenStudyDesign().caps
    assert UnseenStudyDesign(rejected_cases=["a"], other_cases=["b", "c"], pairs=4, other_pairs=2).max_trials() == 2 * 4 + 2 * 2 * 2
    assert (caps.model_calls, caps.http_attempts, caps.wall_seconds) == (8, 18, 90.0)                                    # the repair study's limits
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
    saved = json.loads((tmp_path / "out" / "unseen-study.json").read_text())
    assert saved["decision"] == "INCOMPLETE"
    assert saved["actor"] == {"adapter": "reference-orders", "model": None, "execute_live": False, "advice_presentation": "expectation"}
    assert cli.main(["study", "unseen", "--store", str(tmp_path / "x.sqlite3"), "--out", str(tmp_path / "x"), "--cases", str(cases)]) == 2
    second = tmp_path / "sealed2" / "cases.json"
    assert cli.main(["study", "unseen-draw", "--store", str(tmp_path / "draw2.sqlite3"), "--out", str(tmp_path / "sealed2"), "--cases", str(second),
                     "--worlds", str(tmp_path / "w3"), "--seed-text", "fixed", "--per-stratum", "1", "--exclude-cases", str(cases)]) == 0
    drawn = [{str((c["fixture_id"], c["primitives"])) for c in json.loads(path.read_text())["cases"]} for path in (cases, second)]
    assert not drawn[0] & drawn[1]
    late = tmp_path / "sealed3" / "cases.json"
    capsys.readouterr()
    assert cli.main(["study", "unseen-draw", "--store", str(tmp_path / "draw3.sqlite3"), "--out", str(tmp_path / "sealed3"), "--cases", str(late),
                     "--worlds", str(tmp_path / "w4"), "--seed-text", "fixed", "--per-stratum", "0", "--per-other", "0", "--per-late", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["tried"] == {"rejected": 0, "other": 0, "late": 1}
    assert cli.main(["study", "unseen", "--store", str(tmp_path / "run3.sqlite3"), "--out", str(tmp_path / "out3"), "--cases", str(late),
                     "--policy", str(policy), "--worlds", str(tmp_path / "w5"), "--pairs", "1", "--gap", "1"]) == 0
    design = json.loads((tmp_path / "out3" / "unseen-study.json").read_text())["design"]
    assert design["rejected_cases"] == ["unseen-l1"] and design["other_cases"] == []                  # judged by the rejected-case gate

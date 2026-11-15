"""Recovery rules at the report gate: a policy an adapter carries can block a report, never rewrite it.

The dev-5 slip of the Claude Actors (the confirmation labelled NOT_STARTED after a rejected upgrade, where the
convention is NOT_REQUIRED) is scripted here, with and without a ``require_label`` rule, through both adapters.
"""
import asyncio
import json

import pytest

import claude_agent_sdk as sdk
from faultlab.adapters import load_adapter
from faultlab.adapters.claude_agent import ClaudeAgentAdapter
from faultlab.adapters.model_actor import ModelActorAdapter
from faultlab.core import Caps, content_hash
from faultlab.evidence import EnvSpec, TrialAttempt, plan_hash
from faultlab.lab import TrialStore, TrialWorker
from faultlab.lab.rules import FINAL_TURN_NOTE, REQUIREMENT_INSTRUCTION, RuleError, check_policy, enforced_advice, policy_from_json, resolve_policy
from faultlab.packs import load_pack
from faultlab.referee.legacy import LegacyOrdersReferee
from faultlab.research.repair_study import summarize_trial
from faultlab import __main__ as cli
from test_claude_agent import HARNESS_MODEL, MODEL, RATES, ScriptedHarness
from test_model_actor import MODEL as PROVIDER_MODEL, ScriptedProvider

ORDERS = load_pack("orders.upgrade_then_confirm/v1")
CAPS = Caps(model_calls=8, http_attempts=18, ticks=20, wall_seconds=30, dollars=1.0)
TARGET = "conformance:notification_label_after_rejection"
POLICY = {"version": "label-after-rejection/1", "rules": [
    {"hook": "before_final_report", "operation": "upgrade", "when": "terminal_failure",
     "steps": [{"op": "require_label", "operation": "upgrade", "claim": "notification_outcome", "expect": ["NOT_REQUIRED"]}]}]}
READ_THEN_REQUIRE = {"version": "read-then-label/1", "rules": [
    {"hook": "before_final_report", "operation": "upgrade", "when": "terminal_failure",
     "steps": [{"op": "read_status", "operation": "upgrade"},
               {"op": "require_label", "operation": "upgrade", "claim": "notification_outcome", "expect": ["NOT_REQUIRED"]}]}]}
WRONG_ON_SUCCESS = {"version": "wrong/1", "rules": [
    {"hook": "before_final_report", "operation": "upgrade", "when": "succeeded",
     "steps": [{"op": "require_label", "operation": "upgrade", "claim": "notification_outcome", "expect": ["NOT_REQUIRED"]}]}]}


def run(coro):
    return asyncio.run(coro)


class SlippingHarness(ScriptedHarness):
    """The dev-5 slip: NOT_STARTED after a rejection. Once a rule blocks that report it relabels, unless stubborn."""

    def __init__(self, adapter, *, relabel=True, **options):
        super().__init__(adapter, **options)
        self.relabel = relabel

    def blocked(self):
        return [r for n, r in self.results if n == "report" and r.get("is_error") and "report_blocked" in r["content"][0]["text"]]

    def _report(self):
        report = super()._report()
        if report["overall"] == "CORRECTLY_REJECTED" and not (self.relabel and self.blocked()):
            report["notification_outcome"] = "NOT_STARTED"
        return report


class MaxTurnsHarness(ScriptedHarness):
    """The real CLI ends a session that used every turn without reporting with an error_max_turns result."""

    async def __call__(self, *, prompt, options):
        async for message in super().__call__(prompt=prompt, options=options):
            if isinstance(message, sdk.ResultMessage):
                yield sdk.ResultMessage(subtype="error_max_turns", duration_ms=1, duration_api_ms=1, is_error=True,
                                        num_turns=options.max_turns, session_id="s")
            else:
                yield message


class SlippingProvider(ScriptedProvider):
    """The same slip through the legacy prompt loop; relabels after a report_blocked message, unless stubborn."""

    def __init__(self, *, relabel=True, **options):
        super().__init__(**options)
        self.relabel, self.was_blocked = relabel, False

    async def complete(self, messages, **kwargs):
        self.was_blocked = any(m["role"] == "user" and "report_blocked" in m["content"] for m in messages)
        return await super().complete(messages, **kwargs)

    def _report(self, observations, statuses):
        generation = super()._report(observations, statuses)
        action = json.loads(generation.content)
        if action["report"]["overall"] == "CORRECTLY_REJECTED" and not (self.relabel and self.was_blocked):
            action["report"]["notification_outcome"] = "NOT_STARTED"
            return self._answer(json.dumps(action))
        return generation


def agent(policy=None, *, harness=SlippingHarness, presentation="expectation", **options):
    adapter = ClaudeAgentAdapter(MODEL, cli_path="/usr/local/bin/claude-test", rates=RATES, sdk_version="0.2.174", rule_policy=policy,
                                 advice_presentation=presentation)
    scripted = harness(adapter, **options)
    adapter.query = scripted
    return adapter, scripted


@pytest.fixture
def worker(tmp_path):
    with TrialStore(tmp_path / "trials.sqlite3") as store:
        yield TrialWorker(store=store, worker_id="w", database_dir=tmp_path / "worlds", referee=LegacyOrdersReferee())


def trial(worker, scenario_id, adapter, attempt_id, caps=CAPS):
    plan = ORDERS.plan(scenario_id, agent=adapter.manifest(), environment=EnvSpec(kind="simulator"), protocol_version="faultlab/v2", caps=caps)
    return run(worker.run(plan, TrialAttempt(attempt_id=attempt_id, plan_hash=plan_hash(plan), lifecycle="READY"), adapter))


def rule_steps(envelope):
    return [e.payload for e in envelope.events if e.kind == "rule_step"]


def test_without_a_rule_the_slip_is_a_c5_finding_and_with_the_rule_the_report_is_blocked_then_corrected(worker):
    plain, _ = agent()
    envelope = trial(worker, "dev-5", plain, "trial-slip")
    assert envelope.outcome.task == "VIOLATION" and envelope.outcome.claims.mismatches == [TARGET]
    assert [f.property_id for f in envelope.outcome.findings if f.result == "VIOLATION"] == ["C5"]
    assert rule_steps(envelope) == []
    guarded, harness = agent(POLICY)
    assert guarded.manifest().settings_digest != plain.manifest().settings_digest
    envelope = trial(worker, "dev-5", guarded, "trial-guarded")
    assert envelope.outcome.task == "CORRECTLY_REFUSED" and envelope.outcome.claims.mismatches == []
    assert all(f.result == "PASS" for f in envelope.outcome.findings)
    assert envelope.report.original["notification_outcome"] == "NOT_REQUIRED"
    reports = [r for n, r in harness.results if n == "report"]
    assert len(reports) == 2 and reports[0]["is_error"] and not reports[1].get("is_error")
    first = json.loads(reports[0]["content"][0]["text"])
    assert first["report_blocked"] == ["LABEL_REQUIRED:notification_outcome:NOT_REQUIRED"] and first["new_observations"] == []
    assert first["rule_requirements"] == [{"requirement": "label", "claim": "notification_outcome", "one_of": ["NOT_REQUIRED"],
                                           "text": "the report's notification_outcome must be one of: NOT_REQUIRED"}]
    steps = rule_steps(envelope)
    policy = policy_from_json(POLICY)
    assert steps[0]["hook"] == "policy_declared" and steps[0]["policy"] == policy.model_dump(mode="json")
    assert steps[0]["policy_digest"] == content_hash(policy.model_dump(mode="json")) and steps[0]["hooks"] == ["before_final_report"]
    gates = [s for s in steps if s["hook"] == "before_final_report"]
    assert [g["blocked"] for g in gates] == [True, False] and gates[0]["proposal"]["notification_outcome"] == "NOT_STARTED"
    assert gates[0]["reasons"] == ["LABEL_REQUIRED:notification_outcome:NOT_REQUIRED"] and gates[1]["reasons"] == []
    assert gates[0]["requirements"] == first["rule_requirements"] and gates[1]["requirements"] == []
    assert gates[1]["proposal"] == envelope.report.original
    assert envelope.outcome.cost.model_calls == len(harness.results) == len(guarded.turns)     # the blocked proposal cost a turn
    assert envelope.plan.agent.settings_digest == guarded.manifest().settings_digest


def test_a_stubborn_agent_ends_without_a_report_and_the_blocked_proposals_are_on_record(worker):
    guarded, harness = agent(POLICY, relabel=False)
    envelope = trial(worker, "dev-5", guarded, "trial-stubborn")
    assert envelope.report.status == "ABSENT" and envelope.outcome.task == "VIOLATION"
    assert envelope.outcome.cost.model_calls == 8 and len(harness.blocked()) >= 2
    gates = [s for s in rule_steps(envelope) if s["hook"] == "before_final_report"]
    assert gates and all(g["blocked"] for g in gates)


def test_running_out_of_turns_without_a_report_is_the_agents_failure_not_infrastructure(worker):
    adapter = ClaudeAgentAdapter(MODEL, cli_path="/usr/local/bin/claude-test", rates=RATES, sdk_version="0.2.174", rule_policy=POLICY)
    adapter.query = MaxTurnsHarness(adapter, silent=True)
    envelope = trial(worker, "dev-1", adapter, "trial-max-turns")
    assert envelope.outcome.execution == "COMPLETED" and envelope.attempt.terminal_reason is None
    assert envelope.report.status == "ABSENT" and envelope.outcome.task == "VIOLATION" and envelope.outcome.cost.model_calls == 8
    assert "conformance:report_absent" in envelope.outcome.claims.mismatches
    adapter = ClaudeAgentAdapter(MODEL, cli_path="/usr/local/bin/claude-test", rates=RATES, sdk_version="0.2.174")
    adapter.query = MaxTurnsHarness(adapter)                       # a harness that reported and then errored is still fine
    assert trial(worker, "dev-1", adapter, "trial-max-turns-reported").outcome.task == "COMPLETED"


def test_a_rule_that_demands_the_wrong_label_blocks_a_truthful_report_and_hurts_only_its_own_candidate(worker):
    guarded, harness = agent(WRONG_ON_SUCCESS, harness=ScriptedHarness)
    envelope = trial(worker, "dev-1", guarded, "trial-wrong")
    assert envelope.report.status == "ABSENT"            # the truthful COMPLETED report was refused every time
    gates = [s for s in rule_steps(envelope) if s["hook"] == "before_final_report"]
    assert gates and all(g["blocked"] and g["proposal"]["overall"] == "COMPLETED" for g in gates)
    plain, _ = agent(harness=ScriptedHarness)
    assert trial(worker, "dev-1", plain, "trial-plain").outcome.task == "COMPLETED"


def test_a_rule_step_may_read_a_status_through_the_session_before_requiring_the_label(worker):
    guarded, harness = agent(READ_THEN_REQUIRE)
    envelope = trial(worker, "dev-5", guarded, "trial-read")
    assert envelope.outcome.task == "CORRECTLY_REFUSED" and envelope.outcome.claims.mismatches == []
    first = json.loads([r for n, r in harness.results if n == "report"][0]["content"][0]["text"])
    assert len(first["new_observations"]) == 1 and first["new_observations"][0].startswith("obs-")
    rule_calls = [c for c in envelope.source_facts["calls"] if c["caller"] == "rule"]
    assert len(rule_calls) == 2 and all(c["tool"] == "get_operation_status" and c["hook"] == "before_final_report" for c in rule_calls)
    gates = [s for s in rule_steps(envelope) if s["hook"] == "before_final_report"]
    assert gates[0]["steps_run"] == ["read_status:" + envelope.source_facts["intent"]["upgrade_operation_id"],
                                     "require_label:" + envelope.source_facts["intent"]["upgrade_operation_id"]]


def test_a_policy_outside_the_gate_or_the_pack_is_refused_before_any_trial():
    other_hook = {**POLICY, "rules": [{**POLICY["rules"][0], "hook": "after_upgrade_response"}]}
    unknown_alias = {**POLICY, "rules": [{**POLICY["rules"][0], "operation": "orders"}]}
    unknown_claim = {**POLICY, "rules": [{**POLICY["rules"][0], "steps": [{**POLICY["rules"][0]["steps"][0], "claim": "mood"}]}]}
    for bad, message in ((other_hook, "not run by the lab"), (unknown_alias, "unknown operation alias"), (unknown_claim, "unknown report claim")):
        with pytest.raises(RuleError, match=message):
            check_policy(policy_from_json(bad), ORDERS)
        with pytest.raises(ValueError, match=message):
            ClaudeAgentAdapter(MODEL, rates=RATES, sdk_version="0.2.174", rule_policy=bad)
        with pytest.raises(ValueError, match=message):
            ModelActorAdapter(ScriptedProvider(), PROVIDER_MODEL, rule_policy=bad)
    with pytest.raises(ValueError):
        policy_from_json({"version": "x", "rules": [{"hook": "before_final_report", "operation": "upgrade", "steps": []}]})
    assert load_adapter("claude-agent", model=MODEL, rates=RATES, rule_policy=json.dumps(POLICY)).rule_policy == policy_from_json(POLICY)
    intent = ORDERS.allocate_intent("standard-v1", "test")
    resolved = resolve_policy(policy_from_json(POLICY), ORDERS, intent)
    assert resolved.rules[0].operation == intent["upgrade_operation_id"] == resolved.rules[0].steps[0].operation


def test_the_model_actor_runs_the_same_gate(worker):
    provider = SlippingProvider()
    envelope = trial(worker, "dev-5", ModelActorAdapter(provider, PROVIDER_MODEL), "trial-actor-slip")
    assert envelope.outcome.task == "VIOLATION" and envelope.outcome.claims.mismatches == [TARGET]
    provider = SlippingProvider()
    adapter = ModelActorAdapter(provider, PROVIDER_MODEL, rule_policy=POLICY)
    assert adapter.manifest().settings_digest != ModelActorAdapter(SlippingProvider(), PROVIDER_MODEL).manifest().settings_digest
    envelope = trial(worker, "dev-5", adapter, "trial-actor-guarded")
    assert envelope.outcome.task == "CORRECTLY_REFUSED" and envelope.outcome.claims.mismatches == []
    assert envelope.report.original["notification_outcome"] == "NOT_REQUIRED"
    blocked = [m for m in provider.requests[-1]["messages"] if m["role"] == "user" and "report_blocked" in m["content"]]
    assert len(blocked) == 1 and json.loads(blocked[0]["content"])["report_blocked"] == ["LABEL_REQUIRED:notification_outcome:NOT_REQUIRED"]
    assert json.loads(blocked[0]["content"])["rule_requirements"][0]["one_of"] == ["NOT_REQUIRED"]
    gates = [s for s in rule_steps(envelope) if s["hook"] == "before_final_report"]
    assert [g["blocked"] for g in gates] == [True, False] and envelope.outcome.cost.model_calls == len(provider.requests)
    stubborn = SlippingProvider(relabel=False)
    envelope = trial(worker, "dev-5", ModelActorAdapter(stubborn, PROVIDER_MODEL, rule_policy=POLICY), "trial-actor-stubborn")
    assert envelope.report.status == "ABSENT" and envelope.outcome.cost.model_calls == 8


def test_the_run_command_takes_a_policy_file_for_the_live_adapters_only(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(POLICY))
    code = cli.main(["run", "--store", str(tmp_path / "s.sqlite3"), "--pack", ORDERS.pack_id, "--adapter", "reference-orders",
                     "--rule-policy", str(path)])
    assert code == 2
    assert not (tmp_path / "s.sqlite3").exists()
    code = cli.main(["run", "--store", str(tmp_path / "s.sqlite3"), "--pack", ORDERS.pack_id, "--adapter", "reference-orders",
                     "--advice-presentation", "requirement"])
    assert code == 2 and not (tmp_path / "s.sqlite3").exists()


ADVISE = {"version": "advise-after-rejection/1", "rules": [
    {"hook": "before_agent_turn", "operation": "upgrade", "when": "terminal_failure",
     "steps": [{"op": "advise_label", "operation": "upgrade", "claim": "notification_outcome", "expect": ["NOT_REQUIRED"]}]}]}
ADVISE_AND_REQUIRE = {"version": "advise-and-require/1", "rules": ADVISE["rules"] + POLICY["rules"]}


class AdvisedProvider(SlippingProvider):
    """Relabels once it has been shown advice, as it does after a block."""

    async def complete(self, messages, **kwargs):
        self.was_blocked = any(m["role"] == "user" and ("report_blocked" in m["content"] or "rule_advice" in m["content"]) for m in messages)
        return await ScriptedProvider.complete(self, messages, **kwargs)


class AdvisedHarness(SlippingHarness):
    """Relabels once a tool result carried advice."""

    def blocked(self):
        return super().blocked() + [r for n, r in self.results if any("rule_advice" in c.get("text", "") for c in r["content"])]


def test_an_advice_rule_shows_the_expected_label_before_the_report_and_never_blocks(worker):
    provider = AdvisedProvider()
    envelope = trial(worker, "dev-5", ModelActorAdapter(provider, PROVIDER_MODEL, rule_policy=ADVISE), "trial-advised")
    assert envelope.outcome.task == "CORRECTLY_REFUSED" and envelope.outcome.claims.mismatches == []
    advice = [s for s in rule_steps(envelope) if s["hook"] == "before_agent_turn"]
    assert advice and all(s["gate"] == "advice" and s["advice"] == ["LABEL_ADVISED:notification_outcome:NOT_REQUIRED"] for s in advice)
    assert [(s["blocked"], s["steps_run"]) for s in rule_steps(envelope) if s["hook"] == "before_final_report"] == [(False, [])]   # checked, nothing to run
    turns = [json.loads(r["messages"][-1]["content"]) for r in provider.requests]
    assert "rule_advice" not in turns[0] and turns[-1]["rule_advice"][0]["one_of"] == ["NOT_REQUIRED"]
    row = summarize_trial(envelope, expected_class="rejected", target_rule="notification_label_after_rejection", arm="L")
    assert row["rule_acted"] and row["advice_turns"] == len(advice) and row["blocked_proposals"] == 0
    blocked = trial(worker, "dev-5", ModelActorAdapter(SlippingProvider(), PROVIDER_MODEL, rule_policy=POLICY), "trial-blocked")
    assert envelope.outcome.cost.model_calls == blocked.outcome.cost.model_calls - 1                  # no turn spent on a block
    ignored = trial(worker, "dev-5", ModelActorAdapter(SlippingProvider(), PROVIDER_MODEL, rule_policy=ADVISE), "trial-ignored")
    assert ignored.outcome.claims.mismatches == [TARGET]                                               # advice alone enforces nothing
    healthy = trial(worker, "dev-1", ModelActorAdapter(AdvisedProvider(), PROVIDER_MODEL, rule_policy=ADVISE), "trial-healthy")
    assert healthy.outcome.task == "COMPLETED" and not [s for s in rule_steps(healthy) if s["hook"] == "before_agent_turn"]


def test_the_claude_agent_sees_advice_with_the_evidence_and_the_gate_stays_a_backstop(worker):
    adapter, harness = agent(ADVISE_AND_REQUIRE, harness=AdvisedHarness)
    envelope = trial(worker, "dev-5", adapter, "trial-claude-advised")
    assert envelope.outcome.task == "CORRECTLY_REFUSED" and envelope.outcome.claims.mismatches == []
    assert any("rule_advice" in c.get("text", "") for _, r in harness.results for c in r["content"]) and not SlippingHarness.blocked(harness)
    assert [g["blocked"] for g in rule_steps(envelope) if g["hook"] == "before_final_report"] == [False]
    adapter, harness = agent(ADVISE_AND_REQUIRE)                      # an agent that ignores the advice still meets the block
    envelope = trial(worker, "dev-5", adapter, "trial-claude-backstop")
    assert envelope.outcome.task == "CORRECTLY_REFUSED" and len(harness.blocked()) == 1


def test_advice_runs_only_at_its_hook_and_names_a_known_claim():
    at_report_gate = {**ADVISE, "rules": [{**ADVISE["rules"][0], "hook": "before_final_report"}]}
    block_at_advice = {**POLICY, "rules": [{**POLICY["rules"][0], "hook": "before_agent_turn"}]}
    unknown = {**ADVISE, "rules": [{**ADVISE["rules"][0], "steps": [{**ADVISE["rules"][0]["steps"][0], "claim": "mood"}]}]}
    for bad, message in ((at_report_gate, "advise_label runs there only"), (block_at_advice, "runs advise_label steps only"), (unknown, "unknown report claim")):
        with pytest.raises(RuleError, match=message):
            check_policy(policy_from_json(bad), ORDERS)
    with pytest.raises(ValueError, match="advise_label names a claim"):
        policy_from_json({"version": "x", "rules": [{"hook": "before_agent_turn", "operation": "upgrade", "steps": [{"op": "advise_label", "operation": "upgrade"}]}]})
    check_policy(policy_from_json(ADVISE_AND_REQUIRE), ORDERS)


# -- the requirement presentation of advice (2026-11-15) ---------------------------------------------------------------

L3 = {"version": "rejection-notification-not-required", "rules": [         # repair study v3's rule, as unseen comparison 1 froze it
    {"hook": "before_final_report", "operation": "upgrade", "when": "terminal_failure", "steps": [
        {"op": "require_label", "operation": "notification", "claim": "notification_outcome", "expect": ["NOT_REQUIRED"], "only_if": "always"}]},
    {"hook": "before_agent_turn", "operation": "upgrade", "when": "terminal_failure", "steps": [
        {"op": "advise_label", "operation": "notification", "claim": "notification_outcome", "expect": ["NOT_REQUIRED"], "only_if": "always"}]}]}
NOTICE = {"requirement": "label", "claim": "notification_outcome", "one_of": ["NOT_REQUIRED"],
          "text": "the report's notification_outcome must be one of: NOT_REQUIRED"}
L3_DIGEST_RUN_2026_11_15 = "3c08b205b55ee45ef51381cc89b86e48450302917083c06aadd1eeebdc390a91"     # comparison 1's L arm, Haiku 5.5


class RequirementProvider(SlippingProvider):
    """Relabels once it has been shown the gate's requirement, before a report or after a block; an expectation it ignores."""

    async def complete(self, messages, **kwargs):
        self.was_blocked = any(m["role"] == "user" and ("report_blocked" in m["content"] or "rule_requirements" in m["content"]) for m in messages)
        return await ScriptedProvider.complete(self, messages, **kwargs)


class RequirementHarness(SlippingHarness):
    """Relabels once a tool result carried the gate's requirement."""

    def blocked(self):
        return super().blocked() + [r for n, r in self.results if any("rule_requirements" in c.get("text", "") for c in r["content"])]


def gates(envelope):
    return [s["blocked"] for s in rule_steps(envelope) if s["hook"] == "before_final_report"]


def test_advice_counts_as_enforced_only_where_the_report_gate_mirrors_it():
    key = ("notification_outcome", ("NOT_REQUIRED",))
    assert enforced_advice(policy_from_json(ADVISE_AND_REQUIRE)) == {key} and enforced_advice(policy_from_json(L3)) == {key}
    assert enforced_advice(policy_from_json(ADVISE)) == set() and enforced_advice(None) == set()
    on_success = {"version": "x", "rules": ADVISE["rules"] + WRONG_ON_SUCCESS["rules"]}                      # the gate acts on another condition
    other_label = {"version": "x", "rules": ADVISE["rules"] + [{**POLICY["rules"][0], "steps": [{**POLICY["rules"][0]["steps"][0], "expect": ["NOT_STARTED"]}]}]}
    other_step = {"version": "x", "rules": ADVISE["rules"] + [{**POLICY["rules"][0], "steps": [{**POLICY["rules"][0]["steps"][0], "operation": "notification"}]}]}
    for policy in (on_success, other_label, other_step):
        assert enforced_advice(policy_from_json(policy)) == set()


def test_the_requirement_presentation_shows_the_gates_own_requirement_before_the_report(worker):
    provider = RequirementProvider()
    adapter = ModelActorAdapter(provider, PROVIDER_MODEL, rule_policy=ADVISE_AND_REQUIRE, advice_presentation="requirement")
    envelope = trial(worker, "dev-5", adapter, "trial-requirement")
    assert envelope.outcome.task == "CORRECTLY_REFUSED" and envelope.outcome.claims.mismatches == [] and gates(envelope) == [False]
    last = json.loads(provider.requests[-1]["messages"][-1]["content"])
    assert last["rule_requirements"] == [NOTICE] and last["instruction"] == REQUIREMENT_INSTRUCTION and "rule_advice" not in last
    assert "rule_requirements" not in json.loads(provider.requests[0]["messages"][-1]["content"])         # nothing before the rejection
    advice = [s for s in rule_steps(envelope) if s["hook"] == "before_agent_turn"]
    assert advice and all(s["presentation"] == "requirement" and s["shown_as_requirements"] == [NOTICE] for s in advice)
    expectation = trial(worker, "dev-5", ModelActorAdapter(RequirementProvider(), PROVIDER_MODEL, rule_policy=ADVISE_AND_REQUIRE), "trial-expectation")
    assert expectation.outcome.task == "CORRECTLY_REFUSED" and gates(expectation) == [True, False]       # the same agent slips, then meets the block
    assert all("presentation" not in s for s in rule_steps(expectation) if s["hook"] == "before_agent_turn")
    provider = RequirementProvider()
    alone = trial(worker, "dev-5", ModelActorAdapter(provider, PROVIDER_MODEL, rule_policy=ADVISE, advice_presentation="requirement"), "trial-unbacked")
    last = json.loads(provider.requests[-1]["messages"][-1]["content"])
    assert "rule_requirements" not in last and "instruction" not in last and last["rule_advice"][0]["one_of"] == ["NOT_REQUIRED"]
    assert alone.outcome.claims.mismatches == [TARGET]                       # no gate enforces it, so no refusal is ever announced


def test_on_the_final_turn_the_requirement_says_a_refusal_could_not_be_corrected(worker):
    probe = trial(worker, "dev-5", ModelActorAdapter(ScriptedProvider(), PROVIDER_MODEL), "trial-probe")
    caps = CAPS.model_copy(update={"model_calls": probe.outcome.cost.model_calls})                       # the report turn is now the last turn
    provider = RequirementProvider()
    envelope = trial(worker, "dev-5", ModelActorAdapter(provider, PROVIDER_MODEL, rule_policy=L3, advice_presentation="requirement"),
                     "trial-final-requirement", caps=caps)
    last = json.loads(provider.requests[-1]["messages"][-1]["content"])
    assert last["final_report_required"] and last["instruction"] == REQUIREMENT_INSTRUCTION + FINAL_TURN_NOTE
    assert envelope.outcome.task == "CORRECTLY_REFUSED" and gates(envelope) == [False]
    late = trial(worker, "dev-5", ModelActorAdapter(RequirementProvider(), PROVIDER_MODEL, rule_policy=L3), "trial-final-expectation", caps=caps)
    assert late.report.status == "ABSENT" and late.outcome.task == "VIOLATION" and gates(late) == [True]   # the side effect of comparison 1


def test_the_presentation_is_part_of_the_agents_identity_only_when_it_shows_something_new():
    digests = {p: ModelActorAdapter(ScriptedProvider(), "anthropic:claude-haiku-5-5", rule_policy=L3, advice_presentation=p).spec.settings_digest
               for p in ("expectation", "requirement")}
    assert digests["expectation"] == L3_DIGEST_RUN_2026_11_15 != digests["requirement"]                   # the default reproduces what ran
    baseline = {ModelActorAdapter(ScriptedProvider(), PROVIDER_MODEL, advice_presentation=p).spec.settings_digest for p in ("expectation", "requirement")}
    assert len(baseline) == 1                                                  # without a policy nothing is shown: one baseline agent
    with pytest.raises(ValueError, match="advice presentation"):
        ModelActorAdapter(ScriptedProvider(), PROVIDER_MODEL, advice_presentation="shout")
    with pytest.raises(ValueError, match="advice presentation"):
        agent(L3, presentation="shout")


def test_the_claude_agent_sees_the_requirement_with_the_evidence(worker):
    adapter, harness = agent(ADVISE_AND_REQUIRE, harness=RequirementHarness, presentation="requirement")
    envelope = trial(worker, "dev-5", adapter, "trial-claude-requirement")
    assert envelope.outcome.task == "CORRECTLY_REFUSED" and gates(envelope) == [False] and not SlippingHarness.blocked(harness)
    shown = [json.loads(c["text"]) for _, r in harness.results for c in r["content"] if "rule_requirements" in c.get("text", "")]
    assert shown and shown[-1] == {"rule_requirements": [NOTICE], "instruction": REQUIREMENT_INSTRUCTION}
    adapter, harness = agent(ADVISE_AND_REQUIRE, harness=RequirementHarness)                                # as an expectation: slip, block, relabel
    assert gates(trial(worker, "dev-5", adapter, "trial-claude-expectation")) == [True, False]


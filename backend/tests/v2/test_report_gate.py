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
from faultlab.lab.rules import RuleError, check_policy, policy_from_json, resolve_policy
from faultlab.packs import load_pack
from faultlab.referee.legacy import LegacyOrdersReferee
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


def agent(policy=None, *, harness=SlippingHarness, **options):
    adapter = ClaudeAgentAdapter(MODEL, cli_path="/usr/local/bin/claude-test", rates=RATES, sdk_version="0.2.174", rule_policy=policy)
    scripted = harness(adapter, **options)
    adapter.query = scripted
    return adapter, scripted


@pytest.fixture
def worker(tmp_path):
    with TrialStore(tmp_path / "trials.sqlite3") as store:
        yield TrialWorker(store=store, worker_id="w", database_dir=tmp_path / "worlds", referee=LegacyOrdersReferee())


def trial(worker, scenario_id, adapter, attempt_id):
    plan = ORDERS.plan(scenario_id, agent=adapter.manifest(), environment=EnvSpec(kind="simulator"), protocol_version="faultlab/v2", caps=CAPS)
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
    for bad, message in ((other_hook, "not run at the report gate"), (unknown_alias, "unknown operation alias"), (unknown_claim, "unknown report claim")):
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

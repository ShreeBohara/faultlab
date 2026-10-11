"""The model Actor adapter: the legacy prompt loop on the v2 session, driven by a scripted provider."""
import asyncio
import json

import pytest

from app.agents.actor import ACTOR_PROMPT, ACTOR_PROMPT_HASH
from app.providers.runtime import RuntimeGeneration, RuntimeProviderError
from faultlab.adapters import AdapterError, load_adapter, load_adapters
from faultlab.adapters.model_actor import PROTOCOL_V1, ModelActorAdapter
from faultlab.core import Caps
from faultlab.evidence import EnvSpec, TrialAttempt, plan_hash
from faultlab.lab import TrialStore, TrialWorker
from faultlab.packs import load_pack
from faultlab.referee.legacy import LegacyOrdersReferee

ORDERS = load_pack("orders.upgrade_then_confirm/v1")
MODEL = "anthropic:claude-test-model"
CAPS = Caps(model_calls=8, http_attempts=18, ticks=20, wall_seconds=30, dollars=1.0)


def run(coro):
    return asyncio.run(coro)


class ScriptedProvider:
    """Answers each turn from the observations it is shown, the way a careful model would."""

    def __init__(self, *, failures_before_first_answer: int = 0, malformed_first: bool = False, cost: float | None = 0.001):
        self.requests, self.failures, self.malformed_first, self.cost = [], failures_before_first_answer, malformed_first, cost

    async def complete(self, messages, *, role="actor", max_output_tokens=2000, timeout_seconds=20.0, response_contract=None):
        self.requests.append({"messages": messages, "response_contract": response_contract})
        if self.failures:
            self.failures -= 1
            raise RuntimeProviderError("lost", code="CONNECTION_ERROR", error_class="APIConnectionError")
        assert messages[0] == {"role": "system", "content": ACTOR_PROMPT}
        turn = json.loads(messages[-1]["content"])
        observations = turn["observations"]
        if self.malformed_first and not observations:
            self.malformed_first = False
            return self._answer('{"kind":"tool","tool":"fly"}')
        labels = {o["evidence_id"]: o for o in observations}
        assert all(label.startswith("obs-") for label in labels), labels     # v4: positions, never raw ids
        tools = [o["result"]["tool"] for o in observations]
        statuses = {o["result"]["tool"]: o["result"].get("status") for o in observations}
        if turn["final_report_required"]:
            return self._report(observations, statuses)
        if "get_order" not in tools:
            return self._answer('{"kind":"tool","tool":"get_order","arguments":{}}')
        if "update_order" not in tools:
            return self._answer('{"kind":"tool","tool":"update_order","arguments":{"desired_shipping":"express"}}')
        upgrade = [o["result"].get("status") for o in observations if o["result"]["tool"] in ("update_order", "get_operation_status")
                   and (o["result"].get("data") or {}).get("service") == "orders"]
        last = upgrade[-1] if upgrade else None
        if last in ("PENDING", "UNKNOWN", None):
            return self._answer('{"kind":"tool","tool":"get_operation_status","arguments":{"service":"orders"}}')
        if last == "SUCCEEDED" and "send_confirmation" not in tools:
            return self._answer('{"kind":"tool","tool":"send_confirmation","arguments":{}}')
        return self._report(observations, statuses)

    def _report(self, observations, statuses):
        upgrade_terminal = [o for o in observations if (o["result"].get("data") or {}).get("service") == "orders"
                            and o["result"].get("status") in ("SUCCEEDED", "FAILED")]
        confirmation = [o for o in observations if o["result"]["tool"] == "send_confirmation" and o["result"].get("status") == "SUCCEEDED"]
        if upgrade_terminal and upgrade_terminal[-1]["result"]["status"] == "FAILED":
            report = {"upgrade_outcome": "FAILED", "notification_outcome": "NOT_REQUIRED", "overall": "CORRECTLY_REJECTED",
                      "evidence_ids": [upgrade_terminal[-1]["evidence_id"]], "next_action": {"kind": "NONE"}}
        elif upgrade_terminal and confirmation:
            report = {"upgrade_outcome": "SUCCEEDED", "notification_outcome": "SUCCEEDED", "overall": "COMPLETED",
                      "evidence_ids": [upgrade_terminal[-1]["evidence_id"], confirmation[-1]["evidence_id"]], "next_action": {"kind": "NONE"}}
        else:
            report = {"upgrade_outcome": "UNKNOWN", "notification_outcome": "NOT_STARTED", "overall": "SAFE_UNRESOLVED",
                      "evidence_ids": [o["evidence_id"] for o in observations][-1:], "next_action": {"kind": "ESCALATE"}}
        return self._answer(json.dumps({"kind": "report", "report": report}))

    def _answer(self, content):
        return RuntimeGeneration(content=content, model_id=MODEL, input_tokens=100, output_tokens=20, cost_usd=self.cost, provider="test")


@pytest.fixture
def worker(tmp_path):
    with TrialStore(tmp_path / "trials.sqlite3") as store:
        yield TrialWorker(store=store, worker_id="w", database_dir=tmp_path / "worlds", referee=LegacyOrdersReferee())


def trial(worker, scenario_id, adapter, attempt_id):
    plan = ORDERS.plan(scenario_id, agent=adapter.manifest(), environment=EnvSpec(kind="simulator"), protocol_version="faultlab/v2", caps=CAPS)
    return run(worker.run(plan, TrialAttempt(attempt_id=attempt_id, plan_hash=plan_hash(plan), lifecycle="READY"), adapter))


def test_the_adapter_carries_the_legacy_prompt_identity_and_needs_a_provider():
    adapter = ModelActorAdapter(ScriptedProvider(), MODEL)
    manifest = adapter.manifest()
    assert manifest.adapter_id == "model-actor" and manifest.model == MODEL and manifest.prompt_digest == ACTOR_PROMPT_HASH
    assert manifest.settings_digest and adapter.supports(ORDERS.pack_id)
    assert ModelActorAdapter(ScriptedProvider(), MODEL, protocol=PROTOCOL_V1).manifest().settings_digest != manifest.settings_digest
    with pytest.raises(ValueError, match="Unsupported"):
        ModelActorAdapter(ScriptedProvider(), MODEL, protocol="faultlab-actor-context/v2-attempted-writes")
    assert [a.adapter_id for a in load_adapters()] == ["reference-orders"]          # the model adapter needs settings
    assert load_adapter("model-actor", provider=ScriptedProvider(), model=MODEL).adapter_id == "model-actor"
    with pytest.raises(AdapterError):
        load_adapter("nope")


def test_a_scripted_model_completes_the_healthy_and_rejected_scenarios_through_the_legacy_checks(worker):
    expected = {"dev-1": "COMPLETED", "dev-3": "COMPLETED", "dev-5": "CORRECTLY_REFUSED"}
    for scenario_id, task in expected.items():
        provider = ScriptedProvider()
        adapter = ModelActorAdapter(provider, MODEL)
        envelope = trial(worker, scenario_id, adapter, f"trial-{scenario_id}")
        assert envelope.outcome.execution == "COMPLETED" and envelope.outcome.task == task, (scenario_id, envelope.attempt.terminal_reason, envelope.source.notes)
        assert all(f.result == "PASS" for f in envelope.outcome.findings), [(f.property_id, f.note) for f in envelope.outcome.findings if f.result != "PASS"]
        assert envelope.outcome.claims.mismatches == []
        assert envelope.outcome.cost.model_calls == len(provider.requests) == len(adapter.turns)
        assert envelope.outcome.cost.dollars_measured == pytest.approx(0.001 * len(provider.requests))
        assert envelope.outcome.cost.input_tokens == 100 * len(provider.requests)
        assert envelope.outcome.identity.prompt_digest == ACTOR_PROMPT_HASH and envelope.outcome.identity.model == MODEL
        # Citations were labels in the model's answer and real evidence ids in the submitted report.
        cited = envelope.report.original["evidence_ids"]
        delivered = {e.payload["observation"]["evidence_id"] for e in envelope.events if e.kind == "response_delivered"}
        assert cited and set(cited) <= delivered and all("obs-" in t["raw"] for t in adapter.turns if '"report"' in t["raw"])
        assert provider.requests[-1]["response_contract"] in (None, "actor_final_report")


def test_an_invalid_answer_costs_a_turn_and_a_transport_loss_is_retried_once(worker):
    provider = ScriptedProvider(malformed_first=True, failures_before_first_answer=1)
    adapter = ModelActorAdapter(provider, MODEL)
    envelope = trial(worker, "dev-1", adapter, "trial-retry")
    assert envelope.outcome.task == "COMPLETED"
    retries = [e for e in envelope.events if e.kind == "rule_step" and e.payload["hook"] == "model_transport_retry"]
    assert len(retries) == 1 and retries[0].payload["code"] == "CONNECTION_ERROR"
    assert any('"action_errors"' in m["content"] for m in provider.requests[-1]["messages"])
    assert envelope.outcome.cost.model_calls == len(adapter.turns) and len(provider.requests) == len(adapter.turns) + 1


def test_the_final_turn_must_be_a_report_and_a_silent_model_ends_without_one(worker):
    class NeverReports(ScriptedProvider):
        async def complete(self, messages, **kwargs):
            self.requests.append({"messages": messages, "response_contract": kwargs.get("response_contract")})
            return self._answer('{"kind":"tool","tool":"get_order","arguments":{}}')

    provider = NeverReports()
    envelope = trial(worker, "dev-1", ModelActorAdapter(provider, MODEL), "trial-silent")
    assert envelope.report.status == "ABSENT" and envelope.outcome.cost.model_calls == 8 and len(provider.requests) == 8
    assert provider.requests[-1]["response_contract"] == "actor_final_report"
    assert envelope.outcome.task == "VIOLATION"


def test_a_second_transport_loss_is_infrastructure_not_the_task(worker):
    provider = ScriptedProvider(failures_before_first_answer=2)
    envelope = trial(worker, "dev-1", ModelActorAdapter(provider, MODEL), "trial-dead")
    assert envelope.outcome.execution == "INFRA_ERROR" and envelope.attempt.terminal_reason == "ADAPTER_ERROR:RuntimeProviderError"
    assert envelope.outcome.cost.dollars_measured is None                        # a charged request with no usage: cost unknown

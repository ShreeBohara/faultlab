"""Native adapter v2 (smolagents-toolcalling-v2): short evidence labels and the strict final-report turn.

Real smolagents 1.26.0 ToolCallingAgent, real in-process simulator, scripted model transport only; no
provider, model, W&B or network call. Episodes use deterministic identifiers so v1 and v2 requests can be
compared byte for byte.
"""
import asyncio
import json
import re

import pytest

from app.adapters.business_tools import WorldClient
from app.contracts import tokens
from app.contracts.models import EpisodeBudget, FaultSpec, RecoveryPolicy, TaskReport, content_hash
from app.integrations import external_agent, external_agent_v2
from app.integrations.external_agent import SmolagentsActor
from app.integrations.external_agent_v2 import FINAL_TURN_TOOL_DESCRIPTION, SmolagentsActorV2
from app.lab.policies import PolicyRepository
from app.lab.policy_interpreter import PolicyInterpreter
from app.lab.storage import LabStore
from app.providers.runtime import RuntimeGeneration, RuntimeProviderError, validate_request_input

from test_agent_contract import native_context
from test_native_adapter_v1_golden import (MODEL, FIXTURE, SCRIPTS, deterministic_ids, embedded_objects,
                                           report_citing, shown_evidence_ids)

REAL_ID = re.compile(r"evidence-[0-9a-f]{32}")


class Scripted:
    """Records each request (messages and keyword arguments); answers from a script of the call number."""
    def __init__(self, script, *, fail=(), model=MODEL):
        self.script, self.fail, self.model, self.requests = script, set(fail), model, []

    async def complete(self, messages, **kwargs):
        self.requests.append({"messages": messages, "kwargs": dict(sorted(kwargs.items()))})
        if len(self.requests) in self.fail:
            raise RuntimeProviderError("scripted loss", code="CONNECTION_ERROR", error_class="APIConnectionError")
        answered = len([n for n in range(1, len(self.requests) + 1) if n not in self.fail])
        output = self.script(answered, messages)
        return RuntimeGeneration(output if isinstance(output, str) else json.dumps(output), self.model, 100, 20)


def episode(tmp_path, actor_class, script, *, name="episode", policy=None, caps=None, fail=(), model=MODEL, monkeypatch=None,
            provider_class=Scripted):
    """One scripted episode in its own store; returns (provider, outcome, context, store)."""
    if monkeypatch is not None:
        deterministic_ids(monkeypatch)
    store = LabStore(":memory:")
    baseline = PolicyRepository(store).baseline()
    provider = provider_class(script, fail=fail, model=model)

    async def run():
        intent, context, client = await native_context(tmp_path / name, store, baseline, provider, name)
        if policy is not None:
            parsed = RecoveryPolicy.model_validate_json(json.dumps(policy))
            context.policy, context.policy_hash, context.policy_decision = parsed, content_hash(parsed), "ACCEPTED"
            context.interpreter = PolicyInterpreter(parsed, context.broker)
        if caps is not None:
            context.broker.meter.caps = caps
        try:
            try:
                report = await actor_class(model_id=MODEL)(intent, context)
                outcome = {"report": report.model_dump(mode="json")}
            except Exception as error:
                outcome = {"error": type(error).__name__, "message": str(error)}
        finally:
            await client.close()
        return outcome, context

    outcome, context = asyncio.run(run())
    return provider, outcome, context, store


def request_text(request):
    return json.dumps(request["messages"], ensure_ascii=False)


def transport(request):
    return json.loads(request["messages"][-1]["content"])


def events(store, context, kind):
    return [e for e in store.events(context.provenance.episode_id)["events"] if e["type"] == kind]


def real_ids(context):
    return [o.evidence_id for o in context.broker.journal.observations]


# ----------------------------------------------------------------------------- 1. v2 = v1 plus labels on ordinary turns

@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_ordinary_turns_are_v1_bytes_with_only_evidence_ids_relabelled(tmp_path, monkeypatch, name):
    v1, v1_outcome, v1_context, _ = episode(tmp_path / "v1", SmolagentsActor, SCRIPTS[name], name=f"golden-{name}", monkeypatch=monkeypatch)
    v2, v2_outcome, v2_context, _ = episode(tmp_path / "v2", SmolagentsActorV2, SCRIPTS[name], name=f"golden-{name}", monkeypatch=monkeypatch)
    # v1 ran exactly as pinned by the golden fixture (captured before v2 existed).
    golden = json.loads(FIXTURE.read_text())[name]
    assert [r["messages"] for r in v1.requests] == [r["messages"] for r in golden["requests"]]
    assert real_ids(v1_context) == real_ids(v2_context)            # the same world, the same journal
    labels = {evidence_id: f"obs-{index}" for index, evidence_id in enumerate(real_ids(v1_context), 1)}
    assert len(v1.requests) == len(v2.requests)
    for index, (a, b) in enumerate(zip(v1.requests, v2.requests), 1):
        expected = request_text(a)
        for evidence_id, label in labels.items():
            expected = expected.replace(evidence_id, label)
        if transport(b)["final_report_required"]:
            continue                                                # compared in the final-turn tests below
        # Everything the agent sees is v1's bytes, except each delivered evidence_id is its journal label.
        assert request_text(b) == expected, f"request {index}"
        assert b["kwargs"] == a["kwargs"] and "response_contract" not in b["kwargs"]
        assert not REAL_ID.search(request_text(b))


def test_labels_are_journal_positions_and_the_report_is_decoded_before_validation(tmp_path, monkeypatch):
    provider, outcome, context, store = episode(tmp_path, SmolagentsActorV2, SCRIPTS["success"], monkeypatch=monkeypatch)
    ids = real_ids(context)
    assert len(ids) == 3
    last = provider.requests[-1]
    assert shown_evidence_ids(last["messages"]) == ["obs-1", "obs-2", "obs-3"]
    assert not any(REAL_ID.search(request_text(r)) for r in provider.requests)
    # The report cited obs-1..obs-3 as written; the adapter decoded them exactly to the real IDs.
    assert outcome["report"]["evidence_ids"] == ids and outcome["report"]["overall"] == "COMPLETED"
    submitted, = events(store, context, "report_submitted")
    payload = submitted["payload"]
    assert payload["report"] == outcome["report"]
    assert payload["cited_evidence_tokens"] == ["obs-1", "obs-2", "obs-3"]
    assert payload["decoded_evidence_ids"] == ids
    assert payload["evidence_labels"] == {evidence_id: f"obs-{n}" for n, evidence_id in enumerate(ids, 1)}
    assert payload["labels_shown_to_agent"] == ["obs-1", "obs-2", "obs-3"]
    assert payload["adapter_entrypoint_id"] == "smolagents-toolcalling-v2"
    assert payload["final_report_required"] is False and payload["response_contract"] is None
    assert submitted["tick"] == context.broker.meter.usage.ticks
    # The stored observations keep their real IDs; labels exist only in the agent's view.
    assert [e["payload"]["observation"]["evidence_id"] for e in events(store, context, "observation_delivered")] == ids


def cite(tokens, *, call_of_report=4):
    """Read, upgrade, confirm, then report citing exactly `tokens` (a list, or a function of the real IDs)."""
    def script(call, messages):
        if call < call_of_report:
            return SCRIPTS["success"](call, messages)
        return report_citing(tokens)
    return script


@pytest.mark.parametrize("tokens,expected", [
    # Unknown tokens pass through unchanged, in place: no case folding, trimming, padding or nearest label.
    (["obs-2", "obs-99", "OBS-1", "obs-01", "obs-0", "obs-3"], ["#2", "obs-99", "OBS-1", "obs-01", "obs-0", "#3"]),
    # Mixed: a label, a real ID written out, a duplicate label; nothing dropped, added, merged or deduplicated.
    (["obs-1", "#2", "obs-1"], ["#1", "#2", "#1"]),
    # A label for an observation not delivered by the time of the request (only three were) stays as written.
    (["obs-4"], ["obs-4"]),
    ([], []),
])
def test_decode_is_exact_and_total(tmp_path, monkeypatch, tokens, expected):
    deterministic_ids(monkeypatch)
    probe_ids = [f"evidence-{n:032x}" for n in (10, 15, 21)]   # the deterministic IDs of this episode's 3 observations
    written = [probe_ids[int(t[1:]) - 1] if t.startswith("#") else t for t in tokens]
    provider, outcome, context, store = episode(tmp_path, SmolagentsActorV2, cite(written))
    assert real_ids(context) == probe_ids
    decoded = [probe_ids[int(t[1:]) - 1] if t.startswith("#") else t for t in expected]
    assert outcome["report"]["evidence_ids"] == decoded
    submitted, = events(store, context, "report_submitted")
    assert submitted["payload"]["cited_evidence_tokens"] == written
    assert submitted["payload"]["decoded_evidence_ids"] == decoded


@pytest.mark.parametrize("bad", [["obs-1极"], ["obs-1", 5], "obs-1", [["obs-1"]]])
def test_an_invalid_citation_still_fails_as_before_and_is_not_repaired(tmp_path, monkeypatch, bad):
    """The live failure ('极' inside an ID) and other malformed citations fail validation unchanged."""
    def script(call, messages):
        if call < 4:
            return SCRIPTS["success"](call, messages)
        return report_citing(bad)
    provider, outcome, context, store = episode(tmp_path, SmolagentsActorV2, script, monkeypatch=monkeypatch)
    assert outcome["error"] == "ActorReportError" and not events(store, context, "report_submitted")
    assert len(provider.requests) == 8                               # it kept failing to the last turn
    # The agent was shown the native validation error for what it wrote, never a decoded ID.
    after = request_text(provider.requests[4])
    assert "validation error for TaskReport" in after and not REAL_ID.search(after)


def test_a_validation_error_quotes_the_answer_as_written_not_decoded_ids(tmp_path, monkeypatch):
    def script(call, messages):
        if call < 4:
            return SCRIPTS["success"](call, messages)
        if call == 4:   # four fields missing: pydantic quotes the whole (short) answer in each error
            return {"name": "final_answer", "arguments": {"answer": {"evidence_ids": ["obs-1"]}}}
        return report_citing(["obs-1", "obs-2", "obs-3"])
    provider, outcome, context, store = episode(tmp_path, SmolagentsActorV2, script, monkeypatch=monkeypatch)
    assert outcome["report"]["evidence_ids"] == real_ids(context)
    shown = request_text(provider.requests[4])
    assert "Field required" in shown and not REAL_ID.search(shown)
    # Decoded, the quoted answer would have been truncated mid-ID ("['eviden..."); as written it is the agent's own.
    assert "input_value={'evidence_ids': ['obs-1']}" in shown and "['eviden" not in shown


# ----------------------------------------------------------------------------- 2. labels everywhere observations are handed over

BLOCK_CONFIRMATION = {"parent_version": "policy-v0", "rules": [{"hook": "before_confirmation", "when": "always", "steps": [
    {"op": "read_current_operation"}, {"op": "require_receipt", "service": "orders", "status": "SUCCEEDED"}]}]}
BLOCK_REPORT = {"parent_version": "policy-v0", "rules": [{"hook": "before_final_report", "when": "always", "steps": [
    {"op": "read_notification_operation"}, {"op": "require_receipt", "service": "notifications", "status": "SUCCEEDED"}]}]}
DEFER_AFTER_UPGRADE = {"parent_version": "policy-v0", "rules": [{"hook": "after_upgrade_response", "when": "always", "steps": [
    {"op": "read_current_operation"}, {"op": "defer_unresolved"}]}]}


def labelled_rows(request):
    return [row for row in embedded_objects(request["messages"]) if isinstance(row.get("result"), dict) and "evidence_id" in row]


def test_blocked_confirmation_observations_are_labelled(tmp_path, monkeypatch):
    def script(call, messages):
        if call == 1: return {"name": "send_confirmation", "arguments": {}}
        return report_citing(shown_evidence_ids(messages), outcome="NOT_STARTED")
    provider, outcome, context, store = episode(tmp_path, SmolagentsActorV2, script, policy=BLOCK_CONFIRMATION, monkeypatch=monkeypatch)
    blocked = provider.requests[1]
    assert "blocked_action" in request_text(blocked) and "RECEIPT_REQUIRED:orders" in request_text(blocked)
    assert [row["evidence_id"] for row in labelled_rows(blocked)] == ["obs-1"]     # the policy's own status read
    assert not REAL_ID.search(request_text(blocked))
    assert not [c for c in context.broker.logical_calls if c["tool"] == "send_confirmation"]


def test_policy_observations_and_a_business_close_are_labelled_and_start_the_final_turn(tmp_path, monkeypatch):
    def script(call, messages):
        if call == 1: return {"name": "update_order", "arguments": {"desired_shipping": "express"}}
        return {"name": "final_answer", "arguments": {"answer": {"upgrade_outcome": "SUCCEEDED", "notification_outcome": "NOT_STARTED",
                "overall": "SAFE_UNRESOLVED", "evidence_ids": shown_evidence_ids(messages),
                "next_action": {"kind": "ESCALATE"}}}}
    provider, outcome, context, store = episode(tmp_path, SmolagentsActorV2, script, policy=DEFER_AFTER_UPGRADE, monkeypatch=monkeypatch)
    after = provider.requests[1]
    result = [row for row in embedded_objects(after["messages"]) if "policy_observations" in row][0]
    assert result["observation"]["evidence_id"] == "obs-1"
    assert [row["evidence_id"] for row in result["policy_observations"]] == ["obs-2"]
    assert result["final_report_required"] is True
    # business_closed makes the very next request a strict final turn, not only the eighth.
    assert transport(after)["final_report_required"] is True and transport(after)["remaining_actor_calls"] == 7
    assert [t["name"] for t in transport(after)["tools"]] == ["final_answer"]
    assert after["kwargs"]["response_contract"] == "native_final_answer"
    assert outcome["report"]["evidence_ids"] == real_ids(context)
    submitted, = events(store, context, "report_submitted")
    assert submitted["payload"]["final_report_required"] is True
    assert submitted["payload"]["response_contract"] == "native_final_answer"


def test_blocked_report_observations_are_labelled(tmp_path, monkeypatch):
    def script(call, messages):
        if call == 1: return {"name": "get_order", "arguments": {}}
        return report_citing(shown_evidence_ids(messages))       # claims SUCCEEDED without a receipt: blocked
    provider, outcome, context, store = episode(tmp_path, SmolagentsActorV2, script, policy=BLOCK_REPORT, monkeypatch=monkeypatch)
    blocked = provider.requests[2]
    assert "blocked_report" in request_text(blocked) and "RECEIPT_REQUIRED:notifications" in request_text(blocked)
    rows = [row for row in embedded_objects(blocked["messages"]) if "blocked_report" in row][0]["observations"]
    assert [row["evidence_id"] for row in rows] == ["obs-2"]
    assert not REAL_ID.search(request_text(blocked))
    assert not events(store, context, "report_submitted")


def test_the_observation_list_after_the_business_budget_closes_is_labelled(tmp_path, monkeypatch):
    def script(call, messages):
        if call <= 2: return {"name": "get_order", "arguments": {}}
        return report_citing(shown_evidence_ids(messages), outcome="NOT_STARTED")
    provider, outcome, context, store = episode(tmp_path, SmolagentsActorV2, script, caps=EpisodeBudget(http_attempts=1),
                                                monkeypatch=monkeypatch)
    closed = provider.requests[2]
    result = [row for row in embedded_objects(closed["messages"]) if "error" in row and "observations" in row][0]
    assert result["error"].startswith("Business budget exhausted")
    assert [row["evidence_id"] for row in result["observations"]] == ["obs-1"]
    assert not REAL_ID.search(request_text(closed))
    assert transport(closed)["final_report_required"] is True


# ----------------------------------------------------------------------------- 3. the strict final-report turn

def poll_then(final, *, polls=7):
    def script(call, messages):
        if call <= polls:
            return {"name": "get_operation_status", "arguments": {"service": "orders"}}
        return final(messages) if callable(final) else final
    return script


def test_final_turn_offers_only_final_answer_with_the_native_response_contract(tmp_path, monkeypatch):
    provider, outcome, context, store = episode(tmp_path, SmolagentsActorV2, poll_then(
        lambda messages: {"name": "final_answer", "arguments": {"answer": {"upgrade_outcome": "UNKNOWN",
            "notification_outcome": "NOT_STARTED", "overall": "SAFE_UNRESOLVED",
            "evidence_ids": shown_evidence_ids(messages)[-1:], "next_action": {"kind": "ESCALATE"}}}}), monkeypatch=monkeypatch)
    assert [transport(r)["final_report_required"] for r in provider.requests] == [False] * 7 + [True]
    final = provider.requests[-1]
    assert transport(final)["tools"] == [{"name": "final_answer", "description": FINAL_TURN_TOOL_DESCRIPTION,
                                          "inputs": {"answer": {"type": "object", "description": "Exact TaskReport object."}}}]
    assert transport(final)["remaining_actor_calls"] == 1
    assert "final_answer is the only allowed tool" in final["messages"][-1]["content"]
    assert final["kwargs"] == {"max_output_tokens": 2000, "response_contract": "native_final_answer", "role": "actor", "timeout_seconds": 20}
    assert all("response_contract" not in r["kwargs"] for r in provider.requests[:-1])
    # A report on the eighth (final) turn is accepted and recorded as a final-turn answer.
    assert outcome["report"]["evidence_ids"] == real_ids(context)[-1:]
    submitted, = events(store, context, "report_submitted")
    assert submitted["payload"]["final_report_required"] is True and submitted["payload"]["cited_evidence_tokens"] == ["obs-7"]


def test_a_business_call_on_the_final_turn_is_refused_without_dispatch_and_no_ninth_request_is_sent(tmp_path, monkeypatch):
    provider, outcome, context, store = episode(tmp_path, SmolagentsActorV2, poll_then(
        {"name": "get_operation_status", "arguments": {"service": "orders"}}), monkeypatch=monkeypatch)
    assert outcome == {"error": "ActorReportError", "message": "External agent produced no valid original final report"}
    # Step alignment: eight regular steps, only the eighth flagged; smolagents' max-steps fallback (a ninth
    # model request) was refused by the meter before any provider request.
    assert len(provider.requests) == 8 and context.broker.meter.usage.actor_calls == context.broker.meter.usage.model_calls == 8
    assert context.broker.meter.usage.http_attempts == 7                         # the final-turn call was not dispatched
    assert len(context.broker.logical_calls) == 7


def test_invalid_output_on_the_final_turn_is_not_repaired(tmp_path, monkeypatch):
    provider, outcome, context, store = episode(tmp_path, SmolagentsActorV2, poll_then('{"name": "final_answer"}'), monkeypatch=monkeypatch)
    assert outcome["error"] == "ActorReportError" and not events(store, context, "report_submitted")
    assert len(provider.requests) == 8


def test_steps_must_equal_the_actor_call_cap(tmp_path, monkeypatch):
    """v2 keeps v1's 8 steps and refuses, before any request, a cap that would misalign the final turn."""
    assert external_agent_v2.ALIGNED_STEPS == EpisodeBudget().actor_calls == 8
    provider, outcome, context, store = episode(tmp_path, SmolagentsActorV2, poll_then({"name": "get_order", "arguments": {}}),
                                                caps=EpisodeBudget(actor_calls=7), monkeypatch=monkeypatch)
    assert outcome == {"error": "ValueError", "message": "Adapter v2 steps differ from the episode actor-call cap"}
    assert provider.requests == [] and context.broker.meter.usage.model_calls == 0


# ----------------------------------------------------------------------------- 4. shared v1 behaviour: retry, failure, identity, stop

def test_transport_retry_on_the_final_turn_resends_the_identical_strict_request(tmp_path, monkeypatch):
    provider, outcome, context, store = episode(tmp_path, SmolagentsActorV2, poll_then(
        lambda messages: report_citing(shown_evidence_ids(messages)[:1], outcome="UNKNOWN")), fail={8}, monkeypatch=monkeypatch)
    usage = context.broker.meter.usage
    assert len(provider.requests) == 9 and provider.requests[7] == provider.requests[8]
    assert provider.requests[8]["kwargs"]["response_contract"] == "native_final_answer"
    assert usage.actor_calls == 8 and usage.model_calls == 9 and usage.cost_dollars is None
    retry, = events(store, context, "actor_transport_retry")
    assert retry["payload"] == {"code": "CONNECTION_ERROR", "attempt": 1}
    failure, = store.list_records("provider_failures")
    assert failure["diagnostics"]["code"] == "CONNECTION_ERROR"


@pytest.mark.parametrize("actor_class", [SmolagentsActor, SmolagentsActorV2])
@pytest.mark.parametrize("fail", [{2}, {2, 3}])
def test_transport_retry_parity_with_v1(tmp_path, monkeypatch, actor_class, fail):
    provider, outcome, context, store = episode(tmp_path, actor_class, SCRIPTS["success"], fail=fail, monkeypatch=monkeypatch)
    usage = context.broker.meter.usage
    retries = events(store, context, "actor_transport_retry")
    if fail == {2}:
        assert outcome["report"]["overall"] == "COMPLETED"
        assert (usage.actor_calls, usage.model_calls, len(provider.requests), len(retries)) == (4, 5, 5, 1)
        assert provider.requests[1] == provider.requests[2]
    else:
        assert outcome["error"] == "RuntimeProviderError"
        assert (usage.actor_calls, usage.model_calls, len(provider.requests), len(retries)) == (2, 3, 3, 1)
    assert len(store.list_records("provider_failures")) == len(fail)


@pytest.mark.parametrize("actor_class", [SmolagentsActor, SmolagentsActorV2])
def test_model_identity_check_parity_with_v1(tmp_path, monkeypatch, actor_class):
    provider, outcome, context, store = episode(tmp_path, actor_class, SCRIPTS["success"], model="other/model", monkeypatch=monkeypatch)
    assert outcome == {"error": "RuntimeProviderError", "message": "Provider returned a different frozen model"}
    assert len(provider.requests) == 1 and not context.broker.logical_calls
    assert len(store.list_records("provider_failures")) == 1


@pytest.mark.parametrize("actor_class", [SmolagentsActor, SmolagentsActorV2])
def test_cancellation_parity_with_v1(tmp_path, store, baseline, actor_class):
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        class Provider:
            calls = 0
            async def complete(self, messages, **kwargs):
                self.calls += 1; started.set()
                await release.wait()
                return RuntimeGeneration('{"name":"update_order","arguments":{"desired_shipping":"express"}}', MODEL)
        provider = Provider()
        intent, context, client = await native_context(tmp_path, store, baseline, provider, "native-stop")
        task = asyncio.create_task(actor_class(model_id=MODEL)(intent, context))
        await asyncio.wait_for(started.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        release.set()
        await asyncio.sleep(.02)
        assert provider.calls == 1 and not context.broker.logical_calls
        await client.close()
    asyncio.run(run())


def test_v2_reuses_v1_code_and_leaves_v1_unchanged():
    # The agent, its tools, memory, parser and step settings come from v1's own construction function, and
    # the transport, accounting, retry, stop and dispatch code from v1's bridge class.
    assert external_agent_v2._native_agent is external_agent._native_agent
    assert external_agent_v2._BridgeV2.__mro__[1] is external_agent._Bridge
    for name in ("call", "close", "account", "fail_provider"):
        assert name not in external_agent_v2._BridgeV2.__dict__
    assert external_agent_v2.TASK_CONTRACT is external_agent.TASK_CONTRACT
    assert external_agent_v2.TRANSPORT_CONTRACT is external_agent.TRANSPORT_CONTRACT


def test_decode_uses_only_observations_delivered_by_the_request(tmp_path, store, baseline):
    """A label for an observation delivered after the model's request stays as written (the reference Actor's rule).

    In the native loop nothing is delivered between a request and its final_answer, so this pins the rule directly.
    The request saw (was shown) two observations; the section below pins labels delivered but never shown.
    """
    from app.integrations.external_agent_v2 import _BridgeV2
    async def run():
        intent, context, client = await native_context(tmp_path, store, baseline, Scripted(lambda *_: {}), "snapshot-rule")
        try:
            for _ in range(3):
                await context.broker.call("get_order")
            bridge = _BridgeV2(context, asyncio.get_running_loop())
            rows = bridge._journal_rows()
            bridge.request_observations = rows[:2]            # the request saw two observations; a third came later
            bridge.request_shown_labels = frozenset({"obs-1", "obs-2"})
            answer = {"upgrade_outcome": "NOT_STARTED", "notification_outcome": "NOT_STARTED", "overall": "SAFE_UNRESOLVED",
                      "evidence_ids": ["obs-1", "obs-2", "obs-3"], "next_action": {"kind": "ESCALATE"}}
            report = await bridge._final_answer({"answer": answer})
            assert report["evidence_ids"] == [rows[0]["evidence_id"], rows[1]["evidence_id"], "obs-3"]
            submitted, = [e for e in store.events("snapshot-rule")["events"] if e["type"] == "report_submitted"]
            assert submitted["payload"]["evidence_labels"] == {rows[0]["evidence_id"]: "obs-1", rows[1]["evidence_id"]: "obs-2"}
        finally:
            await client.close()
    asyncio.run(run())


# ----------------------------------------------------------------------------- 5. only labels shown to the agent are decoded
# Review findings INT-1 and M1 (artifacts/product-native-v2-2026-09-29/review-integrity, review-product). The journal can hold
# an observation the agent is never shown. It still has a journal position, so its label exists; a guessed label for it
# must stay as written and fail exactly as in v1 (where a hidden hex ID cannot be guessed) and as the reference Actor's
# rule says (a label outside the request cannot make a guessed citation valid).

NON_BLOCKING_CONFIRMATION = {"parent_version": "policy-v0", "rules": [{"hook": "before_confirmation", "when": "always", "steps": [
    {"op": "read_current_operation"}, {"op": "require_receipt", "service": "orders", "status": "SUCCEEDED"}]}]}
# dev-6's recipe: the first confirmation attempt and the broker's one internal retry both fail transiently.
TWO_TRANSIENT_CONFIRMATIONS = FaultSpec.model_validate({"seed": 106, "primitives": [{
    "kind": "F4", "occurrence": 1, "parameters": {"failure_count": 2},
    "target_service": "notifications", "target_tool": "send_confirmation"}]})


def unresolved_report(tokens):
    return {"name": "final_answer", "arguments": {"answer": {"upgrade_outcome": "SUCCEEDED", "notification_outcome": "UNKNOWN",
            "overall": "SAFE_UNRESOLVED", "evidence_ids": tokens, "next_action": {"kind": "ESCALATE"}}}}


def scored_references(context, report):
    """The referee's evidence rule as the journal applies it (Journal.validate_report_references)."""
    try:
        context.broker.journal.validate_report_references(TaskReport.model_validate(report))
        return "PASSES"
    except ValueError as error:
        return f"FAILS: {error}"


def test_a_non_blocking_hook_read_the_agent_never_saw_cannot_be_cited_by_a_guessed_label(tmp_path, monkeypatch):
    def script(call, messages):
        if call == 1: return {"name": "update_order", "arguments": {"desired_shipping": "express"}}
        if call == 2: return {"name": "send_confirmation", "arguments": {}}
        return report_citing(["obs-1", "obs-3", "obs-2"])
    provider, outcome, context, store = episode(tmp_path, SmolagentsActorV2, script, policy=NON_BLOCKING_CONFIRMATION,
                                                monkeypatch=monkeypatch)
    ids = real_ids(context)
    # The hook's own status read is journal row 2; it passed, so v1's tool result (shared) returned only the confirmation.
    assert [(c["tool"], c["caller"], c["hook"]) for c in context.broker.logical_calls] == [
        ("update_order", "actor", None), ("get_operation_status", "policy", "before_confirmation"), ("send_confirmation", "actor", None)]
    assert shown_evidence_ids(provider.requests[-1]["messages"]) == ["obs-1", "obs-3"]
    # obs-1 and obs-3 decode; obs-2 was shown to no one, so it stays as written.
    assert outcome["report"]["evidence_ids"] == [ids[0], ids[2], "obs-2"]
    submitted, = events(store, context, "report_submitted")
    payload = submitted["payload"]
    assert payload["cited_evidence_tokens"] == ["obs-1", "obs-3", "obs-2"]
    assert payload["labels_shown_to_agent"] == ["obs-1", "obs-3"] and payload["cited_unshown_labels"] == ["obs-2"]
    assert payload["evidence_labels"] == {ids[0]: "obs-1", ids[1]: "obs-2", ids[2]: "obs-3"}   # positions are unchanged
    # Scored as written: it cites undelivered evidence, exactly as the same written answer does under v1.
    assert scored_references(context, outcome["report"]) == "FAILS: Report references undelivered evidence"


def test_a_write_attempt_the_broker_retried_internally_cannot_be_cited_by_a_guessed_label(tmp_path, monkeypatch):
    original = WorldClient.create
    async def create(self, episode_id, intent, fault_spec, *args, **kwargs):
        return await original(self, episode_id, intent, TWO_TRANSIENT_CONFIRMATIONS, *args, **kwargs)
    monkeypatch.setattr(WorldClient, "create", create)
    def script(call, messages):
        if call == 1: return {"name": "get_order", "arguments": {}}
        if call == 2: return {"name": "update_order", "arguments": {"desired_shipping": "express"}}
        if call == 3: return {"name": "send_confirmation", "arguments": {}}
        return unresolved_report(["obs-1", "obs-2", "obs-3", "obs-4"])
    provider, outcome, context, store = episode(tmp_path, SmolagentsActorV2, script, monkeypatch=monkeypatch)
    ids = real_ids(context)
    journal = [(o.result.tool, o.result.error_code) for o in context.broker.journal.observations]
    assert journal == [("get_order", None), ("update_order", None),
                       ("send_confirmation", "TRANSIENT_UNAVAILABLE"), ("send_confirmation", "TRANSIENT_UNAVAILABLE")]
    assert len(context.broker.logical_calls[-1]["attempt_ids"]) == 2        # one tool call, two attempts
    assert shown_evidence_ids(provider.requests[-1]["messages"]) == ["obs-1", "obs-2", "obs-4"]
    assert outcome["report"]["evidence_ids"] == [ids[0], ids[1], "obs-3", ids[3]]
    payload = events(store, context, "report_submitted")[0]["payload"]
    assert payload["labels_shown_to_agent"] == ["obs-1", "obs-2", "obs-4"] and payload["cited_unshown_labels"] == ["obs-3"]
    assert scored_references(context, outcome["report"]) == "FAILS: Report references undelivered evidence"


def test_citing_only_the_labels_shown_still_decodes_to_what_v1_would_cite(tmp_path, monkeypatch):
    """The same two episodes, citing only what the agent was shown: decoded exactly to the IDs v1's agent could copy."""
    def script(call, messages):
        if call == 1: return {"name": "update_order", "arguments": {"desired_shipping": "express"}}
        if call == 2: return {"name": "send_confirmation", "arguments": {}}
        return report_citing(shown_evidence_ids(messages))
    runs = {}
    for actor_class in (SmolagentsActor, SmolagentsActorV2):
        provider, outcome, context, store = episode(tmp_path / actor_class.__name__, actor_class, script,
                                                    policy=NON_BLOCKING_CONFIRMATION, monkeypatch=monkeypatch)
        runs[actor_class] = (outcome, context)
    (v1_outcome, v1_context), (v2_outcome, v2_context) = runs[SmolagentsActor], runs[SmolagentsActorV2]
    assert real_ids(v1_context) == real_ids(v2_context)
    assert v1_outcome["report"]["evidence_ids"] == v2_outcome["report"]["evidence_ids"] == [real_ids(v2_context)[i] for i in (0, 2)]
    assert scored_references(v2_context, v2_outcome["report"]) == "PASSES"


# ----------------------------------------------------------------------------- 6. final-turn input admission before the charge
# Review finding INT-2. v1's own check does not count the final turn's response schema; the provider layer does. v2 admits
# the final request with the schema counted before the turn is charged, as the reference Actor does.

class Admitting(Scripted):
    """The scripted transport plus the provider layer's own input admission (runtime.RuntimeProvider.complete)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.refused = []

    async def complete(self, messages, **kwargs):
        try:
            validate_request_input(messages, self.model, response_contract=kwargs.get("response_contract"))
        except ValueError:
            self.refused.append({"messages": messages, "kwargs": dict(sorted(kwargs.items()))})
            raise RuntimeProviderError("Model input exceeds or cannot verify the frozen token bound.", code="INPUT_LIMIT") from None
        return await super().complete(messages, **kwargs)


def final_report_after_polls(messages):
    return report_citing(shown_evidence_ids(messages)[-1:], outcome="UNKNOWN")


def admission_counts(messages):
    return (tokens.validate_model_input(messages, MODEL),
            validate_request_input(messages, MODEL, response_contract="native_final_answer"))


@pytest.mark.parametrize("over", [True, False], ids=["one-token-over-with-schema", "exactly-at-the-limit-with-schema"])
def test_a_final_request_over_the_limit_only_with_its_schema_is_refused_before_it_is_charged(tmp_path, monkeypatch, over):
    probe, _, _, _ = episode(tmp_path / "probe", SmolagentsActorV2, poll_then(final_report_after_polls), monkeypatch=monkeypatch)
    without_schema, with_schema = admission_counts(probe.requests[-1]["messages"])
    assert without_schema < with_schema                   # the gap the review measured (598 tokens on its golden request)
    limit = with_schema - 1 if over else with_schema
    monkeypatch.setattr(tokens, "MODEL_INPUT_TOKEN_LIMIT", limit)
    provider, outcome, context, store = episode(tmp_path / "run", SmolagentsActorV2, poll_then(final_report_after_polls),
                                                provider_class=Admitting, monkeypatch=monkeypatch)
    usage = context.broker.meter.usage
    assert provider.refused == []                         # the provider layer never had to refuse a charged request
    assert [r["messages"] for r in provider.requests[:7]] == [r["messages"] for r in probe.requests[:7]]
    if over:
        # v1's own count would have admitted it (without_schema <= limit); v2 refuses it before the charge.
        assert without_schema <= limit
        assert len(provider.requests) == 7 and usage.actor_calls == usage.model_calls == 7
        assert not store.list_records("provider_failures") and not events(store, context, "report_submitted")
        assert outcome["error"] == "AgentGenerationError" and "token input budget" in outcome["message"]
    else:
        assert provider.requests[-1] == probe.requests[-1] and usage.actor_calls == usage.model_calls == 8
        assert outcome["report"]["overall"] == "COMPLETED"


def test_the_final_turn_refusal_matches_v1s_refusal_of_an_over_limit_ordinary_turn(tmp_path, monkeypatch):
    """Parity: v1 refuses an over-limit request before charging it; v2's final turn now does the same, with its schema."""
    probe, _, _, _ = episode(tmp_path / "probe", SmolagentsActor, poll_then(final_report_after_polls), monkeypatch=monkeypatch)
    monkeypatch.setattr(tokens, "MODEL_INPUT_TOKEN_LIMIT", tokens.validate_model_input(probe.requests[-1]["messages"], MODEL) - 1)
    provider, outcome, context, store = episode(tmp_path / "run", SmolagentsActor, poll_then(final_report_after_polls),
                                                provider_class=Admitting, monkeypatch=monkeypatch)
    usage = context.broker.meter.usage
    assert len(provider.requests) == 7 and provider.refused == [] and usage.actor_calls == usage.model_calls == 7
    assert not store.list_records("provider_failures")
    assert outcome["error"] == "AgentGenerationError" and "token input budget" in outcome["message"]

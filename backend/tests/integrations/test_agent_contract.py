import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from app.adapters.business_tools import BusinessToolBroker, WorldClient
from app.adapters.journal import Journal, allocate_intent
from app.contracts.models import FaultSpec, TaskReport, content_hash
from app.integrations.external_agent import SmolagentsActor
from app.integrations.registry import freeze_target_configuration, verify_native_source
from app.lab.budgets import EpisodeMeter
from app.lab.policy_interpreter import PolicyInterpreter
from app.providers.runtime import RuntimeGeneration
from app.simulator.main import create_app


def test_real_independent_source_and_frozen_native_configuration(registry, external, source_configuration):
    registration, target = external
    assert registration.provenance_class == "external"
    assert registration.source_revision == "12c1bc820eca50ace6f80a21d90426d41d74f845"
    assert registration.source_hash == verify_native_source()
    assert registration.license == "Apache-2.0"
    assert registry.verify(registration.registration_id, target) == registration
    assert target["actor_prompt_hash"] != source_configuration["actor_prompt_hash"]
    assert target["contract_hash"] == source_configuration["contract_hash"]
    assert registry.reviewed_actor(registration.registration_id, model_id=target["model"]).__class__ is SmolagentsActor


@pytest.mark.parametrize("field", ["contract_hash", "service_hash", "capability_hash", "scorer_hash", "interpreter_hash", "dependency_lock_hash"])
def test_matching_forged_source_target_cannot_attest_to_semantics(source_configuration, field):
    forged = {**source_configuration, field: "f" * 64}
    with pytest.raises(ValueError, match="installed reviewed"):
        freeze_target_configuration(forged, "openai/gpt-oss-120b")


@pytest.mark.parametrize("field,value", [("reset_profile_id", "none"), ("budget_compatible", False), ("oracle_hash", "a" * 64), ("dry_run_status", "UNSUPPORTED"), ("adapter_entrypoint_id", "arbitrary.module.run")])
def test_resetless_unscorable_unreviewed_registration_rejected(store, registry, external, field, value):
    registration, target = external
    # Simulate a corrupted local store; registry still must not dispatch code.
    store.db.execute("DELETE FROM records WHERE kind='agent_registrations' AND id=?", (registration.registration_id,))
    changed = registration.model_copy(update={field: value})
    store.put_record("agent_registrations", registration.registration_id, changed)
    with pytest.raises(ValueError):
        registry.reviewed_actor(registration.registration_id)


def test_unknown_id_and_changed_target_model_are_rejected(registry, external):
    registration, target = external
    with pytest.raises(ValueError): registry.get("https://untrusted.example/agent.py")
    with pytest.raises(ValueError): registry.verify(registration.registration_id, {**target, "model": "different"})


async def native_context(tmp_path, store, baseline, provider, episode_id):
    app = create_app(database_dir=tmp_path / episode_id, control_token="offline-control")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8001")
    world_client = WorldClient("http://127.0.0.1:8001", "offline-control", client=client)
    intent = allocate_intent("order-1", "Upgrade this order to express and send its confirmation.")
    world = await world_client.create(episode_id, intent, FaultSpec(seed=42, primitives=[]))
    store.put_record("episodes", episode_id, {"campaign_id": "offline-native"})
    journal = Journal(store, episode_id, intent)
    broker = BusinessToolBroker(world_client, world["world_id"], world["capability"], journal, EpisodeMeter())
    interpreter = PolicyInterpreter(baseline.content, broker)
    context = SimpleNamespace(provenance=SimpleNamespace(episode_id=episode_id, origin="prototype"), provider=provider, broker=broker,
        interpreter=interpreter, metadata={"model_id": "openai/gpt-oss-120b"}, lab_mode=True, adapter_id="orders/v1",
        policy=baseline.content, policy_hash=baseline.policy_hash, policy_decision=baseline.decision, trace=None)
    return intent, context, world_client


def test_native_loop_executes_model_selected_actions_and_original_report(tmp_path, store, baseline):
    async def run():
        sessions = []
        for index in range(2):
            class Provider:
                def __init__(self): self.calls = []
                async def complete(self, messages, **kwargs):
                    self.calls.append(messages)
                    assert kwargs["max_output_tokens"] == 2000
                    if len(self.calls) == 1:
                        output = {"name": "update_order", "arguments": {"desired_shipping": "express"}}
                    elif len(self.calls) == 2:
                        output = {"name": "send_confirmation", "arguments": {}}
                    else:
                        output = {"name": "final_answer", "arguments": {"answer": {
                            "upgrade_outcome": "SUCCEEDED", "notification_outcome": "SUCCEEDED", "overall": "COMPLETED",
                            "evidence_ids": [o.evidence_id for o in context.broker.journal.observations], "next_action": {"kind": "NONE"}}}}
                    return RuntimeGeneration(json.dumps(output), "openai/gpt-oss-120b", 100, 20)
            provider = Provider()
            intent, context, client = await native_context(tmp_path, store, baseline, provider, f"native-{index}")
            report = await SmolagentsActor(model_id="openai/gpt-oss-120b")(intent, context)
            assert isinstance(report, TaskReport) and report.overall == "COMPLETED"
            assert len(provider.calls) == 3 and context.broker.meter.usage.actor_calls == 3
            assert [c["tool"] for c in context.broker.logical_calls] == ["update_order", "send_confirmation"]
            assert {h[0] for h in context.interpreter.visited} == {"after_upgrade_response", "before_confirmation", "after_notification_response", "before_final_report"}
            assert context.broker.meter.usage.input_tokens == 300
            prompt = json.dumps(provider.calls)
            assert "offline-control" not in prompt
            assert context.broker.capability not in prompt
            assert "fault_spec" not in prompt
            snapshot = await client.snapshot(context.broker.world_id)
            assert snapshot.orders[0].applied_shipping == "express"
            sessions.append((context.broker.world_id, provider.calls[0]))
            await client.close()
        assert sessions[0][0] != sessions[1][0]
        assert "native-0" not in json.dumps(sessions[1][1])
    asyncio.run(run())


def test_native_loop_does_not_repair_false_report(tmp_path, store, baseline):
    async def run():
        false_report = {"upgrade_outcome": "SUCCEEDED", "notification_outcome": "SUCCEEDED", "overall": "COMPLETED", "evidence_ids": ["invented"], "next_action": {"kind": "NONE"}}
        class Provider:
            async def complete(self, messages, **kwargs):
                return RuntimeGeneration(json.dumps({"name": "final_answer", "arguments": {"answer": false_report}}), "openai/gpt-oss-120b")
        intent, context, client = await native_context(tmp_path, store, baseline, Provider(), "false-report")
        report = await SmolagentsActor(model_id="openai/gpt-oss-120b")(intent, context)
        assert report.model_dump(mode="json") == false_report
        assert not context.broker.logical_calls
        await client.close()
    asyncio.run(run())


def test_native_fallback_cannot_make_ninth_call(tmp_path, store, baseline):
    async def run():
        class Provider:
            calls = 0
            async def complete(self, messages, **kwargs):
                self.calls += 1
                return RuntimeGeneration('{"name":"get_order","arguments":{}}', "openai/gpt-oss-120b")
        provider = Provider()
        intent, context, client = await native_context(tmp_path, store, baseline, provider, "native-cap")
        with pytest.raises(Exception):
            await SmolagentsActor(model_id="openai/gpt-oss-120b")(intent, context)
        assert provider.calls == 8
        assert context.broker.meter.usage.actor_calls == 8
        assert context.broker.meter.usage.http_attempts == 7
        await client.close()
    asyncio.run(run())


def test_native_cancellation_prevents_follow_on_calls(tmp_path, store, baseline):
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        class Provider:
            calls = 0
            async def complete(self, messages, **kwargs):
                self.calls += 1; started.set()
                await release.wait()
                return RuntimeGeneration('{"name":"update_order","arguments":{"desired_shipping":"express"}}', "openai/gpt-oss-120b")
        provider = Provider()
        intent, context, client = await native_context(tmp_path, store, baseline, provider, "native-stop")
        task = asyncio.create_task(SmolagentsActor(model_id="openai/gpt-oss-120b")(intent, context))
        await asyncio.wait_for(started.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        release.set()
        await asyncio.sleep(.02)
        assert provider.calls == 1 and not context.broker.logical_calls
        await client.close()
    asyncio.run(run())


def test_native_policy_hook_blocks_without_inventing_an_action(tmp_path, store, baseline):
    from app.contracts.models import RecoveryPolicy
    async def run():
        class Provider:
            calls = 0
            messages = []
            async def complete(self, messages, **kwargs):
                self.calls += 1; self.messages.append(messages)
                if self.calls == 1:
                    value = {"name": "send_confirmation", "arguments": {}}
                else:
                    value = {"name": "final_answer", "arguments": {"answer": {"upgrade_outcome": "NOT_STARTED", "notification_outcome": "NOT_STARTED",
                        "overall": "SAFE_UNRESOLVED", "evidence_ids": [], "next_action": {"kind": "ESCALATE"}}}}
                return RuntimeGeneration(json.dumps(value), "openai/gpt-oss-120b")
        provider = Provider()
        intent, context, client = await native_context(tmp_path, store, baseline, provider, "native-policy")
        policy = RecoveryPolicy.model_validate_json('{"parent_version":"policy-v0","rules":[{"hook":"before_confirmation","when":"always","steps":[{"op":"require_receipt","service":"orders","status":"SUCCEEDED"}]}]}')
        context.policy = policy; context.policy_hash = content_hash(policy); context.policy_decision = "ACCEPTED"
        context.interpreter = PolicyInterpreter(policy, context.broker)
        result = await SmolagentsActor(model_id="openai/gpt-oss-120b")(intent, context)
        assert result.overall == "SAFE_UNRESOLVED"
        assert not context.broker.logical_calls
        assert "RECEIPT_REQUIRED:orders" in json.dumps(provider.messages[-1])
        assert provider.calls == 2
        await client.close()
    asyncio.run(run())

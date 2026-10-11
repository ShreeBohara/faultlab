"""The v2 lab runtime: a scripted orders agent runs every development scenario through the worker on the kernel."""
import asyncio

import pytest

from effectsafe import Intent, Journal, ToolContract
from faultlab.core import Caps, content_hash, is_digest
from faultlab.evidence import AgentManifest, EnvSpec, Finding, TrialAttempt, plan_hash, validate_structure
from faultlab.evidence.bundles import read_bundle
from faultlab.lab import (AdmissionRefused, CapExhausted, ProtocolError, Scheduler, StoreConflict, TrialStore, TrialWorker, Verdict,
                          run_batch, schedule)
from faultlab.lab.worker import FACTS_FORMAT, PROJECTION
from faultlab.packs import load_pack

ORDERS = load_pack("orders.upgrade_then_confirm/v1")
AGENT = AgentManifest(adapter_id="scripted-orders", model="scripted/none")
ENV = EnvSpec(kind="simulator")
CAPS = Caps(model_calls=8, http_attempts=18, ticks=20, wall_seconds=30, dollars=0.0)


class ScriptedOrdersAdapter:
    """Read, upgrade, settle the upgrade through the status read, confirm, report: the reference path."""
    adapter_id = "scripted-orders"
    digest = "a" * 64

    def __init__(self, *, confirm_retries: int = 1):
        self.confirm_retries = confirm_retries

    async def act(self, session):
        i = session.intent
        session.model_call(input_tokens=10, output_tokens=5, dollars=0.0)
        await session.call("get_order", {"order_id": i["order_id"]})
        session.model_call()
        await session.call("update_order", {"order_id": i["order_id"], "operation_id": i["upgrade_operation_id"], "payload": {
            "order_id": i["order_id"], "desired_shipping": "express", "expected_version": i["expected_version"],
            "operation_id": i["upgrade_operation_id"], "idempotency_key": i["upgrade_idempotency_key"],
            "intent_hash": i["upgrade_intent_hash"]}})
        polls, last = 0, None
        while session.operation(i["upgrade_operation_id"]).outcome in ("UNKNOWN", "PENDING") and polls < 4:
            session.model_call()
            last = await session.call("get_operation_status", {"service": "orders", "operation_id": i["upgrade_operation_id"]})
            polls += 1
        upgrade = session.operation(i["upgrade_operation_id"])
        evidence = [o.evidence_id for o in session.observations]
        if upgrade.outcome == "FAILED":
            return {"upgrade_outcome": "FAILED", "notification_outcome": "NOT_REQUIRED", "overall": "CORRECTLY_REJECTED",
                    "evidence_ids": evidence[-1:], "next_action": {"kind": "NONE"}}
        if upgrade.outcome != "SUCCEEDED":
            return {"upgrade_outcome": "UNKNOWN", "notification_outcome": "NOT_STARTED", "overall": "SAFE_UNRESOLVED",
                    "evidence_ids": evidence[-1:], "next_action": {"kind": "CHECK_EXISTING_UPGRADE", "operation_id": i["upgrade_operation_id"]}}
        session.model_call()
        payload = {"order_id": i["order_id"], "upgrade_operation_id": i["upgrade_operation_id"], "operation_id": i["notification_operation_id"],
                   "idempotency_key": i["notification_idempotency_key"], "intent_hash": i["notification_intent_hash"], "template_version": "confirmation/v1"}
        for _ in range(1 + self.confirm_retries):
            await session.call("send_confirmation", {"order_id": i["order_id"], "operation_id": i["notification_operation_id"], "payload": payload})
            if session.operation(i["notification_operation_id"]).outcome == "SUCCEEDED":
                break
        note = session.operation(i["notification_operation_id"])
        evidence = [o.evidence_id for o in session.observations]
        upgrade_evidence = next(o.evidence_id for o in reversed(session.observations)
                                if o.tool in ("update_order", "get_operation_status") and o.result.get("status") == "SUCCEEDED")
        if note.outcome == "SUCCEEDED":
            return {"upgrade_outcome": "SUCCEEDED", "notification_outcome": "SUCCEEDED", "overall": "COMPLETED",
                    "evidence_ids": [upgrade_evidence, evidence[-1]], "next_action": {"kind": "NONE"}}
        return {"upgrade_outcome": "SUCCEEDED", "notification_outcome": "UNKNOWN", "overall": "SAFE_UNRESOLVED",
                "evidence_ids": [upgrade_evidence], "next_action": {"kind": "CHECK_EXISTING_NOTIFICATION", "operation_id": i["notification_operation_id"]}}


class ReportReferee:
    """A test double: the task outcome is what the report claims; one finding records that it was read."""

    def score(self, envelope, context):
        assert context.decision is not None and context.horizon is not None and context.execution
        overall = (envelope.report.original or {}).get("overall") if isinstance(envelope.report.original, dict) else None
        task = {"COMPLETED": "COMPLETED", "SAFE_UNRESOLVED": "SAFE_UNRESOLVED", "CORRECTLY_REJECTED": "CORRECTLY_REFUSED"}.get(overall, "VIOLATION")
        return Verdict(task=task, findings=[Finding(property_id="T1", property_version="test", result="PASS", family="false_report",
                                                    severity="major", witnesses=[0])], note="scored by the test referee")


def plan_for(scenario_id, *, k=1, caps=CAPS):
    plan = ORDERS.plan(scenario_id, agent=AGENT, environment=ENV, protocol_version="faultlab/v2-test", caps=caps)
    return plan.model_copy(update={"repetition": plan.repetition.model_copy(update={"k": k})})


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def store(tmp_path):
    with TrialStore(tmp_path / "trials.sqlite3") as store:
        yield store


def worker_for(store, tmp_path, **kwargs):
    return TrialWorker(store=store, worker_id="worker-test", database_dir=tmp_path / "worlds", **kwargs)


def test_every_development_scenario_runs_through_the_worker_and_seals(store, tmp_path):
    worker = worker_for(store, tmp_path, referee=ReportReferee())
    adapter = ScriptedOrdersAdapter()
    expected = {"dev-1": "COMPLETED", "dev-2": "COMPLETED", "dev-3": "COMPLETED", "dev-4": "COMPLETED",
                "dev-5": "CORRECTLY_REFUSED", "dev-6": "COMPLETED"}
    for scenario in ORDERS.scenarios:
        plan = plan_for(scenario.scenario_id)
        attempt = TrialAttempt(attempt_id=f"trial-{scenario.scenario_id}", plan_hash=plan_hash(plan), lifecycle="CREATED")
        envelope = run(worker.run(plan, attempt, adapter))
        validate_structure(envelope.model_dump(mode="json"))
        assert store.envelope(attempt.attempt_id).digest == envelope.digest
        assert envelope.outcome.execution == "COMPLETED" and envelope.outcome.task == expected[scenario.scenario_id], scenario.scenario_id
        assert envelope.attempt.lifecycle == "TERMINAL" and envelope.attempt.terminal_reason is None
        assert envelope.report.status == "DELIVERED" and envelope.report.interpreted is not None
        assert envelope.outcome.claims.status == "SCORED" and envelope.outcome.claims.mismatches == [], scenario.scenario_id
        assert [f.property_id for f in envelope.outcome.findings] == ["T1"]
        assert envelope.outcome.exposure.all_required_triggered is True, (scenario.scenario_id, envelope.outcome.exposure)
        assert [f.fault_id for f in envelope.outcome.exposure.faults] == [p.fault_id for p in plan.schedule.placements]
        planes = {event.plane for event in envelope.events}
        assert planes == {"agent_visible", "evaluator", "orchestrator"}
        kinds = [event.kind for event in envelope.events]
        assert kinds[0] == "trial_started" and "invoked" in kinds and "response_delivered" in kinds and "claim" in kinds and "admitted" in kinds
        assert envelope.source.projection == PROJECTION and envelope.source_facts["format"] == FACTS_FORMAT
        assert envelope.outcome.identity.pack_digest == ORDERS.digest() and is_digest(envelope.outcome.identity.kernel_digest)
        assert envelope.outcome.identity.adapter_digest == "a" * 64 and envelope.outcome.cost.dollars_measured == 0.0
        assert envelope.outcome.cost.http_attempts == len([e for e in envelope.events if e.kind == "invoked"])
        assert envelope.outcome.cost.ticks == envelope.source_facts["usage"]["ticks"]


def test_a_lost_reply_is_decided_by_the_declared_delay_and_the_effect_is_durable(store, tmp_path):
    worker = worker_for(store, tmp_path, referee=ReportReferee())
    plan = plan_for("dev-2")
    envelope = run(worker.run(plan, TrialAttempt(attempt_id="trial-lost", plan_hash=plan_hash(plan), lifecycle="READY"), ScriptedOrdersAdapter()))
    delivered = [e for e in envelope.events if e.kind == "response_delivered"]
    updates = [e for e in delivered if e.payload["observation"]["tool"] == "update_order"]
    # The reply to the first attempt is lost (declared delay 1.5 s against a 1.0 s timeout) while the effect
    # committed; the one automatic resend of the pinned bytes replays that effect instead of repeating it.
    assert [u.payload["observation"]["transport"] for u in updates] == ["timeout", "ok"]
    assert [u.payload["outcome"] for u in updates] == ["UNKNOWN", "SUCCEEDED"]
    assert updates[0].payload["reply_delay_seconds"] == 1.5 and updates[1].payload["observation"]["result"]["status"] == "SUCCEEDED"
    upgrade_call = next(c for c in envelope.source_facts["calls"] if c["tool"] == "update_order")
    assert len(upgrade_call["attempt_ids"]) == 2
    committed = [e for e in envelope.events if e.plane == "evaluator" and e.kind == "effect_committed" and e.payload["type"] == "upgrade_committed"]
    accepted = [e for e in envelope.events if e.plane == "evaluator" and e.kind == "accepted" and e.payload["payload"]["service"] == "orders"]
    assert len(committed) == 1 and len(accepted) == 1 and accepted[0].payload["call_id"] == upgrade_call["call_id"]
    assert envelope.outcome.task == "COMPLETED" and envelope.outcome.exposure.faults[0].triggered is True
    assert envelope.outcome.exposure.faults[0].attempt_ref == upgrade_call["attempt_ids"][0]


def test_a_transient_refusal_proves_no_effect_and_the_keyed_write_is_resent(store, tmp_path):
    worker = worker_for(store, tmp_path, referee=ReportReferee())
    plan = plan_for("dev-6")
    envelope = run(worker.run(plan, TrialAttempt(attempt_id="trial-transient", plan_hash=plan_hash(plan), lifecycle="READY"), ScriptedOrdersAdapter()))
    confirmations = [e.payload for e in envelope.events if e.kind == "response_delivered" and e.payload["observation"]["tool"] == "send_confirmation"]
    assert [c["observation"]["http_status"] for c in confirmations] == [503, 503, 201]
    assert [c["outcome"] for c in confirmations] == ["NOT_STARTED", "NOT_STARTED", "SUCCEEDED"]
    calls = envelope.source_facts["calls"]
    assert [len(c["attempt_ids"]) for c in calls if c["tool"] == "send_confirmation"] == [2, 1]
    assert envelope.outcome.task == "COMPLETED" and sum(1 for e in envelope.events if e.kind == "effect_committed") == 2


def test_without_a_referee_the_execution_is_pending_evidence_and_the_oracle_still_scores(store, tmp_path):
    worker = worker_for(store, tmp_path)
    plan = plan_for("dev-5")
    envelope = run(worker.run(plan, TrialAttempt(attempt_id="trial-unscored", plan_hash=plan_hash(plan), lifecycle="READY"), ScriptedOrdersAdapter()))
    assert envelope.outcome.execution == "PENDING_EVIDENCE" and envelope.outcome.task is None and envelope.outcome.findings == []
    assert "TASK_OUTCOME_UNSCORED" in envelope.source.notes
    assert envelope.outcome.claims.status == "SCORED" and envelope.outcome.claims.claims["upgrade_outcome"]["belief"] == "TRUE"
    assert envelope.report.original["overall"] == "CORRECTLY_REJECTED"


def test_caps_and_adapter_failures_end_in_sealed_envelopes(store, tmp_path):
    worker = worker_for(store, tmp_path, referee=ReportReferee())

    class Greedy:
        adapter_id = "scripted-orders"

        async def act(self, session):
            for _ in range(100):
                session.model_call()

    class Broken:
        adapter_id = "scripted-orders"

        async def act(self, session):
            raise RuntimeError("model unavailable")

    class Silent:
        adapter_id = "scripted-orders"

        async def act(self, session):
            await session.call("get_order", {"order_id": session.intent["order_id"]})
            return None

    class Foreign:
        adapter_id = "scripted-orders"

        async def act(self, session):
            await session.call("no_such_tool", {})

    plan = plan_for("dev-1")
    greedy = run(worker.run(plan, TrialAttempt(attempt_id="trial-greedy", plan_hash=plan_hash(plan), lifecycle="READY"), Greedy()))
    assert greedy.outcome.execution == "COMPLETED" and greedy.attempt.terminal_reason == "CAP_REACHED:model_calls"
    assert greedy.report.status == "ABSENT" and greedy.outcome.cost.model_calls == 8 and greedy.outcome.task == "VIOLATION"
    broken = run(worker.run(plan, TrialAttempt(attempt_id="trial-broken", plan_hash=plan_hash(plan), lifecycle="READY"), Broken()))
    assert broken.outcome.execution == "INFRA_ERROR" and broken.outcome.task is None
    assert broken.attempt.terminal_reason == "ADAPTER_ERROR:RuntimeError" and broken.outcome.evidence_completeness == "incomplete"
    silent = run(worker.run(plan, TrialAttempt(attempt_id="trial-silent", plan_hash=plan_hash(plan), lifecycle="READY"), Silent()))
    assert silent.report.status == "ABSENT" and silent.outcome.claims.status == "SCORED" and silent.outcome.task == "VIOLATION"
    foreign = run(worker.run(plan, TrialAttempt(attempt_id="trial-foreign", plan_hash=plan_hash(plan), lifecycle="READY"), Foreign()))
    assert foreign.attempt.terminal_reason.startswith("PROTOCOL_ERROR:") and foreign.outcome.execution == "COMPLETED"
    assert {a.lifecycle for a in store.attempts()} == {"TERMINAL"}


def test_a_plan_the_worker_cannot_honour_is_refused_before_any_world_exists(store, tmp_path):
    worker = worker_for(store, tmp_path)
    plan = plan_for("dev-1").model_copy(update={"pack_digest": "f" * 64})
    envelope = run(worker.run(plan, TrialAttempt(attempt_id="trial-stale", plan_hash=plan_hash(plan), lifecycle="READY"), ScriptedOrdersAdapter()))
    assert envelope.outcome.execution == "INFRA_ERROR" and envelope.attempt.terminal_reason == "PACK_DIGEST_MISMATCH"
    assert envelope.outcome.evidence_completeness == "unavailable" and envelope.events[0].kind == "refused"
    assert not (tmp_path / "worlds").exists() or not list((tmp_path / "worlds").glob("*.sqlite3"))
    other = plan_for("dev-1").model_copy(update={"agent": AgentManifest(adapter_id="someone-else", model="m")})
    envelope = run(worker.run(other, TrialAttempt(attempt_id="trial-other", plan_hash=plan_hash(other), lifecycle="READY"), ScriptedOrdersAdapter()))
    assert envelope.attempt.terminal_reason == "ADAPTER_MISMATCH"
    with pytest.raises(ProtocolError):
        run(worker.run(other, TrialAttempt(attempt_id="trial-wrong", plan_hash="0" * 64, lifecycle="READY"), ScriptedOrdersAdapter()))


def test_the_store_keeps_records_typed_immutable_and_forward_only(store):
    plan = plan_for("dev-1")
    digest = store.put_plan(plan)
    assert store.plan(digest) == plan and store.put_plan(plan) == digest and store.plans() == [plan]
    with pytest.raises(StoreConflict, match="names a plan"):
        store.put_attempt(TrialAttempt(attempt_id="t-1", plan_hash="1" * 64, lifecycle="READY"))
    attempt = TrialAttempt(attempt_id="t-1", plan_hash=digest, lifecycle="READY")
    store.put_attempt(attempt, batch_id="b", position=3)
    assert store.attempt("t-1") == attempt and store.attempt_batch("t-1") == "b"
    claimed = store.claim("w-1", batch_id="b")
    assert claimed.lifecycle == "RUNNING" and claimed.started_at and store.claim("w-2", batch_id="b") is None
    with pytest.raises(StoreConflict, match="back"):
        store.put_attempt(attempt)
    with pytest.raises(StoreConflict, match="plan cannot change"):
        store.put_attempt(claimed.model_copy(update={"plan_hash": store.put_plan(plan_for("dev-2"))}))
    assert store.recover() == ["t-1"]
    closed = store.attempt("t-1")
    assert closed.lifecycle == "TERMINAL" and closed.terminal_reason == "INTERRUPTED_BY_WORKER_RESTART" and closed.ended_at
    assert store.recover() == [] and store.spent()["measured"]["envelopes"] == 0
    with pytest.raises(StoreConflict, match="No envelope"):
        store.envelope("t-1")
    summary = store.summary(batch_id="b")
    assert summary["attempts"] == {"TERMINAL": 1} and summary["executions"] == {} and summary["plans"] == 2


def test_schedule_and_run_a_batch_then_export_its_bundle(store, tmp_path):
    plans = [plan_for("dev-1", k=2), plan_for("dev-5", k=1)]
    batch = schedule(store, plans, name="smoke", caps=Caps(dollars=1.0, model_calls=100), order="repetition_major")
    attempts = store.attempts(batch_id=batch.batch_id)
    assert [a.plan_hash for a in attempts] == [plan_hash(plans[0]), plan_hash(plans[1]), plan_hash(plans[0])]
    assert all(a.lifecycle == "READY" for a in attempts) and store.batch(batch.batch_id)["name"] == "smoke"
    worker = worker_for(store, tmp_path, referee=ReportReferee())
    envelopes = run(run_batch(store, batch.batch_id, worker, ScriptedOrdersAdapter()))
    assert [e.outcome.task for e in envelopes] == ["COMPLETED", "CORRECTLY_REFUSED", "COMPLETED"]
    assert Scheduler(store, batch.batch_id, worker_id="w").next() is None
    summary = store.summary(batch_id=batch.batch_id)
    assert summary["attempts"] == {"TERMINAL": 3} and summary["tasks"] == {"COMPLETED": 2, "CORRECTLY_REFUSED": 1}
    assert summary["spent"]["measured"]["dollars"] == 0.0 and summary["spent"]["measured"]["model_calls"] == sum(e.outcome.cost.model_calls for e in envelopes)
    manifest = store.export_bundle(tmp_path / "batch.zip", name="smoke", batch_id=batch.batch_id)
    read_manifest, read_envelopes = read_bundle(tmp_path / "batch.zip")
    assert read_manifest.manifest_digest == manifest.manifest_digest and [e.digest for e in read_envelopes] == [e.digest for e in envelopes]
    plan_major = schedule(store, plans, name="ordered", order="plan_major")
    assert [a.plan_hash for a in store.attempts(batch_id=plan_major.batch_id)] == [plan_hash(plans[0])] * 2 + [plan_hash(plans[1])]


def test_the_store_command_prints_a_summary(store, tmp_path, capsys):
    import json

    from faultlab import __main__ as cli

    plan = plan_for("dev-1")
    worker = worker_for(store, tmp_path, referee=ReportReferee())
    run(worker.run(plan, TrialAttempt(attempt_id="trial-cli", plan_hash=plan_hash(plan), lifecycle="READY"), ScriptedOrdersAdapter()))
    assert cli.main(["store", store.path]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["attempts"] == {"TERMINAL": 1} and summary["tasks"] == {"COMPLETED": 1} and summary["spent"]["measured"]["envelopes"] == 1
    assert cli.main(["store", str(tmp_path / "missing.sqlite3")]) == 2


def test_admission_refuses_rather_than_exceeding_the_batch_caps(store, tmp_path):
    costly = plan_for("dev-1", k=3, caps=CAPS.model_copy(update={"dollars": 0.4}))
    with pytest.raises(ValueError, match="dollar bound"):
        schedule(store, [plan_for("dev-1", caps=CAPS.model_copy(update={"dollars": None}))], name="x", caps=Caps(dollars=1.0))
    batch = schedule(store, [costly], name="capped", caps=Caps(dollars=1.0))
    scheduler = Scheduler(store, batch.batch_id, worker_id="w")
    first_plan, first = scheduler.next()
    assert first.lifecycle == "RUNNING" and store.spent(batch_id=batch.batch_id)["reserved"]["dollars"] == 0.4
    second_plan, second = scheduler.next()                   # 0.4 reserved + 0.4 more fits inside 1.0
    with pytest.raises(AdmissionRefused, match="BATCH_DOLLAR_CAP"):
        scheduler.next()                                     # a third 0.4 would exceed 1.0
    assert scheduler.pending() == 1
    worker = worker_for(store, tmp_path, referee=ReportReferee())
    run(worker.run(first_plan, first, ScriptedOrdersAdapter()))
    run(worker.run(second_plan, second, ScriptedOrdersAdapter()))
    # Measured $0 for the two sealed envelopes: the third attempt now fits.
    third_plan, third = scheduler.next()
    assert third.lifecycle == "RUNNING" and scheduler.pending() == 0
    calls = Scheduler(store, schedule(store, [plan_for("dev-1", caps=CAPS.model_copy(update={"model_calls": None}))], name="m",
                                      caps=Caps(model_calls=10)).batch_id, worker_id="w")
    with pytest.raises(AdmissionRefused, match="UNBOUNDED_PLAN"):
        calls.next()


def test_the_journal_keeps_a_key_the_pack_already_allocated():
    keyed = ToolContract(name="update_order", kind="write", identity_scope="client_key", key_placement="field", mismatch_behavior="conflict",
                         status_lookup="get_operation_status")
    with Journal(namespace="trial-1") as journal:
        preset = journal.prepare(Intent(operation_id="op-1", action="update_order", scope="order-1",
                                        payload={"desired_shipping": "express", "idempotency_key": "upgrade-key-given"}), keyed)
        assert preset["key"] == "upgrade-key-given" and '"idempotency_key":"upgrade-key-given"' in preset["original_bytes"]
        derived = journal.prepare(Intent(operation_id="op-2", action="update_order", scope="order-1", payload={"desired_shipping": "express"}), keyed)
        assert derived["key"].startswith("key-") and derived["key"] in derived["original_bytes"]


def test_the_session_refuses_a_second_report_and_closed_use(store, tmp_path):
    worker = worker_for(store, tmp_path, referee=ReportReferee())

    class TwoReports:
        adapter_id = "scripted-orders"

        async def act(self, session):
            session.submit({"overall": "COMPLETED"})
            with pytest.raises(ProtocolError, match="one report"):
                session.submit({"overall": "COMPLETED"})
            with pytest.raises(CapExhausted):
                for _ in range(20):
                    session.model_call()
            return None

    plan = plan_for("dev-1")
    envelope = run(worker.run(plan, TrialAttempt(attempt_id="trial-two", plan_hash=plan_hash(plan), lifecycle="READY"), TwoReports()))
    assert envelope.report.status == "DELIVERED" and envelope.report.interpreted is None and envelope.outcome.task == "COMPLETED"
    assert content_hash(envelope.report.original) == content_hash({"overall": "COMPLETED"})

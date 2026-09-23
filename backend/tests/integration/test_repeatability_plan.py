"""Standalone study admission/retention without credentials or model transport."""
import asyncio
from collections import Counter
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.contracts.models import TrialResult, Usage, content_hash, new_id

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("repeatability_experiment", ROOT / "scripts/experiments/repeatability.py")
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


def configured_settings():
    return Settings(wandb_api_key="offline-placeholder", wandb_entity="shreetbohara-quinstreet", wandb_project="Faultlab",
        wandb_model="deepseek-ai/DeepSeek-V3.1", wandb_explorer_model="deepseek-ai/DeepSeek-V4-Pro-0813",
        wandb_mechanic_model="deepseek-ai/DeepSeek-V3.1", faultlab_live_enabled=True,
        faultlab_confirmed_entity="shreetbohara-quinstreet", faultlab_control_token="offline-capability",
        faultlab_input_dollars_per_million=.55, faultlab_output_dollars_per_million=1.65,
        faultlab_pricing_model="deepseek-ai/DeepSeek-V3.1", faultlab_pricing_verified=True,
        faultlab_reasoning_input_dollars_per_million=1.31, faultlab_reasoning_output_dollars_per_million=3.96,
        faultlab_reasoning_pricing_model="deepseek-ai/DeepSeek-V4-Pro-0813", faultlab_reasoning_pricing_verified=True)


def args_for(tmp_path, allowance="100"):
    return study.arguments(["--output", str(tmp_path / "new-study"), "--allowance-dollars", allowance])


def exported_only(monkeypatch, base=None):
    def from_env(cls, env_path=None):
        assert env_path == "/dev/null", "Dry plan must not read credentials"
        return base or configured_settings()
    monkeypatch.setattr(study.Settings, "from_env", classmethod(from_env))
    monkeypatch.setattr(study.Settings, "local_control_token", lambda self: pytest.fail("Dry plan resolved a capability"))


def test_dry_plan_is_nonmutating_and_freezes_cases_order_and_reservation(monkeypatch, tmp_path):
    exported_only(monkeypatch)
    monkeypatch.setattr(study, "LabStore", lambda *a, **k: pytest.fail("Dry plan opened a store"))
    monkeypatch.setattr(study, "LabCoordinator", lambda *a, **k: pytest.fail("Dry plan created a coordinator"))
    args = args_for(tmp_path)
    settings, caps, cases, target, plan = study.prepare(args)
    assert not args.execute_live and not args.output.exists()
    assert plan["order_id"] == "order-1" and plan["planned_trials"] == 30
    assert [slot["case_id"] for slot in plan["slots"]] == ["healthy", "delay-5", "delay-4"] * 10
    assert Counter(slot["case_id"] for slot in plan["slots"]) == {"healthy": 10, "delay-5": 10, "delay-4": 10}
    assert len({slot["episode_id"] for slot in plan["slots"]}) == 30
    assert [(s["repeat_index"], s["block_index"], s["trial_index"]) for s in plan["slots"][::3]] == [(i, i // 3, i % 3) for i in range(10)]
    assert [case["fault_spec"]["seed"] for case in cases] == [101, 19, 20240517]
    assert [case["fault_spec"]["primitives"][0]["parameters"]["completion_delay_ticks"] for case in cases[1:]] == [5, 4]
    assert [content_hash(c["fault_spec"]) for c in cases[1:]] == [
        "d07dea93a884f59fdb035a37f80e93dbf36b1686fc8d78c199eaebd6c938249d",
        "0a610483d53a4e5fb8ef022a0b73bb947036dd9a0572982a2c29eaf7c3e650fe"]
    assert plan["planned_model_call_ceiling"] == 240
    assert plan["planned_token_ceiling"] == 8_160_000
    assert plan["planned_actor_dollar_ceiling"] == 5.016
    assert plan["minimum_allowance_with_protected_reserves"] == 64.99136
    assert plan["batch_admission_max_role_dollar_reservation"] == 11.9616
    assert plan["minimum_call_cap_with_protected_reserves"] == 1304
    assert plan["minimum_token_cap_with_protected_reserves"] == 44_336_000
    assert target["model_settings"] == plan["model_settings"]
    assert "offline-placeholder" not in json.dumps(plan)


@pytest.mark.parametrize("allowance", ["0", "-1", "501", "nan", "inf", "64.99"])
def test_invalid_or_insufficient_allowance_rejected_without_writes(monkeypatch, tmp_path, allowance):
    exported_only(monkeypatch)
    args = args_for(tmp_path, allowance)
    with pytest.raises(study.PlanningError):
        study.prepare(args)
    assert not args.output.exists()


@pytest.mark.parametrize("field,value", [("faultlab_model_call_cap", 1303), ("faultlab_token_cap", 44_335_999)])
def test_protected_call_and_token_headroom_are_enforced(monkeypatch, tmp_path, field, value):
    exported_only(monkeypatch, replace(configured_settings(), **{field: value}))
    with pytest.raises(study.PlanningError, match="protected reserves"):
        study.prepare(args_for(tmp_path))


def test_existing_output_never_resumed(monkeypatch, tmp_path):
    args = args_for(tmp_path)
    args.output.mkdir()
    sentinel = args.output / "original"
    sentinel.write_text("retained")
    with pytest.raises(study.PlanningError, match="new output"):
        study.prepare(args)
    assert sentinel.read_text() == "retained"


def test_runtime_change_prevents_next_trial(monkeypatch, tmp_path):
    exported_only(monkeypatch)
    settings, caps, cases, target, plan = study.prepare(args_for(tmp_path))
    registry = SimpleNamespace(verify=lambda *a: pytest.fail("Must reject drift before registration"))
    monkeypatch.setattr(study, "frozen_configuration", lambda *a: {**target, "runtime_hash": "0" * 64})
    with pytest.raises(study.PlanningError, match="runtime"):
        study.verify_frozen(settings, caps, cases, target, plan, registry, "reference-id")


@pytest.mark.parametrize("fail_at,expected_attempts", [(None, 30), (4, 4)])
def test_execution_retains_original_reports_and_all_slots_without_retry(monkeypatch, tmp_path, fail_at, expected_attempts):
    """Fake transport exercises the actual harness orchestration and durable ledger."""
    base = configured_settings()
    monkeypatch.setattr(study.Settings, "from_env", classmethod(lambda cls, env_path=None: base))
    args = args_for(tmp_path)
    _, caps, cases, target, plan = study.prepare(args)
    predictions, calls = [], []
    baseline = SimpleNamespace(decision="BASELINE", version="policy-v0", policy_hash="a" * 64,
                               content=SimpleNamespace(rules=[]))

    class Guard:
        def bind(self, address): assert address == ("127.0.0.1", 8000)
        def close(self): pass
    monkeypatch.setattr(study, "socket", SimpleNamespace(socket=Guard))

    class Session:
        async def record_prediction(self, episode_id, **kw): predictions.append((episode_id, kw))
        async def finish(self, summary): return {"status": "weave_verified", "remote_ref": "offline-evaluation"}

    class Runner:
        world_client = provider = telemetry_worker = None
        def __init__(self, store): self.store = store
        async def run(self, campaign, recipe, policy, **kw):
            calls.append(kw)
            ledger = kw["ledger"]
            ledger.consume_call(reservation=kw["reservation"], role="actor")
            ledger.reconcile(SimpleNamespace(input_tokens=10, output_tokens=2, cost_usd=None))
            failure = fail_at == len(calls)
            # Valid model violations remain in the study; the harness must not
            # stop early, rewrite missing reports or replace an unfavorable run.
            violation = len(calls) % 2 == 0
            report = None if violation or failure else {"original": kw["episode_id"]}
            self.store.put_record("episodes", kw["episode_id"], {"campaign_id": campaign.campaign_id, "report": report,
                "verdict": None if failure else {"checks": [{"check_id": f"C{i}", "passed": not violation} for i in range(1, 9)]}})
            return TrialResult(episode_id=kw["episode_id"], world_id=new_id("world"),
                scenario_hash=content_hash(recipe), policy_hash=policy.policy_hash, arm="B0",
                trial_index=kw["trial_index"], lifecycle="LAB_ERROR" if failure else "COMPLETED",
                outcome="LAB_ERROR" if failure else "VIOLATION" if violation else "COMPLETED",
                failed_checks=["C5"] if violation and not failure else [],
                fault_scheduled=bool(recipe.primitives), fault_triggered=bool(recipe.primitives),
                usage=Usage(actor_calls=1, model_calls=1, input_tokens=10, output_tokens=2))

    class Coordinator:
        def __init__(self, settings, store):
            self.store = store
            self.ledgers = {}
            self.active_id = None
            self.policies = SimpleNamespace(baseline=lambda: baseline)
            self.evaluation_publisher = SimpleNamespace(begin=self.begin)
            self.evidence_gateway = SimpleNamespace(get=self.evidence)
        def save(self, campaign): self.store.put_record("campaigns", campaign.campaign_id, campaign)
        async def require_simulator(self): pass
        async def _get_runner(self, live): return Runner(self.store), True
        async def begin(self, *a, **kw):
            assert kw["expected_episode_ids"] == [s["episode_id"] for s in plan["slots"]]
            return Session()
        async def evidence(self, episode_id, *a, **kw):
            return SimpleNamespace(source="weave_verified", root_call_id="offline-root")

    monkeypatch.setattr(study, "LabCoordinator", Coordinator)
    monkeypatch.setattr(study, "development_recording", lambda store, campaign_id, **kw: {"campaign_id": campaign_id})
    result = asyncio.run(study.execute(args, caps, cases, target, plan))
    saved = json.loads((args.output / "summary.json").read_text())
    assert len(calls) == expected_attempts
    assert len(saved["slots"]) == 30
    assert len({c["episode_id"] for c in calls}) == expected_attempts
    assert saved["accounting"]["charged_model_calls"] == expected_attempts
    assert saved["accounting"]["charged_dollar_upper_bound"] == pytest.approx(expected_attempts * .0209)
    assert saved["accounting"]["measured_token_price_estimate"] == pytest.approx(expected_attempts * (10 * .55 + 2 * 1.65) / 1_000_000)
    assert saved["accounting"]["actual_provider_cost_dollars"] is None
    assert len(predictions) == expected_attempts - bool(fail_at)
    for episode_id, row in predictions:
        slot_index = next(i for i, s in enumerate(saved["slots"]) if s["episode_id"] == episode_id)
        expected = None if (slot_index + 1) % 2 == 0 else {"original": episode_id}
        assert row["original_report"] == expected
        assert row["inputs"]["repeat_index"] == slot_index // 3
    assert saved["status"] == ("INCOMPLETE" if fail_at else "COMPLETED")
    assert result == (1 if fail_at else 0)
    if fail_at:
        assert all(slot["status"] == "NOT_ATTEMPTED" for slot in saved["slots"][fail_at:])
        assert saved["evaluation"]["status"] == "pending"
    else:
        assert saved["summary"]["counts"]["violations"] == 15
        assert saved["evaluation"]["status"] == "weave_verified"

import asyncio
from types import SimpleNamespace

import pytest

from app.telemetry.evaluations import EvaluationPublisher
from app.telemetry.outbox import TelemetryOutbox
from app.telemetry.safety import TelemetryError
from app.telemetry.worker import SDKHandler
from app.config import Settings


SCORES = {f"C{i}": i != 3 for i in range(1, 9)}


def test_installed_evaluation_logger_explicit_summary_envelope():
    from weave import EvaluationLogger
    saved = []
    # Exercise the installed SDK method itself, replacing only storage sinks.
    logger = object.__new__(EvaluationLogger)
    logger._is_finalized = False
    logger._evaluate_call = SimpleNamespace(id="offline-fixture")
    logger._eval_meta = {}
    logger._pseudo_evaluation = SimpleNamespace(summarize=lambda: None)
    logger._finalize_evaluation = lambda *, output: saved.append(output)
    summary = {"attempted": 3, "violations": 1, "lab_errors": 0}
    logger.log_summary(summary, auto_summarize=False)
    assert saved == [{**summary, "output": summary}]


def test_initialization_before_model_original_scores_before_summary(worker, store, metadata):
    report = {"shipping_status": "UNKNOWN", "original": True}
    async def run():
        session = await EvaluationPublisher(worker, TelemetryOutbox(store)).begin("batch", metadata, expected_episode_ids=["episode"])
        assert worker.commands[0][0] == "evaluation_init"
        worker.commands.append(("fixture_model_call", {}, 0))
        await session.record_prediction("episode", inputs={"task": "fixture"}, original_report=report, persisted_scores=SCORES)
        result = await session.finish({"attempted": 1, "violation": 1, "triggered": 1, "lab_error": 0})
        assert result["status"] == "weave_verified"
    asyncio.run(run())
    assert [c for c, _, _ in worker.commands] == ["evaluation_init", "fixture_model_call", "prediction", "evaluation_summary"]
    assert worker.commands[2][1]["scores"] == SCORES and worker.commands[2][1]["report"] == report


@pytest.mark.parametrize("split,purpose,frozen,allowed", [
    ("promotion", "promotion", False, False), ("final_audit", "final_audit", False, False),
    ("final_audit", "final_audit", True, True)])
def test_full_batch_capture_gate(worker, store, metadata, split, purpose, frozen, allowed):
    metadata.update(split=split, experiment_purpose=purpose, origin="faultlab_evaluation")
    async def run():
        session = await EvaluationPublisher(worker, TelemetryOutbox(store)).begin("batch", metadata, expected_episode_ids=["e"], frozen=frozen)
        await session.record_prediction("e", inputs={}, original_report={"unaltered": True}, persisted_scores=SCORES)
        await session.finish({"attempted": 1})
    asyncio.run(run())
    assert bool(worker.commands) is allowed
    assert len(store.list_records("telemetry_predictions")) == 1


def test_incomplete_or_changed_prediction_cannot_finish(worker, store, metadata):
    async def run():
        session = await EvaluationPublisher(worker, TelemetryOutbox(store)).begin("batch", metadata, expected_episode_ids=["e", "missing"])
        await session.record_prediction("e", inputs={}, original_report={"original": True}, persisted_scores=SCORES)
        with pytest.raises(TelemetryError):
            await session.record_prediction("e", inputs={}, original_report={"repaired": True}, persisted_scores=SCORES)
        with pytest.raises(TelemetryError):
            await session.finish({"attempted": 1})
        with pytest.raises(TelemetryError):
            await session.record_prediction("missing", inputs={"audit_manifest": {}}, original_report={}, persisted_scores=SCORES)
    asyncio.run(run())
    assert "evaluation_summary" not in [x[0] for x in worker.commands]


def test_late_sync_retries_only_stored_predictions(worker, store, metadata):
    worker.fail = True
    async def run():
        session = await EvaluationPublisher(worker, TelemetryOutbox(store)).begin("batch", metadata, expected_episode_ids=["e"])
        await session.record_prediction("e", inputs={}, original_report={}, persisted_scores=SCORES)
        assert (await session.finish({"attempted": 1}))["status"] == "weave_pending"
        worker.fail = False
        assert (await session.retry())["status"] == "weave_verified"
    asyncio.run(run())
    assert all(x[0] in {"evaluation_init", "prediction", "evaluation_summary"} for x in worker.commands)


def test_real_sdk_handler_finishes_scores_before_summary():
    events = []
    call = SimpleNamespace(id="fixture", ui_url="https://wandb.ai/fixture/project/call/eval")
    prediction_call = SimpleNamespace(id="fixture-prediction", ui_url="https://wandb.ai/fixture/project/call/prediction")
    class Prediction:
        predict_and_score_call = prediction_call
        def log_score(self, *, scorer, score): events.append(("score", scorer, score))
        def finish(self): events.append(("finish",))
    class Logger:
        _evaluate_call = call
        def __init__(self, **kwargs): events.append(("initialize",))
        def log_prediction(self, *, inputs, output):
            events.append(("prediction", output))
            return Prediction()
        def log_summary(self, summary, *, auto_summarize): events.append(("summary", summary, auto_summarize))
    def readback(call_id, **kwargs):
        output = {"attempted": 1, "output": {"attempted": 1}} if call_id == "fixture" else {"output": {"original": True}, "scores": SCORES}
        return SimpleNamespace(id=call_id, project_id="fixture/project", ended_at="now", output=output)
    client = SimpleNamespace(flush=lambda: None, get_call=readback)
    handler = SDKHandler(Settings(wandb_entity="fixture", wandb_project="project"), SimpleNamespace(EvaluationLogger=Logger), client)
    handler.handle("evaluation_init", {"batch_id": "b", "name": "b", "model_id": "model", "metadata": {}})
    handler.handle("prediction", {"batch_id": "b", "inputs": {}, "report": {"original": True}, "scores": SCORES})
    handler.handle("evaluation_summary", {"batch_id": "b", "summary": {"attempted": 1}})
    assert [e[0] for e in events] == ["initialize", "prediction"] + ["score"] * 8 + ["finish", "summary"]
    assert events[-1][2] is False

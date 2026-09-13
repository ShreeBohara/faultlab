"""Offline sponsor doubles; no fixture constitutes live sponsor evidence."""
import copy
import pytest


class MemoryStore:
    def __init__(self):
        self.records = {}
    def get_record(self, kind, record_id):
        return copy.deepcopy(self.records.get((kind, record_id)))
    def put_record(self, kind, record_id, payload, *, immutable=False):
        existing = self.records.get((kind, record_id))
        if immutable and existing is not None and existing != payload:
            raise ValueError("Immutable record conflict")
        self.records[kind, record_id] = copy.deepcopy(payload)
    def list_records(self, kind):
        return [copy.deepcopy(v) for (k, _), v in self.records.items() if k == kind]


class FakeWorker:
    def __init__(self):
        self.commands = []
        self.calls = []
        self.fail = False
    async def request(self, command, payload, *, timeout_seconds=20):
        self.commands.append((command, copy.deepcopy(payload), timeout_seconds))
        if self.fail:
            raise RuntimeError("fixture SDK outage")
        if command == "start_call":
            return {"id": payload["call_id"], "url": "https://wandb.ai/fixture/project/call/root"}
        if command == "get_calls":
            return self.calls
        if command in {"prediction", "evaluation_summary"}:
            return {"id": "fixture-evaluation", "url": "https://wandb.ai/fixture/project/call/evaluation", "verified": True}
        if command == "dataset":
            return {"ref": "weave:///fixture/project/object/regressions:" + "a" * 64, "verified": True}
        if command == "campaign_bridge":
            return {"run_id": payload["run_id"], "url": "https://wandb.ai/fixture/project/runs/" + payload["run_id"]}
        return {}


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def worker():
    return FakeWorker()


@pytest.fixture
def metadata():
    return {"campaign_id": "fixture-campaign", "episode_id": "fixture-episode", "execution_epoch": 0,
            "origin": "prototype", "arm": "B0", "split": "development", "source_mode": "live",
            "model_id": "fixture-model", "policy_hash": "a" * 64, "contract_hash": "b" * 64,
            "scorer_hash": "c" * 64, "experiment_purpose": "discovery", "trial_index": 0,
            "agent_registration_id": "orders-v1", "study_id": "fixture-study", "evidence_context_id": "fixture-context"}

import asyncio

import pytest

from app.telemetry.datasets import DatasetPublisher
from app.telemetry.outbox import TelemetryOutbox
from app.telemetry.safety import TelemetryError, immutable_weave_ref


def test_dataset_immutable_reference_and_duplicate_publication(worker, store):
    publisher = DatasetPublisher(worker, TelemetryOutbox(store), "fixture/project")
    kwargs = {"name": "fixture-regression", "rows": [{"episode_id": "e", "split": "development", "source_mode": "live"}],
              "regression_hash": "a" * 64, "source_episode_ids": ["e"], "authorize": lambda e: e == "e"}
    async def run():
        first = await publisher.publish("regression", **kwargs)
        second = await publisher.publish("regression", **kwargs)
        assert first["state"] == second["state"] == "VERIFIED"
        assert first["remote_ref"].endswith("a" * 64)
    asyncio.run(run())
    assert len(worker.commands) == 1


@pytest.mark.parametrize("mutation", [{"split": "promotion"}, {"private_snapshot": {}}, {"source_mode": "offline_fixture"},
                                       {"experiment_purpose": "selection_comparison"}])
def test_dataset_rejects_hidden_or_wrong_split_before_call(worker, store, mutation):
    row = {"episode_id": "e", "split": "development", "source_mode": "live", **mutation}
    with pytest.raises(TelemetryError):
        asyncio.run(DatasetPublisher(worker, TelemetryOutbox(store), "fixture/project").publish("r", name="r", rows=[row],
            regression_hash="a" * 64, source_episode_ids=["e"], authorize=lambda _: True))
    assert worker.commands == []


@pytest.mark.parametrize("ref", ["weave:///fixture/project/object/data:latest", "weave:///other/project/object/data:" + "a" * 64,
                                  "https://wandb.ai/fixture/project"])
def test_unpinned_or_foreign_dataset_ref_rejected(ref):
    with pytest.raises(TelemetryError):
        immutable_weave_ref(ref, "fixture/project")

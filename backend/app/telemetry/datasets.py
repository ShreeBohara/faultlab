"""Versioned, sanitized development regression publication."""

from app.telemetry.safety import TelemetryError, immutable_weave_ref, public_json


class DatasetPublisher:
    def __init__(self, worker, outbox, project: str):
        self.worker, self.outbox, self.project = worker, outbox, project

    async def publish(self, regression_id: str, *, name: str, rows: list[dict], regression_hash: str,
                      source_episode_ids: list[str], authorize):
        if not rows or len(rows) > 200 or not source_episode_ids or not all(authorize(e) for e in source_episode_ids):
            raise TelemetryError("Dataset requires authorized development episodes.")
        clean = public_json(rows)
        for row in clean:
            if row.get("split") != "development" or row.get("source_mode") != "live" or row.get("episode_id") not in source_episode_ids:
                raise TelemetryError("Dataset row is not live development evidence.")
            if row.get("experiment_purpose") in {"selection_comparison", "portability", "final_audit", "promotion"}:
                raise TelemetryError("Study evidence cannot enter the campaign dataset.")
        payload = {"name": name, "rows": clean, "regression_hash": regression_hash, "source_episode_ids": source_episode_ids}
        job = self.outbox.enqueue("dataset", regression_id, payload)
        async def upload(saved):
            if not all(authorize(e) for e in saved["source_episode_ids"]):
                raise TelemetryError("Dataset source authorization expired.")
            result = await self.worker.request("dataset", saved, timeout_seconds=60)
            if result.get("verified") is not True:
                raise TelemetryError("Dataset remote persistence is unverified.")
            return immutable_weave_ref(result["ref"], self.project)
        return await self.outbox.deliver(job["outbox_id"], upload)

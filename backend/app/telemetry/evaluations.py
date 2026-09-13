"""Mirror persisted fixed scores through the actual EvaluationLogger lifecycle."""

from app.telemetry.safety import TelemetryError, capture_allowed, digest, public_json, utc_now, wandb_url


class EvaluationPublisher:
    def __init__(self, worker, outbox):
        self.worker, self.outbox = worker, outbox

    async def begin(self, batch_id: str, metadata, *, expected_episode_ids: list[str], frozen: bool = False):
        metadata = public_json(metadata)
        if not expected_episode_ids or len(set(expected_episode_ids)) != len(expected_episode_ids):
            raise TelemetryError("Evaluation episode inventory is missing or duplicated.")
        payload = {"batch_id": batch_id, "metadata": metadata, "expected_episode_ids": expected_episode_ids,
                   "frozen": frozen, "created_at": utc_now()}
        existing = self.outbox.store.get_record("telemetry_evaluations", batch_id)
        if existing:
            if any(existing[k] != payload[k] for k in ("metadata", "expected_episode_ids", "frozen")):
                raise TelemetryError("Evaluation identity conflicts with frozen lineage.")
        else:
            self.outbox.store.put_record("telemetry_evaluations", batch_id, payload, immutable=True)
        session = EvaluationSession(self.worker, self.outbox, payload)
        if session.allowed:
            try:
                await session.initialize_remote()
            except Exception:
                session.remote_available = False
        return session


class EvaluationSession:
    def __init__(self, worker, outbox, batch):
        self.worker, self.outbox, self.batch = worker, outbox, batch
        self.batch_id = batch["batch_id"]
        self.allowed = capture_allowed(batch["metadata"], frozen=batch["frozen"])
        self.remote_available = False
        self.finished = False
        self.prediction_refs = {}

    async def initialize_remote(self):
        if not self.allowed:
            return
        await self.worker.request("evaluation_init", {"batch_id": self.batch_id, "name": f"faultlab-{self.batch_id}",
                                  "model_id": self.batch["metadata"]["model_id"], "metadata": self.batch["metadata"]})
        self.remote_available = True

    async def record_prediction(self, episode_id: str, *, inputs, original_report, persisted_scores: dict):
        if self.finished or episode_id not in self.batch["expected_episode_ids"]:
            raise TelemetryError("Prediction is not in this unfinished evaluation.")
        if set(persisted_scores) != {f"C{i}" for i in range(1, 9)}:
            raise TelemetryError("All eight persisted fixed scores are required.")
        row = public_json({"batch_id": self.batch_id, "episode_id": episode_id, "inputs": inputs,
                           "report": original_report, "scores": persisted_scores})
        key = f"{self.batch_id}:{episode_id}"
        previous = self.outbox.store.get_record("telemetry_predictions", key)
        if previous:
            if previous != row:
                raise TelemetryError("A prediction cannot be rewritten after recording.")
            return
        self.outbox.store.put_record("telemetry_predictions", key, row, immutable=True)
        if self.allowed and self.remote_available:
            try:
                self.prediction_refs[episode_id] = await self.worker.request("prediction", row)
            except Exception:
                self.remote_available = False

    async def finish(self, persisted_summary: dict):
        rows = [self.outbox.store.get_record("telemetry_predictions", f"{self.batch_id}:{episode}")
                for episode in self.batch["expected_episode_ids"]]
        if any(row is None for row in rows):
            raise TelemetryError("An incomplete evaluation cannot publish a finished summary.")
        summary = public_json(persisted_summary)
        previous = self.outbox.store.get_record("telemetry_summaries", self.batch_id)
        if previous is not None and previous != summary:
            raise TelemetryError("The persisted evaluation summary is immutable.")
        self.outbox.store.put_record("telemetry_summaries", self.batch_id, summary, immutable=True)
        self.finished = True
        if not self.allowed:
            return {"status": "local_only", "remote_ref": None}
        job = self.outbox.enqueue("evaluation", self.batch_id, {"batch": self.batch, "rows": rows, "summary": summary})
        if not self.remote_available:
            return {"status": "weave_pending", "remote_ref": None, "outbox_id": job["outbox_id"]}
        try:
            result = await self.worker.request("evaluation_summary", {"batch_id": self.batch_id, "summary": summary}, timeout_seconds=60)
            if result.get("verified") is not True:
                raise TelemetryError("Evaluation reference is unverified.")
            ref = wandb_url(result["url"])
            self.outbox.update(job["outbox_id"], state="VERIFIED", remote_ref=ref)
            return {"status": "weave_verified", "remote_ref": ref, "id": result["id"]}
        except Exception:
            self.outbox.update(job["outbox_id"], state="ERROR", error_code="EVALUATION_UNSYNCED")
            return {"status": "weave_pending", "remote_ref": None, "outbox_id": job["outbox_id"]}

    async def retry(self):
        """Publish stored rows only, with no actor/model callback or score recomputation."""
        if not self.allowed or not self.finished:
            raise TelemetryError("Evaluation is not eligible for evidence-only synchronization.")
        await self.initialize_remote()
        for episode in self.batch["expected_episode_ids"]:
            row = self.outbox.store.get_record("telemetry_predictions", f"{self.batch_id}:{episode}")
            if episode not in self.prediction_refs:
                self.prediction_refs[episode] = await self.worker.request("prediction", row)
        return await self.finish(self.outbox.store.get_record("telemetry_summaries", self.batch_id))

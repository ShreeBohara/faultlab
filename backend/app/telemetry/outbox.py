"""Durable telemetry jobs using the lab-owned repository boundary."""

import asyncio
from typing import Protocol

from app.telemetry.safety import TelemetryError, digest, public_json, utc_now


class RecordStore(Protocol):
    def get_record(self, kind: str, record_id: str) -> dict | None: ...
    def put_record(self, kind: str, record_id: str, payload: dict, *, immutable: bool = False): ...
    def list_records(self, kind: str) -> list[dict]: ...


class TelemetryOutbox:
    def __init__(self, store: RecordStore):
        self.store = store
        self._lock = asyncio.Lock()

    def enqueue(self, kind: str, record_ref: str, payload: dict) -> dict:
        if kind not in {"trace", "evaluation", "dataset", "campaign"}:
            raise TelemetryError("Unknown telemetry record kind.")
        clean = public_json(payload)
        key = f"{kind}:{record_ref}"
        existing = self.store.get_record("telemetry_outbox", key)
        payload_digest = digest(clean)
        if existing:
            if existing["payload_digest"] != payload_digest:
                raise TelemetryError("Telemetry identity conflicts with immutable payload.")
            return existing
        record = {"outbox_id": key, "record_kind": kind, "record_ref": record_ref, "payload": clean,
                  "payload_digest": payload_digest, "state": "PENDING", "attempts": 0,
                  "remote_ref": None, "error_code": None, "updated_at": utc_now()}
        self.store.put_record("telemetry_outbox", key, record)
        return record

    def update(self, key: str, **changes) -> dict:
        record = self.store.get_record("telemetry_outbox", key)
        if record is None:
            raise TelemetryError("Unknown telemetry job.")
        record.update(changes, updated_at=utc_now())
        self.store.put_record("telemetry_outbox", key, record)
        return record

    async def deliver(self, key: str, publisher) -> dict:
        """Publisher accepts stored public payload only; business callbacks are absent."""
        async with self._lock:
            record = self.store.get_record("telemetry_outbox", key)
            if not record:
                raise TelemetryError("Unknown telemetry job.")
            if record["state"] == "VERIFIED":
                return record
            self.update(key, state="UPLOADING", attempts=record["attempts"] + 1, error_code=None)
            try:
                ref = await publisher(record["payload"])
                if not isinstance(ref, str) or not ref:
                    raise TelemetryError("Publisher returned no verified reference.")
                return self.update(key, state="VERIFIED", remote_ref=ref)
            except asyncio.CancelledError:
                self.update(key, state="PENDING", error_code="INTERRUPTED")
                raise
            except Exception:
                return self.update(key, state="ERROR", error_code="TELEMETRY_UNAVAILABLE")

    def recover_pending(self):
        for record in self.store.list_records("telemetry_outbox"):
            if record["state"] == "UPLOADING":
                self.update(record["outbox_id"], state="PENDING", error_code="INTERRUPTED")

"""The typed trial store (plan phase 1.5): plans, attempts and sealed envelopes in one SQLite file.

Every record is a validated model on the way in and on the way out. Plans are content-addressed
and immutable; an attempt's lifecycle only moves forward (CREATED, READY, RUNNING, SETTLING,
TERMINAL); an envelope is written once, re-validated when read, and its attempt record becomes
the envelope's own. ``claim`` hands a READY attempt to exactly one worker in one transaction, and
``recover`` closes the attempts a dead worker left open without ever inventing their evidence.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from threading import RLock

from faultlab.core.canonical import canonical_json
from faultlab.core.clock import utc_now_text
from faultlab.core.errors import FaultLabError, IntegrityError
from faultlab.evidence.bundles import write_bundle
from faultlab.evidence.models import TrialAttempt, TrialEnvelope, TrialPlan, plan_hash, validate_structure

LIFECYCLES = ("CREATED", "READY", "RUNNING", "SETTLING", "TERMINAL")
RECOVERY_REASON = "INTERRUPTED_BY_WORKER_RESTART"


class StoreConflict(FaultLabError, ValueError):
    """A write the store refuses: an unknown plan, a backwards lifecycle, a changed immutable record."""


class TrialStore:
    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA busy_timeout=5000")
        if self.path != ":memory:":
            self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS plans(plan_hash TEXT PRIMARY KEY, value TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS batches(batch_id TEXT PRIMARY KEY, value TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts(attempt_id TEXT PRIMARY KEY, plan_hash TEXT NOT NULL REFERENCES plans(plan_hash),
                batch_id TEXT, position INTEGER NOT NULL, lifecycle TEXT NOT NULL, worker TEXT, value TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS attempts_batch ON attempts(batch_id, position);
            CREATE TABLE IF NOT EXISTS envelopes(attempt_id TEXT PRIMARY KEY REFERENCES attempts(attempt_id), digest TEXT NOT NULL,
                value TEXT NOT NULL, created_at TEXT NOT NULL);
        """)
        for table in ("plans", "envelopes"):
            for action in ("UPDATE", "DELETE"):
                self.db.execute(f"CREATE TRIGGER IF NOT EXISTS no_{action.lower()}_{table} BEFORE {action} ON {table} "
                                "BEGIN SELECT RAISE(ABORT,'immutable record'); END")

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @contextmanager
    def transaction(self):
        with self._lock:
            nested = self.db.in_transaction
            if not nested:
                self.db.execute("BEGIN IMMEDIATE")
            try:
                yield self.db
                if not nested:
                    self.db.execute("COMMIT")
            except BaseException:
                if not nested and self.db.in_transaction:
                    self.db.execute("ROLLBACK")
                raise

    # -- plans ----------------------------------------------------------------------------------

    def put_plan(self, plan: TrialPlan) -> str:
        digest = plan_hash(plan)
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM plans WHERE plan_hash=?", (digest,)).fetchone() is None:
                db.execute("INSERT INTO plans VALUES (?,?,?)", (digest, canonical_json(plan), utc_now_text()))
        return digest

    def plan(self, digest: str) -> TrialPlan:
        row = self.db.execute("SELECT value FROM plans WHERE plan_hash=?", (digest,)).fetchone()
        if row is None:
            raise StoreConflict(f"Unknown plan {digest}")
        plan = TrialPlan.model_validate(json.loads(row["value"]))
        if plan_hash(plan) != digest:
            raise IntegrityError("Stored plan does not match its hash")
        return plan

    def plans(self) -> list[TrialPlan]:
        return [self.plan(row["plan_hash"]) for row in self.db.execute("SELECT plan_hash FROM plans ORDER BY rowid")]

    # -- batches --------------------------------------------------------------------------------

    def put_batch(self, batch_id: str, value: dict) -> None:
        with self.transaction() as db:
            db.execute("INSERT INTO batches VALUES (?,?,?) ON CONFLICT(batch_id) DO UPDATE SET value=excluded.value",
                       (batch_id, canonical_json(value), utc_now_text()))

    def batch(self, batch_id: str) -> dict:
        row = self.db.execute("SELECT value FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
        if row is None:
            raise StoreConflict(f"Unknown batch {batch_id}")
        return json.loads(row["value"])

    def batches(self) -> list[dict]:
        return [json.loads(row["value"]) for row in self.db.execute("SELECT value FROM batches ORDER BY rowid")]

    # -- attempts -------------------------------------------------------------------------------

    def put_attempt(self, attempt: TrialAttempt, *, batch_id: str | None = None, position: int | None = None,
                    worker: str | None = None) -> TrialAttempt:
        """Insert or advance an attempt; the lifecycle never moves backwards and the plan never changes."""
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM plans WHERE plan_hash=?", (attempt.plan_hash,)).fetchone() is None:
                raise StoreConflict("An attempt names a plan the store does not hold")
            now = utc_now_text()
            row = db.execute("SELECT plan_hash, lifecycle, batch_id, position, worker FROM attempts WHERE attempt_id=?",
                             (attempt.attempt_id,)).fetchone()
            if row is None:
                db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?)",
                           (attempt.attempt_id, attempt.plan_hash, batch_id, position if position is not None else 0,
                            attempt.lifecycle, worker, canonical_json(attempt), now, now))
                return attempt
            if row["plan_hash"] != attempt.plan_hash:
                raise StoreConflict("An attempt's plan cannot change")
            if LIFECYCLES.index(attempt.lifecycle) < LIFECYCLES.index(row["lifecycle"]):
                raise StoreConflict(f"Lifecycle cannot move from {row['lifecycle']} back to {attempt.lifecycle}")
            if db.execute("SELECT 1 FROM envelopes WHERE attempt_id=?", (attempt.attempt_id,)).fetchone() is not None:
                raise StoreConflict("An attempt with a sealed envelope is final")
            db.execute("UPDATE attempts SET lifecycle=?, value=?, updated_at=?, worker=COALESCE(?, worker) WHERE attempt_id=?",
                       (attempt.lifecycle, canonical_json(attempt), now, worker, attempt.attempt_id))
            return attempt

    def attempt(self, attempt_id: str) -> TrialAttempt:
        row = self.db.execute("SELECT value FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
        if row is None:
            raise StoreConflict(f"Unknown attempt {attempt_id}")
        return TrialAttempt.model_validate(json.loads(row["value"]))

    def attempt_batch(self, attempt_id: str) -> str | None:
        row = self.db.execute("SELECT batch_id FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
        return None if row is None else row["batch_id"]

    def attempts(self, *, batch_id: str | None = None, lifecycle: str | None = None) -> list[TrialAttempt]:
        clauses, parameters = [], []
        if batch_id is not None:
            clauses.append("batch_id=?")
            parameters.append(batch_id)
        if lifecycle is not None:
            clauses.append("lifecycle=?")
            parameters.append(lifecycle)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self.db.execute(f"SELECT value FROM attempts{where} ORDER BY position, rowid", parameters)
        return [TrialAttempt.model_validate(json.loads(row["value"])) for row in rows]

    def claim(self, worker: str, *, batch_id: str | None = None) -> TrialAttempt | None:
        """Move the first READY attempt (by position) to RUNNING for this worker, atomically."""
        with self.transaction() as db:
            clause = " AND batch_id=?" if batch_id is not None else ""
            parameters = (batch_id,) if batch_id is not None else ()
            row = db.execute(f"SELECT value FROM attempts WHERE lifecycle='READY'{clause} ORDER BY position, rowid LIMIT 1",
                             parameters).fetchone()
            if row is None:
                return None
            attempt = TrialAttempt.model_validate(json.loads(row["value"]))
            running = attempt.model_copy(update={"lifecycle": "RUNNING", "started_at": utc_now_text()})
            return self.put_attempt(running, worker=worker)

    def recover(self, *, reason: str = RECOVERY_REASON) -> list[str]:
        """Close every RUNNING or SETTLING attempt as TERMINAL with the reason; no evidence is invented."""
        closed = []
        with self.transaction() as db:
            rows = db.execute("SELECT value FROM attempts WHERE lifecycle IN ('RUNNING','SETTLING') ORDER BY position, rowid").fetchall()
            for row in rows:
                attempt = TrialAttempt.model_validate(json.loads(row["value"]))
                self.put_attempt(attempt.model_copy(update={"lifecycle": "TERMINAL", "terminal_reason": reason[:600],
                                                            "ended_at": utc_now_text()}))
                closed.append(attempt.attempt_id)
        return closed

    # -- envelopes ------------------------------------------------------------------------------

    def put_envelope(self, envelope: TrialEnvelope) -> TrialEnvelope:
        """Seal-check and store an envelope once; the attempt record becomes the envelope's attempt."""
        envelope = validate_structure(envelope)
        attempt = envelope.attempt
        if attempt.lifecycle != "TERMINAL":
            raise StoreConflict("Only a terminal attempt carries an envelope")
        with self.transaction() as db:
            row = db.execute("SELECT plan_hash FROM attempts WHERE attempt_id=?", (attempt.attempt_id,)).fetchone()
            if row is None:
                raise StoreConflict("An envelope names an attempt the store does not hold")
            if row["plan_hash"] != attempt.plan_hash or plan_hash(envelope.plan) != attempt.plan_hash:
                raise StoreConflict("Envelope plan does not match the stored attempt's plan")
            existing = db.execute("SELECT digest FROM envelopes WHERE attempt_id=?", (attempt.attempt_id,)).fetchone()
            if existing is not None:
                if existing["digest"] != envelope.digest:
                    raise StoreConflict("An attempt's envelope cannot change")
                return envelope
            self.put_attempt(attempt)
            db.execute("INSERT INTO envelopes VALUES (?,?,?,?)",
                       (attempt.attempt_id, envelope.digest, canonical_json(envelope), utc_now_text()))
        return envelope

    def envelope(self, attempt_id: str) -> TrialEnvelope:
        row = self.db.execute("SELECT value, digest FROM envelopes WHERE attempt_id=?", (attempt_id,)).fetchone()
        if row is None:
            raise StoreConflict(f"No envelope for attempt {attempt_id}")
        envelope = validate_structure(json.loads(row["value"]))
        if envelope.digest != row["digest"]:
            raise IntegrityError("Stored envelope digest changed")
        return envelope

    def envelopes(self, *, batch_id: str | None = None) -> list[TrialEnvelope]:
        clause = " WHERE a.batch_id=?" if batch_id is not None else ""
        parameters = (batch_id,) if batch_id is not None else ()
        rows = self.db.execute("SELECT e.attempt_id FROM envelopes e JOIN attempts a ON a.attempt_id=e.attempt_id"
                               f"{clause} ORDER BY a.position, a.rowid", parameters).fetchall()
        return [self.envelope(row["attempt_id"]) for row in rows]

    def export_bundle(self, path, *, name: str, batch_id: str | None = None, notes=None):
        return write_bundle(self.envelopes(batch_id=batch_id), path, name=name, notes=notes)

    # -- accounting -----------------------------------------------------------------------------

    def spent(self, *, batch_id: str | None = None) -> dict:
        """Measured cost of the sealed envelopes plus the reserved bound of every open attempt."""
        measured = {"dollars": 0.0, "model_calls": 0, "http_attempts": 0, "input_tokens": 0, "output_tokens": 0, "envelopes": 0}
        reserved = {"dollars": 0.0, "model_calls": 0, "open_attempts": 0, "unbounded": 0}
        for envelope in self.envelopes(batch_id=batch_id):
            cost = envelope.outcome.cost
            measured["envelopes"] += 1
            measured["model_calls"] += cost.model_calls
            measured["http_attempts"] += cost.http_attempts
            measured["input_tokens"] += cost.input_tokens
            measured["output_tokens"] += cost.output_tokens
            # An envelope whose dollars were not measured counts at its reserved bound, never at zero.
            measured["dollars"] += cost.dollars_measured if cost.dollars_measured is not None else (cost.dollars_reserved or 0.0)
        for attempt in self.attempts(batch_id=batch_id):
            if attempt.lifecycle in ("RUNNING", "SETTLING"):
                caps = self.plan(attempt.plan_hash).caps
                reserved["open_attempts"] += 1
                if caps.dollars is None:
                    reserved["unbounded"] += 1
                else:
                    reserved["dollars"] += caps.dollars
                reserved["model_calls"] += caps.model_calls or 0
        return {"measured": measured, "reserved": reserved}

    def summary(self, *, batch_id: str | None = None) -> dict:
        lifecycles: dict[str, int] = {}
        for attempt in self.attempts(batch_id=batch_id):
            lifecycles[attempt.lifecycle] = lifecycles.get(attempt.lifecycle, 0) + 1
        executions: dict[str, int] = {}
        tasks: dict[str, int] = {}
        for envelope in self.envelopes(batch_id=batch_id):
            executions[envelope.outcome.execution] = executions.get(envelope.outcome.execution, 0) + 1
            tasks[str(envelope.outcome.task)] = tasks.get(str(envelope.outcome.task), 0) + 1
        return {"store": self.path, "batch_id": batch_id, "plans": len(self.plans()), "attempts": lifecycles,
                "executions": executions, "tasks": tasks, "spent": self.spent(batch_id=batch_id)}


__all__ = ["LIFECYCLES", "RECOVERY_REASON", "StoreConflict", "TrialStore"]

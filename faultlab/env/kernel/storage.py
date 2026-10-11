"""One SQLite database per world. Transactions serialize the clock and every effect.

The state row is an atomic aggregate; the ``events`` table and the handler's history tables
are append-only, protected by SQL triggers. No database path is public, and a world is only
reachable with the capability returned at creation.
"""

from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import sqlite3
from threading import RLock

from faultlab.core.canonical import canonical_json, content_hash
from faultlab.core.clock import utc_now_text
from faultlab.core.ids import new_id
from faultlab.env.kernel.errors import WorldError

SCHEMA_VERSION = "faultlab/v1"


def event(state: dict, event_type: str, payload: dict | None = None, call_id: str | None = None) -> dict:
    """Append one evaluator-private event to the world's log and return it."""
    value = {"schema_version": SCHEMA_VERSION, "episode_id": state["episode_id"], "seq": len(state["events"]) + 1,
             "tick": state["tick"], "at": utc_now_text(), "role": "coordinator", "type": event_type,
             "payload": payload or {}, "call_id": call_id, "evidence_id": None, "visibility": "PRIVATE_EVALUATOR"}
    state["events"].append(value)
    return value


class WorldStore:
    def __init__(self, directory, handler):
        self.directory = Path(directory)
        self.handler = handler
        self._lock = RLock()

    def _path(self, world_id):
        if not isinstance(world_id, str) or not world_id.startswith("world-") or not world_id[6:].isalnum():
            raise WorldError("WORLD_NOT_FOUND", 404)
        return self.directory / (world_id + ".sqlite3")

    def create(self, episode_id: str, intent: dict, fault_spec: dict, fixture_id: str) -> dict:
        from faultlab.env.kernel.faults import FaultSpec, initial_executions
        intent = self.handler.validate_intent(intent)
        if fixture_id not in self.handler.fixtures:
            raise WorldError("UNKNOWN_FIXTURE", 422)
        pack_state = self.handler.initial_state(intent, fixture_id)
        try:
            spec = FaultSpec.model_validate(fault_spec).model_dump(mode="json")
        except ValueError as error:
            raise WorldError("INVALID_FAULT_SPEC", 422) from error
        world_id = new_id("world")
        capability = secrets.token_urlsafe(32)
        state = {"world_id": world_id, "episode_id": episode_id, "capability_hash": content_hash(capability),
                 "intent": intent, "fixture_id": fixture_id, "tick": 0, "attempts": 0, "waits": 0, "stopped": False,
                 "decision_tick": None, "horizon_done": False, "events": [], "occurrences": {},
                 "fault_spec": spec, "fault_executions": initial_executions(spec), "pack": pack_state}
        self.handler.validate_schedule(spec, state)
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(world_id)
        with sqlite3.connect(path) as db:
            db.executescript("CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);"
                             "CREATE TABLE events(seq INTEGER PRIMARY KEY, value TEXT NOT NULL);")
            for table in self.handler.history_tables:
                db.execute(f'CREATE TABLE "{table}"(key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            for table in ("events", *self.handler.history_tables):
                for action in ("UPDATE", "DELETE"):
                    db.execute(f'CREATE TRIGGER no_{action.lower()}_{table} BEFORE {action} ON "{table}" '
                               "BEGIN SELECT RAISE(ABORT,'immutable history'); END")
            self._persist(db, state)
        path.chmod(0o600)
        return {"world_id": world_id, "capability": capability, "tick": 0}

    def _persist(self, db, state):
        db.execute("INSERT INTO state(id,value) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",
                   (canonical_json(state),))
        for item in state["events"]:
            db.execute("INSERT OR IGNORE INTO events VALUES(?,?)", (item["seq"], canonical_json(item)))
        for table, rows in self.handler.histories(state).items():
            for key, value in rows:
                db.execute(f'INSERT OR IGNORE INTO "{table}" VALUES(?,?)', (str(key), canonical_json(value)))

    @contextmanager
    def transaction(self, world_id):
        path = self._path(world_id)
        if not path.exists():
            raise WorldError("WORLD_NOT_FOUND", 404)
        with self._lock, sqlite3.connect(path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            state = json.loads(db.execute("SELECT value FROM state WHERE id=1").fetchone()[0])
            yield state
            self._persist(db, state)

    def read(self, world_id):
        path = self._path(world_id)
        if not path.exists():
            raise WorldError("WORLD_NOT_FOUND", 404)
        with sqlite3.connect(path) as db:
            return json.loads(db.execute("SELECT value FROM state WHERE id=1").fetchone()[0])

    def snapshot(self, world_id):
        return self.handler.snapshot(self.read(world_id))

    def authorize(self, world_id, capability):
        state = self.read(world_id)
        if not capability or not secrets.compare_digest(state["capability_hash"], content_hash(capability)):
            raise WorldError("FORBIDDEN", 403)

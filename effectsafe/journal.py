"""The journal: every dispatch recorded before the wire, exact bytes pinned, outcomes reconciled.

One SQLite file (or ``:memory:``) with three append-only tables. The invariants, taken from the
legacy broker and made task-agnostic:

* an operation's original bytes are pinned by the first ``prepare``; a later ``prepare`` with
  different bytes for the same operation is refused (``Original intent bytes cannot change``);
* an attempt is journalled before the request leaves (``dispatch`` returns the attempt id and
  the exact bytes to send), so a crash between dispatch and delivery leaves the operation
  ``UNKNOWN``, never ``NOT_STARTED``;
* a resend is only ever the pinned bytes; and when the tool contract gives the provider no way to
  recognise the same operation (``identity_scope == "none"``), a resend while any attempt's
  effect is unknown is refused as ``UnsafeResend``: that is how a duplicate effect is prevented
  on a non-idempotent create.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4

from effectsafe.contract import ToolContract
from effectsafe.intent import Intent, derive_key, digest
from effectsafe.outcome import NOT_STARTED, Evidence, OperationState, reconcile


class JournalError(ValueError):
    """A request the journal refuses: changed bytes, an unknown operation, an unsafe resend."""


class UnsafeResend(JournalError):
    """Re-sending could create a second effect: the provider cannot recognise the operation and an
    earlier attempt's effect is unknown."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Journal:
    def __init__(self, path=":memory:", *, namespace: str = "default"):
        self.namespace = namespace
        self._lock = RLock()      # one writer per journal object; BEGIN IMMEDIATE serializes across processes
        self._memory = str(path) == ":memory:"
        if not self._memory:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS operations(operation_id TEXT PRIMARY KEY, action TEXT NOT NULL, scope TEXT NOT NULL,
                intent_hash TEXT NOT NULL, key TEXT, original_bytes TEXT NOT NULL, contract TEXT NOT NULL, state TEXT NOT NULL,
                prepared_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts(attempt_id TEXT PRIMARY KEY, operation_id TEXT NOT NULL, seq INTEGER NOT NULL,
                bytes_digest TEXT NOT NULL, dispatched_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS deliveries(delivery_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL UNIQUE, evidence TEXT NOT NULL,
                received_at TEXT NOT NULL);
        """)
        for table in ("attempts", "deliveries"):
            for action in ("UPDATE", "DELETE"):
                self._db.execute(f"CREATE TRIGGER IF NOT EXISTS no_{action.lower()}_{table} BEFORE {action} ON {table} "
                                 "BEGIN SELECT RAISE(ABORT,'append-only journal'); END")

    def close(self) -> None:
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # -- operations -------------------------------------------------------------------------

    def prepare(self, intent: Intent, contract: ToolContract) -> dict:
        """Pin an operation's identity and exact bytes; idempotent for identical bytes, refused otherwise."""
        key = None
        if contract.kind == "write" and contract.identity_scope == "client_key":
            key = derive_key(self.namespace, intent.intent_hash)
        original = intent.original_bytes(key=key) if contract.key_placement == "field" and key else intent.original_bytes()
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute("SELECT * FROM operations WHERE operation_id=?", (intent.operation_id,)).fetchone()
                if row is not None:
                    if row["original_bytes"] != original:
                        raise JournalError("Original intent bytes cannot change")
                    if row["contract"] != contract.model_dump_json():
                        raise JournalError("An operation's tool contract cannot change")
                    return self._operation(row)
                self._db.execute("INSERT INTO operations VALUES (?,?,?,?,?,?,?,?,?)",
                                 (intent.operation_id, intent.action, intent.scope, intent.intent_hash, key, original,
                                  contract.model_dump_json(), OperationState().model_dump_json(), _now()))
                return self.operation(intent.operation_id)
            finally:
                self._db.execute("COMMIT") if self._db.in_transaction else None

    def operation(self, operation_id: str) -> dict:
        row = self._db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
        if row is None:
            raise JournalError("Unknown operation")
        return self._operation(row)

    def _operation(self, row) -> dict:
        state = OperationState.model_validate_json(row["state"])
        contract = ToolContract.model_validate_json(row["contract"])
        return {"operation_id": row["operation_id"], "action": row["action"], "scope": row["scope"],
                "intent_hash": row["intent_hash"], "key": row["key"], "original_bytes": row["original_bytes"],
                "contract": contract, "state": state}

    def operations(self) -> list[dict]:
        return [self._operation(row) for row in self._db.execute("SELECT * FROM operations ORDER BY prepared_at, operation_id")]

    # -- attempts -----------------------------------------------------------------------------

    def dispatch(self, operation_id: str) -> tuple[str, str]:
        """Journal an attempt and return ``(attempt_id, exact_bytes)``; the caller sends exactly those bytes.

        A second attempt of a write the provider cannot recognise is refused while an earlier
        attempt's effect is unknown; a read, or a keyed write, may always be resent.
        """
        with self._lock:
            # The safety check and the attempt record are one transaction: two concurrent dispatches of a
            # write the provider cannot recognise can never both pass the check.
            self._db.execute("BEGIN IMMEDIATE")
            try:
                operation = self.operation(operation_id)
                contract, state = operation["contract"], operation["state"]
                if contract.kind == "write" and state.attempts and not contract.resend_is_identity_safe and state.effect_possibly_pending:
                    raise UnsafeResend(f"{operation['action']} on {operation['scope']}: an earlier attempt may have taken effect "
                                       f"and the provider cannot recognise a resend (outcome {state.outcome})")
                if contract.kind == "write" and state.outcome in ("SUCCEEDED", "FAILED", "CONFLICT") and not contract.resend_is_identity_safe:
                    raise UnsafeResend(f"{operation['action']} on {operation['scope']} already reached {state.outcome}")
                seq = state.attempts + 1
                attempt_id = f"attempt-{uuid4().hex}"
                state.attempts = seq
                if contract.kind == "write":
                    # From here on, the bytes may reach the provider: the effect is unknown until evidence says otherwise.
                    state.in_flight += 1
                    if state.outcome == NOT_STARTED:
                        state.outcome = "UNKNOWN"
                    state.history.append("dispatched")
                self._db.execute("INSERT INTO attempts VALUES (?,?,?,?,?)",
                                 (attempt_id, operation_id, seq, digest(operation["original_bytes"]), _now()))
                self._db.execute("UPDATE operations SET state=? WHERE operation_id=?", (state.model_dump_json(), operation_id))
                self._db.execute("COMMIT")
                return attempt_id, operation["original_bytes"]
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def deliver(self, attempt_id: str, evidence: Evidence) -> OperationState:
        """Fold what an attempt delivered into the operation's outcome (append-only; monotonic)."""
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute("SELECT operation_id FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
                if row is None:
                    raise JournalError("Unknown attempt")
                if self._db.execute("SELECT 1 FROM deliveries WHERE attempt_id=?", (attempt_id,)).fetchone() is not None:
                    raise JournalError("An attempt delivers exactly once")
                operation = self.operation(row["operation_id"])
                contract, state = operation["contract"], operation["state"]
                if contract.kind == "write":
                    if state.in_flight:
                        state.in_flight -= 1
                    if evidence.error_code and evidence.error_code in contract.errors_proving_no_effect and not evidence.proves_no_effect:
                        evidence = evidence.model_copy(update={"proves_no_effect": True})
                    state = reconcile(state, evidence, terminal_states=contract.terminal_states, pending_states=contract.pending_states)
                else:
                    state.last_status = evidence.status
                    state.history.append(f"read:{evidence.transport}:{evidence.status or evidence.error_code or ''}")
                self._db.execute("INSERT INTO deliveries VALUES (?,?,?,?)",
                                 (f"delivery-{uuid4().hex}", attempt_id, evidence.model_dump_json(), _now()))
                self._db.execute("UPDATE operations SET state=? WHERE operation_id=?", (state.model_dump_json(), operation["operation_id"]))
                self._db.execute("COMMIT")
                return state
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def attempts(self, operation_id: str) -> list[dict]:
        rows = self._db.execute("SELECT * FROM attempts WHERE operation_id=? ORDER BY seq", (operation_id,))
        return [dict(row) for row in rows]

    def deliveries(self, operation_id: str) -> list[dict]:
        rows = self._db.execute("SELECT d.* FROM deliveries d JOIN attempts a ON a.attempt_id=d.attempt_id "
                                "WHERE a.operation_id=? ORDER BY d.received_at, d.delivery_id", (operation_id,))
        return [{**dict(row), "evidence": json.loads(row["evidence"])} for row in rows]

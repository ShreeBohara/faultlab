"""Installed synthetic payment cases and a projection of their persisted facts.

This is a deterministic local service fixture, not LangGraph, HTTP, a model, or
production payment infrastructure. Business intent and provider keys are separate.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import platform
import sqlite3
from typing import Literal
from uuid import uuid4

from pydantic import Field, JsonValue, ValidationError

from .models import (PAYMENTS, Envelope, Identity, IntegrityError, Model, canonical,
                     digest, schema_digest, seal)

CASE_IDS = ("healthy", "reconcile", "blind_retry", "two_intents", "wrong_receipt",
            "payload_conflict", "stopped", "untriggered")
CaseId = Literal["healthy", "reconcile", "blind_retry", "two_intents", "wrong_receipt",
                 "payload_conflict", "stopped", "untriggered"]
FACTS_VERSION = "faultlab-payment-facts/v1"
FAULT_ID = "post-commit-reply-loss"
TABLES = ("intents", "attempts", "effects", "observations", "events", "reports", "faults")
CONTRACT = {
    "version": PAYMENTS,
    "payload": ["invoice_id", "amount_minor", "currency"],
    "binding": "same key and payload returns existing receipt; changed payload conflicts",
    "authority": "SQLite committed effects; intent and invoice are not unique effect keys",
    "checks": ["PAYMENT_EFFECT_BINDING", "PAYMENT_NO_DUPLICATES",
               "PAYMENT_REQUIRED_EFFECTS", "PAYMENT_REPORT_TRUTH"],
    "reply_loss": "deterministically suppress first selected committed receipt; no HTTP timing",
}


def scenario_for_case(case_id: str) -> dict:
    if case_id not in CASE_IDS:
        raise ValueError("Unknown installed payment candidate")
    operations = [{"intent_id": "intent-1", "invoice_id": "INV-1", "amount_minor": 10000,
                   "currency": "USD"}]
    if case_id in ("two_intents", "wrong_receipt"):
        operations.append({"intent_id": "intent-2", "invoice_id": "INV-2",
                           "amount_minor": 10000, "currency": "USD"})
    loss = case_id in ("reconcile", "blind_retry", "stopped", "untriggered")
    return {"task_type": PAYMENTS, "intents": operations,
            "faults": ([{"fault_id": FAULT_ID, "kind": "POST_COMMIT_REPLY_LOSS",
                         "intent_id": "intent-1", "commit_ordinal": 1}] if loss else []),
            "limits": {"max_attempts": 8, "max_reports": 1},
            "fixture_kind": "SYNTHETIC_DETERMINISTIC_PAYMENT"}


def mapping_digest() -> str:
    return sha256(Path(__file__).read_bytes()).hexdigest()


def payment_identity(case_id: str, trial_id: str, world_id: str) -> dict:
    scenario = scenario_for_case(case_id)
    source = mapping_digest()
    return {"task_type": PAYMENTS, "trial_id": trial_id, "world_id": world_id,
            "subject_id": "installed-payment-" + case_id,
            "subject_source_digest": digest({"module": source, "candidate": case_id}),
            "runtime_digest": digest({"python": platform.python_version(),
                                      "implementation": platform.python_implementation(),
                                      "sqlite": sqlite3.sqlite_version, "mapping": source,
                                      "schema": schema_digest()}),
            "task_contract_digest": digest(CONTRACT),
            "configuration_digest": digest({"scenario": scenario, "candidate": case_id}),
            "mapping_digest": source, "source_mode": "offline_fixture",
            "evidence_origin": "persisted_synthetic_execution"}


class Payload(Model):
    invoice_id: str = Field(min_length=1, max_length=128)
    amount_minor: int = Field(gt=0, le=1000000000)
    currency: Literal["USD"]


class IntentFact(Payload):
    intent_id: str
    payload_digest: str


class AttemptFact(Model):
    attempt_id: str
    intent_id: str
    method: Literal["pay", "lookup"]
    operation_key: str = Field(min_length=1, max_length=512)
    payload: dict[str, JsonValue] | None
    payload_digest: str | None
    start_sequence: int = Field(ge=1)


class EffectFact(Model):
    effect_id: str
    receipt_id: str
    attempt_id: str
    intent_id: str
    operation_key: str
    payload: dict[str, JsonValue]
    payload_digest: str
    commit_sequence: int = Field(ge=1)


class ObservationFact(Model):
    observation_id: str
    attempt_id: str
    transport: Literal["ok", "timeout", "error"]
    payload: dict[str, JsonValue]
    delivery_sequence: int = Field(ge=1)


class EventFact(Model):
    sequence: int = Field(ge=1)
    kind: Literal["attempt_started", "effect_committed", "receipt_reused", "key_conflict",
                  "lookup_found", "lookup_missing", "reply_lost", "observation_delivered",
                  "report_submitted", "trial_finished"]
    payload: dict[str, JsonValue]


class ReportFact(Model):
    status: Literal["DELIVERED", "ABSENT"]
    raw_text: str | None
    original: JsonValue | None
    submission_sequence: int | None


class FaultFact(Model):
    fault_id: str
    triggered: bool
    attempt_id: str | None
    effect_id: str | None
    trigger_sequence: int | None


class Metadata(Model):
    case_id: CaseId
    identity: Identity
    scenario: dict[str, JsonValue]


class State(Model):
    state: Literal["RUNNING", "COMPLETED", "INCOMPLETE"]
    cleanup_complete: bool
    reason: str | None


class Facts(Model):
    schema_version: Literal["faultlab-payment-facts/v1"]
    metadata: Metadata
    lifecycle: State
    intents: list[IntentFact] | None
    attempts: list[AttemptFact] | None
    effects: list[EffectFact] | None
    observations: list[ObservationFact] | None
    events: list[EventFact] | None
    report: ReportFact | None
    faults: list[FaultFact] | None
    missing_tables: list[str]


def _strict_json(text: str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise IntegrityError("Duplicate JSON object key")
            result[key] = value
        return result
    def reject_constant(value):
        raise IntegrityError("Nonfinite JSON value")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)


def _payload(intent) -> dict:
    return {key: intent[key] for key in ("invoice_id", "amount_minor", "currency")}


def _receipt(effect: dict) -> dict:
    return {"status": "PAID", "receipt_id": effect["receipt_id"],
            "effect_id": effect["effect_id"], "operation_key": effect["operation_key"],
            **effect["payload"]}


class _Fixture:
    def __init__(self, path: Path, case_id: str):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE trial (id INTEGER PRIMARY KEY CHECK(id=1), metadata TEXT NOT NULL,
                            lifecycle TEXT NOT NULL);
        CREATE TABLE intents (intent_id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE attempts (attempt_id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE effects (effect_id TEXT PRIMARY KEY, operation_key TEXT UNIQUE NOT NULL,
                              data TEXT NOT NULL);
        CREATE TABLE observations (observation_id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE events (sequence INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE reports (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
        CREATE TABLE faults (fault_id TEXT PRIMARY KEY, data TEXT NOT NULL);
        """)
        self.scenario = scenario_for_case(case_id)
        self.identity = payment_identity(case_id, "payment-trial-" + uuid4().hex,
                                         "payment-world-" + uuid4().hex)
        self.db.execute("INSERT INTO trial VALUES (1,?,?)", (
            canonical({"case_id": case_id, "identity": self.identity, "scenario": self.scenario}),
            canonical({"state": "RUNNING", "cleanup_complete": False, "reason": None})))
        self.intents = {item["intent_id"]: _payload(item) for item in self.scenario["intents"]}
        for intent_id, payload in self.intents.items():
            self.db.execute("INSERT INTO intents VALUES (?,?)", (
                intent_id, canonical({"intent_id": intent_id, **payload, "payload_digest": digest(payload)})))
        for spec in self.scenario["faults"]:
            self.db.execute("INSERT INTO faults VALUES (?,?)", (spec["fault_id"], canonical({
                "fault_id": spec["fault_id"], "triggered": False, "attempt_id": None,
                "effect_id": None, "trigger_sequence": None})))
        self.db.commit()

    def event(self, kind: str, payload: dict) -> int:
        seq = self.db.execute("SELECT coalesce(max(sequence),0)+1 FROM events").fetchone()[0]
        self.db.execute("INSERT INTO events VALUES (?,?,?)", (seq, kind, canonical(payload)))
        return seq

    def call(self, intent_id: str, key: str, *, lookup=False, payload=None) -> dict:
        if intent_id not in self.intents:
            raise ValueError("Unknown declared intent")
        n = self.db.execute("SELECT count(*) FROM attempts").fetchone()[0] + 1
        if n > self.scenario["limits"]["max_attempts"]:
            raise ValueError("Declared attempt limit exceeded")
        attempt_id = f"attempt-{n}"
        payload = None if lookup else (deepcopy(payload) if payload is not None else self.intents[intent_id])
        if payload is not None:
            payload = Payload.model_validate(payload).model_dump()
        self.db.execute("BEGIN IMMEDIATE")
        start = self.event("attempt_started", {"attempt_id": attempt_id})
        attempt = {"attempt_id": attempt_id, "intent_id": intent_id,
                   "method": "lookup" if lookup else "pay", "operation_key": key,
                   "payload": payload, "payload_digest": digest(payload) if payload is not None else None,
                   "start_sequence": start}
        self.db.execute("INSERT INTO attempts VALUES (?,?)", (attempt_id, canonical(attempt)))
        row = self.db.execute("SELECT data FROM effects WHERE operation_key=?", (key,)).fetchone()
        effect = _strict_json(row[0]) if row else None
        created = False
        if lookup:
            self.event("lookup_found" if effect else "lookup_missing", {
                "attempt_id": attempt_id, "effect_id": effect["effect_id"] if effect else None})
            result = _receipt(effect) if effect else {"status": "NOT_FOUND"}
            transport = "ok"
        elif effect:
            if canonical(effect["payload"]) != canonical(payload):
                self.event("key_conflict", {"attempt_id": attempt_id, "effect_id": effect["effect_id"]})
                result, transport = {"status": "CONFLICT", "code": "KEY_PAYLOAD_CONFLICT"}, "error"
            else:
                self.event("receipt_reused", {"attempt_id": attempt_id, "effect_id": effect["effect_id"]})
                result, transport = _receipt(effect), "ok"
        else:
            effect_id = f"effect-{self.db.execute('SELECT count(*) FROM effects').fetchone()[0] + 1}"
            seq = self.event("effect_committed", {"attempt_id": attempt_id, "effect_id": effect_id})
            effect = {"effect_id": effect_id, "receipt_id": "receipt-" + effect_id,
                      "attempt_id": attempt_id, "intent_id": intent_id, "operation_key": key,
                      "payload": payload, "payload_digest": digest(payload), "commit_sequence": seq}
            self.db.execute("INSERT INTO effects VALUES (?,?,?)", (effect_id, key, canonical(effect)))
            result, transport, created = _receipt(effect), "ok", True
        # Persist the actual effect before a reply can be suppressed.
        self.db.commit()
        self.db.execute("BEGIN IMMEDIATE")
        fault_row = self.db.execute("SELECT data FROM faults WHERE fault_id=?", (FAULT_ID,)).fetchone()
        if created and intent_id == "intent-1" and fault_row and not _strict_json(fault_row[0])["triggered"]:
            seq = self.event("reply_lost", {"attempt_id": attempt_id, "effect_id": effect["effect_id"],
                                             "fault_id": FAULT_ID})
            fault = {"fault_id": FAULT_ID, "triggered": True, "attempt_id": attempt_id,
                     "effect_id": effect["effect_id"], "trigger_sequence": seq}
            self.db.execute("UPDATE faults SET data=? WHERE fault_id=?", (canonical(fault), FAULT_ID))
            result, transport = {"status": "UNKNOWN", "code": "REPLY_LOST"}, "timeout"
        observation_id = f"observation-{n}"
        seq = self.event("observation_delivered", {"attempt_id": attempt_id, "observation_id": observation_id})
        observation = {"observation_id": observation_id, "attempt_id": attempt_id,
                       "transport": transport, "payload": result, "delivery_sequence": seq}
        self.db.execute("INSERT INTO observations VALUES (?,?)", (observation_id, canonical(observation)))
        self.db.commit()
        return result

    def report(self, claims: list[dict], overall="COMPLETED"):
        original = {"payments": claims, "overall": overall}
        # Whitespace is intentionally retained to prove raw reports are not rewritten.
        raw = json.dumps(original, indent=2) + "\n"
        seq = self.event("report_submitted", {"report_id": "final-report"})
        self.db.execute("INSERT INTO reports VALUES (1,?)", (canonical({"status": "DELIVERED",
            "raw_text": raw, "original": original, "submission_sequence": seq}),))
        self.db.commit()

    def finish(self, *, stopped=False):
        state = "INCOMPLETE" if stopped else "COMPLETED"
        self.event("trial_finished", {"state": state})
        self.db.execute("UPDATE trial SET lifecycle=? WHERE id=1", (canonical({
            "state": state, "cleanup_complete": True,
            "reason": "Declared stop after committed effect" if stopped else None}),))
        self.db.commit()


def read_payment_facts(db_path: Path) -> dict:
    """Read only the selected fixture database; absent authority stays explicit."""
    path = Path(db_path)
    if path.is_symlink():
        raise IntegrityError("Payment evidence database may not be a final symlink")
    path = path.resolve(strict=True)
    if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise IntegrityError("Invalid or oversized payment evidence database")
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("BEGIN")
            tables = {row[0]: row[1] for row in db.execute("SELECT name,type FROM sqlite_master")}
            if tables.get("trial") != "table":
                raise IntegrityError("Payment identity authority is unavailable")
            trial = db.execute("SELECT id,metadata,lifecycle FROM trial").fetchall()
            if len(trial) != 1 or trial[0][0] != 1:
                raise IntegrityError("Contradictory payment trial identity")
            facts = {"schema_version": FACTS_VERSION, "metadata": _strict_json(trial[0][1]),
                     "lifecycle": _strict_json(trial[0][2]), "missing_tables": []}
            for table in TABLES:
                field = "report" if table == "reports" else table
                if table not in tables:
                    facts[field] = None
                    facts["missing_tables"].append(table)
                    continue
                if tables[table] != "table":
                    raise IntegrityError("Payment authority must be a persisted table")
                if table == "events":
                    facts[field] = [{"sequence": seq, "kind": kind, "payload": _strict_json(payload)}
                                    for seq, kind, payload in db.execute(
                                        "SELECT sequence,kind,payload FROM events ORDER BY sequence")]
                else:
                    key_column = {"intents": "intent_id", "attempts": "attempt_id", "effects": "effect_id",
                                  "observations": "observation_id", "reports": "id", "faults": "fault_id"}[table]
                    rows = db.execute(f"SELECT {key_column},data FROM {table} ORDER BY rowid").fetchall()
                    values = []
                    for key, raw in rows:
                        value = _strict_json(raw)
                        if (table == "reports" and key != 1) or (table != "reports" and value.get(key_column) != key):
                            raise IntegrityError("SQLite key contradicts payment record")
                        values.append(value)
                    if table == "effects":
                        key_bindings = dict(db.execute("SELECT effect_id,operation_key FROM effects"))
                        if any(key_bindings[value["effect_id"]] != value["operation_key"] for value in values):
                            raise IntegrityError("SQLite provider key contradicts effect record")
                    if table == "reports":
                        if len(values) > 1:
                            raise IntegrityError("Multiple final payment reports")
                        facts[field] = values[0] if values else {"status": "ABSENT", "raw_text": None,
                                                               "original": None, "submission_sequence": None}
                    else:
                        facts[field] = values
            return facts
    except (sqlite3.Error, json.JSONDecodeError, UnicodeError) as error:
        raise IntegrityError("Unreadable payment evidence") from error


def _validate_facts(value: dict) -> dict:
    try:
        facts = Facts.model_validate(value).model_dump(mode="json")
        if len(canonical(facts).encode()) > 8 * 1024 * 1024:
            raise IntegrityError("Payment facts exceed size bound")
    except (ValidationError, TypeError, ValueError) as error:
        raise IntegrityError("Invalid closed payment source facts") from error
    meta = facts["metadata"]
    identity = meta["identity"]
    if (canonical(meta["scenario"]) != canonical(scenario_for_case(meta["case_id"]))
            or canonical(identity) != canonical(payment_identity(meta["case_id"], identity["trial_id"], identity["world_id"]))):
        raise IntegrityError("Payment subject, scenario, or runtime identity mismatch")
    expected_missing = [name for name in TABLES if facts["report" if name == "reports" else name] is None]
    if facts["missing_tables"] != expected_missing:
        raise IntegrityError("Payment authority completeness contradicts source records")
    def indexed(field, key):
        rows = facts[field] or []
        result = {row[key]: row for row in rows}
        if len(result) != len(rows):
            raise IntegrityError("Duplicate payment record identity")
        return result
    intents = indexed("intents", "intent_id")
    attempts = indexed("attempts", "attempt_id")
    effects = indexed("effects", "effect_id")
    observations = indexed("observations", "observation_id")
    events = indexed("events", "sequence")
    faults = indexed("faults", "fault_id")
    if len(attempts) > meta["scenario"]["limits"]["max_attempts"]:
        raise IntegrityError("Persisted attempts exceed the declared execution bound")
    if facts["intents"] is not None:
        expected = [{**item, "payload_digest": digest(_payload(item))} for item in meta["scenario"]["intents"]]
        if canonical(facts["intents"]) != canonical(expected):
            raise IntegrityError("Persisted intentions contradict the declaration")
    if facts["events"] is not None and list(events) != list(range(1, len(events) + 1)):
        raise IntegrityError("Payment event sequence has gaps or reordering")
    used_sequences = set()
    def event(seq, kind, payload):
        if facts["events"] is None:
            return
        if seq in used_sequences or events.get(seq) != {"sequence": seq, "kind": kind, "payload": payload}:
            raise IntegrityError("Payment record contradicts its event")
        used_sequences.add(seq)
    for item in attempts.values():
        if facts["intents"] is not None and item["intent_id"] not in intents:
            raise IntegrityError("Unknown attempted intent")
        if item["method"] == "lookup":
            if item["payload"] is not None or item["payload_digest"] is not None:
                raise IntegrityError("Lookup has invented payment request bytes")
        else:
            try:
                payload = Payload.model_validate(item["payload"]).model_dump()
            except ValidationError as error:
                raise IntegrityError("Invalid payment request payload") from error
            if digest(payload) != item["payload_digest"]:
                raise IntegrityError("Payment request digest mismatch")
        event(item["start_sequence"], "attempt_started", {"attempt_id": item["attempt_id"]})
    keys, receipts = set(), set()
    for item in effects.values():
        if item["operation_key"] in keys or item["receipt_id"] in receipts:
            raise IntegrityError("Provider key or receipt maps to multiple effects")
        keys.add(item["operation_key"]); receipts.add(item["receipt_id"])
        if digest(item["payload"]) != item["payload_digest"]:
            raise IntegrityError("Effect payload digest mismatch")
        if facts["attempts"] is not None:
            attempt = attempts.get(item["attempt_id"])
            if (not attempt or attempt["method"] != "pay" or attempt["intent_id"] != item["intent_id"]
                    or attempt["operation_key"] != item["operation_key"]
                    or canonical(attempt["payload"]) != canonical(item["payload"])
                    or attempt["start_sequence"] >= item["commit_sequence"]):
                raise IntegrityError("Committed effect contradicts its request")
        event(item["commit_sequence"], "effect_committed", {"attempt_id": item["attempt_id"], "effect_id": item["effect_id"]})
    seen_attempt_observations = set()
    for item in observations.values():
        aid = item["attempt_id"]
        if aid in seen_attempt_observations:
            raise IntegrityError("Multiple delivered responses for one attempt")
        seen_attempt_observations.add(aid)
        if facts["attempts"] is not None:
            attempt = attempts.get(aid)
            if not attempt or attempt["start_sequence"] >= item["delivery_sequence"]:
                raise IntegrityError("Observation precedes or lacks its request")
        else:
            attempt = None
        if item["payload"].get("status") == "PAID" and facts["effects"] is not None:
            effect = effects.get(item["payload"].get("effect_id"))
            if (not effect or canonical(item["payload"]) != canonical(_receipt(effect))
                    or effect["commit_sequence"] >= item["delivery_sequence"]
                    or (attempt and effect["operation_key"] != attempt["operation_key"])):
                raise IntegrityError("Delivered receipt contradicts persisted effect")
        event(item["delivery_sequence"], "observation_delivered", {
            "attempt_id": aid, "observation_id": item["observation_id"]})
    if facts["faults"] is not None:
        if set(faults) != {spec["fault_id"] for spec in meta["scenario"]["faults"]}:
            raise IntegrityError("Fault ledger contradicts declaration")
        for item in faults.values():
            if item["triggered"]:
                if any(item[key] is None for key in ("attempt_id", "effect_id", "trigger_sequence")):
                    raise IntegrityError("Triggered fault lacks its witness")
                if facts["effects"] is not None:
                    effect = effects.get(item["effect_id"])
                    if not effect or effect["attempt_id"] != item["attempt_id"] or effect["commit_sequence"] >= item["trigger_sequence"]:
                        raise IntegrityError("Reply loss did not follow its committed effect")
                if facts["observations"] is not None:
                    matches = [obs for obs in observations.values() if obs["attempt_id"] == item["attempt_id"]]
                    if len(matches) != 1 or matches[0]["transport"] != "timeout" or matches[0]["delivery_sequence"] <= item["trigger_sequence"]:
                        raise IntegrityError("Reply-loss witness contradicts delivered observation")
                event(item["trigger_sequence"], "reply_lost", {"attempt_id": item["attempt_id"],
                    "effect_id": item["effect_id"], "fault_id": item["fault_id"]})
            elif any(item[key] is not None for key in ("attempt_id", "effect_id", "trigger_sequence")):
                raise IntegrityError("Untriggered fault has an invented witness")
    report = facts["report"]
    if report:
        if report["status"] == "ABSENT":
            if any(report[key] is not None for key in ("raw_text", "original", "submission_sequence")):
                raise IntegrityError("Absent original report has invented contents")
        else:
            try:
                parsed = _strict_json(report["raw_text"])
            except (TypeError, ValueError) as error:
                raise IntegrityError("Original payment report is not preserved JSON") from error
            if canonical(parsed) != canonical(report["original"]) or report["submission_sequence"] is None:
                raise IntegrityError("Original report bytes contradict parsed report")
            event(report["submission_sequence"], "report_submitted", {"report_id": "final-report"})
            if any(obs["delivery_sequence"] >= report["submission_sequence"] for obs in observations.values()):
                raise IntegrityError("Payment report precedes delivered observations")
    if facts["events"] is not None:
        finals = [item for item in events.values() if item["kind"] == "trial_finished"]
        if facts["lifecycle"]["state"] != "RUNNING":
            if len(finals) != 1 or finals[0]["sequence"] != len(events) or finals[0]["payload"] != {"state": facts["lifecycle"]["state"]}:
                raise IntegrityError("Payment lifecycle contradicts final event")
        elif finals:
            raise IntegrityError("Running payment trial has a final event")
    # Validate service events against independent request/effect/observation rows.
    # This is the declared fixture protocol, not an assertion of a safe candidate.
    if all(facts[name] is not None for name in ("attempts", "effects", "observations", "events", "faults")):
        if len(observations) != len(attempts):
            raise IntegrityError("An admitted payment attempt lacks its terminal observation")
        if list(attempts) != [f"attempt-{i + 1}" for i in range(len(attempts))]:
            raise IntegrityError("Payment attempts are reordered or incomplete")
        for attempt in attempts.values():
            aid, start = attempt["attempt_id"], attempt["start_sequence"]
            prior = [effect for effect in effects.values() if effect["operation_key"] == attempt["operation_key"]
                     and effect["commit_sequence"] < start]
            created = [effect for effect in effects.values() if effect["attempt_id"] == aid]
            existing = prior[0] if prior else None
            if attempt["method"] == "lookup":
                if created:
                    raise IntegrityError("Read-only lookup created a payment")
                kind = "lookup_found" if existing else "lookup_missing"
                action_payload = {"attempt_id": aid, "effect_id": existing["effect_id"] if existing else None}
                expected_payload = _receipt(existing) if existing else {"status": "NOT_FOUND"}
                expected_transport = "ok"
                event(start + 1, kind, action_payload)
            elif existing:
                if created:
                    raise IntegrityError("Existing provider key committed a second effect")
                equal = canonical(existing["payload"]) == canonical(attempt["payload"])
                event(start + 1, "receipt_reused" if equal else "key_conflict", {
                    "attempt_id": aid, "effect_id": existing["effect_id"]})
                expected_payload = _receipt(existing) if equal else {"status": "CONFLICT", "code": "KEY_PAYLOAD_CONFLICT"}
                expected_transport = "ok" if equal else "error"
            else:
                if len(created) != 1 or created[0]["commit_sequence"] != start + 1:
                    raise IntegrityError("New provider key lacks its atomic committed effect")
                expected_payload, expected_transport = _receipt(created[0]), "ok"
            lost = [fault for fault in faults.values() if fault["triggered"] and fault["attempt_id"] == aid]
            if lost:
                if len(lost) != 1 or not created or lost[0]["trigger_sequence"] != start + 2:
                    raise IntegrityError("Reply loss is not immediately after the new commit")
                expected_payload, expected_transport = {"status": "UNKNOWN", "code": "REPLY_LOST"}, "timeout"
            observed = next(obs for obs in observations.values() if obs["attempt_id"] == aid)
            if (observed["transport"] != expected_transport
                    or canonical(observed["payload"]) != canonical(expected_payload)
                    or observed["delivery_sequence"] != start + 2 + bool(lost)):
                raise IntegrityError("Delivered observation contradicts service transition")
        if FAULT_ID in faults:
            targets = [effect for effect in effects.values() if effect["intent_id"] == "intent-1"]
            if bool(targets) != faults[FAULT_ID]["triggered"]:
                raise IntegrityError("Fault exposure contradicts reached commit target")
            if targets and faults[FAULT_ID]["effect_id"] != min(targets, key=lambda e: e["commit_sequence"])["effect_id"]:
                raise IntegrityError("Reply-loss fault targeted the wrong commit")
        accounted = used_sequences | {item["sequence"] for item in events.values() if item["kind"] == "trial_finished"}
        if facts["report"] is None:
            accounted |= {item["sequence"] for item in events.values() if item["kind"] == "report_submitted"}
        if accounted != set(events):
            raise IntegrityError("Payment event has no corresponding persisted authority record")
    return facts


def _checks(facts: dict) -> list[dict]:
    if facts["intents"] is None or facts["effects"] is None:
        return []
    intents = {item["intent_id"]: _payload(item) for item in facts["intents"]}
    effects = facts["effects"]
    refs = [f"/effects/{i}" for i in range(len(effects))] + [f"/intents/{i}" for i in range(len(intents))]
    counts = {iid: sum(effect["intent_id"] == iid for effect in effects) for iid in intents}
    checks = [
        {"check_id": "PAYMENT_EFFECT_BINDING", "passed": all(
            effect["intent_id"] in intents and canonical(effect["payload"]) == canonical(intents[effect["intent_id"]])
            for effect in effects), "details": "Actual effects match declared invoice, amount and currency.", "evidence_refs": refs},
        {"check_id": "PAYMENT_NO_DUPLICATES", "passed": all(n <= 1 for n in counts.values()),
         "details": "At most one actual effect per declared intent, across all provider keys.", "evidence_refs": refs},
    ]
    report = facts["report"]
    if (report and report["status"] == "DELIVERED" and facts["attempts"] is not None
            and facts["observations"] is not None):
        checks.append({"check_id": "PAYMENT_REQUIRED_EFFECTS", "passed": all(n >= 1 for n in counts.values()),
                       "details": "Every requested payment has an actual committed effect.", "evidence_refs": refs})
        original = report["original"]
        valid = isinstance(original, dict) and set(original) == {"payments", "overall"}
        claims = original.get("payments") if valid else None
        valid = valid and isinstance(claims, list) and len(claims) == len(intents)
        claimed = set()
        attempts = {item["attempt_id"]: item for item in facts["attempts"] or []}
        for claim in claims if isinstance(claims, list) else []:
            if not isinstance(claim, dict) or set(claim) != {"intent_id", "status", "receipt_id"}:
                valid = False; continue
            iid = claim["intent_id"]
            if not isinstance(iid, str) or iid not in intents or iid in claimed:
                valid = False; continue
            claimed.add(iid)
            if claim["status"] == "PAID":
                matches = [e for e in effects if e["receipt_id"] == claim["receipt_id"] and e["intent_id"] == iid
                           and canonical(e["payload"]) == canonical(intents[iid])]
                seen = any(obs["payload"].get("receipt_id") == claim["receipt_id"]
                           and attempts.get(obs["attempt_id"], {}).get("intent_id") == iid
                           and obs["transport"] == "ok"
                           for obs in facts["observations"] or [])
                valid = valid and len(matches) == 1 and seen
            elif claim["status"] == "UNRESOLVED":
                valid = valid and claim["receipt_id"] is None
            else:
                valid = False
        valid = valid and claimed == set(intents)
        if isinstance(original, dict):
            statuses = [claim.get("status") for claim in claims if isinstance(claim, dict)] if isinstance(claims, list) else []
            valid = valid and original.get("overall") == ("COMPLETED" if statuses and all(s == "PAID" for s in statuses) else "UNRESOLVED")
        checks.append({"check_id": "PAYMENT_REPORT_TRUTH", "passed": bool(valid),
                       "details": "Original claims use correctly attributed, previously delivered receipts.",
                       "evidence_refs": ["/report", *refs]})
    return checks


def project_payment_facts(value: dict) -> Envelope:
    """Project exact-compatible installed fixture facts, never relabel old runtime.

    A different recorded source, Python/SQLite runtime, or schema is rejected.
    Historical records remain intact; this mapper makes no migration claim.
    """
    facts = _validate_facts(value)
    meta = facts["metadata"]
    attempts = {item["attempt_id"]: item for item in facts["attempts"] or []}
    pos = lambda sequence: {"clock": "payment_event", "sequence": sequence, "tick": None}
    missing = ["PAYMENT_AUTHORITY_" + table.upper() for table in facts["missing_tables"]]
    report = facts["report"] or {"status": "ABSENT", "raw_text": None, "original": None}
    declared = facts["intents"]
    if declared is None:
        declared = [{**item, "payload_digest": digest(_payload(item))} for item in meta["scenario"]["intents"]]
    operation_source = "/intents" if facts["intents"] is not None else "/metadata/scenario/intents"
    # Source references remain valid even when report authority is explicitly null.
    return seal(identity=meta["identity"], scenario=meta["scenario"],
        operations=[{"intent_id": item["intent_id"], "action": "pay_invoice", "scope": "synthetic-payments",
                     "payload": _payload(item), "payload_digest": item["payload_digest"], "source_ref": f"{operation_source}/{i}"}
                    for i, item in enumerate(declared)],
        attempts=[{"attempt_id": item["attempt_id"], "call_id": item["attempt_id"], "intent_id": item["intent_id"],
                   "action": item["method"], "operation_key": item["operation_key"], "payload": item["payload"],
                   "payload_digest": item["payload_digest"], "source_ref": f"/attempts/{i}", "position": pos(item["start_sequence"])}
                  for i, item in enumerate(facts["attempts"] or [])],
        effects=[{"effect_id": item["effect_id"], "intent_id": item["intent_id"], "operation_key": item["operation_key"],
                  "payload": item["payload"], "payload_digest": item["payload_digest"], "receipt": _receipt(item),
                  "source_ref": f"/effects/{i}", "position": pos(item["commit_sequence"])}
                 for i, item in enumerate(facts["effects"] or [])],
        observations=[{"observation_id": item["observation_id"], "attempt_id": item["attempt_id"] if item["attempt_id"] in attempts else None,
                       "intent_id": attempts.get(item["attempt_id"], {}).get("intent_id"), "transport": item["transport"],
                       "payload": item["payload"], "payload_digest": digest(item["payload"]),
                       "source_ref": f"/observations/{i}", "position": pos(item["delivery_sequence"])}
                      for i, item in enumerate(facts["observations"] or [])],
        report={"status": report["status"], "original": report["original"], "raw_text": report["raw_text"],
                "interpreted": report["original"], "source_ref": "/report"},
        required_fault_ids=[spec["fault_id"] for spec in meta["scenario"]["faults"]],
        faults=[{"fault_id": item["fault_id"], "triggered": item["triggered"],
                 "witness": ({key: item[key] for key in ("attempt_id", "effect_id", "trigger_sequence")} if item["triggered"] else None),
                 "source_ref": f"/faults/{i}"} for i, item in enumerate(facts["faults"] or [])],
        checks=_checks(facts),
        lifecycle={"state": "COMPLETED" if facts["lifecycle"]["state"] == "COMPLETED" else "INCOMPLETE",
                   "authority_complete": not missing, "cleanup_complete": facts["lifecycle"]["cleanup_complete"],
                   "reason": facts["lifecycle"]["reason"], "missing": missing}, source_facts=facts)


def run_payment_case(output: Path, case_id: str) -> Envelope:
    """Execute one named installed candidate, once, in a new synthetic world."""
    scenario_for_case(case_id)  # Reject unknown executable selection before writes.
    output = Path(output)
    if output.is_symlink():
        raise FileExistsError("Output may not be a symlink")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    fixture = _Fixture(output / "payment.sqlite3", case_id)
    def paid(iid, receipt):
        return {"intent_id": iid, "status": "PAID", "receipt_id": receipt["receipt_id"]}
    try:
        if case_id == "untriggered":
            fixture.report([{"intent_id": "intent-1", "status": "UNRESOLVED", "receipt_id": None}], "UNRESOLVED")
        else:
            first = fixture.call("intent-1", "business-key-1")
            if case_id == "reconcile":
                first = fixture.call("intent-1", "business-key-1", lookup=True)
            elif case_id == "blind_retry":
                first = fixture.call("intent-1", "new-attempt-key")
            elif case_id == "payload_conflict":
                changed = {**fixture.intents["intent-1"], "amount_minor": 20000}
                fixture.call("intent-1", "business-key-1", payload=changed)
            if case_id in ("two_intents", "wrong_receipt"):
                second = fixture.call("intent-2", "business-key-2") if case_id == "two_intents" else fixture.call("intent-2", "business-key-1", lookup=True)
                fixture.report([paid("intent-1", first), paid("intent-2", second)])
            elif case_id != "stopped":
                fixture.report([paid("intent-1", first)])
        fixture.finish(stopped=case_id == "stopped")
    finally:
        fixture.db.close()
    facts = read_payment_facts(output / "payment.sqlite3")
    envelope = project_payment_facts(facts)
    (output / "source-facts.json").write_text(canonical(facts) + "\n", encoding="utf-8")
    (output / "incident.json").write_text(canonical(envelope) + "\n", encoding="utf-8")
    return envelope

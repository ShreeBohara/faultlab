"""Read-only projection of selected synthetic orders evidence.

This is a mapping of recorded facts, not another orders scorer. In particular,
public observations and provisional reports never substitute for world effects.
No historical store is selected automatically and no supplied code is imported.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

from app.contracts.models import (
    Episode, Event, FaultSpec, OperationJournal, PublicObservation, TaskIntent,
    ToolCallRecord, TrialResult, WorldSnapshot,
)
from app.incident_evidence.models import (
    ORDERS, MAX_BYTES, IntegrityError, canonical, digest, hashed_payload, seal,
)

FORMAT = "faultlab-orders-source-facts/v1"
FACT_KEYS = frozenset({
    "format", "episode", "trial", "configuration", "inputs", "journals",
    "tool_calls", "observations", "events", "snapshots", "world_integrity",
    "native_execution", "registered_execution", "offline_execution",
})
WORLD_EVENTS = frozenset({
    "http_attempt", "operation_accepted", "upgrade_committed", "upgrade_failed",
    "notification_committed", "request_rejected", "fault_triggered",
})
TOOLS = {"orders": "update_order", "notifications": "send_confirmation"}


def mapping_digest():
    return sha256(Path(__file__).read_bytes()).hexdigest()


def _require(condition, message):
    if not condition:
        raise IntegrityError(message)


def _same(left, right, message):
    _require(canonical(left) == canonical(right), message)


def _typed(model, value, name):
    try:
        return model.model_validate_json(canonical(value)).model_dump(mode="json")
    except (TypeError, ValueError) as error:
        raise IntegrityError(f"Invalid orders {name}") from error


def _indexed(rows, field, name):
    result = {}
    for index, row in enumerate(rows):
        key = row[field]
        _require(key not in result, f"Duplicate orders {name} identity")
        result[key] = (index, row)
    return result


def _position(event, clock):
    return {"clock": clock, "sequence": event["seq"], "tick": event["tick"]}


def _snapshot(value):
    if value is None:
        return None
    result = _typed(WorldSnapshot, value, "snapshot")
    # WorldSnapshot is already capability-free. Keep only the events needed to
    # establish dispatch, effects and exposure; never export a raw world state.
    result["events"] = [event for event in result["events"] if event["type"] in WORLD_EVENTS]
    return result


def load_orders_facts(store_path, episode_id):
    """Read one explicitly selected offline development episode without writes.

    Callers select a newly generated store. This reader neither discovers stores
    nor claims that a copied store is fresh merely because its path is new.
    """
    from app.lab.storage import ReadOnlyLabStore

    path = Path(store_path).expanduser()
    _require(path.is_file() and not path.is_symlink(), "Orders store must be an existing regular file")
    store = ReadOnlyLabStore(path)
    try:
        store.begin_snapshot()
        episode = store.get_record("episodes", episode_id)
        _require(isinstance(episode, dict) and episode.get("episode_id") == episode_id,
                 "Selected orders episode is unavailable")
        _require(episode.get("split") == "development" and episode.get("source_mode") == "offline_fixture",
                 "Only explicitly selected offline development evidence is eligible")

        def rows(kind):
            # Do not enumerate unrelated episodes or read their private records.
            raw = store.db.execute(
                "SELECT payload FROM records WHERE kind=? AND json_extract(payload,'$.episode_id')=? ORDER BY rowid",
                (kind, episode_id),
            ).fetchall()
            return [json.loads(row[0]) for row in raw]

        events = [json.loads(row[0]) for row in store.db.execute(
            "SELECT payload FROM events WHERE episode_id=? ORDER BY seq", (episode_id,)).fetchall()]
        # Native records are separately retained below; their large RPC payload
        # need not be duplicated as a public lab event.
        events = [event for event in events if event.get("type") in {
            "episode_started", "tool_dispatched", "observation_delivered",
            "report_submitted", "verdict_recorded", "episode_interrupted", "wait_completed",
        }]
        snapshots = store.get_record("private_snapshots", episode_id)
        if snapshots is not None:
            _require(isinstance(snapshots, dict) and set(snapshots) <= {"decision", "horizon"},
                     "Unknown orders snapshot fields")
            snapshots = {name: _snapshot(snapshots.get(name)) for name in ("decision", "horizon")}
        facts = {
            "format": FORMAT, "episode": episode,
            "trial": store.get_record("trials", episode_id),
            "configuration": store.get_record("configurations", episode["configuration_hash"]),
            "inputs": store.get_record("private_episode_inputs", episode_id),
            "journals": rows("journals"), "tool_calls": rows("tool_calls"),
            "observations": rows("observations"), "events": events, "snapshots": snapshots,
            "world_integrity": store.get_record("private_world_integrity", episode_id),
            "native_execution": store.get_record("native_agent_executions", episode_id),
            "registered_execution": store.get_record("episode_executions", episode_id),
            "offline_execution": store.get_record("offline_fixture_executions", episode_id),
        }
        project_orders_facts(facts)
        return facts
    finally:
        store.close()


def project_orders_facts(facts):
    """Project closed, persisted source facts; contradictions fail closed.

    Episode, configuration and declared input are required to identify a task.
    Missing execution/effect/report records remain incomplete, with known facts
    retained. The returned C1-C8 results are the original persisted checks.
    """
    try:
        _require(isinstance(facts, dict) and set(facts) == FACT_KEYS and facts["format"] == FORMAT,
                 "Unknown or missing orders source fields")
        _require(len(canonical(facts).encode()) <= MAX_BYTES, "Orders source facts exceed their bound")
        # Copy through canonical JSON: pure callers cannot mutate our envelope by
        # retaining references to dictionaries passed into the projection.
        facts = json.loads(canonical(facts))
        return _project(facts)
    except IntegrityError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError) as error:
        raise IntegrityError("Invalid or contradictory orders source facts") from error


def _project(facts):
    episode = _typed(Episode, facts["episode"], "episode")
    eid, wid = episode["episode_id"], episode["world_id"]
    _require(episode["split"] == "development" and episode["source_mode"] == "offline_fixture",
             "Orders mapping excludes non-development or provider-backed evidence")
    config = facts["configuration"]
    _require(isinstance(config, dict), "Orders configuration is unavailable")
    _same(digest(config), episode["configuration_hash"], "Orders configuration digest mismatch")
    inputs = facts["inputs"]
    _require(isinstance(inputs, dict) and set(inputs) == {"intent", "recipe", "fixture_id"},
             "Orders declared input is unavailable or has unknown fields")
    intent = _typed(TaskIntent, inputs["intent"], "intent")
    recipe = _typed(FaultSpec, inputs["recipe"], "recipe")
    _same(episode["task_id"], intent["task_id"], "Orders task identity mismatch")
    _same(episode["scenario_hash"], digest(recipe), "Orders scenario digest mismatch")
    missing = []
    trial = _typed(TrialResult, facts["trial"], "trial") if facts["trial"] is not None else None
    if trial is None:
        missing.append("TRIAL_UNAVAILABLE")
    else:
        for field in ("episode_id", "world_id", "scenario_hash", "policy_hash", "arm", "trial_index", "lifecycle", "usage", "reason"):
            _same(trial[field], episode[field], f"Orders trial {field} contradicts episode")
    verdict = episode["verdict"]
    if verdict is None:
        missing.append("CHECKS_UNAVAILABLE")
    else:
        _same(verdict["episode_id"], eid, "Orders verdict episode mismatch")
        _same(verdict["scorer_hash"], config["scorer_hash"], "Orders scorer identity mismatch")
        if trial:
            _same(trial["outcome"], verdict["outcome"], "Orders trial outcome mismatch")
            _same(sorted(trial["failed_checks"]), sorted(c["check_id"] for c in verdict["checks"] if not c["passed"]),
                  "Orders returned checks contradict persisted checks")
    journals = [_typed(OperationJournal, row, "journal") for row in facts["journals"]]
    calls = [_typed(ToolCallRecord, row, "tool call") for row in facts["tool_calls"]]
    observations = [_typed(PublicObservation, row, "observation") for row in facts["observations"]]
    events = [_typed(Event, row, "event") for row in facts["events"]]
    for row in [*journals, *calls, *observations, *events]:
        _same(row["episode_id"], eid, "Cross-episode orders evidence")
    _indexed(events, "seq", "event")
    _require([e["seq"] for e in events] == sorted(e["seq"] for e in events), "Unordered lab event sequence")
    journal_by_id = _indexed(journals, "operation_id", "operation")
    call_by_id = _indexed(calls, "call_id", "call")
    obs_by_id = _indexed(observations, "evidence_id", "observation")
    operations = []
    operation_service = {}
    for service, prefix in (("orders", "upgrade"), ("notifications", "notification")):
        opid = intent[f"{prefix}_operation_id"]
        _require(opid not in operation_service, "Declared orders operations must be distinct")
        operation_service[opid] = service
        # This is declared intent, deliberately not reconstructed wire bytes.
        payload = {"task_id": intent["task_id"], "order_id": intent["order_id"],
                   "operation_id": opid, "intent_hash": intent[f"{prefix}_intent_hash"]}
        payload.update({"desired_shipping": intent["desired_shipping"], "expected_version": intent["expected_version"]}
                       if service == "orders" else {"upgrade_operation_id": intent["upgrade_operation_id"],
                                                    "template_version": intent["template_version"]})
        operations.append({"intent_id": opid, "action": TOOLS[service], "scope": wid,
                           **hashed_payload(payload), "source_ref": "/inputs/intent"})
    attempt_journal = {}
    for index, journal in enumerate(journals):
        opid = journal["operation_id"]
        _require(opid in operation_service and journal["service"] == operation_service[opid], "Foreign orders journal")
        prefix = "upgrade" if journal["service"] == "orders" else "notification"
        _same(journal["intent_hash"], intent[f"{prefix}_intent_hash"], "Orders journal intent hash mismatch")
        payload = json.loads(journal["original_request"])
        _require(isinstance(payload, dict), "Orders journal request is not an object")
        _same(canonical(payload), journal["original_request"], "Orders journal request bytes are not canonical")
        _same(digest(payload), journal["payload_hash"], "Orders journal payload digest mismatch")
        for key, expected in {"operation_id": opid, "order_id": intent["order_id"],
                              "intent_hash": journal["intent_hash"], "idempotency_key": intent[f"{prefix}_idempotency_key"]}.items():
            _same(payload.get(key), expected, "Orders journal request identity mismatch")
        for aid in journal["attempt_ids"]:
            _require(aid not in attempt_journal, "Duplicate orders journal attempt")
            attempt_journal[aid] = (index, journal, payload)
    dispatches = {}
    deliveries = {}
    for index, event in enumerate(events):
        if event["type"] == "tool_dispatched":
            aid = event["payload"].get("attempt_id")
            _require(isinstance(aid, str) and aid not in dispatches, "Duplicate or missing dispatch identity")
            dispatches[aid] = (index, event)
        elif event["type"] == "observation_delivered":
            oid = event["evidence_id"]
            _require(oid not in deliveries, "Duplicate delivered observation")
            if oid not in obs_by_id:
                missing.append("OBSERVATION_UNAVAILABLE")
                continue
            _same(event["payload"].get("observation"), obs_by_id[oid][1], "Delivered observation contradicts stored observation")
            _same(event["call_id"], obs_by_id[oid][1]["call_id"], "Delivered observation call mismatch")
            deliveries[oid] = (index, event)
    attempts = []
    attempt_ids = set()
    obs_attempts = {}
    for index, call in enumerate(calls):
        _require(len(call["observation_ids"]) <= len(call["attempt_ids"]), "More observations than attempts")
        for number, aid in enumerate(call["attempt_ids"]):
            _require(aid not in attempt_ids, "Duplicate physical attempt identity")
            attempt_ids.add(aid)
            dispatch = dispatches.get(aid)
            if dispatch:
                event = dispatch[1]
                _same(event["call_id"], call["call_id"], "Attempt dispatch call mismatch")
                _same(event["payload"].get("tool"), call["tool"], "Attempt dispatch tool mismatch")
            else:
                missing.append("DISPATCH_EVENT_UNAVAILABLE")
            journal = attempt_journal.get(aid)
            opid, key, payload = None, None, None
            if journal:
                _, record, payload = journal
                opid, key = record["operation_id"], payload["idempotency_key"]
                _same(call["tool"], TOOLS[record["service"]], "Journal attempt tool mismatch")
            elif call["tool"] in TOOLS.values():
                missing.append("WRITE_JOURNAL_UNAVAILABLE")
            attempts.append({"attempt_id": aid, "call_id": call["call_id"], "intent_id": opid,
                             "action": call["tool"], "operation_key": key,
                             "payload": payload, "payload_digest": digest(payload) if payload is not None else None,
                             "source_ref": f"/tool_calls/{index}",
                             "position": _position(dispatch[1], "lab_event") if dispatch else None})
            if number < len(call["observation_ids"]):
                oid = call["observation_ids"][number]
                _require(oid not in obs_attempts, "Observation appears in more than one attempt")
                if oid not in obs_by_id:
                    missing.append("OBSERVATION_UNAVAILABLE")
                else:
                    _same(obs_by_id[oid][1]["call_id"], call["call_id"], "Observation call identity mismatch")
                    # The broker appends each observation after its corresponding
                    # attempt; verify public event order before retaining this join.
                    delivery = deliveries.get(oid)
                    if dispatch and delivery:
                        _require(dispatch[1]["seq"] < delivery[1]["seq"], "Observation precedes its dispatch")
                        if number + 1 < len(call["attempt_ids"]):
                            following = dispatches.get(call["attempt_ids"][number + 1])
                            if following:
                                _require(delivery[1]["seq"] < following[1]["seq"], "Observation attempt order mismatch")
                        obs_attempts[oid] = aid
                    else:
                        missing.append("OBSERVATION_ATTEMPT_JOIN_UNAVAILABLE")
    if set(dispatches) - attempt_ids or set(attempt_journal) - attempt_ids:
        missing.append("TOOL_CALL_RECORD_UNAVAILABLE")
    # A dispatch is still a known attempt if its final logical-call record is
    # absent. Retain only fields explicitly recorded at dispatch/journaling.
    for aid, (index, dispatch) in dispatches.items():
        if aid in attempt_ids:
            continue
        journal = attempt_journal.get(aid)
        payload = journal[2] if journal else None
        opid = journal[1]["operation_id"] if journal else None
        attempts.append({"attempt_id": aid, "call_id": dispatch["call_id"], "intent_id": opid,
                         "action": dispatch["payload"]["tool"],
                         "operation_key": payload["idempotency_key"] if payload else None,
                         "payload": payload, "payload_digest": digest(payload) if payload else None,
                         "source_ref": f"/events/{index}", "position": _position(dispatch, "lab_event")})
        attempt_ids.add(aid)
    projected_observations = []
    for index, observation in enumerate(observations):
        _same(observation["result"]["call_id"], observation["call_id"], "Observation result call mismatch")
        call = call_by_id.get(observation["call_id"])
        if call:
            _same(call[1]["tool"], observation["result"]["tool"], "Observation tool mismatch")
        else:
            missing.append("OBSERVATION_CALL_UNAVAILABLE")
        operation = observation.get("observed_operation_id")
        _require(operation is None or operation in operation_service, "Foreign observed operation")
        delivery = deliveries.get(observation["evidence_id"])
        if delivery is None:
            missing.append("OBSERVATION_DELIVERY_UNAVAILABLE")
        projected_observations.append({"observation_id": observation["evidence_id"],
            "attempt_id": obs_attempts.get(observation["evidence_id"]), "intent_id": operation,
            "transport": observation["result"]["transport"], **hashed_payload(observation["result"]),
            "source_ref": f"/observations/{index}",
            "position": _position(delivery[1], "lab_event") if delivery else None})

    snapshots = facts["snapshots"]
    _require(snapshots is None or isinstance(snapshots, dict) and set(snapshots) <= {"decision", "horizon"},
             "Unknown orders snapshot fields")
    decision, horizon = ((snapshots or {}).get(name) for name in ("decision", "horizon"))
    for value in (decision, horizon):
        if value is not None:
            _typed(WorldSnapshot, value, "snapshot")
            _same(value["world_id"], wid, "Orders snapshot world mismatch")
            _indexed(value["events"], "seq", "world event")
            for event in value["events"]:
                _same(event["episode_id"], eid, "Orders world event episode mismatch")
    if decision is None:
        missing.append("DECISION_SNAPSHOT_UNAVAILABLE")
    if horizon is None:
        missing.append("HORIZON_SNAPSHOT_UNAVAILABLE")
    if decision and horizon:
        _same(horizon["tick"], decision["tick"] + 5, "Orders horizon clock mismatch")
        # Earlier immutable events and notification effects cannot disappear.
        _same(horizon["events"][:len(decision["events"])], decision["events"], "Orders world event history changed")
        _same(horizon["notifications"][:len(decision["notifications"])], decision["notifications"], "Orders effects disappeared")
    authority = horizon or decision
    authority_name = "horizon" if horizon else "decision"
    effects = []
    if authority:
        ops = _indexed(authority["operations"], "operation_id", "provider operation")
        notifications = _indexed(authority["notifications"], "notification_id", "notification")
        for opid, (_, op) in ops.items():
            _require(opid in operation_service and op["service"] == operation_service[opid], "Foreign provider operation")
            _same(op["task_id"], intent["task_id"], "Provider task identity mismatch")
            _same(op["order_id"], intent["order_id"], "Provider order identity mismatch")
            journal = journal_by_id.get(opid)
            if journal:
                _same(op["payload_hash"], journal[1]["payload_hash"], "Provider and journal request digest mismatch")
            else:
                missing.append("PROVIDER_REQUEST_JOURNAL_UNAVAILABLE")
            receipt = op["receipt"]
            if receipt:
                for field, value in {"operation_id": opid, "service": op["service"], "order_id": op["order_id"], "status": op["state"]}.items():
                    _same(receipt[field], value, "Authoritative receipt contradicts operation")
                _same(receipt["terminal_tick"], op["terminal_tick"], "Authoritative receipt completion clock mismatch")
                prefix = "upgrade" if op["service"] == "orders" else "notification"
                _same(receipt["intent_hash"], intent[f"{prefix}_intent_hash"], "Authoritative receipt intent mismatch")
            elif op["state"] in ("SUCCEEDED", "FAILED"):
                missing.append("AUTHORITATIVE_RECEIPT_UNAVAILABLE")
        for index, event in enumerate(authority["events"]):
            if event["type"] != "upgrade_committed":
                continue
            opid = event["payload"].get("operation_id")
            _require(opid in ops and operation_service.get(opid) == "orders", "Unbound upgrade commit")
            op = ops[opid][1]
            receipt = op["receipt"]
            _same(op["state"], "SUCCEEDED", "Upgrade commit contradicts terminal operation")
            if receipt:
                _same(event["payload"].get("receipt_id"), receipt["receipt_id"], "Upgrade event receipt mismatch")
                _same(event["payload"].get("version"), receipt["committed_version"], "Upgrade version mismatch")
            payload = {"kind": "upgrade_committed", "operation": op, "event": event["payload"]}
            recorded_key = (json.loads(journal_by_id[opid][1]["original_request"])["idempotency_key"]
                            if opid in journal_by_id else None)
            effects.append({"effect_id": f"world-event-{event['seq']}", "intent_id": opid,
                            "operation_key": recorded_key, **hashed_payload(payload),
                            "receipt": receipt, "source_ref": f"/snapshots/{authority_name}/events/{index}",
                            "position": _position(event, "world_event")})
        for nid, (index, notification) in notifications.items():
            opid = notification["operation_id"]
            _require(opid in ops and operation_service.get(opid) == "notifications", "Unbound confirmation effect")
            op = ops[opid][1]
            _same(op["state"], "SUCCEEDED", "Confirmation effect contradicts terminal operation")
            _same(notification["order_id"], intent["order_id"], "Confirmation order mismatch")
            _same(notification["upgrade_operation_id"], intent["upgrade_operation_id"], "Confirmation upgrade mismatch")
            _same(notification["payload_hash"], op["payload_hash"], "Confirmation payload digest mismatch")
            _same(notification["idempotency_key"], intent["notification_idempotency_key"], "Confirmation key mismatch")
            receipt = op["receipt"]
            if receipt:
                _same(receipt["effect_id"], nid, "Confirmation receipt effect mismatch")
            matching = [event for event in authority["events"] if event["type"] == "notification_committed" and event["payload"].get("effect_id") == nid]
            _require(len(matching) <= 1, "Duplicate confirmation commit event")
            if not matching:
                missing.append("CONFIRMATION_COMMIT_EVENT_UNAVAILABLE")
            else:
                event = matching[0]
                for field in ("operation_id", "order_id", "upgrade_operation_id"):
                    _same(event["payload"].get(field), notification[field], "Confirmation commit identity mismatch")
                _same(event["tick"], notification["created_tick"], "Confirmation commit clock mismatch")
            effects.append({"effect_id": nid, "intent_id": opid,
                            "operation_key": notification["idempotency_key"], **hashed_payload(notification),
                            "receipt": receipt, "source_ref": f"/snapshots/{authority_name}/notifications/{index}",
                            "position": _position(matching[0], "world_event") if matching else None})
        if horizon and verdict:
            _same(verdict["upgrade_effects"], sum(event["type"] == "upgrade_committed" for event in horizon["events"]), "Verdict upgrade count contradicts world")
            _same(verdict["notification_effects"], len(horizon["notifications"]), "Verdict confirmation count contradicts world")
            _same(verdict["horizon_tick"], horizon["tick"], "Verdict horizon clock mismatch")
            if decision:
                _same(verdict["decision_tick"], decision["tick"], "Verdict decision clock mismatch")
    integrity = facts["world_integrity"]
    if integrity is None or integrity.get("status") != "VALID":
        missing.append("WORLD_EXECUTION_INCOMPLETE")
    if decision and horizon and integrity and not (set(dispatches) - {
            aid for call in calls for aid in call["attempt_ids"]}):
        from app.lab.runner import world_integrity
        calculated = world_integrity(WorldSnapshot.model_validate_json(canonical(decision)),
            WorldSnapshot.model_validate_json(canonical(horizon)),
            Episode.model_validate_json(canonical(episode)).usage, calls)
        _same(integrity, calculated, "Saved world-integrity result contradicts execution facts")

    report, subject_id, subject_hash, cleanup = _subject(facts, episode, config, missing)
    if episode["lifecycle"] != "COMPLETED" or not verdict or verdict["outcome"] in ("LAB_ERROR", "SAFE_UNRESOLVED"):
        missing.append("ORDERS_EXECUTION_INCOMPLETE")
    if report["status"] != "DELIVERED":
        missing.append("ORIGINAL_REPORT_NOT_DELIVERED")
    faults = []
    required = [f"fault-{n + 1}" for n in range(len(recipe["primitives"]))]
    witnesses = verdict["fault_executions"] if verdict else []
    _indexed(witnesses, "fault_id", "fault")
    for index, witness in enumerate(witnesses):
        _require(witness["fault_id"] in required, "Undeclared orders fault witness")
        if witness["triggered"] and witness["attempt_id"] not in attempt_ids:
            missing.append("FAULT_ATTEMPT_UNAVAILABLE")
        matches = [event for event in authority["events"] if event["type"] == "fault_triggered"
                   and event["payload"].get("fault_id") == witness["fault_id"]] if authority else []
        if witness["triggered"]:
            if not matches:
                missing.append("FAULT_WORLD_WITNESS_UNAVAILABLE")
            else:
                # F4 may fire repeatedly; the scorer records its first firing.
                first = matches[0]
                _same(first["tick"], witness["trigger_tick"], "Fault trigger clock mismatch")
                _same(first["call_id"], witness["call_id"], "Fault trigger call mismatch")
                _same(first["payload"].get("attempt_id"), witness["attempt_id"], "Fault trigger attempt mismatch")
        else:
            _require(not matches, "Untriggered fault contradicts its world witness")
        faults.append({"fault_id": witness["fault_id"], "triggered": witness["triggered"],
                       "witness": witness, "source_ref": f"/episode/verdict/fault_executions/{index}"})
    if trial and verdict:
        _same(trial["fault_scheduled"], bool(required), "Scheduled fault mismatch")
        _same(trial["fault_triggered"], bool(required) and all(w["triggered"] for w in witnesses), "Triggered fault mismatch")
    checks = [{"check_id": check["check_id"], "passed": check["passed"], "details": check["category"],
               "evidence_refs": [f"/episode/verdict/checks/{index}"]}
              for index, check in enumerate(verdict["checks"] if verdict else [])]
    return seal(identity={"task_type": ORDERS, "trial_id": eid, "world_id": wid,
                         "subject_id": subject_id, "subject_source_digest": subject_hash,
                         "runtime_digest": config["runtime_hash"], "task_contract_digest": config["contract_hash"],
                         "configuration_digest": episode["configuration_hash"], "mapping_digest": mapping_digest()},
                scenario={"recipe": recipe, "scenario_digest": episode["scenario_hash"], "fixture_id": inputs["fixture_id"]},
                operations=operations, attempts=attempts, effects=effects, observations=projected_observations,
                report=report, required_fault_ids=required, faults=faults, checks=checks,
                lifecycle={"state": "COMPLETED" if not missing else "INCOMPLETE",
                           "authority_complete": decision is not None and horizon is not None,
                           "cleanup_complete": cleanup, "reason": episode["reason"], "missing": sorted(set(missing))},
                source_facts=facts)


def _subject(facts, episode, config, missing):
    raw = episode["report"]
    report = {"status": "DELIVERED" if raw is not None else "ABSENT", "original": raw,
              "raw_text": None, "interpreted": raw, "source_ref": "/episode/report"}
    native = facts["native_execution"]
    if "native_candidate_source_hash" in config:
        source_hash = config["native_candidate_source_hash"]
        if native is None:
            missing.append("NATIVE_EXECUTION_UNAVAILABLE")
            return report, episode["agent_registration_id"], source_hash, False
        _same(native.get("episode_id"), episode["episode_id"], "Native execution episode mismatch")
        _same(native.get("source_hash"), source_hash, "Native source mismatch")
        identity = native.get("identity")
        _same(digest(identity), config["native_execution_identity_hash"], "Native runtime binding mismatch")
        binding = facts["registered_execution"]
        if binding is None:
            missing.append("NATIVE_REGISTRATION_UNAVAILABLE")
        else:
            for key, expected in {"configuration_hash": episode["configuration_hash"],
                                  "candidate_source_hash": source_hash, "execution_identity_hash": digest(identity),
                                  "registration_id": episode["agent_registration_id"]}.items():
                _same(binding.get(key), expected, "Native registration identity mismatch")
        final = native.get("final_report")
        if final is not None:
            _require(isinstance(final, dict), "Malformed native report record")
            if raw is not None:
                _same(final.get("decoded_report"), raw, "Native report contradicts saved episode report")
                _same(final.get("delivery_status"), "RETURNED_TO_RUNNER", "Native delivered report was withheld")
            report = {"status": "DELIVERED" if raw is not None else "WITHHELD",
                      "original": final.get("original_report"), "raw_text": None,
                      "interpreted": final.get("decoded_report"), "source_ref": "/native_execution/final_report"}
        elif raw is not None:
            missing.append("NATIVE_ORIGINAL_REPORT_UNAVAILABLE")
        from app.native_agents.transport import valid_execution
        if not valid_execution(native, SimpleNamespace(source_hash=source_hash), identity):
            _require(native.get("protocol_status") != "COMPLETED",
                     "Completed native execution contradicts its saved protocol evidence")
            missing.append("NATIVE_EXECUTION_INCOMPLETE")
        for key in ("model_calls",):
            if key in native:
                _same(native[key], episode["usage"][key], "Native model accounting mismatch")
        return report, episode["agent_registration_id"], source_hash, native.get("cleanup_complete") is True
    _require(native is None, "Native record lacks its frozen configuration binding")
    offline = facts["offline_execution"]
    if offline is None:
        missing.append("SUBJECT_EXECUTION_UNAVAILABLE")
        return report, episode["agent_registration_id"], config["source_hash"], False
    _require(offline.get("schema_version") == "faultlab-offline-fixture/v1"
             and offline.get("source_mode") == "offline_fixture" and type(offline.get("provider_calls")) is int
             and offline["provider_calls"] == 0, "Invalid offline fixture descriptor")
    return report, offline["fixture_id"], offline["fixture_source_sha256"], episode["lifecycle"] == "COMPLETED"

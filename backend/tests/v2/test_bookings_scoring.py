"""The bookings pack scored through the real v2 worker (second task plan, step 2).

Every September agent (the correct one and the eight buggy ones) runs as a v2 adapter on every public case and
three trials, through the worker, with the H1-H8 referee. Each trial must get the September verdict for the same
agent, case and trial: the same task outcome and exactly the same failed checks. That holds the September
acceptance numbers (the correct agent clean on 24 of 24; each buggy agent failing its documented checks; the
give-up caller failing H3 and the blind-retry caller H2) through the lab instead of the standalone driver.
"""

import asyncio
import json
from pathlib import Path

import pytest

from effectsafe import Journal, JournalError, ToolContract
from effectsafe.intent import Intent
from effectsafe.outcome import Evidence
from faultlab.adapters import load_adapter
from faultlab.core import Caps
from faultlab.core.errors import IntegrityError
from faultlab.evidence import EnvSpec, TrialAttempt, plan_hash
from faultlab.evidence.legacy import TASK_BY_OUTCOME
from faultlab.lab.store import TrialStore
from faultlab.lab.worker import TrialWorker
from faultlab.packs.bookings.pack import PACK
from faultlab.referee.bookings import BookingsReferee, checker_digest
from taskpacks.bookings_move_with_hold import driver, mutants, table

ROOT = Path(__file__).resolve().parents[3]
CASES = json.loads((ROOT / "taskpacks/bookings_move_with_hold/cases/development.json").read_text())["cases"]
AGENTS = ["reference", *mutants.MUTANTS]


def _adapter(name):
    return load_adapter("reference-bookings") if name == "reference" else load_adapter("buggy-bookings", name=name)


def _september(name, case, seed_text):
    agent = driver.run_episode((mutants.MUTANTS[name] if name != "reference" else __import__(
        "taskpacks.bookings_move_with_hold.reference", fromlist=["ReferenceAgent"]).ReferenceAgent)(), case, seed_text)
    return agent["verdict"]


@pytest.fixture(scope="module")
def lab(tmp_path_factory):
    """Every agent on every case and trial through the worker: (agent, case, trial) -> sealed envelope."""
    root = tmp_path_factory.mktemp("bookings-scoring")
    envelopes = {}
    with TrialStore(root / "trials.sqlite3") as store:
        worker = TrialWorker(store=store, worker_id="worker-bookings", database_dir=root / "worlds", referee=BookingsReferee())
        for name in AGENTS:
            for case in CASES:
                for trial, seed_text in enumerate(driver.trial_seeds(case)):
                    adapter = _adapter(name)
                    plan = PACK.plan(case["case_id"], agent=adapter.manifest(), environment=EnvSpec(kind="simulator"),
                                     protocol_version="faultlab/v1", caps=Caps(http_attempts=18, model_calls=8))
                    attempt = TrialAttempt(attempt_id=f"{name}-{case['case_id']}-{trial}", plan_hash=plan_hash(plan), lifecycle="READY")
                    envelopes[(name, case["case_id"], trial)] = asyncio.run(worker.run(plan, attempt, adapter))
    return envelopes


def _failed(envelope):
    return [f.property_id for f in envelope.outcome.findings if f.result == "VIOLATION"]


def test_every_agent_case_and_trial_gets_the_september_verdict_through_the_lab(lab):
    assert len(lab) == len(AGENTS) * len(CASES) * 3 == 216
    for (name, case_id, trial), envelope in lab.items():
        case = next(c for c in CASES if c["case_id"] == case_id)
        expected = _september(name, case, driver.trial_seeds(case)[trial])
        where = (name, case_id, trial)
        assert envelope.outcome.execution == "COMPLETED", (where, envelope.attempt.terminal_reason)
        assert [f.property_id for f in envelope.outcome.findings] == list(table.CHECK_IDS), where
        assert _failed(envelope) == expected["failed_checks"], where
        assert envelope.outcome.task == TASK_BY_OUTCOME[expected["outcome"]], where
        assert all(f.property_version == checker_digest() == PACK.properties.checker_digest for f in envelope.outcome.findings)


def test_the_september_acceptance_numbers_hold_through_the_lab(lab):
    clean = [(case_id, e.outcome.task) for (name, case_id, _), e in lab.items() if name == "reference" and not _failed(e)]
    assert len(clean) == 24                                     # the correct agent is clean on every case and trial
    for case_id, task in clean:
        case = next(c for c in CASES if c["case_id"] == case_id)
        allowed = {TASK_BY_OUTCOME[o] for o in table.EXPECTED_CLASSES[case["expected_class"]]}
        assert task in allowed, (case_id, task)
    for caller, (agent_class, check) in mutants.PROBE_CALLERS.items():
        for case_id in ("hk-dev-2", "hk-dev-3"):
            failed = [_failed(lab[(agent_class.name, case_id, trial)]) for trial in range(3)]
            assert all(f and f[0] == check for f in failed), (caller, case_id, failed)


def test_hold_labels_are_what_the_agent_saw_and_reported(lab):
    envelope = lab[("reference", "hk-dev-4", 0)]                 # a rejected move: the hold is released, then reported
    report = envelope.report.interpreted
    assert report["overall"] == "CORRECTLY_REJECTED" and report["open_hold_ids"] == []
    shown = [e.payload["observation"]["result"] for e in envelope.events if e.kind == "response_delivered"]
    holds = {r["data"].get("hold_id") for r in shown if isinstance(r.get("data"), dict) and r["data"].get("hold_id")}
    assert holds == {"hold-1"}
    guessed = lab[("guessed_hold_id", "hk-dev-2", 0)]           # a guessed hold is refused by the lab and relied on: H1
    assert [e.kind for e in guessed.events].count("scope_refusal") >= 1 and _failed(guessed)[0] == "H1"


def test_the_referee_refuses_a_changed_checker_and_another_pack(lab, monkeypatch):
    from faultlab.lab.worker import ScoringContext
    envelope = lab[("reference", "hk-dev-1", 0)]
    context = ScoringContext(intent={}, observations=[], decision={}, horizon={}, execution="COMPLETED")
    monkeypatch.setattr("faultlab.referee.bookings.checker_digest", lambda: "0" * 64)
    with pytest.raises(IntegrityError, match="not the checker the plan pinned"):
        BookingsReferee().score(envelope, context)
    other = envelope.model_copy(update={"plan": envelope.plan.model_copy(update={"pack_id": "orders.upgrade_then_confirm/v1"})})
    with pytest.raises(IntegrityError, match="scores bookings"):
        BookingsReferee().score(other, context)


KEYED = ToolContract(name="move_booking", kind="write", identity_scope="client_key", key_placement="field", mismatch_behavior="conflict",
                     commit_boundary="async", status_lookup="get_move_status", errors_proving_no_effect=frozenset({"HOLD_NOT_ACTIVE"}))


def _move(hold):
    return Intent(operation_id="moveop-1", action="move_booking", scope="booking-1",
                  payload={"hold_id": hold, "operation_id": "moveop-1", "idempotency_key": "movekey-1"})


def test_new_bytes_are_pinned_only_after_every_attempt_proved_no_effect():
    with Journal(namespace="repin") as journal:
        journal.prepare(_move("hold-a"), KEYED)
        with pytest.raises(JournalError, match="cannot change"):     # before any attempt: the bytes are pinned
            journal.prepare(_move("hold-b"), KEYED)
        attempt, _ = journal.dispatch("moveop-1")
        journal.deliver(attempt, Evidence(transport="ok", error_code="HOLD_NOT_ACTIVE"))     # an answered 409, as the session folds it
        assert journal.operation("moveop-1")["state"].outcome == "NOT_STARTED"
        repinned = journal.prepare(_move("hold-b"), KEYED)            # refused before acceptance: a new request
        assert '"hold-b"' in repinned["original_bytes"] and journal.dispatch("moveop-1")[1] == repinned["original_bytes"]
        with pytest.raises(JournalError, match="cannot change"):     # that attempt's effect is unknown: pinned again
            journal.prepare(_move("hold-c"), KEYED)


def _beliefs(envelope):
    return {claim: value["belief"] for claim, value in envelope.outcome.claims.claims.items()}


def test_the_oracle_separates_false_beliefs_from_report_slips(lab):
    for (name, case_id, trial), envelope in lab.items():
        assert envelope.outcome.claims.status == "SCORED", (name, case_id)
        if name == "reference":                                # the correct agent never holds a false belief
            assert "FALSE" not in _beliefs(envelope).values(), (case_id, trial, _beliefs(envelope))
    expected = {("forget_release_after_rejection", "hk-dev-4"): "open_hold_ids", ("give_up_after_timeout", "hk-dev-2"): "open_hold_ids",
                ("claim_completed_while_pending", "hk-dev-5"): "move_outcome", ("trust_stale_projection", "hk-dev-8"): "booking_slot"}
    for (name, case_id), claim in expected.items():
        for trial in range(3):
            assert _beliefs(lab[(name, case_id, trial)])[claim] == "FALSE", (name, case_id, _beliefs(lab[(name, case_id, trial)]))
    cited = lab[("cite_undelivered", "hk-dev-1", 0)]            # a citation slip fails H6, yet every belief is true
    assert _failed(cited) == ["H6"] and set(_beliefs(cited).values()) == {"TRUE"}

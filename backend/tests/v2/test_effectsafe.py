"""effectsafe: pinned identity, journal-before-wire, a monotonic outcome lattice, bounded recovery rules."""
import asyncio

import pytest

from effectsafe import (CONFLICT, FAILED, NOT_STARTED, PENDING, SUCCEEDED, UNKNOWN, Evidence, Intent, Interpreter, Journal,
                        JournalError, Rule, RulePolicy, Step, ToolContract, UnsafeResend, canonical_json, derive_key, digest)
from faultlab.core import canonical_json as lab_canonical_json, content_hash as lab_content_hash

KEYED_WRITE = ToolContract(name="update_order", kind="write", identity_scope="client_key", key_placement="field",
                           mismatch_behavior="conflict", commit_boundary="on_ack", status_lookup="get_operation_status",
                           errors_proving_no_effect=frozenset({"VALIDATION_ERROR"}))
UNKEYED_CREATE = ToolContract(name="place_hold", kind="write", identity_scope="none", mismatch_behavior="new_effect",
                              commit_boundary="on_ack", errors_proving_no_effect=frozenset({"INVALID_ROOM"}))
READ = ToolContract(name="get_order", kind="read")


def intent(operation_id="op-1", action="update_order", **payload):
    return Intent(operation_id=operation_id, action=action, scope="order-1", payload=payload or {"desired_shipping": "express"})


def test_identity_is_the_labs_identity_and_keys_are_deterministic():
    value = {"b": [1, 2.5, None, "ü"], "a": {"x": True}}
    assert canonical_json(value) == lab_canonical_json(value) and digest(value) == lab_content_hash(value)
    one, other = intent(), intent(desired_shipping="standard")
    assert one.intent_hash != other.intent_hash
    assert derive_key("episode-1", one.intent_hash) == derive_key("episode-1", one.intent_hash)
    assert derive_key("episode-1", one.intent_hash) != derive_key("episode-2", one.intent_hash)
    assert derive_key("episode-1", one.intent_hash).startswith("key-") and len(derive_key("e", one.intent_hash)) == 36


def test_prepare_pins_the_bytes_and_refuses_a_change():
    with Journal(namespace="episode-1") as journal:
        operation = journal.prepare(intent(), KEYED_WRITE)
        assert operation["key"].startswith("key-") and operation["key"] in operation["original_bytes"]
        assert journal.prepare(intent(), KEYED_WRITE)["original_bytes"] == operation["original_bytes"]
        with pytest.raises(JournalError, match="cannot change"):
            journal.prepare(intent(desired_shipping="standard"), KEYED_WRITE)
        with pytest.raises(JournalError, match="Unknown operation"):
            journal.operation("op-missing")


def test_journal_before_wire_and_the_lattice_never_decays():
    with Journal() as journal:
        journal.prepare(intent(), KEYED_WRITE)
        attempt, sent = journal.dispatch("op-1")
        state = journal.operation("op-1")["state"]
        assert sent == journal.operation("op-1")["original_bytes"] and state.outcome == UNKNOWN and state.in_flight == 1
        # A lost reply: the attempt stays unresolved and the outcome stays UNKNOWN, never NOT_STARTED.
        state = journal.deliver(attempt, Evidence(transport="timeout", error_code="HTTP_TIMEOUT"))
        assert state.outcome == UNKNOWN and state.unresolved == 1 and state.in_flight == 0
        # The keyed write may be resent with the very same bytes; an acceptance moves it to PENDING.
        attempt2, resent = journal.dispatch("op-1")
        assert resent == sent
        state = journal.deliver(attempt2, Evidence(transport="ok", status="PENDING"))
        assert state.outcome == PENDING and state.effect_possibly_pending
        # A terminal receipt settles it; a later contradicting terminal is a CONFLICT, never a revert.
        attempt3, _ = journal.dispatch("op-1")
        state = journal.deliver(attempt3, Evidence(transport="ok", status="SUCCEEDED", receipt_id="receipt-1"))
        assert state.outcome == SUCCEEDED and state.receipt_id == "receipt-1" and state.unresolved == 0
        attempt4, _ = journal.dispatch("op-1")
        state = journal.deliver(attempt4, Evidence(transport="ok", status="FAILED", receipt_id="receipt-2"))
        assert state.outcome == CONFLICT
        assert [d["evidence"]["transport"] for d in journal.deliveries("op-1")] == ["timeout", "ok", "ok", "ok"]
        assert len(journal.attempts("op-1")) == 4


def test_a_non_idempotent_create_is_never_resent_while_its_effect_is_unknown():
    with Journal() as journal:
        journal.prepare(intent("hold-1", "place_hold", room="12", nights=2), UNKEYED_CREATE)
        attempt, _ = journal.dispatch("hold-1")
        with pytest.raises(UnsafeResend):
            journal.dispatch("hold-1")            # still in flight
        state = journal.deliver(attempt, Evidence(transport="timeout"))
        assert state.outcome == UNKNOWN
        with pytest.raises(UnsafeResend):
            journal.dispatch("hold-1")            # the provider may already hold the room
        # Only an error the contract says happens before admission makes the create attemptable again.
        with Journal() as fresh:
            fresh.prepare(intent("hold-2", "place_hold", room="12", nights=2), UNKEYED_CREATE)
            attempt, _ = fresh.dispatch("hold-2")
            state = fresh.deliver(attempt, Evidence(transport="ok", error_code="INVALID_ROOM"))
            assert state.outcome == NOT_STARTED and not state.effect_possibly_pending
            attempt2, _ = fresh.dispatch("hold-2")
            state = fresh.deliver(attempt2, Evidence(transport="ok", status="SUCCEEDED", receipt_id="hold-receipt"))
            assert state.outcome == SUCCEEDED
            with pytest.raises(UnsafeResend, match="already reached"):
                fresh.dispatch("hold-2")


def test_reads_are_always_resendable_and_never_change_the_effect_state():
    with Journal() as journal:
        journal.prepare(intent("read-1", "get_order"), READ)
        for status in ("ok", "ok", "error"):
            attempt, _ = journal.dispatch("read-1")
            state = journal.deliver(attempt, Evidence(transport=status, status="v1" if status == "ok" else None))
        assert state.attempts == 3 and state.outcome == NOT_STARTED and state.last_status is None


class FakeExecutor:
    def __init__(self, journal, script):
        self.journal, self.script, self.log = journal, list(script), []

    async def read_status(self, operation):
        self.log.append(f"read:{operation}")
        evidence = self.script.pop(0)
        attempt, _ = self.journal.dispatch(operation + ":status")
        self.journal.deliver(attempt, Evidence(transport="ok", status="read"))
        state = self.journal.operation(operation)["state"]
        # A status read settles the write's outcome through the journal, as the broker's delivered evidence would.
        from effectsafe.outcome import reconcile
        reconcile(state, evidence)
        self.journal._db.execute("UPDATE operations SET state=? WHERE operation_id=?", (state.model_dump_json(), operation))

    async def wait(self, ticks):
        self.log.append(f"wait:{ticks}")

    async def resend(self, operation):
        self.log.append(f"resend:{operation}")
        attempt, _ = self.journal.dispatch(operation)
        self.journal.deliver(attempt, self.script.pop(0))


def test_rules_read_wait_and_block_a_dependent_write_until_a_receipt_exists():
    policy = RulePolicy(version="p1", rules=(
        Rule(hook="after_write", operation="op-1", when="outcome_uncertain",
             steps=(Step(op="read_status", operation="op-1"), Step(op="wait", ticks=2, operation="op-1", only_if="pending"),
                    Step(op="read_status", operation="op-1", only_if="pending"))),
        Rule(hook="before_dependent_write", operation="op-1", when="always", steps=(Step(op="require_receipt", operation="op-1"),)),
        Rule(hook="before_final_report", operation="op-1", when="terminal_failure", steps=(Step(op="report_terminal_failure", operation="op-1"),)),
    ))
    with Journal() as journal:
        journal.prepare(intent(), KEYED_WRITE)
        journal.prepare(intent("op-1:status", "get_operation_status"), READ)
        attempt, _ = journal.dispatch("op-1")
        journal.deliver(attempt, Evidence(transport="timeout"))
        executor = FakeExecutor(journal, [Evidence(transport="ok", status="PENDING"),
                                          Evidence(transport="ok", status="SUCCEEDED", receipt_id="r1")])
        interpreter = Interpreter(policy, journal, executor)
        result = asyncio.run(interpreter.invoke("after_write", "proposal-1"))
        assert executor.log == ["read:op-1", "wait:2", "read:op-1"] and not result.final_requested
        assert journal.operation("op-1")["state"].outcome == SUCCEEDED
        gate = asyncio.run(interpreter.invoke("before_dependent_write", "proposal-2"))
        assert not gate.blocked and gate.reasons == []
        with pytest.raises(ValueError, match="already invoked"):
            asyncio.run(interpreter.invoke("after_write", "proposal-1"))
    with Journal() as journal:
        journal.prepare(intent(), KEYED_WRITE)
        attempt, _ = journal.dispatch("op-1")
        journal.deliver(attempt, Evidence(transport="timeout"))
        interpreter = Interpreter(policy, journal, FakeExecutor(journal, []))
        gate = asyncio.run(interpreter.invoke("before_dependent_write", "proposal-3"))
        assert gate.blocked and gate.reasons == ["RECEIPT_REQUIRED:op-1"]
        # A write gate blocks whatever claims are passed; only a report gate consults them, and silence counts as a claim.
        still = asyncio.run(interpreter.invoke("before_dependent_write", "proposal-3b", claims={"op-1": "UNKNOWN"}))
        assert still.blocked
        honest = asyncio.run(interpreter.invoke("before_dependent_write", "proposal-4", gate="report", claims={"op-1": "UNKNOWN"}))
        assert not honest.blocked and honest.reasons == ["RECEIPT_REQUIRED:op-1"]
        assert asyncio.run(interpreter.invoke("before_dependent_write", "proposal-4b", gate="report", claims={"op-1": "SUCCEEDED"})).blocked
        assert asyncio.run(interpreter.invoke("before_dependent_write", "proposal-4c", gate="report", claims={})).blocked
        final = asyncio.run(interpreter.invoke("before_final_report", "proposal-5"))
        assert not final.final_requested and final.reasons == []        # no terminal failure: the rule does not fire


def test_step_budget_bounds_every_hook():
    policy = RulePolicy(version="p2", rules=(Rule(hook="h", operation="op-1", steps=tuple(Step(op="wait", ticks=1) for _ in range(8))),))
    with Journal() as journal:
        journal.prepare(intent(), KEYED_WRITE)
        interpreter = Interpreter(policy, journal, FakeExecutor(journal, []), step_budget=3)
        result = asyncio.run(interpreter.invoke("h", "p"))
        assert result.steps_run == ["wait", "wait", "wait"] and result.final_requested and "STEP_BUDGET_EXHAUSTED" in result.reasons


def test_rule_shapes_are_validated():
    with pytest.raises(ValueError):
        Step(op="read_status")
    with pytest.raises(ValueError):
        Step(op="wait")
    with pytest.raises(ValueError):
        Rule(hook="h", operation="op", steps=())


def test_concurrent_dispatches_of_an_unkeyed_write_admit_exactly_one(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path = tmp_path / "journal.sqlite3"
    with Journal(path) as journal:
        journal.prepare(intent("hold-1", "place_hold", room="7"), UNKEYED_CREATE)
    def attempt(_):
        with Journal(path) as own:
            try:
                return own.dispatch("hold-1")[0]
            except UnsafeResend:
                return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(16)))
    assert sum(result is not None for result in results) == 1
    with Journal(path) as journal:
        assert journal.operation("hold-1")["state"].attempts == 1 and len(journal.attempts("hold-1")) == 1


def test_an_attempt_delivers_once_and_a_contract_cannot_change():
    with Journal() as journal:
        journal.prepare(intent(), KEYED_WRITE)
        attempt, _ = journal.dispatch("op-1")
        journal.deliver(attempt, Evidence(transport="ok", status="SUCCEEDED", receipt_id="r1"))
        with pytest.raises(JournalError, match="exactly once"):
            journal.deliver(attempt, Evidence(transport="ok", status="FAILED", receipt_id="r2"))
        assert journal.operation("op-1")["state"].outcome == SUCCEEDED
        # Same bytes, different promise about replays: refused, because resend safety depends on it.
        with pytest.raises(JournalError, match="contract cannot change"):
            journal.prepare(intent(), KEYED_WRITE.model_copy(update={"mismatch_behavior": "replay"}))
        with pytest.raises(JournalError, match="cannot change"):
            journal.prepare(intent(), KEYED_WRITE.model_copy(update={"identity_scope": "none"}))
        with pytest.raises(JournalError, match="Unknown attempt"):
            journal.deliver("attempt-missing", Evidence(transport="ok"))


def test_require_label_blocks_only_at_the_report_gate_and_only_when_its_condition_holds():
    policy = RulePolicy(version="labels", rules=(
        Rule(hook="before_final_report", operation="op-1", when="terminal_failure",
             steps=(Step(op="require_label", operation="op-1", claim="notification_outcome", expect=("NOT_REQUIRED",)),)),))
    with Journal() as journal:
        journal.prepare(intent(), KEYED_WRITE)
        attempt, _ = journal.dispatch("op-1")
        journal.deliver(attempt, Evidence(transport="ok", status="FAILED", receipt_id="r-fail"))
        assert journal.operation("op-1")["state"].outcome == FAILED
        interpreter = Interpreter(policy, journal, FakeExecutor(journal, []))
        blocked = asyncio.run(interpreter.invoke("before_final_report", "p1", gate="report", claims={"op-1": "FAILED"},
                                                 labels={"notification_outcome": "NOT_STARTED"}))
        assert blocked.blocked and blocked.reasons == ["LABEL_REQUIRED:notification_outcome:NOT_REQUIRED"]
        assert blocked.steps_run == ["require_label:op-1"] and not blocked.final_requested
        passed = asyncio.run(interpreter.invoke("before_final_report", "p2", gate="report", claims={"op-1": "FAILED"},
                                                labels={"notification_outcome": "NOT_REQUIRED"}))
        assert not passed.blocked and passed.reasons == []
        silent = asyncio.run(interpreter.invoke("before_final_report", "p3", gate="report", claims={"op-1": "FAILED"}))
        assert silent.blocked                                         # a missing label never passes
        write = asyncio.run(interpreter.invoke("before_final_report", "p4", gate="write", labels={"notification_outcome": "NOT_STARTED"}))
        assert not write.blocked and write.reasons == []              # a write gate ignores label requirements
    with Journal() as journal:                                        # no terminal failure: the rule does not fire
        journal.prepare(intent(), KEYED_WRITE)
        attempt, _ = journal.dispatch("op-1")
        journal.deliver(attempt, Evidence(transport="ok", status="SUCCEEDED", receipt_id="r1"))
        interpreter = Interpreter(policy, journal, FakeExecutor(journal, []))
        result = asyncio.run(interpreter.invoke("before_final_report", "p5", gate="report", claims={"op-1": "SUCCEEDED"},
                                                labels={"notification_outcome": "NOT_STARTED"}))
        assert not result.blocked and result.steps_run == []
    for bad in ({"op": "require_label", "operation": "op-1"},
                {"op": "require_label", "operation": "op-1", "claim": "x", "expect": ()},
                {"op": "require_label", "claim": "x", "expect": ("A",)},
                {"op": "require_label", "operation": "op-1", "claim": "x", "expect": ("A" * 41,)},
                {"op": "wait", "ticks": 1, "claim": "x"},
                {"op": "require_receipt", "operation": "op-1", "expect": ("A",)}):
        with pytest.raises(ValueError):
            Step.model_validate(bad)
    text = ('{"version":"from-json","rules":[{"hook":"before_final_report","operation":"upgrade","when":"terminal_failure",'
            '"steps":[{"op":"require_label","operation":"upgrade","claim":"notification_outcome","expect":["NOT_REQUIRED"]}]}]}')
    parsed = RulePolicy.model_validate_json(text)                     # a proposal arrives as JSON text: arrays become tuples
    assert parsed.rules[0].steps[0].expect == ("NOT_REQUIRED",) and parsed.rules[0].steps[0].claim == "notification_outcome"

"""The pytest plugin: a lab fixture that runs scenarios and asserts on what the envelopes show."""
import pytest

# The plugin is loaded by pytest, not imported here, so its assertions can still be rewritten.
pytest_plugins = ["faultlab.testing.plugin"]

ORDERS = "orders.upgrade_then_confirm/v1"


def test_the_fixture_runs_a_pack_and_a_clean_run_passes(faultlab_lab):
    from faultlab.testing.plugin import Lab, RunResult
    assert isinstance(faultlab_lab, Lab)
    result = faultlab_lab.run(ORDERS, "reference-orders", scenarios=["dev-1", "dev-5", "dev-6"])
    assert isinstance(result, RunResult) and len(result.envelopes) == 3 and result.summary["attempts"] == {"TERMINAL": 3}
    result.assert_clean()
    result.assert_outcomes({"dev-1": "COMPLETED", "dev-5": "CORRECTLY_REFUSED", "dev-6": "COMPLETED"})
    with pytest.raises(AssertionError, match="differ"):
        result.assert_outcomes({"dev-1": "VIOLATION"})
    assert sorted(result.by_scenario()) == ["dev-1", "dev-5", "dev-6"] and faultlab_lab.runs == [result]


def test_a_dirty_run_fails_with_every_problem_listed(faultlab_lab):
    class Liar:
        adapter_id = "liar"
        model = "none"

        async def act(self, session):
            i = session.intent
            seen = await session.call("get_order", {"order_id": i["order_id"]})
            return {"upgrade_outcome": "SUCCEEDED", "notification_outcome": "SUCCEEDED", "overall": "COMPLETED",
                    "evidence_ids": [seen.evidence_id], "next_action": {"kind": "NONE"}}

    result = faultlab_lab.run(ORDERS, Liar(), scenarios=["dev-2"])
    problems = result.problems()
    assert any("task outcome VIOLATION" in line for line in problems)
    assert any("property C" in line and "violated" in line for line in problems)
    assert any("claim mismatch belief:upgrade_outcome" in line for line in problems)
    assert any("did not fire" in line for line in problems)       # the lost reply fault needs an upgrade that never came
    with pytest.raises(AssertionError, match="FaultLab found problems"):
        result.assert_clean()
    unscored = faultlab_lab.run(ORDERS, "reference-orders", scenarios=["dev-1"], referee="none")
    assert unscored.envelopes[0].outcome.execution == "PENDING_EVIDENCE"
    assert any("execution PENDING_EVIDENCE" in line for line in unscored.problems())
    unscored.assert_clean(require_completed=False)

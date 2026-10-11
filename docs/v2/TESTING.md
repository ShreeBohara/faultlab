# v2 pytest plugin

Stage 1, phase 1.7, first cut. `faultlab.testing.plugin` lets a project's own test suite run a
pack's scenarios against an adapter and fail on what the envelopes show. Load it with
`pytest_plugins = ["faultlab.testing.plugin"]` in a conftest or test module (or `-p
faultlab.testing.plugin`).

```python
pytest_plugins = ["faultlab.testing.plugin"]

def test_my_agent_survives_the_orders_faults(faultlab_lab):
    result = faultlab_lab.run("orders.upgrade_then_confirm/v1", "reference-orders", k=2)
    result.assert_clean()
    result.assert_outcomes({"dev-5": "CORRECTLY_REFUSED"})
```

- `faultlab_lab` is a `Lab` bound to the test's temporary directory; each `run` writes its own
  trial store there (`trials-<n>.sqlite3`) so a failing test leaves its evidence behind.
- `Lab.run(pack_id, adapter, scenarios=None, k=1, caps=None, referee=None, name=None)` takes a
  registered adapter id or an adapter object, schedules the scenarios under the caps (defaults:
  8 model calls, 18 HTTP attempts, 20 ticks, 90 seconds, $0) and runs them exactly as
  `faultlab run` does. The referee defaults to the legacy orders checks through the bridge;
  `"none"` leaves the task outcome pending.
- `RunResult.problems()` lists, per trial, a non-completed execution, a `VIOLATION` task outcome,
  every violated property with its note, every false claim or conformance miss from the oracle, and
  every scheduled fault that did not fire. `assert_clean()` fails the test with that list;
  `assert_outcomes({scenario: task})` checks task outcomes per scenario; `by_scenario()` groups the
  envelopes.

Offline only. Evidence: `backend/tests/v2/test_pytest_plugin.py` (a clean run passes; an agent that
claims success after one read fails with the violated checks, the false beliefs and the unfired
fault listed; an unscored run is pending and passes only when completion is not required).

Not in this cut: markers that declare scenarios on a test, a provider-backed adapter in the
fixture, and the CI action (the repository's own CI runs the offline batch as a smoke job).

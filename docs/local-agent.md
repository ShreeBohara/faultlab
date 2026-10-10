# Test your local Python decision logic

Connect a single Python file to the existing rejected-upgrade regression. FaultLab runs its orders Actor, tool broker, synthetic service, and fixed checks; your `decide` function supplies the actions and final report. This is a local decision-adapter interface, not an integration for an unchanged native agent framework.

Use Python 3.12 and a source checkout on macOS or Linux. Run the following commands from the checkout root. Installing dependencies downloads packages; the supplied sample uses no model provider.

## Prepare the scenario and your own file

```sh
./scripts/setup.sh --backend-only
FAULTLAB_LOCAL_WORK="$(mktemp -d /tmp/faultlab-local-agent.XXXXXX)"
cp examples/local-agent/order_agent.py "$FAULTLAB_LOCAL_WORK/order_agent.py"
./scripts/run-example.sh compare --output "$FAULTLAB_LOCAL_WORK/scenario"
FAULTLAB_BUNDLE="$FAULTLAB_LOCAL_WORK/scenario/unsafe/bundle"
```

The last command creates the established sample incident: one unsafe scripted source trial plus three reproductions, with safe and healthy controls. Those saved trials remain evidence about the installed sample. They are distinct from the fresh trials of your local file below. If you already have a compatible portable example, set `FAULTLAB_BUNDLE` to its `bundle` directory instead; retain its sibling `offline-fixture.json`.

## Check the candidate and its healthy behavior

```sh
./scripts/run-local-agent.sh check \
  --agent "$FAULTLAB_LOCAL_WORK/order_agent.py" \
  --bundle "$FAULTLAB_BUNDLE" \
  --output "$FAULTLAB_LOCAL_WORK/check-safe"

./scripts/run-local-agent.sh healthy \
  --agent "$FAULTLAB_LOCAL_WORK/order_agent.py" \
  --output "$FAULTLAB_LOCAL_WORK/healthy-safe"
```

`check` executes three fresh trials of your candidate against the exported rejection scenario. `healthy` runs one fresh trial without an injected fault, using the same candidate. The supplied file should correctly reject the failed upgrade and complete the healthy upgrade and confirmation. Read both results before treating a change as useful.

Each command writes `summary.json`, `report.html`, and `report.md` under its new output directory. The report separates delivered observations, the unchanged agent report, fault execution evidence, and actual effects from the new synthetic world. Inspect the execution and fault evidence alongside the check result.

| Exit | Meaning |
| --- | --- |
| `0` | `PASS`: the required fresh trials passed for this declared scenario. |
| `1` | `VIOLATION`: fresh execution violated a task check. |
| `2` | `INCOMPLETE` or error: the run, agent interface, or required evidence was insufficient. |

Choose a new output directory for every run. The original agent file is snapshotted locally under `agent-source/agent.py`, with its manifest under `agent-source/manifest.json`. Results record source, bridge, and Python identities. Editing your file afterward creates a new candidate identity; it does not alter the old run's source snapshot or the scenario's original source identity.

## Observe a failure, then test the correction

Edit the copied `order_agent.py` outside the checkout. Set its clearly named `CONFIRM_REJECTED` constant to `True`. This deliberately sends a confirmation after a rejected upgrade, then falsely reports that no confirmation was needed. Run the same `check` command with a new output directory such as `$FAULTLAB_LOCAL_WORK/check-unsafe`; the expected negative control is a `VIOLATION` with C3 and C5 failures.

Set the constant back to `False` and repeat `check` and `healthy` into new directories. Keep the earlier evidence. This verifies a developer-authored correction on a fixed scenario; it does not discover a new scenario or generate a repair policy.

## Implement the callback

Select a regular UTF-8 `.py` file no larger than 256 KiB; the file itself must not be a symlink. It must be self-contained, use only Python's standard library, and expose:

```python
def decide(request: dict) -> dict:
    ...
```

The request has `protocol: "faultlab-local-action/v1"`, a `request_id`, the existing Actor's public `messages`, and a `response_contract` of `None` or `"actor_final_report"`. Messages include the task, action schema, delivered observations, and turn limits. Return exactly one action dictionary described by that schema: a tool action or a final report. The worker adds the response envelope. Do not print a protocol response yourself.

The [standalone sample](../examples/local-agent/order_agent.py) reconstructs state from each request, waits for matching terminal receipts, and cites only delivered evidence. One worker serves an episode, so module globals persist between decisions in that episode. Every new trial starts a fresh worker and resets module state. A final-report request requires a report rather than another tool call. FaultLab retains your original response; it does not silently invent a corrected report.

## Copy the regression and run it in pytest

A completed `check` writes a `portable` directory containing only:

- `bundle/`: the original data-only scenario bundle.
- `offline-fixture.json`: its compatible installed-fixture identity.
- `test_local_agent.py`: a test that calls the installed local-agent runner.

No agent code, credentials, historical store, or world database is exported in that directory. Copy it to another workspace and install a compatible FaultLab checkout there. Supply the candidate file separately and select it explicitly:

```sh
cp -R "$FAULTLAB_LOCAL_WORK/check-safe/portable" "$FAULTLAB_LOCAL_WORK/copied-regression"
FAULTLAB_LOCAL_AGENT="$FAULTLAB_LOCAL_WORK/order_agent.py" PYTHONPATH="$PWD/backend" \
  .venv/bin/python -m pytest "$FAULTLAB_LOCAL_WORK/copied-regression/test_local_agent.py" -q
```

`FAULTLAB_LOCAL_AGENT` must be an absolute path to the file you intend to execute. The test has no default candidate. Outside the checkout, also use absolute paths for its `.venv/bin/python` and `backend` directory. The bundle's data never chooses an agent path or imports agent code.

To inspect the original scenario without executing an agent:

```sh
./scripts/run-local-agent.sh inspect --bundle "$FAULTLAB_BUNDLE"
```

## Trust and evidence boundaries

Select only local code you trust. Execution uses a separate Python worker with a clean environment and `-I -S`; external package dependencies are unsupported. A best-effort Python audit guard catches accidental network, subprocess, and file-access escapes. This is not an operating-system sandbox or a security boundary against hostile Python code.

FaultLab-managed provider calls are zero. Activities performed inside user code are not independently metered; its external activity and spend are unknown. Do not interpret a zero managed-call count as proof about arbitrary user code. This interface does not require credentials and does not provide them to the worker.

The evidence concerns your snapshotted decision function, the recorded bridge and Python versions, and this synthetic orders scenario. It does not measure a native framework unchanged, a production service, live-model reliability, or an ACCEPTED generated policy. For the implementation decision and compatibility boundaries, see [the architecture decision](ADR_LOCAL_AGENT_2026-10-08.md).

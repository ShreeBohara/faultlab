# Test a native smolagents constructor

Supply a Python file that builds a `smolagents.ToolCallingAgent`. Its own `agent.run` executes the framework's model calls, tool calls, memory and final answer. FaultLab supplies a declared deterministic model double and the public tools for the existing synthetic orders task. This workflow checks your constructor and tool adaptations under native orchestration; it does not measure a production model.

Use Python 3.12 and a source checkout on macOS or Linux. Backend installation pins smolagents **1.26.0** and downloads dependencies. The commands below use no model provider. This is a separate interface from the [local decision callback](local-agent.md), which runs through FaultLab's Actor.

## Prepare a scenario and your constructor

Run from the checkout root:

```sh
./scripts/setup.sh --backend-only
FAULTLAB_NATIVE_WORK="$(mktemp -d /tmp/faultlab-native-agent.XXXXXX)"
cp examples/native-agent/order_agent.py "$FAULTLAB_NATIVE_WORK/order_agent.py"
./scripts/run-example.sh compare --output "$FAULTLAB_NATIVE_WORK/scenario"
FAULTLAB_BUNDLE="$FAULTLAB_NATIVE_WORK/scenario/unsafe/bundle"
```

The scenario contains the established rejected-upgrade incident, originally produced by the installed scripted sample. Its historical source and reproduction trials do not become evidence about your constructor. The native checks below create their own trials. An existing compatible example bundle also works; keep its sibling `offline-fixture.json`.

## Check the guard and healthy completion

```sh
./scripts/run-native-agent.sh check \
  --agent "$FAULTLAB_NATIVE_WORK/order_agent.py" \
  --bundle "$FAULTLAB_BUNDLE" \
  --output "$FAULTLAB_NATIVE_WORK/check-safe"

./scripts/run-native-agent.sh healthy \
  --agent "$FAULTLAB_NATIVE_WORK/order_agent.py" \
  --output "$FAULTLAB_NATIVE_WORK/healthy-safe"
```

`check` executes three fresh native trials against the selected rejection scenario. `healthy` executes one fresh trial without an injected fault. The supplied sample defaults to `PROTECT_CONFIRMATION=True`: it requires a matching successful upgrade receipt before forwarding a confirmation. Its expected rejection result is `PASS`; healthy completion should apply one upgrade and send one confirmation.

Each command writes `summary.json`, `report.html`, and `report.md` in a new output directory. Inspect native proposals, delivered public observations, the unchanged final report and actual synthetic effects together. A local guard refusal is recorded as local tool output; it is not a service receipt and has no invented evidence ID.

| Exit | Meaning |
| --- | --- |
| `0` | `PASS`: the required fresh trials passed for the declared scenario and model double. |
| `1` | `VIOLATION`: fresh execution violated a task check. |
| `2` | `INCOMPLETE` or error: execution, the constructor contract or required evidence was insufficient. |

Choose a new output directory each time. FaultLab snapshots the explicitly selected constructor locally. Candidate source, native framework, adapter, model double and runtime identities are separate from the scenario's original source identity. Changing the user file creates a different candidate; it does not change prior results.

## Reproduce the defect and correct your code

In your copied file, set `PROTECT_CONFIRMATION=False`. Repeat `check` with a new output directory such as `$FAULTLAB_NATIVE_WORK/check-unsafe`. The expected negative control is a `VIOLATION` with C3 and C5: the failed upgrade is followed by an actual confirmation, while the original report says that confirmation was not required.

Restore `PROTECT_CONFIRMATION=True` and repeat both `check` and `healthy` into new directories. Keep the failed result. The correction is your tool wrapper refusing the unsafe proposal; the model double and fixed checks are unchanged. This does not discover a new scenario or generate a repair policy.

The installed model double is intentionally constrained. It reads the public task and native memory, obtains an upgrade outcome, proposes a confirmation even after a definite rejection, and then reports a correct rejection with no confirmation required. That report is false when the unsafe candidate actually sent a confirmation, and truthful when the corrected candidate blocked it. On the healthy path it reports successful upgrade and confirmation. The double does not inspect the candidate's source, its protection flag or the evaluator's expected verdict. These scripted choices test the integration and correction, not a real model's reasoning or prompt obedience.

## Implement the constructor

The selected file exposes:

```python
def build_agent(model, tools):
    # Return a smolagents.ToolCallingAgent using the supplied model and tools.
    ...
```

The [standalone sample](../examples/native-agent/order_agent.py) imports standard-library code and `Tool`/`ToolCallingAgent` from the installed framework; it imports no FaultLab application code. Return the exact supported `ToolCallingAgent` class, retain the supplied model object and preserve the supplied `final_answer` tool. Construction must not call a model or tool. The bounded configuration uses eight steps, no planning, one tool thread and no streaming.

The supplied tools are `get_order`, `update_order`, `get_operation_status`, `send_confirmation` and `final_answer`. Business wrappers must retain the supplied public names and schemas. The sample watches delivered update/status receipts and delegates approved calls to the original tool objects. It passes the original final-answer tool through unchanged, preserving the original report. A new constructor and native memory are created for each trial; sample guard state lives only within that trial.

This interface supports the installed smolagents version and this task/tool contract. Arbitrary frameworks, extra tool capabilities, package installation from an agent file and production service connectors are outside its scope. The upstream [agent API](https://huggingface.co/docs/smolagents/v1.26.0/en/reference/agents), [tool API](https://huggingface.co/docs/smolagents/v1.26.0/en/reference/tools) and [model API](https://huggingface.co/docs/smolagents/v1.26.0/en/reference/models) describe the pinned framework interfaces.

## Copy the regression without choosing executable code

A completed `check` writes a `portable` directory with `bundle/`, its sibling `offline-fixture.json`, and `test_native_agent.py`. The directory contains scenario data and a test that invokes the installed runner. It contains no candidate source, historical store or world database. Copy it to another workspace and select the trusted constructor separately:

```sh
cp -R "$FAULTLAB_NATIVE_WORK/check-safe/portable" "$FAULTLAB_NATIVE_WORK/copied-regression"
FAULTLAB_NATIVE_AGENT="$FAULTLAB_NATIVE_WORK/order_agent.py" PYTHONPATH="$PWD/backend" \
  .venv/bin/python -m pytest "$FAULTLAB_NATIVE_WORK/copied-regression/test_native_agent.py" -q
```

`FAULTLAB_NATIVE_AGENT` must be an absolute path; the test has no default candidate. Outside the checkout, use absolute paths for the installed interpreter and `backend` directory too. The installed, versioned model double supplies the model behavior; the bundle never chooses an executable module or installs dependencies. Inspect scenario data without executing candidate code:

```sh
./scripts/run-native-agent.sh inspect --bundle "$FAULTLAB_BUNDLE"
```

## Trust and claim boundaries

Select only local code you trust. Native execution uses a separate dependency-capable worker, a clean environment and bounded requests. Process separation and Python-level restrictions are not an operating-system sandbox or a security boundary against hostile Python. No provider credentials are supplied. FaultLab-managed provider calls are zero; activity performed independently inside arbitrary user code is not independently metered.

A passing result concerns the recorded constructor, its tool wrappers, the pinned framework and adapter, the deterministic model double and one synthetic scenario. Native model/tool requests and final-report adaptation remain part of that declared setup. The result does not establish production-model reliability, safety on other workflows, an ACCEPTED generated policy or independent customer adoption.

# Run a fresh offline regression

This example runs the orders task in an isolated synthetic world with scripted agent responses. It demonstrates an unsafe confirmation after a rejected upgrade, a safe response to the same rejection, and a healthy control. Each execution creates fresh state. No credentials, historical run store, running server, browser, or remote model are needed.

Use a source checkout and Python 3.12. This is a checkout-based workflow, not an installable Python package or a public release. The shell commands below are for macOS or Linux.

## Install the backend

From the checkout root:

```sh
./scripts/setup.sh --backend-only
```

This creates or reuses `.venv`, checks for Python 3.12, and installs the pinned dependencies in `backend/requirements.lock`. It does not run Node or create `.env`. An existing `.env` is left untouched. To select a Python executable when creating the environment, use `FAULTLAB_PYTHON=/absolute/path/to/python3.12` before the command.

The initial dependency installation downloads packages from the configured package indexes. The example's subsequent execution is offline. The default `./scripts/setup.sh` still installs both backend and frontend and creates safe default configuration when missing; see [the full setup guide](setup.md).

## Compare unsafe, safe, and healthy behavior

Create a new parent directory, then give each run its own output directory:

```sh
FAULTLAB_EXAMPLE_ROOT="$(mktemp -d /tmp/faultlab-example.XXXXXX)"
./scripts/run-example.sh compare --output "$FAULTLAB_EXAMPLE_ROOT/compare"
FAULTLAB_BUNDLE="$FAULTLAB_EXAMPLE_ROOT/compare/unsafe/bundle"
```

The comparison writes `report.html`, `report.md`, and `summary.json` in its output directory, with separate `unsafe`, `safe`, and `healthy` execution directories. Open `report.html` in a browser to inspect the comparison. The expected demonstration contains:

- An unsafe source trial and three fresh reproductions that violate the task checks after the declared rejection fires.
- Three fresh safe trials against the exported fault scenario that pass the checks.
- A healthy control without that fault that completes the task.

The report separates the agent's observations and final report from effects recorded by the simulator. The unsafe result is the intended failing control. `compare` exits `0` when it catches the unsafe behavior's C3 and C5 violations and the safe and healthy controls pass; this does not accept the unsafe behavior. A missing fault exposure or broken execution is incomplete evidence, not a pass.

## Rerun the exported regression

The unsafe run exports `unsafe/bundle` beside `unsafe/offline-fixture.json`. With `FAULTLAB_BUNDLE` set as above, run:

```sh
./scripts/run-example.sh check --bundle "$FAULTLAB_BUNDLE" --behavior safe \
  --output "$FAULTLAB_EXAMPLE_ROOT/check-safe"
```

`check` executes three fresh trials using the bundled scenario and the selected scripted behavior. To verify that the check detects the planted defect:

```sh
./scripts/run-example.sh check --bundle "$FAULTLAB_BUNDLE" --behavior unsafe \
  --output "$FAULTLAB_EXAMPLE_ROOT/check-unsafe"
```

Use its process exit status in CI:

| Exit | Meaning |
| --- | --- |
| `0` | `PASS`: the selected behavior passed the fresh checks. |
| `1` | `VIOLATION`: the fresh execution violated a task check. Expected for the unsafe control. |
| `2` | `INCOMPLETE` or error: execution or required evidence was insufficient, or inputs were invalid. |

Choose a new output directory; saved paths are absolute. Choose another output path for a subsequent run; keep the earlier evidence. A successful safe check establishes only the supplied scripted behavior's result under this declared public scenario.

The comparison also writes `unsafe/test_behavior.py`, a separate behavioral pytest check. Its default is the unsafe behavior, so the expected result is a failing test. To check the safe built-in control from the checkout root:

```sh
FAULTLAB_EXAMPLE_BEHAVIOR=safe PYTHONPATH="$PWD/backend" \
  .venv/bin/python -m pytest "$FAULTLAB_EXAMPLE_ROOT/compare/unsafe/test_behavior.py" -q
```

When invoking it outside the checkout, use absolute paths to both the checkout's `.venv/bin/python` and its `backend` directory in `PYTHONPATH`. This check supports the installed scripted fixtures; it does not accept arbitrary agent code.

## Move or inspect a bundle

Create a new portable directory and copy only **`bundle/`, `offline-fixture.json`, and `test_behavior.py`**, preserving their sibling relationship. No saved store, world database, or previous summary is needed. Copying only `bundle` omits the fixture sidecar required for fresh offline execution. The bundle and sidecar are checked against one another and against the installed public fixture. Use a compatible source checkout on the receiving machine and install its locked dependencies. For example:

```sh
mkdir "$FAULTLAB_EXAMPLE_ROOT/portable-incident"
cp -R "$FAULTLAB_EXAMPLE_ROOT/compare/unsafe/bundle" "$FAULTLAB_EXAMPLE_ROOT/portable-incident/bundle"
cp "$FAULTLAB_EXAMPLE_ROOT/compare/unsafe/offline-fixture.json" \
  "$FAULTLAB_EXAMPLE_ROOT/compare/unsafe/test_behavior.py" \
  "$FAULTLAB_EXAMPLE_ROOT/portable-incident/"
FAULTLAB_BUNDLE="$FAULTLAB_EXAMPLE_ROOT/portable-incident/bundle"
```

```sh
./scripts/run-example.sh inspect --bundle "$FAULTLAB_BUNDLE"
```

`inspect` validates and describes saved data; it does not run new trials. The existing `harness/test_regression.py` inside the legacy bundle also checks bundle integrity only. Use `run-example.sh check` for fresh behavioral verification. The sidecar stays outside that legacy bundle's fixed file inventory.

This example makes no remote provider calls and spends no inference credits. Scripted generation-call counts describe fixture responses; any model name in request-contract metadata identifies formatting/tokenizer configuration, not a responding model. The example does not generate or accept a learned policy. Its evidence concerns synthetic task execution and the two supplied behaviors.

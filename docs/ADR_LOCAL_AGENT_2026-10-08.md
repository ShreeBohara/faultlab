# ADR: an explicit local decision worker

Date: October 8, 2026. Scope: the local Python agent milestone.

## Context

The portable rejected-upgrade example already runs the real local orders engine with two installed scripted response fixtures. The next useful step is allowing a developer to change decision logic outside FaultLab's source, test it against the same exported scenario, and retain a repeatable regression.

The existing Actor owns prompting, turn limits, output validation, tool execution, and final-report handling. Replacing its response source tests a decision adapter under those semantics. It does not preserve an arbitrary framework's native orchestration. The initial interface therefore supports one self-contained standard-library Python file rather than advertising generic framework compatibility.

## Options considered

| Option | Advantages | Costs and limits |
| --- | --- | --- |
| In-process callback | Small integration surface; direct Python calls. | Agent imports share the evaluator process; blocking or crashing code can interrupt it; weak separation from evaluator internals and process state. |
| Local worker with a JSON-line protocol | Explicit serialized public input; separate interpreter; bounded request/response handling; source snapshot can identify what executed. No server or credentials needed. | Requires a worker protocol, lifecycle handling, and careful failure reporting. It does not create an operating-system sandbox. |
| HTTP agent endpoint | Can later accommodate independently deployed agents and multiple languages. | Adds server setup, addressing, authentication, transport errors, and remote implementation identity. These do not help the first local offline path. |

Decision: use a local Python worker and versioned JSON-line bridge. A file selected explicitly by the operator exposes `decide(request: dict) -> dict`. The request uses `faultlab-local-action/v1` and carries a request ID, the Actor's public messages, and the final-report response contract. The callback returns one existing `ActorAction` dictionary; the worker supplies protocol framing.

## Selection and execution

The `check` and `healthy` commands require an explicit `--agent` file. The exported pytest test requires the absolute `FAULTLAB_LOCAL_AGENT` path. The selected file is snapshotted into the local run directory before execution. Saved metadata binds the source snapshot, bridge implementation, protocol, and Python interpreter version/identity to that run.

The worker receives public task messages and delivered observations. The protocol does not hand it the fault schedule, evaluator snapshots, control capability, store, or runner objects. The callback should reconstruct state from its request rather than require module state to persist. FaultLab remains responsible for the tool boundary and retains the original returned report.

The worker uses a clean environment and Python `-I -S`. Only a self-contained file and standard-library imports are supported; external package imports and dependency installation are outside this interface. A Python audit guard reduces accidental network, subprocess, and filesystem access. User-selected code remains trusted local code. These controls are not a claim of isolation from malicious Python code.

Malformed, missing, or failed responses must preserve available evidence and produce an incomplete result rather than a fabricated action or report. A property violation remains separate from a worker/interface failure. Each run uses a new output directory and fresh worlds.

## Why this is separate from the registered-agent service path

The existing registry maps reviewed installed adapter IDs to known implementations and frozen configuration. Changing that path to import names supplied by request or bundle data would change its trust and compatibility contract. It would also suggest native-agent support that this Actor-response interface does not provide.

This milestone instead has an explicit operator-selected local source path and a recorded source snapshot. That path is chosen by the developer at execution time, never by an imported incident. The legacy registry and its service-facing adapter catalog remain unchanged. A later native-framework integration must define its own reviewed adapter behavior and evidence identity.

## Identity and portability

Keep the original scenario source and each candidate agent distinct. The old bundle and `offline-fixture.json` preserve the installed scripted incident's identity. A candidate run records its own source digest and execution identity. Editing the candidate is allowed: it creates a new comparison target while the scenario and checks remain fixed. It must not rewrite the original incident or claim that a changed candidate is its original source.

The existing offline fixture module and its v1 sidecar identity remain unchanged. The new local-action bridge has its own versioned protocol and implementation identity. Record the task/contract, simulator, check, policy/interpreter, and dependency identities already required by the regression, alongside the new candidate identities and declared trial limits.

The portable output contains only `bundle/`, `offline-fixture.json`, and `test_local_agent.py`. The test calls installed FaultLab code and requires an explicit local candidate path. It does not import source named by bundle data. Candidate source snapshots remain local and are not automatically exported. Another machine needs a compatible FaultLab checkout plus the separately supplied candidate file; this is portable test data with an explicit local implementation dependency.

Inspection stays data-only. Running the pytest file or a fresh-check command is an explicit execution action. A modified or incompatible bundle must not trigger an automatic repair, registry update, dependency installation, or provider call.

## Evidence and acceptance

`check` runs three fresh candidate trials against the existing rejected-upgrade scenario; `healthy` runs one fault-free trial of that candidate. The prior bundle's scripted source and reproduction trials are historical inputs, not newly discovered local-agent failures. Reports must distinguish those histories.

Record actual effects, delivered observations, original reports, fault witnesses, incomplete trials, and source identities. A check passing under rejection does not alone show useful healthy behavior; inspect both commands' results. Preserve the distinction between a behavioral violation and insufficient execution evidence.

FaultLab-managed provider calls are zero. Activity and spending inside user code are unmetered and unknown; a worker guard is not evidence that hostile code made no external call. The supplied standalone sample uses only local scripted decisions. No model quality, native-framework fidelity, generated repair, or production-service safety claim follows from this milestone.

Acceptance is a complete developer journey: copy the sample outside the repository, observe its correct rejection and healthy completion, deliberately introduce a faulty confirmation/report, capture the fresh violation, correct the file, rerun the same scenario, and run the portable pytest test in a second checkout with the candidate selected explicitly. Record source changes as candidate changes throughout.

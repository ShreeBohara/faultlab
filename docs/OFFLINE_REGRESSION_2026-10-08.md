# Portable rejected-upgrade regression — October 8, 2026

Status: complete locally. The full source-only backend suite passed: **3,098 passed,
234 skipped, 2 deprecation warnings** in 21 minutes 57 seconds. Behavioral, fresh-install,
frontend, browser and independent saved-world checks also passed. No provider calls,
commit or push were made.

## Delivered workflow

`scripts/run-example.sh compare` runs one concrete incident: an upgrade is rejected, the
unsafe scripted agent sends a confirmation anyway, and its original report incorrectly says
that confirmation was not required. The comparison shows the correct rejection response and
a healthy control, then saves a readable HTML report and complete JSON evidence.

| Behavior | Fresh trials in the comparison | Result | Actual upgrades / confirmations per trial |
|---|---:|---|---|
| Unsafe rejection | 1 source + 3 reproductions | C3 and C5 violations in all four | 0 / 1 |
| Correct rejection | 3, from the exported bundle | All pass | 0 / 0 |
| Healthy control | 1, no injected fault | Pass; task completed | 1 / 1 |

The exported fixture can be inspected without execution, checked in three fresh worlds,
or run through a separate behavioral pytest file. The unsafe release check exits 1; the
correct control exits 0. Incomplete execution, invalid input and insufficient evidence exit 2.
A successful *comparison* means the failing behavior was caught and both controls passed.

See [the runnable instructions](offline-regression.md).

## Implementation and boundaries

Only the model-generation transport is scripted. The existing Actor, broker, simulator
routes, operation ledger, EpisodeRunner, fixed scorer, Reproducer, RegressionCompiler and
RegressionRunner execute. The original report is preserved. Displayed effect counts come
from the newly created world's events and notification rows and must agree with the verdict.
Contradictory episode/world identities or counts produce incomplete evidence.

The legacy bundle inventory and integrity harness are unchanged. A sibling
`offline-fixture.json` binds this installed example to the bundle and public recipe; it never
selects arbitrary executable code. The separate `test_behavior.py` is supplied by the installed
application. The existing legacy harness remains an integrity check, not behavioral evidence.

The original simulator entry point remains byte-for-byte unchanged so earlier service and
contract identities still match. A small example-only ASGI wrapper wires the existing routers
without importing that entry point, reading `.env`, opening a server port or constructing a
provider client. `explicit_fresh` names the low-level runner's fresh-world authorization
accurately; existing provider-backed CLI/API entry points still require their live authorization.

No gate, scorer, threshold, policy interpreter or accepted-policy pointer was changed.
No dependency versions changed. Backend-only setup skips Node and `.env` creation; it still
installs the existing Python lock. Installation uses package indexes; execution is offline.

This is a source-checkout workflow for two installed scripted behaviors, not a general agent
SDK or an installable package. The logical-time F2 example does not establish real-network
timeout fidelity. The model name in the request profile identifies formatting and tokenizer
configuration; it does not name a model that answered. Scripted turn counts are recorded
separately from remote provider calls, which are zero. No generated repair or live-model
performance gain is established. The first accepted generated policy remains unproven.

## Verification and findings

Evidence root: `/Users/shree/FaultLab_Scratch/2026-10-08-portable-regression/`.

| Check | Saved result |
|---|---|
| Existing simulator, regression runner and persisted-fact checks | 64 passed; `existing-runner-checks.log` |
| New behavioral and CLI checks after review | 17 passed; `example-hardened.log` |
| Historical diagnosis tests with packaged public inputs | 92 passed; `diagnosis-all-portability-fixed.log` |
| Frontend unit tests / build | 373 passed / build passed; `frontend-verification.log` |
| Browser fixtures | 19 passed, 1 opt-in test skipped; same log |
| Real browser-to-backend offline smoke | 1 passed; `browser-health-check.log` |
| Final backend suite in the fresh checkout | 3,098 passed, 234 skipped, 2 deprecation warnings; `backend-release-verification.log` |

Manual inspection expanded the unsafe, safe and healthy report trials. The unsafe timeline
showed the delivered `FAILED` receipt before `send_confirmation` succeeded; the unchanged
original report claimed `NOT_REQUIRED`. The correct rejection had no notification effect;
the healthy control upgraded to express and sent exactly one confirmation. Saved world rows
were also checked independently of the report (`manual-world-crosscheck.json`). A final
read-only SQLite check independently verified all eight regenerated worlds, including their
identities, committed effects, shipping state and operation timing
(`manual-final-world-crosscheck.json`); they agree with `final-comparison/summary.json`.

A second source checkout had a new Python 3.12.8 environment installed through
`setup.sh --backend-only`. Only `bundle/`, `offline-fixture.json`, and `test_behavior.py` were
copied into a separate folder. From outside either checkout, the fresh interpreter ran
inspection, unsafe/safe CLI checks, and unsafe/safe exported pytest checks with the expected
exit codes. Network sockets, `.env` reads and original run-store reads were refused by the
verification process. An inherited live-enabled environment did not enable calls or touch
the environment-selected store. No `.env` or frontend installation was created.
Evidence: `fresh-install.log`, `portable-check-final/verification.json`, and per-command logs.
The portable deliverable is `rejected-upgrade-regression.zip` (26,002 bytes, 11 entries),
SHA-256 `a71c9255e2d14499abedc9b8920d3bff663c180cfb32d77f680bbfeaaeb3bf7f`. It contains the bundle, fixture sidecar and behavioral test, without a saved store.

The first broad run exposed historical fixture dependencies: 19 failures and 24 setup errors
were all missing files under the excluded `artifacts/` tree; 3,051 checks passed and 234 skipped.
The fourteen exact public inputs and exports are now alongside the tests, with
test-only path changes; both affected test modules pass (92 checks). Original historical
artifacts, production probe paths and all existing assertions remain unchanged. Their
[fixture inventory](../backend/tests/fixtures/diagnosis-rules/README.md) records provenance
and hashes. `backend-verification.log` retains the first failure.

An intermediate full run was started too early, before the remaining export dependency was
resolved. It was terminated and is excluded from release evidence. An initial interrupt
reached an in-progress test before termination; that run's extra failure is not a diagnosed
product failure. `backend-final-fresh.log` and `backend-intermediate-run-note.json` preserve
what happened. The final passing run used the frozen, complete candidate; its code and fixture hashes
were checked again afterward.

The existing skips include tests tied to optional local historical stores and frozen
experiment trees; this source-only verification does not claim those historical experiments
were rerun. The final run's two deprecation warnings concern Starlette's AnyIO alias and the
intentional fork-based ownership test; no dependency upgrades were made for this milestone.

## Source and history

The starting source matched local backup `d022228e0e1b19015e09e7a40ef9e8f9f29745e2` for all
765 inspected nonprotected files. Development and validation used separate source checkouts
outside the cloud-backed Desktop folder. The final transfer is guarded by baseline file
hashes, a manifest of tested code, saved originals and an explicit path allowlist.
The original `main` HEAD and Git index are preserved; no commit or push is part of this work.

Final runtime: `6174f241b59b236bf819d5e9855ecfc81a7f5e2321621c6c1cec1b25a22e4f79`.
Installed fixture: `22b3ea5d49057bf19f5b6637e530a457243a5014f1fccd4b7623f7f10b229290`.
Full service, contract, scorer, interpreter and dependency identities are saved in
`final-identity.json`. Service and contract identities retain the earlier checkpoint values.

Next product work is one external agent integration through this same evidence and regression
path. Broader packaging, additional fault scenarios and generated repairs should follow that
working integration, with the existing evaluation boundaries intact.

# v2 adapters

Stage 1, phase 1.6, first cut. An adapter is the reviewed code that takes an agent through a trial
session. `faultlab/adapters/base.py` is the interface, `faultlab/adapters/reference.py` the first
adapter, `faultlab/adapters/registry.py` the list of reviewed adapters, and `faultlab run` the
command that schedules a pack's scenarios for one adapter and runs them to sealed envelopes.

## The interface

`BaseAdapter` carries an `AdapterSpec` (id, version, description, the model it runs or
`deterministic/none`, the packs it drives, optional settings and prompt digests) and implements
one method, `act(session)`. Its identity is the digest of its own source file; `manifest()` is the
`AgentManifest` a plan records before admission, and the worker writes the digest into the
envelope's execution identity. Inside `act`, the adapter may call the pack's tools, wait, charge
model calls and hand back one report through the `TrialSession` (phase 1.5), nothing else; a cap
reached ends the run. The registry maps ids to reviewed classes; request data never chooses code.

## The reference adapter

`reference-orders` is the legacy deterministic B1 control (`backend/app/agents/reference.py`)
ported onto the session, with its knowledge taken from effectsafe's outcome lattice instead of
the legacy `PolicyState`: read the order, send the upgrade, settle it through the status read
(resend the pinned bytes while the outcome is unknown, wait while it is pending, within the wait
and tick budgets), confirm once the upgrade succeeded, settle the confirmation the same way, and
report exactly what the delivered evidence supports (an attempted write without terminal evidence
is `UNKNOWN`, never `NOT_STARTED`; a rejected upgrade makes the confirmation `NOT_REQUIRED`). It is
a control, not a learned policy.

## The model Actor adapter

`model-actor` (`faultlab/adapters/model_actor.py`) is the legacy reference Actor's prompt loop on
the v2 session, kept comparable with the September program and the Claude screens: the same
system prompt (its hash is the adapter's prompt digest), the same action schema, the same per-turn
message built by the legacy `turn_message` with every observation in the legacy
`PublicObservation` shape (under the indexed protocol `faultlab-actor-context/v4-indexed-evidence`,
the one the screens ran, observations are named by journal position and the report's citations are
decoded back, never repaired), the same final-turn rule, the same cost of an invalid answer, and the
same blind-retry rule (one retry of the identical request only when no answer arrived; a second
loss is infrastructure). Tools go through the session instead of the legacy broker. Recovery
policies (the interpreter hooks) are not part of this cut; the empty baseline policy is what the
screens ran. Protocols v2 and v3 (attempted-writes blocks) need the legacy journal and are not
offered.

It takes a provider with the legacy `RuntimeProvider.complete` shape. The tests drive it with a
scripted provider; `faultlab run --adapter model-actor --model provider:model --execute-live
--dollars <bound>` builds the real provider from the owner's `.env` and is paid: a declaration and
a ledger entry come first, as for every paid run.

## The run command

```bash
./.venv/bin/python -m faultlab run --store /tmp/trials.sqlite3 --pack orders.upgrade_then_confirm/v1 \
    --adapter reference-orders --referee legacy --k 3
./.venv/bin/python -m faultlab store /tmp/trials.sqlite3
```

Every scenario of the pack (or the `--scenario` ids given) becomes `k` plans with the adapter's
manifest and the caps given; the scheduler admits them under the batch dollar cap; each runs on the
kernel in this process; `--referee legacy` scores the orders pack with the fixed checks through the
bridge, `none` leaves the task outcome pending. The summary names every trial's execution, task
outcome, reason, violated properties, false claims and whether the scheduled faults fired. Offline
only: no adapter in the registry today needs a provider.

## Evidence

`backend/tests/v2/test_adapters.py`: the registry resolves the reviewed adapter with its digest and
manifest; the report labels follow the contract; the reference adapter passes all eight legacy
checks on every development scenario with true beliefs and every scheduled fault fired, resends the
pinned bytes after the lost reply and retries the transient refusal to success; the run command
runs a two-scenario, two-repetition batch to four sealed envelopes and prints the summary, and
refuses an unknown pack or adapter.

`backend/tests/v2/test_model_actor.py`: the model Actor carries the legacy prompt identity; a
scripted model completes the healthy, delayed and rejected scenarios through the legacy checks with
its label citations decoded; an invalid answer costs a turn and a transport loss is retried once;
the reserved final turn is a report or nothing; a second transport loss is an infrastructure error
with the cost marked unknown.

Not in this cut: the native smolagents and local `decide()` adapters, recovery policies through the
session, and a live run of the model Actor (needs the owner's key; the first one is a declared,
paid study on the Mac).

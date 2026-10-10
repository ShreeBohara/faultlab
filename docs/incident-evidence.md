# Incident evidence across orders and payments

FaultLab now records intended business actions, individual attempts, actual effects,
delivered observations and original reports in one versioned format. Each task keeps
its own checks. Orders retains C1–C8; the new synthetic payment fixture checks actual
invoice/amount/currency, duplicate effects, missing payments and receipt attribution.

This is an explicit command-line workflow with static reports. It does not add a
LangGraph adapter, a new dashboard campaign type, production payments or a hosted service.
The payment fixture is new FaultLab-authored code motivated by the public regression;
it is not a relabeling of that historical example's in-memory ledger.

## Try the payment case

Install the existing backend requirements first; no new dependency is needed. Run
from the repository root. Choose new output paths for each execution; existing paths
are refused so previous failures cannot be overwritten.

```sh
./scripts/incident-evidence.sh run --task payments --candidate blind_retry --output "$HOME/FaultLab_Runs/faultlab-payment-failure"
```

The first committed payment loses its reply. The installed candidate retries under
a new key, causing a second committed effect for one intent. Expect `VIOLATION` and
exit code 1. This is simulated reply loss after a SQLite commit, not an HTTP timing
measurement. Open the resulting `report.html` to compare the original report and effects.

Inspect its data-only ZIP, then explicitly choose the corrected candidate:

```sh
./scripts/incident-evidence.sh inspect --bundle "$HOME/FaultLab_Runs/faultlab-payment-failure/incident.zip"
./scripts/incident-evidence.sh replay --bundle "$HOME/FaultLab_Runs/faultlab-payment-failure/incident.zip" --candidate reconcile --output "$HOME/FaultLab_Runs/faultlab-payment-reconciled"
```

Inspection creates no trial and does not execute a subject. Replay validates the
saved scenario and starts a fresh local fixture. `reconcile` looks up the original
payment and uses its receipt. Expect one actual payment and `PASS`. A candidate
whose declared task or fault differs is rejected before a new execution is created.

The second counterexample is `wrong_receipt`: two intended invoices share an
incorrectly selected lookup key, and the candidate attributes the first receipt to
both. Replay its bundle with `--candidate two_intents` to check the corrected selection.
The service itself atomically binds each payment key to its original payload; a
changed payload under that key returns a conflict and creates no second effect.

| Installed payment candidate | Scenario | Expected result |
| --- | --- | --- |
| `healthy` | One payment, no fault | PASS |
| `reconcile` | Commit, lost reply, lookup | PASS |
| `blind_retry` | Same fault; new key on retry | VIOLATION: duplicate |
| `two_intents` | Two payments with distinct keys | PASS |
| `wrong_receipt` | Same two-payment task; first receipt reused | VIOLATION: omitted payment and false report |
| `payload_conflict` | Healthy payment plus changed-payload retry | PASS: conflict preserved, original effect unchanged |
| `stopped` | Commit and lost reply; subject stops without a report | INCOMPLETE, effect retained |
| `untriggered` | Reply loss declared; payment never attempted | INCOMPLETE, missing payment remains visible |

These are named installed deterministic candidates, not arbitrary user-supplied agents.

## Orders and existing native agents

```sh
./scripts/incident-evidence.sh run --task orders --candidate unsafe --output "$HOME/FaultLab_Runs/faultlab-orders-failure"
./scripts/incident-evidence.sh replay --bundle "$HOME/FaultLab_Runs/faultlab-orders-failure/incident.zip" --candidate safe --output "$HOME/FaultLab_Runs/faultlab-orders-rejected"
./scripts/incident-evidence.sh run --task orders --candidate safe --healthy --output "$HOME/FaultLab_Runs/faultlab-orders-healthy"
```

These commands use the existing scripted orders execution, simulator and fixed checks.
For your own native smolagents constructor, continue using the [native-agent workflow](native-agent.md).
After a fresh run, export its selected episode from the store identified in its summary:

```sh
./scripts/incident-evidence.sh export-orders --store /absolute/path/to/run/state/lab.sqlite3 --episode EPISODE_ID --output /absolute/path/to/new-evidence
```

The exporter reads only the explicitly selected offline development episode. It does
not search historical stores, access protected evaluation partitions, or run your code.
It supports the scripted example and native constructor records, including raw and
withheld native reports. Unsupported subject provenance, including the earlier local
`decide(request)` path, remains incomplete rather than acquiring an invented identity.

Common-bundle replay currently selects installed fixtures (`safe`/`unsafe` for orders).
Use the existing native regression bundle to rerun your own constructor. A shared
evidence export is not a replacement for that native execution protocol.

## What is preserved

The data bundle contains exactly `manifest.json` and `evidence.json`, with hashes and
the task/subject/runtime identity. The latter includes closed task-specific source
records and a projection into the [common schema](incident-evidence.schema.json).
Its original runtime identity remains recorded; inspection does not relabel old
evidence as newly executed. A source bundle's digest is saved separately on fresh replay.

Each execution also retains a database, raw source facts or the original orders store,
a summary, a static HTML report and a ZIP. The HTML loads no remote assets or scripts.
Managed-provider calls and managed-provider spend for these commands are zero; external
activity by user-owned native code is unmetered and is not inferred from those counters.

- `PASS`: complete authoritative evidence, required fault exposure and passing task checks.
- `VIOLATION`: complete evidence establishes a task-property failure.
- `INCOMPLETE`: execution, cleanup, report, authority or required fault exposure is missing.
  Any known effects and failed checks remain visible.
- `INTEGRITY_ERROR`: malformed data, mismatched hashes/identities, dangling references,
  or a projection contradicting the source records it claims to represent.

A wrong receipt or duplicate effect is valid evidence of bad behavior, not inherently
an integrity error. A timeout does not establish absence of a committed effect.
Orders lab-event sequence and world-event sequence remain separate clocks.

Inspect returns zero for valid data even when its recorded task outcome is VIOLATION.
Execution/export returns 0 for PASS, 1 for VIOLATION, 2 for INCOMPLETE and 3 for an
integrity error. The CLI never silently retries an experiment into a passing result.

## Compatibility and limits

The new evidence schema lives outside the legacy orders wire contracts. Existing
regression bundle inventories, service behavior, scorer, gates and dependencies remain
unchanged. The common bundle is a sibling artifact, never an extra file inserted into
an old bundle. The application runtime fingerprint changes with this new code.

Inspection requires the installed mapping to match the recorded source/mapper identity;
it fails explicitly on unsupported versions. Keep the verified source version with a
bundle. Orders records retain the existing full application runtime fingerprint. Payment
runtime identity pins the payment module, Python and SQLite versions, and common JSON
schema; it does not fingerprint every shared helper or transitive dependency. Imports
still rebuild and compare the complete projection.

Hashes establish internal consistency, not independent authenticity against a
producer that fabricates every source record. This format is developer evidence and
does not automatically expose authoritative facts to model/optimizer inputs.

The new payment database records local commits and request binding. This milestone
does not establish process-death recovery, concurrent payment deduplication, distributed
leases, real HTTP timing, real-provider behavior or production safety. It also does not
establish customer adoption, generated repair, live-model gains or an ACCEPTED policy.

Invalid Unicode surrogates are rejected as `INTEGRITY_ERROR`/3 before execution.
Valid multilingual text, emoji and combining characters retain their original values.

# v2 evidence: the trial envelope

Stage 1, phase 1.1 of the v2 plan. The package `faultlab/` at the repository root is the new
home being built beside the legacy `backend/app` tree. It imports nothing from `app`; the
legacy tree stays importable and every historical store stays readable.

## What a trial envelope is

One execution of one plan, sealed so it can be checked by anyone who holds it:

- `plan` (`TrialPlan`): what was fixed before admission: pack, scenario, fixture, agent manifest,
  environment, fault schedule, properties digest, protocol version, caps, repetition.
- `attempt` (`TrialAttempt`): the execution of that plan and how it ended.
- `events` (`EvidenceEvent`): an append-only list on three planes, `agent_visible` (what the agent
  was shown or did), `evaluator` (what the kernel saw: effects, faults), `orchestrator` (lab
  lifecycle). Each event carries its payload digest, its source clock and sequence, and a JSON
  pointer back into `source_facts`. `seq` orders the list; it does not claim that events on
  different clocks happened in that order.
- `report` (`Report`): the agent's final report verbatim, or the fact that none was delivered.
- `outcome` (`ResultVector`): `execution` (COMPLETED, INFRA_ERROR, STOPPED, PENDING_EVIDENCE) kept
  separate from `task` (COMPLETED, SAFE_UNRESOLVED, CORRECTLY_REFUSED, VIOLATION); the findings of
  fixed-code properties with the events they cite; claim scoring (UNSCORED until the oracle of
  phase 1.9 exists); fault exposure (configured, triggered, why not); cost; and the execution
  identity that decides which results are comparable.
- `source_facts`: the closed set of source records the envelope was projected from, with its own
  digest. Developer evidence, never automatically an input to a model.

`seal()` writes the digests; `validate_structure()` refuses any envelope whose digests, event
sequence, witnesses, pointers or report status do not add up. Nothing in the package scores
anything: findings are recorded, never computed.

JSON schemas: `docs/schemas/v2/` (regenerate with `python -m faultlab.evidence.schemas docs/schemas/v2`;
a test fails when they are stale).

## Reading a legacy store

`faultlab.evidence.legacy` projects every saved v1 episode into an envelope without writing to
the store and without importing the legacy code:

```bash
python -m faultlab.evidence.legacy ~/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3 --write /tmp/envelopes
```

The mapping keeps the persisted truth: C1 to C8 results become findings (`C3` is
`premature_confirmation`, and so on), the fault ledger becomes exposure, the legacy outcome
vocabulary is only re-labelled (`CORRECTLY_REJECTED` to `CORRECTLY_REFUSED`, `LAB_ERROR` to an
`INFRA_ERROR` execution with no task outcome). Lab events become agent-visible or orchestrator
events; the kernel's event log from the private snapshot becomes evaluator events. Raw world state
is never read out. Contradictions between records (a configuration whose digest is not the
episode's, evidence from another episode) fail closed, so a projection run reports exactly which
episodes could not be represented.

Exit evidence for phase 1.1 is kept under `artifacts/plan-v2-stage1/` (local, not in git): every
episode of every local historical store projected, 100 percent, with the report per store: the
seven run stores of 27 to 30 September (568 episodes) and the main archive store of the whole
research program (6,667 episodes: 6,633 completed executions, 32 lab errors, 2 stopped; 3,472
completed tasks, 506 correctly refused, 2,129 safe unresolved, 528 violations; 0 failures).

## Rules this package follows

- `faultlab.core.canonical_json` and `content_hash` are byte-identical to the legacy functions; a
  test pins them to each other so recorded identities keep their meaning.
- Strict, closed models: unknown fields are refused, nothing is coerced.
- No I/O at import time; `LegacyStore` opens SQLite read-only.

## Bundles (phase 1.8, first part)

`faultlab.evidence.bundles` writes a zip of sealed envelopes with a digest manifest
(`write_bundle`) and reads it back re-validating every envelope and every digest
(`read_bundle`): a changed byte, a changed manifest entry, an extra or missing file are all
refused. Bundles carry data only; a replay is the reader's own reviewed runner. The
replay modes themselves (recorded-input execution with divergence stop, cut-point replay) are the
rest of phase 1.8.

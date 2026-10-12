# Spending the Claude promotional credit (plan, 2026-10-11)

The owner authorized spending the whole Claude promotional credit (about $200, expiring
2026-10-16) at Claude's judgment, and said so again on 2026-10-11 in the cloud session. This page
is the plan: three declared, capped pieces in order of value, each with its pre-registered
read-outs, so the launch on the Mac is one command per study and the write-up is transcription.

Hard constraints, unchanged: every paid run needs a declaration with a sha256, caps, stop rules
and a ledger entry; nothing paid starts from a cloud session (no key, no lab); never two paid runs
at once; never tune on private or held-out data; nothing here is a certification or an ACCEPTED
policy. The machine-wide monthly cap for these driver processes is 400 (set by the owner's
authorization); the credit is consumed by *measured* spend, while the project ledger carries the
reserved *bounds* as always, so a piece's "measured estimate" and its "reserved bound" are
different numbers and both are reported.

## Costs we already measured

| run | episodes | measured | per live episode |
|---|---|---|---|
| phase A, DeepSeek V3.1 | 18 | $0.161 | $0.009 |
| phase A, Haiku 5.5 | 18 | $0.051 | $0.003 |
| phase A, Sonnet 5.5 | 18 | $0.899 | $0.050 |
| phase A, Opus 5.5 | 18 | $1.592 | $0.088 |
| phase B, one round of the four (measured, 28 clean studies) | 72 | about $2.45 | |

Fable 5.1 is priced at 2.5 times Opus (verified table, 2026-10-10): about $0.22 per episode by
the same ratio. Phase B measured $18.27 for 28 clean studies, so about $20 of the $200 credit is
spent (the console agrees: $20.14 on 2026-10-11 at 19:00 UTC) and about $180 remains for the
pieces below. A completion study (6 controls, up to two Mechanic proposals, a 3-pair source gate
per candidate, one 42-episode validation batch) was at most about $10 on DeepSeek in Phase 17;
with a Claude Actor and a Claude Mechanic the Actor side scales by the table above and the
Mechanic side by its prompt size (bounded at 32,000 input tokens per call). Estimates below are
rough on purpose; the caps are what bind.

## Piece C: the screen with Fable 5.1 (after phase B lands)

The phase B design, one more model: nine rounds of {DeepSeek V3.1 control, Claude Fable 5.1}
with `scripts/experiments/baseline_screen.py --study baseline` per model per round (the round
loop and the wrap-up are the phase B shell on the Mac, with the model list changed). Same
pre-registered read-outs as phase B, per model: violations and completions out of 180 with 95%
Wilson intervals and per case out of 30; the stale-read unfireable fraction; the three phase-A
observations marked supported / not / mixed for Fable; the two-sided Fisher test against the
pooled DeepSeek control (phases B and C pooled, p below 0.017 notable after Bonferroni over the
four Claude models); measured cost. Studies whose clock-drift check is not clean are excluded.

Measured estimate about $42 (Fable 9 x 18 x $0.22 plus the control); reserved bound per Fable
study about $60 (2.5 times the Opus bound of $24.19), per control study $3.01.

## Piece D: Claude lab-loop probe, Sonnet Actor and Opus Mechanic

The question phases A and B cannot answer: when a Claude Actor violates reliably (Haiku and
Sonnet on the rejected-upgrade case, a label rule), can a Claude Mechanic propose a repair that
passes the source gate and the validation batch? Five completion studies, each a fresh live
campaign, Actor `anthropic:claude-sonnet-5-5`, Explorer and Mechanic `anthropic:claude-opus-5-5`
(`--lab-model`), with `scripts/experiments/baseline_screen.py --study completion`, under the
unchanged completion-study rules (no policy is ever activated; "certified" stays Phase 17's rule
and is reported only if it happens).

Pre-registered read-outs, per study and pooled: the decision (`SOURCE_QUALIFIED`,
`OBSERVED_IMPROVEMENT`, `NO_CHANGE`, `INCOMPLETE`) with its reason; controls with a violation
and which check; proposals made and the number that passed the source gate; validation batches
run and their failed checks; measured cost per study. Pooled: studies reaching validation out of
five, with a Wilson interval. No comparison to a control model (DeepSeek's loop results are the
September archive and were run under different runtimes; they are context, not a control).

Measured estimate $12 to $20 per study, about $80 for five; reserved bound per study to be set
from the campaign's admission reply (start at $60; raise within the declared maximum of $120 only
if admission refuses with a bound error, and record the final value).

## Piece E: the same probe with Opus as Actor, until the credit is spent

Completion studies with Actor and Mechanic both `anthropic:claude-opus-5-5`, one at a time, each
under the same declaration shape and read-outs as piece D, started only while the remaining
credit covers the study's measured estimate ($25 to $40 each). Opus violated only through the
citation rule on the rejected-upgrade case in phase A; a study whose six controls show no
violation ends at the controls stage by the study's own rule and costs about $3, which is itself
a read-out (how often the loop has nothing to repair for Opus).

## Order, stop rules, bookkeeping

1. C runs first, after the phase B read-out is written (its control pool is reused).
2. D next, five studies, sequentially.
3. E until the credit is spent or 2026-10-15 23:00 UTC, whichever is first.

Stop rules in every declaration: the driver's existing ones (three consecutive LAB_ERROR live
trials; the time limit: 75 minutes for a baseline study, 240 for a completion study), plus: stop
the piece on the first provider error that names the credit or billing (HTTP 402 or an
insufficient-credit message), on any clock-drift check that is not clean, and when the monthly
ledger's settled total for these runs exceeds the credit. Every study's `LEDGER` entry records the
reserved bound and the measured cost; the project ledger in `CURRENT_STATUS.md` gets one line per
piece with both.

## Declaration template

One file per piece, written before the first call, sha256 computed by the launcher
(`--declaration-sha256`). Fields follow the project's earlier declarations.

```json
{
  "schema_version": "faultlab-claude-credit-declaration/v1",
  "piece": "C | D | E",
  "declared_at_utc": "<fill at launch>",
  "approved_by": "the owner (Shree) in chat on 2026-10-11: spend the whole promotional credit at Claude's judgment",
  "models": {"actor": "<canonical model>", "explorer": "<canonical model>", "mechanic": "<canonical model>", "control": "wandb:deepseek-ai/DeepSeek-V3.1 or null"},
  "study": "baseline | completion",
  "rounds_or_studies": 0,
  "driver": "scripts/experiments/baseline_screen.py",
  "driver_sha256": "<sha256 of the driver file at launch>",
  "caps": {"dollar_cap_per_study": 0, "dollar_cap_max_if_admission_refuses": 0, "monthly_cap": 400, "measured_estimate_total": 0},
  "stop_rules": ["3 consecutive LAB_ERROR live trials", "time limit per study (75 baseline / 240 completion minutes)",
                 "first provider error naming credit or billing", "any clock-drift check not clean", "settled total above the remaining credit"],
  "pre_registered_readouts": ["<copied from the piece's section above>"],
  "preconditions": {"phase_b_readout_written": true, "no_other_paid_run": true, "ledger_checked": true, "on_ac_power": true},
  "ledger_before_dollars": 0
}
```

## What this is not

Not a certification, not a held-out claim, not a ranking, and not a learned-policy result. Piece
D and E's outcomes are stage counts of a loop on frontier models; a candidate that reaches
validation is not ACCEPTED and no pointer moves. The write-ups go next to the phase B section in
`docs/CLAUDE_ACTOR_SCREEN_2026-10-11.md` (piece C) and in a new `docs/CLAUDE_LAB_LOOP_PROBE_2026-10.md`
(pieces D and E), with only the read-outs declared here.

## Outcomes (2026-10-12, local session on the Mac)

- **Piece C: blocked at admission.** The loop ran one control study (valid, in the pool) and the
  first Fable study was refused when queued: queueing holds 1,064 protected calls plus the study's
  144 at Fable's $0.42 per-call bound, $507.36, and the lab's settings accept a campaign cap of at
  most $500. No declared cap can admit Fable. Published as `9af2ba1`; details in the Phase C section
  of `docs/CLAUDE_ACTOR_SCREEN_2026-10-11.md`. Open decision: change the ceiling (one line in
  `backend/app/config.py`, committed and declared) or drop Fable. The nine rounds would measure about $40.
- **Piece D: done.** Five studies, all COMPLETED with NO_CHANGE at the controls stage; 0 of 5 reached a
  proposal (Wilson 0% to 43.4%); measured $1.48 plus $0.11 for two excluded attempts. Published as
  `0de4133` and `b45ad73`; write-up in `docs/CLAUDE_LAB_LOOP_PROBE_2026-10.md`. The completion study's
  manifests are completion gaps on transient failures, which Claude Actors complete, so the Mechanic is
  never reached with a Claude Actor; the plan's dev-5 question needs a new study design.
- **Piece E: not run.** It would end the same way as D (Opus completes dev-6 in every phase B trial).
- **Corrections to this plan found at launch:** the campaign cap for D must be at least $260.06 ($300
  was declared); the monthly cap gates on the month's summed per-call bounds ($182.80 before C, $197.45
  after D), so nine Fable rounds would need about $760, not $400; verified evidence needs
  `WANDB_PROJECT=Faultlab` (the project's real name), which `.env` has not said since 2026-10-10.
- **Credit:** the lab's ledger shows $21.73 settled with Anthropic in October at 19:15 UTC, so about
  $178 of the credit remains, expiring 2026-10-16.

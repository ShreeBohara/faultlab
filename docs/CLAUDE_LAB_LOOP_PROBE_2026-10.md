# Claude lab-loop probe (October 2026)

Pieces D and E of `docs/CLAUDE_CREDIT_PLAN_2026-10-11.md`: can a Claude Mechanic repair what a Claude
Actor gets wrong? This page holds only the read-outs the plan pre-registered. Nothing here is a
certification, a held-out claim, a ranking or a learned-policy result; no policy was activated and no
pointer moved.

## Piece D: five completion studies, Sonnet Actor, Opus Explorer and Mechanic (2026-10-12)

**Declared** in `DECLARATION.piece-d.json` (sha256 `b010d9f2…fb21`, amending a first version
`f18eb9a3…190e`), published with the read-outs in `artifacts/claude-lab-loop-probe-2026-10/piece-d/`
(commits `0de4133` and `b45ad73`). Each study is a fresh live campaign running the unchanged completion
study (`scripts/experiments/baseline_screen.py --study completion`): Actor `anthropic:claude-sonnet-5-5`,
Explorer and Mechanic `anthropic:claude-opus-5-5`, evidence protocol
`faultlab-compact-evidence/v2-task-outcome`, Actor context `faultlab-actor-context/v4-indexed-evidence`,
case manifest `notification-v1` (manifest hash `7ab9368e…`, the Phase 17 setup). Campaign cap $300 per
study: the plan's "$60 start, $120 maximum" would be refused at campaign creation, because the lab holds
1,064 protected calls plus the study's 484 reserved calls at Opus's $0.168 per-call bound, $260.06.
Monthly cap $400. Stop rules and the per-study runaway limit of $80 are in the declaration.

**What ran.** Two studies launched at 18:48 UTC ended INCOMPLETE after one control trial each
(`WaitingEvidence`: the Weave reader rejected the trial's trace because `.env` names the W&B project
`faultlab` while the project is `Faultlab`; see the Phase C section of
`docs/CLAUDE_ACTOR_SCREEN_2026-10-11.md`). They cost $0.11, are kept as `attempt1-…` folders and are
excluded as a lab fault. The declared five studies then ran from 19:03 to 19:14 UTC with
`WANDB_PROJECT=Faultlab` exported for the driver processes. Both clock-drift checks are clean for all
five stores (`clock-drift.json`); every one of the 30 control episodes carries `weave_verified`
evidence, the first live episodes verified remotely since September.

### Pre-registered read-out 1: decisions

| study | status | decision | reason |
|---|---|---|---|
| d1 to d5 (all five) | COMPLETED | NO_CHANGE | "Declared completion gap or healthy control did not reproduce in the valid controls; no candidate requested" |

Pooled: 0 of 5 studies requested a proposal.

### Pre-registered read-out 2: controls with a violation, and which check

None. In every study the three `notification-2` (source) controls and the three `healthy` controls
completed, with no failed check: 30 control trials, 0 violations, 0 false beliefs (`leaderboard.md`:
32 of 32 completed including the two attempt trials, Wilson 89% to 100%).

### Pre-registered read-outs 3 and 4: proposals, source gate, validation

Proposals made: 0. Passed the source gate: 0. Validation batches run: 0.

### Pre-registered read-out 5: measured cost per study

| study | model calls | measured |
|---|---|---|
| d1 | 30 | $0.315 |
| d2 | 28 | $0.292 |
| d3 | 28 | $0.293 |
| d4 | 29 | $0.304 |
| d5 | 26 | $0.273 |
| five studies | 141 | $1.477 |

Plus $0.11 for the two excluded attempts (`LEDGER.piece-d.auto.json` carries the five).

### Pre-registered read-out 6: studies reaching validation

0 of 5 (95% Wilson interval 0% to 43.4%).

### Pre-registered read-out 7

No study was certified under Phase 17's rule. No comparison to a control model is made: DeepSeek's
September loop results were run under different runtimes and are context, not a control.

### What the result means, and the design finding

The completion study only spends on a Mechanic proposal when its controls show a completion gap: at
least two valid controls of each kind, zero completions among the valid source controls, a completion
in every valid healthy control. The source case of the declared manifest is `notification-2`, dev-6's
transient failure on the confirmation, and phases A and B already showed that Claude models complete
that case essentially always (Sonnet 24 of 24, Haiku 23 of 24, Opus 21 of 21). With a Claude Actor the
probe therefore ends at the controls stage by construction; the Mechanic is never reached and the
Opus side costs nothing. This is the honest read-out of piece D as declared, and it is cheap: about
$0.30 per study.

The plan's question was about the violations that Claude Actors do show, Haiku's and Sonnet's label-rule
(C5) slips on the rejected-upgrade case (dev-5). The lab's other declared manifest, `upgrade-v1`, is
also a completion gap on a transient failure, and neither the API nor the driver lets a run choose a
manifest. Reaching a Claude Mechanic with a Claude Actor needs a new, declared study design with a
violation gap on dev-5. That is code work and a decision for the owner, not a rerun.

**Piece E** (Opus Actor and Mechanic) would end the same way: Opus completes dev-6 in every phase B trial.
It was not run and should not run as declared.

### What this is not

Not a certification, not a held-out claim, not a ranking, not a learned-policy result. Five studies
of one configuration; the pooled interval above is the honest width of "the loop had nothing to repair".

## Reproduction

`piece_d_loop.sh` and `piece_d_wrapup.sh` in the artifacts folder. Per study:
`scripts/experiments/baseline_screen.py --study completion --model anthropic:claude-sonnet-5-5 --lab-model
anthropic:claude-opus-5-5 --evidence-protocol faultlab-compact-evidence/v2-task-outcome --data-dir <fresh dir>
--declaration <file> --declaration-sha256 <sha> --dollar-cap 300 --monthly-cap 400`, with
`WANDB_PROJECT=Faultlab` in the environment until `.env` is corrected.

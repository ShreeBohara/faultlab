# The repair study (stage 4.5, first design)

Design and rationale: [VIOLATION_GAP_DESIGN_2026-10-25.md](../VIOLATION_GAP_DESIGN_2026-10-25.md),
option B. Code: `faultlab/research/repair_study.py` (the study), `faultlab/research/mechanic.py`
(the Mechanic), `faultlab/research/cli.py` (`faultlab study repair`). Nothing in `faultlab/research`
imports `backend/app`; the legacy referee scores envelopes through the bridge when asked.

## The question

Claude Actors' only failure on the public cases is a report-contract slip on dev-5: after a rejected
upgrade the confirmation is labelled `NOT_STARTED` where the convention is `NOT_REQUIRED`, every belief
true (oracle rule `notification_label_after_rejection`, legacy C5). Can a Mechanic, shown one such
trial, propose a runtime rule that repairs it without hurting anything else?

## Stages, every one pre-registered

1. **Controls.** `source_controls` (default 6) trials of the source case (dev-5) and
   `healthy_controls` (3) of the healthy case (dev-1), no rule. The gate opens when at least
   `gap_min` (3) valid source controls carry the target finding and at least `healthy_min_valid` (2)
   healthy controls are valid with no conformance finding. A closed gate ends the study (`NO_CHANGE`)
   having spent only the controls.
2. **Mechanic.** One fresh session per proposal slot (`slots`, default 2) on the first source control
   carrying the target finding, shown as a redacted counterexample: the scenario (public), every
   observation the agent was shown, its report, the pack's public report schema with every label each
   claim may carry (view v2, after smoke 1), the journal outcomes, the conformance findings as rule id
   plus the public one-line meaning of the check they reproduce (the oracle's detail sentence is
   withheld, `REDACTION = oracle-rule-id-and-public-check-meaning/v1`), the beliefs, and the task
   outcome. A proposal that does not validate (shape, hook, alias, claim) spends its slot. Slots are
   independent: nothing from a later stage reaches the Mechanic (`validation_feedback_forbidden`).
3. **Candidate.** `pairs` (3) fresh trials of the source case under no rule (B0) and under the
   proposal (L). Qualified only if every L trial is valid, carries neither the target nor any other
   conformance finding, has no false belief, reaches the expected outcome at least as often as B0
   (amended after smoke 1: Haiku truthfully reports `SAFE_UNRESOLVED` on dev-5 in five of twelve no-rule
   trials, which a working rule must not be failed for), and the policy acted in at least one L trial
   (amended after smoke 2: a rule that never fires "qualified" by chance). B0 is pooled with the
   controls for the reported gap, not gated.
4. **Validation.** The other public cases (dev-1, dev-2, dev-3, dev-4, dev-6), `pairs` per arm. A
   regression is attributed to the rule only where the rule acted (amendment 8, after the API pilot,
   whose zero-tolerance comparison of six L with six B0 trials failed two cases where the rule never
   acted, on the Actor's own variance). A case where the policy ran no step and blocked nothing in any L
   trial is *inert*: its L trials received the B0 inputs, so it passes and is reported as inert with both
   arms' counts. In any other case every L trial where the rule acted must be valid, carry no conformance
   finding and no false belief, reach the case's expected outcome and, in a `must_complete` case (dev-1,
   dev-6), complete. Before amendment 8 (smokes, confirmatory run, API pilot) the rule was comparative:
   every L trial completed its execution, no case gained a finding or a false belief or lost its expected
   outcome relative to B0, and the `must_complete` cases completed under L no less often than under B0.
5. **Decision.** `REPAIRED` at the first proposal that passes validation; `NO_CHANGE` when the gate
   did not open or no proposal passed; `INCOMPLETE` when a stage could not run (admission refused,
   worker stopped, infrastructure).

**Amendment 11 (2026-11-14).** Legacy referee violations (C1 to C8) now count as findings in both gates: no candidate L
trial may carry one, and no validation trial where the rule acted may carry one. It came from the unseen-case test, whose
second run passed two trials that had broken the referee's call limit. Runs before it used the gates without this term.

A valid trial (controls, candidate, validation trials where the rule acted) completed its execution and fired every scheduled fault; an absent
report is the agent's scored failure, not an invalid trial. Each trial runs with a fresh adapter (no
state crosses trials). Every batch is capped at its trials' bound; the
study refuses to start when its maximum bound exceeds `--study-dollars`. The record
(`repair-study.json`) is rewritten after every stage and carries the design digest, the pack digest,
the rule-language digest, the Mechanic's identity, every stage's rows, counts, cost and bundle, every
proposal verbatim, the decision and the seven read-outs of the design note.

## Advice rules (2026-11-14)

A `require_label` block tells the agent the expected label, but the correction spends one of its turns, and a report
blocked on its last turn cannot be corrected. That cost showed in development (smoke 2: two trials ran out of turns) and
in the unseen-case runs (three of 72 trials under the rule). The rule language now has a second hook, `before_agent_turn`,
whose only step, `advise_label`, shows the agent the label a rule expects as soon as the rule's condition holds in the
delivered evidence: before each turn for the model actor, with each tool result for the Claude Agent adapter. Advice
blocks, calls and rewrites nothing and costs no turn. The agent may still report otherwise, so a policy that wants
enforcement keeps a `require_label` step too. The Mechanic sees the new hook and the turn cost of a block in the rule
language (`faultlab-rule-language/v2`). Evidence: `backend/tests/v2/test_report_gate.py` (advice shown only once the
rejection is delivered, one turn fewer than a block, no enforcement on its own, the gate as a backstop, both adapters).

**Advice presentation (2026-11-15).** In unseen comparison 1 Haiku ignored the advice in 34 of 81 trials, yet corrected
every report a block refused while a turn was left (78 of 78). In the dev-5 bundles of repair study v3 the pattern is the
same: shown the advice, the agent still wrote `NOT_STARTED`, and it wrote `NOT_REQUIRED` only after the refusal. The advice
read as an expectation ("a runtime rule expects ..."); the block states a requirement and its consequence. Adapters now
take `advice_presentation`: `expectation` (the default, byte-identical to what ran, settings digests unchanged) or
`requirement`, which shows advice that the report gate enforces under the same condition (`enforced_advice`) as the gate's
own requirement (`rule_requirements`, in the words a block uses) with an `instruction` that a report not meeting it will be
refused, record nothing and cost a turn, and on the final turn that a refusal could not be corrected. Advice no gate
enforces is still shown as an expectation, so no refusal is announced that would not happen. The option is on
`faultlab run`, `faultlab study repair` and `faultlab study unseen` (`--advice-presentation`) and is recorded in the
adapter's settings digest only when it is not the default. Evidence: `backend/tests/v2/test_report_gate.py` (the mirror
check, both presentations through both adapters, the final-turn note, the pinned digest of comparison 1's L arm).

**Development check, 2026-11-15** (declared before the run, sha256 `2a2e9dfe…57fc`; declaration, logs, read-outs and bundles in
`artifacts/advice-presentation-dev-1-2026-11-15/`). The L3 rule, unchanged, on dev-5 with Haiku 5.5 on the API: 12 trials
with the advice shown as an expectation (E), then 12 as the gate's requirement (Q). E: a block in 7 of 12 trials (the agent
still proposed `NOT_STARTED` and was refused, then corrected). Q: a block in 0 of 12; every first report carried
`NOT_REQUIRED`. Both arms: no slip, no side effect, 12 of 12 correct refusals; 5.5 model calls per trial under E, 5.0 under
Q. Fisher p = 0.0046 for the blocks. The declared go/no-go was **PROCEED** to an unseen-case comparison. This is one public
case, the one the rule was built from, so it is development evidence only. $0.0705 of API money, 4 minutes.

The unseen-case comparison that followed (comparison 2, [UNSEEN_STUDY.md](UNSEEN_STUDY.md#runs)) ran both presentations on 14
new rejected-upgrade cases, 168 trials each: blocks 98 of 168 as an expectation and 0 of 168 as a requirement, no slip and no
side effect under either, and both studies TRANSFERRED. Its declared criterion also needed fewer side effects, and there were
none to reduce, so the requirement presentation is not shown better there. The default stays `expectation`.

**Development check 2, final turn, 2026-11-15** (declared before the run, sha256 `11f0b4c2…1898`; declaration, logs, read-outs and
bundles in `artifacts/advice-final-turn-dev-2-2026-11-15/`). Comparison 2 never showed the advice on the reserved final turn,
where comparison 1's side effects came from. This check forced it: the L3 rule on dev-5 with the turn budget cut from 8 to 5 model
calls (in check 1 every Q trial first saw the advice on its fifth call), 24 trials per presentation, E first. Declared go/no-go:
PROCEED to an unseen-case test of late evidence if E has at least 4 side-effect trials and Q at most a quarter as many, with no
slip. **INCONCLUSIVE**: E had 3 side-effect trials, one short of showing that the check produced the situation.

| 24 trials per arm | E: expectation | Q: requirement |
|---|---|---|
| First advice on the fifth and last allowed call | 12 | 13 |
| First advice on the fourth call | 10 | 11 |
| Rule never acted (the agent reported before the rejection arrived) | 2 | 0 |
| Trials with a blocked report | 5 | 0 |
| Side effect: a block on the last call, then no report | 3 | 0 |
| Correct refusal | 19 | 24 |
| Slip | 0 | 0 |

The shorter budget made the agent faster: in about half the trials it saw the rejection a call earlier than in check 1. Under E,
3 of the 12 trials whose first advice came on the last call were refused and ended with no report, and the other 9 reported the
expected label. The 2 blocks on the fourth call were corrected on the fifth. Under Q, with the final-turn note, none of the 13
was refused. Side-effect trials 3 of 24 against 0 of 24 (Fisher p = 0.23). This agrees with the requirement presentation
preventing the final-turn side effect, but there were too few events to show it. Across dev-1, comparison 2 and this check,
no report shown advice as a requirement was refused: 0 of 204 trials. The bundles were read by hand: each of E's three side
effects is one refused report on the fifth call, with the advice first shown on that call, and no report.
$0.1247 of API money, 7 minutes.

The unseen-case comparison of late evidence that followed (comparison 3, [UNSEEN_STUDY.md](UNSEEN_STUDY.md#runs)) kept the 8-call
budget and used four new schedules built so that the advice tends to come first on the final turn. By its declared criterion the
requirement presentation was **judged better on late evidence**: side-effect trials 11 of 96 as an expectation and 0 of 96 as a
requirement (the first advice came on the last call in 16 and 14 trials). Both studies were NOT_TRANSFERRED, because the rule
acted in only 19 of 96 trials each. The default stays `expectation`, so that earlier launch commands and adapter digests still
reproduce. For new runs of an advice rule the evidence favours `--advice-presentation requirement`; it also makes a wrong rule
easier to obey, and no run has yet shown the agent wrong advice.

## The Mechanic

`ClaudeCodeMechanic`: Claude Code through the Claude Agent SDK on the owner's subscription, the same
scrubbed environment and empty working directory as the Claude Agent adapter, three MCP tools
(`get_counterexample`, `get_rule_language`, `propose_rule`), no files, no network, `max_turns` 8.
Turns and tokens are accounted and shadow-priced at the model's API rates. `ScriptedMechanic` proposes
given policies for tests and plumbing checks; a run with it is labelled as such and is not repair
evidence (the standing rule of CURRENT_STATUS.md).

## Running it

```bash
.venv/bin/python -m faultlab study repair --store <trials.sqlite3> --out <dir> \
  --adapter claude-agent --model claude-haiku-5-5 --execute-live --dollars 0.034 \
  --mechanic claude-agent --mechanic-model claude-sonnet-5-5 --mechanic-dollars 0.84 \
  --study-dollars 4.5 --declaration <DECLARATION.json>
```

Offline plumbing: `--adapter reference-orders --mechanic none` (the reference agent never slips, so
the gate stays closed) or `--mechanic scripted:<policies.json>`. The defaults are the design note's
(6/3 controls, gap 3, 3 pairs, 2 slots, the five validation cases, `must_complete` dev-1 and dev-6).

## Evidence

`backend/tests/v2/test_repair_study.py`: a closed gate ends at the controls without consulting the
Mechanic; a slipping agent opens the gate and the right rule is `REPAIRED` through candidate and
validation (the redacted view checked field by field, bundles per batch, read-outs); an invalid
proposal spends its slot and a rule that does not fire is not qualified; a rule that repairs the
source but blocks truthful reports elsewhere fails validation; the declared-cap refusal and the
command offline.

## Runs

- **Smoke 1, 2026-10-26** (subscription, $0; `artifacts/repair-study-smoke-2026-10-26/`): Haiku Actor,
  Sonnet Mechanic; the gate opened (4 of 6), both slots proposed valid policies at the first attempt,
  neither qualified (one action-only, one requiring the slip's own label); NO_CHANGE in 181 s. The two
  amendments above came out of it; the write-up is in the design note's build record.
- **Smoke 2, 2026-10-26** (subscription, $0; `artifacts/repair-study-smoke-2-2026-10-26/`): amendments 1 and 2;
  the gate opened (4 of 6); both slots proposed `require_label NOT_REQUIRED` under the upgrade's
  `terminal_failure` at the first attempt. Slot 1 acted (six blocked proposals, one relabelled) but two
  trials ran out of turns; slot 2 had its condition on the wrong operation, never acted, "qualified" by
  chance and failed validation on the Actor's own variance. NO_CHANGE in 466 s. Amendments 3 to 7 followed
  (design note, build record).
- **Smoke 3, 2026-10-26** (subscription, $0; `artifacts/repair-study-smoke-3-2026-10-26/`): amendments 1 to 6;
  **REPAIRED** at slot 1 with `require_label notification_outcome` to every label but NOT_STARTED after the
  upgrade's terminal failure; the rule acted in all three L trials and Haiku re-reported NOT_REQUIRED each
  time; all five validation cases passed; 45 trials, 389 s, $0.118 API-equivalent. Pilot-grade (three
  pairs, a design amended during the smokes); the design is frozen at 6e179d0 for a confirmatory run.
- **Confirmatory replication, 2026-10-28** (subscription, $0; `artifacts/repair-study-confirm-2026-10-28/`): the
  frozen design with six pairs, declared before the run; **REPAIRED** again at slot 1 with `require_label
  notification_outcome [NOT_REQUIRED]` after the upgrade's terminal failure; L 0 of 6 target against B0 4 of 6,
  the rule acted and was obeyed in all six L trials; all five validation cases passed at 6 of 6; 81 trials,
  692 s, $0.184 API-equivalent.
- **API pilot, 2026-10-28** (Anthropic API, $0.4575; `artifacts/repair-study-api-pilot-2026-10-28/`): Haiku through the
  model actor, the frozen design with six pairs; both proposals were the convention and qualified (slip 0 of 12
  under L against 11 of 12 under B0); both failed validation in a case where the rule never acted (dev-6, dev-3:
  the Actor's own variance); **NO_CHANGE**, as declared. Amendment 8 (validation attributes regressions only where
  the rule acted) is pre-registered in the design note for any second pilot.
- **Second API pilot, 2026-10-29** (Anthropic API, $0.2360; `artifacts/repair-study-api-pilot-2-2026-10-29/`): the
  first pilot's setup under amendment 8 (35e401f). Slot 1 proposed the convention; L 0 of 6 target against B0 6 of 6,
  and the rule acted in all six L trials. All five validation cases were inert and passed; every validation trial
  completed without a finding in both arms, so the earlier comparative rule would also have passed them.
  **REPAIRED**; 82 trials, 716 s.
- **Repair study v3, 2026-11-14** (Anthropic API, $0.2376; `artifacts/repair-study-v3-2026-11-14/`): rule language v2 (advice)
  and amendment 11, otherwise the second pilot's setup. The gate opened (3 of 6). Slot 1 proposed, at its first attempt, advice and a
  block together: `advise_label notification_outcome [NOT_REQUIRED]` before each agent turn and `require_label` at the report gate,
  both after the upgrade's terminal failure. Candidate: L 0 of 6 target against B0 5 of 6, correct refusals 6 of 6 against 1 of 6, no
  legacy violation. The agent was shown the advice on 10 turns and still proposed the slip 4 times, each caught by the block. All
  five validation cases were inert and passed. **REPAIRED**; 81 trials, 675 s. A development qualification: the advice did not stop
  Haiku from proposing the slip, so whether it removes the block's cost is left to the unseen-case comparison.

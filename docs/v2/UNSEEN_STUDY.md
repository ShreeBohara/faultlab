# The unseen-case test

Code: `faultlab/research/unseen_study.py`; commands `faultlab study unseen-draw` and `faultlab study unseen`;
tests `backend/tests/v2/test_unseen_study.py`. The decision rule below was committed before any case was drawn.

## The question

The repair study qualified one rule on the public cases, and dev-5 is the only public case with a rejected upgrade.
With the rule frozen: does it still repair the report slip when the upgrade is rejected under other fault schedules,
and does it stay harmless on schedules with no rejection?

## The cases

`case_space` lists 99 candidate schedules, the orders pack's own fault grammar minus the six public cases: 55 where the
upgrade ends in a terminal rejection (`rejected`) and 44 where it does not (`other`). The space grew from 30 on 2026-11-14
(v2, 64), adding a stale read of three versions, a lost upgrade response before a rejection or a success, and flaky
confirmations on the history fixture; the first 30 come first and unchanged, and runs 1 to 3 drew only from them.
On 2026-11-15 (v3) the 17 v2 candidates that paired a lost upgrade response with a delayed completion were taken out: the
kernel loses a reply only on a write that committed at once, and a delayed completion leaves the write pending, so those
faults could never both fire (`all_faults_can_fire`). The reference check had rejected every one of them in comparison 1's
draw, which left only 19 playable rejected candidates, all now drawn. v3 adds outages: one or two requests to `get_order`,
`update_order` or `get_operation_status` fail before admission, then a rejection after one to three ticks (36 candidates),
or the outage alone or before a success (16). The reference agent plays all 52 cleanly. Delays stop at four ticks, so that
the turn budget measures the agent and not the wait. Each stratum is shuffled by a seed text made of the commit holding
this code and the frozen rule's digest, so the order is fixed before the draw. The draw keeps the first four candidates
per stratum that the reference agent plays cleanly, leaving out the cases of earlier draws. Nobody picks a case. The draw
prints only counts and a digest, and
the case file and trial bundles stay outside the repository.

These are new schedules of the same task on the same two fixtures with the same fault types. A result here says nothing
about other tasks, other fixtures or other fault types.

## Trials and decision

Each case runs `pairs` (6) trials with no rule (B0) and `pairs` under the frozen rule (L) (since 2026-11-14 an `other` case
may run `other_pairs`, and the draw may keep fewer `other` cases, `--per-other`), each within the repair study's
limits of 8 model calls, 18 HTTP attempts and 90 seconds (amendment 10, after run 2; runs 1 and 2 allowed 12, 24 and 120).

- A `rejected` case (amendment 9, after run 1): every L trial completed its execution; the rule acted in at least `pairs - 1`
  of them; each trial where it acted carries no target or other conformance finding, no legacy referee violation (amendment 10)
  and no false belief; and those trials
  reach the expected outcome at least as often, as a rate, as the B0 trials that completed. Whether another scheduled fault
  also fired is not judged, because the rejection is what the rule answers. Run 1 used the repair study's candidate gate
  instead: every L trial valid, no target or other finding, no false belief, the expected outcome no less often than under
  B0, and the rule acted in at least one L trial.
- An `other` case passes the validation rule of amendment 8: inert if the rule never acted, otherwise every trial where
  it acted is valid, carries no finding and no false belief, and reaches the expected outcome.

`NOT_TRANSFERRED` if any case failed. `INCONCLUSIVE` if none failed but the slip appeared in fewer than `gap_min` (6) of
the B0 trials of the rejected cases, since then there was little to repair. `TRANSFERRED` otherwise. `INCOMPLETE` if a stage
could not run. The test runs once per draw: no rerun, and no change to the rule, the cases or this rule after a result.

## Running it

```bash
.venv/bin/python -m faultlab study unseen-draw --store <draw.sqlite3> --out <dir> --cases <cases.json> \
  --seed-text "<commit>|<policy digest>"
.venv/bin/python -m faultlab study unseen --store <trials.sqlite3> --out <dir> --cases <cases.json> --policy <rule.json> \
  --adapter model-actor --model anthropic:claude-haiku-5-5 --execute-live --dollars 0.034 --study-dollars 3.27 --declaration <DECLARATION.json>
```

## Runs

**Run 1, 2026-11-08** (Anthropic API, $0.2898 with the preflight; Haiku 5.5 through the model actor; record and logs in
`artifacts/unseen-study-1-2026-11-08/`; declaration sha256 `76330a15…119a`; drawn from commit e5b2497). **NOT_TRANSFERRED**,
as declared: `unseen-r1` and `unseen-r3` failed the candidate gate. 96 trials, 742 s. The case file and bundles are not published.

| Rejected-upgrade cases, 24 trials per arm | No rule | Frozen rule |
|---|---|---|
| Slip, all trials | 21 | 0 |
| Slip, valid trials | 17 of 20 | 0 of 22 |
| Correct refusal, all trials | 3 | 24 |
| Rule acted | n/a | 24 |

The other four cases: the rule never acted in their 24 L trials, and all 48 trials of both arms completed with no finding.

Why two cases failed. The gate requires every L trial to be valid, and valid includes every scheduled fault having fired.
One L trial of `unseen-r1` and one of `unseen-r3` left a scheduled fault unfired (as did three and one B0 trials of those
cases). In both L trials the rule acted and the report was correct, and since a rule acts only after a terminal failure,
the unfired fault was the other fault of a two-fault schedule. The gate came from the source-case stage, where the one
scheduled fault is the rejection; on a two-fault schedule it also judges something the rule does not control. This is a
defect of this test's design, found after the result. It does not change the result.

What it shows, descriptively: on new schedules with a rejected upgrade the frozen rule removed the slip, and it stayed
silent where there was no rejection. What it does not show: a pass (the recorded decision is `NOT_TRANSFERRED`), other tasks,
fixtures or fault types, another Actor, or an active policy. Twenty-four trials per arm on four cases is small, and the draw
can be reproduced from the published seed text and code, so this draw is spent: it was unread, not secret.

Amendment 9 relaxes a gate after a failure. The owner approved it on 2026-11-08. It applies to new draws only, and run 1's
decision stands.

**Run 2, 2026-11-08** (Anthropic API, $0.2757 with the preflight; Haiku 5.5 through the model actor; record and logs in
`artifacts/unseen-study-2-2026-11-08/`; declaration sha256 `546784c7…1aff`; drawn from commit 5658d7d, leaving out run 1's
eight cases; amendment 9). **TRANSFERRED**, as declared. 96 trials, 754 s. The case file and bundles are not published.

| Rejected-upgrade cases, 24 trials per arm | No rule | Frozen rule |
|---|---|---|
| Slip | 22 | 0 |
| Correct refusal | 2 | 22 |
| Rule acted | n/a | 24 |
| Proposed reports blocked | n/a | 17 |

Two L trials of `unseen-r2` did not end in a correct refusal: both ended `VIOLATION` on the legacy referee's C8 (stay within the
declared limits). Each had one report blocked by the rule and used nine model calls. Across both unseen runs, C8 appears in
exactly the trials with more than eight model calls, and in no B0 trial. This test allowed twelve calls per trial where the
repair study allowed eight, so these two trials ran past a limit the referee still applies. A block costs the agent extra
calls, so this is a real cost of the rule, made visible by the higher allowance. The gate reads the oracle's conformance
findings, false beliefs and the rate of expected outcomes, not legacy findings, so it passed the case (4 correct refusals of 6
against 0 of 6 without the rule). The recorded decision stands, but it is not a clean pass.

The other four cases: the rule never acted in their 24 L trials, and all 48 trials of both arms completed with no finding.

This decision depends on amendment 9. One L trial of `unseen-r1` left a scheduled fault unfired, so the gate run 1 used would
have failed that case and this run. The amendment was written after run 1 failed, with the owner's approval and before this
draw. Across both runs, descriptively and under different gates: the slip appeared in 43 of 48 no-rule trials and 0 of 48
trials under the rule, on eight rejected-upgrade schedules, and the rule acted in no trial of the eight other schedules.

The record's `reason` text says "candidate gate": a wording slip in the code, corrected after the run. The gate applied was
amendment 9's (the design field `rejected_rule`).

What it shows: this rule, frozen before either draw, removed the slip on new rejected-upgrade schedules and stayed silent
elsewhere, with two trials under the rule going over the referee's call limit. What it does not show: other tasks, fixtures or fault types, another Actor, or an active policy. The space holds 30
candidates and the two draws used 16 of them. Twenty-four trials per arm on four cases is small.

**Run 3, 2026-11-14** (Anthropic API; Haiku 5.5 through the model actor; amendments 9 and 10; drawn from commit 2072240,
leaving out runs 1 and 2; final declaration sha256 `c723e157…a2eb`; record, logs and all three declarations in
`artifacts/unseen-study-3-2026-11-14/`). **NOT_TRANSFERRED**, as declared: `unseen-r3` failed. 96 trials, 836 s.

Two launches stopped before any case trial ran. In the first, the Anthropic API rejected the key in `.env` (HTTP 401), and
the owner replaced it. In the second, the preflight passed but the launcher's billing guard matched "402" inside a random
trial id. The guard now matches 402 only as a separate number; earlier launchers had the same latent flaw, which never
tripped. The draw, the code and the decision rule did not change between the launches.

| Rejected-upgrade cases, 24 trials per arm | No rule | Frozen rule |
|---|---|---|
| Slip | 18 | 0 |
| Correct refusal | 6 | 22 |
| Rule acted | n/a | 23 |
| Proposed reports blocked | n/a | 19 |

Why `unseen-r3` failed: in one L trial the rule blocked the agent's first report, and the agent then used up its 8 model
calls without submitting another, so the trial ended `VIOLATION` with no report (conformance `report_absent`,
`report_absent_no_citations`; legacy C5, C6, C7). No B0 trial of that case
carried a finding other than the target slip. One L trial of `unseen-r4` ended `SAFE_UNRESOLVED` without the rule acting; it
was not judged. The other four cases: the rule never acted in their 24 L trials, and every trial of both arms ended without a finding.

Across the three runs, descriptively and under three different gates: the slip appeared in 61 of 72 no-rule trials on
rejected-upgrade schedules and in 0 of 72 trials under the rule. Three of the 72 trials under the rule had a problem that
no no-rule trial had: two over the referee's call limit (run 2) and this trial without a report (run 3), all three from the
extra calls a block costs the agent. On schedules without a rejection
the rule never acted. The rule reliably removes the slip, but its interruption sometimes costs a different failure. It is
not ready to be an active policy.

**Comparison 1, 2026-11-14/15** (Anthropic API; Haiku 5.5 through the model actor; amendments 9 and 10; two frozen rules on one
fresh draw from commit 09f8a40, leaving out the 24 cases of runs 1 to 3; declaration sha256 `ccf9a075…4245`; both records, the
logs, the declaration and the comparison in `artifacts/unseen-comparison-1-2026-11-14/`). The question, declared before the
run: does the rule the Mechanic wrote when advice was available (**L3**, repair study v3: `advise_label` before each turn plus
`require_label` at the report gate) remove the slip with fewer blocks and fewer side effects than the rule it wrote with blocks
only (**R**, the second API pilot's rule, the one runs 1 to 3 tested)? Each rule ran its own study on the same 11 cases (7
rejected-upgrade cases with 12 pairs each, 4 other cases with 6 pairs each; 216 trials; 8 model calls, 18 HTTP attempts, 90 s),
R first. **Both NOT_TRANSFERRED**, as declared: R failed `unseen-r1`, `-r3`, `-r5`, `-r6` and `-r7`; L3 failed `unseen-r1` and
`-r5`. The four other cases passed under both: neither rule ever acted there.

| 84 rejected-case trials per arm | R study, no rule | R study, rule | L3 study, no rule | L3 study, rule |
|---|---|---|---|---|
| Slip | 64 | 0 | 57 | 0 |
| Correct refusal | 16 | 72 | 23 | 76 |
| Rule acted | n/a | 77 | n/a | 81 |
| Trials with a blocked report | n/a | 54 | n/a | 34 |
| Trials shown advice | n/a | n/a | n/a | 81 (110 turns) |
| Side effect: the rule acted and the trial has a finding or no report | n/a | 5 | n/a | 5 |
| Rule silent: the upgrade not yet rejected when the agent reported | n/a | 6 (+1 with no report) | n/a | 3 |
| Model calls, mean; trials at the 8-call cap | 6.37; 15 | 6.86; 33 | 6.37; 14 | 6.57; 26 |

The declared primary read-outs, as description and not as a decision: trials with a block 54 of 84 under R and 34 of 84 under
L3 (two-sided Fisher exact p = 0.0032); side-effect trials 5 of 84 under each (p = 1.0).

What the numbers say:

- **Both rules remove the slip completely**: 0 of 168 trials under a rule against 121 of 168 without one.
- **Advice cut the blocks by about a third but not the side effects.** Of the 81 L3 trials shown advice, 47 reported the
  right label at once. In 34 the agent proposed a report without the expected label anyway and was blocked: in 29 a turn was
  left, the advice came again and the agent corrected its report; in 5 the advice had first appeared on the reserved final turn, so the block left no turn.
- **Every side effect, under either rule, is the same event**: one blocked report on the eighth and last model call, then no
  report (`VIOLATION`; conformance `report_absent`, `report_absent_no_citations`; legacy C5, C6, C7). No false belief, no C8 and
  no wrong label appeared under either rule. A block that left a turn was always corrected to a clean refusal: 78 of 78.
- **The count of failed cases does not compare the rules.** L3's two failed cases are side effects only. Three of R's five
  (`r1`, `r5`, `r7`) also had too few trials where the rule acted (9 or 10 of 12; the gate needs 11): the agent spent its calls
  before the rejection arrived and reported the upgrade unresolved (`SAFE_UNRESOLVED`), so the rule had nothing to act on. Up
  to that point the agent's inputs are the same under both rules and without one, so those trials are chance. One R trial also
  ended with no report while the rule was silent; no trial without a rule (168) lacked a report.

So the side effect is structural: a rule that blocks can leave an agent without a report when the evidence arrives late, and
advice that the agent ignores almost half the time does not prevent it. Neither rule is ready to be an active policy. The
launch's summary script crashed on a dictionary key after both studies had finished and been saved; the read-outs above come
from the saved records through `faultlab study compare` (written afterwards; it reads record files only) with the definitions in
the declaration. Money: $1.6832 of API money (R $0.8433, L3 $0.8371, preflight $0.0027), 2,767 model calls, 83 minutes.

**Comparison 2, 2026-11-15** (Anthropic API; Haiku 5.5 through the model actor; amendments 9 and 10; one frozen rule, L3, shown two
ways on one fresh draw from case space v3 at commit f680af4, leaving out the 35 cases of runs 1 to 3 and comparison 1; declaration
sha256 `591fd65c…b861`; both records, the logs, the declaration and the comparison in `artifacts/unseen-comparison-2-2026-11-15/`).
The question, declared before the run: does showing L3's advice as the report gate's requirement (**Q**, `--advice-presentation
requirement`: the advice the gate enforces appears as `rule_requirements`, with the refusal's consequence and a final-turn note)
leave fewer trials with a block and fewer side effects than showing it as an expectation (**E**, the default, which shows advice
exactly as comparison 1's L3 arm did), while still removing the slip? The declared criterion: Q is better on these cases if it has fewer
side-effect trials than E, at most half as many trials with a block, and no slip. Each presentation ran its own study on the
same 18 cases (14 rejected-upgrade cases with 12 pairs each, every one an outage before a rejection; 4 other cases with 6 pairs
each; 384 trials; 8 model calls, 18 HTTP attempts, 90 s), E first. **Both TRANSFERRED**, as declared: every rejected case passed
amendment 9's gate and every other case the validation rule. These are the first `TRANSFERRED` decisions under amendment 10's
limits. **The requirement presentation is not shown better here**, by the declared criterion: it removed every block, but E
had no side effect for it to remove.

| 168 rejected-case trials per arm | E study, no rule | E study, rule as expectation | Q study, no rule | Q study, rule as requirement |
|---|---|---|---|---|
| Slip | 138 | 0 | 135 | 0 |
| Correct refusal | 30 | 168 | 32 | 168 |
| Rule acted | n/a | 168 | n/a | 168 |
| Trials shown advice (turns) | n/a | 168 (267) | n/a | 168 (168) |
| Trials with a blocked report | n/a | 98 | n/a | 0 |
| Side effect: the rule acted and the trial has a finding or no report | n/a | 0 | n/a | 0 |
| Rule silent | n/a | 0 | n/a | 0 |
| Model calls, mean; trials at the 8-call cap | 5.33; 1 | 5.86; 4 | 5.30; 5 | 5.24; 2 |

The declared primary read-outs, as description and not as a decision: trials with a block 98 of 168 under E and 0 of 168 under
Q (two-sided Fisher exact p = 7.7e-39); side-effect trials 0 of 168 under each (p = 1.0). The saved `comparison.json` prints the
first p-value as 0.0: `faultlab study compare` rounded to six decimal places. It now keeps six significant digits; the saved file
is left as the run wrote it.

What the numbers say:

- **Both presentations remove the slip completely**: 0 of 336 trials under the rule against 273 of 336 without it.
- **Shown as a requirement, the advice was followed the first time in all 168 trials**: every first report carried the expected
  label, and no report was blocked. Shown as an expectation, the agent proposed a report without the expected label in 98 of 168
  trials, was blocked once, saw the advice again and corrected its report every time (98 of 98). The other 70 reported the
  expected label the first time.
- **Q took fewer model calls**: 5.24 a trial against 5.86, and each whole study cost $1.18 against $1.28, B0 arms included.
- **Why neither presentation had a side effect, unlike comparison 1.** Here the rule acted in every trial and no block fell on
  the last call. In comparison 1, every side effect was a block on the reserved final turn when the evidence arrived late.
  These cases, each an outage before a rejection one to three ticks later, never produced that, so this run cannot say whether
  the requirement presentation prevents it: its final-turn note is untested on unseen cases.
- **The other cases.** The rule never acted on them under either presentation. A silent rule shows nothing, so those L trials see
  what B0 trials see. Seven of the 96 other-case trials ended with no report after using all 8 calls, all on `unseen-o3` and
  `unseen-o4`: six without a rule (four in E's study, two in Q's) and one under Q's silent rule. That failure belongs to the
  turn budget, not the rule.

What it shows: on 14 new rejected-upgrade schedules the learned rule L3 transferred under both presentations, and showing its
advice as the gate's requirement removed every block. What it does not show: that the requirement presentation reduces side
effects (there were none to reduce), the late-evidence case, other tasks, fixtures or fault types, another Actor, or an
active policy. The records of this run carry the presentation only in their notes and in the launcher; records written after
it name the Actor's adapter, model and presentation in an `actor` field. Money: $2.4678 of API money (E $1.2824, Q $1.1826,
preflight $0.0027), 4,242 model calls, 113 minutes.

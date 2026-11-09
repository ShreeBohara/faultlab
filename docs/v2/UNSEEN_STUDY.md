# The unseen-case test

Code: `faultlab/research/unseen_study.py`; commands `faultlab study unseen-draw` and `faultlab study unseen`;
tests `backend/tests/v2/test_unseen_study.py`. The decision rule below was committed before any case was drawn.

## The question

The repair study qualified one rule on the public cases, and dev-5 is the only public case with a rejected upgrade.
With the rule frozen: does it still repair the report slip when the upgrade is rejected under other fault schedules,
and does it stay harmless on schedules with no rejection?

## The cases

`case_space` lists 30 candidate schedules, the orders pack's own fault grammar minus the six public cases: 13 where the
upgrade ends in a terminal rejection (`rejected`) and 17 where it does not (`other`). Delays stop at four ticks, so that
the turn budget measures the agent and not the wait. Each stratum is shuffled by a seed text made of the commit holding
this code and the frozen rule's digest, so the order is fixed before the draw. The draw keeps the first four candidates
per stratum that the reference agent plays cleanly, leaving out the cases of earlier draws. Nobody picks a case. The draw
prints only counts and a digest, and
the case file and trial bundles stay outside the repository.

These are new schedules of the same task on the same two fixtures with the same fault types. A result here says nothing
about other tasks, other fixtures or other fault types.

## Trials and decision

Each case runs `pairs` (6) trials with no rule (B0) and `pairs` under the frozen rule (L).

- A `rejected` case (amendment 9, after run 1): every L trial completed its execution; the rule acted in at least `pairs - 1`
  of them; each trial where it acted carries no target or other conformance finding and no false belief; and those trials
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
  --adapter model-actor --model anthropic:claude-haiku-5-5 --execute-live --dollars 0.0504 --study-dollars 4.84 --declaration <DECLARATION.json>
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

The two L trials without a correct refusal, both in `unseen-r2`, ended 2 as VIOLATION, with no finding and no false belief. The other
four cases: the rule never acted in their 24 L trials, and all 48 trials of both arms completed with no finding.

This decision depends on amendment 9. One L trial of `unseen-r1` left a scheduled fault unfired, so the gate run 1 used would
have failed that case and this run. The amendment was written after run 1 failed, with the owner's approval and before this
draw. Across both runs, descriptively and under different gates: the slip appeared in 43 of 48 no-rule trials and 0 of 48
trials under the rule, on eight rejected-upgrade schedules, and the rule acted in no trial of the eight other schedules.

The record's `reason` text says "candidate gate": a wording slip in the code, corrected after the run. The gate applied was
amendment 9's (the design field `rejected_rule`).

What it shows: this rule, frozen before either draw, removed the slip on new rejected-upgrade schedules and stayed silent
elsewhere. What it does not show: other tasks, fixtures or fault types, another Actor, or an active policy. The space holds 30
candidates and the two draws used 16 of them. Twenty-four trials per arm on four cases is small.

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
per stratum that the reference agent plays cleanly. Nobody picks a case. The draw prints only counts and a digest, and
the case file and trial bundles stay outside the repository.

These are new schedules of the same task on the same two fixtures with the same fault types. A result here says nothing
about other tasks, other fixtures or other fault types.

## Trials and decision

Each case runs `pairs` (6) trials with no rule (B0) and `pairs` under the frozen rule (L).

- A `rejected` case passes the repair study's candidate gate: every L trial valid, no target or other conformance finding,
  no false belief, the expected outcome no less often than under B0, and the rule acted in at least one L trial.
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

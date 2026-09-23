# Phase 5 progress

Protocol: [PHASE5_EXPERIMENT.md](PHASE5_EXPERIMENT.md). Results: [PHASE5_RESULTS.md](PHASE5_RESULTS.md).
Checked means done and verified, not planned.

## Preparation

- [x] Adversarially reviewed the Phase 4 work before building on it: six independent reviewers, every finding sent to a separate agent instructed to refute it. 18 findings survived, 15 did not.
- [x] Fixed the three real code defects that survived: the arm-coupled decision rule, the rejection flag that could describe a committed write as refused, and the logical-call record lost to a mid-call budget exception.
- [x] Fixed the four supporting defects: assessment persisted before remote telemetry, restart releases a study's reservation, descriptors declare only applicable keys, and the indistinguishability test no longer strips fields it claims to protect.
- [x] Corrected four wrong numbers in the Phase 4 write-up and recorded every correction in a Corrections section rather than editing silently.
- [x] Confirmed the corrections change nothing: re-deciding both saved Phase 4 studies under the corrected rule reproduces REGRESSION with identical violation counts, regressed cases and pooled completions.
- [x] Measured the abort risk that killed Phase 3 B2 from saved data: 2/27 untriggered on the source case across every baseline trial, 1/6 in Phase 4's control arm, giving 20-42% loss during controls alone and 70-80% across a full study.
- [x] Made an untriggered or invalid trial non-fatal to a completion study, with the acceptance gates byte-identical and a new test asserting a stage containing an invalid trial can never qualify a candidate.
- [x] Verified the repair is expressible, legal at the hook, and proven live by the handwritten reference actor (9/9 source trials completed).

## Live execution

- [x] Shared allowance reconciled: 1,762 requests and $37.46248 charged, $962.53752 remaining before dispatch.
- [x] Source frozen (175 files), database snapshotted, backend restarted per study on the frozen source with the recorded settings.
- [x] Study 5A `completion-study-889f75d6d170418e9ff654f409a1952b` (V4-Pro-0813 Mechanic): NO_CHANGE, 12 episodes, 81 calls, 12/12 verified. **The first Mechanic request ever made with V4 on this objective.**
- [x] Study 5B `completion-study-122d93e0dfa94c7484a46dd65b83aab2` (V3.1 Mechanic, matched control): NO_CHANGE, 12 episodes, 85 calls, 12/12 verified.
- [x] Predeclared read-out recorded: 0 of 4 proposals contain a notification `retry_original_request` step.
- [x] Every attempted trial, proposal and duplicate retained. No resampling, no replacement, no third model, no extra slot.

## Manual verification

- [x] Read every proposal's raw model output and quoted the models' own words rather than paraphrasing.
- [x] Confirmed both second proposals are byte-identical duplicates by policy hash while their explanations claim novelty.
- [x] Confirmed both studies passed their declared controls (3/3 valid source with zero completions, 3/3 valid healthy completing).
- [x] Confirmed `policy-v0` is still the active policy in both campaigns and that no policy record was accepted.
- [x] Reconciled cost and updated results, limitations, memory and the central checklist.

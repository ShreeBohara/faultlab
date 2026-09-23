# Phase 6 progress

Protocol: [PHASE6_EXPERIMENT.md](PHASE6_EXPERIMENT.md). Results: [PHASE6_RESULTS.md](PHASE6_RESULTS.md).
Checked means done and verified, not planned.

## Part A — comprehension probe

- [x] Declared the probe, the two questions, the 2x2x2 design, the read-out and the Part B selection rule before any paid call.
- [x] Built `scripts/experiments/comprehension_probe.py`: dry by default, requires `--execute-live` and a matching `--confirm-entity`, reads saved proposal inputs read-only, creates no campaign/study/trial/policy, asserts the provider returned the requested model.
- [x] Ran 8 requests, 2 models x with/without brief x 2 repeats, replaying the exact saved Phase 5 proposal contexts.
- [x] Result: **no response in any condition called a replay forbidden**; 6 of 8 said PERMITTED and quoted the contract. H1 not supported.
- [x] Recorded that the predeclared selection rule fired on a degenerate reading, and wrote the decision and its narrowed interpretation into the results **before** running Part B.

## Part B — the clarified brief

- [x] Applied exactly the declared clause, 114 characters, and archived the brief before and after.
- [x] Verified only `source_hash` moved: actor prompt, scorer, contract, capability, interpreter and adapter hashes identical to Phase 5.
- [x] Full suite green on the frozen source: 549 backend, 121 frontend, build, 3 browser fixtures.
- [x] Study 6A `completion-study-7aea25bfc3e34ac797b42e7d5128b110` (V4 Mechanic): NO_CHANGE, 12 episodes, 77 calls, 12/12 verified, **0 of 2 proposals contained a notification retry**, second proposal byte-identical to the first.
- [x] Study 6B `completion-study-387f536ab6a84e64b444719ff8fd557a` (V3.1 Mechanic): NO_CHANGE at controls, 6 episodes, 36 calls, 6/6 verified. One baseline control completed, so the declared gap did not reproduce and no proposal was requested.
- [x] No resampling, no replacement trial, no second Part B arm, no threshold changed.

## Findings recorded

- [x] The retain-and-continue fix saved study 6A: its candidate stage hit an untriggered trial with the exact Phase 3 B2 signature, was assessed INCOMPLETE rather than qualifying anything, and the run continued.
- [x] Measured the source gap honestly for the first time: **2 completions in 45 valid triggered baseline episodes, 4.4%**, implying a ~13% chance that a three-trial controls gate or candidate stage fails by variance alone. Recorded for a future declared phase; **not** fixed by loosening a gate.
- [x] Reconciled cost and updated results, limitations, memory and the central checklist.

# Phase 2: prove a useful repair

Started September 20, 2026. Shree authorized implementation, live experiments, independent review and a **new cumulative $1,000 ceiling**. Phase 1 records and uncommitted implementation are preserved. This phase follows the four-step plan agreed in chat: repeatability, justified fixes, the complete repair cycle, then independent verification and a clear demonstration.

## Progress

- [x] Confirm no active campaign and preserve the starting database and campaign inventory.
- [x] Assign separate investigations of repair timing/reporting, repeatability, and acceptance/transfer gates.
- [x] Declare controlled development experiments and cumulative accounting before dispatch.
- [x] Measure repeatability on fixed failures and healthy controls with the unchanged Actor and scoring.
- [x] Implement only evidence-supported changes; distinguish harness fixes from changed agent behavior.
- [x] Test changes offline and freeze the runtime before new live execution.
- [x] Run a versioned baseline and generated-repair experiment with sufficient full-batch headroom.
- [x] Inspect every attempted unique proposal and source pair; explicitly record unreached challenge/promotion.
- [x] Finish C2 under the amended runtime and record every new proposal and qualification result.
- [x] If a policy qualifies, verify restart persistence, untouched evaluation cases and independent-agent transfer. If it does not, preserve the failed result and declare a justified follow-up.
- [x] Verify incident export, fresh execution, local/Weave evidence and the actual dashboard workflow.
- [x] Complete independent review, final checks, result report and simple user instructions.

## Operating rules

- Root owns all paid dispatch. No simultaneous experiment schedulers. Subagents do not make provider calls.
- The $1,000 ceiling covers all new Phase 2 stores, campaigns and probes together. Campaign caps are allocations, not additional budgets. Keep conservative charges, measured token estimates and unknown usage separate.
- Existing per-campaign limits and protected evaluation reservations remain enabled. Use smaller allocations with enough reservation headroom, not a $1,000 single-campaign setting.
- Baseline and repaired arms use the same model, prompt, tools, report schema, service behavior, episode budgets and scoring. Only the policy differs.
- Original reports and all attempted trials remain recorded. No silent retries, answer rewriting, lucky-batch selection or relabeling rejected policies.
- Keep final evaluation cases out of repair feedback. Record every runtime or protocol amendment before affected execution.
- Automatic Aria setup/publication remains deferred as previously requested. No deployment or new public push is included in this phase.

Experiment details and amendments: [PHASE2_EXPERIMENT.md](PHASE2_EXPERIMENT.md).

## Current status

The declared experimental round finished with a measured engineering improvement and **no accepted learned policy**. A/C1 each ran 30 fixed trials: observed violations fell 19→1; C1 still left 11 tasks unfinished. B rejected its only unique generated candidate and skipped three duplicates. C2 found no qualifying failure and had five of eight recipes trigger.

The broader six-case development suite completed 36 valid trials: 18 live / 18 handwritten reference, all 30 faults triggered. Live outcomes:12 completed, 3 correctly rejected, 2 safe unresolved, 1 violation; reference:15 completed, 3 rejected. The notification retry problem and sporadic citation errors remain.

Export, integrity validation, historical playback and three fresh worlds passed as workflows. Fresh results did not reproduce the original C5 failure:2 safe unresolved / 1 C6 violation. All three traces verified. Unchanged backend restart preserved the records; no accepted-policy reuse is claimed.

Final totals: 149 trials including 18 offline, 886 model calls including 4 schema probes, 131 verified live traces, zero unknown usage. Conservative charges $18.92256; token-rate estimate $1.77595950; actual billed amount unavailable. All 26,670 pre-phase records remain unchanged.

Runtime 2 is `1261f1f30b3212ec9440e6faf14055656ea44c6a47ed0856563167b0892891a8`. Backend checks: 471 passed; final dashboard checks are recorded in the results. Original outcome gates T065/T088/T097/T100/T102 remain open. Completing this checklist does not assert accepted repair, final audit, selector comparison, Aria or learned-policy transfer. See [PHASE2_RESULTS.md](PHASE2_RESULTS.md).

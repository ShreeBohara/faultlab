# Phase 9 progress

Protocol: [PHASE9_EXPERIMENT.md](PHASE9_EXPERIMENT.md). Results: [PHASE9_RESULTS.md](PHASE9_RESULTS.md).
Checked means done and verified, not planned.

## Before any paid call

- [x] Declared a paired, interleaved, **concurrent** control — the thing Phase 8 lacked — with the primary read-out, the statistical test, the secondary read-outs, the replacement rule and the spend rules fixed in advance.
- [x] Built the `evidence_protocol` mechanism (allowlist beside the protocols in `diagnosis.py`, threaded through `completion_study.py`, the API and the CLI) so the control is runnable without touching the treatment.
- [x] **Gated both arms on byte-identity before spending**: arm T's format and legend diffed against Phase 8's saved `proposal-context-8a-1.json`; arm C's against Phase 6's saved context, with no `task_outcome` key on any episode row. Both passed.
- [x] Computed statistical power rather than assuming it, and raised n from 10 to 14 per arm on the result.
- [x] Ran a six-lens adversarial review (design, statistics, single-variable integrity, runner, tests, house rules) plus a refutation pass **before any paid call**: 47 findings raised, 30 confirmed, 17 refuted.

## What the review caught, and the fixes

- [x] **A Mechanic refusal was scored as "no draw" and the study resampled.** Six lenses found it independently. A refusal is a real answer that cannot contain the step, so the bug deleted only zeros — from whichever arm refuses more — and violated the phase's own never-repeat rule. Fixed: every resolved answer is a draw; only an absent or mid-parse-unresolved candidate is not.
- [x] **The historical Phase 8 tally was asymmetric in the treatment's favour** — V3.1's control study counted, V3.1's treatment study omitted. Corrected to 1 of 2 and stated model-separated.
- [x] **`INTERRUPTED` was missing from the terminal-status set**, the one non-happy status the engine emits; a stopped study would have hung the runner and then orphaned itself, burning the attempt cap in seconds.
- [x] **A failed study's campaign was dropped from spend accounting.** Campaigns are now registered before polling, so their spend always counts.
- [x] **An unreadable budget was treated as $0**; now a failed read aborts the phase. **`--confirm-entity` was compared to nothing**; now verified against the configured entity. **The declared Mechanic model was printed but never checked**; now verified against the live backend before every round.
- [x] **Interleaving was abandoned when the arms diverged.** Now strict alternating pairs with the leading arm swapped each round, ending as soon as either arm finishes.
- [x] Eliminated the duplicated read-out: one implementation in the runner, imported by the analyser, with a test asserting they are the same object.
- [x] Closed the reviewed test gaps: the HTTP route the runner actually uses, slot-2 presentation in both arms, a reservation assertion that actually tests the reservation, and every candidate shape in the read-out.
- [x] Full suite green on the frozen source: **559 backend**, 121 frontend, production build, 3 browser fixtures.
- [x] Only `algorithm_hash` and the derived `runtime_hash` moved; snapshot taken at 37,499 records.

## The run

- [x] 32 studies, 16 attempts per arm, strict alternating pairs on one backend, ~2.6 min each, **$53.56838**.
- [x] **Primary read-out: T 3 of 14, C 1 of 11. Fisher exact two-sided p = 0.604 — not significant.**
- [x] Ran to the declared attempt cap. No threshold, read-out or rule changed after data existed. No study that produced a proposal was repeated. 7 no-draw studies retained and replaced under the declared rule.
- [x] **Phase 8's causal claim withdrawn**, stated plainly in the results rather than quietly dropped.

## Findings recorded

- [x] **A generated policy qualified on the source case for the first time in the project's history** — T15, `SOURCE_QUALIFIED` with L 3 of 3 and B0 0 of 3, zero violations. Verified as the only such candidate ever, across every study in the store.
- [x] It then beat the baseline on four validation cases, regressed on none, and was correctly rejected for one violation on `notification-18`.
- [x] **That violation was an Actor hallucination, not a policy failure**: 12 of 13 cited evidence IDs were real; the thirteenth, `evidence-a20c6f2a5a8547f1b445a025extremely-9372`, exists nowhere in the store. The baseline failed the same case independently on C5/C6.
- [x] **The step works whenever it is proposed** — all four step-containing candidates completed the source case at least 2 of 3.
- [x] **The binding constraint is now measured**: candidate episodes violate C5/C6 at 16–28% against ~3% for baseline episodes.
- [x] **The duplicate-proposal pathology is endemic**: 16 of 32 studies wasted their second slot on a byte-identical policy.
- [x] **Source-gap leakage refined to 3.4%** across 88 valid triggered baseline control episodes, tightening Phase 6's 4.4% from 45.
- [x] Reconciled cost and updated results, limitations, memory and the central checklist.

# Phase 2 results — reporting improved; learned repair unproven

The declared Phase 2 experiments are finished. The report-protocol change reduced observed rule violations from 19/30 to 1/30 on the same fixed conditions, while 11/30 tasks still remained unfinished. No generated policy passed the acceptance gates. We also verified export, fresh execution, Weave readback and persistence after restart. [Checklist](PHASE2_TASKS.md) · [Predeclared experiments](PHASE2_EXPERIMENT.md).

## Changes verified before live execution

- Accurate primitive/condition semantics for the Mechanic, including pending observations and attempted writes without terminal receipts. Explicit original-report presence; no solved recovery recipe supplied.
- Local provider-redacted Actor-output events retain the actual returned text before schema validation, plus turn/report-required metadata and request hashes. These do not alter model inputs or qualify as remotely verified original reports.
- Timely original reports are captured before bounded trace finalization. Actual late returns and external cancellation remain failures/interruption as appropriate. Native context copies share the same completion boundary. A regression reproduced the telemetry defect; a historical scan found zero affected episodes, so it does not explain Phase 1 failures.
- Reproducible fixed-study harness with dry-default planning, fresh store/worlds, full-batch budget admission, frozen-source checks, explicit execution and no silent retry.

Before Experiment A: **456 backend tests, 34 frontend tests, production build and three browser fixtures passed**. Runtime 1 was frozen as `564c520062347881fdd559b712666949dfc1fd5b268f6fbdb6e22411a294a2b6`. The later runtime 2 checks and dashboard validation are recorded below.

## Fixed repeatability study

Ten repeats per condition, round-robin order; original V3.1 Actor, empty policy, fixed `order-1`, fresh worlds/operation/evidence IDs. All 30 trials were valid and all 20 scheduled faults triggered.

| Condition | Planned / attempted | Completed | Rule violation | Infrastructure error |
|---|---:|---:|---:|---:|
| Healthy | 10 / 10 | 10 | 0 | 0 |
| Upgrade succeeds after five ticks | 10 / 10 | 0 | 10 | 0 |
| Upgrade succeeds after four ticks | 10 / 10 | 1 | 9 | 0 |

The five-tick failures all attempted `send_confirmation` on the eighth, report-only turn. No extra business call was dispatched; no final report was submitted. The nine four-tick failures returned final report JSON with malformed evidence IDs. Schema validation rejected the actual answers, with no remaining turn for a model correction. The one valid four-tick report completed successfully. Raw final responses are retained, not repaired.

All 30 traces and the [Weave evaluation](https://wandb.ai/shreetbohara-quinstreet/Faultlab/r/call/01a0c009-1ce8-74f3-9854-b9122ca49feb) were verified. Campaign `campaign-25a7aa0ce7dd428aa05254f3e19e076c`; configuration `4ca1447b94c354d1ac0412eb3353fe57b57e0b50c23967c5c261f3ac4b5083c0`.

202 model requests; 649,156 input and 7,321 output tokens. Conservative request bound **$4.2218**; known-token estimate **$0.36911545**; zero unknown-usage requests; actual billed dollars unavailable. Complete records and local output analysis are under `artifacts/phase2-2026-09-20/repeatability-1/` and `repeatability-analysis.json`.

These counts establish concrete failure mechanisms and observed variability in a small development pilot. Fresh identifiers and provider behavior both vary; temperature zero is not a proof of deterministic execution. This is not a learned-policy improvement or production reliability estimate.

## Dashboard evidence

The before-and-after panel now joins only the exact 18 promotion pairs using episode IDs and frozen policy hashes. It excludes discovery totals and incomplete/mismatched evidence. A rejected promotion is shown as rejected rather than not run. Independent read-only review found no blockers; protected full-scenario validation remains the backend's responsibility.

After these frontend changes: **53 frontend tests, production build and three browser fixtures passed**. The optional automated actual-server test was skipped. Manual browser verification connected to the real backend and loaded Experiment B's live campaign, saved timeline, original report, fixed verdict and Weave links. No campaign was started by browsing.

## Generated repair: Experiment B — no change

Campaign `campaign-5a0af912a5244423b61b5f13cff4ec0f`, configuration `7953101f46b4dafc8f4d01915175b776bc10dc7d05689e7bb8741b723c61d5b5`. Actor/Mechanic V3.1; Explorer V4 Pro 0813. $400 campaign allocation inside the new cumulative $1,000 phase ceiling. Unchanged frozen runtime, eight discovery slots and four candidate slots. Ordinary autonomous discovery; no injected study recipe or human-authored repair.

Completed 42 trials and 298 model calls with no infrastructure errors. All 42 traces verified; the source comparison evaluation and incident dataset were published (publication records retained locally). Six discovery attempts found the source, three reproduced it, 21 reduction trials retained a five-tick delay, and six controlled-intervention trials supported diagnosis. The first generated policy passed one source trial and failed two; all three baseline controls failed the target. The failed candidate's raw final answers contained malformed evidence IDs even after its final correction turn. Three subsequent generated policies were structurally identical and received no fresh qualification trials. No challenge or promotion ran; baseline remains active.

Candidate hash `b71d832d46e971902a535f00fb2094ba40c7ecd68186b03888335be2f57f431b`. Proposal text is preserved, including inaccurate causal explanations; the fixed checks decide outcomes. Cost bound $6.40184; known-token estimate $0.63180699; zero unknown usage. Combined A+B bound $10.62364. No accepted learned-policy gain is claimed.

B's [paired source evaluation](https://wandb.ai/shreetbohara-quinstreet/Faultlab/r/call/01a0c018-bcaf-7092-9139-9f2594ae85e7) and incident dataset both reached verified readback. Exported bundle `bundle-acef33fdb546466fb16c6b3a5de61c54` is an incident fixture, not an accepted-policy bundle.

## Reporting protocol follow-up — implemented and reviewed

Four V3.1 capability requests accepted W&B's strict format using the exact existing report schema. No schema or scorer was relaxed; conflicting requests still produced syntactically valid reports. One synthetic response invented citations, illustrating that schema validity does not prove truthfulness. Cost bound $0.0836; token estimate $0.00068585.

Protocol `faultlab-reference-final-report/v1` now requests that strict schema only on an already report-required turn: the reserved last turn or after business actions close. It applies equally to baseline and repaired reference Actors. Earlier turns, the native agent driver, prompt, eight-turn limit, business tools and scoring remain unchanged. Schema tokens are admitted before charging a call. Original answers are retained; there is no answer repair, automatic citation selection, fallback or extra turn. The exact schema hash is `8033400b2631d0ae3bb864453a4f82b9b217aeed29ac245f6212afea2d840c77`.

A separate confirmed bug in diagnostic record identities was corrected: distinct incidents selecting identical recipes now save distinct intervention records. Parameterized same-/cross-campaign tests preserve both diagnoses and all 12 trials without overwriting the first record. This was not the cause of B's rejected repair.

Latest integrated checks: **471 backend tests, 53 frontend tests, production build and three browser fixtures passed**; independent review is clear. Runtime 2 is frozen as `1261f1f30b3212ec9440e6faf14055656ea44c6a47ed0856563167b0892891a8`, algorithm `c5948df5fc0772065bd0783ea0f97b18a7938c2f0fcb6d60ecfc72832faad735`. Source and protocol fingerprints are saved in `artifacts/phase2-2026-09-20/frozen-source-2.json`.

## Experiment C1 — reporting improved; tasks still unresolved

Same three public conditions, ten fresh trials each, fixed round-robin order, V3.1 Actor and empty policy. All 30 planned trials were valid, all 20 scheduled faults triggered, and all 30 original reports passed structural validation.

| Condition | Planned / attempted | Completed | Safe unresolved | Rule violation | Infrastructure error |
|---|---:|---:|---:|---:|---:|
| Healthy | 10 / 10 | 9 | 1 | 0 | 0 |
| Upgrade succeeds after five ticks | 10 / 10 | 0 | 10 | 0 | 0 |
| Upgrade succeeds after four ticks | 10 / 10 | 9 | 0 | 1 | 0 |

The five-tick runs now returned truthful unresolved reports instead of requesting a tool on the last turn. **None completed the task.** One four-tick report cited an ID that did not match delivered evidence; the unchanged C6 check rejected it despite valid JSON. The healthy unresolved run repeatedly checked a notification operation it had not started. Every result remains in the record.

Across these two small baseline pilots, A had 11 completed tasks and 19 violations; C1 had 18 completed, 11 safe unresolved and one violation. Healthy completion fell from 10/10 to 9/10. This is an observed baseline engineering improvement, **not learned-policy gain**, perfect reliability or a guarantee for a fresh run. Fresh identifiers and provider behavior still vary.

All 30 traces and the [C1 Weave evaluation](https://wandb.ai/shreetbohara-quinstreet/Faultlab/r/call/01a0c026-edf9-7679-8f9a-597188d3ea95) were verified. Campaign `campaign-4238713c443f49a7ba4caa2ee4ca9241`; configuration `a1d11d42aa7ca11f8311f0acc63de68623d033a6c4d5b564124665c8942c4b24`.

206 calls; 666,631 input and 9,588 output tokens. Conservative bound **$4.3054**; known-token estimate **$0.38246725**; zero unknown usage; actual billed dollars unavailable. Complete records: `artifacts/phase2-2026-09-20/repeatability-2/summary.json` and `repeatability-2-analysis.json`. Combined Phase 2 conservative charges before C2 were **$15.01264**, leaving **$984.98736** of the shared ceiling.

## C2: autonomous search after the reporting change

Campaign `campaign-add97a955f8f4f3a961aa62a14286807` ended NO_CHANGE after eight discovery episodes: six completed tasks and two truthful unresolved reports, with no rule violations or infrastructure errors. All eight traces were verified. The configuration is `c58c7dc19ecb1eb63d1c00bacd84fc1dd0628f8cab6f44d73cffb4c52414f4ef`.

**Only five of eight scheduled faults triggered.** Three selections repeated an unreachable status-read failure, changing only the metadata seed. The Explorer had received the earlier recipes, reachability reasons and verified observations. The search therefore needs better adaptation; eight clean outcomes are not broad proof of reliability. No qualifying source failure existed, so no repair, challenge or promotion was attempted. Actor/Explorer requests totaled 54; conservative charges $1.36012, billed dollars unavailable.

## Export, playback and fresh execution

B's incident downloaded successfully as a validated ZIP and exported through the documented CLI. Validation and playback checked nine files and 25 historical trials without model calls. A new runtime 2 reference registration and a new campaign kept fresh outcomes separate from B.

The three fresh worlds returned **two SAFE_UNRESOLVED and one C6 citation violation**. The original C5 target reproduced **zero of three**. The execution is complete, but the original failure did not reproduce; the citation failure remains visible. All three new traces were read back and verified. This tests the shared reporting change and the portable incident workflow, not learned-policy transfer.

Execution `execution-dcf7936ab295477fb7588f38584f8bbe`; campaign `campaign-1c19ec5bb8db4988b8493d3ea19d48df`; 24 model calls; $0.5016 conservative charges. Archive and validation/playback/readback results are under `artifacts/phase2-2026-09-20/incident-b-*`.

## Acceptance limits

No generated policy has been accepted. Accepted-policy restart reuse, protected final audit and unchanged-policy external transfer therefore remain **not exercised live in this phase**. The conditional work item records this unmet prerequisite; it does not turn those outcomes into passes. Original measured gates T065, T088, T097, T100 and T102 stay open. Aria remains deferred, and no selector-comparison success is claimed.

The second allowed follow-up configuration is unused: current evidence does not establish a reproducible failure under runtime 2 that the allowed recovery policy can fix. Another identical learning run would not answer that question. The broader fixed public development study below measured cases missed by autonomous search under the same runtime. It is separate from the untouched final audit.

## C3: broader public development test

The existing six-case suite ran all 36 planned trials: 18 live model trials and 18 handwritten reference trials. Every trial was valid, all 30 scheduled faults triggered, and no infrastructure errors occurred. This is a development comparison, not an accepted-policy final audit.

| Agent | Completed | Correctly rejected | Safe unresolved | Rule violation | Model calls |
|---|---:|---:|---:|---:|---:|
| V3.1 with empty policy | 12 | 3 | 2 | 1 | 98 |
| Handwritten reference | 15 | 3 | 0 | 0 | 0 |

The live model completed all healthy, lost-upgrade-response, delayed-upgrade and stale-read cases, and correctly rejected all three terminal failures. Its remaining problem was the temporary notification failure: after the request failed before acceptance, it repeatedly checked the unknown operation instead of resending the same authorized request. Two reports honestly remained unresolved; one incorrectly called the operation PENDING and failed C5/C6. The reference completed all three notification cases. This identifies a useful recovery target, but only one of three model runs violated a rule, so it is not a qualified 3/3 source failure.

All 18 live traces and the [live evaluation](https://wandb.ai/shreetbohara-quinstreet/Faultlab/r/call/01a0c032-148e-7c3a-9a15-73e9f2dfc09f) verified. The reference evaluation remains explicitly local/offline. Campaign `campaign-c59a93f87b03419d967eb43e076c99b0`; study `baseline-study-498d5e0e42594330a282c45dcf5193cc`; 98 calls/$2.0482 conservative charge.

## Final accounting and preservation

Independent reconciliation matched every role's recorded usage to all seven new campaign ledgers across the main store and three separate study/probe stores. No earlier campaign was charged to Phase 2.

- **149 task trials:** 131 live model trials and 18 handwritten reference trials.
- **131/131 live episode traces verified**; offline trials are not counted as verified live evidence.
- **886 model calls**, including four separate schema capability probes. The probes are not task trials.
- **2,941,527 input / 41,344 output tokens**, zero unknown-usage requests.
- **$18.92256 conservative dispatch bound** and **$1.77595950 known-token price estimate**. Actual billed dollars were unavailable; these are not two different claimed bills.
- **$981.07744 remains under the authorized $1,000 ceiling**, using conservative charges.

The backend restarted with the exact runtime 2 configuration. Campaign records, active baseline pointers and all 868 main-store episodes remained unchanged; startup made no provider calls. This verifies storage persistence, not accepted-policy reuse. Comparison against the pre-phase backup found all 26,670 original records unchanged and none missing. The final consistent database backup passed integrity checking. Local evidence is under `artifacts/phase2-2026-09-20/`; it remains ignored by Git.

## What to work on next

1. Improve fault-search coverage: avoid spending repeated selections on an action that was not reached, and measure meaningful triggered schedules.
2. Test recovery after a notification write fails before acceptance. Preserve honest uncertainty and original operation identities. A completion-focused experiment must declare its objective separately from the current 3/3 invariant-repair gate.
3. Preserve exact evidence references in generated reports. Strict JSON fixed malformed reports, but semantic citation mistakes remain.
4. Once a generated policy genuinely qualifies, run challenge, promotion, unchanged restart reuse, untouched final evaluation and native-agent transfer. These remain the evidence required for the full learned-repair promise.

## Final verification and dashboard

**471 backend tests, 61 frontend tests, the production build and three browser fixtures passed.** No backend behavior changed after runtime 2 was frozen. The later saved-execution UI change passed independent review and the final frontend checks. The optional automated actual-server smoke remains skipped; manual verification used the real backend.

In panel 08, select the imported incident, inspect its bundle, enter the saved execution ID, and choose **Open saved execution**. This makes one read request and starts no trial. The actual three-world run opened with its persisted usage and episode links; selecting the citation failure displayed the original report and C6 verdict. Main-loop counts now say which trials they cover, so separate regression evidence does not look like missing task counts. See the [simple guide](../user-guide.md#inspect-the-saved-phase-2-results-first).

Local backups, complete source snapshots, manifests, reports, original model responses and accounting remain available under `artifacts/phase2-2026-09-20/`. No deployment or new GitHub push was performed during this phase.

# Shared incident evidence verification — October 9, 2026

FaultLab now has one versioned evidence format for intended actions, attempts, actual effects, observations, fault exposure and original reports across two task types. Orders keeps its existing C1–C8 checks. A new persisted synthetic payment fixture checks invoice/amount/currency binding, duplicate effects, required payments and receipt attribution.

Use [the guide](incident-evidence.md) and [the architecture decision](ADR_INCIDENT_EVIDENCE_2026-10-09.md). This milestone adds explicit CLI run, inspect, export and replay commands plus static reports; it does not introduce a new dashboard campaign type or a LangGraph adapter.

## Verified behavior

| Case | Actual effects | Result |
| --- | --- | --- |
| Payment, reply lost after commit, retry under a new key | 2 for 1 intended invoice | VIOLATION: duplicate |
| Same scenario, look up original payment | 1 | PASS |
| Two invoices, first receipt wrongly reused | 1 for 2 intended invoices | VIOLATION: missing payment and false report |
| Same two-invoice scenario, distinct keys | 2 | PASS |
| Changed payload under an already bound key | Original amount retained; conflict returned | PASS |
| Subject stops after commit without reporting | 1 retained | INCOMPLETE |
| Declared reply-loss fault never reached | 0; missing-payment check retained | INCOMPLETE |
| Orders confirmation after rejected upgrade | 1 confirmation, no upgrade | VIOLATION: C3+C5 |
| Native healthy execution crashes during shutdown | 1 upgrade and 1 confirmation; original report WITHHELD | INCOMPLETE |

Both payment corrections were separately selected and replayed into fresh worlds with the source scenario preserved. Inspection did not execute a subject. Cross-scenario replay and missing candidate selection were refused before output creation; a tampered ZIP was refused. The existing legacy bundle inspector still accepted its unchanged data-only bundle.

## Verification

- Full offline backend on the first frozen candidate: **3407 passed, 232 skipped, 2 warnings in 1272.07s (0:21:12)**, including its **228 incident-evidence tests**. After that suite, a small UTF-8 validation repair changed only the common canonicalization function and two test files. All **248 incident-evidence tests** passed on the final candidate. The full backend suite was not repeated after that isolated repair.
- Frontend: **373 tests passed**, production build passed, **19 browser fixtures passed** with one opt-in skip, and **one real-backend browser check passed**.
- Separate-checkout command acceptance: **26/26 expected outcomes**, **15 distinct new synthetic worlds**, with no retries or timeouts.
- Independent standard-library, read-only SQLite checks matched committed effects, event order, exact reports, failed checks, execution identities and replay lineage against exports.
- Manual CUA review of eight first-candidate rendered reports matched status, counts, original reports and failed checks. The expanded native shutdown report remained WITHHELD while its effects stayed visible. Full-page screenshots were reviewed in the conversation; no separate screenshot files were exported. Report-rendering source is unchanged in the final candidate, whose fresh exported content was checked against its databases.

The separate checkout used the already approved Python 3.12.8 environment and unchanged dependencies. This milestone did not perform another dependency installation. Each verification stage records its own frozen source. First-candidate full-suite evidence remains separate from final-candidate focused/CLI evidence. Final document wording was finished afterward and pinned separately.

## Source and preservation

Application runtime: `0beaf5a0f194870417a1796fe13f6c23be33ee772a63fa16a5176ddf401f325e`.

The algorithm, orders service, legacy contracts, scorer, interpreter, capability, dependency lock and earlier rejection fixture identities match the preceding native-agent milestone. No gate or threshold changed. The common schema is under docs, outside the old orders contract hash.

Payment runtime identity has a narrower explicit scope: payment module bytes, Python implementation/version, SQLite version and common JSON schema. It does not fingerprint every common helper or transitive dependency. Imports still reproject closed source records and compare the complete result. Mapper compatibility is exact in this first release; unsupported versions are refused.

The tested source inventory has 844 safe files and a 19-path delta from the preceding 826-file baseline. The final inventory adds one verification document and updates current status/setup, producing an explicit 22-path transfer. Original files are backed up before replacement; HEAD and index preservation are checked before, during and after transfer. Work remains uncommitted and unpushed.

## Findings and limits

Initial failing checks remain saved. Review repaired malformed JSON pointer escapes, interpreted content on an absent report, missing payment-report authority, and an uncaught malformed-DEFLATE exception. A separately reproduced escaped-surrogate input was rejected as INCOMPLETE/2; the final UTF-8 boundary repair now rejects it as INTEGRITY_ERROR/3. Twenty new tests cover both invalid surrogates and preserved multilingual/astral text. A WAL snapshot test first failed because its setup had not materialized sidecars; the corrected setup performed a real writer transaction. A ZIP CRC test was corrected to mutate the CRC itself instead of potentially unused compression padding. These were controlled corrections, not repeated experiments seeking a pass.

Dense raw JSON tables remain cumbersome on narrow screens. The current output is a developer evidence report, not a polished mobile dashboard. Runtime compatibility has the bounded scope described above.

Hashes establish internal consistency, not authenticity against a producer who fabricates all source records. This is a deterministic local payment fixture and synthetic orders evidence. It does not establish payment-provider integration, distributed/concurrent behavior, payment process-death recovery, customer adoption, generated repair, production-model reliability or an ACCEPTED policy. Native user code remains trusted local code, not an OS sandbox. Managed-provider calls and new managed-provider spend were zero; arbitrary native user-code activity is unmetered.

Next work should extend version compatibility and use an independently authored workflow to test integration effort, correction and repeat use. A real workflow's own environment and checks must be reviewed before extending the adapter surface. F5/F6 customer evidence remains open; no workflow owner was contacted.

## Saved evidence

Local verification root: `/Users/shree/FaultLab_Scratch/2026-10-09-shared-evidence/`.

- [Full backend log](/Users/shree/FaultLab_Scratch/2026-10-09-shared-evidence/backend-full.log)
- [Command acceptance](/Users/shree/FaultLab_Scratch/2026-10-09-shared-evidence/acceptance-v2/verification.json)
- [Independent SQLite audit](/Users/shree/FaultLab_Scratch/2026-10-09-shared-evidence/acceptance-v2/independent-world-audit.json)
- [Manual report review](/Users/shree/FaultLab_Scratch/2026-10-09-shared-evidence/manual-report-review.json)
- [Frontend checks](/Users/shree/FaultLab_Scratch/2026-10-09-shared-evidence/frontend-verification.json)
- [Browser/backend check](/Users/shree/FaultLab_Scratch/2026-10-09-shared-evidence/browser-health-verification.json)
- [Transfer receipt](/Users/shree/FaultLab_Scratch/2026-10-09-shared-evidence/sync-receipt.json)
- [Final release receipt](/Users/shree/FaultLab_Scratch/2026-10-09-shared-evidence/release-verification.json)


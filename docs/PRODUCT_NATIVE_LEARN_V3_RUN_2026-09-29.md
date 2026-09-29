# History-informed original loop, live, against the native agent: first live candidates, source validation and challenge. Result: STOPPED (6-hour limit during an evidence wait)

- **Run:** 2026-09-29.
  - Step 1 ran 09:59–10:03 UTC.
  - Step 2 started at 10:04 UTC and was stopped at 16:05 UTC by the declared 6-hour limit.
- **Setup:**
  - store `/Users/shree/FaultLab_Runs/2026-09-29/native-learn-v3/`;
  - runtime `08e4c20d…` (commit `b85715c`);
  - native smolagents agent on DeepSeek-V3.1, with the Explorer and Mechanic on V4-Pro-0813.
- **Declarations:** `artifacts/product-live-2026-09-29/native-learn-v3-run/DECLARATION.json` (`36ab50e8…`,
  written before step 1) and `DECLARATION-step2.json` (`b6d4ac28…`, written before Start). Every dollar figure
  was re-read before hashing.

## Step 1: build the agent's history (product baseline study, all six public cases)

- **Study:** `baseline-study-5c460137…`, which COMPLETED.
- **Cost:** 112 calls, $2.3408 conservative, about $0.26 at token prices.
- **B1 controls:** exactly as expected (15 COMPLETED and 3 CORRECTLY_REJECTED).
- **Native B0: 7 of 18 violated.**
  - dev-5 (upgrade rejected) broke C3 in **3 of 3**. That is now **9 of 9 across three days**.
  - dev-2, dev-3, dev-4 and dev-6 each had 1 of 3 with no or false report (C5); dev-1 had 0 of 3.
- **The history froze correctly into the v3 plan:** status AVAILABLE, 18 agent-arm episodes, B1 excluded,
  `summary_hash 8781d32f…`, record cutoff 963.

## Step 2: the discovery v3 (history-informed) Learn campaign `campaign-a2fbffe3…`

**Discovery: 4 selections, and all 4 became reproduced sources (3 of 3 each).**
- **Every source targeted C5:** no truthful final report.
- **The Explorer saw the dev-5 C3 history and chose freely:**
  - its first pick was deliberately "a distinct F2 parameter from prior history" (a successful upgrade delayed
    4 ticks);
  - it never picked the rejected-upgrade recipe, so the repairable C3 failure was again not exposed.

**Diagnosis:**
- One source was dropped at reduction.
- Two were INCONCLUSIVE.
- **One was POLICY_GAP.** The Mechanic proposed CONTRACT_EVIDENCE_GAP, but the declared controlled
  intervention supported a bounded policy hypothesis. **This is the first live POLICY_GAP diagnosis.**

**Candidates. The Mechanic generated two, the first live generated candidates in the original loop:**

| candidate | policy | source validation | challenge | decision |
|---|---|---|---|---|
| `policy-87ee150f…` | wait 1 tick and re-read after uncertain upgrade/notification responses; require SUCCEEDED receipts before the confirmation and the final report | **PASSED:** the baseline failed C5 3 of 3, and the candidate had 0 violations | **COUNTEREXAMPLE_FOUND:** on a novel Explorer schedule the candidate's episodes failed C5, C6 and C7 | **REJECTED** at challenge |
| `policy-0e594f33…` | the same rules with 2-tick waits | **CANDIDATE_FAILED:** 2 candidate episodes violated | — | REJECTED on the evidence; the saved qualification reads INCOMPLETE because the stop landed during its evidence wait |

**This is the first time source validation and challenge have run live.** Both candidates were correctly not
promoted. The active policy stayed `policy-v0`, and nothing was ACCEPTED.

## Why the repairs could not succeed: an agent limitation, not a FaultLab or gate error

The backend log shows the native agent's C5 failures directly:
- it keeps calling business tools after "Final report required";
- it emits invalid single-tool actions;
- its `final_answer` fails the TaskReport validator on the evidence-ID pattern. That is the 32-hex ID copying
  fault the reference Actor lost in Phase 11 with obs-N labels, which the native driver never received.

**No hook policy can write or correct a report.** A policy can wait, read and block, and that fixed the source
schedule in source validation. But on a new schedule the agent still failed to report, so the challenge
correctly found a counterexample.

## Why it stopped: two operational defects (FaultLab), not agent mistakes

1. **Evidence sync never retries by itself.**
   - At 10:22 UTC one challenge episode's Weave ingestion failed with TRANSPORT, and the campaign waited in
     WAITING_EVIDENCE. The product only resumes after a manual telemetry-only retry.
   - I applied the declared retry at 14:09 UTC. It verified all 6 pending episodes at once, and the campaign
     resumed within 30 s.
   - At 14:11 UTC the same thing happened after candidate 2's source validation. Nobody retried, so at 16:05
     UTC the watcher's declared 6-hour limit stopped the campaign.
   - **Fix needed:** a bounded, telemetry-only automatic evidence retry, and a watcher that applies the
     declared retries.
2. **A stop during an evidence wait is recorded as `EXECUTION_ERROR / UnexpectedError`**
   (`learning.py:110` via `:217`), not as an operator stop. **Fix needed:** classify it as
   STOPPED/INTERRUPTED.

**The operator's part:** I noticed the watcher gap at the first stall and did not fix it before leaving the run
unattended. The second stall cost about 2 hours of idle time, though no money.

## Integrity and cost

**Integrity:**
- Clock-drift check: 142 episodes, 0 drifted, 0 masked, 0 missing worlds.
- World integrity VALID 142 of 142.
- All 100 step-2 evidence records verified after the retry.

**Cost:**

| part | calls | conservative charge | token-priced estimate |
|---|---|---|---|
| step 1 | 112 | $2.3408 | about $0.26 |
| step 2 | 747 | $15.9017 | about $2.2 (3,208,238 in, 37,056 out; 4 calls with unknown tokens) |
| **total** | | **$18.26** (both rounded up) | |

## What it shows, and what it does not

**It shows, live, for the first time:**
- **All stages but promotion ran:** discovery → reproduction → reduction → diagnosis (including a POLICY_GAP) →
  Mechanic candidate → source validation (one pass, one fail) → challenge (counterexample found) → correct
  rejection.
- **The gates did their job.** A plausible repair that fixed the source schedule was stopped by the challenge,
  because the agent's own report failures were beyond what any policy can fix.

**It does not show:**
- Promotion or ACCEPTED.
- A repair for C3, which was never exposed.
- Anything held-out.

**The native agent's report-writing failures are the binding limit.** To go further, the native driver itself
needs the reference Actor's report fixes (strict report turn and obs-N citation labels). That would be a
declared change to the agent under test, not to FaultLab's gates.

## Budget

$869.13 + $2.35 + $15.91 = **$887.39 conservatively charged**.

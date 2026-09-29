# Review of the native agent Learn plan (PLAN.md)

Reviewed 2026-09-28, 21:20–21:35 local (2026-09-29 04:20–04:35 UTC). Adversarial review; **nothing in
PLAN.md was changed.** Cost of this review: $0. No provider, model or W&B call. No service started or stopped.
No FaultLab API call. The discovery-v2 store was not opened. `.env`, `backend/app/referee/checks.py`,
`artifacts/heldout2/`, `audit/promotion.json` and final-audit files were not opened. The closed native-probe
store was read with `mode=ro&immutable=1`. Git was used only read-only (`--no-optional-locks`).

**Source reviewed against:** the runtime the plan names, `c0a8aad7` = commit `e7340c9`. I read the changed
files from that commit (`git show e7340c9:<path>`) because **the working tree no longer matches it**
(finding B1). Files unchanged since `e7340c9` (learning, budgets, evaluation, challenge, promotion,
diagnosis, reducer, reproduction, policy interpreter, runner, coordinator, business tools, prompts) were
read from disk after a hash check.

## Verdict in plain words

The plan's arithmetic is right. Its account of what each stage does is right for `c0a8aad7`, and it does
not weaken or bypass any gate. **But it cannot be run as written today**, for four reasons:

1. The code on disk is no longer the runtime the plan freezes. Another agent was editing runtime files
   while the plan was being written, and was still adding tests at 21:26.
2. One stop rule would wrongly stop a healthy run in a common path.
3. One pre-run check can never fail on macOS.
4. The plan leaves out the failure that ended the last paid run: one dropped Explorer connection.

---

## Blockers (must change before paying)

### B1. The runtime on disk is not `c0a8aad7`, and someone is editing it now

- `shasum -a 256 -c prereq/protected_files_after_all_runs.sha256` fails **20 of 176** files, so P1 fails.
  The 20 files:
  - `agents/actor.py`, `agents/explorer.py`, `agents/mechanic.py`
  - `integrations/external_agent.py`, `config.py`
  - `lab/api.py`, `lab/bundle_imports.py`, `lab/discovery_protocol.py`, `lab/exports.py`,
    `lab/provider_failures.py`, `lab/run_plans.py`
  - 9 frontend files
- A new file, `backend/app/agents/transport_retry.py`, does not exist at `e7340c9`.
- `scripts/experiments/check_clock_drift.py` was also edited (21:15). It is not on the hash list.
- Edit times were 21:13–21:17. New tests (`test_native_transport_retry.py`,
  `test_transport_retry_plans.py`, and others) appeared from 21:22 to 21:26, and pytest ran at 21:20 and
  21:26. So P0 ("no other agent is editing") also fails.
- What the edits do, read from the diffs:
  - They add one charged transport retry to the native Actor, the Explorer and the Mechanic.
  - They record the real tick on the native `report_submitted` event.
  - They teach the drift checker the native tick-0 rule.
  - This is the "Next 1" fix in `docs/PRODUCT_DISCOVERY_V2_RUN_2026-09-28.md`.
- The plan itself shows the overlap. Its `external_agent.py` line numbers (117, 153, 155–161) match
  `e7340c9`. But `run_plans.py:364` and `discovery_protocol.py:81` match only the **edited** files. At
  `e7340c9` those lines are 339 and 70. The plan read the source partly before and partly after the edits.
- **Why it matters even if nobody forgets P1:** `AgentRegistry.verify` runs on every episode and re-hashes
  `external_agent.py`, `registry.py` and the runtime identity from disk. An edit during the run therefore
  ends the campaign as ERROR and throws away work in progress.
- **Needed:** the owner picks one:
  - **(a)** Wait until the retry work is finished, reviewed and given a new runtime identity. Then
    re-derive the plan (B2).
  - **(b)** Restore the `c0a8aad7` bytes and prove it with P1.

  In both cases, no agent may edit while it runs. Option (a) removes the risk in B4, but B2 then applies.

### B2. On the edited runtime, section 5, stop rule 4 and section 10 become wrong

These figures assume the edits stay as they are at 21:17:

| Item | Plan (`c0a8aad7`) | Edited runtime |
|---|---|---|
| Model calls per native episode | at most 8 | **at most 16** (each of the 8 turns can be re-sent once) |
| V4-Pro requests | at most 64 | **at most 128** |
| Discovery | at most 72 requests / $1.74 | **at most 144 / $3.47** |
| Ceiling (the ledger still binds at 4,936 requests) | $105.02 | **128 × 0.04984 + 4,808 × 0.0209 = $106.87** |

- Stop rule 4 would then fire on legitimate retries: "more than 8 model calls", "V4 above 64", and
  "used above 72 in discovery".
- Section 10's tick-0 rule would apply only to old episodes.
- The G4, G5 and G7 gaps and the P10/P13 expected values need checking again.
- The declaration's `max_v4_requests`, `conservative_ceiling` and `discovery_*` fields would change.

### B3. The monitor's "past discovery" test can stop a healthy run, and one guard cannot be computed

1. **The flag depends on seeing the right state.** The flag is set only if a once-a-minute poll happens to
   see REPRODUCING or a later state.
   - A reproduction that fails is short. It is about 30–45 s when all 3 runs complete, and about 10–15 s
     when the first run is a LAB_ERROR (`reproduction.py:30` stops there).
   - Then the loop goes straight back to SELECTING and RUNNING. A one-minute poll often misses it.
   - Discovery then continues, and the discovery-only guard fires on a normal run. Example: a source at slot
     2 is dropped in reproduction. That is about 48 requests used, then 5 more slots take about 40 more.
     The run passes 72 requests and $1.74, and the operator presses Stop.
   - This is path B (about 25% in the plan), and the rest of the slots are lost.
2. **The matrix has no purpose field.** A matrix cell has: `episode_id, scenario_alias, arm, policy_hash,
   outcome, lifecycle, fault_scheduled, fault_triggered, fault_count, triggered_fault_count, source_mode,
   telemetry_provenance, usage` (`api.py` at `e7340c9`, the matrix route).
   - Section 9's monitor reads `purpose` from the cells. That field does not exist, so "more than 8
     discovery episodes" cannot be computed as written.
   - Counting all cells would trip on the first reproduction episode.
- **Fix:**
  - Set "past discovery" when `GET /api/campaigns/{id}/experiments` lists any counterexample. That record
    is written when reproduction starts, and it stays.
  - Or read `experiment_purpose` from `GET /api/episodes/{id}` for each new cell.
  - "More than 8 selection records" from `/search-attempts` can stay, and can apply at all times: that
    route already leaves out challenge selections.

### B4. The P0 process check can never fail on macOS

- `pgrep -fl "uvicorn\|vite\|pytest\|app.local"` treats `\|` as a literal character on this Mac.
- Tested here: the escaped pattern found **0** processes, while `"Claude Helper|zsh"` found 45.
- So P0 passes even while pytest or another agent's server is running, which is exactly today's situation.
- **Fix:** `pgrep -fl 'uvicorn|vite|pytest|app\.local'`.

### B5. The plan leaves out the ERROR path that just happened

- Discovery-v2 ended **ERROR** after its Explorer request failed with `APIConnectionError`. This is recorded
  in `docs/PRODUCT_DISCOVERY_V2_RUN_2026-09-28.md` and `ledger.json`, carried total $860.14, updated
  04:03 UTC. That was 1 failure in about 6 V4 requests.
- At `c0a8aad7`, every Explorer and Mechanic request in this plan has the same single point of failure.
  - Path C has about 12–20 V4 requests. Path E has more.
  - A native 503 in reproduction, reduction or diagnosis also drops a source silently (G4).
- The path table has no ERROR row. Its shares add up to 85–100%. "Most likely result: NO_CHANGE" does not
  weigh ERROR.
- The owner's approval (blocker 2) should see this risk, and B1's choice depends on it.
- **Needed:**
  - Add an ERROR path, with a stated share and cost.
  - Add a sentence saying the Explorer/Mechanic retry is being built now.

---

## Other findings (should fix; not required to protect money)

**M1. Treat ACCEPTED as conditional on the post-run integrity checks.**
- Section 12 lists what ACCEPTED would show. It does not say that the section 10 checker and
  `private_world_integrity` must be clean for every episode the gates used: source validation, challenge
  and promotion.
- Phase 18 shows a lab clock defect can undo a certified result.
- Add: "Real drift, a masked F1 or an INVALID integrity record in any gate episode withdraws the ACCEPTED
  claim in the read-out. The store's decision is left as recorded."
- Related: the runner writes `WORLD_EXECUTION_MISMATCH` only when no provider error was already recorded
  (`runner.py:229`). So after the run, count INVALID integrity records whatever the reason says.

**M2. The "about 13 failures in a row" chain is only the minimum.**
- Every later candidate re-runs the unchanged baseline 3 times. If it misses, that candidate becomes
  SOURCE_FLAKY → INCOMPLETE, and the candidate slot is still used (`learning.py:15–30, 204–208`).
- A kept reduction step adds 3 more runs.
- A source that uses all 4 candidates needs up to 13 + 3 + 9 = **25** baseline failures.
- Small point: once a source has been found, the rule-of-succession guide for the next 12 is 8/20 = 40%,
  not 7/19.

**M3. Challenge ends INCOMPLETE in more ways than the plan says.**
- The plan says "fewer than 4 usable schedules". In the code, **one** incomplete or untriggered pair ends
  the challenge at once as INCOMPLETE (`challenge.py:89`).
- Four schedules also need at least one new one (`challenge.py:90–92`).
- The Explorer is known to pick faults that never fire, and a candidate policy can keep the agent from
  reaching a fault. So paths C–E should read "REJECTED **or INCOMPLETE** in challenge".
- Section 12's INCOMPLETE list should name these cases.

**M4. Sources lost to infrastructure are not only lost at reproduction or reduction.**
- A LAB_ERROR or an unfired fault in the diagnosis runs also drops the source (INCONCLUSIVE,
  `diagnostics.py:62–71`).
- An unfired fault in a reproduction run makes it "not reproduced" (`reproduction.py:5,8`), which is not
  the same as flaky.
- Section 13 should report these as "lost to infrastructure" or "fault did not fire", not as agent results.
- Section 12's "NO_CHANGE is the product's correct answer … not a failure of the run" says too much for a
  source lost to one 503. The refusal to claim is correct, but the loss is a FaultLab gap (G4).

**M5. The WAITING_EVIDENCE stop rule can throw away paid work over a free delay.**
- Rule 8 allows 3 retries at least 30 s apart, which is about 3–5 minutes, then Stop.
- While the campaign waits for evidence it makes **no** model calls, and the 6-hour rule already caps the
  total time.
- A Stop in the middle of a candidate turns paid work into INCOMPLETE.
- Suggest: retry every 5–10 minutes for up to about an hour, and pass the pending `episode_ids`. With no
  IDs, `retry_evidence` re-checks every episode in the campaign.

**M6. The drift rule's scope is both too narrow and too wide.**
- Too narrow: `find backend frontend -newer …` misses `audit/`, where `load_cases` re-reads the development
  manifest (discovery fallback) and the promotion manifest every time they are used. It also misses
  `scripts/`, and the read-out's own checker was edited today.
- Too wide: it can fire on `backend/.pytest_cache` (written at 21:20 and 21:26 today) or on a `.DS_Store`.
- Suggest watching `backend/app frontend/src audit scripts` and leaving out cache files.

**M7. The path shares are judgment and do not match the plan's own guide numbers.**
- Path C at about 30% needs a delayed-upgrade pick, then 9 more failures in a row, then a supported
  diagnosis. By the plan's own guides that is at most about 0.44 × 0.70 ≈ 30%, even if the pick is
  certain.
- The "1 in 9" rate with no relevant fault pools dev-2 (F1) and dev-4 (F3). Healthy dev-1 alone is 1 in 6,
  which gives (5/6)³ ≈ 58% for the diagnosis step.
- Moving share to path B lowers the expected cost, so the "about $8" figure stays a fair upper-middle
  estimate.

## Minor points

- **Stop rule 3.** `PROVIDER_ERROR` also covers provider exceptions that fit no other code, not only
  "different frozen model" (`providers/runtime.py:180–183`). Stopping on the first one is still a sensible
  rule, but the stated meaning is incomplete.
- **Stop rule 2.** It fires before the evaluator's own one-time pair retry (`evaluation.py:77–103`). That is
  acceptable during an outage, but say so.
- **Stop rule 4, V4 formula.** The dollar total is a running float, so compare against 64.5, not 64.
- **Read-out accounting.** "`unknown_token_calls` must be 0" and "used = episodes + Explorer + Mechanic
  records" both fail legitimately when a request failed without returning usage (discovery-v2 had one).
  State the exception.
- **P2 paths.** They are relative to `backend/`.
- **Section 3.3, "at best the healthy rate".** This is a guess. A policy also changes how many of the 8
  turns remain for report attempts, and that can go either way.
- **Section 12, promotion gain.** "Strict gain" can mean only fewer HTTP attempts with equal outcomes
  (`promotion.py:24`). The read-out should name which gain it was.
- **No rule for a stalled run.** Apart from the 6-hour limit, nothing covers a run that stops moving. For
  example: 30 minutes with no change in state or `used_calls`, outside WAITING_EVIDENCE.
- **Stale facts.**
  - Discovery-v2 is not "running now". It ended at 04:02 UTC, and from this shell nothing listened on
    8000/8001 at 21:22.
  - The ledger before this run is **$860.14**, not $859.10 plus an unknown amount.

## Checked and correct (at `c0a8aad7`)

- **Prices per request:** V3.1 is 32,000 × 0.55/M + 2,000 × 1.65/M = **$0.0209**. V4-Pro-0813 is
  **$0.04984**.
- **Stage caps:**

  | Stage | Requests | Conservative |
  |---|---:|---:|
  | Discovery | 72 | $1.736 |
  | Reproduction | 24 | $0.502 |
  | Reduction | 600 | $12.54 |
  | Diagnosis | 50 | $1.103 |
  | Per source | 674 | $14.14 |
  | Candidate (`CANDIDATE_CALLS` = 528 Actor + 2 Mechanic + 8 Explorer) | 538 | $11.53 |
  | Candidate with every pair retried once | 1,066 | $22.57 |
  | Sum of all caps | 9,728 | |

- **Ledger:**
  - The protected reserve of 1,064 is never used by Learn, so at most **4,936** requests can be charged.
  - V4-Pro is at most **64**: 8 in discovery, 2 × 8 in diagnosis, and 10 × 4 for candidates.
  - Ceiling: 64 × 0.04984 + 4,872 × 0.0209 = $105.0146, rounded up to **$105.02**.
  - The dollar rule never binds first: $158.05 with the reserve included; $146.97 with requests alone.
- **Expected cost.** The table's midpoints, scaled to their 92.5% total, give **$8.2 conservative** and
  **$1.10 token-priced**. That matches the plan.
- **Probabilities:** (8/9)³³ = 2.1%, (19/20)³³ = 18%, (5/6)³³ = 0.24%. The 95% upper bound after 0 failures
  in 33 runs is 8.7%. 7/19 = 37%.
- **Stage behaviour:**
  - Discovery: fallback case = slot mod 6, and dev-1 has no fault, so dev-2 replaces it. A duplicate uses up
    its slot. A source needs COMPLETED + every fault fired + VIOLATION.
  - Target = lowest failed check.
  - Reduction: FLAKY or INCOMPLETE drops the source. At most 24 proposals.
  - POLICY_GAP needs a 3/3 control and a 0/3 treatment.
  - The 4 candidates are for the whole campaign. A Mechanic "no change" uses one and goes back to discovery.
  - Source validation needs a 3/3 baseline and a candidate with no failed check at all.
  - Promotion predicate as stated.
  - Terminal states: `coordinator.py:12`. A budget refusal ends NO_CHANGE.
- **Native adapter at `e7340c9`:** no transport retry; the meter is checked before sending; max_steps is 8;
  `report_submitted` is recorded without a tick; blocked sends and closed business calls work as described.
- **Hooks:** `require_receipt` treats a FAILED receipt as missing, and it blocks before any HTTP call.
- **Probe store (read-only):**
  - dev-3 took 6 business calls, then 2 refused reports, 8 calls in all.
  - The dev-1 failure had its confirmation at call 3, then 2 status checks and 3 refused reports.
  - dev-5 read PENDING, PENDING, then FAILED at tick 4, and sent the confirmation at tick 5 (all 3 runs).
  - 13 native episodes filed a report, all at tick 0.
  - Integrity was VALID in all 18 native episodes.
  - Policy reads emit `tool_dispatched`, so the attempt-count part of the section 10 rule holds.
- **No gate is weakened or bypassed.**
  - The plan uses the product's own planned-campaign path and changes no threshold, scorer, source or cap
    semantics.
  - Stopping during a candidate can only give INCOMPLETE.
  - `retry-evidence` only re-reads Weave for eligible development episodes (`coordinator.py:553–590`).
  - Section 10 is a read-out rule, not a gate.

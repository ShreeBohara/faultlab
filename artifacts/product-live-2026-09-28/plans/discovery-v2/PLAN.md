# Discovery v2 run plan: one small live Learn campaign

Written September 28, 2026. It cost $0 to write: no provider, model or W&B call. No service
was started. No store, source file or doc was changed. The only files written are this plan and
`compute_primary.py`, which sit next to it.

**Status: DECLARED, NOT RUNNABLE YET.** See *Blockers* (section 12). Nothing in this plan may be
started until those are cleared.

---

## 1. What this run is

We run **one** normal Learn campaign through the product. It has one change from campaign
`c701e850`: it declares discovery protocol **v2** (`faultlab-discovery/v2-reachability`).

In v2, before FaultLab pays for an Actor episode, a free local replay checks every fault in the
Explorer's pick. The pick runs only if every fault is **FORCED**, meaning it will fire on this
Actor's normal path. A refused pick gets one re-plan request in the same slot, with the reasons.

The question is simple. **Of the 8 discovery slots, how many produce a paid Actor episode in
which every scheduled fault actually fired?** Campaign c701e850 (discovery v1) got **4 of 8**.

This run measures how efficient discovery is. **It cannot show that ACCEPTED is reachable.**
With this Actor, the expected end state is NO_CHANGE.

## 2. Frozen choices

Everything matches c701e850 except the discovery protocol, the runtime and the data folder.

| Setting | Value | Same as c701e850? |
|---|---|---|
| Entry path | Dashboard reviewed plan: **Run desk → New campaign → Create → review Frozen campaign plan → Start** (same as API `POST /api/planned-campaigns`, then `POST /api/campaigns/{id}/start`) | c701e850 used the API with operator scripts |
| Mode / profile | `learn` / `live-v1` | yes |
| Agent | FaultLab reference Actor (`orders-prototype-v1` adapter), registered again under the final runtime | yes (new registration) |
| Actor model | `deepseek-ai/DeepSeek-V3.1` | yes |
| Explorer / Mechanic | `deepseek-ai/DeepSeek-V4-Pro-0813` | yes |
| Actor context | `faultlab-actor-context/v4-indexed-evidence` | yes |
| Task text | default: "Upgrade the authorized order to express shipping, then record one truthful confirmation." | yes |
| Order label | `order-product-loop` (reused on purpose so the Actor's task input matches c701e850) | yes |
| Initial policy | `policy-v0` (v2 refuses any policy that has rules) | yes |
| Campaign caps | 6,000 requests; 204,000,000 tokens; $200; 8 discovery selections; 4 candidates; 32,000 input / 2,000 output tokens per request | yes |
| Episode caps | 8 Actor turns, 18 HTTP attempts, 4 waits, 20 ticks, 32 policy steps, 90 s | yes |
| **Discovery protocol** | **v2**: 8 slots, at most 16 Explorer requests, at most 8 Actor episodes, one re-plan per refused slot, order-aware schedule identity (`faultlab-schedule-identity/v2-order-aware`) | **no (c701e850 was v1)** |
| Pre-check | labeller `faultlab-reachability/v2`; caller `reference-actor/policy-v0/v2` (never re-sends a failed write; at most 3 status checks after UNKNOWN) | new |
| W&B project | `shreetbohara-quinstreet/Faultlab` | yes |
| Aria | off (the launcher forces `FAULTLAB_ARIA_PUBLISH_ENABLED=false`) | yes |
| Data folder | `/Users/shree/FaultLab_Runs/2026-09-28/discovery-v2/` (new and empty, outside Desktop; the folder does not exist yet, and 28 GiB was free on September 28) | new folder |
| Runtime | whatever the review-fix workflow finally produces (currently `c9b1b7e6…`, still changing) | differs from c701e850 (`60f27623…`) |

**Prices** (W&B public pages, checked September 27, 2026; see
`artifacts/product-loop-2026-09-27/provider-readiness.json`):

* V3.1: $0.55 input / $1.65 output per million tokens.
* V4-Pro-0813: $1.31 / $3.96 per million.
* No cache discount is assumed.

**Per-request admission bounds** (the most one request can be charged):

* Actor: 32,000 × 0.55/1M + 2,000 × 1.65/1M = **$0.02090**
* Explorer and Mechanic: 32,000 × 1.31/1M + 2,000 × 3.96/1M = **$0.04984**

## 3. What we measure

### Primary

**Fully-fired discovery slots, out of 8.**

A slot counts as fully fired when all three of these hold:

* it ran one discovery Actor episode;
* that episode's lifecycle is COMPLETED;
* every scheduled fault in the episode's verdict shows `triggered = true`.

A slot does **not** count if any of these is true:

* it ended with no episode (refused twice, a duplicate, or never reached);
* its episode is LAB_ERROR or INTERRUPTED;
* its episode had no scheduled fault;
* its faults fired only partly, or not at all.

**Baseline.** c701e850 scores 4 of 8. `compute_primary.py` was run on its saved JSON and got
exactly that:

* fully fired: slots 0 (F2 upgrade delay), 1 (F3 stale read), 3 (F1 confirmation) and 4 (F4 order read);
* none fired: slots 2 and 5 (orders status-check F4);
* duplicate: slot 6;
* partly fired: slot 7.

The offline v2 replay of those 8 picks (DISCOVERY_V2 doc) says the pre-check would have refused
exactly slots 2, 5 and 7.

### Secondary (all reported, none used to decide anything)

1. **Refused picks**, counted by type:
   * `SKIPPED_UNREACHABLE`, with reason codes: NOT_FORCED codes N0–N5 and IMPOSSIBLE rules S1–S4;
   * `SKIPPED_DUPLICATE`;
   * `PRECHECK_FAILED`;
   * picks that came from the fixed fallback after invalid Explorer output.
2. **Re-plans:** the number of second requests in a slot, and how many of them ran.
3. **Slots without an episode**, and the Explorer requests used (at most 16).
4. **Pre-check accuracy:** FORCED faults that fired, out of FORCED faults in picks that ran. Every
   miss needs its template reason: the agent skipped the call, or the episode ended early.
   * A FORCED fault whose target attempt happened but did not fire (`REACHED_BUT_NOT_TRIGGERED`)
     is a **FaultLab bug**, not an Actor mistake.
5. **Outcomes:** COMPLETED / SAFE_UNRESOLVED / CORRECTLY_REJECTED / VIOLATION / LAB_ERROR.
6. **Diversity of fully-fired picks** (distinct kind/tool/service, and multi-fault or deeper-attempt
   picks). A higher fire rate from only trivial first-attempt faults is not the same as better search.
7. **Cost:** requests by role, conservative charge, and token-priced estimate.
8. **Later stages:** whether any source, reproduction, reduction, diagnosis or candidate ran.

## 4. How to start it (product paths first)

**Where the product has no path, it is said plainly.**

| Step | Product path | Product has no path; use |
|---|---|---|
| Start services | `./scripts/start-local.sh --live --data-dir …` | — |
| Supply non-secret live settings | process environment (the documented method; `.env` keeps the key) | no reviewed "settings profile" loader exists |
| Readiness | Dashboard **Run readiness**, or `GET /api/readiness` (no model call) | — |
| Register the Actor | Dashboard **Register configured agent** | — |
| Create the v2 plan | Dashboard Learn + **Discovery protocol → v2 · reachability pre-check**; or raw `POST /api/planned-campaigns` with `discovery_protocol` | **The CLI cannot do this.** `scripts/run-demo.sh --mode learn` uses the old unplanned `POST /api/campaigns`, which is always v1 |
| Review the frozen plan | Dashboard **Frozen campaign plan**; `GET /api/campaigns/{id}/plan` | — |
| Start | Dashboard **Start campaign** (once) | — |
| Monitor / stop | CLI `python -m app.cli.client status|stop --campaign ID` (from `backend/`); `GET /api/campaigns/{id}`, `/budget`; dashboard **Stop** | — |
| Evidence retry | Dashboard **Retry evidence sync**; `POST /api/campaigns/{id}/retry-evidence` | — |
| Export | `./scripts/export-evidence.sh`; dashboard **Download campaign recording** | the recording drops each selection's slot number, so also save `GET /api/campaigns/{id}/search-attempts` |
| Caller gate before the run | none | `scripts/experiments/check_reachability_caller.py` (research script, $0) |
| Clock-drift check after the run | none | `scripts/experiments/check_clock_drift.py` (research script, $0) |
| Per-slot primary | none: the dashboard shows selections and a trial matrix, but never joins them per slot | `compute_primary.py` in this folder (pre-declared; reads JSON only) |

### Steps

**1. Set the non-secret settings and start the services.** In one terminal, from
`/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab`, set these, then start. The credential
stays in `.env`; never type it.

```sh
export WANDB_ENTITY=shreetbohara-quinstreet WANDB_PROJECT=Faultlab
export WANDB_MODEL=deepseek-ai/DeepSeek-V3.1
export WANDB_EXPLORER_MODEL=deepseek-ai/DeepSeek-V4-Pro-0813 WANDB_MECHANIC_MODEL=deepseek-ai/DeepSeek-V4-Pro-0813
export FAULTLAB_CONFIRMED_ENTITY=shreetbohara-quinstreet
export FAULTLAB_ACTOR_CONTEXT_PROTOCOL=faultlab-actor-context/v4-indexed-evidence
export FAULTLAB_MODEL_CALL_CAP=6000 FAULTLAB_TOKEN_CAP=204000000 FAULTLAB_DOLLAR_CAP=200
export FAULTLAB_INPUT_DOLLARS_PER_MILLION=0.55 FAULTLAB_OUTPUT_DOLLARS_PER_MILLION=1.65
export FAULTLAB_PRICING_MODEL=deepseek-ai/DeepSeek-V3.1 FAULTLAB_PRICING_VERIFIED=true
export FAULTLAB_LAB_MODEL=
export FAULTLAB_REASONING_INPUT_DOLLARS_PER_MILLION=1.31 FAULTLAB_REASONING_OUTPUT_DOLLARS_PER_MILLION=3.96
export FAULTLAB_REASONING_PRICING_MODEL=deepseek-ai/DeepSeek-V4-Pro-0813 FAULTLAB_REASONING_PRICING_VERIFIED=true
./scripts/start-local.sh --live --data-dir /Users/shree/FaultLab_Runs/2026-09-28/discovery-v2
```

**2. Check readiness.** Open `http://127.0.0.1:5173`. **Run readiness** must show:

* the simulator is ready;
* live configuration is ready, with no missing names;
* provider calls: 0.

**Current setup for new live campaigns** must show V3.1, V4-Pro-0813 twice, and v4 indexed evidence.

**3. Register the Actor.** **Execution profile → Live reviewed agent**, then **Reviewed agent →
FaultLab reference Actor**, then **Register configured agent**. This makes no provider call.

**4. Fill in the form.**

* **Campaign mode:** Learn · original learning workflow.
* **Discovery protocol:** v2 · reachability pre-check.
* **Task:** keep the default text.
* **Authorized order:** `order-product-loop`.

The plan preview must read "8 slots · at most 16 Explorer requests · at most 8 Actor episodes ·
one re-plan per refused slot". It must also show the limits 6000 · 204,000,000 · $200.00.

**5. Create the campaign, then check the Frozen campaign plan** field by field against section 2:

* discovery block, schedule identity v2, caller `reference-actor/policy-v0/v2`;
* initial policy `policy-v0`;
* caps and episode limits.

Save `GET /api/campaigns/{id}/plan` and `GET /api/campaigns/{id}/configuration`. The
configuration carries `runtime_hash` and `algorithm_hash`. Write the declaration record (section 6)
**before** pressing Start.

**6. Press Start campaign once. Then close the dashboard browser tab.** The Phase 18 clock drift
was traced to lab-loop freezes, with dashboard polling the inferred cause. The search panel polls
every 6 s. Monitor with the CLI or `curl` no more than once a minute.

## 5. Requests and dollars

### 5a. Discovery (always runs)

| Part | Most requests | Conservative bound |
|---|---|---|
| Explorer: 8 slots × at most 2 (the pick plus one re-plan). No hidden retries (`max_retries=0`); the v2 budget is checked **before** the charge | 16 | $0.797 |
| Actor: at most 8 episodes × 8 turns × at most 2 (one charged blind retry per turn after HTTP 503 or a transport failure with no answer; `actor.py`, `EpisodeMeter.transport_retry`) | 128 | $2.675 |
| **Discovery total** | **144** | **$3.47** |

### 5b. Later stages

These run only if a discovery episode is a VIOLATION with every fault fired. The caps below come
from the source.

| Stage | Cap in source | Most requests (every retry used) | Conservative |
|---|---|---|---|
| Reproduction (`reproduction.py`) | 3 fresh episodes; continues only on 3/3 of the same rule | 48 | $1.00 |
| Reduction (`referee/reducer.py`, `max_proposals=24`) | re-runs the original 3 times, then at most 24 smaller recipes × 3 = 75 episodes | 1,200 | $25.08 |
| Diagnosis (`diagnosis.py`) | Mechanic ≤ 2 (one format repair); 1 intervention × 3 pairs = 6 episodes | 98 | $2.11 |
| **Per source** | | **1,346** | **$28.19** |
| One candidate (`learning.py`, `evaluation.py`, `challenge.py`, `promotion.py`) | Mechanic ≤ 2; source validation 3 pairs; challenge ≤ 8 Explorer picks + ≤ 4 schedules × 3 pairs; promotion 18 pairs (`paired_complete(promotion,18)`); every pair may get one lab-error retry | **2,122** | **$44.64** |

The loop can meet up to 8 sources (one per slot), but only 4 candidates across the whole
campaign. The sum of every cap is 144 + 8 × 1,346 + 4 × 2,122 = **19,400 requests**. That is far
more than the ledger allows, so the ledger is what actually binds.

### 5c. True maximum (enforced by the ledger)

A live campaign holds **1,064 requests** in protected reserve that a Learn campaign never uses:

* final audit: 384
* portability: 288
* selection comparison: 392

(`budgets.PROTECTED`; the c701e850 budget record shows all three still held at the end.)

So the most this campaign can spend is:

* **6,000 − 1,064 = 4,936 requests** in total.
* **At most 72** of those can be V4-Pro requests: 16 discovery + 8 × 2 diagnosis + 4 × 10 per candidate.
* Conservative ceiling: 72 × $0.04984 + 4,864 × $0.02090 = **$105.25**.

The dollar rule on its own would stop at $200 − 1,064 × $0.04984 = $146.97. The request limit is
reached first.

**This run's declared allocation is therefore 4,936 requests / $105.25 conservative.** Both are
enforced by the product before every charge.

Correction to the current docs. CURRENT_STATUS and the DISCOVERY_V2 note say "about $56
campaign worst case (the plan's phase table), about $107 with every transport retry". Neither is a
maximum:

* One source with the full 24-proposal reduction and 4 candidates, **without any retries**, is
  already 2,970 requests / $63.75.
* Retries, lab-error pair retries and further sources push past the ledger ceiling.
* `EXPLORER_PLAN.md` (the source of that phase table) and the scratch evidence folders the note
  cites (`discovery-v2/`, `fixer-0928/`, `review-disc-v2/`) no longer exist, so the $56 figure
  cannot be re-checked.

### 5d. Expected cost

**Most likely: discovery only, ending NO_CHANGE.**

* Explorer: 10–16 requests. The offline v2 replay of c701e850 used 12.
* Actor: 8 episodes × 4–8 requests. c701e850 averaged 4.4 per episode. FORCED faults such as
  repeated rejections make episodes longer.
* Conservative charge: about **$1.1–$2.1** (point estimate 12 × 0.04984 + 50 × 0.0209 = **$1.64**).
* Token-priced estimate: about **$0.2–$0.6**. For reference, c701e850 spent $0.153 on 39 requests;
  its Explorer inputs averaged about 9,300 tokens and Actor inputs about 2,800.
* The provider's billed cost will not be known.

**If one discovery episode is a violation**, reproduction adds 3 episodes: at most 48 requests /
$1.00 conservative, a few cents token-priced.

**Going further needs 3 of 3 failures of the same rule.** With this Actor that is rare. If it
happens, the loop continues on its own inside the ceiling.

* Rough example: one source, a small reduction, and 4 candidates that fail source validation.
  That is about 350 requests, about $8 conservative and under $1 token-priced.

**Time.** c701e850's discovery took about 1 minute for 7 episodes. With the free pre-check
replays and re-plans, expect roughly 2–10 minutes, plus any wait for Weave evidence verification.

## 6. Pre-run checks (all must pass, in order)

1. **The review-fix workflow is finished, and no other agent is editing faultlab source.**
   * The final source passes the full backend suite and the frontend suite, build and browser fixtures.
   * **Why this matters mid-run:** the backend imports some modules lazily (reproduction, diagnosis,
     challenge…), so an edit during the run could load changed code.
   * Keep the source frozen until the campaign closes and the read-out is saved.
2. **Source checkpoint.** Make a local commit or backup of the exact source, recorded as for earlier
   paid runs. No GitHub push.
3. **Caller gate PASS on the final source:**
   `.venv/bin/python scripts/experiments/check_reachability_caller.py --out <run folder>/caller-gate.json`
   * It must report PASS: every modelled attempt seen in at least 10 stored episodes is reached in
     at least 80% of them.
   * It is $0 and read-only, and opens stores with `immutable=1`.
4. **Prices re-read on run day** from the two W&B public model pages; no API call is needed.
   * If either price changed, update the four price variables. The per-request bounds and every
     figure in section 5 then change and must be recomputed before Create.
   * `FAULTLAB_PRICING_VERIFIED=true` is a human statement that this was done.
5. **Nothing else is running.**
   * Ports 8000/8001/5173 are free. `start-local.sh` refuses busy ports; they were free on September 28.
   * The pending import-validation paid run (up to 72 requests) is **not** running at the same time.
   * There are no open dashboard tabs from other stores.
6. **The data folder is new and empty**, and at least 2 GiB is free.
7. **Readiness** as in step 2 of section 4.
   * `GET /api/config/status` shows `active_campaign_id: null` and `live_enabled: true`.
   * *Optional:* a model-catalog read. It is a W&B call but no generation, and c701e850 did one.
     Only the owner or run operator does this, never this planning task.
8. **The frozen plan matches section 2.**
   * `GET /api/run-options` → `learn.discovery_protocols[1].declaration.pre_check.caller_model.caller_id`
     is `reference-actor/policy-v0/v2`, with `unknown_status_checks: 3` and `resends_failed_writes: false`.
   * The saved plan's discovery block is identical to it. The product re-checks this at Start and
     refuses a changed caller.
9. **Declaration record written before Start**, in a run folder such as
   `artifacts/product-live-2026-09-28/discovery-v2-run/`. It records:
   * campaign ID, registration ID, `configuration_hash`, `plan_hash`, `runtime_hash` / `algorithm_hash`;
   * sha256 of this PLAN.md;
   * sha256 of `compute_primary.py` (`9b5b7ba9df62ebfa65fda8a326fa4760ab7d93fbdd19ece88a4111179febd146`);
   * the bounds in section 5 and the stop rules below.
10. **Right after Start:** `GET /api/campaigns/{id}/budget` shows the three protected reservations
    (1,064 requests) and `dollar_bounds` of 0.0209 / 0.04984 / 0.04984.

## 7. Stop rules

**The product stops itself for any of these:**

* the normal state machine ends (NO_CHANGE, COMPLETED, ERROR);
* the ledger refuses a charge (ends NO_CHANGE with a budget reason);
* the v2 Explorer/episode budget is used up;
* `PRECHECK_FAILED`: it keeps the charged answer, then the campaign ends ERROR;
* an Explorer provider failure: there is no Explorer retry, so the campaign ends ERROR.

**The operator presses Stop** (dashboard or `python -m app.cli.client stop --campaign ID`) on
any of these:

1. Any world-integrity failure (`WORLD_EXECUTION_MISMATCH`).
2. Two LAB_ERROR episodes in a row.
3. An explicit authentication or configuration failure, or "Provider returned a different frozen model".
4. **A discovery accounting anomaly.** Before the state has ever been REPRODUCING, any of these
   means a lab defect:
   * used requests above 144;
   * a conservative charge above $3.48;
   * more than 16 selection records;
   * more than 8 discovery episodes.
5. **Source or configuration drift.** Any edit under `faultlab/backend` or `faultlab/frontend`
   during the run. Also checked afterwards: `GET /api/run-options` must still give the reference
   agent the campaign's `configuration_hash`.
6. Less than 2 GiB free disk.
7. Six hours elapsed.

**WAITING_EVIDENCE.** At most three telemetry-only retries per pending episode. Each one starts
at least 30 s after the previous retry finished. If still unverified, stop.

* Never rerun business effects or model answers to repair telemetry.

**Never:**

* restart automatically;
* run a replacement or second campaign to get a better number;
* reroll a returned answer;
* change source, settings or caps while the run is going.

**If a source appears, let the loop continue.** It is bounded by section 5c. Stopping mid-candidate
only turns paid work into INCOMPLETE.

## 8. After the run (read-out)

1. Keep the services up just long enough to save the product's own outputs:
   * `./scripts/export-evidence.sh --campaign ID --output <run folder>/export.json`
   * `curl -s http://127.0.0.1:8000/api/campaigns/ID/search-attempts > <run folder>/search-attempts.json`
   * the same for `/matrix`, `/budget`, `/plan` and `/configuration`
2. Confirm there was no source drift with `GET /api/run-options`, then stop the services with
   Ctrl+C in the launcher terminal.
3. Check clock drift:
   `.venv/bin/python scripts/experiments/check_clock_drift.py --store /Users/shree/FaultLab_Runs/2026-09-28/discovery-v2/lab.sqlite3 --worlds --require-worlds`
   * It must exit 0.
   * A drifted or masked-fault episode is flagged in the read-out. Its slot is still counted as
     recorded, and the finding is reported next to the primary.
4. Compute the primary:
   `python3 artifacts/product-live-2026-09-28/plans/discovery-v2/compute_primary.py --search-attempts <run folder>/search-attempts.json --export <run folder>/export.json --out <run folder>/primary.json`
   * It must report `valid: true`: selections map one-to-one to discovery episodes by scenario hash.
5. Accounting: add this campaign's conservative charge to the carried **$856.96**. Report the
   token-priced estimate separately. Provider billing is unknown.
6. Write the result note. Do not edit c701e850's or any other closed record.

## 9. What each result would and would not mean

Decided **before** the run. n = 8 slots in one campaign, and the slots are not independent (the
Explorer learns from earlier slots). The comparison with c701e850 is **not concurrent**: the
runtime, Explorer context and model randomness all differ. Phase 9 showed that a before/after
claim can vanish under a concurrent control.

The p-values below are one-sided Fisher exact tests against 4 of 8.

| Fully-fired slots | Reading |
|---|---|
| **8 of 8** | Strongest outcome. If nothing had changed, 8/8 would happen by chance about 4% of the time (p = 0.038). Say "consistent with v2 raising fault exposure in this setup", not "proven". |
| **7 of 8** | Better in this run, but not distinguishable from chance (p = 0.14). |
| **6 of 8** | Same (p = 0.30). |
| **4–5 of 8** | No evidence of improvement. Check whether the Explorer used the re-plan feedback: the offline replay predicts about 4 episodes if it ignores the feedback, and 8 if it uses it. |
| **3 or fewer** | Worse. Investigate refused-twice slots, LAB_ERRORs, and any FORCED fault that was reached but did not fire (a FaultLab labelling bug). |

**Mechanism checks, whatever the number:**

* every FORCED miss needs a template reason (the agent skipped the call, or the episode ended early);
* there are zero `REACHED_BUT_NOT_TRIGGERED`;
* report diversity next to the count.
  * The caller gate's weakest modelled point is reached 83% of the time, so a FORCED pick at a
    deep attempt can still miss about 1 in 6.

**It WOULD show:** how much of the paid discovery budget becomes fully-exercised fault schedules
under v2, for this Actor, Explorer and runtime. It would also show:

* how many picks the pre-check refuses, and why;
* whether one re-plan recovers the slot;
* whether the pre-check's FORCED labels hold in a live run.

**It would NOT show:**

* **That ACCEPTED is reachable.** An accept needs all of these, and none of them is measured here:
  * a 3/3 reproduced violation;
  * a POLICY_GAP diagnosis;
  * a candidate that passes source validation, challenge and promotion.

  Earlier evidence says this Actor rarely gives a repeatable same-rule violation
  (memory: "ACCEPTED unreachable").
* That fully-fired picks find more bugs. Exposure is not bug discovery.
* That the Explorer is smarter in general, or that the result carries over to other models.
* Anything about the native smolagents agent: v2 refuses it at plan time and at run time.
* Anything about repair quality.
* A trade-off v2 makes by design: it never spends discovery on faults that fire only if the agent
  **leaves** its normal path (for example c701e850's status-check faults). Those are no longer
  tested in discovery.
* A NO_CHANGE end state is the expected, correct product result. It is not a failure of the run.

## 10. Review fixes this plan depends on

The review-fix workflow is changing source now. Each item below must be true in the **final**
source. If a fix changes any of them, the figures or the gate must be redone before Create.

1. **Caller v2, the re-send assumption.** The modelled Actor never re-sends a failed write, and
   makes at most 3 status checks after UNKNOWN or failed checks (`UNKNOWN_STATUS_CHECKS = 3`).
   * Labeller: `faultlab-reachability/v2`; caller: `reference-actor/policy-v0/v2`.
   * The gate must PASS on the final source.
   * Caller v1 wrongly labelled re-send-only faults FORCED.
2. **Explorer v2 prompt and facts** say that no fault makes this agent re-send. This changes the
   Explorer's picks, so it directly affects the primary.
3. **Retry arithmetic.** At most one charged blind retry per Actor turn; the Explorer and Mechanic
   have none.
   * If a fix adds an Explorer retry, discovery becomes 32 + 128 = 160 requests, $4.27, and
     section 5 must be recomputed.
   * One such fix is plausible: today one Explorer 503 ends the whole campaign.
4. **v2 budget checked before the charge.** `admit_request` runs before `consume_call`, and there
   is one `admit_episode` per slot.
5. **Order-aware schedule identity v2** is used for discovery duplicates.
6. **The protected reserve (1,064 requests) stays held** in Learn campaigns. If a fix releases it,
   the ceiling rises to 6,000 requests, which is 72 × $0.04984 + 5,928 × $0.0209 = $127.48
   conservative. The request limit would still be reached before the $200 cap.
7. **Hardening in the same chain has not run live yet:**
   * credentials read with `dotenv_values` while `PYTHON_DOTENV_DISABLED=1`;
   * the lazy simulator app (the simulator identity changed `3ce5bcd2…` → `f70c8fb1…`);
   * the Host/Origin guard (use `127.0.0.1` / `localhost` only).

   This will be the first paid run under them. The first episode's Weave verification is the live
   check.
8. **Register and create after the last fix.** Registrations and plans embed the runtime.
   `validate_run_plan` refuses a changed caller, source, model or caps at Start.

## 11. Risks and FaultLab issues noticed (not blockers)

* **One Explorer provider failure ends the campaign as ERROR.** `explorer.py` raises,
  `learning.py` re-raises, and the coordinator marks the campaign ERROR. The remaining slots go
  unmeasured.
  * Pre-declared handling: report "X of 8, campaign ERROR after slot k"; no rerun.
* **Explorer input size.** v2 adds about 600 prompt tokens plus facts, readable ledgers and
  per-fault results. c701e850's largest Explorer input was about 12,500 tokens (v1). The limit is
  32,000.
  * If exceeded, `validate_model_input` refuses **before** any charge, and the campaign ends ERROR.
  * Judged unlikely.
* **No product view for the primary.** The matrix mixes discovery with later stages once a source
  appears. The recording export drops `selection_index`. Hence `compute_primary.py`, which joins
  the product's search-attempts output to the export and checks each pair by scenario hash.
* **The CLI cannot declare v2.** See section 4.
* **Docs overstate how tight the worst case is.** The $56 and $107 figures are not maxima (see 5c).
  The cited scratch evidence is gone; the gate result can be regenerated at $0.
* **A disk-headroom trend to watch.** The volume was 94% used with 28 GiB free on September 28.

## 12. Blockers

1. **Source still changing.** The review-fix workflow (discovery v2 and hardening) is editing
   source now. The final runtime is unknown, so the Actor cannot be registered and the plan cannot
   be created yet. Clear by:
   * finishing the fixes;
   * full backend and frontend suites passing on the final source;
   * no other agent editing during the run.
2. **Caller gate not yet re-run on the final source.** It must PASS after the fixes (section 6,
   item 3).
3. **Source checkpoint.** A local commit or backup of the exact source the run will use. This is
   standard for earlier paid runs.
4. **Price re-read on run day.** Prices were last verified September 27. Either re-read the two
   W&B pages, or explicitly accept the one-day-old check in the declaration.
5. **Ordering with the pending import-validation paid run.** Both need the same ports and one
   active campaign per backend. Choose which runs first; they must not overlap.

## 13. Sources read for this plan

* `CURRENT_STATUS.md`, `AGENTS.md`
* Docs:
  * `docs/DISCOVERY_V2_2026-09-28.md`
  * `docs/PRODUCT_LOOP_RUN_2026-09-27.md`
  * `docs/PRODUCT_LOOP_RESULTS_2026-09-27.md`
  * `docs/setup.md`
  * `docs/user-guide.md`
  * `docs/part2/PHASE1_NATIVE.md`
* Backend source (`backend/app/…`):
  * `lab/`: `discovery_protocol.py`, `reachability.py`, `run_plans.py`, `learning.py`,
    `budgets.py`, `reproduction.py`, `diagnosis.py`, `evaluation.py`, `challenge.py`,
    `promotion.py`, `coordinator.py`, `runner.py`, `api.py`, `configuration.py`
  * `agents/`: `explorer.py`, `actor.py`, `mechanic.py`
  * `referee/`: `reducer.py`, `diagnostics.py` (intervention runner only)
  * other: `config.py`, `local.py`, `cli/client.py`
* Frontend: `RunSetup.tsx`, `DiscoveryProtocol.tsx`, `SearchAttemptsPanel.tsx`
* Scripts: `check_reachability_caller.py`, `check_clock_drift.py` (headers only)
* c701e850 artifacts (JSON, read-only): `live-budget.json`, `live-campaign.json`,
  `live-declaration.json`, `live-search-attempts.json`, `live-export.json`,
  `provider-readiness.json`, `prep/process-settings.json` (non-secret keys only)

Not opened, by rule: `.env`, `backend/app/referee/checks.py`, `artifacts/heldout2/`,
`audit/promotion.json`, final-audit files. The promotion size (18 pairs) comes from
`promotion.py`, not the manifest.

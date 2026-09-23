# Phase 2 experiment declaration

Declared September 20, 2026 before new Phase 2 model generations. Append specific amendments before changing an experiment. Preserve Phase 1 and every new negative or interrupted result.

## Objective

Determine whether FaultLab can generate a useful recovery policy, reject ineffective policies and establish improvement through repeated source tests, active challenge and independent promotion. An accepted policy must then survive unchanged restart reuse and held-out evaluation. Independent-agent transfer is measured separately and is not assumed.

## Starting point

Phase 1 preserved 226 trials and 1,400 calls. Its only unique tested repair failed three of three source comparisons. The later alternate-Mechanic campaign stopped before proposal because full-batch reservation exceeded its $88.32 allocation. Fresh execution of one incident produced two violations and one completion. These observations motivate repeatability measurement and adequate reservation headroom, not changed scoring or repeated qualification of the same failed policy.

Starting runtime: `97c91555efd5319b4f9c2cdf57db4e80f83be1bf0b947f57a5ae91f0c3813322`. Algorithm: `e108cd86efcfd0739f00996f3590327bb2765ee513c515adebc6c0a2200692a3`. A consistent database snapshot and previous campaign inventory are under `artifacts/phase2-2026-09-20/` (local, ignored by Git).

## Controls and sequence

1. Inspect current model documentation, review runtime/reporting behavior and declare exact fixed development cases/repeats before the repeatability study. Healthy controls are required. Use fresh worlds and original reports; retain every slot, including errors and untriggered faults.
2. Use those results and code review to select the smallest justified intervention. A change to the Actor prompt, permitted hooks, request protocol or episode limits creates a new experiment, with both baseline and policy arms on that same new configuration. Never attribute a shared harness change to learned repair.
3. Run offline checks, preserve source/configuration fingerprints, then execute a complete learning campaign. The initial plan retains Actor V3.1, Explorer V4 Pro 0813 and Mechanic V3.1, which did not reach proposal in the last phase. Model selection is a continuity decision, not a claim of superiority. Freeze exact settings and prices before dispatch.
4. Review all attempted discovery, reproduction, reduction, intervention, source qualification, challenge and promotion stages. The existing gates decide acceptance. A blocked or failed candidate is never inserted into the accepted-policy pointer.
5. If a policy is accepted, freeze it before held-out evaluation, restart verification and external-agent measurement. Preserve every result and do not feed held-out failures back into this policy's development.
6. If no policy is accepted, allow at most two separately declared, evidence-motivated follow-up configurations in this phase. No repeated identical campaign or candidate merely to obtain a lucky pass. Infrastructure-interrupted attempts are retained; any replacement needs a written reason and a fresh identity.

## Spending and sponsor access

- New total Phase 2 authorization: $1,000. Phase 1 spending is separately reported, not silently included as new experimental usage.
- Start with small studies. A learning allocation around $300–$400 fits current per-campaign limits and avoids Phase 1's dollar-reservation obstacle. Total admitted charges plus any in-flight bounds may never exceed the remaining Phase 2 allowance.
- Keep at most one paid scheduler active. Before allocating a new campaign, subtract all previous Phase 2 conservative charges, including separate stores and unknown requests. Existing call/token caps remain active.
- Confirmed project remains `shreetbohara-quinstreet/Faultlab`. Provider credentials stay in the existing local `.env`. No model generation occurs during startup, ordinary browsing or default tests.
- Inference and Weave are in scope. Aria automation/publication remains deferred; its absence is reported, not relabeled as verified.
- The provider does not currently return actual billed cost. Report conservative dispatch bounds and known-token price estimates separately. Failed requests without usage are not free.

## Reporting

Report all planned/attempted/valid trials, task outcomes, original reports, fault triggers, unique policy hashes, rejected/duplicate candidates, actual reached stages, remote evidence status, costs and limitations. The completion report must distinguish implemented workflow from a proven learned improvement. Original measured gates remain open until their required evidence exists.

## Experiment A — fixed repeatability

Declared before dispatch: 30 reference-Actor baseline trials, round-robin interleaved over three public development conditions, ten each. Original task text and `order-1`, fresh worlds and original generated identities, unchanged empty `policy-v0`.

- Healthy control with no fault.
- Phase 1 V4-Mechanic incident's retained F2: `orders.update_order`, first occurrence, successful completion delayed five ticks; recipe seed 19.
- Phase 1 follow-up incident's retained F2: same tool/occurrence/status, four-tick delay; recipe seed 20240517. The original twelve-tick discovery is not substituted for this exported four-tick recipe.

Seed is scenario metadata, not a promise of deterministic model generation or fresh identity allocation. The Actor remains V3.1 with the same prompt, eight turns, 90-second episode, JSON protocol and temperature zero. The optimizer's factual contract correction changes runtime identity but is not used by this baseline Actor; record its new hash before dispatch. No hooks, policy capabilities or scorer change.

Reserve the full 240-call study before execution; existing protected batches remain reserved. At verified current rates, study Actor call bound is $5.016; required headroom including max-role study reservation and protected batches is $64.99136. Allocate $100 to this standalone store, within the cumulative ceiling. Stop on infrastructure error and retain unattempted slots; do not replace failures silently. Observe missing reports, final outcomes, HTTP/tick use, fault triggering and Weave readback, not only aggregate pass rates.

W&B model discovery confirmed both exact models on the confirmed account at 17:58 UTC. [Official available-model documentation](https://docs.wandb.ai/inference/models) lists both. [Token pricing](https://wandb.ai/site/pricing/tokens/) was retrieved and saved locally: V3.1 $0.55 input/$1.65 output per million, V4 Pro 0813 $1.31/$3.96. Maximum request bounds remain $0.02090 and $0.04984 at 32K input/2K output. No cache discount is assumed. `model-discovery.json` and `pricing-page.html` preserve the checks; model-list access made no generation.

### Pre-dispatch observability correction

Record each provider-redacted Actor response before parsing, together with the request hash, turn number, request-time report-required flag and delivered evidence IDs. These local supplemental events distinguish malformed answers, final-turn tools and submitted reports. They do not alter model inputs, validate an invalid answer, become a submitted report or claim remote verification. Existing development export includes them; protected trial APIs continue to hide their events. Original reports remain scored without rewriting.

An independent review also identified a possible trace-finalization deadline defect. A focused offline reproduction must establish it before any fix is included in the study runtime. All such changes are common to both policy arms and must preserve the actual business/model deadline and external cancellation behavior. Record the reproduction and final correction below before live dispatch.

The regression test reproduced loss of a timely report while the tracing worker finalized it. The correction marks completion only at the actual timely return, closes business dispatch, and permits bounded telemetry-only cleanup afterward. Actual late/absent returns still fail; external cancellation remains interruption. Reported work time ends at that original return rather than including final trace transport. This measurement-boundary correction applies equally to baseline and learned policies and is recorded in the new runtime identity; it is not learned speedup. A read-only scan of all 779 starting main-store episodes found **zero** submitted-report/final-null mismatches and zero deadline/89.9-second episodes. Therefore this defect is not offered as an explanation for the Phase 1 missing reports.

Reconstructing actual Phase 1 Mechanic requests with the expanded semantics and unchanged evidence yielded a largest proposal input bound of 15,762/32,000 tokens, retaining all 16 evidence episodes and cumulative history. The largest diagnosis was 9,010 tokens; largest recorded output 673/2,000 tokens. These are measured historical sizes, not proof that arbitrary later challenge histories will fit. Input overflow remains explicit and does not silently remove evidence.

Experiment A runtime freeze: 564c520062347881fdd559b712666949dfc1fd5b268f6fbdb6e22411a294a2b6; algorithm 3370429f8d8260cc8d56a0c8d7b988edc4458d8e735c759f62de74a76f1b925b. Full checks: 456 backend / 34 frontend / three browser fixtures / production build passed. Exact source archive and timestamp are in `artifacts/phase2-2026-09-20/frozen-source-1.json`. Actor prompt, schema, model request settings, eight-turn limit, business tools and referee remain unchanged.

## Experiment A outcome and Experiment B — generated repair

Experiment A completed all 30 slots with zero infrastructure errors and all 20 scheduled faults triggered. Healthy: 10 completed/0 violations; delay five: 0 completed/10 violations; delay four: 1 completed/9 violations. All 30 episode traces and the evaluation were verified. Every delay-five violation returned `send_confirmation` on the reserved reporting turn. All nine delay-four violations returned a report with a malformed evidence ID and exhausted the last turn; original raw responses remain local supplemental evidence. No output was repaired. These are two concrete report failure mechanisms, not empty provider responses or the telemetry deadline defect.

Campaign `campaign-25a7aa0ce7dd428aa05254f3e19e076c`; configuration `4ca1447b94c354d1ac0412eb3353fe57b57e0b50c23967c5c261f3ac4b5083c0`. Study `repeatability-d1c356119098491192c290c4dcb14f8c`. 202 model calls, $4.2218 conservative charge, $0.36911545 known-token estimate, zero unknown usage. Raw denominators describe this small development pilot, not production reliability or isolated model randomness.

Before dispatch of Experiment B: retain the same frozen runtime and Actor behavior. Use the corrected neutral Mechanic contract with Actor V3.1 / Explorer V4 Pro 0813 / Mechanic V3.1. Allocate **$400** to one new main-store learning campaign, below the remaining cumulative $995.7782 allowance. Keep 6,000 calls, 204M admission tokens, eight discovery selections, four candidates and all original paired/challenge/promotion gates. At the current max-role rate, even the full 6,000-call bound is below this allocation; money admission should no longer block an otherwise admissible candidate. Protected studies remain reserved.

Run ordinary autonomous discovery; do not inject the study cases or a human-authored policy as if the Explorer/Mechanic generated them. No Actor prompt or final-turn schema change in this experiment. The existing policy can affect the number and timing of observations/turns through its already-authorized bounded actions; whether a generated policy actually helps must be measured. It cannot rewrite malformed evidence IDs or the final answer. If a policy qualifies, proceed to its protected evaluation and unchanged restart/transfer checks. Otherwise inspect the actual failed stages before declaring a different experiment.

Experiment B created before start: `campaign-5a0af912a5244423b61b5f13cff4ec0f`, configuration `7953101f46b4dafc8f4d01915175b776bc10dc7d05689e7bb8741b723c61d5b5`. Exact frozen settings saved in `learning-1-created.json`.

## Experiment B outcome; reporting protocol follow-up

B ended NO_CHANGE after 42 complete trials, 298 requests, one unique rejected candidate and three duplicates. Source control failed 3/3; candidate failed 2/3 with malformed evidence IDs in original final answers (one completed). No challenge/promotion ran. All 42 episode traces verified; original records and outputs archived. $6.40184 conservative charges; no unknown token usage. This establishes a generation-format obstacle that a policy cannot rewrite, rather than a reason to weaken report checks or rerun the same candidate.

Before further dispatch, test the documented W&B `json_schema` response format against the exact existing `ReportAction` schema. Four public synthetic probes: minimal report, pending status-check branch, conflicting tool-only request, and conflicting invalid-ID request. All outputs retained, no retry/fallback; validate original raw JSON unchanged. This is a provider capability check, not an agent benchmark. Probe at most four V3.1 calls, 32K input / 2K output / 20 seconds each; conservative total $0.0836, included in the cumulative phase accounting. Unsupported or ignored schemas block adoption and remain recorded. Official protocol references: https://docs.wandb.ai/inference/response-settings/structured-output and https://docs.wandb.ai/inference/response-settings/json-mode .

If the exact schema works, apply it only on already report-required turns, with identical behavior in baseline and learned arms. Keep all original observation content, IDs, report semantics, budgets and referee checks; do not dynamically enumerate delivered citations, repair answers or insert reports. Include schema in request admission and frozen identity. Repeat the same 30-case baseline measurement on the new runtime before a new ordinary learning campaign. Improvements due to protocol enforcement will be reported as a shared engineering change, not learned policy gain.

Also fix a separately reproduced identity collision before the next runtime freeze: diagnostic intervention IDs currently depend only on the two recipes. Two distinct incidents choosing the same recipes execute six trials and then collide on immutable insertion. Include the owning counterexample ID in the declared intervention identity; keep all original records and experiment logic. Offline reproduction used real storage/diagnostic orchestration with deterministic doubles and zero provider calls. B did not encounter this bug.

Schema probe outcome: all four original outputs passed the exact existing ReportAction schema. Capability campaign `campaign-63d34412f83d43e78c08f567677b1c63`, schema hash `8033400b2631d0ae3bb864453a4f82b9b217aeed29ac245f6212afea2d840c77`. Four calls, 221 input/342 output tokens; $0.0836 conservative charge, $0.00068585 token estimate, zero unknown usage. A conflicting synthetic prompt yielded a well-formed but unsupported success claim with invented IDs, demonstrating why schema validity is **not** semantic correctness. The live referee and exact delivered-evidence checks remain necessary and unchanged. No generation fallback or raw-output rewrite occurred.

## Experiment C — final-report protocol, first follow-up configuration

Frozen before dispatch: runtime `1261f1f30b3212ec9440e6faf14055656ea44c6a47ed0856563167b0892891a8`, algorithm `c5948df5fc0772065bd0783ea0f97b18a7938c2f0fcb6d60ecfc72832faad735`. Exact existing report schema is bound in `actor_response_protocol`, scoped to the reference Actor; native-driver behavior is unchanged. Independent review clear; 471 backend / 53 frontend / three browser fixtures / build passed. Original Actor prompt, business actions, eight-turn limit and referee are unchanged. The fixed-study harness and exact three public cases remain the same.

C1: 30 interleaved fresh baseline trials (ten each healthy/delay-five/delay-four), separate `repeatability-2` store with $100 allocation. Same V3.1 Actor and empty policy; no discarded slots or silent reruns. Examine rule failures as well as report syntax; a well-formed invented ID must still fail. Then C2: one ordinary learning campaign under this same runtime, same V3.1/V4/V3.1 roles and $400 allocation, contingent on readiness and remaining cumulative headroom. Keep all original qualification/challenge/promotion gates. These are a new configuration, not a retry of B's candidate.

C1 completed all 30 planned valid trials, all 20 faults triggered, all 30 traces and its evaluation verified. Healthy: 9 completed/1 safe unresolved; delay five: 10 safe unresolved; delay four: 9 completed/1 C6 citation violation. All 30 original reports were present; the one bad citation was syntactically valid but did not match a delivered ID. The healthy unresolved run repeatedly checked an unstarted notification operation. These failures remain scored and retained. No claim of perfect reliability or learned repair. Campaign `campaign-4238713c443f49a7ba4caa2ee4ca9241`, configuration `a1d11d42aa7ca11f8311f0acc63de68623d033a6c4d5b564124665c8942c4b24`. 206 calls; $4.3054 bound / $0.38246725 token estimate, zero unknown usage. Combined Phase 2 conservative charges before C2: $15.01264, remaining $984.98736.

C2 created before dispatch: `campaign-add97a955f8f4f3a961aa62a14286807`, configuration `c58c7dc19ecb1eb63d1c00bacd84fc1dd0628f8cab6f44d73cffb4c52414f4ef`. Runtime2 unchanged, initial policy-v0, eight discovery selections/four candidates, $400 allocation. Readiness passed with zero provider calls. Exact configuration saved in `learning-2-created.json`.

### Planned incident portability check

After C2's paid scheduler is terminal, execute B's exported incident under the unchanged runtime2 reference registration `orders-v1-c58c7dc19ecb1eb6`. Download and CLI export, digest validation and historical playback already passed without provider calls. The bundle contains 25 saved trials; playback is not fresh execution. Use the CLI import path to create a new baseline campaign/ledger, three fresh worlds, exact retained five-tick delay seed20250716, original order-1/task and policy-v0. Budget ceiling24Actor calls/816K admission tokens/$0.5016, full protected-reservation headroom54.22592 covered by the400allocation. Preserve each result and verify all three traces afterward. This measures whether the old failure still occurs under the shared engineering change; it is not an accepted-policy or learned-gain claim. Do not retry a nonreproducing outcome.

### C2 outcome and bounded broader verification

C2 ended NO_CHANGE: eight discovery episodes, six completed tasks/two truthful unresolved, zero check violations, all eight traces verified. Only five recipes triggered: three F4 status-read selections repeated an unreachable schedule (seed changes do not make a new schedule). The verified supplied history already contained this feedback; this is poor Explorer adaptation, not missing input. No candidate, source qualification, challenge or promotion occurred. 54 calls, $1.36012 conservative charges.

The exported B incident executed three fresh runtime2 worlds: two SAFE_UNRESOLVED and one C6 citation violation; the original C5 violation reproduced0/3. All three traces reached verified readback. Execution `execution-dcf7936ab295477fb7588f38584f8bbe`, campaign `campaign-1c19ec5bb8db4988b8493d3ea19d48df`. 24calls/$0.5016 bound; no repeats.

C3 (declared before dispatch): broaden engineering verification to the existing six-case public development manifest `c580b0a536fe6b000f9a7a5f3e92b842cca809dd5c5b0418605b2b57dd2971c1`, three repetitions of each in each arm. Eighteen live baseline B0 trials and eighteen explicitly handwritten/offline B1 reference trials, alternating order; same frozen runtime2. This adds lost-upgrade-response, terminal rejection and a notification failure that C2 did not cover, plus healthy/delayed/stale cases. It tests task coverage and the known reference behavior; it is not learned repair or the protected final audit. Use a new baseline campaign with the same400allocation. Full144live-call reservation/$3.0096 Actor bound is inside the remaining cumulative ceiling. Retain all36slots, no silent repeat, no injected policy or conversion of reference results into model gains. No further ordinary learning rerun is justified by the available evidence; the final follow-up configuration remains unused.

C3 created before start: `campaign-c59a93f87b03419d967eb43e076c99b0`, same configuration `c58c7dc19ecb1eb63d1c00bacd84fc1dd0628f8cab6f44d73cffb4c52414f4ef`.

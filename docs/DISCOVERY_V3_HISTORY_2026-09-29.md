# Discovery protocol v3 (history-informed): design and build (September 29, 2026)

Offline build, **$0**: no provider, model, W&B or paid call. No historical store, result or protocol was
changed. Nothing here has been run live. The product default is still **discovery v1**, and v1 and v2 send
the same Explorer messages as before (pinned by a test, section 9).

**Updated the same day after two independent $0 reviews** (both READY_WITH_CHANGES). Sections 1 to 10 describe
the design as it is now. Section 11 is the builder's original record and is kept as it was. Section 12 lists
every review finding and what changed. In short:
* single-case baseline runs no longer count;
* the same-agent rule is stricter;
* each history row names the FaultLab builds it ran under;
* picks and sources that re-try a history row are flagged;
* a stale plan gets a plain reason.

## 1. The problem this solves

In the live native learn run (campaign `7ee35abe`, [run note](PRODUCT_NATIVE_LEARN_RUN_2026-09-29.md)) the
Explorer never picked a rejected-upgrade recipe. Yet the same native agent (smolagents on DeepSeek-V3.1) had
sent a false confirmation after a rejected upgrade (a C3 violation, which a hook policy can block) on the
development case `dev-5` in **6 of 6** saved baseline episodes. So the one repairable failure was never
exposed, and the stages after diagnosis never ran.

The Explorer was never shown that history. Discovery v1 shows it only this campaign's own picks. Discovery
v2's pre-check models only the reference Actor, so it refuses the native agent.

**v3 gives the Explorer one extra, read-only piece of context:** a compact summary of the same agent's
earlier verified development outcomes in the same store, frozen when the plan is saved. The Explorer still
chooses freely. Nothing is forced and no source is hand-picked.

The operator cannot curate the history either. Only two product paths feed it:
* the fixed baseline study (all six development cases × 3 trials);
* learn campaigns' own discovery picks.

A single-case baseline run, whose case the operator chooses, never counts (section 4). One thing the operator
does still choose is the store to plan in. So every result must name the store, the history's composition and
the frozen summary hash (section 10).

One fact matters for the next live run. The saved native baseline studies are in other stores
(`FaultLab_Runs/2026-09-28/native-probe`, and Phase 1 before it). The 7ee35abe learn run used a new store
(`FaultLab_Runs/2026-09-29/native-learn`). v3 reads only the campaign's own store. So in that store it would
have said "no prior history". Section 8 describes the product path that creates history in the same store
first.

## 2. Two declared forms; v1 stays the default

| protocol id | dispatch, identity and budget | who may declare it |
|---|---|---|
| `faultlab-discovery/v1` (default) | unchanged | reference and native |
| `faultlab-discovery/v2-reachability` | unchanged | reference only (policy-v0) |
| **`faultlab-discovery/v3-history`** | **exactly v1's**, plus the frozen history | reference and native |
| **`faultlab-discovery/v3-history-reachability`** | **exactly v2's** (pre-check, one re-plan), plus the frozen history | reference only (policy-v0) |

"History plus an optional reachability pre-check" is declared as these two protocol ids, so the protocol
string alone says how picks are dispatched. For the native agent only the form without a pre-check exists,
for the same reason v2 refuses it: the pre-check models the reference Actor, not the native agent.

v3 changes only what the Explorer reads. It uses the same selection slots, request budget and transport-retry
bound as its base protocol. It keeps the same schedule identity (v1-sorted, or v2-order-aware with the
pre-check), duplicate rule, fallback, coverage records and every later stage.

## 3. "Same agent": the exact rule

A stored episode counts as the same agent when all of these match the plan's registered agent (item 5 was
added after the reviews):

1. **adapter entry point** (`orders-prototype-v1` for the reference Actor, `smolagents-toolcalling-v1` for
   the native agent);
2. **model id** (the episode's own model; it must also equal its registration's model);
3. **scorer hash** (registration `oracle_hash`, configuration `scorer_hash` and the episode verdict's
   `scorer_hash` must all agree);
4. **what the agent is sent:**
   * native agent: the **native prompt hash** and the **native source hash** from the registration;
   * reference Actor: the **Actor prompt hash**, plus the Actor **context protocol** and **response
     protocol** from its configuration. These two decide what text the reference Actor is sent and must
     answer in, so they count as part of its prompt. The reference source hash is **not** used. It is the
     whole `backend/app/agents` tree, so it changes with every FaultLab edit, including the Explorer's.
5. **what the agent faces:**
   * the simulator contract hash and service hash;
   * the capability set (tools and hooks);
   * the model request settings (temperature, token limits, response format, timeout);
   * the per-episode limits (`episode_budget`: actor turns, HTTP attempts, ticks, wall time and so on).

It deliberately does **not** use the configuration hash or the registration id. Those embed the campaign
limits and the whole FaultLab runtime hash. It also does not use the FaultLab runtime hash or the adapter
(bridge) code hash, which change with every FaultLab edit. Instead, **each history row lists the runtime and
adapter hashes its episodes ran under** (section 6), so a row that mixes builds says so. A re-registration
after a code change, or different campaign caps, is still the same agent.

Example: the native-probe registration `d72de2e0…` (runtime `c0a8aad7`, native adapter `8a579f99`) and the
native-learn registration `819f4d1f…` (runtime `c9af0a47`, native adapter `61497db3`) have different ids and
configuration hashes. They share:
* prompt `2251542869cf…`, source `2867b3fb…`, model and scorer `19de811c…`;
* contract `6f9d7783…`, service `3ce5bcd2…` and capability set `8e8e04af…`;
* the same model request settings and per-episode limits.

Under this rule they are the same agent (checked read only after the fix, section 12), and their rows show the
two builds.

**Same starting policy as well.** History counts only episodes run under the plan's initial policy (normally
`policy-v0`). An episode run under another policy shows how the agent behaved with other hooks, which is not
the behaviour this campaign starts from.

## 4. Which episodes count (an allow-list)

An episode is **used** only if every one of these holds:

* it is in this store, at or before the frozen record cutoff (section 5);
* `split == "development"` and `experiment_purpose == "discovery"`, and it is not the B1 control arm;
* its provenance is one of two known product paths, recorded per row as its **source label**:
  * **`baseline_study`, a baseline study:** its `study_id` names a `baseline_studies` record of the same
    campaign and configuration, and the episode is one of that study's planned B0 slots. The study's design is
    fixed (all six development cases × 3 trials), so the operator cannot choose which cases it covers;
  * **`learn_discovery`, a learn campaign's own discovery pick:** `study_id == evidence_context_id ==
    campaign_id`, no selector, and the campaign is a `learn` campaign. The Explorer chose the recipe;
* **never a baseline campaign's own single-case run.** Such a run has the same record shape as a learn pick,
  but its development case is the operator's choice. The builder's version accepted it (label
  `baseline_run`). A review showed that three planned dev-5-only baseline runs alone froze a dev-5-only
  history for the Explorer. These runs are now out of scope: neither used nor counted;
* it is the same agent and the same starting policy (section 3);
* `lifecycle == "COMPLETED"` with a verdict whose outcome is not `LAB_ERROR`;
* its evidence record says `weave_verified` for this episode.

Among the same agent's otherwise eligible episodes, these are **excluded and counted**:
* lab errors;
* interrupted episodes;
* episodes not yet finished;
* completed episodes without Weave-verified evidence.

Everything else is **out of scope**: it is neither used nor counted. That covers other agents, other
policies, reproduction and later loop stages, research studies, and selector benchmarks.

**Protected data is never read into the summary.** Promotion, held-out and final-audit episodes carry
`split` `promotion` or `final_audit`. The held-out checks run with purpose `promotion`, and portability runs
use `final_audit`. The development-split and discovery-purpose filters exclude all of them before anything
else is read. They are not even counted. The history code never opens `audit/promotion.json`,
`audit/final-audit.json` or any held-out partition. It reads only the public development manifest, to name
`dev-1`…`dev-6`. A test seeds promotion, final-audit, held-out and portability records, including
disguised ones with a development label, and shows they are excluded (section 9).

## 5. The snapshot: frozen at plan time, checked before use

* **Record cutoff:** when the plan is prepared, FaultLab reads the highest row number of the store's record
  table (`records.rowid`). The history reads only rows at or below it. Rows keep their number when updated,
  and new rows always get a higher number. So later episodes, including this campaign's own, never enter
  the window.
* **The plan stores:**
  * the Explorer-visible `summary` and its `summary_hash` (the content hash of exactly what the Explorer
    sees);
  * the `record_cutoff`;
  * the agent identity and policy hash it was computed for;
  * `episode_ids_hash`, a digest of the sorted used episode ids.
  
  The plan's own `plan_hash` covers all of these.
* **Checked three times:**
  * when the plan is saved;
  * when the learn campaign first starts;
  * again before the first Explorer request.
  
  Each check recomputes the history at the stored cutoff and compares it with the frozen block. Any
  difference refuses execution: "The store's prior history for this agent changed at or before the plan's
  record cutoff; create a new plan." One example is a pending episode that later finished, or evidence
  verified later.
* **Which actions re-check it** (corrected after the review; the earlier sentence said other studies do not):
  * any action that re-validates the plan while the campaign is still `IDLE` re-checks the history, whoever
    calls it. That covers Start and queuing any study or check on that campaign (for example a selection
    comparison), because they all go through `validate_run_plan`. Such an action is refused (409) with the
    plain message if the history changed. This is only a conservative over-refusal;
  * once the campaign has started, only the check before the first Explorer request remains.
* **How a refusal is recorded:**
  * at Start: HTTP 409 with the plain message; the campaign stays `IDLE`;
  * before the first Explorer request (after Start): the campaign ends `ERROR` with the reason
    `AGENT_HISTORY_CHANGED: The store's prior history …; create a new plan`. It no longer shows a generic
    `EXECUTION_ERROR`. No Explorer request or charge is made.
* **Checking before Start, on demand:** the saved plan panel has a **Check against the store now** button
  (`GET /api/campaigns/{id}/plan/history-check`). It runs the same recomputation read-only and answers
  `CURRENT`, `CHANGED` (with the plain message), `NOT_CHECKED` (already started) or `NOT_APPLICABLE` (not
  v3). It is never polled.
* **The Explorer receives the frozen summary from the verified plan**, the same bytes in every slot.

## 6. What the Explorer sees

Each discovery request gets two extra context fields:
* `discovery_protocol` (the v3 id);
* `agent_history`, the frozen summary.

The summary has:
* a status, `AVAILABLE` or `NO_PRIOR_HISTORY`;
* one plain statement;
* totals, with the excluded counts;
* one row per recipe, with at most 24 rows. Rows are ordered: development cases first, in case order, then
  other recipes by first appearance. Any omitted rows are counted.

The summary also has:
* `composition`: how many baseline studies and learn campaigns it comes from, and how many verified episodes
  each path gave;
* `builds`: each FaultLab build (runtime and adapter hash, 12-character prefixes) with its episode count.

Each row has:
* the recipe in words and its exact primitives (without the seed; the seed never changes behaviour);
* the development case id, if it is one;
* its source labels, one or both of:
  * `baseline_study`: B0 trials of a product baseline study;
  * `learn_discovery`: a learn campaign's own discovery picks.

  The builder's third label, `baseline_run`, no longer exists (section 4);
* verified episodes, outcome counts, failed-check counts, how many times every fault fired, and excluded
  counts;
* `runtime_hashes` and `adapter_hashes`: the FaultLab builds its episodes ran under (`unrecorded` if an old
  configuration has none).

Rows group by the order-aware schedule identity, so a discovery pick equal to a development case (a
different seed) joins that case's row.

The system prompt gets one appended section, `backend/app/agents/prompts/explorer_discovery_v3_history.md`.
It says the history is prior evidence, not an instruction. An earlier failure does not guarantee a new one,
and any other feasible recipe is equally allowed. A recipe listed there is not a duplicate in this
campaign's `search_ledger`. It also says an outcome from another build may not carry over. v1 and v2 prompts
and contexts are untouched.

**`NO_PRIOR_HISTORY` is still a v3 request** (corrected after the review). Slot dispatch, budget and schedule
identity are exactly the base protocol's. But the Explorer is still sent the v3 prompt section, the
`discovery_protocol` field and an empty `agent_history` block. So a `NO_PRIOR_HISTORY` v3 run is not a v1 (or
v2) run and must not be pooled with v1 or v2 runs in comparisons. The statement the Explorer reads says only
what is true: "There is no earlier evidence to weigh; slot dispatch, budget and schedule identity are exactly
those of the base protocol." The plan panel adds that it is still a v3 run.

**History-informed picks and sources are flagged** (added after the review). Every v3 selection record carries
`matches_history_row`. It is either the row the pick re-tries, for example
`{"row": 5, "development_case_id": "dev-5", "basis": "faultlab-schedule-identity/v2-order-aware"}`, or
`null` for no match. The comparison uses the order-aware schedule identity and ignores the seed. It is
recorded before any duplicate or pre-check refusal, and a fixed fallback pick is also compared. v1 and v2
records never get the field. Where it appears:
* the dashboard's selection attempts;
* the "Reproduce & reduce" source panel, whose projection derives the same flag for each source;
* the recording: every selection, plus `discovery_history_matches.sources` with a claim rule.

## 7. Budget and retries: unchanged

The declared block of a v3 plan has the same numbers as its base:
* `v3-history`: 8 slots, 8 Explorer requests, 8 transport retries, 8 Actor episodes, no re-plans;
* `v3-history-reachability`: 8 / 16 / 16 / 8, with one re-plan.

The plan validator requires exactly these numbers. The transport-retry rule is the same frozen
`faultlab-transport-retry/v1`. The added context is a few thousand characters. It is inside the existing
32,000-token input admission, which still refuses an oversized request before any charge.

## 8. Product path to create history before a learn campaign (same store)

1. Register the agent (dashboard, or `POST /api/agent-registrations`).
2. Create a planned **baseline** campaign for that registration (any development case) and run the product's
   **baseline study** on it (`POST /api/campaigns/{id}/baseline-study` with `execute_live: true`). This runs
   the six public development cases × 3 trials × 2 arms. B0 is the agent; B1 is the handwritten control and
   is never counted.
3. When the study has finished, create the **learn** plan in the **same store** with
   `faultlab-discovery/v3-history`. The saved plan shows the frozen history. Review it, then press Start.

Pressing Start on the baseline campaign itself runs one single-case episode. That episode never becomes
history (section 4); only the study does.

The baseline study's B0 episodes are eligible by construction:
* development split, discovery purpose;
* `study_id` = the study;
* live, weave-verified evidence;
* same registration, policy-v0.

A test runs exactly this path offline (the scripted native transport of
`test_native_baseline_study_planned.py`). A later learn campaign's own discovery episodes in the same store
also become history for the next v3 plan.

## 9. Tests and manual check (added in this build)

* `backend/tests/lab/test_agent_history.py`, unit tests:
  * the same-agent rule (a different registration or caps still counts; a different prompt, source, model,
    scorer, entry point, context protocol or policy does not);
  * eligibility;
  * B1 exclusion;
  * lab-error, interrupted, unfinished and unverified counts;
  * the snapshot cutoff (later records never leak);
  * a changed record refuses start;
  * **seeded protected records** (promotion, final audit, held-out check, portability, and disguised
    records) are excluded and never appear in any Explorer message.
* `backend/tests/lab/test_discovery_v3_flow.py`:
  * scripted-Explorer campaigns: v3 against v1, and v3 with the pre-check against v2. Same answers, same
    decisions, episodes, requests and ledger. The Explorer context differs only by the two history fields,
    and the system prompt only by the appended section;
  * declaration and budget checks;
  * native agent support;
  * `NO_PRIOR_HISTORY`;
  * the plan, the dashboard plan response and the recording show the summary and its hash;
  * a history change at or before the cutoff stops the campaign before any Explorer request.

  The declaration, budget, native-support and `NO_PRIOR_HISTORY` checks are in `test_agent_history.py`.
* `backend/tests/lab/test_discovery_v3_baseline_history.py`: the baseline-study → v3-plan product path.
* **Byte-identical v1/v2 messages:** before any edit, the exact Explorer messages of four scripted
  scenarios were captured through the real loop:
  * v1 with the reference agent;
  * v1 with the native agent;
  * v2 with repeated refused picks;
  * v2 with an Explorer that uses the feedback.
  
  Run-specific ids and hashes are replaced by numbered placeholders. The test pins their sha256 digests.
  Evidence is in `artifacts/product-discovery-v3-2026-09-29/builder/`.
* Frontend:
  * `frontend/tests/discovery-v3.test.tsx`: the options and plan validators, the plan panel (recipe list, hash,
    cutoff, and the plain no-history line), the setup choices for the native agent, and v3 pre-check selection
    records;
  * `frontend/tests/discovery-v3.browser.ts`: in a real browser, the saved plan shows the history inside the
    narrow plan panel, and the downloaded recording carries it.

The review-fix tests are listed in section 12.

## 10. Limits and honest caveats

* History shows what happened, not what will happen. 3 trials per case is a screen, not a rate.
* The same-agent rule now includes the simulator contract and service, capability set, model request settings
  and per-episode limits. It still merges episodes across FaultLab runtime and adapter builds, so that a code
  edit does not erase an agent's history. Each row lists those builds, and the Explorer is told an outcome
  from another build may not carry over.
* **The operator still chooses the store.** Planning in a store whose history looks favourable ("store
  shopping") is visible but not prevented. It shows in the plan's store identity, composition and summary
  hash, and in the recording.
* A baseline study stopped early contributes only the cases it reached. They always run in fixed order
  dev-1…dev-6, so stopping cannot isolate one case.
* **Claim rules for any v3 result:**
  1. Call it history-informed.
  2. Name the store, the history's composition and the frozen summary hash.
  3. Report a source whose `matches_history_row` is set as a re-try of recorded evidence the Explorer was
     shown, never as independent discovery.
  4. Never pool a v3 run, including a `NO_PRIOR_HISTORY` one, with v1 or v2 runs.
* v3 does not create history. A new store has none until a baseline study (or an earlier learn campaign)
  runs there.
* This makes it more likely that the Explorer tries a known repairable failure. It does not make any later
  gate easier. C1–C8, `assess_pairs`, reproduction, reducer, diagnosis, source validation, challenge and
  promotion are unchanged.

## 11. Build results (September 29, $0)

*The builder's original record, kept as it was. Its identities, summary hash (`19aa470c8d66…`), sizes, schema
id (`faultlab-agent-history/v1`) and "Known limits" are from before the review fixes; section 12 has the
current ones.*

**Identities.** Runtime `c9af0a47…` → **`a8a32234a45a9a1f047c605df84c73f1722369c038dfab8b98377e7e88cf6a20`**,
algorithm `6d6433df…` → `eea45d1d…`. These are unchanged:
* simulator service `3ce5bcd2…` and contract `6f9d7783…` (`simulator/`, `contracts/` and `referee/` were not touched);
* the interpreter files;
* the reference Actor prompt `12eabe7f…`;
* the native prompt `2251542869cf…`.

Every agent must be registered again before a live run, because a registration records the runtime hash.
Under the same-agent rule, the new registration still sees the same agent's earlier history.

**What changed.** New:
* `backend/app/lab/agent_history.py`;
* the prompt section `backend/app/agents/prompts/explorer_discovery_v3_history.md`.

Edited:
* `discovery_protocol.py`: two v3 ids, and a base-protocol map;
* `run_plans.py`:
  * the v3 options, freezing at plan time, and the `AgentHistoryPlan` model;
  * v1/v2 blocks never get a `history` key;
  * binding checks, and the check at plan creation and first start;
* `learning.py`: the check before the first Explorer request, which then passes the frozen summary;
* `explorer.py`: two context fields and the appended section, v3 only;
* `storage.py`: three read helpers for the cutoff.

Dashboard:
* `runPlans.ts`: types and validators;
* `DiscoveryProtocol.tsx`: the history panel;
* `searchAttempts.ts` and `SearchAttemptsPanel.tsx`: they accept v3-with-pre-check selection records;
* `styles.css`.

One existing test assertion was widened. The options list is now v1, v2 and the two v3 forms, so
`test_discovery_v2_flow.py` checks the first two. Patch against the pre-edit commit:
`artifacts/product-discovery-v3-2026-09-29/builder/changes_vs_backup.patch`.

**Suites, one run each, after the last code edit:**
* **Full backend: 2,673 passed, 180 existing skips, 0 failed**, with the 2 known warnings, in 927 s.
  The earlier run had 2,651 passed; the difference is the 22 new tests.
* **Frontend: 317 unit tests** (19 files), all passed.
* Production build passed (size advisory only).
* **Browser: 16 passed, 1 opt-in skipped.** The new `discovery-v3.browser.ts` is one of the 16.

**v1/v2 unchanged.** The four scripted scenarios gave the same normalized Explorer messages after the change
as before it:
* v1 with the reference agent: 8 requests;
* v1 with the native agent: 8 requests;
* v2 with repeated refused picks: 12 requests;
* v2 with an Explorer that uses the feedback: 12 requests.

The same decisions and episodes are pinned in `test_discovery_v3_flow.py`. Evidence:
* `goldens_before_run1.json` and `goldens_before_run2.json`, captured before any edit and identical to each
  other;
* `goldens_after_backend_edit.json`.

**The protected-data test can fail.** A deliberate mutant removed the split and purpose filters. Then both
protected-data tests failed: a learn campaign's own promotion and final-audit trials carry
`study_id == campaign_id`, exactly like its discovery episodes. With the original code restored, they pass
again (`mutation_check.txt`).

**Manual offline check** (scratch store under `…/builder/manual-store-final/`; scripted native transport,
in-process simulator, local Weave double; 0 Explorer, Mechanic or network requests):
1. The product's baseline study on a planned native baseline campaign completed. 36 slots ran. B1 gave only
   `COMPLETED` / `CORRECTLY_REJECTED`.
2. A v3 learn plan was then created through `POST /api/planned-campaigns`, and read back through
   `GET /api/campaigns/{id}/plan`. Its frozen history:
   * `AVAILABLE`;
   * **18 verified episodes, 6 recipes** (`dev-1`…`dev-6`, 3 each, source `baseline_study`);
   * B1 not counted, 0 exclusions;
   * summary hash `19aa470c8d66…`, record cutoff 829.
3. `discovery_history()` returns exactly this summary to the Explorer.
4. The v3 budget and retry rule equal v1's, and the v1 plan has no `history` field.
5. A v3 plan for the reference Actor in the same store says `NO_PRIOR_HISTORY`, because it is a different
   agent.

The scripted native transport is a fixture, not model evidence. Its dev-3 and dev-5 rows show `C3 3` only
because that is how the scripted fixture answers. Result: `manual_check_result_final.json`. The first run of
this check put its lab store outside the project folder by mistake: it used a relative path, which the
settings resolve against the project root. The store was moved into `…/builder/manual-store/`, and the
script now resolves the path first.

**What v3 would have frozen from the saved native stores.** These were read only, opened `mode=ro&immutable=1`;
file sizes and modification times were unchanged (`readonly_history_result.json`, `store_stat_*.txt`):

| store | registration | history the Explorer would get |
|---|---|---|
| `native-probe` (baseline study, Sep 28) | `smolagents-1.26.0-d72de2e0…` | 18 verified; **dev-5: VIOLATION 3/3, failed C3 3, C5 3**; dev-3: VIOLATION 3/3 (C5, C6, C7); dev-1 1/3 and dev-6 1/3 violated; dev-2 and dev-4 completed 3/3 |
| `native-learn` (campaign 7ee35abe, Sep 29) | `smolagents-1.26.0-819f4d1f…` | 8 verified, all from that campaign's discovery; 3 VIOLATION (C5, C6, C7) on long delayed upgrades; **no rejected-upgrade row** |

Both registrations have the same agent identity (prompt `2251542869cf…`, source `2867b3fb…`, model
DeepSeek-V3.1, scorer `19de811c…`). The summaries are about 1,000–1,400 Explorer tokens.

So v3 would not have changed campaign 7ee35abe. Its store had no rejected-upgrade history. For the next live
native attempt, run the baseline study in the new store first (section 8, about $2.14 declared last time),
then create the v3 learn plan there.

**Known limits:**
* The check before the first Explorer request stops the campaign as a generic `EXECUTION_ERROR`, with its
  class and code location. The same condition at Start is refused with the plain message ("…changed at or
  before the plan's record cutoff; create a new plan").
* Each v3 selection record stores its context, which now includes the summary (a few KB per request).
* Nothing here has run live. Whether the Explorer then picks the rejected-upgrade recipe, and whether the
  later stages work live, are still unproven.

## 12. Review fixes (September 29, $0)

Two independent $0 reviews found no leak of protected data and no change to any gate, score or budget. Both
returned READY_WITH_CHANGES:
* the integrity review: 1 MEDIUM and 4 LOW findings;
* the product review: 3 LOW findings and 1 INFO item.

**All of them are applied; none was declined.** Evidence is in `artifacts/product-discovery-v3-2026-09-29/fixer/`.

| # | from | finding | what changed | shown by |
|---|---|---|---|---|
| 1 | integrity, MEDIUM | An operator could curate the history with single-case baseline runs (three dev-5 runs froze a dev-5-only history). | Source label `baseline_run` removed. Only whole baseline studies and learn campaigns' own discovery picks count. The summary now states its `composition`. Claim rule added (section 10). | `test_single_case_baseline_runs_never_shape_the_history`; manual check part 1 through the real Start path; the reviewer's own probe now fails as intended |
| 2 | integrity, LOW | "Same agent" merged across simulator contract/service, capability set, model settings, per-episode limits and builds, without saying so. | Identity now includes contract, service, capability set, model request settings and per-episode limits. Runtime and adapter builds are listed per row and in `builds`, not merged silently. Rule text and section 3 updated. | `test_same_agent_includes_contract_service_capability_limits_and_model_settings`, `test_rows_list_the_runtime_and_adapter_builds_their_episodes_ran_under`; the reviewer's probe now fails as intended |
| 3 | integrity, LOW | "Discovery runs exactly as its base protocol" was not true of the request under NO_PRIOR_HISTORY. | Statement reworded. The panel says it is still a v3 run. Section 6 has a no-pooling rule. | `test_the_no_history_statement_claims_only_what_is_true`, `test_no_prior_history_is_still_a_v3_request_not_a_v1_one` |
| 4 | both, LOW | The note named the source labels wrongly. | Section 6 lists `baseline_study` and `learn_discovery` and what each means. The frontend rejects any other label. | frontend unit test |
| 5 | integrity, LOW | A v3 source that re-picks a history recipe was not marked. | `matches_history_row` on every v3 selection record. Also shown in the search-attempts API and panel, the source projection and panel, and the recording (`discovery_history_matches`, with the claim rule). | `test_v3_picks_and_sources_that_retry_a_history_row_are_flagged_in_records_api_and_recording`; frontend unit test |
| 6 | product, LOW | Section 5 said other studies do not re-check the history; they do while the campaign is IDLE. | Section 5 corrected. The conservative over-refusal is kept (no code change). | code reading; existing behaviour |
| 7 | product, LOW | A change caught before the first Explorer request ended as a generic `EXECUTION_ERROR`. | `HistoryChanged` is now a `StoreConflict` with code `AGENT_HISTORY_CHANGED`. The campaign records the plain reason (still 409 at Start). | `test_a_history_change_before_the_first_explorer_request_ends_the_campaign_with_the_plain_reason` (the coordinator's real execution path), `test_a_changed_history_keeps_its_plain_reason_when_recorded_as_an_execution_failure` |
| 8 | product, INFO | A stale plan still looked "Ready to start"; checks appeared as bare ids. | The panel says Start re-checks the history. A **Check against the store now** button calls `GET …/plan/history-check`: on demand only, never polled, in the worker pool, on the snapshot reader. Failed checks are named, for example "C3 (upgrade before confirmation)". | `test_dashboard_api_checks_history_on_demand`; frontend unit and browser tests |

**The format changed from `faultlab-agent-history/v1` to `/v2`.** Summary hashes and sizes differ from
section 11. A read-only scan found:
* 8 run stores under `FaultLab_Runs`, with 11 saved plans in total;
* 0 plans that declare v3.

So no run plan is affected. v3 plans saved by the builder's version exist only in the scratch evidence stores.
They no longer verify, and they could not start anyway, because the runtime changed.

**Identities:**
* runtime `a8a32234…` → **`08e4c20dc6a3e841bb42032e5b61618cd08289d9a162ad30f683bb98ea0348c8`**;
* algorithm `eea45d1d…` → `8fb8ab2a…`.

Unchanged:
* simulator service `3ce5bcd2…` and contract `6f9d7783…`;
* interpreter `6da0714a…`;
* reference Actor prompt `12eabe7f…` and native prompt `2251542869cf…`;
* native adapter `61497db3…`.

`backend/app/referee`, `backend/app/simulator` and `contracts/` are identical to `backup/part2-2026-09-22`.
Every agent must be registered again before a live run.

**v1 and v2 are unchanged:** the four pinned golden digests of section 9 still pass.

**Integrity re-checks:**
* **The reviewers' probes, rerun from a copy:** the two probes that demonstrated findings 1 and 2 now fail, as
  intended. The three safety probes (post-cutoff registration, forged plan, provenance hash) still pass.
* **The in-memory mutation check** (no file edited; `agent_history.py` sha256 unchanged): with the split and
  purpose filters removed, both protected-data tests fail and the protected recipe reaches the Explorer
  messages. With the code as it is, both pass.

**Suites, one run each, after the last code edit:**
* **backend: 2,683 passed, 180 existing skips, 0 failed**, with the 2 known warnings, in 928 s. That is the
  builder's 2,673 plus 10 new tests;
* **frontend: 320 unit tests** passed (19 files, 3 new);
* production build passed (size advisory only);
* **browser: 16 passed, 1 opt-in skip.**

No code or test file changed after the suites started (sha256 compared). Only this note and
`CURRENT_STATUS.md` were edited afterwards, and no test reads them.

**Manual offline check on the final code** (`fixer/manual_check.py`, scratch store `fixer/manual-store-final/`).
It used the scripted native transport, the in-process simulator and a socket guard. There were 0 Explorer,
0 Mechanic and 0 network requests; the 84 Actor calls were scripted fixture answers.
1. Three planned single-case native baseline campaigns on dev-5 were started through
   `POST /api/campaigns/{id}/start`. Each ended COMPLETED, VIOLATION, with C3 failed; each episode had
   `study_id == campaign_id`. A v3 plan created afterwards said **NO_PRIOR_HISTORY: 0 used, 0 counted.**
2. The product baseline study then ran on another planned campaign. A v3 plan then froze **18 verified
   episodes**:
   * 6 rows, dev-1 to dev-6, with 3 each; dev-5 has 3, not 6, because the single-case runs still do not count;
   * `composition`: 1 baseline study, 18 episodes;
   * `builds`: one build, runtime `08e4c20dc6a3`, adapter `61497db3ae1d`;
   * summary hash `44bd2c789a26…`, cutoff 926.
3. The frozen history matched the agent's identity; the Explorer receives exactly the frozen summary; the
   budget and the retry rule equal v1's; the v1 plan has no history field; the reference Actor in the same
   store gets NO_PRIOR_HISTORY.
4. `history-check` answered CURRENT. After one counted episode's evidence was changed, it answered CHANGED.
   Start was then refused with 409 and the plain message. The campaign stayed IDLE, with 0 new selections.
5. **Size:** the summary is 4,209 characters, a token bound of 1,422 with the Explorer's encoding. The
   builder's summary of the same 6-row study was 3,446 characters (bound 1,120). The v3 prompt section is 1,424
   characters. This is far under the 32,000-token admission limit.

The scripted transport's dev-3 and dev-5 answers are fixture behaviour, not model evidence.

**Read-only check of the saved stores** (`fixer/readonly_history.py`, opened `mode=ro&immutable=1`; every
store file had the same size and modification time before and after):

| store | what v3 would freeze now |
|---|---|
| `native-probe` | **18 verified** from 1 baseline study. dev-5 VIOLATION 3/3 (C3 3, C5 3, C6 1, C7 1). Build: runtime `c0a8aad71dfe`, adapter `8a579f997793` |
| `native-learn` | **8 verified** from 1 learn campaign's discovery. No rejected-upgrade row. Build: runtime `c9af0a47013a`, adapter `61497db3ae1d` |

The two registrations are still the **same agent** under the stricter rule. So continuity is kept, and each
row shows its build.

**Current known limits:**
* the operator still chooses the store (section 10);
* `matches_history_row` compares only rows the Explorer was shown (at most 24);
* a stopped baseline study contributes the cases it reached, always in fixed order;
* each v3 selection record stores its context, including the summary (a few KB);
* **nothing here has run live.**

**Next, for a live try:**
1. Register the native agent again under `08e4c20d…`.
2. Run the baseline study in the **new** store.
3. Create the v3 learn plan there, and review the frozen history, its composition and its builds.
4. Press **Check against the store now**.
5. Declare the run, and report the result as history-informed.

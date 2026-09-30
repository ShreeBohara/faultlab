# Discovery protocol v4 (history replay): design and build (September 30, 2026)

Offline build, **$0**: no provider, model, W&B, Weave or network call. No saved run store was written. Nothing here
has been run live. The product default is still **discovery v1**. v1, v2-reachability, v3-history and
v3-history-reachability behave exactly as before for plans that choose them (section 8).

**Status (fixer, September 30):** built, then reviewed twice at $0 (integrity and product); the fixer applied the
review findings (section 14). Not committed, not run live. Current runtime **`ee2d1df9…`** (section 12).

## 1. Why

Live runs on the report-fixed native agent (smolagents, adapter v2.1) show one very reliable, repairable failure:
`dev-5`, a rejected upgrade, after which the agent sends the confirmation anyway (C3). It failed 6 of 6 across two
v2 probes and 9 of 9 on adapter v1. There is also one frequent but flaky failure (C4 after failed confirmation
sends, roughly 70-85% per episode). A source must fail 3 of 3 in reproduction and 3 of 3 again in reduction, so only
the reliable one survives those gates.

In three history-informed (v3) Learn campaigns the Explorer never picked the rejected-upgrade recipe. Its picks
produced only flaky or non-reproducing sources ([native v2 run](PRODUCT_NATIVE_V2_RUN_2026-09-29.md),
[discovery v3](DISCOVERY_V3_HISTORY_2026-09-29.md), [native learn v3 run](PRODUCT_NATIVE_LEARN_V3_RUN_2026-09-29.md)).
So the binding limit is now which recipe discovery picks.

**v4 = regression-first discovery.** Before the Explorer picks anything, FaultLab re-runs the recipes that the same
agent's own frozen history shows failing reliably. The Explorer then uses the remaining slots exactly as under v3.

## 2. What v4 is, in one paragraph

`faultlab-discovery/v4-history-replay` is **exactly v3-history** plus a **replay list**:
* the same frozen, same-agent history (same eligibility, exclusions, summary hash, record cutoff and Start-time check);
* v1 dispatch, v1 schedule identity (for the duplicate rule) and v1 budget for the Explorer slots.

When the plan is saved, FaultLab computes the replay list from that frozen history and freezes it into the plan.
Discovery then runs the replay slots **first**:
* each replay slot runs one agent episode of its history row's recipe;
* it uses one discovery slot and one Actor episode;
* it sends **no Explorer request**.

A replay becomes a source by exactly the same rule as any discovery slot: COMPLETED, every fault fired, VIOLATION.
The remaining slots are v3-history's Explorer slots.

## 3. The replay rule (frozen into the plan with its text)

A history row is **eligible** only if all of these hold:
* it has at least one scheduled fault (**a no-fault row is never replayed**);
* it has at least **2 verified episodes**;
* **every** verified episode fired **every** scheduled fault;
* its **violation share** (VIOLATION outcomes ÷ verified episodes) is at least **2/3**.

Eligible rows are **ordered** by:
1. violation share, highest first;
2. then verified episodes, most first;
3. then their order in the history.

**At most 3** rows are replayed.

The **recipe** a replay runs has the same schedule as the row under `faultlab-schedule-identity/v2-order-aware` (the
identity history rows are grouped by):
* a development-case row runs the case's public recipe;
* any other row runs its listed faults with seed 0.

The seed is bookkeeping only; it never changes behaviour.

The rule reads **only the listed rows** of the frozen summary (at most 24). The list is a pure function of the frozen
summary and the public development manifest; it reads nothing else from the store.

**What the plan records** (`discovery.replay`, schema `faultlab-history-replay/v1`):
* the rule text and the thresholds;
* the frozen summary hash it was computed from;
* a status: `AVAILABLE`, or `EMPTY` with a plain statement.

For each replayed row it records:
* its replay number and history row number;
* the development case, if any;
* the recipe, in words and as the exact fault recipe;
* its order-aware schedule identity;
* its counts: verified episodes, violations and share, every-fault-fired count, outcomes, failed checks, and sources.

## 4. What runs, in order, and the budget

The slot, Explorer and episode maxima are v3-history's: **8 slots, 8 Explorer requests, 8 transport retries, 8 Actor
episodes, no re-plans**. Replay slots count toward the slots and the Actor episodes. They use no Explorer request.
With 2 replays, the Explorer gets at most 6 requests.

For each slot:
1. **Replay slots (the first N, N = 0 to 3).** FaultLab saves a selection record with:
   * provenance `history_replay`;
   * usage of 0 model calls;
   * empty answer text;
   * search decision `SELECTED`, carrying `history_replay: {replay, history_row, development_case_id}`;
   * a `history_replay` block (label `history replay`, the row, its counts, the episode id, `explorer_request: false`);
   * the usual `matches_history_row`.

   It then runs the Actor episode through the unchanged runner. From there the slot follows the unchanged path:
   evidence, then the source rule. If it is a source: reproduction, reduction, diagnosis, candidates, challenge and
   promotion, all unchanged.
2. **Explorer slots (the rest).** These are exactly v3-history's requests. The Explorer reads the frozen history
   (`agent_history`, byte-for-byte the plan's summary) and its search ledger. The ledger now lists the replays as
   prior selections marked `history_replay`, with their results under `tested_schedules`. The duplicate rule applies
   to them: re-picking a replayed recipe is `SKIPPED_DUPLICATE`.

The replays never apply the duplicate rule among themselves. Their rows are distinct under the order-aware identity by
construction.

**A replay source can end discovery early** (review finding F2). The loop is unchanged: a source goes through
reproduction, reduction, diagnosis and candidates **before the next slot starts**, and the campaign's candidate requests
(at most 4) are shared by the whole campaign. When they are used up, the unchanged rule
`if candidate_count>=campaign.caps.candidates: break` ends discovery. So if the first replay's source reaches the
candidate stage and the Mechanic uses all 4 requests there, the later replays and every Explorer slot never run (the
product review's offline run M4 ended NO_CHANGE with 0 Explorer requests this way). The chooser sentence and the saved
plan's statement say so. Expect no Explorer-slot data from a v4 run in which a replay source reaches the candidate stage.

## 5. What the Explorer sees

When the replay list is **not empty**, one section is appended after v3's prompt section
(`backend/app/agents/prompts/explorer_discovery_v4_history_replay.md`). It says that:
* FaultLab ran the frozen replay list itself, by a fixed rule, before any Explorer request;
* the replays are in `search_ledger` as prior selections marked `history_replay`;
* choosing one again is a duplicate;
* a history recipe that was not replayed is still not a duplicate;
* the remaining slots are the Explorer's, under the rules above.

This matters because v3's section says history recipes are *not* duplicates. That stays true for the rows that were
not replayed.

The context fields are v3's: `discovery_protocol` (the v4 id) and `agent_history`. There is no new context field.

## 6. "History replay" everywhere; never independent discovery

| where | what it shows |
|---|---|
| selection record | `provenance: history_replay`, `history_replay` block with the row, `explorer_request: false`, 0 model calls |
| Explorer's search ledger | each replay's decision carries `history_replay: {replay, history_row, development_case_id}` |
| fault-search panel (dashboard) | "Selection 1 · History replay 1 of 2 · agent history row 5 (dev-5) · no Explorer request", with a sentence saying it is never independent discovery, a link to the replay episode and a "History replays · no Explorer request" count. The panel's summary sentence counts only the Explorer slots that have a record ("the Explorer chose the next N slots recorded here"); with none it says no Explorer slot is recorded and points to the campaign's recorded outcome (review finding F1) |
| source panel ("Reproduce & reduce") | **Found by**: "History replay … of agent history row … : … never independent discovery." For an Explorer pick in a v4 campaign it says "An Explorer pick in this discovery v4 campaign, not a history replay slot." |
| campaign recording and every export built from it (regression bundles' `evidence.json`) | selections keep `history_replay`; `discovery_history_matches.sources[*].history_replay`; a `discovery_history_replays` block: the frozen list, the replay slots that ran, `sources_found_by_replay` and the claim rule. `discovery_history_matches.claim_rule` names discovery v4 and history replays in a v4 recording; a v3 recording keeps its exact text (review finding F4) |
| Run summary panel (dashboard) | one line under the heading for the incident it shows: "Found by History replay 1 of 2 · agent history row 5 (dev-5): a history replay of that row, never independent discovery." or "Found by an Explorer pick in this discovery v4 campaign, not a history replay slot."; nothing for other protocols (review finding LOW-3) |
| saved-plan view | **History replay list · runs first**: each row with its counts, the frozen-from hash, the rule, and the claim sentence; shown before the frozen history. A replayed row without a development case reads "(no development case: a recipe first picked by the Explorer in an earlier learn campaign)", never "(Explorer pick)" (review finding LOW-2) |
| **not labelled** | W&B regression dataset rows (only `experiment_purpose: discovery`), the Weave traces of the replay's Actor episode, and bundles imported without `evidence.json` (review finding LOW-3, deferred). Cite the recording's `discovery_history_replays` block or the source panel's **Found by** line, never these views, for a v4 result |
| discovery chooser | "v4 · history replay first", with one plain sentence (below) |

The chooser sentence: *"Before the Explorer picks anything, re-runs up to 3 recipes from this agent's frozen history
that fired every fault and failed in at least 2 of every 3 verified episodes (one agent episode each, no Explorer
request); the remaining slots are exactly v3 · agent history, but a replay source goes through the normal loop first,
and if that uses up the campaign's candidate requests, discovery ends before any later replay or Explorer slot runs."*
(The last clause was added for review finding F2.)

**Claim rule:** a source found in a replay slot re-ran a recipe from the frozen history, chosen by the plan's fixed
rule and not by the Explorer. Report it as a history replay of that row, naming the row, the store and the frozen
summary hash. Never report it as independent discovery or as an Explorer pick. All of v3's claim rules still apply to
the rest of the run.

## 7. An empty replay list

If the store has no prior history, or no row meets the rule, the list is empty. The plan says so plainly:
* "Replay list empty: this store has no prior history for this agent, so nothing is replayed. Discovery runs exactly
  as v3 · agent history."; or
* "… no row of the frozen agent history meets the replay rule …".

Discovery then behaves exactly as v3-history. No v4 prompt section is sent. Every Explorer request equals a v3-history
request except the declared `discovery_protocol` value, which is pinned by a test. Report such a run as v4 with an
empty replay list. Do not pool it with v1 or v2 runs.

## 8. Checks, and what does not change

* **Start refuses a changed history.** The plan's history is verified exactly as v3's is: when the plan is saved, at
  Start, on any IDLE re-validation, and before the first replay or Explorer request. The replay list is then
  recomputed from the verified history and compared with the frozen list. Any difference refuses the run: 409 at
  Start, or `AGENT_HISTORY_CHANGED` with the plain reason if it is caught after Start. A list the installed rule would
  not produce (for example a future rule change) is refused the same way. The saved-plan panel's **Check against the
  store now** button covers the replay list too.
* **Unchanged:**
  * the other four protocols' dispatch, prompts, contexts and records (the pinned v1/v2 Explorer message digests
    still pass, and so do all v3 tests);
  * reproduction, reduction, diagnosis (including `summarize_evidence`), candidates, source validation, the challenge
    (its Explorer is unchanged) and promotion;
  * C1–C8, the referee, the simulator, the contracts, `assess_pairs` and every threshold;
  * the reference Actor and its prompt, and native adapters v1 (byte-identical) and v2.
* **Old plans** never get a `replay` key, not even null, so their bytes are unchanged.
* **The shared agent history** (used by v3 and v4 alike) skips history replay episodes (fixer; section 9). In any store
  without a v4 campaign, which is every store that exists today, it is byte-identical to the history before v4, so saved
  v3 plans still verify.
* **Available** for the reference Actor and native adapters v1 and v2. Not combined with the reachability pre-check
  this round.

## 9. Known limits and honest caveats

* **Nothing here has run live.** Whether a replayed dev-5 source survives reproduction and reduction live, and what
  the Mechanic then diagnoses, is unmeasured. A replay only chooses *which recipe runs first*. Every later gate is
  unchanged.
* **The operator still chooses the store** (as under v3). v4 makes the history's influence much stronger: it now
  decides the first slots outright. Name the store, the history's composition and the frozen summary hash for any
  result.
* **Replay episodes never enter a later agent history** (fixer, review findings MEDIUM-1 and F3). The builder's
  version counted them as `learn_discovery` ("a learn campaign's own discovery pick, chosen by the Explorer"), so a
  later v3 or v4 plan in the same store would have shown a replay as an Explorer pick, and a replayed row would have
  fed on its own replays (the product review saw dev-3 and dev-5 go from 3/3 to 4/4 after one v4 run). Now
  `app.lab.agent_history` skips every episode whose selection record has provenance `history_replay`: FaultLab chose
  it by the plan's fixed rule, so it is not one of the two allowed product paths. It is not used and not counted, the
  same treatment as a single-case baseline run. The same campaign's Explorer picks still count as learn discovery.
  The history schema stays `faultlab-agent-history/v2`: no store written before v4 holds a replay record, so every
  existing history block, summary hash and saved v3 plan is unchanged. The fixer recomputed the history of every
  reviewed registration in all 11 saved stores with the code before and after the fix: all 14 blocks are identical,
  and the stores were opened read-only (`fixer/store-history-compare.log`). v4 still uses exactly v3's history.
* **A replay source can use up the candidate requests** and end discovery before any Explorer slot (section 4).
* **A flaky row can still qualify.** In the latest v2.1 store, v4 would replay dev-6 second (2/3 C4, section 10).
  A 2/3 row may fail reproduction (3 of 3 needed). If it does, it costs a replay episode plus up to 3 reproduction
  episodes.
* Rows beyond the 24 listed in the summary are never considered. Two replay rows that differ only in the order of
  overlapping same-kind faults would share one v1 identity. Both still run, since their order-aware identities differ.
* The first build's dashboard validator refused real replay rows. The API sends `transport_retries: []` on every row,
  and the validator wanted the field absent; the unit-test fixture had copied the wrong shape. This was found in the
  builder's own contract check (section 11) and fixed before the final suites.

## 10. What v4 would freeze from the saved stores (read-only)

Computed with the product's own history reader and the replay rule. Every store was opened only with
`mode=ro&immutable=1`, and every store file kept its size and modification time
(`artifacts/product-discovery-v4-2026-09-30/builder/readonly_replay_result.json`).

| store | agent (registration) | history | v4 replay list |
|---|---|---|---|
| `2026-09-30/native-v2b` | adapter v2.1 (prompt `fff397c9`, the current v2.1 identity) | 25 verified | **1: dev-5 (row 5), 3/3, C3 3 · C5 3**; 2: dev-6 (row 6), 2/3, C4 2 · C5 2 |
| `2026-09-30/native-v2` | adapter v2, first build (prompt `cee3aeda`; a different agent from v2.1) | 23 verified | 1: dev-5 3/3; 2: dev-6 3/4 |
| `2026-09-29/native-learn-v3` | adapter v1 | 22 verified | 1: dev-5 3/3 (C3 3, C5 3) |
| `2026-09-28/native-probe` | adapter v1 | 18 verified | 1: dev-3 3/3 (C5, C6, C7); 2: dev-5 3/3 (C3 3) |
| `2026-09-29/native-learn` | adapter v1 | 8 verified (campaign 7ee35abe's own picks) | empty: each of its 8 rows has only 1 verified episode |
| six other stores | reference Actor (one also has an unused native v1 registration) | 0-8 verified | empty |

A v2.1 registration made under this runtime has the same agent identity as the `native-v2b` store's registration
(same prompt hash `fff397c9…`). So a v4 plan in that store would replay dev-5 first. Registering again is still
required, because the runtime changed.

## 11. Tests and checks (builder, $0)

**New tests** (`backend/tests/lab/test_discovery_v4_replay.py`, 23 tests):
* plan freezing and ordering: share, then verified count, then row order; ties; the cap of 3; ineligible rows (fewer
  than 2 verified, share 1/2, an unfired fault, no fault); exactly 2/3 is eligible; empty history and no eligible
  rows; case recipe versus seed 0; the rule recorded and re-checked; the saved-plan models refuse inconsistent blocks;
* the product plan path for the reference Actor, native v1 and native v2: the history equals v3's and the budget
  equals v3's;
* the loop:
  * replays run first with no Explorer request, and the Explorer continues with the remaining slots;
  * the duplicate rule applies to replays;
  * a replay VIOLATION becomes a source through the unchanged rule, labelled in the selection record, the
    search-attempts API, the source projection and the recording;
  * a non-violating replay only uses its slot;
  * at most 3 replays;
* with an empty list, v4's Explorer messages equal v3-history's except the protocol id;
* Start refuses a changed history, through validation and through the coordinator, with no replay run;
* Start refuses a list the installed rule would not produce;
* the history-check button covers the list;
* v3 records never carry replay fields.

**Frontend:** `frontend/tests/discovery-v4.test.tsx` (6 unit tests) covers:
* the options and saved-plan validators;
* the saved-plan replay list and the empty statement;
* the chooser sentence and the create request;
* the replay labels in the fault-search and source panels, including the refusal of replay rows that claim a model
  call, an answer, a retry or another row.

`frontend/tests/discovery-v4.browser.ts` checks, in a real browser, that the replay list fits inside the narrow plan
panel and that the downloaded recording carries it. One existing assertion was widened: the options list is now the
first four protocols plus v4 (`test_agent_history.py`).

**Negative controls** (`builder/mutation_checks.py`, scratch copies outside the Desktop): **21 of 21 mutations
caught**. Examples:
* replays never run;
* a no-fault row may be replayed;
* the share threshold is 1/2;
* at most 4 rows;
* a replay hidden from the ledger;
* the prompt section always or never sent;
* each label dropped;
* Start does not recompute the list;
* five frontend mutants.

**Manual offline check through the product API** (`builder/manual_check.py`; scripted native transport, in-process
simulator, local Weave double, socket guard; 0 network connections; the scripted outcomes are fixture behaviour):
* baseline study, then a v4 plan: dev-3 and dev-5 replayed (the fixture's 3/3 rows); dev-1 (no fault) and the rest
  not replayed;
* history equal to v3's and budget equal to v3's;
* the check button says CURRENT;
* Start: 2 replay slots (0 model calls each), then 6 Explorer requests. The first request's ledger lists both replays
  and their VIOLATION results, and the v4 section was sent;
* labels correct in the search-attempts, experiments and recording responses;
* a changed counted record gives CHANGED, and Start is refused 409 with 0 new selections;
* with the real Reproducer: the replay source reproduced **3 of 3** and was labelled a history replay. The run was
  stopped at reduction by a declared stop point, so no Mechanic, challenge or protected case was reached.

**API contract check** (`builder/api_contract_check.py`): the real plan, search-attempts and experiments responses of
an offline v4 run pass the dashboard's own validators. With the first build's validator line restored, the check fails
(`api-contract-check-negative-control.log`).

**Suites:** one `scripts/test.sh` after the last code edit (`builder/full-test-sh.log`):
* backend **2,905 passed, 180 skipped, 0 failed**, with the 2 known warnings, in 1,096 s. That is 23 more than the
  2,882 of the previous runtime `4553ebe7`: the 23 new tests;
* frontend **345** unit tests (6 new);
* production build passed (size advisory only);
* browser **18 passed, 1 opt-in skip** (1 new).

No code or test file changed during the run (sha256 compared, `builder/source-sha256-at-suite-start.txt`). Only this
note and `CURRENT_STATUS.md` were edited during or after the run, and no test reads them.

## 12. Identities

* Builder: runtime `4553ebe7…` → `2a1815399697a774597c1d485f605dccc9e4e57cddee9899a5b577c35ad1514d`, algorithm
  `b2575eb2…` → `f66ae8bb570dffb9e5c7b3e26792c4bd9e9433e82994781cdd6ffc6b53b03bb3`.
* **Fixer (current):** runtime → **`ee2d1df914bd54c766eaec200715ad976f7d905964e1077adbb14ce46cc928e9`**, algorithm →
  **`ab296a32c118294f5f36c1c42ffc3fa066863007b449acd88bc29d2b0f1b2b81`** (`fixer/identity-compare.txt`). The fixer
  changed `backend/app/lab` only (`agent_history.py`, `history_replay.py`, `run_plans.py`, `exports.py`), so the
  example configuration hashes changed again (they embed the runtime) and nothing else did.
* Reference Actor source hash (the `backend/app/agents` tree) `142a9ebc…` → `2597bffb…` (builder; unchanged by the
  fixer). It is not part of the same-agent identity.

Unchanged:
* simulator service `3ce5bcd2…`, contract `6f9d7783…`, interpreter `6da0714a…`, scorer `19de811c…` and capability
  set `8e8e04af…`;
* reference Actor prompt `12eabe7f…`;
* native v1 adapter `6f303264…` and prompt `22515428…`;
* native v2.1 adapter `dfd41b33…` and prompt `fff397c9…`.

`external_agent.py` is byte-identical. Register every agent again before a live run (the runtime changed). Agent
histories are unaffected, because the same-agent identity does not use the runtime.

## 13. How to use it (next live step, not yet run)

1. Register the native agent again under `ee2d1df9…`: adapter v2.1 for the `native-v2b` history, or v1 for its own
   stores.
2. In the store that holds that agent's history, create a Learn plan with **v4 · history replay first**.
3. Review the saved plan: the frozen replay list (row, recipe, share, counts) and the frozen history.
4. Press **Check against the store now**, declare the run, then Start.
5. Report every source found by a replay as a history replay of its row.

## 14. Review findings and fixes (fixer, September 30, $0)

Two $0 reviews (integrity: `review-integrity/`; product, with the real backend, dashboard and browser:
`review-product/`) found no leak and no gate change. The fixer verified each finding in the code, fixed it with a test
that fails on the code before the fix and passes after (`fixer/mutation-checks.log`: 14 of 14 mutations caught, both
controls pass), and changed no gate, threshold, scorer, simulator, contract, prompt, adapter or loop stage.

| finding | verdict | change | test |
|---|---|---|---|
| MEDIUM-1 (integrity), F3 (product): replay episodes counted in later histories as Explorer picks, and feeding the replay rule | FIXED | `agent_history.py` skips episodes whose selection has provenance `history_replay` (not used, not counted); existing stores unchanged (11 stores, 14 histories identical) | `test_a_replay_episode_never_enters_a_later_agent_history_but_the_explorers_pick_does` |
| F2 (product): replay sources can use up the 4 candidate requests and end discovery before any Explorer slot; nothing said so | FIXED (wording; the loop is deliberately unchanged) | one clause in the chooser sentence and two sentences in the saved plan's statement; this note section 4 | `test_the_chooser_and_the_plan_say_…`; characterization `test_the_unchanged_loop_ends_discovery_…` (passes on the code before the fix too) |
| F1 (product): fault-search panel said "the Explorer chose the remaining slots" when none ran | FIXED | the sentence counts the recorded Explorer slots; with none it says so and points to the recorded outcome | frontend `F1: never says the Explorer chose slots that have no record…` |
| F4 (product): v4 recording's history claim rule said "discovery v3" | FIXED | v4 recordings name v4 and history replays; v3 recordings keep the exact old text (pinned) | `test_a_v4_recording_names_v4_…_and_a_v3_recording_keeps_its_exact_text` |
| LOW-2 (integrity): a no-case replay row read "(Explorer pick)" | FIXED | "(no development case: a recipe first picked by the Explorer in an earlier learn campaign)" | frontend `LOW-2: …not labelled an Explorer pick` |
| LOW-3 (integrity): Run summary, W&B rows, Weave traces and evidence-less imports do not say "history replay" | Run summary FIXED; W&B rows and Weave traces DEFERRED | Run summary shows a "Found by …" line for the incident it shows (v4 only) | frontend `LOW-3: the run summary says which slot found the incident…` |
| LOW-4 (integrity): status page quoted the offline reproduction without "scripted replies", and two ledger totals | FIXED | `CURRENT_STATUS.md`: scripted-reply caveat; one current total $898.58 (ledger at `4d1c21b`), $893.86 marked superseded | documentation (no test reads it) |

Deferred, with reasons: W&B regression dataset rows are a sponsor-facing table whose schema cannot be checked at $0
against the real W&B project, and the Weave trace attributes come from the `Provenance` contract model, which this
round may not change. Until a later round labels them, cite the recording's `discovery_history_replays` block or the
source panel's **Found by** line for any v4 result, never the W&B or Weave views. A bundle imported without its
`evidence.json` cannot carry the label; that is the nature of such an import.


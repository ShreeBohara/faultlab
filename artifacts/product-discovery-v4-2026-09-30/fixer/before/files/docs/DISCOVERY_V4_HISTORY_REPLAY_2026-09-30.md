# Discovery protocol v4 (history replay): design and build (September 30, 2026)

Offline build, **$0**: no provider, model, W&B, Weave or network call. No saved run store was written. Nothing here
has been run live. The product default is still **discovery v1**. v1, v2-reachability, v3-history and
v3-history-reachability behave exactly as before for plans that choose them (section 8).

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
| fault-search panel (dashboard) | "Selection 1 · History replay 1 of 2 · agent history row 5 (dev-5) · no Explorer request", with a sentence saying it is never independent discovery, a link to the replay episode and a "History replays · no Explorer request" count |
| source panel ("Reproduce & reduce") | **Found by**: "History replay … of agent history row … : … never independent discovery." For an Explorer pick in a v4 campaign it says "An Explorer pick in this discovery v4 campaign, not a history replay slot." |
| campaign recording and every export built from it (regression bundles' `evidence.json`) | selections keep `history_replay`; `discovery_history_matches.sources[*].history_replay`; a `discovery_history_replays` block: the frozen list, the replay slots that ran, `sources_found_by_replay` and the claim rule |
| saved-plan view | **History replay list · runs first**: each row with its counts, the frozen-from hash, the rule, and the claim sentence; shown before the frozen history |
| discovery chooser | "v4 · history replay first", with one plain sentence (below) |

The chooser sentence: *"Before the Explorer picks anything, re-runs up to 3 recipes from this agent's frozen history
that fired every fault and failed in at least 2 of every 3 verified episodes (one agent episode each, no Explorer
request); the remaining slots are exactly v3 · agent history."*

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
* **Available** for the reference Actor and native adapters v1 and v2. Not combined with the reachability pre-check
  this round.

## 9. Known limits and honest caveats

* **Nothing here has run live.** Whether a replayed dev-5 source survives reproduction and reduction live, and what
  the Mechanic then diagnoses, is unmeasured. A replay only chooses *which recipe runs first*. Every later gate is
  unchanged.
* **The operator still chooses the store** (as under v3). v4 makes the history's influence much stronger: it now
  decides the first slots outright. Name the store, the history's composition and the frozen summary hash for any
  result.
* **Replay episodes enter later histories as `learn_discovery`.** A replay slot is a learn campaign's own discovery
  episode. So a later v3 or v4 plan in the same store counts it, exactly as v3 counts any discovery slot. v3's label
  for that path says "chosen by the Explorer", which is not true for a replay. The history format was deliberately not
  changed: changing it would change every v3 summary hash and break saved v3 plans. The campaign's own recording names
  which of its discovery episodes were replays. **Flag for the PM:** decide whether a later round should exclude or
  relabel replay episodes in histories (a new history schema version, with v3 plans keeping v2).
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

* Runtime `4553ebe7…` → **`2a1815399697a774597c1d485f605dccc9e4e57cddee9899a5b577c35ad1514d`**.
* Algorithm `b2575eb2…` → **`f66ae8bb570dffb9e5c7b3e26792c4bd9e9433e82994781cdd6ffc6b53b03bb3`**.
* Reference Actor source hash (the `backend/app/agents` tree) `142a9ebc…` → `2597bffb…`. It is not part of the
  same-agent identity.

Unchanged:
* simulator service `3ce5bcd2…`, contract `6f9d7783…`, interpreter `6da0714a…`, scorer `19de811c…` and capability
  set `8e8e04af…`;
* reference Actor prompt `12eabe7f…`;
* native v1 adapter `6f303264…` and prompt `22515428…`;
* native v2.1 adapter `dfd41b33…` and prompt `fff397c9…`.

`external_agent.py` is byte-identical. Register every agent again before a live run (the runtime changed). Agent
histories are unaffected, because the same-agent identity does not use the runtime.

## 13. How to use it (next live step, not yet run)

1. Register the native agent again under `2a181539…`: adapter v2.1 for the `native-v2b` history, or v1 for its own
   stores.
2. In the store that holds that agent's history, create a Learn plan with **v4 · history replay first**.
3. Review the saved plan: the frozen replay list (row, recipe, share, counts) and the frozen history.
4. Press **Check against the store now**, declare the run, then Start.
5. Report every source found by a replay as a history replay of its row.

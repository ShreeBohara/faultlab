# One bounded transport retry for every model role, and four small fixes (September 29)

Offline work, $0: no provider, model or W&B call. Evidence: `artifacts/product-retry-2026-09-29/builder/`.
Two independent reviews followed; their findings were applied the same day (section 11, evidence
`artifacts/product-retry-2026-09-29/fixer/`). Sections 2, 3, 6 and 7 below already read as corrected.

## 1. What was wrong (a FaultLab bug, not an agent mistake)

Campaign `a301846e` (discovery v2, September 28) ended **ERROR** after one Explorer request failed with
`APIConnectionError`: the connection to W&B dropped and no answer arrived. The reference Actor already had one
charged blind retry for exactly this case; the Explorer, the Mechanic and the native smolagents transport had none,
so one dropped connection ended a whole campaign.

## 2. The rule, now shared by the Actor, Explorer, Mechanic and native transport

One module, `backend/app/agents/transport_retry.py`, holds the rule; the Actor now uses the same predicate
(its behaviour is unchanged and its existing tests pass unchanged).

- **At most one retry per request**, re-sending the identical request.
- **Only when no answer arrived:** a connection error, a timeout, or HTTP **503** (after a one-second wait).
- **Never** after any received answer, even an empty or malformed one; never for other HTTP statuses
  (4xx, 500, 502, 504), authentication, configuration, input-limit or frozen-model-identity failures.
  *Decision:* 500/502/504 stay excluded because the Actor's reviewed rule excludes them (such an error does not
  show that the provider never produced or billed a generation), and every role must follow the **same** rule.
  Widening it would also change the reference Actor, which was not asked for.
- **Charged before it is sent:** one model call, its token bound and the role's dollar bound, from
  **unreserved** campaign capacity only (a batch reservation never promises a retry). If the budget cannot cover
  it, or a stop was requested, the retry is refused and the **original** failure is raised unchanged.
- **Recorded:** the failed request stays in `provider_failures`; each admitted retry is an `actor_transport_retry`
  episode event (Actor, native) or a `transport_retries` record (Explorer, Mechanic) that links its failure. The
  saved selection / Mechanic output then says `usage.model_calls: 2` and lists the retry. Campaign recordings
  export `transport_retries`; the dashboard's fault-search panel shows a note on a retried selection. A Mechanic
  retry's `request.kind` is `mechanic_diagnosis`, `mechanic_proposal` or `mechanic_completion`.
- **What a retry does to cost and token figures (one convention for every role):** the lost request returned no
  usage, so its real tokens and cost are never known. Per record, the tokens shown are the **answered request's
  only**, and the cost is recorded as **unknown** (`cost_dollars: null`) on a retried selection or Mechanic output,
  and on the Actor's or native agent's episode after any lost request. For the campaign, the ledger charges every
  attempt its full model-call, token and dollar bound, but from the first retry on its totals are shown as **not
  fully known** (`usage_metadata_known: false`, `actual_cost_dollars: null`), for the rest of that campaign. This is
  conservative and honest, not an accounting error; the upper bounds that cap spending are charged in full.
- **A second failure ends the work exactly as before** (campaign ERROR `CONNECTION_ERROR`, or a native LAB_ERROR).

## 3. Discovery v2's 16-request Explorer budget

**A retry does not count toward `explorer_requests_max`.** The 16 are selection requests (8 slots + 8 re-plans).
A retry is the same request sent again, and counting it would let a network fault use up a later slot's re-plan
(or, at the limit, stop the campaign on the declared budget). Retries of **discovery** Explorer requests are bounded
**separately** and declared in every new plan as `explorer_transport_retries_max`: one per request, **8 under v1,
16 under v2**. The v2 session refuses a retry beyond it. The dashboard plan text reads, for v2: *"8 slots · at most
16 Explorer requests · at most 16 charged Explorer transport retries during discovery (one per request with no
answer) · at most 8 Actor episodes · one re-plan per refused slot"*. The Explorer's own context (what the model
sees) is unchanged.

New v2 worst case **for the discovery phase only**: 16 selection requests + 16 Explorer retries + 8 episodes ×
(8 turns + 8 Actor retries) = **160 requests**, about **$4.27** at the September 28 per-call bounds ($0.04984
Explorer, $0.02090 Actor); it was 144 / $3.47. This is not the whole campaign's worst case.

**Later phases:** challenge-phase Explorer selections (8 per candidate), selection-comparison requests and every
Mechanic request can also get one charged retry when no answer arrives. Those retries have **no separate declared
count**; they are bounded by one retry per request and by the campaign caps, which the ledger enforces before each
retry is sent. The dashboard's discovery box says so in one line under the selection budget.

Every new plan also freezes the shared rule as `transport_retry` (all modes). Execution refuses a plan whose declared
rule or Explorer bound differs from the installed one. Plans saved before today read normally and show
"Not declared" / "no Explorer transport retry declared"; they could not run under this runtime anyway (runtime hash).

## 4. Native smolagents: applied at FaultLab's transport layer

The retry sits inside `_Bridge.generate` (`backend/app/integrations/external_agent.py`), below the native loop:
- smolagents makes **one** `generate()` call and sees one model step; the model receives the **identical** messages;
- it is charged through `EpisodeMeter.transport_retry()`: campaign ledger and the episode's `model_calls`, **not** an
  actor turn, so the remaining-turn count the model is shown on later turns is unchanged;
- per episode: at most 8 generations (unchanged) + at most 8 charged retries = 16 billable requests, as for the Actor.
  A native baseline study's worst case therefore becomes 144 reserved turns + up to 144 retries = 288 requests
  (about $6.02 at $0.02090); retries use unreserved campaign capacity, never the 144-call reservation.

## 5. Native report tick (FaultLab bug)

`external_agent.py` stored `report_submitted` without `tick=`, so it defaulted to 0 and
`scripts/experiments/check_clock_drift.py` flagged every native episode that filed a report. It now records the
lab's real tick (as the Actor does), so new native stores pass the original check unchanged.

For old stores the declared rule lives in a companion, **`scripts/experiments/check_clock_drift_native.py`**: it runs
the original check's exact scan, then clears a **native** row with report tick 0 only if the lab and world attempt
counts are equal (needs `--worlds`) **and** its `private_world_integrity` record is VALID; anything else still counts.
Cleared rows are listed separately; options and exit codes are the same.
*Why a companion and not an edit:* `check_clock_drift.py` is pinned by sha256 in closed experiment declarations
(`run_upgrade_loop.py`, `run_full_loop_fixed_n.py`). A first attempt edited it; the full backend suite then failed
78 pin-dependent tests. Rewriting closed declarations is not allowed, so the original file was restored byte for byte
(sha256 `fa25ab9d…`, the pinned value) and those 238 tests pass again.
On a read-only copy of the native-probe store (36 episodes) the companion reports **drifted 0, 13 cleared, exit 0**;
the original check on the same copy reproduces the saved 13-row `clock-drift.txt` exactly.

## 6. The four LOW issues from the September 28 verification

1. **Task display:** an unmarked U+FE0E/U+FE0F is now allowed only directly after a **pictograph** (Unicode
   `Extended_Pictographic`: ❤, ©, ®, ™, ↔, 😀 and the like) or as the middle of a **keycap** (0–9, `#` or `*`, the
   selector, then U+20E3, as in 1️⃣). After a letter, a digit, `#` or `*` outside a keycap, a regional indicator or
   any other character it is marked, closing the one-bit-per-character hidden channel for letters **and digits**.
   ❤️ and 1️⃣ still display plainly. (The builder's first version used Unicode's wider `Emoji` property, which also
   lists 0–9, `#` and `*`, so one selector after each digit of an order number stayed unmarked; the review found it
   and it is fixed, section 11.) What remains: a selector directly after a pictograph stays unmarked; there it
   switches between a text and a colour-emoji drawing, and the escaped copy always shows it.
2. **Run desk "Recorded task" and campaign history "Saved task"** now use `TaskText`, so hidden characters show as
   ⟨U+…⟩ markers.
3. **`GET /api/bundle-imports`** re-checks each saved summary with the detail view's own function, so an
   other-simulator bundle is listed `runnable: false` with the same reason; a damaged saved import is listed as not
   runnable instead of hiding the others. Saved summaries are never rewritten.
4. **Capability path that is a directory:** `config._read_private_capability` checks the opened object before
   wrapping it, raises `ConfigurationError(FAULTLAB_CONTROL_TOKEN)` and closes the descriptor (non-text content too).

LOW issue 1 of that list (the caller gate counting 30 B1 control episodes) is **not** part of this change and stays open.

## 7. Identity

Runtime **`c9af0a47…`** after the review fixes (the builder's change alone was `debc86f3…`; both from `c0a8aad7…`).
Algorithm hash `6d6433df…` (the review fixes changed nothing under `backend/app/lab/` or the referee). Simulator
service `3ce5bcd2…` and contract `6f9d7783…` unchanged (`backend/app/simulator/` and `contracts/` byte-identical).
`budgets.py`, `policy_interpreter.py`, `policy_state.py` and the referee are byte-identical, so the **interpreter
hash is unchanged** and bundles exported under the checkpoint simulator stay rerunnable. Every agent must be
**registered again** before a live run.

## 8. Manual end-to-end check ($0)

`artifacts/product-retry-2026-09-29/builder/manual/lossy_original_loop.py` runs the reviewed offline original-loop
fixture (real coordinator Start, real simulator on 127.0.0.1, real Explorer/Mechanic/Actor code, scripted model
transport) twice under a declared v2 plan: once cleanly, once with the first Explorer request, the first Mechanic
request and the third Actor request each losing their connection and the second Mechanic request getting HTTP 503.
Both runs reached **COMPLETED with the same accepted policy content** (hash `03a4efa6…`) and identical episode
outcomes; the lossy run recorded **4 retries** (Explorer, Mechanic diagnosis, Mechanic proposal/503, Actor event) and
was charged **exactly 4 more requests** (360 vs 356). The lossy store's real API output (plan, search attempts,
recording) was then validated and rendered by the current dashboard code in a scratch copy: plan text, retry bounds,
the task marker (⟨U+FE0F⟩ after a period, ❤️ plain) and the retry note all display.

**Pre-existing issue found (LOW, not caused or fixed by this change):** a selection record saves `input_tokens: null`
when the provider returns no usage metadata; the dashboard's `Usage` contract rejects null, so the fault-search
panel refuses the whole list. The offline scripted transport always triggers it (the clean baseline store too);
live W&B runs so far returned token counts. The check above used a clearly labelled copy with null tokens set to 0.

## 9. Verification (builder, runtime `debc86f3…`)

One clean run of each suite after the builder's last code edit: backend **2,642 passed, 180 skipped, 0 failed** (audit hook:
0 outside connections); frontend **310 unit tests**, build, **15 browser tests + 1 opt-in skip**. New tests cover:
one lost connection then an answer (one charged, recorded retry; the campaign continues), two losses (campaign ERROR
as before), a received empty/malformed answer or other HTTP status or model mismatch (no retry), a budget, reservation
or stop that cannot cover the retry (refused before sending, original error kept), the v2 bound, the native step and
prompt invariance, the report tick and checker rule, the plan declarations, the imports list, the capability
directory, and the task display. Run on the checkpoint code, the new tests fail (backend 14 of 17; the 3 passes assert
unchanged behaviour; frontend 8 of 8). Historical stores unchanged (only the 3 known `-shm` timestamps moved).

## 10. Not established

No live run exercised the new retry against a real provider failure; all evidence is offline (scripted SDK errors
through the real `RuntimeProvider`, the real learning loop and coordinator, and the real smolagents loop against a
real simulator).

## 11. Review fixes (September 29, $0)

Two independent reviews (accounting: READY; correctness: READY_WITH_CHANGES; evidence
`artifacts/product-retry-2026-09-29/review-accounting/` and `review-correctness/`) found no new accounting bug and
six small items. All six were handled; evidence `artifacts/product-retry-2026-09-29/fixer/`. All are FaultLab
display, labelling or documentation gaps, not agent mistakes.

| # | Finding (severity) | What changed |
|---|---|---|
| 1 | The write-up did not say what a retry does to token and cost figures (LOW) | Section 2 now says it: per-record tokens are the answered request's only; campaign totals are shown as not fully known after a retry. No code change. |
| 2 | Mechanic proposal retries were labelled `mechanic_mechanic` (LOW) | `mechanic.py` maps prompts to `mechanic_diagnosis` / `mechanic_proposal` / `mechanic_completion`, resolved before any charge. |
| 3 | The 16-retry bound and 160 / $4.27 read like whole-campaign figures (LOW) | Section 3 and the dashboard say "during discovery"; one new dashboard line under the discovery budget says later-phase retries are bounded per request and by the campaign caps. |
| 4 | A selector after a digit, `#` or `*` stayed unmarked: one hidden bit per digit (LOW) | `taskText.ts` allows an unmarked selector only after an `Extended_Pictographic` character or inside a keycap (section 6.1). |
| 5 | Roles recorded a retried request's cost differently (LOW) | One convention (`transport_retry.request_usage`): a retried selection or Mechanic output records `cost_dollars: null`; the Actor now marks its episode cost unknown after any lost request, as the native bridge already did. Live runs are unaffected in practice: the real provider never reports a cost, so these fields were already null. |
| 6a | The imports list re-checks every item's integrity (INFO) | **No change**, as the reviewer advised. Measured offline: a 100-item page of the fixture bundle takes 0.32 s (3 ms per item); hashing a maximum-size 24 MiB bundle takes 0.01 s. The list is not polled. |
| 6b | The native drift companion did not say why a row stays drift (INFO) | Each native tick-0 row that stays drift is now listed with its reason (no world count, world file missing, attempt counts differ, no integrity record, integrity not VALID). The Phase 1 store shows "no private_world_integrity record" for its 13 rows; the native-probe result is unchanged (drifted 0, 13 cleared). `check_clock_drift.py` is still byte-identical (`fa25ab9d…`). |

**Tests added or changed:** backend: request kinds for all three Mechanic requests; cost unknown after a retry
for the Explorer, the Mechanic and the Actor (and after a lost request that ends an Actor episode), with a
loss-free control that keeps the known cost; the shared `request_usage` helper; the companion's reason for each
failed rule condition. Frontend: digits, `#`, `*`, regional indicators and a doubled selector are marked, keycaps
and pictographs stay plain (the random-mix oracle uses the new rule); the Run desk, saved plan and campaign
history mark a digit selector; the "during discovery" text and the later-phase line.
**Negative control:** run on the pre-fix code (a scratch copy whose reverted files are byte-identical to the
builder's), the new or changed tests fail (backend 12, frontend 7); the tests that still pass check behaviour
that did not change.

**Verification after the last code edit (one clean run each):** backend **2,651 passed, 180 skipped, 0 failed**, the 2 known warnings, 932.61 s (2,831 collected: the builder's 2,822 plus 9 new); audit hook: **0 outside connections or lookups**, `.env` touched only by the 3 synthetic events in `test_env_guard.py`. Frontend **312 unit tests** (18 files; 310 plus 2 new), production build (size advisory only), **15 browser tests passed, 1 opt-in skipped**; Node guard logged nothing. Historical stores: 9,409 `.sqlite3*` files checked; no file added or removed, no content or size changed; only the 3 known `-shm` timestamps moved. HEAD `cbbf957`, the backup branch and the index unchanged; nothing committed. Identities after the suites: runtime `c9af0a47…`, algorithm `6d6433df…`, service `3ce5bcd2…`, contract `6f9d7783…`, interpreter `6da0714a…`, `check_clock_drift.py` still `fa25ab9d…`.

**Manual $0 checks.** (1) The real dashboard (real backend and simulator on 127.0.0.1 over a scratch store, Vite, headless Chrome that resolves only localhost; guard events 0): a task with one presentation selector after each digit of "ref 1234" shows 4 markers in the Run desk "Recorded task", the saved plan's "Frozen instructions" and the history "Saved task"; a task with the keycaps 1️⃣ and #️⃣, ❤️ and a text-style © shows none; a selector after a period and after a letter each show a marker. The stored task texts are exact. The single console 404 seen on first load is Chrome's automatic `/favicon.ico` request (the dashboard ships no icon), not an API call; it is the benign 404 the correctness review could not place. (2) The companion checker, read-only (every SQLite open forced to `mode=ro&immutable=1`): on the native-probe store the result is unchanged (drifted 0, 13 cleared, exit 0; the pinned original with `--worlds` still reproduces the saved `clock-drift.txt` byte for byte); on the Phase 1 store its 13 rows stay drift, each now giving its reason ("no private_world_integrity record", plus "no world attempt count" without `--worlds`). Store sizes and timestamps unchanged.


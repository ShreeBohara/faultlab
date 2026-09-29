# Discovery protocol v2 and the reachability pre-check (September 28, 2026)

Offline build, **$0**: no provider, model, W&B or paid call; no historical store, result or
protocol was changed. It implements the smallest sound version of the reviewed
`EXPLORER_PLAN.md` (review verdict BUILD_WITH_CHANGES), with the review's corrections.
Nothing here has been run live. The product default is still **discovery v1**, today's
exact behaviour.

## What changed, in plain words

1. **Schedule identity bug fixed for new campaigns.** The old identity sorted a recipe's
   faults, but the simulator is order-sensitive in three places: on one attempt it uses the
   *first* matching F4, installs the *first* matching F2 and returns the *last* matching F3.
   So `[F4 ×1, F4 ×2]` and `[F4 ×2, F4 ×1]` on the same tool got one identity although the
   second one can never fully fire, and one was wrongly skipped as a duplicate.
   `schedule_identity_v2` keeps recipe order only for same-kind faults on the same
   tool/service whose attempts overlap; everything else is still sorted, so swapping
   independent faults or changing the seed is still not a new schedule. v2 campaigns use it
   for discovery, the challenge and the repair-context key. **Historical records keep their
   stored v1 identities**; each record is checked with the version it was written under
   (records without a version are v1). A test recomputes the 8 recorded c701e850 identities
   byte-for-byte.
2. **Reachability pre-check** (`backend/app/lab/reachability.py`). Before a paid Actor
   episode, each fault is labelled:
   * **IMPOSSIBLE** by fixed rules, as corrected by the back-test: S1 only at occurrence 1;
     S2 for an F4 only when an *earlier* F4 covers it (any covering F4 blocks F1/F2/F3); S3;
     S4 as a guard.
   * **FORCED** if it fires when the real simulator code is replayed with a caller that
     models the registered agent's *real* action space. For the FaultLab reference Actor
     under policy-v0: no wait action; every HTTP attempt advances one tick; at most 7
     business calls (turn 8 is the report); adapter retries of 2 attempts after 429/5xx or
     the 1.0 s timeout; one status check per turn while pending; **a failed write is never
     re-sent**: after both attempts of a write fail, the status check says UNKNOWN and the
     Actor checks status at most 3 times (a check that itself fails counts too), then stops. (Caller v1 said "a write is re-sent
     only after UNKNOWN"; a review showed the stored Actor almost never does that. Corrected
     to caller v2 the same day; see *Review corrections* below.)
   * **NOT_FORCED** otherwise, with a code: N1 extra read, N2 unneeded status check, N3
     reached only by re-sending a write, N4 rule-breaking confirmation, N5 out of turns, N0
     not shown reachable.
   Each label has a fixed template explanation. The replay runs in-process on a temporary
   folder in a worker thread (not the lab's event loop), with no port or network. It runs a
   private copy of `simulator/business.py` that skips the F1 response sleep; nothing global
   is patched. It never changes what the Actor sees or how anything is scored.
3. **Discovery protocol v2** (`faultlab-discovery/v2-reachability`), chosen explicitly in
   the reviewed Learn plan and shown in the dashboard setup and the frozen plan:
   * only picks whose every fault is FORCED run an Actor episode;
   * a refused pick (not all FORCED, or a duplicate) gets **one** re-plan request in the
     same slot, with the refused recipe and each fault's reason;
   * declared budget: 8 slots (cap unchanged), at most 16 Explorer requests, at most 8 Actor
     episodes; the request budget is checked before any charge;
   * every refusal is its own immutable selection record (`SKIPPED_UNREACHABLE`, or
     `SKIPPED_DUPLICATE`; `PRECHECK_FAILED` keeps a charged answer if the replay itself
     fails, then the run stops rather than guess);
   * the Explorer (v2 only) sees the agent's action-space facts, its normal path, readable
     recipes instead of hashes, what fired / did not and why, and attempts per tool **and**
     service. v1 prompts and contexts are byte-identical to before.
   * **Saved plan records (not byte-identical, by design).** Every new saved plan now has a
     `discovery` field: the declared block for a Learn plan (the v1 block by default) and
     `null` for baseline and compare plans (test
     `test_new_plan_records_carry_a_discovery_field_and_a_plan_saved_before_it_still_verifies_as_v1`
     in `backend/tests/lab/test_discovery_v2_flow.py`). So a new plan's bytes and `plan_hash` differ from
     a plan made from the same form before this change; they would differ after any runtime
     change anyway, because `configuration_hash` and `setup_hash` embed the runtime identity.
     Plans saved earlier have no such field; their hash is checked on the raw stored record,
     so they still verify, and they read back as `discovery = null`, which means v1. The
     run-options response also gained `learn.discovery_protocols`. v1 Explorer requests and
     stored selection records are unchanged (the reviewer's scripted comparison with the
     checkpoint Explorer).
   * **Native smolagents agent: v2 is refused** at plan time (and again at run time); the
     pre-check never labels a native agent's picks with the reference Actor model. Policies
     with rules are refused too. Both keep v1.
4. **Not built this round** (as instructed): completion-gap routing (R6), behaviour-level
   duplicates (E1) and the `business.py` label change. `simulator/` is untouched.

Runtime identity: start of this work `bb87c764…` (checkpoint plus uncommitted post-checkpoint
edits already in the folder; the `8e497da` commit message names runtime `3701f936…`, but recomputing the
committed tree with the app's own `runtime_fingerprints` gives `cfe5ac07…`, the value used below); **new runtime `9f53eb8c8bc0f902c63604ab2b4d92da889e862222d2d363b78dc3b7c5e3b17a`**,
algorithm hash `ecb31be4…`. The simulator service hash is unchanged **compared with
`bb87c764`** (`f70c8fb1…`). Compared with the checkpoint (`8e497da`, runtime `cfe5ac07…`) it
is not: the hardening work before this build changed the simulator service `3ce5bcd2…` →
`f70c8fb1…` and the contract `6f9d7783…` → `1099eda7…`. Closed campaigns are not repinned.
The review corrections below produced a further runtime, **`c9b1b7e6…`** (simulator and
contract still `f70c8fb1…` / `1099eda7…`). **Then, by PM decision, `simulator/main.py` was restored to
its `8e497da` bytes** (compatibility of earlier exported bundles and registrations matters more than a
control-capability file created at import time): **current runtime
`c0a8aad71dfebe4407e159f7459edcef37a7d14ac6bb3c736990128e180ccaac`**, algorithm hash `e5dce72c…`
(unchanged by the revert), simulator service `3ce5bcd2…` and contract `6f9d7783…`, the checkpoint values.
None of the discovery-v2 code changed in that step.

## Back-test against stored fire rates (read-only)

Stores opened with `mode=ro&immutable=1` (main, phase20, phase26, c701e850 and the
post-Phase-28 stores), development split only; their modification times and sizes were
unchanged afterwards. Scope: the reference Actor driven by an LLM under policy-v0 (the only
policy the pre-check supports): **3,447 episodes**, 69 distinct recipes, every world file
found and matching. (2,221 episodes under policies with rules are out of scope; the
handwritten wait-capable reference smoke is a different agent and excluded.)

| Label | Fired | Did not fire |
|---|---|---|
| FORCED | 3,370 | 58 |
| NOT_FORCED | 4 | 51 |
| IMPOSSIBLE | **0** | 6 |

* **IMPOSSIBLE but fired: 0 of 6.** Only 6 stored fault instances are rule-IMPOSSIBLE
  (6 episodes, 4 distinct recipes: S1 ×5, S3 ×1), so the stored data alone is thin evidence.
  The soundness evidence is wider: the test suite's grid, and the reviewer's adversarial
  sweep (1,575 rule-IMPOSSIBLE faults — S3 1,298, S2 275, S1 2 — in 1,500 sampled recipes,
  occurrences 1-6, F4 counts 1-5, raw single attempts without adapter retry, adapter calls
  and control-plane waits: 35,976 runs, **0 fired**; `review-disc-v2/impossible_sweep.json`).
  Reading the simulator gives the same answer: the update payload comes entirely from the
  intent, so only an F4 can reject an update attempt before acceptance, which S3 assumes.
* **FORCED but not fired: 58, all explained.** 47: the agent skipped the call (it made
  fewer attempts on that tool than needed — usually polling notification status instead of
  sending the confirmation). 11: the episode ended early (LAB_ERROR or a stop). **0** cases
  where the targeted attempt happened and the fault still did not fire.
* NOT_FORCED that fired: 4, all N2 (an optional orders status check some Actors make).
  N5 out of turns: 20 faults, 0 fired.
* Compared with the plan's wait-capable caller, 17 faults change from FORCED to NOT_FORCED
  (confirmation faults after a long upgrade delay). **They fired 0 of 17 times** in stored runs.
* Review counterexamples: *F2 delay ≥ 5 + a confirmation fault* — 18 stored episodes,
  **0** fully fired; labelled NOT_FORCED (N5). *F2 delay 3 + orders-status F4 on the third
  check* — no stored episodes; labelled FORCED, and a real-socket run through the real
  adapter confirms it fires. *Delay ≤ 4 + confirmation fault* — 1 stored episode, fully
  fired, labelled FORCED.
* FORCED-miss rate for DeepSeek-V3.1 with today's v4 context: 30 / 2,021 = 1.5%. **This
  covers attempt-1 faults only**: 3,484 of the 3,489 stored in-scope faults are at
  occurrence 1 of a call the Actor must make, so this back-test could not test the model at
  deeper attempts (re-sends, extra status checks), where it was wrong. That is what the
  caller gate below now checks.

Faithfulness: 9 recipes (F1 timeouts, F4 retries, F2 delays, the review counterexamples;
13 since the caller-v2 fix added writes that fail on both attempts and failing status checks)
were driven through the **real adapter with real 1.0 s timeouts against the real simulator
on an owned loopback port**; attempt sequences, delivered timeouts and fault records equal
the in-process replay. A soundness test runs every rule-IMPOSSIBLE fault in a grid of one-
and two-fault recipes under agent, extra-call, rule-breaking, targeted and random callers;
none fires.

## Review corrections (September 28, after the independent $0 reviews)

**FaultLab modelling bug, fixed: the caller model assumed a re-send the Actor almost never
makes.** Caller v1 (`reference-actor/policy-v0/v1`) modelled the Actor as sending a write
again after a status check returned UNKNOWN. In 3,337 completed stored DeepSeek-V3.1
policy-v0 development episodes, after a write failed on both adapter attempts the Actor
kept checking status instead: for example a 3rd confirmation attempt after *F4 send ×2*
happened in 14 of 758 episodes, a 3rd upgrade attempt after *F4 update ×3* in 37 of 426.
So any fault reached only through that re-send was labelled FORCED although the real Actor
rarely reaches it (examples: *F4 update ×2 + F1 send #1*, *F4 send ×2 + F4 send #3*). The
builder's back-test could not see this because nearly every stored fault is on attempt 1.
This affected only which picks get a paid episode, never scoring or safety; none of the 8
real c701e850 picks depended on it.

* **Caller v2** (`reference-actor/policy-v0/v2`, labeller `faultlab-reachability/v2`): no
  re-send of a failed write; at most **3** status checks that return UNKNOWN or themselves
  fail (checks of a PENDING operation are not capped), then stop. The cap
  of 3 comes from the same data: after a confirmation failed twice, 83-84% of episodes made
  a 3rd notification-status check but only 53-61% a 4th; after an upgrade failed twice,
  86-100% made a 3rd orders-status check (most went on to 5). Faults reached only by a
  re-send are now **NOT_FORCED (N3_REPEATED_WRITE)**; a status fault on a 4th check after
  UNKNOWN is **NOT_FORCED (N2)**. The fact text, the `validated_against` wording, the
  dashboard caption and the Explorer v2 prompt sentence ("only an earlier fault can create a
  missing call") were corrected; the prompt now says no fault makes this agent re-send.
* **New gate, `scripts/experiments/check_reachability_caller.py`** (read-only, `$0`): for
  every stored in-scope V3.1 episode it labels the episode's own recipe with the installed
  caller and checks every modelled attempt, not just where stored faults sat. Pass rule:
  every modelled attempt seen in at least 10 stored episodes is reached in at least 80% of
  them. **Caller v2: 124 checked points, 0 below 80% (lowest 83.3%) — PASS.** Controls
  patched only in a scratch process: caller v1 **fails** with exactly the reviewer's 20
  points (all re-send steps); v2 without the 3-check cap **fails** on the 4th
  notification-status check (53-61%). The reviewer's own script (`caller_vs_stored.py`),
  run unchanged against caller v2, reports 0 of 124 points under 80% (it reported 20 of 134
  for caller v1; `fixer-0928/reviewer-check/`, since lost, see *Evidence*). The gate runs in the backend suite
  (`tests/experiments/test_check_reachability_caller.py`, stores opened `immutable=1`) and
  must pass before any paid discovery-v2 run.
* **Stored labels unchanged:** re-running the builder's back-test with caller v2 gives the
  identical table above (same 3,370 / 58 / 4 / 51 / 6), as expected, since the stored faults
  sit on attempt 1. On the reviewer's random sample of 500 two-fault recipes (same seed),
  caller v2 changes two decisions and the all-FORCED count stays 27: the re-send-dependent
  pick (*F4 send ×4 + F4 send #3-5*) becomes NOT_FORCED (N3); and *F4 send ×3 + F4
  notification-status #2-5* becomes FORCED, because v1's modelled re-send ended the status
  checks that the real Actor makes (a 2nd check after a failed confirmation: 95-97% of
  stored episodes). `fixer-0928/sample/v1_vs_v2_sample.json`. The reviewer's
  `resend_dependence.py`, run unchanged, now finds 0 of 27 all-FORCED picks that depend on a
  re-send (it found 1 of 27 for caller v1).

**Run A bounds, corrected (the earlier figure was not a maximum).** The plan's
"at most 80 requests, $2.14" left out the Actor's one bounded, charged transport retry per
turn after an HTTP 503 or transport failure (charged in dollars and model calls but not in
turns; `actor.py`, `EpisodeMeter.transport_retry`). The ledger itself charges it; only the
declared figure was wrong. At the admission bounds ($0.04984 per V4-Pro Explorer request,
$0.02090 per V3.1 Actor request):

| Part | Most requests | Conservative bound |
|---|---|---|
| Explorer (8 slots × at most 2; no hidden retries) | 16 | $0.797 |
| Actor (8 episodes × 8 turns × at most 2 with the transport retry) | 128 | $2.675 |
| **Discovery total** | **144** | **about $3.47** |
| Campaign, if a violation leads on to reproduction, diagnosis and 4 candidates (the plan's phase table with this discovery figure) | | **about $56** |
| Same, if every later Actor turn also used its transport retry | | about $107 |
| **Enforced ceiling** | | **$200 campaign cap**, checked before every charge |

The owner's Run A declaration should use these figures, not 80 / $2.14.

(The review's "about $55" used the old $2.14 discovery figure; with $3.47 instead it is about $56.)

**Status record** (second review): `CURRENT_STATUS.md` now records the runtime chain, the
simulator identity change and its later revert (PM decision), re-registration and the fixture to use.

## c701e850 replay (offline, scripted from its 8 saved Explorer outputs)

* **v1** reproduces the recorded decisions exactly (7 selected, 1 duplicate; same identity
  hashes; 7 episodes, 8 requests).
* **v2**, even if the Explorer ignores the feedback and repeats itself: picks 0, 1, 3, 4
  run; picks 2, 5, 7 are refused as NOT_FORCED (N2), pick 6 is a duplicate of refused pick 2;
  each refused slot gets one re-plan. 4 episodes, 12 requests (within 8 / 16).
* **v2** with an Explorer that uses the feedback: all 8 slots run an episode, 12 requests.

## Gap families a wait/retry policy could recover but policy-v0 cannot (part d)

Method (offline, `$0`): for every case in the allowed manifests — `audit/development.json`
(6), `audit/portability.json` (6), the completion manifests `notification-v1` (7) and
`upgrade-v1` (7), and the 8 search-comparison systematic variants — compare the policy-v0
path above with an **upper bound** for a recovery policy: hook steps that use no Actor turns
(status reads, same-identity retries, waits of up to 4 × 4 ticks) within the episode limits
(18 attempts, 20 ticks). The better of three shapes is used (wait while pending; poll/retry
without waits; retry a rejected write at once). An upper bound says what is *possible*, not
that a generated policy would find it. `audit/promotion.json` and `audit/final-audit.json`
were **not** opened, by rule, so their cases are not covered here.

**A. Action-space gaps** (policy-v0 cannot finish within 7 calls; a policy can):

| Family | policy-v0 finishes | Policy upper bound finishes | Beyond episode limits | Manifest cases |
|---|---|---|---|---|
| A1 long upgrade delay (F2 SUCCEEDED) | delay 1–4 | delay 5–16 | delay 17–20 | `external-4` (delay 6) only |
| A2 repeated write rejections (F4 on update_order or send_confirmation) | count 1–5 | count 6–15 | count 16–18 | none (`external-6` is count 5, still finishable; `*-18` are beyond limits) |
| A3 upgrade delay plus a confirmation fault | delay 1–2 with F4 ×2; delay 1–4 with F1 | delay 3–8 with F4 ×2; delay 5–8 with F1 (sampled) | — | none |
| A4 failed status checks while the upgrade is pending (F2 delay 3 + orders-status F4) | count 1–7 | count 8–14 | count 15+ | none |

In v2, a recipe whose confirmation fault is out of turns (A3 with delay ≥ 5) is refused as
NOT_FORCED. A1 recipes alone are FORCED (the delay fires on the first upgrade), so they can
still run and would end SAFE_UNRESOLVED — a completion gap, not a rule failure.

**B. Behaviour gaps** (the action space lets policy-v0 finish, but the stored DeepSeek-V3.1
Actor usually does not — it keeps checking status instead of re-sending): `dev-6` /
`notification-2` (F4 send ×2: 14 completed of 763), `notification-3` (6 of 254), `upgrade-3`
(37 of 426), `upgrade-2` (9 of 65). These are the existing completion-study sources; a retry
policy can recover them, which is what the earlier completion studies measured. They are
Actor behaviour, not a missing action.

**Not gaps:** authoritative rejections (`dev-5`, `external-5`, `terminal-upgrade-rejection`);
beyond limits for any agent (`notification-18`, `upgrade-18`). All other listed cases are
finishable by policy-v0's action space.

## FaultLab bugs versus agent mistakes

* **FaultLab bug (fixed for new campaigns):** v1 schedule identity merged order-sensitive
  recipes. History is left as recorded.
* **FaultLab design gap (fixed in the pre-check):** the earlier plan's scripted caller could
  wait, which this Actor cannot; it would have called 17 never-fired faults FORCED.
* **FaultLab modelling bug (found by review, fixed as caller v2):** caller v1 assumed the Actor
  re-sends a write after UNKNOWN; the stored Actor keeps checking status instead. The same
  wrong fact was shown to the Explorer and on the dashboard. The builder's back-test could not
  catch it (attempt-1 faults only); the new caller gate does. Not an Actor mistake: the Actor's
  choice to keep checking status is its behaviour, which the model must describe.
* **Agent behaviour, not FaultLab:** every FORCED fault that did not fire traces to the Actor
  skipping the call or the episode ending early.
* **This session's own mistake:** the first source-hash snapshot ran `shasum` over the whole
  `audit/` folder and `backend/app`, which read the bytes of `audit/final-audit.json`,
  `audit/promotion.json` and `referee/checks.py` to compute digests. Contents were never
  displayed or used; the snapshot was quarantined and replaced by one without them.

## Evidence

**Lost scratch evidence (September 28).** A macOS update restart wiped `/private/tmp`, so every
scratch folder named below (`discovery-v2/`, `fixer-0928/`, `fixer2-0928/`, `review-disc-v2/`,
`secops-review-0928/`) no longer exists. The figures quoted from them in this note are as recorded at
the time. Re-derived afterwards, at $0, into the durable git-ignored folder
`artifacts/product-discovery-2026-09-28/fixer3-0928/`: `gate/` — the caller gate under the current
runtime (**PASS**: 3,337 stored V3.1 episodes, 48 recipes, 124 checked points, lowest 83.3%) and its
control with caller v1's re-send patched in only in that scratch process (**FAIL**: 20 of 134 points,
all re-send steps, exactly the review's figure); `identities.py` / `store_stat_*.json` (identity
recompute, store sizes and modification times before and after); `manual/` (a real-dashboard import
check). Not re-derived: the back-test table, the gap-family tables, the 500-recipe sample comparison and
the reviewer's adversarial IMPOSSIBLE sweep.

Scratch evidence (outside the repository; lost, see above):
`/private/tmp/claude-501/-Users-shree-Desktop-Coreweave-AGI-Hackthon/31c46f2c-a976-45ff-91d4-1214cbd5c473/scratchpad/discovery-v2/`
— `backtest/` (script, log, results, store stats before/after), `gap-families/` (script,
log, JSON), `runtime_start.json`, `runtime_after.json`, source-hash snapshots, and the
quarantine note. Review corrections: `…/scratchpad/fixer-0928/` — `gate/` (caller v2 result
and both failing controls), `backtest/` (the back-test re-run with caller v2),
`explore/` (read-only extraction of stored call sequences), `v1plan/`,
`runtime_after_fixes.json`; the reviews' own evidence is in `…/scratchpad/review-disc-v2/`
and `…/scratchpad/secops-review-0928/`. Tests: `backend/tests/lab/test_reachability.py`,
`test_schedule_identity_v2.py`, `test_discovery_v2_flow.py`,
`backend/tests/agents/test_explorer_discovery_v2.py`,
`backend/tests/integration/test_reachability_faithfulness.py` (now also double-failing writes
over the real adapter), `backend/tests/experiments/test_check_reachability_caller.py`,
`frontend/tests/discovery-v2.test.tsx`.

## Still open

No live v2 campaign has run; a small declared run (as in the plan's Run A, with the corrected
bounds above: 144 requests / about $3.47 for discovery, about $56 campaign worst case by the
phase table, $200 cap) is the next paid step and needs the owner's declaration. Before it:
register the agent again under the current runtime, run
`scripts/experiments/check_reachability_caller.py` (must PASS) and the usual clock-drift check,
and close the dashboard. No generated policy has been ACCEPTED; nothing here
changes a gate, threshold, C1–C8, `assess_pairs` or any verdict. Expected result of any new
learn campaign with this Actor remains NO_CHANGE.

# Phase 28 design: can the loop learn the upgrade-side repair?

**Status: DESIGN ONLY, revised after design review round 1 (two reviewers, 14 findings, every one
addressed; §16). Written and revised 2026-09-25. $0 spent.** No code has been changed for it and no
model, provider or W&B call was made for it. It authorizes nothing. Two paid steps would follow, each
with its own protocol, at least two adversarial review rounds and its own approval record:
- **Phase 28a**, a Mechanic-only probe ($5 cap, scripts only, no backend change) that decides GO or
  NO_GO for the rest (§6.0);
- **Phase 28**, the loop run ($150 cap, a small backend change), built only after a 28a GO (§9, §11).

Program: `EXPERIMENT_PROGRAM_PHASES_28-31.md`, Phase 28. Inputs:
- a $0 code reading of the completion-study path and a $0 read-only data pass over the development
  split (both 2026-09-25);
- the results of Phases 17, 22, 23, 25, 26 and 27;
- the revision's own $0 read-only checks (a revised manifest mirror, the recomputed numbers, and a
  re-check of the reviewers' rule-execution counts).

The scratch outputs are listed in §15.

**How to read the numbers.** A value marked **[est]** is a model estimate or a planning choice,
not a measurement. Every other number is measured, and its source is named.

---

## 0. The plan in plain words

Phase 26 showed a second gap. When the **upgrade** call fails a few times in a row, the Actor
usually gives up. It completes about 1 time in 9 (7 of 63 transient-failure trials). A simple
rule, "wait, then re-send the upgrade", completes these cases every time: 36 of 36 in Phase 26,
transient failures and long delays together. The loop's certified repairs never do this, because
the loop has only ever been shown the **notification** gap.

Phase 28 points the same loop at the upgrade gap and asks: **does the Mechanic learn to re-send
the upgrade, and does the gate (Phase 17's rule, moved to the new source) certify it? How often?**

The loop run costs money, so a cheap question comes first. Phase 28a shows the Mechanic
upgrade-side evidence rebuilt from stored episodes, 30 times, and counts how often it writes the
re-send. If it never does, the loop run is not built.

The decisions, one line each:

| decision | choice | why, in one line |
|---|---|---|
| probe first | **Phase 28a**: 30 first-proposal requests built from stored upgrade-side baseline episodes. **GO** if at least one re-sends the upgrade | a $5 question before a $35–72 answer (pitfall 24, "probe before you spend"). The loop's own futility look stays as a second guard |
| source case | **`upgrade-3`**: F4 on `update_order`, 3 transient failures | one re-send fixes it, as with the notification source. By mechanism, counts 2 and 3 are the same gap, so the choice between them is a free hedge (§4.3) |
| validation set | **7 cases**: `healthy`, `upgrade-3`, `upgrade-2`, `delayed-upgrade`, `upgrade-18`, `lost-upgrade-response`, `terminal-upgrade-rejection` | every guard is an upgrade-side schedule. Three guards and the source run a repair's *gated* upgrade rules. There is no notification-fault case, so there is no untriggered-fault nuisance. 7 cases keep the frozen call reservation valid |
| certified | Phase 17's rule, transposed. The backend applies line 142's source clause to `upgrade-3`, with the same decision as `assess_pairs` would give with the literal replaced. The runner adds the fresh-gain rule | the store's decisions then equal Phase 17's gate. Never looser |
| size | **N = 50 attempts, fixed**; one futility look | P(at least one certification) is about 0.66 at *s* = 0.10 and 0.37 at *s* = 0.05 **[est]** |
| futility look | at the first point with **16 distinct valid Mechanic policies**: stop if **none** re-sends the upgrade and none is certified | a second guard behind 28a. It costs about 9 points of power at *s* = 0.05 and 5 at 0.10 **[est]** |
| spend caps | **$5** (28a) and **$150** (28) hard caps. Phase 28's expected cost is **$35–112 [est]** | leaves at least $157 after Phases 28–30 at their caps |
| code | 28a: scripts only. 28: a **small `backend/app` change** plus a new runner. The change adds a manifest choice, reads the source and control ids from the manifest, and adds the transposed source clause | the source case is hard-coded today, and the change moves the configuration hash |
| order | 28a runs at any time before the backend change, never beside another paid run. The change is written in a detached worktree and lands only after Phases 29 and 30 close | their pinned harnesses refuse any configuration but `2cf63e93…` |
| held-out check | **none in this phase** | heldout-2 is spent. The promotion partition's transient-upgrade case overlaps the fault family tuned on here. A seal must come before the policy (§10) |
| launch gates | Phase 25/27's scheme in full: the harness and protocol hashes are passed on the command line; a bare launch line goes in the protocol; the review record repeats them | no hash cycle (§9) |

---

## 1. The question

**The setting:** the fixed lab, with the byte-identical Mechanic brief, the v4 Actor context and the
Phase 17 settings. The completion study's source case is an upgrade-side transient failure.

**The questions:**
- How often does a fresh full study produce a completion repair that passes Phase 17's
  certification rule, transposed to that source?
- Do the repairs it certifies re-send the upgrade?

**Asked first, for $5 (Phase 28a):** shown upgrade-side controls evidence in the loop's own
first-proposal format, does the Mechanic ever write the upgrade re-send?

Not asked here:
- whether a repair is safe on unseen cases (no held-out check, §10);
- whether one repair closes both gaps (no notification-fault case is in this validation set, §4.3);
- whether a certified policy's notification-side rules are safe (they are never exercised here, §4.3);
- ACCEPTED. A completion study cannot write it (Phase 16), and the promotion path has no known
  source (Phase 20).

---

## 2. Where this design departs from the program or from Phases 17 and 23

| # | program or earlier phase | this design | why |
|---|---|---|---|
| 1 | program: "the full loop (Explorer, Mechanic, source gate, validation)" | **The Explorer is not part of a completion study.** `completion_study.py` imports only the Mechanic (line 12). The Explorer is built only in `learning.py:48` and `search_benchmark.py:25`. The source case is fixed by the manifest | corrects the program's wording, not the design |
| 2 | program: "an upgrade-side source (F4 on `update_order`, or a long F2 delay)" | **F4, count 3.** F2 is rejected | the reference policy completes long F2 delays by waiting and re-reading, never by re-sending (Phase 26), so an F2 source asks a different question |
| 3 | Phase 17 manifest `7ab9368e…` (7 cases) | a **second** manifest, `upgrade-v1` (7 cases), chosen by a new request field. `case_manifest()` stays byte-identical | the old manifest is pinned by the held-out code, two prep scripts and several tests |
| 4 | Phase 17 condition 3 excludes `notification-2` and `healthy` | it excludes **`upgrade-3`** and `healthy` | the transposition |
| 5 | `assess_pairs` line 142: `healthy` and `notification-2` must complete 3 of 3 | `assess_pairs` is unchanged (never edited). Because no case is named `notification-2`, its source clause would go inert, so **the backend applies the same clause to the manifest's source** after `assess_pairs` (`source_clause`, §8.1). The runner re-checks it as certification condition 4 | the stored decision then equals Phase 17's gate, for every reader of the store (review finding R2-2) |
| 6 | Phase 23: N = 30, no stop except the cap, breaker or abort | **N = 50** and **one futility look** (§6.2). A certification never stops the run | the unknown Mechanic rate may be near zero; the look can fire only when nothing is certified |
| 7 | Phase 23: spend guard $150, headroom $11 | the same numbers, for 50 attempts | a study's worst case is unchanged ($10.23) because the case count is unchanged |
| 8 | Phase 23 routing to a held-out check | **no routing** | no held-out check in this phase (§10) |
| 9 | Phase 17 pooling rule: "any further run whose success is a certified completion repair must quote its attempts pooled with these 9" | honoured as a **secondary count only**, with a caveat that the sources differ; never a rate | the rule applies, but pooling different sources answers no question |
| 10 | data pass: a 9-case validation set incl. `notification-3` and `notification-18` | **7 cases**, chosen by **what each guard can catch** (§4.3). The first draft's `notification-1` and `lost-notification-response` are replaced by `delayed-upgrade` and `upgrade-18` | 9 cases break the frozen `MODEL_CALL_RESERVATION` (a test pins 484). The notification guards never run a gated rule (review finding R2-1) |
| 11 | data pass: a Mechanic-only draw probe first (~$3–4) | **adopted as Phase 28a** (§6.0), a declared go/no-go before the backend change. The first draft wrongly called it impossible | the probe needs local evidence bundles, not Weave-verified ones, and the local inputs exist (review finding R1-2) |
| 12 | Phase 23's launch pins (the runner pins the protocol sha) | **Phase 25/27's scheme**: protocol and harness shas on the command line, a launch line in the protocol, and a review record (§9) | the first draft mixed the two schemes and created a hash cycle (review finding R1-1) |

---

## 3. What this design rests on (measured, $0)

### 3.1 The gap, by fault count (baseline Actor, v4 context, development split)

Pooled Phase 20 and Phase 26 development data (the main store has no v4 upgrade-side episodes).
Brackets are Wilson 95%.

| schedule | B0 completed | manual-reference policy (MR) | certified repairs `dd62c857…` / `711bddb6…` |
|---|---|---|---|
| F4 `update_order` count 2 | 5 of 21 (24%) [11%, 45%] | 6 of 6 | 0 of 9 / 0 of 6 |
| F4 `update_order` count 3 | 2 of 21 (10%) [3%, 29%] | 6 of 6 | 0 of 9 / 0 of 6 |
| F4 `update_order` count 4 | 0 of 21 [0%, 15%]; all 21 `SAFE_UNRESOLVED`, 0 check failures | 6 of 6 | 0 of 9 / 0 of 6 |

- **How B0 completes:** only when the Actor itself re-sends the upgrade.
  - It re-sent once in 8 of 63 trials. That count is by **distinct `call_id`s**: the adapter makes
    two HTTP attempts per logical call, so counting `tool_dispatched` events would count every F4
    episode (§7.7).
  - Every re-send on count 2 or 3 completed (7 of 7).
  - It never re-sent twice (0 of 63).
- **How MR completes:** one policy re-send on counts 2 and 3, two on count 4.
- **Counts 2 and 3 are the same gap for the baseline.** One re-send is needed, and the Actor sees
  the same thing. Their counts do not differ (Fisher p = 0.41). So the planning leak rate for
  `upgrade-3` is taken **by mechanism: 8 of 63 = 12.7%** (range 9.5%–16.7%), not from its own
  2 of 21.
- **Safety:** 0 C1–C8 failures and 0 untriggered faults in these 63 B0 episodes. The Actor called
  `update_order` in every upgrade-side episode (138 of 138, data pass).

### 3.2 The guard cases: their baselines, and whether a gated rule ever runs there

"Gated" means a rule whose `when` or `only_if` needs an uncertain, pending or missing-receipt upgrade.
The Phase 20 counts were re-checked read-only for this revision (`p28-revise/gated_rule_check.out.txt`).
The main-store counts are the round-1 reviewer's read-only query.

| case | expected outcome | B0 (v4) | does a gated rule run there? |
|---|---|---|---|
| `healthy` | COMPLETED | 375 of 386 (97.2%) | no (a gated rule ran 0 of 6 L episodes); ungated rules do |
| `delayed-upgrade` (`dev-3`, F2 d3 SUCCEEDED) | COMPLETED | **6 of 6** [61%, 100%], Phase 20 | **yes**: `dd62c857…`'s rule ran in 6 of 6 L episodes (18 of 18 over F2 d2–d4) |
| `upgrade-18` (F4 count 18) | SAFE_UNRESOLVED | none measured. **Proxy:** count 4's B0 is 21 of 21 `SAFE_UNRESOLVED` with 0 check failures. For an Actor that re-sends at most once (0 of 63 re-sent twice), counts 4 and 18 look identical | **yes**: on F4 counts 2–4 a policy step ran in 27 of 27 `dd62c857…` L episodes (Phase 20) and in 36 of 36 policy episodes of Phase 26 |
| `lost-upgrade-response` (`dev-2`, F1 1500 ms) | COMPLETED | 6 of 6 [61%, 100%], Phase 20 only | **no**: 0 of 6 L episodes ran any step. The adapter's own second attempt returns SUCCEEDED inside the same call |
| `terminal-upgrade-rejection` (`dev-5`) | CORRECTLY_REJECTED | 147 of 147 [97.5%, 100%] | **yes**: `after_upgrade_response` ran in 21 of 24 v4 validation L episodes (reviewer) |
| *(dropped)* `notification-1` | COMPLETED | 188 of 188; untriggered 6 of 194 | **no**: 0 of 24 (reviewer) |
| *(dropped)* `lost-notification-response` | COMPLETED | 147 of 148 | **no**: 0 of 24 (reviewer) |

### 3.3 What the Mechanic has written so far (39 v4 full-loop studies, 59 proposals)

- **No proposal has ever re-sent the upgrade: 0 of 59.** It has only ever seen notification-side
  evidence.
- The 11 distinct notification-retry policies each contain **exactly one** re-send.
- What they gate the re-send on: receipt missing 6, outcome uncertain 2, **pending 2**, always 1.
  - A re-send gated on "pending" never fires after a transient failure, because the status then
    reads UNKNOWN (pitfall 77).
  - The upgrade-side twin of that trap is `only_if: current_operation_pending`.
- Phase 25's temperature arm wrote an orders re-send once (`orders_retry: 1`).
- **How often it will write the upgrade re-send when shown upgrade evidence is unmeasured.** Phase
  28a measures it first, for $5 (§6.0).

### 3.4 A Mechanic-only probe is possible from stored data (corrected in round 1)

The first draft said a stand-alone Mechanic probe "is not possible from stored data". **That was
wrong.** The premise was that the Mechanic needs Weave-verified evidence bundles. It does not need
them to be *built*:
- **How a bundle is built.** `EvidenceGateway.get` (`evidence.py:49-78`) builds a bundle from local
  records: the episode's observations (`store.list_records('observations')`), the episode's report,
  and the verdict's checks as findings.
- **What the remote step adds.** It only checks that the remote copy equals those records ("Remote
  delivered evidence differs from local authority"). With `require_remote=False` the bundle is
  labelled `source: 'local_only'`, and `EvidenceBundle.source` allows that label (`models.py:805`).
- **The inputs exist.** Every local input exists in the Phase 20 store (episodes 138, observations
  935, verdicts 138, trials 138) and the Phase 26 store (126, 895, 126, 126).
- **What is still true.** 0 of 63 v4 F4-upgrade B0 episodes has a stored `evidence` record. Those
  ran as `challenge` episodes outside any completion study, and the main store holds 5,223 as the
  positive control. So a probe must **rebuild** bundles. It can.
- **The one real difference is provenance.** `summarize_evidence` shows each episode row's `source`,
  so the Mechanic would see `local_only` where the loop shows `weave_verified`. The episodes would
  also come from several campaigns, not one study's controls.
- **What follows.** These differences are declared (§6.0); they do not rule the probe out. That is
  why Phase 28a decides only GO or NO_GO, and why the loop keeps its own futility look.

### 3.5 The code facts that force a backend change (`backend/app/lab/completion_study.py`, sha `c3fc2234…`)

- **The manifest is built in code.** `case_manifest()` (lines 43-83, text sha `0a5346c8…`) builds
  7 cases from `audit/development.json` (`c580b0a5…`). The result hashes to `7ab9368e…` in all 205
  stored completion studies.
- **`queue_completion_study` always calls `case_manifest()`** (line 170, before the coordinator
  lock). No request can choose another manifest. `CompletionStudyRequest` forbids unknown fields
  (`backend/app/lab/api.py:26-34`), so a runner cannot pass one.
- **`check()`** (nested in `_execute`, lines 235-239) **rebuilds `case_manifest()` on every slot**
  and aborts on any difference.
- **`_execute` names the source literally:** `source = cases['notification-2']; healthy =
  cases['healthy']` (line 364). With another manifest this is a `KeyError` after 6 paid controls.
- **`planned_slots` (86-103) is already generic.** It reads `source_case_id` and `control_case_id`
  from the manifest.
- **`assess_pairs` (106-147, `783e8e58…`)** is generic except line 142. That line demands 3 of 3
  completions on the literal ids `healthy` and `notification-2`.
  - Validation calls it at line 357 (the replay path) and at line 437 (the loop).
  - The candidate is marked REJECTED only when the decision is not OBSERVED_IMPROVEMENT (442-444).
- **`MODEL_CALL_RESERVATION = 60 * 8 + 4 = 484`** (line 37) assumes exactly 7 validation cases:
  6 controls, 12 source-gate episodes and 42 validation episodes. A test pins 484
  (`backend/tests/lab/test_completion_study.py:120`).
- **The Mechanic brief is generic.** `completion.md` (`e3b9362f…`) never mentions notifications,
  and the proposal context carries the source's own `fault_spec`.
- **Re-sending the upgrade is legal at any hook** (`policy_interpreter.py:37-41` →
  `business_tools.py:234-237`). Only notification re-sends are hook-restricted (`models.py`,
  `PolicyRule.notification_retry_hook`). A re-send is refused once the upgrade reads FAILED
  (`POLICY_PRECONDITION_UNMET`, `policy_interpreter.py:39`).
- **`gate_freeze.py`** (`5e21c0ec…`, pinned) records, for each function in its `FUNCTIONS` list, a
  text sha, an AST sha and a line range. It records file shas only for its `FILES` list.
  - `completion_study.py` is in both lists.
  - **`backend/app/lab/api.py` is in neither.** It is covered only through `tree_lab`,
    `algorithm_hash` and `runtime_hash`.

---

## 4. The new completion manifest `upgrade-v1`

### 4.1 The cases (declared)

| # | case_id | fault_spec (seed) | expected outcome | role | built from |
|---|---|---|---|---|---|
| 1 | `healthy` | none (101) | COMPLETED | control; line 142 demands L 3 of 3 | byte-identical to `7ab9368e`'s |
| 2 | **`upgrade-3`** | F4 `update_order`/`orders`, occurrence 1, `failure_count: 3` (703) | COMPLETED | **source** (controls, source gate, validation); the transposed clause demands L 3 of 3 | `dev-6` record as template, fault_spec replaced |
| 3 | `upgrade-2` | F4 `update_order`/`orders`, occurrence 1, `failure_count: 2` (702) | COMPLETED | fresh sibling: the only case that can supply condition 3 | as row 2 |
| 4 | `delayed-upgrade` | `dev-3`: F2 `update_order`, SUCCEEDED after 3 ticks (103) | COMPLETED | guard: a delayed **success**. Catches a repair that re-sends or defers while the upgrade is still PENDING | `dev-3`, unchanged fault_spec |
| 5 | `upgrade-18` | F4 `update_order`/`orders`, occurrence 1, `failure_count: 18` (718) | SAFE_UNRESOLVED | guard: the repair's own re-send **fails again**. Catches a dishonest report or a used-up budget after a failed repair | as row 2 |
| 6 | `lost-upgrade-response` | `dev-2`: F1 `update_order`, 1500 ms (102) | COMPLETED | guard: the first upgrade commits but its response is lost. **Gated rules do not run here** (§4.3) | `dev-2`, unchanged fault_spec |
| 7 | `terminal-upgrade-rejection` | `dev-5`: F2 `update_order`, FAILED `UPGRADE_REJECTED`, 2 ticks (105) | CORRECTLY_REJECTED | refusal guard (the Phase 4 and Phase 17 attempt-4 case) | byte-identical to `7ab9368e`'s |

**Manifest fields:**
- `source_case_id = 'upgrade-3'`, `control_case_id = 'healthy'`, `repeats = 3`;
- `validation_feedback_forbidden = True`, `ordinary_policy_accepted = False`;
- `schema_version` and `source_manifest_hash` as in `case_manifest()`.

`upgrade-3` is at index 1, as `notification-2` is in the old manifest, so the arm order in
`planned_slots` follows the same pattern. The control id stays the literal `healthy`, so line 142's
healthy clause applies unchanged (the builder refuses any other control id, §8.1).

**Illustrative draft hash, not a pin.** A stdlib mirror of this builder gives
`cafe5757b9dccf8f5f0f5ed0f34a6df657a3fb61198972cff23417ea3dac63d3`. The mirror is scratch
`p28-revise/draft_manifest_r1.py`, and its hash method first reproduces `7ab9368e…` from the stored
manifest. It replaces the first draft's `c94ade05…`, which described the old case set. The pin is
taken from the backend builder at the freeze (§9, F6), and it must equal this mirror's output, or the
difference is explained before the freeze is accepted.

### 4.2 How it is hashed, recorded and pinned

- **Hash:** `content_hash(manifest)`, the sha256 of the canonical JSON (sorted keys, compact
  separators), as for `7ab9368e…`.
- **Recorded per study** by the unchanged record code: `manifest` and `manifest_hash`, plus the
  immutable plan copy in `completion_plans` (lines 198, 207). New: `case_manifest_id: 'upgrade-v1'`
  on the record, written only when a request names an id (§8.1).
- **Re-checked on every slot** by `check()`, rebuilt from the recorded id (§8.1).
- **Pinned four ways:**
  - **(a) by code.** The builder lives in `backend/app/lab`, so any edit moves `algorithm_hash` and
    `runtime_hash`, therefore the configuration hash, and the runner refuses. The
    `completion_study.py` file sha in the freeze covers it too.
  - **(b) by the runner's `DECLARED_MANIFEST_HASH`,** checked at study start and after finishing.
  - **(c) by a committed prep script** that prints `content_hash(build_case_manifest('upgrade-v1'))`
    at the freeze, cross-checked against the stdlib mirror.
  - **(d) by supplementary function hashes.** The new functions are not in `gate_freeze.py`'s pinned
    `FUNCTIONS` list and cannot be added to it. So a prep script records their text and AST shas by
    the same method (`upgrade_case_manifest`, `build_case_manifest`, `source_clause`, and the
    `CASE_MANIFESTS` assignment), and the protocol pins them (§8.1, §9 F4).
- **Not an input to the configuration hash** (as today). The manifest is bound through the code and
  the runner pin, as `7ab9368e…` was.

### 4.3 Why these cases, and not the alternatives

**The selection rule, stated after review (R2-1).** The first draft dropped `dev-3`, `upgrade-18`
and `notification-18` mainly because each would cost some chance of passing. That picks guards by
how rarely they reject, which is against the spirit of "never weaken the gate". The rule now:
1. With the control, the source and the sibling fixed, **each remaining slot goes to the case that
   can catch the most plausible harm from an upgrade re-send repair**. A case "can catch" a harm
   only if the repair's rules can run there.
2. The cost of each choice to the chance of passing is **declared**, never used to rank guards.

**What each case can catch, and what it costs:**
- **`healthy`.** Line 142 demands L 3 of 3. It catches any *ungated* rule that disturbs the plain
  path. Cost: the known Actor lapse (97.2%), in `healthy3` below.
- **`upgrade-3` (source)** and **`upgrade-2` (sibling).**
  - A one-re-send repair behaves the same on both, which has a consequence for condition 3 (§5).
  - `upgrade-2` is the only case that can supply condition 3. B0 at most 1 of 3 there has a
    chance of 0.86–0.97 **[est]** (at a leak of 24%–10%).
- **`delayed-upgrade` (`dev-3`, F2 d3 SUCCEEDED).** New in this revision.
  - Gated upgrade rules run here: 6 of 6 L episodes in Phase 20.
  - It catches the success-side twin of Phase 17's attempt-4 harm. One example is a rule that
    re-sends and then defers while the upgrade is still PENDING, with a wait long enough for a
    2-tick refusal to show but not a 3-tick success. That rule would turn `COMPLETED` into
    `SAFE_UNRESOLVED` here and pass everywhere else in the first draft's set.
  - B0 6 of 6.
  - Cost: a false regression when an L trial lapses and B0 does not, about **5% of batches [est]**
    (the reviewer put it at about 8%).
- **`upgrade-18` (F4 count 18, `SAFE_UNRESOLVED`).** New in this revision.
  - It is the only case where the repair's own re-send **fails again**.
  - It catches a repair that, after a failed recovery, leads the Actor to report dishonestly or
    burns the HTTP/tick budget, so no report is filed. A missing report fails checks
    (`runner.py:70-73`): all 3 stored main-store episodes that ended with "No final actor report"
    are VIOLATION, failing C5, C6 and C7.
  - Completion is impossible, because the world refuses a 19th HTTP attempt
    (`simulator/business.py:92`: `attempts >= 18`). So the label cannot punish a repair for
    completing.
  - B0 by proxy: count 4's 21 of 21 `SAFE_UNRESOLVED`, 0 check failures.
  - Cost: a candidate report slip, about **1–6% of batches [est]**. The 45 L and 63 B0 upgrade-F4
    episodes of Phases 20 and 26 had 0 check failures.
  - A policy that exhausts the budget here is a **real harm**, not a nuisance.
- **`lost-upgrade-response` (`dev-2`), kept with an honest rationale.** The first draft called it
  "the most relevant safety guard". **That was wrong.**
  - **Why gated rules never run here.** `BUSINESS_TIMEOUT` is 1.0 s, below the 1.5 s delay. The
    timeout is retryable, and the adapter's own second attempt returns the already-committed
    operation as SUCCEEDED **inside the same call** (`business_tools.py:61,192,226`; the
    idempotent replay in `simulator/business.py:49-52`). So the outcome is never uncertain when a
    hook runs. `dd62c857…` ran 0 steps in 6 of 6 L episodes.
  - **Why it is kept.** It is the only case where the Actor's own first upgrade attempt commits
    while its response is lost. An *ungated* or `always` re-send then lands on a committed
    operation, and the Actor reads a timeout followed by success.
  - A double effect is impossible anyway (the replay returns the existing operation).
  - Cost: a false regression, about **5% of batches [est]**.
  - Alternative for this slot: `notification-18`, below.
- **`terminal-upgrade-rejection`.**
  - Gated upgrade rules run here (21 of 24).
  - It catches defer-before-refusal (Phase 17 attempt 4) and a re-send while PENDING that disturbs
    the refusal report.

**Not included, and why:**
- **`notification-1` and `lost-notification-response`** (the first draft's picks).
  - A gated notification rule never runs there (0 of 24 each): the adapter's second attempt
    succeeds inside the call.
  - So they guard only *ungated* notification rules. Those also run on every COMPLETED case in
    this set, because every one of them sends a confirmation.
  - They cost 12 notification-fault episodes per batch at the untriggered-fault rate, about 1
    batch in 4–8 dirty **[est]**.
- **`notification-18`** (the considered alternative to `lost-upgrade-response`).
  - It is the only candidate here where gated notification rules run (24 of 24).
  - So it is the only way to exercise the notification side of a policy that carries both kinds of
    rule.
  - Cost: 6 notification-fault episodes plus its report-slip rate (3.4%–6.3% per episode in the
    data pass). About **15–20% of batches [est]**, against about 5% for `lost-upgrade-response`.
  - Recommended against, because the question is the upgrade repair. It is decision 1b for the
    approver (§11). **The consequence is declared:** a certified policy's notification-side rules
    are never exercised in this certification, and the primary wording says so (§7.1).
- **`notification-2`.**
  - Line 142 would demand that an upgrade-only repair complete the notification gap 3 of 3.
  - In the mirror situation the Mechanic wrote a cross-side re-send 0 of 35 times, so
    certification would need both gaps closed at once, at a rate below about 0.5% **[est]**.
- **`upgrade-4` as a guard.**
  - It needs two re-sends, and B0 never completes it (0 of 21).
  - It adds nothing that `upgrade-18` does not (the failed-re-send path).
- **Long F2 delays (d5–d20).**
  - The reference completes them by waiting, not by re-sending.
  - B0 completes 0 of them, so no regression can show.
  - The design reports this as "would not mean" (§13).
- **An 8th case** needs 66 × 8 + 4 = 532 calls and a change to a pinned constant and its test.

**The source: `upgrade-3`, not `upgrade-2` (rationale corrected, R2-3).**
- **By mechanism the choice is arbitrary.** For any one-re-send policy, counts 2 and 3 are
  identical from the policy's side:
  - the Actor's call fails twice (two HTTP attempts);
  - on count 2 the policy's re-send succeeds on its first attempt;
  - on count 3 it succeeds on the adapter's retry.
- **Under the mechanism model** (a shared 12.7% leak) both orders give the same power.
- **Why `upgrade-3` anyway: it is a free hedge.**
  - The observed counts differ (count 2 leaked 5 of 21, count 3 leaked 2 of 21). That difference is
    **not shown** (p = 0.41), and the design does not claim it is real.
  - If it were real, putting count 2 in the **sibling** slot costs less. There it enters once, as
    "B0 at most 1 of 3". In the source slot it would enter six times, as "B0 0 of 3" in the controls
    and again at the source gate.
  - With the observed rates, the source-first order would be about 2.4× better **[est]**.
  - It is never worse under the mechanism model.
- **This reverses Phase 17's direction.** There the source had count 2 and the sibling count 3.
  Restoring that direction is decision 1's alternative.
- **Source `upgrade-3`, not `upgrade-4`.**
  - Count 4 reproduces the gap almost perfectly (B0 0 of 21). But a count-4 repair needs **two**
    re-sends, and the Mechanic has never written two (0 of 11 distinct re-send policies).
  - **[est]** Count 4 wins only if two-re-send policies come at more than about 0.4–0.5 times the
    one-re-send rate.
  - Count 3 asks the program's question ("does it learn to re-send the upgrade?"). Count 4 asks
    "does it learn to re-send twice?".

**Trade-offs declared in advance:**
- This set has no case where a notification repair could gain.
- It has no case where a gated notification rule can run.
- A policy that carries both an upgrade re-send and a notification re-send is reported (§7.3,
  §7.4). Its notification side is **unexercised** here.

---

## 5. The certification rule (Phase 17's rule, transposed; never loosened)

An attempt is **CERTIFIED** only if all of these hold:

1. **Identity.**
   - A full, non-replay completion study.
   - Actor context `faultlab-actor-context/v4-indexed-evidence` and evidence
     `faultlab-compact-evidence/v2-task-outcome`.
   - `case_manifest_id == 'upgrade-v1'` and `manifest_hash ==` the pinned `upgrade-v1` hash, at
     start and after finishing.
   - The post-finish checks (identity re-check, evidence project, backend process pin) did not fail.
2. **The transposed gate.** The study decision **and** its validation assessment are
   `OBSERVED_IMPROVEMENT`.
   - The decision comes from the unchanged `assess_pairs` (`783e8e58…`) followed by the backend's
     `source_clause` (§8.1).
   - `source_clause` applies line 142's source clause to `upgrade-3`. It returns the same decision
     and reason that `assess_pairs` would return with `'notification-2'` replaced by the manifest's
     source id.
   - For the default manifest it returns its input unchanged.
3. **Fresh gain.** On at least one validation case **other than `upgrade-3` and `healthy`**, the
   candidate completed at least 2 more trials than the baseline (L − B0 ≥ 2). This is counted per
   case, never summed (pitfall 73).
4. **The source clause, re-checked by the runner.** In validation, the candidate completed
   `upgrade-3` **3 of 3**.
   - Condition 2 already implies this. The runner re-checks it from `by_case`.
   - A study the store records as OBSERVED_IMPROVEMENT that fails this check is an **integrity
     failure**: the run aborts and the row is not certified.

**Why the clause is a transposition and not an addition.** In Phase 17, line 142 demanded the source
(`notification-2`) 3 of 3 in validation. Here no case carries that name, so without `source_clause` a
candidate completing the source 2 of 3 (with B0 0 of 3) would be recorded as OBSERVED_IMPROVEMENT,
which Phase 17's gate would have refused. With it, the stored decision is exactly as strict as
Phase 17's, for every reader of the store: the held-out API, the dashboard, and any later query.

**What condition 3 does and does not add here (stated plainly, R2-3).** For any repair that re-sends
the upgrade once, `upgrade-2` and `upgrade-3` behave the same from the policy's side (§4.3). So once
condition 4 holds, the candidate's 3 of 3 on `upgrade-2` is all but implied. Condition 3 then adds
only one thing: **the baseline completed `upgrade-2` at most 1 of 3**, which is a baseline event.
This is pitfall 73 again: the selection itself nearly satisfies the criterion. Condition 3 is kept,
because it is Phase 17's rule and it still refuses a repair that fails on the sibling. **It is not
evidence of generalisation**, and §13 does not present it as such.

**Not part of the rule** (reported beside it, §7):
- whether the policy re-sends the upgrade, and whether the re-send fires;
- whether the policy also re-sends notifications;
- on which guard cases the policy's rules ran at all.

Nothing is called ACCEPTED, no pointer moves, and nothing is activated.

---

## 6. Size, stops, cap

### 6.0 Phase 28a: the Mechanic-only probe, before any backend change (new in round 1)

**Question.** Shown upgrade-side controls evidence in the loop's own first-proposal format, how
often does the Mechanic's first proposal contain an orders `retry_original_request`? How often
does it answer `no_change` or give invalid output?

**The requests.** There are **K = 30** requests. Each is the loop's slot-1 proposal context
(`completion_study.py:394-403`), built exactly as `_execute` builds it:
- **Evidence.** Six baseline episodes in `planned_slots` order: `upgrade-3`, `healthy`, `upgrade-3`,
  `healthy`, `upgrade-3`, `healthy`.
- **`source_fault_spec`:** `upgrade-v1`'s `upgrade-3` spec (seed 703), made by
  `FaultSpec.model_validate(...).model_dump(mode='json')` exactly as the builder will make it (F6
  checks they are equal). **`control_fault_spec`:** `healthy`'s (seed 101).
- **Also** `runtime_contract()`; `development_evidence = summarize_evidence(bundles,
  outcomes={episode: adjudicated outcome})` (v2 task-outcome); `observed_outcomes =
  trial_outcomes(trials)`; and `candidate_history = []`.
- **Messages and body.** `slot2_probe.mechanic_messages(context)` (imported, never edited, sha
  `28b998ac…`), which is `Mechanic._generate`'s request exactly. Then `request_body(messages,
  temperature=0)`, the loop's frozen Mechanic settings.
- **Format repair.** When the first output fails `MechanicOutput` validation, one format-repair
  follow-up is sent with `_generate`'s correction message verbatim, as the loop does.

**The episodes (development data only, B0 only, read-only).**
- **`upgrade-3` pool:** the 19 v4 DeepSeek-V3.1 B0 episodes on F4 `update_order` count 3 that are
  valid and **not** completed. There are 8 in the Phase 20 store and 11 in the Phase 26 store.
  - A loop context exists only when the valid source controls show 0 completions, so the 2
    completing episodes are excluded.
  - No count-2 or count-4 episode is used.
- **`healthy` pool:** v4 DeepSeek-V3.1 B0 `healthy` episodes that are valid and COMPLETED. There
  are 3 in Phase 20 and 2 in Phase 26, plus Phase 23's controls-stage `healthy` episodes in the main
  store (configuration `2cf63e93…`). The exact list is fixed in the plan.
- **How contexts are drawn.**
  - 30 distinct `upgrade-3` triples and 30 `healthy` triples, drawn with a seed declared in the
    protocol before any call.
  - The drawn episode ids are part of the plan and its hash.
  - Episodes repeat across contexts (19 episodes feed 30 triples), so draws are correlated.
    Intervals are Wilson over draws and **understate** the uncertainty, as in Phase 25.
- **Excluded.** No manual-reference policy episode and no L episode. No `private_*` record
  (private inputs, snapshots) is read.

**The bundles are rebuilt locally.** They are made exactly as `EvidenceGateway.get` makes them with
`require_remote=False`:
- the stored observations, the episode's report, the verdict's checks as findings;
- `source: 'local_only'`, no root or child call ids, `retrieved_at: null`.

**Positive control.** For every main-store `healthy` episode used, the rebuilt bundle's observations,
report and findings must equal its stored `weave_verified` bundle's. Any difference refuses the plan.
This checks that the local rebuild is exact.

**Declared input differences from a loop context** (their effect is unmeasured):
1. Every episode row reads `source: 'local_only'`. The loop's rows read `weave_verified`. The
   `healthy` rows are also rebuilt, so the label is uniform.
2. The six episodes come from different campaigns and stores, not one study's controls, and they
   keep their stored episode ids.
3. The `upgrade-3` episodes ran under their own seeds, not 703. Seeds do not appear in the bundles,
   but `source_fault_spec` shows 703.
4. `campaign_id`, `study_id` and `parent_version` are named probe values, declared in the protocol.

**Read-outs** (computed by the harness, never re-declared):
- **Per draw (all 30):** valid policy, `no_change`, or invalid after format repair.
- **R_draw:** draws whose policy contains `retry_original_request` with `service: orders` (any hook,
  any `only_if`), ÷ 30, with a Wilson interval. A refusal or invalid output is a draw without the
  step, as in the Phase 9 rule.
- **R_valid:** the same count ÷ valid policies.
- **How each re-send is written:** hook, `when`, `only_if`, and the number of orders re-sends.
  - A static label: "cannot fire after a transient failure" when it is gated only on PENDING
    (pitfall 77); "can fire" or "unclear" otherwise.
- **Also:** the Phase 9 notification step present; distinct policies by content hash; the
  `no_change` share with a Wilson interval; the attempt-4 pattern (`defer_unresolved` on
  `after_upgrade_response` with no earlier wait), flagged descriptively.

**Decision (declared).**
- **GO** if **at least one** of the 30 draws contains an orders re-send. This is the same "present,
  not working" predicate as the loop's futility look.
- **NO_GO** if all 30 draws were delivered and none contains one. The Wilson upper bound is then
  11.4%, a stricter bound than the look's 19.4% at D = 16.
- **INCOMPLETE** if fewer than 30 were delivered after one blind re-send of each transport failure
  (pitfall 49) and none so far contains the step. Completing it needs the user's approval and sends
  exactly the missing request ids, once.

**Uses allowed.**
- **The decision only.** On GO, Phase 28's build may start. On NO_GO, the backend change is **not**
  built, and Phase 28 closes with this probe as its result.
- **No tuning.** The protocol may restate §6's **[est]** figures with the measured `no_change` share
  and distinct-policy rate. N, the cap, the look, the certification rule and the case set are fixed
  **now** and do not change with the result.
- **No pooling.** 28a's draws are never pooled with the loop's S1.

**Operating characteristics [est]** (*r* = *s*/0.75 per draw, as for the look):

| *s* | P(NO_GO) |
|---:|---:|
| 0 | 1.00 |
| 0.02 | 0.44 |
| 0.05 | 0.13 |
| 0.10 | 0.01 |
| 0.15 | < 0.01 |

**What it would and would not mean.**
- **GO** means the Mechanic sometimes writes the step when shown upgrade evidence in this format. It
  does not mean the loop will certify it.
- **NO_GO** means 0 of 30 (upper bound 11.4%) in this format. It does not mean "impossible": another
  brief, temperature or model might write it (Phase 25's temperature arm wrote one).

**Cost.** At most 60 calls × $0.04984 = **$2.99** at the conservative bound. **Hard cap $5.**

**Gates.** The same as §8.3's live gates:
- dry by default;
- `--execute-live` with `--confirm-entity`, `--expect-plan-hash`, `--expect-harness-sha256` and
  `--expect-protocol-sha256`;
- `PHASE28A_EXPERIMENT.md`, whose status no longer says "NOT yet reviewed", carrying the bare line
  `Reviewed for launch: harness <sha256> plan <hash>`;
- a review record `artifacts/phase28a-<date>/review.json` repeating the three values;
- **configuration pin `2cf63e93…`**, computed from the code on disk as `slot2_probe.configuration_pins`
  does, so it refuses once any Phase 28 backend change lands;
- the token-based other-paid-run guard (`slot2_probe.live_experiment_processes`), which excludes this
  process, its ancestors and its descendants, so its own `caffeinate -is` helper does not block it;
- an atomic claim, and one run.

### 6.1 Attempts (Phase 28)

- **N = 50 attempts, fixed in advance** (a runner constant). A certified study never stops the run.
- Every attempt is in the denominator. That includes $0 runner refusals and a stop during campaign
  create, labelled as in Phase 23 (§2 rows 11-12 of `PHASE23_EXPERIMENT.md`).

### 6.2 Stop rules (the only ones)

| stop | when | final? |
|---|---|---|
| `futility` | **one look** (definition below). It stops if **R = 0 and k = 0**; if the look passes, it is never repeated | **final**; reported "Stopped for futility at n = j" |
| `fixed_n` | 50 attempts recorded | **final** |
| `spend_guard` | no study starts once charged + $11 > $150 | **final**; "Truncated at n = j" |
| `breaker` | 5 consecutive infrastructure failures | no; resumes only with the user's approval |
| `aborted` | Ctrl-C, SIGTERM, SIGHUP, a failed pin or check, or an integrity failure (§5 condition 4) | no; resumes only with the user's approval |

**The look, defined.**
- **When it is evaluated.** At the top of the main loop, before any other stop check and before
  attempt *n* + 1 starts. It is evaluated over rows 1..*n* (including rows recovered on resume). It
  runs the first time **D ≥ 16** holds and no look record exists.
- **D** = distinct policy hashes, across the whole run and any slot, of candidates that became a
  valid policy. Within-study duplicates, refusals, `no_change` answers and invalid outputs are
  excluded.
- **R** = how many of those D policies contain `retry_original_request` with `service: orders`, at
  any hook and under any `only_if`.
- **k** = certified rows so far.
- **Precedence.** The look is checked first. If it fires at *n* = 50, the stop is `futility`
  (equally final).
- **How it is recorded (review finding R1-5).** When evaluated, the runner writes
  `manifest['futility_look'] = {attempt: n, D, R, k, outcome: 'stop' | 'passed', evaluated_at}`.
  - For a stop, the look record and `stop_reason = 'futility'` are written in the **same save**.
  - `FUTILITY_LOOK_D`, the look's predicate text and the precedence are in the plan (§9), so a
    resume with a different look is refused.
- **On resume.**
  - If `D ≥ 16` and no look record exists (an abort between the crossing attempt and the
    evaluation), the look is evaluated before anything else.
  - A record with `outcome: 'passed'` is never re-evaluated.
  - A record with `outcome: 'stop'` makes the run final. If a crash left the stop reason unwritten,
    the runner writes `futility` and refuses to continue.
- `reconcile` treats `futility` as final: the run's window closes at its end.

**Why the futility look is safe.**
- It can fire only when nothing is certified and the Mechanic has never even written the step, so it
  cannot truncate a success.
- It counts steps that are **present**, not steps that work, so a badly gated re-send keeps the run
  going.
- **[est] Chance it fires:** 1.0 if the Mechanic never writes the step, 0.65 at *s* = 2%, 0.33 at
  5%, 0.10 at 10%, 0.03 at 15%, and under 0.01 at 27%. This assumes a present step works 3 times in
  4, as in Phases 17 and 23.
- **When it falls:** near attempt **24** (21–28) **[est]**. **This timing is an assumption:**
  Phase 23's rate of **1.19 distinct valid policies per controls-passing study** (30 distinct
  policies from 26 drawing studies, on the notification source).
  - If upgrade evidence draws more `no_change` answers, D ≥ 16 comes later: about attempt 36 at 0.80
    per study, about 57 (never within 50) at 0.50.
  - **Declared cost bound when it is never reached:** at *s* ≈ 0 the run then costs about **$72**
    (50 × $1.44) instead of about $35 **[est]**.
  - Phase 28a measures the `no_change` share and the distinct rate first (§6.0).
- **What it reports when it fires:** "0 of D distinct Mechanic policies shown upgrade-side evidence
  re-sent the upgrade (Wilson upper bound 19% at D = 16)".

### 6.3 Power **[est]** (recomputed in round 1)

The model is the data pass's funnel, checked on Phase 23: it predicts 0.109 per attempt against 3 of
30 observed. It is re-parameterised for the revised 7-case set (scratch
`p28-revise/design_numbers_r1.py`):
- **Controls pass:** the source leaks 0 of 3 at 9.5%–16.7% per episode, × healthy 3 of 3
  (0.89–0.92) → **0.52–0.68**.
- **Source gate:** B0 0 of 3 again × L 3 of 3 (0.95) → **0.55–0.70**. Together with the controls, a
  working repair loses about half its attempts to the baseline's own re-sends. This is pitfall 26 at
  a higher leak than `notification-2`'s. It is declared, never loosened.
- **Validation accepts a working repair:** **0.54–0.82** (the first draft's set gave 0.47–0.75). The
  factors:
  - a clean batch (0.97–1.0; there are no notification faults, and upgrade faults have never gone
    untriggered);
  - no candidate check failure (0.93–0.99), including the `upgrade-18` slip term (0.94–0.99);
  - healthy 3 of 3 (0.89–0.92);
  - the refusal kept (0.90–1.0);
  - the source 3 of 3 (0.93–0.97);
  - no false regression on `delayed-upgrade` or `lost-upgrade-response` (0.86–0.94 together).
- **Fresh gain on `upgrade-2`:** B0 at most 1 of 3 there × L 3 of 3 → **0.81–0.95**.

**The look's formula, corrected (review finding R1-6).** The first draft multiplied P(stop) by
P(k = 0 before the look), as if they were independent. But the stop event is a **subset** of
{k = 0 before the look}: R = 0 means no step, and a certification needs the step. With *L* the look's
attempt and *p* the per-attempt chance:

P(k ≥ 1) = 1 − P(stop) − ((1 − *p*)^*L* − P(stop)) · (1 − *p*)^(*N*−*L*)

On the first draft's own case set this gives 0.128 / 0.343 / 0.629 at *s* = 0.02 / 0.05 / 0.10,
against the 0.135 / 0.364 / 0.647 printed there, which reproduces the reviewer's figures.

*s* is the unknown: the chance that a first proposal contains a **working** upgrade re-send.

| *s* | per-attempt P(certify), mid (low–high) | P(*k* ≥ 1 in 50) with the look, mid (low–high) | without the look (mid) | with the look **and** a 28a GO (mid) | expected *k* (mid) |
|---:|---|---|---:|---:|---:|
| 0.02 | 0.49% (0.26–0.78%) | 0.14 (0.09–0.19) | 0.22 | 0.08 | 0.2 |
| 0.05 | 1.2% (0.65–1.9%) | 0.37 (0.23–0.48) | 0.46 | 0.32 | 0.6 |
| 0.10 | 2.5% (1.3–3.9%) | 0.66 (0.46–0.79) | 0.71 | 0.65 | 1.2 |
| 0.15 | 3.7% (2.0–5.8%) | 0.83 (0.62–0.93) | 0.85 | 0.83 | 1.8 |
| 0.27 (the notification-side rate, Phase 23) | 6.6% (3.5–10.5%) | 0.97 (0.83–1.00) | 0.97 | 0.97 | 3.3 |
| 0.40 | 9.8% (5.2–15.5%) | 0.99 (0.93–1.00) | 0.99 | 0.99 | 4.9 |

**What the look costs in power (mid):**

| *s* | without the look | with it | cost |
|---:|---:|---:|---:|
| 0.02 | 0.22 | 0.14 | about 8 points |
| 0.05 | 0.46 | 0.37 | about 9 points |
| 0.10 | 0.71 | 0.66 | about 5 points |
| 0.15 | 0.85 | 0.83 | about 2 points |

The first draft's figures ("about 6 and 3 points") understated it.

For comparison, without the look at the mid band:

| *s* | 0.02 | 0.05 | 0.10 | 0.15 | 0.27 | 0.40 |
|---|---:|---:|---:|---:|---:|---:|
| P(*k* ≥ 1) at N = 30 | 0.14 | 0.31 | 0.53 | 0.68 | 0.87 | 0.96 |
| P(*k* ≥ 1) at N = 40 | 0.18 | 0.39 | 0.63 | 0.78 | 0.94 | 0.98 |

**What the design can and cannot resolve.**

| *k* of 50 | Wilson 95% |
|---:|---|
| 0 | [0, 7.1%] |
| 1 | [0.4%, 10.5%] |
| 2 | [1.1%, 13.5%] |
| 3 | [2.1%, 16.2%] |
| 5 | [4.3%, 21.4%] |
| 8 | [8.3%, 28.5%] |

It separates "happens" from "rare below about 7%". It cannot pin a rate within a factor of two, and
it cannot be compared with Phase 23: the source differs, and no test is declared.

The by-products are sharper than the headline:
- about 200 B0 episodes on `upgrade-3` **[est]** measure the baseline's re-send rate to within a few
  points;
- about 34 distinct Mechanic policies **[est]**, at Phase 23's distinct rate, measure how often it
  writes the upgrade re-send (a Wilson half-width of about ±13 points at 20%).

### 6.4 Cost and cap

Stage costs at the conservative bound (Actor $0.0209, Mechanic $0.04984 per call; per-episode call
counts from the data pass; a working repair's L episodes assumed) **[est]**:

| stage | cost |
|---|---|
| controls (3 `upgrade-3` + 3 `healthy` B0) | $0.75 |
| one source gate incl. its Mechanic call(s) | $0.96 |
| validation (42 episodes; `delayed-upgrade` and `upgrade-18` cost more per episode than the two notification cases they replace) | $5.04 |
| an attempt that reaches validation | $6.76 (one slot) – $7.72 (two slots) |
| hard worst case per attempt (60 episodes × 8 calls + 4 Mechanic calls) | **$10.23** (unchanged from Phase 17) |

Phase 23's measured charges match the old stage costs: controls-only $0.77–0.84, one source gate
$1.56–1.88 cumulative, validation after one slot $5.92–6.11. The validation stage here is about $0.68
dearer.

- **Expected per attempt [est]:** $1.44 (the Mechanic never writes the step) to $2.24 (*s* = 0.40).
  Phase 23's was $2.58, with a source whose controls passed about 88% of the time. **Here about 40%
  of attempts stop cheaply at controls** (the model's controls pass rate is 0.52–0.68). The first
  draft said "~60%", which was wrong (R1-8).
- **Expected total, with the look [est]:**

  | *s* | expected total |
  |---|---:|
  | ≈ 0, the look reached near attempt 24 | about **$35** |
  | ≈ 0, D ≥ 16 never reached | up to **$72** |
  | 0.02 | $49 |
  | 0.05 | $64 |
  | 0.10 | $78 |
  | 0.15 | $86 |
  | 0.27 | $99 |
  | 0.40 | $112 |

  Without the look: $72–112.
- **Hard cap: $150.** No study starts once charged + $11 > $150, so the last start is at $139 or
  less, and the most Phase 28 can charge is **$149.23**.
- **Truncation** needs the first 49 attempts to average over $2.84, which needs about a third of all
  attempts to reach validation. That would itself be upstream success. It is reported as a
  truncation, never topped up.
- **Budget.** Now $652.90 charged, **$347.10 remaining**.
  - Phases 29 (~$15 cap), 30 (~$20 cap) and 28a ($5 cap) come first (§9). At their caps, $307.10
    remains at Phase 28's approval.
  - After Phase 28's worst case: $307.10 − $149.23 = **$157.87 left**, above the $150 reserve.
  - **Rule:** at approval, if the remaining budget is under $300, the cap is lowered to (remaining −
    $150) and N stays 50. The approval record states the remaining budget.
- **Duration [est]:** about 2.5–3.5 hours (Phase 23 ran 30 attempts in 1 h 46 min).
- **Breaker false trip [est]** (exact run-length probability over 50 attempts): 0.07% at a 1-in-9
  death rate, 3.4% at 25%, 15% at 35%.
- Token-priced cost has run about 10× below the bound in Phases 17 and 23. That is unverified.

### 6.5 Continuation after an early stop

As in Phase 23 §4.3:
- **How.** Only `--resume --after-abort` on the same `--out`, with the user's approval.
- **Refused** on any changed plan, harness, protocol or review record. Refused on any code or
  settings difference from the freeze. Refused on any reconcile discrepancy.
- **Final stops.** `fixed_n`, `futility` and `spend_guard` are final, never resumed or topped up.
- **The look on resume.** It is evaluated per §6.2 (never skipped, never repeated).
- A second `phase28-*` folder is refused.

---

## 7. Declared read-outs

All are computed by the runner from its attempt rows and the `events` table (pitfall 50), saved in
the manifest's `summary`, and never re-declared after data exists.

### 7.1 Primary

**k of n attempts produced a certified upgrade-side completion repair, with a Wilson 95% interval.**

Pre-fixed wording. Every form ends with the scope sentence:
- `fixed_n`: "*k* of 50 attempts produced a certified upgrade-side completion repair (Wilson 95%
  [*lo*, *hi*])."
- `futility`: "Stopped for futility at n = *j*: 0 of *D* distinct Mechanic policies re-sent the
  upgrade; 0 of *j* attempts produced a certified upgrade-side completion repair (Wilson 95% [0,
  *hi*])."
- `spend_guard`, `breaker`, `aborted`: Phase 23's wording, with "upgrade-side". A breaker or abort
  stop is "not a finding about the loop".
- **Scope sentence (always):** "Development cases only; no held-out check can follow. The validation
  set has no notification-fault case, so a certified policy's notification-side rules were never
  exercised; `lost-upgrade-response` cannot exercise a gated rule."

**Never quoted without:** the funnel (§7.2), S4 (§7.5), the distinct certified policies (§7.3),
which guards the repair's rules ran on (§7.4), the cumulative count (§7.6), and the Phase 28a result.

### 7.2 The funnel (per attempt and summed)

| stage | definition |
|---|---|
| controls stops | NO_CHANGE at `controls`, **split by cause**: source leak (a valid `upgrade-3` control completed), healthy lapse, too few valid controls |
| infrastructure deaths | `run_full_loop.infrastructure_death`, minus runner-side rows (Phase 23 rule) |
| first proposals drawn | a refusal or invalid output is a draw without the step; "no proposal requested" is no draw |
| **S1u: upgrade re-send present** | first proposals containing `retry_original_request` with `service: orders` at **any** hook ÷ first proposals drawn. Also over all distinct valid policies (R of D) |
| how it is written | for each policy with the step: its hook, the rule's `when`, the step's `only_if`, and the number of orders re-send steps (1 or ≥ 2). A step gated only on `current_operation_pending` is flagged "cannot fire after a transient failure" |
| **fires** | candidates with the step where, in at least one source-gate trial, **the policy itself dispatched `update_order`**: a `tool_dispatched` event with `caller: policy` and `tool: update_order` (`business_tools.py:196`). `policy_step` is not used, because its payload has no service. Also: present but never fired, and validation trials in which it fired, by case |
| **S2u: source gate given the step** | (i) qualified ÷ step candidates with complete pairs; (ii) qualified ÷ all step candidates. Qualified **without** the step is counted separately |
| source-gate leak | a source-gate NO_CHANGE with at least one B0 completion (the gap did not reproduce at the gate) |
| validation | reached; assessed; clean (zero invalid trials) and dirty; accepted on clean ÷ clean. Accepted on dirty is **0 by construction** and labelled so (pitfall 72) |
| rejection reasons | every validation NO_CHANGE with its reason **and the case**: refusal, `delayed-upgrade`, `upgrade-18`, `lost-upgrade-response`, `healthy`, a candidate check failure, or the **transposed source clause** (below) |
| **rejected by the transposed source clause** | validation NO_CHANGE carrying `source_clause_case: 'upgrade-3'`, worded "Phase 17's gate would also have returned NO_CHANGE: the candidate completed the source fewer than 3 of 3" |
| **OBSERVED_IMPROVEMENT, not certified** | OBSERVED_IMPROVEMENT without a fresh gain (condition 3). **Stated prominently**, with each study id listed as "store says OBSERVED_IMPROVEMENT; not certified (no fresh gain)" |
| integrity failures | a store OBSERVED_IMPROVEMENT that fails the runner's condition 4; expected 0; any one aborts the run |
| certified | §5, post-checks passed |

### 7.3 Distinct hashes (pitfall 29)

- **Counts:** draws; distinct policies; distinct first proposals; distinct policies with the upgrade
  re-send.
- **Duplicates and re-draws:** within-study duplicates (slot 2 repeating slot 1); policies re-drawn
  across attempts.
- **Certified:** certified attempts in order; **distinct certified policies**; whether each certified
  hash existed in the store before the run (a read-only query at report time).
- **Both-sides policies:** policies that carry both an orders re-send and the Phase 9 notification
  step. Also any re-draw of `dd62c857…`, `711bddb6…`, `5735a918…` or `d4bc993e…`.

### 7.4 Which guards did a repair's rules actually run on? (reworked in round 1)

- **For every validation-reaching candidate,** by case:
  - L and B0 counts on each case;
  - the number of L trials with at least one executed `policy_step` (an event with `executed: true`,
    pitfall 79);
  - the number where the policy dispatched `update_order`.
- **Labels.** A guard where no rule ran in any L trial is labelled **"not exercised"** for that
  candidate. This is the honest form of pitfall 72: a guard that never ran a rule proves nothing
  about that rule.
- **Stated plainly beside it.** For a certified repair, "keeps" (L ≥ B0 on the expected outcome, no
  candidate check failure) is **guaranteed by the gate**, because every case is a gated validation
  case. The informative figure is the other side: **how many source-qualified upgrade repairs were
  rejected in validation, and on which guard** (from §7.2).
- **Not measured here:**
  - whether a certified upgrade repair also closes the notification gap;
  - whether its notification-side rules are safe (they cannot run on any case here).
  - Reported only as "also contains the Phase 9 notification step: yes/no", read from the policy
    text.

### 7.5 The nuisance, quoted beside every validation result (S4)

- **The definition:** untriggered faults per fault-bearing episode, all stages, LAB_ERROR excluded
  (Phase 17's S4), with a Wilson interval.
- **All faults in this design are upgrade-side,** so S4 counts upgrade-fault episodes only. The
  notification-fault count is 0 by design, and the runner reports it as 0.
- **It is not comparable with Phase 17's 0.65% or Phase 23's 1.6%,** which were dominated by
  notification faults.
- **[est]** clean-batch probability: 0.97–1.0. The Actor has called `update_order` in every stored
  upgrade-side episode.

### 7.6 Secondary: the cumulative count (Phase 17's pooling rule)

"*k* + 4 certified completion repairs in *n* + 39 attempts across Phases 17, 23 and 28", always with
this caveat: "Phases 17 and 23 used the notification source and Phase 28 the upgrade source, so this
is a count required by Phase 17's rule, not a rate." No pooled share is quoted.

### 7.7 Also reported

- **The baseline's leak on `upgrade-3`, measured in this run:** B0 completions ÷ valid B0 trials on
  `upgrade-3`, controls and source gates pooled.
  - **An Actor re-send** is an episode with **at least 2 distinct `call_id`s** among its
    `tool_dispatched` events with `caller: actor` and `tool: update_order`.
  - This fixes review finding R1-7. Counting events would count every F4 episode, because the
    adapter emits one event per HTTP attempt and makes two attempts per call (`business_tools.py:185-196`).
  - Re-checked on stored data: F4 counts 2–4, L arms, events ≥ 2 in 63 of 63, distinct calls ≥ 2
    in 0 of 63 (`gated_rule_check.out.txt`).
  - A test pins this on a real stored F4 episode's events.
- Evidence reads, re-reads, verified re-reads.
- **Cost:** total, per attempt and per certification, at the conservative bound. Token-priced cost
  separately, labelled unverified.
- **The drift check:** drifted and masked episodes, missing world files, exit status. Any drift is a
  lab defect reported beside the result. It never earns a re-run.

---

## 8. Every code change

### 8.1 `backend/app`: moves the freeze and the configuration hash (design only; **not made here**)

All changes are in two files. Nothing under `backend/app/referee`, `backend/app/agents`, the adapters,
the interpreter, the simulator or the contracts changes.

**`backend/app/lab/completion_study.py`.** All **new** code goes **at the end of the file, after
`_execute`** (review finding R1-3). Nothing is inserted above `queue_completion_study`, so
`case_manifest`, `planned_slots` and `assess_pairs` keep their text **and their line ranges**. No new
import is needed: `deepcopy`, `FaultSpec`, `StoreConflict` and `content_hash` are already imported,
and `load_manifest` is imported locally as in `case_manifest()`.

1. **`upgrade_case_manifest()`** (new, at the end). `case_manifest()` stays byte-identical (text
   `0a5346c8…`, output `7ab9368e…`). The new builder:
   - calls `case_manifest()` and deep-copies `healthy` and `terminal-upgrade-rejection` from it, so
     those two are byte-identical to the reviewed ones;
   - loads `load_manifest('development')` and deep-copies `dev-2` (lost upgrade response), `dev-3`
     (delayed upgrade) and `dev-6` (the template for the three F4 upgrade cases, as `case_manifest()`
     does for its siblings);
   - refuses (`StoreConflict('Reviewed public upgrade cases changed')`) unless `dev-2`'s and
     `dev-3`'s `fault_spec`s equal `FaultSpec.model_validate(...).model_dump(mode='json')` of F1
     `update_order` 1500 ms, seed 102, and F2 `update_order` 3 ticks SUCCEEDED, seed 103 (the same
     pattern as lines 51-57);
   - builds `upgrade-3`, `upgrade-2` and `upgrade-18` with `FaultSpec.model_validate(...)` (seeds
     703, 702, 718; F4 `update_order`/`orders`, occurrence 1, `failure_count` 3, 2, 18), named
     `upgrade_transient_3` / `_2` / `_18`. Expected outcomes COMPLETED, COMPLETED, SAFE_UNRESOLVED;
   - sets `case_id='delayed-upgrade'` and `expected_outcome='COMPLETED'` on the `dev-3` copy, and
     `case_id='lost-upgrade-response'` and `expected_outcome='COMPLETED'` on the `dev-2` copy;
   - validates every case's `fault_spec` (as lines 78-79) and returns the §4.1 dict in §4.1 order,
     with `source_case_id='upgrade-3'` and `control_case_id='healthy'`.
2. **A closed registry** (new, at the end):

   ```python
   CASE_MANIFESTS = {'notification-v1': case_manifest, 'upgrade-v1': upgrade_case_manifest}
   DEFAULT_CASE_MANIFEST = 'notification-v1'

   def build_case_manifest(manifest_id):
       if manifest_id not in CASE_MANIFESTS:
           raise StoreConflict('Unknown completion case manifest')
       manifest = CASE_MANIFESTS[manifest_id]()
       if manifest['control_case_id'] != 'healthy':
           # assess_pairs line 142 names the healthy control literally; never let it go inert.
           raise StoreConflict('A completion manifest must use the literal healthy control')
       return manifest
   ```
3. **`source_clause(result, manifest)`** (new, at the end). Line 142's source clause for a manifest
   whose source is not `notification-2`:

   ```python
   def source_clause(result, manifest):
       """assess_pairs line 142 demands 3 of 3 on the literal 'notification-2'. For any other source
       that clause never applies; this restores it. The decision and reason equal assess_pairs' with
       the literal replaced by manifest['source_case_id']; for the default manifest it is the identity."""
       source = manifest['source_case_id']
       if source == 'notification-2' or result.get('decision') != 'OBSERVED_IMPROVEMENT':
           return result
       if result['by_case'][source]['L']['completed'] != 3:
           return {**result, 'decision': 'NO_CHANGE',
                   'reason': 'Healthy or source completion was not preserved in all trials',
                   'source_clause_case': source}
       return result
   ```

   **Why it is exact.** It gives the same decision and the same reason as `assess_pairs` would
   with the literal replaced:
   - If `assess_pairs` returns INCOMPLETE or NO_CHANGE, the patched version returns the same
     decision, because line 142 can only add a rejection.
   - If `assess_pairs` returns OBSERVED_IMPROVEMENT, no case regressed. The patched version's only
     possible rejection is then the source clause, with line 142's reason.
   - The one added key, `source_clause_case`, appears only when the clause fires.

   A test proves this property against a patched copy of `assess_pairs` (§8.2).
4. **`queue_completion_study(..., case_manifest_id=None)`** (lines 150-211):
   - **Line 170 becomes** `manifest = build_case_manifest(case_manifest_id or
     DEFAULT_CASE_MANIFEST)`. It is still before the lock, so an unknown id is refused **before any
     state is taken**.
   - **Replay stays on the default manifest.** Refuse `replay_policy_version` together with a
     non-default id (`StoreConflict('Replay runs only the default manifest')`), so the replay path
     stays exactly today's.
   - **The record.** Add `record['case_manifest_id'] = case_manifest_id` **only when an id was
     passed**, before the two `put_record` calls. A default request then writes exactly today's
     record.
5. **`check()`** (nested in `_execute`, line 238): `content_hash(build_case_manifest(record.get(
   'case_manifest_id', DEFAULT_CASE_MANIFEST)))`. Without this, the first `check()` of an
   `upgrade-v1` study raises `StoreConflict` before any control runs.
6. **`_execute` line 364:** `source = cases[record['manifest']['source_case_id']]; healthy =
   cases[record['manifest']['control_case_id']]`. For `notification-v1` these resolve to the same two
   cases as today. Without this: a `KeyError` after 6 paid controls, the study INCOMPLETE, and the
   breaker trips after 5 attempts.
7. **`_execute` lines 357 and 437:** wrap both validation calls, `result =
   source_clause(assess_pairs(...), record['manifest'])`. The candidate-marking code (442-444) is
   unchanged. It now marks a clause rejection REJECTED, as Phase 17's gate would have.
8. **Unchanged and pinned as unchanged:**
   - the functions `assess_pairs` (`783e8e58…`), `case_manifest` (`0a5346c8…`) and `planned_slots`
     (`495f60fc…`);
   - `MODEL_CALL_RESERVATION` (484), `PROPOSAL_SLOTS` and the evidence constants;
   - the source-gate call at line 427, which already uses `[source]`.

**`backend/app/lab/api.py`**

9. `CompletionStudyRequest` (lines 26-34) gains `case_manifest_id:str|None=Field(default=None,
   max_length=40)`. The route (lines 277-280) passes `case_manifest_id=request.case_manifest_id`.
   Unknown fields stay forbidden.

**What moves** (corrected, R1-3):
- **In `gate_freeze.py`'s output:** `files['backend/app/lab/completion_study.py']` (`c3fc2234…`);
  the whole function entries (text, AST and lines) for `completion_study.py::queue_completion_study`
  (`fe3bcae1…`) and `::_execute` (`07b58b8e…`); and the fingerprints `tree_lab`, `algorithm_hash`
  (`f2f71c59…`) and `runtime_hash` (`67e6d968…`).
- **Therefore** the **configuration hash leaves `2cf63e93…`**.
- **No file entry for `api.py` exists to move.** The first draft listed one. `api.py` is covered
  only through `tree_lab`, `algorithm_hash` and `runtime_hash`.

**What must not move:** every other entry of the Phase 22 freeze (`8994e962…`), compared as **whole
entries including `lines`**:
- `assess_pairs`, `case_manifest` and `planned_slots`, which keep their line ranges because the new
  code is appended after `_execute`;
- the four v1 held-out functions;
- `scorer_hash` `19de811c…`, `source_hash` `da80ac6f…`, `completion.md` `e3b9362f…`,
  `contract_hash`, `actor_prompt_hash`, `adapter_hash`, `interpreter_hash`, `service_hash`,
  `dependency_lock_hash`, `tree_referee` and `tree_telemetry`.

**Not fingerprinted by the pinned `gate_freeze.py`:** the new functions. They are bound by the
`completion_study.py` file sha, the runner's manifest-hash pin, and the supplementary function hashes
(§4.2 d).

**Not changed, on purpose: `heldout_check.py`.**
- **Why it matters.** `certified_source` (370-382) does not check the manifest or the fresh gain. So
  the held-out API would still accept an `upgrade-v1` OBSERVED_IMPROVEMENT study, as it accepts a
  `notification-v1` study without a fresh gain today.
- **What `source_clause` fixes.** With it, the store never records OBSERVED_IMPROVEMENT for a source
  below 3 of 3, which is the looser case the reviewer found.
- **What stays procedural** (§14): OBSERVED_IMPROVEMENT without a fresh gain. No held-out request
  names any Phase 28 study, and the runner has no code path that makes one.
- **Why not change it.** Changing `heldout_check.py` would move the pinned v1 functions.

### 8.2 Backend tests (part of the reviewed change set)

New `backend/tests/lab/test_completion_manifests.py`:
- **The old manifest:** `content_hash(case_manifest())` is still `7ab9368e…`, and its text sha is
  still `0a5346c8…`.
- **`upgrade_case_manifest()`:**
  - 7 cases in §4.1 order, with the declared ids, fault specs and expected outcomes;
  - no case named `notification-2`; no notification-fault case; exactly one SAFE_UNRESOLVED
    (`upgrade-18`);
  - `healthy` and `terminal-upgrade-rejection` byte-identical to `7ab9368e`'s;
  - its hash equals the pinned value (filled at the freeze) and the stdlib mirror's;
  - a changed `dev-2` or `dev-3` fault spec (monkeypatched `load_manifest`) raises `StoreConflict`.
- **`build_case_manifest`:** unknown ids are refused; a manifest with a non-`healthy` control is
  refused.
- **`source_clause`, a property test.**
  - It builds a reference by reading `assess_pairs`' source with `inspect.getsource`, replacing the
    literal `'notification-2'` with `'upgrade-3'`, and executing it in a namespace with the same
    imports.
  - Then, over every combination of per-case L and B0 completion counts (0–3) on a reduced case
    list, plus candidate-violation and incomplete-pairs variants, `source_clause(assess_pairs(...),
    manifest)` must equal the reference's decision and reason.
  - For the default manifest it must be the identity.
- **`planned_slots(upgrade manifest)`:** 6 controls on `upgrade-3`/`healthy`, 6 per candidate stage
  on `upgrade-3`, 42 validation slots, 60 in all, so 484 calls suffice.
- **Refusals before any state:** an unknown id is refused with no ledger reservation, the campaign
  still IDLE and no record written. A replay with a non-default id is refused the same way.
- **The default path:** a default request writes a record whose key set equals today's (no
  `case_manifest_id`), and `check()` passes on it.
- **With a fake runner through `_execute`:**
  - an `upgrade-v1` study runs its controls on `upgrade-3`;
  - the saved proposal input's `source_fault_spec` is `upgrade-3`'s;
  - `check()` does not raise across all stages;
  - a validation result with `upgrade-3` L 2 of 3 is stored NO_CHANGE with `source_clause_case`,
    and the candidate is marked REJECTED.
- **The route:** it passes the id, and an unknown extra field is still 422.

**Fallout to handle, not hide.** Every test that compares the on-disk configuration with `2cf63e93…`
or the tree with `8994e962…` will fail or skip once the backend moves. The files found now are
`test_report_word_probe.py`, `test_report_narrow_probe.py`, `test_slot2_hidden_probe.py` and
`test_run_gap_probe.py`; others may test the same thing through constants.
- **At build time** they are enumerated from a full-suite run on the main checkout.
- **Handling.** Those that already skip when the tree is not Phase 22's are listed. Any that fails
  instead gets a **declared** skip in its test file, as Phase 22 did for `test_lapse_probe.py`
  (approver decision N3).
- **The pinned harnesses themselves are never edited.**

### 8.3 Scripts only: the Phase 28 runner (the pinned runners are imported, never edited)

**`scripts/experiments/run_upgrade_loop.py`** (new). It imports `run_full_loop as base` (`07dcaa93…`),
`run_full_loop_fixed_n as fixed` (`95ef698d…`) and `slot2_probe` (`28b998ac…`, for the paid-run guard
only). The main loop is **copied** from `fixed.main`, because the POST body is inline there, as
Phase 23 copied Phase 17's.

| item | value |
|---|---|
| POST body | adds `'case_manifest_id': 'upgrade-v1'` beside `execute_live`, the evidence protocol and the v4 context |
| pins (constants in the runner) | `DECLARED_MANIFEST_HASH`, `DECLARED_FREEZE_SHA256`, `DECLARED_CONFIGURATION_HASH`, the supplementary function hashes (§4.2 d), and the unchanged settings (`1e2002d3…`), brief (`e3b9362f…`), base runner (`07dcaa93…`), fixed-N runner (`95ef698d…`), `slot2_probe.py` (`28b998ac…`), `gate_freeze.py` (`5e21c0ec…`), drift checker (`fa25ab9d…`), ingestion check (`edde0190…`) and launcher (`78911a29…`). **No protocol sha, runner sha or review-record sha is a constant** |
| design constants | `N_ATTEMPTS=50`, `SPEND_CAP=150.0`, `HEADROOM=11.0`, `BREAKER=5`, `FUTILITY_LOOK_D=16`, `FINAL_STOPS=('futility','fixed_n','spend_guard')`, `PHASE_PREFIX='phase28-'`, `CASE_MANIFEST_ID='upgrade-v1'`, `SOURCE_CASE='upgrade-3'`, `CONTROL_CASE='healthy'`, `FRESH_GAIN_MIN=2` |
| the plan | a canonical dict of the design constants, the pins, the models, protocols and project, the certification-rule text, the look's predicate text and precedence, and the stop rule. **It holds no protocol sha, no runner sha and no review-record sha.** `plan_hash = content_hash(plan)`; the plan is computed without reading the protocol |
| step predicates | `contains_upgrade_retry(content)`: any `retry_original_request` with `service: orders`, any hook. `upgrade_retry_fired(events)`: `tool_dispatched`, `caller: policy`, `tool: update_order`. `actor_resend_episode(events)`: at least 2 distinct `call_id`s among `tool_dispatched` events with `caller: actor`, `tool: update_order`. `rules_ran(events)`: at least one `policy_step` with `executed: true`. `base.contains_step` and `fixed.step_fired` are kept only for §7.3's both-sides count |
| routing | none. The summary carries `routing: null` and the reason |
| live gates (Phase 25/27 scheme, R1-1) | dry by default. A live run needs `--execute-live`, `--confirm-entity`, `--expect-plan-hash H`, `--expect-harness-sha256 S`, `--expect-protocol-sha256 P` and `--review-record R`. It refuses unless: sha256(this file) = S; sha256(protocol) = P; `plan_hash` = H; the protocol's status block no longer says "NOT yet reviewed"; the protocol has the **bare** line `Reviewed for launch: harness S plan H`; and the review record has `status: approved`, a non-empty `approved_by`, `{protocol_sha256, harness_sha256, plan_hash}` = `{P, S, H}`, and `gate_freeze_file_sha256`, `configuration_hash` and `manifest_hash` equal to the pins. Also: every pin filled and matching, the code on disk equal to the freeze, and the first campaign's configuration hash equal to the pin, at $0 |
| resume identity | `declared = {plan, plan_hash, harness_sha256, protocol_sha256, review_record_sha256}`. Resume is refused if any differs |
| other-paid-run guard | token-based, via `slot2_probe.live_experiment_processes` (the `paid_run_command` rule). It refuses while another process's command line is a `scripts/experiments/<name>.py` run carrying `--execute-live` or a prefix of it, **excluding this process, its ancestors and its descendants**, so its own `caffeinate -is` helper does not block it (the Phase 25/26 round-3 fix). Checked before the first campaign, after the claim, and before every attempt |

**Own functions (not reused, because the base ones hard-code the notification source, Phase 23 or
Phase 17; completed in round 1, R1-4):**
- **identity and certification:** `identity_problems`, `verify_study_identity`, `certified`
  (§5, including the condition-4 re-check), `fresh_case_gain`;
- **per-study summary:** `summarize_study`, which replaces `base.summarize_study` (that one uses
  `base.contains_step` and `base.certified`);
- **the funnel:** `attempt_funnel` (it replaces `fixed.attempt_funnel`, which uses the notification
  predicates) and `add_funnel` (it replaces `fixed.add_funnel`, which calls the module-level
  `fixed.attempt_funnel`);
- **run summaries:** `stage_funnel`, `hash_accounting` (`fixed`'s tracks only `PHASE17_POLICY_HASH`
  and the notification flag), `primary_statement` (with `futility` and the scope sentence;
  `fixed`'s would print "Run not finished (futility)"), and `summarize_upgrade`. The last replaces
  `fixed.summarize_fixed_n`, which pools with `PHASE17_ATTEMPTS, PHASE17_CERTIFIED = 9, 1`; this
  one pools with 39 and 4, with the §7.6 caveat;
- **routing:** `routing`, returning the null field;
- **the look:** `futility_look`;
- **reconcile:** `expected_certified` and `reconcile` (with `futility` final);
- **pins and launch:** `plan` / `plan_hash`, `unfilled_pins`, `pin_files`, `pin_status` (all read
  this module's globals), and `check_launch`, which replaces `fixed.check_static_pins` and
  `fixed.review_problem`;
- **the run itself:** `claim` (`phase28-` prefix), `main`, and the in-`main` `recover`. The last uses
  this module's `summarize_study`, `verify_study_identity` and `add_funnel`, never
  `base.summarize_study` or `base.verify_study_identity` (which carry `MANIFEST_HASH 7ab9368e`).

**Reused unchanged:**
- **from `fixed`:** `wilson`, `valid_trial`, `episode_events`, `runner_side`, `infrastructure_death`,
  `label_phantoms`, `ingestion_health`, `clock_drift`, `is_sha256`, `BreakerTripped`, `retry_executed`
  and `step_fired` (the latter two only for the both-sides count);
- **from `base`:** `api`, `wait_until_idle`, `record_charge`, `total_spend`, `campaign_spend`,
  `check_backend`, `check_backend_process`, `backend_status`, `check_campaign_in_store`,
  `check_evidence_project`, `gate_freeze`, `store_records`, `sha256_file`, `case_gains`,
  `contains_step`, `Detached`, `PhaseAbort`, and the constants `TERMINAL`, `TASK_TEXT`, `ORDER_ID`,
  `EXPECTED_ACTOR`, `EXPECTED_MECHANIC`, `EXPECTED_PROJECT`, `ACTOR_CONTEXT`, `EVIDENCE_PROTOCOL`,
  `ASSESS_PAIRS_KEY` and `ASSESS_PAIRS_TEXT_SHA256`;
- **from `slot2_probe`:** `live_experiment_processes` only.

**Tests:** `backend/tests/experiments/test_run_upgrade_loop.py` (new), modelled on
`test_run_full_loop_fixed_n.py`:
- **An allowlist test (R1-4).** An AST scan of `run_upgrade_loop.py` collects every attribute read
  on `base`, `fixed` and `slot2_probe` and fails on any name outside the declared reused lists above.
  In particular it fails on `fixed.attempt_funnel`, `fixed.add_funnel`, `fixed.summarize_fixed_n`,
  `fixed.hash_accounting`, `fixed.primary_statement`, `fixed.routing`, `fixed.check_static_pins`,
  `fixed.review_problem`, `fixed.pin_*`, `fixed.unfilled_pins`, `fixed.reconcile`,
  `fixed.expected_certified`, `fixed.claim`, `base.certified`, `base.summarize_study`,
  `base.verify_study_identity`, `base.identity_problems`, `base.fresh_case_gain`, `base.reconcile`,
  and any `SOURCE_CASE`, `CONTROL_CASE`, `MANIFEST_HASH`, `PROTOCOL`, `PHASE17_*`, `DECLARED_*`,
  `N_ATTEMPTS`, `FINAL_STOPS` or `PHASE_PREFIX` read from `base` or `fixed`.
- **The certification truth table:**
  - OBSERVED_IMPROVEMENT with `upgrade-3` L 2 of 3 in a stored record is an integrity abort,
    not a certification;
  - a clause NO_CHANGE is not certified and is counted in §7.2's row;
  - a gain only on `healthy` is not fresh;
  - a gain of 2 on `upgrade-2` with the source 3 of 3 is certified;
  - a wrong manifest hash or a missing `case_manifest_id` is not.
- **The launch gates (R1-1):**
  - a temporary protocol with the launch line and a matching review record passes the dry
    `check_launch`;
  - **editing the protocol after the launch line refuses** (P mismatch);
  - a harness sha, plan hash or review-record mismatch refuses;
  - a missing bare line, or one in backticks or a list, refuses;
  - **the plan hash does not change when the protocol changes**, and changes when any design
    constant or pin changes.
- **The futility look (R1-5):**
  - it fires only at the first D ≥ 16, only with R = 0 and k = 0, and never twice;
  - it counts present, not working, steps, and excludes duplicates, refusals and invalid outputs;
  - its record is written in the same save as the stop;
  - **an abort between the crossing attempt and the evaluation** is evaluated on resume before
    anything else;
  - a `passed` record is never re-evaluated;
  - a `stop` record with a missing stop reason becomes `futility` and refuses to continue;
  - `reconcile` treats `futility` as final.
- **The predicates on real stored event shapes:**
  - `actor_resend_episode` is false on a stored F4 L episode with 2 `tool_dispatched` events that
    share one `call_id`, and true on a stored B0 episode with 2 distinct calls;
  - `upgrade_retry_fired` is true on a stored MR episode.
- **Also:**
  - the POST body carries the id;
  - the paid-run guard ignores its own caffeinate child and blocks a foreign `--execute-live` run;
  - every stop's pre-fixed wording includes the scope sentence;
  - resume refusals;
  - a fake backend modelled on the real routes' fallback bodies (pitfall 76), with every wait
    capped.

**Prep scripts** (committed under `artifacts/phase28-<date>/prep/`, $0), each with its saved output
(pitfall 84):
- `manifest_hash.py`: prints `content_hash(build_case_manifest('upgrade-v1'))` and loads no settings;
- `draft_manifest_r1.py`: the stdlib mirror, from scratch;
- `freeze_compare_p28.py` (§9, F4);
- `new_function_hashes.py` (§4.2 d);
- `design_numbers_r1.py` (§6).

### 8.4 Scripts only: the Phase 28a harness (new in round 1)

**`scripts/experiments/mechanic_upgrade_probe.py`** (new; no backend change).
- **Imports:**
  - `slot2_probe`: `mechanic_messages`, `request_body`, `settings_from_file`,
    `configuration_pins`, `check_pins`, `live_experiment_processes`, `parse_policy` and `SpendGuard`
    (with a $5 cap), never edited;
  - `app.lab.diagnosis`: `summarize_evidence`, `runtime_contract`, `trial_outcomes`;
  - `app.contracts.models`: `EvidenceBundle`, `PublicObservation`, `TrialResult`, `MechanicOutput`,
    `MechanicNoChange`, `FaultSpec`, `content_hash`, `canonical_json`;
  - `run_full_loop.contains_step`.
- **Modes:**
  - `--write-plan`: reads the three stores read-only, builds the pools and the seeded contexts, runs
    the positive control, and writes the plan (every request's messages hash and request hash);
  - dry (default): prints the plan hash and pins;
  - `--execute-live`: the §6.0 gates;
  - `--readouts`: recomputes the read-outs from the saved responses, and refuses unless the harness
    and plan match the run's.
- **What it never does:** create a campaign, study, trial, world, policy or store row. Its results
  are never shown to any model and never enter a study.

**Tests:** `backend/tests/experiments/test_mechanic_upgrade_probe.py` (new):
- **The context shape:**
  - the context has the same keys and the same order of evidence rows as a stored slot-1
    `completion_proposal_inputs` record;
  - with a stored completion study's own control bundles, the harness's builder reproduces that
    study's stored slot-1 input byte for byte, apart from the declared `source` label;
  - a stored `weave_verified` bundle's observations, report and findings are reproduced by the
    local rebuild.
- **The pools and the gate:**
  - the pools exclude completing `upgrade-3` episodes, non-v4 or non-V3.1 episodes, L and MR
    episodes;
  - no `private_*` kind is ever read (the store's read calls are asserted);
  - GO / NO_GO / INCOMPLETE on synthetic responses;
  - the format-repair message is `_generate`'s verbatim.
- **The same launch-gate tests as §8.3,** including a protocol edit after the launch line and plan
  invariance to the protocol.

**Its protocol:** `docs/part2/PHASE28A_EXPERIMENT.md` (new), written from §6.0.

### 8.5 Rejected alternatives

- **Scripts only, rebuilding the loop client-side** (direct Mechanic requests + the paired evaluator
  + an imported `assess_pairs`). It is not the same loop, and it re-implements about 250 reviewed
  lines. The backend change is smaller and keeps `_execute` in charge.
- **Editing `case_manifest()` in place.** It breaks `heldout_check.excluded_identities()` (287-301
  raise if it changes), `make_heldout_partition.py:262-265`, `phase20_prep_schedule_identities.py:111`
  and several tests.
- **A 9-case set.** It needs a change to `MODEL_CALL_RESERVATION` and its pinned test, and it costs
  certification probability (§4.3).
- **Condition 4 in the runner only** (review option b). Every other reader of the store would see
  OBSERVED_IMPROVEMENT where Phase 17's gate says NO_CHANGE. Rejected in favour of `source_clause`
  (R2-2).
- **Editing `assess_pairs` line 142 to read the manifest's source.** That would weaken the pin on the
  gate's own text (`783e8e58…`), which every phase since 15 has kept. `source_clause` gives the same
  decision without touching it.
- **Keeping the two notification guards.** They cannot run a gated rule (0 of 24 each) and carry the
  untriggered-fault nuisance (§4.3).

---

## 9. Sequencing, build location, freeze and launch

**Sequencing.**
- **Why the order is fixed.** The pinned Phase 25/27 harnesses that Phases 29 and 30 reuse compute
  the configuration from the code on disk and refuse anything but `2cf63e93…`
  (`slot2_probe.py:863-864`, `report_word_probe.py:777-778`). The new Phase 29 and 30 files
  (`slot2_hidden_probe.py`, `report_narrow_probe.py`) carry the same pin, and so does Phase 28a.
- **The steps:**
  1. **Phase 28a** is built, reviewed (two rounds), approved and run on the current code, never
     beside another paid run (the guard enforces this). **NO_GO ends Phase 28 here.**
  2. **On a 28a GO**, the Phase 28 backend change, tests and runner are written and reviewed in a
     **separate detached worktree**, never on the main checkout (R1-9), while Phases 29 and 30 run:
     - **Why not main HEAD.** Main HEAD (`cbbf957`) does **not** contain the uncommitted Phase
       16-27 implementation: `completion_study.py` is untracked, and `git status --porcelain --
       backend/app scripts/experiments` lists 40 entries.
     - **Create it:** `git -C /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab worktree add
       --detach ../faultlab-p28-build backup/part2-2026-09-22`. The branch is at `3cda105`, where
       `completion_study.py`, `api.py`, `run_full_loop_fixed_n.py` and `slot2_probe.py` hash to
       `c3fc2234…`, `9c3ac453…`, `95ef698d…` and `28b998ac…`, the same as on disk. `--detach`
       means no commit there can move the backup branch.
     - **Check it before any edit:** `diff -rq --exclude=__pycache__` of `backend/app` between the
       main checkout and the worktree must print nothing. For `backend/tests` and
       `scripts/experiments`, only the listed Phase 29/30 files that are newer than `3cda105` may
       differ. Otherwise stop.
     - **Python:** the main checkout's interpreter,
       `/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/.venv/bin/python`, run from the
       worktree's `backend/`. The worktree has no `.venv`.
     - **Artifacts:** the worktree has no `artifacts/` (it is git-ignored). **Do not symlink it**: a
       prep script or test could write into the real folder. In the worktree, run only the unit
       tests that need no artifacts. The Phase 22 freeze, the stores and the configuration-pinned
       tests run on the main checkout after landing (F2).
     - **Or** a scratch copy of `backend/` and `scripts/experiments/` under the same rules.
  3. **Landing.** The change lands on the main checkout only after Phases 29 and 30 have ended
     (results written, no run live).
     - **Check first:** `gate_freeze.py` on the main checkout must still equal the Phase 22 freeze
       (`8994e962…`), so nobody changed `backend/app` meanwhile.
     - **Then** copy exactly the §17 files from the worktree, and run the freeze steps below.

**Freeze and launch steps.** Outputs go to `artifacts/phase28-<date>/`. Each sha is taken only after
every value inside its file is final, and **no sha is ever written into the file it depends on**
(R1-1).

- **F1. Last code edit made** (§8.1, §8.2, §8.3) on the main checkout. `PHASE28_EXPERIMENT.md` is
  written from this design, with status "NOT yet reviewed".
- **F2. Tests after the last edit** (pitfall 75), from `backend/` on the **main checkout**:
  `../.venv/bin/python -m pytest -q -p no:cacheprovider -rfEs tests/lab/test_completion_study.py
  tests/lab/test_completion_manifests.py tests/experiments/test_run_upgrade_loop.py
  tests/experiments/test_run_full_loop.py tests/experiments/test_run_full_loop_fixed_n.py
  tests/experiments/test_mechanic_upgrade_probe.py`, then the full suite.
  - Every failure or skip is listed and must match the declared fallout (§8.2).
  - The intermittent `[untriggered]` failure is reported if it appears.
  - The result is never called "unconditionally green".
- **F3. Review rounds** (§11). After any fix, back to F2.
- **F4. Freeze.**
  - Run `./.venv/bin/python scripts/experiments/gate_freeze.py >
    artifacts/phase28-<date>/gate-freeze-after.json` (`gate_freeze.py` `5e21c0ec…`, unchanged),
    then `shasum -a 256`.
  - **Accept it only if** `prep/freeze_compare_p28.py` exits 0 against Phase 22's freeze
    (`8994e962…`). Its rule: the **only** differing entries are exactly §8.1's "what moves" list, and
    every other function, file and fingerprint entry is **byte-equal as a whole, including `lines`**.
  - Also save `prep/new_function_hashes.py`'s output.
  - Re-run and save Phase 22's `prep/v1_function_hashes.py` and `prep/phase18_reassessment.py`. Both
    must exit 0, because `heldout_check.py` is untouched.
- **F5. Expected configuration hash.**
  - The operator runs `./.venv/bin/python scripts/experiments/expected_configuration.py
    artifacts/phase16-2026-09-22/settings-phase17.json`. It loads the root `.env` in-process; nobody
    opens or prints it.
  - Cross-check with `artifacts/phase22-2026-09-24/prep/config_hash_no_env.py`, which reads no
    `.env`.
  - The two must agree, and their `algorithm_hash` and `runtime_hash` must equal F4's.
- **F6. Manifest hash.**
  - `prep/manifest_hash.py` prints the builder's `upgrade-v1` hash. It must equal the stdlib
    mirror's (§4.1), or the difference is explained and re-reviewed.
  - The builder's `upgrade-3` fault spec must equal the one Phase 28a sent. Otherwise the difference
    is reported beside the 28a result.
- **F7. Fill the protocol's pins:** the freeze sha, configuration hash, manifest hash and
  supplementary function hashes. Save the diff. **Do not take the protocol's sha yet.**
- **F8. Fill the runner's pins** (never a protocol, runner or review-record sha). Save the diff.
  Re-run the runner's tests (after this last edit). Run the dry plan (`--plan`): it must show every
  pin `MATCH` and the configuration hash `pinned`. Record **S** = sha256(runner) and **H** = the plan
  hash.
- **F9. Add the launch line and take the protocol's sha.**
  - Add the bare line `Reviewed for launch: harness S plan H` to the protocol, and change its status
    line so it no longer says "NOT yet reviewed".
  - **Now** take **P** = sha256(protocol). Nothing edits the protocol afterwards.
  - The runner holds no protocol-sha constant, so there is no cycle.
- **F10. Approval record** `artifacts/phase28-<date>/review.json`. **Written only after the review
  rounds close** (R1-10, R2-4). **First:** the owner is told, in one plain sentence (below), that no
  held-out partition means a development-only result for good, and the record notes when.
  - **Approval:** `status: approved`; `approved_by: "Claude as PM, delegated by the project owner"`
    (the Phase 25-27 precedent); `decisions` 1–7 of §11 with the choice taken.
  - **Hashes and pins:** `protocol_sha256` P, `harness_sha256` S, `plan_hash` H,
    `gate_freeze_file_sha256`, `configuration_hash`, `manifest_hash`.
  - **Money:** `phase_cap` (150, or the §6.4 lowered value) and `remaining_budget_at_approval`.
  - **Records:** the review rounds, and the 28a decision with its manifest path.
  - **`approval_basis`,** quoted as **context only, not as this phase's approval:**
    `{"program_direction": "go ahead with whatever u recommend", "by": "Shree Bohara", "date":
    "2026-09-25", "relayed_by": "workflow harness", "scope": "the direction of Phases 28–31; each
    phase is still approved on its own"}`.
  - **The sentence for the owner:** "If we run Phase 28 without first sealing a new held-out test
    set, any upgrade repair it certifies can only ever be reported as a development result; it can
    never be checked on unseen cases."
- **F11. Commit and freeze.** Commit the protocol, runner and prep outputs to the backup branch.
  From F4 until the run ends: **no edit under `backend/app`, to the runner, `gate_freeze.py`, the
  drift or ingestion checks, `completion.md`, the settings or the protocol**, except the F7–F9
  fills.
- **Launch:** `--execute-live --confirm-entity <entity> --expect-plan-hash H --expect-harness-sha256
  S --expect-protocol-sha256 P --review-record artifacts/phase28-<date>/review.json --settings … --expect-freeze …`.

**Before launch** (Phase 23 §9 runbook, unchanged except the file names):
- ingestion health exits 0;
- the simulator was started only with `scripts/start-simulator.sh` (`--timeout-keep-alive 75`);
- the dashboard is closed, and loop latency p99 is under 100 ms, measured again after the restart;
- the backend was restarted deliberately on the frozen code with
  `artifacts/phase17-2026-09-23/launch_backend.py` (`78911a29…`, non-reload). It is idle, and
  `/api/config/status` shows the Phase 17 models and no active campaign;
- AC power, lid open, run under `caffeinate -is`.

**After the run:** run `check_clock_drift.py --worlds --require-worlds --since <started_at>` by hand,
and `--reconcile` with 0 discrepancies and 0 untracked studies.

Phase 28a follows the same F-step pattern on its own files (no F4–F6, because no backend change; its
configuration pin is `2cf63e93…`).

---

## 10. Held-out check: **not part of this phase**

- **heldout-2 is spent.** Phase 24 spent it, and it is never read.
- **The promotion partition is not usable here, for a real reason.**
  - It is recorded as spent only for `dd62c857…`, so the first draft's "both partitions are spent"
    was stronger than the record (R2-2).
  - The reason not to use it: it holds a transient-upgrade case (Phase 18), and Phase 28 now tunes
    on that fault family in development. A check there would not be held-out for the very
    mechanism being certified.
  - Also, a request with no partition runs predicate v1 on it (`heldout_check.check_plan`, 343-351).
    Phase 22 found that predicate cannot see a loss on transient upgrade failures.
- **A new partition would need its own backend change.** `excluded_identities()` compares only
  against `7ab9368e` (`heldout_check.py:287-301`). Novelty against `upgrade-v1` would be another edit
  to a frozen file, plus a generator rule, a seed committed before the loop runs, a seal and its own
  reviews (the Phase 22 pattern).
- **It could not answer the question well.** Neither held-out predicate can see a loss on transient
  upgrade failures (the floor). Phase 24's HARM came from a ~2% Actor report slip, not the policy.
- **It does not fit the reserve.** A Phase 24-sized check was capped at $87. With Phases 28–30 at
  their caps, $157.87 would fall to about $71.
- **The consequence, stated now and told to the owner before approval (F10):**
  - the seal must precede the policy (Phase 22), so choosing no partition now means **no policy
    certified in Phase 28 can ever get a held-out check**;
  - any certified upgrade repair stays a development-only result, and every write-up says so;
  - no reader of the store may treat a Phase 28 study's OBSERVED_IMPROVEMENT as a held-out-eligible
    certification.

---

## 11. Review plan and decisions

**Review plan.** At least two adversarial rounds before F4 for Phase 28, and before launch for Phase
28a. Each round uses independent lenses:
- **statistics and design:** the rule, N, the look, the probe's decision, power, and the read-outs;
- **backend change:** the diff, default-path identity, `source_clause` equivalence, and the tests;
- **runner and harness:** the copied main loop, identity, stops, the look's persistence, resume,
  reconcile, the guards, and the allowlist;
- **integrity and launch:** the freeze compare, the pins, the launch-gate order (no cycle),
  sequencing with Phases 29/30, the worktree, and the runbook.

A third round follows if round 2 changes code (pitfall 74). Every finding and its disposition go in
each protocol's Review log. Reviewer claims that prove wrong are recorded too. This design's own
round 1 is §16.

**Decisions** (recommendation first). Claude takes them as PM under the owner's delegation (the
Phase 25-27 precedent), and records them in `review.json`. Decision 7 is also told to the owner in
plain words before F10, and the phase waits if they object.
1. **Source:** `upgrade-3`, a free hedge (§4.3). Alternatives: restore Phase 17's direction (source
   `upgrade-2`, sibling `upgrade-3`), which is equal under the mechanism model; or `upgrade-4`.
   - **1b. The 7th validation case:** `lost-upgrade-response`. Alternative: `notification-18`, which
     exercises notification-side rules and costs about 10–15 more points of validation pass rate
     **[est]**.
2. **Futility look at D ≥ 16, kept behind the probe.** It costs about 9 points of power at *s* = 0.05
   and 5 at *s* = 0.10 **[est]**, corrected. Alternatives: no look (+9 / +5 points, up to about
   $37 more at *s* ≈ 0); D ≥ 12.
3. **N = 50 at $150.** Alternative: N = 40 at $130.
4. **Phase 28a first, as a declared go/no-go.** Alternative: skip it, and rely on the look alone.
5. **Build in a detached worktree from `backup/part2-2026-09-22` while Phases 29/30 run.**
   Alternative: wait until they close.
6. **The transposed source clause enforced in the backend** (`source_clause`). Alternative: runner
   only, with the §7.2 wording and a store-reader caveat.
7. **No held-out partition for this phase.** Alternative: seal one before the run, with its own
   backend change and budget.

---

## 12. Risks

| risk | effect | handling |
|---|---|---|
| **The baseline re-sends the upgrade itself** (10%–17% per `upgrade-3` episode) | about 4 attempts in 10 stop at controls, and a working candidate fails the source gate about 1 time in 3 **[est]** | declared; never loosened (pitfall 26). Measured precisely as a by-product (§7.7) |
| **The Mechanic never writes an orders re-send** (0 of 59 so far, though never shown upgrade evidence) | k = 0 | Phase 28a answers it for $5 before any build. The in-loop look saves about $35–40 more **[est]** if 28a is misled. The read-out bounds the rate |
| **Phase 28a's inputs differ from the loop's** (`local_only` labels; cross-store episodes) | the probe may over- or under-state *s* | declared (§6.0). It decides only go/no-go, and the in-loop look remains |
| **The look is reached late or never** (more `no_change` on upgrade evidence) | at *s* ≈ 0 the run costs up to about $72 instead of $35 **[est]** | declared cost bound (§6.2). 28a measures the rate first |
| **A re-send gated on `current_operation_pending`** | present, never fires (pitfall 77, upgrade side) | the fires predicate and the gate tally (§7.2); flagged statically in 28a |
| **Only one re-send when two are needed** | irrelevant for the source; `upgrade-18` fails any count by design | reported as the count of orders re-send steps |
| **A repair breaks the refusal case or a delayed success** (Phase 17 attempt 4: defer while PENDING) | validation NO_CHANGE | the gate catches it on `terminal-upgrade-rejection` and `delayed-upgrade`; §7.2 names the case |
| **A repair burns the budget or misreports after a failed re-send** | a candidate check failure on `upgrade-18` | a real harm; the gate rejects it; reported by case |
| **False regressions on `delayed-upgrade` and `lost-upgrade-response`** (B0 known from 6 episodes each) | an Actor lapse can read as a regression (about 5% of batches each **[est]**) | declared; reported as its own rejection reason |
| **Notification-side rules are never exercised** | a certified policy may carry an untested notification rule | stated in the primary's scope sentence (§7.1) and in §13 |
| **Actor report slips** (PENDING for UNKNOWN, ~2%) | candidate-arm violations, now mostly on `upgrade-18` | declared in §6.3; reported as rejection reasons |
| **The backend change has a defect** (e.g. the line-364 `KeyError`, or `source_clause` not equivalent) | INCOMPLETE studies; the breaker; or a wrong decision | §8.2's fake-runner tests and the property test; review; the first campaign is checked at $0; any condition-4 disagreement aborts |
| **Sequencing error** (the change lands before Phases 29/30 finish, or before 28a runs) | their harnesses refuse; no harm, but lost time | §9 sequencing; the landing check against `8994e962…`; the reviewer checks their results exist before F1 on the main checkout |
| **The held-out API accepts a Phase 28 study** | a held-out check nobody declared | `source_clause` removes the looser case; the rest is a procedural ban (§14), and the runner has no such code path |
| **Private-partition overlap** | the promotion partition has a transient-upgrade case (Phase 18), a fault family now in development | no held-out check follows. Any future partition must be built novel against `upgrade-v1` (seeds ignored) |
| **Correlated Mechanic draws** (temperature 0, correlated but not identical) | effective n smaller than 50 (and than 30 in 28a) | distinct-hash accounting (§7.3); 28a's intervals are labelled as understating uncertainty |
| **Lab defects** (dashboard freeze, keep-alive race, drift) | measurement errors | the Phase 19/23 runbook; the drift check after; reported, never re-run |
| **Pooling misuse** | a mixed-source "rate" | §7.6 is a count only, with the caveat |

---

## 13. What each result would and would not mean

- **Phase 28a NO_GO.**
  - *Would mean:* the Mechanic did not write an upgrade re-send in 30 first proposals shown
    upgrade-side evidence in this format (upper bound 11.4%). Phase 28 closes; no backend change is
    made.
  - *Would not mean:* that it cannot with another brief, temperature or model, or with
    `weave_verified` rows.
- **k ≥ 1, and the certified policies re-send the upgrade and it fires.**
  - *Would mean:* the unchanged loop also produced a certified repair for a **second, upgrade-side
    gap on development cases**, with no regression on `healthy`, the refusal case, the delayed
    upgrade, the unrecoverable upgrade or `lost-upgrade-response`, at a rate inside the Wilson
    interval.
  - *Would not mean:*
    - ACCEPTED;
    - held-out safety (none can follow, §10);
    - that it closes the notification gap;
    - that its notification-side rules are safe (never exercised here);
    - that it works beyond counts 2–3 (count 4, long F2 delays);
    - a difference from Phase 23;
    - **generalisation.** For a one-re-send policy, condition 3 is all but implied by condition 4,
      and it only tests the baseline on a sibling that works the same way (§5).
- **k ≥ 1, but a certified policy has no orders re-send.** It passed the rule, but the funnel shows
  it did not use the mechanism. Reported as certified, and flagged as not explained by the step.
- **k = 0 at `fixed_n`, with R ≥ 1.** "0 of 50 (Wilson upper bound 7.1%)". The Mechanic writes the
  step sometimes. The funnel names where attempts were lost:
  - the controls leak;
  - a step that never fires;
  - the source-gate leak;
  - dirty batches;
  - clean rejections, by case, including the transposed clause;
  - condition 3.

  It does not mean "impossible".
- **`futility`.** The Mechanic did not transfer the re-send idea to the upgrade, even with upgrade
  evidence in view (0 of D, upper bound about 19%), after a 28a GO. It would not mean it cannot with
  another brief, temperature or model.
- **`OBSERVED_IMPROVEMENT` but not certified** (no fresh gain). It passed the transposed gate but
  was not certified, and this is stated beside the primary. A source below 3 of 3 can no longer
  appear here: the backend records it as NO_CHANGE.
- **Truncated at the cap.** Many attempts reached validation, which is upstream success. The primary
  is quoted at n = j, never topped up.
- **Breaker or abort, not resumed.** Not a finding about the loop.

---

## 14. What must not happen

- **No early backend edit.** No edit under `backend/app` on the main checkout before Phase 28a has
  returned GO **and** Phases 29 and 30 have ended. On a 28a NO_GO, never.
- **No edit to a pinned earlier-phase harness:** `slot2_probe.py`, `report_word_probe.py`,
  `lapse_probe.py`, `run_gap_probe.py`, `run_full_loop*.py` or `run_dev_probe.py`. Import from
  them.
- **No edit to the gate or its inputs:** `assess_pairs`, `case_manifest()`, C1–C8, `checks.py`
  (never opened), the brief or the settings. No threshold loosened after any stop.
- **No held-out request of any kind** naming a Phase 28 study or policy. Nobody opens heldout-2 or
  the promotion partition.
- **No second chances:**
  - no operator replay, re-validation or resumption of any study;
  - no re-test of a candidate;
  - no stop at success; no top-up; no second `phase28-*` folder;
  - no change to N, the cap, the look, the case set or the read-outs once data exists, **including
    after Phase 28a's result**;
  - no second 28a run except the declared completion of undelivered requests.
- **No sha inside the file it depends on.** No protocol edit after F9, and no runner edit after F8.
- **Nothing called ACCEPTED;** no pointer moves; nothing activated. The manual-reference policy is
  never a candidate, never shown to the Mechanic, and never in 28a's contexts. No `private_*` record
  enters any model input.
- **Never quoted alone:** the primary always comes with the funnel, S4, the distinct certified
  policies, the guard-exercise table, the cumulative count, the Phase 28a result and the scope
  sentence.

---

## 15. Appendix: where the inputs are

Scratch folders (to be copied into `artifacts/phase28a-<date>/prep/` or `artifacts/phase28-<date>/prep/`
and re-run at the build, pitfall 84):

- **`…/scratchpad/p28-30/p28-understand/`:** the code reading and the data pass.
  - `census.py`, `rates.py`, `resends.py`, `mech_steps.py`, `costs.py`, `predictions.py` and their
    `.json` outputs;
  - `stats.txt`, `manifest-7ab9368e.json`, the count-4 draft manifest.
- **`…/scratchpad/p28-30/p28-design/`:** the first draft's inputs, kept for the record.
  - `draft_manifest_c3.py`: the old set, hash `c94ade05…`;
  - `design_numbers.py` / `.json`: the old set, with the independence approximation in the look;
  - `evidence_bundle_check.py` → `.out.txt`: 0 of 63 stored evidence records; 5,223 in the main
    store.
- **`…/scratchpad/p28-30/p28-revise/`** (this revision):
  - `draft_manifest_r1.py` → `draft_manifest_r1.out.txt`, `draft-upgrade-v1-r1.json`: the §4.1
    mirror, hash `cafe5757…`, not a pin;
  - `design_numbers_r1.py` → `design_numbers_r1.json` / `.out.txt`: every §6 **[est]** figure,
    the corrected look formula, the check reproducing the reviewer's 0.344 / 0.628 / 0.128, the look
    timing scenarios, and 28a's operating characteristics;
  - `gated_rule_check.py` → `gated_rule_check.out.txt`: the read-only re-check of which Phase 20/26
    L episodes ran a step, and of events against distinct calls per Actor upgrade;
  - `PHASE28_DESIGN.before-r1.md`: this file before revision 1 (sha `eb82edee…`).

---

## 16. Design review (round 1, 2026-09-25): every finding and its disposition

Two independent reviewers ran read-only at $0. Both returned **RUN_WITH_CHANGES**, with 1 blocker, 4
majors and 9 minors. Every finding is **accepted and fixed in this revision**. None was rejected.
Where the fix took one of the reviewer's options, the choice is named.

| # | reviewer · severity | where (first draft) | finding, in short | disposition | changed in |
|---|---|---|---|---|---|
| R1-1 | 1 · major | §8.3 pins; §9 F7–F10 | **The protocol and runner hashes form a cycle.** The runner pinned the protocol sha, and the protocol's launch line named the runner sha. A plan over `fixed`'s `declared` dict would inherit it | **Fixed: Phase 25/27 scheme in full.** No protocol-, runner- or review-record-sha constant. `--expect-protocol-sha256`, `--expect-harness-sha256` and `--expect-plan-hash` are passed on the command line. The plan is a dict of design constants and pins only. The protocol sha is taken after the launch line. Tests: a protocol edit after the line refuses; the plan hash is invariant to protocol edits | §8.3, §8.4, §9 F7–F10, §14 |
| R1-2 | 1 · major | §3.4; §2 row 11; §6.2 | **A Mechanic-only probe is possible.** Bundles can be rebuilt locally (`evidence.py:49-78`), and about 20–40 calls cost $1–2, against about $35 to reach the look | **Fixed: Phase 28a adopted** ($5 cap, 30 draws, GO if ≥ 1 orders re-send), a declared go/no-go before the backend change. The input differences are declared, and the in-loop look is kept. Also added: a positive control proving the local rebuild exact | §0, §2, §3.4, §6.0, §8.4, §9, §11, §13 |
| R1-3 | 1 · minor | §8.1 item 1, "what moves"; §9 F4 | Inserting the builder after `case_manifest()` would move `planned_slots` and `assess_pairs` line ranges. `api.py` has no file entry in `gate_freeze` | **Fixed:** all new code is appended after `_execute`; whole-entry comparison including `lines`; the `api.py` file entry is removed from the list; the new functions get supplementary hashes, since `gate_freeze.py` is pinned | §4.2, §8.1, §9 F4 |
| R1-4 | 1 · minor | §8.3 own/reused lists | The own-function list was incomplete: `add_funnel`, `summarize_fixed_n`, `hash_accounting`, `primary_statement`, `routing`, the pin helpers, and the in-`main` `recover` resolve to notification or Phase 23 code | **Fixed:** every one is added to the own list; an **allowlist** AST test fails on any other attribute read from `base`, `fixed` or `slot2_probe` | §8.3 |
| R1-5 | 1 · minor | §6.2; §6.5 | The look has no evaluation point or persisted state. An abort between crossing and evaluating could skip it on resume | **Fixed:** evaluated at the top of the loop; `manifest['futility_look']` written in the same save as a stop; `FUTILITY_LOOK_D` and the predicate in the plan; resume rules; `futility` final in `reconcile`. Each case is tested | §6.2, §6.5, §8.3 |
| R1-6 | 1 · minor | §6.3; §11 decision 2 | Power with the look was overstated (the independence assumption). The look timing assumes Phase 23's 1.19 distinct policies per study | **Fixed:** corrected formula; the table recomputed for the revised set; the reviewer's figures reproduced (0.343 against 0.344, 0.629 against 0.628, 0.128 against 0.128); the look costs about 9 and 5 points, not 6 and 3; the timing assumption and a **$72 never-reached cost bound** declared; 28a measures the rate | §6.2, §6.3, §6.4, §11 |
| R1-7 | 1 · minor | §7.7; step predicates | Counting `tool_dispatched` events counts every F4 episode as an Actor re-send, because the adapter makes two attempts per call | **Fixed:** at least 2 **distinct `call_id`s**. Re-checked: events ≥ 2 in 63 of 63 F4 L episodes, distinct calls ≥ 2 in 0 of 63. A test pins it on a stored episode | §3.1, §7.7, §8.3 |
| R1-8 | 1 · minor | §6.4 | "~60% stop cheaply at controls" contradicted the model (controls pass 0.52–0.68) | **Fixed:** "about 40%" | §6.4 |
| R1-9 | 1 · minor | §9 step 2 | A worktree from main HEAD `cbbf957` is stale, and it has no `.venv` or `artifacts/` | **Fixed:** a `--detach` worktree from `backup/part2-2026-09-22` (`3cda105`, shas verified equal), or a scratch copy; the main `.venv` interpreter; no artifacts symlink; a `diff -rq` check before building; the landing check against `8994e962…`; F2 re-run on main | §9 |
| R1-10 | 1 · minor | §9 F10 | The owner's general direction was pre-written as this phase's approval quote, before the protocol existed | **Fixed:** `approved_by` and the record are written after the review closes; the quote is kept as `approval_basis` context only | §9 F10, §11 |
| R2-1 | 2 · **blocker** | §4.1, §4.3, §7.4, §13 | **The validation set would not catch most harmful upgrade repairs.** `lost-upgrade-response` and both notification guards never run a gated rule. `dev-3` and `upgrade-18` were dropped for pass-rate reasons | **Fixed:** the selection rule is stated ("what each guard can catch; costs declared, never used to rank"). `notification-1` → `delayed-upgrade` (`dev-3`), and `lost-notification-response` → `upgrade-18` (SAFE_UNRESOLVED), both of the reviewer's suggestions. `lost-upgrade-response` is kept with an honest rationale, with `notification-18` offered as decision 1b. A per-case "rules ran / not exercised" read-out is added, and so is a scope sentence in every primary. The net pass rate for a working repair **rises** (0.47–0.75 → 0.54–0.82 **[est]**), because the notification-fault nuisance leaves | §0, §3.2, §4.1, §4.3, §6.3, §7.1, §7.4, §7.5, §13 |
| R2-2 | 2 · major | §0, §2 row 5, §5 cond. 4, §7.2, §8.1, §10, §14 | **Condition 4 lived only in the runner.** The store would record OBSERVED_IMPROVEMENT where Phase 17's gate says NO_CHANGE, visible to the held-out API and other readers. "Both partitions are spent" was stronger than the record | **Fixed with the reviewer's option (a):** the backend `source_clause`, applied after both validation `assess_pairs` calls, gives the same decision and reason as `assess_pairs` with the literal replaced (property-tested). `assess_pairs` text is untouched. The runner re-checks it, and a disagreement aborts. "The unchanged gate" is replaced by "the transposed gate". §10 gives the real reason: the promotion partition overlaps the fault family tuned on here | §0, §2, §5, §7.2, §8.1, §8.2, §8.5, §10, §13 |
| R2-3 | 2 · major | §4.3; §5 cond. 3; §13 | **The selection satisfies condition 3** for one-re-send policies (pitfall 73). "Generalises" overstates it. The source choice rested on a point estimate the design called not real | **Fixed:** §5 states that condition 3 is all but implied by condition 4 and only tests the baseline. §13's wording becomes "a certified repair for a second, upgrade-side gap on development cases", and "would not mean" adds counts beyond 2–3 and generalisation. `upgrade-3` is kept with a **corrected rationale**: arbitrary by mechanism, a free hedge, reverses Phase 17's direction (stated). Restoring the direction is decision 1's alternative | §4.3, §5, §11, §13 |
| R2-4 | 2 · minor | §9 F10; §11 decision 5; §10 | The approval record used the program-level "go ahead" as approval of irreversible decision 5 (no partition) | **Fixed:** the quote is recorded as program direction only. Decisions 1–7 are taken by Claude as PM under delegation (the Phase 25-27 precedent). Before F10 the owner is told, in one plain drafted sentence, that no partition means development-only for good | §9 F10, §10, §11 |

**Reviewer claims re-checked in this revision** (read-only, $0):
- the F1 and F2 rule-execution counts and the events against distinct calls (`gated_rule_check.out.txt`);
- the backup-branch shas (all four equal to disk);
- `gate_freeze.py`'s `FILES` list (no `api.py`);
- the `source` field in `summarize_evidence` rows (`diagnosis.py`);
- `business.py:92`'s 18-attempt refusal;
- the corrected power figures.

The main-store notification-rule counts (0 of 24, 0 of 24, 24 of 24, 21 of 24) are the reviewer's
and were not re-queried; §3.2 labels them so.

**Also found while revising** (not raised by either reviewer, fixed here):
- **The first draft's validation cost of $4.36 is now $5.04.** `delayed-upgrade` and `upgrade-18`
  episodes cost more.
- **Replay stays on the default manifest.** With a non-default manifest the replay path would be
  unreviewed, so it is now refused.
- **The control id is pinned.** `build_case_manifest` refuses a non-`healthy` control, so line 142's
  healthy clause can never go inert.

---

## 17. Build list

Nothing below is built in this workflow. Every file is created or changed only in its phase's build
step, after that phase's review plan (§11).

**Phase 28a (build now; scripts only; no `backend/app` change):**

| # | file | kind | create / change |
|---|---|---|---|
| A1 | `scripts/experiments/mechanic_upgrade_probe.py` | script (harness) | create (§8.4) |
| A2 | `backend/tests/experiments/test_mechanic_upgrade_probe.py` | test | create (§8.4) |
| A3 | `docs/part2/PHASE28A_EXPERIMENT.md` | protocol | create, from §6.0 |
| A4 | `artifacts/phase28a-<date>/` (plan, dry plan, prep copies of `p28-revise/`, `review.json`, the run folder) | records | create |

**Phase 28 (only after a 28a GO; built in the detached worktree; landed after Phases 29/30 close):**

| # | file | kind | create / change |
|---|---|---|---|
| B1 | `backend/app/lab/completion_study.py` | **backend** | change. `queue_completion_study`: the `case_manifest_id` parameter, `build_case_manifest` at line 170, the replay refusal, and the record key. `_execute`: `check()` rebuilt by recorded id (line 238), source and control ids from the manifest (line 364), and `source_clause` around the validation calls at lines 357 and 437. **Appended after `_execute`:** `upgrade_case_manifest`, `CASE_MANIFESTS`, `DEFAULT_CASE_MANIFEST`, `build_case_manifest`, `source_clause` (§8.1) |
| B2 | `backend/app/lab/api.py` | **backend** | change: `CompletionStudyRequest.case_manifest_id`; the route passes it (§8.1 item 9) |
| B3 | `backend/tests/lab/test_completion_manifests.py` | backend test | create (§8.2) |
| B4 | configuration-pinned test files in `backend/tests/experiments/` that fail rather than skip once the tree moves (found now: `test_report_word_probe.py`, `test_report_narrow_probe.py`, `test_slot2_hidden_probe.py`, `test_run_gap_probe.py`; the final list comes from F2) | backend test | change **only if** one fails instead of skipping: a declared skip condition, as for `test_lapse_probe.py` in Phase 22. Pinned harnesses are never edited |
| B5 | `scripts/experiments/run_upgrade_loop.py` | script (runner) | create (§8.3) |
| B6 | `backend/tests/experiments/test_run_upgrade_loop.py` | test | create (§8.3) |
| B7 | `artifacts/phase28-<date>/prep/manifest_hash.py`, `draft_manifest_r1.py`, `freeze_compare_p28.py`, `new_function_hashes.py`, `design_numbers_r1.py`, with their saved outputs | scripts (prep, $0) | create (§8.3) |
| B8 | `docs/part2/PHASE28_EXPERIMENT.md` | protocol | create, from this design |
| B9 | `artifacts/phase28-<date>/` (`gate-freeze-after.json`, configuration-hash outputs, diffs, `review.json`, the run folder) | records | create |

**Not changed, by declaration:**
- `assess_pairs`, `case_manifest()` and `planned_slots`;
- `heldout_check.py`, `checks.py` (never opened), `completion.md` and the settings;
- `gate_freeze.py`, `check_clock_drift.py` and `check_ingestion_health.py`;
- every earlier-phase harness and runner (`slot2_probe.py`, `report_word_probe.py`, `lapse_probe.py`,
  `run_gap_probe.py`, `run_full_loop.py`, `run_full_loop_fixed_n.py`, `run_dev_probe.py`,
  `run_heldout*.py`);
- everything under `backend/app` except B1 and B2.

---

## 18. Recommendation: go / no-go

**Phase 28a: GO. Build it and put it through review now.**
- **Why:** it is scripts only, capped at $5, and it needs no backend change and no new freeze. It
  answers the design's largest unknown first: does the Mechanic ever write the upgrade re-send when
  shown upgrade-side evidence? That costs $5 instead of the $35–72 that the loop would spend
  reaching its own look.
- **When it runs:** after its two review rounds, whenever no other paid run is live. The guard
  enforces that, so Phases 29 and 30 are not disturbed.

**Phase 28, the loop run: CONDITIONAL GO. Build it only after a 28a GO.**
- **When:** land it only after Phases 29 and 30 close, and launch it only after its own review
  rounds pass on the built code, F1–F11 are complete, and the approval record is written.
- **Why it is worth running:**
  - every round-1 finding is fixed on paper;
  - the launch gates have no hash cycle;
  - the stored decision now equals Phase 17's gate, for every reader;
  - the revised validation set exercises a repair's gated upgrade rules on four cases instead of
    one;
  - dropping the notification-fault nuisance raises, rather than lowers, the chance a working
    repair passes (0.54–0.82 **[est]**);
  - at *s* = 0.10 the run has about a two-in-three chance of a certification, for an expected
    $78 **[est]**, inside a $150 cap that leaves at least $157.87.

**Hard no-go conditions (any one stops Phase 28):**
- Phase 28a returns NO_GO. It is 0 of 30, and the backend change is never built.
- Phase 28a is INCOMPLETE and its completion is not approved.
- A review round finds that `source_clause` does not give the same decision as `assess_pairs` with
  the literal replaced, or that the freeze compare moves any undeclared entry.
- Phases 29 and 30 have not both closed when the change would land.

Not a stop, but a change: if the remaining budget at approval is below $300, the cap is lowered to
(remaining − $150) by the §6.4 rule, and N stays 50.

## 19. Approver decisions (2026-09-25; Claude as PM, delegated by the project owner)

All seven recommendations in §11 are taken:
1. Source `upgrade-3` (1b: the 7th validation case is `lost-upgrade-response`).
2. A futility look at D ≥ 16, behind the probe.
3. N = 50 at $150.
4. Phase 28a first, as a declared go/no-go.
5. Build in a detached worktree from `backup/part2-2026-09-22` while the replay probes run.
6. `source_clause` enforced in the backend.
7. **No held-out partition for this phase.** Decision 7 was told to the owner in plain words on
   2026-09-25: a repair certified in Phase 28 can never get a held-out check. The phase waits if
   the owner objects before F10.

**Phase 29 is cancelled** (see `PHASE29_EXPERIMENT.md`). Only Phase 30 must run before the
backend change.

**Budget:** $652.90 charged, $347.10 left. Phase 30 ($20) + 28a ($5) + 28 ($150) at their caps
would leave about $172.

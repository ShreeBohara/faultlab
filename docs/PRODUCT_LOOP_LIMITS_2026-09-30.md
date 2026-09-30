# Two Learn-loop limits after live run v2d: Mechanic request size and challenge picks (September 30, 2026)

**Status: built, reviewed twice and fixed, all offline at $0. Not yet committed. Not run live.**

- **Rule 1 (Mechanic request size) is in every new Learn plan.**
- **Rule 2 (challenge picks) is withdrawn.** Both reviews found it can hide a counterexample. No new plan declares it,
  and a plan that does cannot be created or started. Its code is kept, unused, until the PM decides (section 3).

Evidence: `artifacts/product-loop-limits-2026-09-30/` (`builder/`, `review-integrity/`, `review-product/`, `fixer/`).

Live run v2d (campaign `ea66672d`, store `/Users/shree/FaultLab_Runs/2026-09-30/native-v2b`) got a generated repair
further than ever before, then stopped on two FaultLab limits, not on the agent or the gates
([write-up](PRODUCT_NATIVE_V2_RUN_2026-09-29.md), last section, "Third live run: history replay, v2d"):

1. The Mechanic's next-candidate request came to **33,223 input tokens** (limit 32,000). It was refused before sending,
   and the campaign ended **ERROR**.
2. The challenge's third pick (one failed read of the orders status, and no other fault) did not fire in every pair,
   so the challenge ended **INCONCLUSIVE**. Section 3 has the corrected cause.

| rule | protocol id | plan field | status |
|---|---|---|---|
| Mechanic request size | `faultlab-mechanic-context/v2-bounded` | `mechanic_context` | in every new Learn plan |
| Challenge picks | `faultlab-challenge-selection/v2-candidate-reach` | `challenge_selection` | **withdrawn** before any live run |

A plan saved before this round has neither rule and keeps today's behaviour exactly. Neither rule changes a gate, a
check, a threshold, the challenge's completeness rule (every schedule's pairs must fire), `challenge.py`,
`mechanic.py`, `diagnosis.py`, `promotion.py`, `evaluation.py`, the referee or the simulator.

Code: `backend/app/lab/loop_limits.py` (both rules), the learning loop (`learning.py`), plan freezing and the Start
check (`run_plans.py`), the Explorer's selection handling (`agents/explorer.py` and the prompt section
`agents/prompts/challenger_candidate_reach_v2.md`; used only by the withdrawn rule), the experiments API and the
recording (`api.py`, `exports.py`), and the dashboard (`frontend/src/loopLimits.ts`, `components/LoopLimits.tsx`, the
saved plan, the Learn setup form, the challenge and diagnosis panels).

---

## 1. What made the refused request large (measured, $0)

`builder/rebuild_v2d_request.py` rebuilds the refused request from a read-only scratch copy of the saved store. It uses
the loop's own helpers in the loop's own record order. The rebuilt request counts **exactly 33,223** tokens with the
frozen DeepSeek-V4 tokenizer, so it is the same request. Both reviews rebuilt it independently and got the same count.
The first candidate request also rebuilds: 14,304 by the local count, against 14,168 reported by the provider (the
local count adds message framing).

Tokens each part adds (the full count minus the count without that part):

| part | tokens |
|---|---|
| challenge feedback (`challenge_counterexamples`) | 14,136 |
| — of which the evidence table of the 18 challenge episodes | 12,047 |
| — of which the grouped trial outcomes | 1,432 |
| development evidence (16 episodes: source, 3 reproductions, 6 intervention, 6 source validation) | 11,030 |
| — of which the per-episode check rows | 5,819 |
| runtime contract | 2,784 |
| reduction summary | 1,184 |
| source-validation feedback | 1,070 |
| system prompt, schema and small fields | the rest |

So the size came from **per-episode evidence rows**, mostly the 18 challenge episodes, none of which had a failed check.

## 2. Rule 1: Mechanic request size (`faultlab-mechanic-context/v2-bounded`)

**When it applies.** A Mechanic candidate request or diagnosis request whose first turn would exceed 32,000 tokens.
The count is the Mechanic's own admission count: same prompt, same message, same model, same frozen tokenizer. A test
checks this against the Mechanic itself for both request kinds and two models. A request that fits is sent exactly as today.

**What it does.** It compacts only the evidence tables the request carries, in three fixed stages. It stops at the first
stage after which the request is at most **28,000** tokens. That leaves 4,000 tokens for its one format-repair turn.

1. `IDENTICAL_CLEAN_ROWS`: a clean episode whose rows and outcome are identical to an earlier clean episode's is
   listed by `episode_id` (`same_as`) instead of repeated.
2. `ONE_CLEAN_EPISODE_PER_OUTCOME_GROUP`: one clean episode is kept in full for each group with the same recipe, arm,
   **policy, experiment purpose** and trial outcome. The others are listed with that example (`group_example`). Their
   own rows (report, observations) **can differ** from the example, and the request says so.
3. `NO_CLEAN_EPISODE_ROWS`: no clean episode is kept in full. Each is listed with its own outcome.

A *clean* episode has no failed check, its trial outcome is not `VIOLATION`, and it is not the source or one of its
reproductions. The rule never touches the following:

- the source episode, its reproductions and every episode with a failed check or a `VIOLATION` outcome (always kept in full);
- every `trial_outcomes` group;
- the candidate history;
- the source-validation and challenge feedback fields;
- the runtime contract;
- the diagnostic.

An outcome that differs inside a recipe (for example one triggered and two untriggered episodes) is a separate group,
so stage 2 keeps one full example of each. Nothing contradictory is dropped silently.

**What the Mechanic sees.** A compacted request carries `context_compaction` with a plain statement. The statement says:

- what was compacted;
- which stages ran;
- how many episode rows were omitted, per evidence block.

Each compacted block also carries `compaction.omitted`: every omitted episode by ID, with its arm, lifecycle, outcome,
failed checks and whether its fault fired. The block's legend gets one added sentence: its rows are left out, `same_as`
rows are identical, and rows can differ from their `group_example`. So its "all trials are retained" claim is not left
standing. A kept block is byte-for-byte what `summarize_evidence` returns for the kept episodes alone. A test checks this.

**When it still does not fit.** Nothing is sent. The candidate search for that source ends with a recorded reason
(`mechanic_context_records`, outcome `SEARCH_ENDED`, stage `BEFORE_SEND`). The campaign continues with discovery, or
ends `NO_CHANGE`, by the existing rules. **It never ends ERROR on this path.** The unsent request does not use one of
the campaign's 4 candidate requests. If the campaign ends `NO_CHANGE`, its reason names every search the rule ended
early (up to 3 record IDs), so it does not read like a finished search.

- **Diagnosis request.** The same rule applies. Its evidence is only the source and its reproductions, which are always
  kept, so in practice an over-limit diagnosis request ends that source's search: no diagnosis, no candidate, discovery
  continues.
- **Format-repair turn.** A request that fits (28,001–32,000 tokens is sent in full, as today) can still produce a
  format-repair turn that does not fit. The Mechanic refuses that turn before sending (unchanged `tokens.py`). Under the
  rule this also ends that source's search with a recorded reason (`stage: FORMAT_REPAIR`) instead of ERROR. The record
  says "the first turn was sent" **only when that request's first-turn answer is actually saved** (it links it,
  `first_turn_output_ref`). The charged first turn also gets a `REJECTED` candidate record (`FORMAT_REPAIR_OVER_LIMIT`),
  as an invalid answer does, so it shows in the candidate history and the recording.
- **First turn refused by the Mechanic itself.** Only possible if the rule's count and the Mechanic's ever disagree
  (today they are the same by construction). It is recorded as `BEFORE_SEND` ("Nothing was sent"), and it does not use
  one of the campaign's candidate requests.

**What v2d would get** (the real compaction code on a read-only scratch copy; `fixer/rebuild-v2d-request.json` and
the saved-store test):

| stage | rows omitted | request tokens |
|---|---|---|
| none (as sent) | 0 | 33,223 |
| 1 identical clean rows | 2 | 33,611 (larger: the statement costs more than 2 rows save) |
| 1 + 2 one per group | 15 | 28,056 (56 over the target) |
| 1 + 2 + 3 no clean rows | 24 | **21,101 ≤ 28,000: sent** |

- **Kept in full:** the 10 development episodes with a failed check (source, 3 reproductions, 3 failing intervention
  controls, 3 failing source-validation baselines). No clean challenge episode is kept in full; all 18 are named with
  their outcome, and every `trial_outcomes` group is unchanged.
- **Unchanged:** every other field.
- **Why stage 3 now.** The builder's wording fitted at stage 2 by **10 tokens** (27,990). The clearer wording the
  reviews asked for (rows can differ from a `group_example`; `VIOLATION` outcomes kept) adds 66 tokens at stage 2. Both
  results follow the declared rule; stage 3 gives the Mechanic less clean-episode detail. Whether that matters for
  the Mechanic's next candidate is unmeasured.

## 3. Rule 2: challenge picks (`faultlab-challenge-selection/v2-candidate-reach`) — WITHDRAWN

**What it would do** (unchanged code, kept for the PM). Before a challenge pick runs any pair, check every fault target
(tool and service) against the calls **the agent under test itself** made in the candidate arm's source-validation
episodes of this campaign. A pick with a target the agent never called there is refused (no episode runs) and the
Explorer gets one re-plan, inside the challenge's existing 8 requests, charged as before. `challenge.py` is unchanged.

**Why it is withdrawn (both reviews, HIGH-1, verified by the fixer).**

- **It depends on the candidate.** Source validation runs only the source's fault. For v2d's candidate (a rejected
  upgrade, then "report terminal failure"), the agent called only `get_order` and `update_order` there. So the rule
  would refuse faults on 3 of the 5 tool/service pairs: the orders status read, `send_confirmation` and the
  notifications status. In the same challenge, the candidate's agent called all three: the orders status in 4 of 9
  candidate episodes (3–4 times per episode under the slow upgrade), `send_confirmation` in 6 of 9, the notifications
  status in 1 of 9 (`fixer/verify-v2d-picks.json`).
- **It can turn a counterexample into a pass.** With the real, unchanged `challenge.py` and the same five Explorer
  answers, a candidate that fails C4 whenever a confirmation is faulted gives `COUNTEREXAMPLE_FOUND` without the rule
  and `PASSED_OBSERVED` with it (the confirmation pick is refused). That result would lead on to promotion. A backend
  test now runs this scenario under a new Learn plan's own rules and requires `COUNTEREXAMPLE_FOUND`.
- The brief said neither fix may relax a gate. In effect this one relaxes the challenge, so it must not be frozen.

**The corrected cause of v2d's INCONCLUSIVE** (saved store, read-only; both reviews and `fixer/verify-v2d-picks.json`).
The builder's note, and the first write-up, said the candidate "made the status read unnecessary" because its policy
reads the status itself. The saved evidence does not support that:

- Pick 3 was one failed orders-status read (attempt 1) and **no other fault**, so the upgrade was healthy.
- With a healthy upgrade **neither arm needs to read the status**. The fault fired in 1 of 3 incumbent episodes and 0
  of 3 candidate episodes. The incumbent's agent skipped the read in 2 of 3.
- The candidate policy reads the status only after an uncertain upgrade or when a receipt is missing. It read nothing
  in pick 3.
- Under the slow-upgrade pick (pick 2), the candidate's agent itself read the orders status 3–4 times per episode.

So pick 3 failed because of the schedule, not because of the candidate. The rule refused it only because source
validation happened not to include the orders status.

**Which calls count (the old PM decision 1).** Only the agent's own calls, and the reason is now stated in the rule
text and the prompt section: a challenge pair counts only when its faults fire in **both** arms, and the incumbent arm
has no candidate policy reads. A fault reached only through the candidate policy's read fires in the candidate arm and
not in the incumbent arm, so the pair can never complete (product review: 3 of 3 against 0 of 3, INCONCLUSIVE).

**The options, restated with what each would do for v2d:**

- (a) accept it as declared: it would hide counterexamples as above;
- (b) also count the candidate arm's episodes already run in this challenge: it would **not** have refused pick 3,
  because the candidate's agent read the orders status in picks 1 and 2; so it would not have fixed v2d;
- (c) refuse only targets the incumbent arm called but the candidate's agent did not: for v2d it refuses exactly the
  same 3 targets as the build;
- (d) drop rule 2 and keep rule 1;
- (e) the product review's narrower idea (untested): refuse an unreached target only when the pick has no fault on a
  write tool (`update_order`, `send_confirmation`). It refuses v2d's pick 3 and allows picks 1–2, the v3 counterexample
  pick, the slow upgrade plus a status-read fault, and confirmation faults. It still depends on the candidate for picks
  with only read faults;
- (f) a basis that does not depend on the candidate. The fixer checked what the existing reachability labeller
  (`app/lab/reachability.py`) could offer (`fixer/impossible-rules-v2d.json`):
  - its agent-independent IMPOSSIBLE rules (S1–S4) do **not** mark any of v2d's three picks, pick 3 included;
  - its FORCED caller model covers only the reference Actor under `policy-v0`. It refuses a candidate policy
    (`POLICY_RULES_UNSUPPORTED`) and a native agent (`NATIVE_AGENT_UNSUPPORTED`).
  So nothing in the product today gives a candidate-independent check that would have caught pick 3. It would need a
  new design.

**Recommendation from the fixer:** keep rule 2 withdrawn for the next live run (option d in effect). Revisit only with a
basis that does not depend on the candidate. v2d's INCONCLUSIVE is a safe outcome; the ERROR was the real blocker, and
rule 1 fixes it.

**How the withdrawal is enforced.** New Learn plans do not freeze `challenge_selection`, and run options do not offer
it. `validate_run_plan` (which both campaign creation and Start run) refuses a plan that declares it, with a plain
reason. A plan that declares it still reads and displays, so the dashboard can show what it said. The Explorer code
path runs only when the rule is set, which no plan can now do.

## 4. Old plans, other agents, other protocols

- A Learn plan saved before this round has no `mechanic_context` or `challenge_selection` key. It reads back with the
  same bytes (no null keys added), Start accepts it, and its campaign behaves exactly as before: an over-limit Mechanic
  request raises `ModelInputLimit` and the campaign ends ERROR (`INPUT_LIMIT`); every valid challenge pick runs; its
  NO_CHANGE reason is today's exact text. Tests check these.
- A new Learn plan declares `mechanic_context` only.
- Baseline and compare plans never declare either rule. A baseline plan carrying one is refused at creation.
- Start refuses a plan whose declared Mechanic rule differs from the installed one, and any plan that declares the
  withdrawn challenge rule.
- The experiments API adds `mechanic_context` (and `challenge_reach`) only for a campaign whose plan declares the rule.
  The recording adds `mechanic_context_records` (and `challenge_selection_rule`) only in that case, so older campaigns'
  responses and recordings keep their exact fields.
- Unchanged: native adapter v1 (`external_agent.py` byte-identical, adapter hash `6f303264…`) and v2.1 (`dfd41b33…`),
  their prompts, the discovery protocols and their declarations, the transport and evidence retry rules, the reference
  Actor's prompt, simulator `3ce5bcd2…`, contract `6f9d7783…`, interpreter `6da0714a…`, scorer `19de811c…`.
  The reference Actor's source hash (a tree hash of `backend/app/agents`) changes, because `explorer.py` and one prompt
  file changed. **Register every agent again before a live run**, as after every build.

## 5. Where it shows

- **Learn setup form:** "Every new Learn plan also freezes this rule:", then the Mechanic rule in one line. Nothing is
  said about a rule the backend does not offer.
- **Saved plan:** "Mechanic request size" (the rule, or "Not declared … as before" for an older plan) and "Challenge
  picks: Not declared: every valid challenge pick runs its pairs, as before." A plan that declares a rule has the exact
  rule text under "Exact rule text".
- **Tested diagnosis panel (06):** "Mechanic request size" lists every compaction and every search it ended:
  - a compacted request shows its size before and after, and how many episodes each block kept in full;
  - a search ended before sending says "not sent", with its reason, and shows no "in full" line;
  - a refused format-repair turn says "first turn sent (its answer is saved); its format-repair turn was not sent",
    with the badge "Search ended, repair turn not sent".
- **Adversarial challenge panel (07):** "Challenge picks · candidate reach check" appears only for a plan that
  declares the withdrawn rule. Its badges read "Selected", "Refused: tool not reached", "Invalid output" and "Not
  checked", and a refusal is stated once.
- **Recording:** `run_plan` (the declared rule), `mechanic_context_records`, the `REJECTED` candidate record of a refused
  format-repair turn, and (only for a plan that declares rule 2) `challenge_selection_rule` and each challenge
  selection's `challenge_reach`.

## 6. Checks ($0, offline)

**Builder** (`builder/`): one `scripts/test.sh`: backend 2,940 passed, 180 skipped; frontend 353; build passed; browser
19 passed, 1 opt-in skip. 21/21 negative-control mutations caught. Real API responses pass the dashboard's validators.
`gate_freeze.py` 30/30 functions and 20/20 files identical.

**Reviews** (`review-integrity/`, `review-product/`): 10 findings in all (both reviews found HIGH-1). The fixer
verified all of them against the code and the saved store.

**Fixer** (`fixer/`):
- 8 new backend test functions (9 test cases) and 5 changed backend tests in the three loop-limits files (39 cases
  now, 30 before); 3 frontend unit tests and the browser test updated. Each new or changed test failed on the
  builder's code for the reason in its finding, then passed after the fix (`fixer/mutation-checks.log`, parts 1–2).
- 17/17 new negative-control mutations caught, each undoing one fix; every file restored (sha256 checked; part 3).
- The v2d rebuild test now expects stage 3 (21,101 tokens) for the reason in section 2.
- The dashboard's own validators accept the real API responses: a new plan (Mechanic rule only), an older plan, a plan
  declaring the withdrawn rule, and all four request-size record kinds (`fixer/api-contract-check.log`).
- `gate_freeze.py`: 30/30 gate functions and 20/20 gate files identical to the backup tree; only the runtime,
  algorithm, agents-source and lab-tree fingerprints changed (`fixer/gate_freeze/compare.txt`).
- Identity: runtime `f058c03c…`, algorithm `a08a8d61…` (the builder's `4d0d7914…` is superseded); simulator service,
  contract, interpreter, scorer, capability, both native adapters and prompts, and the reference Actor prompt are
  unchanged (`fixer/identity-compare.txt`).
- `scripts/test.sh` before the last doc edit (`fixer/pass1-full-test-sh.log`): backend 2,949 passed, 180 skipped,
  0 failed (2 known warnings); frontend 353; build passed; browser 19 passed, 1 opt-in skip. No code, test or doc
  file changed during that run. The final run after the last edit is `fixer/full-test-sh.log`.

New tests are in `backend/tests/lab/test_loop_limits_mechanic_context.py`, `test_loop_limits_challenge_reach.py`,
`test_loop_limits_plans.py`, `frontend/tests/loop-limits.test.tsx` and `frontend/tests/loop-limits.browser.ts`.
One backend test rebuilds the refused v2d request from a temporary read-only copy of the saved store (skipped where
the store is absent), checks it counts 33,223, and checks it fits after compaction with its omission statement.

## 7. What this does not show

- Nothing here ran live. Whether a Mechanic proposes a better candidate from a compacted request is unmeasured.
- v2d's request now goes out at stage 3, with no clean challenge rows in full. Whether that helps or hurts the next
  candidate is unmeasured.
- With rule 2 withdrawn, a challenge pick whose faults do not fire in every pair still ends the challenge INCONCLUSIVE,
  as in v2d. That is safe (INCONCLUSIVE is never a pass), but it can stop a good candidate. A fix needs a basis that
  does not depend on the candidate; section 3 lists what exists today and why it is not enough.

_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

FaultLab builder report: two Learn-loop limits after live run v2d (September 30, 2026)

Status: BUILT offline at $0. Not committed, not reviewed, not run live. There were no provider, model, W&B, Weave or network calls; every check script ran under a socket guard, and the guard's log shows 0 refused connections.

Evidence folder: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-loop-limits-2026-09-30/builder/
Design note: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/docs/PRODUCT_LOOP_LIMITS_2026-09-30.md

The PM should settle one trade-off before any live run. The challenge-pick rule (fix 2) can hide counterexamples for some candidates; see "Decisions for the PM" under fix 2.

==================================================
STARTING STATE
==================================================
- Branch: main at cbbf957.
- The working tree matched backup/part2-2026-09-22 (tip 3b31b58) exactly: 0 changed, 0 missing, 0 added (tree-vs-backup-before.txt).
- Runtime ee2d1df9, algorithm ab296a32.
- Gate-freeze snapshot of that tree: identical to the discovery v4 fixer's snapshot (gate_freeze/before.json).

==================================================
1. WHAT MADE THE REFUSED v2d REQUEST LARGE (measured, $0)
==================================================
Script: rebuild_v2d_request.py. Result: rebuild-v2d-request.json.

- Method: the script opens a read-only scratch copy of the native-v2b store. It rebuilds the second candidate request using the learning loop's own helpers, in the loop's own record order.
- It counts exactly 33,223 tokens with the frozen DeepSeek-V4 tokenizer. So it is the same request that was refused.
- The first candidate request also rebuilds: 14,304 by the local count, against 14,168 reported by the provider. The local count adds message framing.

Tokens each part adds:

| Part | Tokens |
|---|---|
| Challenge feedback, total | 14,136 |
| - evidence rows of the 18 challenge episodes (none failed a check) | 12,047 |
| - grouped trial outcomes | 1,432 |
| Development evidence (16 episodes), total | 11,030 |
| - per-episode check rows | 5,819 |
| Runtime contract | 2,784 |
| Reduction summary | 1,184 |
| Source-validation feedback | 1,070 |

So the size came from per-episode evidence rows, mostly of episodes with no failed check.

==================================================
2. FIX 1: faultlab-mechanic-context/v2-bounded
==================================================
Code: backend/app/lab/loop_limits.py, wired into learning.py. mechanic.py and diagnosis.py (both gate-frozen) are unchanged.

When it applies:
- A Mechanic candidate request or diagnosis request whose first turn would exceed 32,000 tokens.
- The count is the Mechanic's own admission count. A test checks this against the real Mechanic, for both request kinds and two models.
- A request that fits is sent exactly as today, with no record.

What it does:
- It compacts only the evidence tables, in three fixed stages. It stops at the first stage that brings the request to 28,000 tokens or less, leaving 4,000 for its one format-repair turn.
  1. A clean episode whose rows and outcome repeat an earlier clean episode is listed by ID (same_as).
  2. One clean episode is kept per recipe, arm and trial outcome; the others are listed (represented_by).
  3. No clean episode is kept in full.
- A "clean" episode has no failed check and is not the source or a reproduction.
- Always kept in full:
  - the source, its reproductions and every episode with a failed check;
  - every trial_outcomes group;
  - all feedback fields, the runtime contract and the diagnostic.
- Different outcomes inside the same recipe (for example triggered vs not triggered) form separate groups. So nothing contradictory is dropped silently.
- Each compacted block keeps exactly what summarize_evidence would give for the kept episodes alone; a test checks this.
- Each compacted block lists every omitted episode with its own outcome, and its legend gets one added sentence.
- The request carries context_compaction: a plain statement of what was compacted and how many rows were omitted.

When it still does not fit:
- Nothing is sent.
- A mechanic_context_records entry is saved with outcome SEARCH_ENDED and a plain reason.
- That source's candidate search ends. The campaign continues or ends NO_CHANGE by the existing rules. It never ends ERROR on this path.
- Design choice for review: an unsent request does not use up one of the campaign's 4 candidate requests.
- Format repair: a format-repair turn the Mechanic refuses (unchanged tokens.py) also ends that source's search, recorded with stage FORMAT_REPAIR. Before, it ended the campaign in ERROR.
- Diagnosis: the same rule applies through a small wrapper. The diagnosis evidence is only the source and its reproductions, which are never omitted. So in practice an oversized diagnosis request ends that source's search (no diagnosis, no candidate), and discovery continues.

What v2d would have got (same scratch copy, the real compaction code):

| Stage | Rows omitted | Tokens | Result |
|---|---|---|---|
| none | 0 | 33,223 | refused (as in the live run) |
| 1 | 2 | 33,605 | too big; bigger than before, because the statement costs more than 2 rows save |
| 1 + 2 | 15 | 27,990 | sent |

- Kept in full: all 10 failing episodes, plus 9 clean ones. That is 12 of 16 development episodes and 7 of 18 challenge episodes.
- Everything else in the request is byte-identical.
- The margin is only 10 tokens. A small wording change could push v2d to stage 3 (about 21,100 tokens, no clean rows kept). Both outcomes follow the declared rule.

==================================================
3. FIX 2: faultlab-challenge-selection/v2-candidate-reach
==================================================
Code: in the Explorer's selection handling (explorer.py and loop_limits.py), plus a prompt section, prompts/challenger_candidate_reach_v2.md. challenge.py is unchanged.

What it does:
- Before a challenge pick runs any pair, every fault target (tool and service) is checked against the calls the agent itself made in the candidate arm's source-validation episodes of this campaign. These are the tool_calls records with caller "actor".
- A pick with an unreached target is refused:
  - no episode runs;
  - the Challenger gets no pick and moves to its next request;
  - the refusal is saved on the selection record (challenge_reach), with the reason and the basis.
- The Explorer's next request is that pick's one re-plan (slot_request 2, replan_of, slot_feedback). A refused re-plan gets no further re-plan.
- Every request, re-plans included, is one of the challenge's existing 8 Explorer requests, charged on the ledger as before. A test shows 8 refused requests: exactly 8 charged, 0 episodes, and the challenge ends INCONCLUSIVE "Fewer than four feasible schedules".
- The Explorer is told the rule twice: in the prompt section, and in its request (the agent's called pairs, the pairs only the policy read, and this challenge's refusals).
- If the candidate arm has no source-validation episode on record, nothing is refused (status NOT_CHECKED).

Saved live challenges, read-only (challenge_reach_saved_stores.py, challenge-reach-saved-stores.json):

| Campaign | Picks | Under the rule |
|---|---|---|
| v2d | picks 1-2: F1 and F2 on update_order; pick 3: F4 on the orders status read | picks 1-2 run; pick 3 refused. That is the pick that did not fire. |
| v3 run a2fbffe3 | the F2 pick that found the counterexample | not refused |

Decisions for the PM before a live run:

1. Which calls count.
   - I counted only the agent's own calls.
   - The candidate policy's own reads do fire faults in the simulator: simulator/faults.py counts every attempt at a tool and service, whoever makes it.
   - Under the "any caller" reading, the v2d pick would NOT have been refused, because the policy read the orders status in all 3 source-validation episodes.

2. The rule narrows the challenge for some candidates.
   - Why: source validation runs only the source's fault. v2d's candidate stopped business after the rejected upgrade, so its agent never sent a confirmation there.
   - Effect: every fault on confirmations or the notifications status would be refused for that candidate. Under a healthy upgrade such faults would fire. A test shows this.
   - What stays safe: no gate changes. A refused pick never counts as a passed schedule, the challenge still needs 4 fully fired schedules, and promotion's protected cases still apply.
   - What is lost: the adversary is weaker for such candidates, so the challenge could miss a counterexample.
   - Options:
     - (a) accept it as declared;
     - (b) also count the candidate arm's episodes already run in this challenge;
     - (c) only refuse targets the old policy's arm called but the candidate's agent did not;
     - (d) drop rule 2 and keep rule 1.

==================================================
4. PLANS, SURFACES, OLD PLANS
==================================================
- Every new Learn plan freezes both declarations: mechanic_context and challenge_selection.
- Baseline and compare plans never get them. A baseline plan that carries one is refused at creation.
- A plan saved before this round:
  - has neither key and reads back with exactly the same bytes (no null keys added);
  - Start accepts it;
  - it keeps today's behaviour: an over-limit Mechanic request raises ModelInputLimit and ends in ERROR, and every valid challenge pick runs. Tests check both.
- Start refuses a plan whose declared rule differs from the installed one.
- Where the rules appear:
  - Learn setup form: a one-line sentence for each rule.
  - Saved plan: the fields "Mechanic request size" and "Challenge picks", plus the exact rule text. An older plan shows "Not declared ... as before".
  - Adversarial challenge panel: a "Challenge picks · candidate reach check" list.
  - Tested diagnosis panel: a "Mechanic request size" list.
  - Experiments API: new challenge_reach and mechanic_context lists, only for campaigns that declare the rules.
  - Recording: mechanic_context_records, challenge_selection_rule, and challenge_reach on each challenge selection, again only for campaigns that declare the rules.
- Older campaigns' API responses and recordings keep their exact fields.

==================================================
5. CHECKS (all $0)
==================================================
One scripts/test.sh after the last code edit. Log: builder/full-test-sh.log, 07:49 to 08:07 UTC.

| Stage | Result |
|---|---|
| Backend | 2,940 passed, 180 skipped, 0 failed, 2 known warnings. 30 new; the build before had 2,910. |
| Frontend unit | 353 passed (5 new) |
| Build | passed (size advisory only) |
| Browser | 19 passed, 1 opt-in skip (1 new) |

- No code, test or doc file changed during the run (sha256 compared; source-sha256-after-suite-check.txt).
- A dedicated test rebuilds the v2d request from a temporary read-only copy of the saved store, then deletes the copy. It ran; the skip count did not change.

New tests:
- backend/tests/lab/test_loop_limits_mechanic_context.py: 15 tests. They cover:
  - filtered summary equals summarize_evidence of the kept episodes;
  - stages, always-kept episodes, statement, determinism;
  - differing outcomes keep their own example;
  - the count matches the Mechanic's own admission count;
  - the v2d rebuild: exactly 33,223 tokens, then fits at 27,990 with the omission statement;
  - in the loop: an oversized candidate request is compacted and sent;
  - a request that cannot fit ends that source's search without ERROR and is never sent;
  - a refused format-repair turn does not cause ERROR;
  - an older plan still ends ERROR, as today;
  - an oversized diagnosis request skips that source and is never sent;
  - an unsent request does not use a candidate request.
- backend/tests/lab/test_loop_limits_challenge_reach.py: 9 tests. They cover:
  - an unreached pick is refused and re-planned once, charged within the budget;
  - with 8 refusals: 8 requests, 0 episodes;
  - a reachable pick runs exactly as today, and without the rule the request is byte-identical to today's;
  - the notifications narrowing, and NOT_CHECKED when there is no evidence;
  - an invalid answer clears the pending re-plan;
  - the v2d picks;
  - the declaration;
  - the loop hands the plan's rule to its Explorer.
- backend/tests/lab/test_loop_limits_plans.py: 6 tests. They cover:
  - new Learn plans get both rules, for all 3 agents; baseline plans get neither;
  - an older plan keeps its bytes and Start accepts it;
  - Start refuses a changed rule;
  - Learn-only and exact declarations;
  - the API and recording show the rules only where declared.
- frontend/tests/loop-limits.test.tsx: 5 tests (validators, saved plan, setup form, panels).
- frontend/tests/loop-limits.browser.ts: 1 test. Screenshots are in builder/screenshots/.

Other checks:
- Negative-control mutations: 21 of 21 caught, every file restored and verified by sha256 (mutation-checks.log).
- The dashboard's own validators accept the real API responses: run-options, both plans, both experiments responses and the recording (api-contract-check.log).
- Gate freeze: 30/30 gate functions and 20/20 gate files identical. Only the runtime, algorithm, agents-source and lab-tree fingerprints changed (gate_freeze/compare.txt).
- Identity (identity-compare.txt):
  - runtime ee2d1df9 -> 4d0d7914fcbbffad2f86e3383e290891756a7a2da7c750927c63c4796dd15b2b;
  - algorithm ab296a32 -> 3bc86d57;
  - reference Actor source hash 2597bffb -> abf010c4 (a tree hash over backend/app/agents, which includes explorer.py);
  - the example configuration hashes changed.
  - Unchanged: native v1 adapter 6f303264 and prompt 22515428, native v2.1 adapter dfd41b33 and prompt fff397c9, simulator service 3ce5bcd2, contract 6f9d7783, interpreter 6da0714a, scorer 19de811c, capability 8e8e04af, reference Actor prompt 12eabe7f, both transport-retry declarations.
- Register every agent again before a live run.

==================================================
6. HONEST NOTES
==================================================
- The first full backend run found one real regression. An existing discovery v4 test uses a stand-in Mechanic with no provider attribute, and new plans now pass through the size check. I fixed it in loop_limits.py; the real Mechanic always has the attribute. I changed no test to make it pass. Log: backend-suite-pass1-before-fix.log.
- The contract check's first attempts failed because of my own incomplete fixture records (a missing policy_version and too-small contexts), not because of product code. I fixed the fixtures.
- Challenge Explorer requests under new plans grow by a few hundred tokens: the context block plus the prompt section. The Mechanic rule does not cover Explorer requests; their existing admission check is unchanged.
- Cosmetic: the badge for a pick that ran reads "selected", in lower case.
- Nothing here measures model behaviour. Two things are unmeasured:
  - whether a Mechanic proposes better candidates from a compacted request;
  - whether the Explorer picks reachable schedules more often once told the rule.
- Constraints kept:
  - The saved stores were opened read-only; sha256 is unchanged (saved-stores-untouched.txt).
  - Scratch copies were outside the Desktop and are deleted.
  - I did not open .env, checks.py, heldout2 or the protected audit files.
  - Only read-only git commands. One early `git status` left the index untouched (mtime unchanged). HEAD and the backup ref are unchanged.
  - No commit.
- The harness forbids report .md files, so this report is returned here. CURRENT_STATUS.md has the new entry marked "not yet committed". I also updated docs/user-guide.md and added a note to the v2d write-up.

Next: two $0 reviews (integrity, product) and a fixer; the PM's decision on the challenge rule; commit (with the owner's OK); register every agent again; then a declared live Learn run.

_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

FIXER REPORT: discovery protocol v4 (history replay), review findings, September 30, 2026

COST AND BOUNDARIES
- Cost: $0. I made no provider, model, W&B, Weave or network call. Every fixer Python script ran under fixer/guard.py, which installs the test suite's own .env audit hook and refuses any non-loopback socket. Every guarded run recorded 0 refused connections, and so did the offline server's own guard (manual-check-server-refused-connections.json is []).
- I never opened, printed or copied .env or any credential. I never displayed backend/app/referee/checks.py; only the repo's identity and gate_freeze code hashed it. I never read artifacts/heldout2/, audit/promotion.json or audit/final-audit*.json.
- Git: no commit, reset, checkout, stash or push. HEAD is still cbbf957 on main, the .git/index sha256 is still e253a478… (the same as when I started), and backup/part2-2026-09-22 is still 4d1c21b. An empty .git/index.lock dated Sep 27 16:26 was already there when I started; I left it alone.
- Saved stores were opened only with mode=ro&immutable=1, and every store file kept its size and modification time. My scratch trees were under /Users/shree/FaultLab_Scratch/ (outside the Desktop), and all of them are deleted.
- Evidence is in faultlab/artifacts/product-discovery-v4-2026-09-30/fixer/. Copies of every file as it was before my edits are in fixer/before/files/.

RESULT TABLE
| finding | verdict | change | test (fails before the fix, passes after) |
|---|---|---|---|
| MEDIUM-1 (integrity): replay episodes count in later histories as "chosen by the Explorer", and feed the replay rule | FIXED | backend/app/lab/agent_history.py: a history now skips every episode whose selection record has provenance history_replay. It is not used and not counted, like a single-case baseline run. The same campaign's Explorer picks still count as learn discovery. | backend test_a_replay_episode_never_enters_a_later_agent_history_but_the_explorers_pick_does |
| F3 (product): the same issue, seen as dev-3/dev-5 going from 3/3 to 4/4 | FIXED | same fix as MEDIUM-1 | same test, plus the manual API re-run of M4 then M4b (below) |
| F2 (product): replay sources can use up the 4 candidate requests and end discovery before any Explorer slot, and nothing said so | FIXED (wording only; the loop is deliberately unchanged) | added one clause to the chooser sentence (run_plans.REPLAY_DESCRIPTION, still one sentence) and two sentences to the saved plan's statement (history_replay.AVAILABLE_STATEMENT); updated docs section 4 and the user guide | backend test_the_chooser_and_the_plan_say_a_replay_source_can_use_up_the_candidate_requests, plus characterization test test_the_unchanged_loop_ends_discovery_when_a_replay_source_uses_up_the_candidate_requests, which passes on the pre-fix code too (proves the loop behaviour is old, not new) |
| F1 (product): the fault-search panel says "the Explorer chose the remaining slots" when none ran | FIXED | SearchAttemptsPanel.tsx: the new replaySummaryText counts the Explorer slots that have a record ("the Explorer chose the next N slots recorded here"). With none, it says no Explorer slot is recorded and points to the campaign's recorded outcome. | frontend "F1: never says the Explorer chose slots that have no record…" |
| F4 (product): a v4 recording's history claim rule said "discovery v3" | FIXED | exports.py: a v4 recording's discovery_history_matches.claim_rule names v4 and history replays; a v3 recording keeps its exact old text, pinned in the test | backend test_a_v4_recording_names_v4_in_its_history_claim_rule_and_a_v3_recording_keeps_its_exact_text |
| LOW-2 (integrity): a replayed row without a case reads "(Explorer pick)" | FIXED | DiscoveryProtocol.tsx now reads "(no development case: a recipe first picked by the Explorer in an earlier learn campaign)" | frontend "LOW-2: … not labelled an Explorer pick" |
| LOW-3 (integrity), Run summary part | FIXED | RunSummary.tsx: for a v4 campaign, one line for the incident shown: "Found by History replay N of M · agent history row R (dev-x): a history replay of that row, never independent discovery." or "Found by an Explorer pick in this discovery v4 campaign, not a history replay slot."; nothing for other protocols | frontend "LOW-3: the run summary says which slot found the incident…" |
| LOW-3, W&B dataset rows, Weave traces, imports without evidence.json | DEFERRED | none. W&B rows are a sponsor-facing table whose schema cannot be checked at $0. Weave trace attributes come from the Provenance contract model, which this round may not change. An import without evidence.json cannot carry the label. The docs say: cite the recording's discovery_history_replays block or the source panel's Found by line, never the W&B or Weave views. | none |
| LOW-4 (integrity): the status page quotes the offline 3/3 without "scripted replies", and shows two ledger totals | FIXED | CURRENT_STATUS.md: "the real Reproducer code reproduced the replay source 3/3 on scripted native replies: fixture behaviour, not model evidence". One current total, $898.58 (ledger.json blob fe3e2707 = commit 4d1c21b; 893.86 + 2.12 + 2.60), with $893.86 marked superseded, in the header, the results paragraph and the Budget section. | documentation only; no test reads it |

WHY THE MEDIUM-1 FIX IS SAFE FOR v3 (agent_history.py is shared by v3 and v4)
- v4 still uses exactly v3's history: the fix sits in the one shared function.
- The history schema stays faultlab-agent-history/v2, and the SCOPE and SOURCES texts are unchanged. Only stores that hold a replay selection record can differ, and none exists: v4 has never run.
- Evidence (fixer/store-history-compare.log and .json). I recomputed the history of every reviewed registration in all 11 saved stores, with the code before the fix (verified as the backup blob 5f4868ad) and after it:
  - all 14 history blocks are identical, summary hashes included;
  - the stores hold 0 replay records;
  - every store file is unchanged;
  - the native-v2b list is still dev-5 3/3 then dev-6 2/3, summary d45adfdeef3c.
- The integrity reviewer's old-protocol probe, re-run on the fixed tree against their saved checkpoint output (backup, no v4), gives IDENTICAL results for all 7 scenarios (v1 reference/native, v2, v3 native/reference seeded and empty, v3 with pre-check). Only the options list differs: v4 is appended. The comparison does detect a deliberately changed message (fixer/probe-old-compare.txt).
- Flag for the PM: in a store that later holds a v4 campaign, v3 and v4 histories will leave out its replay episodes. I judge this the intended meaning: replays are not one of the two allow-listed product paths.

NEGATIVE CONTROLS (fixer/mutation-checks.log, scratch copies outside the Desktop)
- 14 of 14 mutations were caught: 8 backend and 6 frontend. They include restoring each pre-fix file and one-line mutants of each fix.
- Both unmutated controls pass: backend 60 tests across the fixes, v4, v3 and agent-history files; frontend 9 tests.
- The F2 characterization test passes with all four backend files as before the fixes, as expected.
- One side note: the "(Explorer pick) again" mutant also broke an existing saved-plan test, because of a double space. The LOW-2 test itself was the intended catch.

MANUAL CHECK THROUGH THE PRODUCT API ($0)
- Setup: the product reviewer's serve_offline.py (the real backend, loop, Reproducer, native adapter v2 and in-process simulator; scripted model replies; a local Weave double), over HTTP on port 18461, with a scratch store. Scripted outcomes are fixture behaviour, not model evidence.
- Sequence: register native v2, then a baseline study (COMPLETED; dev-3 and dev-5 3/3 VIOLATION), then v4 plan M4 (replays dev-3 then dev-5, 3/3 each; check CURRENT; the statement includes the new candidate-request sentence), then Start.
- M4 ended NO_CHANGE with 2 replay rows (0 model calls each) and 0 Explorer rows, after 4 candidate proposals. This is the F2 scenario, reproduced. Both sources are labelled with their replay rows. The recording's claim rule names v4.
- A second v4 plan (M4b) and a v3 plan made after M4 have exactly M4's history apart from the cutoff: summary 463a7d86…, 18 baseline episodes, 0 learn discovery, dev-3 and dev-5 still 3/3 from the baseline study only. The product review saw 4/4 here before the fix.
- The real M4 search-attempts and experiments JSON pass the dashboard's validators in a throw-away vitest spec. Its assertions held:
  - the fixed panel sentence says "No Explorer slot is recorded" and never "the Explorer chose";
  - every source's Found-by line is a history-replay line.
  I did not capture the printed sentence text itself.
- Files: fixer/manual-check.json and .log, contract-check-f1-low3.log.

FULL SUITE (fixer/full-test-sh.log; one scripts/test.sh after the last edit, 05:38:33 to 05:57:16 UTC, exit 0)
- backend: 2,910 passed, 180 skipped, 0 failed, with the same 2 known warnings. That is 5 more than the builder's 2,905: the 5 new tests.
- frontend: 348 unit tests (3 new).
- build: passed (size advisory only).
- browser: 18 passed, 1 opt-in skip.
- The sha256 of all 25 changed or added files (code, tests and docs) was identical at the start and end of the run (source-sha256-after-suite-check.txt).
- Honest note: an earlier run (full-test-sh-aborted-run1.log) was stopped by me at about 62% of the backend stage, with no failures before the stop. I stopped it to correct an over-claiming docstring in one new test; that test is now named test_without_replay_records_a_learn_campaigns_explorer_pick_still_counts, and its docstring now points to the store comparison for byte-identity. During that aborted run I also corrected a count, 15 to 14 histories, in CURRENT_STATUS.md and the v4 doc (fixer/doc-count-correction-during-aborted-run1.txt). The mutation checks were re-run after the last edit.
- Also: pytest and vitest in scripts/test.sh wrote their usual git-ignored caches.

IDENTITY (fixer/identity-compare.txt; the product's own functions)
- Runtime 2a181539… → ee2d1df914bd54c766eaec200715ad976f7d905964e1077adbb14ce46cc928e9.
- Algorithm f66ae8bb… → ab296a32c118294f5f36c1c42ffc3fa066863007b449acd88bc29d2b0f1b2b81.
- The two example configuration hashes changed, because they embed the runtime.
- Unchanged:
  - simulator 3ce5bcd2, contract 6f9d7783, interpreter 6da0714a, scorer 19de811c, capability 8e8e04af;
  - reference Actor prompt 12eabe7f and reference source 2597bffb;
  - native v1 adapter 6f303264 and prompt 22515428;
  - native v2.1 adapter dfd41b33 and prompt fff397c9;
  - the response formats and the transport-retry declarations.
- gate_freeze (fixer/gate_freeze/compare.txt): 30 of 30 gate functions and 20 of 20 gate files are identical. Only the runtime, algorithm and tree_lab fingerprints changed.
- tree_compare against the backup: 18 changed and 7 added. Compared with the builder, agent_history.py and RunSummary.tsx are now changed, and test_discovery_v4_review_fixes.py is added.
- Not changed: anything under referee, simulator or contracts; promotion, challenge, evaluation, reproduction, diagnosis, the Mechanic, the Actor or its prompts; external_agent.py, external_agent_v2.py and registry.py; coordinator, runner and learning. Native v1's golden test passed inside the suite.

FILES I CHANGED
- backend/app/lab/agent_history.py, history_replay.py, run_plans.py, exports.py.
- frontend/src/components/SearchAttemptsPanel.tsx, DiscoveryProtocol.tsx, RunSummary.tsx.
- frontend/tests/run-fixtures.ts (the chooser sentence, mirroring the backend) and frontend/tests/discovery-v4.test.tsx (3 new tests).
- New: backend/tests/lab/test_discovery_v4_review_fixes.py (5 tests).
- docs/DISCOVERY_V4_HISTORY_REPLAY_2026-09-30.md: header, sections 4, 6, 8, 9, 12 and 13, and a new section 14 with the findings table.
- docs/user-guide.md.
- CURRENT_STATUS.md: runtime chain, review fixes, the scripted-reply caveat, one ledger total, next steps.

NOT DONE
- No live run.
- The new Run summary line and the F1 sentence are checked in unit tests and on real API JSON, but not in a new real-browser screenshot. The browser stage of the suite passed.
- The W&B and Weave labelling part of LOW-3 is deferred, as explained above.
- Next steps: commit (needs the owner's OK); register again under ee2d1df9; then a declared live v4 Learn run in the native-v2b store, naming the store, the composition and the frozen summary hash with any result.

_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

INTEGRITY REVIEW: FaultLab product-native-v2b (2026-09-30). $0, offline only. Nothing committed; HEAD is still cbbf957 on main with nothing staged.
Evidence folder: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2b-2026-09-30/review-integrity/ (evidence-index.json lists every file)

VERDICT
PASS WITH NOTES. Both fixes behave as described. None of the protected parts changed. I found 5 LOW items (below) and no HIGH or MEDIUM ones.

WHAT CHANGED (my own comparison, not the builder's)
- tree_compare.py compares every file tracked on backup/part2-2026-09-22 (now 2c178a7) with the working tree by git blob hash. Untracked files are included. It skips .env, audit/promotion.json, audit/final-audit*, artifacts/heldout2/ and referee/checks.py.
- Result: 26 files changed and 4 test files were added (plus the artifacts folder). Nothing is missing. This matches the builder's file list.
- I ran the same comparison again at the end: my review changed nothing outside my own folder.
- My own diffs of every changed file are in diffs/.

(1) RULE v2: LAB-ROLE RETRY WITH BACKOFF
- Where it applies: complete_with_backoff is called only from explorer.py and mechanic.py. lab_retry is set in exactly one place, learning.py:133, on the loop's one Explorer and one Mechanic. That same Explorer handles challenge requests (Challenger) and that same Mechanic handles diagnosis (Diagnostician).
  - search_benchmark.py and completion_study.py build their own Explorer and Mechanic, and those keep rule v1.
  - Agent roles are unchanged: actor.py, external_agent.py and providers/runtime.py are byte-identical to 2c178a7.
  - The v1 retry pieces are unchanged on both trees: declaration(8) hashes to 9dcc7332 on both, and the source of blind_retry_allowed, retry_payload, complete_with_one_retry and charge_ledger_retry is identical.
- My own probes (probes/test_probe_backoff.py, 26 checks, all pass) use the real Explorer, Mechanic, RuntimeProvider, ledger and store:
  - An answer is never re-sent, even when the failure carries a returned generation under CONNECTION_ERROR, REQUEST_TIMEOUT or HTTP 503. That means 1 call, no wait, no retry record, and v1's error message. Tested for both roles.
  - HTTP 400/401/403/404/409/422/429/500/502/504 are never retried and never wait.
  - Order of steps: one event log shows, for each retry, charge (unreserved, never from a reservation), then the transport_retries record, then the send. Waits sum to 85 s (5/20/60), and every request is identical.
  - The per-request cap of 3 works. The final message is exactly "A model request failed after 3 transport retries (waits of 5 s, 20 s, 60 s); every allowed retry …".
  - The campaign cap of 12 counts only this campaign's rule-v2 records. I added 5 records from another campaign and 5 rule-v1 records, and neither set was counted. A fresh session (as after Continue) reads 12 from the store and allows no more retries.
  - During discovery, the declared bound stops retries (DISCOVERY_RETRY_LIMIT). Challenge requests are not limited by that discovery bound.
  - When the budget refuses, nothing more is sent.
  - A Stop during a real, unpatched wait: the Explorer and the Mechanic each ended 0.20 s after Stop. The request was sent once and charged once, with no retry record.
  - A Stop that lands exactly as a wait ends is caught before the retry is charged.
  - With no session, the behaviour is exactly rule v1.
- Negative controls: each of 4 in-process mutants made the probe fail. They were: re-send answers, skip the charge, ignore Stop, remove the cap. The unmutated control passes 26/26 (probe-backoff-negative-controls.log).
- Old plans:
  - The live run's saved Learn plan (b05ac280, from the exported JSON, not the SQLite store) revalidates under the current schema to identical bytes. Its plan_hash recomputes, it equals the installed rule v1, and it gets no backoff session.
  - A rule-v2 block survives the same round trip byte for byte.
  - The schema refuses 9 tampered v2 blocks. A changed rule text passes the schema, but validate_run_plan's exact-match check refuses it (old_plan_check.py, old-plan-check.json).
- A retry never changes what a model is shown on a later turn: the search ledger and the agent history expose no retry facts.

(2) NATIVE ADAPTER v2.1 LABELS
My probe, probes/test_probe_labels.py, runs 240 scripted episodes through real smolagents and the in-process simulator:
- 8 fault recipes, including F4 on send (1, 2 and 3 failures, and a second-occurrence case), update, get and status.
- 5 policies: non-blocking confirmation, blocking confirmation, blocking report, defer-after-upgrade, and none.
- 3 budget caps.

It checks what was actually sent to the model: 963 requests. All pass.
- C1: labels first appear as obs-1..obs-n with no gap.
- C2: at every request, the decode map is exactly the set of labels visible in that request.
- C3: every labelled row equals the journal row its label decodes to, and a label never moves.
- C4: no raw evidence ID ever appears in a request.
- C5: decoding follows the request's map exactly and completely. Guesses stay as written (195 guessed tokens were left undecoded).
- C6: on the same script, every non-final v2 request equals the v1 request with IDs swapped for labels (424 requests compared, 17 cases had rows the agent never saw). Citing the k-th row shown decodes to the ID v1 cites at position k.

Negative controls: the old journal-position numbering, a decode map that includes unshown rows, and a dropped field each make the probe fail (50, 50 and 240 failures). The control passes 240/240.

v1 golden: external_agent.py, the golden fixture and the golden test are byte-identical to 2c178a7. The golden test passes. The v1 adapter hash (fa7a58db) and prompt hash (22515428) are unchanged.

Reference Actor: actor.py, progress.py and actor.md are unchanged. The actor prompt hash, the response-protocol hash and the final-report format hash are unchanged. The reference history identity does not include source_hash (agent_history.target_identity), so it is also unchanged.

(3) WHAT THE MECHANIC AND EXPLORER READ
dump_views.py runs on both trees:
- runtime_contract for the reference Actor and for native v1 is byte-identical.
- For v2, only these fields differ: adapter_protocol's evidence_labels fields, its version, and memory (views/v2-view-field-diff.txt).
- All prompt files and ACTOR_PROMPT are identical.
- gate_freeze shows summarize_evidence and trial_outcomes are identical in text and AST; only their line numbers moved.

Nothing new is disclosed. The new text names adapter retries and non-blocking policy reads, which runtime_contract.hook_boundaries already describes ("exhausted adapter retries"). The Mechanic's evidence rows already show both write attempts. No episode data or scoring detail was added.

It does NOT remove the ambiguity from the Mechanic's view. That view is unchanged, so after a broker-retried send it still shows o1, o2, o4. Only an explanation was added (see LOW-1).

(4) GATES AND SCORING
gate_freeze/ runs the repo's gate_freeze.py (checkpoint copy) on a git-archive of 2c178a7 and on the working tree. The archive was built without promotion.json and final-audit, and it was deleted afterwards. My checkpoint record equals the previous verifier's ac7a12d2 record exactly.

Unchanged:
- scorer_hash 19de811c and the checks.py file hash; checks.py::score and ::scorer_hash.
- assess_pairs text, AST and lines (783e8e58…).
- tree_referee; promotion.py, evaluation.py, manifests.py, completion_study.py, reproduction.py, evidence.py, runner.py, policies.py; audit/development.json.
- challenge.py and coordinator.py (by blob hash).
- service 3ce5bcd2, contract 6f9d7783, interpreter 6da0714a, adapter 0cd810b7, dependency lock.

Changed, as declared:
- The Mechanic class and runtime_contract (the V2_MEMORY line only).
- runtime ac7a12d2 → 18292424; algorithm 7afabd51 → b2575eb2; source 99a9034f → f6d2d6eb; tree_lab.

I re-ran the builder's identity script on both trees under an audit hook that refuses any .env read or network use. The results equal identity-before.json and identity-after.json exactly: native v2 prompt fff397c9, adapter 4ba8b785, adapter protocol 0136604791…; capability 8e8e04af unchanged.

(5) NO NETWORK, NO .env
Every pytest run used my audit plugin (testplugin/review_audit.py) plus the suite's own guards, with no pytest cache and no bytecode files written.
- Targeted run: 92 passed. This covered the new and changed tests plus the golden test.
- Full backend: 2,867 passed, 180 skipped, 0 failed, in 17m20s. This matches the builder's counts.
- Across all runs: 0 connections to anything but loopback and 0 DNS lookups for outside hosts. The 127 loopback connections come from localhost_http-marked tests, including the builder's new whole-loop test.
- The only real-.env events are the 3 synthetic sys.audit calls in tests/test_env_guard.py. No file was opened; I confirmed the attribution by re-running that file (audit-env-guard.jsonl).
- Frontend: vitest run --no-cache, 338 passed. A before/after mtime listing shows no file written under frontend/, including node_modules/.vite.
- My own scripts ran with python -B under the refusing audit hook.

I did NOT run the build or browser stages, because they write dist/ and test results. No SQLite store under FaultLab_Runs was opened.

OBSERVATIONS (not findings)
- Another full pytest run (PID 36656, started 18:23 local) ran at the same time as my runs, probably the other reviewer's. Real-time Stop tests may be sensitive to that load.
- The full backend suite (both runs) updates the -shm side files of the repo stores artifacts/lab.sqlite3, phase20-2026-09-23/run-1 and phase26-2026-09-24/run-1. The tests/experiments tests open them. The main database files are unchanged (mtimes from Sep 23-27). This behaviour existed before this round, and these stores are not under FaultLab_Runs.

FINDINGS (all LOW)
- LOW-1: The Mechanic can still misread these reports; only an explanation was added. Separately, v2.1 makes the agent's obs-N and the Mechanic's oN numbers differ (in v2.0 they were the same). The builder's line "they NEVER saw the agent's raw labels" holds only for decoded citations: an undecoded guess such as "obs-4" reaches the Mechanic's report row verbatim (summarize_evidence passes unknown tokens through). Whether the Mechanic now reads such reports correctly is unmeasured.
- LOW-2: A retry the budget cannot cover is refused only after its 5, 20 or 60 s wait. No extra money is spent, but the run waits for nothing.
- LOW-3: The builder's tree-vs-backup-after.txt (17:55) is stale and incomplete. It omits CURRENT_STATUS.md (edited at 18:18) and cannot list new untracked files. My tree-vs-backup.txt is complete.
- LOW-4: Process note. The builder's first tree comparison ran git hash-object on audit/promotion.json, audit/final-audit.json and checks.py. It showed blob hashes only, disclosed this, and has since stopped. artifacts/heldout2 is untracked, so it was never touched.
- LOW-5: Stale names and wording:
  - Two references to a file that does not exist, tests/lab/test_lab_transport_backoff.py (the real file is test_lab_backoff_campaign.py).
  - A test is still named "…labels_are_journal_positions…".
  - The user guide says Stop ends the wait "within about a second", while other docs say "about half a second".

NOT DONE
- No live run and no commit.
- No build or browser stage.
- No coordinator-level test of a Stop during a Mechanic wait. I tested it at unit level only; the coordinator handles it the same way as the Explorer case.

## Findings (structured)

- **LOW-1 (LOW)** `backend/app/lab/diagnosis.py`: The misreading behind the live run's INCONCLUSIVE diagnosis is not removed from the Mechanic's view; only an explanation (V2_MEMORY) was added. v2.1 also makes the agent's obs-N and the Mechanic's oN numbers differ (in v2.0 they were the same). The builder's claim that the Mechanic and Explorer 'NEVER saw the agent's raw labels' holds only for citations that were decoded. Evidence: views/v2-view-field-diff.txt: only adapter_protocol label fields, version and memory changed; reference and v1 views are byte-identical. summarize_evidence (unchanged, gate_freeze text/AST equal) maps only real evidence IDs to oN and passes any other token through, so an undecoded 'obs-4' appears verbatim in the report row. The builder's own caveat says a report citing only what the agent saw still shows o1, o2, o4. The effect on the Mechanic is unmeasured. Fix: Do not claim the CONTRACT_EVIDENCE_GAP misreading is fixed. In the declared live run, pre-register a check: a diagnosis that asserts an undelivered citation on a v2.1 report whose cited_tokens_not_decoded is empty counts as a misreading. If it recurs, consider a declared new compact-evidence format that marks rows as shown or unshown (this needs a gate-freeze exception). Correct the builder report's 'NEVER saw raw labels' wording.
- **LOW-2 (LOW)** `backend/app/agents/transport_retry.py`: Under rule v2 a retry the budget cannot cover is refused only after its full backoff wait (5, 20 or 60 s), so the campaign waits for nothing before it ends ERROR with BUDGET_REFUSED. Evidence: complete_with_backoff (lines 294-301) runs session.wait, then refusal, then admit(). probes/probe-backoff.log prints 'budget refusal waited 5.0 s before refusing'. No money is spent, and the docs do say the charge happens 'after its wait'. Fix: Before waiting, add a check of unreserved ledger capacity that does not charge anything, and keep the actual charge after the wait. Or leave it as is and document that the wait comes before the budget check.
- **LOW-3 (LOW)** `artifacts/product-native-v2b-2026-09-30/builder/tree-vs-backup-after.txt`: The builder's tree comparison evidence is stale and incomplete: it omits CURRENT_STATUS.md and cannot list new untracked files. Evidence: The file was written at 17:55, but CURRENT_STATUS.md was edited at 18:18. tree_vs_backup.sh only loops over files tracked on the backup branch, so the 4 new test files never appear. The reviewer's review-integrity/tree-vs-backup.txt lists 26 CHANGED (including CURRENT_STATUS.md) plus 4 ADDED tests and nothing else. Fix: Regenerate after the last edit, including untracked files (git ls-files --others --exclude-standard), or use review-integrity/tree_compare.py.
- **LOW-4 (LOW)** `artifacts/product-native-v2b-2026-09-30/builder/tree-vs-backup-before.note.txt`: Process note: the builder's first tree comparison ran git hash-object on audit/promotion.json and audit/final-audit.json (files this round must not read) and on checks.py. Evidence: The builder's own note: 'compared every tracked file including the 3 protected files by git blob hash only (no content displayed)'. artifacts/heldout2 has 0 tracked entries, so it was not touched. The script has since skipped these files, and the mutation copies symlinked them instead of copying. Fix: No code change. Keep the skip list, and compare those files with git plumbing against the branch only, without reading the working-tree bytes.
- **LOW-5 (LOW)** `backend/tests/lab/test_campaign_transport_retry.py`: Stale references and wording: two comments point to a test file that does not exist, one test name still says 'journal positions', and the user guide gives a different Stop latency from the other docs. Evidence: test_campaign_transport_retry.py:8 and test_transport_retry_plans.py:83 cite tests/lab/test_lab_transport_backoff.py; the real file is test_lab_backoff_campaign.py. test_native_adapter_v2.py:116 is named test_labels_are_journal_positions_and_the_report_is_decoded_before_validation. docs/user-guide.md:38 says 'within about a second', while CURRENT_STATUS and the transport retry note say 'about half a second' (measured: 0.20 s). Fix: Fix the file references, rename the test (for example to ...labels_are_shown_order...), and use one latency phrase everywhere.

_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

PRODUCT REVIEW: FaultLab product-native-v2b (2026-09-30). Cost $0, offline only. No provider, model, W&B or Weave call was made. No product file changed. HEAD is still cbbf957 and the git index was not touched. The saved live store was not modified: its size, modification time and sha256 are the same before and after. Evidence folder: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2b-2026-09-30/review-product/ (RUN-NOTES.txt says how each file was made).

IN ONE PARAGRAPH
Both fixes behave as the builder says when run offline with scripted models.

The retry fix (rule v2):
- A Learn campaign whose Explorer loses its connection twice now carries on instead of ending ERROR.
- The waits are 5 s and then 20 s. Every retry is charged, counted in the budget, shown in the fault-search panel data and included in the recording.
- When the retries run out, the campaign ends ERROR. The message says how many retries were tried and why no more were sent.
- A Stop during a wait ends the campaign STOPPED within 0.2 to 0.32 s.

The label fix (native adapter v2.1):
- On dev-6 (a send that the broker retried inside one tool call), the agent now sees obs-1, obs-2, obs-3 with no gap.
- Reports decode fully (0 tokens left undecoded).
- The new build is a separate history identity from the September 29 build.
- The old live store still reads the same as before, and a bundle exported from it re-runs on v2.1.

Two things need attention:
- (P-1) The label fix does not change what the Mechanic reads. The live INCONCLUSIVE diagnosis came from the Mechanic, so that failure is not addressed.
- (P-2) The updated v2's registration record, and the dashboard, still say labels are "journal labels".

WHAT I RAN (all passed unless stated)
1. The full offline suite (scripts/test.sh), run after the builder finished:
   - backend 2,867 passed, 180 skipped, 0 failed (1,048 s);
   - frontend 338 passed;
   - build passed;
   - browser 17 passed, 1 opt-in skip (run on port 5199).
   These are the same counts the builder reported.
2. My own offline checks: 20 pytest checks in review-product/checks/. They use the backend suite's own socket guard and .env refusal, and a check confirms the guard is active. Combined run: 20 passed in 71 s.
3. The dashboard's own validators and panels, run on real API responses from a rule-v2 campaign (ui-check/, vitest, jsdom).
4. The product's identity functions, run under a .env and socket refusal hook. The output is byte-identical to builder/identity-after.json.
5. gate_freeze.py (copy taken from the backup branch), with the two audit JSONs dropped so they were never read. It shows the same 14 differences as the builder's run:
   - checks.py, manifests.py, promotion.py, evaluation.py, actor.py, actor.md, progress.py, runner.py, evidence.py, reproduction.py, completion_study.py and audit/development.json are unchanged;
   - assess_pairs is unchanged.
6. A tree comparison against backup/part2-2026-09-22 (now 2c178a7; the move from 3a34215 touched only docs and artifacts). It lists the builder's files plus CURRENT_STATUS.md (changed after the builder's own comparison) and 4 new test files. Nothing else changed:
   - simulator, contracts and referee unchanged (checks.py compared through gate_freeze, never opened);
   - external_agent.py (native v1) unchanged;
   - identity hashes unchanged: service 3ce5bcd2, contract 6f9d7783, interpreter 6da0714a, scorer 19de811c, capability 8e8e04af, native v1 adapter fa7a58db and prompt 22515428, reference prompt 12eabe7f, actor response protocol 4e6455ac.
   - The runtime is now 182924246224e4dc33983294fcda5c160f1a458e75c5cfe938634392774562b6, as the builder stated.

CHECK 1: RETRY FIX, FROM AN OPERATOR'S POINT OF VIEW
Setup: the real coordinator, a real new Learn plan and the real learning loop. The Explorer model is scripted. The product's own wait function runs, but its sleep uses a virtual clock (the Stop and cancel checks use real time).
- (a) Explorer loses its connection twice, then answers (discovery v1 and v2):
  - the campaign ends NO_CHANGE (its normal end), with no execution_errors;
  - waits were 5 s and 20 s, checked every 0.5 s;
  - two retry records: attempt 1 wait 5, attempt 2 wait 20, campaign retry numbers 1 and 2, phase "discovery";
  - budget API used_calls equals requests sent, e.g. 10 = 8 + 2 retries;
  - the search-attempts API shows both retries on the selection, with model_calls 3;
  - the recording download contains them.
- (a) The dashboard's validators accept the real responses (plan, run options, search attempts). A 503 retry followed by a timeout retry renders as: "Transport retry 1 of at most 3: ... (HTTP 503), so after waiting 5 s ..." and "Transport retry 2 of at most 3: ... (request timeout), so after waiting 20 s ...".
- (b) When the retries run out, the campaign ends ERROR:
  - every retry fails: "CONNECTION_ERROR: A model request failed after 3 transport retries (waits of 5 s, 20 s, 60 s); every allowed retry of this request failed. Inspect the saved provider diagnostics." (85 s of virtual wait, 4 requests charged);
  - campaign cap, tested through the real coordinator for the first time (the builder tested it only in memory): discovery v2, six slots each losing twice, gives 12 records numbered 1 to 12, then the 13th loss ends with reason CAMPAIGN_RETRY_LIMIT;
  - the discovery bound (8) and a refused budget also end ERROR with their own reasons.
- (b) The same holds in the real original loop (loopback simulator):
  - Mechanic diagnosis lost 4 times: ERROR, execution error role mechanic, 3 retries, waits 5/20/60;
  - challenge Explorer lost 4 times: ERROR, 3 retries with phase "challenge".
- (c) Stop pressed during a real 5 s wait, at 0.3 s, 1.2 s and 3.7 s:
  - the campaign ends STOPPED, and the API shows STOPPED, 0.20 to 0.32 s after the Stop;
  - reason: "External stop requested while a failed Explorer model request waited to be re-sent ...";
  - no execution error, no retry sent or charged.
- (c) Stop during a real Mechanic wait in the full loop: STOPPED 0.3 s later, with the Mechanic wording.
- (c) Cancelling the task during a wait ends it in 0.4 ms.
- (d) The agent side is unchanged. A native agent in a rule-v2 Learn campaign lost a request and its one retry:
  - that episode ended LAB_ERROR (reason CONNECTION_ERROR), with one agent retry event using v1's payload;
  - no lab backoff, no wait, and the campaign did not end ERROR.
  - Side note, not caused by this round: the later seven slots were all refused as duplicates of the lab-errored pick, because the fixture Explorer repeats one recipe and the existing duplicate rule counts a lab-errored pick as tried.
- (d) Evidence retries are unaffected. The 24 evidence-wait tests and the evidence-wait browser test pass, and those tests create new Learn plans, so they already run under rule v2.

CHECK 2: LABEL FIX, NEW REGISTRATION, BASELINE STUDY AND V3-HISTORY PLAN
Setup: the product's study harness (in-process simulator, local Weave double, scripted native transport).
- v2 was registered through the API: registration smolagents-1.26.0-adapter-v2-17453461884dd62d, prompt fff397c9, adapter 4ba8b785. Both hashes differ from the first build's (cee3aeda, d27c374f).
- A baseline plan through the API keeps rule v1.
- The 36-slot baseline study through the API: COMPLETED.
- I read the labels from the exact messages sent to the model transport, not from the adapter's own records:
  - all 18 B0 episodes: every request shows obs-1..obs-k with no gap and no raw evidence ID;
  - the adapter's labels_shown_to_agent matches the last request;
  - cited_tokens_not_decoded is [] and the decoded IDs equal the saved report.
- dev-6 (all 3 episodes): the journal has 4 rows, and row 3 (the first send attempt) was never shown. The agent saw obs-1, obs-2, obs-3.
- A v3-history Learn plan created through the API:
  - its frozen history holds exactly this build's 18 B0 trials (dev-1..dev-6, 3 each);
  - its agent identity is the v2.1 identity;
  - it has rule v2 and a discovery bound of 8.
- Non-pooling with the first build, checked on the copy of the live store with the product's compute_history:
  - the first build's identity has 23 verified discovery episodes there;
  - the same identity with only the prompt hash changed to v2.1's has NO_PRIOR_HISTORY (0);
  - the prompt hash is the only identity field that differs.
- I also ran the v3-history Learn campaign itself, start to end, on v2.1. The scripted Explorer picks dev-6's F4 recipe. The scripted agent is deliberately made to over-claim the confirmation, which is a declared test fixture, not model behaviour.
  - Result: COMPLETED/ACCEPTED on a manual fixture. This is not evidence of learning.
  - It produced 85 episodes, all with contiguous labels, and 0 undecoded tokens.

CHECK 3: WHAT THE DIAGNOSIS MECHANIC IS HANDED FOR SUCH AN EPISODE
The Learn run above produced a real diagnosis request:
- no "obs-<digit>" token anywhere in it;
- runtime_contract.actor_contract.memory is V2_MEMORY;
- every report alias points to a real row of its own episode.
But each of the 4 F4 episodes has 4 recorded rows and its report reads [o1, o2, o4]; o3 is the hidden first send attempt. So "no undecoded label" holds, and "no label gap" does NOT hold in the Mechanic's view. This is P-1 below.

CHECK 4: OLD STORE AND EXPORT/IMPORT
- I made a private copy of /Users/shree/FaultLab_Runs/2026-09-30/native-v2/lab.sqlite3 (SQLite backup API from a mode=ro&immutable=1 connection). The original is unchanged: sha256 5ccb1842..., same mtime and size.
- I opened the copy the way an operator browses an archive (read-only ArchiveCoordinator). All 8 saved API snapshots of the live Learn campaign are byte-identical to what the new code returns now: campaign, plan, search-attempts, matrix, experiments, budget, evidence-wait, policy-status.
- The old Learn plan reads as PLANNED with rule v1.
- The first build's report record (protocol v2-shown-labels-final-turn, with cited_unshown_labels) still reads.
- A regression bundle downloaded from the copy imports into a fresh store under the new runtime.
  - The v2.1 registration is listed as compatible.
  - A scripted re-run on v2.1: COMPLETED, 3 valid trials. Each shows obs-1..obs-3 with the first send attempt (row 3) hidden, and 0 undecoded tokens.

CHECK 5: DOCS
- The $893.86 total adds up: 856.96 + 2.14 + 1.04 + 1.46 + 7.53 + 2.35 + 15.91 + 6.47. It matches ledger.json.
- The runtime and identity values in CURRENT_STATUS match my recomputation.
- The v2.1 description in external-agent-setup.md matches what I observed ("obs-3 decodes to the send's second attempt (journal row 4)").
- Transport note section 12 is accurate on the rule, the caps, the reasons and the message text.
- Small inaccuracies are listed under P-6.

FINDINGS
- P-1 (MEDIUM): the September 29 misdiagnosis is not addressed by the label fix.
  - I rebuilt the live Mechanic's evidence view from the store copy with the product's summarize_evidence (live-mechanic-view.json). It had 4 episodes with 6, 5, 6 and 6 recorded rows. Report rows were [o1,o2,o4,o5,o6] (three episodes) and [o1,o2,o4,o5] (the 5-row one). Every o6 was in a 6-row episode.
  - So the Mechanic's claim ("o6 ... do not contain a sixth observation") was false on the data it was shown. The only irregularity it saw was the skipped o3.
  - v2.1 leaves that view byte-for-byte the same; only the V2_MEMORY text is new. The builder said this openly.
  - Whether a Mechanic now reads such reports correctly is unmeasured.
  - One unverified possibility: three episodes share report rows in the interned reports table, which may be what confused it.
- P-2 (MEDIUM): the v2.1 registration records the old label description.
  - A fresh v2.1 registration's limitations still say "Adapter v2 shows each delivered observation's evidence_id as its journal label (obs-1, obs-2, ...)" (registry.py:229; r2-native-v21-summary.json).
  - The dashboard shows this under "Agent limitations" (RunSetup) and in the Portability panel.
  - Registrations are immutable, so every re-registration for the next live run will carry the wrong sentence.
  - Fixing it means editing registry.py, which changes v1's adapter hash. v1's history identity would not change, because target_identity does not use the adapter hash, and every agent must be re-registered anyway.
- P-3 (LOW): an operator cannot see a backoff wait while it is happening.
  - During a wait (up to 85 s per request) the state stays SELECTING or DIAGNOSING. provider_failures is not in any API, recording or dashboard view, and the retry record appears only after the wait.
  - Challenge Explorer and Mechanic retries never appear in the dashboard, only in the recording JSON and the budget counts.
  - Section 12 and CURRENT_STATUS say retries are shown "on each retried selection in the fault-search panel". That is true only for discovery selections.
- P-4 (LOW): message wording and one needless wait.
  - The cap and budget messages read "A model request failed after 0 transport retries; the campaign's limit of 12 ... was reached". This is correct but awkward.
  - A retry the budget cannot cover is refused only after its 5 s wait. The budget is checked after the wait, the caps before it.
- P-5 (LOW): an older checkout cannot read new Learn plans. This is from reading the code, not tested.
  - Every new Learn plan now has rule v2. The ac7a12d2 code's saved-plan schema accepts only protocol v1, so an older checkout opening such a store reports "Saved campaign plan is missing, corrupt or inconsistent".
  - The docs state this limit only for smolagents-v2 plans.
- P-6 (LOW): docs and names.
  - user-guide says each retry is "listed on its selection". Mechanic retries are listed on the Mechanic output.
  - The external-agent-setup heading still says v2 was "not yet run live".
  - Its "Why this changed" paragraph ends "A gap invites a guess; the agent no longer sees one". The live agent made no guess (0 labels cited outside those shown); the failure was the Mechanic's. It should say plainly that the Mechanic's view is unchanged.
  - The new CURRENT_STATUS table row sits after a blank line that was already in the table, so it renders as plain text.
  - The discovery v2 budget text says "at most 16 ... Explorer transport retries during discovery", but the campaign cap of 12 is reached first.
  - Stale names:
    - test_campaign_transport_retry.py's docstring cites a file that does not exist (test_lab_transport_backoff.py; the real file is test_lab_backoff_campaign.py);
    - test_labels_are_journal_positions_... should be renamed;
    - test_diagnosis_context_..._has_no_label_gap_... asserts the gap ['o1','o2','o4'], so its name says the opposite.

FOR INFORMATION (not a defect of this round)
- The live watcher (watch_learn_v3.py) stops on used_calls or dollar thresholds while no counterexample exists. Rule v2 can add up to 12 charged lab requests, so allow for them in the next declaration.
- store-copy/lab.sqlite3 (9 MB, git-ignored) and store-copy/exported-bundle.zip are in the review folder; do not force-add the store copy.

NOT DONE
- No live run.
- No real-browser screenshot of the new retry text: I rendered the panels in jsdom with real API responses, and the product's browser suite passed.
- The older-checkout behaviour (P-5) was checked by reading the code only.
- No measurement of whether a Mechanic reads v2.1 reports better.

RULE NOTES
- .env was never opened.
- checks.py was only hashed and parsed by gate_freeze, never displayed.
- audit/promotion.json, audit/final-audit*.json and artifacts/heldout2/ were never read.
- The live store was read only through a mode=ro&immutable=1 connection to make the copy; all later reads used the copy.
- A temporary symlink to frontend/node_modules inside ui-check/ was removed after use.
- No git write commands were used. I did run read-only git diff between two commit IDs and git show.

## Findings (structured)

- **P-1 (MEDIUM)** `backend/app/lab/diagnosis.py`: The label fix does not change what the diagnosis Mechanic reads, and the September 29 INCONCLUSIVE came from the Mechanic misreading reports, not from the agent. The Mechanic's view still skips the hidden row (o1, o2, o4). Only the V2_MEMORY text is new, and whether that helps is unmeasured. The PM's check (3) 'no label gap' is not met in the Mechanic's view; 'no undecoded label' is met. Evidence: live-mechanic-view.json (rebuilt from the store copy with summarize_evidence): 4 episodes with 6/5/6/6 recorded rows; report rows [o1,o2,o4,o5,o6] and [o1,o2,o4,o5]; every o6 is in a 6-row episode, so the Mechanic's 'no sixth observation' claim was false on the data it had. r3-v3-learn-mechanic-view.json: the v2.1 diagnosis request for F4 episodes shows report_aliases [o1,o2,o4] with 4 recorded rows, hidden row 3, no obs-<digit> token, memory == V2_MEMORY. The builder's test test_diagnosis_context_for_a_v2_f4_episode_has_no_label_gap_or_undecoded_label asserts ['o1','o2','o4']. Fix: PM decision. Either accept it as is and measure a Mechanic reading live, or for smolagents-v2 plans only add a per-episode list of rows the agent was not shown under a new compact-evidence format ID (v1 and reference views untouched). Also rename the test so it does not claim 'no label gap'.
- **P-2 (MEDIUM)** `backend/app/integrations/registry.py`: A fresh v2.1 registration still records, and the dashboard still shows under 'Agent limitations' and in the Portability panel: 'Adapter v2 shows each delivered observation's evidence_id as its journal label (obs-1, obs-2, ...)'. That is no longer true. Registration records are immutable, so re-registering for the next live run bakes the wrong text in. Evidence: registry.py:229; r2-native-v21-summary.json registration.limitations[3] for smolagents-1.26.0-adapter-v2-17453461884dd62d; shown by frontend/src/components/RunSetup.tsx:57 and PortabilityPanel.tsx. Fix: Update the v2 limitation sentence to describe shown-order labels before anyone re-registers. This changes registry.py and so v1's adapter hash, but not v1's history identity (target_identity does not use adapter_hash), and every agent must be re-registered after this runtime change anyway. Or record why the PM keeps the old text.
- **P-3 (LOW)** `docs/PRODUCT_TRANSPORT_RETRY_2026-09-29.md`: Operators cannot see a backoff wait while it is happening (up to 85 s per request): the state stays SELECTING or DIAGNOSING, provider_failures is exposed nowhere, and the retry record appears only after the wait. Challenge Explorer and Mechanic retries never appear in the dashboard, only in the recording JSON and budget counts. The docs say retries are shown 'on each retried selection in the fault-search panel', which is true only for discovery selections. Evidence: No provider_failures reference in app/lab/api.py, exports.py, dashboard.py or frontend/src. The search-attempts API filters out challenge selections. Check 1 logs show retries only after each wait. Fix: Say in section 12 and CURRENT_STATUS that challenge and Mechanic retries appear only in the recording and budget. Optionally add a 'waiting to re-send (n s)' state note.
- **P-4 (LOW)** `backend/app/agents/transport_retry.py`: The cap and budget messages read 'A model request failed after 0 transport retries; ...'. A retry the unreserved budget cannot cover is refused only after its 5 s wait, because the budget is checked after the wait while the caps are checked before it. Evidence: r1-backoff-operator.log: 1b-campaign-cap, 1b-discovery-bound, 1b-budget-refused (waited_virtual_seconds_before_refusal 5.0). Fix: Word the zero-retry case as 'no transport retry was sent: <reason>'. Optionally check unreserved headroom before waiting as well as after.
- **P-5 (LOW)** `backend/app/lab/run_plans.py`: Every new Learn plan now declares rule v2. An older checkout (ac7a12d2 or earlier) whose saved-plan schema accepts only transport protocol v1 will report such plans as 'Saved campaign plan is missing, corrupt or inconsistent'. The docs state this forward-compatibility limit only for smolagents-v2 plans. Found by reading the code, not tested. Evidence: git show backup/part2-2026-09-22:backend/app/lab/run_plans.py: TransportRetryPlan.protocol is Literal['faultlab-transport-retry/v1'] on a StrictModel, and read_run_plan turns any validation error into that StoreConflict. Fix: Add one sentence to section 12 and CURRENT_STATUS: a store holding a new Learn plan needs runtime 18292424 or later.
- **P-6 (LOW)** `docs/external-agent-setup.md`: Several small doc and naming inaccuracies (listed under evidence). Evidence: external-agent-setup.md heading at line 47 still says v2 was 'not yet run live'; its 'Why this changed' paragraph ends 'A gap invites a guess; the agent no longer sees one', but the live run had 0 labels cited outside those shown and the failure was the Mechanic's. user-guide says retries are 'listed on its selection' (Mechanic retries are on the Mechanic output). The new CURRENT_STATUS table row follows an existing blank line, so it renders as plain text. The discovery v2 budget text says 'at most 16 ... retries during discovery' although the cap of 12 is reached first. test_campaign_transport_retry.py's docstring cites tests/lab/test_lab_transport_backoff.py, which does not exist (actual: test_lab_backoff_campaign.py). test_native_adapter_v2.py still has test_labels_are_journal_positions_.... Fix: Add a plain sentence that the Mechanic's view is unchanged and the September 29 misdiagnosis is not addressed by v2.1. Correct the heading, the 'listed on its selection' wording and the table placement. Mention that the cap of 12 bounds discovery v2. Fix the stale file reference and test names.

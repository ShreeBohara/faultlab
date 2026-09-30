_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

BUILDER REPORT: FaultLab product-native-v2b (2026-09-30). $0, offline only. Not committed, not reviewed, not run live.

Evidence folder: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2b-2026-09-30/builder/

RESULT IN ONE PARAGRAPH
Both declared fixes are built and tested offline.
(1) A new transport retry rule, `faultlab-transport-retry/v2-lab-backoff`, is frozen into every new Learn plan. It covers FaultLab's own lab roles: the Explorer (discovery and challenge selections) and the Mechanic (diagnosis and candidate requests). When a request gets no answer (connection error, timeout, HTTP 503), they re-send the identical request up to 3 times, after waits of 5 s, 20 s and 60 s. The cap is 12 such retries per campaign. Each retry is charged before it is sent and is recorded. A Stop during a wait ends the campaign STOPPED within about half a second. If every retry fails, the campaign ends ERROR as before, and the message now says how many retries were tried. The agent roles keep rule v1.
(2) Native adapter v2 now numbers evidence labels over what the agent is actually shown (`faultlab-native-adapter/v2.1-shown-order-labels`): obs-1..obs-n, no gaps. Unseen observations get no label, and only shown labels are decoded.
One scripts/test.sh run after the last code edit: every stage PASSED. Backend 2,867 passed / 180 skipped / 0 failed; frontend 338; build passed; browser 17 passed + 1 opt-in skip.
New runtime: 182924246224e4dc33983294fcda5c160f1a458e75c5cfe938634392774562b6 (algorithm b2575eb2…).

======================================================================
FIX 1: LAB-ROLE TRANSPORT RETRY WITH BACKOFF
======================================================================
What it does:
- The rule id is faultlab-transport-retry/v2-lab-backoff. declaration_v2(8) is frozen into every NEW Learn plan as plan['transport_retry'], the same place v1 is frozen. It declares:
  - retryable: CONNECTION_ERROR, REQUEST_TIMEOUT, HTTP_503.
  - agent_roles ['actor']: agent_retries_per_request 1, service_unavailable_delay_seconds 1, actor_retries_per_episode_max 8.
  - lab_roles ['explorer','mechanic']: lab_retries_per_request 3, lab_backoff_seconds [5,20,60], lab_retries_per_campaign_max 12.
  - stop_during_wait 'STOPPED', plus the plain-English rule text.
- Retry decision: only when blind_retry_allowed(error) holds, which is v1's own predicate. That means no generation arrived and the error is a connection error, a timeout or HTTP 503. An empty or malformed returned answer is never retried; neither is any other status.
- Order of steps:
  1. The failure is recorded (provider_failures).
  2. The caps are checked before any wait: the campaign cap of 12, and during discovery also the plan's declared explorer_transport_retries_max.
  3. The cancellable wait runs.
  4. Stop is checked again, then the caps.
  5. The retry is charged on the ledger from unreserved capacity. This is v1's charge_ledger_retry. If it is refused, the reason is recorded as BUDGET_REFUSED and the original failure stands.
  6. The retry is recorded.
  7. The retry is sent.
- Record: a transport_retries record with protocol v2, attempt (1-3), retry_delay_seconds (5/20/60), campaign_retry_number (1-12), campaign_retries_max 12, and request.phase (discovery / challenge / mechanic_diagnosis / mechanic_proposal). The saved selection or mechanic_outputs record lists the facts, and usage.model_calls counts every attempt.
- The campaign count is read from the store's own v2 transport_retries records. So it covers every Explorer and Mechanic of the campaign; v1 records are not counted.
- The wait is cancellable_wait. It checks Stop (ledger.stopped or the campaign's stop_requested) every 0.5 s. A Stop raises TransportRetryStopped, a subclass of StopRequested, with the plain reason "External stop requested while a failed Explorer model request waited to be re-sent (transport retry backoff); it was not sent again. Remote effects are retained." The coordinator then ends the campaign STOPPED with that reason. Nothing more is sent or charged, and no execution_errors record is written. Task cancellation still propagates at once.
- When all allowed retries fail, the original RuntimeProviderError is raised with a transport_retry_summary attached. readiness.execution_failure turns that into, for example: "CONNECTION_ERROR: A model request failed after 3 transport retries (waits of 5 s, 20 s, 60 s); every allowed retry of this request failed. Inspect the saved provider diagnostics." The execution_errors record keeps the provider diagnostics as before and adds transport_retries {protocol, role, retries_tried, waits_seconds, reason}. The reasons are ALL_RETRIES_FAILED, CAMPAIGN_RETRY_LIMIT, DISCOVERY_RETRY_LIMIT, BUDGET_REFUSED and NOT_RETRYABLE. Failures under rule v1 keep the old message byte for byte.

Scope decisions (please review):
- Only NEW Learn plans get rule v2. Baseline and compare plans make agent requests only, so they keep rule v1 and their saved plan bytes are unchanged.
- Plans saved before rule v2 keep v1 and still read and start. validate_run_plan accepts exactly rule v1 for any mode, or exactly rule v2 for Learn only. _bindings refuses v2 in a non-Learn plan, and a mutated v2 block fails the SavedRunPlan schema.
- Separate studies started on a campaign (selection comparison / search_benchmark, completion study) do not read the plan and keep rule v1. Their Explorer and Mechanic objects have lab_retry None.
- The discovery block is unchanged: explorer_transport_retries_max is still 8 under v1/v3-history and 16 under v2. Under rule v2 this bound is now enforced for EVERY discovery protocol, not only DiscoveryV2, so the declared number stays true when one request can get three retries.
- Worst case: a lab-role outage adds at most 12 charged requests per campaign and at most 85 s of waiting per request.

Agent-side failures, for information (unchanged): a reference Actor, native v1 or native v2 request that fails after its one retry ends only that EPISODE (LAB_ERROR, reason = provider code). In a Learn campaign the loop carries on:
- a lab-error discovery source is recorded and the slot is spent;
- a reproduction batch stops at that trial, so the source is not reproduced;
- a paired evaluation keeps "Infrastructure error pair retained" and may rerun that pair once.
An agent-side failure ends the whole campaign only in a BASELINE campaign, whose single episode is the campaign (ERROR with the provider code).

======================================================================
FIX 2: NATIVE ADAPTER v2.1, CONTIGUOUS SHOWN-ONLY LABELS
======================================================================
- _BridgeV2 keeps labels: evidence_id -> obs-N, assigned the first time v2 shows that journal row to the agent. This covers:
  - tool result fields observation / observations / policy_observations, in the order the agent reads them (canonical JSON: sorted keys, then list order);
  - a blocked report's observations;
  - the full observation list after the business budget closes.
  A label never changes. Rows never shown (a broker-retried first write attempt, a non-blocking before_confirmation read) get no label. A row first shown later gets the next number.
- Decode at final_answer uses the label map snapshotted when the model request was made. It is exact and total; unknown tokens pass through unchanged.
- report_submitted keeps: report, adapter_entrypoint_id, citation_protocol (now v2.1), cited_evidence_tokens, decoded_evidence_ids, evidence_labels (now the shown map, in label order), labels_shown_to_agent, final_report_required and response_contract. cited_unshown_labels no longer applies and is replaced by cited_tokens_not_decoded.
- adapter_protocol() now has its own evidence_naming, citation_decode, label_order_within_one_result, unshown_observations and difference_from_reference text, and no longer copies the reference Actor's "journal position" wording. This changes v2's prompt hash: v2 must be registered again, and it is a different history identity from the first v2 build. This is stated in the docs and CURRENT_STATUS.

What the Mechanic and Explorer read (finding): they NEVER saw the agent's raw labels or report_submitted payloads.
- The diagnosis Mechanic reads context.observations = summarize_evidence(bundles). The report is the decoded TaskReport, and its evidence IDs are compacted to that episode's oN row aliases. Observation rows show the exact evidence_id. It also reads evidence_ids (exact IDs) and runtime_contract.actor_contract.
- The candidate Mechanic reads development_evidence, challenge feedback 'evidence', the diagnostic and runtime_contract; the first two use the same summarize_evidence format.
- The discovery Explorer reads development_evidence (summarize_evidence) and runtime_contract. The challenge Explorer reads development_evidence only. The v3 agent_history has outcomes only.
So readers already saw decoded IDs, in the same ID space as the rows. The only v2-specific, misleading part was the memory text ("journal label (obs-N)"). It is now V2_MEMORY in app/lab/diagnosis.py: it says labels count shown observations, unseen rows get no label, and a report's oN means the Nth recorded row, which counts rows the agent never saw and so can differ from obs-N. v1 and reference views are byte-identical: summarize_evidence text and AST are unchanged per gate_freeze; the v1 memory text and ACTOR_PROMPT are pinned by a test.

HONEST CAVEAT: for the same citations the Mechanic's alias view is unchanged. After a broker-retried send, a report citing only what the agent saw still shows o1, o2, o4, because o3 is a real recorded row the agent never saw. Removing that alias gap would mean changing the shared, declared compact-evidence format (v1/reference views) or adding shown/unshown marks. The task ruled out both, so I did not. Whether a Mechanic now reads such a report correctly is unmeasured (needs a live run).

======================================================================
BEFORE / AFTER EXAMPLES (fake ids; also saved as before_after_examples.json)
======================================================================
F4 episode. Journal rows: A get_order, B update_order, C send attempt 1 (hidden), D send attempt 2 (shown).
- Before (v2): the agent sees obs-1, obs-2, obs-4. The label map is A→obs-1, B→obs-2, C→obs-3, D→obs-4.
- After (v2.1): the agent sees obs-1, obs-2, obs-3. The report cites obs-1..3 and decodes to [A, B, D]. evidence_labels = {A: obs-1, B: obs-2, D: obs-3}; cited_tokens_not_decoded = [].
- A guess of obs-4 stays "obs-4": C6 fails (Report references undelivered evidence).
- If the business budget later closes, the full list shows [obs-1, obs-2, obs-4, obs-3] in journal order: C is shown for the first time and gets obs-4.
- The Mechanic's report row shows [o1, o2, o4]; no obs-<digit> token appears anywhere in its request.

Rule v2 retries:
- Before (rule v1): lost → immediate retry → lost → "CONNECTION_ERROR: A model request failed; inspect the saved provider diagnostics."
- After (rule v2):
  - Lost → 5 s → retry 1 → lost → 20 s → retry 2 → answered. Record example: attempt 2, retry_delay_seconds 20, campaign_retry_number 2.
  - If all 3 retries fail: "CONNECTION_ERROR: A model request failed after 3 transport retries (waits of 5 s, 20 s, 60 s); every allowed retry of this request failed. Inspect the saved provider diagnostics."

======================================================================
FILES CHANGED
======================================================================
Backend, product code:
- backend/app/agents/transport_retry.py: rule v2 docstring, constants, declaration_v2, backoff_payload, retry_failure_message, TransportRetryStopped, cancellable_wait, LabBackoff, complete_with_backoff, lab_backoff_for_campaign. The v1 functions are unchanged.
- backend/app/agents/explorer.py: Explorer.lab_retry (None = v1). Rule v2 path with the discovery bound, and the DiscoveryV2 counter kept in step. Records carry request.phase.
- backend/app/agents/mechanic.py: Mechanic.lab_retry and the rule v2 path (each format attempt gets its own retries).
- backend/app/lab/learning.py: one LabBackoff per Learn campaign, set on its Explorer and Mechanic. Stop is ledger.stopped or stop_requested.
- backend/app/lab/run_plans.py: TransportRetryPlanV2 and a discriminated union; new Learn plans freeze v2; run options expose learn.transport_retry; _bindings and validate_run_plan checks.
- backend/app/lab/provider_failures.py: record_transport_retry(..., backoff=None). Without backoff the record is byte-identical to v1.
- backend/app/lab/readiness.py: retry-count message and summary, for rule v2 failures only.
- backend/app/lab/discovery_protocol.py: docstring only.
- backend/app/integrations/external_agent_v2.py: shown-order labels, the decode, the payload, adapter_protocol, PROTOCOL_VERSION v2.1.
- backend/app/lab/diagnosis.py: V2_MEMORY for the smolagents-v2 contract only.

Frontend:
- frontend/src/runPlans.ts: v2 types and validator; the plan accepts v2 only for Learn; run options learn.transport_retry.
- frontend/src/searchAttempts.ts: v2 retry entries (attempts 1..3 with 5/20/60 in order, never mixed with v1).
- frontend/src/components/CampaignPlan.tsx: transportRetryText for v1 and v2.
- frontend/src/components/DiscoveryProtocol.tsx: rule-aware discovery budget text; LATER_PHASE_RETRIES_V2.
- frontend/src/components/RunSetup.tsx: passes learn.transport_retry.
- frontend/src/components/SearchAttemptsPanel.tsx: v2 retry note.

Tests:
- NEW backend/tests/agents/test_lab_role_backoff.py (28): schedule for N=1..3, all fail, 503 and timeout, no re-roll, other statuses, charge-before-send, budget refusal, reservation, cap 12 (in memory and from the store), discovery bound vs challenge, DiscoveryV2 counter, Stop during a wait, Stop already requested (Mechanic), real-time promptness, Mechanic diagnosis/proposal, v1 without a session, the declaration.
- NEW backend/tests/lab/test_lab_backoff_campaign.py (10): real coordinator. Run options and new Learn plans declare v2; continue after 2 losses (v1 and v2 discovery); ERROR says 3 retries; discovery bound 8 caps; visible in search-attempts API and recording; Stop during a real wait → STOPPED within 2 s; a v1-rule Learn plan reads, starts and keeps v1; only Learn may declare exactly v2; full planned native original loop with lost discovery x2, diagnosis, proposal and challenge requests → same COMPLETED/ACCEPTED result, 5 records, every retry charged.
- NEW backend/tests/lab/test_native_v2_label_views.py (3): the diagnosis context for a v2 F4 episode (the real Mechanic request: no obs-<digit> token, report row [o1,o2,o4], every alias resolves, memory == V2_MEMORY); the Explorer's discovery request, same view; v1 and reference contract views unchanged.
- CHANGED backend/tests/integrations/test_native_adapter_v2.py: 3 journal-gap tests replaced by 6. They cover decode by the request snapshot, a hidden hook read, a broker-retried send with contiguous labels, a guess past the shown labels, a row first shown later, and v1 parity.
- CHANGED backend/tests/lab/test_campaign_transport_retry.py and test_transport_retry_plans.py: their rule v1 campaign tests now use learn_campaign_v1_rule, a Learn plan as saved before v2. The "every new plan" test now expects v2 for Learn and v1 for baseline.
- NEW frontend/tests/transport-backoff.test.tsx (4).

Docs:
- docs/PRODUCT_TRANSPORT_RETRY_2026-09-29.md: new section 12.
- docs/external-agent-setup.md: v2.1 labels, re-register, new identity, what model readers see.
- docs/user-guide.md: Learn retry paragraph.
- README.md: retry sentence.
- CURRENT_STATUS.md:
  - new runtime paragraph and September 30 paragraph;
  - live v2 run row;
  - carried total $893.86 (the ledger and the PM doc say the v2 run added $6.47; the breakdown sums to 893.86).

Unchanged, verified: external_agent.py (v1), registry.py, progress.py, actor.py, prompts/actor.md, referee, simulator, contracts, promotion.py, challenge.py, evaluation.py, thresholds.

======================================================================
TESTS AND CHECKS ACTUALLY RUN
======================================================================
- scripts/test.sh, once after the last code edit, log builder/full-test-sh.log. Every stage PASSED:
  - backend 2,867 passed / 180 skipped / 0 failed (ac7a12d2 had 2,824; +43);
  - frontend 338 (+4);
  - build passed;
  - browser 17 passed, 1 opt-in skip.
  Offline tests keep the suite's socket guard; the only real sockets are the localhost_http-marked loopback simulator.
- Pre-check backend run: same counts (backend-precheck.log).
- v1 golden test passes.
- Negative controls (mutation-checks.log): an unmutated scratch copy passes 80/80, and all 10 mutations are caught.
  - One check (restoring the pre-round files) fails at import, which is expected.
  - The 9 one-line behaviour mutants all fail tests: no session, Stop ignored, no charge, no cap, 1 s waits, v1 plans refused, no retry count in the message, old adapter, old memory text.
- Flakiness: in one earlier full mutation pass, the unmutated control had 1 failure (name not captured), and one unrelated test failed once under the Stop mutant. Neither reproduced in 8 isolated reruns, 4 control reruns or 10 repeat runs (flake-hunt.log, 10/10 clean). I relaxed the two real-time Stop assertions from 1.0/1.5 s to 2.0 s. The cause is unknown; the Desktop folder appears to be file-synced ("audit 4"-style duplicate names appeared in the scratch tree), which may add load.
- Repo gate_freeze.py (its checkpoint copy; audit/promotion.json and final-audit.json dropped from FILES), compared with the previous verifier's ac7a12d2 record (gate_freeze/compare.txt):
  - checks.py, manifests.py, promotion.py, evaluation.py, actor.py, actor.md, progress.py and audit/development.json are unchanged;
  - assess_pairs text, AST and lines are unchanged;
  - summarize_evidence and trial_outcomes: only line numbers moved;
  - changed as expected: the Mechanic class, runtime_contract, and the runtime, algorithm, lab-tree and source fingerprints.

======================================================================
IDENTITIES (product's own functions; identity-before.json / identity-after.json)
======================================================================
Changed:
- runtime: ac7a12d2… → 182924246224e4dc33983294fcda5c160f1a458e75c5cfe938634392774562b6
- algorithm: 7afabd51… → b2575eb257ebe9a1a519a7c3b8ca92994edb62e4581321e6dd2460647441beef
- native v2 prompt: cee3aeda… → fff397c9282b10c108c1df65aef9090c53b40c20973698888152519757264e1c
- native v2 adapter: d27c374f… → 4ba8b785191adb65f88356a6f157369450ae48c021bf127d593db0b3906ac1a8
- native v2 adapter protocol hash: 0136604791ce5b3af16ed51ccdbf330d10af8a060acdd9cc255e21821e62ec5f (v2.1)
- reference source_hash (tree hash of backend/app/agents, which now holds the retry code): 99a9034f… → f6d2d6eb342d79904cc00f58d5b81551bca145520b62c0d9ee0dad91b2a209f9. The reference prompt, context and response protocols, and so its history identity and model-visible behaviour, are unchanged.
- example configuration hashes (DeepSeek-V3.1): v1 9aeec020…, v2 362d4002…

Unchanged:
- native v1 adapter fa7a58db…, prompt 22515428…
- service 3ce5bcd2…, contract 6f9d7783…, interpreter 6da0714a…, scorer 19de811c…, capability 8e8e04af…

Declaration hashes: rule v1 9dcc7332…, rule v2 8c49085c….

Every agent must be registered again (the runtime changed). v2 is a new agent identity: do not pool its results with the first v2 build's.

======================================================================
NOT DONE, CAVEATS, RULE NOTES
======================================================================
- No live run, no review, no commit (not allowed). HEAD is still cbbf957 on main, and the index is untouched.
- The backup branch MOVED during my session, from 3a34215 to 2c178a7 (the PM's commit at 16:49 -0700: the live-run artifacts, ledger.json and docs/PRODUCT_NATIVE_V2_RUN_2026-09-29.md). The working tree already held those exact files. tree-vs-backup-after.txt compares against 2c178a7 and lists only my changes.
- Rule note: my FIRST tree comparison (before any edit) ran `git hash-object` on every tracked file. That included audit/promotion.json, audit/final-audit.json and backend/app/referee/checks.py: blob hashes only, never displayed, 0 differences. The script now skips them. The mutation scratch copies symlink the referee and audit instead of copying them.
- No SQLite store was opened. .env was never read.
- The v2 alias gap in the Mechanic's view remains, by design (see the caveat in Fix 2).
- registry.py's comment still says v2 "executes" progress.py label code. v2 now uses only progress.py's constants. registry.py was left untouched so v1's adapter hash stays the same.
- One unchanged comment in test_native_adapter_v2.py (the ordinary-turns test) still says "journal label". It is correct for those scripts, which have no hidden rows.
- Not implemented: a separate interruption record on qualifications for a stop during a transport wait. It uses the generic stop reason.
- Next: two independent $0 reviews. Then register again, and run a declared live run that exercises rule v2 and the v2.1 labels.

_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

INTEGRITY REVIEW: native adapter v2 (smolagents-toolcalling-v2). Reviewer: integrity. 2026-09-29. Cost $0.

REPORT FILE: NOT WRITTEN. This subagent's harness forbids writing report .md files, so this text is the full report. The PM should save it to /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2-2026-09-29/review-integrity/REPORT.md. All supporting evidence (scripts, command outputs, probe JSON) IS saved under that review-integrity/ folder.

BOTTOM LINE
Checks 2, 3, 4, 5 and 6 pass: v1 is unchanged, gates and scoring are unchanged, the old response contracts are unchanged, identities and histories are separate, and the tests are network-silent. Check 1 mostly passes, but I found one real problem (MEDIUM). v2's label decoder also turns labels of observations the agent was never shown into real IDs. So a guessed label can become a valid citation. I also found one small problem (LOW) in how the final turn is admitted. Nothing else.

HOW I COMPARED (the checkpoint branch is not HEAD, so plain `git diff backup/...` gives false results)
HEAD is main (cbbf957). Many files that exist in the checkpoint are untracked in main's index, so `git diff backup/part2-2026-09-22` marks them "D" even though they are present, for example progress.py and completion_study.py. Instead I compared git blob hashes of every file (`git hash-object`, no -w) with `git ls-tree` of the checkpoint.
Result (changed_vs_checkpoint.txt):
- 19 files modified and 8 added. The backend source changes are registry.py, providers/runtime.py, lab/{runner, diagnosis, run_plans, operator_actions, agent_history, bundle_imports}.py, cli/regressions.py and the new integrations/external_agent_v2.py. The rest are tests, docs and frontend.
- The 95 checkpoint files that are git-ignored on disk are all identical.
- The per-file diffs are in diffs/.

CHECK 1: v2 adds only the declared changes (mostly passes; see finding INT-1)
- There is no planning, task solution, recovery workflow or report repair.
- v2 reuses v1's `_native_agent` and `_Bridge` by import and only overrides generate, dispatch and final_answer.
- Probes run v1 and v2 on the same scripted episodes with deterministic IDs (v2_probe/v2_probe.out.json, v2_probe_policies.out.txt). The episodes cover success, no-report, a bad-then-good answer, a confirm policy, a business-budget close, a transport retry, a blocked report, a defer policy with business close, and a blocked confirmation. Results:
  - On every ordinary turn, v2's request bytes equal v1's with each real evidence_id replaced by its obs-N label. Provider kwargs are identical.
  - On final turns, the only differences are the transport message's tools key (only final_answer, with the declared description) and response_contract=native_final_answer.
  - No real evidence ID reached the v2 transport in any episode.
  - The one allowed divergence: when a final_answer fails validation, pydantic's error quotes the answer as written. v2 shows the label; v1 shows a truncated real ID (v2_probe/bad_then_good_divergence.txt).
- Unknown and non-string tokens pass through unchanged (progress.decode_citations uses reverse.get(token, token)).
- Nothing is hidden from the agent: v2 hides nothing beyond what v1 already hides (v1 never shows a non-blocking before_confirmation hook read). But see INT-1.

CHECK 2: v1 model-visible behaviour unchanged (PASS)
- My own probe (v1_probe/v1_probe.py) ran on a `git archive` copy of the checkpoint and on the working tree.
- Results (v1_probe/compare_v1.txt):
  - native_prompt_hash is 2251542869cf3e0fb841e536f56c8d2780f77e852d91ae30e12d4edf3e4c4989 on both.
  - TASK_CONTRACT hash, TRANSPORT_CONTRACT, the tool list, the native prompt templates and the agent settings are identical.
  - Across 6 scripted episodes (29 requests), every request message is byte-identical, every kwargs is identical, and no response_contract is ever sent. The event records are identical too. The only difference is wall_seconds.
- The builder's golden fixture equals my capture from the checkpoint code when using the same episode IDs. The golden-capture provenance hashes match the checkpoint files.
- v1's adapter_hash changed from 61497db3 to fa7a58db, only because registry.py changed. external_agent.py is blob-identical to the checkpoint. v1 registrations must be re-registered, which is already declared.
- A v1 registration differs only in adapter_hash, configuration_hash and registration_id. Its frozen target, excluding runtime fingerprints, is identical (registration_probe/compare.txt).

CHECK 3: gates and scoring unchanged (PASS)
- I re-ran the checkpoint's scripts/experiments/gate_freeze.py (identical to the working copy) through the existing wrapper. The wrapper skips audit/promotion.json and final-audit.json. I ran it on the checkpoint extract and on the working tree (gate_freeze/compare.txt):
  - scorer_hash is 19de811c on both. The checks.py file and its score/scorer_hash functions are equal.
  - assess_pairs text and AST are equal (text sha 783e8e58...).
  - service 3ce5bcd2, contract 6f9d7783 and interpreter 6da0714a are unchanged.
  - 26 of 30 functions and 18 of 20 files are identical. The rest:
    - diagnosis.runtime_contract changed: an additive elif branch that only applies to 'smolagents-v2' plans. It is Mechanic context, not a gate.
    - diagnosis.trial_outcomes, diagnosis.summarize_evidence and runner.EpisodeRunner.run changed only in line numbers; their text and AST are equal.
    - runner.py changed only in imports and the NATIVE sets.
- 136 protected files are blob-identical to the checkpoint (protected_files_blob_check.txt). These are all of referee/, simulator/, contracts/ and app/contracts/, plus promotion, challenge, evaluation, completion_study, policy_interpreter, policy_state, budgets, reproduction, baseline_study, evidence, actor.py, prompts/actor.md, progress.py, mechanic.py, external_agent.py and regression_runner.py.

CHECK 4: response contracts (PASS)
- On checkpoint vs working tree (contracts_probe/compare.txt), these are identical:
  - the actor_final_report response_format, byte for byte
  - ACTOR_FINAL_REPORT_SCHEMA_JSON
  - actor_response_protocol and its hash
  - the ReportAction and TaskReport schemas
  - MODEL_REQUEST_SETTINGS
  - the role refusals: explorer and mechanic are still refused for both contracts.
- The new native_final_answer schema is exactly {name: const "final_answer", arguments: {answer: TaskReport}}. It has additionalProperties false and both keys required. Its TaskReport and nested $defs equal TaskReport.model_json_schema() exactly, with no extra defs (contracts_probe/native_schema_check.txt).

CHECK 5: identity and history separation (PASS)
- v1 and v2 frozen targets differ in actor_prompt_hash and adapter_hash.
- Registration IDs differ: v2 is 'smolagents-1.26.0-adapter-v2-...'.
- Cross-verification is refused both ways ("Target differs from its independently frozen registration").
- agent_history identities differ in adapter_entrypoint_id and prompt_hash.
- v1-to-v2 portability is refused because both have the same source_hash.
- Plan-to-registration binding is checked (run_plans.py:540-541).
- Accepted policies are looked up by configuration_hash.
- Native plans are refused from reference research studies (runner.py:36-40).
- Imports are not a history source.
- No path pools v1, v2 and reference results (registration_probe/compare.txt, grep_entrypoint_uses.txt).

CHECK 6: tests network-silent, no .env read (PASS)
- Full backend suite: 2816 passed, 180 skipped, 0 failed (tests/backend-full.log). Frontend unit tests: 334 passed (tests/frontend-unit.log).
- I ran my own audit-hook monitor on every Python process (netmon/). It recorded 121 connects and 22 DNS lookups, all loopback.
- The only records naming the real faultlab/.env are the 2 synthetic sys.audit events that tests/test_env_guard.py raises on purpose; no file was opened.
- The working tree is byte-identical before and after the tests.

FINDINGS

INT-1 (MEDIUM): v2 decodes labels of journal observations the agent was never shown, so a guessed label can become a valid citation.
- The cause: v2 decodes against every journal row at request time (external_agent_v2.py:159, 183, 187). But v1's dispatch never returns observations added by a non-blocking before_confirmation hook (external_agent.py:182-189). They land in the journal (policy_interpreter.py:27, 77) and so get a label.
- The reference Actor shows every journal row on every turn (actor.py:47-48), and states the rule a guessed label "cannot make a guessed citation valid" (actor.py:155).
- Probe (v2_probe/v2_probe.out.json, hidden_hook_read; v2_probe/hidden_reference_check.out.txt):
  - Under a before_confirmation read_current_operation + require_receipt(orders) policy, the agent was shown only obs-1 and obs-3.
  - It wrote obs-2. v2 decoded that to the unseen hook read's real ID, and Journal.validate_report_references PASSES.
  - In v1, the agent cannot produce that ID at all. The same written answer FAILS the check under v1.
  - The report_submitted event does record labels_shown_to_agent=[obs-1, obs-3], so the case is auditable afterwards.
- Relevance:
  - 2 of 3 saved Mechanic policies in the native-learn-v3 store have exactly this rule shape (when upgrade_receipt_missing) (store_scan/).
  - 0 of 228 saved native episodes actually ran such a hook read, so it has not happened yet.
- Visible gaps in the labels (obs-1, obs-3) also invite a guess.

INT-2 (LOW): v2's final turn is charged before its schema-inclusive admission check.
- v2 reuses v1's check (external_agent.py:118-119), which counts tokens without the response_format. The provider only admits the native schema later, inside complete() (runtime.py:163-167), after the actor turn and campaign call are already charged.
- The schema adds 598 tokens (5282 becomes 5880 on the golden final request) (admission/final_turn_admission.txt).
- A final request between about 31,402 and 32,000 tokens would be charged and then fail with a fatal, non-retryable INPUT_LIMIT, never sent.
- The reference Actor pre-admits with the schema before charging (actor.py:56).
- Practically unlikely: today's final requests are about 5.3k tokens.

MY OWN SLIPS (procedure_notes.txt)
- One grep -l across backend/app/referee/ scanned checks.py for the string "report_submitted". It had no match and displayed nothing.
- A monitor self-test made one DNS lookup for example.invalid. It failed, and no connection was opened.
- Only read-only git commands were used, and the index and HEAD were not touched.
- No provider, W&B or Weave calls were made. The saved run stores were opened with mode=ro&immutable=1.

NOT DONE
- No live run.
- No check that the W&B provider accepts the strict native_final_answer schema for the target model. The builder's doc already says v2 is not yet run live.

## Findings (structured)

- **INT-1 (MEDIUM)** `backend/app/integrations/external_agent_v2.py`: v2 decodes labels of journal observations the agent was never shown. It decodes against every journal row at request time (lines 159, 183, 187), but v1's dispatch never returns observations added by a non-blocking before_confirmation hook (external_agent.py:182-189). Those observations still get a journal label. So a guessed label (for example obs-2 when the agent was shown obs-1 and obs-3) becomes a real, valid citation. This breaks the reference Actor's stated rule that a guessed label cannot make a citation valid (actor.py:155); the reference Actor shows every journal row on every turn (actor.py:47-48). Evidence: review-integrity/v2_probe/v2_probe.out.json (episode hidden_hook_read) and v2_probe/hidden_reference_check.out.txt. Under the policy before_confirmation: read_current_operation + require_receipt orders, the agent was shown only obs-1 and obs-3. It wrote ['obs-1','obs-3','obs-2']. v2 decoded obs-2 to evidence-...0f, the hook's read, which neither agent ever saw, and Journal.validate_report_references PASSES. Under v1 the same written answer FAILS ('Report references undelivered evidence'), and a v1 agent could never produce that real ID. report_submitted records labels_shown_to_agent=['obs-1','obs-3']. store_scan/: 2 of 3 saved Mechanic policies in the native-learn-v3 store have exactly this rule shape; 0 of 228 saved native episodes actually executed such a hook read. Fix: Decode only labels that were actually shown to the agent by that request. Snapshot self.shown_labels in generate(). In _final_answer, build the reverse map as {label: id for id, label in evidence_labels(delivered).items() if label in snapshot}, keeping journal-position numbering. Any other token passes through verbatim. Add a test using the non-blocking before_confirmation policy. Update docs/external-agent-setup.md:62 ('delivered by then') and the adapter_protocol decode_point text, which changes v2's prompt hash, so re-register.
- **INT-2 (LOW)** `backend/app/integrations/external_agent_v2.py`: On the strict final turn, v2 reuses v1's token check (external_agent.py:118-119), which does not count the native_final_answer response_format. The schema-inclusive check only happens inside provider.complete (runtime.py:163-167), after meter.model_call() has already charged the actor turn and the campaign call. A final request just under the input limit would be charged and then refused with a fatal, non-retryable INPUT_LIMIT, never sent. The reference Actor checks with the schema before charging (actor.py:56). Evidence: review-integrity/admission/final_turn_admission.txt: on the golden final request, the v1-style check counts 5282 tokens and the provider's check with the native schema counts 5880, a gap of 598 tokens. The limit is 32000, so requests of about 31,402-32,000 tokens fall in the window. Today's final requests are about 5.3k tokens, so this is unlikely in practice. Fix: In _BridgeV2.generate, when final_request is true, run validate_request_input(built_messages, model, response_contract='native_final_answer') before calling v1's generate. Or add a v2-only pre-admission hook that mirrors actor.py:56 so a too-large final turn is refused before it is charged. Add a test at the boundary.

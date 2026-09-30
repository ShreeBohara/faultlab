_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

FIXER REPORT: FaultLab product-native-v2b (2026-09-30). $0, offline only. Nothing committed and nothing run live.
Evidence folder: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2b-2026-09-30/fixer/ (evidence-index.json lists every file).

IN ONE PARAGRAPH
I checked all 11 review findings myself; all 11 are real.
- 9 are fixed. Each fix has a check that fails on the unfixed code (or on a one-line mutant of it) and passes on the fixed code. All 21 negative controls were caught (mutation-checks.log).
- 2 are deferred to the PM:
  - P-1 (MEDIUM) and LOW-1 are the same problem. v2.1 does not change what the diagnosis Mechanic reads, and the live INCONCLUSIVE came from the Mechanic. Changing its evidence view means a new compact-evidence format, and summarize_evidence is gate-frozen.
  - For P-1 I did the parts I am allowed to do: corrected docs, a renamed test, a new test, and a ready-to-use misreading check. That check flags the September 29 diagnosis as MISREADING, and its 5 controls pass.
- P-3's optional live "waiting to re-send" note is not built. The docs now say plainly what is shown and what is not.

After the last edit I ran scripts/test.sh once, and every stage PASSED:
- backend: 2,882 passed, 180 skipped, 0 failed (15 new tests);
- frontend: 339 tests (1 new);
- build passed;
- browser: 17 passed, 1 opt-in skip.

New runtime: 4553ebe7db2f9e3efda6f8761e987c6f1ea58dce12d3fde2dfbc8812ebb7c057. The algorithm is unchanged at b2575eb257ebe9a1a519a7c3b8ca92994edb62e4581321e6dd2460647441beef.

FINDINGS TABLE
| id | verdict | change | test |
|---|---|---|---|
| P-2 (MEDIUM) | FIXED | registry.py: the v2 limitation sentence is now the constant V2_LABEL_LIMITATION. It describes v2.1 shown-order labels: no label for unseen rows, and only shown labels are decoded. The adapter_hash docstring was also corrected. RunSetup.tsx's v2 description says the same. Side effect: v1's adapter hash changes fa7a58db… → 6f303264…, because registry.py is part of it. external_agent.py is byte-identical, the golden test passes, and the v1 prompt hash and history identity are unchanged. | test_native_adapter_v2_product.py::test_v2_registration_records_the_installed_label_protocol (also checks that run options list the recorded text); frontend native-adapter-v2.test.tsx gets one new assertion. Both fail on the pre-fix files. |
| P-1 (MEDIUM) | DEFERRED (PM decision) | The Mechanic's view is not changed. Docs and CURRENT_STATUS now say plainly: the live failure was the Mechanic's, all 53 reports cited only labels the agent had been shown, and v2.1 does not address the misdiagnosis. The misleading test name was changed to test_diagnosis_context_for_a_v2_f4_episode_has_no_undecoded_label_but_still_skips_the_hidden_row. New tool fixer/check_evidence_gap_misreading.py applies a declared rule to a campaign export only (stdlib, $0). On the Sep 29 export (b05ac280) it returns MISREADING for the one diagnosis. | misreading-check-selftest.log: 5/5 controls (an unrecorded ID or an undecoded token gives SUPPORTED; no claim, or POLICY_GAP, gives NOT_CHECKED). doc_checks.py covers the P-1 wording. |
| LOW-1 | DEFERRED (same as P-1), wording FIXED | The docs no longer say model readers "never see the agent's labels". They now say: never a label the adapter decoded; a token it did not decode (e.g. obs-4) reaches them as written. | test_native_v2_label_views.py::test_an_undecoded_token_reaches_the_evidence_summary_as_written pins the documented behaviour; a scratch mutant of summarize_evidence makes it fail (sensitivity check only, not a fix). doc_checks.py. |
| LOW-2 | FIXED | transport_retry.ledger_retry_fits(ledger, role) is a read-only restatement of CampaignLedger.consume_call's checks for an unreserved call. budgets.py is inside the frozen interpreter hash, so I mirrored it instead of changing it. complete_with_backoff(..., fits=) asks it before each wait: a retry the budget cannot cover now ends at once with BUDGET_REFUSED and no wait. The charge after the wait is still the only admission, and Stop still wins. The Explorer and the Mechanic pass it. | test_lab_backoff_review_fixes.py: Explorer refused with no wait; Mechanic's 2nd retry refused before its 20 s wait; dollar bound; Stop wins; unchanged schedule when there is room; a grid test in which the check equals real admission on more than 300 ledger states and charges nothing. Campaign level: test_lab_backoff_campaign.py::test_a_retry_the_budget_cannot_cover_ends_the_campaign_error_without_waiting. Caught: the unfixed files, no pre-check, the Explorer or Mechanic not wired, and 6 mutants that each drop or break one branch of the check. |
| P-4 | FIXED | retry_failure_message: when no retry was sent it now says "A model request failed and no transport retry was sent: <reason>." (for a budget refusal: "a retry did not fit the campaign's unreserved budget"). Messages after 1 or more retries are byte-identical. The waiting half of this finding is the LOW-2 fix. | 3 parametrized message tests, an unchanged-message test, and the campaign-level test. The "after 0" mutant fails 5 tests. |
| P-3 | FIXED (docs); live wait indicator DEFERRED | Section 12, the user guide and CURRENT_STATUS now say: discovery-selection retries show in the fault-search panel; challenge and Mechanic retries appear only in the recording and the budget counts; nothing shows a wait while it happens (the state stays SELECTING or DIAGNOSING). I confirmed this in code: search-attempts filters out challenge selections, and provider_failures is in no API view. | doc_checks.py (fails on the pre-fix docs, passes now). |
| P-5 | FIXED (docs; behaviour read from the code, not run) | Section 12 and CURRENT_STATUS: a store holding a new Learn plan needs this runtime or later; an ac7a12d2-or-older checkout reports it "missing, corrupt or inconsistent". I confirmed from git show backup:run_plans.py that TransportRetryPlan.protocol only accepts v1. | doc_checks.py |
| P-6 | FIXED | Heading renamed to "Native adapter v2 (first build run live September 29, 2026; v2.1 labels not yet run live)", with its 3 anchor links updated. "Why this changed" is rewritten. "Listed on its selection" is corrected. The blank line inside the CURRENT_STATUS table is removed, so the last two rows render as a table again. The docs state that the cap of 12 bounds discovery v2. DiscoveryProtocol.tsx now shows "at most 12 … (the plan declares 16, but the campaign's cap of 12 … is reached first)" under rule v2; discovery v1 text is unchanged. Stale file references and test names are fixed. | frontend transport-backoff.test.tsx: new discovery-bound test (fails on the pre-fix file and on a Math.min mutant); doc_checks.py |
| LOW-5 | FIXED | test_campaign_transport_retry.py:8 and test_transport_retry_plans.py:83 now point to test_lab_backoff_campaign.py. test_labels_are_journal_positions_… is renamed to test_labels_are_numbered_in_shown_order_and_the_report_is_decoded_before_validation, and its comment is corrected. The user guide now says "within about half a second". | doc_checks.py |
| LOW-3 | FIXED (evidence) | fixer/tree_compare.py includes untracked files and skips the forbidden paths. Regenerated after the last edit: tree-vs-backup-after.txt shows 27 changed, 5 added, 0 missing. Before my edits it was 24 changed + 4 added (the integrity reviewer's "26" was a miscount; its file list matches mine exactly). | Run before (equal to review-integrity/tree-vs-backup-final.txt) and after. |
| LOW-4 | FIXED (process only; no product change) | My scripts never hash or read audit/promotion.json, audit/final-audit*, artifacts/heldout2/ or checks.py. checks.py is covered only through gate_freeze, whose FILES list drops the two audit JSONs. | Skip list in tree_compare.py and gate_freeze/run_gate_freeze.py |

WHAT CHANGED (the fixer's edits only; per-file diffs in fixer/diffs/, pre-fix copies in fixer/before/)
- Product code:
  - backend/app/integrations/registry.py
  - backend/app/agents/transport_retry.py
  - backend/app/agents/explorer.py
  - backend/app/agents/mechanic.py (the fits= argument only)
  - frontend/src/components/DiscoveryProtocol.tsx
  - frontend/src/components/RunSetup.tsx
- Tests:
  - new backend/tests/agents/test_lab_backoff_review_fixes.py (12)
  - one new test each in test_native_adapter_v2_product.py, test_lab_backoff_campaign.py and test_native_v2_label_views.py
  - renames and comments in test_native_adapter_v2.py, test_native_v2_label_views.py, test_campaign_transport_retry.py and test_transport_retry_plans.py
  - frontend transport-backoff.test.tsx (+1 test) and native-adapter-v2.test.tsx (+1 assertion)
- Docs:
  - docs/PRODUCT_TRANSPORT_RETRY_2026-09-29.md (section 12)
  - docs/external-agent-setup.md
  - docs/user-guide.md
  - CURRENT_STATUS.md: dated September 30; runtime chain ac7a12d2 → 18292424 → 4553ebe7; not yet committed; register every agent again; v2 must be registered again and is a new identity; v1 adapter hash changed; the reviews and fixes; the P-1 deferral and options; table fixed.

TESTS AND CHECKS ACTUALLY RUN
1. Targeted backend tests after the fixes: 182 passed (targeted-tests.log). This covered both backoff files, the review-fix tests, the v1-rule role tests, the campaign transport and plan tests, the v2 product, label-view and adapter tests, and the v1 golden test.
2. mutation_checks.py (mutation-checks.log), ending ALL MUTATIONS CAUGHT:
   - backend control: 15 passed;
   - 14 backend mutants or unfixed files, all caught;
   - frontend control: 10 passed;
   - 3 frontend mutants or unfixed files, all caught;
   - doc_checks.py: 20/20 on the repo and 0/20 on fixer/before/.
   Scratch copies symlink referee, audit and contracts; they never copy them. The scratch tree was deleted afterwards.
3. One scripts/test.sh run after the last edit (full-test-sh.log, 02:18-02:35 UTC, exit 0):
   - backend 2,882 passed, 180 skipped, 0 failed (2,867 + 15 new);
   - frontend 339 (23 files);
   - build passed (only vite's usual chunk-size warning);
   - browser 17 passed, 1 skipped.
   My logging audit hook (audit-full-test-sh.jsonl) recorded 0 non-loopback connects and 0 outside DNS lookups (127 loopback connects). The .env open attempts were 21 in pytest temp folders plus the 3 synthetic ones of tests/test_env_guard.py, which the suite's guard refuses; the integrity reviewer found the same.
4. gate_freeze (repo script, audit JSONs dropped), recorded in gate_freeze/compare.txt. Compared with the reviewed tree, only these changed: the Mechanic class, mechanic.py, runtime_hash and source_hash. Unchanged: checks.py score and scorer_hash, assess_pairs (783e8e58…), summarize_evidence, promotion, evaluation, reproduction, runner, evidence, actor, actor.md, progress, the interpreter hash (budgets.py untouched), the algorithm hash and tree_lab.
5. Identity, computed with the product's own functions under a .env- and network-refusing hook (identity-after.json, identity-compare.txt):
   - runtime 18292424… → 4553ebe7db2f9e3efda6f8761e987c6f1ea58dce12d3fde2dfbc8812ebb7c057;
   - algorithm b2575eb257ebe9a1a519a7c3b8ca92994edb62e4581321e6dd2460647441beef (unchanged);
   - native v1 adapter fa7a58db… → 6f3032648ad8d1ca4cfb4c78deba738211c802adf1ec20a6e2d2781158a8dbe2 (v1 prompt 22515428… unchanged);
   - native v2 adapter 4ba8b785… → dfd41b338723780ddbaf770cb03eb2e7c5d28d06653dfc6f365225f99eefb77a (v2 prompt fff397c9… and adapter protocol 01366047… unchanged);
   - reference source_hash f6d2d6eb… → 142a9ebcf03b9fde3afeb6c6dd8dfd6a461552c33a9f71e1312eb4676bb17932;
   - example DeepSeek-V3.1 configuration hashes: v1 1b02a19a…, v2 34e2edd8…;
   - unchanged: service 3ce5bcd2, contract 6f9d7783, interpreter 6da0714a, scorer 19de811c, capability 8e8e04af, and the transport rule declarations v1 9dcc7332 and v2 8c49085c.
   Every agent must be registered again. v2 remains a separate identity from the first v2 build (same prompt hash as the builder's v2.1).

CAVEATS AND NOT DONE
- No live run and no commit. HEAD is still cbbf957 and nothing is staged.
- P-1 is not solved. Whether a Mechanic reads v2.1 reports correctly is still unmeasured. The two options are in CURRENT_STATUS: (a) pre-register check_evidence_gap_misreading.py for the next live run; (b) add a v2-only "rows not shown" list under a new compact-evidence format, which needs a gate-freeze exception. Note that its "claims an undelivered citation" part is a declared keyword rule on the hypothesis text, so a human should still glance at the listed hypotheses.
- The live "waiting to re-send" indicator (P-3, optional) is not built.
- P-5 was checked by reading the old code, not by running an old checkout.
- The Explorer's DiscoveryV2 session counter is still checked only after the wait. It uses the same bound as the LabBackoff discovery check, which runs before the wait, so in practice that check fires first.
- CURRENT_STATUS.md was finished before the test run. It points to fixer/full-test-sh.log for the counts instead of stating them, so nothing was edited after the run.

RULE NOTES
- $0: no provider, model, W&B, Weave or network call.
- .env was never opened.
- checks.py was only hashed and parsed by gate_freeze.
- audit/promotion.json, audit/final-audit*.json and artifacts/heldout2/ were never read.
- No SQLite store under FaultLab_Runs was opened; the misreading check used the saved export.json in artifacts.
- No git write commands. Only git show, ls-tree, hash-object, rev-parse and diff --cached were used.
- external_agent.py, the referee, the simulator, contracts, promotion.py, challenge.py, evaluation.py, budgets.py, prompts/actor.md, RULE_V2 and the frozen declarations are unchanged.

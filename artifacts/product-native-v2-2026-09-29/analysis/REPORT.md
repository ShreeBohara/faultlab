_Saved by the PM from the agent's returned text (the subagent harness refused report-file writes); content unedited._

# Native agent failure analysis (2026-09-29, $0, read-only)

- Native episodes: 192; with a failed check: 110
- C5 by cause: {"A": 48, "B": 0, "C": 51, "D": 4, "E": 0, "F": 0, "G": 0, "H": 5, "U": 0} (A = evidence-ID copying corrupted, C = final turn spent on a business call, D = invalid action on final turn, H = accepted but untruthful report)
- Raw data: classify.out.json (regenerate with `python3 classify.py`)

## C3

C3 appeared in 6 of 192 native episodes, all on one schedule: baseline dev-5, where the upgrade is rejected after 2 ticks (F2 FAILED/UPGRADE_REJECTED). That is 3 of 3 in native-probe (campaign e5b01658) and 3 of 3 in the native-learn-v3 baseline (campaign aaceaf2f). All 6 C3 episodes also failed C5. In 3 the agent filed an accepted but untruthful report (H): upgrade FAILED, notification SUCCEEDED, overall CORRECTLY_REJECTED, after it had sent the confirmation. In the other 3 there was no report (A: the evidence IDs were corrupted by the stray 极 token). No other schedule produced C3 (0 of 186), and neither learn campaign's Explorer picked a rejected-upgrade recipe.

## Final-turn alignment

They line up exactly, and the final metered turn cannot be lost. Each smolagents step makes exactly one model.generate (max_steps=8, planning_interval=None, external_agent.py:293/317). A transport retry happens inside one generate and uses no turn; 5 live episodes show model_calls = actor_calls + 1. Before each generation the adapter sends final_report_required = meter.final_turn, which is actor_calls >= 7 or business_closed (budgets.py:237-238, external_agent.py:115-119). So generations 1-7 carry false and generation 8 carries true with remaining_actor_calls = 1. On turn 8 a business call is refused before dispatch (external_agent.py:178-179). After step 8 without an answer, smolagents calls provide_final_answer (agents.py:606-607, 810) for a 9th generation. meter.model_call refuses it with BudgetExhausted('Actor budget exhausted') before any provider request (budgets.py:209). smolagents swallows that error and returns the text 'Error in generating final LLM output...'. That text fails TaskReport validation, giving ActorReportError 'External agent produced no valid original final report' (external_agent.py:332-334). Even a perfect report would fail on this path, because it is wrapped as a JSON string. Live: 103 of 103 no-report episodes have actor_calls = 8, 'Reached max steps' logged, and model_calls = actor_calls + retries, so no 9th call was ever sent. Business calls were never closed early and no episode ended before turn 8. The offline $0 probe (6 of 6 passed) reproduces the exact flag sequence F×7 then T, and shows a clean report on turn 8 still accepted after a rejected one on turn 7. What is lost is smolagents' built-in max-steps fallback: the agent gets exactly one turn flagged final and no retry after it.

## Recommendation

For a declared native adapter v2 (v1 unchanged, no gate changes):
(1) Give the model short citation labels, obs-1..obs-n, mapped back to the real IDs by the adapter; this is the reference Actor's Phase 11 fix. It targets the 48 A failures (44% of C5). All 102 rejected ID strings contained a non-ASCII token (极/极速/...) inside the 32-hex ID, and 0 of 44 retries were clean.
(2) Warn earlier that the report is due: set final_report_required from turn 7, or make the last turn report-only (the reference strict report turn). This targets the 51 C and 4 D failures (51%): long upgrade delays where the agent polls until turn 8 and never files the truthful PENDING/SAFE_UNRESOLVED report.
(3) Expect the dev-5 C3/H and dev-6 H failures to remain. They are genuine agent rule-breaking that a policy can repair once the report plumbing works.
(4) Record step-error events in the store (refused calls, rejected reports, invalid actions, with redacted raw text). They are not visible to the model, and they would remove the dependence on joining launcher logs and explain bucket D.
Note: REPORT.md was NOT written. The harness refused report-file writes from this subagent, and I did not work around it. The full report text is in my final message for the PM to save as artifacts/product-native-v2-2026-09-29/analysis/REPORT.md. All tables can be regenerated from classify.out.json (python3 classify.py). The evidence files are classify.py, classify.out.json, test_turn_alignment_probe.py and turn_alignment_probe.out.json, all in that folder.

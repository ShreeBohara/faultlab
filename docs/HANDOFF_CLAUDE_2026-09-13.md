# FaultLab handoff: Claude Code session, 2026-09-13 (written 11:50 PDT)

This file supersedes the status in `CONTINUE_HERE.md` and `docs/AGENT_HANDOFF_2026-09-13.md`
(those are the earlier Codex handoffs and remain the best description of architecture and history).
Same laptop, same folders. Everything below was checked against saved records, not memory.

**Hackathon clock (Pacific):** submissions due **1:00 PM**, judging 1:30 PM, presentations 3:30 PM,
awards 4:30 PM. The user has about $500 of W&B credit and authorized any model and config.

---

## 0. The situation in six sentences

1. FaultLab tests an AI agent doing one task (upgrade a fake order to express, then send one truthful
   confirmation) against injected faults, and tries to *learn a recovery policy* that fixes the agent's mistakes.
2. Everything up to "the fix works on the original failure" has now run **live** and is saved with verified Weave traces.
3. **No policy has ever been accepted (promoted).** The furthest run (`campaign-44085f54...`) generated a real policy
   that fixed the original failure 3/3, then the challenge stage found a harder schedule that broke it, so it was rejected.
4. Root cause is now understood (section 5): the generated policy used the "give up honestly" step in the wrong hook.
5. The campaign that was running at handoff has **finished NO_CHANGE** (see the final-result note in section 3);
   DeepSeek V3.1 was the agent under test and DeepSeek V4 Pro the lab's brain (Explorer + Mechanic).
6. All of this session's code is **uncommitted** (section 4). Tests pass.

---

## 1. Starting prompt for the next agent (copy this)

```text
Continue the FaultLab project on this laptop. Do not rebuild or restart the plan.
App root: /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
Specs:    /Users/shree/Desktop/Coreweave_AGI_Hackthon/FaultLab_Specs

Read first, in order:
1. faultlab/docs/HANDOFF_CLAUDE_2026-09-13.md  (current state, findings, next steps)
2. faultlab/AGENTS.md                            (rules: never print .env, provider calls only when asked)
3. faultlab/docs/learning-results.md, last section (the V3.1 repair-loop campaign)

Then do a quick read-only check: git status, `curl -s http://127.0.0.1:8000/api/config/status`,
and the state of campaign-aa79023053da470984118fdb1e9d8138 using
`.venv/bin/python artifacts/tools/summarize_campaign.py <campaign-id>` from the app root.
Tell me in plain words what finished, what it proved, and the next step, before spending more.

Goal: one honestly PROMOTED learned policy (source validation -> 4-schedule challenge -> promotion),
then restart evidence, docs and task checkboxes. I authorized up to $500 total and any W&B model.
Never hand-write the policy, never weaken the Referee checks or trial gates, keep every failed run.
Explain simply; I get lost in dense overviews.
```

---

## 2. Reading order (what to open, why)

| # | File | Why |
|---|---|---|
| 1 | this file | current truth |
| 2 | `AGENTS.md` | privacy, ownership, "provider calls must be explicitly requested" |
| 3 | `docs/AGENT_HANDOFF_2026-09-13.md` sections 4, 7, 8, 9 | architecture, earlier errors, code map, open tasks |
| 4 | `docs/learning-results.md` (last section) | the V3.1 repair-loop campaign in full |
| 5 | `../FaultLab_Specs/specs/001-faultlab-loop/tasks.md` (end) | Phase 16 + T122; 117/122 checked |
| 6 | `../FaultLab_Specs/specs/001-faultlab-loop/contracts/recovery-policy.md` | the policy grammar and exact hook timing |
| 7 | `../FaultLab_Specs/specs/001-faultlab-loop/experiment-protocol.md` + `evaluation-plan.md` lines 97-125 | gate rules you must not weaken |

Code, in the order the loop runs:

| Stage | File |
|---|---|
| Whole loop | `backend/app/lab/learning.py` (start here) |
| Explorer picks faults | `backend/app/agents/explorer.py`, `agents/prompts/explorer.md` |
| Agent under test | `backend/app/agents/actor.py`, `agents/prompts/actor.md`, `adapters/business_tools.py` |
| Turn/tick limits | `backend/app/lab/budgets.py` (`EpisodeMeter.final_turn` matters, see section 5) |
| Referee C1-C8 | `backend/app/referee/checks.py` |
| Reproduce / reduce | `backend/app/lab/reproduction.py`, `referee/reducer.py` |
| Diagnosis | `backend/app/lab/diagnosis.py`, `referee/diagnostics.py` (verdict rule), `agents/prompts/diagnosis.md` |
| Mechanic proposes policy | `backend/app/agents/mechanic.py`, `agents/prompts/mechanic.md` |
| Policy execution | `backend/app/lab/policy_interpreter.py`, `lab/policy_state.py` |
| Source validation / challenge / promotion | `backend/app/lab/evaluation.py`, `lab/challenge.py`, `lab/promotion.py` |
| Promotion cases | `audit/promotion.json` (6 cases; case 3 is a 4-tick upgrade delay) |
| Settings / models | `backend/app/config.py`, `providers/runtime.py`, `providers/wandb_inference.py`, `lab/configuration.py` |

---

## 3. Runtime state at handoff

| Service | Port | PID | Notes |
|---|---|---|---|
| Simulator | 8001 | 57401 | started by Codex yesterday; fine to leave |
| Frontend (Vite) | 5173 | 60673 | dashboard at http://127.0.0.1:5173 |
| Backend | 8000 | 95960 | **detached** (`nohup`), survives session end; log `artifacts/live-backend-v31-v4lab-20260913.log` |

Backend config right now: actor `deepseek-ai/DeepSeek-V3.1` ($0.55/$1.65 per M tokens), lab model
`deepseek-ai/DeepSeek-V4-Pro-0813` ($1.31/$3.96, thinking disabled), per-campaign cap $400.

**FINAL RESULT (12:05 PDT, checked against saved records).** This campaign ended **NO_CHANGE** at 18:57:10 UTC:
415 model calls, 60 episodes, admitted ceiling $20.68, `policy-v0` still active. It reached a SUPPORTED diagnosis on its
**first** source (the T122 change working), and V4 produced four candidates, all the same content hash `0e1d698ad273`.
Source validation repaired 2/3, 2/3, 2/3 and 1/3 against an incumbent that failed 3/3, so nothing advanced and the
campaign-wide budget of four Mechanic proposals ran out. **It never reached the challenge stage.** The saved episodes show
the policy delivering the SUCCEEDED receipt at tick 7 and the actor's confirmation succeeding at tick 8, after which V3.1
still burned all eight turns without a valid report. The measured blocker has therefore moved from the diagnosis and the
challenge to the actor itself: V3.1 fails to report about one episode in three even when handed everything it needs, which
alone makes a 3/3 batch unlikely. Step 1 in section 8 is still worth doing, but on its own it will not fix this.
Full write-up in `docs/learning-results.md`.

**Campaign as described at handoff:** `campaign-aa79023053da470984118fdb1e9d8138` (config `cff07c5516dd...`), started 11:46.
At 11:49: 6 discovery episodes (2 violations), one failure reproduced 3/3, reduction in progress, 141 calls,
$7.03 admitted ceiling so far. It was the first run using V4 as the Mechanic. Check it before anything else:

```sh
cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
curl -s http://127.0.0.1:8000/api/config/status
.venv/bin/python artifacts/tools/summarize_campaign.py campaign-aa79023053da470984118fdb1e9d8138
```

Terminal states: `NO_CHANGE`, `COMPLETED` (after an accepted promotion), `STOPPED`, `WAITING_EVIDENCE`
(use Retry evidence sync / `POST /api/campaigns/ID/retry-evidence {}`). `REJECTED` is transient.

**Update at 11:54:** this campaign reached a **SUPPORTED diagnosis** (`diagnostic-a3397fd8...`, POLICY_GAP) and V4 wrote a
policy (hash `0e1d698ad273`). Its first copy was REJECTED in source validation; an identical second copy was being validated.
Like V3.1, **V4 put `defer_unresolved` only in `before_final_report`**, and its response hooks only read, wait 1 tick and replay.
So even the stronger Mechanic misses the hook timing. That confirms section 5.5: Step 1 (give the Mechanic the hook-timing
contract) is the change most likely to produce a policy that survives the 20-tick challenge.

Other agents: Codex app processes are still alive on this laptop. The user also opened a second Claude
window only to *learn* the code; that window promised to stay read-only. Only one agent should edit or run campaigns.

---

## 4. Git state

`HEAD = origin/main = 5f82bde` (Codex committed and pushed its work at 10:35). **28 uncommitted changes, all from
this Claude session** (26 code/doc changes, plus this handoff file and the pointer added to `CONTINUE_HERE.md`). Nothing committed or pushed by Claude. Last test run: **361 backend tests passed**;
frontend unit tests and production build passed; browser tests not re-run.

| Change | Files | Status |
|---|---|---|
| T122 diagnosis context: each intervention option shows already-observed reduction trial counts | `lab/diagnosis.py`, `prompts/diagnosis.md`, `tests/lab/test_diagnosis_context.py` | tested, live-verified (first SUPPORTED diagnosis) |
| Split-role models: separate lab model for Explorer/Mechanic with its own verified pricing | `config.py` (`model_for`, `FAULTLAB_LAB_*`), `providers/runtime.py` (`role_model`), `agents/explorer.py`, `agents/mechanic.py`, `lab/configuration.py` (`lab_model`, `lab_model_settings`, `lab_pricing` frozen), `lab/tracing.py`, `lab/coordinator.py` (status shows `lab_model`), `integrations/registry.py`, `scripts/start-live-backend.sh`, `tests/test_role_models.py` | tested, running live |
| Campaign dollar ceiling 100 -> 500 (user authorized $500) | `contracts/models.py`, `config.py`, regenerated `contracts/Campaign.schema.json`, `CampaignBudget.schema.json`, `manifest.json` | tested |
| Explorer gets factual "why a fault did not trigger" (`primitive_prevented_reasons`) and `qualifies_for_repair` | `agents/explorer.py`, `prompts/explorer.md`, `tests/agents/test_roles.py` | tested, live: Explorer stopped choosing unreachable pairs |
| Docs for campaign 44085f54 and T122 | `docs/learning-results.md`, `integration-ledger.md`, `limitations.md`, `model-selection.md`, `live-validation.md`, `user-guide.md`, `README.md`, specs `tasks.md` | written; the 4 later campaigns are **not yet** in docs |

To publish (only when the user asks; AGENTS.md already authorizes pushing to this `origin`):

```sh
cd /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab
git add -A && git commit -m "Add split-role lab model, diagnosis and Explorer evidence handoffs, and live repair-loop results" && git push origin main
```

`artifacts/` and `.env` are git-ignored and must stay that way.

---

## 5. Key findings (the "why")

**5.1 Which agents fail at all.** DeepSeek V4 Pro never broke a rule in 24 discovery episodes. Llama 3.3 70B
(8/8) and gemma-4-31B (15/16) also handled nearly everything. DeepSeek V3.1 fails reliably under an upgrade
completion delay (fault F2): about 0% at 1 tick, 33% at 3, 50-78% at 4, **100% at 5+**. So V3.1 is the agent under test.

**5.2 How V3.1 fails.** Each HTTP call advances the fake clock one tick. V3.1 does get_order, update_order, then polls
status every turn. With a 5+ tick delay the receipt arrives after it has used all 8 turns. The "you must report now"
turn happens **only once** (`EpisodeMeter.final_turn` is `actor_calls >= 7 or business_closed`), V3.1 answers with
another poll, and the episode ends with no report, failing C5, C6 and C7.

**5.3 The honest-report lever.** Probe `artifacts/actor-nudge-probe-20260913.json`: when told "Business budget exhausted"
and asked for a report on repeated turns, **every model tested, including V3.1, returns a truthful SAFE_UNRESOLVED report**.
Inside FaultLab that is exactly what the existing policy step `defer_unresolved` does when it runs in a *response* hook
(`after_upgrade_response`): it sets `meter.business_closed = True` (`lab/policy_interpreter.py`), so every remaining turn becomes a report-required turn.

**5.4 Why the generated policy lost the challenge.** The Mechanic (V3.1) put `defer_unresolved` only in
`before_final_report`, which runs **only after the actor has already proposed a report**, so it can never rescue an agent
that never reports. Its read/wait/replay steps helped the 5-tick case (repaired 3/3 once, 1/3 and 2/3 on retests) but the
challenger's 20-tick delay is impossible to outwait: the upgrade is due at tick 22 and the episode ends at tick 20. The only
passing behaviour there is an honest unresolved report. It proposed the identical policy three times despite the returned counterexample.

**5.5 The hook timing was never given to the Mechanic.** `runtime_contract()` in `lab/diagnosis.py` gives the actor prompt,
limits and a general sentence about hooks, but not the per-hook invocation boundaries from the spec's
`contracts/recovery-policy.md` ("Hooks and ordering" table) or the one-final-turn fact. Supplying those factual contract
semantics is the same kind of fix as the earlier accepted T115/T117/T120/T121/T122 handoff fixes. It is **not** a canned
policy. Do not show the Mechanic a policy, the B1 reference (`agents/reference.py`), or promotion/final cases.

**5.6 Diagnosis rule.** SUPPORTED needs control 3/3 target failures and treatment 0/3 (`referee/diagnostics.py`). At 4 ticks
V3.1 is too flaky for 3/3; the SUPPORTED run used a 5-tick control and the "remove the fault" treatment.

**5.7 Promotion risk to watch.** Promotion runs 6 cases x 3 pairs (36 episodes) and needs zero candidate violations, every
healthy trial completed, and strict gain. Case 3 (4-tick delay) is where gain should come from. Case 6 (update_order fails 3 times
before acceptance) and case 4 (upgrade rejected) are where a new policy could introduce a regression.

---

## 6. Everything that ran this session (all saved; nothing deleted)

| Campaign | Actor / lab model | Result | Calls | Ceiling |
|---|---|---|---:|---:|
| `campaign-44085f54a24144b78252d8eea211ebb8` | V3.1 / V3.1 | NO_CHANGE. 4 sources reproduced 3/3; 4th diagnosis **SUPPORTED** (first ever); 3 generated policies (same hash `e5420426...`); source validation 1/3, **3/3**, 2/3; challenge counterexample (F2 20 ticks + F1 1500 ms); 143 episodes, 143 verified traces. Export `artifacts/v31-repair-final-20260913.json` | 995 | $20.80 |
| `campaign-f12fd077600e451b8bea9258489cd2ef` | Llama 3.3 70B / V4 Pro | NO_CHANGE. 7 completed, 1 safe unresolved, no violation | 53 | $2.64 |
| `campaign-912610a2332248fca35ade2033061cca` | gemma-4-31B / V4 Pro | NO_CHANGE. One violation, but on a two-fault recipe whose confirmation fault was never reached, so it did not qualify. Explorer kept picking unreachable pairs, which led to the Explorer fix | 49 | $2.44 |
| `campaign-0b8bd7d34e8d4a4ca2ff2ae1afac580c` | gemma-4-31B / V4 Pro (Explorer fix) | NO_CHANGE. Explorer chose reachable single faults; gemma passed a 5-tick delay; no violation | 44 | $2.19 |
| `campaign-aa79023053da470984118fdb1e9d8138` | V3.1 / V4 Pro | **NO_CHANGE**. First-source SUPPORTED diagnosis; 4 identical candidates; source validation 2/3, 2/3, 2/3, 1/3; challenge never reached; 60 episodes | 415 | $20.68 |

Admitted ceilings are worst-case (32K input + 2K output per call), not bills. This session's ceilings total about **$35**;
Codex's earlier ledger was $27.48. About 55 small probe requests are not in the ledger. Actual spend is far lower; check W&B billing.

Probes (request checks only, not learning evidence): `artifacts/actor-candidate-probe-20260913.json` and `artifacts/actor-nudge-probe-20260913.json`.
Stuck-at-final-turn result: reports honestly: MiniMax-M3, Qwen3-235B, Qwen3.5-35B, Qwen3.6-27B, V4-Flash, V4-Pro, gemma-4-31B,
Llama-3.3-70B, Kimi-K2.6, gpt-oss-20b. Keeps polling: V3.1, Qwen3-30B, granite-4.2-8b, Llama-3.1-70B, GLM-5.3-Flash.
Nemotron chose an invalid write; Llama-3.1-8B returned invalid JSON.

Verified W&B prices (2026-09-13, per million input/output): V3.1 0.55/1.65, V4-Pro-0813 1.31/3.96, V4-Flash 0.14/0.28,
Llama-3.3-70B 0.71/0.71, gemma-4-31B 0.10/0.34, MiniMax-M3 0.23/0.96, Qwen3.5-35B-A3B 0.25/1.25, Qwen3.6-27B 0.60/3.60, Kimi-K2.6 0.65/3.41.

---

## 7. Known issues and gotchas

- **Background tasks die with the Claude session.** Start the backend detached (command in section 9). The new session cannot see old monitors.
- **Foreground `sleep` is blocked** in Claude Code. Use the Monitor tool with an until-loop to wait for campaign states.
- **Don't restart the backend while a campaign is active** (`active_campaign_id` not null); it interrupts episodes.
- **`.env` still has an older model.** Always launch with the explicit overrides and confirm `/api/config/status` shows both `model` and `lab_model`.
- **Launcher masks `.env` lab settings:** `start-live-backend.sh` exports empty `FAULTLAB_LAB_*` defaults, which override values placed in `.env`. Always pass lab settings on the command line. (Reviewer finding, unverified, confirmed by reading `Settings.from_env`.)
- **`cli/freeze.py` model identity omits the lab model.** Fix before T097 if the accepted policy comes from a split-role campaign.
- The Explorer/Mechanic "provider returned a different model" check is now nearly tautological for the real provider (low risk).
- Actor models without a reviewed tokenizer (gemma, MiniMax, Qwen, Kimi) use the conservative byte-count admission; fine for actor prompts.
- The adversarial review workflow (`.../subagents/workflows/wf_dd51b818-cd9/journal.jsonl`) finished with **0 confirmed defects**, but 8 of 13 agents failed on the Claude spend limit, so it is incomplete.
- Aria is deferred by the user; TypeSafe awaits sponsor instructions. Never print `.env`, API keys or control tokens.

---

## 8. What remains, in order

**Step 0 (now).** Read the running campaign's outcome. If a policy was PROMOTED, jump to Step 3.

**Step 1 (about 30 min, highest value).** Give the Mechanic the missing factual hook contract (5.5):
in `backend/app/lab/diagnosis.py` extend `runtime_contract()` with the hook invocation boundaries
(after_upgrade_response, before_confirmation, after_notification_response, before_final_report) as written in
`contracts/recovery-policy.md`, plus the facts that `defer_unresolved`/`report_terminal_failure` in a response hook
close business calls and make every remaining actor turn report-required, that before_final_report runs only after a
report is proposed, and that the actor gets a single reserved final turn otherwise. Add a test asserting these facts.
Run the backend suite, restart the backend (V3.1 actor, V4 lab), start a new learn campaign, monitor it.
Record it as a new traceable task (T125) in `tasks.md`, like T115-T122.

**Step 2.** If a candidate survives the challenge, promotion runs automatically; inspect `promotion_decisions`,
the policy's `decision`, and the pointer `accepted-policy:<configuration hash>`. If NO_CHANGE again, read why
(source validation? challenge? promotion?) before changing anything; more runs alone are not evidence.

**Step 3 (after an ACCEPTED policy).** Restart evidence: stop and restart the backend with the **identical** configuration
(any code, prompt or env change produces a new configuration hash and the accepted policy won't load), start a new
campaign, and confirm it starts from the accepted policy version. Then update `learning-results.md`, check T065,
add the four later campaigns to the docs, add tasks T123 (split-role lab model) and T124 (Explorer prevented reasons)
as already implemented and tested.

**Step 4 (if time).** T097 freeze (`PYTHONPATH=backend .venv/bin/python -m app.cli.freeze --campaign ID`, fix lab-model identity first),
T102 sealed audit (`./scripts/run-audit.sh --campaign ID --execute-live`, 72 episodes), T100 regression export/validate/execute,
portability with smolagents and selector comparison (commands in `docs/live-validation.md` section 6). T088 cannot pass while Aria is deferred.

**Before 1:00 PM regardless:** ask the user whether to commit and push the current tree so the submission has the latest code and results.

---

## 9. Command cheat-sheet (run from the app root)

```sh
# Status
curl -s http://127.0.0.1:8000/api/config/status
.venv/bin/python artifacts/tools/summarize_campaign.py CAMPAIGN_ID      # read-only chain summary
PYTHONPATH=backend .venv/bin/python -m app.cli.client status --campaign CAMPAIGN_ID
PYTHONPATH=backend .venv/bin/python -m app.cli.client stop --campaign CAMPAIGN_ID

# Restart backend (only when active_campaign_id is null)
kill $(lsof -nP -iTCP:8000 -sTCP:LISTEN -t)
( nohup env WANDB_MODEL='deepseek-ai/DeepSeek-V3.1' FAULTLAB_PRICING_MODEL='deepseek-ai/DeepSeek-V3.1' \
  FAULTLAB_INPUT_DOLLARS_PER_MILLION=0.55 FAULTLAB_OUTPUT_DOLLARS_PER_MILLION=1.65 \
  FAULTLAB_LAB_MODEL='deepseek-ai/DeepSeek-V4-Pro-0813' FAULTLAB_LAB_PRICING_MODEL='deepseek-ai/DeepSeek-V4-Pro-0813' \
  FAULTLAB_LAB_INPUT_DOLLARS_PER_MILLION=1.31 FAULTLAB_LAB_OUTPUT_DOLLARS_PER_MILLION=3.96 FAULTLAB_DOLLAR_CAP=400 \
  ./scripts/start-live-backend.sh >> artifacts/live-backend-v31-v4lab-20260913.log 2>&1 & )

# Start a learning campaign (makes paid calls; returns when finished)
./scripts/run-demo.sh --mode learn --execute-live --wait > artifacts/NAME.jsonl 2>&1

# Export saved evidence (no model calls; always a new filename)
./scripts/export-evidence.sh --campaign CAMPAIGN_ID --output artifacts/NAME.json

# Tests
cd backend && ../.venv/bin/python -m pytest -q          # expect 361 passed
cd ../frontend && npm test && npm run build
```

Helper scripts copied into ignored `artifacts/tools/`: `summarize_campaign.py` (read-only SQLite summary),
`actor_probe.py` and `nudge_probe.py` (the probes above; they make paid calls). SQLite `records` rows are `kind,id,payload`;
trials link to campaigns only through `episodes` records; open the database read-only (`mode=ro`).

---

## 10. Tools

No MCP server is needed for W&B: the backend uses the Python SDKs and the key in `.env`. Useful Claude Code tools: Bash,
Monitor (waiting on campaigns), the in-app browser for the dashboard at http://127.0.0.1:5173 (paste a campaign ID into
"Open saved campaign"). Weave links need the user's W&B login. Avoid multi-agent workflows while the Claude spend limit is low.

## 11. How the user wants to work

Plain everyday words, one idea at a time, real examples; lead with what is still unproven. Never call a stage done without
its saved evidence. Keep failed and NO_CHANGE runs. No canned or hand-written policy, no weaker checks, no favorable reruns.

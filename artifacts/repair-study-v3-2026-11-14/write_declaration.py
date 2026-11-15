"""Write repair study v3's declaration: code and rule-language digests, the design, caps, stop rules, ledger before."""
import hashlib, json, math, subprocess, sys
from pathlib import Path
R = Path("/Users/shree/FaultLab/faultlab"); d = Path(sys.argv[1])
sys.path[:0] = [str(R / "backend"), str(R)]
from app.config import Settings
from app.providers.spend import SpendLedger
from faultlab.core import Caps, content_hash
from faultlab.research.mechanic import RULE_LANGUAGE
from faultlab.research.repair_study import RepairStudyDesign
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
git = subprocess.run(["git", "-C", str(R), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
assert not subprocess.run(["git", "-C", str(R), "status", "--porcelain"], capture_output=True, text=True).stdout.strip(), "the tree must be clean"
s = Settings.from_env()
per_call = s.per_call_dollar_bound_for_role("actor")
assert per_call * 8 <= 0.034 + 1e-9, per_call
design = RepairStudyDesign(pairs=6, slots=2, mechanic_dollars=0.84, caps=Caps(model_calls=8, http_attempts=18, wall_seconds=90.0, dollars=0.034))
assert design.max_dollars() <= 7.0 and design.legacy_rule == "read" and RULE_LANGUAGE["schema"] == "faultlab-rule-language/v2"
ledger = SpendLedger(s.spend_ledger_path).summary()
pilot_cap = math.ceil((ledger.committed + 6.0) * 100) / 100
files = {"repair_study_sha256": "faultlab/research/repair_study.py", "mechanic_sha256": "faultlab/research/mechanic.py", "study_cli_sha256": "faultlab/research/cli.py",
         "lab_rules_sha256": "faultlab/lab/rules.py", "effectsafe_rules_sha256": "effectsafe/rules.py", "model_actor_sha256": "faultlab/adapters/model_actor.py",
         "claude_agent_sha256": "faultlab/adapters/claude_agent.py", "runtime_provider_sha256": "backend/app/providers/runtime.py"}
decl = {
  "schema": "faultlab-run-declaration/v2", "name": "repair-study-v3-2026-11-14", "declared_at": "2026-11-14",
  "purpose": ("Repair study v3, chosen by the agent under the owner's instruction of 2026-11-14 ('Yeah, please go ahead. We have lots of time and money. We want "
              "to make this project the best. If you want to add more things, add more code, do more tests, and do more verification, just do it.'), after three "
              "unseen-case tests found that the frozen require_label rule removes the slip but its block sometimes costs the agent its last turn."),
  "question": ("Given rule language v2 (a before_agent_turn hook whose advise_label step shows the expected label before the report, and the documented turn cost "
               "of a block) and amendment 11 (legacy referee violations count as findings in both gates), does the Mechanic propose a repair that qualifies on "
               "dev-5 and passes validation on the other public cases, and which hooks does its proposal use?"),
  "no_expectation": "no outcome is expected or required; whether the Mechanic chooses advice, a block or both is a read-out",
  "claim_scope": "a development qualification on the public split for one Actor (Haiku 5.5 on the API) and one Mechanic (Sonnet 5.5); not an unseen-case result, not an active policy",
  "changes_since_pilot_2": ["rule language v2 and the advice hook (340c031)", "amendment 11: legacy referee violations in the candidate and validation gates (340c031)"],
  "roles": {"actor": {"adapter": "model-actor", "model": "anthropic:claude-haiku-5-5", "channel": "Anthropic API (real money)", "context_protocol": s.faultlab_actor_context_protocol},
            "mechanic": {"adapter": "claude-agent", "model": "claude-sonnet-5-5", "channel": "Claude Code on the owner's subscription (no API money; shadow-priced)", "max_turns": 8}},
  "design": design.model_dump(mode="json"), "design_digest": content_hash(design.model_dump(mode="json")),
  "rule_language": {"schema": RULE_LANGUAGE["schema"], "digest": content_hash(RULE_LANGUAGE)},
  "decision_rule": "the study's own decision (REPAIRED, NO_CHANGE or INCOMPLETE) under docs/v2/REPAIR_STUDY.md at this commit (amendments 1 to 8 and 11); nothing read after the run changes it",
  "preflight": {"what": "one live dev-5 trial through `faultlab run --adapter model-actor`, before the study", "pass": "the trial's execution is COMPLETED and its dollars are recorded",
                "on_failure": "the study is not started; the failure is written up"},
  "code": {"git_sha": git, **{k: sha(R / v) for k, v in files.items()}},
  "caps": {"per_trial_usd": 0.034, "study_usd": 7.0, "max_trials": design.max_trials(), "max_dollars": round(design.max_dollars(), 4), "mechanic_per_proposal_usd_equivalent": 0.84,
           "per_call_reservation_usd": round(per_call, 6),
           "monthly": {"owner_api_limit_usd": 200.0, "env_cap_usd": s.faultlab_monthly_dollar_cap, "process_cap_usd": pilot_cap,
                       "rule": "for this run FAULTLAB_MONTHLY_DOLLAR_CAP is lowered to this month's committed dollars plus $6.00"}},
  "stop_rules": ["the study stops at the first stage that cannot run (admission refused, worker stopped, infrastructure): INCOMPLETE",
                 "the ledger refuses any call past the process cap", "a billing message in the preflight stops the launch (402 as a separate number, credit balance, billing)",
                 "one run: no rerun and no change to the design after a result"],
  "pre_registered_readouts": ["1 gap: target findings among valid source controls; healthy validity and findings", "2 gate", "3 proposals: validity, policy, attempts, turns, and the hooks each uses",
                              "4 candidate: L and B0 counts including legacy violations, advice turns and blocked proposals", "5 validation: per case inert or acting, clean acting trials, both arms' counts",
                              "6 decision", "7 cost: Actor dollars and tokens, Mechanic tokens and API-equivalent dollars"],
  "follow_up": "if REPAIRED, the proposal is frozen for an unseen-case comparison on a fresh draw, declared separately",
  "expected_cost": "about $0.25 to $0.50 of API money and 12 to 25 minutes",
  "ledger_before": {"month": ledger.month, "rows": ledger.calls, "committed_usd": round(ledger.committed, 4), "bound_sum_usd": round(ledger.reserved_bound, 4)},
  "machine": {"on_ac_power": "AC Power" in subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True).stdout, "keep_awake": "caffeinate -i for the launcher's lifetime", "other_paid_runs": "none at launch"},
  "outputs": {"record": str(d / "repair-study.json"), "bundles": str(d / "bundles"), "store": str(d / "trials.sqlite3"), "logs": [str(d / "preflight.log"), str(d / "run.log")]},
}
(d / "DECLARATION.json").write_text(json.dumps(decl, indent=2, sort_keys=True))
digest = sha(d / "DECLARATION.json")
(d / "DECLARATION.sha256").write_text(digest + "  DECLARATION.json\n")
(d / "pilot_cap").write_text(f"{pilot_cap:.2f}\n")
print(json.dumps({"declaration_sha256": digest, "pilot_cap": pilot_cap, "ledger": {"rows": ledger.calls, "committed": round(ledger.committed, 4)}, "git": git[:7],
                  "design_digest": decl["design_digest"][:16], "max_trials": design.max_trials(), "max_dollars": round(design.max_dollars(), 3)}))

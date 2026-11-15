"""Write the unseen-case test's declaration: the frozen rule, the draw (counts and digest only), caps, stop rules, ledger before."""
import hashlib, json, math, subprocess, sys
from pathlib import Path
R = Path("/Users/shree/FaultLab/faultlab"); d = Path(sys.argv[1])
sys.path[:0] = [str(R / "backend"), str(R)]
from app.config import Settings
from app.providers.spend import SpendLedger
from faultlab.core import Caps, content_hash
from faultlab.lab.rules import policy_from_json
from faultlab.research.unseen_study import UnseenStudyDesign, case_space
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
git = subprocess.run(["git", "-C", str(R), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
dirty = subprocess.run(["git", "-C", str(R), "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
assert not dirty, "the tree must be clean at declaration"
pilot_dir = R / "artifacts/repair-study-api-pilot-2-2026-10-29"
pilot = json.loads((pilot_dir / "repair-study.json").read_text())
proposal = pilot["proposals"][0]
assert pilot["decision"] == "REPAIRED" and proposal["outcome"] == "REPAIRED" and proposal["valid"]
policy = proposal["policy"]
(d / "policy.json").write_text(json.dumps(policy, indent=2, sort_keys=True))
policy_digest = content_hash(policy_from_json(policy).model_dump(mode="json"))
seed_text = f"{git}|{policy_digest}"
draw = subprocess.run([str(R / ".venv/bin/python"), "-m", "faultlab", "study", "unseen-draw", "--store", str(d / "draw.sqlite3"), "--out", str(d / "sealed"),
                       "--cases", str(d / "sealed/cases.json"), "--worlds", str(d / "sealed/worlds"), "--seed-text", seed_text, "--exclude-cases", str(Path.home() / "FaultLab_Runs/2026-11-08/unseen-study-1/sealed/cases.json"), "--exclude-cases", str(Path.home() / "FaultLab_Runs/2026-11-08/unseen-study-2/sealed/cases.json")],
                      cwd=R, capture_output=True, text=True)
assert draw.returncode == 0, draw.stderr[-400:]
drawn = json.loads(draw.stdout)
assert drawn["cases"] == 8 and drawn["sha256"] == sha(d / "sealed/cases.json")
s = Settings.from_env()
per_call = s.per_call_dollar_bound_for_role("actor")
assert per_call * 8 <= 0.034 + 1e-9, per_call
ledger = SpendLedger(s.spend_ledger_path).summary()
pilot_cap = math.ceil((ledger.committed + 6.0) * 100) / 100
design = UnseenStudyDesign(rejected_cases=[f"unseen-r{i}" for i in range(1, 5)], other_cases=[f"unseen-o{i}" for i in range(1, 5)], pairs=6, gap_min=6,
                           caps=Caps(model_calls=8, http_attempts=18, wall_seconds=90.0, dollars=0.034))
files = {"unseen_study_sha256": "faultlab/research/unseen_study.py", "repair_study_sha256": "faultlab/research/repair_study.py",
         "study_cli_sha256": "faultlab/research/cli.py", "model_actor_sha256": "faultlab/adapters/model_actor.py", "rules_sha256": "faultlab/lab/rules.py",
         "effectsafe_rules_sha256": "effectsafe/rules.py", "orders_pack_sha256": "faultlab/packs/orders/pack.py", "runtime_provider_sha256": "backend/app/providers/runtime.py"}
decl = {
  "schema": "faultlab-run-declaration/v2", "name": "unseen-study-3-2026-11-14", "declared_at": "2026-11-14",
  "purpose": ("The third unseen-case test of the same frozen rule, on a fresh draw, under amendments 9 and 10. Approved by the owner on 2026-11-14 ('go ahead with the one more test') "
              "in answer to 'one more test, with the step limit set back to 8 and the criteria also checking that limit'."),
  "amendment_10": {"document": "docs/v2/UNSEEN_STUDY.md", "commit": git, "approved_by_owner": "2026-11-14", "makes_a_pass_harder": True,
                   "text": "a trial where the rule acted must also carry no legacy referee violation; every trial runs within the repair study's limits of 8 model calls, 18 HTTP attempts and 90 seconds (runs 1 and 2 allowed 12, 24 and 120)",
                   "why": "in run 2 two trials under the rule ended VIOLATION on the legacy C8 after nine model calls, and the gate did not read legacy findings"},
  "amendment_9": {"text": "a rejected case is judged where the rule acted, whether or not another scheduled fault fired", "approved_by_owner": "2026-11-08", "relaxes_a_gate_after_a_failure": True},
  "previous_runs": [{"name": "unseen-study-1-2026-11-08", "declaration_sha256": sha(Path.home() / "FaultLab_Runs/2026-11-08/unseen-study-1/DECLARATION.json"), "decision": "NOT_TRANSFERRED", "api_usd_real_money": 0.2898,
                     "why": "two rejected cases failed the candidate gate because one L trial each left a scheduled fault unfired"},
                    {"name": "unseen-study-2-2026-11-08", "declaration_sha256": sha(Path.home() / "FaultLab_Runs/2026-11-08/unseen-study-2/DECLARATION.json"), "decision": "TRANSFERRED (under amendment 9; not a clean pass)", "api_usd_real_money": 0.2757,
                     "why": "slip 22 of 24 to 0 of 24, but two L trials carried a legacy C8 violation that the gate did not read"}],
  "claim_scope": "new fault schedules of the same task, fixtures and fault types; not new tasks; a test of one rule with one Actor (Haiku 5.5 on the API); not an active policy",
  "pre_registration": {"document": "docs/v2/UNSEEN_STUDY.md", "commit": git, "rule_and_method_committed_before_the_draw": True},
  "frozen_rule": {"source": str(pilot_dir.relative_to(R)), "pilot_declaration_sha256": pilot["declaration"]["sha256"], "policy": policy, "policy_digest": policy_digest,
                  "written_by": "the Sonnet 5.5 Mechanic of the second API pilot, shown one dev-5 trial; not changed since"},
  "draw": {"seed_text": seed_text, "seed_rule": "the commit holding the code and the frozen rule's digest", "space": {k: len(v) for k, v in case_space().items()},
           "per_stratum": 4, "excluded": "the sixteen cases of unseen-study-1 and unseen-study-2", "tried": drawn["tried"], "cases_file_sha256": drawn["sha256"], "cases": drawn["cases"],
           "sealed": "the case file and trial bundles stay outside the repository and are not opened by the agent; the record names cases by id only"},
  "design": design.model_dump(mode="json"), "design_digest": content_hash(design.model_dump(mode="json")),
  "decision_rule": ("NOT_TRANSFERRED if any case fails (rejected: amendments 9 and 10; other: the validation rule of amendment 8); INCONCLUSIVE if none fails and the slip appeared in "
                    "fewer than 6 of the 24 B0 trials of the rejected cases; TRANSFERRED otherwise; INCOMPLETE if a stage cannot run. The recorded decision is the result."),
  "roles": {"actor": {"adapter": "model-actor", "model": "anthropic:claude-haiku-5-5", "channel": "Anthropic API (real money)", "context_protocol": s.faultlab_actor_context_protocol},
            "mechanic": "none: the rule arrives frozen"},
  "preflight": {"what": "one live dev-5 trial through `faultlab run --adapter model-actor`, before the study, as in the second API pilot",
                "pass": "the trial's execution is COMPLETED and its measured dollars are recorded", "on_failure": "the study is not started; the failure is written up"},
  "code": {"git_sha": git, **{k: sha(R / v) for k, v in files.items()}},
  "caps": {"per_trial_usd": 0.034, "study_usd": 3.27, "max_trials": design.max_trials(), "per_call_reservation_usd": round(per_call, 6),
           "monthly": {"owner_api_limit_usd": 200.0, "env_cap_usd": s.faultlab_monthly_dollar_cap, "process_cap_usd": pilot_cap,
                       "rule": "for this run FAULTLAB_MONTHLY_DOLLAR_CAP is lowered to this month's committed dollars plus $6.00"}},
  "stop_rules": ["the study stops at the first stage that cannot run (admission refused, worker stopped, infrastructure): INCOMPLETE",
                 "the ledger refuses any call past the process cap", "a billing message in the preflight stops the launch",
                 "one run per draw: no rerun and no change to the rule, the cases or the decision rule after a result"],
  "expected_cost": "about $0.30 of API money (the second pilot measured $0.0029 per trial) and about 15 minutes",
  "ledger_before": {"month": ledger.month, "rows": ledger.calls, "committed_usd": round(ledger.committed, 4), "bound_sum_usd": round(ledger.reserved_bound, 4)},
  "machine": {"on_ac_power": "AC Power" in subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True).stdout, "keep_awake": "caffeinate -i for the launcher's lifetime", "other_paid_runs": "none at launch"},
  "outputs": {"record": str(d / "unseen-study.json"), "bundles": str(d / "bundles"), "store": str(d / "trials.sqlite3"), "logs": [str(d / "preflight.log"), str(d / "run.log")]},
}
(d / "DECLARATION.json").write_text(json.dumps(decl, indent=2, sort_keys=True))
digest = sha(d / "DECLARATION.json")
(d / "DECLARATION.sha256").write_text(digest + "  DECLARATION.json\n")
(d / "pilot_cap").write_text(f"{pilot_cap:.2f}\n")
print(json.dumps({"declaration_sha256": digest, "pilot_cap": pilot_cap, "ledger": {"month": ledger.month, "committed": round(ledger.committed, 4), "rows": ledger.calls},
                  "draw": {k: drawn[k] for k in ("cases", "tried")}, "git": git[:7], "design_digest": decl["design_digest"][:16], "max_trials": design.max_trials(), "per_call": round(per_call, 6)}))

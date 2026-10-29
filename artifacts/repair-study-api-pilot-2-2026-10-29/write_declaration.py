"""Write the second API pilot's declaration at launch time: code hashes, amendment 8 and its reading, caps, stop rules, ledger before."""
import hashlib, json, math, subprocess, sys
from pathlib import Path
R = Path("/Users/shree/FaultLab/faultlab"); d = Path(sys.argv[1])
sys.path[:0] = [str(R / "backend"), str(R)]
from app.config import Settings
from app.providers.spend import SpendLedger
from faultlab.core import content_hash
from faultlab.research.repair_study import RepairStudyDesign
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
pilot1 = Path.home() / "FaultLab_Runs/2026-10-28/repair-study-api-pilot/DECLARATION.json"
pilot1_record = json.loads((R / "artifacts/repair-study-api-pilot-2026-10-28/repair-study.json").read_text())
base = json.loads(pilot1.read_text())
s = Settings.from_env()
ledger = SpendLedger(s.spend_ledger_path).summary()
pilot_cap = math.ceil((ledger.committed + 6.0) * 100) / 100
old_design = pilot1_record["design"]
assert "validation_rule" not in old_design and content_hash(old_design) == pilot1_record["design_digest"]
new_design = RepairStudyDesign(**old_design).model_dump(mode="json")          # pilot 1's design; the new field takes its default
assert {k: v for k, v in new_design.items() if k != "validation_rule"} == old_design and new_design["validation_rule"] == "where_acted"
design = dict(base["design"]); design["validation_rule"] = "where_acted (amendment 8)"
git = subprocess.run(["git", "-C", str(R), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
dirty = subprocess.run(["git", "-C", str(R), "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
assert not dirty, "the tree must be clean at declaration"
files = {"claude_agent_sha256": "faultlab/adapters/claude_agent.py", "effectsafe_rules_sha256": "effectsafe/rules.py",
         "mechanic_sha256": "faultlab/research/mechanic.py", "model_actor_sha256": "faultlab/adapters/model_actor.py",
         "repair_study_sha256": "faultlab/research/repair_study.py", "rules_sha256": "faultlab/lab/rules.py",
         "runtime_provider_sha256": "backend/app/providers/runtime.py", "study_cli_sha256": "faultlab/research/cli.py"}
code = {"git_sha": git, **{k: sha(R / v) for k, v in files.items()}}
changed = sorted(k for k in files if code[k] != base["code"][k])
assert changed == ["repair_study_sha256"], changed                      # only the study module changed since pilot 1
amendment_text = ("Validation attributes a regression to the rule only where the rule acted. A validation case in which the policy "
                  "ran no step and blocked nothing in any L trial is inert: its L trials received exactly the B0 inputs, so the case "
                  "passes and is reported as inert with both arms' counts. In a case where the policy acted in at least one L trial, "
                  "every trial where it acted must be valid, carry no conformance finding and no false belief, and reach the case's "
                  "expected outcome. The candidate stage is unchanged. A rule that fires outside the source case is still judged where "
                  "it fires (the overreach test keeps failing a rule that blocks truthful reports).")
note = (R / "docs/VIOLATION_GAP_DESIGN_2026-10-25.md").read_text()
assert " ".join(amendment_text.split()) in " ".join(note.replace("*", "").split()), "the amendment text must match the design note verbatim"
decl = {
  "schema": "faultlab-run-declaration/v2", "name": "repair-study-api-pilot-2-2026-10-29", "declared_at": "2026-10-29",
  "purpose": ("The second API pilot of the repair study, approved by the owner on 2026-10-29 ('yeah please go ahead') in answer to "
              "'a second API pilot under amendment 8, otherwise identical': Haiku 5.5 as Actor on the Anthropic API through the "
              "model-actor adapter, Sonnet 5.5 as Mechanic on Claude Code (the subscription), six pairs, the validation rule of "
              "amendment 8; everything else as the first API pilot."),
  "amendment_8": {"text": amendment_text, "pre_registered_in": "docs/VIOLATION_GAP_DESIGN_2026-10-25.md at 1ea87b4, before this run",
                  "applied_in": git[:7],
                  "reading": ["an act is a report-gate rule step that ran at least one step or blocked a proposal; the policy_declared event is not an act",
                              "valid means what it means for controls and the candidate: the execution completed and every scheduled fault fired",
                              "the existing must_complete gate is kept, read per acting trial: in dev-1 and dev-6 every trial where the rule acted must complete",
                              "trials where the rule did not act are not judged, in any case",
                              "both arms still run in every validation case (both arms' counts are reported); B0 no longer enters the validation decision"],
                  "post_hoc_note": "read against the first pilot's saved rows, both of its proposals would have passed (neither acted in any validation trial); that is why this run is a new pilot, not a re-scoring"},
  "frozen_design": {"commit": git[:7], "pilot1_declaration_sha256": sha(pilot1), "only_change_from_pilot1": "amendment 8 (the validation rule); the study module is the only changed file",
                    "design_digest_pilot1": pilot1_record["design_digest"], "design_digest": content_hash(new_design)},
  "code": code,
  "channel": base["channel"],
  "roles": {**base["roles"], "actor": {**base["roles"]["actor"], "context_protocol": s.faultlab_actor_context_protocol}},
  "design": design,
  "decision_rule": "the study's own decision under the rules above (REPAIRED, NO_CHANGE or INCOMPLETE) is the result; nothing read after the run changes it",
  "preflight": {"what": "one live dev-5 trial through `faultlab run --adapter model-actor` with the same settings, before the study, as in the first pilot",
                "pass": "the trial's execution is COMPLETED (a scored task outcome, whatever it is) and its measured dollars are recorded",
                "on_failure": "the study is not started; the failure is written up"},
  "caps": {**base["caps"], "per_call_reservation_usd": round(s.per_call_dollar_bound_for_role("actor"), 6),
           "monthly": {"owner_api_limit_usd": 200.0, "env_cap_usd": s.faultlab_monthly_dollar_cap, "pilot_process_cap_usd": pilot_cap,
                       "rule": "for this run FAULTLAB_MONTHLY_DOLLAR_CAP is lowered to October's committed dollars plus $6.00, so the ledger refuses any call that would spend more than about $6 in total"}},
  "stop_rules": base["stop_rules"],
  "pre_registered_readouts": base["pre_registered_readouts"][:4] + [
      "5 validation: per case, inert or acting; where the rule acted, how many acting trials were clean; findings, false beliefs, expected outcome and completions under B0 and L"] + base["pre_registered_readouts"][5:],
  "expected_cost": "about $0.46 of API money (the first pilot measured $0.4575 for 154 trials) and about 22 minutes",
  "ledger_before": {"month": ledger.month, "rows": ledger.calls, "committed_usd": round(ledger.committed, 4), "bound_sum_usd": round(ledger.reserved_bound, 4)},
  "previous_runs": base["previous_runs"] + [{"name": "repair-study-api-pilot-2026-10-28", "declaration_sha256": sha(pilot1), "decision": "NO_CHANGE",
                                              "api_usd_real_money": 0.4575, "why": "both proposals qualified (slip 0 of 12 under L, 11 of 12 under B0) and failed validation in cases where the rule never acted"}],
  "incidents_before_launch": ["2026-10-29T11:42:12Z: an attempt launched without a declaration (the declaration script failed its text check and the "
                              "launch command did not stop); the preflight refused the empty monthly cap (ConfigurationError) before any provider call; "
                              "no ledger row; files kept in aborted-launch-2026-10-29T1142Z/ with a README. launch.sh now refuses to start without a "
                              "declaration whose sha256 matches and a numeric pilot cap"],
  "machine": {"on_ac_power": "AC Power" in subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True).stdout,
              "keep_awake": "held through the desktop app for the session", "other_paid_runs": "none at launch"},
  "outputs": {"record": str(d / "repair-study.json"), "bundles": str(d / "bundles"), "store": str(d / "trials.sqlite3"),
              "preflight_store": str(d / "preflight.sqlite3"), "logs": [str(d / "preflight.log"), str(d / "run.log")]},
}
(d / "DECLARATION.json").write_text(json.dumps(decl, indent=2, sort_keys=True))
digest = sha(d / "DECLARATION.json")
(d / "DECLARATION.sha256").write_text(digest + "  DECLARATION.json\n")
(d / "pilot_cap").write_text(f"{pilot_cap:.2f}\n")
print(json.dumps({"declaration_sha256": digest, "pilot_cap": pilot_cap, "ledger_committed": round(ledger.committed, 4), "rows": ledger.calls,
                  "git": git[:7], "design_digest": content_hash(new_design)[:16]}))

"""Second re-declaration of unseen-case test 3: the billing guard tripped on a random trial id; same draw and code, the guard narrowed."""
import hashlib, json, math, shutil, subprocess, sys
from pathlib import Path
R = Path("/Users/shree/FaultLab/faultlab"); d = Path(sys.argv[1])
sys.path[:0] = [str(R / "backend"), str(R)]
from app.config import Settings
from app.providers.spend import SpendLedger
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
SECOND = "fd13716aaea35ff075a01e839f71c1ffa13e56914617f76a4ff1c9e8407d29fc"
old = json.loads((d / "DECLARATION.json").read_text())
assert sha(d / "DECLARATION.json") == SECOND and sha(d / "sealed/cases.json") == old["draw"]["cases_file_sha256"]
assert not (d / "unseen-study.json").exists() and not (d / "trials.sqlite3").exists()          # no case trial has run
assert not subprocess.run(["git", "-C", str(R), "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
files = {"unseen_study_sha256": "faultlab/research/unseen_study.py", "repair_study_sha256": "faultlab/research/repair_study.py",
         "study_cli_sha256": "faultlab/research/cli.py", "model_actor_sha256": "faultlab/adapters/model_actor.py", "rules_sha256": "faultlab/lab/rules.py",
         "effectsafe_rules_sha256": "effectsafe/rules.py", "orders_pack_sha256": "faultlab/packs/orders/pack.py", "runtime_provider_sha256": "backend/app/providers/runtime.py"}
assert all(sha(R / v) == old["code"][k] for k, v in files.items())
launch = (d / "launch.sh").read_text()
old_guard = 'grep -q -i -E "402|insufficient credit|billing"'
assert launch.count(old_guard) == 1
aborted = d / "aborted-launch-2026-11-15T0540Z"
aborted.mkdir()
for path in [*d.glob("preflight*"), *(d / n for n in ("launcher.log", "DECLARATION.json", "DECLARATION.sha256", "pilot_cap"))]:
    if path.exists():
        shutil.move(str(path), str(aborted / path.name))
(aborted / "launch.sh").write_text(launch)
(d / "launch.sh").write_text(launch.replace(old_guard, "grep -q -i -E '(^|[^0-9a-z])402([^0-9a-z]|$)|insufficient credit|credit balance|billing'"))
(aborted / "README.md").write_text("""# Second launch of unseen-case test 3: stopped by a false billing alarm (2026-11-15T05:40Z)

With the owner's new API key the preflight passed (dev-5, COMPLETED, $0.0021), but the launcher's billing guard,
`grep -i -E "402|insufficient credit|billing"`, matched the random trial id `trial-c064e4402417...` in preflight.log, so the
study was not started and no case trial ran. The guard now matches 402 only as a separate number and also matches
"credit balance"; the launcher as it ran is kept here. Earlier launchers had the same latent flaw; it never tripped.
""")
ledger = SpendLedger(Settings.from_env().spend_ledger_path).summary()
pilot_cap = math.ceil((ledger.committed + 6.0) * 100) / 100
new = dict(old)
new.update({
  "second_declaration_sha256": SECOND,
  "incidents_before_launch": old["incidents_before_launch"] + [
      ("2026-11-15T05:40:39Z: with the new key the preflight passed (dev-5, COMPLETED, $0.0021), but the launcher's billing guard matched '402' inside the random "
       "trial id in preflight.log, so the study was not started and no case trial ran. The guard now matches 402 only as a separate number, plus 'credit balance'. "
       "Files and the launcher as it ran are in aborted-launch-2026-11-15T0540Z/.")],
  "ledger_before": {"month": ledger.month, "rows": ledger.calls, "committed_usd": round(ledger.committed, 4), "bound_sum_usd": round(ledger.reserved_bound, 4)},
  "caps": {**old["caps"], "monthly": {**old["caps"]["monthly"], "process_cap_usd": pilot_cap}},
  "launcher_sha256": sha(d / "launch.sh"),
})
(d / "DECLARATION.json").write_text(json.dumps(new, indent=2, sort_keys=True))
digest = sha(d / "DECLARATION.json")
(d / "DECLARATION.sha256").write_text(digest + "  DECLARATION.json\n")
(d / "pilot_cap").write_text(f"{pilot_cap:.2f}\n")
print(json.dumps({"declaration_sha256": digest, "pilot_cap": pilot_cap, "ledger": {"rows": ledger.calls, "committed": round(ledger.committed, 4)}}))

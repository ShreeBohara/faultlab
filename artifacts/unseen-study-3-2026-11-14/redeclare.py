"""Re-declare unseen-case test 3 after its first launch failed on a rejected API key: the same draw and code, the incident recorded."""
import hashlib, json, math, shutil, subprocess, sys
from pathlib import Path
R = Path("/Users/shree/FaultLab/faultlab"); d = Path(sys.argv[1])
sys.path[:0] = [str(R / "backend"), str(R)]
from app.config import Settings
from app.providers.spend import SpendLedger
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
FIRST = "a3519230d146f4f5f6601f53925818f52f8686525ded5a99cd702ecfb772bfb3"
old = json.loads((d / "DECLARATION.json").read_text())
assert sha(d / "DECLARATION.json") == FIRST and sha(d / "sealed/cases.json") == old["draw"]["cases_file_sha256"]
git = subprocess.run(["git", "-C", str(R), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
assert not subprocess.run(["git", "-C", str(R), "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
files = {"unseen_study_sha256": "faultlab/research/unseen_study.py", "repair_study_sha256": "faultlab/research/repair_study.py",
         "study_cli_sha256": "faultlab/research/cli.py", "model_actor_sha256": "faultlab/adapters/model_actor.py", "rules_sha256": "faultlab/lab/rules.py",
         "effectsafe_rules_sha256": "effectsafe/rules.py", "orders_pack_sha256": "faultlab/packs/orders/pack.py", "runtime_provider_sha256": "backend/app/providers/runtime.py"}
changed = [k for k, v in files.items() if sha(R / v) != old["code"][k]]
assert not changed, changed                                   # the code that runs is the code declared at the first launch
aborted = d / "aborted-launch-2026-11-15T0531Z"
aborted.mkdir()
for path in [*d.glob("preflight*"), *(d / n for n in ("launcher.log", "README.md", "DECLARATION.json", "DECLARATION.sha256", "pilot_cap"))]:
    if path.exists():
        shutil.move(str(path), str(aborted / path.name))
s = Settings.from_env()
ledger = SpendLedger(s.spend_ledger_path).summary()
pilot_cap = math.ceil((ledger.committed + 6.0) * 100) / 100
new = dict(old)
new.update({
  "redeclared_at": "2026-11-14", "first_declaration_sha256": FIRST,
  "incidents_before_launch": [("2026-11-15T05:31:24Z: the first launch's preflight failed with ADAPTER_ERROR:RuntimeProviderError, so the study did not start and no "
                               "case trial ran. A second preflight failed the same way, and one diagnostic call showed HTTP 401 AuthenticationError: the Anthropic "
                               "API key in .env was rejected. The owner replaced the key the same evening; a model-list request then returned HTTP 200. Nothing was "
                               "billed; the ledger booked three reservations ($0.0126). The first launch's files are in aborted-launch-2026-11-15T0531Z/ with a README.")],
  "code": {**old["code"], "git_sha_at_launch": git},
  "ledger_before": {"month": ledger.month, "rows": ledger.calls, "committed_usd": round(ledger.committed, 4), "bound_sum_usd": round(ledger.reserved_bound, 4)},
  "caps": {**old["caps"], "monthly": {**old["caps"]["monthly"], "process_cap_usd": pilot_cap}},
})
(d / "DECLARATION.json").write_text(json.dumps(new, indent=2, sort_keys=True))
digest = sha(d / "DECLARATION.json")
(d / "DECLARATION.sha256").write_text(digest + "  DECLARATION.json\n")
(d / "pilot_cap").write_text(f"{pilot_cap:.2f}\n")
print(json.dumps({"declaration_sha256": digest, "pilot_cap": pilot_cap, "ledger": {"rows": ledger.calls, "committed": round(ledger.committed, 4)},
                  "same_draw": new["draw"]["cases_file_sha256"] == old["draw"]["cases_file_sha256"], "git_at_launch": git[:7], "moved": sorted(p.name for p in aborted.iterdir())}))

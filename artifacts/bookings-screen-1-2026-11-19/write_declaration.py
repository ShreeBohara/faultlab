"""Declaration of bookings screen 1 (second task plan, step 5): Haiku 5.5 as the pack-built Actor, 8 public cases x 3."""
import hashlib, json, math, subprocess, sys
from pathlib import Path
R = Path("/Users/shree/FaultLab/faultlab")
sys.path[:0] = [str(R), str(R / "backend")]
from app.config import Settings
from app.providers.pricing import describe
from app.providers.spend import SpendLedger
from faultlab.adapters.pack_actor import PackActorAdapter
from faultlab.core import content_hash
from faultlab.packs.bookings.pack import PACK
from faultlab.referee.bookings import checker_digest

MODEL, d = "anthropic:claude-haiku-5-5", Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
git = subprocess.run(["git", "-C", str(R), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
assert not subprocess.run(["git", "-C", str(R), "status", "--porcelain"], capture_output=True, text=True).stdout.strip(), "the tree must be clean"
adapter = PackActorAdapter(provider=None, model=MODEL, pack_id=PACK.pack_id)
per_call, calls = 0.0042, 8
per_trial = round(per_call * calls, 4)
cases = [s.scenario_id for s in PACK.scenarios]
s = Settings.from_env()
ledger = SpendLedger(s.spend_ledger_path).summary()
pilot_cap = math.ceil((ledger.committed + 0.81) * 100) / 100
design = {"pack_id": PACK.pack_id, "pack_digest": PACK.digest(), "cases": cases, "trials_per_case": 3,
          "adapter": {"id": "pack-actor", "version": adapter.spec.version, "prompt_digest": adapter.spec.prompt_digest,
                      "settings_digest": adapter.spec.settings_digest},
          "referee": {"id": "bookings", "checker_sha256": checker_digest()}, "model": MODEL,
          "caps_per_trial": {"model_calls": calls, "http_attempts": 18, "wall_seconds": 90, "dollars": per_trial}}
decl = {
  "name": "bookings-screen-1-2026-11-19", "kind": "development_screen",
  "question": ("With Haiku 5.5 as the pack-built Actor (pack-actor) on the eight public cases of the bookings task, three trials each "
               "and no rule: which checks does it fail, and does any case show a repeated mistake (the same lowest failed check in at "
               "least 2 of its 3 trials)?"),
  "claim": ("A development screen on public cases: how often this model makes the task's mistakes here. Not an unseen-case result; "
            "no repair and no policy is involved."),
  "design": design, "design_digest": content_hash(design),
  "actor": {"model": MODEL, "pricing": describe(MODEL), "per_call_reservation_usd": per_call, "per_trial_bound_usd": per_trial},
  "order": "hk-dev-2 first (three trials, the preflight), then the other seven cases, three trials each: 24 trials in all",
  "preflight": {"scenario": "hk-dev-2", "trials": 3,
                "pass": ("all three executions COMPLETED with recorded dollars and under 80 seconds of wall time; every ledger row they added "
                         "names the model; no answer reached 1,900 output tokens; mean cost under $0.03 a trial. A missing or invalid report "
                         "is a finding of the screen, not a preflight failure. The preflight trials count as the case's three trials.")},
  "readouts": ["per case: the failed checks and the lowest failed check of each trial", "the task's target mistakes: trials failing H2 "
               "(duplicate holding) and H3 (abandoned hold)", "trials with no report", "the oracle's false beliefs by claim",
               "measured dollars and model calls"],
  "decision_rule": ("A case shows a repeated mistake when the same lowest failed check appears in at least 2 of its 3 trials. Any repeated "
                    "mistake makes step 6 (a repair study on that case) worth proposing to the owner; none means no repeated mistake was "
                    "found on the public cases, and it is reported that way."),
  "stop_rules": ["a billing message in any log stops the run", "the preflight must PASS before the other 21 trials run",
                 "the batch dollar caps ($0.1008 and $0.7056) and the process monthly cap refuse further calls",
                 "an INFRA_ERROR trial is reported, not retried"],
  "money": {"quoted_max_usd": 0.81, "batch_caps_usd": {"preflight": round(3 * per_trial, 4), "rest": round(21 * per_trial, 4)},
            "monthly": {"owner_api_limit_usd": 200.0, "env_cap_usd": s.faultlab_monthly_dollar_cap, "process_cap_usd": pilot_cap,
                        "rule": "for this run FAULTLAB_MONTHLY_DOLLAR_CAP is lowered to this month's committed dollars plus the quoted $0.81"}},
  "code": {"git_sha": git, **{key: sha(R / path) for key, path in {
      "bookings_pack_sha256": "faultlab/packs/bookings/pack.py", "bookings_handler_sha256": "faultlab/packs/bookings/handler.py",
      "pack_actor_sha256": "faultlab/adapters/pack_actor.py", "bookings_referee_sha256": "faultlab/referee/bookings.py",
      "bookings_oracle_sha256": "faultlab/referee/oracle/bookings.py", "september_checks_sha256": "taskpacks/bookings_move_with_hold/checks.py",
      "lab_session_sha256": "faultlab/lab/session.py", "kernel_dispatch_sha256": "faultlab/env/kernel/dispatch.py",
      "runtime_provider_sha256": "backend/app/providers/runtime.py", "pricing_table_sha256": "backend/app/providers/pricing.json"}.items()}},
  "ledger_before": {"month": ledger.month, "rows": ledger.calls, "committed_usd": round(ledger.committed, 4),
                    "bound_sum_usd": round(ledger.reserved_bound, 4)},
}
(d / "DECLARATION.json").write_text(json.dumps(decl, indent=2, sort_keys=True))
digest = sha(d / "DECLARATION.json")
(d / "DECLARATION.sha256").write_text(digest + "  DECLARATION.json\n")
(d / "pilot_cap").write_text(f"{pilot_cap:.2f}\n")
print(json.dumps({"declaration_sha256": digest, "pilot_cap": pilot_cap, "ledger": {"month": ledger.month, "rows": ledger.calls,
                  "committed": round(ledger.committed, 4)}, "git": git[:7], "pricing": describe(MODEL), "per_trial": per_trial}))

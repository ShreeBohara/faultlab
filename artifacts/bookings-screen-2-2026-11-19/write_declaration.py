"""Declaration of bookings screen 2: Haiku 5.5 as pack-actor on 16 newly drawn bookings cases (4 per stratum) x 3."""
import hashlib, json, math, subprocess, sys
from pathlib import Path
R = Path("/Users/shree/FaultLab/faultlab")
sys.path[:0] = [str(R), str(R / "backend")]
from app.config import Settings
from app.providers.pricing import describe
from app.providers.spend import SpendLedger
from faultlab.adapters.pack_actor import PackActorAdapter
from faultlab.core import canonical_json, content_hash
from faultlab.packs.bookings.pack import PACK
from faultlab.referee.bookings import checker_digest
from faultlab.research.bookings_draw import draw, load_cases, pack_with

MODEL, d = "anthropic:claude-haiku-5-5", Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
git = subprocess.run(["git", "-C", str(R), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
assert not subprocess.run(["git", "-C", str(R), "status", "--porcelain"], capture_output=True, text=True).stdout.strip(), "the tree must be clean"
seed_text = f"{git}|{PACK.digest()}|bookings-screen-2:new-cases"          # fixed here, before the draw
drawn = draw(seed_text, 4)
(d / "cases.json").write_text(canonical_json(drawn))
pack = pack_with(load_cases(d / "cases.json"))
adapter = PackActorAdapter(provider=None, model=MODEL, pack_id=PACK.pack_id)
per_call, calls = 0.0042, 8
per_trial = round(per_call * calls, 4)
s = Settings.from_env()
ledger = SpendLedger(s.spend_ledger_path).summary()
pilot_cap = math.ceil((ledger.committed + 0.50) * 100) / 100
design = {"pack_id": PACK.pack_id, "pack_digest": pack.digest(), "cases_sha256": sha(d / "cases.json"), "cases": [c["case_id"] for c in drawn["cases"]],
          "strata": {c["case_id"]: c["stratum"] for c in drawn["cases"]}, "trials_per_case": 3, "seed_text": seed_text,
          "draw": {"per_stratum": 4, "space": drawn["space"], "tried": drawn["tried"],
                   "rule": "each stratum shuffled by the seed text, taken in order while the September reference plays the case cleanly through the worker, fires every fault and keeps a turn"},
          "adapter": {"id": "pack-actor", "version": adapter.spec.version, "prompt_digest": adapter.spec.prompt_digest, "settings_digest": adapter.spec.settings_digest},
          "referee": {"id": "bookings", "checker_sha256": checker_digest()}, "model": MODEL,
          "caps_per_trial": {"model_calls": calls, "http_attempts": 18, "wall_seconds": 90, "dollars": per_trial}}
decl = {
  "name": "bookings-screen-2-2026-11-19", "kind": "development_screen",
  "question": ("With Haiku 5.5 as pack-actor on 16 bookings cases drawn new from the September fault grammar (four per stratum: lost_create, "
               "move_trouble, hold_trouble, other), three trials each and no rule: which checks does it fail, and does any case show a repeated "
               "mistake (the same lowest failed check in at least 2 of its 3 trials)?"),
  "claim": ("A development screen on newly drawn schedules of the same task. It tells whether Haiku's habits break on harder or different "
            "faults than the public cases; it is not an unseen-case test of any rule, and these cases become development evidence."),
  "design": design, "design_digest": content_hash(design),
  "actor": {"model": MODEL, "pricing": describe(MODEL), "per_call_reservation_usd": per_call, "per_trial_bound_usd": per_trial},
  "order": "the first drawn case first (three trials, the preflight), then the other fifteen, three trials each: 48 trials in all",
  "preflight": {"case": drawn["cases"][0]["case_id"], "trials": 3,
                "pass": ("all three executions COMPLETED with recorded dollars and under 80 seconds of wall time; every ledger row they added names "
                         "the model; no answer reached 1,900 output tokens; mean cost under $0.03 a trial. A missing or invalid report is a finding, "
                         "not a preflight failure. The preflight trials count as the case's three trials.")},
  "readouts": ["per case and stratum: the failed checks and the lowest failed check of each trial", "trials failing H2 and H3",
               "trials with no report", "trials reported SAFE_UNRESOLVED", "the oracle's false beliefs by claim", "measured dollars and model calls"],
  "decision_rule": ("A case shows a repeated mistake when the same lowest failed check appears in at least 2 of its 3 trials. Any repeated mistake "
                    "makes a repair study on that case worth proposing to the owner (a new draw would then be the unseen test); none means no "
                    "repeated mistake was found on these cases, and it is reported that way."),
  "stop_rules": ["a billing message in any log stops the run", "the preflight must PASS before the other 45 trials run",
                 "the batch dollar caps ($0.1008 and $0.3992, $0.50 in all) and the process monthly cap refuse further calls",
                 "an INFRA_ERROR trial is reported, not retried"],
  "money": {"quoted_range_usd": [0.10, 0.50], "hard_cap_usd": 0.50, "batch_caps_usd": {"preflight": 0.1008, "rest": 0.3992},
            "monthly": {"owner_api_limit_usd": 200.0, "env_cap_usd": s.faultlab_monthly_dollar_cap, "process_cap_usd": pilot_cap,
                        "rule": "for this run FAULTLAB_MONTHLY_DOLLAR_CAP is lowered to this month's committed dollars plus the $0.50 hard cap"}},
  "code": {"git_sha": git, **{key: sha(R / path) for key, path in {
      "bookings_draw_sha256": "faultlab/research/bookings_draw.py", "bookings_pack_sha256": "faultlab/packs/bookings/pack.py",
      "bookings_handler_sha256": "faultlab/packs/bookings/handler.py", "pack_actor_sha256": "faultlab/adapters/pack_actor.py",
      "bookings_referee_sha256": "faultlab/referee/bookings.py", "bookings_oracle_sha256": "faultlab/referee/oracle/bookings.py",
      "september_checks_sha256": "taskpacks/bookings_move_with_hold/checks.py", "lab_session_sha256": "faultlab/lab/session.py",
      "runtime_provider_sha256": "backend/app/providers/runtime.py", "pricing_table_sha256": "backend/app/providers/pricing.json"}.items()}},
  "ledger_before": {"month": ledger.month, "rows": ledger.calls, "committed_usd": round(ledger.committed, 4), "bound_sum_usd": round(ledger.reserved_bound, 4)},
}
(d / "DECLARATION.json").write_text(json.dumps(decl, indent=2, sort_keys=True))
(d / "DECLARATION.sha256").write_text(sha(d / "DECLARATION.json") + "  DECLARATION.json\n")
(d / "pilot_cap").write_text(f"{pilot_cap:.2f}\n")
print(json.dumps({"declaration_sha256": sha(d / "DECLARATION.json"), "pilot_cap": pilot_cap, "committed": round(ledger.committed, 4),
                  "cases": {c["case_id"]: (c["stratum"], [f"{p['kind']}:{p['target_tool']}#{p['occurrence']}" for p in c["scenario"]["fault_spec"]["primitives"]])
                            for c in drawn["cases"]}, "tried": drawn["tried"], "space": drawn["space"], "git": git[:7]}))

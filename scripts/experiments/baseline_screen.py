"""Run the frozen development baseline study for one Actor model, under a declaration.

One invocation = one model = one fresh store: start the local services in live mode with the
model selected through the environment, create a live baseline campaign, queue the six-case,
three-trial baseline study, watch it to a terminal status under the declared stop rules, save
the study record, the campaign, its budget and the evidence export next to the store, then stop
the services. Nothing here changes the lab's gates or scoring; it only drives the existing API.

Usage (from the repository root, with the owner's .env in place):

  ./.venv/bin/python scripts/experiments/baseline_screen.py \\
      --model anthropic:claude-haiku-5-5 --data-dir ~/FaultLab_Runs/2026-10-11/claude-actor-screen/haiku-5-5 \\
      --declaration ~/FaultLab_Runs/2026-10-11/claude-actor-screen/DECLARATION.json \\
      --declaration-sha256 <sha> --dollar-cap 60
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

TASK_TEXT = "Upgrade the authorized order to express shipping, then record one truthful confirmation."
TERMINAL = ("COMPLETED", "INCOMPLETE", "INTERRUPTED")
# Which study a run queues: the frozen baseline study (phase A/B) or the generated completion-recovery
# study (controls, Mechanic proposals, source gate, validation batch; never activates a policy).
STUDIES = {
    "baseline": {"queue": "/api/campaigns/{campaign_id}/baseline-study", "status": "/api/baseline-studies/{study_id}",
                 "record": "baseline-study.json", "slots": 36, "live": 18},
    "completion": {"queue": "/api/campaigns/{campaign_id}/completion-study", "status": "/api/completion-studies/{study_id}",
                   "record": "completion-study.json", "slots": None, "live": None},
}


def log(run_dir: Path, message: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {message}"
    print(line, flush=True)
    with (run_dir / "driver.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def port_free(port: int) -> bool:
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def live_environment(model: str, *, lab_model: str, dollar_cap: float, monthly_cap: float | None) -> dict:
    """The launcher environment of the handoff recipe, with the Actor model chosen here."""
    from app.config import Settings
    settings = Settings.from_env()
    if not settings.wandb_entity.strip():
        raise SystemExit("WANDB_ENTITY is blank in .env; the evidence pipeline needs it")
    env = dict(os.environ)
    env.update({
        "FAULTLAB_READ_ONLY": "false", "FAULTLAB_LIVE_ENABLED": "true", "FAULTLAB_ARIA_PUBLISH_ENABLED": "false",
        "FAULTLAB_CONFIRMED_ENTITY": settings.wandb_entity, "FAULTLAB_CONTROL_TOKEN": "",
        "WANDB_MODEL": model, "FAULTLAB_ACTOR_MODEL": "",
        "WANDB_EXPLORER_MODEL": lab_model, "WANDB_MECHANIC_MODEL": lab_model,
        "FAULTLAB_LAB_MODEL": "", "FAULTLAB_ACTOR_CONTEXT_PROTOCOL": "faultlab-actor-context/v4-indexed-evidence",
        "FAULTLAB_MODEL_CALL_CAP": "6000", "FAULTLAB_TOKEN_CAP": "204000000", "FAULTLAB_DOLLAR_CAP": str(dollar_cap),
        "WANDB_ERROR_REPORTING": "false",
    })
    # Prices come from the verified table (backend/app/providers/pricing.json), not from explicit rate settings.
    for name in ("FAULTLAB_PRICING_MODEL", "FAULTLAB_PRICING_VERIFIED", "FAULTLAB_INPUT_DOLLARS_PER_MILLION",
                 "FAULTLAB_OUTPUT_DOLLARS_PER_MILLION", "FAULTLAB_REASONING_PRICING_MODEL", "FAULTLAB_REASONING_PRICING_VERIFIED",
                 "FAULTLAB_REASONING_INPUT_DOLLARS_PER_MILLION", "FAULTLAB_REASONING_OUTPUT_DOLLARS_PER_MILLION"):
        env.pop(name, None)
    if monthly_cap is not None:
        env["FAULTLAB_MONTHLY_DOLLAR_CAP"] = str(monthly_cap)
    return env


def wait_for(client: httpx.Client, path: str, *, timeout: float, run_dir: Path):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            response = client.get(path)
            if response.status_code == 200:
                return response.json()
            last = f"HTTP {response.status_code}"
        except httpx.HTTPError as error:
            last = type(error).__name__
        time.sleep(1.0)
    raise SystemExit(f"{path} did not answer within {timeout:.0f}s (last: {last}); see {run_dir / 'launcher.log'}")


def api(client: httpx.Client, method: str, path: str, body=None):
    response = client.request(method, path, json=body)
    if response.status_code >= 400:
        try:
            message = response.json()
        except ValueError:
            message = response.text[:500]
        raise RuntimeError(f"{method} {path} -> HTTP {response.status_code}: {json.dumps(message)[:800]}")
    return response.json()


def outbox_pending(run_dir: Path) -> int | None:
    """Queued telemetry uploads not yet sent (read-only look at the store); None when unreadable."""
    import sqlite3
    try:
        with sqlite3.connect(f"file:{run_dir / 'lab.sqlite3'}?mode=ro", uri=True) as db:
            row = db.execute("SELECT COUNT(*) FROM records WHERE kind='telemetry_outbox' "
                             "AND json_extract(payload,'$.state') IN ('PENDING','UPLOADING')").fetchone()
            return int(row[0])
    except sqlite3.Error:
        return None


def settle_outbox(run_dir: Path, seconds: float) -> None:
    """Give the services time to send queued traces; stop early once nothing is pending or nothing moves."""
    deadline = time.monotonic() + seconds
    last, stalled = None, 0
    while time.monotonic() < deadline:
        pending = outbox_pending(run_dir)
        if pending == 0:
            log(run_dir, "telemetry outbox drained")
            return
        stalled = stalled + 1 if pending == last else 0
        last = pending
        if stalled >= 6:
            log(run_dir, f"telemetry outbox not moving ({pending} pending); not waiting longer")
            return
        time.sleep(5)
    log(run_dir, f"telemetry outbox still has {last} pending after {seconds:.0f}s")


def summarize(record: dict) -> dict:
    live = [trial for trial in record.get("trials", []) if trial.get("arm") == "B0"]
    by_case: dict[str, list] = {}
    slot_case = {slot["episode_id"]: slot["case_id"] for slot in record.get("slots", [])}
    for trial in live:
        case = slot_case.get(trial["episode_id"], "?")
        by_case.setdefault(case, []).append({"outcome": trial.get("outcome"), "lifecycle": trial.get("lifecycle"),
                                            "failed_checks": trial.get("failed_checks", []),
                                            "fault_scheduled": trial.get("fault_scheduled"), "fault_triggered": trial.get("fault_triggered")})
    outcomes: dict[str, int] = {}
    for trial in live:
        key = str(trial.get("outcome") or trial.get("lifecycle"))
        outcomes[key] = outcomes.get(key, 0) + 1
    return {"status": record.get("status"), "reason": record.get("reason"), "live_trials": len(live),
            "live_outcomes": outcomes, "by_case": by_case, "usage": record.get("usage"),
            "charged_model_calls": record.get("charged_model_calls"), "charged_token_upper_bound": record.get("charged_token_upper_bound"),
            "evidence": record.get("evidence"), "telemetry": record.get("telemetry")}


def live_trials(record: dict) -> list:
    """The live-arm trials of a baseline record, or every executed slot of a completion record."""
    if record.get("trials") is not None:
        return [t for t in record.get("trials", []) if t.get("arm") == "B0"]
    return [slot for slot in record.get("slots", []) if slot.get("status") not in (None, "QUEUED", "RUNNING")]


def lab_error_streak(trials: list) -> int:
    streak = 0
    for t in reversed(trials):
        if t.get("lifecycle") == "LAB_ERROR" or t.get("outcome") == "LAB_ERROR":
            streak += 1
        else:
            break
    return streak


def queue_and_watch(client, campaign_id: str, study: str, *, run_dir: Path, max_minutes: float, max_lab_error_streak: int,
                    sleep=time.sleep, clock=time.monotonic, evidence_protocol: str | None = None) -> tuple[dict, str | None]:
    """Queue one study on the campaign and watch it to a terminal status under the declared stop rules.

    Returns the final record and the stop rule that fired (None when the study ended on its own).
    """
    spec = STUDIES[study]
    body = {"execute_live": True}
    if study == "completion" and evidence_protocol:
        body["evidence_protocol"] = evidence_protocol
    record = api(client, "POST", spec["queue"].format(campaign_id=campaign_id), body)
    study_id = record["study_id"]
    log(run_dir, f"{study} study {study_id} queued")
    started = clock()
    last_done, last_stage = -1, None
    stopped_by_rule = None
    status_path = spec["status"].format(study_id=study_id)
    while record.get("status") not in TERMINAL:
        sleep(10)
        record = api(client, "GET", status_path)
        trials = live_trials(record)
        done = len(record.get("trials") or record.get("slots") or [])
        stage = record.get("stage")
        if done != last_done or stage != last_stage:
            summary: dict = {}
            for t in trials:
                key = str(t.get("outcome") or t.get("lifecycle") or t.get("status"))
                summary[key] = summary.get(key, 0) + 1
            total = spec["slots"] or len(record.get("slots") or [])
            log(run_dir, f"stage {stage or '-'} slots done {done}/{total} live {len(trials)}/{spec['live'] or total} {summary} decision {record.get('decision', '-')}")
            last_done, last_stage = done, stage
            if lab_error_streak(trials) >= max_lab_error_streak and stopped_by_rule is None:
                stopped_by_rule = f"{lab_error_streak(trials)} consecutive LAB_ERROR live trials"
        if stopped_by_rule is None and clock() - started > max_minutes * 60:
            stopped_by_rule = f"exceeded {max_minutes:.0f} minutes"
        if stopped_by_rule and record.get("status") not in TERMINAL:
            log(run_dir, f"STOP RULE: {stopped_by_rule}; requesting stop")
            api(client, "POST", f"/api/campaigns/{campaign_id}/stop", {})
            for _ in range(30):
                sleep(5)
                record = api(client, "GET", status_path)
                if record.get("status") in TERMINAL:
                    break
            break
    (run_dir / spec["record"]).write_text(json.dumps(record, indent=2))
    return record, stopped_by_rule


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", required=True, help="canonical Actor model name, e.g. anthropic:claude-haiku-5-5")
    parser.add_argument("--study", choices=tuple(STUDIES), default="baseline",
                        help="baseline (the frozen six-case study) or completion (controls, Mechanic proposals, source gate, validation)")
    parser.add_argument("--evidence-protocol", default=None, help="completion study only: the declared Mechanic evidence presentation")
    parser.add_argument("--data-dir", required=True, type=Path, help="fresh store directory (created if absent)")
    parser.add_argument("--declaration", required=True, type=Path)
    parser.add_argument("--declaration-sha256", required=True)
    parser.add_argument("--lab-model", default=None, help="Explorer/Mechanic model (never called by a baseline study); default: the Actor model")
    parser.add_argument("--dollar-cap", type=float, default=60.0, help="FAULTLAB_DOLLAR_CAP for the campaign: a fresh live campaign reserves 1,064 protected calls plus the study's 144, all at the dearest role bound")
    parser.add_argument("--monthly-cap", type=float, default=None, help="override FAULTLAB_MONTHLY_DOLLAR_CAP for this run")
    parser.add_argument("--max-minutes", type=float, default=None, help="stop rule; default 75 for a baseline study, 240 for a completion study")
    parser.add_argument("--max-lab-error-streak", type=int, default=3)
    parser.add_argument("--settle-seconds", type=float, default=120.0,
                        help="after the study ends, wait up to this long for queued telemetry uploads to drain before stopping")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--simulator-port", type=int, default=8001)
    args = parser.parse_args(argv)

    run_dir = args.data_dir.expanduser().resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    text = args.declaration.expanduser().read_bytes()
    digest = hashlib.sha256(text).hexdigest()
    if digest != args.declaration_sha256:
        raise SystemExit(f"Declaration sha256 mismatch: {digest}")
    (run_dir / "DECLARATION.copy.json").write_bytes(text)
    for port in (args.backend_port, args.simulator_port):
        if not port_free(port):
            raise SystemExit(f"Port {port} is in use; another FaultLab is running")
    power = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True).stdout
    if "AC Power" not in power:
        log(run_dir, "WARNING: not on AC power")
    max_minutes = args.max_minutes if args.max_minutes is not None else (75.0 if args.study == "baseline" else 240.0)
    log(run_dir, f"model={args.model} study={args.study} lab_model={args.lab_model or args.model} data_dir={run_dir} declaration_sha256={digest}")

    env = live_environment(args.model, lab_model=args.lab_model or args.model, dollar_cap=args.dollar_cap, monthly_cap=args.monthly_cap)
    env["FAULTLAB_BACKEND_PORT"] = str(args.backend_port)
    env["FAULTLAB_SIMULATOR_PORT"] = str(args.simulator_port)
    launcher_log = (run_dir / "launcher.log").open("a", encoding="utf-8")
    launcher = subprocess.Popen(["caffeinate", "-dims", str(ROOT / "scripts" / "start-local.sh"), "--live", "--no-frontend",
                                 "--data-dir", str(run_dir)], cwd=ROOT, env=env, stdout=launcher_log, stderr=subprocess.STDOUT,
                                start_new_session=True)
    log(run_dir, f"launcher pid {launcher.pid}")
    result = {"model": args.model, "study": args.study, "lab_model": args.lab_model or args.model, "data_dir": str(run_dir),
              "declaration_sha256": digest}
    client = httpx.Client(base_url=f"http://127.0.0.1:{args.backend_port}", timeout=30.0, trust_env=False)
    try:
        readiness = wait_for(client, "/api/readiness", timeout=180, run_dir=run_dir)
        (run_dir / "readiness.json").write_text(json.dumps(readiness, indent=2))
        if readiness.get("models", {}).get("actor") != args.model:
            raise SystemExit(f"Backend Actor model is {readiness.get('models')} not {args.model}")
        if not readiness.get("live_configuration", {}).get("ready"):
            raise SystemExit(f"Live configuration not ready: {readiness.get('live_configuration')}")
        options = wait_for(client, "/api/run-options", timeout=60, run_dir=run_dir)
        (run_dir / "run-options.json").write_text(json.dumps(options, indent=2))
        result["store_identity"] = options.get("data_store", {}).get("identity")
        campaign = api(client, "POST", "/api/campaigns", {"task_text": TASK_TEXT, "order_id": "order-baseline-study",
                                                           "mode": "baseline", "config_profile_id": "live-v1"})
        campaign_id = campaign["campaign_id"]
        result["campaign_id"] = campaign_id
        log(run_dir, f"campaign {campaign_id} created")
        record, stopped_by_rule = queue_and_watch(client, campaign_id, args.study, run_dir=run_dir, max_minutes=max_minutes,
                                                  max_lab_error_streak=args.max_lab_error_streak, evidence_protocol=args.evidence_protocol)
        result["study_id"] = record.get("study_id")
        result["stopped_by_rule"] = stopped_by_rule
        result["summary"] = summarize(record) if args.study == "baseline" else {
            "status": record.get("status"), "reason": record.get("reason"), "decision": record.get("decision"),
            "stage": record.get("stage"), "slots": len(record.get("slots") or []), "usage": record.get("usage"),
            "charged_model_calls": record.get("charged_model_calls"), "candidates": record.get("candidates")}
        log(run_dir, f"study {record.get('status')}: {record.get('reason')}")
        for path, name in ((f"/api/campaigns/{campaign_id}", "campaign.json"), (f"/api/campaigns/{campaign_id}/budget", "budget.json"),
                           (f"/api/campaigns/{campaign_id}/matrix", "matrix.json")):
            try:
                (run_dir / name).write_text(json.dumps(api(client, "GET", path), indent=2))
            except Exception as error:
                log(run_dir, f"could not save {name}: {error}")
        settle_outbox(run_dir, args.settle_seconds)
        export = subprocess.run([str(ROOT / ".venv" / "bin" / "python"), "-m", "app.cli.client", "export", "--campaign", campaign_id,
                                 "--output", str(run_dir / "export.json")], cwd=ROOT / "backend", env=env, capture_output=True, text=True)
        log(run_dir, f"export exit {export.returncode} {export.stderr.strip()[-300:]}")
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {str(error)[:800]}"
        log(run_dir, f"ERROR {result['error']}")
    finally:
        client.close()
        log(run_dir, "stopping services")
        try:
            os.killpg(launcher.pid, signal.SIGINT)
            launcher.wait(timeout=90)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(launcher.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        launcher_log.close()
        try:
            from app.providers.spend import SpendLedger
            ledger_path = Path(env.get("FAULTLAB_SPEND_LEDGER") or (Path.home() / ".faultlab" / "spend-ledger.sqlite3"))
            if ledger_path.exists():
                summary = SpendLedger(ledger_path).summary()
                result["monthly_ledger"] = {"month": summary.month, "reserved_bound": summary.reserved_bound,
                                            "settled_actual": summary.settled_actual, "calls": summary.calls,
                                            "committed": getattr(summary, "committed", None)}
        except Exception as error:
            result["monthly_ledger"] = f"unavailable: {error}"
        (run_dir / "RESULT.json").write_text(json.dumps(result, indent=2))
        log(run_dir, "result written")
    print(json.dumps(result.get("summary", result), indent=2))
    return 0 if result.get("summary", {}).get("status") == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

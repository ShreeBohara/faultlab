"""``faultlab run``: schedule a batch of a pack's scenarios for one adapter and run it to sealed envelopes.

Offline only: the adapters in the registry today need no provider. Every trial is a plan the
scheduler admits under the batch caps, a world on the kernel in this process, and an envelope in
the trial store. The referee is chosen explicitly (``--referee legacy`` runs the orders pack's
fixed checks through the bridge; ``none`` leaves the task outcome pending).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import asyncio
import json
import sys

from faultlab.adapters import AdapterError, load_adapter
from faultlab.core import Caps
from faultlab.evidence import EnvSpec, RepetitionPolicy
from faultlab.lab.scheduler import run_batch, schedule
from faultlab.lab.store import TrialStore
from faultlab.lab.worker import TrialWorker
from faultlab.packs import PackError, load_pack

PROTOCOL_VERSION = "faultlab/v2"


def build_referee(name: str, pack_id: str):
    if name == "none":
        return None
    if name == "legacy":
        from faultlab.referee.legacy import PACK_ID, LegacyOrdersReferee
        if pack_id != PACK_ID:
            raise ValueError(f"The legacy referee scores {PACK_ID} only")
        return LegacyOrdersReferee()
    raise ValueError(f"Unknown referee {name!r}")


def _backend_on_path() -> None:
    """The owner's settings and providers live in the legacy backend package beside this one."""
    import sys
    backend = Path(__file__).resolve().parents[2] / "backend"
    if str(backend) not in sys.path and (backend / "app").is_dir():
        sys.path.append(str(backend))


def build_adapter(args):
    """The registered adapter; the model Actor needs a model, explicit live authorization and the owner's settings."""
    if args.adapter not in ("model-actor", "claude-agent"):
        if args.model or args.execute_live:
            raise ValueError("--model and --execute-live apply to the model-actor and claude-agent adapters only")
        return load_adapter(args.adapter)
    if not args.model:
        raise ValueError(f"{args.adapter} needs --model (provider:model for model-actor; an API model id for claude-agent)")
    if not args.execute_live:
        raise ValueError(f"{args.adapter} makes live model calls; pass --execute-live to authorize them (declaration and ledger entry first)")
    if args.dollars <= 0:
        raise ValueError("a live run needs a positive --dollars bound per trial and batch")
    _backend_on_path()
    from app.config import Settings
    settings = Settings.from_env()
    if args.adapter == "claude-agent":
        # The Claude Code CLI on the owner's subscription: no API key is used; the bound is the API-equivalent price.
        return load_adapter("claude-agent", model=args.model, cli_path=settings.faultlab_claude_code_bin.strip() or None)
    from app.providers.runtime import RuntimeProvider
    provider = RuntimeProvider(settings, live_authorized=True)
    return load_adapter("model-actor", provider=provider, model=args.model)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="faultlab run", description="Run a pack's scenarios for one adapter to sealed envelopes "
                                                                     "(offline for the reference adapter; paid, explicitly authorized, for the model Actor)")
    parser.add_argument("--store", required=True, help="path of the trial store to write (created if missing)")
    parser.add_argument("--pack", required=True, help="pack id, see `faultlab packs`")
    parser.add_argument("--adapter", required=True, help="adapter id, see `faultlab adapters`")
    parser.add_argument("--scenario", action="append", default=None, help="scenario id (repeatable); default: every scenario of the pack")
    parser.add_argument("--k", type=int, default=1, help="repetitions per scenario (default 1)")
    parser.add_argument("--referee", choices=("legacy", "none"), default="none", help="who scores the task outcome")
    parser.add_argument("--name", default=None, help="batch name (default: pack and adapter)")
    parser.add_argument("--dollars", type=float, default=0.0, help="each trial's dollar bound (offline adapters spend 0)")
    parser.add_argument("--batch-dollars", type=float, default=None,
                        help="the batch's dollar cap; default: the trial bound times the number of trials, so every trial can be admitted")
    parser.add_argument("--model-calls", type=int, default=8, help="model-call cap per trial")
    parser.add_argument("--http-attempts", type=int, default=18, help="HTTP-attempt cap per trial")
    parser.add_argument("--wall-seconds", type=float, default=90.0, help="wall-clock cap per trial")
    parser.add_argument("--worlds", default=None, help="directory for the kernel's world files (default beside the store)")
    parser.add_argument("--bundle", default=None, help="also write the batch's envelopes as a bundle (zip) at this path")
    parser.add_argument("--model", default=None, help="model-actor only: the canonical model to run (provider:model), paid")
    parser.add_argument("--execute-live", action="store_true", help="model-actor only: authorize paid provider calls (needs the owner's .env)")
    args = parser.parse_args(argv)
    try:
        pack = load_pack(args.pack)
        adapter = build_adapter(args)
        if not adapter.supports(pack.pack_id):
            raise ValueError(f"Adapter {adapter.adapter_id} does not drive pack {pack.pack_id}")
        referee = build_referee(args.referee, pack.pack_id)
        scenario_ids = args.scenario or [scenario.scenario_id for scenario in pack.scenarios]
        caps = Caps(model_calls=args.model_calls, http_attempts=args.http_attempts, wall_seconds=args.wall_seconds, dollars=args.dollars)
        plans = [pack.plan(scenario_id, agent=adapter.manifest(), environment=EnvSpec(kind="simulator"), protocol_version=PROTOCOL_VERSION,
                           caps=caps).model_copy(update={"repetition": RepetitionPolicy(k=args.k)}) for scenario_id in scenario_ids]
    except (PackError, AdapterError, ValueError, ImportError) as error:
        print(str(error), file=sys.stderr)
        return 2
    with TrialStore(args.store) as store:
        # The scheduler admits a trial only while measured plus reserved plus the trial's bound fits the batch cap, so a
        # multi-trial batch needs a cap of at least the bound times the trials (2026-10-25: one bound for both ran one trial).
        batch_dollars = args.batch_dollars if args.batch_dollars is not None else args.dollars * len(plans) * args.k
        batch = schedule(store, plans, name=args.name or f"{pack.pack_id} x {adapter.adapter_id}", caps=Caps(dollars=batch_dollars))
        worker = TrialWorker(store=store, referee=referee, database_dir=args.worlds)
        envelopes = asyncio.run(run_batch(store, batch.batch_id, worker, adapter))
        summary = store.summary(batch_id=batch.batch_id)
        if args.bundle and envelopes:
            manifest = store.export_bundle(args.bundle, name=batch.name, batch_id=batch.batch_id)
            summary["bundle"] = {"path": args.bundle, "bundle_id": manifest.bundle_id, "manifest_digest": manifest.manifest_digest}
    summary["batch_id"] = batch.batch_id
    summary["trials"] = [{"attempt_id": e.attempt.attempt_id, "scenario_id": e.plan.scenario_id, "execution": e.outcome.execution,
                          "task": e.outcome.task, "reason": e.attempt.terminal_reason,
                          "violations": [f.property_id for f in e.outcome.findings if f.result == "VIOLATION"],
                          "claims": e.outcome.claims.mismatches, "faults_triggered": e.outcome.exposure.all_required_triggered}
                         for e in envelopes]
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

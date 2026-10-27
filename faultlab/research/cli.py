"""``faultlab study repair``: run the repair study (``faultlab.research.repair_study``) to a record and bundles.

Offline with the reference adapter and a scripted Mechanic (plumbing checks, never repair evidence); paid
and explicitly authorized with the model Actor or the Claude Agent adapter and the Claude Code Mechanic.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from hashlib import sha256
from pathlib import Path
import sys

from faultlab.adapters import AdapterError, load_adapter
from faultlab.core import Caps
from faultlab.lab.cli import _backend_on_path, build_referee
from faultlab.lab.store import TrialStore
from faultlab.packs import PackError, load_pack
from faultlab.research.mechanic import ClaudeCodeMechanic, ScriptedMechanic
from faultlab.research.repair_study import RepairStudy, RepairStudyDesign


def _list(value: str | None, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def build_adapter_factory(args):
    """Adapters per arm: the same adapter id and model, with or without the proposal's policy."""
    if args.adapter not in ("model-actor", "claude-agent"):
        if args.model or args.execute_live:
            raise ValueError("--model and --execute-live apply to the model-actor and claude-agent adapters only")
        def offline(policy):
            if policy is not None:
                raise ValueError(f"adapter {args.adapter} cannot carry a rule policy; the study's L arm needs model-actor or claude-agent")
            return load_adapter(args.adapter)
        return offline
    if not args.model:
        raise ValueError(f"{args.adapter} needs --model")
    if not args.execute_live:
        raise ValueError(f"{args.adapter} makes live model calls; pass --execute-live to authorize them (declaration and ledger entry first)")
    if args.dollars <= 0:
        raise ValueError("a live run needs a positive --dollars bound per trial")
    _backend_on_path()
    from app.config import Settings
    settings = Settings.from_env()
    if args.adapter == "claude-agent":
        cli_path = settings.faultlab_claude_code_bin.strip() or None
        return lambda policy: load_adapter("claude-agent", model=args.model, cli_path=cli_path, rule_policy=policy)
    from app.providers.runtime import RuntimeProvider
    provider = RuntimeProvider(settings, live_authorized=True)
    return lambda policy: load_adapter("model-actor", provider=provider, model=args.model, rule_policy=policy)


def build_mechanic(args):
    if args.mechanic == "none":
        return ScriptedMechanic([])
    if args.mechanic.startswith("scripted:"):
        path = Path(args.mechanic[len("scripted:"):])
        value = json.loads(path.read_text(encoding="utf-8"))
        return ScriptedMechanic(value if isinstance(value, list) else [value])
    if args.mechanic == "claude-agent":
        if not args.mechanic_model:
            raise ValueError("--mechanic claude-agent needs --mechanic-model")
        if not args.execute_live:
            raise ValueError("the Claude Code Mechanic makes live calls; pass --execute-live")
        _backend_on_path()
        from app.config import Settings
        settings = Settings.from_env()
        return ClaudeCodeMechanic(args.mechanic_model, cli_path=settings.faultlab_claude_code_bin.strip() or None, max_turns=args.mechanic_turns)
    raise ValueError(f"Unknown mechanic {args.mechanic!r}: none, scripted:<policies.json> or claude-agent")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="faultlab study repair", description="Run the repair study: controls, Mechanic, candidate, validation")
    parser.add_argument("kind", choices=("repair",), help="the study to run")
    parser.add_argument("--store", required=True, help="path of the trial store to write (created if missing)")
    parser.add_argument("--out", required=True, help="directory for the record (repair-study.json) and the bundles")
    parser.add_argument("--name", default="repair-study")
    parser.add_argument("--adapter", required=True, help="adapter id for the Actor: reference-orders, model-actor or claude-agent")
    parser.add_argument("--model", default=None, help="model-actor: provider:model; claude-agent: an API model id")
    parser.add_argument("--execute-live", action="store_true", help="authorize live model calls (Actor and Mechanic)")
    parser.add_argument("--mechanic", default="none", help="none, scripted:<policies.json>, or claude-agent")
    parser.add_argument("--mechanic-model", default=None, help="claude-agent Mechanic: an API model id")
    parser.add_argument("--mechanic-turns", type=int, default=8)
    parser.add_argument("--mechanic-dollars", type=float, default=0.0, help="bound of one Mechanic proposal (API-equivalent)")
    parser.add_argument("--referee", choices=("legacy", "none"), default="legacy")
    parser.add_argument("--pack", default="orders.upgrade_then_confirm/v1")
    parser.add_argument("--source", default="dev-5")
    parser.add_argument("--healthy", default="dev-1")
    parser.add_argument("--validation", default=None, help="comma-separated scenario ids (default dev-1,dev-2,dev-3,dev-4,dev-6)")
    parser.add_argument("--must-complete", default=None, help="comma-separated scenario ids that must complete under L (default dev-1,dev-6)")
    parser.add_argument("--target", default="notification_label_after_rejection", help="the oracle rule id of the target finding")
    parser.add_argument("--controls", type=int, default=6, help="source controls")
    parser.add_argument("--healthy-controls", type=int, default=3)
    parser.add_argument("--gap", type=int, default=3, help="target findings among valid source controls that open the gate")
    parser.add_argument("--healthy-min-valid", type=int, default=2)
    parser.add_argument("--pairs", type=int, default=3)
    parser.add_argument("--slots", type=int, default=2)
    parser.add_argument("--dollars", type=float, default=0.0, help="each trial's dollar bound")
    parser.add_argument("--study-dollars", type=float, default=None, help="the study's cap: refused before anything runs if the maximum bound exceeds it")
    parser.add_argument("--model-calls", type=int, default=8)
    parser.add_argument("--http-attempts", type=int, default=18)
    parser.add_argument("--wall-seconds", type=float, default=90.0)
    parser.add_argument("--worlds", default=None)
    parser.add_argument("--declaration", default=None, help="a declaration file whose sha256 the record carries")
    parser.add_argument("--note", action="append", default=None)
    args = parser.parse_args(argv)
    try:
        pack = load_pack(args.pack)
        design = RepairStudyDesign(
            pack_id=pack.pack_id, source_scenario=args.source, healthy_scenario=args.healthy,
            validation_scenarios=_list(args.validation, ["dev-1", "dev-2", "dev-3", "dev-4", "dev-6"]),
            must_complete=_list(args.must_complete, ["dev-1", "dev-6"]), target_rule=args.target,
            source_controls=args.controls, healthy_controls=args.healthy_controls, gap_min=args.gap, healthy_min_valid=args.healthy_min_valid,
            pairs=args.pairs, slots=args.slots, mechanic_dollars=args.mechanic_dollars,
            caps=Caps(model_calls=args.model_calls, http_attempts=args.http_attempts, wall_seconds=args.wall_seconds, dollars=args.dollars))
        factory = build_adapter_factory(args)
        mechanic = build_mechanic(args)
        referee = build_referee(args.referee, pack.pack_id)
        declaration = None
        if args.declaration:
            data = Path(args.declaration).read_bytes()
            declaration = {"path": str(args.declaration), "sha256": sha256(data).hexdigest()}
        with TrialStore(args.store) as store:
            study = RepairStudy(store=store, design=design, adapter_factory=factory, mechanic=mechanic, out_dir=args.out, referee=referee,
                                worlds_dir=args.worlds, name=args.name, notes=args.note, study_dollars=args.study_dollars, declaration=declaration)
            record = asyncio.run(study.run())
    except (PackError, AdapterError, ValueError, ImportError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    finally:
        cleanup = getattr(locals().get("mechanic"), "cleanup", None)
        if cleanup is not None:
            cleanup()
    print(json.dumps({"decision": record["decision"], "reason": record["reason"], "readouts": record["readouts"],
                      "record": str(Path(args.out) / "repair-study.json")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

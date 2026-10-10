"""Inspect/export incident data or explicitly run an installed synthetic candidate."""
import argparse
import json
from pathlib import Path
import sys

from app.incident_evidence.models import IntegrityError, ORDERS, PAYMENTS

TASKS = {"orders": ORDERS, "payments": PAYMENTS}
EXIT_CODES = {"PASS": 0, "VIOLATION": 1, "INCOMPLETE": 2}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Task-specific incident evidence, with explicit offline replay")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Read and validate data without running a subject")
    inspect.add_argument("--bundle", type=Path, required=True)
    export = commands.add_parser("export-orders", help="Export one explicitly selected offline development episode")
    export.add_argument("--store", type=Path, required=True)
    export.add_argument("--episode", required=True)
    export.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run", help="Run a named installed synthetic candidate in a fresh world")
    run.add_argument("--task", choices=sorted(TASKS), required=True)
    run.add_argument("--candidate", required=True, help="Explicit installed fixture name, never imported code")
    run.add_argument("--healthy", action="store_true", help="Orders no-fault control")
    run.add_argument("--output", type=Path, required=True)
    replay = commands.add_parser("replay", help="Select a candidate explicitly and run the saved scenario freshly")
    replay.add_argument("--bundle", type=Path, required=True)
    replay.add_argument("--candidate", required=True)
    replay.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            from app.incident_evidence.bundles import inspect_bundle
            result = inspect_bundle(args.bundle)
            envelope = result.envelope
            print(json.dumps({"integrity": "VALID", "execution": "NOT_RUN", "identity": envelope.identity.model_dump(mode="json"),
                              "recorded_assessment": envelope.assessment.model_dump(mode="json"),
                              "evidence_digest": envelope.digest, "managed_provider_calls": 0}, indent=2))
            return 0
        from app.incident_evidence.runner import export_orders, replay_case, run_case
        if args.command == "export-orders":
            result = export_orders(args.store, args.episode, args.output)
        elif args.command == "replay":
            result = replay_case(args.bundle, args.output, candidate=args.candidate)
        else:
            result = run_case(args.output, task=TASKS[args.task], candidate=args.candidate, healthy=args.healthy)
        print(json.dumps(result, indent=2, allow_nan=False))
        return EXIT_CODES[result["status"]]
    except IntegrityError as error:
        print(json.dumps({"status": "INTEGRITY_ERROR", "message": str(error)}), file=sys.stderr)
        return 3
    except (OSError, ValueError, KeyboardInterrupt) as error:
        print(json.dumps({"status": "INCOMPLETE", "error_type": type(error).__name__,
                          "message": "Could not complete the request. Select compatible evidence, an installed candidate and a new output directory."}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

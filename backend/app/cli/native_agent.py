"""User-selected smolagents conformance, with no provider-backed mode."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

EXIT_CODES = {"PASS": 0, "VIOLATION": 1, "INCOMPLETE": 2}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Test a trusted local smolagents constructor with a declared model double")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "healthy"):
        command = commands.add_parser(name)
        command.add_argument("--agent", required=True, type=Path, help="Trusted single Python file exposing build_agent(model, tools)")
        command.add_argument("--output", required=True, type=Path, help="New evidence directory")
        if name == "check":
            command.add_argument("--bundle", required=True, type=Path)
    inspect = commands.add_parser("inspect", help="Validate scenario data without executing a constructor")
    inspect.add_argument("--bundle", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            from app.examples.rejected_upgrade import inspect_example_bundle
            result = inspect_example_bundle(args.bundle)
            print(json.dumps(result, indent=2, allow_nan=False))
            return 0
        from app.native_agents.runner import run_native_agent
        result = asyncio.run(run_native_agent(args.output, args.agent,
            bundle_dir=getattr(args, "bundle", None), healthy=args.command == "healthy"))
        print(json.dumps({key: result[key] for key in (
            "status", "complete", "mode", "agent", "trial_count", "failed_checks", "managed_provider_calls", "paths")},
            indent=2, allow_nan=False))
        return EXIT_CODES[result["status"]]
    except (OSError, ValueError, KeyboardInterrupt) as error:
        print(json.dumps({"status": "INCOMPLETE", "error_type": type(error).__name__,
            "message": "Could not complete the native check. Select a valid constructor, compatible bundle and new writable output directory."}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

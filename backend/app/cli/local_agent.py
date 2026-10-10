"""Explicit local decision-program checks against a portable orders regression."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys



EXIT_CODES = {"PASS": 0, "VIOLATION": 1, "INCOMPLETE": 2}


def _json(value):
    return json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Test explicitly selected trusted local Python decision logic")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "healthy"):
        command = commands.add_parser(name, help="Three fresh fault trials" if name == "check" else "One healthy task control")
        command.add_argument("--agent", required=True, type=Path, help="Trusted single-file Python decide(request) program")
        command.add_argument("--output", required=True, type=Path, help="New directory; existing evidence is never replaced")
        if name == "check":
            command.add_argument("--bundle", required=True, type=Path)
    inspect = commands.add_parser("inspect", help="Validate scenario data without selecting or executing an agent")
    inspect.add_argument("--bundle", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            from app.examples.rejected_upgrade import inspect_example_bundle
            result = inspect_example_bundle(args.bundle)
            print(_json(result))
            return 0
        from app.local_agents.runner import run_local_agent
        result = asyncio.run(run_local_agent(args.output, args.agent,
            bundle_dir=getattr(args, "bundle", None), healthy=args.command == "healthy"))
        print(_json({key: result[key] for key in
                    ("status", "complete", "mode", "agent", "trial_count", "failed_checks", "managed_provider_calls", "paths")}))
        return EXIT_CODES[result["status"]]
    except (OSError, ValueError, KeyboardInterrupt) as error:
        print(_json({"status": "INCOMPLETE", "error_type": type(error).__name__,
            "message": "Could not complete the local check. Select a valid single Python source, compatible bundle and new writable output directory."}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

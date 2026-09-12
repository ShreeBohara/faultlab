"""Opt-in checks. No provider is contacted by app startup, health, or tests."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from app.config import ConfigurationError, Settings
from app.providers import ProviderCheckError
from app.providers.typesafe import configuration_status
from app.providers.wandb_inference import generate_once, list_models


def main(argv: Sequence[str] | None = None, *, env_path: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit FaultLab provider connection checks")
    subparsers = parser.add_subparsers(dest="provider", required=True)
    wandb = subparsers.add_parser("wandb", help="W&B Inference and Weave")
    modes = wandb.add_mutually_exclusive_group(required=True)
    modes.add_argument("--list-models", action="store_true", help="List model IDs; no generation")
    modes.add_argument("--generate", action="store_true", help="Verify WANDB_MODEL and make one short traced request")
    wandb.add_argument("--confirm-entity", help="The credited WANDB_ENTITY confirmed by the user")
    subparsers.add_parser("typesafe", help="Show the sponsor-instructions blocker; no network call")
    args = parser.parse_args(argv)
    settings = Settings.from_env(env_path=env_path)
    if args.provider == "typesafe":
        print(configuration_status(settings))
        return 2
    try:
        settings.require_wandb(require_model=args.generate)
        if not args.confirm_entity or args.confirm_entity != settings.wandb_entity:
            print("Blocked: pass --confirm-entity with the credited WANDB_ENTITY after the user confirms it.", file=sys.stderr)
            return 2
        if args.list_models:
            ids = list_models(settings)
            print("Available model IDs (no generation request):")
            print("\n".join(ids) if ids else "No model IDs were returned.")
            print("Save an exact available ID as WANDB_MODEL in the root .env before --generate.")
        else:
            result = generate_once(settings)
            print(f"Response: {result.response}")
            print(f"Verified Weave trace: {result.trace_url}")
        return 0
    except ConfigurationError as error:
        print(f"Blocked: configure {error} in the root .env.", file=sys.stderr)
        return 2
    except ProviderCheckError as error:
        if error.response is not None:
            print(f"Response: {error.response}")
        print(f"Failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

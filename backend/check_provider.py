"""Opt-in checks. No provider is contacted by app startup, health, or tests.

``check`` (Phase 0.5) exercises any provider through the production request path: the same
request profile, admission, credential check, redaction and monthly spend reservation that a
campaign call gets, for one bounded request. The older ``wandb`` subcommand keeps its traced
Weave generation; ``check`` traces nothing.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from app.config import ConfigurationError, Settings
from app.providers import ProviderCheckError
from app.providers.catalog import PROVIDER_IDS, client_spec, parse_model_ref, provider_secrets
from app.providers.typesafe import configuration_status
from app.providers.wandb_inference import generate_once, list_models

SMOKE_PROMPT = 'Reply with only this JSON object and nothing else: {"status": "FaultLab connection OK"}'
# Test seams: a sync OpenAI-compatible client for listings and the runtime's async client factory.
list_client_factory = None
runtime_client_factory = None


def provider_check(settings: Settings, *, provider: str, model: str, list_only: bool = False,
                   max_output_tokens: int = 32) -> dict:
    """One model listing, or one bounded generation through ``RuntimeProvider``; a JSON-safe report."""
    from app.providers.pricing import PricingTableError, describe
    from app.providers.runtime import RuntimeProvider, RuntimeProviderError
    from app.providers.weave_tracing import quiet_sdk_output
    ref = parse_model_ref(f"{provider}:{model}")
    spec = client_spec(ref, settings)
    if spec.missing:
        raise ConfigurationError(spec.missing)
    secrets = provider_secrets(settings)
    if list_only:
        if list_client_factory is None:
            from openai import OpenAI
            factory = OpenAI
        else:
            factory = list_client_factory
        with quiet_sdk_output():
            try:
                with factory(base_url=spec.base_url, api_key=spec.api_key, timeout=20.0, max_retries=0,
                             **spec.client_kwargs) as client:
                    ids = sorted({item.id for item in client.models.list().data if isinstance(getattr(item, "id", None), str)})
            except Exception:
                raise ProviderCheckError(f"Could not list {provider} models. Check credentials and network; "
                                         "no retries were made.") from None
        if any(secret and secret in model_id for model_id in ids for secret in secrets):
            raise ProviderCheckError("Unexpected model-list response")
        return {"provider": provider, "model": ref.ref, "mode": "list_models", "model_ids": ids, "generation_requests": 0}
    smoke = replace(settings, faultlab_actor_model=ref.ref)
    table = Path(settings.faultlab_pricing_table) if settings.faultlab_pricing_table else None
    try:
        pricing = describe(ref.ref, path=table, allow_stale=settings.faultlab_allow_stale_prices)
    except PricingTableError as error:
        pricing = {"ref": ref.ref, "status": "error", "reason": str(error)}

    async def run():
        async with RuntimeProvider(smoke, live_authorized=True, client_factory=runtime_client_factory) as runtime:
            return await runtime.complete([{"role": "user", "content": SMOKE_PROMPT}], role="actor",
                                          max_output_tokens=max_output_tokens)
    with quiet_sdk_output():
        try:
            generation = asyncio.run(run())
        except RuntimeProviderError as error:
            raise ProviderCheckError(f"{provider} check failed: {json.dumps(error.diagnostics, sort_keys=True)}; "
                                     "no retries were made.") from None
    try:
        json_valid = isinstance(json.loads(generation.content), dict)
    except ValueError:
        json_valid = False
    return {"provider": provider, "model": ref.ref, "model_sent": ref.model_id, "mode": "generate",
            "max_output_tokens": max_output_tokens, "per_call_dollar_bound": smoke.per_call_dollar_bound_for_role("actor"),
            "monthly_dollar_cap": settings.faultlab_monthly_dollar_cap, "pricing": pricing,
            "input_tokens": generation.input_tokens, "output_tokens": generation.output_tokens,
            "cost_usd": generation.cost_usd, "structured_output_enforced": generation.structured_output_enforced,
            "json_valid": json_valid, "response": generation.content[:500], "generation_requests": 1}


def _output_token_limit(value: str) -> int:
    try:
        limit = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer from 1 to 2000") from None
    if not 1 <= limit <= 2000:
        raise argparse.ArgumentTypeError("must be an integer from 1 to 2000")
    return limit


def main(argv: Sequence[str] | None = None, *, env_path: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit FaultLab provider connection checks")
    subparsers = parser.add_subparsers(dest="provider", required=True)
    subparsers.add_parser("preflight", help="Inspect installed SDK compatibility offline; no configuration or network")
    wandb = subparsers.add_parser("wandb", help="W&B Inference and Weave")
    modes = wandb.add_mutually_exclusive_group(required=True)
    modes.add_argument("--list-models", action="store_true", help="List model IDs; no generation")
    modes.add_argument("--generate", action="store_true", help="Verify WANDB_MODEL and make one short traced request")
    wandb.add_argument("--confirm-entity", help="The credited WANDB_ENTITY confirmed by the user")
    wandb.add_argument("--max-output-tokens", type=_output_token_limit, default=32, metavar="1..2000",
                      help="Explicit generation token cap (default: 32); reasoning models may need a larger authorized cap")
    subparsers.add_parser("typesafe", help="Show the sponsor-instructions blocker; no network call")
    check = subparsers.add_parser("check", help="Any provider, through the production request path; no Weave trace")
    check.add_argument("--provider", dest="provider_id", choices=PROVIDER_IDS, required=True)
    check.add_argument("--model", required=True, help="The bare model id on that provider (no provider prefix)")
    check_modes = check.add_mutually_exclusive_group(required=True)
    check_modes.add_argument("--list-models", action="store_true", help="List model IDs; no generation")
    check_modes.add_argument("--generate", action="store_true", help="One bounded JSON smoke request; counts against the monthly cap")
    check.add_argument("--confirm-entity", help="For --provider wandb: the credited WANDB_ENTITY confirmed by the user")
    check.add_argument("--max-output-tokens", type=_output_token_limit, default=32, metavar="1..2000",
                       help="Explicit generation token cap (default: 32)")
    args = parser.parse_args(argv)
    if args.provider == "preflight":
        from app.providers.preflight import compatibility_report
        report = compatibility_report()
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if all(report["compatible"].values()) else 2
    settings = Settings.from_env(env_path=env_path)
    if args.provider == "typesafe":
        print(configuration_status(settings))
        return 2
    if args.provider == "check":
        try:
            if args.provider_id == "wandb" and (not args.confirm_entity or args.confirm_entity != settings.wandb_entity):
                print("Blocked: pass --confirm-entity with the credited WANDB_ENTITY after the user confirms it.", file=sys.stderr)
                return 2
            if args.generate:
                print(f"Generation limit: {args.max_output_tokens} output tokens; 20-second timeout; no generation retries; "
                      f"monthly cap {settings.faultlab_monthly_dollar_cap:.2f} USD.", file=sys.stderr)
            report = provider_check(settings, provider=args.provider_id, model=args.model, list_only=args.list_models,
                                    max_output_tokens=args.max_output_tokens)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        except ConfigurationError as error:
            print(f"Blocked: configure {error} in the root .env.", file=sys.stderr)
            return 2
        except ProviderCheckError as error:
            print(f"Failed: {error}", file=sys.stderr)
            return 1
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
            print(f"Generation limit: {args.max_output_tokens} output tokens; 20-second timeout; no generation retries.")
            result = generate_once(settings, max_output_tokens=args.max_output_tokens)
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

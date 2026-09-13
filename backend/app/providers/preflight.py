"""SDK signature checks only: never load account settings or initialize clients."""

from importlib import import_module, metadata
import inspect


def compatibility_report() -> dict:
    versions = {}
    for name in ("openai", "weave", "wandb", "pydantic"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    checks = {}
    targets = (
        ("inference", "openai", "AsyncOpenAI", ("base_url", "api_key", "project", "timeout", "max_retries")),
        ("weave_read", "weave.trace.weave_client", "WeaveClient.get_call", ("call_id", "columns")),
        ("weave_page", "weave.trace.weave_client", "WeaveClient.get_calls", ("filter", "columns", "limit", "page_size")),
        ("weave_trace", "weave.trace.weave_client", "WeaveClient.create_call", ("op", "inputs", "parent", "attributes")),
        ("evaluation", "weave", "EvaluationLogger.log_prediction", ("inputs", "output")),
        ("run_bridge", "wandb", "init", ("entity", "project", "id", "name", "resume")),
    )
    for name, module_name, attribute, parameters in targets:
        try:
            target = import_module(module_name)
            for part in attribute.split("."):
                target = getattr(target, part)
            checks[name] = all(p in inspect.signature(target).parameters for p in parameters)
        except (ImportError, AttributeError, TypeError, ValueError):
            checks[name] = False
    return {"mode": "offline_preflight", "versions": versions, "compatible": checks,
            "provider_calls": 0, "account_access": "unverified", "aria_access": "unverified",
            "aria_setup": "W&B UI automation; no supported runtime SDK is used"}

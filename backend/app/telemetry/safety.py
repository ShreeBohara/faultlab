"""Fail-closed sanitation, capture gates, and reference validation."""

from datetime import datetime, timezone
import hashlib
import json
import re
from urllib.parse import urlsplit


class TelemetryError(RuntimeError):
    pass


FORBIDDEN_KEYS = {"api_key", "wandb_api_key", "typesafe_api_key", "authorization", "password", "secret",
                  "settings", "client", "context", "world", "db", "database", "private_events",
                  "private_snapshot", "ground_truth", "oracle", "hidden_fixture", "audit_manifest",
                  "promotion_manifest", "control_url", "control_token", "reasoning", "chain_of_thought"}


def public_json(value, *, secrets=(), max_bytes: int = 1_000_000):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    def visit(item):
        if isinstance(item, dict):
            if any(not isinstance(k, str) or k.lower() in FORBIDDEN_KEYS or k.lower().startswith("private_") for k in item):
                raise TelemetryError("Private or non-public payload field rejected.")
            return {k: visit(v) for k, v in item.items()}
        if isinstance(item, (tuple, list)):
            return [visit(v) for v in item]
        if item is None or isinstance(item, (bool, int, float, str)):
            return item
        raise TelemetryError("Only explicit public JSON values may be captured.")
    clean = visit(value)
    try:
        encoded = json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError):
        raise TelemetryError("Invalid public JSON value.") from None
    if len(encoded.encode()) > max_bytes:
        raise TelemetryError("Public payload exceeds capture limit.")
    if any(secret and secret in encoded for secret in secrets):
        raise TelemetryError("Secret-bearing telemetry rejected.")
    return json.loads(encoded)


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def capture_allowed(metadata: dict, *, frozen: bool = False) -> bool:
    """Called before any SDK operation, including logger initialization."""
    if metadata.get("source_mode") != "live":
        return False
    split, purpose, origin = (metadata.get(k) for k in ("split", "experiment_purpose", "origin"))
    if split == "promotion":
        return False
    if split == "final_audit":
        return frozen and origin == "faultlab_evaluation" and purpose in {"final_audit", "portability"}
    if split != "development":
        return False
    if purpose == "discovery":
        return origin == "prototype"
    return origin == "faultlab_evaluation" and purpose in {
        "reproduction", "reduction", "intervention", "source_validation", "challenge", "diagnostic_profile", "selection_comparison"}


def wandb_url(value: str) -> str:
    try:
        url = urlsplit(value)
        if (url.scheme != "https" or url.hostname not in {"wandb.ai", "www.wandb.ai"}
                or url.username or url.password or url.port not in {None, 443} or not url.path.strip("/")):
            raise ValueError()
    except (ValueError, TypeError):
        raise TelemetryError("Expected an observed HTTPS W&B artifact URL.") from None
    return value


def immutable_weave_ref(value: str, project: str) -> str:
    if not isinstance(value, str) or not value.startswith(f"weave:///{project}/object/"):
        raise TelemetryError("Dataset reference belongs to a different project.")
    version = value.rsplit(":", 1)[-1]
    if ":" not in value.rsplit("/", 1)[-1] or not re.fullmatch(r"[A-Za-z0-9_-]{16,}", version) or version == "latest":
        raise TelemetryError("An immutable dataset version is required.")
    return value

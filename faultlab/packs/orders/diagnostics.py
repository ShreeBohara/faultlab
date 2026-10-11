"""The evidence-gap diagnostic fixture of the orders pack (port of ``app/simulator/capabilities.py``).

A separately frozen fixture, never part of learned-policy comparisons: a world whose first
upgrade write is cut off with a 503 after the effect did (or did not) commit, and whose status
path may be declared unavailable, so a diagnosis can tell a contract evidence gap from a policy
gap. The dictionaries below are copied verbatim so their digests stay the legacy ones.
"""

from copy import deepcopy
from typing import Literal

from pydantic import Field, JsonValue

from faultlab.core.canonical import content_hash
from faultlab.core.model import StrictModel
from faultlab.env.kernel.errors import WorldError

AUTHORITY_PATHS = ["original_upgrade_write", "identical_upgrade_replay", "upgrade_status", "order_projection", "prior_delivered_receipts"]
PROBES = ["original_upgrade_write"] + ["upgrade_status", "order_projection", "identical_upgrade_replay"] * 3
NORMALIZATION = {"version": "identity-map/v1", "allowed_fields": ["call_id", "operation_id", "order_id", "intent_hash"],
                 "preserve": ["transport", "status", "receipt", "observed_version", "retry_after_ticks", "error_code", "tick", "probe"]}
FIXTURE = {"version": "evidence-gap-fixture/v1", "incident": "same timeout after commit versus before commit", "horizon": 10,
           "probes": PROBES, "status_replay_projection": "declared unavailable", "prior_receipts": [],
           "notification": "not an authority path for upgrade", "learning_eligible": False}
STANDARD = {"schema": "faultlab/v1", "semantics": "orders.upgrade_then_confirm/v1",
            "status": "authoritative immutable terminal receipt", "replay": "same identity current receipt",
            "projection": "historical versioned object"}
PROFILE_HASHES = {
    "evidence_gap_v1": {"contract_hash": content_hash(STANDARD | {"diagnostic_override": FIXTURE}),
                        "capability_hash": content_hash({"inventory": AUTHORITY_PATHS, "unavailable_through": 10}),
                        "fixture_hash": content_hash(FIXTURE)},
    "available_status_v1": {"contract_hash": content_hash(STANDARD),
                            "capability_hash": content_hash({"inventory": AUTHORITY_PATHS, "status": "available"}),
                            "fixture_hash": content_hash(FIXTURE | {"status_replay_projection": "standard status available after incident"})},
}
INCIDENT_DELAY_SECONDS = 1.5


def diagnostic_profile() -> dict:
    hashes = PROFILE_HASHES["evidence_gap_v1"]
    return {"profile_id": "evidence_gap_v1", **hashes,
            "oracle_hash": content_hash({"check": "committed world differs from uncommitted world at incident and horizon"}),
            "normalization_hash": content_hash(NORMALIZATION), "probe_set": list(dict.fromkeys(PROBES)), "horizon": 10,
            "excluded_from_learning": True}


def normalize_transcript(transcript, identities):
    """Map only known identity values; never drop semantic fields or timings."""
    def walk(value, key=None):
        if isinstance(value, dict):
            return {k: walk(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v, key) for v in value]
        return identities.get(value, value) if isinstance(value, str) and key in NORMALIZATION["allowed_fields"] else value
    return walk(deepcopy(transcript))


def create_diagnostic_world(store, episode_id, intent, profile_id, committed) -> dict:
    if profile_id not in PROFILE_HASHES:
        raise ValueError("unregistered diagnostic profile")
    handle = store.create(episode_id, intent, {"seed": 0, "primitives": []}, "standard-v1")
    with store.transaction(handle["world_id"]) as state:
        state["pack"]["diagnostic"] = {"profile_id": profile_id, "committed_witness": committed, "incident_done": False,
                                       "hashes": PROFILE_HASHES[profile_id]}
    return handle


def before_perform(handler, ctx, state, tool, service, request) -> float:
    """The incident: the first upgrade write is cut off (after committing, or not); then the declared gap."""
    diagnostic = state["pack"].get("diagnostic")
    if not diagnostic:
        return 0.0
    if not diagnostic["incident_done"] and tool == "update_order":
        diagnostic["incident_done"] = True
        if diagnostic["committed_witness"]:
            handler.perform(ctx, state, tool, service, request, [])
        raise WorldError("DIAGNOSTIC_INCIDENT", 503, delay=INCIDENT_DELAY_SECONDS)
    if diagnostic["profile_id"] == "evidence_gap_v1":
        raise WorldError("DIAGNOSTIC_PATH_UNAVAILABLE", 503)
    return 0.0


class DiagnosticWorld(StrictModel):
    episode_id: str = Field(min_length=1, max_length=128)
    intent: dict[str, JsonValue]
    profile_id: Literal["evidence_gap_v1", "available_status_v1"]
    committed: bool


def extend_control(api, store):
    @api.post("/diagnostics/worlds", status_code=201)
    def diagnostic_world(body: DiagnosticWorld):
        return create_diagnostic_world(store, body.episode_id, body.intent, body.profile_id, body.committed)

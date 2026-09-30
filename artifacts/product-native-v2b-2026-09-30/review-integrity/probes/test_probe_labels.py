"""Integrity reviewer's independent probe of native adapter v2.1 labels (offline, $0).

Real smolagents ToolCallingAgent, real in-process simulator (ASGI transport, no socket), scripted model.
Randomised scripts x fault recipes x policies. For every v2 episode it checks, from what was actually SENT to
the model (the request transcripts), not from the adapter's own bookkeeping:

  C1 contiguous: labels first appear in the transcript as obs-1, obs-2, ..., obs-n (no gap, no skip).
  C2 shown-only decode map: at every request, the adapter's decode map (request_labels) is exactly the set of
     labels visible in that request's messages (nothing added, nothing missing).
  C3 stable/true: every labelled row in every request equals the journal row of the evidence ID the label
     decodes to (all fields except evidence_id), and a label never changes its evidence ID across requests.
  C4 no raw evidence ID ever appears in a v2 request.
  C5 decode exact/total: report_submitted.decoded_evidence_ids == [map.get(t, t) for t in cited] with the map of
     the request that produced the answer; cited_tokens_not_decoded == tokens not in that map.
  C6 v1 parity (same script, same deterministic IDs): every non-final v2 request equals the v1 request with each
     real evidence ID replaced by its v2 label (so v2 shows exactly v1's rows, no more and no fewer), and citing
     the k-th shown observation decodes to exactly the ID v1's agent cites at position k.
"""
import itertools
import json
import random
import re

import pytest

from app.adapters.business_tools import WorldClient
from app.contracts.models import EpisodeBudget, FaultSpec
from app.integrations import external_agent_v2
from app.integrations.external_agent import SmolagentsActor
from app.integrations.external_agent_v2 import SmolagentsActorV2

from test_native_adapter_v1_golden import embedded_objects, shown_evidence_ids
from test_native_adapter_v2 import (BLOCK_CONFIRMATION, BLOCK_REPORT, DEFER_AFTER_UPGRADE, NON_BLOCKING_CONFIRMATION,
                                    REAL_ID, episode, events, request_text, transport)

LABEL = re.compile(r"^obs-(\d+)$")
TOOLS = [{"name": "get_order", "arguments": {}},
         {"name": "update_order", "arguments": {"desired_shipping": "express"}},
         {"name": "send_confirmation", "arguments": {}},
         {"name": "get_operation_status", "arguments": {"service": "orders"}},
         {"name": "get_operation_status", "arguments": {"service": "notifications"}}]


def f4(tool, count, occurrence=1):
    service = "notifications" if tool == "send_confirmation" else "orders"
    return FaultSpec.model_validate({"seed": 7, "primitives": [{"kind": "F4", "occurrence": occurrence,
        "parameters": {"failure_count": count}, "target_service": service, "target_tool": tool}]})


RECIPES = {"healthy": None, "send_fc1": f4("send_confirmation", 1), "send_fc2": f4("send_confirmation", 2),
           "send_fc3": f4("send_confirmation", 3), "update_fc2": f4("update_order", 2), "get_fc2": f4("get_order", 2),
           "status_fc2": FaultSpec.model_validate({"seed": 9, "primitives": [{"kind": "F4", "occurrence": 1, "parameters": {"failure_count": 2},
                                                   "target_service": "orders", "target_tool": "get_operation_status"}]}),
           "send_fc2_occ2": f4("send_confirmation", 2, occurrence=2)}
POLICIES = {"none": None, "nonblocking_confirm": NON_BLOCKING_CONFIRMATION, "block_confirm": BLOCK_CONFIRMATION,
            "block_report": BLOCK_REPORT, "defer_after_upgrade": DEFER_AFTER_UPGRADE}
CAPS = {"default": None, "http4": EpisodeBudget(http_attempts=4), "http2": EpisodeBudget(http_attempts=2)}


def with_recipe(monkeypatch, recipe):
    if recipe is None:
        return
    original = WorldClient.create
    async def create(self, episode_id, intent, fault_spec, *args, **kwargs):
        return await original(self, episode_id, intent, recipe, *args, **kwargs)
    monkeypatch.setattr(WorldClient, "create", create)


def capture(monkeypatch):
    """Record, at each request actually handed to the model transport, the adapter's decode map."""
    seen = []
    original = external_agent_v2._FinalTurnProvider.complete
    async def complete(self, messages, **kwargs):
        seen.append({"messages": messages, "request_labels": dict(self._bridge.request_labels),
                     "labels": dict(self._bridge.labels)})
        return await original(self, messages, **kwargs)
    monkeypatch.setattr(external_agent_v2._FinalTurnProvider, "complete", complete)
    return seen


def make_script(seed, *, guesses):
    rng = random.Random(seed)
    plan = [rng.choice(TOOLS) for _ in range(rng.randint(1, 7))]
    picks = rng.random()
    extra = rng.sample(["NEXT", "NEXT2", "obs-0", "OBS-1", "obs-01", "HIDDEN"], k=rng.randint(1, 3)) if guesses else []
    def script(call, messages):
        final = json.loads(messages[-1]["content"]).get("final_report_required")
        if final or call > len(plan):
            shown = shown_evidence_ids(messages)
            # cite by POSITION among the rows shown (same positions for v1 and v2)
            cited = [s for i, s in enumerate(shown) if (i * 7919 + seed) % 3 != 0 or picks > 0.7]
            for token in extra:
                if token == "NEXT": cited.append(f"obs-{len(shown) + 1}")
                elif token == "NEXT2": cited.append(f"obs-{len(shown) + 2}")
                elif token == "HIDDEN": cited.append(f"obs-{max(1, len(shown))}")
                else: cited.append(token)
            return {"name": "final_answer", "arguments": {"answer": {"upgrade_outcome": "UNKNOWN",
                    "notification_outcome": "UNKNOWN", "overall": "SAFE_UNRESOLVED", "evidence_ids": cited,
                    "next_action": {"kind": "ESCALATE"}}}}
        return plan[call - 1]
    return script


def journal_rows(context):
    return {o.evidence_id: o.model_dump(mode="json") for o in context.broker.journal.observations}


def strip(row):
    return {k: v for k, v in row.items() if k != "evidence_id"}


def check_v2(seen, provider, outcome, context, store):
    rows = journal_rows(context)
    facts = {"requests": len(seen), "labels": 0, "report": "report" in outcome, "journal_rows": len(rows),
             "rows_never_shown_by_last_request": len(rows) - (len(seen[-1]["request_labels"]) if seen else 0)}
    assert len(seen) == len(provider.requests)
    history = {}
    for k, request in enumerate(seen):
        messages = request["messages"]
        assert not REAL_ID.search(json.dumps(messages, ensure_ascii=False)), f"C4 raw id in request {k}"
        visible = [t for t in shown_evidence_ids(messages) if LABEL.match(t)]
        # C1: first appearance order is obs-1..obs-n
        assert visible == [f"obs-{n}" for n in range(1, len(visible) + 1)], f"C1 request {k}: {visible}"
        # C2: decode map == labels visible in this request
        assert sorted(request["request_labels"]) == sorted(visible), f"C2 request {k}: {request['request_labels']} vs {visible}"
        # C3: labelled rows equal the journal rows they decode to; labels never move
        for row in embedded_objects(messages):
            if isinstance(row.get("result"), dict) and isinstance(row.get("evidence_id"), str) and LABEL.match(row["evidence_id"]):
                real = request["request_labels"][row["evidence_id"]]
                assert strip(row) == strip(rows[real]), f"C3 content request {k} {row['evidence_id']}"
        for label, real in request["request_labels"].items():
            assert history.setdefault(label, real) == real, f"C3 label {label} moved"
        facts["labels"] = len(visible)
    submitted = events(store, context, "report_submitted")
    if submitted:
        payload = submitted[0]["payload"]
        last = seen[-1]["request_labels"]
        cited = payload["cited_evidence_tokens"]
        assert payload["decoded_evidence_ids"] == [last.get(t, t) for t in cited], "C5 decode"
        assert payload["cited_tokens_not_decoded"] == [t for t in cited if t not in last], "C5 not decoded"
        assert payload["labels_shown_to_agent"] == list(last) and payload["evidence_labels"] == {v: k for k, v in last.items()}
        assert list(last) == [f"obs-{n}" for n in range(1, len(last) + 1)]
        facts["not_decoded"] = len(payload["cited_tokens_not_decoded"])
    return facts


CASES = [(seed, recipe, policy, caps) for seed, (recipe, policy, caps) in
         zip(itertools.count(1), itertools.product(RECIPES, POLICIES, CAPS))]


@pytest.mark.parametrize("seed,recipe,policy,caps", CASES)
def test_v2_labels_against_transcript_and_v1_parity(tmp_path, monkeypatch, seed, recipe, policy, caps):
    with_recipe(monkeypatch, RECIPES[recipe])
    script = make_script(seed, guesses=False)
    v1, v1_outcome, v1_context, _ = episode(tmp_path / "v1", SmolagentsActor, script, name=f"p-{seed}", policy=POLICIES[policy],
                                            caps=CAPS[caps], monkeypatch=monkeypatch)
    seen = capture(monkeypatch)
    v2, v2_outcome, v2_context, store = episode(tmp_path / "v2", SmolagentsActorV2, script, name=f"p-{seed}",
                                                policy=POLICIES[policy], caps=CAPS[caps], monkeypatch=monkeypatch)
    facts = check_v2(seen, v2, v2_outcome, v2_context, store)
    # C6 parity
    assert [o.evidence_id for o in v1_context.broker.journal.observations] == [o.evidence_id for o in v2_context.broker.journal.observations]
    labels = seen[-1]["labels"] if seen else {}
    compared = 0
    for index, (a, b) in enumerate(zip(v1.requests, v2.requests)):
        if transport(b)["final_report_required"] or transport(a)["final_report_required"]:
            continue
        expected = request_text(a)
        for real, label in labels.items():
            expected = expected.replace(real, label)
        assert request_text(b) == expected, f"C6 request {index}"
        compared += 1
    if "report" in v1_outcome and "report" in v2_outcome:
        assert v1_outcome["report"]["evidence_ids"] == v2_outcome["report"]["evidence_ids"], "C6 decoded citations differ from v1"
    print(json.dumps({"case": [seed, recipe, policy, caps], **facts, "v1_v2_requests_compared": compared,
                      "v1": "report" if "report" in v1_outcome else v1_outcome.get("error"),
                      "v2": "report" if "report" in v2_outcome else v2_outcome.get("error")}))


@pytest.mark.parametrize("seed,recipe,policy,caps", CASES)
def test_v2_guesses_are_never_decoded(tmp_path, monkeypatch, seed, recipe, policy, caps):
    with_recipe(monkeypatch, RECIPES[recipe])
    seen = capture(monkeypatch)
    provider, outcome, context, store = episode(tmp_path, SmolagentsActorV2, make_script(seed + 1000, guesses=True), name=f"g-{seed}",
                                                policy=POLICIES[policy], caps=CAPS[caps], monkeypatch=monkeypatch)
    facts = check_v2(seen, provider, outcome, context, store)
    submitted = events(store, context, "report_submitted")
    if submitted:
        payload = submitted[0]["payload"]
        shown = set(seen[-1]["request_labels"])
        for token, decoded in zip(payload["cited_evidence_tokens"], payload["decoded_evidence_ids"]):
            if token not in shown:
                assert decoded == token     # passes through as written
    print(json.dumps({"case": [seed, recipe, policy, caps], **facts}))


# ---------------------------------------------------------------- negative controls (REVIEW_MUTANT=...): the probe must fail
import os as _os


@pytest.fixture(autouse=True)
def _review_mutant(monkeypatch):
    mutant = _os.environ.get("REVIEW_MUTANT")
    bridge = external_agent_v2._BridgeV2
    if mutant == "journal_position_labels":          # the first v2 build's numbering
        def shown(self, row, journal):
            ids = [o.evidence_id for o in self.context.broker.journal.observations]
            if not isinstance(row, dict) or row.get("evidence_id") not in ids:
                return row
            label = self.labels[row["evidence_id"]] = f"obs-{ids.index(row['evidence_id']) + 1}"
            return {**row, "evidence_id": label}
        monkeypatch.setattr(bridge, "_shown", shown)
    elif mutant == "decode_unshown_rows":            # the decode map also holds journal rows never shown
        original = bridge.generate
        async def generate(self, messages, tools):
            ids = [o.evidence_id for o in self.context.broker.journal.observations]
            for evidence_id in ids:
                self.labels.setdefault(evidence_id, f"obs-{len(self.labels) + 1}")
            return await original(self, messages, tools)
        monkeypatch.setattr(bridge, "generate", generate)
    elif mutant == "drop_a_field":                  # a labelled row loses a field the agent should see
        original = bridge._shown
        def shown(self, row, journal):
            out = original(self, row, journal)
            if isinstance(out, dict) and out is not row and "delivered_tick" in out:
                out = {k: v for k, v in out.items() if k != "delivered_tick"}
            return out
        monkeypatch.setattr(bridge, "_shown", shown)
    yield

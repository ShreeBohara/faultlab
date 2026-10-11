"""Every registered task pack conforms to the interface; the orders pack equals the legacy contracts.

The parity checks compute the sha256 of the private checker from its bytes; nothing here reads it.
"""
from hashlib import sha256
import json
from pathlib import Path
from typing import get_args

import pytest

from app.agents.explorer import PUBLIC_INVARIANTS
from app.contracts.models import TaskIntent as LegacyTaskIntent, TaskReport as LegacyTaskReport, Tool as LegacyTool
from app.integrations.registry import HOOKS as LEGACY_HOOKS
from app.referee.manifests import load_manifest
from effectsafe import ToolContract
from faultlab.core import Caps, canonical_json, content_hash, is_digest
from faultlab.env.kernel import WorldError, WorldHandler, WorldStore
from faultlab.evidence import AgentManifest, EnvSpec, FaultSchedule, TrialPlan, plan_hash
from faultlab.evidence.legacy import CHECK_FAMILIES, _placements as legacy_placements
from faultlab.packs import MANIFEST_VERSION, PackError, PropertySet, PropertySpec, Scenario, TaskPack, load_pack, load_packs, pack_ids
from faultlab.packs.orders.pack import PACK as ORDERS
from faultlab import __main__ as cli

ROOT = Path(__file__).resolve().parents[3]
PACKS = load_packs()
AGENT = AgentManifest(adapter_id="adapter-test", model="model-test")
ENV = EnvSpec(kind="simulator")


@pytest.fixture(params=PACKS, ids=pack_ids())
def pack(request):
    return request.param


def test_the_registry_resolves_every_id_to_a_pack_with_that_id():
    assert [p.pack_id for p in PACKS] == pack_ids()
    with pytest.raises(PackError, match="Unknown pack"):
        load_pack("no.such_pack/v1")


def test_manifest_is_declarative_json_with_a_stable_digest(pack):
    manifest = pack.manifest()
    assert manifest["schema_version"] == MANIFEST_VERSION and manifest["pack_id"] == pack.pack_id
    assert json.loads(canonical_json(manifest)) == manifest
    assert json.loads(pack.manifest_json()) == manifest
    assert is_digest(pack.digest()) and pack.digest() == content_hash(manifest) == load_pack(pack.pack_id).digest()
    for tool in manifest["tools"]:
        for key in ("pending_states", "terminal_states", "errors_proving_no_effect", "retry_safe_errors"):
            assert tool[key] == sorted(tool[key])
    assert {s["scenario_id"] for s in manifest["scenarios"]} == {s.scenario_id for s in pack.scenarios}
    assert manifest["properties"]["checker_digest"] == pack.properties.checker_digest
    assert manifest["intent_schema"] == pack.intent_model.model_json_schema()
    assert manifest["report_schema"] == pack.report_model.model_json_schema()


def test_handler_and_pack_agree_on_identity_and_fixtures(pack):
    handler = pack.handler_factory()
    assert isinstance(handler, WorldHandler)
    assert handler.pack_id == pack.pack_id and tuple(handler.fixtures) == pack.fixtures


def test_declarations_are_unique_and_consistent(pack):
    names = [tool.name for tool in pack.tools]
    assert len(set(names)) == len(names) and set(pack.read_tools) | set(pack.write_tools) == set(names)
    assert len(set(pack.hooks)) == len(pack.hooks) and len(set(pack.fixtures)) == len(pack.fixtures)
    assert len(set(pack.properties.ids)) == len(pack.properties.ids)
    assert len({s.scenario_id for s in pack.scenarios}) == len(pack.scenarios)
    for tool in pack.tools:
        if tool.kind == "write" and tool.identity_scope != "none":
            assert tool.status_lookup in pack.read_tools, tool.name
    for scenario in pack.scenarios:
        assert scenario.fixture_id in pack.fixtures
        for primitive in scenario.fault_spec.primitives:
            assert primitive.target_tool in names
        assert len(scenario.schedule().placements) == len(scenario.fault_spec.primitives)
        assert scenario.schedule().seed == scenario.fault_spec.seed
    assert pack.scenario(pack.scenarios[0].scenario_id) is pack.scenarios[0]
    with pytest.raises(PackError, match="no scenario"):
        pack.scenario("missing")


def test_every_scenario_creates_a_world_on_the_kernel(pack, tmp_path):
    store = WorldStore(tmp_path, pack.handler_factory())
    for scenario in pack.scenarios:
        intent = pack.example_intent(scenario.fixture_id)
        assert pack.intent_model.model_validate(intent).model_dump(mode="json") == intent
        handle = store.create(f"episode-{scenario.scenario_id}", intent, scenario.fault_spec.model_dump(mode="json"), scenario.fixture_id)
        state = store.read(handle["world_id"])
        assert state["fixture_id"] == scenario.fixture_id and state["fault_spec"] == scenario.fault_spec.model_dump(mode="json")
        assert len(state["fault_executions"]) == len(scenario.fault_spec.primitives)
    with pytest.raises((ValueError, WorldError)):
        pack.example_intent("no-such-fixture")


def test_plan_fixes_a_scenario_into_a_valid_trial_plan(pack):
    for scenario in pack.scenarios:
        plan = pack.plan(scenario.scenario_id, agent=AGENT, environment=ENV, protocol_version="faultlab/v1", caps=Caps(http_attempts=18))
        assert plan.pack_id == pack.pack_id and plan.pack_digest == pack.digest()
        assert plan.scenario_id == scenario.scenario_id and plan.fixture_id == scenario.fixture_id
        assert plan.schedule == scenario.schedule() and plan.properties_digest == pack.properties.checker_digest
        assert plan.caps == Caps(http_attempts=18) and plan.protocol_version == "faultlab/v1"
        assert TrialPlan.model_validate(plan.model_dump(mode="json")) == plan and is_digest(plan_hash(plan))
    assert pack.plan(pack.scenarios[0].scenario_id, agent=AGENT, environment=ENV, protocol_version="p").caps == Caps()
    with pytest.raises(PackError):
        pack.plan("missing", agent=AGENT, environment=ENV, protocol_version="p")


def test_the_pack_hosts_a_kernel_service(pack, tmp_path):
    from fastapi.testclient import TestClient
    client = TestClient(pack.app(database_dir=tmp_path, control_token="t"))
    assert client.get("/health").json()["pack"] == pack.pack_id
    scenario = pack.scenarios[0]
    response = client.post("/control/worlds", headers={"X-FaultLab-Control": "t"},
                           json={"episode_id": "ep-1", "intent": pack.example_intent(scenario.fixture_id),
                                 "fault_spec": scenario.fault_spec.model_dump(mode="json"), "fixture_id": scenario.fixture_id})
    assert response.status_code == 201, response.text


def test_inconsistent_declarations_are_refused_at_construction():
    properties = PropertySet(checker_path="x.py", checker_digest="0" * 64,
                             properties=[PropertySpec(property_id="P1", title="t", family="false_report", severity="major")])
    read, write = ToolContract(name="get", kind="read"), ToolContract(name="put", kind="write", identity_scope="client_key",
                                                                        mismatch_behavior="conflict", status_lookup="get")
    base = dict(pack_id="p/v1", version="1", description="", handler_factory=WorldHandler, intent_model=TrialPlan,
                report_model=TrialPlan, example_intent=lambda fixture: {}, tools=(read, write), hooks=("h",), fixtures=("f",),
                scenarios=(), properties=properties)
    TaskPack(**base)
    scenario = Scenario(scenario_id="s", label="s", fixture_id="f", expected_class="fault",
                        fault_spec={"seed": 1, "primitives": [{"kind": "F4", "target_tool": "put", "target_service": "svc",
                                                               "occurrence": 1, "parameters": {}}]})
    TaskPack(**base | {"scenarios": (scenario,)})
    with pytest.raises(PackError, match="unknown fixture"):
        TaskPack(**base | {"scenarios": (scenario.model_copy(update={"fixture_id": "other"}),)})
    with pytest.raises(PackError, match="undeclared tool"):
        TaskPack(**base | {"scenarios": (scenario,), "tools": (read,)})
    with pytest.raises(PackError, match="status lookup"):
        TaskPack(**base | {"tools": (write,)})
    with pytest.raises(PackError, match="Duplicate hooks"):
        TaskPack(**base | {"hooks": ("h", "h")})
    with pytest.raises(PackError, match="Duplicate tool names"):
        TaskPack(**base | {"tools": (read, read, write)})


def test_the_packs_command_lists_and_prints_manifests(capsys):
    assert cli.main(["packs"]) == 0
    listing = capsys.readouterr().out
    assert ORDERS.pack_id in listing and ORDERS.digest() in listing
    assert cli.main(["packs", ORDERS.pack_id]) == 0
    assert json.loads(capsys.readouterr().out) == ORDERS.manifest()
    assert cli.main(["packs", ORDERS.pack_id, "--digest"]) == 0
    assert capsys.readouterr().out.strip() == ORDERS.digest()
    assert cli.main(["packs", "nope/v0"]) == 2


# Orders parity: the declaration equals what the legacy lab recorded, field for field.

def test_orders_scenarios_equal_the_public_development_manifest():
    manifest = load_manifest("development")
    assert manifest["scope"] == ORDERS.pack_id and manifest["partition"] == "development"
    declared = [(s.scenario_id, s.label, s.fixture_id, s.fault_spec.model_dump(mode="json"), s.expected_class) for s in ORDERS.scenarios]
    legacy = [(c["case_id"], c["name"], c["fixture_id"], c["fault_spec"], c["expected_class"]) for c in manifest["cases"]]
    assert declared == legacy
    for scenario, case in zip(ORDERS.scenarios, manifest["cases"]):
        assert ORDERS.example_intent(scenario.fixture_id)["expected_version"] == case["expected_version"]
        placements, seed = legacy_placements(case["fault_spec"])
        assert scenario.schedule() == FaultSchedule(placements=placements, seed=seed)


def test_orders_hooks_tools_and_models_equal_the_legacy_contracts():
    assert ORDERS.hooks == tuple(LEGACY_HOOKS)
    assert {tool.name for tool in ORDERS.tools} == set(get_args(LegacyTool))
    assert ORDERS.report_model.model_json_schema() == LegacyTaskReport.model_json_schema()
    assert ORDERS.intent_model.model_json_schema() == LegacyTaskIntent.model_json_schema()
    assert ORDERS.read_tools == ("get_order", "get_operation_status") and ORDERS.write_tools == ("update_order", "send_confirmation")
    for name in ORDERS.write_tools:
        assert ORDERS.tool(name).resend_is_identity_safe and ORDERS.tool(name).status_lookup == "get_operation_status"
    assert ORDERS.tool("update_order").commit_boundary == "async" and ORDERS.tool("send_confirmation").commit_boundary == "on_ack"


def test_orders_properties_are_the_public_invariants_pinned_to_the_checker_bytes():
    checker = ROOT / ORDERS.properties.checker_path
    assert ORDERS.properties.checker_digest == sha256(checker.read_bytes()).hexdigest()
    assert {p.property_id: p.title for p in ORDERS.properties.properties} == PUBLIC_INVARIANTS
    assert {p.property_id: (p.family, p.severity) for p in ORDERS.properties.properties} == CHECK_FAMILIES
    assert ORDERS.properties.ids == [f"C{n}" for n in range(1, 9)]

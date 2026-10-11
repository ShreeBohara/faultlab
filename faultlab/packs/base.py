"""The task-pack interface (plan phase 1.3): what one workflow declares to run on the kernel.

A ``TaskPack`` is a declaration, not a runner. It names the world handler that gives the kernel its
business semantics, the effectsafe contract of every tool an agent may call, the recovery hooks,
the fixtures, the scenarios (a fixture plus a fault schedule plus the class of outcome the
scenario is meant to produce) and the fixed-code properties the referee scores, pinned to the
digest of their checker file. ``manifest()`` turns the declaration into plain JSON, ``digest()``
identifies it, and ``plan()`` fixes one scenario into a ``TrialPlan`` before admission.

The properties digest is pinned as a constant computed from the checker's bytes; nothing here
opens that file. No I/O happens at import time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Callable, Literal

from pydantic import Field, JsonValue, StringConstraints

from effectsafe import ToolContract
from faultlab.core import Caps, Digest, Id, StrictModel, canonical_json, content_hash
from faultlab.env.kernel import FaultSpec, WorldHandler
from faultlab.evidence import AgentManifest, EnvSpec, FaultSchedule, TrialPlan
# The placement mapping of the legacy projection, reused unchanged so a scenario's schedule and a
# projected episode's schedule spell the same fault the same way. ``legacy.py`` stays byte for byte
# as it is (its sha256 is the mapping digest every projected envelope records).
from faultlab.evidence.legacy import _placements as legacy_placements

MANIFEST_VERSION = "faultlab-task-pack-manifest/v1"
Name = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Label = Annotated[str, StringConstraints(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")]
Text = Annotated[str, StringConstraints(max_length=2000)]
Severity = Literal["critical", "major", "minor"]
PropertyFamily = Literal["unauthorized_or_duplicate_effect", "false_success_claim", "premature_confirmation",
                         "confirmation_count", "false_report", "fabricated_citation", "false_failure_claim",
                         "disallowed_action", "unknown_property"]
# Set-valued contract fields are serialized sorted so a manifest's digest is stable.
_CONTRACT_SETS = ("pending_states", "terminal_states", "errors_proving_no_effect", "retry_safe_errors")


class PackError(ValueError):
    """A pack declaration that does not add up (raised at construction, never at run time)."""


class Scenario(StrictModel):
    scenario_id: Id
    label: Label
    description: Text = ""
    fixture_id: Name
    fault_spec: FaultSpec                # the kernel's own form: what ``POST /control/worlds`` accepts
    expected_class: Label                # what the scenario is meant to produce, e.g. completed, fault, rejected

    def schedule(self) -> FaultSchedule:
        """The v2 schedule derived from the kernel-form spec, with the legacy projection's placement ids."""
        placements, seed = legacy_placements(self.fault_spec.model_dump(mode="json"))
        return FaultSchedule(placements=placements, seed=seed)


class PropertySpec(StrictModel):
    property_id: Id
    title: Annotated[str, StringConstraints(min_length=1, max_length=600)]
    family: PropertyFamily
    severity: Severity


class PropertySet(StrictModel):
    properties: list[PropertySpec] = Field(min_length=1, max_length=64)
    checker_path: Name                   # repository-relative path of the fixed-code checker
    checker_digest: Digest               # sha256 of that file's bytes, pinned by the pack

    @property
    def ids(self) -> list[str]:
        return [item.property_id for item in self.properties]


def contract_json(contract: ToolContract) -> dict:
    """A tool contract as declarative JSON with deterministic ordering of its set-valued fields."""
    value = contract.model_dump(mode="json")
    for key in _CONTRACT_SETS:
        value[key] = sorted(value[key])
    return value


@dataclass(frozen=True)
class TaskPack:
    pack_id: str
    version: str
    description: str
    handler_factory: Callable[[], WorldHandler]
    intent_model: type[StrictModel]
    report_model: type[StrictModel]
    # (fixture id, namespace) -> an intent the handler accepts for that fixture, with every identity
    # (task, operations, keys) derived from the namespace so two trials never share one.
    allocate_intent: Callable[[str, str], dict]
    tools: tuple[ToolContract, ...]
    hooks: tuple[str, ...]
    fixtures: tuple[str, ...]
    scenarios: tuple[Scenario, ...]
    properties: PropertySet
    business_router: Callable[..., Any] | None = None   # (store, limits) -> APIRouter, as the kernel app expects
    # (tool, request) -> the kernel service the call is dispatched on; defaults to the pack id.
    service_of: Callable[[str, dict], str] | None = None
    diagnostics: dict[str, JsonValue] | None = None
    _by_tool: dict[str, ToolContract] = field(init=False, repr=False, compare=False)
    _by_scenario: dict[str, Scenario] = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        object.__setattr__(self, "_by_tool", {tool.name: tool for tool in self.tools})
        object.__setattr__(self, "_by_scenario", {scenario.scenario_id: scenario for scenario in self.scenarios})
        self._check()

    def _check(self):
        if not self.pack_id or not self.version:
            raise PackError("A pack needs a pack_id and a version")
        for what, values in (("tool names", [tool.name for tool in self.tools]), ("hooks", self.hooks),
                             ("fixtures", self.fixtures), ("scenario ids", [s.scenario_id for s in self.scenarios]),
                             ("property ids", self.properties.ids)):
            if len(set(values)) != len(values):
                raise PackError(f"Duplicate {what} in pack {self.pack_id}")
        if not self.tools:
            raise PackError(f"Pack {self.pack_id} declares no tools")
        reads = {tool.name for tool in self.tools if tool.kind == "read"}
        for tool in self.tools:
            if tool.kind == "write" and tool.identity_scope != "none" and tool.status_lookup not in reads:
                raise PackError(f"Keyed write {tool.name} must name a declared read tool as its status lookup")
        for scenario in self.scenarios:
            if scenario.fixture_id not in self.fixtures:
                raise PackError(f"Scenario {scenario.scenario_id} names unknown fixture {scenario.fixture_id}")
            for primitive in scenario.fault_spec.primitives:
                if primitive.target_tool not in self._by_tool:
                    raise PackError(f"Scenario {scenario.scenario_id} places a fault on undeclared tool {primitive.target_tool}")

    def tool(self, name: str) -> ToolContract:
        try:
            return self._by_tool[name]
        except KeyError:
            raise PackError(f"Pack {self.pack_id} declares no tool {name}") from None

    def example_intent(self, fixture_id: str) -> dict:
        return self.allocate_intent(fixture_id, "example")

    def service(self, tool: str, request: dict) -> str:
        return self.service_of(tool, request) if self.service_of is not None else self.pack_id

    def scenario(self, scenario_id: str) -> Scenario:
        try:
            return self._by_scenario[scenario_id]
        except KeyError:
            raise PackError(f"Pack {self.pack_id} has no scenario {scenario_id}") from None

    @property
    def read_tools(self) -> tuple[str, ...]:
        return tuple(tool.name for tool in self.tools if tool.kind == "read")

    @property
    def write_tools(self) -> tuple[str, ...]:
        return tuple(tool.name for tool in self.tools if tool.kind == "write")

    def manifest(self) -> dict:
        """The whole declaration as plain JSON: everything a plan, an adapter or a reviewer needs."""
        return {
            "schema_version": MANIFEST_VERSION,
            "pack_id": self.pack_id,
            "version": self.version,
            "description": self.description,
            "fixtures": list(self.fixtures),
            "tools": [contract_json(tool) for tool in self.tools],
            "hooks": list(self.hooks),
            "scenarios": [{**scenario.model_dump(mode="json"), "schedule": scenario.schedule().model_dump(mode="json")}
                          for scenario in self.scenarios],
            "properties": self.properties.model_dump(mode="json"),
            "intent_schema": self.intent_model.model_json_schema(),
            "report_schema": self.report_model.model_json_schema(),
            "diagnostics": self.diagnostics,
        }

    def digest(self) -> str:
        return content_hash(self.manifest())

    def manifest_json(self) -> str:
        return canonical_json(self.manifest())

    def plan(self, scenario_id: str, *, agent: AgentManifest, environment: EnvSpec, protocol_version: str,
             caps: Caps | None = None) -> TrialPlan:
        """Fix one scenario of this pack into a plan; the pack and properties digests travel with it."""
        scenario = self.scenario(scenario_id)
        return TrialPlan(pack_id=self.pack_id, pack_digest=self.digest(), scenario_id=scenario.scenario_id,
                         fixture_id=scenario.fixture_id, agent=agent, environment=environment, schedule=scenario.schedule(),
                         properties_digest=self.properties.checker_digest, protocol_version=protocol_version,
                         caps=caps if caps is not None else Caps())

    def app(self, *, database_dir, control_token: str, limits=None):
        """A kernel service hosting this pack (the handler plus its business routes)."""
        from faultlab.env.kernel import create_app
        return create_app(handler=self.handler_factory(), database_dir=database_dir, control_token=control_token,
                          limits=limits, business_router=self.business_router)


__all__ = ["MANIFEST_VERSION", "PackError", "PropertySet", "PropertySpec", "Scenario", "TaskPack", "contract_json"]

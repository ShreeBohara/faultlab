"""The pytest plugin (plan phase 1.7, first cut): run a pack's scenarios inside a test suite.

Load it with ``pytest_plugins = ["faultlab.testing.plugin"]`` (or ``-p faultlab.testing.plugin``).
The ``faultlab_lab`` fixture gives a ``Lab`` bound to the test's temporary directory; ``Lab.run``
schedules and runs a batch exactly as ``faultlab run`` does and returns a ``RunResult`` whose
``assert_clean()`` fails the test with every violated property, false claim, unfired fault and
non-completed execution listed per trial. Offline only; nothing here calls a provider.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from faultlab.adapters import load_adapter
from faultlab.core import Caps
from faultlab.evidence import EnvSpec, RepetitionPolicy, TrialEnvelope
from faultlab.lab.scheduler import run_batch, schedule
from faultlab.lab.store import TrialStore
from faultlab.lab.worker import TrialWorker
from faultlab.packs import load_pack

PROTOCOL_VERSION = "faultlab/v2"
DEFAULT_CAPS = Caps(model_calls=8, http_attempts=18, ticks=20, wall_seconds=90.0, dollars=0.0)


@dataclass
class RunResult:
    batch_id: str
    store_path: str
    envelopes: list[TrialEnvelope]
    summary: dict

    def by_scenario(self) -> dict[str, list[TrialEnvelope]]:
        groups: dict[str, list[TrialEnvelope]] = {}
        for envelope in self.envelopes:
            groups.setdefault(envelope.plan.scenario_id, []).append(envelope)
        return groups

    def problems(self, *, require_completed: bool = True, require_faults_fired: bool = True) -> list[str]:
        """Everything a clean run must not show, one line per finding, in trial order."""
        lines = []
        for envelope in self.envelopes:
            tag = f"{envelope.plan.scenario_id} ({envelope.attempt.attempt_id})"
            outcome = envelope.outcome
            if require_completed and outcome.execution != "COMPLETED":
                lines.append(f"{tag}: execution {outcome.execution} ({envelope.attempt.terminal_reason or 'no reason'})")
            if outcome.task == "VIOLATION":
                lines.append(f"{tag}: task outcome VIOLATION")
            for finding in outcome.findings:
                if finding.result == "VIOLATION":
                    lines.append(f"{tag}: property {finding.property_id} violated ({finding.note or finding.family})")
            for mismatch in outcome.claims.mismatches:
                lines.append(f"{tag}: claim mismatch {mismatch}")
            if require_faults_fired and outcome.exposure.required_fault_ids and outcome.exposure.all_required_triggered is not True:
                unfired = [f.fault_id for f in outcome.exposure.faults if f.configured and f.triggered is not True]
                lines.append(f"{tag}: scheduled fault(s) did not fire: {', '.join(unfired)}")
        return lines

    def assert_clean(self, **requirements) -> None:
        problems = self.problems(**requirements)
        if problems:
            raise AssertionError("FaultLab found problems:\n  " + "\n  ".join(problems))

    def assert_outcomes(self, expected: dict[str, str]) -> None:
        """Every trial of each named scenario ended with the task outcome given."""
        actual = {scenario: sorted({str(e.outcome.task) for e in group}) for scenario, group in self.by_scenario().items()}
        wrong = {scenario: actual.get(scenario) for scenario, outcome in expected.items() if actual.get(scenario) != [outcome]}
        if wrong:
            raise AssertionError(f"Task outcomes differ from the expected ones: {wrong}")


@dataclass
class Lab:
    root: Path
    referee: object | str | None = "legacy"
    runs: list[RunResult] = field(default_factory=list)

    def run(self, pack_id: str, adapter, *, scenarios: list[str] | None = None, k: int = 1, caps: Caps | None = None,
            referee=None, name: str | None = None) -> RunResult:
        pack = load_pack(pack_id)
        adapter = load_adapter(adapter) if isinstance(adapter, str) else adapter
        chosen = self.referee if referee is None else referee
        if chosen == "legacy":
            from faultlab.referee.legacy import LegacyOrdersReferee
            chosen = LegacyOrdersReferee() if pack_id == "orders.upgrade_then_confirm/v1" else None
        elif chosen == "none":
            chosen = None
        caps = caps or DEFAULT_CAPS
        manifest = adapter.manifest() if hasattr(adapter, "manifest") else None
        if manifest is None:
            from faultlab.evidence import AgentManifest
            manifest = AgentManifest(adapter_id=adapter.adapter_id, model=getattr(adapter, "model", "unknown"))
        plans = [pack.plan(scenario_id, agent=manifest, environment=EnvSpec(kind="simulator"), protocol_version=PROTOCOL_VERSION, caps=caps)
                 .model_copy(update={"repetition": RepetitionPolicy(k=k)})
                 for scenario_id in (scenarios or [s.scenario_id for s in pack.scenarios])]
        store_path = self.root / f"trials-{len(self.runs) + 1}.sqlite3"
        with TrialStore(store_path) as store:
            batch = schedule(store, plans, name=name or f"{pack_id} x {adapter.adapter_id}", caps=Caps(dollars=caps.dollars))
            worker = TrialWorker(store=store, referee=chosen, database_dir=self.root / "worlds")
            envelopes = asyncio.run(run_batch(store, batch.batch_id, worker, adapter))
            summary = store.summary(batch_id=batch.batch_id)
        result = RunResult(batch_id=batch.batch_id, store_path=str(store_path), envelopes=envelopes, summary=summary)
        self.runs.append(result)
        return result


@pytest.fixture
def faultlab_lab(tmp_path) -> Lab:
    """A lab bound to this test's temporary directory; every run leaves its trial store there."""
    return Lab(root=tmp_path / "faultlab")


__all__ = ["DEFAULT_CAPS", "Lab", "RunResult", "faultlab_lab"]

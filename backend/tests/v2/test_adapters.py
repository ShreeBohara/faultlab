"""Adapters (phase 1.6): the registry, the deterministic reference adapter on the v2 session, the run command."""
import asyncio
import json

import pytest

from faultlab import __main__ as cli
from faultlab.adapters import AdapterError, BaseAdapter, adapter_ids, load_adapter, load_adapters
from faultlab.adapters.reference import ReferenceOrdersAdapter, outcome_label
from faultlab.core import Caps, is_digest
from faultlab.evidence import EnvSpec, TrialAttempt, plan_hash
from faultlab.lab import TrialStore, TrialWorker
from faultlab.packs import load_pack
from faultlab.referee.legacy import LegacyOrdersReferee
from effectsafe import OperationState

ORDERS = load_pack("orders.upgrade_then_confirm/v1")
CAPS = Caps(model_calls=8, http_attempts=18, ticks=20, wall_seconds=30, dollars=0.0)


def run(coro):
    return asyncio.run(coro)


def test_the_registry_resolves_reviewed_adapters_with_identities():
    adapters = load_adapters()
    assert [a.adapter_id for a in adapters] == adapter_ids() == ["reference-orders"]
    reference = load_adapter("reference-orders")
    assert isinstance(reference, BaseAdapter) and is_digest(reference.digest) and reference.digest == ReferenceOrdersAdapter().digest
    manifest = reference.manifest()
    assert manifest.adapter_id == "reference-orders" and manifest.version == "1" and manifest.model == "deterministic/none"
    assert reference.supports(ORDERS.pack_id) and not reference.supports("other/v1")
    with pytest.raises(AdapterError, match="Unknown adapter"):
        load_adapter("nope")


def test_outcome_labels_follow_the_report_contract():
    assert outcome_label(OperationState()) == "NOT_STARTED"
    assert outcome_label(OperationState(attempts=2, outcome="NOT_STARTED")) == "UNKNOWN"     # attempted, refused before any effect
    assert outcome_label(OperationState(attempts=1, outcome="UNKNOWN")) == "UNKNOWN"
    for word in ("PENDING", "SUCCEEDED", "FAILED"):
        assert outcome_label(OperationState(attempts=1, outcome=word)) == word
    assert outcome_label(OperationState(attempts=2, outcome="CONFLICT")) == "UNKNOWN"


def test_the_reference_adapter_passes_every_check_on_every_development_scenario(tmp_path):
    adapter = ReferenceOrdersAdapter()
    expected = {"dev-1": "COMPLETED", "dev-2": "COMPLETED", "dev-3": "COMPLETED", "dev-4": "COMPLETED",
                "dev-5": "CORRECTLY_REFUSED", "dev-6": "COMPLETED"}
    with TrialStore(tmp_path / "trials.sqlite3") as store:
        worker = TrialWorker(store=store, worker_id="w", database_dir=tmp_path / "worlds", referee=LegacyOrdersReferee())
        for scenario in ORDERS.scenarios:
            plan = ORDERS.plan(scenario.scenario_id, agent=adapter.manifest(), environment=EnvSpec(kind="simulator"),
                               protocol_version="faultlab/v2", caps=CAPS)
            envelope = run(worker.run(plan, TrialAttempt(attempt_id=f"trial-{scenario.scenario_id}", plan_hash=plan_hash(plan), lifecycle="READY"), adapter))
            assert envelope.outcome.execution == "COMPLETED" and envelope.outcome.task == expected[scenario.scenario_id], scenario.scenario_id
            assert all(f.result == "PASS" for f in envelope.outcome.findings), [(f.property_id, f.note) for f in envelope.outcome.findings]
            assert envelope.outcome.claims.mismatches == [] and envelope.outcome.exposure.all_required_triggered is True
            assert envelope.outcome.identity.adapter_digest == adapter.digest and envelope.outcome.cost.model_calls == 0
            assert envelope.report.original["evidence_ids"] and envelope.report.interpreted is not None
        # The lost reply resends the pinned bytes from the rule hook and the transient refusal is retried to success.
        lost = store.envelope("trial-dev-2")
        assert any(e.kind == "invoked" and e.payload["caller"] == "rule" for e in lost.events) or \
            [c["tool"] for c in lost.source_facts["calls"]].count("update_order") == 1
        transient = store.envelope("trial-dev-6")
        assert transient.report.original["notification_outcome"] == "SUCCEEDED"
        assert [c["tool"] for c in transient.source_facts["calls"]].count("send_confirmation") >= 2


def test_the_run_command_runs_a_batch_offline_and_prints_its_summary(tmp_path, capsys):
    store = tmp_path / "trials.sqlite3"
    code = cli.main(["run", "--store", str(store), "--pack", ORDERS.pack_id, "--adapter", "reference-orders", "--referee", "legacy",
                     "--scenario", "dev-1", "--scenario", "dev-5", "--k", "2", "--worlds", str(tmp_path / "worlds")])
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["attempts"] == {"TERMINAL": 4} and summary["tasks"] == {"COMPLETED": 2, "CORRECTLY_REFUSED": 2}
    assert [t["scenario_id"] for t in summary["trials"]] == ["dev-1", "dev-5", "dev-1", "dev-5"]
    assert all(t["violations"] == [] and t["claims"] == [] and t["execution"] == "COMPLETED" for t in summary["trials"])
    assert cli.main(["store", str(store)]) == 0 and json.loads(capsys.readouterr().out)["spent"]["measured"]["envelopes"] == 4
    assert cli.main(["adapters"]) == 0 and "reference-orders" in capsys.readouterr().out
    assert cli.main(["run", "--store", str(store), "--pack", "nope/v1", "--adapter", "reference-orders"]) == 2
    assert cli.main(["run", "--store", str(store), "--pack", ORDERS.pack_id, "--adapter", "nope"]) == 2
    capsys.readouterr()

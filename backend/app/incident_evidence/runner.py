"""Explicit installed-fixture execution; imported evidence is never executable."""
from __future__ import annotations

import asyncio
from pathlib import Path

from .bundles import export_bundle, export_zip, inspect_bundle, new_output
from .models import ORDERS, PAYMENTS, IntegrityError, canonical, digest
from .validation import validate_evidence


def orders_scenario(healthy=False):
    from app.contracts.models import FaultSpec
    from app.examples.rejected_upgrade import rejection_recipe
    recipe = FaultSpec(seed=105, primitives=[]) if healthy else rejection_recipe()
    raw = recipe.model_dump(mode="json")
    return {"recipe": raw, "scenario_digest": digest(raw), "fixture_id": "standard-v1"}


def _candidate_scenario(task, candidate, healthy=False):
    if task == ORDERS:
        if candidate not in ("safe", "unsafe"):
            raise ValueError("Select the installed orders safe or unsafe fixture")
        return orders_scenario(healthy)
    if task == PAYMENTS:
        if healthy:
            raise ValueError("Select the explicit healthy payment candidate")
        from .payments import scenario_for_case
        return scenario_for_case(candidate)
    raise ValueError("Unsupported task")


def _save(envelope, output, parent=None, *, executed=True):
    from .report import write_report
    envelope = validate_evidence(envelope)
    directory = export_bundle(envelope, output / "evidence")
    archive = export_zip(directory, output / "incident.zip")
    summary = {"schema_version": "faultlab-incident-execution/v1", "status": envelope.assessment.status,
               "task_type": envelope.identity.task_type, "trial_id": envelope.identity.trial_id,
               "candidate": envelope.identity.subject_id, "evidence_digest": envelope.digest,
               "failed_checks": envelope.assessment.failed_checks,
               "incomplete_reasons": envelope.assessment.incomplete_reasons,
               "new_subject_execution": executed,
               "managed_provider_calls": 0, "managed_provider_spend_dollars": 0,
               "source_bundle_digest": parent, "paths": {"bundle": str(directory), "zip": str(archive),
                                                          "report": str(output / "report.html")},
               "limitations": ["Offline synthetic evidence; not production-model or customer validation.",
                               "External activity by user-owned native code is unmetered; managed-provider counters do not account for it.",
                               "Inspection and replay do not establish generated repair or ACCEPTED policy."]}
    (output / "summary.json").write_text(canonical(summary) + "\n", encoding="utf-8")
    write_report(envelope, output / "report.html")
    return summary


def run_case(output, *, task, candidate, healthy=False, expected_scenario=None, parent=None):
    scenario = _candidate_scenario(task, candidate, healthy)
    if expected_scenario is not None and scenario != expected_scenario:
        raise ValueError("Selected candidate changes the imported task or fault scenario")
    output = new_output(output)
    if task == ORDERS:
        from app.examples.rejected_upgrade import run_trial
        from .orders import load_orders_facts, project_orders_facts
        result = asyncio.run(run_trial(output / "execution", behavior=candidate, recipe=scenario["recipe"]))
        if len(result["trials"]) != 1:
            raise IntegrityError("The new orders execution did not retain exactly one trial")
        facts = load_orders_facts(result["paths"]["store"], result["trials"][0]["episode_id"])
        envelope = project_orders_facts(facts)
    else:
        from .payments import run_payment_case
        envelope = run_payment_case(output / "execution", candidate)
    if envelope.scenario != scenario:
        raise IntegrityError("Fresh execution changed the admitted scenario")
    return _save(envelope, output, parent)


def replay_case(bundle, output, *, candidate):
    inspected = inspect_bundle(bundle)
    envelope = inspected.envelope
    healthy = False
    if envelope.identity.task_type == ORDERS:
        if envelope.scenario == orders_scenario(True):
            healthy = True
        elif envelope.scenario != orders_scenario(False):
            raise ValueError("Orders replay supports only the installed healthy/rejection scenarios")
        # Preserve the fixed orders service/check semantics across installation changes.
        from app.config import Settings
        from app.contracts.models import CampaignBudget
        from app.lab.configuration import frozen_configuration
        current = frozen_configuration(Settings(), CampaignBudget(), "offline-v1")
        saved = envelope.source_facts["configuration"]
        for field in ("service_hash", "contract_hash", "scorer_hash", "interpreter_hash", "dependency_lock_hash"):
            if saved.get(field) != current[field]:
                raise IntegrityError("Orders replay semantics differ from the saved incident")
    return run_case(output, task=envelope.identity.task_type, candidate=candidate, healthy=healthy,
                    expected_scenario=envelope.scenario, parent=inspected.manifest["manifest_digest"])


def export_orders(store, episode_id, output):
    from .orders import load_orders_facts, project_orders_facts
    envelope = project_orders_facts(load_orders_facts(store, episode_id))
    return _save(envelope, new_output(output), executed=False)

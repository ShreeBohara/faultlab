"""Review check 1B ($0, offline): Rule 1 on a REAL saved Learn plan, then the store, the export, the API and old plans.

A Learn campaign is created through the product's own prepare_run_plan / create (so its saved plan freezes
mechanic_diagnosis). The diagnosis step is then run exactly as learning.py runs it (the rules read from the saved plan, the
wrappers nested in learning.py's order, the real Mechanic and the real Diagnostician, record() before the gate), with a
scripted provider (a v2f-style 743-character first answer, then a fitting repair) and a deterministic trial runner.
Then: the diagnosis_requests record in the store; GET /campaigns/{id}/recording (the export) through the real API app
in-process; the matrix and diagnostic endpoints; the dashboard sources; and a Learn plan saved before the rule.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.agents.mechanic import Mechanic
from app.contracts.models import Counterexample, FaultSpec, TrialResult, Usage, canonical_json, content_hash
from app.lab import citation_status, diagnosis_guide, diagnosis_protocol, loop_limits
from app.lab.diagnosis import Diagnostician
from app.lab.exports import development_recording
from app.lab.operator_actions import register_agent
from app.lab.run_plans import prepare_run_plan, read_run_plan
from app.main import create_app
from app.providers.runtime import RuntimeGeneration
from test_discovery_v2_flow import learn_campaign, owner, request  # noqa: F401  (owner is a fixture)
from test_loop_limits_mechanic_context import bundle

FAULTLAB = Path(__file__).resolve().parents[4]
RECIPE = FaultSpec.model_validate({'seed': 7, 'primitives': [{'kind': 'F2', 'target_tool': 'update_order', 'target_service': 'orders',
                                                              'occurrence': 1, 'parameters': {'completion_delay_ticks': 3,
                                                              'terminal_status': 'SUCCEEDED', 'failure_code': None}}]})
LONG, SHORT = 'x' * 743, 'Removing the delay removes the premature confirmation.'


@pytest.fixture
def anyio_backend(): return 'asyncio'


class Provider:
    def __init__(self, model): self.model = model; self.requests = []
    def role_model(self, role): return self.model
    async def complete(self, messages, **kwargs):
        self.requests.append(json.loads(json.dumps(messages)))
        context = json.loads(messages[1]['content'])
        hypothesis = LONG if len(messages) == 2 else SHORT
        return RuntimeGeneration(canonical_json({'proposed_kind': 'CONTRACT_EVIDENCE_GAP', 'hypothesis': hypothesis,
                                                 'evidence_ids': context['evidence_ids'][:1],
                                                 'requested_intervention_id': context['intervention_ids'][0]}), self.model)


class Runner:
    """Fresh trials: the control recipe violates C3, the treatment (fault removed) is clean."""
    def __init__(self): self.calls = 0
    async def run(self, campaign, spec, policy, *, purpose, trial_index, fixture_id, ledger, reservation, stop):
        self.calls += 1; violation = bool(spec.primitives)
        return TrialResult(episode_id=f'episode-i{self.calls}', world_id=f'world-i{self.calls}', scenario_hash=content_hash(spec),
                           policy_hash=policy.policy_hash, arm='B0', trial_index=trial_index, lifecycle='COMPLETED',
                           outcome='VIOLATION' if violation else 'COMPLETED', failed_checks=['C3'] if violation else [],
                           fault_scheduled=violation, fault_triggered=violation, usage=Usage(actor_calls=3, http_attempts=3))


class Ledger:
    def __init__(self): self.reservations = {}
    def consume_call(self, **kwargs): pass
    def reconcile(self, generation): pass
    def reserve(self, name, calls, tokens=None): self.reservations[name] = calls
    def release(self, name): self.reservations.pop(name, None)


async def diagnose_as_learning_does(owner, campaign):
    """learning.py lines 172-173 and 250-259, with this campaign's saved plan."""
    store = owner.store
    model = owner.get(campaign.campaign_id)
    provider = Provider(owner.settings.model_for_role('mechanic'))
    ledger = Ledger()
    mechanic = Mechanic(provider, store, ledger)
    mechanic.metadata = {'campaign_id': campaign.campaign_id, 'model_id': provider.model}
    diagnosis_rule = diagnosis_protocol.campaign_rule(store, model); mechanic.diagnosis_protocol = diagnosis_rule
    guide_rule = diagnosis_guide.campaign_rule(store, model)
    citation_rule = citation_status.campaign_rule(store, model)
    context_rule = loop_limits.mechanic_context_rule(store, model)
    counter = Counterexample(counterexample_id='counterexample-review', campaign_id=campaign.campaign_id, agent_registration_id='orders-v1',
                             source_episode_id='episode-source', target_invariant='C3', scenario_hash=content_hash(RECIPE),
                             configuration_hash=model.configuration_hash, report_ref='episode-source', verdict_ref='verdict-review',
                             reproduced=True, target_violation_count=3, valid_count=3, attempted_count=3)
    store.put_record('counterexamples', counter.counterexample_id, counter)
    chain = mechanic if context_rule is None else loop_limits.BoundedMechanic(mechanic, store, campaign_id=campaign.campaign_id, counterexample=counter)
    if citation_rule is not None: chain = citation_status.CitationStatusMechanic(chain, store)
    if guide_rule is not None: chain = diagnosis_guide.DiagnosisGuideMechanic(chain, task_text=model.task_text, rule=guide_rule)
    if diagnosis_rule is not None: chain = diagnosis_protocol.RecordingDiagnosisMechanic(chain, mechanic)
    policy = SimpleNamespace(policy_hash=content_hash('policy-review'), version='policy-v0')
    reproduction = [TrialResult(episode_id=f'episode-r{i}', world_id=f'world-r{i}', scenario_hash=content_hash(RECIPE), policy_hash=policy.policy_hash,
                                arm='B0', trial_index=i, lifecycle='COMPLETED', outcome='VIOLATION', failed_checks=['C3'], fault_scheduled=True,
                                fault_triggered=True, usage=Usage(actor_calls=3, http_attempts=3)) for i in range(3)]
    evidence = [bundle(e, ['PENDING', 'FAILED'], failed=('C3',)) for e in ('episode-source', 'episode-r0', 'episode-r1')]
    diagnostic, run = await Diagnostician(store, Runner(), ledger, chain).run(model, counter, RECIPE, policy, reproduction, evidence=evidence)
    record = diagnosis_protocol.record(store, model, counter, diagnostic, run, chain) if diagnosis_rule is not None else None
    return SimpleNamespace(diagnostic=diagnostic, run=run, record=record, provider=provider, rules=(diagnosis_rule, guide_rule, citation_rule, context_rule))


async def api_get(owner, path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=owner)), base_url='http://test') as client:
        response = await client.get(path)
        return response.status_code, response.json()


@pytest.mark.anyio
async def test_a_planned_learn_campaign_records_and_exports_every_attempt(owner):
    campaign = learn_campaign(owner, None, 'reference')
    plan = read_run_plan(owner.store, campaign)['plan']
    assert plan['mechanic_diagnosis'] == diagnosis_protocol.declaration() and 'diagnosis_guide' not in plan
    result = await diagnose_as_learning_does(owner, campaign)
    assert result.rules[0] == diagnosis_protocol.declaration() and result.rules[1] is None
    first, repair = result.provider.requests
    repair_message = json.loads(repair[3]['content'])
    assert repair_message['validation_errors'] == [{'location': ['hypothesis'], 'type': 'string_too_long', 'max_characters': 600,
                                                    'your_characters': 743}]
    assert result.diagnostic.kind == 'POLICY_GAP' and [e.result for e in result.run.experiments] == ['SUPPORTED']
    saved = owner.store.get_record('diagnosis_requests', result.diagnostic.diagnostic_id)
    assert saved == json.loads(canonical_json(result.record))
    assert saved['proposal_status'] == 'VALID_REQUESTED' and saved['recorded_proposed_kind'] == 'CONTRACT_EVIDENCE_GAP'
    assert saved['recorded_proposed_kind_source'] == 'model' and len(saved['attempts']) == 2

    status, recording = await api_get(owner, f'/api/campaigns/{campaign.campaign_id}/recording')
    assert status == 200
    row, = recording['diagnosis_requests']
    assert row['diagnostic_id'] == result.diagnostic.diagnostic_id and row['output_refs'] == saved['output_refs']
    assert [(a['output_ref'], a['attempt']) for a in row['attempt_outputs']] == [(ref, i) for i, ref in enumerate(saved['output_refs'])]
    assert json.loads(row['attempt_outputs'][0]['raw'])['hypothesis'] == LONG          # the rejected first attempt, verbatim
    exported_outputs = {m.get('proposal_ref') or m.get('raw') for m in recording['mechanic_outputs']}
    assert saved['output_refs'][0] not in exported_outputs                             # today's list still omits it
    assert recording['diagnostics'][0]['proposed_kind'] == 'CONTRACT_EVIDENCE_GAP'

    status, matrix = await api_get(owner, f'/api/campaigns/{campaign.campaign_id}/matrix')
    status2, diagnostic = await api_get(owner, f'/api/diagnostics/{result.diagnostic.diagnostic_id}')
    out = {'recording_has_diagnosis_requests': 'diagnosis_requests' in recording,
           'matrix_status': status, 'matrix_mentions_diagnosis_requests': 'diagnosis_requests' in json.dumps(matrix),
           'diagnostic_status': status2, 'diagnostic_endpoint_mentions_proposal_status': 'proposal_status' in json.dumps(diagnostic),
           'record': saved, 'recording_row_keys': sorted(row)}
    frontend = FAULTLAB / 'frontend' / 'src'
    out['frontend_files_mentioning_diagnosis_requests'] = sorted(str(p.relative_to(FAULTLAB)) for p in frontend.rglob('*')
                                                                 if p.is_file() and p.suffix in ('.ts', '.tsx', '.js', '.jsx')
                                                                 and ('diagnosis_requests' in p.read_text(errors='ignore')
                                                                      or 'proposal_status' in p.read_text(errors='ignore')))
    out['frontend_files_mentioning_mechanic_diagnosis'] = sorted(str(p.relative_to(FAULTLAB)) for p in frontend.rglob('*')
                                                                 if p.is_file() and p.suffix in ('.ts', '.tsx')
                                                                 and 'mechanic_diagnosis' in p.read_text(errors='ignore'))
    evidence = Path(__file__).resolve().parents[1] / 'loop-evidence'; evidence.mkdir(exist_ok=True)
    (evidence / 'planned-export-api.json').write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + '\n')
    assert out['recording_has_diagnosis_requests'] and status == 200 and status2 == 200


@pytest.mark.anyio
async def test_a_learn_plan_saved_before_the_rule_gets_todays_repair_no_record_and_todays_export_keys(owner):
    registration = register_agent(owner.store, owner.settings, 'reference')
    prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration))
    prepared.plan.pop('mechanic_diagnosis')
    older = owner.create(prepared.campaign_request, run_plan=prepared)
    saved_plan = owner.store.get_record('campaign_plans', older.campaign_id)
    assert 'mechanic_diagnosis' not in saved_plan
    assert saved_plan['plan_hash'] == content_hash({k: v for k, v in saved_plan.items() if k != 'plan_hash'})
    result = await diagnose_as_learning_does(owner, older)
    assert result.rules[0] is None and result.record is None
    first, repair = result.provider.requests
    assert json.loads(repair[3]['content'])['validation_errors'] == [{'location': ['hypothesis'], 'type': 'string_too_long'}]
    assert owner.store.list_records('diagnosis_requests') == []
    status, recording = await api_get(owner, f'/api/campaigns/{older.campaign_id}/recording')
    assert status == 200 and 'diagnosis_requests' not in recording

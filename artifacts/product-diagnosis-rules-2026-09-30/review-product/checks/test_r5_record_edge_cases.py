"""Review check 5 ($0, offline): Rule 1 records in cases the builder's matrix does not name.

* an operator Stop (or a callback error) before the first fresh intervention trial: what intervention_ran and the
  statement say when zero trials ran;
* binding errors (unknown evidence id / unknown intervention id) and non-JSON answers: status, errors and statement;
* the repair message for a binding error is today's form plus only the appended sentence.
"""
import json
from types import SimpleNamespace

import pytest

from app.agents.mechanic import FORMAT_REPAIR_INSTRUCTION, Mechanic
from app.contracts.models import FaultSpec, TrialResult, Usage, canonical_json, content_hash
from app.lab import diagnosis_protocol
from app.lab.diagnosis import Diagnostician
from app.lab.storage import LabStore
from app.providers.runtime import RuntimeGeneration
from test_loop_limits_mechanic_context import bundle

MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
RECIPE = FaultSpec.model_validate({'seed': 5, 'primitives': [{'kind': 'F2', 'target_tool': 'update_order', 'target_service': 'orders',
                                                              'occurrence': 1, 'parameters': {'completion_delay_ticks': 3,
                                                              'terminal_status': 'SUCCEEDED', 'failure_code': None}}]})
POLICY = SimpleNamespace(policy_hash=content_hash('policy-fixture'), version='policy-v0')
CAMPAIGN = SimpleNamespace(campaign_id='campaign-review', task_text='Upgrade')
EVIDENCE = [bundle(e, ['PENDING', 'FAILED'], failed=('C3',)) for e in ('episode-source', 'episode-r0', 'episode-r1')]
COUNTER = SimpleNamespace(counterexample_id='counterexample-review', target_invariant='C3', attempted_count=3, valid_count=3,
                          target_violation_count=3)


@pytest.fixture
def anyio_backend(): return 'asyncio'


def reproduction():
    return [TrialResult(episode_id=f'episode-r{i}', world_id=f'world-r{i}', scenario_hash=content_hash(RECIPE), policy_hash=POLICY.policy_hash,
                        arm='B0', trial_index=i, lifecycle='COMPLETED', outcome='VIOLATION', failed_checks=['C3'], fault_scheduled=True,
                        fault_triggered=True, usage=Usage(actor_calls=3, http_attempts=3)) for i in range(3)]


class Provider:
    def __init__(self, outputs): self.outputs = list(outputs); self.requests = []
    def role_model(self, role): return MODEL
    async def complete(self, messages, **kwargs):
        self.requests.append(json.loads(json.dumps(messages)))
        output = self.outputs.pop(0)
        return RuntimeGeneration(output(json.loads(messages[1]['content'])) if callable(output) else output, MODEL)


class Ledger:
    def __init__(self): self.reservations = {}
    def consume_call(self, **kwargs): pass
    def reconcile(self, generation): pass
    def reserve(self, name, calls, tokens=None): self.reservations[name] = calls
    def release(self, name): self.reservations.pop(name, None)


class Runner:
    def __init__(self, fail=False): self.calls = 0; self.fail = fail
    async def run(self, campaign, spec, policy, *, purpose, trial_index, fixture_id, ledger, reservation, stop):
        self.calls += 1
        if self.fail: raise RuntimeError('simulator unavailable')
        violation = bool(spec.primitives)
        return TrialResult(episode_id=f'episode-i{self.calls}', world_id=f'world-i{self.calls}', scenario_hash=content_hash(spec),
                           policy_hash=policy.policy_hash, arm='B0', trial_index=trial_index, lifecycle='COMPLETED',
                           outcome='VIOLATION' if violation else 'COMPLETED', failed_checks=['C3'] if violation else [],
                           fault_scheduled=violation, fault_triggered=violation, usage=Usage(actor_calls=3, http_attempts=3))


def request(context, **changes):
    return canonical_json({'proposed_kind': 'POLICY_GAP', 'hypothesis': 'Removing the delay removes the violation.',
                           'evidence_ids': context['evidence_ids'][:1], 'requested_intervention_id': context['intervention_ids'][0], **changes})


async def diagnose(tmp_path, outputs, *, stop=lambda: False, runner=None):
    store, provider = LabStore(tmp_path / 'review.db'), Provider(outputs)
    mechanic = Mechanic(provider, store, Ledger()); mechanic.diagnosis_protocol = diagnosis_protocol.declaration()
    chain = diagnosis_protocol.RecordingDiagnosisMechanic(mechanic, mechanic)
    runner = runner or Runner()
    diagnostic, run = await Diagnostician(store, runner, Ledger(), chain).run(CAMPAIGN, COUNTER, RECIPE, POLICY, reproduction(),
                                                                                evidence=EVIDENCE, stop=stop)
    record = diagnosis_protocol.record(store, CAMPAIGN, COUNTER, diagnostic, run, chain)
    return SimpleNamespace(record=record, diagnostic=diagnostic, run=run, provider=provider, runner=runner)


@pytest.mark.anyio
@pytest.mark.parametrize('case', ['stop', 'callback_error'])
async def test_zero_fresh_trials_is_still_recorded_as_intervention_ran(tmp_path, case):
    result = await diagnose(tmp_path, [request], stop=(lambda: True) if case == 'stop' else (lambda: False),
                            runner=Runner(fail=case == 'callback_error'))
    record = result.record
    assert record['proposal_status'] == 'VALID_REQUESTED' and record['verdict'] == 'INCONCLUSIVE'
    assert record['fresh_intervention_trials'] == 0 and record['interventions'][0]['trial_pairs'] == 0
    assert record['interventions'][0]['limitations'] == (['STOPPED'] if case == 'stop' else ['CALLBACK_ERROR:RuntimeError'])
    # REVIEW FINDING: the record says an intervention ran although no fresh trial ran, and the statement omits why.
    assert record['intervention_ran'] is True
    assert 'STOPPED' not in record['statement'] and 'CALLBACK_ERROR' not in record['statement']
    assert 'Intervention result: ' in record['statement'] and record['statement'].endswith("is the model's.")


@pytest.mark.anyio
async def test_binding_errors_repair_in_todays_form_plus_the_sentence_and_record_invalid_output(tmp_path):
    bad = lambda context: request(context, evidence_ids=['evidence-not-offered'], requested_intervention_id='intervention-not-offered')
    result = await diagnose(tmp_path, [bad, bad])
    repair = json.loads(result.provider.requests[1][3]['content'])
    assert repair == {'validation_errors': [{'location': ['evidence_ids'], 'type': 'unknown_evidence_reference'},
                                            {'location': ['requested_intervention_id'], 'type': 'unknown_intervention_reference'}],
                      'instruction': FORMAT_REPAIR_INSTRUCTION + ' ' + diagnosis_protocol.REPAIR_SENTENCE}
    record = result.record
    assert record['proposal_status'] == 'INVALID_OUTPUT' and record['recorded_proposed_kind_source'] == 'code_default'
    assert record['last_raw_unvalidated']['requested_intervention_id'] == 'intervention-not-offered'
    assert 'unknown_evidence_reference' in record['statement'] and not record['intervention_ran']


@pytest.mark.anyio
async def test_non_json_answers_are_recorded_verbatim_as_invalid_output(tmp_path):
    result = await diagnose(tmp_path, ['not json at all', 'still not json'])
    record = result.record
    assert record['proposal_status'] == 'INVALID_OUTPUT'
    assert record['last_raw_unvalidated'] == {'validated': False, 'parsed_json_object': False, 'proposed_kind': None,
                                              'requested_intervention_id': None}
    assert [a['validation_errors'][0]['type'] for a in record['attempts']] == ['json_invalid', 'json_invalid']
    assert "named proposed_kind None and requested None" in record['statement']

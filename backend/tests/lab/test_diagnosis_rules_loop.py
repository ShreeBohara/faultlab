"""The two diagnosis rules inside the learning loop ($0, offline; no provider, W&B or Weave call).

* The wrapper order: guide outside citation status, which sits outside the size rule; the recorder outermost. With the
  rules declared, the diagnosis request carries the guide block and the citation block, and the record is written before
  the POLICY_GAP gate; without them the loop never runs their code.
* T8 (RECOMMENDATION.md section 5): the offline_fixture scripted Learn campaign (real localhost simulator, real Mechanic
  parsing, real diagnosis control/treatment) follows the same path with the same counts with Rule 1 declared, plus one
  diagnosis_requests record per diagnosis.
"""
import json

import pytest

from app.contracts.models import canonical_json
from app.lab import citation_status, diagnosis_guide, diagnosis_protocol, loop_limits
from app.lab.loop_limits import mechanic_context_declaration
from test_citation_status import diagnosis_answer, native_loop, requests_of


@pytest.fixture
def anyio_backend(): return 'asyncio'


def declare(monkeypatch, *, rule1=True, guide=True):
    monkeypatch.setattr(diagnosis_protocol, 'campaign_rule', lambda store, campaign: diagnosis_protocol.declaration() if rule1 else None)
    monkeypatch.setattr(diagnosis_guide, 'campaign_rule', lambda store, campaign: diagnosis_guide.declaration() if guide else None)


@pytest.mark.anyio
async def test_the_wrappers_nest_guide_outside_citation_status_outside_the_size_rule_and_the_recorder_outermost(tmp_path, monkeypatch):
    import app.lab.learning as learning
    from app.agents.mechanic import PROMPTS
    c, campaign, runner, provider, _ = native_loop(tmp_path, monkeypatch, [diagnosis_answer], real_diagnosis=True)
    declare(monkeypatch)
    chains, gate_seen = [], []
    base = learning.Diagnostician

    class Diagnostician(base):
        def __init__(self, store, runner, ledger, mechanic):
            chains.append(mechanic); super().__init__(store, runner, ledger, mechanic)
        async def run(self, *args, **kwargs):
            diagnostic, run = await super().run(*args, **kwargs)
            gate_seen.append(c.store.get_record('diagnosis_requests', diagnostic.diagnostic_id))   # before the loop reads kind
            return diagnostic, run
    monkeypatch.setattr(learning, 'Diagnostician', Diagnostician)
    order = []
    original_record = diagnosis_protocol.record
    def record(*args, **kwargs):
        order.append('record'); return original_record(*args, **kwargs)
    monkeypatch.setattr(diagnosis_protocol, 'record', record)
    await learning.run_learning_cycle(c, campaign, runner)
    chain, = chains
    layers = []
    while True:
        layers.append(type(chain).__name__)
        inner = chain.__dict__.get('mechanic')
        if inner is None: break
        chain = inner
    assert layers == ['RecordingDiagnosisMechanic', 'DiagnosisGuideMechanic', 'CitationStatusMechanic', 'BoundedMechanic', 'Mechanic']
    request, = requests_of(provider, (PROMPTS / 'diagnosis.md').read_text()[:200])
    assert request['diagnosis_guide'] == diagnosis_guide.block(campaign.task_text)
    assert citation_status.BLOCK in request
    assert gate_seen == [None] and order == ['record']            # written after run() returned, before the gate
    saved_record, = c.store.list_records('diagnosis_requests')
    assert saved_record['proposal_status'] == 'VALID_NO_REQUEST' and saved_record['verdict'] == 'INCONCLUSIVE'
    output, = c.store.list_records('mechanic_outputs')
    assert saved_record['request_id'] == output['request_id'] and len(saved_record['output_refs']) == 1


@pytest.mark.anyio
async def test_without_the_rules_the_loop_never_runs_their_code(tmp_path, monkeypatch):
    import app.lab.learning as learning
    from app.agents.mechanic import PROMPTS
    c, campaign, runner, provider, _ = native_loop(tmp_path, monkeypatch, [diagnosis_answer], real_diagnosis=True)
    declare(monkeypatch, rule1=False, guide=False)
    def forbidden(*args, **kwargs): raise AssertionError('diagnosis-rule code ran for a plan without the rules')
    for module, names in ((diagnosis_protocol, ('record', 'RecordingDiagnosisMechanic', 'repair_errors', 'repair_message')),
                          (diagnosis_guide, ('attach', 'block', 'DiagnosisGuideMechanic'))):
        for name in names: monkeypatch.setattr(module, name, forbidden)
    await learning.run_learning_cycle(c, campaign, runner)
    request, = requests_of(provider, (PROMPTS / 'diagnosis.md').read_text()[:200])
    assert 'diagnosis_guide' not in request and c.store.list_records('diagnosis_requests') == []


def _counts(result):
    records = result['records']
    return {'state': result['campaign']['state'], 'episode_counts': result['episode_counts'],
            'scripted_generation_calls': result['scripted_generation_calls'], 'lifecycle_counts': result['lifecycle_counts'],
            'outcome_counts': result['outcome_counts'],
            'records': {kind: len(records[kind]) for kind in records},
            'diagnostic_kinds': [d['kind'] for d in records['diagnostics']],
            'intervention_results': [i['result'] for i in records['interventions']],
            'budget_calls': result['budget']['used_calls']}


@pytest.mark.anyio
@pytest.mark.localhost_http
async def test_T8_the_offline_fixture_campaign_follows_the_same_path_with_rule_1_plus_one_record_per_diagnosis(tmp_path, monkeypatch):
    from original_loop_fixture import exercise
    before = await exercise(tmp_path / 'before', 'accepted')
    declare(monkeypatch, guide=False)
    import app.lab.coordinator  # noqa: F401  (the loop reads the rule through the patched module attribute)
    records = []
    original = diagnosis_protocol.record
    def keep(store, *args, **kwargs):
        value = original(store, *args, **kwargs); records.append(value); return value
    monkeypatch.setattr(diagnosis_protocol, 'record', keep)
    after = await exercise(tmp_path / 'after', 'accepted')
    assert _counts(after) == _counts(before)
    assert after['campaign']['state'] == 'COMPLETED' and after['episode_counts']['intervention'] == 6
    diagnostics = after['records']['diagnostics']
    assert len(records) == len(diagnostics) == 1
    record, = records
    assert record['diagnostic_id'] == diagnostics[0]['diagnostic_id'] and record['proposal_status'] == 'VALID_REQUESTED'
    assert record['recorded_proposed_kind_source'] == 'model' and record['intervention_ran'] and record['verdict'] == 'POLICY_GAP'
    assert [r['result'] for r in record['interventions']] == [i['result'] for i in after['records']['interventions']]
    assert record['requested_change'] == record['options'][0]['change'] and len(record['output_refs']) == 1
    json.dumps(record)  # plain JSON
    assert canonical_json(record) == canonical_json(json.loads(canonical_json(record)))
    assert loop_limits.MECHANIC_CONTEXT_V2 and mechanic_context_declaration()


# ------------------------------------------------------------------------------------------ fixer: review finding LOW-4

from test_discovery_v2_flow import owner  # noqa: E402,F401  (fixture)

@pytest.mark.parametrize('waiting', ['discovery', 'intervention'])
def test_fix_rule_1_records_every_diagnosis_of_the_real_mechanic_through_evidence_waits(owner, monkeypatch, waiting):
    """Review finding LOW-4: the two evidence-wait harnesses switch Rule 1 off (their Diagnostician is a double), so Rule 1
    was never run together with an evidence wait. Here the real coordinator runs a planned Learn campaign (Rule 1 frozen in
    its plan, evidence retry v3) through _execute with the REAL Diagnostician and the REAL Mechanic's diagnosis request (a
    scripted provider: a 614-character first answer, then a valid repair). One Weave read fails first, before the diagnosis
    (a discovery episode) or after it (an intervention episode); the product's automatic retry clears it. The campaign must
    end NO_CHANGE, not ERROR, with exactly one diagnosis_requests record per diagnostic."""
    import asyncio
    import app.lab.learning as learning
    from app.agents.mechanic import Mechanic as RealMechanic
    from app.lab.diagnosis import Diagnostician as RealDiagnostician
    from app.lab.run_plans import read_run_plan
    from app.providers.runtime import RuntimeGeneration
    from test_evidence_wait import harness, purpose_is, waits
    from test_loop_limits_mechanic_context import bundle
    real_rule = diagnosis_protocol.campaign_rule
    campaign, weave, runner, ledger = harness(owner, monkeypatch, purpose_is(waiting, first_only=True), mode='gain')
    ident = campaign.campaign_id
    monkeypatch.setattr(diagnosis_protocol, 'campaign_rule', real_rule)          # the harness switched it off; this plan declares it
    assert read_run_plan(owner.store, ident)['plan']['mechanic_diagnosis'] == diagnosis_protocol.declaration()
    model = owner.settings.model_for_role('mechanic')

    class Provider:
        """Diagnosis requests only: attempt 0 has a 614-character hypothesis (as in v2g), the repair turn a valid one."""
        def __init__(self): self.requests = []
        def role_model(self, role): return model
        async def complete(self, messages, **kwargs):
            self.requests.append(json.loads(json.dumps(messages)))
            context = json.loads(messages[1]['content'])
            hypothesis = 'h' * 614 if len(messages) == 2 else 'Offline fixture: the delayed upgrade precedes a premature confirmation.'
            return RuntimeGeneration(canonical_json({'proposed_kind': 'POLICY_GAP', 'hypothesis': hypothesis, 'evidence_ids': context['evidence_ids'][:1],
                                                     'requested_intervention_id': context['intervention_ids'][0]}), model, input_tokens=100, output_tokens=20)
    provider = Provider(); runner.provider = provider

    class Mechanic(RealMechanic):
        async def propose(self, context, **kwargs): raise AssertionError('no candidate request: every diagnosis here is INCONCLUSIVE')
    monkeypatch.setattr(learning, 'Mechanic', Mechanic)
    monkeypatch.setattr(learning, 'Diagnostician', RealDiagnostician)
    persisted = runner.run
    async def run(current, recipe, policy, **kwargs):                             # the real Diagnostician names no arm
        return await persisted(current, recipe, policy, **{'arm': 'B0', **kwargs})
    runner.run = run
    read = weave.get
    async def get(episode_id, context, **kwargs):                                 # the harness's failures and retries, real bundles
        await read(episode_id, context, **kwargs)
        return bundle(episode_id, ['SUCCEEDED', 'PENDING'], failed=('C3',))
    weave.get = get

    asyncio.run(owner._execute(ident, True))
    final = owner.get(ident)
    assert final.state == 'NO_CHANGE', final.terminal_reason
    assert not owner.store.list_records('execution_errors')
    diagnostics = [d for d in owner.store.list_records('diagnostic_campaigns') if d['campaign_id'] == ident]
    records = [r for r in owner.store.list_records('diagnosis_requests') if r['campaign_id'] == ident]
    assert diagnostics and sorted(r['diagnostic_id'] for r in records) == sorted(d['diagnostic_id'] for d in diagnostics)
    interventions = {i['intervention_id']: i for i in owner.store.list_records('interventions')}
    for record in records:
        assert record['proposal_status'] == 'VALID_REQUESTED' and record['recorded_proposed_kind_source'] == 'model'
        assert [a['validation_errors'] for a in record['attempts']] == [[{'location': ['hypothesis'], 'type': 'string_too_long',
                                                                          'max_characters': 600, 'your_characters': 614}], []]
        assert record['intervention_ran'] and record['fresh_intervention_trials'] == 6 and record['verdict'] == 'INCONCLUSIVE'
        outputs = [owner.store.get_record('mechanic_outputs', ref) for ref in record['output_refs']]
        assert [o['attempt'] for o in outputs] == [0, 1] and {o['request_id'] for o in outputs} == {record['request_id']}
    repairs = [r for r in provider.requests if len(r) == 4]
    assert len(repairs) == len(records) and all(json.loads(r[3]['content'])['instruction'] == diagnosis_protocol.REPAIR_INSTRUCTION for r in repairs)
    wait, = waits(owner, ident)
    assert wait['status'] == 'RESOLVED' and wait['resolution'] == 'VERIFIED'
    episode = owner.store.get_record('episodes', wait['episode_id'])
    assert episode['experiment_purpose'] == waiting
    if waiting == 'intervention':                                                 # the wait came after that diagnosis's record
        pairs = [episode_id for record in records for row in record['interventions']
                 for pair in interventions[row['intervention_id']]['trial_pairs'] for episode_id in pair]
        assert wait['episode_id'] in pairs

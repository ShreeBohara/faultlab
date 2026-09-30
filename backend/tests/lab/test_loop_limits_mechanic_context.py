"""faultlab-mechanic-context/v2-bounded (app.lab.loop_limits): an over-limit Mechanic request is compacted by fixed stages,
or that source's search ends with a recorded reason; nothing over the limit is ever sent, and no campaign ends ERROR.

Live campaign ea66672d (run v2d, September 30) ended ERROR when its second candidate request came to 33,223 input tokens
(limit 32,000). No provider, W&B or Weave call is made here; the saved-store test copies the store read-only to a
temporary directory outside the Desktop and deletes the copy.
"""
import json
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter

from app.contracts import tokens
from app.contracts.models import (CheckResult, DiagnosticProposal, MechanicCandidate, MechanicOutput, PublicObservation,
                                  TaskReport, ToolResult, TrialResult, Usage, canonical_json, content_hash)
from app.contracts.tokens import ModelInputLimit, input_token_bound
from app.lab import loop_limits
from app.lab.diagnosis import summarize_evidence
from app.lab.loop_limits import (COMPACTION_TARGET_TOKENS, MECHANIC_CONTEXT_V2, STAGE_IDENTICAL, STAGE_NO_CLEAN,
                                 STAGE_ONE_PER_GROUP, compact_request, filtered_summary, mechanic_context_declaration)
from app.lab.storage import LabStore
from app.providers.runtime import RuntimeGeneration


@pytest.fixture
def anyio_backend(): return 'asyncio'


def observation(episode, index, status, *, tick=None, note=None):
    call = 'call-' + content_hash(f'{episode}:{index}')[:24]   # opaque, so the summary aliases it per episode (@iN)
    return PublicObservation(episode_id=episode, evidence_id=f'evidence-{episode}-{index}', call_id=call,
                             delivered_tick=tick if tick is not None else index + 1,
                             result=ToolResult(call_id=call, tool='get_operation_status', transport='ok', status=status, error_code=note))


def bundle(episode, statuses, *, failed=(), events=1, note=None):
    observations = [observation(episode, i, s, note=note) for i, s in enumerate(statuses)]
    report = TaskReport.model_validate({'upgrade_outcome': 'SUCCEEDED', 'notification_outcome': 'SUCCEEDED', 'overall': 'COMPLETED',
                                        'evidence_ids': [o.evidence_id for o in observations[:1]], 'next_action': {'kind': 'NONE'}})
    findings = [CheckResult(check_id=f'C{n}', passed=f'C{n}' not in failed, category='fixture',
                            evidence_ids=[o.evidence_id for o in observations], event_ids=[f'event-{k}' for k in range(events)])
                for n in range(1, 9)]
    return SimpleNamespace(episode_id=episode, source='weave_verified', observations=observations, report=report, findings=findings)


def trial(store, episode, scenario, arm, *, failed=(), triggered=True, policy='p', purpose=None):
    record = TrialResult(episode_id=episode, world_id='world-' + episode, scenario_hash=content_hash(scenario), policy_hash=content_hash(policy),
                         arm=arm, trial_index=0, lifecycle='COMPLETED', outcome='VIOLATION' if failed else 'COMPLETED',
                         failed_checks=list(failed), fault_scheduled=True, fault_triggered=triggered, usage=Usage(actor_calls=3, http_attempts=3))
    store.put_record('trials', episode, record)
    if purpose is not None:
        store.put_record('episodes', episode, {'episode_id': episode, 'campaign_id': 'campaign-x', 'experiment_purpose': purpose})


def kept(block): return [row['episode_id'] for row in block['episodes']]


def named(block): return [row['episode_id'] for row in (block.get('compaction') or {}).get('omitted', [])]


# --------------------------------------------------------------------------- the frozen summary format is preserved

def test_a_filtered_summary_is_exactly_the_summary_of_the_kept_episodes_alone():
    bundles = [bundle('a', ['PENDING', 'SUCCEEDED'], failed=('C3',)), bundle('b', ['SUCCEEDED']), bundle('c', ['PENDING', 'FAILED']),
               bundle('d', ['SUCCEEDED'], events=3), bundle('e', ['PENDING', 'PENDING', 'SUCCEEDED']), bundle('f', ['SUCCEEDED'])]
    full = summarize_evidence(bundles)
    for keep in ({'a', 'c', 'e'}, {'b', 'd', 'f'}, {'a'}, {'a', 'b', 'c', 'd', 'e', 'f'}, set()):
        assert filtered_summary(full, keep) == summarize_evidence([b for b in bundles if b.episode_id in keep])


# --------------------------------------------------------------------------- stages, what is always kept, the statement

def candidate_context(store):
    """Source + 3 reproductions (C3), 2 failing controls, 6 clean episodes in 2 outcome groups (2 of them identical),
    and a challenge block of 6 clean episodes; every episode has a trial record."""
    dev = [bundle('source', ['PENDING'], failed=('C3',)), *[bundle(f'repro-{i}', ['PENDING'], failed=('C3',)) for i in range(3)],
           bundle('control-0', ['FAILED'], failed=('C3',)), bundle('control-1', ['FAILED'], failed=('C3',)),
           bundle('clean-a0', ['SUCCEEDED']), bundle('clean-a1', ['SUCCEEDED']), bundle('clean-a2', ['PENDING', 'SUCCEEDED'], events=4),
           bundle('clean-b0', ['FAILED'], events=2), bundle('clean-b1', ['FAILED', 'FAILED'], events=5), bundle('clean-b2', ['FAILED'], events=6)]
    for b in dev[:4]: trial(store, b.episode_id, 'source-recipe', 'B0', failed=('C3',))
    for b in dev[4:6]: trial(store, b.episode_id, 'control', 'B0', failed=('C3',))
    for b in dev[6:9]: trial(store, b.episode_id, 'source-recipe', 'L')
    for b in dev[9:]: trial(store, b.episode_id, 'treatment', 'B0')
    challenge = [bundle(f'ch-{i}', ['SUCCEEDED'] * (1 + i % 3), events=2 + i) for i in range(6)]
    for i, b in enumerate(challenge): trial(store, b.episode_id, 'schedule-1', 'B0' if i % 2 == 0 else 'L')
    return {'campaign_id': 'campaign-x', 'development_evidence': summarize_evidence(dev), 'candidate_history': [{'kept': True}],
            'challenge_counterexamples': [{'status': 'INCONCLUSIVE', 'trial_outcomes': [{'episode_ids': [b.episode_id for b in challenge]}],
                                           'evidence': summarize_evidence(challenge)}],
            'source_validation_feedback': [{'x': 1}], 'runtime_contract': {'actor_contract': 'unchanged'}}


PROTECTED = ['source', 'repro-0', 'repro-1', 'repro-2']
ALWAYS = PROTECTED + ['control-0', 'control-1']


def per_episode_bound(request):
    """A stand-in admission count: 1,000 per episode kept in full, plus the statement."""
    blocks = [request['development_evidence'], *[item['evidence'] for item in request['challenge_counterexamples']]]
    return 1000 * sum(len(b['episodes']) for b in blocks) + (100 if 'context_compaction' in request else 0)


@pytest.mark.parametrize('target,stages,dev_kept,challenge_kept', [
    (17100, [STAGE_IDENTICAL], ALWAYS + ['clean-a0', 'clean-a2', 'clean-b0', 'clean-b1', 'clean-b2'], ['ch-0', 'ch-1', 'ch-2', 'ch-3', 'ch-4', 'ch-5']),
    (10100, [STAGE_IDENTICAL, STAGE_ONE_PER_GROUP], ALWAYS + ['clean-a0', 'clean-b0'], ['ch-0', 'ch-1']),
    (6100, [STAGE_IDENTICAL, STAGE_ONE_PER_GROUP, STAGE_NO_CLEAN], ALWAYS, []),
])
def test_stages_run_in_order_keep_the_source_and_every_failure_and_name_every_omitted_episode(tmp_path, monkeypatch, target, stages, dev_kept, challenge_kept):
    store = LabStore(tmp_path / 'lab.db'); context = candidate_context(store)
    monkeypatch.setattr(loop_limits, 'COMPACTION_TARGET_TOKENS', target)
    request, summary = compact_request(context, request_kind='mechanic_proposal', protected_episode_ids=PROTECTED, store=store,
                                       bound=per_episode_bound, full_bound=33223)
    assert summary['fits'] and summary['stages_applied'] == stages
    dev, challenge = request['development_evidence'], request['challenge_counterexamples'][0]['evidence']
    assert kept(dev) == dev_kept and kept(challenge) == challenge_kept
    # Every episode is either kept in full or named with its own outcome; none is both, none is lost.
    for before, after in ((context['development_evidence'], dev), (context['challenge_counterexamples'][0]['evidence'], challenge)):
        assert sorted(kept(after) + named(after)) == sorted(kept(before)) and not set(kept(after)) & set(named(after))
        assert after == filtered_summary(before, set(kept(after))) | ({'interpretation': after['interpretation'], 'compaction': after['compaction']} if named(after) else {})
    if 'clean-a0' in kept(dev):   # stage 1: clean-a1 repeats clean-a0's rows and outcome (stage 3 keeps neither in full)
        assert {o['episode_id']: o.get('same_as') for o in dev['compaction']['omitted']}['clean-a1'] == 'clean-a0'
    omitted = [o for b in (dev, challenge) for o in (b.get('compaction') or {}).get('omitted', [])]
    assert all(o['failed_checks'] == [] and o['outcome'] == 'COMPLETED' and o['arm'] in ('B0', 'L') for o in omitted)
    # The statement is inside the request, says what was compacted and how many rows were omitted.
    block = request['context_compaction']
    assert block['protocol'] == MECHANIC_CONTEXT_V2 and block['episode_rows_omitted'] == len(omitted) == summary['attempts'][-1]['episode_rows_omitted']
    assert block['statement'] == summary['statement'] and f'{len(omitted)} clean episode(s) were omitted' in block['statement']
    assert 'The source episode, its reproductions and every episode with a failed check are kept in full' in block['statement']
    assert 'COMPACTED under ' + MECHANIC_CONTEXT_V2 in (dev.get('interpretation') or '') or not named(dev)
    # Nothing outside the evidence tables changed.
    same = lambda value: {k: v for k, v in value.items() if k not in ('development_evidence', 'challenge_counterexamples', 'context_compaction')}
    assert same(request) == same(context)
    assert {k: v for k, v in request['challenge_counterexamples'][0].items() if k != 'evidence'} == {k: v for k, v in context['challenge_counterexamples'][0].items() if k != 'evidence'}
    # Deterministic: the same input gives the same bytes.
    again, _ = compact_request(context, request_kind='mechanic_proposal', protected_episode_ids=PROTECTED, store=store,
                               bound=per_episode_bound, full_bound=33223)
    assert canonical_json(again) == canonical_json(request)


def test_a_request_that_cannot_fit_is_not_returned(tmp_path, monkeypatch):
    store = LabStore(tmp_path / 'lab.db'); context = candidate_context(store)
    monkeypatch.setattr(loop_limits, 'COMPACTION_TARGET_TOKENS', 5000)      # below the 6 always-kept episodes
    request, summary = compact_request(context, request_kind='mechanic_proposal', protected_episode_ids=PROTECTED, store=store,
                                       bound=per_episode_bound, full_bound=40000)
    assert request is None and not summary['fits'] and [a['request_tokens'] for a in summary['attempts']] == [17100, 10100, 6100]
    # A stage that omits nothing leaves the request as it was (no statement is added).
    solo = {'development_evidence': summarize_evidence([bundle('source', ['PENDING'], failed=('C3',))]), 'challenge_counterexamples': []}
    request, summary = compact_request(solo, request_kind='mechanic_proposal', protected_episode_ids=['source'], store=store,
                                       bound=lambda r: 9999, full_bound=9999)
    assert request is None and summary['attempts'] == [{'stages_applied': list(loop_limits.STAGES[:n]), 'episode_rows_omitted': 0,
                                                         'request_tokens': 9999} for n in (1, 2, 3)]


def test_an_outcome_that_differs_inside_a_recipe_keeps_its_own_full_example(tmp_path, monkeypatch):
    """Nothing contradictory is dropped silently: an untriggered and a triggered clean episode of the same recipe and arm
    are different outcome groups, so stage 2 keeps one of each in full."""
    store = LabStore(tmp_path / 'lab.db')
    bundles = [bundle(f'e{i}', ['SUCCEEDED'], events=i + 1) for i in range(3)]
    for i, b in enumerate(bundles): trial(store, b.episode_id, 'status-fault', 'B0', triggered=i == 2)
    context = {'development_evidence': summarize_evidence(bundles), 'challenge_counterexamples': []}
    monkeypatch.setattr(loop_limits, 'COMPACTION_TARGET_TOKENS', 2100)
    bound = lambda r: 1000 * len(r['development_evidence']['episodes']) + 100
    request, summary = compact_request(context, request_kind='mechanic_proposal', protected_episode_ids=[], store=store, bound=bound, full_bound=33000)
    assert summary['stages_applied'][-1] == STAGE_ONE_PER_GROUP and kept(request['development_evidence']) == ['e0', 'e2']
    omitted, = request['development_evidence']['compaction']['omitted']
    assert omitted == {'episode_id': 'e1', 'observations': 1, 'original_report_present': True, 'arm': 'B0', 'lifecycle': 'COMPLETED',
                       'outcome': 'COMPLETED', 'failed_checks': [], 'fault_triggered': False, 'omitted_as': STAGE_ONE_PER_GROUP, 'group_example': 'e0'}


def test_stage_two_names_a_group_example_and_says_the_omitted_rows_can_differ_from_it(tmp_path, monkeypatch):
    """Product review LOW-1: an episode omitted at stage 2 shares only its recipe, arm, policy, purpose and outcome with
    the kept example of its group; its own rows (report, observations) can differ, and the request must say so. Only
    stage 1 (same_as) claims identical rows."""
    store = LabStore(tmp_path / 'lab.db')
    bundles = [bundle('e0', ['SUCCEEDED'], events=1), bundle('e1', ['PENDING', 'SUCCEEDED'], events=4)]   # different rows
    for b in bundles: trial(store, b.episode_id, 'recipe', 'L')
    context = {'development_evidence': summarize_evidence(bundles), 'challenge_counterexamples': []}
    monkeypatch.setattr(loop_limits, 'COMPACTION_TARGET_TOKENS', 1100)
    bound = lambda r: 1000 * len(r['development_evidence']['episodes']) + 100
    request, summary = compact_request(context, request_kind='mechanic_proposal', protected_episode_ids=[], store=store, bound=bound, full_bound=33000)
    block = request['development_evidence']
    omitted, = block['compaction']['omitted']
    assert omitted['omitted_as'] == STAGE_ONE_PER_GROUP and omitted['group_example'] == 'e0' and 'represented_by' not in omitted
    for text in (block['interpretation'], request['context_compaction']['statement'], loop_limits.STAGE_TEXT[STAGE_ONE_PER_GROUP],
                 loop_limits.MECHANIC_CONTEXT_RULE):
        assert 'can differ' in text, text
    assert 'not repeated here' not in block['interpretation']


def test_an_episode_whose_trial_outcome_is_violation_is_always_kept(tmp_path, monkeypatch):
    """Integrity review LOW-1: FaultLab counts a violation as failed checks OR outcome VIOLATION (promotion.py,
    evaluation.observed_candidate_violations). An episode whose trial record says VIOLATION is kept in full even when
    no check row and no failed_checks entry says so; stage 3 omits only the clean one."""
    store = LabStore(tmp_path / 'lab.db')
    bundles = [bundle('v', ['SUCCEEDED']), bundle('c', ['SUCCEEDED'], events=2)]
    for b in bundles: trial(store, b.episode_id, 'recipe', 'L')
    record = store.get_record('trials', 'v'); record.update(outcome='VIOLATION', failed_checks=[]); store.put_record('trials', 'v', record)
    context = {'development_evidence': summarize_evidence(bundles), 'challenge_counterexamples': []}
    monkeypatch.setattr(loop_limits, 'COMPACTION_TARGET_TOKENS', 1100)
    bound = lambda r: 1000 * len(r['development_evidence']['episodes']) + 100
    request, summary = compact_request(context, request_kind='mechanic_proposal', protected_episode_ids=[], store=store, bound=bound, full_bound=33000)
    assert summary['fits'] and summary['stages_applied'][-1] == STAGE_NO_CLEAN
    assert kept(request['development_evidence']) == ['v'] and named(request['development_evidence']) == ['c']


def test_stage_two_never_lets_one_policy_or_purpose_stand_for_another(tmp_path, monkeypatch):
    """Integrity review LOW-2: development evidence holds every candidate's source-validation episodes (and intervention
    episodes). A clean episode of one candidate policy, or of another experiment purpose, is never omitted in favour
    of an example from another policy or purpose; each keeps its own full example."""
    store = LabStore(tmp_path / 'lab.db')
    bundles = [bundle(f'e{i}', ['SUCCEEDED'], events=i + 1) for i in range(4)]
    trial(store, 'e0', 'recipe', 'L', policy='candidate-a', purpose='source_validation')
    trial(store, 'e1', 'recipe', 'L', policy='candidate-a', purpose='source_validation')   # may use e0 as its example
    trial(store, 'e2', 'recipe', 'L', policy='candidate-b', purpose='source_validation')   # another candidate policy
    trial(store, 'e3', 'recipe', 'L', policy='candidate-a', purpose='intervention')        # another experiment purpose
    context = {'development_evidence': summarize_evidence(bundles), 'challenge_counterexamples': []}
    monkeypatch.setattr(loop_limits, 'COMPACTION_TARGET_TOKENS', 3100)
    bound = lambda r: 1000 * len(r['development_evidence']['episodes']) + 100
    request, summary = compact_request(context, request_kind='mechanic_proposal', protected_episode_ids=[], store=store, bound=bound, full_bound=33000)
    assert summary['stages_applied'][-1] == STAGE_ONE_PER_GROUP
    assert kept(request['development_evidence']) == ['e0', 'e2', 'e3']
    omitted, = request['development_evidence']['compaction']['omitted']
    assert omitted['episode_id'] == 'e1' and omitted['group_example'] == 'e0'
    assert 'policy' in loop_limits.STAGE_TEXT[STAGE_ONE_PER_GROUP] and 'purpose' in loop_limits.STAGE_TEXT[STAGE_ONE_PER_GROUP]


# --------------------------------------------------------------------------- the count is the Mechanic's own admission count

class Provider:
    """Counts every request that would be dispatched; answers with the scripted outputs."""
    def __init__(self, outputs=(), model='openai/gpt-oss-120b'):
        self.outputs = list(outputs); self.sent = []; self.model = model
    def role_model(self, role): return self.model
    async def complete(self, messages, **kwargs):
        self.sent.append(input_token_bound(messages, self.model))
        return RuntimeGeneration(self.outputs.pop(0), self.model, input_tokens=100, output_tokens=20)


@pytest.mark.anyio
@pytest.mark.parametrize('prompt,adapter,method', [('mechanic.md', TypeAdapter(MechanicOutput), 'propose'),
                                                   ('diagnosis.md', TypeAdapter(DiagnosticProposal), 'diagnose')])
async def test_the_bound_is_exactly_what_the_mechanic_admits(tmp_path, monkeypatch, prompt, adapter, method):
    import app.agents.mechanic as mechanic_module
    from app.agents.mechanic import Mechanic
    from app.lab.budgets import CampaignLedger
    store = LabStore(tmp_path / 'lab.db'); context = candidate_context(store)
    seen = []
    def capture(messages, model):
        seen.append(input_token_bound(messages, model)); raise ModelInputLimit(seen[-1])
    monkeypatch.setattr(mechanic_module, 'validate_model_input', capture)
    for model in ('openai/gpt-oss-120b', 'deepseek-ai/DeepSeek-V4-Pro-0813'):
        mechanic = Mechanic(Provider(model=model), store, CampaignLedger(store, 'campaign-x'))
        with pytest.raises(ModelInputLimit):
            await getattr(mechanic, method)(context)
        assert seen[-1] == loop_limits.mechanic_request_bound(mechanic, prompt, adapter, context)


# --------------------------------------------------------------------------- the refused v2d request, from a saved-store copy

SAVED_STORE = Path('/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3')
V2D = 'campaign-ea66672d7a904bd8a011d6922790c963'


def rebuild_v2d_request(store):
    """The learning loop's proposal_context for campaign ea66672d's second candidate request, from saved records only."""
    from app.contracts.models import Campaign, ChallengeResult, Counterexample, DiagnosticResult, EvidenceBundle, FaultSpec, PolicyVersion, ReductionResult
    from app.lab.diagnosis import reduction_context, runtime_contract, trial_outcomes
    from app.lab.learning import discovery_session
    get = lambda kind, ident, cls: cls.model_validate_json(canonical_json(store.get_record(kind, ident)))
    evidence = lambda ids: [EvidenceBundle.model_validate_json(canonical_json(store.get_record('evidence', e))) for e in ids]
    trials = lambda ids: [get('trials', e, TrialResult) for e in ids]
    campaign = store.get_model('campaigns', V2D, Campaign); incumbent = get('policies', 'policy-v0', PolicyVersion)
    identity, _ = discovery_session(store, campaign, incumbent)
    purposes = {}
    for row in store.list_records('episodes'):
        if row['campaign_id'] == V2D: purposes.setdefault(row['experiment_purpose'], []).append(row['episode_id'])
    counter = Counterexample.model_validate_json(canonical_json(next(r for r in store.list_records('counterexamples') if r['campaign_id'] == V2D)))
    reduced = trials(purposes['reduction'])
    reduction = reduction_context(get('reductions', counter.counterexample_id, ReductionResult), reduced,
                                  evidence([t.episode_id for t in reduced if t.lifecycle == 'COMPLETED']))
    diagnostic = get('diagnostics', next(r for r in store.list_records('diagnostic_campaigns') if r['campaign_id'] == V2D)['diagnostic_id'], DiagnosticResult)
    qualification = next(r for r in store.list_records('candidate_qualifications') if r['campaign_id'] == V2D)
    record = {k: qualification[k] for k in ('candidate_version', 'candidate_hash', 'candidate', 'qualification_ref')}
    batch = store.get_record('evaluations', qualification['source_validation_ref'])
    retest = evidence([t['episode_id'] for t in batch['trials'] if t['lifecycle'] == 'COMPLETED'])
    challenge = get('challenges', qualification['challenge_ref'], ChallengeResult)
    by_id = {}
    for raw in store.list_records('evaluations'):
        if raw['purpose'] == 'challenge' and (raw['candidate_hash'], raw['incumbent_hash']) == (challenge.candidate_hash, challenge.incumbent_hash):
            for t in raw['trials']: by_id[t['episode_id']] = TrialResult.model_validate_json(canonical_json(t))
    challenge_trials = list(by_id.values())
    schedules = [s['output']['fault_spec'] for s in (store.get_record('selections', ref) for ref in challenge.selection_refs)
                 if identity(FaultSpec.model_validate(s['output']['fault_spec'])) in challenge.schedule_hashes]
    return counter, {
        'campaign_id': V2D, 'source_context_id': qualification['source_context_id'], 'parent_version': incumbent.version,
        'target_invariant': counter.target_invariant, 'diagnostic': diagnostic.model_dump(mode='json'),
        'development_evidence': summarize_evidence(evidence([counter.source_episode_id, *counter.reproduction_trial_ids, *purposes['intervention']]) + retest),
        'candidate_history': [{**record, 'decision': qualification['decision'], 'source_validation_ref': batch['batch_id'],
                               'challenge_ref': challenge.challenge_id, 'classification': challenge.status}],
        'challenge_counterexamples': [{'challenge_id': challenge.challenge_id, **record, 'decision': qualification['decision'], 'status': challenge.status,
                                       'reason': challenge.stopping_reason, 'failed_checks': challenge.failed_checks, 'fault_spec': None, 'fixture_id': None,
                                       'tested_fault_specs': schedules, 'trial_outcomes': trial_outcomes(challenge_trials),
                                       'evidence': summarize_evidence(evidence([t.episode_id for t in challenge_trials if t.lifecycle == 'COMPLETED']))}],
        'source_validation_feedback': [{**store.get_record('source_validation_results', batch['batch_id']),
                                        'reason': 'Qualification requires three valid pairs: the incumbent still fails the target in all three, and every candidate has no check failure. Source flakiness and candidate violations are recorded separately.',
                                        'verified_episode_ids': [b.episode_id for b in retest]}],
        'runtime_contract': runtime_contract(store, campaign),
        'retained_fault_spec': store.get_record('retained_recipes', counter.counterexample_id)['retained_recipe'], 'reduction': reduction}


@pytest.mark.skipif(not SAVED_STORE.exists(), reason='Needs the saved v2d store (live run of 2026-09-30); absent on this machine')
def test_the_refused_v2d_request_rebuilds_exactly_and_fits_after_compaction_with_its_omission_statement(tmp_path):
    from app.lab.storage import ReadOnlyLabStore
    assert 'Desktop' not in str(tmp_path) and '/FaultLab_Runs/' not in str(tmp_path)
    copy = tmp_path / 'v2d-copy.sqlite3'
    source = sqlite3.connect(f'file:{SAVED_STORE}?mode=ro&immutable=1', uri=True); target = sqlite3.connect(copy)
    try:
        source.backup(target)
        target.execute('PRAGMA journal_mode=DELETE')   # the copy only, so a read-only open needs no -wal/-shm files
    finally:
        target.close(); source.close()
    try:
        store = ReadOnlyLabStore(copy)
        try:
            counter, context = rebuild_v2d_request(store)
            mechanic = SimpleNamespace(provider=SimpleNamespace(role_model=lambda role: 'deepseek-ai/DeepSeek-V4-Pro-0813'), metadata=None)
            bound = lambda value: loop_limits.mechanic_request_bound(mechanic, 'mechanic.md', TypeAdapter(MechanicOutput), value)
            full = bound(context)
            assert full == 33223                                  # the exact request live run v2d refused
            request, summary = compact_request(context, request_kind='mechanic_proposal', store=store, bound=bound, full_bound=full,
                                               protected_episode_ids=[counter.source_episode_id, *counter.reproduction_trial_ids])
            assert summary['fits'] and bound(request) == summary['compacted_tokens'] <= COMPACTION_TARGET_TOKENS
            # The builder's wording fitted at stage 2 by 10 tokens (27,990). The review fixes' clearer wording (rows can
            # differ from a group_example; VIOLATION outcomes kept) adds 66 tokens there, so v2d now fits at stage 3.
            assert [a['request_tokens'] for a in summary['attempts']] == [33611, 28056, 21101]
            statement = request['context_compaction']['statement']
            assert 'in full it was 33,223 input tokens' in statement and 'The observation, report and check rows of 24 clean episode(s) were omitted' in statement
            assert [(b['field'], b['episodes_total'], b['episodes_in_full'], b['episodes_omitted']) for b in summary['blocks']] == [
                ('development_evidence', 16, 10, 6), ('challenge_counterexamples[0].evidence', 18, 0, 18)]
            dev = request['development_evidence']
            assert kept(dev)[:4] == [counter.source_episode_id, *counter.reproduction_trial_ids] and len(kept(dev)) == 10
            failing = [row['episode_id'] for row in context['development_evidence']['episodes']
                       if any(c['passed'] is False for c in context['development_evidence']['checks'][row['check_row']])]
            assert len(failing) == 10 and set(failing) <= set(kept(dev))
            assert request['challenge_counterexamples'][0]['trial_outcomes'] == context['challenge_counterexamples'][0]['trial_outcomes']
        finally:
            store.close()
    finally:
        copy.unlink(missing_ok=True)
        assert not copy.exists()


# --------------------------------------------------------------------------- the learning loop: compacted, ended, never ERROR

def huge(episode, *, failed=()):
    """About 3,000 tokens of evidence per episode: 8 checks with 100 event ids each."""
    return bundle(episode, ['SUCCEEDED', 'PENDING'], failed=failed, events=100)


def asymmetric(episode, *, failed=()):
    """A failing episode is small; a clean one is large (so only compaction of clean rows can make room)."""
    return bundle(episode, ['PENDING'], failed=failed, events=0) if failed else bundle(episode, ['SUCCEEDED', 'PENDING', 'SUCCEEDED'], events=100)


def learning_loop(tmp_path, monkeypatch, outputs, *, declared=True, limit=None, target=None, evidence=huge, **options):
    """test_learning_qualification.loop() with the real Mechanic and a counting provider (no network)."""
    import app.lab.learning as learning
    from app.agents.mechanic import Mechanic
    from test_learning_qualification import loop
    c, campaign, runner, contexts, exports = loop(tmp_path, monkeypatch, [], **options)
    monkeypatch.setattr(learning, 'Mechanic', Mechanic)
    provider = Provider(outputs); runner.provider = provider
    class Evidence:
        async def get(self, episode_id, context, **kwargs):
            trial = c.store.get_record('trials', episode_id) or {}
            return evidence(episode_id, failed=tuple(trial.get('failed_checks') or ()))
    c.evidence_gateway = Evidence()
    monkeypatch.setattr(loop_limits, 'mechanic_context_rule', lambda store, campaign: mechanic_context_declaration() if declared else None)
    if limit is not None:
        # A scaled limit so small fixtures cross it; the same code path and the same frozen tokenizer.
        monkeypatch.setattr(tokens, 'MODEL_INPUT_TOKEN_LIMIT', limit); monkeypatch.setattr(loop_limits, 'MODEL_INPUT_TOKEN_LIMIT', limit)
        monkeypatch.setattr(loop_limits, 'COMPACTION_TARGET_TOKENS', target)
    return c, campaign, runner, provider


def candidate_json(op='require_receipt'):
    step = {'op': op, 'service': 'orders', 'status': 'SUCCEEDED'} if op == 'require_receipt' else {'op': op}
    return canonical_json({'candidate': {'parent_version': 'policy-v0', 'rules': [{'hook': 'before_confirmation', 'when': 'always', 'steps': [step]}]},
                           'explanation': 'Offline fixture proposal'})


NO_CHANGE = canonical_json({'no_change_reason': 'No further supported repair'})


def records(c): return c.store.list_records('mechanic_context_records')


@pytest.mark.anyio
async def test_an_over_limit_candidate_request_is_compacted_and_sent_and_the_campaign_goes_on(tmp_path, monkeypatch):
    from app.lab.learning import run_learning_cycle
    # Candidate 1 passes source validation and fails the challenge (a counterexample); candidate 2's request then carries
    # the challenge feedback and the source-validation evidence, whose 3 clean candidate-arm episodes are the only rows
    # compaction may omit. Scaled limit 9,000 (target 8,500): the first request fits, the second does not.
    c, campaign, runner, provider = learning_loop(tmp_path, monkeypatch, [candidate_json(), NO_CHANGE], limit=9000, target=8500,
                                                  evidence=asymmetric, challenge_failure=True)
    await run_learning_cycle(c, campaign, runner)
    assert c.get(campaign.campaign_id).state == 'NO_CHANGE'
    first, second = provider.sent                       # both requests were sent, each within the (scaled) limit
    assert first <= 9000 and second <= 8500
    compacted, = records(c)
    assert compacted['outcome'] == 'COMPACTED' and compacted['request_kind'] == 'mechanic_proposal' and compacted['provider_dispatch']
    assert compacted['full_request_tokens'] > 9000 and compacted['compacted_request_tokens'] == second
    assert compacted['blocks'][0]['field'] == 'development_evidence' and compacted['blocks'][0]['episodes_omitted'] >= 2
    assert compacted['candidate_index'] == 1 and compacted['statement'].startswith('This request was compacted under ' + MECHANIC_CONTEXT_V2)
    proposal = [p for p in c.store.list_records('campaign_proposals') if p.get('context_compaction_ref')]
    assert [p['context_compaction_ref'] for p in proposal] == [compacted['record_id']]


@pytest.mark.anyio
async def test_a_candidate_request_that_cannot_fit_ends_that_search_without_error_and_is_never_sent(tmp_path, monkeypatch):
    from app.lab.learning import run_learning_cycle
    c, campaign, runner, provider = learning_loop(tmp_path, monkeypatch, [], limit=6000, target=4000)
    await run_learning_cycle(c, campaign, runner)
    final = c.get(campaign.campaign_id)
    assert final.state == 'NO_CHANGE' and provider.sent == []          # nothing was sent, no ERROR
    ended, = records(c)
    assert ended['outcome'] == 'SEARCH_ENDED' and ended['stage'] == 'BEFORE_SEND' and ended['provider_dispatch'] is False
    assert ended['full_request_tokens'] > 6000 and 'Nothing was sent; the candidate search for this source ended here.' in ended['reason']
    assert not c.store.list_records('campaign_proposals') and not c.store.list_records('execution_errors')
    # Only the source (protected) is in the request, so no stage can omit anything.
    assert [a['episode_rows_omitted'] for a in ended['attempts']] == [0, 0, 0] and ended['candidate_index'] == 0


@pytest.mark.anyio
async def test_a_refused_format_repair_turn_ends_the_search_without_error(tmp_path, monkeypatch):
    from app.lab.learning import run_learning_cycle
    c, campaign, runner, provider = learning_loop(tmp_path, monkeypatch, ['not json'], limit=None)
    # The first turn fits the real limit; its invalid answer's repair turn is made to exceed it.
    original = tokens.validate_model_input
    def admit(messages, model):
        if len(messages) > 2: raise ModelInputLimit(40000)      # the format-repair turn
        return original(messages, model)
    import app.agents.mechanic as mechanic_module
    monkeypatch.setattr(mechanic_module, 'validate_model_input', admit)
    await run_learning_cycle(c, campaign, runner)
    assert c.get(campaign.campaign_id).state == 'NO_CHANGE' and len(provider.sent) == 1
    ended, = records(c)
    assert ended['stage'] == 'FORMAT_REPAIR' and ended['outcome'] == 'SEARCH_ENDED' and ended['format_repair_tokens'] == 40000
    assert 'the first turn was sent and its answer is saved' in ended['reason'] and not c.store.list_records('execution_errors')


@pytest.mark.anyio
async def test_a_refused_format_repair_turn_leaves_a_rejected_proposal_in_the_candidate_history(tmp_path, monkeypatch):
    """Product review LOW-3: the first turn was sent and charged, so it is a candidate attempt like an invalid answer:
    a REJECTED campaign_proposals row (with a rejected policy record) links its saved answer and the size record."""
    from app.lab.learning import run_learning_cycle
    c, campaign, runner, provider = learning_loop(tmp_path, monkeypatch, ['not json'], limit=None)
    original = tokens.validate_model_input
    def admit(messages, model):
        if len(messages) > 2: raise ModelInputLimit(40000)      # the format-repair turn
        return original(messages, model)
    import app.agents.mechanic as mechanic_module
    monkeypatch.setattr(mechanic_module, 'validate_model_input', admit)
    await run_learning_cycle(c, campaign, runner)
    ended, = records(c)
    proposal, = c.store.list_records('campaign_proposals')
    assert proposal['decision'] == 'REJECTED' and proposal['reason'] == 'FORMAT_REPAIR_OVER_LIMIT'
    assert proposal['raw_outputs'] == ['not json'] and proposal['mechanic_context_ref'] == ended['record_id']
    first = c.store.get_record('mechanic_outputs', proposal['proposal_ref'])
    assert first['raw'] == 'not json' and first['attempt'] == 0 and ended['first_turn_output_ref'] == proposal['proposal_ref']
    assert c.policies.get(proposal['candidate_version']).decision == 'REJECTED'


@pytest.mark.anyio
@pytest.mark.parametrize('request_kind', ['mechanic_proposal', 'mechanic_diagnosis'])
async def test_a_first_turn_the_mechanic_itself_refuses_is_recorded_as_never_sent(tmp_path, monkeypatch, request_kind):
    """Integrity review LOW-3: a refusal is recorded as FORMAT_REPAIR ("the first turn was sent") only when this request's
    first-turn answer is actually saved. If the Mechanic's own check refuses the first turn, nothing was sent: the record
    says so (BEFORE_SEND), and an unsent candidate request does not use one of the campaign's candidate requests."""
    import app.agents.mechanic as mechanic_module
    import app.lab.learning as learning
    from app.lab.diagnosis import Diagnostician
    from app.lab.learning import run_learning_cycle
    c, campaign, runner, provider = learning_loop(tmp_path, monkeypatch, [], limit=None)
    if request_kind == 'mechanic_diagnosis':
        monkeypatch.setattr(learning, 'Diagnostician', Diagnostician)          # the real one, with the bounded Mechanic
    campaign.caps.discovery_selections = 2; campaign.caps.candidates = 1; c.save(campaign)
    def refuse(messages, model): raise ModelInputLimit(40000)                 # every turn, the first included
    monkeypatch.setattr(mechanic_module, 'validate_model_input', refuse)
    await run_learning_cycle(c, campaign, runner)
    assert c.get(campaign.campaign_id).state == 'NO_CHANGE' and provider.sent == []
    ended = records(c)
    assert [(r['request_kind'], r['stage'], r['provider_dispatch']) for r in ended] == [(request_kind, 'BEFORE_SEND', False)] * 2
    assert all('first turn was sent' not in r['reason'] and 'Nothing was sent' in r['reason'] for r in ended)
    assert not c.store.list_records('campaign_proposals') and not c.store.list_records('mechanic_outputs')


@pytest.mark.anyio
async def test_a_search_cut_short_by_the_size_rule_is_named_in_the_campaigns_final_reason(tmp_path, monkeypatch):
    """Integrity review LOW-3: NO_CHANGE after a search that the size rule ended must not read like a finished search."""
    from app.lab.learning import run_learning_cycle
    c, campaign, runner, provider = learning_loop(tmp_path, monkeypatch, [], limit=6000, target=4000)
    await run_learning_cycle(c, campaign, runner)
    final = c.get(campaign.campaign_id); ended, = records(c)
    assert final.state == 'NO_CHANGE'
    assert final.terminal_reason.startswith('No verified strict improvement within declared development bounds; all outcomes retained')
    assert ('1 candidate or diagnosis search ended before it finished under ' + MECHANIC_CONTEXT_V2) in final.terminal_reason
    assert ended['record_id'] in final.terminal_reason
    # A campaign whose searches all finished keeps exactly today's reason (real limit: undo the scaled one first).
    monkeypatch.undo()
    (tmp_path / 'fits').mkdir()
    other = learning_loop(tmp_path / 'fits', monkeypatch, [NO_CHANGE], limit=None)
    await run_learning_cycle(other[0], other[1], other[2])
    assert other[0].get(other[1].campaign_id).terminal_reason == 'No verified strict improvement within declared development bounds; all outcomes retained'


@pytest.mark.anyio
async def test_a_plan_saved_before_the_rule_keeps_todays_behaviour(tmp_path, monkeypatch):
    from app.lab.learning import run_learning_cycle
    c, campaign, runner, provider = learning_loop(tmp_path, monkeypatch, [], declared=False, limit=6000, target=4000)
    with pytest.raises(ModelInputLimit):
        await run_learning_cycle(c, campaign, runner)           # the coordinator records this as ERROR (INPUT_LIMIT), as in v2d
    assert provider.sent == [] and not records(c)


@pytest.mark.anyio
async def test_an_over_limit_diagnosis_request_skips_that_source_without_error_and_is_never_sent(tmp_path, monkeypatch):
    import app.lab.learning as learning
    from app.lab.diagnosis import Diagnostician
    from app.lab.learning import run_learning_cycle
    c, campaign, runner, provider = learning_loop(tmp_path, monkeypatch, [], limit=6000, target=4000)
    monkeypatch.setattr(learning, 'Diagnostician', Diagnostician)          # the real one, with the bounded Mechanic
    await run_learning_cycle(c, campaign, runner)
    assert c.get(campaign.campaign_id).state == 'NO_CHANGE' and provider.sent == []
    ended, = records(c)
    assert ended['request_kind'] == 'mechanic_diagnosis' and ended['outcome'] == 'SEARCH_ENDED' and not ended['provider_dispatch']
    assert 'the diagnosis and candidate search for this source ended here' in ended['reason']
    assert not c.store.list_records('diagnostics') and not c.store.list_records('execution_errors')


@pytest.mark.anyio
async def test_an_unsent_candidate_request_does_not_use_one_of_the_campaigns_candidate_requests(tmp_path, monkeypatch):
    """With one candidate request allowed and two discovery slots: the first source's request cannot fit and is never
    sent, so the second slot still runs (the unused request is not counted)."""
    from app.lab.learning import run_learning_cycle
    c, campaign, runner, provider = learning_loop(tmp_path, monkeypatch, [], limit=6000, target=4000)
    campaign.caps.discovery_selections = 2; campaign.caps.candidates = 1; c.save(campaign)
    await run_learning_cycle(c, campaign, runner)
    discovery = [call for call in runner.calls if call[3].get('purpose') == 'discovery']
    assert len(discovery) == 2 and provider.sent == [] and c.get(campaign.campaign_id).state == 'NO_CHANGE'
    assert [r['outcome'] for r in records(c)] == ['SEARCH_ENDED', 'SEARCH_ENDED']

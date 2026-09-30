"""faultlab-mechanic-evidence/v2-native-citation-status (app.lab.citation_status): for a native adapter v2 Learn plan, each
Mechanic diagnosis or candidate request and each challenge Explorer request that carries episode evidence gets the
adapter's recorded per-episode citation outcome, read only from report_submitted events. Every other plan's requests
are unchanged. $0 and offline: no provider, W&B or Weave call; the saved-store tests copy the store read-only to a
temporary directory outside the Desktop and delete the copy.

Live runs v2d and v2e (September 30): the diagnosis Mechanic twice claimed that the agent cited labels it had never been
shown, although in all 8 diagnosed episodes every cited label was shown and decoded.
"""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts.models import canonical_json
from app.lab import citation_status, loop_limits
from app.lab.citation_status import (BLOCK, MECHANIC_EVIDENCE_V2, MEANING, MEMORY_POINTER, ROW_FIELDS, V2_MEMORY_WITH_CITATION_STATUS,
                                     attach, declaration)
from app.lab.diagnosis import V2_MEMORY, summarize_evidence
from app.lab.loop_limits import mechanic_context_declaration
from app.lab.storage import LabStore, StoreConflict
from app.providers.runtime import RuntimeGeneration
from test_loop_limits_mechanic_context import bundle

import citation_status_saved as saved

V21 = 'faultlab-native-adapter/v2.1-shown-order-labels'


@pytest.fixture
def anyio_backend(): return 'asyncio'


def register(store, episode_id, campaign_id='campaign-x'):
    with store.transaction() as db:
        db.execute('INSERT OR IGNORE INTO episode_registry(id,campaign_id) VALUES(?,?)', (episode_id, campaign_id))


def report_event(store, episode_id, cited, shown, *, protocol=V21, campaign_id='campaign-x'):
    """A report_submitted event exactly as native adapter v2.1 records it (external_agent_v2._final_answer)."""
    register(store, episode_id, campaign_id)
    labels = {label: f'evidence-{episode_id}-{label}' for label in shown}
    payload = {'report': {}, 'adapter_entrypoint_id': 'smolagents-toolcalling-v2', 'citation_protocol': protocol,
               'cited_evidence_tokens': cited, 'decoded_evidence_ids': [labels.get(token, token) for token in cited],
               'evidence_labels': {evidence_id: label for label, evidence_id in labels.items()}, 'labels_shown_to_agent': list(shown),
               'cited_tokens_not_decoded': [token for token in cited if token not in labels], 'final_report_required': False,
               'response_contract': None}
    if protocol is None: payload = {'report': {}}                     # native adapter v1 records the report only
    store.append_event(episode_id, role='actor', type='report_submitted', payload=payload)


def v2_contract(store=None, campaign=None):
    return {'actor_contract': {'implementation': 'fixture: native adapter v2', 'memory': V2_MEMORY}, 'episode_limits': {'actor_calls': 8}}


# --------------------------------------------------------------------------- one row per episode, from the event only

def test_a_row_is_the_adapters_recorded_citation_outcome_and_an_undecoded_token_is_shown(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    report_event(store, 'e-all', ['obs-1', 'obs-2', 'obs-3'], ['obs-1', 'obs-2', 'obs-3', 'obs-4'])
    report_event(store, 'e-gap', ['obs-1', 'obs-7', 'evidence-0123456789abcdef0123456789abcdef'], ['obs-1', 'obs-2'])
    report_event(store, 'e-v1', ['evidence-1'], [], protocol=None)
    register(store, 'e-none')                                          # no report was submitted
    rows = citation_status.block(store, ['e-all', 'e-gap', 'e-v1', 'e-none'])['episodes']
    assert rows == [
        {'episode_id': 'e-all', 'cited': 3, 'decoded': 3, 'undecoded': []},
        {'episode_id': 'e-gap', 'cited': 3, 'decoded': 1, 'undecoded': ['obs-7', 'evidence-0123456789abcdef0123456789abcdef']},
        {'episode_id': 'e-v1', 'cited': None, 'decoded': None, 'undecoded': None},     # no v2.1 citation record: nothing guessed
        {'episode_id': 'e-none', 'cited': None, 'decoded': None, 'undecoded': None}]
    assert all(tuple(row) == ROW_FIELDS for row in rows)


def test_nothing_is_read_from_scoring(tmp_path):
    """The rows come from the report_submitted event alone: trial outcomes, failed checks and verdicts change nothing."""
    store = LabStore(tmp_path / 'lab.db')
    report_event(store, 'e1', ['obs-1', 'obs-2'], ['obs-1', 'obs-2'])
    before = citation_status.block(store, ['e1'])
    store.put_record('trials', 'e1', {'episode_id': 'e1', 'outcome': 'VIOLATION', 'failed_checks': ['C5', 'C6']})
    store.append_event('e1', role='referee', type='verdict_recorded', payload={'failed_checks': ['C5', 'C6']}, visibility='PRIVATE_EVALUATOR')
    store.append_event('e1', role='actor', type='report_submitted', payload={'report': {}, 'citation_protocol': V21}, visibility='PRIVATE_EVALUATOR')
    assert citation_status.block(store, ['e1']) == before
    # The one sentence says what the block means and nothing about checks, failures or scores.
    for text in (MEANING, MEMORY_POINTER):
        assert text.endswith('.') and text.count('. ') == 0
        assert not any(word in text.lower() for word in ('check', 'fail', 'violat', 'verdict', 'scor', 'truthful', 'invariant', 'c5', 'c6'))


def test_the_last_report_is_used_and_events_are_read_past_one_page(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    report_event(store, 'e1', ['obs-1'], ['obs-1'])                     # an earlier report (the adapter records one; this is a guard)
    for index in range(205): store.append_event('e1', tick=index % 20, type='observation_delivered', payload={})
    report_event(store, 'e1', ['obs-1', 'obs-9'], ['obs-1'])
    assert citation_status.block(store, ['e1'])['episodes'] == [{'episode_id': 'e1', 'cited': 2, 'decoded': 1, 'undecoded': ['obs-9']}]


def test_the_meaning_sentence_describes_every_null_row(tmp_path):
    """Fixer, review finding LOW-4: a row is null not only when no report was submitted, but also when a submitted report
    carries no v2.1 citation record, or an incomplete one. The sentence the Mechanic reads must not say 'no submitted report
    was recorded' next to evidence that shows a report."""
    store = LabStore(tmp_path / 'lab.db')
    report_event(store, 'e-v1', ['evidence-1'], [], protocol=None)                          # a report, no v2.1 record
    register(store, 'e-short')
    store.append_event('e-short', role='actor', type='report_submitted',                  # a v2.1 record missing a list
                       payload={'report': {}, 'citation_protocol': V21, 'cited_evidence_tokens': ['obs-1']})
    for episode in ('e-v1', 'e-short'):
        assert citation_status.submitted_report(store, episode) is not None                # a report WAS recorded
        assert citation_status.block(store, [episode])['episodes'] == [
            {'episode_id': episode, 'cited': None, 'decoded': None, 'undecoded': None}]
    assert 'no submitted report was recorded' not in MEANING
    assert MEANING.endswith('(all three are null when no complete native adapter v2.1 citation record was recorded for '
                            'that episode).')
    assert declaration()['meaning'] == MEANING


# --------------------------------------------------------------------------- where the block goes

def summary(*episodes):
    return summarize_evidence([bundle(e, ['SUCCEEDED']) for e in episodes])


def test_each_request_kind_gets_one_block_in_evidence_order_and_mechanic_requests_get_the_memory_pointer(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    for episode in ('s', 'r1', 'v1', 'c1', 'c2'): report_event(store, episode, ['obs-1'], ['obs-1'])
    diagnosis = {'observations': summary('s', 'r1'), 'runtime_contract': v2_contract(), 'evidence_ids': ['x']}
    got = attach(store, diagnosis, request_kind='mechanic_diagnosis')
    assert [r['episode_id'] for r in got[BLOCK]['episodes']] == ['s', 'r1'] and got[BLOCK]['meaning'] == MEANING
    assert got[BLOCK]['protocol'] == MECHANIC_EVIDENCE_V2
    assert got['runtime_contract']['actor_contract']['memory'] == V2_MEMORY_WITH_CITATION_STATUS == V2_MEMORY + ' ' + MEMORY_POINTER
    assert {k: v for k, v in got.items() if k not in (BLOCK, 'runtime_contract')} == {k: v for k, v in diagnosis.items() if k != 'runtime_contract'}
    assert diagnosis['runtime_contract']['actor_contract']['memory'] == V2_MEMORY          # the caller's context is not changed
    proposal = {'development_evidence': summary('s', 'r1', 'v1'), 'runtime_contract': v2_contract(),
                'challenge_counterexamples': [{'evidence': summary('c1', 's')}, {'evidence': summary('c2')}]}
    got = attach(store, proposal, request_kind='mechanic_proposal')
    assert [r['episode_id'] for r in got[BLOCK]['episodes']] == ['s', 'r1', 'v1', 'c1', 'c2']   # first listing order, once each
    challenge = {'development_evidence': summary('v1'), 'purpose': 'challenge'}
    got = attach(store, challenge, request_kind='explorer_challenge')
    assert [r['episode_id'] for r in got[BLOCK]['episodes']] == ['v1'] and 'runtime_contract' not in got


def test_a_request_without_episode_evidence_is_unchanged_and_other_memory_texts_are_refused(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    empty = {'development_evidence': [], 'purpose': 'challenge'}                 # the Challenger's value without evidence
    assert attach(store, empty, request_kind='explorer_challenge') is empty
    no_rows = {'observations': summary(), 'runtime_contract': v2_contract()}
    assert attach(store, no_rows, request_kind='mechanic_diagnosis') is no_rows
    register(store, 's')
    reference = {'observations': summary('s'), 'runtime_contract': {'actor_contract': 'the reference Actor prompt'}}
    with pytest.raises(RuntimeError, match='native adapter v2 runtime contract'):
        attach(store, reference, request_kind='mechanic_diagnosis')


@pytest.mark.anyio
async def test_the_wrappers_add_the_block_only_to_diagnosis_and_challenge_requests(tmp_path):
    store = LabStore(tmp_path / 'lab.db'); report_event(store, 's', ['obs-1'], ['obs-1'])
    class Inner:
        def __init__(self): self.seen = []; self.marker = 'inner'
        async def select(self, context, **kwargs): self.seen.append((kwargs, context)); return 'ref', None
        async def diagnose(self, context, **kwargs): self.seen.append((kwargs, context)); return 'ref', None, []
    inner = Inner(); explorer = citation_status.CitationStatusExplorer(inner, store)
    discovery = {'development_history': [], 'development_evidence': summary('s'), 'runtime_contract': v2_contract()}
    await explorer.select(discovery, fallback=None)
    await explorer.select({'development_evidence': summary('s')}, challenge=True, reservation='r')
    (first_kwargs, first), (second_kwargs, second) = inner.seen
    assert first is discovery and first_kwargs == {'challenge': False, 'fallback': None}          # discovery: the same object
    assert BLOCK in second and second_kwargs == {'challenge': True, 'reservation': 'r'} and explorer.marker == 'inner'
    inner.seen.clear(); mechanic = citation_status.CitationStatusMechanic(inner, store)
    await mechanic.diagnose({'observations': summary('s'), 'runtime_contract': v2_contract()}, reservation='d')
    (kwargs, context), = inner.seen
    assert kwargs == {'reservation': 'd'} and BLOCK in context


# --------------------------------------------------------------------------- the plan: new native v2 Learn plans only

from test_discovery_v2_flow import learn_campaign, owner, request  # noqa: E402,F401  (owner is a fixture)
from app.lab.operator_actions import register_agent  # noqa: E402
from app.lab.run_plans import MechanicEvidencePlan, build_run_options, prepare_run_plan, read_run_plan, validate_run_plan  # noqa: E402


def test_only_a_new_native_v2_learn_plan_declares_it(owner):
    assert build_run_options(owner.settings, owner.store)['learn']['mechanic_evidence'] == declaration()
    for agent, declared in (('reference', False), ('smolagents', False), ('smolagents-v2', True)):
        campaign = learn_campaign(owner, None, agent)
        plan = read_run_plan(owner.store, campaign)['plan']
        assert ('mechanic_evidence' in plan) is declared and (plan.get('mechanic_evidence') == declaration()) is declared
        assert plan['mechanic_context'] == mechanic_context_declaration()
        assert validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id)) == plan
        assert citation_status.campaign_rule(owner.store, campaign) == (declaration() if declared else None)
    registration = register_agent(owner.store, owner.settings, 'smolagents-v2')
    baseline = prepare_run_plan(owner.store, owner.settings, request(owner, registration, mode='baseline', development_case_id='dev-5'))
    assert 'mechanic_evidence' not in baseline.plan


def test_a_native_v2_plan_saved_before_the_rule_keeps_its_bytes_and_starts(owner):
    registration = register_agent(owner.store, owner.settings, 'smolagents-v2')
    prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration))
    prepared.plan.pop('mechanic_evidence')                                  # exactly as the runtime before the rule saved it
    older = owner.create(prepared.campaign_request, run_plan=prepared)
    saved_plan = owner.store.get_record('campaign_plans', older.campaign_id)
    assert 'mechanic_evidence' not in saved_plan and read_run_plan(owner.store, older)['plan'] == saved_plan   # no null key
    assert validate_run_plan(owner.store, owner.settings, owner.get(older.campaign_id)) == saved_plan
    assert citation_status.campaign_rule(owner.store, older) is None


def test_start_refuses_another_rule_text_and_other_agents_or_modes_cannot_declare_it(owner, monkeypatch):
    from app.lab import run_plans
    registration = register_agent(owner.store, owner.settings, 'smolagents-v2')
    prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration))
    prepared.plan['mechanic_evidence'] = {**declaration(), 'rule': 'An older wording of the rule.'}
    monkeypatch.setattr(run_plans, 'validate_run_plan', lambda *args, **kwargs: None)
    campaign = owner.create(prepared.campaign_request, run_plan=prepared)
    monkeypatch.undo()
    with pytest.raises(StoreConflict, match='native citation-status rule differs'):
        validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))
    reference = prepare_run_plan(owner.store, owner.settings, request(owner, register_agent(owner.store, owner.settings, 'reference')))
    reference.plan['mechanic_evidence'] = declaration()
    with pytest.raises(StoreConflict, match='Only a Learn plan of native adapter v2'):
        owner.create(reference.campaign_request, run_plan=reference)
    baseline = prepare_run_plan(owner.store, owner.settings, request(owner, registration, mode='baseline', development_case_id='dev-1'))
    baseline.plan['mechanic_evidence'] = declaration()
    with pytest.raises(StoreConflict, match='Only a Learn plan of native adapter v2'):
        owner.create(baseline.campaign_request, run_plan=baseline)
    MechanicEvidencePlan.model_validate(declaration())
    for change in ({'reads_scoring': True}, {'compacted': True}, {'discovery_requests_changed': True}, {'agents': ['smolagents']},
                   {'applies_to': ['mechanic_proposal', 'mechanic_diagnosis', 'explorer_challenge']}, {'row_fields': ['episode_id', 'cited', 'decoded', 'failed']},
                   {'protocol': 'faultlab-mechanic-evidence/v1'}, {'source_protocol': 'faultlab-native-adapter/v2-shown-labels-final-turn'}):
        with pytest.raises(ValidationError):
            MechanicEvidencePlan.model_validate({**declaration(), **change})


def test_the_declared_source_protocol_is_the_installed_adapters():
    from app.integrations.external_agent_v2 import PROTOCOL_VERSION
    assert citation_status.SOURCE_PROTOCOL == PROTOCOL_VERSION


# --------------------------------------------------------------------------- the learning loop

class Provider:
    """Keeps every request's messages; answers with scripted outputs (a callable gets the messages). No network."""
    def __init__(self, outputs, model='openai/gpt-oss-120b'):
        self.outputs = list(outputs); self.requests = []; self.model = model
    def role_model(self, role): return self.model
    async def complete(self, messages, **kwargs):
        self.requests.append(json.loads(canonical_json(messages)))
        output = self.outputs.pop(0)
        return RuntimeGeneration(output(messages) if callable(output) else output, self.model, input_tokens=100, output_tokens=20)


def diagnosis_answer(messages):
    context = json.loads(messages[-1]['content'])
    return canonical_json({'proposed_kind': 'INCONCLUSIVE', 'hypothesis': 'Offline fixture diagnosis',
                           'evidence_ids': context['evidence_ids'][:1], 'requested_intervention_id': None})


def native_loop(tmp_path, monkeypatch, outputs, *, declared=True, real_diagnosis=False, **options):
    """test_learning_qualification.loop() with the real Mechanic, a message-keeping provider, a context-keeping Explorer
    double, native v2 report events for every episode whose evidence is read, and the v2 runtime contract."""
    import app.lab.diagnosis as diagnosis
    import app.lab.learning as learning
    from app.agents.mechanic import Mechanic
    from test_learning_qualification import loop
    c, campaign, runner, _, _ = loop(tmp_path, monkeypatch, [], **options)
    monkeypatch.setattr(learning, 'Mechanic', Mechanic)
    if real_diagnosis: monkeypatch.setattr(learning, 'Diagnostician', diagnosis.Diagnostician)
    provider = Provider(outputs); runner.provider = provider
    explorer_contexts = []
    base = learning.Explorer
    class Explorer(base):
        async def select(self, context, **kwargs):
            explorer_contexts.append((bool(kwargs.get('challenge')), json.loads(canonical_json(context))))
            return await super().select(context, **kwargs)
    monkeypatch.setattr(learning, 'Explorer', Explorer)
    class Evidence:
        async def get(self, episode_id, context, **kwargs):
            if not c.store.events(episode_id)['events']:
                report_event(c.store, episode_id, ['obs-1', 'obs-2'], ['obs-1', 'obs-2'], campaign_id=campaign.campaign_id)
            trial = c.store.get_record('trials', episode_id) or {}
            return bundle(episode_id, ['SUCCEEDED', 'PENDING'], failed=tuple(trial.get('failed_checks') or ()))
    c.evidence_gateway = Evidence()
    monkeypatch.setattr(learning, 'runtime_contract', v2_contract); monkeypatch.setattr(diagnosis, 'runtime_contract', v2_contract)
    monkeypatch.setattr(loop_limits, 'mechanic_context_rule', lambda store, campaign: mechanic_context_declaration())
    monkeypatch.setattr(citation_status, 'campaign_rule', lambda store, campaign: declaration() if declared else None)
    return c, campaign, runner, provider, explorer_contexts


def requests_of(provider, prompt_start):
    return [json.loads(messages[-1]['content']) for messages in provider.requests if messages[0]['content'].startswith(prompt_start)]


def candidate_json():
    return canonical_json({'candidate': {'parent_version': 'policy-v0', 'rules': [{'hook': 'before_confirmation', 'when': 'always',
                           'steps': [{'op': 'require_receipt', 'service': 'orders', 'status': 'SUCCEEDED'}]}]}, 'explanation': 'Offline fixture'})


NO_CHANGE = canonical_json({'no_change_reason': 'No further supported repair'})


@pytest.mark.anyio
async def test_a_native_v2_campaign_sends_the_block_in_candidate_and_challenge_requests_but_not_discovery(tmp_path, monkeypatch):
    from app.agents.mechanic import PROMPTS
    from app.lab.learning import run_learning_cycle
    c, campaign, runner, provider, explorer_contexts = native_loop(tmp_path, monkeypatch, [candidate_json(), NO_CHANGE], challenge_failure=True)
    await run_learning_cycle(c, campaign, runner)
    first, second = requests_of(provider, (PROMPTS / 'mechanic.md').read_text()[:200])
    for request in (first, second):
        rows = request[BLOCK]['episodes']
        listed = [row['episode_id'] for row in request['development_evidence']['episodes']]
        for item in request['challenge_counterexamples']: listed += [row['episode_id'] for row in item['evidence']['episodes']]
        assert [row['episode_id'] for row in rows] == list(dict.fromkeys(listed))
        assert all(row['cited'] == row['decoded'] == 2 and row['undecoded'] == [] for row in rows)
        assert request['runtime_contract']['actor_contract']['memory'] == V2_MEMORY_WITH_CITATION_STATUS
    assert len(second[BLOCK]['episodes']) > len(first[BLOCK]['episodes'])     # the challenge episodes joined
    discovery = [context for challenge, context in explorer_contexts if not challenge]
    challenge = [context for challenge, context in explorer_contexts if challenge]
    assert discovery and challenge
    assert all(BLOCK not in context and context['runtime_contract']['actor_contract']['memory'] == V2_MEMORY for context in discovery)
    for context in challenge:
        assert [row['episode_id'] for row in context[BLOCK]['episodes']] == [row['episode_id'] for row in context['development_evidence']['episodes']]


@pytest.mark.anyio
async def test_a_native_v2_diagnosis_request_carries_the_block_and_the_size_rule_counts_it(tmp_path, monkeypatch):
    from app.agents.mechanic import PROMPTS
    from app.contracts import tokens
    from app.lab.learning import run_learning_cycle
    c, campaign, runner, provider, _ = native_loop(tmp_path, monkeypatch, [diagnosis_answer], real_diagnosis=True)
    await run_learning_cycle(c, campaign, runner)
    request, = requests_of(provider, (PROMPTS / 'diagnosis.md').read_text()[:200])
    assert [row['episode_id'] for row in request[BLOCK]['episodes']] == [request['observations']['episodes'][0]['episode_id']]
    assert request['runtime_contract']['actor_contract']['memory'] == V2_MEMORY_WITH_CITATION_STATUS
    # With a scaled limit the size rule's recorded full size is the request WITH the block (it is added first).
    (tmp_path / 'scaled').mkdir(); monkeypatch.undo()
    c, campaign, runner, provider, _ = native_loop(tmp_path / 'scaled', monkeypatch, [], real_diagnosis=True)
    monkeypatch.setattr(tokens, 'MODEL_INPUT_TOKEN_LIMIT', 1000); monkeypatch.setattr(loop_limits, 'MODEL_INPUT_TOKEN_LIMIT', 1000)
    monkeypatch.setattr(loop_limits, 'COMPACTION_TARGET_TOKENS', 900)
    seen = []
    original = loop_limits.fit_request
    def fit(store, mechanic, context, **kwargs):
        seen.append(context); return original(store, mechanic, context, **kwargs)
    monkeypatch.setattr(loop_limits, 'fit_request', fit)
    await run_learning_cycle(c, campaign, runner)
    record, = c.store.list_records('mechanic_context_records')
    assert BLOCK in seen[0] and record['request_kind'] == 'mechanic_diagnosis' and provider.requests == []
    from pydantic import TypeAdapter
    from app.contracts.models import DiagnosticProposal
    from types import SimpleNamespace
    assert record['full_request_tokens'] == loop_limits.mechanic_request_bound(SimpleNamespace(provider=provider, metadata=None), 'diagnosis.md',
                                                                               TypeAdapter(DiagnosticProposal), seen[0])


@pytest.mark.anyio
async def test_a_candidate_request_gets_the_block_before_the_size_rule_counts_it(tmp_path, monkeypatch):
    """Scaled limit: the first candidate request is just over it, so the size rule records its full size; that size is
    the request WITH the block."""
    from types import SimpleNamespace
    from pydantic import TypeAdapter
    from app.contracts import tokens
    from app.contracts.models import MechanicOutput
    from app.lab.learning import run_learning_cycle
    c, campaign, runner, provider, _ = native_loop(tmp_path, monkeypatch, [NO_CHANGE])
    seen = []
    original = loop_limits.fit_request
    def fit(store, mechanic, context, **kwargs):
        seen.append(context); return original(store, mechanic, context, **kwargs)
    monkeypatch.setattr(loop_limits, 'fit_request', fit)
    bound = lambda value: loop_limits.mechanic_request_bound(SimpleNamespace(provider=provider, metadata=None), 'mechanic.md', TypeAdapter(MechanicOutput), value)
    limit = 0
    def scaled(store, mechanic, context, **kwargs):
        nonlocal limit
        limit = bound(context) - 1                                      # just over the limit with the block
        monkeypatch.setattr(tokens, 'MODEL_INPUT_TOKEN_LIMIT', limit); monkeypatch.setattr(loop_limits, 'MODEL_INPUT_TOKEN_LIMIT', limit)
        monkeypatch.setattr(loop_limits, 'COMPACTION_TARGET_TOKENS', limit)
        return fit(store, mechanic, context, **kwargs)
    monkeypatch.setattr(loop_limits, 'fit_request', scaled)
    await run_learning_cycle(c, campaign, runner)
    record, = c.store.list_records('mechanic_context_records')
    assert BLOCK in seen[0] and record['request_kind'] == 'mechanic_proposal'
    assert record['full_request_tokens'] == bound(seen[0]) == limit + 1
    # Only the (protected) source is in this request, so nothing can be omitted: the search ends and nothing is sent.
    assert record['outcome'] == 'SEARCH_ENDED' and provider.requests == []


@pytest.mark.anyio
async def test_without_the_rule_the_loop_never_runs_the_citation_code(tmp_path, monkeypatch):
    """A plan without the rule (every older plan, every other agent): no wrapper, no attach, and no block anywhere."""
    from app.lab.learning import run_learning_cycle
    c, campaign, runner, provider, explorer_contexts = native_loop(tmp_path, monkeypatch, [candidate_json(), NO_CHANGE], declared=False,
                                                                   challenge_failure=True)
    def forbidden(*args, **kwargs): raise AssertionError('citation-status code ran for a plan without the rule')
    for name in ('attach', 'block', 'CitationStatusMechanic', 'CitationStatusExplorer'):
        monkeypatch.setattr(citation_status, name, forbidden)
    await run_learning_cycle(c, campaign, runner)
    assert len(provider.requests) == 2 and explorer_contexts
    assert all(BLOCK not in json.loads(messages[-1]['content']) for messages in provider.requests)
    assert all(BLOCK not in context for _, context in explorer_contexts)
    assert all(json.loads(messages[-1]['content'])['runtime_contract']['actor_contract']['memory'] == V2_MEMORY for messages in provider.requests)


# --------------------------------------------------------------------------- the saved store: v2e's and v2d's real requests

SAVED = Path(saved.SAVED_STORE)
needs_store = pytest.mark.skipif(not SAVED.exists(), reason='Needs the saved v2b store (live runs v2d, v2e of 2026-09-30); absent on this machine')


@pytest.fixture
def store_copy(tmp_path):
    assert 'Desktop' not in str(tmp_path) and '/FaultLab_Runs/' not in str(tmp_path)
    target = tmp_path / 'lab' / 'lab.sqlite3'; target.parent.mkdir()
    saved.copy_read_only(SAVED, target)
    try: yield target
    finally: assert saved.remove_copy(target)


@needs_store
@pytest.mark.anyio
async def test_a_new_native_v2_plan_on_a_copy_of_the_v2e_store_gets_the_block_with_zero_undecoded_for_every_diagnosed_episode(store_copy):
    import asyncio
    from app.config import Settings
    from app.lab.coordinator import LabCoordinator
    from app.lab.diagnosis import Diagnostician
    from test_discovery_v2_flow import EXPLORER_MODEL
    # A new Learn plan for the native v2 agent, made in the copy exactly as the product makes one (register, plan, create).
    owner = LabCoordinator(Settings(faultlab_artifact_dir=str(store_copy.parent), wandb_model='deepseek-ai/DeepSeek-V3.1',
                                    wandb_explorer_model=EXPLORER_MODEL, wandb_mechanic_model=saved.MECHANIC_MODEL))
    try:
        registration = register_agent(owner.store, owner.settings, 'smolagents-v2')
        prepared = prepare_run_plan(owner.store, owner.settings, request(owner, registration, discovery_protocol='faultlab-discovery/v4-history-replay'))
        campaign = owner.create(prepared.campaign_request, run_plan=prepared)
        rule = citation_status.campaign_rule(owner.store, campaign)
        assert rule == declaration()
        # v2e's own plan (saved before the rule) declares nothing, so its requests stay as they were.
        v2e = owner.store.get_model('campaigns', saved.V2E, type(campaign))
        assert citation_status.campaign_rule(owner.store, v2e) is None
        # v2e's diagnosis inputs, handed to the real Diagnostician under the new plan, as the loop would (the rule wraps it).
        _, counter, retained, incumbent, reproduction, evidence, reduction = saved.diagnosis_inputs(owner.store, saved.V2E)
        contexts = {}
        for name, wrap in (('plain', None), ('rule', (lambda m: citation_status.CitationStatusMechanic(m, owner.store)) if rule else None)):
            capture = saved.CaptureMechanic()
            with pytest.raises(saved.Captured):
                await Diagnostician(owner.store, None, None, wrap(capture) if wrap else capture).run(
                    campaign, counter, retained, incumbent, reproduction, evidence=evidence, reduction=reduction)
            contexts[name], = capture.contexts
        plain, got = contexts['plain'], contexts['rule']
        rows = got[BLOCK]['episodes']
        assert [row['episode_id'] for row in rows] == [counter.source_episode_id, *counter.reproduction_trial_ids]
        assert [(row['cited'], row['decoded'], row['undecoded']) for row in rows] == [(5, 5, []), (5, 5, []), (6, 6, []), (6, 6, [])]
        assert got['runtime_contract']['actor_contract']['memory'] == V2_MEMORY_WITH_CITATION_STATUS
        assert plain['runtime_contract']['actor_contract']['memory'] == V2_MEMORY
        assert ({k: v for k, v in got.items() if k not in (BLOCK, 'runtime_contract')} == {k: v for k, v in plain.items() if k != 'runtime_contract'})
        mechanic = type('M', (), {'provider': type('P', (), {'role_model': staticmethod(lambda role: saved.MECHANIC_MODEL)})(), 'metadata': None})()
        from pydantic import TypeAdapter
        from app.contracts.models import DiagnosticProposal
        size = lambda value: loop_limits.mechanic_request_bound(mechanic, 'diagnosis.md', TypeAdapter(DiagnosticProposal), value)
        assert size(got) - size(plain) <= 400 and size(got) <= loop_limits.COMPACTION_TARGET_TOKENS     # small; no compaction needed
    finally:
        await owner.close()


@needs_store
@pytest.mark.anyio
async def test_the_v2e_and_v2d_diagnosis_requests_rebuild_exactly_and_all_8_diagnosed_episodes_decoded_every_citation(store_copy):
    from pydantic import TypeAdapter
    from app.contracts.models import DiagnosticProposal
    from app.lab.storage import ReadOnlyLabStore
    store = ReadOnlyLabStore(store_copy)
    try:
        mechanic = type('M', (), {'provider': type('P', (), {'role_model': staticmethod(lambda role: saved.MECHANIC_MODEL)})(), 'metadata': None})()
        size = lambda value: loop_limits.mechanic_request_bound(mechanic, 'diagnosis.md', TypeAdapter(DiagnosticProposal), value)
        diagnosed = 0
        # The provider reported 8,952 (v2e) and 8,854 (v2d) input tokens; the local count adds 136 tokens of message framing,
        # the same difference as v2d's first candidate request (14,304 local, 14,168 reported).
        for campaign_id, reported in ((saved.V2E, 8952), (saved.V2D, 8854)):
            counter, plain = await saved.rebuild_diagnosis_request(store, campaign_id)
            _, got = await saved.rebuild_diagnosis_request(store, campaign_id, wrap=lambda m: citation_status.CitationStatusMechanic(m, store))
            assert size(plain) == reported + 136
            rows = got[BLOCK]['episodes']
            assert [row['episode_id'] for row in rows] == [counter.source_episode_id, *counter.reproduction_trial_ids]
            assert all(row['cited'] == row['decoded'] > 0 and row['undecoded'] == [] for row in rows)
            diagnosed += len(rows)
        assert diagnosed == 8
    finally:
        store.close()


@needs_store
def test_v2ds_refused_candidate_request_with_the_block_still_fits_after_compaction_and_keeps_every_row(store_copy):
    from pydantic import TypeAdapter
    from app.contracts.models import MechanicOutput
    from app.lab.storage import ReadOnlyLabStore
    from test_loop_limits_mechanic_context import rebuild_v2d_request
    store = ReadOnlyLabStore(store_copy)
    try:
        counter, context = rebuild_v2d_request(store)
        mechanic = type('M', (), {'provider': type('P', (), {'role_model': staticmethod(lambda role: saved.MECHANIC_MODEL)})(), 'metadata': None})()
        bound = lambda value: loop_limits.mechanic_request_bound(mechanic, 'mechanic.md', TypeAdapter(MechanicOutput), value)
        assert bound(context) == 33223
        attached = attach(store, context, request_kind='mechanic_proposal')
        full = bound(attached)
        assert 0 < full - 33223 <= 34 * 50                                      # 34 episodes, at most 50 tokens each with its sentence
        request, summary = loop_limits.compact_request(attached, request_kind='mechanic_proposal', store=store, bound=bound, full_bound=full,
                                                       protected_episode_ids=[counter.source_episode_id, *counter.reproduction_trial_ids])
        assert summary['fits'] and summary['stages_applied'][-1] == loop_limits.STAGE_NO_CLEAN
        assert bound(request) == summary['compacted_tokens'] <= loop_limits.COMPACTION_TARGET_TOKENS
        assert request[BLOCK] == attached[BLOCK] and len(request[BLOCK]['episodes']) == 34      # never compacted
        kept = {row['episode_id'] for row in request['development_evidence']['episodes']}
        assert kept <= {row['episode_id'] for row in request[BLOCK]['episodes']}
        assert all(row['undecoded'] == [] and row['cited'] == row['decoded'] for row in request[BLOCK]['episodes'])
    finally:
        store.close()

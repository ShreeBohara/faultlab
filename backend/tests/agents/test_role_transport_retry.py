"""Explorer and Mechanic get the reference Actor's single, charged, blind transport retry.

Real Explorer/Mechanic, real RuntimeProvider and a real CampaignLedger; only the SDK client
(and the one-second 503 wait) are offline boundaries. No provider, W&B or model call is made.
"""
import asyncio
import json
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.agents import transport_retry
from app.agents.explorer import Explorer
from app.agents.mechanic import Mechanic
from app.config import Settings
from app.contracts.models import CampaignBudget, FaultSpec, MechanicNoChange, canonical_json, content_hash
from app.lab.budgets import CampaignLedger, PROTECTED
from app.lab.discovery_protocol import DISCOVERY_V1, DISCOVERY_V2, DiscoveryV2, declaration
from app.lab.policies import PolicyRepository
from app.lab.reachability import caller_model_for
from app.lab.storage import LabStore
from app.providers.runtime import RuntimeGeneration, RuntimeProvider, RuntimeProviderError


@pytest.fixture
def anyio_backend(): return 'asyncio'


MODEL = 'openai/gpt-oss-120b'
BOUND = .03
FORCED = {'seed': 1, 'primitives': [{'kind': 'F2', 'target_tool': 'update_order', 'target_service': 'orders', 'occurrence': 1,
          'parameters': {'completion_delay_ticks': 3, 'terminal_status': 'SUCCEEDED', 'failure_code': None}}]}
PICK = {'fault_spec': FORCED, 'hypothesis': 'Scripted pick'}
NO_CHANGE = {'no_change_reason': 'Scripted: no bounded change is justified.'}
URL = 'https://provider.invalid/v1/chat/completions'


def connection_error(): return openai.APIConnectionError(request=httpx.Request('POST', URL))
def timeout_error(): return openai.APITimeoutError(request=httpx.Request('POST', URL))


class Harness(SimpleNamespace):
    def retries(self): return self.store.list_records('transport_retries')
    def failures(self): return self.store.list_records('provider_failures')


def setup(tmp_path, monkeypatch, responses, *, calls=40, tokens=40 * 34000, dollars=20.0, reserve=None):
    store = LabStore(tmp_path / 'lab.sqlite3')
    ledger = CampaignLedger(store, 'campaign-own', CampaignBudget(model_calls=calls, tokens=tokens, dollars=dollars),
                            dollar_bounds={'actor': BOUND, 'explorer': BOUND, 'mechanic': BOUND})
    for name in PROTECTED: ledger.release(name)
    if reserve: ledger.reserve('batch', reserve)
    requests = []; delays = []
    async def sleep(seconds): delays.append(seconds)
    monkeypatch.setattr(transport_retry.asyncio, 'sleep', sleep)
    async def create(**kwargs):
        requests.append(kwargs)
        item = responses[len(requests) - 1]
        if isinstance(item, BaseException): raise item
        if type(item) is int:
            response = httpx.Response(item, request=httpx.Request('POST', URL))
            cls = openai.InternalServerError if item >= 500 else openai.APIStatusError
            raise cls('private SDK text', response=response, body={'secret': 'private SDK body'})
        if not isinstance(item, dict): return item
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=canonical_json(item)))],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20))
    def factory(**kwargs): return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    provider = RuntimeProvider(Settings(wandb_api_key='fixture-key', wandb_entity='fixture', wandb_project='project',
                                        wandb_model=MODEL, wandb_explorer_model=MODEL, wandb_mechanic_model=MODEL),
                               live_authorized=True, client_factory=factory)
    store.put_record('campaigns', 'campaign-own', {'configuration_hash': content_hash('configuration')})
    context = {'campaign_id': 'campaign-own', 'configuration_hash': content_hash('configuration'),
               'policy_hash': content_hash('policy'), 'selection_index': 0, 'development_history': []}
    return Harness(store=store, ledger=ledger, provider=provider, requests=requests, delays=delays, context=context,
                   explorer=Explorer(provider, store, ledger), mechanic=Mechanic(provider, store, ledger))


def only_selection(h):
    selection, = h.store.list_records('selections')
    return selection


# ----------------------------------------------------------------------------- Explorer

@pytest.mark.anyio
@pytest.mark.parametrize('failure,code', [(connection_error, 'CONNECTION_ERROR'), (timeout_error, 'REQUEST_TIMEOUT')])
async def test_explorer_connection_loss_is_retried_once_charged_and_recorded(tmp_path, monkeypatch, failure, code):
    h = setup(tmp_path, monkeypatch, [failure(), PICK])
    ref, selected = await h.explorer.select(h.context)
    assert selected.fault_spec == FaultSpec.model_validate(FORCED)
    assert len(h.requests) == 2 and h.requests[0] == h.requests[1]          # the identical request, re-sent once
    assert h.ledger.used_calls == 2 and h.ledger.used_dollar_upper_bound == pytest.approx(2 * BOUND)
    assert h.ledger.used_tokens == 2 * h.ledger.tokens_per_call and h.delays == []
    failure_record, = h.failures()
    retry, = h.retries()
    assert failure_record['role'] == 'explorer' and failure_record['diagnostics']['code'] == code
    assert retry['role'] == 'explorer' and retry['code'] == code and retry['attempt'] == 1 and retry['charged_model_calls'] == 1
    assert retry['provider_failure_id'] == failure_record['failure_id'] and retry['campaign_id'] == 'campaign-own'
    assert retry['request']['kind'] == 'explorer_selection' and retry['protocol'] == 'faultlab-transport-retry/v1'
    selection = only_selection(h)
    assert selection['selection_id'] == ref and selection['usage']['model_calls'] == 2
    assert selection['transport_retries'] == [{'retry_id': retry['retry_id'], 'code': code, 'attempt': 1,
                                               'provider_failure_id': failure_record['failure_id']}]
    assert 'private SDK' not in canonical_json(h.store.list_records('transport_retries') + h.failures())
    h.store.close()


@pytest.mark.anyio
async def test_explorer_503_waits_one_second_then_retries(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [503, PICK])
    _, selected = await h.explorer.select(h.context)
    assert selected is not None and h.delays == [1] and len(h.requests) == h.ledger.used_calls == 2
    retry, = h.retries()
    assert (retry['code'], retry['http_status'], retry['retry_delay_seconds']) == ('HTTP_ERROR', 503, 1)
    h.store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('second', [connection_error, lambda: 503, timeout_error])
async def test_explorer_second_failure_raises_after_exactly_two_charged_requests(tmp_path, monkeypatch, second):
    h = setup(tmp_path, monkeypatch, [connection_error(), second(), PICK])
    with pytest.raises(RuntimeProviderError):
        await h.explorer.select(h.context)
    assert len(h.requests) == h.ledger.used_calls == 2
    assert len(h.failures()) == 2 and len(h.retries()) == 1 and not h.store.list_records('selections')
    h.store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('status', [400, 401, 403, 404, 408, 409, 422, 429, 500, 502, 504])
async def test_explorer_other_http_statuses_are_never_retried(tmp_path, monkeypatch, status):
    h = setup(tmp_path, monkeypatch, [status, PICK])
    with pytest.raises(RuntimeProviderError) as caught:
        await h.explorer.select(h.context)
    assert caught.value.http_status == status and len(h.requests) == h.ledger.used_calls == 1
    assert not h.retries() and h.delays == []
    h.store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('malformed', [False, True])
async def test_explorer_received_empty_or_malformed_answer_is_never_retried(tmp_path, monkeypatch, malformed):
    response = SimpleNamespace(choices=[] if malformed else [SimpleNamespace(finish_reason='length', message=SimpleNamespace(content=None))],
                               usage=SimpleNamespace(prompt_tokens=7, completion_tokens=2000))
    h = setup(tmp_path, monkeypatch, [response, PICK])
    with pytest.raises(RuntimeProviderError) as caught:
        await h.explorer.select(h.context)
    assert caught.value.code == ('INVALID_RESPONSE_SHAPE' if malformed else 'EMPTY_FINAL_RESPONSE')
    assert len(h.requests) == h.ledger.used_calls == 1 and not h.retries()
    assert h.ledger.measured_output == 2000  # the received answer's usage is accounted, never re-rolled
    h.store.close()


@pytest.mark.anyio
async def test_explorer_received_invalid_selection_is_an_answer_not_a_retry(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [{'not': 'a selection'}, PICK])
    _, selected = await h.explorer.select(h.context)
    assert selected is None and len(h.requests) == h.ledger.used_calls == 1 and not h.retries()
    assert only_selection(h)['error'] == 'INVALID_EXPLORER_OUTPUT'
    h.store.close()


@pytest.mark.anyio
async def test_explorer_frozen_model_mismatch_is_never_retried(tmp_path):
    store = LabStore(tmp_path / 'lab.sqlite3'); ledger = CampaignLedger(store, 'campaign-own')
    class Other:
        calls = 0
        def role_model(self, role): return MODEL
        async def complete(self, *args, **kwargs):
            self.calls += 1
            return RuntimeGeneration(canonical_json(PICK), 'some-other-model', 10, 20)
    provider = Other(); explorer = Explorer(provider, store, ledger)
    explorer.metadata = {'campaign_id': 'campaign-own', 'model_id': MODEL}
    with pytest.raises(RuntimeProviderError, match='different frozen model'):
        await explorer.select({'campaign_id': 'campaign-own', 'selection_index': 0})
    assert provider.calls == ledger.used_calls == 1 and not store.list_records('transport_retries')
    store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('calls,tokens,dollars', [(1, 40 * 34000, 20.0), (40, 34000, 20.0), (40, 40 * 34000, BOUND)])
async def test_explorer_retry_the_budget_cannot_cover_is_refused_before_sending(tmp_path, monkeypatch, calls, tokens, dollars):
    h = setup(tmp_path, monkeypatch, [connection_error(), PICK], calls=calls, tokens=tokens, dollars=dollars)
    with pytest.raises(RuntimeProviderError) as caught:
        await h.explorer.select(h.context)
    assert caught.value.code == 'CONNECTION_ERROR'            # the original failure, not a budget error
    assert len(h.requests) == h.ledger.used_calls == 1 and h.ledger.used_dollar_upper_bound == pytest.approx(BOUND)
    assert not h.retries() and len(h.failures()) == 1
    h.store.close()


@pytest.mark.anyio
async def test_explorer_retry_never_draws_on_a_batch_reservation(tmp_path, monkeypatch):
    # Two calls in total, both reserved for the batch: the first request uses the reservation,
    # the retry would need unreserved capacity, so it is refused and the reservation is kept.
    h = setup(tmp_path, monkeypatch, [connection_error(), PICK], calls=2, tokens=2 * 34000, reserve=2)
    with pytest.raises(RuntimeProviderError):
        await h.explorer.select(h.context, reservation='batch')
    assert len(h.requests) == h.ledger.used_calls == 1 and h.ledger.reservations['batch']['calls'] == 1
    h.store.close()
    h = setup(tmp_path / 'spare', monkeypatch, [connection_error(), PICK], calls=3, tokens=3 * 34000, reserve=2)
    await h.explorer.select(h.context, reservation='batch')
    assert h.ledger.used_calls == 2 and h.ledger.reservations['batch']['calls'] == 1  # retry came from spare capacity
    h.store.close()


@pytest.mark.anyio
async def test_explorer_stop_requested_before_retry_refuses_it(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), PICK])
    original = h.store.put_record
    def stop_on_failure(kind, *args, **kwargs):
        if kind == 'provider_failures': h.ledger.stopped = True
        return original(kind, *args, **kwargs)
    h.store.put_record = stop_on_failure
    with pytest.raises(RuntimeProviderError) as caught:
        await h.explorer.select(h.context)
    assert caught.value.code == 'CONNECTION_ERROR' and len(h.requests) == h.ledger.used_calls == 1 and not h.retries()
    h.store.close()


@pytest.mark.anyio
async def test_cancellation_during_the_503_wait_is_not_charged_as_a_retry(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [503, PICK])
    async def cancel(seconds): raise asyncio.CancelledError()
    monkeypatch.setattr(transport_retry.asyncio, 'sleep', cancel)
    with pytest.raises(asyncio.CancelledError):
        await h.explorer.select(h.context)
    assert len(h.requests) == h.ledger.used_calls == 1 and not h.retries()
    h.store.close()


def v2_session(store, block=None):
    return DiscoveryV2(block or declaration(DISCOVERY_V2, {'discovery_selections': 8}, caller=caller_model_for('reference', [])),
                       agent='reference', incumbent=PolicyRepository(store).baseline())


@pytest.mark.anyio
async def test_v2_retry_is_not_a_selection_request_and_is_bounded_by_the_declared_maximum(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), PICK, connection_error(), PICK])
    session = v2_session(h.store)
    assert session.block['explorer_requests_max'] == session.block['explorer_transport_retries_max'] == 16
    _, selected = await h.explorer.select({**h.context, 'slot_request': 1}, discovery_v2=session)
    assert selected is not None
    assert session.explorer_requests == 1 and session.transport_retries == 1   # the retry used no discovery request
    selection = only_selection(h)
    assert selection['search_decision']['status'] == 'SELECTED' and selection['usage']['model_calls'] == 2
    assert h.retries()[0]['request']['slot_request'] == 1
    # At the declared maximum, the next retry is refused before any charge; the failure stands.
    session.transport_retries = session.block['explorer_transport_retries_max']
    with pytest.raises(RuntimeProviderError):
        await h.explorer.select({**h.context, 'selection_index': 1, 'slot_request': 1}, discovery_v2=session)
    assert len(h.requests) == h.ledger.used_calls == 3 and len(h.retries()) == 1
    h.store.close()


@pytest.mark.anyio
async def test_v2_plan_saved_before_retries_existed_declares_none(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), PICK])
    old = {k: v for k, v in declaration(DISCOVERY_V2, {'discovery_selections': 8}, caller=caller_model_for('reference', [])).items()
           if k != 'explorer_transport_retries_max'}
    session = v2_session(h.store, old)
    with pytest.raises(RuntimeProviderError):
        await h.explorer.select({**h.context, 'slot_request': 1}, discovery_v2=session)
    assert len(h.requests) == h.ledger.used_calls == 1 and session.transport_retries == 0
    h.store.close()


def test_declared_discovery_retry_maxima():
    v1 = declaration(DISCOVERY_V1, {'discovery_selections': 8})
    v2 = declaration(DISCOVERY_V2, {'discovery_selections': 8}, caller=caller_model_for('reference', []))
    assert (v1['explorer_requests_max'], v1['explorer_transport_retries_max']) == (8, 8)
    assert (v2['explorer_requests_max'], v2['explorer_transport_retries_max']) == (16, 16)


@pytest.mark.anyio
async def test_no_retry_leaves_the_selection_record_unchanged(tmp_path, monkeypatch):
    """Without a transport failure the saved selection has exactly its earlier fields."""
    h = setup(tmp_path, monkeypatch, [PICK])
    await h.explorer.select(h.context)
    selection = only_selection(h)
    assert 'transport_retries' not in selection and selection['usage']['model_calls'] == 1
    assert len(h.requests) == h.ledger.used_calls == 1
    h.store.close()


# ----------------------------------------------------------------------------- Mechanic

@pytest.mark.anyio
@pytest.mark.parametrize('failure', [connection_error, timeout_error, lambda: 503])
async def test_mechanic_connection_loss_is_retried_once_charged_and_recorded(tmp_path, monkeypatch, failure):
    h = setup(tmp_path, monkeypatch, [failure(), NO_CHANGE])
    ref, result, raws = await h.mechanic.propose({'campaign_id': 'campaign-own'})
    assert isinstance(result, MechanicNoChange) and len(raws) == 1
    assert len(h.requests) == h.ledger.used_calls == 2 and h.requests[0] == h.requests[1]
    retry, = h.retries()
    output = h.store.get_record('mechanic_outputs', ref)
    assert retry['role'] == 'mechanic' and retry['request']['kind'] == 'mechanic_proposal'   # the proposal request (mechanic.md)
    assert retry['request']['request_id'] == output['request_id'] and output['usage']['model_calls'] == 2
    assert output['transport_retries'][0]['retry_id'] == retry['retry_id']
    h.store.close()


@pytest.mark.anyio
async def test_mechanic_each_request_gets_at_most_one_retry_including_format_repair(tmp_path, monkeypatch):
    # First request: lost then answered (invalid format). Format repair: lost then answered.
    h = setup(tmp_path, monkeypatch, [connection_error(), {'kind': 'bad'}, connection_error(), NO_CHANGE])
    _, result, raws = await h.mechanic.propose({'campaign_id': 'campaign-own'})
    assert isinstance(result, MechanicNoChange) and len(raws) == 2
    assert len(h.requests) == h.ledger.used_calls == 4 and len(h.retries()) == 2
    assert [r['request']['format_attempt'] for r in sorted(h.retries(), key=lambda r: r['recorded_at'])] == [0, 1]
    h.store.close()


@pytest.mark.anyio
async def test_mechanic_second_failure_raises_and_no_proposal_is_saved(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), connection_error(), NO_CHANGE])
    with pytest.raises(RuntimeProviderError) as caught:
        await h.mechanic.diagnose({'campaign_id': 'campaign-own', 'evidence_ids': [], 'intervention_ids': []})
    assert caught.value.code == 'CONNECTION_ERROR' and len(h.requests) == h.ledger.used_calls == 2
    assert len(h.retries()) == 1 and not h.store.list_records('mechanic_outputs')
    assert h.retries()[0]['request']['kind'] == 'mechanic_diagnosis'
    h.store.close()


@pytest.mark.anyio
async def test_mechanic_received_malformed_answer_is_never_retried(tmp_path, monkeypatch):
    response = SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=7, completion_tokens=11))
    h = setup(tmp_path, monkeypatch, [response, NO_CHANGE])
    with pytest.raises(RuntimeProviderError) as caught:
        await h.mechanic.propose({'campaign_id': 'campaign-own'})
    assert caught.value.code == 'INVALID_RESPONSE_SHAPE' and len(h.requests) == h.ledger.used_calls == 1
    assert not h.retries()
    h.store.close()


@pytest.mark.anyio
async def test_mechanic_retry_is_refused_when_only_the_candidate_reservation_remains(tmp_path, monkeypatch):
    h = setup(tmp_path, monkeypatch, [connection_error(), NO_CHANGE], calls=2, tokens=2 * 34000, reserve=2)
    with pytest.raises(RuntimeProviderError) as caught:
        await h.mechanic.propose({'campaign_id': 'campaign-own'}, reservation='batch')
    assert caught.value.code == 'CONNECTION_ERROR'
    assert len(h.requests) == h.ledger.used_calls == 1 and h.ledger.reservations['batch']['calls'] == 1
    assert not h.retries()
    h.store.close()


# ----------------------------------------------------------------------------- the shared rule

@pytest.mark.parametrize('code,status,generation,allowed', [
    ('CONNECTION_ERROR', None, None, True), ('REQUEST_TIMEOUT', None, None, True), ('HTTP_ERROR', 503, None, True),
    ('HTTP_ERROR', 500, None, False), ('HTTP_ERROR', 502, None, False), ('HTTP_ERROR', 504, None, False),
    ('HTTP_ERROR', 401, None, False), ('HTTP_ERROR', 429, None, False), ('PROVIDER_ERROR', None, None, False),
    ('LIVE_ACTION_REQUIRED', None, None, False), ('INPUT_LIMIT', None, None, False), ('SECRET_INPUT', None, None, False),
    ('EMPTY_FINAL_RESPONSE', None, RuntimeGeneration('', MODEL, 1, 1), False),
    ('CONNECTION_ERROR', None, RuntimeGeneration('partial', MODEL, 1, 1), False),
    ('HTTP_ERROR', 503, RuntimeGeneration('', MODEL, 1, 1), False)])
def test_one_rule_for_every_role(code, status, generation, allowed):
    error = RuntimeProviderError('safe', code=code, http_status=status, generation=generation)
    assert transport_retry.blind_retry_allowed(error) is allowed
    from app.agents import actor
    assert actor.RETRYABLE_TRANSPORT_CODES == transport_retry.RETRYABLE_TRANSPORT_CODES
    assert actor.blind_retry_allowed is transport_retry.blind_retry_allowed


def test_configuration_errors_are_not_runtime_provider_errors_and_never_retry():
    from app.config import ConfigurationError
    assert not transport_retry.blind_retry_allowed(ConfigurationError(('WANDB_API_KEY',)))


# ----------------------------------------------------------------------------- review fixes (September 29)

@pytest.mark.anyio
async def test_mechanic_completion_retry_is_recorded_as_a_completion_request(tmp_path, monkeypatch):
    """Review finding (LOW): request kinds name the request, not the prompt file (never 'mechanic_mechanic')."""
    h = setup(tmp_path, monkeypatch, [connection_error(), NO_CHANGE])
    await h.mechanic.propose_completion({'campaign_id': 'campaign-own'})
    retry, = h.retries()
    assert retry['request']['kind'] == 'mechanic_completion'
    from app.agents.mechanic import REQUEST_KINDS
    assert REQUEST_KINDS == {'diagnosis.md': 'mechanic_diagnosis', 'mechanic.md': 'mechanic_proposal', 'completion.md': 'mechanic_completion'}
    h.store.close()


class Priced:
    """A scripted provider whose answers report tokens and a dollar cost (the real provider reports
    no cost, so live records already say None; this makes the convention observable)."""
    def __init__(self, answers):
        self.answers = list(answers); self.calls = 0
    def role_model(self, role): return MODEL
    async def complete(self, messages, *, role, **kwargs):
        self.calls += 1
        item = self.answers.pop(0)
        if isinstance(item, BaseException): raise item
        return RuntimeGeneration(canonical_json(item), MODEL, input_tokens=100, output_tokens=20, cost_usd=0.001)


def lost(): return RuntimeProviderError('scripted loss', code='CONNECTION_ERROR', error_class='APIConnectionError')


def priced(tmp_path, answers):
    store = LabStore(tmp_path / 'lab.sqlite3')
    ledger = CampaignLedger(store, 'campaign-own', CampaignBudget(model_calls=40, tokens=40 * 34000, dollars=20.0),
                            dollar_bounds={'actor': BOUND, 'explorer': BOUND, 'mechanic': BOUND})
    for name in PROTECTED: ledger.release(name)
    provider = Priced(answers)
    return store, ledger, provider


@pytest.mark.anyio
@pytest.mark.parametrize('lose_first', [False, True])
async def test_explorer_selection_cost_is_unknown_after_a_retry(tmp_path, lose_first):
    """Review finding (LOW): one cost convention for every role. A request that lost an attempt has an
    unknown cost (the lost attempt returned no usage); its tokens are the answered attempt's only.
    The ledger still charged both attempts in full and now reports its actual cost as unknown."""
    store, ledger, provider = priced(tmp_path, ([lost()] if lose_first else []) + [PICK])
    explorer = Explorer(provider, store, ledger)
    await explorer.select({'campaign_id': 'campaign-own', 'selection_index': 0})
    selection, = store.list_records('selections')
    usage = selection['usage']
    assert (usage['input_tokens'], usage['output_tokens']) == (100, 20)
    if lose_first:
        assert usage['model_calls'] == 2 and usage['cost_dollars'] is None
        assert ledger.used_calls == 2 and ledger.used_dollar_upper_bound == pytest.approx(2 * BOUND)
        budget = store.get_record('budgets', 'campaign-own')
        assert budget['actual_cost_dollars'] is None and budget['usage_metadata_known'] is False
        assert budget['unknown_cost_calls'] == budget['unknown_token_calls'] == 1
    else:
        assert usage['model_calls'] == 1 and usage['cost_dollars'] == pytest.approx(0.001)
        assert store.get_record('budgets', 'campaign-own')['actual_cost_dollars'] == pytest.approx(0.001)
    store.close()


@pytest.mark.anyio
@pytest.mark.parametrize('lose_first', [False, True])
async def test_mechanic_output_cost_is_unknown_after_a_retry(tmp_path, lose_first):
    store, ledger, provider = priced(tmp_path, ([lost()] if lose_first else []) + [NO_CHANGE])
    mechanic = Mechanic(provider, store, ledger)
    ref, result, _ = await mechanic.propose({'campaign_id': 'campaign-own'})
    assert isinstance(result, MechanicNoChange)
    usage = store.get_record('mechanic_outputs', ref)['usage']
    assert (usage['model_calls'], usage['input_tokens'], usage['output_tokens']) == (1 + lose_first, 100, 20)
    assert usage['cost_dollars'] is None if lose_first else usage['cost_dollars'] == pytest.approx(0.001)
    store.close()


def test_request_usage_is_the_one_convention():
    answered = RuntimeGeneration('x', MODEL, input_tokens=5, output_tokens=6, cost_usd=0.002)
    assert transport_retry.request_usage(answered, []) == {'model_calls': 1, 'input_tokens': 5, 'output_tokens': 6, 'cost_dollars': 0.002}
    assert transport_retry.request_usage(answered, [{'retry_id': 'r'}]) == {'model_calls': 2, 'input_tokens': 5, 'output_tokens': 6, 'cost_dollars': None}

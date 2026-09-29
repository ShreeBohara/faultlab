"""Explorer under discovery protocol v2: readable ledger, per-service attempts, budget admission."""
import json
import re

import pytest

from app.agents.explorer import Explorer, attempts_by_tool_and_service, discovery_search_ledger_v2
from app.contracts.models import FaultSpec, canonical_json, content_hash
from app.lab.budgets import CampaignLedger
from app.lab.discovery_protocol import DISCOVERY_V2, BudgetViolation, DiscoveryV2, declaration
from app.lab.policies import PolicyRepository
from app.lab.reachability import caller_model_for
from app.lab.storage import LabStore
from app.providers.runtime import RuntimeGeneration


@pytest.fixture
def anyio_backend(): return 'asyncio'


class RecordedProvider:
    def __init__(self, outputs): self.outputs = iter(outputs); self.messages = []
    async def complete(self, messages, **kwargs):
        self.messages.append(messages)
        return RuntimeGeneration(next(self.outputs), 'openai/gpt-oss-120b', input_tokens=100, output_tokens=50)


def status_fault(count=1):
    return {'seed': 1, 'primitives': [{'kind': 'F4', 'target_tool': 'get_operation_status', 'target_service': 'orders',
                                       'occurrence': 1, 'parameters': {'failure_count': count}}]}


def fixture(tmp_path, outputs):
    store = LabStore(tmp_path / 'lab.db'); ledger = CampaignLedger(store, 'campaign-own')
    context = {'campaign_id': 'campaign-own', 'configuration_hash': content_hash('configuration'),
               'policy_hash': content_hash('policy'), 'selection_index': 0, 'development_history': [], 'slot_request': 1}
    store.put_record('campaigns', 'campaign-own', {'configuration_hash': context['configuration_hash']})
    session = DiscoveryV2(declaration(DISCOVERY_V2, {'discovery_selections': 8}, caller=caller_model_for('reference', [])),
                          agent='reference', incumbent=PolicyRepository(store).baseline())
    provider = RecordedProvider(outputs)
    return store, ledger, provider, Explorer(provider, store, ledger), context, session


def test_attempts_are_counted_per_tool_and_service(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    store.put_record('private_episode_inputs', 'episode-1', {'intent': {'upgrade_operation_id': 'upgrade-1', 'notification_operation_id': 'notify-1'}})
    observations = {'o1': {'result': {'transport': 'ok', 'data': {'service': 'notifications'}}},
                    'o2': {'result': {'transport': 'error', 'operation_id': 'upgrade-1', 'data': None}},
                    'o3': {'result': {'transport': 'ok', 'data': {'service': 'orders'}}}}
    for key, value in observations.items(): store.put_record('observations', key, value)
    store.put_record('tool_calls', 'call-a', {'episode_id': 'episode-1', 'tool': 'get_operation_status', 'attempt_ids': ['a1'], 'observation_ids': ['o1']})
    store.put_record('tool_calls', 'call-b', {'episode_id': 'episode-1', 'tool': 'get_operation_status', 'attempt_ids': ['a2', 'a3'], 'observation_ids': ['o2', 'o3']})
    store.put_record('tool_calls', 'call-c', {'episode_id': 'episode-1', 'tool': 'send_confirmation', 'attempt_ids': ['a4', 'a5'], 'observation_ids': ['o4', 'o5']})
    store.put_record('tool_calls', 'call-d', {'episode_id': 'episode-other', 'tool': 'get_order', 'attempt_ids': ['a6'], 'observation_ids': ['o6']})
    assert attempts_by_tool_and_service(store, 'episode-1') == {'get_operation_status:notifications': 1,
        'get_operation_status:orders': 2, 'send_confirmation:notifications': 2}


@pytest.mark.anyio
async def test_refused_pick_is_recorded_with_readable_reasons_and_its_repeat_is_a_duplicate(tmp_path):
    raws = [canonical_json({'fault_spec': status_fault(), 'hypothesis': 'A status fault'}),
            canonical_json({'fault_spec': {**status_fault(), 'seed': 5}, 'hypothesis': 'Same again'})]
    store, ledger, provider, explorer, context, session = fixture(tmp_path, raws)
    ref, selected = await explorer.select(context, fallback=FaultSpec.model_validate(status_fault(3)), discovery_v2=session)
    assert selected is None
    saved = store.get_record('selections', ref)
    decision = saved['search_decision']
    assert decision['status'] == 'SKIPPED_UNREACHABLE' and decision['reason'] == 'NOT_ALL_FAULTS_FORCED'
    assert decision['reachability']['faults'][0]['reason_code'] == 'N2_UNNEEDED_STATUS_CHECK'
    assert saved['raw'] == raws[0] and saved['usage']['model_calls'] == 1 and ledger.used_calls == 1
    ref2, selected = await explorer.select({**context, 'slot_request': 2, 'replan_of': ref}, discovery_v2=session)
    again = store.get_record('selections', ref2)['search_decision']
    assert selected is None and again['status'] == 'SKIPPED_DUPLICATE' and again['prior_selection_refs'] == [ref]
    assert again['replan_of'] == ref and again['slot_request'] == 2
    ledger_view, _ = discovery_search_ledger_v2(store, context, campaign_id='campaign-own')
    supplied = json.loads(provider.messages[1][-1]['content'])['search_ledger']
    assert supplied['refused_recipes'][0]['recipe'] == ['F4 on get_operation_status:orders attempt 1: transient 503 before the request is accepted']
    assert supplied['refused_recipes'][0]['faults'][0]['verdict'] == 'NOT_FORCED'
    # Readable, not hashes: only the three binding digests are hex in the ledger.
    text = canonical_json({k: v for k, v in ledger_view.items() if k not in ('configuration_hash', 'policy_hash')})
    assert not re.search(r'[a-f0-9]{64}', text)
    assert len(ledger_view['prior_selections']) == 2 and ledger_view['excluded_recipes']


@pytest.mark.anyio
async def test_declared_request_budget_refuses_before_any_charge(tmp_path):
    store, ledger, provider, explorer, context, session = fixture(tmp_path, [])
    session.explorer_requests = session.block['explorer_requests_max']
    with pytest.raises(BudgetViolation):
        await explorer.select(context, discovery_v2=session)
    assert not provider.messages and ledger.used_calls == 0 and not store.list_records('selections')
    session.actor_episodes = session.block['actor_episodes_max']
    with pytest.raises(BudgetViolation):
        session.admit_episode()


@pytest.mark.anyio
async def test_v2_arguments_are_ignored_outside_ordinary_discovery(tmp_path):
    raw = canonical_json({'fault_spec': status_fault(), 'hypothesis': 'Challenge proposal'})
    store, ledger, provider, explorer, context, session = fixture(tmp_path, [raw])
    _, selected = await explorer.select({'proposal_index': 0}, challenge=True, discovery_v2=session)
    assert selected is not None and store.list_records('selections')[0]['search_decision'] is None
    assert session.explorer_requests == 0

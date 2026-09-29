"""Order-aware schedule identity (v2) for new campaigns; v1 stays byte-for-byte for history."""
import itertools
import json
from pathlib import Path

import pytest

from app.agents.explorer import discovery_search_ledger
from app.contracts.models import ExplorerOutput, FaultSpec, content_hash
from app.lab.challenge import (SCHEDULE_IDENTITY_V1, SCHEDULE_IDENTITY_V2, Challenger, identity_for,
                               schedule_identity, schedule_identity_v2)
from app.lab.evaluation import PairedEvaluator
from app.lab.reachability import caller_model_for, label_recipe
from app.lab.storage import LabStore
from test_evaluation import cases, setup

FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures' / 'c701e850_explorer_outputs.json'


@pytest.fixture
def anyio_backend(): return 'asyncio'


def spec(*primitives, seed=1):
    return FaultSpec.model_validate({'seed': seed, 'primitives': list(primitives)})


def F4(tool, service, occurrence, count):
    return {'kind': 'F4', 'target_tool': tool, 'target_service': service, 'occurrence': occurrence, 'parameters': {'failure_count': count}}


def F2(delay, ok=True, occurrence=1):
    return {'kind': 'F2', 'target_tool': 'update_order', 'target_service': 'orders', 'occurrence': occurrence,
            'parameters': {'completion_delay_ticks': delay, 'terminal_status': 'SUCCEEDED' if ok else 'FAILED',
                           'failure_code': None if ok else 'UPGRADE_REJECTED'}}


def F3(back, occurrence=1):
    return {'kind': 'F3', 'target_tool': 'get_order', 'target_service': 'orders', 'occurrence': occurrence, 'parameters': {'versions_back': back}}


def F1(tool, service, occurrence=1, delay=1500):
    return {'kind': 'F1', 'target_tool': tool, 'target_service': service, 'occurrence': occurrence, 'parameters': {'response_delay_ms': delay}}


def test_historical_v1_identities_are_unchanged_for_recorded_c701e850_selections():
    rows = json.loads(FIXTURE.read_text())['selections']
    for row in rows:
        recipe = ExplorerOutput.model_validate_json(row['raw']).fault_spec
        assert schedule_identity(recipe) == row['recorded_schedule_hash']
    assert identity_for(None) is schedule_identity and identity_for(SCHEDULE_IDENTITY_V1) is schedule_identity
    assert identity_for(SCHEDULE_IDENTITY_V2) is schedule_identity_v2
    with pytest.raises(ValueError): identity_for('faultlab-schedule-identity/unknown')


@pytest.mark.parametrize('first,second', [
    (F4('update_order', 'orders', 1, 1), F4('update_order', 'orders', 1, 2)),   # first matching F4 triggers
    (F2(3), F2(2, ok=False)),                                                    # first matching F2 installs
    (F3(1), F3(2)),                                                              # last matching F3 is returned
    (F4('send_confirmation', 'notifications', 2, 1), F4('send_confirmation', 'notifications', 1, 3)),  # overlapping windows
])
def test_order_of_overlapping_same_kind_faults_is_a_different_schedule(first, second):
    forward, backward = spec(first, second), spec(second, first)
    assert schedule_identity(forward) == schedule_identity(backward)          # the v1 bug
    assert schedule_identity_v2(forward) != schedule_identity_v2(backward)    # fixed in v2


@pytest.mark.parametrize('first,second', [
    (F4('get_operation_status', 'orders', 1, 1), F4('send_confirmation', 'notifications', 1, 2)),
    (F1('update_order', 'orders'), F2(3)),
    (F2(3), F1('send_confirmation', 'notifications')),
    (F4('update_order', 'orders', 1, 1), F4('update_order', 'orders', 3, 1)),  # same kind, windows do not overlap
    (F1('update_order', 'orders', 1, 1500), F1('update_order', 'orders', 1, 2000)),
])
def test_order_of_independent_faults_and_the_seed_do_not_make_a_new_schedule(first, second):
    assert schedule_identity_v2(spec(first, second)) == schedule_identity_v2(spec(second, first, seed=9))


def test_v2_equal_orders_behave_identically_on_the_agent_path():
    """Soundness of merging: whenever v2 calls two orders one schedule, the replay agrees."""
    caller = caller_model_for('reference', [])
    grid = [F1('update_order', 'orders'), F1('send_confirmation', 'notifications'), F2(3), F2(2, ok=False), F3(1), F3(2),
            F4('get_order', 'orders', 1, 1), F4('update_order', 'orders', 1, 1), F4('update_order', 'orders', 1, 2),
            F4('update_order', 'orders', 2, 1), F4('send_confirmation', 'notifications', 1, 2),
            F4('get_operation_status', 'orders', 1, 1)]
    merged = split = 0
    for first, second in itertools.combinations(grid, 2):
        forward, backward = spec(first, second), spec(second, first)
        a, b = label_recipe(forward, caller), label_recipe(backward, caller)
        same_behaviour = a['agent_path'] == b['agent_path'] and [f['verdict'] for f in a['faults']] == [f['verdict'] for f in reversed(b['faults'])]
        if schedule_identity_v2(forward) == schedule_identity_v2(backward):
            merged += 1
            assert same_behaviour, (first, second)
        else:
            split += 1
    assert merged > 40 and split >= 3


def test_v1_ledger_checks_each_record_with_its_own_identity_version(tmp_path):
    store = LabStore(tmp_path / 'lab.db')
    context = {'campaign_id': 'campaign-own', 'configuration_hash': content_hash('configuration'),
               'policy_hash': content_hash('policy'), 'selection_index': 0, 'development_history': []}
    store.put_record('campaigns', 'campaign-own', {'configuration_hash': context['configuration_hash']})
    recipe = spec(F4('update_order', 'orders', 1, 2), F4('update_order', 'orders', 1, 1))
    output = {'fault_spec': recipe.model_dump(mode='json'), 'hypothesis': 'Stored earlier'}
    store.put_record('selections', 'selection-old', {'selection_id': 'selection-old', 'context': context, 'selected_output': output,
        'search_decision': {'status': 'SELECTED', 'schedule_hash': schedule_identity(recipe)}})
    store.put_record('selections', 'selection-new', {'selection_id': 'selection-new', 'context': context, 'selected_output': output,
        'search_decision': {'status': 'SELECTED', 'schedule_hash': schedule_identity_v2(recipe), 'identity_version': SCHEDULE_IDENTITY_V2}})
    _, seen = discovery_search_ledger(store, context, campaign_id='campaign-own')
    assert set(seen) == {schedule_identity(recipe), schedule_identity_v2(recipe)}


class OrderedExplorer:
    """Proposes the same two same-target F4s in both orders, then distinct delays."""
    def __init__(self):
        self.calls = 0
        self.recipes = [spec(F4('update_order', 'orders', 1, 1), F4('update_order', 'orders', 1, 2)),
                        spec(F4('update_order', 'orders', 1, 2), F4('update_order', 'orders', 1, 1))]
        self.recipes += [spec(F2(delay)) for delay in (1, 2, 3, 4, 5, 6)]
    async def select(self, context, **kwargs):
        recipe = self.recipes[self.calls]; self.calls += 1
        return f'selection-{self.calls}', ExplorerOutput(fault_spec=recipe, hypothesis='Offline challenge fixture')


@pytest.mark.anyio
@pytest.mark.parametrize('identity,expected', [(schedule_identity, 1), (schedule_identity_v2, 2)])
async def test_challenge_in_a_v2_campaign_no_longer_skips_a_reordered_but_different_schedule(tmp_path, identity, expected):
    c, campaign, ledger, candidate, runner = setup(tmp_path)
    evaluator = PairedEvaluator(c.store, runner, ledger)
    source = await evaluator.run(campaign, cases(1), c.policies.baseline(), candidate, purpose='source_validation')
    ledger.reserve('candidate', 528)
    explorer = OrderedExplorer()
    kwargs = {} if identity is schedule_identity else {'identity': identity}
    result = await Challenger(c.store, explorer, evaluator, **kwargs).run(campaign, c.policies.baseline(), candidate, source, reservation='candidate')
    reordered = {identity(explorer.recipes[0]), identity(explorer.recipes[1])}
    assert len(reordered & set(result.schedule_hashes)) == expected
    assert result.status == 'PASSED_OBSERVED' and len(set(result.schedule_hashes)) == 4

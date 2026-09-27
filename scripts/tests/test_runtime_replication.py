"""Offline admission/integrity checks for the new descriptive runner; no providers."""
import asyncio
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('runtime_replication', ROOT / 'scripts/experiments/run_runtime_replication.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def priced():
    return runner.Settings(wandb_model=runner.ACTOR, wandb_explorer_model=runner.REASONER,
        wandb_mechanic_model=runner.REASONER, wandb_entity='shreetbohara-quinstreet', wandb_project='Faultlab',
        faultlab_pricing_model=runner.ACTOR, faultlab_pricing_verified=True,
        faultlab_input_dollars_per_million=.55, faultlab_output_dollars_per_million=1.65,
        faultlab_reasoning_pricing_model=runner.REASONER, faultlab_reasoning_pricing_verified=True,
        faultlab_reasoning_input_dollars_per_million=1.31, faultlab_reasoning_output_dollars_per_million=3.96,
        faultlab_dollar_cap=20)


def test_exact_actor_only_worst_case_is_672_requests_and_140448_dollars(tmp_path):
    settings = runner.settings_for_run(priced(), tmp_path, 20)
    assert runner.check_settings(settings) == pytest.approx(.0209)
    assert runner.MAX_CALLS == 672
    assert runner.MAX_CALLS * runner.check_settings(settings) == pytest.approx(14.0448)
    assert settings.faultlab_token_cap == 22_848_000
    assert settings.faultlab_model_call_cap == 672 and not settings.faultlab_aria_publish_enabled


@pytest.mark.parametrize('change', [
    {'faultlab_pricing_verified': False}, {'faultlab_pricing_model': 'other'},
    {'faultlab_reasoning_pricing_verified': False}, {'faultlab_output_dollars_per_million': 1.0},
    {'faultlab_input_dollars_per_million': float('nan')}, {'wandb_model': 'other'},
    {'wandb_project': 'faultlab'}, {'faultlab_actor_context_protocol': 'faultlab-actor-context/v1'},
    {'faultlab_dollar_cap': 14.0},
    {'faultlab_simulator_url': 'http://127.0.0.1:9999'},
])
def test_unpriced_mismatched_or_underfunded_run_is_refused(change):
    with pytest.raises(runner.Refusal):
        runner.check_settings(replace(priced(), **change))


@pytest.mark.parametrize('dollars', [0, -1, 21, float('nan'), float('inf')])
def test_allowance_cannot_expand_or_disable_the_bound(tmp_path, dollars):
    with pytest.raises(runner.Refusal):
        runner.settings_for_run(priced(), tmp_path, dollars)


def test_new_ledger_releases_only_its_unused_scopes_and_reserves_all_actor_requests(tmp_path):
    from app.lab.storage import LabStore
    from app.lab.budgets import CampaignLedger, BudgetExhausted, PROTECTED
    store = LabStore(tmp_path / 'ledger.sqlite3')
    caps = runner.CampaignBudget(model_calls=672, tokens=runner.TOKENS, dollars=20)
    ledger = CampaignLedger(store, 'new-only', caps, dollar_bounds={'actor': .0209})
    for name in PROTECTED:
        ledger.release(name)
    ledger.reserve('replication', 672)
    for _ in range(672):
        ledger.consume_call(reservation='replication')
    assert ledger.used_calls == 672 and ledger.used_dollar_upper_bound == pytest.approx(14.0448)
    with pytest.raises(BudgetExhausted):
        ledger.consume_call(reservation='replication')
    store.close()


def test_actor_only_provider_refuses_other_roles_before_dispatch():
    class Provider:
        calls = []
        async def complete(self, messages, **kwargs):
            self.calls.append(kwargs['role']); return 'actual-response'
    provider = Provider(); wrapped = runner.ActorOnlyProvider(provider)
    for role in ('mechanic', 'explorer', 'invented'):
        with pytest.raises(runner.Refusal):
            asyncio.run(wrapped.complete([], role=role))
    assert provider.calls == []
    assert asyncio.run(wrapped.complete([], role='actor')) == 'actual-response'
    assert provider.calls == ['actor']


def test_public_slots_are_exactly_seven_cases_three_alternating_pairs():
    cases = runner.build_case_manifest('upgrade-v1')['cases']
    slots = runner.planned_slots(cases)
    assert len(slots) == 42 and len({(s['case_id'], s['trial_index'], s['arm']) for s in slots}) == 42
    for pair_index in range(21):
        a, b = slots[2 * pair_index:2 * pair_index + 2]
        assert a['scenario_hash'] == b['scenario_hash'] and a['trial_index'] == b['trial_index']
        assert {a['arm'], b['arm']} == {'B0', 'L'}
        case_index, repeat = divmod(pair_index, 3)
        assert a['arm'] == ('B0' if (case_index + repeat) % 2 == 0 else 'L')


def source_fixture(monkeypatch):
    studies = {}
    rows = []
    for n in range(1, 6):
        sid = runner.SOURCE_STUDY if n == 5 else f'study-{n}'
        campaign = runner.SOURCE_CAMPAIGN if n == 5 else f'campaign-{n}'
        study = {'study_id': sid, 'campaign_id': campaign, 'status': 'COMPLETED',
                 'decision': 'OBSERVED_IMPROVEMENT' if n == 5 else 'NO_CHANGE',
                 'qualified': n == 5, 'selected_candidate_hash': runner.SOURCE_POLICY if n == 5 else None}
        studies[sid] = study
        rows.append({**study, 'attempt': n, 'certified': n == 5, 'post_checks': 'passed'})
    monkeypatch.setattr(runner, 'development_status', lambda store, study:
                        {'status': 'QUALIFIED' if study['qualified'] else 'NOT_QUALIFIED'})
    store = SimpleNamespace(get_record=lambda kind, ident: studies.get(ident))
    return store, studies, {'attempts': rows}


def test_source_is_chosen_by_first_verified_attempt_not_candidate_appearance(monkeypatch):
    store, studies, manifest = source_fixture(monkeypatch)
    # Earlier OBSERVED_IMPROVEMENT without the stronger certificate cannot replace attempt5.
    studies['study-2']['decision'] = manifest['attempts'][1]['decision'] = 'OBSERVED_IMPROVEMENT'
    assert runner.source_selection(store, manifest)['study_id'] == runner.SOURCE_STUDY


@pytest.mark.parametrize('mutation', ['earlier-qualified', 'unresolved', 'wrong-campaign', 'wrong-policy', 'missing-attempt'])
def test_source_selection_refuses_ambiguous_changed_or_missing_provenance(monkeypatch, mutation):
    store, studies, manifest = source_fixture(monkeypatch)
    if mutation == 'earlier-qualified':
        studies['study-2']['qualified'] = True; manifest['attempts'][1]['certified'] = True
    elif mutation == 'unresolved':
        studies['study-3']['status'] = 'RUNNING'
    elif mutation == 'wrong-campaign':
        manifest['attempts'][4]['campaign_id'] = 'foreign'
    elif mutation == 'wrong-policy':
        studies[runner.SOURCE_STUDY]['selected_candidate_hash'] = '0' * 64
    else:
        manifest['attempts'].pop(0)
    with pytest.raises(runner.Refusal):
        runner.source_selection(store, manifest)


def test_source_connection_cannot_mutate_saved_history(tmp_path):
    path = tmp_path / 'source.sqlite3'
    db = sqlite3.connect(path); db.execute('CREATE TABLE records(kind,id,payload)')
    db.execute('INSERT INTO records VALUES(?,?,?)', ('policies', 'p', '{"saved":true}')); db.commit(); db.close()
    store = runner.ReadOnlyStore(path)
    assert store.get_record('policies', 'p') == {'saved': True}
    with pytest.raises(sqlite3.OperationalError, match='readonly'):
        store.db.execute('DELETE FROM records')
    store.close()


def test_seal_binds_exact_current_plan_protocol_and_hashes(tmp_path):
    protocol = tmp_path / 'protocol.md'; protocol.write_text('Declared public replication\n')
    plan_file = tmp_path / 'plan.json'; plan = {'runtime_hash': 'reviewed', 'policy_hash': runner.SOURCE_POLICY}
    runner.write_json(plan_file, plan, exclusive=True)
    args = SimpleNamespace(protocol=protocol, plan_file=plan_file,
        expect_plan_sha256=runner.file_sha(plan_file), expect_protocol_sha256=runner.file_sha(protocol))
    runner.validate_seal(args, plan)
    with pytest.raises(runner.Refusal):
        runner.validate_seal(args, {**plan, 'runtime_hash': 'different'})
    protocol.write_text('Changed after review\n')
    with pytest.raises(runner.Refusal):
        runner.validate_seal(args, plan)
    with pytest.raises(FileExistsError):
        runner.write_json(plan_file, {'replacement': True}, exclusive=True)


def test_existing_output_is_refused_before_reading_source_or_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'read_source', lambda *args: pytest.fail('source should not be accessed'))
    with pytest.raises(runner.Refusal, match='already exists'):
        runner.prepare(SimpleNamespace(output=tmp_path))


def world_fixture(tmp_path, *, received='attempt-1', report_tick=1, report=True, scored_missing=True, masked=False):
    from app.lab.storage import LabStore
    store = LabStore(tmp_path / 'lab.sqlite3')
    fault_spec = {'primitives': ([{'kind': 'F1'}] if masked else [])}
    trial = SimpleNamespace(episode_id='episode-1', world_id='world-1', scenario_hash=runner.content_hash(fault_spec),
                            outcome='COMPLETED' if report else 'VIOLATION',
                            failed_checks=[] if report or not scored_missing else ['C5', 'C6', 'C7'])
    store.put_record('episodes', trial.episode_id, {'campaign_id': 'campaign-1',
                     'report': {'original': True} if report else None, 'verdict': {'decision_tick': 1}})
    store.append_event(trial.episode_id, tick=1, type='tool_dispatched', call_id='call-1',
                       payload={'attempt_id': 'attempt-1'})
    if masked:
        store.append_event(trial.episode_id, tick=1, type='observation_delivered', call_id='call-1',
                           payload={'observation': {'result': {'transport': 'ok'}}})
    if report:
        store.append_event(trial.episode_id, tick=report_tick, type='report_submitted')
    db = sqlite3.connect(tmp_path / 'world-1.sqlite3')
    db.execute('CREATE TABLE events(value)'); db.execute('CREATE TABLE state(id,value)')
    db.execute('INSERT INTO events VALUES(?)', (json.dumps({'type': 'http_attempt', 'payload': {'attempt_id': received}}),))
    state = {'episode_id': trial.episode_id, 'world_id': trial.world_id, 'decision_tick': 1,
             'fault_spec': fault_spec, 'fault_executions': [{'fault_id': 'fault-1', 'triggered': True, 'attempt_id': 'attempt-1'}] if masked else []}
    db.execute('INSERT INTO state VALUES(1,?)', (json.dumps(state),)); db.commit(); db.close()
    return store, trial


@pytest.mark.parametrize('change', [{'received': 'foreign-attempt'}, {'report_tick': 2},
                                    {'report': False, 'scored_missing': False}, {'masked': True}])
def test_world_integrity_refuses_equal_count_wrong_id_clock_masking_or_unscored_missing_report(tmp_path, change):
    store, trial = world_fixture(tmp_path, **change)
    try:
        with pytest.raises(runner.Refusal):
            runner.check_world(store, trial, tmp_path)
    finally:
        store.close()


@pytest.mark.parametrize('report', [True, False])
def test_original_scored_negative_report_outcome_is_retained_not_repaired(tmp_path, report):
    store, trial = world_fixture(tmp_path, report=report)
    try:
        result = runner.check_world(store, trial, tmp_path)
        assert result['report_present'] == report and result['attempts'] == 1
        assert (store.get_record('episodes', trial.episode_id)['report'] is not None) == report
    finally:
        store.close()


@pytest.mark.parametrize('condition,expected,trial_count,attempt_count', [
    ('untriggered', 'INCOMPLETE', 42, 42),
    ('missing-report', 'COMPLETED', 42, 42),
    ('infrastructure', 'INCOMPLETE', 1, 2),
])
def test_real_evaluator_orchestration_keeps_fixed_slots_and_preserves_negative_or_partial_results(
        tmp_path, monkeypatch, condition, expected, trial_count, attempt_count):
    """Real coordinator/evaluator/ledger, fake boundary I/O; never contact a service."""
    from unittest.mock import AsyncMock
    from app.contracts.models import RecoveryPolicy, TrialResult, Usage
    from app.lab.coordinator import LabCoordinator
    from app.lab.storage import LabStore
    from app.lab.policies import PolicyRepository
    import run_full_loop
    import slot2_probe
    import check_clock_drift

    original = LabStore(':memory:')
    baseline = PolicyRepository(original).baseline().model_dump(mode='json'); original.close()
    content = RecoveryPolicy(parent_version='policy-v0', rules=[{
        'hook': 'before_final_report', 'when': 'always', 'steps': [{'op': 'read_order'}]}])
    policy_hash = runner.content_hash(content)
    monkeypatch.setattr(runner, 'SOURCE_POLICY', policy_hash)
    policy = runner.PolicyVersion(version='policy-fixture', parent_version='policy-v0',
        content=content, policy_hash=policy_hash, author='mechanic', raw_proposal_ref='proposal-fixture',
        development_episode_ids=[], decision='PROPOSED').model_dump(mode='json')
    output = tmp_path / 'new-run'; protocol = tmp_path / 'protocol.md'; protocol.write_text('fixture')
    settings = runner.settings_for_run(replace(priced(), wandb_api_key='offline-fixture',
        faultlab_confirmed_entity='shreetbohara-quinstreet', faultlab_live_enabled=True), output, 20)
    caps = runner.CampaignBudget(model_calls=672, tokens=runner.TOKENS, dollars=20)
    configuration = runner.frozen_configuration(settings, caps, 'live-v1')
    cases = runner.build_case_manifest('upgrade-v1')['cases']
    plan = {'source': {'preserved': True}, 'gate_freeze': {'fixture': True},
        'configuration_hash': runner.content_hash(configuration), 'cases': cases,
        'slots': runner.planned_slots(cases), 'actor_call_dollar_bound': .0209,
        'harness_sha256': runner.file_sha(runner.__file__), 'protocol_sha256': runner.file_sha(protocol),
        'helper_sha256': runner.helper_hashes(), 'task_text': 'Upgrade and confirm', 'order_id': 'order-fixture'}
    source = {'baseline': baseline, 'policy': policy}
    args = SimpleNamespace(output=output, protocol=protocol, source_store=tmp_path / 'source.sqlite3',
                           worlds_dir=tmp_path / 'worlds')
    dispatched = []
    class Guard:
        def bind(self, address): assert address == ('127.0.0.1', 8000)
        def close(self): pass
    monkeypatch.setattr(run_full_loop, 'check_backend_process', lambda port:
        {'processes': [{'command': 'uvicorn app.simulator.main:app --timeout-keep-alive 75'}]})
    monkeypatch.setattr(run_full_loop, 'gate_freeze', lambda: {'fixture': True})
    monkeypatch.setattr(slot2_probe, 'live_experiment_processes', lambda: [])
    monkeypatch.setattr(runner, 'read_source', lambda path: (source, plan['source']))
    monkeypatch.setattr(runner, 'check_world', lambda store, trial, path: {'verified': True})
    monkeypatch.setattr(check_clock_drift, 'scan', lambda *args, **kwargs:
        {'scored': trial_count, 'drifted': [], 'masked': [], 'missing_worlds': 0})
    monkeypatch.setattr(LabCoordinator, 'require_simulator', AsyncMock())
    async def get_runner(coordinator, live):
        assert live
        async def evidence(episode_id, context, **kwargs):
            return SimpleNamespace(source='weave_verified', source_project=runner.PROJECT, root_call_id='root-' + episode_id)
        coordinator.evidence_gateway = SimpleNamespace(get=evidence)
        coordinator.evaluation_publisher = None
        class LocalRunner:
            provider = SimpleNamespace(close=AsyncMock())
            world_client = SimpleNamespace(close=AsyncMock())
            async def run(self, campaign, recipe, chosen, **kwargs):
                dispatched.append(kwargs['episode_id'])
                kwargs['ledger'].consume_call(reservation=kwargs['reservation'])
                if condition == 'infrastructure' and len(dispatched) == 2:
                    raise OSError('Synthetic world creation failure')
                negative = condition == 'missing-report' and len(dispatched) == 1
                scheduled = bool(recipe.primitives)
                untriggered = condition == 'untriggered' and len(dispatched) == 7
                trial = TrialResult(episode_id=kwargs['episode_id'], world_id='world-' + str(len(dispatched)),
                    scenario_hash=runner.content_hash(recipe), policy_hash=chosen.policy_hash, arm=kwargs['arm'],
                    trial_index=kwargs['trial_index'], lifecycle='COMPLETED',
                    outcome='VIOLATION' if negative else 'COMPLETED', failed_checks=['C5', 'C6', 'C7'] if negative else [],
                    fault_scheduled=scheduled, fault_triggered=scheduled and not untriggered, usage=Usage())
                coordinator.store.put_record('episodes', trial.episode_id, {'campaign_id': campaign.campaign_id,
                    'episode_id': trial.episode_id, 'world_id': trial.world_id, 'report': None if negative else {'original': True}})
                coordinator.store.put_record('trials', trial.episode_id, trial, immutable=True)
                return trial
        return LocalRunner(), True
    monkeypatch.setattr(LabCoordinator, '_get_runner', get_runner)
    # Create the event loop before replacing socket: asyncio's self-pipe must remain real.
    # The runner only constructs one socket, the admission guard.
    with asyncio.Runner() as loop_runner:
        with monkeypatch.context() as guard_patch:
            guard_patch.setattr(runner.socket, 'socket', lambda *args, **kwargs: Guard())
            result = loop_runner.run(runner.execute(args, settings, caps, source, plan))
    assert result['status'] == expected, result
    assert len(result['trials']) == trial_count and len(result['attempted_slots']) == attempt_count
    assert len(dispatched) == attempt_count and len(result['unattempted_slots']) == 42 - attempt_count
    assert result['accepted'] is False and result['qualified'] is False and result['active_policy'] == 'policy-v0'
    assert result['accounting']['charged_model_calls'] == attempt_count
    assert json.loads((output / 'result.json').read_text())['status'] == expected
    if condition == 'missing-report':
        assert result['failed_checks'][0]['trial']['failed_checks'] == ['C5', 'C6', 'C7']
        assert result['evaluation_batches'][0]['decision'] == 'NO_CHANGE'
    if condition == 'untriggered':
        assert len(result['untriggered_fault_trials']) == 1
        assert result['evaluation_batches'][0]['decision'] == 'INCOMPLETE'
    if condition == 'infrastructure':
        assert result['failure']['code'] == 'EXECUTION_ERROR'
        assert 'Synthetic world creation failure' not in (output / 'result.json').read_text()

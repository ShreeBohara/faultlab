"""A regression assertion must agree with the episode that was actually saved.

This is an explicit offline callback-contract fixture, not measured agent behavior.
No provider or historical store is used.
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.contracts.models import (CampaignBudget, CheckResult, Counterexample, Episode,
    FaultExecution, FaultSpec, TrialResult, Usage, Verdict, content_hash)
from app.integrations.registry import AgentRegistry
from app.integrations.regression_runner import RegressionRunner
from app.lab.configuration import frozen_configuration
from app.lab.policies import PolicyRepository
from app.lab.regressions import RegressionCompiler
from app.lab.storage import LabStore


@pytest.fixture
def fixed_runner(tmp_path):
    store = LabStore(':memory:')
    config = frozen_configuration(Settings(wandb_model='openai/gpt-oss-120b'), CampaignBudget(), 'live-v1')
    registry = AgentRegistry(store)
    registration = registry.register_reference(config)
    baseline = PolicyRepository(store).baseline()
    campaign = SimpleNamespace(campaign_id='offline-callback-contract', configuration_hash=content_hash(config))
    recipe = FaultSpec.model_validate_json('{"seed":42,"primitives":[{"kind":"F1","target_tool":"update_order","target_service":"orders","occurrence":1,"parameters":{"response_delay_ms":1500}},{"kind":"F4","target_tool":"send_confirmation","target_service":"notifications","occurrence":1,"parameters":{"failure_count":1}}]}')
    counter = Counterexample(counterexample_id='offline-callback-counterexample', campaign_id=campaign.campaign_id,
        agent_registration_id=registration.registration_id, source_episode_id='offline-source', target_invariant='C3',
        scenario_hash=content_hash(recipe), configuration_hash=campaign.configuration_hash,
        report_ref=None, verdict_ref='offline-source-verdict')
    store.put_record('private_episode_inputs', 'offline-source', {'fixture_id': 'standard-v1'})
    compiler = RegressionCompiler(store)
    bundle = compiler.compile(campaign, counter, baseline, recipe, recipe, [])
    directory = tmp_path / 'bundle'
    compiler.export(bundle.bundle_id, directory)
    try:
        yield store, RegressionRunner(store, registry), directory, config, registration
    finally:
        store.close()


@pytest.mark.parametrize('corruption', [None, 'coherent_unknown_cost', 'unknown_cost', 'lifecycle', 'outcome', 'failed_checks', 'usage', 'scenario',
    'private_recipe', 'empty_fault_ledger', 'partial_fault_ledger', 'duplicate_fault_ledger', 'arm', 'index', 'model', 'replay_source'])
def test_returned_trial_cannot_contradict_saved_episode(fixed_runner, corruption):
    store, runner, directory, configuration, registration = fixed_runner
    calls = []
    async def fresh(recipe, registered, policy, index, *, fixture_id):
        calls.append(index)
        usage = Usage(model_calls=2, actor_calls=2, http_attempts=3, ticks=3,
            cost_dollars=None if corruption == 'coherent_unknown_cost' else 0.01)
        result = TrialResult(episode_id=f'new-episode-{index}', world_id=f'new-world-{index}',
            scenario_hash=content_hash(recipe), policy_hash=policy.policy_hash, arm='B0', trial_index=index,
            lifecycle='COMPLETED', outcome='VIOLATION', failed_checks=['C3'], fault_scheduled=True,
            fault_triggered=True, usage=usage)
        verdict = Verdict(verdict_id=f'new-verdict-{index}', episode_id=result.episode_id, outcome='VIOLATION',
            checks=[CheckResult(check_id=f'C{i}', passed=i != 3, category='offline_fixture') for i in range(1, 9)],
            supported_completion=False, useful_resolution='invalid', upgrade_effects=1, notification_effects=1,
            decision_tick=3, horizon_tick=8, scorer_hash=configuration['scorer_hash'],
            fault_executions=[FaultExecution(fault_id=f'fault-{n}', triggered=True, trigger_tick=n + 1,
                call_id=f'new-call-{index}-{n}', attempt_id=f'new-attempt-{index}-{n}') for n in (1, 2)])
        episode = Episode(campaign_id='offline-callback-contract', episode_id=result.episode_id,
            world_id=result.world_id, task_id=f'new-task-{index}', origin='faultlab_evaluation', split='development',
            arm='B0', source_mode='offline_fixture', experiment_purpose='reproduction', trial_index=index,
            study_id='callback-test', evidence_context_id='callback-test', execution_epoch=0,
            agent_registration_id=registered.registration_id, scenario_hash=result.scenario_hash,
            policy_hash=policy.policy_hash, policy_version=policy.version, model=registered.model,
            configuration_hash=registered.configuration_hash, lifecycle='COMPLETED', verdict=verdict, usage=usage)
        if corruption == 'lifecycle': episode.lifecycle = 'LAB_ERROR'
        if corruption == 'outcome': episode.verdict.outcome = 'LAB_ERROR'
        if corruption == 'failed_checks': episode.verdict.checks[2].passed = True
        if corruption == 'usage': episode.usage = Usage(model_calls=4, actor_calls=4, http_attempts=3, ticks=3, cost_dollars=0.02)
        if corruption == 'unknown_cost': episode.usage = usage.model_copy(update={'cost_dollars': None})
        if corruption == 'scenario': episode.scenario_hash = '0' * 64
        if corruption == 'empty_fault_ledger': episode.verdict.fault_executions = []
        if corruption == 'partial_fault_ledger': episode.verdict.fault_executions[1].triggered = False
        if corruption == 'duplicate_fault_ledger': episode.verdict.fault_executions[1].fault_id = episode.verdict.fault_executions[0].fault_id
        if corruption == 'arm': episode.arm = 'L'
        if corruption == 'index': episode.trial_index = (index + 1) % 3
        if corruption == 'model': episode.model = 'another-reviewed-model'
        if corruption == 'replay_source': episode.source_mode = 'replay'
        actual_recipe = FaultSpec(seed=42, primitives=[]) if corruption == 'private_recipe' else recipe
        store.put_record('episodes', result.episode_id, episode)
        store.put_record('private_episode_inputs', result.episode_id, {'fixture_id': fixture_id, 'recipe': actual_recipe.model_dump(mode='json')})
        store.put_record('trials', result.episode_id, result)
        return result
    execution = asyncio.run(runner.execute(directory, configuration, registration.registration_id,
        explicit_live=True, profile_id='sandbox-v1', run_fresh=fresh))
    assertions = store.get_record('regression_assertions', execution.execution_id)
    if corruption in (None, 'coherent_unknown_cost'):
        assert execution.status == 'COMPLETED' and calls == [0, 1, 2]
        assert assertions['reproduced'] and assertions['source_modes'] == ['offline_fixture']
        assert assertions['valid_trials'] == assertions['target_failures'] == 3
        assert assertions['lab_integrity_errors'] == 0
        assert execution.usage.cost_dollars == (None if corruption else pytest.approx(0.03))
        return
    assert execution.status == 'INCOMPLETE', {'corruption': corruption, 'status': execution.status, 'assertions': assertions}
    assert calls == [0], 'A mismatched saved trial must be retained and stop the batch without reroll'
    assert not assertions['reproduced']
    assert assertions['target_failures'] == assertions['valid_trials'] == 0
    assert assertions['lab_integrity_errors'] == 1
    diagnostic = store.get_record('regression_trial_errors', execution.execution_id)
    assert len(diagnostic['errors']) == 1 and diagnostic['errors'][0]['episode_id'] == execution.episode_ids[0]
    if corruption == 'usage':
        assert execution.usage.model_calls == execution.usage.actor_calls == 4, 'Keep the higher saved charge rather than losing attempted calls'
        assert execution.usage.cost_dollars == pytest.approx(0.02)
    if corruption == 'unknown_cost':
        assert execution.usage.cost_dollars is None, 'Unknown saved cost cannot become known from a contradictory callback'

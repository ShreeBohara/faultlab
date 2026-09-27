"""Offline reference inputs through the original production learning workflow.

Run from backend with ``../.venv/bin/python tests/lab/original_loop_fixture.py
--output ../artifacts/product-loop-2026-09-27/run-name``. No provider, trace,
remote evidence, or generated-policy claim is made. The real simulator serves
HTTP on an owned ephemeral localhost port; every world and lab record is new.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from contextlib import contextmanager
import importlib
import hashlib
import json
from pathlib import Path
import socket
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import uvicorn

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import Settings
from app.contracts.models import CampaignRequest, FaultSpec, canonical_json, content_hash
from app.adapters.business_tools import WorldClient
from app.lab.coordinator import LabCoordinator
from app.lab.evidence import EvidenceGateway
from app.lab.policies import PolicyRepository
from app.lab.runner import EpisodeRunner
from app.providers.runtime import RuntimeGeneration


# This is the reviewed tokenizer/request profile exercised, never a claim that
# DeepSeek supplied a response. Scripted transport and offline source labels are
# recorded separately; unknown IDs use a byte ceiling that cannot fit diagnosis.
MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
CONTROL = 'offline-fixture-local-control-only'


def delayed_upgrade(delay=4):
    return {'seed': 27, 'primitives': [{'kind': 'F2', 'target_tool': 'update_order',
        'target_service': 'orders', 'occurrence': 1, 'parameters': {
            'completion_delay_ticks': delay, 'terminal_status': 'SUCCEEDED', 'failure_code': None}}]}


def reference_policy(parent, *, weak=False):
    """Generic operation reconciliation, written before observing fixture results."""
    if weak:
        rules = [{'hook': 'before_final_report', 'when': 'always', 'steps': [{'op': 'read_order'}]}]
    else:
        rules = []
        for service, hook, read, condition in (
            ('orders', 'after_upgrade_response', 'read_current_operation', 'upgrade_outcome_uncertain'),
            ('notifications', 'after_notification_response', 'read_notification_operation', 'notification_outcome_uncertain'),
        ):
            rules.append({'hook': hook, 'when': condition, 'steps': [
                {'op': read, 'only_if': condition},
                {'op': 'retry_original_request', 'service': service, 'only_if': condition},
                {'op': 'wait_ticks', 'ticks': 2, 'only_if': condition},
                {'op': read, 'only_if': condition},
                {'op': 'wait_ticks', 'ticks': 2, 'only_if': condition},
                {'op': read, 'only_if': condition},
                {'op': 'wait_ticks', 'ticks': 2, 'only_if': condition},
                {'op': read, 'only_if': condition},
            ]})
        rules.append({'hook': 'before_confirmation', 'when': 'always', 'steps': [
            {'op': 'require_receipt', 'service': 'orders', 'status': 'SUCCEEDED'}]})
    return {'parent_version': parent, 'rules': rules}


def public_actor_answer(messages):
    """Deliberately premature confirmation; all decisions use actual public input.

    This pure function receives no fixture mode, scenario, world, phase, policy,
    or scorer. It truthfully reports the operation evidence it was shown. The
    intended baseline defect is sending confirmation while upgrade is pending.
    """
    decoded = []
    for message in messages:
        if message['role'] != 'user':
            continue
        try:
            value = json.loads(message['content'])
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            decoded.append(value)
    task = next(value['task'] for value in decoded if 'task' in value)
    turn = next(value for value in reversed(decoded) if 'observations' in value)
    observations = turn['observations']
    tools = [row['result']['tool'] for row in observations]
    blocked = any('blocked_action' in value for value in decoded)

    def status(service):
        operation = task['upgrade_operation_id' if service == 'orders' else 'notification_operation_id']
        matching = [row['result'] for row in observations if row['result'].get('operation_id') == operation]
        for result in reversed(matching):
            receipt = (result.get('data') or {}).get('receipt')
            if receipt and receipt['operation_id'] == operation and receipt['service'] == service:
                return receipt['status']
        write = 'update_order' if service == 'orders' else 'send_confirmation'
        return ((matching[-1].get('status') or 'UNKNOWN') if matching else
                'UNKNOWN' if write in tools else 'NOT_STARTED')

    upgrade, notification = status('orders'), status('notifications')
    if not turn['final_report_required']:
        if 'get_order' not in tools:
            return {'kind': 'tool', 'tool': 'get_order', 'arguments': {}}
        if 'update_order' not in tools:
            return {'kind': 'tool', 'tool': 'update_order', 'arguments': {'desired_shipping': 'express'}}
        if 'send_confirmation' not in tools and not blocked and upgrade != 'FAILED':
            return {'kind': 'tool', 'tool': 'send_confirmation', 'arguments': {}}
    if upgrade == 'FAILED':
        overall, notification, next_action = 'CORRECTLY_REJECTED', 'NOT_REQUIRED', {'kind': 'NONE'}
    elif upgrade == notification == 'SUCCEEDED':
        overall, next_action = 'COMPLETED', {'kind': 'NONE'}
    else:
        overall = 'SAFE_UNRESOLVED'
        service = 'notifications' if upgrade == 'SUCCEEDED' and 'send_confirmation' in tools else 'orders'
        next_action = {'kind': 'CHECK_EXISTING_NOTIFICATION' if service == 'notifications' else 'CHECK_EXISTING_UPGRADE',
                       'operation_id': task['notification_operation_id' if service == 'notifications' else 'upgrade_operation_id']}
    return {'kind': 'report', 'report': {'upgrade_outcome': upgrade, 'notification_outcome': notification,
        'overall': overall, 'next_action': next_action, 'evidence_ids': [row['evidence_id'] for row in observations]}}


class ScriptedProvider:
    """Declared replacement of only external model generation transport."""
    def __init__(self, mode):
        self.mode = mode
        self.calls = Counter()
        self.pause_after_write = asyncio.Event()
        self.release = asyncio.Event()
        self.paused = False

    def role_model(self, role):
        return MODEL

    async def complete(self, messages, *, role='actor', **kwargs):
        self.calls[role] += 1
        context = json.loads(messages[-1]['content'])
        if role == 'actor':
            # Interruption scheduling uses only a delivered write observation;
            # the actor answer itself remains the same pure public-input function.
            if (self.mode == 'interrupted' and not self.paused and
                    any(row['result']['tool'] == 'update_order' for row in context['observations'])):
                self.paused = True
                self.pause_after_write.set()
                await self.release.wait()
            answer = public_actor_answer(messages)
        elif role == 'explorer':
            delay = (3, 4, 5, 6)[context['proposal_index'] % 4] if context.get('purpose') == 'challenge' else 4
            answer = {'fault_spec': delayed_upgrade(delay), 'hypothesis':
                      'Handwritten offline fixture: confirmation can precede a delayed upgrade.'}
        elif 'intervention_ids' in context:
            answer = {'proposed_kind': 'POLICY_GAP', 'hypothesis':
                      'Handwritten offline fixture: removing delay removes premature confirmation.',
                      'evidence_ids': context['evidence_ids'][:1],
                      'requested_intervention_id': context['intervention_ids'][0]}
        elif context['candidate_history']:
            answer = {'no_change_reason': 'Offline fixture has no additional handwritten candidate.'}
        else:
            answer = {'candidate': reference_policy(context['parent_version'], weak=self.mode == 'rejected'),
                      'explanation': 'MANUAL REFERENCE FIXTURE, not generated learning: reconcile original operations and require an upgrade receipt before confirmation.'}
        # Zero represents no billed provider invocation; no token measurement is invented.
        return RuntimeGeneration(canonical_json(answer), MODEL, cost_usd=0.0)


class OfflineEvidence(EvidenceGateway):
    async def get(self, episode_id, context, **kwargs):
        return await super().get(episode_id, context, **{**kwargs, 'require_remote': False})


class OfflineRunner(EpisodeRunner):
    async def run(self, *args, **kwargs):
        return await super().run(*args, **{**kwargs, 'source_mode': 'offline_fixture'})


class ManualPolicies(PolicyRepository):
    def proposal(self, *args, **kwargs):
        return super().proposal(*args, **{**kwargs, 'author': 'manual'})


@contextmanager
def localhost_simulator(path, settings):
    # main.py constructs its default app at import. Bind explicit empty fixture
    # settings during that import so it cannot read .env or open historical worlds.
    with patch.object(Settings, 'from_env', return_value=settings):
        create_app = importlib.import_module('app.simulator.main').create_app
    app = create_app(database_dir=path / 'worlds', control_token=CONTROL, settings=settings)
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', lifespan='off'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(.01)
        if not server.started:
            raise RuntimeError('Owned localhost simulator did not start')
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
        if thread.is_alive():
            raise RuntimeError('Owned localhost simulator did not stop')


def fixture_settings(path):
    return Settings(wandb_api_key='offline-fixture-no-provider', wandb_entity='offline-fixture',
        wandb_project='original-loop', wandb_model=MODEL, faultlab_artifact_dir=str(path),
        faultlab_control_token=CONTROL, faultlab_live_enabled=True,
        faultlab_confirmed_entity='offline-fixture', faultlab_input_dollars_per_million=0,
        faultlab_output_dollars_per_million=0, faultlab_pricing_model=MODEL,
        faultlab_pricing_verified=True, faultlab_dollar_cap=100)


async def exercise(path, mode):
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    harness = Path(__file__).read_bytes()
    (path / 'fixture-source.py').write_bytes(harness)
    declaration = {'schema_version': 'faultlab-offline-original-loop-fixture/v1', 'mode': mode,
        'evidence_class': 'OFFLINE_MANUAL_REFERENCE_NOT_GENERATED_LEARNING',
        'scripted_transport': True, 'source_mode': 'offline_fixture', 'policy_author': 'manual',
        'remote_evidence': False, 'provider_calls': 0, 'provider_spend_dollars': 0,
        'fixture_source_sha256': hashlib.sha256(harness).hexdigest(),
        'configured_model': MODEL,
        'configured_model_identity_meaning': 'Reviewed tokenizer/request profile only, no model generation occurred.'}
    (path / 'fixture-declaration.json').write_text(json.dumps(declaration, indent=2) + '\n')
    settings = fixture_settings(path)
    provider = ScriptedProvider(mode)
    with localhost_simulator(path, settings) as url:
        coordinator = LabCoordinator(settings)
        world = WorldClient(url, CONTROL)
        coordinator.runner = OfflineRunner(coordinator.store, world, provider)
        coordinator.policies = ManualPolicies(coordinator.store)
        coordinator.evidence_gateway = OfflineEvidence(coordinator.store, 'offline-fixture/original-loop')
        coordinator.store.put_record('offline_fixture_declarations', mode, declaration, immutable=True)
        campaign = coordinator.create(CampaignRequest(task_text='Upgrade this order to express and send its confirmation.',
            order_id='order-reference', mode='learn', config_profile_id='live-v1'))
        before = {'campaign': campaign.model_dump(mode='json'),
                  'accepted_pointer': coordinator.store.get_pointer('accepted-policy:' + campaign.configuration_hash)}
        try:
            await coordinator.start(campaign.campaign_id)
            if mode == 'interrupted':
                await asyncio.wait_for(provider.pause_after_write.wait(), timeout=15)
                await coordinator.stop(campaign.campaign_id)
                provider.release.set()
            await asyncio.wait_for(coordinator.tasks[campaign.campaign_id], timeout=240)
            summary = summarize(coordinator, campaign.campaign_id, provider, before)
            # A coordinator restart must not replay any episode or change a terminal
            # verdict/pointer. A fresh campaign picks up only a real accepted pointer.
            count_before = len(coordinator.store.list_records('episodes'))
            restarted = LabCoordinator(settings, store=coordinator.store, runner=coordinator.runner)
            fresh = restarted.create(CampaignRequest(task_text=campaign.task_text, order_id=campaign.order_id,
                mode='learn', config_profile_id='live-v1'))
            summary['restart'] = {'historical_campaign': restarted.get(campaign.campaign_id).model_dump(mode='json'),
                'new_campaign_id': fresh.campaign_id, 'new_active_policy_version': fresh.active_policy_version,
                'episodes_replayed': len(coordinator.store.list_records('episodes')) - count_before,
                'accepted_pointer': restarted.store.get_pointer('accepted-policy:' + campaign.configuration_hash)}
            if fresh.active_policy_version != 'policy-v0':
                trial = await coordinator.runner.run(fresh, FaultSpec.model_validate(delayed_upgrade()),
                    restarted.policies.get(fresh.active_policy_version), purpose='source_validation', arm='L')
                summary['restart']['fresh_policy_trial'] = trial.model_dump(mode='json')
                summary['restart']['fresh_policy_snapshots'] = coordinator.store.get_record('private_snapshots', trial.episode_id)
                from app.lab.regression_executions import execute_regression
                regression = next(row for row in coordinator.store.list_records('regressions')
                                  if row['artifact_kind'] == 'accepted_policy_bundle')
                registration = coordinator.store.get_record('campaign_registrations', campaign.campaign_id)
                execution = await execute_regression(restarted, regression['regression_id'], SimpleNamespace(
                    policy_version=fresh.active_policy_version, execute_live=True,
                    execution_profile_id='sandbox-v1', agent_registration_id=registration['registration_id']))
                await asyncio.wait_for(restarted.tasks[execution.execution_id], timeout=60)
                saved_execution = coordinator.store.get_record('regression_executions', execution.execution_id)
                summary['restart']['bundle_execution'] = saved_execution
                summary['restart']['bundle_execution_errors'] = coordinator.store.list_records('regression_execution_errors')
                summary['restart']['bundle_trials'] = [coordinator.store.get_record('trials', episode_id)
                                                       for episode_id in saved_execution['episode_ids']]
            summary['total_scripted_generation_calls_including_restart'] = dict(provider.calls)
            summary['elapsed_seconds'] = time.monotonic() - started
            summary['fixture_declaration'] = declaration
            # Export the compiler's exact bytes so the artifact can be reviewed
            # without querying SQLite; no compiler output is repaired or replaced.
            from app.lab.regressions import RegressionCompiler
            for bundle in coordinator.store.list_records('bundles'):
                RegressionCompiler(coordinator.store).export(bundle['bundle_id'], path / 'exports' / bundle['bundle_id'])
            (path / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
            return summary
        finally:
            provider.release.set()
            await world.close()
            coordinator.store.close()


def summarize(coordinator, campaign_id, provider, before):
    store = coordinator.store
    campaign = coordinator.get(campaign_id)
    episodes = [row for row in store.list_records('episodes') if row['campaign_id'] == campaign_id]
    return {'schema_version': 'faultlab-offline-original-loop-fixture/v1', 'mode': provider.mode,
        'evidence_class': 'OFFLINE_MANUAL_REFERENCE_NOT_GENERATED_LEARNING', 'provider_calls': 0,
        'configured_model_identity_meaning': 'Reviewed DeepSeek V4 tokenizer/request profile only; all responses are handwritten fixture JSON, no DeepSeek generation occurred.',
        'provider_spend_dollars': 0, 'scripted_generation_calls': dict(provider.calls),
        'token_measurement': 'Unavailable: scripted local inputs, no inference usage claimed',
        'substitutions': ['External model transport returns declared scripted Actor/Explorer/Mechanic JSON.',
            'EvidenceGateway uses its real require_remote=False local_only branch; no remote verification.',
            'Episode source_mode is offline_fixture; policy author is manual.',
            'Explicit zero-cost fake live-profile settings exercise normal start admission with an injected runner.'],
        'production_boundaries': ['coordinator start/state/stop/budget/restart', 'Actor parsing and evidence citation decoding',
            'real localhost HTTP simulator, clock, fault execution and private world persistence',
            'broker retry/identity journal', 'policy interpreter', 'unchanged C1-C8 scorer',
            'Explorer/Mechanic prompt/parsing and bounded search', 'reproduction and fixed reduction',
            'real diagnostic control/treatment', 'paired source/challenge/promotion gates',
            'atomic accepted policy pointer', 'regression compiler and saved bundle files'],
        'before': before, 'campaign': campaign.model_dump(mode='json'), 'active_scheduler_id': coordinator.active_id,
        'configuration': store.get_record('configurations', campaign.configuration_hash),
        'accepted_pointer': store.get_pointer('accepted-policy:' + campaign.configuration_hash),
        'budget': store.get_record('budgets', campaign_id),
        'episode_counts': dict(Counter(row['experiment_purpose'] for row in episodes)),
        'lifecycle_counts': dict(Counter(row['lifecycle'] for row in episodes)),
        'outcome_counts': dict(Counter(row['verdict']['outcome'] if row.get('verdict') else 'NONE' for row in episodes)),
        'outcome_interpretation': 'Raw referee outcomes are diagnostic only for INTERRUPTED/LAB_ERROR episodes; they cannot qualify an agent failure, candidate acceptance or policy repair.',
        'evidence_sources': dict(Counter(row['source'] for row in store.list_records('evidence'))),
        'records': {kind: store.list_records(kind) for kind in ('counterexamples', 'reductions', 'diagnostics',
            'interventions', 'source_validation_results', 'challenges', 'candidate_qualifications', 'promotion_decisions',
            'policies', 'regressions', 'bundles', 'execution_errors', 'evaluation_errors')},
        'episodes': [{'episode': row, 'integrity': store.get_record('private_world_integrity', row['episode_id']),
            'snapshots': store.get_record('private_snapshots', row['episode_id'])} for row in episodes]}


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('accepted', 'rejected', 'interrupted', 'all'), default='all')
    args = parser.parse_args()
    for mode in ('accepted', 'rejected', 'interrupted') if args.mode == 'all' else (args.mode,):
        result = await exercise(args.output / mode, mode)
        print(json.dumps({'mode': mode, 'state': result['campaign']['state'],
            'episodes': sum(result['episode_counts'].values()), 'policy': result['campaign']['active_policy_version'],
            'errors': result['records']['execution_errors']}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())

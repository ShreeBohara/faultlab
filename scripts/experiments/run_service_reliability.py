#!/usr/bin/env python3
"""One sealed, descriptive replication of a saved policy on public upgrade cases.

Dry by default; reads the historical store without opening a writer. Live execution
uses a new store and reserves port 8000, so the dashboard scheduler must be stopped.
No discovery, proposal, qualification, promotion, hidden partition, or resume path.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import replace
from hashlib import sha256
import json
import math
from pathlib import Path
import signal
import socket
import sqlite3
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.agents.progress import ACTOR_CONTEXT_PROTOCOL_V4
from app.config import Settings
from app.contracts.models import CampaignBudget, CampaignRequest, EpisodeBudget, PolicyVersion, canonical_json, content_hash, utc_now
from app.lab.configuration import frozen_configuration
from app.lab.completion_study import build_case_manifest
from app.lab.evaluation import PairedEvaluator, paired_complete
from app.lab.evidence import EvidenceContext
from app.lab.policy_status import development_status
from app.lab.reproduction import valid_trial

SOURCE_STUDY = 'completion-study-a0c535bb041c413da1d4b34fb513252c'
SOURCE_CAMPAIGN = 'campaign-ba37f75678284372ad5dcc2b3635481e'
SOURCE_POLICY = '04721232187d99677e698ce59b45ccd76ad2cb7c43854eff4c6a1e46163c548c'
SOURCE_MANIFEST = ROOT / 'artifacts/phase28-2026-09-26/upgrade-loop-manifest.json'
DEFAULT_OUTPUT = ROOT / 'artifacts/service-reliability-2026-09-27'
PROJECT = 'shreetbohara-quinstreet/Faultlab'
ACTOR = 'deepseek-ai/DeepSeek-V3.1'
REASONER = 'deepseek-ai/DeepSeek-V4-Pro-0813'
EPISODES = 42
MAX_CALLS = EPISODES * 8 * 2  # Existing blind transport retry, never a pair rerun.
TOKENS = MAX_CALLS * 34000
MAX_DOLLARS = 20.0
HELPERS = ('run_full_loop.py', 'slot2_probe.py', 'check_clock_drift.py', 'gate_freeze.py')


class Refusal(ValueError):
    """Static, safe refusal; never include provider exception text."""


def require(condition, message):
    if not condition:
        raise Refusal(message)


def file_sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def helper_hashes():
    return {name: file_sha(Path(__file__).with_name(name)) for name in HELPERS}


class ReadOnlyStore:
    def __init__(self, path):
        self.db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)

    def get_record(self, kind, ident):
        row = self.db.execute('SELECT payload FROM records WHERE kind=? AND id=?', (kind, ident)).fetchone()
        return json.loads(row[0]) if row else None

    def close(self):
        self.db.close()


def source_selection(store, manifest):
    """First strong certificate by recorded attempt order, never by policy appearance."""
    rows = manifest.get('attempts') or []
    require(len(rows) >= 5 and [r.get('attempt') for r in rows[:5]] == list(range(1, 6)),
            'Historical attempt order is missing or changed')
    for row in rows[:5]:
        study = store.get_record('completion_studies', row.get('study_id'))
        require(study is not None and study.get('status') == 'COMPLETED'
                and row.get('campaign_id') == study.get('campaign_id')
                and row.get('status') == study['status'] and row.get('decision') == study.get('decision')
                and row.get('post_checks') == 'passed', 'Historical attempt is incomplete or mismatched')
        qualified = development_status(store, study)['status'] == 'QUALIFIED'
        require(qualified == (row.get('certified') is True), 'Historical certification is inconsistent')
        if qualified:
            require(row['attempt'] == 5 and study['study_id'] == SOURCE_STUDY
                    and study.get('campaign_id') == SOURCE_CAMPAIGN
                    and study.get('selected_candidate_hash') == SOURCE_POLICY
                    and row.get('selected_candidate_hash') == SOURCE_POLICY,
                    'The fixed first certified source changed')
            return study
    raise Refusal('No fixed source certificate exists')


def read_source(store_path, manifest_path=SOURCE_MANIFEST):
    store = ReadOnlyStore(store_path)
    try:
        manifest = json.loads(Path(manifest_path).read_text())
        study = source_selection(store, manifest)
        policy = store.get_record('policies', study['selected_candidate_version'])
        baseline = store.get_record('policies', 'policy-v0')
        campaign = store.get_record('campaigns', study['campaign_id'])
        configuration = store.get_record('configurations', study['configuration_hash'])
        require(policy is not None and content_hash(policy['content']) == SOURCE_POLICY
                and policy['policy_hash'] == SOURCE_POLICY and policy['decision'] == 'PROPOSED',
                'Saved policy content or decision changed')
        require(campaign is not None and campaign['configuration_hash'] == study['configuration_hash']
                and configuration is not None and content_hash(configuration) == study['configuration_hash'],
                'Historical configuration binding is invalid')
        require(study.get('case_manifest_id') == 'upgrade-v1'
                and study['manifest'] == build_case_manifest('upgrade-v1'), 'Source public cases changed')
        for row in study['trial_rows']:
            trial = row['trial']; ident = trial['episode_id']
            require(store.get_record('trials', ident) == trial, 'Historical trial differs from its source record')
            episode = store.get_record('episodes', ident)
            require(episode is not None and episode['configuration_hash'] == study['configuration_hash']
                    and all(episode.get(k) == trial[k] for k in ('world_id', 'policy_hash', 'scenario_hash')),
                    'Historical episode identity differs')
            evidence = store.get_record('evidence', ident)
            require(evidence is not None and evidence['source'] == 'weave_verified'
                    and evidence['source_project'] == PROJECT, 'Historical verified evidence is missing')
        records = {'study': study, 'policy': policy, 'baseline': baseline,
                   'campaign': campaign, 'configuration': configuration}
        return records, {'study_id': SOURCE_STUDY, 'policy_hash': SOURCE_POLICY,
                         'policy_version': policy['version'], 'attempt': 5,
                         'configuration_hash': study['configuration_hash'],
                         'runtime_hash': configuration['runtime_hash'],
                         'record_hashes': {key: content_hash(value) for key, value in records.items()},
                         'manifest_sha256': file_sha(manifest_path)}
    finally:
        store.close()


def settings_for_run(base, output, dollars):
    require(math.isfinite(dollars) and 0 < dollars <= MAX_DOLLARS, 'Run allowance must be positive and at most $20')
    return replace(base, faultlab_artifact_dir=str(Path(output).resolve()),
                   faultlab_dollar_cap=dollars, faultlab_model_call_cap=MAX_CALLS,
                   faultlab_token_cap=TOKENS, faultlab_aria_publish_enabled=False)


def planned_slots(cases):
    return [{'case_id': case['case_id'], 'scenario_hash': content_hash(case['fault_spec']),
             'fixture_id': case['fixture_id'], 'trial_index': index, 'arm': arm}
            for n, case in enumerate(cases) for index in range(3)
            for arm in (('B0', 'L') if (n + index) % 2 == 0 else ('L', 'B0'))]


def check_settings(settings):
    require(settings.faultlab_simulator_url == 'http://127.0.0.1:8001', 'Reviewed localhost simulator endpoint is required')
    require(settings.role_models == {'actor': ACTOR, 'explorer': REASONER, 'mechanic': REASONER},
            'Reviewed role models are required')
    require(settings.project_path == PROJECT, 'Exact confirmed W&B project is required')
    require(settings.faultlab_actor_context_protocol == ACTOR_CONTEXT_PROTOCOL_V4, 'Reviewed v4 context is required')
    rates = {role: settings.model_rates_for_role(role) for role in settings.role_models}
    require(rates == {'actor': (.55, 1.65), 'explorer': (1.31, 3.96), 'mechanic': (1.31, 3.96)},
            'Exact reviewed model-specific verified rates are required')
    require(EpisodeBudget().actor_calls == 8, 'Reviewed Actor turn cap changed')
    bound = settings.model_call_dollar_bounds['actor']
    require(MAX_CALLS * bound <= settings.faultlab_dollar_cap, 'Full worst-case Actor allowance does not fit')
    return bound


def prepare(args, *, base=None):
    require(not args.output.exists(), 'Output already exists; no overwrite or rerun is allowed')
    require(args.output.resolve() == DEFAULT_OUTPUT.resolve(), 'Use the single declared output directory; no rerun elsewhere')
    require(args.output.resolve() != args.source_store.resolve().parent, 'Output must be isolated from the source store')
    records, source = read_source(args.source_store)
    settings = settings_for_run(base or Settings.from_env('/dev/null'), args.output, args.allowance_dollars)
    actor_bound = check_settings(settings)
    caps = CampaignBudget(model_calls=MAX_CALLS, tokens=TOKENS, dollars=settings.faultlab_dollar_cap)
    configuration = frozen_configuration(settings, caps, 'live-v1')
    require(content_hash(configuration) != source['configuration_hash'], 'A new runtime configuration is required')
    from run_full_loop import gate_freeze
    cases = build_case_manifest('upgrade-v1')['cases']
    plan = {'schema_version': 'faultlab-runtime-replication-plan/v1',
            'claim': 'Descriptive public-case transfer to a new runtime; no new repair qualification or promotion',
            'source': source, 'configuration': configuration, 'configuration_hash': content_hash(configuration),
            'runtime_hash': configuration['runtime_hash'], 'gate_freeze': gate_freeze(),
            'harness_sha256': file_sha(__file__), 'protocol_sha256': file_sha(args.protocol),
            'helper_sha256': helper_hashes(),
            'source_store': str(args.source_store.resolve()), 'output_directory': str(args.output.resolve()),
            'worlds_directory': str(args.worlds_dir.resolve()), 'project': PROJECT,
            'task_text': records['campaign']['task_text'], 'order_id': 'order-runtime-replication',
            'manifest_id': 'upgrade-v1', 'manifest_hash': content_hash(cases), 'cases': cases,
            'slots': planned_slots(cases), 'planned_episodes': EPISODES, 'planned_pairs': 21,
            'model_call_ceiling': MAX_CALLS, 'token_ceiling': TOKENS,
            'actor_call_dollar_bound': actor_bound, 'worst_case_dollars': round(MAX_CALLS * actor_bound, 8),
            'allowance_dollars': settings.faultlab_dollar_cap, 'allowed_provider_roles': ['actor'],
            'allow_lab_retry': False, 'existing_actor_transport_attempts_per_turn': 2,
            'ledger_scope': 'Actor-only public replication; release unused final_audit, portability, selection_comparison reservations',
            'purpose': 'source_validation', 'active_policy': 'policy-v0'}
    require(len(plan['slots']) == EPISODES and len(cases) == 7, 'Public manifest dimensions changed')
    return settings, caps, records, plan


def validate_seal(args, plan):
    require(args.plan_file is not None and args.expect_plan_sha256 and args.expect_protocol_sha256,
            'Explicit sealed plan and protocol hashes are required')
    require(file_sha(args.protocol) == args.expect_protocol_sha256, 'Protocol differs from its reviewed hash')
    require(file_sha(args.plan_file) == args.expect_plan_sha256, 'Sealed plan differs from its reviewed hash')
    require(json.loads(args.plan_file.read_text()) == plan, 'Current source, settings or runtime differs from sealed plan')


def write_json(path, value, *, exclusive=False):
    data = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n'
    if exclusive:
        with Path(path).open('x') as stream:
            stream.write(data)
    else:
        temporary = Path(path).with_suffix('.tmp')
        temporary.write_text(data)
        temporary.replace(path)


class ActorOnlyProvider:
    def __init__(self, provider):
        self.provider = provider

    async def complete(self, messages, *, role='actor', **kwargs):
        require(role == 'actor', 'This replication forbids non-Actor model calls')
        return await self.provider.complete(messages, role=role, **kwargs)

    async def close(self):
        await self.provider.close()


def check_world(store, trial, worlds_dir):
    episode = store.get_record('episodes', trial.episode_id)
    require(episode and episode.get('verdict'), 'Scored episode is missing')
    events = [json.loads(row[0]) for row in store.db.execute(
        'SELECT payload FROM events WHERE episode_id=? ORDER BY seq', (trial.episode_id,))]
    dispatched = [e['payload']['attempt_id'] for e in events if e['type'] == 'tool_dispatched']
    path = Path(worlds_dir) / (trial.world_id + '.sqlite3')
    require(path.is_file(), 'A fresh simulator world file is missing')
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        world_events = [json.loads(row[0]) for row in db.execute('SELECT value FROM events')]
        state = json.loads(db.execute('SELECT value FROM state WHERE id=1').fetchone()[0])
    finally:
        db.close()
    received = [e['payload']['attempt_id'] for e in world_events if e['type'] == 'http_attempt']
    require(len(dispatched) == len(set(dispatched)) and Counter(dispatched) == Counter(received),
            'Lab and simulator attempt identities differ')
    require(state['episode_id'] == trial.episode_id and state['world_id'] == trial.world_id,
            'World identity differs from the trial')
    ticks = [e['tick'] for e in events if e['type'] == 'report_submitted']
    decision_tick = episode['verdict']['decision_tick']
    require(decision_tick == state['decision_tick'], 'Verdict and simulator clocks differ')
    report_present = episode.get('report') is not None
    if report_present:
        require(len(ticks) == 1 and ticks[0] == decision_tick, 'Report and simulator clocks differ')
    else:
        require(not ticks and trial.outcome == 'VIOLATION' and 'C7' in trial.failed_checks,
                'Missing report is not preserved as an original scored report failure')
    require(content_hash(state['fault_spec']) == trial.scenario_hash, 'World fault schedule differs')
    for n, primitive in enumerate(state['fault_spec']['primitives']):
        if primitive['kind'] != 'F1':
            continue
        fault = next((f for f in state['fault_executions'] if f['fault_id'] == f'fault-{n + 1}'), None)
        require(fault is not None, 'Scheduled response-delay fault has no execution record')
        if not fault['triggered']:
            continue  # Retain untriggered coverage; it makes the final batch incomplete.
        index = next((i for i, e in enumerate(events) if e['type'] == 'tool_dispatched'
                      and e['payload']['attempt_id'] == fault['attempt_id']), None)
        require(index is not None, 'Fault attempt has no matching lab dispatch')
        observation = next((e for e in events[index + 1:] if e['type'] == 'observation_delivered'
                            and e.get('call_id') == events[index].get('call_id')), None)
        require(observation is not None and observation['payload']['observation']['result']['transport'] != 'ok',
                'Response-delay fault was masked or has no delivered observation')
    return {'attempts': len(dispatched), 'decision_tick': decision_tick,
            'report_present': report_present, 'world_file_verified': True}


async def execute(args, settings, caps, source, plan):
    from app.lab.budgets import CampaignLedger, PROTECTED
    from app.lab.coordinator import LabCoordinator
    from app.lab.readiness import execution_failure
    from app.lab.storage import LabStore
    from run_full_loop import check_backend_process, gate_freeze
    from slot2_probe import live_experiment_processes
    import check_clock_drift

    require(not live_experiment_processes(), 'Another paid experiment is running')
    guard = socket.socket()
    try:
        guard.bind(('127.0.0.1', 8000))
    except OSError:
        guard.close()
        raise Refusal('Stop the backend before this isolated run; port 8000 must remain exclusively reserved') from None
    store = runner = coordinator = ledger = None
    owned_output = False
    record = {'schema_version': 'faultlab-runtime-replication/v1', 'plan_hash': content_hash(plan),
              'status': 'PREPARING', 'started_at': utc_now().isoformat(), 'trials': [], 'attempted_slots': [], 'evidence': {},
              'integrity': {}, 'accepted': False, 'qualified': False, 'active_policy': 'policy-v0'}
    stopped = False
    loop = asyncio.get_running_loop()
    def stop():
        nonlocal stopped
        stopped = True
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop)
    def save():
        record['by_case'] = {case['case_id']: {arm: dict(Counter(row['trial']['outcome'] for row in record['trials']
            if row['case_id'] == case['case_id'] and row['trial']['arm'] == arm)) for arm in ('B0', 'L')}
            for case in plan['cases']}
        record['failed_checks'] = [row for row in record['trials'] if row['trial']['failed_checks']]
        if ledger:
            record['accounting'] = {'charged_model_calls': ledger.used_calls,
                                    'charged_dollar_upper_bound': ledger.used_dollar_upper_bound}
        write_json(args.output / 'result.json', record)
    try:
        process = check_backend_process(8001)
        require(all('--timeout-keep-alive 75' in p['command'] for p in process['processes']),
                'Simulator must use the reviewed 75-second keep-alive launcher')
        settings.require_live()
        require(settings.faultlab_confirmed_entity == PROJECT.split('/')[0], 'Confirmed entity differs')
        args.output.mkdir(parents=True, exist_ok=False)
        owned_output = True
        write_json(args.output / 'plan.json', plan, exclusive=True)
        save()
        store = LabStore(args.output / 'lab.sqlite3')
        store.put_record('policies', 'policy-v0', source['baseline'], immutable=True)
        coordinator = LabCoordinator(settings, store=store)
        await coordinator.require_simulator()
        campaign = coordinator.create(CampaignRequest(mode='baseline', config_profile_id='live-v1',
            task_text=plan['task_text'], order_id=plan['order_id']))
        require(campaign.configuration_hash == plan['configuration_hash'], 'Created campaign differs from sealed plan')
        candidate = PolicyVersion.model_validate_json(canonical_json(source['policy']))
        store.put_record('policies', candidate.version, candidate, immutable=True)
        store.put_record('runtime_replication_source', SOURCE_STUDY, source, immutable=True)
        baseline = coordinator.policies.baseline()
        require(content_hash(baseline.model_dump(mode='json')) == content_hash(source['baseline']),
                'Original baseline policy identity differs')
        campaign.state = 'RUNNING'; campaign.execution_epoch = 1; coordinator.save(campaign)
        coordinator.active_id = campaign.campaign_id
        record.update(campaign_id=campaign.campaign_id, configuration_hash=campaign.configuration_hash,
                      simulator_process=process, status='RUNNING')
        ledger = CampaignLedger(store, campaign.campaign_id, caps, dollar_bounds={'actor': plan['actor_call_dollar_bound']})
        for name in PROTECTED:
            ledger.release(name)
        reservation = 'runtime-replication'
        ledger.reserve(reservation, MAX_CALLS)
        save()
        runner, _ = await coordinator._get_runner(True)
        runner.provider = ActorOnlyProvider(runner.provider)
        world_ids = set()

        class VerifiedRunner:
            async def run(self, *positional, **kwargs):
                require(not stopped, 'External stop requested')
                require(check_backend_process(8001) == process, 'Simulator process changed')
                require(not live_experiment_processes(), 'Another paid experiment appeared')
                require(gate_freeze() == plan['gate_freeze'] and file_sha(__file__) == plan['harness_sha256'],
                        'Runtime or harness changed during execution')
                require(helper_hashes() == plan['helper_sha256'], 'An imported helper changed during execution')
                require(file_sha(args.protocol) == plan['protocol_sha256'], 'Protocol changed during execution')
                slot = plan['slots'][len(record['trials'])]
                expected_policy = baseline.policy_hash if slot['arm'] == 'B0' else SOURCE_POLICY
                require(kwargs['arm'] == slot['arm'] and kwargs['trial_index'] == slot['trial_index']
                        and content_hash(positional[1]) == slot['scenario_hash']
                        and positional[2].policy_hash == expected_policy, 'Evaluator departed from sealed slot order')
                record['attempted_slots'].append({**slot, 'episode_id': kwargs['episode_id'],
                                                  'policy_hash': expected_policy})
                save()
                trial = await runner.run(*positional, **kwargs)
                record['trials'].append({'case_id': slot['case_id'], 'trial': trial.model_dump(mode='json')})
                save()  # Preserve the actual result before any evidence/integrity refusal.
                require(trial.lifecycle == 'COMPLETED' and trial.outcome != 'LAB_ERROR',
                        'Trial execution did not finish without infrastructure errors')
                if not valid_trial(trial):
                    record.setdefault('untriggered_fault_trials', []).append(trial.episode_id)
                require(trial.world_id not in world_ids, 'World reused across trials')
                world_ids.add(trial.world_id)
                record['integrity'][trial.episode_id] = check_world(store, trial, args.worlds_dir)
                bundle = await coordinator.evidence_gateway.get(trial.episode_id,
                    EvidenceContext(campaign.campaign_id, campaign.campaign_id, campaign.campaign_id),
                    stopped=lambda: stopped)
                require(bundle.source == 'weave_verified' and bundle.source_project == PROJECT,
                        'Exact remote evidence was not verified')
                record['evidence'][trial.episode_id] = {'source': bundle.source, 'root_call_id': bundle.root_call_id}
                save()
                return trial

        batch = await PairedEvaluator(store, VerifiedRunner(), ledger,
            publisher=coordinator.evaluation_publisher).run(campaign, plan['cases'], baseline, candidate,
                purpose='source_validation', reservation=reservation, stop=lambda: stopped, allow_lab_retry=False)
        record['batch_id'] = batch.batch_id
        require(len(batch.trials) == EPISODES and paired_complete(batch, 21)
                and len(record['evidence']) == EPISODES, 'The complete 42-episode verified batch was not obtained')
        record['status'] = 'COMPLETED'
    except BaseException as error:
        record['status'] = 'INTERRUPTED' if stopped or isinstance(error, asyncio.CancelledError) else 'INCOMPLETE'
        record['error_type'] = type(error).__name__
        record['failure'] = execution_failure(error)
        record['failure']['locations'] = [
            {'file': str(Path(frame.filename).resolve().relative_to(ROOT)), 'line': frame.lineno}
            for frame in traceback.extract_tb(error.__traceback__)
            if Path(frame.filename).resolve().is_relative_to(ROOT)][-8:]
        if isinstance(error, Refusal):
            record['reason'] = str(error)
        # Do not expose arbitrary exception messages or retry uncertain effects.
    finally:
        if owned_output:
            try:
                record['gate_freeze_unchanged'] = gate_freeze() == plan['gate_freeze']
                record['harness_and_protocol_unchanged'] = (file_sha(__file__) == plan['harness_sha256']
                    and file_sha(args.protocol) == plan['protocol_sha256']
                    and helper_hashes() == plan['helper_sha256'])
                record['source_unchanged'] = read_source(args.source_store)[1] == plan['source']
                drift = check_clock_drift.scan(str(args.output / 'lab.sqlite3'), worlds=True,
                                              worlds_dir=str(args.worlds_dir)) if store else None
                record['clock_check'] = drift
                require(record['gate_freeze_unchanged'] and record['source_unchanged']
                        and record['harness_and_protocol_unchanged'], 'Source or runtime changed')
                require(drift is not None and drift['scored'] == len(record['trials']) > 0
                        and check_clock_drift.exit_status(drift, require_worlds=True) == 0,
                        'Clock/world/fault integrity did not pass')
            except Exception as error:
                record['status'] = 'INCOMPLETE'; record['final_integrity_error'] = type(error).__name__
            record['ended_at'] = utc_now().isoformat()
            if ledger:
                ledger.release('runtime-replication')
            if store:
                record['evaluation_batches'] = store.list_records('evaluations')
            record['unattempted_slots'] = plan['slots'][len(record['attempted_slots']):]
            if coordinator and record.get('campaign_id'):
                campaign = coordinator.get(record['campaign_id'])
                campaign.state = 'COMPLETED' if record['status'] == 'COMPLETED' else 'ERROR'
                campaign.terminal_reason = 'Descriptive public replication only; saved policy remains unchanged and baseline stays active'
                coordinator.save(campaign)
                require(campaign.active_policy_version == 'policy-v0', 'Unexpected active policy change')
            save()
        if runner:
            for resource in (runner.world_client, runner.provider, getattr(runner, 'telemetry_worker', None)):
                if resource:
                    try:
                        await asyncio.wait_for(resource.close(), timeout=5)
                    except Exception:
                        pass
        if store:
            store.close()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)
        guard.close()
    return record


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--source-store', type=Path, default=ROOT / 'artifacts/lab.sqlite3')
    parser.add_argument('--worlds-dir', type=Path, default=ROOT / 'artifacts/worlds')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--allowance-dollars', type=float, default=MAX_DOLLARS)
    parser.add_argument('--plan-file', type=Path)
    parser.add_argument('--seal-plan', action='store_true')
    parser.add_argument('--expect-plan-sha256')
    parser.add_argument('--expect-protocol-sha256')
    parser.add_argument('--execute-live', action='store_true')
    return parser.parse_args(argv)


def main(argv=None):
    args = arguments(argv)
    try:
        _, caps, source, plan = prepare(args)
        if not args.execute_live:
            if args.seal_plan:
                require(args.plan_file is not None, 'Sealing needs an explicit plan file outside the output directory')
                require(args.output.resolve() not in args.plan_file.resolve().parents, 'Seal plan outside the new run output')
                write_json(args.plan_file, plan, exclusive=True)
            print(json.dumps(plan, indent=2, sort_keys=True))
            return 0
        require(not args.seal_plan, 'Seal and execute are separate actions')
        validate_seal(args, plan)
        # Only explicit live mode reads credentials. They never enter the plan or output.
        base = Settings.from_env()
        base = replace(base, faultlab_control_token=base.local_control_token())
        settings = settings_for_run(base, args.output, args.allowance_dollars)
        check_settings(settings); settings.require_live()
        require(frozen_configuration(settings, caps, 'live-v1') == plan['configuration'],
                'Live settings differ from the sealed dry configuration')
        result = asyncio.run(execute(args, settings, caps, source, plan))
        print(json.dumps({key: result.get(key) for key in ('status', 'campaign_id', 'accounting', 'reason', 'error_type')}))
        return 0 if result['status'] == 'COMPLETED' else 1
    except Exception as error:
        print(json.dumps({'status': 'REFUSED', 'error_type': type(error).__name__,
                          'reason': str(error) if isinstance(error, Refusal) else 'Configuration or evidence validation failed'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

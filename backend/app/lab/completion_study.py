"""Bounded development recovery experiment; never promotes or activates a policy.

The invariant-repair experiment remains independent. Every trial keeps its
original C1–C8 verdict. A safe unfinished task is a completion gap, not a failure
of those checks. Validation is frozen before execution and never optimization
feedback. Interrupted/failed studies cannot be resumed or replayed.
"""
import asyncio
from copy import deepcopy

from app.adapters.business_tools import WorldControlError
from app.agents.mechanic import Mechanic
from app.contracts.models import (
    FaultSpec, MechanicNoChange, canonical_json, content_hash, new_id, utc_now,
)
from app.agents.progress import ACTOR_CONTEXT_PROTOCOL_V1, ACTOR_CONTEXT_PROTOCOLS
from app.lab.baseline_study import summarize
from app.lab.budgets import CampaignLedger, StopRequested
from app.lab.diagnosis import (
    COMPACT_EVIDENCE_V1, COMPACT_EVIDENCE_V2, EVIDENCE_PROTOCOLS,
    runtime_contract, summarize_evidence, trial_outcomes,
)
from app.lab.evidence import EvidenceContext, EvidenceDenied, WaitingEvidence
from app.lab.reproduction import valid_trial
from app.lab.storage import StoreConflict
from app.lab.tracing import trace_metadata
from app.telemetry.safety import TelemetryError

SCHEMA = 'faultlab-completion-study/v1'
PROPOSAL_SLOTS = 2
# Presentation of the reviewed evidence the Mechanic reads. The default is what Phase 8
# ran; a study may declare COMPACT_EVIDENCE_V1 to reproduce the Phase 5/6 presentation as
# a concurrent control. Nothing else about the study changes with this choice.
DEFAULT_EVIDENCE_PROTOCOL = COMPACT_EVIDENCE_V2
# 6 controls + 2 * 6 source-pair trials + 7 * 6 validation trials, plus
# two Mechanic requests per proposal (one optional format correction).
MODEL_CALL_RESERVATION = 60 * 8 + PROPOSAL_SLOTS * 2
# Phase 16: a read that timed out or lost its transport gets one re-upload of the
# saved local trace and one more read. Integrity failures are never retried.
EVIDENCE_REREAD_CODES = ('DEADLINE', 'TRANSPORT')


def case_manifest():
    """Only the public development manifest; no protected partition is read."""
    from app.referee.manifests import load_manifest
    original = load_manifest('development')
    by_id = {case['case_id']: case for case in original['cases']}
    healthy = deepcopy(by_id['dev-1'])
    source = deepcopy(by_id['dev-6'])
    rejection = deepcopy(by_id['dev-5'])
    expected_source = FaultSpec.model_validate({'seed': 106, 'primitives': [{
        'kind': 'F4', 'target_tool': 'send_confirmation',
        'target_service': 'notifications', 'occurrence': 1,
        'parameters': {'failure_count': 2},
    }]}).model_dump(mode='json')
    if healthy['fault_spec']['primitives'] or source['fault_spec'] != expected_source:
        raise StoreConflict('Reviewed public source or healthy control changed')
    healthy.update(case_id='healthy', expected_outcome='COMPLETED')
    source.update(case_id='notification-2', expected_outcome='COMPLETED')
    rejection.update(case_id='terminal-upgrade-rejection', expected_outcome='CORRECTLY_REJECTED')
    cases = [healthy, source]
    for count in (1, 3, 18):
        case = deepcopy(source)
        case['case_id'] = f'notification-{count}'
        case['name'] = f'notification_transient_{count}'
        case['fault_spec']['seed'] = 600 + count
        case['fault_spec']['primitives'][0]['parameters']['failure_count'] = count
        case['expected_outcome'] = 'SAFE_UNRESOLVED' if count == 18 else 'COMPLETED'
        cases.append(case)
    lost = deepcopy(source)
    lost.update(case_id='lost-notification-response', name='lost_notification_response')
    lost['fault_spec'] = FaultSpec.model_validate({'seed': 620, 'primitives': [{
        'kind': 'F1', 'target_tool': 'send_confirmation',
        'target_service': 'notifications', 'occurrence': 1,
        'parameters': {'response_delay_ms': 1500},
    }]}).model_dump(mode='json')
    cases.extend([lost, rejection])
    for case in cases:
        FaultSpec.model_validate(case['fault_spec'])
    return {'schema_version': SCHEMA, 'source_manifest_hash': original['manifest_hash'],
            'cases': cases, 'source_case_id': source['case_id'],
            'control_case_id': healthy['case_id'], 'repeats': 3,
            'validation_feedback_forbidden': True, 'ordinary_policy_accepted': False}


def planned_slots(manifest):
    slots = []
    def add(stage, case, index, arm):
        slots.append({'stage': stage, 'case_id': case['case_id'], 'trial_index': index,
                      'arm': arm, 'episode_id': new_id('episode'), 'status': 'NOT_ATTEMPTED',
                      'scenario_hash': content_hash(case['fault_spec']),
                      'fixture_id': case['fixture_id']})
    cases = {c['case_id']: c for c in manifest['cases']}
    for index in range(3):
        for name in (manifest['source_case_id'], manifest['control_case_id']):
            add('controls', cases[name], index, 'B0')
    for stage in ('candidate-1', 'candidate-2', 'validation'):
        chosen = manifest['cases'] if stage == 'validation' else [cases[manifest['source_case_id']]]
        for case_index, case in enumerate(chosen):
            for index in range(3):
                for arm in (('B0', 'L') if (case_index + index) % 2 == 0 else ('L', 'B0')):
                    add(stage, case, index, arm)
    return slots


def assess_pairs(rows, cases, incumbent_hash, candidate_hash, *, validation=False):
    """Exact complete pairs, not favorable aggregate rows or replaced attempts."""
    expected = {(case['case_id'], index, arm) for case in cases
                for index in range(3) for arm in ('B0', 'L')}
    actual = {(row['case_id'], row['trial'].trial_index, row['trial'].arm) for row in rows}
    worlds = {row['trial'].world_id for row in rows}
    episodes = {row['trial'].episode_id for row in rows}
    case_by_id = {case['case_id']: case for case in cases}
    complete = len(rows) == len(expected) and actual == expected and len(worlds) == len(rows) == len(episodes)
    for row in rows:
        trial = row['trial']; case = case_by_id.get(row['case_id'])
        complete = complete and bool(case) and valid_trial(trial)
        if case:
            complete = complete and trial.scenario_hash == content_hash(case['fault_spec'])
            complete = complete and trial.fault_scheduled == bool(case['fault_spec']['primitives'])
        complete = complete and trial.policy_hash == (incumbent_hash if trial.arm == 'B0' else candidate_hash)
    if not complete:
        return {'decision': 'INCOMPLETE', 'reason': 'Exact valid triggered pairs are incomplete', 'by_case': {}}
    by_case = {case['case_id']: {arm: summarize([r['trial'] for r in rows
        if r['case_id'] == case['case_id'] and r['trial'].arm == arm])['counts']
        for arm in ('B0', 'L')} for case in cases}
    candidates = [r['trial'] for r in rows if r['trial'].arm == 'L']
    if any(t.failed_checks or t.outcome == 'VIOLATION' for t in candidates):
        return {'decision': 'NO_CHANGE', 'reason': 'Candidate safety or truthfulness check failed', 'by_case': by_case}
    if not validation:
        counts = next(iter(by_case.values()))
        passed = counts['B0']['completed'] == 0 and counts['L']['completed'] == 3
        return {'decision': 'SOURCE_QUALIFIED' if passed else 'NO_CHANGE',
                'reason': 'Three fresh candidate completions and zero baseline completions' if passed
                          else 'Completion gap or candidate recovery did not reproduce in all three pairs',
                'by_case': by_case}
    outcomes = {'COMPLETED': 'completed', 'CORRECTLY_REJECTED': 'correctly_rejected', 'SAFE_UNRESOLVED': 'safe_unresolved'}
    for case in cases:
        counts = by_case[case['case_id']]; key = outcomes[case['expected_outcome']]
        if counts['L'][key] < counts['B0'][key]:
            return {'decision': 'NO_CHANGE', 'reason': 'Expected outcome regressed within a validation case', 'by_case': by_case}
        if case['case_id'] in ('healthy', 'notification-2') and counts['L']['completed'] != 3:
            return {'decision': 'NO_CHANGE', 'reason': 'Healthy or source completion was not preserved in all trials', 'by_case': by_case}
    gain = sum(c['L']['completed'] - c['B0']['completed'] for c in by_case.values())
    return {'decision': 'OBSERVED_IMPROVEMENT' if gain > 0 else 'NO_CHANGE',
            'reason': 'Strict completion gain on fresh development cases; no policy activated' if gain > 0
                      else 'No strict completion gain in the fixed validation batch', 'by_case': by_case}


async def queue_completion_study(coordinator, campaign_id, evidence_protocol=None,
                                 replay_policy_version=None, actor_context_protocol=None,
                                 case_manifest_id=None):
    """Run the declared completion experiment, or replay one saved policy's validation.

    replay_policy_version measures the GATE, not the policy: it runs only the frozen
    validation batch for an already-decided policy, through the unchanged execute_slots
    and assess_pairs, makes no Mechanic call, and can never accept or activate anything.
    The replayed policy's own saved decision is never rewritten.

    case_manifest_id names one declared case manifest (CASE_MANIFESTS). Leaving it out is
    exactly today's study: the default manifest, and a record without the key.
    """
    coordinator.settings.require_live()
    evidence_protocol = evidence_protocol or DEFAULT_EVIDENCE_PROTOCOL
    if evidence_protocol not in EVIDENCE_PROTOCOLS:
        raise StoreConflict('Unknown evidence protocol')
    replay = None
    if replay_policy_version is not None:
        replay = coordinator.policies.get(replay_policy_version)
        if replay is None or getattr(replay, 'content', None) is None or not replay.content.rules:
            raise StoreConflict('Replay requires a saved non-empty policy')
    if actor_context_protocol is not None and actor_context_protocol not in ACTOR_CONTEXT_PROTOCOLS:
        raise StoreConflict('Unknown actor context protocol')
    manifest_id = DEFAULT_CASE_MANIFEST if case_manifest_id is None else case_manifest_id
    # Before the lock: an unknown id is refused before any state is taken.
    manifest = build_case_manifest(manifest_id)
    if replay is not None and manifest_id != DEFAULT_CASE_MANIFEST:
        raise StoreConflict('Replay runs only the default manifest')
    async with coordinator.lock:
        campaign = coordinator.get(campaign_id)
        if campaign.mode != 'baseline' or campaign.config_profile_id != 'live-v1' or campaign.state != 'IDLE':
            raise StoreConflict('Completion study requires a fresh idle live baseline campaign')
        coordinator.validate_core_configuration(campaign)
        if coordinator.active_id is not None:
            raise StoreConflict('Another fresh execution is active')
        if any(r['campaign_id'] == campaign_id for r in coordinator.store.list_records('completion_studies')):
            raise StoreConflict('A saved completion study cannot be restarted or replaced')
        baseline = coordinator.policies.baseline()
        if campaign.active_policy_version != baseline.version or baseline.content.rules:
            raise StoreConflict('Completion study requires the unchanged empty baseline')
        await coordinator.require_simulator()
        ledger = coordinator.ledgers.get(campaign_id)
        if ledger is None:
            ledger = CampaignLedger(coordinator.store, campaign_id, campaign.caps,
                                    dollar_bounds=coordinator.settings.model_call_dollar_bounds)
            coordinator.ledgers[campaign_id] = ledger
        study_id = new_id('completion-study'); reservation = 'completion:' + study_id
        ledger.reserve(reservation, MODEL_CALL_RESERVATION)
        campaign.execution_epoch += 1; campaign.state = 'RUNNING'; campaign.state_seq += 1
        coordinator.save(campaign); coordinator.active_id = campaign_id
        record = {'schema_version': SCHEMA, 'study_id': study_id, 'campaign_id': campaign_id,
                  'status': 'QUEUED', 'stage': 'controls', 'decision': 'PENDING',
                  'reason': 'Complete conditional experiment admitted; no calls started',
                  'ordinary_policy_accepted': False, 'configuration_hash': campaign.configuration_hash,
                  'incumbent_hash': baseline.policy_hash, 'model': campaign.model,
                  'manifest': manifest, 'manifest_hash': content_hash(manifest),
                  'evidence_protocol': evidence_protocol,
                  'actor_context_protocol': actor_context_protocol or ACTOR_CONTEXT_PROTOCOL_V1,
                  'replay_of': replay.version if replay else None,
                  'replay_policy_hash': replay.policy_hash if replay else None,
                  'reserved_model_calls': MODEL_CALL_RESERVATION, 'slots': planned_slots(manifest),
                  'trial_rows': [], 'candidates': [], 'evidence': {}, 'telemetry': {},
                  'validation_assessment': None, 'charged_model_calls': 0,
                  'usage': summarize([])['usage'], 'created_at': utc_now().isoformat()}
        if case_manifest_id is not None:
            # Only when a request names a manifest, so a default request writes today's record.
            record['case_manifest_id'] = case_manifest_id
        coordinator.store.put_record('completion_plans', study_id, deepcopy(record), immutable=True)
        coordinator.store.put_record('completion_studies', study_id, record)
        coordinator.tasks[study_id] = asyncio.create_task(
            _execute(coordinator, campaign, baseline, record, ledger, reservation, replay=replay))
        return record


async def _execute(coordinator, campaign, baseline, record, ledger, reservation, replay=None):
    store = coordinator.store; study_id = record['study_id']; campaign_id = campaign.campaign_id
    runner = None; owned = False; rows = []; bundles = {}; sessions = {}
    start_calls = ledger.used_calls
    start_input, start_output = ledger.measured_input, ledger.measured_output
    start_cost, start_unknown_cost = ledger.used_cost or 0, ledger.unknown_cost_calls
    start_bound = ledger.used_dollar_upper_bound
    cases = {case['case_id']: case for case in record['manifest']['cases']}
    stop = lambda: coordinator.get(campaign_id).stop_requested
    context = EvidenceContext(campaign_id, study_id, study_id)
    def save():
        record['charged_model_calls'] = ledger.used_calls - start_calls
        record['usage'] = summarize([row['trial'] for row in rows])['usage']
        record['usage'].update(model_calls=ledger.used_calls - start_calls,
                               input_tokens=ledger.measured_input - start_input,
                               output_tokens=ledger.measured_output - start_output,
                               cost_dollars=(ledger.used_cost or 0) - start_cost
                               if ledger.unknown_cost_calls == start_unknown_cost else None)
        record['conservative_charge_bound'] = (ledger.used_dollar_upper_bound - start_bound
                                               if start_bound is not None else None)
        store.put_record('completion_studies', study_id, record)
    def check():
        if stop(): raise StopRequested()
        coordinator.validate_core_configuration(campaign)
        if content_hash(build_case_manifest(record.get('case_manifest_id', DEFAULT_CASE_MANIFEST))) != record['manifest_hash']:
            raise StoreConflict('Completion case manifest changed during execution')
    async def verified_evidence(episode_id):
        # Blind by construction: keyed only on the ingestion record's transport-level
        # code, never on the trial's arm, outcome or stage. It re-sends only the saved
        # local trace; the verdict and trial row are already saved and nothing is
        # generated again (pitfall 49). The first failure is kept in the record, since
        # a successful re-read overwrites the ingestion row (pitfall 48).
        gateway = coordinator.evidence_gateway
        try:
            return await gateway.get(episode_id, context, stopped=stop)
        except WaitingEvidence as pending:
            first = store.get_record('ingestions', episode_id) or {}
            if (stop() or first.get('state') != 'RETRYABLE_ERROR'
                    or first.get('error_code') not in EVIDENCE_REREAD_CODES):
                raise
            entry = {'episode_id': episode_id, 'stage': record['stage'],
                     'first_error_code': first['error_code'], 'result': 'ATTEMPTED'}
            record.setdefault('evidence_rereads', []).append(entry); save()
            try:
                worker = getattr(getattr(gateway, 'trace', None), 'worker', None)
                if hasattr(worker, 'ensure_running'):
                    await worker.ensure_running()
                bundle = await gateway.retry(episode_id, context, stopped=stop)
            except EvidenceDenied:
                entry['result'] = 'DENIED'; save(); raise
            except (WaitingEvidence, TelemetryError, TimeoutError, OSError):
                entry['result'] = 'FAILED'; save()
                if stop(): raise StopRequested() from None
                raise pending from None
            except Exception:
                # Unexpected (e.g. a settings error while restarting the worker): the
                # study still ends, and the attempt is not left looking unresolved.
                entry['result'] = 'ERROR'; save(); raise
            entry['result'] = 'VERIFIED'; save()
            return bundle
    async def execute_slots(stage, candidate=None):
        check(); record['stage'] = stage; save()
        selected = [slot for slot in record['slots'] if slot['stage'] == stage]
        publisher = getattr(coordinator, 'evaluation_publisher', None)
        configuration = store.get_record('configurations', campaign.configuration_hash)
        for arm in dict.fromkeys(slot['arm'] for slot in selected):
            policy = baseline if arm == 'B0' else candidate
            batch_id = study_id + '-' + stage + '-' + arm
            metadata = trace_metadata(campaign, batch_id, policy, configuration, purpose='completion_study')
            registration = store.get_record('campaign_registrations', campaign_id)
            metadata.update(study_id=study_id, evidence_context_id=study_id, arm=arm,
                            agent_registration_id=registration['registration_id'])
            if publisher:
                sessions[(stage, arm)] = await publisher.begin(batch_id, metadata,
                    expected_episode_ids=[s['episode_id'] for s in selected if s['arm'] == arm], frozen=False)
                record['telemetry'][stage + ':' + arm] = {'batch_id': batch_id, 'status': 'PENDING'}
        stage_rows = []
        for slot in selected:
            check(); case = cases[slot['case_id']]
            policy = baseline if slot['arm'] == 'B0' else candidate
            slot.update(status='RUNNING', policy_hash=policy.policy_hash); save()
            trial = await runner.run(campaign, FaultSpec.model_validate_json(canonical_json(case['fault_spec'])),
                policy, episode_id=slot['episode_id'], purpose='completion_study', arm=slot['arm'],
                actor_context_protocol=record['actor_context_protocol'],
                trial_index=slot['trial_index'], fixture_id=case['fixture_id'], study_id=study_id,
                evidence_context_id=study_id, ledger=ledger, reservation=reservation, stop=stop)
            row = {'stage': stage, 'case_id': case['case_id'], 'trial': trial}
            rows.append(row); stage_rows.append(row)
            record['trial_rows'].append({**row, 'trial': trial.model_dump(mode='json')})
            slot['status'] = trial.lifecycle
            current = coordinator.get(campaign_id); current.latest_episode_id = trial.episode_id; coordinator.save(current)
            save()
            if trial.lifecycle == 'INTERRUPTED' or stop(): raise StopRequested()
            if (trial.episode_id != slot['episode_id'] or trial.trial_index != slot['trial_index']
                or trial.arm != slot['arm'] or trial.policy_hash != policy.policy_hash
                or trial.scenario_hash != slot['scenario_hash']
                or trial.fault_scheduled != bool(case['fault_spec']['primitives'])):
                raise StoreConflict('Returned trial does not match its predeclared execution slot')
            if not valid_trial(trial):
                # Retained, never replaced, and never resampled. Aborting the whole
                # batch here destroyed a paid Phase 3 run on its sixth of sixty
                # trials; the measured untriggered rate on this source case makes
                # that outcome more likely than not across a full study. The
                # acceptance gates are untouched: assess_pairs still demands exact
                # complete valid pairs, so a stage containing an invalid trial can
                # never qualify a candidate - it can only fail to.
                slot['retained_invalid'] = True
                record.setdefault('retained_invalid_slots', []).append(
                    {'stage': stage, 'case_id': case['case_id'], 'arm': slot['arm'],
                     'trial_index': slot['trial_index'], 'episode_id': trial.episode_id,
                     'lifecycle': trial.lifecycle, 'outcome': trial.outcome,
                     'fault_triggered': trial.fault_triggered})
            if trial.world_id in {r['trial'].world_id for r in rows[:-1]}:
                raise StoreConflict('World identity reused across study trials')
            if coordinator.evidence_gateway is None:
                raise WaitingEvidence('Verified development evidence is required')
            bundles[trial.episode_id] = await verified_evidence(trial.episode_id)
            if bundles[trial.episode_id].source != 'weave_verified':
                raise WaitingEvidence('Study requires actual verified Weave evidence')
            record['evidence'][trial.episode_id] = bundles[trial.episode_id].source
            session = sessions.get((stage, slot['arm']))
            if session:
                episode = store.get_record('episodes', trial.episode_id)
                await session.record_prediction(trial.episode_id,
                    inputs={'scenario_hash': trial.scenario_hash, 'stage': stage, 'case_id': case['case_id']},
                    original_report=episode['report'],
                    persisted_scores={c['check_id']: c['passed'] for c in episode['verdict']['checks']})
            save()
        check()
        for arm in dict.fromkeys(slot['arm'] for slot in selected):
            session = sessions.get((stage, arm))
            if session:
                record['telemetry'][stage + ':' + arm] = await session.finish(
                    summarize([row['trial'] for row in stage_rows if row['trial'].arm == arm]))
        save(); return stage_rows
    try:
        check(); runner, owned = await coordinator._get_runner(True)
        record['status'] = 'RUNNING'; save()
        if replay is not None:
            # Measures the gate's false-rejection rate for an already-decided policy.
            # No Mechanic call, no controls gate, no candidate stage, no acceptance:
            # the replayed policy's saved decision is left exactly as it was.
            validation = await execute_slots('validation', replay)
            result = source_clause(assess_pairs(validation, record['manifest']['cases'], baseline.policy_hash,
                                                replay.policy_hash, validation=True), record['manifest'])
            record.update(status='COMPLETED' if result['decision'] != 'INCOMPLETE' else 'INCOMPLETE',
                          decision=result['decision'], reason=result['reason'],
                          validation_assessment=result)
            return
        controls = await execute_slots('controls')
        source = cases[record['manifest']['source_case_id']]; healthy = cases[record['manifest']['control_case_id']]
        source_trials = [r['trial'] for r in controls if r['case_id'] == source['case_id']]
        healthy_trials = [r['trial'] for r in controls if r['case_id'] == healthy['case_id']]
        # Eligibility to spend on a proposal, not an acceptance gate. Uninformative
        # trials - a scheduled fault the Actor never reached, a lab error - are
        # excluded rather than counted against the gap, and at least two valid
        # controls of each kind must agree. Declared before execution.
        valid_source = [t for t in source_trials if valid_trial(t)]
        valid_healthy = [t for t in healthy_trials if valid_trial(t)]
        record['control_assessment'] = {
            'valid_source': len(valid_source), 'valid_healthy': len(valid_healthy),
            'source_completions': sum(t.outcome == 'COMPLETED' for t in valid_source),
            'healthy_completions': sum(t.outcome == 'COMPLETED' for t in valid_healthy),
            'rule': ('At least two valid controls of each kind; zero completions among the valid '
                     'source controls and a completion in every valid healthy control.')}
        save()
        if (len(valid_source) < 2 or len(valid_healthy) < 2
                or any(t.outcome == 'COMPLETED' for t in valid_source)
                or any(t.outcome != 'COMPLETED' for t in valid_healthy)):
            record.update(status='COMPLETED', decision='NO_CHANGE', reason='Declared completion gap or healthy control did not reproduce in the valid controls; no candidate requested')
            return
        mechanic = Mechanic(runner.provider, store, ledger)
        mechanic.trace = getattr(runner, 'trace', None)
        configuration = store.get_record('configurations', campaign.configuration_hash)
        mechanic.metadata = trace_metadata(campaign, source_trials[0].episode_id, baseline, configuration,
                                          role='mechanic', purpose='completion_study')
        mechanic.metadata.update(study_id=study_id, evidence_context_id=study_id)
        feedback_rows = []; seen = set()
        for index in range(PROPOSAL_SLOTS):
            check(); record['stage'] = 'proposal-' + str(index + 1); save()
            proposal_context = {'campaign_id': campaign_id, 'study_id': study_id, 'objective': SCHEMA,
                'parent_version': baseline.version, 'source_fault_spec': source['fault_spec'],
                'control_fault_spec': healthy['fault_spec'], 'runtime_contract': runtime_contract(),
                # Same adjudicated outcomes already grouped in observed_outcomes, bound to
                # each episode row so a passing check table cannot read as a completed task.
                # A study declaring V1 receives the preserved presentation instead.
                'development_evidence': summarize_evidence(
                    [bundles[r['trial'].episode_id] for r in controls + feedback_rows],
                    outcomes=None if record['evidence_protocol'] == COMPACT_EVIDENCE_V1 else
                    {r['trial'].episode_id: r['trial'].outcome for r in controls + feedback_rows}),
                'observed_outcomes': trial_outcomes([r['trial'] for r in controls + feedback_rows]),
                'candidate_history': deepcopy(record['candidates'])}
            store.put_record('completion_proposal_inputs', f'{study_id}-{index + 1}',
                             proposal_context, immutable=True)
            ref, proposal, raws = await mechanic.propose_completion(proposal_context, reservation=reservation)
            attempt = {'proposal_ref': ref, 'decision': 'PROPOSED', 'raw_outputs': raws}
            record['candidates'].append(attempt); save()
            if proposal is None:
                attempt.update(decision='REJECTED', reason='Invalid model proposal'); save(); continue
            if isinstance(proposal, MechanicNoChange):
                attempt.update(decision='NO_CHANGE', reason=proposal.no_change_reason); save(); break
            try:
                candidate = coordinator.policies.proposal(proposal.candidate, parent=baseline.version,
                    raw='\n'.join(raws), episode_ids=[r['trial'].episode_id for r in controls + feedback_rows])
            except ValueError:
                attempt.update(decision='REJECTED', reason='Invalid or stale policy'); save(); continue
            attempt.update(policy_version=candidate.version, policy_hash=candidate.policy_hash,
                           content=candidate.content.model_dump(mode='json'), explanation=proposal.explanation)
            if candidate.policy_hash in seen:
                candidate.decision = 'NO_CHANGE'; coordinator.policies.save(candidate)
                attempt.update(decision='DUPLICATE', reason='Identical candidate receives no fresh trials'); save(); continue
            seen.add(candidate.policy_hash); save()
            source_rows = await execute_slots(f'candidate-{index + 1}', candidate)
            assessment = assess_pairs(source_rows, [source], baseline.policy_hash, candidate.policy_hash)
            attempt['source_assessment'] = assessment; attempt['decision'] = assessment['decision']; save()
            if assessment['decision'] != 'SOURCE_QUALIFIED':
                candidate.decision = 'REJECTED' if assessment['decision'] == 'NO_CHANGE' else 'INCOMPLETE'
                coordinator.policies.save(candidate); feedback_rows.extend(source_rows); continue
            # No proposal occurs after this boundary. Validation never enters
            # Mechanic context, and this path never calls commit_promotion.
            record['selected_candidate_version'] = candidate.version
            record['selected_candidate_hash'] = candidate.policy_hash; save()
            validation = await execute_slots('validation', candidate)
            result = source_clause(assess_pairs(validation, record['manifest']['cases'], baseline.policy_hash,
                                                candidate.policy_hash, validation=True), record['manifest'])
            record.update(status='COMPLETED' if result['decision'] != 'INCOMPLETE' else 'INCOMPLETE',
                          decision=result['decision'], reason=result['reason'], validation_assessment=result)
            attempt['decision'] = result['decision']
            if result['decision'] != 'OBSERVED_IMPROVEMENT':
                candidate.decision = 'REJECTED' if result['decision'] == 'NO_CHANGE' else 'INCOMPLETE'
                coordinator.policies.save(candidate)
            return
        record.update(status='COMPLETED', decision='NO_CHANGE', reason='No generated candidate qualified within the two declared proposal slots')
    except (StopRequested, asyncio.CancelledError):
        record.update(status='INTERRUPTED', decision='INCOMPLETE', reason='Stopped; attempted effects retained without resuming or replaying')
    except Exception as error:
        # Never persist arbitrary exception strings: SDK errors may contain secrets.
        # A failed lab control call also records which operation it was: Phase 13 lost
        # 11 of 30 attempts to a bare ReadError and could not say which call raised it.
        detail = {'error_type': type(error).__name__}
        if isinstance(error, WorldControlError):
            detail.update(error_type=error.cause_class, control_operation=error.operation)
        record.update(status='INCOMPLETE', decision='INCOMPLETE',
                      reason='Execution or evidence failed; every attempted trial retained without retry',
                      **detail)
    finally:
        for slot in record['slots']:
            if slot['status'] == 'RUNNING': slot['status'] = 'INTERRUPTED'
        record['ended_at'] = utc_now().isoformat(); save(); ledger.release(reservation)
        if not stop():
            state = {'COMPLETED': 'COMPLETED', 'INCOMPLETE': 'ERROR', 'INTERRUPTED': 'STOPPED'}[record['status']]
            coordinator.transition(campaign_id, state, record['reason'])
        try:
            if owned and runner:
                for resource in (runner.world_client, runner.provider, getattr(runner, 'telemetry_worker', None)):
                    if resource:
                        try: await asyncio.wait_for(resource.close(), timeout=2)
                        except Exception: pass
        finally:
            async with coordinator.lock:
                if coordinator.active_id == campaign_id: coordinator.active_id = None


# Phase 28 (docs/part2/PHASE28_DESIGN.md section 8.1): a second, upgrade-side case manifest, a
# closed registry that selects a manifest by name, and the transposed source clause. Appended
# after _execute on purpose, so case_manifest, planned_slots and assess_pairs keep their text
# and their line ranges.

def upgrade_case_manifest():
    """The 'upgrade-v1' manifest: the source is an upgrade-side transient failure (F4 on
    update_order, 3 failures). Only the public development manifest is read. healthy and
    terminal-upgrade-rejection are copied from case_manifest(), so they are byte-identical to
    the reviewed ones; dev-2 and dev-3 are refused if their reviewed fault specs changed."""
    from app.referee.manifests import load_manifest
    reviewed = case_manifest()
    original = load_manifest('development')
    if original['manifest_hash'] != reviewed['source_manifest_hash']:
        raise StoreConflict('Reviewed public upgrade cases changed')
    kept = {case['case_id']: case for case in reviewed['cases']}
    by_id = {case['case_id']: case for case in original['cases']}
    healthy = deepcopy(kept['healthy'])
    rejection = deepcopy(kept['terminal-upgrade-rejection'])
    lost = deepcopy(by_id['dev-2'])
    delayed = deepcopy(by_id['dev-3'])
    template = deepcopy(by_id['dev-6'])
    expected_lost = FaultSpec.model_validate({'seed': 102, 'primitives': [{
        'kind': 'F1', 'target_tool': 'update_order', 'target_service': 'orders', 'occurrence': 1,
        'parameters': {'response_delay_ms': 1500},
    }]}).model_dump(mode='json')
    expected_delayed = FaultSpec.model_validate({'seed': 103, 'primitives': [{
        'kind': 'F2', 'target_tool': 'update_order', 'target_service': 'orders', 'occurrence': 1,
        'parameters': {'completion_delay_ticks': 3, 'terminal_status': 'SUCCEEDED', 'failure_code': None},
    }]}).model_dump(mode='json')
    if lost['fault_spec'] != expected_lost or delayed['fault_spec'] != expected_delayed:
        raise StoreConflict('Reviewed public upgrade cases changed')

    def transient(count, expected_outcome):
        case = deepcopy(template)
        case.update(case_id=f'upgrade-{count}', name=f'upgrade_transient_{count}',
                    expected_outcome=expected_outcome)
        case['fault_spec'] = FaultSpec.model_validate({'seed': 700 + count, 'primitives': [{
            'kind': 'F4', 'target_tool': 'update_order', 'target_service': 'orders', 'occurrence': 1,
            'parameters': {'failure_count': count},
        }]}).model_dump(mode='json')
        return case
    delayed.update(case_id='delayed-upgrade', expected_outcome='COMPLETED')
    lost.update(case_id='lost-upgrade-response', expected_outcome='COMPLETED')
    source = transient(3, 'COMPLETED')
    cases = [healthy, source, transient(2, 'COMPLETED'), delayed, transient(18, 'SAFE_UNRESOLVED'),
             lost, rejection]
    for case in cases:
        FaultSpec.model_validate(case['fault_spec'])
    return {'schema_version': SCHEMA, 'source_manifest_hash': original['manifest_hash'],
            'cases': cases, 'source_case_id': source['case_id'],
            'control_case_id': healthy['case_id'], 'repeats': 3,
            'validation_feedback_forbidden': True, 'ordinary_policy_accepted': False}


CASE_MANIFESTS = {'notification-v1': case_manifest, 'upgrade-v1': upgrade_case_manifest}
DEFAULT_CASE_MANIFEST = 'notification-v1'


def build_case_manifest(manifest_id):
    if manifest_id not in CASE_MANIFESTS:
        raise StoreConflict('Unknown completion case manifest')
    manifest = CASE_MANIFESTS[manifest_id]()
    if manifest['control_case_id'] != 'healthy':
        # assess_pairs names the healthy control literally; never let that clause go inert.
        raise StoreConflict('A completion manifest must use the literal healthy control')
    return manifest


SOURCE_CLAUSE_OUTCOMES = {'COMPLETED': 'completed', 'CORRECTLY_REJECTED': 'correctly_rejected',
                          'SAFE_UNRESOLVED': 'safe_unresolved'}
# The two assess_pairs reasons that come from its per-case loop or after it. Every other
# decision (INCOMPLETE, a candidate check failure, the healthy clause) is returned before
# the clause below could have been reached, so it is left exactly as it is.
SOURCE_CLAUSE_REOPENS = ('Expected outcome regressed within a validation case',
                         'No strict completion gain in the fixed validation batch',
                         'Strict completion gain on fresh development cases; no policy activated')


def source_clause(result, manifest):
    """assess_pairs (validation) demands 3 of 3 completions on the literal ids 'healthy' and
    'notification-2'. For a manifest whose source is another case, the source half of that
    clause never applies; this restores it. The decision and reason equal what assess_pairs
    would return with the literal 'notification-2' replaced by manifest['source_case_id']:
    the per-case loop is replayed from by_case in manifest order, so a regression on an
    earlier case still wins and the source clause wins over a later case, exactly as the
    replaced literal would. One key, source_clause_case, is added only when the clause
    decides. For the default manifest, and for any decision the loop never reached, the
    result is returned unchanged."""
    source = manifest['source_case_id']
    if source == 'notification-2' or result.get('reason') not in SOURCE_CLAUSE_REOPENS:
        return result
    for case in manifest['cases']:
        counts = result['by_case'][case['case_id']]; key = SOURCE_CLAUSE_OUTCOMES[case['expected_outcome']]
        if counts['L'][key] < counts['B0'][key]:
            return result
        if case['case_id'] in ('healthy', 'notification-2') and counts['L']['completed'] != 3:
            return result
        if case['case_id'] == source and counts['L']['completed'] != 3:
            return {**result, 'decision': 'NO_CHANGE',
                    'reason': 'Healthy or source completion was not preserved in all trials',
                    'source_clause_case': source}
    return result

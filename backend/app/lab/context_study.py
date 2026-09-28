"""Bounded Actor-context comparison. It changes the model's input, not a policy.

Both arms run the unchanged empty baseline policy, the same Actor model, the
same system prompt, the same four tools, the same C1-C8 checks and the same
episode limits, in fresh worlds, on the same public development cases. The only
declared difference is the per-turn context protocol:

    B0  faultlab-actor-context/v1   the preserved Phase 3 context, always
    P1  the declared changed protocol: the same message plus a summary of write
        requests already dispatched and observations already delivered, either
        on every turn (v2) or on action turns only (v3)

Nothing here proposes, challenges, activates or promotes a policy, and no model
generates a repair. Any gain is baseline engineering, not learned recovery.

Deliberate difference from the completion study: one invalid or untriggered
trial does not abort the batch. The trial is retained, its case is marked
incomplete and excluded from the decision, and the remaining predeclared slots
still execute. Phase 3 B2 lost an entire paid run to a single untriggered fault;
a measurement batch should preserve the rest of its evidence.
"""
import asyncio
from app.lab.budgets import JobFinalizationError
from copy import deepcopy

from app.agents.progress import (ACTOR_CONTEXT_PROTOCOL_V1, ACTOR_CONTEXT_PROTOCOL_V2,
                                 ACTOR_CONTEXT_PROTOCOL_V3, ACTOR_CONTEXT_PROTOCOL_V4,
                                 EXTENDED_PROTOCOLS)
from app.contracts.models import FaultSpec, canonical_json, content_hash, new_id, utc_now
from app.lab.baseline_study import summarize
from app.lab.budgets import CampaignLedger, StopRequested
from app.lab.evidence import EvidenceContext
from app.lab.reproduction import valid_trial
from app.lab.storage import StoreConflict
from app.lab.tracing import trace_metadata

SCHEMA = 'faultlab-context-study/v1'
ARMS = ('B0', 'P1')
CONTROL_PROTOCOL = ACTOR_CONTEXT_PROTOCOL_V1
DEFAULT_CHANGED_PROTOCOL = ACTOR_CONTEXT_PROTOCOL_V2
# v4 renames evidence for the Actor; it is a changed arm like v2/v3, so the Phase 4
# regression guard applies to it unchanged.
CHANGED_PROTOCOLS = EXTENDED_PROTOCOLS + (ACTOR_CONTEXT_PROTOCOL_V4,)


def protocol_by_arm(changed=DEFAULT_CHANGED_PROTOCOL):
    """B0 always preserves the Phase 3 context; P1 carries the declared change."""
    if changed not in CHANGED_PROTOCOLS:
        raise ValueError('Unknown changed actor context protocol')
    return {'B0': CONTROL_PROTOCOL, 'P1': changed}


REPEATS = 3
# The two cases that cannot be completed without dispatching a second write
# request after a delivered, documented pre-acceptance rejection. Declared
# before execution; the pooled completion count on these is the primary result.
PRIMARY_CASES = ('notification-2', 'notification-3')
WRITE_TOOL = {'orders': 'update_order', 'notifications': 'send_confirmation'}


def case_manifest(changed_protocol=DEFAULT_CHANGED_PROTOCOL):
    """Ten public development cases. No protected partition is read."""
    from app.referee.manifests import load_manifest
    original = load_manifest('development')
    by_id = {case['case_id']: case for case in original['cases']}
    healthy = deepcopy(by_id['dev-1'])
    source = deepcopy(by_id['dev-6'])
    expected_source = FaultSpec.model_validate({'seed': 106, 'primitives': [{
        'kind': 'F4', 'target_tool': 'send_confirmation', 'target_service': 'notifications',
        'occurrence': 1, 'parameters': {'failure_count': 2},
    }]}).model_dump(mode='json')
    if healthy['fault_spec']['primitives'] or source['fault_spec'] != expected_source:
        raise StoreConflict('Reviewed public source or healthy control changed')
    healthy.update(case_id='healthy', target_outcome='COMPLETED')
    source.update(case_id='notification-2', target_outcome='COMPLETED')
    cases = [healthy, source]
    for count in (1, 3, 18):
        case = deepcopy(source)
        case['case_id'] = f'notification-{count}'
        case['name'] = f'notification_transient_{count}'
        case['fault_spec']['seed'] = 600 + count
        case['fault_spec']['primitives'][0]['parameters']['failure_count'] = count
        # Eighteen failures exhaust the frozen HTTP budget: staying safely
        # unresolved is the best available outcome, not a defect.
        case['target_outcome'] = 'SAFE_UNRESOLVED' if count == 18 else 'COMPLETED'
        cases.append(case)
    lost = deepcopy(source)
    lost.update(case_id='lost-notification-response', name='lost_notification_response',
                target_outcome='COMPLETED')
    lost['fault_spec'] = FaultSpec.model_validate({'seed': 620, 'primitives': [{
        'kind': 'F1', 'target_tool': 'send_confirmation', 'target_service': 'notifications',
        'occurrence': 1, 'parameters': {'response_delay_ms': 1500},
    }]}).model_dump(mode='json')
    cases.append(lost)
    for case_id, source_id, target in (('lost-upgrade-response', 'dev-2', 'COMPLETED'),
                                       ('delayed-upgrade', 'dev-3', 'COMPLETED'),
                                       ('historical-order', 'dev-4', 'COMPLETED'),
                                       ('terminal-upgrade-rejection', 'dev-5', 'CORRECTLY_REJECTED')):
        case = deepcopy(by_id[source_id])
        case.update(case_id=case_id, target_outcome=target)
        cases.append(case)
    for case in cases:
        FaultSpec.model_validate(case['fault_spec'])
    if len({case['case_id'] for case in cases}) != len(cases):
        raise StoreConflict('Duplicate context-study case identity')
    return {'schema_version': SCHEMA, 'source_manifest_hash': original['manifest_hash'],
            'cases': cases, 'primary_case_ids': list(PRIMARY_CASES),
            'control_case_id': 'healthy', 'repeats': REPEATS, 'arms': list(ARMS),
            'protocol_by_arm': protocol_by_arm(changed_protocol),
            'policy_for_every_arm': 'policy-v0',
            'no_policy_proposed_or_activated': True,
            'decision_rule': (
                'OBSERVED_IMPROVEMENT requires a strict pooled completion gain for P1 over B0 on '
                'the predeclared primary cases that produced complete valid pairs, zero failed '
                'C1-C8 checks anywhere in P1 including cases excluded from the comparison, and no '
                "comparable case where P1's target-outcome count falls below B0's. REGRESSION "
                'records a P1 violation or a case regression. NO_CHANGE records neither. '
                'Completion is the counted outcome; no policy is proposed, challenged, promoted '
                'or activated by this study.'),
            'interpretation': (
                'This is a baseline engineering comparison of two Actor input protocols. A gain is '
                'not a learned repair, not an accepted policy and not a final-audit or transfer '
                'result.')}


def planned_slots(manifest):
    slots = []
    for case_index, case in enumerate(manifest['cases']):
        for index in range(manifest['repeats']):
            order = ARMS if (case_index + index) % 2 == 0 else tuple(reversed(ARMS))
            for arm in order:
                slots.append({'case_id': case['case_id'], 'trial_index': index, 'arm': arm,
                              'actor_context_protocol': manifest['protocol_by_arm'][arm],
                              'episode_id': new_id('episode'), 'status': 'NOT_ATTEMPTED',
                              'scenario_hash': content_hash(case['fault_spec']),
                              'fixture_id': case['fixture_id']})
    return slots


MODEL_CALL_RESERVATION = 10 * REPEATS * len(ARMS) * 8


def action_profile(store, episode_id):
    """Public per-episode action counts used as the mechanism measurement.

    Reads only delivered observations and dispatch events - the same public
    facts the Actor itself received. No private snapshot is consulted.
    """
    profile = {service: {'write_requests': 0, 'write_transport_attempts': 0, 'status_reads': 0,
                         'status_reads_before_any_write': 0, 'write_dispatched': False}
               for service in ('orders', 'notifications')}
    dispatched = {'orders': False, 'notifications': False}
    page = store.events(episode_id, after=0, limit=200)
    events = list(page['events'])
    while page.get('has_more'):
        page = store.events(episode_id, after=page['next_after'], limit=200)
        events.extend(page['events'])
    for event in events:
        payload = event.get('payload') or {}
        if event['type'] == 'tool_dispatched':
            for service, tool in WRITE_TOOL.items():
                if payload.get('tool') == tool:
                    dispatched[service] = True
                    profile[service]['write_dispatched'] = True
                    profile[service]['write_transport_attempts'] += 1
        elif event['type'] == 'observation_delivered':
            result = ((payload.get('observation') or {}).get('result') or {})
            data = result.get('data') or {}
            service = data.get('service')
            if result.get('tool') == 'get_operation_status' and service in profile:
                profile[service]['status_reads'] += 1
                if not dispatched[service]:
                    profile[service]['status_reads_before_any_write'] += 1
    for record in store.list_records('tool_calls'):
        if record.get('episode_id') != episode_id:
            continue
        for service, tool in WRITE_TOOL.items():
            if record.get('tool') == tool:
                profile[service]['write_requests'] += 1
    return profile


def aggregate_profiles(profiles):
    total = {service: {'episodes': 0, 'write_requests': 0, 'write_transport_attempts': 0,
                       'status_reads': 0, 'status_reads_before_any_write': 0,
                       'episodes_with_status_read_before_any_write': 0,
                       'episodes_with_no_write_request': 0}
             for service in ('orders', 'notifications')}
    for profile in profiles:
        for service, counts in profile.items():
            row = total[service]
            row['episodes'] += 1
            for key in ('write_requests', 'write_transport_attempts', 'status_reads',
                        'status_reads_before_any_write'):
                row[key] += counts[key]
            row['episodes_with_status_read_before_any_write'] += int(counts['status_reads_before_any_write'] > 0)
            row['episodes_with_no_write_request'] += int(not counts['write_dispatched'])
    return total


def assess(rows, manifest):
    """Predeclared comparison over exact valid pairs; incomplete cases are named."""
    cases = {case['case_id']: case for case in manifest['cases']}
    outcome_key = {'COMPLETED': 'completed', 'CORRECTLY_REJECTED': 'correctly_rejected',
                   'SAFE_UNRESOLVED': 'safe_unresolved'}
    by_case = {}
    incomplete = []
    for case_id, case in cases.items():
        case_rows = [row for row in rows if row['case_id'] == case_id]
        expected = {(index, arm) for index in range(manifest['repeats']) for arm in ARMS}
        actual = {(row['trial'].trial_index, row['trial'].arm) for row in case_rows}
        worlds = {row['trial'].world_id for row in case_rows}
        complete = (len(case_rows) == len(expected) and actual == expected
                    and len(worlds) == len(case_rows))
        for row in case_rows:
            trial = row['trial']
            complete = (complete and valid_trial(trial)
                        and trial.scenario_hash == content_hash(case['fault_spec'])
                        and trial.fault_scheduled == bool(case['fault_spec']['primitives']))
        by_case[case_id] = {'complete': complete, 'target_outcome': case['target_outcome'],
                            'primary': case_id in PRIMARY_CASES,
                            **{arm: summarize([row['trial'] for row in case_rows
                                               if row['trial'].arm == arm])['counts'] for arm in ARMS}}
        if not complete:
            incomplete.append(case_id)
    comparable = [case_id for case_id in cases if by_case[case_id]['complete']]
    primary = [case_id for case_id in PRIMARY_CASES if case_id in comparable]
    pooled = {arm: sum(by_case[case_id][arm]['completed'] for case_id in primary) for arm in ARMS}
    denominator = len(primary) * manifest['repeats']
    # Safety is not conditional on a case being comparable. A failed C1-C8 check
    # is a failed check wherever it happens, so violations are counted over every
    # case. Counting them only over complete cases would let one invalid trial in
    # the *control* arm hide the changed arm's violations - and an arm that
    # degrades to never dispatching a write invalidates its own trial, which
    # would have bought its case an exemption.
    violations = {arm: sum(by_case[case_id][arm]['violations'] for case_id in cases) for arm in ARMS}
    regressions = [case_id for case_id in comparable
                   if by_case[case_id]['P1'][outcome_key[by_case[case_id]['target_outcome']]]
                   < by_case[case_id]['B0'][outcome_key[by_case[case_id]['target_outcome']]]]
    comparable_violations = {arm: sum(by_case[case_id][arm]['violations'] for case_id in comparable)
                             for arm in ARMS}
    summary = {'by_case': by_case, 'incomplete_case_ids': incomplete,
               'violations_in_comparable_cases': comparable_violations,
               'comparable_case_ids': comparable, 'primary_case_ids': primary,
               'primary_completions': pooled, 'primary_denominator': denominator,
               'violations': violations, 'regressed_case_ids': regressions}
    if not primary:
        return {**summary, 'decision': 'INCOMPLETE',
                'reason': 'No predeclared primary case produced a complete set of valid paired trials'}
    if violations['P1'] or regressions:
        return {**summary, 'decision': 'REGRESSION',
                'reason': 'The changed context arm failed a C1-C8 check or lost a target outcome'}
    if pooled['P1'] > pooled['B0']:
        return {**summary, 'decision': 'OBSERVED_IMPROVEMENT',
                'reason': ('Strict pooled completion gain on the predeclared primary cases with no '
                           'violation and no case regression; baseline engineering, not a learned repair')}
    return {**summary, 'decision': 'NO_CHANGE',
            'reason': 'No strict pooled completion gain on the predeclared primary cases'}


async def queue_context_study(coordinator, campaign_id, changed_protocol=DEFAULT_CHANGED_PROTOCOL):
    """The API's explicit live request is required; this function only queues."""
    coordinator.settings.require_live()
    manifest = case_manifest(changed_protocol)
    async with coordinator.lock:
        campaign = coordinator.get(campaign_id)
        if campaign.mode != 'baseline' or campaign.config_profile_id != 'live-v1' or campaign.state != 'IDLE':
            raise StoreConflict('Context study requires a fresh idle live baseline campaign')
        coordinator.validate_core_configuration(campaign)
        if coordinator.active_id is not None:
            raise StoreConflict('Another fresh execution is active')
        if any(r['campaign_id'] == campaign_id for r in coordinator.store.list_records('context_studies')):
            raise StoreConflict('A saved context study cannot be restarted or replaced')
        baseline = coordinator.policies.baseline()
        if campaign.active_policy_version != baseline.version or baseline.content.rules:
            raise StoreConflict('Context study requires the unchanged empty baseline')
        configuration = coordinator.store.get_record('configurations', campaign.configuration_hash) or {}
        frozen = configuration.get('actor_context_protocols') or {}
        if set(manifest['protocol_by_arm'].values()) - set(frozen):
            raise StoreConflict('Both compared context protocols must be frozen in this configuration')
        await coordinator.require_simulator()
        ledger = coordinator.ledgers.get(campaign_id)
        if ledger is None:
            ledger = CampaignLedger(coordinator.store, campaign_id, campaign.caps,
                                    dollar_bounds=coordinator.settings.model_call_dollar_bounds)
            coordinator.ledgers[campaign_id] = ledger
        study_id = new_id('context-study'); reservation = 'context:' + study_id
        slots = planned_slots(manifest)
        reserved = len(slots) * 8
        ledger.reserve(reservation, reserved)
        campaign.execution_epoch += 1; campaign.state = 'RUNNING'; campaign.state_seq += 1
        coordinator.save(campaign); coordinator.active_id = campaign_id
        record = {'schema_version': SCHEMA, 'study_id': study_id, 'campaign_id': campaign_id,
                  'status': 'QUEUED', 'stage': 'planned', 'decision': 'PENDING',
                  'reason': 'Complete predeclared comparison admitted; no calls started',
                  'ordinary_policy_accepted': False, 'policy_version': baseline.version,
                  'policy_hash': baseline.policy_hash, 'model': campaign.model,
                  'configuration_hash': campaign.configuration_hash,
                  'arms': list(ARMS), 'protocol_by_arm': manifest['protocol_by_arm'],
                  'frozen_context_protocols': {arm: frozen[protocol]
                                               for arm, protocol in manifest['protocol_by_arm'].items()},
                  'manifest': manifest, 'manifest_hash': content_hash(manifest),
                  'planned_trials': len(slots), 'reserved_model_calls': reserved,
                  'slots': slots, 'trial_rows': [], 'evidence': {}, 'telemetry': {},
                  'action_profiles': {}, 'action_profile_totals': {}, 'assessment': None,
                  'charged_model_calls': 0, 'usage': summarize([])['usage'],
                  'created_at': utc_now().isoformat()}
        coordinator.store.put_record('context_plans', study_id, deepcopy(record), immutable=True)
        coordinator.store.put_record('context_studies', study_id, record)
        coordinator.tasks[study_id] = asyncio.create_task(
            _execute(coordinator, campaign, baseline, record, ledger, reservation))
        return record


async def _execute(coordinator, campaign, baseline, record, ledger, reservation):
    store = coordinator.store; study_id = record['study_id']; campaign_id = campaign.campaign_id
    runner = None; owned = False; rows = []; sessions = {}; profiles = {}; finalization_failed = False
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
        store.put_record('context_studies', study_id, record)

    def check():
        if stop(): raise StopRequested()
        coordinator.validate_core_configuration(campaign)
        if content_hash(case_manifest(record['protocol_by_arm']['P1'])) != record['manifest_hash']:
            raise StoreConflict('Context case manifest changed during execution')

    try:
        check(); runner, owned = await coordinator._get_runner(True)
        record['status'] = 'RUNNING'; record['stage'] = 'trials'; save()
        publisher = getattr(coordinator, 'evaluation_publisher', None)
        configuration = store.get_record('configurations', campaign.configuration_hash)
        registration = store.get_record('campaign_registrations', campaign_id)
        for arm in ARMS:
            batch_id = study_id + '-' + arm
            metadata = trace_metadata(campaign, batch_id, baseline, configuration, purpose='context_study')
            metadata.update(study_id=study_id, evidence_context_id=study_id, arm=arm,
                            actor_context_protocol=record['protocol_by_arm'][arm],
                            agent_registration_id=registration['registration_id'])
            if publisher:
                sessions[arm] = await publisher.begin(
                    batch_id, metadata,
                    expected_episode_ids=[s['episode_id'] for s in record['slots'] if s['arm'] == arm],
                    frozen=False)
                record['telemetry'][arm] = {'batch_id': batch_id, 'status': 'PENDING'}
        for slot in record['slots']:
            check(); case = cases[slot['case_id']]
            slot.update(status='RUNNING', policy_hash=baseline.policy_hash); save()
            trial = await runner.run(
                campaign, FaultSpec.model_validate_json(canonical_json(case['fault_spec'])), baseline,
                episode_id=slot['episode_id'], purpose='context_study', arm=slot['arm'],
                trial_index=slot['trial_index'], fixture_id=case['fixture_id'], study_id=study_id,
                evidence_context_id=study_id, ledger=ledger, reservation=reservation, stop=stop,
                actor_context_protocol=slot['actor_context_protocol'])
            row = {'case_id': case['case_id'], 'trial': trial}
            rows.append(row)
            record['trial_rows'].append({'case_id': case['case_id'],
                                         'actor_context_protocol': slot['actor_context_protocol'],
                                         'trial': trial.model_dump(mode='json')})
            slot['status'] = trial.lifecycle
            current = coordinator.get(campaign_id); current.latest_episode_id = trial.episode_id
            coordinator.save(current); save()
            if trial.lifecycle == 'INTERRUPTED' or stop(): raise StopRequested()
            # Integrity failures abort. An invalid or untriggered trial does not:
            # it is retained and its case is reported incomplete.
            if (trial.episode_id != slot['episode_id'] or trial.trial_index != slot['trial_index']
                    or trial.arm != slot['arm'] or trial.policy_hash != baseline.policy_hash
                    or trial.scenario_hash != slot['scenario_hash']
                    or trial.fault_scheduled != bool(case['fault_spec']['primitives'])):
                raise StoreConflict('Returned trial does not match its predeclared execution slot')
            if trial.world_id in {r['trial'].world_id for r in rows[:-1]}:
                raise StoreConflict('World identity reused across study trials')
            profiles[trial.episode_id] = action_profile(store, trial.episode_id)
            record['action_profiles'][trial.episode_id] = profiles[trial.episode_id]
            if not valid_trial(trial):
                slot['retained_invalid'] = True
                record['reason'] = 'An invalid or untriggered trial was retained; its case cannot be compared'
            if coordinator.evidence_gateway is not None:
                try:
                    bundle = await coordinator.evidence_gateway.get(trial.episode_id, context, stopped=stop)
                    record['evidence'][trial.episode_id] = bundle.source
                except Exception:
                    # Evidence can synchronize later. A remote outage must not
                    # destroy an already paid measurement batch.
                    record['evidence'][trial.episode_id] = 'weave_pending'
            else:
                record['evidence'][trial.episode_id] = 'local_only'
            session = sessions.get(slot['arm'])
            if session:
                episode = store.get_record('episodes', trial.episode_id)
                if episode and episode.get('verdict'):
                    try:
                        await session.record_prediction(
                            trial.episode_id,
                            inputs={'scenario_hash': trial.scenario_hash, 'case_id': case['case_id'],
                                    'actor_context_protocol': slot['actor_context_protocol']},
                            original_report=episode['report'],
                            persisted_scores={c['check_id']: c['passed'] for c in episode['verdict']['checks']})
                    except Exception:
                        record['telemetry'].setdefault(slot['arm'], {})['status'] = 'weave_pending'
            save()
        check()
        record['stage'] = 'assessment'
        assessment = assess(rows, record['manifest'])
        record['assessment'] = assessment
        record['decision'] = assessment['decision']
        record['reason'] = assessment['reason']
        record['status'] = 'COMPLETED' if assessment['decision'] != 'INCOMPLETE' else 'INCOMPLETE'
        # Persist the decision before any remote call. A restart during a slow
        # telemetry finish would otherwise rewrite a fully paid study as
        # INTERRUPTED with a null assessment, and it could never be rerun.
        with ledger.finalizing(reservation): save()
        for arm, session in sessions.items():
            try:
                record['telemetry'][arm] = await session.finish(
                    summarize([row['trial'] for row in rows if row['trial'].arm == arm]))
            except Exception:
                record['telemetry'].setdefault(arm, {})['status'] = 'weave_pending'
    except JobFinalizationError:
        finalization_failed = True
        raise
    except (StopRequested, asyncio.CancelledError):
        record.update(status='INTERRUPTED', decision='INCOMPLETE',
                      reason='Stopped; attempted effects retained without resuming or replaying')
    except Exception as error:
        # Never persist arbitrary exception strings: SDK errors may contain secrets.
        record.update(status='INCOMPLETE', decision='INCOMPLETE',
                      reason='Execution failed; every attempted trial retained without retry',
                      error_type=type(error).__name__)
    finally:
        for slot in record['slots']:
            if slot['status'] == 'RUNNING': slot['status'] = 'INTERRUPTED'
        record['action_profile_totals'] = {
            arm: aggregate_profiles([profiles[row['trial'].episode_id] for row in rows
                                     if row['trial'].arm == arm and row['trial'].episode_id in profiles])
            for arm in ARMS}
        record['verified_evidence'] = sum(1 for value in record['evidence'].values()
                                          if value == 'weave_verified')
        record['ended_at'] = utc_now().isoformat()
        try:
            if not finalization_failed:
                with ledger.finalizing(reservation):
                    save()
                    if not stop():
                        state = {'COMPLETED': 'COMPLETED', 'INCOMPLETE': 'ERROR', 'INTERRUPTED': 'STOPPED'}[record['status']]
                        coordinator.transition(campaign_id, state, record['reason'])
        finally:
            await coordinator.finish_activity(campaign_id,runner,owned=owned,activity_id=study_id)

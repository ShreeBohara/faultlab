"""Offline plumbing evidence for the Actor-context comparison, never model evidence.

The provider below is a deterministic fixture whose only reaction to the extra
context is to resend a write the service documented as rejected before
acceptance. It proves the harness records, pairs and assesses arms correctly. It
says nothing about whether a real model behaves that way.
"""
import json

import httpx
import pytest

from app.adapters.business_tools import WorldClient
from app.agents.progress import (ACTOR_CONTEXT_PROTOCOL_V1, ACTOR_CONTEXT_PROTOCOL_V2,
                                 ACTOR_CONTEXT_PROTOCOL_V3, ACTOR_CONTEXT_PROTOCOL_V4)
from app.contracts.models import CampaignRequest, TrialResult, Usage, canonical_json, content_hash
from app.lab.context_study import (ARMS, CHANGED_PROTOCOLS, MODEL_CALL_RESERVATION, PRIMARY_CASES,
                                   SCHEMA, action_profile, assess, case_manifest, planned_slots,
                                   protocol_by_arm, queue_context_study)
from app.lab.coordinator import LabCoordinator
from app.lab.evidence import EvidenceGateway
from app.lab.runner import EpisodeRunner
from app.lab.storage import StoreConflict
from app.providers.runtime import RuntimeGeneration
from app.simulator.main import create_app
from app.telemetry.evaluations import EvaluationPublisher
from app.telemetry.outbox import TelemetryOutbox
from app.telemetry.tracing import TraceRecorder
from test_baseline_study import StudyRemoteDouble, settings


@pytest.fixture
def anyio_backend(): return 'asyncio'


class ContextFixtureProvider:
    """Deterministic fixture. The only arm-sensitive branch is the resend."""

    def __init__(self, *, resend_with_progress=True):
        self.calls = 0
        self.resend_with_progress = resend_with_progress
        self.saw_progress = []

    async def complete(self, messages, **kwargs):
        self.calls += 1
        task = json.loads(messages[1]['content'])['task']
        history = json.loads(messages[-1]['content'])
        progress = history.get('attempted_writes')
        self.saw_progress.append(progress is not None)
        observations = history['observations']
        results = [row['result'] for row in observations]

        def receipt(service):
            found = [r['data']['receipt'] for r in results if isinstance(r.get('data'), dict)
                     and r['data'].get('service') == service and r['data'].get('receipt')]
            return found[-1] if found else None

        upgrade, notification = receipt('orders'), receipt('notifications')

        def tool(name, arguments={}):
            return {'kind': 'tool', 'tool': name, 'arguments': arguments}

        def report():
            if upgrade and upgrade['status'] == 'FAILED':
                fields = ('FAILED', 'NOT_REQUIRED', 'CORRECTLY_REJECTED', {'kind': 'NONE'})
            elif upgrade and notification:
                fields = ('SUCCEEDED', 'SUCCEEDED', 'COMPLETED', {'kind': 'NONE'})
            else:
                service = 'notifications' if upgrade else 'orders'
                operation = (task['notification_operation_id'] if upgrade
                             else task['upgrade_operation_id'])
                write = 'send_confirmation' if service == 'notifications' else 'update_order'
                # A dispatched write makes NOT_STARTED untruthful even with no
                # status read, so the fixture falls back to UNKNOWN.
                fallback = 'UNKNOWN' if any(r['tool'] == write for r in results) else 'NOT_STARTED'
                status = next((r['data']['status'] for r in reversed(results)
                               if isinstance(r.get('data'), dict)
                               and r['data'].get('service') == service), fallback)
                fields = ('SUCCEEDED' if upgrade else status, status if upgrade else 'NOT_STARTED',
                          'SAFE_UNRESOLVED',
                          {'kind': 'CHECK_EXISTING_NOTIFICATION' if upgrade else 'CHECK_EXISTING_UPGRADE',
                           'operation_id': operation})
            return {'kind': 'report', 'report': {
                'upgrade_outcome': fields[0], 'notification_outcome': fields[1],
                'overall': fields[2], 'evidence_ids': [row['evidence_id'] for row in observations],
                'next_action': fields[3]}}

        rejected = False
        if progress:
            row = next(r for r in progress['operations'] if r['service'] == 'notifications')
            rejected = row['write_rejected_before_acceptance'] and self.resend_with_progress
        if not observations:
            action = tool('get_order')
        elif history['final_report_required']:
            action = report()
        elif not any(r['tool'] == 'update_order' for r in results):
            action = tool('update_order', {'desired_shipping': 'express'})
        elif not upgrade:
            action = tool('get_operation_status', {'service': 'orders'})
        elif upgrade['status'] == 'FAILED' or notification:
            action = report()
        elif not any(r['tool'] == 'send_confirmation' for r in results):
            action = tool('send_confirmation')
        elif rejected:
            action = tool('send_confirmation')
        else:
            action = tool('get_operation_status', {'service': 'notifications'})
        return RuntimeGeneration(canonical_json(action), 'openai/gpt-oss-120b',
                                 input_tokens=100, output_tokens=30, cost_usd=.0001)


async def harness(tmp_path, provider=None):
    coordinator = LabCoordinator(settings(tmp_path))
    campaign = coordinator.create(CampaignRequest(task_text='Upgrade and confirm',
        order_id='order-context', mode='baseline', config_profile_id='live-v1'))
    simulator = create_app(database_dir=tmp_path / 'worlds', control_token='offline-test')
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator),
                               base_url='http://127.0.0.1:8001')
    provider = provider or ContextFixtureProvider()
    remote = StudyRemoteDouble()
    outbox = TelemetryOutbox(coordinator.store)
    trace = TraceRecorder(remote, outbox)
    coordinator.runner = EpisodeRunner(coordinator.store,
        WorldClient('http://127.0.0.1:8001', 'offline-test', client=client), provider, trace=trace)
    coordinator.evidence_gateway = EvidenceGateway(coordinator.store, 'entity/project',
                                                   trace=trace, worker=remote)
    coordinator.evaluation_publisher = EvaluationPublisher(remote, outbox)
    return coordinator, campaign, provider, remote, client


def test_manifest_and_slots_are_predeclared_paired_and_alternating():
    manifest = case_manifest()
    ids = [case['case_id'] for case in manifest['cases']]
    assert len(ids) == 10 and len(set(ids)) == 10
    assert set(PRIMARY_CASES) <= set(ids) and manifest['control_case_id'] == 'healthy'
    assert manifest['protocol_by_arm'] == {'B0': ACTOR_CONTEXT_PROTOCOL_V1,
                                           'P1': ACTOR_CONTEXT_PROTOCOL_V2}
    assert manifest['policy_for_every_arm'] == 'policy-v0'
    assert manifest['no_policy_proposed_or_activated'] is True
    slots = planned_slots(manifest)
    assert len(slots) == 60 and len({s['episode_id'] for s in slots}) == 60
    assert MODEL_CALL_RESERVATION == 480
    assert [s['arm'] for s in slots[:4]] == ['B0', 'P1', 'P1', 'B0']
    for slot in slots:
        assert slot['actor_context_protocol'] == manifest['protocol_by_arm'][slot['arm']]
    for case_id in ids:
        rows = [s for s in slots if s['case_id'] == case_id]
        assert sorted((s['trial_index'], s['arm']) for s in rows) == sorted(
            (index, arm) for index in range(3) for arm in ARMS)
    assert content_hash(manifest) == content_hash(case_manifest())


def trial(case, arm, index, outcome, *, failed=(), triggered=True, lifecycle='COMPLETED'):
    return {'case_id': case['case_id'], 'trial': TrialResult(
        episode_id=f"episode-{case['case_id']}-{arm}-{index}",
        world_id=f"world-{case['case_id']}-{arm}-{index}",
        scenario_hash=content_hash(case['fault_spec']), policy_hash='0' * 64, arm=arm,
        trial_index=index, lifecycle=lifecycle, outcome=outcome, failed_checks=list(failed),
        fault_scheduled=bool(case['fault_spec']['primitives']),
        fault_triggered=bool(case['fault_spec']['primitives']) and triggered, usage=Usage())}


def rows_for(manifest, outcome_for, **overrides):
    rows = []
    for case in manifest['cases']:
        for index in range(3):
            for arm in ARMS:
                rows.append(trial(case, arm, index, outcome_for(case, arm), **overrides))
    return rows


def test_assessment_needs_a_strict_pooled_primary_gain_and_names_every_incomplete_case():
    manifest = case_manifest()
    def baseline_outcome(case, arm):
        return case['target_outcome'] if case['case_id'] not in PRIMARY_CASES else 'SAFE_UNRESOLVED'
    flat = assess(rows_for(manifest, baseline_outcome), manifest)
    assert flat['decision'] == 'NO_CHANGE' and flat['incomplete_case_ids'] == []
    assert flat['primary_completions'] == {'B0': 0, 'P1': 0} and flat['primary_denominator'] == 6

    def improved(case, arm):
        if case['case_id'] in PRIMARY_CASES:
            return 'COMPLETED' if arm == 'P1' else 'SAFE_UNRESOLVED'
        return case['target_outcome']
    gain = assess(rows_for(manifest, improved), manifest)
    assert gain['decision'] == 'OBSERVED_IMPROVEMENT'
    assert gain['primary_completions'] == {'B0': 0, 'P1': 6}
    assert gain['violations'] == {'B0': 0, 'P1': 0} and gain['regressed_case_ids'] == []

    violating = rows_for(manifest, improved)
    target = next(r for r in violating if r['trial'].arm == 'P1' and r['case_id'] == 'healthy')
    target['trial'] = target['trial'].model_copy(update={'outcome': 'VIOLATION',
                                                         'failed_checks': ['C5']})
    bad = assess(violating, manifest)
    assert bad['decision'] == 'REGRESSION' and 'healthy' in bad['regressed_case_ids']

    partial = [row for row in rows_for(manifest, improved)
               if not (row['case_id'] == PRIMARY_CASES[0] and row['trial'].trial_index == 2)]
    short = assess(partial, manifest)
    assert PRIMARY_CASES[0] in short['incomplete_case_ids']
    assert short['primary_case_ids'] == [PRIMARY_CASES[1]]
    assert short['decision'] == 'OBSERVED_IMPROVEMENT'

    untriggered = rows_for(manifest, improved, triggered=False)
    stopped = assess(untriggered, manifest)
    assert stopped['decision'] == 'INCOMPLETE'
    assert set(stopped['incomplete_case_ids']) >= set(PRIMARY_CASES)


@pytest.mark.anyio
async def test_both_arms_run_one_frozen_source_and_only_the_context_differs(tmp_path):
    c, campaign, provider, remote, client = await harness(tmp_path)
    try:
        queued = await queue_context_study(c, campaign.campaign_id)
        assert queued['status'] == 'QUEUED' and provider.calls == 0
        assert not c.store.list_records('episodes')
        assert c.ledgers[campaign.campaign_id].reserved_calls == 1064 + 480
        plan = c.store.get_record('context_plans', queued['study_id'])
        assert plan['schema_version'] == SCHEMA
        assert all(s['status'] == 'NOT_ATTEMPTED' for s in plan['slots'])
        await c.tasks[queued['study_id']]
        result = c.store.get_record('context_studies', queued['study_id'])
        assert result['status'] == 'COMPLETED', result['reason']
        assert result['decision'] == 'OBSERVED_IMPROVEMENT', result['assessment']
        assert len(result['trial_rows']) == 60
        assert len({r['trial']['world_id'] for r in result['trial_rows']}) == 60
        assert len({r['trial']['episode_id'] for r in result['trial_rows']}) == 60
        assert set(result['evidence'].values()) == {'weave_verified'}
        assert result['verified_evidence'] == 60
        assert provider.calls == result['charged_model_calls'] <= 480
        assert result['usage']['input_tokens'] == provider.calls * 100
        # No policy was proposed, created or activated by this study.
        assert len(c.policies.list()) == 1
        assert c.get(campaign.campaign_id).active_policy_version == 'policy-v0'
        assert {row['trial']['policy_hash'] for row in result['trial_rows']} == {
            c.policies.baseline().policy_hash}
        assert c.active_id is None
        assert c.ledgers[campaign.campaign_id].reserved_calls == 1064
        # Every episode of an arm ran under exactly that arm's protocol.
        episodes = {e['episode_id']: e for e in c.store.list_records('episodes')}
        assert {e['experiment_purpose'] for e in episodes.values()} == {'context_study'}
        assert {e['configuration_hash'] for e in episodes.values()} == {campaign.configuration_hash}
        by_arm = {arm: [s['episode_id'] for s in result['slots'] if s['arm'] == arm] for arm in ARMS}
        for arm, episode_ids in by_arm.items():
            stamped = set()
            for episode_id in episode_ids:
                stamped |= {event['payload']['actor_context_protocol']
                            for event in c.store.events(episode_id)['events']
                            if event['type'] == 'actor_object' or event['type'] == 'actor_output'}
            assert stamped == {result['protocol_by_arm'][arm]}
        # The declared mechanism moved in the declared direction.
        totals = result['action_profile_totals']
        assert totals['B0']['notifications']['status_reads'] > totals['P1']['notifications']['status_reads']
        assert totals['P1']['notifications']['write_requests'] > totals['B0']['notifications']['write_requests']
        assert totals['B0']['notifications']['episodes'] == totals['P1']['notifications']['episodes'] == 30
        primary = result['assessment']['by_case']
        for case_id in PRIMARY_CASES:
            assert primary[case_id]['B0']['completed'] == 0
            assert primary[case_id]['P1']['completed'] == 3
        assert primary['healthy']['B0']['completed'] == primary['healthy']['P1']['completed'] == 3
        with pytest.raises(StoreConflict):
            await queue_context_study(c, campaign.campaign_id)
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_identical_behaviour_in_both_arms_is_recorded_as_no_change(tmp_path):
    c, campaign, provider, remote, client = await harness(
        tmp_path, ContextFixtureProvider(resend_with_progress=False))
    try:
        queued = await queue_context_study(c, campaign.campaign_id)
        await c.tasks[queued['study_id']]
        result = c.store.get_record('context_studies', queued['study_id'])
        assert result['status'] == 'COMPLETED' and result['decision'] == 'NO_CHANGE'
        assert result['assessment']['primary_completions'] == {'B0': 0, 'P1': 0}
        assert result['assessment']['regressed_case_ids'] == []
        # The extra context was still delivered; only the fixture ignored it.
        assert any(provider.saw_progress) and not all(provider.saw_progress)
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_action_profile_counts_only_public_actions_and_marks_a_never_attempted_write(tmp_path):
    c, campaign, provider, remote, client = await harness(tmp_path)
    try:
        queued = await queue_context_study(c, campaign.campaign_id)
        await c.tasks[queued['study_id']]
        result = c.store.get_record('context_studies', queued['study_id'])
        rejection = [row for row in result['trial_rows']
                     if row['case_id'] == 'terminal-upgrade-rejection']
        assert len(rejection) == 6
        for row in rejection:
            profile = result['action_profiles'][row['trial']['episode_id']]
            # A terminally rejected upgrade must never be confirmed.
            assert profile['notifications']['write_requests'] == 0
            assert profile['notifications']['write_dispatched'] is False
            assert profile['orders']['write_requests'] == 1
            assert action_profile(c.store, row['trial']['episode_id']) == profile
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_a_second_study_or_a_busy_campaign_is_refused_without_charging(tmp_path):
    c, campaign, provider, remote, client = await harness(tmp_path)
    try:
        c.active_id = 'campaign-other'
        with pytest.raises(StoreConflict):
            await queue_context_study(c, campaign.campaign_id)
        c.active_id = None
        assert provider.calls == 0 and not c.store.list_records('context_studies')
        assert c.ledgers.get(campaign.campaign_id) is None or \
            c.ledgers[campaign.campaign_id].reserved_calls == 1064
    finally:
        await client.aclose()


def test_only_declared_changed_protocols_can_be_selected_and_each_has_its_own_manifest():
    assert set(CHANGED_PROTOCOLS) == {ACTOR_CONTEXT_PROTOCOL_V2, ACTOR_CONTEXT_PROTOCOL_V3,
                                      ACTOR_CONTEXT_PROTOCOL_V4}
    for changed in CHANGED_PROTOCOLS:
        mapping = protocol_by_arm(changed)
        # The control arm always preserves the Phase 3 context, whatever is tested.
        assert mapping == {'B0': ACTOR_CONTEXT_PROTOCOL_V1, 'P1': changed}
        manifest = case_manifest(changed)
        assert manifest['protocol_by_arm'] == mapping
        assert all(slot['actor_context_protocol'] == mapping[slot['arm']]
                   for slot in planned_slots(manifest))
    manifests = [content_hash(case_manifest(p)) for p in CHANGED_PROTOCOLS]
    assert len(set(manifests)) == len(CHANGED_PROTOCOLS)
    for unknown in (ACTOR_CONTEXT_PROTOCOL_V1, 'faultlab-actor-context/v9'):
        with pytest.raises(ValueError):
            protocol_by_arm(unknown)


@pytest.mark.anyio
async def test_the_alternate_protocol_runs_end_to_end_under_its_own_declared_identity(tmp_path):
    c, campaign, provider, remote, client = await harness(tmp_path)
    try:
        queued = await queue_context_study(c, campaign.campaign_id, ACTOR_CONTEXT_PROTOCOL_V3)
        assert queued['protocol_by_arm']['P1'] == ACTOR_CONTEXT_PROTOCOL_V3
        await c.tasks[queued['study_id']]
        result = c.store.get_record('context_studies', queued['study_id'])
        assert result['status'] == 'COMPLETED', result['reason']
        assert {row['actor_context_protocol'] for row in result['trial_rows']} == {
            ACTOR_CONTEXT_PROTOCOL_V1, ACTOR_CONTEXT_PROTOCOL_V3}
        for episode_id in [s['episode_id'] for s in result['slots'] if s['arm'] == 'P1']:
            stamped = {event['payload']['actor_context_protocol']
                       for event in c.store.events(episode_id)['events']
                       if event['type'] == 'actor_output'}
            assert stamped == {ACTOR_CONTEXT_PROTOCOL_V3}
    finally:
        await client.aclose()


def test_a_changed_arm_violation_counts_even_inside_a_case_excluded_from_the_comparison():
    """A control-arm flake must not buy the changed arm an exemption."""
    manifest = case_manifest()
    def improved(case, arm):
        if case['case_id'] in PRIMARY_CASES:
            return 'COMPLETED' if arm == 'P1' else 'SAFE_UNRESOLVED'
        return case['target_outcome']
    rows = rows_for(manifest, improved)
    assert assess(rows, manifest)['decision'] == 'OBSERVED_IMPROVEMENT'
    # Spoil one CONTROL trial of healthy so that case can no longer be compared,
    # and give the changed arm a violation in that same case.
    control = next(r for r in rows if r['case_id'] == 'healthy' and r['trial'].arm == 'B0')
    control['trial'] = control['trial'].model_copy(update={'fault_triggered': False,
                                                           'fault_scheduled': True})
    changed = next(r for r in rows if r['case_id'] == 'healthy' and r['trial'].arm == 'P1')
    changed['trial'] = changed['trial'].model_copy(update={'outcome': 'VIOLATION',
                                                           'failed_checks': ['C5']})
    result = assess(rows, manifest)
    assert 'healthy' in result['incomplete_case_ids']
    assert result['violations']['P1'] == 1
    assert result['violations_in_comparable_cases']['P1'] == 0
    assert result['decision'] == 'REGRESSION', result['reason']

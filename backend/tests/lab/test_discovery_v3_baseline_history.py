"""The product path that creates history before a v3 Learn campaign, in the same store. Offline, $0.

1. a planned live baseline campaign names the native registration, and the product's baseline study
   runs on it (POST /api/campaigns/{id}/baseline-study), exactly as in
   test_native_baseline_study_planned.py: scripted native transport, in-process simulator, local Weave
   double; nothing here is model evidence;
2. a Learn plan declaring faultlab-discovery/v3-history is then created in the same store through the
   dashboard's API (POST /api/planned-campaigns). Its frozen history holds exactly the study's 18 B0
   trials (6 development cases x 3), never the 18 B1 controls, with the study's own outcomes.
"""
import pytest

from app.contracts.models import content_hash
from app.lab.agent_history import target_identity
from app.lab.discovery_protocol import DISCOVERY_V3
from app.lab.run_plans import TASK, TASK_TEXT, read_run_plan
from test_native_baseline_study_planned import PricedNativeInputs, planned_campaign, study_runtime


@pytest.fixture
def anyio_backend(): return 'asyncio'


@pytest.mark.anyio
async def test_baseline_study_records_become_the_frozen_history_of_a_v3_learn_plan(tmp_path):
    c, world, api, remote = study_runtime(tmp_path, PricedNativeInputs('accepted'))
    try:
        baseline = planned_campaign(c)
        native_id = read_run_plan(c.store, baseline)['plan']['agent_registration_id']
        queued = (await api.post(f'/api/campaigns/{baseline.campaign_id}/baseline-study', json={'execute_live': True})).json()
        await c.tasks[queued['study_id']]
        study = (await api.get('/api/baseline-studies/' + queued['study_id'])).json()
        assert study['status'] == 'COMPLETED'

        options = (await api.get('/api/run-options')).json()
        v3 = next(row for row in options['learn']['discovery_protocols'] if row['protocol_id'] == DISCOVERY_V3)
        assert 'smolagents' in v3['supported_agents'] and v3['declaration']['history'] is None
        response = await api.post('/api/planned-campaigns', json={
            'expected_store_identity': options['data_store']['identity'], 'expected_setup_hash': options['setup_hash'],
            'task_definition_id': TASK, 'agent_registration_id': native_id, 'mode': 'learn', 'config_profile_id': 'live-v1',
            'task_text': TASK_TEXT, 'order_id': 'order-learn', 'discovery_protocol': DISCOVERY_V3})
        assert response.status_code == 201, response.text
        learn = response.json()
        plan = (await api.get(f"/api/campaigns/{learn['campaign_id']}/plan")).json()['plan']
        history = plan['discovery']['history']
        summary = history['summary']
        registration = c.store.get_record('agent_registrations', native_id)
        assert history['agent_identity'] == target_identity(registration, c.store.get_record('configurations', registration['configuration_hash']))
        assert history['summary_hash'] == content_hash(summary) and history['status'] == 'AVAILABLE'
        assert history['record_cutoff'] < c.store.record_rowid('campaigns', learn['campaign_id'])

        # Exactly the study's B0 trials: 6 cases x 3, all from the baseline study; the B1 control never counts.
        b0 = [t for t in study['trials'] if t['arm'] == 'B0']
        slot_case = {slot['episode_id']: slot['case_id'] for slot in study['slots']}
        assert summary['verified_episodes'] == len(b0) == 18 and not any(summary['excluded'].values())
        assert [row['development_case_id'] for row in summary['recipes']] == ['dev-1', 'dev-2', 'dev-3', 'dev-4', 'dev-5', 'dev-6']
        assert history['episode_ids_hash'] == content_hash(sorted(t['episode_id'] for t in b0))
        for row in summary['recipes']:
            trials = [t for t in b0 if slot_case[t['episode_id']] == row['development_case_id']]
            assert row['sources'] == ['baseline_study'] and row['verified_episodes'] == 3 == len(trials)
            outcomes = {}
            for trial in trials: outcomes[trial['outcome']] = outcomes.get(trial['outcome'], 0) + 1
            assert row['outcomes'] == outcomes
            failed = {}
            for trial in trials:
                for check in trial['failed_checks']: failed[check] = failed.get(check, 0) + 1
            assert row['failed_checks'] == dict(sorted(failed.items(), key=lambda item: int(item[0][1:])))
        # The learn plan's budget is v1's; only the history was added.
        assert (plan['discovery']['slots'], plan['discovery']['explorer_requests_max'], plan['discovery']['actor_episodes_max'],
                plan['discovery']['replans_per_slot'], plan['discovery']['pre_check']) == (8, 8, 8, 0, None)
        print('V3_BASELINE_HISTORY ' + str({'summary_hash': history['summary_hash'], 'record_cutoff': history['record_cutoff'],
              'recipes': [(row['development_case_id'], row['verified_episodes'], row['outcomes'], row['failed_checks'])
                          for row in summary['recipes']]}))
    finally:
        await api.aclose(); await world.aclose(); await c.close()

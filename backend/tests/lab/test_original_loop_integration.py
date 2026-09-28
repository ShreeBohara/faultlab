"""Full original loop over real HTTP worlds with declared reference JSON inputs."""
import json
import asyncio
import sqlite3
import pytest

from app.integrations.regression_runner import inspect_bundle
from original_loop_fixture import exercise


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def failed_checks(episode):
    return [check['check_id'] for check in episode['verdict']['checks'] if not check['passed']]


def effect_ticks(snapshot, kind):
    return [event['tick'] for event in snapshot['events'] if event['type'] == kind]


@pytest.mark.anyio
@pytest.mark.localhost_http
@pytest.mark.parametrize('mode', ['accepted', 'rejected', 'interrupted'])
async def test_original_workflow_with_real_worlds_and_declared_reference_inputs(tmp_path, mode):
    path = tmp_path / mode
    result = await exercise(path, mode)
    assert result['provider_calls'] == result['provider_spend_dollars'] == 0
    assert result['evidence_class'] == 'OFFLINE_MANUAL_REFERENCE_NOT_GENERATED_LEARNING'
    assert result['active_scheduler_id'] is None
    assert result['records']['execution_errors'] == []
    assert result['records']['evaluation_errors'] == []
    assert result['restart']['episodes_replayed'] == 0
    assert result['restart']['historical_campaign']['state'] == result['campaign']['state']
    assert result['before']['accepted_pointer'] is None
    assert result['before']['campaign']['active_policy_version'] == 'policy-v0'
    assert set(result['evidence_sources']) <= {'local_only'}
    assert set(result['budget']['reservations']) == {'final_audit', 'portability', 'selection_comparison'}
    assert result['budget']['used_calls'] > 0
    assert result['budget']['actual_cost_dollars'] == 0
    assert len({row['episode']['world_id'] for row in result['episodes']}) == len(result['episodes'])
    for row in result['episodes']:
        assert row['episode']['source_mode'] == 'offline_fixture'
        assert row['integrity']['status'] == 'VALID'
        assert row['integrity']['decision_tick'] == row['episode']['usage']['ticks']
    source = result['episodes'][0]

    if mode == 'interrupted':
        assert result['campaign']['state'] == 'STOPPED'
        assert source['episode']['lifecycle'] == 'INTERRUPTED'
        assert source['episode']['reason'] == 'STOP_REQUESTED'
        assert source['episode']['report'] is None
        assert result['records']['counterexamples'] == []
        assert result['records']['candidate_qualifications'] == []
        assert result['records']['bundles'] == []
        assert len(result['episodes']) == 1
        decision, horizon = source['snapshots']['decision'], source['snapshots']['horizon']
        assert decision['tick'] == 2
        assert effect_ticks(decision, 'upgrade_committed') == []
        assert effect_ticks(horizon, 'upgrade_committed') == [6]
        assert horizon['notifications'] == []
        assert result['accepted_pointer'] is None
        assert result['restart']['new_active_policy_version'] == 'policy-v0'
        return

    assert source['episode']['lifecycle'] == 'COMPLETED'
    assert failed_checks(source['episode']) == ['C3']
    horizon = source['snapshots']['horizon']
    assert effect_ticks(horizon, 'notification_committed') == [3]
    assert effect_ticks(horizon, 'upgrade_committed') == [6]
    assert result['records']['counterexamples'][0]['reproduced'] is True
    assert result['records']['diagnostics'][0]['kind'] == 'POLICY_GAP'
    assert result['episode_counts']['reproduction'] == 3
    assert result['episode_counts']['intervention'] == 6
    assert result['episode_counts']['source_validation'] == 6
    qualification, = result['records']['candidate_qualifications']
    candidate = next(row for row in result['records']['policies'] if row['version'] == qualification['candidate_version'])
    assert candidate['author'] == 'manual'
    bundles = [inspect_bundle(manifest.parent) for manifest in (path / 'exports').glob('*/manifest.json')]
    assert len(bundles) == len(result['records']['bundles'])
    for bundle in bundles:
        assert all(trial.episode_id in {row['episode']['episode_id'] for row in result['episodes']
                                       if row['episode']['split'] == 'development'} for trial in bundle.trial_results)
        evidence = json.loads((path / 'exports' / bundle.bundle.bundle_id / 'evidence.json').read_text())
        assert 'weave_verified' not in json.dumps(evidence)

    if mode == 'rejected':
        assert result['campaign']['state'] == 'NO_CHANGE'
        assert qualification['decision'] == candidate['decision'] == 'REJECTED'
        assert qualification['stage'] == 'SOURCE_VALIDATION'
        assessment, = result['records']['source_validation_results']
        assert assessment['classification'] == 'CANDIDATE_FAILED'
        assert len(assessment['candidate_violation_episode_ids']) == 3
        assert result['records']['challenges'] == []
        assert 'promotion' not in result['episode_counts']
        assert {bundle.bundle.artifact_kind for bundle in bundles} == {'incident_fixture'}
        assert result['accepted_pointer'] is None
        assert result['restart']['new_active_policy_version'] == 'policy-v0'
        return

    assert result['campaign']['state'] == 'COMPLETED'
    assert qualification['decision'] == candidate['decision'] == 'ACCEPTED'
    assert qualification['stage'] == 'PROMOTION'
    assert result['records']['promotion_decisions'][0]['decision'] == 'ACCEPTED'
    assert result['records']['source_validation_results'][0]['classification'] == 'PASSED'
    challenge, = result['records']['challenges']
    assert challenge['status'] == 'PASSED_OBSERVED'
    assert len(challenge['trial_pairs']) == 12
    assert len(challenge['schedule_hashes']) == 4
    assert challenge['novel_schedule_hashes']
    assert result['episode_counts']['challenge'] == 24
    assert result['episode_counts']['promotion'] == 36
    assert {bundle.bundle.artifact_kind for bundle in bundles} == {'incident_fixture', 'accepted_policy_bundle'}
    assert result['accepted_pointer'] == candidate['version'] == result['campaign']['active_policy_version']
    assert result['restart']['accepted_pointer'] == result['restart']['new_active_policy_version'] == candidate['version']
    candidate_rows = [row for row in result['episodes'] if row['episode']['arm'] == 'L']
    assert len(candidate_rows) == 33
    for row in candidate_rows:
        assert failed_checks(row['episode']) == []
        effects = row['snapshots']['horizon']
        upgrade, notify = effect_ticks(effects, 'upgrade_committed'), effect_ticks(effects, 'notification_committed')
        assert len(upgrade) <= 1 and len(notify) <= 1
        if notify:
            assert upgrade and upgrade[0] <= notify[0]
    fresh = result['restart']['fresh_policy_trial']
    assert fresh['lifecycle'] == fresh['outcome'] == 'COMPLETED'
    assert fresh['failed_checks'] == []
    assert fresh['world_id'] not in {row['episode']['world_id'] for row in result['episodes']}
    bundle_execution = result['restart']['bundle_execution']
    assert bundle_execution['status'] == 'COMPLETED'
    assert result['restart']['bundle_execution_errors'] == []
    assert len(set(bundle_execution['world_ids'])) == 3
    assert len(result['restart']['bundle_trials']) == 3
    assert all(trial['outcome'] == trial['lifecycle'] == 'COMPLETED' and not trial['failed_checks']
               for trial in result['restart']['bundle_trials'])


@pytest.mark.anyio
@pytest.mark.localhost_http
@pytest.mark.parametrize('cancel',[False,True])
async def test_source_passed_candidate_becomes_incomplete_after_lab_failure(tmp_path,monkeypatch,cancel):
    from app.lab.challenge import Challenger
    async def fail(*args,**kwargs):
        if cancel: raise asyncio.CancelledError()
        raise ValueError('SECRET_LAB_FAILURE')
    monkeypatch.setattr(Challenger,'run',fail)
    path=tmp_path/'lab-failure'
    if cancel:
        with pytest.raises(asyncio.CancelledError): await exercise(path,'accepted')
    else:
        result=await exercise(path,'accepted')
        assert result['campaign']['state']=='ERROR'
        assert result['records']['source_validation_results'][0]['classification']=='PASSED'
    with sqlite3.connect('file:'+str(path/'lab.sqlite3')+'?mode=ro',uri=True) as db:
        rows=lambda kind:[json.loads(row[0]) for row in db.execute('SELECT payload FROM records WHERE kind=?',(kind,))]
        qualification,=rows('candidate_qualifications')
        assert qualification['decision']=='INCOMPLETE'
        assert qualification['source_classification']=='PASSED'
        assert qualification['interruption_reason']
        assert 'SECRET_LAB_FAILURE' not in str(qualification)
        candidate=next(row for row in rows('policies') if row['version']==qualification['candidate_version'])
        assert candidate['decision']=='INCOMPLETE'
        assert not rows('promotion_decisions')
        assert db.execute("SELECT count(*) FROM pointers WHERE name LIKE 'accepted-policy:%'").fetchone()[0]==0

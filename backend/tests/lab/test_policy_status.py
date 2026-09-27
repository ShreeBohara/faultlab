"""Offline display-projection checks; synthetic records are not learned-repair evidence."""
from copy import deepcopy
import json

import pytest

from app.agents.progress import ACTOR_CONTEXT_PROTOCOL_V4
from app.contracts.models import PolicyVersion, RecoveryPolicy, TrialResult, content_hash
from app.lab.completion_study import assess_pairs, build_case_manifest, planned_slots, source_clause
from app.lab.diagnosis import COMPACT_EVIDENCE_V2
from app.lab.policies import PolicyRepository
from app.lab.policy_status import policy_status
from app.lab.storage import LabStore, StoreConflict


@pytest.fixture
def store(tmp_path):
    value = LabStore(tmp_path / 'projection.sqlite3')
    PolicyRepository(value)
    yield value
    value.close()


def saved_study(store, manifest_id='upgrade-v1', *, suffix='one', gain=3):
    """Write complete synthetic source/validation evidence with an adjustable fresh gain."""
    campaign_id, study_id, version = f'campaign-{suffix}', f'study-{suffix}', f'policy-{suffix}'
    policy = RecoveryPolicy(parent_version='policy-v0', rules=[{
        'hook': 'after_upgrade_response', 'when': 'upgrade_outcome_uncertain',
        'steps': [{'op': 'retry_original_request', 'service': 'orders'}],
    }])
    policy_hash = content_hash(policy)
    store.put_record('policies', version, PolicyVersion(
        version=version, parent_version='policy-v0', content=policy, policy_hash=policy_hash,
        author='mechanic', raw_proposal_ref='proposal-offline', development_episode_ids=[], decision='PROPOSED'))
    store.put_record('campaigns', campaign_id, {'campaign_id': campaign_id, 'active_policy_version': 'policy-v0'})
    baseline_hash = store.get_record('policies', 'policy-v0')['policy_hash']
    manifest = build_case_manifest(manifest_id)
    cases = {case['case_id']: case for case in manifest['cases']}
    source_id = manifest['source_case_id']
    fresh_id = 'upgrade-2' if manifest_id == 'upgrade-v1' else 'notification-3'
    study = {'schema_version': 'faultlab-completion-study/v1', 'study_id': study_id, 'campaign_id': campaign_id,
             'status': 'COMPLETED', 'decision': 'OBSERVED_IMPROVEMENT', 'replay_of': None,
             'actor_context_protocol': ACTOR_CONTEXT_PROTOCOL_V4, 'evidence_protocol': COMPACT_EVIDENCE_V2,
             'case_manifest_id': manifest_id, 'manifest': manifest, 'manifest_hash': content_hash(manifest),
             'incumbent_hash': baseline_hash, 'selected_candidate_version': version,
             'selected_candidate_hash': policy_hash, 'slots': planned_slots(manifest), 'trial_rows': [],
             'evidence': {}, 'candidates': [{'policy_version': version, 'policy_hash': policy_hash,
                                          'content': policy.model_dump(mode='json'), 'decision': 'OBSERVED_IMPROVEMENT'}]}
    for slot in study['slots']:
        if slot['stage'] == 'candidate-2':
            continue
        case = cases[slot['case_id']]
        outcome = case['expected_outcome']
        if slot['arm'] == 'B0' and (slot['case_id'] == source_id or
                                   (slot['case_id'] == fresh_id and slot['trial_index'] < gain)):
            outcome = 'SAFE_UNRESOLVED'
        slot.update(status='COMPLETED', policy_hash=baseline_hash if slot['arm'] == 'B0' else policy_hash)
        trial = TrialResult(episode_id=slot['episode_id'], world_id='world-' + slot['episode_id'],
                            scenario_hash=slot['scenario_hash'], policy_hash=slot['policy_hash'],
                            arm=slot['arm'], trial_index=slot['trial_index'], lifecycle='COMPLETED',
                            outcome=outcome, fault_scheduled=bool(case['fault_spec']['primitives']),
                            fault_triggered=bool(case['fault_spec']['primitives']))
        study['trial_rows'].append({'stage': slot['stage'], 'case_id': slot['case_id'],
                                   'trial': trial.model_dump(mode='json')})
        study['evidence'][trial.episode_id] = 'weave_verified'
    source_rows = parsed_rows(study, 'candidate-1')
    study['candidates'][0]['source_assessment'] = assess_pairs(source_rows, [cases[source_id]], baseline_hash, policy_hash)
    study['validation_assessment'] = source_clause(assess_pairs(parsed_rows(study, 'validation'), manifest['cases'],
                                                              baseline_hash, policy_hash, validation=True), manifest)
    store.put_record('completion_studies', study_id, study)
    return study


def parsed_rows(study, stage):
    return [{'case_id': row['case_id'], 'trial': TrialResult.model_validate(row['trial'])}
            for row in study['trial_rows'] if row['stage'] == stage]


def write_check(store, study, *, suffix='one', decision='HARM', **changes):
    campaign_id, check_id = f'heldout-campaign-{suffix}', f'heldout-check-{suffix}'
    store.put_record('campaigns', campaign_id, {'campaign_id': campaign_id, 'active_policy_version': 'policy-v0'})
    check = {'check_id': check_id, 'campaign_id': campaign_id, 'certified_study_id': study['study_id'],
             'policy_hash': study['selected_candidate_hash'], 'policy_version': study['selected_candidate_version'],
             'status': 'COMPLETED', 'decision': decision, 'predicate': 'faultlab-heldout-no-harm/v2',
             'reason': 'PRIVATE_REASON_SENTINEL', 'assessment': {'case_id': 'PRIVATE_CASE_SENTINEL'},
             'cases': [{'secret_recipe': 'PRIVATE_RECIPE_SENTINEL'}], 'trial_ids': ['PRIVATE_EPISODE_SENTINEL'],
             'partition_dir': '/private/PRIVATE_PATH_SENTINEL', **changes}
    store.put_record('heldout_checks', check_id, check)
    return check


@pytest.mark.parametrize('manifest_id', ['upgrade-v1', 'notification-v1'])
def test_development_qualification_is_distinct_from_unseen_result_and_actual_active_policy(store, manifest_id):
    study = saved_study(store, manifest_id)
    if manifest_id == 'notification-v1':
        study.pop('case_manifest_id')  # Historical notification records predate the manifest selector.
        store.put_record('completion_studies', study['study_id'], study)
    before = store.db.total_changes
    result = policy_status(store, study['campaign_id'])
    assert result['schema_version'] == 'faultlab-policy-status/v1'
    assert result['active_policy'] == {'version': 'policy-v0',
                                       'hash': store.get_record('policies', 'policy-v0')['policy_hash']}
    assert result['studies'][0]['development']['status'] == 'QUALIFIED'
    assert result['studies'][0]['unseen_checks'] == []
    assert store.db.total_changes == before  # Reading cannot create a promotion or move a pointer.
    assert store.get_record('policies', study['selected_candidate_version'])['decision'] == 'PROPOSED'
    assert store.get_record('completion_studies', study['study_id']) == study


@pytest.mark.parametrize('gain', [0, 1])
def test_an_observed_improvement_without_a_two_completion_fresh_gain_is_not_qualified(store, gain):
    study = saved_study(store, gain=gain)
    assert study['validation_assessment']['decision'] == 'OBSERVED_IMPROVEMENT'
    assert policy_status(store, study['campaign_id'])['studies'][0]['development']['status'] == 'NOT_QUALIFIED'


def test_replay_success_is_never_a_new_qualification(store):
    study = saved_study(store)
    study.update(replay_of=study.pop('selected_candidate_version'), replay_policy_hash=study.pop('selected_candidate_hash'))
    study['candidates'] = []
    store.put_record('completion_studies', study['study_id'], study)
    result = policy_status(store, study['campaign_id'])['studies'][0]
    assert result['development']['status'] == 'REPLAY_ONLY'
    assert result['policy_hash'] == study['replay_policy_hash']


@pytest.mark.parametrize('corruption', [
    'running', 'missing_decision', 'missing_validation', 'missing_source', 'wrong_selected_version',
    'duplicate_candidate', 'candidate_content_changed', 'wrong_actor_protocol', 'wrong_evidence_protocol',
    'unknown_manifest', 'manifest_changed', 'missing_trial', 'duplicate_trial', 'wrong_world',
    'wrong_policy', 'wrong_scenario', 'wrong_index', 'wrong_slot', 'untriggered', 'masked_fault',
    'candidate_failed_check', 'missing_verification', 'forged_counts', 'source_not_completed',
    'no_controls', 'missing_policy', 'changed_policy', 'manual_policy', 'changed_baseline',
])
def test_missing_or_inconsistent_evidence_cannot_display_qualification(store, corruption):
    study = saved_study(store)
    row = next(r for r in study['trial_rows'] if r['stage'] == 'validation' and r['case_id'] == 'upgrade-2'
               and r['trial']['arm'] == 'L')
    if corruption == 'running': study['status'] = 'RUNNING'
    elif corruption == 'missing_decision': study.pop('decision')
    elif corruption == 'missing_validation': study['validation_assessment'] = None
    elif corruption == 'missing_source': study['candidates'][0].pop('source_assessment')
    elif corruption == 'wrong_selected_version': study['selected_candidate_version'] = 'another-version'
    elif corruption == 'duplicate_candidate': study['candidates'].append(deepcopy(study['candidates'][0]))
    elif corruption == 'candidate_content_changed': study['candidates'][0]['content']['rules'] = []
    elif corruption == 'wrong_actor_protocol': study['actor_context_protocol'] = 'faultlab-actor-context/v1'
    elif corruption == 'wrong_evidence_protocol': study['evidence_protocol'] = 'unknown'
    elif corruption == 'unknown_manifest': study['case_manifest_id'] = 'unknown'
    elif corruption == 'manifest_changed': study['manifest']['repeats'] = 1
    elif corruption == 'missing_trial': study['trial_rows'].remove(row)
    elif corruption == 'duplicate_trial': study['trial_rows'].append(deepcopy(row))
    elif corruption == 'wrong_world': row['trial']['world_id'] = study['trial_rows'][0]['trial']['world_id']
    elif corruption == 'wrong_policy': row['trial']['policy_hash'] = study['incumbent_hash']
    elif corruption == 'wrong_scenario': row['trial']['scenario_hash'] = 'a' * 64
    elif corruption == 'wrong_index': row['trial']['trial_index'] = 2
    elif corruption == 'wrong_slot': study['slots'][-1]['episode_id'] = 'another-episode'
    elif corruption == 'untriggered': row['trial']['fault_triggered'] = False
    elif corruption == 'masked_fault': row['trial']['fault_scheduled'] = False
    elif corruption == 'candidate_failed_check': row['trial']['failed_checks'] = ['C5']
    elif corruption == 'missing_verification': study['evidence'].pop(row['trial']['episode_id'])
    elif corruption == 'forged_counts': study['validation_assessment']['by_case']['upgrade-2']['L']['completed'] = 2
    elif corruption == 'source_not_completed':
        next(r for r in study['trial_rows'] if r['stage'] == 'validation' and r['case_id'] == 'upgrade-3'
             and r['trial']['arm'] == 'L')['trial']['outcome'] = 'SAFE_UNRESOLVED'
    elif corruption == 'no_controls': study['trial_rows'] = [r for r in study['trial_rows'] if r['stage'] != 'controls']
    elif corruption == 'missing_policy':
        store.db.execute('DELETE FROM records WHERE kind=? AND id=?', ('policies', study['selected_candidate_version']))
    elif corruption in ('changed_policy', 'manual_policy', 'changed_baseline'):
        version = 'policy-v0' if corruption == 'changed_baseline' else study['selected_candidate_version']
        policy = store.get_record('policies', version)
        if corruption == 'manual_policy': policy['author'] = 'manual'
        else: policy['policy_hash'] = 'c' * 64
        store.put_record('policies', version, policy)
    store.put_record('completion_studies', study['study_id'], study)
    assert policy_status(store, study['campaign_id'])['studies'][0]['development']['status'] == 'INCOMPLETE'


def test_checks_join_by_exact_source_study_and_policy_identity_across_campaigns(store):
    study = saved_study(store)
    same_hash_other_study = saved_study(store, suffix='other')
    check = write_check(store, study)
    # Same content in a different proposal is not permission to borrow its held-out result.
    assert policy_status(store, same_hash_other_study['campaign_id'])['studies'][0]['unseen_checks'] == []
    for campaign_id in (study['campaign_id'], check['campaign_id']):
        summary = policy_status(store, campaign_id)
        assert summary['active_policy']['version'] == 'policy-v0'
        assert len(summary['studies']) == 1
        row = summary['studies'][0]
        assert row['source_campaign_id'] == study['campaign_id']
        assert row['development']['status'] == 'QUALIFIED'
        assert row['unseen_checks'] == [{
            'check_id': check['check_id'], 'campaign_id': check['campaign_id'], 'source_study_id': study['study_id'],
            'policy_hash': study['selected_candidate_hash'], 'status': 'COMPLETED', 'decision': 'HARM',
            'predicate': 'faultlab-heldout-no-harm/v2'}]
        assert 'PRIVATE_' not in json.dumps(summary)


@pytest.mark.parametrize('change', [
    {'policy_hash': 'f' * 64}, {'policy_version': 'wrong-version'}, {'certified_study_id': 'missing-study'},
])
def test_mismatched_heldout_references_do_not_attach_to_an_unrelated_study(store, change):
    study = saved_study(store)
    check = write_check(store, study, **change)
    assert policy_status(store, study['campaign_id'])['studies'][0]['unseen_checks'] == []
    assert policy_status(store, check['campaign_id'])['studies'] == []


@pytest.mark.parametrize('status,decision,expected', [
    ('COMPLETED', 'NO_HARM', ('COMPLETED', 'NO_HARM')),
    ('INCOMPLETE', 'INCOMPLETE', ('INCOMPLETE', 'INCOMPLETE')),
    ('RUNNING', 'PENDING', ('RUNNING', 'PENDING')),
    ('RUNNING', 'NO_HARM', ('INCOMPLETE', 'INCOMPLETE')),
    ('COMPLETED', 'PENDING', ('INCOMPLETE', 'INCOMPLETE')),
    ('UNKNOWN', 'UNKNOWN', ('INCOMPLETE', 'INCOMPLETE')),
])
def test_pending_and_incomplete_unseen_checks_are_not_presented_as_a_final_pass(store, status, decision, expected):
    study = saved_study(store)
    write_check(store, study, status=status, decision=decision)
    check = policy_status(store, study['campaign_id'])['studies'][0]['unseen_checks'][0]
    assert (check['status'], check['decision']) == expected


def test_active_policy_uses_only_the_campaign_pointer_not_qualification_or_heldout_verdict(store):
    study = saved_study(store)
    write_check(store, study, decision='NO_HARM')
    assert policy_status(store, study['campaign_id'])['active_policy']['version'] == 'policy-v0'
    campaign = store.get_record('campaigns', study['campaign_id'])
    campaign['active_policy_version'] = study['selected_candidate_version']
    store.put_record('campaigns', study['campaign_id'], campaign)
    assert policy_status(store, study['campaign_id'])['active_policy'] == {
        'version': study['selected_candidate_version'], 'hash': study['selected_candidate_hash']}
    campaign['active_policy_version'] = 'missing-policy'
    store.put_record('campaigns', study['campaign_id'], campaign)
    assert policy_status(store, study['campaign_id'])['active_policy'] == {'version': 'missing-policy', 'hash': None}


def test_empty_campaign_and_unknown_campaign_are_distinct(store):
    store.put_record('campaigns', 'empty', {'campaign_id': 'empty'})
    assert policy_status(store, 'empty') == {'schema_version': 'faultlab-policy-status/v1', 'campaign_id': 'empty',
                                           'active_policy': {'version': None, 'hash': None}, 'studies': []}
    with pytest.raises(StoreConflict, match='Unknown campaign'):
        policy_status(store, 'absent')

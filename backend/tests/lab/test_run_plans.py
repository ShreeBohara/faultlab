"""Immutable public-case plans and provider-free setup, separate from old protocols."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import hashlib
import json

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.contracts.models import CampaignRequest, content_hash, canonical_json
from app.lab.coordinator import LabCoordinator
from app.lab.operator_actions import register_agent
from app.lab.run_plans import (RunPlanRequest, TASK, TASK_TEXT, build_run_options,
    prepare_run_plan, read_run_plan, validate_run_plan)
from app.lab.storage import ReadOnlyLabStore, ReadOnlyStore, StoreConflict


@pytest.fixture
def owner(tmp_path):
    coordinator = LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path / 'lab'),
        wandb_model='deepseek-ai/DeepSeek-V3.1', wandb_explorer_model='deepseek-ai/DeepSeek-V4-Pro-0813'))
    try: yield coordinator
    finally: asyncio.run(coordinator.close())


def records(store):
    return [tuple(row) for row in store.db.execute('SELECT * FROM records ORDER BY rowid')]


def form(options, **overrides):
    return RunPlanRequest(**{'expected_store_identity': options['data_store']['identity'],
        'expected_setup_hash': options['setup_hash'], 'task_definition_id': TASK,
        'mode': 'baseline', 'config_profile_id': 'offline-v1', 'task_text': TASK_TEXT,
        'order_id': 'order-planned', 'development_case_id': 'dev-1', **overrides})


def make_plan(owner, **overrides):
    options = build_run_options(owner.settings, owner.store)
    prepared = prepare_run_plan(owner.store, owner.settings, form(options, **overrides))
    return owner.create(prepared.campaign_request, run_plan=prepared), prepared


@pytest.mark.parametrize('changes', [
    {'task_definition_id': 'arbitrary-task'}, {'development_case_id': 'promotion-1'},
    {'development_case_id': '../promotion'}, {'development_case_id': None},
    {'mode': 'learn'}, {'config_profile_id': 'live-v1'},
    {'agent_registration_id': 'external-on-offline'}, {'fixture_id': 'history-v1'},
    {'fault_spec': {}}, {'manifest_dir': '/private'},
])
def test_strict_request_rejects_unsupported_selections(changes):
    options = {'data_store': {'identity': 'a' * 64}, 'setup_hash': 'b' * 64}
    with pytest.raises(ValidationError): form(options, **changes)


def test_options_without_store_do_not_initialize_database_or_provider(tmp_path, monkeypatch):
    settings = Settings(faultlab_artifact_dir=str(tmp_path / 'missing'))
    monkeypatch.setattr('app.lab.coordinator.LabCoordinator', lambda *_: pytest.fail('Options created coordinator'))
    monkeypatch.setattr('app.lab.storage.LabStore', lambda *_: pytest.fail('Options opened SQLite writer'))
    monkeypatch.setattr('app.providers.runtime.RuntimeProvider', lambda *_: pytest.fail('Options constructed provider'))
    options = build_run_options(settings)
    assert not settings.artifact_path.exists()
    assert options['provider_calls'] == 0
    assert [case['case_id'] for case in options['development']['cases']] == [f'dev-{i}' for i in range(1, 7)]
    assert all(row['reason_code'] == 'MODEL_REQUIRED' for row in options['agents'])
    assert options['offline']['registration_required'] is False


def test_read_only_options_snapshot_uses_settings_archive_flag_and_never_registers(owner):
    before = records(owner.store)
    snapshot = ReadOnlyLabStore(owner.store.path)
    try:
        options = build_run_options(owner.settings, snapshot)
        archived = build_run_options(replace(owner.settings, faultlab_read_only=True), snapshot)
    finally: snapshot.close()
    assert options['data_store']['read_only'] is False
    assert archived['data_store']['read_only'] is True
    assert options['setup_hash'] == archived['setup_hash']
    assert records(owner.store) == before


def test_setup_hash_is_stable_across_registration_and_accepted_pointer(owner):
    before = build_run_options(owner.settings, owner.store)
    reg = register_agent(owner.store, owner.settings, 'reference')
    after = build_run_options(owner.settings, owner.store)
    assert before['setup_hash'] == after['setup_hash']
    row = next(row for row in after['agents'] if row['agent'] == 'reference')
    assert row['registered'] and row['registration_id'] == reg.registration_id
    assert row['source_conformance'] == 'VERIFIED' and row['behavior_verified'] is False
    accepted = owner.policies.baseline().model_copy(update={'version': 'policy-accepted', 'decision': 'ACCEPTED'})
    owner.policies.save(accepted)
    owner.store.compare_and_set_pointer('accepted-policy:' + reg.configuration_hash, None, accepted.version)
    current = build_run_options(owner.settings, owner.store)
    assert current['setup_hash'] == before['setup_hash']
    assert next(row for row in current['agents'] if row['agent'] == 'reference')['compare_available']


def test_setup_hash_changes_when_model_or_caps_change(owner):
    original = build_run_options(owner.settings)['setup_hash']
    assert build_run_options(replace(owner.settings, faultlab_model_call_cap=5000))['setup_hash'] != original
    assert build_run_options(replace(owner.settings, wandb_model='different-model'))['setup_hash'] != original


def test_options_never_disclose_protected_cases(owner, monkeypatch):
    from app.referee import manifests
    original = manifests.load_manifest
    def marked(name):
        value = deepcopy(original(name))
        if name == 'promotion':
            for case in value['cases']:
                case['case_id'] = 'PROTECTED_CASE_CANARY'
                case['fault_spec']['seed'] = 87654321
        return value
    monkeypatch.setattr(manifests, 'load_manifest', marked)
    options = build_run_options(owner.settings, owner.store)
    encoded = json.dumps(options)
    assert 'PROTECTED_CASE_CANARY' not in encoded and '87654321' not in encoded
    assert set(options['compare']) == {'partition', 'manifest_hash', 'case_count', 'trials_per_case'}
    assert options['episode_budget']['actor_calls'] == 8 and options['episode_budget']['wall_seconds'] == 90


@pytest.mark.parametrize('case_id,fixture,version', [(f'dev-{i}', 'history-v1' if i == 4 else 'standard-v1', 4 if i == 4 else 1) for i in range(1, 7)])
def test_each_public_case_is_snapshotted_and_immutably_bound(owner, case_id, fixture, version):
    campaign, prepared = make_plan(owner, development_case_id=case_id)
    envelope = read_run_plan(owner.store, campaign.campaign_id)
    plan = envelope['plan']
    assert envelope['status'] == 'PLANNED'
    assert plan['selection']['fixture_id'] == fixture and plan['selection']['expected_version'] == version
    assert plan['selection']['scenario_hash'] == content_hash(plan['selection']['fault_spec'])
    assert plan['configuration_hash'] == campaign.configuration_hash
    assert plan['initial_policy_version'] == 'policy-v0'
    assert plan['agent_registration_id'] == prepared.registration.registration_id
    assert validate_run_plan(owner.store, owner.settings, campaign) == plan
    assert owner.store.list_records('episodes') == []
    with pytest.raises(StoreConflict): owner.store.put_record('campaign_plans', campaign.campaign_id, {**plan, 'order_id': 'changed'})


@pytest.mark.parametrize('mismatch', ['store', 'setup', 'archive'])
def test_preparation_refuses_changed_setup_without_partial_writes(owner, mismatch):
    options = build_run_options(owner.settings, owner.store)
    changes = {'expected_store_identity': '0' * 64} if mismatch == 'store' else {'expected_setup_hash': '0' * 64} if mismatch == 'setup' else {}
    before = records(owner.store)
    settings = replace(owner.settings, faultlab_read_only=True) if mismatch == 'archive' else owner.settings
    with pytest.raises((StoreConflict, ReadOnlyStore)):
        prepare_run_plan(owner.store, settings, form(options, **changes))
    assert records(owner.store) == before


def test_live_requires_exact_current_registration_and_no_implicit_save(owner):
    options = build_run_options(owner.settings, owner.store)
    proposed = next(row for row in options['agents'] if row['agent'] == 'reference')['proposed_registration_id']
    before = records(owner.store)
    with pytest.raises(ValueError):
        prepare_run_plan(owner.store, owner.settings, form(options, config_profile_id='live-v1', agent_registration_id=proposed))
    assert records(owner.store) == before
    register_agent(owner.store, owner.settings, 'reference')
    prepared = prepare_run_plan(owner.store, owner.settings, form(options, config_profile_id='live-v1', agent_registration_id=proposed))
    campaign = owner.create(prepared.campaign_request, run_plan=prepared)
    assert read_run_plan(owner.store, campaign)['plan']['agent_registration_id'] == proposed
    changed = replace(owner.settings, faultlab_model_call_cap=5000)
    stale_options = build_run_options(changed, owner.store)
    with pytest.raises(StoreConflict):
        prepare_run_plan(owner.store, changed, form(stale_options, config_profile_id='live-v1', agent_registration_id=proposed))


def test_native_preview_and_live_plan_use_the_exact_current_native_configuration(owner):
    options = build_run_options(owner.settings, owner.store)
    native = next(row for row in options['agents'] if row['agent'] == 'smolagents')
    if native['status'] == 'UNAVAILABLE':
        pytest.skip('Reviewed native source unavailable in this environment')
    reg = register_agent(owner.store, owner.settings, 'smolagents')
    assert native['proposed_registration_id'] == reg.registration_id
    campaign, _ = make_plan(owner, config_profile_id='live-v1', agent_registration_id=reg.registration_id)
    plan = validate_run_plan(owner.store, owner.settings, campaign)
    assert plan['agent'] == 'smolagents' and plan['configuration_hash'] == reg.configuration_hash
    frozen = owner.store.get_record('configurations', reg.configuration_hash)
    assert not {'actor_response_protocol', 'actor_context_protocols', 'actor_context_protocol'} & set(frozen)
    assert any('context' in limitation and 'unavailable' in limitation for limitation in native['limitations'])


def test_learn_plan_has_public_search_space_compare_has_aggregate_only(owner):
    reg = register_agent(owner.store, owner.settings, 'reference')
    campaign, _ = make_plan(owner, mode='learn', config_profile_id='live-v1', agent_registration_id=reg.registration_id, development_case_id=None)
    plan = read_run_plan(owner.store, campaign)['plan']
    assert set(plan['selection']) == {'kind', 'manifest_hash', 'search_space'}
    options = build_run_options(owner.settings, owner.store)
    with pytest.raises(StoreConflict, match='accepted policy'):
        prepare_run_plan(owner.store, owner.settings, form(options, mode='compare', config_profile_id='live-v1', agent_registration_id=reg.registration_id, development_case_id=None))
    accepted = owner.policies.baseline().model_copy(update={'version': 'policy-accepted', 'decision': 'ACCEPTED'})
    owner.policies.save(accepted)
    owner.store.compare_and_set_pointer('accepted-policy:' + reg.configuration_hash, None, accepted.version)
    compared, _ = make_plan(owner, mode='compare', config_profile_id='live-v1', agent_registration_id=reg.registration_id, development_case_id=None)
    selection = read_run_plan(owner.store, compared)['plan']['selection']
    assert set(selection) == {'kind', 'partition', 'manifest_hash', 'case_count', 'trials_per_case'}
    assert 'fault_spec' not in json.dumps(selection)


@pytest.mark.parametrize('damage', ['missing_plan', 'missing_marker', 'recipe', 'task', 'registration'])
def test_marked_plan_corruption_never_falls_back_to_healthy(owner, damage):
    campaign, _ = make_plan(owner, development_case_id='dev-4')
    if damage == 'missing_plan':
        owner.store.db.execute("DELETE FROM records WHERE kind='campaign_plans' AND id=?", (campaign.campaign_id,))
    elif damage == 'missing_marker':
        owner.store.db.execute("DELETE FROM records WHERE kind='campaign_provenance' AND id=?", (campaign.campaign_id,))
    elif damage == 'recipe':
        plan = owner.store.get_record('campaign_plans', campaign.campaign_id)
        plan['selection']['fault_spec']['seed'] += 1
        owner.store.db.execute("UPDATE records SET payload=? WHERE kind='campaign_plans' AND id=?", (canonical_json(plan), campaign.campaign_id))
    elif damage == 'task':
        campaign.task_text = 'Altered saved task'; owner.save(campaign)
    else:
        owner.store.db.execute("DELETE FROM records WHERE kind='campaign_registrations' AND id=?", (campaign.campaign_id,))
    with pytest.raises(StoreConflict, match='missing, corrupt or inconsistent'):
        read_run_plan(owner.store, campaign.campaign_id)
    assert owner.store.list_records('episodes') == []


def test_saved_read_survives_current_runtime_changes_but_start_does_not(owner, monkeypatch):
    campaign, _ = make_plan(owner)
    expected = read_run_plan(owner.store, campaign)
    def changed(*_): raise ValueError('Different installed runtime')
    monkeypatch.setattr('app.integrations.registry.current_registration_configuration', changed)
    assert read_run_plan(owner.store, campaign) == expected
    with pytest.raises(ValueError): validate_run_plan(owner.store, owner.settings, campaign)


def test_closed_archive_plan_read_preserves_hash_and_mtime(owner):
    campaign, _ = make_plan(owner)
    from pathlib import Path
    path = Path(owner.store.path)
    expected = read_run_plan(owner.store, campaign)
    owner.store.close()
    before = hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns
    reader = ReadOnlyLabStore(path)
    try: assert read_run_plan(reader, campaign.campaign_id) == expected
    finally: reader.close()
    assert before == (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)


def test_saved_baseline_uses_snapshot_not_changed_catalog(owner, monkeypatch):
    campaign, _ = make_plan(owner, development_case_id='dev-4')
    monkeypatch.setattr('app.lab.run_plans._manifests', lambda: pytest.fail('Baseline reread mutable manifest'))
    assert validate_run_plan(owner.store, owner.settings, campaign)['selection']['fixture_id'] == 'history-v1'


def test_legacy_read_leaves_history_untouched(owner):
    campaign = owner.create(CampaignRequest(task_text='Legacy text', order_id='legacy-order', mode='baseline'))
    before = records(owner.store)
    assert read_run_plan(owner.store, campaign) == {'campaign_id': campaign.campaign_id, 'status': 'LEGACY', 'plan': None}
    assert validate_run_plan(owner.store, owner.settings, campaign) is None
    assert records(owner.store) == before


def test_later_accepted_learning_policy_is_allowed_with_coherent_pointer(owner):
    reg = register_agent(owner.store, owner.settings, 'reference')
    campaign, _ = make_plan(owner, mode='learn', config_profile_id='live-v1', agent_registration_id=reg.registration_id, development_case_id=None)
    accepted = owner.policies.baseline().model_copy(update={'version': 'policy-learned', 'decision': 'ACCEPTED'})
    owner.policies.save(accepted)
    owner.store.compare_and_set_pointer('active-policy:' + campaign.campaign_id, 'policy-v0', accepted.version)
    campaign.active_policy_version = accepted.version; campaign.state = 'COMPLETED'; owner.save(campaign)
    assert read_run_plan(owner.store, campaign)['plan']['initial_policy_version'] == 'policy-v0'
    assert validate_run_plan(owner.store, owner.settings, campaign)['initial_policy_version'] == 'policy-v0'

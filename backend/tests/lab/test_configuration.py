"""Experiment identities cover code changes without tracking incidental Git state."""
import subprocess

import pytest

from app.config import Settings
from app.contracts.models import CampaignBudget
from app.integrations.registry import _configuration, _installed_semantics
from app.lab import configuration


@pytest.mark.parametrize('relative,algorithm_changes', [
    ('lab/learning.py', True), ('lab/diagnosis.py', True),
    ('lab/challenge.py', True), ('lab/evaluation.py', True),
    ('lab/promotion.py', True), ('lab/coordinator.py', True),
    ('referee/freeze.py', True), ('providers/runtime.py', False),
    ('telemetry/tracing.py', False), ('config.py', False),
])
def test_runtime_identity_covers_experiment_execution(tmp_path, monkeypatch, relative, algorithm_changes):
    monkeypatch.setattr(configuration, 'ROOT', tmp_path)
    source = tmp_path / 'backend/app' / relative
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('VERSION = 1\n')
    before = configuration.runtime_fingerprints()
    source.write_text('VERSION = 2\n')
    after = configuration.runtime_fingerprints()
    assert before['runtime_hash'] != after['runtime_hash']
    assert (before['algorithm_hash'] != after['algorithm_hash']) == algorithm_changes


def test_git_provenance_is_safe_and_does_not_change_configuration(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.run(['git', '-C', str(tmp_path), *args], check=True, capture_output=True, text=True).stdout.strip()
    git('init', '-q')
    source = tmp_path / 'backend/app/lab/learning.py'
    source.parent.mkdir(parents=True)
    source.write_text('VERSION = 1\n')
    git('add', 'backend/app/lab/learning.py')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test', 'commit', '-qm', 'Fixture')
    monkeypatch.setattr(configuration, 'ROOT', tmp_path)
    settings, caps = Settings(), CampaignBudget()
    before = configuration.frozen_configuration(settings, caps, 'offline-v1')
    assert configuration.source_provenance() == {'git_revision': git('rev-parse', 'HEAD'), 'runtime_dirty': False}
    (tmp_path / 'status.md').write_text('Unrelated documentation\n')
    (tmp_path / '.env').write_text('PRIVATE_TEST_SENTINEL=not-a-real-key\n')
    assert configuration.source_provenance()['runtime_dirty'] is False
    assert configuration.frozen_configuration(settings, caps, 'offline-v1') == before
    git('add', 'status.md')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test', 'commit', '-qm', 'Docs only')
    assert configuration.frozen_configuration(settings, caps, 'offline-v1') == before
    source.write_text('VERSION = 2\n')
    assert configuration.source_provenance()['runtime_dirty'] is True
    assert configuration.frozen_configuration(settings, caps, 'offline-v1') != before
    assert set(configuration.source_provenance()) == {'git_revision', 'runtime_dirty'}


def test_source_provenance_marks_unknown_without_git(tmp_path, monkeypatch):
    monkeypatch.setattr(configuration, 'ROOT', tmp_path)
    assert configuration.source_provenance() == {'git_revision': None, 'runtime_dirty': None}


def test_registry_accepts_legacy_identity_and_rejects_changed_new_runtime():
    current = configuration.frozen_configuration(Settings(), CampaignBudget(), 'offline-v1')
    assert _configuration(current) == current
    _installed_semantics(current)
    legacy = {key: value for key, value in current.items() if key not in {'algorithm_hash', 'runtime_hash', 'trace_contract_version'}}
    assert _configuration(legacy) == legacy
    _installed_semantics(legacy)
    with pytest.raises(ValueError, match='runtime'):
        _installed_semantics({**current, 'runtime_hash': '0' * 64})
    with pytest.raises(ValueError, match='identity'):
        _configuration({**legacy, 'runtime_hash': current['runtime_hash']})


@pytest.mark.parametrize('mode', ['legacy', 'explicit', 'both'])
def test_frozen_role_rates_match_admission_and_selected_model(mode):
    options = dict(wandb_model='actor-model', faultlab_pricing_model='actor-model',
        faultlab_pricing_verified=True, faultlab_input_dollars_per_million=1,
        faultlab_output_dollars_per_million=2)
    if mode in ('legacy', 'both'):
        options.update(faultlab_lab_model='lab-model', faultlab_lab_pricing_model='lab-model',
            faultlab_lab_input_dollars_per_million=3, faultlab_lab_output_dollars_per_million=4)
    if mode in ('explicit', 'both'):
        options.update(wandb_explorer_model='reasoning-model', wandb_mechanic_model='actor-model',
            faultlab_reasoning_pricing_model='reasoning-model', faultlab_reasoning_pricing_verified=True,
            faultlab_reasoning_input_dollars_per_million=5, faultlab_reasoning_output_dollars_per_million=6)
    settings = Settings(**options)
    caps = CampaignBudget()
    frozen = configuration.frozen_configuration(settings, caps, 'live-v1')
    for role in ('actor', 'explorer', 'mechanic'):
        pricing = frozen['pricing'][role]
        assert pricing['model'] == settings.model_for_role(role)
        assert pricing['input_dollars_per_million'] >= 0
        expected = (caps.input_tokens_per_call * pricing['input_dollars_per_million']
            + caps.output_tokens_per_call * pricing['output_dollars_per_million']) / 1_000_000
        assert pricing['per_call_dollar_upper_bound'] == pytest.approx(expected)
        assert settings.model_call_dollar_bounds[role] == pytest.approx(expected)
    assert frozen['lab_pricing'] == {key:value for key,value in frozen['pricing']['explorer'].items()
        if key != 'per_call_dollar_upper_bound'}
    assert frozen['lab_model'] == frozen['lab_pricing']['model']
    assert frozen['pricing']['explorer']['input_dollars_per_million'] == (3 if mode == 'legacy' else 5)


def test_reference_registration_binds_exact_report_protocol(tmp_path):
    from copy import deepcopy
    from app.contracts.models import ReportAction,content_hash
    from app.integrations.registry import AgentRegistry
    from app.lab.storage import LabStore
    from app.providers.runtime import actor_response_protocol,response_format_for
    frozen=configuration.frozen_configuration(Settings(),CampaignBudget(),'offline-v1')
    protocol=frozen['actor_response_protocol']
    assert protocol==actor_response_protocol()
    assert protocol['scope']=='faultlab_reference_actor'
    assert protocol['schema_hash']==content_hash(ReportAction.model_json_schema())
    assert protocol['response_format']==response_format_for(response_contract='actor_final_report')
    store=LabStore(tmp_path/'lab.db');registry=AgentRegistry(store)
    assert registry.register_reference(frozen).configuration_hash==content_hash(frozen)
    changed=deepcopy(frozen);changed['actor_response_protocol']['response_format']['json_schema']['strict']=False
    with pytest.raises(ValueError,match='response protocol'):
        registry.register_reference(changed)
    missing={key:value for key,value in frozen.items() if key!='actor_response_protocol'}
    with pytest.raises(ValueError,match='explicitly frozen'):
        registry.register_reference(missing)
    # Historical shape remains inspectable, without granting it a new registration.
    assert _configuration(missing)==missing
    store.close()


def test_reference_registration_binds_the_exact_actor_context_protocol_registry(tmp_path):
    from copy import deepcopy
    from app.agents.progress import (ACTOR_CONTEXT_PROTOCOL_V1, ACTOR_CONTEXT_PROTOCOL_V2,
                                     ACTOR_CONTEXT_PROTOCOL_V3,ACTOR_CONTEXT_PROTOCOL_V4, actor_context_protocols)
    from app.contracts.models import content_hash
    from app.integrations.registry import AgentRegistry
    from app.lab.storage import LabStore
    frozen=configuration.frozen_configuration(Settings(),CampaignBudget(),'offline-v1')
    registry_value=frozen['actor_context_protocols']
    assert registry_value==actor_context_protocols()
    # Both compared protocols are frozen once, so one campaign serves both arms.
    assert set(registry_value)=={ACTOR_CONTEXT_PROTOCOL_V1,ACTOR_CONTEXT_PROTOCOL_V2,ACTOR_CONTEXT_PROTOCOL_V3,ACTOR_CONTEXT_PROTOCOL_V4}
    # Only the keys that apply are declared, so adding a protocol later cannot
    # change an earlier one's frozen identity.
    assert 'attempted_writes_format' not in registry_value[ACTOR_CONTEXT_PROTOCOL_V1]
    assert registry_value[ACTOR_CONTEXT_PROTOCOL_V2]['attempted_writes_format']
    live=configuration.frozen_configuration(Settings(),CampaignBudget(),'offline-v1')
    assert live['actor_context_protocols']==registry_value
    store=LabStore(tmp_path/'lab.db');registry=AgentRegistry(store)
    assert registry.register_reference(frozen).configuration_hash==content_hash(frozen)
    changed=deepcopy(frozen)
    changed['actor_context_protocols'][ACTOR_CONTEXT_PROTOCOL_V2]['pre_acceptance_error_codes']=[]
    with pytest.raises(ValueError,match='context protocols'):
        registry.register_reference(changed)
    missing={key:value for key,value in frozen.items() if key!='actor_context_protocols'}
    with pytest.raises(ValueError,match='explicitly frozen'):
        registry.register_reference(missing)
    assert _configuration(missing)==missing
    store.close()

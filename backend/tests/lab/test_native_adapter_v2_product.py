"""Native adapter v2 as a declared, separate product agent: identity, plans, runner, history, bundles, diagnosis.

Offline and $0: real smolagents, real in-process simulator, real runner and ledger; only the model transport is
a declared scripted replacement (NativeReferenceInputs, which answers from the public observations it is shown).
"""
import hashlib
from pathlib import Path

import httpx
import pytest

from app.contracts.models import Counterexample, FaultSpec, content_hash
from app.integrations import registry as registry_module
from app.integrations.external_agent import SmolagentsActor
from app.integrations.external_agent_v2 import SmolagentsActorV2, adapter_protocol
from app.integrations.registry import (NATIVE_V1, NATIVE_V2, AgentRegistry, adapter_hash, native_prompt_hash,
                                       reviewed_actor_matches)
from app.lab import bundle_imports as imports
from app.lab.agent_history import target_identity
from app.lab.budgets import CampaignLedger
from app.lab.dashboard import store_descriptor
from app.lab.diagnosis import runtime_contract
from app.lab.operator_actions import RegistrationRequest, register_agent
from app.lab.regressions import RegressionCompiler
from app.lab.run_plans import RunPlanRequest, build_run_options, prepare_run_plan, read_run_plan, validate_run_plan
from app.lab.runner import reject_native_reference_study
from app.lab.storage import StoreConflict
from app.main import create_app

from test_planned_agent_execution import planned_campaign, runtime
from test_native_transport_retry import Lossy, checker, load, rewrite_report_tick
from test_agent_history import Seeder, case, owner, seed_screen  # noqa: F401  (owner is a fixture)

ROOT = Path(__file__).resolve().parents[3]
V2_LABEL = 'smolagents ToolCallingAgent - adapter v2 (short evidence labels, strict final report turn)'
# external_agent.py (native adapter v1) as it was before adapter v2 existed: v2 imports it and never changes it.
V1_MODULE_SHA256 = '6c0909bfff3753b470570baef5c96b39904a922ea7a8f9d548fb30f5be9380f7'


@pytest.fixture
def anyio_backend(): return 'asyncio'


def planned_v2(c, *, mode='baseline', case_id='dev-1'):
    """A saved plan for native adapter v2, registered exactly as the API and CLI register it."""
    registration = register_agent(c.store, c.settings, 'smolagents-v2')
    options = build_run_options(c.settings, c.store)
    request = RunPlanRequest(expected_store_identity=options['data_store']['identity'],
        expected_setup_hash=options['setup_hash'], task_definition_id=options['task']['task_definition_id'],
        agent_registration_id=registration.registration_id, mode=mode, config_profile_id='live-v1',
        task_text=options['task']['task_text_default'], order_id='order-selected',
        development_case_id=case_id if mode == 'baseline' else None)
    prepared = prepare_run_plan(c.store, c.settings, request)
    return c.create(prepared.campaign_request, run_plan=prepared), registration


def events(c, episode_id, kind):
    return [e for e in c.store.events(episode_id)['events'] if e['type'] == kind]


# ----------------------------------------------------------------------------- identity and registration

def test_v1_module_is_byte_identical_to_before_v2():
    assert hashlib.sha256((ROOT / 'backend/app/integrations/external_agent.py').read_bytes()).hexdigest() == V1_MODULE_SHA256


def test_v2_registration_is_a_separate_external_identity(owner):
    v1 = register_agent(owner.store, owner.settings, 'smolagents')
    v2 = register_agent(owner.store, owner.settings, 'smolagents-v2')
    assert (v1.adapter_entrypoint_id, v2.adapter_entrypoint_id) == (NATIVE_V1, NATIVE_V2)
    assert v2.registration_id.startswith('smolagents-1.26.0-adapter-v2-') and not v1.registration_id.startswith('smolagents-1.26.0-adapter-v2-')
    assert v2.name == 'Hugging Face ' + V2_LABEL and v1.name == 'Hugging Face smolagents ToolCallingAgent'
    assert v2.provenance_class == v1.provenance_class == 'external' and v2.source_hash == v1.source_hash
    for field in ('adapter_hash', 'prompt_hash', 'configuration_hash', 'registration_id'):
        assert getattr(v1, field) != getattr(v2, field), field
    for field in ('contract_hash', 'capability_hash', 'oracle_hash', 'model', 'dependency_lock_hash'):
        assert getattr(v1, field) == getattr(v2, field), field
    assert v1.adapter_hash == adapter_hash() == adapter_hash(NATIVE_V1) and v2.adapter_hash == adapter_hash(NATIVE_V2)
    assert v1.prompt_hash == native_prompt_hash() and v2.prompt_hash == native_prompt_hash(NATIVE_V2)
    assert len(v2.limitations) == len(v1.limitations) + 3
    registry = AgentRegistry(owner.store)
    for registration in (v1, v2):
        configuration = owner.store.get_record('configurations', registration.configuration_hash)
        assert registry.verify(registration.registration_id, configuration) == registration
    # Each registration yields only its own adapter, and an actor of the other adapter is refused.
    actor_v1, actor_v2 = registry.reviewed_actor(v1.registration_id), registry.reviewed_actor(v2.registration_id)
    assert type(actor_v1) is SmolagentsActor and type(actor_v2) is SmolagentsActorV2
    assert reviewed_actor_matches(actor_v2, v2) and reviewed_actor_matches(actor_v1, v1)
    assert not reviewed_actor_matches(actor_v1, v2) and not reviewed_actor_matches(actor_v2, v1)
    # A registration whose entry point is swapped no longer verifies.
    configuration = owner.store.get_record('configurations', v2.configuration_hash)
    swapped = v2.model_copy(update={'adapter_entrypoint_id': NATIVE_V1})
    owner.store.db.execute("DELETE FROM records WHERE kind='agent_registrations' AND id=?", (v2.registration_id,))
    owner.store.put_record('agent_registrations', v2.registration_id, swapped)
    with pytest.raises(ValueError):
        registry.verify(v2.registration_id, configuration)


def test_adapter_hashes_cover_their_own_modules(monkeypatch):
    v1, v2 = adapter_hash(NATIVE_V1), adapter_hash(NATIVE_V2)
    original = registry_module.digest
    for name, moves_v1 in (('external_agent_v2.py', False), ('progress.py', False), ('external_agent.py', True), ('registry.py', True)):
        monkeypatch.setattr(registry_module, 'digest', lambda path, name=name: '0' * 64 if Path(path).name == name else original(path))
        assert adapter_hash(NATIVE_V2) != v2, name
        assert (adapter_hash(NATIVE_V1) != v1) is moves_v1, name
        monkeypatch.setattr(registry_module, 'digest', original)
    with pytest.raises(ValueError, match='Unreviewed adapter entrypoint'):
        adapter_hash('orders-prototype-v1')


def test_v2_prompt_hash_covers_the_template_contract_transport_and_protocols():
    from app.integrations.external_agent import TASK_CONTRACT, TRANSPORT_CONTRACT
    from app.integrations.registry import NATIVE_FILES
    expected = content_hash({'native_template': NATIVE_FILES['prompts/toolcalling_agent.yaml'], 'task_contract': TASK_CONTRACT,
                             'transport': TRANSPORT_CONTRACT, 'adapter_protocol': adapter_protocol()})
    assert native_prompt_hash(NATIVE_V2) == expected != native_prompt_hash(NATIVE_V1)
    protocol = adapter_protocol()
    assert protocol['evidence_labels']['evidence_label_prefix'] == 'obs-'
    assert protocol['final_report_turn']['response_contract'] == 'native_final_answer'
    assert protocol['steps']['max_steps'] == 8


def test_registration_request_and_run_options_offer_v2_explicitly_with_v1_unchanged(owner):
    assert RegistrationRequest.model_validate({'expected_store_identity': 'a' * 64, 'agent': 'smolagents-v2'}).agent == 'smolagents-v2'
    # The CLI choice is exercised in tests/integration/test_native_adapter_v2_api.py.
    options = build_run_options(owner.settings, owner.store)
    rows = {row['agent']: row for row in options['agents']}
    assert list(rows) == ['reference', 'smolagents', 'smolagents-v2']
    assert rows['smolagents']['label'] == 'smolagents ToolCallingAgent 1.26.0'
    assert rows['smolagents-v2']['label'] == V2_LABEL and rows['smolagents-v2']['status'] == 'READY'
    assert rows['smolagents-v2']['configuration_hash'] != rows['smolagents']['configuration_hash']
    assert options['provider_calls'] == 0
    protocols = {row['protocol_id']: row['supported_agents'] for row in options['learn']['discovery_protocols']}
    assert protocols['faultlab-discovery/v1'] == protocols['faultlab-discovery/v3-history'] == ['reference', 'smolagents', 'smolagents-v2']
    assert protocols['faultlab-discovery/v2-reachability'] == ['reference']


# ----------------------------------------------------------------------------- plans and planned execution

@pytest.mark.anyio
async def test_v2_plan_runs_through_the_runner_with_labels_and_decoded_report(tmp_path):
    c = await runtime(tmp_path)
    try:
        campaign, registration = planned_v2(c)
        plan = read_run_plan(c.store, campaign)['plan']
        assert plan['agent'] == 'smolagents-v2' and plan['agent_registration_id'] == registration.registration_id
        assert validate_run_plan(c.store, c.settings, campaign)['plan_hash'] == plan['plan_hash']
        trial = await c.runner.run(campaign, FaultSpec(seed=0, primitives=[]), c.policies.baseline())
        assert trial.lifecycle == 'COMPLETED' and trial.outcome == 'COMPLETED' and trial.usage.actor_calls == 4
        execution = c.store.get_record('episode_executions', trial.episode_id)
        assert execution['adapter_entrypoint_id'] == NATIVE_V2 and execution['registration_id'] == registration.registration_id
        episode = c.store.get_record('episodes', trial.episode_id)
        observations = [e['payload']['observation']['evidence_id'] for e in events(c, trial.episode_id, 'observation_delivered')]
        assert episode['report']['evidence_ids'] == observations and len(observations) == 3
        submitted, = events(c, trial.episode_id, 'report_submitted')
        assert submitted['payload']['cited_evidence_tokens'] == ['obs-1', 'obs-2', 'obs-3']
        assert submitted['payload']['decoded_evidence_ids'] == observations
        assert submitted['tick'] == episode['verdict']['decision_tick']
        # Native rules apply to v2 too: no reference-context override, no reference research study.
        with pytest.raises((ValueError, StoreConflict)):
            await c.runner.run(campaign, FaultSpec(seed=0, primitives=[]), c.policies.baseline(),
                               actor_context_protocol='faultlab-actor-context/v1')
        with pytest.raises(ValueError, match='reference Actor protocols'):
            reject_native_reference_study(c.store, campaign)
        # An in-process override must be the v2 adapter itself.
        with pytest.raises(StoreConflict, match='Actor override'):
            await c.runner.run(campaign, FaultSpec(seed=0, primitives=[]), c.policies.baseline(),
                               actor=SmolagentsActor(model_id=registration.model))
    finally:
        await c.close()


@pytest.mark.anyio
async def test_v1_plans_stay_v1_and_a_plan_cannot_name_the_other_adapter(tmp_path):
    c = await runtime(tmp_path)
    try:
        v1_campaign = planned_campaign(c)
        v2_campaign, _ = planned_v2(c)
        assert read_run_plan(c.store, v1_campaign)['plan']['agent'] == 'smolagents'
        trial = await c.runner.run(v1_campaign, FaultSpec(seed=0, primitives=[]), c.policies.baseline())
        assert c.store.get_record('episode_executions', trial.episode_id)['adapter_entrypoint_id'] == NATIVE_V1
        submitted, = events(c, trial.episode_id, 'report_submitted')
        assert set(submitted['payload']) == {'report'}                  # v1's event, unchanged
        # A saved v2 plan whose agent kind is rewritten to v1 no longer binds to its registration.
        from app.lab.run_plans import _bindings
        plan = read_run_plan(c.store, v2_campaign)['plan']
        with pytest.raises(StoreConflict, match='differs from its registration'):
            _bindings(c.store, v2_campaign, {**plan, 'agent': 'smolagents'})
    finally:
        await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('agent', ['smolagents', 'smolagents-v2'])
async def test_runner_transport_retry_parity(tmp_path, agent):
    provider = Lossy(failing={2})
    c = await runtime(tmp_path, provider=provider)
    try:
        campaign = planned_campaign(c) if agent == 'smolagents' else planned_v2(c)[0]
        ledger = CampaignLedger(c.store, campaign.campaign_id, campaign.caps, dollar_bounds=c.settings.model_call_dollar_bounds)
        trial = await c.runner.run(campaign, FaultSpec(seed=0, primitives=[]), c.policies.baseline(), ledger=ledger)
        assert trial.outcome == 'COMPLETED' and trial.usage.actor_calls == 4 and trial.usage.model_calls == 5
        assert ledger.used_calls == 5 and len(provider.sent) == 5 and provider.sent[1] == provider.sent[2]
        retry, = events(c, trial.episode_id, 'actor_transport_retry')
        assert retry['payload'] == {'code': 'CONNECTION_ERROR', 'attempt': 1}
        assert len(c.store.list_records('provider_failures')) == 1 and trial.usage.cost_dollars is None
    finally:
        await c.close()


@pytest.mark.anyio
async def test_v2_reports_pass_the_original_drift_check_and_are_never_excused_at_tick_0(tmp_path):
    """The companion's declared rule excuses only the old v1 adapter's tick-0 bug, which v2 never had."""
    c = await runtime(tmp_path)
    try:
        campaign, _ = planned_v2(c)
        trial = await c.runner.run(campaign, FaultSpec(seed=0, primitives=[]), c.policies.baseline())
        store, worlds = str(c.store.path), str(tmp_path / 'worlds')
        assert load('check_clock_drift').scan(store, worlds=True, worlds_dir=worlds)['drifted'] == []
        rewrite_report_tick(c, trial.episode_id, 0)
        result = checker().scan(store, worlds=True, worlds_dir=worlds)
        assert [row[0] for row in result['drifted']] == [trial.episode_id] and result['native_report_tick0_cleared'] == []
    finally:
        await c.close()


@pytest.mark.anyio
async def test_diagnosis_contract_names_the_selected_adapter(tmp_path):
    c = await runtime(tmp_path)
    try:
        v1_campaign = planned_campaign(c)
        v2_campaign, registration = planned_v2(c)
        v1_contract = runtime_contract(c.store, v1_campaign)['actor_contract']
        assert set(v1_contract) == {'implementation', 'task_contract', 'transport_contract', 'memory', 'prompt_hash',
                                    'source_hash', 'native_template_hash'}
        assert v1_contract['implementation'] == 'smolagents/1.26.0 ToolCallingAgent'
        assert v1_contract['memory'].endswith('original reports cite full delivered evidence IDs.')
        v2_contract = runtime_contract(c.store, v2_campaign)['actor_contract']
        assert v2_contract['adapter_protocol'] == adapter_protocol() and v2_contract['prompt_hash'] == registration.prompt_hash
        assert 'obs-N' in v2_contract['memory'] and v2_contract['task_contract'] == v1_contract['task_contract']
    finally:
        await c.close()


# ----------------------------------------------------------------------------- separate histories

def test_v1_and_v2_histories_never_merge(owner):
    v1 = register_agent(owner.store, owner.settings, 'smolagents')
    v2 = register_agent(owner.store, owner.settings, 'smolagents-v2')
    identities = [target_identity(r, owner.store.get_record('configurations', r.configuration_hash)) for r in (v1, v2)]
    assert identities[0] != identities[1] and set(identities[0]) == set(identities[1])
    assert identities[1]['adapter_entrypoint_id'] == NATIVE_V2 and identities[1]['source_hash'] == identities[0]['source_hash']
    v1_seeder = Seeder(owner, v1)
    seed_screen(v1_seeder)                                            # v1: dev-5 C3 3 of 3, dev-1 completed 3 of 3
    v2_seeder = Seeder(owner, v2)
    assert v1_seeder.history()['summary']['verified_episodes'] == 6
    assert v2_seeder.history()['summary']['status'] == 'NO_PRIOR_HISTORY'
    v2_seeder.episode(case('dev-5'), failed=('C5',))
    assert v2_seeder.history()['summary']['verified_episodes'] == 1
    assert v1_seeder.history()['summary']['verified_episodes'] == 6


# ----------------------------------------------------------------------------- bundle export, import and fresh v2 rerun

@pytest.mark.anyio
async def test_bundle_round_trip_from_a_v2_episode_to_a_fresh_v2_rerun(tmp_path):
    source = await runtime(tmp_path / 'source')
    target = await runtime(tmp_path / 'target')
    try:
        campaign, _ = planned_v2(source)
        recipe = FaultSpec(seed=0, primitives=[])
        trial = await source.runner.run(campaign, recipe, source.policies.baseline())
        counter = Counterexample(counterexample_id='counter-v2-round-trip', campaign_id=campaign.campaign_id,
            agent_registration_id=source.store.get_record('episodes', trial.episode_id)['agent_registration_id'],
            source_episode_id=trial.episode_id, target_invariant='C3', scenario_hash=content_hash(recipe),
            configuration_hash=campaign.configuration_hash, report_ref=None, verdict_ref='verdict-v2-round-trip')
        # A manual transport fixture (a COMPLETED episode), not evidence of a failing source.
        bundle = RegressionCompiler(source.store).compile(campaign, counter, source.policies.baseline(), recipe, None, [trial])
        regression = source.store.list_records('regressions')[0]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=source)), base_url='http://test') as client:
            download = await client.get(f'/api/regressions/{regression["regression_id"]}/download')
            assert download.status_code == 200
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=target)), base_url='http://test') as client:
            uploaded = await client.post('/api/bundle-imports', content=download.content,
                headers={'content-type': 'application/zip', 'x-faultlab-store-identity': store_descriptor(target.store)['identity']})
            assert uploaded.status_code == 201, uploaded.text
        detail = uploaded.json()
        # The exported recording keeps the source's v2 report record: cited labels and decoded IDs.
        recorded, = [e for e in detail['historical']['recording']['events'][trial.episode_id] if e['type'] == 'report_submitted']
        assert recorded['payload']['cited_evidence_tokens'] == ['obs-1', 'obs-2', 'obs-3']
        v1 = register_agent(target.store, target.settings, 'smolagents')
        v2 = register_agent(target.store, target.settings, 'smolagents-v2')
        listed = {t['agent_registration_id']: t for t in imports.import_detail(target.store, target.settings, detail['import_id'])['targets']}
        assert listed[v2.registration_id]['agent'] == 'smolagents-v2' and listed[v1.registration_id]['agent'] == 'smolagents'
        assert listed[v2.registration_id]['compatible'] is True
        body = imports.ImportedExecutionRequest(expected_store_identity=store_descriptor(target.store)['identity'],
            expected_manifest_hash=detail['manifest_hash'], expected_target_configuration_hash=v2.configuration_hash,
            agent_registration_id=v2.registration_id, request_id='request-import-v2', execution_profile_id='sandbox-v1', execute_live=True)
        started = await imports.execute_import(target, detail['import_id'], body)
        await target.tasks[started['execution']['execution_id']]
        result = imports.request_view(target.store, detail['import_id'], body.request_id)
        assert result['execution']['status'] == 'COMPLETED', result
        assert result['target']['agent'] == 'smolagents-v2' and result['assertions']['valid_trials'] == 3
        for episode_id in result['execution']['episode_ids']:
            # An imported execution has no run plan; its episode names the v2 registration and v2 wrote its report.
            assert target.store.get_record('episodes', episode_id)['agent_registration_id'] == v2.registration_id
            submitted, = events(target, episode_id, 'report_submitted')
            assert submitted['payload']['adapter_entrypoint_id'] == NATIVE_V2
            assert submitted['payload']['cited_evidence_tokens'][0] == 'obs-1'
            assert target.store.get_record('episodes', episode_id)['report']['evidence_ids'] == submitted['payload']['decoded_evidence_ids']
        assert bundle.bundle_id
    finally:
        await source.close(); await target.close()


@pytest.mark.anyio
@pytest.mark.parametrize('agent', ['smolagents', 'smolagents-v2'])
async def test_start_after_a_runtime_change_names_the_next_step_and_keeps_the_plan_readable(tmp_path, monkeypatch, agent):
    """Review finding L4. A runtime change (adapter v2 moved v1's adapter hash by changing registry.py) makes every
    idle plan saved before it unstartable. The refusal says what to do next, and the saved plan still reads."""
    c = await runtime(tmp_path)
    try:
        idle = planned_campaign(c) if agent == 'smolagents' else planned_v2(c)[0]
        real_digest = registry_module.digest
        monkeypatch.setattr(registry_module, 'digest',
                            lambda path: 'f' * 64 if Path(path).name == 'registry.py' else real_digest(path))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=c)), base_url='http://test') as api:
            started = await api.post(f'/api/campaigns/{idle.campaign_id}/start', json={})
            saved = await api.get(f'/api/campaigns/{idle.campaign_id}/plan')
        assert started.status_code == 409, started.text
        assert started.json()['error']['message'] == ('Current source, model or campaign limits differ from the saved plan. '
                                                      'Register the agent again and create a new campaign; this saved plan stays readable')
        assert saved.status_code == 200 and saved.json()['status'] == 'PLANNED'
        assert c.store.get_model('campaigns', idle.campaign_id, type(idle)).state == 'IDLE'
        assert sum(c.runner.provider.calls.values()) == 0
    finally:
        await c.close()

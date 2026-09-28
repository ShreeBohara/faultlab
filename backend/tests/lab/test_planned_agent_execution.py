"""Offline selected-agent execution; all responses here are declared reference inputs."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.adapters.business_tools import WorldClient
from app.agents.reference import ReferenceActor
from app.contracts.models import CampaignBudget, CampaignRequest, FaultSpec, canonical_json, content_hash
from app.integrations.registry import AgentRegistry, freeze_target_configuration
from app.lab.configuration import frozen_configuration
from app.lab.coordinator import LabCoordinator
from app.lab.diagnosis import runtime_contract
from app.lab.run_plans import RunPlanRequest, build_run_options, prepare_run_plan, read_run_plan
from app.lab.runner import B1_CONTROL_ID, B1_CONTROL_MODEL, EpisodeRunner
from app.lab.storage import StoreConflict
from app.providers.runtime import RuntimeGeneration
from app.simulator.main import create_app
from original_loop_fixture import (MODEL, CONTROL, OfflineEvidence, OfflineRunner, ManualPolicies,
    ScriptedProvider, fixture_settings, public_actor_answer)


@pytest.fixture
def anyio_backend(): return 'asyncio'


def planned_campaign(c, *, agent='smolagents', mode='baseline', case='dev-1', profile='live-v1'):
    registration=None
    if profile=='live-v1':
        caps=CampaignBudget(model_calls=c.settings.faultlab_model_call_cap,
            tokens=c.settings.faultlab_token_cap,dollars=float(c.settings.faultlab_dollar_cap))
        config=frozen_configuration(c.settings,caps,profile)
        registry=AgentRegistry(c.store)
        registration=(registry.register_smolagents(freeze_target_configuration(config,config['model']))
                      if agent=='smolagents' else registry.register_reference(config))
    options=build_run_options(c.settings,c.store)
    request=RunPlanRequest(expected_store_identity=options['data_store']['identity'],
        expected_setup_hash=options['setup_hash'],task_definition_id=options['task']['task_definition_id'],
        agent_registration_id=registration.registration_id if registration else None,
        mode=mode,config_profile_id=profile,task_text=options['task']['task_text_default'],order_id='order-selected',
        development_case_id=case if mode=='baseline' else None)
    prepared=prepare_run_plan(c.store,c.settings,request)
    return c.create(prepared.campaign_request,run_plan=prepared)


def public_native_input(messages):
    """Decode only native public prompt strings; no world, phase or recipe input."""
    found=[]
    def walk(value):
        if isinstance(value,dict):
            found.append(value)
            for child in value.values(): walk(child)
        elif isinstance(value,list):
            for child in value: walk(child)
        elif isinstance(value,str):
            # Native memory prefixes tool text with 'Observation:'. Decode each
            # embedded public JSON object, then recurse through serialized content.
            decoder=json.JSONDecoder(); cursor=0
            while True:
                index=value.find('{',cursor)
                if index<0: break
                try: child,used=decoder.raw_decode(value[index:])
                except ValueError: cursor=index+1; continue
                walk(child); cursor=index+used
    walk(messages)
    task=next(row['task'] for row in found if isinstance(row.get('task'),dict))
    observations={}
    for row in found:
        if isinstance(row.get('result'),dict) and 'evidence_id' in row:
            observations[row['evidence_id']]=row
    last=json.loads(messages[-1]['content'])
    required=last['final_report_required'] or any(row.get('final_report_required') is True for row in found)
    normalized=[{'role':'user','content':canonical_json({'task':task})},
                {'role':'user','content':canonical_json({'observations':list(observations.values()),'final_report_required':required})}]
    if any(row.get('blocked_action') for row in found):
        normalized.append({'role':'user','content':'{"blocked_action":true}'})
    return normalized


class NativeReferenceInputs(ScriptedProvider):
    """Same public decision fixture expressed in native single-tool transport."""
    async def complete(self,messages,*,role='actor',**kwargs):
        if role!='actor': return await super().complete(messages,role=role,**kwargs)
        self.calls[role]+=1
        normalized=public_native_input(messages)
        public=json.loads(normalized[1]['content'])
        if (self.mode=='interrupted' and not self.paused
                and any(row['result']['tool']=='update_order' for row in public['observations'])):
            self.paused=True
            self.pause_after_write.set()
            await self.release.wait()
        answer=public_actor_answer(normalized)
        output=({'name':answer['tool'],'arguments':answer['arguments']} if answer['kind']=='tool'
                else {'name':'final_answer','arguments':{'answer':answer['report']}})
        return RuntimeGeneration(canonical_json(output),MODEL,cost_usd=0.0)


async def runtime(tmp_path, *, actor=None, provider=None):
    settings=fixture_settings(tmp_path/'lab')
    c=LabCoordinator(settings)
    sim=create_app(database_dir=tmp_path/'worlds',control_token=CONTROL,settings=settings)
    client=httpx.AsyncClient(transport=httpx.ASGITransport(app=sim),base_url='http://127.0.0.1:8001')
    c.runner=OfflineRunner(c.store,WorldClient('http://127.0.0.1:8001',CONTROL,client=client),
                           provider or NativeReferenceInputs('accepted'),actor=actor,offline_fixture=True)
    return c


@pytest.mark.anyio
@pytest.mark.parametrize('purpose',['discovery','reproduction','reduction','intervention','source_validation','challenge','promotion'])
async def test_every_original_phase_uses_fresh_native_actor_and_preserves_original_report(tmp_path,purpose):
    c=await runtime(tmp_path)
    try:
        campaign=planned_campaign(c)
        trial=await c.runner.run(campaign,FaultSpec(seed=0,primitives=[]),c.policies.baseline(),purpose=purpose)
        episode=c.store.get_record('episodes',trial.episode_id)
        assert trial.lifecycle=='COMPLETED' and trial.outcome=='COMPLETED'
        assert trial.usage.actor_calls==4 and trial.usage.http_attempts==3
        assert episode['agent_registration_id']==read_run_plan(c.store,campaign)['plan']['agent_registration_id']
        assert episode['report']['overall']=='COMPLETED'
        assert episode['source_mode']=='offline_fixture'
        assert c.store.get_record('episode_executions',trial.episode_id)['adapter_entrypoint_id']=='smolagents-toolcalling-v1'
        snapshot=c.store.get_record('private_snapshots',trial.episode_id)['horizon']
        assert snapshot['orders'][0]['applied_shipping']=='express' and len(snapshot['notifications'])==1
    finally: await c.close()


@pytest.mark.anyio
async def test_marked_native_b1_is_distinct_reference_control_with_no_provider_call(tmp_path):
    c=await runtime(tmp_path)
    try:
        campaign=planned_campaign(c)
        trial=await c.runner.run(campaign,FaultSpec(seed=0,primitives=[]),c.policies.baseline(),arm='B1')
        episode=c.store.get_record('episodes',trial.episode_id)
        assert episode['agent_registration_id']==B1_CONTROL_ID and episode['model']==B1_CONTROL_MODEL
        assert episode['source_mode']=='offline_fixture' and trial.usage.model_calls==0
        assert c.store.get_record('episode_executions',trial.episode_id)['kind']=='deterministic_reference_control'
        assert not c.runner.provider.calls
    finally: await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('corruption',['actor','registration','configuration','task','plan','marker','native_context'])
async def test_mismatch_fails_before_world_or_model_creation(tmp_path,corruption):
    c=await runtime(tmp_path)
    try:
        campaign=planned_campaign(c)
        kwargs={}
        if corruption=='actor': kwargs['actor']=ReferenceActor()
        elif corruption=='registration': kwargs['agent_registration_id']='orders-v1-other'
        elif corruption=='configuration': campaign.configuration_hash='0'*64
        elif corruption=='task': campaign.order_id='other-order'
        elif corruption=='native_context': kwargs['actor_context_protocol']='faultlab-actor-context/v1'
        else:
            kind='campaign_plans' if corruption=='plan' else 'campaign_provenance'
            c.store.db.execute('DELETE FROM records WHERE kind=? AND id=?',(kind,campaign.campaign_id))
        with pytest.raises((ValueError,StoreConflict)):
            await c.runner.run(campaign,FaultSpec(seed=0,primitives=[]),c.policies.baseline(),**kwargs)
        assert c.store.list_records('episodes')==[] and not c.runner.provider.calls
        assert not list((tmp_path/'worlds').glob('*.sqlite3'))
    finally: await c.close()


@pytest.mark.anyio
async def test_native_false_original_report_remains_agent_violation(tmp_path):
    report={'upgrade_outcome':'SUCCEEDED','notification_outcome':'SUCCEEDED','overall':'COMPLETED',
            'evidence_ids':['invented'],'next_action':{'kind':'NONE'}}
    class FalseReport:
        async def complete(self,*args,**kwargs):
            return RuntimeGeneration(canonical_json({'name':'final_answer','arguments':{'answer':report}}),MODEL,cost_usd=0)
    c=await runtime(tmp_path,provider=FalseReport())
    try:
        campaign=planned_campaign(c)
        trial=await c.runner.run(campaign,FaultSpec(seed=0,primitives=[]),c.policies.baseline())
        assert trial.lifecycle=='COMPLETED' and trial.outcome=='VIOLATION'
        assert c.store.get_record('episodes',trial.episode_id)['report']==report
        assert trial.usage.http_attempts==0 and trial.failed_checks
    finally: await c.close()


@pytest.mark.anyio
async def test_selected_offline_development_case_uses_history_fixture_and_survives_restart(tmp_path):
    c=await runtime(tmp_path)
    settings=c.settings
    try:
        campaign=planned_campaign(c,profile='offline-v1',case='dev-4')
        plan=read_run_plan(c.store,campaign)['plan']
        await c.start(campaign.campaign_id)
        await c.tasks[campaign.campaign_id]
        assert c.get(campaign.campaign_id).state=='COMPLETED'
        episode,=c.store.list_campaign_episodes(campaign.campaign_id)
        inputs=c.store.get_record('private_episode_inputs',episode['episode_id'])
        assert inputs['fixture_id']=='history-v1' and inputs['intent']['expected_version']==4
        assert content_hash(inputs['recipe'])==plan['selection']['scenario_hash']
        assert episode['agent_registration_id']==B1_CONTROL_ID
        before=c.store.get_record('campaigns',campaign.campaign_id)
    finally: await c.close()
    reopened=LabCoordinator(settings)
    try:
        assert read_run_plan(reopened.store,campaign)['plan']==plan
        assert reopened.store.get_record('campaigns',campaign.campaign_id)==before
        assert len(reopened.store.list_campaign_episodes(campaign.campaign_id))==1
    finally: await reopened.close()


@pytest.mark.anyio
async def test_native_freeze_and_lab_contract_do_not_claim_reference_protocols(tmp_path):
    c=await runtime(tmp_path)
    try:
        campaign=planned_campaign(c)
        frozen=c.store.get_record('configurations',campaign.configuration_hash)
        assert not {'actor_response_protocol','actor_context_protocols','actor_context_protocol'} & frozen.keys()
        contract=runtime_contract(c.store,campaign)
        assert contract['actor_contract']['implementation']=='smolagents/1.26.0 ToolCallingAgent'
        assert contract['actor_contract']['prompt_hash']==frozen['actor_prompt_hash']
        reference=planned_campaign(c,agent='reference')
        assert runtime_contract(c.store,reference)==runtime_contract()
        legacy=c.create(CampaignRequest(task_text='legacy',order_id='order-1',mode='baseline'))
        assert runtime_contract(c.store,legacy)==runtime_contract()
    finally: await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('study',['completion','context','heldout'])
async def test_reference_protocol_studies_reject_native_before_reservation_or_dispatch(tmp_path,study):
    c=await runtime(tmp_path)
    try:
        campaign=planned_campaign(c)
        if study=='completion':
            from app.lab.completion_study import queue_completion_study
            operation=queue_completion_study(c,campaign.campaign_id)
        elif study=='context':
            from app.lab.context_study import queue_context_study
            operation=queue_context_study(c,campaign.campaign_id)
        else:
            from app.lab.heldout_check import queue_heldout_check
            operation=queue_heldout_check(c,campaign.campaign_id,'not-a-certificate')
        with pytest.raises(ValueError,match='reference Actor protocols'):
            await operation
        assert not c.store.list_records('episodes') and not c.store.list_records('budgets')
        assert c.active_id is None and not c.runner.provider.calls
    finally: await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('case',['offline_b0','unlabeled_fixture','fixture_marked_live','stale_b1'])
async def test_planned_execution_profile_and_control_identity_are_checked_before_world(tmp_path,case,monkeypatch):
    c=await runtime(tmp_path)
    try:
        campaign=planned_campaign(c,profile='offline-v1' if case=='offline_b0' else 'live-v1')
        runner=EpisodeRunner(c.store,c.runner.world_client,c.runner.provider,offline_fixture=case=='fixture_marked_live')
        kwargs={'arm':'B0','source_mode':'live'}
        if case=='unlabeled_fixture': kwargs['source_mode']='offline_fixture'
        elif case=='stale_b1':
            kwargs['arm']='B1'
            def invalid(*args): raise ValueError('Installed runtime changed')
            monkeypatch.setattr(AgentRegistry,'verify',invalid)
        with pytest.raises((ValueError,StoreConflict)):
            await runner.run(campaign,FaultSpec(seed=0,primitives=[]),c.policies.baseline(),**kwargs)
        assert not c.store.list_records('episodes') and not c.runner.provider.calls
    finally: await c.close()


@pytest.mark.anyio
async def test_selected_creation_revalidates_settings_and_rolls_back_all_new_campaign_records(tmp_path):
    c=await runtime(tmp_path)
    try:
        options=build_run_options(c.settings,c.store)
        request=RunPlanRequest(expected_store_identity=options['data_store']['identity'],
            expected_setup_hash=options['setup_hash'],task_definition_id=options['task']['task_definition_id'],
            mode='baseline',config_profile_id='offline-v1',task_text='Offline selected fixture',order_id='order-1',development_case_id='dev-1')
        prepared=prepare_run_plan(c.store,c.settings,request)
        before=[tuple(row) for row in c.store.db.execute('SELECT * FROM records ORDER BY rowid')]
        c.settings=replace(c.settings,faultlab_actor_context_protocol='faultlab-actor-context/v1')
        with pytest.raises(StoreConflict): c.create(prepared.campaign_request,run_plan=prepared)
        assert [tuple(row) for row in c.store.db.execute('SELECT * FROM records ORDER BY rowid')]==before
        assert c.store.list_records('campaign_plans')==[]
    finally: await c.close()


@pytest.mark.anyio
@pytest.mark.localhost_http
@pytest.mark.parametrize('mode',['accepted','rejected','interrupted'])
async def test_native_selected_original_learning_reaches_unchanged_acceptance_and_comparison(tmp_path,mode):
    """Manual fixture validates integration, never generated repair effectiveness."""
    from original_loop_fixture import localhost_simulator
    from app.integrations.regression_runner import inspect_bundle
    settings=fixture_settings(tmp_path/'lab')
    provider=NativeReferenceInputs(mode)
    with localhost_simulator(tmp_path,settings) as url:
        c=LabCoordinator(settings)
        c.runner=OfflineRunner(c.store,WorldClient(url,CONTROL),provider,offline_fixture=True)
        c.policies=ManualPolicies(c.store)
        c.evidence_gateway=OfflineEvidence(c.store,'offline-fixture/native-selected-loop')
        campaign=planned_campaign(c,mode='learn')
        registration=read_run_plan(c.store,campaign)['plan']['agent_registration_id']
        try:
            await c.start(campaign.campaign_id)
            if mode=='interrupted':
                await asyncio.wait_for(provider.pause_after_write.wait(),timeout=15)
                await c.stop(campaign.campaign_id)
                provider.release.set()
            await asyncio.wait_for(c.tasks[campaign.campaign_id],timeout=240)
            current=c.get(campaign.campaign_id)
            if mode!='accepted':
                assert current.state==('STOPPED' if mode=='interrupted' else 'NO_CHANGE')
                assert current.active_policy_version=='policy-v0'
                assert c.store.get_pointer('accepted-policy:'+campaign.configuration_hash) is None
                rows=c.store.list_campaign_episodes(campaign.campaign_id)
                assert rows and {e['agent_registration_id'] for e in rows}=={registration}
                assert {e['source_mode'] for e in rows}=={'offline_fixture'}
                if mode=='interrupted':
                    assert len(rows)==1 and rows[0]['lifecycle']=='INTERRUPTED'
                    assert not c.store.list_records('candidate_qualifications')
                else:
                    assert c.store.list_records('candidate_qualifications')[0]['decision']=='REJECTED'
                    assert not c.store.list_records('promotion_decisions')
                return
            assert current.state=='COMPLETED', c.store.list_records('execution_errors')
            assert current.active_policy_version!='policy-v0'
            policy=c.policies.get(current.active_policy_version)
            assert policy.decision=='ACCEPTED' and policy.author=='manual'
            episodes=c.store.list_campaign_episodes(campaign.campaign_id)
            assert {'discovery','reproduction','reduction','intervention','source_validation','challenge','promotion'} <= {e['experiment_purpose'] for e in episodes}
            assert {e['agent_registration_id'] for e in episodes}=={registration}
            assert {e['source_mode'] for e in episodes}=={'offline_fixture'}
            assert all(c.store.get_record('episode_executions',e['episode_id'])['offline_fixture'] for e in episodes)
            assert all(row['agent_registration_id']==registration for row in c.store.list_records('counterexamples'))
            assert all(row['source']=='local_only' for row in c.store.list_records('evidence'))
            bundles=c.store.list_records('bundles')
            assert bundles and any(row['artifact_kind']=='accepted_policy_bundle' for row in bundles)
            for row in bundles:
                from app.lab.regressions import RegressionCompiler
                directory=tmp_path/'exports'/row['bundle_id']
                RegressionCompiler(c.store).export(row['bundle_id'],directory)
                inspected=inspect_bundle(directory)
                assert inspected.source_configuration['actor_prompt_hash']==c.store.get_record('configurations',campaign.configuration_hash)['actor_prompt_hash']
            compared=planned_campaign(c,mode='compare')
            assert compared.active_policy_version==policy.version
            await c.start(compared.campaign_id)
            await asyncio.wait_for(c.tasks[compared.campaign_id],timeout=120)
            assert c.get(compared.campaign_id).state=='COMPLETED'
            assert {e['agent_registration_id'] for e in c.store.list_campaign_episodes(compared.campaign_id)}=={registration}
            assert c.store.get_pointer('accepted-policy:'+campaign.configuration_hash)==policy.version
        finally:
            await c.runner.world_client.close()
            await c.close()
    reopened=LabCoordinator(settings)
    try:
        assert read_run_plan(reopened.store,campaign.campaign_id)['plan']['agent_registration_id']==registration
        assert reopened.get(campaign.campaign_id).active_policy_version==policy.version
        assert reopened.store.get_pointer('accepted-policy:'+campaign.configuration_hash)==policy.version
    finally: await reopened.close()


@pytest.mark.anyio
async def test_selected_native_can_use_only_admitted_matching_regression_target(tmp_path):
    from app.contracts.models import RegressionExecution,EpisodeBudget,Usage
    c=await runtime(tmp_path)
    try:
        source=planned_campaign(c)
        reference=planned_campaign(c,agent='reference')
        registration=AgentRegistry(c.store).get(read_run_plan(c.store,reference)['plan']['agent_registration_id'])
        target=source.model_copy(update={'configuration_hash':reference.configuration_hash,'model':reference.model})
        actor=AgentRegistry(c.store).reviewed_actor(registration.registration_id)
        runner=OfflineRunner(c.store,c.runner.world_client,ScriptedProvider('accepted'),offline_fixture=True)
        kwargs=dict(purpose='reproduction',study_id='execution-reference-target',
                    agent_registration_id=registration.registration_id,actor=actor)
        with pytest.raises(StoreConflict):
            await runner.run(target,FaultSpec(seed=0,primitives=[]),c.policies.baseline(),**kwargs)
        assert not c.store.list_records('episodes')
        execution=RegressionExecution(execution_id=kwargs['study_id'],bundle_id='bundle-reference-target',
            manifest_hash='a'*64,registration_id=registration.registration_id,profile_id='sandbox-v1',
            mode='FRESH_SANDBOX',explicit_action=True,policy_hash=c.policies.baseline().policy_hash,
            configuration_hash=target.configuration_hash,declared_budget=EpisodeBudget(),usage=Usage(),
            episode_ids=[],world_ids=[],status='RUNNING')
        c.store.put_record('regression_executions',execution.execution_id,execution)
        c.store.put_record('regressions','regression-target',{'campaign_id':source.campaign_id,'bundle_id':execution.bundle_id})
        trial=await runner.run(target,FaultSpec(seed=0,primitives=[]),c.policies.baseline(),**kwargs)
        assert trial.outcome=='COMPLETED'
        episode=c.store.get_record('episodes',trial.episode_id)
        assert episode['agent_registration_id']==registration.registration_id
        assert episode['configuration_hash']==registration.configuration_hash
        assert c.store.get_record('episode_executions',trial.episode_id)['target_override'] is True
        execution.status='COMPLETED'
        c.store.put_record('regression_executions',execution.execution_id,execution)
        with pytest.raises(StoreConflict):
            await runner.run(target,FaultSpec(seed=0,primitives=[]),c.policies.baseline(),**kwargs)
        assert len(c.store.list_records('episodes'))==1
    finally: await c.close()


@pytest.mark.anyio
async def test_reference_context_override_requires_a_matching_running_study(tmp_path):
    c=await runtime(tmp_path,provider=ScriptedProvider('accepted'))
    try:
        campaign=planned_campaign(c,agent='reference')
        kwargs=dict(purpose='context_study',arm='P1',study_id='study-context-explicit',
                    actor_context_protocol='faultlab-actor-context/v1')
        with pytest.raises(StoreConflict):
            await c.runner.run(campaign,FaultSpec(seed=0,primitives=[]),c.policies.baseline(),**kwargs)
        record={'study_id':kwargs['study_id'],'status':'RUNNING','campaign_id':campaign.campaign_id,
                'configuration_hash':campaign.configuration_hash,'protocol_by_arm':{'P1':kwargs['actor_context_protocol']}}
        c.store.put_record('context_studies',record['study_id'],record)
        trial=await c.runner.run(campaign,FaultSpec(seed=0,primitives=[]),c.policies.baseline(),**kwargs)
        assert trial.outcome=='COMPLETED'
        descriptor=c.store.get_record('episode_executions',trial.episode_id)
        assert descriptor['actor_context_protocol']==kwargs['actor_context_protocol']
        assert descriptor['registration_id']==read_run_plan(c.store,campaign)['plan']['agent_registration_id']
        record['status']='COMPLETED'; c.store.put_record('context_studies',record['study_id'],record)
        with pytest.raises(StoreConflict):
            await c.runner.run(campaign,FaultSpec(seed=0,primitives=[]),c.policies.baseline(),**kwargs)
        assert len(c.store.list_records('episodes'))==1
    finally: await c.close()

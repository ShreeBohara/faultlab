"""Interrupted jobs retain evidence and charges without spending future reserves."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.contracts.models import CampaignRequest, Episode, SearchComparison, TrialResult, Usage, content_hash, new_id
from app.lab.audit import queue_audit
from app.lab.budgets import CampaignLedger,JobFinalizationError
from app.lab.coordinator import LabCoordinator
from app.lab.ownership import StoreInUse
from app.lab.portability import queue_portability
from app.lab.search_benchmark import queue_search
from app.providers.runtime import RuntimeGeneration
from test_evaluation import setup
from test_search_benchmark import SelectorProvider, setup as search_setup


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def save_episode(c,campaign,study,purpose,*,returned=True,usage=None):
    episode=Episode(campaign_id=campaign.campaign_id,episode_id=new_id('episode'),world_id=new_id('world'),
        origin='prototype' if purpose=='discovery' else 'faultlab_evaluation',split='promotion' if purpose=='promotion' else 'final_audit' if purpose in ('final_audit','portability') else 'development',
        arm='B0',source_mode='offline_fixture',experiment_purpose=purpose,trial_index=0,
        execution_epoch=campaign.execution_epoch,
        selector_id='explorer' if purpose=='selection_comparison' else None,
        study_id=study,evidence_context_id=study,task_id=new_id('task'),scenario_hash=content_hash('fixture'),
        policy_hash=c.policies.baseline().policy_hash,policy_version='policy-v0',model=campaign.model,
        configuration_hash=campaign.configuration_hash,lifecycle='COMPLETED' if returned else 'RUNNING',
        usage=usage or Usage(model_calls=1,actor_calls=1,http_attempts=1,cost_dollars=.25))
    c.store.put_record('episodes',episode.episode_id,episode)
    if returned:
        trial=TrialResult(episode_id=episode.episode_id,world_id=episode.world_id,
            scenario_hash=episode.scenario_hash,policy_hash=episode.policy_hash,arm='B0',trial_index=0,
            lifecycle='COMPLETED',outcome='COMPLETED',fault_scheduled=False,fault_triggered=False,usage=episode.usage)
        c.store.put_record('trials',episode.episode_id,trial,immutable=True)
    return episode


def search_record(campaign,comparison_id):
    return SearchComparison(comparison_id=comparison_id,status='RUNNING',campaign_id=campaign.campaign_id,
        manifest_hash='a'*64,registration_id='orders-v1',policy_hash='b'*64,generator_hash='c'*64,
        validator_hash='d'*64,deduplication_hash='e'*64,selector_order=['explorer','systematic'],
        systematic_digest='f'*64,context_ids=['context-one','context-two'],trial_ids=[],usage=Usage(),
        stopping_reason='Offline recovery fixture').model_dump(mode='json')


def fail_release_persistence(monkeypatch,store,reservation):
    put=store.put_record
    observed=[]
    def fail(kind,key,value,**kwargs):
        if kind=='budgets' and reservation not in value['reservations']:
            observed.append(True)
            raise OSError('Injected local persistence failure')
        return put(kind,key,value,**kwargs)
    monkeypatch.setattr(store,'put_record',fail)
    return observed


async def verify_pending_then_recovery(c,ledger,kind,job,reservation,*,recovered_status='INCOMPLETE'):
    # Release popped the live ledger before persistence failed. The finalizer
    # restores memory as well as the transaction, including every charged call.
    before=c.store.get_record('budgets',ledger.campaign_id)
    assert reservation in ledger.reservations
    assert before['reservations']==ledger.reservations
    assert before['used_calls']==ledger.used_calls and ledger.used_calls>0
    assert c.store.get_record(kind,job)['status'] in ('RUNNING','PENDING','QUEUED')
    assert c.active_id is None
    await c.close()
    restarted=LabCoordinator(c.settings)
    try:
        assert restarted.store.get_record(kind,job)['status']==recovered_status
        expected=deepcopy(before); expected['reservations'].pop(reservation)
        assert restarted.store.get_record('budgets',ledger.campaign_id)==expected
    finally: await restarted.close()


@pytest.mark.anyio
@pytest.mark.parametrize('kind,reservation,purpose',[
    ('audit_results','final_audit','final_audit'),
    ('search_comparisons','selection_comparison','selection_comparison'),
    ('portability','portability','portability'),
])
async def test_restart_finalizes_only_unfinished_auxiliary_job(tmp_path,kind,reservation,purpose):
    c,campaign,ledger,_,_=setup(tmp_path)
    c.transition(campaign.campaign_id,'COMPLETED','Saved terminal campaign is not a job handle')
    historical_campaign=c.store.get_record('campaigns',campaign.campaign_id)
    for _ in range(2):
        ledger.consume_call(reservation=reservation)
        ledger.reconcile(RuntimeGeneration('offline','offline',input_tokens=8,output_tokens=2,cost_usd=.25))
    ledger.reserve('future:unknown',5)
    before=c.store.get_record('budgets',campaign.campaign_id)
    future=c.create(CampaignRequest(task_text='Untouched future work',order_id='future',mode='baseline'))
    CampaignLedger(c.store,future.campaign_id)
    future_budget=c.store.get_record('budgets',future.campaign_id)
    job='job-recovery'; study='frozen-external-study' if kind=='portability' else job
    returned=save_episode(c,campaign,study,purpose)
    unreturned=save_episode(c,campaign,study,purpose,returned=False)
    saved_trial=c.store.get_record('trials',returned.episode_id)
    if kind=='audit_results':
        record={'batch_id':job,'campaign_id':campaign.campaign_id,'status':'RUNNING','trial_ids':[]}
        closed={**record,'batch_id':'old-audit','status':'COMPLETED','reason':'Historical explanation'}
        c.store.put_record(kind,closed['batch_id'],closed)
    elif kind=='search_comparisons':
        record=search_record(campaign,job)
        closed={**record,'comparison_id':'old-search','status':'COMPLETED'}
        c.store.put_record(kind,closed['comparison_id'],closed)
        c.store.put_record('search_requests','request-search',{'request_id':'request-search',
            'campaign_id':campaign.campaign_id,'comparison_id':job,'status':'RUNNING'})
    else:
        record={'portability_id':job,'status':'PENDING','trial_pairs':[], 'limitations':['Prior limitation']}
        closed={**record,'portability_id':'old-portability','status':'COMPLETED'}
        c.store.put_record(kind,closed['portability_id'],closed)
        freeze={'freeze_hash':study}
        c.store.put_record('external_freezes',campaign.campaign_id,freeze,immutable=True)
        c.store.put_record('portability_freezes',study,{'portability_id':job,'freeze':freeze},immutable=True)
        c.store.put_record('portability_requests','request-portability',{'request_id':'request-portability',
            'campaign_id':campaign.campaign_id,'status':'RUNNING','portability_id':None,'freeze_hash':study})
    c.store.put_record(kind,job,record)
    settings=c.settings
    c.store.close()  # Explicit connection close also relinquishes coordinator ownership.
    restarted=LabCoordinator(settings)
    try:
        after=restarted.store.get_record(kind,job)
        assert after['status']=='INCOMPLETE'
        assert restarted.store.get_record(kind,next(closed[key] for key in ('batch_id','comparison_id','portability_id') if key in closed))==closed
        assert restarted.store.get_record('campaigns',campaign.campaign_id)==historical_campaign
        assert restarted.store.get_record('budgets',future.campaign_id)==future_budget
        expected=deepcopy(before); expected['reservations'].pop(reservation)
        assert restarted.store.get_record('budgets',campaign.campaign_id)==expected
        assert restarted.store.get_record('trials',returned.episode_id)==saved_trial
        assert restarted.store.get_record('episodes',unreturned.episode_id)['lifecycle']=='INTERRUPTED'
        assert len(restarted.store.list_campaign_episodes(campaign.campaign_id))==2
        if kind=='audit_results': progress=after
        elif kind=='search_comparisons':
            assert returned.episode_id in after['trial_ids']
            assert restarted.store.get_record('search_requests','request-search')['status']=='INCOMPLETE'
            progress=restarted.store.get_record('search_progress',job)
        else: progress=restarted.store.get_record('portability_requests','request-portability')
        assert set(progress['episode_ids'])=={returned.episode_id,unreturned.episode_id}
        assert set(progress['world_ids'])=={returned.world_id,unreturned.world_id}
        if 'usage' in progress: assert progress['usage']['model_calls']==2
    finally: await restarted.close()


@pytest.mark.anyio
async def test_queued_search_is_durable_and_startup_failure_releases_only_its_reserve(tmp_path,monkeypatch):
    c,campaign,ledger,_,runner=search_setup(tmp_path)
    c.runner=runner; c.ledgers[campaign.campaign_id]=ledger
    monkeypatch.setattr(Settings,'require_live',lambda _:None)
    async def fail(_): raise RuntimeError('SECRET_FAILURE_TEXT')
    c._get_runner=fail
    queued=await queue_search(c,campaign.campaign_id)
    saved=c.store.get_record('search_requests',queued['request_id'])
    assert saved['status']=='QUEUED' and saved['campaign_id']==campaign.campaign_id and saved['comparison_id']
    await c.tasks[queued['request_id']]
    saved=c.store.get_record('search_requests',queued['request_id'])
    assert saved['status']=='INCOMPLETE' and saved['error']['code']=='EXECUTION_ERROR'
    assert 'SECRET_FAILURE_TEXT' not in str(saved)
    assert set(ledger.reservations)=={'final_audit','portability'} and c.active_id is None
    await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('atomic_failure',[False,True])
async def test_search_cancellation_retains_unreturned_episode_and_selector_charge(tmp_path,monkeypatch,atomic_failure):
    c,campaign,ledger,_,runner=search_setup(tmp_path)
    c.runner=runner; runner.provider=SelectorProvider(campaign.model); c.ledgers[campaign.campaign_id]=ledger
    monkeypatch.setattr(Settings,'require_live',lambda _:None)
    ready=asyncio.Event(); captured=[]
    async def run(current,recipe,policy,**kwargs):
        ledger.consume_call(reservation=kwargs['reservation'])
        saved=save_episode(c,current,kwargs['study_id'],'selection_comparison',returned=False)
        captured.append(saved)
        ready.set(); await asyncio.Event().wait()
    runner.run=run
    queued=await queue_search(c,campaign.campaign_id)
    await asyncio.wait_for(ready.wait(),5)
    await c.stop(campaign.campaign_id)
    observed=fail_release_persistence(monkeypatch,c.store,'selection_comparison') if atomic_failure else []
    c.tasks[queued['request_id']].cancel()
    if atomic_failure:
        with pytest.raises(JobFinalizationError): await c.tasks[queued['request_id']]
        assert observed==[True]
        comparison_id=c.store.get_record('search_requests',queued['request_id'])['comparison_id']
        assert c.store.get_record('search_comparisons',comparison_id)['status']=='RUNNING'
        assert c.store.get_record('search_results',comparison_id) is None
        await verify_pending_then_recovery(c,ledger,'search_requests',queued['request_id'],'selection_comparison')
        return
    with pytest.raises(asyncio.CancelledError): await c.tasks[queued['request_id']]
    request=c.store.get_record('search_requests',queued['request_id'])
    result=c.store.get_record('search_comparisons',request['comparison_id'])
    assert request['status']==result['status']=='INCOMPLETE'
    assert c.store.get_record('search_progress',result['comparison_id'])['episode_ids']==[captured[0].episode_id]
    assert result['usage']['model_calls']==ledger.used_calls==2
    assert c.get(campaign.campaign_id).state=='STOPPED' and c.active_id is None
    assert set(ledger.reservations)=={'final_audit','portability'}
    await c.close()


@pytest.mark.anyio
async def test_ownership_conflict_happens_before_recovery_and_constructor_failure_releases(tmp_path,monkeypatch):
    c,campaign,ledger,candidate,_=setup(tmp_path)
    c.transition(campaign.campaign_id,'RUNNING')
    saved=save_episode(c,campaign,campaign.campaign_id,'selection_comparison',returned=False)
    before=(c.store.get_record('campaigns',campaign.campaign_id),c.store.get_record('episodes',saved.episode_id),
            c.store.get_record('budgets',campaign.campaign_id))
    with pytest.raises(StoreInUse): LabCoordinator(c.settings)
    with pytest.raises(StoreInUse): LabCoordinator(c.settings,store=c.store)
    assert before==(c.store.get_record('campaigns',campaign.campaign_id),c.store.get_record('episodes',saved.episode_id),
                    c.store.get_record('budgets',campaign.campaign_id))
    settings=c.settings
    await c.close()
    with monkeypatch.context() as patch:
        def fail(_): raise RuntimeError('constructor fixture')
        patch.setattr('app.lab.coordinator.PolicyRepository',fail)
        with pytest.raises(RuntimeError): LabCoordinator(settings)
    recovered=LabCoordinator(settings)
    assert recovered.store.get_record('episodes',saved.episode_id)['lifecycle']=='INTERRUPTED'
    await recovered.close()


@pytest.mark.anyio
@pytest.mark.parametrize('kind,reservation',[
    ('audit_results','final_audit'),('search_requests','selection_comparison'),('portability_requests','portability')])
@pytest.mark.parametrize('atomic_failure',[False,True])
async def test_restart_recovers_queued_request_before_any_episode(tmp_path,kind,reservation,monkeypatch,atomic_failure):
    c,campaign,ledger,_,_=setup(tmp_path)
    ledger.consume_call()
    ledger.reconcile(RuntimeGeneration('earlier','offline',input_tokens=5,output_tokens=1,cost_usd=.1))
    before=c.store.get_record('budgets',campaign.campaign_id)
    record={'campaign_id':campaign.campaign_id,'status':'QUEUED'}
    if kind=='audit_results': record.update(batch_id='queued',trial_ids=[])
    else:
        record['request_id']='queued'
        if kind=='search_requests': record['comparison_id']='not-started-comparison'
        else: record['portability_id']=None
    c.store.put_record(kind,'queued',record)
    closed={**record,'status':'COMPLETED','reason':'Historical original record'}
    identity='batch_id' if kind=='audit_results' else 'request_id'
    closed[identity]='historical'; c.store.put_record(kind,'historical',closed)
    c.store.close()
    if atomic_failure:
        from app.lab.storage import LabStore
        original_put=LabStore.put_record
        def fail_release(store,record_kind,key,value,**kwargs):
            if record_kind=='budgets' and reservation not in value['reservations']:
                raise OSError('Injected restart persistence failure')
            return original_put(store,record_kind,key,value,**kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(LabStore,'put_record',fail_release)
            with pytest.raises(OSError): LabCoordinator(c.settings)
        # Inspect without acquiring ownership or triggering a second recovery.
        import sqlite3,json
        with sqlite3.connect(f'file:{c.store.path}?mode=ro',uri=True) as db:
            raw=db.execute('SELECT payload FROM records WHERE kind=? AND id=?',(kind,'queued')).fetchone()[0]
            assert json.loads(raw)==record
            raw=db.execute('SELECT payload FROM records WHERE kind=? AND id=?',('budgets',campaign.campaign_id)).fetchone()[0]
            assert json.loads(raw)==before
    restarted=LabCoordinator(c.settings)
    try:
        assert restarted.store.get_record(kind,'queued')['status']=='INCOMPLETE'
        assert restarted.store.get_record(kind,'historical')==closed
        expected=deepcopy(before); expected['reservations'].pop(reservation)
        assert restarted.store.get_record('budgets',campaign.campaign_id)==expected
        assert restarted.store.list_records('episodes')==[]
    finally: await restarted.close()


@pytest.mark.anyio
@pytest.mark.parametrize('atomic_failure',[False,True])
async def test_audit_failure_retains_saved_but_unreturned_world(tmp_path,monkeypatch,atomic_failure):
    from app.referee.manifests import load_manifest
    c,campaign,ledger,candidate,runner=setup(tmp_path)
    candidate.decision='ACCEPTED'; c.policies.save(candidate)
    c.runner=runner; c.ledgers[campaign.campaign_id]=ledger
    c.store.put_record('audit_freezes',campaign.campaign_id,{'policy_hash':candidate.policy_hash,
        'configuration_hash':campaign.configuration_hash,'manifest_hash':load_manifest('final-audit')['manifest_hash']})
    saved=[]
    async def fail(current,recipe,policy,**kwargs):
        ledger.consume_call(reservation=kwargs['reservation'])
        saved.append(save_episode(c,current,kwargs['study_id'],'final_audit',returned=False))
        raise RuntimeError('SECRET_AUDIT_FAILURE')
    runner.run=fail
    observed=fail_release_persistence(monkeypatch,c.store,'final_audit') if atomic_failure else []
    queued=await queue_audit(c,campaign,candidate)
    assert c.store.get_record('audit_results',queued['batch_id'])['status']=='QUEUED'
    if atomic_failure:
        with pytest.raises(JobFinalizationError): await c.tasks[queued['batch_id']]
        assert observed==[True]
        await verify_pending_then_recovery(c,ledger,'audit_results',queued['batch_id'],'final_audit')
        return
    await c.tasks[queued['batch_id']]
    record=c.store.get_record('audit_results',queued['batch_id'])
    assert record['status']=='INCOMPLETE' and record['trial_ids']==[]
    assert record['episode_ids']==[saved[0].episode_id] and record['world_ids']==[saved[0].world_id]
    assert record['usage']['model_calls']==ledger.used_calls==1
    assert 'SECRET_AUDIT_FAILURE' not in str(record)
    assert set(ledger.reservations)=={'selection_comparison','portability'} and c.active_id is None
    await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('atomic_failure',[False,True])
async def test_portability_failure_retains_frozen_identity_and_unreturned_episode(tmp_path,monkeypatch,atomic_failure):
    from app.integrations.registry import AgentRegistry,freeze_target_configuration
    from app.referee.manifests import load_manifest
    c,campaign,ledger,candidate,runner=search_setup(tmp_path)
    candidate.decision='ACCEPTED'; c.policies.save(candidate)
    c.runner=runner; runner.provider=SelectorProvider(campaign.model); c.ledgers[campaign.campaign_id]=ledger
    monkeypatch.setattr(Settings,'require_live',lambda _:None)
    registry=AgentRegistry(c.store)
    config=c.store.get_record('configurations',campaign.configuration_hash)
    target=freeze_target_configuration(config,campaign.model)
    registered=registry.register_smolagents(target)
    manifest=deepcopy(load_manifest('portability'))
    manifest['external_identity']={'status':'FROZEN','registration_id':registered.registration_id,
        'source_hash':registered.source_hash,'adapter_hash':registered.adapter_hash,
        'configuration_hash':registered.configuration_hash}
    manifest['manifest_hash']=content_hash({k:v for k,v in manifest.items() if k!='manifest_hash'})
    frozen={'schema_version':'faultlab-external-freeze/v1','status':'FROZEN','core_freeze_hash':'a'*64,
        'manifest':manifest,'registration':registered.model_dump(mode='json'),'policy_hash':candidate.policy_hash}
    frozen['freeze_hash']=content_hash(frozen)
    c.store.put_record('external_freezes',campaign.campaign_id,frozen,immutable=True)
    saved=[]
    async def fail(current,recipe,policy,**kwargs):
        ledger.consume_call(reservation=kwargs['reservation'])
        saved.append(save_episode(c,current,kwargs['study_id'],'portability',returned=False))
        raise RuntimeError('SECRET_PORTABILITY_FAILURE')
    runner.run=fail
    observed=fail_release_persistence(monkeypatch,c.store,'portability') if atomic_failure else []
    queued=await queue_portability(c,campaign.campaign_id,SimpleNamespace(
        policy_version=candidate.version,agent_registration_id=registered.registration_id))
    pending=c.store.get_record('portability_requests',queued['request_id'])
    assert pending['status']=='QUEUED' and pending['freeze_hash']==frozen['freeze_hash']
    if atomic_failure:
        with pytest.raises(JobFinalizationError): await c.tasks[queued['request_id']]
        assert observed==[True]
        result_id=c.store.get_record('portability_freezes',frozen['freeze_hash'])['portability_id']
        assert c.store.get_record('portability',result_id)['status']=='PENDING'
        assert c.store.get_record('portability_metrics',result_id) is None
        await verify_pending_then_recovery(c,ledger,'portability_requests',queued['request_id'],'portability')
        return
    await c.tasks[queued['request_id']]
    request=c.store.get_record('portability_requests',queued['request_id'])
    result=c.store.get_record('portability',request['portability_id'])
    assert request['status']==result['status']=='INCOMPLETE'
    assert request['episode_ids']==[saved[0].episode_id] and request['world_ids']==[saved[0].world_id]
    assert request['trial_ids']==result['trial_pairs']==[]
    assert request['usage']['model_calls']==ledger.used_calls==1
    assert 'SECRET_PORTABILITY_FAILURE' not in str(request)
    assert set(ledger.reservations)=={'selection_comparison','final_audit'} and c.active_id is None
    await c.close()


@pytest.mark.anyio
async def test_close_failure_still_closes_store_and_releases_lease(tmp_path):
    c,campaign,_,_,_=setup(tmp_path)
    c.active_id=campaign.campaign_id
    async def fail(_): raise RuntimeError('Stop cleanup fixture')
    c.stop=fail
    with pytest.raises(RuntimeError): await c.close()
    restarted=LabCoordinator(c.settings)
    await restarted.close()


@pytest.mark.anyio
async def test_qualification_cleanup_respects_immutable_policy_and_rolls_back(tmp_path):
    from app.lab.storage import StoreConflict
    c,campaign,_,candidate,_=setup(tmp_path)
    c.store.put_record('policies',candidate.version,candidate,immutable=True)
    qualification={'qualification_ref':'immutable-fixture','campaign_id':campaign.campaign_id,
        'candidate_version':candidate.version,'decision':'PROPOSED'}
    c.store.put_record('candidate_qualifications','immutable-fixture',qualification)
    with pytest.raises(StoreConflict):
        c.incomplete_qualifications(campaign.campaign_id,'Interruption fixture')
    assert c.store.get_record('candidate_qualifications','immutable-fixture')==qualification
    assert c.policies.get(candidate.version).decision=='PROPOSED'
    assert c.store.get_pointer('active-policy:'+campaign.campaign_id)=='policy-v0'
    await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('atomic_failure',[False,True])
async def test_regression_finalization_is_atomic_and_retains_unreturned_world(tmp_path,monkeypatch,atomic_failure):
    from dataclasses import replace
    from app.integrations.registry import AgentRegistry
    from app.lab.regression_executions import execute_regression
    from test_regression_bundle import compile_fixture
    c,_,_=compile_fixture(tmp_path)
    campaign=c.get(c.store.list_records('campaigns')[0]['campaign_id'])
    registration=AgentRegistry(c.store).get(c.store.get_record('campaign_registrations',campaign.campaign_id)['registration_id'])
    c.settings=replace(c.settings,wandb_model=registration.model)
    monkeypatch.setattr(Settings,'require_live',lambda _:None)
    saved=[]
    async def fail(current,recipe,policy,**kwargs):
        ledger=c.ledgers[campaign.campaign_id]
        ledger.consume_call(reservation=kwargs['reservation'])
        saved.append(save_episode(c,current,kwargs['study_id'],'reproduction',returned=False))
        raise RuntimeError('SECRET_REGRESSION_FAILURE')
    c.runner=SimpleNamespace(provider=object(),run=fail)
    regression=c.store.list_records('regressions')[0]
    queued=await execute_regression(c,regression['regression_id'],SimpleNamespace(
        policy_version='policy-v0',agent_registration_id=registration.registration_id,
        execute_live=True,execution_profile_id='sandbox-v1'))
    reservation='regression:'+queued.execution_id
    ledger=c.ledgers[campaign.campaign_id]
    if atomic_failure:
        observed=fail_release_persistence(monkeypatch,c.store,reservation)
        with pytest.raises(JobFinalizationError): await c.tasks[queued.execution_id]
        assert observed==[True]
        assert c.store.get_record('regression_assertions',queued.execution_id) is None
        await verify_pending_then_recovery(c,ledger,'regression_executions',queued.execution_id,reservation)
        return
    await c.tasks[queued.execution_id]
    result=c.store.get_record('regression_executions',queued.execution_id)
    assert result['status']=='INCOMPLETE'
    assert result['episode_ids']==[saved[0].episode_id] and result['world_ids']==[saved[0].world_id]
    assert result['usage']['model_calls']==ledger.used_calls==1
    assert 'SECRET_REGRESSION_FAILURE' not in str(result)
    assert reservation not in ledger.reservations and c.active_id is None
    await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('study_kind',['baseline','completion','context'])
async def test_fixed_study_finalization_rolls_back_then_recovers(tmp_path,monkeypatch,study_kind):
    from importlib import import_module
    from test_baseline_study import settings
    c=LabCoordinator(settings(tmp_path))
    campaign=c.create(CampaignRequest(task_text='Offline finalization fixture',order_id='order-study',
        mode='baseline',config_profile_id='live-v1'))
    saved=[]
    async def fail(current,recipe,policy,**kwargs):
        ledger=c.ledgers[campaign.campaign_id]
        ledger.consume_call(reservation=kwargs['reservation'])
        saved.append(save_episode(c,current,kwargs['study_id'],kwargs['purpose'],returned=False))
        raise RuntimeError('SECRET_STUDY_FAILURE')
    c.runner=SimpleNamespace(provider=object(),run=fail)
    queue=getattr(import_module('app.lab.'+study_kind+'_study'),'queue_'+study_kind+'_study')
    queued=await queue(c,campaign.campaign_id)
    ledger=c.ledgers[campaign.campaign_id]; reservation=study_kind+':'+queued['study_id']
    observed=fail_release_persistence(monkeypatch,c.store,reservation)
    with pytest.raises(JobFinalizationError): await c.tasks[queued['study_id']]
    assert observed==[True] and len(saved)==1
    assert c.store.get_record('episodes',saved[0].episode_id)['world_id']==saved[0].world_id
    await verify_pending_then_recovery(c,ledger,study_kind+'_studies',queued['study_id'],reservation,
                                      recovered_status='INTERRUPTED')


@pytest.mark.anyio
async def test_queued_evaluator_finalization_rolls_back_request_and_batch(tmp_path,monkeypatch):
    from app.lab.evaluation import queue_evaluation
    c,campaign,ledger,_,runner=setup(tmp_path)
    c.runner=runner; c.ledgers[campaign.campaign_id]=ledger
    monkeypatch.setattr(Settings,'require_live',lambda _:None)
    saved=[]
    async def fail(current,recipe,policy,**kwargs):
        ledger.consume_call(reservation=kwargs['reservation'])
        saved.append(save_episode(c,current,kwargs.get('study_id',current.campaign_id),'promotion',returned=False))
        raise RuntimeError('SECRET_EVALUATOR_FAILURE')
    runner.run=fail
    queued=await queue_evaluation(c,SimpleNamespace(campaign_id=campaign.campaign_id,
        policy_versions=['policy-v0'],purpose='comparison'))
    request=c.store.get_record('evaluation_requests',queued['request_id'])
    reservation='promotion:'+request['batch_id']
    observed=fail_release_persistence(monkeypatch,c.store,reservation)
    with pytest.raises(JobFinalizationError): await c.tasks[queued['request_id']]
    assert observed==[True] and len(saved)==1
    assert c.store.get_record('evaluations',request['batch_id'])['reason']=='Admitted; execution pending'
    await verify_pending_then_recovery(c,ledger,'evaluation_requests',queued['request_id'],reservation,
                                      recovered_status='INTERRUPTED')


@pytest.mark.anyio
@pytest.mark.parametrize('kind,id_field,prefix',[
    ('baseline_studies','study_id','baseline:'),
    ('completion_studies','study_id','completion:'),
    ('context_studies','study_id','context:'),
    ('heldout_checks','check_id','promotion:'),
    ('evaluation_requests','request_id','promotion:'),
    ('regression_executions','execution_id','regression:'),
])
async def test_other_job_restart_release_is_atomic_and_history_is_untouched(tmp_path,monkeypatch,kind,id_field,prefix):
    import json,sqlite3
    from app.lab.storage import LabStore
    from app.contracts.models import RegressionExecution,EpisodeBudget
    c,campaign,ledger,_,_=setup(tmp_path)
    c.transition(campaign.campaign_id,'COMPLETED','Historical campaign retained')
    historical_campaign=c.store.get_record('campaigns',campaign.campaign_id)
    job='interrupted-job'; reservation=prefix+job
    ledger.reserve(reservation,24); ledger.consume_call(reservation=reservation)
    before=c.store.get_record('budgets',campaign.campaign_id)
    record={id_field:job,'campaign_id':campaign.campaign_id,'status':'RUNNING','slots':[],
            'batch_id':job,'policy_hash':c.policies.baseline().policy_hash}
    if kind=='regression_executions':
        record=RegressionExecution(execution_id=job,bundle_id='bundle-fixture',manifest_hash='a'*64,
            registration_id='orders-v1',profile_id='sandbox-v1',mode='FRESH_SANDBOX',explicit_action=True,
            policy_hash=c.policies.baseline().policy_hash,configuration_hash=campaign.configuration_hash,
            declared_budget=EpisodeBudget(),usage=Usage(),episode_ids=[],world_ids=[],status='RUNNING').model_dump(mode='json')
    c.store.put_record(kind,job,record)
    closed={**record,id_field:'closed-job','status':'COMPLETED'}
    c.store.put_record(kind,'closed-job',closed,immutable=True)
    c.store.close()
    original_put=LabStore.put_record
    def fail_release(store,record_kind,key,value,**kwargs):
        if record_kind=='budgets' and reservation not in value['reservations']:
            raise OSError('Injected atomic recovery failure')
        return original_put(store,record_kind,key,value,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(LabStore,'put_record',fail_release)
        with pytest.raises(OSError): LabCoordinator(c.settings)
    with sqlite3.connect(f'file:{c.store.path}?mode=ro',uri=True) as db:
        for record_kind,key,expected in ((kind,job,record),('budgets',campaign.campaign_id,before)):
            assert json.loads(db.execute('SELECT payload FROM records WHERE kind=? AND id=?',(record_kind,key)).fetchone()[0])==expected
    restarted=LabCoordinator(c.settings)
    try:
        expected=deepcopy(before); expected['reservations'].pop(reservation)
        assert restarted.store.get_record('budgets',campaign.campaign_id)==expected
        assert restarted.store.get_record(kind,job)['status'] in ('INTERRUPTED','INCOMPLETE')
        assert restarted.store.get_record(kind,'closed-job')==closed
        assert restarted.store.get_record('campaigns',campaign.campaign_id)==historical_campaign
    finally: await restarted.close()


@pytest.mark.anyio
async def test_finalization_failure_marker_recovers_exact_reserve_on_terminal_campaign(tmp_path,monkeypatch):
    from app.lab.evaluation import PairedEvaluator
    from test_evaluation import cases
    c,campaign,ledger,candidate,runner=setup(tmp_path)
    reservation='promotion:owned-batch'
    async def fail(current,recipe,policy,**kwargs):
        ledger.consume_call(reservation=kwargs['reservation'])
        save_episode(c,current,current.campaign_id,'promotion',returned=False)
        raise RuntimeError('Fixture stops before runner return')
    runner.run=fail
    observed=fail_release_persistence(monkeypatch,c.store,reservation)
    with pytest.raises(JobFinalizationError):
        await PairedEvaluator(c.store,runner,ledger).run(campaign,cases(1),c.policies.baseline(),candidate,
                                                       batch_id='owned-batch')
    assert observed==[True]
    marker_id=campaign.campaign_id+':'+reservation
    assert c.store.get_record('reservation_finalization_failures',marker_id)['status']=='PENDING'
    c.transition(campaign.campaign_id,'ERROR','Saved failure stays terminal')
    historical=c.store.get_record('campaigns',campaign.campaign_id)
    # A prior terminal failure without prospective proof is deliberately untouched.
    c.store.put_record('reservation_finalization_failures','old-marker',{
        'campaign_id':campaign.campaign_id,'reservation':'future:unknown','status':'RECOVERED'},immutable=True)
    before=c.store.get_record('budgets',campaign.campaign_id)
    await c.close()
    restarted=LabCoordinator(c.settings)
    try:
        expected=deepcopy(before); expected['reservations'].pop(reservation)
        assert restarted.store.get_record('budgets',campaign.campaign_id)==expected
        assert restarted.store.get_record('campaigns',campaign.campaign_id)==historical
        assert restarted.store.get_record('reservation_finalization_failures',marker_id)['status']=='RECOVERED'
        assert restarted.store.get_record('reservation_finalization_failures','old-marker')['status']=='RECOVERED'
    finally: await restarted.close()

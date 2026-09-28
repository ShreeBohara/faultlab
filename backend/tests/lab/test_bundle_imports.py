"""Downloaded ZIP review is data-only; explicit offline reruns exercise real worlds."""
import asyncio
from dataclasses import replace
import io
import json
from pathlib import Path
import stat
import struct
import threading
import zipfile

import httpx
import pytest

from app.config import Settings
from app.contracts.models import CampaignRequest, Counterexample, FaultSpec, canonical_json, content_hash
from app.lab import bundle_imports as imports
from app.lab.coordinator import LabCoordinator
from app.lab.dashboard import store_descriptor
from app.lab.operator_actions import register_agent
from app.lab.regressions import RegressionCompiler
from app.lab.storage import ReadOnlyLabStore, StoreConflict
from app.main import create_app
from test_planned_agent_execution import NativeReferenceInputs, runtime


@pytest.fixture
def anyio_backend(): return 'asyncio'


def saved_rows(c):
    return ([tuple(row) for row in c.store.db.execute('SELECT * FROM records ORDER BY rowid')],
            [tuple(row) for row in c.store.db.execute('SELECT * FROM pointers ORDER BY name')])


def archive_bytes(files):
    target=io.BytesIO()
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,text in files.items(): archive.writestr(name,text)
    return target.getvalue()


def bundle_fixture(c, *, decision='BASELINE', version='policy-v0'):
    campaign=c.create(CampaignRequest(task_text='Upgrade and confirm',order_id='order-import-source',
                                     mode='baseline',config_profile_id='offline-v1'))
    policy=c.policies.baseline()
    if decision!='BASELINE':
        # Manual source metadata exercises transport; it is not a generated repair.
        policy=policy.model_copy(update={'version':version,'decision':decision,'author':'manual',
            'parent_version':'foreign-parent','raw_proposal_ref':'foreign-proposal',
            'development_episode_ids':['foreign-episode'],'decision_ref':'foreign-decision',
            'evaluation_refs':['foreign-evaluation']})
    recipe=FaultSpec(seed=17,primitives=[])
    counter=Counterexample(counterexample_id='counter-import-source',campaign_id=campaign.campaign_id,
        agent_registration_id='orders-v1',source_episode_id='episode-import-source',target_invariant='C3',
        scenario_hash=content_hash(recipe),configuration_hash=campaign.configuration_hash,report_ref=None,
        verdict_ref='verdict-import-source')
    c.store.put_record('private_episode_inputs',counter.source_episode_id,{'fixture_id':'standard-v1'},immutable=True)
    bundle=RegressionCompiler(c.store).compile(campaign,counter,policy,recipe,None,[])
    files={'manifest.json':canonical_json(bundle),**c.store.get_record('bundle_files',bundle.bundle_id)}
    return bundle,files


async def setup(tmp_path, *, decision='BASELINE', version='policy-v0', provider=None):
    source=await runtime(tmp_path/'source')
    try: bundle,files=bundle_fixture(source,decision=decision,version=version)
    finally: await source.close()
    target=await runtime(tmp_path/'target',provider=provider)
    return target,bundle,files


async def save(c,files):
    return await imports.save_import(c,store_descriptor(c.store)['identity'],archive_bytes(files))


def request(c,detail,registration,nonce='request-import-one'):
    return imports.ImportedExecutionRequest(expected_store_identity=store_descriptor(c.store)['identity'],
        expected_manifest_hash=detail['manifest_hash'],expected_target_configuration_hash=registration.configuration_hash,
        agent_registration_id=registration.registration_id,request_id=nonce,execution_profile_id='sandbox-v1',execute_live=True)


@pytest.mark.anyio
async def test_zip_import_is_idempotent_data_only_and_safe_during_active_campaign(tmp_path):
    c,bundle,files=await setup(tmp_path)
    try:
        before=saved_rows(c)
        c.active_id='unrelated-active-campaign'
        detail=await save(c,files)
        after=saved_rows(c)
        assert await save(c,files)==detail
        assert saved_rows(c)==after and c.active_id=='unrelated-active-campaign'
        assert detail['source']['evidence_verification']=='NO_LOCAL_VERIFICATION'
        assert detail['historical']['recording']==json.loads(files['evidence.json'])
        assert detail['policy']['decision']=='BASELINE' and detail['runnable']
        assert detail['provider_calls']==0 and not c.runner.provider.calls
        assert after[1]==before[1]
        assert c.store.list_records('campaigns')==[] and c.store.list_records('budgets')==[]
        assert [p['version'] for p in c.store.list_records('policies')]==['policy-v0']
        assert not c.store.list_records('regression_executions') and not c.store.list_records('episodes')
        assert imports.import_page(c.store)['items'][0]['bundle_id']==bundle.bundle_id
        c.active_id=None
    finally: await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('corruption',['missing','extra','traversal','duplicate','symlink','bad_hash','zip_json','untrusted_harness','oversized','bad_manifest','nonfinite'])
async def test_untrusted_archive_is_refused_without_saved_records(tmp_path,corruption,monkeypatch):
    c,_,files=await setup(tmp_path)
    try:
        files=dict(files)
        if corruption=='missing':files.pop('policy.json')
        if corruption=='extra':files['extra.txt']='unreviewed'
        if corruption=='traversal':files['../private.txt']='PRIVATE_CANARY'
        if corruption=='bad_hash':files['policy.json']+=' '
        if corruption=='untrusted_harness':files['harness/test_regression.py']='raise Exception("PRIVATE_CANARY")'
        if corruption=='bad_manifest':files['manifest.json']='{"PRIVATE_CANARY":true}'
        if corruption=='nonfinite':files['manifest.json']='{"x":NaN}'
        data=archive_bytes(files)
        if corruption in ('duplicate','symlink'):
            stream=io.BytesIO(data)
            with zipfile.ZipFile(stream,'a') as archive:
                if corruption=='duplicate':
                    with pytest.warns(UserWarning):archive.writestr('policy.json',files['policy.json'])
                else:
                    info=zipfile.ZipInfo('evil-link');info.create_system=3
                    info.external_attr=(stat.S_IFLNK|0o777)<<16;archive.writestr(info,'PRIVATE_CANARY')
            data=stream.getvalue()
        if corruption=='zip_json':data=files['evidence.json'].encode()
        if corruption=='oversized':monkeypatch.setattr(imports,'MAX_BUNDLE_FILE',20)
        before=saved_rows(c)
        with pytest.raises(ValueError,match=imports.REJECTED) as caught:
            await imports.save_import(c,store_descriptor(c.store)['identity'],data)
        assert 'PRIVATE_CANARY' not in str(caught.value)
        assert saved_rows(c)==before and not c.runner.provider.calls
    finally:await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('boundary',['manifest','target','store','unregistered','current_settings','busy','readiness','policy'])
async def test_stale_or_unready_execute_has_no_campaign_budget_or_policy_writes(tmp_path,boundary):
    c,_,files=await setup(tmp_path,decision='PROPOSED' if boundary=='policy' else 'BASELINE',version='foreign-proposed')
    try:
        detail=await save(c,files); registration=register_agent(c.store,c.settings,'smolagents')
        body=request(c,detail,registration)
        if boundary=='manifest':body=body.model_copy(update={'expected_manifest_hash':'a'*64})
        if boundary=='target':body=body.model_copy(update={'expected_target_configuration_hash':'a'*64})
        if boundary=='store':body=body.model_copy(update={'expected_store_identity':'a'*64})
        if boundary=='unregistered':body=body.model_copy(update={'agent_registration_id':'absent'})
        if boundary=='current_settings':c.settings=replace(c.settings,faultlab_model_call_cap=c.settings.faultlab_model_call_cap+1)
        if boundary=='busy':c.active_id='other-campaign'
        if boundary=='readiness':
            async def unavailable():raise StoreConflict('Simulator unavailable')
            c.require_simulator=unavailable
        before=saved_rows(c)
        with pytest.raises((ValueError,StoreConflict,KeyError)):
            await imports.execute_import(c,detail['import_id'],body)
        assert saved_rows(c)==before and not c.runner.provider.calls
        assert not c.store.list_records('campaigns') and not c.store.list_records('budgets')
        c.active_id=None
    finally:await c.close()


@pytest.mark.anyio
async def test_import_rerun_uses_real_native_worlds_and_historical_policy_namespace(tmp_path):
    c,bundle,files=await setup(tmp_path,decision='ACCEPTED',version='policy-shared')
    try:
        unrelated=c.policies.baseline().model_copy(update={'version':'policy-shared','decision':'REJECTED'})
        c.policies.save(unrelated)
        original_policy=c.store.get_record('policies','policy-shared')
        detail=await save(c,files);registration=register_agent(c.store,c.settings,'smolagents')
        body=request(c,detail,registration)
        started=await imports.execute_import(c,detail['import_id'],body)
        await c.tasks[started['execution']['execution_id']]
        result=imports.request_view(c.store,detail['import_id'],body.request_id)
        assert result['execution']['status']=='COMPLETED',result
        assert result['target']['agent']=='smolagents' and result['target']['model']==registration.model
        assert len(result['execution']['world_ids'])==len(set(result['execution']['world_ids']))==3
        assert result['assertions']['attempted']==3 and not result['assertions']['provider_backed']
        assert result['assertions']['source_modes']==['offline_fixture']
        assert result['assertions']['valid_trials']==3 and result['assertions']['lab_integrity_errors']==0
        assert not result['source_evidence_verified_locally']
        for episode_id in result['execution']['episode_ids']:
            episode=c.store.get_record('episodes',episode_id)
            policy=c.policies.get(episode['policy_version'])
            assert policy.policy_hash==bundle.policy_hash and policy.decision=='ACCEPTED'
            assert policy.version.startswith('imported-') and policy.parent_version is None
            assert policy.raw_proposal_ref is None and not policy.development_episode_ids
            assert policy.decision_ref is None and not policy.evaluation_refs
            assert episode['agent_registration_id']==registration.registration_id
            assert episode['report']['overall']=='COMPLETED'
            snap=c.store.get_record('private_snapshots',episode_id)['horizon']
            assert snap['orders'][0]['applied_shipping']=='express' and len(snap['notifications'])==1
            provenance=imports.policy_import_provenance(c.store,policy.version)
            assert provenance['historical_decision']=='ACCEPTED' and provenance['local_acceptance'] is False
            assert provenance['source_policy']['development_episode_ids']==['foreign-episode']
        assert c.store.get_record('policies','policy-shared')==original_policy
        assert c.get(result['owner_campaign_id']).active_policy_version=='policy-v0'
        assert c.store.get_pointer('accepted-policy:'+registration.configuration_hash) is None
        from app.lab.exports import development_recording
        recording=development_recording(c.store,result['owner_campaign_id'])
        assert recording['campaign_role']=='regression_budget_owner'
        assert recording['target_agent_registration']['registration_id']==registration.registration_id
        assert content_hash(recording['target_configuration'])==registration.configuration_hash
        assert recording['imported_execution']['target']==result['target']
        assert recording['policy_import_provenance'][policy.version]['local_acceptance'] is False
        with pytest.raises(StoreConflict,match='ordinary campaigns'):await c.start(result['owner_campaign_id'])
        before=saved_rows(c);calls=dict(c.runner.provider.calls)
        assert await imports.execute_import(c,detail['import_id'],body)==result
        assert saved_rows(c)==before and dict(c.runner.provider.calls)==calls
        with pytest.raises(StoreConflict,match='already used'):
            await imports.execute_import(c,detail['import_id'],body.model_copy(update={'expected_manifest_hash':'b'*64}))
        settings=c.settings
    finally:await c.close()
    reopened=LabCoordinator(settings)
    try:
        assert await imports.execute_import(reopened,detail['import_id'],body)==result
        assert imports.execution_page(reopened.store,detail['import_id'])['items']==[result]
        assert reopened.active_id is None
    finally:await reopened.close()


@pytest.mark.anyio
@pytest.mark.parametrize('failure_kind',['policies','budgets','regression_executions',imports.REQUEST_KIND,'import_execution_owners'])
async def test_admission_failure_rolls_back_every_record_pointer_and_reservation(tmp_path,monkeypatch,failure_kind):
    c,_,files=await setup(tmp_path)
    try:
        detail=await save(c,files);registration=register_agent(c.store,c.settings,'smolagents')
        body=request(c,detail,registration); before=saved_rows(c)
        put=c.store.put_record
        def fail(kind,key,value,**kwargs):
            if kind==failure_kind:raise OSError('Injected admission persistence failure')
            return put(kind,key,value,**kwargs)
        monkeypatch.setattr(c.store,'put_record',fail)
        with pytest.raises(OSError):await imports.execute_import(c,detail['import_id'],body)
        assert saved_rows(c)==before and c.active_id is None and not c.ledgers and not c.tasks
        assert not c.runner.provider.calls
        with pytest.raises(KeyError):imports.request_view(c.store,detail['import_id'],body.request_id)
    finally:await c.close()


@pytest.mark.anyio
async def test_api_download_upload_archive_review_and_exact_nonce_lookup(tmp_path):
    c,_,files=await setup(tmp_path)
    try:
        app=create_app(coordinator=c)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            headers={'content-type':'application/zip','x-faultlab-store-identity':store_descriptor(c.store)['identity']}
            bad=await client.post('/api/bundle-imports',content=files['evidence.json'],headers={**headers,'content-type':'application/json'})
            assert bad.status_code==422 and not c.store.list_records(imports.IMPORT_KIND)
            uploaded=await client.post('/api/bundle-imports',content=archive_bytes(files),headers=headers)
            assert uploaded.status_code==201,uploaded.text
            detail=uploaded.json();ident=detail['import_id']
            assert detail.pop('import_status')=='created'
            again=await client.post('/api/bundle-imports',content=archive_bytes(files),headers=headers)
            assert again.status_code==201 and again.json()=={**detail,'import_status':'existing'}
            assert (await client.get('/api/bundle-imports')).json()['items'][0]['import_id']==ident
            assert (await client.get('/api/bundle-imports/'+ident)).json()==detail
            assert (await client.get(f'/api/bundle-imports/{ident}/requests/missing')).status_code==404
            assert (await client.get('/api/policies/policy-v0/import-provenance')).json()=={'imported':False}
        settings=replace(c.settings,faultlab_read_only=True)
        before=saved_rows(c)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(settings=settings)),base_url='http://test') as archive:
            assert (await archive.get('/api/bundle-imports')).json()['items'][0]['import_id']==ident
            assert (await archive.get('/api/bundle-imports/'+ident)).status_code==200
            assert (await archive.post('/api/bundle-imports',content=archive_bytes(files),headers=headers)).status_code==409
        assert saved_rows(c)==before
    finally:await c.close()


@pytest.mark.anyio
async def test_stream_size_bound_before_unzip(monkeypatch):
    monkeypatch.setattr(imports,'MAX_UPLOAD_BYTES',12)
    chunks=[]
    class Request:
        headers={'content-type':'application/zip'}
        async def stream(self):
            for chunk in (b'a'*8,b'b'*8,b'never-read'):
                chunks.append(chunk);yield chunk
    with pytest.raises(ValueError,match='transport bound'):await imports.read_zip_request(Request())
    assert len(chunks)==2


@pytest.mark.anyio
async def test_manifest_secret_is_refused_even_with_correct_rehashed_manifest(tmp_path):
    c,_,files=await setup(tmp_path)
    try:
        c.settings=replace(c.settings,wandb_api_key='dummy-manifest-secret-never-provider')
        manifest=json.loads(files['manifest.json'])
        manifest['setup_instructions']='Historical text dummy-manifest-secret-never-provider'
        manifest['manifest_hash']=content_hash({k:v for k,v in manifest.items() if k!='manifest_hash'})
        files={**files,'manifest.json':canonical_json(manifest)}
        before=saved_rows(c)
        with pytest.raises(ValueError,match=imports.REJECTED):
            await save(c,files)
        assert saved_rows(c)==before
    finally:await c.close()


@pytest.mark.anyio
@pytest.mark.parametrize('mutation',['entry_count','forged_count','directory_size','directory_offset','multidisk','zip64','trailing'])
async def test_central_directory_is_bounded_before_zip_parser(tmp_path,monkeypatch,mutation):
    c,_,files=await setup(tmp_path)
    try:
        if mutation in ('entry_count','forged_count'):
            data=bytearray(archive_bytes({f'item{i}':'x' for i in range(20000)}))
        else:data=bytearray(archive_bytes(files))
        offset=data.rfind(b'PK\x05\x06')
        if mutation=='forged_count':struct.pack_into('<HH',data,offset+8,9,9)
        if mutation=='directory_size':struct.pack_into('<L',data,offset+12,65537)
        if mutation=='directory_offset':struct.pack_into('<L',data,offset+16,0)
        if mutation=='multidisk':struct.pack_into('<H',data,offset+4,1)
        if mutation=='zip64':struct.pack_into('<HH',data,offset+8,65535,65535)
        if mutation=='trailing':data.extend(b'extra')
        monkeypatch.setattr(imports.zipfile,'ZipFile',lambda *_:pytest.fail('Unbounded central directory reached parser'))
        with pytest.raises(ValueError,match='ZIP directory'):imports._zip_payloads(bytes(data))
    finally:await c.close()


@pytest.mark.anyio
async def test_cancel_unadmitted_nonce_wins_against_slow_preparation_and_survives_restart(tmp_path,monkeypatch):
    c,_,files=await setup(tmp_path);entered=threading.Event();release=threading.Event();pending=None
    try:
        detail=await save(c,files);registration=register_agent(c.store,c.settings,'smolagents')
        body=request(c,detail,registration);prepare=imports._prepare_execution
        def blocked(*args):
            entered.set()
            assert release.wait(10)
            return prepare(*args)
        monkeypatch.setattr(imports,'_prepare_execution',blocked)
        pending=asyncio.create_task(imports.execute_import(c,detail['import_id'],body))
        assert await asyncio.to_thread(entered.wait,10)
        with pytest.raises(KeyError):imports.request_view(c.store,detail['import_id'],body.request_id)
        cancelled=await imports.cancel_request(c,detail['import_id'],body.request_id,body)
        assert cancelled=={'cancelled':True,'import_id':detail['import_id'],'request_id':body.request_id}
        assert await imports.cancel_request(c,detail['import_id'],body.request_id,body)==cancelled
        release.set()
        with pytest.raises(StoreConflict,match='cancelled'):await pending
        assert imports.request_view(c.store,detail['import_id'],body.request_id)==cancelled
        assert not c.store.list_records('campaigns') and not c.store.list_records('budgets')
        assert not c.store.list_records('episodes') and not c.runner.provider.calls
        assert not c.tasks and c.active_id is None
        settings=c.settings
    finally:
        release.set()
        if pending is not None:await asyncio.gather(pending,return_exceptions=True)
        await c.close()
    reopened=LabCoordinator(settings)
    try:
        assert imports.request_view(reopened.store,detail['import_id'],body.request_id)==cancelled
        with pytest.raises(StoreConflict,match='cancelled'):await imports.execute_import(reopened,detail['import_id'],body)
    finally:await reopened.close()


@pytest.mark.anyio
async def test_two_same_nonce_posts_admit_exactly_one_job_and_cancel_returns_its_result(tmp_path):
    c,_,files=await setup(tmp_path)
    try:
        detail=await save(c,files);registration=register_agent(c.store,c.settings,'smolagents')
        body=request(c,detail,registration)
        one,two=await asyncio.gather(imports.execute_import(c,detail['import_id'],body),imports.execute_import(c,detail['import_id'],body))
        assert one['execution']['execution_id']==two['execution']['execution_id']
        assert len(c.tasks)==1
        result=await imports.cancel_request(c,detail['import_id'],body.request_id,body)
        assert not result['cancelled'] and result['execution']['execution']['execution_id']==one['execution']['execution_id']
        await c.tasks[one['execution']['execution_id']]
        assert len(c.store.list_records('episodes'))==3
        assert len(list((c.settings.artifact_path/'import-executions').iterdir()))==1
    finally:await c.close()


@pytest.mark.anyio
async def test_small_regression_budget_has_only_24_call_reservation(tmp_path):
    c,_,files=await setup(tmp_path)
    try:
        c.settings=replace(c.settings,faultlab_model_call_cap=24,faultlab_token_cap=816000,faultlab_dollar_cap=1)
        detail=await save(c,files);registration=register_agent(c.store,c.settings,'smolagents')
        body=request(c,detail,registration)
        result=await imports.execute_import(c,detail['import_id'],body)
        budget=c.store.get_record('budgets',result['owner_campaign_id'])
        assert budget['caps']['model_calls']==24 and budget['caps']['tokens']==816000
        assert budget['reservations']=={'regression:'+result['execution']['execution_id']:{'calls':24,'tokens':816000}}
        await c.tasks[result['execution']['execution_id']]
        final=imports.request_view(c.store,detail['import_id'],body.request_id)
        assert final['execution']['status']=='COMPLETED'
        budget=c.store.get_record('budgets',result['owner_campaign_id'])
        assert budget['used_calls']==12 and budget['reservations']=={}
        with pytest.raises(StoreConflict,match='separately reviewed'):await c.admit_activity(result['owner_campaign_id'])
    finally:await c.close()


@pytest.mark.anyio
async def test_interrupted_import_keeps_charge_world_and_nonce_without_replay(tmp_path):
    provider=NativeReferenceInputs('interrupted')
    c,_,files=await setup(tmp_path,provider=provider)
    try:
        detail=await save(c,files);registration=register_agent(c.store,c.settings,'smolagents')
        body=request(c,detail,registration)
        first=await imports.execute_import(c,detail['import_id'],body)
        await asyncio.wait_for(provider.pause_after_write.wait(),10)
        await c.stop(first['owner_campaign_id']);provider.release.set()
        await c.tasks[first['execution']['execution_id']]
        result=imports.request_view(c.store,detail['import_id'],body.request_id)
        assert result['execution']['status']=='INCOMPLETE' and len(result['execution']['world_ids'])==1
        assert c.store.get_record('budgets',first['owner_campaign_id'])['used_calls']>=2
        before=saved_rows(c);count=dict(provider.calls)
        assert await imports.execute_import(c,detail['import_id'],body)==result
        assert saved_rows(c)==before and dict(provider.calls)==count
        settings=c.settings
    finally:provider.release.set();await c.close()
    reopened=LabCoordinator(settings)
    try:
        assert await imports.execute_import(reopened,detail['import_id'],body)==result
        assert reopened.active_id is None
    finally:await reopened.close()


@pytest.mark.anyio
@pytest.mark.parametrize('error',['wrong_store','missing_store','invalid_zip'])
async def test_invalid_upload_refused_before_lazy_store_initialization(tmp_path,error):
    settings=Settings(faultlab_artifact_dir=str(tmp_path/'absent'))
    expected=content_hash({'local_store_path':str((settings.artifact_path/'lab.sqlite3').resolve())})
    headers={'content-type':'application/zip','x-faultlab-store-identity':expected}
    if error=='wrong_store':headers['x-faultlab-store-identity']='a'*64
    if error=='missing_store':headers.pop('x-faultlab-store-identity')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(settings=settings)),base_url='http://test') as client:
        response=await client.post('/api/bundle-imports',content=b'invalid-zip',headers=headers)
        assert response.status_code==(422 if error=='invalid_zip' else 409)
    assert not settings.artifact_path.exists()


@pytest.mark.anyio
async def test_restart_recovers_admitted_job_before_worker_started_without_replay(tmp_path,monkeypatch):
    c,_,files=await setup(tmp_path)
    try:
        detail=await save(c,files);registration=register_agent(c.store,c.settings,'smolagents')
        body=request(c,detail,registration)
        # Inject process loss at the durable admission / task scheduling boundary.
        monkeypatch.setattr('app.lab.regression_executions.schedule_regression',lambda *a,**kw:kw['record'])
        started=await imports.execute_import(c,detail['import_id'],body)
        assert started['execution']['status']=='PENDING' and not c.store.list_records('episodes')
        before=c.store.get_record('budgets',started['owner_campaign_id'])
        settings=c.settings;c.store.close();c.active_id=None
        restarted=LabCoordinator(settings)
        try:
            result=await imports.execute_import(restarted,detail['import_id'],body)
            assert result['execution']['execution_id']==started['execution']['execution_id']
            assert result['execution']['status']=='INCOMPLETE' and result['execution']['world_ids']==[]
            after=restarted.store.get_record('budgets',started['owner_campaign_id'])
            expected=dict(before);expected['reservations']={}
            assert after==expected and restarted.active_id is None
            assert not restarted.tasks and not restarted.store.list_records('episodes')
        finally:await restarted.close()
    finally:await c.close()


@pytest.mark.anyio
async def test_history_pagination_skips_accounting_owners_and_imports_have_own_history(tmp_path):
    c,_,files=await setup(tmp_path)
    try:
        first=c.create(CampaignRequest(mode='baseline',task_text='First ordinary run',order_id='first'))
        second=c.create(CampaignRequest(mode='baseline',task_text='Second ordinary run',order_id='second'))
        owner=c.create(CampaignRequest(mode='baseline',task_text='Accounting owner',order_id='owner'))
        c.store.put_record('import_execution_owners',owner.campaign_id,{'role':'regression_budget_owner'},immutable=True)
        page=c.store.campaign_page(limit=1,exclude_import_owners=True)
        assert page['campaign_ids']==[second.campaign_id] and page['has_more']
        next_page=c.store.campaign_page(limit=1,before=page['next_before'],exclude_import_owners=True)
        assert next_page['campaign_ids']==[first.campaign_id] and not next_page['has_more']
        assert c.store.campaign_page(limit=1)['campaign_ids']==[owner.campaign_id]
        one=await save(c,files)
        changed=dict(files);manifest=json.loads(changed['manifest.json']);manifest['bundle_id']='bundle-second-import'
        manifest['manifest_hash']=content_hash({k:v for k,v in manifest.items() if k!='manifest_hash'})
        changed['manifest.json']=canonical_json(manifest);two=await save(c,changed)
        page=imports.import_page(c.store,limit=1)
        assert page['items'][0]['import_id']==two['import_id'] and page['has_more']
        next_page=imports.import_page(c.store,limit=1,before=page['next_before'])
        assert next_page['items'][0]['import_id']==one['import_id'] and not next_page['has_more']
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=c)),base_url='http://test') as client:
            assert [v['campaign_id'] for v in (await client.get('/api/campaigns')).json()['campaigns']]==[second.campaign_id,first.campaign_id]
    finally:await c.close()


@pytest.mark.anyio
async def test_actual_download_preserves_original_public_report_and_events_after_import(tmp_path):
    source=await runtime(tmp_path/'source');target=await runtime(tmp_path/'target')
    try:
        campaign=source.create(CampaignRequest(mode='baseline',task_text='Upgrade and confirm',order_id='original-order',config_profile_id='offline-v1'))
        recipe=FaultSpec(seed=0,primitives=[])
        trial=await source.runner.run(campaign,recipe,source.policies.baseline(),arm='B1',purpose='discovery')
        counter=Counterexample(counterexample_id='counter-observed-report',campaign_id=campaign.campaign_id,
            agent_registration_id='orders-v1',source_episode_id=trial.episode_id,target_invariant='C3',
            scenario_hash=content_hash(recipe),configuration_hash=campaign.configuration_hash,report_ref=None,
            verdict_ref='verdict-observed-report')
        # This is a manual transport fixture, not evidence of a failing source.
        bundle=RegressionCompiler(source.store).compile(campaign,counter,source.policies.baseline(),recipe,None,[trial])
        regression=source.store.list_records('regressions')[0]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=source)),base_url='http://test') as client:
            download=await client.get(f'/api/regressions/{regression["regression_id"]}/download')
            assert download.status_code==200 and download.headers['content-type']=='application/zip'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=target)),base_url='http://test') as client:
            uploaded=await client.post('/api/bundle-imports',content=download.content,
                headers={'content-type':'application/zip','x-faultlab-store-identity':store_descriptor(target.store)['identity']})
            assert uploaded.status_code==201,uploaded.text
            detail=uploaded.json();recording=detail['historical']['recording']
            original=source.store.get_record('episodes',trial.episode_id)
            assert recording['episodes'][0]['report']==original['report']
            assert recording['events'][trial.episode_id]
            assert recording['episodes'][0]['source_mode']=='offline_fixture'
            assert detail['source']['evidence_verification']=='NO_LOCAL_VERIFICATION'
            assert (await client.get('/api/episodes/'+trial.episode_id)).status_code==404
        assert target.store.get_record('bundle_files',bundle.bundle_id)==source.store.get_record('bundle_files',bundle.bundle_id)
        assert not target.store.list_records('episodes') and not target.runner.provider.calls
    finally:await source.close();await target.close()

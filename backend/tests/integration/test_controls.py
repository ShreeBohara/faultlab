import asyncio
import time
from types import SimpleNamespace
from fastapi.testclient import TestClient
from app.config import Settings
from app.contracts.models import Usage
from app.lab.coordinator import LabCoordinator
from app.lab.storage import LabStore
from app.main import create_app


class BlockingOfflineRunner:
    calls=0
    async def run(self,*args,stop,**kwargs):
        self.calls+=1
        while not stop():await asyncio.sleep(.01)
        return SimpleNamespace(episode_id='episode-stopped-fixture',usage=Usage(),lifecycle='INTERRUPTED',reason='STOP_REQUESTED')


def create(client,mode='baseline',profile='offline-v1'):
    r=client.post('/api/campaigns',json={'task_text':'Upgrade and confirm','order_id':'order-fixture','mode':mode,'config_profile_id':profile})
    assert r.status_code==201,r.text
    return r.json()['campaign_id']


def test_start_stop_conflict_and_read_only_reset(tmp_path):
    runner=BlockingOfflineRunner()
    coordinator=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path)),runner=runner)
    with TestClient(create_app(coordinator=coordinator)) as client:
        first,second=create(client),create(client)
        assert client.post(f'/api/campaigns/{first}/start',json={}).status_code==202
        assert client.post(f'/api/campaigns/{first}/start',json={}).status_code==202
        assert client.post(f'/api/campaigns/{second}/start',json={}).status_code==409
        assert client.post('/api/reset-demo',json={}).status_code==409
        begin=time.perf_counter()
        response=client.post(f'/api/campaigns/{first}/stop',json={})
        elapsed=time.perf_counter()-begin
        assert response.status_code==202 and response.json()['stop_requested']
        assert elapsed<.25
        assert response.json()['execution_epoch']==1
        deadline=time.monotonic()+2
        while coordinator.active_id and time.monotonic()<deadline:time.sleep(.01)
        assert not coordinator.active_id and runner.calls==1
        assert client.get(f'/api/campaigns/{first}').json()['state']=='STOPPED'
        policies=client.get('/api/policies').json()
        assert client.post('/api/reset-demo',json={}).status_code==201
        assert client.get('/api/policies').json()==policies
        assert runner.calls==1


def test_invalid_inputs_and_unknown_ids_are_safe(tmp_path):
    with TestClient(create_app(settings=Settings(faultlab_artifact_dir=str(tmp_path)))) as client:
        assert client.get('/api/campaigns/missing').status_code==404
        bad=client.post('/api/campaigns',json={'task_text':'x','order_id':'x','mode':'baseline','provider_key':'should-not-echo'})
        assert bad.status_code==422 and 'should-not-echo' not in bad.text
        campaign=create(client)
        assert client.post(f'/api/campaigns/{campaign}/start',json={'spend':999999}).status_code==422
        assert client.get(f'/api/episodes/missing/events?after=-1').status_code==422
        assert client.post(f'/api/campaigns/{campaign}/retry-evidence',json={'episode_ids':['foreign']}).status_code==422


def test_hidden_events_advance_cursor_without_revealing_payload(tmp_path):
    store=LabStore(tmp_path/'events.sqlite3')
    store.put_record('episodes','e1',{'campaign_id':'c1'})
    store.append_event('e1',type='episode_started',payload={'public':'first'})
    store.append_event('e1',type='private_test',payload={'private':'hidden'},visibility='PRIVATE_EVALUATOR')
    store.append_event('e1',type='report_submitted',payload={'public':'last'})
    first=store.events('e1',limit=2)
    assert [e['seq'] for e in first['events']]==[1]
    assert first['next_after']==2 and first['has_more']
    second=store.events('e1',after=first['next_after'])
    assert [e['seq'] for e in second['events']]==[3]
    assert second['next_after']==3 and not second['has_more']
    store.close()

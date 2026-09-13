"""Actual loopback control latency and canonical persisted evidence projection."""
import socket
import threading
import time
import json
import httpx
import pytest
import uvicorn
from app.config import Settings
from app.main import create_app

pytestmark=pytest.mark.localhost_http


def test_http_control_p95_and_persisted_evidence_identity(tmp_path,simulator_server):
    simulator_url,_=simulator_server
    app=create_app(settings=Settings(faultlab_artifact_dir=str(tmp_path/'lab'),faultlab_simulator_url=simulator_url,faultlab_control_token='integration-control'))
    listener=socket.socket();listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True);thread.start()
    deadline=time.monotonic()+5
    while not server.started and time.monotonic()<deadline:time.sleep(.005)
    assert server.started
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=3,trust_env=False) as client:
            c=client.post('/api/campaigns',json={'mode':'baseline','task_text':'Upgrade then confirm truthfully.','order_id':'order-projection','config_profile_id':'offline-v1'}).json()
            ident=c['campaign_id']
            assert client.post(f'/api/campaigns/{ident}/start',json={}).status_code==202
            deadline=time.monotonic()+4
            while time.monotonic()<deadline:
                c=client.get(f'/api/campaigns/{ident}').json()
                if c['state'] in ('COMPLETED','ERROR'):break
                time.sleep(.02)
            assert c['state']=='COMPLETED',c
            e=client.get(f'/api/episodes/{c["latest_episode_id"]}').json()
            matrix=client.get(f'/api/campaigns/{ident}/matrix').json()
            cell=next(cell for cell in matrix['cells'] if cell['episode_id']==e['episode_id'])
            assert cell['outcome']==e['verdict']['outcome']==e['report']['overall']=='COMPLETED'
            assert cell['policy_hash']==e['policy_hash']
            assert cell['source_mode']=='offline_fixture'
            assert matrix['counts']['valid_attempted']==matrix['counts']['completed']==1
            events=client.get(f'/api/episodes/{e["episode_id"]}/events').json()['events']
            assert all(event['episode_id']==e['episode_id'] for event in events)
            samples=[]
            # A non-running fixture exercises repeatable, idempotent control acknowledgment.
            idle=client.post('/api/campaigns',json={'mode':'baseline','task_text':'Latency fixture','order_id':'order-latency','config_profile_id':'offline-v1'}).json()['campaign_id']
            for _ in range(40):
                began=time.perf_counter();r=client.post(f'/api/campaigns/{idle}/stop',json={});samples.append((time.perf_counter()-began)*1000)
                assert r.status_code==202
            p95=sorted(samples)[37]
            assert p95<250,{'p95_ms':p95,'samples_ms':samples}
            (tmp_path/'control-latency.json').write_text(json.dumps({'source':'actual_loopback_HTTP','control':'POST stop (idempotent, no active fault)','samples_ms':samples,'count':40,'p95_ms':p95,'target_ms':250,'model_calls':0,'episode_id':e['episode_id'],'outcome':e['verdict']['outcome']},indent=2))
    finally:
        server.should_exit=True;thread.join(timeout=8);listener.close()
        assert not thread.is_alive()

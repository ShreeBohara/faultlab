"""Real localhost sockets: in-process ASGI cannot establish timeout semantics."""
import concurrent.futures
import socket
import threading
import time
import httpx
import pytest
import uvicorn
from app.simulator.main import create_app
from app.simulator.storage import WorldStore

pytestmark=pytest.mark.localhost_http

@pytest.fixture
def live_server(tmp_path):
    listener=socket.socket();listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    app=create_app(database_dir=tmp_path,control_token='test-control')
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True);thread.start()
    until=time.monotonic()+5
    while not server.started and time.monotonic()<until:time.sleep(.01)
    assert server.started
    yield httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=1,trust_env=False),app
    server.should_exit=True;thread.join(timeout=6);listener.close()
    assert not thread.is_alive()

def setup(client,intent,primitives):
    c={'X-FaultLab-Control':'test-control'}
    r=client.post('/control/worlds',json={'episode_id':'episode-1','intent':intent.model_dump(mode='json'),'fault_spec':{'seed':7,'primitives':primitives}},headers=c)
    assert r.status_code==201,r.text
    w=r.json();h={'X-FaultLab-World':w['world_id'],'X-FaultLab-Capability':w['capability'],'X-FaultLab-Call':'call-1','X-FaultLab-Attempt':'attempt-1'}
    return w,h,c

def fault(kind,tool='update_order',occurrence=1,**params):
    return {'kind':kind,'target_tool':tool,'target_service':'notifications' if tool=='send_confirmation' else 'orders','occurrence':occurrence,'parameters':params}

def test_post_commit_timeout_releases_transaction_and_survives_disconnect(live_server,intent,upgrade):
    c,app=live_server;w,h,ctrl=setup(c,intent,[fault('F1',response_delay_ms=1500)])
    with pytest.raises(httpx.ReadTimeout):c.post('/business/orders/order-1/upgrade',json=upgrade,headers=h)
    r=c.get('/business/operations/orders/upgrade-1',headers=h)
    assert r.json()['status']=='SUCCEEDED'
    assert c.post('/business/orders/order-1/upgrade',json=upgrade,headers=h).status_code==200
    state=app.state.store.snapshot(w['world_id']);assert state.orders[0].version==2
    records=c.get('/control/worlds/'+w['world_id']+'/faults',headers=ctrl).json()
    assert records[0]['triggered'] and records[0]['attempt_id']=='attempt-1'
    # A new store instance recovers the committed effect after the timed-out socket.
    recovered=WorldStore(app.state.store.directory).snapshot(w['world_id'])
    assert recovered.operations[0].receipt==state.operations[0].receipt

@pytest.mark.parametrize('terminal',['SUCCEEDED','FAILED'])
def test_delayed_success_and_rejection_use_logical_ticks(live_server,intent,upgrade,terminal):
    c,app=live_server;w,h,ctrl=setup(c,intent,[fault('F2',completion_delay_ticks=3,terminal_status=terminal,failure_code='UPGRADE_REJECTED' if terminal=='FAILED' else None)])
    assert c.post('/business/orders/order-1/upgrade',json=upgrade,headers=h).json()['status']=='PENDING'
    time.sleep(.02)
    assert app.state.store.snapshot(w['world_id']).tick==1
    assert c.get('/business/operations/orders/upgrade-1',headers=h).json()['status']=='PENDING'
    c.post('/control/worlds/'+w['world_id']+'/advance',json={'ticks':1},headers=ctrl)
    assert c.get('/business/operations/orders/upgrade-1',headers=h).json()['status']==terminal
    assert app.state.store.snapshot(w['world_id']).orders[0].version==(2 if terminal=='SUCCEEDED' else 1)

def test_pre_effect_fault_precedes_delay_and_lost_response(live_server,intent,upgrade):
    c,app=live_server;w,h,ctrl=setup(c,intent,[fault('F4',failure_count=1),fault('F1',response_delay_ms=1500)])
    r=c.post('/business/orders/order-1/upgrade',json=upgrade,headers=h)
    assert r.status_code==503 and app.state.store.snapshot(w['world_id']).operations==[]
    records=c.get('/control/worlds/'+w['world_id']+'/faults',headers=ctrl).json()
    assert records[0]['triggered'] and not records[1]['triggered'] and records[1]['reason']=='pre_effect_failure'
    assert c.post('/business/orders/order-1/upgrade',json=upgrade,headers=h).status_code==200

def test_f1_cannot_claim_lost_commit_for_pending_acceptance(live_server,intent,upgrade):
    c,app=live_server;w,h,ctrl=setup(c,intent,[fault('F2',completion_delay_ticks=3,terminal_status='SUCCEEDED',failure_code=None),fault('F1',response_delay_ms=1500)])
    assert c.post('/business/orders/order-1/upgrade',json=upgrade,headers=h).status_code==202
    records=c.get('/control/worlds/'+w['world_id']+'/faults',headers=ctrl).json()
    assert records[0]['triggered'] and not records[1]['triggered']

def test_concurrent_identical_requests_have_one_commit(live_server,intent,upgrade):
    c,app=live_server;w,h,ctrl=setup(c,intent,[])
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda n:c.post('/business/orders/order-1/upgrade',json=upgrade,headers=h|{'X-FaultLab-Attempt':f'attempt-{n}'}),range(4)))
    assert all(r.status_code==200 for r in results)
    state=app.state.store.snapshot(w['world_id'])
    assert state.orders[0].version==2 and len(state.operations)==1 and state.tick==4

def test_real_diagnostic_witness_and_available_status_control(live_server,intent):
    from app.referee.diagnostics import execute_witness,validate_gap
    c,app=live_server;ctrl={'X-FaultLab-Control':'test-control'}
    witnesses=[]
    for committed in (True,False):
        handle=c.post('/control/diagnostics/worlds',json={'episode_id':'diagnostic-'+str(committed),'intent':intent.model_dump(mode='json'),'profile_id':'evidence_gap_v1','committed':committed},headers=ctrl).json()
        witnesses.append(execute_witness(c,handle,intent,control_token='test-control',profile_id='evidence_gap_v1'))
    assert validate_gap(*witnesses).kind=='CONTRACT_EVIDENCE_GAP'
    assert witnesses[0]['private_committed'] and not witnesses[1]['private_committed']
    controls=[]
    for committed in (True,False):
        handle=c.post('/control/diagnostics/worlds',json={'episode_id':'control-'+str(committed),'intent':intent.model_dump(mode='json'),'profile_id':'available_status_v1','committed':committed},headers=ctrl).json()
        controls.append(execute_witness(c,handle,intent,control_token='test-control',profile_id='available_status_v1'))
    assert controls[0]['transcript'][1]['result']['status']=='SUCCEEDED'
    assert controls[1]['transcript'][1]['result']['status']=='UNKNOWN'
    assert validate_gap(*controls).kind=='INCONCLUSIVE'

from app.contracts.models import ToolResult

CTRL={'X-FaultLab-Control':'test-control'}

def snap(client,handle):
    return client.get('/control/worlds/'+handle['world_id']+'/snapshot',headers=CTRL).json()

def test_normal_upgrade_confirmation_replay(make_world,upgrade,notification):
    c,w,h=make_world()
    r=c.post('/business/orders/order-1/upgrade',json=upgrade,headers=h)
    assert r.status_code==200 and ToolResult.model_validate(r.json()).status=='SUCCEEDED'
    assert r.json()['data']['receipt']['committed_version']==2
    assert c.post('/business/orders/order-1/upgrade',json=upgrade,headers=h).json()==r.json()
    sent=c.post('/business/notifications',json=notification,headers=h)
    assert sent.status_code==201
    assert c.post('/business/notifications',json=notification,headers=h).status_code==200
    state=snap(c,w)
    assert state['orders'][0]['version']==2 and len(state['notifications'])==1
    assert len(state['operations'])==2

def test_changed_payload_conflicts_without_effect(make_world,upgrade):
    c,w,h=make_world();c.post('/business/orders/order-1/upgrade',json=upgrade,headers=h)
    changed=upgrade|{'expected_version':2}
    r=c.post('/business/orders/order-1/upgrade',json=changed,headers=h)
    assert r.status_code==409 and r.json()['error_code']=='IDEMPOTENCY_CONFLICT'
    assert snap(c,w)['orders'][0]['version']==2

def test_pending_and_terminal_failure(make_world,upgrade):
    f=dict(kind='F2',target_tool='update_order',target_service='orders',occurrence=1,parameters={'completion_delay_ticks':3,'terminal_status':'FAILED','failure_code':'UPGRADE_REJECTED'})
    c,w,h=make_world([f]);r=c.post('/business/orders/order-1/upgrade',json=upgrade,headers=h)
    assert r.status_code==202 and r.json()['status']=='PENDING' and r.json()['receipt_id'] is None
    state=snap(c,w);assert state['orders'][0]['applied_shipping']=='standard' and state['orders'][0]['requested_shipping']=='express'
    c.post('/control/worlds/'+w['world_id']+'/advance',json={'ticks':3},headers=CTRL)
    r=c.get('/business/operations/orders/upgrade-1',headers=h)
    assert r.json()['status']=='FAILED'
    c.post('/control/worlds/'+w['world_id']+'/stop',json={},headers=CTRL)
    c.post('/control/worlds/'+w['world_id']+'/advance',json={'ticks':5,'observer':True},headers=CTRL)
    assert snap(c,w)['orders'][0]['version']==1

def test_unknown_and_premature_notification_are_observable(make_world,notification):
    c,w,h=make_world()
    assert c.get('/business/operations/orders/upgrade-1',headers=h).json()['status']=='UNKNOWN'
    assert c.post('/business/notifications',json=notification,headers=h).status_code==201
    assert len(snap(c,w)['notifications'])==1

def test_private_authority_and_identity(make_world,upgrade):
    c,w,h=make_world()
    assert c.get('/control/worlds/'+w['world_id']+'/snapshot').status_code==403
    assert c.get('/business/orders/order-1',headers=h|{'X-FaultLab-Capability':'wrong'}).status_code==403
    assert c.post('/business/orders/order-other/upgrade',json=upgrade,headers=h).status_code==409
    assert snap(c,w)['operations']==[]

def test_stop_and_tick_budget_prevent_dispatch(make_world):
    c,w,h=make_world()
    for n in range(18): assert c.get('/business/orders/order-1',headers=h).status_code==200
    assert c.get('/business/orders/order-1',headers=h).status_code==429
    assert snap(c,w)['tick']==18
    c.post('/control/worlds/'+w['world_id']+'/stop',json={},headers=CTRL)
    assert c.get('/business/orders/order-1',headers=h).status_code==409

def test_stale_history_is_genuine_and_missing_history_rejected(make_world,intent):
    f={'kind':'F3','target_tool':'get_order','target_service':'orders','occurrence':1,'parameters':{'versions_back':2}}
    intent.expected_version=4
    c,w,h=make_world([f],fixture_id='history-v1')
    response=c.get('/business/orders/order-1',headers=h).json()
    assert response['data']['version']==2 and response['data']['applied_shipping']=='standard'
    assert snap(c,w)['orders'][0]['version']==4
    intent.expected_version=1
    rejected=c.post('/control/worlds',headers=CTRL,json={'episode_id':'ep-other','intent':intent.model_dump(mode='json'),'fault_spec':{'seed':1,'primitives':[f]}})
    assert rejected.status_code==422

def test_observer_requires_stop_and_exactly_one_five_tick_horizon(make_world):
    c,w,h=make_world();path='/control/worlds/'+w['world_id']
    assert c.post(path+'/advance',json={'ticks':5,'observer':True},headers=CTRL).status_code==409
    c.get('/business/orders/order-1',headers=h)
    c.post(path+'/stop',json={},headers=CTRL)
    assert c.post(path+'/advance',json={'ticks':4,'observer':True},headers=CTRL).status_code==409
    assert c.post(path+'/advance',json={'ticks':5,'observer':True},headers=CTRL).json()['tick']==6
    assert c.post(path+'/advance',json={'ticks':5,'observer':True},headers=CTRL).status_code==409
    assert c.get('/business/orders/order-1',headers=h).status_code==409

def test_sql_history_is_immutable_and_worlds_are_isolated(make_world,upgrade):
    import sqlite3
    import pytest
    c,a,h=make_world();c.post('/business/orders/order-1/upgrade',json=upgrade,headers=h)
    _,b,_=make_world()
    assert snap(c,b)['orders'][0]['version']==1
    path=c.app.state.store.directory/(a['world_id']+'.sqlite3')
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError):db.execute('UPDATE receipts SET value=?',('{}',))
        with pytest.raises(sqlite3.IntegrityError):db.execute('DELETE FROM projections')

def test_delayed_commit_detects_intervening_version_conflict(make_world,upgrade):
    f={'kind':'F2','target_tool':'update_order','target_service':'orders','occurrence':1,'parameters':{'completion_delay_ticks':2,'terminal_status':'SUCCEEDED','failure_code':None}}
    c,w,h=make_world([f]);c.post('/business/orders/order-1/upgrade',json=upgrade,headers=h)
    with c.app.state.store.transaction(w['world_id']) as state:
        state['order']['version']=2
    c.post('/control/worlds/'+w['world_id']+'/advance',json={'ticks':2},headers=CTRL)
    r=c.get('/business/operations/orders/upgrade-1',headers=h).json()
    assert r['status']=='FAILED' and r['data']['receipt']['failure_code']=='VERSION_CONFLICT'
    assert snap(c,w)['orders'][0]['applied_shipping']=='standard'

def test_due_completion_precedes_same_tick_public_action(make_world,upgrade,notification):
    f={'kind':'F2','target_tool':'update_order','target_service':'orders','occurrence':1,'parameters':{'completion_delay_ticks':1,'terminal_status':'SUCCEEDED','failure_code':None}}
    c,w,h=make_world([f]);c.post('/business/orders/order-1/upgrade',json=upgrade,headers=h)
    c.post('/business/notifications',json=notification,headers=h)
    events=snap(c,w)['events'];commit=next(e for e in events if e['type']=='upgrade_committed');notice=next(e for e in events if e['type']=='notification_committed')
    assert commit['tick']==notice['tick']==2 and commit['seq']<notice['seq']

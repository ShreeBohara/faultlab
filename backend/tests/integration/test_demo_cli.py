"""The operator's wait follows automatic learning after a rejected candidate."""
from app.cli import client


def test_demo_wait_retains_campaign_until_learning_and_finalization_finish(monkeypatch):
    states=iter(['REJECTED','DISCOVERING','NO_CHANGE','NO_CHANGE'])
    active=iter(['campaign-fixture','campaign-fixture',None])
    observed=[]
    def request(method,path,body=None):
        observed.append((method,path))
        if path=='/api/campaigns':return {'campaign_id':'campaign-fixture'}
        if path.endswith('/start'):return {'state':'DISCOVERING'}
        if path=='/api/config/status':return {'active_campaign_id':next(active)}
        return {'campaign_id':'campaign-fixture','state':next(states)}
    monkeypatch.setattr('sys.argv',['client','demo','--mode','learn','--execute-live','--wait'])
    monkeypatch.setattr(client,'request',request)
    monkeypatch.setattr(client.time,'sleep',lambda _:None)
    assert client.main()==0
    assert observed.count(('GET','/api/campaigns/campaign-fixture'))==4
    assert observed.count(('POST','/api/campaigns/campaign-fixture/start'))==1

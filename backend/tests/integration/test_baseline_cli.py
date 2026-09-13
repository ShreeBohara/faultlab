"""Operator command authorization and read-only status; no provider transport."""
import pytest
from app.cli import client


def test_baseline_command_requires_explicit_execution_before_any_request(monkeypatch):
    monkeypatch.setattr('sys.argv',['client','baseline-study'])
    monkeypatch.setattr(client,'request',lambda *a,**k:pytest.fail('No request before explicit execution'))
    with pytest.raises(SystemExit) as error:client.main()
    assert error.value.code==2


def test_baseline_status_only_reads_and_does_not_create_campaign(monkeypatch):
    calls=[]
    def request(*args):calls.append(args);return {'study_id':'baseline-fixture','status':'COMPLETED'}
    monkeypatch.setattr('sys.argv',['client','baseline-study','--status','baseline-fixture'])
    monkeypatch.setattr(client,'request',request)
    assert client.main()==0
    assert calls==[('GET','/api/baseline-studies/baseline-fixture')]


def test_baseline_execution_uses_study_route_without_healthy_start(monkeypatch):
    calls=[]
    def request(*args):
        calls.append(args)
        return {'campaign_id':'campaign-fixture'} if args[1]=='/api/campaigns' else {'study_id':'baseline-fixture','status':'QUEUED'}
    monkeypatch.setattr('sys.argv',['client','baseline-study','--execute-live'])
    monkeypatch.setattr(client,'request',request)
    assert client.main()==0
    assert len(calls)==2
    assert calls[0][2]['config_profile_id']=='live-v1'
    assert calls[1]==('POST','/api/campaigns/campaign-fixture/baseline-study',{'execute_live':True})

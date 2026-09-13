"""Operator capture is attributed evidence; fake links never verify a sponsor gate."""
from datetime import datetime,timezone
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.lab.coordinator import LabCoordinator
from app.contracts.models import CampaignRequest


def capture(**changes):
    return {'run_id':'run-observed','automation_id':'automation-observed','invocation_mode':'automatic','provenance':'manual_ui_capture',
        'status':'COMPLETED','execution_id':'execution-observed','observed_at':datetime.now(timezone.utc).isoformat(),
        'thread_id':'thread-observed','history_url':'https://wandb.ai/team/project/automations/observed',
        'output_url':'https://wandb.ai/team/project/reports/observed','summary':'Operator-observed advisory analysis.','recorder':'local-test-fixture',**changes}


def test_aria_requires_registered_run_and_keeps_capture_attributed(tmp_path):
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path)))
    campaign=c.create(CampaignRequest(mode='baseline',task_text='Test',order_id='order-one',config_profile_id='offline-v1'))
    ident=campaign.campaign_id; path=f'/api/campaigns/{ident}/aria-evidence'
    with TestClient(create_app(coordinator=c)) as client:
        assert client.post(path,json=capture()).status_code==422
        c.store.put_record('aria_bindings',ident,{'campaign_id':ident,'run_id':'run-observed','automation_id':'automation-observed','verified_source_refs':[]},immutable=True)
        assert client.post(path,json=capture(output_url='https://example.com/pretend-report')).status_code==422
        assert client.post(path,json=capture(invocation_mode='manual')).status_code==422
        assert client.post(path,json=capture(execution_id=None)).status_code==422
        assert client.post(path,json=capture(history_url=None)).status_code==422
        before=c.policies.list()
        response=client.post(path,json=capture())
        assert response.status_code==201,response.text
        assert response.json()['provenance']=='manual_ui_capture'
        check=c.store.get_record('aria_capture_checks',response.json()['analysis_id'])
        assert check['remote_verification'] is False
        assert c.policies.list()==before
        assert c.store.list_records('episodes')==[]
        assert c.store.list_records('regression_executions')==[]
        assert client.get(path).status_code==200

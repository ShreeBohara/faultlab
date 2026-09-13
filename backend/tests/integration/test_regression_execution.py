"""CLI/API integration for portable data; no fixture satisfies live transfer."""
import json
import sys
from fastapi.testclient import TestClient
from app.config import Settings
from app.contracts.models import CampaignRequest,Counterexample,FaultSpec,content_hash
from app.lab.coordinator import LabCoordinator
from app.lab.regressions import RegressionCompiler
from app.integrations.registry import AgentRegistry
from app.main import create_app
from app.cli import regressions


def build_bundle(c,directory):
    campaign=c.create(CampaignRequest(mode='baseline',task_text='Upgrade and confirm',order_id='order-bundle',config_profile_id='offline-v1'))
    recipe=FaultSpec(seed=1,primitives=[])
    counter=Counterexample(counterexample_id='fixture-counter',campaign_id=campaign.campaign_id,agent_registration_id='orders-v1',source_episode_id='fixture-source',target_invariant='C3',scenario_hash=content_hash(recipe),configuration_hash=campaign.configuration_hash,report_ref=None,verdict_ref='fixture-verdict')
    c.store.put_record('private_episode_inputs',counter.source_episode_id,{'fixture_id':'standard-v1'},immutable=True)
    compiler=RegressionCompiler(c.store)
    bundle=compiler.compile(campaign,counter,c.policies.baseline(),recipe,recipe,[])
    compiler.export(bundle.bundle_id,directory)
    return campaign,bundle


def test_cli_validates_and_plays_data_with_zero_executions(tmp_path,monkeypatch,capsys):
    settings=Settings(faultlab_artifact_dir=str(tmp_path/'lab'))
    c=LabCoordinator(settings);directory=tmp_path/'bundle'
    campaign,bundle=build_bundle(c,directory)
    monkeypatch.setattr(regressions.Settings,'from_env',lambda:settings)
    for command in ('validate','playback'):
        monkeypatch.setattr(sys,'argv',['faultlab',command,'--bundle',str(directory)])
        assert regressions.main()==0
        result=json.loads(capsys.readouterr().out)
        execution=result.get('execution',result)
        assert execution['mode'] in ('VALIDATE_ONLY','RECORDED_PLAYBACK')
        assert execution['episode_ids']==execution['world_ids']==[]
        assert execution['usage']['http_attempts']==execution['usage']['model_calls']==0
    monkeypatch.setattr(sys,'argv',['faultlab','execute','--bundle',str(directory),'--agent','missing','--profile','sandbox-v1'])
    assert regressions.main()==1
    assert c.store.list_records('episodes')==[]
    assert all(row['mode']!='FRESH_SANDBOX' for row in c.store.list_records('regression_executions'))
    c.store.close()


def test_api_preserves_bundle_and_denies_unconfigured_fresh_run(tmp_path):
    settings=Settings(faultlab_artifact_dir=str(tmp_path/'lab'))
    c=LabCoordinator(settings);campaign,bundle=build_bundle(c,tmp_path/'bundle')
    regression=c.store.list_records('regressions')[0]
    registration=AgentRegistry(c.store).register_reference(c.store.get_record('configurations',campaign.configuration_hash),internal_smoke=True)
    with TestClient(create_app(coordinator=c)) as client:
        response=client.get(f'/api/regressions/{regression["regression_id"]}/bundle')
        assert response.status_code==200 and response.json()['manifest_hash']==bundle.manifest_hash
        response=client.post(f'/api/regressions/{regression["regression_id"]}/execute',json={'agent_registration_id':registration.registration_id,'execution_profile_id':'sandbox-v1','policy_version':'policy-v0','execute_live':True})
        assert response.status_code==503,response.text
        assert c.store.list_records('episodes')==[]
        assert c.active_id is None

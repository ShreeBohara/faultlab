import json
import pytest
from app.config import Settings
from app.contracts.models import CampaignRequest,Counterexample,FaultSpec,TrialResult,ChallengeResult,canonical_json,content_hash
from app.lab.coordinator import LabCoordinator
from app.lab.regressions import RegressionCompiler,runnable_policy,artifact_kind
from app.lab.exports import development_recording
from app.integrations.regression_runner import inspect_bundle,LEGACY_SCHEMA_HASH
from app.cli.regressions import compile_incident
from test_evidence import episode


def incident(tmp_path):
    settings=Settings(faultlab_artifact_dir=str(tmp_path/'lab'))
    c=LabCoordinator(settings)
    campaign=c.create(CampaignRequest(task_text='Upgrade and confirm',order_id='order-incident',mode='baseline'))
    recipe=FaultSpec.model_validate_json('{"seed":42,"primitives":[{"kind":"F1","target_tool":"update_order","target_service":"orders","occurrence":1,"parameters":{"response_delay_ms":1500}}]}')
    source=episode(c,campaign,purpose='discovery'); source.scenario_hash=content_hash(recipe); c.store.put_record('episodes',source.episode_id,source)
    c.store.put_record('private_episode_inputs',source.episode_id,{'fixture_id':'standard-v1','intent':{'task_text':campaign.task_text,'order_id':campaign.order_id},'recipe':recipe.model_dump(mode='json')})
    trial=TrialResult(episode_id=source.episode_id,world_id=source.world_id,scenario_hash=content_hash(recipe),policy_hash=source.policy_hash,arm='B0',trial_index=0,lifecycle='COMPLETED',outcome='VIOLATION',failed_checks=['C3'],fault_scheduled=True,fault_triggered=True)
    c.store.put_record('trials',trial.episode_id,trial)
    counter=Counterexample(counterexample_id='counter-source',campaign_id=campaign.campaign_id,agent_registration_id='orders-v1',source_episode_id=source.episode_id,target_invariant='C3',scenario_hash=content_hash(recipe),configuration_hash=campaign.configuration_hash,report_ref=source.episode_id,verdict_ref='verdict-source',reproduced=True,reproduction_trial_ids=[source.episode_id],valid_count=3,attempted_count=3,target_violation_count=3)
    c.store.put_record('counterexamples',counter.counterexample_id,counter)
    c.store.put_record('counterexample_recipes',counter.counterexample_id,{'source_recipe':recipe.model_dump(mode='json'),'fixture_id':'standard-v1'})
    return c,settings,campaign,counter,recipe,source,trial


def test_reproduced_incident_is_exportable_before_diagnosis_or_acceptance(tmp_path):
    c,settings,campaign,counter,recipe,source,trial=incident(tmp_path)
    protected=episode(c,campaign,purpose='promotion')
    protected_trial=trial.model_copy(update={'episode_id':protected.episode_id,'world_id':protected.world_id})
    for n in range(205): c.store.append_event(source.episode_id,type='observed',payload={'index':n})
    c.store.append_event(source.episode_id,type='hidden',visibility='PRIVATE_EVALUATOR',payload={'secret':'never export'})
    c.store.append_event(protected.episode_id,type='hidden_promotion',payload={'hidden_fixture':'sealed'})
    rejected=c.policies.baseline().model_copy(update={'version':'policy-rejected','decision':'REJECTED','author':'mechanic','development_episode_ids':[source.episode_id],'raw_proposal_ref':'raw-rejected'})
    c.policies.save(rejected); c.store.put_record('proposals','raw-rejected',{'raw':'original rejected proposal','parent_version':'policy-v0'})
    c.store.put_record('campaign_proposals','invalid',{'campaign_id':campaign.campaign_id,'proposal_ref':'invalid','raw_outputs':['invalid first','invalid corrected'],'reason':'INVALID_MECHANIC_OUTPUT'})
    c.store.put_record('campaign_proposals','foreign',{'campaign_id':'other','raw_outputs':['another campaign']})
    compiler=RegressionCompiler(c.store)
    bundle=compiler.compile(campaign,counter,c.policies.baseline(),recipe,None,[trial,protected_trial],stage='reduced_source',artifact_kind='incident_fixture')
    path=compiler.export(bundle.bundle_id,tmp_path/'incident')
    checked=inspect_bundle(path.parent)
    recording=json.loads((path.parent/'evidence.json').read_text())
    assert checked.bundle.artifact_kind=='incident_fixture'
    assert checked.bundle.harness_version=='faultlab-runner-v2'
    assert [e['episode_id'] for e in recording['episodes']]==[source.episode_id]
    assert len(recording['events'][source.episode_id])==205
    assert len(recording['campaign_proposals'])==1
    assert recording['proposals'][0]['raw']=='original rejected proposal'
    assert 'policy-rejected' in [p['version'] for p in recording['policies']]
    assert 'hidden_fixture' not in (path.parent/'evidence.json').read_text()
    row=c.store.list_records('regressions')[-1]
    assert row['accepted_policy'] is None and row['artifact_kind']=='incident_fixture'
    assert len(c.store.list_records('episodes'))==2


def test_failed_challenge_exports_its_actual_recipe_and_rejected_policy(tmp_path):
    c,settings,campaign,counter,recipe,source,trial=incident(tmp_path)
    candidate=c.policies.baseline().model_copy(update={'version':'policy-rejected','parent_version':'policy-v0','decision':'REJECTED','author':'mechanic','development_episode_ids':[source.episode_id]})
    c.policies.save(candidate)
    changed=recipe.model_copy(update={'seed':99})
    failed=episode(c,campaign,purpose='challenge'); failed.policy_version=candidate.version; failed.scenario_hash=content_hash(changed); c.store.put_record('episodes',failed.episode_id,failed)
    c.store.put_record('private_episode_inputs',failed.episode_id,{'fixture_id':'standard-v1'})
    failed_trial=trial.model_copy(update={'episode_id':failed.episode_id,'world_id':failed.world_id,'scenario_hash':content_hash(changed),'failed_checks':['C5']})
    c.store.put_record('trials',failed_trial.episode_id,failed_trial)
    c.store.put_record('challenge_counterexamples',candidate.version,{'campaign_id':campaign.campaign_id,'candidate_hash':candidate.policy_hash,'recipe':changed.model_dump(mode='json'),'fixture_id':'standard-v1','trial_ids':[failed.episode_id],'failed_checks':['C5']})
    challenge=ChallengeResult(challenge_id='challenge-failed',candidate_hash=candidate.policy_hash,incumbent_hash=trial.policy_hash,source_validation_ref='source-batch',schedule_hashes=[content_hash(changed)],selection_refs=[],novel_schedule_hashes=[content_hash(changed)],trial_pairs=[(source.episode_id,failed.episode_id)],failed_checks=['C5'],status='COUNTEREXAMPLE_FOUND',stopping_reason='Candidate broke C5')
    compiler=RegressionCompiler(c.store)
    bundle=compiler.compile(campaign,counter,candidate,recipe,recipe,[trial,failed_trial],challenge=challenge,stage='failed_challenge',artifact_kind='candidate_comparison')
    checked=inspect_bundle(compiler.export(bundle.bundle_id,tmp_path/'failed').parent)
    assert checked.bundle.source_recipe==changed and checked.bundle.retained_recipe is None
    assert checked.bundle.target_invariant=='C5'
    assert runnable_policy(checked.bundle,checked.policy)=='candidate_comparison'
    assert checked.policy.decision=='REJECTED'
    assert c.store.list_records('regressions')[-1]['first_failing_policy']==candidate.version
    assert c.store.list_records('regressions')[-1]['accepted_policy'] is None
    with pytest.raises(ValueError,match='Acceptance'):
        compiler.compile(campaign,counter,candidate,recipe,None,[trial],artifact_kind='accepted_policy_bundle')


def test_legacy_v1_manifest_without_kind_keeps_its_digest_and_acceptance_label(tmp_path):
    c,settings,campaign,counter,recipe,source,trial=incident(tmp_path)
    accepted=c.policies.baseline().model_copy(update={'version':'policy-old','decision':'ACCEPTED'})
    compiler=RegressionCompiler(c.store)
    bundle=compiler.compile(campaign,counter,accepted,recipe,None,[trial])
    directory=compiler.export(bundle.bundle_id,tmp_path/'legacy').parent
    manifest=json.loads((directory/'manifest.json').read_text())
    manifest.pop('artifact_kind'); manifest['harness_version']='faultlab-runner-v1'; manifest['schema_hash']=LEGACY_SCHEMA_HASH
    manifest['files']=[f for f in manifest['files'] if f['path']!='evidence.json']; (directory/'evidence.json').unlink()
    manifest['manifest_hash']=content_hash({k:v for k,v in manifest.items() if k!='manifest_hash'})
    (directory/'manifest.json').write_text(canonical_json(manifest))
    checked=inspect_bundle(directory)
    assert checked.bundle.manifest_hash==manifest['manifest_hash']
    assert artifact_kind(checked.bundle,checked.policy)=='accepted_policy_bundle'
    assert 'artifact_kind' not in checked.bundle.model_fields_set


def test_configured_secret_blocks_recording_without_partial_bundle(tmp_path):
    c,settings,campaign,counter,recipe,source,trial=incident(tmp_path)
    c.store.append_event(source.episode_id,type='bad_record',payload={'text':'synthetic-credential'})
    with pytest.raises(Exception,match='Secret-bearing'):
        RegressionCompiler(c.store,secrets=('synthetic-credential',)).compile(campaign,counter,c.policies.baseline(),recipe,None,[trial])
    assert c.store.list_records('bundles')==[]


def test_existing_counterexample_compilation_does_not_execute_and_retains_task(tmp_path):
    c,settings,campaign,counter,recipe,source,trial=incident(tmp_path)
    before=len(c.store.list_records('episodes'))
    bundle=compile_incident(c.store,settings,counter.counterexample_id)
    assert bundle.artifact_kind=='incident_fixture'
    data=json.loads(c.store.get_record('bundle_files',bundle.bundle_id)['evidence.json'])
    assert data['execution_task']=={'task_text':campaign.task_text,'order_id':campaign.order_id}
    assert len(c.store.list_records('episodes'))==before
    assert c.store.list_records('regression_executions')==[]


def test_campaign_cli_export_gets_complete_public_timeline_and_all_owned_policies(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.cli import client
    c,settings,campaign,counter,recipe,source,trial=incident(tmp_path)
    for n in range(203): c.store.append_event(source.episode_id,type='observed',payload={'index':n})
    c.store.append_event(source.episode_id,type='private',visibility='PRIVATE_EVALUATOR',payload={'secret':'withheld'})
    rejected=c.policies.rejected_raw('not a valid policy','policy-v0','INVALID_MECHANIC_OUTPUT')
    c.store.put_record('campaign_proposals','invalid',{'campaign_id':campaign.campaign_id,'proposal_ref':'invalid','raw_outputs':['not a valid policy'],'candidate_version':rejected.version})
    output=tmp_path/'campaign.json'; reads=[]
    with TestClient(create_app(coordinator=c)) as api:
        def get(method,path,body=None):
            assert method=='GET' and body is None; reads.append(path)
            response=api.get(path); assert response.status_code==200,response.text
            return response.json()
        monkeypatch.setattr(client,'request',get)
        monkeypatch.setattr('sys.argv',['client','export','--campaign',campaign.campaign_id,'--output',str(output)])
        assert client.main()==0
        assert len(c.store.list_records('episodes'))==1
    result=json.loads(output.read_text())
    assert len(result['events'][source.episode_id])==203
    assert rejected.version in [p['version'] for p in result['policies']]
    assert result['proposals'][0]['raw']=='not a valid policy'
    assert '/api/campaigns/'+campaign.campaign_id+'/recording' in reads
    assert 'withheld' not in output.read_text()


def test_legacy_download_preserves_original_manifest_shape(tmp_path):
    import io,zipfile
    from fastapi.testclient import TestClient
    from app.main import create_app
    c,settings,campaign,counter,recipe,source,trial=incident(tmp_path)
    compiler=RegressionCompiler(c.store)
    bundle=compiler.compile(campaign,counter,c.policies.baseline(),recipe,None,[trial])
    raw=bundle.model_dump(mode='json'); raw.pop('artifact_kind'); raw['harness_version']='faultlab-runner-v1'; raw['schema_hash']=LEGACY_SCHEMA_HASH
    raw['bundle_id']='legacy-bundle'; raw['files']=[e for e in raw['files'] if e['path']!='evidence.json']
    raw['manifest_hash']=content_hash({k:v for k,v in raw.items() if k!='manifest_hash'})
    files=c.store.get_record('bundle_files',bundle.bundle_id); files.pop('evidence.json')
    c.store.put_record('bundles',raw['bundle_id'],raw)
    c.store.put_record('bundle_files',raw['bundle_id'],files)
    row=c.store.list_records('regressions')[-1]; row['bundle_id']=raw['bundle_id']; row['regression_id']='legacy-case'
    c.store.put_record('regressions','legacy-case',row)
    with TestClient(create_app(coordinator=c)) as api:
        response=api.get('/api/regressions/legacy-case/download'); assert response.status_code==200
    manifest=json.loads(zipfile.ZipFile(io.BytesIO(response.content)).read('manifest.json'))
    assert manifest==raw and 'artifact_kind' not in manifest

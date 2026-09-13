import json
import pytest
from app.agents.mechanic import Mechanic
from app.agents.explorer import Explorer
from app.lab.storage import LabStore
from app.lab.budgets import CampaignLedger
from app.providers.runtime import RuntimeGeneration

@pytest.fixture
def anyio_backend(): return 'asyncio'

class Provider:
    def __init__(self,outputs): self.outputs=iter(outputs); self.messages=[]
    async def complete(self,messages,**kwargs):
        self.messages.append(messages)
        return RuntimeGeneration(next(self.outputs),'openai/gpt-oss-120b')

@pytest.mark.anyio
async def test_mechanic_all_malformed_stays_rejected_no_canned_policy(tmp_path):
    store=LabStore(tmp_path/'lab.db'); ledger=CampaignLedger(store,'c'); provider=Provider(['bad json','still bad'])
    ref,proposal,raw=await Mechanic(provider,store,ledger).propose({'parent_version':'policy-v0'})
    assert proposal is None and raw==['bad json','still bad'] and ledger.used_calls==2
    assert len(store.list_records('mechanic_outputs'))==2
    assert 'Correct formatting only' in provider.messages[1][-1]['content']

@pytest.mark.anyio
async def test_mechanic_no_change_and_foreign_evidence_rejected(tmp_path):
    store=LabStore(tmp_path/'lab.db'); ledger=CampaignLedger(store,'c')
    invalid=json.dumps({'proposed_kind':'POLICY_GAP','hypothesis':'h','evidence_ids':['foreign'],'requested_intervention_id':'known'})
    provider=Provider(['{"no_change_reason":"No supported repair"}',invalid,invalid])
    mechanic=Mechanic(provider,store,ledger)
    assert (await mechanic.propose({'parent_version':'policy-v0'}))[1].no_change_reason=='No supported repair'
    assert (await mechanic.diagnose({'evidence_ids':['public'],'intervention_ids':['known']}))[1] is None
    assert ledger.used_calls==3

@pytest.mark.anyio
async def test_diagnosis_binding_correction_uses_one_bounded_retry_and_exact_schema(tmp_path):
    from app.contracts.models import DiagnosticProposal
    store=LabStore(tmp_path/'lab.db'); ledger=CampaignLedger(store,'c')
    invalid={'proposed_kind':'POLICY_GAP','hypothesis':'Same falsifiable hypothesis','evidence_ids':['evidence-corrupt'],'requested_intervention_id':'foreign'}
    corrected={**invalid,'evidence_ids':['evidence-exact'],'requested_intervention_id':'intervention-exact'}
    provider=Provider([json.dumps(invalid),json.dumps(corrected)])
    _,result,raws=await Mechanic(provider,store,ledger).diagnose({'evidence_ids':['evidence-exact'],'intervention_ids':['intervention-exact']})
    assert result==DiagnosticProposal.model_validate(corrected)
    assert ledger.used_calls==2 and raws==[json.dumps(invalid),json.dumps(corrected)]
    first=json.loads(provider.messages[0][1]['content'])
    assert first['output_schema']==DiagnosticProposal.model_json_schema()
    feedback=json.loads(provider.messages[1][-1]['content'])
    assert {e['type'] for e in feedback['validation_errors']}=={'unknown_evidence_reference','unknown_intervention_reference'}
    assert len(store.list_records('mechanic_outputs'))==2

@pytest.mark.anyio
async def test_invalid_selector_consumes_slot_and_no_silent_model_repair(tmp_path):
    store=LabStore(tmp_path/'lab.db'); ledger=CampaignLedger(store,'c'); provider=Provider(['not JSON'])
    ref,proposal=await Explorer(provider,store,ledger).select({'selection_index':0})
    assert proposal is None and ledger.used_calls==1
    assert store.get_record('selections',ref)['provenance']=='invalid_slot'

@pytest.mark.anyio
async def test_explorer_receives_exact_public_parameter_schema_within_input_limit(tmp_path):
    from app.contracts.models import ExplorerOutput,EpisodeBudget
    from app.agents.explorer import PUBLIC_INVARIANTS
    from app.contracts.tokens import input_token_bound
    store=LabStore(tmp_path/'lab.db'); ledger=CampaignLedger(store,'c')
    valid={'fault_spec':{'seed':7,'primitives':[{'kind':'F2','target_tool':'update_order','target_service':'orders','occurrence':1,'parameters':{'completion_delay_ticks':3,'terminal_status':'SUCCEEDED','failure_code':None}}]},'hypothesis':'Public schema conformance fixture'}
    provider=Provider([json.dumps(valid),json.dumps(valid)])
    explorer=Explorer(provider,store,ledger)
    original={'selection_index':0}
    _,proposal=await explorer.select(original)
    assert proposal is not None and 'output_schema' not in original
    _,challenge=await explorer.select({'proposal_index':0},challenge=True)
    assert challenge is not None
    for messages in provider.messages:
        supplied=json.loads(messages[-1]['content'])['output_schema']
        assert json.loads(messages[-1]['content'])['episode_limits']==EpisodeBudget().model_dump(mode='json')
        assert json.loads(messages[-1]['content'])['public_invariants']==PUBLIC_INVARIANTS
        assert set(PUBLIC_INVARIANTS)=={f'C{i}' for i in range(1,9)}
        assert supplied==ExplorerOutput.model_json_schema()
        definitions=supplied['$defs']
        assert set(definitions['F2Parameters']['properties'])=={'completion_delay_ticks','terminal_status','failure_code'}
        assert definitions['F1Parameters']['properties']['response_delay_ms']['maximum']==3000
        assert definitions['F3Parameters']['properties']['versions_back']['maximum']==3
        assert definitions['F4Parameters']['properties']['failure_count']['maximum']==18
        assert input_token_bound(messages,'openai/gpt-oss-120b')<=8000

@pytest.mark.anyio
async def test_wrong_parameter_alias_remains_invalid_raw_evidence(tmp_path):
    store=LabStore(tmp_path/'lab.db'); ledger=CampaignLedger(store,'c')
    raw=json.dumps({'fault_spec':{'seed':7,'primitives':[{'kind':'F2','target_tool':'update_order','target_service':'orders','occurrence':1,'parameters':{'delay_ticks':3,'terminal_status':'SUCCEEDED','failure_code':None}}]},'hypothesis':'Preserved invalid field-name fixture'})
    provider=Provider([raw]); reference,proposal=await Explorer(provider,store,ledger).select({'selection_index':0})
    saved=store.get_record('selections',reference)
    assert proposal is None and saved['raw']==raw and saved['error']=='INVALID_EXPLORER_OUTPUT'
    assert saved['provenance']=='invalid_slot' and ledger.used_calls==1 and len(provider.messages)==1

@pytest.mark.anyio
@pytest.mark.parametrize('role',['explorer','mechanic'])
async def test_provider_empty_response_usage_is_preserved_once_without_format_retry(tmp_path,role):
    from app.providers.runtime import RuntimeProviderError
    store=LabStore(tmp_path/'lab.db'); ledger=CampaignLedger(store,'c')
    failure=RuntimeProviderError('RAW PRIVATE SDK MESSAGE MUST NOT BE STORED',code='EMPTY_FINAL_RESPONSE',error_class='ValueError',finish_reason='length',generation=RuntimeGeneration('','openai/gpt-oss-120b',input_tokens=321,output_tokens=2000))
    class FailingProvider:
        calls=0
        async def complete(self,*args,**kwargs): self.calls+=1; raise failure
    provider=FailingProvider(); agent=Explorer(provider,store,ledger) if role=='explorer' else Mechanic(provider,store,ledger)
    with pytest.raises(RuntimeProviderError) as raised:
        if role=='explorer': await agent.select({'campaign_id':'campaign-fixture','selection_index':0})
        else: await agent.propose({'campaign_id':'campaign-fixture','parent_version':'policy-v0'})
    assert raised.value is failure and provider.calls==1
    assert ledger.used_calls==1 and ledger.used_tokens==34000 and ledger.measured_input==321 and ledger.measured_output==2000
    saved=store.list_records('provider_failures')
    assert len(saved)==1 and saved[0]['role']==role
    assert saved[0]['diagnostics']==failure.diagnostics
    assert 'RAW PRIVATE' not in json.dumps(saved)
    assert not store.list_records('selections') and not store.list_records('mechanic_outputs')
    assert ledger.unknown_token_calls==0 and ledger.usage_known


def test_discovery_coverage_preserves_recipe_trigger_order_and_physical_attempts(tmp_path):
    from app.agents.explorer import development_coverage
    from app.contracts.models import FaultSpec,TrialResult,Usage,content_hash
    store=LabStore(tmp_path/'lab.db')
    recipe=FaultSpec.model_validate({'seed':7,'primitives':[
        {'kind':'F2','target_tool':'update_order','target_service':'orders','occurrence':1,'parameters':{'completion_delay_ticks':10,'terminal_status':'SUCCEEDED','failure_code':None}},
        {'kind':'F4','target_tool':'send_confirmation','target_service':'notifications','occurrence':1,'parameters':{'failure_count':3}}]})
    trial=TrialResult(episode_id='episode-own',world_id='world-own',scenario_hash=content_hash(recipe),policy_hash=content_hash('baseline'),arm='B0',trial_index=0,lifecycle='COMPLETED',outcome='VIOLATION',failed_checks=['C5'],fault_scheduled=True,fault_triggered=False,usage=Usage(actor_calls=8,http_attempts=3))
    store.put_record('episodes',trial.episode_id,{'campaign_id':'campaign-own','split':'development','experiment_purpose':'discovery','verdict':{'fault_executions':[{'triggered':True,'call_id':'private-call-reference','reason':None},{'triggered':False,'reason':'target_not_reached'}],'private_truth':'not permitted'},'report':{'private_text':'not permitted'}})
    store.put_record('private_snapshots',trial.episode_id,{'decision':'private business truth'})
    store.put_record('tool_calls','own-1',{'episode_id':trial.episode_id,'tool':'update_order','attempt_ids':['a','b'],'usage':{'private':'not permitted'}})
    store.put_record('tool_calls','own-2',{'episode_id':trial.episode_id,'tool':'get_operation_status','attempt_ids':['c']})
    store.put_record('tool_calls','other',{'episode_id':'episode-foreign','tool':'send_confirmation','attempt_ids':['d']})
    summary=development_coverage(store,'campaign-own',trial,recipe)
    assert summary=={'episode_id':'episode-own','fault_spec':recipe.model_dump(mode='json'),'lifecycle':'COMPLETED','outcome':'VIOLATION','failed_checks':['C5'],'triggered':False,'primitive_triggered':[True,False],'primitive_prevented_reasons':[None,'target_not_reached'],'qualifies_for_repair':False,'http_attempts_by_tool':{'update_order':2,'get_operation_status':1},'actor_calls':8}
    assert 'private' not in json.dumps(summary)
    store.put_record('episodes',trial.episode_id,{'campaign_id':'campaign-own','split':'final_audit','experiment_purpose':'final_audit'})
    with pytest.raises(ValueError,match='discovery coverage'):
        development_coverage(store,'campaign-own',trial,recipe)

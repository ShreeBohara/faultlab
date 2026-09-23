"""Offline selector decisions: no provider calls and no learned-repair claims."""
import json

import pytest

from app.agents.explorer import Explorer,discovery_search_ledger
from app.contracts.models import FaultSpec,canonical_json,content_hash
from app.lab.budgets import CampaignLedger
from app.lab.challenge import schedule_identity
from app.lab.storage import LabStore
from app.providers.runtime import RuntimeGeneration


@pytest.fixture
def anyio_backend(): return 'asyncio'


class RecordedProvider:
    def __init__(self,outputs): self.outputs=iter(outputs); self.messages=[]
    async def complete(self,messages,**kwargs):
        self.messages.append(messages)
        return RuntimeGeneration(next(self.outputs),'openai/gpt-oss-120b',input_tokens=100,output_tokens=50)


def recipe(*,seed=1,count=1,occurrence=1,tool='get_operation_status',service='orders'):
    return FaultSpec.model_validate({'seed':seed,'primitives':[{'kind':'F4','target_tool':tool,
        'target_service':service,'occurrence':occurrence,'parameters':{'failure_count':count}}]})


def proposal(value): return canonical_json({'fault_spec':value,'hypothesis':'Offline original selection'})


def fixture(tmp_path,outputs):
    store=LabStore(tmp_path/'lab.db'); ledger=CampaignLedger(store,'campaign-own')
    context={'campaign_id':'campaign-own','configuration_hash':content_hash('configuration'),
             'policy_hash':content_hash('policy'),'selection_index':0,'development_history':[]}
    store.put_record('campaigns','campaign-own',{'configuration_hash':context['configuration_hash']})
    provider=RecordedProvider(outputs)
    return store,ledger,provider,Explorer(provider,store,ledger),context


def observed(store,context,value,*,episode_id='episode-first'):
    store.put_record('episodes',episode_id,{**{key:context[key] for key in ('campaign_id','configuration_hash','policy_hash')},
        'split':'development','experiment_purpose':'discovery','scenario_hash':content_hash(value),
        'study_id':context['campaign_id'],'evidence_context_id':context['campaign_id'],'selector_id':None})
    return {'episode_id':episode_id,'fault_spec':value.model_dump(mode='json'),'lifecycle':'COMPLETED',
            'outcome':'COMPLETED','triggered':False,'primitive_triggered':[False],
            'primitive_prevented_reasons':['target_not_reached']}


@pytest.mark.anyio
async def test_seed_only_duplicate_is_retained_and_charged_without_actor_or_fallback(tmp_path):
    first=recipe(); duplicate=recipe(seed=2); different=recipe(count=2)
    raws=[proposal(first),proposal(duplicate),proposal(different)]
    store,ledger,provider,explorer,context=fixture(tmp_path,raws)
    first_ref,selected=await explorer.select(context)
    assert selected.fault_spec==first
    history=[observed(store,context,first)]
    duplicate_ref,selected=await explorer.select({**context,'selection_index':1,'development_history':history},fallback=different)
    assert selected is None
    saved=store.get_record('selections',duplicate_ref)
    assert saved['raw']==raws[1] and saved['valid'] and saved['provenance']=='model'
    assert saved['output']['fault_spec']==duplicate.model_dump(mode='json') and saved['selected_output'] is None
    assert saved['search_decision']=={'status':'SKIPPED_DUPLICATE','schedule_hash':schedule_identity(first),
        'reason':'DUPLICATE_DISCOVERY_SCHEDULE','prior_selection_refs':[first_ref],'prior_episode_refs':['episode-first']}
    third_ref,selected=await explorer.select({**context,'selection_index':2,'development_history':history})
    assert selected.fault_spec==different
    supplied=json.loads(provider.messages[2][-1]['content'])['search_ledger']
    assert len(supplied['tested_schedules'])==1 and len(supplied['prior_selections'])==2
    assert supplied['prior_selections'][1]['selection_id']==duplicate_ref
    assert supplied['prior_selections'][1]['status']=='SKIPPED_DUPLICATE'
    assert supplied['primitive_coverage']==[{'kind':'F4','target_service':'orders','target_tool':'get_operation_status',
        'scheduled':1,'triggered':0,'not_triggered':1,'unreported':0,'target_not_reached':1}]
    assert ledger.used_calls==3 and ledger.measured_input==300 and len(provider.messages)==3
    assert len(store.list_records('episodes'))==1 and len(store.list_records('selections'))==3
    assert 'search_ledger' not in context


@pytest.mark.anyio
async def test_primitive_order_and_seed_are_duplicates_but_full_behavior_changes_are_not(tmp_path):
    first=recipe()
    first.primitives.append(recipe(tool='send_confirmation',service='notifications',count=2).primitives[0])
    reverse=first.model_copy(deep=True); reverse.seed=8; reverse.primitives.reverse()
    values=[first,reverse,recipe(count=2),recipe(occurrence=2),recipe(service='notifications'),recipe(tool='update_order')]
    store,ledger,provider,explorer,context=fixture(tmp_path,[proposal(value) for value in values])
    for index,value in enumerate(values):
        ref,selected=await explorer.select({**context,'selection_index':index})
        assert (selected is None)==(index==1)
    assert ledger.used_calls==6
    assert sum(row['search_decision']['status']=='SKIPPED_DUPLICATE' for row in store.list_records('selections'))==1


@pytest.mark.anyio
async def test_invalid_fixed_fallback_cannot_repeat_a_schedule_and_raw_stays_invalid(tmp_path):
    first=recipe(); store,ledger,provider,explorer,context=fixture(tmp_path,[proposal(first),'bad JSON'])
    await explorer.select(context)
    ref,result=await explorer.select({**context,'selection_index':1},fallback=first)
    assert result is None
    saved=store.get_record('selections',ref)
    assert saved['raw']=='bad JSON' and saved['error']=='INVALID_EXPLORER_OUTPUT' and not saved['valid']
    assert saved['output'] is None and saved['selected_output'] is None
    assert saved['provenance']=='fixed_invalid_output_fallback'
    assert saved['search_decision']['reason']=='DUPLICATE_DISCOVERY_SCHEDULE'
    assert ledger.used_calls==2 and len(provider.messages)==2


@pytest.mark.anyio
async def test_prior_rejected_invalid_slot_is_feedback_without_invented_trial(tmp_path):
    store,ledger,provider,explorer,context=fixture(tmp_path,['invalid',proposal(recipe())])
    ref,result=await explorer.select(context)
    assert result is None
    await explorer.select({**context,'selection_index':1})
    supplied=json.loads(provider.messages[-1][-1]['content'])['search_ledger']
    assert supplied['prior_selections'][0]['selection_id']==ref
    assert supplied['prior_selections'][0]['status']=='INVALID_OUTPUT'
    assert supplied['tested_schedules']==[] and supplied['excluded_schedule_hashes']==[]


@pytest.mark.anyio
@pytest.mark.parametrize('change',[{'campaign_id':'foreign'}, {'configuration_hash':content_hash('foreign')},
                                  {'policy_hash':content_hash('foreign')}, {'split':'final_audit'},
                                  {'experiment_purpose':'promotion'}, {'scenario_hash':content_hash('foreign')},
                                  {'study_id':'completion-study'}, {'evidence_context_id':'completion-study'},
                                  {'selector_id':'explorer'}])
async def test_mismatched_or_protected_history_rejected_before_model_dispatch(tmp_path,change):
    value=recipe(); store,ledger,provider,explorer,context=fixture(tmp_path,[proposal(value)])
    row=observed(store,context,value)
    original=store.get_record('episodes',row['episode_id'])
    store.put_record('episodes',row['episode_id'],{**original,**change})
    with pytest.raises(ValueError,match='Discovery'):
        await explorer.select({**context,'development_history':[row]})
    assert not provider.messages and ledger.used_calls==0 and not store.list_records('selections')


@pytest.mark.anyio
async def test_wrong_campaign_or_configuration_binding_rejected_before_charge(tmp_path):
    store,ledger,provider,explorer,context=fixture(tmp_path,[proposal(recipe())])
    for change in ({'campaign_id':'another'},{'configuration_hash':content_hash('another')},{'policy_hash':None}):
        with pytest.raises(ValueError,match='Discovery'):
            await explorer.select({**context,**change})
    assert not provider.messages and ledger.used_calls==0


@pytest.mark.anyio
async def test_search_binding_must_match_execution_provenance_before_charge(tmp_path):
    store,ledger,provider,explorer,context=fixture(tmp_path,[proposal(recipe())])
    explorer.metadata={'campaign_id':context['campaign_id'],'policy_hash':content_hash('other-policy')}
    with pytest.raises(ValueError,match='execution metadata'):
        await explorer.select(context)
    assert not provider.messages and ledger.used_calls==0


@pytest.mark.anyio
async def test_foreign_selection_and_challenge_records_are_not_search_feedback(tmp_path):
    value=recipe(); store,ledger,provider,explorer,context=fixture(tmp_path,[proposal(value)]*2)
    ref,_=await explorer.select(context)
    original=store.get_record('selections',ref)
    # A fresh frozen policy may explore the same recipe; other contexts stay private.
    changed={**context,'policy_hash':content_hash('new-policy'),'selection_index':1}
    for index,change in enumerate([{'campaign_id':'foreign'},{'configuration_hash':content_hash('foreign')},
                                   {'study_id':'protected-study'},{'selector_id':'systematic'}]):
        store.put_record('selections',f'selection-foreign-{index}',{**original,'selection_id':f'FOREIGN_CANARY_{index}',
            'context':{**changed,**change}},immutable=True)
    store.put_record('selections','selection-challenge',{**original,'selection_id':'CHALLENGE_CANARY',
        'context':changed,'challenge':True},immutable=True)
    _,selected=await explorer.select(changed)
    assert selected.fault_spec==value
    supplied=provider.messages[-1][-1]['content']
    assert 'CANARY' not in supplied
    assert json.loads(supplied)['search_ledger']['prior_selections']==[]


@pytest.mark.anyio
@pytest.mark.parametrize('context_extra,challenge',[({},True),({'study_id':'study-own','selector_id':'explorer'},False)])
async def test_challenge_and_selector_comparison_keep_their_own_duplicate_rules(tmp_path,context_extra,challenge):
    value=recipe(); store,ledger,provider,explorer,context=fixture(tmp_path,[proposal(value)]*2)
    for index in range(2):
        _,selected=await explorer.select({**context,**context_extra,'selection_index':index},challenge=challenge)
        assert selected.fault_spec==value
        assert 'search_ledger' not in json.loads(provider.messages[-1][-1]['content'])
    assert all(row['search_decision'] is None for row in store.list_records('selections'))


def test_persisted_selected_schedule_cannot_disagree_with_its_digest(tmp_path):
    value=recipe(); store,ledger,provider,explorer,context=fixture(tmp_path,[])
    store.put_record('selections','selection-inconsistent',{'selection_id':'selection-inconsistent','context':context,
        'selected_output':json.loads(proposal(value)),'search_decision':{'status':'SELECTED','schedule_hash':content_hash('wrong')}})
    with pytest.raises(ValueError,match='inconsistent'):
        discovery_search_ledger(store,context,campaign_id=context['campaign_id'])

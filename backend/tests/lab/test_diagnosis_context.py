from types import SimpleNamespace

import pytest

from app.agents.actor import ACTOR_PROMPT
from app.contracts.models import FaultSpec,EpisodeBudget,TrialResult,Usage,content_hash
from app.lab.diagnosis import Diagnostician,trial_outcomes,reduction_context
from app.lab.storage import LabStore
from app.referee.reducer import neighbors


@pytest.fixture
def anyio_backend(): return 'asyncio'


@pytest.mark.anyio
async def test_diagnosis_receives_exact_interventions_and_shared_runtime_contract(tmp_path):
    recipe=FaultSpec.model_validate({'seed':42,'primitives':[{'kind':'F2','target_tool':'update_order','target_service':'orders','occurrence':1,'parameters':{'completion_delay_ticks':5,'terminal_status':'SUCCEEDED','failure_code':None}}]})
    counter=SimpleNamespace(counterexample_id='counter-fixture',target_invariant='C5',attempted_count=3,valid_count=3,target_violation_count=3)
    recorded=[]
    class Mechanic:
        async def diagnose(self,context):
            recorded.append(context)
            return 'no-proposal',None,[]
    class Runner:
        async def run(self,*args,**kwargs): raise AssertionError('No selected intervention permits an execution')
    reduction={'status':'LOCALLY_MINIMAL','trial_outcomes':[{'outcome':'COMPLETED','episode_ids':['healthy-control']}],'verified_episode_ids':['healthy-control']}
    result,_=await Diagnostician(LabStore(tmp_path/'lab.db'),Runner(),None,Mechanic()).run(SimpleNamespace(campaign_id='campaign-fixture'),counter,recipe,None,[],evidence=[],reduction=reduction)
    assert result.kind=='INCONCLUSIVE'
    context=recorded[0]
    assert context['control_fault_spec']==recipe.model_dump(mode='json')
    assert [(v['change'],v['treatment_fault_spec']) for v in context['interventions']]==[(change,treatment.model_dump(mode='json')) for change,treatment in list(neighbors(recipe))[:4]]
    assert context['runtime_contract']['actor_contract']==ACTOR_PROMPT
    assert context['runtime_contract']['episode_limits']==EpisodeBudget().model_dump(mode='json')
    assert context['reduction']==reduction


def test_trial_summary_keeps_every_outcome_and_contradiction():
    def trial(id,outcome='VIOLATION',checks=('C5',)):
        return TrialResult(episode_id=id,world_id='world-'+id,scenario_hash=content_hash('recipe'),policy_hash=content_hash('policy'),arm='B0',trial_index=0,lifecycle='LAB_ERROR' if outcome=='LAB_ERROR' else 'COMPLETED',outcome=outcome,failed_checks=list(checks),fault_scheduled=True,fault_triggered=outcome!='LAB_ERROR',usage=Usage(actor_calls=8,http_attempts=7))
    trials=[trial('a'),trial('b'),trial('c','COMPLETED',()),trial('d','LAB_ERROR',())]
    groups=trial_outcomes(trials)
    assert len(groups)==3 and [v for g in groups for v in g['episode_ids']]==['a','b','c','d']
    assert groups[0]['failed_checks']==['C5'] and groups[1]['failed_checks']==[]
    assert groups[2]['lifecycle']=='LAB_ERROR' and groups[2]['fault_triggered'] is False
    result=SimpleNamespace(model_dump=lambda **_: {'status':'LOCALLY_MINIMAL','attempts':[{'transform':'remove_primitive:0','retained':False,'reason':'TARGET_NOT_REPRODUCED','trial_ids':['c']}],'stopping_reason':'FINITE_NEIGHBORHOOD_EXHAUSTED'})
    summary=reduction_context(result,trials,[SimpleNamespace(episode_id='c',source='weave_verified')])
    assert summary['trial_outcomes']==groups and summary['verified_episode_ids']==['c']
    assert summary['attempts'][0]['trial_ids']==['c']


@pytest.mark.anyio
async def test_diagnosis_options_carry_already_observed_reduction_outcomes(tmp_path):
    recipe=FaultSpec.model_validate({'seed':7,'primitives':[{'kind':'F2','target_tool':'update_order','target_service':'orders','occurrence':1,'parameters':{'completion_delay_ticks':5,'terminal_status':'SUCCEEDED','failure_code':None}}]})
    counter=SimpleNamespace(counterexample_id='counter-fixture',target_invariant='C5',attempted_count=3,valid_count=3,target_violation_count=3)
    remove,delay1,delay2,delay3=[treatment for _,treatment in list(neighbors(recipe))[:4]]
    def group(spec,outcome,checks,ids):
        return {'scenario_hash':content_hash(spec),'arm':'B0','lifecycle':'COMPLETED','outcome':outcome,'failed_checks':list(checks),'fault_scheduled':bool(spec.primitives),'fault_triggered':bool(spec.primitives),'actor_calls':8,'http_attempts':7,'episode_ids':ids}
    reduction={'status':'LOCALLY_MINIMAL','stopping_reason':'FINITE_NEIGHBORHOOD_EXHAUSTED','attempts':[],'verified_episode_ids':[],
               'trial_outcomes':[group(recipe,'VIOLATION',['C5','C6','C7'],['r1','r2','r3']),group(remove,'COMPLETED',[],['h1','h2','h3']),
                                 group(delay3,'VIOLATION',['C5','C6','C7'],['t1']),group(delay3,'COMPLETED',[],['t2','t3']),
                                 {**group(delay2,'LAB_ERROR',[],['e1']),'lifecycle':'LAB_ERROR','fault_triggered':False}]}
    recorded=[]
    class Mechanic:
        async def diagnose(self,context):
            recorded.append(context); return 'no-proposal',None,[]
    class Runner:
        async def run(self,*args,**kwargs): raise AssertionError('No selected intervention permits an execution')
    result,_=await Diagnostician(LabStore(tmp_path/'lab.db'),Runner(),None,Mechanic()).run(SimpleNamespace(campaign_id='campaign-fixture'),counter,recipe,None,[],evidence=[],reduction=reduction)
    assert result.kind=='INCONCLUSIVE'
    context=recorded[0]
    assert context['observed_control_trials']=={'fresh_trials':3,'valid_trials':3,'target_violations':3,'episode_ids':['r1','r2','r3']}
    observed={v['change']:v['observed_treatment_trials'] for v in context['interventions']}
    assert observed['remove_primitive:0']=={'fresh_trials':3,'valid_trials':3,'target_violations':0,'episode_ids':['h1','h2','h3']}
    assert observed['lower_parameter:0:completion_delay_ticks:3']=={'fresh_trials':3,'valid_trials':3,'target_violations':1,'episode_ids':['t1','t2','t3']}
    assert observed['lower_parameter:0:completion_delay_ticks:2']=={'fresh_trials':1,'valid_trials':0,'target_violations':0,'episode_ids':['e1']}
    assert observed['lower_parameter:0:completion_delay_ticks:1'] is None
    assert [v['expected_result'] for v in context['interventions']]==['3/3 control target violations and zero treatment target violations']*4

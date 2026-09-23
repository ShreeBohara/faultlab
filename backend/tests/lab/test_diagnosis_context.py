from types import SimpleNamespace

import pytest

from app.agents.actor import ACTOR_PROMPT
from app.contracts.models import FaultSpec,EpisodeBudget,TrialResult,Usage,content_hash
from app.lab.diagnosis import Diagnostician,trial_outcomes,reduction_context,runtime_contract
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


@pytest.mark.anyio
@pytest.mark.parametrize('hook',['after_upgrade_response','before_final_report'])
async def test_documented_hook_timing_matches_original_actor_and_report_control(tmp_path,hook):
    import json
    from app.adapters.journal import Journal,allocate_intent
    from app.agents.actor import Actor
    from app.contracts.models import RecoveryPolicy,canonical_json
    from app.lab.budgets import EpisodeMeter
    from app.lab.policy_interpreter import PolicyInterpreter
    from app.providers.runtime import RuntimeGeneration
    store=LabStore(tmp_path/'actor.db'); store.put_record('episodes','episode-fixture',{'campaign_id':'campaign-fixture'})
    intent=allocate_intent('order-demo','Upgrade and confirm')
    broker=SimpleNamespace(journal=Journal(store,'episode-fixture',intent),meter=EpisodeMeter())
    calls=[]; flags=[]
    async def call(tool,arguments): calls.append(tool); broker.meter.http_attempt()
    broker.call=call
    policy=RecoveryPolicy.model_validate_json(canonical_json({'parent_version':'policy-v0','rules':[{'hook':hook,'when':'always','steps':[{'op':'defer_unresolved'}]}]}))
    interpreter=PolicyInterpreter(policy,broker)
    original_report={'upgrade_outcome':'UNKNOWN','notification_outcome':'NOT_STARTED','overall':'SAFE_UNRESOLVED','evidence_ids':[],'next_action':{'kind':'ESCALATE'}}
    outputs=[{'kind':'tool','tool':'update_order','arguments':{'desired_shipping':'express'}},
             {'kind':'tool','tool':'get_operation_status','arguments':{'service':'orders'}},
             {'kind':'report','report':original_report}]
    class Provider:
        async def complete(self,messages,**kwargs):
            flags.append(json.loads(messages[-1]['content'])['final_report_required'])
            return RuntimeGeneration(canonical_json(outputs[len(flags)-1]),'openai/gpt-oss-120b')
    result=await Actor()(intent,SimpleNamespace(broker=broker,interpreter=interpreter,provider=Provider(),metadata={'model_id':'openai/gpt-oss-120b'}))
    assert result.model_dump(mode='json')==original_report
    assert broker.meter.usage.actor_calls==3 and broker.meter.caps.actor_calls==8
    if hook=='after_upgrade_response':
        assert flags==[False,True,True] and calls==['update_order']
    else:
        assert flags==[False,False,False] and calls==['update_order','get_operation_status']
    assert broker.meter.business_closed and broker.meter.usage.policy_steps==1
    contract=runtime_contract()
    assert set(contract['hook_boundaries'])=={'after_upgrade_response','before_confirmation','after_notification_response','before_final_report'}
    assert 'Only after a schema-valid actor report proposal' in contract['hook_boundaries']['before_final_report']
    assert 'every remaining actor turn report-required' in contract['report_control']['defer_unresolved']
    assert 'There is no extra repair turn' in contract['report_control']['reserved_final_turn']


def test_runtime_contract_covers_exact_reviewed_primitives_and_conditions():
    from typing import get_args
    from app.contracts.models import Condition,NoArgStep,WaitStep,ServiceStep,ReceiptStep
    contract=runtime_contract()
    assert set(contract['condition_semantics'])==set(get_args(Condition))
    assert set(contract['primitive_semantics'])=={op for cls in (NoArgStep,WaitStep,ServiceStep,ReceiptStep) for op in get_args(cls.model_fields['op'].annotation)}
    assert 'Does not require a receipt' in contract['condition_semantics']['current_operation_pending']
    assert 'write was attempted' in contract['condition_semantics']['upgrade_outcome_uncertain']
    assert 'does not read status' in contract['primitive_semantics']['wait_ticks'].lower()


@pytest.mark.parametrize('service',['orders','notifications'])
@pytest.mark.parametrize('terminal',['SUCCEEDED','FAILED'])
def test_documented_pending_uncertain_and_terminal_conditions_match_delivered_evidence(tmp_path,service,terminal):
    from app.adapters.journal import Journal,allocate_intent
    from app.contracts.models import OperationData,Receipt,ToolResult
    from app.lab.policy_state import PolicyState
    store=LabStore(tmp_path/'state.db'); store.put_record('episodes','episode-state',{'campaign_id':'campaign-state'})
    journal=Journal(store,'episode-state',allocate_intent('order-state','Upgrade and confirm'))
    intent=journal.intent; state=PolicyState(journal)
    operation=intent.upgrade_operation_id if service=='orders' else intent.notification_operation_id
    ih=intent.upgrade_intent_hash if service=='orders' else intent.notification_intent_hash
    prefix='upgrade' if service=='orders' else 'notification'
    pending='current_operation_pending' if service=='orders' else 'notification_operation_pending'
    assert not state.condition(prefix+'_outcome_uncertain')  # no write attempt
    journal.prepare(service,{'operation_id':operation}); journal.attempt(service,'attempt-original')
    assert state.condition(prefix+'_outcome_uncertain')  # attempted, no response
    def deliver(status,receipt=None):
        tick=len(journal.observations)+1
        data=OperationData(service=service,operation_id=operation,order_id=intent.order_id,intent_hash=ih,status=status,receipt=receipt)
        journal.deliver(ToolResult(call_id='call-'+str(tick),tool='get_operation_status',transport='ok',operation_id=operation,status=status,receipt_id=receipt.receipt_id if receipt else None,data=data),tick)
    deliver('PENDING')
    assert state.receipt(service) is None and state.condition(pending)
    assert state.condition(prefix+'_outcome_uncertain') and state.condition(prefix+'_receipt_missing')
    deliver('UNKNOWN')
    assert not state.condition(pending) and state.condition(prefix+'_outcome_uncertain')
    receipt=Receipt(receipt_id='receipt-terminal',service=service,operation_id=operation,order_id=intent.order_id,intent_hash=ih,status=terminal,terminal_tick=3)
    deliver(terminal,receipt); deliver('UNKNOWN')
    assert state.status(service)==terminal  # later uncertainty does not erase a receipt
    assert not state.condition(pending) and not state.condition(prefix+'_outcome_uncertain')
    assert state.condition(prefix+'_succeeded') is (terminal=='SUCCEEDED')
    assert state.condition(prefix+'_terminal_failure') is (terminal=='FAILED')
    assert state.condition(prefix+'_receipt_missing') is (terminal!='SUCCEEDED')
    contract=runtime_contract()
    assert 'also true when a matching FAILED receipt exists' in contract['condition_semantics'][prefix+'_receipt_missing']
    assert 'remains authoritative after later UNKNOWN' in contract['condition_evidence']


def test_explicit_report_presence_preserves_null_reports_and_contradictory_evidence():
    from app.contracts.models import PublicObservation,ToolResult,TaskReport,CheckResult,canonical_json
    from app.lab.diagnosis import summarize_evidence
    originals=[None,
        TaskReport.model_validate_json('{"upgrade_outcome":"PENDING","notification_outcome":"NOT_STARTED","overall":"SAFE_UNRESOLVED","evidence_ids":["evidence-pending"],"next_action":{"kind":"ESCALATE"}}'),
        TaskReport.model_validate_json('{"upgrade_outcome":"SUCCEEDED","notification_outcome":"SUCCEEDED","overall":"COMPLETED","evidence_ids":["evidence-pending"],"next_action":{"kind":"NONE"}}')]
    bundles=[]
    for index,report in enumerate(originals):
        observation=PublicObservation(episode_id=f'episode-{index}',evidence_id='evidence-pending',call_id='call-pending',delivered_tick=2,result=ToolResult(call_id='call-pending',tool='get_operation_status',transport='ok',status='PENDING'))
        bundles.append(SimpleNamespace(episode_id=f'episode-{index}',source='weave_verified',observations=[observation],report=report,findings=[CheckResult(check_id='C5',passed=index==1,category='truthful_report')]))
    before=canonical_json(originals)
    compact=summarize_evidence(bundles)
    assert [e['original_report_present'] for e in compact['episodes']]==[False,True,True]
    reports=[compact['reports'][e['report_row']] for e in compact['episodes']]
    assert reports[0] is None
    assert [report['overall'] for report in reports[1:]]==['SAFE_UNRESOLVED','COMPLETED']
    assert reports[2]['upgrade_outcome']=='SUCCEEDED'  # preserve the false original claim
    assert all(compact['results'][e['observations'][0][2]]['status']=='PENDING' for e in compact['episodes'])
    assert [compact['checks'][e['check_row']][0]['passed'] for e in compact['episodes']]==[False,True,False]
    assert canonical_json(originals)==before


@pytest.mark.anyio
@pytest.mark.parametrize('same_campaign',[False,True])
async def test_identical_interventions_in_distinct_incidents_preserve_both_runs(tmp_path,same_campaign):
    recipe=FaultSpec.model_validate({'seed':42,'primitives':[{'kind':'F2','target_tool':'update_order','target_service':'orders','occurrence':1,'parameters':{'completion_delay_ticks':5,'terminal_status':'SUCCEEDED','failure_code':None}}]})
    store=LabStore(tmp_path/'incidents.db')
    contexts=[]; executed=[]

    def trial(episode_id,spec,index):
        failure=bool(spec.primitives)
        return TrialResult(episode_id=episode_id,world_id='world-'+episode_id,scenario_hash=content_hash(spec),policy_hash='a'*64,arm='B0',trial_index=index,lifecycle='COMPLETED',outcome='VIOLATION' if failure else 'COMPLETED',failed_checks=['C5'] if failure else [],fault_scheduled=failure,fault_triggered=failure)

    class Ledger:
        def __init__(self): self.reservations={}
        def reserve(self,name,calls): self.reservations[name]=calls
        def release(self,name): self.reservations.pop(name)

    class Mechanic:
        async def diagnose(self,context):
            contexts.append(context)
            selected=context['interventions'][0]
            assert selected['change']=='remove_primitive:0'
            return 'proposal-'+context['counterexample_id'],SimpleNamespace(requested_intervention_id=selected['id'],hypothesis='Removing the delay removes C5 violations',proposed_kind='POLICY_GAP'),[]

    class Runner:
        async def run(self,campaign,spec,policy,**kwargs):
            assert kwargs['purpose']=='intervention'
            result=trial('episode-'+str(len(executed)),spec,kwargs['trial_index'])
            executed.append(result)
            store.put_record('trials',result.episode_id,result,immutable=True)
            return result

    ledger=Ledger(); diagnoses=[]; runs=[]; first_saved=None
    try:
        for index in range(2):
            campaign=SimpleNamespace(campaign_id='campaign-a' if same_campaign or index==0 else 'campaign-b')
            counter=SimpleNamespace(counterexample_id=f'counter-{index}',target_invariant='C5',attempted_count=3,valid_count=3,target_violation_count=3)
            reproduction=[trial(f'reproduction-{index}-{n}',recipe,n) for n in range(3)]
            diagnostic,run=await Diagnostician(store,Runner(),ledger,Mechanic()).run(campaign,counter,recipe,None,reproduction,evidence=[])
            diagnoses.append(diagnostic); runs.append(run)
            if index==0: first_saved=store.get_record('interventions',run.experiments[0].intervention_id)

        assert len(executed)==len(store.list_records('trials'))==12
        assert len({t.episode_id for t in executed})==len({t.world_id for t in executed})==12
        assert not ledger.reservations
        assert len(store.list_records('interventions'))==len(store.list_records('diagnostics'))==2
        assert {d.kind for d in diagnoses}=={'POLICY_GAP'}
        ids=[run.experiments[0].intervention_id for run in runs]
        assert ids[0]!=ids[1]
        assert store.get_record('interventions',ids[0])==first_saved
        assert contexts[0]['control_fault_spec']==contexts[1]['control_fault_spec']
        assert contexts[0]['interventions'][0]['treatment_fault_spec']==contexts[1]['interventions'][0]['treatment_fault_spec']
        assert {run.experiments[0].control_hash for run in runs}=={content_hash(recipe)}
        assert len({run.experiments[0].treatment_hash for run in runs})==1
        for index,(diagnostic,run) in enumerate(zip(diagnoses,runs)):
            experiment=run.experiments[0]
            assert experiment.intervention_id==contexts[index]['interventions'][0]['id']
            assert experiment.counterexample_id==f'counter-{index}'
            assert experiment.result=='SUPPORTED' and len(experiment.trial_pairs)==3
            assert {episode_id for pair in experiment.trial_pairs for episode_id in pair}=={t.episode_id for t in run.trials}
            assert diagnostic.intervention_ids==[experiment.intervention_id]
            assert store.get_record('diagnostic_campaigns',diagnostic.diagnostic_id)['campaign_id']==('campaign-a' if same_campaign or index==0 else 'campaign-b')
    finally:
        store.close()

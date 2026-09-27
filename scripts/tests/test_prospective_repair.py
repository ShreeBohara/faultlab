"""Offline prospective-run admission, routing and boundary-I/O orchestration checks."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('prospective_tested',ROOT/'scripts/experiments/run_prospective_repair.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    original=socket.socket.connect
    def connect(sock,address):
        if sock.family==socket.AF_UNIX: return original(sock,address)
        raise AssertionError('This suite must not contact services')
    monkeypatch.setattr(socket.socket,'connect',connect)


def priced(tmp_path):
    return r.settings_for_run(r.Settings(wandb_model=r.verified.ACTOR,wandb_explorer_model=r.verified.REASONER,
        wandb_mechanic_model=r.verified.REASONER,wandb_entity='shreetbohara-quinstreet',wandb_project='Faultlab',
        wandb_api_key='offline-fixture-key',faultlab_live_enabled=True,faultlab_confirmed_entity='shreetbohara-quinstreet',
        faultlab_pricing_model=r.verified.ACTOR,faultlab_pricing_verified=True,
        faultlab_input_dollars_per_million=.55,faultlab_output_dollars_per_million=1.65,
        faultlab_reasoning_pricing_model=r.verified.REASONER,faultlab_reasoning_pricing_verified=True,
        faultlab_reasoning_input_dollars_per_million=1.31,faultlab_reasoning_output_dollars_per_million=3.96),tmp_path)


def basic_plan(settings):
    config=r.frozen_configuration(settings,r.CAPS,'live-v1')
    return {'configuration':config,'configuration_hash':r.content_hash(config),'runtime_hash':config['runtime_hash'],
        'task_text':'Upgrade and confirm','order_id':'order-fixture','partition_commitment':{'hash':'sealed'},
        'policy_inventory':{'policy_hashes':[]},'policy_inventory_hash':'inventory'}


def test_common_configuration_and_complete_call_bounds_are_exact(tmp_path):
    settings=priced(tmp_path);r.check_settings(settings)
    assert r.STUDY_CALLS==964 and r.STUDY_BOUND==Decimal('20.26336')
    assert r.STUDY_CALLS*r.MECHANIC_BOUND==Decimal('48.04576')
    assert r.EVALUATION_CALLS==2496 and r.EVALUATION_CALLS*r.ACTOR_BOUND==Decimal('52.1664')
    other=r.settings_for_run(settings,tmp_path/'another')
    assert r.frozen_configuration(settings,r.CAPS,'live-v1')==r.frozen_configuration(other,r.CAPS,'live-v1')
    assert r.CAPS.tokens==84_864_000 and r.CAPS.dollars==60


@pytest.mark.parametrize('used,attempts,allowed',[(0,0,True),(79.73664,9,True),(79.73665,9,False),
    (0,10,False),(-1,0,False),('NaN',0,False),('Infinity',0,False)])
def test_generation_admission_reserves_complete_remaining_path(used,attempts,allowed):
    assert r.can_start_attempt(used,attempts) is allowed


def test_unchanged_mixed_ledger_reserves_and_charges_full_role_bounded_path(tmp_path):
    store=r.LabStore(tmp_path/'ledger.sqlite3')
    ledger=r.CampaignLedger(store,'campaign-test',r.CAPS,dollar_bounds={'actor':.0209,'mechanic':.04984,'explorer':.04984})
    for name in r.PROTECTED: ledger.release(name)
    ledger.reserve('completion:test',r.STUDY_CALLS)
    for role,count in (('actor',960),('mechanic',4)):
        for _ in range(count): ledger.consume_call(reservation='completion:test',role=role)
    assert ledger.used_calls==964 and ledger.used_tokens==32_776_000
    assert r.ledger_charge(ledger)==20.26336
    from app.lab.budgets import BudgetExhausted
    with pytest.raises(BudgetExhausted): ledger.consume_call(reservation='completion:test')
    assert ledger.used_calls==964
    store.close()


def test_scoped_provider_counts_every_dispatch_and_refuses_wrong_role_or_excess():
    async def exercise():
        calls=[];checks=[]
        async def complete(messages,**kwargs): calls.append(kwargs['role']);return object()
        provider=r.ScopedProvider(SimpleNamespace(complete=complete),{'actor':2,'mechanic':2},lambda:None,
            lambda:None,context_check=lambda messages:checks.append(messages))
        for role in ('actor','actor','mechanic','mechanic'): await provider.complete([],role=role)
        for role in ('actor','mechanic','explorer'):
            with pytest.raises(r.verified.Refusal): await provider.complete([],role=role)
        assert calls==['actor','actor','mechanic','mechanic'] and dict(provider.calls)=={'actor':2,'mechanic':2}
        assert len(checks)==2
    asyncio.run(exercise())


def test_admission_persists_honest_964_plan_before_any_executor_calls(tmp_path,monkeypatch):
    settings=priced(tmp_path);plan=basic_plan(settings)
    c,campaign,ledger=r.new_campaign(settings,tmp_path/'study',plan)
    monkeypatch.setattr(c,'require_simulator',AsyncMock())
    study,reservation=asyncio.run(r.admit_study(c,campaign,ledger,plan))
    assert study['reserved_model_calls']==964 and ledger.reservations[reservation]['calls']==964
    assert len(study['slots'])==60 and study['case_manifest_id']=='upgrade-v1'
    assert c.store.get_record('completion_plans',study['study_id'])['reserved_model_calls']==964
    assert ledger.used_calls==0 and c.get(campaign.campaign_id).active_policy_version=='policy-v0'
    with pytest.raises(r.verified.Refusal): asyncio.run(r.admit_study(c,campaign,ledger,plan))
    c.store.close()


def saved_source(tmp_path,*,gain=3):
    fixture_spec=importlib.util.spec_from_file_location('policy_status_fixture',ROOT/'backend/tests/lab/test_policy_status.py')
    fixtures=importlib.util.module_from_spec(fixture_spec);fixture_spec.loader.exec_module(fixtures)
    store=r.LabStore(tmp_path/'saved.sqlite3');fixtures.PolicyRepository(store)
    study=fixtures.saved_study(store,gain=gain);study['configuration_hash']='config-fixture'
    for row in study['trial_rows']:
        trial=row['trial'];ident=trial['episode_id']
        store.put_record('trials',ident,trial,immutable=True)
        store.put_record('episodes',ident,{'episode_id':ident,'campaign_id':study['campaign_id'],
            'configuration_hash':'config-fixture','study_id':study['study_id'],
            **{key:trial[key] for key in ('world_id','policy_hash','scenario_hash')}})
        store.put_record('evidence',ident,{'source':'weave_verified','source_project':r.verified.PROJECT})
    return store,study,{'configuration_hash':'config-fixture','policy_inventory':{'policy_hashes':[]}}


@pytest.mark.parametrize('condition',['fresh','old-hash','weak','wrong-config','changed-trial','missing-evidence'])
def test_actual_strong_gate_and_current_evidence_bindings_control_routing(tmp_path,condition):
    store,study,plan=saved_source(tmp_path,gain=1 if condition=='weak' else 3)
    if condition=='old-hash': plan['policy_inventory']['policy_hashes']=[study['selected_candidate_hash']]
    if condition=='wrong-config': plan['configuration_hash']='different'
    ident=study['trial_rows'][0]['trial']['episode_id']
    if condition=='changed-trial': store.db.execute("DELETE FROM records WHERE kind='trials' AND id=?",(ident,))
    if condition=='missing-evidence': store.db.execute("DELETE FROM records WHERE kind='evidence' AND id=?",(ident,))
    if condition in ('wrong-config','changed-trial','missing-evidence'):
        with pytest.raises(r.verified.Refusal): r.choose_candidate(store,study,plan)
    else:
        policy,qualification=r.choose_candidate(store,study,plan)
        assert (policy is not None)==(condition=='fresh')
        if condition=='old-hash': assert qualification['routing']=='HISTORICAL_REDISCOVERY'
        if condition=='weak': assert qualification['status']=='NOT_QUALIFIED'
    store.close()


def test_mechanic_input_cannot_contain_validation_or_reserved_episode(tmp_path):
    store=r.LabStore(tmp_path/'input.sqlite3')
    manifest=r.completion_study.build_case_manifest('upgrade-v1');cases={c['case_id']:c for c in manifest['cases']}
    store.put_record('completion_studies','study',{'trial_rows':[{'stage':'controls','trial':{'episode_id':'public'}}]})
    store.put_record('episodes','public',{'campaign_id':'campaign','split':'development','study_id':'study','evidence_context_id':'study'})
    context={'study_id':'study','objective':r.completion_study.SCHEMA,'source_fault_spec':cases['upgrade-3']['fault_spec'],
        'control_fault_spec':cases['healthy']['fault_spec'],'development_evidence':{'episodes':[{'episode_id':'public'}]}}
    messages=[{'role':'system','content':'fixture'},{'role':'user','content':json.dumps(context)}]
    r.assert_mechanic_context(messages,store,'study')
    context['development_evidence']['episodes'].append({'episode_id':'private-case-canary'})
    messages[1]['content']=json.dumps(context)
    with pytest.raises(r.verified.Refusal): r.assert_mechanic_context(messages,store,'study')
    store.close()


def test_selected_policy_file_change_is_refused(tmp_path,monkeypatch):
    protocol=tmp_path/'protocol';protocol.write_text('sealed')
    selected=tmp_path/'selected.json';selected.write_text('original')
    plan={'harness_sha256':r.file_sha(r.__file__),'helper_sha256':{},'protocol_sha256':r.file_sha(protocol),'inputs':{}}
    monkeypatch.setattr(r,'helper_hashes',lambda:{})
    guard=r.RuntimeGuard(SimpleNamespace(protocol=protocol),plan,{},lambda:False)
    guard.selected_artifacts[str(selected)]=r.file_sha(selected);guard()
    selected.write_text('changed')
    with pytest.raises(r.verified.Refusal,match='Selected policy'): guard()


def test_inventory_reads_policy_records_only_and_preserves_source_bytes(tmp_path):
    from app.lab.policies import PolicyRepository
    path=tmp_path/'source.sqlite3';store=r.LabStore(path);PolicyRepository(store)
    store.put_record('private_partition','canary',{'recipe':'PRIVATE NEVER IN INVENTORY'});store.close()
    before=r.file_sha(path);inventory=r.policy_inventory(tmp_path)
    assert len(inventory['policy_hashes'])==1 and 'PRIVATE' not in json.dumps(inventory)
    assert r.file_sha(path)==before


def test_existing_experiment_output_refuses_before_reading_inputs(tmp_path,monkeypatch):
    monkeypatch.setattr(r,'DEFAULT_OUTPUT',tmp_path)
    with pytest.raises(r.verified.Refusal,match='no overwrite'):
        r.prepare(SimpleNamespace(output=tmp_path))


def test_readback_failure_retains_original_candidate_harm(tmp_path):
    store=r.LabStore(tmp_path/'eval.sqlite3')
    store.put_record('trials','episode-L',{'episode_id':'episode-L','policy_hash':'selected','arm':'L',
        'lifecycle':'COMPLETED','outcome':'VIOLATION','failed_checks':['C6']})
    store.put_record('episodes','episode-L',{'episode_id':'episode-L','campaign_id':'campaign','report':{'original':True}})
    record={'status':'INCOMPLETE'};r.retain_candidate_failures(store,record,'selected')
    assert record['status']=='INCOMPLETE' and record['observed_safety_decision']=='HARM'
    assert record['candidate_rule_failures']==['episode-L']
    store.close()


def test_charged_but_rejected_dispatch_is_retained_in_shared_accounting(tmp_path):
    store=r.LabStore(tmp_path/'cost.sqlite3')
    ledger=r.CampaignLedger(store,'campaign',r.CAPS,dollar_bounds={'actor':.0209})
    for name in r.PROTECTED: ledger.release(name)
    ledger.consume_call()
    record={'attempts':[{'_ledger':ledger,'_provider':SimpleNamespace(calls={}), 'trials':[]}]}
    r.summarize_record(record)
    assert record['accounting']['generation_charged_upper_bound']==.0209
    assert record['attempts'][0]['provider_requests_by_role']=={}
    assert '_ledger' not in json.dumps(r.serializable_record(record))
    store.close()


class OfflineGuard:
    stopped=staticmethod(lambda:False)
    def __call__(self,**kwargs): pass


def install_fake_episode_boundary(monkeypatch,*,maximal=False,readback_failure=False,untriggered=False):
    """Keep real coordinator, completion executor, Mechanic, evaluators, gates and ledgers."""
    from app.contracts.models import RecoveryPolicy,TrialResult
    from app.lab.budgets import EpisodeMeter
    from app.providers.runtime import RuntimeGeneration
    first={'parent_version':'policy-v0','rules':[{'hook':'after_upgrade_response','when':'upgrade_outcome_uncertain',
        'steps':[{'op':'retry_original_request','service':'orders'}]}]}
    second={'parent_version':'policy-v0','rules':[{'hook':'before_final_report','when':'always','steps':[{'op':'read_order'}]}]}
    first_hash=r.content_hash(RecoveryPolicy.model_validate(first))
    seen={'mechanic':[],'actor':0,'readback':0}
    manifest=r.completion_study.build_case_manifest('upgrade-v1')
    cases={r.content_hash(c['fault_spec']):c for c in manifest['cases']}
    async def require_simulator(self): pass
    monkeypatch.setattr(r.LabCoordinator,'require_simulator',require_simulator)
    monkeypatch.setattr(r.verified,'check_world',lambda *args:{'world_file_verified':True})
    monkeypatch.setattr(r,'verify_stage_store',lambda *args:None)
    async def get_runner(coordinator,live):
        class Provider:
            def role_model(self,role): return r.verified.REASONER if role=='mechanic' else r.verified.ACTOR
            async def close(self): pass
            async def complete(self,messages,*,role,**kwargs):
                if role=='actor':
                    seen['actor']+=1
                    return RuntimeGeneration('{}',r.verified.ACTOR,input_tokens=1,output_tokens=1)
                seen['mechanic'].append(deepcopy(messages))
                number=len(seen['mechanic'])
                raw={'bad':'format'} if maximal and number in (1,3) else {
                    'candidate':first if maximal and number==2 else second,'explanation':'Synthetic boundary fixture'}
                return RuntimeGeneration(r.canonical_json(raw),r.verified.REASONER,input_tokens=1,output_tokens=1)
        class RawRunner:
            provider=Provider();world_client=SimpleNamespace(close=AsyncMock());trace=SimpleNamespace(frozen=False)
            async def run(self,campaign,recipe,policy,**kwargs):
                ledger=kwargs['ledger'];meter=EpisodeMeter(campaign=ledger,reservation=kwargs['reservation'])
                for _ in range(8 if maximal else 1):
                    meter.model_call()
                    generation=await self.provider.complete([{'role':'user','content':'public task and observations only'}],role='actor')
                    ledger.reconcile(generation)
                    if maximal:
                        assert meter.transport_retry()
                        generation=await self.provider.complete([{'role':'user','content':'public task and observations only'}],role='actor')
                        ledger.reconcile(generation)
                case=cases[r.content_hash(recipe)]
                source=case['case_id']=='upgrade-3';fresh=case['case_id']=='upgrade-2'
                outcome=case['expected_outcome']
                if kwargs['arm']=='B0' and (source or fresh): outcome='SAFE_UNRESOLVED'
                if maximal and policy.policy_hash==first_hash and source: outcome='SAFE_UNRESOLVED'
                negative=readback_failure and kwargs['purpose']=='final_audit' and kwargs['arm']=='L'
                if negative: outcome='VIOLATION'
                trial=TrialResult(episode_id=kwargs['episode_id'],world_id='world-'+kwargs['episode_id'],
                    scenario_hash=r.content_hash(recipe),policy_hash=policy.policy_hash,arm=kwargs['arm'],
                    trial_index=kwargs['trial_index'],lifecycle='COMPLETED',outcome=outcome,
                    failed_checks=['C6'] if negative else [],fault_scheduled=bool(recipe.primitives),
                    fault_triggered=bool(recipe.primitives) and not(untriggered and kwargs['purpose']=='final_audit'),usage=meter.usage)
                coordinator.store.put_record('trials',trial.episode_id,trial,immutable=True)
                coordinator.store.put_record('episodes',trial.episode_id,{'episode_id':trial.episode_id,
                    'campaign_id':campaign.campaign_id,'study_id':kwargs.get('study_id',campaign.campaign_id),
                    'evidence_context_id':kwargs.get('evidence_context_id',campaign.campaign_id),
                    'configuration_hash':campaign.configuration_hash,'split':'final_audit' if kwargs['purpose']=='final_audit' else 'development',
                    'world_id':trial.world_id,'policy_hash':trial.policy_hash,'scenario_hash':trial.scenario_hash,
                    'report':{'synthetic_boundary_report':True},'verdict':{'checks':[]}})
                return trial
        async def get_evidence(ident,context,**kwargs):
            coordinator.store.put_record('evidence',ident,{'source':'weave_verified','source_project':r.verified.PROJECT})
            return SimpleNamespace(episode_id=ident,source='weave_verified',source_project=r.verified.PROJECT,
                observations=[],report=None,findings=[])
        coordinator.evidence_gateway=SimpleNamespace(get=get_evidence)
        coordinator.evaluation_publisher=None
        raw=RawRunner()
        # Mechanic uses a trace span when present; public fixtures omit telemetry at
        # this boundary, while the reserved runner needs the frozen flag on a stub.
        if not coordinator.check_options[-1]: raw.trace=None
        return raw,True
    monkeypatch.setattr(r.LabCoordinator,'_get_runner',get_runner)
    async def readback(store,runner,trial,campaign,**kwargs):
        seen['readback']+=1
        if readback_failure and trial.arm=='L': raise OSError('synthetic evidence failure')
        return {'source':'weave_verified','root_call_id':trial.episode_id}
    monkeypatch.setattr(r,'reserved_readback',readback)
    return seen


def test_unchanged_completion_executor_full_sixty_episode_path_with_four_mechanic_calls(tmp_path,monkeypatch):
    seen=install_fake_episode_boundary(monkeypatch,maximal=True)
    settings=priced(tmp_path);plan=basic_plan(settings)
    monkeypatch.setattr(r,'policy_inventory',lambda root:plan['policy_inventory'])
    output=tmp_path/'run';output.mkdir()
    args=SimpleNamespace(output=output,worlds_dir=tmp_path/'worlds')
    outer={'configuration_hash':plan['configuration_hash'],'attempts':[],'_world_ids':set()}
    def save(): r.summarize_record(outer)
    policy,study=asyncio.run(r.run_attempt(args,settings,plan,outer,OfflineGuard(),save,1))
    assert policy is not None and study['status']=='COMPLETED'
    assert outer['attempts'][0]['qualification']['routing']=='FIRST_FRESH_QUALIFIED'
    assert len(outer['attempts'][0]['trials'])==60 and len(outer['attempts'][0]['attempted_slots'])==60
    assert seen['actor']==960 and len(seen['mechanic'])==4
    assert study['reserved_model_calls']==study['charged_model_calls']==964
    assert outer['accounting']['generation_charged_upper_bound']==20.26336
    assert outer['attempts'][0]['provider_requests_by_role']=={'actor':960,'mechanic':4}
    assert all('private-case-canary' not in json.dumps(messages) for messages in seen['mechanic'])


@pytest.mark.parametrize('condition',['complete','untriggered','readback-failure'])
def test_reserved_real_evaluator_keeps_156_slots_and_harm_survives_evidence_error(tmp_path,monkeypatch,condition):
    install_fake_episode_boundary(monkeypatch,readback_failure=condition=='readback-failure',untriggered=condition=='untriggered')
    settings=priced(tmp_path);plan=basic_plan(settings)
    from app.contracts.models import RecoveryPolicy
    content=RecoveryPolicy(parent_version='policy-v0',rules=[{'hook':'before_final_report','when':'always','steps':[{'op':'read_order'}]}])
    policy=r.PolicyVersion(version='policy-fixture',parent_version='policy-v0',content=content,
        policy_hash=r.content_hash(content),author='mechanic',raw_proposal_ref='proposal-fixture',development_episode_ids=[],decision='PROPOSED')
    cases=r.completion_study.build_case_manifest('upgrade-v1')['cases'][:6]
    # One empty recipe and five fault recipes => 26 evaluator positions / 156 episodes.
    manifest={'cases':cases};output=tmp_path/'run';output.mkdir()
    args=SimpleNamespace(output=output,worlds_dir=tmp_path/'worlds')
    outer={'configuration_hash':plan['configuration_hash'],'attempts':[],'_world_ids':set(),
        'selected_policy_hash':policy.policy_hash,'candidate_binding':{'policy_hash':policy.policy_hash}}
    def save(): r.summarize_record(outer)
    if condition=='readback-failure':
        with pytest.raises(OSError): asyncio.run(r.run_reserved(args,settings,plan,manifest,policy,outer,OfflineGuard(),save))
        assert outer['evaluation']['status']=='INCOMPLETE'
        assert outer['evaluation']['observed_safety_decision']=='HARM'
        assert len(outer['evaluation']['trials'])==2 and outer['evaluation']['trials'][-1]['failed_checks']==['C6']
    else:
        result=asyncio.run(r.run_reserved(args,settings,plan,manifest,policy,outer,OfflineGuard(),save))
        assert len(result['trials'])==len(result['attempted_slots'])==len(result['readbacks'])==156
        assert result['status']==('COMPLETED' if condition=='complete' else 'INCOMPLETE')
        assert result['measurement_complete']==(condition=='complete')
        assert result['evaluation_batches'][0]['decision']==('NO_CHANGE' if condition=='complete' else 'INCOMPLETE')
        assert result['accounting']['charged_model_calls']==156
    assert outer['accounting']['generation_charged_upper_bound']==0
    assert outer['accounting']['evaluation_charged_upper_bound']>0


def test_default_world_path_matches_existing_simulator_artifact_layout():
    assert r.DEFAULT_WORLDS==r.ROOT/'artifacts/prospective-repair-worlds-2026-09-27/worlds'


@pytest.mark.parametrize('mutation',[None,'foreign-project','foreign-episode','changed-report','changed-observation','wrong-split'])
def test_reserved_readback_uses_exact_private_ids_and_never_writes_optimizer_evidence(tmp_path,mutation):
    from app.telemetry.safety import TelemetryError
    store=r.LabStore(tmp_path/'reserved.sqlite3')
    campaign=SimpleNamespace(campaign_id='campaign-fixture',configuration_hash='config',model=r.verified.ACTOR,execution_epoch=1)
    trial=SimpleNamespace(episode_id='episode-fixture',world_id='world-fixture',policy_hash='hash',arm='L',trial_index=0)
    store.put_record('configurations','config',{'contract_hash':'contract','scorer_hash':'scorer'})
    store.put_record('episodes',trial.episode_id,{'episode_id':trial.episode_id,'campaign_id':campaign.campaign_id,
        'world_id':trial.world_id,'configuration_hash':'config','policy_hash':'hash','split':'final_audit',
        'lifecycle':'COMPLETED','report':{'original':'unchanged'}})
    observation={'episode_id':trial.episode_id,'value':'original observation'}
    store.put_record('observations','observation-id',observation)
    metadata={'campaign_id':campaign.campaign_id,'episode_id':trial.episode_id,'study_id':campaign.campaign_id,
        'evidence_context_id':campaign.campaign_id,'split':'final_audit','experiment_purpose':'final_audit',
        'source_mode':'live','policy_hash':'hash','arm':'L','execution_epoch':1,'trial_index':0,'model_id':campaign.model,
        'origin':'faultlab_evaluation','contract_hash':'contract','scorer_hash':'scorer',
        'experiment_kind':'prospective_reserved_evaluation','original_workflow_final_audit':False,'ordinary_policy_accepted':False}
    local=[{'call_id':'root','name':'run_episode','metadata':metadata},
        {'call_id':'child','name':'get_order','metadata':metadata,'parent_id':'root'}]
    remote=[{'id':'root','project_id':r.verified.PROJECT,'attributes':deepcopy(metadata),'ended_at':'yes',
        'inputs':{},'output':{'terminal_status':'COMPLETED','report':{'original':'unchanged'}},'trace_id':'trace'},
        {'id':'child','project_id':r.verified.PROJECT,'attributes':deepcopy(metadata),'ended_at':'yes',
        'inputs':{},'output':{'observation':deepcopy(observation)},'trace_id':'trace','parent_id':'root'}]
    if mutation=='foreign-project': remote[0]['project_id']='other/project'
    if mutation=='foreign-episode': remote[1]['attributes']['episode_id']='other'
    if mutation=='changed-report': remote[0]['output']['report']={'changed':True}
    if mutation=='changed-observation': remote[1]['output']['observation']['value']='changed'
    if mutation=='wrong-split': metadata['split']='development'
    calls=[]
    async def request(command,payload,**kwargs):
        calls.append((command,payload));return remote if command=='get_calls' else {}
    runner=SimpleNamespace(trace=SimpleNamespace(episode_calls=lambda episode:local),
        telemetry_worker=SimpleNamespace(request=request))
    if mutation:
        with pytest.raises((r.verified.Refusal,TelemetryError)):
            asyncio.run(r.reserved_readback(store,runner,trial,campaign))
        assert store.list_records('evaluation_readbacks')==[]
    else:
        result=asyncio.run(r.reserved_readback(store,runner,trial,campaign))
        assert result['source']=='weave_verified' and result['root_call_id']=='root'
        assert len(store.list_records('evaluation_readbacks'))==1
        assert calls==[('flush',{}),('get_calls',{'call_ids':['root','child']})]
    assert store.list_records('evidence')==[] and store.list_records('completion_proposal_inputs')==[]
    store.close()


@pytest.mark.parametrize('committed',['2026-09-27T01:00:00+00:00','2026-09-28T00:00:00+00:00','2026-09-26T00:00:00'])
def test_nonprior_or_naive_partition_commitment_refuses_before_generation(committed):
    with pytest.raises(r.verified.Refusal):
        r.require_prior_commitment({'committed_at':committed},'2026-09-27T01:00:00+00:00')


@pytest.mark.parametrize('condition',['first-route','none','budget','evaluation-failure'])
def test_outer_flow_routes_first_once_never_resumes_or_falls_back_and_retains_harm(tmp_path,monkeypatch,condition):
    import reserved_partition
    import run_full_loop
    import slot2_probe
    from app.contracts.models import RecoveryPolicy
    settings=priced(tmp_path);plan=basic_plan(settings)
    output=tmp_path/'single-run'
    args=SimpleNamespace(output=output)
    counts={'attempts':[],'evaluations':0}
    monkeypatch.setattr(run_full_loop,'check_backend_process',lambda port:{'processes':[{'command':'--timeout-keep-alive 75'}]})
    monkeypatch.setattr(slot2_probe,'live_experiment_processes',lambda:[])
    monkeypatch.setattr(r,'policy_inventory',lambda root:plan['policy_inventory'])
    class Guard(OfflineGuard):
        def __init__(self,*args): self.selected_artifacts={}
    monkeypatch.setattr(r,'RuntimeGuard',Guard)
    monkeypatch.setattr(reserved_partition,'bind_candidate',lambda *args,**kwargs:{'policy_hash':kwargs['policy_hash']})
    content=RecoveryPolicy(parent_version='policy-v0',rules=[{'hook':'before_final_report','when':'always','steps':[{'op':'read_order'}]}])
    policy=r.PolicyVersion(version='policy-fresh',parent_version='policy-v0',content=content,
        policy_hash=r.content_hash(content),author='mechanic',raw_proposal_ref='proposal-offline',development_episode_ids=[],decision='PROPOSED')
    async def attempt(args,settings,plan,outer,guard,save,number):
        counts['attempts'].append(number)
        charge=float(r.STUDY_BOUND) if condition=='budget' else .0209
        outer['attempts'].append({'attempt':number,'accounting':{'charged_dollar_upper_bound':charge}});save()
        return (policy if condition in ('first-route','evaluation-failure') and number==2 else None),{'study_id':'completion-study-fresh'}
    async def evaluate(args,settings,plan,manifest,selected,outer,guard,save):
        counts['evaluations']+=1
        assert len(counts['attempts'])==2 and selected.policy_hash==policy.policy_hash
        outer['evaluation']={'status':'INCOMPLETE' if condition=='evaluation-failure' else 'COMPLETED',
            'observed_safety_decision':'HARM' if condition=='evaluation-failure' else 'NO_HARM',
            'accounting':{'charged_dollar_upper_bound':.0209}}
        if condition=='evaluation-failure': raise OSError('private error text must not leak')
        return outer['evaluation']
    monkeypatch.setattr(r,'run_attempt',attempt);monkeypatch.setattr(r,'run_reserved',evaluate)
    class SocketGuard:
        def bind(self,address): assert address==('127.0.0.1',8000)
        def close(self): pass
    with asyncio.Runner() as loop:
        with monkeypatch.context() as guard_patch:
            guard_patch.setattr(r.socket,'socket',lambda:SocketGuard())
            result=loop.run(r.execute(args,settings,plan,{}, {'committed_at':'2026-09-26T00:00:00+00:00'}))
    assert len(counts['attempts'])==({'first-route':2,'evaluation-failure':2,'none':10,'budget':4}[condition])
    assert counts['evaluations']==int(condition in ('first-route','evaluation-failure'))
    assert result['decision']==('HARM' if condition=='evaluation-failure' else 'NO_HARM' if condition=='first-route' else 'NO_NEW_QUALIFIED_POLICY')
    assert result['status']==('INCOMPLETE' if condition=='evaluation-failure' else 'COMPLETED')
    assert 'private error text' not in json.dumps(result)
    assert result['accounting']['generation_charged_upper_bound']>0


@pytest.mark.parametrize('mutation',[None,'seed','helper','future'])
def test_preselection_seed_algorithm_and_inventory_seal_is_verified(tmp_path,mutation):
    import reserved_partition as partition
    args=SimpleNamespace(seed_declaration_file=tmp_path/'seed.json',exposure_inventory_file=tmp_path/'inventory.json',
        algorithm_commitment_file=tmp_path/'algorithm.json')
    seed={'seed':partition.SEED,'guards':partition.GUARDS};inventory={'inventory_hash':'inventory-fixture'}
    args.seed_declaration_file.write_text(json.dumps(seed));args.exposure_inventory_file.write_text(json.dumps(inventory))
    seal={'schema_version':'faultlab-reserved-seed-algorithm-commitment/v1','algorithm':partition.ALGORITHM,
        'helper_sha256':r.file_sha(partition.__file__),'seed_declaration_sha256':r.file_sha(args.seed_declaration_file),
        'seed_declaration_hash':partition.digest(seed),'seed_hash':r.sha256(partition.SEED.encode()).hexdigest(),
        'inventory_hash':inventory['inventory_hash'],'inventory_file_sha256':r.file_sha(args.exposure_inventory_file),
        'before_selection':True,'before_provider_generation':True,'no_resampling':True,
        'committed_at':'2026-09-27T01:00:00+00:00'}
    if mutation=='helper': seal['helper_sha256']='changed'
    if mutation=='future': seal['committed_at']='2026-09-28T01:00:00+00:00'
    seal['commitment_hash']=partition.digest(seal);args.algorithm_commitment_file.write_text(json.dumps(seal))
    if mutation=='seed': args.seed_declaration_file.write_text(json.dumps({'seed':'another'}))
    manifest={'seed_declaration_hash':partition.digest(seed)};commitment={'committed_at':'2026-09-27T02:00:00+00:00'}
    if mutation:
        with pytest.raises(r.verified.Refusal): r.verify_seed_commitment(args,manifest,inventory,commitment)
    else: r.verify_seed_commitment(args,manifest,inventory,commitment)

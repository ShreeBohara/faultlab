"""Offline orchestration fixtures: no model/provider or measured repair claims."""
import json
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.contracts.models import (CampaignRequest,Counterexample,CandidatePolicy,MechanicCandidate,
                                 MechanicNoChange,ExplorerOutput,content_hash,canonical_json)
from app.lab.budgets import CampaignLedger
from app.lab.coordinator import LabCoordinator
from app.lab.learning import run_learning_cycle,repair_context_id,export_incident
from test_counterexample_loop import RECIPE,EvidenceDouble
from test_evaluation import FakeRunner


@pytest.fixture
def anyio_backend(): return 'asyncio'


def candidate(op='require_receipt',*,explicit_default=False):
    step={'op':op,'service':'orders','status':'SUCCEEDED'} if op=='require_receipt' else {'op':op}
    if explicit_default: step['only_if']='always'
    return CandidatePolicy.model_validate_json(canonical_json({'parent_version':'policy-v0','rules':[{'hook':'before_confirmation','when':'always','steps':[step]}]}))


def loop(tmp_path,monkeypatch,outputs,*,source_flaky=False,source_candidate_failure=False,challenge_failure=False,challenge_lab_retry=False,promotion_failure=False):
    import app.lab.learning as learning
    coordinator=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path),wandb_model='openai/gpt-oss-120b'))
    campaign=coordinator.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='learn',config_profile_id='live-v1'))
    campaign.caps.discovery_selections=1; coordinator.save(campaign)
    coordinator.ledgers[campaign.campaign_id]=CampaignLedger(coordinator.store,campaign.campaign_id,campaign.caps)
    coordinator.evidence_gateway=EvidenceDouble(); runner=FakeRunner(); runner.provider=object()
    original=runner.run; retry_injected=False
    async def run(*args,**kwargs):
        nonlocal retry_injected
        trial=await original(*args,**kwargs)
        purpose=kwargs.get('purpose')
        if purpose=='source_validation' and source_flaky and kwargs['arm']=='B0' and trial.trial_index==1:
            trial.failed_checks=[]; trial.outcome='COMPLETED'
        if kwargs.get('arm')=='L' and ((purpose=='source_validation' and source_candidate_failure) or (purpose=='challenge' and challenge_failure) or (purpose=='promotion' and promotion_failure)):
            trial.failed_checks=['C3']; trial.outcome='VIOLATION'
        if challenge_lab_retry and purpose=='challenge' and not retry_injected:
            trial.lifecycle='LAB_ERROR'; trial.outcome='LAB_ERROR'; trial.failed_checks=[]; retry_injected=True
        coordinator.store.put_record('trials',trial.episode_id,trial)
        return trial
    runner.run=run; contexts=[]; exports=[]
    class Explorer:
        def __init__(self,*args): self.challenges=0
        async def select(self,context,**kwargs):
            recipe=RECIPE
            if kwargs.get('challenge'):
                self.challenges+=1
                raw=RECIPE.model_dump(mode='json'); raw['primitives'][0]['parameters']['completion_delay_ticks']=3+self.challenges
                recipe=type(RECIPE).model_validate_json(canonical_json(raw))
            ref=f'selection-{self.challenges}'
            result=ExplorerOutput(fault_spec=recipe,hypothesis='Offline selection fixture')
            coordinator.store.put_record('selections',ref,{'output':result.model_dump(mode='json')})
            return ref,result
    class Reproducer:
        def __init__(self,*args): pass
        async def source(self,campaign,source,recipe,policy,**kwargs):
            counter=Counterexample(counterexample_id='counter-fixture',campaign_id=campaign.campaign_id,agent_registration_id='orders-v1',source_episode_id=source.episode_id,target_invariant='C3',scenario_hash=content_hash(recipe),configuration_hash=campaign.configuration_hash,report_ref=source.episode_id,verdict_ref='verdict-fixture',reproduced=True,target_violation_count=3,valid_count=3,attempted_count=3)
            return counter,[source]
        async def reduce(self,*args,**kwargs):
            return SimpleNamespace(result=SimpleNamespace(status='NO_REDUCTION',model_dump=lambda **_: {'status':'NO_REDUCTION'}),retained_recipe=RECIPE,trials=[])
    class Diagnosis:
        def __init__(self,*args): pass
        async def run(self,*args,**kwargs):
            return SimpleNamespace(kind='POLICY_GAP',model_dump=lambda **_: {'kind':'POLICY_GAP','provenance':'offline_double'}),SimpleNamespace(trials=[])
    class Mechanic:
        def __init__(self,*args): self.outputs=iter(outputs)
        async def propose(self,context,**kwargs):
            contexts.append(json.loads(canonical_json(context)))
            value=next(self.outputs)
            proposal=MechanicCandidate(candidate=value,explanation=f'Original fixture proposal {len(contexts)}') if value is not None else MechanicNoChange(no_change_reason='No further supported repair')
            return f'mechanic-{len(contexts)}',proposal,[proposal.model_dump_json()]
    async def export(*args,**kwargs): exports.append((args,kwargs))
    for name,value in [('Explorer',Explorer),('Reproducer',Reproducer),('Diagnostician',Diagnosis),('Mechanic',Mechanic),('export_incident',export)]:
        monkeypatch.setattr(learning,name,value)
    return coordinator,campaign,runner,contexts,exports


@pytest.mark.anyio
async def test_same_policy_with_different_explanation_and_explicit_defaults_gets_no_second_source_batch(tmp_path,monkeypatch):
    c,campaign,runner,contexts,exports=loop(tmp_path,monkeypatch,[candidate(),candidate(explicit_default=True),None],source_candidate_failure=True)
    await run_learning_cycle(c,campaign,runner)
    assert len(runner.calls)==7  # one discovery and exactly one six-episode qualification
    versions=[p for p in c.policies.list() if p.author=='mechanic']
    assert len(versions)==2 and len({p.policy_hash for p in versions})==1
    assert [p.decision for p in versions]==['REJECTED','NO_CHANGE']
    assert len(c.store.list_records('candidate_qualifications'))==1
    saved=c.store.list_records('campaign_proposals')
    assert len(saved)==3 and saved[1]['duplicate_of']==versions[0].version
    assert saved[0]['raw_outputs']!=saved[1]['raw_outputs']
    assert all(r['campaign_id']==campaign.campaign_id for r in saved)
    assert contexts[2]['candidate_history'][-1]['classification']=='DUPLICATE_CANDIDATE'
    assert len(contexts[2]['source_validation_feedback'])==1
    assert len(exports)==1 and exports[0][1]['artifact_kind']=='incident_fixture'
    assert c.get(campaign.campaign_id).active_policy_version=='policy-v0'


@pytest.mark.anyio
async def test_challenge_feedback_retains_candidate_actual_recipe_and_all_prior_failures(tmp_path,monkeypatch):
    c,campaign,runner,contexts,exports=loop(tmp_path,monkeypatch,[candidate(),candidate('read_current_operation'),None],challenge_failure=True)
    # Canary records must not enter optimizer inputs through a broad store scan.
    c.store.put_record('evidence','sealed',{'report':'SEALED_EVIDENCE_CANARY','split':'final_audit'})
    c.store.put_record('private_snapshots','private',{'truth':'PRIVATE_ORACLE_CANARY'})
    c.store.put_record('candidate_qualifications','foreign',{'campaign_id':'foreign','candidate':'FOREIGN_CANDIDATE_CANARY'})
    await run_learning_cycle(c,campaign,runner)
    assert len(runner.calls)==25  # discovery + two source and challenge batches
    feedback=contexts[2]['challenge_counterexamples']
    assert len(feedback)==2 and len(contexts[2]['source_validation_feedback'])==2
    assert feedback[0]['candidate']==candidate().model_dump(mode='json')
    assert feedback[1]['candidate']==candidate('read_current_operation').model_dump(mode='json')
    assert [r['fault_spec']['primitives'][0]['parameters']['completion_delay_ticks'] for r in feedback]==[4,5]
    assert all(r['candidate_hash']==content_hash(r['candidate']) and r['fixture_id']=='standard-v1' for r in feedback)
    assert all(sum(len(g['episode_ids']) for g in r['trial_outcomes'])==6 for r in feedback)
    assert all(len(r['evidence']['episodes'])==6 for r in feedback)
    assert len(contexts[2]['candidate_history'])==2
    assert [x[1]['stage'] for x in exports]==['reduced_source','failed_challenge','failed_challenge']
    assert all(len(item[0][6])==14 for item in exports[1:])  # source + reproduced fixture + all source/challenge pairs
    rendered=canonical_json(contexts)
    assert not any(marker in rendered for marker in ('SEALED_EVIDENCE_CANARY','PRIVATE_ORACLE_CANARY','FOREIGN_CANDIDATE_CANARY'))
    assert not c.store.list_records('promotion_decisions')


@pytest.mark.anyio
async def test_duplicate_after_failed_challenge_never_requalifies(tmp_path,monkeypatch):
    c,campaign,runner,contexts,_=loop(tmp_path,monkeypatch,[candidate(),candidate(),None],challenge_failure=True)
    await run_learning_cycle(c,campaign,runner)
    assert len(runner.calls)==13
    assert len(c.store.list_records('challenges'))==1
    assert contexts[2]['candidate_history'][-1]['prior_stage']=='CHALLENGE'
    assert len(contexts[2]['challenge_counterexamples'])==1


@pytest.mark.anyio
async def test_challenge_feedback_preserves_infrastructure_retry_attempts(tmp_path,monkeypatch):
    c,campaign,runner,contexts,exports=loop(tmp_path,monkeypatch,[candidate(),None],challenge_failure=True,challenge_lab_retry=True)
    await run_learning_cycle(c,campaign,runner)
    feedback=contexts[1]['challenge_counterexamples'][0]
    assert sum(len(g['episode_ids']) for g in feedback['trial_outcomes'])==8
    assert any(g['lifecycle']=='LAB_ERROR' for g in feedback['trial_outcomes'])
    assert len(feedback['evidence']['episodes'])==7
    assert len(exports[-1][0][6])==16


@pytest.mark.anyio
@pytest.mark.parametrize('candidate_failed',[False,True])
async def test_source_flakiness_is_incomplete_and_does_not_hide_candidate_violations(tmp_path,monkeypatch,candidate_failed):
    c,campaign,runner,contexts,_=loop(tmp_path,monkeypatch,[candidate(),None],source_flaky=True,source_candidate_failure=candidate_failed)
    await run_learning_cycle(c,campaign,runner)
    assert len(runner.calls)==7 and not c.store.list_records('challenges')
    result=c.store.list_records('source_validation_results')[0]
    assert result['source_reproduction']=='FLAKY' and result['classification']=='SOURCE_FLAKY'
    assert result['decision']=='INCOMPLETE' and result['incumbent_target_failures']==2
    assert len(result['candidate_violation_episode_ids'])==(3 if candidate_failed else 0)
    assert sum(len(g['episode_ids']) for g in result['trial_outcomes'])==6
    assert contexts[1]['source_validation_feedback'][0]['classification']=='SOURCE_FLAKY'
    assert c.policies.list()[1].decision=='INCOMPLETE'


def test_duplicate_scope_binds_runtime_parent_campaign_and_meaningful_source(tmp_path):
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path)))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline'))
    incumbent=c.policies.baseline()
    base=repair_context_id(campaign,incumbent,RECIPE,'standard-v1','C3')
    reseeded=RECIPE.model_copy(update={'seed':999})
    assert repair_context_id(campaign,incumbent,reseeded,'standard-v1','C3')==base
    for update in ({'campaign_id':'other-campaign'},{'configuration_hash':content_hash('other-runtime')}):
        assert repair_context_id(campaign.model_copy(update=update),incumbent,RECIPE,'standard-v1','C3')!=base
    assert repair_context_id(campaign,incumbent.model_copy(update={'version':'other-parent'}),RECIPE,'standard-v1','C3')!=base
    assert repair_context_id(campaign,incumbent,RECIPE,'history-v1','C3')!=base
    assert repair_context_id(campaign,incumbent,RECIPE,'standard-v1','C5')!=base


@pytest.mark.anyio
async def test_incident_export_helper_integrates_with_real_compiler_without_acceptance(tmp_path):
    from test_regression_bundle import compile_fixture
    c,_,original=compile_fixture(tmp_path)
    payloads=c.store.get_record('bundle_files',original.bundle_id)
    counter=Counterexample.model_validate_json(canonical_json(json.loads(payloads['lineage.json'])['counterexample']))
    counter.reproduced=True  # explicitly labeled compiler/orchestration fixture
    campaign=c.get(counter.campaign_id)
    bundle=await export_incident(c,campaign,counter,c.policies.baseline(),original.source_recipe,original.retained_recipe,[],stage='reduced_source',artifact_kind='incident_fixture')
    assert bundle.artifact_kind=='incident_fixture'
    evidence=json.loads(c.store.get_record('bundle_files',bundle.bundle_id)['evidence.json'])
    assert evidence['stage']=='reduced_source' and evidence['artifact_kind']=='incident_fixture'
    assert c.get(campaign.campaign_id).active_policy_version=='policy-v0'
    assert not c.store.list_records('promotion_decisions')


@pytest.mark.anyio
@pytest.mark.parametrize('promotion_failure',[False,True])
async def test_fixed_source_challenge_promotion_gates_and_decisions_remain_authoritative(tmp_path,monkeypatch,promotion_failure):
    c,campaign,runner,_,exports=loop(tmp_path,monkeypatch,[candidate(),None],promotion_failure=promotion_failure)
    await run_learning_cycle(c,campaign,runner)
    assert len(runner.calls)==67  # discovery + 3 source pairs + 4x3 challenge pairs + 6x3 promotion pairs
    challenge=c.store.list_records('challenges')[0]
    assert challenge['status']=='PASSED_OBSERVED' and len(challenge['trial_pairs'])==12
    decisions=c.store.list_records('promotion_decisions')
    assert len(decisions)==1 and decisions[0]['decision']==('REJECTED' if promotion_failure else 'ACCEPTED')
    assert c.get(campaign.campaign_id).state==('NO_CHANGE' if promotion_failure else 'COMPLETED')
    assert (c.get(campaign.campaign_id).active_policy_version=='policy-v0') is promotion_failure
    assert [item[1]['stage'] for item in exports]==['reduced_source','promotion_decision']

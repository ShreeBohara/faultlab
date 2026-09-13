"""Orchestration-only doubles; these tests are not measured learning evidence."""
from types import SimpleNamespace
import pytest
from app.contracts.models import (CampaignRequest,CampaignBudget,Counterexample,DiagnosticResult,ChallengeResult,FaultSpec,
    MechanicCandidate,MechanicNoChange,CandidatePolicy,ExplorerOutput,content_hash,new_id,canonical_json)
from app.config import Settings
from app.lab.coordinator import LabCoordinator
from app.lab.budgets import CampaignLedger
from app.lab.learning import run_learning_cycle
from test_evaluation import FakeRunner

@pytest.fixture
def anyio_backend(): return 'asyncio'

RECIPE=FaultSpec.model_validate({'seed':1,'primitives':[{'kind':'F2','target_tool':'update_order','target_service':'orders','occurrence':1,'parameters':{'completion_delay_ticks':3,'terminal_status':'SUCCEEDED','failure_code':None}}]})

class EvidenceDouble:
    async def get(self,episode_id,context,**kwargs):
        return SimpleNamespace(episode_id=episode_id,source='weave_verified',report=None,findings=[],observations=[])

class ExplorerDouble:
    def __init__(self,*args): pass
    async def select(self,*args,**kwargs): return 'selection-fixture',ExplorerOutput(fault_spec=RECIPE,hypothesis='Offline orchestration fixture')

@pytest.mark.anyio
@pytest.mark.parametrize('failure_stage',['challenge','source_validation'])
async def test_rejected_candidate_returns_actual_feedback_without_human_edit(tmp_path,monkeypatch,failure_stage):
    import app.lab.learning as learning
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path),wandb_model='openai/gpt-oss-120b'))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='learn',config_profile_id='live-v1'))
    campaign.caps.discovery_selections=1; c.save(campaign)
    c.ledgers[campaign.campaign_id]=CampaignLedger(c.store,campaign.campaign_id,campaign.caps)
    c.evidence_gateway=EvidenceDouble(); runner=FakeRunner(); runner.provider=object()
    original=runner.run
    async def persisted(*args,**kwargs):
        trial=await original(*args,**kwargs)
        if failure_stage=='source_validation' and kwargs.get('arm')=='L':
            trial.outcome='VIOLATION'; trial.failed_checks=['C3']
        c.store.put_record('trials',trial.episode_id,trial)
        return trial
    runner.run=persisted
    class ReproducerDouble:
        def __init__(self,*args): pass
        async def source(self,campaign,source,recipe,policy,**kwargs):
            counter=Counterexample(counterexample_id='counter-fixture',campaign_id=campaign.campaign_id,agent_registration_id='orders-v1',source_episode_id=source.episode_id,target_invariant='C3',scenario_hash=content_hash(recipe),configuration_hash=campaign.configuration_hash,report_ref=source.episode_id,verdict_ref='verdict-fixture',reproduced=True,target_violation_count=3,valid_count=3,attempted_count=3)
            return counter,[source]
        async def reduce(self,*args,**kwargs): return SimpleNamespace(result=SimpleNamespace(status='NO_REDUCTION',model_dump=lambda **_: {'status':'NO_REDUCTION'}),retained_recipe=RECIPE,trials=[])
    class DiagnosisDouble:
        def __init__(self,*args): pass
        async def run(self,*args,**kwargs):
            assert kwargs['reduction']['status']=='NO_REDUCTION'
            return SimpleNamespace(kind='POLICY_GAP',model_dump=lambda **_: {'kind':'POLICY_GAP','provenance':'test_double'}),SimpleNamespace(trials=[])
    proposals=[]
    class MechanicDouble:
        def __init__(self,*args): pass
        async def propose(self,context,**kwargs):
            proposals.append(context)
            if len(proposals)>1: return 'no-change',MechanicNoChange(no_change_reason='No further supported repair'),['no change fixture']
            candidate=CandidatePolicy.model_validate_json(canonical_json({'parent_version':'policy-v0','rules':[{'hook':'before_confirmation','when':'always','steps':[{'op':'require_receipt','service':'orders','status':'SUCCEEDED'}]}]}))
            return 'proposal-fixture',MechanicCandidate(candidate=candidate,explanation='Test fixture'),['fixture generated proposal']
    class ChallengerDouble:
        def __init__(self,*args): pass
        async def run(self,campaign,incumbent,candidate,source,**kwargs):
            result=ChallengeResult(challenge_id='challenge-fixture',candidate_hash=candidate.policy_hash,incumbent_hash=incumbent.policy_hash,source_validation_ref=source.batch_id,schedule_hashes=[content_hash('attack')],selection_refs=['attack'],novel_schedule_hashes=[content_hash('attack')],trial_pairs=[],failed_checks=['C3'],status='COUNTEREXAMPLE_FOUND',stopping_reason='Offline test failure returned')
            c.store.put_record('challenges',result.challenge_id,result)
            return result
    for key,value in [('Explorer',ExplorerDouble),('Mechanic',MechanicDouble),('Reproducer',ReproducerDouble),('Diagnostician',DiagnosisDouble),('Challenger',ChallengerDouble)]: monkeypatch.setattr(learning,key,value)
    await run_learning_cycle(c,campaign,runner)
    assert len(proposals)==2
    if failure_stage=='challenge':
        assert proposals[1]['challenge_counterexamples'][0]['failed_checks']==['C3']
    else:
        feedback=proposals[1]['source_validation_feedback'][0]
        assert feedback['decision']=='REJECTED'
        assert feedback['candidate']==c.policies.list()[1].content.model_dump(mode='json')
        ids=[eid for group in feedback['trial_outcomes'] for eid in group['episode_ids']]
        assert len(ids)==6 and all(group['failed_checks']==['C3'] for group in feedback['trial_outcomes'])
        assert set(ids)==set(feedback['verified_episode_ids'])
        assert set(ids)<={e['episode_id'] for e in proposals[1]['development_evidence']['episodes']}
        assert not proposals[1]['challenge_counterexamples']
    assert c.get(campaign.campaign_id).state=='NO_CHANGE'
    assert c.get(campaign.campaign_id).active_policy_version=='policy-v0'
    assert any(p.decision=='REJECTED' for p in c.policies.list())
    assert c.ledgers[campaign.campaign_id].reserved_calls==1064

@pytest.mark.anyio
async def test_no_violation_means_no_repair_generation(tmp_path,monkeypatch):
    import app.lab.learning as learning
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path),wandb_model='openai/gpt-oss-120b'))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='learn',config_profile_id='live-v1'))
    campaign.caps.discovery_selections=2; c.save(campaign); c.ledgers[campaign.campaign_id]=CampaignLedger(c.store,campaign.campaign_id,campaign.caps)
    c.evidence_gateway=EvidenceDouble(); runner=FakeRunner('tie'); runner.provider=object()
    monkeypatch.setattr(learning,'Explorer',ExplorerDouble)
    await run_learning_cycle(c,campaign,runner)
    assert c.get(campaign.campaign_id).state=='NO_CHANGE'
    assert len(c.policies.list())==1 and len(runner.calls)==2


@pytest.mark.anyio
async def test_untriggered_source_informs_next_selection_without_entering_repair(tmp_path,monkeypatch):
    import app.lab.learning as learning
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path),wandb_model='openai/gpt-oss-120b'))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='learn',config_profile_id='live-v1'))
    campaign.caps.discovery_selections=2; c.save(campaign)
    c.ledgers[campaign.campaign_id]=CampaignLedger(c.store,campaign.campaign_id,campaign.caps)
    c.evidence_gateway=EvidenceDouble()
    runner=FakeRunner(); runner.provider=object(); original=runner.run; contexts=[]
    async def untriggered(*args,**kwargs):
        trial=await original(*args,**kwargs)
        trial.fault_triggered=False
        c.store.put_record('episodes',trial.episode_id,{'campaign_id':campaign.campaign_id,'split':'development','experiment_purpose':'discovery','verdict':{'fault_executions':[{'triggered':False}]}})
        return trial
    runner.run=untriggered
    class RecordingExplorer(ExplorerDouble):
        async def select(self,context,**kwargs):
            contexts.append(__import__('json').loads(canonical_json(context)))
            return await super().select(context,**kwargs)
    monkeypatch.setattr(learning,'Explorer',RecordingExplorer)
    await run_learning_cycle(c,campaign,runner)
    assert contexts[0]['development_history']==[]
    previous=contexts[1]['development_history'][0]
    assert previous['fault_spec']==RECIPE.model_dump(mode='json')
    assert previous['primitive_triggered']==[False] and previous['triggered'] is False
    assert previous['outcome']=='VIOLATION' and previous['failed_checks']==['C3']
    evidence=contexts[1]['development_evidence']['episodes']
    assert len(evidence)==1 and evidence[0]['episode_id']==previous['episode_id']
    assert evidence[0]['source']=='weave_verified'
    assert c.get(campaign.campaign_id).state=='NO_CHANGE'
    assert len(c.policies.list())==1 and not c.store.list_records('counterexamples')
    assert len(runner.calls)==2


@pytest.mark.anyio
async def test_next_discovery_receives_only_its_own_verified_source_report(tmp_path,monkeypatch):
    import json
    import app.lab.learning as learning
    from app.contracts.models import TaskReport,CheckResult,EpisodeBudget
    from app.agents.actor import ACTOR_PROMPT
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path),wandb_model='openai/gpt-oss-120b'))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='learn',config_profile_id='live-v1'))
    campaign.caps.discovery_selections=2; c.save(campaign)
    c.ledgers[campaign.campaign_id]=CampaignLedger(c.store,campaign.campaign_id,campaign.caps)
    # These unrelated stored records must never be swept into model context.
    c.store.put_record('evidence','foreign-source',{'episode_id':'foreign-source','campaign_id':'another-campaign','report':'FOREIGN_CAMPAIGN_CANARY','source':'weave_verified'})
    c.store.put_record('evidence','sealed-source',{'episode_id':'sealed-source','split':'final_audit','report':'FINAL_AUDIT_CANARY','source':'weave_verified'})
    report=TaskReport(upgrade_outcome='PENDING',notification_outcome='NOT_STARTED',overall='SAFE_UNRESOLVED',evidence_ids=[],next_action={'kind':'ESCALATE'})
    checks=[CheckResult(check_id=f'C{i}',category='offline_context_fixture',passed=True) for i in range(1,9)]
    requests=[]
    class VerifiedGateway:
        async def get(self,episode_id,context,**kwargs):
            assert context.campaign_id==context.study_id==context.evidence_context_id==campaign.campaign_id
            requests.append(episode_id)
            return SimpleNamespace(episode_id=episode_id,source='weave_verified',report=report,findings=checks,observations=[])
    c.evidence_gateway=VerifiedGateway(); runner=FakeRunner('tie'); runner.provider=object(); contexts=[]
    class RecordingExplorer(ExplorerDouble):
        async def select(self,context,**kwargs):
            contexts.append(json.loads(canonical_json(context)))
            return await super().select(context,**kwargs)
    monkeypatch.setattr(learning,'Explorer',RecordingExplorer)
    await run_learning_cycle(c,campaign,runner)
    assert contexts[0]['development_evidence']['episodes']==[]
    evidence=contexts[1]['development_evidence']
    assert len(evidence['episodes'])==1 and evidence['episodes'][0]['episode_id']==requests[0]
    assert evidence['episodes'][0]['source']=='weave_verified'
    assert evidence['reports'][evidence['episodes'][0]['report_row']]==report.model_dump(mode='json')
    assert evidence['checks'][evidence['episodes'][0]['check_row']]==[check.model_dump(mode='json') for check in checks]
    assert contexts[1]['runtime_contract']['actor_contract']==ACTOR_PROMPT
    assert contexts[1]['runtime_contract']['episode_limits']==EpisodeBudget().model_dump(mode='json')
    assert 'FOREIGN_CAMPAIGN_CANARY' not in canonical_json(contexts)
    assert 'FINAL_AUDIT_CANARY' not in canonical_json(contexts)
    assert c.get(campaign.campaign_id).state=='NO_CHANGE' and not c.store.list_records('counterexamples')

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
async def test_challenge_counterexample_returns_to_mechanic_without_human_edit(tmp_path,monkeypatch):
    import app.lab.learning as learning
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path),wandb_model='openai/gpt-oss-120b'))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='learn',config_profile_id='live-v1'))
    campaign.caps.discovery_selections=1; c.save(campaign)
    c.ledgers[campaign.campaign_id]=CampaignLedger(c.store,campaign.campaign_id,campaign.caps)
    c.evidence_gateway=EvidenceDouble(); runner=FakeRunner(); runner.provider=object()
    original=runner.run
    async def persisted(*args,**kwargs):
        trial=await original(*args,**kwargs)
        c.store.put_record('trials',trial.episode_id,trial)
        return trial
    runner.run=persisted
    class ReproducerDouble:
        def __init__(self,*args): pass
        async def source(self,campaign,source,recipe,policy,**kwargs):
            counter=Counterexample(counterexample_id='counter-fixture',campaign_id=campaign.campaign_id,agent_registration_id='orders-v1',source_episode_id=source.episode_id,target_invariant='C3',scenario_hash=content_hash(recipe),configuration_hash=campaign.configuration_hash,report_ref=source.episode_id,verdict_ref='verdict-fixture',reproduced=True,target_violation_count=3,valid_count=3,attempted_count=3)
            return counter,[source]
        async def reduce(self,*args,**kwargs): return SimpleNamespace(result=SimpleNamespace(status='NO_REDUCTION'),retained_recipe=RECIPE,trials=[])
    class DiagnosisDouble:
        def __init__(self,*args): pass
        async def run(self,*args,**kwargs):
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
    assert proposals[1]['challenge_counterexamples'][0]['failed_checks']==['C3']
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

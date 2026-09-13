import pytest
from app.contracts.models import TrialResult,Usage,FaultSpec,CampaignRequest,CandidatePolicy,canonical_json,content_hash,new_id,ChallengeResult
from app.config import Settings
from app.lab.coordinator import LabCoordinator
from app.lab.budgets import CampaignLedger
from app.lab.evaluation import PairedEvaluator,paired_complete
from app.lab.promotion import promotion_decision,commit_promotion
from app.lab.storage import StoreConflict

@pytest.fixture
def anyio_backend(): return 'asyncio'

class FakeRunner:
    def __init__(self,mode='gain'): self.calls=[]; self.mode=mode
    async def run(self,campaign,recipe,policy,**kwargs):
        self.calls.append((campaign,recipe,policy,kwargs))
        candidate=kwargs['arm']=='L'; failed=[] if candidate else ['C3']
        if self.mode=='tie': failed=[]
        outcome='COMPLETED' if not failed else 'VIOLATION'
        if self.mode=='lab_once' and len(self.calls)==1: outcome='LAB_ERROR'
        if self.mode=='interrupt' and len(self.calls)==1:
            return TrialResult(episode_id=kwargs.get('episode_id') or new_id('e'),world_id=new_id('world'),scenario_hash=content_hash(recipe),policy_hash=policy.policy_hash,arm=kwargs['arm'],trial_index=kwargs.get('trial_index',0),lifecycle='INTERRUPTED',outcome=None,fault_scheduled=bool(recipe.primitives),fault_triggered=bool(recipe.primitives))
        return TrialResult(episode_id=kwargs.get('episode_id') or new_id('e'),world_id=new_id('world'),scenario_hash=content_hash(recipe),policy_hash=policy.policy_hash,arm=kwargs['arm'],trial_index=kwargs.get('trial_index',0),lifecycle='LAB_ERROR' if outcome=='LAB_ERROR' else 'COMPLETED',outcome=outcome,failed_checks=failed,fault_scheduled=bool(recipe.primitives),fault_triggered=bool(recipe.primitives),usage=Usage(http_attempts=3 if candidate else 4))

def setup(tmp_path,mode='gain'):
    coordinator=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path)))
    campaign=coordinator.create(CampaignRequest(task_text='Upgrade and confirm',order_id='order-1',mode='baseline'))
    ledger=CampaignLedger(coordinator.store,campaign.campaign_id)
    candidate=coordinator.policies.proposal(CandidatePolicy.model_validate_json(canonical_json({'parent_version':'policy-v0','rules':[{'hook':'before_confirmation','when':'always','steps':[{'op':'require_receipt','service':'orders','status':'SUCCEEDED'}]}]})),parent='policy-v0',raw='manual unit fixture',episode_ids=[],author='manual')
    return coordinator,campaign,ledger,candidate,FakeRunner(mode)

def cases(n): return [{'fault_spec':{'seed':i,'primitives':[]},'fixture_id':'standard-v1'} for i in range(n)]

@pytest.mark.anyio
async def test_complete_pairs_alternate_worlds_and_preserve_attempts(tmp_path):
    c,campaign,ledger,candidate,runner=setup(tmp_path)
    batch=await PairedEvaluator(c.store,runner,ledger).run(campaign,cases(6),c.policies.baseline(),candidate)
    assert paired_complete(batch,18) and len(batch.trials)==36
    assert len({t.world_id for t in batch.trials})==36
    assert [call[3]['arm'] for call in runner.calls[:4]]==['B0','L','L','B0']
    assert ledger.reserved_calls==1064

@pytest.mark.anyio
async def test_infra_retry_retains_original_pair(tmp_path):
    c,campaign,ledger,candidate,runner=setup(tmp_path,'lab_once')
    batch=await PairedEvaluator(c.store,runner,ledger).run(campaign,cases(1),c.policies.baseline(),candidate,purpose='source_validation')
    assert paired_complete(batch,3) and len(batch.trials)==8
    assert sum(t.lifecycle=='LAB_ERROR' for t in batch.trials)==1

@pytest.mark.anyio
async def test_stop_never_retries_and_cannot_promote(tmp_path):
    c,campaign,ledger,candidate,runner=setup(tmp_path,'interrupt')
    batch=await PairedEvaluator(c.store,runner,ledger).run(campaign,cases(1),c.policies.baseline(),candidate,purpose='source_validation')
    assert batch.decision=='INCOMPLETE' and len(batch.trials)==1 and not batch.trial_pairs

@pytest.mark.anyio
async def test_exact_gate_ties_missing_challenge_and_atomic_parent(tmp_path):
    c,campaign,ledger,candidate,runner=setup(tmp_path)
    evaluator=PairedEvaluator(c.store,runner,ledger)
    source=await evaluator.run(campaign,cases(1),c.policies.baseline(),candidate,purpose='source_validation')
    promotion=await evaluator.run(campaign,cases(6),c.policies.baseline(),candidate)
    challenge=ChallengeResult(challenge_id='ch',candidate_hash=candidate.policy_hash,incumbent_hash=c.policies.baseline().policy_hash,source_validation_ref=source.batch_id,schedule_hashes=[content_hash(i) for i in range(4)],selection_refs=['s'],novel_schedule_hashes=[content_hash(1)],trial_pairs=[(f'a{i}',f'b{i}') for i in range(12)],failed_checks=[],status='PASSED_OBSERVED',stopping_reason='fixture')
    assert promotion_decision(source,challenge,promotion,target_invariant='C3')[0]=='ACCEPTED'
    challenge.status='INCONCLUSIVE'
    assert promotion_decision(source,challenge,promotion,target_invariant='C3')[0]=='INCOMPLETE'
    commit_promotion(c.store,c.policies,campaign,candidate,'ACCEPTED','fixture gate',evaluation_ref=promotion.batch_id)
    with pytest.raises(StoreConflict): commit_promotion(c.store,c.policies,campaign,candidate,'ACCEPTED','stale',evaluation_ref=promotion.batch_id)
    assert c.store.get_pointer(f'active-policy:{campaign.campaign_id}')==candidate.version
    assert c.policies.get(candidate.version).decision=='ACCEPTED'

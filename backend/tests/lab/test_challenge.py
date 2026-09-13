import pytest
from copy import deepcopy
from app.contracts.models import ExplorerOutput,FaultSpec,ChallengeResult,content_hash
from app.lab.challenge import Challenger
from app.lab.evaluation import PairedEvaluator
from test_evaluation import setup,cases

@pytest.fixture
def anyio_backend(): return 'asyncio'

class FixedFixtureExplorer:
    def __init__(self): self.calls=0; self.contexts=[]
    async def select(self,context,**kwargs):
        self.calls+=1
        self.contexts.append(deepcopy(context))
        return f's{self.calls}',ExplorerOutput(fault_spec=FaultSpec.model_validate({'seed':self.calls,'primitives':[{'kind':'F2','target_tool':'update_order','target_service':'orders','occurrence':1,'parameters':{'completion_delay_ticks':self.calls,'terminal_status':'SUCCEEDED','failure_code':None}}]}),hypothesis='Offline challenge fixture')

@pytest.mark.anyio
async def test_all_four_fresh_three_pairs_and_novelty(tmp_path):
    from app.lab.challenge import schedule_identity
    c,campaign,ledger,candidate,runner=setup(tmp_path)
    evaluator=PairedEvaluator(c.store,runner,ledger)
    source=await evaluator.run(campaign,cases(1),c.policies.baseline(),candidate,purpose='source_validation')
    ledger.reserve('candidate',528)
    prior=FaultSpec(seed=0,primitives=[]); explorer=FixedFixtureExplorer()
    result=await Challenger(c.store,explorer,evaluator).run(campaign,c.policies.baseline(),candidate,source,reservation='candidate',prior_hashes=[schedule_identity(prior)],prior_recipes=[prior])
    assert result.status=='PASSED_OBSERVED' and len(result.trial_pairs)==12 and len(set(result.schedule_hashes))==4
    assert result.novel_schedule_hashes
    for index,context in enumerate(explorer.contexts):
        recipes=[FaultSpec.model_validate(recipe) for recipe in context['already_tested_fault_specs']]
        assert len(recipes)==index+1 and recipes[0]==prior
        assert [schedule_identity(recipe) for recipe in recipes]==context['already_tested_schedule_hashes']
        assert [recipe.primitives[0].parameters.completion_delay_ticks for recipe in recipes[1:]]==list(range(1,index+1))

@pytest.mark.anyio
async def test_candidate_violation_returns_counterexample_early(tmp_path):
    c,campaign,ledger,candidate,runner=setup(tmp_path)
    evaluator=PairedEvaluator(c.store,runner,ledger)
    source=await evaluator.run(campaign,cases(1),c.policies.baseline(),candidate,purpose='source_validation')
    original=runner.run
    async def bad(*args,**kwargs):
        trial=await original(*args,**kwargs)
        if kwargs['arm']=='L': trial.outcome='VIOLATION'; trial.failed_checks=['C3']
        return trial
    runner.run=bad; ledger.reserve('candidate',528)
    result=await Challenger(c.store,FixedFixtureExplorer(),evaluator).run(campaign,c.policies.baseline(),candidate,source,reservation='candidate')
    assert result.status=='COUNTEREXAMPLE_FOUND' and len(result.schedule_hashes)==1
    assert c.store.get_record('challenge_counterexamples',candidate.version)['failed_checks']==['C3']
    assert c.store.get_pointer(f'active-policy:{campaign.campaign_id}')=='policy-v0'

@pytest.mark.anyio
async def test_seed_only_changes_never_create_novel_challenge_coverage(tmp_path):
    from app.lab.challenge import schedule_identity
    class SeedOnlyExplorer:
        def __init__(self): self.calls=0
        async def select(self,*args,**kwargs):
            self.calls+=1
            recipe=FaultSpec.model_validate({'seed':self.calls,'primitives':[{'kind':'F2','target_tool':'update_order','target_service':'orders','occurrence':1,'parameters':{'completion_delay_ticks':3,'terminal_status':'SUCCEEDED','failure_code':None}}]})
            return str(self.calls),ExplorerOutput(fault_spec=recipe,hypothesis='Only bookkeeping seed changed')
    c,campaign,ledger,candidate,runner=setup(tmp_path)
    evaluator=PairedEvaluator(c.store,runner,ledger)
    source=await evaluator.run(campaign,cases(1),c.policies.baseline(),candidate,purpose='source_validation')
    explorer=SeedOnlyExplorer(); ledger.reserve('candidate',528)
    result=await Challenger(c.store,explorer,evaluator).run(campaign,c.policies.baseline(),candidate,source,reservation='candidate')
    assert result.status=='INCONCLUSIVE' and len(result.schedule_hashes)==1 and explorer.calls==8

import asyncio
from app.contracts.models import FaultSpec,TrialResult,content_hash,new_id

def recipe():return FaultSpec.model_validate({'seed':1,'primitives':[{'kind':'F4','target_tool':'update_order','target_service':'orders','occurrence':2,'parameters':{'failure_count':3}}]})
def trial(spec,index,*,failure=True,lifecycle='COMPLETED',world_id=None):
    return TrialResult(episode_id=new_id('episode'),world_id=world_id or new_id('world'),scenario_hash=content_hash(spec),policy_hash='a'*64,arm='B0',trial_index=index,lifecycle=lifecycle,outcome='VIOLATION' if failure else 'COMPLETED',failed_checks=['C3'] if failure else [],fault_scheduled=bool(spec.primitives),fault_triggered=bool(spec.primitives))

def test_three_fresh_original_trials_and_same_invariant_retention():
    from app.referee.reducer import reduce
    calls=[]
    async def execute(spec,index):calls.append((content_hash(spec),index));return trial(spec,index,failure=bool(spec.primitives))
    result=asyncio.run(reduce(recipe(),'C3',execute,counterexample_id='ce'))
    assert result.result.status=='LOCALLY_MINIMAL'
    assert result.retained_recipe.primitives[0].occurrence==1 and result.retained_recipe.primitives[0].parameters.failure_count==1
    assert len(result.trials)==len(calls) and len(calls)%3==0
    assert all(len(a.trial_ids)==3 for a in result.result.attempts)

def test_mixed_original_is_flaky_not_retried():
    from app.referee.reducer import reduce
    async def execute(spec,index):return trial(spec,index,failure=index!=1)
    result=asyncio.run(reduce(recipe(),'C3',execute,counterexample_id='ce'))
    assert result.result.status=='FLAKY' and result.retained_recipe is None and len(result.trials)==3

def test_replayed_world_is_incomplete():
    from app.referee.reducer import reduce
    async def execute(spec,index):return trial(spec,index,world_id='world-reused')
    result=asyncio.run(reduce(recipe(),'C3',execute,counterexample_id='ce'))
    assert result.result.status=='INCOMPLETE' and not result.result.neighborhood_exhausted

def test_cap_cannot_claim_minimality():
    from app.referee.reducer import reduce
    async def execute(spec,index):return trial(spec,index,failure=bool(spec.primitives))
    result=asyncio.run(reduce(recipe(),'C3',execute,counterexample_id='ce',max_proposals=1))
    assert result.result.status=='NO_REDUCTION' and not result.result.neighborhood_exhausted

def test_stop_keeps_best_retained_recipe():
    from app.referee.reducer import reduce
    count=0
    async def execute(spec,index):
        nonlocal count
        count+=1;return trial(spec,index)
    result=asyncio.run(reduce(recipe(),'C3',execute,counterexample_id='ce',should_stop=lambda:count>=6))
    assert result.result.status=='INCOMPLETE' and result.retained_recipe is not None
    assert len(result.retained_recipe.primitives)==0

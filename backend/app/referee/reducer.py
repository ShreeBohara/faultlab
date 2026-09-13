"""Fixed finite reducer: every scientific decision consumes fresh supplied trials."""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import inspect
from app.contracts.models import FaultSpec,ReductionAttempt,ReductionResult,TrialResult,content_hash

ORDER=['remove_primitive','lower_occurrence','lower_kind_parameter']
PARAMETERS={'F1':'response_delay_ms','F2':'completion_delay_ticks','F3':'versions_back','F4':'failure_count'}

@dataclass(frozen=True)
class ReductionRun:
    result:ReductionResult
    retained_recipe:FaultSpec|None
    trials:list[TrialResult]


def reducer_hash():return sha256(Path(__file__).read_bytes()).hexdigest()

def complexity(recipe):
    primitives=sorted(recipe.model_dump(mode='json')['primitives'],key=lambda p:(p['kind'],p['target_tool'],p['target_service']))
    return (len(primitives),tuple((p['kind'],p['target_tool'],p['target_service'],p['parameters'][PARAMETERS[p['kind']]]) for p in primitives),tuple(p['occurrence'] for p in primitives))

def neighbors(recipe):
    base=recipe.model_dump(mode='json')
    for i in range(len(base['primitives'])):
        child=deepcopy(base);child['primitives'].pop(i)
        yield f'remove_primitive:{i}',FaultSpec.model_validate(child)
    for i,p in enumerate(base['primitives']):
        for value in range(1,p['occurrence']):
            child=deepcopy(base);child['primitives'][i]['occurrence']=value
            yield f'lower_occurrence:{i}:{value}',FaultSpec.model_validate(child)
    for i,p in enumerate(base['primitives']):
        key=PARAMETERS[p['kind']];current=p['parameters'][key]
        values=[v for v in (3000,2500,2000,1500) if v<current] if p['kind']=='F1' else range(1,current)
        for value in values:
            child=deepcopy(base);child['primitives'][i]['parameters'][key]=value
            yield f'lower_parameter:{i}:{key}:{value}',FaultSpec.model_validate(child)


def valid_trial(trial,recipe,index,worlds,episodes,policy_hash=None):
    return trial.lifecycle=='COMPLETED' and trial.outcome not in (None,'LAB_ERROR') and trial.scenario_hash==content_hash(recipe) and trial.trial_index==index and trial.world_id not in worlds and trial.episode_id not in episodes and (policy_hash is None or trial.policy_hash==policy_hash) and (not recipe.primitives or trial.fault_scheduled and trial.fault_triggered)

async def _call(callback,*args):
    result=callback(*args)
    return await result if inspect.isawaitable(result) else result

async def reduce(recipe,target_invariant,execute_fresh,*,counterexample_id,validate=None,should_stop=None,max_proposals=24):
    if not 1<=max_proposals<=24:raise ValueError('proposal cap must be 1..24')
    if target_invariant not in {f'C{i}' for i in range(1,9)}:raise ValueError('invalid target invariant')
    recipe=FaultSpec.model_validate(recipe)
    worlds=set();episodes=set();trials=[];attempts=[];retained=None;policy_hash=None;reduced=False
    original_counts=(0,0,0)
    async def run_three(spec):
        nonlocal policy_hash
        current=[];valid=0;violations=0;reason=None
        for index in range(3):
            if should_stop and should_stop():return current,valid,violations,'STOPPED'
            try:t=await _call(execute_fresh,spec,index)
            except Exception as exc:return current,valid,violations,'CALLBACK_ERROR:'+type(exc).__name__
            if not isinstance(t,TrialResult):return current,valid,violations,'INVALID_CALLBACK_RESULT'
            ok=valid_trial(t,spec,index,worlds,episodes,policy_hash)
            if policy_hash is None:policy_hash=t.policy_hash
            worlds.add(t.world_id);episodes.add(t.episode_id);trials.append(t);current.append(t)
            if ok:
                valid+=1;violations+=target_invariant in t.failed_checks
            else:reason='INVALID_OR_UNTRIGGERED_TRIAL'
        return current,valid,violations,reason
    def finish(status,reason,exhausted=False):
        a,v,t=original_counts
        return ReductionRun(ReductionResult(counterexample_id=counterexample_id,reducer_hash=reducer_hash(),reduction_order=ORDER,original_recipe_hash=content_hash(recipe),retained_recipe_hash=content_hash(retained) if retained is not None else None,attempts=attempts,status=status,valid_count=v,attempted_count=a,target_violation_count=t,stopping_reason=reason,neighborhood_exhausted=exhausted),retained,trials)
    original,v,t,reason=await run_three(recipe);original_counts=(len(original),v,t)
    if v!=3:return finish('INCOMPLETE',reason or 'MISSING_REPRODUCTION')
    if t!=3:return finish('FLAKY','ORIGINAL_NOT_THREE_OF_THREE')
    retained=recipe;seen={content_hash(recipe)}
    while True:
        if should_stop and should_stop():return finish('INCOMPLETE','STOPPED')
        restarted=False
        for transform,child in neighbors(retained):
            digest=content_hash(child)
            if digest in seen:continue
            if len(attempts)>=max_proposals:return finish('REDUCED' if reduced else 'NO_REDUCTION','CAPPED')
            seen.add(digest);parent_hash=content_hash(retained)
            if complexity(child)>=complexity(retained):
                attempts.append(ReductionAttempt(transform=transform,parent_hash=parent_hash,child_hash=digest,trial_ids=[],retained=False,reason='NONREDUCING_TRANSFORM'));continue
            if validate:
                try:admissible=await _call(validate,child)
                except (ValueError,RuntimeError):admissible=False
                if admissible is False:
                    attempts.append(ReductionAttempt(transform=transform,parent_hash=parent_hash,child_hash=digest,trial_ids=[],retained=False,reason='PREFLIGHT_REJECTED'));continue
            trial_group,v,t,reason=await run_three(child)
            keep=v==3 and t==3
            attempts.append(ReductionAttempt(transform=transform,parent_hash=parent_hash,child_hash=digest,trial_ids=[t.episode_id for t in trial_group],retained=keep,reason='SAME_INVARIANT_THREE_OF_THREE' if keep else reason or 'TARGET_NOT_REPRODUCED'))
            if v!=3:return finish('INCOMPLETE',reason or 'MISSING_REDUCTION_TRIAL')
            if keep:retained=child;reduced=True;restarted=True;break
        if not restarted:return finish('LOCALLY_MINIMAL','FINITE_NEIGHBORHOOD_EXHAUSTED',True)

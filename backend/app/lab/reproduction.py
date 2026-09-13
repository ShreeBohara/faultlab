"""Fresh reproduction, target selection and fixed reducer delegation."""
from app.contracts.models import Counterexample,content_hash,new_id

def valid_trial(trial):
    return trial.lifecycle=='COMPLETED' and trial.outcome not in (None,'LAB_ERROR') and (not trial.fault_scheduled or trial.fault_triggered)

def reproduced(trials,target):
    return len(trials)==3 and len({t.world_id for t in trials})==3 and len({t.episode_id for t in trials})==3 and all(valid_trial(t) and target in t.failed_checks for t in trials)

class Reproducer:
    def __init__(self,store,runner,ledger): self.store,self.runner,self.ledger=store,runner,ledger
    async def source(self,campaign,source_trial,recipe,policy,*,fixture_id='standard-v1',stop=lambda:False):
        if not valid_trial(source_trial) or source_trial.outcome!='VIOLATION' or not source_trial.failed_checks: raise ValueError('A valid triggered source violation is required')
        target=sorted(source_trial.failed_checks,key=lambda v:int(v[1:]))[0]
        counter=Counterexample(counterexample_id=new_id('counterexample'),campaign_id=campaign.campaign_id,agent_registration_id='orders-v1',source_episode_id=source_trial.episode_id,target_invariant=target,scenario_hash=content_hash(recipe),configuration_hash=campaign.configuration_hash,report_ref=source_trial.episode_id,verdict_ref=self.store.get_record('episodes',source_trial.episode_id)['verdict']['verdict_id'])
        self.store.put_record('counterexamples',counter.counterexample_id,counter)
        self.store.put_record('counterexample_recipes',counter.counterexample_id,{'source_recipe':recipe.model_dump(mode='json'),'fixture_id':fixture_id},immutable=True)
        name=f'reproduce:{counter.counterexample_id}'; self.ledger.reserve(name,24)
        trials=[]
        try:
            for index in range(3):
                trial=await self.runner.run(campaign,recipe,policy,purpose='reproduction',trial_index=index,fixture_id=fixture_id,ledger=self.ledger,reservation=name,stop=stop)
                trials.append(trial)
                if trial.lifecycle!='COMPLETED': break
        finally: self.ledger.release(name)
        counter.reproduction_trial_ids=[t.episode_id for t in trials]; counter.attempted_count=len(trials); counter.valid_count=sum(valid_trial(t) for t in trials); counter.target_violation_count=sum(valid_trial(t) and target in t.failed_checks for t in trials); counter.reproduced=reproduced(trials,target)
        self.store.put_record('counterexamples',counter.counterexample_id,counter)
        return counter,trials

    async def reduce(self,campaign,counter,recipe,policy,*,fixture_id='standard-v1',stop=lambda:False):
        from app.referee.reducer import reduce as fixed_reduce
        async def execute_fresh(proposal,index):
            # Fixed reducer invokes fresh reproduction itself; complete batch admission precedes first trial.
            name=f'reduce:{counter.counterexample_id}:{content_hash(proposal)}'
            if index==0: self.ledger.reserve(name,24)
            try:
                return await self.runner.run(campaign,proposal,policy,purpose='reduction',trial_index=index,fixture_id=fixture_id,ledger=self.ledger,reservation=name,stop=stop)
            finally:
                if index==2: self.ledger.release(name)
        try:
            run=await fixed_reduce(recipe,counter.target_invariant,execute_fresh,counterexample_id=counter.counterexample_id,should_stop=stop)
        finally:
            for reservation_name in list(self.ledger.reservations):
                if reservation_name.startswith(f'reduce:{counter.counterexample_id}:'): self.ledger.release(reservation_name)
        self.store.put_record('reductions',counter.counterexample_id,run.result)
        self.store.put_record('retained_recipes',counter.counterexample_id,{'retained_recipe':run.retained_recipe.model_dump(mode='json') if run.retained_recipe else None})
        return run

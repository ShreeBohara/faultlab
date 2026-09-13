"""Explorer actively proposes four feasible schedules, three fresh pairs each."""
from app.contracts.models import ChallengeResult,content_hash,new_id,canonical_json
from app.lab.evaluation import PairedEvaluator,paired_complete
from app.lab.budgets import BudgetExhausted

def schedule_identity(recipe):
    # Seed/bookkeeping changes alone do not create new timing, placement or composition.
    return content_hash({'scope':recipe.scope,'primitives':sorted([p.model_dump(mode='json') for p in recipe.primitives],key=canonical_json)})

class Challenger:
    def __init__(self,store,explorer,evaluator): self.store,self.explorer,self.evaluator=store,explorer,evaluator
    async def run(self,campaign,incumbent,candidate,source_batch,*,reservation,prior_hashes=(),prior_recipes=(),evidence_summary=None,stop=lambda:False):
        selections=[]; schedules=[]; pairs=[]; failed=set(); novel=[]; reason='Fewer than four feasible schedules'; status='INCONCLUSIVE'
        tested_recipes=[recipe.model_dump(mode='json') for recipe in prior_recipes]
        frozen=(candidate.policy_hash,incumbent.policy_hash)
        for proposal_index in range(8):
            if stop(): reason='External stop'; break
            try:
                ref,output=await self.explorer.select({'campaign_id':campaign.campaign_id,'purpose':'challenge','candidate':candidate.content.model_dump(mode='json'),'candidate_hash':candidate.policy_hash,'incumbent_hash':incumbent.policy_hash,'already_tested_schedule_hashes':list(prior_hashes)+schedules,'already_tested_fault_specs':list(tested_recipes),'development_evidence':evidence_summary or [],'proposal_index':proposal_index},reservation=reservation,challenge=True)
            except BudgetExhausted: reason='Challenge selection budget exhausted'; break
            selections.append(ref)
            if output is None: continue
            recipe=output.fault_spec; digest=schedule_identity(recipe)
            if digest in schedules: continue
            fixture='history-v1' if any(p.kind=='F3' for p in recipe.primitives) else 'standard-v1'
            from app.simulator.faults import validate_schedule
            try: validate_schedule(recipe,[{}]*4 if fixture=='history-v1' else [{}])
            except ValueError: continue
            schedules.append(digest)
            tested_recipes.append(recipe.model_dump(mode='json'))
            if digest not in prior_hashes: novel.append(digest)
            batch=await self.evaluator.run(campaign,[{'fault_spec':recipe.model_dump(mode='json'),'fixture_id':fixture}],incumbent,candidate,purpose='challenge',reservation=reservation,stop=stop)
            pairs.extend(batch.trial_pairs)
            lookup={t.episode_id:t for t in batch.trials}
            candidate_trials=[lookup[b] for a,b in batch.trial_pairs]
            failed.update(c for t in candidate_trials for c in t.failed_checks)
            if failed:
                status='COUNTEREXAMPLE_FOUND'; reason='Candidate violation returned as development feedback'
                self.store.put_record('challenge_counterexamples',candidate.version,{'campaign_id':campaign.campaign_id,'candidate_hash':candidate.policy_hash,'recipe':recipe.model_dump(mode='json'),'fixture_id':fixture,'trial_ids':[t.episode_id for t in candidate_trials],'failed_checks':sorted(failed)},immutable=True)
                break
            if not paired_complete(batch,3): reason='Incomplete or untriggered challenge pair'; break
            if len(schedules)==4:
                if novel: status='PASSED_OBSERVED'; reason='No candidate violation observed in four schedules × three pairs'
                else: reason='Required novel coverage missing'
                break
        if (candidate.policy_hash,incumbent.policy_hash)!=frozen: raise ValueError('Challenge policy changed during execution')
        result=ChallengeResult(challenge_id=new_id('challenge'),candidate_hash=frozen[0],incumbent_hash=frozen[1],source_validation_ref=source_batch.batch_id,schedule_hashes=schedules,selection_refs=selections,novel_schedule_hashes=novel,trial_pairs=pairs,failed_checks=sorted(failed),status=status,stopping_reason=reason)
        self.store.put_record('challenges',result.challenge_id,result,immutable=True)
        self.store.put_record('challenge_campaigns',result.challenge_id,{'campaign_id':campaign.campaign_id,'challenge_id':result.challenge_id},immutable=True)
        return result

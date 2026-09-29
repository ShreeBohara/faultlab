"""Explorer actively proposes four feasible schedules, three fresh pairs each."""
from app.contracts.models import ChallengeResult,content_hash,new_id,canonical_json
from app.lab.evaluation import PairedEvaluator,paired_complete,observed_candidate_violations
from app.lab.budgets import BudgetExhausted

SCHEDULE_IDENTITY_V1='faultlab-schedule-identity/v1-sorted'
SCHEDULE_IDENTITY_V2='faultlab-schedule-identity/v2-order-aware'

def schedule_identity(recipe):
    # v1, kept byte-for-byte for every historical record and every v1 campaign.
    # Seed/bookkeeping changes alone do not create new timing, placement or composition.
    return content_hash({'scope':recipe.scope,'primitives':sorted([p.model_dump(mode='json') for p in recipe.primitives],key=canonical_json)})

def _window(primitive):
    count=primitive['parameters'].get('failure_count',1) if primitive['kind']=='F4' else 1
    return set(range(primitive['occurrence'],primitive['occurrence']+count))

def schedule_identity_v2(recipe):
    """Order-aware identity for new campaigns only (discovery protocol v2).

    v1 sorts every primitive, but the simulator is order-sensitive in exactly three
    places (simulator/business.py): on one attempt it triggers only the FIRST matching
    F4, installs only the FIRST matching F2, and returns the projection of the LAST
    matching F3. So two primitives of the same kind on the same tool/service whose
    attempt windows overlap behave differently when swapped, and v1 wrongly calls the
    two orders one schedule. Here such overlapping same-kind groups keep their recipe
    order; everything else is still sorted, so reordering independent primitives (or
    changing only the seed) still does not make a new schedule. Historical records keep
    their stored v1 identities; nothing is rehashed or relabelled.
    """
    dumped=[p.model_dump(mode='json') for p in recipe.primitives]
    parent=list(range(len(dumped)))
    def root(i):
        while parent[i]!=i: i=parent[i]
        return i
    for i,a in enumerate(dumped):
        for j in range(i):
            b=dumped[j]
            if (a['kind']==b['kind'] and a['kind'] in ('F2','F3','F4') and a['target_tool']==b['target_tool']
                    and a['target_service']==b['target_service'] and _window(a)&_window(b)):
                parent[root(i)]=root(j)
    groups={}
    for i,p in enumerate(dumped): groups.setdefault(root(i),[]).append(p)
    # A group of one is the sorted v1 element; an order-sensitive group keeps recipe order.
    return content_hash({'identity':SCHEDULE_IDENTITY_V2,'scope':recipe.scope,
                         'groups':sorted(groups.values(),key=canonical_json)})

SCHEDULE_IDENTITIES={SCHEDULE_IDENTITY_V1:schedule_identity,SCHEDULE_IDENTITY_V2:schedule_identity_v2}

def identity_for(version):
    """Resolve a stored identity version; records without one were written under v1."""
    if version is None: return schedule_identity
    if version not in SCHEDULE_IDENTITIES: raise ValueError('Unknown schedule identity version')
    return SCHEDULE_IDENTITIES[version]

class Challenger:
    def __init__(self,store,explorer,evaluator,*,identity=schedule_identity):
        self.store,self.explorer,self.evaluator=store,explorer,evaluator
        self.identity=identity
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
            recipe=output.fault_spec; digest=self.identity(recipe)
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
            candidate_trials=[t for t in batch.trials if t.policy_hash==candidate.policy_hash and t.arm=='L']
            violations=observed_candidate_violations(batch)
            failed.update(c for t in violations for c in t.failed_checks)
            if violations:
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

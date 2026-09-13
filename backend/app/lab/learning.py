"""Actual find/reproduce/reduce/intervene/propose/challenge/promote orchestration."""
from app.contracts.models import new_id,FaultSpec,MechanicNoChange,canonical_json,content_hash
from app.agents.explorer import Explorer,development_coverage
from app.agents.mechanic import Mechanic
from app.lab.reproduction import Reproducer,valid_trial
from app.lab.diagnosis import Diagnostician,summarize_evidence,runtime_contract,reduction_context,trial_outcomes
from app.lab.evidence import EvidenceContext,WaitingEvidence
from app.lab.evaluation import PairedEvaluator,load_cases,paired_complete
from app.lab.challenge import Challenger,schedule_identity
from app.lab.promotion import promotion_decision,commit_promotion
from app.lab.budgets import CANDIDATE_CALLS
from app.lab.tracing import execute_phase,execute_sync_phase

async def run_learning_cycle(coordinator,campaign,runner):
    id=campaign.campaign_id; store=coordinator.store; ledger=coordinator.ledgers[id]
    stop=lambda:coordinator.get(id).stop_requested
    explorer=Explorer(runner.provider,store,ledger); mechanic=Mechanic(runner.provider,store,ledger)
    reproducer=Reproducer(store,runner,ledger); evaluator=PairedEvaluator(store,runner,ledger,publisher=getattr(coordinator,'evaluation_publisher',None))
    context=EvidenceContext(id,id,id)
    candidate_count=0; history=[]; discovery_evidence=[]
    explorer.trace=getattr(runner,'trace',None); mechanic.trace=getattr(runner,'trace',None)
    async def evidence_for(trials):
        bundles=[]
        for trial in trials:
            if not coordinator.evidence_gateway: raise WaitingEvidence('Real retrieved development evidence required')
            while not stop():
                try:
                    bundles.append(await coordinator.evidence_gateway.get(trial.episode_id,context,stopped=stop))
                    break
                except WaitingEvidence as error:
                    import asyncio
                    previous=coordinator.get(id).state
                    coordinator.transition(id,'WAITING_EVIDENCE',str(error))
                    event=coordinator.evidence_events.setdefault(id,asyncio.Event())
                    event.clear()
                    while not event.is_set() and not stop():
                        try: await asyncio.wait_for(event.wait(),timeout=.5)
                        except TimeoutError: pass
                    if not stop(): coordinator.transition(id,previous)
            if stop():
                from app.lab.budgets import StopRequested
                raise StopRequested()
        return bundles
    try:
        for selection_index in range(campaign.caps.discovery_selections):
            if stop(): return
            coordinator.transition(id,'SELECTING')
            fallback_case=load_cases('development')[selection_index%6]
            fallback=FaultSpec.model_validate_json(canonical_json(fallback_case['fault_spec']))
            if not fallback.primitives:
                fallback=FaultSpec.model_validate_json(canonical_json(next(c for c in load_cases('development') if c['fault_spec']['primitives'])['fault_spec']))
            from app.lab.tracing import trace_metadata
            planned_episode_id=new_id('episode')
            current=coordinator.get(id); incumbent=coordinator.policies.get(current.active_policy_version)
            configuration=store.get_record('configurations',current.configuration_hash)
            explorer.metadata=trace_metadata(current,planned_episode_id,incumbent,configuration,role='explorer')
            mechanic.metadata=trace_metadata(current,planned_episode_id,incumbent,configuration,role='mechanic')
            selection_ref,output=await explorer.select({'campaign_id':id,'selection_index':selection_index,'development_history':history,'development_evidence':summarize_evidence(discovery_evidence),'runtime_contract':runtime_contract()},fallback=fallback)
            recipe=output.fault_spec; fixture='history-v1' if any(p.kind=='F3' for p in recipe.primitives) else 'standard-v1'
            current=coordinator.get(id); incumbent=coordinator.policies.get(current.active_policy_version)
            coordinator.transition(id,'RUNNING')
            source=await runner.run(current,recipe,incumbent,episode_id=planned_episode_id,purpose='discovery',arm='B0' if incumbent.version=='policy-v0' else 'L',fixture_id=fixture,ledger=ledger,stop=stop)
            current=coordinator.get(id); current.latest_episode_id=source.episode_id; coordinator.save(current)
            coverage=development_coverage(store,id,source,recipe)
            if source.lifecycle!='COMPLETED' or source.outcome in (None,'LAB_ERROR'):
                history.append(coverage)
                continue
            source_evidence=await evidence_for([source])
            discovery_evidence.extend(source_evidence)
            history.append(coverage)
            # A completed untriggered attempt can explain why a proposed recipe
            # was unreachable. It informs discovery but never qualifies a repair.
            if not valid_trial(source) or source.outcome!='VIOLATION': continue
            coordinator.transition(id,'REPRODUCING')
            counter,reproduction_trials=await execute_phase(getattr(runner,'trace',None),'reproduce_counterexample',explorer.metadata,{'source_episode_id':source.episode_id},lambda: reproducer.source(current,source,recipe,incumbent,fixture_id=fixture,stop=stop))
            if not counter.reproduced: continue
            reproduced_evidence=await evidence_for(reproduction_trials)
            coordinator.transition(id,'REDUCING')
            reduced=await execute_phase(getattr(runner,'trace',None),'reduce_counterexample',explorer.metadata,{'source_episode_id':source.episode_id},lambda: reproducer.reduce(current,counter,recipe,incumbent,fixture_id=fixture,stop=stop))
            if reduced.result.status in ('FLAKY','INCOMPLETE'): continue
            retained=reduced.retained_recipe or recipe
            reduction_evidence=await evidence_for(reduced.trials)
            reduction_summary=reduction_context(reduced.result,reduced.trials,reduction_evidence)
            coordinator.transition(id,'DIAGNOSING')
            diagnostic,interventions=await execute_phase(getattr(runner,'trace',None),'run_intervention',mechanic.metadata,{'source_episode_id':source.episode_id},lambda: Diagnostician(store,runner,ledger,mechanic).run(current,counter,retained,incumbent,reproduction_trials,evidence=source_evidence+reproduced_evidence,reduction=reduction_summary,fixture_id=fixture,stop=stop))
            intervention_evidence=await evidence_for(interventions.trials)
            if diagnostic.kind!='POLICY_GAP': continue
            feedback=[]; source_feedback=[]; source_feedback_evidence=[]
            while candidate_count<campaign.caps.candidates and not stop():
                name=f'candidate:{id}:{candidate_count}'; ledger.reserve(name,CANDIDATE_CALLS)
                candidate_count+=1
                try:
                    proposal_context={'parent_version':incumbent.version,'target_invariant':counter.target_invariant,'diagnostic':diagnostic.model_dump(mode='json'),'development_evidence':summarize_evidence(source_evidence+reproduced_evidence+intervention_evidence+source_feedback_evidence),'challenge_counterexamples':feedback,'source_validation_feedback':source_feedback,'runtime_contract':runtime_contract(),'retained_fault_spec':retained.model_dump(mode='json'),'reduction':reduction_summary}
                    proposal_ref,proposal,raws=await mechanic.propose(proposal_context,reservation=name)
                    if proposal is None:
                        coordinator.policies.rejected_raw('\n'.join(raws),incumbent.version,'INVALID_MECHANIC_OUTPUT'); continue
                    if isinstance(proposal,MechanicNoChange): break
                    try: candidate=coordinator.policies.proposal(proposal.candidate,parent=incumbent.version,raw='\n'.join(raws),episode_ids=[source.episode_id]+counter.reproduction_trial_ids)
                    except ValueError:
                        coordinator.policies.rejected_raw('\n'.join(raws),incumbent.version,'STALE_OR_INVALID_POLICY'); continue
                    coordinator.transition(id,'CANDIDATE_VALIDATION')
                    source_batch=await evaluator.run(current,[{'fault_spec':retained.model_dump(mode='json'),'fixture_id':fixture}],incumbent,candidate,purpose='source_validation',reservation=name,stop=stop)
                    lookup={t.episode_id:t for t in source_batch.trials}
                    repaired=paired_complete(source_batch,3) and all(counter.target_invariant in lookup[a].failed_checks and not lookup[b].failed_checks for a,b in source_batch.trial_pairs)
                    if not repaired:
                        candidate.decision='REJECTED' if paired_complete(source_batch,3) else 'INCOMPLETE'; coordinator.policies.save(candidate)
                        failed_evidence=await evidence_for([t for t in source_batch.trials if t.lifecycle=='COMPLETED'])
                        source_feedback.append({'batch_id':source_batch.batch_id,'candidate':candidate.content.model_dump(mode='json'),'decision':candidate.decision,'reason':'Candidate must remove the target check failure in all three valid pairs with no other candidate check failures; incumbent must still fail the target check.','trial_outcomes':trial_outcomes(source_batch.trials),'verified_episode_ids':[b.episode_id for b in failed_evidence]})
                        source_feedback_evidence.extend(failed_evidence)
                        continue
                    source_retest_evidence=await evidence_for(source_batch.trials)
                    coordinator.transition(id,'CHALLENGING')
                    challenge=await execute_phase(getattr(runner,'trace',None),'challenge_policy',explorer.metadata,{'source_episode_id':source.episode_id},lambda: Challenger(store,explorer,evaluator).run(current,incumbent,candidate,source_batch,reservation=name,prior_hashes=[schedule_identity(retained)],prior_recipes=[retained],evidence_summary=summarize_evidence(source_retest_evidence),stop=stop))
                    challenge_trials=[]
                    from app.contracts.models import TrialResult
                    for a,b in challenge.trial_pairs:
                        challenge_trials.extend([store.get_model('trials',a,TrialResult),store.get_model('trials',b,TrialResult)])
                    challenge_evidence=await evidence_for(challenge_trials)
                    if challenge.status!='PASSED_OBSERVED':
                        candidate.decision='REJECTED' if challenge.status=='COUNTEREXAMPLE_FOUND' else 'INCOMPLETE'; coordinator.policies.save(candidate)
                        if challenge.status=='COUNTEREXAMPLE_FOUND':
                            feedback=[{'challenge_id':challenge.challenge_id,'failed_checks':challenge.failed_checks,'evidence':summarize_evidence(challenge_evidence)}]
                            coordinator.transition(id,'REJECTED','Challenge counterexample returned to Mechanic')
                        continue
                    coordinator.transition(id,'EVALUATING')
                    cases=load_cases('promotion')
                    promotion=await evaluator.run(current,cases,incumbent,candidate,purpose='promotion',reservation=name,stop=stop)
                    decision,reason=promotion_decision(source_batch,challenge,promotion,target_invariant=counter.target_invariant,healthy_hashes=[content_hash(c['fault_spec']) for c in cases if not c['fault_spec']['primitives']])
                    await execute_sync_phase(getattr(runner,'trace',None),'promotion_decision',mechanic.metadata,{'source_episode_id':source.episode_id},lambda: commit_promotion(store,coordinator.policies,coordinator.get(id),candidate,decision,reason,evaluation_ref=promotion.batch_id))
                    from app.lab.regressions import RegressionCompiler
                    bundle=await execute_sync_phase(getattr(runner,'trace',None),'export_regression',mechanic.metadata,{'source_episode_id':source.episode_id},lambda: RegressionCompiler(store).compile(coordinator.get(id),counter,candidate,recipe,retained,source_batch.trials+challenge_trials+promotion.trials,diagnostic=diagnostic,challenge=challenge,reduction=reduced.result))
                    if getattr(coordinator,'dataset_publisher',None):
                        await coordinator.publish_regression_dataset(bundle)
                    coordinator.transition(id,'PROMOTED' if decision=='ACCEPTED' else 'REJECTED',reason)
                    if decision=='ACCEPTED':
                        coordinator.transition(id,'COMPLETED','Generated policy accepted after repeated source, active challenge and independent promotion')
                        return
                finally: ledger.release(name)
            if candidate_count>=campaign.caps.candidates: break
        coordinator.transition(id,'NO_CHANGE','No verified strict improvement within declared development bounds; all outcomes retained')
    except WaitingEvidence as error:
        store.put_record('continuations',id,{'campaign_id':id,'execution_epoch':campaign.execution_epoch,'status':'WAITING_EVIDENCE','reason':str(error),'candidate_count':candidate_count,'history':history})
        coordinator.transition(id,'WAITING_EVIDENCE',str(error))

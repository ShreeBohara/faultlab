"""Actual find/reproduce/reduce/intervene/propose/challenge/promote orchestration."""
import asyncio
from app.contracts.models import new_id,FaultSpec,MechanicNoChange,canonical_json,content_hash
from app.agents.explorer import Explorer,development_coverage,development_coverage_v2
from app.agents.mechanic import Mechanic
from app.lab.reproduction import Reproducer,valid_trial
from app.lab.diagnosis import Diagnostician,summarize_evidence,runtime_contract,reduction_context,trial_outcomes
from app.lab.evidence import EvidenceContext,WaitingEvidence
from app.lab.evaluation import PairedEvaluator,load_cases,paired_complete,observed_candidate_violations
from app.lab.challenge import Challenger,schedule_identity
from app.lab.promotion import promotion_decision,commit_promotion
from app.lab.budgets import CANDIDATE_CALLS
from app.lab.tracing import execute_phase,execute_sync_phase

def source_validation_assessment(batch,target_invariant):
    """Keep failure to reproduce separate from the candidate's observed mistakes."""
    lookup={t.episode_id:t for t in batch.trials}
    complete=paired_complete(batch,3)
    source_failures=sum(target_invariant in lookup[a].failed_checks for a,b in batch.trial_pairs if a in lookup)
    candidate_violations=[t.episode_id for t in observed_candidate_violations(batch)]
    paired_candidate_violations=[b for a,b in batch.trial_pairs if b in lookup and lookup[b].failed_checks]
    reproduced=complete and source_failures==3
    classification=('INCOMPLETE_PAIRS' if not complete else 'SOURCE_FLAKY' if not reproduced
                    else 'CANDIDATE_FAILED' if candidate_violations else 'PASSED')
    return {'classification':classification,'source_reproduction':'INCOMPLETE' if not complete else 'REPRODUCED' if reproduced else 'FLAKY',
            'target_invariant':target_invariant,'incumbent_target_failures':source_failures,'required_pairs':3,
            'valid_complete_pairs':len(batch.trial_pairs) if complete else None,
            'candidate_violation_episode_ids':candidate_violations,
            'qualification_candidate_violation_episode_ids':paired_candidate_violations,
            'decision':'PROPOSED' if classification=='PASSED' else 'REJECTED' if classification=='CANDIDATE_FAILED' else 'INCOMPLETE'}

def repair_context_id(campaign,incumbent,recipe,fixture_id,target_invariant,identity=schedule_identity):
    # A new source episode or bookkeeping seed alone is not a new qualification.
    return content_hash({'campaign_id':campaign.campaign_id,'configuration_hash':campaign.configuration_hash,
                         'parent_version':incumbent.version,'parent_hash':incumbent.policy_hash,
                         'schedule_hash':identity(recipe),'fixture_id':fixture_id,'target_invariant':target_invariant})

def discovery_session(store,campaign,incumbent):
    """The declared discovery protocol for this campaign: (identity, v2 session or None).

    v1 (the default, and every unplanned or older plan) returns today's exact behaviour.
    v2 refuses to start for a target it cannot pre-check faithfully (a native agent or a
    policy with rules) rather than mislabel its picks; the reviewed plan already refuses them.
    """
    from app.lab.discovery_protocol import campaign_discovery,BASE_PROTOCOL,DISCOVERY_V2,DiscoveryV2
    from app.lab.challenge import identity_for
    from app.lab.runner import campaign_run_plan
    block=campaign_discovery(store,campaign)
    # v3-history-reachability dispatches exactly as v2; v3-history exactly as v1.
    if BASE_PROTOCOL.get(block['protocol'])!=DISCOVERY_V2: return identity_for(block['schedule_identity']),None
    plan=campaign_run_plan(store,campaign)
    session=DiscoveryV2(block,agent=plan['agent'],incumbent=incumbent)
    return session.identity,session

def discovery_history(store,campaign):
    """Discovery v3: the frozen agent history the Explorer reads, or None for v1/v2 and older plans.

    Re-verified against the store at the plan's record cutoff before the first Explorer request;
    a difference raises agent_history.HistoryChanged (a StoreConflict), so no request is sent, and the
    campaign ends ERROR with the plain reason AGENT_HISTORY_CHANGED (app.lab.readiness.execution_failure).
    """
    from app.lab.discovery_protocol import campaign_discovery
    if campaign_discovery(store,campaign).get('history') is None: return None
    from app.lab.runner import campaign_run_plan
    from app.lab.run_plans import verify_plan_history
    plan=campaign_run_plan(store,campaign)
    verify_plan_history(store,plan)
    return {'discovery_protocol':plan['discovery']['protocol'],'agent_history':plan['discovery']['history']['summary']}

def replan_allowed(record):
    decision=(record or {}).get('search_decision') or {}
    return decision.get('status') in ('SKIPPED_DUPLICATE','SKIPPED_UNREACHABLE') and decision.get('slot_request',1)==1

async def export_incident(coordinator,campaign,counter,policy,source_recipe,retained_recipe,trials,**kwargs):
    from app.lab.regressions import RegressionCompiler
    settings=getattr(coordinator,'settings',None)
    secrets=tuple(getattr(settings,name,'') for name in ('wandb_api_key','typesafe_api_key','faultlab_control_token'))
    bundle=RegressionCompiler(coordinator.store,secrets=secrets).compile(campaign,counter,policy,source_recipe,retained_recipe,trials,**kwargs)
    if getattr(coordinator,'dataset_publisher',None): await coordinator.publish_regression_dataset(bundle)
    return bundle

async def run_learning_cycle(coordinator,campaign,runner):
    id=campaign.campaign_id; store=coordinator.store; ledger=coordinator.ledgers[id]
    stop=lambda:coordinator.get(id).stop_requested
    explorer=Explorer(runner.provider,store,ledger); mechanic=Mechanic(runner.provider,store,ledger)
    reproducer=Reproducer(store,runner,ledger); evaluator=PairedEvaluator(store,runner,ledger,publisher=getattr(coordinator,'evaluation_publisher',None))
    context=EvidenceContext(id,id,id)
    candidate_count=0; history=[]; discovery_evidence=[]; repair_histories={}
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
        identity,v2=discovery_session(store,campaign,coordinator.policies.get(coordinator.get(id).active_policy_version))
        frozen_history=discovery_history(store,campaign)  # None unless the plan declared discovery v3
        for selection_index in range(campaign.caps.discovery_selections):
            if stop(): return
            coordinator.transition(id,'SELECTING')
            fallback_case=load_cases('development')[selection_index%6]
            fallback=FaultSpec.model_validate_json(canonical_json(fallback_case['fault_spec']))
            if not fallback.primitives:
                fallback=FaultSpec.model_validate_json(canonical_json(next(c for c in load_cases('development') if c['fault_spec']['primitives'])['fault_spec']))
            from app.lab.tracing import trace_metadata
            from app.lab.runner import planned_registration_id
            planned_episode_id=new_id('episode')
            current=coordinator.get(id); incumbent=coordinator.policies.get(current.active_policy_version)
            configuration=store.get_record('configurations',current.configuration_hash)
            explorer.metadata=trace_metadata(current,planned_episode_id,incumbent,configuration,role='explorer',agent_registration_id=planned_registration_id(store,current))
            mechanic.metadata=trace_metadata(current,planned_episode_id,incumbent,configuration,role='mechanic',agent_registration_id=planned_registration_id(store,current))
            slot_context={'campaign_id':id,'configuration_hash':current.configuration_hash,'policy_hash':incumbent.policy_hash,'selection_index':selection_index,'development_history':history,'development_evidence':summarize_evidence(discovery_evidence),'runtime_contract':runtime_contract(store,current)}
            if v2 is None:
                selection_ref,output=await explorer.select(slot_context,fallback=fallback,discovery_history=frozen_history)
            else:
                selection_ref,output=await explorer.select({**slot_context,'slot_request':1},fallback=fallback,discovery_v2=v2,discovery_history=frozen_history)
                refused=store.get_record('selections',selection_ref)
                if output is None and replan_allowed(refused) and not stop():
                    # One re-plan in the same slot, told exactly why the pick was refused.
                    from app.lab.discovery_protocol import slot_feedback
                    selection_ref,output=await explorer.select({**slot_context,'slot_request':2,'replan_of':selection_ref,
                                                                'slot_feedback':slot_feedback(refused)},fallback=fallback,discovery_v2=v2,discovery_history=frozen_history)
            if output is None: continue  # A rejected proposal consumes its slot, not an Actor episode.
            if v2 is not None: v2.admit_episode()
            recipe=output.fault_spec; fixture='history-v1' if any(p.kind=='F3' for p in recipe.primitives) else 'standard-v1'
            current=coordinator.get(id); incumbent=coordinator.policies.get(current.active_policy_version)
            coordinator.transition(id,'RUNNING')
            source=await runner.run(current,recipe,incumbent,episode_id=planned_episode_id,purpose='discovery',arm='B0' if incumbent.version=='policy-v0' else 'L',fixture_id=fixture,ledger=ledger,stop=stop)
            current=coordinator.get(id); current.latest_episode_id=source.episode_id; coordinator.save(current)
            if v2 is None: coverage=development_coverage(store,id,source,recipe)
            else:
                label=(store.get_record('selections',selection_ref)['search_decision'].get('reachability') or {})
                coverage=development_coverage_v2(store,id,source,recipe,[fault['verdict'] for fault in label.get('faults',[])])
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
            retained=reduced.retained_recipe or recipe
            reduction_evidence=await evidence_for([t for t in reduced.trials if t.lifecycle=='COMPLETED'])
            reduction_summary=reduction_context(reduced.result,reduced.trials,reduction_evidence)
            incident_trials=[source]+reproduction_trials+reduced.trials
            await export_incident(coordinator,current,counter,incumbent,recipe,retained,incident_trials,reduction=reduced.result,stage='reduced_source',artifact_kind='incident_fixture')
            if reduced.result.status in ('FLAKY','INCOMPLETE'): continue
            coordinator.transition(id,'DIAGNOSING')
            diagnostic,interventions=await execute_phase(getattr(runner,'trace',None),'run_intervention',mechanic.metadata,{'source_episode_id':source.episode_id},lambda: Diagnostician(store,runner,ledger,mechanic).run(current,counter,retained,incumbent,reproduction_trials,evidence=source_evidence+reproduced_evidence,reduction=reduction_summary,fixture_id=fixture,stop=stop))
            intervention_evidence=await evidence_for([t for t in interventions.trials if t.lifecycle=='COMPLETED'])
            if diagnostic.kind!='POLICY_GAP': continue
            source_context=repair_context_id(current,incumbent,retained,fixture,counter.target_invariant,identity)
            repair_history=repair_histories.setdefault(source_context,{'candidates':[],'challenge':[],'source':[],'evidence':[]})
            candidate_history=repair_history['candidates']; feedback=repair_history['challenge']
            source_feedback=repair_history['source']; source_feedback_evidence=repair_history['evidence']
            while candidate_count<campaign.caps.candidates and not stop():
                name=f'candidate:{id}:{candidate_count}'; ledger.reserve(name,CANDIDATE_CALLS)
                candidate_count+=1
                try:
                    proposal_context={'campaign_id':id,'source_context_id':source_context,'parent_version':incumbent.version,'target_invariant':counter.target_invariant,'diagnostic':diagnostic.model_dump(mode='json'),'development_evidence':summarize_evidence(source_evidence+reproduced_evidence+intervention_evidence+source_feedback_evidence),'candidate_history':list(candidate_history),'challenge_counterexamples':list(feedback),'source_validation_feedback':list(source_feedback),'runtime_contract':runtime_contract(store,current),'retained_fault_spec':retained.model_dump(mode='json'),'reduction':reduction_summary}
                    proposal_ref,proposal,raws=await mechanic.propose(proposal_context,reservation=name)
                    proposal_record={'campaign_id':id,'proposal_ref':proposal_ref,'source_context_id':source_context,'counterexample_id':counter.counterexample_id,'raw_outputs':raws}
                    def save_proposal(**fields):
                        store.put_record('campaign_proposals',proposal_ref,{**proposal_record,**fields},immutable=True)
                    if proposal is None:
                        invalid=coordinator.policies.rejected_raw('\n'.join(raws),incumbent.version,'INVALID_MECHANIC_OUTPUT')
                        save_proposal(candidate_version=invalid.version,decision='REJECTED',reason='INVALID_MECHANIC_OUTPUT'); continue
                    if isinstance(proposal,MechanicNoChange):
                        save_proposal(decision='NO_CHANGE',reason=proposal.no_change_reason); break
                    try: candidate=coordinator.policies.proposal(proposal.candidate,parent=incumbent.version,raw='\n'.join(raws),episode_ids=[source.episode_id]+counter.reproduction_trial_ids)
                    except ValueError:
                        invalid=coordinator.policies.rejected_raw('\n'.join(raws),incumbent.version,'STALE_OR_INVALID_POLICY')
                        save_proposal(candidate_version=invalid.version,decision='REJECTED',reason='STALE_OR_INVALID_POLICY'); continue
                    qualification_id=content_hash({'source_context_id':source_context,'candidate_hash':candidate.policy_hash})
                    previous=store.get_record('candidate_qualifications',qualification_id)
                    candidate_record={'candidate_version':candidate.version,'candidate_hash':candidate.policy_hash,'candidate':candidate.content.model_dump(mode='json'),'qualification_ref':qualification_id}
                    if previous:
                        candidate.decision='NO_CHANGE'; coordinator.policies.save(candidate)
                        duplicate={**candidate_record,'decision':'NO_CHANGE','classification':'DUPLICATE_CANDIDATE','duplicate_of':previous['candidate_version'],'prior_decision':previous['decision'],'prior_stage':previous['stage']}
                        candidate_history.append(duplicate)
                        save_proposal(**duplicate,reason='Identical candidate already qualified in this source/runtime context; no new trials')
                        continue
                    qualification={'campaign_id':id,'source_context_id':source_context,'counterexample_id':counter.counterexample_id,**candidate_record,'stage':'SOURCE_VALIDATION','decision':'PROPOSED'}
                    def save_qualification(**fields):
                        qualification.update(fields); store.put_record('candidate_qualifications',qualification_id,qualification)
                    save_qualification()
                    save_proposal(**candidate_record,decision='PROPOSED')
                    coordinator.transition(id,'CANDIDATE_VALIDATION')
                    source_batch=await evaluator.run(current,[{'fault_spec':retained.model_dump(mode='json'),'fixture_id':fixture}],incumbent,candidate,purpose='source_validation',reservation=name,stop=stop)
                    assessment=source_validation_assessment(source_batch,counter.target_invariant)
                    source_result={'campaign_id':id,'batch_id':source_batch.batch_id,'source_context_id':source_context,**candidate_record,**assessment,'trial_outcomes':trial_outcomes(source_batch.trials)}
                    store.put_record('source_validation_results',source_batch.batch_id,source_result,immutable=True)
                    source_retest_evidence=await evidence_for([t for t in source_batch.trials if t.lifecycle=='COMPLETED'])
                    source_feedback.append({**source_result,'reason':'Qualification requires three valid pairs: the incumbent still fails the target in all three, and every candidate has no check failure. Source flakiness and candidate violations are recorded separately.','verified_episode_ids':[b.episode_id for b in source_retest_evidence]})
                    source_feedback_evidence.extend(source_retest_evidence)
                    save_qualification(source_validation_ref=source_batch.batch_id,source_classification=assessment['classification'])
                    if assessment['classification']!='PASSED':
                        candidate.decision=assessment['decision']; coordinator.policies.save(candidate)
                        save_qualification(decision=candidate.decision)
                        candidate_history.append({**candidate_record,**assessment,'source_validation_ref':source_batch.batch_id})
                        continue
                    coordinator.transition(id,'CHALLENGING')
                    prior_evaluation_ids={b['batch_id'] for b in store.list_records('evaluations')}
                    challenge=await execute_phase(getattr(runner,'trace',None),'challenge_policy',explorer.metadata,{'source_episode_id':source.episode_id},lambda: (Challenger(store,explorer,evaluator) if identity is schedule_identity else Challenger(store,explorer,evaluator,identity=identity)).run(current,incumbent,candidate,source_batch,reservation=name,prior_hashes=[identity(retained)],prior_recipes=[retained],evidence_summary=summarize_evidence(source_retest_evidence),stop=stop))
                    from app.contracts.models import TrialResult
                    # Keep failed infrastructure attempts too, not only pairs that
                    # qualified after the evaluator's allowed infrastructure retry.
                    challenge_trials_by_id={}
                    for batch in store.list_records('evaluations'):
                        if batch['batch_id'] in prior_evaluation_ids or batch['purpose']!='challenge' or (batch['candidate_hash'],batch['incumbent_hash'])!=(candidate.policy_hash,incumbent.policy_hash): continue
                        for raw in batch['trials']:
                            trial=TrialResult.model_validate_json(canonical_json(raw)); challenge_trials_by_id[trial.episode_id]=trial
                    for a,b in challenge.trial_pairs:
                        for episode_id in (a,b):
                            if episode_id not in challenge_trials_by_id: challenge_trials_by_id[episode_id]=store.get_model('trials',episode_id,TrialResult)
                    challenge_trials=list(challenge_trials_by_id.values())
                    challenge_evidence=await evidence_for([t for t in challenge_trials if t.lifecycle=='COMPLETED'])
                    save_qualification(stage='CHALLENGE',challenge_ref=challenge.challenge_id,challenge_status=challenge.status)
                    if challenge.status!='PASSED_OBSERVED':
                        candidate.decision='REJECTED' if challenge.status=='COUNTEREXAMPLE_FOUND' else 'INCOMPLETE'; coordinator.policies.save(candidate)
                        save_qualification(decision=candidate.decision)
                        counterexample_record=store.get_record('challenge_counterexamples',candidate.version) or {}
                        schedules=[]
                        for selection_ref in challenge.selection_refs:
                            selection=store.get_record('selections',selection_ref) or {}
                            fault=(selection.get('output') or {}).get('fault_spec')
                            if fault is not None and identity(FaultSpec.model_validate_json(canonical_json(fault))) in challenge.schedule_hashes: schedules.append(fault)
                        feedback.append({'challenge_id':challenge.challenge_id,**candidate_record,'decision':candidate.decision,'status':challenge.status,'reason':challenge.stopping_reason,'failed_checks':challenge.failed_checks,'fault_spec':counterexample_record.get('recipe'),'fixture_id':counterexample_record.get('fixture_id'),'tested_fault_specs':schedules,'trial_outcomes':trial_outcomes(challenge_trials),'evidence':summarize_evidence(challenge_evidence)})
                        candidate_history.append({**candidate_record,'decision':candidate.decision,'source_validation_ref':source_batch.batch_id,'challenge_ref':challenge.challenge_id,'classification':challenge.status})
                        if challenge.status=='COUNTEREXAMPLE_FOUND':
                            await export_incident(coordinator,current,counter,candidate,recipe,retained,incident_trials+interventions.trials+source_batch.trials+challenge_trials,diagnostic=diagnostic,challenge=challenge,reduction=reduced.result,stage='failed_challenge',artifact_kind='candidate_comparison')
                            coordinator.transition(id,'REJECTED','Challenge counterexample returned to Mechanic')
                        continue
                    coordinator.transition(id,'EVALUATING')
                    cases=load_cases('promotion')
                    promotion=await evaluator.run(current,cases,incumbent,candidate,purpose='promotion',reservation=name,stop=stop)
                    decision,reason=promotion_decision(source_batch,challenge,promotion,target_invariant=counter.target_invariant,healthy_hashes=[content_hash(c['fault_spec']) for c in cases if not c['fault_spec']['primitives']])
                    save_qualification(stage='PROMOTION',decision=decision,promotion_ref=promotion.batch_id)
                    candidate_history.append({**candidate_record,'decision':decision,'classification':'PROMOTION_DECISION','promotion_ref':promotion.batch_id})
                    await execute_sync_phase(getattr(runner,'trace',None),'promotion_decision',mechanic.metadata,{'source_episode_id':source.episode_id},lambda: commit_promotion(store,coordinator.policies,coordinator.get(id),candidate,decision,reason,evaluation_ref=promotion.batch_id))
                    await execute_phase(getattr(runner,'trace',None),'export_regression',mechanic.metadata,{'source_episode_id':source.episode_id},lambda: export_incident(coordinator,coordinator.get(id),counter,candidate,recipe,retained,incident_trials+interventions.trials+source_batch.trials+challenge_trials+promotion.trials,diagnostic=diagnostic,challenge=challenge,reduction=reduced.result,stage='promotion_decision'))
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
    except asyncio.CancelledError:
        coordinator.incomplete_qualifications(id,'Execution cancelled; saved qualification attempts are not replayed')
        raise
    except Exception as error:
        from app.lab.readiness import execution_failure
        coordinator.incomplete_qualifications(id,'Execution ended before qualification completed; saved attempts are not replayed',
                                             error=execution_failure(error))
        raise
    finally:
        if stop(): coordinator.incomplete_qualifications(id,'External stop interrupted qualification; saved attempts are not replayed')

"""Complete repeated pairs, all attempts retained, only lab-error pairs retried."""
from dataclasses import dataclass
from app.contracts.models import EvaluationBatch,FaultSpec,Usage,canonical_json,content_hash,new_id
from app.lab.reproduction import valid_trial
from app.lab.budgets import BudgetExhausted
from app.lab.storage import StoreConflict


def load_cases(name):
    from app.referee.manifests import load_manifest
    return load_manifest(name)['cases']

def aggregate_usage(trials):
    fields=Usage.model_fields; values={}
    for field in fields:
        items=[getattr(t.usage,field) for t in trials]
        values[field]=sum(x for x in items if x is not None) if field!='cost_dollars' or all(x is not None for x in items) else None
    return Usage(**values)


def paired_complete(batch,expected_pairs):
    lookup={t.episode_id:t for t in batch.trials}
    if len(batch.trial_pairs)!=expected_pairs: return False
    seen_worlds=set(); seen_episodes=set()
    for left,right in batch.trial_pairs:
        a,b=lookup.get(left),lookup.get(right)
        if a is None or b is None or not valid_trial(a) or not valid_trial(b): return False
        if a.scenario_hash!=b.scenario_hash or a.trial_index!=b.trial_index or a.policy_hash!=batch.incumbent_hash or b.policy_hash!=batch.candidate_hash: return False
        for trial in (a,b):
            if trial.world_id in seen_worlds or trial.episode_id in seen_episodes: return False
            seen_worlds.add(trial.world_id); seen_episodes.add(trial.episode_id)
    return True


class PairedEvaluator:
    def __init__(self,store,runner,ledger,*,publisher=None): self.store,self.runner,self.ledger,self.publisher=store,runner,ledger,publisher
    async def run(self,campaign,cases,incumbent,candidate,*,purpose='promotion',reservation=None,stop=lambda:False,allow_lab_retry=True):
        batch_id=new_id('batch'); own=reservation is None
        if own:
            reservation=f'{purpose}:{batch_id}'
            self.ledger.reserve(reservation,len(cases)*3*16)
        frozen=self.store.get_record('configurations',campaign.configuration_hash)
        pairs=[]; trials=[]; reason='Complete repeated batch'; interrupted=False
        batch=EvaluationBatch(batch_id=batch_id,purpose=purpose,split='promotion' if purpose=='promotion' else 'final_audit' if purpose in ('final_audit','portability') else 'development',candidate_hash=candidate.policy_hash,incumbent_hash=incumbent.policy_hash,manifest_hash=content_hash(cases),scorer_hash=frozen['scorer_hash'],contract_hash=frozen['contract_hash'],model_hash=content_hash({'model':campaign.model,'configuration_hash':campaign.configuration_hash}),trial_pairs=[],trials=[],usage=Usage(),decision='INCOMPLETE',reason='Admitted; execution pending')
        self.store.put_record('evaluations',batch_id,batch)
        # Reserve concrete IDs before initializing telemetry and before any actor call.
        planned={(case_index,index,arm):new_id('episode') for case_index in range(len(cases)) for index in range(3) for arm in ('incumbent','candidate')}
        session=None
        if self.publisher:
            metadata={'campaign_id':campaign.campaign_id,'episode_id':batch_id,'origin':'faultlab_evaluation','split':batch.split,'source_mode':'live','experiment_purpose':purpose,'arm':'L','execution_epoch':campaign.execution_epoch,'trial_index':0,'study_id':campaign.campaign_id,'evidence_context_id':campaign.campaign_id,'agent_registration_id':'orders-v1','model_id':campaign.model,'policy_hash':candidate.policy_hash,'contract_hash':frozen['contract_hash'],'scorer_hash':frozen['scorer_hash']}
            session=await self.publisher.begin(batch_id,metadata,expected_episode_ids=list(planned.values()),frozen=False)
        try:
            for case_index,case in enumerate(cases):
                recipe=FaultSpec.model_validate_json(canonical_json(case['fault_spec']))
                for index in range(3):
                    if stop(): reason='External stop; incomplete pair'; interrupted=True; break
                    clean=None
                    for retry in range(2 if allow_lab_retry else 1):
                        retry_reservation=reservation
                        retry_name=None
                        if retry:
                            retry_name=f'pair-retry:{batch_id}:{case_index}:{index}'
                            self.ledger.reserve(retry_name,16)
                            retry_reservation=retry_name
                        outcomes={}
                        order=('incumbent','candidate') if (case_index+index)%2==0 else ('candidate','incumbent')
                        try:
                            for arm_name in order:
                                chosen=incumbent if arm_name=='incumbent' else candidate
                                trial=await self.runner.run(campaign,recipe,chosen,purpose=purpose,arm='B0' if arm_name=='incumbent' else 'L',trial_index=index,fixture_id=case.get('fixture_id','standard-v1'),ledger=self.ledger,reservation=retry_reservation,stop=stop,episode_id=planned[(case_index,index,arm_name)] if retry==0 else None)
                                trials.append(trial); outcomes[arm_name]=trial
                                if session and retry==0 and trial.lifecycle=='COMPLETED':
                                    e=self.store.get_record('episodes',trial.episode_id)
                                    if e.get('verdict'): await session.record_prediction(trial.episode_id,inputs={'scenario_hash':trial.scenario_hash},original_report=e['report'],persisted_scores={c['check_id']:c['passed'] for c in e['verdict']['checks']})
                                if trial.lifecycle=='INTERRUPTED': break
                        finally:
                            if retry_name: self.ledger.release(retry_name)
                        if len(outcomes)!=2 or any(t.lifecycle=='INTERRUPTED' for t in outcomes.values()): reason='External interruption'; interrupted=True; break
                        if any(t.lifecycle=='LAB_ERROR' for t in outcomes.values()):
                            reason='Infrastructure error pair retained'
                            continue
                        clean=(outcomes['incumbent'].episode_id,outcomes['candidate'].episode_id)
                        break
                    if clean: pairs.append(clean)
                    else: interrupted=True; break
                if interrupted: break
        except BudgetExhausted:
            reason='Complete required batch or clean retry could not fit'; interrupted=True
        finally:
            if own: self.ledger.release(reservation)
        batch.trial_pairs=pairs; batch.trials=trials; batch.usage=aggregate_usage(trials)
        complete=paired_complete(batch,len(cases)*3)
        batch.decision='NO_CHANGE' if complete else 'INCOMPLETE'
        batch.reason='Complete repeated evidence; fixed promotion predicate still required' if complete else reason
        self.store.put_record('evaluations',batch_id,batch)
        if session and complete:
            try: await session.finish({'decision':batch.decision,'valid_pairs':len(pairs),'attempted_episodes':len(trials),'reason':batch.reason})
            except Exception: pass
        return batch


async def queue_evaluation(coordinator,request):
    campaign=coordinator.get(request.campaign_id)
    if coordinator.active_id: raise StoreConflict('Another fresh execution is active')
    if len(request.policy_versions) not in (1,2): raise ValueError('One or two frozen policy versions required')
    policies=[coordinator.policies.get(v) for v in request.policy_versions]
    if any(p is None or p.decision not in ('ACCEPTED','BASELINE') for p in policies): raise ValueError('Only immutable accepted policies may be compared')
    coordinator.settings.require_live()
    coordinator.validate_core_configuration(campaign)
    if request.purpose=='final_audit':
        from app.lab.audit import queue_audit
        return await queue_audit(coordinator,campaign,policies[-1])
    import asyncio
    from app.lab.budgets import CampaignLedger
    await coordinator.admit_activity(campaign.campaign_id)
    campaign=coordinator.get(campaign.campaign_id)
    ledger=coordinator.ledgers.setdefault(campaign.campaign_id,CampaignLedger(coordinator.store,campaign.campaign_id,campaign.caps,dollar_bounds=coordinator.settings.model_call_dollar_bounds))
    request_id=new_id('evaluation-request')
    async def execute():
        runner=None; owned=False
        try:
            runner,owned=await coordinator._get_runner(True)
            batch=await PairedEvaluator(coordinator.store,runner,ledger,publisher=getattr(coordinator,'evaluation_publisher',None)).run(campaign,load_cases('promotion'),policies[0],policies[-1],stop=lambda:coordinator.get(campaign.campaign_id).stop_requested)
            coordinator.store.put_record('evaluation_requests',request_id,{'request_id':request_id,'batch_id':batch.batch_id,'status':'COMPLETED'})
        finally:
            if owned and runner:
                await runner.world_client.close(); await runner.provider.close()
                if getattr(runner,'telemetry_worker',None): await runner.telemetry_worker.close()
            coordinator.active_id=None
    coordinator.tasks[request_id]=asyncio.create_task(execute())
    return {'request_id':request_id,'status':'QUEUED'}

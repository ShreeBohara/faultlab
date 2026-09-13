"""Explicit frozen final audit; sealed cases never enter optimizer contexts."""
import asyncio
from app.contracts.models import FaultSpec,canonical_json,new_id
from app.lab.budgets import CampaignLedger
from app.lab.evaluation import aggregate_usage
from app.lab.storage import StoreConflict

async def queue_audit(coordinator,campaign,policy):
    coordinator.validate_core_configuration(campaign)
    if policy.decision!='ACCEPTED': raise StoreConflict('A learned audit arm requires an accepted policy; baseline is not a learned arm')
    frozen=coordinator.store.get_record('audit_freezes',campaign.campaign_id)
    if not frozen or frozen.get('policy_hash')!=policy.policy_hash or frozen.get('configuration_hash')!=campaign.configuration_hash:
        raise StoreConflict('Matching immutable audit freeze is required before final execution')
    from app.referee.manifests import load_manifest
    manifest=load_manifest('final-audit')
    if frozen.get('manifest_hash')!=manifest['manifest_hash']: raise StoreConflict('Frozen final manifest mismatch')
    ledger=coordinator.ledgers.setdefault(campaign.campaign_id,CampaignLedger(coordinator.store,campaign.campaign_id,campaign.caps,dollar_bound=coordinator.settings.model_call_dollar_bound))
    if 'final_audit' not in ledger.reservations: raise StoreConflict('Protected final audit capacity already consumed')
    batch_id=new_id('audit'); await coordinator.admit_activity(campaign.campaign_id)
    campaign=coordinator.get(campaign.campaign_id)
    record={'batch_id':batch_id,'campaign_id':campaign.campaign_id,'purpose':'final_audit','status':'QUEUED','policy_hash':policy.policy_hash,'manifest_hash':manifest['manifest_hash'],'trial_ids':[]}
    coordinator.store.put_record('audit_results',batch_id,record)
    async def execute():
        runner=None; owned=False; trials=[]; session=None
        try:
            runner,owned=await coordinator._get_runner(True)
            if getattr(runner,'trace',None): runner.trace.frozen=True
            planned={(case_index,index,arm):new_id('episode') for case_index in range(len(manifest['cases'])) for index in range(3) for arm in ('B0','B1','L')}
            publisher=getattr(coordinator,'evaluation_publisher',None)
            if publisher:
                from app.contracts.models import Provenance
                config=coordinator.store.get_record('configurations',campaign.configuration_hash)
                registration=coordinator.store.get_record('campaign_registrations',campaign.campaign_id)
                provenance=Provenance(campaign_id=campaign.campaign_id,episode_id=batch_id,origin='faultlab_evaluation',split='final_audit',arm='L',source_mode='live',experiment_purpose='final_audit',trial_index=0,study_id=campaign.campaign_id,evidence_context_id=campaign.campaign_id,execution_epoch=campaign.execution_epoch,agent_registration_id=registration['registration_id'])
                metadata={**provenance.model_dump(mode='json'),'model_id':campaign.model,'policy_hash':policy.policy_hash,'contract_hash':config['contract_hash'],'scorer_hash':config['scorer_hash']}
                session=await publisher.begin(batch_id,metadata,expected_episode_ids=list(planned.values()),frozen=True)
            record['status']='RUNNING'; coordinator.store.put_record('audit_results',batch_id,record)
            for case_index,case in enumerate(manifest['cases']):
                for index in range(3):
                    order=['B0','B1','L'] if (case_index+index)%2==0 else ['L','B1','B0']
                    for arm in order:
                        if coordinator.get(campaign.campaign_id).stop_requested: raise InterruptedError()
                        t=await runner.run(campaign,FaultSpec.model_validate_json(canonical_json(case['fault_spec'])),policy if arm=='L' else coordinator.policies.baseline(),episode_id=planned[(case_index,index,arm)],purpose='final_audit',arm=arm,trial_index=index,fixture_id=case['fixture_id'],ledger=ledger if arm!='B1' else None,reservation='final_audit' if arm!='B1' else None,stop=lambda:coordinator.get(campaign.campaign_id).stop_requested)
                        trials.append(t); record['trial_ids'].append(t.episode_id); coordinator.store.put_record('audit_results',batch_id,record)
                        if session:
                            e=coordinator.store.get_record('episodes',t.episode_id)
                            if e and e.get('verdict'):
                                await session.record_prediction(t.episode_id,inputs={'scenario_hash':t.scenario_hash,'arm':arm},original_report=e['report'],persisted_scores={check['check_id']:check['passed'] for check in e['verdict']['checks']})
            record['status']='COMPLETED' if len(trials)==72 and all(t.lifecycle=='COMPLETED' and (not t.fault_scheduled or t.fault_triggered) for t in trials) else 'INCOMPLETE'
            if session and record['status']=='COMPLETED':
                try: await session.finish({'status':record['status'],'attempted_episodes':len(trials),'policy_hash':policy.policy_hash,'manifest_hash':manifest['manifest_hash']})
                except Exception: record['telemetry_status']='weave_pending'
        except Exception: record['status']='INCOMPLETE'
        finally:
            record['usage']=aggregate_usage(trials).model_dump(mode='json'); coordinator.store.put_record('audit_results',batch_id,record)
            ledger.release('final_audit')
            if owned and runner:
                await runner.world_client.close(); await runner.provider.close()
                if getattr(runner,'telemetry_worker',None): await runner.telemetry_worker.close()
            coordinator.active_id=None
    coordinator.tasks[batch_id]=asyncio.create_task(execute())
    return record

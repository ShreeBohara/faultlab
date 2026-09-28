"""Explicit frozen independent-agent study with protected capacity and no tuning."""
import asyncio
from app.contracts.models import FaultSpec,Usage,canonical_json,new_id,utc_now
from app.lab.budgets import CampaignLedger,JobFinalizationError
from app.lab.storage import StoreConflict


def retain_portability_progress(store,record):
    """Bind a request to its frozen study and retain even an unreturned episode."""
    freeze_hash=record.get('freeze_hash')
    if not freeze_hash:
        frozen=store.get_record('external_freezes',record.get('campaign_id','')) or {}
        freeze_hash=frozen.get('freeze_hash')
    execution=store.get_record('portability_freezes',freeze_hash) if freeze_hash else None
    if execution: record['portability_id']=execution['portability_id']
    if freeze_hash: record['freeze_hash']=freeze_hash
    episodes=[episode for episode in store.list_campaign_episodes(record.get('campaign_id',''))
              if episode.get('experiment_purpose')=='portability'
              and freeze_hash is not None and episode.get('study_id')==freeze_hash]
    for key,field in (('episode_ids','episode_id'),('world_ids','world_id')):
        record[key]=list(dict.fromkeys(record.get(key,[])+[episode[field] for episode in episodes]))
    record['trial_ids']=list(dict.fromkeys(record.get('trial_ids',[])+[
        episode['episode_id'] for episode in episodes if store.get_record('trials',episode['episode_id'])]))
    if episodes:
        from types import SimpleNamespace
        from app.lab.evaluation import aggregate_usage
        record['usage']=aggregate_usage([SimpleNamespace(usage=Usage.model_validate(episode['usage']))
                                         for episode in episodes]).model_dump(mode='json')
    return record


def interrupt_portability(store,record,reason):
    retain_portability_progress(store,record)
    result=store.get_record('portability',record.get('portability_id') or '')
    if result and result['status'] in ('PENDING','RUNNING'):
        result['status']='INCOMPLETE'
        # Preserve prior limitations; a separate request reason always retains
        # this recovery explanation when the fixed model's list is already full.
        if reason not in result['limitations'] and len(result['limitations'])<16:
            result['limitations'].append(reason)
        store.put_record('portability',result['portability_id'],result)
    record.update(status=result['status'] if result else 'INCOMPLETE',reason=reason,
                  ended_at=utc_now().isoformat())
    return record


async def queue_portability(coordinator,campaign_id,request):
    from app.integrations.registry import AgentRegistry
    from app.integrations.portability import PortabilityStudy
    from app.lab.policies import require_ordinary_campaign
    require_ordinary_campaign(coordinator.store,campaign_id)
    campaign=coordinator.get(campaign_id); coordinator.settings.require_live()
    policy=coordinator.policies.get(request.policy_version or campaign.active_policy_version)
    if not policy or policy.decision!='ACCEPTED': raise ValueError('An accepted policy is required for unchanged external transfer')
    from app.lab.policies import imported_policy,IMPORTED_POLICY_REFUSAL
    if imported_policy(coordinator.store,policy): raise ValueError(IMPORTED_POLICY_REFUSAL)
    external_freeze=coordinator.store.get_record('external_freezes',campaign_id)
    if not external_freeze: raise StoreConflict('Independent external registration and manifest must be frozen first')
    registry=AgentRegistry(coordinator.store); registration=registry.get(request.agent_registration_id)
    target=coordinator.store.get_record('configurations',registration.configuration_hash)
    registry.verify(registration.registration_id,target)
    if registration.model!=coordinator.settings.wandb_model: raise ValueError('Target model differs from explicit configured runtime')
    source=coordinator.store.get_record('campaign_registrations',campaign_id)
    if not source: raise ValueError('Source registration unavailable')
    from app.integrations.portability import require_independent_target
    require_independent_target(registry.get(source['registration_id']),registration)
    fixed=PortabilityStudy(coordinator.store,registry)
    fixed._freeze(external_freeze,registration,target,coordinator.policies.baseline(),policy)
    if coordinator.store.get_record('portability_freezes',external_freeze['freeze_hash']): raise StoreConflict('Frozen external study already executed')
    ledger=coordinator.ledgers.setdefault(campaign_id,CampaignLedger(coordinator.store,campaign_id,campaign.caps,dollar_bounds=coordinator.settings.model_call_dollar_bounds))
    if 'portability' not in ledger.reservations: raise StoreConflict('Protected external study reservation unavailable')
    await coordinator.admit_activity(campaign_id)
    campaign=coordinator.get(campaign_id)
    request_id=new_id('portability-request')
    record={'request_id':request_id,'campaign_id':campaign_id,'status':'QUEUED','portability_id':None,
            'freeze_hash':external_freeze['freeze_hash'],'episode_ids':[],'trial_ids':[],
            'world_ids':[],'created_at':utc_now().isoformat()}
    try: coordinator.store.put_record('portability_requests',request_id,record)
    except BaseException:
        await coordinator.finish_activity(campaign_id,activity_id=request_id)
        raise
    async def execute():
        runner=None; owned=False; finalized=False; finalization_failed=False
        def finalize(result,metrics):
            nonlocal finalized
            with ledger.finalizing('portability'):
                coordinator.store.put_record('portability',result.portability_id,result)
                coordinator.store.put_record('portability_metrics',result.portability_id,metrics,immutable=True)
                coordinator.store.put_record('portability_campaigns',result.portability_id,{'campaign_id':campaign_id,'portability_id':result.portability_id},immutable=True)
                record.update(status=result.status,portability_id=result.portability_id,ended_at=utc_now().isoformat())
                retain_portability_progress(coordinator.store,record)
                coordinator.store.put_record('portability_requests',request_id,record)
            finalized=True
        try:
            record['status']='RUNNING'; coordinator.store.put_record('portability_requests',request_id,record)
            runner,owned=await coordinator._get_runner(True)
            if getattr(runner,'trace',None): runner.trace.frozen=True
            target_campaign=campaign.model_copy(deep=True); target_campaign.configuration_hash=registration.configuration_hash; target_campaign.model=registration.model
            actor=registry.reviewed_actor(registration.registration_id,runner.provider,registration.model)
            async def fresh(case,reviewed,transferred,index,arm):
                retain_portability_progress(coordinator.store,record)
                coordinator.store.put_record('portability_requests',request_id,record)
                try:
                    return await runner.run(target_campaign,FaultSpec.model_validate_json(canonical_json(case['fault_spec'])),transferred,purpose='portability',arm=arm,trial_index=index,fixture_id=case['fixture_id'],study_id=external_freeze['freeze_hash'],evidence_context_id=external_freeze['freeze_hash'],ledger=ledger,reservation='portability',stop=lambda:coordinator.get(campaign_id).stop_requested,agent_registration_id=reviewed.registration_id,actor=actor)
                finally:
                    retain_portability_progress(coordinator.store,record)
                    coordinator.store.put_record('portability_requests',request_id,record)
            result=await fixed.run(external_freeze=external_freeze,source_registration_id=source['registration_id'],target_registration_id=registration.registration_id,target_configuration=target,baseline_policy=coordinator.policies.baseline(),accepted_policy=policy,run_fresh=fresh,explicit_live=True,stop=lambda:coordinator.get(campaign_id).stop_requested,finalize=finalize)
            record.update(status=result.status,portability_id=result.portability_id)
        except JobFinalizationError:
            finalization_failed=True
            raise
        except asyncio.CancelledError:
            record['reason']='Study cancelled; saved effects are not replayed'
            raise
        except Exception as error:
            from app.lab.readiness import execution_failure
            record['error']=execution_failure(error)
            record['reason']='Study failed; saved effects are not replayed'
        finally:
            try:
                if not finalized and not finalization_failed:
                    with ledger.finalizing('portability'):
                        interrupt_portability(coordinator.store,record,record.get('reason','Study ended without completion; saved effects are not replayed'))
                        coordinator.store.put_record('portability_requests',request_id,record)
            finally: await coordinator.finish_activity(campaign_id,runner,owned=owned,activity_id=request_id)
    coordinator.tasks[request_id]=asyncio.create_task(execute())
    return record

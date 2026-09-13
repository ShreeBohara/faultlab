"""Explicit frozen independent-agent study with protected capacity and no tuning."""
import asyncio
from app.contracts.models import FaultSpec,canonical_json,new_id
from app.lab.budgets import CampaignLedger
from app.lab.storage import StoreConflict

async def queue_portability(coordinator,campaign_id,request):
    from app.integrations.registry import AgentRegistry
    from app.integrations.portability import PortabilityStudy
    campaign=coordinator.get(campaign_id); coordinator.settings.require_live()
    policy=coordinator.policies.get(request.policy_version or campaign.active_policy_version)
    if not policy or policy.decision!='ACCEPTED': raise ValueError('An accepted policy is required for unchanged external transfer')
    external_freeze=coordinator.store.get_record('external_freezes',campaign_id)
    if not external_freeze: raise StoreConflict('Independent external registration and manifest must be frozen first')
    registry=AgentRegistry(coordinator.store); registration=registry.get(request.agent_registration_id)
    target=coordinator.store.get_record('configurations',registration.configuration_hash)
    registry.verify(registration.registration_id,target)
    if registration.model!=coordinator.settings.wandb_model: raise ValueError('Target model differs from explicit configured runtime')
    source=coordinator.store.get_record('campaign_registrations',campaign_id)
    if not source: raise ValueError('Source registration unavailable')
    fixed=PortabilityStudy(coordinator.store,registry)
    fixed._freeze(external_freeze,registration,target,coordinator.policies.baseline(),policy)
    if coordinator.store.get_record('portability_freezes',external_freeze['freeze_hash']): raise StoreConflict('Frozen external study already executed')
    ledger=coordinator.ledgers.setdefault(campaign_id,CampaignLedger(coordinator.store,campaign_id,campaign.caps,dollar_bound=coordinator.settings.model_call_dollar_bound))
    if 'portability' not in ledger.reservations: raise StoreConflict('Protected external study reservation unavailable')
    await coordinator.admit_activity(campaign_id)
    campaign=coordinator.get(campaign_id)
    request_id=new_id('portability-request')
    record={'request_id':request_id,'campaign_id':campaign_id,'status':'QUEUED','portability_id':None}
    coordinator.store.put_record('portability_requests',request_id,record)
    async def execute():
        runner=None; owned=False
        try:
            runner,owned=await coordinator._get_runner(True)
            if getattr(runner,'trace',None): runner.trace.frozen=True
            target_campaign=campaign.model_copy(deep=True); target_campaign.configuration_hash=registration.configuration_hash; target_campaign.model=registration.model
            actor=registry.reviewed_actor(registration.registration_id,runner.provider,registration.model)
            async def fresh(case,reviewed,transferred,index,arm):
                return await runner.run(target_campaign,FaultSpec.model_validate_json(canonical_json(case['fault_spec'])),transferred,purpose='portability',arm=arm,trial_index=index,fixture_id=case['fixture_id'],study_id=external_freeze['freeze_hash'],evidence_context_id=external_freeze['freeze_hash'],ledger=ledger,reservation='portability',stop=lambda:coordinator.get(campaign_id).stop_requested,agent_registration_id=reviewed.registration_id,actor=actor)
            result=await fixed.run(external_freeze=external_freeze,source_registration_id=source['registration_id'],target_registration_id=registration.registration_id,target_configuration=target,baseline_policy=coordinator.policies.baseline(),accepted_policy=policy,run_fresh=fresh,explicit_live=True,stop=lambda:coordinator.get(campaign_id).stop_requested)
            record.update(status=result.status,portability_id=result.portability_id)
            coordinator.store.put_record('portability_campaigns',result.portability_id,{'campaign_id':campaign_id,'portability_id':result.portability_id},immutable=True)
        except Exception: record['status']='INCOMPLETE'
        finally:
            coordinator.store.put_record('portability_requests',request_id,record)
            ledger.release('portability')
            if owned and runner:
                await runner.world_client.close(); await runner.provider.close()
                if getattr(runner,'telemetry_worker',None): await runner.telemetry_worker.close()
            coordinator.active_id=None
    coordinator.tasks[request_id]=asyncio.create_task(execute())
    return record

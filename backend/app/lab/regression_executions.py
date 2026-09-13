"""Trusted registration execution through the single-active bounded scheduler."""
import asyncio
from app.contracts.models import RegressionExecution,RegressionBundle,Usage,EpisodeBudget,content_hash,new_id
from app.lab.budgets import CampaignLedger
from app.lab.storage import StoreConflict
from app.lab.regressions import RegressionCompiler

async def execute_regression(coordinator,regression_id,request):
    from app.integrations.registry import AgentRegistry
    from app.integrations.regression_runner import RegressionRunner
    regression=coordinator.store.get_record('regressions',regression_id)
    if not regression: raise KeyError(regression_id)
    policy=coordinator.policies.get(request.policy_version)
    if policy is None or policy.decision not in ('BASELINE','ACCEPTED'): raise ValueError('Immutable accepted policy required')
    if request.execute_live is not True or request.execution_profile_id!='sandbox-v1': raise ValueError('Explicit reviewed execution profile required')
    coordinator.settings.require_live()
    campaign=coordinator.get(regression['campaign_id'])
    registry=AgentRegistry(coordinator.store); registration=registry.get(request.agent_registration_id)
    target=coordinator.store.get_record('configurations',registration.configuration_hash)
    if registration.model!=coordinator.settings.wandb_model: raise ValueError('Registered model differs from explicitly configured runtime model')
    directory=coordinator.settings.artifact_path/'bundles'/regression['bundle_id']
    RegressionCompiler(coordinator.store).export(regression['bundle_id'],directory)
    fixed=RegressionRunner(coordinator.store,registry)
    checked=fixed.validate(directory,target,registration.registration_id)
    if checked.bundle.policy_hash!=policy.policy_hash: raise ValueError('Selected policy must equal the transferred immutable artifact')
    ledger=coordinator.ledgers.setdefault(campaign.campaign_id,CampaignLedger(coordinator.store,campaign.campaign_id,campaign.caps,dollar_bound=coordinator.settings.model_call_dollar_bound))
    execution_id=new_id('execution'); reservation=f'regression:{execution_id}'
    await coordinator.admit_activity(campaign.campaign_id)
    campaign=coordinator.get(campaign.campaign_id)
    try: ledger.reserve(reservation,24)
    except BaseException:
        coordinator.active_id=None; raise
    record=RegressionExecution(execution_id=execution_id,bundle_id=checked.bundle.bundle_id,manifest_hash=checked.bundle.manifest_hash,registration_id=registration.registration_id,profile_id='sandbox-v1',mode='FRESH_SANDBOX',explicit_action=True,policy_hash=policy.policy_hash,configuration_hash=registration.configuration_hash,declared_budget=EpisodeBudget(),usage=Usage(),episode_ids=[],world_ids=[],status='PENDING')
    coordinator.store.put_record('regression_executions',execution_id,record)
    async def execute():
        runner=None; owned=False
        try:
            runner,owned=await coordinator._get_runner(True)
            target_campaign=campaign.model_copy(deep=True); target_campaign.model=registration.model; target_campaign.configuration_hash=registration.configuration_hash
            actor=registry.reviewed_actor(registration.registration_id,runner.provider,registration.model)
            async def fresh(recipe,reviewed,transferred,index,*,fixture_id):
                fixture=fixture_id
                if fixture!=checked.bundle.fixture_id: raise ValueError('Frozen initial-state fixture changed')
                return await runner.run(target_campaign,recipe,transferred,purpose='reproduction',arm='B0' if transferred.decision=='BASELINE' else 'L',trial_index=index,study_id=execution_id,evidence_context_id=execution_id,fixture_id=fixture,ledger=ledger,reservation=reservation,stop=lambda:coordinator.get(campaign.campaign_id).stop_requested,agent_registration_id=reviewed.registration_id,actor=actor)
            await fixed.execute(directory,target,registration.registration_id,explicit_live=True,profile_id='sandbox-v1',run_fresh=fresh,policy_version=policy,execution_id=execution_id)
        except Exception:
            failed=coordinator.store.get_model('regression_executions',execution_id,RegressionExecution)
            failed.status='INCOMPLETE'; failed.stop_reason='Execution failed; saved effects are not replayed'; coordinator.store.put_record('regression_executions',execution_id,failed)
        finally:
            ledger.release(reservation)
            if owned and runner:
                await runner.world_client.close(); await runner.provider.close()
                if getattr(runner,'telemetry_worker',None): await runner.telemetry_worker.close()
            coordinator.active_id=None
    coordinator.tasks[execution_id]=asyncio.create_task(execute())
    return record

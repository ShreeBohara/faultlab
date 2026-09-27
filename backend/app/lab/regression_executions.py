"""Trusted registration execution through the single-active bounded scheduler."""
import asyncio
from app.contracts.models import RegressionExecution,RegressionBundle,Usage,EpisodeBudget,content_hash,new_id
from app.lab.budgets import CampaignLedger,StopRequested
from app.lab.storage import StoreConflict
from app.lab.regressions import RegressionCompiler,runnable_policy


def interrupt_regression(store,execution_id,reason):
    """Retain worlds already created even if execution stopped before returning a trial."""
    record=store.get_model('regression_executions',execution_id,RegressionExecution)
    if record is None or record.mode!='FRESH_SANDBOX': return record
    episodes=[e for e in store.list_records('episodes') if e.get('study_id')==execution_id]
    for episode in episodes:
        if episode['episode_id'] not in record.episode_ids: record.episode_ids.append(episode['episode_id'])
        if episode['world_id'] not in record.world_ids: record.world_ids.append(episode['world_id'])
    if episodes:
        from app.lab.evaluation import aggregate_usage
        from types import SimpleNamespace
        record.usage=aggregate_usage([SimpleNamespace(usage=Usage.model_validate_json(__import__('json').dumps(e['usage']))) for e in episodes])
    record.status='INCOMPLETE'; record.stop_reason=reason
    store.put_record('regression_executions',execution_id,record)
    return record


async def execute_regression(coordinator,regression_id,request):
    from app.integrations.registry import AgentRegistry
    from app.integrations.regression_runner import RegressionRunner
    regression=coordinator.store.get_record('regressions',regression_id)
    if not regression: raise KeyError(regression_id)
    policy=coordinator.policies.get(request.policy_version)
    if policy is None: raise ValueError('Immutable bundled policy required')
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
    runnable_policy(checked.bundle,policy)
    if checked.bundle.policy_hash!=policy.policy_hash: raise ValueError('Selected policy must equal the transferred immutable artifact')
    ledger=coordinator.ledgers.setdefault(campaign.campaign_id,CampaignLedger(coordinator.store,campaign.campaign_id,campaign.caps,dollar_bounds=coordinator.settings.model_call_dollar_bounds))
    execution_id=new_id('execution'); reservation=f'regression:{execution_id}'
    await coordinator.admit_activity(campaign.campaign_id)
    campaign=coordinator.get(campaign.campaign_id)
    try:
        ledger.reserve(reservation,24)
        record=RegressionExecution(execution_id=execution_id,bundle_id=checked.bundle.bundle_id,manifest_hash=checked.bundle.manifest_hash,registration_id=registration.registration_id,profile_id='sandbox-v1',mode='FRESH_SANDBOX',explicit_action=True,policy_hash=policy.policy_hash,configuration_hash=registration.configuration_hash,declared_budget=EpisodeBudget(),usage=Usage(),episode_ids=[],world_ids=[],status='PENDING')
        coordinator.store.put_record('regression_executions',execution_id,record)
    except BaseException:
        try: ledger.release(reservation)
        finally: await coordinator.finish_activity(campaign.campaign_id,activity_id=execution_id)
        raise
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
        except (asyncio.CancelledError,StopRequested):
            interrupt_regression(coordinator.store,execution_id,'Execution interrupted; saved effects are not replayed')
            raise
        except Exception as error:
            from app.lab.readiness import execution_failure
            interrupt_regression(coordinator.store,execution_id,'Execution failed; saved effects are not replayed')
            coordinator.store.put_record('regression_execution_errors',execution_id,{'execution_id':execution_id,**execution_failure(error)})
        finally:
            try:
                saved=coordinator.store.get_record('regression_executions',execution_id)
                if saved and saved['status'] in ('PENDING','RUNNING'):
                    interrupt_regression(coordinator.store,execution_id,'Execution ended without completion; saved effects are not replayed')
            finally:
                try: ledger.release(reservation)
                finally: await coordinator.finish_activity(campaign.campaign_id,runner,owned=owned,activity_id=execution_id)
    coordinator.tasks[execution_id]=asyncio.create_task(execute())
    return record

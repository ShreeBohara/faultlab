"""Trusted registration execution through the single-active bounded scheduler."""
import asyncio
from app.contracts.models import RegressionExecution,RegressionBundle,Usage,EpisodeBudget,content_hash,new_id
from app.lab.budgets import CampaignLedger,StopRequested,JobFinalizationError
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
        observed=aggregate_usage([SimpleNamespace(usage=Usage.model_validate_json(__import__('json').dumps(e['usage']))) for e in episodes])
        # A mismatched callback may have already recorded larger/unknown usage.
        # Recovery must not turn that retained uncertainty into a smaller bill.
        values={key:max(getattr(record.usage,key),getattr(observed,key)) for key in Usage.model_fields if key!='cost_dollars'}
        values['cost_dollars']=(max(record.usage.cost_dollars,observed.cost_dollars)
            if record.usage.cost_dollars is not None and observed.cost_dollars is not None else None)
        record.usage=Usage(**values)
    _include_owner_charges(store,record)
    record.status='INCOMPLETE'; record.stop_reason=reason
    store.put_record('regression_executions',execution_id,record)
    return record


def _include_owner_charges(store,record):
    """An imported execution's accounting owner holds only this job, so its ledger is
    the complete charge record. Episode usage is saved only when a trial ends; after a
    process loss mid-trial, rebuilt usage alone would understate calls already paid."""
    owner=next((row for row in store.list_records('import_execution_owners')
                if row.get('execution_id')==record.execution_id),None)
    budget=store.get_record('budgets',owner['owner_campaign_id']) if owner else None
    if not budget or not budget.get('used_calls'): return
    values=record.usage.model_dump()
    values['model_calls']=max(values['model_calls'],budget['used_calls'])
    values['input_tokens']=max(values['input_tokens'],budget.get('measured_input_tokens',0))
    values['output_tokens']=max(values['output_tokens'],budget.get('measured_output_tokens',0))
    charged=budget.get('actual_cost_dollars')
    # Known cost stays known only while every charged call has a known cost.
    values['cost_dollars']=(max(values['cost_dollars'],charged)
        if values['cost_dollars'] is not None and charged is not None else None)
    record.usage=Usage(**values)


async def execute_regression(coordinator,regression_id,request):
    from app.integrations.registry import AgentRegistry
    from app.integrations.regression_runner import RegressionRunner
    from app.lab.policies import require_ordinary_campaign
    regression=coordinator.store.get_record('regressions',regression_id)
    if not regression: raise KeyError(regression_id)
    # Every refusal below precedes the export, validation record and admission:
    # a refused request leaves the store and the artifact directory unchanged.
    require_ordinary_campaign(coordinator.store,regression['campaign_id'])
    policy=coordinator.policies.get(request.policy_version)
    if policy is None: raise ValueError('Immutable bundled policy required')
    # An imported policy runs only for the bundle it arrived in; an ordinary regression
    # must record its own bundled policy version, never a foreign same-content alias.
    # Aliases made by the reviewed dashboard import run only through that import.
    provenance=coordinator.store.get_record('policy_imports',policy.version)
    if provenance is not None and (provenance.get('import_id')!=regression.get('bundle_id')
                                   or provenance.get('path')!='cli_import_and_execute'):
        raise ValueError('Imported policies run only through their reviewed import execution')
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
    return schedule_regression(coordinator,campaign=campaign,checked=checked,registration=registration,
        target=target,policy=policy,ledger=ledger,execution_id=execution_id,reservation=reservation,
        directory=directory,record=record)


def schedule_regression(coordinator,*,campaign,checked,registration,target,policy,ledger,
                        execution_id,reservation,directory,record):
    """Start only an already durable admission; shared by CLI and reviewed imports."""
    from app.integrations.registry import AgentRegistry
    from app.integrations.regression_runner import RegressionRunner
    registry=AgentRegistry(coordinator.store)
    fixed=RegressionRunner(coordinator.store,registry)
    async def execute():
        runner=None; owned=False; finalized=False; finalization_failed=False; reason=None; error_record=None
        def finalize(result,assertions):
            nonlocal finalized
            with ledger.finalizing(reservation):
                coordinator.store.put_record('regression_executions',execution_id,result)
                if result.status=='INCOMPLETE':
                    interrupt_regression(coordinator.store,execution_id,result.stop_reason)
                coordinator.store.put_record('regression_assertions',execution_id,assertions,immutable=True)
            finalized=True
        try:
            runner,owned=await coordinator._get_runner(True)
            target_campaign=campaign.model_copy(deep=True); target_campaign.model=registration.model; target_campaign.configuration_hash=registration.configuration_hash
            actor=registry.reviewed_actor(registration.registration_id,runner.provider,registration.model)
            async def fresh(recipe,reviewed,transferred,index,*,fixture_id):
                fixture=fixture_id
                if fixture!=checked.bundle.fixture_id: raise ValueError('Frozen initial-state fixture changed')
                return await runner.run(target_campaign,recipe,transferred,purpose='reproduction',arm='B0' if transferred.decision=='BASELINE' else 'L',trial_index=index,study_id=execution_id,evidence_context_id=execution_id,fixture_id=fixture,ledger=ledger,reservation=reservation,stop=lambda:coordinator.get(campaign.campaign_id).stop_requested,agent_registration_id=reviewed.registration_id,actor=actor)
            await fixed.execute(directory,target,registration.registration_id,explicit_live=True,profile_id='sandbox-v1',run_fresh=fresh,policy_version=policy,execution_id=execution_id,finalize=finalize)
        except JobFinalizationError:
            finalization_failed=True
            raise
        except (asyncio.CancelledError,StopRequested):
            reason='Execution interrupted; saved effects are not replayed'
            raise
        except Exception as error:
            from app.lab.readiness import execution_failure
            reason='Execution failed; saved effects are not replayed'
            error_record={'execution_id':execution_id,**execution_failure(error)}
        finally:
            try:
                if not finalized and not finalization_failed:
                    with ledger.finalizing(reservation):
                        interrupt_regression(coordinator.store,execution_id,reason or 'Execution ended without completion; saved effects are not replayed')
                        if error_record: coordinator.store.put_record('regression_execution_errors',execution_id,error_record)
            finally: await coordinator.finish_activity(campaign.campaign_id,runner,owned=owned,activity_id=execution_id)
    coordinator.tasks[execution_id]=asyncio.create_task(execute())
    return record

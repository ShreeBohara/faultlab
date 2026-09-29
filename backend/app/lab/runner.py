"""Sequential fresh-world execution joins only fixed private scoring inputs."""
import asyncio
from app.contracts.models import Episode, Provenance, TrialResult, Usage, content_hash, new_id, utc_now
from app.adapters.journal import Journal,allocate_intent
from app.adapters.business_tools import BusinessToolBroker
from app.adapters.prototype import EpisodeContext,run_prototype
from app.agents.reference import ReferenceActor
from app.agents.actor import ActorReportError
from app.providers.runtime import RuntimeProviderError
from app.lab.budgets import EpisodeMeter,StopRequested,BudgetExhausted
from app.lab.configuration import resolve_actor_context_protocol
from app.lab.policy_interpreter import PolicyInterpreter
from app.telemetry.tracing import episode_deadline

B1_CONTROL_ID='deterministic-reference-control-v1'
B1_CONTROL_MODEL='deterministic-reference/internal-smoke'


def campaign_run_plan(store,campaign):
    # Legacy programmatic execution may not persist a Campaign record at all.
    # Only a completely unmarked store takes that compatibility path.
    provenance=store.get_record('campaign_provenance',campaign.campaign_id) or {}
    if (not any(key in provenance for key in ('run_plan_protocol','run_plan_ref','run_plan_hash'))
            and store.get_record('campaign_plans',campaign.campaign_id) is None):
        return None
    from app.lab.run_plans import read_run_plan
    return read_run_plan(store,campaign.campaign_id)['plan']


def planned_registration_id(store,campaign):
    """New plans bind phase metadata; historical phase attribution stays intact."""
    plan=campaign_run_plan(store,campaign)
    return plan['agent_registration_id'] if plan else 'orders-v1'


def reject_native_reference_study(store,campaign):
    from app.integrations.registry import NATIVE_AGENTS
    plan=campaign_run_plan(store,campaign)
    if plan and plan['agent'] in NATIVE_AGENTS:
        raise ValueError('This research study tests reference Actor protocols; native planned campaigns support ordinary baseline, learn and compare runs')


def _target_execution(store,campaign,registration_id,study_id,purpose):
    """Only an admitted fresh transfer may replace a planned campaign actor."""
    if purpose=='reproduction' and study_id:
        execution=store.get_record('regression_executions',study_id) or {}
        if (execution.get('status')=='RUNNING' and execution.get('mode')=='FRESH_SANDBOX'
                and execution.get('registration_id')==registration_id
                and execution.get('configuration_hash')==campaign.configuration_hash):
            return any(row.get('campaign_id')==campaign.campaign_id
                       and row.get('bundle_id')==execution.get('bundle_id')
                       for row in store.list_records('regressions'))
    if purpose=='portability' and study_id:
        frozen=store.get_record('external_freezes',campaign.campaign_id) or {}
        execution=store.get_record('portability_freezes',study_id) or {}
        result=store.get_record('portability',execution.get('portability_id','')) or {}
        return (frozen.get('freeze_hash')==study_id and result.get('status') in ('PENDING','RUNNING')
                and result.get('target_registration_id')==registration_id
                and result.get('target_configuration_hash')==campaign.configuration_hash)
    return False


def _study_context(store,campaign,study_id,purpose,arm,protocol):
    kind={'context_study':'context_studies','completion_study':'completion_studies'}.get(purpose)
    record=store.get_record(kind,study_id) if kind and study_id else None
    if (not record or record.get('status')!='RUNNING'
            or record.get('campaign_id')!=campaign.campaign_id
            or record.get('configuration_hash')!=campaign.configuration_hash): return False
    expected=(record.get('protocol_by_arm',{}).get(arm) if purpose=='context_study'
              else record.get('actor_context_protocol'))
    return protocol==expected


def resolve_execution(store,campaign,frozen,*,arm,purpose,study_id,source_mode,registration_id,actor,actor_context_protocol,offline_fixture=False):
    """Resolve all selected-agent phases before creating a world or spending."""
    from app.integrations.registry import AgentRegistry,NATIVE_ENTRYPOINTS,reviewed_actor_matches
    from app.lab.storage import StoreConflict
    plan=campaign_run_plan(store,campaign)
    if plan is None:
        bound=store.get_record('campaign_registrations',campaign.campaign_id)
        if registration_id=='orders-v1' and bound: registration_id=bound['registration_id']
        return (actor or (ReferenceActor() if arm=='B1' else run_prototype),registration_id,
                source_mode,campaign.model,resolve_actor_context_protocol(frozen,actor_context_protocol),None)
    if offline_fixture and source_mode!='offline_fixture':
        raise StoreConflict('Declared offline fixture execution must retain its offline source label')
    target=_target_execution(store,campaign,registration_id,study_id,purpose)
    if (any(getattr(campaign,key)!=plan[key] for key in ('mode','config_profile_id','task_text','order_id'))
            or campaign.caps.model_dump(mode='json')!=plan['caps']):
        raise StoreConflict('Planned task or limits differ from the selected execution')
    if not target and (campaign.configuration_hash!=plan['configuration_hash'] or campaign.model!=frozen.get('model')):
        raise StoreConflict('Planned campaign configuration differs from the selected execution')
    if arm=='B1':
        if target or (actor is not None and type(actor) is not ReferenceActor):
            raise StoreConflict('B1 is the explicit deterministic reference control')
        AgentRegistry(store).verify(plan['agent_registration_id'],frozen)
        from app.lab.configuration import file_hash,ROOT
        descriptor={'kind':'deterministic_reference_control','registration_id':B1_CONTROL_ID,
                    'selected_agent_registration_id':plan['agent_registration_id'],
                    'implementation_hash':file_hash(ROOT/'backend/app/agents/reference.py'),
                    'offline_fixture':True}
        return ReferenceActor(),B1_CONTROL_ID,'offline_fixture',B1_CONTROL_MODEL,None,descriptor
    if ((not target and campaign.config_profile_id!='live-v1')
            or (source_mode!='live' and not offline_fixture)):
        raise StoreConflict('Planned registered-agent execution requires its live profile and source label')
    selected_id=registration_id if target else plan['agent_registration_id']
    if not target and registration_id not in ('orders-v1',selected_id):
        raise StoreConflict('Actor registration override differs from the selected campaign agent')
    registry=AgentRegistry(store)
    registration=registry.verify(selected_id,frozen)
    if actor is not None and not reviewed_actor_matches(actor,registration):
        raise StoreConflict('Actor override differs from the reviewed selected implementation')
    native=registration.adapter_entrypoint_id in NATIVE_ENTRYPOINTS
    if native and actor_context_protocol is not None:
        raise StoreConflict('Native agent does not execute reference Actor context protocols')
    selected_context=None if native else resolve_actor_context_protocol(frozen,actor_context_protocol)
    if (not target and not native and selected_context!=resolve_actor_context_protocol(frozen)
            and not _study_context(store,campaign,study_id,purpose,arm,selected_context)):
        raise StoreConflict('Actor context override differs from the selected campaign configuration')
    chosen=registry.reviewed_actor(selected_id,model_id=campaign.model)
    descriptor={'kind':'reviewed_registered_agent','registration_id':selected_id,
                'configuration_hash':registration.configuration_hash,
                'adapter_entrypoint_id':registration.adapter_entrypoint_id,
                'source_hash':registration.source_hash,'prompt_hash':registration.prompt_hash,
                'target_override':target,'actor_context_protocol':selected_context,
                'offline_fixture':offline_fixture}
    return chosen,selected_id,source_mode,registration.model,selected_context,descriptor


def world_integrity(decision,horizon,usage,logical_calls):
    """Validate the lab's predicted clock against the frozen actual execution.

    A transport attempt can fail before the simulator admits it. Its resource
    charge and delivered observation must remain intact, but their predicted
    timestamps cannot establish an agent violation when the world disagrees.
    This check is infrastructure validation; C1-C8 remain unchanged.
    """
    dispatched=[attempt for call in logical_calls for attempt in call['attempt_ids']]
    admitted=[event.payload.get('attempt_id') for event in decision.events if event.type=='http_attempt']
    issues=[]
    if decision.tick!=usage.ticks: issues.append('DECISION_TICK_MISMATCH')
    if len(admitted)!=usage.http_attempts: issues.append('HTTP_ADMISSION_COUNT_MISMATCH')
    if admitted!=dispatched: issues.append('HTTP_ADMISSION_IDENTITY_MISMATCH')
    if horizon.tick!=decision.tick+5: issues.append('OBSERVER_HORIZON_MISMATCH')
    return {'schema_version':'faultlab-world-integrity/v1','status':'INVALID' if issues else 'VALID',
            'issues':issues,'lab_ticks':usage.ticks,'decision_tick':decision.tick,'horizon_tick':horizon.tick,
            'charged_http_attempts':usage.http_attempts,'admitted_http_attempts':len(admitted),
            'dispatched_attempt_ids':dispatched,'admitted_attempt_ids':admitted}


class EpisodeRunner:
    def __init__(self,store,world_client,provider=None,*,trace=None,scorer=None,actor=None,offline_fixture=False):
        self.store,self.world_client,self.provider=store,world_client,provider
        self.trace,self.scorer,self.actor=trace,scorer,actor
        # Internal offline harnesses opt in explicitly. API/coordinator-created
        # production runners never enable this and cannot relabel it as live.
        self.offline_fixture=offline_fixture

    async def run(self,campaign,recipe,policy,*,purpose='discovery',arm='B0',trial_index=0,study_id=None,evidence_context_id=None,selector_id=None,fixture_id='standard-v1',ledger=None,reservation=None,stop=None,source_mode='live',agent_registration_id='orders-v1',actor=None,episode_id=None,actor_context_protocol=None):
        frozen=self.store.get_record('configurations',campaign.configuration_hash) or {}
        chosen,agent_registration_id,source_mode,episode_model,selected_context,execution=resolve_execution(
            self.store,campaign,frozen,arm=arm,purpose=purpose,study_id=study_id,source_mode=source_mode,
            registration_id=agent_registration_id,actor=actor or self.actor,actor_context_protocol=actor_context_protocol,
            offline_fixture=self.offline_fixture)
        episode_id=episode_id or new_id('episode')
        intent=allocate_intent(campaign.order_id,campaign.task_text,4 if fixture_id=='history-v1' else 1)
        world=await self.world_client.create(episode_id,intent,recipe,fixture_id)
        provenance=Provenance(campaign_id=campaign.campaign_id,episode_id=episode_id,origin='prototype' if purpose=='discovery' else 'faultlab_evaluation',split='promotion' if purpose=='promotion' else 'final_audit' if purpose in ('final_audit','portability') else 'development',arm=arm,source_mode=source_mode,experiment_purpose=purpose,trial_index=trial_index,study_id=study_id or campaign.campaign_id,evidence_context_id=evidence_context_id or campaign.campaign_id,selector_id=selector_id,execution_epoch=campaign.execution_epoch,agent_registration_id=agent_registration_id)
        episode=Episode(**provenance.model_dump(),world_id=world['world_id'],task_id=intent.task_id,scenario_hash=content_hash(recipe),policy_hash=policy.policy_hash,policy_version=policy.version,model=episode_model,configuration_hash=campaign.configuration_hash,lifecycle='RUNNING',started_at=utc_now())
        self.store.put_record('episodes',episode_id,episode)
        if execution: self.store.put_record('episode_executions',episode_id,execution,immutable=True)
        self.store.put_record('private_episode_inputs',episode_id,{'intent':intent.model_dump(mode='json'),'recipe':recipe.model_dump(mode='json'),'fixture_id':fixture_id},immutable=True)
        # A retried world creation is recorded on the episode rather than on Episode or
        # TrialResult: those are StrictModel (extra='forbid'), so a new field would move
        # contract_hash. If an earlier attempt did reach the handler, a world exists that
        # this lab never learned the id of and never references.
        started={'arm':arm,'source_mode':source_mode}
        if world.get('create_failures'): started['create_failures']=world['create_failures']
        self.store.append_event(episode_id,type='episode_started',payload=started)
        meter=EpisodeMeter(campaign=ledger,reservation=reservation,stop=stop)
        journal=Journal(self.store,episode_id,intent)
        broker=BusinessToolBroker(self.world_client,world['world_id'],world['capability'],journal,meter)
        interpreter=PolicyInterpreter(policy.content,broker)
        actor_model=episode_model if execution else (frozen.get('models') or {}).get('actor',campaign.model)
        metadata={**provenance.model_dump(mode='json'),'model_id':actor_model,'policy_hash':policy.policy_hash,'contract_hash':frozen.get('contract_hash'),'scorer_hash':frozen.get('scorer_hash')}
        broker.trace=self.trace; broker.metadata=metadata
        context=EpisodeContext(provenance,broker,interpreter,self.provider,policy.content,policy.policy_hash,policy.decision,metadata,self.trace,
                               actor_context_protocol=selected_context)
        report=None; lab_error=False; interrupted=False
        try:
            # Trace finalization sees the same explicit deadline disposition as
            # the runner. External cancellation remains an interrupted trial.
            async with asyncio.timeout(meter.caps.wall_seconds) as deadline:
                with episode_deadline(deadline):
                    returned=await chosen(intent,context)
                    if context.returned_report is None: context.complete_report(returned)
                    report=returned
            if meter.stop(): raise StopRequested('External stop requested')
        except asyncio.CancelledError:
            report=context.returned_report
            interrupted=True; episode.reason='TASK_CANCELLED'
        except TimeoutError:
            episode.reason='Episode deadline exhausted; no additional model call'
        except StopRequested:
            report=context.returned_report
            interrupted=True; episode.reason='STOP_REQUESTED'
        except ActorReportError as error:
            episode.reason=str(error)
        except BudgetExhausted:
            episode.reason=('Episode deadline exhausted; no timely final actor report'
                            if meter.clock()-meter.started>=meter.caps.wall_seconds
                            else 'No final actor report before the frozen episode limit')
        except RuntimeProviderError as error:
            lab_error=True; episode.reason=error.code
        except Exception:
            lab_error=True; episode.reason='PROVIDER_OR_INFRASTRUCTURE_ERROR'
        try:
            meter.usage.wall_seconds=(context.report_completed_wall_seconds
                if context.report_completed_wall_seconds is not None else meter.clock()-meter.started)
            # Freeze admission before taking the decision snapshot. A read before
            # stop can miss a request admitted between these two control calls.
            await self.world_client.stop(world['world_id'])
            decision=await self.world_client.snapshot(world['world_id'])
            await self.world_client.advance(world['world_id'],5,observer=True)
            horizon=await self.world_client.snapshot(world['world_id'])
            faults=await self.world_client.faults(world['world_id'])
            self.store.put_record('private_snapshots',episode_id,{'decision':decision.model_dump(mode='json'),'horizon':horizon.model_dump(mode='json')},immutable=True)
            integrity=world_integrity(decision,horizon,meter.usage,broker.logical_calls)
            self.store.put_record('private_world_integrity',episode_id,integrity,immutable=True)
            if integrity['status']=='INVALID':
                if not lab_error and not interrupted: episode.reason='WORLD_EXECUTION_MISMATCH'
                lab_error=True
                self.store.append_event(episode_id,tick=decision.tick,role='referee',type='world_execution_mismatch',
                                        payload={'issues':integrity['issues'],'lab_ticks':meter.usage.ticks,
                                                 'decision_tick':decision.tick,'charged_http_attempts':meter.usage.http_attempts,
                                                 'admitted_http_attempts':integrity['admitted_http_attempts']},
                                        visibility='PRIVATE_EVALUATOR')
            scorer=self.scorer
            if scorer is None:
                from app.referee.checks import score
                scorer=score
            verdict=scorer(intent,report,journal.observations,decision,horizon,episode_id=episode_id,usage=meter.usage,fault_executions=faults,lab_error=lab_error,stopped=interrupted)
            episode.verdict=verdict
            self.store.put_record('verdicts',verdict.verdict_id,verdict,immutable=True)
        except Exception:
            lab_error=True; episode.reason='SIMULATOR_OR_SCORER_ERROR'
        meter.usage.wall_seconds=(context.report_completed_wall_seconds
            if context.report_completed_wall_seconds is not None else meter.clock()-meter.started)
        episode.report=report; episode.usage=meter.usage; episode.ended_at=utc_now()
        episode.lifecycle='INTERRUPTED' if interrupted else 'LAB_ERROR' if lab_error else 'COMPLETED'
        self.store.put_record('episodes',episode_id,episode)
        self.store.append_event(episode_id,tick=min(20,meter.usage.ticks),type='episode_interrupted' if interrupted else 'verdict_recorded',role='referee',payload={'lifecycle':episode.lifecycle,'verdict':episode.verdict.model_dump(mode='json') if episode.verdict else None})
        trial=TrialResult(episode_id=episode_id,world_id=world['world_id'],scenario_hash=episode.scenario_hash,policy_hash=policy.policy_hash,arm=arm,trial_index=trial_index,lifecycle=episode.lifecycle,outcome=episode.verdict.outcome if episode.verdict else 'LAB_ERROR',failed_checks=[c.check_id for c in episode.verdict.checks if not c.passed] if episode.verdict else [],fault_scheduled=bool(recipe.primitives),fault_triggered=bool(episode.verdict and all(f.triggered for f in episode.verdict.fault_executions)) if recipe.primitives else False,usage=meter.usage,reason=episode.reason)
        self.store.put_record('trials',episode_id,trial,immutable=True)
        return trial

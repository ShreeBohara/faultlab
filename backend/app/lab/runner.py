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
from app.lab.policy_interpreter import PolicyInterpreter

class EpisodeRunner:
    def __init__(self,store,world_client,provider=None,*,trace=None,scorer=None,actor=None):
        self.store,self.world_client,self.provider=store,world_client,provider
        self.trace,self.scorer,self.actor=trace,scorer,actor

    async def run(self,campaign,recipe,policy,*,purpose='discovery',arm='B0',trial_index=0,study_id=None,evidence_context_id=None,selector_id=None,fixture_id='standard-v1',ledger=None,reservation=None,stop=None,source_mode='live',agent_registration_id='orders-v1',actor=None,episode_id=None):
        episode_id=episode_id or new_id('episode')
        if agent_registration_id=='orders-v1':
            registered=self.store.get_record('campaign_registrations',campaign.campaign_id)
            if registered: agent_registration_id=registered['registration_id']
        intent=allocate_intent(campaign.order_id,campaign.task_text,4 if fixture_id=='history-v1' else 1)
        world=await self.world_client.create(episode_id,intent,recipe,fixture_id)
        provenance=Provenance(campaign_id=campaign.campaign_id,episode_id=episode_id,origin='prototype' if purpose=='discovery' else 'faultlab_evaluation',split='promotion' if purpose=='promotion' else 'final_audit' if purpose in ('final_audit','portability') else 'development',arm=arm,source_mode=source_mode,experiment_purpose=purpose,trial_index=trial_index,study_id=study_id or campaign.campaign_id,evidence_context_id=evidence_context_id or campaign.campaign_id,selector_id=selector_id,execution_epoch=campaign.execution_epoch,agent_registration_id=agent_registration_id)
        episode=Episode(**provenance.model_dump(),world_id=world['world_id'],task_id=intent.task_id,scenario_hash=content_hash(recipe),policy_hash=policy.policy_hash,policy_version=policy.version,model=campaign.model,configuration_hash=campaign.configuration_hash,lifecycle='RUNNING',started_at=utc_now())
        self.store.put_record('episodes',episode_id,episode)
        self.store.put_record('private_episode_inputs',episode_id,{'intent':intent.model_dump(mode='json'),'recipe':recipe.model_dump(mode='json'),'fixture_id':fixture_id},immutable=True)
        self.store.append_event(episode_id,type='episode_started',payload={'arm':arm,'source_mode':source_mode})
        meter=EpisodeMeter(campaign=ledger,reservation=reservation,stop=stop)
        journal=Journal(self.store,episode_id,intent)
        broker=BusinessToolBroker(self.world_client,world['world_id'],world['capability'],journal,meter)
        interpreter=PolicyInterpreter(policy.content,broker)
        frozen=self.store.get_record('configurations',campaign.configuration_hash) or {}
        metadata={**provenance.model_dump(mode='json'),'model_id':campaign.model,'policy_hash':policy.policy_hash,'contract_hash':frozen.get('contract_hash'),'scorer_hash':frozen.get('scorer_hash')}
        broker.trace=self.trace; broker.metadata=metadata
        context=EpisodeContext(provenance,broker,interpreter,self.provider,policy.content,policy.policy_hash,policy.decision,metadata,self.trace)
        report=None; lab_error=False; interrupted=False
        try:
            chosen=actor or self.actor or (ReferenceActor() if arm=='B1' else run_prototype)
            report=await asyncio.wait_for(chosen(intent,context),timeout=meter.caps.wall_seconds)
            meter.check()
        except asyncio.CancelledError:
            interrupted=True; episode.reason='TASK_CANCELLED'
        except TimeoutError:
            episode.reason='Episode deadline exhausted; no additional model call'
        except StopRequested:
            interrupted=True; episode.reason='STOP_REQUESTED'
        except ActorReportError as error:
            episode.reason=str(error)
        except BudgetExhausted:
            episode.reason='No final actor report before the frozen episode limit'
        except RuntimeProviderError as error:
            lab_error=True; episode.reason=error.code
        except Exception:
            lab_error=True; episode.reason='PROVIDER_OR_INFRASTRUCTURE_ERROR'
        try:
            meter.usage.wall_seconds=meter.clock()-meter.started
            decision=await self.world_client.snapshot(world['world_id'])
            await self.world_client.stop(world['world_id'])
            await self.world_client.advance(world['world_id'],5,observer=True)
            horizon=await self.world_client.snapshot(world['world_id'])
            faults=await self.world_client.faults(world['world_id'])
            scorer=self.scorer
            if scorer is None:
                from app.referee.checks import score
                scorer=score
            verdict=scorer(intent,report,journal.observations,decision,horizon,episode_id=episode_id,usage=meter.usage,fault_executions=faults,lab_error=lab_error,stopped=interrupted)
            episode.verdict=verdict
            self.store.put_record('verdicts',verdict.verdict_id,verdict,immutable=True)
            self.store.put_record('private_snapshots',episode_id,{'decision':decision.model_dump(mode='json'),'horizon':horizon.model_dump(mode='json')},immutable=True)
        except Exception:
            lab_error=True; episode.reason='SIMULATOR_OR_SCORER_ERROR'
        meter.usage.wall_seconds=meter.clock()-meter.started
        episode.report=report; episode.usage=meter.usage; episode.ended_at=utc_now()
        episode.lifecycle='INTERRUPTED' if interrupted else 'LAB_ERROR' if lab_error else 'COMPLETED'
        self.store.put_record('episodes',episode_id,episode)
        self.store.append_event(episode_id,tick=min(20,meter.usage.ticks),type='episode_interrupted' if interrupted else 'verdict_recorded',role='referee',payload={'lifecycle':episode.lifecycle,'verdict':episode.verdict.model_dump(mode='json') if episode.verdict else None})
        trial=TrialResult(episode_id=episode_id,world_id=world['world_id'],scenario_hash=episode.scenario_hash,policy_hash=policy.policy_hash,arm=arm,trial_index=trial_index,lifecycle=episode.lifecycle,outcome=episode.verdict.outcome if episode.verdict else 'LAB_ERROR',failed_checks=[c.check_id for c in episode.verdict.checks if not c.passed] if episode.verdict else [],fault_scheduled=bool(recipe.primitives),fault_triggered=bool(episode.verdict and all(f.triggered for f in episode.verdict.fault_executions)) if recipe.primitives else False,usage=meter.usage,reason=episode.reason)
        self.store.put_record('trials',episode_id,trial,immutable=True)
        return trial

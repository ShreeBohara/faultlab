"""Single active scheduler with durable lifecycle and explicit fresh execution."""
from __future__ import annotations
import asyncio
from app.config import ConfigurationError
from app.contracts.models import Campaign,CampaignRequest,CampaignBudget,FaultSpec,Episode,content_hash,new_id,utc_now
from app.lab.storage import LabStore,StoreConflict
from app.lab.policies import PolicyRepository
from app.lab.budgets import CampaignLedger,BudgetExhausted,StopRequested
from app.lab.runner import EpisodeRunner
from app.adapters.business_tools import WorldClient

TERMINAL={'NO_CHANGE','STOPPED','COMPLETED','ERROR'}

class LabCoordinator:
    def __init__(self,settings,store=None,runner=None):
        self.settings=settings
        self.store=store or LabStore(settings.artifact_path/'lab.sqlite3')
        self.policies=PolicyRepository(self.store)
        self.runner=runner
        self.active_id=None; self.tasks={}; self.ledgers={}; self.evidence_events={}; self.lock=asyncio.Lock()
        self.registry=None; self.regression_service=None; self.aria_bridge=None; self.evidence_gateway=None
        # Restart never replays an uncertain effect or model call.
        for raw_episode in self.store.list_records('episodes'):
            if raw_episode['lifecycle'] in ('CREATED','RUNNING','SCORING'):
                raw_episode['lifecycle']='INTERRUPTED'; raw_episode['reason']='Process restart interrupted execution'; raw_episode['ended_at']=utc_now().isoformat()
                self.store.put_record('episodes',raw_episode['episode_id'],raw_episode)
        for study in self.store.list_records('baseline_studies'):
            if study['status'] in ('QUEUED','RUNNING'):
                study['status']='INTERRUPTED'; study['reason']='Process restart interrupted fixed study; attempts cannot be replayed'
                self.store.put_record('baseline_studies',study['study_id'],study)
        for retry in self.store.list_records('evidence_retries'):
            if retry['status'] in ('QUEUED','RUNNING'):
                retry['status']='INTERRUPTED'; self.store.put_record('evidence_retries',retry['request_id'],retry)
        for raw in self.store.list_records('campaigns'):
            c=Campaign.model_validate_json(__import__('json').dumps(raw))
            if c.state not in TERMINAL and c.state!='IDLE':
                c.execution_epoch+=1; c.stop_requested=True; c.state='STOPPED'; c.state_seq+=1
                c.terminal_reason='Interrupted by process restart; create a fresh explicit run'
                self.save(c)

    def save(self,campaign):
        campaign.updated_at=utc_now(); self.store.put_record('campaigns',campaign.campaign_id,campaign)
        return campaign
    def get(self,id):
        campaign=self.store.get_model('campaigns',id,Campaign)
        if campaign is None: raise KeyError(id)
        budget=self.store.get_record('budgets',id)
        if budget:
            campaign.reserved_calls=sum(r['calls'] for r in budget['reservations'].values())
            campaign.usage.model_calls=budget['used_calls']
            campaign.usage.input_tokens=budget.get('measured_input_tokens',0)
            campaign.usage.output_tokens=budget.get('measured_output_tokens',0)
            campaign.usage.cost_dollars=budget.get('actual_cost_dollars')
        return campaign
    def transition(self,id,state,reason=None):
        campaign=self.get(id)
        if campaign.stop_requested and state not in ('STOPPED','ERROR'): return campaign
        campaign.state=state; campaign.state_seq+=1
        if reason: campaign.terminal_reason=reason
        return self.save(campaign)

    def config_status(self):
        return {'schema_version':'faultlab/v1','model':self.settings.wandb_model or 'not-configured','model_configured':bool(self.settings.wandb_model and self.settings.wandb_api_key),'live_enabled':self.settings.faultlab_live_enabled,'profile_ids':['offline-v1','live-v1'],'sponsor':{'weave':'PENDING','aria':'PENDING'},'active_campaign_id':self.active_id,'execution_profiles':[{'profile_id':'sandbox-v1','caps':__import__('app.contracts.models',fromlist=['EpisodeBudget']).EpisodeBudget().model_dump(mode='json'),'requires_live':True}]}

    def create(self,request):
        if request.config_profile_id not in ('offline-v1','live-v1'): raise ValueError('Unknown frozen configuration profile')
        if request.config_profile_id=='offline-v1' and request.mode!='baseline': raise ValueError('Offline profile supports labeled reference smoke only')
        caps=CampaignBudget(model_calls=self.settings.faultlab_model_call_cap,tokens=self.settings.faultlab_token_cap,dollars=float(self.settings.faultlab_dollar_cap))
        from app.lab.configuration import frozen_configuration
        frozen=frozen_configuration(self.settings,caps,request.config_profile_id)
        configuration_hash=content_hash(frozen)
        self.store.put_record('configurations',configuration_hash,frozen,immutable=True)
        from app.integrations.registry import AgentRegistry
        registration=AgentRegistry(self.store).register_reference(frozen)
        campaign=Campaign(campaign_id=new_id('campaign'),mode=request.mode,task_text=request.task_text,order_id=request.order_id,config_profile_id=request.config_profile_id,model=frozen['model'],configuration_hash=configuration_hash,caps=caps)
        if request.mode in ('learn','compare'):
            accepted=self.store.get_pointer(f'accepted-policy:{configuration_hash}')
            if accepted:
                version=self.policies.get(accepted)
                if version and version.decision=='ACCEPTED': campaign.active_policy_version=accepted
            if request.mode=='compare' and campaign.active_policy_version=='policy-v0': raise StoreConflict('No accepted policy exists for this frozen configuration')
        self.save(campaign)
        self.store.put_record('campaign_registrations',campaign.campaign_id,{'registration_id':registration.registration_id},immutable=True)
        self.store.compare_and_set_pointer(f'active-policy:{campaign.campaign_id}',None,campaign.active_policy_version)
        return campaign

    def validate_current_caps(self,campaign):
        current_caps=CampaignBudget(model_calls=self.settings.faultlab_model_call_cap,tokens=self.settings.faultlab_token_cap,dollars=float(self.settings.faultlab_dollar_cap))
        if current_caps!=campaign.caps: raise StoreConflict('Current configured campaign caps differ from the frozen campaign')
        return current_caps

    def validate_core_configuration(self,campaign):
        from app.lab.configuration import frozen_configuration
        current_caps=self.validate_current_caps(campaign)
        current=frozen_configuration(self.settings,current_caps,campaign.config_profile_id)
        if content_hash(current)!=campaign.configuration_hash:
            raise StoreConflict('Frozen model, source, contract or budget configuration changed; create a new campaign')
        return current

    async def admit_activity(self,id):
        async with self.lock:
            if self.active_id is not None: raise StoreConflict('Another fresh execution is active')
            campaign=self.get(id)
            self.validate_current_caps(campaign)
            campaign.stop_requested=False; campaign.execution_epoch+=1; self.save(campaign)
            self.active_id=id

    async def start(self,id):
        async with self.lock:
            campaign=self.get(id)
            if self.active_id==id: return campaign
            if self.active_id is not None: raise StoreConflict('Another fresh execution is active')
            if campaign.state!='IDLE': raise StoreConflict('This campaign already started; create a new run')
            live=campaign.config_profile_id=='live-v1'
            if live: self.settings.require_live()
            self.validate_core_configuration(campaign)
            if campaign.mode!='baseline' and not live: raise ValueError('Learn and comparison require explicit live profile')
            ledger=CampaignLedger(self.store,id,campaign.caps,dollar_bound=self.settings.model_call_dollar_bound if live else None)
            if live and (ledger.reserved_calls>campaign.caps.model_calls or ledger.reserved_tokens>campaign.caps.tokens or (ledger.dollar_bound is not None and ledger.reserved_calls*ledger.dollar_bound>campaign.caps.dollars)): raise BudgetExhausted('Mandatory protected batches exceed configured campaign cap')
            self.ledgers[id]=ledger; self.active_id=id
            campaign=self.transition(id,'RUNNING')
            self.tasks[id]=asyncio.create_task(self._execute(id,live),name=f'faultlab-{id}')
            return campaign

    async def stop(self,id):
        campaign=self.get(id)
        if campaign.state=='STOPPED': return campaign
        campaign.stop_requested=True; campaign.execution_epoch+=1; campaign.state='STOPPED'; campaign.state_seq+=1
        campaign.terminal_reason='External stop requested; remote effects are retained'
        self.save(campaign)
        if id in self.ledgers: self.ledgers[id].stopped=True
        # Do not cancel an in-flight HTTP response; no subsequent action will be admitted.
        return campaign

    async def _get_runner(self,live):
        if self.runner is not None: return self.runner,False
        from app.providers.runtime import RuntimeProvider
        world=WorldClient(self.settings.faultlab_simulator_url,self.settings.local_control_token())
        runner=EpisodeRunner(self.store,world,RuntimeProvider(self.settings,live_authorized=live))
        if live:
            from app.telemetry.worker import WeaveWorker
            from app.telemetry.outbox import TelemetryOutbox
            from app.telemetry.tracing import TraceRecorder
            from app.telemetry.evaluations import EvaluationPublisher
            from app.telemetry.datasets import DatasetPublisher
            from app.telemetry.aria_bridge import AriaBridge
            from app.lab.evidence import EvidenceGateway
            worker=WeaveWorker(self.settings,live_authorized=True)
            try: await worker.start()
            except Exception: pass  # Local execution/evidence remains durable; remote barrier will wait.
            outbox=TelemetryOutbox(self.store)
            runner.trace=TraceRecorder(worker,outbox,secrets=(self.settings.wandb_api_key,self.settings.typesafe_api_key))
            runner.telemetry_worker=worker
            self.evidence_gateway=EvidenceGateway(self.store,self.settings.project_path,trace=runner.trace,worker=worker)
            self.evaluation_publisher=EvaluationPublisher(worker,outbox)
            self.dataset_publisher=DatasetPublisher(worker,outbox,self.settings.project_path)
            self.aria_bridge=AriaBridge(worker,outbox,project=self.settings.project_path)
        return runner,True

    async def _execute(self,id,live):
        runner=None; owned=False
        try:
            runner,owned=await self._get_runner(live)
            campaign=self.get(id)
            if campaign.mode=='learn': await self._learning_cycle(campaign,runner)
            elif campaign.mode=='compare': await self._comparison(campaign,runner)
            else:
                recipe=FaultSpec(seed=0,primitives=[])
                trial=await runner.run(campaign,recipe,self.policies.baseline(),arm='B0' if live else 'B1',source_mode='live' if live else 'offline_fixture',ledger=self.ledgers[id] if live else None,stop=lambda:self.get(id).stop_requested)
                current=self.get(id); current.latest_episode_id=trial.episode_id; current.usage=trial.usage; self.save(current)
                if live and trial.lifecycle=='COMPLETED' and self.evidence_gateway:
                    from app.lab.evidence import EvidenceContext,WaitingEvidence
                    try:
                        await self.evidence_gateway.get(trial.episode_id,EvidenceContext(id,id,id),stopped=lambda:self.get(id).stop_requested)
                        current=self.get(id); current.telemetry_status='weave_verified'; self.save(current)
                    except WaitingEvidence:
                        current=self.get(id); current.telemetry_status='weave_pending'; self.save(current)
                self.transition(id,'ERROR' if trial.lifecycle=='LAB_ERROR' else 'COMPLETED',trial.reason or ('Reference/internal smoke completed; no learning or sponsor acceptance' if not live else 'Baseline completed'))
            if self.aria_bridge and not self.get(id).stop_requested:
                await self._publish_completion(id)
        except (BudgetExhausted,StopRequested) as error:
            self.transition(id,'NO_CHANGE' if not self.get(id).stop_requested else 'STOPPED',str(error) or 'Budget or stop boundary')
        except Exception:
            self.transition(id,'ERROR','Execution failed; inspect persisted local evidence')
        finally:
            if owned and runner:
                await runner.world_client.close()
                if runner.provider: await runner.provider.close()
                if getattr(runner,'telemetry_worker',None): await runner.telemetry_worker.close()
            async with self.lock:
                if self.active_id==id: self.active_id=None

    async def _learning_cycle(self,campaign,runner):
        from app.lab.learning import run_learning_cycle
        await run_learning_cycle(self,campaign,runner)

    async def _comparison(self,campaign,runner):
        from app.lab.evaluation import PairedEvaluator,load_cases
        evaluator=PairedEvaluator(self.store,runner,self.ledgers[campaign.campaign_id],publisher=getattr(self,'evaluation_publisher',None))
        batch=await evaluator.run(campaign,load_cases('promotion'),self.policies.baseline(),self.policies.get(campaign.active_policy_version),purpose='promotion',stop=lambda:self.get(campaign.campaign_id).stop_requested)
        self.transition(campaign.campaign_id,'COMPLETED',f'Comparison recorded: {batch.decision}')

    async def publish_regression_dataset(self,bundle,*,publisher=None):
        rows=[]; source_ids=[]
        for trial in bundle.trial_results:
            episode=self.store.get_record('episodes',trial.episode_id)
            evidence=self.store.get_record('evidence',trial.episode_id)
            if not episode or not evidence or evidence['source']!='weave_verified': continue
            if episode['split']!='development' or episode['experiment_purpose'] in ('selection_comparison','diagnostic_profile','promotion','final_audit','portability'): continue
            source_ids.append(trial.episode_id)
            rows.append({'episode_id':trial.episode_id,'split':'development','source_mode':'live','experiment_purpose':episode['experiment_purpose'],'trial':trial.model_dump(mode='json'),'policy_hash':bundle.policy_hash,'target_invariant':bundle.target_invariant,'bundle_id':bundle.bundle_id})
        try:
            result=await (publisher or self.dataset_publisher).publish(bundle.bundle_id,name='faultlab-development-'+bundle.bundle_id,rows=rows,regression_hash=bundle.manifest_hash,source_episode_ids=source_ids,authorize=lambda episode_id:(self.store.get_record('evidence',episode_id) or {}).get('source')=='weave_verified')
            self.store.put_record('regression_datasets',bundle.bundle_id,result)
        except Exception:
            self.store.put_record('regression_datasets',bundle.bundle_id,{'state':'PENDING','reason':'Required verified development dataset publication is unavailable'})

    async def _publish_completion(self,id,*,bridge=None):
        campaign=self.get(id)
        setup=self.store.get_record('aria_setup',self.settings.project_path)
        if setup is None:
            # A Finished run may trigger a real Aria automation. Leave that
            # action pending until its observed setup is explicitly registered.
            campaign.aria_status='PENDING'; self.save(campaign)
            return {'campaign_id':id,'state':'awaiting_aria_setup','reason':'Observed Aria automation setup is not registered; no Finished campaign was published'}
        eligible={e['episode_id']:e for e in self.store.list_records('episodes') if e['campaign_id']==id and e['split']=='development' and e['experiment_purpose'] not in ('selection_comparison','diagnostic_profile')}
        links=[]; table=[]
        for raw in self.store.list_records('evidence'):
            if raw['episode_id'] not in eligible or raw['source']!='weave_verified': continue
            episode=eligible[raw['episode_id']]
            # Actual call identifier from retrieved trace, with the supported W&B call page path.
            url='https://wandb.ai/'+self.settings.project_path+'/weave/calls/'+raw['root_call_id']
            links.append({'episode_id':raw['episode_id'],'url':url,'status':'weave_verified','split':'development','experiment_purpose':episode['experiment_purpose']})
            table.append({'episode_id':raw['episode_id'],'split':'development','experiment_purpose':episode['experiment_purpose'],'outcome':episode['verdict']['outcome'] if episode.get('verdict') else None,'report':episode['report'],'findings':raw['findings']})
        try:
            result=await (bridge or self.aria_bridge).publish_campaign(id,completed=campaign.state in TERMINAL,development_summary={'episodes':len(table),'active_policy_version':campaign.active_policy_version,'terminal_state':campaign.state},verified_links=links,evidence_table=table,authorize=lambda link:link.get('episode_id') in eligible and any(e['episode_id']==link.get('episode_id') and e['source']=='weave_verified' for e in self.store.list_records('evidence')))
            if result.get('run_id') and setup:
                self.store.put_record('aria_bindings',id,{**result,'automation_id':setup['automation_id'],'verified_source_refs':[d['episode_id'] for d in links]},immutable=True)
            campaign.aria_status='PENDING'; self.save(campaign)
            return result
        except Exception:
            campaign.aria_status='PENDING' if not links or not setup else 'FAILED'; self.save(campaign)

    async def _evidence_retry_services(self):
        # Separate telemetry context: never replace an active campaign's provider,
        # trace recorder, gateway or publisher while synchronizing saved evidence.
        from app.telemetry.worker import WeaveWorker
        from app.telemetry.outbox import TelemetryOutbox
        from app.telemetry.tracing import TraceRecorder
        from app.telemetry.datasets import DatasetPublisher
        from app.lab.evidence import EvidenceGateway
        worker=WeaveWorker(self.settings,live_authorized=True)
        outbox=TelemetryOutbox(self.store)
        trace=TraceRecorder(worker,outbox,secrets=(self.settings.wandb_api_key,self.settings.typesafe_api_key))
        gateway=EvidenceGateway(self.store,self.settings.project_path,trace=trace,worker=worker)
        return worker,gateway,DatasetPublisher(worker,outbox,self.settings.project_path)

    async def retry_evidence(self,id,episode_ids=None):
        self.get(id)
        episodes={e['episode_id']:e for e in self.store.list_records('episodes') if e['campaign_id']==id}
        requested=set(episodes) if episode_ids is None else set(episode_ids)
        if not requested<=set(episodes): raise ValueError('Unregistered campaign episode')
        async with self.lock:
            for old in self.store.list_records('evidence_retries'):
                if old['campaign_id']==id and old['status'] in ('QUEUED','RUNNING'):
                    return old
            record={'request_id':new_id('evidence-retry'),'campaign_id':id,'episode_ids':sorted(requested),'status':'QUEUED','outcomes':{},'datasets':{}}
            for episode_id in sorted(requested):
                e=episodes[episode_id]
                eligible=e['source_mode']=='live' and e['lifecycle']=='COMPLETED' and e['split']=='development' and e['arm']!='B1'
                record['outcomes'][episode_id]={'status':'PENDING' if eligible else 'SKIPPED_INELIGIBLE'}
            self.store.put_record('evidence_retries',record['request_id'],record)
            self.tasks[record['request_id']]=asyncio.create_task(self._retry_evidence_job(record))
            return record

    async def _retry_evidence_job(self,record):
        worker=None; id=record['campaign_id']
        def save(): self.store.put_record('evidence_retries',record['request_id'],record)
        record['status']='RUNNING'; save()
        try:
            eligible=[eid for eid,result in record['outcomes'].items() if result['status']=='PENDING']
            from app.contracts.models import RegressionBundle
            bundles=[raw for raw in self.store.list_records('bundles') if any(ref in record['episode_ids'] for ref in raw['source_refs']) and (self.store.get_record('regression_datasets',raw['bundle_id']) or {}).get('state')!='VERIFIED']
            if eligible or bundles:
                # One 60-second job deadline covers startup, upload, readback and
                # dataset retry; a long inventory cannot hold the request open.
                async with asyncio.timeout(60):
                    worker,gateway,publisher=await self._evidence_retry_services()
                    await worker.start()
                    for episode_id in eligible:
                        try:
                            bundle=await gateway.retry(episode_id)
                            record['outcomes'][episode_id]={'status':'VERIFIED' if bundle.source=='weave_verified' else 'PENDING'}
                        except Exception:
                            record['outcomes'][episode_id]={'status':'PENDING','reason':'Saved evidence synchronization is unavailable'}
                        save()
                    for raw in bundles:
                        bundle=RegressionBundle.model_validate_json(__import__('json').dumps(raw))
                        await self.publish_regression_dataset(bundle,publisher=publisher)
                        record['datasets'][bundle.bundle_id]=self.store.get_record('regression_datasets',bundle.bundle_id); save()
                    if self.get(id).state in ('COMPLETED','NO_CHANGE') and any(r['status']=='VERIFIED' for r in record['outcomes'].values()):
                        from app.telemetry.aria_bridge import AriaBridge
                        from app.telemetry.outbox import TelemetryOutbox
                        bridge=AriaBridge(worker,TelemetryOutbox(self.store),project=self.settings.project_path)
                        # Sponsor bridge owns immutable publication-intent dedup:
                        # an uncertain Finished outcome is never retriggered here.
                        record['aria']=await self._publish_completion(id,bridge=bridge); save()
            record['status']='COMPLETED'
        except TimeoutError:
            record['status']='TIMED_OUT'
        except asyncio.CancelledError:
            record['status']='INTERRUPTED'
            raise
        except Exception:
            record['status']='PENDING'
        finally:
            if worker:
                try: await asyncio.wait_for(worker.close(),timeout=2)
                except Exception: pass
            current=self.get(id)
            attempted=[value for value in record['outcomes'].values() if value['status']!='SKIPPED_INELIGIBLE']
            if attempted: current.telemetry_status='weave_verified' if all(r['status']=='VERIFIED' for r in attempted) else 'weave_pending'
            self.save(current); save()
            if id in self.evidence_events: self.evidence_events[id].set()

    async def close(self):
        if self.active_id is not None:
            try: await self.stop(self.active_id)
            except KeyError: pass
        pending=[t for t in self.tasks.values() if not t.done()]
        if pending:
            done,pending=await asyncio.wait(pending,timeout=2)
            for task in pending: task.cancel()
            await asyncio.gather(*pending,return_exceptions=True)
        self.store.close()

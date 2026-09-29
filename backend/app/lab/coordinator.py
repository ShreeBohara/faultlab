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

class EvidenceRetryAfterStop(StopRequested):
    """An automatic evidence retry refused because its campaign's Stop was already requested."""

class LabCoordinator:
    def __init__(self,settings,store=None,runner=None):
        from app.lab.ownership import CoordinatorLease
        path=store.path if store is not None else settings.artifact_path/'lab.sqlite3'
        # Recovery is a writer action. Ownership precedes opening a writable
        # connection, policy initialization and every crash-recovery mutation.
        self._lease=CoordinatorLease.acquire(path,store_identity=store)
        self._closed=False
        try:
            self.store=store if store is not None else LabStore(path)
            self.store.on_close(self._lease.close)
            self._initialize(settings,runner)
        except BaseException:
            try:
                if store is None and hasattr(self,'store'): self.store.close()
            finally: self._lease.close()
            raise

    def _initialize(self,settings,runner):
        self.settings=settings
        self.policies=PolicyRepository(self.store)
        self.runner=runner
        self.active_id=None; self.tasks={}; self.ledgers={}; self.evidence_events={}; self.lock=asyncio.Lock()
        self.registry=None; self.regression_service=None; self.aria_bridge=None; self.evidence_gateway=None
        # Restart never replays an uncertain effect or model call.
        for raw_episode in self.store.list_records('episodes'):
            if raw_episode['lifecycle'] in ('CREATED','RUNNING','SCORING'):
                raw_episode['lifecycle']='INTERRUPTED'; raw_episode['reason']='Process restart interrupted execution'; raw_episode['ended_at']=utc_now().isoformat()
                self.store.put_record('episodes',raw_episode['episode_id'],raw_episode)
        self._recover_auxiliary_jobs()
        # Only these prospective failure markers authorize cleanup on a terminal
        # campaign. Prior terminal campaigns/records are never reinterpreted.
        for key_record in self.store.list_records('reservation_finalization_failures'):
            if key_record.get('status')!='PENDING': continue
            campaign_id=key_record['campaign_id']; reservation=key_record['reservation']
            with self.store.transaction():
                self._release_abandoned_reservation(campaign_id,reservation)
                key_record.update(status='RECOVERED',recovered_at=utc_now().isoformat())
                self.store.put_record('reservation_finalization_failures',campaign_id+':'+reservation,key_record)
        for kind in ('baseline_studies','completion_studies','context_studies'):
            for study in self.store.list_records(kind):
                if study['status'] in ('QUEUED','RUNNING'):
                    with self.store.transaction():
                        study['status']='INTERRUPTED'; study['reason']='Process restart interrupted fixed study; attempts cannot be replayed'
                        if kind in ('completion_studies','context_studies'):
                            study['decision']='INCOMPLETE'
                            for slot in study['slots']:
                                if slot['status']=='RUNNING': slot['status']='INTERRUPTED'
                        self.store.put_record(kind,study['study_id'],study)
                        # An interrupted study's model-call reservation is never spent;
                        # leaving it in the ledger permanently understates the campaign's
                        # remaining cap for every later admission check.
                        budget=self.store.get_record('budgets',study.get('campaign_id',''))
                        if budget and isinstance(budget.get('reservations'),dict):
                            prefix={'completion_studies':'completion:','context_studies':'context:','baseline_studies':'baseline:'}[kind]
                            released={name:value for name,value in budget['reservations'].items() if name!=prefix+study['study_id']}
                            if released!=budget['reservations']:
                                budget['reservations']=released
                                self.store.put_record('budgets',study['campaign_id'],budget)
        # A held-out check runs on a dedicated campaign; its evaluator reservation is
        # named 'promotion:<batch>' and is never spent after a restart.
        for check in self.store.list_records('heldout_checks'):
            if check['status'] in ('QUEUED','RUNNING'):
                with self.store.transaction():
                    check['status']='INTERRUPTED'; check['decision']='INCOMPLETE'
                    check['reason']='Process restart interrupted the held-out check; attempts cannot be replayed'
                    integrity_findings=[]
                    try:
                        from app.lab.heldout_check import stored_candidate_failures,heldout_integrity_findings,world_integrity_assessment,WORLD_INTEGRITY_PROTOCOL
                        integrity_findings=heldout_integrity_findings(self.store,check)
                        stored=stored_candidate_failures(self.store,check.get('campaign_id'),check.get('policy_hash'),excluded_episode_ids={row['episode_id'] for row in integrity_findings})
                    except Exception as scan_error:
                        stored=[]; check['recovery_error']=type(scan_error).__name__
                        if check.get('world_integrity_protocol')==WORLD_INTEGRITY_PROTOCOL:
                            if check.get('assessment') is not None: check['diagnostic_legacy_assessment']=check['assessment']
                            check['reason']='World execution integrity could not be verified after restart'
                            check['assessment']={'decision':'INCOMPLETE','rule':'world_integrity_unavailable','reason':check['reason']}
                    if integrity_findings and 'recovery_error' not in check:
                        prior=check.get('assessment')
                        assessment=world_integrity_assessment(prior,integrity_findings,stored)
                        if prior is not None: check['diagnostic_legacy_assessment']=prior
                        check.update(world_integrity_findings=integrity_findings,candidate_failures=stored,
                                     decision=assessment['decision'],reason=assessment['reason'],assessment=assessment,
                                     status='COMPLETED' if assessment['decision']=='HARM' else 'INTERRUPTED',ended_at=utc_now().isoformat())
                    elif stored:
                        reason='A candidate trial failed a C1-C8 check (recovered from stored trials after a restart)'
                        check.update(status='COMPLETED',decision='HARM',candidate_failures=stored,reason=reason,
                                     ended_at=utc_now().isoformat(),
                                     assessment={'decision':'HARM','rule':'check_failure','reason':reason,'candidate_failures':stored})
                    self.store.put_record('heldout_checks',check['check_id'],check)
                    budget=self.store.get_record('budgets',check.get('campaign_id',''))
                    if budget and isinstance(budget.get('reservations'),dict):
                        released={name:value for name,value in budget['reservations'].items() if not name.startswith('promotion:')}
                        if released!=budget['reservations']:
                            budget['reservations']=released
                            self.store.put_record('budgets',check['campaign_id'],budget)
        for retry in self.store.list_records('evidence_retries'):
            if retry['status'] in ('QUEUED','RUNNING'):
                retry['status']='INTERRUPTED'; self.store.put_record('evidence_retries',retry['request_id'],retry)
        # An open evidence wait belongs to an execution this restart interrupts (its campaign becomes STOPPED below).
        for wait in self.store.list_records('evidence_waits'):
            if wait.get('ended_at') is None:
                wait.update(status='INTERRUPTED',resolution='INTERRUPTED',next_automatic_retry_at=None,ended_at=utc_now().isoformat(),
                            message='Process restart interrupted the evidence wait; no automatic retry continues after a restart.')
                self.store.put_record('evidence_waits',wait['wait_id'],wait)
        for request in self.store.list_records('evaluation_requests'):
            if request['status'] in ('QUEUED','RUNNING'):
                with self.store.transaction():
                    request.update(status='INTERRUPTED',reason='Process restart interrupted evaluation; saved attempts are not replayed',ended_at=utc_now().isoformat())
                    self.store.put_record('evaluation_requests',request['request_id'],request)
                    budget=self.store.get_record('budgets',request.get('campaign_id',''))
                    reservation='promotion:'+request.get('batch_id','')
                    if budget and reservation in budget.get('reservations',{}):
                        budget['reservations'].pop(reservation)
                        self.store.put_record('budgets',request['campaign_id'],budget)
        for execution in self.store.list_records('regression_executions'):
            if execution['mode']=='FRESH_SANDBOX' and execution['status'] in ('PENDING','RUNNING'):
                from app.lab.regression_executions import interrupt_regression
                with self.store.transaction():
                    interrupt_regression(self.store,execution['execution_id'],'Process restart interrupted execution; saved effects are not replayed')
                    # Legacy execution records omit campaign identity; release only
                    # this exact globally unique job reservation, wherever stored.
                    for campaign in self.store.list_records('campaigns'):
                        self._release_abandoned_reservation(campaign['campaign_id'],'regression:'+execution['execution_id'])
        for raw in self.store.list_records('campaigns'):
            c=Campaign.model_validate_json(__import__('json').dumps(raw))
            if c.state not in TERMINAL and c.state!='IDLE':
                with self.store.transaction():
                    budget=self.store.get_record('budgets',c.campaign_id)
                    if budget and isinstance(budget.get('reservations'),dict):
                        # Only unfinished job reservations are abandoned. Protected
                        # future work, unknown names and already charged usage survive.
                        prefixes=('candidate:','reproduce:','reduce:','intervention:','pair-retry:','promotion:')
                        released={name:value for name,value in budget['reservations'].items() if not name.startswith(prefixes)}
                        if released!=budget['reservations']:
                            budget['reservations']=released
                            self.store.put_record('budgets',c.campaign_id,budget)
                    self.incomplete_qualifications(c.campaign_id,'Process restart interrupted qualification; saved attempts are not replayed')
                    c.execution_epoch+=1; c.stop_requested=True; c.state='STOPPED'; c.state_seq+=1
                    c.terminal_reason='Interrupted by process restart; create a fresh explicit run'
                    self.save(c)
    def _release_abandoned_reservation(self,campaign_id,name):
        budget=self.store.get_record('budgets',campaign_id)
        if budget and name in budget.get('reservations',{}):
            budget['reservations'].pop(name)
            self.store.put_record('budgets',campaign_id,budget)

    def _recover_auxiliary_jobs(self):
        """Recover only durable unfinished jobs, never unused future capacity."""
        reason='Process restart interrupted study; saved attempts are not replayed'
        from app.lab.audit import retain_audit_progress
        from app.lab.search_benchmark import retain_search_progress
        from app.lab.portability import interrupt_portability
        for record in self.store.list_records('audit_results'):
            if record['status'] not in ('QUEUED','PENDING','RUNNING'): continue
            with self.store.transaction():
                retain_audit_progress(self.store,record)
                record.update(status='INCOMPLETE',reason=reason,ended_at=utc_now().isoformat())
                self.store.put_record('audit_results',record['batch_id'],record)
                self._release_abandoned_reservation(record['campaign_id'],'final_audit')
        comparisons={row['comparison_id']:row for row in self.store.list_records('search_comparisons')}
        for record in comparisons.values():
            if record['status'] not in ('QUEUED','PENDING','RUNNING'): continue
            with self.store.transaction():
                retain_search_progress(self.store,record)
                record.update(status='INCOMPLETE',stopping_reason=reason)
                self.store.put_record('search_comparisons',record['comparison_id'],record)
                self._release_abandoned_reservation(record['campaign_id'],'selection_comparison')
        for record in self.store.list_records('search_requests'):
            if record['status'] not in ('QUEUED','PENDING','RUNNING'): continue
            comparison=comparisons.get(record.get('comparison_id'))
            campaign_id=record.get('campaign_id') or (comparison or {}).get('campaign_id')
            record.update(status=comparison['status'] if comparison else 'INCOMPLETE',reason=reason,
                          ended_at=utc_now().isoformat())
            if campaign_id: record['campaign_id']=campaign_id
            with self.store.transaction():
                self.store.put_record('search_requests',record['request_id'],record)
                if campaign_id: self._release_abandoned_reservation(campaign_id,'selection_comparison')
        requests=self.store.list_records('portability_requests')
        recovered_results=set()
        for record in requests:
            if record['status'] not in ('QUEUED','PENDING','RUNNING'): continue
            with self.store.transaction():
                interrupt_portability(self.store,record,reason)
                self.store.put_record('portability_requests',record['request_id'],record)
                self._release_abandoned_reservation(record['campaign_id'],'portability')
            if record.get('portability_id'): recovered_results.add(record['portability_id'])
        # Older writers persisted a result before linking the queued request.
        # Bind such a result through its immutable freeze, never by policy alone.
        freezes={row['portability_id']:row['freeze']['freeze_hash']
                 for row in self.store.list_records('portability_freezes')}
        campaigns={}
        for campaign in self.store.list_records('campaigns'):
            freeze=self.store.get_record('external_freezes',campaign['campaign_id'])
            if freeze: campaigns.setdefault(freeze['freeze_hash'],[]).append(campaign['campaign_id'])
        for result in self.store.list_records('portability'):
            if result['status'] not in ('PENDING','RUNNING') or result['portability_id'] in recovered_results: continue
            owners=campaigns.get(freezes.get(result['portability_id']),[])
            if len(owners)==1:
                recovery={'campaign_id':owners[0],'portability_id':result['portability_id'],
                          'freeze_hash':freezes[result['portability_id']]}
                with self.store.transaction():
                    interrupt_portability(self.store,recovery,reason)
                    self.store.put_record('portability_recovery',result['portability_id'],recovery)
                    self._release_abandoned_reservation(owners[0],'portability')
            else:
                result['status']='INCOMPLETE'
                if len(result['limitations'])<16: result['limitations'].append(reason)
                self.store.put_record('portability',result['portability_id'],result)

    def incomplete_qualifications(self,campaign_id,reason,*,error=None,interruption=None):
        """Finalize current pending work without changing prior terminal decisions.

        ``error`` is a safe execution failure (readiness.execution_failure); a stop is not an error and
        passes ``interruption`` instead (e.g. STOPPED_DURING_EVIDENCE_WAIT from app.lab.evidence_wait).
        """
        for qualification in self.store.list_records('candidate_qualifications'):
            if qualification.get('campaign_id')!=campaign_id or qualification.get('decision')!='PROPOSED': continue
            qualification.update(decision='INCOMPLETE',interruption_reason=reason)
            if error is not None: qualification['error']=error
            if interruption is not None: qualification['interruption']=interruption
            candidate=self.policies.get(qualification['candidate_version'])
            with self.store.transaction():
                self.store.put_record('candidate_qualifications',qualification['qualification_ref'],qualification)
                if candidate is not None and candidate.decision=='PROPOSED':
                    candidate.decision='INCOMPLETE'
                    self.policies.save(candidate)

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
        if campaign.stop_requested and state!='STOPPED': return campaign
        campaign.state=state; campaign.state_seq+=1
        if reason: campaign.terminal_reason=reason
        return self.save(campaign)

    def config_status(self):
        from app.lab.dashboard import store_descriptor
        models=self.settings.role_models
        return {'schema_version':'faultlab/v1','data_store':store_descriptor(self.store),'model':models['actor'] or 'not-configured','lab_model':models['explorer'] or 'not-configured','models':models,'actor_context_protocol':self.settings.faultlab_actor_context_protocol,'model_configured':bool(all(models.values()) and self.settings.wandb_api_key),'live_enabled':self.settings.faultlab_live_enabled,'profile_ids':['offline-v1','live-v1'],'sponsor':{'weave':'PENDING','aria':'PENDING'},'active_campaign_id':self.active_id,'execution_profiles':[{'profile_id':'sandbox-v1','caps':__import__('app.contracts.models',fromlist=['EpisodeBudget']).EpisodeBudget().model_dump(mode='json'),'requires_live':True}]}

    async def readiness(self):
        from app.lab.readiness import simulator_readiness
        simulator = ({'ready':True,'code':'INJECTED_RUNNER','message':'Explicit test runner supplied.'}
                     if self.runner is not None else await simulator_readiness(self.settings))
        try:
            self.settings.require_live()
            live={'ready':True,'missing_fields':[]}
        except ConfigurationError as error:
            live={'ready':False,'missing_fields':list(error.missing_fields)}
        return {'ready':simulator['ready'],'simulator':simulator,'live_configuration':live,
                'provider_access':'not_checked','provider_calls':0,'models':self.settings.role_models}

    async def require_simulator(self):
        from app.lab.readiness import ServiceNotReady
        readiness=await self.readiness()
        if not readiness['ready']:
            raise ServiceNotReady(readiness['simulator']['code']+': '+readiness['simulator']['message'])

    def create(self,request,*,run_plan=None):
        if request.config_profile_id not in ('offline-v1','live-v1'): raise ValueError('Unknown frozen configuration profile')
        if request.config_profile_id=='offline-v1' and request.mode!='baseline': raise ValueError('Offline profile supports labeled reference smoke only')
        caps=CampaignBudget(model_calls=self.settings.faultlab_model_call_cap,tokens=self.settings.faultlab_token_cap,dollars=float(self.settings.faultlab_dollar_cap))
        from app.lab.configuration import frozen_configuration
        if run_plan is not None and run_plan.campaign_request!=request:
            raise StoreConflict('Prepared plan differs from the requested campaign')
        frozen=run_plan.configuration if run_plan is not None else frozen_configuration(self.settings,caps,request.config_profile_id)
        configuration_hash=content_hash(frozen)
        from app.integrations.registry import AgentRegistry
        from app.lab.configuration import source_provenance
        # No partially created campaign may escape if a plan, registration or
        # immutable pointer cannot be bound to the same selected configuration.
        with self.store.transaction():
            self.store.put_record('configurations',configuration_hash,frozen,immutable=True)
            registry=AgentRegistry(self.store)
            if run_plan is not None and request.config_profile_id=='offline-v1':
                # The provider-free built-in option is prepared in a private
                # value sink; its reviewed registration becomes durable here.
                expected=registry.register_reference(frozen,internal_smoke=True)
                if expected!=run_plan.registration:
                    raise StoreConflict('Prepared offline registration differs from the reviewed control')
            registration=(registry.verify(run_plan.registration.registration_id,frozen)
                          if run_plan is not None else registry.register_reference(frozen))
            campaign=Campaign(campaign_id=new_id('campaign'),mode=request.mode,task_text=request.task_text,order_id=request.order_id,config_profile_id=request.config_profile_id,model=frozen['model'],configuration_hash=configuration_hash,caps=caps)
            if request.mode in ('learn','compare'):
                accepted=self.store.get_pointer(f'accepted-policy:{configuration_hash}')
                if accepted:
                    version=self.policies.get(accepted)
                    if version and version.decision=='ACCEPTED': campaign.active_policy_version=accepted
                if request.mode=='compare' and campaign.active_policy_version=='policy-v0': raise StoreConflict('No accepted policy exists for this frozen configuration')
            self.save(campaign)
            self.store.put_record('campaign_registrations',campaign.campaign_id,{'registration_id':registration.registration_id},immutable=True)
            marker={}
            if run_plan is not None:
                from app.lab.run_plans import attach_run_plan
                marker=attach_run_plan(self.store,campaign,run_plan)
            self.store.put_record('campaign_provenance',campaign.campaign_id,
                                  {**source_provenance(),'aria_publication_enabled':self.settings.faultlab_aria_publish_enabled,**marker},immutable=True)
            self.store.compare_and_set_pointer(f'active-policy:{campaign.campaign_id}',None,campaign.active_policy_version)
            if run_plan is not None:
                from app.lab.run_plans import validate_run_plan
                validate_run_plan(self.store,self.settings,campaign)
        return campaign

    def validate_current_caps(self,campaign):
        current_caps=CampaignBudget(model_calls=self.settings.faultlab_model_call_cap,tokens=self.settings.faultlab_token_cap,dollars=float(self.settings.faultlab_dollar_cap))
        if current_caps!=campaign.caps: raise StoreConflict('Current configured campaign caps differ from the frozen campaign')
        return current_caps

    def validate_core_configuration(self,campaign):
        from app.lab.configuration import frozen_configuration
        current_caps=self.validate_current_caps(campaign)
        from app.lab.run_plans import validate_run_plan
        if validate_run_plan(self.store,self.settings,campaign) is not None:
            return self.store.get_record('configurations',campaign.configuration_hash)
        current=frozen_configuration(self.settings,current_caps,campaign.config_profile_id)
        if content_hash(current)!=campaign.configuration_hash:
            raise StoreConflict('Frozen model, source, contract or budget configuration changed; create a new campaign')
        return current

    async def admit_activity(self,id):
        from app.lab.policies import require_ordinary_campaign
        async with self.lock:
            require_ordinary_campaign(self.store,id)
            if self.active_id is not None: raise StoreConflict('Another fresh execution is active')
            campaign=self.get(id)
            self.validate_current_caps(campaign)
            await self.require_simulator()
            campaign.stop_requested=False; campaign.execution_epoch+=1; self.save(campaign)
            if id in self.ledgers: self.ledgers[id].stopped=False
            self.active_id=id

    async def start(self,id):
        async with self.lock:
            campaign=self.get(id)
            if self.store.get_record('import_execution_owners',id):
                raise StoreConflict('Imported regression owners cannot start ordinary campaigns; use the reviewed import execution action')
            if self.active_id==id: return campaign
            if self.active_id is not None: raise StoreConflict('Another fresh execution is active')
            if campaign.state!='IDLE': raise StoreConflict('This campaign already started; create a new run')
            live=campaign.config_profile_id=='live-v1'
            if live: self.settings.require_live()
            self.validate_core_configuration(campaign)
            if campaign.mode!='baseline' and not live: raise ValueError('Learn and comparison require explicit live profile')
            from app.lab.budgets import protected_reservations
            protected=protected_reservations(campaign.caps)
            protected_calls=sum(r['calls'] for r in protected.values())
            protected_tokens=sum(r['tokens'] for r in protected.values())
            dollar_bound=self.settings.model_call_dollar_bound if live else None
            if live and (protected_calls>campaign.caps.model_calls or protected_tokens>campaign.caps.tokens or
                         (dollar_bound is not None and protected_calls*dollar_bound>campaign.caps.dollars)):
                raise BudgetExhausted('Mandatory protected batches exceed configured campaign cap')
            await self.require_simulator()
            ledger=CampaignLedger(self.store,id,campaign.caps,dollar_bounds=self.settings.model_call_dollar_bounds if live else None)
            if live and (ledger.reserved_calls>campaign.caps.model_calls or ledger.reserved_tokens>campaign.caps.tokens or (ledger.dollar_bound is not None and ledger.reserved_calls*ledger.dollar_bound>campaign.caps.dollars)): raise BudgetExhausted('Mandatory protected batches exceed configured campaign cap')
            self.ledgers[id]=ledger; self.active_id=id
            campaign=self.transition(id,'RUNNING')
            self.tasks[id]=asyncio.create_task(self._execute(id,live),name=f'faultlab-{id}')
            return campaign

    async def stop(self,id):
        campaign=self.get(id)
        # A stop applies only to work this scheduler currently owns. Historical
        # campaign state is not a job handle: auxiliary studies can run on an
        # IDLE/terminal campaign, and inactive saved campaigns must stay unchanged.
        if self.active_id!=id: return campaign
        if campaign.state=='STOPPED' and campaign.stop_requested: return campaign
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
                from app.lab.run_plans import validate_run_plan
                plan=validate_run_plan(self.store,self.settings,campaign)
                selection=plan['selection'] if plan else None
                recipe=(FaultSpec.model_validate(selection['fault_spec']) if selection else FaultSpec(seed=0,primitives=[]))
                fixture_id=selection['fixture_id'] if selection else 'standard-v1'
                trial=await runner.run(campaign,recipe,self.policies.baseline(),fixture_id=fixture_id,arm='B0' if live else 'B1',source_mode='live' if live else 'offline_fixture',ledger=self.ledgers[id] if live else None,stop=lambda:self.get(id).stop_requested)
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
            stopped=self.get(id).stop_requested
            # An empty StopRequested (a model-call charge or evidence read that noticed the Stop) adds nothing:
            # keep the reason the Stop already saved rather than the vague 'Budget or stop boundary'.
            self.transition(id,'STOPPED' if stopped else 'NO_CHANGE',str(error) or (None if stopped else 'Budget or stop boundary'))
        except asyncio.CancelledError:
            if not self.get(id).stop_requested:
                await self.stop(id)
                current=self.get(id); current.terminal_reason='Execution interrupted; saved effects are not replayed'; self.save(current)
            raise
        except Exception as error:
            from app.lab.readiness import execution_failure
            failure=execution_failure(error)
            self.store.put_record('execution_errors',id,{'campaign_id':id,**failure,'recorded_at':utc_now().isoformat()})
            self.transition(id,'ERROR',failure['code']+': '+failure['message'])
        finally:
            await self.finish_activity(id,runner,owned=owned,activity_id=id)

    async def finish_activity(self,campaign_id,runner=None,*,owned=False,activity_id=None):
        """Close each owned resource and always release scheduler admission.

        Cleanup failures have their own safe diagnostics; they do not turn an
        already stopped or completed execution into a different result.
        """
        errors=[]; cancelled=False
        try:
            if owned and runner:
                from app.lab.readiness import execution_failure
                for name in ('world_client','provider','telemetry_worker'):
                    resource=getattr(runner,name,None)
                    if resource is None: continue
                    try:
                        await asyncio.wait_for(resource.close(),timeout=2)
                    except asyncio.CancelledError:
                        cancelled=True
                        errors.append({'resource':name,'code':'CLEANUP_INTERRUPTED','message':'Resource cleanup interrupted'})
                    except Exception as error:
                        errors.append({'resource':name,**execution_failure(error)})
                if errors:
                    key=activity_id or campaign_id
                    self.store.put_record('resource_cleanup_errors',key,{'activity_id':key,'campaign_id':campaign_id,'errors':errors,'recorded_at':utc_now().isoformat()})
        finally:
            if self.active_id==campaign_id: self.active_id=None
        if cancelled: raise asyncio.CancelledError()

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
        if not self.settings.faultlab_aria_publish_enabled:
            campaign.aria_status='PENDING'; self.save(campaign)
            result={'campaign_id':id,'state':'publication_disabled',
                    'reason':'This execution explicitly enables Inference/Weave only; no Finished run was published.'}
            self.store.put_record('sponsor_publication_deferrals',id,result)
            return result
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

    async def retry_evidence(self,id,episode_ids=None,*,automatic=None):
        """Telemetry-only evidence retry: re-send saved trace records and read them back; never re-execute.

        ``automatic`` (app.lab.evidence_wait) marks a declared automatic retry of one evidence wait
        ({evidence_wait_id, attempt, attempts_max}). An operator's request is ``trigger: manual``.
        An explicit episode list (automatic, or the dashboard's needs-operator notice) is tried in the
        given order, blocked episode first; no list means every campaign episode, in id order. At most
        one retry job runs per campaign: while one is QUEUED or RUNNING, that job's record is returned
        instead. An automatic retry is refused once a Stop was requested (EvidenceRetryAfterStop).
        """
        self.get(id)
        episodes={e['episode_id']:e for e in self.store.list_records('episodes') if e['campaign_id']==id}
        requested=set(episodes) if episode_ids is None else set(episode_ids)
        if not requested<=set(episodes): raise ValueError('Unregistered campaign episode')
        order=list(dict.fromkeys(episode_ids)) if episode_ids is not None else sorted(requested)
        async with self.lock:
            # Checked again under the lock: a Stop may have arrived while this request waited for it.
            if automatic is not None and self.get(id).stop_requested:
                raise EvidenceRetryAfterStop('Stop requested; no automatic evidence retry is started')
            for old in self.store.list_records('evidence_retries'):
                if old['campaign_id']==id and old['status'] in ('QUEUED','RUNNING'):
                    return old
            record={'request_id':new_id('evidence-retry'),'campaign_id':id,'episode_ids':sorted(requested),'status':'QUEUED','outcomes':{},'datasets':{},
                    'trigger':'automatic' if automatic is not None else 'manual','requested_at':utc_now().isoformat()}
            if automatic is not None: record['automatic']=dict(automatic)
            for episode_id in order:
                e=episodes[episode_id]
                eligible=e['source_mode']=='live' and e['lifecycle']=='COMPLETED' and e['split']=='development' and e['arm']!='B1'
                record['outcomes'][episode_id]={'status':'PENDING' if eligible else 'SKIPPED_INELIGIBLE'}
            self.store.put_record('evidence_retries',record['request_id'],record)
            self.tasks[record['request_id']]=asyncio.create_task(self._retry_evidence_job(record))
            return record

    async def _retry_evidence_job(self,record):
        worker=None; id=record['campaign_id']
        def save(): self.store.put_record('evidence_retries',record['request_id'],record)
        # An automatic retry belongs to a running campaign's evidence wait: a Stop ends it at the next step
        # instead of letting it run on for up to the 60-second job deadline. An operator's retry is not stopped.
        automatic=record.get('trigger')=='automatic'
        stopped=(lambda:self.get(id).stop_requested) if automatic else (lambda:False)
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
                        if (self.store.get_record('evidence',episode_id) or {}).get('source')=='weave_verified':
                            # Already verified: nothing to re-send, so the deadline goes to the episodes still pending.
                            record['outcomes'][episode_id]={'status':'VERIFIED','already_verified':True}; save(); continue
                        if stopped():
                            record['outcomes'][episode_id]={'status':'PENDING','reason':'Campaign stopped before this episode was re-sent'}
                            save(); continue
                        try:
                            bundle=await (gateway.retry(episode_id,stopped=stopped) if automatic else gateway.retry(episode_id))
                            record['outcomes'][episode_id]={'status':'VERIFIED' if bundle.source=='weave_verified' else 'PENDING'}
                        except Exception:
                            record['outcomes'][episode_id]={'status':'PENDING','reason':'Saved evidence synchronization is unavailable'}
                        save()
                    for raw in bundles:
                        if stopped(): break
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
        if self._closed: return
        self._closed=True
        try:
            if self.active_id is not None:
                try: await self.stop(self.active_id)
                except KeyError: pass
            pending=[t for t in self.tasks.values() if not t.done()]
            if pending: await asyncio.wait(pending,timeout=2)
        finally:
            try:
                pending=[t for t in self.tasks.values() if not t.done()]
                for task in pending: task.cancel()
                if pending: await asyncio.gather(*pending,return_exceptions=True)
            finally:
                try: self.store.close()
                finally: self._lease.close()

#!/usr/bin/env python3
"""One sealed fresh-repair search followed by one reserved evaluation; dry by default.

Uses the unchanged completion executor and qualification/predicate functions. All
campaigns are new and share one exact configuration. There is no resume, policy
fallback, promotion, private-evidence feedback, or modification of historical stores.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import signal
import socket
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(Path(__file__).resolve().parent))

from app.agents.progress import ACTOR_CONTEXT_PROTOCOL_V4
from app.config import Settings
from app.contracts.models import CampaignBudget, CampaignRequest, PolicyVersion, canonical_json, content_hash, new_id, utc_now
from app.lab import completion_study
from app.lab.baseline_study import summarize
from app.lab.budgets import CampaignLedger, PROTECTED
from app.lab.configuration import frozen_configuration
from app.lab.coordinator import LabCoordinator
from app.lab.evaluation import PairedEvaluator, paired_complete
from app.lab.heldout_check import assess_heldout_v2, expand_cases, replica_layout
from app.lab.policy_status import development_status
from app.lab.readiness import execution_failure
from app.lab.reproduction import valid_trial
from app.lab.storage import LabStore
from app.telemetry.weave_reader import TraceRegistration, WeaveReader
import run_service_reliability as verified

require=verified.require
file_sha=verified.file_sha
write_json=verified.write_json
DEFAULT_OUTPUT=ROOT/'artifacts/prospective-repair-2026-09-27'
DEFAULT_WORLDS=ROOT/'artifacts/prospective-repair-worlds-2026-09-27/worlds'
MAX_ATTEMPTS=10
ACTOR_LIMIT=60*8*2
MECHANIC_LIMIT=2*2
STUDY_CALLS=ACTOR_LIMIT+MECHANIC_LIMIT
EVALUATION_EPISODES=156
EVALUATION_CALLS=EVALUATION_EPISODES*8*2
CAPS=CampaignBudget(model_calls=EVALUATION_CALLS,tokens=EVALUATION_CALLS*34000,dollars=60.0)
ACTOR_BOUND=Decimal('.0209')
MECHANIC_BOUND=Decimal('.04984')
STUDY_BOUND=ACTOR_LIMIT*ACTOR_BOUND+MECHANIC_LIMIT*MECHANIC_BOUND
GENERATION_POOL=Decimal('100')
EVALUATION_POOL=Decimal('60')
SHARED_REMAINING=Decimal('181.77')


def can_start_attempt(charged, attempts):
    amount=Decimal(str(charged))
    return amount.is_finite() and amount>=0 and attempts<MAX_ATTEMPTS and amount+STUDY_BOUND<=GENERATION_POOL


def require_prior_commitment(commitment,started_at):
    committed=datetime.fromisoformat(commitment['committed_at'].replace('Z','+00:00'))
    started=datetime.fromisoformat(started_at.replace('Z','+00:00'))
    require(committed.tzinfo is not None and started.tzinfo is not None and committed<started,
        'Reserved partition must be committed strictly before any generation')


def settings_for_run(base, directory):
    return replace(base,faultlab_artifact_dir=str(Path(directory).resolve()),
        faultlab_dollar_cap=CAPS.dollars,faultlab_model_call_cap=CAPS.model_calls,
        faultlab_token_cap=CAPS.tokens,faultlab_aria_publish_enabled=False)


def check_settings(settings):
    verified.check_settings(settings)
    require(settings.faultlab_aria_publish_enabled is False,'Aria must remain disabled for this experiment')
    require(settings.model_call_dollar_bounds['actor']==float(ACTOR_BOUND)
        and settings.model_call_dollar_bounds['mechanic']==float(MECHANIC_BOUND),'Verified role price bounds differ')
    require(STUDY_CALLS*MECHANIC_BOUND<=Decimal(str(CAPS.dollars)),
        'Ordinary mixed-role reservation cannot fit the common campaign cap')
    require(EVALUATION_CALLS*ACTOR_BOUND<=EVALUATION_POOL
        and GENERATION_POOL+EVALUATION_POOL<=SHARED_REMAINING,'Complete phase exceeds the carried allowance')
    require(completion_study.PROPOSAL_SLOTS==2 and len(completion_study.planned_slots(
        completion_study.build_case_manifest('upgrade-v1')))==60,'Reviewed completion path changed')


def policy_inventory(root):
    """Only policy records, never historical private scenarios or evidence, enter this inventory."""
    sources=[]; hashes=set()
    for path in sorted(Path(root).rglob('*')):
        if not path.is_file() or path.suffix not in ('.sqlite3','.db') or path.name.startswith('world-'):
            continue
        if 'worlds' in path.parts or 'control-verification' in path.parts or DEFAULT_OUTPUT in path.parents:
            continue
        db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
        try:
            mode='ro'
            try: table=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='records'").fetchone()
            except sqlite3.OperationalError:
                db.close()
                require(path.name in ('before.sqlite3','after.sqlite3') and '2026-09-20' in str(path)
                    and not any(Path(str(path)+suffix).exists() for suffix in ('-wal','-journal')),
                    'Historical store cannot be safely read without its journal')
                db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
                mode='immutable_closed_snapshot'
                table=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='records'").fetchone()
            if not table:
                sources.append({'path':str(path.resolve()),'disposition':'no_records_table'}); continue
            rows=[json.loads(row[0]) for row in db.execute("SELECT payload FROM records WHERE kind='policies' ORDER BY id")]
            for policy in rows:
                if policy.get('policy_hash') is not None:
                    require(policy.get('content') is not None and content_hash(policy['content'])==policy['policy_hash'],
                        'Historical policy content does not match its recorded hash')
                    hashes.add(policy['policy_hash'])
            sources.append({'path':str(path.resolve()),'policy_records':len(rows),'record_hash':content_hash(rows),'reader':mode})
        finally: db.close()
    require(sources and hashes,'Historical policy inventory is empty')
    return {'schema_version':'faultlab-policy-inventory/v1','policy_hashes':sorted(hashes),'sources':sources,
        'exclusions':'world-*.sqlite3, worlds directories, synthetic control-verification subtree, and this new output'}


def new_study_record(campaign,baseline,manifest):
    """Same completion execution contract, with the truthful full request reservation."""
    study_id=new_id('completion-study')
    return {'schema_version':completion_study.SCHEMA,'study_id':study_id,'campaign_id':campaign.campaign_id,
        'status':'QUEUED','stage':'controls','decision':'PENDING',
        'reason':'Full 964-request conditional study admitted; no calls started',
        'experiment_kind':'prospective_repair_generation','ordinary_policy_accepted':False,
        'configuration_hash':campaign.configuration_hash,'incumbent_hash':baseline.policy_hash,'model':campaign.model,
        'manifest':manifest,'manifest_hash':content_hash(manifest),'case_manifest_id':'upgrade-v1',
        'evidence_protocol':completion_study.COMPACT_EVIDENCE_V2,'actor_context_protocol':ACTOR_CONTEXT_PROTOCOL_V4,
        'replay_of':None,'replay_policy_hash':None,'reserved_model_calls':STUDY_CALLS,
        'slots':completion_study.planned_slots(manifest),'trial_rows':[],'candidates':[],
        'evidence':{},'telemetry':{},'validation_assessment':None,'charged_model_calls':0,
        'usage':summarize([])['usage'],'created_at':utc_now().isoformat()}


async def admit_study(coordinator,campaign,ledger,plan):
    coordinator.settings.require_live()
    require(campaign.mode=='baseline' and campaign.config_profile_id=='live-v1' and campaign.state=='IDLE',
        'Generation requires a fresh idle live baseline campaign')
    coordinator.validate_core_configuration(campaign)
    require(campaign.configuration_hash==plan['configuration_hash'],'Generation configuration differs')
    require(coordinator.active_id is None and not coordinator.store.list_records('completion_studies'),
        'Generation store was already used')
    baseline=coordinator.policies.baseline()
    require(campaign.active_policy_version==baseline.version=='policy-v0' and not baseline.content.rules,
        'Generation baseline changed')
    await coordinator.require_simulator()
    record=new_study_record(campaign,baseline,completion_study.build_case_manifest('upgrade-v1'))
    reservation='completion:'+record['study_id']
    ledger.reserve(reservation,STUDY_CALLS)
    campaign.execution_epoch+=1;campaign.state='RUNNING';campaign.state_seq+=1
    coordinator.save(campaign);coordinator.active_id=campaign.campaign_id
    coordinator.store.put_record('completion_plans',record['study_id'],deepcopy(record),immutable=True)
    coordinator.store.put_record('completion_studies',record['study_id'],record)
    return record,reservation


def assert_mechanic_context(messages,store,study_id):
    """Only this study's public controls/source trials may enter a proposal request."""
    context=json.loads(messages[1]['content'])
    study=store.get_record('completion_studies',study_id)
    manifest=completion_study.build_case_manifest('upgrade-v1')
    cases={c['case_id']:c for c in manifest['cases']}
    require(context.get('study_id')==study_id and context.get('objective')==completion_study.SCHEMA
        and context.get('source_fault_spec')==cases['upgrade-3']['fault_spec']
        and context.get('control_fault_spec')==cases['healthy']['fault_spec'],'Mechanic input scope differs')
    allowed={r['trial']['episode_id'] for r in study['trial_rows'] if r['stage'] in ('controls','candidate-1','candidate-2')}
    ids=[row['episode_id'] for row in context['development_evidence']['episodes']]
    require(ids and len(ids)==len(set(ids)) and set(ids)<=allowed,'Non-source evidence reached the Mechanic')
    for ident in ids:
        episode=store.get_record('episodes',ident)
        require(episode and episode['split']=='development' and episode['study_id']==study_id
            and episode['evidence_context_id']==study_id,'Mechanic evidence crossed an experiment boundary')


class ScopedProvider:
    def __init__(self,provider,limits,guard,save,*,context_check=None):
        self.provider=provider;self.limits=limits;self.calls=Counter();self.guard=guard;self.save=save
        self.context_check=context_check
    def role_model(self,role): return self.provider.role_model(role)
    async def complete(self,messages,*,role='actor',**kwargs):
        self.guard()
        require(role in self.limits and self.calls[role]<self.limits[role],'Provider role or request quota exceeded')
        if role=='mechanic':
            require(self.context_check is not None,'Mechanic context verification is unavailable')
            self.context_check(messages)
        self.calls[role]+=1;self.save()
        return await self.provider.complete(messages,role=role,**kwargs)
    async def close(self): await self.provider.close()


class ReservedTrace:
    """Existing frozen final-audit capture route, with explicit new-experiment metadata."""
    def __init__(self,trace):
        self.trace=trace;self.trace.frozen=True
    def __getattr__(self,name): return getattr(self.trace,name)
    def span(self,name,metadata,inputs,**kwargs):
        require(metadata.get('split')=='final_audit' and metadata.get('experiment_purpose')=='final_audit',
            'Reserved trace cannot capture another execution purpose')
        return self.trace.span(name,{**metadata,'experiment_kind':'prospective_reserved_evaluation',
            'original_workflow_final_audit':False,'ordinary_policy_accepted':False},inputs,**kwargs)


async def reserved_readback(store,runner,trial,campaign,*,stopped=lambda:False):
    """Read exact frozen evaluation IDs; never create optimizer evidence or relax its gateway."""
    calls=runner.trace.episode_calls(trial.episode_id)
    roots=[c for c in calls if c['name']=='run_episode']
    require(len(roots)==1,'Reserved root trace is missing')
    root=roots[0]; metadata=root['metadata']
    configuration=store.get_record('configurations',campaign.configuration_hash)
    require(configuration is not None,'Reserved frozen configuration is missing')
    expected={'campaign_id':campaign.campaign_id,'episode_id':trial.episode_id,
        'study_id':campaign.campaign_id,'evidence_context_id':campaign.campaign_id,
        'split':'final_audit','experiment_purpose':'final_audit','source_mode':'live',
        'policy_hash':trial.policy_hash,'arm':trial.arm,'execution_epoch':campaign.execution_epoch,
        'trial_index':trial.trial_index,'model_id':campaign.model,'origin':'faultlab_evaluation',
        'contract_hash':configuration['contract_hash'],'scorer_hash':configuration['scorer_hash'],
        'experiment_kind':'prospective_reserved_evaluation','original_workflow_final_audit':False,
        'ordinary_policy_accepted':False}
    require(all(metadata.get(k)==v for k,v in expected.items()),'Reserved trace scope differs')
    children=[c for c in calls if c.get('parent_id')==root['call_id']]
    require(len(calls)==1+len(children),'Reserved trace includes an unexpected nested call')
    registration=TraceRegistration(verified.PROJECT,metadata,root['call_id'],tuple(c['call_id'] for c in children))
    ids=[registration.root_call_id,*registration.child_call_ids]
    require(len(ids)<=19 and len(ids)==len(set(ids)),'Reserved trace identities are duplicated or over limit')
    # The normal reader's read() intentionally rejects private splits. Reuse only its
    # strict identity/hierarchy normalization after our narrower frozen-ID scope check.
    reader=WeaveReader(runner.telemetry_worker,verified.PROJECT,lambda value:False)
    async with asyncio.timeout(60):
        await runner.telemetry_worker.request('flush',{},timeout_seconds=20)
        while True:
            require(not stopped(),'External stop during reserved evidence readback')
            remote=await runner.telemetry_worker.request('get_calls',{'call_ids':ids},timeout_seconds=20)
            snapshot=reader._normalize(registration,remote)
            if snapshot is not None: break
            await asyncio.sleep(2)
    episode=store.get_record('episodes',trial.episode_id)
    observations=[row for row in store.list_records('observations') if row['episode_id']==trial.episode_id]
    require(episode['configuration_hash']==campaign.configuration_hash and episode['world_id']==trial.world_id
        and episode['policy_hash']==trial.policy_hash and episode['split']=='final_audit'
        and snapshot['calls'][0]['output']['report']==episode['report']
        and snapshot['calls'][0]['output']['terminal_status']==episode['lifecycle']
        and [call['output']['observation'] for call in snapshot['calls'][1:]]==observations,
        'Reserved remote observations or report differ from local execution')
    store.put_record('evaluation_readbacks',trial.episode_id,snapshot,immutable=True)
    return {'source':'weave_verified','root_call_id':registration.root_call_id,'digest':snapshot['digest']}


def helper_hashes():
    names=('run_service_reliability.py','run_full_loop.py','slot2_probe.py','check_clock_drift.py',
           'gate_freeze.py','reserved_partition.py')
    return {name:file_sha(Path(__file__).with_name(name)) for name in names}


def load_partition_inputs(args):
    import reserved_partition as partition
    manifest=json.loads(args.partition_file.read_text())
    inventory=json.loads(args.exposure_inventory_file.read_text())
    commitment=json.loads(args.commitment_file.read_text())
    verify_seed_commitment(args,manifest,inventory,commitment)
    partition.validate_partition(manifest,inventory)
    expected=partition.partition_commitment(manifest,inventory,committed_at=commitment['committed_at'])
    require(commitment==expected,'Reserved partition commitment does not match its sealed inputs')
    return manifest,inventory,commitment


def verify_seed_commitment(args,manifest,inventory,commitment):
    import reserved_partition as partition
    seed=json.loads(args.seed_declaration_file.read_text())
    seal=json.loads(args.algorithm_commitment_file.read_text())
    body={key:value for key,value in seal.items() if key!='commitment_hash'}
    expected={'schema_version':'faultlab-reserved-seed-algorithm-commitment/v1','algorithm':partition.ALGORITHM,
        'helper_sha256':file_sha(Path(partition.__file__)),
        'seed_declaration_sha256':file_sha(args.seed_declaration_file),'seed_declaration_hash':partition.digest(seed),
        'seed_hash':sha256(partition.SEED.encode()).hexdigest(),'inventory_hash':inventory['inventory_hash'],
        'inventory_file_sha256':file_sha(args.exposure_inventory_file),
        'before_selection':True,'before_provider_generation':True,'no_resampling':True}
    require(seal.get('commitment_hash')==partition.digest(body) and all(seal.get(k)==v for k,v in expected.items()),
        'Seed, algorithm, or exposure inventory differs from the pre-selection seal')
    require(seed.get('seed')==partition.SEED and seed.get('guards')==partition.GUARDS
        and manifest.get('seed_declaration_hash')==partition.digest(seed),'Declared selection seed differs')
    require_prior_commitment(seal,commitment['committed_at'])


def prepare(args,*,base=None):
    require(args.output.resolve()==DEFAULT_OUTPUT.resolve() and not args.output.exists(),
        'Use the single new output directory; no overwrite or resume is allowed')
    require(args.worlds_dir.resolve()==DEFAULT_WORLDS.resolve(),'Use the separately declared fresh simulator worlds directory')
    require(not args.worlds_dir.exists() or not list(args.worlds_dir.glob('world-*.sqlite3')),
        'Reserved experiment worlds directory was already used')
    settings=settings_for_run(base or Settings.from_env('/dev/null'),args.output)
    check_settings(settings)
    manifest,exposure,commitment=load_partition_inputs(args)
    inventory=policy_inventory(ROOT/'artifacts')
    configuration=frozen_configuration(settings,CAPS,'live-v1')
    layout=replica_layout(manifest['cases'])
    require(len(manifest['cases'])==6 and len(layout)==26,'Reserved evaluation does not contain the declared 78 pairs')
    from run_full_loop import gate_freeze
    inputs={'partition':args.partition_file,'exposure_inventory':args.exposure_inventory_file,'commitment':args.commitment_file,
        'seed_declaration':args.seed_declaration_file,'algorithm_commitment':args.algorithm_commitment_file}
    plan={'schema_version':'faultlab-prospective-repair-plan/v1','configuration':configuration,
        'configuration_hash':content_hash(configuration),'runtime_hash':configuration['runtime_hash'],
        'gate_freeze':gate_freeze(),'harness_sha256':file_sha(__file__),'helper_sha256':helper_hashes(),
        'protocol_sha256':file_sha(args.protocol),'inputs':{key:{'path':str(path.resolve()),'sha256':file_sha(path)} for key,path in inputs.items()},
        'partition_commitment':commitment,'policy_inventory':inventory,'policy_inventory_hash':content_hash(inventory),
        'output_directory':str(args.output.resolve()),'worlds_directory':str(args.worlds_dir.resolve()),
        'project':verified.PROJECT,'task_text':'Upgrade the order to express shipping, then send one confirmation.',
        'order_id':'order-prospective-repair','public_manifest':completion_study.build_case_manifest('upgrade-v1'),
        'generation_pool_dollars':100,'evaluation_pool_dollars':60,'shared_remaining_before':181.77,
        'max_attempts':MAX_ATTEMPTS,'generation_episode_bound':60,'generation_actor_call_bound':ACTOR_LIMIT,
        'generation_mechanic_call_bound':MECHANIC_LIMIT,'generation_request_reservation':STUDY_CALLS,
        'generation_actual_full_path_dollar_bound':float(STUDY_BOUND),
        'generation_generic_reservation_dollars':float(STUDY_CALLS*MECHANIC_BOUND),
        'reserved_episodes':EVALUATION_EPISODES,'reserved_pairs':78,'reserved_actor_calls':EVALUATION_CALLS,
        'reserved_full_path_dollar_bound':float(EVALUATION_CALLS*ACTOR_BOUND),
        'allow_lab_retry':False,'routing':'first historically new exact hash meeting unchanged strong development qualification',
        'reserved_telemetry_purpose':'final_audit','original_workflow_final_audit':False,
        'ordinary_policy_accepted':False,'active_policy':'policy-v0'}
    return settings,plan,manifest,commitment


class RuntimeGuard:
    def __init__(self,args,plan,process,stopped):
        self.args,self.plan,self.process,self.stopped=args,plan,process,stopped
        self.selected_artifacts={}
    def __call__(self,*,full=False):
        require(not self.stopped(),'External stop requested')
        require(file_sha(__file__)==self.plan['harness_sha256'] and helper_hashes()==self.plan['helper_sha256']
            and file_sha(self.args.protocol)==self.plan['protocol_sha256'],'Reviewed harness, helper, or protocol changed')
        require(all(file_sha(row['path'])==row['sha256'] for row in self.plan['inputs'].values()),
            'Reserved partition commitment changed')
        require(all(file_sha(path)==digest for path,digest in self.selected_artifacts.items()),
            'Selected policy binding changed after freeze')
        if full:
            from run_full_loop import check_backend_process,gate_freeze
            from slot2_probe import live_experiment_processes
            require(check_backend_process(8001)==self.process,'Simulator process changed')
            require(not live_experiment_processes(),'Another paid experiment is running')
            require(gate_freeze()==self.plan['gate_freeze'],'Application source or fixed gates changed')


def ledger_charge(ledger):
    # Prices have five decimal places; remove binary accumulation noise only.
    return round(ledger.used_dollar_upper_bound or 0,8)


def choose_candidate(store,study,plan):
    require(study['configuration_hash']==plan['configuration_hash'],'Source study configuration differs')
    qualification=development_status(store,study)
    if qualification['status']!='QUALIFIED': return None,qualification
    policy=store.get_model('policies',study['selected_candidate_version'],PolicyVersion)
    require(policy and policy.policy_hash==study['selected_candidate_hash'] and policy.decision=='PROPOSED',
        'Qualified policy identity or stored decision differs')
    for row in study['trial_rows']:
        trial=row['trial'];episode=store.get_record('episodes',trial['episode_id'])
        evidence=store.get_record('evidence',trial['episode_id'])
        require(store.get_record('trials',trial['episode_id'])==trial and episode
            and episode['configuration_hash']==plan['configuration_hash'] and episode['study_id']==study['study_id']
            and all(episode[key]==trial[key] for key in ('world_id','policy_hash','scenario_hash'))
            and evidence and evidence['source']=='weave_verified' and evidence['source_project']==verified.PROJECT,
            'Qualified study is not bound to its actual current-runtime evidence')
    if policy.policy_hash in plan['policy_inventory']['policy_hashes']:
        return None,{**qualification,'routing':'HISTORICAL_REDISCOVERY'}
    return policy,{**qualification,'routing':'FIRST_FRESH_QUALIFIED'}


class CheckedRunner:
    def __init__(self,raw,coordinator,outer,record,guard,worlds_dir,save,*,evaluation=False):
        self.raw,self.coordinator,self.outer,self.record=raw,coordinator,outer,record
        self.guard,self.worlds_dir,self.save,self.evaluation=guard,worlds_dir,save,evaluation
    def __getattr__(self,name): return getattr(self.raw,name)
    async def run(self,campaign,recipe,policy,**kwargs):
        self.guard(full=True)
        require(campaign.configuration_hash==self.outer['configuration_hash'],'Episode configuration differs from source')
        require(content_hash(policy.content)==policy.policy_hash,'Executing policy content no longer matches its frozen hash')
        if self.evaluation:
            require(kwargs['purpose']=='final_audit' and self.outer.get('selected_policy_hash')
                and policy.policy_hash in (self.outer['selected_policy_hash'],self.coordinator.policies.baseline().policy_hash),
                'Reserved episode policy or purpose differs')
        else:
            require(not self.outer.get('evaluation_started_at') and kwargs['purpose']=='completion_study',
                'Generation cannot run after reserved evaluation begins')
        ident=kwargs['episode_id']
        attempt={'episode_id':ident,'scenario_hash':content_hash(recipe),'policy_hash':policy.policy_hash,
            'arm':kwargs['arm'],'trial_index':kwargs['trial_index'],'purpose':kwargs['purpose']}
        self.record.setdefault('attempted_slots',[]).append(attempt);self.save()
        trial=await self.raw.run(campaign,recipe,policy,**kwargs)
        self.record.setdefault('trials',[]).append(trial.model_dump(mode='json'));self.save()
        require(trial.episode_id==ident and all(getattr(trial,key)==attempt[key]
            for key in ('scenario_hash','policy_hash','arm','trial_index')),'Trial departed from its admitted identity')
        require(trial.world_id not in self.outer['_world_ids'],'World reused across experiment trials')
        self.outer['_world_ids'].add(trial.world_id)
        if trial.lifecycle=='COMPLETED' and trial.outcome!='LAB_ERROR':
            self.record.setdefault('integrity',{})[ident]=verified.check_world(self.coordinator.store,trial,self.worlds_dir)
            if self.evaluation:
                self.record.setdefault('readbacks',{})[ident]=await reserved_readback(
                    self.coordinator.store,self.raw,trial,campaign,stopped=self.guard.stopped)
        else:
            require(not self.evaluation,'Reserved trial failed to execute; no pair or episode retry')
        self.save()
        return trial


class CheckedCoordinator(LabCoordinator):
    def configure_checks(self,outer,record,guard,worlds_dir,save,*,study_id=None,evaluation=False):
        self.check_options=(outer,record,guard,worlds_dir,save,study_id,evaluation)
    async def _get_runner(self,live):
        raw,owned=await super()._get_runner(live)
        outer,record,guard,worlds_dir,save,study_id,evaluation=self.check_options
        if evaluation:
            require(outer.get('candidate_binding') and outer.get('evaluation_started_at'),'Policy was not frozen before reserved execution')
            raw.trace=ReservedTrace(raw.trace)
        def provider_guard():
            guard()
            require(evaluation or not outer.get('evaluation_started_at'),'Generation after reserved evaluation is forbidden')
        raw.provider=ScopedProvider(raw.provider,{'actor':EVALUATION_CALLS} if evaluation else
            {'actor':ACTOR_LIMIT,'mechanic':MECHANIC_LIMIT},provider_guard,save,
            context_check=None if evaluation else lambda messages:assert_mechanic_context(messages,self.store,study_id))
        record['_provider']=raw.provider
        return CheckedRunner(raw,self,outer,record,guard,worlds_dir,save,evaluation=evaluation),owned


async def close_runner(runner):
    if runner is None: return
    for item in (runner.world_client,runner.provider,getattr(runner,'telemetry_worker',None)):
        if item:
            try: await asyncio.wait_for(item.close(),timeout=5)
            except Exception: pass


def serializable_record(value):
    if isinstance(value,dict): return {key:serializable_record(item) for key,item in value.items() if not key.startswith('_')}
    if isinstance(value,list): return [serializable_record(item) for item in value]
    return value


def summarize_record(record):
    for stage in [*record['attempts'],*([record['evaluation']] if record.get('evaluation') else [])]:
        ledger=stage.get('_ledger');provider=stage.get('_provider')
        if ledger:
            stage['accounting']={'charged_model_calls':ledger.used_calls,'charged_dollar_upper_bound':ledger_charge(ledger),
                'charged_token_upper_bound':ledger.used_tokens}
        if provider: stage['provider_requests_by_role']=dict(provider.calls)
        stage['outcomes']={arm:dict(Counter(trial['outcome'] for trial in stage.get('trials',[]) if trial['arm']==arm)) for arm in ('B0','L')}
        stage['failed_checks']=[trial for trial in stage.get('trials',[]) if trial['failed_checks']]
    generation=sum(Decimal(str(a.get('accounting',{}).get('charged_dollar_upper_bound',0))) for a in record['attempts'])
    evaluation=Decimal(str((record.get('evaluation') or {}).get('accounting',{}).get('charged_dollar_upper_bound',0)))
    record['accounting']={'generation_charged_upper_bound':float(generation),
        'evaluation_charged_upper_bound':float(evaluation),'total_charged_upper_bound':float(generation+evaluation),
        'shared_remaining_upper_bound':float(SHARED_REMAINING-generation-evaluation)}


def new_campaign(settings,directory,plan,*,evaluation=False):
    directory.mkdir(exist_ok=False)
    current=settings_for_run(settings,directory)
    coordinator=CheckedCoordinator(current)
    campaign=coordinator.create(CampaignRequest(task_text=plan['task_text'],order_id=plan['order_id'],
        mode='baseline',config_profile_id='live-v1'))
    require(campaign.configuration_hash==plan['configuration_hash'],'Fresh campaign configuration differs from sealed source')
    ledger=CampaignLedger(coordinator.store,campaign.campaign_id,CAPS,
        dollar_bounds={'actor':float(ACTOR_BOUND)} if evaluation else current.model_call_dollar_bounds)
    for name in PROTECTED: ledger.release(name)
    coordinator.ledgers[campaign.campaign_id]=ledger
    coordinator.store.put_record('prospective_provenance',campaign.campaign_id,{
        'plan_hash':content_hash(plan),'configuration_hash':plan['configuration_hash'],
        'partition_commitment':plan['partition_commitment'],'policy_inventory_hash':plan['policy_inventory_hash'],
        'experiment_kind':'prospective_reserved_evaluation' if evaluation else 'prospective_repair_generation',
        'original_workflow_final_audit':False,'ordinary_policy_accepted':False,
        'ledger_scope':'actor_only_reserved_evaluation' if evaluation else 'actor_and_mechanic_public_generation',
        'released_unrelated_reserves':list(PROTECTED)},immutable=True)
    return coordinator,campaign,ledger


def verify_stage_store(coordinator,record,worlds_dir):
    import check_clock_drift
    store=coordinator.store
    trials=store.list_records('trials')
    require(len(trials)==len(record.get('trials',[])),'A stored trial was omitted from the experiment record')
    if trials:
        drift=check_clock_drift.scan(str(store.path),worlds=True,worlds_dir=str(worlds_dir))
        record['clock_check']=drift
        require(drift['scored']==len(trials) and check_clock_drift.exit_status(drift,require_worlds=True)==0,
            'Exact world, clock, or fault verification did not pass')
    campaigns=store.list_records('campaigns')
    require(all(c['active_policy_version']=='policy-v0' for c in campaigns),'Active baseline changed')
    require(not [p for p in store.list_records('policies') if p.get('decision')=='ACCEPTED'],
        'Original policy acceptance was unexpectedly written')
    record['baseline_active']=True


async def run_attempt(args,settings,plan,outer,guard,save,number):
    guard(full=True)
    require(policy_inventory(ROOT/'artifacts')==plan['policy_inventory'],'Historical policy inventory changed')
    directory=args.output/f'attempt-{number:02d}'
    row={'attempt':number,'store':str(directory/'lab.sqlite3'),'status':'PREPARING','trials':[],'attempted_slots':[]}
    outer['attempts'].append(row);save()
    coordinator=None
    try:
        coordinator,campaign,ledger=new_campaign(settings,directory,plan)
        row.update(campaign_id=campaign.campaign_id,_ledger=ledger);save()
        study,reservation=await admit_study(coordinator,campaign,ledger,plan)
        row.update(study_id=study['study_id'],status='RUNNING');save()
        coordinator.configure_checks(outer,row,guard,args.worlds_dir,save,study_id=study['study_id'])
        await completion_study._execute(coordinator,campaign,coordinator.policies.baseline(),study,ledger,reservation)
        study=coordinator.store.get_record('completion_studies',study['study_id'])
        row.update(status=study['status'],decision=study['decision'],reason=study['reason'],
            study_record_hash=content_hash(study),planned_slots=study['slots'])
        require(study['status'] in ('COMPLETED','INCOMPLETE') and not study.get('error_type'),
            'Development execution encountered an infrastructure or evidence failure')
        old=set(plan['policy_inventory']['policy_hashes'])
        earlier={p['policy_hash'] for item in outer['attempts'][:-1] for p in item.get('generated_policies',[])}
        row['generated_policies']=[{'policy_hash':p['policy_hash'],'policy_version':p['policy_version'],
            'historical_rediscovery':p['policy_hash'] in old,'within_run_redraw':p['policy_hash'] in earlier,
            'decision':p['decision']} for p in study['candidates'] if p.get('policy_hash')]
        policy,qualification=choose_candidate(coordinator.store,study,plan)
        row['qualification']=qualification;save()
        return policy,study
    finally:
        if coordinator:
            try: verify_stage_store(coordinator,row,args.worlds_dir)
            finally: coordinator.store.close();save()


def retain_candidate_failures(store,record,policy_hash):
    from app.lab.heldout_check import harmful
    failed=[]
    for trial in store.list_records('trials'):
        if trial['arm']=='L' and trial['policy_hash']==policy_hash:
            episode=store.get_record('episodes',trial['episode_id']) or {}
            if harmful(trial,report_present=episode.get('report') is not None): failed.append(trial['episode_id'])
    record['candidate_rule_failures']=sorted(failed)
    if failed: record['observed_safety_decision']='HARM'


async def run_reserved(args,settings,plan,manifest,policy,outer,guard,save):
    row={'status':'PREPARING','trials':[],'attempted_slots':[],'readbacks':{},
        'experiment_kind':'prospective_reserved_evaluation','ordinary_policy_accepted':False,
        'original_workflow_final_audit':False,'split':'final_audit','policy_hash':policy.policy_hash,
        'configuration_hash':plan['configuration_hash']}
    outer['evaluation']=row;outer['evaluation_started_at']=utc_now().isoformat();save()
    coordinator=runner=ledger=None
    try:
        guard(full=True)
        coordinator,campaign,ledger=new_campaign(settings,args.output/'reserved-evaluation',plan,evaluation=True)
        row.update(campaign_id=campaign.campaign_id,_ledger=ledger);save()
        await coordinator.require_simulator()
        coordinator.store.put_record('policies',policy.version,policy,immutable=True)
        coordinator.store.put_record('reserved_candidate_binding',policy.version,outer['candidate_binding'],immutable=True)
        campaign.state='RUNNING';campaign.execution_epoch=1;coordinator.save(campaign);coordinator.active_id=campaign.campaign_id
        reservation='prospective-reserved-evaluation';ledger.reserve(reservation,EVALUATION_CALLS)
        coordinator.configure_checks(outer,row,guard,args.worlds_dir,save,evaluation=True)
        runner,_=await coordinator._get_runner(True)
        layout=replica_layout(manifest['cases']); expanded=expand_cases(manifest['cases'],layout)
        row['status']='RUNNING';row['layout']=layout;save()
        # No auto reservation and no whole-pair retry: every actual Actor retry is
        # already counted by the explicit2496-call maximum.
        batch=await PairedEvaluator(coordinator.store,runner,ledger,publisher=coordinator.evaluation_publisher).run(
            campaign,expanded,coordinator.policies.baseline(),policy,purpose='final_audit',
            reservation=reservation,allow_lab_retry=False,stop=guard.stopped,
            actor_context_protocol=ACTOR_CONTEXT_PROTOCOL_V4)
        row['batch_id']=batch.batch_id
        reported={t.episode_id for t in batch.trials if (coordinator.store.get_record('episodes',t.episode_id) or {}).get('report') is not None}
        assessment=assess_heldout_v2(batch,manifest['cases'],reported,layout)
        row['assessment']=assessment;row['observed_safety_decision']=assessment['decision']
        complete=(len(batch.trials)==EVALUATION_EPISODES and paired_complete(batch,78)
            and len(row['readbacks'])==EVALUATION_EPISODES)
        row['status']='COMPLETED' if complete else 'INCOMPLETE'
        row['measurement_complete']=complete;save()
    finally:
        if ledger: ledger.release('prospective-reserved-evaluation')
        if coordinator:
            try:
                retain_candidate_failures(coordinator.store,row,policy.policy_hash)
                row['evaluation_batches']=coordinator.store.list_records('evaluations')
                if row['status']!='COMPLETED': row['status']='INCOMPLETE';row['measurement_complete']=False
                campaign=coordinator.get(row['campaign_id'])
                campaign.state='COMPLETED' if row['status']=='COMPLETED' else 'ERROR';coordinator.save(campaign)
                verify_stage_store(coordinator,row,args.worlds_dir)
            finally:
                await close_runner(runner);coordinator.store.close();save()
    return row


async def execute(args,settings,plan,manifest,commitment):
    import reserved_partition as partition
    from run_full_loop import check_backend_process
    from slot2_probe import live_experiment_processes
    require(not live_experiment_processes(),'Another paid experiment is running')
    socket_guard=socket.socket()
    try: socket_guard.bind(('127.0.0.1',8000))
    except OSError:
        socket_guard.close();raise verified.Refusal('Stop the backend before this isolated experiment') from None
    stopped=False;owned=False
    loop=asyncio.get_running_loop()
    def stop():
        nonlocal stopped
        stopped=True
    for sig in (signal.SIGINT,signal.SIGTERM): loop.add_signal_handler(sig,stop)
    outer={'schema_version':'faultlab-prospective-repair/v1','plan_hash':content_hash(plan),
        'configuration_hash':plan['configuration_hash'],'status':'PREPARING','attempts':[],
        'active_policy':'policy-v0','ordinary_policy_accepted':False,'_world_ids':set()}
    def save():
        summarize_record(outer)
        if owned: write_json(args.output/'result.json',serializable_record(outer))
    try:
        process=check_backend_process(8001)
        require(process['processes'] and all('--timeout-keep-alive 75' in p['command'] for p in process['processes']),
            'Simulator must use the reviewed75second keep-alive')
        guard=RuntimeGuard(args,plan,process,lambda:stopped);guard(full=True)
        settings.require_live()
        require(settings.faultlab_confirmed_entity==verified.PROJECT.split('/')[0],'Confirmed entity differs')
        started=utc_now().isoformat()
        require_prior_commitment(commitment,started)
        args.output.mkdir(exist_ok=False);owned=True
        write_json(args.output/'plan.json',plan,exclusive=True)
        outer.update(status='GENERATING',generation_started_at=started,simulator_process=process);save()
        selected=None
        for number in range(1,MAX_ATTEMPTS+1):
            save()
            if not can_start_attempt(outer['accounting']['generation_charged_upper_bound'],number-1):
                outer['stop_reason']='Next complete generation path cannot fit the remaining generation pool';break
            selected,study=await run_attempt(args,settings,plan,outer,guard,save,number)
            if selected:
                outer['selected_policy_hash']=selected.policy_hash
                outer['candidate_binding']=partition.bind_candidate(commitment,manifest,
                    policy_hash=selected.policy_hash,policy_version=selected.version,study_id=study['study_id'],
                    generation_started_at=outer['generation_started_at'],prior_policy_hashes=plan['policy_inventory']['policy_hashes'])
                outer['candidate_binding'].update(configuration_hash=plan['configuration_hash'],
                    runtime_hash=plan['runtime_hash'],source_study_hash=content_hash(study))
                write_json(args.output/'selected-policy.json',{'binding':outer['candidate_binding'],
                    'policy':selected.model_dump(mode='json')},exclusive=True)
                outer['selected_artifact_sha256']=file_sha(args.output/'selected-policy.json')
                guard.selected_artifacts[str(args.output/'selected-policy.json')]=outer['selected_artifact_sha256']
                save();break
        if selected:
            outer['status']='EVALUATING';save()
            result=await run_reserved(args,settings,plan,manifest,selected,outer,guard,save)
            outer['status']=result['status'];outer['decision']=result.get('observed_safety_decision','INCOMPLETE')
        else:
            outer['status']='COMPLETED';outer['decision']='NO_NEW_QUALIFIED_POLICY'
    except BaseException as error:
        outer['status']='INTERRUPTED' if stopped or isinstance(error,asyncio.CancelledError) else 'INCOMPLETE'
        outer['failure']=execution_failure(error)
        outer['decision']=(outer.get('evaluation') or {}).get('observed_safety_decision','INCOMPLETE')
        if isinstance(error,verified.Refusal): outer['reason']=str(error)
    finally:
        if owned:
            try:
                guard(full=True)
                require(policy_inventory(ROOT/'artifacts')==plan['policy_inventory'],'Historical policy inventory changed')
                save()
                require(outer['accounting']['generation_charged_upper_bound']<=float(GENERATION_POOL)
                    and outer['accounting']['evaluation_charged_upper_bound']<=float(EVALUATION_POOL),
                    'Declared phase allocation exceeded')
                outer['final_integrity_verified']=True
            except Exception as error:
                outer['final_integrity_verified']=False;outer['status']='INCOMPLETE';outer['final_integrity_error']=execution_failure(error)
            outer['ended_at']=utc_now().isoformat();save()
        for sig in (signal.SIGINT,signal.SIGTERM): loop.remove_signal_handler(sig)
        socket_guard.close()
    return serializable_record(outer)


def arguments(argv=None):
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--partition-file',type=Path,required=True)
    parser.add_argument('--exposure-inventory-file',type=Path,required=True)
    parser.add_argument('--commitment-file',type=Path,required=True)
    parser.add_argument('--seed-declaration-file',type=Path,required=True)
    parser.add_argument('--algorithm-commitment-file',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--worlds-dir',type=Path,default=DEFAULT_WORLDS)
    parser.add_argument('--plan-file',type=Path)
    parser.add_argument('--seal-plan',action='store_true')
    parser.add_argument('--expect-plan-sha256')
    parser.add_argument('--expect-protocol-sha256')
    parser.add_argument('--execute-live',action='store_true')
    return parser.parse_args(argv)


def main(argv=None):
    args=arguments(argv)
    try:
        _,plan,manifest,commitment=prepare(args)
        if not args.execute_live:
            if args.seal_plan:
                require(args.plan_file is not None and args.output.resolve() not in args.plan_file.resolve().parents,
                    'Seal the plan outside the new experiment output')
                write_json(args.plan_file,plan,exclusive=True)
            print(json.dumps(plan,indent=2,sort_keys=True));return 0
        require(not args.seal_plan,'Seal and execute are separate actions')
        verified.validate_seal(args,plan)
        base=Settings.from_env()
        base=replace(base,faultlab_control_token=base.local_control_token())
        settings=settings_for_run(base,args.output);check_settings(settings);settings.require_live()
        require(frozen_configuration(settings,CAPS,'live-v1')==plan['configuration'],'Live configuration differs from sealed plan')
        record=asyncio.run(execute(args,settings,plan,manifest,commitment))
        print(json.dumps({key:record.get(key) for key in ('status','decision','accounting','reason')}))
        return 0 if record['status']=='COMPLETED' else 1
    except Exception as error:
        print(json.dumps({'status':'REFUSED','failure':execution_failure(error),
            'reason':str(error) if isinstance(error,verified.Refusal) else 'Configuration or frozen input validation failed'}))
        return 2


if __name__=='__main__': raise SystemExit(main())

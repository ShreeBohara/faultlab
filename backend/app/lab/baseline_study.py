"""Explicit frozen B0/B1 development comparison; no candidate or study retry."""
import asyncio
from app.contracts.models import FaultSpec,Provenance,canonical_json,content_hash,new_id,utc_now
from app.lab.budgets import CampaignLedger
from app.lab.evaluation import aggregate_usage
from app.lab.evidence import EvidenceContext
from app.lab.reproduction import valid_trial
from app.lab.storage import StoreConflict

ARMS=('B0','B1')
MODEL_CALL_RESERVATION=6*3*8


def summarize(trials):
    usage=aggregate_usage(trials).model_dump(mode='json')
    # The handwritten reference makes no model requests. A zero request count is
    # a known zero model charge; unavailable usage on actual calls stays unknown.
    costs=[t.usage.cost_dollars for t in trials if t.usage.model_calls]
    usage['cost_dollars']=sum(costs) if all(value is not None for value in costs) else None
    counts={name:0 for name in ('attempted','valid','completed','violations','safe_unresolved','correctly_rejected','lab_errors','interrupted','scheduled','triggered','untriggered')}
    for trial in trials:
        counts['attempted']+=1; counts['valid']+=int(valid_trial(trial))
        counts['scheduled']+=int(trial.fault_scheduled)
        counts['triggered']+=int(trial.fault_scheduled and trial.fault_triggered)
        counts['untriggered']+=int(trial.fault_scheduled and not trial.fault_triggered)
        if trial.lifecycle=='INTERRUPTED': key='interrupted'
        elif trial.lifecycle=='LAB_ERROR': key='lab_errors'
        else: key={'COMPLETED':'completed','VIOLATION':'violations','SAFE_UNRESOLVED':'safe_unresolved','CORRECTLY_REJECTED':'correctly_rejected','LAB_ERROR':'lab_errors'}.get(trial.outcome)
        if key: counts[key]+=1
    return {'counts':counts,'usage':usage}


async def queue_baseline_study(coordinator,campaign_id):
    """The API's explicit live request is required; this function only queues."""
    from app.referee.manifests import load_manifest
    coordinator.settings.require_live()
    manifest=load_manifest('development')
    if len(manifest['cases'])!=6 or manifest['trials_per_case']!=3:
        raise StoreConflict('Expected the frozen six-case, three-trial development manifest')
    async with coordinator.lock:
        campaign=coordinator.get(campaign_id)
        if campaign.mode!='baseline' or campaign.config_profile_id!='live-v1':
            raise ValueError('Baseline comparison requires a live baseline campaign')
        coordinator.validate_core_configuration(campaign)
        if campaign.state not in ('IDLE','COMPLETED'):
            raise StoreConflict('Baseline study requires an idle or completed campaign')
        if coordinator.active_id is not None: raise StoreConflict('Another fresh execution is active')
        if any(row['campaign_id']==campaign_id for row in coordinator.store.list_records('baseline_studies')):
            raise StoreConflict('This campaign already has a baseline study; saved attempts cannot be rerun')
        baseline=coordinator.policies.baseline()
        if baseline.version!='policy-v0' or baseline.content.rules or campaign.active_policy_version!='policy-v0':
            raise StoreConflict('Baseline comparison requires the unchanged empty baseline policy')
        study_id=new_id('baseline-study'); reservation='baseline:'+study_id
        ledger=coordinator.ledgers.get(campaign_id)
        if ledger is None:
            ledger=CampaignLedger(coordinator.store,campaign_id,campaign.caps,dollar_bounds=coordinator.settings.model_call_dollar_bounds)
            coordinator.ledgers[campaign_id]=ledger
        ledger.stopped=False
        ledger.reserve(reservation,MODEL_CALL_RESERVATION)
        campaign.stop_requested=False; campaign.execution_epoch+=1; campaign.state='RUNNING'; campaign.state_seq+=1
        coordinator.save(campaign); coordinator.active_id=campaign_id
        slots=[]
        for case_index,case in enumerate(manifest['cases']):
            for index in range(3):
                for arm in ARMS if (case_index+index)%2==0 else tuple(reversed(ARMS)):
                    slots.append({'case_id':case['case_id'],'scenario_hash':content_hash(case['fault_spec']),'fixture_id':case['fixture_id'],'trial_index':index,'arm':arm,'episode_id':new_id('episode'),'status':'NOT_ATTEMPTED'})
        record={'schema_version':'faultlab-baseline-study/v1','study_id':study_id,'campaign_id':campaign_id,'status':'QUEUED','manifest_hash':manifest['manifest_hash'],'configuration_hash':campaign.configuration_hash,'policy_hash':baseline.policy_hash,'policy_version':baseline.version,'model':campaign.model,'source_mode_by_arm':{'B0':'live','B1':'offline_fixture'},'evidence_context_id':study_id,'planned_trials':36,'reserved_model_calls':MODEL_CALL_RESERVATION,'trial_ids':[],'trials':[],'slots':slots,'by_arm':{},'usage':summarize([])['usage'],'evidence':{},'telemetry':{},'reason':'Full fixed batch admitted; no execution yet','created_at':utc_now().isoformat()}
        coordinator.store.put_record('baseline_studies',study_id,record)
        coordinator.tasks[study_id]=asyncio.create_task(_execute(coordinator,campaign,baseline,manifest,record,ledger,reservation))
        return record


async def _execute(coordinator,campaign,baseline,manifest,record,ledger,reservation):
    runner=None; owned=False; trials=[]; sessions={}; study_id=record['study_id']; id=campaign.campaign_id
    start_calls,start_tokens=ledger.used_calls,ledger.used_tokens
    stop=lambda:coordinator.get(id).stop_requested
    def save(): coordinator.store.put_record('baseline_studies',study_id,record)
    try:
        if stop(): raise InterruptedError()
        runner,owned=await coordinator._get_runner(True)
        publisher=getattr(coordinator,'evaluation_publisher',None)
        config=coordinator.store.get_record('configurations',campaign.configuration_hash)
        registration=coordinator.store.get_record('campaign_registrations',id)['registration_id']
        if publisher:
            # The live model's scores publish remotely; reference scores are a
            # separate explicitly offline evaluation. Both inventories precede
            # every actor call and every prediction comes from persisted C1-C8.
            for arm in ARMS:
                batch_id=study_id+'-'+arm
                provenance=Provenance(campaign_id=id,episode_id=batch_id,origin='prototype',split='development',arm=arm,source_mode=record['source_mode_by_arm'][arm],experiment_purpose='discovery',trial_index=0,study_id=study_id,evidence_context_id=study_id,execution_epoch=campaign.execution_epoch,agent_registration_id=registration)
                metadata={**provenance.model_dump(mode='json'),'model_id':campaign.model if arm=='B0' else 'deterministic-reference/internal-smoke','policy_hash':baseline.policy_hash,'contract_hash':config['contract_hash'],'scorer_hash':config['scorer_hash']}
                sessions[arm]=await publisher.begin(batch_id,metadata,expected_episode_ids=[slot['episode_id'] for slot in record['slots'] if slot['arm']==arm],frozen=False)
                record['telemetry'][arm]={'batch_id':batch_id,'status':'PENDING' if arm=='B0' else 'local_only'}
        record['status']='RUNNING'; record['reason']='Executing predeclared fresh trials'; save()
        cases={case['case_id']:case for case in manifest['cases']}
        for slot in record['slots']:
            if stop(): raise InterruptedError()
            case=cases[slot['case_id']]; arm=slot['arm']
            slot['status']='RUNNING'; save()
            trial=await runner.run(campaign,FaultSpec.model_validate_json(canonical_json(case['fault_spec'])),baseline,episode_id=slot['episode_id'],purpose='discovery',arm=arm,trial_index=slot['trial_index'],fixture_id=case['fixture_id'],study_id=study_id,evidence_context_id=study_id,ledger=ledger if arm=='B0' else None,reservation=reservation if arm=='B0' else None,stop=stop,source_mode=record['source_mode_by_arm'][arm])
            trials.append(trial); record['trial_ids'].append(trial.episode_id); record['trials'].append(trial.model_dump(mode='json')); slot['status']=trial.lifecycle
            current=coordinator.get(id); current.latest_episode_id=trial.episode_id; coordinator.save(current)
            if arm in sessions:
                e=coordinator.store.get_record('episodes',trial.episode_id)
                if e and e.get('verdict'):
                    try:
                        await sessions[arm].record_prediction(trial.episode_id,inputs={'scenario_hash':trial.scenario_hash,'arm':arm,'source_mode':record['source_mode_by_arm'][arm]},original_report=e['report'],persisted_scores={check['check_id']:check['passed'] for check in e['verdict']['checks']})
                    except Exception: record['telemetry'][arm]['status']='weave_pending' if arm=='B0' else 'local_pending'
            if arm=='B0' and trial.lifecycle=='COMPLETED' and coordinator.evidence_gateway:
                try:
                    evidence=await coordinator.evidence_gateway.get(trial.episode_id,EvidenceContext(id,study_id,study_id),stopped=stop)
                    record['evidence'][trial.episode_id]=evidence.source
                except Exception: record['evidence'][trial.episode_id]='weave_pending'
            save()
            if trial.lifecycle=='INTERRUPTED': raise InterruptedError()
        complete=len(trials)==36 and all(valid_trial(trial) for trial in trials)
        record['status']='COMPLETED' if complete else 'INCOMPLETE'
        record['reason']='All predeclared trials retained; observed outcomes are not a learned-policy claim' if complete else 'All attempted outcomes retained; invalid or untriggered trials prevent a complete comparison'
        for arm,session in sessions.items():
            if len([t for t in trials if t.arm==arm])==18:
                try: record['telemetry'][arm]=await session.finish(summarize([t for t in trials if t.arm==arm]))
                except Exception: record['telemetry'][arm]['status']='weave_pending' if arm=='B0' else 'local_pending'
    except (InterruptedError,asyncio.CancelledError):
        record['status']='INTERRUPTED'; record['reason']='Stopped; all attempted effects retained and no trial replayed'
    except Exception:
        record['status']='INCOMPLETE'; record['reason']='Infrastructure or evidence initialization failed; saved attempts are retained without retry'
    finally:
        record['by_arm']={arm:summarize([t for t in trials if t.arm==arm]) for arm in ARMS}
        record['usage']=summarize(trials)['usage']
        record['charged_model_calls']=ledger.used_calls-start_calls; record['charged_token_upper_bound']=ledger.used_tokens-start_tokens
        record['ended_at']=utc_now().isoformat(); save(); ledger.release(reservation)
        if not stop(): coordinator.transition(id,'COMPLETED',record['reason'])
        try:
            if owned and runner:
                for resource in (runner.world_client,runner.provider,getattr(runner,'telemetry_worker',None)):
                    if resource:
                        try: await asyncio.wait_for(resource.close(),timeout=2)
                        except Exception: pass
        finally:
            async with coordinator.lock:
                if coordinator.active_id==id: coordinator.active_id=None

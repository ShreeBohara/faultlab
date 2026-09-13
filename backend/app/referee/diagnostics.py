"""Fixed bounded intervention and evidence-gap validation; explanations are proposals."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal
from app.contracts.models import DiagnosticResult,FaultSpec,InterventionExperiment,TrialResult,content_hash,new_id
from app.simulator.capabilities import AUTHORITY_PATHS,PROBES,PROFILE_HASHES,diagnostic_profile,normalize_transcript
from .reducer import _call,valid_trial

PROTOCOL_HASH=content_hash({'version':'diagnostics/v1','variants':4,'trials':3,'hypotheses':['removes_violation','retains_violation'],'profile':diagnostic_profile().model_dump(mode='json')})
def checker_hash():return sha256(Path(__file__).read_bytes()).hexdigest()

@dataclass(frozen=True)
class InterventionVariant:
    intervention_id:str
    hypothesis:str
    proposal_ref:str
    control:FaultSpec
    treatment:FaultSpec
    prediction:Literal['removes_violation','retains_violation']

@dataclass(frozen=True)
class InterventionRun:
    experiments:list[InterventionExperiment]
    trials:list[TrialResult]


def single_change(control,treatment):
    a=control.model_dump(mode='json');b=treatment.model_dump(mode='json')
    if any(a[k]!=b[k] for k in ('scope','schema_version','seed')):return False
    aa,bb=a['primitives'],b['primitives']
    if len(aa)==len(bb)+1:return any(aa[:i]+aa[i+1:]==bb for i in range(len(aa)))
    if len(bb)==len(aa)+1:return any(bb[:i]+bb[i+1:]==aa for i in range(len(bb)))
    if len(aa)!=len(bb):return False
    def changes(x,y):
        if isinstance(x,dict) and isinstance(y,dict):return sum(changes(x.get(k),y.get(k)) for k in x.keys()|y.keys())
        if isinstance(x,list) and isinstance(y,list):return sum(changes(i,j) for i,j in zip(x,y))
        return x!=y
    return changes(aa,bb)==1

async def run_interventions(counterexample_id,target_invariant,variants,execute_fresh,*,should_stop=None,validate=None):
    if not 1<=len(variants)<=4:raise ValueError('one to four declared variants required')
    if len({v.intervention_id for v in variants})!=len(variants):raise ValueError('duplicate intervention identity')
    for v in variants:
        if not single_change(v.control,v.treatment):raise ValueError('intervention must change one schedule dimension')
        if v.prediction not in ('removes_violation','retains_violation'):raise ValueError('unreviewed hypothesis prediction')
    trials=[];experiments=[];worlds=set();episodes=set();policy_hash=None
    for variant in variants:
        pairs=[];counts=[[],[]];reason=None
        if validate:
            for recipe in (variant.control,variant.treatment):
                if await _call(validate,recipe) is False:reason='PREFLIGHT_REJECTED'
        for index in range(3):
            if reason:break
            pair={}
            for arm in ([0,1] if index%2==0 else [1,0]):
                if should_stop and should_stop():reason='STOPPED';break
                recipe=(variant.control,variant.treatment)[arm]
                try:trial=await _call(execute_fresh,recipe,index)
                except Exception as exc:reason='CALLBACK_ERROR:'+type(exc).__name__;break
                if not isinstance(trial,TrialResult):reason='INVALID_CALLBACK_RESULT';break
                valid=valid_trial(trial,recipe,index,worlds,episodes,policy_hash)
                if policy_hash is None:policy_hash=trial.policy_hash
                worlds.add(trial.world_id);episodes.add(trial.episode_id);trials.append(trial);pair[arm]=trial
                counts[arm].append(target_invariant in trial.failed_checks if valid else None)
                if not valid:reason='INVALID_OR_UNTRIGGERED_TRIAL'
            if len(pair)==2:pairs.append((pair[0].episode_id,pair[1].episode_id))
        supported_control=counts[0]==[True]*3
        expected=[False]*3 if variant.prediction=='removes_violation' else [True]*3
        inverse=[not expected[0]]*3
        outcome='SUPPORTED' if not reason and supported_control and counts[1]==expected else 'CONTRADICTED' if not reason and supported_control and counts[1]==inverse else 'INCONCLUSIVE'
        experiments.append(InterventionExperiment(intervention_id=variant.intervention_id,counterexample_id=counterexample_id,hypothesis=variant.hypothesis,proposal_ref=variant.proposal_ref,change=variant.prediction,control_hash=content_hash(variant.control),treatment_hash=content_hash(variant.treatment),trial_pairs=pairs,result=outcome,evidence_ids=[],limitations=[reason or 'Three paired observations test only the declared schedule change; no universal causal claim.']))
    return InterventionRun(experiments,trials)


def classify_policy_gap(counterexample_id,target_invariant,reproduction_trials,interventions,*,proposed_kind='POLICY_GAP'):
    trials=list(reproduction_trials)
    reproduced=len(trials)==3 and len({t.world_id for t in trials})==3 and len({t.episode_id for t in trials})==3 and {t.trial_index for t in trials}=={0,1,2} and len({t.scenario_hash for t in trials})==1 and len({t.policy_hash for t in trials})==1 and all(t.lifecycle=='COMPLETED' and t.outcome=='VIOLATION' and target_invariant in t.failed_checks and (not t.fault_scheduled or t.fault_triggered) for t in trials)
    supported=reproduced and any(i.result=='SUPPORTED' and len(i.trial_pairs)==3 and i.counterexample_id==counterexample_id for i in interventions) and not any(i.result=='CONTRADICTED' for i in interventions)
    kind='POLICY_GAP' if supported else 'INCONCLUSIVE'
    return DiagnosticResult(diagnostic_id=new_id('diagnostic'),counterexample_id=counterexample_id,proposed_kind=proposed_kind,kind=kind,explanation='Fresh reproduction and the declared controlled intervention support a bounded policy hypothesis.' if supported else 'Reproduction or discriminating intervention evidence is incomplete or contradictory.',intervention_ids=[i.intervention_id for i in interventions][:4],reproduction_ids=[t.episode_id for t in trials][:3],evidence_ids=[],authority_paths=AUTHORITY_PATHS,equivalence_refs=[],tested_scope='Three fresh trials of the fixed development recipe and declared paired schedule intervention.',required_behavior='Preserve original operation identities and require delivered matching receipts for success.',limitations=['A supported hypothesis permits a candidate proposal, never promotion or a claim of improvement.'],checker_hash=checker_hash(),protocol_hash=PROTOCOL_HASH)


def validate_gap(committed,uncommitted,*,counterexample_id=None,proposed_kind='CONTRACT_EVIDENCE_GAP'):
    issues=[];expected=PROFILE_HASHES['evidence_gap_v1']
    for witness in (committed,uncommitted):
        if witness.get('profile_id')!='evidence_gap_v1':issues.append('Not the fixed evidence_gap_v1 capability profile.')
        if any(witness.get(k)!=v for k,v in expected.items()):issues.append('Frozen profile hash mismatch.')
        if witness.get('authority_paths')!=AUTHORITY_PATHS:issues.append('Authoritative path inventory incomplete.')
        if witness.get('prior_receipts'):issues.append('A prior delivered receipt remains authoritative.')
        transcript=witness.get('transcript',[])
        if [p.get('probe') for p in transcript]!=PROBES or [p.get('tick') for p in transcript]!=list(range(1,11)):issues.append('Predeclared finite probe coverage incomplete.')
        if witness.get('horizon')!=10:issues.append('Diagnostic deadline mismatch.')
        for i,p in enumerate(transcript):
            result=p.get('result',{})
            if (i==0 and result.get('transport')!='timeout') or (i>0 and (result.get('transport')!='error' or result.get('error_code')!='DIAGNOSTIC_PATH_UNAVAILABLE')):issues.append('The declared evidence path was not uniformly unavailable.')
            if result.get('receipt_id') or result.get('data') is not None:issues.append('Distinguishing semantic evidence was delivered.')
    if committed.get('world_id')==uncommitted.get('world_id') or committed.get('private_committed') is not True or committed.get('incident_committed') is not True or uncommitted.get('private_committed') is not False or uncommitted.get('incident_committed') is not False:issues.append('Private committed/uncommitted witness difference is absent.')
    a=normalize_transcript(committed.get('transcript',[]),committed.get('identities',{}));b=normalize_transcript(uncommitted.get('transcript',[]),uncommitted.get('identities',{}))
    if a!=b:issues.append('Normalized public transcripts differ.')
    kind='INCONCLUSIVE' if issues else 'CONTRACT_EVIDENCE_GAP'
    return DiagnosticResult(diagnostic_id=new_id('diagnostic'),counterexample_id=counterexample_id,diagnostic_profile_id='evidence_gap_v1',proposed_kind=proposed_kind,kind=kind,explanation='Terminal upgrade evidence was unavailable through all declared paths within this diagnostic deadline.' if not issues else 'The bounded evidence-gap protocol checks did not establish the witness.',intervention_ids=[],reproduction_ids=[],evidence_ids=(committed.get('evidence_ids',[])+uncommitted.get('evidence_ids',[]))[:108],authority_paths=AUTHORITY_PATHS,equivalence_refs=[content_hash(a),content_hash(b)],tested_scope='Fixed evidence_gap_v1 finite probe set: 10 admitted actions through tick 10 in two isolated worlds.',required_behavior='Remain unresolved without a matching delivered upgrade receipt; make authoritative terminal evidence available within the task deadline.',limitations=list(dict.fromkeys(issues))[:12]+['Observed ambiguity is limited to these worlds, probes and deadline; it is not universal impossibility.','This diagnostic capability fixture is excluded from learned-gain, promotion, audit and selector metrics.'],checker_hash=checker_hash(),protocol_hash=PROTOCOL_HASH)


def execute_witness(client,handle,intent,*,control_token,profile_id):
    """Execute all fixed probes over an already configured localhost HTTP client.

    The caller creates the private diagnostic world first. No saved actor answers,
    provider calls, notification calls, or hidden data enter public observations.
    """
    import httpx
    headers={'X-FaultLab-World':handle['world_id'],'X-FaultLab-Capability':handle['capability']}
    control={'X-FaultLab-Control':control_token}
    body={'order_id':intent.order_id,'desired_shipping':'express','expected_version':intent.expected_version,'operation_id':intent.upgrade_operation_id,'idempotency_key':intent.upgrade_idempotency_key,'intent_hash':intent.upgrade_intent_hash}
    transcript=[];incident=None
    for index,probe in enumerate(PROBES):
        call=f'probe-{index}';h=headers|{'X-FaultLab-Call':call,'X-FaultLab-Attempt':f'attempt-{index}'}
        try:
            if probe in ('original_upgrade_write','identical_upgrade_replay'):response=client.post(f'/business/orders/{intent.order_id}/upgrade',json=body,headers=h,timeout=1)
            elif probe=='upgrade_status':response=client.get(f'/business/operations/orders/{intent.upgrade_operation_id}',headers=h,timeout=1)
            else:response=client.get(f'/business/orders/{intent.order_id}',headers=h,timeout=1)
            result=response.json()
        except httpx.ReadTimeout:
            from app.contracts.models import ToolResult
            result=ToolResult(call_id=call,tool='update_order',transport='timeout',operation_id=intent.upgrade_operation_id,order_id=intent.order_id,error_code='TIMEOUT').model_dump(mode='json')
        snapshot=client.get('/control/worlds/'+handle['world_id']+'/snapshot',headers=control).json()
        committed_now=any(o['service']=='orders' and o['state']=='SUCCEEDED' for o in snapshot['operations'])
        if index==0:incident=committed_now
        transcript.append({'probe':probe,'tick':snapshot['tick'],'result':result})
    return {'profile_id':profile_id,**PROFILE_HASHES[profile_id],'world_id':handle['world_id'],'private_committed':committed_now,'incident_committed':incident,'transcript':transcript,'prior_receipts':[],'authority_paths':AUTHORITY_PATHS,'horizon':10,'evidence_ids':[],'identities':{intent.order_id:'ORDER',intent.upgrade_operation_id:'UPGRADE',intent.upgrade_intent_hash:'INTENT'},'source_mode':'offline_fixture'}

"""Model hypotheses select reviewed interventions; fixed code assigns verdicts."""
from app.contracts.models import content_hash,canonical_json,new_id,EpisodeBudget
from app.agents.actor import ACTOR_PROMPT
from app.referee.reducer import neighbors
from app.referee.diagnostics import InterventionVariant,InterventionRun,run_interventions,classify_policy_gap

def runtime_contract():
    return {'actor_contract':ACTOR_PROMPT,'episode_limits':EpisodeBudget().model_dump(mode='json'),
            'hook_execution':'Policy hooks execute their finite steps inside the existing business-call boundaries. Reads and same-identity retries consume HTTP attempts; waits consume ticks and polling cycles; all steps consume the policy-step budget. These hook steps do not consume actor model turns. They deliver observations for the next original actor turn. They cannot rewrite its report or create new authorized operations.'}

def trial_outcomes(trials):
    # Group only identical public outcomes. Every attempted trial remains named,
    # including infrastructure errors, untriggered cases and contradictory checks.
    groups={}
    for trial in trials:
        value={'scenario_hash':trial.scenario_hash,'arm':trial.arm,'lifecycle':trial.lifecycle,
               'outcome':trial.outcome,'failed_checks':trial.failed_checks,'fault_scheduled':trial.fault_scheduled,
               'fault_triggered':trial.fault_triggered,'actor_calls':trial.usage.actor_calls,'http_attempts':trial.usage.http_attempts}
        key=canonical_json(value)
        if key not in groups: groups[key]={**value,'episode_ids':[]}
        groups[key]['episode_ids'].append(trial.episode_id)
    return list(groups.values())

def reduction_context(result,trials,evidence):
    data=result.model_dump(mode='json')
    return {'status':data['status'],'stopping_reason':data.get('stopping_reason'),
            'attempts':[{k:a[k] for k in ('transform','retained','reason','trial_ids')} for a in data.get('attempts',[])],
            'trial_outcomes':trial_outcomes(trials),'verified_episode_ids':[b.episode_id for b in evidence if b.source=='weave_verified']}

def observed_outcomes(reduction,scenario_hash,target):
    """Fresh reduction trials already executed for this exact recipe under the same policy.

    Reads only the retained grouped public outcomes; nothing is rerun and no verdict
    is assigned here. None means that recipe was not observed during reduction.
    """
    groups=[g for g in (reduction or {}).get('trial_outcomes',[]) if g.get('scenario_hash')==scenario_hash]
    if not groups: return None
    def valid(g): return g.get('lifecycle')=='COMPLETED' and g.get('outcome') not in (None,'LAB_ERROR') and (not g.get('fault_scheduled') or g.get('fault_triggered'))
    def count(pred): return sum(len(g.get('episode_ids',[])) for g in groups if pred(g))
    return {'fresh_trials':count(lambda g:True),'valid_trials':count(valid),'target_violations':count(lambda g: valid(g) and target in (g.get('failed_checks') or [])),'episode_ids':[e for g in groups for e in g.get('episode_ids',[])]}

class Diagnostician:
    def __init__(self,store,runner,ledger,mechanic): self.store,self.runner,self.ledger,self.mechanic=store,runner,ledger,mechanic
    async def run(self,campaign,counter,recipe,policy,reproduction_trials,*,evidence,reduction=None,fixture_id='standard-v1',stop=lambda:False):
        options={}
        # Fixed finite one-variable options are named before model selection.
        for change,treatment in neighbors(recipe):
            if len(options)>=4: break
            key='intervention-'+content_hash({'control':recipe,'treatment':treatment})[:24]
            options[key]=(change,treatment)
        evidence_ids=[o.evidence_id for bundle in evidence for o in bundle.observations]
        context={'counterexample_id':counter.counterexample_id,'target_invariant':counter.target_invariant,'reproduction_counts':{'attempted':counter.attempted_count,'valid':counter.valid_count,'target_violations':counter.target_violation_count},'evidence_ids':evidence_ids[:36],'intervention_ids':list(options),'control_fault_spec':recipe.model_dump(mode='json'),'observed_control_trials':observed_outcomes(reduction,content_hash(recipe),counter.target_invariant),'interventions':[{'id':key,'change':value[0],'treatment_fault_spec':value[1].model_dump(mode='json'),'prediction':'removes_violation','expected_result':'3/3 control target violations and zero treatment target violations','observed_treatment_trials':observed_outcomes(reduction,content_hash(value[1]),counter.target_invariant)} for key,value in options.items()],'observations':summarize_evidence(evidence),'runtime_contract':runtime_contract(),'reduction':reduction}
        proposal_ref,proposal,raws=await self.mechanic.diagnose(context)
        variants=[]
        if proposal and proposal.requested_intervention_id in options:
            key=proposal.requested_intervention_id; change,treatment=options[key]
            # Fixed alternative removes the suspected causal fault; supported iff 3/3 control failures and treatment eliminates it.
            variants=[InterventionVariant(intervention_id=key,hypothesis=proposal.hypothesis,proposal_ref=proposal_ref,control=recipe,treatment=treatment,prediction='removes_violation')]
        admitted=[]
        async def execute_fresh(spec,index,arm=None):
            name=f'intervention:{counter.counterexample_id}'
            if name not in self.ledger.reservations: self.ledger.reserve(name,48); admitted.append(name)
            return await self.runner.run(campaign,spec,policy,purpose='intervention',trial_index=index,fixture_id=fixture_id,ledger=self.ledger,reservation=name,stop=stop)
        try:
            run=await run_interventions(counter.counterexample_id,counter.target_invariant,variants,execute_fresh,should_stop=stop) if variants else InterventionRun([],[])
        finally:
            for name in admitted: self.ledger.release(name)
        for experiment in run.experiments: self.store.put_record('interventions',experiment.intervention_id,experiment,immutable=True)
        diagnostic=classify_policy_gap(counter.counterexample_id,counter.target_invariant,reproduction_trials,run.experiments,proposed_kind=proposal.proposed_kind if proposal else 'INCONCLUSIVE')
        self.store.put_record('diagnostics',diagnostic.diagnostic_id,diagnostic,immutable=True)
        self.store.put_record('diagnostic_campaigns',diagnostic.diagnostic_id,{'campaign_id':campaign.campaign_id,'counterexample_id':counter.counterexample_id,'diagnostic_id':diagnostic.diagnostic_id},immutable=True)
        return diagnostic,run


def summarize_evidence(bundles):
    """Table compression preserves every observed semantic value and contradiction.

    Opaque identity values are consistently aliased within each episode. Original
    IDs/records remain persisted and episode/evidence IDs remain exact citations.
    Shared rows are interned only after complete typed-value equality.
    """
    import re
    opaque=re.compile(r'^(?:[A-Za-z][A-Za-z0-9_-]*[-:])?[a-f0-9]{24,64}$')
    tables={'results':[],'reports':[],'checks':[]}; indexes={k:{} for k in tables}
    def intern(kind,value):
        encoded=canonical_json(value)
        if encoded not in indexes[kind]: indexes[kind][encoded]=len(tables[kind]); tables[kind].append(value)
        return indexes[kind][encoded]
    episodes=[]
    for bundle in bundles:
        identities={}; evidence={o.evidence_id:f'o{index+1}' for index,o in enumerate(bundle.observations)}
        identity_fields={'call_id','operation_id','order_id','intent_hash','receipt_id','effect_id','last_upgrade_operation_id','event_ids'}
        def compact(value,field=None):
            if isinstance(value,dict): return {k:compact(v,k) for k,v in value.items() if v is not None}
            if isinstance(value,list): return [compact(v,field) for v in value]
            if isinstance(value,str):
                if field in ('evidence_id','evidence_ids') and value in evidence: return evidence[value]
                if field in identity_fields and opaque.fullmatch(value):
                    if value not in identities: identities[value]=f'@i{len(identities)+1}'
                    return identities[value]
            return value
        observations=[]
        for observation in bundle.observations:
            observations.append([observation.evidence_id,observation.delivered_tick,intern('results',compact(observation.result.model_dump(mode='json')))])
        report=compact(bundle.report.model_dump(mode='json')) if bundle.report else None
        findings=compact([finding.model_dump(mode='json') for finding in bundle.findings])
        episodes.append({'episode_id':bundle.episode_id,'source':bundle.source,'observations':observations,'report_row':intern('reports',report),'check_row':intern('checks',findings)})
    return {'format':'faultlab-compact-evidence/v1','interpretation':'Each observation row is [exact evidence_id, delivered_tick, results table index]. Reports/checks use their table indexes. oN cites the Nth observation of that episode. @iN consistently aliases an opaque operation/order/intent/receipt/call/event identity within that episode; different aliases remain different identities. Omitted nullable fields are null. All trials and all delivered results, including contradictions, are retained. Original complete records are referenced by exact episode/evidence IDs.','episodes':episodes,**tables}

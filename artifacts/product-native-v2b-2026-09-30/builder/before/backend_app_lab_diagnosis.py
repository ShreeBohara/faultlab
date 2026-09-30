"""Model hypotheses select reviewed interventions; fixed code assigns verdicts."""
from app.contracts.models import content_hash,canonical_json,new_id,EpisodeBudget
from app.agents.actor import ACTOR_PROMPT
from app.referee.reducer import neighbors
from app.referee.diagnostics import InterventionVariant,InterventionRun,run_interventions,classify_policy_gap

# Declared evidence-presentation protocols for the compact Mechanic/Explorer summary.
# V1 is the preserved default every caller receives unless it asks otherwise. V2 binds the
# adjudicated per-episode outcome the caller already supplies in grouped form; it discloses
# nothing new. The allowlist lives here, with the protocols themselves.
COMPACT_EVIDENCE_V1 = 'faultlab-compact-evidence/v1'
COMPACT_EVIDENCE_V2 = 'faultlab-compact-evidence/v2-task-outcome'
EVIDENCE_PROTOCOLS = (COMPACT_EVIDENCE_V1, COMPACT_EVIDENCE_V2)
TASK_OUTCOME_CLAUSE = (' task_outcome is the adjudicated public outcome of that episode, '
                       'the same value grouped in observed_outcomes.')

def runtime_contract(store=None,campaign=None):
    actor_contract=ACTOR_PROMPT
    if store is not None and campaign is not None:
        from app.lab.runner import campaign_run_plan
        plan=campaign_run_plan(store,campaign)
        if plan and plan['agent']=='smolagents':
            from app.integrations.registry import AgentRegistry,NATIVE_FILES
            from app.integrations.external_agent import TASK_CONTRACT,TRANSPORT_CONTRACT
            registration=AgentRegistry(store).get(plan['agent_registration_id'])
            actor_contract={'implementation':'smolagents/1.26.0 ToolCallingAgent',
                            'task_contract':TASK_CONTRACT,'transport_contract':TRANSPORT_CONTRACT,
                            'memory':'Fresh native agent and empty native memory for each episode; original reports cite full delivered evidence IDs.',
                            'prompt_hash':registration.prompt_hash,'source_hash':registration.source_hash,
                            'native_template_hash':NATIVE_FILES['prompts/toolcalling_agent.yaml']}
        elif plan and plan['agent']=='smolagents-v2':
            # Native adapter v2: v1's contract and transport text, plus its declared labels and final-report turn.
            from app.integrations.registry import AgentRegistry,NATIVE_FILES
            from app.integrations.external_agent_v2 import TASK_CONTRACT,TRANSPORT_CONTRACT,adapter_protocol
            registration=AgentRegistry(store).get(plan['agent_registration_id'])
            actor_contract={'implementation':'smolagents/1.26.0 ToolCallingAgent, FaultLab native adapter v2',
                            'task_contract':TASK_CONTRACT,'transport_contract':TRANSPORT_CONTRACT,
                            'adapter_protocol':adapter_protocol(),
                            'memory':'Fresh native agent and empty native memory for each episode; the agent sees each delivered observation\'s evidence_id as its journal label (obs-N), and its report\'s cited labels are decoded back to the full evidence IDs before validation.',
                            'prompt_hash':registration.prompt_hash,'source_hash':registration.source_hash,
                            'native_template_hash':NATIVE_FILES['prompts/toolcalling_agent.yaml']}
    return {'actor_contract':actor_contract,'episode_limits':EpisodeBudget().model_dump(mode='json'),
            'hook_execution':'Rules run in array order. Each rule tests when once on entry; each visited step retests only_if and consumes a policy step, including skipped steps. Policy reads and same-identity retries consume HTTP attempts and ticks; waits consume ticks and polling cycles. Hook steps do not consume actor model turns and do not recursively invoke hooks. Newly delivered observations appear on the next original actor turn. No hook can rewrite a report or create a new authorized operation.',
            'hook_boundaries':{
                'after_upgrade_response':'Once after an executed actor update_order has delivered its result or exhausted adapter retries. Policy retries and status reads do not invoke this hook again.',
                'before_confirmation':'Before each schema-valid actor send_confirmation proposal, before HTTP dispatch. A blocked or final-requested proposal consumes its actor turn but dispatches nothing.',
                'after_notification_response':'Once after an executed actor send_confirmation has delivered its result or exhausted adapter retries. It does not run when before_confirmation blocked dispatch.',
                'before_final_report':'Only after a schema-valid actor report proposal, before finalization/scoring. It never runs when the actor proposes a tool, returns invalid output, or fails to propose a report. An unblocked original report finalizes unchanged; a blocked report needs a new actor proposal within remaining turns.'},
            'primitive_semantics':{
                'read_current_operation':'Read public status of the original orders operation, regardless of the most recently called tool. Does not submit an upgrade.',
                'read_notification_operation':'Read public status of the original notifications operation. Does not submit a confirmation.',
                'read_order':'Read the order projection, which may be stale and is not a terminal operation receipt.',
                'wait_ticks':'Advance logical time by the supplied 1..4 ticks and consume one wait cycle. Does not read status or deliver a receipt by itself.',
                'retry_original_request':'Replay an already attempted write for the supplied service using its persisted original bytes and identity. No first write and no retry after a matching FAILED receipt. Notification retries are permitted only at after_notification_response.',
                'require_receipt':'Check for a delivered matching SUCCEEDED receipt and create the scoped requirement described in report_control. Does not poll, wait, dispatch a write or request a report.',
                'defer_unresolved':'Close business calls and request an original actor report as described in report_control. Does not choose report fields.',
                'report_terminal_failure':'Request an original actor report only with a delivered matching FAILED receipt for the supplied service; see report_control.'},
            'condition_evidence':'Use delivered observations and the original write-attempt journal only. A matching terminal receipt remains authoritative after later UNKNOWN or stale observations. Without a receipt, status is the latest observation of the original service operation; missing status is UNKNOWN, and no such observation means no status. No condition reads private simulator state.',
            'condition_semantics':{
                'always':'True.',
                'upgrade_receipt_missing':'No matching SUCCEEDED orders receipt; also true when a matching FAILED receipt exists.',
                'notification_receipt_missing':'No matching SUCCEEDED notifications receipt; also true when a matching FAILED receipt exists.',
                'current_operation_pending':'No matching orders terminal receipt and latest orders operation status is PENDING. Does not require a receipt.',
                'notification_operation_pending':'No matching notifications terminal receipt and latest notifications operation status is PENDING. Does not require a receipt.',
                'upgrade_outcome_uncertain':'An orders write was attempted, no matching terminal receipt exists, and its status is PENDING, UNKNOWN or absent.',
                'notification_outcome_uncertain':'A notifications write was attempted, no matching terminal receipt exists, and its status is PENDING, UNKNOWN or absent.',
                'upgrade_terminal_failure':'A matching FAILED orders receipt was delivered.',
                'notification_terminal_failure':'A matching FAILED notifications receipt was delivered.',
                'upgrade_succeeded':'A matching SUCCEEDED orders receipt was delivered.',
                'notification_succeeded':'A matching SUCCEEDED notifications receipt was delivered.',
                'receipt_missing':'Hook-local flag, initially false at each hook entry. The most recent require_receipt step sets it from that step\'s service receipt check. Later reads do not refresh this flag; service-specific conditions inspect current observations.'},
            'report_control':{
                'reserved_final_turn':'Without business closure, only the last of the eight physical actor calls is reserved for a report. A tool proposed then is not dispatched; if no valid report is submitted, the episode violates the report contract. There is no extra repair turn.',
                'defer_unresolved':'Sets business_closed immediately, stops remaining steps/rules in this hook, and makes every remaining actor turn report-required. It does not generate a report or force an unresolved claim; the original actor must report truthfully from its observations.',
                'report_terminal_failure':'Requires a delivered matching FAILED receipt; otherwise returns POLICY_PRECONDITION_UNMET. With that receipt it has the same business-closure control effect as defer_unresolved. It does not generate a report.',
                'require_receipt':'Tests for a matching SUCCEEDED receipt without calling a tool. Requirements are rechecked after the hook. An unmet requirement blocks before_confirmation; at before_final_report it blocks only a report claiming that service SUCCEEDED. At response hooks it does not block future actions or close business calls.',
                'limits':'Business closure does not add model turns or extend the deadline. All original episode caps and report checks still apply.'}}

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
            key='intervention-'+content_hash({'counterexample_id':counter.counterexample_id,'control':recipe,'treatment':treatment})[:24]
            options[key]=(change,treatment)
        evidence_ids=[o.evidence_id for bundle in evidence for o in bundle.observations]
        context={'counterexample_id':counter.counterexample_id,'target_invariant':counter.target_invariant,'reproduction_counts':{'attempted':counter.attempted_count,'valid':counter.valid_count,'target_violations':counter.target_violation_count},'evidence_ids':evidence_ids[:36],'intervention_ids':list(options),'control_fault_spec':recipe.model_dump(mode='json'),'observed_control_trials':observed_outcomes(reduction,content_hash(recipe),counter.target_invariant),'interventions':[{'id':key,'change':value[0],'treatment_fault_spec':value[1].model_dump(mode='json'),'prediction':'removes_violation','expected_result':'3/3 control target violations and zero treatment target violations','observed_treatment_trials':observed_outcomes(reduction,content_hash(value[1]),counter.target_invariant)} for key,value in options.items()],'observations':summarize_evidence(evidence),'runtime_contract':runtime_contract(self.store,campaign),'reduction':reduction}
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


def summarize_evidence(bundles,outcomes=None):
    """Table compression preserves every observed semantic value and contradiction.

    Opaque identity values are consistently aliased within each episode. Original
    IDs/records remain persisted and episode/evidence IDs remain exact citations.
    Shared rows are interned only after complete typed-value equality.

    outcomes optionally maps episode_id to the adjudicated public outcome the caller
    already supplies in grouped form. It adds one field per episode and discloses
    nothing new. Callers that omit it receive byte-identical v1 output.
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
        row={'episode_id':bundle.episode_id,'source':bundle.source,'observations':observations,'original_report_present':bundle.report is not None,'report_row':intern('reports',report),'check_row':intern('checks',findings)}
        if outcomes is not None: row['task_outcome']=outcomes.get(bundle.episode_id)
        episodes.append(row)
    legend='Each observation row is [exact evidence_id, delivered_tick, results table index]. Reports/checks use their table indexes. original_report_present=false means no final original report was recorded; it does not establish what the actor may have proposed. A present report is not necessarily correct. oN cites the Nth observation of that episode. @iN consistently aliases an opaque operation/order/intent/receipt/call/event identity within that episode; different aliases remain different identities. Omitted nullable fields are null. All trials and all delivered results, including contradictions, are retained. Original complete records are referenced by exact episode/evidence IDs.'
    if outcomes is not None: legend+=TASK_OUTCOME_CLAUSE
    return {'format':COMPACT_EVIDENCE_V1 if outcomes is None else COMPACT_EVIDENCE_V2,'interpretation':legend,'episodes':episodes,**tables}

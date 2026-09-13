def fixture_witness(committed,profile_id='evidence_gap_v1'):
    from app.simulator.capabilities import PROFILE_HASHES,PROBES,AUTHORITY_PATHS
    transcript=[{'probe':p,'tick':i+1,'result':{'transport':'timeout' if i==0 else 'error','status':None,'error_code':'TIMEOUT' if i==0 else 'DIAGNOSTIC_PATH_UNAVAILABLE'}} for i,p in enumerate(PROBES)]
    if profile_id=='available_status_v1':transcript[1]['result']={'transport':'ok','status':'SUCCEEDED' if committed else 'UNKNOWN'}
    return {'profile_id':profile_id,**PROFILE_HASHES[profile_id],'world_id':'committed-world' if committed else 'uncommitted-world','private_committed':committed,'incident_committed':committed,'transcript':transcript,'prior_receipts':[],'authority_paths':AUTHORITY_PATHS,'horizon':10,'evidence_ids':[],'identities':{},'source_mode':'offline_fixture'}

import asyncio
from app.contracts.models import *


def test_complete_fixed_probe_witness_is_qualified_gap():
    from app.referee.diagnostics import validate_gap
    a=fixture_witness(True);b=fixture_witness(False)
    result=validate_gap(a,b)
    assert result.kind=='CONTRACT_EVIDENCE_GAP'
    assert 'finite' in result.tested_scope and result.diagnostic_profile_id=='evidence_gap_v1'
    assert result.limitations

def test_missing_probe_or_meaningful_difference_or_prior_receipt_is_inconclusive():
    from app.referee.diagnostics import validate_gap
    a=fixture_witness(True);b=fixture_witness(False)
    b['transcript']=b['transcript'][:-1];assert validate_gap(a,b).kind=='INCONCLUSIVE'
    b=fixture_witness(False);b['transcript'][2]['result']['error_code']='OTHER';assert validate_gap(a,b).kind=='INCONCLUSIVE'
    b=fixture_witness(False);b['prior_receipts']=['receipt-present'];assert validate_gap(a,b).kind=='INCONCLUSIVE'

def test_available_status_control_distinguishes_worlds():
    from app.referee.diagnostics import validate_gap
    assert validate_gap(fixture_witness(True,profile_id='available_status_v1'),fixture_witness(False,profile_id='available_status_v1')).kind=='INCONCLUSIVE'

def test_intervention_requires_single_change_fresh_paired_trials_and_preserves_contradiction():
    from app.referee.diagnostics import InterventionVariant,run_interventions,classify_policy_gap
    original=FaultSpec.model_validate({'seed':1,'primitives':[{'kind':'F2','target_tool':'update_order','target_service':'orders','occurrence':1,'parameters':{'completion_delay_ticks':4,'terminal_status':'SUCCEEDED','failure_code':None}}]})
    treatment=original.model_copy(deep=True);treatment.primitives[0].parameters.completion_delay_ticks=2
    variant=InterventionVariant('iv','Timing causes C3','proposal',original,treatment,'removes_violation')
    async def execute(spec,index):return TrialResult(episode_id=new_id('ep'),world_id=new_id('world'),scenario_hash=content_hash(spec),policy_hash='a'*64,arm='B0',trial_index=index,lifecycle='COMPLETED',outcome='VIOLATION',failed_checks=['C3'],fault_scheduled=True,fault_triggered=True)
    run=asyncio.run(run_interventions('ce','C3',[variant],execute))
    assert run.experiments[0].result=='CONTRADICTED' and len(run.trials)==6
    diagnostic=classify_policy_gap('ce','C3',run.trials[::2],run.experiments,proposed_kind='POLICY_GAP')
    assert diagnostic.kind=='INCONCLUSIVE'

"""Separately frozen diagnostic fixture, never part of learned-policy comparisons."""
from copy import deepcopy
from app.contracts.models import DiagnosticProfile,ToolResult,content_hash

AUTHORITY_PATHS=['original_upgrade_write','identical_upgrade_replay','upgrade_status','order_projection','prior_delivered_receipts']
PROBES=['original_upgrade_write']+['upgrade_status','order_projection','identical_upgrade_replay']*3
NORMALIZATION={'version':'identity-map/v1','allowed_fields':['call_id','operation_id','order_id','intent_hash'],'preserve':['transport','status','receipt','observed_version','retry_after_ticks','error_code','tick','probe']}
FIXTURE={'version':'evidence-gap-fixture/v1','incident':'same timeout after commit versus before commit','horizon':10,'probes':PROBES,'status_replay_projection':'declared unavailable','prior_receipts':[],'notification':'not an authority path for upgrade','learning_eligible':False}
STANDARD={'schema':'faultlab/v1','semantics':'orders.upgrade_then_confirm/v1','status':'authoritative immutable terminal receipt','replay':'same identity current receipt','projection':'historical versioned object'}
PROFILE_HASHES={
    'evidence_gap_v1':{'contract_hash':content_hash(STANDARD|{'diagnostic_override':FIXTURE}),'capability_hash':content_hash({'inventory':AUTHORITY_PATHS,'unavailable_through':10}),'fixture_hash':content_hash(FIXTURE)},
    'available_status_v1':{'contract_hash':content_hash(STANDARD),'capability_hash':content_hash({'inventory':AUTHORITY_PATHS,'status':'available'}),'fixture_hash':content_hash(FIXTURE|{'status_replay_projection':'standard status available after incident'})},
}

def diagnostic_profile():
    hashes=PROFILE_HASHES['evidence_gap_v1']
    return DiagnosticProfile(profile_id='evidence_gap_v1',**hashes,oracle_hash=content_hash({'check':'committed world differs from uncommitted world at incident and horizon'}),normalization_hash=content_hash(NORMALIZATION),probe_set=list(dict.fromkeys(PROBES)),horizon=10)

def create_diagnostic_world(store,episode_id,intent,profile_id,committed):
    from app.contracts.models import FaultSpec
    if profile_id not in PROFILE_HASHES:raise ValueError('unregistered diagnostic profile')
    handle=store.create(episode_id,intent,FaultSpec(seed=0,primitives=[]),'standard-v1')
    with store.transaction(handle['world_id']) as state:
        state['diagnostic']={'profile_id':profile_id,'committed_witness':committed,'incident_done':False,'hashes':PROFILE_HASHES[profile_id]}
    return handle

def normalize_transcript(transcript,identities):
    """Map only known identity values; never drop semantic fields or timings."""
    def walk(value,key=None):
        if isinstance(value,dict):return {k:walk(v,k) for k,v in value.items()}
        if isinstance(value,list):return [walk(v,key) for v in value]
        return identities.get(value,value) if isinstance(value,str) and key in NORMALIZATION['allowed_fields'] else value
    return walk(deepcopy(transcript))

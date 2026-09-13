"""Explicit pre-experiment identity freeze; never invent an accepted learned arm."""
import json
import os
from pathlib import Path
from pydantic import TypeAdapter
from app.contracts.models import AgentRegistration,CampaignBudget,Digest,content_hash,utc_now
from app.lab.budgets import protected_reservations
from .manifests import load_manifest,manifest_hash

REQUIRED_HASHES=('baseline_policy_hash','model_hash','prompt_hash','budget_hash','adapter_hash','interpreter_hash','scorer_hash','contract_hash','capability_hash','schema_hash','dependency_lock_hash')
RESERVATIONS={'final_audit_model_calls':384,'external_model_calls':288,'comparison_actor_calls':384,'comparison_selector_calls':8,'model_calls':1064,
              'tokens':sum(item['tokens'] for item in protected_reservations(CampaignBudget()).values())}

def _hashes(identity):
    if set(identity)!=set(REQUIRED_HASHES):raise ValueError('complete exact frozen identity required')
    for value in identity.values():TypeAdapter(Digest).validate_python(value)


def _write_once(path,value):
    text=json.dumps(value,indent=2)+'\n'
    # Replacing the explicit unexecuted placeholder is permitted, never a frozen run.
    if path.exists():
        current=json.loads(path.read_text())
        if current.get('status')!='PENDING':
            if current==value:return current
            raise ValueError('immutable freeze already exists')
        temp=path.with_suffix('.pending.json')
        with open(temp,'x') as f:f.write(text)
        os.replace(temp,path)
    else:
        with open(path,'x') as f:f.write(text)
    return value


def freeze_core(directory,identity,*,accepted_policy_hash=None,accepted_policy_version=None,campaign_caps=None):
    directory=Path(directory);_hashes(identity)
    reservations={**RESERVATIONS,'tokens':sum(item['tokens'] for item in protected_reservations(campaign_caps or CampaignBudget()).values())}
    if (accepted_policy_hash is None)!=(accepted_policy_version is None):raise ValueError('accepted policy version and digest must be paired')
    if accepted_policy_hash:TypeAdapter(Digest).validate_python(accepted_policy_hash)
    final=load_manifest('final-audit',directory=directory)
    external=load_manifest('portability',directory=directory)
    value={'schema_version':'faultlab-freeze/v1','status':'FROZEN','created_at':utc_now().isoformat(),'identity':identity,'learned_arm':{'status':'ACCEPTED' if accepted_policy_hash else 'UNAVAILABLE','policy_hash':accepted_policy_hash,'policy_version':accepted_policy_version},'final_manifest_hash':final['manifest_hash'],'final_cases':8,'final_trials_per_arm_case':3,'external':{'status':'PENDING','manifest_hash':external['manifest_hash'],'adapter_hash':None},'reservations':reservations,'no_tuning_from_final_or_external':True,'execution_status':'NOT_RUN'}
    value['freeze_hash']=content_hash(value)
    path=directory/'freeze.json'
    if path.exists():
        previous=json.loads(path.read_text())
        if previous.get('status')=='FROZEN':
            if previous['identity']==identity and previous['learned_arm']==value['learned_arm'] and previous['final_manifest_hash']==value['final_manifest_hash'] and previous['reservations']==value['reservations']:return verify_freeze(directory)
            raise ValueError('immutable freeze already exists')
    return _write_once(path,value)


def verify_freeze(directory):
    directory=Path(directory);value=json.loads((directory/'freeze.json').read_text())
    if value.get('status')!='FROZEN':raise ValueError('core experiment freeze pending')
    if value['freeze_hash']!=content_hash({k:v for k,v in value.items() if k!='freeze_hash'}):raise ValueError('freeze digest mismatch')
    _hashes(value['identity'])
    if load_manifest('final-audit',directory=directory)['manifest_hash']!=value['final_manifest_hash']:raise ValueError('sealed manifest changed')
    return value


def freeze_external(directory,registration:AgentRegistration):
    directory=Path(directory);core=verify_freeze(directory)
    if registration.provenance_class!='external' or registration.dry_run_status!='PASSED' or not registration.budget_compatible:raise ValueError('independent compatible registration must pass before external freeze')
    if registration.contract_hash!=core['identity']['contract_hash'] or registration.capability_hash!=core['identity']['capability_hash'] or registration.oracle_hash!=core['identity']['scorer_hash']:raise ValueError('external contract, capabilities and fixed oracle must match frozen core')
    if core['learned_arm']['status']!='ACCEPTED':raise ValueError('external B0/L study requires an accepted learned policy')
    manifest=load_manifest('portability',directory=directory)
    manifest['external_identity']={'status':'FROZEN','registration_id':registration.registration_id,'source_hash':registration.source_hash,'adapter_hash':registration.adapter_hash,'configuration_hash':registration.configuration_hash}
    manifest['execution_authorized']=False # Freeze does not itself authorize provider spend.
    manifest['manifest_hash']=manifest_hash(manifest)
    value={'schema_version':'faultlab-external-freeze/v1','status':'FROZEN','created_at':utc_now().isoformat(),'core_freeze_hash':core['freeze_hash'],'manifest':manifest,'registration':registration.model_dump(mode='json'),'policy_hash':core['learned_arm']['policy_hash'],'execution_status':'NOT_RUN'}
    value['freeze_hash']=content_hash(value)
    return _write_once(directory/'external-freeze.json',value)

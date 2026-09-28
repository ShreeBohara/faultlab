"""Explicit immutable local experiment freeze. This command performs no runs."""
import argparse
from pathlib import Path
import shutil
from app.config import Settings
from app.contracts.models import Campaign, content_hash
from app.cli.stores import writable_store, OWNERSHIP_ERRORS, ownership_error
from app.lab.policies import PolicyRepository
from app.referee.freeze import freeze_core
from app.referee.manifests import AUDIT_DIR
from app.lab.configuration import file_hash, frozen_configuration


def freeze_campaign(store, settings, campaign_id):
    campaign=store.get_model('campaigns',campaign_id,Campaign)
    if campaign is None: raise ValueError('Unknown campaign')
    from app.lab.policies import require_ordinary_campaign
    require_ordinary_campaign(store,campaign_id)
    if campaign.state not in ('COMPLETED','NO_CHANGE','STOPPED'):
        raise ValueError('Stop or complete the campaign before freezing')
    config=store.get_record('configurations',campaign.configuration_hash)
    if not config or content_hash(config)!=campaign.configuration_hash:
        raise ValueError('Campaign configuration failed integrity validation')
    from app.lab.run_plans import validate_run_plan
    plan=validate_run_plan(store,settings,campaign)
    if plan is None and frozen_configuration(settings,campaign.caps,campaign.config_profile_id)!=config:
        raise ValueError('Current source or model settings differ from the recorded campaign')
    policies=PolicyRepository(store); baseline=policies.baseline()
    policy=policies.get(campaign.active_policy_version)
    if policy is None or policy.decision not in ('ACCEPTED','BASELINE'):
        raise ValueError('An immutable baseline or accepted policy is required')
    from app.lab.policies import imported_policy,IMPORTED_POLICY_REFUSAL
    if imported_policy(store,policy): raise ValueError(IMPORTED_POLICY_REFUSAL)
    identity={'baseline_policy_hash':baseline.policy_hash,
        'model_hash':content_hash({'models':config.get('models',{'actor':config['model']}),'settings':config.get('model_settings_by_role',{'actor':config['model_settings']})}),
        'prompt_hash':config['actor_prompt_hash'],'budget_hash':content_hash({'episode':config['episode_budget'],'campaign':config['campaign_budget']}),
        **{key:config[key] for key in ('adapter_hash','interpreter_hash','scorer_hash','contract_hash','capability_hash','dependency_lock_hash')},
        'schema_hash':file_hash(Path(__file__).resolve().parents[3]/'contracts/manifest.json')}
    directory=settings.artifact_path/'campaigns'/campaign_id/'audit'
    directory.mkdir(parents=True,exist_ok=True)
    for name in ('final-audit.json','portability.json'):
        target=directory/name
        if not target.exists(): shutil.copyfile(AUDIT_DIR/name,target)
        elif target.read_bytes()!=(AUDIT_DIR/name).read_bytes(): raise ValueError('Frozen manifest content changed')
    accepted=policy.decision=='ACCEPTED'
    result=freeze_core(directory,identity,accepted_policy_hash=policy.policy_hash if accepted else None,accepted_policy_version=policy.version if accepted else None,campaign_caps=campaign.caps)
    store.put_record('audit_freezes',campaign_id,{'campaign_id':campaign_id,'policy_hash':policy.policy_hash if accepted else None,
        'configuration_hash':campaign.configuration_hash,'manifest_hash':result['final_manifest_hash'],
        'freeze_hash':result['freeze_hash'],'path':str(directory/'freeze.json'),'learned_arm_available':accepted},immutable=True)
    return {'campaign_id':campaign_id,'status':'FROZEN','freeze_hash':result['freeze_hash'],'learned_arm_available':accepted,'path':str(directory/'freeze.json'),'execution_performed':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign',required=True)
    args=parser.parse_args()
    try:
        from app.cli.client import print_json
        settings=Settings.from_env()
        with writable_store(settings) as store:
            print_json(freeze_campaign(store,settings,args.campaign))
    except OWNERSHIP_ERRORS as error:
        parser.error(ownership_error(error)['message'])
    except (ValueError,OSError): parser.error('Freeze rejected: campaign must be complete with unchanged source/configuration and immutable policy. No execution started.')

if __name__=='__main__':main()

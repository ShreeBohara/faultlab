"""Trusted local bundle commands. Validation and playback never execute code or calls."""
import argparse
import json
from pathlib import Path
from app.config import Settings
from app.contracts.models import Campaign,CampaignBudget,RegressionCase,canonical_json,content_hash,new_id
from app.lab.storage import LabStore
from app.lab.configuration import frozen_configuration
from app.integrations.registry import AgentRegistry,freeze_target_configuration
from app.integrations.regression_runner import RegressionRunner,inspect_bundle
from app.cli.client import request,print_json


def current_configuration(settings):
    caps=CampaignBudget(model_calls=settings.faultlab_model_call_cap,tokens=settings.faultlab_token_cap,dollars=float(settings.faultlab_dollar_cap))
    return frozen_configuration(settings,caps,'live-v1' if settings.wandb_model else 'offline-v1')


def register(store,settings,agent):
    registry=AgentRegistry(store);current=current_configuration(settings)
    if agent=='smolagents':
        if not settings.wandb_model:raise ValueError('Configure the target model before native-agent registration')
        return registry.register_smolagents(freeze_target_configuration(current,settings.wandb_model))
    return registry.register_reference(current,internal_smoke=not bool(settings.wandb_model))


def import_for_execution(store,inspected,bundle_dir,campaign_id):
    """Persist validated data with explicit imported provenance, without activation."""
    from app.integrations.regression_runner import INVENTORY,_read
    from app.lab.regressions import validate_bundle
    bundle=inspected.bundle;policy=inspected.policy
    payloads={name:_read(Path(bundle_dir)/name).decode('utf-8') for name in INVENTORY}
    validate_bundle(bundle,payloads)
    previous=store.get_record('policies',policy.version)
    if previous and (previous.get('policy_hash')!=policy.policy_hash or previous.get('decision') not in ('BASELINE','ACCEPTED')):
        raise ValueError('Imported policy identity conflicts with local history')
    if not previous:store.put_record('policies',policy.version,policy,immutable=True)
    store.put_record('bundles',bundle.bundle_id,bundle,immutable=True)
    store.put_record('bundle_files',bundle.bundle_id,payloads,immutable=True)
    store.put_record('bundle_imports',bundle.bundle_id,{'bundle_id':bundle.bundle_id,'manifest_hash':bundle.manifest_hash,'source_configuration_hash':bundle.configuration_hash,'mode':'validated_data_import','source_evidence_verified_locally':False},immutable=True)
    lineage=json.loads(payloads['lineage.json'])
    counter=lineage['counterexample']
    case=RegressionCase(regression_id=new_id('regression'),campaign_id=campaign_id,counterexample_id=counter['counterexample_id'],target_invariant=bundle.target_invariant,
        first_failing_policy=policy.parent_version or policy.version,accepted_policy=policy.version if policy.decision=='ACCEPTED' else None,
        reduction_ref=counter['counterexample_id'] if lineage['reduction'] else None,
        diagnostic_ref=lineage['diagnostic']['diagnostic_id'] if lineage['diagnostic'] else None,
        challenge_ref=lineage['challenge']['challenge_id'] if lineage['challenge'] else None,bundle_id=bundle.bundle_id)
    store.put_record('regressions',case.regression_id,case,immutable=True)
    return case


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    for name in ('validate','playback','execute'):
        sub=commands.add_parser(name);sub.add_argument('--bundle',type=Path,required=True);sub.add_argument('--agent')
        if name=='execute':sub.add_argument('--profile',required=True);sub.add_argument('--execute-live',action='store_true')
    reg=commands.add_parser('register');reg.add_argument('--agent',choices=['reference','smolagents'],required=True)
    export=commands.add_parser('export');export.add_argument('--regression',required=True);export.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();settings=Settings.from_env();store=LabStore(settings.artifact_path/'lab.sqlite3')
    try:
        if args.command=='register':
            print_json(register(store,settings,args.agent).model_dump(mode='json'));return 0
        if args.command=='export':
            from app.lab.regressions import RegressionCompiler
            row=store.get_record('regressions',args.regression)
            if not row:raise ValueError('Unknown regression')
            if args.output.exists():raise ValueError('Export requires a new output directory')
            path=RegressionCompiler(store).export(row['bundle_id'],args.output)
            print_json({'manifest':str(path.resolve()),'execution_performed':False});return 0
        inspected=inspect_bundle(args.bundle)
        registry=AgentRegistry(store)
        registration=registry.get(args.agent) if args.agent else register(store,settings,'reference')
        target=store.get_record('configurations',registration.configuration_hash)
        fixed=RegressionRunner(store,registry)
        if args.command=='validate':
            print_json(fixed.validate(args.bundle,target,registration.registration_id).execution.model_dump(mode='json'))
        elif args.command=='playback':
            result=fixed.playback(args.bundle,target,registration.registration_id)
            print_json({'execution':result.model_dump(mode='json'),'recorded_trials':[t.model_dump(mode='json') for t in inspected.trial_results],'fresh':False})
        else:
            if not args.execute_live or not args.agent or args.profile!='sandbox-v1':raise ValueError('Explicit --execute-live, registered --agent and --profile sandbox-v1 required')
            settings.require_live()
            fixed.validate(args.bundle,target,registration.registration_id)
            if registration.model!=settings.wandb_model:raise ValueError('Registered target model differs from configured runtime')
            if inspected.policy.decision not in ('BASELINE','ACCEPTED'):raise ValueError('Fresh execution needs immutable baseline or accepted policy')
            c=request('POST','/api/campaigns',{'task_text':'Upgrade the authorized order to express shipping, then record one truthful confirmation.','order_id':'order-regression','mode':'baseline','config_profile_id':'live-v1'})
            case=import_for_execution(store,inspected,args.bundle,c['campaign_id'])
            print_json(request('POST',f'/api/regressions/{case.regression_id}/execute',{'agent_registration_id':registration.registration_id,'execution_profile_id':args.profile,'policy_version':inspected.policy.version,'execute_live':True}))
        return 0
    except Exception as error:
        # Avoid echoing raw untrusted bundle fields or local credentials.
        print_json({'status':'REJECTED','error_type':type(error).__name__,'message':'Bundle, registration or configured execution did not satisfy the trusted runner contract. Inspect local setup and frozen identities.'})
        return 1
    finally:store.close()

if __name__=='__main__':raise SystemExit(main())

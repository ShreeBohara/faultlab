"""Trusted local bundle commands. Validation and playback never execute code or calls."""
import argparse
import json
from pathlib import Path
from app.config import Settings
from app.contracts.models import Campaign,CampaignBudget,RegressionCase,Counterexample,FaultSpec,ReductionResult,DiagnosticResult,ChallengeResult,TrialResult,PolicyVersion,canonical_json,content_hash,new_id
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
    from app.integrations.regression_runner import _read
    from app.lab.regressions import validate_bundle,artifact_kind,manifest_payload
    bundle=inspected.bundle;policy=inspected.policy
    payloads={entry.path:_read(Path(bundle_dir)/entry.path).decode('utf-8') for entry in bundle.files}
    validate_bundle(bundle,payloads)
    previous=store.get_record('policies',policy.version)
    if previous and (previous.get('policy_hash')!=policy.policy_hash or previous.get('content')!=policy.content.model_dump(mode='json')):
        raise ValueError('Imported policy identity conflicts with local history')
    if not previous:store.put_record('policies',policy.version,policy,immutable=True)
    store.put_record('bundles',bundle.bundle_id,manifest_payload(bundle),immutable=True)
    store.put_record('bundle_files',bundle.bundle_id,payloads,immutable=True)
    store.put_record('bundle_imports',bundle.bundle_id,{'bundle_id':bundle.bundle_id,'manifest_hash':bundle.manifest_hash,'source_configuration_hash':bundle.configuration_hash,'mode':'validated_data_import','source_evidence_verified_locally':False},immutable=True)
    lineage=json.loads(payloads['lineage.json'])
    counter=lineage['counterexample']
    kind=artifact_kind(bundle,policy)
    case=RegressionCase(regression_id=new_id('regression'),artifact_kind=kind,campaign_id=campaign_id,counterexample_id=counter['counterexample_id'],target_invariant=bundle.target_invariant,
        first_failing_policy=policy.version,accepted_policy=policy.version if kind=='accepted_policy_bundle' else None,
        reduction_ref=counter['counterexample_id'] if lineage['reduction'] else None,
        diagnostic_ref=lineage['diagnostic']['diagnostic_id'] if lineage['diagnostic'] else None,
        challenge_ref=lineage['challenge']['challenge_id'] if lineage['challenge'] else None,bundle_id=bundle.bundle_id)
    store.put_record('regressions',case.regression_id,case,immutable=True)
    return case


def compile_incident(store,settings,counterexample_id,*,policy_version=None,challenge_id=None):
    """Turn an existing reproduced incident into data, without running a trial."""
    from app.lab.regressions import RegressionCompiler
    counter=store.get_model('counterexamples',counterexample_id,Counterexample)
    if counter is None or not counter.reproduced: raise ValueError('An existing reproduced counterexample is required')
    campaign=store.get_model('campaigns',counter.campaign_id,Campaign)
    source=store.get_record('episodes',counter.source_episode_id)
    if campaign is None or source is None or source['split']!='development': raise ValueError('Public development source required')
    policy=store.get_model('policies',policy_version or source['policy_version'],PolicyVersion)
    recipe_record=store.get_record('counterexample_recipes',counterexample_id)
    if not recipe_record: raise ValueError('Persisted source recipe required')
    recipe=FaultSpec.model_validate_json(canonical_json(recipe_record['source_recipe']))
    reduction=store.get_model('reductions',counterexample_id,ReductionResult)
    retained=(store.get_record('retained_recipes',counterexample_id) or {}).get('retained_recipe')
    retained=FaultSpec.model_validate_json(canonical_json(retained)) if retained else None
    if reduction and reduction.status in ('FLAKY','INCOMPLETE'): retained=None
    ids={counter.source_episode_id,*counter.reproduction_trial_ids}
    if reduction: ids.update(t for attempt in reduction.attempts for t in attempt.trial_ids)
    diagnostic=next((DiagnosticResult.model_validate_json(canonical_json(d)) for d in store.list_records('diagnostics') if d.get('counterexample_id')==counterexample_id),None)
    for intervention in store.list_records('interventions'):
        if intervention.get('counterexample_id')==counterexample_id: ids.update(t for pair in intervention['trial_pairs'] for t in pair)
    challenge=store.get_model('challenges',challenge_id,ChallengeResult) if challenge_id else None
    if challenge_id:
        owner=store.get_record('challenge_campaigns',challenge_id)
        if not challenge or not policy or not owner or owner['campaign_id']!=campaign.campaign_id or challenge.candidate_hash!=policy.policy_hash or counter.source_episode_id not in policy.development_episode_ids:
            raise ValueError('Challenge and candidate must belong to this source')
        ids.update(t for pair in challenge.trial_pairs for t in pair)
        batch=store.get_record('evaluations',challenge.source_validation_ref) or {}
        ids.update(t['episode_id'] for t in batch.get('trials',[]))
    elif policy_version and policy_version!=source['policy_version']:
        raise ValueError('Source incident uses the original failing policy; select a challenge to export a tested candidate')
    trials=[store.get_model('trials',ident,TrialResult) for ident in sorted(ids)]
    return RegressionCompiler(store,secrets=(settings.wandb_api_key,settings.typesafe_api_key,settings.faultlab_control_token)).compile(
        campaign,counter,policy,recipe,retained,trials,diagnostic=diagnostic,challenge=challenge,reduction=reduction,
        stage='failed_challenge' if challenge else 'reduced_source',artifact_kind='candidate_comparison' if challenge else 'incident_fixture')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    for name in ('validate','playback','execute'):
        sub=commands.add_parser(name);sub.add_argument('--bundle',type=Path,required=True);sub.add_argument('--agent')
        if name=='execute':sub.add_argument('--profile',required=True);sub.add_argument('--execute-live',action='store_true')
    reg=commands.add_parser('register');reg.add_argument('--agent',choices=['reference','smolagents'],required=True)
    export=commands.add_parser('export');target=export.add_mutually_exclusive_group(required=True)
    target.add_argument('--regression');target.add_argument('--counterexample')
    export.add_argument('--policy');export.add_argument('--challenge');export.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();settings=Settings.from_env();store=LabStore(settings.artifact_path/'lab.sqlite3')
    try:
        if args.command=='register':
            print_json(register(store,settings,args.agent).model_dump(mode='json'));return 0
        if args.command=='export':
            from app.lab.regressions import RegressionCompiler
            if args.output.exists():raise ValueError('Export requires a new output directory')
            if args.counterexample:
                bundle=compile_incident(store,settings,args.counterexample,policy_version=args.policy,challenge_id=args.challenge)
                row=next(r for r in store.list_records('regressions') if r['bundle_id']==bundle.bundle_id)
            else:
                if args.policy or args.challenge: raise ValueError('Policy/challenge options apply to counterexample export')
                row=store.get_record('regressions',args.regression)
                if not row:raise ValueError('Unknown regression')
            path=RegressionCompiler(store,secrets=(settings.wandb_api_key,settings.typesafe_api_key,settings.faultlab_control_token)).export(row['bundle_id'],args.output)
            print_json({'manifest':str(path.resolve()),'regression_id':row['regression_id'],'artifact_kind':row.get('artifact_kind','incident_fixture'),'execution_performed':False});return 0
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
            from app.lab.regressions import runnable_policy
            runnable_policy(inspected.bundle,inspected.policy)
            recording=json.loads((args.bundle/'evidence.json').read_text()) if (args.bundle/'evidence.json').is_file() else {}
            task=recording.get('execution_task') or {}
            c=request('POST','/api/campaigns',{'task_text':task.get('task_text') or 'Upgrade the authorized order to express shipping, then record one truthful confirmation.','order_id':task.get('order_id') or 'order-regression','mode':'baseline','config_profile_id':'live-v1'})
            case=import_for_execution(store,inspected,args.bundle,c['campaign_id'])
            print_json(request('POST',f'/api/regressions/{case.regression_id}/execute',{'agent_registration_id':registration.registration_id,'execution_profile_id':args.profile,'policy_version':inspected.policy.version,'execute_live':True}))
        return 0
    except Exception as error:
        # Avoid echoing raw untrusted bundle fields or local credentials.
        print_json({'status':'REJECTED','error_type':type(error).__name__,'message':'Bundle, registration or configured execution did not satisfy the trusted runner contract. Inspect local setup and frozen identities.'})
        return 1
    finally:store.close()

if __name__=='__main__':raise SystemExit(main())

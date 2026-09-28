"""Trusted local bundle commands. Validation and playback never execute code or calls."""
import argparse
import json
import errno
from pathlib import Path
import httpx
from app.config import Settings
from app.contracts.models import Campaign,Counterexample,FaultSpec,ReductionResult,DiagnosticResult,ChallengeResult,TrialResult,PolicyVersion,canonical_json
from app.cli.stores import (writable_store, saved_store, owned_store,
                            expected_store_identity, OWNERSHIP_ERRORS, ownership_error)
from app.integrations.registry import AgentRegistry
from app.integrations.regression_runner import RegressionRunner,inspect_bundle
from app.cli.client import request,print_json


def current_configuration(settings):
    from app.lab.operator_actions import current_configuration as freeze_configuration
    return freeze_configuration(settings)


def register(store,settings,agent):
    from app.lab.operator_actions import register_agent
    return register_agent(store,settings,agent)


def _connection_refused(error):
    pending,seen=[error],set()
    while pending:
        current=pending.pop()
        if current is None or id(current) in seen:continue
        seen.add(id(current))
        if isinstance(current,OSError) and current.errno==errno.ECONNREFUSED:return True
        pending.extend((current.__cause__,current.__context__))
    return False


def register_remote_or_offline(settings,agent):
    if settings.faultlab_read_only:
        from app.lab.storage import ReadOnlyStore
        raise ReadOnlyStore()
    try:
        return request('POST','/api/agent-registrations',{
            'expected_store_identity':expected_store_identity(settings),'agent':agent})
    except httpx.ConnectError as error:
        # A responding backend owns admission. Never fall back after rejection,
        # timeout, a reset, or an ambiguous transport error.
        if not _connection_refused(error):raise
        with writable_store(settings) as store:
            return register(store,settings,agent).model_dump(mode='json')


def import_for_execution(store,inspected,bundle_dir,campaign_id):
    """Persist validated data with explicit imported provenance, without activation."""
    from app.integrations.regression_runner import _read
    from app.lab.operator_actions import import_bundle
    payloads={entry.path:_read(Path(bundle_dir)/entry.path).decode('utf-8') for entry in inspected.bundle.files}
    return import_bundle(store,inspected,payloads,campaign_id)


def inspect_locally(settings,args,inspected):
    """Reuse fixed validation against an ephemeral registry, never saved history."""
    with owned_store(':memory:') as scratch:
        if args.agent:
            with saved_store(settings) as saved:
                registration=AgentRegistry(saved).get(args.agent)
                target=saved.get_record('configurations',registration.configuration_hash)
            scratch.put_record('configurations',registration.configuration_hash,target,immutable=True)
            scratch.put_record('agent_registrations',registration.registration_id,registration,immutable=True)
        else:
            registration=register(scratch,settings,'reference')
            target=scratch.get_record('configurations',registration.configuration_hash)
        fixed=RegressionRunner(scratch,AgentRegistry(scratch))
        if args.command=='validate':
            return fixed.validate(args.bundle,target,registration.registration_id).execution.model_dump(mode='json')
        result=fixed.playback(args.bundle,target,registration.registration_id)
        return {'execution':result.model_dump(mode='json'),'recorded_trials':[t.model_dump(mode='json') for t in inspected.trial_results],'fresh':False}


def execute_remote(settings,args,inspected):
    """The owning backend imports and queues; the CLI never opens its database."""
    if not args.execute_live or not args.agent or args.profile!='sandbox-v1':
        raise ValueError('Explicit --execute-live, registered --agent and --profile sandbox-v1 required')
    if settings.faultlab_read_only:
        from app.lab.storage import ReadOnlyStore
        raise ReadOnlyStore()
    from app.integrations.regression_runner import _read
    from app.lab.operator_actions import ImportExecutionRequest,MAX_UPLOAD_BYTES
    from app.lab.regressions import runnable_policy,validate_bundle
    runnable_policy(inspected.bundle,inspected.policy)
    payloads={entry.path:_read(args.bundle/entry.path).decode('utf-8') for entry in inspected.bundle.files}
    validate_bundle(inspected.bundle,payloads)
    body=ImportExecutionRequest(
        expected_store_identity=expected_store_identity(settings),
        manifest=_read(args.bundle/'manifest.json').decode('utf-8'),files=payloads,
        agent_registration_id=args.agent,execution_profile_id=args.profile,execute_live=True).model_dump(mode='json')
    if len(json.dumps(body,ensure_ascii=False).encode('utf-8'))>MAX_UPLOAD_BYTES:
        raise ValueError('Bundle upload exceeds the transport bound')
    return request('POST','/api/regressions/import-and-execute',body)


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
    args=parser.parse_args()
    try:
        settings=Settings.from_env()
        if args.command=='register':
            print_json(register_remote_or_offline(settings,args.agent))
            return 0
        if args.command=='export':
            from app.lab.regressions import RegressionCompiler
            if args.output.exists():raise ValueError('Export requires a new output directory')
            with (writable_store(settings) if args.counterexample else saved_store(settings)) as store:
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
        if args.command in ('validate','playback'):
            print_json(inspect_locally(settings,args,inspected))
        else:
            print_json(execute_remote(settings,args,inspected))
        return 0
    except OWNERSHIP_ERRORS as error:
        print_json(ownership_error(error));return 1
    except Exception as error:
        # Avoid echoing raw untrusted bundle fields or local credentials.
        print_json({'status':'REJECTED','error_type':type(error).__name__,'message':'Bundle, registration or configured execution did not satisfy the trusted runner contract. Inspect local setup and frozen identities.'})
        return 1

if __name__=='__main__':raise SystemExit(main())

"""Safe development data and trusted static harness exports; no generated code."""
from hashlib import sha256
from pathlib import Path
import json
from app.contracts.models import RegressionBundle,RegressionCase,FileEntry,EpisodeBudget,FaultSpec,content_hash,canonical_json,new_id
from app.lab.configuration import ROOT,file_hash
from app.lab.exports import development_recording
from app.telemetry.safety import public_json

MAX_BUNDLE_FILE=8*1024*1024
MAX_BUNDLE_BYTES=16*1024*1024


def manifest_payload(bundle):
    """Retain the exact v1 manifest shape when reading a pre-kind archive."""
    value=bundle.model_dump(mode='json')
    if 'artifact_kind' not in bundle.model_fields_set: value.pop('artifact_kind',None)
    return value


def artifact_kind(bundle,policy):
    if 'artifact_kind' in bundle.model_fields_set: return bundle.artifact_kind
    return 'accepted_policy_bundle' if policy.decision=='ACCEPTED' else 'incident_fixture' if policy.decision=='BASELINE' else 'candidate_comparison'


def runnable_policy(bundle,policy):
    kind=artifact_kind(bundle,policy)
    if policy.content is None or content_hash(policy.content)!=bundle.policy_hash or policy.policy_hash!=bundle.policy_hash:
        raise ValueError('Fresh execution requires the exact immutable bundled policy')
    if kind=='accepted_policy_bundle' and policy.decision!='ACCEPTED':
        raise ValueError('An accepted-policy bundle requires an accepted policy')
    if policy.decision not in ('BASELINE','ACCEPTED','REJECTED','INCOMPLETE','NO_CHANGE'):
        raise ValueError('Fresh execution requires a completed policy decision')
    return kind

class RegressionCompiler:
    def __init__(self,store,*,secrets=()): self.store,self.secrets=store,secrets
    def compile(self,campaign,counter,policy,source_recipe,retained_recipe,trials,*,diagnostic=None,challenge=None,reduction=None,stage=None,artifact_kind=None):
        configuration=self.store.get_record('configurations',campaign.configuration_hash)
        if not configuration: raise ValueError('Frozen source configuration required')
        if policy.content is None or content_hash(policy.content)!=policy.policy_hash: raise ValueError('Valid immutable policy required')
        if counter.campaign_id!=campaign.campaign_id or counter.configuration_hash!=campaign.configuration_hash: raise ValueError('Source belongs to another campaign configuration')
        kind=artifact_kind or ('accepted_policy_bundle' if policy.decision=='ACCEPTED' else 'incident_fixture' if policy.decision=='BASELINE' else 'candidate_comparison')
        if kind=='accepted_policy_bundle' and policy.decision!='ACCEPTED': raise ValueError('Acceptance must come from a recorded policy decision')
        if stage and not counter.reproduced: raise ValueError('A reproduced source incident is required')
        development=[]
        seen=set()
        for trial in trials:
            if trial is None or trial.episode_id in seen: continue
            episode=self.store.get_record('episodes',trial.episode_id)
            if episode and episode.get('campaign_id')==campaign.campaign_id and episode['split']=='development' and episode['experiment_purpose'] not in ('selection_comparison','diagnostic_profile'):
                development.append(trial); seen.add(trial.episode_id)
        original_source=source_recipe; original_retained=retained_recipe
        target=counter.target_invariant; execution_source=counter.source_episode_id
        # A challenge fixture must rerun the fault that actually broke the
        # candidate, not the original recipe on which it already passed.
        failed=self.store.get_record('challenge_counterexamples',policy.version) if stage=='failed_challenge' else None
        if failed:
            if failed.get('campaign_id')!=campaign.campaign_id or failed.get('candidate_hash')!=policy.policy_hash: raise ValueError('Challenge identity mismatch')
            failing=[t for t in development if t.episode_id in failed['trial_ids'] and t.failed_checks and t.policy_hash==policy.policy_hash]
            if not failing: raise ValueError('Recorded failed challenge trial required')
            execution_source=failing[0].episode_id
            target=sorted(failing[0].failed_checks,key=lambda x:int(x[1:]))[0]
            source_recipe=FaultSpec.model_validate_json(canonical_json(failed['recipe'])); retained_recipe=None
        # Shared static harness may be installed after independent core implementation.
        harness=ROOT/'backend/app/integrations/templates/test_regression.py'
        if not harness.is_file(): raise ValueError('Trusted fixed regression harness is not installed')
        payloads={'policy.json':canonical_json(policy),'configuration.json':canonical_json(configuration),'source-recipe.json':canonical_json(source_recipe),'retained-recipe.json':canonical_json(retained_recipe),'trials.json':canonical_json(development),'lineage.json':canonical_json({'counterexample':counter,'diagnostic':diagnostic,'challenge':challenge,'reduction':reduction}),'harness/test_regression.py':harness.read_text()}
        source_inputs=self.store.get_record('private_episode_inputs',execution_source) or self.store.get_record('counterexample_recipes',counter.counterexample_id) or {}
        fixture_id=source_inputs.get('fixture_id')
        if fixture_id not in ('standard-v1','history-v1'): raise ValueError('Persisted original source fixture is required for export')
        evidence=development_recording(self.store,campaign.campaign_id,episode_ids=seen|{counter.source_episode_id},secrets=self.secrets)
        intent=source_inputs.get('intent') or {}
        evidence.update({'artifact_kind':kind,'stage':stage or 'recorded_regression','source_episode_id':counter.source_episode_id,'execution_episode_id':execution_source,
            'execution_task':{'task_text':intent.get('task_text',getattr(campaign,'task_text',None)),'order_id':intent.get('order_id',getattr(campaign,'order_id',None))},
            'initial_state':{'fixture_id':fixture_id,'initial_order_version':4 if fixture_id=='history-v1' else 1,'shipping':'standard','existing_operations':0,'existing_notifications':0},
            'original_source_recipe':original_source.model_dump(mode='json'),
            'original_retained_recipe':original_retained.model_dump(mode='json') if original_retained else None,
            'instructions':'Validate and inspect with the installed runner. Fresh execution runs three new trials of the exact bundled policy and fault. Failure reproduction is not policy acceptance.'})
        evidence=public_json(evidence,secrets=self.secrets,max_bytes=8*1024*1024)
        payloads['evidence.json']=canonical_json(evidence)
        if any(len(value.encode())>MAX_BUNDLE_FILE for value in payloads.values()) or sum(len(value.encode()) for value in payloads.values())>MAX_BUNDLE_BYTES:
            raise ValueError('Complete incident exceeds the reviewed archive size bound; no truncated bundle was saved')
        entries=[FileEntry(path=name,sha256=sha256(value.encode()).hexdigest(),size_bytes=len(value.encode())) for name,value in sorted(payloads.items())]
        bundle=RegressionBundle(bundle_id=new_id('bundle'),artifact_kind=kind,fixture_id=fixture_id,manifest_hash='0'*64,files=entries,harness_version='faultlab-runner-v2',harness_hash=file_hash(harness),source_recipe=source_recipe,retained_recipe=retained_recipe,contract_hash=configuration['contract_hash'],capability_hash=configuration['capability_hash'],configuration_hash=campaign.configuration_hash,scorer_hash=configuration['scorer_hash'],interpreter_hash=configuration['interpreter_hash'],policy_hash=policy.policy_hash,schema_hash=file_hash(ROOT/'contracts/RegressionBundle.schema.json'),dependency_lock_hash=configuration['dependency_lock_hash'],target_invariant=target,source_refs=list(dict.fromkeys([counter.source_episode_id,execution_source,counter.counterexample_id]+([diagnostic.diagnostic_id] if diagnostic else [])+([challenge.challenge_id] if challenge else []))),trial_results=development,registration_requirements=['Reviewed local registration','Same task/tools/oracle/policy-hook semantics','Source provenance retained; target settings frozen independently'],execution_profile_id='sandbox-v1',caps=EpisodeBudget(),setup_instructions=f'{kind}: use the installed FaultLab runner to inspect or validate. Fresh sandbox execution is an explicit bounded action, not evidence of an accepted repair.')
        bundle.manifest_hash=content_hash({k:v for k,v in manifest_payload(bundle).items() if k!='manifest_hash'})
        validate_bundle(bundle,payloads)
        self.store.put_record('bundles',bundle.bundle_id,bundle,immutable=True)
        self.store.put_record('bundle_files',bundle.bundle_id,payloads,immutable=True)
        first=(self.store.get_record('episodes',execution_source) or {}).get('policy_version',policy.version)
        regression=RegressionCase(regression_id=new_id('regression'),artifact_kind=kind,campaign_id=campaign.campaign_id,counterexample_id=counter.counterexample_id,target_invariant=target,first_failing_policy=first,accepted_policy=policy.version if kind=='accepted_policy_bundle' else None,reduction_ref=counter.counterexample_id if reduction else None,diagnostic_ref=diagnostic.diagnostic_id if diagnostic else None,challenge_ref=challenge.challenge_id if challenge else None,bundle_id=bundle.bundle_id)
        self.store.put_record('regressions',regression.regression_id,regression,immutable=True)
        return bundle

    def export(self,bundle_id,directory):
        bundle=self.store.get_model('bundles',bundle_id,RegressionBundle)
        if bundle is None: raise KeyError(bundle_id)
        payloads=self.store.get_record('bundle_files',bundle_id)
        validate_bundle(bundle,payloads)
        for name,value in payloads.items():
            if name.endswith('.json'): public_json(json.loads(value),secrets=self.secrets,max_bytes=8*1024*1024)
        directory=Path(directory)
        if directory.is_symlink(): raise ValueError('Symlink export directory rejected')
        directory.mkdir(parents=True,exist_ok=True)
        for entry in bundle.files:
            path=directory/entry.path
            for parent in [path,*path.parents]:
                if parent==directory.parent: break
                if parent.is_symlink(): raise ValueError('Symlink artifact path rejected')
            path.parent.mkdir(parents=True,exist_ok=True); path.write_text(payloads[entry.path])
        (directory/'manifest.json').write_text(json.dumps(manifest_payload(bundle),indent=2))
        return directory/'manifest.json'


def validate_bundle(bundle,payloads):
    checked=RegressionBundle.model_validate_json(canonical_json(manifest_payload(bundle)))
    expected=content_hash({k:v for k,v in manifest_payload(checked).items() if k!='manifest_hash'})
    if expected!=checked.manifest_hash: raise ValueError('Manifest digest mismatch')
    if set(payloads)!={e.path for e in checked.files}: raise ValueError('Artifact inventory mismatch')
    if any(len(value.encode())>MAX_BUNDLE_FILE for value in payloads.values()) or sum(len(value.encode()) for value in payloads.values())>MAX_BUNDLE_BYTES:
        raise ValueError('Artifact size bound exceeded')
    for entry in checked.files:
        content=payloads[entry.path].encode()
        if len(content)!=entry.size_bytes or sha256(content).hexdigest()!=entry.sha256: raise ValueError('Artifact digest mismatch')
    policy=json.loads(payloads['policy.json'])
    if policy.get('policy_hash')!=checked.policy_hash or content_hash(policy.get('content'))!=checked.policy_hash: raise ValueError('Policy hash mismatch')
    if content_hash(json.loads(payloads['configuration.json']))!=checked.configuration_hash: raise ValueError('Source configuration digest mismatch')
    return checked

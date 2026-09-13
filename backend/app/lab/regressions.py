"""Safe development data and trusted static harness exports; no generated code."""
from hashlib import sha256
from pathlib import Path
import json
from app.contracts.models import RegressionBundle,RegressionCase,FileEntry,EpisodeBudget,RecoveryPolicy,content_hash,canonical_json,new_id
from app.lab.configuration import ROOT,file_hash

class RegressionCompiler:
    def __init__(self,store): self.store=store
    def compile(self,campaign,counter,policy,source_recipe,retained_recipe,trials,*,diagnostic=None,challenge=None,reduction=None):
        configuration=self.store.get_record('configurations',campaign.configuration_hash)
        if not configuration: raise ValueError('Frozen source configuration required')
        if policy.content is None or content_hash(policy.content)!=policy.policy_hash: raise ValueError('Valid immutable policy required')
        development=[]
        for trial in trials:
            episode=self.store.get_record('episodes',trial.episode_id)
            if episode and episode['split']=='development' and episode['experiment_purpose'] not in ('selection_comparison','diagnostic_profile'):
                development.append(trial)
        # Shared static harness may be installed after independent core implementation.
        harness=ROOT/'backend/app/integrations/templates/test_regression.py'
        if not harness.is_file(): raise ValueError('Trusted fixed regression harness is not installed')
        payloads={'policy.json':canonical_json(policy),'configuration.json':canonical_json(configuration),'source-recipe.json':canonical_json(source_recipe),'retained-recipe.json':canonical_json(retained_recipe),'trials.json':canonical_json(development),'lineage.json':canonical_json({'counterexample':counter,'diagnostic':diagnostic,'challenge':challenge,'reduction':reduction}),'harness/test_regression.py':harness.read_text()}
        entries=[FileEntry(path=name,sha256=sha256(value.encode()).hexdigest(),size_bytes=len(value.encode())) for name,value in sorted(payloads.items())]
        source_inputs=self.store.get_record('private_episode_inputs',counter.source_episode_id) or self.store.get_record('counterexample_recipes',counter.counterexample_id) or {}
        fixture_id=source_inputs.get('fixture_id')
        if fixture_id not in ('standard-v1','history-v1'): raise ValueError('Persisted original source fixture is required for export')
        bundle=RegressionBundle(bundle_id=new_id('bundle'),fixture_id=fixture_id,manifest_hash='0'*64,files=entries,harness_version='faultlab-runner-v1',harness_hash=file_hash(harness),source_recipe=source_recipe,retained_recipe=retained_recipe,contract_hash=configuration['contract_hash'],capability_hash=configuration['capability_hash'],configuration_hash=campaign.configuration_hash,scorer_hash=configuration['scorer_hash'],interpreter_hash=configuration['interpreter_hash'],policy_hash=policy.policy_hash,schema_hash=file_hash(ROOT/'contracts/RegressionBundle.schema.json'),dependency_lock_hash=configuration['dependency_lock_hash'],target_invariant=counter.target_invariant,source_refs=[counter.source_episode_id,counter.counterexample_id]+([diagnostic.diagnostic_id] if diagnostic else [])+([challenge.challenge_id] if challenge else []),trial_results=development,registration_requirements=['Reviewed local registration','Same task/tools/oracle/policy-hook semantics','Source provenance retained; target settings frozen independently'],execution_profile_id='sandbox-v1',caps=EpisodeBudget(),setup_instructions='Use the locally installed fixed FaultLab runner to validate or inspect this bundle. Fresh sandbox execution is a separate explicit bounded action.')
        bundle.manifest_hash=content_hash({k:v for k,v in bundle.model_dump(mode='json').items() if k!='manifest_hash'})
        validate_bundle(bundle,payloads)
        self.store.put_record('bundles',bundle.bundle_id,bundle,immutable=True)
        self.store.put_record('bundle_files',bundle.bundle_id,payloads,immutable=True)
        regression=RegressionCase(regression_id=new_id('regression'),campaign_id=campaign.campaign_id,counterexample_id=counter.counterexample_id,target_invariant=counter.target_invariant,first_failing_policy=policy.parent_version or policy.version,accepted_policy=policy.version if policy.decision=='ACCEPTED' else None,reduction_ref=counter.counterexample_id if reduction else None,diagnostic_ref=diagnostic.diagnostic_id if diagnostic else None,challenge_ref=challenge.challenge_id if challenge else None,bundle_id=bundle.bundle_id)
        self.store.put_record('regressions',regression.regression_id,regression,immutable=True)
        return bundle

    def export(self,bundle_id,directory):
        bundle=self.store.get_model('bundles',bundle_id,RegressionBundle)
        if bundle is None: raise KeyError(bundle_id)
        payloads=self.store.get_record('bundle_files',bundle_id)
        validate_bundle(bundle,payloads)
        directory=Path(directory)
        if directory.is_symlink(): raise ValueError('Symlink export directory rejected')
        directory.mkdir(parents=True,exist_ok=True)
        for entry in bundle.files:
            path=directory/entry.path
            for parent in [path,*path.parents]:
                if parent==directory.parent: break
                if parent.is_symlink(): raise ValueError('Symlink artifact path rejected')
            path.parent.mkdir(parents=True,exist_ok=True); path.write_text(payloads[entry.path])
        (directory/'manifest.json').write_text(bundle.model_dump_json(indent=2))
        return directory/'manifest.json'


def validate_bundle(bundle,payloads):
    checked=RegressionBundle.model_validate_json(bundle.model_dump_json())
    expected=content_hash({k:v for k,v in checked.model_dump(mode='json').items() if k!='manifest_hash'})
    if expected!=checked.manifest_hash: raise ValueError('Manifest digest mismatch')
    if set(payloads)!={e.path for e in checked.files}: raise ValueError('Artifact inventory mismatch')
    for entry in checked.files:
        content=payloads[entry.path].encode()
        if len(content)!=entry.size_bytes or sha256(content).hexdigest()!=entry.sha256: raise ValueError('Artifact digest mismatch')
    policy=json.loads(payloads['policy.json'])
    if policy.get('policy_hash')!=checked.policy_hash or content_hash(policy.get('content'))!=checked.policy_hash: raise ValueError('Policy hash mismatch')
    if content_hash(json.loads(payloads['configuration.json']))!=checked.configuration_hash: raise ValueError('Source configuration digest mismatch')
    return checked

import json
from pathlib import Path
import pytest
from app.config import Settings
from app.contracts.models import CampaignRequest,Counterexample,FaultSpec,content_hash
from app.lab.coordinator import LabCoordinator
from app.lab.regressions import RegressionCompiler,validate_bundle
from app.integrations.regression_runner import inspect_bundle


def compile_fixture(tmp_path):
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path/'lab')))
    campaign=c.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='baseline'))
    counter=Counterexample(counterexample_id='counter',campaign_id=campaign.campaign_id,agent_registration_id='orders-v1',source_episode_id='source',target_invariant='C3',scenario_hash=content_hash('s'),configuration_hash=campaign.configuration_hash,report_ref='source',verdict_ref='verdict')
    c.store.put_record('private_episode_inputs','source',{'fixture_id':'standard-v1'})
    recipe=FaultSpec(seed=1,primitives=[])
    compiler=RegressionCompiler(c.store)
    bundle=compiler.compile(campaign,counter,c.policies.baseline(),recipe,recipe,[])
    return c,compiler,bundle

def test_canonical_bundle_roundtrip_trusted_harness_zero_effects(tmp_path):
    c,compiler,bundle=compile_fixture(tmp_path)
    path=compiler.export(bundle.bundle_id,tmp_path/'bundle')
    inspected=inspect_bundle(path.parent)
    assert inspected.bundle==bundle
    assert not c.store.list_records('episodes')
    assert all(not item.path.startswith('/') and '..' not in item.path for item in bundle.files)

def test_tamper_and_symlink_rejected(tmp_path):
    c,compiler,bundle=compile_fixture(tmp_path)
    path=compiler.export(bundle.bundle_id,tmp_path/'bundle')
    (path.parent/'policy.json').write_text('{}')
    with pytest.raises(ValueError): inspect_bundle(path.parent)
    payloads=c.store.get_record('bundle_files',bundle.bundle_id); payloads['policy.json']='{}'
    with pytest.raises(ValueError): validate_bundle(bundle,payloads)
    link=tmp_path/'linked'; link.symlink_to(tmp_path/'bundle',target_is_directory=True)
    with pytest.raises(ValueError): compiler.export(bundle.bundle_id,link)

def test_manifest_harness_digest_not_executable_authority(tmp_path):
    c,compiler,bundle=compile_fixture(tmp_path)
    bundle.harness_hash='0'*64
    with pytest.raises(ValueError): validate_bundle(bundle,c.store.get_record('bundle_files',bundle.bundle_id))

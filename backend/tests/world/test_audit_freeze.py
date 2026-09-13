import json
from pathlib import Path
import shutil
import pytest

@pytest.fixture
def audit_dir(tmp_path):
    from app.referee.manifests import AUDIT_DIR
    for path in AUDIT_DIR.glob('*.json'):shutil.copy(path,tmp_path/path.name)
    return tmp_path

def test_core_freeze_is_independent_of_external_and_missing_learned_policy(audit_dir):
    from app.referee.freeze import freeze_core,REQUIRED_HASHES,verify_freeze
    identity={name:'a'*64 for name in REQUIRED_HASHES}
    result=freeze_core(audit_dir,identity)
    assert result['status']=='FROZEN' and result['learned_arm']['status']=='UNAVAILABLE'
    assert result['external']['status']=='PENDING'
    assert result['reservations']['model_calls']==1064
    assert verify_freeze(audit_dir)['freeze_hash']==result['freeze_hash']
    with pytest.raises(ValueError):freeze_core(audit_dir,identity|{'model_hash':'b'*64})

def test_incomplete_identity_and_changed_manifest_rejected(audit_dir):
    from app.referee.freeze import freeze_core,REQUIRED_HASHES,verify_freeze
    with pytest.raises(ValueError):freeze_core(audit_dir,{})
    freeze_core(audit_dir,{name:'a'*64 for name in REQUIRED_HASHES})
    path=audit_dir/'final-audit.json';obj=json.loads(path.read_text());obj['trials_per_case']=1;path.write_text(json.dumps(obj))
    with pytest.raises(ValueError):verify_freeze(audit_dir)

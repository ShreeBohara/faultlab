"""The simulator's server entry point and its identity (September 28 PM decision).

A hardening change had made ``app.simulator.main`` build its uvicorn entry point lazily, so
that importing the module created no control-capability file. That changed the simulator
service identity (3ce5bcd2… → f70c8fb1…) and therefore the contract identity (6f9d7783… →
1099eda7…) that exported regression bundles and agent registrations carry. The PM decided
that compatibility with earlier exports and registrations matters more than a file created at
import time, so ``main.py`` was restored to its checkpoint (8e497da) bytes: importing the
module builds ``app = create_app()`` at once.

These checks pin that decision and the entry point's behaviour. Each child-process check runs
with an empty scratch settings file (the real .env is never read) and a scratch artifact
directory, and refuses network sockets.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import zipfile

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
# Checkpoint 8e497da identities (runtime cfe5ac07…), recomputed with the app's own functions.
CHECKPOINT_SERVICE_HASH = '3ce5bcd25af4b37ec908f8699de2de31684a585c54346e4fff4b85396438f2c3'
CHECKPOINT_CONTRACT_HASH = '6f9d778323a4efc227c721a1844cafce751752f92c1bdcb2cf3ee45929e54727'
# A real dashboard download saved at that checkpoint (restored to its 8e497da bytes).
CHECKPOINT_DOWNLOAD = ROOT / 'frontend/tests/fixtures/exported-regression.zip'

CHILD = textwrap.dedent('''
    import json, os, socket, stat, sys
    from pathlib import Path
    def refuse(*args, **kwargs):
        raise AssertionError('network use by the simulator entry-point check')
    socket.socket.connect = refuse
    socket.create_connection = refuse
    import app.config as config
    config.ROOT_ENV_PATH = Path(sys.argv[1])
    artifacts = Path(sys.argv[2])
    import app.simulator.main as simulator
    capability = artifacts / 'control-capability'
    result = {'app_built_by_import': 'app' in vars(simulator),
              'files_after_import': sorted(p.name for p in artifacts.iterdir()) if artifacts.exists() else None,
              'capability_mode': oct(stat.S_IMODE(capability.stat().st_mode)) if capability.exists() else None,
              'store_directory': str(simulator.app.state.store.directory)}
    from uvicorn.importer import import_from_string
    served = import_from_string('app.simulator.main:app')
    token = capability.read_text().strip()
    from fastapi.testclient import TestClient
    client = TestClient(served)
    result.update(
        served_is_the_import_time_app=served is simulator.app,
        health=client.get('/health').status_code,
        control_without_token=client.get('/control/ready').status_code,
        control_with_wrong_token=client.get('/control/ready', headers={'X-FaultLab-Control': 'w' * len(token)}).status_code,
        control_with_capability=client.get('/control/ready', headers={'X-FaultLab-Control': token}).status_code,
    )
    print(json.dumps(result))
''')


def _child(tmp_path, artifacts):
    settings_file = tmp_path / 'empty-settings.env'
    settings_file.write_text('')
    script = tmp_path / 'child.py'
    script.write_text(CHILD)
    env = {key: value for key, value in os.environ.items() if not key.startswith('FAULTLAB_')}
    env.update(PYTHONPATH=str(BACKEND), FAULTLAB_ARTIFACT_DIR=str(artifacts), FAULTLAB_CONTROL_TOKEN='')
    completed = subprocess.run([sys.executable, str(script), str(settings_file), str(artifacts)], cwd=tmp_path,
                               env=env, capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stderr[-2000:]
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_simulator_identity_is_the_checkpoint_identity_so_earlier_exports_stay_compatible():
    """If this fails, a change under backend/app/simulator/ (or contracts/*.schema.json) moved the
    simulator identity away from checkpoint 8e497da. Every earlier export and registration would
    then stop matching; make such a change only by an explicit decision, then update this pin and
    CURRENT_STATUS.md."""
    from app.config import Settings
    from app.contracts.models import CampaignBudget
    from app.lab.configuration import frozen_configuration
    installed = frozen_configuration(Settings(), CampaignBudget(), 'offline-v1')
    assert installed['service_hash'] == CHECKPOINT_SERVICE_HASH
    assert installed['contract_hash'] == CHECKPOINT_CONTRACT_HASH
    with zipfile.ZipFile(CHECKPOINT_DOWNLOAD) as archive:
        manifest = json.loads(archive.read('manifest.json'))
    assert manifest['contract_hash'] == installed['contract_hash']
    for field in ('capability_hash', 'scorer_hash', 'interpreter_hash'):
        assert manifest[field] == installed[field]


def test_the_restored_download_fixture_has_its_checkpoint_bytes():
    digest = hashlib.sha256(CHECKPOINT_DOWNLOAD.read_bytes()).hexdigest()
    assert digest == '14e53310cde9a3f6f985eb6bc4ac9fa0393a2155effd518953f39699a4ecb6df'


def test_import_builds_the_entry_point_with_a_private_capability_and_the_same_authorization(tmp_path):
    artifacts = tmp_path / 'artifacts'
    result = _child(tmp_path, artifacts)
    assert result['app_built_by_import'] is True
    assert result['files_after_import'] == ['control-capability']
    assert result['capability_mode'] == '0o600'
    assert result['store_directory'] == str(artifacts / 'worlds')
    assert result['served_is_the_import_time_app'] is True
    assert result['health'] == 200
    assert result['control_without_token'] == 403 and result['control_with_wrong_token'] == 403
    assert result['control_with_capability'] == 200


def test_a_restarted_entry_point_reuses_the_saved_capability(tmp_path):
    artifacts = tmp_path / 'artifacts'
    _child(tmp_path, artifacts)
    first = hashlib.sha256((artifacts / 'control-capability').read_bytes()).hexdigest()
    result = _child(tmp_path, artifacts)
    assert result['files_after_import'] == ['control-capability']
    assert result['control_with_capability'] == 200
    assert hashlib.sha256((artifacts / 'control-capability').read_bytes()).hexdigest() == first


def test_the_test_process_built_its_import_time_app_in_scratch_not_in_artifacts():
    """The root conftest imports the module with an empty scratch settings file and a scratch
    artifact directory, so the test process neither reads the real .env nor uses artifacts/."""
    import tempfile
    import app.simulator.main as simulator
    store = Path(simulator.app.state.store.directory).resolve()
    scratch = store.parent.parent
    assert store.name == 'worlds' and store.parent.name == 'artifacts'
    assert scratch.name.startswith('faultlab-tests-simulator-')
    assert scratch.parent == Path(tempfile.gettempdir()).resolve()
    assert not store.is_relative_to((ROOT / 'artifacts').resolve())
    assert oct((store.parent / 'control-capability').stat().st_mode & 0o777) == '0o600'

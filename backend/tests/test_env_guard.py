"""The test process never reads the project's real .env (September 28 review finding).

The conftest audit hook refuses an open of faultlab/.env before anything is opened. These
checks raise the audit event directly with sys.audit, so no file is touched at all.
"""
from pathlib import Path
import sys

import pytest

from app.config import ROOT_ENV_PATH, Settings

REAL_ENV = Path(__file__).resolve().parents[2] / '.env'


def test_the_guarded_path_is_the_one_settings_would_read():
    assert REAL_ENV == ROOT_ENV_PATH.resolve()


@pytest.mark.parametrize('target', [str(REAL_ENV), REAL_ENV, bytes(REAL_ENV)])
def test_opening_the_real_env_is_refused_before_anything_is_read(target):
    with pytest.raises(PermissionError, match='must not read the project .env'):
        sys.audit('open', target, 'r', 0)


def test_other_env_files_are_unaffected(tmp_path, monkeypatch):
    monkeypatch.delenv('WANDB_ENTITY', raising=False)
    other = tmp_path / '.env'
    other.write_text('WANDB_ENTITY=temporary-test-entity\n')
    sys.audit('open', str(other), 'r', 0)
    assert Settings.from_env(env_path=other).wandb_entity == 'temporary-test-entity'


def test_the_offline_simulator_needs_no_environment_settings(tmp_path):
    from fastapi.testclient import TestClient
    from app.simulator.main import create_app
    with TestClient(create_app(database_dir=tmp_path, control_token='guard-test', settings=Settings())) as client:
        assert client.get('/health').json()['service'] == 'faultlab-simulator'

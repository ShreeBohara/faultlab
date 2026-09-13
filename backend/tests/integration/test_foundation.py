from pathlib import Path
from unittest.mock import patch
import httpx
import pytest
from fastapi.testclient import TestClient
from app.config import Settings


def test_health_remains_configuration_free():
    from app.main import create_app
    with patch.object(Settings,'from_env',side_effect=AssertionError('health loaded configuration')):
        with TestClient(create_app()) as client:
            assert client.get('/api/health').json()=={'status':'ok','service':'faultlab-backend'}


@pytest.mark.localhost_http
def test_simulator_real_localhost_health(simulator_server):
    url,app=simulator_server
    with httpx.Client(base_url=url,trust_env=False) as client:
        response=client.get('/health')
        assert response.status_code==200
        assert response.json()['service']=='faultlab-simulator'
        assert client.get('/control/worlds/world-unknown/snapshot').status_code==403


def test_all_process_bindings_are_local():
    root=Path(__file__).resolve().parents[3]
    for name in ['start-backend.sh','start-simulator.sh']:
        text=(root/'scripts'/name).read_text()
        assert '--host 127.0.0.1' in text
        assert '0.0.0.0' not in text
    assert "host: '127.0.0.1'" in (root/'frontend/vite.config.ts').read_text()

import os
from unittest.mock import patch
import pytest

from app.local import launch_plan, check_ports


def test_launch_pairs_services_without_live_or_aria_and_preserves_environment(tmp_path):
    with patch.dict(os.environ, {'FAULTLAB_LIVE_ENABLED': 'true', 'FAULTLAB_ARIA_PUBLISH_ENABLED': 'true'}):
        path, environment, commands = launch_plan(tmp_path / 'new', frontend=False)
        assert [command[0] for command in commands] == ['simulator', 'backend']
        assert environment['FAULTLAB_ARTIFACT_DIR'] == str(path)
        assert environment['FAULTLAB_LIVE_ENABLED'] == 'false'
        assert environment['FAULTLAB_ARIA_PUBLISH_ENABLED'] == 'false'
        assert environment['FAULTLAB_READ_ONLY'] == 'false'
        assert os.environ['FAULTLAB_LIVE_ENABLED'] == 'true'
        assert not path.exists()


def test_archive_requires_saved_database_and_never_launches_simulator(tmp_path):
    with pytest.raises(ValueError, match='existing lab.sqlite3'):
        launch_plan(tmp_path, archive=True, frontend=False)
    (tmp_path / 'lab.sqlite3').touch()
    path, environment, commands = launch_plan(tmp_path, archive=True, frontend=False)
    assert environment['FAULTLAB_READ_ONLY'] == 'true'
    assert [command[0] for command in commands] == ['backend']
    with pytest.raises(ValueError, match='cannot enable live'):
        launch_plan(tmp_path, archive=True, live=True, frontend=False)


def test_busy_port_fails_without_starting_services():
    import socket
    with socket.socket() as server:
        server.bind(('127.0.0.1', 0))
        port = server.getsockname()[1]
        with pytest.raises(ValueError, match=f'Port {port} is in use'):
            check_ports([('backend', [], '.', port)])

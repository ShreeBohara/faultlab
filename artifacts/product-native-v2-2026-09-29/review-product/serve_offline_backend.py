"""A real FaultLab backend for the reviewer's dashboard walk-through: offline, scripted, loopback only, $0.

The API, coordinator, planner, runner, ledger, store and real smolagents 1.26.0 adapters are the product's own.
Only three things are the repository's declared offline test replacements (backend/tests/lab/original_loop_fixture.py
and test_planned_agent_execution.py): the model transport (NativeReferenceInputs, which answers from the public
observations it is shown, for every role), the evidence reader (OfflineEvidence) and the simulator transport
(in-process ASGI; no simulator port). Guards, as in backend/tests/conftest.py: an audit hook refuses any open of
the project .env; python-dotenv is disabled; every socket connect outside loopback raises.

Usage (from faultlab/backend):
  PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python ../artifacts/product-native-v2-2026-09-29/review-product/serve_offline_backend.py \
      --port 18431 --data-dir <scratch dir>
"""
import argparse
import ipaddress
import os
from pathlib import Path
import socket
import sys
import tempfile

REPO = Path(__file__).resolve().parents[3]
REAL_ENV = str(REPO / '.env')


def _refuse_real_env(event, args):
    if event != 'open' or not args or not isinstance(args[0], (str, bytes, os.PathLike)):
        return
    try:
        path = os.fsdecode(os.fspath(args[0]))
    except TypeError:
        return
    if os.path.basename(path) == '.env' and os.path.abspath(path) == REAL_ENV:
        raise PermissionError('The reviewer backend must not read the project .env')


sys.addaudithook(_refuse_real_env)
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['WANDB_ERROR_REPORTING'] = 'false'


def _loopback(host):
    if isinstance(host, bytes): host = host.decode()
    if host == 'localhost': return True
    try: return ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError): return False


_connect, _connect_ex, _gai = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo
def _guard(address):
    if isinstance(address, tuple) and not _loopback(address[0]):
        raise PermissionError(f'Reviewer backend refused a non-loopback connection to {address[0]}')
def _guarded_connect(sock, address):
    if sock.family != socket.AF_UNIX: _guard(address)
    return _connect(sock, address)
def _guarded_connect_ex(sock, address):
    if sock.family != socket.AF_UNIX: _guard(address)
    return _connect_ex(sock, address)
def _guarded_gai(host, *args, **kwargs):
    _guard((host, 0)); return _gai(host, *args, **kwargs)
socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = _guarded_connect, _guarded_connect_ex, _guarded_gai

sys.path[:0] = [str(REPO / 'backend'), str(REPO / 'backend/tests/lab'), str(REPO / 'backend/tests')]


def _import_simulator_offline(scratch):
    """As tests/conftest.py does: app.simulator.main builds an app at import, so import it with empty settings."""
    import importlib
    import app.config as config
    settings_file = scratch / 'empty-settings.env'; settings_file.write_text('')
    saved = config.ROOT_ENV_PATH
    config.ROOT_ENV_PATH = settings_file
    os.environ['FAULTLAB_ARTIFACT_DIR'] = str(scratch / 'import-artifacts')
    os.environ.pop('FAULTLAB_CONTROL_TOKEN', None)
    try:
        importlib.import_module('app.simulator.main')
    finally:
        config.ROOT_ENV_PATH = saved
        os.environ.pop('FAULTLAB_ARTIFACT_DIR', None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--data-dir', required=True)
    args = parser.parse_args()
    data = Path(args.data_dir); data.mkdir(parents=True, exist_ok=True)
    _import_simulator_offline(Path(tempfile.mkdtemp(prefix='review-sim-import-', dir=data)))
    import httpx
    import uvicorn
    from app.adapters.business_tools import WorldClient
    from app.lab.coordinator import LabCoordinator
    from app.main import create_app
    from app.simulator.main import create_app as simulator_app
    from original_loop_fixture import CONTROL, ManualPolicies, OfflineEvidence, OfflineRunner, fixture_settings
    from test_planned_agent_execution import NativeReferenceInputs
    settings = fixture_settings(data / 'lab')        # placeholder credentials; no provider is ever constructed
    coordinator = LabCoordinator(settings)
    simulator = simulator_app(database_dir=data / 'worlds', control_token=CONTROL, settings=settings)
    world = httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator), base_url='http://127.0.0.1:8001')
    coordinator.runner = OfflineRunner(coordinator.store, WorldClient('http://127.0.0.1:8001', CONTROL, client=world),
                                       NativeReferenceInputs('accepted'), offline_fixture=True)
    coordinator.policies = ManualPolicies(coordinator.store)
    coordinator.evidence_gateway = OfflineEvidence(coordinator.store, 'offline-fixture/review-dashboard')
    print(f'REVIEW BACKEND READY 127.0.0.1:{args.port} store={coordinator.store.path}', flush=True)
    uvicorn.run(create_app(coordinator=coordinator), host='127.0.0.1', port=args.port, log_level='warning')


if __name__ == '__main__':
    main()

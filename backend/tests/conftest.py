"""Default tests prohibit network; explicit HTTP tests allow loopback only.

Tests also never read the project's real .env (it holds provider credentials): an audit
hook refuses to open it in the test process, so a test that builds settings from the
environment must pass explicit settings or a temporary env_path. The simulator module,
which builds its server app when imported, is imported once below with scratch settings.
"""
import ipaddress
import os
from pathlib import Path
import socket
import sys
import pytest

_REAL_ENV = str(Path(__file__).resolve().parents[2] / '.env')


def _refuse_real_env(event, args):
    """Audit hook: refuse, before any byte is read, every open of the project's real .env."""
    if event != 'open' or not args or not isinstance(args[0], (str, bytes, os.PathLike)):
        return
    try:
        path = os.fsdecode(os.fspath(args[0]))
    except TypeError:
        return
    if os.path.basename(path) == '.env' and os.path.abspath(path) == _REAL_ENV:
        raise PermissionError('Offline tests must not read the project .env: pass settings= to create_app, '
                              'or Settings.from_env(env_path=<a temporary file>).')


sys.addaudithook(_refuse_real_env)

# Weave reads this once, at its first import, and otherwise registers an atexit
# Sentry upload that runs after these per-test socket guards are gone. Pin it before
# pytest imports any test module (some import the SDK directly); see app/__init__.py.
os.environ['WANDB_ERROR_REPORTING'] = 'false'
# smolagents calls python-dotenv's load_dotenv() when it is first imported, and that
# search reaches the project's real .env from inside .venv, exporting its credentials
# into os.environ. The native adapter guards its own import
# (app.integrations.external_agent._import_smolagents); this switch, python-dotenv's
# documented one, additionally makes any implicit load_dotenv() in the test process, or
# a child process it starts, a no-op. FaultLab's own settings use dotenv_values(), which
# this switch does not affect. (An earlier version of this comment said tests pass explicit
# temporary .env paths anyway; a September 28 review found 139 real-.env reads from 20 test
# files that called create_app() without settings. Those tests now pass settings, and the
# audit hook above refuses any such read.)
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
# In-process test clients address the app by synthetic host names (httpx
# base_url 'http://test', Starlette TestClient 'testserver'). Production allows only
# localhost, 127.0.0.1 and ::1 (app.main.LOCAL_HOSTS); tests opt in explicitly.
os.environ.setdefault('FAULTLAB_ALLOWED_HOSTS', 'test,testserver,lab')


def _import_simulator_entry_point_offline():
    """Import ``app.simulator.main`` once, before any test module, with scratch settings.

    That module builds uvicorn's entry point when it is imported (``app = create_app()``).
    The September 28 PM decision kept this checkpoint (8e497da) behaviour, so the simulator's
    service and contract identities, and with them earlier exported bundles, stay unchanged.
    The import-time build reads settings from the project .env and creates or reuses the
    control capability in the artifact directory. Here it reads an empty scratch settings
    file and uses a scratch artifact directory instead, so the test process never reads the
    real .env (the audit hook above would refuse it) and never touches artifacts/. Later
    imports reuse this module object; tests build their own simulators with
    create_app(database_dir=..., control_token=..., settings=...).
    """
    import atexit
    import importlib
    import shutil
    import tempfile
    import app.config as config
    scratch = Path(tempfile.mkdtemp(prefix='faultlab-tests-simulator-'))
    atexit.register(shutil.rmtree, scratch, True)
    settings_file = scratch / 'settings.env'
    settings_file.write_text('')
    names = ('FAULTLAB_ARTIFACT_DIR', 'FAULTLAB_CONTROL_TOKEN')
    saved_env = {name: os.environ.get(name) for name in names}
    saved_path = config.ROOT_ENV_PATH
    config.ROOT_ENV_PATH = settings_file
    os.environ['FAULTLAB_ARTIFACT_DIR'] = str(scratch / 'artifacts')
    os.environ.pop('FAULTLAB_CONTROL_TOKEN', None)
    try:
        importlib.import_module('app.simulator.main')
    finally:
        config.ROOT_ENV_PATH = saved_path
        for name, value in saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return scratch


# The scratch artifact directory the test process's import-time simulator app uses.
SIMULATOR_IMPORT_SCRATCH = _import_simulator_entry_point_offline()


def _local(host):
    if isinstance(host, bytes): host=host.decode()
    if host == 'localhost': return True
    try: return ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError): return False


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch, request):
    permit = request.node.get_closest_marker('localhost_http') is not None
    original_gai=socket.getaddrinfo
    original_connect=socket.socket.connect
    original_connect_ex=socket.socket.connect_ex
    original_create=socket.create_connection
    def verify(address):
        if not permit or not isinstance(address,tuple) or not _local(address[0]):
            raise AssertionError('Offline tests may only use explicitly marked loopback HTTP')
    def gai(host,*args,**kwargs):
        verify((host,0));return original_gai(host,*args,**kwargs)
    def connect(sock,address):
        if sock.family == socket.AF_UNIX: return original_connect(sock,address)
        verify(address);return original_connect(sock,address)
    def connect_ex(sock,address):
        verify(address);return original_connect_ex(sock,address)
    def create(address,*args,**kwargs):
        verify(address);return original_create(address,*args,**kwargs)
    monkeypatch.setattr(socket,'getaddrinfo',gai)
    monkeypatch.setattr(socket,'create_connection',create)
    monkeypatch.setattr(socket.socket,'connect',connect)
    monkeypatch.setattr(socket.socket,'connect_ex',connect_ex)

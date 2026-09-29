"""Building the native smolagents agent must never export a .env file into os.environ.

smolagents calls python-dotenv's load_dotenv() on first import; from this project's
.venv its default search reaches faultlab/.env. These checks run in fresh child
processes whose .env search is redirected to a dummy file written here, so the real
project .env is never opened, whatever the outcome. The child refuses all sockets.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import dotenv
import dotenv.main

BACKEND = Path(__file__).resolve().parents[2]
DUMMY_VALUES = {
    'FAULTLAB_DOTENV_PROBE_ONLY': 'present-only-in-the-dummy-dotenv',
    'WANDB_API_KEY': 'dummy-not-a-real-credential',
    'WANDB_ENTITY': 'dummy-probe-entity',
}
CHILD = textwrap.dedent('''
    import json, os, socket, sys
    from pathlib import Path
    dummy, mode = Path(sys.argv[1]), sys.argv[2]
    import dotenv, dotenv.main
    def redirected(*args, **kwargs):
        return str(dummy)
    dotenv.main.find_dotenv = redirected
    dotenv.find_dotenv = redirected
    def refuse(*args, **kwargs):
        raise AssertionError('network use while building the native agent')
    socket.socket.connect = refuse
    socket.create_connection = refuse
    keys = [line.split('=', 1)[0] for line in dummy.read_text().splitlines() if '=' in line]
    assert not [key for key in keys if key in os.environ]
    originals = (dotenv.load_dotenv, dotenv.main.load_dotenv)
    result = {}
    if mode == 'native-adapter':
        from app.integrations.external_agent import _native_agent
        result['agent'] = type(_native_agent(object(), 'offline/dotenv-isolation')).__name__
        from app.config import Settings
        result['explicit_settings_entity'] = Settings.from_env(env_path=dummy).wandb_entity
    elif mode == 'app-default-then-unguarded-import':
        import app  # sets PYTHON_DOTENV_DISABLED=1 unless the operator set a value
        import smolagents  # a direct import, bypassing the adapter's guard
    else:
        import smolagents  # unguarded control: shows the probe detects the leak
    result.update(
        smolagents_imported='smolagents.remote_executors' in sys.modules,
        leaked=sorted(key for key in keys if key in os.environ),
        load_dotenv_restored=(dotenv.load_dotenv, dotenv.main.load_dotenv) == originals,
        dotenv_switch=os.environ.get('PYTHON_DOTENV_DISABLED'),
    )
    print(json.dumps(result))
''')


def _child(tmp_path, mode, *, dotenv_switch='0'):
    dummy = tmp_path / '.env'
    dummy.write_text(''.join(f'{key}={value}\n' for key, value in DUMMY_VALUES.items()))
    script = tmp_path / 'child.py'
    script.write_text(CHILD)
    # The child gets no key from the dummy file up front. By default it gets an explicit
    # PYTHON_DOTENV_DISABLED=0 (which app/__init__.py keeps), so implicit loading is ON and
    # the adapter's own guard is what is under test; None leaves the variable unset.
    env = {key: value for key, value in os.environ.items()
           if key not in DUMMY_VALUES and key != 'PYTHON_DOTENV_DISABLED'}
    if dotenv_switch is not None:
        env['PYTHON_DOTENV_DISABLED'] = dotenv_switch
    env['PYTHONPATH'] = str(BACKEND)
    completed = subprocess.run([sys.executable, str(script), str(dummy), mode], cwd=tmp_path, env=env,
                               capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stderr[-2000:]
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_building_the_native_agent_exports_no_dotenv_value(tmp_path):
    result = _child(tmp_path, 'native-adapter')
    assert result['agent'] == 'ToolCallingAgent' and result['smolagents_imported']
    assert result['leaked'] == []
    assert result['load_dotenv_restored'] and result['dotenv_switch'] == '0'  # the guard alone did it
    # FaultLab's own explicit settings loading is unchanged: it still reads the file
    # it is given, without exporting anything.
    assert result['explicit_settings_entity'] == DUMMY_VALUES['WANDB_ENTITY']


def test_control_unguarded_smolagents_import_does_export_the_dummy_values(tmp_path):
    result = _child(tmp_path, 'unguarded-import')
    assert result['smolagents_imported']
    assert result['leaked'] == sorted(DUMMY_VALUES)


def test_importing_app_disables_implicit_dotenv_loading_for_any_later_import(tmp_path):
    # Defence in depth (review finding): even a direct smolagents import that bypasses the
    # adapter's guard exports nothing once the backend package has been imported.
    result = _child(tmp_path, 'app-default-then-unguarded-import', dotenv_switch=None)
    assert result['smolagents_imported'] and result['leaked'] == []
    assert result['dotenv_switch'] == '1'
    # An explicit operator value is kept: with 0 the same direct import leaks again, which
    # is why the adapter keeps its own guard and the static import test below exists.
    explicit = _child(tmp_path, 'app-default-then-unguarded-import', dotenv_switch='0')
    assert explicit['leaked'] == sorted(DUMMY_VALUES) and explicit['dotenv_switch'] == '0'


def test_test_process_disables_implicit_dotenv_loading(tmp_path, monkeypatch):
    dummy = tmp_path / '.env'
    dummy.write_text('FAULTLAB_DOTENV_PROBE_ONLY=present-only-in-the-dummy-dotenv\n')
    monkeypatch.setattr(dotenv.main, 'find_dotenv', lambda *args, **kwargs: str(dummy))
    monkeypatch.delenv('FAULTLAB_DOTENV_PROBE_ONLY', raising=False)
    assert os.environ.get('PYTHON_DOTENV_DISABLED') == '1'
    assert dotenv.load_dotenv() is False
    assert 'FAULTLAB_DOTENV_PROBE_ONLY' not in os.environ

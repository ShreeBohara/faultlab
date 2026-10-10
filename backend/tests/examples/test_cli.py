"""The public offline command works without configuration, sockets or old stores."""
import json
import os
from pathlib import Path
import subprocess
import sys

from app.cli.example import write_report


BACKEND = Path(__file__).resolve().parents[2]
GUARDED_CLI = '''
import os, runpy, socket, sys
def audit(event, args):
    if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
        if os.path.basename(os.fsdecode(args[0])) == '.env':
            raise AssertionError('Offline example tried to read .env')
def refuse(*args, **kwargs):
    raise AssertionError('Offline example tried to use a network socket')
sys.addaudithook(audit)
socket.socket.connect = refuse
socket.socket.connect_ex = refuse
socket.create_connection = refuse
socket.getaddrinfo = refuse
sys.argv = ['faultlab-example', *sys.argv[1:]]
runpy.run_module('app.cli.example', run_name='__main__')
'''


def invoke(tmp_path, *arguments):
    env = {**os.environ, 'PYTHONPATH': str(BACKEND), 'PYTHON_DOTENV_DISABLED': '1',
           'FAULTLAB_LIVE_ENABLED': 'true', 'FAULTLAB_ARIA_PUBLISH_ENABLED': 'true',
           'FAULTLAB_ARTIFACT_DIR': str(tmp_path / 'do-not-touch')}
    return subprocess.run([sys.executable, '-c', GUARDED_CLI, *map(str, arguments)],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)


def test_cli_distinguishes_demo_success_from_a_failing_release_check(tmp_path):
    output = tmp_path / 'comparison'
    comparison = invoke(tmp_path, 'compare', '--output', output)
    assert comparison.returncode == 0, comparison.stdout + comparison.stderr
    summary = json.loads((output / 'summary.json').read_text())
    assert summary['comparison_verified'] is True
    assert summary['runs']['unsafe']['status'] == 'VIOLATION'
    assert summary['runs']['safe']['status'] == summary['runs']['healthy']['status'] == 'PASS'
    assert summary['provider_calls'] == 0
    assert (output / 'report.html').is_file()
    assert (output / 'unsafe' / 'test_behavior.py').is_file()
    bundle = output / 'unsafe' / 'bundle'
    inspected = invoke(tmp_path, 'inspect', '--bundle', bundle)
    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout)['execution_performed'] is False
    for behavior, exit_code in [('unsafe', 1), ('safe', 0)]:
        check = invoke(tmp_path, 'check', '--bundle', bundle, '--behavior', behavior,
                       '--output', tmp_path / behavior)
        assert check.returncode == exit_code, check.stdout + check.stderr
        result = json.loads(check.stdout)
        assert result['trial_count'] == 3 and result['complete'] is True
        assert result['status'] == ('VIOLATION' if behavior == 'unsafe' else 'PASS')
    before = (output / 'summary.json').read_bytes()
    occupied = invoke(tmp_path, 'compare', '--output', output)
    assert occupied.returncode == 2
    assert (output / 'summary.json').read_bytes() == before
    assert not (tmp_path / 'do-not-touch').exists()
    assert not (tmp_path / '.env').exists()


def test_report_escapes_untrusted_agent_text_and_does_not_hide_missing_trials(tmp_path):
    run = {'status': 'INCOMPLETE', 'complete': False, 'provider_calls': 0,
           'provider_spend_dollars': 0, 'trial_count': 1, 'required_trials': 3,
           'failed_checks': ['C5'], 'trials': [{'original_report': {'text': '<script>alert(1)</script>'},
               'status': 'VIOLATION', 'failed_checks': ['C5']}]}
    result = write_report(tmp_path, {'unsafe': run}, comparison=False)
    page = (tmp_path / 'report.html').read_text()
    assert result['status'] == 'INCOMPLETE'
    assert '<script>' not in page
    assert '&lt;script&gt;' in page
    assert '1 of 3 required trials' in page
    assert 'default-src' in page

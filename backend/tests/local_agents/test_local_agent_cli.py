"""The documented CLI and exported pytest exercise an explicitly selected file."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from app.local_agents.report import write_report


ROOT = Path(__file__).resolve().parents[3]
GUARDED_ENTRY = '''
import os, runpy, socket, sys
def audit(event, args):
    if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
        if os.path.basename(os.fsdecode(args[0])) == '.env':
            raise AssertionError('Local-agent command tried to read .env')
def refuse(*args, **kwargs):
    raise AssertionError('Local-agent command tried to use a network socket')
sys.addaudithook(audit)
socket.socket.connect = refuse
socket.socket.connect_ex = refuse
socket.create_connection = refuse
socket.getaddrinfo = refuse
module, *arguments = sys.argv[1:]
sys.argv = [module, *arguments]
runpy.run_module(module, run_name='__main__')
'''


def invoke(tmp_path, module, *arguments, agent=None):
    env = {**os.environ, 'PYTHONPATH': str(ROOT / 'backend'),
           'PYTHON_DOTENV_DISABLED': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
           'FAULTLAB_LIVE_ENABLED': 'true', 'FAULTLAB_ARIA_PUBLISH_ENABLED': 'true',
           'FAULTLAB_ARTIFACT_DIR': str(tmp_path / 'do-not-touch')}
    env.pop('FAULTLAB_LOCAL_AGENT', None)
    if agent is not None:
        env['FAULTLAB_LOCAL_AGENT'] = str(agent)
    return subprocess.run([sys.executable, '-c', GUARDED_ENTRY, module, *map(str, arguments)],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)


def test_cli_and_exported_pytest_follow_the_outside_authors_correction(tmp_path):
    # Commands run outside the source checkout, with no historical store.
    scenario = tmp_path / 'source-scenario'
    prepared = invoke(tmp_path, 'app.cli.example', 'compare', '--output', scenario)
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
    copied = tmp_path / 'copied scenario'
    copied.mkdir()
    shutil.copytree(scenario / 'unsafe/bundle', copied / 'bundle')
    shutil.copy2(scenario / 'unsafe/offline-fixture.json', copied / 'offline-fixture.json')
    scenario.rename(tmp_path / 'unavailable-original-store')
    bundle = copied / 'bundle'
    agent = tmp_path / 'my local decision.py'
    safe_source = (ROOT / 'examples/local-agent/order_agent.py').read_text()
    assert 'CONFIRM_REJECTED = False' in safe_source
    unsafe_source = safe_source.replace('CONFIRM_REJECTED = False', 'CONFIRM_REJECTED = True')
    agent.write_text(unsafe_source)

    inspected = invoke(tmp_path, 'app.cli.local_agent', 'inspect', '--bundle', bundle)
    assert inspected.returncode == 0, inspected.stdout + inspected.stderr
    assert json.loads(inspected.stdout)['execution_performed'] is False
    for name, source, expected_code in [('unsafe', unsafe_source, 1), ('safe', safe_source, 0)]:
        agent.write_text(source)
        output = tmp_path / name
        checked = invoke(tmp_path, 'app.cli.local_agent', 'check', '--agent', agent,
                         '--bundle', bundle, '--output', output)
        assert checked.returncode == expected_code, checked.stdout + checked.stderr
        result = json.loads(checked.stdout)
        assert result['complete'] is True and result['trial_count'] == 3
        assert result['failed_checks'] == (['C3', 'C5'] if name == 'unsafe' else [])
        assert (output / 'report.html').is_file() and (output / 'report.md').is_file()
        assert sorted(path.name for path in (output / 'portable').iterdir()) == [
            'bundle', 'offline-fixture.json', 'test_local_agent.py']

    healthy = invoke(tmp_path, 'app.cli.local_agent', 'healthy', '--agent', agent,
                     '--output', tmp_path / 'healthy')
    assert healthy.returncode == 0, healthy.stdout + healthy.stderr
    assert json.loads(healthy.stdout)['trial_count'] == 1
    copied_test = tmp_path / 'receiving workspace'
    shutil.copytree(tmp_path / 'safe/portable', copied_test)
    # The entire originating run disappears from its recorded path.
    (tmp_path / 'safe').rename(tmp_path / 'saved-safe-run-unavailable')
    for source, expected_code in [(unsafe_source, 1), (safe_source, 0)]:
        agent.write_text(source)
        checked = invoke(tmp_path, 'pytest', copied_test / 'test_local_agent.py', '-q', agent=agent)
        assert checked.returncode == expected_code, checked.stdout + checked.stderr
        assert ('1 failed' if expected_code else '1 passed') in checked.stdout
        if expected_code:
            assert "VIOLATION: failed checks ['C3', 'C5']" in checked.stdout
    missing = invoke(tmp_path, 'pytest', copied_test / 'test_local_agent.py', '-q')
    assert missing.returncode == 1 and 'Select your local program' in missing.stdout

    before = (tmp_path / 'unsafe/summary.json').read_bytes()
    occupied = invoke(tmp_path, 'app.cli.local_agent', 'check', '--agent', agent,
                      '--bundle', bundle, '--output', tmp_path / 'unsafe')
    assert occupied.returncode == 2
    assert (tmp_path / 'unsafe/summary.json').read_bytes() == before
    assert not (tmp_path / 'do-not-touch').exists()
    assert not (tmp_path / '.env').exists()


def test_local_report_keeps_incomplete_status_and_escapes_untrusted_text(tmp_path):
    result = {'status': 'INCOMPLETE', 'mode': 'regression',
              'agent': {'source_hash': 'a' * 64}, 'failed_checks': ['C5'],
              'trial_count': 1, 'required_trials': 3, 'decision_calls': 1,
              'paths': {'output_dir': str(tmp_path), 'portable': None},
              'trials': [{'status': 'INCOMPLETE', 'failed_checks': ['C5'],
                          'original_report': {'text': '<script>alert(1)</script>'}}]}
    write_report(result)
    page = (tmp_path / 'report.html').read_text()
    assert 'cannot establish a pass' in page and '1 of 3 required trials' in page
    assert '<script>' not in page and '&lt;script&gt;' in page
    assert 'default-src' in page and 'External program activity and spending are not metered' in page

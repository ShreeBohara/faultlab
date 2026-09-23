"""Offline checks of the Phase 18 held-out runner against a scripted fake backend."""
import hashlib
import importlib.util
import json
import pathlib
import sqlite3
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/experiments'))
SPEC = importlib.util.spec_from_file_location('run_heldout_check', ROOT / 'scripts/experiments/run_heldout_check.py')
held = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(held)
base = held.base

CONFIG = 'c' * 64
FREEZE = {'schema_version': 'faultlab-gate-freeze/v1', 'files': {}, 'fingerprints': {},
          'functions': {base.ASSESS_PAIRS_KEY: {'text_sha256': base.ASSESS_PAIRS_TEXT_SHA256}}}
PROCESS = {'processes': [{'pid': 1, 'command': 'python -m uvicorn app.main:app', 'started_at': 'x'}]}
CERTIFIED = {'study_id': held.CERTIFIED_STUDY, 'replay_of': None, 'decision': 'OBSERVED_IMPROVEMENT',
             'actor_context_protocol': base.ACTOR_CONTEXT, 'evidence_protocol': base.EVIDENCE_PROTOCOL,
             'manifest_hash': base.MANIFEST_HASH, 'selected_candidate_hash': held.CERTIFIED_POLICY_HASH,
             'validation_assessment': {'decision': 'OBSERVED_IMPROVEMENT', 'by_case': {
                 'notification-3': {'B0': {'completed': 0}, 'L': {'completed': 3}},
                 'notification-2': {'B0': {'completed': 0}, 'L': {'completed': 3}}}}}


class FakeBackend:
    def __init__(self, store, outcomes, *, config_hash=CONFIG, spend=4.0, lose_reply=False, hang=False,
                 list_fails=False, commit_after_lists=0, on_poll=None):
        self.store, self.outcomes, self.config_hash, self.spend = store, list(outcomes), config_hash, spend
        self.lose_reply, self.hang, self.list_fails = lose_reply, hang, list_fails
        self.commit_after_lists, self.list_calls, self.pending, self.on_poll = commit_after_lists, 0, None, on_poll
        self.campaigns, self.ledgers, self.checks, self.stops = [], {}, {}, []
        self.active = None

    def put(self, kind, id, payload):
        con = sqlite3.connect(self.store)
        con.execute('INSERT INTO records(kind,id,payload) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload',
                    (kind, id, json.dumps(payload)))
        con.commit(); con.close()

    def __call__(self, b, method, path, body=None, timeout=30):
        if path == '/api/config/status':
            return {'live_enabled': True, 'active_campaign_id': self.active,
                    'models': {'actor': base.EXPECTED_ACTOR, 'mechanic': base.EXPECTED_MECHANIC}}
        if path == '/api/campaigns' and method == 'POST':
            cid = f'campaign-{len(self.campaigns) + 1}'; self.campaigns.append(cid)
            self.put('campaign_provenance', cid, {'aria_publication_enabled': False})
            return {'campaign_id': cid, 'configuration_hash': self.config_hash}
        if path.endswith('/heldout-check') and method == 'POST':
            assert body == {'execute_live': True, 'certified_study_id': held.CERTIFIED_STUDY}
            cid = path.split('/')[3]
            check_id = f'heldout-check-{len(self.checks) + 1}'
            decision = self.outcomes.pop(0)
            identity = {'check_id': check_id, 'campaign_id': cid, 'policy_hash': held.CERTIFIED_POLICY_HASH,
                        'predicate': held.PREDICATE, 'actor_context_protocol': base.ACTOR_CONTEXT,
                        'partition': 'promotion', 'certified_study_id': held.CERTIFIED_STUDY}
            self.checks[check_id] = {**identity, 'status': 'INCOMPLETE' if decision == 'INCOMPLETE' else 'COMPLETED',
                                     'decision': decision, 'reason': 'r', 'batch_id': 'b', 'trials': 36, 'pairs': 18,
                                     'assessment': {'decision': decision}}
            self.ledgers[cid] = {'charged_dollar_upper_bound': self.spend, 'used_calls': 100}
            if self.hang:
                self.active = cid
                self.checks[check_id]['status'] = 'RUNNING'
            if self.commit_after_lists:
                self.pending = self.checks.pop(check_id)          # not visible yet: committed late
                raise TimeoutError('reply timed out before the server committed the check')
            if self.lose_reply:
                self.lose_reply = False
                raise TimeoutError('reply lost after the server started the check')
            return {**identity, 'status': 'QUEUED'}
        if path.endswith('/heldout-checks') and method == 'GET':
            if self.list_fails:
                raise OSError('list failed')
            self.list_calls += 1
            if self.pending and self.list_calls >= self.commit_after_lists:
                self.checks[self.pending['check_id']] = self.pending; self.pending = None
            cid = path.split('/')[3]
            return [c for c in self.checks.values() if c['campaign_id'] == cid]
        if path.startswith('/api/heldout-checks/'):
            if self.on_poll:
                self.on_poll(self)
            return self.checks[path.rsplit('/', 1)[1]]
        if path.endswith('/completion-studies'):
            return []
        if path.endswith('/budget'):
            return self.ledgers.get(path.split('/')[3], {'reservations': {}})
        if path.endswith('/stop'):
            self.stops.append(path); return {}
        raise AssertionError(f'unexpected {method} {path}')


@pytest.fixture
def env(tmp_path, monkeypatch):
    freeze = tmp_path / 'freeze.json'; freeze.write_text(json.dumps(FREEZE))
    settings_file = tmp_path / 'settings.json'; settings_file.write_text('{}')
    store = tmp_path / 'lab.sqlite3'
    con = sqlite3.connect(store)
    con.execute('CREATE TABLE records(kind TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,immutable INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(kind,id))')
    con.execute('INSERT INTO records(kind,id,payload) VALUES(?,?,?)', ('completion_studies', held.CERTIFIED_STUDY, json.dumps(CERTIFIED)))
    con.commit(); con.close()
    (tmp_path / 'docs/part2').mkdir(parents=True)
    (tmp_path / 'docs/part2/PHASE18_EXPERIMENT.md').write_text('protocol')
    monkeypatch.setattr(held, 'ROOT', tmp_path)
    monkeypatch.setattr(held, 'DECLARED_FREEZE_SHA256', hashlib.sha256(freeze.read_bytes()).hexdigest())
    monkeypatch.setattr(held, 'DECLARED_CONFIGURATION_HASH', CONFIG)
    monkeypatch.setattr(held, 'DECLARED_SETTINGS_SHA256', hashlib.sha256(settings_file.read_bytes()).hexdigest())
    monkeypatch.setattr(base, 'gate_freeze', lambda: json.loads(json.dumps(FREEZE)))
    monkeypatch.setattr(base, 'check_backend_process', lambda: PROCESS)
    monkeypatch.setattr(base.time, 'sleep', lambda s: None)
    import app.config
    monkeypatch.setattr(app.config.Settings, 'from_env', classmethod(
        lambda cls: type('S', (), {'wandb_entity': 'entity', 'project_path': base.EXPECTED_PROJECT})()))

    def run(backend, *extra, out='phase18-test'):
        monkeypatch.setattr(base, 'api', backend)
        monkeypatch.setattr(sys, 'argv', ['run_heldout_check.py', '--out', str(tmp_path / 'artifacts' / out), '--store', str(store),
                                          '--settings', str(settings_file), '--expect-freeze', str(freeze), '--poll', '0',
                                          '--idle-grace', '2', '--execute-live', '--confirm-entity', 'entity', *extra])
        held.main()
        return json.loads((tmp_path / 'artifacts' / out / 'heldout-manifest.json').read_text())
    run.store = store
    return run


@pytest.mark.parametrize('verdict', ['NO_HARM', 'HARM'])
def test_the_first_verdict_is_final(env, verdict):
    backend = FakeBackend(env.store, [verdict, 'NO_HARM'])
    manifest = env(backend)
    assert manifest['stop_reason'] == 'verdict' and manifest['verdict'] == verdict
    assert len(manifest['attempts']) == 1 and len(backend.checks) == 1
    assert manifest['total_charged_upper_bound'] == pytest.approx(4.0)


def test_only_an_attempt_without_a_verdict_is_replaced(env):
    backend = FakeBackend(env.store, ['INCOMPLETE', 'HARM', 'NO_HARM'])
    manifest = env(backend)
    assert [r['decision'] for r in manifest['attempts']] == ['INCOMPLETE', 'HARM'] and manifest['verdict'] == 'HARM'


def test_attempts_are_capped_at_three(env):
    backend = FakeBackend(env.store, ['INCOMPLETE'] * 5)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'attempt_cap' and len(manifest['attempts']) == 3 and manifest['verdict'] is None


def test_the_spend_guard_stops_before_an_attempt_that_could_cross_the_cap(env):
    backend = FakeBackend(env.store, ['INCOMPLETE'] * 5, spend=8.0)
    manifest = env(backend, '--spend-cap', '20', '--headroom', '7')
    # 0 -> 8 -> 16; at 16 + 7 > 20 no third attempt starts.
    assert manifest['stop_reason'] == 'spend_guard' and len(manifest['attempts']) == 2


def test_a_configuration_mismatch_stops_at_no_cost(env):
    backend = FakeBackend(env.store, ['NO_HARM'], config_hash='d' * 64)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and not backend.checks and 'configuration_hash' in manifest['abort_detail']


def test_it_refuses_to_overwrite_a_run(env):
    backend = FakeBackend(env.store, ['NO_HARM'])
    env(backend)
    with pytest.raises(SystemExit, match='refusing to overwrite'):
        env(backend)


def test_it_refuses_a_study_that_no_longer_meets_the_certification_rule(env):
    con = sqlite3.connect(env.store)
    con.execute('UPDATE records SET payload=? WHERE id=?', (json.dumps({**CERTIFIED, 'replay_of': 'x'}), held.CERTIFIED_STUDY))
    con.commit(); con.close()
    backend = FakeBackend(env.store, ['NO_HARM'])
    with pytest.raises(SystemExit, match='certification rule'):
        env(backend)
    assert not backend.checks


def test_code_that_differs_from_the_freeze_is_refused(env, monkeypatch):
    monkeypatch.setattr(base, 'gate_freeze', lambda: {**FREEZE, 'files': {'x': 1}})
    backend = FakeBackend(env.store, ['NO_HARM'])
    with pytest.raises(SystemExit, match='differs from the reviewed freeze'):
        env(backend)
    assert not backend.checks


def test_plan_is_dry(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(base, 'api', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no HTTP')))
    monkeypatch.setattr(sys, 'argv', ['run_heldout_check.py', '--out', str(tmp_path / 'p'), '--plan'])
    assert held.main() == 0 and 'Dry plan only' in capsys.readouterr().out


def test_a_lost_start_reply_is_adopted_not_lost(env):
    backend = FakeBackend(env.store, ['NO_HARM'], lose_reply=True)
    manifest = env(backend)
    row = manifest['attempts'][0]
    assert row['adopted_after_start_error'] and row['start_error'] == 'TimeoutError'
    assert manifest['verdict'] == 'NO_HARM' and len(backend.checks) == 1


def test_a_timed_out_check_is_left_running_not_stopped(env):
    backend = FakeBackend(env.store, ['NO_HARM'], hang=True)
    manifest = env(backend, '--check-timeout', '0')
    assert manifest['stop_reason'] == 'aborted' and not backend.stops
    assert manifest['check_left_running'] == 'heldout-check-1'


def test_a_second_run_folder_is_refused(env):
    backend = FakeBackend(env.store, ['NO_HARM'])
    env(backend)
    with pytest.raises(SystemExit, match='Another Phase 18 run exists'):
        env(backend, out='phase18-other')


def test_a_lost_reply_with_a_failing_lookup_stops_nothing(env):
    backend = FakeBackend(env.store, ['NO_HARM'], lose_reply=True, hang=True, list_fails=True)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and not backend.stops
    assert manifest['check_state_unknown'] == 'campaign-1'


def test_a_check_the_server_commits_late_is_adopted(env):
    backend = FakeBackend(env.store, ['NO_HARM'], commit_after_lists=3)
    manifest = env(backend)
    assert manifest['attempts'][0]['adopted_after_start_error'] and manifest['verdict'] == 'NO_HARM'


def test_a_signal_leaves_the_running_check_alone(env):
    def detach(fake):
        fake.on_poll = None
        raise held.Detached(15)
    backend = FakeBackend(env.store, ['NO_HARM'], hang=True, on_poll=detach)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and 'left running' in manifest['abort_detail'] and not backend.stops

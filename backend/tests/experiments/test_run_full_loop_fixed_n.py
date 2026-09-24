"""Offline checks of the Phase 23 fixed-N full-loop runner against a scripted fake backend.

No network, no provider, no real store: the reused Phase 17 HTTP helper is replaced by an
in-memory fake that also writes to a throwaway SQLite store with the real records/events
schema, and every pin is pointed at synthetic files. Mirrors test_run_full_loop.py for the
behaviour that is new: no stop at a certified study, fixed N, spend truncation, the 5-failure
stop, the routing field, distinct-hash counts, the stage funnel and placeholder refusal.
"""
import hashlib
import importlib.util
import json
import os
import pathlib
import signal
import sqlite3
import sys
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/experiments'))
SPEC = importlib.util.spec_from_file_location('run_full_loop_fixed_n',
                                              ROOT / 'scripts/experiments/run_full_loop_fixed_n.py')
fixed = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixed)
base = fixed.base
SHIPPED_PINS = {name: getattr(fixed, name) for name in fixed.PINS}   # before any monkeypatch
REAL_SIGNAL = signal.signal                                          # the env fixture replaces it

CONFIG = 'c' * 64
DD62 = fixed.PHASE17_POLICY_HASH
STEP_RULES = {'rules': [{'hook': 'after_notification_response', 'when': 'notification_outcome_uncertain',
                         'steps': [{'op': 'read_notification_operation'},
                                   {'op': 'retry_original_request', 'service': 'notifications'}]}]}
NO_STEP_RULES = {'rules': [{'hook': 'after_notification_response', 'when': 'notification_outcome_uncertain',
                            'steps': [{'op': 'wait_ticks', 'ticks': 1}, {'op': 'read_notification_operation'}]}]}
CASES = ('healthy', 'notification-2', 'notification-1', 'notification-3', 'notification-18',
         'lost-notification-response', 'terminal-upgrade-rejection')
FIRES = [{'type': 'policy_step', 'payload': {'executed': True, 'hook': 'after_notification_response',
                                             'op': 'retry_original_request'}},
         {'type': 'tool_dispatched', 'payload': {'caller': 'policy', 'hook': 'after_notification_response',
                                                 'tool': 'send_confirmation'}}]
GATED = [{'type': 'policy_step', 'payload': {'executed': False, 'hook': 'after_notification_response',
                                             'op': 'retry_original_request'}}]


def counts(completed):
    return {'attempted': 3, 'valid': 3, 'completed': completed, 'violations': 0, 'safe_unresolved': 3 - completed,
            'correctly_rejected': 0, 'lab_errors': 0, 'interrupted': 0, 'scheduled': 3, 'triggered': 3,
            'untriggered': 0}


def by_case(l_completed, b0_completed=None):
    b0_completed = b0_completed or {}
    return {case: {'B0': counts(b0_completed.get(case, 0)), 'L': counts(l_completed.get(case, 0))}
            for case in CASES}


def study(*, status='COMPLETED', decision='NO_CHANGE', stage='controls', candidates=(), l=None, b0=None,
          error_type=None, protocol=base.ACTOR_CONTEXT, rereads=(), evidence=2, selected=None, trial_rows=(),
          events=None):
    record = {'status': status, 'decision': decision, 'reason': 'r', 'stage': stage,
              'actor_context_protocol': protocol, 'evidence_protocol': base.EVIDENCE_PROTOCOL,
              'replay_of': None, 'manifest_hash': base.MANIFEST_HASH, 'candidates': list(candidates),
              'trial_rows': list(trial_rows), 'evidence_rereads': list(rereads), 'evidence_count': evidence,
              'selected_candidate_hash': selected,
              'validation_assessment': None if l is None else {'decision': decision, 'by_case': by_case(l, b0)}}
    if error_type:
        record['error_type'] = error_type
    if events:
        record['_events'] = events
    return record


def candidate(content, decision, source=None, policy_hash='h' * 64):
    return {'decision': decision, 'policy_hash': policy_hash, 'content': content,
            'source_assessment': {'decision': source} if source else None}


def certified_study(policy_hash, **kwargs):
    return study(decision='OBSERVED_IMPROVEMENT', stage='validation',
                 l={'notification-2': 3, 'healthy': 3, 'notification-3': 3}, b0={'healthy': 3, 'notification-3': 1},
                 candidates=[candidate(STEP_RULES, 'OBSERVED_IMPROVEMENT', 'SOURCE_QUALIFIED', policy_hash)],
                 selected=policy_hash, **kwargs)


def trial(stage, arm, eid, *, case='notification-2', scheduled=True, triggered=True, lifecycle='COMPLETED',
          outcome='COMPLETED'):
    return {'stage': stage, 'case_id': case,
            'trial': {'episode_id': eid, 'arm': arm, 'lifecycle': lifecycle, 'outcome': outcome,
                      'fault_scheduled': scheduled, 'fault_triggered': triggered if scheduled else False,
                      'failed_checks': [], 'trial_index': 0, 'policy_hash': 'x', 'world_id': 'world-' + eid}}


OK = study()
DEAD = study(status='INCOMPLETE', decision='INCOMPLETE', error_type='WaitingEvidence')
SOURCE_ONLY = study(decision='OBSERVED_IMPROVEMENT', stage='validation', l={'notification-2': 3, 'healthy': 3},
                    b0={'healthy': 3}, candidates=[candidate(STEP_RULES, 'OBSERVED_IMPROVEMENT', 'SOURCE_QUALIFIED')],
                    selected='h' * 64)


# ----------------------------------------------------------------- pure read-out rules

@pytest.mark.parametrize('lifecycle', ['COMPLETED', 'LAB_ERROR', 'INTERRUPTED'])
@pytest.mark.parametrize('outcome', [None, 'LAB_ERROR', 'COMPLETED', 'SAFE_UNRESOLVED', 'VIOLATION'])
@pytest.mark.parametrize('scheduled,triggered', [(False, False), (True, True), (True, False)])
def test_valid_trial_mirrors_the_backend_rule(lifecycle, outcome, scheduled, triggered):
    from app.lab.reproduction import valid_trial
    row = {'lifecycle': lifecycle, 'outcome': outcome, 'fault_scheduled': scheduled, 'fault_triggered': triggered}
    assert fixed.valid_trial(row) == valid_trial(SimpleNamespace(**row))


def test_a_step_that_is_present_is_not_a_step_that_fires():
    assert fixed.step_fired(FIRES) and fixed.retry_executed(FIRES)
    assert not fixed.step_fired(GATED) and not fixed.retry_executed(GATED)       # gated on PENDING: never ran
    actor_send = [{'type': 'tool_dispatched', 'payload': {'caller': 'actor', 'tool': 'send_confirmation'}}]
    upgrade_retry = [{'type': 'tool_dispatched', 'payload': {'caller': 'policy', 'tool': 'update_order'}}]
    assert not fixed.step_fired(actor_send) and not fixed.step_fired(upgrade_retry) and not fixed.step_fired([])


def test_routing_takes_the_first_new_certified_hash_and_never_the_phase17_policy():
    rows = [{'attempt': 1, 'certified': False, 'selected_candidate_hash': 'a' * 64},
            {'attempt': 2, 'certified': True, 'selected_candidate_hash': DD62, 'post_checks': 'passed'},
            {'attempt': 3, 'certified': True, 'selected_candidate_hash': 'b' * 64, 'study_id': 's3',
             'campaign_id': 'c3', 'post_checks': 'passed'},
            {'attempt': 4, 'certified': True, 'selected_candidate_hash': 'c' * 64, 'post_checks': 'passed'}]
    field = fixed.routing(rows, final=True)
    assert (field['policy_hash'], field['attempt'], field['study_id'], field['routable']) == ('b' * 64, 3, 's3', True)
    assert field['excluded_certified_attempts'] == [{'attempt': 2, 'policy_hash': DD62}]
    assert not fixed.routing(rows, final=False)['routable']                    # an open run routes nothing
    only_dd62 = fixed.routing(rows[:2], final=True)
    assert only_dd62['policy_hash'] is None and not only_dd62['routable']
    pending = fixed.routing([{**rows[2], 'post_checks': 'pending'}], final=True)
    assert pending['policy_hash'] == 'b' * 64 and not pending['routable']


def test_the_primary_statement_says_truncated_at_n():
    assert fixed.primary_statement(2, 30, 'fixed_n').startswith('2 of 30 attempts produced a certified')
    assert fixed.primary_statement(1, 14, 'spend_guard').startswith('Truncated at n=14 by the $150 spend guard')
    assert 'not a finding about the loop' in fixed.primary_statement(0, 10, 'breaker')


def test_the_shipped_design_is_the_declared_one():
    assert (fixed.N_ATTEMPTS, fixed.SPEND_CAP, fixed.HEADROOM, fixed.BREAKER) == (30, 150.0, 11.0, 5)
    assert fixed.FINAL_STOPS == ('fixed_n', 'spend_guard') and 'certified' not in fixed.FINAL_STOPS
    assert set(fixed.EXCLUDED_FROM_ROUTING) == {DD62}
    assert fixed.MECHANIC_BRIEF == 'backend/app/agents/prompts/completion.md'
    assert base.ACTOR_CONTEXT == 'faultlab-actor-context/v4-indexed-evidence'


# ----------------------------------------------------------------- pins

FREEZE_TIME_PINS = ('DECLARED_FREEZE_SHA256', 'DECLARED_CONFIGURATION_HASH', 'DECLARED_PROTOCOL_SHA256',
                    'DECLARED_GATE_FREEZE_SCRIPT_SHA256', 'DECLARED_DRIFT_CHECKER_SHA256',
                    'DECLARED_INGESTION_CHECK_SHA256')


def test_every_shipped_pin_is_a_placeholder_or_a_well_formed_hash():
    """Holds before the Phase 22 freeze (placeholders) and after it (filled): R6."""
    assert all(SHIPPED_PINS[name] == fixed.PLACEHOLDER or fixed.is_sha256(SHIPPED_PINS[name])
               for name in FREEZE_TIME_PINS)
    known = set(fixed.PINS) - set(FREEZE_TIME_PINS)
    assert all(fixed.is_sha256(SHIPPED_PINS[name]) for name in known)


FREEZE_TIME_FILES = {'DECLARED_FREEZE_SHA256': 'artifacts/phase22-2026-09-24/gate-freeze-after.json',
                     'DECLARED_PROTOCOL_SHA256': fixed.PROTOCOL,
                     'DECLARED_GATE_FREEZE_SCRIPT_SHA256': 'scripts/experiments/gate_freeze.py',
                     'DECLARED_DRIFT_CHECKER_SHA256': 'scripts/experiments/check_clock_drift.py',
                     'DECLARED_INGESTION_CHECK_SHA256': 'scripts/experiments/check_ingestion_health.py'}


@pytest.mark.parametrize('name', sorted(FREEZE_TIME_FILES))
def test_a_filled_freeze_time_pin_matches_its_file(name):
    """After the freeze fills a pin, the file it names must be exactly that file."""
    if SHIPPED_PINS[name] == fixed.PLACEHOLDER:
        pytest.skip('not filled until the Phase 22 freeze')
    assert base.sha256_file(ROOT / FREEZE_TIME_FILES[name]) == SHIPPED_PINS[name]


def test_the_pins_declared_unchanged_from_phase17_match_the_files_on_disk():
    """The Mechanic brief is byte-identical to Phase 17's, the reused runner is unedited, and the
    settings file is Phase 17's. Also checks the brief against the Phase 16 freeze Phase 17 ran on."""
    assert base.sha256_file(ROOT / 'scripts/experiments/run_full_loop.py') == SHIPPED_PINS['DECLARED_BASE_RUNNER_SHA256']
    assert base.sha256_file(ROOT / fixed.MECHANIC_BRIEF) == SHIPPED_PINS['DECLARED_MECHANIC_BRIEF_SHA256']
    settings = ROOT / fixed.DEFAULT_SETTINGS
    phase16 = ROOT / 'artifacts/phase16-2026-09-22/gate-freeze-after.json'
    if not settings.exists() or not phase16.exists():
        pytest.skip('no local artifacts')
    assert base.sha256_file(settings) == SHIPPED_PINS['DECLARED_SETTINGS_SHA256']
    frozen = json.loads(phase16.read_text())
    assert frozen['files'][fixed.MECHANIC_BRIEF] == SHIPPED_PINS['DECLARED_MECHANIC_BRIEF_SHA256']
    assert frozen['fingerprints']['scorer_hash'] == fixed.SCORER_HASH


# ----------------------------------------------------------------- fake backend and store

NO_LEDGER = {'usage_metadata_known': True, 'measured_input_tokens': 0, 'measured_output_tokens': 0,
             'reservations': {}}


def make_store(path):
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE records(kind TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,'
                'immutable INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(kind,id))')
    con.execute('CREATE TABLE events(episode_id TEXT NOT NULL,seq INTEGER NOT NULL,payload TEXT NOT NULL,'
                'PRIMARY KEY(episode_id,seq))')
    con.commit(); con.close()


class FakeBackend:
    def __init__(self, store, outcomes, *, spend=2.0, config_hash=CONFIG, aria=False, project=base.EXPECTED_PROJECT,
                 start_fails=(), adopt=False, drift=False):
        self.store, self.outcomes, self.spend = store, list(outcomes), spend
        self.config_hash, self.aria, self.project = config_hash, aria, project
        self.start_fails, self.adopt, self.drift = set(start_fails), adopt, drift
        self.campaigns, self.ledgers, self.studies, self.stops, self.started = [], {}, {}, [], []
        self.active = None
        self.actor = base.EXPECTED_ACTOR
        self.clock = 0
        self.on_poll = None

    def put(self, kind, id, payload):
        con = sqlite3.connect(self.store)
        con.execute('INSERT INTO records(kind,id,payload) VALUES(?,?,?) '
                    'ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload', (kind, id, json.dumps(payload)))
        con.commit(); con.close()

    def put_events(self, episode_id, events):
        con = sqlite3.connect(self.store)
        con.executemany('INSERT INTO events(episode_id,seq,payload) VALUES(?,?,?)',
                        [(episode_id, i, json.dumps(e)) for i, e in enumerate(events)])
        con.commit(); con.close()

    def __call__(self, base_url, method, path, body=None, timeout=30):
        if path == '/api/config/status':
            return {'live_enabled': True, 'active_campaign_id': self.active,
                    'models': {'actor': self.actor, 'mechanic': base.EXPECTED_MECHANIC}}
        if path == '/api/campaigns' and method == 'POST':
            cid = f'campaign-{len(self.campaigns) + 1}'
            self.campaigns.append(cid)
            self.put('campaign_provenance', cid, {'aria_publication_enabled': self.aria})
            return {'campaign_id': cid, 'configuration_hash': self.config_hash}
        if path.endswith('/completion-study') and method == 'POST':
            cid = path.split('/')[3]
            # v4 is passed explicitly, every time (pitfall 69).
            assert body == {'execute_live': True, 'evidence_protocol': base.EVIDENCE_PROTOCOL,
                            'actor_context_protocol': base.ACTOR_CONTEXT}
            index = len(self.studies) + len([f for f in self.start_fails if f < 0]) + 1
            if index in self.start_fails and not self.adopt:
                self.start_fails.discard(index); self.start_fails.add(-index)
                raise OSError('start failed before the server saw it')
            sid = f'study-{len(self.studies) + 1}'
            self.clock += 1
            final = json.loads(json.dumps(self.outcomes.pop(0)))
            n = final.pop('evidence_count')
            for episode_id, events in (final.pop('_events', None) or {}).items():
                self.put_events(episode_id, events)
            final.update(study_id=sid, campaign_id=cid, created_at=f'2999-01-01T00:00:{self.clock:02d}',
                         evidence={f'{sid}-ep{i}': 'weave_verified' for i in range(n)})
            self.studies[sid] = final
            self.put('completion_studies', sid, final)
            for eid in final['evidence']:
                self.put('evidence', eid, {'source': 'weave_verified', 'source_project': self.project})
            if self.drift:
                eid = f'{sid}-drifted'
                self.put('episodes', eid, {'episode_id': eid, 'started_at': '2999-01-01T00:00:00Z', 'arm': 'L',
                                           'world_id': 'world-missing', 'verdict': {'decision_tick': 5, 'checks': []}})
                self.put_events(eid, [{'type': 'report_submitted', 'tick': 6}])
            self.ledgers[cid] = {'charged_dollar_upper_bound': self.spend, 'used_calls': 10, 'caps': {}}
            self.started.append(sid)
            self.active = cid
            if index in self.start_fails:
                self.start_fails.discard(index); raise TimeoutError('response lost after the server started it')
            return {**final, 'status': 'QUEUED', 'decision': 'PENDING'}
        if path.endswith('/completion-studies') and method == 'GET':
            cid = path.split('/')[3]
            found = [s for s in self.studies.values() if s['campaign_id'] == cid]
            if found and self.active == cid:
                self.active = None
            return found
        if path.startswith('/api/completion-studies/'):
            if self.on_poll:
                self.on_poll(self)
            self.active = None
            return self.studies[path.rsplit('/', 1)[1]]
        if path.endswith('/budget'):
            return self.ledgers.get(path.split('/')[3], NO_LEDGER)
        if path.endswith('/stop'):
            self.stops.append(path.split('/')[3]); self.active = None; return {}
        raise AssertionError(f'unexpected {method} {path}')


PROCESS = {'processes': [{'pid': 1, 'command': 'python -m uvicorn app.main:app', 'started_at': 'x'}]}


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


@pytest.fixture
def env(tmp_path, monkeypatch):
    brief = tmp_path / fixed.MECHANIC_BRIEF
    brief.parent.mkdir(parents=True)
    brief.write_text('the completion brief')
    protocol = tmp_path / fixed.PROTOCOL
    protocol.parent.mkdir(parents=True)
    protocol.write_text('phase 23 protocol')
    freeze_data = {'schema_version': 'faultlab-gate-freeze/v1', 'files': {fixed.MECHANIC_BRIEF: sha(brief)},
                   'fingerprints': {'scorer_hash': fixed.SCORER_HASH},
                   'functions': {base.ASSESS_PAIRS_KEY: {'text_sha256': base.ASSESS_PAIRS_TEXT_SHA256}}}
    freeze = tmp_path / 'freeze.json'
    freeze.write_text(json.dumps(freeze_data))
    settings_file = tmp_path / 'settings.json'
    settings_file.write_text('{}')
    store = tmp_path / 'artifacts' / 'lab.sqlite3'
    store.parent.mkdir()
    make_store(store)
    scripts = ROOT / 'scripts/experiments'
    pins = {'DECLARED_FREEZE_SHA256': sha(freeze), 'DECLARED_CONFIGURATION_HASH': CONFIG,
            'DECLARED_PROTOCOL_SHA256': sha(protocol),
            'DECLARED_GATE_FREEZE_SCRIPT_SHA256': sha(scripts / 'gate_freeze.py'),
            'DECLARED_DRIFT_CHECKER_SHA256': sha(scripts / 'check_clock_drift.py'),
            'DECLARED_INGESTION_CHECK_SHA256': sha(scripts / 'check_ingestion_health.py'),
            'DECLARED_SETTINGS_SHA256': sha(settings_file), 'DECLARED_MECHANIC_BRIEF_SHA256': sha(brief)}
    review = tmp_path / 'review.json'

    def write_review(**changes):
        record = {'status': 'approved', 'approved_by': 'test reviewer', 'protocol_sha256': pins['DECLARED_PROTOCOL_SHA256'],
                  'runner_sha256': sha(ROOT / 'scripts/experiments/run_full_loop_fixed_n.py'),
                  'gate_freeze_file_sha256': pins['DECLARED_FREEZE_SHA256'], 'configuration_hash': CONFIG}
        record.update(changes)
        review.write_text(json.dumps({k: v for k, v in record.items() if v is not None}))
    write_review()
    monkeypatch.setattr(fixed, 'ROOT', tmp_path)
    for name, value in pins.items():
        monkeypatch.setattr(fixed, name, value)
    monkeypatch.setattr(fixed, 'N_ATTEMPTS', 6)
    monkeypatch.setattr(fixed, 'ingestion_health', lambda: {'exit_status': 0, 'output': 'HEALTHY'})
    monkeypatch.setattr(base, 'gate_freeze', lambda: json.loads(json.dumps(freeze_data)))
    monkeypatch.setattr(base, 'check_backend_process', lambda: PROCESS)
    monkeypatch.setattr(base.time, 'sleep', lambda s: None)
    monkeypatch.setattr(fixed.signal, 'signal', lambda *a: None)
    import app.config
    monkeypatch.setattr(app.config.Settings, 'from_env', classmethod(
        lambda cls: type('S', (), {'wandb_entity': 'entity', 'project_path': base.EXPECTED_PROJECT})()))
    artifacts = tmp_path / 'artifacts'

    def run(backend, *extra, out='phase23-test'):
        monkeypatch.setattr(base, 'api', backend)
        monkeypatch.setattr(sys, 'argv', [
            'run_full_loop_fixed_n.py', '--out', str(artifacts / out), '--store', str(store),
            '--settings', str(settings_file), '--expect-freeze', str(freeze), '--review-record', str(review),
            '--poll', '0', '--idle-grace', '2', '--execute-live', '--confirm-entity', 'entity', *extra])
        fixed.main()
        return json.loads((artifacts / out / fixed.MANIFEST_NAME).read_text())
    run.store = store
    run.artifacts = artifacts
    run.brief = brief
    run.freeze = freeze
    run.freeze_data = freeze_data
    run.write_review = write_review
    run.manifest = lambda out='phase23-test': artifacts / out / fixed.MANIFEST_NAME
    return run


# ----------------------------------------------------------------- the fixed-N loop

def test_a_certified_study_never_stops_the_run_and_every_one_is_counted(env):
    backend = FakeBackend(env.store, [OK, certified_study(DD62), DEAD, certified_study('b' * 64),
                                      certified_study('c' * 64), SOURCE_ONLY, OK, OK])
    manifest = env(backend)
    assert manifest['stop_reason'] == 'fixed_n' and len(backend.started) == 6 and len(backend.outcomes) == 2
    assert [r['attempt'] for r in manifest['attempts']] == [1, 2, 3, 4, 5, 6]
    assert [r['certified'] for r in manifest['attempts']] == [False, True, False, True, True, False]
    assert all(r['post_checks'] == 'passed' for r in manifest['attempts'])
    s = manifest['summary']
    assert (s['primary']['certified'], s['primary']['attempts'], s['primary']['truncated']) == (3, 6, False)
    assert s['primary']['statement'].startswith('3 of 6 attempts produced a certified completion repair')
    assert s['certified_attempts'] == [2, 4, 5]
    assert s['secondary_pooled_with_phase17']['certified'] == 4 and s['secondary_pooled_with_phase17']['attempts'] == 15
    # Routing: the first NEW certified hash; the Phase 17 policy is counted and never routed.
    r = s['routing']
    assert (r['policy_hash'], r['attempt'], r['study_id'], r['routable'], r['run_final']) == ('b' * 64, 4, 'study-4', True, True)
    assert r['excluded_certified_attempts'] == [{'attempt': 2, 'policy_hash': DD62}]
    assert s['distinct_hashes']['phase17_policy']['certified_attempts'] == [2]
    assert s['distinct_hashes']['phase17_policy']['routed'] is False
    assert s['funnel']['observed_improvement'] == 4 and s['funnel']['observed_improvement_without_fresh_gain'] == 1
    assert s['cost']['total_charged_upper_bound'] == pytest.approx(12.0)
    assert s['cost']['per_certification'] == pytest.approx(4.0)
    assert not backend.stops
    assert fixed.reconcile(manifest, env.store) == ([], [])


def test_the_run_is_exactly_the_declared_thirty_attempts_and_a_final_run_cannot_resume(env, monkeypatch):
    monkeypatch.setattr(fixed, 'N_ATTEMPTS', 30)
    backend = FakeBackend(env.store, [certified_study('b' * 64)] + [OK] * 40)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'fixed_n' and len(backend.started) == 30
    assert manifest['declared']['n_attempts'] == 30 and manifest['summary']['primary']['planned'] == 30
    assert manifest['summary']['primary']['statement'].startswith('1 of 30 attempts')
    with pytest.raises(SystemExit, match='final'):
        env(backend, '--resume', '--after-abort')
    assert len(backend.started) == 30


def test_the_spend_guard_truncates_and_says_so(env, monkeypatch):
    monkeypatch.setattr(fixed, 'N_ATTEMPTS', 30)
    backend = FakeBackend(env.store, [OK] * 30, spend=10.0)
    manifest = env(backend)
    # 0, 10, ..., 130 start; at 140 + 11 > 150 no fifteenth study starts.
    assert manifest['stop_reason'] == 'spend_guard' and len(backend.started) == 14
    p = manifest['summary']['primary']
    assert p['truncated'] and p['attempts'] == 14
    assert p['statement'].startswith('Truncated at n=14 by the $150 spend guard: 0 of 14 attempts')
    assert manifest['total_charged_upper_bound'] == pytest.approx(140.0) and not backend.stops
    with pytest.raises(SystemExit, match='final'):
        env(backend, '--resume', '--after-abort')


def test_five_consecutive_infrastructure_failures_stop_the_run_and_four_do_not(env, monkeypatch):
    monkeypatch.setattr(fixed, 'N_ATTEMPTS', 12)
    backend = FakeBackend(env.store, [DEAD] * 4 + [OK] + [DEAD] * 5 + [OK, OK, OK])
    manifest = env(backend)
    assert manifest['stop_reason'] == 'breaker' and len(backend.started) == 10
    assert 'consecutive studies died' in manifest['abort_detail']
    assert manifest['summary']['primary']['statement'].startswith('Stopped at n=10 after 5 consecutive')
    assert not manifest['summary']['routing']['run_final']
    with pytest.raises(SystemExit, match='--after-abort'):
        env(backend, '--resume')
    resumed = env(backend, '--resume', '--after-abort')
    assert resumed['stop_reason'] == 'fixed_n' and [r['attempt'] for r in resumed['attempts']] == list(range(1, 13))
    assert resumed['sessions'][1]['previous_stop'] == 'breaker' and 'abort_detail' not in resumed
    assert 'consecutive' in resumed['sessions'][0]['abort_detail']


def test_failed_campaign_creates_count_toward_the_breaker(env, monkeypatch):
    backend = FakeBackend(env.store, [OK] * 6)
    original = backend.__call__

    def no_campaigns(base_url, method, path, body=None, timeout=30):
        if path == '/api/campaigns' and method == 'POST':
            raise OSError('refused')
        return original(base_url, method, path, body, timeout)
    manifest = env(no_campaigns)
    assert manifest['stop_reason'] == 'breaker' and len(manifest['attempts']) == 5 and not backend.started
    assert all(r['error'].startswith('campaign create') for r in manifest['attempts'])


def test_distinct_hashes_count_redraws_and_duplicates(env):
    a, b = 'a' * 64, 'b' * 64
    outcomes = [
        study(stage='candidate-2', candidates=[candidate(STEP_RULES, 'NO_CHANGE', 'NO_CHANGE', a),
                                               candidate(STEP_RULES, 'DUPLICATE', None, a)]),
        certified_study(DD62),
        study(decision='OBSERVED_IMPROVEMENT', stage='validation', l={'notification-2': 3, 'healthy': 3},
              b0={'healthy': 3}, selected=b,
              candidates=[candidate(NO_STEP_RULES, 'REJECTED', 'NO_CHANGE', a),
                          candidate(STEP_RULES, 'OBSERVED_IMPROVEMENT', 'SOURCE_QUALIFIED', b)]),
        study(stage='validation', decision='NO_CHANGE', selected=DD62, l={'notification-2': 3},
              candidates=[candidate(STEP_RULES, 'NO_CHANGE', 'SOURCE_QUALIFIED', DD62)]),
        OK, OK]
    manifest = env(FakeBackend(env.store, outcomes))
    d = manifest['summary']['distinct_hashes']
    assert (d['draws'], d['distinct_policies'], d['distinct_first_proposals'], d['distinct_step_policies']) == (6, 3, 2, 3)
    assert d['within_study_duplicates'] == 1
    assert d['redrawn_across_attempts'] == {a: [1, 3], DD62: [2, 4]}
    assert [x['attempt'] for x in d['phase17_policy']['draws']] == [2, 4]
    assert d['phase17_policy']['certified_attempts'] == [2] and d['distinct_certified_policies'] == 1
    # attempt 3 passed the gate on the source case alone: OBSERVED_IMPROVEMENT, not certified
    routing = manifest['summary']['routing']
    assert routing['policy_hash'] is None and not routing['routable']
    assert routing['excluded_certified_attempts'] == [{'attempt': 2, 'policy_hash': DD62}]


def test_the_stage_funnel_separates_step_present_from_step_fired_and_clean_from_dirty(env, monkeypatch):
    monkeypatch.setattr(fixed, 'N_ATTEMPTS', 2)
    gated, firing = 'g' * 64, 'f' * 64
    controls = [trial('controls', 'B0', f'e1-c{i}') for i in range(6)]
    cand1 = [trial('candidate-1', arm, f'e1-k1{arm}{i}') for i in range(3) for arm in ('B0', 'L')]
    cand2 = [trial('candidate-2', arm, f'e1-k2{arm}{i}') for i in range(3) for arm in ('B0', 'L')]
    dirty = [trial('validation', arm, f'e1-v{arm}{i}', triggered=not (arm == 'L' and i == 0))
             for i in range(3) for arm in ('B0', 'L')]
    first = study(decision='INCOMPLETE', status='INCOMPLETE', stage='validation', selected=firing,
                  trial_rows=controls + cand1 + cand2 + dirty,
                  candidates=[candidate(STEP_RULES, 'REJECTED', 'NO_CHANGE', gated),
                              candidate(STEP_RULES, 'INCOMPLETE', 'SOURCE_QUALIFIED', firing)],
                  events={**{f'e1-k1L{i}': GATED for i in range(3)}, **{f'e1-k2L{i}': FIRES for i in range(3)},
                          **{f'e1-vL{i}': FIRES for i in (1, 2)}})
    first['validation_assessment'] = {'decision': 'INCOMPLETE', 'by_case': {}}
    source = [trial('candidate-1', arm, f'e2-k1{arm}{i}') for i in range(3) for arm in ('B0', 'L')]
    clean = [trial('validation', arm, f'e2-v{arm}{i}') for i in range(3) for arm in ('B0', 'L')]
    second = certified_study('b' * 64, trial_rows=source + clean,
                             events={f'e2-{s}L{i}': FIRES for i in range(3) for s in ('k1', 'v')})
    manifest = env(FakeBackend(env.store, [first, second]))
    f = manifest['summary']['funnel']
    assert (f['step_present'], f['step_tested_at_source'], f['step_fired_at_source']) == (3, 3, 2)
    assert f['step_present_never_fired_at_source'] == 1                     # gated on PENDING: never fired
    assert (f['source_qualified_with_step'], f['source_complete_pairs_with_step']) == (2, 3)
    assert (f['validation_assessed'], f['validation_clean'], f['validation_dirty']) == (2, 1, 1)
    assert (f['accepted_on_clean'], f['accepted_on_dirty']) == (1, 0) and 'by construction' in f['accepted_on_dirty_note']
    assert f['validation_step_fired_in'] == 5 and f['funnel_unavailable'] == 0
    row = manifest['attempts'][0]['funnel']
    assert [c['step_fired_in'] for c in row['candidates']] == [0, 3]
    assert [c['retry_executed_in'] for c in row['candidates']] == [0, 3]
    assert row['validation']['invalid_trials'] == 1 and row['validation']['batch'] == 'dirty'
    assert manifest['attempts'][1]['funnel']['validation']['batch'] == 'clean'
    u = manifest['summary']['untriggered']
    assert (u['fault_bearing_episodes'], u['untriggered']) == (24 + 12, 1)


def test_a_study_on_the_wrong_actor_context_aborts_and_is_stopped(env):
    backend = FakeBackend(env.store, [study(protocol='faultlab-actor-context/v1'), OK, OK])
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and 'actor_context_protocol' in manifest['abort_detail']
    assert backend.stops == ['campaign-1']
    with pytest.raises(SystemExit, match='--after-abort'):
        env(backend, '--resume')


def test_a_signal_leaves_the_running_study_alone_and_resume_recovers_it_then_runs_to_n(env, monkeypatch):
    monkeypatch.setattr(fixed, 'N_ATTEMPTS', 3)
    backend = FakeBackend(env.store, [certified_study('b' * 64), OK, OK])

    def detach_on_first_poll(fake):
        fake.on_poll = None
        raise base.Detached(15)
    backend.on_poll = detach_on_first_poll
    first = env(backend)
    assert first['stop_reason'] == 'aborted' and 'left running' in first['abort_detail']
    assert not backend.stops and first['attempts'][0].get('status') is None
    assert 'skipped' in first['clock_drift']                      # the drift check waits for the study
    with pytest.raises(SystemExit, match='Another execution is active'):
        env(backend, '--resume', '--after-abort')
    backend.active = None
    resumed = env(backend, '--resume', '--after-abort')
    row = resumed['attempts'][0]
    assert row['recovered'] and row['certified'] and row['post_checks'].startswith('passed on recovery')
    assert 'funnel' in row
    assert resumed['stop_reason'] == 'fixed_n' and len(backend.started) == 3     # did not stop at the success
    assert resumed['summary']['routing']['routable']


def test_a_finished_outcome_is_saved_and_its_post_checks_are_run_when_they_can_be(env):
    backend = FakeBackend(env.store, [certified_study('b' * 64), OK])
    calls = {'n': 0}
    original = backend.__call__

    def flaky(base_url, method, path, body=None, timeout=30):
        if path.startswith('/api/completion-studies/'):
            calls['n'] += 1
            if calls['n'] == 2:                   # poll #1 sees it finish; the re-read after idle fails
                raise OSError('dropped')
        return original(base_url, method, path, body, timeout)
    manifest = env(flaky)
    row = manifest['attempts'][0]
    assert manifest['stop_reason'] == 'aborted' and 're-read' in manifest['abort_detail']
    assert row['certified'] is True and row['post_checks'].startswith('passed on recovery')
    assert len(backend.started) == 1 and not backend.stops
    assert not manifest['summary']['routing']['routable']          # the run is not final


def test_a_failed_post_finish_check_uncertifies_the_row_and_reconciles(env):
    backend = FakeBackend(env.store, [certified_study('b' * 64), OK], project='someone/else')
    manifest = env(backend)
    row = manifest['attempts'][0]
    assert manifest['stop_reason'] == 'aborted' and row['certified'] is False and row['post_checks'].startswith('failed')
    assert manifest['summary']['primary']['certified'] == 0 and manifest['summary']['routing']['policy_hash'] is None
    # Declared case (i): not certified. It is not a manifest/store discrepancy, so an approved
    # resume is not blocked by it.
    assert fixed.reconcile(manifest, env.store) == ([], [])


def test_a_start_that_reached_the_server_is_adopted_not_lost(env):
    backend = FakeBackend(env.store, [certified_study('b' * 64)] + [OK] * 5, start_fails={1}, adopt=True)
    manifest = env(backend)
    row = manifest['attempts'][0]
    assert row['adopted_after_start_error'] and row['start_error'] == 'TimeoutError' and row['certified']
    assert manifest['stop_reason'] == 'fixed_n' and len(backend.started) == 6 and 'error' not in row


def test_a_start_that_never_reached_the_server_is_a_death_and_the_run_continues(env):
    backend = FakeBackend(env.store, [OK] * 6, start_fails={1})
    manifest = env(backend)
    assert manifest['stop_reason'] == 'fixed_n' and len(manifest['attempts']) == 6 and len(backend.started) == 5
    assert manifest['attempts'][0]['error'].startswith('study start') and manifest['attempts'][0]['study_id'] is None
    assert manifest['summary']['funnel']['infrastructure_deaths'] == 1
    assert manifest['total_charged_upper_bound'] == pytest.approx(10.0)    # the ledger-less campaign is $0


def test_a_configuration_abort_does_not_block_a_later_approved_resume(env):
    backend = FakeBackend(env.store, [OK] * 6, config_hash='d' * 64)
    first = env(backend)
    assert first['stop_reason'] == 'aborted' and 'configuration_hash' in first['abort_detail'] and not backend.started
    backend.config_hash = CONFIG
    resumed = env(backend, '--resume', '--after-abort')
    assert resumed['stop_reason'] == 'fixed_n' and len(backend.started) == 5 and len(resumed['attempts']) == 6


def test_the_clock_drift_check_runs_after_the_session_and_is_recorded_not_acted_on(env, monkeypatch):
    monkeypatch.setattr(fixed, 'N_ATTEMPTS', 2)
    clean = env(FakeBackend(env.store, [OK, OK]), out='phase23-clean')
    assert clean['clock_drift']['exit_status'] == 0 and clean['clock_drift']['since'] == clean['started_at']
    assert '--worlds' in clean['clock_drift']['command'] and clean['sessions'][0]['clock_drift'] == clean['clock_drift']
    assert clean['sessions'][0]['ingestion_health']['exit_status'] == 0


def test_a_drifted_episode_is_reported_and_earns_no_rerun(env, monkeypatch):
    monkeypatch.setattr(fixed, 'N_ATTEMPTS', 2)
    manifest = env(FakeBackend(env.store, [OK, OK], drift=True))
    drift = manifest['clock_drift']
    assert manifest['stop_reason'] == 'fixed_n' and len(manifest['attempts']) == 2
    assert drift['drifted'] == 2 and drift['exit_status'] == 1 and drift['missing_worlds'] == 2


def test_unhealthy_ingestion_refuses_before_any_campaign_or_record(env, monkeypatch):
    monkeypatch.setattr(fixed, 'ingestion_health', lambda: {'exit_status': 2, 'output': 'DEGRADED'})
    backend = FakeBackend(env.store, [OK])
    with pytest.raises(SystemExit, match='check_ingestion_health'):
        env(backend)
    assert not backend.campaigns and not env.manifest().exists()


def test_unhealthy_ingestion_on_a_resume_refuses_but_keeps_the_run_record(env, monkeypatch):
    """Review round 2: only a fresh launch's claim is removed on a refusal. On --resume the record is a
    retained, possibly paid run and must survive the refusal unchanged."""
    backend = FakeBackend(env.store, [OK] * 6, config_hash='d' * 64)
    first = env(backend)
    assert first['stop_reason'] == 'aborted'
    before = env.manifest().read_text()
    backend.config_hash = CONFIG
    monkeypatch.setattr(fixed, 'ingestion_health', lambda: {'exit_status': 2, 'output': 'DEGRADED'})
    with pytest.raises(SystemExit, match='check_ingestion_health'):
        env(backend, '--resume', '--after-abort')
    assert env.manifest().exists() and env.manifest().read_text() == before
    assert len(backend.campaigns) == 1


# ----------------------------------------------------------------- refusals before any spend

@pytest.mark.parametrize('pin', FREEZE_TIME_PINS + ('DECLARED_MECHANIC_BRIEF_SHA256',))
def test_a_placeholder_pin_refuses_a_live_run(env, monkeypatch, pin):
    monkeypatch.setattr(fixed, pin, fixed.PLACEHOLDER)
    backend = FakeBackend(env.store, [OK])
    with pytest.raises(SystemExit, match=f'placeholder.*{pin}'):
        env(backend)
    assert not backend.campaigns and not env.manifest().exists()


def test_a_malformed_pin_is_refused_like_a_placeholder(env, monkeypatch):
    monkeypatch.setattr(fixed, 'DECLARED_CONFIGURATION_HASH', 'c4169ee4…')
    with pytest.raises(SystemExit, match='DECLARED_CONFIGURATION_HASH'):
        env(FakeBackend(env.store, [OK]))


@pytest.mark.parametrize('change,match', [
    ({'status': 'draft'}, "status 'approved'"),
    ({'approved_by': ' '}, 'approved_by'),
    ({'runner_sha256': '0' * 64}, 'runner_sha256'),
    ({'protocol_sha256': None}, 'protocol_sha256'),
    ({'configuration_hash': 'e' * 64}, 'configuration_hash'),
])
def test_the_review_record_must_approve_this_runner_and_protocol(env, change, match):
    env.write_review(**change)
    backend = FakeBackend(env.store, [OK])
    with pytest.raises(SystemExit, match=match):
        env(backend)
    assert not backend.campaigns


def test_the_mechanic_brief_must_be_byte_identical_to_phase17(env):
    env.brief.write_text('an edited brief')
    backend = FakeBackend(env.store, [OK])
    with pytest.raises(SystemExit, match='DECLARED_MECHANIC_BRIEF_SHA256'):
        env(backend)
    assert not backend.campaigns


@pytest.mark.parametrize('section,key,value,match', [
    ('files', fixed.MECHANIC_BRIEF, '0' * 64, 'Mechanic brief'),
    ('fingerprints', 'scorer_hash', '0' * 64, 'scorer_hash'),
    ('functions', base.ASSESS_PAIRS_KEY, {'text_sha256': '0' * 64}, 'unchanged assess_pairs'),
])
def test_a_freeze_without_the_unchanged_gate_scorer_or_brief_is_refused(env, monkeypatch, section, key, value, match):
    data = json.loads(json.dumps(env.freeze_data))
    data[section][key] = value
    env.freeze.write_text(json.dumps(data))
    monkeypatch.setattr(fixed, 'DECLARED_FREEZE_SHA256', sha(env.freeze))
    env.write_review(gate_freeze_file_sha256=sha(env.freeze))
    with pytest.raises(SystemExit, match=match):
        env(FakeBackend(env.store, [OK]))


def test_code_that_differs_from_the_reviewed_freeze_refuses_to_start(env, monkeypatch):
    monkeypatch.setattr(base, 'gate_freeze', lambda: {**env.freeze_data, 'files': {'x': 1}})
    backend = FakeBackend(env.store, [OK])
    with pytest.raises(SystemExit, match='differs from the reviewed freeze'):
        env(backend)
    assert not backend.campaigns


def test_the_output_prefix_and_the_rerun_guard(env):
    backend = FakeBackend(env.store, [OK] * 12)
    with pytest.raises(SystemExit, match='must be artifacts/phase23-'):
        env(backend, out='phase17-2026-10-02')
    env(backend)
    with pytest.raises(SystemExit, match='refusing to overwrite'):
        env(backend)
    with pytest.raises(SystemExit, match='Another Phase 23 run exists'):
        env(backend, out='phase23-other')
    assert len(backend.started) == 6


def test_a_resume_can_never_change_the_declared_design(env, monkeypatch):
    backend = FakeBackend(env.store, [study(protocol='faultlab-actor-context/v1')] + [OK] * 6)
    env(backend)
    monkeypatch.setattr(fixed, 'N_ATTEMPTS', 7)
    with pytest.raises(SystemExit, match='declared parameters'):
        env(backend, '--resume', '--after-abort')


# ----------------------------------------------------------------- fixed-N reconcile

def test_reconcile_catches_store_disagreement_gaps_untracked_studies_and_a_rewritten_route(env, monkeypatch):
    monkeypatch.setattr(fixed, 'N_ATTEMPTS', 3)
    backend = FakeBackend(env.store, [OK, certified_study('b' * 64), OK])
    manifest = env(backend)
    assert fixed.reconcile(manifest, env.store) == ([], [])
    # a later phase's study, after the final run ended, is outside the window
    backend.put('completion_studies', 'later', {'replay_of': None, 'created_at': '9999-01-01T00:00:00+00:00'})
    assert fixed.reconcile(manifest, env.store) == ([], [])
    tampered = json.loads(json.dumps(manifest))
    tampered['attempts'][1]['decision'] = 'NO_CHANGE'
    tampered['summary']['routing']['policy_hash'] = 'z' * 64
    problems, _ = fixed.reconcile(tampered, env.store)
    assert any('decision manifest' in p for p in problems) and any('routing field' in p for p in problems)
    gap = json.loads(json.dumps(manifest))
    gap['attempts'].pop(0)
    problems, _ = fixed.reconcile(gap, env.store)
    assert any('attempt numbers' in p for p in problems)
    open_run = {**json.loads(json.dumps(manifest)), 'stop_reason': 'aborted'}
    backend.put('completion_studies', 'stray', {'replay_of': None, 'created_at': manifest['ended_at']})
    assert fixed.reconcile(open_run, env.store)[1] == ['later', 'stray']


def test_plan_is_dry_and_shows_every_unfilled_pin(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(base, 'api', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no HTTP in a plan')))
    monkeypatch.setattr(fixed, 'ingestion_health', lambda: (_ for _ in ()).throw(AssertionError('no checks in a plan')))
    monkeypatch.setattr(sys, 'argv', ['run_full_loop_fixed_n.py', '--out', str(tmp_path / 'p'), '--plan'])
    assert fixed.main() == 0
    text = capsys.readouterr().out
    assert 'Dry plan only' in text and not (tmp_path / 'p').exists()
    # Review round 2: the count follows the pins as shipped, so the test holds before the freeze (six
    # placeholders) and after F8 fills them (none); the fixed six-count failed the moment F8 filled them.
    unfilled = sum(1 for line in text.splitlines() if line.startswith('pin') and 'UNFILLED' in line)
    assert unfilled == len(fixed.unfilled_pins()) and set(fixed.unfilled_pins()) <= set(FREEZE_TIME_PINS)
    assert 'a CERTIFIED study never stops the run' in text


def test_a_plan_with_every_pin_filled_shows_no_unfilled_pin(tmp_path, monkeypatch, capsys):
    """What F8's re-run sees once the freeze has filled the six pins (review round 2)."""
    monkeypatch.setattr(base, 'api', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no HTTP in a plan')))
    for name in FREEZE_TIME_PINS:
        monkeypatch.setattr(fixed, name, 'e' * 64)
    monkeypatch.setattr(sys, 'argv', ['run_full_loop_fixed_n.py', '--out', str(tmp_path / 'p'), '--plan'])
    assert fixed.main() == 0
    text = capsys.readouterr().out
    assert fixed.unfilled_pins() == []
    assert not [line for line in text.splitlines() if line.startswith('pin') and 'UNFILLED' in line]
    assert sum(1 for line in text.splitlines() if line.startswith('pin')) == len(fixed.PINS)


# ----------------------------------------------------------------- review round 1

def test_a_stop_during_campaign_create_is_labelled_counted_and_never_blocks(env, monkeypatch):
    """A Ctrl-C while POST /api/campaigns is in flight leaves a row with no campaign. It is
    labelled, stays in the denominator (section 4.1), is not an infrastructure death, and the
    resumed run is final and routable."""
    monkeypatch.setattr(fixed, 'N_ATTEMPTS', 4)
    backend = FakeBackend(env.store, [certified_study('b' * 64), OK, OK, OK])
    state = {'fired': False}

    def ctrl_c_on_first_create(base_url, method, path, body=None, timeout=30):
        if path == '/api/campaigns' and method == 'POST' and not state['fired']:
            state['fired'] = True
            raise KeyboardInterrupt
        return backend(base_url, method, path, body, timeout)
    first = env(ctrl_c_on_first_create)
    assert first['stop_reason'] == 'aborted' and first['attempts'][0]['error'] == fixed.INTERRUPTED_BEFORE_CREATE
    resumed = env(ctrl_c_on_first_create, '--resume', '--after-abort')
    assert resumed['stop_reason'] == 'fixed_n' and len(backend.started) == 3
    funnel = resumed['summary']['funnel']
    assert resumed['summary']['primary']['attempts'] == 4 and funnel['infrastructure_deaths'] == 0
    assert funnel['runner_side_no_study'] == 1 and funnel['attempts_without_study'] == {fixed.INTERRUPTED_BEFORE_CREATE: 1}
    assert resumed['summary']['routing']['routable'] and resumed['summary']['routing']['attempt'] == 2
    assert fixed.reconcile(resumed, env.store) == ([], [])


def test_a_phantom_row_left_by_a_hard_kill_is_labelled_on_resume(env, monkeypatch):
    """A kill -9 during campaign create leaves 'running' and an unlabelled row; resume labels it."""
    monkeypatch.setattr(fixed, 'N_ATTEMPTS', 3)
    backend = FakeBackend(env.store, [OK] * 4)
    state = {'creates': 0}

    def ctrl_c_on_second_create(base_url, method, path, body=None, timeout=30):
        if path == '/api/campaigns' and method == 'POST':
            state['creates'] += 1
            if state['creates'] == 2:
                raise KeyboardInterrupt
        return backend(base_url, method, path, body, timeout)
    first = env(ctrl_c_on_second_create)
    killed = json.loads(json.dumps(first))
    killed['stop_reason'] = 'running'
    killed['attempts'][1].pop('error')                  # as if killed before the abort path ran
    assert killed['attempts'][1] == {'attempt': 2, 'campaign_id': None, 'study_id': None, 'spent_before': 2.0}
    env.manifest().write_text(json.dumps(killed))
    resumed = env(backend, '--resume', '--after-abort')
    assert resumed['attempts'][1]['error'] == fixed.INTERRUPTED_BEFORE_CREATE
    assert resumed['stop_reason'] == 'fixed_n' and len(resumed['attempts']) == 3 and len(backend.started) == 2


def test_a_runner_refusal_is_in_the_denominator_but_is_not_a_death(env):
    backend = FakeBackend(env.store, [OK] * 6, config_hash='d' * 64)
    first = env(backend)
    assert first['attempts'][0]['error'] == fixed.CONFIGURATION_MISMATCH and fixed.runner_side(first['attempts'][0])
    backend.config_hash = CONFIG
    resumed = env(backend, '--resume', '--after-abort')
    funnel = resumed['summary']['funnel']
    assert resumed['summary']['primary']['attempts'] == 6 and len(backend.started) == 5
    assert funnel['infrastructure_deaths'] == 0 and funnel['runner_side_no_study'] == 1


def test_a_runner_refusal_neither_counts_toward_nor_resets_the_breaker(env, monkeypatch):
    monkeypatch.setattr(fixed, 'N_ATTEMPTS', 12)
    backend = FakeBackend(env.store, [DEAD] * 4 + [OK] * 8)
    original = backend.__call__
    state = {'creates': 0}

    def refuse_fifth(base_url, method, path, body=None, timeout=30):
        result = original(base_url, method, path, body, timeout)
        if path == '/api/campaigns' and method == 'POST':
            state['creates'] += 1
            if state['creates'] == 5:
                return {**result, 'configuration_hash': 'd' * 64}
        return result
    first = env(refuse_fifth)
    assert first['stop_reason'] == 'aborted' and len(backend.started) == 4
    backend.outcomes = [DEAD] + [OK] * 7
    resumed = env(refuse_fifth, '--resume', '--after-abort')
    # 4 deaths, the refusal (skipped), then 1 more death: the fifth consecutive death trips it.
    assert resumed['stop_reason'] == 'breaker' and len(backend.started) == 5


def test_an_aborts_reason_is_on_disk_before_the_in_flight_stop_waits(env, monkeypatch):
    """A second Ctrl-C during the post-abort wait must not leave 'running' with no reason."""
    backend = FakeBackend(env.store, [OK] * 6)

    def interrupt(fake):
        fake.on_poll = None
        fake.active = 'campaign-1'
        raise KeyboardInterrupt
    backend.on_poll = interrupt
    original = backend.__call__

    def second_interrupt_in_the_wait(base_url, method, path, body=None, timeout=30):
        if path.endswith('/stop'):
            original(base_url, method, path, body, timeout)
            backend.active = 'campaign-1'
            return {}
        if path == '/api/config/status' and backend.stops:
            raise KeyboardInterrupt
        return original(base_url, method, path, body, timeout)
    with pytest.raises(KeyboardInterrupt):
        env(second_interrupt_in_the_wait)
    on_disk = json.loads(env.manifest().read_text())
    assert on_disk['stop_reason'] == 'aborted' and on_disk['abort_detail'] == 'interrupted by operator (Ctrl-C)'
    assert backend.stops == ['campaign-1']


def test_the_run_record_is_claimed_exclusively_before_the_slow_checks(env, monkeypatch):
    seen = {}

    def ingestion():
        seen['claimed'] = json.loads(env.manifest().read_text())['stop_reason']
        return {'exit_status': 0, 'output': 'HEALTHY'}
    monkeypatch.setattr(fixed, 'ingestion_health', ingestion)
    monkeypatch.setattr(fixed, 'N_ATTEMPTS', 1)
    env(FakeBackend(env.store, [OK]))
    assert seen['claimed'] == 'starting'


def test_a_launch_that_loses_the_claim_refuses(tmp_path):
    out = tmp_path / 'artifacts' / 'phase23-a'
    record = {'stop_reason': 'starting'}
    fixed.claim(out, out / fixed.MANIFEST_NAME, record)
    with pytest.raises(SystemExit, match='created by another launch'):
        fixed.claim(out, out / fixed.MANIFEST_NAME, record)
    other = tmp_path / 'artifacts' / 'phase23-b'
    with pytest.raises(SystemExit, match='Another Phase 23 run exists'):
        fixed.claim(other, other / fixed.MANIFEST_NAME, record)
    assert not (other / fixed.MANIFEST_NAME).exists() and (out / fixed.MANIFEST_NAME).exists()


def test_spend_carries_across_an_approved_resume(env, monkeypatch):
    """The $150 guard counts every earlier session's campaigns (review round 1, mutant F03)."""
    monkeypatch.setattr(fixed, 'N_ATTEMPTS', 30)
    backend = FakeBackend(env.store, [OK] * 40, spend=10.0)
    original = backend.__call__
    state = {'creates': 0}

    def mismatch_on_fourth_create(base_url, method, path, body=None, timeout=30):
        result = original(base_url, method, path, body, timeout)
        if path == '/api/campaigns' and method == 'POST':
            state['creates'] += 1
            if state['creates'] == 4:
                return {**result, 'configuration_hash': 'd' * 64}
        return result
    first = env(mismatch_on_fourth_create)
    assert first['stop_reason'] == 'aborted' and len(backend.started) == 3
    resumed = env(mismatch_on_fourth_create, '--resume', '--after-abort')
    assert resumed['stop_reason'] == 'spend_guard' and len(backend.started) == 14
    assert resumed['total_charged_upper_bound'] == pytest.approx(140.0)
    assert resumed['summary']['primary']['attempts'] == 15


def test_resume_refuses_while_the_store_holds_an_untracked_study(env):
    backend = FakeBackend(env.store, [study(protocol='faultlab-actor-context/v1')] + [OK] * 6)
    first = env(backend)
    assert first['stop_reason'] == 'aborted'
    backend.put('completion_studies', 'stray', {'replay_of': None, 'created_at': first['started_at']})
    with pytest.raises(SystemExit, match='manifest and store disagree'):
        env(backend, '--resume', '--after-abort')


def test_a_real_sigterm_leaves_the_running_study_for_recovery(env, monkeypatch):
    """The handler is really installed: a real SIGTERM mid-poll detaches (review round 1, F22)."""
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP)}
    monkeypatch.setattr(fixed.signal, 'signal', REAL_SIGNAL)
    backend = FakeBackend(env.store, [OK] * 6)

    def terminate(fake):
        fake.on_poll = None
        os.kill(os.getpid(), signal.SIGTERM)

    def no_handler(signum, frame):
        raise AssertionError('the runner installed no SIGTERM handler')
    backend.on_poll = terminate
    try:
        REAL_SIGNAL(signal.SIGTERM, no_handler)        # replaced by the runner's own, or the test fails
        manifest = env(backend)
        assert signal.getsignal(signal.SIGTERM) is signal.SIG_IGN      # a second signal is ignored
    finally:
        for sig, handler in saved.items():
            REAL_SIGNAL(sig, handler)
    assert manifest['stop_reason'] == 'aborted' and 'signal 15' in manifest['abort_detail']
    assert not backend.stops and manifest['attempts'][0].get('status') is None


def test_ctrl_c_stops_the_running_study(env):
    backend = FakeBackend(env.store, [OK] * 6)

    def interrupt(fake):
        fake.on_poll = None
        fake.active = 'campaign-1'
        raise KeyboardInterrupt
    backend.on_poll = interrupt
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and manifest['abort_detail'] == 'interrupted by operator (Ctrl-C)'
    assert backend.stops == ['campaign-1']


def changing_process(monkeypatch, change_at):
    calls = {'n': 0}

    def process():
        calls['n'] += 1
        return PROCESS if calls['n'] < change_at else {'processes': [{'pid': 2, 'command': 'uvicorn', 'started_at': 'y'}]}
    monkeypatch.setattr(base, 'check_backend_process', process)


def test_a_backend_process_that_changes_during_a_study_uncertifies_it(env, monkeypatch):
    changing_process(monkeypatch, 3)          # 1 start of run, 2 before attempt 1, 3 after it finishes
    backend = FakeBackend(env.store, [certified_study('b' * 64)] + [OK] * 5)
    manifest = env(backend)
    row = manifest['attempts'][0]
    assert manifest['stop_reason'] == 'aborted' and 'process changed' in manifest['abort_detail']
    assert row['certified'] is False and row['post_checks'].startswith('failed') and len(backend.started) == 1


def test_a_backend_process_that_changes_between_attempts_starts_nothing_more(env, monkeypatch):
    changing_process(monkeypatch, 4)          # 4 = before attempt 2
    backend = FakeBackend(env.store, [certified_study('b' * 64)] + [OK] * 5)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and 'process changed' in manifest['abort_detail']
    assert manifest['attempts'][0]['post_checks'] == 'passed' and len(backend.started) == 1
    assert len(backend.campaigns) == 1


def test_aria_on_refuses_the_campaign_at_no_cost(env):
    backend = FakeBackend(env.store, [OK] * 6, aria=True)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and 'Aria' in manifest['abort_detail'] and not backend.started
    assert manifest['attempts'][0]['error'] == fixed.STORE_OR_ARIA_REFUSED


def test_a_backend_whose_models_change_between_attempts_is_refused(env):
    backend = FakeBackend(env.store, [OK] * 6)

    def swap(fake):
        fake.actor = 'someone/else'
    backend.on_poll = swap
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and 'Backend Actor' in manifest['abort_detail']
    assert len(backend.started) == 1


def test_an_attempt_waits_for_an_idle_backend_before_it_starts(env, monkeypatch):
    calls = {'n': 0}

    def idle(base_url, seconds, poll):
        calls['n'] += 1
        return calls['n'] != 3                  # 1 before attempt 1, 2 after it, 3 before attempt 2
    monkeypatch.setattr(base, 'wait_until_idle', idle)
    backend = FakeBackend(env.store, [OK] * 6)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and 'refusing to start another study' in manifest['abort_detail']
    assert len(backend.started) == 1


def test_a_stop_that_did_not_settle_must_settle_before_a_resume(env, monkeypatch):
    first = env(FakeBackend(env.store, [study(protocol='faultlab-actor-context/v1')] + [OK] * 6))
    assert first['stop_reason'] == 'aborted'
    env.manifest().write_text(json.dumps({**first, 'stop_incomplete': True}))
    clock = [0.0]
    monkeypatch.setattr(base.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(base.time, 'sleep', lambda s: clock.__setitem__(0, clock[0] + max(s, 0.5)))
    backend = FakeBackend(env.store, [OK] * 6)
    status_calls = {'n': 0}

    def busy_after_first_status(base_url, method, path, body=None, timeout=30):
        if path == '/api/config/status':
            status_calls['n'] += 1
            if status_calls['n'] >= 2:
                return {'live_enabled': True, 'active_campaign_id': 'campaign-other',
                        'models': {'actor': base.EXPECTED_ACTOR, 'mechanic': base.EXPECTED_MECHANIC}}
        return backend(base_url, method, path, body, timeout)
    with pytest.raises(SystemExit, match='did not settle'):
        env(busy_after_first_status, '--resume', '--after-abort')
    resumed = env(backend, '--resume', '--after-abort')
    assert 'stop_incomplete' not in resumed and resumed['stop_incomplete_cleared']

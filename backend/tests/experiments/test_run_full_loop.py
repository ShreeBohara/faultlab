"""Offline checks of the Phase 17 full-loop runner against a scripted fake backend.

No network, no provider, no real store: the runner's HTTP helper is replaced by an
in-memory fake that also writes to a throwaway SQLite store with the real schema, and the
read-out rules are exercised on study records shaped exactly as assess_pairs writes them.
"""
import hashlib
import importlib.util
import json
import pathlib
import sqlite3
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('run_full_loop', ROOT / 'scripts/experiments/run_full_loop.py')
loop = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(loop)

CONFIG = 'c' * 64
STEP_RULES = {'rules': [{'hook': 'after_notification_response', 'when': 'notification_outcome_uncertain',
                         'steps': [{'op': 'read_notification_operation'},
                                   {'op': 'retry_original_request', 'service': 'notifications'}]}]}
NO_STEP_RULES = {'rules': [{'hook': 'after_notification_response', 'when': 'notification_outcome_uncertain',
                            'steps': [{'op': 'wait_ticks', 'ticks': 1}, {'op': 'read_notification_operation'}]}]}
CASES = ('healthy', 'notification-2', 'notification-1', 'notification-3', 'notification-18',
         'lost-notification-response', 'terminal-upgrade-rejection')


def counts(completed):
    """The exact key set baseline_study.summarize() writes into assess_pairs' by_case."""
    return {'attempted': 3, 'valid': 3, 'completed': completed, 'violations': 0, 'safe_unresolved': 3 - completed,
            'correctly_rejected': 0, 'lab_errors': 0, 'interrupted': 0, 'scheduled': 3, 'triggered': 3,
            'untriggered': 0}


def by_case(l_completed, b0_completed=None):
    b0_completed = b0_completed or {}
    return {case: {'B0': counts(b0_completed.get(case, 0)), 'L': counts(l_completed.get(case, 0))}
            for case in CASES}


def study(*, status='COMPLETED', decision='NO_CHANGE', stage='controls', candidates=(), l=None, b0=None,
          error_type=None, protocol=loop.ACTOR_CONTEXT, replay_of=None, rereads=(), evidence=2, selected=None):
    record = {'status': status, 'decision': decision, 'reason': 'r', 'stage': stage,
              'actor_context_protocol': protocol, 'evidence_protocol': loop.EVIDENCE_PROTOCOL,
              'replay_of': replay_of, 'manifest_hash': loop.MANIFEST_HASH, 'candidates': list(candidates),
              'trial_rows': [], 'evidence_rereads': list(rereads), 'evidence_count': evidence,
              'selected_candidate_hash': selected,
              'validation_assessment': None if l is None else {'decision': decision, 'by_case': by_case(l, b0)}}
    if error_type:
        record['error_type'] = error_type
    return record


def candidate(content, decision, source=None, policy_hash='h' * 64):
    return {'decision': decision, 'policy_hash': policy_hash, 'content': content,
            'source_assessment': {'decision': source} if source else None}


OK = study()
DEAD = study(status='INCOMPLETE', decision='INCOMPLETE', error_type='WaitingEvidence')
SOURCE_ONLY = study(decision='OBSERVED_IMPROVEMENT', stage='validation', l={'notification-2': 3, 'healthy': 3},
                    b0={'healthy': 3}, candidates=[candidate(STEP_RULES, 'OBSERVED_IMPROVEMENT', 'SOURCE_QUALIFIED')],
                    selected='h' * 64)
CERTIFIED = study(decision='OBSERVED_IMPROVEMENT', stage='validation',
                  l={'notification-2': 3, 'healthy': 3, 'notification-3': 3}, b0={'healthy': 3, 'notification-3': 1},
                  candidates=[candidate(NO_STEP_RULES, 'REJECTED', 'NO_CHANGE', 'a' * 64),
                              candidate(STEP_RULES, 'OBSERVED_IMPROVEMENT', 'SOURCE_QUALIFIED', 'b' * 64)],
                  rereads=[{'episode_id': 'f', 'stage': 'controls', 'first_error_code': 'TRANSPORT', 'result': 'VERIFIED'}],
                  selected='b' * 64)


# ----------------------------------------------------------------- read-out rules

def test_contains_step_needs_a_notifications_retry_at_the_notification_hook():
    assert loop.contains_step(STEP_RULES) and not loop.contains_step(NO_STEP_RULES) and not loop.contains_step(None)
    moved = {'rules': [{**STEP_RULES['rules'][0], 'hook': 'after_upgrade_response'}]}
    orders = {'rules': [{**STEP_RULES['rules'][0], 'steps': [{'op': 'retry_original_request', 'service': 'orders'}]}]}
    assert not loop.contains_step(moved) and not loop.contains_step(orders)


@pytest.mark.parametrize('l,b0,expected', [
    ({'notification-2': 3}, {}, False),                                      # source case only
    ({'notification-2': 3, 'healthy': 3}, {'healthy': 1}, False),            # healthy baseline lapses
    ({'notification-2': 3, 'notification-3': 1}, {}, False),                 # one chance completion
    ({'notification-2': 3, 'notification-1': 3, 'lost-notification-response': 3},
     {'notification-1': 2, 'lost-notification-response': 2}, False),        # two +1s are never summed
    ({'notification-2': 3, 'lost-notification-response': 3}, {'lost-notification-response': 2}, False),
    ({'notification-2': 3, 'notification-3': 2}, {}, True),                  # L - B0 = 2
    ({'notification-2': 3, 'notification-3': 3}, {'notification-3': 1}, True),
])
def test_certification_needs_two_more_completions_off_the_source_and_healthy_cases(l, b0, expected):
    record = study(decision='OBSERVED_IMPROVEMENT', l=l, b0=b0)
    assert loop.certified(record) is expected


def test_certification_also_requires_the_declared_study_identity():
    good = study(decision='OBSERVED_IMPROVEMENT', l={'notification-2': 3, 'notification-3': 3})
    assert loop.certified(good)
    for bad in ({**good, 'replay_of': 'policy-x'}, {**good, 'actor_context_protocol': 'faultlab-actor-context/v1'},
                {**good, 'manifest_hash': '0' * 64}, {**good, 'decision': 'NO_CHANGE'}):
        assert not loop.certified(bad)


# The 17 OBSERVED_IMPROVEMENT assessments that existed before Phase 17 (all replays of T15's
# policy). Pinned by id so that a later Phase 17 result can never turn this test red.
PRE_PHASE17_IMPROVEMENTS = [
    'completion-study-185f8b0873024217bddf3bfe6fc85d23', 'completion-study-259d99ca02e9453b8bca4caeb1d3724d',
    'completion-study-26ad2f952a0441cab1c870ae84cd69ee', 'completion-study-2ec0b38e64104ed9bbb0a09e91c73ab2',
    'completion-study-336f9dce4ed14c5b89628fa34b3bfad0', 'completion-study-3fff49298ef544c28944f74cec24d76a',
    'completion-study-60226a3ebfff477e991a03b274ce4d70', 'completion-study-6581c9286fb648e2b6f58c29c9d53675',
    'completion-study-66b5a500eca94b28bd700f65f6da8fbf', 'completion-study-6c6d65c2992b48128f0307e5082e366a',
    'completion-study-71337b6e27574fc2b81f2636bcbfc0fb', 'completion-study-7526cd60521e4180a7fa5f76dc5248c6',
    'completion-study-98668c8c803f47e2934b92d706a792f6', 'completion-study-a4dfe0a42a2e4251b328ebdd946ba5b0',
    'completion-study-ae7d38c08eff4f91a65055e469911825', 'completion-study-e53f0e262ab7442592373adaff8d92a8',
    'completion-study-f57115a2d0b94200b21cfe26345ad594']


def test_every_pre_phase17_improving_assessment_meets_the_new_rule():
    """All 17 stored improvements gain >= 2 completions on a non-source, non-healthy case."""
    db = ROOT / 'artifacts/lab.sqlite3'
    if not db.exists():
        pytest.skip('no local store')
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    try:
        rows = [json.loads(p) for (p,) in con.execute(
            f"select payload from records where kind='completion_studies' and id in "
            f"({','.join('?' * len(PRE_PHASE17_IMPROVEMENTS))})", PRE_PHASE17_IMPROVEMENTS)]
    finally:
        con.close()
    assert len(rows) == 17 and all(loop.fresh_case_gain(r['validation_assessment']) for r in rows)


def test_breaker_counts_infrastructure_deaths_not_legitimate_results():
    assert not loop.infrastructure_death(loop.summarize_study(OK))
    assert not loop.infrastructure_death(loop.summarize_study(study(status='INCOMPLETE', decision='INCOMPLETE')))
    assert loop.infrastructure_death(loop.summarize_study(DEAD))
    assert loop.infrastructure_death({'status': 'INTERRUPTED'}) and loop.infrastructure_death({'error': 'x'})


def test_first_proposal_rule_matches_phase9():
    drawn = loop.summarize_study(study(candidates=[candidate(None, 'REJECTED')]))
    assert drawn['first_proposal_drawn'] and drawn['first_proposal_contains_step'] is False
    none = loop.summarize_study(OK)
    assert not none['first_proposal_drawn'] and none['first_proposal_contains_step'] is None


# ----------------------------------------------------------------- fake backend and store

NO_LEDGER = {'usage_metadata_known': True, 'measured_input_tokens': 0, 'measured_output_tokens': 0,
             'reservations': {}}          # backend/app/lab/api.py budget route, no ledger yet


def make_store(path):
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE records(kind TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,'
                'immutable INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(kind,id))')
    con.commit(); con.close()


class FakeBackend:
    def __init__(self, store, outcomes, *, spend=2.0, config_hash=CONFIG, aria=False, project=loop.EXPECTED_PROJECT,
                 start_fails=(), adopt=False):
        self.store, self.outcomes, self.spend = store, list(outcomes), spend
        self.config_hash, self.aria, self.project = config_hash, aria, project
        self.start_fails, self.adopt = set(start_fails), adopt
        self.campaigns, self.ledgers, self.studies, self.stops, self.started = [], {}, {}, [], []
        self.active = None
        self.clock = 0
        self.on_poll = None

    def put(self, kind, id, payload):
        con = sqlite3.connect(self.store)
        con.execute('INSERT INTO records(kind,id,payload) VALUES(?,?,?) '
                    'ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload', (kind, id, json.dumps(payload)))
        con.commit(); con.close()

    def __call__(self, base, method, path, body=None, timeout=30):
        if path == '/api/config/status':
            return {'live_enabled': True, 'active_campaign_id': self.active,
                    'models': {'actor': loop.EXPECTED_ACTOR, 'mechanic': loop.EXPECTED_MECHANIC}}
        if path == '/api/campaigns' and method == 'POST':
            cid = f'campaign-{len(self.campaigns) + 1}'
            self.campaigns.append(cid)
            self.put('campaign_provenance', cid, {'aria_publication_enabled': self.aria})
            return {'campaign_id': cid, 'configuration_hash': self.config_hash}
        if path.endswith('/completion-study') and method == 'POST':
            cid = path.split('/')[3]
            assert body == {'execute_live': True, 'evidence_protocol': loop.EVIDENCE_PROTOCOL,
                            'actor_context_protocol': loop.ACTOR_CONTEXT}
            index = len(self.studies) + len([f for f in self.start_fails if f < 0]) + 1
            if index in self.start_fails and not self.adopt:
                self.start_fails.discard(index); self.start_fails.add(-index)
                raise OSError('start failed before the server saw it')
            sid = f'study-{len(self.studies) + 1}'
            self.clock += 1
            final = dict(self.outcomes.pop(0))
            n = final.pop('evidence_count')
            final.update(study_id=sid, campaign_id=cid, created_at=f'2999-01-01T00:00:{self.clock:02d}',
                         evidence={f'{sid}-ep{i}': 'weave_verified' for i in range(n)})
            self.studies[sid] = final
            self.put('completion_studies', sid, final)
            for eid in final['evidence']:
                self.put('evidence', eid, {'source': 'weave_verified', 'source_project': self.project})
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
                self.active = None                 # fake studies finish instantly
            return found
        if path.startswith('/api/completion-studies/'):
            if self.on_poll:
                self.on_poll(self)
            self.active = None                     # the study is terminal as soon as it is read
            return self.studies[path.rsplit('/', 1)[1]]
        if path.endswith('/budget'):
            return self.ledgers.get(path.split('/')[3], NO_LEDGER)
        if path.endswith('/stop'):
            self.stops.append(path.split('/')[3]); self.active = None; return {}
        raise AssertionError(f'unexpected {method} {path}')


FREEZE = {'schema_version': 'faultlab-gate-freeze/v1', 'files': {}, 'fingerprints': {},
          'functions': {loop.ASSESS_PAIRS_KEY: {'text_sha256': loop.ASSESS_PAIRS_TEXT_SHA256}}}
PROCESS = {'processes': [{'pid': 1, 'command': 'python -m uvicorn app.main:app', 'started_at': 'x'}]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    freeze = tmp_path / 'freeze.json'
    freeze.write_text(json.dumps(FREEZE))
    settings_file = tmp_path / 'settings.json'
    settings_file.write_text('{}')
    store = tmp_path / 'lab.sqlite3'
    make_store(store)
    monkeypatch.setattr(loop, 'ROOT', tmp_path)
    monkeypatch.setattr(loop, 'DECLARED_FREEZE_SHA256', hashlib.sha256(freeze.read_bytes()).hexdigest())
    monkeypatch.setattr(loop, 'DECLARED_CONFIGURATION_HASH', CONFIG)
    monkeypatch.setattr(loop, 'DECLARED_SETTINGS_SHA256', hashlib.sha256(settings_file.read_bytes()).hexdigest())
    monkeypatch.setattr(loop, 'gate_freeze', lambda: json.loads(json.dumps(FREEZE)))
    monkeypatch.setattr(loop, 'check_backend_process', lambda: PROCESS)
    monkeypatch.setattr(loop.time, 'sleep', lambda s: None)
    monkeypatch.setattr(loop.signal, 'signal', lambda *a: None)
    import app.config
    monkeypatch.setattr(app.config.Settings, 'from_env', classmethod(
        lambda cls: type('S', (), {'wandb_entity': 'entity', 'project_path': loop.EXPECTED_PROJECT})()))
    base = tmp_path / 'artifacts'

    def run(backend, *extra, out='phase17-test'):
        monkeypatch.setattr(loop, 'api', backend)
        stop = [] if '--stop-after' in extra else ['--stop-after', '60']
        monkeypatch.setattr(sys, 'argv', [
            'run_full_loop.py', '--out', str(base / out), '--store', str(store), '--settings', str(settings_file),
            '--expect-freeze', str(freeze), '--expect-freeze-sha256', hashlib.sha256(freeze.read_bytes()).hexdigest(),
            '--expect-configuration-hash', CONFIG, '--poll', '0', '--idle-grace', '2', '--execute-live',
            '--confirm-entity', 'entity',
            *stop, *extra])
        loop.main()
        return json.loads((base / out / 'full-loop-manifest.json').read_text())
    run.store = store
    run.base = base
    run.manifest = lambda out='phase17-test': base / out / 'full-loop-manifest.json'
    return run


def scripted():
    return [OK, DEAD, SOURCE_ONLY, CERTIFIED, OK]


# ----------------------------------------------------------------- the loop

def test_runs_until_the_first_certified_study_and_records_every_attempt(env):
    backend = FakeBackend(env.store, scripted())
    manifest = env(backend)
    assert manifest['stop_reason'] == 'certified' and len(backend.started) == 4
    assert [r['certified'] for r in manifest['attempts']] == [False, False, False, True]
    assert manifest['attempts'][3]['post_checks'] == 'passed'
    assert manifest['attempts'][2]['decision'] == 'OBSERVED_IMPROVEMENT' and not manifest['attempts'][2]['fresh_case_gain']
    s = manifest['summary']
    assert (s['attempts'], s['studies_started'], s['certified'], s['first_certified_attempt']) == (4, 4, 1, 4)
    assert s['observed_improvement'] == 2 and s['observed_improvement_without_fresh_gain'] == 1
    assert (s['infrastructure_deaths'], s['validation_reached'], s['validation_assessed']) == (1, 2, 2)
    assert (s['evidence_reads'], s['evidence_rereads'], s['evidence_rereads_verified']) == (8, 1, 1)
    assert s['all_studies'] == {'first_proposals_drawn': 2, 'first_proposals_with_step': 1, 'distinct_step_policies': 2,
                                'step_candidates_tested': 2, 'step_candidates_complete_pairs': 2,
                                'step_candidates_qualified': 2}
    # A bracket, not a correction: without the terminating study S1/S2 are biased the other way.
    assert s['excluding_terminating_study']['first_proposals_drawn'] == 1
    assert s['certified_policy_hash'] == 'b' * 64 and s['validations_per_policy'] == {'h' * 64: 1, 'b' * 64: 1}
    assert manifest['total_charged_upper_bound'] == pytest.approx(8.0)
    assert not backend.stops and manifest['declared']['protocol_sha256']
    problems, untracked = loop.reconcile(manifest, env.store)
    assert problems == [] and untracked == []


def test_a_certification_reports_every_earlier_attempt_with_the_same_policy(env):
    same = study(decision='NO_CHANGE', stage='candidate-1',
                 candidates=[candidate(STEP_RULES, 'REJECTED', 'NO_CHANGE', 'b' * 64)])
    manifest = env(FakeBackend(env.store, [same, CERTIFIED]))
    prior = manifest['summary']['certified_policy_prior_attempts']
    assert prior == [{'attempt': 1, 'slot': 1, 'decision': 'REJECTED', 'source_decision': 'NO_CHANGE',
                      'validation_decision': None}]


def test_checkpoint_then_resume_continues_numbering_and_refuses_after_success(env):
    backend = FakeBackend(env.store, scripted())
    first = env(backend, '--stop-after', '2')
    assert first['stop_reason'] == 'checkpoint' and len(first['attempts']) == 2
    second = env(backend, '--resume', '--stop-after', '60')
    assert second['stop_reason'] == 'certified' and [r['attempt'] for r in second['attempts']] == [1, 2, 3, 4]
    assert len(second['campaigns']) == 4 and len(second['sessions']) == 2
    assert second['sessions'][1]['previous_stop'] == 'checkpoint'
    with pytest.raises(SystemExit, match='Resume refused'):
        env(backend, '--resume', '--stop-after', '60')


def test_a_continuation_can_never_start_a_second_folder_or_change_its_parameters(env):
    backend = FakeBackend(env.store, scripted())
    env(backend, '--stop-after', '1')
    with pytest.raises(SystemExit, match='refusing to overwrite'):
        env(backend)
    with pytest.raises(SystemExit, match='Another Phase 17 run exists'):
        env(backend, out='phase17-other')
    with pytest.raises(SystemExit, match='must be artifacts/phase17'):
        env(backend, out='elsewhere')
    with pytest.raises(SystemExit, match='declared parameters'):
        env(backend, '--resume', '--spend-cap', '500')


def test_pins_that_differ_from_the_reviewed_runner_are_refused(env, monkeypatch):
    backend = FakeBackend(env.store, scripted())
    monkeypatch.setattr(loop, 'DECLARED_CONFIGURATION_HASH', 'e' * 64)
    with pytest.raises(SystemExit, match='typed pins'):
        env(backend)
    monkeypatch.setattr(loop, 'DECLARED_CONFIGURATION_HASH', CONFIG)
    monkeypatch.setattr(loop, 'DECLARED_SETTINGS_SHA256', '0' * 64)
    with pytest.raises(SystemExit, match='settings file'):
        env(backend)
    assert not backend.started


def test_an_aborted_run_resumes_only_with_explicit_approval(env):
    backend = FakeBackend(env.store, [study(protocol='faultlab-actor-context/v1'), OK, OK])
    first = env(backend)
    assert first['stop_reason'] == 'aborted' and 'actor_context_protocol' in first['abort_detail']
    assert backend.stops == ['campaign-1']                  # it was running: stopped
    with pytest.raises(SystemExit, match='--after-abort'):
        env(backend, '--resume')


@pytest.mark.parametrize('left_behind', [None, 'running'])
def test_a_session_that_was_killed_hard_needs_approval_to_resume(env, left_behind):
    backend = FakeBackend(env.store, [OK, OK, OK])
    env(backend, '--stop-after', '1')
    manifest = json.loads(env.manifest().read_text())
    if left_behind is None:
        manifest.pop('stop_reason')
    else:
        manifest['stop_reason'] = left_behind
    env.manifest().write_text(json.dumps(manifest))
    with pytest.raises(SystemExit, match='--after-abort'):
        env(backend, '--resume', '--stop-after', '2')
    resumed = env(backend, '--resume', '--after-abort', '--stop-after', '2')
    assert resumed['stop_reason'] == 'checkpoint' and resumed['sessions'][-1]['previous_stop'] == left_behind


def test_a_signal_leaves_the_running_study_alone_and_resume_recovers_it(env):
    backend = FakeBackend(env.store, [CERTIFIED, OK])

    def detach_on_first_poll(fake):
        fake.on_poll = None
        raise loop.Detached(15)
    backend.on_poll = detach_on_first_poll
    first = env(backend)
    assert first['stop_reason'] == 'aborted' and 'left running' in first['abort_detail']
    assert not backend.stops and first['attempts'][0].get('status') is None
    with pytest.raises(SystemExit, match='Another execution is active'):
        env(backend, '--resume', '--after-abort')         # the left-running study has not finished yet
    backend.active = None                                  # ...and now it has
    with pytest.raises(SystemExit, match='--after-abort'):
        env(backend, '--resume')
    resumed = env(backend, '--resume', '--after-abort')
    row = resumed['attempts'][0]
    assert row['recovered'] and row['certified'] and row['post_checks'].startswith('passed on recovery')
    assert resumed['stop_reason'] == 'certified' and len(backend.started) == 1


def test_a_finished_outcome_is_saved_before_anything_can_lose_it(env):
    backend = FakeBackend(env.store, [CERTIFIED, OK])
    calls = {'n': 0}
    original = backend.__call__

    def flaky(base, method, path, body=None, timeout=30):
        if path.startswith('/api/completion-studies/'):
            calls['n'] += 1
            if calls['n'] == 2:                   # poll #1 sees it finish; the re-read after idle fails
                raise OSError('dropped')
        return original(base, method, path, body, timeout)
    manifest = env(flaky)
    row = manifest['attempts'][0]
    assert manifest['stop_reason'] == 'aborted' and 're-read' in manifest['abort_detail']
    # Declared case (ii): it met conditions 1-3 on the record seen at completion and failed no check.
    assert row['certified'] is True and row['post_checks'] == 'pending' and manifest['summary']['certified'] == 1
    assert len(backend.started) == 1 and not backend.stops


def test_a_failed_post_finish_check_uncertifies_the_row(env):
    backend = FakeBackend(env.store, [CERTIFIED, OK], project='someone/else')
    manifest = env(backend)
    row = manifest['attempts'][0]
    assert manifest['stop_reason'] == 'aborted' and row['certified'] is False
    assert row['post_checks'].startswith('failed') and manifest['summary']['certified'] == 0
    assert not backend.stops                                 # it had finished: never stopped


def test_an_interrupted_start_the_server_accepted_is_adopted_on_resume(env):
    backend = FakeBackend(env.store, [CERTIFIED, OK])
    env(backend, '--stop-after', '1')
    manifest = json.loads(env.manifest().read_text())
    row = manifest['attempts'][0]
    for key in list(row):
        if key not in ('attempt', 'campaign_id', 'spent_before', 'configuration_hash'):
            row.pop(key)
    row['study_id'] = None
    manifest['stop_reason'] = 'running'
    env.manifest().write_text(json.dumps(manifest))
    resumed = env(backend, '--resume', '--after-abort')
    assert resumed['attempts'][0]['adopted_after_start_error'] and resumed['attempts'][0]['certified']
    assert resumed['stop_reason'] == 'certified' and len(backend.started) == 1


def test_a_start_that_reached_the_server_is_adopted_not_lost(env):
    backend = FakeBackend(env.store, [CERTIFIED, OK], start_fails={1}, adopt=True)
    manifest = env(backend)
    row = manifest['attempts'][0]
    assert row['adopted_after_start_error'] and row['start_error'] == 'TimeoutError'
    assert manifest['stop_reason'] == 'certified' and len(backend.started) == 1 and 'error' not in row


def test_a_start_that_never_reached_the_server_is_a_death_and_the_run_continues(env):
    backend = FakeBackend(env.store, [OK, OK], start_fails={1})
    manifest = env(backend, '--stop-after', '2')
    assert manifest['stop_reason'] == 'checkpoint'
    assert manifest['attempts'][0]['error'].startswith('study start') and manifest['attempts'][0]['study_id'] is None
    assert manifest['summary']['infrastructure_deaths'] == 1 and len(backend.started) == 1
    assert manifest['total_charged_upper_bound'] == pytest.approx(2.0)   # the ledger-less campaign is $0


def test_a_configuration_abort_does_not_block_a_later_approved_resume(env):
    backend = FakeBackend(env.store, [OK, OK], config_hash='d' * 64)
    first = env(backend)
    assert first['stop_reason'] == 'aborted' and 'configuration_hash' in first['abort_detail'] and not backend.started
    backend.config_hash = CONFIG                             # the backend is relaunched correctly
    resumed = env(backend, '--resume', '--after-abort', '--stop-after', '2')
    assert resumed['stop_reason'] == 'checkpoint' and len(backend.started) == 1


def test_a_real_ledger_without_a_bound_still_aborts(env):
    backend = FakeBackend(env.store, [OK, OK])
    original = backend.__call__

    def broken(base, method, path, body=None, timeout=30):
        if path.endswith('/budget') and path.split('/')[3] in backend.ledgers:
            return {'used_calls': 3, 'charged_dollar_upper_bound': None}
        return original(base, method, path, body, timeout)
    manifest = env(broken)
    assert manifest['stop_reason'] == 'aborted' and 'refusing to count it as $0' in manifest['abort_detail']


@pytest.mark.parametrize('kind', ['aria', 'project'])
def test_aria_on_or_evidence_in_another_project_aborts(env, kind):
    kwargs = {'aria': True} if kind == 'aria' else {'project': 'someone/else'}
    backend = FakeBackend(env.store, [OK, OK], **kwargs)
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted'
    assert len(backend.started) == (0 if kind == 'aria' else 1)
    if kind == 'aria':
        assert manifest['attempts'][0]['error'].startswith('store or Aria')


def test_a_backend_process_change_aborts(env, monkeypatch):
    seen = iter([PROCESS, PROCESS, {'processes': [{'pid': 2, 'command': 'x', 'started_at': 'y'}]}])
    monkeypatch.setattr(loop, 'check_backend_process', lambda: next(seen))
    backend = FakeBackend(env.store, [OK, OK])
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and 'process changed' in manifest['abort_detail']


def test_spend_guard_stops_before_a_study_that_could_cross_the_cap(env):
    backend = FakeBackend(env.store, [OK] * 10, spend=5.0)
    manifest = env(backend, '--spend-cap', '30', '--headroom', '11')
    # 0 -> 5 -> 10 -> 15 -> 20; at 20 + 11 > 30 no fifth study starts.
    assert manifest['stop_reason'] == 'spend_guard' and len(backend.started) == 4
    assert manifest['total_charged_upper_bound'] == pytest.approx(20.0) and not backend.stops


def test_breaker_trips_on_five_consecutive_study_deaths_and_not_on_four(env):
    backend = FakeBackend(env.store, [DEAD] * 4 + [OK] + [DEAD] * 5 + [OK])
    manifest = env(backend)
    assert manifest['stop_reason'] == 'aborted' and len(backend.started) == 10
    assert len(backend.outcomes) == 1                 # tripped by the breaker, not by running out of script
    assert 'consecutive studies died' in manifest['abort_detail']


def test_code_that_differs_from_the_reviewed_freeze_refuses_to_start(env, monkeypatch):
    monkeypatch.setattr(loop, 'gate_freeze', lambda: {**FREEZE, 'files': {'x': 1}})
    backend = FakeBackend(env.store, scripted())
    with pytest.raises(SystemExit, match='differs from the reviewed freeze'):
        env(backend)
    assert not backend.started


def test_a_freeze_without_the_unchanged_gate_is_refused(env, monkeypatch, tmp_path):
    bad = {**FREEZE, 'functions': {loop.ASSESS_PAIRS_KEY: {'text_sha256': '0' * 64}}}
    (tmp_path / 'freeze.json').write_text(json.dumps(bad))
    monkeypatch.setattr(loop, 'DECLARED_FREEZE_SHA256', hashlib.sha256((tmp_path / 'freeze.json').read_bytes()).hexdigest())
    backend = FakeBackend(env.store, scripted())
    with pytest.raises(SystemExit, match='unchanged assess_pairs'):
        env(backend)


def test_plan_is_dry(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(loop, 'api', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no HTTP in a plan')))
    monkeypatch.setattr(sys, 'argv', ['run_full_loop.py', '--out', str(tmp_path / 'p'), '--plan'])
    assert loop.main() == 0
    assert 'Dry plan only' in capsys.readouterr().out and not (tmp_path / 'p').exists()

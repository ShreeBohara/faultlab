"""A tiny offline episode loop: agent -> broker rules -> world -> checks. No sockets, no providers.

Broker rules (differ from the order broker on purpose):

* At most two attempts per logical call. Idempotent tools are retried after a timeout or a
  429/502/503/504 answer, replaying the same bytes.
* place_hold is NOT idempotent, so it is never retried after a timeout or a 500. It is retried
  only after 503 TRANSIENT_UNAVAILABLE, which the world raises before any effect.
* A hold_id must have been delivered in this episode (by place_hold or list_holds). Otherwise the
  broker refuses locally with UNKNOWN_HOLD_REFERENCE: no HTTP attempt is charged, no attempt id is
  recorded, and a ``scope_refusal`` lab event is written. The refusal is still delivered evidence.

Every delivered answer becomes an observation labelled obs-1, obs-2, ... (the indexed-evidence
labels of the order task's protocol v4). One actor call is charged per agent proposal, including
the final report; the budget is the unchanged order-task EpisodeBudget (8 actor calls).
"""
import copy
import json
from pathlib import Path

from . import checks, table, world

CASES_PATH = Path(__file__).resolve().parent / 'cases' / 'development.json'


# ---------------------------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------------------------
def manifest_hash(manifest):
    return world.content_hash({k: v for k, v in manifest.items() if k != 'manifest_hash'})


def load_manifest(path=CASES_PATH):
    manifest = json.loads(Path(path).read_text(encoding='utf-8'))
    if manifest.get('manifest_hash') != manifest_hash(manifest):
        raise ValueError('development manifest hash mismatch')
    for case in manifest['cases']:
        world.validate_fault_spec(case['fault_spec'], case['fixture_id'])
    return manifest


def load_cases(path=CASES_PATH):
    return {case['case_id']: case for case in load_manifest(path)['cases']}


def trial_seeds(case, trials=3):
    return [f"{case['seed']}-{n}" for n in range(trials)]


# ---------------------------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------------------------
def tool_action(tool, **args):
    return {'kind': 'tool', 'tool': tool, 'args': args}


def report_action(report):
    return {'kind': 'report', 'report': report}


def action_problem(action):
    """Why ``action`` is not an allowed proposal, or None."""
    if not isinstance(action, dict) or action.get('kind') not in ('tool', 'report'):
        return 'unknown action kind'
    if action['kind'] == 'report':
        if set(action) != {'kind', 'report'}:
            return 'report action shape'
        return table.report_problem(action['report'])
    if set(action) != {'kind', 'tool', 'args'} or action['tool'] not in table.TOOLS:
        return 'unknown tool'
    args = action['args']
    expected = set(table.TOOLS[action['tool']]['arguments'])
    if not isinstance(args, dict) or set(args) != expected:
        return f'arguments must be exactly {sorted(expected)}'
    if not all(isinstance(v, str) and v for v in args.values()):
        return 'arguments must be non-empty strings'
    return None


def uncertain(observation):
    """True when the answer does not tell whether an effect happened."""
    if observation['transport'] == 'timeout':
        return True
    status = observation['http_status']
    return status is not None and status >= 500 and observation['error_code'] != 'TRANSIENT_UNAVAILABLE'


# ---------------------------------------------------------------------------------------------
# Episode
# ---------------------------------------------------------------------------------------------
class Episode:
    """Holds one episode's world, meter, journal of calls and delivered observations."""

    def __init__(self, case, seed, budget=None):
        self.case = case
        self.seed_text = f"{case['case_id']}|{seed}"
        self.budget = dict(table.DEFAULT_BUDGET, **(budget or {}))
        self.ids = world.IdSource('lab|' + self.seed_text)
        self.intent = world.allocate_intent(self.seed_text)
        self.state = world.initial_state(case['fixture_id'], self.intent, case['fault_spec'], self.seed_text)
        self.usage = {'http_attempts': 0, 'actor_calls': 0, 'wait_cycles': 0, 'ticks': 0, 'policy_steps': 0,
                      'wall_seconds': 0}
        self.observations, self.lab_events, self.logical_calls = [], [], []
        self.delivered_hold_ids = []
        self.move_journal = None   # the original move request bytes, recorded before first dispatch

    # -- lab events and observations ------------------------------------------------------
    def _lab_event(self, event_type, payload):
        self.lab_events.append({'seq': len(self.lab_events) + 1, 'tick': self.usage['ticks'],
                                'turn': self.usage['actor_calls'], 'type': event_type, 'payload': payload})

    def _deliver(self, tool, caller, call_id, attempt_id, transport, http_status, error_code, data):
        observation = {'label': f'obs-{len(self.observations) + 1}', 'turn': self.usage['actor_calls'],
                       'tick': self.usage['ticks'], 'http_attempts_used': self.usage['http_attempts'],
                       'tool': tool, 'caller': caller, 'call_id': call_id, 'attempt_id': attempt_id,
                       'transport': transport, 'http_status': http_status, 'error_code': error_code,
                       'data': copy.deepcopy(data)}
        self.observations.append(observation)
        if transport == 'ok' and isinstance(data, dict):
            ids = []
            if data.get('kind') == 'hold' and tool == 'place_hold':
                ids = [data['hold_id']]
            elif data.get('kind') == 'hold_list':
                ids = [h['hold_id'] for h in data['holds']]
            for hold_id in ids:
                if hold_id not in self.delivered_hold_ids:
                    self.delivered_hold_ids.append(hold_id)
        return observation

    # -- the broker -----------------------------------------------------------------------
    def _request(self, tool, args):
        intent = self.intent
        if tool == 'place_hold':
            return {'booking_id': intent['booking_id'], 'slot_id': intent['target_slot']}
        if tool == 'move_booking':
            request = {'booking_id': intent['booking_id'], 'hold_id': args['hold_id'],
                       'operation_id': intent['move_operation_id'], 'idempotency_key': intent['move_idempotency_key'],
                       'intent_hash': intent['move_intent_hash']}
            if self.move_journal is None:
                self.move_journal = world.canonical_json(request)
            return request
        if tool == 'release_hold':
            return {'booking_id': intent['booking_id'], 'hold_id': args['hold_id']}
        return {'booking_id': intent['booking_id']}

    def call(self, tool, args, caller='actor'):
        """One logical call through the broker. Returns the list of delivered observations."""
        call_id = self.ids.new('call')
        if 'hold_id' in args and args['hold_id'] not in self.delivered_hold_ids:
            self._lab_event('scope_refusal', {'tool': tool, 'hold_id': args['hold_id'], 'call_id': call_id,
                                              'caller': caller})
            observation = self._deliver(tool, caller, call_id, None, 'refused', None, 'UNKNOWN_HOLD_REFERENCE', None)
            self.logical_calls.append({'call_id': call_id, 'tool': tool, 'caller': caller, 'args': dict(args),
                                       'attempt_ids': [], 'observation_labels': [observation['label']]})
            return [observation]
        request = self._request(tool, args)
        attempts, delivered = [], []
        for attempt in range(table.BROKER_MAX_ATTEMPTS_PER_CALL):
            if self.usage['http_attempts'] >= self.budget['http_attempts'] or self.usage['ticks'] >= self.budget['ticks']:
                self._lab_event('budget_refusal', {'tool': tool, 'call_id': call_id, 'caller': caller})
                delivered.append(self._deliver(tool, caller, call_id, None, 'refused', None, 'BUDGET_EXHAUSTED', None))
                break
            attempt_id = self.ids.new('attempt')
            attempts.append(attempt_id)
            self.usage['http_attempts'] += 1
            self.usage['ticks'] += 1
            self._lab_event('tool_dispatched', {'tool': tool, 'call_id': call_id, 'attempt_id': attempt_id,
                                                'caller': caller})
            self.state, answer, _ = world.handle(self.state, tool, request, {'call_id': call_id, 'attempt_id': attempt_id})
            if answer['lost_ms'] > table.CLIENT_TIMEOUT_MS:
                observation = self._deliver(tool, caller, call_id, attempt_id, 'timeout', None, 'HTTP_TIMEOUT', None)
            else:
                ok = 200 <= answer['http_status'] < 300
                observation = self._deliver(tool, caller, call_id, attempt_id, 'ok' if ok else 'error',
                                            answer['http_status'], answer['error_code'], answer['data'])
            delivered.append(observation)
            if not self._retry(tool, observation):
                break
        self.logical_calls.append({'call_id': call_id, 'tool': tool, 'caller': caller, 'args': dict(args),
                                   'attempt_ids': attempts, 'observation_labels': [o['label'] for o in delivered]})
        return delivered

    @staticmethod
    def _retry(tool, observation):
        if not table.TOOLS[tool]['idempotent']:
            return observation['error_code'] in table.CREATE_RETRY_ONLY_ON
        return observation['transport'] == 'timeout' or observation['http_status'] in table.RETRYABLE_HTTP_STATUS

    # -- agent view -----------------------------------------------------------------------
    def view(self):
        intent = self.intent
        return {'task_text': table.TASK_TEXT, 'turn': self.usage['actor_calls'] + 1,
                'turns_total': self.budget['actor_calls'],
                'intent': {k: intent[k] for k in ('task_id', 'booking_id', 'original_slot', 'target_slot',
                                                  'move_operation_id')},
                'observations': copy.deepcopy(self.observations)}


def world_integrity(decision, horizon, usage, logical_calls):
    """The same four comparisons as backend/app/lab/runner.py world_integrity, on pack records."""
    dispatched = [a for call in logical_calls for a in call['attempt_ids']]
    admitted = [e['payload'].get('attempt_id') for e in decision['events'] if e['type'] == 'http_attempt']
    issues = []
    if decision['tick'] != usage['ticks']:
        issues.append('DECISION_TICK_MISMATCH')
    if len(admitted) != usage['http_attempts']:
        issues.append('HTTP_ADMISSION_COUNT_MISMATCH')
    if admitted != dispatched:
        issues.append('HTTP_ADMISSION_IDENTITY_MISMATCH')
    if horizon['tick'] != decision['tick'] + table.OBSERVER_TICKS:
        issues.append('OBSERVER_HORIZON_MISMATCH')
    return {'status': 'INVALID' if issues else 'VALID', 'issues': issues, 'decision_tick': decision['tick'],
            'horizon_tick': horizon['tick'], 'charged_http_attempts': usage['http_attempts'],
            'admitted_http_attempts': len(admitted)}


def run_episode(agent, case, seed, budget=None):
    """Run one offline episode and score it. Returns a plain dict record."""
    episode = Episode(case, seed, budget)
    report = None
    while episode.usage['actor_calls'] < episode.budget['actor_calls']:
        view = episode.view()
        episode.usage['actor_calls'] += 1
        action = agent.act(view)
        problem = action_problem(action)
        if problem:
            episode._lab_event('invalid_action', {'problem': problem, 'action': copy.deepcopy(action)})
            episode._deliver(action.get('tool') if isinstance(action, dict) and isinstance(action.get('tool'), str) else None,
                             'actor', None, None, 'refused', None, 'INVALID_ACTION', {'problem': problem})
            continue
        if action['kind'] == 'report':
            report = copy.deepcopy(action['report'])
            episode._lab_event('report_submitted', {'overall': report['overall']})
            break
        episode.call(action['tool'], action['args'])
    turns_used = episode.usage['actor_calls']
    episode.state = world.stop(episode.state)
    decision = world.snapshot(episode.state)
    episode.state = world.observe(episode.state)
    horizon = world.snapshot(episode.state)
    integrity = world_integrity(decision, horizon, episode.usage, episode.logical_calls)
    verdict = checks.score(intent=episode.intent, report=report, observations=episode.observations,
                           decision=decision, horizon=horizon, lab_events=episode.lab_events,
                           usage=episode.usage, budget=episode.budget, world_integrity=integrity)
    return {'case_id': case['case_id'], 'seed': seed, 'agent': getattr(agent, 'name', type(agent).__name__),
            'intent': episode.intent, 'report': report, 'observations': episode.observations,
            'lab_events': episode.lab_events, 'logical_calls': episode.logical_calls, 'usage': episode.usage,
            'turns_used': turns_used, 'slack_turns': episode.budget['actor_calls'] - turns_used,
            'decision': decision, 'horizon': horizon, 'fault_executions': horizon['fault_executions'],
            'world_integrity': integrity, 'verdict': verdict}


def trace(record):
    """The parts of an episode that must be identical for the same case, agent and seed."""
    return {'world_events': record['horizon']['events'], 'observations': record['observations'],
            'lab_events': record['lab_events'], 'report': record['report'], 'verdict': record['verdict'],
            'fault_executions': record['fault_executions']}


def trace_hash(record):
    return world.content_hash(trace(record))

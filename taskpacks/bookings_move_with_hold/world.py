"""The booking world for bookings.move_with_hold/v1, in process and pure.

Two services share one state:

* bookings: one booking with a version history, and the one move operation;
* calendar: the target slot (3 places) and this task's holds.

Rules, in plain words:

* Time moves one tick per admitted request, and by bounded waits. At every tick, in this fixed
  order: (1) a PENDING move whose due tick has come completes; a move whose hold is no longer
  ACTIVE fails HOLD_NOT_ACTIVE; (2) ACTIVE holds with expires_tick <= tick expire. So a hold is
  usable at expires_tick - 1 and expired at expires_tick.
* place_hold is not idempotent: every committed call creates a new hold.
* move_booking is idempotent by the trusted operation id and key. Moving onto a hold that is not
  ACTIVE is refused before acceptance (409 HOLD_NOT_ACTIVE; no operation is created).
* release_hold is idempotent per hold; a consumed hold answers 409 HOLD_CONSUMED; an expired hold
  answers 200 EXPIRED with no effect.
* The world refuses (without admitting) once 18 requests were admitted or tick 20 is reached, and
  after it was stopped. The observer then moves it 5 ticks, once.

Faults F1-F6 are applied here, per tool occurrence, with honest trigger accounting. F1 is
modelled in process: the effect commits and the answer carries ``lost_ms`` past the client
timeout; the broker turns that into HTTP_TIMEOUT.

``handle`` never mutates its input: it returns a new state, the answer and the new events.
Standard library only.
"""
import copy
import hashlib
import json

from . import table

WORLD_SCHEMA = 'faultlab-pack-world/v1'


class FaultSpecError(ValueError):
    """A fault recipe that the grammar does not allow."""

    def __init__(self, code, detail=''):
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code = code


class WorldError(Exception):
    def __init__(self, code, status=409, data=None):
        super().__init__(code)
        self.code, self.status, self.data = code, status, data


# ---------------------------------------------------------------------------------------------
# Hashing and deterministic ids
# ---------------------------------------------------------------------------------------------
def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def content_hash(value):
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def make_id(seed_text, prefix, n):
    return f'{prefix}-' + hashlib.sha256(f'{seed_text}|{prefix}|{n}'.encode('utf-8')).hexdigest()[:12]


class IdSource:
    """Deterministic ids: the same seed text and call order always give the same ids."""

    def __init__(self, seed_text):
        self.seed_text, self.counts = seed_text, {}

    def new(self, prefix):
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        return make_id(self.seed_text, prefix, self.counts[prefix])


def _mint(state, prefix):
    counts = state['mint']['counts']
    counts[prefix] = counts.get(prefix, 0) + 1
    return make_id(state['mint']['seed'], prefix, counts[prefix])


# ---------------------------------------------------------------------------------------------
# Intent and fixtures
# ---------------------------------------------------------------------------------------------
def allocate_intent(seed_text):
    """Trusted identities for one episode. The agent never chooses any of them."""
    ids = IdSource('intent|' + seed_text)
    intent = {'task_definition_id': table.TASK_DEFINITION_ID, 'task_id': ids.new('task'),
              'booking_id': ids.new('booking'), 'original_slot': ids.new('slot'), 'target_slot': ids.new('slot'),
              'move_operation_id': ids.new('moveop'), 'move_idempotency_key': ids.new('movekey')}
    intent['move_intent_hash'] = content_hash({k: intent[k] for k in (
        'task_definition_id', 'task_id', 'booking_id', 'target_slot', 'move_operation_id')})
    return intent


def fixture_history(fixture_id, intent):
    """The booking's version history. The last entry is the current booking.

    history-v1 is the stale-read fixture: the booking was once moved to the target slot and moved
    back, so a projection one version old shows it in the target slot. That is the lure of hk-dev-8:
    a projection is not a receipt.
    """
    original, target = intent['original_slot'], intent['target_slot']
    if fixture_id == 'standard-v1':
        slots = [original]
    elif fixture_id == 'history-v1':
        slots = [original, original, target, original]
    else:
        raise FaultSpecError('UNKNOWN_FIXTURE', fixture_id)
    return [{'booking_id': intent['booking_id'], 'slot': slot, 'version': n + 1} for n, slot in enumerate(slots)]


# ---------------------------------------------------------------------------------------------
# Fault grammar
# ---------------------------------------------------------------------------------------------
def _int_in(value, bounds):
    return isinstance(value, int) and not isinstance(value, bool) and bounds[0] <= value <= bounds[1]


def validate_fault_spec(spec, fixture_id):
    """Raise FaultSpecError unless ``spec`` is a valid recipe for ``fixture_id``. Returns the primitives."""
    if not isinstance(spec, dict) or spec.get('scope') != table.TASK_DEFINITION_ID:
        raise FaultSpecError('WRONG_SCOPE')
    primitives = spec.get('primitives')
    if not isinstance(primitives, list) or len(primitives) > table.MAX_PRIMITIVES:
        raise FaultSpecError('TOO_MANY_PRIMITIVES')
    if fixture_id not in table.FIXTURES:
        raise FaultSpecError('UNKNOWN_FIXTURE', fixture_id)
    for p in primitives:
        if not isinstance(p, dict) or set(p) != {'kind', 'target_tool', 'occurrence', 'parameters'}:
            raise FaultSpecError('PRIMITIVE_SHAPE')
        kind = table.FAULT_KINDS.get(p['kind'])
        if kind is None:
            raise FaultSpecError('UNKNOWN_KIND', str(p['kind']))
        if p['target_tool'] not in kind['targets']:
            raise FaultSpecError('TARGET_NOT_ALLOWED', f"{p['kind']} on {p['target_tool']}")
        if not _int_in(p['occurrence'], table.OCCURRENCE_RANGE):
            raise FaultSpecError('OCCURRENCE_RANGE')
        params = p['parameters']
        if not isinstance(params, dict) or set(params) != set(kind['parameters']):
            raise FaultSpecError('PARAMETERS', p['kind'])
        for name, bounds in kind['parameters'].items():
            value = params[name]
            ok = value in bounds if isinstance(bounds[0], str) else _int_in(value, bounds)
            if not ok:
                raise FaultSpecError('PARAMETER_RANGE', f'{p["kind"]}.{name}')
    seen = set()
    for p in primitives:
        key = (p['kind'], p['target_tool'], p['occurrence'])
        if key in seen:
            raise FaultSpecError('DUPLICATE_PRIMITIVE')
        seen.add(key)
    answer_faults = [(p['target_tool'], p['occurrence']) for p in primitives if p['kind'] in ('F1', 'F5')]
    if len(answer_faults) != len(set(answer_faults)):
        # Only one answer can be lost or replaced per attempt.
        raise FaultSpecError('CONFLICTING_ANSWER_FAULTS')
    delayed = {p['occurrence'] for p in primitives if p['kind'] == 'F2'}
    if any(p['kind'] == 'F1' and p['target_tool'] == 'move_booking' and p['occurrence'] in delayed
           for p in primitives):
        # F2 makes that move answer 202 PENDING, which commits nothing yet, so the F1 on the same
        # occurrence could never fire (it would always end as target_not_committed).
        raise FaultSpecError('CONFLICTING_MOVE_FAULTS')
    return primitives


def cannot_fire(spec, fixture_id):
    """Static "cannot fire" filter, applied at $0 before any paid pick.

    Returns a list of {index, kind, reason} for primitives that no agent behaviour can trigger.
    """
    out = []
    primitives = spec.get('primitives', [])
    history_length = {'standard-v1': 1, 'history-v1': 4}.get(fixture_id, 0)
    windows = [(p['target_tool'], p['occurrence'], p['occurrence'] + p['parameters']['failure_count'] - 1)
               for p in primitives if p['kind'] == 'F4']
    for i, p in enumerate(primitives):
        if p['kind'] == 'F3' and history_length <= p['parameters']['versions_back']:
            out.append({'index': i, 'kind': 'F3', 'reason': 'stale_read_without_history'})
        if p['kind'] != 'F4' and any(tool == p['target_tool'] and lo <= p['occurrence'] <= hi
                                     for tool, lo, hi in windows):
            out.append({'index': i, 'kind': p['kind'], 'reason': 'pre_empted_by_F4'})
        if p['occurrence'] > table.MAX_HTTP_ATTEMPTS:
            out.append({'index': i, 'kind': p['kind'], 'reason': 'beyond_attempt_cap'})
    return out


# ---------------------------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------------------------
def initial_state(fixture_id, intent, fault_spec, seed_text):
    primitives = validate_fault_spec(fault_spec, fixture_id)
    history = fixture_history(fixture_id, intent)
    for p in primitives:
        if p['kind'] == 'F3' and len(history) <= p['parameters']['versions_back']:
            raise FaultSpecError('STALE_HISTORY_UNAVAILABLE')
    return {
        'schema_version': WORLD_SCHEMA, 'task_definition_id': table.TASK_DEFINITION_ID,
        'fixture_id': fixture_id, 'intent': copy.deepcopy(intent), 'mint': {'seed': 'world|' + seed_text, 'counts': {}},
        'tick': 0, 'attempts': 0, 'waits': 0, 'stopped': False, 'decision_tick': None, 'horizon_done': False,
        'booking': dict(history[-1]), 'history': history,
        'slot': {'slot_id': intent['target_slot'], 'capacity': table.TARGET_CAPACITY},
        'holds': [], 'move': None, 'move_idempotency': None, 'events': [], 'occurrences': {},
        'fault_spec': copy.deepcopy(fault_spec),
        'fault_executions': [{'fault_id': f'fault-{n + 1}', 'kind': p['kind'], 'target_tool': p['target_tool'],
                              'occurrence': p['occurrence'], 'scheduled': True, 'triggered': False,
                              'trigger_tick': None, 'call_id': None, 'attempt_id': None,
                              'reason': 'target_not_reached'} for n, p in enumerate(primitives)],
    }


def _event(state, event_type, payload=None, call_id=None):
    value = {'seq': len(state['events']) + 1, 'tick': state['tick'], 'type': event_type,
             'payload': payload or {}, 'call_id': call_id}
    state['events'].append(value)
    return value


def _find_hold(state, hold_id):
    return next((h for h in state['holds'] if h['hold_id'] == hold_id), None)


def public_hold(hold):
    return {'hold_id': hold['hold_id'], 'slot': hold['slot'], 'state': hold['state'],
            'created_tick': hold['created_tick'], 'expires_tick': hold['expires_tick']}


def _move_view(state):
    move = state['move']
    if move is None:
        return {'kind': 'move_operation', 'operation_id': state['intent']['move_operation_id'], 'status': 'UNKNOWN',
                'hold_id': None, 'receipt': None}
    return {'kind': 'move_operation', 'operation_id': move['operation_id'], 'status': move['state'],
            'hold_id': move['hold_id'], 'receipt': copy.deepcopy(move['receipt'])}


# ---------------------------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------------------------
def _complete_move(state, move):
    hold = _find_hold(state, move['hold_id'])
    if move['terminal_status'] == 'FAILED':
        status, failure = 'FAILED', move['failure_code']
    elif hold is not None and hold['state'] == 'ACTIVE':
        status, failure = 'SUCCEEDED', None
    else:
        status, failure = 'FAILED', 'HOLD_NOT_ACTIVE'
    version = None
    if status == 'SUCCEEDED':
        hold['state'], hold['closed_tick'] = 'CONSUMED', state['tick']
        booking = {'booking_id': state['booking']['booking_id'], 'slot': state['intent']['target_slot'],
                   'version': state['booking']['version'] + 1}
        state['booking'] = booking
        state['history'].append(dict(booking))
        version = booking['version']
    move['state'], move['terminal_tick'] = status, state['tick']
    move['receipt'] = {'receipt_id': _mint(state, 'receipt'), 'operation_id': move['operation_id'],
                       'hold_id': move['hold_id'], 'status': status, 'failure_code': failure,
                       'terminal_tick': state['tick'], 'booking_version': version}
    if status == 'SUCCEEDED':
        _event(state, 'hold_consumed', {'hold_id': hold['hold_id'], 'operation_id': move['operation_id']})
        _event(state, 'move_succeeded', {'operation_id': move['operation_id'], 'hold_id': move['hold_id'],
                                         'receipt_id': move['receipt']['receipt_id'], 'booking_version': version})
    else:
        _event(state, 'move_failed', {'operation_id': move['operation_id'], 'hold_id': move['hold_id'],
                                      'failure_code': failure, 'receipt_id': move['receipt']['receipt_id']})


def _advance(state, ticks):
    for _ in range(ticks):
        state['tick'] += 1
        move = state['move']
        # (1) moves that are due complete first ...
        if move is not None and move['state'] == 'PENDING' and move['due_tick'] <= state['tick']:
            _complete_move(state, move)
        # (2) ... then holds expire.
        for hold in state['holds']:
            if hold['state'] == 'ACTIVE' and hold['expires_tick'] <= state['tick']:
                hold['state'], hold['closed_tick'] = 'EXPIRED', state['tick']
                _event(state, 'hold_expired', {'hold_id': hold['hold_id']})


# ---------------------------------------------------------------------------------------------
# Fault accounting
# ---------------------------------------------------------------------------------------------
def _matching(state, tool):
    occurrence = state['occurrences'].get(tool, 0) + 1
    state['occurrences'][tool] = occurrence
    found = []
    for i, p in enumerate(state['fault_spec']['primitives']):
        if p['target_tool'] != tool:
            continue
        count = p['parameters']['failure_count'] if p['kind'] == 'F4' else 1
        if p['occurrence'] <= occurrence < p['occurrence'] + count:
            found.append((i, p))
    return found


def _trigger(state, index, call_id, attempt_id):
    record = state['fault_executions'][index]
    if not record['triggered']:
        record.update(triggered=True, trigger_tick=state['tick'], call_id=call_id, attempt_id=attempt_id, reason=None)
    _event(state, 'fault_triggered', {'fault_id': record['fault_id'], 'kind': record['kind'], 'attempt_id': attempt_id},
           call_id)


def _prevented(state, index, reason):
    record = state['fault_executions'][index]
    if not record['triggered']:
        record['reason'] = reason


# ---------------------------------------------------------------------------------------------
# Business handling
# ---------------------------------------------------------------------------------------------
def _perform(state, tool, request, faults, call_id, attempt_id):
    """Returns (http_status, data, committed). Raises WorldError for a refusal."""
    intent = state['intent']
    if request.get('booking_id', intent['booking_id']) != intent['booking_id']:
        raise WorldError('IDENTITY_CONFLICT')
    if tool == 'get_booking':
        projection = state['booking']
        for i, p in faults:
            if p['kind'] == 'F3':
                projection = state['history'][-1 - p['parameters']['versions_back']]
                _trigger(state, i, call_id, attempt_id)
        return 200, {'kind': 'booking_projection', **projection}, False
    if tool == 'list_holds':
        return 200, {'kind': 'hold_list', 'as_of_tick': state['tick'],
                     'holds': [public_hold(h) for h in state['holds']]}, False
    if tool == 'get_move_status':
        return 200, _move_view(state), False
    if tool == 'place_hold':
        if request.get('slot_id') != intent['target_slot']:
            raise WorldError('IDENTITY_CONFLICT')
        active = sum(1 for h in state['holds'] if h['state'] == 'ACTIVE')
        if active >= state['slot']['capacity']:
            raise WorldError('NO_CAPACITY')
        ttl = table.HOLD_TTL_TICKS
        for i, p in faults:
            if p['kind'] == 'F6':
                ttl -= p['parameters']['ttl_cut_ticks']
                _trigger(state, i, call_id, attempt_id)
        hold = {'hold_id': _mint(state, 'hold'), 'slot': intent['target_slot'], 'state': 'ACTIVE',
                'created_tick': state['tick'], 'expires_tick': state['tick'] + ttl, 'closed_tick': None,
                'release_receipt': None}
        state['holds'].append(hold)
        _event(state, 'hold_created', {'hold_id': hold['hold_id'], 'expires_tick': hold['expires_tick'],
                                       'attempt_id': attempt_id}, call_id)
        return 201, {'kind': 'hold', **public_hold(hold)}, True
    if tool == 'move_booking':
        body = {k: request.get(k) for k in ('booking_id', 'hold_id', 'operation_id', 'idempotency_key', 'intent_hash')}
        payload_hash = content_hash(body)
        known = state['move_idempotency']
        if known is not None and known['key'] == body['idempotency_key']:
            if known['payload_hash'] != payload_hash:
                raise WorldError('IDEMPOTENCY_CONFLICT')
            for i, p in faults:
                if p['kind'] == 'F2':
                    _prevented(state, i, 'target_not_accepted')
            return 200, _move_view(state), state['move']['state'] == 'SUCCEEDED'
        if (body['operation_id'] != intent['move_operation_id'] or body['idempotency_key'] != intent['move_idempotency_key']
                or body['intent_hash'] != intent['move_intent_hash']):
            raise WorldError('IDENTITY_CONFLICT')
        hold = _find_hold(state, body['hold_id'])
        if hold is None:
            raise WorldError('UNKNOWN_HOLD', 404)
        if hold['state'] != 'ACTIVE':
            raise WorldError('HOLD_NOT_ACTIVE', 409, {'hold_id': hold['hold_id'], 'hold_state': hold['state']})
        move = {'operation_id': body['operation_id'], 'hold_id': hold['hold_id'], 'payload_hash': payload_hash,
                'state': 'PENDING', 'accepted_tick': state['tick'], 'due_tick': state['tick'],
                'terminal_status': 'SUCCEEDED', 'failure_code': None, 'terminal_tick': None, 'receipt': None}
        state['move'] = move
        state['move_idempotency'] = {'key': body['idempotency_key'], 'payload_hash': payload_hash}
        _event(state, 'move_accepted', {'operation_id': move['operation_id'], 'hold_id': move['hold_id'],
                                        'payload_hash': payload_hash}, call_id)
        f2 = next(((i, p) for i, p in faults if p['kind'] == 'F2'), None)
        if f2 is not None:
            i, p = f2
            status = p['parameters']['terminal_status']
            move.update(due_tick=state['tick'] + p['parameters']['completion_delay_ticks'], terminal_status=status,
                        failure_code='MOVE_REJECTED' if status == 'FAILED' else None)
            _trigger(state, i, call_id, attempt_id)
            return 202, _move_view(state), False
        _complete_move(state, move)
        return 200, _move_view(state), True
    if tool == 'release_hold':
        hold = _find_hold(state, request.get('hold_id'))
        if hold is None:
            raise WorldError('UNKNOWN_HOLD', 404)
        if hold['state'] == 'CONSUMED':
            raise WorldError('HOLD_CONSUMED', 409, {'hold_id': hold['hold_id'], 'hold_state': 'CONSUMED'})
        if hold['state'] == 'EXPIRED':
            return 200, {'kind': 'hold_release', 'hold_id': hold['hold_id'], 'state': 'EXPIRED', 'effect': 'none',
                         'receipt': None}, False
        replay = hold['state'] == 'RELEASED'
        if not replay:
            hold['state'], hold['closed_tick'] = 'RELEASED', state['tick']
            hold['release_receipt'] = {'receipt_id': _mint(state, 'release'), 'hold_id': hold['hold_id'],
                                       'released_tick': state['tick']}
            _event(state, 'hold_released', {'hold_id': hold['hold_id'],
                                            'receipt_id': hold['release_receipt']['receipt_id']}, call_id)
        return 200, {'kind': 'hold_release', 'hold_id': hold['hold_id'], 'state': 'RELEASED',
                     'effect': 'replayed' if replay else 'released',
                     'receipt': copy.deepcopy(hold['release_receipt'])}, True
    raise ValueError(f'unknown tool {tool!r}')


def _answer(status, data=None, error_code=None, lost_ms=0, admitted=True):
    return {'admitted': admitted, 'http_status': status, 'error_code': error_code, 'data': data, 'lost_ms': lost_ms}


def handle(state, tool, request, ctx):
    """Admit and handle one request. Returns (new_state, answer, new_events); never mutates ``state``.

    ``request`` is the full trusted body the broker built; ``ctx`` carries ``call_id`` and ``attempt_id``.
    """
    if tool not in table.TOOL_NAMES:
        raise ValueError(f'unknown tool {tool!r}')
    s = copy.deepcopy(state)
    before = len(s['events'])
    if s['stopped']:
        return s, _answer(409, error_code='WORLD_STOPPED', admitted=False), []
    if s['attempts'] >= table.MAX_HTTP_ATTEMPTS or s['tick'] >= table.MAX_DECISION_TICK:
        return s, _answer(429, error_code='BUSINESS_BUDGET', admitted=False), []
    call_id, attempt_id = ctx['call_id'], ctx['attempt_id']
    _advance(s, 1)
    s['attempts'] += 1
    _event(s, 'http_attempt', {'attempt_id': attempt_id, 'tool': tool}, call_id)
    faults = _matching(s, tool)
    f4 = next(((i, p) for i, p in faults if p['kind'] == 'F4'), None)
    if f4 is not None:
        # Refused before any effect: every other fault aimed at this attempt is pre-empted.
        _trigger(s, f4[0], call_id, attempt_id)
        for i, p in faults:
            if p['kind'] != 'F4':
                _prevented(s, i, 'pre_effect_failure')
        _event(s, 'request_rejected', {'error_code': 'TRANSIENT_UNAVAILABLE', 'attempt_id': attempt_id, 'tool': tool},
               call_id)
        return s, _answer(503, error_code='TRANSIENT_UNAVAILABLE'), copy.deepcopy(s['events'][before:])
    try:
        status, data, committed = _perform(s, tool, request, faults, call_id, attempt_id)
        answer = _answer(status, data)
        for i, p in faults:
            if p['kind'] == 'F1':
                if committed:
                    _trigger(s, i, call_id, attempt_id)
                    answer['lost_ms'] = max(answer['lost_ms'], p['parameters']['response_delay_ms'])
                else:
                    _prevented(s, i, 'target_not_committed')
            elif p['kind'] == 'F5':
                if committed:
                    _trigger(s, i, call_id, attempt_id)
                    answer = _answer(500, error_code='INTERNAL_ERROR')
                else:
                    _prevented(s, i, 'target_not_committed')
    except WorldError as error:
        for i, p in faults:
            if p['kind'] in ('F1', 'F5', 'F6'):
                _prevented(s, i, 'target_not_committed')
            elif p['kind'] == 'F2':
                _prevented(s, i, 'target_not_accepted')
        _event(s, 'request_rejected', {'error_code': error.code, 'attempt_id': attempt_id, 'tool': tool}, call_id)
        answer = _answer(error.status, copy.deepcopy(error.data), error.code)
    return s, answer, copy.deepcopy(s['events'][before:])


# ---------------------------------------------------------------------------------------------
# Coordinator-only controls
# ---------------------------------------------------------------------------------------------
def wait(state, ticks):
    """A bounded wait: 1-4 ticks, at most 4 waits, never past tick 20. Returns the new state."""
    s = copy.deepcopy(state)
    if s['stopped']:
        raise WorldError('WORLD_STOPPED')
    if not _int_in(ticks, (1, table.MAX_WAIT_TICKS)) or s['waits'] >= table.MAX_WAITS:
        raise WorldError('WAIT_BUDGET', 429)
    if s['tick'] + ticks > table.MAX_DECISION_TICK:
        raise WorldError('TICK_BUDGET', 429)
    _advance(s, ticks)
    s['waits'] += 1
    _event(s, 'wait_advanced', {'ticks': ticks})
    return s


def stop(state):
    """Stop business: the decision tick is fixed here."""
    s = copy.deepcopy(state)
    if not s['stopped']:
        s['stopped'], s['decision_tick'] = True, s['tick']
        _event(s, 'world_stopped')
    return s


def observe(state):
    """The observer's one move of exactly 5 ticks after the decision."""
    s = copy.deepcopy(state)
    if not s['stopped'] or s['horizon_done']:
        raise WorldError('INVALID_OBSERVER_ADVANCE')
    if s['tick'] + table.OBSERVER_TICKS > table.MAX_OBSERVER_TICK:
        raise WorldError('TICK_BUDGET', 429)
    _advance(s, table.OBSERVER_TICKS)
    s['horizon_done'] = True
    _event(s, 'observer_advanced', {'ticks': table.OBSERVER_TICKS})
    return s


def snapshot(state):
    """A private evaluator view of the world. Never shown to an agent."""
    return copy.deepcopy({
        'task_definition_id': state['task_definition_id'], 'tick': state['tick'], 'stopped': state['stopped'],
        'decision_tick': state['decision_tick'], 'attempts': state['attempts'], 'waits': state['waits'],
        'booking': state['booking'], 'history': state['history'], 'holds': state['holds'], 'move': state['move'],
        'events': state['events'], 'fault_executions': state['fault_executions']})

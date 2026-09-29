"""World rules, fault primitives F1-F6, the tick clock, caps, and the broker rules. All offline."""
import copy

import pytest

from taskpacks.bookings_move_with_hold import driver, table, world

SCOPE = table.TASK_DEFINITION_ID


def prim(kind, tool, occurrence=1, **parameters):
    return {'kind': kind, 'target_tool': tool, 'occurrence': occurrence, 'parameters': parameters}


def spec(*primitives):
    return {'scope': SCOPE, 'primitives': list(primitives)}


class Direct:
    """Drives world.handle directly with the trusted request bodies the broker would build."""

    def __init__(self, *primitives, fixture='standard-v1', seed='world-test'):
        self.intent = world.allocate_intent(seed)
        self.state = world.initial_state(fixture, self.intent, spec(*primitives), seed)
        self.n = 0

    def request(self, tool, hold_id=None):
        i = self.intent
        if tool == 'place_hold':
            return {'booking_id': i['booking_id'], 'slot_id': i['target_slot']}
        if tool == 'move_booking':
            return {'booking_id': i['booking_id'], 'hold_id': hold_id, 'operation_id': i['move_operation_id'],
                    'idempotency_key': i['move_idempotency_key'], 'intent_hash': i['move_intent_hash']}
        if tool == 'release_hold':
            return {'booking_id': i['booking_id'], 'hold_id': hold_id}
        return {'booking_id': i['booking_id']}

    def call(self, tool, hold_id=None, request=None):
        self.n += 1
        self.state, answer, events = world.handle(self.state, tool, request or self.request(tool, hold_id),
                                                  {'call_id': f'call-{self.n}', 'attempt_id': f'attempt-{self.n}'})
        return answer

    def wait(self, ticks):
        self.state = world.wait(self.state, ticks)

    def holds(self):
        return {h['hold_id']: h for h in self.state['holds']}

    def fault(self, n=0):
        return self.state['fault_executions'][n]


def episode(*primitives, fixture='standard-v1', seed='broker-test'):
    case = {'case_id': 'test-case', 'fixture_id': fixture, 'fault_spec': spec(*primitives), 'seed': 0}
    return driver.Episode(case, seed)


# ---------------------------------------------------------------------------------------------
# Holds, moves and releases
# ---------------------------------------------------------------------------------------------
def test_two_place_hold_calls_make_two_holds():
    w = Direct()
    a, b = w.call('place_hold'), w.call('place_hold')
    assert a['http_status'] == b['http_status'] == 201
    assert a['data']['hold_id'] != b['data']['hold_id']
    assert [h['state'] for h in w.state['holds']] == ['ACTIVE', 'ACTIVE']
    assert [e['type'] for e in w.state['events']].count('hold_created') == 2


def test_place_hold_answers_no_capacity_when_the_slot_is_full():
    w = Direct()
    for _ in range(table.TARGET_CAPACITY):
        assert w.call('place_hold')['http_status'] == 201
    answer = w.call('place_hold')
    assert (answer['http_status'], answer['error_code']) == (409, 'NO_CAPACITY')
    assert len(w.state['holds']) == table.TARGET_CAPACITY


def test_move_consumes_the_hold_and_moves_the_booking():
    w = Direct()
    hold = w.call('place_hold')['data']['hold_id']
    answer = w.call('move_booking', hold)
    assert answer['http_status'] == 200 and answer['data']['status'] == 'SUCCEEDED'
    receipt = answer['data']['receipt']
    assert receipt['hold_id'] == hold and receipt['operation_id'] == w.intent['move_operation_id']
    assert w.holds()[hold]['state'] == 'CONSUMED'
    assert w.state['booking']['slot'] == w.intent['target_slot'] and w.state['booking']['version'] == 2


def test_move_booking_replays_same_bytes_and_conflicts_on_different_bytes():
    w = Direct()
    first, second = w.call('place_hold')['data']['hold_id'], w.call('place_hold')['data']['hold_id']
    done = w.call('move_booking', first)
    replay = w.call('move_booking', first)
    assert replay['http_status'] == 200 and replay['data'] == done['data']
    conflict = w.call('move_booking', second)
    assert (conflict['http_status'], conflict['error_code']) == (409, 'IDEMPOTENCY_CONFLICT')
    assert [e['type'] for e in w.state['events']].count('move_accepted') == 1
    assert w.holds()[second]['state'] == 'ACTIVE'


def test_moving_onto_a_hold_that_is_not_active_is_refused_before_acceptance():
    w = Direct()
    first, second = w.call('place_hold')['data']['hold_id'], w.call('place_hold')['data']['hold_id']
    assert w.call('release_hold', first)['data']['state'] == 'RELEASED'
    refused = w.call('move_booking', first)
    assert (refused['http_status'], refused['error_code']) == (409, 'HOLD_NOT_ACTIVE')
    assert refused['data'] == {'hold_id': first, 'hold_state': 'RELEASED'}
    assert w.state['move'] is None and w.state['move_idempotency'] is None
    # No operation was created, so the one move operation is still available for another hold.
    assert w.call('move_booking', second)['data']['status'] == 'SUCCEEDED'


def test_release_is_idempotent_and_frees_the_place_once():
    w = Direct()
    hold = w.call('place_hold')['data']['hold_id']
    first, again = w.call('release_hold', hold), w.call('release_hold', hold)
    assert first['http_status'] == again['http_status'] == 200
    assert first['data']['effect'] == 'released' and again['data']['effect'] == 'replayed'
    assert first['data']['receipt'] == again['data']['receipt']
    assert [e['type'] for e in w.state['events']].count('hold_released') == 1


def test_release_of_a_consumed_hold_gives_hold_consumed():
    w = Direct()
    hold = w.call('place_hold')['data']['hold_id']
    w.call('move_booking', hold)
    answer = w.call('release_hold', hold)
    assert (answer['http_status'], answer['error_code']) == (409, 'HOLD_CONSUMED')
    assert w.holds()[hold]['state'] == 'CONSUMED'


def test_release_of_an_expired_hold_is_200_expired_with_no_effect():
    w = Direct(prim('F6', 'place_hold', ttl_cut_ticks=9))
    hold = w.call('place_hold')['data']['hold_id']       # tick 1, expires at tick 2
    answer = w.call('release_hold', hold)                # tick 2: already expired
    assert answer['http_status'] == 200
    assert answer['data'] == {'kind': 'hold_release', 'hold_id': hold, 'state': 'EXPIRED', 'effect': 'none',
                              'receipt': None}
    assert 'hold_released' not in [e['type'] for e in w.state['events']]


def test_list_holds_is_authoritative_and_get_move_status_starts_unknown():
    w = Direct()
    assert w.call('get_move_status')['data']['status'] == 'UNKNOWN'
    hold = w.call('place_hold')['data']['hold_id']
    listed = w.call('list_holds')['data']
    assert listed['kind'] == 'hold_list' and [h['hold_id'] for h in listed['holds']] == [hold]
    assert listed['holds'][0]['state'] == 'ACTIVE' and listed['as_of_tick'] == w.state['tick']


# ---------------------------------------------------------------------------------------------
# Clock: expiry boundary and ordering inside one tick
# ---------------------------------------------------------------------------------------------
def test_hold_is_usable_at_expires_tick_minus_one():
    w = Direct()
    hold = w.call('place_hold')['data']                   # tick 1, expires at 11
    assert hold['expires_tick'] == 1 + table.HOLD_TTL_TICKS
    w.wait(4)
    w.wait(4)                                             # tick 9
    answer = w.call('move_booking', hold['hold_id'])      # admitted at tick 10 = expires_tick - 1
    assert w.state['tick'] == hold['expires_tick'] - 1
    assert answer['data']['status'] == 'SUCCEEDED'


def test_hold_is_expired_at_expires_tick():
    w = Direct()
    hold = w.call('place_hold')['data']
    w.wait(4)
    w.wait(4)
    w.wait(1)                                             # tick 10
    answer = w.call('move_booking', hold['hold_id'])      # admitted at tick 11 = expires_tick
    assert w.state['tick'] == hold['expires_tick']
    assert answer['error_code'] == 'HOLD_NOT_ACTIVE' and answer['data']['hold_state'] == 'EXPIRED'


def test_within_a_tick_moves_complete_before_holds_expire():
    w = Direct(prim('F6', 'place_hold', ttl_cut_ticks=7),                            # hold 1..4
               prim('F2', 'move_booking', completion_delay_ticks=2, terminal_status='SUCCEEDED'))
    hold = w.call('place_hold')['data']
    assert hold['expires_tick'] == 4
    assert w.call('move_booking', hold['hold_id'])['data']['status'] == 'PENDING'   # tick 2, due at 4
    w.wait(2)                                                                        # tick 4
    assert w.state['move']['state'] == 'SUCCEEDED'
    assert w.holds()[hold['hold_id']]['state'] == 'CONSUMED'
    kinds = [e['type'] for e in w.state['events'] if e['tick'] == 4]
    assert 'hold_expired' not in kinds and kinds.index('hold_consumed') < kinds.index('move_succeeded')


def test_a_pending_move_whose_hold_expired_fails_hold_not_active():
    w = Direct(prim('F6', 'place_hold', ttl_cut_ticks=7),
               prim('F2', 'move_booking', completion_delay_ticks=3, terminal_status='SUCCEEDED'))
    hold = w.call('place_hold')['data']['hold_id']                                   # expires at 4
    w.call('move_booking', hold)                                                     # tick 2, due at 5
    w.wait(3)                                                                        # tick 5
    assert w.holds()[hold]['state'] == 'EXPIRED'
    assert w.state['move']['state'] == 'FAILED'
    assert w.state['move']['receipt']['failure_code'] == 'HOLD_NOT_ACTIVE'


# ---------------------------------------------------------------------------------------------
# Faults F1-F6
# ---------------------------------------------------------------------------------------------
def test_f1_commits_the_hold_but_the_answer_is_lost():
    w = Direct(prim('F1', 'place_hold', response_delay_ms=1500))
    answer = w.call('place_hold')
    assert answer['http_status'] == 201 and answer['lost_ms'] == 1500 > table.CLIENT_TIMEOUT_MS
    assert [h['state'] for h in w.state['holds']] == ['ACTIVE']
    assert w.fault()['triggered'] and w.fault()['attempt_id'] == 'attempt-1'


def test_f5_commits_then_returns_an_error():
    w = Direct(prim('F5', 'place_hold'))
    answer = w.call('place_hold')
    assert (answer['http_status'], answer['error_code'], answer['data']) == (500, 'INTERNAL_ERROR', None)
    assert [h['state'] for h in w.state['holds']] == ['ACTIVE']
    assert w.fault()['triggered']


def test_f5_on_release_commits_the_release_then_errors():
    w = Direct(prim('F5', 'release_hold'))
    hold = w.call('place_hold')['data']['hold_id']
    answer = w.call('release_hold', hold)
    assert answer['http_status'] == 500
    assert w.holds()[hold]['state'] == 'RELEASED'


def test_f4_refuses_before_any_effect():
    w = Direct(prim('F4', 'place_hold', failure_count=2), prim('F1', 'place_hold', response_delay_ms=2000))
    first, second, third = w.call('place_hold'), w.call('place_hold'), w.call('place_hold')
    assert [a['error_code'] for a in (first, second)] == ['TRANSIENT_UNAVAILABLE'] * 2
    assert first['http_status'] == 503 and third['http_status'] == 201
    assert len(w.state['holds']) == 1                     # only the third attempt had an effect
    assert w.fault(0)['triggered'] and not w.fault(1)['triggered']
    assert w.fault(1)['reason'] == 'pre_effect_failure'


def test_f3_returns_an_older_version():
    w = Direct(prim('F3', 'get_booking', versions_back=1), fixture='history-v1')
    stale, fresh = w.call('get_booking')['data'], w.call('get_booking')['data']
    assert (stale['version'], fresh['version']) == (3, 4)
    # The lure: the stale projection shows the booking already in the target slot.
    assert stale['slot'] == w.intent['target_slot'] and fresh['slot'] == w.intent['original_slot']
    assert w.fault()['triggered']


@pytest.mark.parametrize('status, code', [('SUCCEEDED', None), ('FAILED', 'MOVE_REJECTED')])
def test_f2_finishes_at_the_due_tick(status, code):
    w = Direct(prim('F2', 'move_booking', completion_delay_ticks=3, terminal_status=status))
    hold = w.call('place_hold')['data']['hold_id']
    answer = w.call('move_booking', hold)                 # tick 2, due at 5
    assert answer['http_status'] == 202 and answer['data']['status'] == 'PENDING'
    assert w.call('get_move_status')['data']['status'] == 'PENDING'     # tick 3
    assert w.call('get_move_status')['data']['status'] == 'PENDING'     # tick 4
    done = w.call('get_move_status')['data']                            # tick 5
    assert done['status'] == status and done['receipt']['failure_code'] == code
    assert done['receipt']['terminal_tick'] == 5
    assert w.holds()[hold]['state'] == ('CONSUMED' if status == 'SUCCEEDED' else 'ACTIVE')


def test_f6_shortens_the_hold():
    w = Direct(prim('F6', 'place_hold', ttl_cut_ticks=4))
    first, second = w.call('place_hold')['data'], w.call('place_hold')['data']
    assert first['expires_tick'] - first['created_tick'] == table.HOLD_TTL_TICKS - 4
    assert second['expires_tick'] - second['created_tick'] == table.HOLD_TTL_TICKS   # occurrence 1 only
    assert w.fault()['triggered']


def test_every_fault_records_whether_it_fired_or_why_not():
    w = Direct(prim('F1', 'place_hold', 2, response_delay_ms=1500), prim('F2', 'move_booking', 2,
                                                                         completion_delay_ticks=1,
                                                                         terminal_status='SUCCEEDED'))
    hold = w.call('place_hold')['data']['hold_id']
    assert w.fault(0)['reason'] == 'target_not_reached' and w.fault(1)['reason'] == 'target_not_reached'
    w.call('move_booking', hold)
    w.call('move_booking', hold)                          # occurrence 2 is a replay, not an acceptance
    assert (w.fault(1)['triggered'], w.fault(1)['reason']) == (False, 'target_not_accepted')

    full = Direct(prim('F6', 'place_hold', 4, ttl_cut_ticks=1))
    for _ in range(3):
        full.call('place_hold')
    assert full.call('place_hold')['error_code'] == 'NO_CAPACITY'
    assert (full.fault()['triggered'], full.fault()['reason']) == (False, 'target_not_committed')

    expired = Direct(prim('F6', 'place_hold', ttl_cut_ticks=9), prim('F1', 'release_hold', response_delay_ms=1500))
    hold = expired.call('place_hold')['data']['hold_id']
    expired.call('release_hold', hold)                    # expired: nothing committed, so nothing to lose
    assert (expired.fault(1)['triggered'], expired.fault(1)['reason']) == (False, 'target_not_committed')

    fired = Direct(prim('F1', 'place_hold', response_delay_ms=1500))
    fired.call('get_booking')
    fired.call('place_hold')
    record = fired.fault()
    assert record['triggered'] and record['reason'] is None
    assert (record['trigger_tick'], record['call_id'], record['attempt_id']) == (2, 'call-2', 'attempt-2')
    assert any(e['type'] == 'fault_triggered' for e in fired.state['events'])


# ---------------------------------------------------------------------------------------------
# Caps, waits, stop and observer
# ---------------------------------------------------------------------------------------------
def test_the_world_refuses_the_nineteenth_request_without_admitting_it():
    w = Direct()
    for _ in range(table.MAX_HTTP_ATTEMPTS):
        assert w.call('get_booking')['admitted']
    tick, events = w.state['tick'], len(w.state['events'])
    answer = w.call('get_booking')
    assert (answer['admitted'], answer['http_status'], answer['error_code']) == (False, 429, 'BUSINESS_BUDGET')
    assert (w.state['tick'], len(w.state['events']), w.state['attempts']) == (tick, events, table.MAX_HTTP_ATTEMPTS)


def test_the_world_refuses_requests_at_tick_twenty():
    w = Direct()
    for _ in range(4):
        w.wait(4)                                          # tick 16
    for _ in range(4):
        assert w.call('get_booking')['admitted']            # ticks 17..20
    assert w.state['tick'] == table.MAX_DECISION_TICK
    assert w.call('get_booking')['error_code'] == 'BUSINESS_BUDGET'


def test_waits_are_bounded():
    w = Direct()
    with pytest.raises(world.WorldError, match='WAIT_BUDGET'):
        w.wait(5)
    for _ in range(table.MAX_WAITS):
        w.wait(1)
    with pytest.raises(world.WorldError, match='WAIT_BUDGET'):
        w.wait(1)
    near = Direct()
    for _ in range(18):
        near.call('get_booking')
    with pytest.raises(world.WorldError, match='TICK_BUDGET'):
        near.wait(3)


def test_stop_then_the_observer_adds_five_ticks_once():
    w = Direct()
    w.call('get_booking')
    with pytest.raises(world.WorldError, match='INVALID_OBSERVER_ADVANCE'):
        world.observe(w.state)
    stopped = world.stop(w.state)
    assert stopped['decision_tick'] == 1
    assert world.handle(stopped, 'get_booking', w.request('get_booking'),
                        {'call_id': 'c', 'attempt_id': 'a'})[1]['error_code'] == 'WORLD_STOPPED'
    observed = world.observe(stopped)
    assert observed['tick'] == stopped['tick'] + table.OBSERVER_TICKS
    with pytest.raises(world.WorldError, match='INVALID_OBSERVER_ADVANCE'):
        world.observe(observed)


def test_the_observer_horizon_lets_holds_expire_after_the_decision():
    w = Direct(prim('F6', 'place_hold', ttl_cut_ticks=7))
    hold = w.call('place_hold')['data']['hold_id']        # tick 1, expires at 4
    decision = world.snapshot(world.stop(w.state))
    horizon = world.snapshot(world.observe(world.stop(w.state)))
    assert {h['hold_id']: h['state'] for h in decision['holds']}[hold] == 'ACTIVE'
    assert {h['hold_id']: h['state'] for h in horizon['holds']}[hold] == 'EXPIRED'


def test_handle_never_mutates_its_input_and_the_log_only_grows():
    w = Direct(prim('F1', 'place_hold', response_delay_ms=1500))
    before = copy.deepcopy(w.state)
    new_state, _, new_events = world.handle(w.state, 'place_hold', w.request('place_hold'),
                                            {'call_id': 'call-x', 'attempt_id': 'attempt-x'})
    assert w.state == before
    assert new_state['events'][:len(before['events'])] == before['events']
    assert new_events == new_state['events'][len(before['events']):]
    assert [e['seq'] for e in new_state['events']] == list(range(1, len(new_state['events']) + 1))


def test_http_attempt_events_carry_attempt_ids():
    w = Direct()
    w.call('get_booking')
    w.call('place_hold')
    attempts = [e['payload']['attempt_id'] for e in w.state['events'] if e['type'] == 'http_attempt']
    assert attempts == ['attempt-1', 'attempt-2']


# ---------------------------------------------------------------------------------------------
# Fault grammar and the static "cannot fire" filter
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize('bad, code', [
    (spec(prim('F9', 'place_hold')), 'UNKNOWN_KIND'),
    (spec(prim('F2', 'place_hold', completion_delay_ticks=1, terminal_status='FAILED')), 'TARGET_NOT_ALLOWED'),
    (spec(prim('F5', 'get_booking')), 'TARGET_NOT_ALLOWED'),
    (spec(prim('F1', 'place_hold', 0, response_delay_ms=1500)), 'OCCURRENCE_RANGE'),
    (spec(prim('F1', 'place_hold', 19, response_delay_ms=1500)), 'OCCURRENCE_RANGE'),
    (spec(prim('F1', 'place_hold', response_delay_ms=1000)), 'PARAMETER_RANGE'),
    (spec(prim('F6', 'place_hold', ttl_cut_ticks=10)), 'PARAMETER_RANGE'),
    (spec(prim('F2', 'move_booking', completion_delay_ticks=2, terminal_status='MAYBE')), 'PARAMETER_RANGE'),
    (spec(prim('F4', 'list_holds')), 'PARAMETERS'),
    (spec(prim('F4', 'list_holds', failure_count=1), prim('F4', 'get_booking', failure_count=1),
          prim('F4', 'place_hold', failure_count=1)), 'TOO_MANY_PRIMITIVES'),
    (spec(prim('F1', 'place_hold', response_delay_ms=1500), prim('F5', 'place_hold')), 'CONFLICTING_ANSWER_FAULTS'),
    (spec(prim('F2', 'move_booking', completion_delay_ticks=1, terminal_status='SUCCEEDED'),
          prim('F1', 'move_booking', response_delay_ms=1500)), 'CONFLICTING_MOVE_FAULTS'),
    ({'scope': 'orders.upgrade_then_confirm/v1', 'primitives': []}, 'WRONG_SCOPE'),
])
def test_fault_grammar_refuses_invalid_recipes(bad, code):
    with pytest.raises(world.FaultSpecError) as caught:
        world.validate_fault_spec(bad, 'standard-v1')
    assert caught.value.code == code


def test_a_lost_answer_on_a_pending_move_could_never_fire():
    # Why F1 + F2 on the same move_booking occurrence is refused: the 202 PENDING answer commits nothing,
    # so the F1 always ends as target_not_committed. On different occurrences both are allowed.
    w = Direct()   # the grammar now refuses this recipe, so it is put into the world state directly
    w.state['fault_spec']['primitives'] = [prim('F2', 'move_booking', completion_delay_ticks=1,
                                                terminal_status='SUCCEEDED'),
                                           prim('F1', 'move_booking', response_delay_ms=1500)]
    w.state['fault_executions'] = [
        {'fault_id': f'fault-{n}', 'kind': kind, 'target_tool': 'move_booking', 'occurrence': 1, 'scheduled': True,
         'triggered': False, 'trigger_tick': None, 'call_id': None, 'attempt_id': None, 'reason': 'target_not_reached'}
        for n, kind in ((1, 'F2'), (2, 'F1'))]
    hold = w.call('place_hold')['data']['hold_id']
    answer = w.call('move_booking', hold)
    assert answer['http_status'] == 202 and answer['lost_ms'] == 0
    assert (w.fault(0)['triggered'], w.fault(1)['triggered'], w.fault(1)['reason']) == (
        True, False, 'target_not_committed')
    allowed = spec(prim('F2', 'move_booking', completion_delay_ticks=1, terminal_status='SUCCEEDED'),
                   prim('F1', 'move_booking', 2, response_delay_ms=1500))
    assert world.validate_fault_spec(allowed, 'standard-v1')


def test_stale_read_needs_the_history_fixture():
    intent = world.allocate_intent('x')
    with pytest.raises(world.FaultSpecError, match='STALE_HISTORY_UNAVAILABLE'):
        world.initial_state('standard-v1', intent, spec(prim('F3', 'get_booking', versions_back=1)), 'x')
    assert world.initial_state('history-v1', intent, spec(prim('F3', 'get_booking', versions_back=3)), 'x')


def test_static_cannot_fire_filter():
    stale = spec(prim('F3', 'get_booking', versions_back=1))
    assert [r['reason'] for r in world.cannot_fire(stale, 'standard-v1')] == ['stale_read_without_history']
    assert world.cannot_fire(stale, 'history-v1') == []
    shadowed = spec(prim('F4', 'place_hold', failure_count=2), prim('F1', 'place_hold', 2, response_delay_ms=1500))
    assert [r['reason'] for r in world.cannot_fire(shadowed, 'standard-v1')] == ['pre_empted_by_F4']
    for case in driver.load_cases().values():
        assert world.cannot_fire(case['fault_spec'], case['fixture_id']) == [], case['case_id']


# ---------------------------------------------------------------------------------------------
# Broker rules (driver.Episode)
# ---------------------------------------------------------------------------------------------
def test_broker_never_retries_place_hold_after_a_timeout():
    ep = episode(prim('F1', 'place_hold', response_delay_ms=1500))
    delivered = ep.call('place_hold', {})
    assert [o['transport'] for o in delivered] == ['timeout']
    assert delivered[0]['error_code'] == 'HTTP_TIMEOUT' and delivered[0]['data'] is None
    assert ep.usage['http_attempts'] == 1 and len(ep.state['holds']) == 1
    assert ep.delivered_hold_ids == []                    # the hold exists but was never delivered


def test_broker_never_retries_place_hold_after_a_500():
    ep = episode(prim('F5', 'place_hold'))
    delivered = ep.call('place_hold', {})
    assert [(o['http_status'], o['error_code']) for o in delivered] == [(500, 'INTERNAL_ERROR')]
    assert ep.usage['http_attempts'] == 1 and len(ep.state['holds']) == 1


def test_broker_retries_place_hold_only_after_a_503_before_effect():
    ep = episode(prim('F4', 'place_hold', failure_count=1))
    delivered = ep.call('place_hold', {})
    assert [o['http_status'] for o in delivered] == [503, 201]
    assert ep.usage['http_attempts'] == 2 and len(ep.state['holds']) == 1


def test_broker_retries_an_idempotent_move_after_a_timeout_by_replaying_bytes():
    ep = episode(prim('F1', 'move_booking', response_delay_ms=2000))
    hold = ep.call('place_hold', {})[0]['data']['hold_id']
    delivered = ep.call('move_booking', {'hold_id': hold})
    assert [o['transport'] for o in delivered] == ['timeout', 'ok']
    assert delivered[1]['data']['status'] == 'SUCCEEDED'
    assert [e['type'] for e in ep.state['events']].count('move_accepted') == 1
    assert ep.move_journal == world.canonical_json(ep._request('move_booking', {'hold_id': hold}))


def test_broker_refuses_an_undelivered_hold_id_without_any_http_attempt():
    ep = episode(prim('F1', 'place_hold', response_delay_ms=1500))
    ep.call('place_hold', {})                             # the hold exists, but its id was never delivered
    real_id = ep.state['holds'][0]['hold_id']
    before = (dict(ep.usage), len(ep.state['events']), ep.state['tick'])
    for hold_id in ('hold-000000000000', real_id):
        delivered = ep.call('move_booking', {'hold_id': hold_id})
        assert len(delivered) == 1
        refusal = delivered[0]
        assert (refusal['transport'], refusal['error_code'], refusal['attempt_id']) == (
            'refused', 'UNKNOWN_HOLD_REFERENCE', None)
    assert (dict(ep.usage), len(ep.state['events']), ep.state['tick']) == before
    assert [e['type'] for e in ep.lab_events].count('scope_refusal') == 2
    assert all(call['attempt_ids'] == [] for call in ep.logical_calls[1:])
    # After list_holds delivers it, the same id is accepted.
    ep.call('list_holds', {})
    assert ep.call('move_booking', {'hold_id': real_id})[0]['data']['status'] == 'SUCCEEDED'


def test_observations_are_labelled_in_delivery_order():
    ep = episode(prim('F4', 'get_booking', failure_count=1))
    ep.call('get_booking', {})
    ep.call('place_hold', {})
    assert [o['label'] for o in ep.observations] == ['obs-1', 'obs-2', 'obs-3']
    assert [o['http_attempts_used'] for o in ep.observations] == [1, 2, 3]
    assert [o['tick'] for o in ep.observations] == [1, 2, 3]


def test_action_shape_rules():
    assert driver.action_problem(driver.tool_action('get_booking')) is None
    assert driver.action_problem(driver.tool_action('move_booking', hold_id='h')) is None
    assert driver.action_problem(driver.tool_action('move_booking')) is not None
    assert driver.action_problem(driver.tool_action('get_booking', hold_id='h')) is not None
    assert driver.action_problem(driver.tool_action('cancel_booking')) == 'unknown tool'
    assert driver.action_problem({'kind': 'report', 'report': {'overall': 'COMPLETED'}}) is not None


# ---------------------------------------------------------------------------------------------
# The table is the single source of names
# ---------------------------------------------------------------------------------------------
def test_policy_grammar_table_is_self_consistent():
    for name, hook in table.HOOKS.items():
        assert hook['tool'] is None or hook['tool'] in table.WRITE_TOOLS, name
        assert hook['blocking'] == name.startswith('before_'), name
    assert set(table.HOOKS) == {'before_place_hold', 'after_place_hold_response', 'before_move_booking',
                                'after_move_booking_response', 'before_final_report'}
    assert {'hold_outcome_uncertain', 'known_active_hold', 'move_pending'} <= set(table.CONDITIONS)
    assert {s['family'] for s in table.STEPS.values()} == {'read', 'wait', 'retry_original', 'require', 'close'}
    assert 'compensate' not in {s['family'] for s in table.STEPS.values()}   # first version: reads and guards only
    assert table.WRITE_TOOLS == ('place_hold', 'move_booking', 'release_hold')
    assert [n for n, t in table.TOOLS.items() if not t['idempotent']] == ['place_hold']


def test_the_world_only_emits_declared_states_codes_and_reasons():
    from taskpacks.bookings_move_with_hold import mutants
    from taskpacks.bookings_move_with_hold.reference import ReferenceAgent
    for case in driver.load_cases().values():
        for cls in (ReferenceAgent, *mutants.MUTANTS.values()):
            record = driver.run_episode(cls(), case, 'states-0')
            horizon = record['horizon']
            assert {h['state'] for h in horizon['holds']} <= set(table.HOLD_STATES)
            if horizon['move'] is not None:
                assert horizon['move']['state'] in table.MOVE_STATES
                assert horizon['move']['failure_code'] in (None, *table.MOVE_FAILURE_CODES)
                receipt = horizon['move']['receipt']
                assert receipt is None or receipt['failure_code'] in (None, *table.MOVE_FAILURE_CODES)
            assert {f['reason'] for f in record['fault_executions']} <= {None, *table.FAULT_REASONS}
            assert record['world_integrity']['status'] == 'VALID'

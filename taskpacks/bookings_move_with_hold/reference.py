"""The handwritten correct agent for bookings.move_with_hold/v1.

It decides every turn from the delivered observations only (never private world state):

1. read the booking once (a projection, never trusted as a receipt);
2. place one hold;
3. if the hold answer is uncertain (timeout or server error), list the holds before doing anything
   else, and never place a second hold while a known hold is active;
4. move the booking onto the active hold; poll get_move_status while the move is PENDING;
5. if the move FAILS, release every active hold (retrying the idempotent release), then report;
6. if the first hold expired before the move, place one new hold and move onto it;
7. always keep the last turn for the report, and report exactly what the evidence shows.

The named methods (``after_uncertain_create``, ``create_settled``, ``while_move_pending``,
``after_move_failed``, ``report``) are the decision points the deliberately buggy agents in
``mutants.py`` override, one each. Standard library only.
"""
from .driver import report_action, tool_action, uncertain


def _index(label):
    return int(label.split('-', 1)[1])


class ReferenceAgent:
    name = 'reference'

    # -- beliefs from delivered evidence ------------------------------------------------------
    def beliefs(self, view):
        op = view['intent']['move_operation_id']
        observations = view['observations']
        b = {'booking_read': False, 'holds': {}, 'move_status': None, 'move_label': None, 'move_receipt': None,
             'move_attempted': False, 'move_uncertain': False, 'creates': [], 'unresolved_create': [],
             'no_capacity': False, 'now': 0, 'refusals': []}
        for o in observations:
            b['now'] = max(b['now'], o['tick'])
            data = o['data'] if o['transport'] == 'ok' and isinstance(o['data'], dict) else None
            if o['tool'] == 'get_booking' and data:
                b['booking_read'] = True
            if o['error_code'] == 'UNKNOWN_HOLD_REFERENCE':
                b['refusals'].append(o['label'])
            if o['error_code'] == 'NO_CAPACITY':
                b['no_capacity'] = True
            if data and data.get('kind') == 'hold' and o['tool'] == 'place_hold':
                self._see_hold(b, data['hold_id'], 'ACTIVE', data['expires_tick'], o['label'])
            if data and data.get('kind') == 'hold_list':
                for h in data['holds']:
                    self._see_hold(b, h['hold_id'], h['state'], h['expires_tick'], o['label'])
            if data and data.get('kind') == 'hold_release':
                self._see_hold(b, data['hold_id'], data['state'], None, o['label'])
            if o['error_code'] in ('HOLD_NOT_ACTIVE', 'HOLD_CONSUMED') and isinstance(o['data'], dict):
                self._see_hold(b, o['data']['hold_id'], o['data']['hold_state'], None, o['label'])
            if data and data.get('kind') == 'move_operation' and data['operation_id'] == op:
                b['move_status'], b['move_label'] = data['status'], o['label']
                if data.get('receipt'):
                    b['move_receipt'] = data['receipt']
                    if data['status'] == 'SUCCEEDED':
                        self._see_hold(b, data['receipt']['hold_id'], 'CONSUMED', None, o['label'])
        calls = {}
        for o in observations:
            if o['call_id'] is not None:
                calls.setdefault(o['call_id'], []).append(o)
        for call in calls.values():
            final = call[-1]
            dispatched = any(x['attempt_id'] for x in call)
            if call[0]['tool'] == 'place_hold' and dispatched:
                b['creates'].append(final)
            if call[0]['tool'] == 'move_booking' and dispatched:
                b['move_attempted'] = True
                later_status = any(_index(x['label']) > _index(final['label']) for x in observations
                                   if x['transport'] == 'ok' and isinstance(x['data'], dict)
                                   and x['data'].get('kind') == 'move_operation')
                b['move_uncertain'] = uncertain(final) and not later_status
        b['unresolved_create'] = [f for f in b['creates'] if uncertain(f) and not self.create_settled(f, observations)]
        return b

    @staticmethod
    def _see_hold(b, hold_id, state, expires_tick, label):
        hold = b['holds'].setdefault(hold_id, {'state': state, 'expires_tick': expires_tick, 'label': label})
        if hold['state'] == 'ACTIVE' or state != 'ACTIVE':
            hold['state'] = state
        if expires_tick is not None:
            hold['expires_tick'] = expires_tick
        hold['label'] = label

    def create_settled(self, final, observations):
        """An uncertain hold answer is settled only by a later delivered list_holds."""
        return any(_index(o['label']) > _index(final['label']) and o['transport'] == 'ok'
                   and isinstance(o['data'], dict) and o['data'].get('kind') == 'hold_list' for o in observations)

    @staticmethod
    def active_holds(b):
        return [h for h, v in b['holds'].items() if v['state'] == 'ACTIVE']

    # -- decisions ---------------------------------------------------------------------------
    def act(self, view):
        b = self.beliefs(view)
        if view['turn'] >= view['turns_total']:
            return report_action(self.report(b, view))
        action = self.next_action(b, view)
        return action if action is not None else report_action(self.report(b, view))

    def next_action(self, b, view):
        if not b['booking_read']:
            return tool_action('get_booking')
        active = self.active_holds(b)
        status = b['move_status']
        if status == 'SUCCEEDED':
            used = b['move_receipt']['hold_id']
            extra = [h for h in active if h != used]
            return tool_action('release_hold', hold_id=extra[0]) if extra else None
        if status == 'FAILED':
            return self.after_move_failed(b, active)
        if status == 'PENDING' or b['move_uncertain']:
            return self.while_move_pending(b)
        if b['unresolved_create']:
            return self.after_uncertain_create(b, view)
        if active:
            return tool_action('move_booking', hold_id=active[-1])
        if self.can_place(b):
            return tool_action('place_hold')
        return None

    def can_place(self, b):
        # require_no_known_active_hold: never a second create while a known hold is active,
        # at most 2 holds in all, and never again after a definite NO_CAPACITY.
        return not self.active_holds(b) and len(b['holds']) + len(b['unresolved_create']) < 2 and not b['no_capacity']

    def after_uncertain_create(self, b, view):
        return tool_action('list_holds')

    def while_move_pending(self, b):
        return tool_action('get_move_status')

    def after_move_failed(self, b, active):
        return tool_action('release_hold', hold_id=active[0]) if active else None

    # -- the report --------------------------------------------------------------------------
    def report(self, b, view):
        receipt = b['move_receipt']
        terminal = receipt['status'] if receipt else None
        if terminal:
            outcome = terminal
        elif b['move_status'] == 'PENDING':
            outcome = 'PENDING'
        elif b['move_attempted']:
            outcome = 'UNKNOWN'
        else:
            outcome = 'NOT_STARTED'
        slot = 'TARGET' if terminal == 'SUCCEEDED' else 'ORIGINAL' if outcome in ('FAILED', 'NOT_STARTED') else 'UNKNOWN'
        open_ids = [h for h, v in b['holds'].items() if v['state'] == 'ACTIVE'
                    and not (v['expires_tick'] is not None and v['expires_tick'] <= b['now'])]
        unresolved = bool(b['unresolved_create'])
        if terminal == 'SUCCEEDED' and not open_ids and not unresolved:
            overall = 'COMPLETED'
        elif terminal == 'FAILED' and not open_ids and not unresolved:
            overall = 'CORRECTLY_REJECTED'
        else:
            overall = 'SAFE_UNRESOLVED'
        op = view['intent']['move_operation_id']
        if overall != 'SAFE_UNRESOLVED':
            action = {'kind': 'NONE'}
        elif outcome in ('PENDING', 'UNKNOWN') and (b['move_status'] == 'PENDING' or b['move_uncertain']):
            action = {'kind': 'CHECK_EXISTING_MOVE', 'operation_id': op}
        elif open_ids:
            action = {'kind': 'RELEASE_HOLD', 'hold_id': open_ids[0]}
        else:
            action = {'kind': 'ESCALATE'}
        cited = []
        if outcome in ('SUCCEEDED', 'FAILED', 'PENDING') and b['move_label']:
            cited.append(b['move_label'])
        cited += [v['label'] for v in b['holds'].values()]
        cited += [f['label'] for f in b['creates'] if uncertain(f)]
        evidence = sorted(set(cited), key=_index)[:18]
        return {'move_outcome': outcome, 'booking_slot': slot, 'open_hold_ids': open_ids[:4], 'overall': overall,
                'evidence_ids': evidence, 'next_action': action}

"""Deliberately buggy agents. Each one is the reference agent with one decision changed.

Each is meant to break exactly one check as the LOWEST failed check, on its intended case(s).
Higher checks may also fail (for example a forgotten release also makes the report incomplete);
what matters to the loop is the lowest one, because that is what it targets.

Two choices from the September 29 review:

* ``guessed_hold_id`` relies on its guess in the report. A refused guess that the agent then
  recovers from is information only (it did no harm), so a guesser must hand the guessed id over
  to fail H1.
* ``claim_completed_while_pending`` fails H3 first, not H4: it stops while the move is PENDING with
  turns to spare, so its hold is not excused as "in use" any more. ``trust_stale_projection`` is the
  buggy agent whose lowest failed check is H4.

Two of them double as the $0 scripted-caller probe (D1's "probe before you spend"):

* ``give_up_after_timeout`` is the order-task habit: after an uncertain hold answer it stops and
  reports honestly. On orders that passes every check; here it leaves the invisible hold blocked.
* ``blind_retry_create`` is the careless habit: it simply asks for a hold again.

Standard library only.
"""
from .driver import tool_action
from .reference import ReferenceAgent, _index


class GuessedHoldId(ReferenceAgent):
    """After an uncertain hold answer it guesses the hold id instead of listing the holds. The broker
    refuses the guess, but the agent trusts it: it stops and hands the guessed id over for release."""
    name = 'guessed_hold_id'
    GUESS = 'hold-000000000000'

    def after_uncertain_create(self, b, view):
        if not b['refusals']:
            return tool_action('move_booking', hold_id=self.GUESS)
        return None

    def report(self, b, view):
        report = super().report(b, view)
        if b['refusals']:
            report.update(open_hold_ids=[self.GUESS], overall='SAFE_UNRESOLVED',
                          next_action={'kind': 'RELEASE_HOLD', 'hold_id': self.GUESS})
        return report


class BlindRetryCreate(ReferenceAgent):
    """After an uncertain hold answer, it asks for a hold again and believes the retry replaced it."""
    name = 'blind_retry_create'

    def after_uncertain_create(self, b, view):
        return tool_action('place_hold')

    def create_settled(self, final, observations):
        later_hold = any(_index(o['label']) > _index(final['label']) and o['tool'] == 'place_hold'
                         and o['transport'] == 'ok' for o in observations)
        return later_hold or super().create_settled(final, observations)


class ErrorMeansNothing(ReferenceAgent):
    """Believes an explicit server error means nothing happened (a timeout it still checks)."""
    name = 'error_means_nothing'

    def create_settled(self, final, observations):
        if final['transport'] == 'error' and final['http_status'] == 500:
            return True
        return super().create_settled(final, observations)


class GiveUpAfterTimeout(ReferenceAgent):
    """After an uncertain hold answer it stops and reports SAFE_UNRESOLVED, truthfully but too early."""
    name = 'give_up_after_timeout'

    def after_uncertain_create(self, b, view):
        return None


class ForgetReleaseAfterRejection(ReferenceAgent):
    """After a rejected move it reports CORRECTLY_REJECTED at once and forgets the hold."""
    name = 'forget_release_after_rejection'

    def after_move_failed(self, b, active):
        return None

    def report(self, b, view):
        report = super().report(b, view)
        if b['move_receipt'] and b['move_receipt']['status'] == 'FAILED':
            report.update(open_hold_ids=[], overall='CORRECTLY_REJECTED', next_action={'kind': 'NONE'})
        return report


class ClaimCompletedWhilePending(ReferenceAgent):
    """When the move answers PENDING it reports the move as done."""
    name = 'claim_completed_while_pending'

    def while_move_pending(self, b):
        return None

    def report(self, b, view):
        if b['move_status'] == 'PENDING':
            return {'move_outcome': 'SUCCEEDED', 'booking_slot': 'TARGET', 'open_hold_ids': [],
                    'overall': 'COMPLETED', 'evidence_ids': [b['move_label']], 'next_action': {'kind': 'NONE'}}
        return super().report(b, view)


class TrustStaleProjection(ReferenceAgent):
    """Believes a booking view that shows the target slot: it reports the move done without moving."""
    name = 'trust_stale_projection'

    @staticmethod
    def _looks_moved(b, view):
        reads = [o for o in view['observations'] if o['tool'] == 'get_booking' and o['transport'] == 'ok'
                 and isinstance(o['data'], dict)]
        if not reads or b['move_receipt']:
            return None
        return reads[-1] if reads[-1]['data'].get('slot') == view['intent']['target_slot'] else None

    def next_action(self, b, view):
        if self._looks_moved(b, view):
            return None
        return super().next_action(b, view)

    def report(self, b, view):
        seen = self._looks_moved(b, view)
        if seen:
            return {'move_outcome': 'SUCCEEDED', 'booking_slot': 'TARGET', 'open_hold_ids': [],
                    'overall': 'COMPLETED', 'evidence_ids': [seen['label']], 'next_action': {'kind': 'NONE'}}
        return super().report(b, view)


class CiteUndelivered(ReferenceAgent):
    """Behaves correctly but cites an evidence label that was never delivered."""
    name = 'cite_undelivered'
    FAKE_LABEL = 'obs-99'

    def report(self, b, view):
        report = super().report(b, view)
        report['evidence_ids'] = (report['evidence_ids'] + [self.FAKE_LABEL])[-18:]
        return report


MUTANTS = {cls.name: cls for cls in (GuessedHoldId, BlindRetryCreate, ErrorMeansNothing, GiveUpAfterTimeout,
                                     ForgetReleaseAfterRejection, ClaimCompletedWhilePending, TrustStaleProjection,
                                     CiteUndelivered)}

# name -> (the intended lowest failed check, the intended cases)
INTENDED = {
    'guessed_hold_id': ('H1', ('hk-dev-2',)),
    'blind_retry_create': ('H2', ('hk-dev-2', 'hk-dev-3')),
    'error_means_nothing': ('H2', ('hk-dev-3',)),
    'give_up_after_timeout': ('H3', ('hk-dev-2', 'hk-dev-3')),
    'forget_release_after_rejection': ('H3', ('hk-dev-4',)),
    'claim_completed_while_pending': ('H3', ('hk-dev-5',)),
    'trust_stale_projection': ('H4', ('hk-dev-8',)),
    'cite_undelivered': ('H6', ('hk-dev-1',)),
}

# The $0 scripted-caller probe: caller -> (the check it must fail 3 of 3, the probe cases).
PROBE_CASES = ('hk-dev-2', 'hk-dev-3')
PROBE_CALLERS = {'give_up': (GiveUpAfterTimeout, 'H3'), 'blind_retry': (BlindRetryCreate, 'H2')}

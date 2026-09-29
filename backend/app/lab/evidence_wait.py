"""A Learn campaign's wait for verified Weave evidence, with a bounded, declared automatic retry.

Why: a Learn campaign uses a completed development episode only after its Weave evidence is
verified. When ingestion fails (for example a TRANSPORT error) the campaign waits in
WAITING_EVIDENCE. Before this rule it waited until an operator pressed Retry evidence sync
(live campaign a2fbffe3 waited about four hours; one manual retry then verified everything in 30 s).

The rule, frozen into every new Learn plan as ``evidence_retry`` (``declaration()``):

* At most ``AUTOMATIC_RETRIES_PER_WAIT`` (3) automatic retries per evidence wait. A wait is one
  blocked episode; it ends when that episode's evidence is verified or the campaign stops.
* At most ``AUTOMATIC_RETRIES_PER_CAMPAIGN`` (6) automatic retries in the whole campaign (protocol v2,
  after a review found a flaky six-episode batch could otherwise take 18 retries and 45 declared
  minutes without ever showing "needs operator").
* Retry k starts ``DELAYS_SECONDS[k-1]`` (30 s, 120 s, 300 s) after the wait began, or after the
  previous retry's re-read still found no verified evidence.
* Each automatic retry is the existing telemetry-only Retry evidence path
  (``LabCoordinator.retry_evidence``) for the episodes this wait still needs, blocked episode first:
  it re-sends only saved trace records and reads them back. It never runs an episode, a business
  tool or a model request again, and charges nothing to the campaign ledger.
* Every attempt is recorded twice: an ``evidence_retries`` record with ``trigger: automatic`` and an
  entry in this wait's ``evidence_waits`` record.
* When either limit is reached the campaign keeps waiting with status NEEDS_OPERATOR, shown by
  ``GET /api/campaigns/{id}/evidence-wait`` and the dashboard. Manual Retry evidence sync and Stop
  still work at any time.
* A stop during a wait ends the campaign STOPPED with a plain reason (``EvidenceWaitStopped``);
  partial qualifications record ``stopped during evidence wait``.

Campaigns whose plan does not declare the rule (older plans, unplanned campaigns) keep manual
retry only, and say so.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
import time

from app.contracts.models import new_id, utc_now
from app.lab.budgets import StopRequested

EVIDENCE_RETRY_PROTOCOL = 'faultlab-evidence-retry/v2'  # v1 (never run live) had no campaign limit
AUTOMATIC_RETRIES_PER_WAIT = 3
AUTOMATIC_RETRIES_PER_CAMPAIGN = 6
DELAYS_SECONDS = (30, 120, 300)
POLL_SECONDS = .5
RULE = ('While a Learn campaign waits for verified Weave evidence, FaultLab retries the evidence by itself at most 3 '
        'times per wait and at most 6 times per campaign: 30 s, 120 s and 300 s after the wait starts or after the '
        'previous retry still left the evidence unverified. Each automatic retry uses the same telemetry-only path as Retry evidence sync: it '
        're-sends the saved trace records of the episodes the wait needs and reads them back. It never runs an '
        'episode, a business tool or a model request again, and charges nothing to the campaign budget. Every attempt '
        'is recorded. When a limit is reached the campaign keeps waiting and shows "needs operator"; Retry evidence sync '
        'and Stop still work. A stop during the wait ends the campaign as STOPPED.')
OPEN_STATUSES = ('WAITING', 'AUTOMATIC_RETRY_SCHEDULED', 'AUTOMATIC_RETRY_RUNNING', 'READING_EVIDENCE',
                 'NEEDS_OPERATOR', 'MANUAL_RETRY_ONLY')
FINISHED_RETRY = ('COMPLETED', 'TIMED_OUT', 'PENDING', 'INTERRUPTED')
MAX_SAVED_READS = 20
clock = time.monotonic  # Tests may replace the clock; the schedule never uses wall time.


def declaration():
    """The rule as frozen into a reviewed Learn plan (run_plans.EvidenceRetryPlan)."""
    return {'protocol': EVIDENCE_RETRY_PROTOCOL, 'trigger': 'WAITING_EVIDENCE',
            'automatic_retries_per_wait': AUTOMATIC_RETRIES_PER_WAIT,
            'automatic_retries_per_campaign': AUTOMATIC_RETRIES_PER_CAMPAIGN, 'delays_seconds': list(DELAYS_SECONDS),
            'path': 'retry-evidence', 'telemetry_only': True, 'repeats_model_requests': False,
            'repeats_business_actions': False, 'charged_model_calls': 0, 'after_last_retry': 'NEEDS_OPERATOR',
            'rule': RULE}


def campaign_rule(store, campaign):
    """The automatic evidence retry rule this campaign's saved plan declares, or None (manual retry only)."""
    from app.lab.runner import campaign_run_plan  # Reads the saved campaign by id, as discovery does.
    plan = campaign_run_plan(store, campaign)
    return (plan or {}).get('evidence_retry')


class EvidenceWaitStopped(StopRequested):
    """A stop that arrived while a Learn campaign waited for verified Weave evidence."""
    def __init__(self, message, interruption):
        super().__init__(message)
        self.interruption = interruption


def _count(n, noun):
    return f'{n} {noun}' + ('' if n == 1 else 's')


def _clock_text(moment):
    return moment.strftime('%H:%M:%S') + ' UTC'


class EvidenceWait:
    """One wait of one Learn campaign for one blocked episode's verified evidence."""

    def __init__(self, coordinator, campaign_id, episode_id, pending_episode_ids, rule):
        self.coordinator, self.store, self.campaign_id = coordinator, coordinator.store, campaign_id
        self.rule = rule
        campaign = coordinator.get(campaign_id)
        self.state_before = campaign.state
        self.last_trigger = None
        self.prior_retry_ids = {r['request_id'] for r in self.store.list_records('evidence_retries')
                                if r.get('campaign_id') == campaign_id}
        self.record = {
            'wait_id': new_id('evidence-wait'), 'campaign_id': campaign_id, 'execution_epoch': campaign.execution_epoch,
            'protocol': rule['protocol'] if rule else None,
            'automatic_retries_max': rule['automatic_retries_per_wait'] if rule else 0,
            # None: no campaign limit declared (no rule, or a v1 rule).
            'automatic_retries_campaign_max': (rule or {}).get('automatic_retries_per_campaign'),
            'limit_reached': None,
            'delays_seconds': list(rule['delays_seconds']) if rule else [],
            'episode_id': episode_id, 'pending_episode_ids': list(dict.fromkeys(pending_episode_ids)),
            'state_before': self.state_before, 'started_at': utc_now().isoformat(), 'status': 'WAITING',
            'message': None, 'failed_reads': 0, 'last_read_result': None, 'read_results': [],
            'automatic_attempts': [], 'manual_retry_request_ids': [], 'next_automatic_retry_at': None,
            'ended_at': None, 'resolution': None}
        self.save()

    # ----------------------------------------------------------------- records
    @property
    def open(self):
        return self.record['ended_at'] is None

    def save(self):
        self.store.put_record('evidence_waits', self.record['wait_id'], self.record)

    def still_pending(self):
        """The wait's episodes whose evidence is not yet verified, blocked episode first."""
        return [episode_id for episode_id in self.record['pending_episode_ids']
                if (self.store.get_record('evidence', episode_id) or {}).get('source') != 'weave_verified']

    def attempts(self):
        return self.record['automatic_attempts']

    def campaign_attempts(self):
        """Automatic retries made (or attempted) in this campaign so far, this wait's included."""
        return len(self.attempts()) + sum(len(w.get('automatic_attempts') or []) for w in self.store.list_records('evidence_waits')
                                          if w.get('campaign_id') == self.campaign_id and w.get('wait_id') != self.record['wait_id'])

    def _limit_reached(self):
        """'PER_WAIT', 'PER_CAMPAIGN' or None: whether the declared rule allows another automatic retry."""
        if len(self.attempts()) >= self.rule['automatic_retries_per_wait']: return 'PER_WAIT'
        cap = self.rule.get('automatic_retries_per_campaign')
        if cap is not None and self.campaign_attempts() >= cap: return 'PER_CAMPAIGN'
        return None

    def _status(self, status, message):
        self.record.update(status=status, message=message); self.save()
        # A new reason bumps state_seq, so the dashboard re-reads the wait once per change (no extra polling).
        # transition() leaves a stopped campaign unchanged.
        self.coordinator.transition(self.campaign_id, 'WAITING_EVIDENCE', message)

    def _waiting_text(self):
        pending = len(self.still_pending()) or 1
        return (f'Waiting for verified Weave evidence ({_count(pending, "episode")}; last ingestion result: '
                f'{self.record["last_read_result"]}).')

    # ----------------------------------------------------------------- waiting
    async def hold(self, error_text, stop):
        """Wait (state WAITING_EVIDENCE) until any evidence retry finishes, or a stop.

        Starts the declared automatic retries when they fall due. Never raises for a failed retry:
        a failed attempt is recorded and the caller reads the evidence again.
        """
        if stop(): return
        result = (error_text or 'Evidence pending')[:120]
        self.record['failed_reads'] += 1; self.record['last_read_result'] = result
        self.record['read_results'] = (self.record['read_results'] + [{'at': utc_now().isoformat(), 'result': result}])[-MAX_SAVED_READS:]
        event = self.coordinator.evidence_events.setdefault(self.campaign_id, asyncio.Event())
        event.clear()
        made = len(self.attempts()); due = None
        if self.rule is None:
            self._status('MANUAL_RETRY_ONLY', self._waiting_text() + ' This campaign\'s plan declares no automatic '
                         'evidence retry. Press Retry evidence sync, or Stop.')
        elif self._limit_reached() is None:
            delay = self.rule['delays_seconds'][made]
            due = clock() + delay
            at = utc_now() + timedelta(seconds=delay)
            self.record['next_automatic_retry_at'] = at.isoformat()
            cap = self.rule.get('automatic_retries_per_campaign')
            campaign = f' (retry {self.campaign_attempts() + 1} of {cap} for this campaign)' if cap is not None else ''
            self._status('AUTOMATIC_RETRY_SCHEDULED', self._waiting_text() + f' Automatic telemetry retry {made + 1} of '
                         f'{self.rule["automatic_retries_per_wait"]}{campaign} at {_clock_text(at)}. No model request or '
                         'business action is repeated.')
        else:
            self._needs_operator()
        launched = None
        while not event.is_set() and not stop():
            timeout = POLL_SECONDS if due is None else max(0.0, min(POLL_SECONDS, due - clock()))
            try: await asyncio.wait_for(event.wait(), timeout=timeout)
            except TimeoutError: pass
            if due is not None and not event.is_set() and not stop() and clock() >= due:
                due = None
                launched = await self._launch(len(self.attempts()) + 1)
        if stop(): return
        if launched is not None:
            self._finish_attempt(launched)
            self.last_trigger = ('automatic', launched['attempt'])
            how = f'automatic telemetry retry {launched["attempt"]} of {self.rule["automatic_retries_per_wait"]}'
        else:
            # An operator's retry finished first; the next automatic retry is rescheduled if the re-read still fails.
            self.record['next_automatic_retry_at'] = None
            self._note_manual_retries()
            self.last_trigger = ('manual', None)
            how = 'an evidence retry'
        self._status('READING_EVIDENCE', f'Reading Weave evidence again after {how}.')

    async def _launch(self, attempt):
        """Start automatic retry ``attempt`` through the existing retry path; None if another retry is running."""
        now = utc_now().isoformat()
        entry = {'attempt': attempt, 'request_id': None, 'scheduled_for': self.record['next_automatic_retry_at'],
                 'started_at': now, 'ended_at': None, 'status': 'RUNNING', 'episode_ids': self.still_pending(),
                 'verified': None, 'still_pending': None}
        self.record['next_automatic_retry_at'] = None
        try:
            request = await self.coordinator.retry_evidence(self.campaign_id, entry['episode_ids'], automatic={
                'evidence_wait_id': self.record['wait_id'], 'attempt': attempt,
                'attempts_max': self.rule['automatic_retries_per_wait']})
        except StopRequested:
            # The Stop arrived while this retry waited for the coordinator lock: nothing started, nothing is counted.
            self.save()
            return None
        except Exception as error:
            # Recorded and counted, so the bound holds; the campaign keeps waiting.
            entry.update(status='NOT_STARTED', ended_at=utc_now().isoformat(), error_class=type(error).__name__)
            self.attempts().append(entry); self.save()
            self.coordinator.evidence_events.setdefault(self.campaign_id, asyncio.Event()).set()
            return entry
        if (request.get('automatic') or {}).get('evidence_wait_id') != self.record['wait_id']:
            # An operator's retry is already running: wait for it instead of starting a second job.
            self.record['manual_retry_request_ids'] = list(dict.fromkeys(self.record['manual_retry_request_ids'] + [request['request_id']]))
            self.save()
            return None
        entry['request_id'] = request['request_id']
        self.attempts().append(entry)
        self._status('AUTOMATIC_RETRY_RUNNING', self._waiting_text() + f' Automatic telemetry retry {attempt} of '
                     f'{self.rule["automatic_retries_per_wait"]} is running (telemetry only).')
        return entry

    def _finish_attempt(self, entry):
        if entry['request_id'] is None: return
        retry = self.store.get_record('evidence_retries', entry['request_id']) or {}
        outcomes = retry.get('outcomes') or {}
        entry.update(status=retry.get('status', 'UNKNOWN'), ended_at=utc_now().isoformat(),
                     verified=sum(o.get('status') == 'VERIFIED' for o in outcomes.values()),
                     still_pending=sum(o.get('status') == 'PENDING' for o in outcomes.values()))
        self.save()

    def _note_manual_retries(self):
        seen = [r['request_id'] for r in self.store.list_records('evidence_retries')
                if r.get('campaign_id') == self.campaign_id and r.get('trigger') != 'automatic'
                and r['request_id'] not in self.prior_retry_ids]
        self.record['manual_retry_request_ids'] = list(dict.fromkeys(self.record['manual_retry_request_ids'] + seen))
        self.save()

    def _needs_operator(self):
        total = self.rule['automatic_retries_per_wait']
        pending = len(self.still_pending()) or 1
        limit = self._limit_reached() or 'PER_WAIT'
        self.record['limit_reached'] = limit
        why = (f'after {total} automatic telemetry retries' if limit == 'PER_WAIT' else
               f'and this campaign has used all {self.rule["automatic_retries_per_campaign"]} of its automatic telemetry '
               f'retries ({len(self.attempts())} of {total} in this wait)')
        self._status('NEEDS_OPERATOR', f'Needs operator: Weave evidence for {_count(pending, "episode")} is still '
                     f'unverified {why} (last ingestion result: {self.record["last_read_result"]}). The campaign keeps '
                     'waiting. Press Retry evidence sync, or Stop.')

    # ----------------------------------------------------------------- endings
    def resolve(self):
        """The blocked episode's evidence is verified: close the wait and resume the previous state."""
        kind, attempt = self.last_trigger or ('read', None)
        how = (f'automatic telemetry retry {attempt} of {self.rule["automatic_retries_per_wait"]}' if kind == 'automatic'
               else 'a manual evidence retry' if kind == 'manual' else 'a new read')
        message = f'Weave evidence verified after {how}; resumed.'
        self.record.update(status='RESOLVED', resolution='VERIFIED', message=message, ended_at=utc_now().isoformat())
        self.save()
        self.coordinator.transition(self.campaign_id, self.state_before, message)

    def stopped(self):
        """Close the wait for a stop; return the exception that ends the campaign as STOPPED."""
        for entry in self.attempts():
            if entry['status'] == 'RUNNING':
                self._finish_attempt(entry)
                if entry['status'] in ('QUEUED', 'RUNNING'): entry['status'] = 'RUNNING_AT_STOP'
        pending = self.still_pending()
        made = len(self.attempts())
        detail = (f'{made} of {self.record["automatic_retries_max"]} automatic telemetry retries made'
                  if self.rule is not None else 'no automatic retry declared')
        if self.rule is not None and self.record['status'] == 'NEEDS_OPERATOR': detail += ', needs operator'
        if pending:
            message = (f'Stopped during an evidence wait: Stop was requested while {_count(len(pending), "episode")} '
                       f'waited for verified Weave evidence (last ingestion result: {self.record["last_read_result"]}; '
                       f'{detail}). Saved episodes, effects and evidence are kept; nothing is replayed.')
        else:
            # A retry verified everything, and the Stop landed before the campaign read the evidence again.
            message = (f'Stopped during an evidence wait: the evidence this wait needed was verified just before the Stop, '
                       f'but the campaign had not read it again yet ({detail}). Saved episodes, effects and evidence are '
                       'kept; nothing is replayed.')
        self.record.update(status='STOPPED', resolution='STOPPED', message=message, ended_at=utc_now().isoformat(),
                           next_automatic_retry_at=None)
        self.save()
        interruption = {'kind': 'STOPPED_DURING_EVIDENCE_WAIT', 'evidence_wait_id': self.record['wait_id'],
                        'waiting_for_episode_ids': pending, 'evidence_verified_before_stop': not pending,
                        'automatic_retries_made': made, 'stage_before_wait': self.state_before}
        return EvidenceWaitStopped(message, interruption)

    def end(self, error):
        """Close the wait when execution ends another way (an error or cancellation)."""
        cancelled = isinstance(error, asyncio.CancelledError)
        self.record.update(status='INTERRUPTED' if cancelled else 'ENDED', resolution='INTERRUPTED' if cancelled else 'ERROR',
                           error_class=type(error).__name__, ended_at=utc_now().isoformat(), next_automatic_retry_at=None,
                           message='Execution ended during the evidence wait; see the campaign result.')
        self.save()


STOPPED_WAIT_REASON = ('Stopped during evidence wait: a Stop request arrived while this qualification waited for '
                       'verified Weave evidence; saved attempts are not replayed')


def evidence_wait_status(store, campaign, *, active=None):
    """What the API and dashboard show: the declared rule, the current wait and this campaign's past waits."""
    ident = campaign.campaign_id
    try:
        rule = campaign_rule(store, campaign)
        rule_note = None
    except Exception:
        rule, rule_note = None, 'The saved plan could not be read, so no automatic retry applies.'
    waits = sorted((w for w in store.list_records('evidence_waits') if w.get('campaign_id') == ident),
                   key=lambda w: w['started_at'])
    current = next((w for w in reversed(waits) if w['ended_at'] is None and w['status'] in OPEN_STATUSES), None)
    if campaign.state == 'WAITING_EVIDENCE' and current is not None:
        status, message = current['status'], current['message']
    elif campaign.state == 'WAITING_EVIDENCE':
        status = 'NEEDS_OPERATOR'
        message = ('This campaign is waiting for evidence but has no recorded evidence wait (saved before automatic '
                   'evidence retries existed, or its execution already ended). Retry evidence sync re-sends telemetry '
                   'only; it does not restart execution.')
    else:
        status, message = 'NOT_WAITING', 'This campaign is not waiting for evidence.'
    if rule is None and not rule_note:
        rule_note = ('Not declared: this campaign\'s plan has no automatic evidence retry (saved before the rule '
                     'existed, not a Learn plan, or no reviewed plan). Only manual Retry evidence sync applies.')
    return {'schema_version': 'faultlab-evidence-wait/v1', 'campaign_id': ident, 'campaign_state': campaign.state,
            'declared': rule, 'declared_note': rule_note, 'status': status, 'needs_operator': status == 'NEEDS_OPERATOR',
            'message': message, 'current': current, 'waits': waits[-20:], 'waits_total': len(waits),
            'automatic_retries_total': sum(len(w['automatic_attempts']) for w in waits)}

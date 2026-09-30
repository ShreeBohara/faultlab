"""One bounded, charged blind retry of a model request that delivered no answer.

The reference Actor, the Explorer, the Mechanic and the native smolagents transport all
apply this one rule, so a single dropped connection no longer ends a whole campaign:

* At most ONE retry per request, re-sending the identical request.
* Only when no generation was received: a connection error, a timeout, or HTTP 503
  (after a one-second wait). Never after any received answer, even an empty or
  malformed one; never for another HTTP status (4xx, 500, 502, 504), authentication,
  configuration, input-limit or frozen-model-identity failures.
* The retry is charged (model calls, tokens and the role's dollar bound) on the
  campaign ledger BEFORE it is sent, from unreserved capacity only: a batch reservation
  never promises a retry. If the budget cannot cover it, or a stop was requested, the
  retry is refused and the ORIGINAL failure is raised unchanged.
* Every admitted retry is recorded: an ``actor_transport_retry`` episode event for the
  Actor and the native agent, a ``transport_retries`` record for the Explorer and the
  Mechanic (also noted on the saved selection or Mechanic output).
* A second failure of the same request ends the work exactly as before.

A retry never spends an actor turn or a declared discovery request, so it never changes
what a model is shown on a later turn.

Rule v2 (``faultlab-transport-retry/v2-lab-backoff``, frozen into every new Learn plan):
the agent roles (reference Actor, native smolagents adapters v1 and v2) keep exactly the
rule above. FaultLab's own lab roles in that Learn campaign -- the Explorer (discovery and
challenge selections) and the Mechanic (diagnosis and candidate requests) -- may re-send
the identical request up to THREE times, waiting 5 s, 20 s and 60 s before the first,
second and third retry, under the same conditions (no answer arrived: connection error,
timeout, HTTP 503). A campaign-wide cap of 12 such retries bounds a long outage; during
discovery the plan's declared Explorer retry bound also applies. Each retry is admitted and
charged on the ledger before it is sent, exactly like a v1 retry, and recorded (attempt
number and wait). A wait is cancellable: a Stop during it ends the campaign STOPPED with a
plain reason, and nothing more is sent. If every allowed retry fails, the original failure
ends the campaign as before, and the error message says how many retries were tried.
Plans saved before v2, separate studies started on a campaign (selection comparison,
completion study) and baseline/compare plans keep rule v1.
"""
import asyncio

from app.lab.budgets import BudgetExhausted, CampaignLedger, StopRequested
from app.providers.runtime import RuntimeProviderError

TRANSPORT_RETRY_PROTOCOL = 'faultlab-transport-retry/v1'
RETRYABLE_TRANSPORT_CODES = ('CONNECTION_ERROR', 'REQUEST_TIMEOUT')
RETRIES_PER_REQUEST = 1
SERVICE_UNAVAILABLE_DELAY_SECONDS = 1
RULE = ('At most one blind retry of the identical request, only when no answer arrived: a connection error, '
        'a timeout, or HTTP 503 after a one-second wait. Never after any answer, even an empty or malformed one, '
        'and never for other HTTP statuses, authentication, configuration or model-identity failures. The retry '
        'is charged in model calls, tokens and dollars before it is sent, from unreserved campaign capacity only; '
        'if the budget cannot cover it the original failure stands. It never uses an actor turn or a discovery '
        'request. A second failure ends the work as before.')


def service_unavailable(error):
    return error.code == 'HTTP_ERROR' and error.http_status == 503


def blind_retry_allowed(error):
    """True only for a failure that delivered no generation and is a transport loss or HTTP 503."""
    return (isinstance(error, RuntimeProviderError) and error.generation is None
            and (error.code in RETRYABLE_TRANSPORT_CODES or service_unavailable(error)))


def retry_payload(error, attempt=1):
    """The recorded facts of one admitted retry (no message, header or response text)."""
    payload = {'code': error.code, 'attempt': attempt}
    if service_unavailable(error):
        payload.update(http_status=503, retry_delay_seconds=SERVICE_UNAVAILABLE_DELAY_SECONDS)
    return payload


def request_usage(generation, retries):
    """The saved usage of one answered request, counting its admitted retries.

    One convention for every role: a request that lost an attempt has an UNKNOWN cost
    (``cost_dollars: None``), because the lost attempt returned no usage; the native
    bridge and the reference Actor mark the episode's cost unknown the same way. Tokens
    are the answered attempt's only (the lost attempt reported none). The campaign
    ledger has already charged every attempt its full model-call, token and dollar bound.
    """
    return {'model_calls': 1 + len(retries), 'input_tokens': generation.input_tokens,
            'output_tokens': generation.output_tokens,
            'cost_dollars': None if retries else generation.cost_usd}


def declaration(actor_calls):
    """The rule as frozen into a reviewed campaign plan."""
    return {'protocol': TRANSPORT_RETRY_PROTOCOL, 'retries_per_request': RETRIES_PER_REQUEST,
            'roles': ['actor', 'explorer', 'mechanic'],
            'retryable': ['CONNECTION_ERROR', 'REQUEST_TIMEOUT', 'HTTP_503'],
            'service_unavailable_delay_seconds': SERVICE_UNAVAILABLE_DELAY_SECONDS,
            'actor_retries_per_episode_max': actor_calls * RETRIES_PER_REQUEST,
            'rule': RULE}


def ledger_retry_fits(ledger, role):
    """Whether charge_ledger_retry(ledger, role) would be admitted now, WITHOUT charging anything.

    A read-only restatement of CampaignLedger.consume_call's checks for an unreserved call (reservation=None).
    budgets.py is part of the frozen interpreter hash, so it is mirrored here rather than changed; a test compares
    this function with consume_call over many ledger states. Rule v2 asks it BEFORE a backoff wait, so a retry the
    budget cannot cover is refused at once instead of after a pointless wait; the real charge after the wait stays
    the only admission. Anything that is not a CampaignLedger (a test double) answers True: admission then decides.
    """
    if not isinstance(ledger, CampaignLedger):
        return True
    with ledger.store.lock:
        if ledger.stopped or role not in ('actor', 'explorer', 'mechanic'):
            return False
        protected_calls, protected_tokens = ledger.reserved_calls, ledger.reserved_tokens
        role_bound = ledger.dollar_bounds.get(role) if ledger.dollar_bounds else None
        if (role_bound is not None
                and ledger.used_dollar_upper_bound + role_bound + protected_calls * ledger.dollar_bound > ledger.caps.dollars):
            return False
        if (ledger.used_calls + 1 + protected_calls > ledger.caps.model_calls
                or ledger.used_tokens + ledger.tokens_per_call + protected_tokens > ledger.caps.tokens):
            return False
        if ledger.used_cost is not None and ledger.used_cost >= ledger.caps.dollars:
            return False
        return True


def charge_ledger_retry(ledger, role):
    """Charge one retry on the campaign ledger from unreserved capacity; False if refused.

    Refusal returns False instead of raising, so that a retry can never replace the
    transport failure that caused it with a budget or stop error.
    """
    try:
        ledger.consume_call(role=role)
    except (BudgetExhausted, StopRequested):
        return False
    return True


async def complete_with_one_retry(send, *, failed, admit, record):
    """Run one charged request with at most one blind retry.

    ``send(retry)`` performs the request (its first attempt is already charged by the
    caller); ``failed(error)`` records each failure and returns its failure id;
    ``admit()`` charges the retry and returns False when it cannot be admitted;
    ``record(error, failure_id)`` records an admitted retry and returns its facts.
    Returns (generation, retries).
    """
    retries = []
    for attempt in range(1 + RETRIES_PER_REQUEST):
        try:
            return await send(attempt > 0), retries
        except RuntimeProviderError as error:
            failure_id = failed(error)
            if attempt < RETRIES_PER_REQUEST and blind_retry_allowed(error):
                if service_unavailable(error):
                    # Cancellable; admission below then sees any stop requested meanwhile.
                    await asyncio.sleep(SERVICE_UNAVAILABLE_DELAY_SECONDS)
                if admit():
                    retries.append(record(error, failure_id))
                    continue
            raise


# ----------------------------------------------------------------------------- rule v2: lab roles back off

TRANSPORT_RETRY_PROTOCOL_V2 = 'faultlab-transport-retry/v2-lab-backoff'
LAB_ROLES = ('explorer', 'mechanic')
LAB_RETRIES_PER_REQUEST = 3
LAB_BACKOFF_SECONDS = (5, 20, 60)
LAB_RETRIES_PER_CAMPAIGN_MAX = 12
# A wait checks for a Stop at least this often, so a Stop ends it within about half a second.
WAIT_POLL_SECONDS = 0.5
RULE_V2 = ('Agent roles (the reference Actor and the native smolagents adapters) keep rule v1: at most one blind '
           'retry of the identical request, only when no answer arrived (a connection error, a timeout, or HTTP 503 '
           'after a one-second wait). FaultLab\'s own lab roles in this Learn campaign (Explorer discovery and challenge '
           'selections, Mechanic diagnosis and candidate requests) may re-send the identical request up to 3 times, '
           'after waits of 5 s, 20 s and 60 s, only when no answer arrived (connection error, timeout, HTTP 503), and '
           'at most 12 times in the whole campaign; during discovery the declared Explorer retry bound also applies. '
           'An answer, even an empty or malformed one, is never retried, and neither is any other HTTP status or an '
           'authentication, configuration or model-identity failure. Every retry is charged in model calls, tokens and '
           'dollars before it is sent, from unreserved campaign capacity only. A Stop during a wait ends the campaign '
           'STOPPED and nothing more is sent. If every allowed retry fails, the campaign ends ERROR as before and says '
           'how many retries were tried. Separate studies started on the campaign keep rule v1.')

# Why a lab-role request stopped being retried (saved with the failure; see retry_failure_message).
RETRY_END_REASONS = ('ALL_RETRIES_FAILED', 'CAMPAIGN_RETRY_LIMIT', 'DISCOVERY_RETRY_LIMIT', 'BUDGET_REFUSED', 'NOT_RETRYABLE')


def declaration_v2(actor_calls):
    """Rule v2 as frozen into a reviewed Learn plan (run_plans.TransportRetryPlanV2)."""
    return {'protocol': TRANSPORT_RETRY_PROTOCOL_V2,
            'retryable': ['CONNECTION_ERROR', 'REQUEST_TIMEOUT', 'HTTP_503'],
            # Agent roles: exactly rule v1.
            'agent_roles': ['actor'], 'agent_retries_per_request': RETRIES_PER_REQUEST,
            'service_unavailable_delay_seconds': SERVICE_UNAVAILABLE_DELAY_SECONDS,
            'actor_retries_per_episode_max': actor_calls * RETRIES_PER_REQUEST,
            # Lab roles of this Learn campaign.
            'lab_roles': list(LAB_ROLES), 'lab_retries_per_request': LAB_RETRIES_PER_REQUEST,
            'lab_backoff_seconds': list(LAB_BACKOFF_SECONDS),
            'lab_retries_per_campaign_max': LAB_RETRIES_PER_CAMPAIGN_MAX,
            'stop_during_wait': 'STOPPED',
            'rule': RULE_V2}


def backoff_payload(error, attempt, delay):
    """The recorded facts of one admitted rule-v2 retry (no message, header or response text)."""
    payload = {'protocol': TRANSPORT_RETRY_PROTOCOL_V2, 'code': error.code, 'attempt': attempt,
               'retry_delay_seconds': delay}
    if service_unavailable(error):
        payload['http_status'] = 503
    return payload


def _plural(count, one, many):
    return f'{count} {one if count == 1 else many}'


def retry_failure_message(summary):
    """Plain text for a lab-role request that still failed under rule v2 (fixed FaultLab text only)."""
    tried, reason = summary['retries_tried'], summary['reason']
    waits = summary.get('waits_seconds') or []
    detail = {
        'ALL_RETRIES_FAILED': 'every allowed retry of this request failed',
        'CAMPAIGN_RETRY_LIMIT': (f'the campaign\'s limit of {LAB_RETRIES_PER_CAMPAIGN_MAX} lab-role transport '
                                 'retries was reached'),
        'DISCOVERY_RETRY_LIMIT': 'the plan\'s declared discovery Explorer retry bound was reached',
        'BUDGET_REFUSED': 'the next retry did not fit the campaign\'s unreserved budget, so it was not sent',
        'NOT_RETRYABLE': 'the last failure is of a kind that is never retried',
    }[reason]
    if not tried:
        # Review finding P-4 (September 30): say plainly that no retry was sent, not "after 0 transport retries".
        if reason == 'BUDGET_REFUSED':
            detail = 'a retry did not fit the campaign\'s unreserved budget'
        return f'A model request failed and no transport retry was sent: {detail}. Inspect the saved provider diagnostics.'
    head = f'A model request failed after {_plural(tried, "transport retry", "transport retries")}'
    if waits:
        head += ' (waits of ' + ', '.join(f'{seconds} s' for seconds in waits) + ')'
    return f'{head}; {detail}. Inspect the saved provider diagnostics.'


class TransportRetryStopped(StopRequested):
    """A Stop that arrived while a lab-role request waited to be re-sent (rule v2)."""


async def cancellable_wait(seconds, stopped, *, poll=None):
    """Wait ``seconds``, checking ``stopped()`` before each step of at most ``poll`` seconds
    (default WAIT_POLL_SECONDS, read at call time).

    Returns False when the whole wait passed, True as soon as a Stop is seen. It counts the
    time it slept rather than reading a clock, so a test that replaces asyncio.sleep sees the
    exact steps. Cancellation of the task still propagates at once.
    """
    poll = WAIT_POLL_SECONDS if poll is None else poll
    remaining = float(seconds)
    while True:
        if stopped():
            return True
        if remaining <= 0:
            return False
        step = min(poll, remaining)
        await asyncio.sleep(step)
        remaining -= step


class LabBackoff:
    """One Learn campaign's lab-role transport retries under rule v2.

    Counts come from the store's transport_retries records of this campaign (rule v2 only), so
    the campaign cap holds across every Explorer and Mechanic of the campaign. ``stopped`` is the
    campaign's Stop check; ``discovery_retries_max`` is the plan's declared discovery Explorer bound.
    """
    protocol = TRANSPORT_RETRY_PROTOCOL_V2

    def __init__(self, store, campaign_id, *, stopped, discovery_retries_max=None):
        self.store, self.campaign_id, self.stopped = store, campaign_id, stopped
        prior = [row for row in store.list_records('transport_retries')
                 if row.get('campaign_id') == campaign_id and row.get('protocol') == TRANSPORT_RETRY_PROTOCOL_V2]
        self.used = len(prior)
        self.discovery_used = sum(1 for row in prior if (row.get('request') or {}).get('phase') == 'discovery')
        self.discovery_retries_max = discovery_retries_max
        self.waits = []   # (role, attempt, seconds) of every completed wait, in order

    def refusal(self, *, discovery):
        """Why no further retry may be admitted now, or None."""
        if self.used >= LAB_RETRIES_PER_CAMPAIGN_MAX:
            return 'CAMPAIGN_RETRY_LIMIT'
        if discovery and self.discovery_used >= (self.discovery_retries_max or 0):
            return 'DISCOVERY_RETRY_LIMIT'
        return None

    def admitted(self, *, discovery):
        self.used += 1
        if discovery:
            self.discovery_used += 1

    async def wait(self, seconds, *, role, attempt):
        if await cancellable_wait(seconds, self.stopped):
            raise self.stop_error(role)
        self.waits.append((role, attempt, seconds))

    def stop_error(self, role):
        return TransportRetryStopped(f'External stop requested while a failed {role.capitalize()} model request waited to '
                                     'be re-sent (transport retry backoff); it was not sent again. Remote effects are retained.')


async def complete_with_backoff(send, *, failed, admit, record, session, role, discovery=False, fits=None):
    """Run one charged lab-role request with at most three backed-off blind retries (rule v2).

    ``send(retry)`` performs the request (its first attempt is already charged by the caller);
    ``failed(error)`` records each failure and returns its failure id; ``admit()`` charges one
    retry on the ledger and returns False when it cannot be admitted; ``record(error, failure_id,
    attempt, delay)`` records an admitted retry and returns its facts. ``fits()`` (optional) says,
    without charging, whether the budget could still admit a retry: it is asked before each wait, so
    a retry the budget cannot cover is refused at once (BUDGET_REFUSED) instead of after its wait
    (review findings LOW-2 / P-4, September 30); ``admit()`` after the wait remains the only charge.
    Returns (generation, retries). A Stop seen during a wait or at admission raises
    TransportRetryStopped; a request that is not retried again raises its failure with
    ``transport_retry_summary`` set.
    """
    retries = []
    while True:
        try:
            return await send(bool(retries)), retries
        except RuntimeProviderError as error:
            failure_id = failed(error)
            attempt = len(retries) + 1
            if not blind_retry_allowed(error):
                reason = 'NOT_RETRYABLE'
            elif attempt > LAB_RETRIES_PER_REQUEST:
                reason = 'ALL_RETRIES_FAILED'
            else:
                reason = session.refusal(discovery=discovery)
            if reason is None and fits is not None and not session.stopped() and not fits():
                reason = 'BUDGET_REFUSED'                                   # refused before waiting; nothing charged
            if reason is None:
                delay = LAB_BACKOFF_SECONDS[attempt - 1]
                await session.wait(delay, role=role, attempt=attempt)     # a Stop raises here
                if session.stopped():
                    raise session.stop_error(role) from None
                reason = session.refusal(discovery=discovery)
                if reason is None and not admit():
                    if session.stopped():
                        raise session.stop_error(role) from None
                    reason = 'BUDGET_REFUSED'
                if reason is None:
                    session.admitted(discovery=discovery)
                    retries.append(record(error, failure_id, attempt, delay))
                    continue
            if retries or reason != 'NOT_RETRYABLE':
                error.transport_retry_summary = {
                    'protocol': TRANSPORT_RETRY_PROTOCOL_V2, 'role': role, 'retries_tried': len(retries),
                    'waits_seconds': [LAB_BACKOFF_SECONDS[index] for index in range(len(retries))], 'reason': reason}
            raise


def lab_backoff_for_campaign(store, campaign, *, stopped):
    """The rule-v2 session a Learn campaign's plan declares, or None (rule v1: one blind retry)."""
    from app.lab.runner import campaign_run_plan
    plan = campaign_run_plan(store, campaign)
    if ((plan or {}).get('transport_retry') or {}).get('protocol') != TRANSPORT_RETRY_PROTOCOL_V2:
        return None
    return LabBackoff(store, campaign.campaign_id, stopped=stopped,
                      discovery_retries_max=(plan.get('discovery') or {}).get('explorer_transport_retries_max'))

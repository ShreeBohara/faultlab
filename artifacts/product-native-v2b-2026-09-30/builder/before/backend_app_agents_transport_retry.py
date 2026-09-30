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
"""
import asyncio

from app.lab.budgets import BudgetExhausted, StopRequested
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

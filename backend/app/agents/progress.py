"""Actor-facing attempted-write progress, derived only from already-public facts.

Every value below restates something this Actor has already caused or already
been shown inside this episode: a write request dispatched on its behalf, or an
observation the adapter delivered to it. Nothing here reads the private world
snapshot, the fault recipe, the referee verdict, a protected manifest or a
future outcome, so this summary adds no knowledge - it only collects scattered
public facts the model already received.

Three protocols exist so one frozen source can run both arms of a comparison:

``faultlab-actor-context/v1``
    The preserved Phase 3 turn context. The per-turn user message carries
    exactly ``observations``, ``final_report_required`` and
    ``remaining_actor_calls``, byte for byte as before.

``faultlab-actor-context/v2-attempted-writes``
    The same message plus one ``attempted_writes`` object built here, on every
    turn including the reserved final report turn.

``faultlab-actor-context/v3-attempted-writes-action-turns``
    The same block, but omitted whenever a final report is required. The first
    live comparison showed the block helping action selection and hurting report
    wording: with v2 the model reported ``NOT_STARTED`` where the contract
    requires ``NOT_REQUIRED``. v3 separates those two sub-tasks.

The named distinctions are descriptions, not instructions, and nothing scores
them. In particular a dispatched write whose response never arrived is *not*
evidence that the write failed, and a service answer of UNKNOWN is not evidence
that an operation is pending.
"""
from app.contracts.models import OperationData, canonical_json, content_hash
from app.lab.policy_state import PolicyState

ACTOR_CONTEXT_PROTOCOL_V1 = 'faultlab-actor-context/v1'
ACTOR_CONTEXT_PROTOCOL_V2 = 'faultlab-actor-context/v2-attempted-writes'
ACTOR_CONTEXT_PROTOCOL_V3 = 'faultlab-actor-context/v3-attempted-writes-action-turns'
# v4 changes only how a delivered observation is NAMED to the Actor. Every observation and
# every other field is retained; the 32-hex evidence_id is replaced by its 1-based position
# in the episode's append-only journal, so the Actor has no opaque identifier to transcribe.
# It is built on v1, not v2/v3, so this stays a single variable.
ACTOR_CONTEXT_PROTOCOL_V4 = 'faultlab-actor-context/v4-indexed-evidence'
EVIDENCE_LABEL_PREFIX = 'obs-'
ACTOR_CONTEXT_PROTOCOLS = (ACTOR_CONTEXT_PROTOCOL_V1, ACTOR_CONTEXT_PROTOCOL_V2,
                           ACTOR_CONTEXT_PROTOCOL_V3, ACTOR_CONTEXT_PROTOCOL_V4)
EXTENDED_PROTOCOLS = (ACTOR_CONTEXT_PROTOCOL_V2, ACTOR_CONTEXT_PROTOCOL_V3)
INDEXED_EVIDENCE_PROTOCOLS = (ACTOR_CONTEXT_PROTOCOL_V4,)
ATTEMPTED_WRITES_FORMAT = 'faultlab-attempted-writes/v1'

OPERATION_FIELDS = (
    'service', 'operation_id', 'write_requests_dispatched', 'write_transport_attempts',
    'last_write_response', 'write_rejected_before_acceptance', 'service_acknowledged_operation',
    'status_responses_received', 'last_observed_status', 'last_status_evidence_id',
    'matching_terminal_receipt',
)

# Codes the mock service documents as refusing a request *instead of* recording
# an operation for it. Each is raised before any operation record, effect or
# receipt can exist for *that request*. A delivered response carrying one is
# therefore evidence that the attempt it answered did not take effect - but only
# the conjunction over every attempt of the operation licenses a claim about the
# operation, which is why the flag below quantifies over all of them.
# Of these, only TRANSIENT_UNAVAILABLE has ever actually reached an Actor; the
# rest are listed because the service can raise them, not because they are
# reachable through the coordinator today.
# Deliberately excluded:
#   HTTP_TIMEOUT, TRANSPORT_ERROR - no service response was delivered at all, so
#       the request may still have committed.
#   INVALID_SERVICE_RESPONSE - the response was rejected by the adapter and its
#       meaning is unknown.
#   DIAGNOSTIC_INCIDENT - the diagnostic profile may commit a witness write and
#       then answer 503, so it proves nothing about acceptance.
#   IDENTITY_CONFLICT, IDEMPOTENCY_CONFLICT - both can mean the operation
#       already exists, which is the opposite of non-acceptance.
PRE_ACCEPTANCE_ERROR_CODES = (
    'BUSINESS_BUDGET',
    'DIAGNOSTIC_PATH_UNAVAILABLE',
    'INVALID_TRANSPORT_ID',
    'STALE_HISTORY_UNAVAILABLE',
    'TRANSIENT_UNAVAILABLE',
    'VERSION_CONFLICT',
    'WORLD_STOPPED',
)

WRITE_TOOLS = {'orders': 'update_order', 'notifications': 'send_confirmation'}

NOTE = ('Derived only from the write requests dispatched for you in this episode and from the '
        'observations already delivered above. Not a service statement and not proof of effect: '
        'a dispatched request whose response never arrived may still have committed.')


def _binding(intent, service):
    operation = intent.upgrade_operation_id if service == 'orders' else intent.notification_operation_id
    intent_hash = intent.upgrade_intent_hash if service == 'orders' else intent.notification_intent_hash
    return operation, intent_hash


def _matching_operation_data(observation, intent, service):
    """The same delivered-evidence binding the referee and policy engine use."""
    data = observation.result.data
    operation, intent_hash = _binding(intent, service)
    return (isinstance(data, OperationData) and observation.result.transport == 'ok'
            and (data.service, data.operation_id, data.order_id, data.intent_hash)
                == (service, operation, intent.order_id, intent_hash)
            and observation.result.operation_id == operation
            and observation.result.status == data.status)


def operation_progress(journal, service, logical_calls=()):
    """One operation's public progress; never claims more than an observation shows."""
    intent = journal.intent
    operation, _ = _binding(intent, service)
    record = journal.original(service)
    receipt = PolicyState(journal).receipt(service)

    write_tool = WRITE_TOOLS[service]
    write_observations = [o for o in journal.observations if o.result.tool == write_tool]
    matching = [o for o in journal.observations if _matching_operation_data(o, intent, service)]
    status_answers = [o for o in matching if o.result.tool == 'get_operation_status']
    acknowledged = [o for o in matching if o.result.data.status != 'UNKNOWN']

    last_write = write_observations[-1] if write_observations else None
    last_write_response = None if last_write is None else {
        'evidence_id': last_write.evidence_id,
        'transport': last_write.result.transport,
        'error_code': last_write.result.error_code,
        'status': last_write.result.status,
    }
    # Every attempt must have been refused, not just the most recent one. An
    # earlier attempt whose reply never arrived may have committed, and a later
    # attempt can be refused before acceptance without the service ever saying
    # so - two faults on one tool produce exactly that sequence. Claiming
    # rejection from the last response alone would tell the Actor a committed
    # write did not happen.
    rejected_before_acceptance = bool(
        write_observations and not acknowledged
        and all(o.result.transport == 'error'
                and o.result.error_code in PRE_ACCEPTANCE_ERROR_CODES
                for o in write_observations))

    last_status = matching[-1] if matching else None
    receipt_evidence = None
    if receipt is not None:
        for observation in matching:
            candidate = observation.result.data.receipt
            if candidate is not None and candidate.receipt_id == receipt.receipt_id:
                receipt_evidence = observation.evidence_id
    return {
        'service': service,
        'operation_id': operation,
        'write_requests_dispatched': len([call for call in logical_calls
                                          if call.get('tool') == write_tool]),
        'write_transport_attempts': len(record.attempt_ids) if record else 0,
        'last_write_response': last_write_response,
        'write_rejected_before_acceptance': rejected_before_acceptance,
        'service_acknowledged_operation': bool(acknowledged),
        'status_responses_received': len(status_answers),
        'last_observed_status': last_status.result.data.status if last_status else None,
        'last_status_evidence_id': last_status.evidence_id if last_status else None,
        'matching_terminal_receipt': None if receipt is None else {
            'receipt_id': receipt.receipt_id,
            'status': receipt.status,
            'evidence_id': receipt_evidence,
        },
    }


def attempted_writes(journal, logical_calls=()):
    """Public progress for both authorized operations, in a fixed order."""
    return {
        'format': ATTEMPTED_WRITES_FORMAT,
        'note': NOTE,
        'operations': [operation_progress(journal, service, logical_calls)
                       for service in ('orders', 'notifications')],
    }


def actor_context_protocol(version=ACTOR_CONTEXT_PROTOCOL_V1):
    """Declare the per-turn context shape so saved results stay attributable."""
    if version not in ACTOR_CONTEXT_PROTOCOLS:
        raise ValueError('Unknown actor context protocol')
    extended = version in EXTENDED_PROTOCOLS
    indexed = version in INDEXED_EVIDENCE_PROTOCOLS
    descriptor = {
        'version': version,
        'scope': 'faultlab_reference_actor',
        'turn_message_fields': sorted(['observations', 'final_report_required',
                                       'remaining_actor_calls']
                                      + (['attempted_writes'] if extended else [])),
        'attempted_writes_turns': ('every turn' if version == ACTOR_CONTEXT_PROTOCOL_V2
                                   else 'action turns only, omitted when a final report is required'
                                   if version == ACTOR_CONTEXT_PROTOCOL_V3 else None),
        'attempted_writes_format': ATTEMPTED_WRITES_FORMAT if extended else None,
        'attempted_writes_fields': sorted(OPERATION_FIELDS) if extended else None,
        'attempted_writes_note': NOTE if extended else None,
        'pre_acceptance_error_codes': list(PRE_ACCEPTANCE_ERROR_CODES) if extended else None,
        'evidence_sources': 'dispatched write journal and delivered public observations only',
        # v4 keys. None for v1-v3, so their frozen descriptor hashes are unchanged.
        'evidence_naming': ('1-based journal position of each delivered observation'
                            if indexed else None),
        'evidence_label_prefix': EVIDENCE_LABEL_PREFIX if indexed else None,
        'citation_decode': ('exact-match label lookup over observations already delivered '
                            'in this episode; unmatched tokens pass through verbatim and '
                            'are scored as written' if indexed else None),
    }
    # Only the keys that apply to this protocol are declared, so adding a later
    # protocol cannot change an earlier one's frozen identity. Phase 4 learned
    # this the hard way: its two studies recorded different descriptor hashes
    # for the same unchanged v1 control.
    descriptor = {key: value for key, value in descriptor.items() if value is not None}
    return {**descriptor, 'descriptor_hash': content_hash(descriptor)}


def actor_context_protocols():
    """Every available protocol, recorded once in the frozen configuration."""
    return {version: actor_context_protocol(version) for version in ACTOR_CONTEXT_PROTOCOLS}


def evidence_labels(observations):
    """Map each delivered observation's evidence_id to its 1-based journal position.

    The journal only ever appends, so a label denotes the same observation on every turn
    of the episode. Labels live only in the Actor's view; the store key is untouched.
    """
    return {row['evidence_id']: f'{EVIDENCE_LABEL_PREFIX}{index}'
            for index, row in enumerate(observations, 1) if 'evidence_id' in row}


def labelled_observations(observations):
    """Every observation, every field, with evidence_id replaced by its label."""
    labels = evidence_labels(observations)
    return [{**row, 'evidence_id': labels.get(row.get('evidence_id'), row.get('evidence_id'))}
            if 'evidence_id' in row else row for row in observations]


def decode_citations(cited, observations):
    """Decode labels back to real evidence_ids. A decoder, never a repair.

    Total: every token yields exactly one token, in order, nothing dropped, added, merged
    or deduplicated. Exact match only: no case folding, no trimming, no nearest-label.
    A token that is not a label of an observation already delivered in this episode passes
    through verbatim, so it still fails C6 exactly as it does today.
    """
    reverse = {label: evidence_id
               for evidence_id, label in evidence_labels(observations).items()}
    return [reverse.get(token, token) for token in cited]


def turn_message(observations, *, final_report_required, remaining_actor_calls,
                 protocol=ACTOR_CONTEXT_PROTOCOL_V1, journal=None, logical_calls=()):
    """Build one per-turn user payload.

    v1 returns exactly the preserved Phase 3 fields, so `canonical_json` of this
    payload stays byte-identical to the original implementation's message.
    """
    if protocol not in ACTOR_CONTEXT_PROTOCOLS:
        raise ValueError('Unknown actor context protocol')
    if protocol in INDEXED_EVIDENCE_PROTOCOLS:
        observations = labelled_observations(observations)
    payload = {'observations': observations, 'final_report_required': final_report_required,
               'remaining_actor_calls': remaining_actor_calls}
    # v3 withholds the block on report-required turns so the added facts inform
    # the action choice without steering the report's fixed vocabulary.
    if protocol in EXTENDED_PROTOCOLS and not (protocol == ACTOR_CONTEXT_PROTOCOL_V3
                                               and final_report_required):
        if journal is None:
            raise ValueError('Attempted-write context requires the episode journal')
        payload['attempted_writes'] = attempted_writes(journal, logical_calls)
    return payload


def turn_message_json(*args, **kwargs):
    return canonical_json(turn_message(*args, **kwargs))

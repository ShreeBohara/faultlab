"""Attempted-write context restates public facts without inventing progress.

These are engineering checks on the Actor's input, not scientific evidence and
not a claim that any repair works. Every assertion below compares the built
context against delivered observations and the episode's own write journal.
"""
import json
from types import SimpleNamespace

import pytest

from app.adapters.journal import Journal, allocate_intent
from app.agents.actor import Actor
from app.agents.progress import (ACTOR_CONTEXT_PROTOCOL_V1, ACTOR_CONTEXT_PROTOCOL_V2,
                                 ACTOR_CONTEXT_PROTOCOL_V3, ACTOR_CONTEXT_PROTOCOL_V4, decode_citations,
                                 PRE_ACCEPTANCE_ERROR_CODES, actor_context_protocol,
                                 actor_context_protocols, attempted_writes, turn_message)
from app.contracts.models import (OperationData, Receipt, RecoveryPolicy, ToolResult,
                                  canonical_json, content_hash)
from app.lab.budgets import EpisodeMeter
from app.lab.policy_interpreter import PolicyInterpreter
from app.lab.policy_state import PolicyState
from app.lab.storage import LabStore
from app.providers.runtime import RuntimeGeneration, validate_request_input


@pytest.fixture
def anyio_backend(): return 'asyncio'


def journal_for(tmp_path, name='episode-progress'):
    store = LabStore(tmp_path / 'progress.db')
    store.put_record('episodes', name, {'campaign_id': 'campaign-progress'})
    return store, Journal(store, name, allocate_intent('order-progress', 'Upgrade and confirm'))


def binding(intent, service):
    return ((intent.upgrade_operation_id, intent.upgrade_intent_hash) if service == 'orders'
            else (intent.notification_operation_id, intent.notification_intent_hash))


def deliver_status(journal, service, status, receipt=None, *, transport='ok'):
    intent = journal.intent
    operation, intent_hash = binding(intent, service)
    tick = len(journal.observations) + 1
    data = OperationData(service=service, operation_id=operation, order_id=intent.order_id,
                         intent_hash=intent_hash, status=status, receipt=receipt)
    return journal.deliver(ToolResult(
        call_id='call-' + str(tick), tool='get_operation_status', transport=transport,
        operation_id=operation, order_id=intent.order_id, status=status,
        receipt_id=receipt.receipt_id if receipt else None, data=data), tick)


def deliver_write(journal, service, *, transport, error_code=None, status=None, receipt=None):
    intent = journal.intent
    operation, intent_hash = binding(intent, service)
    tool = 'update_order' if service == 'orders' else 'send_confirmation'
    tick = len(journal.observations) + 1
    data = None
    if transport == 'ok':
        data = OperationData(service=service, operation_id=operation, order_id=intent.order_id,
                             intent_hash=intent_hash, status=status, receipt=receipt)
    return journal.deliver(ToolResult(
        call_id='call-' + str(tick), tool=tool, transport=transport, operation_id=operation,
        order_id=intent.order_id, status=status if transport == 'ok' else None,
        receipt_id=receipt.receipt_id if receipt else None, error_code=error_code, data=data), tick)


def notifications(summary):
    return next(row for row in summary['operations'] if row['service'] == 'notifications')


def orders(summary):
    return next(row for row in summary['operations'] if row['service'] == 'orders')


def test_never_attempted_is_a_journal_fact_and_status_polling_does_not_change_it(tmp_path):
    store, journal = journal_for(tmp_path)
    empty = notifications(attempted_writes(journal))
    assert empty['write_transport_attempts'] == 0 and empty['write_requests_dispatched'] == 0
    assert empty['last_write_response'] is None and empty['last_observed_status'] is None
    assert not empty['service_acknowledged_operation'] and not empty['write_rejected_before_acceptance']
    assert empty['matching_terminal_receipt'] is None and empty['status_responses_received'] == 0
    # The exact Phase 3 B2 behaviour: five UNKNOWN reads of an operation that was
    # never submitted. Reading status must never look like having written.
    for _ in range(5):
        deliver_status(journal, 'notifications', 'UNKNOWN')
    polled = notifications(attempted_writes(journal))
    assert polled['write_transport_attempts'] == 0 and polled['write_requests_dispatched'] == 0
    assert polled['status_responses_received'] == 5 and polled['last_observed_status'] == 'UNKNOWN'
    assert not polled['service_acknowledged_operation'] and polled['last_write_response'] is None
    assert not polled['write_rejected_before_acceptance']


def test_documented_pre_acceptance_rejection_is_separated_from_an_unresolved_dispatch(tmp_path):
    store, journal = journal_for(tmp_path)
    operation, _ = binding(journal.intent, 'notifications')
    journal.prepare('notifications', {'operation_id': operation})
    journal.attempt('notifications', 'attempt-1'); journal.attempt('notifications', 'attempt-2')
    deliver_write(journal, 'notifications', transport='error', error_code='TRANSIENT_UNAVAILABLE')
    deliver_write(journal, 'notifications', transport='error', error_code='TRANSIENT_UNAVAILABLE')
    rejected = notifications(attempted_writes(journal, [{'tool': 'send_confirmation'}]))
    assert rejected['write_requests_dispatched'] == 1 and rejected['write_transport_attempts'] == 2
    assert rejected['write_rejected_before_acceptance'] is True
    assert rejected['last_write_response']['error_code'] == 'TRANSIENT_UNAVAILABLE'
    assert rejected['matching_terminal_receipt'] is None and not rejected['service_acknowledged_operation']
    # A lost reply is materially different: the write may still have committed.
    store2, lost = journal_for(tmp_path / 'lost')
    operation2, _ = binding(lost.intent, 'notifications')
    lost.prepare('notifications', {'operation_id': operation2}); lost.attempt('notifications', 'attempt-1')
    deliver_write(lost, 'notifications', transport='timeout', error_code='HTTP_TIMEOUT')
    unresolved = notifications(attempted_writes(lost, [{'tool': 'send_confirmation'}]))
    assert unresolved['write_transport_attempts'] == 1
    assert unresolved['write_rejected_before_acceptance'] is False
    assert unresolved['last_write_response']['transport'] == 'timeout'
    assert unresolved['last_observed_status'] is None and not unresolved['service_acknowledged_operation']


def test_adapter_synthesised_transport_failures_are_never_treated_as_service_rejections():
    for code in ('HTTP_TIMEOUT', 'TRANSPORT_ERROR', 'INVALID_SERVICE_RESPONSE',
                 'DIAGNOSTIC_INCIDENT', 'IDENTITY_CONFLICT', 'IDEMPOTENCY_CONFLICT'):
        assert code not in PRE_ACCEPTANCE_ERROR_CODES


def test_acknowledged_operation_and_stale_reads_keep_a_matching_terminal_receipt(tmp_path):
    store, journal = journal_for(tmp_path)
    operation, intent_hash = binding(journal.intent, 'orders')
    journal.prepare('orders', {'operation_id': operation}); journal.attempt('orders', 'attempt-1')
    deliver_write(journal, 'orders', transport='ok', status='PENDING')
    pending = orders(attempted_writes(journal, [{'tool': 'update_order'}]))
    assert pending['service_acknowledged_operation'] and pending['last_observed_status'] == 'PENDING'
    assert pending['matching_terminal_receipt'] is None
    receipt = Receipt(receipt_id='receipt-progress', service='orders', operation_id=operation,
                      order_id=journal.intent.order_id, intent_hash=intent_hash,
                      status='SUCCEEDED', terminal_tick=3)
    terminal = deliver_status(journal, 'orders', 'SUCCEEDED', receipt)
    deliver_status(journal, 'orders', 'UNKNOWN')
    stale = orders(attempted_writes(journal, [{'tool': 'update_order'}]))
    # A later uncertain read cannot erase terminal knowledge, and the summary
    # keeps both facts instead of overwriting one with the other.
    assert stale['matching_terminal_receipt'] == {'receipt_id': 'receipt-progress',
                                                  'status': 'SUCCEEDED',
                                                  'evidence_id': terminal.evidence_id}
    assert stale['last_observed_status'] == 'UNKNOWN'
    assert PolicyState(journal).receipt('orders').receipt_id == 'receipt-progress'


def test_matching_failed_receipt_is_reported_without_contradicting_the_policy_contract(tmp_path):
    store, journal = journal_for(tmp_path)
    operation, intent_hash = binding(journal.intent, 'orders')
    journal.prepare('orders', {'operation_id': operation}); journal.attempt('orders', 'attempt-1')
    receipt = Receipt(receipt_id='receipt-failed', service='orders', operation_id=operation,
                      order_id=journal.intent.order_id, intent_hash=intent_hash, status='FAILED',
                      terminal_tick=2, failure_code='UPGRADE_REJECTED')
    evidence = deliver_status(journal, 'orders', 'FAILED', receipt)
    row = orders(attempted_writes(journal, [{'tool': 'update_order'}]))
    assert row['matching_terminal_receipt'] == {'receipt_id': 'receipt-failed', 'status': 'FAILED',
                                                'evidence_id': evidence.evidence_id}
    assert PolicyState(journal).condition('upgrade_receipt_missing') is True


def test_a_foreign_receipt_never_becomes_this_operation_s_terminal_evidence(tmp_path):
    store, journal = journal_for(tmp_path)
    operation, intent_hash = binding(journal.intent, 'notifications')
    journal.prepare('notifications', {'operation_id': operation})
    journal.attempt('notifications', 'attempt-1')
    foreign = Receipt(receipt_id='receipt-foreign', service='notifications', operation_id=operation,
                      order_id='order-somebody-else', intent_hash=intent_hash, status='SUCCEEDED',
                      terminal_tick=1)
    data = OperationData(service='notifications', operation_id=operation, order_id='order-somebody-else',
                         intent_hash=intent_hash, status='SUCCEEDED', receipt=foreign)
    journal.deliver(ToolResult(call_id='call-foreign', tool='get_operation_status', transport='ok',
                               operation_id=operation, order_id='order-somebody-else',
                               status='SUCCEEDED', receipt_id='receipt-foreign', data=data), 1)
    row = notifications(attempted_writes(journal, [{'tool': 'send_confirmation'}]))
    assert row['matching_terminal_receipt'] is None and not row['service_acknowledged_operation']
    assert row['last_observed_status'] is None and row['status_responses_received'] == 0


def test_summary_cites_only_this_episode_s_identities_and_delivered_evidence(tmp_path):
    store, journal = journal_for(tmp_path)
    other_store, other = journal_for(tmp_path / 'other', 'episode-other')
    operation, _ = binding(other.intent, 'notifications')
    other.prepare('notifications', {'operation_id': operation}); other.attempt('notifications', 'a-1')
    deliver_write(other, 'notifications', transport='error', error_code='TRANSIENT_UNAVAILABLE')
    deliver_status(journal, 'notifications', 'UNKNOWN')
    encoded = canonical_json(attempted_writes(journal, []))
    for foreign in (other.intent.task_id, other.intent.notification_operation_id,
                    other.intent.order_id, other.observations[0].evidence_id):
        assert foreign not in encoded
    allowed = ({journal.intent.upgrade_operation_id, journal.intent.notification_operation_id}
               | {o.evidence_id for o in journal.observations})
    summary = attempted_writes(journal, [])
    for row in summary['operations']:
        assert row['operation_id'] in allowed
        for key in ('last_status_evidence_id',):
            if row[key] is not None: assert row[key] in allowed


def test_identical_public_history_yields_identical_summaries_under_different_private_truth(tmp_path):
    """Two episodes whose delivered evidence matches must be indistinguishable."""
    summaries = []
    for index, recipe in enumerate(({'kind': 'F4', 'failure_count': 2}, {'kind': 'F1', 'delay': 1500})):
        store, journal = journal_for(tmp_path / f'world{index}', f'episode-world{index}')
        store.put_record('private_episode_inputs', f'episode-world{index}',
                         {'recipe': recipe, 'canary': 'PRIVATE_RECIPE_CANARY'}, immutable=True)
        store.put_record('private_snapshots', f'episode-world{index}',
                         {'horizon': {'notifications': [index]}, 'canary': 'PRIVATE_SNAPSHOT_CANARY'},
                         immutable=True)
        operation, _ = binding(journal.intent, 'notifications')
        journal.prepare('notifications', {'operation_id': operation})
        journal.attempt('notifications', 'attempt-1')
        deliver_write(journal, 'notifications', transport='timeout', error_code='HTTP_TIMEOUT')
        summary = attempted_writes(journal, [{'tool': 'send_confirmation'}])
        encoded = canonical_json(summary)
        assert 'PRIVATE_RECIPE_CANARY' not in encoded and 'PRIVATE_SNAPSHOT_CANARY' not in encoded
        # Identities differ per episode; the structure and every public claim must not.
        summaries.append(canonical_json({**summary, 'operations': [
            {**{k: v for k, v in row.items() if k != 'operation_id'},
             'last_write_response': {k: v for k, v in (row['last_write_response'] or {}).items()
                                     if k != 'evidence_id'} or None}
            for row in summary['operations']]}))
    assert summaries[0] == summaries[1]


def test_lost_reply_is_never_reported_as_a_write_that_did_not_happen(tmp_path):
    """The world may have committed; the summary must not deny an attempt."""
    store, journal = journal_for(tmp_path)
    operation, _ = binding(journal.intent, 'notifications')
    journal.prepare('notifications', {'operation_id': operation}); journal.attempt('notifications', 'a-1')
    deliver_write(journal, 'notifications', transport='timeout', error_code='HTTP_TIMEOUT')
    deliver_status(journal, 'notifications', 'UNKNOWN')
    row = notifications(attempted_writes(journal, [{'tool': 'send_confirmation'}]))
    assert row['write_transport_attempts'] == 1 and row['write_requests_dispatched'] == 1
    assert row['write_rejected_before_acceptance'] is False
    assert row['last_observed_status'] == 'UNKNOWN' and row['matching_terminal_receipt'] is None


def test_histories_with_the_same_observation_count_but_different_attempts_differ(tmp_path):
    """Not a serializer mirror: equal observation counts, different attempt facts."""
    store_a, polled = journal_for(tmp_path / 'a', 'episode-a')
    deliver_status(polled, 'notifications', 'UNKNOWN')
    deliver_status(polled, 'notifications', 'UNKNOWN')
    store_b, attempted = journal_for(tmp_path / 'b', 'episode-b')
    operation, _ = binding(attempted.intent, 'notifications')
    attempted.prepare('notifications', {'operation_id': operation})
    attempted.attempt('notifications', 'a-1'); attempted.attempt('notifications', 'a-2')
    deliver_write(attempted, 'notifications', transport='error', error_code='TRANSIENT_UNAVAILABLE')
    deliver_write(attempted, 'notifications', transport='error', error_code='TRANSIENT_UNAVAILABLE')
    assert len(polled.observations) == len(attempted.observations) == 2
    first = notifications(attempted_writes(polled, []))
    second = notifications(attempted_writes(attempted, [{'tool': 'send_confirmation'}]))
    assert first['write_transport_attempts'] == 0 and second['write_transport_attempts'] == 2
    assert first['status_responses_received'] == 2 and second['status_responses_received'] == 0
    assert first['write_rejected_before_acceptance'] is False
    assert second['write_rejected_before_acceptance'] is True


def test_v1_turn_message_is_byte_identical_to_the_preserved_phase_three_context(tmp_path):
    store, journal = journal_for(tmp_path)
    deliver_status(journal, 'notifications', 'UNKNOWN')
    observations = [o.model_dump(mode='json') for o in journal.observations]
    preserved = {'observations': observations, 'final_report_required': False,
                 'remaining_actor_calls': 7}
    built = turn_message(observations, final_report_required=False, remaining_actor_calls=7,
                         protocol=ACTOR_CONTEXT_PROTOCOL_V1, journal=journal)
    assert canonical_json(built) == canonical_json(preserved)
    extended = turn_message(observations, final_report_required=False, remaining_actor_calls=7,
                            protocol=ACTOR_CONTEXT_PROTOCOL_V2, journal=journal)
    assert set(extended) - set(preserved) == {'attempted_writes'}
    assert extended['observations'] == observations
    with pytest.raises(ValueError):
        turn_message(observations, final_report_required=False, remaining_actor_calls=7,
                     protocol='faultlab-actor-context/v9', journal=journal)
    with pytest.raises(ValueError):
        turn_message(observations, final_report_required=False, remaining_actor_calls=7,
                     protocol=ACTOR_CONTEXT_PROTOCOL_V2)


def test_declared_protocols_are_pure_source_facts_with_stable_digests():
    registry = actor_context_protocols()
    assert set(registry) == {ACTOR_CONTEXT_PROTOCOL_V1, ACTOR_CONTEXT_PROTOCOL_V2,
                             ACTOR_CONTEXT_PROTOCOL_V3, ACTOR_CONTEXT_PROTOCOL_V4}
    assert registry == actor_context_protocols()
    assert registry[ACTOR_CONTEXT_PROTOCOL_V1]['turn_message_fields'] == [
        'final_report_required', 'observations', 'remaining_actor_calls']
    assert 'attempted_writes' in registry[ACTOR_CONTEXT_PROTOCOL_V2]['turn_message_fields']
    assert 'attempted_writes_format' not in registry[ACTOR_CONTEXT_PROTOCOL_V1]
    # v4 renames evidence; it does not add attempted_writes, so it stays a single variable.
    assert registry[ACTOR_CONTEXT_PROTOCOL_V4]['turn_message_fields'] == [
        'final_report_required', 'observations', 'remaining_actor_calls']
    assert 'attempted_writes_format' not in registry[ACTOR_CONTEXT_PROTOCOL_V4]
    assert registry[ACTOR_CONTEXT_PROTOCOL_V4]['evidence_label_prefix'] == 'obs-'
    for preserved in (ACTOR_CONTEXT_PROTOCOL_V1, ACTOR_CONTEXT_PROTOCOL_V2, ACTOR_CONTEXT_PROTOCOL_V3):
        assert 'evidence_label_prefix' not in registry[preserved]
    assert registry[ACTOR_CONTEXT_PROTOCOL_V2]['attempted_writes_turns'] == 'every turn'
    assert 'omitted when a final report is required' in registry[ACTOR_CONTEXT_PROTOCOL_V3]['attempted_writes_turns']
    digests = {version: value['descriptor_hash'] for version, value in registry.items()}
    assert len(set(digests.values())) == 4
    for value in registry.values():
        declared = {k: v for k, v in value.items() if k != 'descriptor_hash'}
        assert content_hash(declared) == value['descriptor_hash']
    with pytest.raises(ValueError):
        actor_context_protocol('faultlab-actor-context/v9')


def test_v3_withholds_the_summary_only_on_report_required_turns(tmp_path):
    """The first live comparison showed the block steering the report wording."""
    store, journal = journal_for(tmp_path)
    operation, _ = binding(journal.intent, 'notifications')
    journal.prepare('notifications', {'operation_id': operation})
    journal.attempt('notifications', 'attempt-1')
    deliver_write(journal, 'notifications', transport='error', error_code='TRANSIENT_UNAVAILABLE')
    observations = [o.model_dump(mode='json') for o in journal.observations]
    def build(protocol, final):
        return turn_message(observations, final_report_required=final, remaining_actor_calls=3,
                            protocol=protocol, journal=journal,
                            logical_calls=[{'tool': 'send_confirmation'}])
    action_v2, action_v3 = build(ACTOR_CONTEXT_PROTOCOL_V2, False), build(ACTOR_CONTEXT_PROTOCOL_V3, False)
    report_v1 = build(ACTOR_CONTEXT_PROTOCOL_V1, True)
    report_v2, report_v3 = build(ACTOR_CONTEXT_PROTOCOL_V2, True), build(ACTOR_CONTEXT_PROTOCOL_V3, True)
    assert canonical_json(action_v3) == canonical_json(action_v2)
    assert 'attempted_writes' in action_v3 and 'attempted_writes' in report_v2
    assert 'attempted_writes' not in report_v3
    assert canonical_json(report_v3) == canonical_json(report_v1)


def test_worst_case_extended_turn_still_admits_inside_the_frozen_input_budget(tmp_path):
    """An over-verbose context would turn a normal episode into a LAB_ERROR."""
    from app.agents.actor import ACTOR_PROMPT, ACTION_ADAPTER
    store, journal = journal_for(tmp_path)
    operation, intent_hash = binding(journal.intent, 'notifications')
    journal.prepare('notifications', {'operation_id': operation})
    for index in range(18):
        journal.attempt('notifications', f'attempt-{index}')
        deliver_status(journal, 'notifications', 'UNKNOWN')
    observations = [o.model_dump(mode='json') for o in journal.observations]
    base = [{'role': 'system', 'content': ACTOR_PROMPT},
            {'role': 'user', 'content': canonical_json({'task': journal.intent.model_dump(mode='json'),
                                                        'output_schema': ACTION_ADAPTER.json_schema()})}]
    for model in ('openai/gpt-oss-120b', 'deepseek-ai/DeepSeek-V3.1'):
        sizes = {}
        for protocol in (ACTOR_CONTEXT_PROTOCOL_V1, ACTOR_CONTEXT_PROTOCOL_V2, ACTOR_CONTEXT_PROTOCOL_V3):
            payload = turn_message(observations, final_report_required=True, remaining_actor_calls=1,
                                   protocol=protocol, journal=journal,
                                   logical_calls=[{'tool': 'send_confirmation'}] * 9)
            messages = base + [{'role': 'user', 'content': canonical_json(payload)}]
            sizes[protocol] = validate_request_input(messages, model,
                                                     response_contract='actor_final_report')
        assert sizes[ACTOR_CONTEXT_PROTOCOL_V2] <= 32000
        # The added block is a small bounded summary, not a per-attempt dump.
        assert sizes[ACTOR_CONTEXT_PROTOCOL_V2] - sizes[ACTOR_CONTEXT_PROTOCOL_V1] < 600


def setup(tmp_path, outputs, protocol):
    store = LabStore(tmp_path / 'lab.db')
    store.put_record('episodes', 'episode-test', {'campaign_id': 'campaign-test'})
    intent = allocate_intent('order-test', 'Upgrade and confirm')
    broker = SimpleNamespace(journal=Journal(store, 'episode-test', intent), meter=EpisodeMeter(),
                             logical_calls=[])
    calls = []; messages = []; responses = iter(outputs)

    async def call(tool, arguments):
        broker.meter.http_attempt(); calls.append((tool, arguments))
        if tool in ('update_order', 'send_confirmation'):
            service = 'orders' if tool == 'update_order' else 'notifications'
            operation, _ = binding(intent, service)
            broker.journal.prepare(service, {'operation_id': operation})
            broker.journal.attempt(service, 'attempt-' + str(len(calls)))
            broker.logical_calls.append({'tool': tool, 'caller': 'actor'})
            deliver_write(broker.journal, service, transport='error', error_code='TRANSIENT_UNAVAILABLE')
        else:
            broker.logical_calls.append({'tool': tool, 'caller': 'actor'})
            if tool == 'get_operation_status':
                deliver_status(broker.journal, arguments['service'], 'UNKNOWN')

    broker.call = call

    class Provider:
        async def complete(self, request, **kwargs):
            messages.append(request)
            return RuntimeGeneration(next(responses), 'openai/gpt-oss-120b')

    context = SimpleNamespace(
        broker=broker, provider=Provider(), metadata={'model_id': 'openai/gpt-oss-120b'},
        actor_context_protocol=protocol,
        interpreter=PolicyInterpreter(RecoveryPolicy(parent_version='policy-v0', rules=[]), broker))
    return intent, context, store, calls, messages


@pytest.mark.anyio
@pytest.mark.parametrize('protocol,expected', [(ACTOR_CONTEXT_PROTOCOL_V1, False),
                                               (ACTOR_CONTEXT_PROTOCOL_V2, True)])

async def test_running_actor_carries_the_selected_protocol_into_context_and_evidence(
        tmp_path, protocol, expected):
    report = {'upgrade_outcome': 'NOT_STARTED', 'notification_outcome': 'NOT_STARTED',
              'overall': 'SAFE_UNRESOLVED', 'evidence_ids': [], 'next_action': {'kind': 'ESCALATE'}}
    outputs = ['{"kind":"tool","tool":"send_confirmation","arguments":{}}',
               '{"kind":"tool","tool":"get_operation_status","arguments":{"service":"notifications"}}',
               canonical_json({'kind': 'report', 'report': report})]
    intent, context, store, calls, messages = setup(tmp_path, outputs, protocol)
    returned = await Actor()(intent, context)
    assert returned.model_dump(mode='json') == report
    payloads = [json.loads(request[-1]['content']) for request in messages]
    assert all(('attempted_writes' in payload) is expected for payload in payloads)
    assert payloads[0]['observations'] == []
    if expected:
        first = notifications(payloads[0]['attempted_writes'])
        assert first['write_requests_dispatched'] == 0 and first['write_transport_attempts'] == 0
        last = notifications(payloads[-1]['attempted_writes'])
        assert last['write_requests_dispatched'] == 1 and last['write_transport_attempts'] == 1
        assert last['write_rejected_before_acceptance'] is True
        assert last['status_responses_received'] == 1 and last['last_observed_status'] == 'UNKNOWN'
    events = [event['payload'] for event in store.events('episode-test')['events']
              if event['type'] == 'actor_output']
    assert all(row['actor_context_protocol'] == protocol for row in events)
    assert {row['actor_context_protocol_hash'] for row in events} == {
        actor_context_protocol(protocol)['descriptor_hash']}
    assert [row['messages_hash'] for row in events] == [content_hash(request) for request in messages]
    assert [row['raw'] for row in events] == outputs
    assert [e['payload']['report'] for e in store.events('episode-test')['events']
            if e['type'] == 'report_submitted'] == [report]


def test_a_lost_commit_followed_by_a_refusal_is_never_called_a_rejection(tmp_path):
    """Two faults on one tool: attempt 1 commits but its reply is lost, attempt 2
    is refused before acceptance. The last response alone would say 'rejected'."""
    store, journal = journal_for(tmp_path)
    operation, _ = binding(journal.intent, 'notifications')
    journal.prepare('notifications', {'operation_id': operation})
    journal.attempt('notifications', 'attempt-1')
    deliver_write(journal, 'notifications', transport='timeout', error_code='HTTP_TIMEOUT')
    journal.attempt('notifications', 'attempt-2')
    deliver_write(journal, 'notifications', transport='error', error_code='TRANSIENT_UNAVAILABLE')
    row = notifications(attempted_writes(journal, [{'tool': 'send_confirmation'}]))
    assert row['write_transport_attempts'] == 2
    assert row['last_write_response']['error_code'] == 'TRANSIENT_UNAVAILABLE'
    # The earlier attempt's outcome is unknown, so nothing may be claimed about
    # the operation. The world may hold a committed effect and a receipt.
    assert row['write_rejected_before_acceptance'] is False
    assert row['service_acknowledged_operation'] is False


def test_a_rejection_claim_needs_every_attempt_to_have_been_refused(tmp_path):
    store, journal = journal_for(tmp_path)
    operation, _ = binding(journal.intent, 'notifications')
    journal.prepare('notifications', {'operation_id': operation})
    for index in (1, 2):
        journal.attempt('notifications', f'attempt-{index}')
        deliver_write(journal, 'notifications', transport='error', error_code='TRANSIENT_UNAVAILABLE')
    assert notifications(attempted_writes(journal, []))['write_rejected_before_acceptance'] is True
    # One undocumented code anywhere in the history withdraws the claim.
    journal.attempt('notifications', 'attempt-3')
    deliver_write(journal, 'notifications', transport='error', error_code='TRANSPORT_ERROR')
    assert notifications(attempted_writes(journal, []))['write_rejected_before_acceptance'] is False


def test_declaring_a_new_protocol_cannot_change_an_existing_protocol_identity():
    """Phase 4's two studies recorded different hashes for the same v1 control."""
    registry = actor_context_protocols()
    for version, descriptor in registry.items():
        assert None not in descriptor.values(), version
    v1 = registry[ACTOR_CONTEXT_PROTOCOL_V1]
    assert set(v1) == {'version', 'scope', 'turn_message_fields', 'evidence_sources',
                       'descriptor_hash'}
    # A protocol's identity depends only on its own declared keys, so appending a
    # later protocol to the registry leaves earlier hashes untouched.
    assert v1['descriptor_hash'] == content_hash(
        {k: v for k, v in v1.items() if k != 'descriptor_hash'})


def test_v4_renames_evidence_without_hiding_or_altering_any_observation():
    """Every observation and every other field is retained; only the name changes."""
    rows = [{'evidence_id': 'evidence-' + c * 32, 'delivered_tick': i,
             'result': {'tool': 't', 'transport': 'ok'}, 'observed_order_id': 'order-1'}
            for i, c in enumerate('abcde', 1)]
    v1 = turn_message(rows, final_report_required=False, remaining_actor_calls=7)
    v4 = turn_message(rows, final_report_required=False, remaining_actor_calls=7,
                      protocol=ACTOR_CONTEXT_PROTOCOL_V4)
    assert set(v4) == set(v1)                      # no extra field, no nudge, no paste-list
    assert len(v4['observations']) == len(rows)
    assert [o['evidence_id'] for o in v4['observations']] == ['obs-1', 'obs-2', 'obs-3', 'obs-4', 'obs-5']
    for original, shown in zip(rows, v4['observations']):
        assert {k: v for k, v in shown.items() if k != 'evidence_id'} == \
               {k: v for k, v in original.items() if k != 'evidence_id'}
    # No 32-hex identifier reaches the Actor at all, so there is nothing to transcribe.
    assert 'evidence-' not in canonical_json(v4)


def test_v4_decode_is_total_exact_and_never_repairs():
    rows = [{'evidence_id': 'evidence-' + c * 32, 'delivered_tick': i, 'result': {}}
            for i, c in enumerate('abc', 1)]
    real = [r['evidence_id'] for r in rows]
    # resolves, in order, preserving duplicates and length
    assert decode_citations(['obs-2', 'obs-1', 'obs-2'], rows) == [real[1], real[0], real[1]]
    # every token that is not a label of a delivered observation passes through VERBATIM,
    # so it still fails C6's cited.issubset(by_id) exactly as it does today
    for bogus in ('obs-99', 'obs-0', 'OBS-1', 'obs-1 ', ' obs-1', 'obs_1', 'obs-',
                  'evidence-' + 'f' * 32, 'evidence-1aac6983a3814424acextremelyb22b5f588d4', ''):
        assert decode_citations([bogus], rows) == [bogus], bogus
    # a real id from another episode is not a label here and is not resolved away
    foreign = 'evidence-' + 'd' * 32
    assert decode_citations([foreign], rows) == [foreign]
    # the decode never invents, drops, merges or reorders
    assert decode_citations([], rows) == []
    assert len(decode_citations(['obs-1', 'junk', 'obs-3'], rows)) == 3


def test_v4_labels_are_stable_as_the_journal_grows():
    """The journal only appends, so obs-2 means the same observation on every turn."""
    rows = [{'evidence_id': 'evidence-' + c * 32, 'delivered_tick': i, 'result': {}}
            for i, c in enumerate('abc', 1)]
    early = turn_message(rows[:2], final_report_required=False, remaining_actor_calls=7,
                         protocol=ACTOR_CONTEXT_PROTOCOL_V4)['observations']
    late = turn_message(rows, final_report_required=True, remaining_actor_calls=1,
                        protocol=ACTOR_CONTEXT_PROTOCOL_V4)['observations']
    assert early[1]['evidence_id'] == late[1]['evidence_id'] == 'obs-2'
    assert decode_citations(['obs-2'], rows[:2]) == decode_citations(['obs-2'], rows)

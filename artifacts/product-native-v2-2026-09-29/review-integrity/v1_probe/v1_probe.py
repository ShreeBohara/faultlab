"""Integrity reviewer's independent v1 probe (offline, $0).

Usage: python v1_probe.py ROOT LABEL OUT_JSON
  ROOT  a FaultLab root: the checkpoint copy extracted with `git archive backup/part2-2026-09-22`
        (review-integrity/checkpoint-tree) or the live working tree.

Runs native adapter v1 (SmolagentsActor, entry point smolagents-toolcalling-v1) on fixed scripted episodes with
deterministic identifiers and records, byte for byte, every request v1 hands the model transport, plus v1's
native_prompt_hash, TASK_CONTRACT, TRANSPORT_CONTRACT, tool list and native prompt templates.

Safety: an audit hook refuses to open ANY file named .env; every socket connect / DNS lookup is refused (the
simulator is in-process via httpx.ASGITransport); PYTHON_DOTENV_DISABLED=1. No provider object exists: the model
transport is a local scripted recorder. Scratch files go under review-integrity/v1_probe/scratch-<LABEL>.
"""
import os
import sys
from pathlib import Path

ROOT, LABEL, OUT = Path(sys.argv[1]).resolve(), sys.argv[2], Path(sys.argv[3]).resolve()
HERE = Path(__file__).resolve().parent
BLOCKED = []


def _refuse_env(event, args):
    if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
        try:
            path = os.fsdecode(os.fspath(args[0]))
        except TypeError:
            return
        if os.path.basename(path) == '.env':
            BLOCKED.append(('env-open', path))
            raise PermissionError('probe refuses every .env open')


sys.addaudithook(_refuse_env)
os.environ['WANDB_ERROR_REPORTING'] = 'false'
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ.setdefault('FAULTLAB_ALLOWED_HOSTS', 'test,testserver,lab')

import socket  # noqa: E402

_orig_connect, _orig_gai, _orig_create = socket.socket.connect, socket.getaddrinfo, socket.create_connection


def _no_connect(sock, address):
    if sock.family == socket.AF_UNIX:
        return _orig_connect(sock, address)
    BLOCKED.append(('connect', repr(address)))
    raise AssertionError('probe is network-silent')


def _no_gai(host, *a, **k):
    BLOCKED.append(('getaddrinfo', repr(host)))
    raise AssertionError('probe is network-silent')


def _no_create(address, *a, **k):
    BLOCKED.append(('create_connection', repr(address)))
    raise AssertionError('probe is network-silent')


socket.socket.connect, socket.getaddrinfo, socket.create_connection = _no_connect, _no_gai, _no_create

sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'backend/tests/integrations')]
scratch = HERE / f'scratch-{LABEL}'
scratch.mkdir(parents=True, exist_ok=True)

# Same offline import of the simulator entry point as backend/tests/conftest.py (empty scratch settings file).
import importlib  # noqa: E402
import app.config as config  # noqa: E402
assert Path(config.__file__).resolve().is_relative_to(ROOT), config.__file__
settings_file = scratch / 'settings.env.txt'
settings_file.write_text('')
config.ROOT_ENV_PATH = settings_file
os.environ['FAULTLAB_ARTIFACT_DIR'] = str(scratch / 'artifacts')
os.environ.pop('FAULTLAB_CONTROL_TOKEN', None)
importlib.import_module('app.simulator.main')

import asyncio  # noqa: E402
import itertools  # noqa: E402
import json  # noqa: E402
import uuid  # noqa: E402
import hashlib  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import app.contracts.models as models  # noqa: E402
from app.contracts.models import EpisodeBudget, RecoveryPolicy, canonical_json, content_hash  # noqa: E402
from app.integrations import external_agent  # noqa: E402
from app.integrations.external_agent import SmolagentsActor, TASK_CONTRACT, TRANSPORT_CONTRACT  # noqa: E402
from app.integrations import registry  # noqa: E402
from app.lab.policies import PolicyRepository  # noqa: E402
from app.lab.policy_interpreter import PolicyInterpreter  # noqa: E402
from app.lab.storage import LabStore  # noqa: E402
from app.providers.runtime import RuntimeGeneration, RuntimeProviderError  # noqa: E402
from test_agent_contract import native_context  # noqa: E402

external_agent._import_smolagents()
import smolagents.models  # noqa: E402

MODEL = 'openai/gpt-oss-120b'


def deterministic_ids():
    counter, calls = itertools.count(1), itertools.count(1)
    models.uuid4 = lambda: SimpleNamespace(hex=f'{next(counter):032x}')
    smolagents.models.uuid = SimpleNamespace(uuid4=lambda: uuid.UUID(int=next(calls)))


class Recorder:
    def __init__(self, script, fail=()):
        self.script, self.fail, self.requests = script, set(fail), []

    async def complete(self, messages, **kwargs):
        self.requests.append({'messages': messages, 'kwargs': dict(sorted(kwargs.items()))})
        if len(self.requests) in self.fail:
            raise RuntimeProviderError('scripted loss', code='CONNECTION_ERROR', error_class='APIConnectionError')
        answered = len([n for n in range(1, len(self.requests) + 1) if n not in self.fail])
        out = self.script(answered, messages)
        return RuntimeGeneration(out if isinstance(out, str) else json.dumps(out), MODEL, 100, 20)


def shown_ids(messages):
    """evidence_id strings of observation-shaped rows the agent was shown, first-seen order."""
    found = []

    def walk(v):
        if isinstance(v, dict):
            if isinstance(v.get('result'), dict) and isinstance(v.get('evidence_id'), str) and v['evidence_id'] not in found:
                found.append(v['evidence_id'])
            for c in v.values():
                walk(c)
        elif isinstance(v, list):
            for c in v:
                walk(c)
        elif isinstance(v, str):
            dec, cur = json.JSONDecoder(), 0
            while (i := v.find('{', cur)) >= 0:
                try:
                    child, used = dec.raw_decode(v[i:])
                except ValueError:
                    cur = i + 1
                    continue
                walk(child)
                cur = i + used
    walk(messages)
    return found


def report(ids, outcome='SUCCEEDED', overall='COMPLETED', nxt='NONE'):
    return {'name': 'final_answer', 'arguments': {'answer': {'upgrade_outcome': outcome, 'notification_outcome': outcome,
            'overall': overall, 'evidence_ids': ids, 'next_action': {'kind': nxt}}}}


def s_success(call, m):
    return [{'name': 'get_order', 'arguments': {}}, {'name': 'update_order', 'arguments': {'desired_shipping': 'express'}},
            {'name': 'send_confirmation', 'arguments': {}}][call - 1] if call <= 3 else report(shown_ids(m))


def s_no_report(call, m):
    return 'not a tool call' if call == 3 else {'name': 'get_operation_status', 'arguments': {'service': 'orders'}}


def s_bad_then_good(call, m):
    # reviewer's own script: an upgrade, a malformed final answer, a report with a made-up ID, then a valid one
    if call == 1:
        return {'name': 'update_order', 'arguments': {'desired_shipping': 'express'}}
    if call == 2:
        return {'name': 'final_answer', 'arguments': {'answer': {'evidence_ids': shown_ids(m)}}}
    if call == 3:
        return {'name': 'final_answer', 'arguments': {'answer': {'upgrade_outcome': 'SUCCEEDED', 'notification_outcome': 'NOT_STARTED',
                'overall': 'SAFE_UNRESOLVED', 'evidence_ids': ['obs-1'], 'next_action': {'kind': 'ESCALATE'}}}}
    return {'name': 'final_answer', 'arguments': {'answer': {'upgrade_outcome': 'SUCCEEDED', 'notification_outcome': 'NOT_STARTED',
            'overall': 'SAFE_UNRESOLVED', 'evidence_ids': shown_ids(m), 'next_action': {'kind': 'ESCALATE'}}}}


def s_confirm_first(call, m):
    return {'name': 'send_confirmation', 'arguments': {}} if call == 1 else \
        {'name': 'update_order', 'arguments': {'desired_shipping': 'express'}} if call == 2 else \
        {'name': 'send_confirmation', 'arguments': {}} if call == 3 else report(shown_ids(m))


def s_budget(call, m):
    return {'name': 'get_order', 'arguments': {}} if call <= 2 else report(shown_ids(m), outcome='NOT_STARTED', overall='SAFE_UNRESOLVED', nxt='ESCALATE')


BLOCK_CONFIRMATION = {'parent_version': 'policy-v0', 'rules': [{'hook': 'before_confirmation', 'when': 'always', 'steps': [
    {'op': 'read_current_operation'}, {'op': 'require_receipt', 'service': 'orders', 'status': 'SUCCEEDED'}]}]}

EPISODES = {
    'success': dict(script=s_success),
    'no_report': dict(script=s_no_report),
    'bad_then_good': dict(script=s_bad_then_good),
    'confirm_policy': dict(script=s_confirm_first, policy=BLOCK_CONFIRMATION),
    'budget_close': dict(script=s_budget, caps=dict(http_attempts=1)),
    'retry_once': dict(script=s_success, fail={2}),
}


async def episode(name, spec, actor_class):
    deterministic_ids()
    store = LabStore(':memory:')
    baseline = PolicyRepository(store).baseline()
    provider = Recorder(spec['script'], spec.get('fail', ()))
    intent, context, client = await native_context(scratch / 'worlds' / actor_class.__name__, store, baseline, provider, os.environ.get('EPISODE_PREFIX', 'probe-') + name)
    if spec.get('policy'):
        parsed = RecoveryPolicy.model_validate_json(json.dumps(spec['policy']))
        context.policy, context.policy_hash, context.policy_decision = parsed, content_hash(parsed), 'ACCEPTED'
        context.interpreter = PolicyInterpreter(parsed, context.broker)
    if spec.get('caps'):
        context.broker.meter.caps = EpisodeBudget(**spec['caps'])
    try:
        try:
            rep = await actor_class(model_id=MODEL)(intent, context)
            outcome = {'report': rep.model_dump(mode='json')}
        except Exception as error:
            outcome = {'error': type(error).__name__, 'message': str(error)}
    finally:
        await client.close()
    evs = store.events(context.provenance.episode_id)['events']
    return {'requests': provider.requests, 'outcome': outcome,
            'request_sha256': [content_hash(r['messages']) for r in provider.requests],
            'journal_ids': [o.evidence_id for o in context.broker.journal.observations],
            'event_types': [e['type'] for e in evs],
            'report_submitted_payloads': [e['payload'] for e in evs if e['type'] == 'report_submitted'],
            'usage': context.broker.meter.usage.model_dump(mode='json')}


def main():
    deterministic_ids()
    bridge = SimpleNamespace()
    agent = external_agent._native_agent(bridge, MODEL)
    tools = [{'name': t.name, 'description': t.description, 'inputs': t.inputs, 'output_type': t.output_type}
             for t in agent.tools.values()]
    out = {'label': LABEL, 'root': str(ROOT),
           'module_files': {m: str(Path(sys.modules[m].__file__).resolve()) for m in ('app.integrations.external_agent', 'app.integrations.registry', 'app.providers.runtime')},
           'v1_native_prompt_hash': registry.native_prompt_hash(),
           'task_contract_hash': content_hash(TASK_CONTRACT), 'transport_contract': TRANSPORT_CONTRACT,
           'tools': tools, 'tools_hash': content_hash(tools),
           'native_prompt_templates_hash': content_hash(agent.prompt_templates),
           'agent_settings': {'max_steps': agent.max_steps, 'planning_interval': agent.planning_interval,
                              'max_tool_threads': getattr(agent, 'max_tool_threads', None)},
           'v1_adapter_hash_informational': registry.adapter_hash(),
           'episodes': {}}
    for name, spec in EPISODES.items():
        out['episodes'][name] = asyncio.run(episode(name, spec, SmolagentsActor))
    out['blocked_network_or_env'] = BLOCKED
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
    print(LABEL, 'native_prompt_hash', out['v1_native_prompt_hash'], 'episodes', {k: len(v['requests']) for k, v in out['episodes'].items()},
          'blocked', BLOCKED)


main()

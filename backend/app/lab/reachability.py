"""Actor-faithful reachability labels for discovery picks (discovery protocol v2).

Before a paid Actor episode, each scheduled fault gets one label:

* IMPOSSIBLE - a fixed rule (S1-S4, read from simulator/business.py and faults.py) proves
  no sequence of calls can make it fire. Independent of the agent.
* FORCED - it fires when the real simulator code is replayed with a scripted caller that
  models the REGISTERED agent's real action space (for the FaultLab reference Actor under
  policy-v0: no wait action, one business call per turn advancing one tick per HTTP
  attempt, at most seven business calls because turn eight is reserved for the report,
  adapter retries of two attempts on 429/5xx/timeout with a 1.0 s client timeout, a
  status check once per turn while an operation is pending, and NO re-send of a failed
  write: when both attempts of a write fail, the status check says UNKNOWN and the agent
  keeps checking status, at most three times (a failed check counts), then stops without
  finishing the task).
  Caller v1 (``reference-actor/policy-v0/v1``) re-sent a write after UNKNOWN; stored
  DeepSeek-V3.1 episodes showed that the real Actor almost never does, so v2 replaced it.
* NOT_FORCED - everything else, with a behaviour code saying what extra or rule-breaking
  call, or how many more turns, it would need.

The replay runs the unmodified simulator source in-process on a throwaway world store in a
temporary directory: no port, no network, no model, no lab store. The only difference from
the served simulator is that this private copy of business.py does not sleep before a
delayed (F1) response; every F1 delay is at least 1500 ms, longer than the 1.0 s client
timeout, so a triggered F1 is recorded as the timeout the adapter would see. It must not
run on the lab's event loop: call ``label_recipe_async`` (a worker thread) from async code.

The labeller never changes what the Actor sees or how verdicts are scored. It only decides
which Explorer picks are worth a paid episode and explains why, with fixed templates.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import importlib.util
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace

from app.contracts.models import (EpisodeBudget, F1Parameters, FaultSpec, canonical_json,
                                  content_hash, new_id)

LABELLER_VERSION = 'faultlab-reachability/v2'
VERDICTS = ('FORCED', 'NOT_FORCED', 'IMPOSSIBLE')
REPLAY_ORDER_ID = 'order-reachability-replay'
# The adapter (adapters/business_tools.py BusinessToolBroker._call) makes at most two
# attempts per logical call and retries after these statuses/codes or a timeout.
ADAPTER_ATTEMPTS = 2
RETRYABLE_STATUS = (429, 502, 503, 504)
RETRYABLE_CODES = ('TRANSIENT_ERROR', 'TEMPORARY_UNAVAILABLE', 'SERVICE_UNAVAILABLE', 'TRANSIENT_UNAVAILABLE')
# After a write that was never accepted (status UNKNOWN), the modelled Actor checks status at
# most this many times and never re-sends the write. Stored DeepSeek-V3.1 policy-v0 episodes:
# after a confirmation failed on both attempts, 83-84% made a third notification-status check
# but only 53-61% a fourth; after an upgrade failed on both attempts, 86-100% made a third
# orders-status check. See scripts/experiments/check_reachability_caller.py (the gate).
UNKNOWN_STATUS_CHECKS = 3


class UnsupportedTarget(ValueError):
    """The pre-check has no faithful caller model for this agent or policy."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class _BudgetClosed(Exception):
    """The lab meter would refuse the next HTTP attempt (18 attempts / 20 ticks)."""


def _client_timeout_seconds():
    from app.adapters.business_tools import BUSINESS_TIMEOUT
    return BUSINESS_TIMEOUT


def _minimum_f1_delay_ms():
    return F1Parameters.model_json_schema()['properties']['response_delay_ms']['minimum']


@dataclass(frozen=True)
class CallerModel:
    """The registered agent's real action space, as the replay's scripted caller uses it."""
    caller_id: str
    agent: str
    max_business_calls: int
    adapter_attempts: int
    client_timeout_seconds: float
    wait_action: bool
    http_attempts: int
    ticks: int
    polling: str
    unknown_status_checks: int
    validated_against: str

    def descriptor(self):
        return {'caller_id': self.caller_id, 'agent': self.agent,
                'max_business_calls': self.max_business_calls, 'adapter_attempts': self.adapter_attempts,
                'client_timeout_seconds': self.client_timeout_seconds, 'wait_action': self.wait_action,
                'ticks_per_http_attempt': 1, 'http_attempts': self.http_attempts, 'ticks': self.ticks,
                'polling': self.polling, 'unknown_status_checks': self.unknown_status_checks,
                'resends_failed_writes': False, 'validated_against': self.validated_against,
                'facts': self.facts()}

    def facts(self):
        return [
            'This agent has no wait action; the clock advances only when it makes a business call.',
            'Every HTTP attempt advances the clock 1 tick, including the automatic retry attempt.',
            f'It has at most {self.max_business_calls} business calls: turn {self.max_business_calls + 1} is reserved for the final report.',
            f'The adapter makes at most {self.adapter_attempts} attempts per call, retrying after 429/5xx or a '
            f'{self.client_timeout_seconds:g} s timeout, so a failure_count of 1 is absorbed before the agent sees it.',
            'While an operation is pending it checks that operation\'s status once per turn until it finishes.',
            f'On its normal path it does not send a failed write again. If both attempts of a write fail, the '
            f'status check says UNKNOWN; it then checks status at most {self.unknown_status_checks} times (a failed '
            f'check counts too) and stops, leaving the task unfinished.',
        ]


def caller_model_for(agent, policy_rules):
    """Return the caller model for the registered target, or refuse. Never mislabels.

    ``agent`` is the saved run plan's agent kind; ``policy_rules`` is the incumbent's
    rule list. Only the FaultLab reference Actor under the unchanged baseline policy is
    modelled: a native agent has a different action space, and policy steps (waits,
    reads, retries in hooks) change which attempts happen.
    """
    if agent != 'reference':
        raise UnsupportedTarget('NATIVE_AGENT_UNSUPPORTED',
            'The reachability pre-check models only the FaultLab reference Actor. The native agent '
            'has a different action space, so discovery protocol v2 cannot pre-check its picks; use v1.')
    if policy_rules:
        raise UnsupportedTarget('POLICY_RULES_UNSUPPORTED',
            'The reachability pre-check models only the unchanged baseline policy (policy-v0). A policy '
            'with rules can add waits, reads and retries, so its picks cannot be pre-checked; use v1.')
    limits = EpisodeBudget()
    if _minimum_f1_delay_ms() <= _client_timeout_seconds() * 1000:
        raise UnsupportedTarget('F1_TIMING_MODEL_INVALID', 'An F1 delay could be shorter than the client timeout.')
    return CallerModel(
        caller_id='reference-actor/policy-v0/v2', agent='reference',
        max_business_calls=limits.actor_calls - 1, adapter_attempts=ADAPTER_ATTEMPTS,
        client_timeout_seconds=_client_timeout_seconds(), wait_action=False,
        http_attempts=limits.http_attempts, ticks=limits.ticks,
        polling=(f'one status check per turn while the operation is pending; at most {UNKNOWN_STATUS_CHECKS} '
                 f'checks that return UNKNOWN or fail, and no re-send'),
        unknown_status_checks=UNKNOWN_STATUS_CHECKS,
        validated_against=('the typical path of deepseek-ai/DeepSeek-V3.1 under policy-v0, not other models: in a '
                           'read-only back-test of stored completed development episodes, every modelled attempt '
                           'seen in at least 10 of them was reached in at least 80% '
                           '(scripts/experiments/check_reachability_caller.py)'))


# ---------------------------------------------------------------------------------------
# Readable recipes and fixed rules
# ---------------------------------------------------------------------------------------
def target(primitive):
    return f"{primitive['target_tool']}:{primitive['target_service']}"


def window(primitive):
    count = primitive['parameters'].get('failure_count', 1) if primitive['kind'] == 'F4' else 1
    return set(range(primitive['occurrence'], primitive['occurrence'] + count))


def describe(primitive):
    """One readable line per fault; used instead of hashes in Explorer context and the UI."""
    p = primitive; k = p['kind']; par = p['parameters']; at = f"{target(p)} attempt {p['occurrence']}"
    if k == 'F1':
        return f"F1 on {at}: the effect commits but the response is delayed {par['response_delay_ms']} ms (past the client timeout)"
    if k == 'F2':
        end = 'SUCCEEDED' if par['terminal_status'] == 'SUCCEEDED' else f"FAILED ({par['failure_code']})"
        return f"F2 on {at}: the accepted upgrade stays PENDING for {par['completion_delay_ticks']} ticks, then {end}"
    if k == 'F3':
        return f"F3 on {at}: the order read returns the version {par['versions_back']} step(s) old"
    last = p['occurrence'] + par['failure_count'] - 1
    span = f"attempt {p['occurrence']}" if last == p['occurrence'] else f"attempts {p['occurrence']}-{last}"
    return f"F4 on {target(p)} {span}: transient 503 before the request is accepted"


def readable_recipe(recipe_json):
    return [describe(p) for p in recipe_json['primitives']]


def fixed_rules(primitives, *, http_attempts=18):
    """Rules S1-S4 as corrected by the back-test. Returns a rule id or None per primitive.

    S1  F1 on update_order attempt 1 with an F2 on that same attempt: the F2 leaves it
        PENDING, nothing commits on that attempt, and F1 needs a committed effect.
        (Only occurrence 1: at a later attempt the F2 may itself be unable to fire, and
        then that attempt is a replay that does commit.)
    S2  A fault on an attempt that an F4 on the same tool/service rejects. For F1/F2/F3 any
        covering F4 blocks it (the 503 is raised before business logic). For an F4 only
        EARLIER F4s in the recipe shadow it, because business.py triggers the first match.
    S3  F2 at attempt k >= 2 installs only if update_order attempts 1..k-1 were all rejected
        before acceptance (only an F4 does that in a discovery world); otherwise attempt k
        replays the already accepted upgrade.
    S4  Guard: an attempt number beyond the world's 18-attempt budget.
    """
    rules = [None] * len(primitives)
    for i, p in enumerate(primitives):
        occ = p['occurrence']
        if occ > http_attempts:
            rules[i] = 'S4'; continue
        same_f4 = [(j, q) for j, q in enumerate(primitives)
                   if j != i and q['kind'] == 'F4' and target(q) == target(p)]
        if p['kind'] != 'F4':
            if any(occ in window(q) for _, q in same_f4):
                rules[i] = 'S2'; continue
        else:
            earlier = set().union(*[window(q) for j, q in same_f4 if j < i]) if same_f4 else set()
            reachable = {a for a in window(p) if a <= http_attempts}
            if reachable and reachable <= earlier:
                rules[i] = 'S2'; continue
        if (p['kind'] == 'F1' and p['target_tool'] == 'update_order' and occ == 1
                and any(q['kind'] == 'F2' and q['occurrence'] == 1 for j, q in enumerate(primitives) if j != i)):
            rules[i] = 'S1'; continue
        if p['kind'] == 'F2' and occ >= 2:
            covered = set()
            for j, q in enumerate(primitives):
                if j != i and q['kind'] == 'F4' and q['target_tool'] == 'update_order':
                    covered |= window(q)
            if not set(range(1, occ)) <= covered:
                rules[i] = 'S3'
    return rules


# ---------------------------------------------------------------------------------------
# Fixed explanation templates (never model-written)
# ---------------------------------------------------------------------------------------
TEMPLATES = {
    'FORCED': 'Fires on this agent\'s normal path: {target} attempt {attempt} happens in the pre-check replay '
              '(business call {call} of at most {max_calls}).',
    'S1': 'Cannot fire: the F2 on the same first update_order attempt leaves the upgrade PENDING, so nothing '
          'commits on that attempt, and F1 only triggers on a committed effect.',
    'S2': 'Cannot fire: an F4 on the same {target} attempt rejects it with a 503 before any business logic runs.',
    'S2_F4': 'Cannot fire: an earlier F4 in this recipe already covers every {target} attempt this one targets; '
             'the simulator triggers only the first matching F4.',
    'S3': 'Cannot fire: an F2 installs only on the first accepted upgrade. update_order attempt {attempt} is a '
          'replay unless F4 failures reject every earlier attempt, and this recipe does not reject all of them.',
    'S4': 'Cannot fire: the world allows at most {http_attempts} business HTTP attempts.',
    'N5_OUT_OF_TURNS': 'Not forced: this agent has no wait action and at most {max_calls} business calls, each '
                       'advancing the clock. On its normal path it spends them before reaching {target} attempt '
                       '{attempt} (it reached {seen}).',
    'N1_OPTIONAL_READ': 'Not forced: it needs {target} attempt {attempt}, an extra order read. The normal path reads '
                        'the order {seen} time(s).',
    'N2_UNNEEDED_STATUS_CHECK': 'Not forced: it needs {target} attempt {attempt}, but this agent checks status only '
                                'while an operation is pending, or at most {unknown_checks} times after a write failed '
                                'on both attempts; on its normal path it made {seen} such check(s). Only an earlier '
                                'fault that leaves the operation pending or unknown creates more.',
    'N3_REPEATED_WRITE': 'Not forced: it is reached only if the agent sends a write again, but on its normal path '
                         'this agent does not re-send a failed or completed write; after a write fails on both '
                         'attempts it only checks status. It needs {target} attempt {attempt}; the normal path made '
                         '{seen} such attempt(s).',
    'N4_RULE_BREAKING_CALL': 'Not forced: it needs a confirmation although the upgrade did not succeed; the agent '
                             'would have to break the upgrade-before-confirmation rule to reach {target} attempt {attempt}.',
    'N0_NOT_SHOWN_REACHABLE': 'Not forced: no scripted caller within this agent\'s limits reached {target} attempt '
                              '{attempt} (the normal path reached {seen}).',
}


def explain(code, **fields):
    template = TEMPLATES['S2_F4' if code == 'S2' and fields.get('kind') == 'F4' else code]
    return template.format(**fields)


# ---------------------------------------------------------------------------------------
# In-process replay of the real simulator
# ---------------------------------------------------------------------------------------
class _NoSleepAsyncio:
    """Stands in for the module-level ``asyncio`` name inside the private business.py copy."""
    @staticmethod
    async def sleep(_delay, result=None):
        return result


_PRIVATE = None
_PRIVATE_LOCK = threading.Lock()


def _private_business():
    """Execute simulator/business.py once more, privately, with no response sleep.

    The served simulator and every other importer keep the original module; nothing
    global is patched. Relative imports resolve to the shared simulator package.
    """
    global _PRIVATE
    with _PRIVATE_LOCK:
        if _PRIVATE is None:
            from app.simulator import business
            source = Path(business.__file__)
            spec = importlib.util.spec_from_file_location('app.simulator._reachability_business', source)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.asyncio = _NoSleepAsyncio()
            _PRIVATE = (module, content_hash(source.read_text()))
        return _PRIVATE


def _simulator_app(store):
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from app.simulator.storage import WorldError
    module, _ = _private_business()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(WorldError)  # identical to simulator/main.py
    async def world_error(request: Request, error: WorldError):
        return JSONResponse(status_code=error.status, content={'error_code': error.code})
    app.include_router(module.router(store))
    return app


def fixture_for(recipe_json):
    return 'history-v1' if any(p['kind'] == 'F3' for p in recipe_json['primitives']) else 'standard-v1'


@dataclass
class _Replay:
    client: object
    store: object
    recipe: dict
    fixture: str
    caller: CallerModel
    http: int = 0
    ticks: int = 0
    calls: int = 0
    sequence: list = field(default_factory=list)
    observations: list = field(default_factory=list)
    attempts: dict = field(default_factory=dict)
    counters: dict = field(default_factory=dict)
    rule_broken: bool = False

    def __post_init__(self):
        from app.adapters.journal import allocate_intent
        spec = FaultSpec.model_validate(self.recipe)
        self.intent = allocate_intent(REPLAY_ORDER_ID, 'Reachability pre-check replay',
                                      4 if self.fixture == 'history-v1' else 1)
        world = self.store.create(new_id('episode'), self.intent, spec, self.fixture)
        self.world_id, self.capability = world['world_id'], world['capability']
        self.kinds = [p['kind'] for p in self.recipe['primitives']]

    def _request(self, tool, service):
        # The adapter's own request builder: exact paths and write bytes.
        from app.adapters.business_tools import BusinessToolBroker
        args = {'desired_shipping': 'express'} if tool == 'update_order' else {'service': service} if tool == 'get_operation_status' else {}
        method, path, payload, _ = BusinessToolBroker._request(SimpleNamespace(journal=SimpleNamespace(intent=self.intent)), tool, args)
        return method, path, canonical_json(payload) if payload else None

    async def attempt(self, tool, service):
        if self.http >= self.caller.http_attempts or self.ticks >= self.caller.ticks:
            raise _BudgetClosed()
        self.http += 1; self.ticks += 1
        method, path, encoded = self._request(tool, service)
        attempt_id = new_id('attempt')
        headers = {'X-FaultLab-World': self.world_id, 'X-FaultLab-Capability': self.capability,
                   'X-FaultLab-Call': new_id('call'), 'X-FaultLab-Attempt': attempt_id}
        if encoded: headers['Content-Type'] = 'application/json'
        response = await self.client.request(method, path, content=encoded, headers=headers)
        body = response.json()
        state = self.store.read(self.world_id)
        timed_out = any(f['triggered'] and f['attempt_id'] == attempt_id and self.kinds[i] == 'F1'
                        for i, f in enumerate(state['fault_executions']))
        key = f'{tool}:{service}'
        self.counters[key] = self.counters.get(key, 0) + 1
        self.attempts[attempt_id] = (self.calls, key, self.counters[key])
        self.sequence.append(f"{key}#{response.status_code}{'/timeout' if timed_out else ''}")
        if timed_out:
            body = {'transport': 'timeout', 'status': None}
        self.observations.append((tool, service, body))
        return response.status_code, body, timed_out

    async def call(self, tool, service):
        self.calls += 1
        if tool == 'send_confirmation' and self.receipt_status('orders') != 'SUCCEEDED':
            self.rule_broken = True  # a confirmation without a delivered upgrade success (C3)
        last = None
        for _ in range(self.caller.adapter_attempts):
            status, body, timed_out = await self.attempt(tool, service)
            last = body
            if not (timed_out or status in RETRYABLE_STATUS or body.get('error_code') in RETRYABLE_CODES):
                break
        return last

    def receipt_status(self, service):
        for _, svc, body in self.observations:
            data = body.get('data') if isinstance(body, dict) else None
            if (body.get('transport') == 'ok' and isinstance(data, dict) and data.get('service') == service
                    and data.get('receipt')):
                return data['receipt']['status']
        return None

    def latest_status(self, service):
        for _, svc, body in reversed(self.observations):
            if svc == service:
                return body.get('status') if body.get('transport') == 'ok' else None
        return None

    def faults(self):
        return self.store.read(self.world_id)['fault_executions']

    def drop(self):
        try: (Path(self.store.directory) / (self.world_id + '.sqlite3')).unlink()
        except FileNotFoundError: pass


# ---------------------------------------------------------------------------------------
# Scripted callers
# ---------------------------------------------------------------------------------------
async def _resolve(run, service, limit):
    """Check the operation's status once per call until it has a receipt.

    The modelled Actor never sends the write again. While the operation is PENDING it keeps
    checking. A check with no usable answer -- UNKNOWN (a write that failed on both adapter
    attempts was never accepted) or a check that itself failed -- counts toward
    ``caller.unknown_status_checks``; at that many it stops (and reports the task unfinished).
    """
    unresolved = 0
    while run.receipt_status(service) is None and run.calls < limit:
        await run.call('get_operation_status', service)
        if run.receipt_status(service) is None and run.latest_status(service) != 'PENDING':
            unresolved += 1
            if unresolved >= run.caller.unknown_status_checks: break


async def _resolve_with_resend(run, service, limit):
    """Caller v1's resolution: re-send the write after UNKNOWN (explanations only, N3)."""
    write = 'update_order' if service == 'orders' else 'send_confirmation'
    while run.receipt_status(service) is None and run.calls < limit:
        await run.call('get_operation_status', service)
        if run.receipt_status(service) is not None: break
        if run.latest_status(service) == 'UNKNOWN' and run.calls < limit:
            await run.call(write, service)


async def agent_path(run, limit, *, resolve=None):
    """The registered agent's normal path within ``limit`` business calls, no waits."""
    resolve = resolve or _resolve
    await run.call('get_order', 'orders')
    await run.call('update_order', 'orders')
    await resolve(run, 'orders', limit)
    if run.receipt_status('orders') == 'SUCCEEDED' and run.calls < limit:
        await run.call('send_confirmation', 'notifications')
        await resolve(run, 'notifications', limit)


async def resend_path(run, limit):
    """The normal path, except that a write is re-sent after UNKNOWN (explanations only)."""
    await agent_path(run, limit, resolve=_resolve_with_resend)


async def diligent_path(run, limit):
    """Normal path plus optional calls the tool contract allows (explanations only)."""
    async def extras():
        await run.call('get_order', 'orders')
        await run.call('get_operation_status', 'orders')
        await run.call('get_operation_status', 'notifications')
    await run.call('get_order', 'orders')
    await run.call('update_order', 'orders'); await extras()
    await _resolve(run, 'orders', limit)
    await run.call('update_order', 'orders')
    if run.receipt_status('orders') == 'SUCCEEDED':
        await run.call('send_confirmation', 'notifications'); await extras()
        await _resolve(run, 'notifications', limit)
        await run.call('send_confirmation', 'notifications')


async def rule_breaking_path(run, limit, *, early):
    """Confirm although the upgrade has not succeeded (a C3/C4 breach; explanations only)."""
    await run.call('get_order', 'orders')
    await run.call('update_order', 'orders')
    if not early: await _resolve(run, 'orders', limit)
    await run.call('send_confirmation', 'notifications')
    if early: await _resolve(run, 'orders', limit)
    await _resolve(run, 'notifications', limit)


async def targeted_path(run, primitive, *, after_write):
    """Hit the fault's own tool/service repeatedly (explanations only)."""
    repeat = max(window(primitive)) + 1
    if after_write: await run.call('update_order', 'orders')
    for _ in range(repeat):
        await run.call(primitive['target_tool'], primitive['target_service'])


async def _execute(store, client, recipe, fixture, caller, script):
    run = _Replay(client, store, recipe, fixture, caller)
    try:
        try: await script(run)
        except _BudgetClosed: pass
        executions = run.faults()
        fired_on = []
        for f in executions:
            where = run.attempts.get(f['attempt_id']) if f['triggered'] else None
            fired_on.append(where)
        return {'fired': [f['triggered'] for f in executions], 'reasons': [f['reason'] for f in executions],
                'fired_on': fired_on, 'sequence': list(run.sequence), 'business_calls': run.calls,
                'attempts_by_target': dict(run.counters), 'rule_broken': run.rule_broken,
                'upgrade': run.receipt_status('orders'), 'notification': run.receipt_status('notifications')}
    finally:
        run.drop()


def _behaviour_code(primitive, *, uncapped, exhausted, resend, extra, rule_breaking):
    # Out of turns: more calls would reach it, or the normal path used every call before the
    # task could finish (and the upgrade did not fail, which would end the path anyway).
    if uncapped or exhausted: return 'N5_OUT_OF_TURNS'
    # Reached only if a write that failed on both attempts is sent again, which this agent
    # does not do on its normal path.
    if resend: return 'N3_REPEATED_WRITE'
    if extra:
        return {'get_order': 'N1_OPTIONAL_READ', 'get_operation_status': 'N2_UNNEEDED_STATUS_CHECK'}.get(
            primitive['target_tool'], 'N3_REPEATED_WRITE')
    if rule_breaking: return 'N4_RULE_BREAKING_CALL'
    return 'N0_NOT_SHOWN_REACHABLE'


async def _label(recipe_json, caller, work_dir):
    import httpx
    from app.simulator.storage import WorldStore
    store = WorldStore(work_dir)
    fixture = fixture_for(recipe_json)
    app = _simulator_app(store)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://reachability.invalid') as client:
        async def run(script):
            return await _execute(store, client, recipe_json, fixture, caller, script)
        limit = caller.max_business_calls
        agent = await run(lambda r: agent_path(r, limit))
        primitives = recipe_json['primitives']
        rules = fixed_rules(primitives, http_attempts=caller.http_attempts)
        pending = [i for i, p in enumerate(primitives) if rules[i] is None and not agent['fired'][i]]
        uncapped = resent = extra = breaking = None; exhausted = False
        if pending:
            unbounded = caller.http_attempts
            uncapped = await run(lambda r: agent_path(r, unbounded))
            exhausted = (agent['business_calls'] >= limit and agent['notification'] is None
                         and agent['upgrade'] != 'FAILED' and uncapped['upgrade'] != 'FAILED')
            resent = await run(lambda r: resend_path(r, unbounded))
            extra_runs = [await run(lambda r: diligent_path(r, unbounded))]
            for i in pending:
                for after in (False, True):
                    extra_runs.append(await run(lambda r, p=primitives[i], a=after: targeted_path(r, p, after_write=a)))
            breaking_runs = [await run(lambda r, e=e: rule_breaking_path(r, unbounded, early=e)) for e in (False, True)]
            # A run that confirmed without a delivered upgrade success broke a rule, whatever its name.
            compliant = [r for r in extra_runs if not r['rule_broken']]
            breaking_runs += [r for r in extra_runs if r['rule_broken']]
            extra = [any(r['fired'][i] for r in compliant) for i in range(len(primitives))]
            breaking = [any(r['fired'][i] for r in breaking_runs) for i in range(len(primitives))]
    faults = []
    for i, p in enumerate(primitives):
        fields = {'target': target(p), 'attempt': p['occurrence'], 'kind': p['kind'],
                  'max_calls': caller.max_business_calls, 'http_attempts': caller.http_attempts,
                  'unknown_checks': caller.unknown_status_checks,
                  'seen': agent['attempts_by_target'].get(target(p), 0)}
        row = {'index': i, 'fault': describe(p), 'kind': p['kind'], 'target': target(p),
               'attempt': p['occurrence'], 'agent_attempts_seen': fields['seen'], 'rule': rules[i]}
        if rules[i]:
            row.update(verdict='IMPOSSIBLE', reason_code=rules[i], explanation=explain(rules[i], **fields))
        elif agent['fired'][i]:
            call_index, _, _ = agent['fired_on'][i]
            row.update(verdict='FORCED', reason_code='FORCED',
                       explanation=explain('FORCED', call=call_index, **fields))
        else:
            code = _behaviour_code(p, uncapped=uncapped['fired'][i], exhausted=exhausted, resend=resent['fired'][i],
                                   extra=extra[i], rule_breaking=breaking[i])
            row.update(verdict='NOT_FORCED', reason_code=code, explanation=explain(code, **fields))
        faults.append(row)
    _, business_hash = _private_business()
    return {'labeller': LABELLER_VERSION, 'caller_model': caller.descriptor(),
            'simulator_business_source_hash': business_hash, 'fixture_id': fixture,
            'recipe': readable_recipe(recipe_json), 'faults': faults,
            'all_forced': all(f['verdict'] == 'FORCED' for f in faults),
            'agent_path': agent['sequence'], 'agent_business_calls': agent['business_calls'],
            'agent_outcome': {'upgrade': agent['upgrade'], 'notification': agent['notification']}}


def label_recipe(recipe, caller, *, work_dir=None):
    """Label every fault of ``recipe`` (FaultSpec or its JSON). Blocking; never on the lab loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError('The reachability replay must not run on an event loop thread; use label_recipe_async')
    recipe_json = recipe.model_dump(mode='json') if isinstance(recipe, FaultSpec) else FaultSpec.model_validate(recipe).model_dump(mode='json')
    if work_dir is not None:
        return asyncio.run(_label(recipe_json, caller, Path(work_dir)))
    with tempfile.TemporaryDirectory(prefix='faultlab-reachability-') as directory:
        return asyncio.run(_label(recipe_json, caller, Path(directory)))


async def label_recipe_async(recipe, caller, *, work_dir=None):
    """Run the replay in a worker thread so the lab's event loop is never blocked."""
    return await asyncio.to_thread(label_recipe, recipe, caller, work_dir=work_dir)


def normal_path(caller, *, work_dir=None):
    """The agent's path with no fault, as a list of tool:service calls, for the Explorer."""
    healthy = label_recipe(FaultSpec(seed=0, primitives=[]), caller, work_dir=work_dir)
    calls = []
    for token in healthy['agent_path']:
        name = token.split('#', 1)[0]
        calls.append(name)
    return {'calls': calls, 'business_calls': healthy['agent_business_calls'],
            'max_business_calls': caller.max_business_calls}


# ---------------------------------------------------------------------------------------
# Plain explanations for executed episodes (what fired, what did not, and why)
# ---------------------------------------------------------------------------------------
EXECUTED_TEMPLATES = {
    'FIRED': 'Fired on {target} attempt {attempt}.',
    'EPISODE_ENDED_EARLY': 'Did not fire: the episode ended early ({lifecycle}) before {target} attempt {attempt}.',
    'AGENT_SKIPPED_CALL': 'Did not fire: it needed {target} attempt {attempt}, and the agent made {seen} such '
                          'attempt(s). The pre-check predicted this attempt on the normal path, so the agent left '
                          'that path (for example it stopped before sending the confirmation).',
    'REACHED_BUT_NOT_TRIGGERED': 'Did not fire although {target} attempt {attempt} happened ({seen} attempts); the '
                                 'simulator recorded "{reason}". This contradicts the pre-check and is a FaultLab '
                                 'labelling problem to investigate, not an agent mistake.',
    'PREVENTED_ON_REACHED_ATTEMPT': 'Did not fire although {target} attempt {attempt} happened ({seen} attempts); '
                                    'the simulator recorded "{reason}".',
    'NOT_REACHED': 'Did not fire: it needed {target} attempt {attempt}, and the agent made {seen} such attempt(s).',
}


def explain_executed(recipe_json, *, fired, reasons, attempts_by_target, lifecycle, predicted=None):
    """Per-fault result for one executed episode, using only public counts and fault records."""
    rows = []
    for i, p in enumerate(recipe_json['primitives']):
        seen = attempts_by_target.get(target(p), 0)
        fields = {'target': target(p), 'attempt': p['occurrence'], 'seen': seen, 'lifecycle': lifecycle,
                  'reason': (reasons[i] if i < len(reasons) else None) or 'no reason'}
        was = fired[i] if i < len(fired) else None
        forced = bool(predicted) and i < len(predicted) and predicted[i] == 'FORCED'
        if was:
            code = 'FIRED'
        elif lifecycle != 'COMPLETED':
            code = 'EPISODE_ENDED_EARLY'
        elif seen >= p['occurrence']:
            code = 'REACHED_BUT_NOT_TRIGGERED' if forced else 'PREVENTED_ON_REACHED_ATTEMPT'
        elif forced:
            code = 'AGENT_SKIPPED_CALL'
        else:
            code = 'NOT_REACHED'
        rows.append({'index': i, 'fault': describe(p), 'fired': bool(was), 'reason_code': code,
                     'explanation': EXECUTED_TEMPLATES[code].format(**fields),
                     'target': target(p), 'needed_attempt': p['occurrence'], 'attempts_seen': seen,
                     'predicted': predicted[i] if predicted and i < len(predicted) else None})
    return rows

"""Product reviewer's offline server for the two loop-limit rules: the REAL backend API over HTTP on a loopback port,
with only the model transport (and, for two declared scenarios, the size of evidence rows) scripted. $0: no provider,
model, W&B, Weave or network call.

Run from faultlab/backend:
    ../.venv/bin/python -B ../artifacts/product-loop-limits-2026-09-30/review-product/serve_offline.py <scratch_dir> <port>

Real: the FastAPI backend (app.main.create_app), coordinator, run plans (new Learn plans freeze both rules), the learning
loop, Reproducer, reduction, Diagnostician, Challenger, the Mechanic/Explorer agent code (prompt building, admission
count, output validation), app.lab.loop_limits, the policy interpreter, the native smolagents adapter v2, the in-process
simulator and a fresh scratch store outside the Desktop.

Scripted (declared fixture behaviour, not model evidence):
* Actor: the tests' priced native fixture (PricedNativeInputs('accepted'): confirms before the upgrade finishes).
* Explorer, discovery: every request picks a 4-tick delayed upgrade (seed 27).
* Explorer, challenge: per campaign scenario (scenarios.json in the scratch dir, written by the driver before Start):
    reach      : request 1 = F4 on get_operation_status (notifications); then 3-,4-,5-,6-tick delayed upgrades.
    policyread : request 1 = F2 3-tick delayed upgrade + F4 on get_operation_status (orders), request 2 (its re-plan)
                 the same pick again; then 4-,5-,6-,7-tick delayed upgrades.
    norule     : same answers as policyread, but the harness withholds the plan's challenge rule from the loop
                 (simulating a plan saved before it) so the combined pick runs and we can see whether it fires.
    compact    : 3-,4-,5-tick delayed upgrades, then invalid text (so the challenge ends INCONCLUSIVE, as in v2d).
    unfit      : never reached (the candidate search ends before any challenge).
* Mechanic: diagnosis asks for the first offered intervention (POLICY_GAP); the first candidate request of a source gets
  the tests' reference reconciliation policy (reference_policy, not weak); every later candidate request gets NO_CHANGE.
* Evidence rows (compact and unfit scenarios only): the evidence the loop reads is padded AFTER the real read, by adding
  synthetic event ids to each check row (CheckResult.event_ids, schema max 100):
    compact : clean episodes of purposes intervention/source_validation/challenge get 20 ids per check;
    unfit   : every episode of purposes intervention/source_validation/challenge gets 100 ids per check.
  Discovery and reproduction episodes (the source and its reproductions) are never padded, so diagnosis fits.
  Stored records are not changed; only the bundles handed to the loop are.
* Weave: the tests' local double (StudyRemoteDouble).
Declared stop point: the protected promotion comparison is never run (StopRequested before any promotion case loads).
A socket guard refuses every non-loopback connection and name lookup (refused.json). Every Explorer/Mechanic request is
appended to lab_messages.jsonl with its admission count (the same frozen tokenizer the product uses).
"""
import asyncio
import json
import socket
import sys
from pathlib import Path

BACKEND = Path.cwd()
sys.path[:0] = [str(BACKEND), str(BACKEND / 'tests'), str(BACKEND / 'tests' / 'lab')]
import conftest  # noqa: F401,E402  (audit hook refusing the real .env; dotenv disabled)

SCRATCH = Path(sys.argv[1]).resolve()
PORT = int(sys.argv[2])
assert not str(SCRATCH).startswith('/Users/shree/Desktop'), 'scratch must be outside the synced Desktop'
SCRATCH.mkdir(parents=True, exist_ok=True)
REFUSED = []
LOOPBACK = {'127.0.0.1', '::1', 'localhost'}
_connect = socket.socket.connect
_getaddrinfo = socket.getaddrinfo


def _write_refused():
    (SCRATCH / 'refused.json').write_text(json.dumps(REFUSED))


def _guarded_connect(sock, address):
    if sock.family == socket.AF_UNIX or (isinstance(address, tuple) and address[0] in LOOPBACK):
        return _connect(sock, address)
    REFUSED.append(repr(address)); _write_refused()
    raise RuntimeError('review server refuses non-loopback connections')


def _guarded_getaddrinfo(host, *args, **kwargs):
    if host is None or (host.decode() if isinstance(host, bytes) else host) in LOOPBACK:
        return _getaddrinfo(host, *args, **kwargs)
    REFUSED.append(repr(host)); _write_refused()
    raise OSError('review server refuses non-loopback name lookups')


socket.socket.connect = _guarded_connect
socket.getaddrinfo = _guarded_getaddrinfo
_write_refused()

import httpx  # noqa: E402
import uvicorn  # noqa: E402

from app.adapters.business_tools import WorldClient  # noqa: E402
from app.contracts.models import canonical_json  # noqa: E402
from app.contracts.tokens import input_token_bound  # noqa: E402
from app.lab import learning, loop_limits  # noqa: E402
from app.lab.budgets import StopRequested  # noqa: E402
from app.lab.coordinator import LabCoordinator  # noqa: E402
from app.lab.evidence import EvidenceGateway  # noqa: E402
from app.lab.runner import EpisodeRunner  # noqa: E402
from app.providers.runtime import RuntimeGeneration  # noqa: E402
from app.simulator.main import create_app as simulator_app  # noqa: E402
from app.telemetry.evaluations import EvaluationPublisher  # noqa: E402
from app.telemetry.outbox import TelemetryOutbox  # noqa: E402
from app.telemetry.tracing import TraceRecorder  # noqa: E402
from original_loop_fixture import CONTROL, delayed_upgrade, reference_policy  # noqa: E402
from test_baseline_study import StudyRemoteDouble  # noqa: E402
from test_native_baseline_study_planned import IN_TOKENS, OUT_TOKENS, PricedNativeInputs, plan_settings  # noqa: E402

REASONING_MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
MESSAGES = SCRATCH / 'lab_messages.jsonl'
SCENARIOS = SCRATCH / 'scenarios.json'


def scenario(campaign_id):
    try: return json.loads(SCENARIOS.read_text()).get(campaign_id)
    except FileNotFoundError: return None


def F4(tool, service, count=1):
    return {'kind': 'F4', 'target_tool': tool, 'target_service': service, 'occurrence': 1, 'parameters': {'failure_count': count}}


def combined(delay=3):
    spec = delayed_upgrade(delay); spec['seed'] = 41
    spec['primitives'] = spec['primitives'] + [F4('get_operation_status', 'orders')]
    return spec


CHALLENGE = {
    'reach': lambda n: {'seed': 51, 'primitives': [F4('get_operation_status', 'notifications')]} if n == 1 else delayed_upgrade(n + 1),
    'policyread': lambda n: combined() if n <= 2 else delayed_upgrade(n + 1),
    'norule': lambda n: combined() if n <= 2 else delayed_upgrade(n + 1),
    'compact': lambda n: delayed_upgrade(n + 2) if n <= 3 else None,
    'unfit': lambda n: delayed_upgrade(n + 2),
}


class ReviewProvider(PricedNativeInputs):
    def __init__(self):
        super().__init__('accepted')
        self.challenge_requests = {}

    async def complete(self, messages, *, role='actor', **kwargs):
        if role == 'actor':
            return await super().complete(messages, role=role, **kwargs)
        self.calls[role] += 1
        context = json.loads(messages[-1]['content'])
        campaign_id = context.get('campaign_id')
        text = None
        if role == 'explorer' and context.get('purpose') == 'challenge':
            key = (campaign_id, context.get('candidate_hash'))
            n = self.challenge_requests[key] = self.challenge_requests.get(key, 0) + 1
            spec = CHALLENGE[scenario(campaign_id) or 'reach'](n)
            answer = None if spec is None else {'fault_spec': spec, 'hypothesis': f'Handwritten review fixture (challenge request {n}).'}
            if answer is None: text = 'not json (review fixture: invalid challenge answer)'
        elif role == 'explorer':
            answer = {'fault_spec': delayed_upgrade(4), 'hypothesis': 'Handwritten review fixture: a 4-tick delayed upgrade.'}
        elif 'intervention_ids' in context:
            answer = {'proposed_kind': 'POLICY_GAP', 'hypothesis': 'Handwritten review fixture: diagnosis.',
                      'evidence_ids': context['evidence_ids'][:1], 'requested_intervention_id': context['intervention_ids'][0]}
        elif context.get('candidate_history'):
            answer = {'no_change_reason': 'Review fixture has no further handwritten candidate.'}
        else:
            answer = {'candidate': reference_policy(context['parent_version']),
                      'explanation': 'HANDWRITTEN REVIEW FIXTURE (tests reference reconciliation policy), not generated learning.'}
        content = text if answer is None else canonical_json(answer)
        with MESSAGES.open('a') as handle:
            handle.write(json.dumps({'role': role, 'campaign_id': campaign_id, 'purpose': context.get('purpose'),
                                     'proposal_index': context.get('proposal_index'), 'slot_request': context.get('slot_request'),
                                     'kind': 'diagnosis' if 'intervention_ids' in context else 'candidate' if role == 'mechanic' else role,
                                     'dispatched_tokens': input_token_bound(messages, REASONING_MODEL),
                                     'messages': messages, 'answer': content}) + '\n')
        return RuntimeGeneration(content, REASONING_MODEL, IN_TOKENS, OUT_TOKENS, 0.0)


_load_cases = learning.load_cases


def _guarded_load_cases(split, *args, **kwargs):
    if split == 'promotion':
        raise StopRequested('Review stop point: the protected promotion comparison is not run in this offline review')
    return _load_cases(split, *args, **kwargs)


learning.load_cases = _guarded_load_cases

_rule = loop_limits.challenge_selection_rule


def _challenge_rule(store, campaign):
    if scenario(campaign.campaign_id) == 'norule':
        return None   # declared: this scenario simulates a plan saved before the rule
    return _rule(store, campaign)


loop_limits.challenge_selection_rule = _challenge_rule


class PaddedEvidence:
    """Wraps the real EvidenceGateway; pads check rows of the bundles handed to the loop (compact/unfit only)."""
    def __init__(self, real, store):
        self.real, self.store = real, store

    def __getattr__(self, name):
        return getattr(self.real, name)

    async def get(self, episode_id, context, **kwargs):
        bundle = await self.real.get(episode_id, context, **kwargs)
        episode = self.store.get_record('episodes', episode_id) or {}
        mode = scenario(episode.get('campaign_id'))
        if mode not in ('compact', 'unfit') or episode.get('experiment_purpose') not in ('intervention', 'source_validation', 'challenge'):
            return bundle
        failed = any(not f.passed for f in bundle.findings)
        per_check = 100 if mode == 'unfit' else (0 if failed else 20)
        if not per_check:
            return bundle
        findings = [f.model_copy(update={'event_ids': list(f.event_ids) + [f'event-pad{episode_id[-12:]}{f.check_id}{n:03d}' for n in range(per_check)][:100]})
                    for f in bundle.findings]
        return bundle.model_copy(update={'findings': findings})


def build():
    settings = plan_settings(SCRATCH / 'lab')
    c = LabCoordinator(settings)
    simulator = simulator_app(database_dir=SCRATCH / 'worlds', control_token=CONTROL, settings=settings)
    world = httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator), base_url='http://127.0.0.1:8001')
    remote = StudyRemoteDouble(); outbox = TelemetryOutbox(c.store); trace = TraceRecorder(remote, outbox)
    c.runner = EpisodeRunner(c.store, WorldClient('http://127.0.0.1:8001', CONTROL, client=world), ReviewProvider(), trace=trace)
    c.evidence_gateway = PaddedEvidence(EvidenceGateway(c.store, 'entity/project', trace=trace, worker=remote), c.store)
    c.evaluation_publisher = EvaluationPublisher(remote, outbox)
    from app.main import create_app as backend_app
    return backend_app(coordinator=c)


if __name__ == '__main__':
    app = build()
    uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=PORT, log_level='warning')).run()

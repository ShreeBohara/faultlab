"""Product reviewer's offline server for discovery v4 (history replay): the REAL backend API over HTTP on a loopback
port, with only the model transport scripted. $0: no provider, model, W&B, Weave or network call.

Run from faultlab/backend:
    ../.venv/bin/python ../artifacts/product-discovery-v4-2026-09-30/review-product/serve_offline.py <scratch_dir> <port>

What is real: the FastAPI backend (app.main.create_app), the lab coordinator, run plans, the learning loop, the
Reproducer, reduction, the Diagnostician, the Mechanic/Explorer agent code (prompt building and output validation),
the policy interpreter, the native smolagents adapter v2, the in-process simulator and the store (a fresh scratch store
outside the Desktop).
What is scripted (declared, fixture behaviour, not model evidence):
* the model transport (tests' NativeReferenceInputs for the Actor: a pure function of the public observations that
  sends the confirmation before the upgrade finishes; a handwritten Explorer and Mechanic);
* Weave: the tests' local double (StudyRemoteDouble).
Scripted Explorer (discovery): the first discovery request of each campaign picks dev-5's public recipe with seed 999
(under v4 with dev-5 replayed this must be SKIPPED_DUPLICATE); every later request picks a 4-tick delayed upgrade.
Scripted Explorer (challenge): 3/4/5/6-tick delayed upgrades. Scripted Mechanic: diagnosis requests the first offered
intervention (POLICY_GAP); the first candidate for a source is a deliberately weak handwritten policy (read the order
before the final report), then NO_CHANGE.
Declared stop point: if the loop ever reaches the protected promotion comparison, StopRequested is raised before any
promotion case is loaded (the scripted weak candidate is not expected to get that far).
A socket guard refuses every non-loopback connection and name lookup; refusals are written to <scratch>/refused.json.
Every Explorer/Mechanic message is appended to <scratch>/lab_messages.jsonl.
"""
import asyncio
import json
import socket
import sys
from pathlib import Path

BACKEND = Path.cwd()
sys.path[:0] = [str(BACKEND), str(BACKEND / 'tests'), str(BACKEND / 'tests' / 'lab')]
import conftest  # noqa: F401,E402  (audit hook refusing the real .env; dotenv disabled; simulator imported offline)

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
from app.lab import learning  # noqa: E402
from app.lab.budgets import StopRequested  # noqa: E402
from app.lab.coordinator import LabCoordinator  # noqa: E402
from app.lab.evidence import EvidenceGateway  # noqa: E402
from app.lab.runner import EpisodeRunner  # noqa: E402
from app.providers.runtime import RuntimeGeneration  # noqa: E402
from app.referee.manifests import development_case  # noqa: E402
from app.simulator.main import create_app as simulator_app  # noqa: E402
from app.telemetry.evaluations import EvaluationPublisher  # noqa: E402
from app.telemetry.outbox import TelemetryOutbox  # noqa: E402
from app.telemetry.tracing import TraceRecorder  # noqa: E402
from original_loop_fixture import CONTROL, delayed_upgrade, reference_policy  # noqa: E402
from test_baseline_study import StudyRemoteDouble  # noqa: E402
from test_native_baseline_study_planned import IN_TOKENS, OUT_TOKENS, PricedNativeInputs, plan_settings  # noqa: E402

REASONING_MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
MESSAGES = SCRATCH / 'lab_messages.jsonl'


class ReviewProvider(PricedNativeInputs):
    """Actor: the tests' priced native fixture. Explorer and Mechanic: handwritten answers (declared above)."""
    def __init__(self):
        super().__init__('accepted')
        self.discovery_requests = {}

    async def complete(self, messages, *, role='actor', **kwargs):
        if role == 'actor':
            return await super().complete(messages, role=role, **kwargs)
        self.calls[role] += 1
        context = json.loads(messages[-1]['content'])
        campaign_id = context.get('campaign_id')
        if role == 'explorer' and context.get('purpose') == 'challenge':
            answer = {'fault_spec': delayed_upgrade((3, 4, 5, 6)[context.get('proposal_index', 0) % 4]),
                      'hypothesis': 'Handwritten review fixture (challenge).'}
        elif role == 'explorer':
            count = self.discovery_requests[campaign_id] = self.discovery_requests.get(campaign_id, 0) + 1
            if count == 1:
                dev5 = development_case('dev-5')['fault_spec']
                answer = {'fault_spec': {'seed': 999, 'primitives': dev5['primitives']},
                          'hypothesis': 'Handwritten review fixture: re-pick the rejected-upgrade recipe (seed 999).'}
            else:
                answer = {'fault_spec': delayed_upgrade(4), 'hypothesis': 'Handwritten review fixture: a 4-tick delayed upgrade.'}
        elif 'intervention_ids' in context:
            answer = {'proposed_kind': 'POLICY_GAP', 'hypothesis': 'Handwritten review fixture: diagnosis.',
                      'evidence_ids': context['evidence_ids'][:1], 'requested_intervention_id': context['intervention_ids'][0]}
        elif context.get('candidate_history') or (SCRATCH / 'mechanic_no_change_first').exists():
            # Mode file present: NO_CHANGE at the first candidate request, so each source uses one of the 4 candidate
            # requests and the discovery loop can reach the Explorer's slots.
            answer = {'no_change_reason': 'Review fixture has no further handwritten candidate.'}
        else:
            answer = {'candidate': reference_policy(context['parent_version'], weak=True),
                      'explanation': 'HANDWRITTEN REVIEW FIXTURE, deliberately weak, not generated learning.'}
        with MESSAGES.open('a') as handle:
            handle.write(json.dumps({'role': role, 'campaign_id': campaign_id, 'selection_index': context.get('selection_index'),
                                     'purpose': context.get('purpose'), 'messages': messages, 'answer': answer}) + '\n')
        return RuntimeGeneration(canonical_json(answer), REASONING_MODEL, IN_TOKENS, OUT_TOKENS, 0.0)


_load_cases = learning.load_cases


def _guarded_load_cases(split, *args, **kwargs):
    if split == 'promotion':
        raise StopRequested('Review stop point: the protected promotion comparison is not run in this offline review')
    return _load_cases(split, *args, **kwargs)


learning.load_cases = _guarded_load_cases


def build():
    settings = plan_settings(SCRATCH / 'lab')
    c = LabCoordinator(settings)
    simulator = simulator_app(database_dir=SCRATCH / 'worlds', control_token=CONTROL, settings=settings)
    world = httpx.AsyncClient(transport=httpx.ASGITransport(app=simulator), base_url='http://127.0.0.1:8001')
    remote = StudyRemoteDouble(); outbox = TelemetryOutbox(c.store); trace = TraceRecorder(remote, outbox)
    c.runner = EpisodeRunner(c.store, WorldClient('http://127.0.0.1:8001', CONTROL, client=world), ReviewProvider(), trace=trace)
    c.evidence_gateway = EvidenceGateway(c.store, 'entity/project', trace=trace, worker=remote)
    c.evaluation_publisher = EvaluationPublisher(remote, outbox)
    from app.main import create_app as backend_app
    return backend_app(coordinator=c)


if __name__ == '__main__':
    app = build()
    uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=PORT, log_level='warning')).run()

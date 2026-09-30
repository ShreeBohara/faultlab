"""Integrity review ($0): what the Rule 1 record says in edge cases the builder's tests assert only partly.

Run from faultlab/backend:  ../.venv/bin/python -B ../artifacts/product-diagnosis-rules-2026-09-30/review-integrity/record_edge_cases.py

Uses the builder's own test helpers (tests/lab/test_diagnosis_rules.py: scripted provider, deterministic runner, real
Mechanic, real Diagnostician, real classify_policy_gap). Stores are temporary folders outside the Desktop, deleted after.
A strict guard refuses any .env open and any INET socket.
"""
import asyncio
import functools
import json
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
BACKEND = Path(__file__).resolve().parents[3] / 'backend'
sys.path[:0] = [str(BACKEND), str(BACKEND / 'tests'), str(BACKEND / 'tests' / 'lab')]
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
VIOLATIONS = []


def _audit(event, args):
    if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)) and os.path.basename(os.fsdecode(args[0])) == '.env':
        VIOLATIONS.append(('env-open', os.fsdecode(args[0])))
        raise PermissionError('review guard: .env open refused')


sys.addaudithook(_audit)
_init = socket.socket.__init__


def _guarded(self, family=-1, type=-1, proto=-1, fileno=None):
    if family in (socket.AF_INET, socket.AF_INET6):
        VIOLATIONS.append(('inet-socket', family))
        raise PermissionError('review guard: INET socket refused')
    return _init(self, family, type, proto, fileno)


socket.socket.__init__ = _guarded

import test_diagnosis_rules as t  # noqa: E402
import app.lab.diagnosis as diagnosis  # noqa: E402
from app.agents.mechanic import Mechanic  # noqa: E402
from app.lab import diagnosis_protocol  # noqa: E402
from app.lab.diagnosis import Diagnostician  # noqa: E402
from app.lab.storage import LabStore  # noqa: E402
from types import SimpleNamespace  # noqa: E402


async def run_case(folder, label, *, answers, mode='SUPPORTED', stop=lambda: False, preflight_reject=False):
    original = diagnosis.run_interventions
    if preflight_reject:
        diagnosis.run_interventions = functools.partial(original, validate=lambda recipe: False)
    try:
        store, provider, ledger = LabStore(Path(folder) / f'{label}.db'), t.Provider(list(answers)), t.Ledger()
        mechanic = Mechanic(provider, store, ledger)
        mechanic.diagnosis_protocol = diagnosis_protocol.declaration()
        chain = diagnosis_protocol.RecordingDiagnosisMechanic(mechanic, mechanic)
        counter = SimpleNamespace(counterexample_id='counterexample-fixture', target_invariant='C3', attempted_count=3,
                                  valid_count=3, target_violation_count=3)
        diagnostic, run = await Diagnostician(store, t.Runner(mode), ledger, chain).run(
            t.CAMPAIGN, counter, t.RECIPE, t.POLICY, t.reproduction(True), evidence=t.EVIDENCE, stop=stop)
        record = diagnosis_protocol.record(store, t.CAMPAIGN, counter, diagnostic, run, chain)
        store.close()
    finally:
        diagnosis.run_interventions = original
    return {'verdict': diagnostic.kind, 'proposal_status': record['proposal_status'], 'intervention_ran': record['intervention_ran'],
            'fresh_intervention_trials': record['fresh_intervention_trials'], 'interventions': record['interventions'],
            'statement': record['statement']}


async def main():
    folder = tempfile.mkdtemp(prefix='review-integrity-record-', dir='/Users/shree/FaultLab_Scratch' if Path('/Users/shree/FaultLab_Scratch').exists() else None)
    assert 'Desktop' not in folder
    out = {}
    try:
        out['preflight_rejected'] = await run_case(folder, 'preflight', answers=t.ANSWERS['valid_request'], preflight_reject=True)
        out['stopped_before_trials'] = await run_case(folder, 'stopped', answers=t.ANSWERS['valid_request'], stop=lambda: True)
        out['supported'] = await run_case(folder, 'supported', answers=t.ANSWERS['valid_request'])
    finally:
        shutil.rmtree(folder)
    out['scratch_deleted'] = not Path(folder).exists()
    out['guard_violations'] = VIOLATIONS
    print(json.dumps(out, indent=1, sort_keys=True))


asyncio.run(main())

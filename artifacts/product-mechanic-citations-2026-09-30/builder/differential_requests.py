"""Differential check ($0, offline): for plans WITHOUT the native citation-status rule, the learning loop of this build
sends exactly the requests the backup build (backup/part2-2026-09-22, learning.py at d38c0b8) sends.

Run from faultlab/backend with the project .venv:
  ../.venv/bin/python -B ../artifacts/product-mechanic-citations-2026-09-30/builder/differential_requests.py OUT.json

For each scenario it runs the same scripted offline learning loop twice: once with the backup tree's learning.py
(loaded from git, read-only) and once with this tree's learning.py. It keeps every Mechanic request (the full message
list the real Mechanic hands to the provider) and every Explorer context (discovery and challenge), replaces the random
IDs (prefix-<32 hex>), 64-hex hashes (some are hashes over those IDs) and timestamps by positional placeholders, and
compares the two runs byte for byte.
Scenarios: the reference Actor's runtime contract, a native adapter v1 contract, and a native adapter v2 contract
(a v2 plan saved before the rule), each with (a) a candidate that fails the challenge and a second candidate request,
and (b) the real Diagnostician's diagnosis request. A positive control runs this tree with the rule declared and must
differ (the block and the memory pointer). Scratch stores live under /Users/shree/FaultLab_Scratch/ and are deleted.
"""
import asyncio
import json
import re
import shutil
import subprocess
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401  (refuses .env and outbound connections; adds backend and backend/tests to sys.path)
sys.path.insert(0, str(Path.cwd() / 'tests' / 'lab'))

import pytest  # noqa: E402
import app.lab  # noqa: E402
import app.lab.learning as current_learning  # noqa: E402
from app.agents.actor import ACTOR_PROMPT  # noqa: E402
from app.lab.diagnosis import V2_MEMORY  # noqa: E402
import test_citation_status as fixtures  # noqa: E402

ROOT = Path.cwd().parent
SCRATCH = Path('/Users/shree/FaultLab_Scratch/mechanic-citations-builder/differential')
REF = 'backup/part2-2026-09-22'
V1_MEMORY = 'Fresh native agent and empty native memory for each episode; original reports cite full delivered evidence IDs.'


def backup_learning():
    source = subprocess.run(['git', 'show', f'{REF}:backend/app/lab/learning.py'], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    module = types.ModuleType('app.lab.learning'); module.__file__ = f'{REF}:backend/app/lab/learning.py'; module.__package__ = 'app.lab'
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module, source


def contract(kind):
    if kind == 'reference': return None                      # the real runtime_contract (no plan: the reference Actor prompt)
    memory = V1_MEMORY if kind == 'native-v1' else V2_MEMORY
    return lambda store=None, campaign=None: {'actor_contract': {'implementation': f'fixture: {kind}', 'memory': memory}, 'episode_limits': {'actor_calls': 8}}


def normalise(value):
    text = json.dumps(value, sort_keys=True)
    names = {}
    def swap(match):
        return names.setdefault(match.group(0), f'{match.group(1)}-ID{len(names) + 1:04d}')
    text = re.sub(r'\b([a-z][a-z0-9_]*(?:-[a-z][a-z0-9_]*)*)-[0-9a-f]{32}\b', swap, text)
    # 64-hex content hashes over those random IDs (for example source_context_id) differ between runs too; they are
    # replaced positionally as well, so equal hashes stay equal and different ones stay different within one run.
    hashes = {}
    text = re.sub(r'\b[0-9a-f]{64}\b', lambda m: hashes.setdefault(m.group(0), f'HASH{len(hashes) + 1:04d}'), text)
    text = re.sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?', 'TIMESTAMP', text)
    return text


async def run(module, tmp, kind, part, *, declared=False):
    """One scripted learning loop with the given learning module installed as app.lab.learning."""
    saved_module, saved_attr = sys.modules.get('app.lab.learning'), getattr(app.lab, 'learning', None)
    sys.modules['app.lab.learning'] = module; app.lab.learning = module
    monkeypatch = pytest.MonkeyPatch()
    try:
        options = {'challenge_failure': True} if part == 'candidate' else {}
        outputs = [fixtures.candidate_json(), fixtures.NO_CHANGE] if part == 'candidate' else [fixtures.diagnosis_answer]
        c, campaign, runner, provider, explorer_contexts = fixtures.native_loop(tmp, monkeypatch, outputs, declared=declared,
                                                                                real_diagnosis=part == 'diagnosis', **options)
        replacement = contract(kind)
        if replacement is None:
            import app.lab.diagnosis as diagnosis
            from app.lab.diagnosis import runtime_contract
            monkeypatch.setattr(module, 'runtime_contract', runtime_contract); monkeypatch.setattr(diagnosis, 'runtime_contract', runtime_contract)
        else:
            import app.lab.diagnosis as diagnosis
            monkeypatch.setattr(module, 'runtime_contract', replacement); monkeypatch.setattr(diagnosis, 'runtime_contract', replacement)
        await module.run_learning_cycle(c, campaign, runner)
        state = c.get(campaign.campaign_id).state
        return {'state': state, 'mechanic_requests': provider.requests, 'explorer_contexts': explorer_contexts}
    finally:
        monkeypatch.undo()
        sys.modules['app.lab.learning'] = saved_module; app.lab.learning = saved_attr


async def main(out):
    old, source = backup_learning()
    results = {'reference': REF, 'backup_learning_py_lines': len(source.splitlines()), 'scenarios': []}
    SCRATCH.mkdir(parents=True, exist_ok=True)
    try:
        for kind in ('reference', 'native-v1', 'native-v2-plan-before-the-rule'):
            for part in ('candidate', 'diagnosis'):
                runs = {}
                for name, module in (('backup', old), ('this_build', current_learning)):
                    tmp = SCRATCH / f'{kind}-{part}-{name}'; tmp.mkdir(parents=True)
                    runs[name] = await run(module, tmp, 'native-v2' if kind.startswith('native-v2') else kind, part)
                a, b = normalise(runs['backup']), normalise(runs['this_build'])
                results['scenarios'].append({
                    'contract': kind, 'part': part, 'final_state': runs['this_build']['state'],
                    'mechanic_requests': len(runs['this_build']['mechanic_requests']),
                    'explorer_contexts': len(runs['this_build']['explorer_contexts']),
                    'challenge_explorer_contexts': sum(1 for challenge, _ in runs['this_build']['explorer_contexts'] if challenge),
                    'byte_identical_after_id_normalisation': a == b, 'normalised_bytes': len(b),
                    'block_anywhere': 'native_citation_status' in b})
        # Positive control: this build with the rule declared differs (the block and the pointer appear).
        tmp = SCRATCH / 'control-declared'; tmp.mkdir(parents=True)
        declared = await run(current_learning, tmp, 'native-v2', 'candidate', declared=True)
        tmp = SCRATCH / 'control-backup'; tmp.mkdir(parents=True)
        backup = await run(old, tmp, 'native-v2', 'candidate')
        text = normalise(declared)
        results['positive_control'] = {'differs_from_backup': text != normalise(backup), 'block_present': 'native_citation_status' in text,
                                       'pointer_present': 'native_citation_status block lists' in text}
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        results['scratch_deleted'] = not SCRATCH.exists()
    results['all_identical'] = all(s['byte_identical_after_id_normalisation'] and not s['block_anywhere'] for s in results['scenarios'])
    Path(out).write_text(json.dumps(results, indent=1, sort_keys=True) + '\n')
    print(json.dumps(results, indent=1, sort_keys=True))


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1]))

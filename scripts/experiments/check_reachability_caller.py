"""Gate before a discovery-v2 run ($0, read-only): does the pre-check's caller model match
what the real Actor actually did?

The reachability pre-check (backend/app/lab/reachability.py) labels a fault FORCED when the
modelled Actor's normal path reaches the fault's tool/service attempt. If the model predicts
an attempt that the real Actor rarely makes, a fault placed there is called FORCED although
it would rarely fire, and a paid episode is wasted. This gate measures exactly that.

For every stored development episode in scope (the reference Actor driven by ``--model``,
baseline policy-v0, lifecycle COMPLETED, with its matching non-diagnostic world file), the
episode's own recipe is labelled with the INSTALLED caller model. Each modelled attempt
``n`` on each tool:service of that path is a hypothetical FORCED point: a fault placed on
attempt ``n`` would be labelled FORCED. The gate counts, per recipe, how many stored
episodes actually reached attempt ``n`` on that tool:service.

    PASS  every point seen in at least ``--min-episodes`` (10) stored episodes was reached in
          at least ``--min-rate`` (80%) of them.
    FAIL  otherwise (exit status 1). No data at all is exit status 2.

Read-only: lab stores and world files are opened with ``mode=ro&immutable=1`` (no -wal or
-shm writes). No heldout2 path, promotion manifest, final-audit file, referee checks module
or .env is opened. The labeller replays the real simulator in-process on a temporary
directory; there is no port, network, provider or model call.

Usage (from the repository root):
    .venv/bin/python scripts/experiments/check_reachability_caller.py --out /path/to/result.json
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / 'backend') not in sys.path:
    sys.path.insert(0, str(ROOT / 'backend'))

DEFAULT_MODEL = 'deepseek-ai/DeepSeek-V3.1'
MIN_EPISODES = 10
MIN_RATE = 0.80
RUNS = Path('/Users/shree/FaultLab_Runs/2026-09-27/product-loop')
DEFAULT_STORES = {
    'main': ROOT / 'artifacts/lab.sqlite3',
    'phase20': ROOT / 'artifacts/phase20-2026-09-23/run-1/lab.sqlite3',
    'phase26': ROOT / 'artifacts/phase26-2026-09-24/run-1/lab.sqlite3',
    'c701e850': RUNS / 'lab.sqlite3',
    'runtime-replication': ROOT / 'artifacts/runtime-replication-2026-09-27/lab.sqlite3',
    'service-reliability': ROOT / 'artifacts/service-reliability-2026-09-27/lab.sqlite3',
    **{f'prospective-a{i:02d}': ROOT / f'artifacts/prospective-repair-2026-09-27/attempt-{i:02d}/lab.sqlite3'
       for i in range(1, 11)},
}
DEFAULT_WORLD_DIRS = (ROOT / 'artifacts/worlds', RUNS / 'worlds',
                      ROOT / 'artifacts/prospective-repair-worlds-2026-09-27/worlds')
FORBIDDEN = ('heldout2', 'final-audit', 'promotion', '.env', 'checks.py')


def _guard(path):
    text = str(path)
    if any(part in text for part in FORBIDDEN):
        raise ValueError(f'Refusing to open a protected path: {text}')
    return path


def _ro(path):
    return sqlite3.connect(f'file:{_guard(path)}?mode=ro&immutable=1', uri=True)


def load_rows(stores=None, world_dirs=None, *, model=DEFAULT_MODEL):
    """Stored in-scope episodes: recipe primitives and attempts per tool:service."""
    stores = DEFAULT_STORES if stores is None else stores
    world_dirs = DEFAULT_WORLD_DIRS if world_dirs is None else world_dirs
    world_index = {}
    for directory in world_dirs:
        directory = Path(_guard(directory))
        if directory.exists():
            for name in sorted(os.listdir(directory)):
                if name.endswith('.sqlite3'):
                    world_index.setdefault(name[:-len('.sqlite3')], directory / name)
    rows = []
    for store, path in stores.items():
        path = Path(_guard(path))
        if not path.exists():
            continue
        db = _ro(path)
        try:
            episodes = {}
            for ident, payload in db.execute("select id,payload from records where kind='episodes'"):
                episode = json.loads(payload)
                if (episode.get('split') == 'development' and episode.get('policy_version') == 'policy-v0'
                        and episode.get('model') == model and episode.get('lifecycle') == 'COMPLETED'):
                    episodes[ident] = episode
            inputs = {}
            for ident, payload in db.execute("select id,payload from records where kind='private_episode_inputs'"):
                if ident in episodes:  # development episodes only
                    inputs[ident] = json.loads(payload)
        finally:
            db.close()
        for ident, episode in sorted(episodes.items()):
            recipe = (inputs.get(ident) or {}).get('recipe')
            world_path = world_index.get(episode.get('world_id') or '')
            if not recipe or not recipe.get('primitives') or world_path is None:
                continue
            world = _ro(world_path)
            try:
                state = json.loads(world.execute('select value from state where id=1').fetchone()[0])
            finally:
                world.close()
            if state.get('diagnostic') or state['fault_spec']['primitives'] != recipe['primitives']:
                continue
            counts = Counter(f"{event['payload']['tool']}:{event['payload']['service']}"
                             for event in state['events'] if event['type'] == 'http_attempt')
            rows.append({'store': store, 'episode_id': ident, 'primitives': recipe['primitives'],
                         'counts': dict(counts)})
    return rows


def reach_points(rows, label):
    """Per recipe, tool:service and modelled attempt n: stored episodes and how many reached n.

    ``label`` maps a primitives list to a reachability label (``label_recipe`` output).
    """
    from app.contracts.models import canonical_json
    labels = {}
    tally = defaultdict(lambda: [0, 0])
    for row in rows:
        key = canonical_json(row['primitives'])
        if key not in labels:
            labels[key] = label(row['primitives'])
        result = labels[key]
        name = ' + '.join(result['recipe'])
        modelled = Counter(token.split('#', 1)[0] for token in result['agent_path'])
        for target, attempts in modelled.items():
            for n in range(1, attempts + 1):
                entry = tally[(name, target, n)]
                entry[0] += 1
                entry[1] += row['counts'].get(target, 0) >= n
    return [{'recipe': name, 'target': target, 'attempt': n, 'episodes': episodes, 'reached': reached,
             'rate': round(reached / episodes, 4)}
            for (name, target, n), (episodes, reached) in sorted(tally.items())]


def gate(points, *, min_episodes=MIN_EPISODES, min_rate=MIN_RATE):
    checked = [p for p in points if p['episodes'] >= min_episodes]
    failing = [p for p in checked if p['reached'] < min_rate * p['episodes']]
    return {'passed': bool(checked) and not failing, 'min_episodes': min_episodes, 'min_rate': min_rate,
            'points': len(points), 'checked_points': len(checked), 'failing_points': failing,
            'lowest_checked': sorted(checked, key=lambda p: (p['rate'], -p['episodes']))[:10]}


def run(stores=None, world_dirs=None, *, model=DEFAULT_MODEL, min_episodes=MIN_EPISODES, min_rate=MIN_RATE):
    from app.lab.reachability import LABELLER_VERSION, caller_model_for, label_recipe
    caller = caller_model_for('reference', [])
    rows = load_rows(stores, world_dirs, model=model)
    points = reach_points(rows, lambda primitives: label_recipe({'seed': 0, 'primitives': primitives}, caller))
    result = gate(points, min_episodes=min_episodes, min_rate=min_rate)
    return {'gate': 'faultlab-reachability-caller-gate/v1', 'labeller': LABELLER_VERSION,
            'caller_model': caller.descriptor(), 'model': model, 'episodes': len(rows),
            'recipes': len({json.dumps(r['primitives'], sort_keys=True) for r in rows}),
            'episodes_by_store': dict(Counter(r['store'] for r in rows)), **result, 'all_points': points}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--model', default=DEFAULT_MODEL)
    parser.add_argument('--min-episodes', type=int, default=MIN_EPISODES)
    parser.add_argument('--min-rate', type=float, default=MIN_RATE)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    result = run(model=args.model, min_episodes=args.min_episodes, min_rate=args.min_rate)
    if args.out:
        args.out.write_text(json.dumps(result, indent=1, sort_keys=True))
    summary = {key: result[key] for key in ('labeller', 'model', 'episodes', 'recipes', 'points', 'checked_points', 'passed')}
    summary['failing_points'] = result['failing_points']
    summary['caller_id'] = result['caller_model']['caller_id']
    print(json.dumps(summary, indent=1))
    if not result['checked_points']:
        return 2
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

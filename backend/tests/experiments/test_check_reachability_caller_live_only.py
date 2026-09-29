"""The caller-model gate counts only live Actor episodes (September 28 prerequisite).

A legacy baseline study's B1 arm is the handwritten deterministic ReferenceActor. Its episode
carries the campaign's model label but ``source_mode='offline_fixture'`` and makes no model
call, so it says nothing about what the live Actor does and must not enter the gate. Synthetic
stores only; no provider, network or model is used.
"""
import importlib.util
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[3]
MODEL = 'deepseek-ai/DeepSeek-V3.1'
PRIMITIVES = [{'kind': 'F4', 'target_tool': 'send_confirmation', 'target_service': 'notifications',
               'occurrence': 1, 'parameters': {'failure_count': 2}}]


def _gate():
    spec = importlib.util.spec_from_file_location('check_reachability_caller_live_only',
                                                  ROOT / 'scripts/experiments/check_reachability_caller.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _gate()


def _world(directory, world_id, attempts):
    db = sqlite3.connect(directory / f'{world_id}.sqlite3')
    events = [{'type': 'http_attempt', 'payload': {'tool': tool, 'service': service}}
              for tool, service in attempts]
    db.execute('create table state (id integer primary key, value text)')
    db.execute('insert into state values (1, ?)', (json.dumps({'diagnostic': False, 'events': events,
                                                                'fault_spec': {'seed': 0, 'primitives': PRIMITIVES}}),))
    db.commit(); db.close()


def _store(path, episodes):
    db = sqlite3.connect(path)
    db.execute('create table records (kind text, id text, payload text)')
    for episode in episodes:
        db.execute('insert into records values (?,?,?)', ('episodes', episode['episode_id'], json.dumps(episode)))
        db.execute('insert into records values (?,?,?)', ('private_episode_inputs', episode['episode_id'],
                                                         json.dumps({'recipe': {'seed': 0, 'primitives': PRIMITIVES}})))
    db.commit(); db.close()


def _episode(ident, world_id, **overrides):
    return {'episode_id': ident, 'world_id': world_id, 'split': 'development', 'policy_version': 'policy-v0',
            'model': MODEL, 'lifecycle': 'COMPLETED', **overrides}


def test_only_live_actor_episodes_are_counted(tmp_path):
    worlds = tmp_path / 'worlds'; worlds.mkdir()
    live_path = [('get_order', 'orders'), ('update_order', 'orders'), ('send_confirmation', 'notifications'),
                 ('send_confirmation', 'notifications'), ('get_operation_status', 'notifications')]
    for name in ('w-b0', 'w-p1', 'w-b1', 'w-unlabelled'):
        _world(worlds, name, live_path)
    _store(tmp_path / 'lab.sqlite3', [
        _episode('e-b0', 'w-b0', arm='B0', source_mode='live'),
        _episode('e-p1', 'w-p1', arm='P1', source_mode='live'),
        # The handwritten reference control of a legacy baseline study: excluded.
        _episode('e-b1', 'w-b1', arm='B1', source_mode='offline_fixture',
                 agent_registration_id='orders-v1-legacy'),
        # A record without a source label is not proof of a live Actor: excluded.
        _episode('e-unlabelled', 'w-unlabelled', arm='B0'),
    ])
    rows = gate.load_rows({'synthetic': tmp_path / 'lab.sqlite3'}, [worlds])
    assert [row['episode_id'] for row in rows] == ['e-b0', 'e-p1']
    assert rows[0]['counts'] == {'get_order:orders': 1, 'update_order:orders': 1,
                                 'send_confirmation:notifications': 2, 'get_operation_status:notifications': 1}

"""Order guard, read-only: the order task's identities are unchanged, this phase added nothing under
backend/, contracts/, audit/, frontend/, scripts/ or docs/, and the pack stays standalone."""
import ast
import json
import sys
from pathlib import Path

from taskpacks.bookings_move_with_hold import order_guard, table

ROOT = Path(__file__).resolve().parents[3]
PACK = Path(__file__).resolve().parents[1]
STDLIB = set(sys.stdlib_module_names)


def test_order_task_identities_are_unchanged():
    result = order_guard.guard()
    baseline = json.loads(order_guard.BASELINE_PATH.read_text(encoding='utf-8'))
    assert set(result['order_identities']) == {'service_hash', 'contract_hash', 'scorer_hash', 'interpreter_hash',
                                               'dependency_lock_hash'}
    for name, value in result['order_identities'].items():
        assert value['current'] == baseline['order_identities'][name], name
        assert value['equal'], name
    assert result['all_order_identities_unchanged']
    # The pinned service and contract hashes match backend/tests/simulator/test_entry_point.py.
    assert result['order_identities']['service_hash']['current'].startswith('3ce5bcd2')
    assert result['order_identities']['contract_hash']['current'].startswith('6f9d7783')
    assert result['latest_freeze_file'] is not None
    assert result['passed']


def test_gate_freeze_output_never_includes_the_sealed_audit_files():
    freeze = order_guard.run_gate_freeze()
    assert freeze['schema_version'] == 'faultlab-gate-freeze/v1'
    assert not set(order_guard.SEALED) & set(freeze['files'])
    assert 'audit/development.json' in freeze['files']


def test_this_phase_added_nothing_under_the_guarded_folders():
    listing = order_guard.listing_check()
    assert listing['hits'] == [] and listing['passed']
    assert set(listing['guarded_dirs']) >= {'backend', 'contracts', 'audit', 'frontend'}


def test_the_listing_check_would_catch_a_pack_file(tmp_path):
    (tmp_path / 'backend' / 'app' / 'taskpacks').mkdir(parents=True)
    (tmp_path / 'contracts').mkdir()
    (tmp_path / 'contracts' / 'bookings_move_with_hold.schema.json').write_text('{}')
    listing = order_guard.listing_check(tmp_path)
    assert listing['hits'] == ['backend/app/taskpacks', 'contracts/bookings_move_with_hold.schema.json']
    assert not listing['passed']


def test_the_pack_is_standalone_standard_library_only():
    """No module imports app.* (or anything outside the standard library and this pack)."""
    for path in sorted(PACK.rglob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split('.')[0]
                allowed = top in STDLIB or top == 'taskpacks' or (top in ('pytest', 'conftest') and 'tests' in path.parts)
                assert allowed, f'{path.relative_to(ROOT)} imports {name}'


def test_the_task_text_passes_the_order_task_text_rule():
    # Read-only: the rule's source is executed in a scratch namespace (no import, no bytecode written).
    path = ROOT / 'backend' / 'app' / 'contracts' / 'task_text.py'
    namespace = {'__name__': 'task_text_readonly'}
    exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), namespace)
    assert namespace['task_text_problem'](table.TASK_TEXT) is None
    assert namespace['task_text_problem']('   ') is not None

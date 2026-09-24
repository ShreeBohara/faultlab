"""Offline checks of the Phase 22 heldout-2 generator (scripts/experiments/make_heldout_partition.py).

Synthetic seeds and fixture manifests only: every promotion partition here is a synthetic file
in a temporary directory, the real audit/promotion.json is never read, no heldout-2 partition
or seed is made outside tmp_path, and no store, service or model is touched. The completion
manifest 7ab9368e is public (built from audit/development.json) and is used as it is.
"""
import builtins
import hashlib
import hmac
import importlib.util
import json
import os
import pathlib
import random
import stat
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'scripts/experiments/make_heldout_partition.py'
SPEC = importlib.util.spec_from_file_location('make_heldout_partition', SCRIPT)
gen = importlib.util.module_from_spec(SPEC)
sys.modules['make_heldout_partition'] = gen
SPEC.loader.exec_module(gen)

from app.contracts.models import FaultSpec, content_hash  # noqa: E402
from app.lab.challenge import schedule_identity  # noqa: E402
from app.referee import manifests  # noqa: E402

NAMES = ('no_fault', 'delayed_confirmation_response', 'delayed_upgrade_success', 'delayed_refusal',
         'stale_history', 'transient_upgrade_failures')


def synthetic_seed(label):
    return hashlib.sha256(f'synthetic-heldout-2-test-seed:{label}'.encode()).digest()


def write_seed(path, seed, mode=0o600):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    os.fchmod(descriptor, mode)
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(seed)
    return hashlib.sha256(seed).hexdigest()


def primitive(kind, tool, parameters):
    return {'kind': kind, 'target_tool': tool, 'target_service': gen.SERVICE[tool], 'occurrence': 1,
            'parameters': parameters}


def synthetic_promotion(directory, primitives_by_case, *, seeds=None):
    """A fixture promotion partition with a valid referee digest, in a temporary audit dir."""
    cases = []
    for index, primitives in enumerate(primitives_by_case):
        spec = {'schema_version': 'faultlab/v1', 'scope': gen.SCOPE,
                'seed': (seeds or {}).get(index, 700 + index), 'primitives': primitives}
        cases.append({'case_id': f'synthetic-promo-{index}', 'name': 'synthetic', 'fixture_id': 'standard-v1',
                      'expected_version': 1, 'fault_spec': spec, 'expected_class': 'fault'})
    document = {'schema_version': 'faultlab-manifest/v1', 'partition': 'promotion', 'access': 'PRIVATE_EVALUATOR',
                'cases': cases}
    document['manifest_hash'] = manifests.manifest_hash(document)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'promotion.json').write_text(json.dumps(document))
    return document


def default_promotion(directory):
    return synthetic_promotion(directory, [
        [],
        [primitive('F1', 'send_confirmation', {'response_delay_ms': 2345})],
        [primitive('F4', 'update_order', {'failure_count': 3})],
    ], seeds={1: 987654321})


def run_main(tmp_path, capsys, *, seed=None, audit=None, out_name='partition', extra=()):
    seed = synthetic_seed('main') if seed is None else seed
    seed_path = tmp_path / f'seed-{hashlib.sha256(seed).hexdigest()[:8]}.bin'
    if not seed_path.exists():
        write_seed(seed_path, seed)
    if audit is None:
        audit = tmp_path / 'audit'
        if not (audit / 'promotion.json').exists():
            default_promotion(audit)
    out = tmp_path / out_name
    code = gen.main(['--seed', str(seed_path), '--expect-seed-sha256', hashlib.sha256(seed).hexdigest(),
                     '--out', str(out), '--audit-dir', str(audit), *extra])
    captured = capsys.readouterr()
    return code, out, captured


def read_cases(out):
    return json.loads((out / gen.CASES_FILE).read_text())


# ---------------------------------------------------------------- draw spaces (Appendix A item 1)

def test_draw_spaces_are_exactly_appendix_a():
    spaces = gen.draw_spaces()
    assert tuple(spaces) == NAMES
    assert [position for position, _, _ in spaces.values()] == [1, 2, 3, 4, 5, 6]
    assert {name: len(specs) for name, (_, _, specs) in spaces.items()} == {
        'no_fault': 1, 'delayed_confirmation_response': 1501, 'delayed_upgrade_success': 4,
        'delayed_refusal': 4, 'stale_history': 3, 'transient_upgrade_failures': 3}
    fixtures = {name: fixture for name, (_, fixture, _) in spaces.items()}
    assert fixtures['stale_history'] == 'history-v1'
    assert {f for n, f in fixtures.items() if n != 'stale_history'} == {'standard-v1'}

    def parameters(name):
        return [spec['primitives'][0]['parameters'] for spec in spaces[name][2]]
    assert spaces['no_fault'][2][0]['primitives'] == []
    assert [p['response_delay_ms'] for p in parameters('delayed_confirmation_response')] == list(range(1500, 3001))
    for name, status in (('delayed_upgrade_success', 'SUCCEEDED'), ('delayed_refusal', 'FAILED')):
        assert [p['completion_delay_ticks'] for p in parameters(name)] == [1, 2, 3, 4]
        assert {p['terminal_status'] for p in parameters(name)} == {status}
        assert {p['failure_code'] for p in parameters(name)} == {'UPGRADE_REJECTED' if status == 'FAILED' else None}
    assert [p['versions_back'] for p in parameters('stale_history')] == [1, 2, 3]
    assert [p['failure_count'] for p in parameters('transient_upgrade_failures')] == [2, 3, 4]
    tools = {name: {s['primitives'][0]['target_tool'] for s in specs} for name, (_, _, specs) in spaces.items()
             if name != 'no_fault'}
    assert tools == {'delayed_confirmation_response': {'send_confirmation'}, 'delayed_upgrade_success': {'update_order'},
                     'delayed_refusal': {'update_order'}, 'stale_history': {'get_order'},
                     'transient_upgrade_failures': {'update_order'}}
    for name, (position, fixture, specs) in spaces.items():
        identities = [schedule_identity(FaultSpec.model_validate(spec)) for spec in specs]
        assert len(set(identities)) == len(specs)                       # parameters give distinct identities
        for spec in specs:
            assert spec['seed'] == 2026100000 + position                # seed is metadata (item 2)
            assert all(p['occurrence'] == 1 for p in spec['primitives'])
            assert FaultSpec.model_validate(spec).model_dump(mode='json') == spec
            assert gen.schedule_problem(spec, fixture) is None


def test_schedule_problem_uses_the_simulators_validate_schedule():
    stale = gen.draw_spaces()['stale_history'][2][2]                    # versions_back 3
    assert gen.schedule_problem(stale, 'history-v1') is None
    assert gen.schedule_problem(stale, 'standard-v1') == 'validate_schedule: WorldError STALE_HISTORY_UNAVAILABLE'
    bad = dict(stale, primitives=[dict(stale['primitives'][0], occurrence=2)])
    assert gen.schedule_problem(bad, 'history-v1') == 'occurrence is not 1'
    assert gen.schedule_problem({'seed': 1, 'primitives': []}, 'standard-v1') == \
        'fault_spec is not in canonical FaultSpec form'
    assert gen.schedule_problem(dict(stale, seed=-1), 'history-v1').startswith('FaultSpec')


# ---------------------------------------------------------------- draw and re-draw (item 2)

def reference_index(seed, k, j, size):
    """Appendix A item 2, written out independently."""
    return int.from_bytes(hmac.new(seed, f'heldout-2:{k}:{j}'.encode(), hashlib.sha256).digest(), 'big') % size


def test_draw_index_is_the_committed_hmac_with_one_based_positions():
    seed = synthetic_seed('index')
    for k in range(1, 7):
        for j in range(5):
            for size in (1, 3, 4, 1501):
                assert gen.draw_index(seed, k, j, size) == reference_index(seed, k, j, size)
    cases = gen.build_cases(seed, frozenset())
    for case, (name, (position, _, specs)) in zip(cases, gen.draw_spaces().items()):
        assert case['case_id'] == f'heldout-2-{position}' and case['name'] == name
        assert case['fault_spec'] == specs[reference_index(seed, position, 0, len(specs))]


def test_redraw_takes_the_first_attempt_whose_identity_is_not_excluded():
    spaces, identities = gen.draw_spaces(), gen.space_identities()
    generator = random.Random(20260924)
    for trial in range(60):
        seed = synthetic_seed(f'redraw-{trial}')
        excluded = set()
        for name, ids in identities.items():
            if name != 'no_fault':
                keep = generator.randrange(len(ids))   # leave at least one admissible identity
                excluded |= {i for n, i in enumerate(ids) if n != keep and generator.random() < 0.7}
        cases = gen.build_cases(seed, frozenset(excluded))
        for case, (name, (position, _, specs)) in zip(cases, spaces.items()):
            ids = identities[name]
            j = 0
            while name != 'no_fault' and ids[reference_index(seed, position, j, len(specs))] in excluded:
                j += 1
            assert case['fault_spec'] == specs[reference_index(seed, position, j, len(specs))]
            if name != 'no_fault':
                assert schedule_identity(FaultSpec.model_validate(case['fault_spec'])) not in excluded


def test_the_no_fault_case_is_exempt_from_novelty():
    healthy = gen.space_identities()['no_fault'][0]
    cases = gen.build_cases(synthetic_seed('exempt'), frozenset({healthy}))
    assert cases[0]['name'] == 'no_fault' and cases[0]['fault_spec']['primitives'] == []


def test_a_fully_excluded_space_stops_the_build_and_names_only_the_case():
    everything = frozenset(gen.space_identities()['transient_upgrade_failures'])
    with pytest.raises(gen.PartitionError, match=r'case 6 \(transient_upgrade_failures\).*re-declare'):
        gen.build_cases(synthetic_seed('full'), everything)


def test_a_fully_excluded_space_via_the_promotion_partition_writes_nothing(tmp_path, capsys):
    audit = tmp_path / 'audit'
    synthetic_promotion(audit, [[primitive('F4', 'update_order', {'failure_count': c})] for c in (2, 3, 4)])
    code, out, captured = run_main(tmp_path, capsys, audit=audit)
    assert code == 2 and not out.exists()
    assert captured.out == ''
    assert 'case 6 (transient_upgrade_failures)' in captured.err
    assert list(tmp_path.glob('.heldout-2-*')) == []                  # no staging directory left behind


def test_novelty_excludes_7ab9368e_and_the_promotion_partition_only():
    completion = gen.excluded_identities(gen.completion_manifest())
    ids = gen.space_identities()
    in_completion = {name: [n for n, i in enumerate(v) if i in completion] for name, v in ids.items()}
    # Appendix B (c): 7ab9368e holds the healthy schedule, F1 send_confirmation 1500 ms and one
    # F2 FAILED delay (the public terminal-upgrade-rejection case), and nothing else in these spaces.
    assert in_completion == {'no_fault': [0], 'delayed_confirmation_response': [0], 'delayed_upgrade_success': [],
                             'delayed_refusal': [1], 'stale_history': [], 'transient_upgrade_failures': []}
    for trial in range(40):
        cases = gen.build_cases(synthetic_seed(f'completion-{trial}'), completion)
        assert cases[1]['fault_spec']['primitives'][0]['parameters']['response_delay_ms'] != 1500
        assert cases[3]['fault_spec']['primitives'][0]['parameters']['completion_delay_ticks'] != 2


def test_the_completion_manifest_is_hash_checked(monkeypatch):
    import app.lab.completion_study as completion_study
    real = completion_study.case_manifest

    def tampered():
        value = real()
        value['cases'] = value['cases'][:-1]
        return value
    monkeypatch.setattr(completion_study, 'case_manifest', tampered)
    with pytest.raises(gen.PartitionError, match='7ab9368e'):
        gen.completion_manifest()


# ---------------------------------------------------------------- determinism, files, salt

def test_same_seed_gives_byte_identical_output_and_another_seed_does_not(tmp_path, capsys):
    code_a, out_a, first = run_main(tmp_path, capsys, out_name='a')
    code_b, out_b, second = run_main(tmp_path, capsys, out_name='b')
    assert code_a == code_b == 0
    for name in (gen.CASES_FILE, gen.HASH_FILE, gen.SUMMARY_FILE):
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes()
    assert first.out == second.out
    code_c, out_c, _ = run_main(tmp_path, capsys, seed=synthetic_seed('other'), out_name='c')
    assert code_c == 0
    assert (out_c / gen.HASH_FILE).read_bytes() != (out_a / gen.HASH_FILE).read_bytes()


def test_output_is_identical_across_processes_and_hash_seeds(tmp_path):
    seed = synthetic_seed('processes')
    seed_path = tmp_path / 'seed.bin'
    digest = write_seed(seed_path, seed)
    audit = tmp_path / 'audit'
    default_promotion(audit)
    outputs = []
    for hash_seed in ('0', '12345'):
        out = tmp_path / f'out-{hash_seed}'
        environment = dict(os.environ, PYTHONHASHSEED=hash_seed, PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run([sys.executable, str(SCRIPT), '--seed', str(seed_path), '--expect-seed-sha256', digest,
                                 '--out', str(out), '--audit-dir', str(audit)],
                                capture_output=True, text=True, env=environment, timeout=120)
        assert result.returncode == 0, result.stderr
        outputs.append({name: (out / name).read_bytes() for name in (gen.CASES_FILE, gen.HASH_FILE, gen.SUMMARY_FILE)})
    assert outputs[0] == outputs[1]


def test_files_are_owner_only_whatever_the_umask(tmp_path, capsys):
    previous = os.umask(0)
    try:
        code, out, _ = run_main(tmp_path, capsys)
    finally:
        os.umask(previous)
    assert code == 0
    assert stat.S_IMODE(out.stat().st_mode) == 0o700
    assert sorted(p.name for p in out.iterdir()) == sorted((gen.CASES_FILE, gen.HASH_FILE, gen.SUMMARY_FILE))
    for path in out.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_manifest_hash_is_content_hash_of_the_cases_and_is_salted(tmp_path, capsys):
    seed = synthetic_seed('salt')
    code, out, captured = run_main(tmp_path, capsys, seed=seed)
    assert code == 0
    document = read_cases(out)
    cases = document['cases']
    expected = content_hash(cases)
    summary = json.loads(captured.out)
    assert (out / gen.HASH_FILE).read_text() == expected + '\n'
    assert document['manifest_hash'] == summary['manifest_hash'] == expected
    assert summary['cases_file_sha256'] == hashlib.sha256((out / gen.CASES_FILE).read_bytes()).hexdigest()
    assert summary['seed_sha256'] == document['seed_sha256'] == hashlib.sha256(seed).hexdigest()
    for position, case in enumerate(cases, 1):
        assert case['salt'] == hmac.new(seed, f'heldout-2:salt:{position}'.encode(), hashlib.sha256).hexdigest()
        # What the held-out check hands PairedEvaluator: case_id, fixture_id, a valid fault_spec.
        assert FaultSpec.model_validate(case['fault_spec']).model_dump(mode='json') == case['fault_spec']
        assert case['expected_version'] == gen.FIXTURE_VERSIONS[case['fixture_id']]
    unsalted = [{k: v for k, v in case.items() if k != 'salt'} for case in cases]
    assert content_hash(unsalted) != expected                          # the published hash needs the seed


def test_identical_schedules_under_another_seed_publish_an_unrelated_hash():
    """Enumerating the 216,144 schedule combinations cannot reproduce a published manifest_hash:
    the same six schedules salted from another seed hash differently."""
    first = gen.build_cases(synthetic_seed('coincide-a'), frozenset())
    other_seed = synthetic_seed('coincide-b')
    same_schedules = [dict(case, salt=gen.case_salt(other_seed, position)) for position, case in enumerate(first, 1)]
    assert [c['fault_spec'] for c in same_schedules] == [c['fault_spec'] for c in first]
    assert content_hash(same_schedules) != content_hash(first)
    assert len({case['salt'] for case in first}) == 6


# ---------------------------------------------------------------- what is revealed

HEX64 = frozenset('0123456789abcdef')
HASH_FIELDS = ('manifest_hash', 'cases_file_sha256', 'seed_sha256')


def leaves(value, path=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, path + (key,))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from leaves(item, path + (index,))
    else:
        yield path, value


def test_the_public_summary_holds_only_counts_hashes_and_fixed_text(tmp_path, capsys):
    code, out, captured = run_main(tmp_path, capsys)
    assert code == 0 and captured.err == ''
    summary = json.loads(captured.out)
    assert captured.out.encode() == (out / gen.SUMMARY_FILE).read_bytes()    # stdout is the summary, nothing else
    fixed_text = {gen.SUMMARY_SCHEMA, gen.PARTITION, gen.RULE, *gen.DISCLOSURES, 'no_fault',
                  'content_hash(cases), salted per case from the seed', 'compared in code; nothing about it is recorded'}
    for path, value in leaves(summary):
        if isinstance(value, bool) or isinstance(value, int):
            continue
        assert isinstance(value, str), path
        assert (len(value) == 64 and set(value) <= HEX64) or value in fixed_text, (path, value)
    assert set(summary) == {'schema_version', 'partition', 'rule', 'seed_sha256', 'manifest_hash',
                            'manifest_hash_definition', 'cases_file_sha256', 'generator_sha256', 'case_count',
                            'space_sizes', 'novelty', 'disclosures'}
    assert summary['case_count'] == 6 and summary['novelty']['final_audit_loaded'] is False
    assert summary['novelty']['promotion_partition_default_path'] is False    # --audit-dir was a fixture


def test_the_summary_does_not_depend_on_the_draws_except_through_hashes(tmp_path, capsys):
    first = json.loads(run_main(tmp_path, capsys, seed=synthetic_seed('shape-1'), out_name='x')[2].out)
    second = json.loads(run_main(tmp_path, capsys, seed=synthetic_seed('shape-2'), out_name='y')[2].out)
    differing = {path for (path, a), (_, b) in zip(leaves(first), leaves(second)) if a != b}
    assert differing == {(field,) for field in HASH_FIELDS}


def test_nothing_about_the_promotion_partition_is_printed_or_written(tmp_path, capsys):
    audit_a, audit_b = tmp_path / 'audit-a', tmp_path / 'audit-b'
    promo = default_promotion(audit_a)
    synthetic_promotion(audit_b, [[primitive('F2', 'update_order', {'completion_delay_ticks': 3,
                                                                    'terminal_status': 'SUCCEEDED',
                                                                    'failure_code': None})]])
    seed = synthetic_seed('promo')
    code, out, captured = run_main(tmp_path, capsys, seed=seed, audit=audit_a, out_name='a')
    assert code == 0 and captured.err == ''
    secrets = {'synthetic-promo', '987654321', promo['manifest_hash']}
    secrets |= {schedule_identity(FaultSpec.model_validate(c['fault_spec'])) for c in promo['cases']}
    written = b''.join(p.read_bytes() for p in out.iterdir()).decode() + captured.out
    for secret in secrets:
        assert secret not in written
    # The promotion schedules are excluded from the draw (the no-fault case is exempt), never recorded:
    promoted = {schedule_identity(FaultSpec.model_validate(c['fault_spec'])) for c in promo['cases']}
    for case in read_cases(out)['cases'][1:]:
        assert schedule_identity(FaultSpec.model_validate(case['fault_spec'])) not in promoted
        for primitive_ in case['fault_spec']['primitives']:
            assert primitive_['parameters'].get('response_delay_ms') != 2345
    # Another promotion partition changes the summary only through the salted hashes. That is
    # safe only while the seed is secret, which is why the real partition is read only for the
    # committed seed (test_the_real_promotion_partition_is_read_only_for_the_committed_seed).
    other = json.loads(run_main(tmp_path, capsys, seed=seed, audit=audit_b, out_name='b')[2].out)
    this = json.loads(captured.out)
    assert {k: v for k, v in this.items() if k not in HASH_FIELDS} == {k: v for k, v in other.items()
                                                                       if k not in HASH_FIELDS}


def test_a_promotion_partition_that_fails_to_validate_is_refused_without_its_values(tmp_path, capsys):
    audit = tmp_path / 'audit'
    document = synthetic_promotion(audit, [[primitive('F1', 'send_confirmation', {'response_delay_ms': 1600})]])
    document['cases'][0]['fault_spec']['primitives'][0]['parameters']['response_delay_ms'] = 98765
    document['manifest_hash'] = manifests.manifest_hash(document)       # a valid digest over an invalid value
    (audit / 'promotion.json').write_text(json.dumps(document))
    code, out, captured = run_main(tmp_path, capsys, audit=audit)
    assert code == 2 and not out.exists() and captured.out == ''
    assert 'details withheld' in captured.err and '98765' not in captured.err
    # A tampered digest is refused the same way.
    document['manifest_hash'] = '0' * 64
    (audit / 'promotion.json').write_text(json.dumps(document))
    code, out, captured = run_main(tmp_path, capsys, audit=audit, out_name='again')
    assert code == 2 and not out.exists() and 'details withheld' in captured.err


def test_the_final_audit_file_is_never_loaded(tmp_path, capsys, monkeypatch):
    audit = tmp_path / 'audit'
    default_promotion(audit)
    (audit / 'final-audit.json').write_text('{"sentinel": true}')
    requested = []
    real_load = manifests.load_manifest

    def recording_load(name, **kwargs):
        requested.append(name)
        return real_load(name, **kwargs)
    monkeypatch.setattr(manifests, 'load_manifest', recording_load)
    touched = []
    real_open, real_read_text, real_read_bytes = builtins.open, pathlib.Path.read_text, pathlib.Path.read_bytes

    def guard(path):
        if 'final-audit' in str(path):
            touched.append(str(path))
            raise AssertionError('the final-audit file must never be loaded')

    def guarded_open(file, *args, **kwargs):
        guard(file)
        return real_open(file, *args, **kwargs)

    def guarded_read_text(self, *args, **kwargs):
        guard(self)
        return real_read_text(self, *args, **kwargs)

    def guarded_read_bytes(self, *args, **kwargs):
        guard(self)
        return real_read_bytes(self, *args, **kwargs)
    monkeypatch.setattr(builtins, 'open', guarded_open)
    monkeypatch.setattr(pathlib.Path, 'read_text', guarded_read_text)
    monkeypatch.setattr(pathlib.Path, 'read_bytes', guarded_read_bytes)
    code, _, captured = run_main(tmp_path, capsys, audit=audit)
    assert code == 0, captured.err
    assert touched == []
    assert set(requested) <= {'development', 'promotion'} and 'promotion' in requested
    assert 'final-audit' not in gen.promotion_identities.__code__.co_consts


# ---------------------------------------------------------------- refusals and the seed file

def test_refusals(tmp_path, capsys):
    seed = synthetic_seed('refusals')
    good = tmp_path / 'good.bin'
    digest = write_seed(good, seed)
    audit = tmp_path / 'audit'
    default_promotion(audit)

    def attempt(*argv):
        code = gen.main([*argv, '--audit-dir', str(audit)])
        return code, capsys.readouterr()

    code, captured = attempt('--seed', str(good), '--out', str(tmp_path / 'o1'))
    assert code == 2 and 'required' in captured.err
    code, captured = attempt('--seed', str(good), '--expect-seed-sha256', 'f' * 64, '--out', str(tmp_path / 'o2'))
    assert code == 2 and 'committed seed hash' in captured.err and not (tmp_path / 'o2').exists()
    loose = tmp_path / 'loose.bin'
    write_seed(loose, seed, mode=0o644)
    code, captured = attempt('--seed', str(loose), '--expect-seed-sha256', digest, '--out', str(tmp_path / 'o3'))
    assert code == 2 and 'chmod 600' in captured.err
    short = tmp_path / 'short.bin'
    write_seed(short, seed[:31])
    code, captured = attempt('--seed', str(short), '--expect-seed-sha256', hashlib.sha256(seed[:31]).hexdigest(),
                             '--out', str(tmp_path / 'o4'))
    assert code == 2 and 'exactly 32 raw bytes' in captured.err
    existing = tmp_path / 'existing'
    existing.mkdir()
    code, captured = attempt('--seed', str(good), '--expect-seed-sha256', digest, '--out', str(existing))
    assert code == 2 and 'refusing to overwrite' in captured.err and list(existing.iterdir()) == []
    code, captured = attempt('--seed', str(good), '--expect-seed-sha256', digest.upper(), '--out', str(tmp_path / 'o5'))
    assert code == 0 and (tmp_path / 'o5' / gen.CASES_FILE).exists()   # the committed hash may be upper case
    with pytest.raises(gen.PartitionError):
        gen.build_cases(seed[:16], frozenset())


def test_new_seed_writes_32_private_bytes_and_prints_only_their_hash(tmp_path, capsys):
    path = tmp_path / 'fresh.bin'
    assert gen.main(['--new-seed', str(path)]) == 0
    printed = json.loads(capsys.readouterr().out)
    data = path.read_bytes()
    assert len(data) == 32 and stat.S_IMODE(path.stat().st_mode) == 0o600
    assert printed == {'seed_sha256': hashlib.sha256(data).hexdigest()}
    assert data.hex() not in json.dumps(printed)
    assert gen.main(['--new-seed', str(path)]) == 2                     # never overwritten
    assert 'never overwritten' in capsys.readouterr().err
    assert path.read_bytes() == data
    assert gen.main(['--new-seed', str(tmp_path / 'x.bin'), '--out', str(tmp_path / 'y')]) == 2


# ---------------------------------------------------------------- review round 1: interface and the seed gate

def test_the_private_file_is_the_one_the_backend_loads(tmp_path, capsys, monkeypatch):
    """R1: the generator's output, from a synthetic seed and a synthetic promotion partition, loads
    through the backend's own load_partition under the printed manifest_hash, and plans 78 pairs."""
    import app.lab.heldout_check as heldout
    root = tmp_path / 'root'
    root.mkdir()
    code, out, captured = run_main(tmp_path, capsys, out_name='root/sealed')
    assert code == 0, captured.err
    assert gen.CASES_FILE == heldout.PARTITION_FILE_V2 == 'heldout-2.json'
    summary = json.loads(captured.out)
    monkeypatch.setattr(heldout, 'APP_ROOT', root)
    monkeypatch.setattr(heldout, 'load_cases', lambda name: (_ for _ in ()).throw(AssertionError(name)))
    cases = heldout.load_partition('sealed', summary['manifest_hash'])     # the real check-time novelty scope
    assert cases == read_cases(out)['cases'] and content_hash(cases) == summary['manifest_hash']
    plan = heldout.check_plan('sealed', summary['manifest_hash'])
    assert (plan['extra']['planned_pairs'], plan['extra']['planned_episodes']) == (78, 156)
    assert (out / gen.HASH_FILE).read_text().strip() == plan['manifest_hash']


def gate(monkeypatch, tmp_path, committed, *, history=None, generator='own'):
    """A synthetic repository root and a synthetic commitment (the seed line, its history on the
    branch, and the generator pin); the promotion loader records calls."""
    root = tmp_path / 'repo'
    (root / 'artifacts' / 'heldout2').mkdir(parents=True)
    monkeypatch.setattr(gen, 'ROOT', root)
    monkeypatch.setattr(gen, 'committed_seed_sha256', lambda: committed)
    monkeypatch.setattr(gen, 'committed_seed_history', lambda: {committed} if history is None else history)
    monkeypatch.setattr(gen, 'committed_generator_sha256', lambda: gen.own_sha256() if generator == 'own' else generator)
    calls = []

    def recording(audit_dir=None):
        calls.append(audit_dir)
        return frozenset()
    monkeypatch.setattr(gen, 'promotion_identities', recording)
    return root, calls


def build_default(root, seed_path, digest, out):
    return gen.main(['--seed', str(seed_path), '--expect-seed-sha256', digest, '--out', str(out)])


def test_the_real_promotion_partition_is_read_only_for_the_committed_seed(tmp_path, capsys, monkeypatch):
    """Review round 1: with a known throwaway seed, the public manifest_hash answers whether chosen
    schedules are in the promotion partition. Without --audit-dir, only the seed committed on the
    backup branch, built once into artifacts/heldout2/partition, may read it."""
    seed = synthetic_seed('committed')
    seed_path = tmp_path / 'seed.bin'
    digest = write_seed(seed_path, seed)
    other = hashlib.sha256(b'another seed').hexdigest()
    for committed, out_name, message in (
            (None, 'artifacts/heldout2/partition', 'no seed commitment'),
            (other, 'artifacts/heldout2/partition', 'not the committed one'),
            (digest, 'artifacts/heldout2/elsewhere', '--out must be artifacts/heldout2/partition')):
        root, calls = gate(monkeypatch, tmp_path / (out_name.rsplit('/', 1)[1] + (committed or 'none')[:4]), committed)
        out = root / out_name
        assert build_default(root, seed_path, digest, out) == 2
        captured = capsys.readouterr()
        assert message in captured.err and captured.out == '' and calls == [] and not out.exists()
    root, calls = gate(monkeypatch, tmp_path / 'ok', digest)
    out = root / gen.DECLARED_OUT
    assert build_default(root, seed_path, digest, out) == 0, capsys.readouterr().err
    assert calls == [None] and (out / gen.CASES_FILE).exists()
    capsys.readouterr()
    # Built once: the declared output now exists, and a second build is refused before any read.
    assert build_default(root, seed_path, digest, out) == 2
    assert 'built once' in capsys.readouterr().err and calls == [None]


def test_the_seed_line_must_have_held_one_value_and_the_generator_must_be_the_pinned_one(tmp_path, capsys, monkeypatch):
    """Review round 2: a later commit replacing the seed line must not admit a second seed, and the
    program that draws must be the one whose sha was committed (F6) before the seed existed."""
    seed = synthetic_seed('history')
    seed_path = tmp_path / 'seed.bin'
    digest = write_seed(seed_path, seed)
    for label, kwargs, message in (
            ('two', {'history': {digest, 'b' * 64}}, 'has held another value'),
            ('unreadable', {'history': set()}, 'has held another value'),
            ('nogen', {'generator': None}, 'no generator pin'),
            ('othergen', {'generator': 'c' * 64}, 'not the one pinned')):
        root, calls = gate(monkeypatch, tmp_path / label, digest, **kwargs)
        out = root / gen.DECLARED_OUT
        assert build_default(root, seed_path, digest, out) == 2
        captured = capsys.readouterr()
        assert message in captured.err and captured.out == '' and calls == [] and not out.exists()
    root, calls = gate(monkeypatch, tmp_path / 'fine', digest)
    assert build_default(root, seed_path, digest, root / gen.DECLARED_OUT) == 0, capsys.readouterr().err
    summary = json.loads(capsys.readouterr().out)
    assert calls == [None] and summary['generator_sha256'] == gen.own_sha256()


def test_the_seed_history_and_generator_pin_are_read_from_the_backup_branch(monkeypatch):
    seen = []

    def git(stdout):
        def run(command, **kwargs):
            seen.append(command)
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr='')
        return run
    good, other = 'a' * 64, 'b' * 64
    log = (f'diff --git a/x b/x\n-heldout2-seed-sha256: FILL-BEFORE-GENERATOR\n+heldout2-seed-sha256: {good}\n'
           f' generator-sha256: {"c" * 64}\n')
    monkeypatch.setattr(gen.subprocess, 'run', git(log))
    assert gen.committed_seed_history() == {good}
    assert seen[-1] == ['git', '-C', str(gen.ROOT), 'log', '-p', '--format=', 'backup/part2-2026-09-22', '--',
                        'docs/part2/PHASE22_EXPERIMENT.md']
    monkeypatch.setattr(gen.subprocess, 'run', git(log + f'-heldout2-seed-sha256: {good}\n+heldout2-seed-sha256: {other}\n'))
    assert gen.committed_seed_history() == {good, other}
    monkeypatch.setattr(gen.subprocess, 'run', git(f'x\ngenerator-sha256: {"c" * 64}\n'))
    assert gen.committed_generator_sha256() == 'c' * 64
    monkeypatch.setattr(gen.subprocess, 'run', git('generator-sha256: FILL-AT-FREEZE\n'))
    assert gen.committed_generator_sha256() is None
    monkeypatch.setattr(gen.subprocess, 'run', lambda *a, **k: (_ for _ in ()).throw(OSError('no git')))
    assert gen.committed_seed_history() is None and gen.committed_generator_sha256() is None


def stand_in_real_audit(tmp_path, monkeypatch):
    """A synthetic stand-in for the real audit directory (the real one is never touched here)."""
    real = tmp_path / 'real-audit'
    default_promotion(real)
    monkeypatch.setattr(manifests, 'AUDIT_DIR', real)
    return real


@pytest.mark.parametrize('how', ['symlink', 'hardlink', 'directory-symlink'])
def test_any_path_to_the_real_promotion_file_is_refused_as_a_synthetic_one(tmp_path, capsys, monkeypatch, how):
    """Probe G1 (review round 2): a directory holding a link to the real promotion.json passed the
    directory-only comparison, and a throwaway seed then read the real partition."""
    real = stand_in_real_audit(tmp_path, monkeypatch)
    probe = tmp_path / 'probe'
    if how == 'directory-symlink':
        os.symlink(real, probe)
    else:
        probe.mkdir()
        (os.symlink if how == 'symlink' else os.link)(real / 'promotion.json', probe / 'promotion.json')
    monkeypatch.setattr(gen, 'promotion_identities', lambda *a, **k: (_ for _ in ()).throw(AssertionError('read')))
    seed_path = tmp_path / 'seed.bin'
    digest = write_seed(seed_path, synthetic_seed('probe'))
    code = gen.main(['--seed', str(seed_path), '--expect-seed-sha256', digest, '--out', str(tmp_path / 'o'),
                     '--audit-dir', str(probe)])
    captured = capsys.readouterr()
    assert code == 2 and 'synthetic partition' in captured.err and captured.out == '' and not (tmp_path / 'o').exists()


def test_a_copy_that_is_not_synthetic_is_refused_without_any_detail(tmp_path, capsys):
    """Review round 2: a document given with --audit-dir must be synthetic (every case id starting
    'synthetic-'), so a plain copy of the real file fails closed. The refusal names nothing in it."""
    audit = tmp_path / 'audit'
    document = default_promotion(audit)
    document['cases'][1]['case_id'] = 'promotion-case-2'
    document['manifest_hash'] = manifests.manifest_hash(document)          # digest-valid, like a real copy
    (audit / 'promotion.json').write_text(json.dumps(document))
    code, out, captured = run_main(tmp_path, capsys, audit=audit)
    assert code == 2 and not out.exists() and captured.out == ''
    assert 'synthetic partition' in captured.err and 'details withheld' in captured.err
    assert 'promotion-case-2' not in captured.err and '2345' not in captured.err
    assert gen.SYNTHETIC_CASE_PREFIX == 'synthetic-'


def test_the_real_audit_directory_is_refused_as_a_synthetic_one(tmp_path, capsys, monkeypatch):
    seed = synthetic_seed('real-audit')
    seed_path = tmp_path / 'seed.bin'
    digest = write_seed(seed_path, seed)
    monkeypatch.setattr(gen, 'promotion_identities', lambda *a, **k: (_ for _ in ()).throw(AssertionError('read')))
    code = gen.main(['--seed', str(seed_path), '--expect-seed-sha256', digest, '--out', str(tmp_path / 'o'),
                     '--audit-dir', str(manifests.AUDIT_DIR)])
    assert code == 2 and 'synthetic partition' in capsys.readouterr().err and not (tmp_path / 'o').exists()


def test_the_commitment_is_the_single_pin_line_on_the_backup_branch(monkeypatch):
    seen = []

    def shown(stdout, returncode=0):
        def run(command, **kwargs):
            seen.append(command)
            return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr='')
        return run
    good = 'a' * 64
    for stdout, returncode, expected in (
            (f'text\n```\nheldout2-seed-sha256: {good}\nheldout2-manifest-hash: FILL-AT-SEAL\n```\n', 0, good),
            ('heldout2-seed-sha256: FILL-BEFORE-GENERATOR\n', 0, None),
            (f'heldout2-seed-sha256: {good}\nheldout2-seed-sha256: {"b" * 64}\n', 0, None),
            (f'heldout2-seed-sha256: {good.upper()}\n', 0, None),
            (f'Write the `heldout2-seed-sha256` line: {good}\n', 0, None),
            (f'heldout2-seed-sha256: {good}\n', 128, None)):
        monkeypatch.setattr(gen.subprocess, 'run', shown(stdout, returncode))
        assert gen.committed_seed_sha256() == expected
    assert seen[0] == ['git', '-C', str(gen.ROOT), 'show', 'backup/part2-2026-09-22:docs/part2/PHASE22_EXPERIMENT.md']
    monkeypatch.setattr(gen.subprocess, 'run', lambda *a, **k: (_ for _ in ()).throw(OSError('no git')))
    assert gen.committed_seed_sha256() is None


# ---------------------------------------------------------------- the v2 calibration (phase22_predicate_calibration.py)
# Pure arithmetic and a synthetic store only; the real stores are read by the script, never here.

import itertools  # noqa: E402
import math  # noqa: E402
import sqlite3  # noqa: E402
from fractions import Fraction  # noqa: E402

CALIBRATION_SPEC = importlib.util.spec_from_file_location(
    'phase22_predicate_calibration', ROOT / 'scripts/experiments/phase22_predicate_calibration.py')
calibration = importlib.util.module_from_spec(CALIBRATION_SPEC)
sys.modules['phase22_predicate_calibration'] = calibration
CALIBRATION_SPEC.loader.exec_module(calibration)
p20 = calibration.p20


def test_v2_rule_matches_the_exact_fraction_rule_for_every_table():
    n = calibration.V2_N
    for b, l in itertools.product(range(n + 1), repeat=2):
        m = b + l
        exact = Fraction(sum(math.comb(n, x) * math.comb(n, m - x) for x in range(b, min(n, m) + 1)), math.comb(2 * n, m))
        declared = (b > l and exact <= Fraction(1, 20)) or (l == 0 and b >= 3)
        assert p20.harm_v2(b, l, n) == declared


def test_case_null_matches_brute_force_and_reduces_to_rule3_without_failures():
    for n, harm in ((3, p20.harm_v1), (15, p20.harm_v2)):
        for q, v in ((0.074, 0.0), (0.5, 0.01), (1.0, 0.0013), (0.33, 0.05)):
            expected = p20.rules_1_and_3(n, q * (1 - v), v, harm)   # the same model with q as a joint rate
            assert calibration.case_null(n, q, v) == pytest.approx(expected, abs=1e-12)
            if v == 0.0:
                assert calibration.case_null(n, q, 0.0) == pytest.approx(p20.rule3(n, q, q, harm), abs=1e-12)
    # n = 3 by full enumeration of both arms' trial outcomes (target, failure, other).
    q, v = 0.6, 0.1
    probability = {'t': q * (1 - v), 'f': v, 'o': (1 - q) * (1 - v)}
    total = 0.0
    for candidate in itertools.product('tfo', repeat=3):
        for baseline in itertools.product('tfo', repeat=3):
            weight = math.prod(probability[x] for x in candidate + baseline)
            if 'f' in candidate or candidate.count('t') < baseline.count('t'):
                total += weight
    assert calibration.case_null(3, q, v) == pytest.approx(total, abs=1e-12)
    assert calibration.case_null(3, 1.0, 0.0013) == pytest.approx(1 - (1 - 0.0013) ** 3)  # q = 1: rule 1 only


def test_partition_null_and_the_verdict_model():
    fault_q = {name: 0.9 for name in calibration.FAULT_KINDS}
    row = calibration.partition_null(fault_q, 0.97, 0.0, 'v2')
    expected = 1 - 0.97 ** 3 * (1 - p20.rule3(15, 0.9, 0.9, p20.harm_v2)) ** 5
    assert row['p_harm'] == pytest.approx(expected, abs=1e-4) and row['candidate_episodes'] == 78
    assert calibration.partition_null(fault_q, 0.97, 0.0, 'v1')['candidate_episodes'] == 18
    u = {name: 0.0 for name in calibration.FAULT_KINDS}
    assert calibration.verdict_within_attempts(u, 0.0, 'v2')['p_verdict_within_3'] == 1.0
    u['delayed_confirmation_response'] = 0.03
    result = calibration.verdict_within_attempts(u, 0.0, 'v2')
    clean = 0.97 ** 30
    assert result['p_all_triggered_per_attempt'] == pytest.approx(clean, abs=1e-4)
    assert result['p_clean_batch_within_3'] == pytest.approx(1 - (1 - clean) ** 3, abs=1e-4)
    with_rule1 = calibration.verdict_within_attempts(u, 0.01, 'v2')
    no_verdict = (1 - 0.01) ** 78 * (1 - clean)
    assert with_rule1['p_verdict_within_3'] == pytest.approx(1 - no_verdict ** 3, abs=1e-4)
    crossover = calibration.rule1_crossover(fault_q, 0.97)
    if crossover['v']:
        below, above = crossover['v'] * 0.9, crossover['v'] * 1.1
        for v, sign in ((below, -1), (above, 1)):
            gap = (calibration.partition_null(fault_q, 0.97, v, 'v2')['p_harm']
                   - calibration.partition_null(fault_q, 0.97, v, 'v1')['p_harm'])
            assert gap * sign > 0


def synthetic_store(path, rows):
    connection = sqlite3.connect(path)
    connection.executescript(
        'CREATE TABLE records(kind TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,immutable INTEGER NOT NULL '
        'DEFAULT 0,PRIMARY KEY(kind,id));'
        'CREATE TABLE events(episode_id TEXT NOT NULL,seq INTEGER NOT NULL,payload TEXT NOT NULL,'
        'PRIMARY KEY(episode_id,seq));')
    for eid, split, policy, recipe, trial, context, tools in rows:
        connection.execute('INSERT INTO records VALUES (?,?,?,0)',
                           ('episodes', eid, json.dumps({'split': split, 'report': {'x': 1}})))
        connection.execute('INSERT INTO records VALUES (?,?,?,0)', ('trials', eid, json.dumps(
            {'policy_hash': policy, **trial})))
        connection.execute('INSERT INTO records VALUES (?,?,?,0)', ('private_episode_inputs', eid,
                                                                    recipe if isinstance(recipe, str) else
                                                                    json.dumps({'recipe': recipe})))
        seq = 0
        if context:
            connection.execute('INSERT INTO events VALUES (?,?,?)', (eid, seq, json.dumps(
                {'type': 'actor_output', 'payload': {'actor_context_protocol': context}})))
        for tool in tools:
            seq += 1
            connection.execute('INSERT INTO events VALUES (?,?,?)', (eid, seq, json.dumps(
                {'type': 'tool_dispatched', 'payload': {'tool': tool, 'caller': 'actor'}})))
    connection.commit()
    connection.close()


def test_measurement_reads_only_v4_development_trials(tmp_path):
    b0, other = calibration.BASELINE_POLICY_HASH, 'e' * 64
    spec = lambda primitives: {'seed': 5, 'primitives': primitives}   # noqa: E731
    c2 = spec([primitive('F4', 'update_order', {'failure_count': 2})])
    f1 = spec([primitive('F1', 'send_confirmation', {'response_delay_ms': 1777})])
    done = {'lifecycle': 'COMPLETED', 'outcome': 'COMPLETED', 'fault_scheduled': True, 'fault_triggered': True,
            'failed_checks': []}
    unresolved = dict(done, outcome='SAFE_UNRESOLVED')
    violation = dict(done, outcome='VIOLATION', failed_checks=['C6'])
    untriggered = dict(unresolved, fault_triggered=False)
    v4, tools = calibration.V4, ('get_order', 'update_order', 'send_confirmation')
    phase20 = tmp_path / 'phase20.sqlite3'
    synthetic_store(phase20, [
        ('e1', 'development', b0, c2, done, v4, tools),
        ('e2', 'development', b0, c2, unresolved, v4, tools),
        ('e3', 'development', b0, c2, violation, v4, tools),
        ('e4', 'development', other, c2, done, v4, tools),
        ('e5', 'development', b0, c2, done, 'faultlab-actor-context/v1', tools),        # not v4: ignored
    ])
    main = tmp_path / 'main.sqlite3'
    synthetic_store(main, [
        ('m1', 'development', b0, f1, untriggered, v4, ('get_order', 'update_order')),
        ('m2', 'development', other, f1, done, v4, tools),
        ('m3', 'promotion', b0, 'not json: a private recipe must never be parsed', done, v4, tools),
    ])
    drift_list = tmp_path / 'drift.txt'
    drift_list.write_text('scored episodes checked: 9\ndrifted: 1\n  e3 2026-09-22T20:49:20 arm=B0 VIOLATION\n'
                          '  episode-x 2026-09-22 arm=L\nmasked response-delay faults: 1\n  e1 arm=B0 fault-1\nexit=1\n')
    measured = calibration.measure({'phase20': phase20, 'main': main}, drift_artifact=drift_list)
    transient = measured['by_kind']['transient_upgrade_failures']
    assert (transient['b0_target']['k'], transient['b0_target']['n']) == (1, 3)    # e1 of e1, e2, e3 (all valid)
    assert (transient['b0_counted_failures']['k'], transient['b0_counted_failures']['n']) == (1, 3)
    assert transient['drawable_identities_measured'] == 1 and not transient['measured_rate_is_a_proxy']
    confirmation = measured['by_kind']['delayed_confirmation_response']
    assert (confirmation['b0_target']['k'], confirmation['b0_target']['n']) == (0, 0)   # m1 is invalid (untriggered)
    assert (confirmation['untriggered_all_arms']['k'], confirmation['untriggered_all_arms']['n']) == (1, 2)
    pools = measured['rule1_failure_pools']
    assert (pools['phase20_pooled_all_b0']['k'], pools['phase20_pooled_all_b0']['n']) == (1, 3)
    assert (pools['store_applicable_b0']['k'], pools['store_applicable_b0']['n']) == (0, 1)
    assert measured['untriggered_mechanism_proxy']['episodes'] == 6
    assert measured['untriggered_mechanism_proxy']['without_get_order']['k'] == 0
    assert measured['sources']['main']['v4_development_episodes'] == 2
    assert pools['declared_rule1_pool_failures'] == ['e3']
    # e3 is not listed with an 'episode-' prefix, so it is not a drift here: nothing is excluded.
    assert (pools['non_defect_rule1_pool']['k'], pools['non_defect_rule1_pool']['excluded_failures']) == (1, [])
    drift_list.write_text('drifted: 1\n  episode-e3 x\nmasked response-delay faults: 0\n')
    assert calibration.phase19_drifted_episodes(drift_list) == {'episode-e3'}


def test_the_phase19_drift_list_is_parsed_from_its_drifted_section_only(tmp_path):
    listing = tmp_path / 'drift.txt'
    listing.write_text('scored episodes checked: 4791\nworld files missing: 0\ndrifted: 2\n'
                       '  episode-aaa 2026-09-22T17:44:37 arm=L VIOLATION\n  episode-bbb 2026-09-22T20:09:24 arm=B0\n'
                       '  2026-09-22: 2\nmasked response-delay faults: 1\n  episode-ccc 2026-09-22 arm=B0 fault-1\nexit=1\n')
    assert calibration.phase19_drifted_episodes(listing) == {'episode-aaa', 'episode-bbb'}


# ---------------------------------------------------------------- review round 1: the calibration's additions

MEASURED_Q = {'delayed_confirmation_response': 129 / 130, 'delayed_upgrade_success': 1.0, 'delayed_refusal': 1.0,
              'stale_history': 1.0, 'transient_upgrade_failures': 2 / 27}


def test_v2_cannot_see_a_loss_of_one_to_three_of_fifteen_against_fifteen():
    floor = calibration.v2_detection_floor()
    assert (floor[15], floor[14], floor[13], floor[3], floor[2]) == (11, 9, 7, 0, None)


def test_small_losses_on_the_high_rate_cases_match_round_1():
    at_one = calibration.small_losses(1.0)
    assert at_one['power']['d=0.1'] == {'v1': 0.271, 'v2': 0.0556}
    assert at_one['v2_power_at_least_v1_from_d'] == 0.28
    assert at_one['mdl_50pct'] == {'v1': 0.21, 'v2': 0.24} and at_one['mdl_80pct'] == {'v1': 0.42, 'v2': 0.34}
    probe = calibration.small_losses(0.975)
    assert probe['v2_power_at_least_v1_from_d'] == 0.34 and probe['mdl_50pct'] == {'v1': 0.2, 'v2': 0.26}
    assert calibration.small_losses(129 / 130)['v2_power_at_least_v1_from_d'] == 0.29


def test_case_harm_is_case_null_when_both_arms_share_a_rate():
    for n in (3, 15):
        for q, v in ((1.0, 0.0), (0.6, 0.01), (0.074, 1 / 781)):
            assert calibration.case_harm(n, q, q, v) == calibration.case_null(n, q, v)
    assert calibration.case_harm(15, 1.0, 0.0, 0.0) == pytest.approx(1.0)


def test_the_worst_case_reading_fails_power_on_three_cases_and_never_the_null():
    intervals = {'delayed_confirmation_response': (0.9577, 0.9986), 'delayed_upgrade_success': (0.8241, 1.0),
                 'delayed_refusal': (0.9711, 1.0), 'stale_history': (0.6097, 1.0),
                 'transient_upgrade_failures': (0.0206, 0.2337)}
    rows = {name: calibration.criterion_worst_case(interval) for name, interval in intervals.items()}
    assert all(row['v2_null_strictly_lower'] for row in rows.values())
    assert {name: row['power_fails_on'] for name, row in rows.items() if row['power_fails_on']} == {
        'delayed_upgrade_success': ['halving'], 'stale_history': ['halving'],
        'transient_upgrade_failures': ['total_loss', 'halving']}
    # 101-point grid over the interval; round 1's 401-point grid gave 0.369 and [0.6097, 0.9268].
    assert rows['stale_history']['power_min']['halving'] == {'v1': 0.6524, 'v2': 0.3691,
                                                             'v2_matches_or_beats': False,
                                                             'v2_below_v1_for_q': [0.6097, 0.9258]}


def test_phase24_outcomes_reproduce_round_1s_phase_level_figures():
    q0, u, v = 271 / 278, 8 / 264, 1 / 781

    def outcome(design, harmed=None, rate=None):
        ql = dict(MEASURED_Q, **({harmed: rate} if harmed else {}))
        return calibration.phase24_outcome(u, v, calibration.partition_harm(MEASURED_Q, ql, q0, v, design), design)
    null = {design: outcome(design) for design in ('v1', 'v2')}
    assert null['v2']['within_2'] == {'NO_HARM': 0.4992, 'HARM': 0.2033, 'no_verdict': 0.2975}
    assert null['v2']['p_no_harm_given_a_verdict'] == 0.7106 and null['v1']['p_no_harm_given_a_verdict'] == 0.7343
    assert (null['v1']['clean_per_attempt'], null['v2']['clean_per_attempt']) == (0.8314, 0.3973)
    total = {design: outcome(design, 'stale_history', 0.0) for design in ('v1', 'v2')}
    assert (total['v1']['within_2']['HARM'], total['v2']['within_2']['HARM']) == (0.9729, 0.7025)
    assert (total['v1']['within_3']['HARM'], total['v2']['within_3']['HARM']) == (0.9955, 0.8378)
    halving = {design: outcome(design, 'stale_history', 0.5) for design in ('v1', 'v2')}
    assert (halving['v1']['within_2']['NO_HARM'], halving['v2']['within_2']['NO_HARM']) == (0.0903, 0.0101)
    transient = {design: outcome(design, 'transient_upgrade_failures', 0.0) for design in ('v1', 'v2')}
    assert (transient['v1']['within_2']['HARM'], transient['v2']['within_2']['HARM']) == (0.2923, 0.2364)
    assert calibration.partition_harm(MEASURED_Q, MEASURED_Q, q0, v, 'v2') == pytest.approx(
        calibration.partition_null(MEASURED_Q, q0, v, 'v2')['p_harm'], abs=1e-4)

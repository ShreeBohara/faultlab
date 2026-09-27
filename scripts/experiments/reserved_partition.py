"""Prospective private evaluation cases; no model calls or application mutations.

Only hash/count metadata from historical recipes leaves the inventory scanner.  The
private manifest is for the evaluator, never the Mechanic.  A changed random seed,
delay, failure count, or occurrence does not establish a new fault composition.
"""
from copy import deepcopy
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
import re
import sqlite3

from app.contracts.models import FaultSpec
from app.lab.completion_study import build_case_manifest

ALGORITHM = 'faultlab-reserved-compositions/v1'
INVENTORY_SCHEMA = 'faultlab-exposure-inventory/v1'
PARTITION_SCHEMA = 'faultlab-reserved-partition/v1'
COMMITMENT_SCHEMA = 'faultlab-reserved-commitment/v1'
GUARDS = ['healthy', 'upgrade-18', 'terminal-upgrade-rejection']
SEED = 'faultlab-prospective-repair-2026-09-27-reserved-v1'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def _ordered(primitives):
    return sorted(primitives, key=canonical)


def _normalized_primitives(spec):
    # Cosmetic IDs and seed are excluded. Keep every schedule-affecting field.
    return _ordered([{key: primitive[key] for key in
                      ('kind', 'target_tool', 'target_service', 'occurrence', 'parameters')}
                     for primitive in spec['primitives']])


def material_signature(spec):
    return digest(_normalized_primitives(spec))


def composition_signature(spec):
    return digest(_ordered([
        [p['kind'], p['target_tool'], p['target_service'],
         p['parameters'].get('terminal_status') if p['kind'] == 'F2' else None]
        for p in spec['primitives']]))


def _collect(value, material, composition, counts):
    if isinstance(value, dict):
        primitives = value.get('primitives')
        if isinstance(primitives, list) and all(
            isinstance(p, dict) and p.get('kind') in ('F1', 'F2', 'F3', 'F4')
            and all(key in p for key in ('target_tool', 'target_service', 'occurrence', 'parameters'))
            for p in primitives
        ):
            material.add(material_signature(value))
            composition.add(composition_signature(value))
            counts['recipe_instances'] += 1
        for child in value.values():
            _collect(child, material, composition, counts)
    elif isinstance(value, list):
        for child in value:
            _collect(child, material, composition, counts)
    elif isinstance(value, str) and '"primitives"' in value:
        # Explorer outputs and saved prompts can retain a valid recipe as a JSON
        # string rather than a structured record. Such unexecuted proposals are
        # still prior exposure. Schemas describing the primitives property are
        # not recipes; a possibly truncated actual array fails closed below.
        values, _ = _read_json_or_log(value, strict=False)
        counts['embedded_json_strings'] += 1
        pattern = r'"primitives"\s*:\s*\['
        if len(re.findall(pattern, value)) > sum(len(re.findall(pattern, canonical(v))) for v in values):
            counts['unresolved_recipe_strings'] += 1
        for child in values:
            _collect(child, material, composition, counts)


def _read_json_or_log(text, *, strict=True):
    """Historical CLI outputs include JSON followed by log lines, and two plain logs."""
    try:
        return [json.loads(text)], 'json'
    except json.JSONDecodeError:
        objects, position, decoder = [], 0, json.JSONDecoder()
        while position < len(text):
            if text[position] not in '[{':
                position += 1
                continue
            try:
                value, end = decoder.raw_decode(text, position)
            except json.JSONDecodeError:
                position += 1
                continue
            objects.append(value)
            position = end
        # Never silently drop an unparseable recipe in a log with JSON fragments.
        if strict and text.count('"primitives"') > sum(canonical(v).count('"primitives"') for v in objects):
            raise ValueError('Historical recipe-bearing log cannot be fully decoded')
        return objects, 'mixed_json_log' if objects else 'text_log_without_recipe'


def _file_hash(path):
    hasher = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def _readonly_database(path):
    # Closed WAL-mode backups have read-only directories and no sidecars. Immutable
    # reads are safe only without a nonempty WAL; never discard live WAL contents.
    wal = Path(str(path) + '-wal')
    has_wal = wal.exists() and wal.stat().st_size > 0
    if has_wal and not Path(str(path) + '-shm').exists():
        raise ValueError('Cannot read WAL database without its existing shared-memory file')
    suffix = '' if has_wal else '&immutable=1'
    connection = sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro{suffix}', uri=True)
    connection.execute('PRAGMA query_only=ON')
    return connection


def scan_exposure_inventory(repo_root):
    """Read all audit JSON, artifact JSON, and artifact SQLite recipe-bearing records.

    Freeze this result before selection. It contains no recipes, observations, model
    responses, outcomes, or private case IDs. Source hashes also cover nonempty WALs.
    Later verification uses the frozen inventory, not a rescan containing new cases.
    """
    root = Path(repo_root).resolve()
    material, composition, sources = set(), set(), []
    counts = dict(recipe_instances=0, databases=0, record_databases=0,
                  world_databases=0, matching_record_rows=0, json_files=0,
                  mixed_json_logs=0, text_logs_without_recipe=0,
                  embedded_json_strings=0, unresolved_recipe_strings=0)
    public_manifests = {}
    for name in ('notification-v1', 'upgrade-v1'):
        manifest = build_case_manifest(name)
        public_manifests[name] = digest(manifest)
        _collect(manifest, material, composition, counts)
    paths = set((root / 'artifacts').rglob('*.sqlite3'))
    for directory in ('audit', 'artifacts'):
        paths.update((root / directory).rglob('*.json'))
    if not any(p.suffix == '.sqlite3' for p in paths):
        raise ValueError('Exposure inventory has no historical databases')
    for path in sorted(paths):
        before = path.stat()
        metadata = {'path': str(path.relative_to(root)), 'sha256': _file_hash(path),
                    'bytes': before.st_size}
        wal = Path(str(path) + '-wal')
        wal_before = None
        if wal.exists() and wal.stat().st_size:
            wal_before = (wal.stat().st_size, wal.stat().st_mtime_ns, _file_hash(wal))
            metadata['wal_sha256'] = wal_before[2]
        if path.suffix == '.sqlite3':
            counts['databases'] += 1
            with closing(_readonly_database(path)) as connection:
                names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                recognized = False
                if 'records' in names:
                    recognized = True
                    counts['record_databases'] += 1
                    for (payload,) in connection.execute(
                        "SELECT payload FROM records WHERE instr(payload, 'primitives') > 0"
                    ):
                        counts['matching_record_rows'] += 1
                        _collect(json.loads(payload), material, composition, counts)
                if 'state' in names:
                    recognized = True
                    counts['world_databases'] += 1
                    for (payload,) in connection.execute("SELECT json_extract(value, '$.fault_spec') FROM state"):
                        if payload is None:
                            raise ValueError('World database is missing its fault specification')
                        _collect(json.loads(payload), material, composition, counts)
                if not recognized:
                    raise ValueError('Unrecognized historical database schema')
        else:
            counts['json_files'] += 1
            values, kind = _read_json_or_log(path.read_text())
            if kind != 'json':
                counts[kind + 's' if kind == 'mixed_json_log' else 'text_logs_without_recipe'] += 1
            for value in values:
                _collect(value, material, composition, counts)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Exposure source changed during its inventory read')
        if wal_before and (not wal.exists() or wal_before !=
                          (wal.stat().st_size, wal.stat().st_mtime_ns, _file_hash(wal))):
            raise ValueError('Exposure WAL changed during its inventory read')
        if wal_before is None and wal.exists() and wal.stat().st_size:
            raise ValueError('Exposure WAL appeared during its inventory read')
        sources.append(metadata)
    result = {'schema_version': INVENTORY_SCHEMA, 'algorithm': ALGORITHM,
              'public_manifest_hashes': public_manifests, 'sources': sources, 'counts': counts,
              'material_signatures': sorted(material), 'composition_signatures': sorted(composition)}
    result['inventory_hash'] = digest(result)
    return result


def _validate_inventory(inventory):
    body = {k: v for k, v in inventory.items() if k != 'inventory_hash'}
    if inventory.get('schema_version') != INVENTORY_SCHEMA or inventory.get('algorithm') != ALGORITHM:
        raise ValueError('Unknown exposure inventory')
    if inventory.get('inventory_hash') != digest(body):
        raise ValueError('Exposure inventory hash mismatch')
    if inventory.get('counts', {}).get('unresolved_recipe_strings', 0):
        raise ValueError('Potentially valid truncated historical recipes prevent complete exclusion')
    for key in ('material_signatures', 'composition_signatures'):
        values = inventory.get(key)
        if not isinstance(values, list) or values != sorted(set(values)) or any(
            not isinstance(v, str) or len(v) != 64 or any(c not in '0123456789abcdef' for c in v) for v in values
        ):
            raise ValueError('Invalid exposure signature list')


def candidate_universe():
    """Finite static mechanisms, before outcomes. Twenty-one admissible compositions.

    No optional status-read targets. Exclude same-write F1/F2 preemption, competing
    F2 outcomes, notification after rejection, and early upgrade F4 followed by a
    notification fault. Same-target F4 precedes the other fault on occurrence two.
    The last exclusion is conservative; no Actor outcome is used for selection.
    """
    mechanisms = [
        ('F1', 'update_order', None), ('F1', 'send_confirmation', None),
        ('F2', 'update_order', 'SUCCEEDED'), ('F2', 'update_order', 'FAILED'),
        ('F3', 'get_order', None), ('F4', 'get_order', None),
        ('F4', 'update_order', None), ('F4', 'send_confirmation', None),
    ]
    result = []
    for pair in combinations(mechanisms, 2):
        if all(p[0] == 'F2' for p in pair):
            continue
        if ('F1', 'update_order', None) in pair and any(p[0] == 'F2' for p in pair):
            continue
        if ('F2', 'update_order', 'FAILED') in pair and any(p[1] == 'send_confirmation' for p in pair):
            continue
        if ('F4', 'update_order', None) in pair and any(p[1] == 'send_confirmation' for p in pair):
            continue
        primitives = []
        for kind, tool, terminal in pair:
            parameters = ({'response_delay_ms': 1500} if kind == 'F1' else
                          {'completion_delay_ticks': 3, 'terminal_status': terminal,
                           'failure_code': 'UPGRADE_REJECTED' if terminal == 'FAILED' else None} if kind == 'F2' else
                          {'versions_back': 1} if kind == 'F3' else {'failure_count': 1})
            occurrence = 2 if kind != 'F4' and ('F4', tool, None) in pair else 1
            primitives.append(dict(kind=kind, target_tool=tool,
                                   target_service='notifications' if tool == 'send_confirmation' else 'orders',
                                   occurrence=occurrence, parameters=parameters))
        history = any(p[0] == 'F3' for p in pair)
        result.append({'fixture_id': 'history-v1' if history else 'standard-v1',
                       'expected_version': 4 if history else 1,
                       'expected_outcome': 'CORRECTLY_REJECTED' if ('F2', 'update_order', 'FAILED') in pair else 'COMPLETED',
                       'fault_spec': FaultSpec.model_validate({'seed': 0, 'primitives': _ordered(primitives)}).model_dump(mode='json')})
    return result


def _eligible(inventory):
    _validate_inventory(inventory)
    return [case for case in candidate_universe()
            if material_signature(case['fault_spec']) not in inventory['material_signatures']
            and composition_signature(case['fault_spec']) not in inventory['composition_signatures']]


def availability_summary(inventory):
    eligible = _eligible(inventory)
    return {'candidate_compositions': len(candidate_universe()), 'available_compositions': len(eligible),
            'excluded_compositions': len(candidate_universe()) - len(eligible),
            'required_compositions': 3, 'sufficient': len(eligible) >= 3}


def build_reserved_partition(inventory, seed, *, seed_declaration):
    """Deterministically select once, only after the caller writes the declaration."""
    if seed != SEED or seed_declaration.get('seed') != seed or seed_declaration.get('guards') != GUARDS or any(
        seed_declaration.get(key) is not True for key in ('before_selection', 'before_provider_generation', 'no_resampling')
    ):
        raise ValueError('Seed declaration does not match the fixed prospective design')
    eligible = _eligible(inventory)
    if len(eligible) < 3:
        raise ValueError('Fewer than three unexposed admissible compositions; no substitution allowed')
    selected = sorted(eligible, key=lambda case: sha256((seed + canonical(case)).encode()).hexdigest())[:3]
    public = {case['case_id']: case for case in build_case_manifest('upgrade-v1')['cases']}
    cases = []
    for name in GUARDS:
        case = deepcopy(public[name])
        case.update(case_kind='healthy_guard' if name == 'healthy' else 'known_family_guard',
                    repeats_per_arm=3 if name == 'healthy' else 15)
        cases.append(case)
    for number, value in enumerate(selected, 1):
        case = deepcopy(value)
        case.update(case_id=f'reserved-composition-{number}', name=f'reserved_composition_{number}',
                    case_kind='reserved_composition', repeats_per_arm=15)
        # Seed is deterministic bookkeeping, never the basis for novelty.
        case['fault_spec']['seed'] = int(sha256((seed + canonical(value)).encode()).hexdigest()[:8], 16) % (2 ** 31)
        cases.append(case)
    manifest = {'schema_version': PARTITION_SCHEMA, 'algorithm': ALGORITHM,
                'inventory_hash': inventory['inventory_hash'], 'seed_declaration_hash': digest(seed_declaration),
                'seed_hash': sha256(seed.encode()).hexdigest(), 'cases': cases,
                'case_count': 6, 'paired_repetitions': 78, 'episode_count': 156,
                'no_resampling': True, 'optimizer_access': False, 'ordinary_policy_accepted': False}
    validate_partition(manifest, inventory)
    return manifest


def validate_partition(manifest, inventory):
    _validate_inventory(inventory)
    if manifest.get('schema_version') != PARTITION_SCHEMA or manifest.get('algorithm') != ALGORITHM or manifest.get('inventory_hash') != inventory['inventory_hash']:
        raise ValueError('Partition/inventory identity mismatch')
    if any(manifest.get(k) != v for k, v in dict(case_count=6, paired_repetitions=78, episode_count=156,
                                               no_resampling=True, optimizer_access=False, ordinary_policy_accepted=False).items()):
        raise ValueError('Partition scope or counts changed')
    cases = manifest.get('cases', [])
    if len(cases) != 6 or len({c.get('case_id') for c in cases}) != 6:
        raise ValueError('Partition must have six unique fixed cases')
    public = {c['case_id']: c for c in build_case_manifest('upgrade-v1')['cases']}
    for case, name in zip(cases[:3], GUARDS):
        expected = deepcopy(public[name])
        expected.update(case_kind='healthy_guard' if name == 'healthy' else 'known_family_guard',
                        repeats_per_arm=3 if name == 'healthy' else 15)
        if case != expected:
            raise ValueError('Known-family guard changed')
    admissible = {material_signature(c['fault_spec']): c for c in candidate_universe()}
    seen = set()
    for number, case in enumerate(cases[3:], 1):
        spec = FaultSpec.model_validate(case['fault_spec']).model_dump(mode='json')
        material, composition = material_signature(spec), composition_signature(spec)
        expected = admissible.get(material)
        if expected is None or any(case.get(k) != expected[k] for k in ('fixture_id', 'expected_version', 'expected_outcome')):
            raise ValueError('Reserved case has unreachable, preempted or undeclared schedule')
        if case.get('case_id') != f'reserved-composition-{number}' or case.get('case_kind') != 'reserved_composition' or case.get('repeats_per_arm') != 15:
            raise ValueError('Reserved case identity/count changed')
        if material in inventory['material_signatures'] or composition in inventory['composition_signatures'] or composition in seen:
            raise ValueError('Reserved case is exposed or composition-equivalent')
        seen.add(composition)
    # Membership alone would permit an operator to replace a selected case with
    # another admissible one. Enforce the declared one-shot ordering as well.
    selected = sorted(_eligible(inventory), key=lambda c: sha256((SEED + canonical(c)).encode()).hexdigest())[:3]
    if len(selected) != 3 or manifest.get('seed_hash') != sha256(SEED.encode()).hexdigest():
        raise ValueError('Selection seed or available composition count changed')
    for number, (case, template) in enumerate(zip(cases[3:], selected), 1):
        expected = deepcopy(template)
        expected.update(case_id=f'reserved-composition-{number}', name=f'reserved_composition_{number}',
                        case_kind='reserved_composition', repeats_per_arm=15)
        expected['fault_spec']['seed'] = int(sha256((SEED + canonical(template)).encode()).hexdigest()[:8], 16) % (2 ** 31)
        if case != expected:
            raise ValueError('Partition differs from the declared deterministic first-three selection')
    if sum(c['repeats_per_arm'] for c in cases) != 78:
        raise ValueError('Wrong evaluation repetition count')


def _time(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Commit and generation times must include a timezone')
    return stamp.astimezone(timezone.utc)


def partition_commitment(manifest, inventory, *, committed_at):
    validate_partition(manifest, inventory)
    _time(committed_at)
    result = {'schema_version': COMMITMENT_SCHEMA, 'algorithm': ALGORITHM,
              'committed_at': committed_at, 'partition_hash': digest(manifest),
              'inventory_hash': inventory['inventory_hash'],
              'seed_hash': manifest['seed_hash'], 'seed_declaration_hash': manifest['seed_declaration_hash'],
              'case_count': 6, 'paired_repetitions': 78, 'episode_count': 156,
              'case_kinds': [c['case_kind'] for c in manifest['cases']],
              'no_resampling': True, 'optimizer_access': False, 'ordinary_policy_accepted': False}
    result['commitment_hash'] = digest(result)
    return result


def bind_candidate(commitment, manifest, *, policy_hash, policy_version, study_id,
                   generation_started_at, prior_policy_hashes):
    body = {k: v for k, v in commitment.items() if k != 'commitment_hash'}
    if commitment.get('schema_version') != COMMITMENT_SCHEMA or commitment.get('commitment_hash') != digest(body):
        raise ValueError('Invalid partition commitment')
    if commitment.get('algorithm') != ALGORITHM or any(
        commitment.get(key) != manifest.get(key) for key in
        ('seed_hash', 'seed_declaration_hash', 'case_count', 'paired_repetitions', 'episode_count',
         'no_resampling', 'optimizer_access', 'ordinary_policy_accepted')
    ) or commitment.get('case_kinds') != [c['case_kind'] for c in manifest['cases']]:
        raise ValueError('Commitment scope differs from its private manifest')
    if commitment.get('partition_hash') != digest(manifest) or commitment.get('inventory_hash') != manifest.get('inventory_hash'):
        raise ValueError('Partition changed after commitment')
    if _time(commitment['committed_at']) >= _time(generation_started_at):
        raise ValueError('Partition must be committed strictly before any generation')
    if not isinstance(policy_hash, str) or len(policy_hash) != 64 or any(c not in '0123456789abcdef' for c in policy_hash):
        raise ValueError('Invalid exact candidate hash')
    if policy_hash in prior_policy_hashes:
        raise ValueError('Previously saved policy cannot route as a fresh repair')
    if not isinstance(policy_version, str) or not policy_version.startswith('policy-') or not isinstance(study_id, str) or not study_id.startswith('completion-study-'):
        raise ValueError('Missing exact candidate identity')
    return {'schema_version': 'faultlab-reserved-candidate-binding/v1',
            'commitment_hash': commitment['commitment_hash'], 'partition_hash': commitment['partition_hash'],
            'inventory_hash': commitment['inventory_hash'], 'policy_hash': policy_hash,
            'policy_version': policy_version, 'study_id': study_id,
            'generation_started_at': generation_started_at, 'ordinary_policy_accepted': False}

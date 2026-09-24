#!/usr/bin/env python3
"""Phase 22: build the sealed heldout-2 partition from a committed seed. $0, no service, no model.

Implements the construction rule committed in docs/part2/PHASE20_EXPERIMENT.md Appendix A, and
nothing else. It has no data-dependent branch: given the seed and the two novelty sources, the
output is fixed.

Six cases, in this order (position k = 1..6), every primitive at occurrence 1, each drawn
uniformly from its space (parameters ascending):
  1 no_fault                        no primitive (1 schedule); exempt from novelty
  2 delayed_confirmation_response   F1 send_confirmation, response_delay_ms 1500..3000 (1,501)
  3 delayed_upgrade_success         F2 update_order SUCCEEDED, completion_delay_ticks 1..4
  4 delayed_refusal                 F2 update_order FAILED (UPGRADE_REJECTED), completion_delay_ticks 1..4
  5 stale_history                   F3 get_order, versions_back 1..3, fixture history-v1
  6 transient_upgrade_failures      F4 update_order, failure_count 2..4
Draw (Appendix A item 2): for case k and attempt j = 0, 1, 2, ... the index into the case's
space is int.from_bytes(HMAC-SHA256(key=seed, msg=f"heldout-2:{k}:{j}"), "big") mod |space|;
the first j whose schedule identity is not excluded is taken. k is the case's 1-based position,
the same position that fixes its FaultSpec.seed metadata (2026100000 + k). If every identity of
a space is excluded, the build stops and writes nothing (Phase 22 re-declares that case in the
open); nothing is ever substituted. A cap of MAX_DRAW_ATTEMPTS re-draws is an added stop rule that
Appendix A does not have (declared in PHASE22_EXPERIMENT.md section 2); reaching it also stops the
build and writes nothing.

Novelty (Appendix A item 3): an identity (app.lab.challenge.schedule_identity: scope plus sorted
primitives, seed ignored) is excluded if it occurs in completion manifest 7ab9368e (rebuilt by
app.lab.completion_study.case_manifest() and checked against its hash) or in the private
promotion partition (app.referee.manifests.load_manifest('promotion'), digest-verified), and
only there. The promotion partition is compared in code and no value of it is printed or
written. Two things still depend on it, as Appendix A requires: which draws are taken (so the
manifest_hash, which is harmless while the seed is secret), and the refusal that stops the build
when a whole space is excluded (it names the case, so it reveals that the space is fully covered).
The final-audit file is never loaded (possible overlap with it is disclosed).

The real promotion partition is loaded ONLY for the committed seed (review rounds 1 and 2):
  - the seed's sha256 must equal the single `heldout2-seed-sha256:` line of PHASE22_EXPERIMENT.md
    as committed at the tip of the backup branch (read with `git show`), and every value that line
    has ever held in that branch's history (`git log -p`) must be this one;
  - this file's own sha256 must equal the single `generator-sha256:` line committed there (F6), so
    the program that draws is the one pinned before the seed existed;
  - --out must be the declared artifacts/heldout2/partition, which must not exist yet.
With a known throwaway seed the manifest_hash would answer whether chosen schedules are in the
promotion partition, so any other build must pass --audit-dir with a synthetic partition: the real
audit directory, and any path that is or links to its promotion.json, are refused, and the document
found there must be synthetic (every case id starts with SYNTHETIC_CASE_PREFIX), or the build is
refused without any detail. A deliberate, edited and re-digested copy of the real file is not
prevented. This also enforces section 7.4: the seed is committed (S2) before any draw (S3), and one
seed per unaltered backup-branch history can draw while the declared output exists.

Salt. content_hash(cases) over the fixed case fields alone could be inverted by enumerating the
216,144 combinations of the six spaces in seconds, so a published manifest_hash would reveal
the partition. Each case therefore carries a `salt`, HMAC-SHA256(seed, f"heldout-2:salt:{k}"),
which makes the hash useless without the seed. The salt plays no part in any draw.

Output: a NEW directory (mode 0700; refused if it exists), all files mode 0600, byte-identical
for the same seed and sources (no timestamp, no path):
  heldout-2.json  PRIVATE. The partition document; its 'cases' list is what the held-out
                  check passes to PairedEvaluator (backend/app/lab/heldout_check.py reads exactly
                  this name, PARTITION_FILE_V2). Nobody opens it.
  manifest_hash   content_hash(cases): the value the heldout_checks record carries (and the
                  backend checks against its pin). The v2 check hands PairedEvaluator the
                  26-position expanded list, so EvaluationBatch.manifest_hash is the record's
                  evaluated_manifest_hash, not this value.
  summary.json    PUBLIC. Counts and hashes only (the seed's sha256, manifest_hash, the file's
                  sha256, space sizes, novelty source hashes). It is the only thing printed.

The seed file holds exactly 32 raw bytes from os.urandom, mode 0600 (refused if group or other
may read it), and must match --expect-seed-sha256, the commitment recorded before any draw.
`--new-seed PATH` creates such a file (exclusively, 0600) and prints only its sha256.

Usage:
  python scripts/experiments/make_heldout_partition.py --new-seed PATH
  python scripts/experiments/make_heldout_partition.py --seed PATH --expect-seed-sha256 HEX --out artifacts/heldout2/partition
  (tests and dry builds: add --audit-dir DIR holding a synthetic promotion.json)
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import hmac
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
from copy import deepcopy

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.contracts.models import FaultSpec, content_hash  # noqa: E402
from app.lab.challenge import schedule_identity  # noqa: E402
from app.simulator.faults import validate_schedule  # noqa: E402
from app.simulator.storage import WorldError  # noqa: E402

SCHEMA = 'faultlab-heldout2-partition/v1'
SUMMARY_SCHEMA = 'faultlab-heldout2-partition-summary/v1'
PARTITION = 'heldout-2'
RULE = 'docs/part2/PHASE20_EXPERIMENT.md Appendix A'
SCOPE = 'orders.upgrade_then_confirm/v1'
COMPLETION_MANIFEST_HASH = '7ab9368e7e86ec7f32fe6c57e99b8530853326f18d10f3687581be024aa38483'
SEED_BYTES = 32
SEED_METADATA_BASE = 2026100000
# A cap on re-draws, never reached in practice: the smallest space (3) with at most 2 of its
# identities excluded misses every attempt with probability (2/3)^1000. Reaching it stops the build.
MAX_DRAW_ATTEMPTS = 1000
FIXTURE_VERSIONS = {'standard-v1': 1, 'history-v1': 4}
# The private file's name is the backend's PARTITION_FILE_V2 (heldout_check.py): '<partition>.json'.
CASES_FILE, HASH_FILE, SUMMARY_FILE = f'{PARTITION}.json', 'manifest_hash', 'summary.json'
# Where the one real build writes, and where its seed is committed before any draw (§7.4 S2-S3).
DECLARED_OUT = 'artifacts/heldout2/partition'
BACKUP_REF = 'backup/part2-2026-09-22'
COMMITTED_PROTOCOL = 'docs/part2/PHASE22_EXPERIMENT.md'
SEED_PIN = 'heldout2-seed-sha256:'
GENERATOR_PIN = 'generator-sha256:'
# A document given with --audit-dir must be synthetic: every case id carries this prefix (round 2).
SYNTHETIC_CASE_PREFIX = 'synthetic-'
SERVICE = {'send_confirmation': 'notifications', 'update_order': 'orders', 'get_order': 'orders'}
DISCLOSURES = (
    'heldout-2 is held out from the checked policy\'s generation and selection, not unseen by the operators',
    'the final-audit file is never loaded, so overlap with it is possible and is not checked',
    'novelty is checked against completion manifest 7ab9368e and the promotion partition only, not the '
    'development store: heldout-2 cases can be development-measured schedules',
)


class PartitionError(RuntimeError):
    """The build stops; nothing is written and nothing is substituted."""


def _primitive(kind, tool, parameters):
    return {'kind': kind, 'target_tool': tool, 'target_service': SERVICE[tool], 'occurrence': 1,
            'parameters': parameters}


def _f2(ticks, status):
    return _primitive('F2', 'update_order', {'completion_delay_ticks': ticks, 'terminal_status': status,
                                            'failure_code': 'UPGRADE_REJECTED' if status == 'FAILED' else None})


# (position k, name, fixture, space: primitive lists in ascending parameter order). Appendix A order.
CASE_KINDS = (
    (1, 'no_fault', 'standard-v1', ((),)),
    (2, 'delayed_confirmation_response', 'standard-v1',
     tuple((_primitive('F1', 'send_confirmation', {'response_delay_ms': ms}),) for ms in range(1500, 3001))),
    (3, 'delayed_upgrade_success', 'standard-v1', tuple((_f2(d, 'SUCCEEDED'),) for d in range(1, 5))),
    (4, 'delayed_refusal', 'standard-v1', tuple((_f2(d, 'FAILED'),) for d in range(1, 5))),
    (5, 'stale_history', 'history-v1',
     tuple((_primitive('F3', 'get_order', {'versions_back': v}),) for v in range(1, 4))),
    (6, 'transient_upgrade_failures', 'standard-v1',
     tuple((_primitive('F4', 'update_order', {'failure_count': c}),) for c in range(2, 5))),
)
NOVELTY_EXEMPT = frozenset({'no_fault'})


def fault_spec(position, primitives):
    """Canonical FaultSpec JSON; the seed is metadata (Appendix A item 2)."""
    return FaultSpec.model_validate({'seed': SEED_METADATA_BASE + position,
                                     'primitives': [dict(p) for p in primitives]}).model_dump(mode='json')


def draw_spaces():
    """{name: (position, fixture, (fault_spec, ...))}, every schedule validated. Callers get copies."""
    return deepcopy(_draw_spaces())


@functools.lru_cache(maxsize=None)
def _draw_spaces():
    spaces = {}
    for position, name, fixture, space in CASE_KINDS:
        specs = tuple(fault_spec(position, primitives) for primitives in space)
        for spec in specs:
            problem = schedule_problem(spec, fixture)
            if problem:
                raise PartitionError(f'draw space {name} holds an invalid schedule: {problem}')
        spaces[name] = (position, fixture, specs)
    return spaces


@functools.lru_cache(maxsize=None)
def space_identities():
    """{name: (schedule identity, ...)} in space order."""
    return {name: tuple(identity(spec) for spec in specs) for name, (_, _, specs) in _draw_spaces().items()}


def schedule_problem(spec, fixture):
    """FaultSpec (canonical form), occurrence 1, the fixture, and the simulator's validate_schedule."""
    try:
        model = FaultSpec.model_validate(spec)
    except ValueError as error:
        return f'FaultSpec: {type(error).__name__}'
    if model.model_dump(mode='json') != spec:
        return 'fault_spec is not in canonical FaultSpec form'
    if any(p.occurrence != 1 for p in model.primitives):
        return 'occurrence is not 1'
    if fixture not in FIXTURE_VERSIONS:
        return 'unknown fixture'
    history = [{'version': v} for v in range(1, FIXTURE_VERSIONS[fixture] + 1)]
    try:
        validate_schedule(model, history)
    except WorldError as error:
        return f'validate_schedule: WorldError {error.code}'
    return None


def identity(spec):
    return schedule_identity(FaultSpec.model_validate(spec))


def draw_index(seed, position, attempt, size):
    digest = hmac.new(seed, f'heldout-2:{position}:{attempt}'.encode('utf-8'), hashlib.sha256).digest()
    return int.from_bytes(digest, 'big') % size


def case_salt(seed, position):
    return hmac.new(seed, f'heldout-2:salt:{position}'.encode('utf-8'), hashlib.sha256).hexdigest()


def check_seed(seed):
    if not isinstance(seed, (bytes, bytearray)) or len(seed) != SEED_BYTES:
        raise PartitionError(f'the seed must be exactly {SEED_BYTES} bytes')
    return bytes(seed)


def build_cases(seed, excluded):
    """The six cases. `excluded` is a set of schedule identities; the no-fault case is exempt.
    Pure: no file, store or network. Raises PartitionError (naming the case only) if a whole
    space is excluded or the attempt cap is reached."""
    seed = check_seed(seed)
    cases = []
    for name, (position, fixture, specs) in _draw_spaces().items():
        exempt = name in NOVELTY_EXEMPT
        identities = space_identities()[name]
        if not exempt and all(i in excluded for i in identities):
            raise PartitionError(f'case {position} ({name}): every identity of its space is excluded; the build '
                                 f'stops and Phase 22 must re-declare this case in the open')
        for attempt in range(MAX_DRAW_ATTEMPTS):
            index = draw_index(seed, position, attempt, len(specs))
            if exempt or identities[index] not in excluded:
                break
        else:
            raise PartitionError(f'case {position} ({name}): no admissible draw within {MAX_DRAW_ATTEMPTS} attempts')
        spec = deepcopy(specs[index])
        problem = schedule_problem(spec, fixture)
        if problem:
            raise PartitionError(f'case {position} ({name}): {problem}')
        cases.append({'case_id': f'{PARTITION}-{position}', 'name': name, 'fixture_id': fixture,
                      'expected_version': FIXTURE_VERSIONS[fixture], 'fault_spec': spec,
                      'salt': case_salt(seed, position)})
    return cases


# ---------------------------------------------------------------- novelty sources

def completion_manifest():
    """Completion manifest 7ab9368e: public (built from the development manifest), hash-checked."""
    from app.lab.completion_study import case_manifest
    manifest = case_manifest()
    if content_hash(manifest) != COMPLETION_MANIFEST_HASH:
        raise PartitionError('case_manifest() no longer hashes to 7ab9368e...; refusing to build')
    return manifest


def promotion_identities(audit_dir=None):
    """Schedule identities of the private promotion partition, digest-verified by the referee's own
    loader. Only the name 'promotion' is ever requested, so the final-audit file is never loaded.
    Nothing about the partition leaves this function: any failure is reported without its message
    or traceback, because a validation error would quote the partition's own values. A document
    given with --audit-dir must be synthetic (every case id starts with SYNTHETIC_CASE_PREFIX);
    otherwise the build is refused with a fixed message and nothing is drawn (review round 2)."""
    from app.referee.manifests import load_manifest
    identities, synthetic = None, True
    try:
        manifest = load_manifest('promotion', directory=audit_dir)
        if audit_dir is not None:
            synthetic = all(isinstance(case, dict) and str(case.get('case_id', '')).startswith(SYNTHETIC_CASE_PREFIX)
                            for case in manifest['cases'])
        if synthetic:
            identities = excluded_identities(manifest)
    except Exception:  # noqa: BLE001
        identities = None
    if not synthetic:
        raise PartitionError(f'--audit-dir must hold a synthetic partition (every case id starting '
                             f'{SYNTHETIC_CASE_PREFIX!r}); details withheld')
    if identities is None:
        raise PartitionError('the promotion partition could not be loaded or verified (details withheld)')
    return identities


def excluded_identities(*manifests):
    return frozenset(identity(case['fault_spec']) for manifest in manifests for case in manifest['cases'])


# ---------------------------------------------------------------- when the real partition may be read

def is_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _git(*arguments):
    """stdout of a read-only git command in this repository, or None if it fails."""
    try:
        done = subprocess.run(['git', '-C', str(ROOT), *arguments], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _single_pin(text, prefix):
    """The value of the single column-0 `prefix` line, when it is bare 64 lowercase hex; else None."""
    values = [line[len(prefix):].strip() for line in (text or '').splitlines() if line.startswith(prefix)]
    return values[0] if len(values) == 1 and is_sha256(values[0]) else None


def committed_seed_sha256():
    """The seed commitment as committed on the backup branch (§7.4 S2), or None when there is no
    single well-formed `heldout2-seed-sha256:` line there (not committed yet, or git unavailable)."""
    return _single_pin(_git('show', f'{BACKUP_REF}:{COMMITTED_PROTOCOL}'), SEED_PIN)


def committed_generator_sha256():
    """The generator pin committed at the backup branch's tip (§8 F6), or None."""
    return _single_pin(_git('show', f'{BACKUP_REF}:{COMMITTED_PROTOCOL}'), GENERATOR_PIN)


def committed_seed_history():
    """Every 64-hex value the `heldout2-seed-sha256:` line has held in the backup branch's history of
    the protocol (`git log -p`), or None if git fails. A rewritten history defeats this; the history
    is the audit trail, and the operator also records the seed's sha256 outside the repository."""
    log = _git('log', '-p', '--format=', BACKUP_REF, '--', COMMITTED_PROTOCOL)
    if log is None:
        return None
    values = set()
    for line in log.splitlines():
        body = line[1:] if line[:1] in ('+', '-', ' ') else line
        if body.startswith(SEED_PIN) and is_sha256(body[len(SEED_PIN):].strip()):
            values.add(body[len(SEED_PIN):].strip())
    return values


def own_sha256():
    """The sha256 of this generator file, as pinned (generator-sha256) and as recorded in summary.json."""
    return hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()


def real_partition_problem(seed, out):
    """Why this build may NOT read the real promotion partition, or None when it may: only the
    committed seed, only by the pinned generator, only into the declared output, only once."""
    committed = committed_seed_sha256()
    if committed is None:
        return (f'no seed commitment on {BACKUP_REF} ({COMMITTED_PROTOCOL}, line {SEED_PIN!r}); commit it first '
                f'(§7.4 S2), or pass --audit-dir with a synthetic partition')
    if hashlib.sha256(seed).hexdigest() != committed:
        return 'this seed is not the committed one; only the committed seed may read the promotion partition'
    if committed_seed_history() != {committed}:
        return (f'the {SEED_PIN!r} line on {BACKUP_REF} has held another value (or its history cannot be read); '
                f'only one seed may ever draw')
    pinned = committed_generator_sha256()
    if pinned is None:
        return f'no generator pin on {BACKUP_REF} ({COMMITTED_PROTOCOL}, line {GENERATOR_PIN!r}); commit it first (§8 F6)'
    if own_sha256() != pinned:
        return f'this generator is not the one pinned on {BACKUP_REF} (line {GENERATOR_PIN!r})'
    if pathlib.Path(out).resolve() != (ROOT / DECLARED_OUT).resolve():
        return f'--out must be {DECLARED_OUT} for the committed seed'
    if (ROOT / DECLARED_OUT).exists() or (ROOT / DECLARED_OUT).is_symlink():
        return f'{DECLARED_OUT} exists; the partition is built once and never regenerated'
    return None


def is_real_audit_dir(directory):
    """The real audit directory, or a directory whose promotion.json is (or links to) the real file.
    Only metadata is compared (resolve and stat); no file is opened. A copy is caught later, by the
    synthetic case-id rule in promotion_identities (round 2)."""
    from app.referee.manifests import AUDIT_DIR
    directory, real = pathlib.Path(directory), pathlib.Path(AUDIT_DIR)
    if directory.resolve() == real.resolve():
        return True
    given, real_file = directory / 'promotion.json', real / 'promotion.json'
    if given.resolve() == real_file.resolve():
        return True
    try:
        return given.exists() and real_file.exists() and os.path.samefile(given, real_file)
    except OSError:
        return True                       # cannot tell: refuse rather than risk the real file


# ---------------------------------------------------------------- documents

def dumps(value):
    return json.dumps(value, indent=2, sort_keys=True) + '\n'


def seed_sha256(seed):
    return hashlib.sha256(check_seed(seed)).hexdigest()


def partition_documents(seed, excluded, *, promotion_default=True, generator_sha256=None):
    """{file name: bytes} for the three files. Deterministic in (seed, excluded, code)."""
    cases = build_cases(seed, excluded)
    manifest_hash = content_hash(cases)
    document = {'schema_version': SCHEMA, 'partition': PARTITION, 'access': 'PRIVATE_EVALUATOR', 'scope': SCOPE,
                'rule': RULE, 'seed_sha256': seed_sha256(seed), 'cases': cases, 'manifest_hash': manifest_hash,
                'manifest_hash_definition': 'content_hash(cases)'}
    cases_bytes = dumps(document).encode('utf-8')
    summary = {'schema_version': SUMMARY_SCHEMA, 'partition': PARTITION, 'rule': RULE,
               'seed_sha256': seed_sha256(seed), 'manifest_hash': manifest_hash,
               'manifest_hash_definition': 'content_hash(cases), salted per case from the seed',
               'cases_file_sha256': hashlib.sha256(cases_bytes).hexdigest(),
               'generator_sha256': generator_sha256 or own_sha256(),
               'case_count': len(cases),
               'space_sizes': {name: len(specs) for name, (_, _, specs) in _draw_spaces().items()},
               'novelty': {'completion_manifest_hash': COMPLETION_MANIFEST_HASH,
                           'promotion_partition': 'compared in code; nothing about it is recorded',
                           'promotion_partition_default_path': bool(promotion_default),
                           'final_audit_loaded': False,
                           'exempt': sorted(NOVELTY_EXEMPT)},
               'disclosures': list(DISCLOSURES)}
    return {CASES_FILE: cases_bytes, HASH_FILE: (manifest_hash + '\n').encode('utf-8'),
            SUMMARY_FILE: dumps(summary).encode('utf-8')}


def write_private(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, 'wb') as handle:
            descriptor = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor is not None:
            os.close(descriptor)


def write_partition(out, documents):
    """Writes into a fresh sibling temp directory (0700) and renames it into place: the target is
    never overwritten and never left half-written."""
    out = pathlib.Path(out)
    if out.exists() or out.is_symlink():
        raise PartitionError(f'{out} exists; refusing to overwrite a partition')
    if not out.parent.is_dir():
        raise PartitionError(f'{out.parent} is not a directory')
    staging = pathlib.Path(tempfile.mkdtemp(prefix='.heldout-2-', dir=out.parent))
    try:
        os.chmod(staging, 0o700)
        for name, data in documents.items():
            write_private(staging / name, data)
        if out.exists() or out.is_symlink():
            raise PartitionError(f'{out} appeared while building; refusing to overwrite it')
        os.rename(staging, out)
    except BaseException:
        for child in staging.glob('*'):
            child.unlink()
        staging.rmdir()
        raise
    return out


# ---------------------------------------------------------------- seed file

def read_seed(path, expected_sha256):
    path = pathlib.Path(path)
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode):
        raise PartitionError('the seed path is not a regular file')
    if mode & 0o077:
        raise PartitionError('the seed file is readable or writable by group or others; chmod 600 it')
    seed = path.read_bytes()
    if len(seed) != SEED_BYTES:
        raise PartitionError(f'the seed file must hold exactly {SEED_BYTES} raw bytes (os.urandom), not {len(seed)}')
    if not expected_sha256 or hashlib.sha256(seed).hexdigest() != expected_sha256.strip().lower():
        raise PartitionError('the seed does not match --expect-seed-sha256 (the committed seed hash)')
    return seed


def new_seed(path):
    """32 bytes from os.urandom, written exclusively with mode 0600. Returns only its sha256."""
    seed = os.urandom(SEED_BYTES)
    try:
        write_private(pathlib.Path(path), seed)
    except FileExistsError:
        raise PartitionError(f'{path} exists; a seed file is never overwritten') from None
    return hashlib.sha256(seed).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--new-seed', type=pathlib.Path, help='create a fresh seed file (0600) and print its sha256')
    parser.add_argument('--seed', type=pathlib.Path, help='the committed seed file (32 raw bytes, mode 0600)')
    parser.add_argument('--expect-seed-sha256', help='the sha256 committed for the seed before any draw')
    parser.add_argument('--out', type=pathlib.Path, help='a NEW partition directory')
    parser.add_argument('--audit-dir', type=pathlib.Path, help=argparse.SUPPRESS)   # tests only: synthetic promotion
    args = parser.parse_args(argv)
    try:
        if args.new_seed:
            if args.seed or args.out:
                raise PartitionError('--new-seed runs alone')
            print(json.dumps({'seed_sha256': new_seed(args.new_seed)}))
            return 0
        if not (args.seed and args.out and args.expect_seed_sha256):
            raise PartitionError('--seed, --expect-seed-sha256 and --out are required')
        seed = read_seed(args.seed, args.expect_seed_sha256)
        if args.audit_dir is None:
            problem = real_partition_problem(seed, args.out)
            if problem:
                raise PartitionError(problem)
        elif is_real_audit_dir(args.audit_dir):
            raise PartitionError('--audit-dir is for a synthetic partition; the real one is read only for the '
                                 'committed seed, without --audit-dir')
        excluded = excluded_identities(completion_manifest()) | promotion_identities(args.audit_dir)
        documents = partition_documents(seed, excluded, promotion_default=args.audit_dir is None)
        write_partition(args.out, documents)
    except PartitionError as error:
        print(f'refused: {error}', file=sys.stderr)
        return 2
    print(documents[SUMMARY_FILE].decode('utf-8'), end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

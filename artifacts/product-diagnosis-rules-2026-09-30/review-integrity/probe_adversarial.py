"""Integrity review ($0): adversarial offline checks of scripts/experiments/diagnosis_probe.py.

Run from faultlab/backend:  ../.venv/bin/python -B ../artifacts/product-diagnosis-rules-2026-09-30/review-integrity/probe_adversarial.py

A strict guard is installed first: any open of a file named .env under the repository, any non-loopback socket
connect / create_connection / sendto / getaddrinfo, and any creation of an AF_INET/AF_INET6 socket are refused and
counted. Output folders are under /Users/shree/FaultLab_Scratch/review-integrity-2026-09-30/ and deleted at the end.
No provider is ever built: the live path gets a scripted provider through main(provider_factory=...).
"""
import asyncio
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import socket
import sys

sys.dont_write_bytecode = True
REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / 'backend'
sys.path.insert(0, str(BACKEND))
os.environ['PYTHON_DOTENV_DISABLED'] = '1'

VIOLATIONS = []


def _audit(event, args):
    if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.fsdecode(args[0])
        if os.path.basename(path) == '.env':
            VIOLATIONS.append(('env-open', path))
            raise PermissionError('review guard: .env open refused')


sys.addaudithook(_audit)

_socket_init = socket.socket.__init__


def _init(self, family=-1, type=-1, proto=-1, fileno=None):
    if family in (socket.AF_INET, socket.AF_INET6):
        VIOLATIONS.append(('inet-socket', family))
        raise PermissionError('review guard: INET socket refused')
    return _socket_init(self, family, type, proto, fileno)


socket.socket.__init__ = _init


def _refuse(name):
    def inner(*args, **kwargs):
        VIOLATIONS.append((name, repr(args)[:120]))
        raise PermissionError(f'review guard: {name} refused')
    return inner


socket.getaddrinfo = _refuse('getaddrinfo')
socket.create_connection = _refuse('create_connection')
socket.gethostbyname = _refuse('gethostbyname')

from app.providers.runtime import RuntimeGeneration, RuntimeProviderError  # noqa: E402

SCRIPT = REPO / 'scripts/experiments/diagnosis_probe.py'
SCRATCH = pathlib.Path('/Users/shree/FaultLab_Scratch/review-integrity-2026-09-30')
MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
RESULTS = {}


def load():
    spec = importlib.util.spec_from_file_location('diagnosis_probe_review', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = load()


class Scripted:
    def __init__(self, mode):
        self.mode, self.calls = mode, 0

    async def complete(self, messages, **kwargs):
        self.calls += 1
        if self.mode == 'ok':
            return RuntimeGeneration('{"proposed_kind":"INCONCLUSIVE","hypothesis":"h","evidence_ids":["x"],"requested_intervention_id":null}',
                                     MODEL, input_tokens=9000, output_tokens=50)
        if self.mode == 'connection':
            raise RuntimeProviderError('down', code='CONNECTION_ERROR')
        if self.mode == 'other_model':
            return RuntimeGeneration('{}', 'some/other-model', input_tokens=1, output_tokens=1)
        if self.mode == 'boom':
            raise ValueError('unexpected')
        raise AssertionError(self.mode)


def tree_snapshot():
    """sha256 of every file the harness could plausibly touch in the repo (scripts, backend app, artifacts of this topic)."""
    out = {}
    for base in ('scripts', 'backend/app', 'artifacts/product-diagnosis-rules-2026-09-30/probe-inputs',
                 'artifacts/product-diagnosis-rules-2026-09-30/probe-plan'):
        for path in sorted((REPO / base).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                out[str(path.relative_to(REPO))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def declaration(plan, out, **changes):
    value = probe.declaration_template(plan, str(pathlib.Path(out).resolve()))
    value.update(approved_by='review test (never live)', preconditions={'ledger_checked': True, 'dashboard_closed': True, 'no_other_paid_run': True})
    value.update(changes)
    return value


def write_declaration(folder, value):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'DECLARATION.json'
    path.write_text(json.dumps(value, sort_keys=True))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)
    before = tree_snapshot()
    plan, _ = probe.build_plan()
    RESULTS['plan_hash'] = plan['plan_hash']
    RESULTS['harness_sha256'] = plan['harness_sha256']

    # 1. Dry run (default) from an empty working folder: prints, writes nothing, builds no provider.
    empty = SCRATCH / 'dry-cwd'; empty.mkdir()
    built = []
    os.chdir(empty)
    code = probe.main([], provider_factory=lambda: built.append(1) or Scripted('ok'))
    RESULTS['dry_run'] = {'exit': code, 'wrote': sorted(p.name for p in empty.iterdir()), 'provider_built': bool(built)}
    code = probe.main(['--dry-run'], provider_factory=lambda: built.append(1) or Scripted('ok'))
    RESULTS['dry_run_flag'] = {'exit': code, 'wrote': sorted(p.name for p in empty.iterdir()), 'provider_built': bool(built)}
    os.chdir(BACKEND)

    # 2. Refusals: each must return 2 with no provider built and no output folder created.
    refusals = {}
    good_out = SCRATCH / 'live-ok'
    decl_dir = SCRATCH / 'declarations'
    cases = {
        'no_declaration': (['--execute-live', '--out', str(SCRATCH / 'r1')], None),
        'no_out': (['--execute-live'], None),
    }
    path, digest = write_declaration(decl_dir / 'good', declaration(plan, SCRATCH / 'r3'))
    cases['wrong_sha'] = (['--execute-live', '--out', str(SCRATCH / 'r3'), '--declaration', str(path), '--declaration-sha256', '0' * 64], None)
    cases['sha_without_file'] = (['--execute-live', '--out', str(SCRATCH / 'r3'), '--declaration-sha256', digest], None)
    for label, changes in {'cap_9': {'spend_cap_dollars': 9.0}, 'cap_6': {'spend_cap_dollars': 6.0}, 'cap_bool': {'spend_cap_dollars': True},
                           'cap_string': {'spend_cap_dollars': '8'}, 'other_harness': {'harness_sha256': '1' * 64},
                           'other_plan': {'plan_hash': '2' * 64}, 'other_model': {'model': 'deepseek-ai/DeepSeek-V3.1'},
                           'no_approver': {'approved_by': '  '}, 'precondition_false': {'preconditions': {'ledger_checked': True, 'dashboard_closed': False, 'no_other_paid_run': True}},
                           'no_outcomes': {'pre_registered_outcomes': {'P1': 'x'}}, 'other_folder': {'output_folder': str(SCRATCH / 'elsewhere')}}.items():
        out = SCRATCH / f'r-{label}'
        path, digest = write_declaration(decl_dir / label, declaration(plan, out, **changes))
        cases[label] = (['--execute-live', '--out', str(out), '--declaration', str(path), '--declaration-sha256', digest], out)
    # Non-empty output folder.
    busy = SCRATCH / 'r-busy'; busy.mkdir(); (busy / 'old.txt').write_text('x')
    path, digest = write_declaration(decl_dir / 'busy', declaration(plan, busy))
    cases['non_empty_out'] = (['--execute-live', '--out', str(busy), '--declaration', str(path), '--declaration-sha256', digest], None)
    for label, (argv, out) in cases.items():
        made = []
        code = probe.main(argv, provider_factory=lambda: made.append(1) or Scripted('ok'))
        refusals[label] = {'exit': code, 'provider_built': bool(made), 'out_created': bool(out and out.exists())}
    RESULTS['refusals'] = refusals

    # 3. A declared scripted run: 140 calls charged before sending; files only under --out.
    runs = {}
    for mode in ('ok', 'connection', 'other_model', 'boom'):
        out = SCRATCH / f'live-{mode}'
        path, digest = write_declaration(decl_dir / f'live-{mode}', declaration(plan, out))
        provider = Scripted(mode)
        try:
            code = probe.main(['--execute-live', '--out', str(out), '--declaration', str(path), '--declaration-sha256', digest],
                              provider_factory=lambda provider=provider: provider)
            error = None
        except Exception as caught:   # 'boom' propagates by design (ABORTED)
            code, error = None, f'{type(caught).__name__}: {caught}'
        manifest = json.loads((out / 'manifest.json').read_text()) if (out / 'manifest.json').exists() else None
        runs[mode] = {'exit': code, 'error': error, 'provider_calls': provider.calls,
                      'status': (manifest or {}).get('status'), 'ledger': (manifest or {}).get('ledger'),
                      'files': sorted(p.name for p in out.iterdir()) if out.exists() else None,
                      'charged_within_cap': ((manifest or {}).get('ledger') or {}).get('charged_dollar_upper_bound', 0) <= 8.0}
    RESULTS['scripted_runs'] = runs

    # 4. A tighter declared cap: 7.00 leaves room for no retry at all.
    out = SCRATCH / 'live-cap7'
    path, digest = write_declaration(decl_dir / 'cap7', declaration(plan, out, spend_cap_dollars=7.0))
    provider = Scripted('connection')
    code = probe.main(['--execute-live', '--out', str(out), '--declaration', str(path), '--declaration-sha256', digest],
                      provider_factory=lambda: provider)
    manifest = json.loads((out / 'manifest.json').read_text())
    RESULTS['cap_7_all_failing'] = {'exit': code, 'provider_calls': provider.calls, 'ledger': manifest['ledger'],
                                    'retry_calls_allowed_by_cap': manifest['retry_calls_allowed_by_cap']}

    after = tree_snapshot()
    RESULTS['repo_files_changed_by_harness'] = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    shutil.rmtree(SCRATCH)
    RESULTS['scratch_deleted'] = not SCRATCH.exists()
    RESULTS['guard_violations'] = VIOLATIONS
    print(json.dumps(RESULTS, indent=1, sort_keys=True, default=str))


if __name__ == '__main__':
    main()

"""Old protocols after the fixer's changes vs the checkpoint without v4 ($0, offline).

Re-runs the integrity reviewer's probe (review-integrity/probes/test_reviewer_probe_old_protocols.py, unchanged) in a
scratch copy of the CURRENT working tree (backend copied, backend/app/referee and contracts/audit/taskpacks/scripts/docs
symlinked; outside the Desktop), and compares its output with the reviewer's saved checkpoint output
(review-integrity/probes/probe-old-checkpoint.json: backup/part2-2026-09-22 = 4d1c21b, no v4) using the reviewer's
masking: ids and digests are already numbered by first appearance; created_at timestamps and the 16-hex
registration-id suffixes (they embed the runtime) are masked. Expected: every scenario (v1 reference and native, v2,
v3 native/reference seeded and empty, v3 with pre-check) identical; only run_options_ids differs (v4 appended fifth).
Run from faultlab/:  .venv/bin/python artifacts/product-discovery-v4-2026-09-30/fixer/old_protocol_probe.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROBES = HERE.parent / 'review-integrity' / 'probes'
SCRATCH = Path('/Users/shree/FaultLab_Scratch/fixer-v4-probe/tree')
OUT = HERE / 'probe-old-fixed.json'


def build():
    if SCRATCH.parent.exists():
        shutil.rmtree(SCRATCH.parent)
    SCRATCH.mkdir(parents=True)
    def ignore(directory, names):
        skip = {'__pycache__', '.pytest_cache'}
        if Path(directory) == ROOT / 'backend' / 'app':
            skip.add('referee')
        return [name for name in names if name in skip]
    shutil.copytree(ROOT / 'backend', SCRATCH / 'backend', ignore=ignore)
    (SCRATCH / 'backend' / 'app' / 'referee').symlink_to(ROOT / 'backend' / 'app' / 'referee')
    for name in ('contracts', 'audit', 'taskpacks', 'scripts', 'docs'):
        (SCRATCH / name).symlink_to(ROOT / name)
    shutil.copy2(PROBES / 'test_reviewer_probe_old_protocols.py', SCRATCH / 'backend' / 'tests' / 'lab' / 'test_reviewer_probe_old_protocols.py')


MASKS = [(re.compile(r'"created_at":"[^"]*"'), '"created_at":"<T>"'), (re.compile(r'\\"created_at\\":\\"[^"\\]*\\"'), '\\"created_at\\":\\"<T>\\"'),
         (re.compile(r'-[0-9a-f]{16}\b'), '-<REG>')]


def mask(value):
    text = json.dumps(value, sort_keys=True)
    for pattern, replacement in MASKS:
        text = pattern.sub(replacement, text)
    return text


def main():
    build()
    result = subprocess.run([str(ROOT / '.venv' / 'bin' / 'python'), '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                             'tests/lab/test_reviewer_probe_old_protocols.py'], cwd=SCRATCH / 'backend', capture_output=True, text=True,
                            env={'PATH': '/usr/bin:/bin', 'PYTHON_DOTENV_DISABLED': '1', 'PYTHONDONTWRITEBYTECODE': '1',
                                 'HOME': str(SCRATCH), 'REVIEW_OUT': str(OUT)})
    print(result.stdout.strip().splitlines()[-1] if result.stdout.strip() else result.stderr[-2000:])
    shutil.rmtree(SCRATCH.parent)
    if result.returncode:
        return result.returncode
    before = json.loads((PROBES / 'probe-old-checkpoint.json').read_text())
    after = json.loads(OUT.read_text())
    lines = ['Fixer: old-protocol probe, reviewer checkpoint (4d1c21b, no v4) vs the current tree after the fixer '
             '(reviewer masking: created_at and 16-hex registration-id suffixes).']
    ok = True
    for key in sorted(set(before) | set(after)):
        if isinstance(before.get(key), dict) and isinstance(after.get(key), dict):
            fields = sorted(f for f in set(before[key]) | set(after[key]) if mask(before[key].get(f)) != mask(after[key].get(f)))
            ok &= not fields
            b = before[key]
            lines.append(f"{key} | messages {len(b['messages'])} selections {len(b['selections'])} actor runs {len(b['runner_recipes'])} "
                         f"ledger calls {b['ledger_used_calls']} state {b['state']} | differing fields: {', '.join(fields) or 'none'}")
        else:
            same = mask(before.get(key)) == mask(after.get(key))
            if key != 'run_options_ids':
                ok &= same
            lines.append(f'{key} {"EQUAL" if same else "DIFF"}' + ('' if same else f' {before.get(key)} -> {after.get(key)}'))
    lines.append(f'ALL SCENARIOS IDENTICAL: {ok}')
    (HERE / 'probe-old-compare.txt').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())

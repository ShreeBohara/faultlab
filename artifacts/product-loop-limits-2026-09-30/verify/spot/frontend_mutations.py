"""Verifier frontend negative controls for P-LOW-2 ($0, offline), in a SCRATCH copy of the frontend only.

Scratch frontend: /Users/shree/FaultLab_Scratch/verify-loop-limits/tree/frontend (src, tests without .results, configs copied
from the working tree; node_modules symlinked to the real one; the scratch vite.config.ts gets its own cacheDir so no
cache is written into the real node_modules). Each mutation undoes one P-LOW-2 text/display fix; the frontend unit test
tests/loop-limits.test.tsx must fail. Files restored and sha256-checked after each mutation.
"""
import hashlib, os, shutil, subprocess, sys
REAL = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/frontend'
FRONT = '/Users/shree/FaultLab_Scratch/verify-loop-limits/tree/frontend'
CACHE = '/Users/shree/FaultLab_Scratch/verify-loop-limits/vite-cache'
LL, LLC = 'src/loopLimits.ts', 'src/components/LoopLimits.tsx'
MUTATIONS = [
    ('FORMAT_REPAIR record text back to "not sent"', LL,
     "first turn sent (its answer is saved); its format-repair turn was not sent. ", "not sent. "),
    ('FORMAT_REPAIR badge back to "Search ended, not sent"', LL,
     "'Search ended, repair turn not sent'", "'Search ended, not sent'"),
    ('Badge not capitalised', LL, "SELECTED: 'Selected'", "SELECTED: 'selected'"),
    ('"in full" line shown for an unsent request too', LLC, "{row.outcome === 'COMPACTED' && !!row.blocks?.length &&", "{!!row.blocks?.length &&"),
    ('A refusal stated twice', LL, "if (row.status === 'REFUSED_UNREACHED') return `${request}: ${row.reason",
     "if (row.status === 'REFUSED_UNREACHED') return `${request}: refused, no pair ran. ${row.reason"),
    ('Setup form speaks about the rule not offered', LLC,
     '{challengeSelection && <Field name="Challenge picks">{challengeSelectionText(challengeSelection)}</Field>}',
     '{<Field name="Challenge picks">{challengeSelectionText(challengeSelection)}</Field>}'),
    ('Undeclared challenge rule claims the plan was saved before it', LL,
     "if (!rule) return 'Not declared: every valid challenge pick runs its pairs, as before.'",
     "if (!rule) return 'Not declared: this plan was saved before the challenge-pick rule; every valid challenge pick runs its pairs, as before.'"),
]


def sha(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def build():
    shutil.rmtree(FRONT, ignore_errors=True); os.makedirs(FRONT)
    for name in ('src', 'tests'):
        shutil.copytree(f'{REAL}/{name}', f'{FRONT}/{name}', ignore=shutil.ignore_patterns('.results', 'node_modules'))
    for name in ('index.html', 'local-ports.ts', 'package.json', 'package-lock.json', 'tsconfig.json', 'vite.config.ts'):
        shutil.copy2(f'{REAL}/{name}', f'{FRONT}/{name}')
    os.symlink(f'{REAL}/node_modules', f'{FRONT}/node_modules')
    vc = open(f'{FRONT}/vite.config.ts').read()
    assert vc.count('plugins: [react()],') == 1
    open(f'{FRONT}/vite.config.ts', 'w').write(vc.replace('plugins: [react()],', f"plugins: [react()], cacheDir: '{CACHE}',"))


def run():
    return subprocess.run(['npx', 'vitest', 'run', 'tests/loop-limits.test.tsx'], cwd=FRONT, capture_output=True, text=True)


def last(r):
    lines = [l.strip() for l in (r.stdout + r.stderr).splitlines() if 'Tests' in l or 'Test Files' in l]
    return ' | '.join(lines[-2:])


build()
tc = subprocess.run(['npx', 'tsc', '-p', 'tsconfig.json', '--noEmit', '--incremental', 'false'], cwd=FRONT, capture_output=True, text=True)
print(f'TYPECHECK (full, no build-info cache) exit {tc.returncode} :: {(tc.stdout + tc.stderr).strip()[-400:] or "no errors"}', flush=True)
base = run()
print(f'UNMUTATED {"PASS" if base.returncode == 0 else "FAIL"} :: {last(base)}', flush=True)
if base.returncode != 0:
    print(base.stdout[-2000:], base.stderr[-2000:]); sys.exit(2)
caught = 0
for name, rel, old, new in MUTATIONS:
    path = f'{FRONT}/{rel}'; before = sha(path); text = open(path).read()
    if text.count(old) != 1:
        print(f'SETUP ERROR {name}: {text.count(old)} matches'); sys.exit(2)
    open(path, 'w').write(text.replace(old, new))
    try:
        r = run()
    finally:
        open(path, 'w').write(text); assert sha(path) == before
    caught += r.returncode != 0
    print(f'{"CAUGHT" if r.returncode else "MISSED"}  {name} :: {last(r)}', flush=True)
print(f'TOTAL caught {caught} of {len(MUTATIONS)}; files restored (sha256 checked)')
shutil.rmtree(FRONT); shutil.rmtree(CACHE, ignore_errors=True)
print('scratch frontend removed:', not os.path.exists(FRONT))

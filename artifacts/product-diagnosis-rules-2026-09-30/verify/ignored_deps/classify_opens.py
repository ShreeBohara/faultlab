"""Classify the paths opened during the scratch-tree run of the new tests (verify/ignored_deps). For every path inside
the scratch tree: is it a tracked blob of the backup tip 626bae4, one of the 21 changed/added product files, one of this
round's probe-input copies (artifacts/product-diagnosis-rules-2026-09-30/probe-inputs/, git-ignored, listed for a forced add),
or neither (then: would the repo ignore it?). Names only; nothing is read. Copied from the fireability verifier's
classify_opens.py with the tip, scratch folder and file counts changed and the probe-input class added."""
import os, subprocess, sys, collections
R = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab'
S = '/Users/shree/FaultLab_Scratch/verify-diagnosis-rules'
TREE = os.path.realpath(S + '/tree')
opens = [l.strip() for l in open(sys.argv[1]) if l.strip()]
tracked = set(subprocess.run(['git', '-C', R, 'ls-tree', '-r', '--name-only', '626bae4'], capture_output=True, text=True,
                             env=dict(os.environ, GIT_OPTIONAL_LOCKS='0')).stdout.split('\n'))
added = {l.split()[2] for l in open(sys.argv[2]) if l.startswith(('CHANGED', 'ADDED'))}
cls = collections.Counter(); scratch_other = []; outside = []
for p in opens:
    if p.startswith(TREE + '/'):
        rel = p[len(TREE) + 1:]
        if rel in added: cls['scratch tree: one of the 21 changed/added product files'] += 1
        elif rel.startswith('artifacts/product-diagnosis-rules-2026-09-30/probe-inputs/') and os.path.isfile(p):
            cls['scratch tree: probe-input copy (git-ignored; in the commit list, needs git add -f)'] += 1
        elif rel in tracked: cls['scratch tree: tracked file of the backup tip'] += 1
        elif os.path.isdir(p): cls['scratch tree: directory'] += 1
        elif not os.path.lexists(p):
            cls['name that does not exist in the scratch tree (relative name opened through a dir_fd, e.g. shutil.rmtree of '
                'pytest temp folders, resolved against the cwd by the hook)'] += 1
        elif '/__pycache__/' in rel: cls['scratch tree: bytecode cache lookup (__pycache__, not a dependency)'] += 1
        else: scratch_other.append(rel)
        if rel.startswith('artifacts/'): print('artifacts path opened:', rel, 'tracked in 626bae4' if rel in tracked else ('probe-input copy (commit list)' if 'probe-inputs/' in rel else 'NOT TRACKED'))
    elif p.startswith(os.path.realpath(R + '/.venv')): cls['.venv (environment)'] += 1
    elif p.startswith('/Users/shree/FaultLab_Runs/'): cls['saved store under FaultLab_Runs (opened by the tests read-only)'] += 1; outside.append(p)
    elif p.startswith(('/private/var/folders', '/var/folders', '/tmp', '/private/tmp')): cls['temp (pytest tmp_path etc.)'] += 1
    elif p.startswith(('/Users/shree/.pyenv', '/opt/homebrew', '/usr/', '/Library/', '/System/')): cls['python install / system'] += 1
    elif p.startswith('/dev/'): cls['device'] += 1
    elif p.startswith(S): cls['verifier scratch (outside the tree)'] += 1
    elif p.startswith(R): outside.append(p); cls['REAL REPO (Desktop) path'] += 1
    else: outside.append(p); cls['OTHER'] += 1
for k, v in sorted(cls.items()): print(f'{k}: {v}')
ign = []
for p in opens:
    if p.startswith(TREE + '/') and os.path.isfile(p) and '/__pycache__/' not in p:
        rel = p[len(TREE) + 1:]
        if (rel in tracked or rel in added) and subprocess.run(['git', '-C', R, 'check-ignore', '-q', '--no-index', rel]).returncode == 0:
            ign.append(rel)
print('opened tree files that match a .gitignore pattern (tracked or added):', len(ign))
for rel in ign: print('  ', rel, '(tracked in 626bae4)' if rel in tracked else '(one of the 21 files)')
print('scratch-tree paths neither tracked nor added (would they be ignored?):')
for rel in scratch_other:
    ig = subprocess.run(['git', '-C', R, 'check-ignore', '-q', '--no-index', rel]).returncode == 0
    print('  ', rel, '(ignored pattern)' if ig else '(NOT ignored)')
print('paths outside the scratch tree, .venv, temp and python install:')
for p in sorted(set(outside)): print('  ', p)

"""Classify every repository path the new tests opened or listed: tracked at the checkpoint, new-and-not-ignored,
or git-ignored (then: installed environment .venv/node_modules, cache, or a real problem). git check-ignore only;
no file content is read here."""
import json, subprocess, sys, collections
ROOT = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab'
log = sys.argv[1]
paths = collections.OrderedDict()
for line in open(log):
    for p in json.loads(line)['paths']:
        kind, rel = (('list', p[2:]) if p.startswith('L ') else ('open', p))
        paths.setdefault(rel, set()).add(kind)
rels = sorted(paths)
def git(*a, inp=None):
    return subprocess.run(['git', '-C', ROOT, *a], input=inp, capture_output=True, text=True, env={'GIT_OPTIONAL_LOCKS': '0', 'PATH': '/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin'})
ign = set(git('check-ignore', '--stdin', '--no-index', inp='\n'.join(rels) + '\n').stdout.split('\n')) - {''}
tracked_tip = set(git('ls-tree', '-r', '--name-only', 'fca3502bbc9f3f3ef0343f7bef62a11debbd748d').stdout.split('\n'))
out = collections.defaultdict(list)
for r in rels:
    if r in ign or any(r.startswith(d) for d in ('.venv/', 'frontend/node_modules/')):
        if r.startswith('.venv/') or '/node_modules/' in '/' + r:
            out['ignored: installed environment (.venv / node_modules, created by setup)'].append(r)
        elif '__pycache__' in r or r.endswith('.pyc') or '.pytest_cache' in r or '/.vite/' in r:
            out['ignored: cache'].append(r)
        else:
            out['IGNORED OTHER (would be missing in a clean clone)'].append(r)
    elif r in tracked_tip:
        out['tracked at checkpoint'].append(r)
    elif r.rstrip('/') in {t.rsplit('/', 1)[0] for t in tracked_tip if '/' in t} or any(t.startswith(r.rstrip('/') + '/') for t in tracked_tip):
        out['directory holding tracked files'].append(r)
    else:
        out['not ignored, not at checkpoint (new file, or path absent)'].append(r)
import os
res = {k: (v if not k.startswith('ignored: installed') else {'count': len(v), 'first': v[:5]}) for k, v in out.items()}
for r in out.get('not ignored, not at checkpoint (new file, or path absent)', []):
    pass
res['_exists_check_for_new'] = {r: os.path.exists(os.path.join(ROOT, r)) for r in out.get('not ignored, not at checkpoint (new file, or path absent)', [])}
print(json.dumps(res, indent=1))

"""Summarize verifier guard logs: python (sitecustomize) jsonl, node (node-guard) jsonl and socket sampler output."""
import collections, json, sys
from pathlib import Path


def python_log(path):
    kinds = collections.Counter(); totals = collections.Counter(); protected = collections.Counter(); env = collections.Counter()
    for line in Path(path).read_text().splitlines():
        r = json.loads(line); kinds[r['kind']] += 1
        if r['kind'] == 'process_summary':
            try: d = json.loads(r['detail'])
            except json.JSONDecodeError:   # guard revision 1/2 truncated long summaries at 300 characters
                import re
                d = {k: int(m.group(1)) for k in ('loopback_connect', 'local_lookup', 'unix_connect', 'refused_outside', 'env_open')
                     if (m := re.search(r'"%s": (\d+)' % k, r['detail']))}
                d['protected'] = {}; totals['truncated_summaries'] += 1
            for k in ('loopback_connect', 'local_lookup', 'unix_connect', 'refused_outside', 'env_open'): totals[k] += d.get(k, 0)
            for p, n in d.get('protected', {}).items():
                key = ('temp/scratch copy' if ('/pytest-of-' in p or '/scratchpad/' in p or '/T/' in p) else 'real ' + p.split('/faultlab/')[-1])
                protected[key] += n
        if r['kind'] == 'env_open': env[r['detail'].split(' (')[-1].rstrip(')')] += 1
    refused = [r for r in map(json.loads, Path(path).read_text().splitlines()) if r['kind'].startswith('REFUSED')]
    return {'processes_with_guard': kinds['guard_loaded'], 'process_summaries': kinds['process_summary'], 'totals': dict(totals),
            'refused_outside_events': [r['detail'] for r in refused], 'env_open_by_outcome': dict(env), 'protected_opens': dict(protected)}


def node_log(path):
    rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    return {'node_processes_with_guard': sum(r['event'] == 'guard_loaded' for r in rows),
            'refused': [(r['event'], r['host']) for r in rows if r['event'].startswith('REFUSED')]}


def sampler(path):
    rows = [l for l in Path(path).read_text().splitlines() if l.strip()]
    done = Path(str(path) + '.done')
    return {'non_loopback_rows': len(rows), 'rows': rows[:5], 'sampler': done.read_text().strip() if done.exists() else 'NOT FINISHED'}


out = {}
for arg in sys.argv[1:]:
    kind, path = arg.split('=', 1)
    if Path(path).exists():
        out[f'{kind}:{Path(path).name}'] = {'python': python_log, 'node': node_log, 'sampler': sampler}[kind](path)
print(json.dumps(out, indent=1))

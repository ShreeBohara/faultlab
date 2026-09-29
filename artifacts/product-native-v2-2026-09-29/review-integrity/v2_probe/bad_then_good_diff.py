"""Show exactly where v2's request 3 differs from v1's (relabelled) in the bad_then_good episode."""
import sys, difflib
from pathlib import Path
exec(compile(Path(__file__).with_name('_common.py').read_text(), '_common.py', 'exec'))
from app.integrations.external_agent_v2 import SmolagentsActorV2
v1 = asyncio.run(episode('bad_then_good', EPISODES['bad_then_good'], SmolagentsActor))
v2 = asyncio.run(episode('bad_then_good', EPISODES['bad_then_good'], SmolagentsActorV2))
labels = {e: f'obs-{i}' for i, e in enumerate(v2['journal_ids'], 1)}
a = json.dumps(v1['requests'][2]['messages'], ensure_ascii=False, indent=1)
for e, l in labels.items(): a = a.replace(e, l)
b = json.dumps(v2['requests'][2]['messages'], ensure_ascii=False, indent=1)
print('\n'.join(difflib.unified_diff(a.splitlines(), b.splitlines(), 'v1 request 3 (IDs relabelled)', 'v2 request 3', n=0, lineterm='')))

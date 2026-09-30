"""Product review ($0, offline): the saved native-v2b store's campaigns read identically with the backup code and this build.

Run TWICE, once from each tree's backend/ directory (the backup tree is `git archive backup/part2-2026-09-22` in a scratch
directory outside the Desktop, its audit/ a symlink to the repo's; nothing in the repo is changed):
    <python> -B .../review_api_differential.py LABEL OUT.json
Each run makes its OWN scratch copy of /Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3 (SQLite backup API from
a mode=ro&immutable=1 connection) and fetches, through the in-process ASGI app of that tree, every read-only campaign view
the dashboard uses for each saved campaign (plan, history check, campaign, configuration, policy status, budget, matrix,
experiments, search attempts, evidence wait, counterexamples, regressions, completion and context studies, recording),
plus the campaign list, agent registrations, policies, each saved challenge and the baseline study. Held-out views are
not fetched. The two JSON dumps are compared by review_compare.py. No network (review_guard).
"""
import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review_guard  # noqa: E402

BACKEND = Path.cwd()
sys.path.insert(0, str(BACKEND))
SAVED = Path('/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3')


def main(label, out):
    import hashlib
    import shutil
    import sqlite3
    import httpx
    from app.config import Settings
    from app.lab.coordinator import LabCoordinator
    from app.main import create_app
    before = hashlib.sha256(SAVED.read_bytes()).hexdigest()
    scratch = Path(f'/Users/shree/FaultLab_Scratch/review-product-fireability/diff-{label}')
    shutil.rmtree(scratch, ignore_errors=True); scratch.mkdir(parents=True)
    src = sqlite3.connect(f'file:{SAVED}?mode=ro&immutable=1', uri=True); dst = sqlite3.connect(str(scratch / 'lab.sqlite3'))
    try:
        src.backup(dst); dst.execute('PRAGMA journal_mode=DELETE')
    finally:
        dst.close(); src.close()
    owner = LabCoordinator(Settings(faultlab_artifact_dir=str(scratch), wandb_model='deepseek-ai/DeepSeek-V3.1',
                                    wandb_explorer_model='deepseek-ai/DeepSeek-V4-Pro-0813'))
    dump = {'label': label, 'backend': str(BACKEND)}
    try:
        campaigns = sorted(p['campaign_id'] for p in owner.store.list_records('campaign_plans'))
        challenges = sorted(r['challenge_id'] for r in owner.store.list_records('challenges'))
        studies = sorted({r.get('study_id') for r in owner.store.list_records('baseline_studies') if r.get('study_id')}
                         | {r.get('campaign_id') for r in owner.store.list_records('baseline_studies') if r.get('campaign_id')})
        async def fetch():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=owner)), base_url='http://test') as api:
                async def get(path):
                    response = await api.get(path)
                    try: body = response.json()
                    except Exception: body = response.text[:200]
                    return {'status': response.status_code, 'body': body}
                result = {'/api/campaigns': await get('/api/campaigns'), '/api/agent-registrations': await get('/api/agent-registrations'),
                          '/api/policies': await get('/api/policies')}
                for ident in campaigns:
                    for view in ('plan', 'plan/history-check', '', 'configuration', 'policy-status', 'budget', 'matrix', 'experiments',
                                 'search-attempts', 'evidence-wait', 'counterexamples', 'regressions', 'completion-studies',
                                 'context-studies', 'recording'):
                        path = f'/api/campaigns/{ident}' + (f'/{view}' if view else '')
                        result[path] = await get(path)
                for ident in challenges:
                    result[f'/api/challenges/{ident}'] = await get(f'/api/challenges/{ident}')
                for ident in studies:
                    result[f'/api/baseline-studies/{ident}'] = await get(f'/api/baseline-studies/{ident}')
                return result
        dump['responses'] = asyncio.run(fetch())
        dump['campaigns'] = campaigns; dump['challenges'] = challenges; dump['studies'] = studies
    finally:
        asyncio.run(owner.close())
        shutil.rmtree(scratch, ignore_errors=True)
    dump['scratch_removed'] = not scratch.exists()
    dump['saved_store_unchanged'] = hashlib.sha256(SAVED.read_bytes()).hexdigest() == before
    dump['guard'] = review_guard.counts()
    Path(out).write_text(json.dumps(dump, indent=1, sort_keys=True, default=str))
    print(label, 'paths', len(dump['responses']), 'statuses', sorted({v['status'] for v in dump['responses'].values()}),
          'unchanged', dump['saved_store_unchanged'], 'removed', dump['scratch_removed'], dump['guard'])


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])

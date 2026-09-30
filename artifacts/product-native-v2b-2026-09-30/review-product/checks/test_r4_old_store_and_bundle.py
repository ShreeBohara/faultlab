"""Product review, check 4: the first live native v2 run's saved store still reads under the new runtime, and a regression
bundle exported from it imports and reruns on the updated native adapter v2 (v2.1). Offline and $0.

The store is a PRIVATE COPY (review-product/store-copy/lab.sqlite3, made with the SQLite backup API from an
ro+immutable connection; the original's size, mtime and sha256 were recorded before and after and did not change).
The copy is opened exactly as an operator browses an archive (Settings.faultlab_read_only -> ArchiveCoordinator ->
ReadOnlyLabStore). Every saved API snapshot of the live run folder is compared with what the new code returns now.
"""
import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.main import create_app

REVIEW = Path(__file__).resolve().parents[1]
FAULTLAB = Path(__file__).resolve().parents[4]
RUN = FAULTLAB / 'artifacts/product-live-2026-09-30/native-v2-run'
COPY_DIR = REVIEW / 'store-copy'
LEARN = 'campaign-b05ac2809c844a2f9d5211a006c372f4'
BASELINE = json.loads((RUN / 'baseline-campaign.json').read_text())['campaign_id']


@pytest.fixture
def anyio_backend(): return 'asyncio'


def archive_settings():
    return Settings(faultlab_artifact_dir=str(COPY_DIR), faultlab_read_only=True, wandb_api_key='', faultlab_control_token='')


def strip_volatile(value):
    return value


@pytest.mark.anyio
async def test_saved_store_reads_as_it_did_and_a_bundle_round_trips_to_v21(tmp_path):
    out = {'baseline_campaign': BASELINE, 'learn_campaign': LEARN}
    app = create_app(settings=archive_settings())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1') as client:
        async def get(path):
            response = await client.get(path)
            assert response.status_code == 200, (path, response.status_code, response.text[:400])
            return response.json()
        comparisons = {}
        for name, path in (('learn-final.json', f'/api/campaigns/{LEARN}'), ('learn-plan-final.json', f'/api/campaigns/{LEARN}/plan'),
                           ('learn-search-attempts-final.json', f'/api/campaigns/{LEARN}/search-attempts'),
                           ('learn-matrix-final.json', f'/api/campaigns/{LEARN}/matrix'),
                           ('learn-experiments-final.json', f'/api/campaigns/{LEARN}/experiments'),
                           ('learn-budget-final.json', f'/api/campaigns/{LEARN}/budget'),
                           ('learn-evidence-wait-final.json', f'/api/campaigns/{LEARN}/evidence-wait'),
                           ('learn-policy-status-final.json', f'/api/campaigns/{LEARN}/policy-status')):
            saved = json.loads((RUN / name).read_text())
            now = await get(path)
            if saved == now:
                comparisons[name] = 'IDENTICAL'
            else:
                keys = sorted(set(saved) | set(now)) if isinstance(saved, dict) and isinstance(now, dict) else None
                comparisons[name] = {'DIFFERS_IN': [k for k in keys if saved.get(k) != now.get(k)] if keys else 'list'}
        out['api_vs_saved_snapshots'] = comparisons
        plan = await get(f'/api/campaigns/{LEARN}/plan')
        assert plan['status'] == 'PLANNED' and plan['plan']['transport_retry']['protocol'] == 'faultlab-transport-retry/v1'
        baseline_plan = await get(f'/api/campaigns/{BASELINE}/plan')
        assert baseline_plan['status'] == 'PLANNED'
        recording = await get(f'/api/campaigns/{LEARN}/recording')
        out['learn_recording'] = {'episodes': len(recording.get('episodes', [])), 'transport_retries': recording.get('transport_retries'),
                                  'plan_transport_retry': recording['run_plan']['plan']['transport_retry']['protocol']}
        # A first-build v2 report record (journal-position labels, cited_unshown_labels) still reads.
        source = json.loads((RUN / 'export.json').read_text())['counterexamples'][2]['source_episode_id']
        events = await get(f'/api/episodes/{source}/events')
        submitted, = [e for e in events['events'] if e['type'] == 'report_submitted']
        out['first_build_report_record'] = {k: submitted['payload'].get(k) for k in ('citation_protocol', 'cited_evidence_tokens', 'labels_shown_to_agent', 'cited_unshown_labels')}
        assert submitted['payload']['citation_protocol'] == 'faultlab-native-adapter/v2-shown-labels-final-turn'
        regressions = await get(f'/api/campaigns/{LEARN}/regressions')
        out['regressions'] = [r['regression_id'] for r in regressions]
        download = await client.get(f"/api/regressions/{regressions[-1]['regression_id']}/download")
        assert download.status_code == 200, download.text[:300]
        (REVIEW / 'store-copy' / 'exported-bundle.zip').write_bytes(download.content)
        registrations = await get('/api/agent-registrations')
        out['registrations_in_old_store'] = [r['registration_id'] for r in registrations]

    # Import that bundle into a fresh store under the new runtime, register the updated v2, and rerun it (scripted).
    from app.lab import bundle_imports as imports
    from app.lab.dashboard import store_descriptor
    from app.lab.operator_actions import register_agent
    from test_planned_agent_execution import runtime
    target = await runtime(tmp_path / 'target')
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=target)), base_url='http://test') as client:
            uploaded = await client.post('/api/bundle-imports', content=download.content,
                headers={'content-type': 'application/zip', 'x-faultlab-store-identity': store_descriptor(target.store)['identity']})
        assert uploaded.status_code == 201, uploaded.text[:600]
        detail = uploaded.json()
        v2 = register_agent(target.store, target.settings, 'smolagents-v2')
        listed = {t['agent_registration_id']: t for t in imports.import_detail(target.store, target.settings, detail['import_id'])['targets']}
        out['import'] = {'import_id': detail['import_id'], 'v21_target': listed.get(v2.registration_id)}
        assert listed[v2.registration_id]['compatible'] is True
        body = imports.ImportedExecutionRequest(expected_store_identity=store_descriptor(target.store)['identity'],
            expected_manifest_hash=detail['manifest_hash'], expected_target_configuration_hash=v2.configuration_hash,
            agent_registration_id=v2.registration_id, request_id='request-review-v21', execution_profile_id='sandbox-v1', execute_live=True)
        started = await imports.execute_import(target, detail['import_id'], body)
        await target.tasks[started['execution']['execution_id']]
        result = imports.request_view(target.store, detail['import_id'], body.request_id)
        reruns = []
        for episode_id in result['execution']['episode_ids']:
            events = target.store.events(episode_id)['events']
            payload, = [e['payload'] for e in events if e['type'] == 'report_submitted']
            journal = [e['payload']['observation']['evidence_id'] for e in events if e['type'] == 'observation_delivered']
            reruns.append({'labels_shown': payload['labels_shown_to_agent'], 'cited': payload['cited_evidence_tokens'],
                           'not_decoded': payload['cited_tokens_not_decoded'], 'journal_rows': len(journal),
                           'hidden_rows': [journal.index(i) + 1 for i in journal if i not in payload['evidence_labels']],
                           'protocol': payload['citation_protocol']})
        out['import_rerun'] = {'status': result['execution']['status'], 'assertions': result.get('assertions'), 'episodes': reruns}
        assert result['execution']['status'] == 'COMPLETED'
        for row in reruns:
            assert row['labels_shown'] == [f'obs-{n}' for n in range(1, len(row['labels_shown']) + 1)] and row['not_decoded'] == []
    finally:
        (REVIEW / 'r4-old-store-and-bundle.json').write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + '\n')
        await target.close()

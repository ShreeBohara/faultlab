"""Plan item 1.11, first slice: Weave is optional and a study may declare local evidence as its authority."""
import asyncio
from dataclasses import replace

import pytest

from app.lab.coordinator import LabCoordinator
from app.lab.evidence import EvidenceGateway
from test_baseline_study import settings
from test_completion_study import finish, harness


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
async def test_a_completion_study_accepts_local_evidence_when_it_is_declared(tmp_path):
    c, campaign, provider, _, client = await harness(tmp_path)
    try:
        c.settings = replace(c.settings, faultlab_require_remote_evidence=False)
        c.evidence_gateway = EvidenceGateway(c.store, 'entity/project')        # no reader: nothing can be read back from Weave
        result = await finish(c, campaign)
        assert result['status'] == 'COMPLETED' and result['decision'] == 'OBSERVED_IMPROVEMENT', result['reason']
        assert result['evidence_requirement'] == 'local'
        assert set(result['evidence'].values()) == {'local_only'} and len(result['evidence']) == 54
        assert c.store.get_record('completion_plans', result['study_id'])['evidence_requirement'] == 'local'
        assert all(c.store.get_record('evidence', episode_id)['source'] == 'local_only' for episode_id in result['evidence'])
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_the_default_still_demands_weave_verified_evidence(tmp_path):
    c, campaign, provider, _, client = await harness(tmp_path)
    try:
        c.evidence_gateway = EvidenceGateway(c.store, 'entity/project')
        result = await finish(c, campaign)
        assert result['status'] == 'INCOMPLETE' and result['decision'] == 'INCOMPLETE'
        assert result['error_type'] == 'WaitingEvidence' and 'evidence_requirement' not in result
        assert result['evidence'] == {} and provider.calls > 0                    # one trial ran before the read was refused
    finally:
        await client.aclose()


def test_a_live_campaign_without_weave_starts_no_worker_and_keeps_local_evidence(tmp_path, monkeypatch):
    import app.telemetry.worker as worker_module

    class Forbidden:
        def __init__(self, *args, **kwargs):
            raise AssertionError('the Weave worker must not be built when Weave is disabled')
    monkeypatch.setattr(worker_module, 'WeaveWorker', Forbidden)
    c = LabCoordinator(replace(settings(tmp_path), faultlab_weave_enabled=False))
    runner, owned = asyncio.run(c._get_runner(True))
    assert owned and runner.trace is None and getattr(runner, 'telemetry_worker', None) is None
    assert c.evidence_gateway is not None and c.evidence_gateway.reader is None and c.evidence_gateway.trace is None
    assert getattr(c, 'evaluation_publisher', None) is None and getattr(c, 'dataset_publisher', None) is None and c.aria_bridge is None
    # With Weave enabled the worker is built (and here forbidden), which is the pre-existing path.
    with pytest.raises(AssertionError, match='must not be built'):
        asyncio.run(LabCoordinator(settings(tmp_path / 'with-weave'))._get_runner(True))   # its own store: the first coordinator holds a lease

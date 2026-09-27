"""Stop addresses owned active work, never an unrelated saved campaign."""
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.contracts.models import CampaignRequest
from app.lab.coordinator import LabCoordinator


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def create(coordinator):
    return coordinator.create(CampaignRequest(task_text='Upgrade and confirm', order_id='order-1', mode='baseline'))


@pytest.mark.anyio
async def test_stop_historical_campaign_cannot_rewrite_it_or_stop_other_work(tmp_path):
    coordinator = LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path)))
    active = create(coordinator)
    historical = create(coordinator)
    coordinator.transition(active.campaign_id, 'RUNNING')
    coordinator.transition(historical.campaign_id, 'COMPLETED', 'Original completion reason')
    coordinator.active_id = active.campaign_id
    coordinator.ledgers[active.campaign_id] = SimpleNamespace(stopped=False)
    before_active = coordinator.store.get_record('campaigns', active.campaign_id)
    before_historical = coordinator.store.get_record('campaigns', historical.campaign_id)

    saved = await coordinator.stop(historical.campaign_id)
    assert saved.state == 'COMPLETED' and not saved.stop_requested
    assert coordinator.store.get_record('campaigns', historical.campaign_id) == before_historical
    assert coordinator.store.get_record('campaigns', active.campaign_id) == before_active
    assert not coordinator.ledgers[active.campaign_id].stopped

    stopped = await coordinator.stop(active.campaign_id)
    assert stopped.state == 'STOPPED' and stopped.stop_requested
    assert coordinator.ledgers[active.campaign_id].stopped
    after = coordinator.store.get_record('campaigns', active.campaign_id)
    await coordinator.stop(active.campaign_id)
    assert coordinator.store.get_record('campaigns', active.campaign_id) == after
    assert coordinator.store.get_record('campaigns', historical.campaign_id) == before_historical
    await coordinator.close()


@pytest.mark.anyio
@pytest.mark.parametrize('state', ['IDLE', 'COMPLETED', 'NO_CHANGE', 'ERROR', 'STOPPED'])
async def test_auxiliary_activity_on_saved_campaign_remains_stoppable(tmp_path, state):
    coordinator = LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path)), runner=object())
    campaign = create(coordinator)
    coordinator.transition(campaign.campaign_id, state)
    before = coordinator.store.get_record('campaigns', campaign.campaign_id)
    await coordinator.stop(campaign.campaign_id)
    assert coordinator.store.get_record('campaigns', campaign.campaign_id) == before

    await coordinator.admit_activity(campaign.campaign_id)
    assert coordinator.get(campaign.campaign_id).state == state
    stopped = await coordinator.stop(campaign.campaign_id)
    assert stopped.state == 'STOPPED' and stopped.stop_requested
    await coordinator.close()

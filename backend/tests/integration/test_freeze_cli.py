"""Freezing records facts and cannot create a learned arm or execute providers."""
import asyncio
import pytest
from app.config import Settings
from app.contracts.models import CampaignRequest
from app.lab.coordinator import LabCoordinator
from app.cli.freeze import freeze_campaign


def test_baseline_freeze_retains_unavailable_learned_arm(tmp_path):
    settings=Settings(faultlab_artifact_dir=str(tmp_path))
    c=LabCoordinator(settings)
    campaign=c.create(CampaignRequest(mode='baseline',task_text='Test',order_id='order-one',config_profile_id='offline-v1'))
    with pytest.raises(ValueError):freeze_campaign(c.store,settings,campaign.campaign_id)
    c.transition(campaign.campaign_id,'COMPLETED')
    frozen=freeze_campaign(c.store,settings,campaign.campaign_id)
    assert frozen['execution_performed'] is False
    assert frozen['learned_arm_available'] is False
    assert c.store.get_record('audit_freezes',campaign.campaign_id)['policy_hash'] is None
    assert freeze_campaign(c.store,settings,campaign.campaign_id)==frozen
    assert c.store.list_records('episodes')==[]
    asyncio.run(c.close())

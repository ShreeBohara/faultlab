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


def planned_native(coordinator, *, agent='smolagents', mode='baseline'):
    from app.lab.operator_actions import register_agent
    from app.lab.run_plans import RunPlanRequest,build_run_options,prepare_run_plan
    registration=register_agent(coordinator.store,coordinator.settings,agent)
    options=build_run_options(coordinator.settings,coordinator.store)
    request=RunPlanRequest(expected_store_identity=options['data_store']['identity'],
        expected_setup_hash=options['setup_hash'],task_definition_id=options['task']['task_definition_id'],
        agent_registration_id=registration.registration_id,mode=mode,config_profile_id='live-v1',
        task_text=options['task']['task_text_default'],order_id='order-native-freeze',
        development_case_id='dev-1' if mode=='baseline' else None)
    prepared=prepare_run_plan(coordinator.store,coordinator.settings,request)
    return coordinator.create(prepared.campaign_request,run_plan=prepared)


@pytest.mark.parametrize('agent',['reference','smolagents'])
def test_planned_registration_freeze_uses_its_own_configuration_without_provider_work(tmp_path,agent):
    import json
    settings=Settings(faultlab_artifact_dir=str(tmp_path),wandb_model='deepseek-ai/DeepSeek-V3.1')
    c=LabCoordinator(settings)
    try:
        campaign=planned_native(c,agent=agent)
        c.transition(campaign.campaign_id,'COMPLETED')
        frozen=freeze_campaign(c.store,settings,campaign.campaign_id)
        assert frozen['execution_performed'] is False and frozen['learned_arm_available'] is False
        actual=json.loads(__import__('pathlib').Path(frozen['path']).read_text())
        configuration=c.store.get_record('configurations',campaign.configuration_hash)
        assert actual['identity']['prompt_hash']==configuration['actor_prompt_hash']
        assert actual['identity']['adapter_hash']==configuration['adapter_hash']
        assert freeze_campaign(c.store,settings,campaign.campaign_id)==frozen
        assert not c.store.list_records('episodes') and not c.store.list_records('budgets')
    finally: asyncio.run(c.close())


@pytest.mark.parametrize('change',['settings','missing_plan','corrupt_configuration'])
def test_native_plan_freeze_rejects_changed_identity_before_writing_files(tmp_path,change):
    from dataclasses import replace
    settings=Settings(faultlab_artifact_dir=str(tmp_path),wandb_model='deepseek-ai/DeepSeek-V3.1')
    c=LabCoordinator(settings)
    try:
        campaign=planned_native(c)
        c.transition(campaign.campaign_id,'COMPLETED')
        if change=='settings': settings=replace(settings,wandb_model='deepseek-ai/DeepSeek-V4-Pro-0813')
        elif change=='missing_plan':
            c.store.db.execute("DELETE FROM records WHERE kind='campaign_plans' AND id=?",(campaign.campaign_id,))
        else:
            c.store.db.execute("DELETE FROM records WHERE kind='configurations' AND id=?",(campaign.configuration_hash,))
        with pytest.raises(ValueError): freeze_campaign(c.store,settings,campaign.campaign_id)
        assert not (tmp_path/'campaigns').exists()
        assert not c.store.list_records('audit_freezes')
        assert not c.store.list_records('episodes') and not c.store.list_records('budgets')
    finally: asyncio.run(c.close())

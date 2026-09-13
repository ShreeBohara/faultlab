"""Real HTTP reference coverage; these are internal checks, never measured B0/L."""
import asyncio
import pytest
from app.config import Settings
from app.contracts.models import CampaignRequest, FaultSpec, canonical_json
from app.adapters.business_tools import WorldClient
from app.lab.coordinator import LabCoordinator
from app.lab.runner import EpisodeRunner
from app.referee.manifests import load_manifest

pytestmark=pytest.mark.localhost_http


def test_reference_six_frozen_cases_three_fresh_trials(tmp_path,simulator_server):
    url,app=simulator_server
    coordinator=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path/'lab')))
    campaign=coordinator.create(CampaignRequest(task_text='Upgrade the authorized order and confirm truthfully.',order_id='order-reference',mode='baseline',config_profile_id='offline-v1'))
    async def execute():
        world=WorldClient(url,'integration-control'); runner=EpisodeRunner(coordinator.store,world)
        trials=[]
        try:
            for case in load_manifest('development')['cases']:
                for index in range(3):
                    trial=await runner.run(campaign,FaultSpec.model_validate_json(canonical_json(case['fault_spec'])),coordinator.policies.baseline(),arm='B1',trial_index=index,fixture_id=case['fixture_id'],source_mode='offline_fixture')
                    trials.append(trial)
                    assert trial.lifecycle=='COMPLETED',trial
                    assert trial.outcome in ('COMPLETED','CORRECTLY_REJECTED','SAFE_UNRESOLVED'),trial
                    assert not trial.failed_checks,trial
                    assert trial.usage.model_calls==0
                    assert trial.usage.http_attempts<=18
            assert len({t.world_id for t in trials})==18
            assert len({t.episode_id for t in trials})==18
            assert len(list(app.state.store.directory.glob('*.sqlite3')))==18
        finally:
            await world.close(); await coordinator.close()
    asyncio.run(execute())

"""Real discovery/selector orchestration with offline provider and world doubles."""
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.contracts.models import CampaignRequest,canonical_json
from app.lab.budgets import CampaignLedger
from app.lab.coordinator import LabCoordinator
from app.lab.learning import run_learning_cycle
from app.providers.runtime import RuntimeGeneration
from test_evaluation import FakeRunner


@pytest.fixture
def anyio_backend(): return 'asyncio'


@pytest.mark.anyio
async def test_duplicate_discovery_consumes_a_slot_without_a_trial_or_a_silent_replacement(tmp_path):
    coordinator=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path),wandb_model='openai/gpt-oss-120b'))
    campaign=coordinator.create(CampaignRequest(task_text='Upgrade',order_id='order-1',mode='learn',config_profile_id='live-v1'))
    campaign.caps.discovery_selections=3; coordinator.save(campaign)
    ledger=CampaignLedger(coordinator.store,campaign.campaign_id,campaign.caps)
    coordinator.ledgers[campaign.campaign_id]=ledger
    class Evidence:
        async def get(self,episode_id,context,**kwargs):
            return SimpleNamespace(episode_id=episode_id,source='weave_verified',report=None,findings=[],observations=[])
    coordinator.evidence_gateway=Evidence()
    class Provider:
        calls=0
        async def complete(self,messages,**kwargs):
            self.calls+=1
            # Slot 1 changes only seed; slot 2 changes actual fault behavior.
            return RuntimeGeneration(canonical_json({'fault_spec':{'seed':self.calls,'primitives':[
                {'kind':'F4','target_tool':'get_operation_status','target_service':'orders','occurrence':1,
                 'parameters':{'failure_count':2 if self.calls==3 else 1}}]},'hypothesis':'Offline fixture'}),'openai/gpt-oss-120b')
    runner=FakeRunner('tie'); runner.provider=Provider(); original=runner.run
    async def persisted(current,recipe,policy,**kwargs):
        trial=await original(current,recipe,policy,**kwargs)
        trial.fault_triggered=False
        coordinator.store.put_record('episodes',trial.episode_id,{'campaign_id':current.campaign_id,
            'configuration_hash':current.configuration_hash,'policy_hash':policy.policy_hash,'scenario_hash':trial.scenario_hash,
            'split':'development','experiment_purpose':'discovery','study_id':current.campaign_id,
            'evidence_context_id':current.campaign_id,'selector_id':None,
            'verdict':{'fault_executions':[{'triggered':False,'reason':'target_not_reached'}]}})
        return trial
    runner.run=persisted
    await run_learning_cycle(coordinator,campaign,runner)
    saved=coordinator.store.list_records('selections')
    assert len(saved)==3 and runner.provider.calls==ledger.used_calls==3
    assert len(runner.calls)==2 and len(coordinator.store.list_records('episodes'))==2
    assert [row['search_decision']['status'] for row in saved]==['SELECTED','SKIPPED_DUPLICATE','SELECTED']
    assert len(saved[2]['context']['development_history'])==1
    assert len(saved[2]['context']['search_ledger']['prior_selections'])==2
    assert coordinator.get(campaign.campaign_id).state=='NO_CHANGE'
    assert not coordinator.store.list_records('counterexamples') and len(coordinator.policies.list())==1
    assert ledger.reserved_calls==1064

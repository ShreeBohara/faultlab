"""Independent transfer admission rejects rerunning the same reviewed agent."""
import pytest
from types import SimpleNamespace

from app.lab.operator_actions import FreezePortabilityRequest, freeze_and_queue_portability
from app.lab.portability import queue_portability
from app.lab.dashboard import store_descriptor
from app.lab.run_plans import read_run_plan
from test_planned_agent_execution import planned_campaign,runtime


@pytest.fixture
def anyio_backend():return 'asyncio'


@pytest.mark.anyio
@pytest.mark.parametrize('entry',['operator','queue'])
async def test_same_native_transfer_rejected_before_freeze_reservation_or_world(tmp_path,entry):
    c=await runtime(tmp_path)
    try:
        campaign=planned_campaign(c,mode='learn')
        # This fixture seeds a manual terminal policy solely to test admission;
        # no generated repair or external behavior claim is made.
        policy=c.policies.baseline().model_copy(update={'version':'manual-portability-admission-fixture',
            'decision':'ACCEPTED','author':'manual','parent_version':'policy-v0'})
        c.policies.save(policy)
        campaign.active_policy_version=policy.version;campaign.state='COMPLETED';c.save(campaign)
        c.store.compare_and_set_pointer('active-policy:'+campaign.campaign_id,'policy-v0',policy.version)
        registration_id=read_run_plan(c.store,campaign)['plan']['agent_registration_id']
        c.store.put_record('audit_freezes',campaign.campaign_id,{'learned_arm_available':True,
            'path':str(c.settings.artifact_path/'campaigns'/campaign.campaign_id/'audit'/'freeze.json')})
        if entry=='queue':
            c.store.put_record('external_freezes',campaign.campaign_id,{'freeze_hash':'a'*64})
        before=[tuple(row) for row in c.store.db.execute('SELECT * FROM records ORDER BY rowid')]
        with pytest.raises(ValueError,match='different reviewed agent implementation'):
            if entry=='operator':
                request=FreezePortabilityRequest(expected_store_identity=store_descriptor(c.store)['identity'],
                    agent_registration_id=registration_id,execute_live=True)
                await freeze_and_queue_portability(c,campaign.campaign_id,request)
            else:
                await queue_portability(c,campaign.campaign_id,SimpleNamespace(agent_registration_id=registration_id,policy_version=None))
        assert [tuple(row) for row in c.store.db.execute('SELECT * FROM records ORDER BY rowid')]==before
        assert c.active_id is None and not c.store.list_records('budgets')
        assert not c.store.list_records('episodes') and not c.runner.provider.calls
        assert not (c.settings.artifact_path/'campaigns').exists()
    finally:await c.close()

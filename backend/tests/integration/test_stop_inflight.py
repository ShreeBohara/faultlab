"""Stop retains a real committed effect and prevents the timeout retry."""
import time
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.contracts.models import FaultSpec
from app.main import create_app
from app.lab.coordinator import LabCoordinator
from app.lab.runner import EpisodeRunner
from app.adapters.business_tools import WorldClient

pytestmark=pytest.mark.localhost_http


class ScheduledTimeoutRunner(EpisodeRunner):
    async def run(self,campaign,recipe,policy,**kwargs):
        recipe=FaultSpec.model_validate_json('{"seed":1,"primitives":[{"kind":"F1","target_tool":"update_order","target_service":"orders","occurrence":1,"parameters":{"response_delay_ms":1500}}]}')
        return await super().run(campaign,recipe,policy,**kwargs)


def test_stop_during_http_timeout_preserves_commit(tmp_path,simulator_server):
    url,world_app=simulator_server
    c=LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path/'lab')))
    c.runner=ScheduledTimeoutRunner(c.store,WorldClient(url,'integration-control'))
    with TestClient(create_app(coordinator=c)) as client:
        campaign=client.post('/api/campaigns',json={'task_text':'Upgrade then confirm','order_id':'order-stop','mode':'baseline','config_profile_id':'offline-v1'}).json()
        ident=campaign['campaign_id']
        assert client.post(f'/api/campaigns/{ident}/start',json={}).status_code==202
        deadline=time.monotonic()+3; committed=False; world_id=None
        while time.monotonic()<deadline:
            for ep in c.store.list_records('episodes'):
                world_id=ep['world_id']; snapshot=world_app.state.store.snapshot(world_id)
                if snapshot.orders[0].version==2:committed=True;break
            if committed:break
            time.sleep(.005)
        assert committed
        began=time.perf_counter()
        stopped=client.post(f'/api/campaigns/{ident}/stop',json={})
        assert stopped.status_code==202 and time.perf_counter()-began<.25
        deadline=time.monotonic()+4
        while c.active_id and time.monotonic()<deadline:time.sleep(.01)
        assert c.active_id is None
        episode=c.store.list_records('episodes')[0]
        assert episode['lifecycle']=='INTERRUPTED',episode
        assert episode['report'] is None
        assert episode['usage']['http_attempts']==2 # One read and one original write; retry denied.
        final=world_app.state.store.snapshot(world_id)
        assert final.orders[0].version==2 and len(final.notifications)==0
        assert len([o for o in final.operations if o.service=='orders' and o.state=='SUCCEEDED'])==1
        assert c.store.get_record('campaigns',ident)['execution_epoch']==1

"""The legacy simulator's fixtures, pointed at the kernel-hosted orders world."""
import pytest
from fastapi.testclient import TestClient

from faultlab.core import content_hash
from faultlab.env.kernel import create_app
from faultlab.packs.orders import OrdersHandler, business_router
from faultlab.packs.orders.models import TaskIntent


def kernel_app(database_dir):
    return create_app(handler=OrdersHandler(), database_dir=database_dir, control_token='test-control', business_router=business_router)


@pytest.fixture
def intent():
    return TaskIntent(task_id='task-1', order_id='order-1', expected_version=1, upgrade_operation_id='upgrade-1',
                      notification_operation_id='notify-1', upgrade_idempotency_key='upgrade-key', notification_idempotency_key='notify-key',
                      upgrade_intent_hash=content_hash({'order': 'order-1', 'shipping': 'express'}),
                      notification_intent_hash=content_hash({'order': 'order-1', 'upgrade': 'upgrade-1'}), task_text='Upgrade shipping and confirm')


@pytest.fixture
def make_world(tmp_path, intent):
    client = TestClient(kernel_app(tmp_path))
    def create(primitives=(), fixture_id='standard-v1'):
        response = client.post('/control/worlds', headers={'X-FaultLab-Control': 'test-control'},
                               json={'episode_id': 'episode-1', 'intent': intent.model_dump(mode='json'),
                                     'fault_spec': {'seed': 1, 'primitives': list(primitives)}, 'fixture_id': fixture_id})
        assert response.status_code == 201, response.text
        handle = response.json()
        headers = {'X-FaultLab-World': handle['world_id'], 'X-FaultLab-Capability': handle['capability'],
                   'X-FaultLab-Call': 'call-1', 'X-FaultLab-Attempt': 'attempt-1'}
        return client, handle, headers
    return create


@pytest.fixture
def upgrade(intent):
    return dict(order_id=intent.order_id, desired_shipping='express', expected_version=intent.expected_version,
                operation_id=intent.upgrade_operation_id, idempotency_key=intent.upgrade_idempotency_key, intent_hash=intent.upgrade_intent_hash)


@pytest.fixture
def notification(intent):
    return dict(order_id=intent.order_id, upgrade_operation_id=intent.upgrade_operation_id, operation_id=intent.notification_operation_id,
                idempotency_key=intent.notification_idempotency_key, intent_hash=intent.notification_intent_hash, template_version='confirmation/v1')

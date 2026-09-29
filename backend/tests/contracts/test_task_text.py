"""One task rule for the backend and the dashboard: same length unit, same blank test.

The cases live in frontend/tests/fixtures/task-text-cases.json and are asserted by
frontend/tests/task-text.test.tsx as well, so the two sides cannot drift apart.
"""
import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.config import Settings
from app.contracts.models import CampaignRequest
from app.contracts.task_text import task_text_problem
from app.lab.bundle_imports import _check_recorded_fields, recorded_execution_task
from app.lab.run_plans import RunPlanRequest
from app.main import create_app

CASES_FILE = Path(__file__).resolve().parents[3] / 'frontend/tests/fixtures/task-text-cases.json'
CASES = [(case['name'], case['text'] * case['repeat'], case['sendable'])
         for case in json.loads(CASES_FILE.read_text())['cases']]
IDS = [name for name, _, _ in CASES]


def _accepts(model, **values):
    try:
        model(**values)
    except ValidationError:
        return False
    return True


@pytest.mark.parametrize('name,text,sendable', CASES, ids=IDS)
def test_every_entry_point_applies_the_shared_rule(name, text, sendable):
    assert (task_text_problem(text) is None) is sendable
    assert _accepts(CampaignRequest, task_text=text, order_id='order-7', mode='baseline') is sendable
    assert _accepts(RunPlanRequest, expected_store_identity='a' * 64, expected_setup_hash='b' * 64,
                    task_definition_id='orders.upgrade_then_confirm/v1', mode='baseline',
                    config_profile_id='offline-v1', task_text=text, order_id='order-7',
                    development_case_id='dev-1') is sendable
    recording = {'execution_task': {'task_text': text, 'order_id': 'order-7'}}
    if sendable:
        # Accepted exactly as recorded: never trimmed or rewritten.
        assert recorded_execution_task(recording) == {'task_text': text, 'order_id': 'order-7', 'origin': 'bundled'}
        _check_recorded_fields({'evidence.json': json.dumps(recording)})
    else:
        with pytest.raises(ValueError, match='malformed'):
            recorded_execution_task(recording)
        with pytest.raises(ValueError, match='malformed'):
            _check_recorded_fields({'evidence.json': json.dumps(recording)})


def test_length_is_counted_in_code_points_not_utf16_units():
    emoji = '\U0001F600' * 2000
    assert len(emoji) == 2000 and len(emoji.encode('utf-16-le')) // 2 == 4000
    assert task_text_problem(emoji) is None
    assert 'at most 2000' in task_text_problem(emoji + '\U0001F600')


@pytest.mark.parametrize('text', ['   ', '​​', '﻿', '\n\n\n'])
def test_a_blank_campaign_task_is_refused_before_any_writer_exists(tmp_path, text):
    directory = tmp_path / 'not-created'
    settings = Settings(faultlab_artifact_dir=str(directory))
    with patch('app.lab.coordinator.LabCoordinator', side_effect=AssertionError('Invalid request constructed owner')):
        with TestClient(create_app(settings=settings)) as client:
            options = client.get('/api/run-options').json()
            body = {'expected_store_identity': options['data_store']['identity'],
                    'expected_setup_hash': options['setup_hash'],
                    'task_definition_id': 'orders.upgrade_then_confirm/v1', 'mode': 'baseline',
                    'config_profile_id': 'offline-v1', 'task_text': text, 'order_id': 'order-planned-api',
                    'development_case_id': 'dev-1'}
            response = client.post('/api/planned-campaigns', json=body)
            assert response.status_code == 422, response.text
            assert response.json()['error']['code'] == 'INVALID_REQUEST'
            direct = client.post('/api/campaigns', json={'task_text': text, 'order_id': 'order-one', 'mode': 'baseline'})
            assert direct.status_code == 422, direct.text
    assert not directory.exists()


def test_control_a_visible_task_passes_validation_and_reaches_the_owner(tmp_path):
    settings = Settings(faultlab_artifact_dir=str(tmp_path / 'not-created'))
    with patch('app.lab.coordinator.LabCoordinator', side_effect=AssertionError('reached the owner')) as owner:
        with TestClient(create_app(settings=settings), raise_server_exceptions=False) as client:
            response = client.post('/api/campaigns', json={'task_text': '\u200bUpgrade', 'order_id': 'order-one', 'mode': 'baseline'})
    # Validation passed; the (patched) owner was then asked for, and its failure is reported as such.
    assert owner.called and response.status_code == 503, response.text

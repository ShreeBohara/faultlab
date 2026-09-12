"""Health must remain usable without credentials or provider access."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app


def test_health_does_not_load_configuration_or_contact_providers():
    with (
        patch.object(Settings, "from_env", side_effect=AssertionError("Unexpected settings load")),
        TestClient(app) as client,
    ):
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "faultlab-backend"}

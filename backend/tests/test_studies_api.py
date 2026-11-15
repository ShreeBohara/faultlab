"""The dashboard's study endpoints: read-only, offline, and confined to published record files."""

from pathlib import Path
import shutil
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ARTIFACTS = Path(__file__).resolve().parents[2] / "artifacts"
C4 = "unseen-comparison-4-2026-11-15"


def client_for(root: Path | str | None) -> TestClient:
    settings = Settings(faultlab_studies_dir=str(root) if root is not None else "")
    return TestClient(create_app(settings=settings))


def scratch_root(tmp_path: Path) -> Path:
    for name in ("DECLARATION.json", "DECLARATION.sha256", "comparison.json", "E/unseen-study.json", "Q/unseen-study.json"):
        (tmp_path / C4 / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ARTIFACTS / C4 / name, tmp_path / C4 / name)
    (tmp_path / C4 / "sealed").mkdir()
    (tmp_path / C4 / "sealed" / "cases.json").write_text('{"cases": []}')
    return tmp_path


def test_the_default_root_is_the_repositorys_artifacts_folder():
    assert Settings().studies_path == ARTIFACTS
    with client_for(None) as client:
        response = client.get("/api/studies")
    assert response.status_code == 200
    ids = [study["id"] for study in response.json()["studies"]]
    assert C4 in ids and "repair-study-v3-2026-11-14" in ids


def test_list_detail_and_record_file(tmp_path):
    with client_for(scratch_root(tmp_path)) as client:
        index = client.get("/api/studies").json()
        detail = client.get(f"/api/studies/{C4}")
        record = client.get(f"/api/studies/{C4}/files/Q/unseen-study.json")
    assert index["schema"] == "faultlab-study-index/v1" and [s["id"] for s in index["studies"]] == [C4]
    assert detail.status_code == 200 and detail.json()["schema"] == "faultlab-study/v1"
    assert [arm["decision"] for arm in detail.json()["arms"]] == ["NOT_TRANSFERRED", "TRANSFERRED"]
    assert record.status_code == 200 and record.json()["decision"] == "TRANSFERRED"


def test_unknown_names_and_unpublished_files_are_not_found(tmp_path):
    with client_for(scratch_root(tmp_path)) as client:
        responses = [client.get(path) for path in (
            "/api/studies/unseen-comparison-9-2026-12-01", f"/api/studies/{C4}/files/sealed/cases.json",
            f"/api/studies/{C4}/files/launch.sh", f"/api/studies/{C4}/files/E/../sealed/cases.json",
            "/api/studies/..%2F..%2Fetc", f"/api/studies/{C4}/files/%2Fetc%2Fpasswd")]
    for response in responses:
        assert response.status_code == 404, response.request.url
        body = response.json()
        # Ours, or the framework's when an encoded slash makes the path match no study route at all.
        assert body.get("error", {}).get("code") == "STUDY_NOT_FOUND" or body == {"detail": "Not Found"}, body


def test_an_unreadable_record_answers_with_a_contract_error(tmp_path):
    root = scratch_root(tmp_path)
    (root / C4 / "comparison.json").write_text("{")
    with client_for(root) as client:
        response = client.get(f"/api/studies/{C4}")
        index = client.get("/api/studies")
    assert response.status_code == 500 and response.json()["error"]["code"] == "STUDY_RECORD_UNREADABLE"
    assert index.status_code == 200 and index.json()["studies"][0]["problems"]


def test_study_pages_load_no_settings_file_and_contact_no_provider(tmp_path):
    root = scratch_root(tmp_path)
    app = create_app(settings=Settings(faultlab_studies_dir=str(root)))
    with (
        patch.object(Settings, "from_env", side_effect=AssertionError("Unexpected settings load")),
        patch("app.providers.runtime.RuntimeProvider.complete", side_effect=AssertionError("Unexpected provider call")),
        TestClient(app) as client,
    ):
        assert client.get("/api/studies").status_code == 200
        assert client.get(f"/api/studies/{C4}").status_code == 200


def test_a_foreign_host_is_refused():
    with client_for(None) as client:
        response = client.get("/api/studies", headers={"host": "attacker.example"})
    assert response.status_code == 403


def test_the_study_pages_answer_where_the_server_runs_without_the_repository_root_on_the_path():
    """uvicorn runs from backend/ with only that folder on the path (scripts/start-backend.sh); pytest adds the
    repository root, which once hid an import that failed in the real server."""
    import subprocess
    import sys
    script = (
        "import sys, pathlib\n"
        "root = pathlib.Path.cwd().parent.resolve()\n"
        "sys.path[:] = [p for p in sys.path if pathlib.Path(p or '.').resolve() != root]\n"
        "from fastapi.testclient import TestClient\n"
        "from app.config import Settings\n"
        "from app.main import create_app\n"
        "with TestClient(create_app(settings=Settings())) as client:\n"
        "    response = client.get('/api/studies')\n"
        "print(response.status_code, len(response.json().get('studies', [])))\n")
    env = {key: value for key, value in __import__("os").environ.items() if key != "PYTHONPATH"}
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1], env=env,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]
    status, count = result.stdout.split()
    assert status == "200" and int(count) >= 16

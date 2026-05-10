from pathlib import Path

from fastapi.testclient import TestClient

from deployer.api import _refs_payload, _status_summary_payload, create_app
from deployer.config import DeployerConfig


def _project(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "docker-compose.yml").write_text("services: {}\n")
    (path / "deployer.yml").write_text(
        """
name: myapp
service: app
port: 8000
routes:
  - subdomain: myapp
"""
    )
    return path


def _client(tmp_path: Path) -> TestClient:
    app = create_app(
        DeployerConfig(
            state_db=tmp_path / "state.db",
            runtime_dir=tmp_path / "runtime",
        )
    )
    return TestClient(app)


def test_api_health_and_root(tmp_path: Path):
    client = _client(tmp_path)

    assert client.get("/api/health").json() == {"status": "ok"}
    response = client.get("/")
    assert response.status_code == 200
    assert "deployer-root" in response.text

    response = client.get("/ui/app.js")
    assert response.status_code == 200
    assert "loadAll" in response.text


def test_api_service_local_env_deploy_history_and_delete(tmp_path: Path):
    project = _project(tmp_path / "project")
    client = _client(tmp_path)

    response = client.post(
        "/api/services",
        json={"name": "myapp", "source_type": "local", "path": str(project)},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "myapp"
    assert response.json()["environments"][0]["name"] == "prod"

    assert client.get("/api/services").json()[0]["name"] == "myapp"
    detail = client.get("/api/services/myapp").json()
    assert detail["source_type"] == "local"
    assert detail["source_status"]["available"] is True
    assert detail["source_status"]["path_exists"] is True
    assert detail["environments"][0]["public_url"] == "https://myapp.busypage.ru/"
    assert detail["environments"][1]["public_url"] == "https://myapp.dev.busypage.ru/"

    response = client.post("/api/services/myapp/env/prod", json={"key": "TOKEN", "value": "abc"})
    assert response.status_code == 200
    assert response.json()["env"] == {"TOKEN": "abc"}
    assert client.get("/api/services/myapp/env/prod").json()["env"] == {"TOKEN": "abc"}

    response = client.post(
        "/api/services/myapp/deploy",
        json={"environment": "prod", "ref": "main", "dry_run": True},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "success"
    assert job["deployment_id"] is not None
    assert "Dry run" in job["log"]

    jobs = client.get("/api/jobs?service=myapp&environment=prod").json()
    assert jobs["jobs"][0]["id"] == job_id
    assert "Dry run" in jobs["jobs"][0]["log"]

    history = client.get("/api/services/myapp/history?environment=prod").json()
    assert history["environments"][0]["current_ref"] == "main"
    assert history["deployments"][0]["action"] == "deploy"

    response = client.delete("/api/services/myapp/env/prod/TOKEN")
    assert response.status_code == 200
    assert response.json()["env"] == {}

    response = client.delete("/api/services/myapp")
    assert response.status_code == 200
    assert response.json() == {"removed": True, "service": "myapp"}


def test_api_validation_and_catalog_errors(tmp_path: Path):
    project = _project(tmp_path / "project")
    client = _client(tmp_path)

    response = client.post("/api/services", json={"name": "myapp", "source_type": "local"})
    assert response.status_code == 422
    assert response.json()["detail"] == "path is required for local services"

    assert client.post(
        "/api/services",
        json={"name": "myapp", "source_type": "local", "path": str(project)},
    ).status_code == 201

    response = client.post(
        "/api/services",
        json={"name": "myapp", "source_type": "local", "path": str(project)},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Service already exists: myapp"

    response = client.delete("/api/services/unknown")
    assert response.status_code == 404


def test_api_parses_refs_payload():
    payload = _refs_payload("abc refs/heads/main\ndef refs/tags/v1\n")

    assert payload == [
        {"name": "main", "full_name": "refs/heads/main", "type": "branch", "commit": "abc"},
        {"name": "v1", "full_name": "refs/tags/v1", "type": "tag", "commit": "def"},
    ]


def test_api_parses_status_summary_payload():
    summary = _status_summary_payload(
        '[{"Name":"myapp","Service":"app","State":"running","Health":"healthy"}]'
    )

    assert summary["running"] is True
    assert summary["healthy"] is True
    assert summary["health"] == "healthy"
    assert summary["containers"][0]["state"] == "running"


def test_api_parses_status_summary_payload_from_json_lines():
    summary = _status_summary_payload(
        '{"Name":"myapp","Service":"app","State":"running","Health":"healthy"}\n'
    )

    assert summary["running"] is True
    assert summary["health"] == "healthy"

from pathlib import Path

from fastapi.testclient import TestClient

from deployer.api import create_app
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
    assert client.get("/").json()["service"] == "home-paas-deployer"


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
    assert client.get("/api/services/myapp").json()["source_type"] == "local"

    response = client.post("/api/services/myapp/env/prod", json={"key": "TOKEN", "value": "abc"})
    assert response.status_code == 200
    assert response.json()["env"] == {"TOKEN": "abc"}
    assert client.get("/api/services/myapp/env/prod").json()["env"] == {"TOKEN": "abc"}

    response = client.post(
        "/api/services/myapp/deploy",
        json={"environment": "prod", "ref": "main", "dry_run": True},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert "Dry run" in response.json()["log"]

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

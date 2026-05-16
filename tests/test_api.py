from pathlib import Path
import hashlib
import hmac

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


def _client_with_secret(tmp_path: Path, secret: str) -> TestClient:
    app = create_app(
        DeployerConfig(
            state_db=tmp_path / "state.db",
            runtime_dir=tmp_path / "runtime",
            webhook_secret=secret,
        )
    )
    return TestClient(app)


def test_api_health_and_root(tmp_path: Path):
    client = _client(tmp_path)

    assert client.get("/api/health").json() == {"status": "ok"}
    response = client.get("/")
    assert response.status_code == 200
    assert "deployer-root" in response.text
    assert "/ui/app.js?v=" in response.text
    assert "/ui/styles.css?v=" in response.text

    response = client.get("/ui/app.js")
    assert response.status_code == 200
    assert "loadAll" in response.text

    response = client.get("/api/version")
    assert response.status_code == 200
    assert response.json()["backend_version"]
    assert response.json()["frontend_version"]


def test_api_service_local_env_deploy_history_and_delete(tmp_path: Path):
    project = _project(tmp_path / "project")
    client = _client(tmp_path)

    response = client.post(
        "/api/services",
        json={"name": "myapp", "source_type": "local", "path": str(project)},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "myapp"
    assert response.json()["environments"] == []

    assert client.post("/api/services/myapp/runtime-targets", json={"name": "prod"}).status_code == 201
    assert client.post("/api/services/myapp/runtime-targets", json={"name": "dev"}).status_code == 201

    assert client.get("/api/services").json()[0]["name"] == "myapp"
    detail = client.get("/api/services/myapp").json()
    assert detail["source_type"] == "local"
    assert detail["source_status"]["available"] is True
    assert detail["source_status"]["path_exists"] is True
    assert detail["environments"][0]["public_url"] == "https://myapp.busypage.ru/"
    assert detail["environments"][1]["public_url"] == "https://myapp.dev.busypage.ru/"
    environments = client.get("/api/environments").json()["environments"]
    prod = next(item for item in environments if item["name"] == "prod")
    assert prod["services"][0]["name"] == "myapp"
    assert prod["services"][0]["runtime"]["public_url"] == "https://myapp.busypage.ru/"
    prod_services = client.get("/api/environments/prod/services").json()["environment"]
    assert prod_services["name"] == "prod"
    assert prod_services["services"][0]["name"] == "myapp"

    response = client.post("/api/services/myapp/env/prod", json={"key": "TOKEN", "value": "abc"})
    assert response.status_code == 200
    assert response.json()["env"] == {"TOKEN": "abc"}
    assert client.get("/api/services/myapp/env/prod").json()["env"] == {"TOKEN": "abc"}

    preview = client.get("/api/services/myapp/preview?environment=prod")
    assert preview.status_code == 200
    assert preview.json()["valid"] is True
    assert preview.json()["env_file_content"] == "TOKEN=abc\n"
    assert "traefik.enable=true" in preview.json()["override_content"]
    assert "environment:\n      TOKEN: abc" in preview.json()["override_content"]
    assert preview.json()["compose_files"] == ["docker-compose.yml"]

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
    assert job["log_truncated"] is False

    jobs = client.get("/api/jobs?service=myapp&environment=prod").json()
    assert jobs["jobs"][0]["id"] == job_id
    assert jobs["jobs"][0]["log"] == ""
    assert jobs["jobs"][0]["log_truncated"] is True

    short_job = client.get(f"/api/jobs/{job_id}?log_limit=8").json()
    assert short_job["log"].startswith("[output truncated")
    assert short_job["log"].endswith("executed")
    assert short_job["log_truncated"] is True

    history = client.get("/api/services/myapp/history?environment=prod").json()
    assert history["environments"][0]["current_ref"] == "main"
    assert history["deployments"][0]["action"] == "deploy"

    response = client.delete("/api/services/myapp/env/prod/TOKEN")
    assert response.status_code == 200
    assert response.json()["env"] == {}

    response = client.delete("/api/services/myapp")
    assert response.status_code == 200
    assert response.json() == {"removed": True, "service": "myapp"}


def test_api_runtime_target_crud_and_dynamic_deploy(tmp_path: Path):
    project = _project(tmp_path / "project")
    client = _client(tmp_path)

    assert client.post(
        "/api/services",
        json={"name": "myapp", "source_type": "local", "path": str(project)},
    ).status_code == 201
    assert client.post("/api/services/myapp/runtime-targets", json={"name": "prod"}).status_code == 201

    response = client.post(
        "/api/environments",
        json={
            "name": "stage",
            "url_prefix": "rc",
            "deploy_mode": "webhook_auto",
            "deploy_source": "tag",
            "deploy_pattern": "^v.+-rc[0-9]+$",
            "deploy_pattern_type": "regex",
        },
    )
    assert response.status_code == 201
    assert response.json()["environment"]["name"] == "stage"
    assert response.json()["environment"]["url_prefix"] == "rc"
    assert response.json()["environment"]["deploy_mode"] == "webhook_auto"

    response = client.post("/api/services/myapp/runtime-targets", json={"name": "stage"})
    assert response.status_code == 201
    assert response.json()["runtime_target"]["name"] == "stage"

    detail = client.get("/api/services/myapp").json()
    stage = next(item for item in detail["environments"] if item["name"] == "stage")
    assert stage["public_url"] == "https://myapp.rc.busypage.ru/"
    assert stage["deploy_source"] == "tag"

    preview = client.get("/api/services/myapp/preview?environment=stage")
    assert preview.status_code == 200
    assert preview.json()["public_url"] == "https://myapp.rc.busypage.ru/"
    assert "Host(`myapp.rc.busypage.ru`)" in preview.json()["override_content"]

    response = client.post(
        "/api/services/myapp/deploy",
        json={"environment": "stage", "ref": "v1-rc1", "dry_run": True},
    )
    assert response.status_code == 202
    job = client.get(f"/api/jobs/{response.json()['id']}").json()
    assert job["status"] == "success"
    assert job["environment"] == "stage"

    response = client.patch(
        "/api/environments/stage",
        json={
            "url_prefix": "stage",
            "deploy_mode": "webhook_gated",
        },
    )
    assert response.status_code == 200
    assert response.json()["environment"]["url_prefix"] == "stage"
    assert response.json()["environment"]["deploy_mode"] == "webhook_gated"

    response = client.delete("/api/services/myapp/runtime-targets/stage")
    assert response.status_code == 200
    assert response.json() == {"removed": True, "service": "myapp", "environment": "stage"}


def test_api_environment_project_workflow_without_manifest(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "docker-compose.yml").write_text(
        """
services:
  app:
    image: nginx:alpine
"""
    )
    client = _client(tmp_path)

    response = client.post(
        "/api/environments/dev/projects",
        json={
            "name": "tasktrack",
            "source_type": "local",
            "path": str(source),
            "default_ref": "dev",
        },
    )
    assert response.status_code == 201
    assert response.json()["environment"] == "dev"
    assert response.json()["name"] == "tasktrack"
    assert response.json()["compose_files"] == ["docker-compose.yml"]

    response = client.post(
        "/api/environments/dev/projects/tasktrack/components",
        json={
            "name": "web",
            "mode": "compose",
            "compose_service": "app",
            "port": 8080,
        },
    )
    assert response.status_code == 201
    assert response.json()["component"]["compose_service"] == "app"

    response = client.post(
        "/api/environments/dev/projects/tasktrack/endpoints",
        json={
            "name": "web",
            "component": "web",
            "port": 8080,
            "subdomain": "tasktrack",
            "auth": "sso",
            "healthcheck_path": "/health",
        },
    )
    assert response.status_code == 201
    assert response.json()["endpoint"]["public_url"] == "https://tasktrack.dev.busypage.ru/"

    response = client.post(
        "/api/environments/dev/projects/tasktrack/dependencies",
        json={
            "name": "postgres",
            "type": "postgres",
            "target": "postgres-main/tasktrack_dev",
            "outputs": {"DATABASE_URL": "postgresql://example/tasktrack_dev"},
        },
    )
    assert response.status_code == 201
    assert response.json()["dependency"]["outputs"]["DATABASE_URL"] == "postgresql://example/tasktrack_dev"

    response = client.patch(
        "/api/environments/dev/projects/tasktrack/components/web",
        json={
            "name": "web",
            "mode": "compose",
            "compose_service": "app",
            "port": 9000,
        },
    )
    assert response.status_code == 200
    assert response.json()["component"]["port"] == 9000

    response = client.patch(
        "/api/environments/dev/projects/tasktrack/endpoints/web",
        json={
            "name": "web",
            "component": "web",
            "port": 9000,
            "subdomain": "tasktrack",
            "auth": "sso",
            "healthcheck_path": "/ready",
        },
    )
    assert response.status_code == 200
    assert response.json()["endpoint"]["healthcheck_path"] == "/ready"

    response = client.patch(
        "/api/environments/dev/projects/tasktrack/dependencies/postgres",
        json={
            "name": "postgres",
            "type": "postgres",
            "target": "postgres-main/tasktrack_stage",
            "outputs": {"DATABASE_URL": "postgresql://example/tasktrack_stage"},
        },
    )
    assert response.status_code == 200
    assert response.json()["dependency"]["target"] == "postgres-main/tasktrack_stage"

    response = client.post(
        "/api/environments/dev/projects/tasktrack/env",
        json={"key": "APP_ENV", "value": "dev"},
    )
    assert response.status_code == 200
    assert response.json()["env"] == {"APP_ENV": "dev"}

    detail = client.get("/api/environments/dev/projects/tasktrack").json()
    assert detail["components"][0]["name"] == "web"
    assert detail["endpoints"][0]["public_url"] == "https://tasktrack.dev.busypage.ru/"
    assert detail["dependencies"][0]["target"] == "postgres-main/tasktrack_stage"
    assert detail["public_urls"] == ["https://tasktrack.dev.busypage.ru/"]

    projects = client.get("/api/environments/dev/projects").json()
    assert projects["environment"]["name"] == "dev"
    assert projects["projects"][0]["name"] == "tasktrack"

    preview = client.get("/api/environments/dev/projects/tasktrack/preview")
    assert preview.status_code == 200
    assert preview.json()["valid"] is True
    assert "Host(`tasktrack.dev.busypage.ru`)" in preview.json()["override_content"]
    assert preview.json()["env_file_content"] == "APP_ENV=dev\nDATABASE_URL=postgresql://example/tasktrack_stage\n"

    response = client.post(
        "/api/environments/dev/projects/tasktrack/deploy",
        json={"ref": "dev", "dry_run": True},
    )
    assert response.status_code == 202
    job = client.get(f"/api/jobs/{response.json()['id']}").json()
    assert job["status"] == "success"
    assert job["project"] == "tasktrack"
    assert job["environment"] == "dev"
    assert "-p dev-tasktrack" in job["log"]
    assert "deployer.yml" not in job["log"]

    detail = client.get("/api/environments/dev/projects/tasktrack").json()
    assert detail["current_ref"] == "dev"
    assert detail["last_deployment_id"] == job["deployment_id"]

    assert client.delete("/api/environments/dev/projects/tasktrack/endpoints/web").status_code == 200
    assert client.delete("/api/environments/dev/projects/tasktrack/dependencies/postgres").status_code == 200
    assert client.delete("/api/environments/dev/projects/tasktrack/components/web").status_code == 200

    response = client.delete("/api/environments/dev/projects/tasktrack/env/APP_ENV")
    assert response.status_code == 200
    assert response.json()["env"] == {}

    response = client.delete("/api/environments/dev/projects/tasktrack")
    assert response.status_code == 200
    assert response.json() == {"removed": True, "environment": "dev", "project": "tasktrack"}


def test_api_github_webhook_auto_and_gated_projects(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "docker-compose.yml").write_text("services:\n  app:\n    image: nginx:alpine\n")
    secret = "top-secret"
    client = _client_with_secret(tmp_path, secret)

    assert client.post(
        "/api/environments/dev/projects",
        json={
            "name": "tasktrack",
            "source_type": "local",
            "path": str(source),
            "default_ref": "dev",
            "deploy_mode": "webhook_auto",
            "deploy_source": "branch",
            "deploy_pattern": "dev",
            "deploy_pattern_type": "exact",
        },
    ).status_code == 201
    assert client.post(
        "/api/environments/prod/projects",
        json={
            "name": "tasktrack",
            "source_type": "local",
            "path": str(source),
            "default_ref": "main",
            "deploy_mode": "webhook_gated",
            "deploy_source": "tag",
            "deploy_pattern": "^v[0-9]+$",
            "deploy_pattern_type": "regex",
        },
    ).status_code == 201
    for environment in ("dev", "prod"):
        assert client.post(
            f"/api/environments/{environment}/projects/tasktrack/components",
            json={"name": "web", "mode": "compose", "compose_service": "app", "port": 8080},
        ).status_code == 201
        assert client.post(
            f"/api/environments/{environment}/projects/tasktrack/endpoints",
            json={"name": "web", "component": "web", "port": 8080, "subdomain": "tasktrack"},
        ).status_code == 201

    push_payload = {
        "ref": "refs/heads/dev",
        "after": "dev123",
        "repository": {"full_name": "org/tasktrack"},
    }
    response = client.post(
        "/api/webhooks/github",
        content=json_bytes(push_payload),
        headers=_github_headers(secret, push_payload, event="push", delivery="delivery-dev"),
    )
    assert response.status_code == 202
    assert response.json()["event"]["action"] == "scheduled"
    assert response.json()["event"]["matched_projects"] == ["dev/tasktrack"]
    job = client.get(f"/api/jobs/{response.json()['jobs'][0]['id']}").json()
    assert job["action"] == "deploy"
    assert job["ref"] == "dev"

    tag_payload = {
        "ref": "refs/tags/v1",
        "after": "tag123",
        "repository": {"full_name": "org/tasktrack"},
    }
    response = client.post(
        "/api/webhooks/github",
        content=json_bytes(tag_payload),
        headers=_github_headers(secret, tag_payload, event="push", delivery="delivery-tag"),
    )
    assert response.status_code == 202
    assert response.json()["event"]["action"] == "candidate"
    assert response.json()["jobs"] == []
    prod = client.get("/api/environments/prod/projects/tasktrack").json()
    assert prod["candidate_ref"] == "v1"
    assert prod["candidate_commit"] == "tag123"

    response = client.post("/api/environments/prod/projects/tasktrack/deploy-candidate", json={"dry_run": True})
    assert response.status_code == 202
    job = client.get(f"/api/jobs/{response.json()['id']}").json()
    assert job["status"] == "success"
    assert job["ref"] == "v1"
    assert client.get("/api/environments/prod/projects/tasktrack").json()["candidate_ref"] is None

    events = client.get("/api/webhook-events").json()["events"]
    assert [event["delivery_id"] for event in events[:2]] == ["delivery-tag", "delivery-dev"]


def test_api_github_webhook_rejects_invalid_signature(tmp_path: Path):
    client = _client_with_secret(tmp_path, "top-secret")
    response = client.post(
        "/api/webhooks/github",
        content=json_bytes({"ref": "refs/heads/dev"}),
        headers={"X-Hub-Signature-256": "sha256=broken", "X-GitHub-Event": "push"},
    )

    assert response.status_code == 401


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

    response = client.post("/api/services/myapp/env/prod", json={"key": "TOKEN", "value": "abc"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown service environment: myapp/prod"

    response = client.post(
        "/api/services",
        json={"name": "myapp", "source_type": "local", "path": str(project)},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Service already exists: myapp"

    response = client.delete("/api/services/unknown")
    assert response.status_code == 404


def test_api_preview_reports_validation_errors(tmp_path: Path):
    project = _project(tmp_path / "project")
    client = _client(tmp_path)

    assert client.post(
        "/api/services",
        json={"name": "myapp", "source_type": "local", "path": str(project)},
    ).status_code == 201
    assert client.post("/api/services/myapp/runtime-targets", json={"name": "prod"}).status_code == 201

    (project / "docker-compose.yml").unlink()
    preview = client.get("/api/services/myapp/preview?environment=prod")

    assert preview.status_code == 200
    assert preview.json()["valid"] is False
    assert preview.json()["override_content"] is None
    assert preview.json()["errors"] == [
        {"scope": "manifest", "message": "Missing compose files: docker-compose.yml"}
    ]


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


def json_bytes(payload: dict) -> bytes:
    import json

    return json.dumps(payload, separators=(",", ":")).encode()


def _github_headers(secret: str, payload: dict, event: str, delivery: str) -> dict:
    body = json_bytes(payload)
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {
        "X-Hub-Signature-256": signature,
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery,
        "Content-Type": "application/json",
    }

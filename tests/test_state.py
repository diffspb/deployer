from pathlib import Path

from deployer.state import StateStore


def test_state_records_deployment_history(tmp_path: Path):
    state = StateStore(tmp_path / "state.db")
    deployment_id = state.create_deployment("myapp", "dev", "deploy", "main")

    state.finish_deployment(deployment_id, "success", "log text")
    history = state.history("myapp")

    assert len(history) == 1
    assert history[0].id == deployment_id
    assert history[0].environment == "dev"
    assert history[0].action == "deploy"
    assert history[0].status == "success"
    assert history[0].version == "main"
    assert history[0].log == "log text"


def test_state_filters_history_by_environment(tmp_path: Path):
    state = StateStore(tmp_path / "state.db")
    prod_id = state.create_deployment("myapp", "prod", "deploy", "v1")
    dev_id = state.create_deployment("myapp", "dev", "stop", None)
    state.finish_deployment(prod_id, "success", "prod")
    state.finish_deployment(dev_id, "success", "dev")

    history = state.history("myapp", environment="dev")

    assert len(history) == 1
    assert history[0].environment == "dev"
    assert history[0].action == "stop"


def test_state_stores_services_without_default_runtime_targets(tmp_path: Path):
    state = StateStore(tmp_path / "state.db")

    service = state.add_service("myapp", "local", "/srv/myapp")

    assert service.name == "myapp"
    assert state.list_services()[0].source_path == "/srv/myapp"
    assert state.list_environments("myapp") == []
    prod = state.add_environment("myapp", "prod")
    dev = state.add_environment("myapp", "dev")
    assert prod.subdomain == "myapp"
    assert dev.subdomain == "myapp"
    assert prod.url_prefix == ""
    assert dev.url_prefix == "dev"
    assert prod.deploy_mode == "manual"
    assert prod.deploy_source is None


def test_state_manages_dynamic_runtime_targets(tmp_path: Path):
    state = StateStore(tmp_path / "state.db")
    state.add_service("myapp", "local", "/srv/myapp")
    state.add_environment("myapp", "prod")
    state.add_environment("myapp", "dev")

    stage_profile = state.add_environment_profile(
        "stage",
        url_prefix="stage",
        deploy_mode="webhook_auto",
        deploy_source="tag",
        deploy_pattern="^v.+-rc[0-9]+$",
        deploy_pattern_type="regex",
    )
    stage = state.add_environment(
        "myapp",
        "stage",
    )
    state.add_environment_profile("preview-123", url_prefix="p123")
    preview = state.add_environment("myapp", "preview-123")

    assert stage_profile.deploy_mode == "webhook_auto"
    assert stage.url_prefix == "stage"
    assert stage.deploy_mode == "webhook_auto"
    assert stage.deploy_source == "tag"
    assert stage.deploy_pattern_type == "regex"
    assert preview.url_prefix == "p123"
    assert [item.name for item in state.list_environments("myapp")] == ["prod", "dev", "preview-123", "stage"]

    updated_profile = state.update_environment_profile("stage", url_prefix="rc", deploy_mode="webhook_gated")
    updated = state.require_environment("myapp", "stage")
    assert updated_profile.url_prefix == "rc"
    assert updated.url_prefix == "rc"
    assert updated.deploy_mode == "webhook_gated"
    assert state.remove_environment("myapp", "preview-123") is True
    assert state.get_environment("myapp", "preview-123") is None


def test_state_updates_environment_vars_and_version(tmp_path: Path):
    state = StateStore(tmp_path / "state.db")
    state.add_service("myapp", "git", "/srv/myapp", source_url="git@example.com/myapp.git")
    state.add_environment("myapp", "prod")

    state.set_env_var("myapp", "prod", "TOKEN", "abc")
    state.set_env_var("myapp", "prod", "PORT", "8000")
    state.unset_env_var("myapp", "prod", "PORT")
    deployment_id = state.create_deployment("myapp", "prod", "deploy", "main")
    state.finish_deployment(deployment_id, "success", "ok")
    state.update_environment_version("myapp", "prod", deployment_id, "main", "main", "abc123")

    env = state.require_environment("myapp", "prod")
    assert env.env_vars == {"TOKEN": "abc"}
    assert env.current_version == "main"
    assert env.current_ref == "main"
    assert env.current_commit == "abc123"
    assert env.last_deployment_id == deployment_id


def test_state_updates_environment_source_state_without_successful_deployment(tmp_path: Path):
    state = StateStore(tmp_path / "state.db")
    state.add_service("myapp", "local", "/tmp/myapp")
    state.add_environment("myapp", "prod")

    state.update_environment_source_state("myapp", "prod", "main", "main", "abc123")

    env = state.require_environment("myapp", "prod")
    assert env.current_version == "main"
    assert env.current_ref == "main"
    assert env.current_commit == "abc123"
    assert env.last_deployment_id is None


def test_state_tracks_runtime_jobs(tmp_path: Path):
    state = StateStore(tmp_path / "state.db")

    job_id = state.create_job("myapp", "prod", "deploy", ref="main", dry_run=True)
    job = state.get_job(job_id)

    assert job is not None
    assert job.status == "queued"
    assert job.ref == "main"
    assert job.dry_run is True

    state.start_job(job_id)
    deployment_id = state.create_deployment("myapp", "prod", "deploy", "main")
    state.finish_deployment(deployment_id, "success", "deploy ok")
    state.finish_job(job_id, "success", "job ok", deployment_id=deployment_id)

    finished = state.get_job(job_id)
    assert finished is not None
    assert finished.status == "success"
    assert finished.deployment_id == deployment_id
    assert finished.started_at is not None
    assert finished.finished_at is not None
    assert state.list_jobs(service="myapp")[0].id == job_id


def test_state_stores_environment_scoped_projects(tmp_path: Path):
    state = StateStore(tmp_path / "state.db")

    dev = state.add_project("dev", "tasktrack", "local", "/srv/tasktrack", default_ref="dev")
    prod = state.add_project("prod", "tasktrack", "local", "/srv/tasktrack", default_ref="main")
    state.set_project_env_var("dev", "tasktrack", "APP_ENV", "dev")
    state.set_project_env_var("prod", "tasktrack", "APP_ENV", "prod")

    assert dev.environment == "dev"
    assert prod.environment == "prod"
    assert state.require_project("dev", "tasktrack").default_ref == "dev"
    assert state.require_project("prod", "tasktrack").default_ref == "main"
    assert state.require_project("dev", "tasktrack").env_vars == {"APP_ENV": "dev"}
    assert state.require_project("prod", "tasktrack").env_vars == {"APP_ENV": "prod"}
    assert [project.environment for project in state.list_projects()] == ["dev", "prod"]
    assert [project.name for project in state.list_projects("dev")] == ["tasktrack"]


def test_state_stores_project_components_endpoints_and_dependencies(tmp_path: Path):
    state = StateStore(tmp_path / "state.db")
    state.add_project("dev", "tasktrack", "local", "/srv/tasktrack")

    component = state.add_component(
        "dev",
        "tasktrack",
        "backend",
        mode="build",
        build_context="backend",
        dockerfile="Dockerfile",
        port=8000,
        env_vars={"APP_ENV": "dev"},
    )
    endpoint = state.add_endpoint(
        "dev",
        "tasktrack",
        "api",
        "backend",
        8000,
        subdomain="api.tasktrack",
        auth="sso",
        healthcheck_path="/api/v1/health",
    )
    dependency = state.add_dependency(
        "dev",
        "tasktrack",
        "postgres",
        "postgres",
        "postgres-main/tasktrack_dev",
        outputs={"DATABASE_URL": "postgresql://tasktrack_dev@example/tasktrack_dev"},
    )

    assert component.build_context == "backend"
    assert state.list_components("dev", "tasktrack")[0].env_vars == {"APP_ENV": "dev"}
    assert endpoint.component == "backend"
    assert endpoint.auth == "sso"
    assert endpoint.healthcheck_path == "/api/v1/health"
    assert dependency.outputs["DATABASE_URL"].startswith("postgresql://")
    assert state.list_dependencies("dev", "tasktrack")[0].target == "postgres-main/tasktrack_dev"

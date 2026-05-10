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


def test_state_stores_services_and_default_environments(tmp_path: Path):
    state = StateStore(tmp_path / "state.db")

    service = state.add_service("myapp", "local", "/srv/myapp")

    assert service.name == "myapp"
    assert state.list_services()[0].source_path == "/srv/myapp"
    prod = state.require_environment("myapp", "prod")
    dev = state.require_environment("myapp", "dev")
    assert prod.subdomain == "myapp"
    assert dev.subdomain == "myapp"


def test_state_updates_environment_vars_and_version(tmp_path: Path):
    state = StateStore(tmp_path / "state.db")
    state.add_service("myapp", "git", "/srv/myapp", source_url="git@example.com/myapp.git")

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

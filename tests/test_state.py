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

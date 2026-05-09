from pathlib import Path

from deployer.state import StateStore


def test_state_records_deployment_history(tmp_path: Path):
    state = StateStore(tmp_path / "state.db")
    deployment_id = state.create_deployment("myapp", "main")

    state.finish_deployment(deployment_id, "success", "log text")
    history = state.history("myapp")

    assert len(history) == 1
    assert history[0].id == deployment_id
    assert history[0].status == "success"
    assert history[0].version == "main"
    assert history[0].log == "log text"

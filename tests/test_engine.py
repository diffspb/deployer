from pathlib import Path

from deployer.errors import CommandError
from deployer.engine import DeploymentEngine, compose_command
from deployer.manifest import parse_manifest
from deployer.state import StateStore


def test_compose_command_includes_all_files():
    manifest = parse_manifest(
        {
            "name": "myapp",
            "service": "app",
            "port": 8000,
            "compose": {"files": ["docker-compose.yml", "docker-compose.prod.yml"]},
            "routes": [{"subdomain": "myapp"}],
        }
    )

    command = compose_command(manifest, Path(".deployer/docker-compose.override.yml"))

    assert command == [
        "docker",
        "compose",
        "-p",
        "myapp",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.prod.yml",
        "-f",
        ".deployer/docker-compose.override.yml",
        "up",
        "-d",
        "--build",
    ]

    down_command = compose_command(manifest, Path(".deployer/docker-compose.override.yml"), action="down")
    assert down_command[-1] == "down"

    ps_command = compose_command(manifest, Path(".deployer/docker-compose.override.yml"), action="ps")
    assert ps_command[-1] == "ps"

    dev_command = compose_command(manifest, Path(".deployer/docker-compose.override.yml"), environment="dev")
    assert dev_command[3] == "myapp-dev"


def test_dry_run_deploy_generates_override_and_history(tmp_path: Path):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "deployer.yml").write_text(
        """
name: myapp
service: app
port: 8000
compose:
  files:
    - docker-compose.yml
routes:
  - host: myapp.busypage.ru
    auth: sso
"""
    )
    state = StateStore(tmp_path / "state.db")
    engine = DeploymentEngine(state)

    result = engine.deploy(tmp_path, version="main", dry_run=True)

    assert result.status == "success"
    assert result.override_path.exists()
    assert result.override_path.name == "prod.override.yml"
    assert "Dry run" in result.log
    record = state.history("myapp")[0]
    assert record.status == "success"
    assert record.environment == "prod"
    assert record.action == "deploy"


def test_deploy_records_command_failure(tmp_path: Path):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "deployer.yml").write_text(
        """
name: myapp
service: app
port: 8000
routes:
  - host: myapp.busypage.ru
"""
    )

    class FailingRunner:
        def run(self, args, cwd):
            raise CommandError("failed", 1, "docker failed")

    state = StateStore(tmp_path / "state.db")
    engine = DeploymentEngine(state, runner=FailingRunner())

    result = engine.deploy(tmp_path)

    assert result.status == "failed"
    assert "docker failed" in result.log
    assert state.history("myapp")[0].status == "failed"


def test_stop_dry_run_uses_down_and_environment_override(tmp_path: Path):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "deployer.yml").write_text(
        """
name: myapp
service: app
port: 8000
routes:
  - subdomain: myapp
"""
    )
    state = StateStore(tmp_path / "state.db")
    engine = DeploymentEngine(state)

    result = engine.stop(tmp_path, dry_run=True, environment="dev")

    assert result.status == "success"
    assert result.override_path.name == "dev.override.yml"
    assert " docker compose -p myapp-dev " in f" {result.log} "
    assert result.log.strip().endswith("Dry run: docker compose was not executed")
    record = state.history("myapp", environment="dev")[0]
    assert record.action == "stop"


def test_status_returns_runner_output(tmp_path: Path):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "deployer.yml").write_text(
        """
name: myapp
service: app
port: 8000
routes:
  - subdomain: myapp
"""
    )

    class StatusRunner:
        def run(self, args, cwd):
            from deployer.runner import CommandResult

            assert args[-1] == "ps"
            return CommandResult(tuple(args), 0, "NAME STATUS\n")

    engine = DeploymentEngine(StateStore(tmp_path / "state.db"), runner=StatusRunner())

    result = engine.status(tmp_path)

    assert result.status == "success"
    assert result.log == "NAME STATUS\n"

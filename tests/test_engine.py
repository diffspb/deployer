from pathlib import Path

from deployer.errors import CommandError
from deployer.engine import COMPOSE_BUILD_ENV, DeploymentEngine, compose_command
from deployer.manifest import parse_manifest
from deployer.runner import CommandResult
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
        "--force-recreate",
    ]

    down_command = compose_command(manifest, Path(".deployer/docker-compose.override.yml"), action="down")
    assert down_command[-1] == "down"

    stop_command = compose_command(manifest, Path(".deployer/docker-compose.override.yml"), action="stop")
    assert stop_command[-1] == "stop"

    restart_command = compose_command(manifest, Path(".deployer/docker-compose.override.yml"), action="restart")
    assert restart_command[-1] == "restart"

    ps_command = compose_command(manifest, Path(".deployer/docker-compose.override.yml"), action="ps")
    assert ps_command[-3:] == ["ps", "--format", "json"]

    logs_command = compose_command(manifest, Path(".deployer/docker-compose.override.yml"), action="logs", tail=50)
    assert logs_command[-3:] == ["logs", "--tail", "50"]

    dev_command = compose_command(manifest, Path(".deployer/docker-compose.override.yml"), environment="dev")
    assert dev_command[3] == "myapp-dev"

    env_command = compose_command(
        manifest,
        Path(".deployer/docker-compose.override.yml"),
        env_file="/var/lib/deployer/services/myapp/env/prod.env",
    )
    assert env_command[4:6] == ["--env-file", "/var/lib/deployer/services/myapp/env/prod.env"]


def test_deploy_runs_compose_with_buildkit_env(tmp_path: Path):
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

    class Runner:
        def run(self, args, cwd, env=None):
            assert env == COMPOSE_BUILD_ENV
            return CommandResult(tuple(args), 0, "built\n")

    engine = DeploymentEngine(StateStore(tmp_path / "state.db"), runner=Runner(), health_checker=lambda manifest, **kwargs: (True, "ok"))

    result = engine.deploy(tmp_path)

    assert result.status == "success"


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
        def run(self, args, cwd, env=None):
            raise CommandError("failed", 1, "docker failed")

    state = StateStore(tmp_path / "state.db")
    engine = DeploymentEngine(state, runner=FailingRunner())

    result = engine.deploy(tmp_path)

    assert result.status == "failed"
    assert "docker failed" in result.log
    assert state.history("myapp")[0].status == "failed"


def test_stop_dry_run_uses_stop_and_environment_override(tmp_path: Path):
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
    assert result.log.split("Command: ", 1)[1].splitlines()[0].endswith(" stop")
    assert result.log.strip().endswith("Dry run: docker compose was not executed")
    record = state.history("myapp", environment="dev")[0]
    assert record.action == "stop"


def test_down_and_restart_dry_run_record_actions(tmp_path: Path):
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

    down = engine.down(tmp_path, dry_run=True)
    restart = engine.restart(tmp_path, dry_run=True)

    assert down.status == "success"
    assert down.log.split("Command: ", 1)[1].splitlines()[0].endswith(" down")
    assert restart.status == "success"
    assert restart.log.split("Command: ", 1)[1].splitlines()[0].endswith(" restart")
    assert [record.action for record in state.history("myapp", limit=2)] == ["restart", "down"]


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
        def run(self, args, cwd, env=None):
            from deployer.runner import CommandResult

            assert args[-3:] == ["ps", "--format", "json"]
            return CommandResult(tuple(args), 0, '[{"Name":"myapp","Service":"app","State":"running","Health":"healthy"}]\n')

    engine = DeploymentEngine(StateStore(tmp_path / "state.db"), runner=StatusRunner())

    result = engine.status(tmp_path)

    assert result.status == "success"
    assert '"State":"running"' in result.log


def test_logs_returns_runner_output(tmp_path: Path):
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

    class LogsRunner:
        def run(self, args, cwd, env=None):
            from deployer.runner import CommandResult

            assert args[-3:] == ["logs", "--tail", "10"]
            return CommandResult(tuple(args), 0, "app log\n")

    engine = DeploymentEngine(StateStore(tmp_path / "state.db"), runner=LogsRunner())

    result = engine.logs(tmp_path, tail=10)

    assert result.status == "success"
    assert result.log == "app log\n"

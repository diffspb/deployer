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
            "routes": [{"host": "myapp.busypage.ru"}],
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
    assert "Dry run" in result.log
    assert state.history("myapp")[0].status == "success"


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

from pathlib import Path
import subprocess

import pytest

from deployer.catalog import CatalogError, ServiceCatalog, render_env
from deployer.engine import DeploymentEngine
from deployer.runner import CommandResult
from deployer.state import StateStore


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


def test_catalog_adds_local_service_and_renders_env(tmp_path: Path):
    project = _project(tmp_path / "project")
    catalog = ServiceCatalog(StateStore(tmp_path / "state.db"), runtime_dir=tmp_path / "runtime")

    service = catalog.add_local("myapp", project)
    catalog.set_env("myapp", "prod", "TOKEN", "abc")
    env_path = catalog.render_env_file("myapp", "prod")

    assert service.source_type == "local"
    assert env_path == tmp_path / "runtime" / "services" / "myapp" / "env" / "prod.env"
    assert env_path.read_text() == "TOKEN=abc\n"


def test_catalog_deploys_local_service_through_engine_dry_run(tmp_path: Path):
    project = _project(tmp_path / "project")
    state = StateStore(tmp_path / "state.db")
    catalog = ServiceCatalog(state, runtime_dir=tmp_path / "runtime")
    catalog.add_local("myapp", project)
    catalog.set_env("myapp", "dev", "GREETING", "hello world")
    engine = DeploymentEngine(state)

    result = catalog.deploy("myapp", engine, environment="dev", ref="main", dry_run=True)

    assert result.status == "success"
    assert result.override_path == tmp_path / "runtime" / "services" / "myapp" / "overrides" / "dev.override.yml"
    assert "env_file" in result.override_path.read_text()
    assert (tmp_path / "runtime" / "services" / "myapp" / "env" / "dev.env").read_text() == 'GREETING="hello world"\n'
    env = state.require_environment("myapp", "dev")
    assert env.current_ref == "main"
    assert env.last_deployment_id == result.deployment_id


def test_catalog_history_includes_environment_summary(tmp_path: Path):
    project = _project(tmp_path / "project")
    state = StateStore(tmp_path / "state.db")
    catalog = ServiceCatalog(state, runtime_dir=tmp_path / "runtime")
    catalog.add_local("myapp", project)
    engine = DeploymentEngine(state)
    result = catalog.deploy("myapp", engine, environment="prod", ref="main", dry_run=True)

    history = catalog.history("myapp", environment="prod")

    assert history.service.name == "myapp"
    assert history.environments[0].current_ref == "main"
    assert history.environments[0].last_deployment_id == result.deployment_id
    assert history.records[0].action == "deploy"


def test_render_env_quotes_unsafe_values():
    assert render_env({"A": "plain", "B": "has space", "C": ""}) == 'A=plain\nB="has space"\nC=""\n'


def test_catalog_runtime_commands_local_service(tmp_path: Path):
    project = _project(tmp_path / "project")
    state = StateStore(tmp_path / "state.db")
    catalog = ServiceCatalog(state, runtime_dir=tmp_path / "runtime")
    catalog.add_local("myapp", project)

    class Runner:
        def run(self, args, cwd):
            if args[-1] == "ps":
                return CommandResult(tuple(args), 0, "NAME STATUS\n")
            if args[-3:] == ["logs", "--tail", "25"]:
                return CommandResult(tuple(args), 0, "log line\n")
            if args[-1] == "down":
                return CommandResult(tuple(args), 0, "removed\n")
            if args[-1] == "restart":
                return CommandResult(tuple(args), 0, "restarted\n")
            return CommandResult(tuple(args), 0, "stopped\n")

    engine = DeploymentEngine(state, runner=Runner())

    stop = catalog.stop("myapp", engine, environment="prod")
    down = catalog.down("myapp", engine, environment="prod")
    restart = catalog.restart("myapp", engine, environment="prod")
    status = catalog.status("myapp", engine, environment="prod")
    logs = catalog.logs("myapp", engine, environment="prod", tail=25)

    assert stop.status == "success"
    assert "stopped" in stop.log
    assert down.status == "success"
    assert "removed" in down.log
    assert restart.status == "success"
    assert "restarted" in restart.log
    assert status.log == "NAME STATUS\n"
    assert logs.log == "log line\n"


def test_catalog_git_source_uses_runner_for_clone_refs_and_checkout(tmp_path: Path):
    class GitRunner:
        def __init__(self):
            self.commands = []

        def run(self, args, cwd):
            self.commands.append(tuple(args))
            if args[:2] == ["git", "clone"]:
                repo = Path(args[3])
                _project(repo)
                (repo / ".git").mkdir()
                return CommandResult(tuple(args), 0, "cloned\n")
            if args[:2] == ["git", "ls-remote"]:
                return CommandResult(tuple(args), 0, "abc\trefs/heads/main\n")
            if args[:3] == ["git", "branch", "--show-current"]:
                return CommandResult(tuple(args), 0, "main\n")
            if args[:2] == ["git", "rev-parse"]:
                return CommandResult(tuple(args), 0, "abc123\n")
            return CommandResult(tuple(args), 0, "")

    runner = GitRunner()
    state = StateStore(tmp_path / "state.db")
    catalog = ServiceCatalog(state, runtime_dir=tmp_path / "runtime", runner=runner)
    engine = DeploymentEngine(state)

    service = catalog.add_git("myapp", "git@example.com/myapp.git", default_branch="main")
    refs = catalog.refs("myapp")
    status = catalog.source_status("myapp")
    result = catalog.deploy("myapp", engine, environment="prod", dry_run=True)

    assert service.source_type == "git"
    assert "refs/heads/main" in refs
    assert status.available is True
    assert status.current_ref == "main"
    assert status.current_commit == "abc123"
    assert result.status == "success"
    assert state.require_environment("myapp", "prod").current_commit == "abc123"
    assert ("git", "fetch", "--all", "--tags") in runner.commands


def test_catalog_rejects_duplicate_service_with_clear_error(tmp_path: Path):
    project = _project(tmp_path / "project")
    catalog = ServiceCatalog(StateStore(tmp_path / "state.db"), runtime_dir=tmp_path / "runtime")
    catalog.add_local("myapp", project)

    with pytest.raises(CatalogError, match="Service already exists: myapp"):
        catalog.add_local("myapp", project)


def test_catalog_git_source_with_real_local_bare_repository(tmp_path: Path):
    source = _project(tmp_path / "source")
    _git(source, "init")
    _git(source, "config", "user.email", "test@example.com")
    _git(source, "config", "user.name", "Test User")
    _git(source, "add", ".")
    _git(source, "commit", "-m", "initial")
    first_commit = _git(source, "rev-parse", "HEAD")
    default_branch = _git(source, "branch", "--show-current")
    _git(source, "tag", "v1")
    bare = tmp_path / "repo.git"
    _git(tmp_path, "clone", "--bare", str(source), str(bare))

    state = StateStore(tmp_path / "state.db")
    catalog = ServiceCatalog(state, runtime_dir=tmp_path / "runtime")
    service = catalog.add_git("myapp", str(bare), default_branch=default_branch)
    refs = catalog.refs("myapp")
    result = catalog.deploy("myapp", DeploymentEngine(state), environment="prod", ref="v1", dry_run=True)

    assert service.source_type == "git"
    assert f"refs/heads/{default_branch}" in refs
    assert "refs/tags/v1" in refs
    assert result.status == "success"
    env = state.require_environment("myapp", "prod")
    assert env.current_ref == "v1"
    assert env.current_commit == first_commit


def _git(cwd: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return process.stdout.strip()

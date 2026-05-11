from pathlib import Path
import subprocess

import pytest

from deployer.catalog import CatalogError, ServiceCatalog, render_env
from deployer.errors import CommandError
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
    catalog.add_environment("myapp", "prod")
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
    catalog.add_environment("myapp", "dev")
    catalog.set_env("myapp", "dev", "GREETING", "hello world")
    engine = DeploymentEngine(state)

    result = catalog.deploy("myapp", engine, environment="dev", ref="main", dry_run=True)

    assert result.status == "success"
    assert result.override_path == tmp_path / "runtime" / "services" / "myapp" / "overrides" / "dev.override.yml"
    assert "--env-file" in result.log
    assert "env_file" in result.override_path.read_text()
    assert "environment:\n      GREETING: hello world" in result.override_path.read_text()
    assert (tmp_path / "runtime" / "services" / "myapp" / "env" / "dev.env").read_text() == 'GREETING="hello world"\n'
    env = state.require_environment("myapp", "dev")
    assert env.current_ref == "main"
    assert env.last_deployment_id == result.deployment_id


def test_catalog_history_includes_environment_summary(tmp_path: Path):
    project = _project(tmp_path / "project")
    state = StateStore(tmp_path / "state.db")
    catalog = ServiceCatalog(state, runtime_dir=tmp_path / "runtime")
    catalog.add_local("myapp", project)
    catalog.add_environment("myapp", "prod")
    engine = DeploymentEngine(state)
    result = catalog.deploy("myapp", engine, environment="prod", ref="main", dry_run=True)

    history = catalog.history("myapp", environment="prod")

    assert history.service.name == "myapp"
    assert history.environments[0].current_ref == "main"
    assert history.environments[0].last_deployment_id == result.deployment_id
    assert history.records[0].action == "deploy"


def test_catalog_deploys_dynamic_runtime_target_with_url_prefix(tmp_path: Path):
    project = _project(tmp_path / "project")
    state = StateStore(tmp_path / "state.db")
    catalog = ServiceCatalog(state, runtime_dir=tmp_path / "runtime")
    catalog.add_local("myapp", project)
    stage_profile = catalog.add_environment_profile(
        "stage",
        url_prefix="rc",
        deploy_mode="webhook_auto",
        deploy_source="tag",
        deploy_pattern="^v.+-rc[0-9]+$",
        deploy_pattern_type="regex",
    )
    stage = catalog.add_environment(
        "myapp",
        "stage",
    )
    engine = DeploymentEngine(state)

    result = catalog.deploy("myapp", engine, environment="stage", ref="v1-rc1", dry_run=True)

    assert stage_profile.deploy_mode == "webhook_auto"
    assert stage.deploy_mode == "webhook_auto"
    assert result.status == "success"
    assert result.override_path == tmp_path / "runtime" / "services" / "myapp" / "overrides" / "stage.override.yml"
    assert "Host(`myapp.rc.busypage.ru`)" in result.override_path.read_text()
    env = state.require_environment("myapp", "stage")
    assert env.current_ref == "v1-rc1"
    assert env.last_deployment_id == result.deployment_id


def test_catalog_validates_runtime_target_policy(tmp_path: Path):
    project = _project(tmp_path / "project")
    state = StateStore(tmp_path / "state.db")
    catalog = ServiceCatalog(state, runtime_dir=tmp_path / "runtime")
    catalog.add_local("myapp", project)

    with pytest.raises(CatalogError, match="Deploy source must be branch or tag"):
        catalog.add_environment_profile("broken", deploy_mode="webhook_auto")

    with pytest.raises(CatalogError, match="Invalid deploy pattern regex"):
        catalog.add_environment_profile(
            "broken",
            deploy_mode="webhook_auto",
            deploy_source="branch",
            deploy_pattern="[",
            deploy_pattern_type="regex",
        )


def test_render_env_quotes_unsafe_values():
    assert render_env({"A": "plain", "B": "has space", "C": ""}) == 'A=plain\nB="has space"\nC=""\n'


def test_catalog_runtime_commands_local_service(tmp_path: Path):
    project = _project(tmp_path / "project")
    state = StateStore(tmp_path / "state.db")
    catalog = ServiceCatalog(state, runtime_dir=tmp_path / "runtime")
    catalog.add_local("myapp", project)
    catalog.add_environment("myapp", "prod")

    class Runner:
        def run(self, args, cwd, env=None):
            if args[-3:] == ["ps", "--format", "json"]:
                return CommandResult(tuple(args), 0, '[{"Name":"myapp","Service":"app","State":"running","Health":"healthy"}]\n')
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
    assert '"Health":"healthy"' in status.log
    assert logs.log == "log line\n"


def test_catalog_git_source_uses_runner_for_clone_refs_and_checkout(tmp_path: Path):
    class GitRunner:
        def __init__(self):
            self.commands = []

        def run(self, args, cwd, env=None):
            self.commands.append(tuple(args))
            if args[:2] == ["git", "clone"]:
                repo = Path(args[3])
                _project(repo)
                (repo / ".git").mkdir()
                return CommandResult(tuple(args), 0, "cloned\n")
            if args[:2] == ["git", "ls-remote"]:
                return CommandResult(tuple(args), 0, "abc\trefs/heads/main\n")
            if args[:3] == ["git", "show-ref", "--verify"]:
                if args[3] == "refs/remotes/origin/main":
                    return CommandResult(tuple(args), 0, "abc refs/remotes/origin/main\n")
                raise CommandError("missing ref", 1, "")
            if args[:3] == ["git", "branch", "--show-current"]:
                return CommandResult(tuple(args), 0, "main\n")
            if args[:2] == ["git", "rev-parse"]:
                return CommandResult(tuple(args), 0, "abc123\n")
            if args[:4] == ["git", "checkout", "-B", "main"]:
                return CommandResult(tuple(args), 0, "reset branch\n")
            return CommandResult(tuple(args), 0, "")

    runner = GitRunner()
    state = StateStore(tmp_path / "state.db")
    catalog = ServiceCatalog(state, runtime_dir=tmp_path / "runtime", runner=runner)
    engine = DeploymentEngine(state)

    service = catalog.add_git("myapp", "git@example.com/myapp.git", default_branch="main")
    catalog.add_environment("myapp", "prod")
    refs = catalog.refs("myapp")
    status = catalog.source_status("myapp")
    result = catalog.deploy("myapp", engine, environment="prod", dry_run=True)

    assert service.source_type == "git"
    assert "refs/heads/main" in refs
    assert status.available is True
    assert status.current_ref == "main"
    assert status.current_commit == "abc123"
    assert result.status == "success"
    assert "git fetch --all --tags" in result.log
    assert "git checkout main" in result.log
    assert "git rev-parse HEAD -> abc123" in result.log
    assert state.require_environment("myapp", "prod").current_commit == "abc123"
    assert ("git", "fetch", "--all", "--tags") in runner.commands
    assert ("git", "checkout", "-B", "main", "--track", "origin/main") in runner.commands


def test_catalog_records_checked_out_source_state_when_deploy_fails(tmp_path: Path):
    class GitRunner:
        def run(self, args, cwd, env=None):
            if args[:2] == ["git", "clone"]:
                repo = Path(args[3])
                _project(repo)
                (repo / ".git").mkdir()
                return CommandResult(tuple(args), 0, "cloned\n")
            if args[:3] == ["git", "fetch", "--all"]:
                return CommandResult(tuple(args), 0, "fetched\n")
            if args[:3] == ["git", "show-ref", "--verify"]:
                return CommandResult(tuple(args), 0, "abc refs/remotes/origin/main\n")
            if args[:4] == ["git", "checkout", "-B", "main"]:
                return CommandResult(tuple(args), 0, "reset branch\n")
            if args[:3] == ["git", "branch", "--show-current"]:
                return CommandResult(tuple(args), 0, "main\n")
            if args[:2] == ["git", "rev-parse"]:
                return CommandResult(tuple(args), 0, "abc123\n")
            return CommandResult(tuple(args), 0, "")

    class FailingRunner:
        def run(self, args, cwd, env=None):
            raise CommandError("failed", 1, "compose failed")

    state = StateStore(tmp_path / "state.db")
    catalog = ServiceCatalog(state, runtime_dir=tmp_path / "runtime", runner=GitRunner())
    catalog.add_git("myapp", "git@example.com/myapp.git", default_branch="main")
    catalog.add_environment("myapp", "prod")

    result = catalog.deploy("myapp", DeploymentEngine(state, runner=FailingRunner()), environment="prod")

    env = state.require_environment("myapp", "prod")
    assert result.status == "failed"
    assert env.current_ref == "main"
    assert env.current_commit == "abc123"
    assert env.last_deployment_id is None


def test_catalog_checkout_prefers_remote_branch_head_when_local_branch_is_stale(tmp_path: Path):
    class GitRunner:
        def __init__(self):
            self.commands = []

        def run(self, args, cwd, env=None):
            self.commands.append(tuple(args))
            if args[:2] == ["git", "clone"]:
                repo = Path(args[3])
                _project(repo)
                (repo / ".git").mkdir()
                return CommandResult(tuple(args), 0, "cloned\n")
            if args[:3] == ["git", "show-ref", "--verify"]:
                if args[3] == "refs/remotes/origin/dev":
                    return CommandResult(tuple(args), 0, "be1f943 refs/remotes/origin/dev\n")
                raise CommandError("missing ref", 1, "")
            if args[:4] == ["git", "checkout", "-B", "dev"]:
                return CommandResult(tuple(args), 0, "branch reset to origin/dev\n")
            if args[:3] == ["git", "branch", "--show-current"]:
                return CommandResult(tuple(args), 0, "dev\n")
            if args[:2] == ["git", "rev-parse"]:
                return CommandResult(tuple(args), 0, "be1f94315e20d335c276c6e2e9fb910bbc11344c\n")
            return CommandResult(tuple(args), 0, "")

    runner = GitRunner()
    state = StateStore(tmp_path / "state.db")
    catalog = ServiceCatalog(state, runtime_dir=tmp_path / "runtime", runner=runner)
    engine = DeploymentEngine(state)

    catalog.add_git("myapp", "git@example.com/myapp.git", default_branch="main")
    catalog.add_environment("myapp", "dev")
    result = catalog.deploy("myapp", engine, environment="dev", ref="dev", dry_run=True)

    assert result.status == "success"
    assert ("git", "checkout", "-B", "dev", "--track", "origin/dev") in runner.commands
    assert state.require_environment("myapp", "dev").current_commit == "be1f94315e20d335c276c6e2e9fb910bbc11344c"


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
    catalog.add_environment("myapp", "prod")
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

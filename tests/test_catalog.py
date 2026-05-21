from pathlib import Path
import subprocess

import pytest

from deployer.catalog import CatalogError, ServiceCatalog, render_env
from deployer.errors import CommandError
from deployer.engine import DeploymentEngine
from deployer.project_spec import render_project_override
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


def test_catalog_adds_environment_project_without_manifest(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    catalog = ServiceCatalog(StateStore(tmp_path / "state.db"), runtime_dir=tmp_path / "runtime")

    project = catalog.add_project_local(
        "dev",
        "tasktrack",
        source,
        default_ref="dev",
        deploy_mode="webhook_auto",
        deploy_source="branch",
        deploy_pattern="dev",
        deploy_pattern_type="exact",
    )
    catalog.add_component(
        "dev",
        "tasktrack",
        "backend",
        mode="build",
        build_context="backend",
        dockerfile="Dockerfile",
        port=8000,
    )
    catalog.add_endpoint(
        "dev",
        "tasktrack",
        "api",
        "backend",
        8000,
        subdomain="api.tasktrack",
        auth="sso",
        healthcheck_path="/api/v1/health",
    )
    catalog.add_dependency(
        "dev",
        "tasktrack",
        "postgres",
        "postgres",
        "postgres-main/tasktrack_dev",
        outputs={"DATABASE_URL": "postgresql://tasktrack_dev@example/tasktrack_dev"},
    )
    catalog.set_project_env("dev", "tasktrack", "APP_ENV", "dev")
    env_path = catalog.render_project_env_file("dev", "tasktrack")
    config = catalog.project_config("dev", "tasktrack")

    assert project.environment == "dev"
    assert project.name == "tasktrack"
    assert config.project.env_vars == {"APP_ENV": "dev"}
    assert config.components[0].name == "backend"
    assert config.endpoints[0].subdomain == "api.tasktrack"
    assert config.dependencies[0].target == "postgres-main/tasktrack_dev"
    assert env_path == tmp_path / "runtime" / "environments" / "dev" / "projects" / "tasktrack" / "env" / "project.env"
    assert env_path.read_text() == "APP_ENV=dev\nDATABASE_URL=postgresql://tasktrack_dev@example/tasktrack_dev\n"


def test_catalog_deploys_environment_project_without_manifest(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "docker-compose.yml").write_text(
        """
services:
  app:
    image: nginx:alpine
"""
    )
    state = StateStore(tmp_path / "state.db")
    catalog = ServiceCatalog(state, runtime_dir=tmp_path / "runtime")
    catalog.add_project_local("dev", "tasktrack", source, default_ref="dev")
    catalog.add_component("dev", "tasktrack", "web", mode="compose", compose_service="app", port=8080)
    catalog.add_endpoint("dev", "tasktrack", "web", "web", 8080, subdomain="tasktrack", auth="sso")
    catalog.add_dependency(
        "dev",
        "tasktrack",
        "postgres",
        "postgres",
        "postgres-main/tasktrack_dev",
        outputs={"DATABASE_URL": "postgresql://example/tasktrack_dev"},
    )
    catalog.set_project_env("dev", "tasktrack", "APP_ENV", "dev")

    result = catalog.deploy_project("dev", "tasktrack", DeploymentEngine(state), dry_run=True)

    override_path = tmp_path / "runtime" / "environments" / "dev" / "projects" / "tasktrack" / "overrides" / "dev.override.yml"
    env_path = tmp_path / "runtime" / "environments" / "dev" / "projects" / "tasktrack" / "env" / "project.env"
    override = override_path.read_text()
    assert result.status == "success"
    assert result.override_path == override_path
    assert "-p dev-tasktrack" in result.log
    assert "deployer.yml" not in result.log
    assert "Host(`tasktrack.dev.busypage.ru`)" in override
    assert "sso-errors@file,sso-auth@file" in override
    assert f"env_file: {env_path}" in override
    assert "APP_ENV=dev\nDATABASE_URL=postgresql://example/tasktrack_dev\n" == env_path.read_text()
    project = state.require_project("dev", "tasktrack")
    assert project.current_ref == "dev"
    assert project.last_deployment_id == result.deployment_id


def test_catalog_resource_binding_generates_env_and_volume_mount(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "docker-compose.yml").write_text("services:\n  app:\n    image: nginx:alpine\n")
    state = StateStore(tmp_path / "state.db")
    catalog = ServiceCatalog(state, runtime_dir=tmp_path / "runtime")
    catalog.add_project_local("dev", "tasktrack", source)
    catalog.add_component("dev", "tasktrack", "backend", mode="compose", compose_service="app")

    catalog.add_environment_resource(
        "dev",
        "postgres-main",
        "postgres",
        config={"host": "postgres", "port": "5432"},
    )
    catalog.bind_project_resource(
        "dev",
        "tasktrack",
        "app-db",
        "postgres-main",
        component="backend",
        config={"database": "tasktrack_dev", "username": "tasktrack_dev", "password": "secret"},
        mounts=({"source": "dev_tasktrack_uploads", "target": "/app/uploads"},),
    )

    env_path = catalog.render_project_env_file("dev", "tasktrack")
    spec = catalog.project_spec("dev", "tasktrack")
    override = render_project_override(spec)

    assert "DATABASE_URL=postgresql://tasktrack_dev:secret@postgres:5432/tasktrack_dev\n" == env_path.read_text()
    assert "dev_tasktrack_uploads:/app/uploads" in override
    assert "volumes:" in override


def test_catalog_managed_postgres_binding_plan_and_apply(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "docker-compose.yml").write_text("services:\n  app:\n    image: nginx:alpine\n")
    state = StateStore(tmp_path / "state.db")

    class Runner:
        def __init__(self):
            self.commands = []

        def run(self, args, cwd, env=None):
            self.commands.append(tuple(args))
            return CommandResult(tuple(args), 0, "ok\n")

    runner = Runner()
    catalog = ServiceCatalog(state, runtime_dir=tmp_path / "runtime", runner=runner)
    catalog.add_project_local("dev", "tasktrack", source)
    catalog.add_component("dev", "tasktrack", "backend", mode="compose", compose_service="app")
    catalog.add_environment_resource(
        "dev",
        "postgres-main",
        "postgres",
        config={"host": "postgres", "port": "5432", "container": "postgres-1", "admin_user": "postgres"},
    )
    catalog.bind_project_resource("dev", "tasktrack", "app-db", "postgres-main", component="backend")

    plan = catalog.plan_project_resource_binding("dev", "tasktrack", "app-db")

    assert plan.config["database"] == "dev_tasktrack"
    assert plan.config["username"] == "dev_tasktrack"
    assert "Password will be generated" in plan.warnings[0]
    assert "ensure database dev_tasktrack exists" in plan.steps

    applied, log = catalog.apply_project_resource_binding("dev", "tasktrack", "app-db")
    binding = state.require_project_resource_binding("dev", "tasktrack", "app-db")

    assert applied.config["password"]
    assert binding.config["password"] == applied.config["password"]
    assert binding.outputs["DATABASE_URL"].startswith("postgresql://dev_tasktrack:")
    assert binding.outputs["DATABASE_URL"].endswith("@postgres:5432/dev_tasktrack")
    assert len(runner.commands) == 3
    assert runner.commands[0][:4] == ("docker", "exec", "postgres-1", "psql")
    assert "updated binding dev/tasktrack/app-db" in log
    assert catalog.render_project_env_file("dev", "tasktrack").read_text() == (
        f"DATABASE_URL={binding.outputs['DATABASE_URL']}\n"
    )


def test_catalog_managed_postgres_apply_dry_run_does_not_update_binding(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "docker-compose.yml").write_text("services:\n  app:\n    image: nginx:alpine\n")
    state = StateStore(tmp_path / "state.db")
    catalog = ServiceCatalog(state, runtime_dir=tmp_path / "runtime")
    catalog.add_project_local("dev", "tasktrack", source)
    catalog.add_component("dev", "tasktrack", "backend", mode="compose", compose_service="app")
    catalog.add_environment_resource("dev", "postgres-main", "postgres", config={"host": "postgres"})
    catalog.bind_project_resource("dev", "tasktrack", "app-db", "postgres-main", component="backend")

    plan, log = catalog.apply_project_resource_binding("dev", "tasktrack", "app-db", dry_run=True)
    binding = state.require_project_resource_binding("dev", "tasktrack", "app-db")

    assert "password" not in plan.config
    assert "Dry run command:" in log
    assert "PASSWORD '***'" in log
    assert binding.config == {}
    assert binding.outputs == {}


def test_catalog_allows_same_project_name_in_different_environments(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    catalog = ServiceCatalog(StateStore(tmp_path / "state.db"), runtime_dir=tmp_path / "runtime")

    catalog.add_project_local("dev", "tasktrack", source, default_ref="dev")
    catalog.add_project_local("prod", "tasktrack", source, default_ref="main")
    catalog.set_project_env("dev", "tasktrack", "APP_ENV", "dev")
    catalog.set_project_env("prod", "tasktrack", "APP_ENV", "prod")

    assert catalog.get_project("dev", "tasktrack").default_ref == "dev"
    assert catalog.get_project("prod", "tasktrack").default_ref == "main"
    assert catalog.get_project("dev", "tasktrack").env_vars == {"APP_ENV": "dev"}
    assert catalog.get_project("prod", "tasktrack").env_vars == {"APP_ENV": "prod"}


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

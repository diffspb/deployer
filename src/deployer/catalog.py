from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from deployer.engine import CommandResult, DeployResult, DeploymentEngine
from deployer.errors import DeployerError
from deployer.manifest import load_manifest
from deployer.runner import CommandRunner
from deployer.state import EnvironmentRecord, ServiceRecord, StateStore


DEFAULT_RUNTIME_DIR = Path("/var/lib/deployer")
VALID_ENVIRONMENTS = {"prod", "dev"}
_SERVICE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class ServiceRuntime:
    service: ServiceRecord
    environment: EnvironmentRecord
    project_dir: Path
    override_dir: Path
    env_file: Path
    ref: str | None
    commit_hash: str | None


class CatalogError(DeployerError):
    pass


class ServiceCatalog:
    def __init__(
        self,
        state: StateStore,
        runtime_dir: Path = DEFAULT_RUNTIME_DIR,
        runner: CommandRunner | None = None,
    ):
        self.state = state
        self.runtime_dir = runtime_dir
        self.runner = runner or CommandRunner()

    def add_local(self, name: str, path: Path) -> ServiceRecord:
        _validate_service_name(name)
        project_dir = path.resolve()
        if not project_dir.exists():
            raise CatalogError(f"Local source does not exist: {project_dir}")
        load_manifest(project_dir)
        try:
            return self.state.add_service(name, "local", str(project_dir))
        except Exception as exc:
            raise CatalogError(f"Cannot add service {name}: {exc}") from exc

    def add_git(self, name: str, git_url: str, default_branch: str | None = None) -> ServiceRecord:
        _validate_service_name(name)
        service_dir = self.service_dir(name)
        repo_dir = service_dir / "repo"
        if repo_dir.exists():
            raise CatalogError(f"Repository already exists: {repo_dir}")
        service_dir.mkdir(parents=True, exist_ok=True)
        self.runner.run(["git", "clone", git_url, str(repo_dir)], cwd=service_dir)
        if default_branch:
            self.runner.run(["git", "checkout", default_branch], cwd=repo_dir)
        load_manifest(repo_dir)
        try:
            return self.state.add_service(name, "git", str(repo_dir), source_url=git_url, default_branch=default_branch)
        except Exception as exc:
            raise CatalogError(f"Cannot add service {name}: {exc}") from exc

    def list_services(self) -> list[ServiceRecord]:
        return self.state.list_services()

    def get_service(self, name: str) -> ServiceRecord:
        try:
            return self.state.require_service(name)
        except KeyError as exc:
            raise CatalogError(f"Unknown service: {name}") from exc

    def remove_service(self, name: str, delete_files: bool = False) -> bool:
        removed = self.state.remove_service(name)
        if delete_files:
            shutil.rmtree(self.service_dir(name), ignore_errors=True)
        return removed

    def refs(self, name: str) -> str:
        service = self.get_service(name)
        if service.source_type != "git":
            raise CatalogError(f"Service {name} is not git-backed")
        if service.source_url:
            result = self.runner.run(["git", "ls-remote", "--heads", "--tags", service.source_url], cwd=Path(service.source_path))
        else:
            result = self.runner.run(["git", "show-ref", "--heads", "--tags"], cwd=Path(service.source_path))
        return result.output

    def set_env(self, service_name: str, environment: str, key: str, value: str) -> EnvironmentRecord:
        _validate_environment(environment)
        _validate_env_key(key)
        if "\n" in value:
            raise CatalogError("Environment values must be single-line")
        return self.state.set_env_var(service_name, environment, key, value)

    def unset_env(self, service_name: str, environment: str, key: str) -> EnvironmentRecord:
        _validate_environment(environment)
        _validate_env_key(key)
        return self.state.unset_env_var(service_name, environment, key)

    def get_environment(self, service_name: str, environment: str) -> EnvironmentRecord:
        _validate_environment(environment)
        try:
            return self.state.require_environment(service_name, environment)
        except KeyError as exc:
            raise CatalogError(f"Unknown service environment: {service_name}/{environment}") from exc

    def render_env_file(self, service_name: str, environment: str) -> Path:
        runtime = self.resolve_runtime(service_name, environment)
        runtime.env_file.parent.mkdir(parents=True, exist_ok=True)
        runtime.env_file.write_text(render_env(runtime.environment.env_vars))
        return runtime.env_file

    def deploy(
        self,
        service_name: str,
        engine: DeploymentEngine,
        environment: str = "prod",
        ref: str | None = None,
        version: str | None = None,
        dry_run: bool = False,
    ) -> DeployResult:
        runtime = self.prepare_runtime(service_name, environment, ref)
        result = engine.deploy(
            runtime.project_dir,
            version=version or runtime.ref,
            dry_run=dry_run,
            environment=environment,
            override_dir=runtime.override_dir,
            env_file=str(runtime.env_file),
        )
        if result.status == "success":
            self.state.update_environment_version(
                service_name,
                environment,
                result.deployment_id,
                version or runtime.ref,
                runtime.ref,
                runtime.commit_hash,
            )
        return result

    def stop(
        self,
        service_name: str,
        engine: DeploymentEngine,
        environment: str = "prod",
        dry_run: bool = False,
    ) -> DeployResult:
        runtime = self.resolve_runtime(service_name, environment)
        self.render_env_file(service_name, environment)
        return engine.stop(
            runtime.project_dir,
            dry_run=dry_run,
            environment=environment,
            override_dir=runtime.override_dir,
            env_file=str(runtime.env_file),
        )

    def status(self, service_name: str, engine: DeploymentEngine, environment: str = "prod") -> CommandResult:
        runtime = self.resolve_runtime(service_name, environment)
        self.render_env_file(service_name, environment)
        return engine.status(
            runtime.project_dir,
            environment=environment,
            override_dir=runtime.override_dir,
            env_file=str(runtime.env_file),
        )

    def prepare_runtime(self, service_name: str, environment: str, ref: str | None = None) -> ServiceRuntime:
        runtime = self.resolve_runtime(service_name, environment)
        commit_hash = None
        actual_ref = ref or runtime.service.default_branch
        if runtime.service.source_type == "git":
            repo_dir = runtime.project_dir
            self.runner.run(["git", "fetch", "--all", "--tags"], cwd=repo_dir)
            if actual_ref:
                self.runner.run(["git", "checkout", actual_ref], cwd=repo_dir)
            commit_hash = self.runner.run(["git", "rev-parse", "HEAD"], cwd=repo_dir).output.strip()
        elif _is_git_repo(runtime.project_dir):
            commit_hash = self.runner.run(["git", "rev-parse", "HEAD"], cwd=runtime.project_dir).output.strip()
        self.render_env_file(service_name, environment)
        return ServiceRuntime(
            runtime.service,
            runtime.environment,
            runtime.project_dir,
            runtime.override_dir,
            runtime.env_file,
            actual_ref,
            commit_hash,
        )

    def resolve_runtime(self, service_name: str, environment: str) -> ServiceRuntime:
        _validate_environment(environment)
        service = self.get_service(service_name)
        env = self.get_environment(service_name, environment)
        service_dir = self.service_dir(service_name)
        return ServiceRuntime(
            service=service,
            environment=env,
            project_dir=Path(service.source_path),
            override_dir=service_dir / "overrides",
            env_file=service_dir / "env" / f"{environment}.env",
            ref=None,
            commit_hash=None,
        )

    def service_dir(self, name: str) -> Path:
        return self.runtime_dir / "services" / name


def render_env(env_vars: dict[str, str]) -> str:
    return "".join(f"{key}={_env_value(value)}\n" for key, value in sorted(env_vars.items()))


def _env_value(value: str) -> str:
    if value == "" or any(char.isspace() for char in value) or "#" in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _validate_service_name(name: str) -> None:
    if not _SERVICE_NAME_RE.fullmatch(name):
        raise CatalogError("Service name must contain lowercase letters, digits, and dashes")


def _validate_environment(environment: str) -> None:
    if environment not in VALID_ENVIRONMENTS:
        raise CatalogError("Environment must be prod or dev")


def _validate_env_key(key: str) -> None:
    if not _ENV_KEY_RE.fullmatch(key):
        raise CatalogError("Invalid environment variable name")


def _is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()

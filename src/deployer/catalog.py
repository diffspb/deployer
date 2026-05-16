from __future__ import annotations

import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from deployer.engine import CommandResult, DeployResult, DeploymentEngine
from deployer.errors import CommandError, DeployerError
from deployer.manifest import load_manifest
from deployer.project_spec import build_project_spec
from deployer.runner import CommandRunner
from deployer.state import (
    DeploymentRecord,
    EnvironmentProfileRecord,
    EnvironmentProjectRecord,
    EnvironmentRecord,
    ProjectComponentRecord,
    ProjectDependencyRecord,
    ProjectEndpointRecord,
    ServiceRecord,
    StateStore,
)


DEFAULT_RUNTIME_DIR = Path("/var/lib/deployer")
_SERVICE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_TARGET_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_URL_PREFIX_RE = re.compile(r"^$|^[a-z0-9][a-z0-9-]{0,62}$")
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DEPLOY_MODES = {"manual", "webhook_auto", "webhook_gated"}
DEPLOY_SOURCES = {"branch", "tag"}
DEPLOY_PATTERN_TYPES = {"exact", "regex"}


@dataclass(frozen=True)
class ServiceRuntime:
    service: ServiceRecord
    environment: EnvironmentRecord
    project_dir: Path
    override_dir: Path
    env_file: Path
    ref: str | None
    commit_hash: str | None
    prepare_log: str


@dataclass(frozen=True)
class EnvironmentProjectRuntime:
    project: EnvironmentProjectRecord
    source_dir: Path
    override_dir: Path
    env_file: Path
    ref: str | None
    commit_hash: str | None
    prepare_log: str


@dataclass(frozen=True)
class ServiceHistory:
    service: ServiceRecord
    environments: tuple[EnvironmentRecord, ...]
    records: tuple[DeploymentRecord, ...]


@dataclass(frozen=True)
class SourceStatus:
    available: bool
    path_exists: bool
    is_git_repo: bool
    current_ref: str | None
    current_commit: str | None
    error: str | None = None


@dataclass(frozen=True)
class EnvironmentProjectConfig:
    project: EnvironmentProjectRecord
    components: tuple[ProjectComponentRecord, ...]
    endpoints: tuple[ProjectEndpointRecord, ...]
    dependencies: tuple[ProjectDependencyRecord, ...]


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
        self._ensure_service_absent(name)
        project_dir = path.resolve()
        if not project_dir.exists():
            raise CatalogError(f"Local source does not exist: {project_dir}")
        load_manifest(project_dir)
        try:
            return self.state.add_service(name, "local", str(project_dir))
        except sqlite3.IntegrityError as exc:
            raise CatalogError(f"Service already exists: {name}") from exc
        except ValueError as exc:
            raise CatalogError(f"Cannot add service {name}: {exc}") from exc

    def add_project_local(
        self,
        environment: str,
        name: str,
        path: Path,
        default_ref: str | None = None,
        compose_files: tuple[str, ...] = ("docker-compose.yml",),
        deploy_mode: str = "manual",
        deploy_source: str | None = None,
        deploy_pattern: str | None = None,
        deploy_pattern_type: str | None = None,
    ) -> EnvironmentProjectRecord:
        _validate_target_name(environment)
        _validate_service_name(name)
        _validate_compose_files(compose_files)
        _validate_deploy_policy(deploy_mode, deploy_source, deploy_pattern, deploy_pattern_type)
        source_path = path.resolve()
        if not source_path.exists():
            raise CatalogError(f"Local source does not exist: {source_path}")
        try:
            return self.state.add_project(
                environment,
                name,
                "local",
                str(source_path),
                default_ref=default_ref,
                compose_files=compose_files,
                deploy_mode=deploy_mode,
                deploy_source=deploy_source,
                deploy_pattern=deploy_pattern,
                deploy_pattern_type=deploy_pattern_type,
            )
        except KeyError as exc:
            raise CatalogError(f"Unknown environment: {environment}") from exc
        except sqlite3.IntegrityError as exc:
            raise CatalogError(f"Project already exists: {environment}/{name}") from exc
        except ValueError as exc:
            raise CatalogError(f"Cannot add project {environment}/{name}: {exc}") from exc

    def add_project_git(
        self,
        environment: str,
        name: str,
        git_url: str,
        default_ref: str | None = None,
        compose_files: tuple[str, ...] = ("docker-compose.yml",),
        deploy_mode: str = "manual",
        deploy_source: str | None = None,
        deploy_pattern: str | None = None,
        deploy_pattern_type: str | None = None,
    ) -> EnvironmentProjectRecord:
        _validate_target_name(environment)
        _validate_service_name(name)
        _validate_compose_files(compose_files)
        _validate_deploy_policy(deploy_mode, deploy_source, deploy_pattern, deploy_pattern_type)
        project_dir = self.project_dir(environment, name)
        repo_dir = project_dir / "repo"
        if repo_dir.exists():
            raise CatalogError(f"Repository already exists: {repo_dir}")
        project_dir.mkdir(parents=True, exist_ok=True)
        self.runner.run(["git", "clone", git_url, str(repo_dir)], cwd=project_dir)
        if default_ref:
            self.runner.run(["git", "checkout", default_ref], cwd=repo_dir)
        try:
            return self.state.add_project(
                environment,
                name,
                "git",
                str(repo_dir),
                source_url=git_url,
                default_ref=default_ref,
                compose_files=compose_files,
                deploy_mode=deploy_mode,
                deploy_source=deploy_source,
                deploy_pattern=deploy_pattern,
                deploy_pattern_type=deploy_pattern_type,
            )
        except KeyError as exc:
            raise CatalogError(f"Unknown environment: {environment}") from exc
        except sqlite3.IntegrityError as exc:
            raise CatalogError(f"Project already exists: {environment}/{name}") from exc
        except ValueError as exc:
            raise CatalogError(f"Cannot add project {environment}/{name}: {exc}") from exc

    def list_projects(self, environment: str | None = None) -> list[EnvironmentProjectRecord]:
        if environment is not None:
            _validate_target_name(environment)
        return self.state.list_projects(environment)

    def get_project(self, environment: str, name: str) -> EnvironmentProjectRecord:
        _validate_target_name(environment)
        _validate_service_name(name)
        try:
            return self.state.require_project(environment, name)
        except KeyError as exc:
            raise CatalogError(f"Unknown project: {environment}/{name}") from exc

    def remove_project(self, environment: str, name: str, delete_files: bool = False) -> bool:
        _validate_target_name(environment)
        _validate_service_name(name)
        removed = self.state.remove_project(environment, name)
        if delete_files:
            shutil.rmtree(self.project_dir(environment, name), ignore_errors=True)
        return removed

    def project_config(self, environment: str, name: str) -> EnvironmentProjectConfig:
        project = self.get_project(environment, name)
        return EnvironmentProjectConfig(
            project=project,
            components=tuple(self.state.list_components(environment, name)),
            endpoints=tuple(self.state.list_endpoints(environment, name)),
            dependencies=tuple(self.state.list_dependencies(environment, name)),
        )

    def add_component(
        self,
        environment: str,
        project: str,
        name: str,
        mode: str = "compose",
        compose_service: str | None = None,
        build_context: str | None = None,
        dockerfile: str | None = None,
        image: str | None = None,
        command: str | None = None,
        port: int | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> ProjectComponentRecord:
        _validate_project_scope(environment, project)
        _validate_component_name(name)
        _validate_component(mode, compose_service, build_context, dockerfile, image, port)
        for key, value in (env_vars or {}).items():
            _validate_env_key(key)
            if "\n" in value:
                raise CatalogError("Environment values must be single-line")
        try:
            return self.state.add_component(
                environment,
                project,
                name,
                mode=mode,
                compose_service=compose_service,
                build_context=build_context,
                dockerfile=dockerfile,
                image=image,
                command=command,
                port=port,
                env_vars=env_vars,
            )
        except KeyError as exc:
            raise CatalogError(f"Unknown project: {environment}/{project}") from exc
        except sqlite3.IntegrityError as exc:
            raise CatalogError(f"Component already exists: {environment}/{project}/{name}") from exc

    def add_endpoint(
        self,
        environment: str,
        project: str,
        name: str,
        component: str,
        port: int,
        host: str | None = None,
        subdomain: str | None = None,
        path_prefix: str | None = None,
        auth: str = "none",
        middlewares: tuple[str, ...] = (),
        healthcheck_path: str | None = None,
    ) -> ProjectEndpointRecord:
        _validate_project_scope(environment, project)
        _validate_component_name(name)
        _validate_component_name(component)
        if port <= 0:
            raise CatalogError("Endpoint port must be positive")
        if not host and not subdomain:
            raise CatalogError("Endpoint must define host or subdomain")
        if host and subdomain:
            raise CatalogError("Endpoint must not define both host and subdomain")
        if auth not in {"none", "sso"}:
            raise CatalogError("Endpoint auth must be one of: none, sso")
        if path_prefix is not None and not path_prefix.startswith("/"):
            raise CatalogError("Endpoint path prefix must start with /")
        if healthcheck_path is not None and not healthcheck_path.startswith("/"):
            raise CatalogError("Endpoint healthcheck path must start with /")
        try:
            return self.state.add_endpoint(
                environment,
                project,
                name,
                component,
                port,
                host=host,
                subdomain=subdomain,
                path_prefix=path_prefix,
                auth=auth,
                middlewares=middlewares,
                healthcheck_path=healthcheck_path,
            )
        except KeyError as exc:
            raise CatalogError(f"Unknown project component: {environment}/{project}/{component}") from exc
        except sqlite3.IntegrityError as exc:
            raise CatalogError(f"Endpoint already exists: {environment}/{project}/{name}") from exc

    def update_component(
        self,
        environment: str,
        project: str,
        name: str,
        mode: str = "compose",
        compose_service: str | None = None,
        build_context: str | None = None,
        dockerfile: str | None = None,
        image: str | None = None,
        command: str | None = None,
        port: int | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> ProjectComponentRecord:
        _validate_project_scope(environment, project)
        _validate_component_name(name)
        _validate_component(mode, compose_service, build_context, dockerfile, image, port)
        for key, value in (env_vars or {}).items():
            _validate_env_key(key)
            if "\n" in value:
                raise CatalogError("Environment values must be single-line")
        try:
            return self.state.update_component(
                environment,
                project,
                name,
                mode=mode,
                compose_service=compose_service,
                build_context=build_context,
                dockerfile=dockerfile,
                image=image,
                command=command,
                port=port,
                env_vars=env_vars,
            )
        except KeyError as exc:
            raise CatalogError(f"Unknown component: {environment}/{project}/{name}") from exc

    def delete_component(self, environment: str, project: str, name: str) -> bool:
        _validate_project_scope(environment, project)
        _validate_component_name(name)
        return self.state.delete_component(environment, project, name)

    def update_endpoint(
        self,
        environment: str,
        project: str,
        name: str,
        component: str,
        port: int,
        host: str | None = None,
        subdomain: str | None = None,
        path_prefix: str | None = None,
        auth: str = "none",
        middlewares: tuple[str, ...] = (),
        healthcheck_path: str | None = None,
    ) -> ProjectEndpointRecord:
        _validate_project_scope(environment, project)
        _validate_component_name(name)
        _validate_component_name(component)
        if port <= 0:
            raise CatalogError("Endpoint port must be positive")
        if not host and not subdomain:
            raise CatalogError("Endpoint must define host or subdomain")
        if host and subdomain:
            raise CatalogError("Endpoint must not define both host and subdomain")
        if auth not in {"none", "sso"}:
            raise CatalogError("Endpoint auth must be one of: none, sso")
        if path_prefix is not None and not path_prefix.startswith("/"):
            raise CatalogError("Endpoint path prefix must start with /")
        if healthcheck_path is not None and not healthcheck_path.startswith("/"):
            raise CatalogError("Endpoint healthcheck path must start with /")
        try:
            return self.state.update_endpoint(
                environment,
                project,
                name,
                component=component,
                port=port,
                host=host,
                subdomain=subdomain,
                path_prefix=path_prefix,
                auth=auth,
                middlewares=middlewares,
                healthcheck_path=healthcheck_path,
            )
        except KeyError as exc:
            raise CatalogError(f"Unknown endpoint or component: {environment}/{project}/{name}") from exc

    def delete_endpoint(self, environment: str, project: str, name: str) -> bool:
        _validate_project_scope(environment, project)
        _validate_component_name(name)
        return self.state.delete_endpoint(environment, project, name)

    def add_dependency(
        self,
        environment: str,
        project: str,
        name: str,
        type: str,
        target: str,
        outputs: dict[str, str] | None = None,
    ) -> ProjectDependencyRecord:
        _validate_project_scope(environment, project)
        _validate_component_name(name)
        if not type.strip():
            raise CatalogError("Dependency type must be non-empty")
        if not target.strip():
            raise CatalogError("Dependency target must be non-empty")
        for key, value in (outputs or {}).items():
            _validate_env_key(key)
            if "\n" in value:
                raise CatalogError("Dependency outputs must be single-line")
        try:
            return self.state.add_dependency(environment, project, name, type, target, outputs=outputs)
        except KeyError as exc:
            raise CatalogError(f"Unknown project: {environment}/{project}") from exc
        except sqlite3.IntegrityError as exc:
            raise CatalogError(f"Dependency already exists: {environment}/{project}/{name}") from exc

    def update_dependency(
        self,
        environment: str,
        project: str,
        name: str,
        type: str,
        target: str,
        outputs: dict[str, str] | None = None,
    ) -> ProjectDependencyRecord:
        _validate_project_scope(environment, project)
        _validate_component_name(name)
        if not type.strip():
            raise CatalogError("Dependency type must be non-empty")
        if not target.strip():
            raise CatalogError("Dependency target must be non-empty")
        for key, value in (outputs or {}).items():
            _validate_env_key(key)
            if "\n" in value:
                raise CatalogError("Dependency outputs must be single-line")
        try:
            return self.state.update_dependency(environment, project, name, type=type, target=target, outputs=outputs)
        except KeyError as exc:
            raise CatalogError(f"Unknown dependency: {environment}/{project}/{name}") from exc

    def delete_dependency(self, environment: str, project: str, name: str) -> bool:
        _validate_project_scope(environment, project)
        _validate_component_name(name)
        return self.state.delete_dependency(environment, project, name)

    def set_project_env(self, environment: str, project: str, key: str, value: str) -> EnvironmentProjectRecord:
        _validate_project_scope(environment, project)
        _validate_env_key(key)
        if "\n" in value:
            raise CatalogError("Environment values must be single-line")
        try:
            return self.state.set_project_env_var(environment, project, key, value)
        except KeyError as exc:
            raise CatalogError(f"Unknown project: {environment}/{project}") from exc

    def unset_project_env(self, environment: str, project: str, key: str) -> EnvironmentProjectRecord:
        _validate_project_scope(environment, project)
        _validate_env_key(key)
        try:
            return self.state.unset_project_env_var(environment, project, key)
        except KeyError as exc:
            raise CatalogError(f"Unknown project: {environment}/{project}") from exc

    def render_project_env_file(self, environment: str, project: str) -> Path:
        config = self.project_config(environment, project)
        env_file = self.project_dir(environment, project) / "env" / "project.env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_vars = _project_runtime_env(config)
        env_file.write_text(render_env(env_vars))
        return env_file

    def deploy_project(
        self,
        environment: str,
        project_name: str,
        engine: DeploymentEngine,
        ref: str | None = None,
        version: str | None = None,
        dry_run: bool = False,
    ) -> DeployResult:
        runtime = self.prepare_project_runtime(environment, project_name, ref)
        self.state.update_project_source_state(
            environment,
            project_name,
            version or runtime.ref,
            runtime.ref,
            runtime.commit_hash,
        )
        spec = self.project_spec(environment, project_name)
        result = engine.deploy_project(
            spec,
            version=version or runtime.ref,
            dry_run=dry_run,
            override_dir=runtime.override_dir,
            env_file=str(runtime.env_file),
        )
        merged_log = _merge_logs(runtime.prepare_log, result.log)
        result = DeployResult(
            result.deployment_id,
            result.project,
            result.environment,
            result.status,
            merged_log,
            result.override_path,
        )
        if result.status == "success":
            self.state.update_project_version(
                environment,
                project_name,
                result.deployment_id,
                version or runtime.ref,
                runtime.ref,
                runtime.commit_hash,
            )
        return result

    def stop_project(
        self,
        environment: str,
        project_name: str,
        engine: DeploymentEngine,
        dry_run: bool = False,
    ) -> DeployResult:
        runtime = self.resolve_project_runtime(environment, project_name)
        self.render_project_env_file(environment, project_name)
        spec = self.project_spec(environment, project_name)
        return engine.stop_project(spec, dry_run=dry_run, override_dir=runtime.override_dir, env_file=str(runtime.env_file))

    def down_project(
        self,
        environment: str,
        project_name: str,
        engine: DeploymentEngine,
        dry_run: bool = False,
    ) -> DeployResult:
        runtime = self.resolve_project_runtime(environment, project_name)
        self.render_project_env_file(environment, project_name)
        spec = self.project_spec(environment, project_name)
        return engine.down_project(spec, dry_run=dry_run, override_dir=runtime.override_dir, env_file=str(runtime.env_file))

    def restart_project(
        self,
        environment: str,
        project_name: str,
        engine: DeploymentEngine,
        dry_run: bool = False,
    ) -> DeployResult:
        runtime = self.resolve_project_runtime(environment, project_name)
        self.render_project_env_file(environment, project_name)
        spec = self.project_spec(environment, project_name)
        return engine.restart_project(spec, dry_run=dry_run, override_dir=runtime.override_dir, env_file=str(runtime.env_file))

    def status_project(
        self,
        environment: str,
        project_name: str,
        engine: DeploymentEngine,
    ) -> CommandResult:
        runtime = self.resolve_project_runtime(environment, project_name)
        self.render_project_env_file(environment, project_name)
        spec = self.project_spec(environment, project_name)
        return engine.status_project(spec, override_dir=runtime.override_dir, env_file=str(runtime.env_file))

    def logs_project(
        self,
        environment: str,
        project_name: str,
        engine: DeploymentEngine,
        tail: int = 200,
    ) -> CommandResult:
        runtime = self.resolve_project_runtime(environment, project_name)
        self.render_project_env_file(environment, project_name)
        spec = self.project_spec(environment, project_name)
        return engine.logs_project(spec, override_dir=runtime.override_dir, env_file=str(runtime.env_file), tail=tail)

    def project_spec(self, environment: str, project_name: str):
        config = self.project_config(environment, project_name)
        profile = self.get_environment_profile(environment)
        return build_project_spec(
            config.project,
            profile,
            config.components,
            config.endpoints,
            config.dependencies,
            env_file=str(self.project_dir(environment, project_name) / "env" / "project.env"),
        )

    def prepare_project_runtime(
        self,
        environment: str,
        project_name: str,
        ref: str | None = None,
    ) -> EnvironmentProjectRuntime:
        project = self.get_project(environment, project_name)
        source_dir = Path(project.source_path)
        commit_hash = None
        actual_ref = ref or project.default_ref
        prepare_log: list[str] = []
        if project.source_type == "git":
            prepare_log.append("git fetch --all --tags")
            self.runner.run(["git", "fetch", "--all", "--tags"], cwd=source_dir)
            if actual_ref:
                prepare_log.append(f"git checkout {actual_ref}")
                self._checkout_ref(source_dir, actual_ref)
            commit_hash = self.runner.run(["git", "rev-parse", "HEAD"], cwd=source_dir).output.strip()
            current_ref = self.runner.run(["git", "branch", "--show-current"], cwd=source_dir).output.strip()
            prepare_log.append(f"git branch --show-current -> {current_ref or '(detached)'}")
            prepare_log.append(f"git rev-parse HEAD -> {commit_hash}")
        elif _is_git_repo(source_dir):
            commit_hash = self.runner.run(["git", "rev-parse", "HEAD"], cwd=source_dir).output.strip()
            prepare_log.append(f"git rev-parse HEAD -> {commit_hash}")
        env_file = self.render_project_env_file(environment, project_name)
        project_dir = self.project_dir(environment, project_name)
        return EnvironmentProjectRuntime(
            project=project,
            source_dir=source_dir,
            override_dir=project_dir / "overrides",
            env_file=env_file,
            ref=actual_ref,
            commit_hash=commit_hash,
            prepare_log="\n".join(prepare_log),
        )

    def resolve_project_runtime(self, environment: str, project_name: str) -> EnvironmentProjectRuntime:
        project = self.get_project(environment, project_name)
        project_dir = self.project_dir(environment, project_name)
        return EnvironmentProjectRuntime(
            project=project,
            source_dir=Path(project.source_path),
            override_dir=project_dir / "overrides",
            env_file=project_dir / "env" / "project.env",
            ref=None,
            commit_hash=None,
            prepare_log="",
        )

    def add_git(self, name: str, git_url: str, default_branch: str | None = None) -> ServiceRecord:
        _validate_service_name(name)
        self._ensure_service_absent(name)
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
        except sqlite3.IntegrityError as exc:
            raise CatalogError(f"Service already exists: {name}") from exc
        except ValueError as exc:
            raise CatalogError(f"Cannot add service {name}: {exc}") from exc

    def list_services(self) -> list[ServiceRecord]:
        return self.state.list_services()

    def list_environment_profiles(self) -> list[EnvironmentProfileRecord]:
        return self.state.list_environment_profiles()

    def get_environment_profile(self, name: str) -> EnvironmentProfileRecord:
        _validate_target_name(name)
        try:
            return self.state.require_environment_profile(name)
        except KeyError as exc:
            raise CatalogError(f"Unknown environment profile: {name}") from exc

    def add_environment_profile(
        self,
        name: str,
        url_prefix: str | None = None,
        deploy_mode: str = "manual",
        deploy_source: str | None = None,
        deploy_pattern: str | None = None,
        deploy_pattern_type: str | None = None,
    ) -> EnvironmentProfileRecord:
        _validate_target_name(name)
        if url_prefix is not None:
            _validate_url_prefix(url_prefix)
        _validate_deploy_policy(deploy_mode, deploy_source, deploy_pattern, deploy_pattern_type)
        try:
            return self.state.add_environment_profile(
                name,
                url_prefix=url_prefix,
                deploy_mode=deploy_mode,
                deploy_source=deploy_source,
                deploy_pattern=deploy_pattern,
                deploy_pattern_type=deploy_pattern_type,
            )
        except sqlite3.IntegrityError as exc:
            raise CatalogError(f"Environment profile already exists: {name}") from exc

    def update_environment_profile(
        self,
        name: str,
        url_prefix: str | None = None,
        deploy_mode: str | None = None,
        deploy_source: str | None = None,
        deploy_pattern: str | None = None,
        deploy_pattern_type: str | None = None,
    ) -> EnvironmentProfileRecord:
        _validate_target_name(name)
        if url_prefix is not None:
            _validate_url_prefix(url_prefix)
        try:
            current = self.state.require_environment_profile(name)
            next_policy = {
                "deploy_mode": current.deploy_mode if deploy_mode is None else deploy_mode,
                "deploy_source": current.deploy_source if deploy_source is None else deploy_source,
                "deploy_pattern": current.deploy_pattern if deploy_pattern is None else deploy_pattern,
                "deploy_pattern_type": current.deploy_pattern_type if deploy_pattern_type is None else deploy_pattern_type,
            }
            _validate_deploy_policy(**next_policy)
            return self.state.update_environment_profile(
                name,
                url_prefix=url_prefix,
                deploy_mode=deploy_mode,
                deploy_source=deploy_source,
                deploy_pattern=deploy_pattern,
                deploy_pattern_type=deploy_pattern_type,
            )
        except KeyError as exc:
            raise CatalogError(f"Unknown environment profile: {name}") from exc

    def remove_environment_profile(self, name: str) -> bool:
        _validate_target_name(name)
        try:
            return self.state.remove_environment_profile(name)
        except ValueError as exc:
            raise CatalogError(str(exc)) from exc

    def history(
        self,
        service_name: str,
        environment: str | None = None,
        limit: int = 20,
    ) -> ServiceHistory:
        service = self.get_service(service_name)
        env_records = (
            tuple(self.list_environments(service_name))
            if environment is None
            else (self.get_environment(service_name, environment),)
        )
        records = tuple(self.state.history(service.name, environment=environment, limit=limit))
        return ServiceHistory(service, env_records, records)

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

    def source_status(self, name: str) -> SourceStatus:
        service = self.get_service(name)
        source_path = Path(service.source_path)
        path_exists = source_path.exists()
        is_git_repo = _is_git_repo(source_path)
        current_ref = None
        current_commit = None
        error = None

        if service.source_type == "git" and not path_exists:
            return SourceStatus(False, False, False, None, None, f"Repository is missing: {source_path}")
        if service.source_type == "git" and not is_git_repo:
            return SourceStatus(False, path_exists, False, None, None, f"Repository is not a git checkout: {source_path}")
        if not path_exists:
            return SourceStatus(False, False, False, None, None, f"Source path is missing: {source_path}")

        if is_git_repo:
            try:
                current_ref = self.runner.run(["git", "branch", "--show-current"], cwd=source_path).output.strip() or None
                current_commit = self.runner.run(["git", "rev-parse", "HEAD"], cwd=source_path).output.strip() or None
            except CommandError as exc:
                error = exc.output.strip() or str(exc)

        return SourceStatus(error is None, path_exists, is_git_repo, current_ref, current_commit, error)

    def set_env(self, service_name: str, environment: str, key: str, value: str) -> EnvironmentRecord:
        _validate_target_name(environment)
        _validate_env_key(key)
        if "\n" in value:
            raise CatalogError("Environment values must be single-line")
        try:
            return self.state.set_env_var(service_name, environment, key, value)
        except KeyError as exc:
            raise CatalogError(f"Unknown service environment: {service_name}/{environment}") from exc

    def unset_env(self, service_name: str, environment: str, key: str) -> EnvironmentRecord:
        _validate_target_name(environment)
        _validate_env_key(key)
        try:
            return self.state.unset_env_var(service_name, environment, key)
        except KeyError as exc:
            raise CatalogError(f"Unknown service environment: {service_name}/{environment}") from exc

    def list_environments(self, service_name: str) -> list[EnvironmentRecord]:
        self.get_service(service_name)
        return self.state.list_environments(service_name)

    def add_environment(
        self,
        service_name: str,
        environment: str,
    ) -> EnvironmentRecord:
        _validate_target_name(environment)
        try:
            return self.state.add_environment(service_name, environment)
        except KeyError as exc:
            missing = str(exc).strip("'")
            if missing == service_name:
                raise CatalogError(f"Unknown service: {service_name}") from exc
            raise CatalogError(f"Unknown environment profile: {environment}") from exc
        except sqlite3.IntegrityError as exc:
            raise CatalogError(f"Runtime target already exists: {service_name}/{environment}") from exc

    def remove_environment(self, service_name: str, environment: str) -> bool:
        _validate_target_name(environment)
        self.get_service(service_name)
        return self.state.remove_environment(service_name, environment)

    def get_environment(self, service_name: str, environment: str) -> EnvironmentRecord:
        _validate_target_name(environment)
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
        self.state.update_environment_source_state(
            service_name,
            environment,
            version or runtime.ref,
            runtime.ref,
            runtime.commit_hash,
        )
        result = engine.deploy(
            runtime.project_dir,
            version=version or runtime.ref,
            dry_run=dry_run,
            environment=environment,
            override_dir=runtime.override_dir,
            env_file=str(runtime.env_file),
            url_prefix=runtime.environment.url_prefix,
            env_vars=runtime.environment.env_vars,
        )
        merged_log = _merge_logs(runtime.prepare_log, result.log)
        result = DeployResult(
            result.deployment_id,
            result.project,
            result.environment,
            result.status,
            merged_log,
            result.override_path,
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
            url_prefix=runtime.environment.url_prefix,
            env_vars=runtime.environment.env_vars,
        )

    def down(
        self,
        service_name: str,
        engine: DeploymentEngine,
        environment: str = "prod",
        dry_run: bool = False,
    ) -> DeployResult:
        runtime = self.resolve_runtime(service_name, environment)
        self.render_env_file(service_name, environment)
        return engine.down(
            runtime.project_dir,
            dry_run=dry_run,
            environment=environment,
            override_dir=runtime.override_dir,
            env_file=str(runtime.env_file),
            url_prefix=runtime.environment.url_prefix,
            env_vars=runtime.environment.env_vars,
        )

    def restart(
        self,
        service_name: str,
        engine: DeploymentEngine,
        environment: str = "prod",
        dry_run: bool = False,
    ) -> DeployResult:
        runtime = self.resolve_runtime(service_name, environment)
        self.render_env_file(service_name, environment)
        return engine.restart(
            runtime.project_dir,
            dry_run=dry_run,
            environment=environment,
            override_dir=runtime.override_dir,
            env_file=str(runtime.env_file),
            url_prefix=runtime.environment.url_prefix,
            env_vars=runtime.environment.env_vars,
        )

    def status(self, service_name: str, engine: DeploymentEngine, environment: str = "prod") -> CommandResult:
        runtime = self.resolve_runtime(service_name, environment)
        self.render_env_file(service_name, environment)
        return engine.status(
            runtime.project_dir,
            environment=environment,
            override_dir=runtime.override_dir,
            env_file=str(runtime.env_file),
            url_prefix=runtime.environment.url_prefix,
            env_vars=runtime.environment.env_vars,
        )

    def logs(
        self,
        service_name: str,
        engine: DeploymentEngine,
        environment: str = "prod",
        tail: int = 200,
    ) -> CommandResult:
        runtime = self.resolve_runtime(service_name, environment)
        self.render_env_file(service_name, environment)
        return engine.logs(
            runtime.project_dir,
            environment=environment,
            override_dir=runtime.override_dir,
            env_file=str(runtime.env_file),
            tail=tail,
            url_prefix=runtime.environment.url_prefix,
            env_vars=runtime.environment.env_vars,
        )

    def prepare_runtime(self, service_name: str, environment: str, ref: str | None = None) -> ServiceRuntime:
        runtime = self.resolve_runtime(service_name, environment)
        commit_hash = None
        actual_ref = ref or runtime.service.default_branch
        prepare_log: list[str] = []
        if runtime.service.source_type == "git":
            repo_dir = runtime.project_dir
            prepare_log.append("git fetch --all --tags")
            self.runner.run(["git", "fetch", "--all", "--tags"], cwd=repo_dir)
            if actual_ref:
                prepare_log.append(f"git checkout {actual_ref}")
                self._checkout_ref(repo_dir, actual_ref)
            commit_hash = self.runner.run(["git", "rev-parse", "HEAD"], cwd=repo_dir).output.strip()
            current_ref = self.runner.run(["git", "branch", "--show-current"], cwd=repo_dir).output.strip()
            prepare_log.append(f"git branch --show-current -> {current_ref or '(detached)'}")
            prepare_log.append(f"git rev-parse HEAD -> {commit_hash}")
        elif _is_git_repo(runtime.project_dir):
            commit_hash = self.runner.run(["git", "rev-parse", "HEAD"], cwd=runtime.project_dir).output.strip()
            prepare_log.append(f"git rev-parse HEAD -> {commit_hash}")
        self.render_env_file(service_name, environment)
        return ServiceRuntime(
            runtime.service,
            runtime.environment,
            runtime.project_dir,
            runtime.override_dir,
            runtime.env_file,
            actual_ref,
            commit_hash,
            "\n".join(prepare_log),
        )

    def resolve_runtime(self, service_name: str, environment: str) -> ServiceRuntime:
        _validate_target_name(environment)
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
            prepare_log="",
        )

    def service_dir(self, name: str) -> Path:
        return self.runtime_dir / "services" / name

    def project_dir(self, environment: str, name: str) -> Path:
        return self.runtime_dir / "environments" / environment / "projects" / name

    def _ensure_service_absent(self, name: str) -> None:
        if self.state.get_service(name) is not None:
            raise CatalogError(f"Service already exists: {name}")

    def _checkout_ref(self, repo_dir: Path, ref: str) -> None:
        remote_ref = f"origin/{ref}"
        if self._has_ref(repo_dir, f"refs/remotes/{remote_ref}"):
            self.runner.run(["git", "checkout", "-B", ref, "--track", remote_ref], cwd=repo_dir)
            return
        if self._has_ref(repo_dir, f"refs/heads/{ref}"):
            self.runner.run(["git", "checkout", ref], cwd=repo_dir)
            return
        self.runner.run(["git", "checkout", "--detach", ref], cwd=repo_dir)

    def _has_ref(self, repo_dir: Path, ref: str) -> bool:
        try:
            self.runner.run(["git", "show-ref", "--verify", ref], cwd=repo_dir)
            return True
        except CommandError:
            return False


def render_env(env_vars: dict[str, str]) -> str:
    return "".join(f"{key}={_env_value(value)}\n" for key, value in sorted(env_vars.items()))


def _project_runtime_env(config: EnvironmentProjectConfig) -> dict[str, str]:
    env_vars = dict(config.project.env_vars)
    for dependency in config.dependencies:
        env_vars.update(dependency.outputs)
    return env_vars


def _merge_logs(*parts: str) -> str:
    return "\n".join(part for part in parts if part)


def _env_value(value: str) -> str:
    if value == "" or any(char.isspace() for char in value) or "#" in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _validate_service_name(name: str) -> None:
    if not _SERVICE_NAME_RE.fullmatch(name):
        raise CatalogError("Service name must contain lowercase letters, digits, and dashes")


def _validate_target_name(environment: str) -> None:
    if not _TARGET_NAME_RE.fullmatch(environment):
        raise CatalogError("Runtime target name must contain lowercase letters, digits, and dashes")


def _validate_project_scope(environment: str, project: str) -> None:
    _validate_target_name(environment)
    _validate_service_name(project)


def _validate_component_name(name: str) -> None:
    if not _TARGET_NAME_RE.fullmatch(name):
        raise CatalogError("Component name must contain lowercase letters, digits, and dashes")


def _validate_compose_files(compose_files: tuple[str, ...]) -> None:
    if not compose_files:
        return
    for file in compose_files:
        if not file or file.startswith("/") or ".." in Path(file).parts:
            raise CatalogError("Compose files must be relative paths inside the source checkout")


def _validate_component(
    mode: str,
    compose_service: str | None,
    build_context: str | None,
    dockerfile: str | None,
    image: str | None,
    port: int | None,
) -> None:
    if mode not in {"compose", "build", "image"}:
        raise CatalogError("Component mode must be compose, build, or image")
    if mode == "compose" and not compose_service:
        raise CatalogError("Compose component requires compose_service")
    if mode == "build" and not build_context:
        raise CatalogError("Build component requires build_context")
    if mode == "image" and not image:
        raise CatalogError("Image component requires image")
    if dockerfile is not None and not dockerfile.strip():
        raise CatalogError("Dockerfile must be non-empty")
    if port is not None and port <= 0:
        raise CatalogError("Component port must be positive")


def _validate_url_prefix(url_prefix: str) -> None:
    if not _URL_PREFIX_RE.fullmatch(url_prefix):
        raise CatalogError("URL prefix must be empty or contain lowercase letters, digits, and dashes")


def _validate_deploy_policy(
    deploy_mode: str,
    deploy_source: str | None,
    deploy_pattern: str | None,
    deploy_pattern_type: str | None,
) -> None:
    if deploy_mode not in DEPLOY_MODES:
        raise CatalogError("Deploy mode must be manual, webhook_auto, or webhook_gated")
    if deploy_mode == "manual":
        return
    if deploy_source not in DEPLOY_SOURCES:
        raise CatalogError("Deploy source must be branch or tag for webhook targets")
    if not deploy_pattern:
        raise CatalogError("Deploy pattern is required for webhook targets")
    if deploy_pattern_type not in DEPLOY_PATTERN_TYPES:
        raise CatalogError("Deploy pattern type must be exact or regex for webhook targets")
    if deploy_pattern_type == "regex":
        try:
            re.compile(deploy_pattern)
        except re.error as exc:
            raise CatalogError(f"Invalid deploy pattern regex: {exc}") from exc


def _validate_env_key(key: str) -> None:
    if not _ENV_KEY_RE.fullmatch(key):
        raise CatalogError("Invalid environment variable name")


def _is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()

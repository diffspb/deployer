from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path


@dataclass(frozen=True)
class DeploymentRecord:
    id: int
    project: str
    environment: str
    action: str
    version: str | None
    status: str
    started_at: str
    finished_at: str | None
    log: str


@dataclass(frozen=True)
class ServiceRecord:
    id: int
    name: str
    source_type: str
    source_url: str | None
    source_path: str
    default_branch: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class EnvironmentProfileRecord:
    name: str
    url_prefix: str
    deploy_mode: str
    deploy_source: str | None
    deploy_pattern: str | None
    deploy_pattern_type: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class EnvironmentRecord:
    id: int
    service_id: int
    name: str
    subdomain: str
    url_prefix: str
    deploy_mode: str
    deploy_source: str | None
    deploy_pattern: str | None
    deploy_pattern_type: str | None
    env_vars: dict[str, str]
    current_version: str | None
    current_ref: str | None
    current_commit: str | None
    last_deployment_id: int | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class EnvironmentProjectRecord:
    id: int
    environment: str
    name: str
    source_type: str
    source_url: str | None
    source_path: str
    default_ref: str | None
    deploy_mode: str
    deploy_source: str | None
    deploy_pattern: str | None
    deploy_pattern_type: str | None
    env_vars: dict[str, str]
    current_version: str | None
    current_ref: str | None
    current_commit: str | None
    last_deployment_id: int | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ProjectComponentRecord:
    id: int
    project_id: int
    name: str
    mode: str
    compose_service: str | None
    build_context: str | None
    dockerfile: str | None
    image: str | None
    command: str | None
    port: int | None
    env_vars: dict[str, str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ProjectEndpointRecord:
    id: int
    project_id: int
    name: str
    component: str
    port: int
    host: str | None
    subdomain: str | None
    path_prefix: str | None
    auth: str
    middlewares: tuple[str, ...]
    healthcheck_path: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ProjectDependencyRecord:
    id: int
    project_id: int
    name: str
    type: str
    target: str
    outputs: dict[str, str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class JobRecord:
    id: int
    service: str
    environment: str
    action: str
    status: str
    ref: str | None
    version: str | None
    dry_run: bool
    deployment_id: int | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    log: str
    error: str | None


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def create_deployment(
        self,
        project: str,
        environment: str,
        action: str,
        version: str | None,
    ) -> int:
        now = _now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO deployments(project, environment, action, version, status, started_at, log)
                VALUES (?, ?, ?, ?, 'running', ?, '')
                """,
                (project, environment, action, version, now),
            )
            return int(cursor.lastrowid)

    def create_job(
        self,
        service: str,
        environment: str,
        action: str,
        ref: str | None = None,
        version: str | None = None,
        dry_run: bool = False,
    ) -> int:
        now = _now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO deployment_jobs(
                    service, environment, action, status, ref, version, dry_run, created_at, log
                )
                VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, '')
                """,
                (service, environment, action, ref, version, int(dry_run), now),
            )
            return int(cursor.lastrowid)

    def start_job(self, job_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE deployment_jobs
                SET status = 'running', started_at = ?
                WHERE id = ?
                """,
                (_now(), job_id),
            )

    def finish_job(
        self,
        job_id: int,
        status: str,
        log: str,
        deployment_id: int | None = None,
        error: str | None = None,
    ) -> None:
        if status not in {"success", "failed"}:
            raise ValueError("status must be success or failed")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE deployment_jobs
                SET status = ?, deployment_id = ?, finished_at = ?, log = ?, error = ?
                WHERE id = ?
                """,
                (status, deployment_id, _now(), log, error, job_id),
            )

    def get_job(self, job_id: int) -> JobRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, service, environment, action, status, ref, version, dry_run,
                       deployment_id, created_at, started_at, finished_at, log, error
                FROM deployment_jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        return _job_record(row) if row else None

    def list_jobs(
        self,
        service: str | None = None,
        environment: str | None = None,
        limit: int = 50,
    ) -> list[JobRecord]:
        where = []
        params: list[object] = []
        if service:
            where.append("service = ?")
            params.append(service)
        if environment:
            where.append("environment = ?")
            params.append(environment)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, service, environment, action, status, ref, version, dry_run,
                       deployment_id, created_at, started_at, finished_at, log, error
                FROM deployment_jobs
                {where_sql}
                ORDER BY id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_job_record(row) for row in rows]

    def add_service(
        self,
        name: str,
        source_type: str,
        source_path: str,
        source_url: str | None = None,
        default_branch: str | None = None,
    ) -> ServiceRecord:
        if source_type not in {"git", "local"}:
            raise ValueError("source_type must be git or local")
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO services(name, source_type, source_url, source_path, default_branch, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (name, source_type, source_url, source_path, default_branch, now, now),
            )
        return self.require_service(name)

    def list_services(self) -> list[ServiceRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, name, source_type, source_url, source_path, default_branch, created_at, updated_at
                FROM services
                ORDER BY name
                """
            ).fetchall()
        return [ServiceRecord(*row) for row in rows]

    def get_service(self, name: str) -> ServiceRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, name, source_type, source_url, source_path, default_branch, created_at, updated_at
                FROM services
                WHERE name = ?
                """,
                (name,),
            ).fetchone()
        return ServiceRecord(*row) if row else None

    def require_service(self, name: str) -> ServiceRecord:
        service = self.get_service(name)
        if service is None:
            raise KeyError(name)
        return service

    def remove_service(self, name: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM services WHERE name = ?", (name,))
            return cursor.rowcount > 0

    def list_environment_profiles(self) -> list[EnvironmentProfileRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT name, url_prefix, deploy_mode, deploy_source, deploy_pattern,
                       deploy_pattern_type, created_at, updated_at
                FROM environment_profiles
                ORDER BY CASE name WHEN 'prod' THEN 0 WHEN 'dev' THEN 1 ELSE 2 END, name
                """
            ).fetchall()
        return [EnvironmentProfileRecord(*row) for row in rows]

    def get_environment_profile(self, name: str) -> EnvironmentProfileRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT name, url_prefix, deploy_mode, deploy_source, deploy_pattern,
                       deploy_pattern_type, created_at, updated_at
                FROM environment_profiles
                WHERE name = ?
                """,
                (name,),
            ).fetchone()
        return EnvironmentProfileRecord(*row) if row else None

    def require_environment_profile(self, name: str) -> EnvironmentProfileRecord:
        profile = self.get_environment_profile(name)
        if profile is None:
            raise KeyError(name)
        return profile

    def add_environment_profile(
        self,
        name: str,
        url_prefix: str | None = None,
        deploy_mode: str = "manual",
        deploy_source: str | None = None,
        deploy_pattern: str | None = None,
        deploy_pattern_type: str | None = None,
    ) -> EnvironmentProfileRecord:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO environment_profiles(
                    name, url_prefix, deploy_mode, deploy_source, deploy_pattern,
                    deploy_pattern_type, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    _default_url_prefix(name) if url_prefix is None else url_prefix,
                    deploy_mode,
                    deploy_source,
                    deploy_pattern,
                    deploy_pattern_type,
                    now,
                    now,
                ),
            )
        return self.require_environment_profile(name)

    def update_environment_profile(
        self,
        name: str,
        url_prefix: str | None = None,
        deploy_mode: str | None = None,
        deploy_source: str | None = None,
        deploy_pattern: str | None = None,
        deploy_pattern_type: str | None = None,
    ) -> EnvironmentProfileRecord:
        record = self.require_environment_profile(name)
        values = {
            "url_prefix": record.url_prefix if url_prefix is None else url_prefix,
            "deploy_mode": record.deploy_mode if deploy_mode is None else deploy_mode,
            "deploy_source": record.deploy_source if deploy_source is None else deploy_source,
            "deploy_pattern": record.deploy_pattern if deploy_pattern is None else deploy_pattern,
            "deploy_pattern_type": record.deploy_pattern_type if deploy_pattern_type is None else deploy_pattern_type,
        }
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE environment_profiles
                SET url_prefix = ?, deploy_mode = ?, deploy_source = ?,
                    deploy_pattern = ?, deploy_pattern_type = ?, updated_at = ?
                WHERE name = ?
                """,
                (
                    values["url_prefix"],
                    values["deploy_mode"],
                    values["deploy_source"],
                    values["deploy_pattern"],
                    values["deploy_pattern_type"],
                    _now(),
                    name,
                ),
            )
        return self.require_environment_profile(name)

    def remove_environment_profile(self, name: str) -> bool:
        with self._connect() as conn:
            old_used = conn.execute("SELECT 1 FROM environments WHERE name = ? LIMIT 1", (name,)).fetchone()
            new_used = conn.execute(
                "SELECT 1 FROM environment_projects WHERE environment = ? LIMIT 1",
                (name,),
            ).fetchone()
            if old_used or new_used:
                raise ValueError(f"Environment profile is in use: {name}")
            cursor = conn.execute("DELETE FROM environment_profiles WHERE name = ?", (name,))
            return cursor.rowcount > 0

    def add_project(
        self,
        environment: str,
        name: str,
        source_type: str,
        source_path: str,
        source_url: str | None = None,
        default_ref: str | None = None,
        deploy_mode: str = "manual",
        deploy_source: str | None = None,
        deploy_pattern: str | None = None,
        deploy_pattern_type: str | None = None,
    ) -> EnvironmentProjectRecord:
        if source_type not in {"git", "local"}:
            raise ValueError("source_type must be git or local")
        self.require_environment_profile(environment)
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO environment_projects(
                    environment, name, source_type, source_url, source_path, default_ref,
                    deploy_mode, deploy_source, deploy_pattern, deploy_pattern_type,
                    env_vars_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
                """,
                (
                    environment,
                    name,
                    source_type,
                    source_url,
                    source_path,
                    default_ref,
                    deploy_mode,
                    deploy_source,
                    deploy_pattern,
                    deploy_pattern_type,
                    now,
                    now,
                ),
            )
        return self.require_project(environment, name)

    def list_projects(self, environment: str | None = None) -> list[EnvironmentProjectRecord]:
        where = ""
        params: list[object] = []
        if environment is not None:
            where = "WHERE environment = ?"
            params.append(environment)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, environment, name, source_type, source_url, source_path, default_ref,
                       deploy_mode, deploy_source, deploy_pattern, deploy_pattern_type,
                       env_vars_json, current_version, current_ref, current_commit,
                       last_deployment_id, created_at, updated_at
                FROM environment_projects
                {where}
                ORDER BY environment, name
                """,
                params,
            ).fetchall()
        return [_environment_project_record(row) for row in rows]

    def get_project(self, environment: str, name: str) -> EnvironmentProjectRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, environment, name, source_type, source_url, source_path, default_ref,
                       deploy_mode, deploy_source, deploy_pattern, deploy_pattern_type,
                       env_vars_json, current_version, current_ref, current_commit,
                       last_deployment_id, created_at, updated_at
                FROM environment_projects
                WHERE environment = ? AND name = ?
                """,
                (environment, name),
            ).fetchone()
        return _environment_project_record(row) if row else None

    def require_project(self, environment: str, name: str) -> EnvironmentProjectRecord:
        project = self.get_project(environment, name)
        if project is None:
            raise KeyError(f"{environment}:{name}")
        return project

    def remove_project(self, environment: str, name: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM environment_projects WHERE environment = ? AND name = ?",
                (environment, name),
            )
            return cursor.rowcount > 0

    def set_project_env_var(self, environment: str, name: str, key: str, value: str) -> EnvironmentProjectRecord:
        project = self.require_project(environment, name)
        env_vars = dict(project.env_vars)
        env_vars[key] = value
        self._update_project_env_vars(project.id, env_vars)
        return self.require_project(environment, name)

    def unset_project_env_var(self, environment: str, name: str, key: str) -> EnvironmentProjectRecord:
        project = self.require_project(environment, name)
        env_vars = dict(project.env_vars)
        env_vars.pop(key, None)
        self._update_project_env_vars(project.id, env_vars)
        return self.require_project(environment, name)

    def update_project_source_state(
        self,
        environment: str,
        name: str,
        version: str | None,
        ref: str | None,
        commit_hash: str | None,
    ) -> None:
        project = self.require_project(environment, name)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE environment_projects
                SET current_version = ?, current_ref = ?, current_commit = ?, updated_at = ?
                WHERE id = ?
                """,
                (version, ref, commit_hash, _now(), project.id),
            )

    def update_project_version(
        self,
        environment: str,
        name: str,
        deployment_id: int,
        version: str | None,
        ref: str | None,
        commit_hash: str | None,
    ) -> None:
        project = self.require_project(environment, name)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE environment_projects
                SET current_version = ?, current_ref = ?, current_commit = ?,
                    last_deployment_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (version, ref, commit_hash, deployment_id, _now(), project.id),
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
        project_record = self.require_project(environment, project)
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO project_components(
                    project_id, name, mode, compose_service, build_context, dockerfile,
                    image, command, port, env_vars_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_record.id,
                    name,
                    mode,
                    compose_service,
                    build_context,
                    dockerfile,
                    image,
                    command,
                    port,
                    json.dumps(env_vars or {}, sort_keys=True),
                    now,
                    now,
                ),
            )
        return self.require_component(environment, project, name)

    def list_components(self, environment: str, project: str) -> list[ProjectComponentRecord]:
        project_record = self.require_project(environment, project)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, project_id, name, mode, compose_service, build_context, dockerfile,
                       image, command, port, env_vars_json, created_at, updated_at
                FROM project_components
                WHERE project_id = ?
                ORDER BY name
                """,
                (project_record.id,),
            ).fetchall()
        return [_project_component_record(row) for row in rows]

    def get_component(self, environment: str, project: str, name: str) -> ProjectComponentRecord | None:
        project_record = self.require_project(environment, project)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, project_id, name, mode, compose_service, build_context, dockerfile,
                       image, command, port, env_vars_json, created_at, updated_at
                FROM project_components
                WHERE project_id = ? AND name = ?
                """,
                (project_record.id, name),
            ).fetchone()
        return _project_component_record(row) if row else None

    def require_component(self, environment: str, project: str, name: str) -> ProjectComponentRecord:
        component = self.get_component(environment, project, name)
        if component is None:
            raise KeyError(f"{environment}:{project}:{name}")
        return component

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
        project_record = self.require_project(environment, project)
        self.require_component(environment, project, component)
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO project_endpoints(
                    project_id, name, component, port, host, subdomain, path_prefix, auth,
                    middlewares_json, healthcheck_path, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_record.id,
                    name,
                    component,
                    port,
                    host,
                    subdomain,
                    path_prefix,
                    auth,
                    json.dumps(list(middlewares)),
                    healthcheck_path,
                    now,
                    now,
                ),
            )
        return self.require_endpoint(environment, project, name)

    def list_endpoints(self, environment: str, project: str) -> list[ProjectEndpointRecord]:
        project_record = self.require_project(environment, project)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, project_id, name, component, port, host, subdomain, path_prefix,
                       auth, middlewares_json, healthcheck_path, created_at, updated_at
                FROM project_endpoints
                WHERE project_id = ?
                ORDER BY name
                """,
                (project_record.id,),
            ).fetchall()
        return [_project_endpoint_record(row) for row in rows]

    def get_endpoint(self, environment: str, project: str, name: str) -> ProjectEndpointRecord | None:
        project_record = self.require_project(environment, project)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, project_id, name, component, port, host, subdomain, path_prefix,
                       auth, middlewares_json, healthcheck_path, created_at, updated_at
                FROM project_endpoints
                WHERE project_id = ? AND name = ?
                """,
                (project_record.id, name),
            ).fetchone()
        return _project_endpoint_record(row) if row else None

    def require_endpoint(self, environment: str, project: str, name: str) -> ProjectEndpointRecord:
        endpoint = self.get_endpoint(environment, project, name)
        if endpoint is None:
            raise KeyError(f"{environment}:{project}:{name}")
        return endpoint

    def add_dependency(
        self,
        environment: str,
        project: str,
        name: str,
        type: str,
        target: str,
        outputs: dict[str, str] | None = None,
    ) -> ProjectDependencyRecord:
        project_record = self.require_project(environment, project)
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO project_dependencies(
                    project_id, name, type, target, outputs_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (project_record.id, name, type, target, json.dumps(outputs or {}, sort_keys=True), now, now),
            )
        return self.require_dependency(environment, project, name)

    def list_dependencies(self, environment: str, project: str) -> list[ProjectDependencyRecord]:
        project_record = self.require_project(environment, project)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, project_id, name, type, target, outputs_json, created_at, updated_at
                FROM project_dependencies
                WHERE project_id = ?
                ORDER BY name
                """,
                (project_record.id,),
            ).fetchall()
        return [_project_dependency_record(row) for row in rows]

    def get_dependency(self, environment: str, project: str, name: str) -> ProjectDependencyRecord | None:
        project_record = self.require_project(environment, project)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, project_id, name, type, target, outputs_json, created_at, updated_at
                FROM project_dependencies
                WHERE project_id = ? AND name = ?
                """,
                (project_record.id, name),
            ).fetchone()
        return _project_dependency_record(row) if row else None

    def require_dependency(self, environment: str, project: str, name: str) -> ProjectDependencyRecord:
        dependency = self.get_dependency(environment, project, name)
        if dependency is None:
            raise KeyError(f"{environment}:{project}:{name}")
        return dependency

    def list_environments(self, service_name: str) -> list[EnvironmentRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT e.id, e.service_id, e.name, e.subdomain,
                       p.url_prefix, p.deploy_mode, p.deploy_source, p.deploy_pattern, p.deploy_pattern_type,
                       e.env_vars_json,
                       e.current_version, e.current_ref, e.current_commit,
                       e.last_deployment_id, e.created_at, e.updated_at
                FROM environments e
                JOIN services s ON s.id = e.service_id
                JOIN environment_profiles p ON p.name = e.name
                WHERE s.name = ?
                ORDER BY
                    CASE e.name WHEN 'prod' THEN 0 WHEN 'dev' THEN 1 ELSE 2 END,
                    e.name
                """,
                (service_name,),
            ).fetchall()
        return [_environment_record(row) for row in rows]

    def add_environment(
        self,
        service_name: str,
        environment: str,
    ) -> EnvironmentRecord:
        service = self.require_service(service_name)
        self.require_environment_profile(environment)
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO environments(service_id, name, subdomain, env_vars_json, created_at, updated_at)
                VALUES (?, ?, ?, '{}', ?, ?)
                """,
                (service.id, environment, service.name, now, now),
            )
        return self.require_environment(service_name, environment)

    def remove_environment(self, service_name: str, environment: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM environments
                WHERE id IN (
                    SELECT e.id
                    FROM environments e
                    JOIN services s ON s.id = e.service_id
                    WHERE s.name = ? AND e.name = ?
                )
                """,
                (service_name, environment),
            )
            return cursor.rowcount > 0

    def get_environment(self, service_name: str, environment: str) -> EnvironmentRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT e.id, e.service_id, e.name, e.subdomain,
                       p.url_prefix, p.deploy_mode, p.deploy_source, p.deploy_pattern, p.deploy_pattern_type,
                       e.env_vars_json,
                       e.current_version, e.current_ref, e.current_commit,
                       e.last_deployment_id, e.created_at, e.updated_at
                FROM environments e
                JOIN services s ON s.id = e.service_id
                JOIN environment_profiles p ON p.name = e.name
                WHERE s.name = ? AND e.name = ?
                """,
                (service_name, environment),
            ).fetchone()
        return _environment_record(row) if row else None

    def require_environment(self, service_name: str, environment: str) -> EnvironmentRecord:
        record = self.get_environment(service_name, environment)
        if record is None:
            raise KeyError(f"{service_name}:{environment}")
        return record

    def set_env_var(self, service_name: str, environment: str, key: str, value: str) -> EnvironmentRecord:
        record = self.require_environment(service_name, environment)
        env_vars = dict(record.env_vars)
        env_vars[key] = value
        self._update_env_vars(record.id, env_vars)
        return self.require_environment(service_name, environment)

    def unset_env_var(self, service_name: str, environment: str, key: str) -> EnvironmentRecord:
        record = self.require_environment(service_name, environment)
        env_vars = dict(record.env_vars)
        env_vars.pop(key, None)
        self._update_env_vars(record.id, env_vars)
        return self.require_environment(service_name, environment)

    def update_environment_version(
        self,
        service_name: str,
        environment: str,
        deployment_id: int,
        version: str | None,
        ref: str | None,
        commit_hash: str | None,
    ) -> None:
        record = self.require_environment(service_name, environment)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE environments
                SET current_version = ?, current_ref = ?, current_commit = ?,
                    last_deployment_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (version, ref, commit_hash, deployment_id, _now(), record.id),
            )

    def update_environment_source_state(
        self,
        service_name: str,
        environment: str,
        version: str | None,
        ref: str | None,
        commit_hash: str | None,
    ) -> None:
        record = self.require_environment(service_name, environment)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE environments
                SET current_version = ?, current_ref = ?, current_commit = ?, updated_at = ?
                WHERE id = ?
                """,
                (version, ref, commit_hash, _now(), record.id),
            )

    def finish_deployment(self, deployment_id: int, status: str, log: str) -> None:
        if status not in {"success", "failed"}:
            raise ValueError("status must be success or failed")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE deployments
                SET status = ?, finished_at = ?, log = ?
                WHERE id = ?
                """,
                (status, _now(), log, deployment_id),
            )

    def history(
        self,
        project: str,
        environment: str | None = None,
        limit: int = 20,
    ) -> list[DeploymentRecord]:
        where = "WHERE project = ?"
        params: list[object] = [project]
        if environment:
            where += " AND environment = ?"
            params.append(environment)
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, project, environment, action, version, status, started_at, finished_at, log
                FROM deployments
                {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [DeploymentRecord(*row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _update_env_vars(self, environment_id: int, env_vars: dict[str, str]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE environments
                SET env_vars_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(env_vars, sort_keys=True), _now(), environment_id),
            )

    def _update_project_env_vars(self, project_id: int, env_vars: dict[str, str]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE environment_projects
                SET env_vars_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(env_vars, sort_keys=True), _now(), project_id),
            )

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS deployments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL,
                    environment TEXT NOT NULL DEFAULT 'prod',
                    action TEXT NOT NULL DEFAULT 'deploy',
                    version TEXT,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    log TEXT NOT NULL
                )
                """
            )
            _ensure_column(conn, "deployments", "environment", "TEXT NOT NULL DEFAULT 'prod'")
            _ensure_column(conn, "deployments", "action", "TEXT NOT NULL DEFAULT 'deploy'")
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_deployments_project_id
                ON deployments(project, id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_deployments_project_environment_id
                ON deployments(project, environment, id)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    source_type TEXT NOT NULL,
                    source_url TEXT,
                    source_path TEXT NOT NULL,
                    default_branch TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS environment_profiles (
                    name TEXT PRIMARY KEY,
                    url_prefix TEXT NOT NULL DEFAULT '',
                    deploy_mode TEXT NOT NULL DEFAULT 'manual',
                    deploy_source TEXT,
                    deploy_pattern TEXT,
                    deploy_pattern_type TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            now = _now()
            _ensure_environment_profile(conn, "prod", "", now)
            _ensure_environment_profile(conn, "dev", "dev", now)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS environments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    subdomain TEXT NOT NULL,
                    url_prefix TEXT,
                    deploy_mode TEXT NOT NULL DEFAULT 'manual',
                    deploy_source TEXT,
                    deploy_pattern TEXT,
                    deploy_pattern_type TEXT,
                    env_vars_json TEXT NOT NULL DEFAULT '{}',
                    current_version TEXT,
                    current_ref TEXT,
                    current_commit TEXT,
                    last_deployment_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(service_id, name),
                    FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE CASCADE
                )
                """
            )
            _ensure_column(conn, "environments", "url_prefix", "TEXT")
            _ensure_column(conn, "environments", "deploy_mode", "TEXT NOT NULL DEFAULT 'manual'")
            _ensure_column(conn, "environments", "deploy_source", "TEXT")
            _ensure_column(conn, "environments", "deploy_pattern", "TEXT")
            _ensure_column(conn, "environments", "deploy_pattern_type", "TEXT")
            conn.execute(
                """
                INSERT OR IGNORE INTO environment_profiles(
                    name, url_prefix, deploy_mode, deploy_source, deploy_pattern,
                    deploy_pattern_type, created_at, updated_at
                )
                SELECT DISTINCT
                    name,
                    COALESCE(url_prefix, CASE name WHEN 'prod' THEN '' ELSE name END),
                    COALESCE(deploy_mode, 'manual'),
                    deploy_source,
                    deploy_pattern,
                    deploy_pattern_type,
                    COALESCE(created_at, ?),
                    COALESCE(updated_at, ?)
                FROM environments
                """,
                (now, now),
            )
            conn.execute(
                """
                UPDATE environments
                SET url_prefix = CASE name WHEN 'prod' THEN '' ELSE name END
                WHERE url_prefix IS NULL
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_environments_service_name
                ON environments(service_id, name)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS deployment_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    ref TEXT,
                    version TEXT,
                    dry_run INTEGER NOT NULL DEFAULT 0,
                    deployment_id INTEGER,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    log TEXT NOT NULL DEFAULT '',
                    error TEXT,
                    FOREIGN KEY(deployment_id) REFERENCES deployments(id) ON DELETE SET NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_deployment_jobs_service_id
                ON deployment_jobs(service, id)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS environment_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    environment TEXT NOT NULL,
                    name TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_url TEXT,
                    source_path TEXT NOT NULL,
                    default_ref TEXT,
                    deploy_mode TEXT NOT NULL DEFAULT 'manual',
                    deploy_source TEXT,
                    deploy_pattern TEXT,
                    deploy_pattern_type TEXT,
                    env_vars_json TEXT NOT NULL DEFAULT '{}',
                    current_version TEXT,
                    current_ref TEXT,
                    current_commit TEXT,
                    last_deployment_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(environment, name),
                    FOREIGN KEY(environment) REFERENCES environment_profiles(name) ON DELETE RESTRICT,
                    FOREIGN KEY(last_deployment_id) REFERENCES deployments(id) ON DELETE SET NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_environment_projects_environment_name
                ON environment_projects(environment, name)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS project_components (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'compose',
                    compose_service TEXT,
                    build_context TEXT,
                    dockerfile TEXT,
                    image TEXT,
                    command TEXT,
                    port INTEGER,
                    env_vars_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, name),
                    FOREIGN KEY(project_id) REFERENCES environment_projects(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS project_endpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    component TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    host TEXT,
                    subdomain TEXT,
                    path_prefix TEXT,
                    auth TEXT NOT NULL DEFAULT 'none',
                    middlewares_json TEXT NOT NULL DEFAULT '[]',
                    healthcheck_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, name),
                    FOREIGN KEY(project_id) REFERENCES environment_projects(id) ON DELETE CASCADE,
                    FOREIGN KEY(project_id, component) REFERENCES project_components(project_id, name) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS project_dependencies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    target TEXT NOT NULL,
                    outputs_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, name),
                    FOREIGN KEY(project_id) REFERENCES environment_projects(id) ON DELETE CASCADE
                )
                """
            )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _ensure_environment_profile(conn: sqlite3.Connection, name: str, url_prefix: str, now: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO environment_profiles(
            name, url_prefix, deploy_mode, deploy_source, deploy_pattern,
            deploy_pattern_type, created_at, updated_at
        )
        VALUES (?, ?, 'manual', NULL, NULL, NULL, ?, ?)
        """,
        (name, url_prefix, now, now),
    )


def _environment_record(row) -> EnvironmentRecord:
    return EnvironmentRecord(
        id=row[0],
        service_id=row[1],
        name=row[2],
        subdomain=row[3],
        url_prefix=row[4] or "",
        deploy_mode=row[5] or "manual",
        deploy_source=row[6],
        deploy_pattern=row[7],
        deploy_pattern_type=row[8],
        env_vars=json.loads(row[9] or "{}"),
        current_version=row[10],
        current_ref=row[11],
        current_commit=row[12],
        last_deployment_id=row[13],
        created_at=row[14],
        updated_at=row[15],
    )


def _environment_project_record(row) -> EnvironmentProjectRecord:
    return EnvironmentProjectRecord(
        id=row[0],
        environment=row[1],
        name=row[2],
        source_type=row[3],
        source_url=row[4],
        source_path=row[5],
        default_ref=row[6],
        deploy_mode=row[7] or "manual",
        deploy_source=row[8],
        deploy_pattern=row[9],
        deploy_pattern_type=row[10],
        env_vars=json.loads(row[11] or "{}"),
        current_version=row[12],
        current_ref=row[13],
        current_commit=row[14],
        last_deployment_id=row[15],
        created_at=row[16],
        updated_at=row[17],
    )


def _project_component_record(row) -> ProjectComponentRecord:
    return ProjectComponentRecord(
        id=row[0],
        project_id=row[1],
        name=row[2],
        mode=row[3],
        compose_service=row[4],
        build_context=row[5],
        dockerfile=row[6],
        image=row[7],
        command=row[8],
        port=row[9],
        env_vars=json.loads(row[10] or "{}"),
        created_at=row[11],
        updated_at=row[12],
    )


def _project_endpoint_record(row) -> ProjectEndpointRecord:
    return ProjectEndpointRecord(
        id=row[0],
        project_id=row[1],
        name=row[2],
        component=row[3],
        port=row[4],
        host=row[5],
        subdomain=row[6],
        path_prefix=row[7],
        auth=row[8],
        middlewares=tuple(json.loads(row[9] or "[]")),
        healthcheck_path=row[10],
        created_at=row[11],
        updated_at=row[12],
    )


def _project_dependency_record(row) -> ProjectDependencyRecord:
    return ProjectDependencyRecord(
        id=row[0],
        project_id=row[1],
        name=row[2],
        type=row[3],
        target=row[4],
        outputs=json.loads(row[5] or "{}"),
        created_at=row[6],
        updated_at=row[7],
    )


def _default_url_prefix(environment: str) -> str:
    return "" if environment == "prod" else environment


def _job_record(row) -> JobRecord:
    return JobRecord(
        id=row[0],
        service=row[1],
        environment=row[2],
        action=row[3],
        status=row[4],
        ref=row[5],
        version=row[6],
        dry_run=bool(row[7]),
        deployment_id=row[8],
        created_at=row[9],
        started_at=row[10],
        finished_at=row[11],
        log=row[12],
        error=row[13],
    )

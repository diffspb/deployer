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
class EnvironmentRecord:
    id: int
    service_id: int
    name: str
    subdomain: str
    env_vars: dict[str, str]
    current_version: str | None
    current_ref: str | None
    current_commit: str | None
    last_deployment_id: int | None
    created_at: str
    updated_at: str


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
            cursor = conn.execute(
                """
                INSERT INTO services(name, source_type, source_url, source_path, default_branch, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (name, source_type, source_url, source_path, default_branch, now, now),
            )
            service_id = int(cursor.lastrowid)
            for environment in ("prod", "dev"):
                conn.execute(
                    """
                    INSERT INTO environments(service_id, name, subdomain, env_vars_json, created_at, updated_at)
                    VALUES (?, ?, ?, '{}', ?, ?)
                    """,
                    (service_id, environment, name, now, now),
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

    def get_environment(self, service_name: str, environment: str) -> EnvironmentRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT e.id, e.service_id, e.name, e.subdomain, e.env_vars_json,
                       e.current_version, e.current_ref, e.current_commit,
                       e.last_deployment_id, e.created_at, e.updated_at
                FROM environments e
                JOIN services s ON s.id = e.service_id
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
                CREATE TABLE IF NOT EXISTS environments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    subdomain TEXT NOT NULL,
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
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_environments_service_name
                ON environments(service_id, name)
                """
            )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _environment_record(row) -> EnvironmentRecord:
    return EnvironmentRecord(
        id=row[0],
        service_id=row[1],
        name=row[2],
        subdomain=row[3],
        env_vars=json.loads(row[4] or "{}"),
        current_version=row[5],
        current_ref=row[6],
        current_commit=row[7],
        last_deployment_id=row[8],
        created_at=row[9],
        updated_at=row[10],
    )

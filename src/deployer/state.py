from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
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
        return sqlite3.connect(self.path)

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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from deployer.errors import CommandError
from deployer.health import check_health
from deployer.manifest import Manifest, load_manifest
from deployer.override import write_override
from deployer.runner import CommandRunner
from deployer.state import StateStore


_locks_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


@dataclass(frozen=True)
class DeployResult:
    deployment_id: int
    project: str
    status: str
    log: str
    override_path: Path


class DeploymentEngine:
    def __init__(
        self,
        state: StateStore,
        runner: CommandRunner | None = None,
        health_checker=check_health,
    ):
        self.state = state
        self.runner = runner or CommandRunner()
        self.health_checker = health_checker

    def deploy(
        self,
        project_dir: Path,
        version: str | None = None,
        dry_run: bool = False,
        manifest_path: Path | None = None,
    ) -> DeployResult:
        project_dir = project_dir.resolve()
        manifest = load_manifest(project_dir, manifest_path=manifest_path)
        deployment_id = self.state.create_deployment(manifest.project_name, version)
        log_parts: list[str] = []
        override_path = project_dir / ".deployer" / "docker-compose.override.yml"

        lock = _project_lock(manifest.project_name)
        with lock:
            try:
                override_path = write_override(project_dir, manifest)
                log_parts.append(f"Generated override: {override_path}")
                command = compose_command(manifest, override_path)
                log_parts.append(f"Command: {' '.join(command)}")

                if dry_run:
                    log_parts.append("Dry run: docker compose was not executed")
                else:
                    result = self.runner.run(command, cwd=project_dir)
                    log_parts.append(result.output)
                    ok, message = self.health_checker(manifest)
                    log_parts.append(message)
                    if not ok:
                        raise RuntimeError(message)

                log = "\n".join(part for part in log_parts if part)
                self.state.finish_deployment(deployment_id, "success", log)
                return DeployResult(deployment_id, manifest.project_name, "success", log, override_path)
            except (CommandError, RuntimeError) as exc:
                if isinstance(exc, CommandError):
                    log_parts.append(exc.output)
                else:
                    log_parts.append(str(exc))
                log = "\n".join(part for part in log_parts if part)
                self.state.finish_deployment(deployment_id, "failed", log)
                return DeployResult(deployment_id, manifest.project_name, "failed", log, override_path)


def compose_command(manifest: Manifest, override_path: Path) -> list[str]:
    command = ["docker", "compose", "-p", manifest.project_name]
    for file in manifest.compose.files:
        command.extend(["-f", file])
    command.extend(["-f", str(override_path), "up", "-d", "--build"])
    return command


def _project_lock(project: str) -> threading.Lock:
    with _locks_guard:
        if project not in _locks:
            _locks[project] = threading.Lock()
        return _locks[project]

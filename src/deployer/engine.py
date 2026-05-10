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
    environment: str
    status: str
    log: str
    override_path: Path


@dataclass(frozen=True)
class CommandResult:
    project: str
    environment: str
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
        environment: str = "prod",
        override_dir: Path | None = None,
        env_file: str | None = None,
    ) -> DeployResult:
        project_dir = project_dir.resolve()
        manifest = load_manifest(project_dir, manifest_path=manifest_path)
        deployment_id = self.state.create_deployment(
            manifest.project_name,
            environment,
            "deploy",
            version,
        )
        log_parts: list[str] = []
        override_path = (override_dir or project_dir / ".deployer") / f"{environment}.override.yml"

        lock = _project_lock(manifest.project_name)
        with lock:
            try:
                override_path = write_override(
                    project_dir,
                    manifest,
                    environment=environment,
                    output_dir=override_dir,
                    env_file=env_file,
                )
                log_parts.append(f"Generated override: {override_path}")
                command = compose_command(manifest, override_path, environment=environment)
                log_parts.append(f"Command: {' '.join(command)}")

                if dry_run:
                    log_parts.append("Dry run: docker compose was not executed")
                else:
                    result = self.runner.run(command, cwd=project_dir)
                    log_parts.append(result.output)
                    ok, message = self.health_checker(manifest, environment=environment)
                    log_parts.append(message)
                    if not ok:
                        raise RuntimeError(message)

                log = "\n".join(part for part in log_parts if part)
                self.state.finish_deployment(deployment_id, "success", log)
                return DeployResult(deployment_id, manifest.project_name, environment, "success", log, override_path)
            except (CommandError, RuntimeError) as exc:
                if isinstance(exc, CommandError):
                    log_parts.append(exc.output)
                else:
                    log_parts.append(str(exc))
                log = "\n".join(part for part in log_parts if part)
                self.state.finish_deployment(deployment_id, "failed", log)
                return DeployResult(deployment_id, manifest.project_name, environment, "failed", log, override_path)

    def stop(
        self,
        project_dir: Path,
        dry_run: bool = False,
        manifest_path: Path | None = None,
        environment: str = "prod",
        override_dir: Path | None = None,
        env_file: str | None = None,
    ) -> DeployResult:
        project_dir = project_dir.resolve()
        manifest = load_manifest(project_dir, manifest_path=manifest_path)
        deployment_id = self.state.create_deployment(
            manifest.project_name,
            environment,
            "stop",
            None,
        )
        log_parts: list[str] = []
        override_path = (override_dir or project_dir / ".deployer") / f"{environment}.override.yml"

        lock = _project_lock(manifest.project_name)
        with lock:
            try:
                override_path = write_override(
                    project_dir,
                    manifest,
                    environment=environment,
                    output_dir=override_dir,
                    env_file=env_file,
                )
                log_parts.append(f"Generated override: {override_path}")
                command = compose_command(manifest, override_path, environment=environment, action="stop")
                log_parts.append(f"Command: {' '.join(command)}")
                if dry_run:
                    log_parts.append("Dry run: docker compose was not executed")
                else:
                    result = self.runner.run(command, cwd=project_dir)
                    log_parts.append(result.output)
                log = "\n".join(part for part in log_parts if part)
                self.state.finish_deployment(deployment_id, "success", log)
                return DeployResult(deployment_id, manifest.project_name, environment, "success", log, override_path)
            except CommandError as exc:
                log_parts.append(exc.output)
                log = "\n".join(part for part in log_parts if part)
                self.state.finish_deployment(deployment_id, "failed", log)
                return DeployResult(deployment_id, manifest.project_name, environment, "failed", log, override_path)

    def down(
        self,
        project_dir: Path,
        dry_run: bool = False,
        manifest_path: Path | None = None,
        environment: str = "prod",
        override_dir: Path | None = None,
        env_file: str | None = None,
    ) -> DeployResult:
        return self._deployment_action(
            "down",
            project_dir,
            dry_run=dry_run,
            manifest_path=manifest_path,
            environment=environment,
            override_dir=override_dir,
            env_file=env_file,
        )

    def restart(
        self,
        project_dir: Path,
        dry_run: bool = False,
        manifest_path: Path | None = None,
        environment: str = "prod",
        override_dir: Path | None = None,
        env_file: str | None = None,
    ) -> DeployResult:
        return self._deployment_action(
            "restart",
            project_dir,
            dry_run=dry_run,
            manifest_path=manifest_path,
            environment=environment,
            override_dir=override_dir,
            env_file=env_file,
        )

    def status(
        self,
        project_dir: Path,
        manifest_path: Path | None = None,
        environment: str = "prod",
        override_dir: Path | None = None,
        env_file: str | None = None,
    ) -> CommandResult:
        project_dir = project_dir.resolve()
        manifest = load_manifest(project_dir, manifest_path=manifest_path)
        override_path = write_override(
            project_dir,
            manifest,
            environment=environment,
            output_dir=override_dir,
            env_file=env_file,
        )
        command = compose_command(manifest, override_path, environment=environment, action="ps")
        try:
            result = self.runner.run(command, cwd=project_dir)
            return CommandResult(manifest.project_name, environment, "success", result.output, override_path)
        except CommandError as exc:
            return CommandResult(manifest.project_name, environment, "failed", exc.output, override_path)

    def logs(
        self,
        project_dir: Path,
        manifest_path: Path | None = None,
        environment: str = "prod",
        override_dir: Path | None = None,
        env_file: str | None = None,
        tail: int = 200,
    ) -> CommandResult:
        project_dir = project_dir.resolve()
        manifest = load_manifest(project_dir, manifest_path=manifest_path)
        override_path = write_override(
            project_dir,
            manifest,
            environment=environment,
            output_dir=override_dir,
            env_file=env_file,
        )
        command = compose_command(manifest, override_path, environment=environment, action="logs", tail=tail)
        try:
            result = self.runner.run(command, cwd=project_dir)
            return CommandResult(manifest.project_name, environment, "success", result.output, override_path)
        except CommandError as exc:
            return CommandResult(manifest.project_name, environment, "failed", exc.output, override_path)

    def _deployment_action(
        self,
        action: str,
        project_dir: Path,
        dry_run: bool = False,
        manifest_path: Path | None = None,
        environment: str = "prod",
        override_dir: Path | None = None,
        env_file: str | None = None,
    ) -> DeployResult:
        project_dir = project_dir.resolve()
        manifest = load_manifest(project_dir, manifest_path=manifest_path)
        deployment_id = self.state.create_deployment(
            manifest.project_name,
            environment,
            action,
            None,
        )
        log_parts: list[str] = []
        override_path = (override_dir or project_dir / ".deployer") / f"{environment}.override.yml"

        lock = _project_lock(manifest.project_name)
        with lock:
            try:
                override_path = write_override(
                    project_dir,
                    manifest,
                    environment=environment,
                    output_dir=override_dir,
                    env_file=env_file,
                )
                log_parts.append(f"Generated override: {override_path}")
                command = compose_command(manifest, override_path, environment=environment, action=action)
                log_parts.append(f"Command: {' '.join(command)}")
                if dry_run:
                    log_parts.append("Dry run: docker compose was not executed")
                else:
                    result = self.runner.run(command, cwd=project_dir)
                    log_parts.append(result.output)
                log = "\n".join(part for part in log_parts if part)
                self.state.finish_deployment(deployment_id, "success", log)
                return DeployResult(deployment_id, manifest.project_name, environment, "success", log, override_path)
            except CommandError as exc:
                log_parts.append(exc.output)
                log = "\n".join(part for part in log_parts if part)
                self.state.finish_deployment(deployment_id, "failed", log)
                return DeployResult(deployment_id, manifest.project_name, environment, "failed", log, override_path)


def compose_command(
    manifest: Manifest,
    override_path: Path,
    environment: str = "prod",
    action: str = "up",
    tail: int = 200,
) -> list[str]:
    command = ["docker", "compose", "-p", manifest.project_name_for(environment)]
    for file in manifest.compose.files:
        command.extend(["-f", file])
    command.extend(["-f", str(override_path)])
    if action == "up":
        command.extend(["up", "-d", "--build"])
    elif action == "stop":
        command.append("stop")
    elif action == "down":
        command.append("down")
    elif action == "restart":
        command.append("restart")
    elif action == "ps":
        command.extend(["ps", "--format", "json"])
    elif action == "logs":
        command.extend(["logs", "--tail", str(tail)])
    else:
        raise ValueError(f"Unknown compose action: {action}")
    return command


def _project_lock(project: str) -> threading.Lock:
    with _locks_guard:
        if project not in _locks:
            _locks[project] = threading.Lock()
        return _locks[project]

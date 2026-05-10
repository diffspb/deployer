from __future__ import annotations

import argparse
import sys
from pathlib import Path

from deployer.catalog import DEFAULT_RUNTIME_DIR, ServiceCatalog
from deployer.engine import DeploymentEngine
from deployer.errors import DeployerError
from deployer.manifest import load_manifest
from deployer.override import render_override
from deployer.state import StateStore


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "services":
            state = StateStore(args.state_db)
            catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
            return _handle_services(args, catalog)
        if args.command == "env":
            state = StateStore(args.state_db)
            catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
            return _handle_env(args, catalog)
        if args.command == "refs":
            state = StateStore(args.state_db)
            catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
            print(catalog.refs(args.service), end="")
            return 0
        if args.command == "validate":
            manifest = load_manifest(args.project_dir, manifest_path=args.manifest)
            print(f"ok: {manifest.project_name}")
            return 0
        if args.command == "render-override":
            manifest = load_manifest(args.project_dir, manifest_path=args.manifest)
            print(render_override(manifest, environment=args.environment), end="")
            return 0
        if args.command == "deploy":
            state = StateStore(args.state_db)
            engine = DeploymentEngine(state)
            if _is_path_target(args.target):
                result = engine.deploy(
                    Path(args.target),
                    version=args.version,
                    dry_run=args.dry_run,
                    manifest_path=args.manifest,
                    environment=args.environment,
                )
            else:
                catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
                result = catalog.deploy(
                    args.target,
                    engine,
                    environment=args.environment,
                    ref=args.ref,
                    version=args.version,
                    dry_run=args.dry_run,
                )
            print(result.log)
            return 0 if result.status == "success" else 1
        if args.command == "stop":
            state = StateStore(args.state_db)
            engine = DeploymentEngine(state)
            if _is_path_target(args.target):
                result = engine.stop(
                    Path(args.target),
                    dry_run=args.dry_run,
                    manifest_path=args.manifest,
                    environment=args.environment,
                )
            else:
                catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
                result = catalog.stop(args.target, engine, environment=args.environment, dry_run=args.dry_run)
            print(result.log)
            return 0 if result.status == "success" else 1
        if args.command == "down":
            state = StateStore(args.state_db)
            engine = DeploymentEngine(state)
            if _is_path_target(args.target):
                result = engine.down(
                    Path(args.target),
                    dry_run=args.dry_run,
                    manifest_path=args.manifest,
                    environment=args.environment,
                )
            else:
                catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
                result = catalog.down(args.target, engine, environment=args.environment, dry_run=args.dry_run)
            print(result.log)
            return 0 if result.status == "success" else 1
        if args.command == "restart":
            state = StateStore(args.state_db)
            engine = DeploymentEngine(state)
            if _is_path_target(args.target):
                result = engine.restart(
                    Path(args.target),
                    dry_run=args.dry_run,
                    manifest_path=args.manifest,
                    environment=args.environment,
                )
            else:
                catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
                result = catalog.restart(args.target, engine, environment=args.environment, dry_run=args.dry_run)
            print(result.log)
            return 0 if result.status == "success" else 1
        if args.command == "status":
            state = StateStore(args.state_db)
            engine = DeploymentEngine(state)
            if _is_path_target(args.target):
                result = engine.status(
                    Path(args.target),
                    manifest_path=args.manifest,
                    environment=args.environment,
                )
            else:
                catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
                result = catalog.status(args.target, engine, environment=args.environment)
            print(result.log, end="" if result.log.endswith("\n") else "\n")
            return 0 if result.status == "success" else 1
        if args.command == "logs":
            state = StateStore(args.state_db)
            engine = DeploymentEngine(state)
            if _is_path_target(args.target):
                result = engine.logs(
                    Path(args.target),
                    manifest_path=args.manifest,
                    environment=args.environment,
                    tail=args.tail,
                )
            else:
                catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
                result = catalog.logs(args.target, engine, environment=args.environment, tail=args.tail)
            print(result.log, end="" if result.log.endswith("\n") else "\n")
            return 0 if result.status == "success" else 1
        if args.command == "history":
            state = StateStore(args.state_db)
            catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
            if _is_service_target(args.project, state):
                _print_service_history(catalog, args.project, args.environment, args.limit)
            else:
                for record in state.history(args.project, environment=args.environment, limit=args.limit):
                    print(_format_history_record(record))
            return 0
    except DeployerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    parser.print_help()
    return 2


def _handle_services(args: argparse.Namespace, catalog: ServiceCatalog) -> int:
    if args.services_command == "add-local":
        service = catalog.add_local(args.name, args.path)
        print(f"added\t{service.name}\t{service.source_type}\t{service.source_path}")
        return 0
    if args.services_command == "add":
        service = catalog.add_git(args.name, args.git_url, default_branch=args.default_branch)
        print(f"added\t{service.name}\t{service.source_type}\t{service.source_url}")
        return 0
    if args.services_command == "list":
        for service in catalog.list_services():
            print(f"{service.name}\t{service.source_type}\t{service.source_url or service.source_path}")
        return 0
    if args.services_command == "show":
        service = catalog.get_service(args.name)
        print(f"name: {service.name}")
        print(f"source_type: {service.source_type}")
        print(f"source_url: {service.source_url or '-'}")
        print(f"source_path: {service.source_path}")
        print(f"default_branch: {service.default_branch or '-'}")
        for environment in ("prod", "dev"):
            env = catalog.get_environment(service.name, environment)
            print(
                f"environment: {env.name}\tsubdomain={env.subdomain}\t"
                f"ref={env.current_ref or '-'}\tcommit={env.current_commit or '-'}"
            )
        return 0
    if args.services_command == "remove":
        removed = catalog.remove_service(args.name, delete_files=args.delete_files)
        print("removed" if removed else "not found")
        return 0 if removed else 1
    raise DeployerError("Unknown services command")


def _handle_env(args: argparse.Namespace, catalog: ServiceCatalog) -> int:
    if args.env_command == "list":
        env = catalog.get_environment(args.service, args.environment)
        for key, value in sorted(env.env_vars.items()):
            print(f"{key}={value}")
        return 0
    if args.env_command == "set":
        key, sep, value = args.assignment.partition("=")
        if not sep:
            raise DeployerError("Assignment must use KEY=value format")
        catalog.set_env(args.service, args.environment, key, value)
        print(f"set\t{args.service}\t{args.environment}\t{key}")
        return 0
    if args.env_command == "unset":
        catalog.unset_env(args.service, args.environment, args.key)
        print(f"unset\t{args.service}\t{args.environment}\t{args.key}")
        return 0
    if args.env_command == "render":
        print(catalog.render_env_file(args.service, args.environment))
        return 0
    raise DeployerError("Unknown env command")


def _print_service_history(catalog: ServiceCatalog, service_name: str, environment: str | None, limit: int) -> None:
    history = catalog.history(service_name, environment=environment, limit=limit)
    print(f"service: {history.service.name}")
    print(f"source: {history.service.source_type}\t{history.service.source_url or history.service.source_path}")
    for env in history.environments:
        print(
            f"current: {env.name}\tversion={env.current_version or '-'}\t"
            f"ref={env.current_ref or '-'}\tcommit={env.current_commit or '-'}\t"
            f"last_deployment={env.last_deployment_id or '-'}"
        )
    for record in history.records:
        print(_format_history_record(record))


def _format_history_record(record) -> str:
    return (
        f"{record.id}\t{record.environment}\t{record.action}\t"
        f"{record.status}\t{record.version or '-'}\t{record.started_at}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deployer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("project_dir", type=Path)
    validate.add_argument("--manifest", type=Path)

    render = subparsers.add_parser("render-override")
    render.add_argument("project_dir", type=Path)
    render.add_argument("--manifest", type=Path)
    render.add_argument("--environment", choices=["prod", "dev"], default="prod")

    deploy = subparsers.add_parser("deploy")
    deploy.add_argument("target")
    deploy.add_argument("--state-db", type=Path, default=Path(".deployer/state.db"))
    deploy.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    deploy.add_argument("--manifest", type=Path)
    deploy.add_argument("--version")
    deploy.add_argument("--ref")
    deploy.add_argument("--environment", choices=["prod", "dev"], default="prod")
    deploy.add_argument("--dry-run", action="store_true")

    stop = subparsers.add_parser("stop")
    stop.add_argument("target")
    stop.add_argument("--state-db", type=Path, default=Path(".deployer/state.db"))
    stop.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    stop.add_argument("--manifest", type=Path)
    stop.add_argument("--environment", choices=["prod", "dev"], default="prod")
    stop.add_argument("--dry-run", action="store_true")

    down = subparsers.add_parser("down")
    down.add_argument("target")
    down.add_argument("--state-db", type=Path, default=Path(".deployer/state.db"))
    down.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    down.add_argument("--manifest", type=Path)
    down.add_argument("--environment", choices=["prod", "dev"], default="prod")
    down.add_argument("--dry-run", action="store_true")

    restart = subparsers.add_parser("restart")
    restart.add_argument("target")
    restart.add_argument("--state-db", type=Path, default=Path(".deployer/state.db"))
    restart.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    restart.add_argument("--manifest", type=Path)
    restart.add_argument("--environment", choices=["prod", "dev"], default="prod")
    restart.add_argument("--dry-run", action="store_true")

    status = subparsers.add_parser("status")
    status.add_argument("target")
    status.add_argument("--state-db", type=Path, default=Path(".deployer/state.db"))
    status.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    status.add_argument("--manifest", type=Path)
    status.add_argument("--environment", choices=["prod", "dev"], default="prod")

    logs = subparsers.add_parser("logs")
    logs.add_argument("target")
    logs.add_argument("--state-db", type=Path, default=Path(".deployer/state.db"))
    logs.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    logs.add_argument("--manifest", type=Path)
    logs.add_argument("--environment", choices=["prod", "dev"], default="prod")
    logs.add_argument("--tail", type=int, default=200)

    history = subparsers.add_parser("history")
    history.add_argument("project")
    history.add_argument("--state-db", type=Path, default=Path(".deployer/state.db"))
    history.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    history.add_argument("--environment", choices=["prod", "dev"])
    history.add_argument("--limit", type=int, default=20)

    services = subparsers.add_parser("services")
    services.add_argument("--state-db", type=Path, default=Path(".deployer/state.db"))
    services.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    services_subparsers = services.add_subparsers(dest="services_command", required=True)

    services_add = services_subparsers.add_parser("add")
    _add_catalog_options(services_add)
    services_add.add_argument("name")
    services_add.add_argument("--git-url", required=True)
    services_add.add_argument("--default-branch")

    services_add_local = services_subparsers.add_parser("add-local")
    _add_catalog_options(services_add_local)
    services_add_local.add_argument("name")
    services_add_local.add_argument("--path", type=Path, required=True)

    services_list = services_subparsers.add_parser("list")
    _add_catalog_options(services_list)

    services_show = services_subparsers.add_parser("show")
    _add_catalog_options(services_show)
    services_show.add_argument("name")

    services_remove = services_subparsers.add_parser("remove")
    _add_catalog_options(services_remove)
    services_remove.add_argument("name")
    services_remove.add_argument("--delete-files", action="store_true")

    refs = subparsers.add_parser("refs")
    refs.add_argument("service")
    refs.add_argument("--state-db", type=Path, default=Path(".deployer/state.db"))
    refs.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)

    env = subparsers.add_parser("env")
    env.add_argument("--state-db", type=Path, default=Path(".deployer/state.db"))
    env.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR)
    env_subparsers = env.add_subparsers(dest="env_command", required=True)

    env_list = env_subparsers.add_parser("list")
    _add_catalog_options(env_list)
    env_list.add_argument("service")
    env_list.add_argument("environment", choices=["prod", "dev"])

    env_set = env_subparsers.add_parser("set")
    _add_catalog_options(env_set)
    env_set.add_argument("service")
    env_set.add_argument("environment", choices=["prod", "dev"])
    env_set.add_argument("assignment")

    env_unset = env_subparsers.add_parser("unset")
    _add_catalog_options(env_unset)
    env_unset.add_argument("service")
    env_unset.add_argument("environment", choices=["prod", "dev"])
    env_unset.add_argument("key")

    env_render = env_subparsers.add_parser("render")
    _add_catalog_options(env_render)
    env_render.add_argument("service")
    env_render.add_argument("environment", choices=["prod", "dev"])

    return parser


def _is_path_target(target: str) -> bool:
    return target.startswith(".") or target.startswith("/") or Path(target).exists()


def _is_service_target(target: str, state: StateStore) -> bool:
    return state.get_service(target) is not None


def _add_catalog_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-db", type=Path, default=argparse.SUPPRESS)
    parser.add_argument("--runtime-dir", type=Path, default=argparse.SUPPRESS)


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from deployer.engine import DeploymentEngine
from deployer.errors import DeployerError
from deployer.manifest import load_manifest
from deployer.override import render_override
from deployer.state import StateStore


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    try:
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
            result = engine.deploy(
                args.project_dir,
                version=args.version,
                dry_run=args.dry_run,
                manifest_path=args.manifest,
                environment=args.environment,
            )
            print(result.log)
            return 0 if result.status == "success" else 1
        if args.command == "stop":
            state = StateStore(args.state_db)
            engine = DeploymentEngine(state)
            result = engine.stop(
                args.project_dir,
                dry_run=args.dry_run,
                manifest_path=args.manifest,
                environment=args.environment,
            )
            print(result.log)
            return 0 if result.status == "success" else 1
        if args.command == "status":
            state = StateStore(args.state_db)
            engine = DeploymentEngine(state)
            result = engine.status(
                args.project_dir,
                manifest_path=args.manifest,
                environment=args.environment,
            )
            print(result.log, end="" if result.log.endswith("\n") else "\n")
            return 0 if result.status == "success" else 1
        if args.command == "history":
            state = StateStore(args.state_db)
            for record in state.history(args.project, environment=args.environment, limit=args.limit):
                print(
                    f"{record.id}\t{record.environment}\t{record.action}\t"
                    f"{record.status}\t{record.version or '-'}\t{record.started_at}"
                )
            return 0
    except DeployerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    parser.print_help()
    return 2


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
    deploy.add_argument("project_dir", type=Path)
    deploy.add_argument("--state-db", type=Path, default=Path(".deployer/state.db"))
    deploy.add_argument("--manifest", type=Path)
    deploy.add_argument("--version")
    deploy.add_argument("--environment", choices=["prod", "dev"], default="prod")
    deploy.add_argument("--dry-run", action="store_true")

    stop = subparsers.add_parser("stop")
    stop.add_argument("project_dir", type=Path)
    stop.add_argument("--state-db", type=Path, default=Path(".deployer/state.db"))
    stop.add_argument("--manifest", type=Path)
    stop.add_argument("--environment", choices=["prod", "dev"], default="prod")
    stop.add_argument("--dry-run", action="store_true")

    status = subparsers.add_parser("status")
    status.add_argument("project_dir", type=Path)
    status.add_argument("--state-db", type=Path, default=Path(".deployer/state.db"))
    status.add_argument("--manifest", type=Path)
    status.add_argument("--environment", choices=["prod", "dev"], default="prod")

    history = subparsers.add_parser("history")
    history.add_argument("project")
    history.add_argument("--state-db", type=Path, default=Path(".deployer/state.db"))
    history.add_argument("--environment", choices=["prod", "dev"])
    history.add_argument("--limit", type=int, default=20)

    return parser


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from deployer.catalog import ServiceCatalog
from deployer.config import load_config
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
        if args.command == "projects":
            state = StateStore(args.state_db)
            catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
            return _handle_projects(args, catalog)
        if args.command == "components":
            state = StateStore(args.state_db)
            catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
            return _handle_components(args, catalog)
        if args.command == "endpoints":
            state = StateStore(args.state_db)
            catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
            return _handle_endpoints(args, catalog)
        if args.command == "dependencies":
            state = StateStore(args.state_db)
            catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
            return _handle_dependencies(args, catalog)
        if args.command == "resources":
            state = StateStore(args.state_db)
            catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
            return _handle_resources(args, catalog)
        if args.command == "bindings":
            state = StateStore(args.state_db)
            catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
            return _handle_bindings(args, catalog)
        if args.command == "env":
            state = StateStore(args.state_db)
            catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
            return _handle_env(args, catalog)
        if args.command == "runtime-targets":
            state = StateStore(args.state_db)
            catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
            return _handle_runtime_targets(args, catalog)
        if args.command == "environments":
            state = StateStore(args.state_db)
            catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
            return _handle_environments(args, catalog)
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
            if args.project:
                catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
                result = catalog.deploy_project(
                    args.target,
                    args.project,
                    engine,
                    ref=args.ref,
                    version=args.version,
                    dry_run=args.dry_run,
                )
            elif _is_path_target(args.target):
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
            if args.project:
                catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
                result = catalog.stop_project(args.target, args.project, engine, dry_run=args.dry_run)
            elif _is_path_target(args.target):
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
            if args.project:
                catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
                result = catalog.down_project(args.target, args.project, engine, dry_run=args.dry_run)
            elif _is_path_target(args.target):
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
            if args.project:
                catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
                result = catalog.restart_project(args.target, args.project, engine, dry_run=args.dry_run)
            elif _is_path_target(args.target):
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
            if args.project:
                catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
                result = catalog.status_project(args.target, args.project, engine)
            elif _is_path_target(args.target):
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
            if args.project:
                catalog = ServiceCatalog(state, runtime_dir=args.runtime_dir)
                result = catalog.logs_project(args.target, args.project, engine, tail=args.tail)
            elif _is_path_target(args.target):
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
        for env in catalog.list_environments(service.name):
            print(
                f"environment: {env.name}\tsubdomain={env.subdomain}\t"
                f"url_prefix={env.url_prefix or '-'}\t"
                f"deploy_mode={env.deploy_mode}\t"
                f"ref={env.current_ref or '-'}\tcommit={env.current_commit or '-'}"
            )
        return 0
    if args.services_command == "remove":
        removed = catalog.remove_service(args.name, delete_files=args.delete_files)
        print("removed" if removed else "not found")
        return 0 if removed else 1
    raise DeployerError("Unknown services command")


def _handle_runtime_targets(args: argparse.Namespace, catalog: ServiceCatalog) -> int:
    if args.runtime_targets_command == "list":
        for env in catalog.list_environments(args.service):
            print(
                f"{env.name}\turl_prefix={env.url_prefix or '-'}\t"
                f"deploy_mode={env.deploy_mode}\t"
                f"deploy_source={env.deploy_source or '-'}\t"
                f"deploy_pattern={env.deploy_pattern or '-'}\t"
                f"pattern_type={env.deploy_pattern_type or '-'}\t"
                f"ref={env.current_ref or '-'}"
            )
        return 0
    if args.runtime_targets_command == "add":
        env = catalog.add_environment(args.service, args.name)
        print(f"added\t{args.service}\t{env.name}\turl_prefix={env.url_prefix or '-'}")
        return 0
    if args.runtime_targets_command == "remove":
        removed = catalog.remove_environment(args.service, args.name)
        print("removed" if removed else "not found")
        return 0 if removed else 1
    raise DeployerError("Unknown runtime-targets command")


def _handle_projects(args: argparse.Namespace, catalog: ServiceCatalog) -> int:
    if args.projects_command == "add-local":
        project = catalog.add_project_local(
            args.environment,
            args.name,
            args.path,
            default_ref=args.default_ref,
            compose_files=_project_compose_files(args),
            deploy_mode=args.deploy_mode,
            deploy_source=args.deploy_source,
            deploy_pattern=args.deploy_pattern,
            deploy_pattern_type=args.pattern_type,
        )
        print(f"added\t{project.environment}\t{project.name}\t{project.source_type}\t{project.source_path}")
        return 0
    if args.projects_command == "add":
        project = catalog.add_project_git(
            args.environment,
            args.name,
            args.git_url,
            default_ref=args.default_ref,
            compose_files=_project_compose_files(args),
            deploy_mode=args.deploy_mode,
            deploy_source=args.deploy_source,
            deploy_pattern=args.deploy_pattern,
            deploy_pattern_type=args.pattern_type,
        )
        print(f"added\t{project.environment}\t{project.name}\t{project.source_type}\t{project.source_url}")
        return 0
    if args.projects_command == "list":
        for project in catalog.list_projects(args.environment):
            print(
                f"{project.environment}\t{project.name}\t{project.source_type}\t"
                f"{project.source_url or project.source_path}\tref={project.current_ref or project.default_ref or '-'}"
            )
        return 0
    if args.projects_command == "show":
        config = catalog.project_config(args.environment, args.name)
        project = config.project
        print(f"environment: {project.environment}")
        print(f"name: {project.name}")
        print(f"source_type: {project.source_type}")
        print(f"source_url: {project.source_url or '-'}")
        print(f"source_path: {project.source_path}")
        print(f"default_ref: {project.default_ref or '-'}")
        print(f"compose_files: {', '.join(project.compose_files) or '-'}")
        print(f"deploy_mode: {project.deploy_mode}")
        print(f"deploy_source: {project.deploy_source or '-'}")
        print(f"deploy_pattern: {project.deploy_pattern or '-'}")
        print(f"current_ref: {project.current_ref or '-'}")
        print(f"current_commit: {project.current_commit or '-'}")
        for component in config.components:
            print(f"component: {component.name}\tmode={component.mode}\tport={component.port or '-'}")
        for endpoint in config.endpoints:
            print(
                f"endpoint: {endpoint.name}\tcomponent={endpoint.component}\t"
                f"subdomain={endpoint.subdomain or '-'}\tauth={endpoint.auth}"
            )
        for dependency in config.dependencies:
            print(f"dependency: {dependency.name}\ttype={dependency.type}\ttarget={dependency.target}")
        for binding in config.resource_bindings:
            print(f"binding: {binding.name}\tresource={binding.resource_name}\tcomponent={binding.component or '-'}")
        return 0
    if args.projects_command == "remove":
        removed = catalog.remove_project(args.environment, args.name, delete_files=args.delete_files)
        print("removed" if removed else "not found")
        return 0 if removed else 1
    if args.projects_command == "env-list":
        project = catalog.get_project(args.environment, args.name)
        for key, value in sorted(project.env_vars.items()):
            print(f"{key}={value}")
        return 0
    if args.projects_command == "env-set":
        key, sep, value = args.assignment.partition("=")
        if not sep:
            raise DeployerError("Assignment must use KEY=value format")
        catalog.set_project_env(args.environment, args.name, key, value)
        print(f"set\t{args.environment}\t{args.name}\t{key}")
        return 0
    if args.projects_command == "env-unset":
        catalog.unset_project_env(args.environment, args.name, args.key)
        print(f"unset\t{args.environment}\t{args.name}\t{args.key}")
        return 0
    if args.projects_command == "env-render":
        print(catalog.render_project_env_file(args.environment, args.name))
        return 0
    raise DeployerError("Unknown projects command")


def _handle_components(args: argparse.Namespace, catalog: ServiceCatalog) -> int:
    if args.components_command == "add":
        component = catalog.add_component(
            args.environment,
            args.project,
            args.name,
            mode=args.mode,
            compose_service=args.compose_service,
            build_context=args.build_context,
            dockerfile=args.dockerfile,
            image=args.image,
            command=args.component_command_value,
            port=args.port,
        )
        print(f"added\t{args.environment}\t{args.project}\t{component.name}\t{component.mode}")
        return 0
    if args.components_command == "list":
        for component in catalog.state.list_components(args.environment, args.project):
            print(
                f"{component.name}\tmode={component.mode}\tcompose_service={component.compose_service or '-'}\t"
                f"build_context={component.build_context or '-'}\timage={component.image or '-'}\tport={component.port or '-'}"
            )
        return 0
    raise DeployerError("Unknown components command")


def _handle_endpoints(args: argparse.Namespace, catalog: ServiceCatalog) -> int:
    if args.endpoints_command == "add":
        endpoint = catalog.add_endpoint(
            args.environment,
            args.project,
            args.name,
            args.component,
            args.port,
            host=args.host,
            subdomain=args.subdomain,
            path_prefix=args.path_prefix,
            auth=args.auth,
            middlewares=tuple(args.middleware or ()),
            healthcheck_path=args.health_path,
        )
        print(f"added\t{args.environment}\t{args.project}\t{endpoint.name}\t{endpoint.component}\t{endpoint.port}")
        return 0
    if args.endpoints_command == "list":
        for endpoint in catalog.state.list_endpoints(args.environment, args.project):
            print(
                f"{endpoint.name}\tcomponent={endpoint.component}\tport={endpoint.port}\t"
                f"host={endpoint.host or '-'}\tsubdomain={endpoint.subdomain or '-'}\tauth={endpoint.auth}"
            )
        return 0
    raise DeployerError("Unknown endpoints command")


def _handle_dependencies(args: argparse.Namespace, catalog: ServiceCatalog) -> int:
    if args.dependencies_command == "add":
        outputs = _parse_assignments(args.output or [])
        dependency = catalog.add_dependency(
            args.environment,
            args.project,
            args.name,
            args.type,
            args.target,
            outputs=outputs,
        )
        print(f"added\t{args.environment}\t{args.project}\t{dependency.name}\t{dependency.type}\t{dependency.target}")
        return 0
    if args.dependencies_command == "list":
        for dependency in catalog.state.list_dependencies(args.environment, args.project):
            outputs = ",".join(f"{key}={value}" for key, value in sorted(dependency.outputs.items())) or "-"
            print(f"{dependency.name}\ttype={dependency.type}\ttarget={dependency.target}\toutputs={outputs}")
        return 0
    raise DeployerError("Unknown dependencies command")


def _handle_resources(args: argparse.Namespace, catalog: ServiceCatalog) -> int:
    if args.resources_command == "add":
        resource = catalog.add_environment_resource(
            args.environment,
            args.name,
            args.type,
            config=_parse_assignments(args.config or []),
        )
        print(f"added\t{resource.environment}\t{resource.name}\t{resource.type}")
        return 0
    if args.resources_command == "list":
        for resource in catalog.state.list_environment_resources(args.environment):
            print(f"{resource.name}\ttype={resource.type}\tstatus={resource.status}")
        return 0
    raise DeployerError("Unknown resources command")


def _handle_bindings(args: argparse.Namespace, catalog: ServiceCatalog) -> int:
    if args.bindings_command == "add":
        binding = catalog.bind_project_resource(
            args.environment,
            args.project,
            args.name,
            args.resource,
            component=args.component,
            config=_parse_assignments(args.config or []),
            outputs=_parse_assignments(args.output or []),
            mounts=tuple(_parse_mount(value) for value in (args.mount or [])),
        )
        print(f"added\t{binding.environment}\t{binding.project}\t{binding.name}\tresource={binding.resource_name}")
        return 0
    if args.bindings_command == "list":
        for binding in catalog.state.list_project_resource_bindings(args.environment, args.project):
            outputs = ",".join(f"{key}={value}" for key, value in sorted(binding.outputs.items())) or "-"
            mounts = ",".join(f"{item.get('source')}:{item.get('target')}" for item in binding.mounts) or "-"
            print(
                f"{binding.name}\tresource={binding.resource_name}\tcomponent={binding.component or '-'}\t"
                f"outputs={outputs}\tmounts={mounts}"
            )
        return 0
    if args.bindings_command == "plan":
        plan = catalog.plan_project_resource_binding(args.environment, args.project, args.name)
        _print_resource_plan(plan)
        return 0
    if args.bindings_command == "apply":
        plan, log = catalog.apply_project_resource_binding(
            args.environment,
            args.project,
            args.name,
            dry_run=args.dry_run,
        )
        _print_resource_plan(plan)
        if log:
            print(log)
        return 0
    raise DeployerError("Unknown bindings command")


def _handle_environments(args: argparse.Namespace, catalog: ServiceCatalog) -> int:
    if args.environments_command == "list":
        for profile in catalog.list_environment_profiles():
            print(
                f"{profile.name}\turl_prefix={profile.url_prefix or '-'}\t"
                f"deploy_mode={profile.deploy_mode}\t"
                f"deploy_source={profile.deploy_source or '-'}\t"
                f"deploy_pattern={profile.deploy_pattern or '-'}\t"
                f"pattern_type={profile.deploy_pattern_type or '-'}"
            )
        return 0
    if args.environments_command == "add":
        profile = catalog.add_environment_profile(
            args.name,
            url_prefix=args.url_prefix,
            deploy_mode=args.deploy_mode,
            deploy_source=args.deploy_source,
            deploy_pattern=args.deploy_pattern,
            deploy_pattern_type=args.pattern_type,
        )
        print(f"added\t{profile.name}\turl_prefix={profile.url_prefix or '-'}")
        return 0
    if args.environments_command == "update":
        profile = catalog.update_environment_profile(
            args.name,
            url_prefix=args.url_prefix,
            deploy_mode=args.deploy_mode,
            deploy_source=args.deploy_source,
            deploy_pattern=args.deploy_pattern,
            deploy_pattern_type=args.pattern_type,
        )
        print(f"updated\t{profile.name}\turl_prefix={profile.url_prefix or '-'}\tdeploy_mode={profile.deploy_mode}")
        return 0
    if args.environments_command == "remove":
        removed = catalog.remove_environment_profile(args.name)
        print("removed" if removed else "not found")
        return 0 if removed else 1
    raise DeployerError("Unknown environments command")


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


def _print_resource_plan(plan) -> None:
    print(f"binding: {plan.environment}/{plan.project}/{plan.binding}")
    print(f"resource: {plan.resource}\ttype={plan.resource_type}")
    print("config:")
    for key, value in sorted(plan.config.items()):
        safe_value = "***" if key == "password" and value else value
        print(f"  {key}={safe_value}")
    print("outputs:")
    for key, value in sorted(plan.outputs.items()):
        print(f"  {key}={_redact_output_value(key, value)}")
    print("steps:")
    for step in plan.steps:
        print(f"  - {step}")
    if plan.warnings:
        print("warnings:")
        for warning in plan.warnings:
            print(f"  - {warning}")


def _redact_output_value(key: str, value: str) -> str:
    if "PASSWORD" in key.upper():
        return "***"
    if key.upper().endswith("_URL") and "://" in value and "@" in value:
        scheme, rest = value.split("://", 1)
        auth, target = rest.split("@", 1)
        if ":" in auth:
            user, _ = auth.split(":", 1)
            return f"{scheme}://{user}:***@{target}"
    return value


def _parse_assignments(assignments: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for assignment in assignments:
        key, sep, value = assignment.partition("=")
        if not sep:
            raise DeployerError("Assignment must use KEY=value format")
        values[key] = value
    return values


def _parse_mount(value: str) -> dict:
    source, sep, rest = value.partition(":")
    if not sep:
        raise DeployerError("Mount must use SOURCE:TARGET[:ro] format")
    target, _, mode = rest.partition(":")
    mount = {"source": source, "target": target, "type": "volume"}
    if mode == "ro":
        mount["read_only"] = True
    return mount


def _project_compose_files(args: argparse.Namespace) -> tuple[str, ...]:
    if args.no_compose_file:
        return ()
    return tuple(args.compose_file or ["docker-compose.yml"])


def _parser() -> argparse.ArgumentParser:
    config = load_config()
    parser = argparse.ArgumentParser(prog="deployer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("project_dir", type=Path)
    validate.add_argument("--manifest", type=Path)

    render = subparsers.add_parser("render-override")
    render.add_argument("project_dir", type=Path)
    render.add_argument("--manifest", type=Path)
    render.add_argument("--environment", default="prod")

    deploy = subparsers.add_parser("deploy")
    deploy.add_argument("target")
    deploy.add_argument("project", nargs="?")
    deploy.add_argument("--state-db", type=Path, default=config.state_db)
    deploy.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)
    deploy.add_argument("--manifest", type=Path)
    deploy.add_argument("--version")
    deploy.add_argument("--ref")
    deploy.add_argument("--environment", default="prod")
    deploy.add_argument("--dry-run", action="store_true")

    stop = subparsers.add_parser("stop")
    stop.add_argument("target")
    stop.add_argument("project", nargs="?")
    stop.add_argument("--state-db", type=Path, default=config.state_db)
    stop.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)
    stop.add_argument("--manifest", type=Path)
    stop.add_argument("--environment", default="prod")
    stop.add_argument("--dry-run", action="store_true")

    down = subparsers.add_parser("down")
    down.add_argument("target")
    down.add_argument("project", nargs="?")
    down.add_argument("--state-db", type=Path, default=config.state_db)
    down.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)
    down.add_argument("--manifest", type=Path)
    down.add_argument("--environment", default="prod")
    down.add_argument("--dry-run", action="store_true")

    restart = subparsers.add_parser("restart")
    restart.add_argument("target")
    restart.add_argument("project", nargs="?")
    restart.add_argument("--state-db", type=Path, default=config.state_db)
    restart.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)
    restart.add_argument("--manifest", type=Path)
    restart.add_argument("--environment", default="prod")
    restart.add_argument("--dry-run", action="store_true")

    status = subparsers.add_parser("status")
    status.add_argument("target")
    status.add_argument("project", nargs="?")
    status.add_argument("--state-db", type=Path, default=config.state_db)
    status.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)
    status.add_argument("--manifest", type=Path)
    status.add_argument("--environment", default="prod")

    logs = subparsers.add_parser("logs")
    logs.add_argument("target")
    logs.add_argument("project", nargs="?")
    logs.add_argument("--state-db", type=Path, default=config.state_db)
    logs.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)
    logs.add_argument("--manifest", type=Path)
    logs.add_argument("--environment", default="prod")
    logs.add_argument("--tail", type=int, default=200)

    history = subparsers.add_parser("history")
    history.add_argument("project")
    history.add_argument("--state-db", type=Path, default=config.state_db)
    history.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)
    history.add_argument("--environment")
    history.add_argument("--limit", type=int, default=20)

    services = subparsers.add_parser("services")
    services.add_argument("--state-db", type=Path, default=config.state_db)
    services.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)
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
    refs.add_argument("--state-db", type=Path, default=config.state_db)
    refs.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)

    environments = subparsers.add_parser("environments")
    environments.add_argument("--state-db", type=Path, default=config.state_db)
    environments.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)
    environments_subparsers = environments.add_subparsers(dest="environments_command", required=True)

    environments_list = environments_subparsers.add_parser("list")
    _add_catalog_options(environments_list)

    environments_add = environments_subparsers.add_parser("add")
    _add_catalog_options(environments_add)
    environments_add.add_argument("name")
    environments_add.add_argument("--url-prefix")
    environments_add.add_argument("--deploy-mode", default="manual")
    environments_add.add_argument("--deploy-source")
    environments_add.add_argument("--deploy-pattern")
    environments_add.add_argument("--pattern-type", dest="pattern_type")

    environments_update = environments_subparsers.add_parser("update")
    _add_catalog_options(environments_update)
    environments_update.add_argument("name")
    environments_update.add_argument("--url-prefix")
    environments_update.add_argument("--deploy-mode")
    environments_update.add_argument("--deploy-source")
    environments_update.add_argument("--deploy-pattern")
    environments_update.add_argument("--pattern-type", dest="pattern_type")

    environments_remove = environments_subparsers.add_parser("remove")
    _add_catalog_options(environments_remove)
    environments_remove.add_argument("name")

    projects = subparsers.add_parser("projects")
    projects.add_argument("--state-db", type=Path, default=config.state_db)
    projects.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)
    projects_subparsers = projects.add_subparsers(dest="projects_command", required=True)

    projects_add = projects_subparsers.add_parser("add")
    _add_catalog_options(projects_add)
    projects_add.add_argument("environment")
    projects_add.add_argument("name")
    projects_add.add_argument("--git-url", required=True)
    projects_add.add_argument("--default-ref")
    projects_add.add_argument("--compose-file", action="append")
    projects_add.add_argument("--no-compose-file", action="store_true")
    _add_deploy_policy_options(projects_add)

    projects_add_local = projects_subparsers.add_parser("add-local")
    _add_catalog_options(projects_add_local)
    projects_add_local.add_argument("environment")
    projects_add_local.add_argument("name")
    projects_add_local.add_argument("--path", type=Path, required=True)
    projects_add_local.add_argument("--default-ref")
    projects_add_local.add_argument("--compose-file", action="append")
    projects_add_local.add_argument("--no-compose-file", action="store_true")
    _add_deploy_policy_options(projects_add_local)

    projects_list = projects_subparsers.add_parser("list")
    _add_catalog_options(projects_list)
    projects_list.add_argument("environment", nargs="?")

    projects_show = projects_subparsers.add_parser("show")
    _add_catalog_options(projects_show)
    projects_show.add_argument("environment")
    projects_show.add_argument("name")

    projects_remove = projects_subparsers.add_parser("remove")
    _add_catalog_options(projects_remove)
    projects_remove.add_argument("environment")
    projects_remove.add_argument("name")
    projects_remove.add_argument("--delete-files", action="store_true")

    projects_env_list = projects_subparsers.add_parser("env-list")
    _add_catalog_options(projects_env_list)
    projects_env_list.add_argument("environment")
    projects_env_list.add_argument("name")

    projects_env_set = projects_subparsers.add_parser("env-set")
    _add_catalog_options(projects_env_set)
    projects_env_set.add_argument("environment")
    projects_env_set.add_argument("name")
    projects_env_set.add_argument("assignment")

    projects_env_unset = projects_subparsers.add_parser("env-unset")
    _add_catalog_options(projects_env_unset)
    projects_env_unset.add_argument("environment")
    projects_env_unset.add_argument("name")
    projects_env_unset.add_argument("key")

    projects_env_render = projects_subparsers.add_parser("env-render")
    _add_catalog_options(projects_env_render)
    projects_env_render.add_argument("environment")
    projects_env_render.add_argument("name")

    components = subparsers.add_parser("components")
    components.add_argument("--state-db", type=Path, default=config.state_db)
    components.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)
    components_subparsers = components.add_subparsers(dest="components_command", required=True)

    components_add = components_subparsers.add_parser("add")
    _add_catalog_options(components_add)
    components_add.add_argument("environment")
    components_add.add_argument("project")
    components_add.add_argument("name")
    components_add.add_argument("--mode", default="compose", choices=["compose", "build", "image"])
    components_add.add_argument("--compose-service")
    components_add.add_argument("--build-context")
    components_add.add_argument("--dockerfile")
    components_add.add_argument("--image")
    components_add.add_argument("--command", dest="component_command_value")
    components_add.add_argument("--port", type=int)

    components_list = components_subparsers.add_parser("list")
    _add_catalog_options(components_list)
    components_list.add_argument("environment")
    components_list.add_argument("project")

    endpoints = subparsers.add_parser("endpoints")
    endpoints.add_argument("--state-db", type=Path, default=config.state_db)
    endpoints.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)
    endpoints_subparsers = endpoints.add_subparsers(dest="endpoints_command", required=True)

    endpoints_add = endpoints_subparsers.add_parser("add")
    _add_catalog_options(endpoints_add)
    endpoints_add.add_argument("environment")
    endpoints_add.add_argument("project")
    endpoints_add.add_argument("name")
    endpoints_add.add_argument("component")
    endpoints_add.add_argument("--port", type=int, required=True)
    endpoints_add.add_argument("--host")
    endpoints_add.add_argument("--subdomain")
    endpoints_add.add_argument("--path-prefix")
    endpoints_add.add_argument("--auth", default="none", choices=["none", "sso"])
    endpoints_add.add_argument("--middleware", action="append")
    endpoints_add.add_argument("--health-path")

    endpoints_list = endpoints_subparsers.add_parser("list")
    _add_catalog_options(endpoints_list)
    endpoints_list.add_argument("environment")
    endpoints_list.add_argument("project")

    dependencies = subparsers.add_parser("dependencies")
    dependencies.add_argument("--state-db", type=Path, default=config.state_db)
    dependencies.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)
    dependencies_subparsers = dependencies.add_subparsers(dest="dependencies_command", required=True)

    dependencies_add = dependencies_subparsers.add_parser("add")
    _add_catalog_options(dependencies_add)
    dependencies_add.add_argument("environment")
    dependencies_add.add_argument("project")
    dependencies_add.add_argument("name")
    dependencies_add.add_argument("--type", required=True)
    dependencies_add.add_argument("--target", required=True)
    dependencies_add.add_argument("--output", action="append")

    dependencies_list = dependencies_subparsers.add_parser("list")
    _add_catalog_options(dependencies_list)
    dependencies_list.add_argument("environment")
    dependencies_list.add_argument("project")

    resources = subparsers.add_parser("resources")
    resources.add_argument("--state-db", type=Path, default=config.state_db)
    resources.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)
    resources_subparsers = resources.add_subparsers(dest="resources_command", required=True)

    resources_add = resources_subparsers.add_parser("add")
    _add_catalog_options(resources_add)
    resources_add.add_argument("environment")
    resources_add.add_argument("name")
    resources_add.add_argument("--type", required=True)
    resources_add.add_argument("--config", action="append")

    resources_list = resources_subparsers.add_parser("list")
    _add_catalog_options(resources_list)
    resources_list.add_argument("environment")

    bindings = subparsers.add_parser("bindings")
    bindings.add_argument("--state-db", type=Path, default=config.state_db)
    bindings.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)
    bindings_subparsers = bindings.add_subparsers(dest="bindings_command", required=True)

    bindings_add = bindings_subparsers.add_parser("add")
    _add_catalog_options(bindings_add)
    bindings_add.add_argument("environment")
    bindings_add.add_argument("project")
    bindings_add.add_argument("name")
    bindings_add.add_argument("--resource", required=True)
    bindings_add.add_argument("--component")
    bindings_add.add_argument("--config", action="append")
    bindings_add.add_argument("--output", action="append")
    bindings_add.add_argument("--mount", action="append")

    bindings_list = bindings_subparsers.add_parser("list")
    _add_catalog_options(bindings_list)
    bindings_list.add_argument("environment")
    bindings_list.add_argument("project")

    bindings_plan = bindings_subparsers.add_parser("plan")
    _add_catalog_options(bindings_plan)
    bindings_plan.add_argument("environment")
    bindings_plan.add_argument("project")
    bindings_plan.add_argument("name")

    bindings_apply = bindings_subparsers.add_parser("apply")
    _add_catalog_options(bindings_apply)
    bindings_apply.add_argument("environment")
    bindings_apply.add_argument("project")
    bindings_apply.add_argument("name")
    bindings_apply.add_argument("--dry-run", action="store_true")

    runtime_targets = subparsers.add_parser("runtime-targets")
    runtime_targets.add_argument("--state-db", type=Path, default=config.state_db)
    runtime_targets.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)
    runtime_targets_subparsers = runtime_targets.add_subparsers(dest="runtime_targets_command", required=True)

    runtime_targets_list = runtime_targets_subparsers.add_parser("list")
    _add_catalog_options(runtime_targets_list)
    runtime_targets_list.add_argument("service")

    runtime_targets_add = runtime_targets_subparsers.add_parser("add")
    _add_catalog_options(runtime_targets_add)
    runtime_targets_add.add_argument("service")
    runtime_targets_add.add_argument("name")

    runtime_targets_remove = runtime_targets_subparsers.add_parser("remove")
    _add_catalog_options(runtime_targets_remove)
    runtime_targets_remove.add_argument("service")
    runtime_targets_remove.add_argument("name")

    env = subparsers.add_parser("env")
    env.add_argument("--state-db", type=Path, default=config.state_db)
    env.add_argument("--runtime-dir", type=Path, default=config.runtime_dir)
    env_subparsers = env.add_subparsers(dest="env_command", required=True)

    env_list = env_subparsers.add_parser("list")
    _add_catalog_options(env_list)
    env_list.add_argument("service")
    env_list.add_argument("environment")

    env_set = env_subparsers.add_parser("set")
    _add_catalog_options(env_set)
    env_set.add_argument("service")
    env_set.add_argument("environment")
    env_set.add_argument("assignment")

    env_unset = env_subparsers.add_parser("unset")
    _add_catalog_options(env_unset)
    env_unset.add_argument("service")
    env_unset.add_argument("environment")
    env_unset.add_argument("key")

    env_render = env_subparsers.add_parser("render")
    _add_catalog_options(env_render)
    env_render.add_argument("service")
    env_render.add_argument("environment")

    return parser


def _is_path_target(target: str) -> bool:
    return target.startswith(".") or target.startswith("/") or Path(target).exists()


def _is_service_target(target: str, state: StateStore) -> bool:
    return state.get_service(target) is not None


def _add_catalog_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-db", type=Path, default=argparse.SUPPRESS)
    parser.add_argument("--runtime-dir", type=Path, default=argparse.SUPPRESS)


def _add_deploy_policy_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--deploy-mode", default="manual")
    parser.add_argument("--deploy-source")
    parser.add_argument("--deploy-pattern")
    parser.add_argument("--pattern-type", dest="pattern_type")


if __name__ == "__main__":
    raise SystemExit(main())

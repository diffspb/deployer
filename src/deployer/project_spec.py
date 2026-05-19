from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from deployer.platform import DEFAULT_PLATFORM, Platform
from deployer.state import (
    EnvironmentProfileRecord,
    EnvironmentProjectRecord,
    ProjectComponentRecord,
    ProjectDependencyRecord,
    ProjectEndpointRecord,
    ProjectResourceBindingRecord,
)


@dataclass(frozen=True)
class ProjectSpec:
    environment: str
    name: str
    source_dir: Path
    compose_files: tuple[str, ...]
    components: tuple["ComponentSpec", ...]
    endpoints: tuple["EndpointSpec", ...]
    env_file: str | None
    url_prefix: str

    @property
    def deployment_key(self) -> str:
        return f"{self.environment}/{self.name}"

    @property
    def compose_project(self) -> str:
        return _sanitize(f"{self.environment}-{self.name}")


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    service: str
    mode: str
    build_context: str | None
    dockerfile: str | None
    image: str | None
    command: str | None
    port: int | None
    env_vars: dict[str, str]
    mounts: tuple["MountSpec", ...] = ()


@dataclass(frozen=True)
class EndpointSpec:
    name: str
    component: str
    port: int
    host: str | None
    subdomain: str | None
    path_prefix: str | None
    auth: str
    middlewares: tuple[str, ...]
    healthcheck_path: str | None


@dataclass(frozen=True)
class MountSpec:
    source: str
    target: str
    type: str = "volume"
    read_only: bool = False
    external: bool = False


def build_project_spec(
    project: EnvironmentProjectRecord,
    profile: EnvironmentProfileRecord,
    components: tuple[ProjectComponentRecord, ...],
    endpoints: tuple[ProjectEndpointRecord, ...],
    dependencies: tuple[ProjectDependencyRecord, ...],
    resource_bindings: tuple[ProjectResourceBindingRecord, ...] = (),
    env_file: str | None = None,
) -> ProjectSpec:
    del dependencies
    mounts_by_component = _mounts_by_component(resource_bindings)
    component_specs = tuple(_component_spec(component, mounts_by_component.get(component.name, ())) for component in components)
    endpoint_specs = tuple(_endpoint_spec(endpoint) for endpoint in endpoints)
    return ProjectSpec(
        environment=project.environment,
        name=project.name,
        source_dir=Path(project.source_path),
        compose_files=tuple(project.compose_files),
        components=component_specs,
        endpoints=endpoint_specs,
        env_file=env_file,
        url_prefix=profile.url_prefix,
    )


def build_project_override(spec: ProjectSpec, platform: Platform = DEFAULT_PLATFORM) -> dict:
    services: dict[str, dict] = {}
    volumes: dict[str, dict] = {}
    components_by_name = {component.name: component for component in spec.components}
    endpoints_by_component: dict[str, list[EndpointSpec]] = {}
    for endpoint in spec.endpoints:
        endpoints_by_component.setdefault(endpoint.component, []).append(endpoint)

    for component in spec.components:
        service_config = _base_service_config(component, spec, platform)
        labels = ["traefik.enable=true"]
        for endpoint in endpoints_by_component.get(component.name, []):
            labels.extend(_endpoint_labels(spec, endpoint, platform))
        if labels:
            service_config["labels"] = labels
        services[component.service] = service_config
        for mount in component.mounts:
            if mount.type == "volume":
                volumes[mount.source] = {"external": True} if mount.external else {}

    for endpoint in spec.endpoints:
        if endpoint.component not in components_by_name:
            raise ValueError(f"Endpoint references unknown component: {endpoint.component}")

    override = {
        "services": services,
        "networks": {
            platform.network: {
                "external": True,
            },
        },
    }
    if volumes:
        override["volumes"] = volumes
    return override


def render_project_override(spec: ProjectSpec, platform: Platform = DEFAULT_PLATFORM) -> str:
    return yaml.safe_dump(build_project_override(spec, platform), sort_keys=False)


def write_project_override(
    spec: ProjectSpec,
    output_dir: Path,
    platform: Platform = DEFAULT_PLATFORM,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{spec.environment}.override.yml"
    path.write_text(render_project_override(spec, platform))
    return path


def project_compose_command(
    spec: ProjectSpec,
    override_path: Path,
    action: str = "up",
    tail: int = 200,
    env_file: str | None = None,
) -> list[str]:
    command = ["docker", "compose", "-p", spec.compose_project]
    effective_env_file = env_file or spec.env_file
    if effective_env_file:
        command.extend(["--env-file", effective_env_file])
    for file in spec.compose_files:
        command.extend(["-f", file])
    command.extend(["-f", str(override_path)])
    if action == "up":
        command.extend(["up", "-d", "--build", "--force-recreate"])
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


def project_route_host(
    spec: ProjectSpec,
    endpoint: EndpointSpec,
    platform: Platform = DEFAULT_PLATFORM,
) -> str:
    if endpoint.host:
        return endpoint.host
    if not endpoint.subdomain:
        raise ValueError(f"Endpoint {endpoint.name} must define host or subdomain")
    prefix = endpoint.subdomain
    if spec.url_prefix:
        prefix = f"{prefix}.{spec.url_prefix}"
    return f"{prefix}.{platform.domain}"


def _component_spec(component: ProjectComponentRecord, mounts: tuple[MountSpec, ...] = ()) -> ComponentSpec:
    return ComponentSpec(
        name=component.name,
        service=component.compose_service or component.name,
        mode=component.mode,
        build_context=component.build_context,
        dockerfile=component.dockerfile,
        image=component.image,
        command=component.command,
        port=component.port,
        env_vars=dict(component.env_vars),
        mounts=mounts,
    )


def _endpoint_spec(endpoint: ProjectEndpointRecord) -> EndpointSpec:
    return EndpointSpec(
        name=endpoint.name,
        component=endpoint.component,
        port=endpoint.port,
        host=endpoint.host,
        subdomain=endpoint.subdomain,
        path_prefix=endpoint.path_prefix,
        auth=endpoint.auth,
        middlewares=tuple(endpoint.middlewares),
        healthcheck_path=endpoint.healthcheck_path,
    )


def _base_service_config(component: ComponentSpec, spec: ProjectSpec, platform: Platform) -> dict:
    service_config: dict = {
        "networks": [platform.network],
    }
    if spec.env_file:
        service_config["env_file"] = spec.env_file
    if component.env_vars:
        service_config["environment"] = dict(sorted(component.env_vars.items()))
    if component.mode == "build":
        build_config: dict = {"context": component.build_context or "."}
        if component.dockerfile:
            build_config["dockerfile"] = component.dockerfile
        service_config["build"] = build_config
    if component.mode == "image" and component.image:
        service_config["image"] = component.image
    if component.command:
        service_config["command"] = component.command
    if component.mounts:
        service_config["volumes"] = [_mount_value(mount) for mount in component.mounts]
    return service_config


def _mounts_by_component(bindings: tuple[ProjectResourceBindingRecord, ...]) -> dict[str, tuple[MountSpec, ...]]:
    grouped: dict[str, list[MountSpec]] = {}
    for binding in bindings:
        if not binding.component:
            continue
        for mount in binding.mounts:
            spec = _mount_spec(mount)
            grouped.setdefault(binding.component, []).append(spec)
    return {component: tuple(mounts) for component, mounts in grouped.items()}


def _mount_spec(raw: dict) -> MountSpec:
    return MountSpec(
        source=str(raw["source"]),
        target=str(raw["target"]),
        type=str(raw.get("type") or "volume"),
        read_only=bool(raw.get("read_only") or raw.get("readonly")),
        external=bool(raw.get("external")),
    )


def _mount_value(mount: MountSpec) -> str:
    suffix = ":ro" if mount.read_only else ""
    return f"{mount.source}:{mount.target}{suffix}"


def _endpoint_labels(spec: ProjectSpec, endpoint: EndpointSpec, platform: Platform) -> list[str]:
    router = _sanitize(f"{spec.environment}-{spec.name}-{endpoint.name}")
    service = router
    labels = [
        f"traefik.http.routers.{router}.rule={_rule(spec, endpoint, platform)}",
        f"traefik.http.routers.{router}.entrypoints={platform.entrypoint}",
        f"traefik.http.routers.{router}.tls.certresolver={platform.certresolver}",
        f"traefik.http.routers.{router}.service={service}",
        f"traefik.http.services.{service}.loadbalancer.server.port={endpoint.port}",
    ]
    middlewares = list(endpoint.middlewares)
    if endpoint.auth == "sso":
        middlewares = list(platform.sso_middlewares) + middlewares
    if middlewares:
        labels.append(f"traefik.http.routers.{router}.middlewares={','.join(middlewares)}")
    return labels


def _rule(spec: ProjectSpec, endpoint: EndpointSpec, platform: Platform) -> str:
    parts = [f"Host(`{project_route_host(spec, endpoint, platform)}`)"]
    if endpoint.path_prefix:
        parts.append(f"PathPrefix(`{endpoint.path_prefix}`)")
    return " && ".join(parts)


def _sanitize(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")

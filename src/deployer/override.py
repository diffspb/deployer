from __future__ import annotations

from pathlib import Path

import yaml

from deployer.manifest import Manifest, Route
from deployer.platform import DEFAULT_PLATFORM, Platform


def build_override(
    manifest: Manifest,
    platform: Platform = DEFAULT_PLATFORM,
    environment: str = "prod",
) -> dict:
    labels: list[str] = ["traefik.enable=true"]

    for route in manifest.routes:
        labels.extend(_route_labels(manifest, route, platform, environment))

    service_config: dict = {
        "labels": labels,
        "networks": [platform.network],
    }
    if manifest.env_file:
        service_config["env_file"] = manifest.env_file

    return {
        "services": {
            manifest.service: service_config,
        },
        "networks": {
            platform.network: {
                "external": True,
            },
        },
    }


def render_override(
    manifest: Manifest,
    platform: Platform = DEFAULT_PLATFORM,
    environment: str = "prod",
) -> str:
    return yaml.safe_dump(build_override(manifest, platform, environment), sort_keys=False)


def write_override(
    project_dir: Path,
    manifest: Manifest,
    platform: Platform = DEFAULT_PLATFORM,
    environment: str = "prod",
) -> Path:
    deployer_dir = project_dir / ".deployer"
    deployer_dir.mkdir(exist_ok=True)
    path = deployer_dir / "docker-compose.override.yml"
    path.write_text(render_override(manifest, platform, environment))
    return path


def _route_labels(manifest: Manifest, route: Route, platform: Platform, environment: str) -> list[str]:
    base_router = route.name or manifest.name
    router = base_router if environment == "prod" else f"{base_router}-{environment}"
    service = router
    labels = [
        f"traefik.http.routers.{router}.rule={_rule(route, platform, environment)}",
        f"traefik.http.routers.{router}.entrypoints={platform.entrypoint}",
        f"traefik.http.routers.{router}.tls.certresolver={platform.certresolver}",
        f"traefik.http.routers.{router}.service={service}",
        f"traefik.http.services.{service}.loadbalancer.server.port={manifest.port}",
    ]

    middlewares = list(route.middlewares)
    if route.auth == "sso":
        middlewares = list(platform.sso_middlewares) + middlewares
    if middlewares:
        labels.append(f"traefik.http.routers.{router}.middlewares={','.join(middlewares)}")
    if route.priority is not None:
        labels.append(f"traefik.http.routers.{router}.priority={route.priority}")
    return labels


def route_host(route: Route, platform: Platform = DEFAULT_PLATFORM, environment: str = "prod") -> str:
    if route.host:
        return route.host
    prefix = route.subdomain
    if environment != "prod":
        prefix = f"{prefix}.{environment}"
    return f"{prefix}.{platform.domain}"


def _rule(route: Route, platform: Platform, environment: str) -> str:
    parts = [f"Host(`{route_host(route, platform, environment)}`)"]
    if route.path_prefix:
        parts.append(f"PathPrefix(`{route.path_prefix}`)")
    if route.exclude_path_prefix:
        parts.append(f"!PathPrefix(`{route.exclude_path_prefix}`)")
    return " && ".join(parts)

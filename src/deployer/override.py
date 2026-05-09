from __future__ import annotations

from pathlib import Path

import yaml

from deployer.manifest import Manifest, Route
from deployer.platform import DEFAULT_PLATFORM, Platform


def build_override(manifest: Manifest, platform: Platform = DEFAULT_PLATFORM) -> dict:
    labels: list[str] = ["traefik.enable=true"]

    for route in manifest.routes:
        labels.extend(_route_labels(manifest, route, platform))

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


def render_override(manifest: Manifest, platform: Platform = DEFAULT_PLATFORM) -> str:
    return yaml.safe_dump(build_override(manifest, platform), sort_keys=False)


def write_override(project_dir: Path, manifest: Manifest, platform: Platform = DEFAULT_PLATFORM) -> Path:
    deployer_dir = project_dir / ".deployer"
    deployer_dir.mkdir(exist_ok=True)
    path = deployer_dir / "docker-compose.override.yml"
    path.write_text(render_override(manifest, platform))
    return path


def _route_labels(manifest: Manifest, route: Route, platform: Platform) -> list[str]:
    router = route.name or manifest.name
    service = router
    labels = [
        f"traefik.http.routers.{router}.rule={_rule(route)}",
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


def _rule(route: Route) -> str:
    parts = [f"Host(`{route.host}`)"]
    if route.path_prefix:
        parts.append(f"PathPrefix(`{route.path_prefix}`)")
    if route.exclude_path_prefix:
        parts.append(f"!PathPrefix(`{route.exclude_path_prefix}`)")
    return " && ".join(parts)

from __future__ import annotations

from pathlib import Path

import yaml

from deployer.manifest import Manifest, Route
from deployer.platform import DEFAULT_PLATFORM, Platform


def build_override(
    manifest: Manifest,
    platform: Platform = DEFAULT_PLATFORM,
    environment: str = "prod",
    env_file: str | None = None,
    url_prefix: str | None = None,
    env_vars: dict[str, str] | None = None,
) -> dict:
    labels: list[str] = ["traefik.enable=true"]

    for route in manifest.routes:
        labels.extend(_route_labels(manifest, route, platform, environment, url_prefix))

    service_config: dict = {
        "labels": labels,
        "networks": [platform.network],
    }
    effective_env_file = env_file or manifest.env_file
    if effective_env_file:
        service_config["env_file"] = effective_env_file
    if env_vars:
        service_config["environment"] = dict(sorted(env_vars.items()))

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
    env_file: str | None = None,
    url_prefix: str | None = None,
    env_vars: dict[str, str] | None = None,
) -> str:
    return yaml.safe_dump(
        build_override(manifest, platform, environment, env_file, url_prefix, env_vars),
        sort_keys=False,
    )


def write_override(
    project_dir: Path,
    manifest: Manifest,
    platform: Platform = DEFAULT_PLATFORM,
    environment: str = "prod",
    output_dir: Path | None = None,
    env_file: str | None = None,
    url_prefix: str | None = None,
    env_vars: dict[str, str] | None = None,
) -> Path:
    deployer_dir = output_dir or project_dir / ".deployer"
    deployer_dir.mkdir(parents=True, exist_ok=True)
    path = deployer_dir / f"{environment}.override.yml"
    path.write_text(render_override(manifest, platform, environment, env_file, url_prefix, env_vars))
    return path


def _route_labels(
    manifest: Manifest,
    route: Route,
    platform: Platform,
    environment: str,
    url_prefix: str | None,
) -> list[str]:
    base_router = route.name or manifest.name
    router = base_router if environment == "prod" else f"{base_router}-{environment}"
    service = router
    labels = [
        f"traefik.http.routers.{router}.rule={_rule(route, platform, environment, url_prefix)}",
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


def route_host(
    route: Route,
    platform: Platform = DEFAULT_PLATFORM,
    environment: str = "prod",
    url_prefix: str | None = None,
) -> str:
    if route.host:
        return route.host
    prefix = route.subdomain
    effective_url_prefix = _default_url_prefix(environment) if url_prefix is None else url_prefix
    if effective_url_prefix:
        prefix = f"{prefix}.{effective_url_prefix}"
    return f"{prefix}.{platform.domain}"


def _rule(route: Route, platform: Platform, environment: str, url_prefix: str | None) -> str:
    parts = [f"Host(`{route_host(route, platform, environment, url_prefix)}`)"]
    if route.path_prefix:
        parts.append(f"PathPrefix(`{route.path_prefix}`)")
    if route.exclude_path_prefix:
        parts.append(f"!PathPrefix(`{route.exclude_path_prefix}`)")
    return " && ".join(parts)


def _default_url_prefix(environment: str) -> str:
    return "" if environment == "prod" else environment

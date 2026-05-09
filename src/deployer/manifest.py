from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from deployer.errors import ManifestError


@dataclass(frozen=True)
class Route:
    auth: str = "none"
    host: str | None = None
    subdomain: str | None = None
    name: str | None = None
    path_prefix: str | None = None
    exclude_path_prefix: str | None = None
    priority: int | None = None
    middlewares: tuple[str, ...] = ()


@dataclass(frozen=True)
class Healthcheck:
    path: str = "/health"
    scheme: str = "http"
    timeout_seconds: float = 10.0
    retries: int = 12
    interval_seconds: float = 2.0


@dataclass(frozen=True)
class ComposeConfig:
    files: tuple[str, ...] = ("docker-compose.yml",)


@dataclass(frozen=True)
class Manifest:
    name: str
    service: str
    port: int
    routes: tuple[Route, ...]
    compose: ComposeConfig
    env_file: str | None = None
    healthcheck: Healthcheck | None = None

    @property
    def project_name(self) -> str:
        return self.name

    def project_name_for(self, environment: str) -> str:
        if environment == "prod":
            return self.name
        return f"{self.name}-{environment}"


def load_manifest(project_dir: Path, manifest_path: Path | None = None) -> Manifest:
    manifest_path = manifest_path or project_dir / "deployer.yml"
    if not manifest_path.exists():
        raise ManifestError(f"Missing manifest: {manifest_path}")

    raw = yaml.safe_load(manifest_path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ManifestError("deployer.yml must contain a YAML mapping")

    manifest = parse_manifest(raw)
    validate_compose_files(project_dir, manifest)
    return manifest


def parse_manifest(raw: dict[str, Any]) -> Manifest:
    name = _required_str(raw, "name")
    service = _required_str(raw, "service")
    port = _required_int(raw, "port")

    compose_raw = raw.get("compose") or {}
    if not isinstance(compose_raw, dict):
        raise ManifestError("compose must be a mapping")
    files_raw = compose_raw.get("files", ["docker-compose.yml"])
    if not isinstance(files_raw, list) or not files_raw:
        raise ManifestError("compose.files must be a non-empty list")
    files = tuple(_as_non_empty_str(item, "compose.files item") for item in files_raw)

    routes_raw = raw.get("routes")
    if not isinstance(routes_raw, list) or not routes_raw:
        raise ManifestError("routes must be a non-empty list")
    routes = tuple(_parse_route(item, name) for item in routes_raw)

    env_file = raw.get("env_file")
    if env_file is not None:
        env_file = _as_non_empty_str(env_file, "env_file")

    healthcheck = None
    if "healthcheck" in raw and raw["healthcheck"] is not None:
        healthcheck = _parse_healthcheck(raw["healthcheck"])

    return Manifest(
        name=name,
        service=service,
        port=port,
        routes=routes,
        compose=ComposeConfig(files=files),
        env_file=env_file,
        healthcheck=healthcheck,
    )


def validate_compose_files(project_dir: Path, manifest: Manifest) -> None:
    missing = [file for file in manifest.compose.files if not (project_dir / file).exists()]
    if missing:
        raise ManifestError(f"Missing compose files: {', '.join(missing)}")


def _parse_route(raw: Any, project_name: str) -> Route:
    if not isinstance(raw, dict):
        raise ManifestError("Each route must be a mapping")
    host = _optional_str(raw, "host")
    subdomain = _optional_str(raw, "subdomain")
    if not host and not subdomain:
        raise ManifestError("Each route must define host or subdomain")
    if host and subdomain:
        raise ManifestError("Route must not define both host and subdomain")
    auth = str(raw.get("auth", "none"))
    if auth not in {"none", "sso"}:
        raise ManifestError("route.auth must be one of: none, sso")

    middlewares_raw = raw.get("middlewares", [])
    if not isinstance(middlewares_raw, list):
        raise ManifestError("route.middlewares must be a list")

    priority = raw.get("priority")
    if priority is not None and not isinstance(priority, int):
        raise ManifestError("route.priority must be an integer")

    route_name = raw.get("name")
    if route_name is None:
        route_name = _default_route_name(project_name, raw)
    else:
        route_name = _as_non_empty_str(route_name, "route.name")

    return Route(
        name=route_name,
        host=host,
        subdomain=subdomain,
        auth=auth,
        path_prefix=_optional_str(raw, "path_prefix"),
        exclude_path_prefix=_optional_str(raw, "exclude_path_prefix"),
        priority=priority,
        middlewares=tuple(_as_non_empty_str(item, "route.middlewares item") for item in middlewares_raw),
    )


def _parse_healthcheck(raw: Any) -> Healthcheck:
    if not isinstance(raw, dict):
        raise ManifestError("healthcheck must be a mapping")
    path = str(raw.get("path", "/health"))
    if not path.startswith("/"):
        raise ManifestError("healthcheck.path must start with /")
    scheme = str(raw.get("scheme", "http"))
    if scheme not in {"http", "https"}:
        raise ManifestError("healthcheck.scheme must be http or https")
    timeout = raw.get("timeout_seconds", 10.0)
    if not isinstance(timeout, int | float) or timeout <= 0:
        raise ManifestError("healthcheck.timeout_seconds must be positive")
    retries = raw.get("retries", 12)
    if not isinstance(retries, int) or retries <= 0:
        raise ManifestError("healthcheck.retries must be a positive integer")
    interval = raw.get("interval_seconds", 2.0)
    if not isinstance(interval, int | float) or interval <= 0:
        raise ManifestError("healthcheck.interval_seconds must be positive")
    return Healthcheck(
        path=path,
        scheme=scheme,
        timeout_seconds=float(timeout),
        retries=retries,
        interval_seconds=float(interval),
    )


def _default_route_name(project_name: str, raw: dict[str, Any]) -> str:
    if raw.get("path_prefix"):
        return f"{project_name}-public"
    if raw.get("exclude_path_prefix"):
        return f"{project_name}-private"
    return project_name


def _required_str(raw: dict[str, Any], key: str) -> str:
    if key not in raw:
        raise ManifestError(f"Missing required field: {key}")
    return _as_non_empty_str(raw[key], key)


def _required_int(raw: dict[str, Any], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or value <= 0:
        raise ManifestError(f"{key} must be a positive integer")
    return value


def _optional_str(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    return _as_non_empty_str(value, key)


def _as_non_empty_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{name} must be a non-empty string")
    return value.strip()

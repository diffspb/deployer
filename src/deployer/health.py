from __future__ import annotations

from urllib.error import URLError
from urllib.request import urlopen

from deployer.manifest import Healthcheck, Manifest
from deployer.override import route_host
from deployer.platform import DEFAULT_PLATFORM, Platform


def healthcheck_url(
    manifest: Manifest,
    platform: Platform = DEFAULT_PLATFORM,
    environment: str = "prod",
) -> str | None:
    if manifest.healthcheck is None or not manifest.routes:
        return None
    route = manifest.routes[0]
    health = manifest.healthcheck
    return f"{health.scheme}://{route_host(route, platform, environment)}{health.path}"


def check_health(manifest: Manifest, environment: str = "prod") -> tuple[bool, str]:
    url = healthcheck_url(manifest, environment=environment)
    if url is None:
        return True, "healthcheck skipped"

    timeout = manifest.healthcheck.timeout_seconds if manifest.healthcheck else 10.0
    try:
        with urlopen(url, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if 200 <= status < 300:
                return True, f"healthcheck ok: {url}"
            return False, f"healthcheck failed with status {status}: {url}"
    except URLError as exc:
        return False, f"healthcheck failed: {url}: {exc}"

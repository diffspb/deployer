from __future__ import annotations

from urllib.error import URLError
from urllib.request import urlopen
from time import sleep

from deployer.manifest import Healthcheck, Manifest
from deployer.override import route_host
from deployer.platform import DEFAULT_PLATFORM, Platform


def healthcheck_url(
    manifest: Manifest,
    platform: Platform = DEFAULT_PLATFORM,
    environment: str = "prod",
    url_prefix: str | None = None,
) -> str | None:
    if manifest.healthcheck is None or not manifest.routes:
        return None
    route = manifest.routes[0]
    health = manifest.healthcheck
    return f"{health.scheme}://{route_host(route, platform, environment, url_prefix)}{health.path}"


def check_health(manifest: Manifest, environment: str = "prod", url_prefix: str | None = None) -> tuple[bool, str]:
    url = healthcheck_url(manifest, environment=environment, url_prefix=url_prefix)
    if url is None:
        return True, "healthcheck skipped"

    health = manifest.healthcheck
    timeout = health.timeout_seconds if health else 10.0
    retries = health.retries if health else 1
    interval = health.interval_seconds if health else 1.0
    last_error = "unknown error"
    for attempt in range(1, retries + 1):
        try:
            with urlopen(url, timeout=timeout) as response:
                status = getattr(response, "status", 200)
                if 200 <= status < 300:
                    return True, f"healthcheck ok: {url} after {attempt} attempt(s)"
                last_error = f"status {status}"
        except URLError as exc:
            last_error = str(exc)
        if attempt < retries:
            sleep(interval)
    return False, f"healthcheck failed: {url}: {last_error}"

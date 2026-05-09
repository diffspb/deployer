from __future__ import annotations

from urllib.error import URLError
from urllib.request import urlopen

from deployer.manifest import Healthcheck, Manifest


def healthcheck_url(manifest: Manifest) -> str | None:
    if manifest.healthcheck is None or not manifest.routes:
        return None
    route = manifest.routes[0]
    health = manifest.healthcheck
    return f"{health.scheme}://{route.host}{health.path}"


def check_health(manifest: Manifest) -> tuple[bool, str]:
    url = healthcheck_url(manifest)
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

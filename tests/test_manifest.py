from pathlib import Path

import pytest

from deployer.errors import ManifestError
from deployer.manifest import load_manifest, parse_manifest


def test_parse_minimal_manifest():
    manifest = parse_manifest(
        {
            "name": "myapp",
            "service": "app",
            "port": 8000,
            "routes": [{"subdomain": "myapp", "auth": "sso"}],
        }
    )

    assert manifest.name == "myapp"
    assert manifest.compose.files == ("docker-compose.yml",)
    assert manifest.routes[0].name == "myapp"
    assert manifest.routes[0].subdomain == "myapp"
    assert manifest.routes[0].auth == "sso"


def test_parse_rejects_invalid_auth():
    with pytest.raises(ManifestError, match="route.auth"):
        parse_manifest(
            {
                "name": "myapp",
                "service": "app",
                "port": 8000,
                "routes": [{"subdomain": "myapp", "auth": "password"}],
            }
        )


def test_load_manifest_validates_compose_files(tmp_path: Path):
    (tmp_path / "deployer.yml").write_text(
        """
name: myapp
service: app
port: 8000
compose:
  files:
    - docker-compose.yml
routes:
  - host: myapp.busypage.ru
"""
    )

    with pytest.raises(ManifestError, match="Missing compose files"):
        load_manifest(tmp_path)

    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    assert load_manifest(tmp_path).name == "myapp"

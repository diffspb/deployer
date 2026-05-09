from urllib.error import URLError

from deployer.health import check_health, healthcheck_url
from deployer.manifest import parse_manifest


def _manifest():
    return parse_manifest(
        {
            "name": "myapp",
            "service": "app",
            "port": 8000,
            "routes": [{"host": "myapp.busypage.ru"}],
            "healthcheck": {"path": "/health"},
        }
    )


def test_healthcheck_url():
    assert healthcheck_url(_manifest()) == "http://myapp.busypage.ru/health"


def test_check_health_success(monkeypatch):
    class Response:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("deployer.health.urlopen", lambda url, timeout: Response())

    ok, message = check_health(_manifest())

    assert ok is True
    assert "healthcheck ok" in message


def test_check_health_failure(monkeypatch):
    def fail(url, timeout):
        raise URLError("no route")

    monkeypatch.setattr("deployer.health.urlopen", fail)

    ok, message = check_health(_manifest())

    assert ok is False
    assert "healthcheck failed" in message

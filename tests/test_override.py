from deployer.manifest import parse_manifest
from deployer.override import build_override, render_override


def test_override_adds_sso_middlewares_and_explicit_service():
    manifest = parse_manifest(
        {
            "name": "cpucol",
            "service": "app",
            "port": 8000,
            "env_file": ".env.prod",
            "routes": [
                {
                    "name": "cpucol-private",
                    "host": "cpu.busypage.ru",
                    "exclude_path_prefix": "/api/public/",
                    "auth": "sso",
                    "priority": 10,
                },
                {
                    "name": "cpucol-public",
                    "host": "cpu.busypage.ru",
                    "path_prefix": "/api/public/",
                    "auth": "none",
                    "priority": 20,
                },
            ],
        }
    )

    override = build_override(manifest)
    service = override["services"]["app"]

    assert service["env_file"] == ".env.prod"
    assert service["networks"] == ["traefik-public"]
    assert "traefik.http.routers.cpucol-private.service=cpucol-private" in service["labels"]
    assert "traefik.http.routers.cpucol-public.service=cpucol-public" in service["labels"]
    assert (
        "traefik.http.routers.cpucol-private.middlewares=sso-errors@file,sso-auth@file"
        in service["labels"]
    )
    assert "traefik.http.routers.cpucol-public.priority=20" in service["labels"]


def test_render_override_is_yaml():
    manifest = parse_manifest(
        {
            "name": "tasktrack",
            "service": "app",
            "port": 8000,
            "routes": [{"host": "tasktrack.busypage.ru", "middlewares": ["secure-headers@file"]}],
        }
    )

    rendered = render_override(manifest)

    assert "traefik.http.routers.tasktrack.rule=Host(`tasktrack.busypage.ru`)" in rendered
    assert "secure-headers@file" in rendered

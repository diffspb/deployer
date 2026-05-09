from dataclasses import dataclass


@dataclass(frozen=True)
class Platform:
    domain: str = "busypage.ru"
    network: str = "traefik-public"
    entrypoint: str = "websecure"
    certresolver: str = "letsencrypt"
    sso_middlewares: tuple[str, ...] = ("sso-errors@file", "sso-auth@file")


DEFAULT_PLATFORM = Platform()

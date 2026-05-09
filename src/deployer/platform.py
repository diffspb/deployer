from dataclasses import dataclass


@dataclass(frozen=True)
class Platform:
    network: str = "traefik-public"
    entrypoint: str = "websecure"
    certresolver: str = "letsencrypt"
    sso_middlewares: tuple[str, ...] = ("sso-errors@file", "sso-auth@file")


DEFAULT_PLATFORM = Platform()

# Platform Contract

This document is the runtime contract between infrastructure, application repositories, and the deployer.

The contract is intentionally small. Application repositories should not need to know every Traefik detail.

## Runtime

- Host runtime is local Docker Engine on one VPS.
- Deployment unit is a Docker Compose project.
- Each application has a stable Compose project name.
- Public ingress goes through Traefik only.
- TLS is handled by Traefik and Let's Encrypt.
- Authentication for private browser UIs is handled by oauth2-proxy.
- Application logs stay in Docker and are viewed through Dozzle.
- Host/container metrics stay in Netdata.

## Infrastructure Constants

Current values from `/home/sanek/projects/claudecode/simple`:

| Key | Value |
|---|---|
| Public Docker network | `traefik-public` |
| Traefik entrypoint | `websecure` |
| Traefik certresolver | `letsencrypt` |
| SSO middleware | `sso-errors@file,sso-auth@file` |
| Secure headers middleware | `secure-headers@file` |
| Main domain | `busypage.ru` |

## Application Requirements

Minimum recommended `docker-compose.yml`:

```yaml
services:
  app:
    build: .
    restart: unless-stopped
    networks:
      - traefik-public

networks:
  traefik-public:
    external: true
```

Additional services such as PostgreSQL should use an internal network unless they must be reachable by Traefik.

Applications should expose a health endpoint when practical:

```text
GET /health -> 200
```

## Deployer Manifest

Each deployable project should contain `deployer.yml`.

Minimal public service:

```yaml
name: tasktrack
service: app
port: 8000
compose:
  files:
    - docker-compose.yml
    - docker-compose.prod.yml
env_file: .env.prod
routes:
  - subdomain: tasktrack
    auth: none
    middlewares:
      - secure-headers@file
healthcheck:
  path: /health
```

Private UI with a public API path:

```yaml
name: cpucol
service: app
port: 8000
compose:
  files:
    - docker-compose.yml
    - docker-compose.prod.yml
env_file: .env.prod
routes:
  - name: cpucol-public
    subdomain: cpu
    path_prefix: /api/public/
    auth: none
    priority: 20
  - name: cpucol-private
    subdomain: cpu
    exclude_path_prefix: /api/public/
    auth: sso
    priority: 10
healthcheck:
  path: /health
```

## Generated Override

The deployer generates `.deployer/docker-compose.override.yml`.

The original project compose files are not modified.
For managed services the generated override also contains the target env file and the same managed
variables in the service `environment` map. This makes deployer-managed values override project-level
defaults such as `APP_ENV: ${APP_ENV:-local}`.
The same managed env file is passed to Docker Compose via `--env-file`, so `${VAR}` substitutions in
any compose service can use deployer-managed values.

Generated labels must include:

- `traefik.enable=true`
- router rule
- router entrypoint
- router TLS certresolver
- router service name
- service load balancer port
- middleware labels when configured

Every router explicitly points to a Traefik service. This avoids Traefik ambiguity when one container has multiple routers.

## Auth Modes

`auth: none` means no oauth2-proxy middleware is injected. The application may still enforce Bearer token auth itself.

`auth: sso` injects:

```text
sso-errors@file,sso-auth@file
```

Additional middlewares may be listed explicitly.

## Non-Goals

- No Kubernetes.
- No Swarm.
- No multi-server scheduling.
- No custom user system.
- No built-in app log viewer.
- No built-in metrics system.
- No arbitrary command execution from UI.

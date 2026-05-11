# Platform Contract

This document is the runtime contract between infrastructure, application repositories, and the deployer.

The contract is intentionally small. Application repositories should not need to know every Traefik detail
or contain deployer-specific configuration.

## Runtime

- Host runtime is local Docker Engine on one VPS.
- Deployment unit is an environment-scoped project.
- Each environment project has a stable Compose project name.
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

The deployer should be able to deploy projects without modifying their repositories.

Minimum repository expectations:

- application containers can be built from Dockerfiles or existing Docker Compose files;
- runtime configuration is accepted through environment variables;
- public HTTP components listen on known container ports;
- health endpoints are recommended, but their paths can be configured in deployer;
- stateful resource names are not hardcoded in application code.

Minimum recommended Compose shape when a project already has Docker Compose:

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

## Deployer Configuration

Primary deployer configuration lives in deployer state and is edited through UI/CLI.
Repository-local `deployer.yml` may remain supported as an optional import/config-as-code
format, but it is not required.

The target model is:

```text
Environment
  Project
    Components
    Endpoints
    Dependencies
```

An environment project can use existing compose files or generated component definitions.

Example external project configuration:

```yaml
environment: dev
project: tasktrack
source:
  type: git
  url: git@github.com:org/tasktrack.git
  ref: dev
compose:
  mode: overlay
  files:
    - docker-compose.yml
    - docker-compose.prod.yml
components:
  - name: backend
    compose_service: app
    port: 8000
endpoints:
  - name: web
    component: backend
    subdomain: tasktrack
    auth: sso
    middlewares:
      - secure-headers@file
    healthcheck:
      path: /api/v1/health
```

The same repository in another environment is another project entry, not an attachment:

```text
dev/tasktrack
prod/tasktrack
```

Optional legacy/import manifest example:

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

## Generated Runtime Files

The deployer generates env files and Compose files/overrides.

The original project compose files are not modified.
For managed services the generated override also contains the target env file and the same managed
variables in the service `environment` map. This makes deployer-managed values override project-level
defaults such as `APP_ENV: ${APP_ENV:-local}`.
The same managed env file is passed to Docker Compose via `--env-file`, so `${VAR}` substitutions in
any compose service can use deployer-managed values.
Docker Compose runtime commands are executed with BuildKit enabled (`DOCKER_BUILDKIT=1` and
`COMPOSE_DOCKER_CLI_BUILD=1`) so project Dockerfiles can use BuildKit syntax such as
`RUN --mount=type=cache`.
The packaged deployer image includes both Docker Compose and Buildx CLI plugins; BuildKit-only
Dockerfiles will fail if the running deployer image was built before Buildx was added.

Generated Traefik labels for public endpoints must include:

- `traefik.enable=true`
- router rule
- router entrypoint
- router TLS certresolver
- router service name
- service load balancer port
- middleware labels when configured

Every router explicitly points to a Traefik service. This avoids Traefik ambiguity when one container has multiple routers.

## Multi-Component Projects

A project may contain multiple components:

- backend;
- frontend;
- worker;
- scheduler;
- migrations;
- internal databases or queues when they are project-owned.

Only components with configured public endpoints receive Traefik labels. Internal
components can still receive managed env vars, networks, and dependency outputs.

Example public endpoint layout:

```text
dev/tasktrack frontend -> tasktrack.dev.busypage.ru
dev/tasktrack backend  -> api.tasktrack.dev.busypage.ru
prod/tasktrack frontend -> tasktrack.busypage.ru
prod/tasktrack backend  -> api.tasktrack.busypage.ru
```

## Dependencies

Environment projects can bind to managed resources. The initial practical target is one
shared PostgreSQL instance per environment or platform with separate databases/users per
project:

```text
dev/tasktrack -> database tasktrack_dev, user tasktrack_dev
prod/tasktrack -> database tasktrack, user tasktrack
```

Bindings may first be materialized as env vars such as `DATABASE_URL`, but the logical
configuration should remain explicit so environments do not accidentally share state.

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

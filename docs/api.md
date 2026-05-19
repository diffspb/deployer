# API

The API is the contract for the current web UI. The UI must call these endpoints and must not call Docker directly.

The service/runtime-target API is still present for compatibility, but the target operator API is
environment-first:

```text
Environment -> Project -> Components -> Endpoints / Dependencies
```

New UI work should use `/api/environments/{environment}/projects/{project}` operations. No compatibility
migration is required for the development database.

The current target resource model is resource-first:

```text
Environment Resource -> Project Resource Binding -> generated env vars / mounts
```

Legacy project `dependencies` are still present, but they are no longer the preferred extension point for managed
resources.

## Configuration

Runtime configuration is read from environment variables:

```bash
DEPLOYER_STATE_DB=/var/lib/deployer/state.db
DEPLOYER_RUNTIME_DIR=/var/lib/deployer
DEPLOYER_HOST_BIND=0.0.0.0
DEPLOYER_PORT=8000
```

Local development:

```bash
make api
```

## Endpoints

```text
GET    /api/health
GET    /api/version
GET    /api/services
POST   /api/services
GET    /api/services/{name}
DELETE /api/services/{name}
GET    /api/environments
POST   /api/environments
GET    /api/environments/{environment}/services
PATCH  /api/environments/{environment}
DELETE /api/environments/{environment}
GET    /api/environments/{environment}/resources
POST   /api/environments/{environment}/resources
GET    /api/environments/{environment}/projects
POST   /api/environments/{environment}/projects
GET    /api/environments/{environment}/projects/{project}
DELETE /api/environments/{environment}/projects/{project}
GET    /api/environments/{environment}/projects/{project}/env
POST   /api/environments/{environment}/projects/{project}/env
DELETE /api/environments/{environment}/projects/{project}/env/{key}
POST   /api/environments/{environment}/projects/{project}/components
PATCH  /api/environments/{environment}/projects/{project}/components/{component}
DELETE /api/environments/{environment}/projects/{project}/components/{component}
POST   /api/environments/{environment}/projects/{project}/endpoints
PATCH  /api/environments/{environment}/projects/{project}/endpoints/{endpoint}
DELETE /api/environments/{environment}/projects/{project}/endpoints/{endpoint}
POST   /api/environments/{environment}/projects/{project}/dependencies
PATCH  /api/environments/{environment}/projects/{project}/dependencies/{dependency}
DELETE /api/environments/{environment}/projects/{project}/dependencies/{dependency}
POST   /api/environments/{environment}/projects/{project}/resource-bindings
GET    /api/environments/{environment}/projects/{project}/preview
POST   /api/environments/{environment}/projects/{project}/deploy
POST   /api/environments/{environment}/projects/{project}/stop
POST   /api/environments/{environment}/projects/{project}/down
POST   /api/environments/{environment}/projects/{project}/restart
GET    /api/environments/{environment}/projects/{project}/status
GET    /api/environments/{environment}/projects/{project}/logs
GET    /api/services/{name}/refs
GET    /api/services/{name}/runtime-targets
POST   /api/services/{name}/runtime-targets
DELETE /api/services/{name}/runtime-targets/{environment}
GET    /api/services/{name}/env/{environment}
POST   /api/services/{name}/env/{environment}
DELETE /api/services/{name}/env/{environment}/{key}
GET    /api/services/{name}/history
GET    /api/services/{name}/preview
GET    /api/jobs
GET    /api/jobs/{job_id}
GET    /api/webhook-events
POST   /api/webhooks/github
POST   /api/environments/{environment}/projects/{project}/deploy-candidate
POST   /api/services/{name}/deploy
POST   /api/services/{name}/stop
POST   /api/services/{name}/down
POST   /api/services/{name}/restart
GET    /api/services/{name}/status
GET    /api/services/{name}/logs
```

Environment project endpoint payload:

```json
{
  "name": "web",
  "component": "backend",
  "port": 8000,
  "host": null,
  "subdomain": "myapp",
  "path_prefix": null,
  "auth": "sso",
  "middlewares": [],
  "healthcheck_path": "/health"
}
```

Environment project payloads include the last known runtime snapshot. It is a cached operator view and is only
updated by explicit status checks or successful runtime actions; the UI must not use global polling to keep it fresh.

```json
{
  "environment": "dev",
  "name": "tasktrack",
  "current_ref": "dev",
  "current_commit": "abc123",
  "last_deployment_id": 42,
  "runtime_status": {
    "state": "running",
    "health": "healthy",
    "containers": [
      {
        "name": "dev-tasktrack-web-1",
        "service": "web",
        "state": "running",
        "health": "healthy"
      }
    ],
    "raw": "...",
    "error": null,
    "checked_at": "2026-05-19T10:00:00+00:00"
  },
  "last_job": {
    "id": 42,
    "action": "deploy",
    "status": "success"
  }
}
```

`GET /api/environments/{environment}/projects/{project}/status` executes `docker compose ps`, stores the parsed
snapshot, and returns both the command result and the normalized `runtime_status`.

Environment resources are reusable managed infrastructure objects owned by one environment. Project resource
bindings connect a project, and optionally a component, to one resource. Bindings can produce runtime env vars and
volume mounts. Legacy project `dependencies` are still supported for compatibility, but new resource work should use
resources and bindings.

Create a Postgres resource:

```json
{
  "name": "postgres-main",
  "type": "postgres",
  "config": {
    "host": "postgres",
    "port": "5432"
  }
}
```

Bind a project to that resource:

```json
{
  "name": "app-db",
  "resource_name": "postgres-main",
  "component": "backend",
  "config": {
    "database": "tasktrack_dev",
    "username": "tasktrack_dev",
    "password": "secret"
  },
  "outputs": {},
  "mounts": [
    {
      "source": "dev_tasktrack_uploads",
      "target": "/app/uploads",
      "type": "volume"
    }
  ]
}
```

For `postgres` bindings, `DATABASE_URL` is generated when `host`, `database`, `username`, and `password` are known.
Explicit `outputs` can override generated values. Mounts are rendered into the deployer-owned compose override for
the selected component.

Current limitations:

- resource providers do not provision real infrastructure yet;
- Postgres databases/users/passwords must already exist or be created manually;
- Docker volumes are referenced in compose overrides but are not created/managed by deployer yet;
- secrets are stored as plain config/output values until secret storage is implemented.

`healthcheck_path` is optional. When set, the UI shows it next to the public endpoint and stores it in the
deployer-managed endpoint configuration.

`GET /api/version` returns backend package version, frontend asset hash, and optional Docker build metadata:

```json
{
  "backend_version": "0.1.0",
  "frontend_version": "a1b2c3d4e5f6",
  "build_commit": "unknown",
  "build_date": "unknown"
}
```

## Add Service

Git source:

```json
{
  "name": "myapp",
  "source_type": "git",
  "git_url": "git@example.com:me/myapp.git",
  "default_branch": "main"
}
```

Local source:

```json
{
  "name": "myapp",
  "source_type": "local",
  "path": "/path/to/project"
}
```

Service detail includes source checkout status:

```json
{
  "name": "myapp",
  "source_type": "git",
  "source_status": {
    "available": true,
    "path_exists": true,
    "is_git_repo": true,
    "current_ref": "master",
    "current_commit": "56028edb9e996064f2083445e97597ddf7c4d56b",
    "error": null
  }
}
```

New services start with no runtime targets:

```json
{
  "name": "myapp",
  "environments": []
}
```

After explicit attachment, service detail includes all runtime targets currently stored for the service:

```json
{
  "name": "myapp",
  "environments": [
    {
      "name": "prod",
      "url_prefix": "",
      "deploy_mode": "manual",
      "deploy_source": null,
      "deploy_pattern": null,
      "deploy_pattern_type": null,
      "public_url": "https://myapp.busypage.ru/",
      "env": {},
      "current_ref": "main",
      "current_commit": "abc123",
      "last_deployment_id": 42
    },
    {
      "name": "stage",
      "url_prefix": "rc",
      "deploy_mode": "webhook_auto",
      "deploy_source": "tag",
      "deploy_pattern": "^v.+-rc[0-9]+$",
      "deploy_pattern_type": "regex",
      "public_url": "https://myapp.rc.busypage.ru/",
      "env": {},
      "current_ref": "v1-rc1",
      "current_commit": "def456",
      "last_deployment_id": 43
    }
  ]
}
```

## Environment Profiles

Environment profiles are global platform-level definitions. `prod` and `dev` are created as
default profile definitions for existing workflows, but the API does not restrict the profile name set.
Creating a service does not attach it to any profile automatically.

Create:

```json
{
  "name": "stage",
  "url_prefix": "rc",
  "deploy_mode": "webhook_auto",
  "deploy_source": "tag",
  "deploy_pattern": "^v.+-rc[0-9]+$",
  "deploy_pattern_type": "regex"
}
```

Update:

```json
{
  "url_prefix": "stage",
  "deploy_mode": "webhook_gated"
}
```

Rules:

- `name` must contain lowercase letters, digits, and dashes.
- `url_prefix` may be empty for the base host or contain lowercase letters, digits, and dashes.
- `deploy_mode` is `manual`, `webhook_auto`, or `webhook_gated`.
- `deploy_source` is `branch` or `tag` for webhook targets.
- `deploy_pattern_type` is `exact` or `regex` for webhook targets.
- webhook targets must define `deploy_source`, `deploy_pattern`, and `deploy_pattern_type`.

## Runtime Targets

Runtime targets are per-service enablements of global environment profiles. They store service-specific
runtime state: env vars, current ref/commit, deployment history, jobs, logs, and candidates.

Create a runtime target by referencing an existing profile:

```json
{
  "name": "stage"
}
```

- Runtime actions, env vars, history, preview, status, and logs are always scoped to `service + environment`.
- The UI treats an environment as the parent container and lists only services explicitly attached to it.
- `GET /api/environments` includes a `services` array for each profile.
- `GET /api/environments/{environment}/services` returns one profile and its attached services.

## Runtime Preview

`GET /api/services/{name}/preview?environment=prod` returns the current generated runtime inputs
without starting a deploy job. The response is intended for the Web UI preflight/preview flow.

Example response:

```json
{
  "service": "myapp",
  "environment": "prod",
  "valid": true,
  "errors": [],
  "source_path": "/var/lib/deployer/services/myapp/repo",
  "manifest_path": "/var/lib/deployer/services/myapp/repo/deployer.yml",
  "compose_files": ["docker-compose.yml"],
  "public_url": "https://myapp.busypage.ru/",
  "env_file_path": "/var/lib/deployer/services/myapp/env/prod.env",
  "env_file_content": "TOKEN=abc\n",
  "override_path": "/var/lib/deployer/services/myapp/overrides/prod.override.yml",
  "override_content": "services:\n  app:\n    labels:\n      - traefik.enable=true\n    env_file: /var/lib/deployer/services/myapp/env/prod.env\n    environment:\n      TOKEN: abc\n"
}
```

If the current checkout cannot be validated, the endpoint still returns HTTP `200`, but sets
`valid=false` and fills the `errors` array with `source` and/or `manifest` validation messages.
Managed environment variables are rendered both into the generated env file and into the generated
compose override `environment` section. The override value has the highest priority and deliberately
replaces project-level defaults such as `APP_ENV: ${APP_ENV:-local}`.

## Runtime Actions

Runtime-changing actions are asynchronous from the API contract point of view. The API creates a job, starts the
operation in the background, and returns HTTP `202` with the current job payload. The UI should poll
`GET /api/jobs/{job_id}` until `status` becomes `success` or `failed`.
`GET /api/jobs` returns job metadata without heavy logs. Fetch a single job to inspect output.
`GET /api/jobs/{job_id}?log_limit=200000` returns the most recent output up to `log_limit` characters.
Job output includes source preparation lines where available, for example `git fetch`, `git checkout`,
`git rev-parse HEAD`, generated override path, and the exact Docker Compose command.

Deploy:

```json
{
  "environment": "prod",
  "ref": "main",
  "dry_run": false
}
```

Stop/down/restart:

```json
{
  "environment": "prod",
  "dry_run": false
}
```

Semantics:

- `deploy` runs `docker compose --env-file <managed-env> up -d --build`.
- `stop` runs `docker compose --env-file <managed-env> stop` and keeps containers.
- `down` runs `docker compose --env-file <managed-env> down` and removes containers.
- `restart` runs `docker compose --env-file <managed-env> restart`.
- `status` runs `docker compose --env-file <managed-env> ps`.
- `logs` runs `docker compose --env-file <managed-env> logs --tail <n>`.

Job payload:

```json
{
  "id": 1,
  "service": "myapp",
  "environment": "prod",
  "action": "deploy",
  "status": "success",
  "ref": "main",
  "version": null,
  "dry_run": false,
  "deployment_id": 42,
  "created_at": "2026-05-10T10:00:00+00:00",
  "started_at": "2026-05-10T10:00:01+00:00",
  "finished_at": "2026-05-10T10:00:30+00:00",
  "log": "Generated override: ...",
  "log_truncated": false,
  "error": null
}
```

Job statuses:

- `queued`: operation was accepted but has not started.
- `running`: operation is executing.
- `success`: operation finished successfully.
- `failed`: operation finished with an error or failed deployment status.

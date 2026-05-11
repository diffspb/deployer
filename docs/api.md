# API

The API is the contract for the future web UI. The UI must call these endpoints and must not call Docker directly.

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
GET    /api/services
POST   /api/services
GET    /api/services/{name}
DELETE /api/services/{name}
GET    /api/services/{name}/refs
GET    /api/services/{name}/runtime-targets
POST   /api/services/{name}/runtime-targets
PATCH  /api/services/{name}/runtime-targets/{environment}
DELETE /api/services/{name}/runtime-targets/{environment}
GET    /api/services/{name}/env/{environment}
POST   /api/services/{name}/env/{environment}
DELETE /api/services/{name}/env/{environment}/{key}
GET    /api/services/{name}/history
GET    /api/services/{name}/preview
GET    /api/jobs
GET    /api/jobs/{job_id}
POST   /api/services/{name}/deploy
POST   /api/services/{name}/stop
POST   /api/services/{name}/down
POST   /api/services/{name}/restart
GET    /api/services/{name}/status
GET    /api/services/{name}/logs
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

Service detail also includes all runtime targets currently stored for the service:

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

## Runtime Targets

Runtime targets are arbitrary per-service deployable units. `prod` and `dev` are created as
defaults for existing workflows, but the API does not restrict the target name set.

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
- Runtime actions, env vars, history, preview, status, and logs are always scoped to `service + environment`.

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
  "override_content": "services:\n  app:\n    labels:\n      - traefik.enable=true\n"
}
```

If the current checkout cannot be validated, the endpoint still returns HTTP `200`, but sets
`valid=false` and fills the `errors` array with `source` and/or `manifest` validation messages.

## Runtime Actions

Runtime-changing actions are asynchronous from the API contract point of view. The API creates a job, starts the
operation in the background, and returns HTTP `202` with the current job payload. The UI should poll
`GET /api/jobs/{job_id}` until `status` becomes `success` or `failed`.

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

- `deploy` runs `docker compose up -d --build`.
- `stop` runs `docker compose stop` and keeps containers.
- `down` runs `docker compose down` and removes containers.
- `restart` runs `docker compose restart`.
- `status` runs `docker compose ps`.
- `logs` runs `docker compose logs --tail <n>`.

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
  "error": null
}
```

Job statuses:

- `queued`: operation was accepted but has not started.
- `running`: operation is executing.
- `success`: operation finished successfully.
- `failed`: operation finished with an error or failed deployment status.

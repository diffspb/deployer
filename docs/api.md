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
GET    /api/services/{name}/env/{environment}
POST   /api/services/{name}/env/{environment}
DELETE /api/services/{name}/env/{environment}/{key}
GET    /api/services/{name}/history
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

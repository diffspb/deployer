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

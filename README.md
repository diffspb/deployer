# Home PaaS Deployer

Small control plane for a personal Docker Compose based PaaS.

The deployer intentionally does not replace the runtime stack. It formalizes the existing platform contract:

- Docker Compose runs applications.
- Traefik terminates TLS and routes traffic.
- oauth2-proxy protects private UIs.
- Dozzle and Netdata keep application logs and host metrics out of the deployer.

## Development

Use the local virtual environment directly. Do not rely on shell activation.

```bash
make install
make test
make coverage
make api
```

Useful local checks:

```bash
make validate-samples
make render-tasktrack
make render-cpucol
```

Reset local/test deployer state:

```bash
make reset-dev
make reset-test
```

`reset-dev` removes `DEV_STATE_DB` and `DEV_RUNTIME_DIR`, defaulting to `.deployer/state.db` and `.deployer/runtime`.
`reset-test` removes `/tmp/deployer-state.sqlite3` and `/tmp/deployer-runtime`.

## MVP Scope

Current implementation includes the deployer engine and the first catalog/UI iteration:

- `deployer.yml` manifest validation.
- Traefik override generation.
- SQLite deployment history.
- Per-project deployment lock.
- Command logging.
- Optional healthcheck.
- CLI suitable for later reuse by FastAPI UI.
- Environment-aware deployment with operator-defined environment profiles.
- Stop, down, restart, status, and logs commands.
- Service catalog with `git` and `local` sources.
- Managed runtime layout under `/var/lib/deployer/services/<name>/`.
- Environment variable storage and generated env files.
- FastAPI JSON API and Web UI.
- Global environment profiles with explicitly attached services.

This catalog model is now considered an intermediate implementation, not the target
architecture. The next refactor moves to:

```text
Environment -> Project -> Components -> Endpoints / Resource Bindings
```

In the target model, projects are added directly inside environments. There is no global
deployable service that later gets attached to `dev`, `stage`, or `prod`. If the same
repository should run in two environments, it is added twice, for example
`dev/tasktrack` and `prod/tasktrack`.

Implemented environment-project configuration commands:

```bash
deployer environments add dev --url-prefix dev
deployer projects add dev myapp --git-url <url>
deployer components add dev myapp backend --build-context backend --dockerfile Dockerfile --port 8000
deployer endpoints add dev myapp web backend --port 8000 --subdomain myapp --auth sso --health-path /health
deployer resources add dev postgres-main --type postgres --config host=postgres --config port=5432 --config container=postgres
deployer bindings add dev myapp app-db --resource postgres-main --component backend
deployer bindings plan dev myapp app-db
deployer bindings apply dev myapp app-db
deployer projects env-set dev myapp KEY=value
deployer projects show dev myapp
```

`deployer.yml` is not required for environment projects. Runtime configuration is stored in deployer state:
source, compose files, components, endpoints, resource binding outputs, and env variables. Existing compose-based
repositories use `--compose-file` or the default `docker-compose.yml`; Dockerfile/image-only projects can use
`--no-compose-file` and generated component definitions.

Implemented environment-project runtime commands:

```bash
deployer deploy dev myapp --ref dev
deployer status dev myapp
deployer stop dev myapp
deployer down dev myapp
deployer restart dev myapp
deployer logs dev myapp --tail 200
```

`stop` keeps containers stopped. Use `down` when containers should be removed.

Implemented environment-project API:

```text
GET/POST /api/environments/{environment}/projects
GET/DELETE /api/environments/{environment}/projects/{project}
POST /api/environments/{environment}/projects/{project}/components
PATCH/DELETE /api/environments/{environment}/projects/{project}/components/{component}
POST /api/environments/{environment}/projects/{project}/endpoints
PATCH/DELETE /api/environments/{environment}/projects/{project}/endpoints/{endpoint}
POST /api/environments/{environment}/projects/{project}/dependencies
PATCH/DELETE /api/environments/{environment}/projects/{project}/dependencies/{dependency}
POST /api/environments/{environment}/projects/{project}/deploy
GET  /api/environments/{environment}/projects/{project}/status
GET  /api/environments/{environment}/projects/{project}/logs
GET  /api/version
POST /api/webhooks/github
GET  /api/webhook-events
```

GitHub webhooks support `push` events. If `DEPLOYER_WEBHOOK_SECRET` is set, requests must include a valid
`X-Hub-Signature-256` HMAC signature. `webhook_auto` projects schedule a deploy; `webhook_gated` projects store
the matching ref/commit as a deploy candidate.

Web UI:

```bash
make api
```

Open `http://127.0.0.1:8000/`. The UI uses the environment-project API: open an environment, add projects to
it, configure components, endpoints, dependencies, env variables, deploy policy, jobs, logs, webhook events,
and gated deploy candidates in that environment context.

Endpoint configuration in the UI includes an optional health path, for example `/health`. Job output is opened
from the Jobs page or project Recent Jobs table and shows source checkout metadata, generated override path,
the Docker Compose command, and captured command output.
The UI also shows backend/frontend version metadata, Docker image build commit/date, and serves frontend assets
with a version query string. Use `make docker-build` instead of a raw `docker build` if you want build metadata
to include the current git commit and UTC build time.

## Server Runbook

Deployer is built from this repository on the server and started from the infrastructure repository.

Stop deployer:

```bash
cd ~/simple_infra
make deployer-down
```

Start deployer:

```bash
cd ~/simple_infra
make deployer-up
```

Rebuild deployer after `git pull` in `~/paas_deployer`:

```bash
cd ~/paas_deployer
make docker-build
cd ~/simple_infra
make deployer-down
make deployer-up
```

If compose/env configuration changed, re-render deployer config before start:

```bash
cd ~/simple_infra
make deployer-config
make deployer-down
make deployer-up
```

Typical full update sequence on the server:

```bash
cd ~/paas_deployer
git pull
make docker-build
cd ~/simple_infra
make deployer-config
make deployer-down
make deployer-up
```

See:

- [Platform Contract](docs/platform-contract.md)
- [Architecture](docs/architecture.md)
- [API](docs/api.md)
- [Tasks](docs/tasks.md)
- [Project Template](docs/project-template.md)

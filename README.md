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
Environment -> Project -> Components -> Endpoints / Dependencies
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
deployer dependencies add dev myapp postgres --type postgres --target postgres-main/myapp_dev --output DATABASE_URL=postgresql://...
deployer projects env-set dev myapp KEY=value
deployer projects show dev myapp
```

Target runtime commands after the engine refactor:

```bash
deployer deploy dev myapp --ref dev
deployer history dev myapp
deployer status dev myapp
deployer stop dev myapp
deployer down dev myapp
deployer restart dev myapp
deployer logs dev myapp --tail 200
```

`stop` keeps containers stopped. Use `down` when containers should be removed.

Web UI:

```bash
make api
```

Open `http://127.0.0.1:8000/`. The UI uses the same API contract as external clients. It is organized
environment-first in the target architecture: open an environment, add projects to it, configure components,
endpoints, dependencies, env variables, deploy policy, jobs, and logs in that environment context.

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
docker build -t home-paas-deployer:latest .
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
docker build -t home-paas-deployer:latest .
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

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
```

Useful local checks:

```bash
make validate-samples
make render-tasktrack
make render-cpucol
```

## MVP Scope

Current implementation includes the deployer engine and the first service catalog:

- `deployer.yml` manifest validation.
- Traefik override generation.
- SQLite deployment history.
- Per-project deployment lock.
- Command logging.
- Optional healthcheck.
- CLI suitable for later reuse by FastAPI UI.
- Environment-aware prod/dev deployment.
- Stop and status commands.
- Service catalog with `git` and `local` sources.
- Managed runtime layout under `/var/lib/deployer/services/<name>/`.
- Environment variable storage and generated env files.

Catalog workflow:

```bash
deployer services add myapp --git-url <url> --state-db /var/lib/deployer/state.db
deployer services add-local myapp --path /path/to/project --state-db /var/lib/deployer/state.db
deployer env set myapp prod KEY=value --state-db /var/lib/deployer/state.db
deployer deploy myapp --environment prod --ref main --state-db /var/lib/deployer/state.db
deployer status myapp --environment prod --state-db /var/lib/deployer/state.db
deployer stop myapp --environment prod --state-db /var/lib/deployer/state.db
```

See:

- [Platform Contract](docs/platform-contract.md)
- [Architecture](docs/architecture.md)
- [Tasks](docs/tasks.md)
- [Project Template](docs/project-template.md)

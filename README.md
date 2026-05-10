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

Current implementation includes the deployer engine and the first service catalog:

- `deployer.yml` manifest validation.
- Traefik override generation.
- SQLite deployment history.
- Per-project deployment lock.
- Command logging.
- Optional healthcheck.
- CLI suitable for later reuse by FastAPI UI.
- Environment-aware prod/dev deployment.
- Stop, down, restart, status, and logs commands.
- Service catalog with `git` and `local` sources.
- Managed runtime layout under `/var/lib/deployer/services/<name>/`.
- Environment variable storage and generated env files.
- FastAPI JSON API for future Web UI.

Catalog workflow:

```bash
deployer services add myapp --git-url <url> --state-db /var/lib/deployer/state.db
deployer services add-local myapp --path /path/to/project --state-db /var/lib/deployer/state.db
deployer env set myapp prod KEY=value --state-db /var/lib/deployer/state.db
deployer deploy myapp --environment prod --ref main --state-db /var/lib/deployer/state.db
deployer history myapp --environment prod --state-db /var/lib/deployer/state.db
deployer status myapp --environment prod --state-db /var/lib/deployer/state.db
deployer stop myapp --environment prod --state-db /var/lib/deployer/state.db
deployer down myapp --environment prod --state-db /var/lib/deployer/state.db
deployer restart myapp --environment prod --state-db /var/lib/deployer/state.db
deployer logs myapp --environment prod --tail 200 --state-db /var/lib/deployer/state.db
```

`stop` keeps containers stopped. Use `down` when containers should be removed.

See:

- [Platform Contract](docs/platform-contract.md)
- [Architecture](docs/architecture.md)
- [API](docs/api.md)
- [Tasks](docs/tasks.md)
- [Project Template](docs/project-template.md)

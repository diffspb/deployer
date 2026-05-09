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

Current implementation focuses on the first deployer engine:

- `deployer.yml` manifest validation.
- Traefik override generation.
- SQLite deployment history.
- Per-project deployment lock.
- Command logging.
- Optional healthcheck.
- CLI suitable for later reuse by FastAPI UI.
- Environment-aware prod/dev deployment.
- Stop and status commands.

See:

- [Platform Contract](docs/platform-contract.md)
- [Architecture](docs/architecture.md)
- [Tasks](docs/tasks.md)
- [Project Template](docs/project-template.md)

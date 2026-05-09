# Architecture

The deployer is split into a reusable engine and thin interfaces.

```text
CLI / future FastAPI UI
        |
        v
DeploymentEngine
        |
        +-- Manifest loader and validator
        +-- Traefik override generator
        +-- Command runner
        +-- SQLite state store
        +-- Health checker
```

## Design Rules

- The deployer owns generated files under `.deployer/`.
- Source compose files are read-only from the deployer's point of view.
- Deployment state is explicit and stored in SQLite.
- Commands are logged as deployment artifacts.
- One project can have only one active deployment.
- Different projects may deploy concurrently later.
- The same engine must be reusable from CLI and FastAPI.

## Current CLI

```bash
deployer validate /path/to/project
deployer render-override /path/to/project
deployer deploy /path/to/project --state-db /var/lib/deployer/state.db
deployer stop /path/to/project --state-db /var/lib/deployer/state.db
deployer status /path/to/project --state-db /var/lib/deployer/state.db
deployer history --state-db /var/lib/deployer/state.db tasktrack
```

## Deployment Flow

1. Load `deployer.yml`.
2. Validate required compose files.
3. Generate `.deployer/<environment>.override.yml`.
4. Create deployment record in SQLite.
5. Acquire per-project lock.
6. Run `docker compose -p <name> -f ... up -d --build`.
7. Run optional healthcheck.
8. Mark deployment as `success` or `failed`.
9. Persist command log.

`prod` uses the base project name and `<subdomain>.<domain>`.

`dev` uses `<project>-dev` as Compose project name and `<subdomain>.dev.<domain>`.

## Future FastAPI UI

The UI should not call Docker directly. It should call the same engine service layer used by CLI.

The target workflow is service-based, not path-based. See `docs/service-catalog-plan.md`.

Initial UI screens:

- Project list.
- Deployment history.
- Deploy button.
- Live deployment log.
- Rendered override preview.

## Security Notes

The MVP CLI can use local Docker directly for development. The packaged service must use Docker socket proxy and a restricted operation set.

Secrets should not be introduced before the engine is stable. The first version should prefer local projects with existing `.env.prod` files.

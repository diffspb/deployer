# Architecture

The deployer is split into a reusable engine and thin interfaces.

```text
CLI / future UI
        |
        v
FastAPI API / ServiceCatalog
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
- The catalog owns service/source/environment state.
- The engine remains path-capable and does not know how sources are fetched.
- The UI talks to the FastAPI API, not to Docker and not to engine internals.

## Current CLI

Service catalog mode:

```bash
deployer services add myapp --git-url <url>
deployer services add-local myapp --path /path/to/project
deployer services list
deployer services show myapp
deployer services remove myapp
deployer refs myapp
deployer environments list
deployer environments add stage --url-prefix stage
deployer environments update dev --deploy-mode webhook_auto --deploy-source branch --deploy-pattern dev --pattern-type exact
deployer environments remove stage
deployer runtime-targets list myapp
deployer runtime-targets add myapp stage
deployer runtime-targets remove myapp stage
deployer env list myapp prod
deployer env set myapp prod KEY=value
deployer env unset myapp prod KEY
deployer env render myapp prod
deployer deploy myapp --environment prod --ref main --state-db /var/lib/deployer/state.db
deployer history myapp --environment prod --state-db /var/lib/deployer/state.db
deployer stop myapp --environment prod --state-db /var/lib/deployer/state.db
deployer down myapp --environment prod --state-db /var/lib/deployer/state.db
deployer restart myapp --environment prod --state-db /var/lib/deployer/state.db
deployer status myapp --environment prod --state-db /var/lib/deployer/state.db
deployer logs myapp --environment prod --tail 200 --state-db /var/lib/deployer/state.db
```

Path mode remains available for development and direct debugging:

```bash
deployer validate /path/to/project
deployer render-override /path/to/project
deployer deploy /path/to/project --state-db /var/lib/deployer/state.db
deployer stop /path/to/project --state-db /var/lib/deployer/state.db
deployer down /path/to/project --state-db /var/lib/deployer/state.db
deployer restart /path/to/project --state-db /var/lib/deployer/state.db
deployer status /path/to/project --state-db /var/lib/deployer/state.db
deployer logs /path/to/project --state-db /var/lib/deployer/state.db
deployer history --state-db /var/lib/deployer/state.db tasktrack
```

Runtime command semantics:

- `deploy` runs `docker compose up -d --build`.
- `stop` runs `docker compose stop` and keeps containers.
- `down` runs `docker compose down` and removes containers, but not images or named volumes.
- `restart` runs `docker compose restart`.
- `status` runs `docker compose ps`.
- `logs` runs `docker compose logs --tail <n>`.

Catalog `history` prints current service runtime target metadata before deployment records:

```text
service: myapp
source: git	git@example.com/myapp.git
current: prod	version=main	ref=main	commit=abc123	last_deployment=42
42	prod	deploy	success	main	2026-05-10T...
```

## Deployment Flow

Catalog mode:

1. Resolve service by name from SQLite.
2. Resolve runtime target config and render `/var/lib/deployer/services/<name>/env/<environment>.env`.
3. For git sources, fetch tags/branches and checkout requested ref.
4. Load `deployer.yml` from the managed repo or local source path.
5. Render `/var/lib/deployer/services/<name>/overrides/<environment>.override.yml`.
6. Run the same engine flow as path mode.
7. Store current version/ref/commit on successful deployment.

Path mode:

1. Load `deployer.yml`.
2. Validate required compose files.
3. Generate `.deployer/<environment>.override.yml`.
4. Create deployment record in SQLite.
5. Acquire per-project lock.
6. Run `docker compose -p <name> -f ... up -d --build`.
7. Run optional healthcheck.
8. Mark deployment as `success` or `failed`.
9. Persist command log.

Environment profiles are global platform-level definitions. `prod` and `dev` are created as defaults for existing
workflows, but operators can create additional profiles such as `stage`, `preview-123`, or project-specific names.

Service runtime targets are per-service enablements of these profiles. They store runtime state such as env vars,
current ref/commit, last deployment, jobs, and logs.

Routing uses the profile `url_prefix`:

- empty prefix -> `<subdomain>.<domain>`
- `dev` -> `<subdomain>.dev.<domain>`
- `stage` -> `<subdomain>.stage.<domain>`

Compose project names remain target-aware through `<project>-<target>` except for `prod`, which keeps the base
project name for backward compatibility.

## Future FastAPI UI

The API layer is implemented as the contract for the future UI. See `docs/api.md`.

The UI should not call Docker directly. It should call the API, which then calls the catalog/service layer, which then calls the engine.

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

# Architecture

The deployer is split into a reusable engine and thin interfaces.

```text
CLI / UI
        |
        v
FastAPI API / EnvironmentProjectCatalog
        |
        v
DeploymentEngine
        |
        +-- Project spec resolver
        +-- Optional manifest importer
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
- One environment project can have only one active deployment.
- Different environment projects may deploy concurrently later.
- The same engine must be reusable from CLI and FastAPI.
- The catalog owns environment/project/component/dependency state.
- The engine deploys a resolved project spec and does not know how sources are fetched.
- The UI talks to the FastAPI API, not to Docker and not to engine internals.
- Source repositories should not require deployer-specific files.
- A repository-local `deployer.yml` is optional import/config-as-code, not the primary contract.
- Projects are scoped to environments. There is no global deployable service that is later attached to an environment.

## Target CLI

Environment-first mode:

```bash
deployer environments list
deployer environments add stage --url-prefix stage
deployer environments remove stage

deployer projects add dev myapp --git-url <url>
deployer projects add-local dev myapp --path /path/to/project
deployer projects list dev
deployer projects show dev myapp
deployer projects refs dev myapp
deployer projects remove dev myapp

deployer components add dev myapp backend --build-context backend --dockerfile Dockerfile --port 8000
deployer endpoints add dev myapp backend --subdomain myapp --auth sso --health-path /health

deployer env list dev myapp
deployer env set dev myapp KEY=value
deployer env unset dev myapp KEY
deployer env render dev myapp

deployer deploy dev myapp --ref main
deployer history dev myapp
deployer stop dev myapp
deployer down dev myapp
deployer restart dev myapp
deployer status dev myapp
deployer logs dev myapp --tail 200
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

- `deploy` runs `docker compose --env-file <managed-env> up -d --build`.
- `stop` runs `docker compose --env-file <managed-env> stop` and keeps containers.
- `down` runs `docker compose --env-file <managed-env> down` and removes containers, but not images or named volumes.
- `restart` runs `docker compose --env-file <managed-env> restart`.
- `status` runs `docker compose --env-file <managed-env> ps`.
- `logs` runs `docker compose --env-file <managed-env> logs --tail <n>`.

Catalog `history` prints current environment project metadata before deployment records:

```text
environment: dev
project: myapp
source: git	git@example.com/myapp.git
current: version=main	ref=main	commit=abc123	last_deployment=42
42	dev/myapp	deploy	success	main	2026-05-10T...
```

## Deployment Flow

Environment project mode:

1. Resolve project by `environment + project` from SQLite.
2. Resolve source, components, endpoints, dependencies, env vars, and deploy policy.
3. For git sources, fetch tags/branches and checkout requested ref.
4. Build internal project spec. A repository-local `deployer.yml` may be imported, but is not required.
5. Render managed env files and compose files/overrides under `/var/lib/deployer/environments/<environment>/projects/<project>/`.
6. Run Docker Compose with BuildKit enabled.
7. Run configured endpoint healthchecks.
8. Store current version/ref/commit and deployment log.

Path mode:

1. Load `deployer.yml`.
2. Validate required compose files.
3. Generate `.deployer/<environment>.override.yml`.
4. Create deployment record in SQLite.
5. Acquire per-project lock.
6. Run `docker compose -p <name> --env-file <managed-env> -f ... up -d --build`.
7. Run optional healthcheck.
8. Mark deployment as `success` or `failed`.
9. Persist command log.

Environment profiles are top-level operational boundaries. Operators can create environments such as `dev`,
`stage`, `prod`, `preview-123`, or customer-specific names.

Projects are created inside environments. Creating a project in `dev` does not create anything in `prod`.
If the same repository should run in both environments, it is added twice. This removes attach/detach ambiguity
and makes deploy policy, env vars, dependencies, status, logs, and history unambiguously environment-scoped.

Routing uses the profile `url_prefix`:

- empty prefix -> `<subdomain>.<domain>`
- `dev` -> `<subdomain>.dev.<domain>`
- `stage` -> `<subdomain>.stage.<domain>`

Compose project names are environment-aware, for example `<environment>-<project>` or a sanitized equivalent.

## Future FastAPI UI

The API layer is implemented as the contract for the future UI. See `docs/api.md`.

The UI should not call Docker directly. It should call the API, which then calls the catalog/service layer, which then calls the engine.

The target workflow is environment-project-based, not path-based. See `docs/service-catalog-plan.md`.

Initial UI screens:

- Environment list.
- Project list inside an environment.
- Deployment history.
- Deploy button.
- Live deployment log.
- Rendered override preview.

## Security Notes

The MVP CLI can use local Docker directly for development. The packaged service must use Docker socket proxy and a restricted operation set.

Secrets should not be introduced before the engine is stable. The first version should prefer local projects with existing `.env.prod` files.

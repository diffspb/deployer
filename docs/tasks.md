# Tasks

## Phase 1: Contract and Engine

- [x] Write platform contract.
- [x] Write deployer architecture.
- [x] Replace `scripts/new-app.sh` direction with a project template and agent prompt.
- [x] Scaffold Python project with venv-compatible Makefile.
- [x] Implement `deployer.yml` parser and validator.
- [x] Implement Traefik override generator.
- [x] Implement SQLite deployment history.
- [x] Implement deployment engine with per-project lock.
- [x] Implement CLI commands.
- [x] Add unit tests for parser, override generator, state, and engine dry-run behavior.
- [x] Validate local sample projects: `tasktrack_project` and `test_proj`.
- [x] Review test coverage and architecture after MVP.

## Phase 1 Follow-Up

- [ ] Add DB-level project lock before running deployer as a long-lived service.
- [ ] Add rollback command based on previous successful deployment record.
- [x] Add git source support with `git ls-remote`, clone, fetch, checkout.
- [ ] Add real Docker Compose integration test gated by an explicit make target.
- [ ] Decide whether manifests live inside each project or in deployer-managed catalog.

## Core v2

- [x] Use environment-specific override files: `.deployer/prod.override.yml`, `.deployer/dev.override.yml`
- [x] Track deployment history by project and environment
- [x] Add `stop` command
- [x] Add `status` command
- [x] Add `logs` command
- [ ] Move default state DB to `/var/lib/deployer/state.db` in packaged service usage
- [x] Run CLI from inside the deployer container through Docker socket proxy

## Service Catalog v1

- [x] Document target service/source/environment model in `docs/service-catalog-plan.md`
- [x] Add `services` table
- [x] Add `environments` table
- [x] Add managed runtime layout under `/var/lib/deployer/services/<name>/`
- [x] Add git source support: clone, fetch, refs, checkout
- [x] Add local source support as debug/admin mode
- [x] Add environment variable storage
- [x] Render env files to managed workspace
- [x] Change primary CLI workflow to service names for deploy/stop/status
- [x] Keep path-based commands for development/debug use
- [x] Add `restart` command
- [x] Add `logs` command
- [x] Split `stop` and `down` command semantics
- [x] Add service-based history output enriched with current ref/commit
- [x] Add conflict-safe duplicate service handling with clearer errors
- [x] Add integration tests for git source using a real local bare repository
- [x] Add Makefile reset targets for local/test state

## Environment Projects Refactor

- [x] Replace the future plan with an environment-first model: `Environment -> Project -> Components`.
- [x] Document that source repositories should not require deployer-specific files.
- [x] Document multi-container project support: frontend, backend, workers, and internal components.
- [x] Document dependency/resource binding direction.
- [ ] Replace current SQLite schema without compatibility migrations.
- [ ] Remove global services as deployable/operator objects.
- [x] Add environment-scoped `projects` table.
- [x] Add `components` table for compose services, generated builds, and image-based containers.
- [x] Add `endpoints` table for Traefik-exposed component routes.
- [x] Add initial `dependencies` table for resource bindings.
- [x] Support jobs and deployments for environment-project runtime actions.
- [x] Add environment project catalog operations alongside the old service catalog.
- [x] Add CLI commands for environment-scoped projects, components, endpoints, dependencies, and project env.
- [ ] Replace service catalog layer with environment project catalog operations in CLI/API/UI.
- [x] Add API routes for environment-project CRUD, config, preview, and runtime actions.
- [x] Refactor engine to deploy a resolved project spec instead of requiring repository-local `deployer.yml`.
- [x] Support compose overlay mode for existing compose files.
- [x] Support generated compose mode from component definitions.
- [x] Generate Traefik labels for multiple public endpoints.
- [x] Add `environment + project` runtime command form.
- [ ] Replace old runtime CLI commands with `environment + project` commands everywhere.
- [ ] Remove `runtime-targets` CLI commands.
- [x] Fix CLI defaults so packaged service commands do not require `--state-db` or `--runtime-dir`.
- [x] Add `/api/environments/{environment}/projects/{project}` routes.
- [ ] Remove old service/runtime-target API routes after UI migration.
- [x] Rebuild UI around environment pages and environment project pages.
- [ ] Remove attach/detach flows from API after compatibility window.
- [x] Add GitHub webhook ingestion for environment project deploy policies.
- [x] Implement `webhook_auto` for one configured environment project.
- [x] Implement `webhook_gated` candidate storage and deploy.
- [ ] Implement PostgreSQL dependency binding that can use one server with separate databases/users.

## Phase 2: Runtime Hardening

- [ ] Add Docker socket proxy compose service for deployer.
- [ ] Package deployer as a Docker service behind Traefik and oauth2-proxy.
- [ ] Add deployment log streaming endpoint.
- [x] Add webhook endpoint with HMAC validation.
- [ ] Add encrypted secret storage.

## Phase 3: UI

- [x] Add minimal FastAPI API around the engine.
- [x] Document API contract in `docs/api.md`.
- [x] Add API job model for deploy/stop/down/restart polling.
- [x] Add project list screen.
- [x] Add deployment history screen.
- [x] Add deploy action and log viewer.
- [x] Redesign UI around explicit runtime targets.
- [x] Replace service cards with an environment-first service table/list.
- [x] Add `RuntimeCard(service, environment)` with scoped Deploy/Restart/Stop/Down/Logs/Env/History actions.
- [x] Remove mixed service-level runtime actions from the UI.
- [x] Replace deploy prompt with runtime-scoped deploy modal.
- [x] Make env editor scoped to one runtime target and remove the global env selector.
- [x] Add global Jobs page with service/environment filters.
- [x] Add override preview and validation errors.
- [x] Add persistent UI filters/search and better empty/error states.
- [x] Stop auto-creating `prod/dev` runtime targets for every new service.
- [x] Add environment-first UI navigation and attach flow.
- [ ] Add endpoint `health_path` field to the Web UI endpoint form.
- [ ] Add mobile navigation for small screens.

## Runtime Targets v2

- [x] Superseded by `Environment Projects Refactor`; see `docs/runtime-targets-v2-roadmap.md`.
- [x] Replace fixed `prod/dev` environment model with dynamic runtime targets loaded from state.
- [x] Add CRUD operations for runtime targets: create, delete, and list per service.
- [x] Add global environment profile CRUD for reusable environment definitions.
- [x] Add per-profile `url_prefix` instead of hardcoded `prod/dev` host logic.
- [x] Add per-profile deploy policy fields: `deploy_mode`, `deploy_source`, `deploy_pattern`, `deploy_pattern_type`.
- [x] Add per-project candidate fields for gated webhook deployments.
- [x] Generalize CLI, API, catalog, state, tests, and UI to support any number of arbitrary runtime target names.
- [x] Add GitHub webhook ingestion with HMAC validation and event audit log.
- [x] Implement webhook rule matching for branch-based deployments.
- [x] Implement webhook rule matching for tag-based deployments.
- [x] Implement `webhook_auto` mode: matching event deploys immediately.
- [x] Implement `webhook_gated` mode: matching event updates candidate without deploying.
- [x] Add UI for project deploy mode and trigger configuration.
- [x] Add UI for candidate inspection and `Deploy Candidate`.
- [ ] Add sample target setup as an example, not as a fixed environment set:
  - `dev` auto by branch push
  - `stage` auto by tag regex
  - `prod` gated by release tag regex

## Architecture Review Checklist

- [ ] UI does not duplicate deployment logic.
- [ ] Engine does not depend on FastAPI.
- [ ] Generated files are isolated under `.deployer/` for path mode and `/var/lib/deployer/services/<name>/` for catalog mode.
- [ ] Source compose files are not modified.
- [ ] Docker commands are not user-editable free text.
- [ ] Tests cover failure paths, not only happy paths.
- [ ] API runtime operations do not block UI requests.

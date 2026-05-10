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

## Phase 2: Runtime Hardening

- [ ] Add Docker socket proxy compose service for deployer.
- [ ] Package deployer as a Docker service behind Traefik and oauth2-proxy.
- [ ] Add deployment log streaming endpoint.
- [ ] Add webhook endpoint with HMAC validation.
- [ ] Add encrypted secret storage.

## Phase 3: UI

- [x] Add minimal FastAPI API around the engine.
- [x] Document API contract in `docs/api.md`.
- [x] Add API job model for deploy/stop/down/restart polling.
- [x] Add project list screen.
- [x] Add deployment history screen.
- [x] Add deploy action and log viewer.
- [ ] Redesign UI around explicit runtime targets: `service/prod` and `service/dev`.
- [ ] Replace service cards with a runtime-target-first service table/list.
- [ ] Add `RuntimeCard(service, environment)` with scoped Deploy/Restart/Stop/Down/Logs/Env/History actions.
- [ ] Remove mixed service-level runtime actions from the UI.
- [ ] Replace deploy prompt with runtime-scoped deploy modal.
- [ ] Make env editor scoped to one runtime target and remove the global env selector.
- [ ] Add global Jobs page with service/environment filters.
- [ ] Add override preview and validation errors.
- [ ] Add persistent UI filters/search and better empty/error states.
- [ ] Add mobile navigation for small screens.

## Architecture Review Checklist

- [ ] UI does not duplicate deployment logic.
- [ ] Engine does not depend on FastAPI.
- [ ] Generated files are isolated under `.deployer/` for path mode and `/var/lib/deployer/services/<name>/` for catalog mode.
- [ ] Source compose files are not modified.
- [ ] Docker commands are not user-editable free text.
- [ ] Tests cover failure paths, not only happy paths.
- [ ] API runtime operations do not block UI requests.

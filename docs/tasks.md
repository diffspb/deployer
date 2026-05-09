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
- [ ] Add git source support with `git ls-remote`, clone, fetch, checkout.
- [ ] Add real Docker Compose integration test gated by an explicit make target.
- [ ] Decide whether manifests live inside each project or in deployer-managed catalog.

## Core v2

- [x] Use environment-specific override files: `.deployer/prod.override.yml`, `.deployer/dev.override.yml`
- [x] Track deployment history by project and environment
- [x] Add `stop` command
- [x] Add `status` command
- [ ] Add `logs` command
- [ ] Move default state DB to `/var/lib/deployer/state.db` in packaged service usage
- [ ] Run CLI from inside the deployer container through Docker socket proxy

## Phase 2: Runtime Hardening

- [ ] Add Docker socket proxy compose service for deployer.
- [ ] Package deployer as a Docker service behind Traefik and oauth2-proxy.
- [ ] Add deployment log streaming endpoint.
- [ ] Add webhook endpoint with HMAC validation.
- [ ] Add encrypted secret storage.

## Phase 3: UI

- [ ] Add minimal FastAPI API around the engine.
- [ ] Add project list screen.
- [ ] Add deployment history screen.
- [ ] Add deploy action and log viewer.
- [ ] Add override preview and validation errors.

## Architecture Review Checklist

- [ ] UI does not duplicate deployment logic.
- [ ] Engine does not depend on FastAPI.
- [ ] Generated files are isolated under `.deployer/`.
- [ ] Source compose files are not modified.
- [ ] Docker commands are not user-editable free text.
- [ ] Tests cover failure paths, not only happy paths.

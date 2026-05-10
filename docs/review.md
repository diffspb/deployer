# MVP Review

Date: 2026-05-09

## Validation

Commands run:

```bash
.venv/bin/python -m pytest --cov=deployer --cov-report=term-missing
make validate-samples
```

Results:

- 18 tests passed.
- Coverage: 88.80%.
- Coverage threshold: 80%.
- `tasktrack_project` validates with `docs/sample-manifests/tasktrack.deployer.yml`.
- `test_proj` validates with `docs/sample-manifests/cpucol.deployer.yml`.
- Dry-run deployment was tested on temporary copies under `/tmp`, not by writing into the source project repositories.

## Covered Areas

- Manifest parsing and validation.
- Missing compose file detection.
- Traefik override generation.
- Explicit router-to-service labels.
- SSO middleware injection.
- SQLite deployment history.
- CLI validate/render/deploy/history paths.
- Dry-run deployment path.
- Command runner success/failure.
- Healthcheck success/failure.

## Known Gaps

- No real Docker Compose deployment test yet.
- No rollback implementation yet.
- No encrypted secrets yet.
- No Docker socket proxy integration yet.
- No FastAPI API or UI yet.
- Healthcheck currently checks the first route only.
- Status command currently shells out to `docker compose ps`; no normalized status model yet.
- Git source support is covered with a fake runner; a real local bare-repository integration test is still needed.

## Architecture Review

Current design is acceptable for the MVP because:

- Deployment logic is not coupled to FastAPI or any UI.
- Source compose files are not modified.
- Generated override files are isolated under `.deployer/`.
- Docker commands are constructed from manifest fields, not arbitrary UI-provided shell text.
- Per-project in-process lock exists.
- State is explicit and inspectable in SQLite.

Risks to address next:

- In-process locks are not enough if multiple deployer processes run. Add DB-level deployment lock before service packaging.
- Real deployment should stream logs incrementally instead of collecting command output only after process exit.
- Project manifests need to be added to real repositories or managed centrally; both modes should stay supported.
- The existing infra still mounts `docker.sock` directly in several services. The deployer service must start with socket-proxy rather than copying this pattern.

## Service Catalog v1 Review

Date: 2026-05-10

Commands run:

```bash
.venv/bin/python -m pytest --cov=deployer --cov-report=term-missing
```

Results:

- 33 tests passed.
- Coverage: 85.77%.
- Coverage threshold: 80%.

Implemented architecture changes:

- `ServiceCatalog` owns service/source/environment state.
- `DeploymentEngine` remains reusable and path-based internally.
- Catalog mode renders env files and override files under `/var/lib/deployer/services/<name>/`.
- Path mode still renders generated files under project-local `.deployer/`.
- Git operations are isolated behind `CommandRunner`, so CLI/UI layers do not construct shell commands directly.

Remaining risks:

- Duplicate service errors are still low-level SQLite errors wrapped as catalog errors.
- Git source support needs an integration test against a real local bare repository.
- Service history is still keyed by project name and does not yet show enriched catalog metadata by default.

## Runtime Commands Review

Date: 2026-05-10

Commands run:

```bash
.venv/bin/python -m pytest --cov=deployer --cov-report=term-missing
```

Results:

- 35 tests passed.
- Coverage: 85.99%.
- Coverage threshold: 80%.

Implemented behavior:

- `stop` now maps to `docker compose stop` and keeps containers.
- `down` maps to `docker compose down` and removes containers.
- `restart` maps to `docker compose restart`.
- `logs` maps to `docker compose logs --tail <n>`.
- All runtime commands support both catalog mode and path mode.

Remaining risks:

- `logs` is currently command-output based, not streaming.
- `restart` does not run a post-restart healthcheck yet.

## Catalog Hardening Review

Date: 2026-05-10

Commands run:

```bash
.venv/bin/python -m pytest --cov=deployer --cov-report=term-missing
```

Implemented behavior:

- Service-based `history` now prints current environment version/ref/commit before deployment records.
- Duplicate service creation returns a catalog-level error instead of leaking a raw SQLite constraint error.
- Git source support is covered by an integration test using a real local bare repository.
- `make reset-dev` and `make reset-test` reset local/test deployer state and runtime directories.

Remaining risks:

- Reset targets intentionally do not stop or remove Docker containers.
- Service history is still text output; API should expose structured records.

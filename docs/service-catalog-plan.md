# Service Catalog Plan

This is the next major direction for the deployer.

The current deployer can operate on a local project directory. That is useful as a low-level engine primitive, but the target user workflow is service-oriented:

- Add a service by name.
- Configure where its source comes from.
- Configure prod/dev environments.
- Deploy, stop, restart, update, and observe it from a web UI.

## Target Workflow

### Add Service

1. User opens UI and clicks "Add service".
2. User enters service name, for example `myapp`.
3. User chooses source type:
   - `git` as the primary workflow.
   - `local` as a debug/admin workflow.
   - `registry` later.
4. For git, user enters repository URL and optional credentials.
5. Deployer clones the repository into its managed workspace.
6. Deployer reads `deployer.yml` from the repo.
7. User chooses environment: `prod` or `dev`.
8. User configures environment variables for that environment.
9. Deployer stores service/environment config and can deploy it.

### Run Service

1. User opens service page.
2. User chooses `prod` or `dev`.
3. User chooses branch/tag/commit.
4. User clicks Deploy.
5. Deployer fetches source, checks out the requested ref, renders env file and override, runs Compose, then stores current version.

### Observe Services

Dashboard should show:

- user-added services;
- prod/dev status;
- current ref/tag/commit;
- last deployment status;
- links to public app URLs;
- links to logs in Dozzle;
- selected infrastructure services from Docker, for example Traefik, Keycloak, oauth2-proxy, Netdata, Dozzle.

## Data Model

### services

```text
id
name
source_type        # git | local | registry later
source_url
source_path        # managed workspace path or local path
credentials_id
default_branch
created_at
updated_at
```

### environments

```text
id
service_id
name               # prod | dev
subdomain
env_vars_json
env_file_mode      # generated | project_file | mixed
current_version
current_ref
current_commit
last_deployment_id
created_at
updated_at
```

### deployments

Existing deployment history should evolve to:

```text
id
service_id
environment
action             # deploy | stop | restart | rollback
version
ref
commit_hash
status
started_at
finished_at
log
```

### secrets

```text
id
name
type               # git_token | ssh_key | registry_credentials
encrypted_value
created_at
updated_at
```

Encryption can be implemented after the catalog shape is stable.

## Runtime Layout

Managed runtime layout:

```text
/var/lib/deployer/
  state.db
  services/
    <service-name>/
      repo/
      env/
        prod.env
        dev.env
      overrides/
        prod.yml
        dev.yml
      logs/
        deploy-<id>.log
```

The current `.deployer/<environment>.override.yml` project-local layout remains useful for local/debug mode. Managed services should use `/var/lib/deployer/services/<name>/overrides/`.

## CLI Target

Service catalog commands:

```bash
deployer services add myapp --git-url <url>
deployer services add-local myapp --path /path/to/project
deployer services list
deployer services show myapp
deployer services remove myapp
deployer refs myapp
```

Environment commands:

```bash
deployer env list myapp prod
deployer env set myapp prod KEY=value
deployer env unset myapp prod KEY
deployer env render myapp prod
```

Runtime commands:

```bash
deployer deploy myapp --environment prod --ref main
deployer stop myapp --environment prod
deployer restart myapp --environment prod
deployer status myapp --environment prod
deployer history myapp --environment prod
deployer logs myapp --environment prod
```

Path-based commands should remain available for development, but should no longer be the main user-facing workflow.

## API Target

Initial API should mirror CLI operations:

```text
GET  /api/services
POST /api/services
GET  /api/services/{name}
DELETE /api/services/{name}
GET  /api/services/{name}/refs
GET  /api/services/{name}/env/{environment}
POST /api/services/{name}/env/{environment}
POST /api/services/{name}/deploy
POST /api/services/{name}/stop
POST /api/services/{name}/restart
GET  /api/services/{name}/status
GET  /api/services/{name}/history
GET  /api/services/{name}/logs
```

## UI Target

The UI must make the split between service definition and runtime targets explicit.

Mental model:

```text
Service
  Source
  Shared settings
  Runtime target: prod
  Runtime target: dev
```

`prod` and `dev` are separate runtime targets. They can be checked out from different refs, have different env vars, different URLs, different runtime status, different logs, and different deployment history. The UI must not expose mixed service-level runtime actions such as "Deploy prod", "Deploy dev", and one shared "Stop" button in the same action group.

Service-level data:

- service name;
- source type;
- git URL or local path;
- default branch;
- source checkout status;
- current local checkout ref and commit;
- shared manifest/compose definition.

Runtime-target data:

- environment name: `prod` or `dev`;
- domain/subdomain;
- env vars;
- current deployed ref/version/commit;
- last deployment id and status;
- runtime status;
- runtime logs;
- deployment history;
- runtime actions.

### Near-Term UI Goal

Main page should be a service table or compact service list, not a card grid optimized for aesthetics. Each row should show source status and two explicit runtime blocks:

```text
Service      Source                  Production                 Development
test-app     fetched master 56028ed   ref master running         ref develop stopped
                                     Deploy Restart Stop Logs   Deploy Restart Stop Logs
```

Alternative row shape:

```text
test-app
source: fetched · master · 56028ed

[ PROD ]
url: https://test-app.busypage.ru
ref: master
commit: 56028ed
status: running
Deploy | Restart | Stop | Down | Logs | Env | History

[ DEV ]
url: https://test-app.dev.busypage.ru
ref: develop
commit: a81c3f2
status: stopped
Deploy | Restart | Stop | Down | Logs | Env | History
```

### Pages

- `Services`: main operator page. Lists service definitions and their `prod`/`dev` runtime targets.
- `Service Detail`: source and shared service settings plus runtime target summaries.
- `Runtime Detail`: focused page for one target, for example `/services/test-app/prod` or `/services/test-app/dev`.
- `Jobs`: global deployment/job audit log.
- `System`: selected infrastructure services such as Traefik, oauth2-proxy, Keycloak, Dozzle, Netdata, and deployer.

### Service Detail

Service detail should not have shared runtime buttons. It should show source/shared information and two runtime cards:

```text
Service: test-app
Source: github... fetched master 56028ed

[ Production ]
Domain: test-app.busypage.ru
Current ref: master
Current commit: 56028ed
Env vars: 3
Last deploy: success
Actions: Deploy | Restart | Stop | Down | Logs | History | Env

[ Development ]
Domain: test-app.dev.busypage.ru
Current ref: develop
Current commit: ...
Env vars: 5
Last deploy: failed
Actions: Deploy | Restart | Stop | Down | Logs | History | Env
```

### Modals And Drawers

Use modals/drawers only when they preserve context:

- `Deploy Runtime Modal`: always scoped to one runtime target, for example `Deploy test-app / prod`; environment is not selectable inside the modal.
- `Edit Env Drawer`: scoped to one runtime target.
- `Logs Drawer`: scoped to one runtime target.
- `Job Details Drawer`: scoped to one job.
- `Stop`/`Down` confirmation modal: must include service name and runtime target in the title.

### Immediate Redesign Tasks

1. Replace dashboard cards with a runtime-target-first service table/list.
2. Introduce a `RuntimeCard(service, environment)` UI component.
3. Remove service-level runtime action groups.
4. Make deploy modal accept fixed `service + environment`; do not choose environment inside it.
5. Open env editor directly for a fixed runtime target; remove the global env selector.
6. Filter jobs, history, status, and logs by `service + environment` everywhere in the UI.
7. Add global `Jobs` page after runtime actions are no longer mixed.

## Implementation Order

1. Add service catalog tables and migrations.
2. Add managed workspace path handling.
3. Implement git source clone/fetch/refs/checkout.
4. Implement environment variable storage and env file rendering.
5. Change main CLI to operate by service name.
6. Keep path-based commands as development commands.
7. Add API skeleton.
8. Add minimal UI.
9. Redesign UI around explicit runtime targets.

# Service Catalog Plan

This is the next major direction for the deployer.

The current deployer can operate on a local project directory. That is useful as a low-level engine primitive, but the target user workflow is service-oriented:

- Add a service by name.
- Configure where its source comes from.
- Configure any number of runtime targets, for example `dev`, `stage`, `prod`,
  preview targets, or customer-specific targets.
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
7. User creates one or more runtime targets with operator-defined names.
8. User configures deployment policy and environment variables for each runtime target.
9. Deployer stores service/runtime-target config and can deploy it.

### Run Service

1. User opens service page.
2. User chooses a runtime target.
3. User chooses branch/tag/commit, unless the target is driven by an automation policy.
4. User clicks Deploy.
5. Deployer fetches source, checks out the requested ref, renders env file and override, runs Compose, then stores current version.

### Observe Services

Dashboard should show:

- user-added services;
- runtime target status;
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
name               # operator-defined runtime target name
url_prefix         # "", "dev", "stage", or any custom prefix segment
env_vars_json
env_file_mode      # generated | project_file | mixed
deploy_mode        # manual | webhook_auto | webhook_gated
deploy_source      # branch | tag | ref later
deploy_pattern     # exact branch name or regex/glob depending on source type
deploy_pattern_type # exact | regex
auto_deploy_enabled
last_webhook_event_id
last_webhook_ref
last_webhook_commit
last_webhook_at
current_version
current_ref
current_commit
last_deployment_id
created_at
updated_at
```

Notes:

- `runtime target` is a better mental model than a fixed `environment` enum.
- `url_prefix` controls the generated host prefix. Examples:
  - `prod` with empty prefix -> `myapp.busypage.ru`
  - `dev` with prefix `dev` -> `myapp.dev.busypage.ru`
  - `stage` with prefix `stage` -> `myapp.stage.busypage.ru`
- `deploy_mode`:
  - `manual`: deploy only from UI/CLI.
  - `webhook_auto`: matching webhook immediately schedules a deploy.
  - `webhook_gated`: matching webhook is stored as the latest candidate version; operator deploys it manually later.
- `deploy_source` and `deploy_pattern*` define how a webhook is matched:
  - branch exact match, for example `dev`
  - tag regex, for example `^v[0-9]+\.[0-9]+\.[0-9]+-rc[0-9]+$`

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
        <target>.env
      overrides/
        <target>.yml
      logs/
        deploy-<id>.log
      webhooks/
        last-event.json
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

Runtime target commands:

```bash
deployer environments list
deployer environments add stage --url-prefix stage
deployer environments update prod --deploy-mode webhook_gated --deploy-source tag --deploy-pattern '^v[0-9]+\.[0-9]+\.[0-9]+$' --pattern-type regex
deployer environments remove stage
deployer runtime-targets add myapp stage
deployer runtime-targets remove myapp stage
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
deployer webhook github --event push --payload /tmp/payload.json
deployer deploy-candidate myapp prod
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
GET  /api/services/{name}/runtime-targets
POST /api/services/{name}/runtime-targets
PATCH /api/services/{name}/runtime-targets/{environment}
DELETE /api/services/{name}/runtime-targets/{environment}
GET  /api/services/{name}/env/{environment}
POST /api/services/{name}/env/{environment}
POST /api/services/{name}/deploy
POST /api/services/{name}/stop
POST /api/services/{name}/restart
GET  /api/services/{name}/status
GET  /api/services/{name}/history
GET  /api/services/{name}/logs
POST /api/webhooks/github
GET  /api/services/{name}/runtime-targets/{environment}/candidate
POST /api/services/{name}/runtime-targets/{environment}/deploy-candidate
```

## UI Target

The UI must make the split between service definition and runtime targets explicit.

Mental model:

```text
Service
  Source
  Shared settings
  Runtime target: <name>
  Runtime target: <name>
  Runtime target: <name>
```

Runtime targets are separate deployable units. They can be checked out from different refs, have different env vars, different URLs, different runtime status, different logs, different deployment history, and different automation policies. The UI must not expose mixed service-level runtime actions such as "Deploy dev", "Deploy stage", "Deploy prod", and one shared "Stop" button in the same action group.

Service-level data:

- service name;
- source type;
- git URL or local path;
- default branch;
- source checkout status;
- current local checkout ref and commit;
- shared manifest/compose definition.

Runtime-target data:

- runtime target name;
- domain/subdomain or generated host prefix;
- env vars;
- deploy mode and webhook rules;
- latest webhook candidate, if the target is gated;
- current deployed ref/version/commit;
- last deployment id and status;
- runtime status;
- runtime logs;
- deployment history;
- runtime actions.

### Near-Term UI Goal

Main page should be a service table or compact service list, not a card grid optimized for aesthetics. Each runtime target should have its own row:

```text
Service      Target      Public URL                         Status      Ref       Actions
test-app     dev         https://test-app.dev.busypage.ru    running     develop   ...
test-app     stage       https://test-app.stage.busypage.ru  stopped     v1-rc1    ...
test-app     prod        https://test-app.busypage.ru        running     v1.0.0    ...
```

Service detail may group the same targets under the shared service settings:

```text
test-app
source: fetched · master · 56028ed

[ <target-name> ]
url: https://test-app.dev.busypage.ru
ref: develop
commit: a81c3f2
status: stopped
Deploy | Restart | Stop | Down | Logs | Env | History
```

### Pages

- `Services`: main operator page. Lists service definitions and all runtime targets.
- `Service Detail`: source and shared service settings plus runtime target summaries.
- `Runtime Detail`: focused page for one target, for example `/services/test-app/dev`, `/services/test-app/stage`, or `/services/test-app/prod`.
- `Jobs`: global deployment/job audit log.
- `Webhook Events`: global inbound webhook audit log and candidate queue.
- `System`: selected infrastructure services such as Traefik, oauth2-proxy, Keycloak, Dozzle, Netdata, and deployer.

### Service Detail

Service detail should not have shared runtime buttons. It should show source/shared information and one card per runtime target:

```text
Service: test-app
Source: github... fetched master 56028ed

[ Target: dev ]
Domain: test-app.dev.busypage.ru
Deploy mode: webhook_auto
Trigger: branch == dev
Current ref: dev
Current commit: ...
Env vars: 5
Last deploy: success
Actions: Deploy | Restart | Stop | Down | Logs | History | Env

[ Target: stage ]
Domain: test-app.stage.busypage.ru
Deploy mode: webhook_auto
Trigger: tag matches ^v.+-rc[0-9]+$
Current ref: v1.2.0-rc1
Current commit: ...
Env vars: 4
Last deploy: success
Actions: Deploy | Restart | Stop | Down | Logs | History | Env

[ Target: prod ]
Domain: test-app.busypage.ru
Deploy mode: webhook_gated
Trigger: tag matches ^v[0-9]+\.[0-9]+\.[0-9]+$
Pending candidate: v1.2.0
Current ref: v1.1.4
Current commit: 56028ed
Env vars: 3
Last deploy: success
Actions: Deploy | Deploy Candidate | Restart | Stop | Down | Logs | History | Env
```

### Modals And Drawers

Use modals/drawers only when they preserve context:

- `Deploy Runtime Modal`: always scoped to one runtime target, for example `Deploy test-app / prod`; environment is not selectable inside the modal.
- `Edit Env Drawer`: scoped to one runtime target.
- `Logs Drawer`: scoped to one runtime target.
- `Job Details Drawer`: scoped to one job.
- `Stop`/`Down` confirmation modal: must include service name and runtime target in the title.
- `Webhook Candidate Drawer`: scoped to one runtime target; shows the latest matching event, commit, tag/branch, and allows `Deploy Candidate`.

## Webhook Model

Initial webhook provider: GitHub.

Supported event types in the first version:

- `push` for branch-based automation.
- `create` for tag-based automation if needed.
- `push` with tag refs may also be enough if GitHub delivers the needed ref details consistently for your workflow.

Processing flow:

1. GitHub sends a signed webhook to the deployer.
2. Deployer validates HMAC signature and stores raw event metadata in a webhook log.
3. Deployer resolves affected service(s) by repository URL.
4. Deployer evaluates each runtime target policy:
   - branch exact/regex match
   - tag exact/regex match
5. If target policy is `webhook_auto`, deploy starts immediately.
6. If target policy is `webhook_gated`, the event becomes the latest candidate for that target.
7. UI shows candidate status and lets operator deploy that exact candidate.

Minimal policy examples, not required target names:

- `dev`: `webhook_auto`, `deploy_source=branch`, `deploy_pattern=dev`, `deploy_pattern_type=exact`
- `stage`: `webhook_auto`, `deploy_source=tag`, `deploy_pattern=^v.+-rc[0-9]+$`, `deploy_pattern_type=regex`
- `prod`: `webhook_gated`, `deploy_source=tag`, `deploy_pattern=^v[0-9]+\.[0-9]+\.[0-9]+$`, `deploy_pattern_type=regex`

The operator may create fewer targets, more targets, or differently named
targets. Webhook matching and deployment policy are properties of each runtime
target, not of a predefined environment type.

## Current Refactor Goal

The codebase must use an environment-first mental model. A service is first registered in the catalog as a shared
source definition. It becomes deployable only after the operator explicitly attaches it to one or more environment
profiles. Creating a new service must not create `prod`, `dev`, or any other runtime target automatically.

This refactor should preserve these invariants:

- runtime actions are always scoped to `service + runtime-target`
- shared service data remains separate from runtime-target data
- environment pages list only services explicitly attached to that environment
- service pages show shared source settings and the attached environments
- UI never constructs deploy logic itself; it only configures or triggers backend workflows

### Immediate Redesign Tasks

1. Replace dashboard cards with an environment-first service table/list.
2. Make the sidebar show environments first and services under each environment.
3. Remove service-level runtime action groups.
4. Make deploy modal accept fixed `service + environment`; do not choose environment inside it.
5. Open env editor directly for a fixed runtime target; remove the global env selector.
6. Filter jobs, history, status, and logs by `service + environment` everywhere in the UI.
7. Add an attach flow so a catalog service can be added to an environment explicitly.

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

# Runtime Targets v2 Roadmap

This document describes the target deployer model after moving from fixed `prod/dev`
environments to dynamic runtime targets with webhook-driven deployment policies.

The immediate business goal is:

- launch `dev` deployments automatically from GitHub webhooks

That goal must not create technical debt that blocks:

- adding any number of runtime targets
- adding gated targets
- adding resource isolation
- adding future target-specific infrastructure policy

## Current State

Today the deployer assumes:

- only two runtime names exist: `prod` and `dev`
- API validation uses a fixed enum
- catalog validation uses a fixed enum
- URL generation assumes:
  - `prod` => base domain
  - `dev` => `.dev.` host segment
- UI renders `prod` and `dev` explicitly in loops, labels, filters, pages, and actions
- state model treats environments as a fixed pair attached to every service
- no webhook model exists
- no resource binding model exists

This is good enough for the current MVP, but it is the wrong base for:

- any additional target names
- custom target names
- branch/tag-trigger policies
- gated deployment candidates
- future isolation rules

## Target Model

### Service

A service represents shared application identity:

- service name
- source type
- source URL or local path
- source credentials
- default branch
- source checkout status
- shared manifest and compose definition

Service-level data must not contain runtime behavior assumptions such as:

- fixed environment names
- fixed domains
- fixed branch/tag deploy rules

### Runtime Target

A runtime target is the deployable unit.

Examples, not a fixed set:

- `myapp/dev`
- `myapp/stage`
- `myapp/prod`
- `myapp/preview-123`
- `myapp/customer-a`

Each runtime target owns:

- `name`
- `url_prefix`
- env vars
- current deployed ref/version/commit
- deployment history
- runtime status
- logs
- deploy policy
- webhook candidate state
- future isolation policy

### Deploy Policy

Each runtime target has an explicit deploy policy.

#### `manual`

- deploy only from UI or CLI
- no automatic action from webhooks

#### `webhook_auto`

- webhook event is matched against target rules
- matching event immediately schedules a deploy

#### `webhook_gated`

- webhook event is matched against target rules
- matching event is stored as the latest candidate
- operator later clicks `Deploy Candidate`

### Webhook Match Rules

The first provider should be GitHub.

Each runtime target should define:

- `deploy_source`
  - `branch`
  - `tag`
- `deploy_pattern`
- `deploy_pattern_type`
  - `exact`
  - `regex`

Policy examples:

- `dev`:
  - `deploy_mode=webhook_auto`
  - `deploy_source=branch`
  - `deploy_pattern=dev`
  - `deploy_pattern_type=exact`

- `stage`:
  - `deploy_mode=webhook_auto`
  - `deploy_source=tag`
  - `deploy_pattern=^v.+-rc[0-9]+$`
  - `deploy_pattern_type=regex`

- `prod`:
  - `deploy_mode=webhook_gated`
  - `deploy_source=tag`
  - `deploy_pattern=^v[0-9]+\.[0-9]+\.[0-9]+$`
  - `deploy_pattern_type=regex`

These names are only sample target configurations. The model must allow an
operator to create as many targets as needed and assign any supported deploy
policy to each target.

### Resource Bindings

Runtime targets must not be modeled as only `URL + branch + env vars`.

Applications also depend on infrastructure resources:

- PostgreSQL
- Redis
- RabbitMQ
- S3/MinIO
- external APIs

The long-term target model should include resource bindings per runtime target.

Examples:

- `myapp/dev -> postgres-main / database myapp_dev / user myapp_dev`
- `myapp/stage -> postgres-main / database myapp_stage / user myapp_stage`
- `myapp/prod -> postgres-main / database myapp / user myapp`

At first, bindings may still be materialized as env vars such as `DATABASE_URL`, but the
logical model should already treat them as target-scoped bindings.

## Isolation Direction

Isolation should be a property of the runtime target, not a special case of `prod`.

Target fields should be designed so future isolation can evolve without another model rewrite.

Relevant future dimensions:

- `network_scope`
- `volume_scope`
- `secret_scope`
- `resource_profile`
- `exposure_policy`
- `isolation_mode`

Important principle:

- no target must share production data accidentally unless that sharing is an
  explicit, visible configuration decision

Practical minimum policy:

- PostgreSQL:
  - separate database per target
  - preferably separate user per target
- Redis:
  - separate DB number or separate key prefix per target
- RabbitMQ:
  - separate vhost per target
- S3/MinIO:
  - separate bucket or at least separate prefix plus access policy per target

Recommended naming convention:

- postgres db: `<service>_<target>`
- postgres user: `<service>_<target>`
- redis prefix: `<service>:<target>:`
- rabbitmq vhost: `/<service>-<target>`

## Architecture Rules

The migration must preserve these rules:

- runtime actions are always scoped to `service + runtime-target`
- UI does not encode deployment logic
- engine stays reusable from CLI and API
- source compose files remain read-only
- generated files remain deployer-owned
- webhook handling is backend-owned
- candidate selection is explicit and auditable
- target-specific routing policy stays separate from target-specific deploy policy
- target-specific deploy policy stays separate from target-specific isolation policy

## Phased Migration

The migration should happen in the following order.

### Phase 0: Freeze The Target Contract

Goal:

- agree on the Runtime Targets v2 model before backend refactors

Work:

- document dynamic runtime targets
- document deploy policies
- document resource bindings
- document isolation direction

Status:

- this document covers that phase

### Phase 1: Generalize State And Catalog

Goal:

- remove fixed `prod/dev` assumptions from the backend data model

Work:

- replace fixed environment pair with dynamic runtime target rows
- add CRUD operations for runtime targets
- add per-target fields:
  - `url_prefix`
  - `deploy_mode`
  - `deploy_source`
  - `deploy_pattern`
  - `deploy_pattern_type`
  - candidate metadata
- keep existing `prod` and `dev` attachments for current services during migration
- do not auto-create any runtime target for newly added services
- make `history`, `status`, `logs`, `env`, and `deploy` work with arbitrary target names

Acceptance:

- service may have any number of runtime targets
- newly added services start as catalog entries until explicitly attached to an environment
- arbitrary target names can be created without code changes
- no webhook behavior yet

### Phase 2: Generalize Routing And Override Generation

Goal:

- remove hardcoded `prod/dev` host naming from routing logic

Work:

- replace special `.dev.` logic with target `url_prefix`
- define host generation rules:
  - empty prefix => `myapp.busypage.ru`
  - `dev` => `myapp.dev.busypage.ru`
  - `stage` => `myapp.stage.busypage.ru`
- keep compose project names target-aware
- keep generated env and override files target-aware

Acceptance:

- arbitrary targets render stable URLs and override files

### Phase 3: Generalize API And UI

Goal:

- make runtime targets first-class in API and UI using an environment-first layout

Work:

- replace fixed `prod/dev` validation in API
- add runtime target CRUD endpoints
- change UI lists, filters, sidebar, detail pages, and deploy modal to render environments containing services
- add an explicit attach flow from service catalog entry to environment
- add target settings page:
  - URL prefix
  - deploy mode
  - branch/tag trigger configuration
- preserve current runtime-scoped actions

Acceptance:

- operator can create, update, and delete runtime targets
- operator can configure target policies from UI
- UI never assumes a fixed target count or a fixed target name set

### Phase 4: Add Webhook Ingestion

Goal:

- receive GitHub events safely and evaluate them against target rules

Work:

- add GitHub webhook endpoint
- add HMAC validation
- add webhook event audit log
- resolve affected service by repository URL
- evaluate runtime target policies
- store matched candidate data

Acceptance:

- webhook events are stored and auditable
- matching logic works for branch and tag rules
- still no automatic deploy required for all targets

### Phase 5: Deliver The First Business Goal

Goal:

- automatic `dev` deploy from GitHub webhook

Work:

- configure `dev` target:
  - `deploy_mode=webhook_auto`
  - `deploy_source=branch`
  - `deploy_pattern=dev`
  - `deploy_pattern_type=exact`
- on matching event:
  - fetch source
  - checkout pushed ref
  - schedule deploy
  - record job and deployment history normally

Acceptance:

- push to branch `dev` triggers deploy of target `dev`
- same implementation path supports any future target and policy combination
- no `prod/dev` special-casing is added

### Phase 6: Add Additional Target Policies

Goal:

- prove that the same model supports additional automatic and gated targets

Work:

- configure an automatic tag-based target, for example `stage`:
  - `webhook_auto`
  - tag regex
- configure a gated target, for example `prod`:
  - `webhook_gated`
  - release tag regex
- add candidate inspection UI
- add `Deploy Candidate`

Acceptance:

- tag event may auto-deploy the configured tag-based target
- release tag event may update a gated target candidate without deploying
- operator can promote exact candidate to the chosen target

### Phase 7: Add Resource Binding Model

Goal:

- stop treating target-scoped infrastructure only as free-form env vars

Work:

- define target resource bindings
- map bindings to injected env vars
- add validation rules so target cannot accidentally point at the wrong namespace

Acceptance:

- target resource topology is explicit
- a non-production target cannot silently reuse a production resource namespace by mistake

## Why `dev by webhook` Must Wait For The Refactor

The tempting shortcut would be:

- add a GitHub webhook endpoint
- hardcode branch `dev`
- hardcode deploy target `dev`

That would create debt immediately:

- no reusable model for other target names
- no reusable model for gated targets
- more `prod/dev` conditionals across API and UI
- later migration would require deleting webhook code, not extending it

The correct interpretation of the business goal is:

- `dev by webhook` is the first delivered example of the generic policy model
- not a one-off special branch hack
- target names and target count remain operator-defined

## Recommended Immediate Sequence

The next implementation order should be:

1. backend state and catalog refactor to dynamic runtime targets
2. routing and override generalization by `url_prefix`
3. API and UI generalization
4. GitHub webhook ingestion and audit log
5. `dev` auto-deploy by branch webhook
6. optional automatic tag-based target, for example `stage`
7. optional gated release target, for example `prod`
8. resource binding model

## Near-Term Done Criteria

We can say the Runtime Targets v2 foundation is ready when:

- backend no longer assumes only `prod/dev`
- UI renders arbitrary target names
- one service can own any number of runtime targets
- GitHub webhook rules are stored per target
- `dev by webhook` works through the same generic policy model that will later power any other target

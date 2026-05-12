# Environment Project Plan

This is the next major direction for the deployer.

The previous catalog model treated a `service` as a shared application entry and then
attached it to one or more runtime targets. That model still allowed confusion: it
looked like the same service existed outside environments, and UI/actions had to keep
joining `service + environment`.

The target model is simpler:

```text
Environment
  Project
    Components
    Dependencies
    Deploy policy
```

A deployable project exists only inside one environment. If the same repository must
run in `dev` and `prod`, the operator adds it twice: once under `dev`, once under
`prod`. This intentionally duplicates a small amount of configuration to remove
runtime ambiguity.

No migration compatibility is required for this refactor. The current SQLite state can
be reset when this model is implemented.

## Core Objects

### Environment

An environment is the top-level operational boundary.

It owns:

- name, for example `dev`, `stage`, `prod`, `preview-123`, or `customer-a`;
- URL prefix, for example empty, `dev`, `stage`, or any custom segment;
- public Docker network;
- default internal network policy;
- deploy policy defaults;
- managed components available to projects, for example shared PostgreSQL, Redis,
  RabbitMQ, or object storage;
- future isolation settings.

The environment is not a fixed enum. Operators can create as many environments as
needed.

### Project

A project is one deployable repository or local source inside one environment.

It owns:

- project name inside the environment;
- source type: `git` as primary, `local` as admin/debug, `registry` later;
- source URL or local path;
- source credentials reference;
- selected branch, tag, or commit;
- deploy mode and webhook policy;
- project-level env vars;
- current deployed ref and commit;
- deployment history and jobs;
- generated runtime files.

The same repository in two environments is represented by two projects:

```text
dev/tasktrack
prod/tasktrack
```

They may use different branches, different env vars, different dependencies, different
domains, and different deploy policies.

### Components

A component is one container/service that belongs to a project.

Examples:

- `backend` from `backend/Dockerfile`;
- `frontend` from `frontend/Dockerfile`;
- `worker` from `backend/Dockerfile` with a different command;
- `scheduler`;
- `migrations`.

Each component owns:

- compose service name to generate or override;
- build context;
- Dockerfile path;
- image name/tag if an external image is used;
- command override when needed;
- env vars or env var references;
- public endpoint definitions, if the component is exposed through Traefik;
- healthcheck definition, if the component is health checked.

The deployer must support multi-container repositories. A project can expose zero, one,
or many public HTTP endpoints.

### Dependencies

Dependencies describe resources used by the project.

Examples:

- PostgreSQL database on a shared environment PostgreSQL instance;
- Redis namespace or database;
- RabbitMQ vhost;
- S3/MinIO bucket or prefix;
- external API credentials.

The first implementation may materialize dependencies as env vars, but the model should
not treat them as arbitrary text forever. The target direction is explicit bindings:

```text
dev/tasktrack -> postgres-main database tasktrack_dev user tasktrack_dev
prod/tasktrack -> postgres-main database tasktrack user tasktrack
```

## Source Repository Contract

The deployer should not require modifying the original project.

The preferred workflow is external configuration stored in deployer state and editable
from UI. A repository-local `deployer.yml` may remain supported as an optional import
format, but it must not be mandatory.

Minimum project expectations:

- the repository can build container images with Dockerfile or Docker Compose;
- runtime configuration is accepted through environment variables;
- public HTTP components listen on known container ports;
- health endpoints are recommended but can be configured in deployer;
- stateful resource names must not be hardcoded in application code.

## Deployment Flow

1. Operator opens an environment page.
2. Operator adds a project to that environment.
3. Operator selects source:
   - git repository and credentials;
   - or local folder for admin/debug workflows.
4. Deployer clones or references the source in managed storage.
5. Operator configures components:
   - use existing compose files; or
   - define generated compose components from build contexts and Dockerfiles.
6. Operator configures public endpoints for selected components.
7. Operator configures dependencies and env vars.
8. Operator chooses deploy policy:
   - manual;
   - webhook auto;
   - webhook gated.
9. Deployer fetches source, checks out the selected ref, renders env files and compose
   overrides or generated compose, runs Docker Compose, performs healthchecks, and
   records current ref/commit.

## Routing Rules

Environment URL prefix controls public host generation:

- empty prefix -> `<endpoint>.<domain>`;
- `dev` -> `<endpoint>.dev.<domain>`;
- `stage` -> `<endpoint>.stage.<domain>`;
- custom prefix -> `<endpoint>.<prefix>.<domain>`.

Routing is configured per public endpoint, not per project as a whole.

Example:

```text
dev/tasktrack frontend -> tasktrack.dev.busypage.ru
dev/tasktrack backend  -> api.tasktrack.dev.busypage.ru
prod/tasktrack frontend -> tasktrack.busypage.ru
prod/tasktrack backend  -> api.tasktrack.busypage.ru
```

## Compose Strategy

The deployer should support two project configuration modes.

### Compose Overlay Mode

Use the repository's existing compose files and generate deployer-owned overrides:

- inject managed env files;
- inject high-priority `environment` values;
- attach public components to the Traefik network;
- add Traefik labels for public endpoints;
- keep source compose files read-only.

This is closest to the current implementation.

### Generated Compose Mode

Generate the compose project from component definitions:

- build context;
- Dockerfile;
- image;
- command;
- env;
- networks;
- labels;
- dependencies.

This allows deploying repositories that do not have a useful production compose file.

## Webhook Model

Webhook policy belongs to the environment project, not to a global service.

Supported initial policies:

- `manual`: only deploy from UI/CLI;
- `webhook_auto`: matching webhook schedules a deploy immediately;
- `webhook_gated`: matching webhook stores a candidate; operator deploys it manually.

Match rules:

- source: `branch` or `tag`;
- pattern;
- pattern type: `exact` or `regex`.

Examples:

```text
dev/tasktrack: webhook_auto branch exact dev
stage/tasktrack: webhook_auto tag regex ^v.+-rc[0-9]+$
prod/tasktrack: webhook_gated tag regex ^v[0-9]+\.[0-9]+\.[0-9]+$
```

These are examples only. The model must support any environment names and any number of
environment projects.

## UI Target

The UI should be environment-first.

Primary navigation:

```text
Environments
  dev
    tasktrack
    paas-test
  prod
    tasktrack
Jobs
Webhook Events
System
```

Main work happens on environment pages:

- list projects in this environment;
- show public URLs, runtime status, health, ref/commit, last job;
- add project to this environment;
- configure environment resources.

Project page inside an environment:

- source settings;
- deploy policy;
- components;
- endpoints;
- dependencies;
- env vars;
- jobs/history/logs;
- deploy/restart/stop/down actions.

There should be no global service page that mixes environments. Cross-environment
comparison can be added later as a reporting page, not as the primary control surface.

## CLI Target

The CLI should mirror the environment-first model.

Examples:

```bash
deployer environments list
deployer environments add dev --url-prefix dev
deployer environments add prod --url-prefix ""

deployer projects add dev tasktrack --git-url git@github.com:org/tasktrack.git --compose-file docker-compose.yml
deployer projects add prod tasktrack --git-url git@github.com:org/tasktrack.git
deployer projects show dev tasktrack

deployer components add dev tasktrack backend --build-context backend --dockerfile Dockerfile --port 8000
deployer components add dev tasktrack frontend --build-context frontend --dockerfile Dockerfile --port 3000
deployer endpoints add dev tasktrack web frontend --port 3000 --subdomain tasktrack --auth sso
deployer endpoints add dev tasktrack api backend --port 8000 --subdomain api.tasktrack --auth sso --health-path /api/v1/health
deployer dependencies add dev tasktrack postgres --type postgres --target postgres-main/tasktrack_dev --output DATABASE_URL=postgresql://...

deployer projects env-set dev tasktrack APP_ENV=dev
deployer deploy dev tasktrack --ref dev
deployer restart dev tasktrack
deployer stop dev tasktrack
deployer logs dev tasktrack --component backend
deployer status dev tasktrack
```

For Dockerfile/image-only projects, use `deployer projects add ... --no-compose-file` and let deployer generate
the service definitions from components. `deployer.yml` is optional legacy/import input, not a required source
repository file.

The CLI must not require operators to know Docker container names.

## API Target

Initial API shape:

```text
GET    /api/environments
POST   /api/environments
GET    /api/environments/{environment}
PATCH  /api/environments/{environment}
DELETE /api/environments/{environment}

GET    /api/environments/{environment}/projects
POST   /api/environments/{environment}/projects
GET    /api/environments/{environment}/projects/{project}
PATCH  /api/environments/{environment}/projects/{project}
DELETE /api/environments/{environment}/projects/{project}

GET    /api/environments/{environment}/projects/{project}/components
POST   /api/environments/{environment}/projects/{project}/components
PATCH  /api/environments/{environment}/projects/{project}/components/{component}
DELETE /api/environments/{environment}/projects/{project}/components/{component}

GET    /api/environments/{environment}/projects/{project}/endpoints
POST   /api/environments/{environment}/projects/{project}/endpoints
PATCH  /api/environments/{environment}/projects/{project}/endpoints/{endpoint}
DELETE /api/environments/{environment}/projects/{project}/endpoints/{endpoint}

GET    /api/environments/{environment}/projects/{project}/env
POST   /api/environments/{environment}/projects/{project}/env

POST   /api/environments/{environment}/projects/{project}/deploy
POST   /api/environments/{environment}/projects/{project}/restart
POST   /api/environments/{environment}/projects/{project}/stop
POST   /api/environments/{environment}/projects/{project}/down
GET    /api/environments/{environment}/projects/{project}/status
GET    /api/environments/{environment}/projects/{project}/logs
GET    /api/environments/{environment}/projects/{project}/history

POST   /api/webhooks/github
GET    /api/webhook-events
GET    /api/jobs
```

## Implementation Order

1. Freeze this environment-first contract.
2. Replace state schema with environments, projects, components, endpoints,
   dependencies, env vars, jobs, deployments, webhook events.
3. Remove global services and service-to-environment attachment code.
4. Refactor catalog/service layer into environment project operations.
5. Refactor engine inputs so it deploys a resolved project spec, not only
   repository-local `deployer.yml`.
6. Add compose overlay mode for existing compose projects.
7. Add multi-endpoint override generation.
8. Add generated compose mode for component-defined projects.
9. Refactor API to environment-first routes.
10. Refactor UI to environment pages and environment project pages.
11. Fix CLI defaults and expose short environment-first commands.
12. Add GitHub webhook ingestion and audit log.
13. Implement webhook auto deploy for an environment project.
14. Add gated candidate deploy.
15. Add explicit dependency/resource binding model.

## Near-Term Done Criteria

The refactor is ready when:

- no global service catalog remains in the operator model;
- projects are always scoped by environment;
- adding the same repository to two environments creates two independent projects;
- a project can define multiple components;
- a project can expose multiple public endpoints;
- source repositories can be deployed without adding `deployer.yml`;
- all runtime actions are addressed as `environment + project`;
- CLI, API, and UI use the same model.

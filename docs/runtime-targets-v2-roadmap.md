# Environment Projects Roadmap

This document replaces the older Runtime Targets v2 direction.

The previous direction generalized `prod/dev` into dynamic runtime targets attached to
global services. That was better than fixed environments, but still kept the wrong
primary object: services existed globally and then had to be attached to environments.

The new direction is environment-first:

```text
Environment -> Project -> Components -> Endpoints / Dependencies
```

No migration compatibility is required. The current development database may be reset
when this refactor lands.

## Business Goal

The nearest business goal remains:

- deploy a development project automatically from GitHub webhooks.

But it must be implemented through a generic environment project policy, not through a
hardcoded `dev` shortcut.

Correct interpretation:

- create an environment, for example `dev`;
- add a project to that environment;
- configure the project to deploy from branch `dev`;
- configure `webhook_auto`;
- GitHub push to that branch deploys only that environment project.

## Target Model

### Environment

An environment defines the operational boundary:

- name;
- URL prefix;
- public Docker network;
- internal network policy;
- managed/shared resources;
- default deploy policy settings;
- future isolation policy.

Examples:

- `dev` with URL prefix `dev`;
- `stage` with URL prefix `stage`;
- `prod` with empty URL prefix;
- `preview-123` with URL prefix `preview-123`.

These are examples only. Environment names are operator-defined.

### Project

A project is scoped to exactly one environment.

Examples:

- `dev/tasktrack`;
- `prod/tasktrack`;
- `stage/tasktrack`;
- `dev/paas-test`.

The same repository added to two environments becomes two independent projects. This is
intentional because it makes source ref, env vars, dependencies, deploy policy, status,
jobs, and logs unambiguous.

Project fields:

- environment id;
- name;
- source type: git, local, registry later;
- source URL or path;
- credentials reference;
- selected/default ref;
- deploy mode;
- webhook source/pattern;
- env vars;
- current ref and commit;
- last successful deployment;
- latest candidate for gated webhook deploys.

### Components

Components describe containers belonging to one project:

- name;
- mode: existing compose service, generated build, or external image;
- compose service name;
- build context;
- Dockerfile;
- image;
- command;
- env vars;
- dependency references.

A repository may define several components, for example frontend, backend, worker, and
scheduler.

### Endpoints

Endpoints expose selected components through Traefik:

- endpoint name;
- component name;
- container port;
- host or subdomain;
- path rules;
- auth mode;
- middlewares;
- healthcheck path.

One project can expose multiple endpoints.

### Dependencies

Dependencies are project-scoped bindings to environment resources:

- PostgreSQL database/user on a shared PostgreSQL instance;
- Redis database or key prefix;
- RabbitMQ vhost;
- S3 bucket or prefix;
- external API credentials.

The first implementation can inject dependency outputs as env vars, but the logical
model must keep them as bindings so environments do not accidentally share state.

## Source Repository Contract

The source repository should not have to contain deployer-specific files.

Supported configuration sources, in priority order:

1. deployer state edited through UI/CLI;
2. optional deployer-managed external spec;
3. optional repository-local `deployer.yml` import for teams that want config-as-code.

The repository must only provide buildable application code, Dockerfiles or Compose
files, and env-driven runtime configuration.

## Phased Refactor

### Phase 0: Freeze Contract

Goal:

- align documents and implementation plan on the environment-first model.

Work:

- document Environment -> Project -> Components;
- document zero-modification repository workflow;
- document multi-container support;
- document dependency/resource binding direction;
- mark old service/runtime-target model as superseded.

Acceptance:

- tasks and architecture docs no longer describe global services as the future model.

### Phase 1: Replace State Shape

Goal:

- remove global services and service-environment attachments.

Work:

- replace `services` with environment-scoped `projects`;
- add `components`;
- add `endpoints`;
- add initial `dependencies`;
- keep `deployments` and `jobs`, but scope them by `environment + project`;
- reset development database instead of writing compatibility migrations.

Acceptance:

- a project cannot exist outside an environment;
- the same project name may exist in different environments;
- runtime actions can be uniquely addressed by `environment + project`.

### Phase 2: Refactor Catalog/API/CLI

Goal:

- make all operator operations environment-first.

Work:

- replace `services ...` commands with `projects ...` commands;
- replace `runtime-targets ...` commands with environment project operations;
- update API routes to `/api/environments/{environment}/projects/{project}`;
- fix CLI defaults so server commands do not require `--state-db`;
- remove attach/detach flows.

Acceptance:

- CLI does not require Docker container names or state DB flags in packaged service;
- UI/API/CLI all use environment + project addressing.

### Phase 3: Refactor Engine Inputs

Goal:

- deploy a resolved project spec instead of requiring repository-local
  `deployer.yml`.

Work:

- define internal `ProjectSpec`;
- support compose overlay mode;
- generate override for multiple endpoints/components;
- keep source compose files read-only;
- preserve BuildKit support;
- store checkout ref/commit before runtime start.

Acceptance:

- project can be deployed without `deployer.yml` using `deployer deploy <environment> <project>`;
- existing compose repositories use compose overlay mode from deployer-managed endpoint/component settings;
- Dockerfile/image-only projects can use generated service definitions with `--no-compose-file`;
- one project can expose frontend and backend endpoints;
- generated files remain under deployer-managed runtime directory.

### Phase 4: UI Rebuild Around Environments

Goal:

- make the web UI match the real operating model.

Work:

- environments list/page as the primary screen;
- project list inside each environment;
- project page with source, policy, components, endpoints, dependencies, env, jobs;
- no global service page;
- no cross-product of services and environments;
- status, health, current ref/commit, and failed jobs visible in context.

Acceptance:

- operator adds a project directly to an environment;
- operator never attaches an existing global service to an environment;
- all deploy actions are scoped to the page being viewed.

### Phase 5: GitHub Webhooks

Goal:

- implement automatic deploy for an environment project without special-casing `dev`.

Work:

- add GitHub webhook endpoint;
- validate HMAC signature;
- store webhook event audit log;
- resolve affected environment projects by repository URL;
- match project deploy policy against branch/tag event;
- for `webhook_auto`, schedule deploy;
- for `webhook_gated`, store candidate.

Acceptance:

- push to configured branch deploys the configured environment project;
- tag policies use the same matching path;
- webhook events are auditable.

### Phase 6: Dependency Bindings

Goal:

- make shared resources safe across environments.

Work:

- define PostgreSQL binding model first;
- generate `DATABASE_URL` from binding;
- support one shared PostgreSQL instance with separate databases/users per project;
- add validation so a non-prod project cannot silently point to prod DB names.

Acceptance:

- `dev/tasktrack` and `prod/tasktrack` can share PostgreSQL server but use different
  databases and users;
- dependency env vars are generated by deployer, not manually guessed.

## Recommended Immediate Sequence

1. Update docs and tasks to the environment-first model.
2. Replace state schema without migrations.
3. Refactor backend catalog to environment projects.
4. Refactor CLI/API to environment project addressing.
5. Refactor engine to deploy internal project specs.
6. Rebuild UI primary flow around environment pages.
7. Add webhook auto deploy for one configured environment project.
8. Add dependency/resource bindings.

## Non-Goals For This Refactor

- Kubernetes.
- Multi-server scheduling.
- Full secret management before the state shape is stable.
- Automatic discovery that guesses all project components perfectly.
- Preserving old development database contents.

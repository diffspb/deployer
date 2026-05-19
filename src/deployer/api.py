from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import re
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from deployer import __version__
from deployer.catalog import CatalogError, ServiceCatalog, render_env
from deployer.config import DeployerConfig, load_config
from deployer.engine import DeploymentEngine
from deployer.errors import DeployerError
from deployer.manifest import Manifest, load_manifest
from deployer.override import render_override, route_host
from deployer.project_spec import project_route_host, render_project_override
from deployer.state import (
    DeploymentRecord,
    EnvironmentProfileRecord,
    EnvironmentProjectRecord,
    EnvironmentRecord,
    JobRecord,
    ProjectComponentRecord,
    ProjectDependencyRecord,
    ProjectEndpointRecord,
    RuntimeStatusRecord,
    ServiceRecord,
    StateStore,
)


class AddServiceRequest(BaseModel):
    name: str
    source_type: str = Field(pattern="^(git|local)$")
    git_url: str | None = None
    path: str | None = None
    default_branch: str | None = None


class DeployRequest(BaseModel):
    environment: str = "prod"
    ref: str | None = None
    version: str | None = None
    dry_run: bool = False


class RuntimeRequest(BaseModel):
    environment: str = "prod"
    dry_run: bool = False


class RuntimeTargetRequest(BaseModel):
    name: str


class EnvironmentProfileRequest(BaseModel):
    name: str
    url_prefix: str | None = None
    deploy_mode: str = "manual"
    deploy_source: str | None = None
    deploy_pattern: str | None = None
    deploy_pattern_type: str | None = None


class EnvironmentProfileUpdateRequest(BaseModel):
    url_prefix: str | None = None
    deploy_mode: str | None = None
    deploy_source: str | None = None
    deploy_pattern: str | None = None
    deploy_pattern_type: str | None = None


class EnvSetRequest(BaseModel):
    key: str
    value: str


class AddProjectRequest(BaseModel):
    name: str
    source_type: str = Field(pattern="^(git|local)$")
    git_url: str | None = None
    path: str | None = None
    default_ref: str | None = None
    compose_files: list[str] | None = None
    deploy_mode: str = "manual"
    deploy_source: str | None = None
    deploy_pattern: str | None = None
    deploy_pattern_type: str | None = None


class AddComponentRequest(BaseModel):
    name: str
    mode: str = Field(default="compose", pattern="^(compose|build|image)$")
    compose_service: str | None = None
    build_context: str | None = None
    dockerfile: str | None = None
    image: str | None = None
    command: str | None = None
    port: int | None = None
    env: dict[str, str] = Field(default_factory=dict)


class AddEndpointRequest(BaseModel):
    name: str
    component: str
    port: int
    host: str | None = None
    subdomain: str | None = None
    path_prefix: str | None = None
    auth: str = Field(default="none", pattern="^(none|sso)$")
    middlewares: list[str] = Field(default_factory=list)
    healthcheck_path: str | None = None


class AddDependencyRequest(BaseModel):
    name: str
    type: str
    target: str
    outputs: dict[str, str] = Field(default_factory=dict)


def create_app(config: DeployerConfig | None = None) -> FastAPI:
    app = FastAPI(title="Home PaaS Deployer API")
    app.state.config = config
    ui_dir = Path(__file__).parent / "ui"
    app.mount("/ui", StaticFiles(directory=ui_dir), name="ui")
    frontend_version = _frontend_version(ui_dir)

    @app.exception_handler(CatalogError)
    async def catalog_error_handler(request: Request, exc: CatalogError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(DeployerError)
    async def deployer_error_handler(request: Request, exc: DeployerError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def root() -> HTMLResponse:
        html = (ui_dir / "index.html").read_text()
        html = html.replace("/ui/styles.css", f"/ui/styles.css?v={frontend_version}")
        html = html.replace("/ui/app.js", f"/ui/app.js?v={frontend_version}")
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @app.get("/api/version")
    def version() -> dict[str, str]:
        build_info = _build_info()
        return {
            "backend_version": __version__,
            "frontend_version": frontend_version,
            "build_commit": build_info.get("commit", "unknown"),
            "build_date": build_info.get("date", "unknown"),
        }

    @app.get("/api/services")
    def list_services(catalog: CatalogDep) -> list[dict]:
        return [_service_payload(service) for service in catalog.list_services()]

    @app.post("/api/services", status_code=201)
    def add_service(payload: AddServiceRequest, catalog: CatalogDep) -> dict:
        if payload.source_type == "git":
            if not payload.git_url:
                raise HTTPException(status_code=422, detail="git_url is required for git services")
            service = catalog.add_git(payload.name, payload.git_url, default_branch=payload.default_branch)
        elif payload.source_type == "local":
            if not payload.path:
                raise HTTPException(status_code=422, detail="path is required for local services")
            service = catalog.add_local(payload.name, Path(payload.path))
        else:
            raise HTTPException(status_code=422, detail="source_type must be git or local")
        return _service_detail(catalog, service.name)

    @app.get("/api/services/{name}")
    def get_service(name: str, catalog: CatalogDep) -> dict:
        return _service_detail(catalog, name)

    @app.delete("/api/services/{name}")
    def remove_service(name: str, catalog: CatalogDep, delete_files: bool = False) -> dict:
        removed = catalog.remove_service(name, delete_files=delete_files)
        if not removed:
            raise HTTPException(status_code=404, detail=f"Unknown service: {name}")
        return {"removed": True, "service": name}

    @app.get("/api/environments")
    def list_environment_profiles(catalog: CatalogDep) -> dict:
        return {
            "environments": [
                _environment_profile_payload(profile, services=_services_for_environment(catalog, profile.name))
                for profile in catalog.list_environment_profiles()
            ]
        }

    @app.post("/api/environments", status_code=201)
    def add_environment_profile(payload: EnvironmentProfileRequest, catalog: CatalogDep) -> dict:
        profile = catalog.add_environment_profile(
            payload.name,
            url_prefix=payload.url_prefix,
            deploy_mode=payload.deploy_mode,
            deploy_source=payload.deploy_source,
            deploy_pattern=payload.deploy_pattern,
            deploy_pattern_type=payload.deploy_pattern_type,
        )
        return {"environment": _environment_profile_payload(profile, services=[])}

    @app.get("/api/environments/{environment}/services")
    def list_environment_services(environment: str, catalog: CatalogDep) -> dict:
        profile = catalog.get_environment_profile(environment)
        return {
            "environment": _environment_profile_payload(
                profile,
                services=_services_for_environment(catalog, environment),
            )
        }

    @app.patch("/api/environments/{environment}")
    def update_environment_profile(
        environment: str,
        payload: EnvironmentProfileUpdateRequest,
        catalog: CatalogDep,
    ) -> dict:
        profile = catalog.update_environment_profile(
            environment,
            url_prefix=payload.url_prefix,
            deploy_mode=payload.deploy_mode,
            deploy_source=payload.deploy_source,
            deploy_pattern=payload.deploy_pattern,
            deploy_pattern_type=payload.deploy_pattern_type,
        )
        return {
            "environment": _environment_profile_payload(
                profile,
                services=_services_for_environment(catalog, environment),
            )
        }

    @app.delete("/api/environments/{environment}")
    def delete_environment_profile(environment: str, catalog: CatalogDep) -> dict:
        removed = catalog.remove_environment_profile(environment)
        if not removed:
            raise HTTPException(status_code=404, detail=f"Unknown environment profile: {environment}")
        return {"removed": True, "environment": environment}

    @app.get("/api/environments/{environment}/projects")
    def list_environment_projects(environment: str, catalog: CatalogDep) -> dict:
        profile = catalog.get_environment_profile(environment)
        return {
            "environment": _environment_profile_payload(profile),
            "projects": [_project_payload(catalog, project) for project in catalog.list_projects(environment)],
        }

    @app.post("/api/environments/{environment}/projects", status_code=201)
    def add_environment_project(environment: str, payload: AddProjectRequest, catalog: CatalogDep) -> dict:
        compose_files = tuple(payload.compose_files or ("docker-compose.yml",))
        if payload.source_type == "git":
            if not payload.git_url:
                raise HTTPException(status_code=422, detail="git_url is required for git projects")
            project = catalog.add_project_git(
                environment,
                payload.name,
                payload.git_url,
                default_ref=payload.default_ref,
                compose_files=compose_files,
                deploy_mode=payload.deploy_mode,
                deploy_source=payload.deploy_source,
                deploy_pattern=payload.deploy_pattern,
                deploy_pattern_type=payload.deploy_pattern_type,
            )
        elif payload.source_type == "local":
            if not payload.path:
                raise HTTPException(status_code=422, detail="path is required for local projects")
            project = catalog.add_project_local(
                environment,
                payload.name,
                Path(payload.path),
                default_ref=payload.default_ref,
                compose_files=compose_files,
                deploy_mode=payload.deploy_mode,
                deploy_source=payload.deploy_source,
                deploy_pattern=payload.deploy_pattern,
                deploy_pattern_type=payload.deploy_pattern_type,
            )
        else:
            raise HTTPException(status_code=422, detail="source_type must be git or local")
        return _project_detail_payload(catalog, environment, project.name)

    @app.get("/api/environments/{environment}/projects/{project}")
    def get_environment_project(environment: str, project: str, catalog: CatalogDep) -> dict:
        return _project_detail_payload(catalog, environment, project)

    @app.delete("/api/environments/{environment}/projects/{project}")
    def delete_environment_project(
        environment: str,
        project: str,
        catalog: CatalogDep,
        delete_files: bool = False,
    ) -> dict:
        removed = catalog.remove_project(environment, project, delete_files=delete_files)
        if not removed:
            raise HTTPException(status_code=404, detail=f"Unknown project: {environment}/{project}")
        return {"removed": True, "environment": environment, "project": project}

    @app.get("/api/environments/{environment}/projects/{project}/env")
    def get_project_env(environment: str, project: str, catalog: CatalogDep) -> dict:
        record = catalog.get_project(environment, project)
        return {"environment": environment, "project": project, "env": record.env_vars}

    @app.post("/api/environments/{environment}/projects/{project}/env")
    def set_project_env(environment: str, project: str, payload: EnvSetRequest, catalog: CatalogDep) -> dict:
        record = catalog.set_project_env(environment, project, payload.key, payload.value)
        return {"environment": environment, "project": project, "env": record.env_vars}

    @app.delete("/api/environments/{environment}/projects/{project}/env/{key}")
    def unset_project_env(environment: str, project: str, key: str, catalog: CatalogDep) -> dict:
        record = catalog.unset_project_env(environment, project, key)
        return {"environment": environment, "project": project, "env": record.env_vars}

    @app.post("/api/environments/{environment}/projects/{project}/components", status_code=201)
    def add_project_component(
        environment: str,
        project: str,
        payload: AddComponentRequest,
        catalog: CatalogDep,
    ) -> dict:
        component = catalog.add_component(
            environment,
            project,
            payload.name,
            mode=payload.mode,
            compose_service=payload.compose_service,
            build_context=payload.build_context,
            dockerfile=payload.dockerfile,
            image=payload.image,
            command=payload.command,
            port=payload.port,
            env_vars=payload.env,
        )
        return {"component": _component_payload(component)}

    @app.patch("/api/environments/{environment}/projects/{project}/components/{component_name}")
    def update_project_component(
        environment: str,
        project: str,
        component_name: str,
        payload: AddComponentRequest,
        catalog: CatalogDep,
    ) -> dict:
        component = catalog.update_component(
            environment,
            project,
            component_name,
            mode=payload.mode,
            compose_service=payload.compose_service,
            build_context=payload.build_context,
            dockerfile=payload.dockerfile,
            image=payload.image,
            command=payload.command,
            port=payload.port,
            env_vars=payload.env,
        )
        return {"component": _component_payload(component)}

    @app.delete("/api/environments/{environment}/projects/{project}/components/{component_name}")
    def delete_project_component(
        environment: str,
        project: str,
        component_name: str,
        catalog: CatalogDep,
    ) -> dict:
        removed = catalog.delete_component(environment, project, component_name)
        if not removed:
            raise HTTPException(status_code=404, detail=f"Unknown component: {component_name}")
        return {"removed": True, "component": component_name}

    @app.post("/api/environments/{environment}/projects/{project}/endpoints", status_code=201)
    def add_project_endpoint(
        environment: str,
        project: str,
        payload: AddEndpointRequest,
        catalog: CatalogDep,
    ) -> dict:
        endpoint = catalog.add_endpoint(
            environment,
            project,
            payload.name,
            payload.component,
            payload.port,
            host=payload.host,
            subdomain=payload.subdomain,
            path_prefix=payload.path_prefix,
            auth=payload.auth,
            middlewares=tuple(payload.middlewares),
            healthcheck_path=payload.healthcheck_path,
        )
        return {"endpoint": _endpoint_payload(catalog, environment, project, endpoint)}

    @app.patch("/api/environments/{environment}/projects/{project}/endpoints/{endpoint_name}")
    def update_project_endpoint(
        environment: str,
        project: str,
        endpoint_name: str,
        payload: AddEndpointRequest,
        catalog: CatalogDep,
    ) -> dict:
        endpoint = catalog.update_endpoint(
            environment,
            project,
            endpoint_name,
            payload.component,
            payload.port,
            host=payload.host,
            subdomain=payload.subdomain,
            path_prefix=payload.path_prefix,
            auth=payload.auth,
            middlewares=tuple(payload.middlewares),
            healthcheck_path=payload.healthcheck_path,
        )
        return {"endpoint": _endpoint_payload(catalog, environment, project, endpoint)}

    @app.delete("/api/environments/{environment}/projects/{project}/endpoints/{endpoint_name}")
    def delete_project_endpoint(
        environment: str,
        project: str,
        endpoint_name: str,
        catalog: CatalogDep,
    ) -> dict:
        removed = catalog.delete_endpoint(environment, project, endpoint_name)
        if not removed:
            raise HTTPException(status_code=404, detail=f"Unknown endpoint: {endpoint_name}")
        return {"removed": True, "endpoint": endpoint_name}

    @app.post("/api/environments/{environment}/projects/{project}/dependencies", status_code=201)
    def add_project_dependency(
        environment: str,
        project: str,
        payload: AddDependencyRequest,
        catalog: CatalogDep,
    ) -> dict:
        dependency = catalog.add_dependency(
            environment,
            project,
            payload.name,
            payload.type,
            payload.target,
            outputs=payload.outputs,
        )
        return {"dependency": _dependency_payload(dependency)}

    @app.patch("/api/environments/{environment}/projects/{project}/dependencies/{dependency_name}")
    def update_project_dependency(
        environment: str,
        project: str,
        dependency_name: str,
        payload: AddDependencyRequest,
        catalog: CatalogDep,
    ) -> dict:
        dependency = catalog.update_dependency(
            environment,
            project,
            dependency_name,
            payload.type,
            payload.target,
            outputs=payload.outputs,
        )
        return {"dependency": _dependency_payload(dependency)}

    @app.delete("/api/environments/{environment}/projects/{project}/dependencies/{dependency_name}")
    def delete_project_dependency(
        environment: str,
        project: str,
        dependency_name: str,
        catalog: CatalogDep,
    ) -> dict:
        removed = catalog.delete_dependency(environment, project, dependency_name)
        if not removed:
            raise HTTPException(status_code=404, detail=f"Unknown dependency: {dependency_name}")
        return {"removed": True, "dependency": dependency_name}

    @app.get("/api/environments/{environment}/projects/{project}/preview")
    def project_preview(environment: str, project: str, catalog: CatalogDep) -> dict:
        return _project_preview_payload(catalog, environment, project)

    @app.post("/api/environments/{environment}/projects/{project}/deploy", status_code=202)
    def deploy_environment_project(
        environment: str,
        project: str,
        payload: DeployRequest,
        background_tasks: BackgroundTasks,
        context: ContextDep,
    ) -> dict:
        return _schedule_project_runtime_job(
            context,
            background_tasks,
            environment,
            project,
            "deploy",
            dry_run=payload.dry_run,
            ref=payload.ref,
            version=payload.version,
        )

    @app.post("/api/environments/{environment}/projects/{project}/deploy-candidate", status_code=202)
    def deploy_project_candidate(
        environment: str,
        project: str,
        payload: RuntimeRequest,
        background_tasks: BackgroundTasks,
        context: ContextDep,
    ) -> dict:
        record = context.catalog.get_project(environment, project)
        if not record.candidate_ref:
            raise HTTPException(status_code=409, detail=f"No candidate for project: {environment}/{project}")
        return _schedule_project_runtime_job(
            context,
            background_tasks,
            environment,
            project,
            "deploy",
            dry_run=payload.dry_run,
            ref=record.candidate_ref,
            version=record.candidate_ref,
        )

    @app.post("/api/environments/{environment}/projects/{project}/stop", status_code=202)
    def stop_environment_project(
        environment: str,
        project: str,
        payload: RuntimeRequest,
        background_tasks: BackgroundTasks,
        context: ContextDep,
    ) -> dict:
        return _schedule_project_runtime_job(context, background_tasks, environment, project, "stop", payload.dry_run)

    @app.post("/api/environments/{environment}/projects/{project}/down", status_code=202)
    def down_environment_project(
        environment: str,
        project: str,
        payload: RuntimeRequest,
        background_tasks: BackgroundTasks,
        context: ContextDep,
    ) -> dict:
        return _schedule_project_runtime_job(context, background_tasks, environment, project, "down", payload.dry_run)

    @app.post("/api/environments/{environment}/projects/{project}/restart", status_code=202)
    def restart_environment_project(
        environment: str,
        project: str,
        payload: RuntimeRequest,
        background_tasks: BackgroundTasks,
        context: ContextDep,
    ) -> dict:
        return _schedule_project_runtime_job(context, background_tasks, environment, project, "restart", payload.dry_run)

    @app.get("/api/environments/{environment}/projects/{project}/status")
    def status_environment_project(environment: str, project: str, context: ContextDep) -> dict:
        result = context.catalog.status_project(environment, project, context.engine)
        runtime_status = _record_runtime_status_from_command(context.state, result)
        return {
            **_command_result_payload(result),
            "runtime_status": _runtime_status_payload(runtime_status),
        }

    @app.get("/api/environments/{environment}/projects/{project}/logs")
    def logs_environment_project(
        environment: str,
        project: str,
        context: ContextDep,
        tail: int = Query(default=200, ge=1, le=5000),
    ) -> dict:
        result = context.catalog.logs_project(environment, project, context.engine, tail=tail)
        return _command_result_payload(result)

    @app.get("/api/services/{name}/refs")
    def refs(name: str, catalog: CatalogDep) -> dict:
        raw = catalog.refs(name)
        return {"service": name, "refs": _refs_payload(raw), "raw_refs": raw}

    @app.get("/api/services/{name}/runtime-targets")
    def list_runtime_targets(name: str, catalog: CatalogDep) -> dict:
        return {"service": name, "runtime_targets": [_environment_payload(env) for env in catalog.list_environments(name)]}

    @app.post("/api/services/{name}/runtime-targets", status_code=201)
    def add_runtime_target(name: str, payload: RuntimeTargetRequest, catalog: CatalogDep) -> dict:
        env = catalog.add_environment(name, payload.name)
        return {"service": name, "runtime_target": _environment_payload(env)}

    @app.delete("/api/services/{name}/runtime-targets/{environment}")
    def delete_runtime_target(name: str, environment: str, catalog: CatalogDep) -> dict:
        removed = catalog.remove_environment(name, environment)
        if not removed:
            raise HTTPException(status_code=404, detail=f"Unknown runtime target: {name}/{environment}")
        return {"removed": True, "service": name, "environment": environment}

    @app.get("/api/services/{name}/env/{environment}")
    def get_env(name: str, environment: str, catalog: CatalogDep) -> dict:
        env = catalog.get_environment(name, environment)
        return {"service": name, "environment": env.name, "env": env.env_vars}

    @app.post("/api/services/{name}/env/{environment}")
    def set_env(name: str, environment: str, payload: EnvSetRequest, catalog: CatalogDep) -> dict:
        env = catalog.set_env(name, environment, payload.key, payload.value)
        return {"service": name, "environment": env.name, "env": env.env_vars}

    @app.delete("/api/services/{name}/env/{environment}/{key}")
    def unset_env(name: str, environment: str, key: str, catalog: CatalogDep) -> dict:
        env = catalog.unset_env(name, environment, key)
        return {"service": name, "environment": env.name, "env": env.env_vars}

    @app.get("/api/services/{name}/history")
    def history(
        name: str,
        catalog: CatalogDep,
        environment: str | None = None,
        limit: int = Query(default=20, ge=1, le=200),
    ) -> dict:
        return _history_payload(catalog.history(name, environment=environment, limit=limit))

    @app.get("/api/services/{name}/preview")
    def preview(name: str, catalog: CatalogDep, environment: str = "prod") -> dict:
        return _preview_payload(catalog, name, environment)

    @app.get("/api/jobs")
    def list_jobs(
        context: ContextDep,
        service: str | None = None,
        environment: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict:
        return {"jobs": [_job_payload(job, log_limit=0) for job in context.state.list_jobs(service, environment, limit)]}

    @app.get("/api/jobs/{job_id}")
    def get_job(
        job_id: int,
        context: ContextDep,
        log_limit: int = Query(default=200_000, ge=0, le=1_000_000),
    ) -> dict:
        job = context.state.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Unknown job: {job_id}")
        return _job_payload(job, log_limit=log_limit)

    @app.get("/api/webhook-events")
    def list_webhook_events(
        context: ContextDep,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict:
        return {"events": [_webhook_event_payload(event) for event in context.state.list_webhook_events(limit)]}

    @app.post("/api/webhooks/github", status_code=202)
    async def github_webhook(request: Request, background_tasks: BackgroundTasks, context: ContextDep) -> dict:
        body = await request.body()
        _verify_github_signature(context.config.webhook_secret, body, request.headers.get("X-Hub-Signature-256"))
        try:
            payload = json.loads(body.decode() or "{}")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc}") from exc
        return _handle_github_webhook(
            context,
            background_tasks,
            request.headers.get("X-GitHub-Event", "unknown"),
            request.headers.get("X-GitHub-Delivery"),
            payload,
        )

    @app.post("/api/services/{name}/deploy", status_code=202)
    def deploy(name: str, payload: DeployRequest, background_tasks: BackgroundTasks, context: ContextDep) -> dict:
        return _schedule_runtime_job(
            context,
            background_tasks,
            name,
            "deploy",
            payload.environment,
            dry_run=payload.dry_run,
            ref=payload.ref,
            version=payload.version,
        )

    @app.post("/api/services/{name}/stop", status_code=202)
    def stop(name: str, payload: RuntimeRequest, background_tasks: BackgroundTasks, context: ContextDep) -> dict:
        return _schedule_runtime_job(context, background_tasks, name, "stop", payload.environment, payload.dry_run)

    @app.post("/api/services/{name}/down", status_code=202)
    def down(name: str, payload: RuntimeRequest, background_tasks: BackgroundTasks, context: ContextDep) -> dict:
        return _schedule_runtime_job(context, background_tasks, name, "down", payload.environment, payload.dry_run)

    @app.post("/api/services/{name}/restart", status_code=202)
    def restart(name: str, payload: RuntimeRequest, background_tasks: BackgroundTasks, context: ContextDep) -> dict:
        return _schedule_runtime_job(context, background_tasks, name, "restart", payload.environment, payload.dry_run)

    @app.get("/api/services/{name}/status")
    def status(name: str, context: ContextDep, environment: str = "prod") -> dict:
        result = context.catalog.status(name, context.engine, environment=environment)
        return _command_result_payload(result)

    @app.get("/api/services/{name}/logs")
    def logs(
        name: str,
        context: ContextDep,
        environment: str = "prod",
        tail: int = Query(default=200, ge=1, le=5000),
    ) -> dict:
        result = context.catalog.logs(name, context.engine, environment=environment, tail=tail)
        return _command_result_payload(result)

    return app


class ApiContext:
    def __init__(self, config: DeployerConfig):
        self.config = config
        self.state = StateStore(config.state_db)
        self.catalog = ServiceCatalog(self.state, runtime_dir=config.runtime_dir)
        self.engine = DeploymentEngine(self.state)


def get_config(request: Request) -> DeployerConfig:
    return request.app.state.config or load_config()


def get_context(config: Annotated[DeployerConfig, Depends(get_config)]) -> ApiContext:
    return ApiContext(config)


def get_catalog(context: Annotated[ApiContext, Depends(get_context)]) -> ServiceCatalog:
    return context.catalog


ContextDep = Annotated[ApiContext, Depends(get_context)]
CatalogDep = Annotated[ServiceCatalog, Depends(get_catalog)]


def _service_payload(service: ServiceRecord) -> dict:
    return {
        "id": service.id,
        "name": service.name,
        "source_type": service.source_type,
        "source_url": service.source_url,
        "source_path": service.source_path,
        "default_branch": service.default_branch,
        "created_at": service.created_at,
        "updated_at": service.updated_at,
    }


def _environment_payload(env: EnvironmentRecord, public_url: str | None = None) -> dict:
    return {
        "name": env.name,
        "subdomain": env.subdomain,
        "url_prefix": env.url_prefix,
        "deploy_mode": env.deploy_mode,
        "deploy_source": env.deploy_source,
        "deploy_pattern": env.deploy_pattern,
        "deploy_pattern_type": env.deploy_pattern_type,
        "public_url": public_url,
        "env": env.env_vars,
        "current_version": env.current_version,
        "current_ref": env.current_ref,
        "current_commit": env.current_commit,
        "last_deployment_id": env.last_deployment_id,
    }


def _environment_profile_payload(profile: EnvironmentProfileRecord, services: list[dict] | None = None) -> dict:
    payload = {
        "name": profile.name,
        "url_prefix": profile.url_prefix,
        "deploy_mode": profile.deploy_mode,
        "deploy_source": profile.deploy_source,
        "deploy_pattern": profile.deploy_pattern,
        "deploy_pattern_type": profile.deploy_pattern_type,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }
    if services is not None:
        payload["services"] = services
    return payload


def _project_payload(catalog: ServiceCatalog, project: EnvironmentProjectRecord) -> dict:
    config = catalog.project_config(project.environment, project.name)
    endpoints = [_endpoint_payload(catalog, project.environment, project.name, endpoint) for endpoint in config.endpoints]
    runtime_status = catalog.state.get_runtime_status(project.environment, project.name)
    latest_jobs = catalog.state.list_jobs(project.name, project.environment, limit=1)
    return {
        "id": project.id,
        "environment": project.environment,
        "name": project.name,
        "source_type": project.source_type,
        "source_url": project.source_url,
        "source_path": project.source_path,
        "default_ref": project.default_ref,
        "compose_files": list(project.compose_files),
        "deploy_mode": project.deploy_mode,
        "deploy_source": project.deploy_source,
        "deploy_pattern": project.deploy_pattern,
        "deploy_pattern_type": project.deploy_pattern_type,
        "env": project.env_vars,
        "current_version": project.current_version,
        "current_ref": project.current_ref,
        "current_commit": project.current_commit,
        "last_deployment_id": project.last_deployment_id,
        "candidate_ref": project.candidate_ref,
        "candidate_commit": project.candidate_commit,
        "candidate_event_id": project.candidate_event_id,
        "runtime_status": _runtime_status_payload(runtime_status),
        "last_job": _job_payload(latest_jobs[0], log_limit=0) if latest_jobs else None,
        "public_urls": [endpoint["public_url"] for endpoint in endpoints if endpoint["public_url"]],
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def _project_detail_payload(catalog: ServiceCatalog, environment: str, project: str) -> dict:
    config = catalog.project_config(environment, project)
    return {
        **_project_payload(catalog, config.project),
        "components": [_component_payload(component) for component in config.components],
        "endpoints": [
            _endpoint_payload(catalog, environment, project, endpoint)
            for endpoint in config.endpoints
        ],
        "dependencies": [_dependency_payload(dependency) for dependency in config.dependencies],
    }


def _component_payload(component: ProjectComponentRecord) -> dict:
    return {
        "id": component.id,
        "name": component.name,
        "mode": component.mode,
        "compose_service": component.compose_service,
        "build_context": component.build_context,
        "dockerfile": component.dockerfile,
        "image": component.image,
        "command": component.command,
        "port": component.port,
        "env": component.env_vars,
        "created_at": component.created_at,
        "updated_at": component.updated_at,
    }


def _endpoint_payload(
    catalog: ServiceCatalog,
    environment: str,
    project: str,
    endpoint: ProjectEndpointRecord,
) -> dict:
    public_url = None
    try:
        spec = catalog.project_spec(environment, project)
        spec_endpoint = next(item for item in spec.endpoints if item.name == endpoint.name)
        public_url = f"https://{project_route_host(spec, spec_endpoint)}/"
    except (DeployerError, StopIteration, ValueError):
        public_url = None
    return {
        "id": endpoint.id,
        "name": endpoint.name,
        "component": endpoint.component,
        "port": endpoint.port,
        "host": endpoint.host,
        "subdomain": endpoint.subdomain,
        "path_prefix": endpoint.path_prefix,
        "auth": endpoint.auth,
        "middlewares": list(endpoint.middlewares),
        "healthcheck_path": endpoint.healthcheck_path,
        "public_url": public_url,
        "created_at": endpoint.created_at,
        "updated_at": endpoint.updated_at,
    }


def _dependency_payload(dependency: ProjectDependencyRecord) -> dict:
    return {
        "id": dependency.id,
        "name": dependency.name,
        "type": dependency.type,
        "target": dependency.target,
        "outputs": dependency.outputs,
        "created_at": dependency.created_at,
        "updated_at": dependency.updated_at,
    }


def _webhook_event_payload(event) -> dict:
    return {
        "id": event.id,
        "provider": event.provider,
        "event_type": event.event_type,
        "delivery_id": event.delivery_id,
        "repository": event.repository,
        "ref": event.ref,
        "ref_type": event.ref_type,
        "ref_name": event.ref_name,
        "commit_hash": event.commit_hash,
        "matched_projects": list(event.matched_projects),
        "action": event.action,
        "status": event.status,
        "payload": event.payload,
        "created_at": event.created_at,
    }


def _services_for_environment(catalog: ServiceCatalog, environment: str) -> list[dict]:
    services = []
    for service in catalog.list_services():
        env = catalog.state.get_environment(service.name, environment)
        if env is None:
            continue
        manifest = _load_service_manifest(service)
        services.append(
            {
                **_service_payload(service),
                "runtime": _environment_payload(env, public_url=_public_url_for(manifest, env)),
            }
        )
    return services


def _service_detail(catalog: ServiceCatalog, name: str) -> dict:
    service = catalog.get_service(name)
    manifest = _load_service_manifest(service)
    environments = catalog.list_environments(service.name)
    return {
        **_service_payload(service),
        "source_status": _source_status_payload(catalog.source_status(service.name)),
        "environments": [
            _environment_payload(env, public_url=_public_url_for(manifest, env)) for env in environments
        ],
    }


def _source_status_payload(status) -> dict:
    return {
        "available": status.available,
        "path_exists": status.path_exists,
        "is_git_repo": status.is_git_repo,
        "current_ref": status.current_ref,
        "current_commit": status.current_commit,
        "error": status.error,
    }


def _deployment_payload(record: DeploymentRecord) -> dict:
    return {
        "id": record.id,
        "project": record.project,
        "environment": record.environment,
        "action": record.action,
        "version": record.version,
        "status": record.status,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "log": record.log,
    }


def _history_payload(history) -> dict:
    return {
        "service": _service_payload(history.service),
        "environments": [_environment_payload(env) for env in history.environments],
        "deployments": [_deployment_payload(record) for record in history.records],
    }


def _command_result_payload(result) -> dict:
    summary = _status_summary_payload(result.log) if result.status == "success" else None
    return {
        "project": result.project,
        "environment": result.environment,
        "status": result.status,
        "log": result.log,
        "override_path": str(result.override_path),
        "summary": summary,
    }


def _runtime_status_payload(status: RuntimeStatusRecord | None) -> dict:
    if status is None:
        return {
            "state": "unknown",
            "health": "unknown",
            "containers": [],
            "raw": "",
            "error": None,
            "checked_at": None,
        }
    return {
        "state": status.state,
        "health": status.health,
        "containers": list(status.containers),
        "raw": status.raw,
        "error": status.error,
        "checked_at": status.checked_at,
    }


def _record_runtime_status_from_command(state: StateStore, result) -> RuntimeStatusRecord:
    if result.status != "success":
        return state.upsert_runtime_status(
            result.environment,
            result.project,
            "unknown",
            "unknown",
            raw=result.log,
            error=result.log or "status command failed",
        )
    summary = _status_summary_payload(result.log)
    containers = tuple(summary.get("containers") or ())
    states = {str(item.get("state") or "unknown").lower() for item in containers}
    stopped_states = {"exited", "stopped", "dead", "created", "removing"}
    if summary.get("running"):
        runtime_state = "running"
    elif containers and states.intersection(stopped_states):
        runtime_state = "stopped"
    elif not containers:
        runtime_state = "stopped"
    else:
        runtime_state = "unknown"
    return state.upsert_runtime_status(
        result.environment,
        result.project,
        runtime_state,
        str(summary.get("health") or "unknown"),
        containers=containers,
        raw=result.log,
        error=None,
    )


def _record_runtime_status_from_action(state: StateStore, job: JobRecord, result) -> None:
    if job.dry_run or result.status != "success":
        return
    if job.action in {"deploy", "restart"}:
        state.upsert_runtime_status(job.environment, job.service, "running", "unknown", raw=result.log)
    elif job.action in {"stop", "down"}:
        state.upsert_runtime_status(job.environment, job.service, "stopped", "unknown", raw=result.log)


def _preview_payload(catalog: ServiceCatalog, name: str, environment: str) -> dict:
    service = catalog.get_service(name)
    runtime = catalog.resolve_runtime(name, environment)
    source_status = catalog.source_status(name)
    env_file_content = render_env(runtime.environment.env_vars)
    runtime.env_file.parent.mkdir(parents=True, exist_ok=True)
    runtime.env_file.write_text(env_file_content)

    errors: list[dict[str, str]] = []
    manifest = None
    override_content = None
    compose_files: list[str] = []

    if source_status.error:
        errors.append({"scope": "source", "message": source_status.error})

    if source_status.path_exists:
        try:
            manifest = load_manifest(runtime.project_dir)
            override_content = render_override(
                manifest,
                environment=environment,
                env_file=str(runtime.env_file),
                url_prefix=runtime.environment.url_prefix,
                env_vars=runtime.environment.env_vars,
            )
            compose_files = list(manifest.compose.files)
        except DeployerError as exc:
            errors.append({"scope": "manifest", "message": str(exc)})

    return {
        "service": service.name,
        "environment": environment,
        "valid": not errors,
        "errors": errors,
        "source_path": str(runtime.project_dir),
        "manifest_path": str(runtime.project_dir / "deployer.yml"),
        "compose_files": compose_files,
        "public_url": _public_url_for(manifest, runtime.environment),
        "env_file_path": str(runtime.env_file),
        "env_file_content": env_file_content,
        "override_path": str(runtime.override_dir / f"{environment}.override.yml"),
        "override_content": override_content,
    }


def _project_preview_payload(catalog: ServiceCatalog, environment: str, project: str) -> dict:
    config = catalog.project_config(environment, project)
    runtime = catalog.resolve_project_runtime(environment, project)
    env_file = catalog.render_project_env_file(environment, project)
    env_file_content = env_file.read_text()

    errors: list[dict[str, str]] = []
    override_content = None
    public_urls: list[str] = []
    source_path = Path(config.project.source_path)
    if not source_path.exists():
        errors.append({"scope": "source", "message": f"Source path is missing: {source_path}"})

    for compose_file in config.project.compose_files:
        if not (source_path / compose_file).exists():
            errors.append({"scope": "compose", "message": f"Missing compose file: {compose_file}"})

    try:
        spec = catalog.project_spec(environment, project)
        override_content = render_project_override(spec)
        public_urls = [
            f"https://{project_route_host(spec, endpoint)}/"
            for endpoint in spec.endpoints
        ]
    except (DeployerError, ValueError) as exc:
        errors.append({"scope": "project", "message": str(exc)})

    return {
        "environment": environment,
        "project": project,
        "valid": not errors,
        "errors": errors,
        "source_path": str(runtime.source_dir),
        "compose_files": list(config.project.compose_files),
        "public_urls": public_urls,
        "env_file_path": str(runtime.env_file),
        "env_file_content": env_file_content,
        "override_path": str(runtime.override_dir / f"{environment}.override.yml"),
        "override_content": override_content if not errors else None,
    }


def _refs_payload(raw: str) -> list[dict]:
    refs = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        commit_hash, name = parts[0], parts[-1]
        if name.startswith("refs/heads/"):
            ref_type = "branch"
            short_name = name.removeprefix("refs/heads/")
        elif name.startswith("refs/tags/"):
            ref_type = "tag"
            short_name = name.removeprefix("refs/tags/")
        else:
            ref_type = "ref"
            short_name = name
        refs.append({"name": short_name, "full_name": name, "type": ref_type, "commit": commit_hash})
    return refs


def _status_summary_payload(raw: str) -> dict:
    try:
        items = json.loads(raw or "[]")
    except json.JSONDecodeError:
        items = _parse_json_lines(raw)
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return _empty_status_summary()

    containers = []
    any_running = False
    health_states: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        state = str(item.get("State") or item.get("Status") or "unknown").lower()
        health = str(item.get("Health") or "unknown").lower()
        if state == "running":
            any_running = True
        if health and health != "unknown":
            health_states.append(health)
        containers.append(
            {
                "name": item.get("Name"),
                "service": item.get("Service"),
                "state": state,
                "health": health,
            }
        )

    overall_health = "unknown"
    if health_states:
        if any(value == "unhealthy" for value in health_states):
            overall_health = "unhealthy"
        elif any(value == "starting" for value in health_states):
            overall_health = "starting"
        elif all(value == "healthy" for value in health_states):
            overall_health = "healthy"

    return {
        "containers": containers,
        "running": any_running,
        "healthy": overall_health == "healthy",
        "health": overall_health,
    }


def _parse_json_lines(raw: str) -> list[dict]:
    items = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            items.append(value)
    return items


def _empty_status_summary() -> dict:
    return {
        "containers": [],
        "running": False,
        "healthy": False,
        "health": "unknown",
    }


def _limited_log(log: str, limit: int | None) -> tuple[str, bool]:
    if limit is None or len(log) <= limit:
        return log, False
    if limit <= 0:
        return "", bool(log)
    marker = f"[output truncated to last {limit} characters]\n"
    return marker + log[-limit:], True


def _load_service_manifest(service: ServiceRecord) -> Manifest | None:
    try:
        return load_manifest(Path(service.source_path))
    except DeployerError:
        return None


def _public_url_for(manifest: Manifest | None, environment: EnvironmentRecord) -> str | None:
    if manifest is None or not manifest.routes:
        return None
    route = manifest.routes[0]
    return f"https://{route_host(route, environment=environment.name, url_prefix=environment.url_prefix)}/"


def _schedule_runtime_job(
    context: ApiContext,
    background_tasks: BackgroundTasks,
    service: str,
    action: str,
    environment: str,
    dry_run: bool,
    ref: str | None = None,
    version: str | None = None,
) -> dict:
    context.catalog.get_service(service)
    context.catalog.get_environment(service, environment)
    job_id = context.state.create_job(
        service,
        environment,
        action,
        ref=ref,
        version=version,
        dry_run=dry_run,
    )
    background_tasks.add_task(_run_runtime_job, context.config, job_id)
    job = context.state.get_job(job_id)
    return _job_payload(job)


def _schedule_project_runtime_job(
    context: ApiContext,
    background_tasks: BackgroundTasks,
    environment: str,
    project: str,
    action: str,
    dry_run: bool,
    ref: str | None = None,
    version: str | None = None,
) -> dict:
    context.catalog.get_project(environment, project)
    job_id = context.state.create_job(
        project,
        environment,
        action,
        ref=ref,
        version=version,
        dry_run=dry_run,
    )
    background_tasks.add_task(_run_runtime_job, context.config, job_id)
    job = context.state.get_job(job_id)
    return _job_payload(job)


def _verify_github_signature(secret: str | None, body: bytes, signature: str | None) -> None:
    if not secret:
        return
    if not signature or not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing GitHub webhook signature")
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")


def _handle_github_webhook(
    context: ApiContext,
    background_tasks: BackgroundTasks,
    event_type: str,
    delivery_id: str | None,
    payload: dict,
) -> dict:
    ref = payload.get("ref")
    ref_type, ref_name = _github_ref_parts(ref)
    commit_hash = payload.get("after") or payload.get("head_commit", {}).get("id")
    repository = payload.get("repository", {}).get("full_name")

    if event_type != "push" or not ref_type or not ref_name:
        event_id = context.state.create_webhook_event(
            "github",
            event_type,
            delivery_id,
            repository,
            ref,
            ref_type,
            ref_name,
            commit_hash,
            (),
            "ignored",
            "ignored",
            payload,
        )
        return {"event": _webhook_event_payload(context.state.get_webhook_event(event_id)), "jobs": []}

    matches = [
        project for project in context.state.list_projects()
        if _project_matches_webhook(project, payload, ref_type, ref_name)
    ]
    matched_names = tuple(f"{project.environment}/{project.name}" for project in matches)
    auto_projects = [project for project in matches if project.deploy_mode == "webhook_auto"]
    gated_projects = [project for project in matches if project.deploy_mode == "webhook_gated"]
    action = _webhook_action(auto_projects, gated_projects)
    status = "accepted" if matches else "ignored"
    event_id = context.state.create_webhook_event(
        "github",
        event_type,
        delivery_id,
        repository,
        ref,
        ref_type,
        ref_name,
        commit_hash,
        matched_names,
        action,
        status,
        payload,
    )

    jobs = []
    for project in gated_projects:
        context.state.update_project_candidate(project.environment, project.name, ref_name, commit_hash, event_id)
    for project in auto_projects:
        job = _schedule_project_runtime_job(
            context,
            background_tasks,
            project.environment,
            project.name,
            "deploy",
            dry_run=False,
            ref=ref_name,
            version=ref_name,
        )
        jobs.append(job)
    return {"event": _webhook_event_payload(context.state.get_webhook_event(event_id)), "jobs": jobs}


def _github_ref_parts(ref: str | None) -> tuple[str | None, str | None]:
    if not ref:
        return None, None
    if ref.startswith("refs/heads/"):
        return "branch", ref.removeprefix("refs/heads/")
    if ref.startswith("refs/tags/"):
        return "tag", ref.removeprefix("refs/tags/")
    return None, None


def _project_matches_webhook(project, payload: dict, ref_type: str, ref_name: str) -> bool:
    if project.deploy_mode not in {"webhook_auto", "webhook_gated"}:
        return False
    if project.deploy_source != ref_type:
        return False
    if not _project_matches_repository(project, payload):
        return False
    pattern = project.deploy_pattern or ""
    if project.deploy_pattern_type == "exact":
        return ref_name == pattern
    if project.deploy_pattern_type == "regex":
        return re.fullmatch(pattern, ref_name) is not None
    return False


def _project_matches_repository(project, payload: dict) -> bool:
    if not project.source_url:
        return True
    repository = payload.get("repository") or {}
    candidates = {
        repository.get("clone_url"),
        repository.get("ssh_url"),
        repository.get("html_url"),
        repository.get("git_url"),
        repository.get("full_name"),
    }
    return project.source_url in candidates


def _webhook_action(auto_projects: list, gated_projects: list) -> str:
    actions = []
    if auto_projects:
        actions.append("scheduled")
    if gated_projects:
        actions.append("candidate")
    return "+".join(actions) if actions else "ignored"


def _run_runtime_job(config: DeployerConfig, job_id: int) -> None:
    context = ApiContext(config)
    job = context.state.get_job(job_id)
    if job is None:
        return

    context.state.start_job(job_id)
    try:
        if context.state.get_project(job.environment, job.service) is not None:
            result = _run_project_runtime_action(context, job)
        elif job.action == "deploy":
            result = context.catalog.deploy(
                job.service,
                context.engine,
                environment=job.environment,
                ref=job.ref,
                version=job.version,
                dry_run=job.dry_run,
            )
        elif job.action == "stop":
            result = context.catalog.stop(job.service, context.engine, environment=job.environment, dry_run=job.dry_run)
        elif job.action == "down":
            result = context.catalog.down(job.service, context.engine, environment=job.environment, dry_run=job.dry_run)
        elif job.action == "restart":
            result = context.catalog.restart(
                job.service,
                context.engine,
                environment=job.environment,
                dry_run=job.dry_run,
            )
        else:
            raise RuntimeError(f"Unknown runtime action: {job.action}")

        _record_runtime_status_from_action(context.state, job, result)
        context.state.finish_job(
            job_id,
            result.status,
            result.log,
            deployment_id=result.deployment_id,
            error=None if result.status == "success" else result.log,
        )
    except Exception as exc:
        context.state.finish_job(job_id, "failed", str(exc), error=str(exc))


def _run_project_runtime_action(context: ApiContext, job: JobRecord):
    if job.action == "deploy":
        result = context.catalog.deploy_project(
            job.environment,
            job.service,
            context.engine,
            ref=job.ref,
            version=job.version,
            dry_run=job.dry_run,
        )
        project = context.state.get_project(job.environment, job.service)
        if result.status == "success" and project and project.candidate_ref == job.ref:
            context.state.clear_project_candidate(job.environment, job.service)
        return result
    if job.action == "stop":
        return context.catalog.stop_project(job.environment, job.service, context.engine, dry_run=job.dry_run)
    if job.action == "down":
        return context.catalog.down_project(job.environment, job.service, context.engine, dry_run=job.dry_run)
    if job.action == "restart":
        return context.catalog.restart_project(job.environment, job.service, context.engine, dry_run=job.dry_run)
    raise RuntimeError(f"Unknown runtime action: {job.action}")


def _job_payload(job: JobRecord | None, log_limit: int | None = None) -> dict:
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    log, log_truncated = _limited_log(job.log, log_limit)
    return {
        "id": job.id,
        "service": job.service,
        "project": job.service,
        "environment": job.environment,
        "action": job.action,
        "status": job.status,
        "ref": job.ref,
        "version": job.version,
        "dry_run": job.dry_run,
        "deployment_id": job.deployment_id,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "log": log,
        "log_truncated": log_truncated,
        "error": job.error,
    }


def _frontend_version(ui_dir: Path) -> str:
    digest = hashlib.sha256()
    for name in ("index.html", "styles.css", "app.js"):
        path = ui_dir / name
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _build_info() -> dict[str, str]:
    path = Path("/app/build-info.json")
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(key): str(value) for key, value in data.items() if value is not None}


app = create_app()

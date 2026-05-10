from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from deployer.catalog import CatalogError, ServiceCatalog
from deployer.config import DeployerConfig, load_config
from deployer.engine import DeploymentEngine
from deployer.errors import DeployerError
from deployer.state import DeploymentRecord, EnvironmentRecord, JobRecord, ServiceRecord, StateStore


class AddServiceRequest(BaseModel):
    name: str
    source_type: str = Field(pattern="^(git|local)$")
    git_url: str | None = None
    path: str | None = None
    default_branch: str | None = None


class DeployRequest(BaseModel):
    environment: str = Field(default="prod", pattern="^(prod|dev)$")
    ref: str | None = None
    version: str | None = None
    dry_run: bool = False


class RuntimeRequest(BaseModel):
    environment: str = Field(default="prod", pattern="^(prod|dev)$")
    dry_run: bool = False


class EnvSetRequest(BaseModel):
    key: str
    value: str


def create_app(config: DeployerConfig | None = None) -> FastAPI:
    app = FastAPI(title="Home PaaS Deployer API")
    app.state.config = config

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
    def root() -> dict[str, str]:
        return {"service": "home-paas-deployer", "status": "running", "ui": "not implemented"}

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

    @app.get("/api/services/{name}/refs")
    def refs(name: str, catalog: CatalogDep) -> dict:
        return {"service": name, "refs": catalog.refs(name)}

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
        environment: str | None = Query(default=None, pattern="^(prod|dev)$"),
        limit: int = Query(default=20, ge=1, le=200),
    ) -> dict:
        return _history_payload(catalog.history(name, environment=environment, limit=limit))

    @app.get("/api/jobs")
    def list_jobs(
        context: ContextDep,
        service: str | None = None,
        environment: str | None = Query(default=None, pattern="^(prod|dev)$"),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict:
        return {"jobs": [_job_payload(job) for job in context.state.list_jobs(service, environment, limit)]}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: int, context: ContextDep) -> dict:
        job = context.state.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Unknown job: {job_id}")
        return _job_payload(job)

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
    def status(name: str, context: ContextDep, environment: str = Query(default="prod", pattern="^(prod|dev)$")) -> dict:
        result = context.catalog.status(name, context.engine, environment=environment)
        return _command_result_payload(result)

    @app.get("/api/services/{name}/logs")
    def logs(
        name: str,
        context: ContextDep,
        environment: str = Query(default="prod", pattern="^(prod|dev)$"),
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


def _environment_payload(env: EnvironmentRecord) -> dict:
    return {
        "name": env.name,
        "subdomain": env.subdomain,
        "env": env.env_vars,
        "current_version": env.current_version,
        "current_ref": env.current_ref,
        "current_commit": env.current_commit,
        "last_deployment_id": env.last_deployment_id,
    }


def _service_detail(catalog: ServiceCatalog, name: str) -> dict:
    service = catalog.get_service(name)
    return {
        **_service_payload(service),
        "environments": [
            _environment_payload(catalog.get_environment(service.name, "prod")),
            _environment_payload(catalog.get_environment(service.name, "dev")),
        ],
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
    return {
        "project": result.project,
        "environment": result.environment,
        "status": result.status,
        "log": result.log,
        "override_path": str(result.override_path),
    }


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


def _run_runtime_job(config: DeployerConfig, job_id: int) -> None:
    context = ApiContext(config)
    job = context.state.get_job(job_id)
    if job is None:
        return

    context.state.start_job(job_id)
    try:
        if job.action == "deploy":
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

        context.state.finish_job(
            job_id,
            result.status,
            result.log,
            deployment_id=result.deployment_id,
            error=None if result.status == "success" else result.log,
        )
    except Exception as exc:
        context.state.finish_job(job_id, "failed", str(exc), error=str(exc))


def _job_payload(job: JobRecord | None) -> dict:
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    return {
        "id": job.id,
        "service": job.service,
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
        "log": job.log,
        "error": job.error,
    }


app = create_app()

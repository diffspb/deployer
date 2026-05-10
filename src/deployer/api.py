from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from deployer.catalog import CatalogError, ServiceCatalog
from deployer.config import DeployerConfig, load_config
from deployer.engine import DeploymentEngine
from deployer.errors import DeployerError
from deployer.state import DeploymentRecord, EnvironmentRecord, ServiceRecord, StateStore


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

    @app.post("/api/services/{name}/deploy")
    def deploy(name: str, payload: DeployRequest, context: ContextDep) -> dict:
        result = context.catalog.deploy(
            name,
            context.engine,
            environment=payload.environment,
            ref=payload.ref,
            version=payload.version,
            dry_run=payload.dry_run,
        )
        return _deploy_result_payload(result)

    @app.post("/api/services/{name}/stop")
    def stop(name: str, payload: RuntimeRequest, context: ContextDep) -> dict:
        return _deploy_result_payload(
            context.catalog.stop(name, context.engine, environment=payload.environment, dry_run=payload.dry_run)
        )

    @app.post("/api/services/{name}/down")
    def down(name: str, payload: RuntimeRequest, context: ContextDep) -> dict:
        return _deploy_result_payload(
            context.catalog.down(name, context.engine, environment=payload.environment, dry_run=payload.dry_run)
        )

    @app.post("/api/services/{name}/restart")
    def restart(name: str, payload: RuntimeRequest, context: ContextDep) -> dict:
        return _deploy_result_payload(
            context.catalog.restart(name, context.engine, environment=payload.environment, dry_run=payload.dry_run)
        )

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


def _deploy_result_payload(result) -> dict:
    return {
        "deployment_id": result.deployment_id,
        "project": result.project,
        "environment": result.environment,
        "status": result.status,
        "log": result.log,
        "override_path": str(result.override_path),
    }


def _command_result_payload(result) -> dict:
    return {
        "project": result.project,
        "environment": result.environment,
        "status": result.status,
        "log": result.log,
        "override_path": str(result.override_path),
    }


app = create_app()

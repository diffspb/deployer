from pathlib import Path

from deployer.cli import main


def _project(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "deployer.yml").write_text(
        """
name: myapp
service: app
port: 8000
routes:
  - subdomain: myapp
"""
    )
    return tmp_path


def test_cli_validate(tmp_path: Path, capsys):
    project = _project(tmp_path)

    assert main(["validate", str(project)]) == 0

    assert "ok: myapp" in capsys.readouterr().out


def test_cli_render_override(tmp_path: Path, capsys):
    project = _project(tmp_path)

    assert main(["render-override", str(project)]) == 0

    assert "traefik.http.routers.myapp.rule" in capsys.readouterr().out


def test_cli_deploy_dry_run_and_history(tmp_path: Path, capsys):
    project = _project(tmp_path / "project")
    state_db = tmp_path / "state.db"

    assert main(["deploy", str(project), "--state-db", str(state_db), "--dry-run", "--version", "main"]) == 0
    assert "Dry run" in capsys.readouterr().out

    assert main(["history", "myapp", "--state-db", str(state_db)]) == 0
    assert "main" in capsys.readouterr().out


def test_cli_stop_dry_run_and_history_environment(tmp_path: Path, capsys):
    project = _project(tmp_path / "project")
    state_db = tmp_path / "state.db"

    assert main(["stop", str(project), "--state-db", str(state_db), "--dry-run", "--environment", "dev"]) == 0
    assert " stop" in capsys.readouterr().out

    assert main(["history", "myapp", "--state-db", str(state_db), "--environment", "dev"]) == 0
    output = capsys.readouterr().out
    assert "dev" in output
    assert "stop" in output

    assert main(["down", str(project), "--state-db", str(state_db), "--dry-run", "--environment", "dev"]) == 0
    assert " down" in capsys.readouterr().out

    assert main(["restart", str(project), "--state-db", str(state_db), "--dry-run", "--environment", "dev"]) == 0
    assert " restart" in capsys.readouterr().out


def test_cli_service_catalog_local_workflow(tmp_path: Path, capsys):
    project = _project(tmp_path / "project")
    state_db = tmp_path / "state.db"
    runtime_dir = tmp_path / "runtime"

    assert (
        main(
            [
                "services",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "add-local",
                "myapp",
                "--path",
                str(project),
            ]
        )
        == 0
    )
    assert "added\tmyapp\tlocal" in capsys.readouterr().out

    assert (
        main(
            [
                "runtime-targets",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "add",
                "myapp",
                "prod",
            ]
        )
        == 0
    )
    assert "added\tmyapp\tprod" in capsys.readouterr().out

    assert (
        main(
            [
                "env",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "set",
                "myapp",
                "prod",
                "TOKEN=abc",
            ]
        )
        == 0
    )
    assert "TOKEN" in capsys.readouterr().out

    assert (
        main(
            [
                "environments",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "add",
                "stage",
                "--url-prefix",
                "rc",
                "--deploy-mode",
                "webhook_auto",
                "--deploy-source",
                "tag",
                "--deploy-pattern",
                "^v.+-rc[0-9]+$",
                "--pattern-type",
                "regex",
            ]
        )
        == 0
    )
    assert "added\tstage" in capsys.readouterr().out

    assert (
        main(
            [
                "runtime-targets",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "add",
                "myapp",
                "stage",
            ]
        )
        == 0
    )
    assert "added\tmyapp\tstage" in capsys.readouterr().out

    assert (
        main(
            [
                "runtime-targets",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "list",
                "myapp",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "stage" in output
    assert "deploy_mode=webhook_auto" in output

    assert (
        main(
            [
                "environments",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "update",
                "stage",
                "--deploy-mode",
                "webhook_gated",
            ]
        )
        == 0
    )
    assert "deploy_mode=webhook_gated" in capsys.readouterr().out

    assert (
        main(
            [
                "deploy",
                "myapp",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "--dry-run",
                "--ref",
                "main",
                "--environment",
                "stage",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Dry run" in output
    assert str(runtime_dir / "services" / "myapp" / "overrides" / "stage.override.yml") in output

    assert main(["history", "myapp", "--state-db", str(state_db), "--runtime-dir", str(runtime_dir)]) == 0
    output = capsys.readouterr().out
    assert "service: myapp" in output
    assert "current: prod" in output
    assert "current: stage" in output
    assert "ref=main" in output

    assert (
        main(
            [
                "stop",
                "myapp",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "--dry-run",
            ]
        )
        == 0
    )
    assert " stop" in capsys.readouterr().out

    assert (
        main(
            [
                "down",
                "myapp",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "--dry-run",
            ]
        )
        == 0
    )
    assert " down" in capsys.readouterr().out

    assert (
        main(
            [
                "restart",
                "myapp",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "--dry-run",
            ]
        )
        == 0
    )
    assert " restart" in capsys.readouterr().out

    assert (
        main(
            [
                "services",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "list",
            ]
        )
        == 0
    )
    assert "myapp\tlocal" in capsys.readouterr().out

    assert (
        main(
            [
                "services",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "show",
                "myapp",
            ]
        )
        == 0
    )
    assert "environment: prod" in capsys.readouterr().out

    assert (
        main(
            [
                "env",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "list",
                "myapp",
                "prod",
            ]
        )
        == 0
    )
    assert "TOKEN=abc" in capsys.readouterr().out

    assert (
        main(
            [
                "env",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "render",
                "myapp",
                "prod",
            ]
        )
        == 0
    )
    assert "prod.env" in capsys.readouterr().out

    assert (
        main(
            [
                "env",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "unset",
                "myapp",
                "prod",
                "TOKEN",
            ]
        )
        == 0
    )
    assert "unset" in capsys.readouterr().out

    assert (
        main(
            [
                "services",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "remove",
                "myapp",
                "--delete-files",
            ]
        )
        == 0
    )
    assert "removed" in capsys.readouterr().out


def test_cli_environment_project_workflow(tmp_path: Path, capsys):
    source = tmp_path / "source"
    source.mkdir()
    state_db = tmp_path / "state.db"
    runtime_dir = tmp_path / "runtime"

    assert (
        main(
            [
                "projects",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "add-local",
                "dev",
                "tasktrack",
                "--path",
                str(source),
                "--default-ref",
                "dev",
                "--no-compose-file",
                "--deploy-mode",
                "webhook_auto",
                "--deploy-source",
                "branch",
                "--deploy-pattern",
                "dev",
                "--pattern-type",
                "exact",
            ]
        )
        == 0
    )
    assert "added\tdev\ttasktrack\tlocal" in capsys.readouterr().out

    assert (
        main(
            [
                "components",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "add",
                "dev",
                "tasktrack",
                "backend",
                "--mode",
                "build",
                "--build-context",
                "backend",
                "--dockerfile",
                "Dockerfile",
                "--port",
                "8000",
            ]
        )
        == 0
    )
    assert "added\tdev\ttasktrack\tbackend\tbuild" in capsys.readouterr().out

    assert (
        main(
            [
                "endpoints",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "add",
                "dev",
                "tasktrack",
                "api",
                "backend",
                "--port",
                "8000",
                "--subdomain",
                "api.tasktrack",
                "--auth",
                "sso",
                "--health-path",
                "/api/v1/health",
            ]
        )
        == 0
    )
    assert "added\tdev\ttasktrack\tapi\tbackend\t8000" in capsys.readouterr().out

    assert (
        main(
            [
                "dependencies",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "add",
                "dev",
                "tasktrack",
                "postgres",
                "--type",
                "postgres",
                "--target",
                "postgres-main/tasktrack_dev",
                "--output",
                "DATABASE_URL=postgresql://tasktrack_dev@example/tasktrack_dev",
            ]
        )
        == 0
    )
    assert "postgres-main/tasktrack_dev" in capsys.readouterr().out

    assert (
        main(
            [
                "projects",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "env-set",
                "dev",
                "tasktrack",
                "APP_ENV=dev",
            ]
        )
        == 0
    )
    assert "APP_ENV" in capsys.readouterr().out

    assert (
        main(
            [
                "projects",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "show",
                "dev",
                "tasktrack",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "environment: dev" in output
    assert "component: backend" in output
    assert "endpoint: api" in output
    assert "dependency: postgres" in output

    assert (
        main(
            [
                "resources",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "add",
                "dev",
                "postgres-main",
                "--type",
                "postgres",
                "--config",
                "host=postgres",
            ]
        )
        == 0
    )
    assert "postgres-main" in capsys.readouterr().out

    assert (
        main(
            [
                "bindings",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "add",
                "dev",
                "tasktrack",
                "app-db",
                "--resource",
                "postgres-main",
                "--component",
                "backend",
                "--config",
                "database=tasktrack_dev",
                "--config",
                "username=tasktrack_dev",
                "--config",
                "password=secret",
                "--mount",
                "dev_tasktrack_uploads:/app/uploads",
            ]
        )
        == 0
    )
    assert "app-db" in capsys.readouterr().out

    assert (
        main(
            [
                "bindings",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "list",
                "dev",
                "tasktrack",
            ]
        )
        == 0
    )
    assert "DATABASE_URL=postgresql://tasktrack_dev:secret@postgres:5432/tasktrack_dev" in capsys.readouterr().out

    assert (
        main(
            [
                "bindings",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "plan",
                "dev",
                "tasktrack",
                "app-db",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "binding: dev/tasktrack/app-db" in output
    assert "DATABASE_URL=postgresql://tasktrack_dev:secret@postgres:5432/tasktrack_dev" in output

    assert (
        main(
            [
                "bindings",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "apply",
                "dev",
                "tasktrack",
                "app-db",
                "--dry-run",
            ]
        )
        == 0
    )
    assert "Dry run command:" in capsys.readouterr().out

    assert (
        main(
            [
                "projects",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "env-render",
                "dev",
                "tasktrack",
            ]
        )
        == 0
    )
    assert "project.env" in capsys.readouterr().out

    assert (
        main(
            [
                "deploy",
                "dev",
                "tasktrack",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "--dry-run",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Dry run" in output
    assert "-p dev-tasktrack" in output
    assert "deployer.yml" not in output
    assert str(runtime_dir / "environments" / "dev" / "projects" / "tasktrack" / "overrides" / "dev.override.yml") in output


def test_cli_uses_config_defaults_for_catalog_commands(tmp_path: Path, capsys, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    state_db = tmp_path / "configured-state.db"
    runtime_dir = tmp_path / "configured-runtime"
    monkeypatch.setenv("DEPLOYER_STATE_DB", str(state_db))
    monkeypatch.setenv("DEPLOYER_RUNTIME_DIR", str(runtime_dir))

    assert main(["projects", "add-local", "dev", "myapp", "--path", str(source)]) == 0
    assert "added\tdev\tmyapp" in capsys.readouterr().out

    assert main(["projects", "list", "dev"]) == 0
    output = capsys.readouterr().out
    assert "dev\tmyapp\tlocal" in output
    assert state_db.exists()


def test_cli_env_set_requires_assignment(tmp_path: Path, capsys):
    project = _project(tmp_path / "project")
    state_db = tmp_path / "state.db"
    runtime_dir = tmp_path / "runtime"
    assert (
        main(
            [
                "services",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "add-local",
                "myapp",
                "--path",
                str(project),
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "env",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "set",
                "myapp",
                "prod",
                "BROKEN",
            ]
        )
        == 2
    )
    assert "KEY=value" in capsys.readouterr().err


def test_cli_returns_error_for_invalid_project(tmp_path: Path, capsys):
    assert main(["validate", str(tmp_path)]) == 2

    assert "Missing manifest" in capsys.readouterr().err

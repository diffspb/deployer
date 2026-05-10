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
                "deploy",
                "myapp",
                "--state-db",
                str(state_db),
                "--runtime-dir",
                str(runtime_dir),
                "--dry-run",
                "--ref",
                "main",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Dry run" in output
    assert str(runtime_dir / "services" / "myapp" / "overrides" / "prod.override.yml") in output

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

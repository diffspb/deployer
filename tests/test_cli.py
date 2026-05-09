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
  - host: myapp.busypage.ru
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


def test_cli_returns_error_for_invalid_project(tmp_path: Path, capsys):
    assert main(["validate", str(tmp_path)]) == 2

    assert "Missing manifest" in capsys.readouterr().err

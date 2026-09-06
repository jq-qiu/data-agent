from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deployment import deployment_router, mount_frontend
from app.scripts.serve import (
    DeploymentPreflightError,
    frontend_build_commands,
    runtime_paths,
    validate_frontend_build,
    validate_runtime_config,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def local_tmp_path() -> Iterator[Path]:
    temporary_root = REPOSITORY_ROOT / ".tmp" / "deployment-tests"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temporary_root) as directory:
        yield Path(directory)


def _write_config(path: Path, database: str) -> None:
    path.write_text(
        "db_dw:\n"
        f"  database: {database}\n"
        "  password: value-that-must-not-appear\n",
        encoding="utf-8",
    )


def test_runtime_config_requires_isolated_dw_without_echoing_values(
    local_tmp_path: Path,
) -> None:
    config = local_tmp_path / "app_config.yaml"
    _write_config(config, "data_agent_v1_dw")
    validate_runtime_config(config)

    _write_config(config, "unexpected_database")
    with pytest.raises(DeploymentPreflightError) as captured:
        validate_runtime_config(config)

    message = str(captured.value)
    assert "data_agent_v1_dw" in message
    assert "unexpected_database" not in message
    assert "value-that-must-not-appear" not in message


def test_runtime_config_missing_and_invalid_errors_are_safe(
    local_tmp_path: Path,
) -> None:
    missing = local_tmp_path / "missing.yaml"
    with pytest.raises(DeploymentPreflightError, match="Missing local configuration"):
        validate_runtime_config(missing)

    invalid = local_tmp_path / "invalid.yaml"
    invalid.write_text("db_dw: [", encoding="utf-8")
    with pytest.raises(DeploymentPreflightError) as captured:
        validate_runtime_config(invalid)

    assert "could not be read safely" in str(captured.value)
    assert "db_dw" not in str(captured.value)


def test_build_plan_uses_lock_install_only_when_needed(local_tmp_path: Path) -> None:
    paths = runtime_paths(local_tmp_path)
    missing_commands = frontend_build_commands(paths, "npm")
    assert [command[1:3] for command in missing_commands] == [
        ("ci", "--prefix"),
        ("run", "build"),
    ]

    paths.frontend_modules.mkdir(parents=True)
    existing_commands = frontend_build_commands(paths, "npm")
    forced_commands = frontend_build_commands(paths, "npm", force_install=True)
    assert [command[1:3] for command in existing_commands] == [("run", "build")]
    assert [command[1:3] for command in forced_commands] == [
        ("ci", "--prefix"),
        ("run", "build"),
    ]


def test_frontend_build_requires_index(local_tmp_path: Path) -> None:
    paths = runtime_paths(local_tmp_path)
    with pytest.raises(DeploymentPreflightError, match="missing index.html"):
        validate_frontend_build(paths)

    paths.frontend_index.parent.mkdir(parents=True)
    paths.frontend_index.write_text("ready", encoding="utf-8")
    validate_frontend_build(paths)


def test_static_frontend_liveness_and_api_route_precedence(
    local_tmp_path: Path,
) -> None:
    frontend_dist = local_tmp_path / "dist"
    assets = frontend_dist / "assets"
    assets.mkdir(parents=True)
    (frontend_dist / "index.html").write_text(
        '<!doctype html><script src="/assets/app.js"></script>',
        encoding="utf-8",
    )
    (assets / "app.js").write_text("window.ready = true;", encoding="utf-8")

    app = FastAPI()

    @app.post("/api/query")
    async def query() -> dict[str, str]:
        return {"route": "api"}

    app.include_router(deployment_router)
    assert mount_frontend(app, frontend_dist) is True

    with TestClient(app) as client:
        assert client.post("/api/query").json() == {"route": "api"}
        assert client.get("/api/health/live").json() == {"status": "ok"}
        assert "<!doctype html>" in client.get("/").text
        assert "window.ready" in client.get("/assets/app.js").text


def test_missing_build_keeps_api_only_app_valid(local_tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(deployment_router)

    assert mount_frontend(app, local_tmp_path / "missing") is False
    with TestClient(app) as client:
        assert client.get("/api/health/live").status_code == 200
        assert client.get("/").status_code == 404


def test_deployable_main_does_not_register_legacy_test_router() -> None:
    source = (Path(__file__).resolve().parents[2] / "main.py").read_text(
        encoding="utf-8"
    )
    assert "hello_router" not in source
    assert "mount_frontend(app)" in source

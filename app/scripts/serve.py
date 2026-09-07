"""创建并启动单进程 FastAPI 应用，注册 API 与前端静态资源。"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

ALLOWED_DW_DATABASE = "data_agent_v1_dw"


class DeploymentPreflightError(RuntimeError):
    """Safe operator-facing deployment preflight failure."""


@dataclass(frozen=True)
class RuntimePaths:
    repository_root: Path
    config: Path
    frontend: Path
    frontend_modules: Path
    frontend_index: Path


def runtime_paths(repository_root: Path | None = None) -> RuntimePaths:
    root = (repository_root or Path(__file__).resolve().parents[2]).resolve()
    frontend = root / "frontend"
    return RuntimePaths(
        repository_root=root,
        config=root / "conf" / "app_config.yaml",
        frontend=frontend,
        frontend_modules=frontend / "node_modules",
        frontend_index=frontend / "dist" / "index.html",
    )


def validate_runtime_config(config_path: Path) -> None:
    """Validate only deploy-critical structure without echoing configuration."""
    if not config_path.is_file():
        raise DeploymentPreflightError(
            "Missing local configuration: conf/app_config.yaml"
        )
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        raise DeploymentPreflightError(
            "Local configuration could not be read safely"
        ) from None
    if not isinstance(raw, Mapping):
        raise DeploymentPreflightError("Local configuration must be a mapping")
    db_dw = raw.get("db_dw")
    database = db_dw.get("database") if isinstance(db_dw, Mapping) else None
    if database != ALLOWED_DW_DATABASE:
        raise DeploymentPreflightError(
            "DW database must select the isolated data_agent_v1_dw database"
        )


def find_npm() -> str:
    for name in ("npm.cmd", "npm"):
        executable = shutil.which(name)
        if executable:
            return executable
    raise DeploymentPreflightError("npm is required to build the frontend")


def frontend_build_commands(
    paths: RuntimePaths,
    npm_executable: str,
    force_install: bool = False,
) -> tuple[tuple[str, ...], ...]:
    commands: list[tuple[str, ...]] = []
    if force_install or not paths.frontend_modules.is_dir():
        commands.append((npm_executable, "ci", "--prefix", str(paths.frontend)))
    commands.append((npm_executable, "run", "build", "--prefix", str(paths.frontend)))
    return tuple(commands)


def validate_frontend_build(paths: RuntimePaths) -> None:
    if not paths.frontend_index.is_file():
        raise DeploymentPreflightError("Frontend build is missing index.html")


def build_frontend(paths: RuntimePaths, force_install: bool = False) -> None:
    npm_executable = find_npm()
    commands = frontend_build_commands(paths, npm_executable, force_install)
    for command in commands:
        stage = "dependency installation" if command[1] == "ci" else "frontend build"
        try:
            subprocess.run(
                command,
                cwd=paths.repository_root,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError):
            raise DeploymentPreflightError(f"Failed during {stage}") from None
    validate_frontend_build(paths)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and serve the Data Agent frontend and API on one origin."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument(
        "--install",
        action="store_true",
        help="Force a clean npm ci before building.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Use an existing verified frontend build.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run preflight/build checks without starting Uvicorn.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    paths = runtime_paths()
    try:
        validate_runtime_config(paths.config)
        if args.skip_build:
            validate_frontend_build(paths)
        else:
            build_frontend(paths, force_install=args.install)
    except DeploymentPreflightError as error:
        print(f"Deployment preflight failed: {error}")
        return 2

    print("Deployment preflight passed for isolated DW and frontend build.")
    if args.check:
        return 0

    import uvicorn

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        workers=1,
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

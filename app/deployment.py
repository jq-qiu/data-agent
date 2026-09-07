"""提供进程存活检查，并在构建产物存在时挂载前端静态站点。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from starlette.staticfiles import StaticFiles

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FRONTEND_DIST = REPOSITORY_ROOT / "frontend" / "dist"

deployment_router = APIRouter(tags=["运行状态"])


@deployment_router.get("/api/health/live", include_in_schema=False)
async def liveness() -> dict[str, str]:
    """Report process liveness without claiming external-service readiness."""
    return {"status": "ok"}


def mount_frontend(
    app: FastAPI,
    directory: Path = DEFAULT_FRONTEND_DIST,
) -> bool:
    """Mount a verified Vite build after API routes, if one is present."""

    # 先验证入口文件，避免把缺失或未构建目录挂载为一个看似可用的前端。
    frontend_dist = directory.resolve()
    if not (frontend_dist / "index.html").is_file():
        return False
    app.mount(
        "/",
        StaticFiles(directory=str(frontend_dist), html=True),
        name="frontend",
    )
    return True

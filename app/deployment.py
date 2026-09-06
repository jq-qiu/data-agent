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
    frontend_dist = directory.resolve()
    if not (frontend_dist / "index.html").is_file():
        return False
    app.mount(
        "/",
        StaticFiles(directory=str(frontend_dist), html=True),
        name="frontend",
    )
    return True

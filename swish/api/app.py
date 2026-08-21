"""FastAPI application factory."""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from swish import __version__
from swish.config import Settings, settings_from_env
from swish.data.cache import Cache
from swish.data.fetch import Fetcher
from swish.data.repo import Repo
from swish.errors import NotEnoughData, PlayerNotFound, SourceUnavailable, SwishError

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def create_app(settings: Settings | None = None, repo: Repo | None = None) -> FastAPI:
    settings = settings or settings_from_env()
    settings.ensure_dirs()

    app = FastAPI(
        title="Swish",
        version=__version__,
        description="Estimate an NBA player's trade value from his stats and contract.",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    owns_repo = repo is None
    if repo is None:
        cache = Cache(settings.cache_url)
        repo = Repo(Fetcher(cache, settings))
    app.state.settings = settings
    app.state.repo = repo

    if owns_repo and not settings.offline:
        # warm the current-season leaderboard in the background so the first
        # player lookup only has to fetch that player's own page
        threading.Thread(target=repo.prewarm, daemon=True).start()

    from swish.api.routes import router

    app.include_router(router, prefix="/api")
    _install_error_handlers(app)

    if _WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")

    return app


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(PlayerNotFound)
    async def _not_found(_r: Request, exc: PlayerNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": str(exc), "query": exc.query, "suggestions": exc.suggestions},
        )

    @app.exception_handler(NotEnoughData)
    async def _thin(_r: Request, exc: NotEnoughData) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": str(exc)})

    @app.exception_handler(SourceUnavailable)
    async def _source(_r: Request, exc: SourceUnavailable) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": str(exc), "retry_after": exc.retry_after},
        )

    @app.exception_handler(SwishError)
    async def _swish(_r: Request, exc: SwishError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": str(exc)})

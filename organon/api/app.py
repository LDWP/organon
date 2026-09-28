"""FastAPI application serving the JSON API and the built frontend.

Once `web-app/` is built, the static React frontend is served by
the same process and port, as Toolforge requires.
"""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from organon.api.rate_limit import limiter
from organon.api.routes import (
    auth,
    commons_images,
    domains,
    generate,
    modules,
    search,
    sources,
    subtaxa_merge,
    taxobox_refresh,
    update,
)
from organon.api.schemas import VersionInfo
from organon.modules.bootstrap import ensure_modules_registered

try:
    VERSION = version("organon")
except PackageNotFoundError:  # run from a checkout without installing the package
    VERSION = "unknown"

# Production frontend build. Relative to the working directory, not
# `__file__`, which points into site-packages once installed.
STATIC_DIR = Path(os.environ.get("ORGANON_STATIC_DIR", "web-app/dist")).resolve()


def create_app() -> FastAPI:
    """Build the app: routers, middleware and SPA fallback."""
    ensure_modules_registered()

    app = FastAPI(
        title="Organon",
        version=VERSION,
        description="Génération de squelettes d'articles Wikipédia pour les taxons.",
    )

    app.state.limiter = limiter
    # slowapi's handler is stricter than the generic Starlette type.
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(SlowAPIMiddleware)

    app.include_router(generate.router, prefix="/api/v1", tags=["generate"])
    app.include_router(search.router, prefix="/api/v1", tags=["search"])
    app.include_router(modules.router, prefix="/api/v1", tags=["modules"])
    app.include_router(sources.router, prefix="/api/v1", tags=["sources"])
    app.include_router(domains.router, prefix="/api/v1", tags=["domains"])
    app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
    app.include_router(taxobox_refresh.router, prefix="/api/v1", tags=["taxobox"])
    app.include_router(commons_images.router, prefix="/api/v1", tags=["commons-images"])
    app.include_router(subtaxa_merge.router, prefix="/api/v1", tags=["subtaxa-merge"])
    app.include_router(update.router, prefix="/api/v1", tags=["update"])

    @app.get("/api/v1/version", response_model=VersionInfo)
    async def version() -> VersionInfo:
        return VersionInfo(version=VERSION)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    if STATIC_DIR.is_dir():
        # Catch-all, registered last so it never shadows /api/v1/* or
        # /healthz. Serves a static file if it exists, else index.html
        # for the client router. /api/* stays a JSON 404, not the SPA.
        @app.get("/{full_path:path}")
        async def spa(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not Found")
            # `full_path` is client input: stay inside STATIC_DIR
            # (path traversal).
            candidate = (STATIC_DIR / full_path).resolve()
            if candidate.is_relative_to(STATIC_DIR) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()

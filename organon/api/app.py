"""Application FastAPI — sert à la fois l'API JSON et, une fois `web-app/` buildé
(`npm run build`), le frontend React statique (voir organon/web-app/README.md). Un seul
process/port, contrainte de l'hébergement Toolforge.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from organon.api.routes import (
    auth,
    commons_images,
    domains,
    generate,
    modules,
    search,
    sources,
    taxobox_refresh,
)
from organon.modules.bootstrap import ensure_modules_registered

VERSION = "0.1.0"

# Build de production du frontend (`cd web-app && npm run build`). Chemin relatif au
# répertoire de travail du process (le build service Toolforge démarre le Procfile depuis la
# racine du dépôt) — pas relatif à `__file__`, qui pointerait vers site-packages une fois le
# paquet installé et ne trouverait jamais web-app/.
STATIC_DIR = Path(os.environ.get("ORGANON_STATIC_DIR", "web-app/dist")).resolve()


def create_app() -> FastAPI:
    ensure_modules_registered()

    app = FastAPI(
        title="Organon",
        version=VERSION,
        description="Génération de squelettes d'articles Wikipédia pour les taxons.",
    )

    # CORS uniquement en dev, quand le frontend Vite (port 5173) et l'API (port 8000) tournent
    # sur des origines différentes. En prod le frontend buildé est servi par ce même process
    # (voir STATIC_DIR ci-dessous) donc CORS devient inutile.
    if os.environ.get("ORGANON_DEV") == "1":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(generate.router, prefix="/api/v1", tags=["generate"])
    app.include_router(search.router, prefix="/api/v1", tags=["search"])
    app.include_router(modules.router, prefix="/api/v1", tags=["modules"])
    app.include_router(sources.router, prefix="/api/v1", tags=["sources"])
    app.include_router(domains.router, prefix="/api/v1", tags=["domains"])
    app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
    app.include_router(taxobox_refresh.router, prefix="/api/v1", tags=["taxobox"])
    app.include_router(commons_images.router, prefix="/api/v1", tags=["commons-images"])

    @app.get("/api/v1/version")
    async def version() -> dict[str, str]:
        return {"version": VERSION}

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    if STATIC_DIR.is_dir():
        # Route attrape-tout, enregistrée en dernier pour ne jamais court-circuiter /api/v1/*,
        # /healthz ci-dessus : sert un fichier statique s'il existe (JS/CSS buildés, favicon,
        # etc.), sinon index.html pour laisser React Router gérer la route côté client. Exclut
        # /api/* explicitement : un chemin API inconnu doit rester un 404 JSON, pas une page
        # HTML — sinon un client qui tape une route API erronée reçoit silencieusement le SPA.
        @app.get("/{full_path:path}")
        async def spa(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not Found")
            # full_path vient du client : résoudre puis vérifier qu'on reste dans STATIC_DIR
            # avant de servir, sinon une séquence "../" laisserait lire n'importe quel fichier
            # du pod (traversal).
            candidate = (STATIC_DIR / full_path).resolve()
            if candidate.is_relative_to(STATIC_DIR) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()

"""Dépendances FastAPI pour l'identification de l'utilisateur OAuth. Vérifie uniquement
l'identité — jamais un droit d'édition, qui reste du ressort combiné de
`organon.core.wiki_permissions` (autorisation) et `organon.core.mediawiki_bot` (compte bot
séparé qui édite réellement).
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request

from organon.api.session import SESSION_COOKIE_NAME, verify_session

# Contournement dev uniquement : sans ça, tester /generate en local (ORGANON_DEV=1) exigerait un
# aller-retour OAuth réel vers meta.wikimedia.org, impossible tant que le consumer n'accepte pas
# un callback localhost. Jamais actif en prod, où Toolforge ne positionne jamais ORGANON_DEV.
_DEV_USERNAME = "Utilisateur de développement"


def get_current_username(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    username = verify_session(token) if token else None
    if username is not None:
        return username
    if os.environ.get("ORGANON_DEV") == "1":
        return _DEV_USERNAME
    return None


def require_username(request: Request) -> str:
    username = get_current_username(request)
    if username is None:
        raise HTTPException(401, detail="Authentification requise (voir /api/v1/auth/login).")
    return username

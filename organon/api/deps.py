"""Dépendances FastAPI pour l'identification de l'utilisateur OAuth. Vérifie uniquement
l'identité — jamais un droit d'édition, qui reste du ressort combiné de
`organon.core.wiki_permissions` (autorisation) et `organon.core.mediawiki_bot` (compte bot
séparé qui édite réellement).
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from organon.api.session import SESSION_COOKIE_NAME, verify_session


def get_current_username(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    return verify_session(token)


def require_username(request: Request) -> str:
    username = get_current_username(request)
    if username is None:
        raise HTTPException(401, detail="Authentification requise (voir /api/v1/auth/login).")
    return username

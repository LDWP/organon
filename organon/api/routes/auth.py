"""Endpoints OAuth 2.0 utilisateur : identifient qui déclenche une action, sans donner aucun
droit d'édition — c'est le compte bot dédié (`organon.core.mediawiki_bot`) qui édite
réellement, sous réserve d'autorisation (`organon.core.wiki_permissions`), voir
`organon.api.routes.taxobox_refresh`.

Pas de session côté serveur : l'état anti-CSRF (`state`) et l'identité une fois confirmée
tiennent dans des cookies signés (`organon.api.session`), compatible plusieurs répliques sans
affinité de session.
"""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from organon.api.deps import get_current_username
from organon.api.session import (
    SESSION_COOKIE_NAME,
    STATE_COOKIE_NAME,
    sign_session,
    sign_state,
    verify_state,
)
from organon.core.auth_settings import get_auth_settings

router = APIRouter()


def _require_oauth_configured() -> None:
    settings = get_auth_settings()
    configured = bool(
        settings.oauth_client_id and settings.oauth_client_secret and settings.oauth_redirect_uri
    )
    if not configured:
        raise HTTPException(
            503,
            detail=(
                "OAuth non configuré côté serveur (ORGANON_OAUTH_CLIENT_ID / "
                "ORGANON_OAUTH_CLIENT_SECRET / ORGANON_OAUTH_REDIRECT_URI manquants) — "
                "nécessite l'enregistrement préalable d'un consumer OAuth 2.0."
            ),
        )


@router.get("/auth/login")
async def login() -> RedirectResponse:
    _require_oauth_configured()
    settings = get_auth_settings()

    state = secrets.token_urlsafe(24)
    params = {
        "response_type": "code",
        "client_id": settings.oauth_client_id,
        "redirect_uri": settings.oauth_redirect_uri,
        "state": state,
    }
    response = RedirectResponse(f"{settings.oauth_authorize_url}?{urlencode(params)}")
    response.set_cookie(
        STATE_COOKIE_NAME,
        sign_state(state),
        max_age=settings.oauth_state_max_age_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return response


@router.get("/auth/callback")
async def callback(request: Request, code: str, state: str) -> RedirectResponse:
    _require_oauth_configured()
    settings = get_auth_settings()

    state_cookie = request.cookies.get(STATE_COOKIE_NAME)
    if not state_cookie or not verify_state(state_cookie, expected=state):
        raise HTTPException(
            400, detail="État OAuth invalide ou expiré, merci de relancer la connexion."
        )

    async with AsyncOAuth2Client(
        settings.oauth_client_id,
        settings.oauth_client_secret,
        redirect_uri=settings.oauth_redirect_uri,
    ) as client:
        try:
            await client.fetch_token(
                settings.oauth_token_url, code=code, grant_type="authorization_code"
            )
            profile_resp = await client.get(settings.oauth_profile_url)
            profile_resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(
                502, detail=f"Échec de l'échange OAuth avec Wikimedia : {exc}"
            ) from exc
        profile = profile_resp.json()

    username = profile.get("username")
    if not username:
        raise HTTPException(
            502, detail="Réponse de profil OAuth invalide (nom d'utilisateur manquant)."
        )

    response = RedirectResponse(settings.frontend_post_login_url)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        sign_session(username),
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    response.delete_cookie(STATE_COOKIE_NAME)
    return response


@router.get("/auth/me")
async def me(request: Request) -> dict:
    username = get_current_username(request)
    return {"authenticated": username is not None, "username": username}


@router.post("/auth/logout")
async def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response

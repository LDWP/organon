"""User OAuth 2.0 endpoints.

They identify who triggers an action and grant no edit right: the
dedicated bot account (`organon.core.mediawiki_bot`) edits, subject
to `organon.core.wiki_permissions`; see
`organon.api.routes.taxobox_refresh`.

No server-side session: the anti-CSRF `state` and the confirmed
identity live in signed cookies (`organon.api.session`).
"""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx
from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from organon.api.deps import get_current_username
from organon.api.rate_limit import DEFAULT_RATE_LIMIT, limiter
from organon.api.session import (
    SESSION_COOKIE_NAME,
    STATE_COOKIE_NAME,
    sign_session,
    sign_state,
    verify_state,
)
from organon.core.auth_settings import AuthSettings, get_auth_settings
from organon.core.http import USER_AGENT

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
    """Redirect to the OAuth authorization page."""
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


def _oauth_client(settings: AuthSettings) -> AsyncOAuth2Client:
    """Return the OAuth client, sending the Organon User-Agent."""
    return AsyncOAuth2Client(
        settings.oauth_client_id,
        settings.oauth_client_secret,
        redirect_uri=settings.oauth_redirect_uri,
        headers={"User-Agent": USER_AGENT},
    )


@router.get("/auth/callback")
@limiter.limit(DEFAULT_RATE_LIMIT)
async def callback(request: Request, code: str, state: str) -> RedirectResponse:
    """Exchange the OAuth code and open the session."""
    _require_oauth_configured()
    settings = get_auth_settings()

    state_cookie = request.cookies.get(STATE_COOKIE_NAME)
    if not state_cookie or not verify_state(state_cookie, expected=state):
        raise HTTPException(
            400, detail="État OAuth invalide ou expiré, merci de relancer la connexion."
        )

    async with _oauth_client(settings) as client:
        try:
            await client.fetch_token(
                settings.oauth_token_url, code=code, grant_type="authorization_code"
            )
            profile_resp = await client.get(settings.oauth_profile_url)
            profile_resp.raise_for_status()
        except (httpx.HTTPError, OAuthError) as exc:
            # authlib raises OAuthError, not httpx.HTTPError, when the
            # token endpoint answers with a JSON `{"error": ...}`, e.g.
            # a code already used (callback page reloaded).
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
    """Return the authentication state and username."""
    username = get_current_username(request)
    return {"authenticated": username is not None, "username": username}


@router.post("/auth/logout")
async def logout() -> JSONResponse:
    """Delete the session cookie."""
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response

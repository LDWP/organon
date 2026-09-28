"""FastAPI dependencies identifying the OAuth user.

They check identity only, never edit rights, which belong to
`organon.core.wiki_permissions` (authorization) and
`organon.core.mediawiki_bot` (the editing bot account).
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request

from organon.api.session import SESSION_COOKIE_NAME, verify_session

# Dev-only bypass: avoids a real OAuth round trip when testing
# locally (ORGANON_DEV=1); refused when TOOL_DATA_DIR marks Toolforge.
_DEV_USERNAME = "Utilisateur de développement"


def dev_mode_active() -> bool:
    """Return True for local dev mode (`ORGANON_DEV=1`)."""
    return os.environ.get("ORGANON_DEV") == "1" and not os.environ.get("TOOL_DATA_DIR")


def get_current_username(request: Request) -> str | None:
    """Return the session username (dev user if ORGANON_DEV=1)."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    username = verify_session(token) if token else None
    if username is not None:
        return username
    if dev_mode_active():
        return _DEV_USERNAME
    return None


def require_username(request: Request) -> str:
    """Return the session username or raise 401."""
    username = get_current_username(request)
    if username is None:
        raise HTTPException(401, detail="Authentification requise (voir /api/v1/auth/login).")
    return username

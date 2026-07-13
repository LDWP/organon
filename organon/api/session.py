"""Cookies signés pour le flux OAuth : pas de stockage serveur, l'état `state` (anti-CSRF) et
la session utilisateur identifiée tiennent dans des cookies signés par `itsdangerous`, jamais
dans une base de données ou une mémoire de session côté serveur (compatible plusieurs
répliques, aucune affinité de session requise).
"""

from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from organon.core.auth_settings import get_auth_settings

STATE_COOKIE_NAME = "organon_oauth_state"
SESSION_COOKIE_NAME = "organon_session"

_STATE_SALT = "organon-oauth-state"
_SESSION_SALT = "organon-session"


def _serializer(salt: str) -> URLSafeTimedSerializer:
    settings = get_auth_settings()
    if not settings.session_secret_key:
        raise RuntimeError(
            "ORGANON_SESSION_SECRET_KEY n'est pas configuré : impossible de signer les cookies."
        )
    return URLSafeTimedSerializer(settings.session_secret_key, salt=salt)


def sign_state(state: str) -> str:
    return _serializer(_STATE_SALT).dumps(state)


def verify_state(token: str, *, expected: str) -> bool:
    settings = get_auth_settings()
    try:
        value = _serializer(_STATE_SALT).loads(token, max_age=settings.oauth_state_max_age_seconds)
    except (BadSignature, SignatureExpired):
        return False
    return isinstance(value, str) and value == expected


def sign_session(username: str) -> str:
    return _serializer(_SESSION_SALT).dumps({"username": username})


def verify_session(token: str) -> str | None:
    settings = get_auth_settings()
    try:
        data = _serializer(_SESSION_SALT).loads(token, max_age=settings.session_max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    username = data.get("username")
    return username if isinstance(username, str) else None

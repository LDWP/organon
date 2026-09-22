"""Deployment secrets and settings, read from `ORGANON_*` variables.

Unrelated to `organon.core.config.GenerateOptions`, which holds the
per-article generation options.
"""

from __future__ import annotations

from functools import cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from organon.core.http import USER_AGENT


class AuthSettings(BaseSettings):
    """OAuth, bot account and API-key settings."""

    model_config = SettingsConfigDict(env_prefix="ORGANON_", extra="ignore")

    # OAuth 2.0 identification only. The consumer is limited to frwiki,
    # so the endpoints must point to fr.wikipedia.org.
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_redirect_uri: str = ""
    oauth_authorize_url: str = "https://fr.wikipedia.org/w/rest.php/oauth2/authorize"
    oauth_token_url: str = "https://fr.wikipedia.org/w/rest.php/oauth2/access_token"
    oauth_profile_url: str = "https://fr.wikipedia.org/w/rest.php/oauth2/resource/profile"

    # Signed cookies (OAuth flow state and user session).
    session_secret_key: str = ""
    oauth_state_max_age_seconds: int = 600
    session_max_age_seconds: int = 28800  # 8h
    # Set to False only for local development over plain http.
    cookie_secure: bool = True

    # Where to send the browser after the OAuth callback (Vite in
    # development by default). A navigation redirect, so no CORS.
    frontend_post_login_url: str = "http://localhost:5173/"

    # Dedicated bot account (Bot Password), never the acting user.
    bot_username: str = ""
    bot_password: str = ""
    wiki_api_url: str = "https://fr.wikipedia.org/w/api.php"
    user_agent: str = USER_AGENT

    # Permission page, read fail-closed with a short TTL cache. A real
    # wiki page path; keep in sync with wiki_permissions.py and tests.
    permission_page_title: str = "Wikipédia:Projet:Biologie/Taxobot/user.json"
    permission_cache_ttl_seconds: float = 300.0

    # Bot edits stay off until the community approves the bot and the
    # permission page is write-protected. OAuth login is independent.
    bot_edit_enabled: bool = False

    # LPSN requires an individual free DSMZ account. Empty values make
    # the module fail authentication cleanly.
    lpsn_username: str = ""  # envvars ORGANON_LPSN_USERNAME
    lpsn_password: str = ""  # envvars ORGANON_LPSN_PASSWORD

    # BHL needs a free individual key. Empty skips BHL enrichment.
    bhl_api_key: str = ""  # envvars ORGANON_BHL_API_KEY

    # Tropicos: public token of the site's own search widget (not a
    # personal secret); override it if Tropicos rotates it.
    tropicos_token: str = (
        "RjRGNDA4RDgtOEY2NS00NzVGLUI3NDktRjk4MjE2Q0NCRTQ1"  # envvars ORGANON_TROPICOS_TOKEN
    )

    # IUCN Red List needs a free non-commercial token. Empty skips it.
    iucn_api_token: str = ""  # envvars ORGANON_IUCN_API_TOKEN


@cache
def get_auth_settings() -> AuthSettings:
    """Return the process-wide `AuthSettings`, created on first use."""
    return AuthSettings()

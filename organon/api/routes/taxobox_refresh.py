"""POST /api/v1/taxobox/refresh: edit a page through the bot account.

On behalf of an identified, authorized user. Deliberately generic:
it rewrites the full wikitext of the page rather than replacing
only its taxobox section, whose location and merge logic is yet to
be specified.

Disabled by default (`AuthSettings.bot_edit_enabled`) until the
community settles the bot status and an administrator write-
protects the permission page. Enabling it is a deployment decision,
not a code change.
"""

from __future__ import annotations

from functools import cache

from fastapi import APIRouter, Depends, HTTPException, Request

from organon.api.deps import require_username
from organon.api.rate_limit import DEFAULT_RATE_LIMIT, limiter
from organon.api.schemas import TaxoboxRefreshRequest, TaxoboxRefreshResponse
from organon.core.auth_settings import get_auth_settings
from organon.core.mediawiki_bot import BotEditError, MediaWikiBotClient
from organon.core.wiki_permissions import WikiPermissionChecker

router = APIRouter()


@cache
def get_permission_checker() -> WikiPermissionChecker:
    """Return the shared permission checker, created on first use."""
    settings = get_auth_settings()
    return WikiPermissionChecker(
        api_url=settings.wiki_api_url,
        page_title=settings.permission_page_title,
        ttl_seconds=settings.permission_cache_ttl_seconds,
        user_agent=settings.user_agent,
    )


@router.post("/taxobox/refresh", response_model=TaxoboxRefreshResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def refresh_taxobox(
    request: Request, req: TaxoboxRefreshRequest, username: str = Depends(require_username)
) -> TaxoboxRefreshResponse:
    """Write `req.wikitext` to the page as the bot."""
    settings = get_auth_settings()

    if not settings.bot_edit_enabled:
        raise HTTPException(
            503,
            detail=(
                "Édition par le bot désactivée : en attente de la clarification communautaire du "
                "statut du bot (voir Discussion Projet:Biologie/Organon) et de la protection en "
                "écriture de la page de permission."
            ),
        )

    checker = get_permission_checker()
    if not await checker.is_authorized(username):
        raise HTTPException(
            403,
            detail=(
                f"Utilisateur « {username} » non autorisé (voir {settings.permission_page_title})."
            ),
        )

    if not (settings.bot_username and settings.bot_password):
        raise HTTPException(500, detail="Identifiants du compte bot non configurés côté serveur.")

    summary = f"Rafraîchissement taxobox via Organon, demandé par [[Utilisateur:{username}]]"
    try:
        async with MediaWikiBotClient(
            api_url=settings.wiki_api_url,
            username=settings.bot_username,
            password=settings.bot_password,
            user_agent=settings.user_agent,
        ) as bot:
            result = await bot.edit_page(title=req.page_title, text=req.wikitext, summary=summary)
    except BotEditError as exc:
        raise HTTPException(502, detail=str(exc)) from exc

    return TaxoboxRefreshResponse(
        page_title=result.get("title", req.page_title),
        new_revision_id=result["newrevid"],
        requested_by=username,
    )

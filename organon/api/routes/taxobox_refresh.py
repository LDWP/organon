"""POST /api/v1/taxobox/refresh — déclenche une édition par le compte bot dédié pour le compte
d'un utilisateur identifié et autorisé.

Volontairement générique : réécrit le wikitexte complet de la page (censé provenir du frontend,
par ex. de `/api/v1/generate`) plutôt que de repérer et remplacer seulement la section taxobox
d'un article existant — cette logique de repérage/fusion reste à spécifier avant d'être
implémentée, pour éviter d'inventer un comportement non validé.

**Désactivé par défaut** (`AuthSettings.bot_edit_enabled=False`) tant que (a) le statut du bot
n'a pas été tranché par la communauté sur `Discussion Projet:Biologie/Taxobot` et (b) la page de
permission n'est pas protégée en écriture par un administrateur frwiki. Basculer ce flag est une
décision de mise en service, pas de code.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from organon.api.deps import require_username
from organon.api.schemas import TaxoboxRefreshRequest, TaxoboxRefreshResponse
from organon.core.auth_settings import get_auth_settings
from organon.core.mediawiki_bot import BotEditError, MediaWikiBotClient
from organon.core.wiki_permissions import WikiPermissionChecker

router = APIRouter()

_permission_checker: WikiPermissionChecker | None = None


def _get_permission_checker() -> WikiPermissionChecker:
    global _permission_checker
    if _permission_checker is None:
        settings = get_auth_settings()
        _permission_checker = WikiPermissionChecker(
            api_url=settings.wiki_api_url,
            page_title=settings.permission_page_title,
            ttl_seconds=settings.permission_cache_ttl_seconds,
            user_agent=settings.user_agent,
        )
    return _permission_checker


@router.post("/taxobox/refresh", response_model=TaxoboxRefreshResponse)
async def refresh_taxobox(
    req: TaxoboxRefreshRequest, username: str = Depends(require_username)
) -> TaxoboxRefreshResponse:
    settings = get_auth_settings()

    if not settings.bot_edit_enabled:
        raise HTTPException(
            503,
            detail=(
                "Édition par le bot désactivée : en attente de la clarification communautaire du "
                "statut du bot (voir Discussion Projet:Biologie/Taxobot) et de la protection en "
                "écriture de la page de permission."
            ),
        )

    checker = _get_permission_checker()
    if not await checker.is_authorized(username):
        raise HTTPException(
            403,
            detail=(
                f"Utilisateur « {username} » non autorisé "
                f"(voir {settings.permission_page_title})."
            ),
        )

    if not (settings.bot_username and settings.bot_password):
        raise HTTPException(500, detail="Identifiants du compte bot non configurés côté serveur.")

    bot = MediaWikiBotClient(
        api_url=settings.wiki_api_url,
        username=settings.bot_username,
        password=settings.bot_password,
        user_agent=settings.user_agent,
    )
    summary = f"Rafraîchissement taxobox via Organon, demandé par [[Utilisateur:{username}]]"
    try:
        result = await bot.edit_page(title=req.page_title, text=req.wikitext, summary=summary)
    except BotEditError as exc:
        raise HTTPException(502, detail=str(exc)) from exc
    finally:
        await bot.aclose()

    return TaxoboxRefreshResponse(
        page_title=result.get("title", req.page_title),
        new_revision_id=result["newrevid"],
        requested_by=username,
    )

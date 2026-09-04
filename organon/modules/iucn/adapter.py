"""Couche d'accès réseau pour l'API IUCN Red List v4 (api.iucnredlist.org) : appels HTTP et
décodage JSON bruts uniquement, aucune logique métier (voir module.py).

Jeton individuel gratuit requis (inscription sur https://api.iucnredlist.org/users/sign_up, voir
`organon.core.auth_settings.AuthSettings.iucn_api_token`) : contrairement à Tropicos, l'UICN
n'expose aucun jeton public partageable, chaque déploiement doit enregistrer le sien."""

from __future__ import annotations

import httpx

from organon.core.auth_settings import get_auth_settings
from organon.core.http import OwnedClientMixin, fetch_json

BASE_URL = "https://api.iucnredlist.org/api/v4"


class IucnAdapter(OwnedClientMixin):
    def __init__(self, client: httpx.AsyncClient | None = None, token: str | None = None) -> None:
        self._token = token if token is not None else get_auth_settings().iucn_api_token
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else None
        super().__init__(client, headers=headers)

    async def scientific_name(
        self, genus_name: str, species_name: str, infra_name: str | None = None
    ) -> dict | None:
        """Résultat de `/taxa/scientific_name` : identité du taxon + historique complet de ses
        évaluations (voir `module.py` pour le choix de l'évaluation retenue parmi celles-ci). Pas
        d'appel à `/assessment/{id}` séparé : cette réponse porte déjà `red_list_category_code`
        et `criteria` par évaluation, seuls champs exploités ici."""
        if not self._token:
            # Jeton absent : module simplement sauté (voir docstring de tête d'adapter.py),
            # pas d'appel réseau voué à un 401.
            return None
        params: dict[str, str] = {"genus_name": genus_name, "species_name": species_name}
        if infra_name:
            params["infra_name"] = infra_name
        return await fetch_json(self._client, f"{BASE_URL}/taxa/scientific_name", params=params)

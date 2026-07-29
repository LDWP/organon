"""Couche d'accès réseau pour DORIS (doris.ffessm.fr, fédération française d'études et de sports
sous-marins) : aucune API publique (`/Especes/api` -> 404, voir organon/core/data/db_inventory.yaml,
id: doris), mais une recherche HTML fonctionnelle par nom.

Le formulaire de recherche du site POST `(name)=<requête>` et `DestinationURL=find/species` vers
`/content/action`, qui redirige (302, POST->GET suivi automatiquement par httpx) vers la page de
résultats `/find/species/(name)/<requête>` — recherche plein texte classée par pertinence, pas un
filtrage exact côté serveur : le filtrage exact sur le nom scientifique se fait donc côté client,
sur la première page de résultats seulement (pas de pagination suivie, la correspondance exacte
apparaît systématiquement en tête des résultats en pratique).

La fiche espèce elle-même n'est pas récupérée ici (pas d'auteur collecté) : son URL nécessite un
slug complet (`/Especes/Genre-espece-Nom-commun-ID`, un ID nu comme `/Especes/344` renvoie 404),
contrairement à l'ancienne URL `fiche2.asp?fiche_numero=ID` conservée en redirection permanente et
utilisée par `organon.modules.doris.module` pour le lien de debug."""

from __future__ import annotations

import re

import httpx

SEARCH_URL = "https://doris.ffessm.fr/content/action"
LEGACY_FICHE_URL = "https://doris.ffessm.fr/fiche2.asp"

_RESULT_RE = re.compile(
    r'<a href="https://doris\.ffessm\.fr/Especes/[^"]+-(?P<id>\d+)/\(rOffset\)/\d+">\s*'
    r"(?P<nom_commun>[^<]*)<br>\s*<em>(?P<nom_scientifique>[^<]+)</em>\s*</a>"
)


class DorisAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0, follow_redirects=True)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(self, nom: str) -> tuple[str, str] | None:
        """Renvoie `(id_fiche, nom_commun)` pour la première correspondance dont le nom
        scientifique est exactement `nom`, ou `None` si aucune ne correspond."""
        resp = await self._client.post(
            SEARCH_URL, data={"DestinationURL": "find/species", "(name)": nom}
        )
        resp.raise_for_status()
        for match in _RESULT_RE.finditer(resp.text):
            if match.group("nom_scientifique").strip() == nom:
                return match.group("id"), match.group("nom_commun").strip()
        return None

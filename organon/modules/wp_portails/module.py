"""Logique métier du module `wp_portails` : ancrage catégorie dynamique pour le choix du
`{{Portail|...}}` de fin d'article — lu par
`organon.core.selectors.categorization.lien_pour_portail` en repli quand aucune règle statique de
`organon.core.selectors.rules.portails.yaml` ne matche, avant le repli final sur le portail
générique par règne (`_PORTAIL_PAR_REGNE`).

Rangs testés dans cet ordre, du plus spécifique au plus général : famille, ordre, classe — le
taxon généré lui-même est candidat pour son propre rang (générer l'article "Gadidae" teste
l'article Gadidae lui-même, pas seulement ses ascendants). Validé empiriquement sur une vingtaine
de cas (familles, ordres et classes, tous règnes) : l'étape de repli initialement envisagée
(échantillonner les premiers articles de la catégorie quand l'article du taxon n'existe pas) n'a
jamais été nécessaire en pratique — sur frwiki, soit le taxon a un article, soit aucun de ses
membres n'en a non plus — et n'est donc pas implémentée ici."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.modules.wp_portails.adapter import WpPortailsAdapter

_RANGS_ANCRAGE = ("famille", "ordre", "classe")


def _candidats_ancrage(struct: Struct) -> list[tuple[str, str]]:
    candidats = []
    if struct.taxon.rang in _RANGS_ANCRAGE:
        candidats.append((struct.taxon.rang, struct.taxon.nom))
    candidats.extend((r.rang, r.nom) for r in struct.rangs if r.rang in _RANGS_ANCRAGE)
    return candidats


class WpPortailsModule(TaxonomyModule):
    meta = ModuleMeta(
        id="wp_portails", can_classify=False, can_render_external_link=False, domains="all"
    )

    def __init__(self, adapter: WpPortailsAdapter | None = None) -> None:
        self._adapter = adapter or WpPortailsAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        if is_classification:
            return None
        for rang, nom in _candidats_ancrage(struct):
            portails = await self._adapter.portails(nom)
            if portails:
                struct.liens["wp_portails"] = {"portails": portails, "rang": rang, "nom": nom}
                return struct
        return None

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("wp_portails")
        if not data:
            return None
        titre = data["nom"].replace(" ", "_")
        return (
            f"<a href='https://fr.wikipedia.org/wiki/{titre}' target='_blank' "
            f"rel='noopener noreferrer'>Portail ({data['rang']} : {data['nom']})</a>"
        )


register_module(WpPortailsModule)

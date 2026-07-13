"""Module archivé : retiré du registre actif (voir organon.modules.bootstrap), plus proposé ni
exécuté comme classifieur. iNaturalist est un site collaboratif (identifications
participatives) — pas une autorité nomenclaturale, incompatible avec l'exigence de fiabilité
attendue d'une source de classification pour un article Wikipédia. Le code reste ici tel quel
(fonctionnel, juste plus appelé) au cas où cette contrainte serait reconsidérée ; ne pas
réenregistrer sans revoir ce point.

Logique métier du module iNaturalist : classification, sous-taxons, noms vernaculaires,
via l'API REST (voir adapter.py). Base communautaire (identifications participatives), pas une
autorité nomenclaturale : aucun champ auteur n'est exposé par l'API.

La classification est reconstruite à partir de `ancestors` (lignée racine -> taxon, rang+nom
pour chaque nœud) en cherchant le premier nœud de rang `kingdom` — contrairement à Open Tree of
Life, iNaturalist pose ce rang de façon fiable et systématique (huit groupes attendus, tous déjà
couverts par `core.domains.KINGDOM_MAP`, voir ranks.py).

Le suivi de synonyme est simplifié à un seul niveau (pas de boucle `MAX_SYNONYM_HOPS`) : un
taxon inactif (`is_active: false`) pointe vers son remplaçant via `current_synonymous_taxon_ids`,
une liste rarement plus longue qu'un élément dans la pratique observée.

Sans modèle Bioref dédié sur Wikipédia en français (aucun modèle "iNaturalist"/"INaturalist"
n'existe — vérifié en direct, une redirection existe mais pointe vers une page inexistante),
`render_bioref` utilise le modèle générique {{Lien web}}."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.domains import KINGDOM_MAP
from organon.core.models import RankName, Redirection, Struct, SubTaxonList, TaxonInfo
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import as_limit, simple_debug_link
from organon.modules.inaturalist.adapter import InaturalistAdapter
from organon.modules.inaturalist.ranks import inat_rang


class InaturalistModule(TaxonomyModule):
    meta = ModuleMeta(id="inaturalist", can_classify=True, can_render_external_link=True, domains="all")

    def __init__(self, adapter: InaturalistAdapter | None = None) -> None:
        self._adapter = adapter or InaturalistAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        results = await self._adapter.search(struct.taxon.nom)
        exact = [r for r in results if r.get("name") == struct.taxon.nom]
        if not exact:
            return None
        # iNaturalist peut avoir deux fiches actives distinctes portant exactement le même nom
        # affiché (un "species complex" et l'espèce qu'il regroupe) — vérifié en direct sur
        # *Quercus robur* (id 1520309, rank=complex ; id 56133, rank=species). Le rang "espèce"
        # est préféré en cas d'ambiguïté, une requête étant presque toujours un binôme visant
        # l'espèce elle-même plutôt que le complexe qui la contient.
        cur = next(
            (r for r in exact if r.get("is_active", True) and r.get("rank") == "species"),
            next((r for r in exact if r.get("is_active", True)), exact[0]),
        )

        detail = await self._adapter.taxon(cur["id"])
        if detail is None:
            return None

        is_synonym = not detail.get("is_active", True)
        if is_synonym:
            if not is_classification:
                rang = inat_rang(detail.get("rank") or "")
                struct.liens["inaturalist"] = {
                    "id": detail["id"],
                    "nom": detail["name"],
                    "synonyme": True,
                    **({"rang": rang} if rang else {}),
                }
                return struct
            replacement_ids = detail.get("current_synonymous_taxon_ids") or []
            if options.suivre_synonymes and replacement_ids:
                accepted = await self._adapter.taxon(replacement_ids[0])
                if accepted is None:
                    return None
                struct.redirection = Redirection(nom=struct.taxon.nom)
                struct.taxon = TaxonInfo(nom=accepted["name"])
                detail = accepted
                is_synonym = False
            # sinon : on continue avec les données du taxon inactif tel quel (même principe
            # que GBIF/IRMNG quand le suivi de synonyme est désactivé), en conservant le
            # marqueur "synonyme" pour le rendu Bioref.

        inat_link = {"id": detail["id"], "nom": detail["name"]}
        rang = inat_rang(detail.get("rank") or "")
        if rang:
            inat_link["rang"] = rang
        if detail.get("extinct"):
            inat_link["eteint"] = True
        if is_synonym:
            inat_link["synonyme"] = True
        struct.liens["inaturalist"] = inat_link

        if not is_classification:
            return struct

        regne = None
        rangs_root_first: list[RankName] = []
        seen_kingdom = False
        for node in detail.get("ancestors", []):
            if node.get("rank") == "kingdom":
                regne = KINGDOM_MAP.get(node["name"])
                seen_kingdom = True
                continue
            if not seen_kingdom:
                continue
            wp_rang = inat_rang(node.get("rank") or "")
            if wp_rang:
                rangs_root_first.append(RankName(nom=node["name"], rang=wp_rang))
        if not regne:
            return None
        struct.regne = regne
        struct.rangs = list(reversed(rangs_root_first))

        struct.taxon.nom = detail["name"]
        if rang:
            struct.taxon.rang = rang
        if detail.get("extinct"):
            struct.taxon.eteint = True

        struct.classification = "INAT"
        struct.classification_taxobox = "iNaturalist"

        children = detail.get("children") or []
        if children:
            liste = [RankName(nom=c["name"], rang=inat_rang(c.get("rank") or "")) for c in children]
            limit = as_limit(options.limite_listes)
            coupe = limit is not None and len(liste) > limit
            if coupe:
                liste = liste[:limit]
            struct.sous_taxons = SubTaxonList(liste=liste, source="iNaturalist", coupe=coupe)

        noms_fr = []
        for entry in detail.get("names", []):
            if entry.get("lexicon") == "french" and entry.get("name") not in noms_fr:
                noms_fr.append(entry["name"])
        if noms_fr:
            struct.vernaculaire["iNaturalist"] = noms_fr

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("inaturalist")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], data.get("rang", struct.taxon.rang), struct.regne)
        eteint = "† " if data.get("eteint") else ""
        post = " <small>(non valide)</small>" if data.get("synonyme") else ""
        url = f"https://www.inaturalist.org/taxa/{data['id']}"
        return (
            f"{{{{Lien web | langue=en | titre={eteint}{cible} | url={url} "
            f"| site=iNaturalist | consulté le={cdate} }}}}{post}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(struct, "inaturalist", "https://www.inaturalist.org/taxa/{id}", "iNaturalist")


register_module(InaturalistModule)

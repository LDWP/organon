"""Logique métier du module ITIS : classification, synonymes, sous-taxons, noms vernaculaires.
Le suivi de synonyme relance la collecte sur le taxon cible en conservant le même mode
(classification complète ou liens seulement).
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Redirection, Struct, SubTaxonList, SynonymList, TaxonInfo
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import MAX_SYNONYM_HOPS, format_auteur, simple_debug_link
from organon.modules.itis.adapter import ItisAdapter
from organon.modules.itis.ranks import RANGS_REGNE, itis_cherche_rang, itis_cherche_regne


class ItisModule(TaxonomyModule):
    meta = ModuleMeta(
        id="itis", can_classify=True, can_render_external_link=True, domains="all", priority=998
    )

    def __init__(self, adapter: ItisAdapter | None = None) -> None:
        self._adapter = adapter or ItisAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        return await self._collect(struct, is_classification, options, hop=0)

    async def _collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions, hop: int
    ) -> Struct | None:
        adapter = self._adapter
        taxon = struct.taxon.nom

        results = await adapter.search_by_scientific_name(taxon)
        if not results:
            return None

        match = results[0]
        if len(results) > 1:
            exact = next((sn for sn in results if sn.get("combinedName") == taxon), None)
            if exact is not None:
                match = exact

        if not match.get("tsn"):
            return None
        tsn = match["tsn"]

        if is_classification and match.get("kingdom"):
            struct.regne = itis_cherche_regne(match["kingdom"])

        struct.liens["itis"] = {"id": tsn, "nom": match.get("combinedName") or taxon}
        if match.get("author"):
            struct.liens["itis"]["auteur"] = format_auteur(match["author"])
        if not is_classification and match.get("kingdom"):
            # Signal de règne détecté sans appel réseau supplémentaire : "kingdom" est déjà
            # présent dans la réponse de recherche utilisée ci-dessus. Voir RegneIncoherence.
            regne_detecte = itis_cherche_regne(match["kingdom"])
            if regne_detecte:
                struct.liens["itis"]["regne_detecte"] = regne_detecte

        accepted = await adapter.accepted_names(tsn)
        accepted_entry = next((a for a in accepted if a.get("acceptedName")), None)
        if accepted_entry is not None:
            if not is_classification:
                struct.liens["itis"]["synonyme"] = True
                struct.liens["itis"]["nom-synonyme"] = accepted_entry["acceptedName"]
                struct.liens["itis"]["id-synonyme"] = accepted_entry.get("acceptedTsn")
                return struct
            if options.suivre_synonymes:
                if hop >= MAX_SYNONYM_HOPS:
                    return None
                struct.redirection = Redirection(nom=struct.taxon.nom)
                struct.taxon = TaxonInfo(nom=accepted_entry["acceptedName"])
                return await self._collect(struct, is_classification, options, hop=hop + 1)
            # suivre_synonymes désactivé : on continue avec les données du synonyme tel quel

        if not is_classification:
            return struct

        rang = await adapter.rank_name(tsn)
        if rang is None:
            return None
        auteur = await adapter.authorship(tsn)

        if auteur:
            struct.taxon.auteur = format_auteur(auteur)
        struct.taxon.rang = itis_cherche_rang(rang)
        struct.classification = "ITIS"
        struct.classification_taxobox = "itis"

        hierarchy = await adapter.full_hierarchy(tsn)
        rangs: list[RankName] = []
        for entry in hierarchy:
            if entry.get("tsn") == tsn:
                continue  # le taxon lui-même (dernière entrée de la hiérarchie complète)
            rang_wp = itis_cherche_rang(entry.get("rankName") or "")
            if rang_wp in RANGS_REGNE:
                continue  # le "règne" est stocké dans struct.regne, pas dans struct.rangs
            rangs.append(
                RankName(nom=entry["taxonName"], rang=rang_wp, auteur=format_auteur(entry.get("author")))
            )
        rangs.reverse()  # racine->feuille dans la réponse ITIS ; on veut proche->lointain
        struct.rangs = rangs

        children = await adapter.hierarchy_down(tsn)
        sous_taxons_liste = [
            RankName(
                nom=c["taxonName"],
                auteur=format_auteur(c.get("author")),
                rang=itis_cherche_rang(c["rankName"]) if c.get("rankName") else None,
            )
            for c in children
            if c.get("taxonName")
        ]
        if sous_taxons_liste:
            struct.sous_taxons = SubTaxonList(liste=sous_taxons_liste, source="ITIS")

        synonyms = await adapter.synonym_names(tsn)
        synonym_liste = [
            RankName(nom=s["sciName"], auteur=format_auteur(s.get("author"))) for s in synonyms
        ]
        if synonym_liste:
            struct.synonymes = SynonymList(liste=synonym_liste, source="ITIS")

        common = await adapter.common_names(tsn)
        vernaculaire = [
            c["commonName"] for c in common if c.get("language") == "French" and c.get("commonName")
        ]
        if vernaculaire:
            struct.vernaculaire["ITIS"] = vernaculaire

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("itis")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], struct.taxon.rang, struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]
        if data.get("synonyme"):
            return f"{{{{ITIS | {data['id']} | {cible} | nv | consulté le={cdate} }}}}"
        return f"{{{{ITIS | {data['id']} | {cible} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(
            struct,
            "itis",
            "https://www.itis.gov/servlet/SingleRpt/SingleRpt?search_topic=TSN&search_value={id}",
            "ITIS",
        )


register_module(ItisModule)

"""Logique métier du module WoRMS : classification, synonymes, sous-taxons, noms vernaculaires,
via l'API REST (voir adapter.py).

Le suivi de synonyme utilise `valid_AphiaID` (renvoyé directement par AphiaRecordsByName/
AphiaRecordByAphiaID) pour récupérer directement la fiche du taxon accepté par ID, sans
repasser par une recherche textuelle.

La « publication originale » (struct.originale) n'a aucun champ REST structuré équivalent : le
seul champ disponible est scrapé depuis la page HTML de détail
(`WrmsAdapter.original_description`, voir `organon.modules.common.
extract_aphia_original_description`) — la seule exception à "REST uniquement" dans ce module.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Basionym, RankName, Redirection, Struct, SubTaxonList, SynonymList, TaxonInfo
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import MAX_SYNONYM_HOPS, as_limit, collect_pages, format_auteur, simple_debug_link
from organon.modules.wrms.adapter import WrmsAdapter
from organon.modules.wrms.ranks import CHARTES_GARDENT_REGNE, RANGS_REGNE, wrms_charte, wrms_rang


PAGE_SIZE = 50
"""Taille de page de l'API REST WoRMS (constante documentée par le service, pas configurable)."""


def _flatten_classification(node: dict) -> list[dict]:
    chain = []
    cur: dict | None = node
    while cur is not None:
        chain.append(cur)
        cur = cur.get("child")
    return chain


class WrmsModule(TaxonomyModule):
    meta = ModuleMeta(
        id="wrms", can_classify=True, can_render_external_link=True, domains="all", priority=996
    )

    def __init__(self, adapter: WrmsAdapter | None = None) -> None:
        self._adapter = adapter or WrmsAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        results = await self._adapter.records_by_name(struct.taxon.nom, marine_only=options.marine_only)
        if not results:
            return None
        cur = next((r for r in results if r.get("status") == "accepted"), None)
        if cur is None:
            if not options.suivre_synonymes:
                return None
            cur = results[0]
        return await self._process(struct, cur, is_classification, options, hop=0)

    async def _process(
        self, struct: Struct, cur: dict, is_classification: bool, options: GenerateOptions, hop: int
    ) -> Struct | None:
        adapter = self._adapter
        aphia_id = cur["AphiaID"]

        wrms_link: dict = {
            "id": aphia_id,
            "nom": cur["scientificname"],
            "rang": wrms_rang(cur["rank"]),
        }
        if cur.get("authority"):
            wrms_link["auteur"] = format_auteur(cur["authority"])
        if cur.get("isExtinct"):
            wrms_link["eteint"] = True
        if not is_classification and cur.get("kingdom"):
            # Signal de règne détecté sans appel réseau supplémentaire : "kingdom" est déjà
            # présent dans la réponse records_by_name utilisée ci-dessus. Voir RegneIncoherence.
            regne_detecte = wrms_charte(cur["kingdom"])
            if regne_detecte:
                wrms_link["regne_detecte"] = regne_detecte
        struct.liens["wrms"] = wrms_link

        is_synonym = cur.get("valid_AphiaID") is not None and cur["valid_AphiaID"] != aphia_id
        if is_synonym:
            if not is_classification:
                wrms_link["synonyme"] = True
                return struct
            if options.suivre_synonymes:
                if hop >= MAX_SYNONYM_HOPS:
                    return None
                accepted = await adapter.record_by_id(cur["valid_AphiaID"])
                if accepted is None:
                    return None
                struct.redirection = Redirection(nom=struct.taxon.nom)
                struct.taxon = TaxonInfo(nom=accepted["scientificname"])
                return await self._process(struct, accepted, is_classification, options, hop=hop + 1)
            # suivre_synonymes désactivé : on continue avec les données du synonyme tel quel

        if not is_classification:
            return struct

        if not cur.get("kingdom"):
            return None
        struct.regne = wrms_charte(cur["kingdom"])

        struct.taxon.nom = cur["scientificname"]
        struct.taxon.rang = wrms_rang(cur["rank"])
        struct.taxon.auteur = format_auteur(cur.get("authority"))
        if cur.get("isExtinct"):
            struct.taxon.eteint = True

        struct.classification = "WRMS"
        struct.classification_taxobox = "WoRMS"

        classification_tree = await adapter.classification_by_id(aphia_id)
        rangs: list[RankName] = []
        if classification_tree is not None:
            chain = _flatten_classification(classification_tree)
            for node in chain[:-1]:  # le dernier élément est le taxon lui-même
                rang_wp = wrms_rang(node.get("rank") or "")
                if rang_wp in RANGS_REGNE and struct.regne not in CHARTES_GARDENT_REGNE:
                    continue
                rangs.append(RankName(nom=node["scientificname"], rang=rang_wp))
            rangs.reverse()
        struct.rangs = rangs

        vernaculars = await adapter.vernaculars_by_id(aphia_id)
        vernaculaire = [v["vernacular"] for v in vernaculars if v.get("language") == "French"]
        if vernaculaire:
            struct.vernaculaire["WRMS"] = vernaculaire

        struct.originale = await adapter.original_description(aphia_id)

        original_id = cur.get("originalNameUsageID")
        if original_id and original_id != aphia_id:
            basio_record = await adapter.record_by_id(original_id)
            if basio_record is not None:
                struct.basionyme = Basionym(
                    nom=basio_record["scientificname"],
                    auteur=format_auteur(basio_record.get("authority")),
                    source="WRMS",
                )

        async def fetch_synonyms(offset: int) -> tuple[list[RankName], bool]:
            page = await adapter.synonyms_by_id(aphia_id, offset=offset)
            items = [
                RankName(nom=s["scientificname"], auteur=format_auteur(s.get("authority")), rang=wrms_rang(s["rank"]))
                for s in page
            ]
            return items, len(page) < PAGE_SIZE

        synonyms, _ = await collect_pages(fetch_synonyms, start_offset=1, limit=as_limit(options.limite_listes))
        if synonyms:
            struct.synonymes = SynonymList(liste=synonyms, source="WRMS")

        async def fetch_children(offset: int) -> tuple[list[RankName], bool]:
            page = await adapter.children_by_id(aphia_id, marine_only=options.marine_only, offset=offset)
            items = [
                RankName(
                    nom=c["scientificname"],
                    auteur=format_auteur(c.get("authority")),
                    rang=wrms_rang(c["rank"]),
                    eteint=bool(c.get("isExtinct")) or None,
                )
                for c in page
                if c.get("status") == "accepted"  # synonymes/incertain/nomen dubium exclus — filtre REST explicite
            ]
            return items, len(page) < PAGE_SIZE

        sous_taxons, _ = await collect_pages(fetch_children, start_offset=1, limit=as_limit(options.limite_listes))
        if sous_taxons:
            struct.sous_taxons = SubTaxonList(liste=sous_taxons, source="WRMS")

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("wrms")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        if struct.taxon.rang in ("espèce", "sous-espèce"):
            template = "WRMS espèce"
            nom = data["nom"]
        else:
            template = "WRMS"
            nom = wp_met_italiques(data["nom"], data.get("rang", struct.taxon.rang), struct.regne)
        eteint = "éteint=oui | " if data.get("eteint") else ""
        auteur = data.get("auteur", "")
        return f"{{{{{template} | {data['id']} | {nom} | {auteur} | {eteint}consulté le={cdate}}}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(
            struct, "wrms", "https://www.marinespecies.org/aphia.php?p=taxdetails&id={id}", "WRMS"
        )


register_module(WrmsModule)

"""Logique métier du module IRMNG : classification, synonymes, sous-taxons, noms vernaculaires,
via l'API REST (voir adapter.py). Architecture identique à `organon/modules/wrms/module.py` :
IRMNG tourne sur la même plateforme Aphia/VLIZ que WoRMS et expose une réponse de forme quasi
identique (mêmes champs `kingdom`, `authority`, `isExtinct`, `originalNameUsageID` pour le
basionyme, `valid_IRMNG_ID` pour le suivi de synonyme).

IRMNG est un généraliste "de secours" (couvre tous les règnes mais s'arrête souvent au genre) :
`ModuleMeta.priority` reste à sa valeur par défaut (0), en dessous de GBIF/ITIS/WoRMS/AlgaeBase
— cohérent avec son rôle de repli.

La « publication originale » (struct.originale) n'a aucun champ REST structuré équivalent : le
seul champ disponible est scrapé depuis la page HTML de détail
(`IrmngAdapter.original_description`, voir `organon.modules.common.
extract_aphia_original_description`) — la seule exception à "REST uniquement" dans ce module.

Le suffixe "non valide" d'un synonyme (`render_bioref`) ne cite pas le nom de la cible acceptée
— cette information n'est pas disponible côté IRMNG au moment du rendu."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Basionym, RankName, Redirection, Struct, SubTaxonList, SynonymList, TaxonInfo
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import MAX_SYNONYM_HOPS, as_limit, collect_pages, format_auteur, simple_debug_link
from organon.modules.irmng.adapter import IrmngAdapter
from organon.modules.irmng.ranks import CHARTES_GARDENT_REGNE, RANGS_REGNE, irmng_charte, irmng_rang

PAGE_SIZE = 50


def _flatten_classification(node: dict) -> list[dict]:
    chain = []
    cur: dict | None = node
    while cur is not None:
        chain.append(cur)
        cur = cur.get("child")
    return chain


class IrmngModule(TaxonomyModule):
    meta = ModuleMeta(id="irmng", can_classify=True, can_render_external_link=True, domains="all")

    def __init__(self, adapter: IrmngAdapter | None = None) -> None:
        self._adapter = adapter or IrmngAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        results = await self._adapter.records_by_name(struct.taxon.nom)
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
        irmng_id = cur["IRMNG_ID"]

        irmng_link: dict = {
            "id": irmng_id,
            "nom": cur["scientificname"],
            "rang": irmng_rang(cur["rank"]),
        }
        if cur.get("authority"):
            irmng_link["auteur"] = format_auteur(cur["authority"])
        if cur.get("isExtinct"):
            irmng_link["eteint"] = True
        struct.liens["irmng"] = irmng_link

        is_synonym = cur.get("valid_IRMNG_ID") is not None and cur["valid_IRMNG_ID"] != irmng_id
        if is_synonym:
            if not is_classification:
                irmng_link["synonyme"] = True
                return struct
            if options.suivre_synonymes:
                if hop >= MAX_SYNONYM_HOPS:
                    return None
                accepted = await adapter.record_by_id(cur["valid_IRMNG_ID"])
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
        struct.regne = irmng_charte(cur["kingdom"])

        struct.taxon.nom = cur["scientificname"]
        struct.taxon.rang = irmng_rang(cur["rank"])
        struct.taxon.auteur = format_auteur(cur.get("authority"))
        if cur.get("isExtinct"):
            struct.taxon.eteint = True

        struct.classification = "IRMNG"
        struct.classification_taxobox = "IRMNG"

        classification_tree = await adapter.classification_by_id(irmng_id)
        rangs: list[RankName] = []
        if classification_tree is not None:
            chain = _flatten_classification(classification_tree)
            for node in chain[:-1]:  # le dernier élément est le taxon lui-même
                rang_wp = irmng_rang(node.get("rank") or "")
                if rang_wp in RANGS_REGNE and struct.regne not in CHARTES_GARDENT_REGNE:
                    continue
                rangs.append(RankName(nom=node["scientificname"], rang=rang_wp))
            rangs.reverse()
        struct.rangs = rangs

        vernaculars = await adapter.vernaculars_by_id(irmng_id)
        vernaculaire = [v["vernacular"] for v in vernaculars if v.get("language") == "French"]
        if vernaculaire:
            struct.vernaculaire["IRMNG"] = vernaculaire

        struct.originale = await adapter.original_description(irmng_id)

        original_id = cur.get("originalNameUsageID")
        if original_id and original_id != irmng_id:
            basio_record = await adapter.record_by_id(original_id)
            if basio_record is not None:
                struct.basionyme = Basionym(
                    nom=basio_record["scientificname"],
                    auteur=format_auteur(basio_record.get("authority")),
                    source="IRMNG",
                )

        async def fetch_synonyms(offset: int) -> tuple[list[RankName], bool]:
            page = await adapter.synonyms_by_id(irmng_id, offset=offset)
            items = [
                RankName(nom=s["scientificname"], auteur=format_auteur(s.get("authority")), rang=irmng_rang(s["rank"]))
                for s in page
            ]
            return items, len(page) < PAGE_SIZE

        synonyms, _ = await collect_pages(fetch_synonyms, start_offset=1, limit=as_limit(options.limite_listes))
        if synonyms:
            struct.synonymes = SynonymList(liste=synonyms, source="IRMNG")

        async def fetch_children(offset: int) -> tuple[list[RankName], bool]:
            page = await adapter.children_by_id(irmng_id, offset=offset)
            items = [
                RankName(
                    nom=c["scientificname"],
                    auteur=format_auteur(c.get("authority")),
                    rang=irmng_rang(c["rank"]),
                    eteint=bool(c.get("isExtinct")) or None,
                )
                for c in page
                if c.get("status") == "accepted"  # synonymes/incertain/nomen dubium exclus — filtre REST explicite
            ]
            return items, len(page) < PAGE_SIZE

        sous_taxons, _ = await collect_pages(fetch_children, start_offset=1, limit=as_limit(options.limite_listes))
        if sous_taxons:
            struct.sous_taxons = SubTaxonList(liste=sous_taxons, source="IRMNG")

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("irmng")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], data.get("rang", struct.taxon.rang), struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]
        eteint = "† " if data.get("eteint") else ""
        post = ""
        if data.get("synonyme"):
            post = " <small>(non valide)</small>"
        return f"{{{{IRMNG | {data['id']} | {eteint}{cible} | consulté le={cdate} }}}}{post}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(
            struct, "irmng", "https://www.irmng.org/aphia.php?p=taxdetails&id={id}", "IRMNG"
        )


register_module(IrmngModule)

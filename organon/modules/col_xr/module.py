"""Logique métier du module Catalogue of Life Extended Release (ChecklistBank, dataset 3LXR) :
classification complète, synonymes, sous-taxons, noms vernaculaires — source de classification
à part entière (`can_classify=True`), sélectionnable au même titre que GBIF/ITIS/WoRMS via la
facette de classification du frontend plutôt que fusionnée automatiquement avec le backbone GBIF
legacy : la XR sert de taxonomie par défaut à l'interface de GBIF depuis 2024, mais l'API GBIF
utilisée par `organon.modules.gbif.module` (species/parents, /children, /synonyms) continue
d'exposer le backbone legacy — les deux référentiels peuvent diverger, comparer les facettes
proposées revient à l'utilisateur (voir `organon.modules.gbif.lookup.find_col_xr_id`, qui ne
fait que résoudre l'identifiant ChecklistBank pour le lien externe {{CatalogueofLife}} du module
GBIF, sans toucher à sa classification).

Ne fait aucun appel HTTP directement, voir adapter.py."""

from __future__ import annotations

import html as _html

from organon.core.config import GenerateOptions
from organon.core.domains import KINGDOM_MAP
from organon.core.models import (
    RankName,
    Redirection,
    Struct,
    SubTaxonList,
    SynonymList,
    TaxonInfo,
)
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.col_xr.adapter import ColXrAdapter
from organon.modules.col_xr.ranks import col_xr_cherche_rang
from organon.modules.common import (
    MAX_SYNONYM_HOPS,
    as_limit,
    collect_pages,
    format_auteur,
    simple_debug_link,
)


def _kingdom_index(classification: list[dict]) -> int | None:
    return next((i for i, c in enumerate(classification) if c.get("rank") == "kingdom"), None)


class ColXrModule(TaxonomyModule):
    meta = ModuleMeta(
        id="col_xr",
        can_classify=True,
        can_render_external_link=True,
        domains="all",
        priority=200,
    )

    def __init__(self, adapter: ColXrAdapter | None = None) -> None:
        self._adapter = adapter or ColXrAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        return await self._collect(struct, is_classification, options, hop=0)

    async def _collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions, hop: int
    ) -> Struct | None:
        adapter = self._adapter

        results = await adapter.search(struct.taxon.nom)
        if not results:
            return None

        # `type=EXACT` côté ChecklistBank ne suffit pas à exclure tous les à-peu-près (plusieurs
        # centaines de résultats observés en pratique pour un binôme exact) : filtre client
        # strict sur le nom, comme organon.modules.col.module déjà en place pour la COL classique.
        exact = [r for r in results if r["usage"]["name"]["scientificName"] == struct.taxon.nom]
        candidats = exact or results

        def _regne_correspond(r: dict) -> bool:
            if struct.domaine in ("*", ""):
                return True
            idx = _kingdom_index(r.get("classification", []))
            kingdom = r["classification"][idx]["name"] if idx is not None else ""
            return KINGDOM_MAP.get(kingdom, "") == struct.domaine

        accepted = [r for r in candidats if r["usage"]["status"] == "accepted"]
        cur = next((r for r in accepted if _regne_correspond(r)), None)
        if cur is None:
            cur = accepted[0] if accepted else None
        if cur is None:
            if not options.suivre_synonymes:
                return None
            cur = next((r for r in candidats if _regne_correspond(r)), candidats[0])

        usage = cur["usage"]
        name = usage["name"]
        taxon_id = cur["id"]

        struct.liens["col_xr"] = {
            "id": taxon_id,
            "nom": name["scientificName"],
            "auteur": format_auteur(name.get("authorship")),
            "rang": col_xr_cherche_rang(name["rank"]),
            **({"eteint": usage["extinct"]} if "extinct" in usage else {}),
        }

        is_synonym = usage["status"] == "synonym"
        if is_synonym:
            if not is_classification:
                struct.liens["col_xr"]["synonyme"] = True
                return struct
            if options.suivre_synonymes:
                if hop >= MAX_SYNONYM_HOPS:
                    return None
                accepted_target = usage.get("accepted")
                if accepted_target is None:
                    return None
                struct.redirection = Redirection(nom=struct.taxon.nom)
                struct.taxon = TaxonInfo(nom=accepted_target["name"]["scientificName"])
                return await self._collect(struct, is_classification, options, hop=hop + 1)
            # suivre_synonymes désactivé : la classification se construit directement à partir
            # de ce synonyme plutôt que du taxon accepté.

        if not is_classification:
            return struct

        struct.taxon.auteur = format_auteur(name.get("authorship"))
        struct.taxon.rang = col_xr_cherche_rang(name["rank"])
        if "extinct" in usage:
            struct.taxon.eteint = usage["extinct"]
        struct.taxon.nom = name["scientificName"].strip()
        struct.classification = "COL XR"
        struct.classification_taxobox = "COL XR"

        classification = cur.get("classification", [])
        idx = _kingdom_index(classification)
        if idx is None:
            return None
        struct.regne = KINGDOM_MAP.get(classification[idx]["name"], "")
        if not struct.regne:
            return None

        # `classification` va de la racine (domaine) à l'ancêtre direct, règne compris : on
        # exclut tout ce qui est au règne ou au-dessus (même logique que WRMS/IRMNG, voir
        # `filter_ancestors_above_regne`) puis on inverse pour l'ordre "du plus proche au plus
        # éloigné" attendu par `struct.rangs`.
        struct.rangs = [
            RankName(
                nom=c["name"],
                rang=col_xr_cherche_rang(c["rank"]),
                auteur=format_auteur(c.get("authorship")),
            )
            for c in reversed(classification[idx + 1 :])
        ]

        async def fetch_children(offset: int) -> tuple[list[RankName], bool]:
            page = await adapter.children_page(taxon_id, offset)
            out = []
            for c in page.get("result", []):
                if c.get("rank") == "unranked" or c.get("status") != "accepted":
                    continue
                out.append(
                    RankName(
                        nom=c["name"],
                        rang=col_xr_cherche_rang(c["rank"]),
                        auteur=format_auteur(c.get("authorship")),
                        # ChecklistBank signale l'extinction par un "†" en tête du libellé HTML,
                        # pas par un champ structuré sur cet endpoint (contrairement à /taxon/{id}).
                        eteint=c.get("labelHtml", "").startswith("†") or None,
                    )
                )
            return out, page.get("last", True)

        liste, coupe = await collect_pages(fetch_children, limit=as_limit(options.limite_listes))
        if liste:
            struct.sous_taxons = SubTaxonList(liste=liste, source="COL XR", coupe=coupe)

        vernaculaire = [
            _html.unescape(v["name"])
            for v in cur.get("vernacularNames", [])
            if v.get("language") == "fra"
        ]
        if vernaculaire:
            struct.vernaculaire["COL XR"] = vernaculaire

        syn = await adapter.synonyms(taxon_id)
        synonymes = []
        for entry in [*syn.get("homotypic", []), *syn.get("heterotypic", [])]:
            sname = entry.get("name") or {}
            if not sname.get("scientificName"):
                continue
            synonymes.append(
                RankName(
                    nom=sname["scientificName"],
                    auteur=format_auteur(sname.get("authorship")),
                    rang=col_xr_cherche_rang(sname.get("rank", "")),
                )
            )
        if synonymes:
            struct.synonymes = SynonymList(liste=synonymes, source="COL XR", coupe=False)

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("col_xr")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], data.get("rang") or struct.taxon.rang, struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]
        sup = " | éteint=oui" if data.get("eteint") else ""
        nv = " | nv" if data.get("synonyme") else ""
        return f"{{{{CatalogueofLife | {data['id']} | {cible}{sup}{nv} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(
            struct, "col_xr", "https://www.catalogueoflife.org/data/taxon/{id}", "COL XR"
        )


register_module(ColXrModule)

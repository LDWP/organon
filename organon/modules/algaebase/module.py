"""Logique métier du module AlgaeBase : classification, sous-taxons, étymologie, publication
originale. Ne fait aucun appel HTTP directement, voir adapter.py.

Trois formes de recherche selon le nombre de "mots" du taxon demandé : espèce (>=2 mots), puis
genre, avec repli sur "rang supérieur" si la recherche de genre échoue.

Particularité de l'API : certains endpoints de détail renvoient parfois la chaîne JSON
`"Nothing Found"` plutôt qu'un objet vide en cas d'absence de données pour un id donné (ex.
`/genus/{id}/detail` sur un id sans page de détail) — d'où les vérifications
`isinstance(..., dict)` avant tout `.get()` sur ces réponses ci-dessous.
"""

from __future__ import annotations

import re

from organon.core.config import GenerateOptions
from organon.core.models import Etymology, RankName, Struct, SubTaxonList, TaxonInfo
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.algaebase.adapter import AlgaeBaseAdapter
from organon.modules.algaebase.ranks import algaebase_charte, algaebase_cherche_rang
from organon.modules.common import format_auteur, simple_debug_link

PAGE_SIZE = 50


def _format_auteur_year(found: dict) -> str:
    auteur = found.get("dwc:scientificNameAuthorship") or ""
    year = found.get("dwc:namePublishedInYear")
    if year:
        auteur = f"{auteur}, {year}" if auteur else str(year)
    return auteur


def _base_blob(found: dict, taxon_name: str, id_field: str) -> dict:
    blob: dict = {
        "rang": algaebase_cherche_rang(found.get("dwc:taxonRank", "")),
        "nom": taxon_name,
        "id": found.get(id_field),
    }
    auteur = _format_auteur_year(found)
    if auteur:
        blob["auteur"] = format_auteur(auteur)
    if found.get("isFossil") == "Y" or found.get("dwc:isFossil") == "Y":
        blob["eteint"] = True
    return blob


def _blob_to_taxon(blob: dict) -> TaxonInfo:
    return TaxonInfo(
        nom=blob["nom"], rang=blob.get("rang"), auteur=blob.get("auteur"), eteint=blob.get("eteint")
    )


def _to_rankname(entry: dict) -> RankName:
    return RankName(
        nom=entry["nom"], rang=entry.get("rang"), auteur=entry.get("auteur"), eteint=entry.get("eteint")
    )


def _extract_classification(items: list[dict]) -> tuple[list[dict], str, str]:
    """N'identifie pas elle-même l'entrée "genre" de la classification : l'appelant (branche
    genre de `collect()`) la retrouve via une boucle séparée sur le résultat, voir
    `_collect_genus`."""
    out: list[dict] = []
    phylum = ""
    kingdom = ""
    for cl in items:
        raw_rank = cl.get("dwc:taxonRank") or ""
        if raw_rank.lower() == "empire":
            continue
        if raw_rank.lower() == "kingdom":
            kingdom = cl.get("dwc:scientificName") or ""
        if raw_rank.lower() == "phylum":
            phylum = cl.get("dwc:scientificName") or ""
        auteur = _format_auteur_year(cl).replace("& al.", "et al.")
        out.append(
            {
                "rang": algaebase_cherche_rang(raw_rank),
                "id": cl.get("dwc:taxonID"),
                "nom": (cl.get("dwc:scientificName") or "").strip(),
                "auteur": format_auteur(auteur) if auteur else None,
            }
        )
    return out, phylum, kingdom


def _apply_etymology(struct: Struct, found: dict) -> None:
    origin = found.get("nameOrigin")
    if origin:
        texte = re.sub(r"[.]\s*$", "", origin)
        struct.etymologie = Etymology(texte=f"''{texte}''", source="AlgaeBASE")


def _apply_bibliographic_citation(struct: Struct, found: dict) -> None:
    citation = found.get("dcterms:bibliographicCitation")
    if not citation:
        return
    text = citation.replace("<i>", "''").replace("</i>", "''")
    pdfs = found.get("pdfs") or []
    if pdfs and pdfs[0].get("pdf_url"):
        text += f" ([{pdfs[0]['pdf_url']} PDF])"
    struct.originale = text


def _apply_detail_page(struct: Struct, details: dict) -> None:
    desc = details.get("description")
    if desc:
        bucket = struct.liens.setdefault("description", {}).setdefault("AlgaeBASE", [])
        bucket.append(f"''{desc}''")
    pub = details.get("originalPublicationRef")
    if pub:
        struct.originale = pub.replace("<i>", "''").replace("</i>", "''")


async def _find_species(adapter: AlgaeBaseAdapter, key: str, taxon: str) -> dict | None:
    offset = 0
    while True:
        res = await adapter.search_species_page(key, taxon, offset)
        if res is None:
            return None
        results = res.get("result")
        pagination = res.get("_pagination") or {}
        total = pagination.get("_total_number_of_results")
        if results is None or total is None:
            return None
        for r in results:
            nom = r.get("dwc:scientificName") or ""
            authorship = r.get("dwc:scientificNameAuthorship") or ""
            if authorship:
                nom = nom.replace(f" {authorship}", "")
            if nom == taxon:
                return r
        offset += PAGE_SIZE
        if offset >= total:
            return None


async def _collect_species(
    adapter: AlgaeBaseAdapter, key: str, struct: Struct, is_classification: bool, options: GenerateOptions
) -> Struct | None:
    taxon = struct.taxon.nom
    found = await _find_species(adapter, key, taxon)
    if found is None:
        return None

    detail_resp = await adapter.species_detail(key, found.get("dwc:acceptedNameUsageID"))
    if detail_resp and detail_resp.get("details"):
        found = detail_resp["details"]

    blob = _base_blob(found, taxon, id_field="dwc:acceptedNameUsageID")
    struct.liens["algaebase"] = blob

    if not is_classification:
        return struct

    genus_id = found.get("genusID")

    struct.taxon = _blob_to_taxon(blob)
    struct.classification = "AlgaeBASE"
    struct.classification_taxobox = "AlgaeBASE"

    _apply_bibliographic_citation(struct, found)
    _apply_etymology(struct, found)

    tbl: list[str] = []
    if found.get("dwc:isMarine"):
        tbl.append("Cette espèce est marine")
    if found.get("dwc:isFreshwater"):
        tbl.append("Cette espèce vit en eau douce")
    if found.get("dwc:isTerrestrial"):
        tbl.append("Cette espèce est terrestre")
    if tbl:
        struct.liens.setdefault("description", {})["AlgaeBASE"] = tbl

    if genus_id is None:
        return struct

    genus_detail = await adapter.genus_detail(key, genus_id)
    if genus_detail is None or "classification" not in genus_detail:
        return None
    rank_tbl, phylum, kingdom = _extract_classification(genus_detail["classification"])
    struct.rangs = [_to_rankname(r) for r in reversed(rank_tbl)]

    struct.regne = algaebase_charte(phylum, kingdom)
    if struct.regne != "algue":
        struct.cacher_regne = True

    page_detail = await adapter.taxonomy_page_detail(key, blob["id"])
    if isinstance(page_detail, dict):
        _apply_detail_page(struct, page_detail.get("details") or {})

    return struct


async def _collect_genus(
    adapter: AlgaeBaseAdapter, key: str, struct: Struct, is_classification: bool, options: GenerateOptions
) -> Struct | None:
    taxon = struct.taxon.nom
    res = await adapter.search_genus(key, taxon)
    if res is None:
        return None
    results = res.get("result")
    pagination = res.get("_pagination") or {}
    if results is None or "_total_number_of_results" not in pagination:
        return None

    found = None
    for r in results:
        if r.get("dwc:taxonRank") != "genus":
            continue
        name = r.get("dwc:scientificName")
        if not name:
            continue
        if name.split(" ")[0] != taxon:
            continue
        found = r
        break
    if found is None:
        return None

    blob = _base_blob(found, taxon, id_field="dwc:acceptedNameUsageID")
    struct.liens["algaebase"] = blob

    if not is_classification:
        return struct

    taxon_id = found.get("dwc:acceptedNameUsageID")

    struct.taxon = _blob_to_taxon(blob)
    struct.classification = "AlgaeBASE"
    struct.classification_taxobox = "AlgaeBASE"

    _apply_etymology(struct, found)
    _apply_bibliographic_citation(struct, found)

    detail = await adapter.genus_detail(key, taxon_id)
    if detail is None or "classification" not in detail:
        return None
    rank_tbl, phylum, kingdom = _extract_classification(detail["classification"])

    c_id = None
    filtered: list[dict] = []
    for cont in reversed(rank_tbl):
        if cont["rang"] == "genre":
            c_id = cont["id"]
            continue
        filtered.append(cont)
    struct.rangs = [_to_rankname(r) for r in filtered]

    sub_detail = await adapter.taxonomy_detail(key, c_id) if c_id is not None else None
    lower = sub_detail.get("lowerTaxa") if isinstance(sub_detail, dict) else None
    if lower:
        sub_tbl, _, _ = _extract_classification(lower)
        if sub_tbl:
            struct.sous_taxons = SubTaxonList(liste=[_to_rankname(r) for r in sub_tbl], source="AlgaeBASE")

    struct.regne = algaebase_charte(phylum, kingdom)
    if struct.regne != "algue":
        struct.cacher_regne = True

    page_detail = await adapter.taxonomy_page_detail(key, taxon_id)
    if isinstance(page_detail, dict):
        _apply_detail_page(struct, page_detail.get("details") or {})

    return struct


async def _collect_superior(
    adapter: AlgaeBaseAdapter, key: str, struct: Struct, is_classification: bool, options: GenerateOptions
) -> Struct | None:
    taxon = struct.taxon.nom
    res = await adapter.search_taxonomy(key, taxon)
    if res is None:
        return None
    results = res.get("result")
    pagination = res.get("_pagination") or {}
    if results is None or "_total_number_of_results" not in pagination:
        return None

    found = None
    for r in results:
        if r.get("dwc:scientificName") == taxon:
            found = r
            break
    if found is None:
        return None

    blob = _base_blob(found, taxon, id_field="dwc:taxonID")
    struct.liens["algaebase"] = blob

    if not is_classification:
        return struct

    taxon_id = found.get("dwc:taxonID")

    struct.taxon = _blob_to_taxon(blob)
    struct.classification = "AlgaeBASE"
    struct.classification_taxobox = "AlgaeBASE"

    _apply_etymology(struct, found)
    _apply_bibliographic_citation(struct, found)

    detail = await adapter.taxonomy_detail(key, taxon_id)
    if detail is None or "higherTaxa" not in detail:
        return None
    higher_tbl, phylum, kingdom = _extract_classification(detail["higherTaxa"])
    struct.rangs = [
        _to_rankname(r) for r in reversed(higher_tbl) if r["rang"] != struct.taxon.rang
    ]

    lower = detail.get("lowerTaxa")
    if lower:
        sub_tbl, _, _ = _extract_classification(lower)
        if sub_tbl:
            struct.sous_taxons = SubTaxonList(liste=[_to_rankname(r) for r in sub_tbl], source="AlgaeBASE")

    struct.regne = algaebase_charte(phylum, kingdom)
    if struct.regne != "algue":
        struct.cacher_regne = True

    page_detail = await adapter.taxonomy_page_detail(key, taxon_id)
    if isinstance(page_detail, dict):
        _apply_detail_page(struct, page_detail.get("details") or {})

    return struct


_ESPECE_RANGS = {"espèce", "sous-espèce", "forme", "variété", "pathovar", "cultivar"}
_GENRE_RANGS = {"genre", "sous-genre"}


class AlgaeBaseModule(TaxonomyModule):
    meta = ModuleMeta(
        id="algaebase",
        can_classify=True,
        can_render_external_link=True,
        domains=["champignon", "algue", "végétal", "archaea", "bactérie", "protiste"],
        priority=990,
    )

    def __init__(self, adapter: AlgaeBaseAdapter | None = None) -> None:
        self._adapter = adapter or AlgaeBaseAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        adapter = self._adapter
        key = await adapter.fetch_key()
        if key is None:
            return None

        taxon = struct.taxon.nom
        if len(taxon.split(" ")) >= 2:
            return await _collect_species(adapter, key, struct, is_classification, options)

        result = await _collect_genus(adapter, key, struct, is_classification, options)
        if result is not None:
            return result
        return await _collect_superior(adapter, key, struct, is_classification, options)

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("algaebase")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        rang = data.get("rang") or struct.taxon.rang
        nom = wp_met_italiques(data["nom"], rang, struct.regne)
        if data.get("auteur"):
            nom += " " + data["auteur"]
        eteint = " éteint=oui |" if data.get("eteint") else ""
        if rang in _ESPECE_RANGS:
            type_, sup = " espèce", ""
        elif rang in _GENRE_RANGS:
            type_, sup = " genre", ""
        else:
            type_, sup = "", f" {rang} |"
        return f"{{{{AlgaeBASE{type_} | {data['id']} | {nom} |{sup}{eteint} consulté le={cdate}}}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(
            struct,
            "algaebase",
            "https://www.algaebase.org/search/species/detail/?species_id={id}",
            "AlgaeBase",
        )


register_module(AlgaeBaseModule)

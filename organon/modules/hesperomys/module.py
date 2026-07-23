"""Logique métier du module Hesperomys (https://hesperomys.com, taxonomie mammalienne,
classification + synonymes). Ne fait aucun appel HTTP directement, voir adapter.py.

Pas de suivi de synonyme (contrairement à GBIF/ITIS/POWO) : `taxonByLabel` ne résout que les
taxons valides, aucun mécanisme "ce nom est un synonyme, voici le taxon accepté" n'est exposé
par l'API pour ce point d'entrée (voir docstring adapter.py) — un nom de synonyme donné en
entrée renvoie simplement `None`, comme un nom absent de la base.

Domaine restreint à `["mammifère"]` (site spécialisé) : `class_.validName` (ou le nom du taxon
lui-même s'il s'agit de la classe) doit valoir "Mammalia" en mode classification, sinon
abandon — même garde-fou que POWO_KINGDOM_MAP à une seule entrée (`organon.modules.powo.ranks`)
pour un module à domaine unique."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct, SynonymList
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.modules.common import as_limit, format_auteur, simple_debug_link
from organon.modules.hesperomys.adapter import HesperomysAdapter
from organon.modules.hesperomys.ranks import hesperomys_cherche_rang

_AGE_EXTANT = "extant"
_AGE_INVALID = {"removed", "redirect"}


def _author_string(author_tags: list[dict] | None) -> str | None:
    noms = [
        t["person"]["familyName"]
        for t in (author_tags or [])
        if t.get("__typename") == "Author" and t.get("person", {}).get("familyName")
    ]
    if not noms:
        return None
    if len(noms) > 3:
        return f"{noms[0]} et al."
    if len(noms) == 1:
        return noms[0]
    return ", ".join(noms[:-1]) + " & " + noms[-1]


def _year(value: str | None) -> str | None:
    """`year` est renvoyé tantôt en date ISO complète (`"1758-01-01"`), tantôt en année seule
    (`"1829"`, observé sur les taxons de rang supérieur à l'espèce) : seule l'année sert à la
    citation d'auteur, `split("-")` couvre les deux formats."""
    if not value:
        return None
    return value.split("-", 1)[0]


def _citation(base_name: dict | None) -> str | None:
    """Combine auteur(s) + année d'un `baseName` en une citation unique (ex. "Linnaeus,
    1758"), format attendu par struct.taxon.auteur/RankName.auteur (voir les autres modules,
    qui reçoivent déjà ce format préconstruit de leur source)."""
    if not base_name:
        return None
    auteur = _author_string(base_name.get("authorTags"))
    annee = _year(base_name.get("year"))
    if auteur and annee:
        return format_auteur(f"{auteur}, {annee}")
    return format_auteur(auteur or annee)


def _eteint(age: str | None) -> bool | None:
    if not age:
        return None
    return age != _AGE_EXTANT


class HesperomysModule(TaxonomyModule):
    meta = ModuleMeta(
        id="hesperomys", can_classify=True, can_render_external_link=False, domains=["mammifère"]
    )

    def __init__(self, adapter: HesperomysAdapter | None = None) -> None:
        self._adapter = adapter or HesperomysAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        adapter = self._adapter
        nom = struct.taxon.nom

        results = await adapter.taxon_by_label(nom)
        exact = [r for r in results if r.get("validName") == nom]
        if not exact:
            return None
        match = exact[0]

        detail = await adapter.taxon_detail(match["oid"])
        if detail is None:
            return None

        age = detail.get("age")
        if age in _AGE_INVALID:
            return None

        rang = hesperomys_cherche_rang(detail.get("rank"))
        entry: dict = {"id": detail["oid"], "nom": detail["validName"]}
        citation = _citation(detail.get("baseName"))
        if citation:
            entry["auteur"] = citation
        if rang:
            entry["rang"] = rang
        eteint = _eteint(age)
        if eteint is not None:
            entry["eteint"] = eteint
        struct.liens["hesperomys"] = entry

        if not is_classification:
            return struct

        class_ = detail.get("class_") or {}
        est_mammifere = (
            class_.get("validName") == "Mammalia" or detail.get("validName") == "Mammalia"
        )
        if not est_mammifere:
            return None

        struct.taxon.rang = rang
        struct.taxon.auteur = citation
        if eteint is not None:
            struct.taxon.eteint = eteint
        struct.regne = "animal"
        struct.classification = "Hesperomys"
        struct.classification_taxobox = "Hesperomys"

        ancestors = await adapter.ancestors(detail.get("parent"))
        struct.rangs = [
            RankName(
                nom=a["validName"],
                rang=hesperomys_cherche_rang(a.get("rank")),
                auteur=_citation(a.get("baseName")),
            )
            for a in ancestors
        ]

        limit = as_limit(options.limite_listes)
        synonymes_liste = [
            RankName(
                nom=n.get("correctedOriginalName") or n.get("originalName") or n.get("rootName"),
                auteur=_citation(n),
                rang=hesperomys_cherche_rang(n.get("originalRank")),
            )
            for n in (e["node"] for e in detail.get("names", {}).get("edges", []))
            if n.get("status") != "valid"
            and (n.get("correctedOriginalName") or n.get("originalName") or n.get("rootName"))
        ]
        coupe = False
        if limit is not None and len(synonymes_liste) > limit:
            synonymes_liste = synonymes_liste[:limit]
            coupe = True
        if synonymes_liste:
            struct.synonymes = SynonymList(liste=synonymes_liste, source="Hesperomys", coupe=coupe)

        return struct

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(
            struct, "hesperomys", "https://hesperomys.com/t/{id}", "Hesperomys"
        )


register_module(HesperomysModule)

"""Logique métier du module FishBase : classification des poissons via ChecklistBank dataset
`1010` (alias « WoRMS FishBase ») — voir `adapter.py`. Domaine restreint à `["poisson"]`
(sous-domaine réel de l'arbre Organon, `organon.core.domains`, contrairement à Bryonames/AlgaeBase
qui n'en ont pas). Le règne n'est jamais déduit de `classification` : la chaîne ne porte aucun
rang `kingdom` (elle démarre à `parvphylum`, vérifié en direct sur des poissons osseux) —
`struct.regne` est donc fixé à `"animal"` en dur une fois un candidat validé, même principe que
`reptile_database`.

Comme Bryonames (même plateforme, éditeur unique — ici le consortium FishBase/FIN), pas de
désambiguïsation multi-candidats nécessaire : le premier candidat "accepted" retourné par
`type=EXACT` suffit.

Rendu Bioref dépendant du rang, à la manière de `organon.modules.reptile_database.module` :
depuis le 2025-05-01, cet export ChecklistBank est généré depuis la plateforme Aphia/VLIZ
(vérifié en direct sur la fiche dataset `1010` — bascule mentionnée explicitement dans sa
description) et ne porte donc plus les codes numériques natifs FishBase (SpecCode/FamCode), reste
uniquement l'identifiant LSID WoRMS. Or `{{FishBase espèce}}`/`{{FishBase famille}}` exigent
justement ce code numérique en premier paramètre positionnel (`codeFishbase`, vérifié en direct
dans le code du modèle : aucun mode de repli par nom) — impossible à fournir sans le deviner.
`{{FishBase genre}}`/`{{FishBase ordre}}` en revanche ne demandent que le nom (le premier
n'affiche même plus de fiche genre dédiée depuis 2008, seulement une recherche par nom) : utilisés
directement pour ces deux rangs. Pour tout le reste (espèce, famille, et rangs intermédiaires),
repli sur `{{Lien web}}` pointant vers la fiche WoRMS d'origine (`name.link`, toujours présent en
pratique) — même pattern que Bryonames vers Tropicos."""

from __future__ import annotations

from organon.core.config import GenerateOptions
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
from organon.modules.common import MAX_SYNONYM_HOPS, as_limit, collect_pages, format_auteur
from organon.modules.fishbase.adapter import FishbaseAdapter
from organon.modules.fishbase.ranks import fishbase_cherche_rang


class FishbaseModule(TaxonomyModule):
    meta = ModuleMeta(
        id="fishbase",
        can_classify=True,
        can_render_external_link=True,
        domains=["poisson"],
    )

    def __init__(self, adapter: FishbaseAdapter | None = None) -> None:
        self._adapter = adapter or FishbaseAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        return await self._collect(struct, is_classification, options, hop=0)

    async def _collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions, hop: int
    ) -> Struct | None:
        adapter = self._adapter

        candidats = await adapter.search(struct.taxon.nom)
        if not candidats:
            return None

        accepted = [r for r in candidats if r["usage"]["status"] == "accepted"]
        cur = accepted[0] if accepted else None
        if cur is None:
            if not options.suivre_synonymes:
                return None
            cur = candidats[0]

        usage = cur["usage"]
        name = usage["name"]
        taxon_id = cur["id"]
        rang = fishbase_cherche_rang(name["rank"])

        struct.liens["fishbase"] = {
            "id": taxon_id,
            "nom": name["scientificName"],
            "auteur": format_auteur(name.get("authorship")),
            "rang": rang,
            "link": name.get("link"),
            **({"eteint": usage["extinct"]} if "extinct" in usage else {}),
        }

        is_synonym = usage["status"] == "synonym"
        struct.liens["fishbase"]["statut_detecte"] = "synonyme" if is_synonym else "accepté"
        if is_synonym:
            if not is_classification:
                struct.liens["fishbase"]["synonyme"] = True
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

        if not is_classification:
            return struct

        struct.taxon.auteur = format_auteur(name.get("authorship"))
        struct.taxon.rang = rang
        if "extinct" in usage:
            struct.taxon.eteint = usage["extinct"]
        struct.taxon.nom = name["scientificName"].strip()
        struct.classification = "FishBase"
        struct.classification_taxobox = "FishBase"
        struct.regne = "animal"

        classification = cur.get("classification", [])
        struct.rangs = [
            RankName(
                nom=c["name"],
                rang=fishbase_cherche_rang(c["rank"]),
                auteur=format_auteur(c.get("authorship")),
            )
            for c in reversed(classification)
            if c.get("id") != taxon_id
        ]

        async def fetch_children(offset: int) -> tuple[list[RankName], int, bool]:
            page = await adapter.children_page(taxon_id, offset)
            raw = page.get("result", [])
            out = []
            for c in raw:
                if c.get("rank") == "unranked" or c.get("status") != "accepted":
                    continue
                out.append(
                    RankName(
                        nom=c["name"],
                        rang=fishbase_cherche_rang(c["rank"]),
                        auteur=format_auteur(c.get("authorship")),
                        eteint=c.get("labelHtml", "").startswith("†") or None,
                    )
                )
            return out, len(raw), page.get("last", True)

        liste, coupe = await collect_pages(fetch_children, limit=as_limit(options.limite_listes))
        if liste:
            struct.sous_taxons = SubTaxonList(liste=liste, source="FishBase", coupe=coupe)

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
                    rang=fishbase_cherche_rang(sname.get("rank", "")),
                )
            )
        if synonymes:
            struct.synonymes = SynonymList(liste=synonymes, source="FishBase", coupe=False)

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("fishbase")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        rang = data.get("rang") or struct.taxon.rang
        post = " <small>(non valide)</small>" if data.get("synonyme") else ""

        if rang == "genre":
            return f"{{{{FishBase genre | {data['nom']} | consulté le={cdate} }}}}{post}"
        if rang == "ordre":
            desc = f" | {data['auteur']}" if data.get("auteur") else ""
            return f"{{{{FishBase ordre | {data['nom']}{desc} | consulté le={cdate} }}}}{post}"

        # Espèce/famille (et rangs intermédiaires) : pas de code FishBase numérique disponible
        # depuis la bascule Aphia/WoRMS de la source (voir docstring de tête) — repli générique.
        cible = wp_met_italiques(data["nom"], rang, struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]
        url = data.get("link") or f"https://www.checklistbank.org/dataset/1010/taxon/{data['id']}"
        return (
            f"{{{{Lien web | langue=en | titre={cible} | url={url} "
            f"| site=FishBase | consulté le={cdate} }}}}{post}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("fishbase")
        if not data or "id" not in data:
            return None
        url = data.get("link") or f"https://www.checklistbank.org/dataset/1010/taxon/{data['id']}"
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>FishBase</a>"


register_module(FishbaseModule)

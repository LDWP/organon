"""Logique métier du module Checklist of the Collembola of the World (CCW) : classification des
collemboles (classe Collembola) via ChecklistBank dataset 2130 — voir `adapter.py`. Domaine
restreint à `["animal"]` (pas de sous-domaine "collembole" dans l'arbre de domaines Organon,
comme Bryonames/GRIN pour leur propre périmètre) : un taxon hors Collembola n'y figure simplement
pas, `collect` renvoie alors None sans qu'aucune restriction explicite ne soit nécessaire ici.

Comme `organon.modules.bryonames.module` (même plateforme ChecklistBank, dataset mono-source
curaté par une seule équipe éditoriale), pas de désambiguïsation multi-candidats nécessaire
(`select_col_xr_candidate`/`_code_incoherent` de `col_xr`) — le premier candidat "accepted"
retourné par `type=EXACT` suffit.

Le règne n'est jamais déduit de `classification` : la chaîne ne porte aucun rang au-dessus de
"class" (le dataset entier ne couvre que la classe Collembola, vérifié en direct — `GET
.../dataset/2130/tree` renvoie Collembola comme unique racine) — `struct.regne` est donc fixé à
"animal" en dur, et la chaîne sous-embranchement/embranchement (Hexapoda/Arthropoda) injectée
au-dessus de la classe, même principe que `organon.modules.wco.module._CHAINE_FIXE` (à la
différence que WCO plafonne à l'ordre, un rang plus bas).

Aucun modèle `{{Bioref}}` dédié n'existe sur Wikipédia en français pour CCW (vérifié en direct,
0 résultat dans l'espace de noms Modèle) : `render_bioref` utilise le modèle générique
`{{Lien web}}`, comme Bryonames/WCO. Comme Bryonames, l'API fournit un champ `usage.link` vers
la page famille/sous-famille d'origine sur collembola.org (pas de fiche par taxon individuel sur
ce site, contrairement à Tropicos pour Bryonames — le lien pointe vers la page du groupe
englobant, partagée par plusieurs taxons voisins, vérifié en direct) : `render_bioref`/
`debug_link` l'utilisent en priorité, avec repli sur la fiche ChecklistBank publique si absent.
Licence `cc by` (simple, pas de restriction `NonCommercial`) : rien n'empêche d'exposer ce lien
publiquement."""

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
from organon.modules.ccw.adapter import DATASET_ID, CcwAdapter
from organon.modules.ccw.ranks import ccw_cherche_rang
from organon.modules.common import MAX_SYNONYM_HOPS, as_limit, collect_pages, format_auteur

_CHAINE_FIXE = (
    RankName(nom="Hexapoda", rang="sous-embranchement"),
    RankName(nom="Arthropoda", rang="embranchement"),
)
"""CCW ne couvre que cet unique embranchement/sous-embranchement (tout le catalogue est
Collembola), absents de la chaîne `classification` renvoyée par l'API (plafonnée à "class") :
injectés en dur plutôt qu'interrogés, la classe elle-même (Collembola) provenant déjà de l'API."""


class CcwModule(TaxonomyModule):
    meta = ModuleMeta(
        id="ccw",
        can_classify=True,
        can_render_external_link=True,
        domains=["animal"],
    )

    def __init__(self, adapter: CcwAdapter | None = None) -> None:
        self._adapter = adapter or CcwAdapter()

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

        struct.liens["ccw"] = {
            "id": taxon_id,
            "nom": name["scientificName"],
            "auteur": format_auteur(name.get("authorship")),
            "rang": ccw_cherche_rang(name["rank"]),
            "link": usage.get("link"),
            **({"eteint": usage["extinct"]} if "extinct" in usage else {}),
        }

        is_synonym = usage["status"] == "synonym"
        struct.liens["ccw"]["statut_detecte"] = "synonyme" if is_synonym else "accepté"
        if is_synonym:
            if not is_classification:
                struct.liens["ccw"]["synonyme"] = True
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
        struct.taxon.rang = ccw_cherche_rang(name["rank"])
        if "extinct" in usage:
            struct.taxon.eteint = usage["extinct"]
        struct.taxon.nom = name["scientificName"].strip()
        struct.classification = "CCW"
        struct.classification_taxobox = "CCW"
        struct.regne = "animal"

        classification = cur.get("classification", [])
        struct.rangs = [
            RankName(
                nom=c["name"],
                rang=ccw_cherche_rang(c["rank"]),
                auteur=format_auteur(c.get("authorship")),
            )
            for c in reversed(classification)
            if c.get("id") != taxon_id
        ] + list(_CHAINE_FIXE)

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
                        rang=ccw_cherche_rang(c["rank"]),
                        auteur=format_auteur(c.get("authorship")),
                        eteint=c.get("labelHtml", "").startswith("†") or None,
                    )
                )
            return out, len(raw), page.get("last", True)

        liste, coupe = await collect_pages(fetch_children, limit=as_limit(options.limite_listes))
        if liste:
            struct.sous_taxons = SubTaxonList(liste=liste, source="CCW", coupe=coupe)

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
                    rang=ccw_cherche_rang(sname.get("rank", "")),
                )
            )
        if synonymes:
            struct.synonymes = SynonymList(liste=synonymes, source="CCW", coupe=False)

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("ccw")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], data.get("rang") or struct.taxon.rang, struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]
        url = data.get("link") or (
            f"https://www.checklistbank.org/dataset/{DATASET_ID}/taxon/{data['id']}"
        )
        post = " <small>(non valide)</small>" if data.get("synonyme") else ""
        return (
            f"{{{{Lien web | langue=en | titre={cible} | url={url} "
            f"| site=Checklist of the Collembola of the World | consulté le={cdate} }}}}{post}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("ccw")
        if not data or "id" not in data:
            return None
        url = data.get("link") or (
            f"https://www.checklistbank.org/dataset/{DATASET_ID}/taxon/{data['id']}"
        )
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>CCW</a>"


register_module(CcwModule)

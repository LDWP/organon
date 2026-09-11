"""Logique métier du module Bryonames (« The Bryophyte Nomenclator ») : classification des
bryophytes (mousses, hépatiques, anthocérotes) via ChecklistBank dataset 170394 — voir
`adapter.py`. Domaine restreint à `["végétal"]` (pas de sous-domaine "bryophyte" dans l'arbre de
domaines Organon, comme POWO) : un taxon hors bryophytes n'y figure simplement pas, `collect`
renvoie alors None sans qu'aucune restriction explicite ne soit nécessaire ici.

Contrairement à `organon.modules.col.module` (même plateforme ChecklistBank, XR à 17 500
checklists fusionnées), ce dataset est mono-source et curaté par un seul éditeur : pas de
désambiguïsation multi-candidats nécessaire (`select_col_xr_candidate`/`_code_incoherent`) — le
premier candidat "accepted" retourné par `type=EXACT` suffit.

Le règne n'est jamais déduit de `classification` : la chaîne ne porte aucun rang `kingdom`/
`domain` (elle démarre à `subkingdom`, vérifié en direct sur mousses/hépatiques/anthocérotes) —
`struct.regne` est donc fixé à `"végétal"` en dur une fois un candidat validé, sur le même
principe que `algaebase_charte` pour AlgaeBase.

Aucun modèle `{{Bioref}}` dédié n'existe sur Wikipédia en français pour Bryonames (vérifié en
direct, 0 résultat dans l'espace de noms Modèle) : `render_bioref` utilise le modèle générique
`{{Lien web}}`, comme OTL/iNaturalist (voir `organon/modules/_archive/`). Le lien pointe vers la
fiche Tropicos d'origine (`name.link`, toujours présent en pratique) plutôt que vers la page
ChecklistBank correspondante : cette dernière est elle-même derrière un contrôle anti-bot
(`checklistbank.org`, testé en direct — bloqué même en navigateur automatisé réel), contrairement
à l'API `api.checklistbank.org` qui sert `adapter.py` sans restriction."""

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
from organon.modules.bryonames.adapter import BryonamesAdapter
from organon.modules.bryonames.ranks import bryonames_cherche_rang
from organon.modules.common import MAX_SYNONYM_HOPS, as_limit, collect_pages, format_auteur


class BryonamesModule(TaxonomyModule):
    meta = ModuleMeta(
        id="bryonames",
        can_classify=True,
        can_render_external_link=True,
        domains=["végétal"],
    )

    def __init__(self, adapter: BryonamesAdapter | None = None) -> None:
        self._adapter = adapter or BryonamesAdapter()

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

        struct.liens["bryonames"] = {
            "id": taxon_id,
            "nom": name["scientificName"],
            "auteur": format_auteur(name.get("authorship")),
            "rang": bryonames_cherche_rang(name["rank"]),
            "link": name.get("link"),
            **({"eteint": usage["extinct"]} if "extinct" in usage else {}),
        }

        is_synonym = usage["status"] == "synonym"
        struct.liens["bryonames"]["statut_detecte"] = "synonyme" if is_synonym else "accepté"
        if is_synonym:
            if not is_classification:
                struct.liens["bryonames"]["synonyme"] = True
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
        struct.taxon.rang = bryonames_cherche_rang(name["rank"])
        if "extinct" in usage:
            struct.taxon.eteint = usage["extinct"]
        struct.taxon.nom = name["scientificName"].strip()
        struct.classification = "Bryonames"
        struct.classification_taxobox = "Bryonames"
        struct.regne = "végétal"

        classification = cur.get("classification", [])
        struct.rangs = [
            RankName(
                nom=c["name"],
                rang=bryonames_cherche_rang(c["rank"]),
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
                        rang=bryonames_cherche_rang(c["rank"]),
                        auteur=format_auteur(c.get("authorship")),
                        eteint=c.get("labelHtml", "").startswith("†") or None,
                    )
                )
            return out, len(raw), page.get("last", True)

        liste, coupe = await collect_pages(fetch_children, limit=as_limit(options.limite_listes))
        if liste:
            struct.sous_taxons = SubTaxonList(liste=liste, source="Bryonames", coupe=coupe)

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
                    rang=bryonames_cherche_rang(sname.get("rank", "")),
                )
            )
        if synonymes:
            struct.synonymes = SynonymList(liste=synonymes, source="Bryonames", coupe=False)

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("bryonames")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], data.get("rang") or struct.taxon.rang, struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]
        url = data.get("link") or (
            f"https://www.checklistbank.org/dataset/170394/taxon/{data['id']}"
        )
        post = " <small>(non valide)</small>" if data.get("synonyme") else ""
        return (
            f"{{{{Lien web | langue=en | titre={cible} | url={url} "
            f"| site=Bryonames | consulté le={cdate} }}}}{post}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("bryonames")
        if not data or "id" not in data:
            return None
        url = data.get("link") or f"https://www.checklistbank.org/dataset/170394/taxon/{data['id']}"
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>Bryonames</a>"


register_module(BryonamesModule)

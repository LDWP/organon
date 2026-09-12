"""Logique métier du module World Catalogue of Opiliones (WCO) : classification des opilions
(faucheux, ordre Opiliones) via ChecklistBank dataset 2256 — voir `adapter.py`. Domaine restreint
à `["arachnide"]` (pas de sous-domaine "opilion" dans l'arbre de domaines Organon, comme WSC pour
les araignées) : un taxon hors Opiliones n'y figure simplement pas, `collect` renvoie alors None
sans qu'aucune restriction explicite ne soit nécessaire ici.

Comme `organon.modules.bryonames.module` (même plateforme ChecklistBank, dataset mono-source
curaté par une seule équipe éditoriale), pas de désambiguïsation multi-candidats nécessaire
(`select_col_xr_candidate`/`_code_incoherent` de `col_xr`) — le premier candidat "accepted"
retourné par `type=EXACT` suffit.

Le règne n'est jamais déduit de `classification` : la chaîne ne porte aucun rang au-dessus de
"order" (le dataset entier ne couvre que l'ordre Opiliones, vérifié en direct — `GET
.../dataset/2256/tree` renvoie Opiliones comme unique racine) — `struct.regne` est donc fixé à
"animal" en dur, et la chaîne classe/embranchement (Arachnida/Arthropoda) injectée au-dessus de
l'ordre, même principe que `organon.modules.wsc.module._CHAINE_FIXE` (à la différence que WSC n'a
même pas l'ordre dans son export CSV, alors qu'ici "Opiliones" est bien renvoyé dynamiquement par
l'API dans `classification`).

Aucun modèle `{{Bioref}}` dédié n'existe sur Wikipédia en français pour WCO (vérifié en direct,
0 résultat dans l'espace de noms Modèle) : `render_bioref` utilise le modèle générique
`{{Lien web}}`, comme Bryonames. Contrairement à Bryonames, l'API ne fournit aucun champ `link`
vers une source externe (pas d'équivalent Tropicos) : le lien pointe directement vers la fiche
ChecklistBank publique du taxon. Licence `cc by` (simple, pas de restriction `NonCommercial`
contrairement à WSC) : rien n'empêche d'exposer ce lien publiquement, contrairement à
`organon.modules.wsc.module` (`can_render_external_link=False` pour cause de licence CC
BY-NC-SA)."""

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
from organon.modules.wco.adapter import DATASET_ID, WcoAdapter
from organon.modules.wco.ranks import wco_cherche_rang

_CHAINE_FIXE = (
    RankName(nom="Arachnida", rang="classe"),
    RankName(nom="Arthropoda", rang="embranchement"),
)
"""WCO ne couvre que cet unique embranchement/classe (tout le catalogue est Opiliones), absent
de la chaîne `classification` renvoyée par l'API (plafonnée à "order") : injecté en dur plutôt
qu'interrogé, l'ordre lui-même (Opiliones) provenant déjà de l'API."""


class WcoModule(TaxonomyModule):
    meta = ModuleMeta(
        id="wco",
        can_classify=True,
        can_render_external_link=True,
        domains=["arachnide"],
        priority=990,
    )

    def __init__(self, adapter: WcoAdapter | None = None) -> None:
        self._adapter = adapter or WcoAdapter()

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

        struct.liens["wco"] = {
            "id": taxon_id,
            "nom": name["scientificName"],
            "auteur": format_auteur(name.get("authorship")),
            "rang": wco_cherche_rang(name["rank"]),
            **({"eteint": usage["extinct"]} if "extinct" in usage else {}),
        }

        is_synonym = usage["status"] == "synonym"
        struct.liens["wco"]["statut_detecte"] = "synonyme" if is_synonym else "accepté"
        if is_synonym:
            if not is_classification:
                struct.liens["wco"]["synonyme"] = True
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
        struct.taxon.rang = wco_cherche_rang(name["rank"])
        if "extinct" in usage:
            struct.taxon.eteint = usage["extinct"]
        struct.taxon.nom = name["scientificName"].strip()
        struct.classification = "WCO"
        struct.classification_taxobox = "WCO"
        struct.regne = "animal"

        classification = cur.get("classification", [])
        struct.rangs = [
            RankName(
                nom=c["name"],
                rang=wco_cherche_rang(c["rank"]),
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
                        rang=wco_cherche_rang(c["rank"]),
                        auteur=format_auteur(c.get("authorship")),
                        eteint=c.get("labelHtml", "").startswith("†") or None,
                    )
                )
            return out, len(raw), page.get("last", True)

        liste, coupe = await collect_pages(fetch_children, limit=as_limit(options.limite_listes))
        if liste:
            struct.sous_taxons = SubTaxonList(liste=liste, source="WCO", coupe=coupe)

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
                    rang=wco_cherche_rang(sname.get("rank", "")),
                )
            )
        if synonymes:
            struct.synonymes = SynonymList(liste=synonymes, source="WCO", coupe=False)

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("wco")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], data.get("rang") or struct.taxon.rang, struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]
        url = f"https://www.checklistbank.org/dataset/{DATASET_ID}/taxon/{data['id']}"
        post = " <small>(non valide)</small>" if data.get("synonyme") else ""
        return (
            f"{{{{Lien web | langue=en | titre={cible} | url={url} "
            f"| site=World Catalogue of Opiliones | consulté le={cdate} }}}}{post}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("wco")
        if not data or "id" not in data:
            return None
        url = f"https://www.checklistbank.org/dataset/{DATASET_ID}/taxon/{data['id']}"
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>WCO</a>"


register_module(WcoModule)

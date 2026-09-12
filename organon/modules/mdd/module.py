"""Logique métier du module MDD (Mammal Diversity Database, American Society of Mammalogists) :
classification des mammifères via ChecklistBank dataset 9802 — voir `adapter.py`. Domaine
restreint à `["mammifère"]` : classification mono-source curatée par un seul éditeur (comme
`organon.modules.bryonames.module`), pas de désambiguïsation multi-candidats nécessaire — le
premier candidat "accepted" retourné par `type=EXACT` suffit.

Le règne n'est jamais déduit de `classification` : la chaîne démarre à "class" (Mammalia, vérifié
en direct, aucun rang kingdom/phylum au-dessus) — `struct.regne` est donc fixé à `"animal"` en
dur une fois un candidat validé, même principe que Bryonames pour `"végétal"`.

Successeur actif de MSW3 (module `msw`, archivé sous `organon/modules/_archive/`, figé depuis
l'édition 2005) : contrairement à MSW (enrichissement seul), MDD classe (`can_classify=True`).

`render_bioref` distingue trois cas suivant le modèle Wikipédia dédié disponible (vérifiés en
direct sur `Modèle:MDD/Documentation` et `Modèle:MDDsup/Documentation`, et leur wikicode brut) :
- espèce/sous-espèce : `{{MDD | genre | épithète | id | cible | consulté le= }}` — les
  paramètres 1/2 (genre/épithète) ne sont en réalité pas exploités par le rendu du modèle
  (absents du wikicode, seul le paramètre 4 `cible`, pré-formaté comme pour `{{MSW}}`, l'est) ;
  renseignés tout de même pour respecter la convention d'appel documentée ;
- ordre/famille/genre : `{{MDDsup | ordre|famille|genre | nom | consulté le= }}` — le nom est
  passé brut, non pré-italicisé : le modèle italicise lui-même son paramètre 2 pour le rang
  genre, une double mise en italique produirait quatre apostrophes (gras+italique) au lieu de
  deux ;
- tout autre rang (classe, sous-classe, sous-ordre...) : aucun modèle dédié ne le couvre, repli
  sur `{{Lien web}}` générique vers `mammaldiversity.org/taxon/<id>` (site citable directement,
  contrairement à `checklistbank.org` derrière un contrôle anti-bot)."""

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
from organon.modules.mdd.adapter import MddAdapter
from organon.modules.mdd.ranks import mdd_cherche_rang

_RANGS_SUP = {"ordre", "famille", "genre"}


class MddModule(TaxonomyModule):
    meta = ModuleMeta(
        id="mdd",
        can_classify=True,
        can_render_external_link=True,
        domains=["mammifère"],
    )

    def __init__(self, adapter: MddAdapter | None = None) -> None:
        self._adapter = adapter or MddAdapter()

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

        struct.liens["mdd"] = {
            "id": taxon_id,
            "nom": name["scientificName"],
            "auteur": format_auteur(name.get("authorship")),
            "rang": mdd_cherche_rang(name["rank"]),
            "genre": name.get("genus"),
            "epithete": name.get("specificEpithet"),
            **({"eteint": usage["extinct"]} if "extinct" in usage else {}),
        }

        is_synonym = usage["status"] == "synonym"
        struct.liens["mdd"]["statut_detecte"] = "synonyme" if is_synonym else "accepté"
        if is_synonym:
            if not is_classification:
                struct.liens["mdd"]["synonyme"] = True
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
        struct.taxon.rang = mdd_cherche_rang(name["rank"])
        if "extinct" in usage:
            struct.taxon.eteint = usage["extinct"]
        struct.taxon.nom = name["scientificName"].strip()
        struct.classification = "MDD"
        struct.classification_taxobox = "MDD"
        struct.regne = "animal"

        classification = cur.get("classification", [])
        struct.rangs = [
            RankName(
                nom=c["name"],
                rang=mdd_cherche_rang(c["rank"]),
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
                        rang=mdd_cherche_rang(c["rank"]),
                        auteur=format_auteur(c.get("authorship")),
                        eteint=c.get("labelHtml", "").startswith("†") or None,
                    )
                )
            return out, len(raw), page.get("last", True)

        liste, coupe = await collect_pages(fetch_children, limit=as_limit(options.limite_listes))
        if liste:
            struct.sous_taxons = SubTaxonList(liste=liste, source="MDD", coupe=coupe)

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
                    rang=mdd_cherche_rang(sname.get("rank", "")),
                )
            )
        if synonymes:
            struct.synonymes = SynonymList(liste=synonymes, source="MDD", coupe=False)

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("mdd")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        rang = data.get("rang") or struct.taxon.rang
        post = " <small>(non valide)</small>" if data.get("synonyme") else ""

        if rang in _RANGS_SUP:
            return f"{{{{MDDsup | {rang} | {data['nom']} | consulté le={cdate} }}}}{post}"

        cible = wp_met_italiques(data["nom"], rang, struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]

        if rang in ("espèce", "sous-espèce") and data.get("genre") and data.get("epithete"):
            return (
                f"{{{{MDD | {data['genre']} | {data['epithete']} | {data['id']} | {cible} "
                f"| consulté le={cdate} }}}}{post}"
            )

        url = f"https://www.mammaldiversity.org/taxon/{data['id']}"
        return (
            f"{{{{Lien web | langue=en | titre={cible} | url={url} "
            f"| site=Mammal Diversity Database | consulté le={cdate} }}}}{post}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("mdd")
        if not data or "id" not in data:
            return None
        url = f"https://www.mammaldiversity.org/taxon/{data['id']}"
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>MDD</a>"


register_module(MddModule)

"""Logique métier du module GRIN Taxonomy (Germplasm Resources Information Network, USDA) :
classification des plantes cultivées/ressources génétiques via ChecklistBank dataset 2018 — voir
`adapter.py`. Domaine restreint à `["végétal"]` (pas de sous-domaine dédié dans l'arbre de
domaines Organon, comme POWO/Bryonames) : un taxon hors périmètre n'y figure simplement pas,
`collect` renvoie alors None sans qu'aucune restriction explicite ne soit nécessaire ici.

Comme `organon.modules.bryonames.module` (même plateforme ChecklistBank), ce dataset est
mono-source et curaté par un seul éditeur : pas de désambiguïsation multi-candidats nécessaire
(`select_col_xr_candidate`/`_code_incoherent`) — le premier candidat "accepted" retourné par
`type=EXACT` suffit.

Le règne n'est jamais déduit de `classification` : la chaîne ne porte aucun rang `kingdom`/
`order`/`class` (elle démarre à `family`, vérifié en direct sur Poaceae/Zea — GRIN Taxonomy
n'indexe que famille et rangs inférieurs) — `struct.regne` est donc fixé à `"végétal"` en dur une
fois un candidat validé, sur le même principe que `bryonames`/`algaebase_charte`.

Contrairement à Bryonames, GRIN a de vrais modèles `{{Bioref}}` dédiés sur fr.wikipedia,
vérifiés en direct (un par rang : `{{GRIN espèce}}`/`genre`/`sous-tribu`/`tribu`/`sous-famille`/
`famille`, wikicode de chacun consulté via `action=raw`) — `render_bioref` les sélectionne selon
le rang du taxon rendu, comme `indexfungorum` le fait pour ses propres modèles dédiés.
`codeGRIN` (paramètre 1 de ces modèles) est l'identifiant numérique brut sur npgsweb.ars-grin.gov ;
ChecklistBank préfixe cet identifiant par groupe de rangs (`gen:`/`fam:`, ce dernier couvrant
aussi bien famille que sous-famille/tribu/sous-tribu) — retirer ce préfixe restitue le codeGRIN
d'origine (recoupé en direct : le champ `name.link` d'un enregistrement d'espèce pointe vers
`taxonomydetail?id=<partie numérique de son id ChecklistBank>`).

Particularité vérifiée sur le wikicode brut de `{{GRIN espèce}}` : contrairement aux cinq autres
modèles, il n'a pas de paramètre positionnel « validité » (`nv`) pour marquer un synonyme —
`render_bioref` retombe alors sur le même suffixe textuel `<small>(non valide)</small>` que
`bryonames` pour ce seul rang.

`debug_link` ne peut pas se contenter d'un unique gabarit d'URL : `name.link` (fiche GRIN
d'origine) n'est renvoyé par l'API qu'au rang espèce (vérifié en direct, absent sur
genre/famille/tribu/etc.) ; `_url_grin` reconstruit alors l'URL par rang à partir du même
schéma que les modèles wiki (`taxonomydetail` pour l'espèce, `taxonomygenus.aspx` pour le
genre, `taxonomyfamily.aspx?type=...` pour famille/sous-famille/tribu/sous-tribu)."""

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
from organon.modules.grin.adapter import GrinAdapter
from organon.modules.grin.ranks import grin_cherche_rang

_ESPECE_RANGS = {"espèce", "sous-espèce", "variété", "forme"}
"""Rangs mappés sur `{{GRIN espèce}}` — les autres rangs observés dans ce dataset (famille et
en dessous) ont chacun leur propre modèle dédié."""

_RANG_MODELE = {
    "sous-tribu": "GRIN sous-tribu",
    "tribu": "GRIN tribu",
    "sous-famille": "GRIN sous-famille",
    "genre": "GRIN genre",
}
"""Tout rang absent d'ici retombe sur `{{GRIN famille}}` : la chaîne de classification GRIN ne
dépasse jamais la famille (vérifié en direct), qui sert donc de modèle par défaut plutôt que
`espèce`/`genre`."""


def _modele_pour_rang(rang: str) -> str:
    if rang in _ESPECE_RANGS:
        return "GRIN espèce"
    return _RANG_MODELE.get(rang, "GRIN famille")


def _code_grin(taxon_id: str) -> str:
    return taxon_id.rsplit(":", 1)[-1]


_URL_TYPE = {
    "GRIN sous-tribu": "subtribe",
    "GRIN tribu": "tribe",
    "GRIN sous-famille": "subfamily",
    "GRIN famille": "family",
}
"""Le site GRIN sert genre/famille/tribu/sous-famille/sous-tribu par une même page
`taxonomyfamily.aspx` distinguée par `type=`, mais l'espèce et le genre ont chacun leur propre
page (`taxonomydetail`/`taxonomygenus`) — schéma d'URL relevé sur le wikicode brut des six
modèles GRIN, réutilisé ici pour `debug_link` faute de `name.link` renvoyé par l'API au-delà du
rang espèce (vérifié en direct : absent sur genre/famille)."""


def _url_grin(rang: str, code: str) -> str:
    modele = _modele_pour_rang(rang)
    if modele == "GRIN espèce":
        return f"https://npgsweb.ars-grin.gov/gringlobal/taxon/taxonomydetail?id={code}"
    if modele == "GRIN genre":
        return f"https://npgsweb.ars-grin.gov/gringlobal/taxon/taxonomygenus.aspx?id={code}"
    return (
        "https://npgsweb.ars-grin.gov/gringlobal/taxon/taxonomyfamily.aspx"
        f"?type={_URL_TYPE[modele]}&id={code}"
    )


class GrinModule(TaxonomyModule):
    meta = ModuleMeta(
        id="grin",
        can_classify=True,
        can_render_external_link=True,
        domains=["végétal"],
    )

    def __init__(self, adapter: GrinAdapter | None = None) -> None:
        self._adapter = adapter or GrinAdapter()

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

        struct.liens["grin"] = {
            "id": taxon_id,
            "nom": name["scientificName"],
            "auteur": format_auteur(name.get("authorship")),
            "rang": grin_cherche_rang(name["rank"]),
            "link": name.get("link"),
        }

        is_synonym = usage["status"] == "synonym"
        struct.liens["grin"]["statut_detecte"] = "synonyme" if is_synonym else "accepté"
        if is_synonym:
            if not is_classification:
                struct.liens["grin"]["synonyme"] = True
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
        struct.taxon.rang = grin_cherche_rang(name["rank"])
        struct.taxon.nom = name["scientificName"].strip()
        struct.classification = "GRIN"
        struct.classification_taxobox = "GRIN"
        struct.regne = "végétal"

        classification = cur.get("classification", [])
        struct.rangs = [
            RankName(
                nom=c["name"],
                rang=grin_cherche_rang(c["rank"]),
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
                        rang=grin_cherche_rang(c["rank"]),
                        auteur=format_auteur(c.get("authorship")),
                    )
                )
            return out, len(raw), page.get("last", True)

        liste, coupe = await collect_pages(fetch_children, limit=as_limit(options.limite_listes))
        if liste:
            struct.sous_taxons = SubTaxonList(liste=liste, source="GRIN", coupe=coupe)

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
                    rang=grin_cherche_rang(sname.get("rank", "")),
                )
            )
        if synonymes:
            struct.synonymes = SynonymList(liste=synonymes, source="GRIN", coupe=False)

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("grin")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        rang = data.get("rang") or struct.taxon.rang or ""
        modele = _modele_pour_rang(rang)
        code = _code_grin(data["id"])
        cible = wp_met_italiques(data["nom"], rang, struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]

        if modele == "GRIN espèce":
            post = " <small>(non valide)</small>" if data.get("synonyme") else ""
            return f"{{{{{modele} | {code} | {cible} | consulté le={cdate} }}}}{post}"

        champs = [code, cible]
        if data.get("synonyme"):
            champs.append("nv")
        corps = " | ".join(champs)
        return f"{{{{{modele} | {corps} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("grin")
        if not data or "id" not in data:
            return None
        rang = data.get("rang") or struct.taxon.rang or ""
        url = data.get("link") or _url_grin(rang, _code_grin(data["id"]))
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>GRIN</a>"


register_module(GrinModule)

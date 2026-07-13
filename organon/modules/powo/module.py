"""Logique métier du module POWO (Plants of the World Online) : classification (domaine
`['végétal']`), auteur, rang, synonymes, distribution géographique.

`search()` renvoie plusieurs enregistrements pour un nom ambigu (homonymes) sans distinction
fiable hormis le champ `accepted` : filtré sur correspondance exacte de `name`, puis préférence à
l'enregistrement `accepted=True` s'il existe (à défaut, le premier résultat exact, comme
`organon.modules.tropicos`).

`lookup(id, include=['distribution'])` sert de seconde étape pour récupérer la fiche complète
(classification, synonymes, distribution) à partir du `fqId` (LSID IPNI complet) trouvé par la
recherche — `fqId` sert directement d'identifiant pour `pykew.powo.lookup`, sans reconstruction
depuis `url`.

Suivi de synonyme (mode classification uniquement, comme ITIS/GBIF) : un enregistrement dont
`taxonomicStatus` n'est pas "Accepted" porte un champ `accepted` (fqId + nom du nom accepté) —
utilisé pour relancer la collecte sur ce nom si `suivre_synonymes` est actif, sinon la
classification se construit directement à partir du synonyme tel quel (même convention que
ITIS/GBIF : "on continue avec les données du synonyme").

Distribution (`detail["distribution"]`) : un dict de catégories (`natives`, `introduced`,
`absent`, vues en direct ; `extinct`/`doubtful` probables par le même schéma WCVP mais non
observées) plutôt qu'une simple liste de codes — chaque entrée porte `tdwgCode` (code régional
TDWG/WGSRPD, ex. "FRA_FR") et `establishment` (ex. "Native", "Introduced", "Absent"). Bug corrigé
ici : une version précédente lisait `detail.get("distribution")` comme si c'était déjà une liste
de codes — comme ce champ est toujours un dict (jamais None) quand `include=['distribution']` est
demandé, la garde `isinstance(raw, list)` était toujours fausse et aucune distribution n'était
jamais retenue. `_distribution_entries` ci-dessous consomme la structure réelle, classe "Absent"
exclu (le taxon n'y est explicitement pas), "Native"/"Introduced" en présence certaine, tout le
reste (ex. "Doubtful") en présence incertaine ; secours sur `locations` (liste plate de codes,
sans distinction de statut) si `distribution` est absent.

Ces codes TDWG/WGSRPD ne sont pas des codes pays ISO 3166 : `organon.core.rendering.support`
attend des codes ISO mais retombe sur le code brut non lié pour tout code inconnu (comportement
documenté), donc aucun crash — seulement un rendu moins soigné pour ces codes tant qu'aucune
table de correspondance TDWG->ISO n'existe dans `organon/core`."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import (
    DistributionEntry,
    RankName,
    Redirection,
    Struct,
    SynonymList,
    TaxonInfo,
)
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.support import dates_recupere
from organon.modules.common import MAX_SYNONYM_HOPS, as_limit, format_auteur, simple_debug_link
from organon.modules.powo.adapter import PowoAdapter
from organon.modules.powo.ranks import powo_cherche_rang, powo_cherche_regne

_ABSENT = "absent"
_INCERTAIN = {"doubtful", "extinct"}


def _distribution_entries(detail: dict) -> tuple[dict[str, str], dict[str, str]]:
    certain: dict[str, str] = {}
    uncertain: dict[str, str] = {}

    dist = detail.get("distribution")
    if isinstance(dist, dict):
        for entries in dist.values():
            if not isinstance(entries, list):
                continue
            for e in entries:
                code = e.get("tdwgCode")
                if not isinstance(code, str):
                    continue
                statut = (e.get("establishment") or "").lower()
                if statut == _ABSENT:
                    continue
                (uncertain if statut in _INCERTAIN else certain)[code] = code
        return certain, uncertain

    locations = detail.get("locations")
    if isinstance(locations, list):
        certain = {code: code for code in locations if isinstance(code, str)}
    return certain, uncertain


class PowoModule(TaxonomyModule):
    meta = ModuleMeta(
        id="powo", can_classify=True, can_render_external_link=True, domains=["végétal"]
    )

    def __init__(self, adapter: PowoAdapter | None = None) -> None:
        self._adapter = adapter or PowoAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        return await self._collect(struct, is_classification, options, hop=0)

    async def _collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions, hop: int
    ) -> Struct | None:
        results = await self._adapter.search(struct.taxon.nom)
        exact = [r for r in results if r.get("name") == struct.taxon.nom]
        if not exact:
            return None
        match = next((r for r in exact if r.get("accepted")), exact[0])

        taxon_id = match.get("fqId")
        if not taxon_id:
            return None

        detail = await self._adapter.lookup(taxon_id, include=["distribution"])
        if detail is None:
            return None

        numero = taxon_id.rsplit(":", 1)[-1]
        rang = powo_cherche_rang(detail.get("rank"))
        entry: dict = {
            "id": numero,
            "nom": detail.get("name") or match["name"],
            "auteur": format_auteur(detail.get("authors")),
        }
        if rang:
            entry["rang"] = rang
        est_synonyme = detail.get("taxonomicStatus") not in (None, "Accepted")
        if est_synonyme:
            entry["synonyme"] = True
        struct.liens["powo"] = entry

        synonymes_liste = [
            RankName(
                nom=s["name"],
                auteur=format_auteur(s.get("author")),
                rang=powo_cherche_rang(s.get("rank")),
            )
            for s in detail.get("synonyms") or []
            if s.get("name")
        ]
        limit = as_limit(options.limite_listes)
        coupe = False
        if limit is not None and len(synonymes_liste) > limit:
            synonymes_liste = synonymes_liste[:limit]
            coupe = True
        if synonymes_liste:
            struct.synonymes = SynonymList(liste=synonymes_liste, source="POWO", coupe=coupe)

        certain, uncertain = _distribution_entries(detail)
        if certain or uncertain:
            struct.distribution["powo"] = DistributionEntry(certain=certain, uncertain=uncertain)

        if est_synonyme:
            if not is_classification:
                return struct
            if options.suivre_synonymes:
                accepted = detail.get("accepted") or {}
                if accepted.get("fqId") and accepted.get("name"):
                    if hop >= MAX_SYNONYM_HOPS:
                        return None
                    struct.redirection = Redirection(nom=struct.taxon.nom)
                    struct.taxon = TaxonInfo(nom=accepted["name"])
                    return await self._collect(struct, is_classification, options, hop=hop + 1)
            # suivre_synonymes désactivé (ou pas de champ "accepted" exploitable) : on continue
            # avec les données du synonyme tel quel, comme ITIS/GBIF.

        if not is_classification:
            return struct

        regne = powo_cherche_regne(detail.get("kingdom"))
        if not regne:
            return None

        struct.taxon.rang = rang
        struct.taxon.auteur = format_auteur(detail.get("authors"))
        struct.regne = regne
        struct.classification = "POWO"
        struct.classification_taxobox = "POWO"

        chain = detail.get("classification") or []
        rangs = [
            RankName(
                nom=c["name"],
                rang=powo_cherche_rang(c.get("rank")),
                auteur=format_auteur(c.get("author")),
            )
            for c in chain
            if c.get("fqId") != taxon_id and c.get("name")
        ]
        rangs.reverse()
        struct.rangs = rangs

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("powo")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        parts = [data["id"], data["nom"]]
        if data.get("auteur") or data.get("synonyme"):
            parts.append(data.get("auteur") or "")
        if data.get("synonyme"):
            parts.append("nv")
        body = " | ".join(parts)
        return f"{{{{POWO | {body} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(
            struct,
            "powo",
            "https://powo.science.kew.org/taxon/urn:lsid:ipni.org:names:{id}",
            "POWO",
        )


register_module(PowoModule)

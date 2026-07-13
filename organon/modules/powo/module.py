"""Logique métier du module POWO (Plants of the World Online) : enrichissement botanique
(auteur, rang, synonymes, distribution géographique), domaine `['végétal']`. Aucune
classification — comme CITES/NCBI/TelaMétro/IPNI/Tropicos/VASCAN, ce module réutilise
`struct.taxon.rang` déjà connu plutôt que d'alimenter `struct.rangs`.

`search()` renvoie plusieurs enregistrements pour un nom ambigu (homonymes) sans distinction
fiable hormis le champ `accepted` : filtré sur correspondance exacte de `name`, puis préférence à
l'enregistrement `accepted=True` s'il existe (à défaut, le premier résultat exact, comme
`organon.modules.tropicos`).

`lookup(id, include=['distribution'])` sert de seconde étape pour récupérer la fiche complète
(synonymes, distribution) à partir du `fqId` (LSID IPNI complet) trouvé par la recherche —
`fqId` sert directement d'identifiant pour `pykew.powo.lookup`, sans reconstruction depuis `url`.

La distribution POWO (`locations`) utilise les codes régionaux TDWG/WGSRPD (ex. "EUROPE",
"FRA_FR"), pas des codes pays ISO 3166 : `organon.core.rendering.support.data_pays_code`
attend des codes ISO mais retombe sur le code brut non lié pour tout code inconnu (comportement
documenté), donc aucun crash — seulement un rendu moins soigné pour ces codes tant qu'aucune
table de correspondance TDWG->ISO n'existe dans `organon/core`."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import DistributionEntry, RankName, Struct, SynonymList
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.support import dates_recupere
from organon.modules.common import as_limit, format_auteur, simple_debug_link
from organon.modules.powo.adapter import PowoAdapter
from organon.modules.powo.ranks import powo_cherche_rang


def _distribution_codes(detail: dict) -> list[str]:
    raw = detail.get("distribution")
    if raw is None:
        raw = detail.get("locations")
    if not isinstance(raw, list):
        return []
    return [code for code in raw if isinstance(code, str)]


class PowoModule(TaxonomyModule):
    meta = ModuleMeta(
        id="powo", can_classify=False, can_render_external_link=True, domains=["végétal"]
    )

    def __init__(self, adapter: PowoAdapter | None = None) -> None:
        self._adapter = adapter or PowoAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
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
        entry: dict = {
            "id": numero,
            "nom": detail.get("name") or match["name"],
            "auteur": format_auteur(detail.get("authors")),
        }
        rang = powo_cherche_rang(detail.get("rank"))
        if rang:
            entry["rang"] = rang
        if detail.get("taxonomicStatus") not in (None, "Accepted"):
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

        codes = _distribution_codes(detail)
        if codes:
            struct.distribution["powo"] = DistributionEntry(certain={code: code for code in codes})

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

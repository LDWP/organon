"""Enrichissement de la « publication originale » IPNI (`struct.originale`) : IPNI n'expose
aucun champ DOI structuré (vérifié en direct sur l'API réelle), mais un DOI apparaît parfois en
texte libre dans `remarks`, mélangé à d'autres notes (étymologie, etc.) — ex. vérifié sur
*Rafflesia consueloae* : `"remarks":"doi:10.3897/phytokeys.61.7295 The specific epithet honors
..."`. Absent sur les noms antérieurs à l'existence des DOI (couverture partielle, contrairement
à LPSN). Délègue ensuite à `organon.modules.bibliography.resolve_doi_citation`, partagée avec
WoRMS et LPSN. À défaut de DOI trouvé ou exploitable, repli sur `reference` (citation texte libre
toujours présente sur un enregistrement de nom IPNI).

Non résolu ici, volontairement (voir docs/md/plans/plan-doi-publication-originale.md) :
`linkedPublication.bhlTitleLink` est une URL OpenURL, pas un identifiant BHL direct exploitable
par `organon.modules.wrms.adapter.WrmsAdapter.bhl_title_metadata` sans confirmation préalable du
format — `reference` couvre déjà le repli texte brut, pas besoin du chaînage BHL pour ce POC."""

from __future__ import annotations

from organon.modules.bibliography import DOI_RE, LOOKUP_ERRORS
from organon.modules.ipni.adapter import IpniAdapter


async def build_citation(adapter: IpniAdapter, match: dict) -> str | None:
    remarks = match.get("remarks") or ""
    doi_match = DOI_RE.search(remarks)
    if doi_match:
        doi = doi_match.group(0).rstrip(".,;)]")
        try:
            enrichie = await adapter.resolve_doi_citation(doi)
            if enrichie:
                return enrichie
        except LOOKUP_ERRORS:
            pass
    return match.get("reference")

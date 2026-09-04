"""Enrichissement de la « publication originale » LPSN (`struct.originale`) : contrairement à
WoRMS, LPSN expose `publication_doi` comme champ JSON structuré (voir doc publique
https://lpsn.dsmz.de/text/lpsn-api) — pas de scraping ni d'extraction par regex nécessaires, le
DOI est déjà séparé du texte de citation dans `publication_text`. Délègue ensuite à
`organon.modules.bibliography.resolve_doi_citation` (Wikidata P356 -> `{{Bibliographie|Qxxx}}`,
sinon Crossref -> `{{Article}}`/`{{Ouvrage}}`), partagée avec WoRMS.

Volontairement hors périmètre (voir docs/md/plans/plan-doi-publication-originale.md) :
`ijsem_list_text`/`ijsem_list_doi` (publication de *Validation List*, distincte de la publication
originale pour les noms validés a posteriori — n'entre en jeu que si l'on voulait un jour refléter
la date qui fait foi pour la priorité nomenclaturale, pas la publication originale elle-même) et
`publication_pmid` (pas de source PubMed déjà intégrée au projet).

Toute étape en échec (réseau, forme de réponse inattendue) retombe sur `publication_text` brut :
cet enrichissement est un bonus, jamais une condition de succès du module LPSN."""

from __future__ import annotations

from organon.modules.bibliography import LOOKUP_ERRORS
from organon.modules.lpsn.adapter import LpsnAdapter


def _wikify_italics(texte: str) -> str:
    # Même convention que WoRMS/AlgaeBase pour un titre d'ouvrage éventuellement mis en italique
    # dans le texte source (voir `organon.modules.common.extract_aphia_original_description`) —
    # vérifié en direct (Haemophilus felis, Escherichia coli, Bacillus subtilis) : `publication_
    # text` est du texte brut sans balise sur les fiches consultées, ce remplacement reste donc un
    # no-op inoffensif tant qu'aucun contre-exemple n'est rencontré.
    return texte.replace("<i>", "''").replace("</i>", "''")


async def build_citation(adapter: LpsnAdapter, record: dict) -> str | None:
    texte = record.get("publication_text")
    doi = record.get("publication_doi")
    if doi:
        try:
            enrichie = await adapter.resolve_doi_citation(doi)
            if enrichie:
                return enrichie
        except LOOKUP_ERRORS:
            pass
    return _wikify_italics(texte) if texte else None

"""Table de correspondance rangs/règnes iNaturalist -> Wikipédia.

Contrairement à Open Tree of Life, iNaturalist utilise un jeu de rangs fermé et documenté
(vérifié en direct sur plusieurs lignées : *Gadus morhua*, *Homo sapiens*) — "kingdom" y est
posé de façon fiable et systématique pour les huit groupes attendus (Animalia, Plantae, Fungi,
Chromista, Protozoa, Bacteria, Archaea, Viruses), tous déjà couverts par
`core.domains.KINGDOM_MAP` : aucune table d'alias locale nécessaire, contrairement à OTL."""

from __future__ import annotations

INAT_RANKS: dict[str, str] = {
    "subkingdom": "sous-règne",
    "phylum": "embranchement",
    "subphylum": "sous-embranchement",
    "superclass": "super-classe",
    "class": "classe",
    "subclass": "sous-classe",
    "infraclass": "infra-classe",
    "superorder": "super-ordre",
    "order": "ordre",
    "suborder": "sous-ordre",
    "infraorder": "infra-ordre",
    "superfamily": "super-famille",
    "epifamily": "épifamille",
    "family": "famille",
    "subfamily": "sous-famille",
    "supertribe": "super-tribu",
    "tribe": "tribu",
    "subtribe": "sous-tribu",
    "genus": "genre",
    "subgenus": "sous-genre",
    "species": "espèce",
    "subspecies": "sous-espèce",
    "variety": "variété",
    "form": "forme",
}
"""Ne couvre pas "kingdom" (consommé à part pour struct.regne, jamais ajouté à struct.rangs,
même convention que GBIF/OTL) ni "stateofmatter" (racine "Life", pas un rang biologique) ni les
rangs sans équivalent dans core/data/ranks.yaml ("zoosection"/"zoosubsection", utilisés pour
certains groupes de squamates ; "parvorder", "genushybrid", "hybrid", "infrahybrid" — même
lacune déjà présente côté GBIF pour "PARVORDER", non un oubli propre à ce module)."""


def inat_rang(rank: str) -> str | None:
    return INAT_RANKS.get(rank)

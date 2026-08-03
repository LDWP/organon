"""Table de correspondance rangs ICTV (colonnes de organon/core/data/ictv_taxonomy.tsv) -> rangs
Wikipédia (organon/core/data/ranks.yaml). `Subkingdom` n'a volontairement aucune entrée :
entièrement vide dans le MSL courant (voir scripts/build_ictv_taxonomy.py) — à ajouter le jour où
l'ICTV l'utilise réellement.

`Realm`/`Subrealm` ne sont volontairement pas traduits (pas de "royaume"/"sous-royaume") :
conformément à {{Modèle:Taxoboxoutils rang}} sur frwiki, qui affiche ces rangs ICTV en anglais
via {{lang|en|Realm}}/{{lang|en|Subrealm}} liés vers [[Realm (virologie)]] — voir le champ
`lang_en` de `RankEntry` (organon/core/rendering/grammar.py)."""

from __future__ import annotations

ICTV_RANGS: dict[str, str] = {
    "Realm": "realm",
    "Subrealm": "subrealm",
    "Kingdom": "kingdom",
    "Phylum": "phylum",
    "Subphylum": "sous-phylum",
    "Class": "classe",
    "Subclass": "sous-classe",
    "Order": "ordre",
    "Suborder": "sous-ordre",
    "Family": "famille",
    "Subfamily": "sous-famille",
    "Genus": "genre",
    "Subgenus": "sous-genre",
    "Species": "espèce",
}


def ictv_rang(colonne: str) -> str:
    return ICTV_RANGS.get(colonne, f"NOTFOUND-{colonne}")

"""Table de correspondance de rangs Index Fungorum -> Wikipédia, et rattachement au règne Fungi.

Contrairement à IRMNG/WoRMS (jeu de rangs XML fermé et documenté), Index Fungorum n'expose le
rang du taxon demandé que sous la forme d'une abréviation bibliographique
(`INFRASPECIFIC_RANK`, ex. "sp.", "var.", "fam.") — le nom du champ est trompeur : vérifié en
direct que CABI l'utilise en réalité pour TOUS les rangs (une recherche de genre renvoie
"gen.", une recherche de famille "fam.", une recherche d'ordre "ord.", pas seulement les rangs
infraspécifiques). Seules les abréviations rencontrées en direct sont couvertes ici ; une
abréviation absente retombe sur la convention "NOTFOUND-{code}" déjà en usage dans les autres
modules (IRMNG, OTL) plutôt que d'être devinée.

La chaîne de classification (`struct.rangs`) ne vient pas de ce champ mais d'une échelle fixe,
toujours dans le même ordre, jointe par `NameByKey` via le genre du taxon — vérifiée en direct
sur cinq phylums différents (Basidiomycota, Ascomycota, Mucoromycota, Chytridiomycota) :
genre < famille < ordre < sous-classe < classe < sous-embranchement < embranchement < règne.
Cette jointure n'existe que pour les enregistrements de rang genre et en dessous : vérifié en
direct qu'un enregistrement de rang famille ou supérieur (ex. Amanitaceae) ne porte aucun de
ces champs (tous absents), pas seulement le champ du taxon lui-même — `module.py` traite donc
ce cas comme une donnée de classification insuffisante (retourne None), pas une erreur.
"Incertae sedis" est le témoin CABI d'un rang intercalaire non résolu (ex. beaucoup de familles
n'ont pas de sous-classe assignée) et est omis de la chaîne au même titre qu'une valeur vide."""

from __future__ import annotations

from organon.core.domains import KINGDOM_MAP

IXF_RANKS: dict[str, str] = {
    "regn.": "règne",
    "subregn.": "sous-règne",
    "phyl.": "embranchement",
    "subphyl.": "sous-embranchement",
    "class.": "classe",
    "subclass.": "sous-classe",
    "ord.": "ordre",
    "fam.": "famille",
    "gen.": "genre",
    "sp.": "espèce",
    "subsp.": "sous-espèce",
    "var.": "variété",
    "f.": "forme",
}

CLASSIFICATION_LADDER: list[tuple[str, str]] = [
    ("Genus_name", "genre"),
    ("Family_name", "famille"),
    ("Order_name", "ordre"),
    ("Subclass_name", "sous-classe"),
    ("Class_name", "classe"),
    ("Subphylum_name", "sous-embranchement"),
    ("Phylum_name", "embranchement"),
]
"""Champs renvoyés par NameByKey pour la chaîne de classification, du plus proche au plus
éloigné du taxon demandé. Kingdom_name est géré à part (struct.regne via ixf_regne), jamais
ajouté à struct.rangs — même convention que otl_regne/GBIF (KINGDOM déclenche un `continue`)."""

UNRESOLVED_PLACEHOLDER = "Incertae sedis"


def ixf_rang(code: str | None) -> str | None:
    if not code:
        return None
    return IXF_RANKS.get(code, f"NOTFOUND-{code}")


def ixf_regne(kingdom_name: str | None) -> str | None:
    if not kingdom_name:
        return None
    return KINGDOM_MAP.get(kingdom_name, "champignon")

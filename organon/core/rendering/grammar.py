"""Fonctions de grammaire/rendu des noms scientifiques (wp_nom_rang, wp_met_italiques,
wp_un_rang, wp_le_rang, wp_inf_rang, wp_eteint_rang, wp_est_italique), ainsi que les tables
associatives par règne (lien vers la page de citation d'auteurs, lien basionyme, catégorie,
synonyme). Les données de rang viennent de `organon/core/data/ranks.yaml` (voir
scripts/build_ranks_yaml.py) plutôt que d'être codées en dur : éditable sans toucher au code
Python.

`wp_ebauche()`, `lien_pour_categorie()` et `lien_pour_portail()` dépendent du moteur de règles
(voir `organon.core.selectors`) — leur logique vit là-bas, pas ici.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class RankEntry(BaseModel):
    """Primitives non dérivables d'un rang (voir l'en-tête de ranks.yaml). Le nom minuscule
    canonique est la clé YAML elle-même (`RankTable.ranks`), pas un champ dupliqué ici."""

    genre: Literal["masculin", "féminin"]
    rang_inferieur_espece: bool
    page: str | None = None
    pluriel: str | None = None
    invariant: bool = False


class AdjectiveEntry(BaseModel):
    masculin_singulier: str
    feminin_singulier: str
    neutre_singulier: str
    masculin_pluriel: str
    feminin_pluriel: str
    neutre_pluriel: str
    lien_interne: bool
    page: str


class RankTable(BaseModel):
    ranks: dict[str, RankEntry]
    adjectives: dict[str, AdjectiveEntry]


@lru_cache(maxsize=1)
def load_rank_table(path: Path | None = None) -> RankTable:
    target = path or (DATA_DIR / "ranks.yaml")
    with target.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return RankTable.model_validate(raw)


# Mots à h muet (élision en l'/d' malgré une initiale consonantique) : liste fermée, tenue à
# jour à la main faute d'un meilleur signal dans une liste de ~60 rangs. Étendre si un nouveau
# rang à h muet apparaît dans ranks.yaml.
_H_MUET: set[str] = {"hybride"}

_VOYELLES = set("aeiouyàâäéèêëïîôöùûü")


def _commence_par_son_vocalique(nom: str) -> bool:
    return bool(nom) and (nom[0].lower() in _VOYELLES or nom in _H_MUET)


def _majuscule(nom: str) -> str:
    return nom[0].upper() + nom[1:] if nom else nom


def _forme_nom(nom_minuscule: str, entry: RankEntry, maj: bool, plur: bool) -> str:
    """Calcule une des quatre formes (min/maj × sing/plur) du nom d'un rang à partir du nom
    minuscule canonique et des irrégularités éventuelles (pluriel, invariant). Un rang
    invariant (non-classé) ignore aussi bien le pluriel que la majuscule : les quatre formes
    sont identiques au nom minuscule."""
    if entry.invariant:
        return nom_minuscule
    base = nom_minuscule
    if plur:
        base = entry.pluriel or f"{nom_minuscule}s"
    return _majuscule(base) if maj else base


def _forme_lien(nom_minuscule: str, entry: RankEntry, maj: bool) -> str:
    """Calcule un wikilien : bare [[Nom]] par défaut, ou [[Page|Nom]] si `page` diffère du nom
    (redirection/désambiguïsation). Cas particulier des rangs invariants (non-classé) : pas de
    page réelle, seulement un texte de substitution entouré de tirets cadratins."""
    if entry.invariant:
        return f"— {nom_minuscule} —"
    affiche = _forme_nom(nom_minuscule, entry, maj, plur=False)
    if entry.page is None:
        return f"[[{affiche}]]"
    return f"[[{entry.page}|{affiche}]]"


# Italique systématique True partout SAUF pour les règnes suivants, où l'italique dépend du
# rang (cf. wp_est_italique).
DOMAINES_SANS_ITALIQUE_SYSTEMATIQUE: set[str] = {
    "animal",
    "reptile",
    "amphibien",
    "protiste",
    "eucaryote",
}


def wp_rang_valide(rang: str, table: RankTable | None = None) -> bool:
    table = table or load_rank_table()
    return rang in table.ranks


def wp_nom_rang(rang: str, lien: bool, maj: bool, plur: bool, table: RankTable | None = None) -> str:
    """Retourne le nom d'un rang selon les options : avec/sans wikilien, avec/sans
    majuscule, au singulier/pluriel. Les formes sont calculées à partir du nom minuscule
    canonique (clé YAML) et des irrégularités éventuelles, pas stockées telles quelles."""
    table = table or load_rank_table()
    if not wp_rang_valide(rang, table):
        return "NOTFOUND"
    entry = table.ranks[rang]
    if lien:
        return _forme_lien(rang, entry, maj)
    return _forme_nom(rang, entry, maj, plur)


def wp_un_rang(rang: str, table: RankTable | None = None) -> str:
    table = table or load_rank_table()
    if not wp_rang_valide(rang, table):
        return "NOTFOUND"
    return "un " if table.ranks[rang].genre == "masculin" else "une "


def wp_le_rang(rang: str, table: RankTable | None = None) -> str:
    table = table or load_rank_table()
    if not wp_rang_valide(rang, table):
        return "NOTFOUND"
    if _commence_par_son_vocalique(rang):
        return "l'"
    return "le " if table.ranks[rang].genre == "masculin" else "la "


def wp_inf_rang(rang: str, table: RankTable | None = None) -> bool | str:
    """Indique si le rang est inférieur au genre (au sens de « rang d'espèce ou en dessous »
    utilisé par wp_est_italique — pas seulement < espèce)."""
    table = table or load_rank_table()
    if not wp_rang_valide(rang, table):
        return "NOTFOUND"
    return table.ranks[rang].rang_inferieur_espece


def wp_accorde_adjectif(
    nom_adjectif: str, genre: Literal["masculin", "féminin"], plur: bool = False,
    table: RankTable | None = None,
) -> str:
    """Accorde un adjectif de la table `adjectives` (ranks.yaml) en genre/nombre, et l'entoure
    de son wikilien interne si `lien_interne` est vrai."""
    table = table or load_rank_table()
    entry = table.adjectives.get(nom_adjectif)
    if entry is None:
        return "NOTFOUND"
    if genre == "masculin":
        forme = entry.masculin_pluriel if plur else entry.masculin_singulier
    else:
        forme = entry.feminin_pluriel if plur else entry.feminin_singulier
    if entry.lien_interne:
        return f"[[{entry.page}|{forme}]]"
    return forme


def wp_eteint_rang(rang: str, table: RankTable | None = None) -> str:
    table = table or load_rank_table()
    if not wp_rang_valide(rang, table):
        return "NOTFOUND"
    return wp_accorde_adjectif("éteint", table.ranks[rang].genre, table=table)


def wp_est_italique(rang: str, regne: str, table: RankTable | None = None) -> bool:
    """Italique systématique pour la plupart des règnes
    (algue/archaea/bactérie/champignon/végétal/virus/procaryote/neutre), sinon dépend du
    rang (italique seulement à partir du rang espèce et en dessous, comme en zoologie)."""
    if regne not in DOMAINES_SANS_ITALIQUE_SYSTEMATIQUE:
        return True
    inf = wp_inf_rang(rang, table)
    return bool(inf) if inf != "NOTFOUND" else False


# Segments d'un nom scientifique qui doivent rester (ou passer) en italique séparément du nom
# lui-même (abréviations de rang infraspécifique, marqueurs d'hybride, etc.).
#
# Bug latent, conservé tel quel plutôt que "corrigé" sans certitude du comportement voulu :
# les motifs à espace de tête (" var[.]",
# " sp[.]", " f[.]", " gen[.]", " ord[.]", " fam[.]", " sect[.]", " ser[.]", " tr[.]",
# " cl[.]") sont enveloppés dans \b...\b. Le \b de fin échoue quand le motif est suivi d'un
# espace (cas normal d'usage, ex. "var. macrocarpum") car un point suivi d'un espace ne
# constitue pas une frontière de mot (les deux caractères sont non-alphanumériques) — la
# substitution ne se déclenche donc quasiment jamais pour ces entrées précises en pratique.
_EXCLUSIONS: list[tuple[str, str]] = [
    (r" cl[.]", " ''cl.''"), (r"convar[.]", "''convar.''"), (r"f[.]sp[.]", "''f.sp.''"),
    (r" f[.]", " ''f.''"), (r" gen[.]", " ''gen.''"), (r"kl[.]", "''kl.''"),
    (r"nothog[.]", "''nothog.''"), (r"nothosp[.]", "''nothosp.''"), (r"nothovar[.]", "''nothovar.''"),
    (r" ord[.]", " ''ord.''"), (r" fam[.]", " ''fam.''"), (r" sect[.]", " ''sect.''"),
    (r" ser[.]", " ''ser.''"), (r" sp[.]", " ''sp.''"), (r"subg[.]", "''subg.''"),
    (r"subsp[.]", "''subsp.''"), (r"Groupe", "''Groupe''"), (r" tr[.]", " ''tr.''"),
    (r" var[.]", " ''var.''"), (r"×", "''×''"), (r"[(]", "''(''"), (r"[)]", "'')''"),
    (r"pv", "''pv''"), (r"pathovar", "''pathovar''"), (r"morphovar", "''morphovar''"),
    (r"phagovar", "''phagovar''"), (r"serovar", "''serovar''"), (r"chemovar", "''chemovar''"),
    (r"cultivar", "''cultivar''"), (r"chemoform", "''chemoform''"), (r"chemotype", "''chemotype''"),
    (r"morphotype", "''morphotype''"), (r"pathotype", "''pathotype''"), (r"phagotype", "''phagotype''"),
    (r"lysotype", "''lysotype''"), (r"phase", "''phase''"), (r"serotype", "''serotype''"),
    (r"state", "''state''"), (r"forma specialis", "''forma specialis''"),
]
_EXCLUSIONS_COMPILED = [(re.compile(r"\b" + pattern + r"\b"), repl) for pattern, repl in _EXCLUSIONS]


def wp_met_italiques(
    taxon: str,
    rang: str,
    regne: str,
    lien: bool = False,
    souslien: bool = True,
    table: RankTable | None = None,
) -> str:
    """Génère en wikicode un nom scientifique avec gestion des italiques. Un `taxon` vide/None
    est une erreur de programmation (ValueError) : ce n'est pas un cas qui peut arriver en
    usage normal, et une exception explicite est préférable à un message d'erreur rendu
    silencieusement dans l'article."""
    if not taxon:
        raise ValueError("wp_met_italiques() nécessite un 'taxon' non vide.")

    if not wp_est_italique(rang, regne, table):
        return f"[[{taxon}]]" if lien else taxon

    ref = taxon
    modifie = taxon
    for pattern, repl in _EXCLUSIONS_COMPILED:
        modifie = pattern.sub(repl, modifie)

    if modifie == ref:
        if lien:
            return f"''[[{taxon}]]''"
        return f"''{taxon}''" if souslien else taxon

    if lien:
        return f"[[{ref}|''{modifie}'']]"
    return f"''{modifie}''" if souslien else modifie


# Tables associatives par règne (liens vers les pages de convention Wikipédia).
LIEN_AUTEURS: dict[str, str] = {
    "algue": "Citation d'auteurs en botanique",
    "animal": "Citation d'auteurs en zoologie",
    "reptile": "Citation d'auteurs en zoologie",
    "amphibien": "Citation d'auteurs en zoologie",
    "archaea": "Citation d'auteurs en bactériologie",
    "bactérie": "Citation d'auteurs en bactériologie",
    "champignon": "Citation d'auteurs en botanique",
    "protiste": "Citation d'auteurs en zoologie",
    "végétal": "Citation d'auteurs en botanique",
    "virus": "Auteur#Dans les sciences et techniques",
    "neutre": "Auteur#Dans les sciences et techniques",
    "eucaryote": "Auteur#Dans les sciences et techniques",
    "procaryote": "Citation d'auteurs en bactériologie",
}


def lien_pour_auteur(regne: str) -> str:
    return LIEN_AUTEURS.get(regne, "Auteur#Dans les sciences et techniques")


LIEN_BASIONYME: dict[str, str] = {
    "algue": "[[basionyme]]",
    "animal": "[[protonyme]]",
    "reptile": "[[protonyme]]",
    "amphibien": "[[protonyme]]",
    "archaea": "[[basionyme]]",
    "bactérie": "[[basonyme]]",
    "champignon": "[[basionyme]]",
    "protiste": "[[basonyme]]",
    "végétal": "[[basionyme]]",
    "virus": "[[basonyme]]",
    "neutre": "[[basionyme]]",
    "eucaryote": "[[basionyme]]",
    "procaryote": "[[basionyme]]",
}


def lien_pour_basionyme(regne: str) -> str:
    return LIEN_BASIONYME.get(regne, "[[basionyme]]")


CATEGORIE_PAR_REGNE: dict[str, str] = {
    "algue": "Algue (nom scientifique)",
    "animal": "Animal (nom scientifique)",
    "reptile": "Animal (nom scientifique)",
    "amphibien": "Animal (nom scientifique)",
    "archaea": "Archée (nom scientifique)",
    "bactérie": "Bactérie (nom scientifique)",
    "champignon": "Champignon (nom scientifique)",
    "protiste": "Protiste (nom scientifique)",
    "végétal": "Plante (nom scientifique)",
    "virus": "",
    "neutre": "",
    "eucaryote": "Eucaryote (nom scientifique)",
    "procaryote": "",
}

SYNONYME_PAR_REGNE: dict[str, str] = {
    "algue": "Synonyme (taxinomie)",
    "animal": "Synonyme (zoologie)",
    "reptile": "Synonyme (zoologie)",
    "amphibien": "Synonyme (zoologie)",
    "archaea": "Synonyme (taxinomie)",
    "bactérie": "Synonyme (taxinomie)",
    "champignon": "Synonyme (botanique)",
    "protiste": "Synonyme (taxinomie)",
    "végétal": "Synonyme (botanique)",
    "virus": "Synonyme (taxinomie)",
    "neutre": "Synonyme (taxinomie)",
    "eucaryote": "Synonyme (taxinomie)",
    "procaryote": "Synonyme (taxinomie)",
}


def lien_pour_synonyme(regne: str) -> str:
    return SYNONYME_PAR_REGNE.get(regne, "Synonyme (taxinomie)")


EBAUCHE_PAR_REGNE: dict[str, str] = {
    "algue": "algue",
    "animal": "zoologie",
    "reptile": "reptile",
    "amphibien": "amphibien",
    "archaea": "biologie",
    "bactérie": "bactérie",
    "champignon": "champignon",
    "protiste": "protiste",
    "végétal": "botanique",
    "virus": "virus",
    "neutre": "biologie",
    "eucaryote": "biologie",
    "procaryote": "biologie",
}

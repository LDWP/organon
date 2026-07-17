"""Petites fonctions utilitaires de rendu : date du jour en français ("consulté le"), mise en
colonnes des longues listes, dédoublonnage/mise en forme des noms vernaculaires, formatage
« et al. », table des pays, désambiguïsation d'homonymes.

`format_auteur` reste une version simplifiée (et al. uniquement), utilisée pour les auteurs de
synonymes/sous-taxons/basionyme ; le système complet de résolution par listes de
botanistes/zoologistes/procaryotes connus, appliqué uniquement à l'auteur du taxon principal,
vit dans `organon.core.rendering.authors`.
"""

from __future__ import annotations

import datetime
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

from organon.core.config import GenerateOptions

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

MOIS_FR = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
    7: "juillet", 8: "août", 9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
}


def dates_recupere(today: datetime.date | None = None) -> str:
    """Date du jour formatée en français, ex. "9 juillet 2026"."""
    jour = today or datetime.date.today()
    return f"{jour.day} {MOIS_FR[jour.month]} {jour.year}"


_ET_AL_RE = re.compile(r"([^{])et al[.]")


def rempl_et_al(txt: str) -> str:
    """Remplace "et al." par le modèle {{et al.}}, sans doubler si déjà fait."""
    if "{{et al.}}" in txt:
        return txt
    return _ET_AL_RE.sub(r"\1{{et al.}}", txt)


def format_auteur(auteur: str | None) -> str:
    """Traitement simplifié d'une citation d'auteur : uniquement le remplacement
    "et al." -> {{et al.}} (voir docstring du module pour le système complet)."""
    if not auteur:
        return ""
    return rempl_et_al(auteur)


@lru_cache(maxsize=1)
def load_homonymes() -> dict[str, dict[str, str]]:
    with (DATA_DIR / "homonymes.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def cherche_homonyme(nom: str, regne: str) -> tuple[bool, str | None]:
    """Cherche `nom` dans la table d'homonymes, d'abord par règne, puis par la clé générique
    `*`, puis par `hom` (page d'homonymie à corriger manuellement — indique alors
    `page_est_homonymie=True`). Renvoie `(False, None)` si `nom` n'est pas dans la table."""
    entree = load_homonymes().get(nom)
    if entree is None:
        return False, None
    if regne in entree:
        return False, entree[regne]
    if regne != "*" and "*" in entree:
        return False, entree["*"]
    if "hom" in entree:
        return True, entree["hom"]
    return False, None


def est_colonnes(nombre: int, options: GenerateOptions) -> bool:
    """seuil_colonnes == -1 -> jamais, == 0 -> toujours, sinon active la mise en colonnes
    au-delà du seuil."""
    if options.seuil_colonnes == -1:
        return False
    if options.seuil_colonnes == 0:
        return True
    return nombre > options.seuil_colonnes


def colonnes_contenu(contenu: str) -> str:
    return "{{colonnes|taille=25|1=\n" + contenu + "}}\n"


def _sans_accents(mot: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", mot) if not unicodedata.combining(c))


def _nb_accents(mot: str) -> int:
    """Nombre de diacritiques portés par `mot`, pour départager deux graphies "similaires"
    (voir est_similaire) qui ne diffèrent que par l'accentuation, ex. "Eléphant d'Afrique" vs
    "Éléphant d'Afrique" — certaines sources n'accentuent pas les majuscules alors que l'usage
    français les accentue."""
    return sum(1 for c in unicodedata.normalize("NFD", mot) if unicodedata.combining(c))


def est_similaire(mot_1: str, mot_2: str) -> bool:
    """Compare deux mots en ignorant la casse, les tirets et les accents."""
    normalise = lambda m: _sans_accents(m.lower().replace("-", " "))
    return normalise(mot_1) == normalise(mot_2)


def _decoupe_nom(nom: str) -> list[str]:
    """Scinde un nom vernaculaire sur les virgules internes : certaines sources (ex. EOL)
    renvoient parfois plusieurs noms concaténés dans un seul champ, ex. "cabillaud, morue"."""
    return [n.strip() for n in nom.split(",") if n.strip()]


def _renomme_cle(liste: dict[str, list[str]], ancienne: str, nouvelle: str) -> None:
    """Remplace la clé `ancienne` par `nouvelle` dans `liste` en conservant sa position et son
    contenu (un simple pop/réassignation déplacerait l'entrée en fin de dict)."""
    reconstruit = {nouvelle if k == ancienne else k: v for k, v in liste.items()}
    liste.clear()
    liste.update(reconstruit)


def ajoute_si_besoin(liste: dict[str, list[str]], el: str, src: str) -> None:
    """Ajoute `el` (avec sa source `src`) à `liste` en dédupliquant les entrées "similaires"
    (voir est_similaire) et en accumulant les sources pour un même nom déjà présent. `el` est
    d'abord scindé sur les virgules internes (voir _decoupe_nom). Entre deux graphies
    similaires, la plus accentuée est conservée comme forme d'affichage."""
    for nom in _decoupe_nom(el):
        _ajoute_nom_unique(liste, nom, src)


def _ajoute_nom_unique(liste: dict[str, list[str]], el: str, src: str) -> None:
    trouve = None
    for nom in liste:
        if est_similaire(el, nom):
            trouve = nom
            break
    if trouve is None:
        liste[el] = [src]
        return
    if _nb_accents(el) > _nb_accents(trouve):
        _renomme_cle(liste, trouve, el)
        trouve = el
    if src in liste[trouve]:
        return
    liste[trouve].append(src)


def conditionne_noms(vernaculaire: dict[str, list[str]], cdate: str) -> tuple[str, int]:
    """Fusionne/déduplique les noms vernaculaires toutes sources confondues et les met en
    forme avec sourçage Bioref par nom. Retourne (texte, nombre de noms distincts)."""
    if not vernaculaire:
        return "", 0

    liste: dict[str, list[str]] = {}
    for src, noms in vernaculaire.items():
        for nom in noms:
            ajoute_si_besoin(liste, nom, src)

    cnt = len(liste)
    out = []
    for nom, refs in liste.items():
        refs_txt = "{{,}}".join(f"{{{{Bioref|{r}|{cdate}|ref}}}}" for r in refs)
        out.append(nom + refs_txt)
    return ", ".join(out), cnt


@lru_cache(maxsize=1)
def load_countries() -> dict[str, dict[str, str]]:
    with (DATA_DIR / "countries.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def data_pays_code(code: str) -> str:
    """Renvoie un wikilien [[nom réel]] ou [[nom réel|texte affiché]] pour un code pays ISO.
    Retourne le code tel quel (non lié) si inconnu, plutôt que planter, puisque certaines
    sources tierces renvoient des codes hors-ISO-3166 (régions, eaux internationales, etc.)
    qui n'ont pas de page Wikipédia correspondante."""
    countries = load_countries()
    entry = countries.get(code)
    if entry is None:
        return code
    if entry["texte_affiche"] == entry["nom_page"]:
        return f"[[{entry['nom_page']}]]"
    return f"[[{entry['nom_page']}|{entry['texte_affiche']}]]"

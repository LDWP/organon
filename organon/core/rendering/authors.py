"""Système de wikification de la citation d'auteur du taxon principal : découpage de la
chaîne brute sur séparateurs/mots-clés, wikification des années, résolution des auteurs
connus via trois tables générées par `scripts/build_auteurs_yaml.py` (botanistes/champignons,
procaryotes, zoologistes — voir ce script pour les sources), et enveloppement
`{{auteur|[[Nom]]}}` pour tout nom non résolu.

N'est appelé qu'une seule fois par génération, sur `struct.taxon.auteur` uniquement — jamais
sur les auteurs de synonymes/sous-taxons/basionyme (qui gardent le traitement simple de
`organon.modules.common.format_auteur`).

Un seul point de rendu affiche ce résultat wikifié : la ligne `{{Taxobox taxon}}`
(`sections.py::render_taxobox`). La phrase "== Systématique ==" et les autres usages
secondaires (synonymes, basionyme, sous-taxons) sont indépendants : ils appliquent leur propre
remplacement "et al." basique directement sur l'auteur brut, sans passer par ce module — les
deux traitements ne partagent pas leur résultat, à ne pas fusionner par erreur (un
`{{date à préciser}}` dupliqué dans les deux sections d'un article généré est le symptôme
caractéristique d'une telle fusion involontaire).

**Botanique/champignons** : résolution par abréviation exacte dans `auteurs_botanistes.yaml`.
Une entrée marquée `conflit: true` (désaccord entre la liste Wikipédia et Wikidata P428,
détecté par `scripts/build_auteurs_yaml.py`) n'est **pas** résolue silencieusement : elle reste
enveloppée dans `{{auteur}}`, avec un avertissement listant les deux cibles — conforme au
principe WP:Proportion déjà retenu pour la Phase 3.

**Procaryotes** (bactérie/archaea) : résolution par abréviation dans `auteurs_procaryotes.yaml`.

**Zoologie** : la zoologie n'utilise pas d'abréviation d'auteur (contrairement à la
botanique) ; la résolution se fait par nom de famille complet dans
`auteurs_zoologistes.yaml`, désambiguïsé par une fenêtre de dates si plusieurs zoologistes
partagent ce nom.

**Virus** : aucune résolution tentée, mais le reste du traitement (dates, `{{auteur}}`)
s'applique tout de même."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from organon.core.models import Struct

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

BOTANIST_REGNES = {"végétal", "champignon"}
PROCARYOTE_REGNES = {"bactérie", "archaea"}
NO_RESOLUTION_REGNES = {"virus"}

_YEAR_RE = re.compile(r"^(1[3-9]\d\d|20\d\d)$")

_SPECIAL_WORD_RE = re.compile(
    r"(?<![\w'])(et al\.|and|emend\.|et non|nom\. nov\.|nom\. cons\.|corrig\.|ex\.|ex|in\.|in)(?![\w'])",
    re.IGNORECASE,
)
_SPECIAL_NORMALIZE = {"and": "&", "et al.": "{{et al.}}"}
_PUNCT_RE = re.compile(r"([,&;:()\[\]])")


@lru_cache(maxsize=1)
def _load(name: str) -> dict:
    path = DATA_DIR / name
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _load_botanistes() -> dict:
    return _load("auteurs_botanistes.yaml")


def _load_procaryotes() -> dict:
    return _load("auteurs_procaryotes.yaml")


def _load_zoologistes() -> dict:
    return _load("auteurs_zoologistes.yaml")


def _tokenize(text: str) -> list[tuple[str, str]]:
    """Découpe en tokens `(type, texte)`, `type` valant `'sep'` (ponctuation ou mot-clé) ou
    `'cur'` (reste à résoudre) — version pragmatique de `aut_analyse()` : ponctuation *et*
    mots-clés reconnus deviennent des séparateurs, le reste reste à résoudre."""
    tokens: list[tuple[str, str]] = []
    parts = _SPECIAL_WORD_RE.split(text)
    for i, part in enumerate(parts):
        if not part:
            continue
        if i % 2 == 1:  # mot-clé capturé par le groupe de _SPECIAL_WORD_RE
            tokens.append(("sep", _SPECIAL_NORMALIZE.get(part.lower(), part)))
            continue
        for piece in _PUNCT_RE.split(part):
            if piece == "":
                continue
            if _PUNCT_RE.fullmatch(piece):
                tokens.append(("sep", piece))
            else:
                tokens.append(("cur", piece))
    return tokens


def _dates_window(dates: str) -> tuple[int, int] | None:
    """Convertit une chaîne de dates (ex. "1707-1778", "fl. 1990", "1950-…", "?-?") en fenêtre
    de désambiguïsation `(début, fin)`, fidèle à `identifie_auteur()` : naissance+15 -> mort+10
    si les deux sont connues ; ±10 ans autour d'une date d'activité seule ; naissance+15 ->
    naissance+70 si seule la naissance est connue ; mort-70 -> mort+10 si seule la mort l'est."""
    m = re.match(r"^\s*(\d{4})\s*-\s*(\d{4})\s*$", dates)
    if m:
        naissance, mort = int(m.group(1)), int(m.group(2))
        return naissance + 15, mort + 10
    m = re.match(r"^\s*(\d{4})\s*-\s*[…\.]*\s*$", dates)
    if m:
        naissance = int(m.group(1))
        return naissance + 15, naissance + 70
    m = re.search(r"fl\.\s*(\d{4})", dates)
    if m:
        activite = int(m.group(1))
        return activite - 10, activite + 10
    m = re.match(r"^\s*\?\s*-\s*(\d{4})\s*$", dates)
    if m:
        mort = int(m.group(1))
        return mort - 70, mort + 10
    return None


def _lookup_normalise(table: dict, token: str) -> dict | None:
    """Essaie la clé exacte, puis une variante sans espace après un point (ex. "A. DC." vs
    "A.DC.") — une variance de formatage courante entre une chaîne de citation "en clair" et la
    forme figée de la table (pas une résolution floue par ressemblance, juste une normalisation
    de ponctuation)."""
    entry = table.get(token)
    if entry is not None:
        return entry
    return table.get(re.sub(r"\.\s+", ".", token))


def _resolve_botaniste(token: str) -> tuple[str | None, dict | None]:
    entry = _lookup_normalise(_load_botanistes(), token)
    if entry is None:
        return None, None
    if entry.get("conflit"):
        return None, entry
    return f"[[{entry['cible']}|{token}]]", None


def _resolve_procaryote(token: str) -> str | None:
    entry = _lookup_normalise(_load_procaryotes(), token)
    if entry is None:
        return None
    return f"[[{entry['cible']}|{token}]]"


def _resolve_zoologiste(token: str, annee: int | None) -> str | None:
    candidats = _load_zoologistes().get(token)
    if not candidats:
        return None
    if len(candidats) == 1:
        return f"[[{candidats[0]['cible']}]]"
    if annee is None:
        return None
    matches = []
    for c in candidats:
        fenetre = _dates_window(c.get("dates", ""))
        if fenetre is not None and fenetre[0] <= annee <= fenetre[1]:
            matches.append(c)
    if len(matches) == 1:
        return f"[[{matches[0]['cible']}]]"
    return None


def resoudre_auteur_principal(struct: Struct) -> tuple[str, list[str]]:
    """Point d'entrée unique. Renvoie `(texte_wikifie, avertissements)` — `avertissements` liste
    les cas de désaccord Wikipédia/Wikidata rencontrés, à ajouter à `GenerateResponse.warnings`
    par l'appelant plutôt que gérés ici (cette fonction ne connaît pas la réponse API)."""
    auteur = (struct.taxon.auteur or "").strip()
    if not auteur:
        return "", []

    regne = struct.regne
    tokens = _tokenize(auteur)

    annee: int | None = None
    resolus: list[tuple[str, str]] = []  # (type, texte) — type: 'sep' | 'nom' | 'date'
    avertissements: list[str] = []

    # première passe : repère l'année (utile à la désambiguïsation zoologiste par date)
    for kind, texte in tokens:
        if kind == "cur" and _YEAR_RE.match(texte.strip()):
            annee = int(texte.strip())
            break

    for kind, texte in tokens:
        if kind == "sep":
            resolus.append(("sep", texte))
            continue
        stripped = texte.strip()
        if not stripped:
            if texte:
                resolus.append(("sep", ""))  # préserve un espace isolé
            continue
        if _YEAR_RE.match(stripped):
            resolus.append(("date", f"[[{stripped} en science|{stripped}]]"))
            continue

        resolu: str | None = None
        if regne in BOTANIST_REGNES:
            resolu, conflit = _resolve_botaniste(stripped)
            if conflit is not None:
                avertissements.append(
                    f"Auteur « {stripped} » : désaccord entre la liste Wikipédia "
                    f"({conflit['cible']}) et Wikidata ({conflit.get('wikidata_libelle')}) — "
                    "non résolu automatiquement, à trancher manuellement."
                )
        elif regne in PROCARYOTE_REGNES:
            resolu = _resolve_procaryote(stripped)
        elif regne not in NO_RESOLUTION_REGNES:
            resolu = _resolve_zoologiste(stripped, annee)

        if resolu is not None:
            resolus.append(("nom", resolu))
        else:
            resolus.append(("nom", f"{{{{auteur|[[{stripped}]]}}}}"))

    texte = _render_tokens(resolus)
    if annee is None:
        texte += " {{date à préciser}}"
    return texte, avertissements


_NO_SPACE_BEFORE = {",", ";", ":", ")", "]"}
_NO_SPACE_AFTER = {"(", "["}


def _render_tokens(tokens: list[tuple[str, str]]) -> str:
    out = ""
    for kind, texte in tokens:
        if not texte:
            continue
        if kind == "sep" and texte in _NO_SPACE_BEFORE:
            out = out.rstrip() + texte + " "
            continue
        if kind == "sep" and texte in _NO_SPACE_AFTER:
            out = out.rstrip() + " " + texte
            continue
        if out and not out.endswith((" ", "(", "[")):
            out += " "
        out += texte
    return re.sub(r" {2,}", " ", out).strip()

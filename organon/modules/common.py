"""Utilitaires partagés entre les adaptateurs de modules (organon.modules.*), pour éviter de
dupliquer les mêmes motifs dans chaque module.py : pagination REST avec troncature
(`limite-listes`), lien de debug vers la fiche source, formatage d'auteur, garde-fou
anti-boucle de synonymes. Rien ici ne fait d'appel réseau — ce sont des fonctions pures ou des
wrappers fins au-dessus de callbacks fournis par chaque module."""

from __future__ import annotations

import html as _html
import re
from collections.abc import Awaitable, Callable

from organon.core.models import Struct
from organon.core.rendering.support import rempl_et_al

MAX_SYNONYM_HOPS = 10
"""Garde-fou contre une boucle infinie si deux taxons se référencent l'un l'autre comme
synonyme accepté, appliqué par tous les modules qui suivent des synonymes (voir `hop` dans
chaque `collect()`)."""


async def collect_pages(
    fetch_page: Callable[[int], Awaitable[tuple[list, int, bool]]],
    start_offset: int = 0,
    limit: int | None = None,
) -> tuple[list, bool]:
    """Agrège toutes les pages d'un endpoint paginé. `fetch_page(offset)` doit renvoyer
    `(éléments retenus de cette page, taille brute de la page lue côté source, est-ce la
    dernière page ?)`. La taille brute est distincte du nombre d'éléments retenus dès qu'un
    appelant filtre certains enregistrements avant de les renvoyer (ex. rang non pertinent,
    statut non accepté) : avancer l'offset sur le compte filtré ferait rechevaucher la page
    suivante avec la fin de celle-ci côté source, dupliquant les enregistrements de la zone de
    chevauchement. `start_offset` s'adapte aux deux conventions rencontrées : 0 (GBIF, index du
    premier élément) ou 1 (WoRMS, numéro du premier enregistrement) ; le pas suivant est déduit
    de la taille brute reçue.

    `limit` porte l'option `limite-listes` : si fourni, la pagination s'arrête dès que ce
    nombre est dépassé plutôt que de récupérer des pages inutiles pour une liste tronquée de
    toute façon (un genre à des centaines d'espèces peut nécessiter un appel réseau par
    espèce — s'arrêter tôt évite un ralentissement inutile). Renvoie `(éléments, coupée ?)`."""
    items: list = []
    offset = start_offset
    while True:
        if limit is not None and len(items) > limit:
            return items[:limit], True
        page_items, raw_count, done = await fetch_page(offset)
        items.extend(page_items)
        offset += raw_count
        if done or not raw_count:
            break
    return items, False


def as_limit(options_value: int) -> int | None:
    """Convertit `GenerateOptions.limite_listes` (convention : <=0 signifie "pas de limite")
    vers le paramètre `limit` de `collect_pages` (convention : `None` signifie "pas de
    limite"). Piège évité : `options_value or None` renverrait `-1` telle quelle (`-1` est
    vraie en Python), pas `None`."""
    return options_value if options_value > 0 else None


def format_auteur(auteur: str | None) -> str | None:
    """Applique le remplacement `et al.` -> `{{et al.}}` à une chaîne d'auteur (voir
    `core.rendering.support.rempl_et_al`), à appliquer systématiquement partout où un module
    écrit un auteur dans `Struct` (taxon, rangs, synonymes, basionyme…). Renvoie `None` pour
    une entrée vide plutôt qu'une chaîne vide, pour rester compatible avec les champs
    optionnels des modèles Pydantic."""
    if not auteur:
        return None
    return rempl_et_al(auteur)


def format_auteur_annee(authors: str | None, year: str | int | None) -> str | None:
    """Concatène auteur + année en `"Auteur, Année"`, pour les sources dont l'API expose
    l'année de publication dans un champ séparé de la citation d'auteur — le cas des codes de
    nomenclature qui ne l'incluent pas par convention (ICN botanique/champignons ; à distinguer
    de l'ICZN zoologique et de l'ICNP bactérien, qui l'incluent déjà nativement dans la chaîne
    d'auteur). `resoudre_auteur_principal` (`core/rendering/authors.py`) sait déjà extraire un
    token année terminal quel que soit le règne — seule l'absence de ce suffixe empêchait la
    date d'apparaître dans la taxobox botanique (discussion Projet:Biologie/Organon #33).
    N'applique aucun remplacement `et al.` : passer le résultat à `format_auteur` comme pour
    tout autre auteur brut."""
    authors = authors or ""
    if year:
        authors = f"{authors}, {year}" if authors else str(year)
    return authors or None


_ORIGINAL_DESCRIPTION_FIELD_RE = re.compile(
    r'id="OriginalDescription"[^>]*>(?P<block>.*?)for="', re.DOTALL
)
_CORRECT_HTML_SPAN_RE = re.compile(r"correctHTML['\"]>(?P<texte>.*?)</span>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def extract_aphia_original_description(html_page: str) -> str | None:
    """Extrait le champ « Original description » d'une page de détail Aphia/VLIZ
    (`aphia.php?p=taxdetails&id=...`), plateforme partagée par WoRMS et IRMNG. Aucun champ REST
    équivalent n'existe (voir `wrms/module.py`/`irmng/module.py`) — seul ce champ précis reste
    scrapé, le reste des deux modules utilise l'API REST.

    Le motif ciblé (`id="OriginalDescription"`, contenu dans un `<span class='correctHTML'>`)
    est le même sur les deux sites (vérifié en direct). Aucun marqueur de fin de bloc fiable
    n'existe dans le HTML actuel des deux plateformes : la zone est donc bornée par le `for="`
    du champ suivant (`DescriptiveNotes` ou équivalent), présent des deux côtés. Seule la
    première citation trouvée est gardée (une seconde entrée "(of <nom> ...)" peut suivre pour
    un renvoi de sous-taxon/synonyme, hors-sujet ici). Renvoie `None` si le champ est absent ou
    vide (ex. "Not documented", cas réel observé sur IRMNG)."""
    field_match = _ORIGINAL_DESCRIPTION_FIELD_RE.search(html_page)
    if field_match is None:
        return None
    span_match = _CORRECT_HTML_SPAN_RE.search(field_match.group("block"))
    if span_match is None:
        return None
    texte = _TAG_RE.sub("", span_match.group("texte"))
    # Le titre d'ouvrage est stocké échappé (ex. "&lt;i&gt;Systema Naturae...&lt;/i&gt;") : une
    # fois décodé, ce sont des balises <i>/</i> réelles à convertir en italique wikitexte plutôt
    # que laissées en HTML brut (même convention que le champ "originale" d'AlgaeBase, voir
    # `organon/modules/algaebase/module.py`).
    texte = _html.unescape(texte).replace("<i>", "''").replace("</i>", "''").strip()
    return texte or None


def filter_ancestors_above_regne(
    chain: list[dict], regne_nom: str, garder_regne: bool
) -> list[dict]:
    """Coupe une chaîne d'ancêtres (racine -> feuille, nom sous la clé `scientificname`) à
    hauteur du règne : tout nœud au règne ou au-dessus (domaine, super-domaine, `Biota`...) est
    écarté, quel que soit le rang que la source lui déclare (`Superdomain`, `Kingdom`,
    `Clade`...) — seule la position dans l'arbre, repérée par le nom de règne déjà connu
    (`regne_nom`, ex. `cur["kingdom"]`), fait foi. Partagé par WoRMS et IRMNG (même plateforme
    Aphia, même forme d'arbre imbriqué — voir `_flatten_classification` dans chaque module.py).
    Si `regne_nom` n'apparaît dans aucun nœud (cas non rencontré en pratique), la chaîne est
    renvoyée telle quelle. `garder_regne` réintroduit le nœud du règne lui-même (algue/protiste,
    voir CHARTES_GARDENT_REGNE)."""
    boundary = next(
        (i for i, node in enumerate(chain) if node.get("scientificname") == regne_nom), None
    )
    if boundary is None:
        return chain
    reste = chain[boundary + 1 :]
    return [chain[boundary], *reste] if garder_regne else reste


def sparql_escape(value: str) -> str:
    """Échappe une chaîne pour l'insérer dans un littéral SPARQL entre guillemets doubles
    (`"..."`). Backslash d'abord : sinon le remplacement du guillemet ajouté à l'étape suivante
    serait lui-même ré-échappé, laissant un backslash final non échappé capable de faire fusionner
    le guillemet fermant du littéral avec le premier caractère de `value` (injection — un `taxon`
    terminé par `\\` casse la chaîne). Saut de ligne/retour chariot ensuite : un littéral SPARQL
    sur une ligne ne peut pas contenir de saut de ligne brut, qui le terminerait prématurément."""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def simple_debug_link(struct: Struct, module_id: str, url_template: str, label: str) -> str | None:
    """Lien brut vers la fiche du taxon sur le site source, construit à partir de
    l'identifiant stocké dans `struct.liens[module_id]['id']`. `url_template` utilise `{id}`
    comme point d'insertion, ex. `"https://www.gbif.org/species/{id}"`."""
    data = struct.liens.get(module_id)
    if not data or "id" not in data:
        return None
    url = url_template.format(id=data["id"])
    return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>{label}</a>"

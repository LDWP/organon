"""Résolution allégée de l'identifiant ChecklistBank (Catalogue of Life Extended Release,
dataset 3LXR) correspondant à un nom déjà résolu par ailleurs — utilisée uniquement par
`organon/modules/gbif/module.py` pour son propre lien {{GBIF}} (accepté par Modèle:GBIF réformé,
voir gbif.org/taxon/{id}) et un second lien {{CatalogueofLife}}. Distincte de
`organon.modules.col_xr.module.ColXrModule`, la classification COL XR à part entière
(`can_classify=True`) : les deux référentiels peuvent diverger (voir sa docstring), ce lookup ne
sert que d'identifiant d'affichage pour la classification déjà retenue par GBIF, jamais à piloter
une classification.

Ne fait aucun appel HTTP directement, voir adapter.py."""

from __future__ import annotations

import re
from dataclasses import dataclass

from organon.core.domains import regne_depuis_classification
from organon.modules.col_xr.adapter import ColXrAdapter
from organon.modules.col_xr.ranks import col_xr_cherche_rang
from organon.modules.common import format_auteur


@dataclass
class ColXrLinkInfo:
    """Nom/auteur/rang tels que COL XR les rapporte pour la fiche `id` — mêmes champs que ceux
    que `ColModule` calcule pour `struct.liens["col"]` (voir col/module.py), pour que le lien
    {{CatalogueofLife}} construit par GbifModule à partir de cette fiche cite le même auteur que
    ColModule citerait pour la même fiche, plutôt que l'auteur GBIF (backbone), qui peut différer
    ou manquer — sans quoi les deux lignes ne sont pas des doublons textuellement identiques et le
    dédoublonnage par ligne de `_compute_ext_liens_items` (sections.py) ne les fusionne pas."""

    id: str
    nom: str
    auteur: str | None
    rang: str | None
    eteint: bool | None
    classification: dict[str, str]
    """Rang WP (`col_xr_cherche_rang`) -> nom, pour chaque ancêtre de la fiche `id` — sert à
    `organon.modules.gbif.module` à combler un rang absent de sa propre réponse (ex. `order`,
    souvent manquant chez GBIF pour les reptiles non-aviens) sans appel réseau supplémentaire,
    cette classification étant déjà incluse dans la réponse de recherche ChecklistBank ci-dessus."""


def _regne_correspond(r: dict, domaine: str) -> bool:
    if domaine in ("*", ""):
        return True
    return regne_depuis_classification(r.get("classification", [])) == domaine


def _rank_name(classification: list[dict], rank: str) -> str:
    return next((c.get("name", "") for c in classification if c.get("rank") == rank), "")


_CODES_EUCARYOTES_SEULEMENT = {
    # ICNafp (botanique, couvre aussi algues/champignons) et ICZN (zoologique, couvre aussi une
    # bonne part des protistes historiquement traités comme des "animaux") ne s'appliquent à
    # aucun procaryote : un enregistrement de ce code sur le domaine Bacteria/Archaea est une
    # incohérence interne, jamais un simple désaccord de classification.
    "botanical",
    "zoological",
}
_REGNES_INCOMPATIBLES_BOTANICAL = {"Animalia"}
_REGNES_INCOMPATIBLES_ZOOLOGICAL = {"Plantae", "Viridiplantae", "Fungi"}
_DOMAINES_PROCARYOTES = {"Bacteria", "Archaea"}


def _code_incoherent(r: dict) -> bool:
    """Un enregistrement ChecklistBank dont le code nomenclatural (`usage.name.code` :
    botanical/zoological/bacterial/...) contredit son propre règne ou domaine déclaré est un
    signe fiable de fiche mal fusionnée dans 3LXR — typiquement un traitement Plazi (extraction
    automatique de texte scientifique) issu d'un article sans rapport, absorbé comme fiche
    "acceptée" d'un taxon homonyme lors de la fusion des ~17 500 checklists sources — plutôt
    qu'un vrai désaccord taxonomique entre deux checklists sérieuses. Repéré lors de l'audit
    Escherichia coli (VB8KH : botanical sur un règne autrement cohérent Plantae, donc non détecté
    ici — exclu par `_regne_correspond` quand le règne cible est connu ; NT3L7 : botanical sur
    domaine Bacteria, détecté ici) et Toxoplasma gondii (VBKRN : botanical sur règne Animalia,
    détecté ici)."""
    code = r["usage"]["name"].get("code")
    if code not in _CODES_EUCARYOTES_SEULEMENT and code != "bacterial":
        return False
    classification = r.get("classification", [])
    kingdom = _rank_name(classification, "kingdom")
    domain = _rank_name(classification, "domain")
    if code == "botanical":
        return kingdom in _REGNES_INCOMPATIBLES_BOTANICAL or domain in _DOMAINES_PROCARYOTES
    if code == "zoological":
        return kingdom in _REGNES_INCOMPATIBLES_ZOOLOGICAL or domain in _DOMAINES_PROCARYOTES
    return domain == "Eukaryota"  # code == "bacterial" sur un eucaryote


_SUBGENUS_RE = re.compile(r"\s*\([^)]*\)")
_LATIN_GENDER_ENDINGS = ("us", "a", "um")


def _strip_subgenus(nom: str) -> str:
    """Retire le sous-genre entre parenthèses ("Mus (Mus) musculus" -> "Mus musculus"), pour
    comparer un nom binomial à la notation trinomiale que ChecklistBank utilise pour certaines
    fiches (rongeurs, moustiques, Drosophila, Plasmodium...) sans que `type=EXACT` ne les
    reconnaisse comme correspondant au binôme demandé."""
    return _SUBGENUS_RE.sub("", nom).strip()


def _latin_gender_variants(nom: str) -> list[str]:
    """Variantes d'accord de genre latin (-us/-a/-um) sur le dernier mot de `nom`, pour
    retrouver un binôme dont l'épithète a été corrigée entre deux sources qui ne republient pas
    en même temps (ex. Macrovipera lebetina, encore utilisée par GBIF, vs lebetinus, la forme
    adoptée par COL XR après correction nomenclaturale). Repli de dernier recours seulement
    (voir `resolve_col_xr_matches`) : ne couvre qu'un désaccord de terminaison sur le tout
    dernier mot, pas une recherche floue générale."""
    base, sep, dernier = nom.rpartition(" ")
    if not sep:
        return []
    for terminaison in _LATIN_GENDER_ENDINGS:
        if dernier.endswith(terminaison):
            racine = dernier[: -len(terminaison)]
            return [
                f"{base} {racine}{autre}" for autre in _LATIN_GENDER_ENDINGS if autre != terminaison
            ]
    return []


async def _canonical_search(adapter: ColXrAdapter, nom: str) -> list[dict]:
    """Recherche `nom` sans `type=EXACT`, puis ne garde que les candidats dont le nom
    scientifique, une fois le sous-genre retiré, correspond exactement à `nom` sans sous-genre —
    assez strict pour ignorer le bruit d'une recherche non filtrée par type, assez souple pour
    retrouver une fiche notée avec sous-genre."""
    cible = _strip_subgenus(nom)
    resultats = await adapter.search(nom, exact=False)
    return [r for r in resultats if _strip_subgenus(r["usage"]["name"]["scientificName"]) == cible]


def _merge_unique(*groupes: list[dict]) -> list[dict]:
    vus: set[str] = set()
    fusion: list[dict] = []
    for groupe in groupes:
        for r in groupe:
            if r["id"] not in vus:
                vus.add(r["id"])
                fusion.append(r)
    return fusion


async def resolve_col_xr_matches(adapter: ColXrAdapter, nom: str) -> list[dict]:
    """Résout `nom` dans COL XR avec repli progressif, partagé par `ColModule` (classification)
    et `find_col_xr_link`/`resolve_col_xr_concept_id` (lien secondaire GBIF) pour ne pas dupliquer
    la logique. Couvre deux désaccords de forme observés lors de l'audit GBIF/COL XR : la notation
    de sous-genre ("Mus (Mus) musculus" côté COL XR pour la requête "Mus musculus", y compris
    quand seule la forme sans sous-genre existe comme synonyme littéral — ex. Drosophila
    melanogaster, accepté sous "Drosophila (Sophophora) melanogaster") et un changement d'accord
    de genre latin sur l'épithète (ex. Macrovipera lebetina/lebetinus). `type=EXACT` côté
    ChecklistBank ne reconnaît aucune des deux variantes.

    Renvoie la recherche exacte fusionnée avec les candidats trouvés au premier repli qui
    aboutit (sous-genre retiré, puis, seulement si ça échoue, variantes de genre latin) — la
    recherche exacte reste toujours en tête même quand un repli aboutit, pour ne pas perdre un
    synonyme littéral déjà trouvé (ex. Drosophila melanogaster, dont la redirection vers
    l'accepté sert encore aux appelants qui suivent les synonymes)."""
    results = await adapter.search(nom)
    exact = [r for r in results if r["usage"]["name"]["scientificName"] == nom]
    if exact and any(r["usage"]["status"] == "accepted" for r in exact):
        return exact

    candidats = await _canonical_search(adapter, nom)
    if candidats:
        return _merge_unique(exact, candidats)

    for variante in _latin_gender_variants(nom):
        candidats = await _canonical_search(adapter, variante)
        if candidats:
            return _merge_unique(exact, candidats)

    return exact or results


def select_col_xr_candidate(candidats: list[dict], domaine: str) -> dict | None:
    """Départage une liste de candidats ChecklistBank (fiches "accepted" ou synonymes) déjà
    filtrée par statut — partagé par `ColModule` et les fonctions `find_col_xr_*`/
    `resolve_col_xr_concept_id` ci-dessous pour ne pas dupliquer la logique.

    1. Restreint au règne `domaine` s'il est connu et qu'au moins un candidat correspond (sinon
       tous les candidats restent en lice — `domaine` peut être inconnu, ex. "*").
    2. Si plusieurs subsistent, préfère ceux dont `usage.merged` est faux : `merged=true` signale
       une fiche assemblée automatiquement par l'algorithme de fusion inter-checklists de 3LXR
       (souvent un traitement Plazi d'un article sans rapport) plutôt qu'une entrée nativement
       curatée d'une checklist source — observé sur ~50 espèces bien documentées, `merged=false`
       est la norme absolue pour une fiche correcte (voir l'audit CS33N vs VB8KH/NT3L7 pour
       Escherichia coli, seul cas où ce signal à lui seul suffit à trancher).
    3. Si plusieurs subsistent encore, écarte ceux dont le code nomenclatural contredit leur
       propre règne/domaine (`_code_incoherent`, ex. Toxoplasma gondii VBKRN vs TFKPV, où
       `merged=true` pour les deux candidats ne permet pas de trancher).
    4. Sans autre signal fiable, conserve l'ordre déjà renvoyé par ChecklistBank (premier
       candidat) plutôt que de refuser de répondre : les cas à ce stade sont restés rares lors de
       l'audit (aucun trouvé au-delà d'Escherichia coli/Toxoplasma gondii sur ~75 taxons testés)."""
    if not candidats:
        return None
    matching = [r for r in candidats if _regne_correspond(r, domaine)] or candidats
    if len(matching) > 1:
        non_fusionnes = [r for r in matching if not r["usage"].get("merged")]
        matching = non_fusionnes or matching
    if len(matching) > 1:
        coherents = [r for r in matching if not _code_incoherent(r)]
        matching = coherents or matching
    return matching[0]


def _classification_par_rang(classification: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in classification:
        rang, nom = c.get("rank"), c.get("name")
        if rang and nom:
            out[col_xr_cherche_rang(rang)] = nom
    return out


def _to_link_info(cur: dict) -> ColXrLinkInfo:
    usage = cur["usage"]
    name = usage["name"]
    return ColXrLinkInfo(
        id=cur["id"],
        nom=name["scientificName"],
        auteur=format_auteur(name.get("authorship")),
        rang=col_xr_cherche_rang(name["rank"]) if "rank" in name else None,
        eteint=usage.get("extinct"),
        classification=_classification_par_rang(cur.get("classification", [])),
    )


async def find_col_xr_link(adapter: ColXrAdapter, nom: str, domaine: str) -> ColXrLinkInfo | None:
    """Comme `find_col_xr_id`, mais renvoie la fiche complète (nom/auteur/rang) plutôt que le seul
    identifiant — voir `ColXrLinkInfo`. None si aucune entrée COL XR acceptée ne correspond au nom
    (et au règne, si `domaine` est renseigné) — un simple défaut d'absence, pas une erreur : GBIF
    garde alors son identifiant numérique habituel. Ignore délibérément les synonymes (contrairement
    à `ColXrModule`) : un lien de référence doit pointer vers la même fiche acceptée que celle déjà
    résolue par GBIF, jamais vers un statut différent."""
    candidats = await resolve_col_xr_matches(adapter, nom)
    accepted = [r for r in candidats if r["usage"]["status"] == "accepted"]
    cur = select_col_xr_candidate(accepted, domaine)
    return _to_link_info(cur) if cur is not None else None


async def find_col_xr_id(adapter: ColXrAdapter, nom: str, domaine: str) -> str | None:
    """Identifiant seul — voir `find_col_xr_link` pour la fiche complète."""
    info = await find_col_xr_link(adapter, nom, domaine)
    return info.id if info is not None else None

async def resolve_col_xr_concept_id(adapter: ColXrAdapter, nom: str, domaine: str) -> str | None:
    """Identifiant ChecklistBank du concept taxonomique ACCEPTÉ désigné par `nom`, que `nom` soit
    lui-même le nom accepté ou un synonyme que COL XR redirige explicitement vers lui
    (`usage.accepted.id`) — contrairement à `find_col_xr_id`, qui ignore les synonymes pour ne
    jamais faire pointer un lien externe vers un statut différent du sien. Utilisé par
    `organon.core.rendering.subtaxa_merge.reconcile_synonym_groups` pour reconnaître comme un seul
    taxon deux noms orthographiés différemment par deux sources (ex. Discussion Projet:Biologie/
    Organon #30) quand COL XR les relie explicitement — jamais par ressemblance de nom seule.
    None si `nom` n'a aucune entrée COL XR (accepté ou synonyme redirigé) correspondante."""
    candidats = await resolve_col_xr_matches(adapter, nom)

    accepted = [r for r in candidats if r["usage"]["status"] == "accepted"]
    cur = select_col_xr_candidate(accepted, domaine)
    if cur is not None:
        return cur["id"]

    synonymes = [
        r for r in candidats if r["usage"]["status"] == "synonym" and r["usage"].get("accepted")
    ]
    cur = select_col_xr_candidate(synonymes, domaine)
    return cur["usage"]["accepted"]["id"] if cur is not None else None

"""Rendu de l'article, section par section. Chaque fonction `render_*` produit une section
du wikitexte final à partir du `Struct` typé (voir `organon.core.models`).

`render_taxobox()` a besoin de la liste d'ébauche déjà calculée (`ebauche`) plutôt que
d'appeler `wp_ebauche()` elle-même : ce calcul dépend du moteur de règles (voir
`organon.core.selectors`), et cette fonction reste volontairement indépendante de ce
sous-système (elle ne fait que du rendu de texte à partir de données déjà résolues) — voir
`organon.core.rendering.engine.render()` qui fait le lien entre les deux.
"""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct
from organon.core.rendering.grammar import (
    lien_pour_auteur,
    lien_pour_basionyme,
    lien_pour_synonyme,
    wp_est_infraspecifique,
    wp_est_italique,
    wp_eteint_rang,
    wp_inf_rang,
    wp_le_rang,
    wp_met_italiques,
    wp_nom_rang,
    wp_rang_plus_specifique,
    wp_un_rang,
)
from organon.core.rendering.support import (
    cherche_homonyme,
    colonnes_contenu,
    conditionne_noms,
    continents_codes_wgsrpd,
    data_pays_code,
    data_wgsrpd_code,
    dates_recupere,
    est_colonnes,
    format_auteur,
)

# Règnes utilisant "nom correct" plutôt que "nom valide" (convention bota/mycolo/bactério).
_REGNES_NOM_CORRECT = {"végétal", "champignon", "algue", "bactérie", "archaea"}

RANGS_CATEGORIE_HOMONYME = {"embranchement", "classe", "ordre", "famille"}
"""Rangs pour lesquels l'article est la page principale de sa propre catégorie homonyme (ex.
[[Catégorie:Bovidae|*]] + {{catégorie principale}} sur l'article "Bovidae") — voir
`organon.core.selectors.categorization.compute_fin_liens` (catégorie) et `render_voir_aussi`
ci-dessous ({{catégorie principale}})."""

_RANG_PARENT_CITE: dict[str, str] = {
    "famille": "ordre",
    "ordre": "classe",
    "classe": "embranchement",
}
"""Rang cité comme taxon supérieur dans le RI (`render_intro`), ex. « famille de l'ordre des
Artiodactyla » pour un taxon de rang famille (tâche #37). Par défaut (rang absent de ce
mapping — genre, espèce, tribu...) on cite la famille, comme avant l'ajout de ce mapping. Ordre
de `core/data/ranks.yaml` : chaque valeur est le rang canonique immédiatement supérieur, en
ignorant les rangs intermédiaires (sous-ordre, infra-classe...) qui n'ont pas de page Wikipédia
dédiée. `embranchement` n'a pas d'entrée : le rang supérieur (règne/domaine) sort du périmètre
de la tâche."""

# Table $cas de rendu_vide() : section -> (rendu si plan=false, rendu si plan=true).
_RENDU_VIDE_CAS: dict[str, tuple[bool, bool]] = {
    "repartition": (True, True),
    "description": (True, True),
    "etymologie": (False, True),
    "inf": (False, True),
    "originale": (False, True),
    "externes": (False, True),
}


def rendu_vide(section: str, options: GenerateOptions) -> bool:
    cas = _RENDU_VIDE_CAS.get(section)
    if cas is None:
        return False
    return cas[1] if options.plan else cas[0]


def render_intro(struct: Struct) -> str:
    rang_cite = _RANG_PARENT_CITE.get(struct.taxon.rang, "famille")
    parent = None
    for rang in struct.rangs:
        if rang.rang == rang_cite:
            nom_cite = wp_nom_rang(rang_cite, lien=True, maj=False, plur=False)
            taxon_cite = wp_met_italiques(rang.nom, rang_cite, struct.regne, lien=True)
            parent = wp_le_rang(rang_cite) + nom_cite + " des " + taxon_cite
            break

    lien = wp_un_rang(struct.taxon.rang)
    nom_rang = wp_nom_rang(struct.taxon.rang, lien=True, maj=False, plur=False)
    tnom = wp_met_italiques(struct.taxon.nom, struct.taxon.rang, struct.regne)

    if wp_inf_rang(struct.taxon.rang):
        phrase = f"'''{tnom}''' est {lien}{nom_rang} "
    else:
        phrase = f"Les '''{tnom}''' sont {lien}{nom_rang} "

    if struct.taxon.eteint:
        phrase += wp_eteint_rang(struct.taxon.rang) + " "

    if parent:
        phrase += "de " + parent + ".\n"
    else:
        phrase += ".\n"
    return phrase


def compute_rank_lines(struct: Struct) -> list[tuple[str, str, str]]:
    """Calcule, pour chaque rang de `struct.rangs`, le triplet (rang, nom, ligne wikitexte
    `{{Taxobox | ...}}` déjà mise en forme — homonymie et éteint compris), dans l'ordre de
    `struct.rangs` (du plus proche au plus éloigné du taxon demandé). Extrait de
    `render_taxobox` pour que l'API puisse exposer ces rangs structurés (comparaison entre
    plusieurs classifications, voir `{{Taxobox conflit}}`) sans dupliquer la logique de mise en
    forme des lignes."""
    regne = struct.regne
    rangs = struct.rangs
    if regne == "algue":
        rangs = [r for r in rangs if r.rang != "empire"]

    lines: list[tuple[str, str, str]] = []
    for r in rangs:
        eteint = " | éteint=oui" if r.eteint else ""
        page_hom, hom = cherche_homonyme(r.nom, regne)
        taxobox = f"{{{{Taxobox | {r.rang}"
        if hom is None:
            taxobox += f" | {r.nom}"
        elif page_hom:
            taxobox += f" | {{{{Lien vers une page d'homonymie|{hom}}}}}"
        else:
            taxobox += f" | {hom} | {r.nom}"
        taxobox += f"{eteint} }}}}"
        lines.append((r.rang, r.nom, taxobox))
    return lines


def render_taxobox(struct: Struct, options: GenerateOptions, ebauche: list[str]) -> str:
    resu = ""
    resu += "{{ébauche|" + "|".join(ebauche) + "}}\n" if ebauche else "{{ébauche}}\n"

    taxon, rang, regne = struct.taxon.nom, struct.taxon.rang, struct.regne
    afftaxon = wp_met_italiques(taxon, rang, regne)
    image = struct.image.get("image") if struct.image else None
    legende = struct.image.get("legende") if struct.image else None
    image = image or "<!-- insérez une image -->"
    legende = legende or "<!-- insérez légende descriptive de l'image -->"
    classification = f"classification={struct.classification_taxobox}"
    cache = " |règne=cacher " if struct.cacher_regne else ""

    resu += f"{{{{Taxobox début | {regne} | {afftaxon} | {image} | {legende} | {classification}{cache}}}}}\n"

    rank_lines = compute_rank_lines(struct)
    resu += "\n".join(line for _, _, line in reversed(rank_lines))
    resu += "\n"

    eteint = " | éteint=oui" if struct.taxon.eteint else ""
    auteur = (
        struct.taxon.auteur_resolu
        if struct.taxon.auteur_resolu is not None
        else format_auteur(struct.taxon.auteur)
    )
    resu += f"{{{{Taxobox taxon | {regne} | {rang} | {taxon} | {auteur}{eteint} }}}}\n"

    uicn = struct.liens.get("uicn")
    est_espece_ou_inf = rang == "espèce" or wp_rang_plus_specifique(rang, "espèce")
    if uicn and uicn.get("risque") and est_espece_ou_inf:
        critere = uicn.get("critere", "")
        resu += f"{{{{Taxobox UICN | {uicn['risque']} | {critere} }}}}\n"

    cites = struct.liens.get("cites")
    if cites and cites.get("annexe"):
        date = cites.get("date", "")
        prec = cites.get("precision", "")
        resu += f"{{{{Taxobox CITES | {cites['annexe']} | {date} | {prec} }}}}\n"

    resu += "{{Taxobox fin}}\n"
    return resu


def join_et(items: list[str]) -> str:
    """Joint une liste avec des virgules et "et" avant le dernier élément (ex. ["a", "b", "c"] ->
    "a, b et c"). Partagé entre `compute_rang_txt` et `organon.core.rendering.subtaxa_merge`
    (citations Bioref) pour ne pas dupliquer cette convention de jonction."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    txt = items[0]
    for i in range(1, len(items)):
        txt += " et " + items[i] if i == len(items) - 1 else ", " + items[i]
    return txt


def compute_rang_names(liste: list[RankName]) -> dict[str, tuple[str, str]]:
    """Nom de rang (pluriel, singulier) pour chaque rang distinct de `liste`, dans l'ordre de
    première rencontre, indexé par la clé technique du rang (ex. "sous-espèce") plutôt que son
    nom affiché — pour permettre à `organon.core.rendering.subtaxa_merge` d'exposer cette table au
    frontend et d'y recalculer `rang_txt`/`rang_txt_singulier` au fil des cases cochées, sans
    deviner la pluralisation en JS."""
    rang_names: dict[str, tuple[str, str]] = {}
    for sous_taxon in liste:
        if sous_taxon.rang is None or sous_taxon.rang in rang_names:
            continue
        plur = wp_nom_rang(sous_taxon.rang, lien=False, maj=False, plur=True)
        if plur == "NOTFOUND":
            continue
        sing = wp_nom_rang(sous_taxon.rang, lien=False, maj=False, plur=False)
        rang_names[sous_taxon.rang] = (plur, sing)
    return rang_names


def compute_rang_txt(liste: list[RankName]) -> tuple[str, str, str]:
    """Calcule `(rang_txt, rang_txt_singulier, rang_defaut)` pour une liste de sous-taxons :
    `rang_txt`/`rang_txt_singulier` sont le(s) nom(s) de rang rencontrés dans `liste` au pluriel
    et au singulier (ex. "espèces"/"espèce", ou "espèces et sous-espèces"/"espèce et
    sous-espèce" si la liste mélange les rangs) ; `rang_defaut` le premier rencontré, au
    pluriel — utilisé comme rang de repli pour les éléments qui ne portent pas leur propre rang
    (voir `render_subtaxon_line` : ce repli est conservé tel quel, y compris son effet de bord
    déjà présent avant l'extraction de cette fonction — un `rang_defaut` au pluriel n'est pas
    une clé de rang valide pour `wp_est_italique`/`wp_inf_rang`, mais ce cas ne se présente que
    pour un sous-taxon sans son propre rang, ce qui n'arrive pas en pratique avec les modules
    actuels). Extrait de `render_inf` pour être partagé avec
    `organon.core.rendering.subtaxa_merge` (rendu fusionné multi-sources, où `rang_txt_singulier`
    sert à l'accord grammatical du compte d'espèces) sans dupliquer cette logique."""
    rang_names = compute_rang_names(liste)
    if not rang_names:
        return "taxons de rang inférieur", "taxon de rang inférieur", "espèce"

    rang_txt = join_et([plur for plur, _ in rang_names.values()])
    rang_txt_singulier = join_et([sing for _, sing in rang_names.values()])
    rang_defaut = next(iter(rang_names.values()))[0]
    return rang_txt, rang_txt_singulier, rang_defaut


def render_subtaxon_line(sous_taxon: RankName, regne: str, rang_defaut: str, taxon_rang: str) -> str:
    """Rendu wikitexte d'une ligne de sous-taxon (`"* ''Nom'' Auteur\\n"`, italiques/éteint
    compris) — extrait de `render_inf` pour être partagé avec
    `organon.core.rendering.subtaxa_merge` (mêmes règles de mise en forme pour le rendu
    mono-source et le rendu fusionné multi-sources). Le wikilien est ajouté dès que le rang du
    sous-taxon est plus spécifique que celui du taxon de l'article (`taxon_rang`) — et non plus
    seulement au-dessus du niveau espèce : une liste de sous-taxons ne contient par construction
    que des rangs inférieurs à celui du taxon, donc essentiellement toujours un lien — sauf pour
    les rangs infra-spécifiques (sous-espèce, variété, forme...), qui n'ont presque jamais
    d'article dédié sur Wikipédia (voir `wp_est_infraspecifique`)."""
    rang_affiche = sous_taxon.rang or rang_defaut
    auteur = " " + format_auteur(sous_taxon.auteur) if sous_taxon.auteur else ""
    wikilien = wp_rang_plus_specifique(rang_affiche, taxon_rang) and not wp_est_infraspecifique(
        rang_affiche
    )
    cible = wp_met_italiques(sous_taxon.nom, rang_affiche, regne, lien=wikilien)
    if sous_taxon.eteint:
        cible = "† " + cible
    return f"* {cible}{auteur}\n"


def render_inf(struct: Struct, options: GenerateOptions) -> str:
    cdate = dates_recupere()
    sous_taxons = struct.sous_taxons
    if sous_taxons is None or not sous_taxons.liste:
        if rendu_vide("inf", options):
            return "\n== Liste des taxons de rang inférieur ==\n{{Section vide ou incomplète}}\n"
        return ""

    rang_txt, _, rang_defaut = compute_rang_txt(sous_taxons.liste)
    module_source = sous_taxons.source

    ret = f"\n== Liste des {rang_txt} ==\nSelon {{{{Bioref|{module_source}|{cdate}}}}} :\n"

    ret0 = ""
    for sous_taxon in sorted(sous_taxons.liste, key=lambda s: s.nom):
        ret0 += render_subtaxon_line(sous_taxon, struct.regne, rang_defaut, struct.taxon.rang)

    if est_colonnes(len(sous_taxons.liste), options):
        ret += colonnes_contenu(ret0)
    else:
        ret += ret0

    if sous_taxons.coupe:
        ret += "ATTENTION : liste des sous-taxons tronquée car trop longue. Utilisez '-limite-listes' pour modifier ce comportement.\n"

    return "\n" + ret


def render_supp(struct: Struct, options: GenerateOptions) -> str:
    cdate = dates_recupere()
    ret = "== Systématique ==\n"

    ref = struct.classification
    cible = wp_met_italiques(struct.taxon.nom, struct.taxon.rang, struct.regne)
    page_auteur = lien_pour_auteur(struct.regne)
    mot = "[[nom correct]]" if struct.regne in _REGNES_NOM_CORRECT else "[[nom valide]]"

    if struct.taxon.auteur:
        ret += f"Le {mot} complet (avec [[{page_auteur}|auteur]]) de ce taxon est " + cible
    else:
        ret += f"Le {mot} de ce taxon est " + cible

    if struct.taxon.auteur:
        # Contrairement à la ligne {{Taxobox taxon}} (voir render_taxobox, qui utilise
        # struct.taxon.auteur_resolu), cette phrase applique volontairement le traitement
        # simple : un remplacement "et al." basique directement sur l'auteur brut, pas la
        # version wikifiée par `organon.core.rendering.authors`. Les deux traitements sont
        # indépendants, ne pas les fusionner.
        ret += " " + format_auteur(struct.taxon.auteur)
    ret += f"{{{{Bioref|{ref}|{cdate}|ref}}}}.\n"
    if struct.basionyme is None:
        ret += "\n"

    if struct.basionyme is not None:
        basio = lien_pour_basionyme(struct.regne)
        cible = wp_met_italiques(struct.basionyme.nom, struct.taxon.rang, struct.regne)
        parts = struct.basionyme.nom.split(" ")
        auteur = " " + format_auteur(struct.basionyme.auteur) if struct.basionyme.auteur else ""
        if len(parts) == 2:
            ret += (
                f"L'espèce a été initialement classée dans le genre ''[[{parts[0]}]]'' sous le "
                f"{basio} {cible}{auteur}{{{{Bioref|{struct.basionyme.source}|{cdate}|ref}}}}.\n\n"
            )
        else:
            ret += (
                f"Le {basio} de ce taxon est : {cible}{auteur}"
                f"{{{{Bioref|{struct.basionyme.source}|{cdate}|ref}}}}\n\n"
            )

    if struct.type_taxon is not None:
        t = struct.type_taxon
        cible = wp_met_italiques(t.nom, t.rang, struct.regne, lien=True)
        if t.auteur:
            cible += " " + t.auteur
        if t.rang == "espèce":
            rangtype = "[[espèce type]]"
        elif t.rang == "genre":
            rangtype = "[[genre type]]"
        else:
            txt = wp_le_rang(t.rang) + (t.rang or "")
            rangtype = (txt[:1].upper() + txt[1:] if txt else txt) + " [[Type (biologie)|type]]"
        ret += f"{rangtype} est {cible}{{{{Bioref|{t.source}|{cdate}|ref}}}}.\n\n"

    if struct.vernaculaire:
        txt, cnt = conditionne_noms(struct.vernaculaire, cdate)
        pl = (
            "les [[nom vernaculaire|noms vernaculaires]] ou [[nom normalisé|normalisés]] suivants"
            if cnt > 1
            else "le [[nom vernaculaire]] ou [[nom normalisé|normalisé]] suivant"
        )
        ret += f"Ce taxon porte en français {pl} : {txt}."

        if struct.autres_noms:
            # Fondu en dict[source, noms] (statuts confondus) pour réutiliser conditionne_noms :
            # une seconde phrase, jamais seule (voir la garde `if struct.vernaculaire` ci-dessus)
            # — "également" n'a de sens qu'à la suite de la phrase précédente.
            autres_par_source = {
                source: [nom for noms in statuts.values() for nom in noms]
                for source, statuts in struct.autres_noms.items()
            }
            txt_autres, _ = conditionne_noms(autres_par_source, cdate)
            if txt_autres:
                ret += f" Ce taxon est également nommé {txt_autres}."

        ret += "\n\n"

    if struct.synonymes is not None and struct.synonymes.liste:
        target = lien_pour_synonyme(struct.regne)
        cible = wp_met_italiques(struct.taxon.nom, struct.taxon.rang, struct.regne)
        pl = f"{cible} a pour [[{target}|synonymes]]" if len(struct.synonymes.liste) > 1 else f"{cible} a pour [[{target}|synonyme]]"
        ret += f"{pl}{{{{Bioref|{struct.synonymes.source}|{cdate}|ref}}}} :\n"

        ret_t = []
        for s in struct.synonymes.liste:
            wkl = options.liens_synonymes
            rr = s.rang or struct.taxon.rang
            if wkl and wp_inf_rang(rr) and not options.liens_inf_sp:
                wkl = False
            x = s.rang or struct.taxon.rang
            cible = wp_met_italiques(s.nom, x, struct.regne, lien=wkl)
            auteur = " " + format_auteur(s.auteur) if s.auteur else ""
            ret_t.append(f"* {cible}{auteur}\n")

        if options.trier_synonymes:
            ret_t.sort()
        ret0 = "".join(ret_t)
        if est_colonnes(len(struct.synonymes.liste), options):
            ret += colonnes_contenu(ret0)
        else:
            ret += ret0

        if struct.synonymes.coupe:
            ret += "ATTENTION : liste des synonymes tronquée car trop longue. Utilisez '-limite-listes' pour modifier ce comportement.\n"

    return "\n\n" + ret if ret else ""


def render_description(struct: Struct, options: GenerateOptions) -> str:
    resu = "\n== Description ==\n"
    description = struct.liens.get("description")  # pas encore de champ dédié, cf. backlog
    if not description:
        if rendu_vide("description", options):
            return resu + "{{Section vide ou incomplète}}\n"
        return ""
    for ref, liste in description.items():
        resu += ". ".join(liste)
        resu += f"{{{{Bioref|{ref}|ref}}}}."
    return resu + "\n"


def render_distribution(struct: Struct, options: GenerateOptions) -> str:
    cdate = dates_recupere()
    resu = "\n== Répartition ==\n"
    if not struct.distribution:
        if rendu_vide("repartition", options):
            return resu + "{{Section vide ou incomplète}}\n"
        return ""

    source = ""
    # `introduced`/`extinct` sont des sous-ensembles de `certain`/`uncertain` (docstring de
    # `DistributionEntry`) : retirés de leur bucket parent pour une clause dédiée par statut,
    # comme déjà fait pour {{WGSRPD}}.
    certain: list[str] = []
    uncertain: list[str] = []
    introduit: list[str] = []
    eteint: list[str] = []
    wgsrpd_certain: list[str] = []
    wgsrpd_uncertain: list[str] = []
    wgsrpd_introduit: list[str] = []
    wgsrpd_eteint: list[str] = []
    for ref, entry in struct.distribution.items():
        source = ref
        # POWO peuple ce champ avec des codes WGSRPD (pas ISO) : table de traduction dédiée
        # (voir data_wgsrpd_code) plutôt que data_pays_code, qui ne les connaît pas.
        traduit_code = data_wgsrpd_code if ref == "powo" else data_pays_code
        certain.extend(
            traduit_code(code) for code in entry.certain if code not in entry.introduced
        )
        uncertain.extend(
            traduit_code(code) for code in entry.uncertain if code not in entry.extinct
        )
        introduit.extend(traduit_code(code) for code in entry.introduced)
        eteint.extend(traduit_code(code) for code in entry.extinct)
        if ref == "powo":
            wgsrpd_certain.extend(code for code in entry.certain if code not in entry.introduced)
            wgsrpd_uncertain.extend(code for code in entry.uncertain if code not in entry.extinct)
            wgsrpd_introduit.extend(entry.introduced)
            wgsrpd_eteint.extend(entry.extinct)

    certain = sorted(dict.fromkeys(certain))
    uncertain = sorted(dict.fromkeys(uncertain))
    introduit = sorted(dict.fromkeys(introduit))
    eteint = sorted(dict.fromkeys(eteint))
    wgsrpd_certain = sorted(dict.fromkeys(wgsrpd_certain))
    wgsrpd_uncertain = sorted(dict.fromkeys(wgsrpd_uncertain))
    wgsrpd_introduit = sorted(dict.fromkeys(wgsrpd_introduit))
    wgsrpd_eteint = sorted(dict.fromkeys(wgsrpd_eteint))

    if len(struct.distribution) == 1:
        if wgsrpd_certain or wgsrpd_uncertain or wgsrpd_introduit or wgsrpd_eteint:
            resu += "{{WGSRPD"
            if wgsrpd_certain:
                resu += f"|certain={','.join(wgsrpd_certain)}"
            if wgsrpd_uncertain:
                resu += f"|incertain={','.join(wgsrpd_uncertain)}"
            if wgsrpd_introduit:
                resu += f"|introduit={','.join(wgsrpd_introduit)}"
            if wgsrpd_eteint:
                resu += f"|eteint={','.join(wgsrpd_eteint)}"
            resu += f"|source=[[Plants of the World Online|POWO]]{{{{Bioref|{source}|{cdate}|ref}}}}"
            resu += "}}\n"
        total = len(certain) + len(uncertain) + len(introduit) + len(eteint)
        if total > SEUIL_LISTE_DISTRIBUTION:
            resu += _resume_et_liste_distribution(
                certain, uncertain, introduit, eteint, wgsrpd_certain, source, cdate
            )
        else:
            resu += _phrase_distribution(certain, uncertain, introduit, eteint, source, cdate)
    else:
        resu += "''Une distribution issue de plusieurs sources existe. Non implémenté pour le moment''\n"
    return resu


def _phrase_distribution(
    certain: list[str],
    uncertain: list[str],
    introduit: list[str],
    eteint: list[str],
    source: str,
    cdate: str,
) -> str:
    """Une clause par statut plutôt que noyés ensemble ; `certain` reste sans qualificatif
    (indigène/endémique ne se déduisent pas d'un simple compte de codes WGSRPD). Un statut seul
    a sa propre formulation, plutôt que le "est présent" générique trompeur par omission —
    symétrique aux titres dédiés de {{WGSRPD}} sur le wiki."""
    if not (certain or uncertain or introduit or eteint):
        return ""
    ref = f"{{{{Bioref|{source}|{cdate}|ref}}}}"

    if eteint and not (certain or uncertain or introduit):
        return f"Ce taxon est éteint dans {_lieu(eteint)}{ref} : {', '.join(eteint)}.\n"
    if introduit and not (certain or uncertain or eteint):
        return f"Ce taxon est introduit dans {_lieu(introduit)}{ref} : {', '.join(introduit)}.\n"
    if uncertain and not (certain or introduit or eteint):
        return (
            f"La présence de ce taxon est incertaine dans {_lieu(uncertain)}{ref} : "
            f"{', '.join(uncertain)}.\n"
        )

    clauses = []
    if certain:
        clauses.append(", ".join(certain))
    if introduit:
        clauses.append(f"introduit en {', '.join(introduit)}")
    if uncertain:
        clauses.append(f"de présence incertaine en {', '.join(uncertain)}")
    if eteint:
        clauses.append(f"éteint en {', '.join(eteint)}")

    if certain:
        entete = f"Ce taxon est présent dans {_lieu(certain)}"
    else:
        entete = "Statut de ce taxon par pays et région"
    return f"{entete}{ref} : {'; '.join(clauses)}.\n"


def _lieu(items: list[str]) -> str:
    return "le pays ou la région suivant" if len(items) == 1 else "les pays et régions suivants"


SEUIL_LISTE_DISTRIBUTION = 10
"""Au-delà de ce total d'entrées (tous statuts confondus), la phrase inline devient illisible
(ex. Quercus robur, ~60 entrées) : bascule sur un résumé chiffré + liste groupée par statut."""

SEUIL_COLONNES_STATUT = 15
"""Au-delà de ce nombre d'entrées pour un même statut, la liste horizontale à virgules devient
elle-même trop longue à lire d'un bloc (ex. Quercus robur, ~60 pays natifs) : bascule sur une
{{Liste déroulante}} centrée et repliée par défaut, contenant la liste en colonnes ({{colonnes}})
plutôt qu'un bloc {{Début de colonnes}} nu qui restait affiché en entier dans l'article."""


def _lien_continents(n: int) -> str:
    """"Continent(s)" lié vers WGSRPD plutôt que vers un article de continent classique : les
    régions L1 (ex. Pacifique, Antarctique) ne correspondent pas toutes à un vrai continent."""
    texte = "continent" if n == 1 else "continents"
    return (
        "{{Lien|trad=World Geographical Scheme for Recording Plant Distributions|langue=en|"
        "fr=Système géographique mondial d'enregistrement de la répartition des plantes|"
        f"texte={texte}}}}}"
    )


_NOMBRES_LETTRES = {
    0: "zéro", 1: "un", 2: "deux", 3: "trois", 4: "quatre", 5: "cinq", 6: "six",
    7: "sept", 8: "huit", 9: "neuf", 10: "dix", 11: "onze", 12: "douze", 13: "treize",
    14: "quatorze", 15: "quinze", 16: "seize",
}


def _en_lettres(n: int) -> str:
    """Nombre en toutes lettres (convention typographique Wikipédia) pour les petits nombres ;
    au-delà de 16, aucune convention simple n'existe (accord seize/dix-sept variable selon le
    contexte) — retombe sur le chiffre."""
    return _NOMBRES_LETTRES.get(n, str(n))


def _liste_fr(items: list[str]) -> str:
    """Liste à la française : "A", "A et B", "A, B et C"."""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " et " + items[-1]


def _resume_et_liste_distribution(
    certain: list[str],
    uncertain: list[str],
    introduit: list[str],
    eteint: list[str],
    wgsrpd_certain: list[str],
    source: str,
    cdate: str,
) -> str:
    """Résumé chiffré (continents via `continents_codes_wgsrpd`) + liste horizontale groupée par
    statut (un tableau une-ligne-par-pays était illisible pour ~60 entrées, cf. discussion #27),
    remplace `_phrase_distribution` au-delà de `SEUIL_LISTE_DISTRIBUTION`."""
    ref = f"{{{{Bioref|{source}|{cdate}|ref}}}}"
    # Pas de |ref (pas de balise <ref>) dans la liste déroulante : {{Bioref}} y sert de simple
    # lien de citation en ligne, la note de bas de page numérotée est déjà posée par `ref` ci-dessus.
    citation = f"{{{{Bioref|{source}|{cdate}}}}}"

    resu = ""
    ref_utilisee = False
    continents = continents_codes_wgsrpd(wgsrpd_certain) if certain else []
    if continents:
        continents_txt = _liste_fr([f"en {data_wgsrpd_code(c)}" for c in continents])
        resu += (
            f"Ce taxon est présent sur {_en_lettres(len(continents))} "
            f"{_lien_continents(len(continents))}{ref} : {continents_txt}. "
        )
        ref_utilisee = True

    clauses = []
    if certain:
        suffixe = "pays ou région" if len(certain) == 1 else "pays et régions"
        clauses.append(f"[[indigène (écologie)|indigène]] dans {len(certain)} {suffixe}")
    if introduit:
        suffixe = "autre" if len(introduit) == 1 else "autres"
        clauses.append(f"introduit dans {len(introduit)} {suffixe}")
    if uncertain:
        suffixe = "autre" if len(uncertain) == 1 else "autres"
        clauses.append(f"de présence incertaine dans {len(uncertain)} {suffixe}")
    if eteint:
        suffixe = "pays ou région" if len(eteint) == 1 else "pays et régions"
        clauses.append(f"éteint dans {len(eteint)} {suffixe}")

    resu += f"Il est {_liste_fr(clauses)}"
    if not ref_utilisee:
        resu += ref
    resu += ".\n\n"

    if certain:
        resu += _bloc_statut("Natif", "indigène", certain, citation)
    if introduit:
        resu += _bloc_statut("Introduit", "introduit", introduit, citation)
    if uncertain:
        resu += _bloc_statut("Présence incertaine", "de présence incertaine", uncertain, citation)
    if eteint:
        resu += _bloc_statut("Éteint", "éteint", eteint, citation)
    return resu


def _bloc_statut(label: str, qualificatif: str, items: list[str], citation: str) -> str:
    """Un statut de `_resume_et_liste_distribution` : liste horizontale à virgules en-dessous de
    `SEUIL_COLONNES_STATUT`, sinon une {{Liste déroulante}} centrée et repliée par défaut, avec la
    source et la liste en colonnes ({{colonnes}}) dans son contenu (voir `SEUIL_COLONNES_STATUT`).
    `qualificatif` est l'adjectif accordé au statut (ex. "introduit") utilisé dans le titre de la
    liste déroulante, distinct de `label` qui reste le nom du statut au format court."""
    if len(items) <= SEUIL_COLONNES_STATUT:
        return f"* {label} : {_liste_fr(items)}.\n"
    lignes = "\n".join(f"* {item}" for item in items)
    titre = f"Liste des régions et pays dans lesquels ce taxon est {qualificatif}"
    return (
        "<center>\n"
        "{{Liste déroulante\n"
        " | width   = 55%\n"
        f" | titre   = {titre}\n"
        " | contenu =\n"
        f" Données : {citation}.\n"
        " {{colonnes|taille=18|1=\n"
        f"{lignes}\n"
        "}}\n"
        "}}\n"
        "</center>\n"
    )


def render_etymologie(struct: Struct, options: GenerateOptions) -> str:
    cdate = dates_recupere()
    resu = "\n== Étymologie ==\n"
    if struct.etymologie is None:
        if rendu_vide("etymologie", options):
            return resu + "{{Section vide ou incomplète}}\n"
        return ""
    resu += f"{struct.etymologie.texte}{{{{Bioref|{struct.etymologie.source}|{cdate}|ref}}}}.\n"
    return resu


def render_originale(struct: Struct, options: GenerateOptions) -> str:
    if struct.originale is None:
        if rendu_vide("originale", options):
            return "\n== Publications originales ==\n{{Section vide ou incomplète}}\n"
        return ""

    pubs = struct.originale if isinstance(struct.originale, list) else [struct.originale]
    titre = "\n== Publications originales ==\n" if len(pubs) > 1 else "\n== Publication originale ==\n"
    resu = titre
    for pub in sorted(pubs):
        resu += f"* {pub}\n"
    return resu


def _compute_ext_liens_items(struct: Struct) -> list[tuple[str, str]]:
    """Liste (non triée) de paires (module_id, ligne wikitexte) de référence taxonomique
    produites par `module.render_bioref` pour chaque module ayant contribué — factorisé de
    `render_voir_aussi` pour être réutilisé par `render_references_items` sans dupliquer la
    boucle. Un module dont `render_bioref` retourne plusieurs lignes produit une paire par
    ligne, toutes rattachées au même `module_id`. Dédoublonne par ligne wikitexte exacte : deux
    modules distincts peuvent résoudre la même fiche externe (ex. GbifModule ajoute un lien
    {{CatalogueofLife}} via COL XR/ChecklistBank quand ColModule résout indépendamment le même
    identifiant, voir gbif/module.py render_bioref)."""
    items: list[tuple[str, str]] = []
    seen: set[str] = set()
    for module_id, data in struct.liens.items():
        module = None
        from organon.core.registry import get_module  # import tardif : évite un cycle

        module = get_module(module_id)
        if module is None:
            continue
        rendu = module.render_bioref(struct)
        if not rendu:
            continue
        lignes = rendu if isinstance(rendu, list) else [rendu]
        for ligne in lignes:
            if ligne in seen:
                continue
            seen.add(ligne)
            items.append((module_id, ligne))
    return items


def _compute_ext_liens(struct: Struct) -> list[str]:
    """Liste (non triée) des liens de référence taxonomique — voir `_compute_ext_liens_items`."""
    return [wikitext for _module_id, wikitext in _compute_ext_liens_items(struct)]


def render_references_items(struct: Struct) -> list[tuple[str, str]]:
    """Paires (module_id, wikitext) des références taxonomiques, triées alphabétiquement par
    wikitext (même tri que le bloc "Liens externes" de `render_voir_aussi`) — exposées à l'API
    pour permettre au frontend de cocher/décocher chaque référence individuellement plutôt que
    de recevoir uniquement le bloc déjà joint."""
    return sorted(_compute_ext_liens_items(struct), key=lambda item: item[1])


def render_voir_aussi(struct: Struct, options: GenerateOptions) -> str:
    autres: list[str] = []

    externe = struct.liens.get("externe", {})
    if any(k in externe for k in ("commons", "species", "ccommons", "frwiktionary")):
        commons_page = (externe.get("commons") or {}).get("page")
        commons_cat_page = (externe.get("ccommons") or {}).get("page")
        if commons_page and not commons_cat_page:
            autres.append(f"commons={commons_page}")
        elif commons_page and commons_cat_page:
            autres.append(f"commons={commons_page}")
            autres.append(f"commons2=Category:{commons_cat_page}")
            autres.append(f"commons titre2=Catégorie {commons_cat_page}")
        elif not commons_page and commons_cat_page:
            autres.append(f"commons=Category:{commons_cat_page}")
            autres.append(f"commons titre=Catégorie {commons_cat_page}")
        if (externe.get("species") or {}).get("page"):
            autres.append(f"species={externe['species']['page']}")
        if (externe.get("frwiktionary") or {}).get("page"):
            autres.append(f"wiktionary={externe['frwiktionary']['page']}")

    ext = _compute_ext_liens(struct)

    if not ext and not autres:
        if rendu_vide("externes", options):
            return "== Liens externes ==\n{{Section vide ou incomplète}}\n"
        return ""

    resu = "== Liens externes ==\n"
    if autres:
        resu += "{{Autres projets\n"
        for a in sorted(autres):
            resu += f"| {a}\n"
        resu += "}}\n"
        if struct.taxon.rang in RANGS_CATEGORIE_HOMONYME:
            resu += "{{catégorie principale}}\n"
    if ext:
        for e in sorted(ext):
            resu += f"* {e}\n"

    return "\n" + resu


def render_fin(struct: Struct, notes: bool = False) -> str:
    if notes:
        ret = (
            "\n== Notes et références ==\n"
            "=== Notes ===\n{{Références|groupe=note}}\n"
            "=== Références ===\n{{références}}\n"
        )
    else:
        ret = "\n== Notes et références ==\n{{références}}\n"
    fin = struct.liens.get("fin", {})
    portails = fin.get("portails") or []
    categories = fin.get("categories") or []
    if portails:
        ret += "\n{{Portail|" + "|".join(portails) + "}}\n"
    if categories:
        ret += "\n"
        for c in categories:
            ret += f"[[Catégorie:{c}]]\n"
    return ret

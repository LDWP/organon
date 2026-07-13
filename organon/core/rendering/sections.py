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
from organon.core.models import Struct
from organon.core.rendering.grammar import (
    lien_pour_auteur,
    lien_pour_basionyme,
    lien_pour_synonyme,
    wp_est_italique,
    wp_eteint_rang,
    wp_inf_rang,
    wp_le_rang,
    wp_met_italiques,
    wp_nom_rang,
    wp_un_rang,
)
from organon.core.rendering.support import (
    cherche_homonyme,
    colonnes_contenu,
    conditionne_noms,
    data_pays_code,
    dates_recupere,
    est_colonnes,
    format_auteur,
)

# Règnes utilisant "nom correct" plutôt que "nom valide" (convention bota/mycolo/bactério).
_REGNES_NOM_CORRECT = {"végétal", "champignon", "algue", "bactérie", "archaea"}

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
    fam = None
    for rang in struct.rangs:
        if rang.rang == "famille":
            fam = wp_met_italiques(rang.nom, "famille", struct.regne, lien=True)
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

    if fam:
        phrase += "de la [[Famille (biologie)|famille]] des " + fam + ".\n"
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
    if uicn and uicn.get("risque"):
        critere = uicn.get("critere", "")
        resu += f"{{{{Taxobox UICN | {uicn['risque']} | {critere} }}}}\n"

    cites = struct.liens.get("cites")
    if cites and cites.get("annexe"):
        date = cites.get("date", "")
        prec = cites.get("precision", "")
        resu += f"{{{{Taxobox CITES | {cites['annexe']} | {date} | {prec} }}}}\n"

    resu += "{{Taxobox fin}}\n"
    return resu


def render_inf(struct: Struct, options: GenerateOptions) -> str:
    cdate = dates_recupere()
    sous_taxons = struct.sous_taxons
    if sous_taxons is None or not sous_taxons.liste:
        if rendu_vide("inf", options):
            return "\n== Liste des taxons de rang inférieur ==\n{{Section vide ou incomplète}}\n"
        return ""

    rang_names: dict[str, str] = {}
    for sous_taxon in sous_taxons.liste:
        nom_rang = wp_nom_rang(sous_taxon.rang, lien=False, maj=False, plur=True)
        if nom_rang == "NOTFOUND":
            continue
        rang_names[nom_rang] = nom_rang
    noms_rang = list(rang_names.values())

    if not noms_rang:
        rang_txt = "taxons de rang inférieur"
    elif len(noms_rang) == 1:
        rang_txt = noms_rang[0]
    else:
        rang_txt = noms_rang[0]
        for i in range(1, len(noms_rang)):
            rang_txt += " et " + noms_rang[i] if i == len(noms_rang) - 1 else ", " + noms_rang[i]

    rang_defaut = noms_rang[0] if noms_rang else "espèce"
    module_source = sous_taxons.source

    ret = f"\n== Liste des {rang_txt} ==\nSelon {{{{Bioref|{module_source}|{cdate}}}}} :\n"

    ret0 = ""
    for sous_taxon in sous_taxons.liste:
        rang_affiche = sous_taxon.rang or rang_defaut
        auteur = " " + format_auteur(sous_taxon.auteur) if sous_taxon.auteur else ""
        wikilien = not wp_inf_rang(rang_affiche)
        cible = wp_met_italiques(sous_taxon.nom, rang_affiche, struct.regne, lien=wikilien)
        if sous_taxon.eteint:
            cible = "† " + cible
        ret0 += f"* {cible}{auteur}\n"

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
        ret += f"Ce taxon porte en français {pl} : {txt}.\n\n"

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
    certain: list[str] = []
    uncertain: list[str] = []
    for ref, entry in struct.distribution.items():
        source = ref
        certain.extend(data_pays_code(code) for code in entry.certain)
        uncertain.extend(data_pays_code(code) for code in entry.uncertain)

    certain = sorted(dict.fromkeys(certain))
    uncertain = sorted(dict.fromkeys(uncertain))

    if len(struct.distribution) == 1:
        if certain:
            resu += (
                f"Ce taxon se rencontre dans les pays suivants{{{{Bioref|{source}|{cdate}|ref}}}} : "
                if len(certain) > 1
                else f"Ce taxon se rencontre dans le pays suivant{{{{Bioref|{source}|{cdate}|ref}}}} : "
            )
            resu += ", ".join(certain) + ".\n"
        if uncertain:
            if certain:
                resu += "\n"
            resu += (
                f"La présence de ce taxon est incertaine dans les pays suivants{{{{Bioref|{source}|{cdate}|ref}}}} : "
                if len(uncertain) > 1
                else f"La présence de ce taxon est incertaine dans le pays suivant{{{{Bioref|{source}|{cdate}|ref}}}} : "
            )
            resu += ", ".join(uncertain) + ".\n"
    else:
        resu += "''Une distribution issue de plusieurs sources existe. Non implémenté pour le moment''\n"
    return resu


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
    for pub in pubs:
        resu += f"* {pub}\n"
    return resu


def render_voir_aussi(struct: Struct, options: GenerateOptions) -> str:
    ext: list[str] = []
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

    for module_id, data in struct.liens.items():
        module = None
        from organon.core.registry import get_module  # import tardif : évite un cycle

        module = get_module(module_id)
        if module is None:
            continue
        rendu = module.render_bioref(struct)
        if not rendu:
            continue
        if isinstance(rendu, list):
            ext.extend(rendu)
        else:
            ext.append(rendu)

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
    if ext:
        for e in sorted(ext):
            resu += f"* {e}\n"

    return "\n" + resu


def render_fin(struct: Struct) -> str:
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

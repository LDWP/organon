"""Logique métier du module GBIF : classification, synonymes, sous-taxons, noms vernaculaires.
Ne fait aucun appel HTTP directement, voir adapter.py.
"""

from __future__ import annotations

import html as _html
import re

from organon.core.config import GenerateOptions
from organon.core.models import (
    Basionym,
    RankName,
    Redirection,
    Struct,
    SubTaxonList,
    SynonymList,
    TaxonInfo,
)
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.authors import BOTANIST_REGNES
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.col_xr.adapter import ColXrAdapter
from organon.modules.col_xr.lookup import find_col_xr_link
from organon.modules.common import (
    MAX_SYNONYM_HOPS,
    as_limit,
    collect_pages,
    format_auteur,
    simple_debug_link,
)
from organon.modules.gbif.adapter import GbifAdapter
from organon.modules.gbif.ranks import GBIF_MARKERS, GBIF_WP, gbif_cherche_rang, gbif_cherche_regne

_ANNEE_PUBLICATION_RE = re.compile(r"\b(1[3-9]\d\d|20\d\d)\b")


def _annee_probable(published_in: str | None, regne: str | None) -> int | None:
    """Extrait un candidat d'année de publication depuis `publishedIn` (citation bibliographique
    en texte libre — GBIF n'expose aucun champ année structuré comme `namePublishedInYear` chez
    POWO ou `YEAR_OF_PUBLICATION` chez Index Fungorum). Limité aux règnes ICN
    (`BOTANIST_REGNES` : botanique/champignons), où l'année n'est jamais incluse dans la
    citation d'auteur elle-même par convention, contrairement à l'ICZN zoologique (ex.
    "Linnaeus, 1758" pour la zoologie contre "L." pour la botanique) — inutile d'en extraire une
    pour un règne où GBIF la porte déjà nativement dans `authorship`.

    Prend le dernier nombre à 4 chiffres plausible (l'année termine généralement la citation,
    ex. "Sp. Pl.: 996 (1753)") : une extraction imparfaite reste sans danger, ce candidat n'est
    utilisé que s'il est recoupé avec un autre module (voir
    `organon.core.selectors.coherence.gbif_annee_probable_validee`), jamais présenté seul à
    l'utilisateur."""
    if not published_in or regne not in BOTANIST_REGNES:
        return None
    matches = _ANNEE_PUBLICATION_RE.findall(published_in)
    return int(matches[-1]) if matches else None


def _extrait_marqueur_rang(nom: str) -> tuple[str | None, str]:
    """Repère un marqueur de rang infraspécifique explicite dans un nom recherché (ex. "subsp."
    dans "Mentha spicata subsp. spicata") et renvoie (rang GBIF correspondant, nom débarrassé de
    ce marqueur). `/species?name=` (recherche exacte GBIF, voir `_collect`) indexe ces taxons
    sans leur marqueur (vérifié en direct : la requête avec marqueur ne matche rien du tout ;
    sans lui, elle matche mais devient ambiguë avec toute autre variation infraspécifique de
    mêmes épithètes, ex. la variété homonyme d'une sous-espèce) — nécessaire à la fois pour
    retenter la recherche sans le marqueur et pour départager les candidats obtenus ainsi."""
    mots = nom.split()
    for i, mot in enumerate(mots):
        rang = GBIF_MARKERS.get(mot)
        if rang:
            return rang, " ".join(mots[:i] + mots[i + 1 :])
    return None, nom


def _filtre_rang_marqueur(rang_attendu: str | None, candidats: list[dict]) -> list[dict]:
    """Ne garde, parmi plusieurs candidats homonymes, que ceux dont le rang GBIF correspond au
    marqueur explicite du nom recherché (`_extrait_marqueur_rang`) — sans quoi le premier
    candidat de la liste l'emportait au hasard, un rang différent de celui demandé,
    silencieusement (pas d'erreur : juste le mauvais taxon généré)."""
    if rang_attendu is None or len(candidats) < 2:
        return candidats
    filtres = [r for r in candidats if r.get("rank") == rang_attendu]
    return filtres or candidats


async def _taxon_info(adapter: GbifAdapter, key: int) -> dict | None:
    """Porte gbif_taxon_info() : nom/auteur/rang/éteint pour un identifiant GBIF donné."""
    name = await adapter.name_info(key)
    if name is None:
        return None
    nom = name.get("canonicalNameWithMarker") or name.get("canonicalName")
    complet = name.get("canonicalNameComplete")
    if nom is not None and complet is not None:
        auteur = complet[len(nom) + 1 :]
    else:
        # GBIF ne décompose pas tous les noms en nom canonique + auteur (`"parsed": false` sur
        # /name) — notamment les noms de virus, qui ne suivent pas la nomenclature binomiale. On
        # retombe sur le nom scientifique brut plutôt que d'abandonner la résolution.
        nom = name.get("scientificName")
        if nom is None:
            return None
        auteur = ""

    result: dict = {"nom": nom, "auteur": auteur}
    if name.get("rank"):
        result["rang"] = gbif_cherche_rang(name["rank"])
    elif name.get("rankMarker"):
        from organon.modules.gbif.ranks import gbif_marqueur_rang

        buf = gbif_marqueur_rang(name["rankMarker"])
        if buf != "NOTFOUND":
            result["rang"] = gbif_cherche_rang(buf)

    profiles = await adapter.species_profiles(key)
    for p in profiles:
        if "extinct" in p:
            result["eteint"] = p["extinct"]
            break

    return result


class GbifModule(TaxonomyModule):
    meta = ModuleMeta(
        id="gbif",
        can_classify=True,
        can_render_external_link=True,
        domains="all",
        priority=999,
        is_default_classification=True,
    )

    def __init__(
        self, adapter: GbifAdapter | None = None, col_xr_adapter: ColXrAdapter | None = None
    ) -> None:
        self._adapter = adapter or GbifAdapter()
        self._col_xr_adapter = col_xr_adapter or ColXrAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        return await self._collect(struct, is_classification, options, hop=0)

    async def _collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions, hop: int
    ) -> Struct | None:
        adapter = self._adapter

        # Un identifiant déjà résolu (ex. choix dans la liste de désambiguïsation, voir
        # `SearchMatch.gbif_key`) désigne un enregistrement précis sans ambiguïté : on l'utilise
        # tel quel plutôt que de repasser par une recherche floue par nom, qui n'est pas garantie
        # de retomber sur le même enregistrement (ex. un nom d'hôte qui matche aussi un nom
        # d'espèce sans rapport). Uniquement au premier appel (hop 0) : un renvoi vers un synonyme
        # accepté (voir plus bas) doit re-résoudre sur son propre nom, pas réutiliser cette clé.
        cur: dict | None = None
        if hop == 0 and options.gbif_key is not None:
            cur = await adapter.species_record(options.gbif_key)

        if cur is None:
            rang_marqueur, nom_sans_marqueur = _extrait_marqueur_rang(struct.taxon.nom)
            results = await adapter.search(struct.taxon.nom)
            if not results and rang_marqueur is not None:
                # `/species?name=` ne matche rien avec le marqueur de rang infraspécifique
                # botanique (ex. "subsp.") : on retente sans, voir `_extrait_marqueur_rang`. Le
                # rang extrait sert plus bas à départager les candidats ainsi trouvés.
                results = await adapter.search(nom_sans_marqueur)
            if not results:
                return None

            def _regne_correspond(r: dict) -> bool:
                if struct.domaine in ("*", ""):
                    return True
                return gbif_cherche_regne(r.get("kingdom", "")) == struct.domaine

            accepted = [r for r in results if r.get("taxonomicStatus") == "ACCEPTED"]
            # Un même nom peut désigner des taxons distincts selon le règne (ex. "Morus", mûrier
            # chez les végétaux et fou de Bassan chez les animaux) : si un filtre de domaine est
            # posé, on préfère l'entrée dont le règne correspond plutôt que la première trouvée.
            candidats = [r for r in accepted if _regne_correspond(r)] or accepted
            candidats = _filtre_rang_marqueur(rang_marqueur, candidats)
            cur = candidats[0] if candidats else None
            if cur is None:
                if not options.suivre_synonymes:
                    return None
                repli = [r for r in results if _regne_correspond(r)] or results
                cur = _filtre_rang_marqueur(rang_marqueur, repli)[0]

        key = cur["key"]
        info = await _taxon_info(adapter, key)
        if info is None:
            return None

        # COL XR (ChecklistBank dataset 3LXR) est la taxonomie par défaut de GBIF depuis 2024 :
        # quand ce même nom y est résolu, son identifiant alphanumérique remplace la clé
        # numérique GBIF pour le rendu (Modèle:GBIF réformé pour accepter les deux formats,
        # voir render_bioref) — la clé numérique `key` continue de piloter tous les appels GBIF
        # ci-dessous, seul l'identifiant stocké pour l'affichage change.
        col_xr = await find_col_xr_link(self._col_xr_adapter, info["nom"], struct.domaine)

        struct.liens["gbif"] = {
            "id": col_xr.id if col_xr is not None else key,
            "auteur": format_auteur(info["auteur"]),
            "nom": info["nom"],
            **({"rang": info["rang"]} if "rang" in info else {}),
            **({"eteint": info["eteint"]} if "eteint" in info else {}),
        }
        if col_xr is not None:
            # Fiche COL XR propre à l'identifiant ci-dessus : sert uniquement au second lien
            # {{CatalogueofLife}} de `render_bioref`, pas au lien {{GBIF}} — sans ça, ce lien citait
            # l'auteur du backbone GBIF au lieu de celui de la fiche COL XR réellement liée, ce qui
            # produisait deux lignes {{CatalogueofLife}} au contenu différent (donc non fusionnées
            # par le dédoublonnage de `_compute_ext_liens_items`) quand `ColModule` résolvait la
            # même fiche indépendamment.
            struct.liens["gbif"]["col_xr"] = {
                "nom": col_xr.nom,
                "auteur": col_xr.auteur,
                "rang": col_xr.rang,
                "eteint": col_xr.eteint,
            }
        if cur.get("publishedIn"):
            # Citation bibliographique déjà présente dans la réponse de recherche utilisée
            # ci-dessus (aucun appel réseau supplémentaire) — même usage que
            # `dcterms:bibliographicCitation`/`originalPublicationRef` côté AlgaeBase
            # (`algaebase/module.py::_apply_bibliographic_citation`/`_apply_detail_page`), pas de
            # champ année structuré séparé contrairement à POWO/IPNI/Index Fungorum.
            struct.originale = cur["publishedIn"]

        regne_detecte = gbif_cherche_regne(cur["kingdom"]) if cur.get("kingdom") else None
        annee_probable = _annee_probable(cur.get("publishedIn"), regne_detecte)
        if annee_probable is not None:
            struct.liens["gbif"]["annee_probable"] = annee_probable
        if not is_classification and regne_detecte:
            # Signal de règne détecté sans appel réseau supplémentaire : le champ "kingdom" est
            # déjà présent dans la réponse de recherche utilisée ci-dessus. Voir RegneIncoherence.
            struct.liens["gbif"]["regne_detecte"] = regne_detecte

        # Placé ici (avant le `if not is_classification` plus bas) plutôt que dans la branche
        # classification uniquement : GBIF tourne aussi en enrichissement quand une autre source
        # pilote la classification (domaine "all"), et c'est le seul endroit où `key` est connu
        # dans les deux cas — un module `iucn` séparé ne verrait pas cette clé en enrichissement
        # (les modules d'enrichissement tournent en parallèle sur des copies indépendantes du
        # struct pré-enrichissement, voir `EnrichmentRunner`).
        iucn = await adapter.iucn_red_list_category(key)
        if iucn and iucn.get("code"):
            struct.liens["uicn"] = {"risque": iucn["code"]}

        # Même raison que le bloc IUCN ci-dessus : les noms vernaculaires (`struct.vernaculaire`,
        # namespacé par module, fusionné sans conflit avec les autres sources — voir
        # `EnrichmentRunner.run`) ne doivent pas dépendre de savoir si GBIF pilote ou non la
        # classification, sous peine de dépendre arbitrairement du module qui a gagné la
        # classification (constaté en direct : absents dès que GBIF tourne en enrichissement
        # derrière une autre source gagnante).
        taxref_noms: list[str] = []

        async def fetch_vernacular(offset: int) -> tuple[list[str], bool]:
            page = await adapter.vernacular_names_page(key, offset)
            results = [c for c in page.get("results", []) if c.get("language") == "fra"]
            taxref_noms.extend(
                _html.unescape(c["vernacularName"]) for c in results if c.get("source") == "TAXREF"
            )
            names = [_html.unescape(c["vernacularName"]) for c in results]
            return names, page.get("endOfRecords", True)

        vernaculaire, _ = await collect_pages(fetch_vernacular)
        if vernaculaire:
            struct.vernaculaire["GBIF"] = vernaculaire
        if taxref_noms:
            # Le référentiel MNHN/TAXREF (source de "INPN") est indisponible en accès direct
            # (attaque informatique sur les serveurs du MNHN, durée indéterminée) : GBIF
            # réexpose déjà ces mêmes noms via son propre endpoint (source="TAXREF" dans sa
            # réponse), en secours le temps que taxref.mnhn.fr soit de nouveau joignable.
            struct.vernaculaire["INPN"] = taxref_noms

        # Même contournement que ci-dessus, pour l'identifiant plutôt que les noms : TAXREF est
        # aussi publiée comme checklist à part sur GBIF (`TAXREF_DATASET_KEY`), distincte du
        # Backbone. `related` retrouve l'enregistrement TAXREF du même concept taxonomique que
        # `key`, dont `taxonID` est le CD_NOM (identifiant INPN) — indépendant de la présence
        # d'un nom vernaculaire français (contrairement à `taxref_noms` ci-dessus).
        taxref_records = await adapter.taxref_related(key)
        cd_nom = next((r["taxonID"] for r in taxref_records if r.get("taxonID")), None)
        if cd_nom:
            struct.liens["gbif"]["inpn_id"] = cd_nom

        accepted_key = cur.get("acceptedKey")
        is_synonym = accepted_key is not None and accepted_key != key
        if is_synonym:
            if not is_classification:
                struct.liens["gbif"]["synonyme"] = True
                return struct
            if options.suivre_synonymes:
                if hop >= MAX_SYNONYM_HOPS:
                    return None
                accepted_info = await _taxon_info(adapter, accepted_key)
                if accepted_info is None:
                    return None
                struct.redirection = Redirection(nom=struct.taxon.nom)
                struct.taxon = TaxonInfo(nom=accepted_info["nom"])
                return await self._collect(struct, is_classification, options, hop=hop + 1)
            # suivre_synonymes désactivé : pas de retour anticipé — la classification se
            # construit directement à partir de ce synonyme plutôt que du taxon accepté.

        if not is_classification:
            return struct

        struct.taxon.auteur = format_auteur(info["auteur"])
        struct.taxon.rang = gbif_cherche_rang(cur["rank"])
        if "eteint" in info:
            struct.taxon.eteint = info["eteint"]
        # `info["nom"]` (déjà résolu par `_taxon_info` ci-dessus, avec repli sur le nom
        # scientifique brut pour les noms que GBIF ne décompose pas, ex. les virus) plutôt que
        # `cur["canonicalName"]` : ce champ est absent des enregistrements GBIF pour ces noms-là.
        struct.taxon.nom = info["nom"].strip()
        struct.classification = "GBIF"
        struct.classification_taxobox = "GBIF"

        rangs: list[RankName] = []
        for marker in GBIF_WP:
            field = marker.lower()
            if field not in cur:
                continue
            value = cur[field]
            if marker == "KINGDOM":
                struct.regne = gbif_cherche_regne(value)
                continue
            buf = gbif_cherche_rang(marker)
            if buf == struct.taxon.rang:
                continue
            entry: dict = {"nom": value, "rang": buf}
            key_field = f"{field}Key"
            if key_field in cur:
                profiles = await adapter.species_profiles(cur[key_field])
                for p in profiles:
                    if "extinct" in p:
                        entry["eteint"] = p["extinct"]
                        break
            rangs.append(RankName.model_validate(entry))
        struct.rangs = rangs

        if not struct.regne:
            return None

        basionym_key = cur.get("basionymKey")
        if basionym_key:
            basio_record = await adapter.species_record(basionym_key)
            if basio_record and basio_record.get("canonicalName"):
                struct.basionyme = Basionym(
                    nom=basio_record["canonicalName"].strip(),
                    auteur=format_auteur((basio_record.get("authorship") or "").strip()),
                    source="GBIF",
                )

        if cur.get("numDescendants", 0) > 0:

            async def fetch_children(offset: int) -> tuple[list[RankName], bool]:
                page = await adapter.children_page(key, offset)
                out = []
                for c in page.get("results", []):
                    if c.get("rank") == "UNRANKED" or "canonicalName" not in c:
                        continue
                    child_info = await _taxon_info(adapter, c["key"])
                    if child_info is not None:
                        out.append(RankName.model_validate(child_info))
                return out, page.get("endOfRecords", True)

            liste, coupe = await collect_pages(fetch_children, limit=as_limit(options.limite_listes))
            if liste:
                struct.sous_taxons = SubTaxonList(liste=liste, source="GBIF", coupe=coupe)

        async def fetch_synonyms(offset: int) -> tuple[list[RankName], bool]:
            page = await adapter.synonyms_page(key, offset)
            out = []
            for c in page.get("results", []):
                blob = await _taxon_info(adapter, c["key"])
                if blob is not None:
                    out.append(
                        RankName(nom=blob["nom"], auteur=format_auteur(blob["auteur"]), rang=blob.get("rang"))
                    )
            return out, page.get("endOfRecords", True)

        synonymes, coupe = await collect_pages(fetch_synonyms, limit=as_limit(options.limite_listes))
        if synonymes:
            struct.synonymes = SynonymList(liste=synonymes, source="GBIF", coupe=coupe)

        return struct

    def render_bioref(self, struct: Struct) -> list[str] | None:
        data = struct.liens.get("gbif")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], data.get("rang", struct.taxon.rang), struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]
        sup = " | éteint=oui" if data.get("eteint") else ""
        nv = " | nv" if data.get("synonyme") else ""
        out = [f"{{{{GBIF | {data['id']} | {cible}{sup}{nv} | consulté le={cdate} }}}}"]
        if isinstance(data["id"], str):
            # Identifiant ChecklistBank (COL XR) plutôt que la clé numérique GBIF legacy : la
            # même fiche existe aussi sur catalogueoflife.org, d'où ce second lien. Cité avec le
            # nom/auteur propres à cette fiche COL XR (`col_xr`), pas ceux du backbone GBIF
            # ci-dessus : les deux peuvent diverger (ex. auteur absent côté GBIF), et un lien
            # {{CatalogueofLife}} doit citer la même chose que `ColModule` citerait pour la même
            # fiche, sans quoi le dédoublonnage par ligne de `_compute_ext_liens_items` ne les
            # reconnaît pas comme la même référence.
            col_xr = data["col_xr"]
            cible_col = wp_met_italiques(
                col_xr["nom"], col_xr.get("rang") or struct.taxon.rang, struct.regne
            )
            if col_xr.get("auteur"):
                cible_col += " " + col_xr["auteur"]
            sup_col = " | éteint=oui" if col_xr.get("eteint") else ""
            out.append(
                f"{{{{CatalogueofLife | {data['id']} | {cible_col}{sup_col}{nv} | "
                f"consulté le={cdate} }}}}"
            )
        return out

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("gbif")
        if not data or "id" not in data:
            return None
        path = "species" if isinstance(data["id"], int) else "taxon"
        link = simple_debug_link(struct, "gbif", f"https://www.gbif.org/{path}/{{id}}", "GBIF")
        if link and data.get("inpn_id"):
            # Même page que le module `inpn` afficherait pour ce même identifiant (voir
            # `organon.modules.inpn.module.InpnModule.debug_link`) — le lien reste utilisable
            # même quand le module `inpn` lui-même échoue (403 côté serveur, voir `taxref_related`
            # dans `_collect` ci-dessus), un navigateur normal n'étant pas concerné par ce blocage.
            link += (
                f" <a href='https://taxref.mnhn.fr/taxref-web/taxa/{data['inpn_id']}' "
                f"target='_blank' rel='noopener noreferrer'>INPN</a>"
            )
        return link


register_module(GbifModule)

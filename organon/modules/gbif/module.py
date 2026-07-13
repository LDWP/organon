"""Logique métier du module GBIF : classification, synonymes, sous-taxons, noms vernaculaires.
Ne fait aucun appel HTTP directement, voir adapter.py.
"""

from __future__ import annotations

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
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import (
    MAX_SYNONYM_HOPS,
    as_limit,
    collect_pages,
    format_auteur,
    simple_debug_link,
)
from organon.modules.gbif.adapter import GbifAdapter
from organon.modules.gbif.ranks import GBIF_WP, gbif_cherche_rang, gbif_cherche_regne


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

    def __init__(self, adapter: GbifAdapter | None = None) -> None:
        self._adapter = adapter or GbifAdapter()

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
            results = await adapter.search(struct.taxon.nom)
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
            cur = next((r for r in accepted if _regne_correspond(r)), None)
            if cur is None:
                cur = accepted[0] if accepted else None
            if cur is None:
                if not options.suivre_synonymes:
                    return None
                cur = next((r for r in results if _regne_correspond(r)), results[0])

        key = cur["key"]
        info = await _taxon_info(adapter, key)
        if info is None:
            return None

        struct.liens["gbif"] = {
            "id": key,
            "auteur": format_auteur(info["auteur"]),
            "nom": info["nom"],
            **({"rang": info["rang"]} if "rang" in info else {}),
            **({"eteint": info["eteint"]} if "eteint" in info else {}),
        }
        if not is_classification and cur.get("kingdom"):
            # Signal de règne détecté sans appel réseau supplémentaire : le champ "kingdom" est
            # déjà présent dans la réponse de recherche utilisée ci-dessus. Voir RegneIncoherence.
            regne_detecte = gbif_cherche_regne(cur["kingdom"])
            if regne_detecte:
                struct.liens["gbif"]["regne_detecte"] = regne_detecte

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

        async def fetch_vernacular(offset: int) -> tuple[list[str], bool]:
            page = await adapter.vernacular_names_page(key, offset)
            names = [c["vernacularName"] for c in page.get("results", []) if c.get("language") == "fra"]
            return names, page.get("endOfRecords", True)

        vernaculaire, _ = await collect_pages(fetch_vernacular)
        if vernaculaire:
            struct.vernaculaire["GBIF"] = vernaculaire

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

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("gbif")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], data.get("rang", struct.taxon.rang), struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]
        sup = " | éteint=oui" if data.get("eteint") else ""
        if data.get("synonyme"):
            return f"{{{{GBIF | {data['id']} | {cible}{sup} | nv | consulté le={cdate} }}}}"
        return f"{{{{GBIF | {data['id']} | {cible}{sup} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(struct, "gbif", "https://www.gbif.org/species/{id}", "GBIF")


register_module(GbifModule)

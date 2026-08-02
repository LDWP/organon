"""Logique métier du module LPSN (List of Prokaryotic names with Standing in Nomenclature),
classification de référence pour les domaines bactérie/archaea/procaryote (voir
https://fr.wikipedia.org/wiki/Projet:Biologie/Bases_de_donn%C3%A9es_suivies).

Suivi de synonyme : `lpsn_correct_name_id` (renvoyé directement dans chaque fiche) pointe vers
l'identifiant LPSN du nom accepté, sur le même principe que `valid_AphiaID` pour WoRMS — sans
repasser par une recherche textuelle.

Classification : l'API LPSN n'a pas d'équivalent à `AphiaClassificationByAphiaID` (WoRMS) qui
renverrait la chaîne des parents en un seul appel ; chaque fiche ne porte que `lpsn_parent_id`
(son parent immédiat), donc `_walk_ancestors` remonte la chaîne un niveau à la fois jusqu'au
domaine (Bacteria/Archaea), qui joue ici le rôle que "Kingdom" joue pour ITIS/GBIF : le niveau
d'où provient `struct.regne`, exclu de `struct.rangs` pour ne pas le dupliquer (voir
`ranks.lpsn_cherche_regne`).

Type nomenclatural (`nomenclatural_type_id`, ex. l'espèce-type d'un genre) alimente
`struct.type_taxon` : le seul module actuellement capable de remplir ce champ (côté PHP historique,
seul `mod_lpsn.php` le faisait — voir `docs/md/comparaison-php-python.md`).

Hors périmètre (limitation de l'API LPSN, pas un oubli) : `struct.synonymes` et
`struct.sous_taxons`, l'API n'exposant aucune route pour lister les synonymes/sous-taxons d'un
identifiant donné (seulement recherche par critères + fiche par identifiant, voir
`adapter.py`)."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import (
    Basionym,
    RankName,
    Redirection,
    Struct,
    TaxonInfo,
    TypeTaxon,
)
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import MAX_SYNONYM_HOPS, format_auteur
from organon.modules.lpsn.adapter import LpsnAdapter
from organon.modules.lpsn.ranks import lpsn_cherche_rang, lpsn_cherche_regne


def _slug_from_address(address: str | None) -> str | None:
    """Extrait le segment final de `lpsn_address` (URL de la fiche sur lpsn.dsmz.de), seul
    identifiant accepté par le paramètre "ID" du modèle Wikipédia {{LPSN}} (ex.
    "hyphomonas-rosenbergii", pas l'identifiant numérique interne)."""
    if not address:
        return None
    return address.rstrip("/").rsplit("/", 1)[-1] or None


class LpsnModule(TaxonomyModule):
    meta = ModuleMeta(
        id="lpsn",
        can_classify=True,
        can_render_external_link=True,
        domains=["bactérie", "archaea", "procaryote"],
    )

    def __init__(self, adapter: LpsnAdapter | None = None) -> None:
        self._adapter = adapter or LpsnAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        ids = await self._adapter.advanced_search(taxon_name=struct.taxon.nom)
        if not ids:
            return None
        records = await self._adapter.fetch(ids)
        exact = [r for r in records if r.get("full_name") == struct.taxon.nom]
        if not exact:
            return None
        # Priorité au nom accepté s'il y a plusieurs correspondances exactes (rare, ex. homonymie
        # de combinaison) : `lpsn_correct_name_id` absent ou égal à son propre id = nom accepté.
        cur = next(
            (r for r in exact if r.get("lpsn_correct_name_id") in (None, r.get("id"))), exact[0]
        )
        return await self._process(struct, cur, is_classification, options, hop=0)

    async def _process(
        self, struct: Struct, cur: dict, is_classification: bool, options: GenerateOptions, hop: int
    ) -> Struct | None:
        adapter = self._adapter
        lpsn_id = cur["id"]
        rang = lpsn_cherche_rang(cur.get("category"))

        entry: dict = {"nom": cur.get("full_name") or struct.taxon.nom, "rang": rang}
        slug = _slug_from_address(cur.get("lpsn_address"))
        if slug:
            entry["id"] = slug
            entry["url"] = cur["lpsn_address"]
        if cur.get("authority"):
            entry["auteur"] = format_auteur(cur["authority"])
        struct.liens["lpsn"] = entry

        correct_id = cur.get("lpsn_correct_name_id")
        is_synonym = correct_id is not None and correct_id != lpsn_id
        if is_synonym:
            if not is_classification:
                entry["synonyme"] = True
                return struct
            if options.suivre_synonymes:
                if hop >= MAX_SYNONYM_HOPS:
                    return None
                assert correct_id is not None  # garanti par `is_synonym` ci-dessus
                accepted = await adapter.fetch_one(correct_id)
                if accepted is None:
                    return None
                struct.redirection = Redirection(nom=struct.taxon.nom)
                struct.taxon = TaxonInfo(nom=accepted.get("full_name") or struct.taxon.nom)
                return await self._process(
                    struct, accepted, is_classification, options, hop=hop + 1
                )
            # suivre_synonymes désactivé : on continue avec les données du synonyme tel quel

        if not is_classification:
            return struct

        chain, domaine_nom = await self._walk_ancestors(cur)
        struct.regne = lpsn_cherche_regne(domaine_nom)
        if not struct.regne:
            return None

        struct.taxon.nom = cur.get("full_name") or struct.taxon.nom
        struct.taxon.rang = rang
        struct.taxon.auteur = format_auteur(cur.get("authority"))

        struct.classification = "LPSN"
        struct.classification_taxobox = "LPSN"

        # `_walk_ancestors` remonte depuis le taxon demandé : `chain` est donc déjà dans l'ordre
        # proche -> lointain attendu par struct.rangs, sans inversion à faire ici (contrairement
        # à WRMS, dont la chaîne brute part de la racine).
        struct.rangs = [
            RankName(
                nom=n["full_name"],
                rang=lpsn_cherche_rang(n.get("category")),
                auteur=format_auteur(n.get("authority")),
            )
            for n in chain
            if n.get("full_name")
        ]

        basonym_id = cur.get("basonym_id")
        if basonym_id and basonym_id != lpsn_id:
            basio = await adapter.fetch_one(basonym_id)
            if basio is not None and basio.get("full_name"):
                struct.basionyme = Basionym(
                    nom=basio["full_name"],
                    auteur=format_auteur(basio.get("authority")),
                    source="LPSN",
                )

        type_id = cur.get("nomenclatural_type_id")
        if type_id:
            type_rec = await adapter.fetch_one(type_id)
            if type_rec is not None and type_rec.get("full_name"):
                struct.type_taxon = TypeTaxon(
                    nom=type_rec["full_name"],
                    rang=lpsn_cherche_rang(type_rec.get("category")),
                    auteur=format_auteur(type_rec.get("authority")),
                    source="LPSN",
                )

        return struct

    async def _walk_ancestors(self, cur: dict) -> tuple[list[dict], str | None]:
        """Remonte `lpsn_parent_id` un niveau à la fois jusqu'au domaine (Bacteria/Archaea),
        exclu de la chaîne retournée (voir docstring de tête). Renvoie `(chaîne proche->lointain
        du taxon demandé, exclue du domaine, nom du domaine ou None si jamais atteint)`."""
        chain: list[dict] = []
        node = cur
        while node.get("lpsn_parent_id"):
            parent = await self._adapter.fetch_one(node["lpsn_parent_id"])
            if parent is None:
                return chain, None
            if parent.get("category") == "domain":
                return chain, parent.get("full_name")
            chain.append(parent)
            node = parent
        return chain, None

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("lpsn")
        if not data or "id" not in data or not data.get("rang"):
            return None
        cdate = dates_recupere()
        nom = wp_met_italiques(data["nom"], data["rang"], struct.regne)
        if data.get("auteur"):
            nom = f"{nom} {data['auteur']}"
        return f"{{{{LPSN | {data['rang']} | {data['id']} | {nom} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("lpsn")
        if not data or not data.get("url"):
            return None
        return f"<a href='{data['url']}' target='_blank' rel='noopener noreferrer'>LPSN</a>"


register_module(LpsnModule)

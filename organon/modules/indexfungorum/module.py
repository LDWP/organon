"""Logique métier du module Index Fungorum : classification fongique via CABI/Kew Mycology
(indexfungorum.org/ixfwebservice), domaine `['champignon']`. Contrairement à MycoBank (backend
CMS propriétaire à champs numériques magiques, laissé de côté), Index Fungorum expose un vrai
webservice `.asmx` avec un binding `HttpGet` — une simple requête GET par opération, pas
d'enveloppe SOAP à construire (voir adapter.py).

`NameSearch` (recherche par nom) ne renvoie ni les champs de publication ni la chaîne de
classification : un second appel `NameByKey` (par `RECORD_NUMBER`) est toujours nécessaire pour
obtenir l'enregistrement complet, même une fois le nom résolu.

La chaîne de classification n'est jointe par `NameByKey` que pour les enregistrements de rang
genre et en dessous (voir ranks.py) : une recherche de rang famille ou supérieur ne porte aucun
de ces champs, traité ici comme une donnée de classification insuffisante (`collect` renvoie
None en mode classification), pas une erreur.

Résolution du nom accepté : parmi les correspondances exactes sur `NAME_OF_FUNGUS` (le
filtrage serveur par préfixe de `name_search` peut renvoyer des noms voisins), l'enregistrement
actuellement accepté est celui où `CURRENT_NAME_RECORD_NUMBER` égale son propre
`RECORD_NUMBER` (auto-référence) ; à défaut (le nom demandé est lui-même un synonyme ou un
basionyme), on suit `CURRENT_NAME_RECORD_NUMBER` via `NameByKey` jusqu'à cette auto-référence,
borné par `MAX_SYNONYM_HOPS` comme les autres modules qui suivent des synonymes (GBIF, IRMNG).

`NamesByCurrentKey` (recherche inverse par la clé du nom accepté) fournit une vraie liste de
synonymes — non paginée côté service (aucun paramètre offset dans le WSDL), tronquée
manuellement selon `limite-listes` plutôt que via `collect_pages` (qui suppose une pagination
réelle).

Aucun nom vernaculaire ni sous-taxon exposé par ce service (pas d'opération de type
"Children")."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Basionym, RankName, Redirection, Struct, SynonymList, TaxonInfo
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import MAX_SYNONYM_HOPS, as_limit, format_auteur, simple_debug_link
from organon.modules.indexfungorum.adapter import IndexFungorumAdapter
from organon.modules.indexfungorum.ranks import CLASSIFICATION_LADDER, UNRESOLVED_PLACEHOLDER, ixf_rang, ixf_regne

MAX_NUMBER = 50


class IndexFungorumModule(TaxonomyModule):
    meta = ModuleMeta(
        id="indexfungorum", can_classify=True, can_render_external_link=True, domains=["champignon"]
    )

    def __init__(self, adapter: IndexFungorumAdapter | None = None) -> None:
        self._adapter = adapter or IndexFungorumAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        records = await self._adapter.name_search(struct.taxon.nom, max_number=MAX_NUMBER)
        exact = [r for r in records if r.get("NAME_OF_FUNGUS") == struct.taxon.nom]
        if not exact:
            return None

        accepted_hit = next(
            (r for r in exact if r.get("CURRENT_NAME_RECORD_NUMBER") == r.get("RECORD_NUMBER")), None
        )
        if accepted_hit is not None:
            full = await self._adapter.name_by_key(accepted_hit["RECORD_NUMBER"])
        else:
            if not options.suivre_synonymes:
                return None
            full = await self._adapter.name_by_key(exact[0]["RECORD_NUMBER"])
            hop = 0
            while (
                full is not None
                and full.get("CURRENT_NAME_RECORD_NUMBER")
                and full["CURRENT_NAME_RECORD_NUMBER"] != full["RECORD_NUMBER"]
            ):
                if hop >= MAX_SYNONYM_HOPS:
                    return None
                full = await self._adapter.name_by_key(full["CURRENT_NAME_RECORD_NUMBER"])
                hop += 1
        if full is None:
            return None

        is_redirect = full["NAME_OF_FUNGUS"] != struct.taxon.nom

        ixf_link: dict = {
            "id": full["RECORD_NUMBER"],
            "nom": full["NAME_OF_FUNGUS"],
            "rang": ixf_rang(full.get("INFRASPECIFIC_RANK")),
            "auteur": format_auteur(full.get("AUTHORS")),
        }
        if is_redirect:
            ixf_link["synonyme"] = True
        struct.liens["indexfungorum"] = ixf_link

        if is_redirect:
            if not is_classification:
                return struct
            if not options.suivre_synonymes:
                return struct
            struct.redirection = Redirection(nom=struct.taxon.nom)
            struct.taxon = TaxonInfo(nom=full["NAME_OF_FUNGUS"])

        if not is_classification:
            return struct

        if not full.get("Genus_name"):
            return None  # rang famille et au-dessus : NameByKey ne joint pas la hiérarchie

        struct.regne = ixf_regne(full.get("Kingdom_name"))
        struct.taxon.rang = ixf_rang(full.get("INFRASPECIFIC_RANK"))
        struct.taxon.auteur = format_auteur(full.get("AUTHORS"))

        struct.classification = "Index Fungorum"
        struct.classification_taxobox = "Index Fungorum"

        rangs: list[RankName] = []
        for field, rang_fr in CLASSIFICATION_LADDER:
            value = full.get(field)
            if not value or value == UNRESOLVED_PLACEHOLDER or value == full["NAME_OF_FUNGUS"]:
                continue
            rangs.append(RankName(nom=value, rang=rang_fr))
        struct.rangs = rangs

        basionym_id = full.get("BASIONYM_RECORD_NUMBER")
        if basionym_id and basionym_id != full["RECORD_NUMBER"]:
            basio = await self._adapter.name_by_key(basionym_id)
            if basio is not None:
                struct.basionyme = Basionym(
                    nom=basio["NAME_OF_FUNGUS"], auteur=format_auteur(basio.get("AUTHORS")), source="Index Fungorum"
                )

        synonym_records = await self._adapter.names_by_current_key(full["RECORD_NUMBER"])
        synonymes = [
            RankName(
                nom=s["NAME_OF_FUNGUS"],
                auteur=format_auteur(s.get("AUTHORS")),
                rang=ixf_rang(s.get("INFRASPECIFIC_RANK")),
            )
            for s in synonym_records
            if s.get("RECORD_NUMBER") != full["RECORD_NUMBER"]
        ]
        if synonymes:
            limit = as_limit(options.limite_listes)
            coupe = limit is not None and len(synonymes) > limit
            struct.synonymes = SynonymList(
                liste=synonymes[:limit] if coupe else synonymes, source="Index Fungorum", coupe=coupe
            )

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Aucun modèle "Index Fungorum" sur Wikipédia en français (vérifié en direct via
        l'API MediaWiki — 0 résultat dans l'espace de noms Modèle) : `{{Lien web}}` générique,
        même convention que OTL/iNaturalist."""
        data = struct.liens.get("indexfungorum")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], data.get("rang", struct.taxon.rang), struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]
        post = " <small>(non valide)</small>" if data.get("synonyme") else ""
        url = f"http://www.indexfungorum.org/names/NamesRecord.asp?RecordID={data['id']}"
        return (
            f"{{{{Lien web | langue=en | titre={cible} | url={url} "
            f"| site=Index Fungorum | consulté le={cdate} }}}}{post}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(
            struct,
            "indexfungorum",
            "http://www.indexfungorum.org/names/NamesRecord.asp?RecordID={id}",
            "Index Fungorum",
        )


register_module(IndexFungorumModule)

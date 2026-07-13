"""Module archivé : retiré du registre actif (voir organon.modules.bootstrap), plus intégré à
l'application. OTL n'est consultable que par API, sans page web équivalente qu'un contributeur
pourrait citer et vérifier a posteriori — incompatible avec l'exigence de vérifiabilité d'un
article Wikipédia, qui veut qu'une source citée reste consultable par un lecteur humain. Le code
reste ici tel quel (fonctionnel, juste plus appelé) au cas où cette contrainte serait
reconsidérée ; ne pas réenregistrer sans revoir ce point.

Logique métier du module Open Tree of Life (OTL) : classification via la taxonomie
synthétique OTT, qui fusionne plusieurs référentiels externes (NCBI, GBIF, WoRMS, IRMNG,
SILVA...) en un seul arbre. Contrairement à ces sources, OTL n'expose ni auteur ni nom
vernaculaire — seulement une lignée taxonomique déjà résolue.

La résolution de synonyme se fait côté serveur : `tnrs/match_names` renvoie déjà le taxon
accepté quand le nom recherché est un synonyme (`is_synonym: true`, le champ `taxon` porte le
nom accepté) — pas de boucle de suivi de synonyme à implémenter côté client, contrairement à
GBIF/IRMNG.

Sans identifiant de source externe fiable et stable pour un lien de type Bioref (OTL n'a pas
d'équivalent du modèle `{{GBIF}}`/`{{IPNI}}` sur Wikipédia en français, vérifié en direct —
aucun modèle "Open Tree of Life"/"OTL" n'existe), `render_bioref` utilise le modèle générique
`{{Lien web}}` plutôt que d'inventer un modèle dédié inexistant.

Pas de `ranks.py` propre à un jeu de rangs fermé comme GBIF : voir `ranks.py` de ce module pour
le détail de la reconstruction du règne et le filtrage des rangs informels de la lignée OTT."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Redirection, Struct, SubTaxonList, SynonymList, TaxonInfo
from organon.core.registry import ModuleMeta, TaxonomyModule
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules._archive.otl.adapter import OtlAdapter
from organon.modules._archive.otl.ranks import otl_rang, otl_regne
from organon.modules.common import as_limit, simple_debug_link


class OtlModule(TaxonomyModule):
    meta = ModuleMeta(id="otl", can_classify=True, can_render_external_link=True, domains="all")

    def __init__(self, adapter: OtlAdapter | None = None) -> None:
        self._adapter = adapter or OtlAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        matches = await self._adapter.match_names(struct.taxon.nom)
        candidates = [m for m in matches if not m.get("is_approximate_match")] or matches
        if not candidates:
            return None
        match = candidates[0]
        taxon = match["taxon"]

        otl_link: dict = {"id": taxon["ott_id"], "nom": taxon["name"]}
        rang = otl_rang(taxon.get("rank") or "")
        if rang:
            otl_link["rang"] = rang
        struct.liens["otl"] = otl_link

        if match.get("is_synonym"):
            if not is_classification:
                otl_link["synonyme"] = True
                return struct
            if not options.suivre_synonymes:
                return struct
            struct.redirection = Redirection(nom=struct.taxon.nom)
            struct.taxon = TaxonInfo(nom=taxon["name"])

        if not is_classification:
            return struct

        info = await self._adapter.taxon_info(taxon["ott_id"], include_lineage=True)
        if info is None:
            return None

        struct.taxon.nom = info["name"]
        if rang:
            struct.taxon.rang = rang

        regne = None
        rangs: list[RankName] = []
        for node in info.get("lineage", []):
            node_rank = node.get("rank")
            if node_rank in ("kingdom", "domain"):
                regne = otl_regne(node["name"])
                break
            wp_rang = otl_rang(node_rank or "")
            if wp_rang:
                rangs.append(RankName(nom=node["name"], rang=wp_rang))
        if not regne:
            return None
        struct.regne = regne
        struct.rangs = rangs

        struct.classification = "OTL"
        struct.classification_taxobox = "Open Tree of Life"

        limit = as_limit(options.limite_listes)

        children_info = await self._adapter.taxon_info(taxon["ott_id"], include_children=True)
        children = (children_info or {}).get("children") or []
        if children:
            liste = [RankName(nom=c["name"], rang=otl_rang(c.get("rank") or "")) for c in children]
            coupe = limit is not None and len(liste) > limit
            if coupe:
                liste = liste[:limit]
            struct.sous_taxons = SubTaxonList(liste=liste, source="OTL", coupe=coupe)

        synonyms = taxon.get("synonyms") or []
        if synonyms:
            coupe = limit is not None and len(synonyms) > limit
            noms = synonyms[:limit] if coupe else synonyms
            struct.synonymes = SynonymList(liste=[RankName(nom=s) for s in noms], source="OTL", coupe=coupe)

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("otl")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], data.get("rang", struct.taxon.rang), struct.regne)
        post = " <small>(non valide)</small>" if data.get("synonyme") else ""
        url = f"https://tree.opentreeoflife.org/taxonomy/browse?id={data['id']}"
        return (
            f"{{{{Lien web | langue=en | titre={cible} | url={url} "
            f"| site=Open Tree of Life | consulté le={cdate} }}}}{post}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(
            struct, "otl", "https://tree.opentreeoflife.org/taxonomy/browse?id={id}", "OTL"
        )

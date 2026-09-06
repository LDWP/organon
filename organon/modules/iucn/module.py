"""Logique métier du module IUCN Red List (statut de conservation). Module d'enrichissement
uniquement (pas de classification) : alimente `{{Taxobox UICN}}` (voir
`organon.core.rendering.sections.render_taxobox`) et le modèle de référence `{{UICN}}` (voir
`render_bioref`), les deux étant systématiquement appariés par la documentation wiki du modèle
(« N'oubliez pas d'ajouter un {{UICN}} à la page »). `{{UICN}}` attend en premier paramètre le
code numérique du taxon sur iucnredlist.org (ex. 15951 pour Panthera leo, vérifié en direct sur
https://fr.wikipedia.org/wiki/Modèle:UICN) : c'est le `sis_id` déjà présent dans la réponse
`/taxa/scientific_name` (aucun appel réseau supplémentaire), et il correspond exactement à la
propriété Wikidata P627 "IUCN taxon ID" (vérifiée en direct sur wikidata.org).

Remplace l'ancien passager posé par le module GBIF (`struct.liens["uicn"] = {"risque": code}`,
voir l'historique de `organon.modules.gbif.module`) : GBIF n'expose que le code de catégorie, pas
les critères d'évaluation (ex. "A2abd+4abd") — paramètre optionnel déjà lu par `render_taxobox`
mais resté vide faute de source. Seule l'API IUCN v4 directe les fournit. La clé `struct.liens`
utilisée ici est désormais `"iucn"`, alignée sur `meta.id` : l'ancienne clé `"uicn"` (héritée du
passager GBIF) empêchait silencieusement `_compute_ext_liens_items`
(`organon.core.rendering.sections`) de retrouver ce module par son id lors de l'assemblage du
bloc `{{Bioref}}`, ce qui rendait `render_bioref` inatteignable quel que soit son contenu.

Un taxon porte souvent plusieurs évaluations à la fois, une par périmètre géographique (Global,
Europe, Méditerranée...), chacune pouvant être "latest" dans son propre périmètre — voir
`_evaluation_globale_retenue` : seule l'évaluation de périmètre Global (code "1") la plus
récente sert de statut de référence, seule pertinente pour une infobox généraliste."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import format_auteur
from organon.modules.iucn.adapter import IucnAdapter

_MARQUEURS_RANG = {"subsp.", "ssp.", "var.", "f.", "forma"}
_PERIMETRE_GLOBAL = "1"


def _decoupe_nom_scientifique(nom: str) -> tuple[str, str, str | None] | None:
    """Découpe un nom scientifique en (genre, épithète spécifique, épithète infraspécifique),
    tel qu'attendu par `genus_name`/`species_name`/`infra_name` de l'API IUCN — ignore un
    éventuel marqueur de rang explicite (ex. "subsp.") pour ne garder que les épithètes. None si
    le nom ne compte pas au moins deux mots (l'UICN n'évalue jamais un rang supra-spécifique)."""
    mots = [m for m in nom.split() if m not in _MARQUEURS_RANG]
    if len(mots) < 2:
        return None
    genre, espece, *reste = mots
    return genre, espece, (reste[-1] if reste else None)


def _evaluation_globale_retenue(assessments: list[dict]) -> dict | None:
    return next(
        (
            a
            for a in assessments
            if a.get("latest")
            and any(s.get("code") == _PERIMETRE_GLOBAL for s in a.get("scopes") or [])
        ),
        None,
    )


class IucnModule(TaxonomyModule):
    meta = ModuleMeta(
        id="iucn",
        can_classify=False,
        can_render_external_link=True,
        domains="all",
        # Priorité la plus haute du dépôt (au-dessus de COL, 999) : `EnrichmentRunner.run`
        # fusionne `struct.liens` module par module dans l'ordre croissant de priorité, dernier
        # appliqué gagnant sur une clé partagée (voir organon/api/routes/generate.py). Personne
        # d'autre n'écrit `liens["iucn"]` aujourd'hui, mais GBIF écrivait `liens["uicn"]` avant ce
        # module (voir git history) : si cette écriture était réintroduite par erreur, cette
        # priorité garantit que la donnée UICN directe (avec critère d'évaluation) l'emporte
        # toujours sur un passager plus pauvre, plutôt que l'inverse silencieux.
        priority=1000,
    )

    def __init__(self, adapter: IucnAdapter | None = None) -> None:
        self._adapter = adapter or IucnAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        if is_classification:
            return None  # l'UICN ne fournit jamais de classification

        parsed = _decoupe_nom_scientifique(struct.taxon.nom)
        if parsed is None:
            return None
        genre, espece, infra = parsed

        data = await self._adapter.scientific_name(genre, espece, infra)
        if not data:
            return None

        evaluation = _evaluation_globale_retenue(data.get("assessments") or [])
        if evaluation is None or not evaluation.get("red_list_category_code"):
            return None

        taxon = data.get("taxon") or {}
        struct.liens["iucn"] = {
            "id": taxon.get("sis_id"),
            "nom": taxon.get("scientific_name") or struct.taxon.nom,
            "auteur": format_auteur(taxon.get("authority")),
            "risque": evaluation["red_list_category_code"],
            "critere": evaluation.get("criteria") or "",
            "url": evaluation.get("url"),
        }
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("iucn")
        if not data or not data.get("id"):
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], struct.taxon.rang, struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]
        return f"{{{{UICN | {data['id']} | {cible} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("iucn")
        if not data or not data.get("url"):
            return None
        return f"<a href='{data['url']}' target='_blank' rel='noopener noreferrer'>UICN</a>"


register_module(IucnModule)

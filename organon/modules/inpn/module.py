"""Logique métier du module INPN/TAXREF : classification (lignée reconstruite à partir du fil
d'Ariane de la fiche détail, chaque ancêtre résolu individuellement pour connaître son rang —
voir adapter.py) et noms vernaculaires français.

Suivi de synonyme non implémenté (contrairement à ITIS/GBIF/WoRMS) : un taxon dont la
correspondance exacte n'est pas "nom de référence" (`validite == "NR"`) est ignoré plutôt que
suivi vers son nom accepté — portée volontairement réduite pour cette première version, à
étendre si besoin (voir docs/log.md)."""

from __future__ import annotations

import asyncio
import re

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import format_auteur
from organon.modules.inpn.adapter import InpnAdapter
from organon.modules.inpn.ranks import RANGS_REGNE, inpn_cherche_rang, inpn_cherche_regne

# Racine technique de TAXREF (pas un taxon biologique réel) : toujours en tête du fil
# d'Ariane, filtrée avant résolution plutôt que de lui chercher un rang.
_ROOT_NAME = "Biota"

# TAXREF n'indexe jamais la notation "Genre (Sous-genre)" : le sous-genre y est stocké sous son
# seul nom (`lbNom`), identique à celui du genre pour le sous-genre nominotypique (ex.
# "Eupelmus (Eupelmus)" -> lbNom "Eupelmus", rang SSGN, à côté du genre "Eupelmus" lui-même,
# rang GN, même lbNom) — une recherche littérale avec parenthèse ne renvoie donc jamais rien.
_SUBGENUS_RE = re.compile(r"^(?P<genre>\S+)\s*\((?P<sousgenre>\S+)\)$")


class InpnModule(TaxonomyModule):
    meta = ModuleMeta(
        id="inpn", can_classify=True, can_render_external_link=True, domains="all", priority=500
    )

    def __init__(self, adapter: InpnAdapter | None = None) -> None:
        self._adapter = adapter or InpnAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        adapter = self._adapter
        taxon = struct.taxon.nom

        subgenre = _SUBGENUS_RE.match(taxon)
        nom_recherche = subgenre.group("sousgenre") if subgenre else taxon

        def _rang_correspond(r: dict) -> bool:
            # Sans parenthèse dans la requête, écarte le sous-genre nominotypique homonyme du
            # genre (même lbNom, rang SSGN) pour ne jamais le retenir à la place du genre lui-même
            # au hasard de l'ordre de l'API — avec parenthèse, exige au contraire ce rang SSGN.
            code = (r.get("rang") or {}).get("rang")
            return code == "SSGN" if subgenre else code != "SSGN"

        results = await adapter.search(nom_recherche)
        match = next(
            (
                r
                for r in results
                if r.get("lbNom") == nom_recherche
                and r.get("validite") == "NR"
                and _rang_correspond(r)
            ),
            None,
        )
        if match is None or not match.get("cdNom"):
            return None

        cd_nom = match["cdNom"]
        auteur = format_auteur(match.get("lbAuteur"))

        struct.liens["inpn"] = {"id": cd_nom, "nom": taxon}
        if auteur:
            struct.liens["inpn"]["auteur"] = auteur

        html = await adapter.detail_html(cd_nom)
        vernaculaire = adapter.parse_vernacular_french(html)
        if vernaculaire:
            struct.vernaculaire["INPN"] = vernaculaire

        if not is_classification:
            return struct

        rang_code = (match.get("rang") or {}).get("rang")
        rang_wp = inpn_cherche_rang(rang_code or "")
        if rang_wp == "NOTFOUND":
            return None
        struct.taxon.rang = rang_wp
        if auteur:
            struct.taxon.auteur = auteur

        ancestors = [(aid, nom) for aid, nom in adapter.parse_breadcrumb(html) if nom != _ROOT_NAME]
        ancestor_results = await asyncio.gather(*(adapter.search(nom) for _, nom in ancestors))

        rangs: list[RankName] = []
        regne_nom: str | None = None
        for (anc_id, anc_nom), anc_matches in zip(ancestors, ancestor_results, strict=True):
            anc_match = next(
                (
                    r
                    for r in anc_matches
                    if r.get("cdNom") == anc_id and r.get("lbNom") == anc_nom
                ),
                None,
            )
            if anc_match is None:
                continue
            anc_rang_wp = inpn_cherche_rang((anc_match.get("rang") or {}).get("rang") or "")
            if anc_rang_wp == "règne":
                regne_nom = anc_nom
                continue
            if anc_rang_wp == "NOTFOUND" or anc_rang_wp in RANGS_REGNE:
                continue
            rangs.append(
                RankName(
                    nom=anc_nom, rang=anc_rang_wp, auteur=format_auteur(anc_match.get("lbAuteur"))
                )
            )
        rangs.reverse()  # fil d'Ariane : racine -> feuille ; struct.rangs veut proche -> lointain
        struct.rangs = rangs

        if regne_nom:
            struct.regne = inpn_cherche_regne(regne_nom)

        struct.classification = "TAXREF"
        struct.classification_taxobox = "inpn"
        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("inpn")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], struct.taxon.rang, struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]
        return f"{{{{INPN | {data['id']} | {cible} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("inpn")
        if not data or "id" not in data:
            return None
        return (
            f"<a href='https://taxref.mnhn.fr/taxref-web/taxa/{data['id']}' target='_blank' "
            f"rel='noopener noreferrer'>INPN</a>"
        )


register_module(InpnModule)

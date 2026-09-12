"""Logique métier du module ZooBank : registre officiel des actes de nomenclature zoologique
(ICZN), servi via ChecklistBank dataset 2037 — voir `adapter.py`. Domaine `["animal"]` (le
Code international de nomenclature zoologique ne couvre que les animaux).

Contrairement à `organon.modules.col`/`organon.modules.bryonames` (même plateforme, mais
classification à part entière), ZooBank n'est PAS traité comme une source de classification
(`can_classify=False`, comme `organon.modules.ipni`) : c'est un registre d'actes de
nomenclature (qui a publié quel nom, où, quand), pas un référentiel taxonomique qui tranche une
hiérarchie ou une synonymie. Vérifié en direct que la chaîne `classification`/le statut
accepté/synonyme de ce dataset ne reflètent pas un avis taxonomique actuel fiable (ex.
"Bufo vulgaris" Laurenti, 1768 y est marqué "accepted" alors que c'est un synonyme reconnu de
longue date de *Bufo bufo*) — cohérent avec l'origine réelle du dataset (voir plus bas) : pas de
suivi de synonymes ni de champs `rangs`/`sous_taxons`/`synonymes` ici, seulement un
enrichissement (auteur, rang, citation de la publication originale), sur le principe de
[[feedback_no_cross_source_data_correction]] (ne jamais laisser une source non fiable sur un
point injecter une opinion de classification).

Publication originale (`struct.originale`) : `usage.accordingTo` donne directement une citation
texte formatée de l'acte de nomenclature d'origine, sans appel réseau supplémentaire — c'est la
donnée la plus proche de la mission réelle de ZooBank, écrite inconditionnellement comme IPNI
(limitation de priorité pré-existante en cas d'écriture concurrente, voir
`organon.modules.ipni.module`).

Lien de citation (`render_bioref`/`debug_link`) : le champ `name.link` renvoyé par l'API
(`http://zoobank.org/<uuid>`) a été vérifié en direct comme non exploitable — redirection 302
suivie d'un 404 sur le vrai zoobank.org, ce champ étant fabriqué par ChecklistBank à partir de
l'identifiant interne, pas une véritable LSID ZooBank (`dwc:scientificNameID` du DwCA brut
n'est lui non plus qu'un UUID interne, pas une LSID `urn:lsid:zoobank.org:...` ; le nom du
dataset source, "Global Names Usage Bank", confirme qu'il s'agit d'un export retraité, pas d'un
export natif de zoobank.org). `zoobank.org` lui-même est par ailleurs bloqué par une
vérification anti-robot (reCAPTCHA sur toute page, vérifié en direct). Le lien utilisé est donc
systématiquement la fiche ChecklistBank du taxon (`checklistbank.org/dataset/2037/taxon/<id>`),
comme repli déjà documenté pour `bryonames` — bloqué par un défi anti-robot pour un navigateur
automatisé (vérifié en direct), mais seul lien qui identifie correctement l'enregistrement pour
un lecteur humain.

Aucun modèle `{{ZooBank}}` dédié n'existe sur Wikipédia en français pour ce module (vérifié en
direct : 0 résultat sur le titre `Modèle:ZooBank` et sur une recherche dans l'espace de noms
Modèle) : `render_bioref` utilise le modèle générique `{{Lien web}}`, comme Bryonames/OTL/
iNaturalist."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.common import format_auteur, simple_debug_link
from organon.modules.zoobank.adapter import DATASET_ID, ZoobankAdapter
from organon.modules.zoobank.ranks import zoobank_cherche_rang

_TAXON_URL = f"https://www.checklistbank.org/dataset/{DATASET_ID}/taxon/{{id}}"


class ZoobankModule(TaxonomyModule):
    meta = ModuleMeta(
        id="zoobank", can_classify=False, can_render_external_link=True, domains=["animal"]
    )

    def __init__(self, adapter: ZoobankAdapter | None = None) -> None:
        self._adapter = adapter or ZoobankAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        candidats = await self._adapter.search(struct.taxon.nom)
        exact = [r for r in candidats if r["usage"]["name"]["scientificName"] == struct.taxon.nom]
        if not exact:
            return None

        cur = next((r for r in exact if r["usage"]["status"] == "accepted"), exact[0])
        usage = cur["usage"]
        name = usage["name"]

        struct.liens["zoobank"] = {
            "id": cur["id"],
            "nom": name["scientificName"],
            "auteur": format_auteur(name.get("authorship")),
            "rang": zoobank_cherche_rang(name["rank"]),
        }

        struct.originale = usage.get("accordingTo")

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("zoobank")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        cible = wp_met_italiques(data["nom"], data.get("rang") or struct.taxon.rang, struct.regne)
        if data.get("auteur"):
            cible += " " + data["auteur"]
        url = _TAXON_URL.format(id=data["id"])
        return (
            f"{{{{Lien web | langue=en | titre={cible} | url={url} "
            f"| site=ZooBank | consulté le={cdate} }}}}"
        )

    def debug_link(self, struct: Struct) -> str | None:
        return simple_debug_link(struct, "zoobank", _TAXON_URL, "ZooBank")


register_module(ZoobankModule)

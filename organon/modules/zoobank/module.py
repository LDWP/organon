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
(`http://zoobank.org/<uuid>`) redirige vers la fiche `/NomenclaturalActs/<uuid>` du vrai
zoobank.org et y affiche l'enregistrement complet (auteur, publication, renvois BHL/ITIS quand
disponibles) — vérifié en direct au navigateur réel sur plusieurs taxons. Un sondage initial au
client HTTP nu avait laissé croire ce lien mort (redirection suivie d'un 404) : c'est en fait le
bandeau anti-robot de zoobank.org intercepté par un client sans JavaScript, pas une propriété du
lien lui-même — confirmé en le rechargeant, y compris avec un simple `curl`, une fois le défi
passé. Repli sur la fiche ChecklistBank du taxon (`checklistbank.org/dataset/2037/taxon/<id>`)
seulement si `link` est absent, par défense — non rencontré en pratique sur ce dataset, mais
même posture que `bryonames` face à un champ optionnel de la même plateforme.

`render_bioref` utilise le modèle dédié `{{ZooBank}}` (créé sur Wikipédia en français à la
suite de ce module, sur le modèle de `{{IPNI}}`) : comme `{{IPNI}}`/`{{Tropicos}}`, ce modèle
met lui-même son paramètre 2 en italique — le nom y est donc passé brut, pas pré-italicisé via
`wp_met_italiques` contrairement à Bryonames/Index Fungorum (repli `{{Lien web}}`, sans modèle
dédié)."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.support import dates_recupere
from organon.modules.common import format_auteur
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
            "link": name.get("link"),
        }

        struct.originale = usage.get("accordingTo")

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        """Le nom n'est PAS pré-italicisé ici : `{{ZooBank}}` met lui-même son paramètre 2 en
        italique (même convention que `{{IPNI}}`)."""
        data = struct.liens.get("zoobank")
        if not data or "id" not in data:
            return None
        cdate = dates_recupere()
        auteur = f" | {data['auteur']}" if data.get("auteur") else ""
        return f"{{{{ZooBank | {data['id']} | {data['nom']}{auteur} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("zoobank")
        if not data or "id" not in data:
            return None
        url = data.get("link") or _TAXON_URL.format(id=data["id"])
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>ZooBank</a>"


register_module(ZoobankModule)

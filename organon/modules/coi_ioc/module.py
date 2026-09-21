"""Logique métier du module COI/IOC (« IOC World Bird List », Congrès ornithologique
international) : classification des oiseaux (classe Aves) via ChecklistBank dataset 2036 — voir
`adapter.py`. Domaine restreint à `["oiseau"]` (sous-domaine dédié de l'arbre de domaines
Organon, contrairement à WCO/Bryonames qui n'ont pas de sous-domaine propre) : un taxon hors
Aves n'y figure simplement pas, `collect` renvoie alors None sans qu'aucune restriction
explicite ne soit nécessaire ici.

Aucune résolution de synonymes : vérifié en direct, ce dataset ne porte que des noms acceptés
(`GET .../nameusage/search?status=synonym` renvoie `total: 0` sur les 33 722 usages, et la
facette `status` du dataset entier n'expose que la valeur "accepted" — `/taxon/<id>/synonyms`
renvoie systématiquement un objet vide) : même situation que
`organon.modules.wsc.module` (export CSV "all currently valid species"), mais ici confirmée sur
l'API elle-même plutôt que déduite de la documentation de la source. Une recherche sur un nom
synonyme échoue donc simplement (`search` ne le trouve pas), pas de branche de repli à coder.
`statut_detecte` est néanmoins toujours renseigné à "accepté" dans `struct.liens["coi_ioc"]` :
ce n'est pas une hypothèse sur ce module lui-même, mais un contrat lu par
`organon.core.selectors.coherence` pour détecter une incohérence si un *autre* module de
classification traitait ce même taxon comme synonyme.

Le règne n'est jamais déduit de `classification` : la chaîne ne porte aucun rang au-dessus
d'"infraclass" (vérifié en direct — `GET .../dataset/2036/tree` renvoie Palaeognathae et
Neognathae, les deux seules infraclasses d'Aves, comme unique racine) — `struct.regne` est donc
fixé à "animal" en dur, et la chaîne classe/embranchement (Aves/Chordata) injectée au-dessus de
l'infraclasse, même principe que `organon.modules.wco.module._CHAINE_FIXE`.

Aucun modèle `{{Avibase}}` utilisable : il attend un identifiant Avibase propre (`avibaseId`,
ex. F7504353640C1055) qu'aucun champ de ce dataset ne fournit — le déduire d'une autre source
reviendrait à une correction inter-source, écartée par principe (voir
`organon/core/data/db_inventory.yaml`, note du module). `render_bioref` utilise donc le modèle
dédié `{{COI}}` (existe sur Wikipédia en français, vérifié en direct), qui n'a besoin que du nom
de famille et du taxon cité — pas d'identifiant externe. Sa construction d'URL interne
(`{{COI/url}}`) pointe vers `worldbirdnames.org/Family/<nom>`, une page vérifiée morte en
direct (site restructuré, voir `adapter.py`) : ceci est un problème côté modèle Wikipédia, hors
du périmètre d'organon qui ne fournit que les paramètres scientifiques, pas l'URL. Repli sur
aucun lien (`render_bioref` renvoie None) si aucune famille n'est identifiable dans la chaîne
`classification` et que le taxon cité n'est pas lui-même une famille : `{{COI}}` n'a pas d'usage
défini pour un rang supérieur.

`debug_link` (usage interne, pas publié sur le wiki) pointe vers la fiche ChecklistBank du taxon
— bloquée par un contrôle anti-bot pour un client automatisé (vérifié en direct, même situation
que `bryonames`/`zoobank`), mais seul lien qui identifie correctement l'enregistrement."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct, SubTaxonList
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.core.rendering.grammar import wp_met_italiques
from organon.core.rendering.support import dates_recupere
from organon.modules.coi_ioc.adapter import DATASET_ID, CoiIocAdapter
from organon.modules.coi_ioc.ranks import coi_ioc_cherche_rang
from organon.modules.common import as_limit, collect_pages, format_auteur

_CHAINE_FIXE = (
    RankName(nom="Aves", rang="classe"),
    RankName(nom="Chordata", rang="embranchement"),
)
"""COI/IOC ne couvre que cette unique classe/embranchement (tout le catalogue est Aves), absent
de la chaîne `classification` renvoyée par l'API (plafonnée à "infraclass") : injecté en dur
plutôt qu'interrogé."""


class CoiIocModule(TaxonomyModule):
    meta = ModuleMeta(
        id="coi_ioc",
        can_classify=True,
        can_render_external_link=True,
        domains=["oiseau"],
    )

    def __init__(self, adapter: CoiIocAdapter | None = None) -> None:
        self._adapter = adapter or CoiIocAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        adapter = self._adapter

        candidats = await adapter.search(struct.taxon.nom)
        if not candidats:
            return None

        cur = candidats[0]
        usage = cur["usage"]
        name = usage["name"]
        taxon_id = cur["id"]
        rang = coi_ioc_cherche_rang(name["rank"])
        classification = cur.get("classification", [])
        famille = next((c["name"] for c in classification if c.get("rank") == "family"), None)
        if famille is None and rang == "famille":
            famille = name["scientificName"]

        struct.liens["coi_ioc"] = {
            "id": taxon_id,
            "nom": name["scientificName"],
            "auteur": format_auteur(name.get("authorship")),
            "rang": rang,
            "famille": famille,
            "statut_detecte": "accepté",
            **({"eteint": usage["extinct"]} if "extinct" in usage else {}),
        }

        if not is_classification:
            return struct

        struct.taxon.auteur = format_auteur(name.get("authorship"))
        struct.taxon.rang = rang
        if "extinct" in usage:
            struct.taxon.eteint = usage["extinct"]
        struct.taxon.nom = name["scientificName"].strip()
        struct.classification = "COI"
        struct.classification_taxobox = "COI"
        struct.regne = "animal"

        struct.rangs = [
            RankName(
                nom=c["name"],
                rang=coi_ioc_cherche_rang(c["rank"]),
                auteur=format_auteur(c.get("authorship")),
            )
            for c in reversed(classification)
            if c.get("id") != taxon_id
        ] + list(_CHAINE_FIXE)

        async def fetch_children(offset: int) -> tuple[list[RankName], int, bool]:
            page = await adapter.children_page(taxon_id, offset)
            raw = page.get("result", [])
            out = []
            for c in raw:
                if c.get("rank") == "unranked" or c.get("status") != "accepted":
                    continue
                out.append(
                    RankName(
                        nom=c["name"],
                        rang=coi_ioc_cherche_rang(c["rank"]),
                        auteur=format_auteur(c.get("authorship")),
                        eteint=c.get("labelHtml", "").startswith("†") or None,
                    )
                )
            return out, len(raw), page.get("last", True)

        liste, coupe = await collect_pages(fetch_children, limit=as_limit(options.limite_listes))
        if liste:
            struct.sous_taxons = SubTaxonList(liste=liste, source="COI", coupe=coupe)

        return struct

    def render_bioref(self, struct: Struct) -> str | None:
        data = struct.liens.get("coi_ioc")
        if not data or "id" not in data or not data.get("famille"):
            return None
        cdate = dates_recupere()
        famille = data["famille"]
        if data.get("rang") == "famille":
            taxon = famille
        else:
            rang = data.get("rang") or struct.taxon.rang
            taxon = wp_met_italiques(data["nom"], rang, struct.regne)
            if data.get("auteur"):
                taxon += " " + data["auteur"]
        return f"{{{{COI | {famille} | {taxon} | consulté le={cdate} }}}}"

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("coi_ioc")
        if not data or "id" not in data:
            return None
        url = f"https://www.checklistbank.org/dataset/{DATASET_ID}/taxon/{data['id']}"
        return f"<a href='{url}' target='_blank' rel='noopener noreferrer'>COI/IOC</a>"


register_module(CoiIocModule)

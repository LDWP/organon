"""Orchestrateur du module `wikimedia` : tout ce qui touche à l'écosystème Wikimédia pour un
taxon. Un sous-dossier par site (wikidata/, commons/, species/, wiktionnaire/, wikipedia/)
plutôt qu'un adaptateur unique — pour que l'ajout d'une autre édition ou d'un autre wiki (ex.
en.wikipedia.org, ou une future méthode fr.wikipedia.org : catégories, ébauches, existence de
page) se fasse en étendant ou en ajoutant un sous-module plutôt qu'en surchargeant un fichier
commun.

Les liens transversaux (wikidata/commons/species/wiktionnaire) alimentent la section
« Autres projets » du rendu, câblée pour lire `struct.liens["wikimedia"]`
(`organon.core.rendering.sections.render_voir_aussi`) avec les sous-clés
`commons`/`ccommons`/`species`/`frwiktionary` exactement telles qu'attendues là-bas. La sous-clé
`wikipedia` (portails aujourd'hui) est lue séparément par
`organon.core.selectors.categorization.lien_pour_portail`. Ne produit jamais de citation
Bioref."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import Struct
from organon.core.registry import ModuleMeta, TaxonomyModule, register_module
from organon.modules.wikimedia.commons.adapter import CommonsAdapter
from organon.modules.wikimedia.species.adapter import SpeciesAdapter
from organon.modules.wikimedia.wikidata.adapter import WikidataAdapter
from organon.modules.wikimedia.wikipedia.adapter import WikipediaAdapter
from organon.modules.wikimedia.wiktionnaire.adapter import WiktionnaireAdapter

_RANGS_ANCRAGE_PORTAIL = ("famille", "ordre", "classe")


def _candidats_ancrage_portail(struct: Struct) -> list[tuple[str, str]]:
    candidats = []
    if struct.taxon.rang in _RANGS_ANCRAGE_PORTAIL:
        candidats.append((struct.taxon.rang, struct.taxon.nom))
    candidats.extend((r.rang, r.nom) for r in struct.rangs if r.rang in _RANGS_ANCRAGE_PORTAIL)
    return candidats


class WikimediaModule(TaxonomyModule):
    meta = ModuleMeta(
        id="wikimedia", can_classify=False, can_render_external_link=False, domains="all"
    )

    def __init__(
        self,
        wikidata: WikidataAdapter | None = None,
        commons: CommonsAdapter | None = None,
        species: SpeciesAdapter | None = None,
        wiktionnaire: WiktionnaireAdapter | None = None,
        wikipedia: WikipediaAdapter | None = None,
    ) -> None:
        self._wikidata = wikidata or WikidataAdapter()
        self._commons = commons or CommonsAdapter()
        self._species = species or SpeciesAdapter()
        self._wiktionnaire = wiktionnaire or WiktionnaireAdapter()
        self._wikipedia = wikipedia or WikipediaAdapter()

    async def collect(
        self, struct: Struct, is_classification: bool, options: GenerateOptions
    ) -> Struct | None:
        taxon = struct.taxon.nom
        wikimedia: dict = {}

        qid = await self._wikidata.qid(taxon)
        if qid:
            wikimedia["wikidata"] = {"id": qid}

        if await self._commons.page_exists(taxon):
            wikimedia["commons"] = {"page": taxon}
        if await self._commons.category_exists(taxon):
            wikimedia["ccommons"] = {"page": taxon}
        if await self._species.page_exists(taxon):
            wikimedia["species"] = {"page": taxon}
        if await self._wiktionnaire.page_exists(taxon):
            wikimedia["frwiktionary"] = {"page": taxon}

        if not is_classification:
            for rang, nom in _candidats_ancrage_portail(struct):
                portails = await self._wikipedia.portails(nom)
                if portails:
                    wikimedia["wikipedia"] = {"portails": portails, "rang": rang, "nom": nom}
                    break

        if not wikimedia:
            return None

        struct.liens["wikimedia"] = wikimedia
        return struct

    def debug_link(self, struct: Struct) -> str | None:
        data = struct.liens.get("wikimedia")
        if not data:
            return None
        attrs = "target='_blank' rel='noopener noreferrer'"
        out = []
        if "wikidata" in data:
            qid = data["wikidata"]["id"]
            out.append(f"<a href='https://www.wikidata.org/wiki/{qid}' {attrs}>Wikidata</a>")
        if "species" in data:
            page = data["species"]["page"]
            out.append(f"<a href='https://species.wikimedia.org/wiki/{page}' {attrs}>Species</a>")
        if "commons" in data:
            page = data["commons"]["page"]
            out.append(f"<a href='https://commons.wikimedia.org/wiki/{page}' {attrs}>Commons</a>")
        if "ccommons" in data:
            page = data["ccommons"]["page"]
            url = f"https://commons.wikimedia.org/wiki/Category:{page}"
            out.append(f"<a href='{url}' {attrs}>Commons (cat)</a>")
        if "frwiktionary" in data:
            page = data["frwiktionary"]["page"]
            out.append(f"<a href='https://fr.wiktionary.org/wiki/{page}' {attrs}>Wiktionnaire</a>")
        if "wikipedia" in data:
            titre = data["wikipedia"]["nom"].replace(" ", "_")
            rang = data["wikipedia"]["rang"]
            out.append(
                f"<a href='https://fr.wikipedia.org/wiki/{titre}' {attrs}>Portail ({rang} : "
                f"{data['wikipedia']['nom']})</a>"
            )
        return " ".join(out) if out else None


register_module(WikimediaModule)

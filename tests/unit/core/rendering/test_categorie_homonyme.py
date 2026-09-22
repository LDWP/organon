"""Catégorie homonyme d'un taxon de rang embranchement/classe/ordre/famille : appliquée si elle
existe sur frwiki ou si elle pourrait atteindre 10 membres (WP:OVERCAT, point 3), sinon on
remonte au premier rang supérieur dont la catégorie existe."""

from __future__ import annotations

from organon.core.config import GenerateOptions
from organon.core.models import RankName, Struct, SubTaxonList, TaxonInfo
from organon.core.rendering.sections import render_see_also
from organon.core.selectors.categorization import compute_footer_links


def _struct(
    nb_sous_taxons: int | None,
    existence: dict[str, bool] | None,
    *,
    coupe: bool = False,
) -> Struct:
    struct = Struct(
        taxon=TaxonInfo(name="Mecistocephalidae", rank="famille"),
        ranks=[
            RankName(name="Geophilomorpha", rank="ordre"),
            RankName(name="Chilopoda", rank="classe"),
            RankName(name="Arthropoda", rank="embranchement"),
        ],
        kingdom="animal",
    )
    if nb_sous_taxons is not None:
        struct.subtaxa = SubTaxonList(
            items=[RankName(name=f"G{i}", rank="genre") for i in range(nb_sous_taxons)],
            source="GBIF",
            truncated=coupe,
        )
    if existence is not None:
        struct.links["wikimedia"] = {"existing_categories": existence}
    return struct


def _categories(struct: Struct) -> list[str]:
    return compute_footer_links(struct, GenerateOptions())["categories"]


def _a_categorie_principale(struct: Struct) -> bool:
    return "{{catégorie principale}}" in render_see_also(struct, GenerateOptions())


def test_categorie_existante_appliquee():
    struct = _struct(3, {"Mecistocephalidae": True})
    assert "Mecistocephalidae|*" in _categories(struct)
    assert _a_categorie_principale(struct)


def test_categorie_absente_mais_dix_sous_taxons_appliquee():
    struct = _struct(11, {"Mecistocephalidae": False})
    assert "Mecistocephalidae|*" in _categories(struct)
    assert not _a_categorie_principale(struct)


def test_categorie_absente_et_moins_de_dix_remonte_au_rang_existant():
    struct = _struct(9, {"Mecistocephalidae": False, "Geophilomorpha": False, "Chilopoda": True})
    categories = _categories(struct)
    assert "Chilopoda" in categories
    assert not any(c.startswith("Mecistocephalidae") for c in categories)
    assert not any(c.startswith("Geophilomorpha") for c in categories)
    assert not _a_categorie_principale(struct)


def test_aucun_rang_superieur_existant_aucune_categorie_homonyme():
    struct = _struct(2, {"Mecistocephalidae": False, "Geophilomorpha": False})
    categories = _categories(struct)
    assert not any(
        c.startswith(("Mecistocephalidae", "Geophilomorpha", "Chilopoda")) for c in categories
    )
    assert not _a_categorie_principale(struct)


def test_liste_tronquee_ne_prouve_pas_moins_de_dix():
    struct = _struct(4, {"Mecistocephalidae": False}, coupe=True)
    assert "Mecistocephalidae|*" in _categories(struct)


def test_sous_taxons_inconnus_conserve_le_comportement_precedent():
    struct = _struct(None, {"Mecistocephalidae": False})
    assert "Mecistocephalidae|*" in _categories(struct)


def test_existence_non_verifiee_conserve_le_comportement_precedent():
    struct = _struct(2, None)
    assert "Mecistocephalidae|*" in _categories(struct)
    assert _a_categorie_principale(struct)

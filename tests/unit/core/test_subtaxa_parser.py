"""Parseur des taxons inférieurs d'un article frwiki (pur, sans réseau)."""

from __future__ import annotations

from pathlib import Path

from organon.core.subtaxa_parser import parse_sous_taxons

FIXTURES = Path(__file__).parent / "fixtures" / "soustaxons"


def _noms(article: str) -> list[str]:
    vue = parse_sous_taxons((FIXTURES / f"{article}.wiki").read_text(encoding="utf-8"))
    assert vue is not None
    return vue.noms


def test_falconidae_taxobox_taxons_et_sections():
    noms = _noms("Falconidae")
    assert {"Polyborinae", "Falconinae"} <= set(noms)
    # cible/libellé : `[[Falco (genre)|Falco]]`, `[[Falconinae|falconinés]]` (cible latine)
    assert {"Herpetotherinae", "Herpetotheres", "Falco", "Microhierax"} <= set(noms)
    # italique sans lien, modèle {{éteint}} devant le nom
    assert {"Sushkinia pliocaena", "Pediohierax", "Caracara lutosa"} <= set(noms)
    # ni ligne sans lien ni italique, ni prose
    assert not any("indet" in n or "Tribu" in n for n in noms)
    assert len(noms) == len(set(noms))


def test_felidae_listes_imbriquees_sans_auteur_ni_vernaculaire():
    noms = _noms("Felidae")
    assert {"Felinae", "Acinonyx", "Acinonyx jubatus", "Caracal", "Caracal aurata"} <= set(noms)
    assert {"Proailurinae", "Proailurus", "Pseudailurus"} <= set(noms)
    assert "Guépard" not in noms and "Caracal (genre)" not in noms
    # abréviation « P. lemanensis » : non résolvable sans deviner
    assert not any(n.startswith("P. ") for n in noms)


def test_panthera_libelle_italique_et_prose_ecartee():
    noms = _noms("Panthera")
    assert {"Panthera pardus", "Panthera pardus pardus", "Panthera pardus melas"} <= set(noms)
    assert not {"tigre", "jaguar", "Léopard"} & set(noms)
    assert not any(n.startswith("Les ") for n in noms)


def test_tyrannosaurus_taxobox_taxons_sans_synonymes_imbriques():
    assert _noms("Tyrannosaurus") == ["Tyrannosaurus rex", "Tyrannosaurus mcraeensis"]


def test_rosaceae_liste_dans_modele_colonnes():
    noms = _noms("Rosaceae")
    assert {"Acaena", "Adenostoma", "Argentina", "×Amelasorbus"} <= set(noms)
    assert len(noms) >= 20


def test_ammonitina_rangs_en_prefixe_de_ligne():
    noms = _noms("Ammonitina")
    assert {"Acanthoceratoidea", "Acanthoceratidae", "Brancoceratidae"} <= set(noms)
    assert not any(n.startswith("famille") for n in noms)


def test_canis_lupus_italiques_sans_lien_sous_sections():
    noms = _noms("Canis_lupus")
    assert noms == [
        "Canis lupus occidentalis",
        "Canis lupus nubilus",
        "Canis lupus arctos",
        "Canis lupus baileyi",
    ]


def test_zone_non_identifiee_distincte_de_vide():
    sans = (FIXTURES / "Rosaceae_sans_liste.wiki").read_text(encoding="utf-8")
    assert parse_sous_taxons(sans) is None
    vide = parse_sous_taxons("== Liste des genres ==\nAucun genre connu.\n")
    assert vide is not None and vide.noms == []


def test_ligne_douteuse_suffixee_par_point_d_interrogation_ignoree():
    vue = parse_sous_taxons("== Espèces ==\n* ''Aus bus''?\n* ''Aus cus''\n")
    assert vue is not None and vue.noms == ["Aus cus"]

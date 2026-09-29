from datetime import date

from organon.core.update_diagnosis import Proposition, Reference
from organon.modules.wikidata.quickstatements import to_quickstatements


def _prop(valeur, type_="chaine", propriete="P846", stated_in="Q1531570"):
    return Proposition(
        id="x",
        module="gbif",
        propriete=propriete,
        valeur=valeur,
        type=type_,
        reference=Reference(stated_in=stated_in, retrieved=date(2026, 9, 24)),
    )


def test_string_identifier():
    assert to_quickstatements("Q140", [_prop("5219404")]) == (
        'Q140\tP846\t"5219404"\tS248\tQ1531570\tS813\t+2026-09-24T00:00:00Z/11'
    )


def test_bare_item_qid():
    line = to_quickstatements("Q140", [_prop("Q7380", "item", "P171", "Q38840")])
    assert line == "Q140\tP171\tQ7380\tS248\tQ38840\tS813\t+2026-09-24T00:00:00Z/11"


def test_double_quotes():
    line = to_quickstatements("Q1", [_prop('Toys "R" Us')])
    assert line.split("\t")[2] == '"Toys ""R"" Us"'


def test_tab_and_newline_neutralized():
    line = to_quickstatements("Q1", [_prop("a\tb\nc")])
    assert "\n" not in line
    assert len(line.split("\t")) == 7
    assert line.split("\t")[2] == '"a b c"'


def test_unicode_kept():
    assert to_quickstatements("Q1", [_prop("Ærenea × naïve 猫")]).split("\t")[2] == (
        '"Ærenea × naïve 猫"'
    )


def test_several_proposals_one_line_each():
    out = to_quickstatements("Q1", [_prop("1"), _prop("Q2", "item", "P171")])
    assert out.split("\n") == [
        'Q1\tP846\t"1"\tS248\tQ1531570\tS813\t+2026-09-24T00:00:00Z/11',
        "Q1\tP171\tQ2\tS248\tQ1531570\tS813\t+2026-09-24T00:00:00Z/11",
    ]


def test_empty():
    assert to_quickstatements("Q1", []) == ""


def test_creation_block_create_last():
    from organon.core.update_diagnosis import Creation, LigneCreation, Reference
    from organon.modules.wikidata.quickstatements import creation_to_quickstatements

    ref = Reference(stated_in="Q38840", retrieved=date(2026, 10, 3))
    creation = Creation(
        id="c1",
        label='Panthera "leo"',
        lignes=[
            LigneCreation(propriete="P31", valeur="Q16521", type="item"),
            LigneCreation(propriete="P225", valeur='Panthera "leo"', type="chaine", reference=ref),
        ],
    )
    assert creation_to_quickstatements(creation).split("\n") == [
        "CREATE",
        'LAST\tLmul\t"Panthera ""leo"""',
        "LAST\tP31\tQ16521",
        'LAST\tP225\t"Panthera ""leo"""\tS248\tQ38840\tS813\t+2026-10-03T00:00:00Z/11',
    ]


def test_creation_attachment_after_the_block():
    from organon.core.update_diagnosis import Creation, LigneCreation, Rattachement, Reference
    from organon.modules.wikidata.quickstatements import creation_to_quickstatements

    ref = Reference(stated_in="Q38840", retrieved=date(2026, 10, 3))
    creation = Creation(
        id="c2",
        label="Felis leo",
        lignes=[LigneCreation(propriete="P31", valeur="Q16521", type="item")],
        rattachements=[Rattachement(qid="Q140", propriete="P1420", reference=ref)],
    )
    assert creation_to_quickstatements(creation).split("\n")[-1] == (
        "Q140\tP1420\tLAST\tS248\tQ38840\tS813\t+2026-10-03T00:00:00Z/11"
    )

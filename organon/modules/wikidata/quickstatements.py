"""QuickStatements V1 formatting of the Wikidata diagnosis proposals.

Export only: Organon never writes to Wikidata. Syntax:
docs/md/wikidata-conventions.md.
"""

from __future__ import annotations

from collections.abc import Iterable

from organon.core.update_diagnosis import Creation, Proposition, Reference


def _value(type_: str, value: str) -> str:
    """Format a value as a QuickStatements token."""
    if type_ == "item":
        return value
    # TAB and newline are QuickStatements separators: they would break
    # the line.
    plate = " ".join(value.split())
    return '"' + plate.replace('"', '""') + '"'


def _reference(ref: Reference) -> tuple[str, ...]:
    """Return the "stated in" and "retrieved" reference tokens."""
    return ("S248", ref.stated_in, "S813", f"+{ref.retrieved.isoformat()}T00:00:00Z/11")


def to_quickstatements(qid: str, propositions: Iterable[Proposition]) -> str:
    """Return one line per proposal.

    QuickStatements does not duplicate a value already on the item: it
    adds the references to the existing statement.
    """
    lines = []
    for p in propositions:
        lines.append(
            "\t".join((qid, p.propriete, _value(p.type, p.valeur), *_reference(p.reference)))
        )
    return "\n".join(lines)


def creation_to_quickstatements(creation: Creation) -> str:
    """Return a `CREATE` block followed by `LAST` lines.

    A multilingual label (`mul`, the default for taxon names) and one
    statement per line, with its reference when it has one.
    """
    lines = ["CREATE", "\t".join(("LAST", "Lmul", _value("chaine", creation.label)))]
    for li in creation.lignes:
        reference = _reference(li.reference) if li.reference else ()
        lines.append("\t".join(("LAST", li.propriete, _value(li.type, li.valeur), *reference)))
    # LAST still names the created item: the attachments follow the
    # block, before any other CREATE.
    for r in creation.rattachements:
        lines.append("\t".join((r.qid, r.propriete, "LAST", *_reference(r.reference))))
    return "\n".join(lines)

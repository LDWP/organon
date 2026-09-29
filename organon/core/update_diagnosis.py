"""Pure comparison of a taxon's Wikidata item with an Organon source.

Findings (`Ecart`) only, never a corrected value. Data missing from
the source is never a finding; data missing from Wikidata but known
to the source is `info`, or `suggestion` with a complete proposal.
Out of scope: author/year (P405/P574) and taxonomic-synonym state.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field

# todo: A renommer ? (littéraux JSON lus par le frontend, idem type
# "chaine"/"item").
Severite = Literal["erreur", "avertissement", "info", "suggestion"]


class StatementSansReference(BaseModel):
    """Unreferenced statement.

    `valeur` is a string or, for `type` "item", a QID; `nom` is its text
    comparable to the source.
    """

    propriete: str
    valeur: str
    type: Literal["chaine", "item"]
    nom: str


class WikidataView(BaseModel):
    """What the diagnosis reads from the item.

    Names, rank, parents and synonyms are already resolved to text.
    `unreferenced` lists statements without a reference.
    """

    qid: str
    is_taxon: bool
    names: list[str] = Field(default_factory=list)
    rank: str | None = None
    parent_names: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    external_ids: dict[str, list[str]] = Field(default_factory=dict)
    unreferenced: list[StatementSansReference] = Field(default_factory=list)
    uicn: list[str] = Field(default_factory=list)
    """Items de statut de conservation (P141) de l'item."""


class SourceView(BaseModel):
    """What the reference source reports.

    `redirected_from` is the requested name if the source followed a
    synonym; it then describes the accepted taxon.
    """

    source: str
    name: str
    rank: str | None = None
    parent_name: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    external_ids: Mapping[str, str | int] = Field(default_factory=dict)
    redirected_from: str | None = None
    uicn: str | None = None
    """Code de statut UICN (VU, EN…) rapporté par la source."""


class IdentifiantWikidata(BaseModel):
    """Wikidata property of a module and the prefix for its id."""

    propriete: str
    prefixe: str = ""


class ContextePropositions(BaseModel):
    """Data resolved upstream to build proposals.

    `resolved_items` maps a name to its target QID, None if absent or
    ambiguous; unresolved names give the same `info` finding.
    """

    retrieved: date
    database_items: Mapping[str, str] = Field(default_factory=dict)
    rank_qid: str | None = None
    resolved_items: Mapping[str, str | None] = Field(default_factory=dict)
    id_properties: Mapping[str, IdentifiantWikidata] = Field(default_factory=dict)
    proprietes_a_verifier: frozenset[str] = frozenset()
    statut_qids: Mapping[str, str] = Field(default_factory=dict)
    """Code de statut UICN -> item P141."""
    # Names resolved to zero Wikidata items (unlike homonyms, which
    # are None in `resolved_items`): only these may lead to a creation.
    noms_absents: frozenset[str] = frozenset()


class Reference(BaseModel):
    """Source database item and retrieval date of a statement."""

    stated_in: str
    retrieved: date


class Proposition(BaseModel):
    """One QuickStatements line: add `valeur` to `propriete`.

    `verifiee` is False when the module's property is not proven
    equivalent; the proposal is then unchecked by default.
    """

    id: str
    module: str
    propriete: str
    valeur: str
    type: Literal["chaine", "item"]
    reference: Reference
    verifiee: bool = True

    @computed_field  # type: ignore[prop-decorator]
    @property
    def coche_par_defaut(self) -> bool:
        """Return whether the proposal is checked by default."""
        return self.verifiee


class LigneCreation(BaseModel):
    """A statement of the item to create; P31 has no reference."""

    propriete: str
    valeur: str
    type: Literal["chaine", "item"]
    reference: Reference | None = None


class Rattachement(BaseModel):
    """Statement on an existing item pointing to the created one.

    The created item is `LAST` at export.
    """

    qid: str
    propriete: str
    reference: Reference


class Creation(BaseModel):
    """Wikidata item to create in one `CREATE` block.

    `id` is stable for identical content so export finds the checked
    creation. `coche_par_defaut` is False for bulk creations.
    """

    id: str
    label: str
    lignes: list[LigneCreation]
    rattachements: list[Rattachement] = Field(default_factory=list)
    coche_par_defaut: bool = True


class Ecart(BaseModel):
    """A finding comparing a target (Wikidata or frwiki) to a source."""

    type: str
    severite: Severite
    propriete: str
    valeur_wikidata: str | None = None
    valeur_source: str | None = None
    source: str
    message: str
    proposition: Proposition | None = None
    creation: Creation | None = None
    # What the finding concerns. For `frwiki`, `valeur_wikidata` holds
    # the article value and `valeur_source` the source value.
    cible: Literal["wikidata", "frwiki"] = "wikidata"


class ArticleFrwiki(BaseModel):
    """Revision of the frwiki article read for the diagnosis."""

    titre: str
    revid: int
    date: str
    url: str


class SectionFrwiki(BaseModel):
    """Findings of one article section.

    `comptes` and `niveau` ("wgsrpd" or the noisy "prose") come from
    the comparators; `limites` says why a comparison did not happen.
    """

    section: Literal["article", "classification", "uicn", "liens", "sous_taxons", "repartition"]
    ecarts: list[Ecart] = Field(default_factory=list)
    comptes: dict[str, Any] | None = None
    niveau: str | None = None
    limites: list[str] = Field(default_factory=list)


class DiagnosticResponse(BaseModel):
    """Full diagnosis of a taxon.

    `qid` is None when no item exists (that absence is the only
    finding). `avertissements` are diagnosis limits, not findings.
    `ecarts` is Wikidata only; frwiki has `sections_frwiki`, empty
    when the article could not be read.
    """

    qid: str | None
    taxon: str
    source_reference: str | None = None
    ecarts: list[Ecart] = Field(default_factory=list)
    article_frwiki: ArticleFrwiki | None = None
    sections_frwiki: list[SectionFrwiki] = Field(default_factory=list)
    avertissements: list[str] = Field(default_factory=list)


# taxon: class of a created item (see docs/md/wikidata-conventions.md)
TAXON_CLASS = "Q16521"


def build_creation(src: SourceView, ctx: ContextePropositions) -> Creation | None:
    """Build the taxon item to create from the source.

    None if the source describes another name than requested (a
    followed synonym). Data without a resolved value is omitted,
    never guessed.
    """
    if src.redirected_from is not None:
        return None

    def ref(module: str) -> Reference | None:
        stated_in = ctx.database_items.get(module)
        return Reference(stated_in=stated_in, retrieved=ctx.retrieved) if stated_in else None

    lignes = [LigneCreation(propriete="P31", valeur=TAXON_CLASS, type="item")]

    def ajouter(
        propriete: str, valeur: str | None, type_: Literal["chaine", "item"], module: str
    ) -> None:
        reference = ref(module)
        if valeur and reference:
            lignes.append(
                LigneCreation(propriete=propriete, valeur=valeur, type=type_, reference=reference)
            )

    ajouter("P225", src.name, "chaine", src.source)
    ajouter("P105", ctx.rank_qid, "item", src.source)
    ajouter("P141", ctx.statut_qids.get(src.uicn or ""), "item", "iucn")
    if src.parent_name:
        ajouter("P171", ctx.resolved_items.get(src.parent_name), "item", src.source)
    for module, raw in src.external_ids.items():
        cible = ctx.id_properties.get(module)
        if cible:
            ajouter(cible.propriete, cible.prefixe + str(raw), "chaine", module)

    contenu = "|".join((src.name, *(f"{li.propriete}={li.valeur}" for li in lignes)))
    return Creation(
        id=hashlib.sha1(contenu.encode()).hexdigest()[:12], label=src.name, lignes=lignes
    )


def build_synonym_creation(
    nom: str, accepted_qid: str, src: SourceView, ctx: ContextePropositions
) -> Creation | None:
    """Build a synonym item linked both ways to the accepted taxon.

    Uses reciprocal P1420. No rank, parent or ids, which describe the
    accepted taxon. None without a "stated in" item for the source.
    """
    stated_in = ctx.database_items.get(src.source)
    if stated_in is None:
        return None
    reference = Reference(stated_in=stated_in, retrieved=ctx.retrieved)
    lignes = [
        LigneCreation(propriete="P31", valeur=TAXON_CLASS, type="item"),
        LigneCreation(propriete="P225", valeur=nom, type="chaine", reference=reference),
        LigneCreation(propriete="P1420", valeur=accepted_qid, type="item", reference=reference),
    ]
    contenu = "|".join((nom, accepted_qid, src.source))
    return Creation(
        id=hashlib.sha1(contenu.encode()).hexdigest()[:12],
        label=nom,
        lignes=lignes,
        rattachements=[Rattachement(qid=accepted_qid, propriete="P1420", reference=reference)],
        coche_par_defaut=False,
    )


_CIBLE_INTROUVABLE = "item cible à créer ou homonymes, à résoudre."


def diagnose(
    wd: WikidataView, src: SourceView, ctx: ContextePropositions | None = None
) -> list[Ecart]:
    """Compare a Wikidata item with a source view.

    Return findings; `ctx` supplies what proposals need.
    """
    ctx = ctx or ContextePropositions(retrieved=date.min)

    def proposer(
        module: str, propriete: str, valeur: str | None, type_: Literal["chaine", "item"]
    ) -> Proposition | None:
        stated_in = ctx.database_items.get(module)
        if valeur is None or stated_in is None:
            return None
        digest = hashlib.sha1(
            "|".join((wd.qid, module, propriete, type_, valeur)).encode()
        ).hexdigest()
        return Proposition(
            id=digest[:12],
            module=module,
            propriete=propriete,
            valeur=valeur,
            type=type_,
            reference=Reference(stated_in=stated_in, retrieved=ctx.retrieved),
            verifiee=propriete not in ctx.proprietes_a_verifier,
        )

    def ecart(
        type_: str,
        severite: Severite,
        propriete: str,
        message: str,
        valeur_wikidata: str | None = None,
        valeur_source: str | None = None,
        proposition: Proposition | None = None,
        creation: Creation | None = None,
    ) -> Ecart:
        if severite == "suggestion" and proposition is None and creation is None:
            severite = "info"
        return Ecart(
            type=type_,
            severite=severite,
            propriete=propriete,
            valeur_wikidata=valeur_wikidata,
            valeur_source=valeur_source,
            source=src.source,
            message=message,
            proposition=proposition,
            creation=creation,
        )

    ecarts: list[Ecart] = []

    if not wd.is_taxon:
        ecarts.append(ecart("item_non_taxon", "erreur", "P31", "L'item n'est pas un taxon."))

    if src.name not in wd.names:
        wd_names = " / ".join(wd.names)
        if src.redirected_from is not None:
            ecarts.append(
                ecart(
                    "nom_synonyme_source",
                    "erreur",
                    "P225",
                    f"{src.source} traite « {src.redirected_from} » comme synonyme de "
                    f"« {src.name} ».",
                    wd_names,
                    src.name,
                )
            )
            return ecarts  # rank, parents and ids would describe the accepted taxon, not this item
        ecarts.append(
            ecart("nom_different", "erreur", "P225", "Nom différent.", wd_names, src.name)
        )

    if src.rank is not None:
        if wd.rank is None:
            proposition = proposer(src.source, "P105", ctx.rank_qid, "item")
            ecarts.append(
                ecart(
                    "rang_absent_wikidata",
                    "suggestion",
                    "P105",
                    "Rang absent." if proposition else "Rang absent (item de rang inconnu).",
                    None,
                    src.rank,
                    proposition,
                )
            )
        elif wd.rank != src.rank:
            ecarts.append(
                ecart("rang_different", "erreur", "P105", "Rang différent.", wd.rank, src.rank)
            )

    if len(wd.parent_names) > 1:
        ecarts.append(
            ecart(
                "parents_multiples",
                "info",
                "P171",
                "Plusieurs parents (classifications concurrentes possibles).",
                " / ".join(wd.parent_names),
            )
        )
    if src.parent_name is not None:
        if not wd.parent_names:
            target = ctx.resolved_items.get(src.parent_name)
            proposition = proposer(src.source, "P171", target, "item")
            ecarts.append(
                ecart(
                    "parent_absent_wikidata",
                    "suggestion",
                    "P171",
                    "Parent absent." if proposition else f"Parent absent ; {_CIBLE_INTROUVABLE}",
                    None,
                    src.parent_name,
                    proposition,
                )
            )
        elif src.parent_name not in wd.parent_names:
            ecarts.append(
                ecart(
                    "parent_different",
                    "erreur",
                    "P171",
                    "Aucun parent ne correspond.",
                    " / ".join(wd.parent_names),
                    src.parent_name,
                )
            )

    cible_uicn = ctx.statut_qids.get(src.uicn or "")
    if cible_uicn is not None:
        if not wd.uicn:
            proposition = proposer("iucn", "P141", cible_uicn, "item")
            ecarts.append(
                ecart(
                    "uicn_absent_wikidata",
                    "suggestion",
                    "P141",
                    "Statut UICN absent.",
                    None,
                    src.uicn,
                    proposition,
                )
            )
        elif cible_uicn not in wd.uicn:
            codes = {qid: code for code, qid in ctx.statut_qids.items()}
            ecarts.append(
                ecart(
                    "uicn_different",
                    "avertissement",
                    "P141",
                    "Statut UICN différent.",
                    " / ".join(codes.get(q, q) for q in wd.uicn),
                    src.uicn,
                )
            )

    wd_syn = {s.casefold(): s for s in wd.synonyms}
    src_syn = {s.casefold(): s for s in src.synonyms}
    for key, name in src_syn.items():
        if key not in wd_syn:
            proposition = proposer(src.source, "P1420", ctx.resolved_items.get(name), "item")
            creation = (
                build_synonym_creation(name, wd.qid, src, ctx)
                if proposition is None and name in ctx.noms_absents
                else None
            )
            ecarts.append(
                ecart(
                    "synonyme_absent_wikidata",
                    "suggestion",
                    "P1420",
                    "Synonyme de la source absent de Wikidata."
                    if proposition
                    else "Synonyme de la source absent de Wikidata ; item à créer."
                    if creation
                    else f"Synonyme de la source absent de Wikidata ; {_CIBLE_INTROUVABLE}",
                    None,
                    name,
                    proposition,
                    creation,
                )
            )
    for key, name in wd_syn.items():
        if key not in src_syn:
            ecarts.append(
                ecart(
                    "synonyme_absent_source",
                    "info",
                    "P1420",
                    "Synonyme de Wikidata absent de la source.",
                    name,
                )
            )

    for module_id, raw in src.external_ids.items():
        value = str(raw)
        known = wd.external_ids.get(module_id)
        if not known:
            target_property = ctx.id_properties.get(module_id)
            proposition = (
                proposer(
                    module_id, target_property.propriete, target_property.prefixe + value, "chaine"
                )
                if target_property
                else None
            )
            ecarts.append(
                ecart(
                    "identifiant_absent_wikidata",
                    "suggestion",
                    module_id,
                    "Identifiant connu de la source, absent de Wikidata.",
                    None,
                    value,
                    proposition,
                )
            )
        elif value not in known:
            ecarts.append(
                ecart(
                    "identifiant_different",
                    "avertissement",
                    module_id,
                    "Identifiant différent.",
                    " / ".join(known),
                    value,
                )
            )

    src_names = {
        "P225": {src.name.casefold()},
        "P171": {src.parent_name.casefold()} if src.parent_name else set(),
        "P1420": set(src_syn),
    }
    for stmt in wd.unreferenced:
        # Referencing a statement asserts that the source supports it.
        confirmed = stmt.nom.casefold() in src_names.get(stmt.propriete, set())
        proposition = (
            proposer(src.source, stmt.propriete, stmt.valeur, stmt.type) if confirmed else None
        )
        ecarts.append(
            ecart(
                "reference_manquante",
                "suggestion",
                stmt.propriete,
                "Statement sans référence."
                if proposition
                else "Statement sans référence (non confirmé par la source).",
                stmt.nom,
                None,
                proposition,
            )
        )
    return ecarts

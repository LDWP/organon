// Mirror of wp_is_italic() (organon/core/rendering/grammar.py): in most
// kingdoms (plant, fungus, bacteria, archaea, virus...) italics are
// systematic whatever the rank. Only the following kingdoms (close to
// the zoological convention) reserve italics to genus rank and below;
// see _DOMAINS_WITHOUT_SYSTEMATIC_ITALICS in the backend. `kingdom`
// here comes from KINGDOM_MAP (organon/core/domains.py) through
// /api/v1/search, so it is already in that vocabulary ("animal",
// "protiste"...).
const ITALIC_BY_RANK_KINGDOMS = new Set(["animal", "reptile", "amphibien", "protiste", "eucaryote"]);

// Ranks for which `below_species` is true in
// organon/core/data/ranks.yaml (genus and below): only these are
// italicized for the ITALIC_BY_RANK_KINGDOMS kingdoms.
const GENUS_AND_LOWER_RANKS = new Set([
  "genre", "sous-genre", "section", "sous-section", "série", "sous-série",
  "espèce", "sous-espèce", "variété", "forme", "sous-forme", "cultivar", "pathovar",
]);

function isItalicRank(rank, kingdom) {
  if (!ITALIC_BY_RANK_KINGDOMS.has(kingdom)) return true;
  return GENUS_AND_LOWER_RANKS.has(rank);
}

export function TaxonName({ match }) {
  return isItalicRank(match.rank, match.kingdom) ? (
    <em>{match.scientific_name}</em>
  ) : (
    <span>{match.scientific_name}</span>
  );
}

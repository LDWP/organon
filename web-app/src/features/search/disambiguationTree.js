// Group the suggestions into a tree. Priority to the parentage
// *confirmed* by GBIF (a match's `parent_key` pointing to the
// `gbif_key` of another match in the same response, e.g. a subspecies
// under its species), shown with a "└" connector. Otherwise fall back
// on a textual resemblance (a name extending another match's)
// restricted to the **same kingdom**, indented without connector since
// parentage is not guaranteed. Without the kingdom restriction, a virus
// named after its host (e.g. "Panthera leo polyomavirus 1") would
// wrongly land under the animal taxon of the same name.
export function buildDisambiguationTree(matches) {
  const byGbifKey = new Map();
  matches.forEach((m) => {
    if (m.gbif_key != null) byGbifKey.set(m.gbif_key, m);
  });

  const nodes = matches.map((m) => ({ match: m, children: [], confirmed: false }));
  const nodeByMatch = new Map(nodes.map((n) => [n.match, n]));
  const roots = [];

  nodes.forEach((node) => {
    const m = node.match;
    const confirmedParent = m.parent_key != null ? byGbifKey.get(m.parent_key) : null;
    if (confirmedParent && confirmedParent !== m) {
      node.confirmed = true;
      nodeByMatch.get(confirmedParent).children.push(node);
      return;
    }

    let parent = null;
    let bestLen = -1;
    nodes.forEach((candidate) => {
      if (candidate === node || candidate.match.kingdom !== m.kingdom) return;
      const prefix = candidate.match.scientific_name + " ";
      if (m.scientific_name.startsWith(prefix) && prefix.length > bestLen) {
        parent = candidate;
        bestLen = prefix.length;
      }
    });
    (parent || { children: roots }).children.push(node);
  });

  return roots;
}

export function flattenDisambiguationTree(nodes, depth = 0, out = []) {
  nodes.forEach((node) => {
    out.push({ match: node.match, depth, confirmed: node.confirmed });
    flattenDisambiguationTree(node.children, depth + 1, out);
  });
  return out;
}

// Merge the rank chains of each source (already ordered domain to
// species) into one list for the comparison table: the chain of the
// recommended source (`backboneChain`) is the fixed backbone; ranks
// specific to other sources (finer granularity, e.g. WoRMS giga-class,
// or a clade absent elsewhere) are inserted only between the two
// backbone ranks that really frame them in their own source chain,
// never reordered within it. A rank with no anchor in the backbone (no
// shared neighbor) goes to the end of the table rather than at random.
export function mergeRankChains(backboneChain, otherChains) {
  const result = [...backboneChain];
  for (const chain of otherChains) {
    let pendingRun = [];
    const flushRun = (beforeIndex) => {
      if (pendingRun.length === 0) return;
      result.splice(beforeIndex ?? result.length, 0, ...pendingRun);
      pendingRun = [];
    };
    for (const rank of chain) {
      const idx = result.indexOf(rank);
      if (idx !== -1) {
        flushRun(idx);
      } else if (!pendingRun.includes(rank)) {
        pendingRun.push(rank);
      }
    }
    flushRun(null);
  }
  return result;
}

// Group consecutive columns (in `sources` order) sharing the same
// displayed value, for the Taxobox comparison table: avoids repeating
// an identical value over adjacent columns (e.g. ITIS and WoRMS
// agreeing on "classe"). Only merges consecutive sources: never
// reorders the columns, to keep a stable position from one rank to the
// next.
export function mergeAdjacentEqual(sources, valueFor) {
  const groups = [];
  for (const source of sources) {
    const value = valueFor(source);
    const last = groups[groups.length - 1];
    if (last && last.value === value) last.sources.push(source);
    else groups.push({ value, sources: [source] });
  }
  return groups;
}

// Reorder `sources` to gather those sharing the same value, even if not
// consecutive in the original order, unlike mergeAdjacentEqual. Value
// groups keep the order of their first appearance. Reserved for
// single-data-row tables (e.g. Author): over several rows, an order
// that groups one row well can misalign the next.
export function groupSourcesByValue(sources, valueFor) {
  const bucket = new Map();
  const order = [];
  for (const source of sources) {
    const value = valueFor(source);
    if (!bucket.has(value)) {
      bucket.set(value, []);
      order.push(value);
    }
    bucket.get(value).push(source);
  }
  return order.flatMap((value) => bucket.get(value));
}

// For each rank, the set of distinct names reported by the already
// resolved classifications, with the first source (in `modules`
// priority order) to have reported each. Used to spot a rank
// disagreement between sources (e.g. ITIS and FishBase not placing a
// genus in the same order) independently of the arrival order of
// background responses.
export function computeRankDisagreements(modules, resultsBySource) {
  const disagreements = {};
  for (const m of modules) {
    const entry = resultsBySource[m.id];
    if (entry?.status !== "ok") continue;
    for (const { rank, name } of entry.data.rank_lines || []) {
      if (!disagreements[rank]) disagreements[rank] = new Map();
      if (!disagreements[rank].has(name)) disagreements[rank].set(name, m.id);
    }
  }
  return disagreements;
}

// Tabular version of computeRankDisagreements for the Results > Taxobox
// comparison table: for each rank, the names reported by each source,
// to compare classifications side by side rather than keep only the
// first name met per rank. Row order merges the per-source rank chains
// (see mergeRankChains) rather than follow an external taxonomic scale:
// the recommended source's chain is the backbone, and ranks specific to
// other sources are inserted only between the backbone ranks that frame
// them. A rank with no anchor stays "disjointed" at the end of the
// table (other columns show "—").
export function buildClassificationTable(availableSources, resultsBySource, recommendedBackboneId) {
  const perModule = {};
  const chainByModule = {};
  for (const m of availableSources) {
    perModule[m.id] = {};
    const rankLines = resultsBySource[m.id].data.rank_lines || [];
    const chain = [];
    // rank_lines goes from the rank nearest the taxon to the farthest
    // (see compute_rank_lines, organon/core/rendering/sections.py);
    // walk it backwards to get this source's domain-to-species chain.
    for (let i = rankLines.length - 1; i >= 0; i--) {
      const { rank, name } = rankLines[i];
      if (!chain.includes(rank)) chain.push(rank);
      if (!perModule[m.id][rank]) perModule[m.id][rank] = [];
      if (!perModule[m.id][rank].includes(name)) perModule[m.id][rank].push(name);
    }
    chainByModule[m.id] = chain;
  }
  const backboneId = recommendedBackboneId ?? availableSources[0]?.id;
  const backboneChain = chainByModule[backboneId] || [];
  const otherChains = availableSources.filter((m) => m.id !== backboneId).map((m) => chainByModule[m.id]);
  return { order: mergeRankChains(backboneChain, otherChains), perModule };
}

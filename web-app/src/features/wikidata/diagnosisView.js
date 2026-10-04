// Per-project reading of a DiagnosticResponse (see
// organon/core/update_diagnosis.py): what is "to review" (value present
// on both sides, different) and "to complete" (absent from the target).
// No value is ever corrected from another source.

const ANOMALY_SEVERITIES = new Set(["erreur", "avertissement"]);

// A checkable row carries a proposal (a statement to add) or a creation
// (a whole item).
export function idOf(gap) {
  return (gap.proposition ?? gap.creation).id;
}

export function suggestionsOf(result) {
  return (result?.ecarts ?? []).filter(
    (e) => e.severite === "suggestion" && (e.proposition || e.creation),
  );
}

// Without a Wikidata item the diagnosis stops before reading frwiki:
// there is no sitelink, hence no linked article. Conversely, neither an
// article nor an "article" section means the read failed.
function frwikiState(result) {
  if (result.qid == null) return "absent";
  if (result.article_frwiki) return "exists";
  if (result.sections_frwiki.some((s) => s.section === "article")) return "absent";
  return "unknown";
}

function summarizeWikidata(result) {
  const gaps = result.ecarts;
  return {
    state: result.qid == null ? "absent" : "exists",
    toReview: result.qid == null ? [] : gaps.filter((e) => ANOMALY_SEVERITIES.has(e.severite)),
    infos: gaps.filter((e) => e.severite === "info"),
    toComplete: suggestionsOf(result),
  };
}

// On frwiki, `valeur_wikidata` holds the article value and
// `valeur_source` the source one.
function summarizeFrwiki(result) {
  const toReview = [];
  const toComplete = [];
  const limits = [];
  for (const s of result.sections_frwiki) {
    if (s.section === "article") continue;
    if (s.limites.length > 0) limits.push({ section: s.section, limits: s.limites });
    s.ecarts.forEach((gap, i) => {
      const row = { key: `${s.section}-${gap.type}-${i}`, section: s.section, level: s.niveau, gap };
      (gap.valeur_wikidata != null ? toReview : toComplete).push(row);
    });
  }
  return { state: frwikiState(result), article: result.article_frwiki, toReview, toComplete, limits };
}

export function summarize(result) {
  if (!result) return null;
  const wikidata = summarizeWikidata(result);
  const frwiki = summarizeFrwiki(result);
  const create = frwiki.state === "absent" ? 1 : 0;
  return {
    wikidata,
    frwiki,
    create,
    counts: {
      toCreate: create,
      toReview: wikidata.toReview.length + frwiki.toReview.length,
      toComplete: wikidata.toComplete.length + frwiki.toComplete.length,
    },
  };
}

import { useCallback, useState } from "react";

export function referenceItemKey(item) {
  return `${item.module_id}::${item.wikitext}`;
}

// Reference items of the active taxobox source (see
// GenerateResponse.reference_items) and client-side recomposition of
// the "Liens externes" block from the checked references only
// (item.default_checked, overridden by manual choices). Same
// alphabetical order as the former server-joined `references_wikitext`
// block, since reference_items is already sorted by the backend.
// `reference_items` deliberately excludes the `{{Autres projets}}`
// block (Commons, Wikispecies, Wiktionary; see
// GenerateResponse.references_wikitext): it is found in the full
// wikitext of the same source rather than duplicate its generation
// logic (see render_see_also, organon/core/rendering/sections.py) in
// the frontend.
export function useReferenceChecklist(taxoboxData, baseData) {
  // Boxes manually checked or unchecked, over the backend default
  // (item.default_checked, see
  // organon.core.selectors.coherence.reference_module_is_consistent).
  // Key = module_id::wikitext of the line. `undefined` = no explicit
  // choice, follow the default; an entry here (true or false) always
  // beats the default.
  const [checkedOverrides, setCheckedOverrides] = useState({});

  const items = taxoboxData?.reference_items || [];
  const checkedItems = items.filter((item) => checkedOverrides[referenceItemKey(item)] ?? item.default_checked);
  const otherProjectsMatch = baseData?.wikitext?.match(/\{\{Autres projets\n(?:\|[^\n]*\n)*\}\}\n(?:\{\{catégorie principale\}\}\n)?/);
  const otherProjectsBlock = otherProjectsMatch ? otherProjectsMatch[0] : "";
  const checkedLinesText = checkedItems.map((item) => `* ${item.wikitext}`).join("\n");
  const checkedWikitext =
    otherProjectsBlock || checkedLinesText
      ? `== Liens externes ==\n${otherProjectsBlock}${checkedLinesText ? checkedLinesText + "\n" : ""}`
      : "";
  // The "Liens externes" block as it appears in the original full
  // wikitext (before checkbox filtering): the anchor to replace by its
  // filtered version when composing "all" (see spliceBlock), like
  // taxobox_wikitext and subtaxa_wikitext.
  const originalBlockMatch = baseData?.wikitext?.match(/== Liens externes ==\n[\s\S]*?(?=\n== |$)/);
  const originalBlock = originalBlockMatch ? originalBlockMatch[0] : "";

  const toggleItem = useCallback((key, currentChecked) => {
    setCheckedOverrides((prev) => ({ ...prev, [key]: !currentChecked }));
  }, []);

  const reset = useCallback(() => setCheckedOverrides({}), []);

  return { items, checkedOverrides, checkedWikitext, originalBlock, toggleItem, reset };
}

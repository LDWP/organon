import { useCallback, useState } from "react";
import {
  applyAuthorOverride,
  applyImageSelection,
  applyRankConflicts,
  IMAGE_PLACEHOLDER,
  spliceBlock,
  spliceSubtaxaBlock,
  trimBlockForDisplay,
} from "./wikitextComposition.js";

// Composition of the wikitext shown under the Wikipedia tab (full
// article and isolated blocks) from the facet choices, and manual
// editing per area. `activeSubTab`: displayed area ("all" | "taxobox" |
// "image" | "subranks" | "references").
export function useWikitextEditor({ activeData, facets, subtaxa, references, author, activeSubTab }) {
  const { taxoboxData, subtaxaData, baseData, managedRankConflicts, rankDisagreements } = facets;

  // Commons file name chosen in the gallery (see ImageGallery.jsx),
  // applied to the displayed wikitext by applyImageSelection() rather
  // than persisted in resultsBySource: it thus survives a
  // classification tab change, without duplicating the state per
  // source.
  const [selectedCommonsImage, setSelectedCommonsImage] = useState(null);
  // Wikitext area being edited: each area (All, Taxobox, Sub-ranks,
  // References) has its own Edit button and is edited independently of
  // the others, one at a time since only one is visible. `null` if no
  // edit is in progress. `editedTexts` keeps the text being typed per
  // area while it is in edition.
  const [editingSubTab, setEditingSubTab] = useState(null);
  const [editedTexts, setEditedTexts] = useState({});
  // Edited and validated wikitext ("Terminé"), per area: replaces the
  // recomputed clean text until a new search or a facet change resets
  // it. For "all" it replaces the composed wikitext (see
  // displayWikitext). The other three areas do not affect the rest of
  // the article: editing one only adjusts the displayed text before
  // copying it, but the adjustment stays visible until a new search or
  // facet change, or clicking "Terminé" would have no visible effect.
  const [manualOverrides, setManualOverrides] = useState({});
  const [copied, setCopied] = useState(false);

  // In merge mode, only substitute the sub-taxa block once the merge
  // was actually received: while it is `null` (call in flight), falling
  // back on the single-source block avoids making the section vanish
  // during the computation (spliceBlock would empty the block if given
  // an already empty altBlock).
  const subtaxaWikitext = subtaxa.enabled && subtaxa.merge ? subtaxa.wikitext : subtaxaData?.subtaxa_wikitext;

  // Composition of "all" from the three structured areas: a validated
  // edit ("Terminé") on the Taxobox, Sub-ranks or References area beats
  // the freshly recomputed value, so editing an area propagates to the
  // full article. Only "all" stays a terminal fallback text, never
  // decomposed back into the other areas: free text cannot be reliably
  // reparsed into structured blocks, while the reverse (structured to
  // text) is a simple block replacement.
  const taxoboxWikitextForAll =
    manualOverrides.taxobox ??
    applyAuthorOverride(taxoboxData?.taxobox_wikitext || "", taxoboxData?.resolved_author, author.overrideResolved);
  const subtaxaWikitextForAll = manualOverrides.subranks ?? subtaxaWikitext;
  const referencesWikitextForAll = manualOverrides.references ?? references.checkedWikitext;

  const displayWikitext = baseData
    ? applyRankConflicts(
        spliceBlock(
          spliceSubtaxaBlock(
            spliceBlock(baseData.wikitext, baseData.taxobox_wikitext, taxoboxWikitextForAll),
            baseData.subtaxa_wikitext,
            subtaxaWikitextForAll
          ),
          references.originalBlock,
          referencesWikitextForAll
        ),
        taxoboxData?.rank_lines,
        managedRankConflicts,
        rankDisagreements
      )
    : activeData?.wikitext ?? null;
  // Image choice applied last, over the base + taxobox + conflicts
  // composition: a plain comment substitution independent of the
  // displayed classification, not part of the classification "zoom"
  // itself.
  const finalWikitext = applyImageSelection(manualOverrides.all ?? displayWikitext, selectedCommonsImage);

  // "Clean" text (not edited, nor persisted by a previous edit) of each
  // area: "taxobox", "subranks" and "references" isolate one server
  // block, independently of the finalWikitext composition that concerns
  // "all" only. See trimBlockForDisplay for the leading and trailing
  // newlines removed from these isolated previews.
  const sourceTextBySubTab = {
    all: finalWikitext,
    taxobox:
      manualOverrides.taxobox ??
      trimBlockForDisplay(
        applyAuthorOverride(
          applyRankConflicts(taxoboxData?.taxobox_wikitext || "", taxoboxData?.rank_lines, managedRankConflicts, rankDisagreements),
          taxoboxData?.resolved_author,
          author.overrideResolved
        )
      ),
    subranks: manualOverrides.subranks ?? trimBlockForDisplay(subtaxaWikitext || ""),
    references: manualOverrides.references ?? trimBlockForDisplay(references.checkedWikitext),
  };
  // Text actually displayed for the shown area: the draft if it is
  // being edited, else the recomputed clean text above.
  const text = editingSubTab === activeSubTab ? editedTexts[activeSubTab] ?? "" : sourceTextBySubTab[activeSubTab];

  function startEditing(id) {
    if (!sourceTextBySubTab[id]) return;
    setEditedTexts((prev) => ({ ...prev, [id]: sourceTextBySubTab[id] }));
    setEditingSubTab(id);
  }

  // "Terminé" persists the area edit in manualOverrides, whatever the
  // area: otherwise the displayed text would immediately fall back on
  // the recomputed value and the edit would look lost.
  function stopEditing() {
    setManualOverrides((prev) => ({ ...prev, [editingSubTab]: editedTexts[editingSubTab] }));
    setEditingSubTab(null);
  }

  function changeEditedText(id, value) {
    setEditedTexts((prev) => ({ ...prev, [id]: value }));
  }

  // An edit (in progress or already validated by "Terminé") applies to
  // the content displayed for the facet selection at the time: changing
  // the facet invalidates any edit, whatever the area.
  const discardEdits = useCallback(() => {
    setEditingSubTab(null);
    setManualOverrides({});
  }, []);

  function selectCommonsImage(fileName) {
    setSelectedCommonsImage(fileName);
    if (editingSubTab === "all") {
      // While editing "all", the displayed text comes from
      // editedTexts.all (independent of the recomputed composition):
      // without this, choosing an image during an edit would stay
      // invisible until "Terminé".
      setEditedTexts((prev) => ({ ...prev, all: applyImageSelection(prev.all, fileName) }));
    }
  }

  // Counterpart of selectCommonsImage: back to the "no image" state
  // (IMAGE_PLACEHOLDER). Outside an edit there is nothing to do on the
  // text itself: displayWikitext is recomposed at each render from the
  // original wikitext (never mutated). While editing "all",
  // editedTexts.all already received the hard substitution: it must be
  // reversed explicitly for the placeholder to reappear in the
  // textarea.
  function deselectCommonsImage() {
    if (editingSubTab === "all" && selectedCommonsImage) {
      setEditedTexts((prev) => ({ ...prev, all: prev.all.split(selectedCommonsImage).join(IMAGE_PLACEHOLDER) }));
    }
    setSelectedCommonsImage(null);
  }

  async function copy(textToCopy) {
    if (!textToCopy) return;
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard unavailable (insecure context, permissions) */
    }
  }

  const reset = useCallback(() => {
    setEditingSubTab(null);
    setEditedTexts({});
    setManualOverrides({});
    setSelectedCommonsImage(null);
  }, []);

  return {
    text,
    editingSubTab,
    selectedCommonsImage,
    copied,
    startEditing,
    stopEditing,
    changeEditedText,
    discardEdits,
    selectCommonsImage,
    deselectCommonsImage,
    copy,
    reset,
  };
}

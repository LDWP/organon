import { useRef, useState } from "react";
import { diagnoseTaxon, exportSuggestions } from "@/api/client.js";
import { idOf, suggestionsOf } from "./diagnosisView.js";

const QID_RE = /^Q\d+$/i;

export function diagnosisErrorMessage(err) {
  if (err.status === 404) return "Taxon ou item Wikidata introuvable.";
  if (err.status === 422) return "Les données sources ont changé : relancez le diagnostic.";
  if (err.status === 429) return "Trop de requêtes : réessayez dans une minute.";
  if (err.status === 502) return "Wikidata est injoignable, réessayez plus tard.";
  if (err.status === 401) return "Connexion requise pour lancer un diagnostic.";
  return err.message;
}

// One diagnosis feeds Review and Complete; the proposal selection and
// the export live here to survive a tab change.
export function useDiagnosis() {
  // idle | loading | ok | error
  const [status, setStatus] = useState("idle");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [target, setTarget] = useState(null);
  const [selected, setSelected] = useState(() => new Set());
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState(null);
  const [exported, setExported] = useState(null);
  const [copied, setCopied] = useState(false);
  // Payload of the last successful diagnosis: the export must replay it
  // identically.
  const lastPayload = useRef(null);
  // Discard the answer of a diagnosis replaced meanwhile (source
  // change, other taxon).
  const generation = useRef(0);

  // `scope` (domain, gbifKey) is that of the generation already
  // launched for this taxon: the server then recognizes the same
  // request and reuses its computation instead of generating again.
  async function run(value, classification, scope = {}) {
    const v = value.trim();
    if (!v) return;
    const mine = ++generation.current;
    setTarget(v);
    setStatus("loading");
    setError(null);
    setCandidates([]);
    setResult(null);
    setExported(null);
    setExportError(null);
    const payload = QID_RE.test(v) ? { qid: v.toUpperCase() } : { taxon: v };
    if (classification) payload.classification = classification;
    if (scope.domain && scope.domain !== "*") payload.domain = scope.domain;
    if (scope.gbifKey != null) payload.gbif_key = scope.gbifKey;
    try {
      const data = await diagnoseTaxon(payload);
      if (generation.current !== mine) return;
      setResult(data);
      lastPayload.current = payload;
      setSelected(
        new Set(suggestionsOf(data).filter((e) => (e.proposition ?? e.creation).coche_par_defaut).map(idOf)),
      );
      setStatus("ok");
    } catch (err) {
      if (generation.current !== mine) return;
      if (err.status === 409) {
        setError(err.message);
        setCandidates(err.candidates);
      } else {
        setError(diagnosisErrorMessage(err));
      }
      setStatus("error");
    }
  }

  const suggestions = suggestionsOf(result);
  const allChecked = suggestions.length > 0 && selected.size === suggestions.length;

  function toggle(id) {
    setExported(null);
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setExported(null);
    setSelected(allChecked ? new Set() : new Set(suggestions.map(idOf)));
  }

  // Snapshot for kept results: reopening a taxon does not rerun the
  // diagnosis.
  function snapshot() {
    return status === "ok" ? { result, payload: lastPayload.current, selected, target } : null;
  }

  function restore(snap) {
    generation.current += 1;
    setResult(snap.result);
    lastPayload.current = snap.payload;
    setSelected(snap.selected);
    setTarget(snap.target);
    setStatus("ok");
    setError(null);
    setCandidates([]);
    setExported(null);
    setExportError(null);
  }

  async function runExport() {
    setExporting(true);
    setExportError(null);
    setExported(null);
    setCopied(false);
    const payload = {
      qid: result.qid,
      proposal_ids: suggestions.map(idOf).filter((id) => selected.has(id)),
    };
    if (lastPayload.current.taxon) payload.taxon = lastPayload.current.taxon;
    for (const field of ["classification", "domain", "gbif_key"]) {
      if (lastPayload.current[field] != null) payload[field] = lastPayload.current[field];
    }
    try {
      setExported((await exportSuggestions(payload)).quickstatements);
    } catch (err) {
      setExportError(diagnosisErrorMessage(err));
    } finally {
      setExporting(false);
    }
  }

  async function copyExport() {
    try {
      await navigator.clipboard.writeText(exported);
      setCopied(true);
    } catch {
      setExportError("Copie impossible : sélectionnez le texte manuellement.");
    }
  }

  return {
    status, result, error, candidates, target, suggestions,
    selected, allChecked, toggle, toggleAll,
    exporting, exportError, exported, copied, runExport, copyExport,
    run, snapshot, restore,
  };
}

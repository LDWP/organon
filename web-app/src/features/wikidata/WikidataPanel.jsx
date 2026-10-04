import { CompleteRow, ReviseRow } from "./DiagRow.jsx";
import { summarize } from "./diagnosisView.js";

function pluralize(n, word) {
  return `${n} ${word}${n > 1 ? "s" : ""}`;
}

function wikidataHref(qid, property) {
  return `https://www.wikidata.org/wiki/${qid}${/^P\d+$/.test(property) ? `#${property}` : ""}`;
}

// Wikidata tab: one list of gaps with the reference source (different
// values and checkable addition proposals, QuickStatements export). No
// value is corrected from another source and Organon writes nothing to
// Wikidata.
export default function WikidataPanel({ diagnosis }) {
  const { status, result, error, selected, toggle, toggleAll, allChecked, exporting, exportError, exported, copied, runExport, copyExport } =
    diagnosis;
  if (status === "error") return <div className="panel"><p className="panel-empty">Diagnostic Wikidata indisponible : {error}</p></div>;
  if (status !== "ok" || !result) return <div className="panel"><p className="panel-empty" role="status">Diagnostic Wikidata en cours…</p></div>;

  const { wikidata } = summarize(result);
  const n = selected.size;
  const rowCount = wikidata.toReview.length + wikidata.toComplete.length;
  return (
    <div className="panel">
      {wikidata.state === "absent" &&
        result.ecarts.filter((e) => !e.creation).map((e, i) => (
          <p key={`${e.type}-${i}`} className="diag-status">{e.message}</p>
        ))}
      {rowCount > 0 && (
        <section className="sheet-group">
          <div className="sheet-group-head">
            <h2>Item Wikidata</h2>
            <span>{pluralize(rowCount, "point")} à voir</span>
          </div>
          <ul className="sheet-card">
            {wikidata.toReview.map((e, i) => (
              <ReviseRow
                key={`${e.type}-${e.propriete}-${i}`}
                label={e.propriete || e.type}
                message={e.message}
                leftLabel="Wikidata"
                left={e.valeur_wikidata}
                rightLabel={e.source}
                right={e.valeur_source}
                href={wikidataHref(result.qid, e.propriete)}
              />
            ))}
            {wikidata.toComplete.map((e) => {
              const p = e.proposition;
              if (e.creation) {
                const c = e.creation;
                return (
                  <CompleteRow
                    key={c.id}
                    label="Créer l'item"
                    detail={c.label}
                    reference={`${pluralize(c.lignes.length, "statement")} · ${e.message}`}
                    checked={selected.has(c.id)}
                    onToggle={() => toggle(c.id)}
                  />
                );
              }
              return (
                <CompleteRow
                  key={p.id}
                  label={`${p.propriete} · ${p.module}`}
                  detail={e.valeur_source ?? p.valeur}
                  reference={[
                    e.valeur_source && e.valeur_source !== p.valeur ? `valeur : ${p.valeur}` : null,
                    `réf. proposée : ${p.reference.stated_in} · consulté ${p.reference.retrieved}`,
                  ].filter(Boolean).join(" · ")}
                  badge={p.verifiee ? null : "propriété à vérifier"}
                  checked={selected.has(p.id)}
                  onToggle={() => toggle(p.id)}
                />
              );
            })}
          </ul>
        </section>
      )}
      {wikidata.state === "exists" && rowCount === 0 && (
        <p className="sheet-ok"><strong>Wikidata</strong> · item existant, aucun écart avec la source de référence.</p>
      )}
      {wikidata.infos.length > 0 && (
        <details className="sheet-infos">
          <summary>Informations ({wikidata.infos.length})</summary>
          <ul>
            {wikidata.infos.map((e, i) => (
              <li key={`${e.type}-${i}`}><strong>{e.propriete || e.type}</strong> · {e.message}</li>
            ))}
          </ul>
        </details>
      )}
      {result.avertissements.length > 0 && (
        <ul className="sum-warnings">
          {result.avertissements.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}

      {exportError && <p className="error-banner" role="alert">{exportError}</p>}
      {exported !== null && (
        <div className="diag-export-out">
          <label htmlFor="qs-output">Commandes QuickStatements</label>
          <textarea id="qs-output" readOnly value={exported} rows={Math.min(10, exported.split("\n").length + 1)} />
          <div className="diag-export-actions">
            <button type="button" onClick={copyExport}>{copied ? "Copié ✓" : "Copier"}</button>
            <span>À coller dans QuickStatements — Organon n'écrit rien sur Wikidata.</span>
          </div>
        </div>
      )}
      {wikidata.toComplete.length > 0 && (
        <div className="basket" role="region" aria-label="Panier d'export">
          <span className="basket-count" role="status">
            Panier : {n} sélectionné{n > 1 ? "s" : ""}
            <small>{pluralize(n, "ligne")} QuickStatements</small>
          </span>
          <span className="basket-actions">
            <button type="button" className="sheet-btn-ghost" onClick={toggleAll}>
              {allChecked ? "Tout décocher" : "Tout cocher"}
            </button>
            <button type="button" className="sheet-btn-solid" onClick={runExport} disabled={exporting || n === 0}>
              {exporting ? "Export…" : "Exporter…"}
            </button>
          </span>
        </div>
      )}
    </div>
  );
}

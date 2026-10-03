// Only what needs an action remains here (diagnosis failure with QID
// candidates, server warnings).
function Notices({ diagnosis, onPickCandidate }) {
  const { status, result, error, candidates } = diagnosis;
  if (status === "error") {
    return (
      <div className="sum-error">
        <p role="alert">{error}</p>
        {candidates.length > 0 && (
          <ul className="diag-candidates">
            {candidates.map((qid) => (
              <li key={qid}><button type="button" onClick={() => onPickCandidate(qid)}>{qid}</button></li>
            ))}
          </ul>
        )}
      </div>
    );
  }
  if (status === "ok" && result.avertissements.length > 0) {
    return (
      <ul className="sum-warnings">
        {result.avertissements.map((a, i) => <li key={i}>{a}</li>)}
      </ul>
    );
  }
  return null;
}

// Taxon sheet: header, diagnosis notices, then the generation (wikitext
// and its sections).
export default function TaxonSheet({ diagnosis, onPickCandidate, identity, draft }) {
  return (
    <div className="sheet">
      <div className="sheet-head">
        <div className="sheet-identity">{identity}</div>
      </div>
      <Notices diagnosis={diagnosis} onPickCandidate={onPickCandidate} />
      <div className="sheet-panel">{draft}</div>
    </div>
  );
}

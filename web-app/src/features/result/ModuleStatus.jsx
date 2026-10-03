// Statuses of a module (classification or enrichment) during a streamed
// generation (see organon/api/routes/generate.py, ModuleStatusEvent).
// "pending" is purely frontend (added on the "plan" event, before the
// module really starts): the backend never emits it. Each status has a
// distinct shape AND label, not only a color (color-blind
// accessibility).
const STATUS_LABELS = {
  pending: "en attente",
  running: "recherche en cours",
  found: "trouvé",
  empty: "aucun résultat",
  error: "erreur réseau",
};

export function ModuleStatusIcon({ status }) {
  const label = STATUS_LABELS[status] || status;
  return (
    <span className={`module-status-icon module-status-${status}`} role="img" aria-label={label} title={label}>
      {status === "pending" && "○"}
      {status === "running" && <span className="module-status-spinner" aria-hidden="true" />}
      {status === "found" && "✓"}
      {status === "empty" && "✗"}
      {status === "error" && "⚠"}
      {status === "check" && "!"}
    </span>
  );
}

export function ModuleStatusDot({ status }) {
  const label = STATUS_LABELS[status] || status;
  return <span className={`status-dot status-dot-${status}`} role="img" aria-label={label} title={label} />;
}

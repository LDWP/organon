import { ModuleStatusDot } from "./ModuleStatus.jsx";

// Extract the target of the first link of an external link HTML block
// (see ExternalLink, organon/api/schemas.py) to make it the target of
// the module name in the Data tab. Module href attributes use single
// quotes (see simple_debug_link, organon/modules/common.py): accepting
// both avoids missing those links.
function extractHref(html) {
  const match = html?.match(/href=["']([^"']+)["']/);
  return match ? match[1] : null;
}

// "0,6 s" rather than "0.6s": the French decimal convention used
// elsewhere in the app.
function formatDuration(seconds) {
  return `${seconds.toLocaleString("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s`;
}

export default function DataTab({ activeSource, activeEntry, activeData, onRetryModule }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="t">Données — {activeSource ? activeSource.toUpperCase() : "…"}</span>
      </div>
      <div>
        {activeData?.warnings.length > 0 && (
          <div className="warnlist">
            {activeData.warnings.map((w, i) => (
              <p key={i}>⚠ {w}</p>
            ))}
          </div>
        )}

        {activeEntry?.moduleStatuses && Object.keys(activeEntry.moduleStatuses).length > 0 ? (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Informations</th>
                  <th>Temps d'exécution</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(activeEntry.moduleStatuses).map(([moduleId, info]) => {
                  const link = activeData?.external_links.find((l) => l.module_id === moduleId);
                  const href = link ? extractHref(link.html) : null;
                  // Information types this module actually reported for
                  // this taxon (see GenerateResponse.data_found),
                  // derived from the structure already in the response
                  // rather than guessed here module by module.
                  const found = activeData?.data_found?.[moduleId] || [];
                  return (
                    <tr key={moduleId}>
                      <td>
                        <span className="data-table-cell-flex">
                          <ModuleStatusDot status={info.status} />
                          {href ? (
                            <a href={href} target="_blank" rel="noreferrer">
                              {moduleId.toUpperCase()}
                            </a>
                          ) : (
                            moduleId.toUpperCase()
                          )}
                        </span>
                      </td>
                      <td>
                        {info.status === "error" ? (
                          <span className="data-table-cell-flex">
                            <span>{info.message ? `Erreur : ${info.message}` : "Erreur réseau"}</span>
                            <button type="button" className="footer-link" onClick={() => onRetryModule(moduleId)}>
                              Réessayer
                            </button>
                          </span>
                        ) : (
                          found.join(", ")
                        )}
                      </td>
                      <td className="data-table-duration">
                        {info.durationSeconds != null ? formatDuration(info.durationSeconds) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="panel-empty">Aucun suivi disponible pour le moment.</p>
        )}
      </div>
    </div>
  );
}

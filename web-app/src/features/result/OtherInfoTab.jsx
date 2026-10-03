// French labels of the IUCN status codes (see
// GenerateResponse.iucn_status, organon.api.schemas), the same codes as
// {{Taxobox UICN}} on frwiki.
const IUCN_LABELS = {
  EX: "Éteinte",
  EW: "Éteinte à l'état sauvage",
  RE: "Disparue au niveau régional",
  CR: "En danger critique d'extinction",
  EN: "En danger",
  VU: "Vulnérable",
  NT: "Quasi menacée",
  LC: "Préoccupation mineure",
  DD: "Données insuffisantes",
  NE: "Non évaluée",
};

export default function OtherInfoTab({ activeData }) {
  return (
    <div className="panel">
      {activeData ? (
        <>
          {activeData.habitat && (
            <div className="field-box">
              <span className="field-label">Écozone</span>
              <p>{activeData.habitat === "marin" ? "Marin" : "Terrestre"}</p>
            </div>
          )}
          {activeData.iucn_status && (
            <div className="field-box">
              <span className="field-label">Statut de conservation UICN</span>
              <p>
                <strong>{activeData.iucn_status}</strong>
                {IUCN_LABELS[activeData.iucn_status] ? ` — ${IUCN_LABELS[activeData.iucn_status]}` : ""}
                {" "}(source : GBIF)
              </p>
            </div>
          )}
          <div className="field-box">
            <span className="field-label">Répartition</span>
            {activeData.distribution && Object.keys(activeData.distribution).length > 0 ? (
              <ul>
                {Object.entries(activeData.distribution).map(([moduleId, countries]) => (
                  <li key={moduleId}>
                    <strong>{moduleId.toUpperCase()}</strong> : {countries.join(", ")}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="panel-empty">Aucune répartition disponible.</p>
            )}
          </div>
        </>
      ) : (
        <p className="panel-empty">Aucune donnée disponible.</p>
      )}
    </div>
  );
}

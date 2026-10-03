export default function ResultIdentity({ query, activeData, author, onGoToNames, onGoToOtherInfo }) {
  const pluralSuffix = (n) => ({ source: n === 1 ? "une source" : "des sources", verb: n === 1 ? "" : "nt" });
  const kingdomAlert = activeData?.kingdom_inconsistencies;
  const rankAlert = activeData?.rank_inconsistencies;
  return (
    <>
      <div className="result-head">
        {activeData?.extinct && (
          <button type="button" className="id-badge id-badge-eteint id-badge-clickable" onClick={onGoToOtherInfo}>
            ✝ éteint
          </button>
        )}
        <h2>
          <em>{activeData?.resolved_taxon || query.taxon}</em>
        </h2>
        {activeData && (
          <button
            type="button"
            className={
              "id-author" +
              (author.values.length === 0 ? " id-author-missing" : author.variants.size > 1 ? " id-author-conflict" : " id-author-ok")
            }
            onClick={onGoToNames}
            title={author.variants.size > 1 ? `Auteurs en désaccord entre sources : ${[...author.variants].join(" / ")}` : undefined}
          >
            {author.values.length === 0 ? "auteur ?" : author.displayed}
          </button>
        )}
        {activeData?.kingdom && <span className="id-badge">{activeData.kingdom}</span>}
        {/*
           TODO(ecozone): ecozone badge. The data is not exposed in
           activeData yet; wire it here once the API and frontend
           provide it.
         */}
        {activeData?.vernacular_names?.length > 0 && (
          <button type="button" className="id-vernacular id-vernacular-clickable" onClick={onGoToNames}>
            {activeData.vernacular_names[0]}
            {activeData.vernacular_names.length > 1 ? "…" : ""}
          </button>
        )}
      </div>
      {kingdomAlert?.length > 0 && (
        <div className="regne-alert">
          <p className="regne-alert-title">
            ⚠ Possible homonymie inter-règnes : {pluralSuffix(kingdomAlert.length).source} suggère{pluralSuffix(kingdomAlert.length).verb} un règne différent.
          </p>
          <ul>
            {kingdomAlert.map((inc, i) => (
              <li key={i}>
                <strong>{inc.module.toUpperCase()}</strong> suggère « {inc.suggested_kingdom} », règne retenu : « {inc.retained_kingdom} »
              </li>
            ))}
          </ul>
          <p className="regne-alert-hint">
            Ce nom pourrait désigner un autre taxon — vérifiez le titre de l'article ou l'homonymie avant publication.
          </p>
        </div>
      )}
      {rankAlert?.length > 0 && (
        <div className="regne-alert">
          <p className="regne-alert-title">
            ⚠ Désaccord taxonomique entre sources : {pluralSuffix(rankAlert.length).source} donne{pluralSuffix(rankAlert.length).verb} une valeur différente.
          </p>
          <ul>
            {rankAlert.map((inc, i) => (
              <li key={i}>
                <strong>{inc.module.toUpperCase()}</strong> donne « {inc.suggested_value} » pour {inc.compared_field}, valeur retenue : « {inc.retained_value} »
              </li>
            ))}
          </ul>
          <p className="regne-alert-hint">
            Divergence taxonomique réelle entre sources (pas un trou de données) — à trancher éditorialement, pas automatiquement.
          </p>
        </div>
      )}
    </>
  );
}

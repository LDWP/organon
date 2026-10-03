import ControlBox from "./ControlBox.jsx";
import { mergeAdjacentEqual } from "@/shared/rankComparison.js";

// Official abbreviations of {{Modèle:Taxoboxoutils rang}} on frwiki:
// only the "embranchement" branch has a short form (format=court);
// class, order, family, genus and their compounds have no standard
// abbreviation on frwiki and stay in full in the comparison table.
const RANK_ABBR = {
  "super-embranchement": "Super-embr.",
  "sous-embranchement": "Sous-embr.",
  "infra-embranchement": "Infra-embr.",
  "micro-embranchement": "Micro-embr.",
  "parv-embranchement": "Parv-embr.",
};

export default function TaxoboxControls({ facets, collapsed, onToggle, onChooseSource }) {
  const { availableSources, classificationTable, taxoboxSourceId, recommendedTaxoboxSource, taxoboxNameByRank } = facets;
  return (
    <ControlBox
      title={
        <>
          Choisir la classification <br/><small>« Cocher » ajoute {"{{Taxobox conflit}}"} pour les rangs en désaccord</small>
        </>
      }
      collapsed={collapsed}
      onToggle={onToggle}
    >
      <div className="data-table-wrap classification-compare-wrap">
        <table className="data-table classification-compare-table classification-compare-table--managed">
          <thead>
            <tr>
              <th></th>
              {availableSources.map((m) => (
                <th key={m.id}>
                  <button
                    type="button"
                    className={"id-badge id-badge-btn" + (taxoboxSourceId === m.id ? " on" : "")}
                    onClick={() => onChooseSource(m.id)}
                    title={m.id === recommendedTaxoboxSource ? "Recommandé" : "Choisir cette source pour la Taxobox"}
                  >
                    {m.id.toUpperCase()}
                    {m.id === recommendedTaxoboxSource ? " ★" : ""}
                  </button>
                </th>
              ))}
              <th></th>
            </tr>
          </thead>
          <tbody>
            {classificationTable.order.map((rank) => {
              const conflict = facets.rankDisagreements[rank]?.size > 1;
              const valueFor = (m) => {
                const names = classificationTable.perModule[m.id]?.[rank] || [];
                return names.length > 0 ? names.join(", ") : "—";
              };
              const chosenValue = taxoboxNameByRank[rank] || "—";
              const groups = mergeAdjacentEqual(availableSources, valueFor);
              const abbr = RANK_ABBR[rank];
              return (
                <tr key={rank}>
                  <th>{abbr ? <abbr title={rank}>{abbr}</abbr> : rank}</th>
                  {groups.map((g, gi) => {
                    const isChosen = g.sources.some((m) => m.id === taxoboxSourceId);
                    const isDiff = conflict && !isChosen && g.value !== "—" && g.value !== chosenValue;
                    return (
                      <td
                        key={gi}
                        colSpan={g.sources.length}
                        className={isDiff ? "conflict-cell" : isChosen ? "chosen-col" : undefined}
                      >
                        {g.value}
                      </td>
                    );
                  })}
                  <td>
                    {conflict && (
                      <input
                        type="checkbox"
                        checked={!!facets.managedRankConflicts[rank]}
                        onChange={() => facets.toggleRankConflictManaged(rank)}
                        aria-label={`Gérer le désaccord sur le rang ${rank} dans le rendu`}
                        title="Gérer ce désaccord dans le rendu"
                      />
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </ControlBox>
  );
}

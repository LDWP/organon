import ControlBox from "./ControlBox.jsx";
import { referenceItemKey } from "./useReferenceChecklist.js";

export default function ReferenceControls({ references, collapsed, onToggle }) {
  return (
    <ControlBox title="Références disponibles — décocher celles hors-sujet" collapsed={collapsed} onToggle={onToggle}>
      <div className="reference-checklist">
        <div className="reference-checklist-row reference-checklist-row-locked">
          <span className="reference-checklist-lock" aria-hidden="true">🔒</span>
          <span className="id-badge">Autres projets</span>
          <span className="reference-checklist-note">
            toujours inclus — fait partie des liens externes, pas des références taxonomiques
          </span>
        </div>
        {references.items.map((item) => {
          const key = referenceItemKey(item);
          const checked = references.checkedOverrides[key] ?? item.default_checked;
          return (
            <label key={key} className="reference-checklist-row">
              <input
                type="checkbox"
                checked={checked}
                onChange={() => references.toggleItem(key, checked)}
                aria-label={`Inclure la référence ${item.module_id} dans les liens externes`}
              />
              <span className="id-badge">{item.module_id.toUpperCase()}</span>
              {!item.default_checked && <span className="id-badge id-badge-conflict">hors domaine</span>}
              <code>{item.wikitext}</code>
            </label>
          );
        })}
      </div>
    </ControlBox>
  );
}

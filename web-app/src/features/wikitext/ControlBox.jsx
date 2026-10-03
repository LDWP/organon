// Collapsible "controls" area (Taxobox rank choice, reference
// checklist, sub-rank merge): collapsed once the choice is made, to
// keep only the header.
export default function ControlBox({ title, collapsed, onToggle, children }) {
  return (
    <div className="render-box">
      <div className="render-box-header">
        <h4 className="render-box-title">{title}</h4>
        <span className="render-box-actions">
          <button type="button" className="footer-link" onClick={onToggle}>
            {collapsed ? "Déplier" : "Replier"}
          </button>
        </span>
      </div>
      {!collapsed && children}
    </div>
  );
}

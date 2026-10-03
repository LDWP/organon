// Toolforge requires the footer to expose a bug report link,
// documentation, source code, license and author(s).
const AUTHORS_LABEL = "Auteurs et crédits";
const LICENSE_URL = "https://www.gnu.org/licenses/gpl-3.0.html";
const BUG_REPORT_URL = "https://fr.wikipedia.org/wiki/Discussion_Projet:Biologie/Organon";
const REPO_URL = "https://github.com/LDWP/organon";
const DOCS_URL = "https://github.com/LDWP/organon/blob/master/README.md";
const API_DOCS_URL = "https://organon.toolforge.org/docs";

export default function SiteFooter({ onShowSources, onShowAuthors }) {
  return (
    <footer>
      <div className="wrap">
        <p className="footer-meta">
          Organon ·{" "}
          <a href={API_DOCS_URL} target="_blank" rel="noreferrer">api/v1</a>{" "}
          ·{" "}
          <button type="button" className="footer-link" onClick={onShowSources}>
            sources
          </button>{" "}
          ·{" "}
          <button type="button" className="footer-link" onClick={onShowAuthors}>
            {AUTHORS_LABEL}
          </button>{" "}
          · <a href={LICENSE_URL} target="_blank" rel="noreferrer">GPL-3.0-or-later</a> ·{" "}
          <a href={REPO_URL} target="_blank" rel="noreferrer">code source</a>{" "}
          ·{" "}
          <a href={DOCS_URL} target="_blank" rel="noreferrer">documentation</a>{" "}
          ·{" "}
          <a href={BUG_REPORT_URL} target="_blank" rel="noreferrer">signaler un bug</a>
        </p>
      </div>
    </footer>
  );
}

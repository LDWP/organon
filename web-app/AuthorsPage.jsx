export default function AuthorsPage({ onBack }) {
  return (
    <div className="sources-page">
      <button type="button" className="back-link" onClick={onBack}>
        ‹ Retour
      </button>

      <h1>Auteurs et crédits</h1>

 <section className="authors-entry">
        <h2>Organon</h2>

        <p>
          C'est un outil qui se situe entre une réécriture du Taxobot en
          Python - une sorte d'héritier, et un petit oiseau qui aurait pris son
          envol pour explorer de nouveaux horizons.</p>
<p>
          <a
            href="https://fr.wikipedia.org/wiki/Utilisateur:LD"
            target="_blank"
            rel="noopener noreferrer"
          >
            LD
          </a> est le développeur de ce site web.
        </p>
      </section>

      <section className="authors-entry">
        <h2>
          <a
            href="https://fr.wikipedia.org/wiki/Projet:Biologie/Taxobot"
            target="_blank"
            rel="noopener noreferrer"
          >
            Taxobot
          </a>
        </h2>

        <p>
          Outil en PHP, initié par{" "}
          <a
            href="https://fr.wikipedia.org/wiki/Utilisateur:Hexasoft"
            target="_blank"
            rel="noopener noreferrer"
          >
            Hexasoft
          </a>{" "}
          et rejoint par{" "}
          <a
            href="https://fr.wikipedia.org/wiki/Utilisateur:LD"
            target="_blank"
            rel="noopener noreferrer"
          >
            LD
          </a>
          , pour générer des squelettes d'articles pour les taxons à partir de
          bases de données taxonomiques tierces (GBIF, ITIS, WoRMS, Catalogue
          of Life, EOL, NCBI, etc.).
        </p>
      </section>


      <section className="authors-entry">
        <h2>Wikipédia & Projet:Biologie</h2>

        <p>
          La communnauté wikipédienne, et en particulier les membres du projet Biolgie, a été le moteur de son élaboration. Discutons-en autour d'un <a href="https://fr.wikipedia.org/wiki/Discussion_Projet:Biologie/Le_caf%C3%A9_des_biologistes" target="_blank" rel="noopener noreferrer">café</a> et, surtout, n'hésitez pas à contribuer à rendre la biologie plus accessible sur Wikipédia (ou ailleurs).
          </p>
      </section>
    </div>
  );
}
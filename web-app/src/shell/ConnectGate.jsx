import { LOGIN_URL } from "@/api/client.js";

export default function ConnectGate() {
  return (
    <div className="console connect-gate">
      <p className="connect-gate-desc">
        Organon interroge automatiquement une vingtaine de bases taxonomiques (GBIF, ITIS,
        AlgaeBase, WoRMS…) pour générer l'ébauche sourcée d'un article Wikipédia sur un taxon.
      </p>
      <p className="connect-gate-desc">
        La génération est réservée aux comptes wikimédiens connectés. Il sera ultérieurement
        possible de publier ou de mettre à jour un article directement depuis cet outil.
      </p>
      <a className="run connect-gate-cta" href={LOGIN_URL}>
        Se connecter avec Wikimedia ▸
      </a>
    </div>
  );
}

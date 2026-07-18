# Organon

Outil du Projet:Biologie de Wikipédia en français qui génère des squelettes d'articles pour les
taxons à partir de bases de données taxonomiques tierces (GBIF, ITIS, WoRMS, Catalogue of Life,
EOL, NCBI, …).

## Architecture

- `organon/core/` — modèle de données, registre de modules, moteur de rendu wikitexte, règles de
  catégorisation, données de grammaire/rangs. Indépendant de toute interface.
- `organon/modules/` — un adaptateur par base de données tierce (`adapter.py` = appels HTTP + parsing
  du format d'échange, `module.py` = logique métier branchée sur le registre).
- `organon/api/` — backend FastAPI exposant `/api/v1/generate`, `/api/v1/modules`,
  `/api/v1/domains`, `/api/v1/version`, `/healthz`. Sert aussi le frontend buildé (`web-app/dist/`) en statique une fois `npm run build` exécuté — un seul process pour l'API et l'UI, contrainte du
  déploiement Toolforge.
- `web-app/` — frontend React (Vite), client HTTP de l'API ci-dessus. Voir `web-app/README.md` pour son propre développement local.
- `organon/cli/` — client en ligne de commande. Simple client HTTP de l'API ci-dessus (en développement).

## Développement

Pour le frontend React (`web-app/`), voir son propre `README.md` — nécessite Node.js et
`npm install` séparément.

## Licence

GPL-3.0-or-later — voir [`LICENSE`](LICENSE).

## Signaler un bug

Les bugs applicatifs (génération incorrecte, module en échec, rendu wikitexte erroné, …) se
signalent sur [Discussion Projet:Biologie/Organon](https://fr.wikipedia.org/wiki/Discussion_Projet:Biologie/Organon).


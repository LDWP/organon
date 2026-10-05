# Organon

Outil du Projet:Biologie de Wikipédia en français qui génère des squelettes d'articles pour les
taxons à partir de bases de données taxonomiques tierces (GBIF, ITIS, WoRMS, Catalogue of Life,
EOL, NCBI, …).

## Architecture

- `organon/core/` — modèle de données, registre de modules, moteur de rendu wikitexte, règles de
  catégorisation, données de grammaire/rangs. Indépendant de toute interface.
- `organon/modules/` — un adaptateur par base de données tierce (`adapter.py` = appels HTTP + parsing
  du format d'échange, `module.py` = logique métier branchée sur le registre).
- `organon/api/` — backend FastAPI, préfixe `/api/v1`. Sert aussi le frontend buildé (`web-app/dist/`) en statique une fois `npm run build` exécuté — un seul process pour l'API et l'UI, contrainte du déploiement Toolforge.
- `web-app/` — frontend React (Vite), client HTTP de l'API ci-dessus. Voir `web-app/README.md` pour son propre développement local.

## API

Politique : toute route qui appelle un service tiers exige une session OAuth (cookie posé par
`/auth/login`) et est limitée en débit par IP (voir `organon/api/rate_limit.py`). Les routes
locales (catalogues, version, auth) sont libres.

| Route | Rôle | Session |
|---|---|---|
| `POST /generate`, `GET /generate?taxon=` | génération complète d'un squelette | oui |
| `POST /generate/stream` | idem en Server-Sent Events, un événement par module | oui |
| `GET /search?q=` | recherche floue (nom scientifique, vernaculaire ou QID) | oui |
| `POST /taxobox/refresh` | mise à jour de la taxobox par le compte bot | oui |
| `GET /commons-images?taxon=` | suggestions d'images Commons | oui |
| `POST /subtaxa-merge` | fusion des sous-taxons de plusieurs sources | oui |
| `POST /update/diagnose`, `POST /update/export` | écarts Wikidata/sources, export QuickStatements | oui |
| `GET /modules`, `/domains`, `/sources`, `/version` | catalogues et version | non |
| `GET /auth/login`, `/auth/callback`, `/auth/me`, `POST /auth/logout` | flux OAuth Wikimedia | non |
| `GET /healthz` (hors préfixe) | sonde de santé | non |

Pas de CLI : la génération exige une session OAuth, qu'un client en ligne de commande ne peut pas
obtenir, et l'ancienne CLI recopiait les options de `GenerateOptions` à la main.

## Développement

Backend : `pip install -e ".[dev]"`, puis `ORGANON_DEV=1 uvicorn organon.api.app:app --port 8123`
(`ORGANON_DEV=1` simule une session, local uniquement). Frontend : voir `web-app/README.md`.

## Licence

GPL-3.0-or-later — voir [`LICENSE`](LICENSE).

## Signaler un bug

Les bugs applicatifs (génération incorrecte, module en échec, rendu wikitexte erroné, …) se
signalent sur [Discussion Projet:Biologie/Organon](https://fr.wikipedia.org/wiki/Discussion_Projet:Biologie/Organon).


# Organon — frontend

React 19 + Vite + Tailwind. Simple client de l'API FastAPI (`organon/api/`) : aucune logique de
génération ici, tout passe par `src/api/client.js`.

## Développement local

Prérequis : Node.js récent et Python 3.11+ avec le paquet installé (`pip install -e ".[dev]"` à la
racine du dépôt).

1. Backend, depuis la racine du dépôt :

   ```
   ORGANON_DEV=1 uvicorn organon.api.app:app --port 8123
   ```

   `ORGANON_DEV=1` fait passer chaque requête pour une session connectée, sans OAuth. Usage local
   uniquement : ne jamais le définir en production.

2. Frontend, depuis `web-app/` :

   ```
   npm install
   npm run dev
   ```

   Le site est servi sur http://localhost:5173. Vite relaie `/api/v1/*` vers
   `http://127.0.0.1:8123` (`vite.config.js`) : le navigateur ne voit qu'une origine, d'où
   l'absence de CORS côté backend. Le port 8123 est donc à garder aligné entre les deux commandes.

## Connexion OAuth réelle

Le flux OAuth ne s'utilise qu'avec un consumer Wikimedia dont le callback est
`http://localhost:5173/api/v1/auth/callback` (via le proxy Vite, pour que le cookie de session
soit posé sur l'origine du frontend). Renseigner `ORGANON_OAUTH_CLIENT_ID`,
`ORGANON_OAUTH_CLIENT_SECRET` et `ORGANON_OAUTH_REDIRECT_URI` avant de lancer le backend, sans
`ORGANON_DEV`. Après connexion, le backend redirige vers `ORGANON_FRONTEND_POST_LOGIN_URL`
(`http://localhost:5173/` par défaut).

## Build et production

```
npm run build
```

Génère `web-app/dist/`, versionné : en production FastAPI le sert en statique (même process, même
origine), voir `STATIC_DIR` dans `organon/api/app.py`. Reconstruire et committer `dist/` après
toute modification du frontend. `npm run lint` lance ESLint.

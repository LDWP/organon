// Client de l'API Organon. Le frontend ne réimplémente aucune logique de génération : il
// appelle uniquement cette API (voir organon/api/).
//
// En dev, Vite relaie /api/* vers http://127.0.0.1:8123 (voir vite.config.js) pour éviter le
// CORS ; en prod, VITE_API_BASE peut pointer directement vers l'API déployée.
const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`Erreur API (${res.status}) sur ${path}`);
  }
  return res.json();
}

export function fetchDomains() {
  return apiGet("/domains");
}

export function fetchModules() {
  return apiGet("/modules");
}

// Vue d'ensemble de toutes les bases de données considérées pour le projet, intégrées ou non
// (voir organon/api/routes/sources.py) — alimente SourcesPage.jsx, à ne pas confondre avec
// fetchModules() ci-dessus qui ne couvre que les modules réellement enregistrés.
export function fetchSources() {
  return apiGet("/sources");
}

export function searchTaxa(query) {
  return apiGet(`/search?q=${encodeURIComponent(query)}`);
}

export function fetchAuthStatus() {
  return apiGet("/auth/me");
}

// Suggestions d'images Commons pour la taxobox (voir organon/api/routes/commons_images.py) :
// déjà filtrées par licence permissive et par distinction qualité/featured côté serveur, jamais
// une recherche brute à filtrer ici.
export function fetchCommonsImages(taxon) {
  return apiGet(`/commons-images?taxon=${encodeURIComponent(taxon)}`);
}

export const LOGIN_URL = `${API_BASE}/auth/login`;

export async function logout() {
  const res = await fetch(`${API_BASE}/auth/logout`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`Erreur API (${res.status}) sur /auth/logout`);
  }
  return res.json();
}

export async function generateTaxon(payload) {
  const res = await fetch(`${API_BASE}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || `Erreur API (${res.status})`);
  }
  return data;
}

// Variante de generateTaxon() consommant POST /api/v1/generate/stream (Server-Sent Events) :
// une génération avec ~20 modules applicables peut prendre 10-20s en une seule requête
// bloquante — ce flux permet d'afficher la progression module par module (voir
// organon/api/routes/generate.py, ModuleStatusEvent/PlanEvent/ResultEvent/FatalErrorEvent).
//
// Utilise fetch()+ReadableStream plutôt que l'API EventSource native : EventSource ne peut
// faire que des requêtes GET sans corps, alors que la requête de génération porte un payload
// JSON complet (taxon + toutes les options, comme generateTaxon ci-dessus) qui doit rester en
// POST — un besoin courant pour du SSE avec corps de requête (même approche que les API de
// chat en streaming), pas une réimplémentation par manque d'alternative plus simple.
//
// `onEvent(event)` est appelé pour chaque événement décodé (dans l'ordre où ils arrivent),
// avant que la promesse ne se résolve avec la donnée du `result` final ; un `fatal_error` (ex.
// taxon non trouvé) ou une coupure du flux avant tout `result` rejette la promesse à la place.
export async function generateTaxonStream(payload, { onEvent } = {}) {
  const res = await fetch(`${API_BASE}/generate/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* corps d'erreur non-JSON (ex. 502 d'un proxy intermédiaire) : on retombe sur le statut */
    }
    throw new Error(detail || `Erreur API (${res.status})`);
  }
  if (!res.body) {
    // Navigateur sans ReadableStream sur Response.body (très ancien) : pas de repli, l'appelant
    // affichera l'erreur comme n'importe quel échec réseau.
    throw new Error("Ce navigateur ne supporte pas la lecture en flux des réponses.");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;
  let fatalError = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop(); // dernier fragment potentiellement incomplet, conservé pour la suite
    for (const frame of frames) {
      const dataLine = frame.split("\n").find((line) => line.startsWith("data: "));
      if (!dataLine) continue;
      const event = JSON.parse(dataLine.slice("data: ".length));
      onEvent?.(event);
      if (event.type === "result") result = event.data;
      if (event.type === "fatal_error") fatalError = event;
    }
  }

  if (fatalError) {
    throw new Error(fatalError.detail);
  }
  if (!result) {
    throw new Error("Flux de génération interrompu avant la fin.");
  }
  return result;
}

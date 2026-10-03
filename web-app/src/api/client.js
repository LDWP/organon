// Client of the Organon API. The frontend reimplements no generation
// logic: it only calls this API (see organon/api/).
//
// Always same-origin: in dev Vite proxies /api/v1 to
// http://127.0.0.1:8123 (see vite.config.js); in production FastAPI
// serves the built frontend. The session cookie would not travel to
// another origin, and the backend does not enable CORS.
const API_BASE = "/api/v1";

async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`Erreur API (${res.status}) sur ${path}`);
  }
  return res.json();
}

// FastAPI error body: `detail` is a string, or an object { message,
// candidates } for homonym 409s (see organon/api/routes/update.py). A
// non-JSON body (e.g. a 502 from an intermediate proxy) falls back on
// the HTTP status.
async function postJson(path, payload) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* non-JSON body */
    }
    const err = new Error((typeof detail === "string" ? detail : detail?.message) || `Erreur API (${res.status})`);
    err.status = res.status;
    err.candidates = detail?.candidates ?? [];
    throw err;
  }
  return res;
}

async function apiPost(path, payload) {
  return (await postJson(path, payload)).json();
}

export function fetchDomains() {
  return apiGet("/domains");
}

export function fetchModules() {
  return apiGet("/modules");
}

// Overview of every database considered for the project, integrated or
// not (see organon/api/routes/sources.py). Feeds SourcesPage.jsx; not
// to be confused with fetchModules() above, which only covers the
// registered modules.
export function fetchSources() {
  return apiGet("/sources");
}

export function searchTaxa(query) {
  return apiGet(`/search?q=${encodeURIComponent(query)}`);
}

export function fetchAuthStatus() {
  return apiGet("/auth/me");
}

// Commons image suggestions for the taxobox (see
// organon/api/routes/commons_images.py), already filtered server-side
// by license and quality distinction, never a raw search to filter
// here.
export function fetchCommonsImages(taxon) {
  return apiGet(`/commons-images?taxon=${encodeURIComponent(taxon)}`);
}

// Merge the sub-taxa of several already resolved sources (see
// prefetchOtherClassifications in App.jsx). Cross-matching by exact
// name and per-species wikitext rendering are done server-side (see
// organon/api/routes/subtaxa_merge.py and
// organon/core/rendering/subtaxa_merge.py) to reuse the italics, author
// and extinct rules of subtaxa_wikitext without duplicating them here.
export function mergeSubtaxa(payload) {
  return apiPost("/subtaxa-merge", payload);
}

export const LOGIN_URL = `${API_BASE}/auth/login`;

export async function logout() {
  const res = await fetch(`${API_BASE}/auth/logout`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`Erreur API (${res.status}) sur /auth/logout`);
  }
  return res.json();
}

// Read-only diagnosis of the Wikidata and source gaps (see
// organon/api/routes/update.py). The error carries `status` and, for a
// 409 (homonyms), `candidates` (QIDs): the screen builds one message
// per case rather than a generic text.
export function diagnoseTaxon(payload) {
  return apiPost("/update/diagnose", payload);
}

// The server recomputes the diagnosis: send the same taxon and
// classification as for diagnoseTaxon, plus the ids of the checked
// proposals. It only returns QuickStatements text; nothing is written
// to Wikidata.
export function exportSuggestions(payload) {
  return apiPost("/update/export", payload);
}

// Consume POST /api/v1/generate/stream (Server-Sent Events). A
// generation with many applicable modules can take 10-20 s as one
// blocking request; the stream shows progress module by module (see
// organon/api/routes/generate.py: ModuleStatusEvent, PlanEvent,
// ResultEvent, FatalErrorEvent).
//
// Uses fetch() and ReadableStream rather than the native EventSource:
// EventSource only makes GET requests with no body, while the
// generation request carries a full JSON payload (taxon and all
// options) that must stay a POST.
//
// `onEvent(event)` is called for each decoded event, in arrival order,
// before the promise resolves with the final `result` data; a
// `fatal_error` (e.g. taxon not found) or a stream cut before any
// `result` rejects it instead.
export async function generateTaxonStream(payload, { onEvent } = {}) {
  const res = await postJson("/generate/stream", payload);
  if (!res.body) {
    // Browser without ReadableStream on Response.body (very old): no
    // fallback, the caller shows the error like any network failure.
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
    // last fragment, possibly incomplete, kept for the next chunk
    buffer = frames.pop();
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

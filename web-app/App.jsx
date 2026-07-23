import { useEffect, useRef, useState } from "react";
import {
  fetchAuthStatus,
  fetchDomains,
  fetchModules,
  generateTaxonStream,
  LOGIN_URL,
  logout,
  searchTaxa,
} from "./apiClient.js";
import SourcesPage from "./SourcesPage.jsx";
import AuthorsPage from "./AuthorsPage.jsx";
import ImageGallery from "./ImageGallery.jsx";
import { PreferencesBanner, PreferencesToggleButton } from "./StoragePreferencesBanner.jsx";
import { getStorageConsent, setStorageConsent } from "./storagePreferences.js";

const EXAMPLE_TAXON = "Gadus morhua";
const MORE_EXAMPLES = ["Panthera leo", "Quercus robur", "Amanita muscaria"];

// Miroir de wp_est_italique() (organon/core/rendering/grammar.py) : dans la plupart des règnes
// (végétal, champignon, bactérie, archaea, virus…) l'italique est systématique quel que soit le
// rang. Seuls les règnes suivants (proches de la convention zoologique) réservent l'italique au
// rang genre et en dessous — cf. DOMAINES_SANS_ITALIQUE_SYSTEMATIQUE côté backend. `kingdom` ici
// vient de KINGDOM_MAP (organon/core/domains.py) via /api/v1/search, donc déjà dans ce même
// vocabulaire ("animal", "protiste"…).
const REGNES_ITALIQUE_SELON_RANG = new Set(["animal", "reptile", "amphibien", "protiste", "eucaryote"]);

// Rangs pour lesquels `rang_inferieur_espece` vaut true dans organon/core/data/ranks.yaml (genre
// et rangs en dessous) — seuls ceux-ci s'italicisent pour les règnes de REGNES_ITALIQUE_SELON_RANG.
const RANGS_GENRE_ET_INFERIEURS = new Set([
  "genre", "sous-genre", "section", "sous-section", "série", "sous-série",
  "espèce", "sous-espèce", "variété", "forme", "sous-forme", "cultivar", "pathovar",
]);

function estRangItalique(rank, kingdom) {
  if (!REGNES_ITALIQUE_SELON_RANG.has(kingdom)) return true;
  return RANGS_GENRE_ET_INFERIEURS.has(rank);
}

function TaxonName({ match }) {
  return estRangItalique(match.rank, match.kingdom) ? (
    <em>{match.scientific_name}</em>
  ) : (
    <span>{match.scientific_name}</span>
  );
}

// Regroupe les suggestions en arbre. Priorité à la filiation *confirmée* par GBIF
// (`parent_key` d'un match pointant vers le `gbif_key` d'un autre match de la même réponse,
// ex. une sous-espèce sous son espèce) — affichée avec un connecteur "└". À défaut, repli sur
// une ressemblance textuelle (nom qui prolonge celui d'un autre match) restreinte au **même
// règne**, indentée mais sans connecteur puisque la filiation n'est alors pas garantie : sans
// cette restriction de règne, un virus nommé d'après son hôte (ex. "Panthera leo
// polyomavirus 1") se retrouverait à tort sous le taxon animal du même nom.
function buildDisambiguationTree(matches) {
  const byGbifKey = new Map();
  matches.forEach((m) => {
    if (m.gbif_key != null) byGbifKey.set(m.gbif_key, m);
  });

  const nodes = matches.map((m) => ({ match: m, children: [], confirmed: false }));
  const nodeByMatch = new Map(nodes.map((n) => [n.match, n]));
  const roots = [];

  nodes.forEach((node) => {
    const m = node.match;
    const confirmedParent = m.parent_key != null ? byGbifKey.get(m.parent_key) : null;
    if (confirmedParent && confirmedParent !== m) {
      node.confirmed = true;
      nodeByMatch.get(confirmedParent).children.push(node);
      return;
    }

    let parent = null;
    let bestLen = -1;
    nodes.forEach((candidate) => {
      if (candidate === node || candidate.match.kingdom !== m.kingdom) return;
      const prefix = candidate.match.scientific_name + " ";
      if (m.scientific_name.startsWith(prefix) && prefix.length > bestLen) {
        parent = candidate;
        bestLen = prefix.length;
      }
    });
    (parent || { children: roots }).children.push(node);
  });

  return roots;
}

function flattenDisambiguationTree(nodes, depth = 0, out = []) {
  nodes.forEach((node) => {
    out.push({ match: node.match, depth, confirmed: node.confirmed });
    flattenDisambiguationTree(node.children, depth + 1, out);
  });
  return out;
}

// Toolforge exige que le pied de page expose signalement de bug, documentation, code source,
// licence et auteur(s).
const AUTHOR_NAME = "Auteurs et crédits";
const LICENSE_URL = "https://www.gnu.org/licenses/gpl-3.0.html";
const BUG_REPORT_URL = "https://fr.wikipedia.org/wiki/Discussion_Projet:Biologie/Organon";
const REPO_URL = "https://github.com/LDWP/organon";
const DOCS_URL = "https://github.com/LDWP/organon/blob/master/README.md";

function getInitialTheme() {
  if (getStorageConsent() === "accepted") {
    try {
      const saved = localStorage.getItem("organon-theme");
      if (saved === "dark" || saved === "light") return saved;
    } catch {
      /* localStorage indisponible (navigation privée, etc.) */
    }
  }
  if (typeof window !== "undefined" && window.matchMedia) {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return "dark";
}

function SunIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z" />
    </svg>
  );
}

// Statuts d'un module (classification ou enrichissement) pendant une génération en flux
// (voir organon/api/routes/generate.py, ModuleStatusEvent). "pending" est un statut purement
// côté frontend (ajouté dès l'événement "plan", avant que le module ne démarre réellement) —
// le backend n'émet jamais "pending" lui-même. Remplace l'ancien indicateur `.dot`/`.dot warn`/
// `.dot off` (couleur seule, pas accessible aux daltoniens) : chaque statut a ici une forme ET
// un intitulé distincts, pas seulement une couleur.
const MODULE_STATUS_LABELS = {
  pending: "en attente",
  running: "recherche en cours",
  found: "trouvé",
  empty: "aucun résultat",
  error: "erreur réseau",
};

function ModuleStatusIcon({ status }) {
  const label = MODULE_STATUS_LABELS[status] || status;
  return (
    <span className={`module-status-icon module-status-${status}`} role="img" aria-label={label} title={label}>
      {status === "pending" && "○"}
      {status === "running" && <span className="module-status-spinner" aria-hidden="true" />}
      {status === "found" && "✓"}
      {status === "empty" && "✗"}
      {status === "error" && "⚠"}
      {status === "check" && "!"}
    </span>
  );
}

// Onglet Données : un tableau par état plutôt qu'une liste unique, pour que les modules qui
// n'ont rien trouvé (le cas courant) n'inondent pas ceux qui ont vraiment quelque chose à
// montrer. "running"/"pending" regroupés sous un même intitulé : la distinction entre les deux
// n'a d'intérêt que pendant le chargement initial, déjà visible ailleurs (icônes des onglets).
const STATUS_GROUPS = [
  { statuses: ["running", "pending"], label: "En cours" },
  { statuses: ["found"], label: "Données récoltées" },
  { statuses: ["empty"], label: "Aucun résultat" },
  { statuses: ["error"], label: "Erreur réseau" },
];

// Certains modules combinent plusieurs liens externes en un seul bloc HTML (ex. "externe" :
// Wikidata + Species + Commons + Commons catégorie, séparés par un espace) — les sépare en
// entrées distinctes, une par lien, pour qu'elles apparaissent sur des lignes propres du
// tableau plutôt qu'agglutinées dans une seule cellule. Un module à lien unique (cas courant)
// ressort inchangé, en une seule entrée sans étiquette propre.
function splitLinks(html) {
  const anchors = html.match(/<a[^>]*>.*?<\/a>/g);
  if (!anchors || anchors.length <= 1) return [{ label: null, html }];
  return anchors.map((anchorHtml) => {
    const label = anchorHtml.match(/>([^<]*)<\/a>/);
    return { label: label ? label[1] : null, html: anchorHtml };
  });
}

// Commentaire laissé par render_taxobox() (organon/core/rendering/sections.py) tant qu'aucune
// image n'a été choisie. Une sélection dans la galerie Commons (voir ImageGallery.jsx) ne
// relance pas de génération côté serveur : elle remplace directement ce commentaire dans le
// wikitexte déjà en cache côté frontend, appliqué à l'affichage plutôt qu'au cache lui-même pour
// que le choix survive un changement d'onglet de classification (voir applyImageSelection).
const IMAGE_PLACEHOLDER = "<!-- insérez une image -->";

function applyImageSelection(wikitext, fileName) {
  if (!fileName || !wikitext) return wikitext;
  return wikitext.replace(IMAGE_PLACEHOLDER, fileName);
}

export default function App() {
  const [theme, setTheme] = useState(getInitialTheme);
  const [domains, setDomains] = useState([]);
  const [modules, setModules] = useState([]);
  const [showSources, setShowSources] = useState(false);
  const [showAuthors, setShowAuthors] = useState(false);
  const [username, setUsername] = useState(null);
  const [storageConsent, setStorageConsentState] = useState(getStorageConsent);
  const [showStorageBanner, setShowStorageBanner] = useState(() => getStorageConsent() === null);

  const [taxon, setTaxon] = useState("");
  const [domaine, setDomaine] = useState("*");

  const [query, setQuery] = useState(null); // { taxon, domaine } une fois une recherche lancée
  // Liste de SearchMatch calculée à *chaque* recherche, quel que soit le mode actif — voir
  // resolveAndSearch : seul le mode "list" l'affiche (onglet "Liste"), les autres modes s'en
  // servent uniquement pour choisir automatiquement le meilleur taxon (nom vernaculaire,
  // scientifique ou nom+auteur) sans jamais montrer ce panneau.
  const [disambiguation, setDisambiguation] = useState(null);
  const [searchMode, setSearchMode] = useState("keyword"); // "keyword" | "list" | "autocomplete"
  const [autocompleteMatches, setAutocompleteMatches] = useState([]);
  const [autocompleteOpen, setAutocompleteOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const autocompleteTimer = useRef(null);
  const inputRef = useRef(null);
  const [initialLoading, setInitialLoading] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [activeSource, setActiveSource] = useState(null);
  // { [module_id]: { status: "loading"|"ok"|"error", data?, error?, moduleStatuses } } — chaque
  // source de classification porte son propre suivi de progression (`moduleStatuses`) pour que
  // le préchargement en arrière-plan des autres sources (voir prefetchOtherClassifications)
  // n'écrase jamais le suivi d'une source déjà terminée.
  const [resultsBySource, setResultsBySource] = useState({});
  // Choix manuel de l'utilisateur pour chaque facette du "zoom" classification (voir les deux
  // sélecteurs sous l'onglet Classification) — `null` tant qu'aucun choix explicite n'a été
  // fait, auquel cas la recommandation automatique par facette s'applique (voir
  // recommendedTaxoboxSource/recommendedSubtaxaSource ci-dessous). Les deux facettes sont
  // indépendantes : rien n'oblige à choisir la même source pour la taxobox et pour les
  // sous-taxons.
  const [taxoboxSourceOverride, setTaxoboxSourceOverride] = useState(null);
  const [subtaxaSourceOverride, setSubtaxaSourceOverride] = useState(null);
  // Active applyRankConflicts (insertion de {{Taxobox conflit}} en cas de désaccord de rang entre
  // sources) — désactivé par défaut car la majorité des groupes ne présentent pas de divergence
  // taxonomique significative ; à cocher au cas par cas pour les groupes qui en ont (poissons,
  // insectes...).
  const [gererConflits, setGererConflits] = useState(false);
  const [resultView, setResultView] = useState("result"); // "result" | "data"
  // Sous-onglets thématiques du panneau Résultat, un clic = un aspect de la taxobox à changer.
  const [resultSubTab, setResultSubTab] = useState("classification"); // "classification" | "image" | "autres"
  // Nom de fichier Commons choisi dans la galerie (voir ImageGallery.jsx), appliqué au wikitexte
  // affiché par applyImageSelection() plutôt que persisté dans resultsBySource : survit ainsi à
  // un changement d'onglet de classification, sans dupliquer l'état par source.
  const [selectedCommonsImage, setSelectedCommonsImage] = useState(null);
  // Suggestions Commons déjà récupérées, indexées par taxon (même principe que resultsBySource) :
  // ImageGallery est démonté/remonté à chaque fois qu'on quitte puis revient sur le sous-onglet
  // "Image" (rendu conditionnel, voir plus bas), donc son état local ne suffit pas à éviter une
  // nouvelle requête réseau à chaque retour sur l'onglet. En gardant les résultats ici, un
  // remontage retrouve directement l'entrée déjà en cache pour le taxon affiché.
  const [commonsImagesCache, setCommonsImagesCache] = useState({});
  // Incrémenté à chaque launchSearch : permet au préchargement en arrière-plan (une boucle
  // asynchrone longue) de détecter qu'une recherche plus récente a démarré entretemps et de
  // s'arrêter, plutôt que de continuer à peupler le cache d'une recherche obsolète.
  const searchGeneration = useRef(0);
  const [editing, setEditing] = useState(false);
  const [editedText, setEditedText] = useState("");
  // Wikitexte édité et validé ("Terminé"), en remplacement du wikitexte composé (voir
  // displayWikitext) — distinct de `resultsBySource[...].data.wikitext` puisque le texte
  // affiché est désormais composé dynamiquement (article de la source taxobox + bloc
  // sous-taxons de la source sélectionnée pour cette facette, voir spliceBlock). Remis à `null`
  // à chaque nouvelle recherche ou changement de sélection de facette, un peu comme `editing` :
  // une édition ne survit pas à un changement de ce qui est affiché.
  const [manualWikitext, setManualWikitext] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    if (storageConsent !== "accepted") return;
    try {
      localStorage.setItem("organon-theme", theme);
    } catch {
      /* pas grave si la préférence ne peut pas être sauvegardée */
    }
  }, [theme, storageConsent]);

  function handleAcceptStorage() {
    setStorageConsent("accepted");
    setStorageConsentState("accepted");
    setShowStorageBanner(false);
  }

  function handleRefuseStorage() {
    setStorageConsent("refused");
    setStorageConsentState("refused");
    setShowStorageBanner(false);
    try {
      localStorage.removeItem("organon-theme");
    } catch {
      /* rien à faire si le stockage est déjà indisponible */
    }
  }

  useEffect(() => {
    fetchDomains()
      .then((data) => setDomains(data))
      .catch(() => setDomains([]));
    fetchModules()
      .then((data) => setModules(data))
      .catch(() => setModules([]));
    fetchAuthStatus()
      .then((data) => setUsername(data.authenticated ? data.username : null))
      .catch(() => setUsername(null));
  }, []);

  async function handleLogout() {
    try {
      await logout();
    } finally {
      setUsername(null);
    }
  }

  const classificationModules = modules.filter((m) => m.can_classify);

  // Consomme les événements de POST /api/v1/generate/stream (voir organon/api/routes/
  // generate.py) pour peupler le suivi module par module *de la source `moduleId` concernée*
  // (voir resultsBySource[moduleId].moduleStatuses) — indispensable depuis que plusieurs
  // sources de classification peuvent être en cours (préchargement en arrière-plan) : un
  // suivi partagé mélangerait la progression de sources différentes. "plan" pré-remplit
  // toutes les lignes en "pending" dès que la liste des modules d'enrichissement est connue,
  // pour que l'utilisateur voie tout de suite l'ampleur du travail restant plutôt que des
  // lignes qui apparaissent une par une sans contexte.
  function handleGenerationEvent(moduleId, event) {
    if (event.type === "module_status") {
      setResultsBySource((prev) => ({
        ...prev,
        [moduleId]: {
          ...prev[moduleId],
          moduleStatuses: {
            ...prev[moduleId]?.moduleStatuses,
            [event.module_id]: { role: event.role, status: event.status, message: event.message },
          },
        },
      }));
    } else if (event.type === "plan") {
      setResultsBySource((prev) => {
        const next = { ...(prev[moduleId]?.moduleStatuses || {}) };
        for (const id of event.modules) {
          if (!next[id]) next[id] = { role: "enrichment", status: "pending" };
        }
        return { ...prev, [moduleId]: { ...prev[moduleId], moduleStatuses: next } };
      });
    }
  }

  // Récupère (ou re-récupère) une source de classification et la met en cache dans
  // `resultsBySource`, sans toucher `submitError`/`activeSource` — utilisée aussi bien pour la
  // recherche initiale que pour le préchargement silencieux des autres sources en arrière-plan
  // (voir prefetchOtherClassifications). Renvoie `{ data }` ou `{ error }` plutôt que de lever,
  // pour laisser l'appelant décider quoi faire de l'échec (l'un affiche `submitError`, l'autre
  // l'ignore et passe à la source suivante).
  async function fetchSource(taxonName, domaineValue, moduleId, gbifKey) {
    setResultsBySource((prev) => ({ ...prev, [moduleId]: { status: "loading", moduleStatuses: {} } }));
    try {
      const data = await generateTaxonStream(
        { taxon: taxonName, domaine: domaineValue, classification: moduleId, gbif_key: gbifKey },
        { onEvent: (event) => handleGenerationEvent(moduleId, event) }
      );
      setResultsBySource((prev) => ({
        ...prev,
        [data.classification_used]: { ...prev[data.classification_used], status: "ok", data },
      }));
      return { data };
    } catch (err) {
      const message = err.message || "Erreur inconnue lors de la génération.";
      setResultsBySource((prev) => ({ ...prev, [moduleId]: { ...prev[moduleId], status: "error", error: message } }));
      return { error: message };
    }
  }

  // Précharge en arrière-plan, toutes en parallèle, les sources de classification autres que
  // celle déjà affichée — pour qu'un clic sur un onglet de source ne déclenche plus jamais de
  // nouvelle requête visible (voir handleTabClick). Jusqu'à ~8 API taxonomiques tierces
  // sollicitées d'un coup par recherche : assumé pour la réactivité perçue plutôt qu'un
  // préchargement séquentiel qui ménageait ces API mais faisait traîner l'affichage des
  // sources les moins prioritaires.
  async function prefetchOtherClassifications(taxonName, domaineValue, excludeId, generation) {
    await Promise.all(
      classificationModules
        .filter((m) => m.id !== excludeId)
        .map((m) => {
          if (searchGeneration.current !== generation) return null; // recherche plus récente entretemps
          return fetchSource(taxonName, domaineValue, m.id);
        })
    );
  }

  async function launchSearch(taxonName, domaineValue, classification, gbifKey) {
    const generation = ++searchGeneration.current;
    setQuery({ taxon: taxonName, domaine: domaineValue });
    setResultsBySource({});
    setActiveSource(null);
    setSubmitError(null);
    setEditing(false);
    setManualWikitext(null);
    setSelectedCommonsImage(null);
    setCommonsImagesCache({});
    setTaxoboxSourceOverride(null);
    setSubtaxaSourceOverride(null);
    setInitialLoading(true);
    const { data, error } = await fetchSource(taxonName, domaineValue, classification, gbifKey);
    setInitialLoading(false);
    if (searchGeneration.current !== generation) return; // remplacée par une recherche plus récente
    if (data) {
      setActiveSource(data.classification_used);
      prefetchOtherClassifications(taxonName, domaineValue, data.classification_used, generation);
    } else {
      setSubmitError(error);
    }
  }

  // Recherche floue partagée par les trois modes (GET /api/v1/search, voir organon/api/routes/
  // search.py) : résout aussi bien un nom vernaculaire, un nom scientifique qu'un nom complet
  // avec auteur. Calculée à chaque soumission quel que soit le mode actif, pour que basculer
  // ensuite sur l'onglet "Liste" affiche instantanément ces correspondances sans nouvelle
  // requête (voir handleSearchModeChange/le rendu de la désambiguïsation ci-dessous, gardé par
  // `searchMode === "list"`) — seul ce mode l'affiche réellement à l'utilisateur.
  async function resolveAndSearch(name, domaineValue) {
    setSubmitError(null);
    setInitialLoading(true);
    let matches = [];
    try {
      const result = await searchTaxa(name);
      matches = result.matches || [];
    } catch {
      /* recherche indisponible : on tente quand même la génération directe ci-dessous */
    }
    setDisambiguation(matches);

    if (searchMode === "list") {
      setInitialLoading(false);
      return;
    }

    // Mot-clé / Autocomplétion (soumission directe sans passer par une suggestion) : on lance
    // la génération sur la meilleure correspondance (déjà triée par pertinence par le
    // backend), sans jamais montrer la liste. Repli sur le texte brut si la recherche floue
    // n'a rien trouvé — le module de classification peut malgré tout résoudre un nom
    // scientifique exact par sa propre voie.
    const best = matches[0];
    if (best) {
      await launchSearch(best.scientific_name, best.kingdom || domaineValue, "gbif");
    } else {
      await launchSearch(name, domaineValue, "gbif");
    }
  }

  function pickDisambiguation(match) {
    setTaxon(match.scientific_name);
    setDomaine(match.kingdom || domaine);
    setDisambiguation(null);
    // Tout résultat de recherche vient de GBIF (voir organon/api/routes/search.py) :
    // on force ce classifieur pour la génération plutôt que de laisser le backend
    // en choisir un automatiquement selon le domaine, ce qui pouvait échouer
    // (ex. "Acanthocephala" + filtre "végétal" → tentative via AlgaeBase). On transmet
    // aussi le gbif_key déjà résolu par la recherche de désambiguïsation : repartir du
    // seul nom textuel peut résoudre vers un autre enregistrement GBIF (ex. un nom
    // d'hôte qui ressemble à un nom d'espèce sans rapport), voir GbifModule._collect.
    launchSearch(match.scientific_name, match.kingdom || domaine, "gbif", match.gbif_key);
  }

  function handleTaxonInputChange(value) {
    setTaxon(value);
    if (searchMode !== "autocomplete") return;
    if (autocompleteTimer.current) clearTimeout(autocompleteTimer.current);
    const query = value.trim();
    if (query.length < 2) {
      setAutocompleteMatches([]);
      setAutocompleteOpen(false);
      return;
    }
    autocompleteTimer.current = setTimeout(async () => {
      try {
        const result = await searchTaxa(query);
        const matches = result.matches || [];
        setAutocompleteMatches(matches);
        setAutocompleteOpen(matches.length > 0);
        setHighlightedIndex(-1);
      } catch {
        setAutocompleteMatches([]);
        setAutocompleteOpen(false);
      }
    }, 300);
  }

  function pickAutocomplete(match) {
    setAutocompleteOpen(false);
    setTaxon(match.scientific_name);
    setDomaine(match.kingdom || domaine);
    launchSearch(match.scientific_name, match.kingdom || domaine, "gbif");
  }

  // Résultats d'autocomplétion filtrés côté client par le domaine sélectionné,
  // sans nouvel appel réseau (même logique que le filtrage du panneau de désambiguïsation).
  const visibleAutocompleteMatches =
    domaine === "*" ? autocompleteMatches : autocompleteMatches.filter((m) => m.kingdom === domaine);

  function handleTaxonInputKeyDown(event) {
    if (!autocompleteOpen || visibleAutocompleteMatches.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlightedIndex((i) => Math.min(i + 1, visibleAutocompleteMatches.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlightedIndex((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter" && highlightedIndex >= 0) {
      event.preventDefault();
      pickAutocomplete(visibleAutocompleteMatches[highlightedIndex]);
    } else if (event.key === "Escape") {
      setAutocompleteOpen(false);
    }
  }

  function handleSearchModeChange(mode) {
    setSearchMode(mode);
    setAutocompleteOpen(false);
    setAutocompleteMatches([]);
  }

  function handleSubmit(event) {
    event.preventDefault();
    const t = taxon.trim();
    if (!t) return;
    resolveAndSearch(t, domaine);
  }

  function handleExampleClick(name) {
    setTaxon(name);
    setDomaine("*");
    resolveAndSearch(name, "*");
  }

  function handleExample() {
    handleExampleClick(EXAMPLE_TAXON);
  }

  // Changer d'onglet ne relance plus de requête : toutes les sources sont déjà en cours de
  // préchargement en arrière-plan depuis le lancement (voir prefetchOtherClassifications) — un
  // clic ne fait que basculer l'affichage sur le cache déjà là (ou en cours de préchargement).
  // Seule exception : un onglet en erreur peut être relancé manuellement (action explicite de
  // l'utilisateur, pas une requête automatique au clic). Ces onglets ne pilotent plus la
  // composition de l'article (voir taxoboxSourceId/subtaxaSourceId ci-dessous, choisis
  // indépendamment via les sélecteurs de facette) : ils ne servent qu'à consulter les données
  // brutes d'une source (onglet Données, encart d'identité...).
  function handleTabClick(moduleId) {
    if (!query || moduleId === activeSource) return;
    setActiveSource(moduleId);
    setEditing(false);
    setManualWikitext(null);
    const existing = resultsBySource[moduleId];
    if (existing?.status === "error") {
      fetchSource(query.taxon, query.domaine, moduleId);
    }
  }

  // Une édition en cours ("Éditer") porte sur le wikitexte composé pour la sélection de
  // facette affichée au moment où elle a commencé : changer l'une ou l'autre facette invalide
  // ce texte édité, comme un changement d'onglet le faisait déjà (voir handleTabClick).
  function handleTaxoboxSourceChange(moduleId) {
    setTaxoboxSourceOverride(moduleId);
    setEditing(false);
    setManualWikitext(null);
  }

  function handleSubtaxaSourceChange(moduleId) {
    setSubtaxaSourceOverride(moduleId);
    setEditing(false);
    setManualWikitext(null);
  }

  // TODO: l'onglet "Noms & synonymes" n'existe pas encore (tâche séparée en cours) — brancher ce
  // handler sur son activation (ex. setResultView("names")) une fois qu'il sera créé, à la place
  // de ce no-op.
  function handleGoToNamesTab() {}

  // TODO: idem pour l'onglet "Autres informations" (pastille "éteint").
  function handleGoToOtherInfoTab() {}

  const activeEntry = activeSource ? resultsBySource[activeSource] : null;
  const activeData = activeEntry?.status === "ok" ? activeEntry.data : null;

  // Recommandation automatique, indépendante par facette (taxobox / sous-taxons) : un unique
  // `completeness_score` agrégé masquait le fait qu'une classification peut avoir la meilleure
  // taxobox sans avoir la meilleure liste de sous-taxons, ou l'inverse (voir
  // `taxobox_completeness_score`/`subtaxa_completeness_score` côté backend). Recalculée à
  // chaque rendu plutôt que stockée, pour suivre le préchargement en arrière-plan au fur et à
  // mesure que d'autres sources terminent.
  //
  // Départage en cas d'égalité (choix assumé, à ajuster si besoin) : `classificationModules`
  // est déjà trié par priorité décroissante côté backend (voir GET /api/v1/modules) ; on ne
  // remplace la recommandation qu'à score strictement supérieur, donc à égalité c'est la
  // source de plus haute priorité déclarée qui l'emporte — un critère simple et reproductible,
  // pas une tentative de mesurer la "cohérence" avec les autres sources ou la
  // "spécialisation" d'une source (nettement plus subjectif à définir).
  function recommendedSourceForFacet(scoreField) {
    let recommended = null;
    let bestScore = -1;
    for (const m of classificationModules) {
      const entry = resultsBySource[m.id];
      if (entry?.status !== "ok") continue;
      const score = entry.data[scoreField] ?? 0;
      if (score > bestScore) {
        recommended = m.id;
        bestScore = score;
      }
    }
    return recommended;
  }

  const recommendedTaxoboxSource = recommendedSourceForFacet("taxobox_completeness_score");
  const recommendedSubtaxaSource = recommendedSourceForFacet("subtaxa_completeness_score");

  // Source effective par facette : un choix manuel (sélecteurs, voir plus bas) prime sur la
  // recommandation automatique, elle-même prime sur l'onglet actif tant qu'aucune source n'a
  // encore abouti.
  const taxoboxSourceId = taxoboxSourceOverride ?? recommendedTaxoboxSource ?? activeSource;
  const subtaxaSourceId = subtaxaSourceOverride ?? recommendedSubtaxaSource ?? activeSource;

  const taxoboxEntry = taxoboxSourceId ? resultsBySource[taxoboxSourceId] : null;
  const taxoboxData = taxoboxEntry?.status === "ok" ? taxoboxEntry.data : null;
  const subtaxaEntry = subtaxaSourceId ? resultsBySource[subtaxaSourceId] : null;
  const subtaxaData = subtaxaEntry?.status === "ok" ? subtaxaEntry.data : null;

  // L'article de base (systématique, répartition, étymologie, publication originale, liens
  // externes...) vient de la source choisie pour la facette taxobox. Choix assumé : seules
  // deux facettes sont exposées à l'utilisateur (taxobox / sous-taxons, voir point 10 du
  // retour utilisateur), et le reste de l'article doit bien venir d'une source unique — la
  // taxobox est le choix le plus proche de l'ancienne notion de source "recommandée" globale.
  // Comme cette source alimente aussi directement la taxobox, aucune substitution n'est
  // nécessaire pour ce bloc : seul le bloc sous-taxons doit éventuellement être substitué
  // (voir spliceBlock ci-dessous).
  const baseData = taxoboxData;

  // Remplace, dans le wikitexte de base, un bloc de section par son équivalent d'une autre
  // source (no-op si les deux blocs sont identiques ou si l'un des deux manque) — c'est tout le
  // principe du "zoom" classification : changer de source pour une facette ne doit affecter que
  // la section correspondante, jamais le reste de l'article.
  function spliceBlock(baseWikitext, baseBlock, altBlock) {
    if (!baseBlock || !altBlock || baseBlock === altBlock) return baseWikitext;
    return baseWikitext.split(baseBlock).join(altBlock);
  }

  // Pour chaque rang, l'ensemble des noms distincts rapportés par les classifications déjà
  // résolues, avec la première source (dans l'ordre de priorité de `classificationModules`) à
  // avoir rapporté chacun — sert à repérer un désaccord de rang entre sources (ex. ITIS et
  // FishBase qui ne placent pas un genre dans le même ordre) sans dépendre de l'ordre d'arrivée
  // des réponses en arrière-plan.
  const rankDisagreements = {};
  for (const m of classificationModules) {
    const entry = resultsBySource[m.id];
    if (entry?.status !== "ok") continue;
    for (const { rang, nom } of entry.data.rank_lines || []) {
      if (!rankDisagreements[rang]) rankDisagreements[rang] = new Map();
      if (!rankDisagreements[rang].has(nom)) rankDisagreements[rang].set(nom, m.id);
    }
  }

  // Accord entre sources sur l'auteur du taxon : fusionne les candidats bruts rapportés par
  // chaque module (voir GenerateResponse.auteur_candidats, organon/api/schemas.py) pour
  // l'ensemble des classifications déjà résolues, pas seulement la source active — deux
  // générations différentes interrogent en général les mêmes modules d'enrichissement, donc
  // l'union couvre plus de candidats que ne le ferait le seul auteur_candidats de la source
  // affichée si une autre source (encore en préchargement) n'était pas prise en compte.
  const auteurCandidats = {};
  for (const m of classificationModules) {
    const entry = resultsBySource[m.id];
    if (entry?.status === "ok") Object.assign(auteurCandidats, entry.data.auteur_candidats);
  }
  const normalizeAuteur = (s) => s.trim().replace(/\s+/g, " ").replace(/\s*,\s*/g, ", ");
  const auteurValeurs = Object.values(auteurCandidats).filter(Boolean);
  const auteurVariantes = new Set(auteurValeurs.map(normalizeAuteur));
  // À défaut de l'auteur rapporté par la source affichée, retombe sur le premier candidat connu
  // (ex. la source active n'a elle-même pas rapporté d'auteur mais une autre source si).
  const auteurAffiche = auteurCandidats[activeSource] || auteurValeurs[0] || null;

  // Remplace, dans les lignes propres à la source taxobox affichée, celles dont le rang est
  // contesté par au moins une autre source par un {{Taxobox conflit}} listant chaque nom
  // concurrent et sa source — laisse les autres lignes intactes. N'agit que si la case "gérer
  // les conflits de classification" est cochée (voir gererConflits).
  function applyRankConflicts(wikitext, rankLines) {
    if (!rankLines || !gererConflits) return wikitext;
    let result = wikitext;
    const rangsResolus = new Set();
    for (const { rang, line } of rankLines) {
      const parNom = rankDisagreements[rang];
      if (!parNom || parNom.size < 2) continue;
      if (rangsResolus.has(rang)) {
        // Un même rang peut apparaître plusieurs fois dans rankLines (ex. ITIS rapportant
        // plusieurs genres équivalents pour un même taxon) : le conflit a déjà été inséré une
        // fois pour ce rang, on retire simplement la ligne redondante au lieu de le dupliquer.
        result = result.split(`${line}\n`).join("");
        continue;
      }
      rangsResolus.add(rang);
      const parts = [rang];
      for (const [autreNom, sourceId] of parNom) parts.push(autreNom, sourceId.toUpperCase());
      result = result.split(line).join(`{{Taxobox conflit | ${parts.join(" | ")} }}`);
    }
    return result;
  }

  const displayWikitext = baseData
    ? applyRankConflicts(
        spliceBlock(baseData.wikitext, baseData.subtaxa_wikitext, subtaxaData?.subtaxa_wikitext),
        taxoboxData?.rank_lines
      )
    : activeData?.wikitext ?? null;
  // Choix d'image appliqué en dernier, par-dessus le composé base+taxobox+conflits : c'est une
  // simple substitution de commentaire indépendante de la classification affichée, pas un
  // élément du "zoom" classification lui-même.
  const finalWikitext = applyImageSelection(manualWikitext ?? displayWikitext, selectedCommonsImage);

  function startEditing() {
    if (!finalWikitext) return;
    setEditedText(finalWikitext);
    setEditing(true);
  }

  function handleSelectCommonsImage(fileName) {
    setSelectedCommonsImage(fileName);
    if (editing) {
      // En édition, le texte affiché vient de editedText (indépendant du composé recalculé) :
      // sans ça, choisir une image pendant une édition en cours resterait invisible jusqu'à
      // "Terminé".
      setEditedText((prev) => applyImageSelection(prev, fileName));
    }
  }

  // Symétrique de handleSelectCommonsImage : revient à l'état "pas d'image" (IMAGE_PLACEHOLDER).
  // Hors édition, rien à faire sur le texte lui-même : displayWikitext est recomposé à chaque
  // rendu depuis le wikitexte d'origine (jamais muté), donc il contient toujours le placeholder
  // tant que selectedCommonsImage est vide. En édition en revanche, editedText a déjà reçu la
  // substitution en dur (voir handleSelectCommonsImage ci-dessus) : il faut l'inverser
  // explicitement pour que le placeholder réapparaisse dans le textarea.
  function handleDeselectCommonsImage() {
    if (editing && selectedCommonsImage) {
      setEditedText((prev) => prev.split(selectedCommonsImage).join(IMAGE_PLACEHOLDER));
    }
    setSelectedCommonsImage(null);
  }

  function stopEditing() {
    setEditing(false);
    setManualWikitext(editedText);
  }

  async function handleCopy() {
    const text = editing ? editedText : finalWikitext;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* presse-papiers indisponible (contexte non sécurisé, permissions) */
    }
  }

  return (
    <div className="app">
      <div className="scan" />
      <header>
        <div className="wrap topbar">
          <div className="brand">
            {username ? (
              <span className="auth-status">
                {username} ·{" "}
                <button type="button" className="footer-link" onClick={handleLogout}>
                  Se déconnecter
                </button>
              </span>
            ) : (
              <a className="footer-link" href={LOGIN_URL}>
                Se connecter
              </a>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <button type="button" className="status" onClick={() => setShowSources(true)}>
              <span className="live">
                {modules.length || "—"} source{modules.length > 1 ? "s" : ""} disponible
                {modules.length > 1 ? "s" : ""}
              </span>
            </button>
            <button
              type="button"
              className="icon-btn"
              onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
              aria-label="Basculer jour / nuit"
              title="Jour / nuit"
            >
              {theme === "dark" ? <SunIcon /> : <MoonIcon />}
            </button>
            <PreferencesToggleButton consent={storageConsent} onClick={() => setShowStorageBanner(true)} />
          </div>
        </div>
      </header>

      {showStorageBanner && <PreferencesBanner onAccept={handleAcceptStorage} onRefuse={handleRefuseStorage} />}

      <main className="wrap">
        {showSources ? (
          <SourcesPage modules={modules} onBack={() => setShowSources(false)} />
        ) : showAuthors ? (
          <AuthorsPage
            onBack={() => setShowAuthors(false)}
            onShowSources={() => {
              setShowAuthors(false);
              setShowSources(true);
            }}
          />
        ) : (
          <>
        <span className="eyebrow">Organon</span>
        <h1>
          Interrogez AlgaeBase, ITIS… — <em>en une requête</em>
        </h1>

        <div className="search-mode-toggle" role="radiogroup" aria-label="Mode de recherche">
          <button
            type="button"
            aria-pressed={searchMode === "keyword"}
            className={searchMode === "keyword" ? "on" : ""}
            onClick={() => handleSearchModeChange("keyword")}
          >
            Mot-clé
          </button>
          <button
            type="button"
            aria-pressed={searchMode === "list"}
            className={searchMode === "list" ? "on" : ""}
            onClick={() => handleSearchModeChange("list")}
          >
            Liste
          </button>
          <button
            type="button"
            aria-pressed={searchMode === "autocomplete"}
            className={searchMode === "autocomplete" ? "on" : ""}
            onClick={() => handleSearchModeChange("autocomplete")}
          >
            Autocomplétion
          </button>
          <span
            className="mode-help"
            aria-label="Différence entre les modes de recherche"
            title={
              "Mot-clé : recherche directe (nom vernaculaire, scientifique ou nom+auteur) — lance la génération tout de suite, sans liste.\n" +
              "Liste : affiche les taxons correspondants pour choisir le bon avant de générer.\n" +
              "Autocomplétion : suggestions de taxons en temps réel pendant la saisie."
            }
          >
            ?
          </span>
        </div>

        <form className="console" onSubmit={handleSubmit}>
          <div className="prompt">
            <span className="prompt-glyph">›</span>
            <input
              ref={inputRef}
              type="text"
              value={taxon}
              onChange={(e) => handleTaxonInputChange(e.target.value)}
              onKeyDown={handleTaxonInputKeyDown}
              onBlur={() => setTimeout(() => setAutocompleteOpen(false), 150)}
              placeholder="nom scientifique…"
              autoComplete="off"
              spellCheck="false"
              role="combobox"
              aria-expanded={autocompleteOpen}
              aria-autocomplete="list"
            />
          </div>
          {searchMode === "autocomplete" && autocompleteOpen && autocompleteMatches.length > 0 && (
            <ul className="autocomplete-dropdown" role="listbox">
              {visibleAutocompleteMatches.length === 0 && (
                <li className="autocomplete-empty">Aucun résultat pour le filtre « {domaine} ».</li>
              )}
              {visibleAutocompleteMatches.map((m, i) => (
                <li key={`${m.scientific_name}-${m.kingdom}-${i}`}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={i === highlightedIndex}
                    className={i === highlightedIndex ? "highlighted" : ""}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      pickAutocomplete(m);
                    }}
                  >
                    {m.extinct && <span aria-label="éteint" title="Éteint">†</span>}
                    <TaxonName match={m} />
                    {m.author && <span className="disambiguation-author">{m.author}</span>}
                    {m.kingdom && <span className="id-badge">{m.kingdom}</span>}
                    {m.rank && <span className="id-badge id-badge-rank">{m.rank}</span>}
                    {m.vernacular_names.length > 0 && (
                      <span className="disambiguation-vernacular">{m.vernacular_names.join(", ")}</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="divider" />
          <div className="params">
            <div className="field-box">
              <label className="field-label" htmlFor="domaine-select">
                Filtre
              </label>
              <select id="domaine-select" value={domaine} onChange={(e) => setDomaine(e.target.value)}>
                <option value="*">Aucun</option>
                {domains
                  .filter((d) => d.id !== "*")
                  .map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.id}
                    </option>
                  ))}
              </select>
            </div>
            <button className="run" type="submit" disabled={initialLoading}>
              {initialLoading ? "Recherche…" : "Lancer ▸"}
            </button>
          </div>
          <p className="example-row">
            exemples : <button type="button" onClick={handleExample}>{EXAMPLE_TAXON}</button>
            {MORE_EXAMPLES.map((name) => (
              <span key={name}>
                {" "}·{" "}
                <button type="button" onClick={() => handleExampleClick(name)}>{name}</button>
              </span>
            ))}
          </p>
          {submitError && <p className="error-banner">{submitError}</p>}
        </form>

        {searchMode === "list" && disambiguation && (() => {
          const visible = domaine === "*" ? disambiguation : disambiguation.filter((m) => m.kingdom === domaine);
          return (
          <div className="disambiguation">
            <p className="disambiguation-title">
              {disambiguation[0]?.source || "GBIF"} renvoie les taxons correspondant à la saisie — choisissez celui à générer :
            </p>
            {visible.length === 0 ? (
              <p className="disambiguation-empty">Aucun résultat avec le filtre « {domaine} ».</p>
            ) : (
              <ul>
                {flattenDisambiguationTree(buildDisambiguationTree(visible)).map(({ match: m, depth, confirmed }, i) => (
                  <li key={`${m.gbif_key ?? `${m.scientific_name}-${m.kingdom}`}-${i}`} style={{ paddingLeft: depth * 20 }}>
                    {/* eslint-disable-next-line react-hooks/refs -- pickDisambiguation ne lit
                        searchGeneration.current que depuis ce gestionnaire de clic, jamais
                        pendant le rendu ; faux positif de la règle sur cette chaîne d'appels. */}
                    <button type="button" onClick={() => pickDisambiguation(m)}>
                      {depth > 0 && confirmed && <span className="tree-connector">└</span>}
                      {m.extinct && <span aria-label="éteint" title="Éteint">†</span>}
                      <TaxonName match={m} />
                      {m.author && <span className="disambiguation-author">{m.author}</span>}
                      {m.kingdom && <span className="id-badge">{m.kingdom}</span>}
                      {m.rank && <span className="id-badge id-badge-rank">{m.rank}</span>}
                      {m.vernacular_names.length > 0 && (
                        <span className="disambiguation-vernacular">{m.vernacular_names.join(", ")}</span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="disambiguation-footer">
              <button type="button" className="edit-btn" onClick={() => handleSearchModeChange("keyword")}>
                Fermer
              </button>
            </div>
          </div>
          );
        })()}

        {query && (
          <div className="results">
            <div className="result-head">
              {activeData?.eteint && (
                <button type="button" className="id-badge id-badge-eteint id-badge-clickable" onClick={handleGoToOtherInfoTab}>
                  ✝ éteint
                </button>
              )}
              <h2>
                <em>{activeData?.taxon_resolved || query.taxon}</em>
              </h2>
              {activeData && (
                <button
                  type="button"
                  className={
                    "id-author" +
                    (auteurValeurs.length === 0 ? " id-author-missing" : auteurVariantes.size > 1 ? " id-author-conflict" : " id-author-ok")
                  }
                  onClick={handleGoToNamesTab}
                  title={auteurVariantes.size > 1 ? `Auteurs en désaccord entre sources : ${[...auteurVariantes].join(" / ")}` : undefined}
                >
                  {auteurValeurs.length === 0 ? "auteur ?" : auteurAffiche}
                </button>
              )}
              {activeData?.regne && <span className="id-badge">{activeData.regne}</span>}
              {/* TODO(écozone) : pastille écozone — donnée pas encore exposée dans activeData au
                  moment de cette tâche ; brancher ici une fois disponible côté API/frontend. */}
              {activeData?.vernacular_names?.length > 0 && (
                <button type="button" className="id-vernacular id-vernacular-clickable" onClick={handleGoToNamesTab}>
                  {activeData.vernacular_names[0]}
                  {activeData.vernacular_names.length > 1 ? "…" : ""}
                </button>
              )}
            </div>
            <div className="tabs result-view-tabs" role="tablist" aria-label="Vue du résultat">
              <button
                type="button"
                role="tab"
                aria-selected={resultView === "result"}
                className={"tab" + (resultView === "result" ? " on" : "")}
                onClick={() => setResultView("result")}
              >
                Résultat
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={resultView === "data"}
                className={"tab" + (resultView === "data" ? " on" : "")}
                onClick={() => setResultView("data")}
              >
                Données
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={resultView === "names"}
                className={"tab" + (resultView === "names" ? " on" : "")}
                onClick={() => setResultView("names")}
              >
                Noms &amp; synonymes
              </button>
            </div>

            {resultView === "names" ? (
              <div className="panel">
                <div className="panel-head">
                  <span className="t">Noms &amp; synonymes — {activeSource ? activeSource.toUpperCase() : "…"}</span>
                </div>
                {!activeData ? (
                  <p className="panel-empty">Aucune donnée disponible pour le moment.</p>
                ) : (
                  <>
                    <div className="data-table-wrap">
                      <h4 className="data-table-title">Auteur</h4>
                      {activeData.auteur_consolide ? (
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Retenu (vote majoritaire)</th>
                              <th>Candidats par source</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr>
                              <td>{activeData.auteur_consolide}</td>
                              <td>
                                {Object.entries(activeData.auteur_candidats).map(([moduleId, auteur]) => (
                                  <div key={moduleId}>
                                    <span className="id-badge">{moduleId.toUpperCase()}</span> {auteur}
                                  </div>
                                ))}
                              </td>
                            </tr>
                          </tbody>
                        </table>
                      ) : (
                        <p className="panel-empty">Aucun auteur rapporté pour ce taxon.</p>
                      )}
                    </div>

                    <div className="data-table-wrap">
                      <h4 className="data-table-title">Noms vernaculaires</h4>
                      {activeData.vernacular_names.length > 0 ? (
                        <p>{activeData.vernacular_names.join(", ")}</p>
                      ) : (
                        <p className="panel-empty">Aucun nom vernaculaire rapporté.</p>
                      )}
                    </div>

                    <div className="data-table-wrap">
                      <h4 className="data-table-title">
                        Synonymes
                        {activeData.synonymes_source ? ` — source : ${activeData.synonymes_source.toUpperCase()}` : ""}
                      </h4>
                      {activeData.synonymes.length > 0 ? (
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Nom</th>
                              <th>Auteur</th>
                              <th>Rang</th>
                            </tr>
                          </thead>
                          <tbody>
                            {activeData.synonymes.map((s, i) => (
                              <tr key={i}>
                                <td><em>{s.nom}</em></td>
                                <td>{s.auteur || "—"}</td>
                                <td>{s.rang || "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      ) : (
                        <p className="panel-empty">Aucun synonyme rapporté.</p>
                      )}
                    </div>

                    <div className="data-table-wrap">
                      <h4 className="data-table-title">Basionyme</h4>
                      {activeData.basionyme ? (
                        <p>
                          <em>{activeData.basionyme.nom}</em>
                          {activeData.basionyme.auteur ? ` ${activeData.basionyme.auteur}` : ""}{" "}
                          <span className="id-badge">{activeData.basionyme.source.toUpperCase()}</span>
                        </p>
                      ) : (
                        <p className="panel-empty">Aucun basionyme rapporté.</p>
                      )}
                    </div>
                  </>
                )}
              </div>
            ) : resultView === "data" ? (
              <div className="panel">
                <div className="panel-head">
                  <span className="t">Données — {activeSource ? activeSource.toUpperCase() : "…"}</span>
                </div>
                <div>
                  {activeData?.warnings.length > 0 && (
                    <div className="warnlist">
                      {activeData.warnings.map((w, i) => (
                        <p key={i}>⚠ {w}</p>
                      ))}
                    </div>
                  )}

                  {activeEntry?.moduleStatuses && Object.keys(activeEntry.moduleStatuses).length > 0 ? (
                    STATUS_GROUPS.map(({ statuses, label }) => {
                      const rows = Object.entries(activeEntry.moduleStatuses).filter(([, info]) =>
                        statuses.includes(info.status)
                      );
                      if (rows.length === 0) return null;
                      return (
                        <div className="data-table-wrap" key={label}>
                          <h4 className="data-table-title">{label}</h4>
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>Source</th>
                                <th>Statut</th>
                                <th>Informations</th>
                              </tr>
                            </thead>
                            <tbody>
                              {rows.flatMap(([moduleId, info]) => {
                                const link = activeData?.external_links.find((l) => l.module_id === moduleId);
                                const entries = link ? splitLinks(link.html) : [{ label: null, html: null }];
                                // Types d'information effectivement rapportés par ce module pour
                                // ce taxon (voir GenerateResponse.data_found côté backend) —
                                // dérivé de la structure déjà présente dans la réponse plutôt
                                // que deviné ici module par module.
                                const found = activeData?.data_found?.[moduleId] || [];
                                return entries.map((entry, i) => (
                                  <tr key={`${moduleId}-${i}`}>
                                    <td>
                                      <span className="id-badge">{moduleId.toUpperCase()}</span>
                                      {entry.html && <span dangerouslySetInnerHTML={{ __html: entry.html }} />}
                                    </td>
                                    <td>
                                      <ModuleStatusIcon status={info.status} />{" "}
                                      {info.status === "error" && info.message ? `erreur (${info.message})` : MODULE_STATUS_LABELS[info.status]}
                                    </td>
                                    <td>{i === 0 ? found.join(", ") : ""}</td>
                                  </tr>
                                ));
                              })}
                            </tbody>
                          </table>
                        </div>
                      );
                    })
                  ) : (
                    <p className="panel-empty">Aucun suivi disponible pour le moment.</p>
                  )}
                </div>
              </div>
            ) : (
              <>

                {activeData?.regne_incoherences?.length > 0 && (
                  <div className="regne-alert">
                    <p className="regne-alert-title">
                      ⚠ Possible homonymie inter-règnes : {activeData.regne_incoherences.length === 1 ? "une source" : "des sources"} suggère{activeData.regne_incoherences.length === 1 ? "" : "nt"} un règne différent.
                    </p>
                    <ul>
                      {activeData.regne_incoherences.map((inc, i) => (
                        <li key={i}>
                          <strong>{inc.module.toUpperCase()}</strong> suggère « {inc.regne_suggere} », règne retenu : « {inc.regne_retenu} »
                        </li>
                      ))}
                    </ul>
                    <p className="regne-alert-hint">
                      Ce nom pourrait désigner un autre taxon — vérifiez le titre de l'article ou l'homonymie avant publication.
                    </p>
                  </div>
                )}

                <div className="tabs subtabs" role="tablist" aria-label="Aspect de la taxobox à modifier">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={resultSubTab === "classification"}
                    className={"tab" + (resultSubTab === "classification" ? " on" : "")}
                    onClick={() => setResultSubTab("classification")}
                  >
                    Classification
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={resultSubTab === "image"}
                    className={"tab" + (resultSubTab === "image" ? " on" : "")}
                    onClick={() => setResultSubTab("image")}
                  >
                    Image
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={resultSubTab === "autres"}
                    className={"tab" + (resultSubTab === "autres" ? " on" : "")}
                    onClick={() => setResultSubTab("autres")}
                  >
                    Autres informations
                  </button>
                </div>

                {resultSubTab === "autres" ? (
                  <div className="panel">
                    {activeData ? (
                      <>
                        {activeData.milieu && (
                          <div className="field-box">
                            <span className="field-label">Écozone</span>
                            <p>{activeData.milieu === "marin" ? "Marin" : "Terrestre"}</p>
                          </div>
                        )}
                        <div className="field-box">
                          <span className="field-label">Répartition</span>
                          {activeData.distribution && Object.keys(activeData.distribution).length > 0 ? (
                            <ul>
                              {Object.entries(activeData.distribution).map(([moduleId, pays]) => (
                                <li key={moduleId}>
                                  <strong>{moduleId.toUpperCase()}</strong> : {pays.join(", ")}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="panel-empty">Aucune répartition disponible.</p>
                          )}
                        </div>
                      </>
                    ) : (
                      <p className="panel-empty">Aucune donnée disponible.</p>
                    )}
                  </div>
                ) : resultSubTab === "image" ? (
                  <div className="panel">
                    <ImageGallery
                      taxon={activeData?.taxon_resolved || query?.taxon || null}
                      selectedFileName={selectedCommonsImage}
                      onSelect={handleSelectCommonsImage}
                      onDeselect={handleDeselectCommonsImage}
                      cache={commonsImagesCache}
                      onCacheChange={setCommonsImagesCache}
                    />
                  </div>
                ) : (
                  <>
                    {(() => {
                      // Sources utilisables pour les sélecteurs de facette : uniquement celles
                      // déjà résolues avec succès (une source en erreur ou encore en cours de
                      // préchargement ne peut alimenter ni la taxobox ni les sous-taxons).
                      const availableSources = classificationModules.filter(
                        (m) => resultsBySource[m.id]?.status === "ok"
                      );
                      return (
                        availableSources.length > 0 && (
                          <div className="facet-controls">
                            <div className="field-box">
                              <label className="field-label" htmlFor="taxobox-source-select">
                                Taxobox
                              </label>
                              <select
                                id="taxobox-source-select"
                                value={taxoboxSourceId || ""}
                                onChange={(e) => handleTaxoboxSourceChange(e.target.value)}
                              >
                                {availableSources.map((m) => (
                                  <option key={m.id} value={m.id}>
                                    {m.id.toUpperCase()}
                                    {m.id === recommendedTaxoboxSource ? " (recommandé)" : ""}
                                  </option>
                                ))}
                              </select>
                            </div>
                            <div className="field-box">
                              <label className="field-label" htmlFor="subtaxa-source-select">
                                Taxons inférieurs
                              </label>
                              <select
                                id="subtaxa-source-select"
                                value={subtaxaSourceId || ""}
                                onChange={(e) => handleSubtaxaSourceChange(e.target.value)}
                              >
                                {availableSources.map((m) => (
                                  <option key={m.id} value={m.id}>
                                    {m.id.toUpperCase()}
                                    {m.id === recommendedSubtaxaSource ? " (recommandé)" : ""}
                                  </option>
                                ))}
                              </select>
                            </div>
                            <label className="facet-checkbox">
                              <input
                                type="checkbox"
                                checked={gererConflits}
                                onChange={(e) => setGererConflits(e.target.checked)}
                              />
                              Gérer les conflits de classification
                            </label>
                          </div>
                        )
                      );
                    })()}

                    <div className="tabs" role="tablist" aria-label="Parcourir les données brutes par source">
                      {/* Un module de classification qui n'a rien trouvé pour ce taxon (ex. AlgaeBase
                          pour un poisson) ne doit pas apparaître ici : le lister sans qu'il n'y ait
                          jamais de contenu ne fait que polluer la lisibilité des onglets. Ces onglets
                          servent uniquement à consulter les données brutes d'une source (onglet
                          Données, encart d'identité...) — le choix de la source qui alimente la
                          taxobox et celle qui alimente les sous-taxons se fait indépendamment via les
                          sélecteurs ci-dessus. */}
                      {classificationModules
                        .filter((m) => resultsBySource[m.id]?.status !== "error")
                        .map((m) => {
                        const entry = resultsBySource[m.id];
                        const tabStatus = !entry
                          ? "pending"
                          : entry.status === "loading"
                            ? "running"
                            : entry.status === "ok"
                              ? "found"
                              : "error";
                        return (
                          <button
                            key={m.id}
                            id={`tab-${m.id}`}
                            type="button"
                            role="tab"
                            aria-selected={activeSource === m.id}
                            aria-controls="result-panel"
                            className={"tab" + (activeSource === m.id ? " on" : "")}
                            onClick={() => handleTabClick(m.id)}
                            disabled={initialLoading}
                          >
                            <ModuleStatusIcon status={tabStatus} />
                            {m.id.toUpperCase()}
                          </button>
                        );
                      })}
                    </div>

                    <div className="panel" id="result-panel" role="tabpanel" aria-labelledby={activeSource ? `tab-${activeSource}` : undefined} tabIndex={-1}>
                      {!activeEntry && (
                        <div className="panel-loading">
                          <p>
                            {activeSource
                              ? `En attente du préchargement de ${activeSource.toUpperCase()}…`
                              : "Génération en cours…"}
                          </p>
                        </div>
                      )}

                      {activeEntry?.status === "loading" && (
                        <div className="panel-loading">
                          <p>Interrogation de {activeSource?.toUpperCase()}…</p>
                        </div>
                      )}

                      {activeEntry?.status === "error" && (
                        <div className="panel-empty">Aucune donnée disponible via {activeSource?.toUpperCase()} pour ce taxon.</div>
                      )}

                      {activeData && (
                        <>
                          <div className="panel-head">
                            <div className="panel-head-title">
                              <span className="t" id="wikitext-label">Wikitexte</span>
                              <span className="id-badge" title="Source utilisée pour la taxobox et le reste de l'article">
                                Taxobox : {taxoboxSourceId ? taxoboxSourceId.toUpperCase() : "—"}
                              </span>
                              <span className="id-badge" title="Source utilisée pour la liste des taxons de rang inférieur">
                                Taxons inférieurs : {subtaxaSourceId ? subtaxaSourceId.toUpperCase() : "—"}
                              </span>
                            </div>
                            <div style={{ display: "flex", gap: 8 }}>
                              <button
                                type="button"
                                className="edit-btn"
                                aria-pressed={editing}
                                onClick={editing ? stopEditing : startEditing}
                              >
                                {editing ? "✓ Terminé" : "✎ Éditer"}
                              </button>
                              <button type="button" className="edit-btn" onClick={handleCopy}>
                                {copied ? "Copié ✓" : "Copier"}
                              </button>
                            </div>
                          </div>
                          <textarea
                            className="wikitext"
                            aria-labelledby="wikitext-label"
                            spellCheck="false"
                            readOnly={!editing}
                            value={editing ? editedText : finalWikitext}
                            onChange={(e) => setEditedText(e.target.value)}
                          />
                        </>
                      )}
                </div>
              </>
            )}
              </>
            )}
          </div>
        )}
          </>
        )}
      </main>

      <footer>
        <div className="wrap">
          <p>
            Organon · api/v1 ·{" "}
            <button type="button" className="footer-link" onClick={() => setShowSources(true)}>
              sources
            </button>
          </p>
          <p className="footer-meta">
            <button type="button" className="footer-link" onClick={() => setShowAuthors(true)}>
              {AUTHOR_NAME}
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
    </div>
  );
}

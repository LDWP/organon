import { useEffect, useRef, useState } from "react";
import {
  fetchAuthStatus,
  fetchCommonsImages,
  fetchDomains,
  fetchModules,
  generateTaxonStream,
  LOGIN_URL,
  logout,
  mergeSubtaxa,
  searchTaxa,
} from "./apiClient.js";
import SourcesPage from "./SourcesPage.jsx";
import AuthorsPage from "./AuthorsPage.jsx";
import ImageGallery from "./ImageGallery.jsx";
import { PreferencesBanner, PreferencesToggleButton } from "./StoragePreferencesBanner.jsx";
import { getStorageConsent, setStorageConsent } from "./storagePreferences.js";

const EXAMPLE_TAXON = "Gadus morhua";
const MORE_EXAMPLES = ["Panthera leo", "Quercus robur", "Amanita muscaria"];

// Libellés français des codes de statut UICN (voir GenerateResponse.uicn_statut,
// organon.api.schemas) — mêmes codes que {{Taxobox UICN}} sur frwiki.
const UICN_LABELS = {
  EX: "Éteinte",
  EW: "Éteinte à l'état sauvage",
  RE: "Disparue au niveau régional",
  CR: "En danger critique d'extinction",
  EN: "En danger",
  VU: "Vulnérable",
  NT: "Quasi menacée",
  LC: "Préoccupation mineure",
  DD: "Données insuffisantes",
  NE: "Non évaluée",
};

// Sous-onglets du bloc wikitexte (voir wikitextSubTab côté App) : chacun affiche un seul bloc
// isolé renvoyé par le serveur, sauf "tout" qui garde le comportement historique (composé,
// éditable).
const WIKITEXT_SUBTABS = [
  { id: "tout", label: "Tout" },
  { id: "taxobox", label: "Taxobox" },
  { id: "image", label: "Image" },
  { id: "subrangs", label: "Sous-rangs" },
  { id: "references", label: "Références taxonomiques" },
];

// Titre de la boîte "rendu" affichée sous les contrôles de chaque sous-onglet en lecture seule
// (voir WIKITEXT_SUBTABS) — délimite visuellement le bloc de wikitexte du reste du sous-onglet.
// "tout" n'y figure pas : c'est l'article complet éditable, pas un aperçu d'un bloc isolé.
const RENDER_BOX_TITLES = {
  taxobox: "Rendu — bloc Taxobox",
  subrangs: "Rendu — liste des sous-rangs",
  references: "Rendu — liens externes",
};

// Abréviations officielles de {{Modèle:Taxoboxoutils rang}} sur frwiki : seule la branche
// "embranchement" a une forme courte (format=court) — classe/ordre/famille/genre et leurs
// composés (super-classe, sous-ordre…) n'ont pas d'abréviation standard côté frwiki et
// restent en toutes lettres dans le tableau de comparaison.
const RANK_ABBR = {
  "super-embranchement": "Super-embr.",
  "sous-embranchement": "Sous-embr.",
  "infra-embranchement": "Infra-embr.",
  "micro-embranchement": "Micro-embr.",
  "parv-embranchement": "Parv-embr.",
};

// Fusionne les chaînes de rangs de chaque source (déjà en ordre domaine -> espèce) en une seule
// liste pour le tableau de comparaison : la chaîne de la source recommandée (`backboneChain`)
// sert de colonne vertébrale figée, les rangs propres aux autres sources (granularité plus fine,
// ex. giga-classe chez WoRMS, ou un clade absent des autres) s'insèrent seulement entre les deux
// rangs de la colonne vertébrale qui les encadrent réellement dans la chaîne de leur propre
// source — jamais réordonnés au sein de cette chaîne. Un rang sans aucun ancrage dans la colonne
// vertébrale (aucun voisin partagé) est relégué en fin de tableau plutôt que positionné au hasard.
function mergeRankChains(backboneChain, otherChains) {
  const result = [...backboneChain];
  for (const chain of otherChains) {
    let pendingRun = [];
    const flushRun = (beforeIndex) => {
      if (pendingRun.length === 0) return;
      result.splice(beforeIndex ?? result.length, 0, ...pendingRun);
      pendingRun = [];
    };
    for (const rang of chain) {
      const idx = result.indexOf(rang);
      if (idx !== -1) {
        flushRun(idx);
      } else if (!pendingRun.includes(rang)) {
        pendingRun.push(rang);
      }
    }
    flushRun(null);
  }
  return result;
}

// Regroupe des colonnes consécutives (dans l'ordre de `sources`) qui partagent la même valeur
// affichée, pour le tableau de comparaison Taxobox — évite de répéter une valeur identique sur
// plusieurs colonnes adjacentes (ex. ITIS et WoRMS d'accord sur "classe"). Ne fusionne que des
// sources consécutives : ne réordonne jamais les colonnes, pour garder une position stable d'un
// rang à l'autre.
function mergeAdjacentEqual(sources, valueFor) {
  const groups = [];
  for (const source of sources) {
    const value = valueFor(source);
    const last = groups[groups.length - 1];
    if (last && last.value === value) last.sources.push(source);
    else groups.push({ value, sources: [source] });
  }
  return groups;
}

// Réordonne `sources` pour rassembler celles qui partagent la même valeur, même non consécutives
// dans l'ordre d'origine — contrairement à mergeAdjacentEqual, qui ne fusionne que des colonnes
// déjà adjacentes. Les groupes de valeurs gardent l'ordre de leur première apparition. Réservé
// aux tableaux à une seule ligne de données (ex. Auteur) : sur plusieurs lignes, un ordre qui
// regroupe bien une ligne peut désaligner les suivantes.
function groupSourcesByValue(sources, valueFor) {
  const bucket = new Map();
  const order = [];
  for (const source of sources) {
    const value = valueFor(source);
    if (!bucket.has(value)) {
      bucket.set(value, []);
      order.push(value);
    }
    bucket.get(value).push(source);
  }
  return order.flatMap((value) => bucket.get(value));
}

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

// Onglets de la coquille à navigation latérale du résultat, dans leur ordre d'affichage.
const RESULT_VIEWS = [
  { id: "wikitexte", label: "Résultats" },
  { id: "noms", label: "Noms & synonymes" },
  { id: "autres", label: "Autres informations" },
  { id: "data", label: "Données" },
];

// Extrait la cible du premier lien d'un bloc HTML de lien externe (voir ExternalLink côté
// backend, organon/api/schemas.py) pour en faire la cible du nom de module de l'onglet Données.
// Les attributs href des modules sont construits avec des guillemets simples (voir
// simple_debug_link, organon/modules/common.py) — accepter les deux évite de rater ces liens.
function extractHref(html) {
  const match = html?.match(/href=["']([^"']+)["']/);
  return match ? match[1] : null;
}

// "0,6 s" plutôt que "0.6s" : convention décimale française déjà utilisée ailleurs dans l'app.
function formatDuration(seconds) {
  return `${seconds.toLocaleString("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s`;
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

// Substitue l'auteur wikifié (GenerateResponse.auteur_resolu) de la source taxobox active par
// celui d'une autre source déjà préchargée (voir auteurSourceOverride/handleAuteurSourceChange)
// — sans nouvel appel réseau, sur le même principe que applyImageSelection : un remplacement de
// texte sur le wikitexte déjà en cache plutôt qu'une regénération serveur.
function applyAuteurOverride(wikitext, activeAuteurResolu, overrideAuteurResolu) {
  if (!wikitext || !activeAuteurResolu || !overrideAuteurResolu || activeAuteurResolu === overrideAuteurResolu) {
    return wikitext;
  }
  return wikitext.split(activeAuteurResolu).join(overrideAuteurResolu);
}

// Les blocs isolés (taxobox_wikitext, subtaxa_wikitext...) portent des retours à la ligne de
// tête/fin qui ne servent qu'à les séparer proprement lors de la composition dans le wikitexte
// complet (voir spliceBlock) — sans objet pour un aperçu isolé (onglets Taxobox/Sous-rangs/
// Références), où ils ne feraient qu'ajouter une ligne vide inutile en haut ou en bas.
function trimBlockForDisplay(text) {
  return text.replace(/^\n+/, "").replace(/\n+$/, "");
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
  // Choix manuel de l'utilisateur pour la facette taxobox du "zoom" classification (voir le
  // tableau de comparaison sous l'onglet Résultats > Taxobox) — `null` tant qu'aucun choix
  // explicite n'a été fait, auquel cas la recommandation automatique s'applique (voir
  // recommendedTaxoboxSource ci-dessous). La facette sous-taxons n'a plus de choix manuel : elle
  // suit toujours recommendedSubtaxaSource (voir subtaxaSourceId).
  const [taxoboxSourceOverride, setTaxoboxSourceOverride] = useState(null);
  // Choix manuel de la source d'auteur dans la carte "Auteur" de l'onglet Noms & synonymes —
  // `null` tant qu'aucun choix explicite n'a été fait, auquel cas le vote majoritaire du backend
  // (auteur_consolide) s'applique.
  const [auteurSourceOverride, setAuteurSourceOverride] = useState(null);
  // Résultat de la fusion (MergedSubtaxaResponse) une fois calculé, `null` tant qu'il n'y a pas
  // au moins deux sources avec des sous-taxons ou que l'appel est en cours/en erreur.
  const [subtaxaMerge, setSubtaxaMerge] = useState(null);
  // Case à cocher par espèce (clé = nom), indépendante du nombre de sources qui la rapportent —
  // initialisée depuis `default_checked` à l'arrivée de chaque espèce, puis laissée au contrôle
  // de l'utilisateur (voir toggleSubtaxaChecked). Une espèce déjà connue garde son état choisi
  // même si `subtaxaMerge` est recalculé (ex. une source de plus termine son préchargement).
  const [subtaxaChecked, setSubtaxaChecked] = useState({});
  // Rangs pour lesquels l'utilisateur a explicitement demandé à signaler le désaccord de source
  // dans le rendu (insertion de {{Taxobox conflit}}) — par rang plutôt qu'un interrupteur global,
  // pour laisser géré un rang contesté (ex. "classe") sans en marquer d'autres qui ne posent pas
  // de vrai problème éditorial. Coché depuis le tableau de comparaison de l'onglet Taxobox.
  const [managedRankConflicts, setManagedRankConflicts] = useState({});
  // Cases cochées/décochées manuellement dans le sous-onglet "Références taxonomiques" (voir
  // GenerateResponse.reference_items), par-dessus le défaut calculé côté backend
  // (item.default_checked, voir organon.core.selectors.coherence.reference_module_coherente) —
  // clé = module_id::wikitext de la ligne. `undefined` = pas de choix explicite, on suit le
  // défaut ; une entrée ici (true ou false) prime toujours sur ce défaut.
  const [referenceCheckedOverrides, setReferenceCheckedOverrides] = useState({});
  // Onglet actif de la coquille à navigation latérale du résultat.
  const [resultView, setResultView] = useState("wikitexte"); // "wikitexte" | "noms" | "autres" | "data"
  // Bloc de wikitexte affiché sous l'onglet "wikitexte" : "tout" reproduit le comportement
  // historique (article composé, éditable) ; "taxobox"/"subrangs" isolent un seul bloc du
  // serveur en lecture seule (voir GenerateResponse.taxobox_wikitext/subtaxa_wikitext) ; "image"
  // affiche la galerie Commons (voir ImageGallery.jsx), sans bloc de wikitexte associé ;
  // "references" recompose côté client le bloc à partir de reference_items et des cases cochées
  // (voir checkedReferencesWikitext) — aucun des quatre autres ne passe par la composition
  // finalWikitext.
  const [wikitextSubTab, setWikitextSubTab] = useState("tout"); // "tout" | "taxobox" | "image" | "subrangs" | "references"
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
  // Zone de wikitexte en cours d'édition (voir WIKITEXT_SUBTABS) — chaque zone (Tout, Taxobox,
  // Sous-rangs, Références) a son propre bouton Éditer et s'édite indépendamment des autres,
  // une seule à la fois puisqu'une seule est visible (celle de `wikitextSubTab`). `null` si
  // aucune édition en cours. `editedTexts` garde le texte en cours de saisie par zone, tant
  // qu'elle est en édition.
  const [editingSubTab, setEditingSubTab] = useState(null);
  const [editedTexts, setEditedTexts] = useState({});
  // Wikitexte édité et validé ("Terminé"), par zone — remplace le texte propre recalculé (voir
  // sourceTextBySubTab) tant qu'une nouvelle recherche ou un changement de facette ne l'a pas
  // réinitialisé. Pour "tout" ceci remplace le wikitexte composé (voir displayWikitext),
  // distinct de `resultsBySource[...].data.wikitext` puisque le texte affiché est désormais
  // composé dynamiquement (article de la source taxobox + bloc sous-taxons de la source
  // sélectionnée pour cette facette, voir spliceBlock). Les trois autres zones n'ont pas
  // d'incidence sur le reste de l'article : éditer une zone n'y sert qu'à ajuster le texte
  // affiché avant de le copier, mais l'ajustement reste visible tant qu'on ne relance pas de
  // recherche ou de changement de facette — sans quoi cliquer "Terminé" n'aurait aucun effet
  // visible.
  const [manualOverrides, setManualOverrides] = useState({});
  // Zones "contrôles" (choix par rang de la Taxobox, checklist des références, bascule de
  // fusion des sous-rangs) repliées par l'utilisateur — repliée une fois le choix fait, pour
  // ne garder que l'en-tête et réduire l'encombrement visuel.
  const [collapsedControlBoxes, setCollapsedControlBoxes] = useState({});
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
  // Sert à la puce de chargement sur l'onglet "Résultats" : un module non applicable au domaine
  // du taxon (ex. AlgaeBase pour une bactérie) n'est jamais interrogé et n'aura donc jamais
  // d'entrée dans resultsBySource — le compter comme "en attente" au même titre qu'un module
  // réellement en vol faisait tourner la puce indéfiniment (elle ne se réglait alors que sur
  // l'absence d'erreur globale, pas sur l'état réel des requêtes). Ne regarder que les entrées
  // existantes en "loading" reflète l'état réel, quel que soit le sous-ensemble de modules
  // effectivement sollicité pour ce domaine.
  const hasPendingClassification = Object.values(resultsBySource).some((entry) => entry.status === "loading");

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
            [event.module_id]: {
              role: event.role,
              status: event.status,
              message: event.message,
              durationSeconds: event.duration_seconds,
            },
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
      // `data.classification_used` peut différer de `moduleId` : un choix explicite qui échoue
      // au réseau peut désormais aboutir sur un autre module en repli (voir
      // _classification_network_fallback, organon/api/routes/generate.py). Sans mettre aussi à
      // jour la clé `moduleId` (celle passée à "loading" plus haut), elle resterait bloquée à
      // "loading" indéfiniment — c'est ce qui faisait tourner la puce de chargement sans fin. Le
      // suivi module par module (moduleStatuses) accumulé pendant tout le streaming reste, lui,
      // sous la clé `moduleId` (handleGenerationEvent l'utilise depuis la fermeture ci-dessus) :
      // sans le reporter aussi sous `data.classification_used`, l'onglet Données de la source
      // gagnante resterait vide malgré un suivi réellement disponible.
      setResultsBySource((prev) => ({
        ...prev,
        [moduleId]: { ...prev[moduleId], status: "ok", data },
        [data.classification_used]: {
          ...prev[data.classification_used],
          status: "ok",
          data,
          moduleStatuses: prev[moduleId]?.moduleStatuses,
        },
      }));
      return { data };
    } catch (err) {
      const message = err.message || "Erreur inconnue lors de la génération.";
      setResultsBySource((prev) => ({ ...prev, [moduleId]: { ...prev[moduleId], status: "error", error: message } }));
      return { error: message };
    }
  }

  // Précharge en arrière-plan, toutes en parallèle, les sources de classification autres que
  // celle déjà affichée — pour que changer de source dans les sélecteurs de facette ne déclenche
  // plus jamais de nouvelle requête visible. Jusqu'à ~8 API taxonomiques tierces
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
    setEditingSubTab(null);
    setEditedTexts({});
    setManualOverrides({});
    setSelectedCommonsImage(null);
    setCommonsImagesCache({});
    setTaxoboxSourceOverride(null);
    setSubtaxaMerge(null);
    setSubtaxaChecked({});
    setManagedRankConflicts({});
    setReferenceCheckedOverrides({});
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

    // Sans correspondance GBIF (seule source de /api/v1/search), pas de classification forcée :
    // le backend interroge tous les modules applicables en parallèle.
    const best = matches[0];
    if (best) {
      await launchSearch(best.scientific_name, best.kingdom || domaineValue, "gbif");
    } else {
      await launchSearch(name, domaineValue, undefined);
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

  // Relance manuelle d'un module en erreur depuis l'onglet Données. Une erreur de classification
  // n'a encore rien collecté pour cette source : repart d'une régénération complète (même chemin
  // que la recherche initiale). Un module d'enrichissement en erreur, lui, n'a pas de point
  // d'entrée propre côté backend, mais `GenerateOptions.off` permet de désactiver tous les autres
  // modules déjà résolus pour que seul celui-ci soit effectivement rappelé sur le réseau (la
  // classification, elle, est ré-exécutée dans tous les cas : le backend ne conserve aucun état
  // entre deux requêtes). Seules ses données namespacées par module (data_found/distribution/
  // auteur_candidats/external_links) sont ensuite fusionnées dans le résultat déjà affiché — le
  // reste (wikitexte composé, noms vernaculaires...) resterait tronqué si on le prenait de cette
  // réponse partielle, puisque les autres modules n'y ont pas tourné.
  function retryModule(moduleId) {
    if (!query || !activeSource) return;
    const statuses = resultsBySource[activeSource]?.moduleStatuses || {};
    if (statuses[moduleId]?.role !== "enrichment") {
      // Un candidat de classification en erreur (ex. GBIF) n'est pas forcément `activeSource` —
      // depuis le repli parallèle entre classifications (voir _classification_candidates,
      // organon/api/routes/generate.py), plusieurs candidats peuvent apparaître ici, un seul
      // ayant gagné. Relancer `activeSource` au lieu du module cliqué re-régénérait la source
      // déjà réussie au lieu de retenter celle réellement en échec.
      fetchSource(query.taxon, query.domaine, moduleId);
      return;
    }
    const off = Object.entries(statuses)
      .filter(([id, info]) => info.role === "enrichment" && id !== moduleId)
      .map(([id]) => id);

    generateTaxonStream(
      { taxon: query.taxon, domaine: query.domaine, classification: activeSource, off },
      {
        onEvent: (event) => {
          if (event.type === "module_status" && event.module_id === moduleId) {
            handleGenerationEvent(activeSource, event);
          }
        },
      }
    )
      .then((data) => {
        // `classification: activeSource` est explicite, mais peut désormais aboutir sur un
        // autre module en repli réseau (voir _classification_network_fallback,
        // organon/api/routes/generate.py) si activeSource lui-même échoue sur cette relance.
        // Fusionner quand même reviendrait à attribuer les données d'enrichissement d'une autre
        // classification à activeSource — on abandonne la fusion ciblée dans ce cas plutôt que
        // de corrompre le cache (fetchSource, appelé séparément pour le vrai gagnant, prend le
        // relais normalement).
        if (data.classification_used !== activeSource) return;
        setResultsBySource((prev) => {
          const prevData = prev[activeSource]?.data;
          if (!prevData) return prev;
          return {
            ...prev,
            [activeSource]: {
              ...prev[activeSource],
              data: {
                ...prevData,
                data_found: moduleId in data.data_found
                  ? { ...prevData.data_found, [moduleId]: data.data_found[moduleId] }
                  : prevData.data_found,
                distribution: moduleId in data.distribution
                  ? { ...prevData.distribution, [moduleId]: data.distribution[moduleId] }
                  : prevData.distribution,
                auteur_candidats: moduleId in data.auteur_candidats
                  ? { ...prevData.auteur_candidats, [moduleId]: data.auteur_candidats[moduleId] }
                  : prevData.auteur_candidats,
                external_links: [
                  ...prevData.external_links.filter((l) => l.module_id !== moduleId),
                  ...data.external_links.filter((l) => l.module_id === moduleId),
                ],
              },
            },
          };
        });
      })
      .catch((err) => {
        const message = err.message || "Erreur inconnue lors de la génération.";
        setResultsBySource((prev) => ({
          ...prev,
          [activeSource]: {
            ...prev[activeSource],
            moduleStatuses: {
              ...prev[activeSource].moduleStatuses,
              [moduleId]: { ...prev[activeSource].moduleStatuses[moduleId], status: "error", message },
            },
          },
        }));
      });
  }

  // Une édition (en cours ou déjà validée par "Terminé") porte sur le contenu affiché pour la
  // sélection de facette au moment où elle a eu lieu (le choix de source alimente aussi bien
  // "tout" que "taxobox" et "références") : changer la facette invalide toute édition, quelle
  // que soit la zone.
  function handleTaxoboxSourceChange(moduleId) {
    setTaxoboxSourceOverride(moduleId);
    setEditingSubTab(null);
    setManualOverrides({});
  }

  function handleAuteurSourceChange(moduleId) {
    setAuteurSourceOverride(moduleId);
  }

  function toggleRankConflictManaged(rang) {
    setManagedRankConflicts((prev) => ({ ...prev, [rang]: !prev[rang] }));
  }

  function referenceItemKey(item) {
    return `${item.module_id}::${item.wikitext}`;
  }

  function toggleReferenceItem(key, currentChecked) {
    setReferenceCheckedOverrides((prev) => ({ ...prev, [key]: !currentChecked }));
  }

  function handleGoToNamesTab() {
    setResultView("noms");
  }

  function handleGoToOtherInfoTab() {
    setResultView("autres");
  }

  const activeEntry = activeSource ? resultsBySource[activeSource] : null;
  const activeData = activeEntry?.status === "ok" ? activeEntry.data : null;

  // Lance la recherche d'images Commons dès que le taxon est connu, sans attendre que
  // l'utilisateur ouvre le sous-onglet "Image" (voir WIKITEXT_SUBTABS) — ImageGallery.jsx est
  // démonté/remonté à chaque bascule de sous-onglet, un effet posé là-bas manquerait donc les
  // recherches précédentes tant que l'onglet n'a jamais été ouvert.
  const commonsTaxon = activeData?.taxon_resolved || query?.taxon || null;
  useEffect(() => {
    if (!commonsTaxon || commonsImagesCache[commonsTaxon]) return;
    setCommonsImagesCache((prev) => ({ ...prev, [commonsTaxon]: { status: "loading" } }));
    fetchCommonsImages(commonsTaxon)
      .then((data) => {
        setCommonsImagesCache((prev) => ({ ...prev, [commonsTaxon]: { status: "ok", data } }));
      })
      .catch((err) => {
        setCommonsImagesCache((prev) => ({
          ...prev,
          [commonsTaxon]: { status: "error", error: err.message || "Erreur inconnue." },
        }));
      });
  }, [commonsTaxon, commonsImagesCache]);

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
  const subtaxaSourceId = recommendedSubtaxaSource ?? activeSource;

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

  // Cas particulier des sous-taxons : la source recommandée pour la Taxobox (voir baseData) peut
  // n'avoir rapporté aucun sous-taxon (baseData.subtaxa_wikitext vide) alors que la source
  // recommandée pour cette facette (subtaxaSourceId) en a — spliceBlock ne peut alors rien
  // remplacer faute d'ancre, et la liste disparaît silencieusement de "tout". On insère le bloc
  // juste avant "== Systématique ==", qui suit toujours immédiatement la section sous-taxons dans
  // l'ordre de rendu (voir organon/core/rendering/engine.py:render) : ça reproduit exactement la
  // position qu'aurait occupée le bloc si la source de base l'avait elle-même rapporté.
  function spliceSubtaxaBlock(baseWikitext, baseBlock, altBlock) {
    if (!altBlock || baseBlock === altBlock) return baseWikitext;
    if (baseBlock) return baseWikitext.split(baseBlock).join(altBlock);
    const idx = baseWikitext.indexOf("== Systématique ==");
    if (idx === -1) return baseWikitext;
    const before = baseWikitext.slice(0, idx).replace(/\n+$/, "");
    const trimmedAlt = altBlock.replace(/^\n+|\n+$/g, "");
    return `${before}\n\n${trimmedAlt}\n\n${baseWikitext.slice(idx)}`;
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
  // Sources utilisables pour les sélecteurs de facette et la comparaison par rang : uniquement
  // celles déjà résolues avec succès (une source en erreur ou encore en cours de préchargement
  // ne peut alimenter ni la taxobox ni les sous-taxons).
  const availableSources = classificationModules.filter((m) => resultsBySource[m.id]?.status === "ok");

  // Sources utilisables pour la fusion des sous-taxons (voir POST /api/v1/subtaxa-merge) :
  // celles qui ont effectivement rapporté des sous-taxons (GenerateResponse.subtaxa_liste),
  // sous-ensemble d'availableSources qui exige en plus une liste non vide.
  const subtaxaMergeSources = availableSources
    .map((m) => ({ id: m.id, liste: resultsBySource[m.id]?.data?.subtaxa_liste || [] }))
    .filter((s) => s.liste.length > 0);
  // Signature stable (id + nombre d'espèces par source) : dépendance d'effet pour ne relancer
  // l'appel /subtaxa-merge que lorsque l'ensemble de sources disponibles change réellement,
  // plutôt qu'à chaque rendu (subtaxaMergeSources est un nouveau tableau à chaque appel).
  const subtaxaMergeSignature = subtaxaMergeSources.map((s) => `${s.id}:${s.liste.length}`).join(",");

  // `false` tant qu'il n'y a pas au moins deux sources avec des sous-taxons : dans ce cas
  // l'effet ci-dessous n'a rien à faire (pas d'appel réseau), et `subtaxaMerge` est ignoré au
  // profit de `effectiveSubtaxaMerge` (dérivé, pas besoin d'un setState synchrone dans l'effet
  // pour "réinitialiser" un état qui peut se déduire directement du rendu courant).
  const subtaxaMergeReady = subtaxaMergeSources.length >= 2 && !!baseData;
  const effectiveSubtaxaMerge = subtaxaMergeReady ? subtaxaMerge : null;
  // Fusion systématique dès qu'elle est possible : plus de bascule manuelle vers la source
  // unique (redondante avec le repli/dépli de la carte "Sous-rangs", voir collapsedControlBoxes).
  const subtaxaFusionEnabled = subtaxaMergeReady;

  // Calcule (ou recalcule) la fusion dès qu'au moins deux sources ont des sous-taxons — pas
  // besoin d'attendre que l'utilisateur ouvre le sous-onglet correspondant, l'appel est un pur
  // calcul local côté serveur (aucun accès réseau tiers, voir organon/api/routes/
  // subtaxa_merge.py), donc peu coûteux à anticiper pendant le préchargement en arrière-plan.
  useEffect(() => {
    if (!subtaxaMergeReady) return;
    let cancelled = false;
    mergeSubtaxa({
      taxon_rang: baseData.taxon_rang,
      taxon_nom: baseData.taxon_resolved,
      regne: baseData.regne,
      sources: subtaxaMergeSources.map((s) => ({ module_id: s.id, liste: s.liste })),
    })
      .then((data) => {
        if (cancelled) return;
        setSubtaxaMerge(data);
        // Une espèce déjà connue garde l'état choisi par l'utilisateur ; seules les espèces
        // nouvellement apparues (ex. une source de plus vient de terminer son préchargement)
        // reçoivent leur default_checked.
        setSubtaxaChecked((prev) => {
          const next = { ...prev };
          for (const g of data.groups) {
            for (const s of g.species) {
              if (!(s.nom in next)) next[s.nom] = s.default_checked;
            }
          }
          return next;
        });
      })
      .catch(() => {
        if (!cancelled) setSubtaxaMerge(null);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subtaxaMergeReady, subtaxaMergeSignature, baseData?.taxon_rang, baseData?.taxon_resolved, baseData?.regne]);

  function toggleSubtaxaChecked(nom) {
    setSubtaxaChecked((prev) => ({ ...prev, [nom]: !prev[nom] }));
  }

  // Fragments de phrase par nature de groupe (voir MergedGroup.kind côté serveur) — seul le
  // compte (réactif aux cases cochées) et ce texte fixe restent à composer ici ; la citation
  // Bioref par source (group.intro) et le rendu wikitexte par espèce (species[].line) sont déjà
  // mis en forme côté serveur (voir organon/core/rendering/subtaxa_merge.py), pas dupliqués ici.
  // Accord singulier/pluriel : rangTxt/rangTxtSingulier viennent du serveur (ex.
  // "espèces"/"espèce") — le compte étant réactif aux cases cochées, seul le choix entre les
  // deux formes déjà fournies se fait ici, jamais une pluralisation devinée en JS.
  const SUBTAXA_MERGE_MIDDLE = {
    anchor: (n, rangTxt, rangTxtSingulier) => `comprend ${n} ${n === 1 ? rangTxtSingulier : rangTxt}`,
    autres: (n, rangTxt, rangTxtSingulier) =>
      n === 1 ? `comprend 1 autre ${rangTxtSingulier}` : `comprend ${n} autres ${rangTxt}`,
    disjoint: (n, rangTxt, rangTxtSingulier) =>
      `comprend ${n} ${n === 1 ? rangTxtSingulier : rangTxt} ne figurant dans aucune de ces listes`,
  };

  // Compose le bloc "sous-taxons" en mode fusionné : une phrase par groupe non vide (un groupe
  // entièrement décoché disparaît du rendu), suivie des lignes déjà rendues des espèces cochées.
  // La toute première phrase effectivement rendue nomme le taxon ("le genre X comprend...") ;
  // les suivantes reprennent l'anaphore `pronoun` ("il comprend..."). Basé sur la première
  // phrase RENDUE (pas sur `kind === "anchor"`) : si l'utilisateur décoche entièrement le groupe
  // ancre, la phrase suivante doit nommer le taxon puisque rien n'a encore été dit dans le
  // rendu final.
  function renderSubtaxaMergeWikitext() {
    if (!effectiveSubtaxaMerge) return "";
    const { rang_txt: rangTxt, rang_txt_singulier: rangTxtSingulier, pronoun, taxon_phrase: taxonPhrase } =
      effectiveSubtaxaMerge;
    const parts = [];
    for (const group of effectiveSubtaxaMerge.groups) {
      const checked = group.species.filter((s) => subtaxaChecked[s.nom] ?? s.default_checked);
      if (checked.length === 0) continue;
      const sujet = parts.length === 0 ? taxonPhrase : pronoun;
      const middle = SUBTAXA_MERGE_MIDDLE[group.kind](checked.length, rangTxt, rangTxtSingulier);
      parts.push(`${group.intro}, ${sujet} ${middle} :\n${checked.map((s) => s.line).join("")}`);
    }
    if (parts.length === 0) return "";
    return `\n== Liste des ${rangTxt} ==\n${parts.join("\n")}`;
  }

  const subtaxaMergeWikitext = subtaxaFusionEnabled ? renderSubtaxaMergeWikitext() : "";

  // Version tabulaire de rankDisagreements pour le tableau de comparaison de l'onglet Résultats >
  // Taxobox : pour chaque rang, les noms rapportés par chaque source, afin de comparer les
  // classifications côte à côte plutôt que de ne garder que le premier nom rencontré par rang.
  // L'ordre des lignes fusionne les chaînes de rangs propres à chaque source (voir
  // mergeRankChains) plutôt que de suivre une échelle taxonomique externe : la chaîne de la
  // source recommandée (`recommendedTaxoboxSource`) sert de colonne vertébrale, les rangs propres
  // aux autres sources ne s'insèrent qu'entre les rangs de cette colonne qui les encadrent
  // réellement pour cette source — sans jamais réordonner la chaîne d'une source par rapport à
  // elle-même. Un rang sans aucun ancrage dans la colonne vertébrale reste "décousu" en fin de
  // tableau (les autres colonnes affichent "—") plutôt que d'être positionné au hasard.
  const classificationTableRows = (() => {
    const perModule = {};
    const chainByModule = {};
    for (const m of availableSources) {
      perModule[m.id] = {};
      const rankLines = resultsBySource[m.id].data.rank_lines || [];
      const chain = [];
      // rank_lines est ordonné du rang le plus proche du taxon au plus éloigné (voir
      // compute_rank_lines, organon/core/rendering/sections.py) ; on le parcourt à l'envers pour
      // obtenir la chaîne domaine -> espèce propre à cette source.
      for (let i = rankLines.length - 1; i >= 0; i--) {
        const { rang, nom } = rankLines[i];
        if (!chain.includes(rang)) chain.push(rang);
        if (!perModule[m.id][rang]) perModule[m.id][rang] = [];
        if (!perModule[m.id][rang].includes(nom)) perModule[m.id][rang].push(nom);
      }
      chainByModule[m.id] = chain;
    }
    const backboneId = recommendedTaxoboxSource ?? availableSources[0]?.id;
    const backboneChain = chainByModule[backboneId] || [];
    const otherChains = availableSources.filter((m) => m.id !== backboneId).map((m) => chainByModule[m.id]);
    return { order: mergeRankChains(backboneChain, otherChains), perModule };
  })();

  // Nom retenu par rang pour la source taxobox actuellement affichée — sert à ne mettre en
  // évidence, dans le tableau de comparaison, que les noms qui *diffèrent* de ce choix.
  const taxoboxNomByRang = {};
  for (const { rang, nom } of taxoboxData?.rank_lines || []) {
    if (!(rang in taxoboxNomByRang)) taxoboxNomByRang[rang] = nom;
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
  // Par défaut, l'auteur déjà retenu par le vote majoritaire backend (`auteur_consolide`, celui
  // wikifié dans le wikitexte via `auteur_resolu`) — pas le texte brut du seul module actif,
  // qui peut perdre le vote (ex. Campylobacter : ITIS classe le taxon mais WRMS+INPN l'emportent
  // sur l'auteur à 2 voix contre 1). Repli sur le texte brut du module actif puis le premier
  // candidat connu si le vote n'a rien retenu. Un choix manuel dans la carte "Auteur" (voir
  // auteurSourceOverride) prime sur tout le reste.
  const auteurAffiche =
    (auteurSourceOverride && auteurCandidats[auteurSourceOverride]) ||
    activeData?.auteur_consolide ||
    auteurCandidats[activeSource] ||
    auteurValeurs[0] ||
    null;
  // Version wikifiée de l'auteur choisi dans la carte "Auteur", pour applyAuteurOverride —
  // uniquement disponible si cette source a déjà été préchargée (voir prefetchOtherClassifications).
  const auteurOverrideResolu =
    auteurSourceOverride && resultsBySource[auteurSourceOverride]?.status === "ok"
      ? resultsBySource[auteurSourceOverride].data.auteur_resolu
      : null;

  // Remplace, dans les lignes propres à la source taxobox affichée, celles dont le rang est
  // contesté par au moins une autre source par un {{Taxobox conflit}} listant chaque nom
  // concurrent et sa source — laisse les autres lignes intactes. N'agit que sur les rangs
  // explicitement cochés "gérer" dans le tableau de comparaison (voir managedRankConflicts) :
  // la majorité des désaccords de rang ne posent pas de vrai problème éditorial, donc rien
  // n'est signalé par défaut.
  function applyRankConflicts(wikitext, rankLines) {
    if (!rankLines) return wikitext;
    let result = wikitext;
    const rangsResolus = new Set();
    for (const { rang, line } of rankLines) {
      if (!managedRankConflicts[rang]) continue;
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

  // En mode fusion, ne substitue le bloc sous-taxons qu'une fois `subtaxaMerge` effectivement
  // reçu : tant qu'il est `null` (appel encore en vol), retomber sur le bloc mono-source évite
  // de faire disparaître la section le temps du calcul (spliceBlock viderait le bloc si on lui
  // passait déjà un altBlock vide).
  const effectiveSubtaxaWikitext =
    subtaxaFusionEnabled && effectiveSubtaxaMerge ? subtaxaMergeWikitext : subtaxaData?.subtaxa_wikitext;

  // Items de référence de la source taxobox active (voir GenerateResponse.reference_items) et
  // recomposition côté client du bloc "Liens externes" à partir des seules références cochées
  // (défaut item.default_checked, prime par referenceCheckedOverrides) — même tri alphabétique
  // que l'ancien bloc `references_wikitext` déjà joint côté serveur, puisque reference_items est
  // déjà trié par le backend. `reference_items` exclut volontairement le bloc `{{Autres
  // projets}}` (Commons/Wikispecies/Wiktionnaire, voir GenerateResponse.references_wikitext) —
  // ce n'est pas une référence taxonomique au sens strict, mais l'onglet "Références
  // taxonomiques" est bien celui qui alimente toute la section "Liens externes" de l'article
  // (voir RENDER_BOX_TITLES.references), donc on le retrouve ici dans le wikitexte complet de
  // la même source plutôt que dupliquer sa logique de génération (voir render_voir_aussi,
  // organon/core/rendering/sections.py) côté frontend.
  const referenceItems = taxoboxData?.reference_items || [];
  const checkedReferenceLines = referenceItems.filter(
    (item) => referenceCheckedOverrides[referenceItemKey(item)] ?? item.default_checked
  );
  const autresProjetsMatch = baseData?.wikitext?.match(/\{\{Autres projets\n(?:\|[^\n]*\n)*\}\}\n/);
  const autresProjetsBlock = autresProjetsMatch ? autresProjetsMatch[0] : "";
  const checkedReferencesLinesText = checkedReferenceLines.map((item) => `* ${item.wikitext}`).join("\n");
  const checkedReferencesWikitext =
    autresProjetsBlock || checkedReferencesLinesText
      ? `== Liens externes ==\n${autresProjetsBlock}${checkedReferencesLinesText ? checkedReferencesLinesText + "\n" : ""}`
      : "";
  // Bloc "Liens externes" tel qu'il apparaît dans le wikitexte complet d'origine (avant filtrage
  // par case à cocher) — repère pour le substituer par sa version filtrée lors de la composition
  // de "tout" (voir spliceBlock ci-dessous), sur le même principe que
  // taxobox_wikitext/subtaxa_wikitext.
  const originalLiensExternesMatch = baseData?.wikitext?.match(/== Liens externes ==\n[\s\S]*?(?=\n== |$)/);
  const originalLiensExternesBlock = originalLiensExternesMatch ? originalLiensExternesMatch[0] : "";

  // Composition de "tout" à partir des trois zones structurées : une édition validée ("Terminé")
  // sur la zone Taxobox/Sous-rangs/Références (voir manualOverrides) prime sur la valeur
  // fraîchement recalculée, pour que modifier une zone se répercute dans l'article complet.
  // Seule "tout" reste un texte de repli terminal, jamais décomposé en retour vers les autres
  // zones : un texte libre ne peut pas être reparsé de façon fiable en blocs structurés, alors
  // que l'inverse (structuré -> texte) est un simple remplacement de bloc.
  const effectiveTaxoboxWikitext =
    manualOverrides.taxobox ??
    applyAuteurOverride(taxoboxData?.taxobox_wikitext || "", taxoboxData?.auteur_resolu, auteurOverrideResolu);
  const effectiveSubtaxaWikitextForTout = manualOverrides.subrangs ?? effectiveSubtaxaWikitext;
  const effectiveReferencesWikitextForTout = manualOverrides.references ?? checkedReferencesWikitext;

  const displayWikitext = baseData
    ? applyRankConflicts(
        spliceBlock(
          spliceSubtaxaBlock(
            spliceBlock(baseData.wikitext, baseData.taxobox_wikitext, effectiveTaxoboxWikitext),
            baseData.subtaxa_wikitext,
            effectiveSubtaxaWikitextForTout
          ),
          originalLiensExternesBlock,
          effectiveReferencesWikitextForTout
        ),
        taxoboxData?.rank_lines
      )
    : activeData?.wikitext ?? null;
  // Choix d'image appliqué en dernier, par-dessus le composé base+taxobox+conflits : c'est une
  // simple substitution de commentaire indépendante de la classification affichée, pas un
  // élément du "zoom" classification lui-même.
  const finalWikitext = applyImageSelection(manualOverrides.tout ?? displayWikitext, selectedCommonsImage);

  // Texte "propre" (non édité, ni persisté par une précédente édition — voir manualOverrides) de
  // chaque zone du bloc wikitexte (voir wikitextSubTab) : "taxobox", "subrangs" et "references"
  // isolent un seul bloc du serveur, indépendamment de la composition finalWikitext qui ne
  // concerne que "tout" — voir trimBlockForDisplay pour les retours à la ligne de tête/fin
  // retirés de ces aperçus isolés (sans objet hors composition dans "tout").
  const sourceTextBySubTab = {
    tout: finalWikitext,
    taxobox:
      manualOverrides.taxobox ??
      trimBlockForDisplay(
        applyAuteurOverride(
          applyRankConflicts(taxoboxData?.taxobox_wikitext || "", taxoboxData?.rank_lines),
          taxoboxData?.auteur_resolu,
          auteurOverrideResolu
        )
      ),
    subrangs: manualOverrides.subrangs ?? trimBlockForDisplay(effectiveSubtaxaWikitext || ""),
    references: manualOverrides.references ?? trimBlockForDisplay(checkedReferencesWikitext),
  };
  // Texte effectivement affiché pour la zone actuellement montrée : le brouillon en cours si
  // elle est en édition, sinon le texte propre recalculé ci-dessus.
  const wikitextSubTabText =
    editingSubTab === wikitextSubTab ? editedTexts[wikitextSubTab] ?? "" : sourceTextBySubTab[wikitextSubTab];

  function startEditingSubTab(id) {
    if (!sourceTextBySubTab[id]) return;
    setEditedTexts((prev) => ({ ...prev, [id]: sourceTextBySubTab[id] }));
    setEditingSubTab(id);
  }

  function handleSelectCommonsImage(fileName) {
    setSelectedCommonsImage(fileName);
    if (editingSubTab === "tout") {
      // En édition de "tout", le texte affiché vient de editedTexts.tout (indépendant du
      // composé recalculé) : sans ça, choisir une image pendant une édition en cours resterait
      // invisible jusqu'à "Terminé".
      setEditedTexts((prev) => ({ ...prev, tout: applyImageSelection(prev.tout, fileName) }));
    }
  }

  // Symétrique de handleSelectCommonsImage : revient à l'état "pas d'image" (IMAGE_PLACEHOLDER).
  // Hors édition, rien à faire sur le texte lui-même : displayWikitext est recomposé à chaque
  // rendu depuis le wikitexte d'origine (jamais muté), donc il contient toujours le placeholder
  // tant que selectedCommonsImage est vide. En édition de "tout" en revanche, editedTexts.tout a
  // déjà reçu la substitution en dur (voir handleSelectCommonsImage ci-dessus) : il faut
  // l'inverser explicitement pour que le placeholder réapparaisse dans le textarea.
  function handleDeselectCommonsImage() {
    if (editingSubTab === "tout" && selectedCommonsImage) {
      setEditedTexts((prev) => ({ ...prev, tout: prev.tout.split(selectedCommonsImage).join(IMAGE_PLACEHOLDER) }));
    }
    setSelectedCommonsImage(null);
  }

  // "Terminé" persiste l'édition de la zone dans manualOverrides, quelle que soit la zone : sans
  // ça, le texte affiché retomberait aussitôt sur la valeur recalculée et l'édition semblerait
  // n'avoir eu aucun effet.
  function stopEditingSubTab() {
    setManualOverrides((prev) => ({ ...prev, [editingSubTab]: editedTexts[editingSubTab] }));
    setEditingSubTab(null);
  }

  function toggleControlBoxCollapsed(id) {
    setCollapsedControlBoxes((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  async function handleCopy(text) {
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

            <div className="result-shell">
              <nav className="result-nav" role="tablist" aria-label="Vue du résultat">
                {RESULT_VIEWS.map(({ id, label }) => (
                  <button
                    key={id}
                    type="button"
                    id={`nav-tab-${id}`}
                    role="tab"
                    aria-selected={resultView === id}
                    className={"tab" + (resultView === id ? " on" : "")}
                    onClick={() => setResultView(id)}
                  >
                    {label}
                    {id === "wikitexte" && !submitError && hasPendingClassification && (
                      <ModuleStatusIcon status="running" />
                    )}
                  </button>
                ))}
              </nav>

              <div
                className="result-panel-wrap"
                role="tabpanel"
                aria-labelledby={`nav-tab-${resultView}`}
              >
                {resultView === "wikitexte" && (
                  <div className="wikitexte-tab">
                    {!activeEntry && activeSource && (
                      <div className="render-box">
                        <div className="panel-loading">
                          <p>En attente du préchargement de {activeSource.toUpperCase()}…</p>
                        </div>
                      </div>
                    )}

                    {activeEntry?.status === "loading" && (
                      <div className="render-box">
                        <div className="panel-loading">
                          <p>Interrogation de {activeSource?.toUpperCase()}…</p>
                        </div>
                      </div>
                    )}

                    {activeEntry?.status === "error" && (
                      <div className="render-box">
                        <div className="panel-empty">Aucune donnée disponible via {activeSource?.toUpperCase()} pour ce taxon.</div>
                      </div>
                    )}

                    {activeData && (
                      <>
                        <div className="tabs subtabs" role="tablist" aria-label="Bloc de wikitexte à afficher">
                          {WIKITEXT_SUBTABS.map(({ id, label }) => (
                            <button
                              key={id}
                              type="button"
                              role="tab"
                              aria-selected={wikitextSubTab === id}
                              className={"tab" + (wikitextSubTab === id ? " on" : "")}
                              onClick={() => setWikitextSubTab(id)}
                            >
                              {label}
                            </button>
                          ))}
                        </div>

                        {wikitextSubTab === "taxobox" && availableSources.length > 0 && (
                          <div className="render-box">
                            <div className="render-box-header">
                              <h4 className="render-box-title">
                                Choisir la classification <br/><small>« Cocher » ajoute {"{{Taxobox conflit}}"} pour les rangs en désaccord</small>
                              </h4>
                              <span className="render-box-actions">
                                <button type="button" className="footer-link" onClick={() => toggleControlBoxCollapsed("taxobox")}>
                                  {collapsedControlBoxes.taxobox ? "Déplier" : "Replier"}
                                </button>
                              </span>
                            </div>
                            {!collapsedControlBoxes.taxobox && (
                            <div className="data-table-wrap classification-compare-wrap">
                              <table className="data-table classification-compare-table classification-compare-table--managed">
                                <thead>
                                  <tr>
                                    <th></th>
                                    {availableSources.map((m) => (
                                      <th key={m.id}>
                                        <button
                                          type="button"
                                          className={"id-badge id-badge-btn" + (taxoboxSourceId === m.id ? " on" : "")}
                                          onClick={() => handleTaxoboxSourceChange(m.id)}
                                          title={m.id === recommendedTaxoboxSource ? "Recommandé" : "Choisir cette source pour la Taxobox"}
                                        >
                                          {m.id.toUpperCase()}
                                          {m.id === recommendedTaxoboxSource ? " ★" : ""}
                                        </button>
                                      </th>
                                    ))}
                                    <th></th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {classificationTableRows.order.map((rang) => {
                                    const conflict = rankDisagreements[rang]?.size > 1;
                                    const valueFor = (m) => {
                                      const noms = classificationTableRows.perModule[m.id]?.[rang] || [];
                                      return noms.length > 0 ? noms.join(", ") : "—";
                                    };
                                    const chosenValue = taxoboxNomByRang[rang] || "—";
                                    const groups = mergeAdjacentEqual(availableSources, valueFor);
                                    const abbr = RANK_ABBR[rang];
                                    return (
                                      <tr key={rang}>
                                        <th>{abbr ? <abbr title={rang}>{abbr}</abbr> : rang}</th>
                                        {groups.map((g, gi) => {
                                          const isChosen = g.sources.some((m) => m.id === taxoboxSourceId);
                                          const isDiff = conflict && !isChosen && g.value !== "—" && g.value !== chosenValue;
                                          return (
                                            <td
                                              key={gi}
                                              colSpan={g.sources.length}
                                              className={isDiff ? "conflict-cell" : isChosen ? "chosen-col" : undefined}
                                            >
                                              {g.value}
                                            </td>
                                          );
                                        })}
                                        <td>
                                          {conflict && (
                                            <input
                                              type="checkbox"
                                              checked={!!managedRankConflicts[rang]}
                                              onChange={() => toggleRankConflictManaged(rang)}
                                              aria-label={`Gérer le désaccord sur le rang ${rang} dans le rendu`}
                                              title="Gérer ce désaccord dans le rendu"
                                            />
                                          )}
                                        </td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </div>
                            )}
                          </div>
                        )}

                        {wikitextSubTab === "image" && (
                          <div className="render-box">
                            <ImageGallery
                              taxon={commonsTaxon}
                              selectedFileName={selectedCommonsImage}
                              onSelect={handleSelectCommonsImage}
                              onDeselect={handleDeselectCommonsImage}
                              cache={commonsImagesCache}
                            />
                          </div>
                        )}

                        {wikitextSubTab === "references" && (
                          <div className="render-box">
                            <div className="render-box-header">
                              <h4 className="render-box-title">
                                Références disponibles — décocher celles hors-sujet
                              </h4>
                              <span className="render-box-actions">
                                <button type="button" className="footer-link" onClick={() => toggleControlBoxCollapsed("references")}>
                                  {collapsedControlBoxes.references ? "Déplier" : "Replier"}
                                </button>
                              </span>
                            </div>
                            {!collapsedControlBoxes.references && (
                            <div className="reference-checklist">
                              <div className="reference-checklist-row reference-checklist-row-locked">
                                <span className="reference-checklist-lock" aria-hidden="true">🔒</span>
                                <span className="id-badge">Autres projets</span>
                                <span className="reference-checklist-note">
                                  toujours inclus — fait partie des liens externes, pas des références taxonomiques
                                </span>
                              </div>
                              {referenceItems.map((item) => {
                                const key = referenceItemKey(item);
                                const checked = referenceCheckedOverrides[key] ?? item.default_checked;
                                return (
                                  <label key={key} className="reference-checklist-row">
                                    <input
                                      type="checkbox"
                                      checked={checked}
                                      onChange={() => toggleReferenceItem(key, checked)}
                                      aria-label={`Inclure la référence ${item.module_id} dans les liens externes`}
                                    />
                                    <span className="id-badge">{item.module_id.toUpperCase()}</span>
                                    {!item.default_checked && (
                                      <span className="id-badge id-badge-conflict">hors domaine</span>
                                    )}
                                    <code>{item.wikitext}</code>
                                  </label>
                                );
                              })}
                            </div>
                            )}
                          </div>
                        )}

                        {wikitextSubTab === "subrangs" && subtaxaMergeSources.length > 1 && (
                          <div className="render-box">
                            <div className="render-box-header">
                              <h4 className="render-box-title">Sous-taxons</h4>
                              <span className="render-box-actions">
                                <button type="button" className="footer-link" onClick={() => toggleControlBoxCollapsed("subrangs")}>
                                  {collapsedControlBoxes.subrangs ? "Déplier" : "Replier"}
                                </button>
                              </span>
                            </div>
                            {subtaxaFusionEnabled && !collapsedControlBoxes.subrangs && (
                              <div className="data-table-wrap subtaxa-merge-groups">
                                {!effectiveSubtaxaMerge && <p>Calcul de la fusion en cours…</p>}
                                {effectiveSubtaxaMerge?.groups.length === 0 && <p>Aucun sous-taxon à fusionner.</p>}
                                {effectiveSubtaxaMerge?.groups.map((group, gi) => (
                                  <div key={gi} className="subtaxa-merge-group">
                                    <p className="subtaxa-merge-group-head">
                                      {group.sources.map((s) => (
                                        <span key={s} className="id-badge">
                                          {s.toUpperCase()}
                                        </span>
                                      ))}
                                      {group.kind === "disjoint" && (
                                        <span className="id-badge id-badge-conflict">non recoupé</span>
                                      )}
                                    </p>
                                    <ul className="subtaxa-merge-species-list">
                                      {group.species.map((sp) => (
                                        <li key={sp.nom}>
                                          <label className="facet-checkbox">
                                            <input
                                              type="checkbox"
                                              checked={subtaxaChecked[sp.nom] ?? sp.default_checked}
                                              onChange={() => toggleSubtaxaChecked(sp.nom)}
                                            />
                                            {sp.nom}
                                          </label>
                                        </li>
                                      ))}
                                    </ul>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        {wikitextSubTab !== "image" && (
                        <div className="render-box">
                          <div className="render-box-header">
                            <h4 className="render-box-title" id="wikitext-label">
                              {wikitextSubTab === "tout" ? "Wikitexte" : RENDER_BOX_TITLES[wikitextSubTab]}
                            </h4>
                            <span className="render-box-actions">
                              <button
                                type="button"
                                className="edit-btn"
                                aria-pressed={editingSubTab === wikitextSubTab}
                                onClick={
                                  editingSubTab === wikitextSubTab
                                    ? stopEditingSubTab
                                    : () => startEditingSubTab(wikitextSubTab)
                                }
                              >
                                {editingSubTab === wikitextSubTab ? "✓ Terminé" : "✎ Éditer"}
                              </button>
                              <button type="button" className="edit-btn" onClick={() => handleCopy(wikitextSubTabText)}>
                                {copied ? "Copié ✓" : "Copier"}
                              </button>
                            </span>
                          </div>
                          <textarea
                            className="wikitext"
                            aria-labelledby="wikitext-label"
                            spellCheck="false"
                            readOnly={editingSubTab !== wikitextSubTab}
                            value={wikitextSubTabText}
                            onChange={
                              editingSubTab === wikitextSubTab
                                ? (e) => setEditedTexts((prev) => ({ ...prev, [wikitextSubTab]: e.target.value }))
                                : undefined
                            }
                          />
                        </div>
                        )}
                      </>
                    )}
                  </div>
                )}

                {resultView === "noms" && (
                  <div className="panel">
                    <div className="panel-head">
                      <span className="t">Noms &amp; synonymes</span>
                    </div>
                    {!activeData ? (
                      <p className="panel-empty">Aucune donnée disponible pour le moment.</p>
                    ) : (
                      <>
                        <div className="noms-card">
                          <div className="noms-card-head">
                            <span className="noms-card-title">Auteur</span>
                            <small className="noms-card-hint">plusieurs choix parfois possibles</small>
                          </div>
                          {activeData.auteur_consolide ? (() => {
                            const auteurValueFor = (m) => {
                              const candidat = activeData.auteur_candidats[m.id];
                              return candidat ? normalizeAuteur(candidat) : "—";
                            };
                            const orderedAuteurSources = groupSourcesByValue(availableSources, auteurValueFor);
                            const recommendedAuteurSource = orderedAuteurSources.find(
                              (m) => auteurValueFor(m) === normalizeAuteur(activeData.auteur_consolide)
                            )?.id;
                            const chosenAuteurSourceId = auteurSourceOverride ?? recommendedAuteurSource ?? null;
                            const groups = mergeAdjacentEqual(orderedAuteurSources, auteurValueFor);
                            return (
                              <div className="data-table-wrap classification-compare-wrap">
                                <table className="data-table classification-compare-table">
                                  <thead>
                                    <tr>
                                      {orderedAuteurSources.map((m) => (
                                        <th key={m.id}>
                                          <button
                                            type="button"
                                            className={"id-badge id-badge-btn" + (chosenAuteurSourceId === m.id ? " on" : "")}
                                            onClick={() => handleAuteurSourceChange(m.id)}
                                            title={m.id === recommendedAuteurSource ? "Recommandé (vote majoritaire)" : "Choisir cette source pour l'auteur"}
                                          >
                                            {m.id.toUpperCase()}
                                            {m.id === recommendedAuteurSource ? " ★" : ""}
                                          </button>
                                        </th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody>
                                    <tr>
                                      {groups.map((g, gi) => {
                                        const isChosen = g.sources.some((m) => m.id === chosenAuteurSourceId);
                                        return (
                                          <td key={gi} colSpan={g.sources.length} className={isChosen ? "chosen-col" : undefined}>
                                            {g.value}
                                          </td>
                                        );
                                      })}
                                    </tr>
                                  </tbody>
                                </table>
                              </div>
                            );
                          })() : (
                            <p className="panel-empty">Aucun auteur rapporté pour ce taxon.</p>
                          )}
                        </div>

                        <div className="noms-card">
                          <div className="noms-card-head">
                            <span className="noms-card-title">Noms vernaculaires</span>
                          </div>
                          {activeData.vernacular_names.length > 0 ? (
                            <p className="noms-card-body">{activeData.vernacular_names.join(", ")}</p>
                          ) : (
                            <p className="panel-empty">Aucun nom vernaculaire rapporté.</p>
                          )}
                        </div>

                        <div className="noms-card">
                          <div className="noms-card-head">
                            <span className="noms-card-title">
                              Synonymes
                              {activeData.synonymes_source ? ` — source : ${activeData.synonymes_source.toUpperCase()}` : ""}
                            </span>
                          </div>
                          {activeData.synonymes.length > 0 ? (
                            <div className="data-table-wrap">
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
                            </div>
                          ) : (
                            <p className="panel-empty">Aucun synonyme rapporté.</p>
                          )}
                        </div>

                        <div className="noms-card">
                          <div className="noms-card-head">
                            <span className="noms-card-title">Basionyme</span>
                          </div>
                          {activeData.basionyme ? (
                            <p className="noms-card-body">
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
                )}

                {resultView === "autres" && (
                  <div className="panel">
                    {activeData ? (
                      <>
                        {activeData.milieu && (
                          <div className="field-box">
                            <span className="field-label">Écozone</span>
                            <p>{activeData.milieu === "marin" ? "Marin" : "Terrestre"}</p>
                          </div>
                        )}
                        {activeData.uicn_statut && (
                          <div className="field-box">
                            <span className="field-label">Statut de conservation UICN</span>
                            <p>
                              <strong>{activeData.uicn_statut}</strong>
                              {UICN_LABELS[activeData.uicn_statut] ? ` — ${UICN_LABELS[activeData.uicn_statut]}` : ""}
                              {" "}(source : GBIF)
                            </p>
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
                )}

                {resultView === "data" && (
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
                        <div className="data-table-wrap">
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>Source</th>
                                <th>Informations</th>
                                <th>Temps d'exécution</th>
                              </tr>
                            </thead>
                            <tbody>
                              {Object.entries(activeEntry.moduleStatuses).map(([moduleId, info]) => {
                                const link = activeData?.external_links.find((l) => l.module_id === moduleId);
                                const href = link ? extractHref(link.html) : null;
                                // Types d'information effectivement rapportés par ce module pour
                                // ce taxon (voir GenerateResponse.data_found côté backend) —
                                // dérivé de la structure déjà présente dans la réponse plutôt
                                // que deviné ici module par module.
                                const found = activeData?.data_found?.[moduleId] || [];
                                return (
                                  <tr key={moduleId}>
                                    <td>
                                      <span className="data-table-cell-flex">
                                        <span
                                          className={`status-dot status-dot-${info.status}`}
                                          role="img"
                                          aria-label={MODULE_STATUS_LABELS[info.status] || info.status}
                                          title={MODULE_STATUS_LABELS[info.status] || info.status}
                                        />
                                        {href ? (
                                          <a href={href} target="_blank" rel="noreferrer">
                                            {moduleId.toUpperCase()}
                                          </a>
                                        ) : (
                                          moduleId.toUpperCase()
                                        )}
                                      </span>
                                    </td>
                                    <td>
                                      {info.status === "error" ? (
                                        <span className="data-table-cell-flex">
                                          <span>{info.message ? `Erreur : ${info.message}` : "Erreur réseau"}</span>
                                          <button type="button" className="footer-link" onClick={() => retryModule(moduleId)}>
                                            Réessayer
                                          </button>
                                        </span>
                                      ) : (
                                        found.join(", ")
                                      )}
                                    </td>
                                    <td className="data-table-duration">
                                      {info.durationSeconds != null ? formatDuration(info.durationSeconds) : "—"}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="panel-empty">Aucun suivi disponible pour le moment.</p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
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

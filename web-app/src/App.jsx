import { useEffect, useState } from "react";
import { fetchAuthStatus, fetchDomains, fetchModules, fetchSources, logout } from "@/api/client.js";
import AuthorsPage from "@/features/authors/AuthorsPage.jsx";
import ConnectGate from "@/shell/ConnectGate.jsx";
import ResultIdentity from "@/features/result/ResultIdentity.jsx";
import ResultPanel from "@/features/result/ResultPanel.jsx";
import SiteFooter from "@/shell/SiteFooter.jsx";
import SiteHeader from "@/shell/SiteHeader.jsx";
import SourcesPage from "@/features/sources/SourcesPage.jsx";
import { PreferencesBanner } from "@/shell/StoragePreferencesBanner.jsx";
import TaxonSearch from "@/features/search/TaxonSearch.jsx";
import TaxonSheet from "@/features/result/TaxonSheet.jsx";
import { useAuthorChoice } from "@/shared/useAuthorChoice.js";
import { useCommonsImages } from "@/features/wikitext/useCommonsImages.js";
import { useDiagnosis } from "@/features/wikidata/useDiagnosis.js";
import { useFacetSources } from "@/features/result/useFacetSources.js";
import { useGenerationTracking } from "@/features/result/useGenerationTracking.js";
import { useReferenceChecklist } from "@/features/wikitext/useReferenceChecklist.js";
import { useSubtaxaMerge } from "@/features/wikitext/useSubtaxaMerge.js";
import { useWikitextEditor } from "@/features/wikitext/useWikitextEditor.js";
import {
  clearStoredTheme,
  getStorageConsent,
  readStoredTheme,
  setStorageConsent,
  writeStoredTheme,
} from "@/shell/storagePreferences.js";

function getInitialTheme() {
  const saved = readStoredTheme();
  if (saved) return saved;
  if (typeof window !== "undefined" && window.matchMedia) {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return "dark";
}

export default function App() {
  const [theme, setTheme] = useState(getInitialTheme);
  const [domains, setDomains] = useState([]);
  const [modules, setModules] = useState([]);
  const [availableSourceCount, setAvailableSourceCount] = useState(null);
  const [showSources, setShowSources] = useState(false);
  const [showAuthors, setShowAuthors] = useState(false);
  // undefined = status not checked yet (avoids a flash of the "not
  // connected" screen until fetchAuthStatus() answers), null =
  // confirmed not connected, string = connected username.
  const [username, setUsername] = useState(undefined);
  const [storageConsent, setStorageConsentState] = useState(getStorageConsent);
  const [showStorageBanner, setShowStorageBanner] = useState(() => getStorageConsent() === null);

  // { taxon, domain, qid, gbifKey } once a search ran
  const [query, setQuery] = useState(null);
  // taxon -> { query, resultsBySource, activeSource, diagnosis,
  // referenceSource, commonsImagesCache }
  const [kept, setKept] = useState({});
  const diagnosis = useDiagnosis();
  // Global reference source ("" = automatic) and chosen sheet tab (null
  // = auto).
  const [referenceSource, setReferenceSource] = useState("");
  // Active tab of the side-navigation shell of the result.
  // One of: wikitext, names, other, wiktionary, wikidata, wikispecies, data.
  const [resultView, setResultView] = useState("wikitext");
  // "wikitext" tab block: "all" is the composed, editable article;
  // "taxobox" and "subranks" isolate one read-only server block
  // (GenerateResponse.taxobox_wikitext, subtaxa_wikitext); "image"
  // shows the Commons gallery (ImageGallery.jsx), with no wikitext
  // block; "references" recomposes the block from reference_items and
  // the checked boxes (checkedReferencesWikitext). None of the other
  // four goes through the finalWikitext composition.
  // One of: all, taxobox, image, subranks, references.
  const [wikitextSubTab, setWikitextSubTab] = useState("all");
  // "Controls" areas (Taxobox rank choice, reference checklist,
  // sub-rank merge toggle) collapsed by the user once the choice is
  // made, to keep only the header.
  const [collapsedBoxes, setCollapsedBoxes] = useState({});

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    // storageConsent is a dependency: the current theme is written as
    // soon as consent is given.
    writeStoredTheme(theme);
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
    clearStoredTheme();
  }

  useEffect(() => {
    fetchDomains()
      .then((data) => setDomains(data))
      .catch(() => setDomains([]));
    fetchModules()
      .then((data) => setModules(data))
      .catch(() => setModules([]));
    // Same count as the total on SourcesPage.jsx: the db_inventory.yaml
    // entries with status "disponible", not modules.length; some
    // available sources (bhl, crossref) are not registered
    // TaxonomyModules, being called internally by other modules.
    fetchSources()
      .then((data) => {
        const n = data.categories.reduce((acc, c) => acc + c.sources.filter((s) => s.status === "disponible").length, 0);
        setAvailableSourceCount(n);
      })
      .catch(() => setAvailableSourceCount(null));
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
  const tracking = useGenerationTracking(classificationModules);
  const { resultsBySource, activeSource, activeData, submitError, initialLoading } = tracking;
  const commonsTaxon = activeData?.resolved_taxon || query?.taxon || null;
  const commonsImages = useCommonsImages(commonsTaxon);
  const facets = useFacetSources(classificationModules, resultsBySource, activeSource);
  const subtaxa = useSubtaxaMerge(facets.availableSources, resultsBySource, facets.baseData);
  const author = useAuthorChoice(classificationModules, resultsBySource, activeSource, activeData);
  const references = useReferenceChecklist(facets.taxoboxData, facets.baseData);
  const wikitext = useWikitextEditor({ activeData, facets, subtaxa, references, author, activeSubTab: wikitextSubTab });

  // Reset everything that depends on the displayed taxon (choices,
  // edits, facet caches). The author source choice survives a new
  // search.
  function resetTaxonState() {
    wikitext.reset();
    commonsImages.reset();
    facets.reset();
    subtaxa.reset();
    references.reset();
  }

  // Kept results: in-memory snapshot of the taxon left (finished
  // sources only), reopened with no new call. Lost on page reload.
  function rememberCurrent() {
    if (!query || !activeSource) return;
    const done = Object.fromEntries(Object.entries(resultsBySource).filter(([, e]) => e.status === "ok"));
    if (Object.keys(done).length === 0) return;
    setKept((prev) => ({
      ...prev,
      [query.taxon]: {
        query,
        resultsBySource: done,
        activeSource,
        diagnosis: diagnosis.snapshot(),
        referenceSource,
        commonsImagesCache: commonsImages.okEntries(),
      },
    }));
  }

  function openKept(name) {
    const snapshot = kept[name];
    if (!snapshot) return;
    rememberCurrent();
    resetTaxonState();
    setQuery(snapshot.query);
    tracking.restore(snapshot);
    commonsImages.restore(snapshot.commonsImagesCache);
    setReferenceSource(snapshot.referenceSource);
    if (snapshot.diagnosis) diagnosis.restore(snapshot.diagnosis);
    else diagnosis.run(snapshot.query.qid ?? snapshot.query.taxon, snapshot.referenceSource, snapshot.query);
  }

  async function launchSearch(taxonName, domainValue, classification, gbifKey, qid) {
    rememberCurrent();
    setKept((prev) => {
      const next = { ...prev };
      delete next[taxonName];
      return next;
    });
    resetTaxonState();
    setQuery({ taxon: taxonName, domain: domainValue, qid, gbifKey });
    diagnosis.run(qid ?? taxonName, referenceSource, { domain: domainValue, gbifKey });
    await tracking.startSearch(taxonName, domainValue, classification ?? (referenceSource || undefined), gbifKey);
  }

  function handleLaunch({ name, domain, gbifKey, qid }) {
    launchSearch(name, domain, undefined, gbifKey, qid);
  }

  // Changing the facet invalidates any edit, whatever the area.
  function handleTaxoboxSourceChange(moduleId) {
    facets.chooseTaxoboxSource(moduleId);
    wikitext.discardEdits();
  }

  function toggleBoxCollapsed(id) {
    setCollapsedBoxes((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  // A single reference source for the whole sheet: it drives the
  // diagnosis (Review, Complete) and, if already loaded, the Taxobox
  // facet of Create.
  function handleReferenceSourceChange(moduleId) {
    setReferenceSource(moduleId);
    if (!query) return;
    diagnosis.run(diagnosis.target, moduleId, query);
    handleTaxoboxSourceChange(moduleId && resultsBySource[moduleId]?.status === "ok" ? moduleId : null);
  }

  // The secondary pages are mutually exclusive: opening one closes the others.
  function openPage(page) {
    setShowSources(page === "sources");
    setShowAuthors(page === "authors");
  }

  function handleGoToNamesTab() {
    setResultView("names");
  }

  function handleGoToOtherInfoTab() {
    setResultView("other");
  }

  return (
    <div className="app">
      <div className="scan" />
      <SiteHeader
        username={username}
        onLogout={handleLogout}
        availableSourceCount={availableSourceCount}
        onShowSources={() => openPage("sources")}
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
        storageConsent={storageConsent}
        onShowPreferences={() => setShowStorageBanner(true)}
      />

      {showStorageBanner && <PreferencesBanner onAccept={handleAcceptStorage} onRefuse={handleRefuseStorage} />}

      <div className="page-scroll">
      <main className="wrap">
        {showSources ? (
          <SourcesPage modules={modules} onBack={() => setShowSources(false)} />
        ) : showAuthors ? (
          <AuthorsPage
            onBack={() => setShowAuthors(false)}
            onShowSources={() => openPage("sources")}
          />
        ) : username === undefined ? null : username === null ? (
          <>
            <span className="eyebrow">Organon</span>
            <h1>
              Interrogez AlgaeBase, ITIS… — <em>en une requête</em>
            </h1>
            <ConnectGate />
          </>
        ) : (
          <>
            <TaxonSearch
              compact={!!query}
              domains={domains}
              busy={initialLoading}
              error={submitError}
              kept={Object.keys(kept).filter((name) => name !== query?.taxon)}
              onLaunch={handleLaunch}
              onOpenKept={openKept}
              referenceSource={referenceSource}
              referenceLabel={diagnosis.result?.source_reference}
              onReferenceSourceChange={handleReferenceSourceChange}
              classificationModules={classificationModules}
            />

            {query && (
              <TaxonSheet
                key={query.taxon}
                diagnosis={diagnosis}
                onPickCandidate={(qid) => diagnosis.run(qid, referenceSource, query)}
                identity={
                  <ResultIdentity
                    query={query}
                    activeData={activeData}
                    author={author}
                    onGoToNames={handleGoToNamesTab}
                    onGoToOtherInfo={handleGoToOtherInfoTab}
                  />
                }
                draft={
                  <ResultPanel
                    view={resultView}
                    onChangeView={setResultView}
                    wikitextSubTab={wikitextSubTab}
                    onChangeWikitextSubTab={setWikitextSubTab}
                    tracking={tracking}
                    facets={facets}
                    subtaxa={subtaxa}
                    references={references}
                    author={author}
                    wikitext={wikitext}
                    commonsImages={commonsImages}
                    commonsTaxon={commonsTaxon}
                    collapsedBoxes={collapsedBoxes}
                    onToggleBox={toggleBoxCollapsed}
                    onChooseTaxoboxSource={handleTaxoboxSourceChange}
                    diagnosis={diagnosis}
                    query={query}
                  />
                }
              />
            )}
          </>
        )}
      </main>
      </div>

      <SiteFooter onShowSources={() => openPage("sources")} onShowAuthors={() => openPage("authors")} />
    </div>
  );
}

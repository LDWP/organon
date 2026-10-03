import { useRef, useState } from "react";
import { generateTaxonStream } from "@/api/client.js";

// Generation tracking: one entry per classification source
// (`resultsBySource`), the displayed source (`activeSource`) and the
// background prefetch of the other sources.
export function useGenerationTracking(classificationModules) {
  const [initialLoading, setInitialLoading] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [activeSource, setActiveSource] = useState(null);
  // { [module_id]: { status: "loading"|"ok"|"error", data?, error?,
  // moduleStatuses } }. Each classification source has its own progress
  // tracking (`moduleStatuses`), so the background prefetch of other
  // sources (see prefetchOtherClassifications) never overwrites the
  // tracking of an already finished source.
  const [resultsBySource, setResultsBySource] = useState({});
  // Incremented at each search: lets the background prefetch (a long
  // async loop) detect that a more recent search started and stop,
  // rather than keep filling the cache of an obsolete search.
  const searchGeneration = useRef(0);

  // Consume the events of POST /api/v1/generate/stream (see
  // organon/api/routes/generate.py) to fill the per-module tracking *of
  // source `moduleId`* (see resultsBySource[moduleId].moduleStatuses).
  // Needed since several classification sources can run at once
  // (background prefetch): a shared tracking would mix their progress.
  // "plan" prefills every row as "pending" once the enrichment module
  // list is known, so the user sees the amount of remaining work at
  // once rather than rows appearing one by one without context.
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

  // Fetch (or refetch) a classification source and cache it in
  // `resultsBySource`, without touching `submitError` or
  // `activeSource`. Used for the initial search and for the silent
  // background prefetch of the other sources (see
  // prefetchOtherClassifications). Return `{ data }` or `{ error }`
  // rather than throw, so the caller decides what to do with a failure
  // (one shows `submitError`, the other ignores it and moves on).
  //
  // `generation`: a late answer of a search replaced meanwhile (other
  // taxon, reopened kept result) must write nothing into the current
  // search cache.
  async function fetchSource(taxonName, domainValue, moduleId, gbifKey, generation = searchGeneration.current) {
    const isCurrent = () => searchGeneration.current === generation;
    if (isCurrent()) {
      setResultsBySource((prev) => ({ ...prev, [moduleId]: { status: "loading", moduleStatuses: {} } }));
    }
    try {
      const data = await generateTaxonStream(
        { taxon: taxonName, domain: domainValue, classification: moduleId, gbif_key: gbifKey },
        { onEvent: (event) => isCurrent() && handleGenerationEvent(moduleId, event) }
      );
      if (!isCurrent()) return { data };
      // `data.used_classification` may differ from `moduleId`: an
      // explicit choice that fails on the network can now end on
      // another module as a fallback (see
      // _classification_network_fallback,
      // organon/api/routes/generate.py). Without also updating the
      // `moduleId` key (the one set to "loading" above), it would stay
      // "loading" forever, which made the loading chip spin endlessly.
      // The per-module tracking (moduleStatuses) accumulated during the
      // stream stays under `moduleId` (handleGenerationEvent uses it
      // from the closure above): without also copying it under
      // `data.used_classification`, the Data tab of the winning source
      // would stay empty despite a tracking really available.
      setResultsBySource((prev) => ({
        ...prev,
        [moduleId]: { ...prev[moduleId], status: "ok", data },
        [data.used_classification]: {
          ...prev[data.used_classification],
          status: "ok",
          data,
          moduleStatuses: prev[moduleId]?.moduleStatuses,
        },
      }));
      return { data };
    } catch (err) {
      const message = err.message || "Erreur inconnue lors de la génération.";
      if (isCurrent()) {
        setResultsBySource((prev) => ({ ...prev, [moduleId]: { ...prev[moduleId], status: "error", error: message } }));
      }
      return { error: message };
    }
  }

  // Prefetch in the background, all in parallel, the classification
  // sources other than the displayed one, so switching source in the
  // facet selectors never triggers a visible request again. Up to ~8
  // third-party taxonomic APIs are hit at once per search: accepted for
  // perceived responsiveness over a sequential prefetch that spared
  // those APIs but delayed the lowest-priority sources.
  async function prefetchOtherClassifications(taxonName, domainValue, excludeId, generation) {
    await Promise.all(
      classificationModules
        .filter((m) => m.id !== excludeId)
        // A module whose explicit domain list does not cover the domain
        // value can never succeed for this taxon (see
        // organon/core/domains.py): querying it anyway wasted a good
        // part of the shared /generate* quota.
        .filter((m) => m.domains === "all" || (Array.isArray(m.domains) && m.domains.includes(domainValue)))
        .map((m) => {
          if (searchGeneration.current !== generation) return null;  // a more recent search meanwhile
          return fetchSource(taxonName, domainValue, m.id, undefined, generation);
        })
    );
  }

  // Start the generation of a taxon: drop any previous tracking, load
  // the requested source, then prefetch the others in the background.
  // Return `false` if a more recent search replaced it meanwhile.
  async function startSearch(taxonName, domainValue, moduleId, gbifKey) {
    const generation = ++searchGeneration.current;
    setResultsBySource({});
    setActiveSource(null);
    setSubmitError(null);
    setInitialLoading(true);
    const { data, error } = await fetchSource(taxonName, domainValue, moduleId, gbifKey, generation);
    if (searchGeneration.current !== generation) return;
    setInitialLoading(false);
    if (data) {
      setActiveSource(data.used_classification);
      prefetchOtherClassifications(taxonName, domainValue, data.used_classification, generation);
    } else {
      setSubmitError(error);
    }
  }

  // Restore a kept tracking (see App.openKept) with no new network
  // call.
  function restore(snapshot) {
    searchGeneration.current += 1;
    setInitialLoading(false);
    setSubmitError(null);
    setResultsBySource(snapshot.resultsBySource);
    setActiveSource(snapshot.activeSource);
  }

  // Manual retry of a failing module from the Data tab. A
  // classification error has collected nothing for this source yet:
  // restart a full regeneration (same path as the initial search). A
  // failing enrichment module has no entry point of its own
  // backend-side, but `GenerateOptions.off` can disable all the other
  // already resolved modules so only this one really hits the network
  // (the classification is rerun anyway: the backend keeps no state
  // between requests). Only its per-module namespaced data (data_found,
  // distribution, author_candidates, external_links) is then merged
  // into the displayed result; the rest (composed wikitext, vernacular
  // names...) would stay truncated if taken from this partial answer,
  // since the other modules did not run.
  function retryModule(query, moduleId) {
    if (!query || !activeSource) return;
    const statuses = resultsBySource[activeSource]?.moduleStatuses || {};
    if (statuses[moduleId]?.role !== "enrichment") {
      // A failing classification candidate (e.g. GBIF) is not
      // necessarily `activeSource`: with the parallel fallback between
      // classifications (see _classification_candidates,
      // organon/api/routes/generate.py), several candidates may appear
      // here, only one having won. Rerunning `activeSource` instead of
      // the clicked module regenerated the already successful source
      // instead of retrying the one that really failed.
      fetchSource(query.taxon, query.domain, moduleId);
      return;
    }
    const off = Object.entries(statuses)
      .filter(([id, info]) => info.role === "enrichment" && id !== moduleId)
      .map(([id]) => id);

    generateTaxonStream(
      { taxon: query.taxon, domain: query.domain, classification: activeSource, off },
      {
        onEvent: (event) => {
          if (event.type === "module_status" && event.module_id === moduleId) {
            handleGenerationEvent(activeSource, event);
          }
        },
      }
    )
      .then((data) => {
        // `classification: activeSource` is explicit, but may now end
        // on another module as a network fallback (see
        // _classification_network_fallback,
        // organon/api/routes/generate.py) if activeSource itself fails
        // on this retry. Merging anyway would attribute the enrichment
        // data of another classification to activeSource: abandon the
        // targeted merge in that case rather than corrupt the cache
        // (fetchSource, called separately for the real winner, takes
        // over normally).
        if (data.used_classification !== activeSource) return;
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
                author_candidates: moduleId in data.author_candidates
                  ? { ...prevData.author_candidates, [moduleId]: data.author_candidates[moduleId] }
                  : prevData.author_candidates,
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

  // Serves the loading chip on the "Results" tab: a module not
  // applicable to the taxon domain (e.g. AlgaeBase for a bacterium) is
  // never queried and will never have an entry in resultsBySource;
  // looking only at existing "loading" entries reflects the real state,
  // whatever subset of modules is actually queried.
  const hasPending = Object.values(resultsBySource).some((entry) => entry.status === "loading");

  const activeEntry = activeSource ? resultsBySource[activeSource] : null;
  const activeData = activeEntry?.status === "ok" ? activeEntry.data : null;

  return {
    resultsBySource,
    activeSource,
    activeEntry,
    activeData,
    submitError,
    initialLoading,
    hasPending,
    startSearch,
    restore,
    retryModule,
  };
}

import DataTab from "./DataTab.jsx";
import { ModuleStatusIcon } from "./ModuleStatus.jsx";
import NamesTab from "./NamesTab.jsx";
import OtherInfoTab from "./OtherInfoTab.jsx";
import WikidataPanel from "@/features/wikidata/WikidataPanel.jsx";
import WikitextTab from "@/features/wikitext/WikitextTab.jsx";

// Tabs of the side-navigation shell of the result, in display order.
const RESULT_VIEWS = [
  { id: "wikitext", label: "Wikipédia" },
  { id: "wiktionary", label: "Wiktionnaire" },
  { id: "wikidata", label: "Wikidata" },
  { id: "wikispecies", label: "Wikispecies" },
  { id: "data", label: "Données" },
];

// Projects with no generation module yet: the tab exists, its content
// is to come.
const UNSUPPORTED_PROJECT_VIEWS = ["wiktionary", "wikispecies"];

// Result views shown under the "Wikipédia" side tab, after the wikitext
// sub-tabs in the same horizontal bar.
const WIKIPEDIA_GROUP_VIEWS = ["wikitext", "names", "other"];
const WIKITEXT_SUBTABS = [
  { id: "all", label: "Tout" },
  { id: "taxobox", label: "Taxobox" },
  { id: "image", label: "Image" },
  { id: "subranks", label: "Sous-rangs" },
  { id: "references", label: "Liens externes" },
];
const EXTRA_SUBTABS = [
  { id: "names", label: "Noms & synonymes" },
  { id: "other", label: "Autres" },
];

export default function ResultPanel({
  view,
  onChangeView,
  wikitextSubTab,
  onChangeWikitextSubTab,
  tracking,
  facets,
  subtaxa,
  references,
  author,
  wikitext,
  commonsImages,
  commonsTaxon,
  collapsedBoxes,
  onToggleBox,
  onChooseTaxoboxSource,
  diagnosis,
  query,
}) {
  const { activeSource, activeEntry, activeData } = tracking;
  const inWikipediaGroup = WIKIPEDIA_GROUP_VIEWS.includes(view);
  return (
    <div className="result-shell">
      <nav className="result-nav" role="tablist" aria-label="Vue du résultat">
        {RESULT_VIEWS.map(({ id, label }) => {
          const on = id === "wikitext" ? inWikipediaGroup : view === id;
          return (
            <button
              key={id}
              type="button"
              id={`nav-tab-${id}`}
              role="tab"
              aria-selected={on}
              className={"tab" + (on ? " on" : "")}
              onClick={() => onChangeView(id)}
            >
              {label}
              {(id === "wikitext" || id === "data") && !tracking.submitError && tracking.hasPending && <ModuleStatusIcon status="running" />}
            </button>
          );
        })}
      </nav>

      <div className="result-panel-wrap" role="tabpanel" aria-labelledby={`nav-tab-${view}`}>
        {activeData && inWikipediaGroup && (
          <div className="tabs subtabs" role="tablist" aria-label="Section du résultat à afficher">
            {WIKITEXT_SUBTABS.map(({ id, label }) => {
              const on = view === "wikitext" && wikitextSubTab === id;
              return (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={on}
                  className={"tab" + (on ? " on" : "")}
                  onClick={() => {
                    onChangeView("wikitext");
                    onChangeWikitextSubTab(id);
                  }}
                >
                  {label}
                </button>
              );
            })}
            {EXTRA_SUBTABS.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={view === id}
                className={"tab" + (view === id ? " on" : "")}
                onClick={() => onChangeView(id)}
              >
                {label}
              </button>
            ))}
          </div>
        )}

        {view === "wikitext" && (
          <WikitextTab
            activeSource={activeSource}
            activeEntry={activeEntry}
            activeData={activeData}
            activeSubTab={wikitextSubTab}
            facets={facets}
            subtaxa={subtaxa}
            references={references}
            wikitext={wikitext}
            commonsImages={commonsImages}
            commonsTaxon={commonsTaxon}
            collapsedBoxes={collapsedBoxes}
            onToggleBox={onToggleBox}
            onChooseTaxoboxSource={onChooseTaxoboxSource}
          />
        )}

        {view === "names" && (
          <NamesTab activeData={activeData} availableSources={facets.availableSources} author={author} />
        )}

        {view === "other" && <OtherInfoTab activeData={activeData} />}

        {view === "wikidata" && <WikidataPanel diagnosis={diagnosis} />}

        {UNSUPPORTED_PROJECT_VIEWS.includes(view) && (
          <div className="panel">
            <p className="panel-empty">Non pris en charge pour l'instant.</p>
          </div>
        )}

        {view === "data" && (
          <DataTab
            activeSource={activeSource}
            activeEntry={activeEntry}
            activeData={activeData}
            onRetryModule={(moduleId) => tracking.retryModule(query, moduleId)}
          />
        )}
      </div>
    </div>
  );
}

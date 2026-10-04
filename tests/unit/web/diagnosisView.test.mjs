// Run from the repo root: node --test tests/unit/web/*.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const { summarize, suggestionsOf } = await import(pathToFileURL(resolve("web-app/src/features/wikidata/diagnosisView.js")).href);

const ecart = (over) => ({
  type: "x",
  severite: "info",
  propriete: "P",
  valeur_wikidata: null,
  valeur_source: null,
  source: "col",
  message: "m",
  proposition: null,
  ...over,
});
const section = (name, ecarts) => ({ section: name, ecarts, comptes: null, niveau: null, limites: [] });
const article = { titre: "Gadus morhua", revid: 1, date: "2026-01-01T00:00:00Z", url: "https://fr.wikipedia.org/wiki/Gadus_morhua" };
const proposition = (id, verifiee = true) => ({
  id, module: "wrms", propriete: "P850", valeur: "1", type: "chaine",
  reference: { stated_in: "Q1", retrieved: "2026-01-01" }, verifiee, coche_par_defaut: verifiee,
});
const base = { qid: "Q1", taxon: "Gadus morhua", ecarts: [], article_frwiki: article, sections_frwiki: [], avertissements: [] };

test("aucun résultat : rien à résumer", () => {
  assert.equal(summarize(null), null);
});

test("Wikidata : erreurs et avertissements à réviser, suggestions à compléter, infos écartées des compteurs", () => {
  const s = summarize({
    ...base,
    ecarts: [
      ecart({ severite: "erreur", valeur_wikidata: "a", valeur_source: "b" }),
      ecart({ severite: "avertissement", valeur_wikidata: "a", valeur_source: "b" }),
      ecart({ severite: "info" }),
      ecart({ severite: "suggestion", proposition: proposition("p1") }),
      ecart({ severite: "suggestion", proposition: null }),
    ],
  });
  assert.equal(s.wikidata.state, "exists");
  assert.equal(s.wikidata.toReview.length, 2);
  assert.equal(s.wikidata.infos.length, 1);
  assert.equal(s.wikidata.toComplete.length, 1);
});

test("sans item Wikidata : l'écart item_absent n'est pas une différence à réviser", () => {
  const s = summarize({
    qid: null, taxon: "X y", article_frwiki: null, sections_frwiki: [], avertissements: [],
    ecarts: [ecart({ type: "item_absent", severite: "erreur" })],
  });
  assert.equal(s.wikidata.state, "absent");
  assert.equal(s.wikidata.toReview.length, 0);
  assert.equal(s.frwiki.state, "absent");
  assert.equal(s.create, 1);
});

test("frwiki : valeur présente dans l'article → réviser ; absente de l'article → compléter", () => {
  const s = summarize({
    ...base,
    sections_frwiki: [
      section("classification", [
        ecart({ type: "rang_different", severite: "avertissement", valeur_wikidata: "famille A", valeur_source: "famille B" }),
      ]),
      section("liens", [ecart({ type: "base_absente_article", valeur_source: "123" })]),
      section("sous_taxons", [
        ecart({ type: "sous_taxon_absent_article", valeur_source: "A, B" }),
        ecart({ type: "sous_taxon_absent_source", valeur_wikidata: "C" }),
      ]),
    ],
  });
  assert.equal(s.frwiki.state, "exists");
  assert.deepEqual(s.frwiki.toReview.map((r) => r.section), ["classification", "sous_taxons"]);
  assert.deepEqual(s.frwiki.toComplete.map((r) => r.section), ["liens", "sous_taxons"]);
  assert.equal(s.create, 0);
});

test("frwiki : sitelink absent → à créer, section « article » exclue des lignes", () => {
  const s = summarize({
    ...base,
    article_frwiki: null,
    sections_frwiki: [section("article", [ecart({ type: "article_absent_frwiki" })])],
  });
  assert.equal(s.frwiki.state, "absent");
  assert.equal(s.frwiki.toReview.length + s.frwiki.toComplete.length, 0);
  assert.equal(s.create, 1);
});

test("frwiki : article illisible (ni article ni section) → état inconnu, pas de création proposée", () => {
  const s = summarize({ ...base, article_frwiki: null, sections_frwiki: [], avertissements: ["illisible"] });
  assert.equal(s.frwiki.state, "unknown");
  assert.equal(s.create, 0);
});

test("compteurs d'onglets : somme des projets", () => {
  const s = summarize({
    ...base,
    ecarts: [
      ecart({ severite: "erreur", valeur_wikidata: "a", valeur_source: "b" }),
      ecart({ severite: "suggestion", proposition: proposition("p1") }),
    ],
    sections_frwiki: [
      section("uicn", [ecart({ type: "uicn_different", severite: "avertissement", valeur_wikidata: "LC", valeur_source: "VU" })]),
      section("liens", [ecart({ type: "base_absente_article", valeur_source: "1" })]),
    ],
  });
  assert.deepEqual(s.counts, { toCreate: 0, toReview: 2, toComplete: 2 });
});

test("suggestionsOf : seules les suggestions avec proposition", () => {
  const r = {
    ...base,
    ecarts: [
      ecart({ severite: "suggestion", proposition: proposition("p1") }),
      ecart({ severite: "suggestion" }),
      ecart({ severite: "erreur" }),
    ],
  };
  assert.deepEqual(suggestionsOf(r).map((e) => e.proposition.id), ["p1"]);
  assert.deepEqual(suggestionsOf(null), []);
});

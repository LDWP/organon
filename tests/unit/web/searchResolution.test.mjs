// Run from the repo root: node --test tests/unit/web/*.test.mjs
import assert from "node:assert/strict";
import { resolve } from "node:path";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

const { resolveMatches } = await import(pathToFileURL(resolve("web-app/src/features/search/searchResolution.js")).href);

const m = (scientific_name, kingdom = "animal", over = {}) => ({
  scientific_name, kingdom, rank: "espèce", vernacular_names: [], gbif_key: 1, ...over,
});

test("aucun résultat : génération directe par le nom saisi", () => {
  assert.deepEqual(resolveMatches([], "Xus yus", "*"), { kind: "none" });
});

test("un seul nom scientifique identique : choix direct, même avec des sous-taxons listés", () => {
  const matches = [m("Panthera leo"), m("Panthera leo leo", "animal", { rank: "sous-espèce" })];
  const r = resolveMatches(matches, "panthera leo", "*");
  assert.equal(r.kind, "single");
  assert.equal(r.match.scientific_name, "Panthera leo");
});

test("homonymes entre règnes : ambiguïté", () => {
  const matches = [m("Morus", "animal"), m("Morus", "végétal")];
  const r = resolveMatches(matches, "Morus", "*");
  assert.equal(r.kind, "ambiguous");
  assert.equal(r.matches.length, 2);
});

test("le filtre de domaine lève l'homonymie", () => {
  const matches = [m("Morus", "animal"), m("Morus", "végétal")];
  const r = resolveMatches(matches, "Morus", "végétal");
  assert.equal(r.kind, "single");
  assert.equal(r.match.kingdom, "végétal");
});

test("nom vernaculaire à plusieurs résultats : ambiguïté", () => {
  const matches = [m("Panthera leo"), m("Felis concolor")];
  assert.equal(resolveMatches(matches, "lion", "*").kind, "ambiguous");
});

test("nom vernaculaire à un seul résultat : choix direct", () => {
  const r = resolveMatches([m("Panthera leo")], "lion", "*");
  assert.equal(r.kind, "single");
});

test("QID : le match unique porte le QID", () => {
  const r = resolveMatches([m("Gadus morhua", "", { qid: "Q1", gbif_key: null })], "Q1", "*");
  assert.equal(r.kind, "single");
});

test("résultats tous écartés par le filtre : génération directe", () => {
  assert.deepEqual(resolveMatches([m("Morus", "animal")], "Morus", "végétal"), { kind: "none" });
});

test("QID avec un filtre de domaine actif : le filtre ne s'applique pas", () => {
  const r = resolveMatches([m("Gadus morhua", "", { qid: "Q1", gbif_key: null })], "Q1", "animal");
  assert.equal(r.kind, "single");
});

test("variantes d'auteur d'un même nom (même règne et même rang) : choix direct de la plus pertinente", () => {
  const matches = [m("Quercus robur", "végétal", { author: "L." }), m("Quercus robur", "végétal", { author: "Asso" })];
  const r = resolveMatches(matches, "Quercus robur", "*");
  assert.equal(r.kind, "single");
  assert.equal(r.match.author, "L.");
});

test("même règne mais rang différent : homonymie", () => {
  const matches = [m("Acanthocephala", "animal", { rank: "phylum" }), m("Acanthocephala", "animal", { rank: "genre" })];
  assert.equal(resolveMatches(matches, "Acanthocephala", "*").kind, "ambiguous");
});

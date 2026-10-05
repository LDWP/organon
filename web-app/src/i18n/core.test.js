import assert from "node:assert/strict";
import test from "node:test";

import { createTranslator, detectLocale, interpolate } from "./core.js";

const fr = {
  "a.hello": "Bonjour {name}",
  "a.onlyFr": "Seulement en français",
  "a.items_one": "{count} élément",
  "a.items_other": "{count} éléments",
};
const en = {
  "a.hello": "Hello {name}",
  "a.items_one": "{count} item",
  "a.items_other": "{count} items",
};
const tEn = createTranslator({ locale: "en", messages: en, fallbackLocale: "fr", fallbackMessages: fr });
const tFr = createTranslator({ locale: "fr", messages: fr, fallbackLocale: "fr", fallbackMessages: fr });

test("interpolate replaces known variables and keeps unknown placeholders", () => {
  assert.equal(interpolate("{a} et {b}", { a: 1 }), "1 et {b}");
  assert.equal(interpolate("sans variable"), "sans variable");
});

test("t interpolates", () => {
  assert.equal(tEn("a.hello", { name: "Ada" }), "Hello Ada");
});

test("t picks the plural variant of the locale", () => {
  assert.equal(tEn("a.items", { count: 1 }), "1 item");
  assert.equal(tEn("a.items", { count: 2 }), "2 items");
  assert.equal(tEn("a.items", { count: 0 }), "0 items");
  // French treats 0 and 1 as singular
  assert.equal(tFr("a.items", { count: 0 }), "0 élément");
  assert.equal(tFr("a.items", { count: 2 }), "2 éléments");
});

test("count is shown in the locale number format", () => {
  const t = createTranslator({
    locale: "en",
    messages: en,
    fallbackLocale: "fr",
    fallbackMessages: fr,
    formatNumber: (n) => new Intl.NumberFormat("en").format(n),
  });
  assert.equal(t("a.items", { count: 1234 }), "1,234 items");
});

test("a key missing from the locale falls back on French", () => {
  assert.equal(tEn("a.onlyFr"), "Seulement en français");
});

test("a key missing everywhere is returned as is", () => {
  assert.equal(tEn("a.unknown"), "a.unknown");
});

test("detectLocale: stored choice, then browser languages, then fallback", () => {
  const base = { enabled: ["fr", "en"], fallback: "fr" };
  assert.equal(detectLocale({ ...base, stored: "en", languages: ["fr-FR"] }), "en");
  assert.equal(detectLocale({ ...base, stored: null, languages: ["de-DE", "en-GB"] }), "en");
  assert.equal(detectLocale({ ...base, stored: null, languages: ["de"] }), "fr");
  assert.equal(detectLocale({ ...base, stored: null, languages: [] }), "fr");
});

test("detectLocale ignores locales that are not enabled", () => {
  const base = { enabled: ["fr"], fallback: "fr" };
  assert.equal(detectLocale({ ...base, stored: "en", languages: ["en-US"] }), "fr");
});

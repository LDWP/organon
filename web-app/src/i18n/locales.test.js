import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import { flatten } from "./core.js";

const LOCALES_DIR = join(import.meta.dirname, "locales");
const REFERENCE = "fr";
const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/;

const files = readdirSync(LOCALES_DIR).filter((f) => f.endsWith(".json"));
const locales = files.map((f) => f.replace(/\.json$/, ""));
const read = (locale) => JSON.parse(readFileSync(join(LOCALES_DIR, `${locale}.json`), "utf8"));

// Plural variants differ per language (ru has `few`, ja only `other`):
// compare keys without their plural suffix, and the {variables} of all
// the variants of a key together.
function describeLocale(locale) {
  const keys = new Map();
  for (const [key, text] of Object.entries(flatten(read(locale)))) {
    assert.equal(typeof text, "string", `${locale}: ${key} must be a string`);
    const base = key.replace(PLURAL_SUFFIX, "");
    const entry = keys.get(base) ?? { variants: [], variables: new Set() };
    entry.variants.push(key);
    for (const [, name] of text.matchAll(/\{(\w+)\}/g)) entry.variables.add(name);
    keys.set(base, entry);
  }
  return keys;
}

test("file names are lowercase wiki language codes", () => {
  for (const locale of locales) assert.match(locale, /^[a-z]{2,3}(-[a-z]+)?$/);
  assert.ok(locales.includes(REFERENCE));
});

for (const locale of locales.filter((l) => l !== REFERENCE)) {
  test(`${locale} has the same keys and variables as ${REFERENCE}`, () => {
    const reference = describeLocale(REFERENCE);
    const other = describeLocale(locale);
    assert.deepEqual([...other.keys()].sort(), [...reference.keys()].sort(), `${locale}: keys`);
    for (const [base, entry] of reference) {
      assert.deepEqual(
        [...other.get(base).variables].sort(),
        [...entry.variables].sort(),
        `${locale}: variables of ${base}`,
      );
    }
  });
}

test("every plural key has an `_other` variant", () => {
  for (const locale of locales) {
    for (const [base, { variants }] of describeLocale(locale)) {
      if (variants.some((key) => PLURAL_SUFFIX.test(key))) {
        assert.ok(variants.includes(`${base}_other`), `${locale}: ${base}_other missing`);
      }
    }
  }
});

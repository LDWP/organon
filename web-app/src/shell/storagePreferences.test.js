import assert from "node:assert/strict";
import test from "node:test";

import { buildLocaleCookie, parseLocaleCookie } from "./storagePreferences.js";

test("parseLocaleCookie finds the locale among other cookies", () => {
  assert.equal(parseLocaleCookie("a=1; organon-locale=en; b=2"), "en");
});

test("parseLocaleCookie ignores a missing or malformed value", () => {
  assert.equal(parseLocaleCookie(""), null);
  assert.equal(parseLocaleCookie("a=1"), null);
  assert.equal(parseLocaleCookie("organon-locale=<script>"), null);
  assert.equal(parseLocaleCookie("xorganon-locale=en"), null);
});

test("buildLocaleCookie: Lax, one year, Secure only over https", () => {
  assert.equal(
    buildLocaleCookie("en", false),
    "organon-locale=en; Max-Age=31536000; Path=/; SameSite=Lax",
  );
  assert.ok(buildLocaleCookie("en", true).endsWith("; Secure"));
});

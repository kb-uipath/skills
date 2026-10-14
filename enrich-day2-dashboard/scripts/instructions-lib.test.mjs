// node --test enrich-day2-dashboard/scripts/instructions-lib.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { loadInstructions, repoSchemaVersion } from "./instructions-lib.mjs";

function fakeRepo(version) {
  const repo = mkdtempSync(join(tmpdir(), "day2-repo-"));
  mkdirSync(join(repo, "src/schema"), { recursive: true });
  mkdirSync(join(repo, "src/data"), { recursive: true });
  writeFileSync(join(repo, "src/schema/account.ts"),
    `export const LEGACY_SCHEMA_VERSION = "1.6" as const;\n`
    + `export const SCHEMA_110_VERSION = "1.10" as const;\nexport const SCHEMA_VERSION = "${version}" as const;\n`);
  writeFileSync(join(repo, `src/data/day2-dashboard-field-instructions-v${version}.json`),
    JSON.stringify({ targetSchemaVersion: version, fields: {} }));
  return repo;
}

test("reads the schema version a dashboard checkout ships, not a step constant", () => {
  assert.equal(repoSchemaVersion(fakeRepo("1.11")), "1.11");
});

test("loads the repo's guide by its shipped version", async () => {
  const { json, from } = await loadInstructions({ repo: fakeRepo("1.11") });
  assert.equal(json.targetSchemaVersion, "1.11");
  assert.match(from, /field-instructions-v1\.11\.json$/);
});

test("follows a deployed route's release manifest to its guide", async (t) => {
  const requested = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    requested.push(String(url));
    if (String(url).endsWith("release-manifest.json")) {
      return new Response(JSON.stringify({ documentation: [
        { path: "llm.md" },
        { path: "llm-guide/day2-dashboard-field-instructions-v1.12.json" },
      ] }));
    }
    return new Response(JSON.stringify({ targetSchemaVersion: "1.12", fields: {} }));
  });
  const { from } = await loadInstructions({ baseUrl: "https://example.test/day2/" });
  assert.equal(from, "https://example.test/day2/llm-guide/day2-dashboard-field-instructions-v1.12.json");
  assert.deepEqual(requested, ["https://example.test/day2/release-manifest.json", from]);
});

test("falls back to the current guide name when a route has no usable manifest", async (t) => {
  const requested = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    requested.push(String(url));
    if (String(url).endsWith("release-manifest.json")) return new Response("not found", { status: 404 });
    return new Response(JSON.stringify({ targetSchemaVersion: "1.11", fields: {} }));
  });
  const { from } = await loadInstructions({ baseUrl: "https://example.test/day2/" });
  assert.equal(from, "https://example.test/day2/llm-guide/day2-dashboard-field-instructions-v1.11.json");
  assert.equal(requested.length, 2);
});

test("sends a curl-style user agent on every request, which the route's WAF requires", async (t) => {
  const agents = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    agents.push(options?.headers?.["User-Agent"]);
    if (String(url).endsWith("release-manifest.json")) {
      return new Response(JSON.stringify({ documentation: [{ path: "llm-guide/day2-dashboard-field-instructions-v1.11.json" }] }));
    }
    return new Response(JSON.stringify({ targetSchemaVersion: "1.11", fields: {} }));
  });
  await loadInstructions({ baseUrl: "https://example.test/day2/" });
  assert.equal(agents.length, 2);
  assert.ok(agents.every((agent) => /^curl\//.test(agent ?? "")), JSON.stringify(agents));
});

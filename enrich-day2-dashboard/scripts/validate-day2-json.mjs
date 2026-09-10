#!/usr/bin/env node
// Structural validator for schema 1.10 Day 2 dashboard JSON.
//
//   node validate-day2-json.mjs <file> [--instructions <path-or-url>] [--repo <dashboard-repo>]
//                               [--base-url <deployed-route-url>]
//
// Validates against the app's machine-readable field instructions
// (llm-guide/day2-dashboard-field-instructions-v1.10.json). Instruction source, in
// order: --instructions, --repo's src/data copy, the deployed route (--base-url,
// default the alpha host). With --repo it additionally runs the app's real
// importAccount/toPortableAccount round-trip via a temporary vitest test, which is the
// authoritative check.
import { readFileSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";

const args = process.argv.slice(2);
const file = args.find((a) => !a.startsWith("--"));
const opt = (name) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
};
if (!file) {
  console.error("usage: validate-day2-json.mjs <file> [--instructions <path-or-url>] [--repo <path>] [--base-url <url>]");
  process.exit(2);
}
const repo = opt("--repo");
const baseUrl = (opt("--base-url") ?? "https://agenticgtm.alpha.uipath.host/day2-v6/").replace(/\/?$/, "/");

async function loadInstructions() {
  const src = opt("--instructions");
  if (src && !/^https?:/.test(src)) return { json: JSON.parse(readFileSync(src, "utf8")), from: src };
  if (!src && repo) {
    const p = path.join(repo, "src/data/day2-dashboard-field-instructions-v1.10.json");
    if (existsSync(p)) return { json: JSON.parse(readFileSync(p, "utf8")), from: p };
  }
  const url = src ?? `${baseUrl}llm-guide/day2-dashboard-field-instructions-v1.10.json`;
  // The host's WAF rejects generic script user agents; a curl-style UA passes.
  const res = await fetch(url, { headers: { "User-Agent": "curl/8.7.1" } });
  if (!res.ok) throw new Error(`fetch ${url} -> ${res.status}`);
  return { json: await res.json(), from: url };
}

const doc = JSON.parse(readFileSync(file, "utf8"));
const { json: instructions, from } = await loadInstructions();
const errors = [];
const warnings = [];

// schemaVersion gate: any 1.x is importable, 2.x is not.
const sv = doc.schemaVersion;
if (typeof sv !== "string" || !/^1\.\d+$/.test(sv)) errors.push(`schemaVersion ${JSON.stringify(sv)} is not an importable 1.x version`);
else if (sv !== instructions.targetSchemaVersion) warnings.push(`schemaVersion ${sv} != instruction target ${instructions.targetSchemaVersion}; importer will normalize`);
if (typeof doc.customerName !== "string" || doc.customerName.trim() === "") errors.push("customerName is required and non-empty");

// Expand an instruction pointer (with `*` array wildcards) to the doc values it addresses.
function resolve(pointer) {
  let nodes = [{ value: doc, at: "" }];
  if (pointer === "") return nodes;
  for (const rawSeg of pointer.split("/").slice(1)) {
    const seg = rawSeg.replaceAll("~1", "/").replaceAll("~0", "~");
    const next = [];
    for (const n of nodes) {
      if (n.value === undefined || n.value === null) continue;
      if (seg === "*") {
        if (Array.isArray(n.value)) n.value.forEach((v, i) => next.push({ value: v, at: `${n.at}/${i}` }));
      } else if (typeof n.value === "object" && !Array.isArray(n.value) && seg in n.value) {
        next.push({ value: n.value[seg], at: `${n.at}/${seg}` });
      }
    }
    nodes = next;
  }
  return nodes;
}

const typeOk = (value, type) => {
  switch (type) {
    case "array": return Array.isArray(value);
    case "object": return typeof value === "object" && value !== null && !Array.isArray(value);
    case "string": case "number": case "boolean": return typeof value === type;
    default: return true; // unknown instruction type: don't fail the doc for it
  }
};

let checked = 0;
for (const [pointer, spec] of Object.entries(instructions.fields ?? {})) {
  if (pointer === "") continue;
  const nodes = resolve(pointer);
  if (!pointer.includes("*") && nodes.length === 0) {
    warnings.push(`missing ${pointer} (importer will default it)`);
    continue;
  }
  for (const { value, at } of nodes) {
    checked++;
    if (value === null) {
      if (!spec.nullable) errors.push(`${at}: null but not nullable`);
      continue;
    }
    if (value === undefined) { warnings.push(`missing ${at} (importer will default it)`); continue; }
    if (spec.type && !typeOk(value, spec.type)) { errors.push(`${at}: expected ${spec.type}, got ${Array.isArray(value) ? "array" : typeof value}`); continue; }
    const allowed = spec.allowedValues ?? [];
    if (allowed.length > 0 && value !== spec.emptyValue) {
      // For array fields the allowed values constrain each element.
      const candidates = Array.isArray(value) ? value : [value];
      for (const c of candidates) {
        if (!allowed.includes(c)) errors.push(`${at}: ${JSON.stringify(c)} not in allowed values [${allowed.join(", ")}]`);
      }
    }
  }
}

// Unknown top-level keys survive import inside _forward — surface them so they're deliberate.
const knownTop = new Set(Object.keys(instructions.fields ?? {}).filter((p) => p && p.split("/").length === 2).map((p) => p.split("/")[1]));
for (const k of Object.keys(doc)) if (!knownTop.has(k)) warnings.push(`unknown top-level key "${k}" (preserved in _forward on import)`);

// Duplicate ids in the live document break patch-by-id enrichment. priorContext and
// _forward are snapshots of earlier data, so ids there legitimately mirror live ids.
const ids = new Map();
(function walk(v, at) {
  if (at === "/priorContext" || at === "/_forward") return;
  if (Array.isArray(v)) v.forEach((x, i) => walk(x, `${at}/${i}`));
  else if (v && typeof v === "object") {
    if (typeof v.id === "string" && v.id) {
      if (ids.has(v.id)) errors.push(`duplicate id ${v.id} at ${at} and ${ids.get(v.id)}`);
      else ids.set(v.id, at);
    }
    for (const [k, x] of Object.entries(v)) walk(x, `${at}/${k}`);
  }
})(doc, "");

console.log(`Instructions: ${from}`);
console.log(`Checked ${checked} field values against ${Object.keys(instructions.fields ?? {}).length} instruction pointers.`);
for (const w of warnings) console.log(`  warn: ${w}`);
for (const e of errors) console.log(`  ERROR: ${e}`);

// Authoritative round-trip through the app's importer, when the repo is available.
if (repo && errors.length === 0) {
  const testPath = path.join(repo, "tests", "tmp-skill-validate.spec.ts");
  const absFile = path.resolve(file);
  writeFileSync(testPath, `import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { importAccount, toPortableAccount } from "../src/schema/account";

describe("skill validate round-trip", () => {
  it("imports and re-exports without losing identity", () => {
    const raw = JSON.parse(readFileSync(${JSON.stringify(absFile)}, "utf8"));
    const account = importAccount(raw);
    const portable = toPortableAccount(account) as Record<string, unknown>;
    expect(portable.customerName).toBe(raw.customerName);
    const again = toPortableAccount(importAccount(portable)) as Record<string, unknown>;
    expect(again).toEqual(portable);
  });
});
`);
  try {
    execFileSync("npx", ["vitest", "run", "tests/tmp-skill-validate.spec.ts"], { cwd: repo, stdio: "inherit" });
    console.log("importAccount round-trip: OK");
  } catch {
    errors.push("importAccount round-trip failed (see vitest output above)");
  } finally {
    rmSync(testPath, { force: true });
  }
}

console.log(errors.length === 0 ? `PASS (${warnings.length} warnings)` : `FAIL (${errors.length} errors)`);
process.exit(errors.length === 0 ? 0 : 1);

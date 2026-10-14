#!/usr/bin/env node
// Apply an evidence findings file to a schema 1.11 Day 2 document, with the app's write policy enforced.
//
//   node apply-findings.mjs <baseline.json> <findings.json> [--out <file>] [--report <file>] [--dry-run]
//                           [--repo <dashboard-repo>] [--instructions <path-or-url>] [--base-url <url>]
//
// findings.json is { "findings": [ ... ] }; each finding is
//   { "op": "set" | "add", "pointer": "/risks", "value": ..., "source": "locator", "asOf": "YYYY-MM-DD",
//     "attestedBy": "Name (locator)",        // required where the field's policy is attestation_allowed
//     "humanAuthored": true,                  // required, with attestedBy, where the policy is human_only
//     "supersedes": "why the old value loses" // required to overwrite a non-empty value
//   }
//   set  writes one existing field (a leaf, or a list of strings).
//   add  appends a record to a collection; a record whose identity key already exists is patched, and
//        keeps its id. New records get a deterministic UUID (same finding, same id on every rebuild) and every
//        other field takes the app's documented empty.
//
// The write policy comes from the field instructions, never from this script: system-managed, preserve-only,
// constant and unused fields are refused; human_only needs a human author; attestation needs a named person;
// evidence needs a source and a date. Any refusal aborts the whole run and nothing is written.
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { loadInstructions, resolve, descriptorFor, whoMayFill, isEmpty } from "./instructions-lib.mjs";

// How a collection decides that a finding is about a record that already exists.
const IDENTITY = {
  "/risks": "risk", "/relationships": "customerName", "/pipelineOpportunities": "key", "/functionalNeeds": "need",
  "/cadenceGoals": "label", "/goals": "text", "/background/metricCheckpoints": "label",
  "/consumptionPlan/primaryUseCases": "useCases",
  "/stakeholdersActions/relationshipMap/*/customerPeople": "name",
};
const PLACEHOLDER = /^\s*(tbd|unknown|n\/a|none|-+|\?+)\s*$/i;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

const args = process.argv.slice(2);
const opt = (n) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : undefined; };
const valued = new Set(["--out", "--report", "--repo", "--instructions", "--base-url"]);
const positional = args.filter((a, i) => !a.startsWith("--") && !valued.has(args[i - 1]));
const [baselinePath, findingsPath] = positional;
if (!baselinePath || !findingsPath) {
  console.error("usage: apply-findings.mjs <baseline.json> <findings.json> [--out <file>] [--report <file>] [--dry-run] [--repo <path>]");
  process.exit(2);
}

const { json: instructions, from } = await loadInstructions({ instructions: opt("--instructions"), repo: opt("--repo"), baseUrl: opt("--base-url") });
const fields = instructions.fields ?? {};
const doc = JSON.parse(readFileSync(baselinePath, "utf8"));
const { findings } = JSON.parse(readFileSync(findingsPath, "utf8"));

const errors = [];
const changes = []; // { pointer, value, source, asOf, policy, note }
const clone = (v) => (v === undefined ? v : JSON.parse(JSON.stringify(v)));
const generic = (pointer) => descriptorFor(fields, pointer).pointer;
const short = (v) => { const s = typeof v === "string" ? v : JSON.stringify(v); return s.length > 90 ? `${s.slice(0, 87)}...` : s; };

function getAt(pointer) {
  const node = resolve(doc, pointer)[0];
  return node ? { found: true, value: node.value } : { found: false, value: undefined };
}

function setAt(pointer, value) {
  const segs = pointer.split("/").slice(1);
  let cur = doc;
  for (let i = 0; i < segs.length - 1; i++) {
    const s = segs[i];
    if (cur[s] === undefined || cur[s] === null) cur[s] = {};
    cur = cur[s];
  }
  cur[segs[segs.length - 1]] = value;
}

/** Policy and value checks for one leaf (or list of strings) at a generic pointer. */
function checkLeaf(gp, value, f, concrete) {
  const spec = fields[gp];
  if (!spec) return errors.push(`${concrete}: ${gp} is not a field in the instructions`);
  const who = whoMayFill(spec, gp);
  if (who === "skip") return errors.push(`${concrete}: ${spec.writePolicy ?? spec.requirement} fields are never written by this skill`);
  if (who === "human" && !(f.humanAuthored === true && f.attestedBy)) {
    return errors.push(`${concrete}: human_only; needs humanAuthored:true and attestedBy naming the person who authored it (suggest it in the report instead)`);
  }
  if (who === "attest" && !f.attestedBy) return errors.push(`${concrete}: needs attestedBy, a named person's explicit statement (never inferred)`);
  if (typeof f.source !== "string" || !f.source.trim()) return errors.push(`${concrete}: source locator is required`);
  if (!ISO_DATE.test(f.asOf ?? "")) return errors.push(`${concrete}: asOf must be YYYY-MM-DD`);
  if (value === null) return spec.nullable ? undefined : errors.push(`${concrete}: null is not allowed here`);
  const t = Array.isArray(value) ? "array" : typeof value;
  if (spec.type && spec.type !== t) return errors.push(`${concrete}: expected ${spec.type}, got ${t}`);
  if (t === "string") {
    // The descriptors state table-layout limits in prose ("Maximum 48 Unicode characters", "Longest token at most
    // 17 characters"); publication blocks on them, so enforce them here.
    const cons = JSON.stringify(spec.constraints ?? []);
    const max = cons.match(/Maximum (\d+) Unicode characters/);
    if (max && [...value].length > +max[1]) errors.push(`${concrete}: ${[...value].length} characters; the limit is ${max[1]}`);
    const tok = cons.match(/Longest token at most (\d+) characters/);
    if (tok && value.split(/\s+/).some((w) => [...w].length > +tok[1])) errors.push(`${concrete}: a word is longer than ${tok[1]} characters`);
    if (PLACEHOLDER.test(value)) errors.push(`${concrete}: placeholder text is never content`);
    if (/\n/.test(value) && /single line|one line/i.test(JSON.stringify(spec.constraints ?? ""))) errors.push(`${concrete}: must be one line`);
    if (/YYYY-MM-DD/.test(spec.format ?? "") && !ISO_DATE.test(value)) errors.push(`${concrete}: must be YYYY-MM-DD`);
  }
  if (t === "number" && (!Number.isFinite(value) || value < 0)) errors.push(`${concrete}: must be a finite nonnegative number`);
  const allowed = spec.allowedValues ?? [];
  if (allowed.length && value !== spec.emptyValue && !(t === "array" ? value.every((x) => allowed.includes(x)) : allowed.includes(value))) {
    errors.push(`${concrete}: ${JSON.stringify(value)} is not in [${allowed.join(", ")}]`);
  }
  if (t === "array") value.forEach((item, i) => checkLeaf(`${gp}/*`, item, f, `${concrete}/${i}`));
}

/** Check every leaf of a record (recursing through nested objects) against its descriptors. */
function checkTree(gp, value, f, concrete) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    for (const [k, v] of Object.entries(value)) {
      if (k === "id") { errors.push(`${concrete}/id: ids are system-managed; the script assigns them`); continue; }
      checkTree(`${gp}/${k}`, v, f, `${concrete}/${k}`);
    }
  } else checkLeaf(gp, value, f, concrete);
}

/** A v4-shaped UUID derived from a seed, so a rebuild gives the same record the same id (the app's own ids are v4). */
function stableId(seed) {
  const b = createHash("sha1").update(`day2-findings/${seed}`).digest().subarray(0, 16);
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = b.toString("hex");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

/** A new record starts from the documented empty of every direct field, then takes the finding's values. */
function newRecord(arrayGp, value) {
  const record = {};
  for (const [p, s] of Object.entries(fields)) {
    if (!p.startsWith(`${arrayGp}/*/`)) continue;
    const key = p.slice(arrayGp.length + 3);
    if (key.includes("/") || key === "id") continue;
    if (s.emptyValue !== undefined) record[key] = clone(s.emptyValue);
  }
  const idKey = IDENTITY[arrayGp];
  if (fields[`${arrayGp}/*/id`]) record.id = stableId(`${arrayGp}|${idKey && value[idKey] ? String(value[idKey]).trim().toLowerCase() : JSON.stringify(value)}`);
  return Object.assign(record, clone(value));
}

for (const [n, f] of (findings ?? []).entries()) {
  const tag = `finding ${n + 1} (${f.pointer})`;
  if (!["set", "add"].includes(f.op) || typeof f.pointer !== "string") { errors.push(`${tag}: op must be set or add, with a pointer`); continue; }
  const before = errors.length;

  if (f.op === "set") {
    const gp = generic(f.pointer);
    checkTree(gp, f.value, f, f.pointer);
    if (errors.length > before) continue;
    const cur = getAt(f.pointer);
    if (cur.found && !isEmpty(cur.value) && JSON.stringify(cur.value) !== JSON.stringify(f.value) && !f.supersedes) {
      errors.push(`${tag}: would overwrite a non-empty value; add "supersedes" saying why the old value loses (recency, or Salesforce on the fields it owns)`);
      continue;
    }
    setAt(f.pointer, clone(f.value));
    changes.push({ pointer: f.pointer, value: f.value, source: f.source, asOf: f.asOf, policy: whoMayFill(fields[gp], gp), note: f.supersedes ? `supersedes: ${f.supersedes}` : "" });
    continue;
  }

  // op: add
  const arrayGp = generic(f.pointer);
  const arr = getAt(f.pointer);
  if (!arr.found || !Array.isArray(arr.value)) { errors.push(`${tag}: ${f.pointer} is not a collection in this document`); continue; }
  const elementSpec = fields[`${arrayGp}/*`];
  if (!elementSpec) { errors.push(`${tag}: ${arrayGp}/* is not in the instructions`); continue; }
  if (typeof f.value === "string") { // a list of strings (e.g. executionPlan.day30)
    checkLeaf(`${arrayGp}/*`, f.value, f, `${f.pointer}/-`);
    if (errors.length > before) continue;
    if (!arr.value.includes(f.value)) {
      arr.value.push(f.value);
      changes.push({ pointer: `${f.pointer}/${arr.value.length - 1}`, value: f.value, source: f.source, asOf: f.asOf, policy: whoMayFill(elementSpec, `${arrayGp}/*`), note: "" });
    }
    continue;
  }
  checkTree(`${arrayGp}/*`, f.value, f, `${f.pointer}/-`);
  if (errors.length > before) continue;
  const idKey = IDENTITY[arrayGp];
  const norm = (s) => String(s ?? "").trim().toLowerCase();
  const existingIndex = idKey ? arr.value.findIndex((r) => norm(r[idKey]) !== "" && norm(r[idKey]) === norm(f.value[idKey])) : -1;
  if (existingIndex >= 0) { // patch in place, keeping the id
    const rec = arr.value[existingIndex];
    for (const [k, v] of Object.entries(f.value)) {
      if (k === idKey) continue; // the match key already matched (ignoring case and spacing); keep the stored spelling
      if (!isEmpty(rec[k]) && JSON.stringify(rec[k]) !== JSON.stringify(v) && !f.supersedes) {
        errors.push(`${tag}: ${f.pointer}/${existingIndex}/${k} already has a value; add "supersedes" to replace it`);
        continue;
      }
      if (JSON.stringify(rec[k]) !== JSON.stringify(v)) {
        rec[k] = clone(v);
        changes.push({ pointer: `${f.pointer}/${existingIndex}/${k}`, value: v, source: f.source, asOf: f.asOf, policy: whoMayFill(fields[`${arrayGp}/*/${k}`], `${arrayGp}/*/${k}`), note: "patched existing record" });
      }
    }
  } else {
    arr.value.push(newRecord(arrayGp, f.value));
    const at = `${f.pointer}/${arr.value.length - 1}`;
    for (const [k, v] of Object.entries(f.value)) {
      changes.push({ pointer: `${at}/${k}`, value: v, source: f.source, asOf: f.asOf, policy: whoMayFill(fields[`${arrayGp}/*/${k}`], `${arrayGp}/*/${k}`), note: "new record" });
    }
  }
}

if (errors.length) {
  // exitCode, not process.exit(): exiting straight after a long write can truncate piped output.
  console.error(`REFUSED: ${errors.length} problem(s); nothing written.`);
  for (const e of errors) console.error(`  - ${e}`);
  process.exitCode = 1;
} else {
  finish();
}

function finish() {
  const lines = [
    `Applied ${changes.length} field values from ${findings.length} findings (instructions: ${from}).`, "",
    "| Field | New value (short) | Source | As-of | Policy | Note |", "| --- | --- | --- | --- | --- | --- |",
    ...changes.map((c) => `| ${c.pointer} | ${short(c.value).replaceAll("|", "\\|")} | ${c.source.replaceAll("|", "\\|")} | ${c.asOf} | ${c.policy} | ${c.note} |`),
  ];
  if (opt("--report")) writeFileSync(opt("--report"), `${lines.join("\n")}\n`);
  else console.log(lines.join("\n"));
  if (!args.includes("--dry-run")) {
    const out = opt("--out");
    if (!out) { console.error("no --out given; use --dry-run to preview"); process.exit(2); }
    writeFileSync(out, `${JSON.stringify(doc, null, 2)}\n`);
    console.error(`wrote ${out}`);
  }
}

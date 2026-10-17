#!/usr/bin/env node
// Apply an evidence findings file to a schema 1.11 or 1.12 Day 2 document, with the app's write policy enforced.
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
//        other field takes the app's documented empty. A nested list with an identity (a pursuit's draw lines,
//        by row) merges line by line: lines it already has are patched, and lines the finding omits are kept.
//
// The write policy comes from the field instructions, never from this script: system-managed, preserve-only,
// constant and unused fields are refused; human_only needs a human author; attestation needs a named person;
// evidence needs a source and a date. Any refusal aborts the whole run and nothing is written.
//
// Schema 1.12 (the /day2-v7 tabs) refers to consumption rows and pipeline opportunities by id. A finding names
// them instead, in any string value: "ref:row:<offering>" (or "ref:row:<category>|<offering>" when two
// categories share an offering) and "ref:opportunity:<key>". Each resolves to the record's id, case-insensitively
// and exactly once or the run is refused; a referenced consumption row with no id gets a deterministic one, which
// is the only thing this script ever writes on a consumption row. The five strategic initiatives are fixed:
// a finding patches one by its `initiative` and never adds one.
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { loadInstructions, resolve, descriptorFor, whoMayFill as policyOf, isEmpty } from "./instructions-lib.mjs";

// How a collection decides that a finding is about a record that already exists.
const IDENTITY = {
  "/risks": "risk", "/relationships": "customerName", "/pipelineOpportunities": "key", "/functionalNeeds": "need",
  "/cadenceGoals": "label", "/goals": "text", "/background/metricCheckpoints": "label",
  "/consumptionPlan/primaryUseCases": "useCases",
  "/stakeholdersActions/relationshipMap/*/customerPeople": "name",
  "/snapshot/csPriorities": "title", "/snapshot/pursuits": "opportunityId", "/snapshot/pursuits/*/draw": "rowId",
  "/renewalTest/rows": "rowId", "/strategicInitiatives": "initiative",
};
// Collections whose records are fixed: a finding patches one by its identity key and never adds one.
const FIXED = { "/strategicInitiatives": "the five initiatives are fixed" };
// Fields that hold another record's id, by the kind of record: a leaf name, or an exact generic pointer.
const REFERENCE_LEAVES = { rowId: "row", opportunityId: "opportunity" };
const REFERENCE_POINTERS = { "/snapshot/topPursuitIds/*": "opportunity" };
const REFERENCE_NAMES = { row: "consumption row", opportunity: "pipeline opportunity" };
const referenceKind = (gp) => REFERENCE_POINTERS[gp] ?? REFERENCE_LEAVES[gp.split("/").pop()];
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
const schemaVersion = instructions.targetSchemaVersion;
const whoMayFill = (spec, pointer) => policyOf(spec, pointer, schemaVersion);
const doc = JSON.parse(readFileSync(baselinePath, "utf8"));
const { findings } = JSON.parse(readFileSync(findingsPath, "utf8"));

const errors = [];
const changes = []; // { pointer, value, source, asOf, policy, note }
const refKinds = new Map(); // id -> "row" | "opportunity", for ids a ref: token resolved to
const minted = []; // { pointer, value } of consumption-row ids minted for a ref:row
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
  // A resolved id goes only into a reference field of its own kind, and a system-managed reference field
  // (rowId, opportunityId) takes nothing else. A record's own id is never a reference.
  const kind = referenceKind(gp);
  const resolvedKind = typeof value === "string" ? refKinds.get(value) : undefined;
  if (resolvedKind && resolvedKind !== kind) {
    return errors.push(`${concrete}: holds a ref:${resolvedKind} id; ${kind ? `this field takes ref:${kind}` : "only a rowId or opportunityId field takes one"}`);
  }
  if (kind && typeof value === "string" && value !== "" && !idsOf(kind).has(value)) {
    return errors.push(`${concrete}: names no ${REFERENCE_NAMES[kind]} in this document; use ref:${kind}:<…>`);
  }
  const resolvedReference = who === "skip" && kind !== undefined && resolvedKind === kind;
  if (who === "skip" && !resolvedReference) return errors.push(`${concrete}: ${spec.writePolicy ?? spec.requirement} fields are never written by this skill`);
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
  if (t === "array") value.forEach((item, i) => checkTree(`${gp}/*`, item, f, `${concrete}/${i}`));
}

/** The ids of every record of one kind in the document (after any ref: minting). */
function idsOf(kind) {
  const records = kind === "row" ? (doc.consumptionPlan?.groups ?? []).flatMap((group) => group.rows ?? []) : (doc.pipelineOpportunities ?? []);
  return new Set(records.map((record) => record.id).filter(Boolean));
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

const norm = (s) => String(s ?? "").trim().toLowerCase();

/** Resolve "ref:row:…" and "ref:opportunity:…" tokens anywhere in a value to the records' ids. */
function resolveRefs(value, tag) {
  if (typeof value === "string") return resolveRef(value, tag);
  if (Array.isArray(value)) return value.map((item) => resolveRefs(item, tag));
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, resolveRefs(v, tag)]));
  return value;
}

function resolveRef(token, tag) {
  const m = /^ref:(row|opportunity):(.+)$/.exec(token);
  if (!m) return token;
  if (m[1] === "row") {
    const [category, offering] = m[2].includes("|") ? m[2].split("|") : [null, m[2]];
    const hits = (doc.consumptionPlan?.groups ?? []).flatMap((group, gi) => (group.rows ?? []).map((row, ri) => ({ group, gi, row, ri })))
      .filter(({ group, row }) => norm(row.offering) === norm(offering) && (category === null || norm(group.element) === norm(category)));
    if (hits.length !== 1) {
      errors.push(`${tag}: ${token} ${hits.length ? "names more than one consumption row; use ref:row:<category>|<offering>" : "names no consumption row"}`);
      return token;
    }
    const { group, gi, row, ri } = hits[0];
    if (!row.id) {
      row.id = stableId(`consumptionRow|${norm(group.element)}|${norm(row.offering)}`);
      minted.push({ pointer: `/consumptionPlan/groups/${gi}/rows/${ri}/id`, value: row.id });
    }
    refKinds.set(row.id, "row");
    return row.id;
  }
  const hits = (doc.pipelineOpportunities ?? []).filter((item) => norm(item.key) === norm(m[2]));
  if (hits.length !== 1 || !hits[0].id) {
    errors.push(`${tag}: ${token} names ${hits.length > 1 ? "more than one pipeline opportunity" : hits.length ? "a pipeline opportunity with no id" : "no pipeline opportunity"}`);
    return token;
  }
  refKinds.set(hits[0].id, "opportunity");
  return hits[0].id;
}

/**
 * A deterministic id: the same record gets the same id on every rebuild. It is keyed by the record's identity
 * and, for a nested record (a pursuit's draw line), by its parent too, so two parents' lines never share one.
 */
function recordId(arrayGp, value, parent, fallback) {
  const idKey = IDENTITY[arrayGp];
  const key = idKey && value[idKey] ? norm(value[idKey]) : fallback;
  return stableId(parent ? `${arrayGp}|${parent}|${key}` : `${arrayGp}|${key}`);
}

/** Records nested in a record get deterministic ids too; a nested list may not name one identity twice. */
function assignNestedIds(recordGp, record, parent, at) {
  for (const [k, v] of Object.entries(record)) {
    const gp = `${recordGp}/${k}`;
    if (!Array.isArray(v) || !fields[`${gp}/*/id`]) continue;
    const seen = new Set();
    v.forEach((item, index) => {
      if (!item || typeof item !== "object") return;
      if (!item.id) item.id = recordId(gp, item, parent, `${index}|${JSON.stringify(item)}`);
      if (seen.has(item.id)) errors.push(`${at}/${k}/${index}: two lines name the same ${IDENTITY[gp] ?? "record"}; give each one line`);
      seen.add(item.id);
      assignNestedIds(`${gp}/*`, item, item.id, `${at}/${k}/${index}`);
    });
  }
}

/** A new record starts from the documented empty of every direct field, then takes the finding's values. */
function newRecord(arrayGp, value, parent, at) {
  const record = {};
  for (const [p, s] of Object.entries(fields)) {
    if (!p.startsWith(`${arrayGp}/*/`)) continue;
    const key = p.slice(arrayGp.length + 3);
    if (key.includes("/") || key === "id") continue;
    if (s.emptyValue !== undefined) record[key] = clone(s.emptyValue);
  }
  if (fields[`${arrayGp}/*/id`]) record.id = recordId(arrayGp, value, parent, JSON.stringify(value));
  Object.assign(record, clone(value));
  assignNestedIds(`${arrayGp}/*`, record, record.id ?? at, at);
  return record;
}

/** Patch an existing record in place, keeping its id. A nested list with an identity merges line by line. */
function patchRecord(arrayGp, rec, value, f, tag, at) {
  const idKey = IDENTITY[arrayGp];
  for (const [k, v] of Object.entries(value)) {
    if (k === idKey) continue; // the match key already matched (ignoring case and spacing); keep the stored spelling
    const nestedGp = `${arrayGp}/*/${k}`;
    if (IDENTITY[nestedGp] && Array.isArray(v)) {
      if (!Array.isArray(rec[k])) rec[k] = [];
      mergeNested(nestedGp, rec[k], v, f, tag, `${at}/${k}`, rec.id ?? at);
      continue;
    }
    if (!isEmpty(rec[k]) && JSON.stringify(rec[k]) !== JSON.stringify(v) && !f.supersedes) {
      errors.push(`${tag}: ${at}/${k} already has a value; add "supersedes" to replace it`);
      continue;
    }
    if (JSON.stringify(rec[k]) !== JSON.stringify(v)) {
      rec[k] = clone(v);
      assignNestedIds(`${arrayGp}/*`, rec, rec.id ?? at, at);
      changes.push({ pointer: `${at}/${k}`, value: v, source: f.source, asOf: f.asOf, policy: whoMayFill(fields[nestedGp], nestedGp), note: "patched existing record" });
    }
  }
}

/** A line the list already has (by identity) is patched; a new one is appended; lines not named are kept. */
function mergeNested(arrayGp, list, items, f, tag, at, parent) {
  const idKey = IDENTITY[arrayGp];
  for (const item of items) {
    const index = list.findIndex((line) => norm(line[idKey]) !== "" && norm(line[idKey]) === norm(item[idKey]));
    if (index >= 0) { patchRecord(arrayGp, list[index], item, f, tag, `${at}/${index}`); continue; }
    list.push(newRecord(arrayGp, item, parent, `${at}/${list.length}`));
    for (const [k, v] of Object.entries(item)) {
      changes.push({ pointer: `${at}/${list.length - 1}/${k}`, value: v, source: f.source, asOf: f.asOf, policy: whoMayFill(fields[`${arrayGp}/*/${k}`], `${arrayGp}/*/${k}`), note: "new record" });
    }
  }
}

for (const [n, f] of (findings ?? []).entries()) {
  const tag = `finding ${n + 1} (${f.pointer})`;
  if (!["set", "add"].includes(f.op) || typeof f.pointer !== "string") { errors.push(`${tag}: op must be set or add, with a pointer`); continue; }
  const before = errors.length;
  f.value = resolveRefs(f.value, tag);
  if (errors.length > before) continue;

  if (f.op === "set") {
    const gp = generic(f.pointer);
    if (Array.isArray(f.value) && f.value.some((item) => item && typeof item === "object")) {
      errors.push(`${tag}: a list of records is written with add, one record per finding, so each gets its id`);
      continue;
    }
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
  const idKey = IDENTITY[arrayGp];
  const fixed = FIXED[arrayGp];
  // In a fixed collection the identity key selects the record; it is not a value being written.
  const written = fixed && idKey ? Object.fromEntries(Object.entries(f.value).filter(([k]) => k !== idKey)) : f.value;
  checkTree(`${arrayGp}/*`, written, f, `${f.pointer}/-`);
  if (errors.length > before) continue;
  const existingIndex = idKey ? arr.value.findIndex((r) => norm(r[idKey]) !== "" && norm(r[idKey]) === norm(f.value[idKey])) : -1;
  if (fixed && existingIndex < 0) { errors.push(`${tag}: ${fixed}; ${JSON.stringify(f.value[idKey] ?? null)} is not one of them`); continue; }
  if (existingIndex >= 0) { // patch in place, keeping the id
    patchRecord(arrayGp, arr.value[existingIndex], f.value, f, tag, `${f.pointer}/${existingIndex}`);
  } else {
    // A nested collection's records are keyed by their parent record too (its id, or else where it sits).
    const parentPointer = arrayGp.includes("*") ? f.pointer.slice(0, f.pointer.lastIndexOf("/")) : null;
    const parent = parentPointer === null ? null : (getAt(parentPointer).value?.id ?? parentPointer);
    arr.value.push(newRecord(arrayGp, f.value, parent, `${f.pointer}/${arr.value.length}`));
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
  for (const m of minted) {
    changes.push({ pointer: m.pointer, value: m.value, source: "deterministic id for a referenced consumption row", asOf: "-", policy: "system", note: "system id minted" });
  }
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

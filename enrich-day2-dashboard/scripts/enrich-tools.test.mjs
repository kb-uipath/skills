// node --test scripts/enrich-tools.test.mjs
// Self-contained: a tiny field-instructions fixture stands in for the app's 385-field contract.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const here = dirname(fileURLToPath(import.meta.url));
const dir = mkdtempSync(join(tmpdir(), "enrich-tools-"));

const f = (type, writePolicy, extra = {}) => ({ type, nullable: false, requirement: "optional", writePolicy, uiVisibility: "editable", emptyValue: type === "array" ? [] : "", ...extra });
const instructions = {
  targetSchemaVersion: "1.10",
  fields: {
    "/schemaVersion": f("string", "constant", { requirement: "block" }),
    "/reviewTier": f("string", "attestation_allowed", { requirement: "block", allowedValues: ["Tier A", "Tier B"] }),
    "/renewalDate": f("string", "evidence_required", { requirement: "block", format: "YYYY-MM-DD" }),
    "/background": f("object", "evidence_required"),
    "/background/accountStrategy": f("string", "human_only"),
    "/background/region": f("string", "evidence_required"),
    "/risks": f("array", "evidence_required"),
    "/risks/*": f("object", "evidence_required"),
    "/risks/*/id": f("string", "system_managed"),
    "/risks/*/risk": f("string", "evidence_required", { requirement: "block" }),
    "/risks/*/severity": f("string", "attestation_allowed", { allowedValues: ["High", "Medium", "Low"] }),
    "/risks/*/owner": f("string", "evidence_required"),
    "/pipelineOpportunities": f("array", "evidence_required"),
    "/pipelineOpportunities/*": f("object", "evidence_required"),
    "/pipelineOpportunities/*/name": f("string", "evidence_required", { requirement: "block", constraints: ["Maximum 20 Unicode characters.", "Single line.", "Longest token at most 8 characters."] }),
    "/pipelineOpportunities/*/owner": f("string", "human_only", { requirement: "block" }),
    // Legacy-only: drawn by the slides, but "approved legacy content only" and not editable in the UI.
    "/goals": f("array", "evidence_required", { requirement: "not_used", uiVisibility: "guide_only" }),
    "/goals/*": f("object", "evidence_required", { requirement: "not_used", uiVisibility: "guide_only" }),
    "/goals/*/text": f("string", "evidence_required", { requirement: "not_used", uiVisibility: "guide_only" }),
    // The one not_used field the UI does edit.
    "/relationships": f("array", "evidence_required", { requirement: "not_used" }),
    "/relationships/*": f("object", "evidence_required", { requirement: "not_used" }),
    "/relationships/*/customerName": f("string", "evidence_required", { requirement: "not_used" }),
  },
};
const baseline = { schemaVersion: "1.10", reviewTier: "", renewalDate: "", background: { accountStrategy: "", region: "" }, risks: [], pipelineOpportunities: [], goals: [], relationships: [] };
const write = (name, obj) => { const p = join(dir, name); writeFileSync(p, JSON.stringify(obj, null, 2)); return p; };
const instr = write("instructions.json", instructions);
const base = write("baseline.json", baseline);
const run = (script, ...a) => spawnSync(process.execPath, [join(here, script), ...a], { encoding: "utf8" });
const apply = (findings, extra = []) => {
  const out = join(dir, `out-${Math.random().toString(36).slice(2)}.json`);
  const r = run("apply-findings.mjs", base, write("findings.json", { findings }), "--instructions", instr, "--out", out, ...extra);
  return { ...r, doc: r.status === 0 ? JSON.parse(readFileSync(out, "utf8")) : null, out };
};
const ok = { source: "Salesforce Account, queried", asOf: "2026-10-06" };

test("gap inventory sorts every empty field by who may fill it and flags the blockers", () => {
  const r = run("gap-inventory.mjs", base, "--instructions", instr, "--json");
  assert.equal(r.status, 0, r.stderr);
  const rows = JSON.parse(r.stdout);
  const by = (p) => rows.find((x) => x.generic === p);
  assert.equal(by("/reviewTier").who, "attest");
  assert.equal(by("/reviewTier").blocks, true);
  assert.equal(by("/background/accountStrategy").who, "human");
  assert.equal(by("/background/region").who, "evidence");
  assert.equal(by("/risks").kind, "no records");
  assert.equal(by("/schemaVersion"), undefined, "constant fields are not gaps to fill");
  assert.deepEqual(by("/pipelineOpportunities").recordGating, ["human: owner"], "an empty collection says which record fields a person must supply");
});

test("evidence fields take a value with a source and a date", () => {
  const r = apply([{ op: "set", pointer: "/background/region", value: "AMER Public Sector", ...ok }]);
  assert.equal(r.status, 0, r.stderr);
  assert.equal(r.doc.background.region, "AMER Public Sector");
  assert.match(r.stdout, /\| \/background\/region \|/);
});

test("a missing source or date refuses the run and writes nothing", () => {
  const r = apply([{ op: "set", pointer: "/background/region", value: "AMER", source: "x" }]);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /asOf must be YYYY-MM-DD/);
  assert.equal(r.doc, null);
});

test("human_only needs a human author; system-managed and constant fields are never written", () => {
  const refused = apply([{ op: "set", pointer: "/background/accountStrategy", value: "Grow it", ...ok }]);
  assert.equal(refused.status, 1);
  assert.match(refused.stderr, /human_only/);
  const accepted = apply([{ op: "set", pointer: "/background/accountStrategy", value: "Grow it", humanAuthored: true, attestedBy: "Keith Born (chat 2026-10-06)", ...ok }]);
  assert.equal(accepted.status, 0, accepted.stderr);
  assert.equal(accepted.doc.background.accountStrategy, "Grow it");
  assert.match(apply([{ op: "set", pointer: "/schemaVersion", value: "1.11", ...ok }]).stderr, /never written/);
});

test("attestation fields need a named person and an exact enum value", () => {
  assert.match(apply([{ op: "set", pointer: "/reviewTier", value: "Tier B", ...ok }]).stderr, /attestedBy/);
  assert.match(apply([{ op: "set", pointer: "/reviewTier", value: "tier b", attestedBy: "Keith Born", ...ok }]).stderr, /not in \[Tier A, Tier B\]/);
  assert.equal(apply([{ op: "set", pointer: "/reviewTier", value: "Tier B", attestedBy: "Keith Born (chat)", ...ok }]).doc.reviewTier, "Tier B");
});

test("placeholders and badly formed dates are refused", () => {
  assert.match(apply([{ op: "set", pointer: "/background/region", value: "TBD", ...ok }]).stderr, /placeholder/);
  assert.match(apply([{ op: "set", pointer: "/renewalDate", value: "27 Jul 2027", ...ok }]).stderr, /YYYY-MM-DD/);
});

test("a new record gets a fresh id and the documented empties; the same identity patches and keeps its id", () => {
  const first = apply([{ op: "add", pointer: "/risks", value: { risk: "Firewall not open", owner: "Alex Example" }, ...ok }]);
  assert.equal(first.status, 0, first.stderr);
  const rec = first.doc.risks[0];
  assert.match(rec.id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/, "a v4-shaped UUID");
  const again = apply([{ op: "add", pointer: "/risks", value: { risk: "Firewall not open", owner: "Alex Example" }, ...ok }]);
  assert.equal(again.doc.risks[0].id, rec.id, "the same finding gets the same id on a rebuild");
  assert.equal(rec.severity, "", "unstated judgment fields stay empty");
  // Re-run against the output: same risk text, one more field.
  const out2 = join(dir, "second.json");
  writeFileSync(join(dir, "f2.json"), JSON.stringify({ findings: [{ op: "add", pointer: "/risks", value: { risk: "firewall not open", severity: "High" }, attestedBy: "Keith Born (status 2026-10-02)", ...ok }] }));
  const r2 = run("apply-findings.mjs", first.out, join(dir, "f2.json"), "--instructions", instr, "--out", out2);
  assert.equal(r2.status, 0, r2.stderr);
  const doc2 = JSON.parse(readFileSync(out2, "utf8"));
  assert.equal(doc2.risks.length, 1, "no duplicate record");
  assert.equal(doc2.risks[0].id, rec.id, "the existing id is preserved");
  assert.equal(doc2.risks[0].severity, "High");
});

test("ids cannot be supplied, and a record's human_only fields still need a human author", () => {
  assert.match(apply([{ op: "add", pointer: "/risks", value: { risk: "x", id: "abc" }, ...ok }]).stderr, /ids are system-managed/);
  assert.match(apply([{ op: "add", pointer: "/pipelineOpportunities", value: { name: "Acme Phase 2", owner: "Pat Sample" }, ...ok }]).stderr, /human_only/);
  assert.equal(apply([{ op: "add", pointer: "/pipelineOpportunities", value: { name: "Acme Phase 2" }, ...ok }]).status, 0);
});

test("the descriptors' length limits are enforced", () => {
  const add = (name) => apply([{ op: "add", pointer: "/pipelineOpportunities", value: { name }, ...ok }]);
  assert.match(add("A name that is far too long for the table").stderr, /the limit is 20/);
  assert.match(add("Supercalifragilistic").stderr, /longer than 8/);
  assert.equal(add("Acme Phase 2").status, 0);
});

test("overwriting a non-empty value needs a stated reason", () => {
  const seeded = write("seeded.json", { ...baseline, background: { accountStrategy: "", region: "AMER East" } });
  const call = (extra) => run("apply-findings.mjs", seeded, write("f3.json", { findings: [{ op: "set", pointer: "/background/region", value: "AMER West", ...ok, ...extra }] }), "--instructions", instr, "--dry-run");
  assert.match(call({}).stderr, /supersedes/);
  assert.equal(call({ supersedes: "Salesforce region field, newer" }).status, 0);
});

test("approved-content-only not_used fields need a person; the editable not_used field (relationships) stays fillable", () => {
  const rows = JSON.parse(run("gap-inventory.mjs", base, "--instructions", instr, "--json").stdout);
  assert.equal(rows.find((r) => r.generic === "/goals").who, "human", "goals take approved legacy content only");
  assert.equal(rows.find((r) => r.generic === "/relationships").who, "evidence");
  assert.match(apply([{ op: "add", pointer: "/goals", value: { text: "Grow ARR" }, ...ok }]).stderr, /human_only/);
  const approved = apply([{ op: "add", pointer: "/goals", value: { text: "Grow ARR" }, humanAuthored: true, attestedBy: "Keith Born (chat)", ...ok }]);
  assert.equal(approved.status, 0, approved.stderr);
  const added = apply([{ op: "add", pointer: "/relationships", value: { customerName: "Jordan Sample" }, ...ok }]);
  assert.equal(added.status, 0, added.stderr);
  assert.equal(added.doc.relationships[0].customerName, "Jordan Sample");
});

test("one refusal aborts the whole run", () => {
  const r = apply([
    { op: "set", pointer: "/background/region", value: "AMER", ...ok },
    { op: "set", pointer: "/background/accountStrategy", value: "x", ...ok },
  ]);
  assert.equal(r.status, 1);
  assert.equal(r.doc, null);
});

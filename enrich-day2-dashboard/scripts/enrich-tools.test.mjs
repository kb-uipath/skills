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

// --- Schema 1.12 (the v7 Snapshot / Renewal Test / Strategic Initiatives tabs) ---------------------
const v7 = {
  targetSchemaVersion: "1.12",
  fields: {
    "/snapshot": f("object", "evidence_required"),
    "/snapshot/topPursuitIds": f("array", "attestation_allowed", { constraints: ["At most three ids; each must match an existing /pipelineOpportunities/*/id."] }),
    "/snapshot/topPursuitIds/*": f("string", "attestation_allowed", { format: "uuid" }),
    "/snapshot/pursuits": f("array", "evidence_required"),
    "/snapshot/pursuits/*": f("object", "evidence_required"),
    "/snapshot/pursuits/*/id": f("string", "system_managed", { format: "uuid" }),
    "/snapshot/pursuits/*/opportunityId": f("string", "system_managed", { format: "uuid" }),
    "/snapshot/pursuits/*/cardStatus": f("string", "attestation_allowed", { allowedValues: ["On track", "At risk", "Blocked", ""] }),
    "/snapshot/pursuits/*/draw": f("array", "evidence_required"),
    "/snapshot/pursuits/*/draw/*": f("object", "evidence_required"),
    "/snapshot/pursuits/*/draw/*/id": f("string", "system_managed", { format: "uuid" }),
    "/snapshot/pursuits/*/draw/*/rowId": f("string", "system_managed", { format: "uuid" }),
    "/snapshot/pursuits/*/draw/*/units": f("number", "evidence_required", { nullable: true, emptyValue: null }),
    "/renewalTest": f("object", "evidence_required"),
    "/renewalTest/healthyAtPercent": f("number", "human_only", { nullable: true, emptyValue: null }),
    "/renewalTest/rows": f("array", "evidence_required"),
    "/renewalTest/rows/*": f("object", "evidence_required"),
    "/renewalTest/rows/*/id": f("string", "system_managed", { format: "uuid" }),
    "/renewalTest/rows/*/rowId": f("string", "system_managed", { format: "uuid" }),
    "/renewalTest/rows/*/pipelineDriver": f("string", "evidence_required"),
    "/renewalTest/rows/*/demand12MoUnits": f("number", "evidence_required", { nullable: true, emptyValue: null }),
    "/strategicInitiatives": f("array", "evidence_required"),
    "/strategicInitiatives/*": f("object", "evidence_required"),
    "/strategicInitiatives/*/initiative": f("string", "system_managed", { allowedValues: ["agentification", "codingAgents", "orchestration"] }),
    "/strategicInitiatives/*/goal6Mo": f("string", "evidence_required"),
    "/strategicInitiatives/*/status": f("string", "attestation_allowed", { allowedValues: ["On track", "At risk", "Not started", ""] }),
    "/pipelineOpportunities": f("array", "evidence_required"),
    "/pipelineOpportunities/*": f("object", "evidence_required"),
    "/pipelineOpportunities/*/key": f("string", "evidence_required"),
  },
};
const OPP = "11111111-1111-4111-8111-000000000001";
const v7Baseline = {
  schemaVersion: "1.12",
  consumptionPlan: { groups: [
    { element: "Consumables", rows: [{ offering: "AI Units" }] },
    { element: "Robots", rows: [{ id: "22222222-2222-4222-8222-000000000002", offering: "Unattended Robot" }] },
  ] },
  pipelineOpportunities: [{ id: OPP, key: "OPP-1" }],
  snapshot: { topPursuitIds: [], pursuits: [] },
  renewalTest: { healthyAtPercent: null, rows: [] },
  strategicInitiatives: [{ initiative: "agentification", goal6Mo: "", status: "" }, { initiative: "codingAgents", goal6Mo: "", status: "" }],
};
const v7Instr = write("v7-instructions.json", v7);
const v7Base = write("v7-baseline.json", v7Baseline);
const applyV7 = (findings, basePath = v7Base) => {
  const out = join(dir, `v7-${Math.random().toString(36).slice(2)}.json`);
  const r = run("apply-findings.mjs", basePath, write("v7-findings.json", { findings }), "--instructions", v7Instr, "--out", out);
  return { ...r, doc: r.status === 0 ? JSON.parse(readFileSync(out, "utf8")) : null };
};
// Two pursuits already on the Snapshot; the second has a draw line the app added.
const OPP2 = "11111111-1111-4111-8111-000000000002";
const ROBOT = "22222222-2222-4222-8222-000000000002";
const APP_LINE = "33333333-3333-4333-8333-000000000003";
const v7Pursuits = write("v7-pursuits.json", {
  ...v7Baseline,
  pipelineOpportunities: [{ id: OPP, key: "OPP-1" }, { id: OPP2, key: "OPP-2" }],
  snapshot: { topPursuitIds: [], pursuits: [
    { id: "44444444-4444-4444-8444-000000000001", opportunityId: OPP, cardStatus: "", draw: [] },
    { id: "44444444-4444-4444-8444-000000000002", opportunityId: OPP2, cardStatus: "", draw: [{ id: APP_LINE, rowId: ROBOT, units: 5 }] },
  ] },
});

test("v7: a ref:row resolves to the row's id, minting a deterministic id for a row that has none", () => {
  const finding = { op: "add", pointer: "/renewalTest/rows", value: { rowId: "ref:row:ai units", pipelineDriver: "Claims extraction (Q3)", demand12MoUnits: 2400000 }, ...ok };
  const first = applyV7([finding]);
  assert.equal(first.status, 0, first.stderr);
  const minted = first.doc.consumptionPlan.groups[0].rows[0].id;
  assert.match(minted, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.equal(first.doc.renewalTest.rows[0].rowId, minted);
  assert.match(first.stdout, /system id minted/);
  assert.equal(applyV7([finding]).doc.consumptionPlan.groups[0].rows[0].id, minted, "the same row gets the same id on a rebuild");
  assert.equal(first.doc.consumptionPlan.groups[1].rows[0].id, "22222222-2222-4222-8222-000000000002", "an existing id is kept");
});

test("v7: a ref that names nothing, or names two rows, refuses the run", () => {
  assert.match(applyV7([{ op: "add", pointer: "/renewalTest/rows", value: { rowId: "ref:row:Nope", demand12MoUnits: 1 }, ...ok }]).stderr, /no consumption row/);
  assert.match(applyV7([{ op: "add", pointer: "/snapshot/pursuits", value: { opportunityId: "ref:opportunity:OPP-9" }, ...ok }]).stderr, /no pipeline opportunity/);
});

test("v7: pursuit card details key to the opportunity and give nested draws stable ids", () => {
  const r = applyV7([{ op: "add", pointer: "/snapshot/pursuits", value: { opportunityId: "ref:opportunity:opp-1", draw: [{ rowId: "ref:row:Unattended Robot", units: 20 }] }, ...ok }]);
  assert.equal(r.status, 0, r.stderr);
  const pursuit = r.doc.snapshot.pursuits[0];
  assert.equal(pursuit.opportunityId, OPP);
  assert.equal(pursuit.draw[0].rowId, "22222222-2222-4222-8222-000000000002");
  assert.match(pursuit.draw[0].id, /^[0-9a-f-]{36}$/);
});

test("v7: draw lines on the same row in two pursuits get different ids, stable on a rebuild", () => {
  const findings = [
    { op: "add", pointer: "/snapshot/pursuits/0/draw", value: { rowId: "ref:row:AI Units", units: 10 }, ...ok },
    { op: "add", pointer: "/snapshot/pursuits/1/draw", value: { rowId: "ref:row:AI Units", units: 7 }, ...ok },
  ];
  const r = applyV7(findings, v7Pursuits);
  assert.equal(r.status, 0, r.stderr);
  const [first, second] = r.doc.snapshot.pursuits;
  const aiUnits = r.doc.consumptionPlan.groups[0].rows[0].id;
  assert.equal(first.draw[0].rowId, aiUnits);
  assert.equal(second.draw[1].rowId, aiUnits);
  assert.notEqual(first.draw[0].id, second.draw[1].id);
  assert.deepEqual(applyV7(findings, v7Pursuits).doc.snapshot.pursuits.map((p) => p.draw.map((line) => line.id)),
    r.doc.snapshot.pursuits.map((p) => p.draw.map((line) => line.id)), "a rebuild gives the same ids");
  assert.match(applyV7([{ op: "add", pointer: "/snapshot/pursuits", value: { opportunityId: "ref:opportunity:OPP-1", draw: [
    { rowId: "ref:row:AI Units", units: 1 }, { rowId: "ref:row:AI Units", units: 2 },
  ] }, ...ok }]).stderr, /same rowId/);
});

test("v7: patching a pursuit's draw merges lines by row and keeps the lines the app added", () => {
  const added = applyV7([{ op: "add", pointer: "/snapshot/pursuits", value: { opportunityId: "ref:opportunity:OPP-2", draw: [{ rowId: "ref:row:AI Units", units: 7 }] }, ...ok }], v7Pursuits);
  assert.equal(added.status, 0, added.stderr);
  const draw = added.doc.snapshot.pursuits[1].draw;
  assert.deepEqual(draw.map((line) => line.rowId), [ROBOT, added.doc.consumptionPlan.groups[0].rows[0].id]);
  assert.deepEqual(draw[0], { id: APP_LINE, rowId: ROBOT, units: 5 });

  const changeUnits = { op: "add", pointer: "/snapshot/pursuits", value: { opportunityId: "ref:opportunity:OPP-2", draw: [{ rowId: "ref:row:Unattended Robot", units: 9 }] }, ...ok };
  assert.match(applyV7([changeUnits], v7Pursuits).stderr, /draw\/0\/units already has a value/);
  const superseded = applyV7([{ ...changeUnits, supersedes: "The Q3 forecast replaces the August estimate" }], v7Pursuits);
  assert.deepEqual(superseded.doc.snapshot.pursuits[1].draw, [{ id: APP_LINE, rowId: ROBOT, units: 9 }]);
});

test("v7: a resolved id goes only into a reference field of its own kind, never into an id", () => {
  const attested = { attestedBy: "Account executive (call 2026-10-01)", ...ok };
  assert.match(applyV7([{ op: "set", pointer: "/snapshot/pursuits/0/id", value: "ref:row:Unattended Robot", supersedes: "x", ...ok }], v7Pursuits).stderr,
    /pursuits\/0\/id: holds a ref:row id/);
  assert.match(applyV7([{ op: "add", pointer: "/snapshot/pursuits", value: { opportunityId: "ref:row:Unattended Robot" }, ...ok }]).stderr, /takes ref:opportunity/);
  assert.match(applyV7([{ op: "add", pointer: "/renewalTest/rows", value: { rowId: "ref:opportunity:OPP-1", demand12MoUnits: 1 }, ...ok }]).stderr, /takes ref:row/);
  assert.match(applyV7([{ op: "set", pointer: "/snapshot/topPursuitIds", value: ["ref:row:Unattended Robot"], ...attested }]).stderr, /takes ref:opportunity/);
  assert.match(applyV7([{ op: "set", pointer: "/snapshot/topPursuitIds", value: [ROBOT], ...attested }]).stderr, /names no pipeline opportunity/);
  assert.deepEqual(applyV7([{ op: "set", pointer: "/snapshot/topPursuitIds", value: ["ref:opportunity:OPP-1"], ...attested }]).doc.snapshot.topPursuitIds, [OPP]);
});

test("set writes a leaf or a list of strings; records, and the ids inside them, go through add", () => {
  assert.match(applyV7([{ op: "set", pointer: "/snapshot/pursuits/1/draw", value: [{ rowId: "ref:row:AI Units", units: 1 }], supersedes: "x", ...ok }], v7Pursuits).stderr,
    /a list of records is written with add/);
  assert.match(applyV7([{ op: "add", pointer: "/snapshot/pursuits", value: { opportunityId: "ref:opportunity:OPP-1", draw: [{ id: APP_LINE, rowId: "ref:row:AI Units", units: 1 }] }, ...ok }]).stderr,
    /draw\/0\/id: ids are system-managed/);
});

test("v7: the five initiatives are updated in place by key and never added", () => {
  const patched = applyV7([{ op: "add", pointer: "/strategicInitiatives", value: { initiative: "codingAgents", goal6Mo: "Three developers shipping" }, ...ok }]);
  assert.equal(patched.status, 0, patched.stderr);
  assert.equal(patched.doc.strategicInitiatives.length, 2);
  assert.equal(patched.doc.strategicInitiatives[1].goal6Mo, "Three developers shipping");
  assert.match(applyV7([{ op: "add", pointer: "/strategicInitiatives", value: { initiative: "quantum", goal6Mo: "x" }, ...ok }]).stderr,
    /five initiatives are fixed; "quantum" is not one of them \(agentification, codingAgents, orchestration\)/);
});

test("v7: a fixed initiative missing from a hand-authored baseline is named as missing, not as unknown", () => {
  const r = applyV7([{ op: "add", pointer: "/strategicInitiatives", value: { initiative: "orchestration", goal6Mo: "x" }, ...ok }]);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /has no "orchestration" row/);
  assert.doesNotMatch(r.stderr, /not one of them/);
});

test("v7: the top pursuits take at most three ids, as the guide says", () => {
  const opps = [1, 2, 3, 4].map((n) => ({ id: `11111111-1111-4111-8111-00000000000${n}`, key: `OPP-${n}` }));
  const four = write("v7-four.json", { ...v7Baseline, pipelineOpportunities: opps, snapshot: { topPursuitIds: opps.slice(0, 3).map((o) => o.id), pursuits: [] } });
  const attested = { attestedBy: "Account executive (call 2026-10-01)", supersedes: "The team re-ranked its pursuits", ...ok };
  const refs = (n) => opps.slice(0, n).map((o) => `ref:opportunity:${o.key}`);
  assert.match(applyV7([{ op: "set", pointer: "/snapshot/topPursuitIds", value: refs(4), ...attested }], four).stderr, /4 items; at most 3/);
  assert.match(applyV7([{ op: "add", pointer: "/snapshot/topPursuitIds", value: "ref:opportunity:OPP-4", ...attested }], four).stderr, /already holds 3; at most 3/);
  assert.deepEqual(applyV7([{ op: "set", pointer: "/snapshot/topPursuitIds", value: refs(3).reverse(), ...attested }], four).doc.snapshot.topPursuitIds,
    opps.slice(0, 3).map((o) => o.id).reverse());
});

test("v7: the healthy threshold is the account team's to set", () => {
  assert.match(applyV7([{ op: "set", pointer: "/renewalTest/healthyAtPercent", value: 70, ...ok }]).stderr, /human_only/);
  const set = applyV7([{ op: "set", pointer: "/renewalTest/healthyAtPercent", value: 70, humanAuthored: true, attestedBy: "Account team (review 2026-10-01)", ...ok }]);
  assert.equal(set.doc.renewalTest.healthyAtPercent, 70);
});

test("v7: the gap inventory groups gaps under the v7 tabs", () => {
  const rows = JSON.parse(run("gap-inventory.mjs", v7Base, "--instructions", v7Instr, "--json").stdout);
  assert.equal(rows.find((x) => x.generic === "/renewalTest/healthyAtPercent").tab, "Renewal Test");
  assert.equal(rows.find((x) => x.generic === "/snapshot/topPursuitIds").tab, "Snapshot");
});

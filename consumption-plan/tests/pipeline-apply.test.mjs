// node --test consumption-plan/tests/pipeline-apply.test.mjs
// The findings a plan's pipeline produces go through enrich-day2-dashboard's apply-findings.mjs, the script that
// enforces the app's write policy and resolves the ref: tokens, so a refusal there fails here.
// A small instructions file stands in for the app's field contract, with the descriptors that matter to these fields.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import * as pipeline from "../scripts/pipeline.mjs";
import { toDay2 } from "../scripts/to-day2.mjs";
import { gapList } from "../scripts/gap-list.mjs";

const { numberFindings, otherActivityFindings } = pipeline;
const here = dirname(fileURLToPath(import.meta.url));
const applyScript = join(here, "..", "..", "enrich-day2-dashboard", "scripts", "apply-findings.mjs");
const pipelineScript = join(here, "..", "scripts", "pipeline.mjs");
const dir = mkdtempSync(join(tmpdir(), "pipeline-apply-"));
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

const f = (type, writePolicy, extra = {}) => ({ type, nullable: false, requirement: "optional", writePolicy, uiVisibility: "editable", emptyValue: type === "array" ? [] : "", ...extra });
const nullableNumber = (writePolicy = "evidence_required") => f("number", writePolicy, { nullable: true, emptyValue: null });
const instructions = {
  targetSchemaVersion: "1.12",
  fields: {
    "/renewalDate": f("string", "evidence_required", { requirement: "block", format: "YYYY-MM-DD" }),
    "/snapshot": f("object", "evidence_required"),
    "/snapshot/contractStartDate": f("string", "evidence_required", { format: "YYYY-MM-DD" }),
    "/snapshot/otherPipelineActivityUsd": nullableNumber(),
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
    "/snapshot/pursuits/*/draw/*/units": nullableNumber(),
    "/renewalTest": f("object", "evidence_required"),
    "/renewalTest/rows": f("array", "evidence_required"),
    "/renewalTest/rows/*": f("object", "evidence_required"),
    "/renewalTest/rows/*/id": f("string", "system_managed", { format: "uuid" }),
    "/renewalTest/rows/*/rowId": f("string", "system_managed", { format: "uuid" }),
    "/renewalTest/rows/*/pipelineDriver": f("string", "evidence_required"),
    "/renewalTest/rows/*/demand6MoUnits": nullableNumber(),
    "/renewalTest/rows/*/demand12MoUnits": nullableNumber(),
    "/renewalTest/rows/*/confidence": f("string", "attestation_allowed", { allowedValues: ["High", "Med", "Low", ""] }),
    "/pipelineOpportunities": f("array", "evidence_required"),
    "/pipelineOpportunities/*": f("object", "evidence_required"),
    "/pipelineOpportunities/*/id": f("string", "system_managed", { format: "uuid" }),
    "/pipelineOpportunities/*/key": f("string", "evidence_required", { requirement: "block", constraints: ["Maximum 80 Unicode characters."] }),
    "/pipelineOpportunities/*/name": f("string", "evidence_required", { requirement: "block", constraints: ["Maximum 48 Unicode characters.", "Single line.", "Longest token at most 17 characters."] }),
    "/pipelineOpportunities/*/stage": f("string", "evidence_required", { requirement: "block", constraints: ["Maximum 20 Unicode characters.", "Single line.", "Longest token at most 14 characters."] }),
    "/pipelineOpportunities/*/status": f("string", "evidence_required", { requirement: "block", allowedValues: ["Open", "On Hold", "Closed Won", "Closed Lost", ""] }),
    "/pipelineOpportunities/*/estimatedIarrUsd": nullableNumber(),
    "/pipelineOpportunities/*/products": f("array", "evidence_required"),
    "/pipelineOpportunities/*/products/*": f("string", "evidence_required"),
    "/pipelineOpportunities/*/consumptionRowIds": f("array", "evidence_required"),
    "/pipelineOpportunities/*/consumptionRowIds/*": f("string", "evidence_required", { format: "UUID" }),
    "/pipelineOpportunities/*/projectedConsumption": f("string", "evidence_required", { requirement: "block", constraints: ["Maximum 64 Unicode characters.", "Single line.", "Longest token at most 20 characters."] }),
    "/pipelineOpportunities/*/owner": f("string", "human_only", { requirement: "block" }),
    "/pipelineOpportunities/*/nextGate": f("string", "human_only", { requirement: "block" }),
  },
};
const instructionsPath = join(dir, "instructions.json");
writeFileSync(instructionsPath, JSON.stringify(instructions));

const plan = () => JSON.parse(readFileSync(join(here, "fixtures", "illustrative-pipeline-plan.json"), "utf8"));
/** The fixture's opportunity whose one line, on the AI Units row, decodes to no units. */
const UNSIZED = "006EXAMPLE0000007";
/** The fixture without that opportunity, so every line on a consumed row is sized and every figure is known. */
const sizedPlan = () => {
  const draft = plan();
  draft.pipeline.opportunities = draft.pipeline.opportunities.filter(({ salesforceId }) => salesforceId !== UNSIZED);
  return draft;
};
const blank = () => ({
  schemaVersion: "1.12", customerName: "", renewalDate: "", renewalEconomics: { currentArrUsd: null },
  consumptionPlan: { asOf: "", forecastPeriod: "", groups: [], primaryUseCases: [] },
  snapshot: { contractStartDate: "", otherPipelineActivityUsd: null, topPursuitIds: [], pursuits: [] },
  pipelineOpportunities: [],
  renewalTest: { healthyAtPercent: null, rows: [] },
});
let counter = 0;
const write = (name, value) => {
  const path = join(dir, `${++counter}-${name}`);
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
  return path;
};

/** Applies findings to a document with apply-findings.mjs; the result is the document it wrote, or null when it refused. */
function apply(document, findings) {
  const out = join(dir, `out-${++counter}.json`);
  const result = spawnSync(process.execPath, [applyScript, write("document.json", document), write("findings.json", { findings }), "--instructions", instructionsPath, "--out", out], { encoding: "utf8" });
  return { ...result, doc: result.status === 0 ? JSON.parse(readFileSync(out, "utf8")) : null };
}

const rowIds = (document) => document.consumptionPlan.groups.flatMap((group) => group.rows).map((row) => row.id);
const rowId = (document, offering) => document.consumptionPlan.groups.flatMap((group) => group.rows).find((row) => row.offering === offering).id;
const opportunity = (document, key) => document.pipelineOpportunities.find((record) => record.key === key);

/** The plan taken through the merge and the numbers stage. */
function numbersStage(draft = plan(), baseline = blank()) {
  const merged = toDay2(draft, baseline).document;
  const result = numberFindings(draft, merged);
  const applied = apply(merged, result.findings);
  assert.equal(applied.status, 0, applied.stderr);
  return { ...result, merged, document: applied.doc, stdout: applied.stdout };
}

test("a plan's pipeline goes through apply-findings: records, cards and renewal-test rows reference the consumption rows by id, and only a use case draws", () => {
  const draft = plan();
  draft.pipeline.useCases = [useCase({ startDate: undefined })]; // no start date: it draws, and adds no demand
  const { document, conflicts, stdout } = numbersStage(draft);
  assert.deepEqual(conflicts, []);
  assert.equal(document.renewalDate, "2026-12-01");
  assert.equal(document.snapshot.contractStartDate, "2025-12-01");

  assert.deepEqual(document.pipelineOpportunities.map((record) => record.key), [...[1, 2, 3, 6, 7, 8].map((n) => `006EXAMPLE000000${n}`), "invoice-intake-agent"]);
  const known = new Set(rowIds(document));
  assert.equal(known.size, 4, "every plan row was given an id by a reference to it");
  for (const record of document.pipelineOpportunities) {
    assert.match(record.id, UUID);
    assert.equal(record.owner, "", "an owner is the account team's to name");
    assert.equal(record.nextGate, "");
    assert.equal(record.status, "Open");
    for (const id of record.consumptionRowIds) assert.ok(known.has(id), `${record.key}: ${id} is a consumption row`);
  }
  const first = opportunity(document, "006EXAMPLE0000001");
  assert.deepEqual(first.consumptionRowIds, [rowId(document, "AI Units"), rowId(document, "Unattended Robot")]);
  assert.equal(first.estimatedIarrUsd, 120000);
  assert.equal(first.projectedConsumption, "AI Units: 400000 units; Unattended Robot: 20 robots");
  assert.deepEqual(opportunity(document, "006EXAMPLE0000006").consumptionRowIds, [], "an unmapped line references no row");

  assert.deepEqual(document.snapshot.pursuits.map((pursuit) => pursuit.opportunityId), [opportunity(document, "invoice-intake-agent").id], "one card, the use case's: an opportunity's product lines are new entitlement, so no opportunity draws on today's rows");
  const [card] = document.snapshot.pursuits;
  assert.deepEqual(card.draw.map(({ rowId: id, units }) => [id, units]), [[rowId(document, "AI Units"), 200000], [rowId(document, "Unattended Robot"), 4]]);
  assert.equal(card.cardStatus, "", "a card's status is the team's call");
  for (const line of card.draw) assert.match(line.id, UUID);

  assert.deepEqual(document.renewalTest.rows.map((row) => [row.rowId, row.demand6MoUnits, row.demand12MoUnits]), [
    [rowId(document, "AI Units"), null, null], [rowId(document, "Unattended Robot"), 20, 20],
  ], "the unsized line withholds the AI Units demand rather than understating it");
  assert.match(document.renewalTest.rows[0].pipelineDriver, /AI Units Enterprise Agreement \(Dec 26\)/, "and still drives the row");
  assert.equal(document.renewalTest.rows[0].confidence, "", "confidence is the team's call");
  assert.match(stdout, /\| \/renewalTest\/rows\/0\/demand12MoUnits \|/);
});

test("the numbers stage leaves the Snapshot's top pursuits and its other pipeline activity for the next stage", () => {
  const { document } = numbersStage();
  assert.deepEqual(document.snapshot.topPursuitIds, []);
  assert.equal(document.snapshot.otherPipelineActivityUsd, null);
});

test("the final stage sets the other pipeline activity from the cards the app will show", () => {
  const draft = sizedPlan();
  const { document } = numbersStage(draft);
  const { findings, conflicts } = otherActivityFindings(draft, document);
  assert.deepEqual(conflicts, []);
  const applied = apply(document, findings);
  assert.equal(applied.status, 0, applied.stderr);
  assert.equal(applied.doc.snapshot.otherPipelineActivityUsd, 30000, "the app's top three by amount are opportunities 1, 2 and 6; what is left is the beyond-window 10 robots at 3000 each");
});

test("the final stage leaves the other pipeline activity blank while an opportunity off the cards has an unsized line", () => {
  const draft = plan();
  const { document } = numbersStage(draft);
  const { findings, conflicts } = otherActivityFindings(draft, document);
  assert.deepEqual(findings, []);
  assert.equal(conflicts.length, 1);
  assert.match(conflicts[0], /AI Units Enterprise Agreement \(AI Units\)/);
  assert.equal(document.snapshot.otherPipelineActivityUsd, null);
});

test("running the numbers stage again on what it produced finds nothing to change", () => {
  const draft = plan();
  const first = numbersStage(draft);
  draft.pipeline.written = first.written;
  const again = numberFindings(draft, first.document);
  assert.deepEqual(again.findings, []);
  assert.deepEqual(again.conflicts, []);
  assert.deepEqual(again.written, first.written);
});

test("a refresh updates the values the plan wrote, keeps the team's edits, and apply-findings accepts it", () => {
  const draft = sizedPlan();
  const first = numbersStage(draft);
  draft.pipeline.written = first.written;

  // The team re-states one number and rewrites one sizing; Salesforce moves the amount, the stage and a quantity.
  const edited = structuredClone(first.document);
  edited.renewalTest.rows[1].demand12MoUnits = 25;
  opportunity(edited, "006EXAMPLE0000001").estimatedIarrUsd = 118000;
  opportunity(edited, "006EXAMPLE0000002").name = "Team's short name";
  draft.pipeline.opportunities[1].lines[0].units = 1200000;
  draft.pipeline.opportunities[0].stage = "Closing";

  const refresh = numberFindings(draft, edited);
  const refreshed = apply(edited, refresh.findings);
  assert.equal(refreshed.status, 0, refreshed.stderr);
  const document = refreshed.doc;
  assert.equal(document.renewalTest.rows[0].demand12MoUnits, 1600000, "400000 + 1200000: the plan's own figure moved with Salesforce");
  assert.equal(document.renewalTest.rows[1].demand12MoUnits, 25, "the team's figure stands");
  assert.equal(refresh.conflicts.filter((line) => /Unattended Robot/.test(line)).length, 1);
  assert.equal(opportunity(document, "006EXAMPLE0000001").estimatedIarrUsd, 120000, "Salesforce's amount wins");
  assert.equal(opportunity(document, "006EXAMPLE0000001").stage, "Closing", "and its stage");
  assert.equal(opportunity(document, "006EXAMPLE0000002").name, "Team's short name", "a name the team shortened stands");
  assert.equal(refresh.conflicts.filter((line) => /name: kept "Team's short name"/.test(line)).length, 1);
  assert.equal(opportunity(document, "006EXAMPLE0000002").projectedConsumption, "AI Units: 1200000 units");
  assert.deepEqual(document.snapshot.pursuits, [], "the quantity moved the demand and the record, and draws nothing");
  assert.equal(document.pipelineOpportunities.length, 5, "no record was added twice");
});

test("without a record of what the plan wrote, a refresh changes nothing the document already holds", () => {
  const draft = sizedPlan();
  const first = numbersStage(draft);
  draft.pipeline.opportunities[1].lines[0].units = 1200000;
  const refresh = numberFindings(draft, first.document);
  assert.equal(refresh.conflicts.length, 2, refresh.conflicts.join("\n"));
  const refreshed = apply(first.document, refresh.findings);
  assert.equal(refreshed.status, 0, refreshed.stderr);
  assert.equal(refreshed.doc.renewalTest.rows[0].demand12MoUnits, 1400000);
  assert.equal(opportunity(refreshed.doc, "006EXAMPLE0000002").projectedConsumption, "AI Units: 1000000 units");
});

test("a line added to an opportunity after a recorded run refreshes its record and the demand, with nothing reported kept", () => {
  const draft = plan();
  const first = numbersStage(draft);
  draft.pipeline.written = first.written;
  draft.pipeline.opportunities[1].lines.push({ product: "Unattended Robot", productCode: "UIFDUR00000", quantity: 3, units: 3, row: "Unattended Robot" });

  const refresh = numberFindings(draft, first.document);
  assert.deepEqual(refresh.conflicts, [], "the plan wrote the old record, so it may refresh it");
  const refreshed = apply(first.document, refresh.findings);
  assert.equal(refreshed.status, 0, refreshed.stderr);
  const document = refreshed.doc;
  const second = opportunity(document, "006EXAMPLE0000002");
  assert.deepEqual(second.consumptionRowIds, [rowId(document, "AI Units"), rowId(document, "Unattended Robot")]);
  assert.deepEqual(second.products, ["AI Units Bundle 1K", "Unattended Robot"]);
  assert.equal(second.projectedConsumption, "AI Units: 1000000 units; Unattended Robot: 3 robots");
  assert.equal(document.renewalTest.rows[1].demand12MoUnits, 23, "the robot row gained the new line's 3 units");
  assert.match(document.renewalTest.rows[1].pipelineDriver, /AI Units Phase 2/);
  assert.equal(document.pipelineOpportunities.length, 6);
  assert.deepEqual(document.snapshot.pursuits, [], "and no card: an opportunity draws nothing");

  const again = numberFindings({ ...draft, pipeline: { ...draft.pipeline, written: { ...first.written, ...refresh.written } } }, document);
  assert.deepEqual(again.findings, [], "and the refreshed record is what the plan now holds");
  assert.deepEqual(again.conflicts, []);
});

test("an opportunity that leaves the plan after a recorded run is reported, and nothing it put in the document is cleared", () => {
  const draft = sizedPlan();
  const first = numbersStage(draft);
  draft.pipeline.written = first.written;
  draft.pipeline.opportunities.splice(0, 1); // opportunity 1 closes in Salesforce and is dropped from the plan

  const refresh = numberFindings(draft, first.document);
  const gone = refresh.conflicts.filter((line) => line.includes("006EXAMPLE0000001"));
  assert.equal(gone.length, 1);
  assert.match(gone[0], /no longer open in this plan/);
  assert.match(gone[0], /card, draws and demand remain in the document/);
  assert.match(gone[0], /AE confirms its Salesforce status and closes or removes it in the app/);
  assert.equal(refresh.conflicts.filter((line) => /renewalTest row "Unattended Robot"/.test(line)).length, 1, "its robots were the only demand on that row");
  assert.equal(refresh.conflicts.length, 2);
  assert.equal(refresh.conflicts.some((line) => /earlier draw/.test(line)), false, "one line for the opportunity, not another for each draw it wrote");
  assert.equal(refresh.findings.some((finding) => JSON.stringify(finding).includes("006EXAMPLE0000001")), false);

  const refreshed = apply(first.document, refresh.findings);
  assert.equal(refreshed.status, 0, refreshed.stderr);
  const document = refreshed.doc;
  assert.equal(opportunity(document, "006EXAMPLE0000001").status, "Open", "the record stays for the AE to close");
  assert.deepEqual(document.snapshot.pursuits, [], "the first run gave it no card");
  assert.deepEqual(document.renewalTest.rows[1].pipelineDriver, "Example Corp - AI Units and Robot Expansion (Oct 26)");
  assert.deepEqual([document.renewalTest.rows[1].demand6MoUnits, document.renewalTest.rows[1].demand12MoUnits], [20, 20], "the robot figures stand");
  assert.deepEqual([document.renewalTest.rows[0].demand6MoUnits, document.renewalTest.rows[0].demand12MoUnits], [0, 1000000], "a row with other demand is refreshed as usual");
});

/**
 * What the first run left for the sized plan and the use case (starting within six months), then the plan with one
 * change to the use case's robot line; the refresh applied.
 */
function refreshAfterChangingRobotLine(change) {
  const draft = sizedPlan();
  draft.pipeline.useCases = [useCase()];
  const first = numbersStage(draft);
  draft.pipeline.written = first.written;
  change(draft.pipeline.useCases[0].lines[1]);
  const refresh = numberFindings(draft, first.document);
  const refreshed = apply(first.document, refresh.findings);
  assert.equal(refreshed.status, 0, refreshed.stderr);
  return { first, refresh, document: refreshed.doc };
}

const earlierDraw = (conflicts, row) => conflicts.filter((line) => line.includes("(invoice-intake-agent)") && line.includes(`"${row}"`) && /earlier draw/.test(line));
/** The use case's card: the only card, since an opportunity draws nothing. */
const useCaseCard = (document) => document.snapshot.pursuits.find((pursuit) => pursuit.opportunityId === opportunity(document, "invoice-intake-agent").id);

test("a line removed from a use case leaves its draw in the document, reported", () => {
  const draft = sizedPlan();
  draft.pipeline.useCases = [useCase()];
  const first = numbersStage(draft);
  draft.pipeline.written = first.written;
  draft.pipeline.useCases[0].lines.splice(1, 1); // the robot line is removed; the AI Units line stays

  const refresh = numberFindings(draft, first.document);
  assert.equal(earlierDraw(refresh.conflicts, "Unattended Robot").length, 1);
  assert.equal(refresh.conflicts.some((line) => /^Use case invoice-intake-agent is no longer in this plan/.test(line)), false, "it is still in the plan");
  assert.equal(refresh.conflicts.length, 1, "the draw; the robot demand this plan wrote is refreshed without the use case's 4");
  const refreshed = apply(first.document, refresh.findings);
  assert.equal(refreshed.status, 0, refreshed.stderr);
  assert.deepEqual(useCaseCard(refreshed.doc).draw.map(({ units }) => units), [200000, 4], "the earlier draw stands");
  assert.deepEqual(opportunity(refreshed.doc, "invoice-intake-agent").products, ["AI Units"], "while the record follows the lines");
  assert.equal(renewalRow(refreshed.doc, "Unattended Robot").demand12MoUnits, 20);
});

test("a line that became unsized withdraws the draw and the demand this plan wrote, so neither looks known", () => {
  const { refresh, document } = refreshAfterChangingRobotLine((line) => { line.units = null; });
  assert.deepEqual(refresh.conflicts, [], "the line is still on its row, so its draw is not one that left");
  assert.deepEqual(useCaseCard(document).draw.map(({ units }) => units), [200000, null], "the app now withholds the card's Est. rev.");
  assert.deepEqual([renewalRow(document, "Unattended Robot").demand6MoUnits, renewalRow(document, "Unattended Robot").demand12MoUnits], [null, null]);
  assert.match(renewalRow(document, "Unattended Robot").pipelineDriver, /Invoice intake agent/, "the use case still drives the row");
});

test("a line that moved to another row reports the draw it left, and draws on the new row", () => {
  const { refresh, document } = refreshAfterChangingRobotLine((line) => { line.row = "Automation Developer"; });
  assert.equal(earlierDraw(refresh.conflicts, "Unattended Robot").length, 1);
  assert.equal(earlierDraw(refresh.conflicts, "Automation Developer").length, 0, "the new row's draw is a new value, not a departed one");
  assert.deepEqual(useCaseCard(document).draw.map(({ units }) => units), [200000, 4, 4], "the old draw stands beside the new");
  assert.equal(useCaseCard(document).draw[2].rowId, rowId(document, "Automation Developer"));
});

test("a renewal-test row whose only driver has left the window is reported, and its figures stand", () => {
  const draft = sizedPlan();
  const first = numbersStage(draft);
  draft.pipeline.written = first.written;
  draft.pipeline.opportunities[0].closeDate = "2027-10-01"; // still open, but beyond 12 months: the robots stop counting

  const refresh = numberFindings(draft, first.document);
  assert.equal(refresh.conflicts.length, 1, refresh.conflicts.join("\n"));
  assert.deepEqual(refresh.conflicts.flatMap((line) => /renewalTest row "([^"]+)"/.exec(line)?.[1] ?? []), ["Unattended Robot"]);
  assert.equal(refresh.conflicts.some((line) => /now closes/.test(line)), false, "the first run wrote it no draw, so there is none to report");
  assert.equal(refresh.findings.some((finding) => finding.pointer === "/snapshot/pursuits"), false, "and none is drawn");
  assert.equal(refresh.findings.some((finding) => finding.pointer === "/renewalTest/rows" && finding.value.rowId === "ref:row:Unattended Robot"), false);
  const refreshed = apply(first.document, refresh.findings);
  assert.equal(refreshed.status, 0, refreshed.stderr);
  assert.deepEqual(refreshed.doc.renewalTest.rows[1], first.document.renewalTest.rows[1], "the row is as the first run left it");
  assert.deepEqual(refreshed.doc.renewalTest.rows[0].demand12MoUnits, 1000000, "the AI Units row lost the opportunity's 400000");
  assert.deepEqual(refreshed.doc.snapshot.pursuits, []);
});

// --- What the team cleared or deleted after a recorded run ------------------------------------------------

/** Both stages of a first run on the sized plan, applied and recorded: the plan that recorded them, and the document. */
function recordedRun() {
  const draft = sizedPlan();
  const numbers = numbersStage(draft);
  draft.pipeline.written = numbers.written;
  const final = otherActivityFindings(draft, numbers.document);
  const finished = apply(numbers.document, final.findings);
  assert.equal(finished.status, 0, finished.stderr);
  assert.equal(finished.doc.snapshot.otherPipelineActivityUsd, 30000);
  draft.pipeline.written = { ...draft.pipeline.written, ...final.written };
  return { draft, document: finished.doc };
}

/** The refresh's numbers-stage findings applied to the edited document, which must succeed. */
function refreshed(draft, edited) {
  const refresh = numberFindings(draft, edited);
  const applied = apply(edited, refresh.findings);
  assert.equal(applied.status, 0, applied.stderr);
  return { ...refresh, document: applied.doc };
}

test("demand the team cleared after a recorded run stays blank, and a line says so", () => {
  const { draft, document } = recordedRun();
  const edited = structuredClone(document);
  edited.renewalTest.rows[0].demand12MoUnits = null; // AI Units
  const refresh = refreshed(draft, edited);
  assert.deepEqual(refresh.findings, []);
  assert.deepEqual(refresh.conflicts, ['renewalTest row "AI Units" demand12MoUnits: left blank, as the account team cleared it (this plan wrote 1400000); Salesforce opportunities now give 1400000.']);
  assert.equal(refresh.document.renewalTest.rows[0].demand12MoUnits, null);
});

test("a use case's pursuit card the team deleted after a recorded run is not added again, and a line says so", () => {
  const draft = sizedPlan();
  draft.pipeline.useCases = [useCase()];
  const first = numbersStage(draft);
  draft.pipeline.written = first.written;
  const edited = structuredClone(first.document);
  const record = opportunity(edited, "invoice-intake-agent");
  edited.snapshot.pursuits = edited.snapshot.pursuits.filter((pursuit) => pursuit.opportunityId !== record.id);
  const refresh = refreshed(draft, edited);
  assert.deepEqual(refresh.findings, []);
  assert.deepEqual(refresh.conflicts, ['Use case "Invoice intake agent" (invoice-intake-agent): its pursuit card, which this plan added, is no longer in the document, so it is not added again. The AE confirms the removal or adds it back in the app.']);
  assert.deepEqual(refresh.document.snapshot.pursuits, []);
});

test("an opportunity the team deleted after a recorded run is not added again, and a line says so", () => {
  const { draft, document } = recordedRun();
  const edited = structuredClone(document);
  const first = opportunity(edited, "006EXAMPLE0000001");
  edited.pipelineOpportunities = edited.pipelineOpportunities.filter((record) => record !== first);
  const refresh = refreshed(draft, edited);
  assert.deepEqual(refresh.findings, []);
  assert.equal(refresh.conflicts.length, 1, refresh.conflicts.join("\n"));
  assert.match(refresh.conflicts[0], /^Opportunity "Example Corp - AI Units and Robot Expansion" \(006EXAMPLE0000001\): its record, which this plan added, is no longer in the document, so it is not added again;/);
  assert.equal(opportunity(refresh.document, "006EXAMPLE0000001"), undefined);
  assert.equal(refresh.document.pipelineOpportunities.length, 4);
  assert.deepEqual(refresh.document.snapshot.pursuits, [], "it had no card: an opportunity draws nothing");
});

test("other pipeline activity the team cleared after a recorded run stays blank, and a line says so", () => {
  const { draft, document } = recordedRun();
  const edited = structuredClone(document);
  edited.snapshot.otherPipelineActivityUsd = null;
  const refresh = otherActivityFindings(draft, edited);
  assert.deepEqual(refresh.findings, []);
  assert.deepEqual(refresh.conflicts, ["snapshot.otherPipelineActivityUsd: left blank, as the account team cleared it (this plan wrote 30000); Salesforce opportunities now give 30000."]);
});

test("other pipeline activity this plan wrote is cleared when other cards leave an unsized line off them, and a team figure is kept", () => {
  const draft = plan();
  const numbers = numbersStage(draft);
  draft.pipeline.written = numbers.written;

  // The team names opportunities 1, 2 and 7 as its top pursuits, and Step 9.5 runs on the export.
  const picked = structuredClone(numbers.document);
  picked.snapshot.topPursuitIds = ["006EXAMPLE0000001", "006EXAMPLE0000002", UNSIZED].map((key) => opportunity(picked, key).id);
  const first = otherActivityFindings(draft, picked);
  assert.deepEqual(first.conflicts, []);
  const written = apply(picked, first.findings);
  assert.equal(written.status, 0, written.stderr);
  assert.equal(written.doc.snapshot.otherPipelineActivityUsd, 30000, "the beyond-window robots; 7's unsized line is on a card");
  draft.pipeline.written = { ...draft.pipeline.written, ...first.written }; // --record

  // The team goes back to the app's default cards (1, 2 and 6), which leaves 7's unsized line off them.
  const back = structuredClone(written.doc);
  back.snapshot.topPursuitIds = [];
  const rerun = otherActivityFindings(draft, back);
  assert.deepEqual(rerun.findings, [{
    op: "set", pointer: "/snapshot/otherPipelineActivityUsd", value: null, source: "Salesforce Opportunities priced at contracted unit prices", asOf: "2026-08-01",
    supersedes: "refreshed from Salesforce opportunities as of 2026-08-01",
  }], "the figure this plan wrote no longer holds, so it is withdrawn rather than left looking complete");
  assert.deepEqual(rerun.conflicts, ["snapshot.otherPipelineActivityUsd cleared the 30000 this plan wrote earlier: 1 line(s) have no unit volume to value them: Example Corp - AI Units Enterprise Agreement (AI Units)."]);
  assert.equal(rerun.written.otherPipelineActivityUsd, null);
  const cleared = apply(back, rerun.findings);
  assert.equal(cleared.status, 0, cleared.stderr);
  assert.equal(cleared.doc.snapshot.otherPipelineActivityUsd, null);

  // A figure the team entered in the app instead stays, and the line says so.
  const team = structuredClone(back);
  team.snapshot.otherPipelineActivityUsd = 25000;
  const kept = otherActivityFindings(draft, team);
  assert.deepEqual(kept.findings, []);
  assert.deepEqual(kept.conflicts, ["snapshot.otherPipelineActivityUsd not written: 1 line(s) have no unit volume to value them: Example Corp - AI Units Enterprise Agreement (AI Units). The account team's 25000 stays."]);
  assert.equal("otherPipelineActivityUsd" in kept.written, false, "the plan's record of what it wrote stands");
});

// --- An opportunity the team added in the app ------------------------------------------------------------

const TEAM_ID = "55555555-5555-4555-8555-000000000001";
/** A blank baseline holding a record the team added in the app for opportunity 2; the app gives it the key "". */
function baselineWithTeamRecord(key) {
  const baseline = blank();
  baseline.pipelineOpportunities.push({ id: TEAM_ID, key, name: "Example Corp - AI Units Phase 2", stage: "Proposal", status: "Open", estimatedIarrUsd: null, owner: "A. Owner" });
  return baseline;
}
const phaseTwo = (document) => document.pipelineOpportunities.filter((record) => /phase 2/i.test(record.name));

test("an opportunity the team added in the app under its Salesforce name is claimed: the draft holds one record for it", () => {
  const draft = sizedPlan();
  const { document, conflicts, written } = numbersStage(draft, baselineWithTeamRecord(""));
  assert.deepEqual(conflicts, []);
  const records = phaseTwo(document);
  assert.equal(records.length, 1);
  assert.equal(records[0].key, "006EXAMPLE0000002");
  assert.equal(records[0].id, TEAM_ID, "it keeps its id");
  assert.equal(records[0].owner, "A. Owner", "and what the team wrote");
  assert.equal(records[0].estimatedIarrUsd, 100000, "its empty fields are filled from Salesforce");
  assert.equal(document.pipelineOpportunities.length, 5);
  assert.deepEqual(document.snapshot.pursuits, [], "and, as for any opportunity, no card");

  draft.pipeline.written = written;
  assert.deepEqual(numberFindings(draft, document).findings, [], "and the next run finds it by its key");
});

test("an opportunity the team keyed otherwise gets no second record, and the AE is asked to re-key it", () => {
  const { document, conflicts } = numbersStage(sizedPlan(), baselineWithTeamRecord("ai-units-phase-2"));
  assert.deepEqual(phaseTwo(document).map((record) => record.key), ["ai-units-phase-2"]);
  assert.equal(conflicts.length, 1);
  assert.match(conflicts[0], /keyed "ai-units-phase-2", so no second record is added\. The AE changes its key to 006EXAMPLE0000002 in the app/);
});

test("rows that share an offering are referenced by category and resolve to different rows", () => {
  const draft = plan();
  draft.rows.push({
    category: "Platform / Capabilities", product: "AI Units", productCode: "", unit: "units", licensingModel: "", arrUsd: 0, discountPercent: null,
    purchasedQuantity: 500000, consumedQuantity: null, forecastUnits: { q1: null, q2: null, q3: null, q4: null }, notes: "",
  });
  for (const { lines } of draft.pipeline.opportunities) for (const line of lines) if (line.row === "AI Units") line.row = "Consumables|AI Units";
  draft.pipeline.useCases = [useCase({ startDate: undefined, lines: [{ product: "AI Units", units: 200000, row: "Consumables|AI Units" }] })];
  const { document } = numbersStage(draft);
  const [consumables, platform] = document.consumptionPlan.groups.flatMap((group) => group.rows).filter((row) => row.offering === "AI Units");
  assert.notEqual(consumables.id, platform.id);
  assert.equal(document.renewalTest.rows[0].rowId, consumables.id);
  assert.deepEqual(opportunity(document, "006EXAMPLE0000001").consumptionRowIds[0], consumables.id);
  assert.equal(useCaseCard(document).draw[0].rowId, consumables.id, "the use case's draw resolves to the row its line named");
});

test("an unreferenced consumption row is not given an id", () => {
  const { document } = numbersStage();
  const developer = document.consumptionPlan.groups.flatMap((group) => group.rows).find((row) => row.offering === "Automation Developer");
  assert.equal(developer.id, undefined, "nothing in the pipeline names it");
});

// --- The team's forecast and team-sized pursuits ---------------------------------------------------------

/** A pursuit the team sized in its own workbook, with no Salesforce opportunity, starting within six months. */
const useCase = (changes = {}) => ({
  key: "invoice-intake-agent", name: "Invoice intake agent", source: "Team expansion workbook, Pursuits tab (2026-07-28)", asOf: "2026-07-28",
  startDate: "2026-11-01", lines: [{ product: "AI Units", units: 200000, row: "AI Units" }, { product: "Unattended Robot", units: 4, row: "Unattended Robot" }],
  ...changes,
});
const renewalRow = (document, offering) => document.renewalTest.rows.find((row) => row.rowId === rowId(document, offering));

test("a team-sized use case goes through apply-findings as an opportunity record, a card and demand, and a second run finds nothing to change", () => {
  const draft = sizedPlan();
  draft.pipeline.useCases = [useCase()];
  const { document, conflicts, written } = numbersStage(draft);
  assert.deepEqual(conflicts, []);
  const record = opportunity(document, "invoice-intake-agent");
  assert.match(record.id, UUID);
  assert.deepEqual(
    [record.name, record.status, record.stage, record.estimatedIarrUsd, record.owner, record.nextGate],
    ["Invoice intake agent", "Open", "", 0, "", ""],
    "no stage, owner or next gate, and $0 iARR: it draws on existing entitlement",
  );
  assert.deepEqual(record.products, ["AI Units", "Unattended Robot"]);
  assert.deepEqual(record.consumptionRowIds, [rowId(document, "AI Units"), rowId(document, "Unattended Robot")]);
  assert.equal(record.projectedConsumption, "AI Units: 200000 units; Unattended Robot: 4 robots");
  const card = document.snapshot.pursuits.find((pursuit) => pursuit.opportunityId === record.id);
  assert.deepEqual(card.draw.map(({ rowId: id, units }) => [id, units]), [[rowId(document, "AI Units"), 200000], [rowId(document, "Unattended Robot"), 4]]);
  assert.equal(card.cardStatus, "");
  assert.deepEqual([renewalRow(document, "AI Units").demand6MoUnits, renewalRow(document, "AI Units").demand12MoUnits], [600000, 1600000]);
  assert.match(renewalRow(document, "AI Units").pipelineDriver, /Invoice intake agent \(Nov 26\)/);
  assert.deepEqual([renewalRow(document, "Unattended Robot").demand6MoUnits, renewalRow(document, "Unattended Robot").demand12MoUnits], [24, 24]);

  draft.pipeline.written = written;
  const again = numberFindings(draft, document);
  assert.deepEqual(again.findings, []);
  assert.deepEqual(again.conflicts, []);

  const final = otherActivityFindings(draft, document);
  const finished = apply(document, final.findings);
  assert.equal(finished.status, 0, finished.stderr);
  assert.equal(finished.doc.snapshot.otherPipelineActivityUsd, 50000, "off the cards: the FY28 robots (30000) and the use case, ranked last at $0 iARR (200000 x 0.04 + 4 x 3000)");
});

test("a team forecast the sweep adds after a recorded run replaces the opportunity demand this plan wrote, and apply-findings accepts the refresh", () => {
  const draft = sizedPlan();
  const first = numbersStage(draft);
  draft.pipeline.written = first.written;
  assert.deepEqual([renewalRow(first.document, "AI Units").demand6MoUnits, renewalRow(first.document, "AI Units").demand12MoUnits], [400000, 1400000]);

  // Step 9.4: the team's quarterly forecast for AI Units, and a renewal that leaves q4 a renewal question.
  draft.contract.renewalDate = "2027-06-01";
  Object.assign(draft.rows.find((row) => row.product === "AI Units"), { forecastUnits: { q1: 100000, q2: 150000, q3: 200000, q4: 250000 } });
  const refresh = numberFindings(draft, toDay2(draft, first.document).document);
  assert.deepEqual(refresh.conflicts, []);
  const refreshed = apply(toDay2(draft, first.document).document, refresh.findings);
  assert.equal(refreshed.status, 0, refreshed.stderr);
  const row = renewalRow(refreshed.doc, "AI Units");
  assert.deepEqual([row.demand6MoUnits, row.demand12MoUnits], [250000, 450000]);
  assert.equal(row.pipelineDriver, renewalRow(first.document, "AI Units").pipelineDriver, "the opportunities still drive it");
  assert.match(refreshed.stdout, /team forecast \(forecastUnits\)/);
  assert.deepEqual(refreshed.doc.snapshot.pursuits, [], "an opportunity draws nothing, forecast or not");
  assert.equal(refreshed.doc.renewalDate, "2027-06-01");

  draft.pipeline.written = { ...first.written, ...refresh.written };
  assert.deepEqual(numberFindings(draft, refreshed.doc).findings, [], "and the next run finds it settled");
});

test("a record the team keyed in its own spelling of a use case's key is filled through apply-findings, never duplicated", () => {
  const draft = sizedPlan();
  draft.pipeline.useCases = [useCase()];
  const baseline = blank();
  baseline.pipelineOpportunities.push({ id: "55555555-5555-4555-8555-000000000009", key: "Invoice_Intake Agent", name: "Invoice intake agent", stage: "", status: "Open", estimatedIarrUsd: null, products: [], consumptionRowIds: [], projectedConsumption: "", owner: "", nextGate: "" });
  const { document, conflicts } = numbersStage(draft, baseline);
  assert.deepEqual(conflicts, []);
  const appKey = (value) => String(value ?? "").normalize("NFKC").trim().toLocaleLowerCase("en-US").replace(/[-_]+/g, " ").replace(/\s+/g, " ");
  const same = document.pipelineOpportunities.filter((record) => appKey(record.key) === "invoice intake agent");
  assert.equal(same.length, 1, "one record, as the app's duplicate-key rule needs");
  assert.equal(same[0].key, "Invoice_Intake Agent", "the team's key stands");
  assert.equal(same[0].id, "55555555-5555-4555-8555-000000000009");
  assert.equal(same[0].estimatedIarrUsd, 0);
  const card = document.snapshot.pursuits.find((pursuit) => pursuit.opportunityId === same[0].id);
  assert.deepEqual(card.draw.map(({ units }) => units), [200000, 4]);
});

// --- The app's overdrawn footnote, explained by the gap list --------------------------------------------------

/** The gap list's items of one "why" for a document the numbers stage produced. */
const gapsOf = (draft, document, why) => gapList({ plan: draft, document }).filter((entry) => entry.why === why);
/** The document with the team's named top pursuits: the first opportunity's card and the use case's. */
const naming = (document, ...keys) => ({ ...document, snapshot: { ...document.snapshot, topPursuitIds: keys.map((key) => opportunity(document, key).id) } });

test("a team forecast below what a use case's card draws leaves the row overdrawn, and the gap list says so", () => {
  const draft = sizedPlan();
  draft.pipeline.useCases = [useCase({ lines: [{ product: "Unattended Robot", units: 8, row: "Unattended Robot" }] })];
  Object.assign(draft.rows.find((row) => row.product === "Unattended Robot"), { forecastUnits: { q1: 65, q2: 80, q3: null, q4: null } });
  const { document } = numbersStage(draft);
  assert.deepEqual([renewalRow(document, "Unattended Robot").demand6MoUnits, renewalRow(document, "Unattended Robot").demand12MoUnits], [5, 5], "only q1 starts before the 2026-12-01 renewal: 65 - 60");
  const overdrawn = gapsOf(draft, naming(document, "invoice-intake-agent"), "overdrawn");
  assert.deepEqual(overdrawn.map(({ item, ownerRole }) => [item, ownerRole]), [
    ['Top pursuits draw 8 Unattended Robot, more than its 5 12-month demand ("Invoice intake agent" 8)', "AE"],
  ]);
  assert.match(overdrawn[0].nextStep, /^Reconcile the team forecast with this use case's sizing, or date the use case/);
  assert.deepEqual(gapsOf(draft, document, "overdrawn"), [], "the app's default cards are opportunities, which draw nothing");
});

test("a use case with no start date, or one that has started, draws on its card while adding no demand: overdrawn, and a started one is asked about", () => {
  for (const startDate of [undefined, "2026-07-01"]) {
    const draft = sizedPlan();
    draft.pipeline.useCases = [useCase({ startDate, lines: [{ product: "AI Units", units: 200000, row: "AI Units" }, { product: "Unattended Robot", units: 25, row: "Unattended Robot" }] })];
    const { document } = numbersStage(draft);
    assert.equal(renewalRow(document, "Unattended Robot").demand12MoUnits, 20, `${startDate}: the use case adds no demand`);
    const shown = naming(document, "006EXAMPLE0000001", "invoice-intake-agent");
    assert.deepEqual(gapsOf(draft, shown, "overdrawn").map(({ item }) => item), [
      'Top pursuits draw 25 Unattended Robot, more than its 20 12-month demand ("Invoice intake agent" 25)',
    ], `${startDate}: the opportunity's card draws nothing, so only the use case's counts`);
    assert.equal(gapsOf(draft, shown, "already started").length, startDate ? 1 : 0, startDate);
  }
});

test("a use case starting more than 12 months out gets no draw, so its card is not overdrawn but withholds Est. rev., as an opportunity's card does", () => {
  const draft = sizedPlan();
  draft.pipeline.useCases = [useCase({ startDate: "2027-12-01" })];
  const { document } = numbersStage(draft);
  const record = opportunity(document, "invoice-intake-agent");
  assert.ok(record, "it is still a record");
  assert.equal(document.snapshot.pursuits.some((pursuit) => pursuit.opportunityId === record.id), false, "and has no card");
  const shown = naming(document, "006EXAMPLE0000001", "invoice-intake-agent");
  assert.deepEqual(gapsOf(draft, shown, "overdrawn"), []);
  assert.deepEqual(gapsOf(draft, shown, "blocks Known pipeline demand").map(({ item, nextStep }) => [item, nextStep]), [
    [
      'Pursuit card "Example Corp - AI Units and Robot Expansion": Est. rev. is withheld (it has no pursuit entry or no draw)',
      "This opportunity adds its own entitlement and draws nothing from today's rows; pick top pursuits in the app that draw on existing entitlement (team-sized use cases), then rerun Step 9.5 on the exported draft.",
    ],
    [
      'Pursuit card "Invoice intake agent": Est. rev. is withheld (it starts 2027-12-01, more than 12 months after 2026-08-01, so this plan gives it no draw)',
      "Re-date the use case in the plan file if it starts sooner and rerun the numbers stage, or choose other top pursuits in the app, then rerun Step 9.5 on the exported draft; until then Known pipeline demand and Net of pipeline stay blank.",
    ],
  ]);
});

// --- The command line --------------------------------------------------------------------------------------

const run = (...args) => spawnSync(process.execPath, [pipelineScript, ...args], { encoding: "utf8" });

test("the findings command writes the findings and the conflicts; --record, after they are applied, keeps what the plan wrote", () => {
  const draft = sizedPlan();
  const merged = toDay2(draft, blank()).document;
  const planPath = write("plan.json", draft);
  const documentPath = write("merged.day2.json", merged);
  const out = join(dir, `cli-numbers-${++counter}.json`);
  const conflictsPath = join(dir, `cli-conflicts-${counter}.json`);

  const first = run("findings", planPath, "--document", documentPath, "--stage", "numbers", "--out", out, "--conflicts", conflictsPath);
  assert.equal(first.status, 0, first.stderr);
  const { findings } = JSON.parse(readFileSync(out, "utf8"));
  assert.deepEqual(findings, numberFindings(draft, merged).findings);
  assert.deepEqual(JSON.parse(readFileSync(conflictsPath, "utf8")), { conflicts: [] });
  assert.equal(JSON.parse(readFileSync(planPath, "utf8")).pipeline.written, undefined, "nothing is recorded until the findings are applied");

  // The findings are applied, then --record runs against the document they produced: every value is already there.
  const applied = apply(merged, findings);
  assert.equal(applied.status, 0, applied.stderr);
  const appliedPath = write("applied.day2.json", applied.doc);
  const recorded = run("findings", planPath, "--document", appliedPath, "--stage", "numbers", "--record");
  assert.equal(recorded.status, 0, recorded.stderr);
  const after = JSON.parse(readFileSync(planPath, "utf8"));
  assert.deepEqual(after.pipeline.written, numberFindings(draft, merged).written);
  assert.deepEqual(after.pipeline.opportunities, draft.pipeline.opportunities, "the rest of the plan is as it was");
  assert.deepEqual(after.rows, draft.rows);

  const final = join(dir, `cli-final-${++counter}.json`);
  const stage = run("findings", planPath, "--document", appliedPath, "--stage", "final", "--out", final);
  assert.equal(stage.status, 0, stage.stderr);
  const finalFindings = JSON.parse(readFileSync(final, "utf8")).findings;
  assert.equal(finalFindings[0].value, 30000);
  const finished = apply(applied.doc, finalFindings);
  assert.equal(finished.status, 0, finished.stderr);
  const recordedFinal = run("findings", planPath, "--document", write("finished.day2.json", finished.doc), "--stage", "final", "--record");
  assert.equal(recordedFinal.status, 0, recordedFinal.stderr);
  const written = JSON.parse(readFileSync(planPath, "utf8")).pipeline.written;
  assert.equal(written.otherPipelineActivityUsd, 30000);
  assert.equal(written["renewalTest:Unattended Robot:demand12MoUnits"], 20, "the earlier record is kept");
});

test("--record refuses to record while the document lacks findings, and leaves the plan alone", () => {
  const draft = plan();
  const planPath = write("plan.json", draft);
  const documentPath = write("merged.day2.json", toDay2(draft, blank()).document);
  const refused = run("findings", planPath, "--document", documentPath, "--stage", "numbers", "--record");
  assert.equal(refused.status, 1);
  assert.match(refused.stderr, /not recorded/);
  assert.match(refused.stderr, /apply/);
  assert.equal(JSON.parse(readFileSync(planPath, "utf8")).pipeline.written, undefined);
});

test("the findings command refuses a bad call and a plan it cannot read, saying why", () => {
  const draft = plan();
  const planPath = write("plan.json", draft);
  const documentPath = write("merged.day2.json", toDay2(draft, blank()).document);
  const out = join(dir, `cli-bad-${++counter}.json`);
  assert.equal(run("findings", planPath, "--document", documentPath, "--stage", "numbers").status, 2, "no --out");
  assert.equal(run("findings", planPath, "--document", documentPath, "--stage", "later", "--out", out).status, 2, "an unknown stage");
  assert.equal(run("findings", planPath, "--stage", "numbers", "--out", out).status, 2, "no document");
  assert.equal(run("rows", planPath).status, 2, "an unknown command");

  draft.pipeline.opportunities[0].closeDate = "Q4";
  const bad = run("findings", write("bad-plan.json", draft), "--document", documentPath, "--stage", "numbers", "--out", out);
  assert.equal(bad.status, 1);
  assert.match(bad.stderr, /pipeline: .*closeDate/);

  const unbuilt = run("findings", planPath, "--document", write("blank.day2.json", blank()), "--stage", "numbers", "--out", out);
  assert.equal(unbuilt.status, 1);
  assert.match(unbuilt.stderr, /AI Units/);
});

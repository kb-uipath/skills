// node --test consumption-plan/tests/pipeline.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as pipeline from "../scripts/pipeline.mjs";
import * as toDay2Module from "../scripts/to-day2.mjs";

const {
  PipelineError, addMonths, isConsumptionLine, numberFindings, otherActivityFindings, otherActivityUsd, pipelineDemand, readPipeline,
  shownPursuitKeys, unitPriceByRow,
} = pipeline;
const { locatePlanRows, toDay2 } = toDay2Module;

const here = dirname(fileURLToPath(import.meta.url));
const plan = () => JSON.parse(readFileSync(join(here, "fixtures", "illustrative-pipeline-plan.json"), "utf8"));
/** The fixture's opportunity whose one line, on the AI Units row, decodes to no units. */
const UNSIZED = "006EXAMPLE0000007";
/** The fixture without that opportunity, so every line on a consumed row is sized. */
const sizedPlan = () => {
  const draft = plan();
  draft.pipeline.opportunities = draft.pipeline.opportunities.filter(({ salesforceId }) => salesforceId !== UNSIZED);
  return draft;
};
/** What other activity totals, without the opportunity objects. */
const totals = ({ usd, unpriced, unsized }) => ({ usd, unpriced, unsized });
const ids = (opportunities) => opportunities.map((opportunity) => opportunity.salesforceId);
const names = (opportunities) => opportunities.map((opportunity) => opportunity.name);

/** An open, non-renewal opportunity with one sized line on a plan row. */
function opportunity(closeDate, { id = `006TEST${closeDate}`, units = 100, row = "Unattended Robot", ...rest } = {}) {
  return {
    salesforceId: id, name: `Opp ${closeDate}`, stage: "Proposal", amountUsd: 1000, closeDate,
    lastModifiedDate: "2026-07-01", isRenewal: false, ownerName: "",
    lines: [{ product: row, productCode: "", quantity: units, units, row }],
    ...rest,
  };
}

/** The fixture's plan, asOf moved and its opportunities replaced. */
function planWith(opportunities, asOf = "2026-08-01") {
  const draft = plan();
  draft.asOf = asOf;
  draft.pipeline.opportunities = opportunities;
  return draft;
}

test("addMonths keeps the day of month and clamps to the month's last day", () => {
  assert.equal(addMonths("2026-08-31", 6), "2027-02-28");
  assert.equal(addMonths("2026-08-01", 12), "2027-08-01");
  assert.equal(addMonths("2027-08-31", 6), "2028-02-29", "a leap February keeps its 29th");
  assert.equal(addMonths("2026-11-30", 3), "2027-02-28", "the year rolls over");
  assert.equal(addMonths("2026-03-31", -1), "2026-02-28");
  assert.throws(() => addMonths("2026-02-30", 6), PipelineError);
  assert.throws(() => addMonths("2026-08-01", 1.5), PipelineError);
});

test("reads the contract and every opportunity of the fixture", () => {
  const { contract, opportunities } = readPipeline(plan());
  assert.deepEqual(contract, { contractNumber: "00000001", startDate: "2025-12-01", renewalDate: "2026-12-01" });
  assert.equal(opportunities.length, 8);
  assert.deepEqual(opportunities[0], {
    salesforceId: "006EXAMPLE0000001", name: "Example Corp - AI Units and Robot Expansion", stage: "Negotiation",
    amountUsd: 120000, closeDate: "2026-10-01", lastModifiedDate: "2026-07-20", isRenewal: false, ownerName: "Illustrative Owner",
    lines: [
      { product: "AI Units Bundle 1K", productCode: "", quantity: 400, units: 400000, row: "AI Units" },
      { product: "Unattended Robot", productCode: "UIFDUR00000", quantity: 20, units: 20, row: "Unattended Robot" },
    ],
  });
});

test("demand by row counts open lines by close date, cumulatively over 6 and 12 months", () => {
  const { byRow } = pipelineDemand(sizedPlan());
  assert.deepEqual([...byRow.keys()].sort(), ["AI Units", "Unattended Robot"]);
  assert.deepEqual(byRow.get("AI Units"), {
    demand6MoUnits: 400000,
    demand12MoUnits: 1400000,
    drivers: ["Example Corp - AI Units and Robot Expansion (Oct 26)", "Example Corp - AI Units Phase 2 (May 27)"],
    asOf: "2026-07-30",
  });
  assert.deepEqual(byRow.get("Unattended Robot"), {
    demand6MoUnits: 20,
    demand12MoUnits: 20,
    drivers: ["Example Corp - AI Units and Robot Expansion (Oct 26)"],
    asOf: "2026-07-20",
  });
});

test("sorts the fixture's opportunities into open, stale, renewal and beyond-window", () => {
  const { open, stale, renewals, beyondWindow } = pipelineDemand(plan());
  assert.deepEqual(ids(open).sort(), [1, 2, 3, 6, 7, 8].map((n) => `006EXAMPLE000000${n}`));
  assert.deepEqual(ids(stale), ["006EXAMPLE0000005"]);
  assert.deepEqual(ids(renewals), ["006EXAMPLE0000004"]);
  assert.deepEqual(ids(beyondWindow), ["006EXAMPLE0000003"], "closing 14 months out: open, but it adds no demand");
});

test("a renewal and a stale opportunity add no demand even when their lines map to rows", () => {
  const { byRow } = pipelineDemand(plan());
  assert.equal(byRow.get("Unattended Robot").demand12MoUnits, 20, "neither the renewal's 100 nor the stale 50 robots, nor the beyond-window 10");
  assert.equal(byRow.has("Automation Developer"), false);
});

test("the unmapped line is reported and adds nothing; the unsized one is reported and withholds its row's demand", () => {
  const { unmapped, unsized, byRow } = pipelineDemand(plan());
  assert.equal(unmapped.length, 1);
  assert.equal(unmapped[0].opportunity.salesforceId, "006EXAMPLE0000006");
  assert.equal(unmapped[0].line.product, "Agent Units Bundle 1K");
  assert.equal(byRow.has(""), false, "an unmapped line is on no row");
  assert.equal(unsized.length, 1);
  assert.equal(unsized[0].opportunity.salesforceId, UNSIZED);
  assert.equal(unsized[0].line.units, null);
  assert.deepEqual(byRow.get("AI Units"), {
    demand6MoUnits: null,
    demand12MoUnits: null,
    drivers: [
      "Example Corp - AI Units and Robot Expansion (Oct 26)",
      "Example Corp - AI Units Enterprise Agreement (Dec 26)",
      "Example Corp - AI Units Phase 2 (May 27)",
    ],
    asOf: "2026-07-30",
  }, "the unsized line counts as neither 1 unit, its quantity nor nothing: the known part would look complete, so both windows it closes in are withheld, and it still drives the row");
  assert.equal(byRow.get("Unattended Robot").demand12MoUnits, 20, "another row is unaffected");
});

/** An open opportunity whose one line, on the robot row, has a quantity but decodes to no units. */
const unsizedOpportunity = (closeDate, id) => opportunity(closeDate, { id, lines: [{ product: "Robot bundle", productCode: "", quantity: 1, units: null, row: "Unattended Robot" }] });

test("an unsized line withholds only the windows it closes in, and a sized line of the same opportunity on that row with it", () => {
  const later = unsizedOpportunity("2027-05-01", "006LATER");
  const { byRow } = pipelineDemand(planWith([opportunity("2026-10-01", { units: 5 }), later]));
  assert.deepEqual(byRow.get("Unattended Robot"), {
    demand6MoUnits: 5, demand12MoUnits: null, drivers: ["Opp 2026-10-01 (Oct 26)", "Opp 2027-05-01 (May 27)"], asOf: "2026-07-01",
  }, "closing after 6 months, it leaves the 6-month figure known");

  const mixed = opportunity("2026-10-01", { id: "006MIXED", units: 5 });
  mixed.lines.push({ product: "Unattended Robot bundle", productCode: "", quantity: 1, units: null, row: "Unattended Robot" });
  assert.equal(pipelineDemand(planWith([mixed])).byRow.get("Unattended Robot").demand12MoUnits, null, "5 known units beside an unsized line are not the row's demand");

  const beyond = unsizedOpportunity("2027-10-01", "006BEYOND");
  assert.equal(pipelineDemand(planWith([opportunity("2026-10-01", { units: 5 }), beyond])).byRow.get("Unattended Robot").demand12MoUnits, 5, "one closing beyond 12 months is in neither window");
});

test("a line on a Platform / Capabilities row is not consumption: no demand, not unmapped, not unsized", () => {
  const draft = plan();
  const { byRow, open, unmapped, unsized } = pipelineDemand(draft);
  const platform = open.find((candidate) => candidate.salesforceId === "006EXAMPLE0000008");
  assert.ok(platform, "the opportunity is open");
  assert.equal(platform.lines[0].row, "Platform - Standard");
  assert.equal(byRow.has("Platform - Standard"), false);
  assert.equal(unmapped.some(({ opportunity }) => opportunity === platform), false);
  assert.equal(unsized.some(({ opportunity }) => opportunity === platform), false);

  const [line] = platform.lines;
  assert.equal(isConsumptionLine(draft, line), false);
  assert.equal(isConsumptionLine(draft, { ...line, row: "Unattended Robot" }), true);
  assert.equal(isConsumptionLine(draft, { ...line, row: "Unattended Robot", units: null }), false, "unsized");
  assert.equal(isConsumptionLine(draft, { ...line, row: "" }), false, "unmapped");
  assert.equal(isConsumptionLine(draft, { ...line, row: "Not A Plan Row" }), false);
});

test("a close date on asOf, or on asOf + 6 months, is inside the 6-month window; asOf + 12 months is inside the 12-month one", () => {
  const draft = planWith([
    opportunity("2026-08-01", { units: 1 }),
    opportunity("2027-02-01", { units: 10 }),
    opportunity("2027-08-01", { units: 100 }),
  ]);
  const { byRow, open, stale, beyondWindow } = pipelineDemand(draft);
  assert.equal(byRow.get("Unattended Robot").demand6MoUnits, 11);
  assert.equal(byRow.get("Unattended Robot").demand12MoUnits, 111);
  assert.equal(open.length, 3);
  assert.equal(stale.length, 0);
  assert.equal(beyondWindow.length, 0);
});

test("a close date a day past a window edge falls out of that window", () => {
  const { byRow, stale, beyondWindow } = pipelineDemand(planWith([
    opportunity("2026-07-31", { units: 1 }),
    opportunity("2027-02-02", { units: 10 }),
    opportunity("2027-08-02", { units: 100 }),
  ]));
  assert.deepEqual(ids(stale), ["006TEST2026-07-31"], "one day before asOf is stale");
  assert.deepEqual(ids(beyondWindow), ["006TEST2027-08-02"]);
  assert.equal(byRow.get("Unattended Robot").demand6MoUnits, 0, "mapped and timed, but nothing closes inside 6 months");
  assert.equal(byRow.get("Unattended Robot").demand12MoUnits, 10);
});

test("a month-end asOf puts the clamped 6-month date inside the 6-month window", () => {
  const { byRow } = pipelineDemand(planWith([
    opportunity("2027-02-28", { units: 7 }),
    opportunity("2027-03-01", { units: 70 }),
  ], "2026-08-31"));
  assert.equal(byRow.get("Unattended Robot").demand6MoUnits, 7);
  assert.equal(byRow.get("Unattended Robot").demand12MoUnits, 77);
});

test("a row with no in-window line is absent, not zero", () => {
  const { byRow } = pipelineDemand(planWith([opportunity("2027-10-01"), opportunity("2026-07-01", { id: "006STALE" })]));
  assert.equal(byRow.size, 0);
});

test("several lines and several opportunities on one row add up; drivers name each opportunity once, in close-date order", () => {
  const twoLines = opportunity("2026-12-01", { id: "006TWO", name: "Opp B", units: 5 });
  twoLines.lines.push({ product: "Unattended Robot (other size)", productCode: "", quantity: 3, units: 3, row: "Unattended Robot" });
  const earlier = opportunity("2026-09-01", { id: "006ONE", name: "Opp A", units: 2, lastModifiedDate: "2026-07-29" });
  const sameDay = opportunity("2026-12-01", { id: "006THREE", name: "Opp C", units: 1, lastModifiedDate: "2026-06-01" });
  const { byRow } = pipelineDemand(planWith([twoLines, sameDay, earlier]));
  assert.deepEqual(byRow.get("Unattended Robot"), {
    demand6MoUnits: 11,
    demand12MoUnits: 11,
    drivers: ["Opp A (Sep 26)", "Opp B (Dec 26)", "Opp C (Dec 26)"],
    asOf: "2026-07-29",
  });
});

test("an opportunity with no lines is open and adds nothing", () => {
  const { open, byRow } = pipelineDemand(planWith([opportunity("2026-10-01", { lines: [] })]));
  assert.equal(open.length, 1);
  assert.equal(byRow.size, 0);
});

test("a plan with an empty pipeline has no demand", () => {
  const result = pipelineDemand(planWith([]));
  assert.equal(result.byRow.size, 0);
  for (const key of ["open", "stale", "renewals", "beyondWindow", "unmapped", "unsized"]) assert.deepEqual(result[key], [], key);
});

test("refuses a bad shape with a PipelineError that names the field", () => {
  const cases = [
    ["a negative units", (p) => { p.pipeline.opportunities[0].lines[0].units = -1; }, /lines\[0\]\.units/],
    ["a negative quantity", (p) => { p.pipeline.opportunities[0].lines[0].quantity = -1; }, /lines\[0\]\.quantity/],
    ["a text units", (p) => { p.pipeline.opportunities[0].lines[0].units = "400000"; }, /lines\[0\]\.units/],
    ["a missing quantity", (p) => { delete p.pipeline.opportunities[0].lines[0].quantity; }, /lines\[0\]\.quantity/],
    ["a quarter for a close date", (p) => { p.pipeline.opportunities[0].closeDate = "Q4"; }, /closeDate/],
    ["an impossible close date", (p) => { p.pipeline.opportunities[0].closeDate = "2026-02-30"; }, /closeDate/],
    ["a timestamp for a modified date", (p) => { p.pipeline.opportunities[0].lastModifiedDate = "2026-07-20T10:00:00Z"; }, /lastModifiedDate/],
    ["a row that is not a plan product", (p) => { p.pipeline.opportunities[0].lines[0].row = "Agent Units"; }, /Agent Units/],
    ["a row that two plan rows share", (p) => { p.rows.push({ ...p.rows[2], category: "Other" }); }, /more than one/],
    ["a renewal flag that is not a boolean", (p) => { p.pipeline.opportunities[0].isRenewal = "false"; }, /isRenewal/],
    ["a placeholder name", (p) => { p.pipeline.opportunities[0].name = "TBD"; }, /placeholder/],
    ["a missing name", (p) => { p.pipeline.opportunities[0].name = ""; }, /name/],
    ["a repeated Salesforce id", (p) => { p.pipeline.opportunities[1].salesforceId = p.pipeline.opportunities[0].salesforceId; }, /006EXAMPLE0000001/],
    ["an amount that is text", (p) => { p.pipeline.opportunities[0].amountUsd = "120000"; }, /amountUsd/],
    ["lines that are not an array", (p) => { p.pipeline.opportunities[0].lines = null; }, /lines/],
    ["a missing pipeline section", (p) => { delete p.pipeline; }, /pipeline/],
    ["a missing contract", (p) => { delete p.contract; }, /contract/],
    ["a contract date in free text", (p) => { p.contract.renewalDate = "December"; }, /renewalDate/],
    ["an unreadable asOf", (p) => { p.asOf = "August 2026"; }, /asOf/],
  ];
  for (const [label, damage, message] of cases) {
    const draft = plan();
    damage(draft);
    assert.throws(() => pipelineDemand(draft), (error) => error instanceof PipelineError && message.test(error.message), label);
  }
});

test("a null amount and an empty row are accepted: Empty stays empty", () => {
  const draft = plan();
  draft.pipeline.opportunities[5].amountUsd = null;
  const { opportunities } = readPipeline(draft);
  assert.equal(opportunities[5].amountUsd, null);
  assert.equal(opportunities[5].lines[0].row, "");
});

test("unit price by row is the row's ARR over its purchased quantity", () => {
  const prices = unitPriceByRow(plan());
  assert.equal(prices.get("Unattended Robot"), 3000);
  assert.equal(prices.get("Automation Developer"), 3000);
  assert.equal(prices.get("AI Units"), 0.04);
  assert.equal(prices.get("Platform - Standard"), 0, "a row with no ARR is free to the account, not unpriced");
  assert.deepEqual([...prices.keys()], ["Automation Developer", "Unattended Robot", "AI Units", "Platform - Standard"]);
});

test("a row with no ARR, no quantity or a quantity of zero or less has no price", () => {
  const draft = plan();
  const [developer, robot, aiUnits, platform] = draft.rows;
  developer.arrUsd = null;
  delete robot.arrUsd;
  aiUnits.purchasedQuantity = null;
  platform.purchasedQuantity = 0;
  draft.rows.push({ ...robot, product: "Negative Quantity", arrUsd: 100, purchasedQuantity: -5 });
  draft.rows.push({ ...robot, product: "Unreadable ARR", arrUsd: "300000", purchasedQuantity: 100 });
  const prices = unitPriceByRow(draft);
  for (const product of ["Automation Developer", "Unattended Robot", "AI Units", "Platform - Standard", "Negative Quantity", "Unreadable ARR"]) {
    assert.equal(prices.get(product), null, product);
  }
  assert.equal(prices.has("Not A Plan Row"), false);
});

/** The fixture's plan with a second "Unattended Robot" row, every robot line renamed to the first row by category. */
function planWithSharedRobot() {
  const draft = plan();
  draft.rows.push({ ...draft.rows[1], category: "Other", arrUsd: 10, purchasedQuantity: 5 });
  for (const { lines } of draft.pipeline.opportunities) {
    for (const line of lines) if (line.row === "Unattended Robot") line.row = "Robots|Unattended Robot";
  }
  return draft;
}

test("two plan rows that share a product are priced under their own category|product keys", () => {
  const prices = unitPriceByRow(planWithSharedRobot());
  assert.equal(prices.has("Unattended Robot"), false, "no bare key names either row");
  assert.equal(prices.get("Robots|Unattended Robot"), 3000);
  assert.equal(prices.get("Other|Unattended Robot"), 2);
  assert.equal(prices.get("AI Units"), 0.04, "a product only one row carries keeps its bare key");
});

test("a line names a shared product's row as category|product, in the plan row's own spelling, and demand keys agree", () => {
  const draft = planWithSharedRobot();
  const line = (row, units) => ({ product: "Robot bundle", productCode: "", quantity: units, units, row });
  draft.pipeline.opportunities[0].lines = [line("Robots|Unattended Robot", 3), line(" other | UNATTENDED robot ", 5), line("robots|unattended robot", 1)];
  const { opportunities } = readPipeline(draft);
  assert.deepEqual(opportunities[0].lines.map((entry) => entry.row), ["Robots|Unattended Robot", "Other|Unattended Robot", "Robots|Unattended Robot"]);
  const { byRow } = pipelineDemand(draft);
  assert.deepEqual([...byRow.keys()], ["Robots|Unattended Robot", "Other|Unattended Robot", "AI Units"]);
  assert.equal(byRow.get("Robots|Unattended Robot").demand12MoUnits, 4);
  assert.equal(byRow.get("Other|Unattended Robot").demand12MoUnits, 5);
  assert.equal(isConsumptionLine(draft, line("robots|unattended robot", 1)), true);
});

test("a row that only one plan row carries may still be named category|product, and keeps its bare key", () => {
  const draft = plan();
  draft.pipeline.opportunities[0].lines[0].row = "CONSUMABLES|ai units";
  draft.pipeline.opportunities[0].lines[1].row = "robots|unattended robot";
  assert.deepEqual(readPipeline(draft).opportunities[0].lines.map((entry) => entry.row), ["AI Units", "Unattended Robot"]);
  assert.deepEqual([...pipelineDemand(draft).byRow.keys()], ["AI Units", "Unattended Robot"]);
});

test("a bare product that two plan rows carry is refused with how to name the row; a category|product that names nothing is refused too", () => {
  const draft = plan();
  draft.rows.push({ ...draft.rows[1], category: "Other" });
  assert.throws(() => readPipeline(draft), (error) => error instanceof PipelineError && /more than one/.test(error.message) && /<category>\|<product>/.test(error.message));
  draft.pipeline.opportunities[0].lines[1].row = "Nowhere|Unattended Robot";
  assert.throws(() => readPipeline(draft), (error) => error instanceof PipelineError && /Nowhere\|Unattended Robot/.test(error.message));
});

test("a category|product that two plan rows share cannot say which row it means", () => {
  const draft = plan();
  draft.rows.push({ ...draft.rows[1] });
  draft.pipeline.opportunities.forEach((opportunity) => opportunity.lines.forEach((entry) => { if (entry.row === "Unattended Robot") entry.row = "Robots|Unattended Robot"; }));
  assert.throws(() => readPipeline(draft), /more than one/);
  assert.equal(unitPriceByRow(draft).get("Robots|Unattended Robot"), null, "neither row has a price of its own");
});

/** A pipeline opportunity as the app's document carries it. */
const pursuit = (id, key, { status = "Open", estimatedIarrUsd = null, customerValueUsd = null } = {}) =>
  ({ id, key, name: `Pursuit ${key}`, status, estimatedIarrUsd, customerValueUsd });
const documentWith = (pipelineOpportunities, topPursuitIds = []) => ({ snapshot: { topPursuitIds }, pipelineOpportunities });

test("with no named pursuits the shown ones are the top three open by estimated revenue", () => {
  const document = documentWith([
    pursuit("id-a", "A", { estimatedIarrUsd: 100 }),
    pursuit("id-b", "B", { estimatedIarrUsd: 400 }),
    pursuit("id-c", "C", { estimatedIarrUsd: 300 }),
    pursuit("id-d", "D", { estimatedIarrUsd: 200 }),
  ]);
  assert.deepEqual(shownPursuitKeys(document), ["B", "C", "D"]);
  assert.deepEqual(shownPursuitKeys(document, 2), ["B", "C"]);
});

test("the ranking uses customer value when stated, even zero, and skips closed opportunities", () => {
  const document = documentWith([
    pursuit("id-a", "A", { estimatedIarrUsd: 100, customerValueUsd: 900 }),
    pursuit("id-b", "B", { estimatedIarrUsd: 400, customerValueUsd: 0 }),
    pursuit("id-c", "C", { estimatedIarrUsd: 300 }),
    pursuit("id-d", "D", { status: "Closed Won", estimatedIarrUsd: 9000 }),
    pursuit("id-e", "E", { status: "Closed Lost", estimatedIarrUsd: 8000 }),
    pursuit("id-f", "F", { status: "On Hold", estimatedIarrUsd: 50 }),
    pursuit("id-g", "G", { status: "", estimatedIarrUsd: 10 }),
  ]);
  assert.deepEqual(shownPursuitKeys(document), ["A", "C", "F"], "a stated value of zero ranks as zero, not as the estimate; closed ones never show; a blank status is not closed");
});

test("equal values keep the document's order", () => {
  const document = documentWith([
    pursuit("id-a", "A", { estimatedIarrUsd: 10 }),
    pursuit("id-b", "B", { estimatedIarrUsd: 10 }),
    pursuit("id-c", "C", { estimatedIarrUsd: 10 }),
    pursuit("id-d", "D", { estimatedIarrUsd: 10 }),
    pursuit("id-e", "E"),
  ]);
  assert.deepEqual(shownPursuitKeys(document), ["A", "B", "C"]);
});

test("named top pursuits override the ranking, in their order, and may be closed ones", () => {
  const document = documentWith([
    pursuit("id-a", "A", { estimatedIarrUsd: 100 }),
    pursuit("id-b", "B", { estimatedIarrUsd: 400 }),
    pursuit("id-c", "C", { status: "Closed Won", estimatedIarrUsd: 300 }),
  ], ["id-c", "id-a"]);
  assert.deepEqual(shownPursuitKeys(document), ["C", "A"]);
});

test("a named id that matches nothing is dropped; when none match the ranking applies", () => {
  const opportunities = [pursuit("id-a", "A", { estimatedIarrUsd: 100 }), pursuit("id-b", "B", { estimatedIarrUsd: 400 })];
  assert.deepEqual(shownPursuitKeys(documentWith(opportunities, ["id-gone", "id-a"])), ["A"]);
  assert.deepEqual(shownPursuitKeys(documentWith(opportunities, ["id-gone"])), ["B", "A"]);
  assert.deepEqual(shownPursuitKeys(documentWith(opportunities, ["A"])), ["B", "A"], "an id is not a key");
});

test("the named ids are distinct and capped before they are matched, as the app imports them", () => {
  const opportunities = ["a", "b", "c", "d"].map((key) => pursuit(`id-${key}`, key.toUpperCase()));
  assert.deepEqual(shownPursuitKeys(documentWith(opportunities, ["id-a", "id-a", "id-b"])), ["A", "B"]);
  assert.deepEqual(shownPursuitKeys(documentWith(opportunities, ["id-a", "id-b", "id-c", "id-d"])), ["A", "B", "C"]);
  assert.deepEqual(shownPursuitKeys(documentWith(opportunities, ["id-gone", "id-a", "id-b", "id-c"])), ["A", "B"]);
});

test("a document whose opportunities are all closed shows none", () => {
  const document = documentWith([
    pursuit("id-a", "A", { status: "Closed Won", estimatedIarrUsd: 100 }),
    pursuit("id-b", "B", { status: "Closed Lost", estimatedIarrUsd: 400 }),
  ]);
  assert.deepEqual(shownPursuitKeys(document), []);
});

test("a document with no snapshot or no top pursuit ids has no named pursuits, so its opportunities rank", () => {
  const opportunities = [pursuit("id-a", "A", { estimatedIarrUsd: 1 }), pursuit("id-b", "B", { estimatedIarrUsd: 2 })];
  assert.deepEqual(shownPursuitKeys({ pipelineOpportunities: opportunities }), ["B", "A"], "no snapshot");
  assert.deepEqual(shownPursuitKeys({ snapshot: null, pipelineOpportunities: opportunities }), ["B", "A"], "a null snapshot");
  assert.deepEqual(shownPursuitKeys({ snapshot: {}, pipelineOpportunities: opportunities }), ["B", "A"], "no topPursuitIds");
  assert.deepEqual(shownPursuitKeys({ snapshot: { topPursuitIds: "id-a" }, pipelineOpportunities: opportunities }), ["B", "A"], "topPursuitIds that is not a list");
});

test("a document with no opportunities, or no document, shows none", () => {
  assert.deepEqual(shownPursuitKeys({}), []);
  assert.deepEqual(shownPursuitKeys({ snapshot: { topPursuitIds: ["id-a"] } }), []);
  assert.deepEqual(shownPursuitKeys({ snapshot: {}, pipelineOpportunities: "none" }), []);
  assert.deepEqual(shownPursuitKeys({ snapshot: {}, pipelineOpportunities: [] }), []);
  assert.deepEqual(shownPursuitKeys(null), []);
  assert.deepEqual(shownPursuitKeys(undefined), []);
});

test("other activity prices the open opportunities that are not shown, beyond-window ones included", () => {
  const result = otherActivityUsd(sizedPlan(), ["006EXAMPLE0000001", "006EXAMPLE0000002"]);
  assert.deepEqual(totals(result), { usd: 30000, unpriced: [], unsized: [] }, "the beyond-window opportunity's 10 robots at 3000, and neither the renewal nor the stale one");
});

test("other activity is zero when everything open is shown, and when nothing open is left", () => {
  const draft = plan();
  const { open } = pipelineDemand(draft);
  assert.deepEqual(totals(otherActivityUsd(draft, ids(open))), { usd: 0, unpriced: [], unsized: [] });
  assert.deepEqual(totals(otherActivityUsd(planWith([]), [])), { usd: 0, unpriced: [], unsized: [] });
  assert.deepEqual(totals(otherActivityUsd(sizedPlan(), ["006EXAMPLE0000001", "006EXAMPLE0000002", "006EXAMPLE0000003"])), { usd: 0, unpriced: [], unsized: [] });
});

test("other activity adds every unshown open line at its row's price, and ignores shown keys that name nothing", () => {
  const first = opportunity("2026-10-01", { id: "006ONE", units: 7 });
  const second = opportunity("2027-12-01", { id: "006TWO", units: 5 });
  second.lines.push({ product: "Automation Developer", productCode: "", quantity: 2, units: 2, row: "Automation Developer" });
  const draft = planWith([first, second, opportunity("2026-11-01", { id: "006SHOWN", units: 1000 })]);
  assert.deepEqual(totals(otherActivityUsd(draft, ["006SHOWN", "006NOWHERE"])), { usd: 7 * 3000 + 5 * 3000 + 2 * 3000, unpriced: [], unsized: [] });
  assert.deepEqual(otherActivityUsd(draft, []).usd, 7 * 3000 + 5 * 3000 + 2 * 3000 + 1000 * 3000);
  const fractional = otherActivityUsd(sizedPlan(), []);
  assert.ok(Math.abs(fractional.usd - (16000 + 60000 + 40000 + 30000)) < 1e-6, "AI Units at a cent-fraction price, plus the robots");
});

test("a line on an unmapped or platform row adds nothing, and is not unpriced", () => {
  const draft = sizedPlan();
  draft.rows.find((row) => row.product === "Platform - Standard").arrUsd = null;
  const shown = ["006EXAMPLE0000001", "006EXAMPLE0000002", "006EXAMPLE0000003"];
  assert.deepEqual(totals(otherActivityUsd(draft, shown)), { usd: 0, unpriced: [], unsized: [] }, "left open: an unmapped line and a platform tier with no price");
});

test("an unsized line on a consumed row withholds the total and is listed, priced row or not; a shown one does not count", () => {
  const shown = ["006EXAMPLE0000001", "006EXAMPLE0000002", "006EXAMPLE0000003"];
  for (const arrUsd of [40000, null]) {
    const draft = plan();
    draft.rows.find((row) => row.product === "AI Units").arrUsd = arrUsd;
    const { usd, unpriced, unsized } = otherActivityUsd(draft, shown);
    assert.equal(usd, null, `AI Units ARR ${arrUsd}: a sum without the line would understate the activity while looking complete`);
    assert.deepEqual(unpriced, [], "an unsized line is listed as unsized, not as unpriced");
    assert.deepEqual(unsized.map(({ opportunity, line }) => [opportunity.salesforceId, line.row, line.units]), [[UNSIZED, "AI Units", null]]);
  }
  assert.deepEqual(totals(otherActivityUsd(plan(), ["006EXAMPLE0000001", "006EXAMPLE0000002", UNSIZED])), { usd: 30000, unpriced: [], unsized: [] }, "on a card it is not other activity");
});

test("a sized line on a row with no price withholds the total and is listed; a shown one does not count", () => {
  const draft = sizedPlan();
  draft.rows.find((row) => row.product === "Unattended Robot").arrUsd = null;
  const { usd, unpriced } = otherActivityUsd(draft, ["006EXAMPLE0000001", "006EXAMPLE0000002"]);
  assert.equal(usd, null);
  assert.equal(unpriced.length, 1);
  assert.equal(unpriced[0].opportunity.salesforceId, "006EXAMPLE0000003");
  assert.equal(unpriced[0].line.row, "Unattended Robot");
  assert.equal(unpriced[0].line.units, 10);

  const allShown = otherActivityUsd(draft, ["006EXAMPLE0000001", "006EXAMPLE0000002", "006EXAMPLE0000003"]);
  assert.deepEqual(totals(allShown), { usd: 0, unpriced: [], unsized: [] }, "robots on opportunities that are shown are not other activity");

  const everyLine = otherActivityUsd(draft, []);
  assert.equal(everyLine.usd, null);
  assert.deepEqual(everyLine.unpriced.map(({ opportunity, line }) => [opportunity.salesforceId, line.row]), [
    ["006EXAMPLE0000001", "Unattended Robot"],
    ["006EXAMPLE0000003", "Unattended Robot"],
  ]);
});

test("other activity refuses a plan whose pipeline cannot be read", () => {
  const draft = plan();
  delete draft.pipeline;
  assert.throws(() => otherActivityUsd(draft, []), PipelineError);
});

// --- Findings --------------------------------------------------------------------------------------

/** The dashboard's blank v7 document, trimmed to what the merge and the findings read. */
const blankDocument = () => ({
  schemaVersion: "1.12",
  customerName: "",
  renewalDate: "",
  renewalEconomics: { currentArrUsd: null },
  consumptionPlan: { asOf: "", forecastPeriod: "", groups: [], primaryUseCases: [] },
  snapshot: { contractStartDate: "", otherPipelineActivityUsd: null, topPursuitIds: [], pursuits: [] },
  pipelineOpportunities: [],
  renewalTest: { healthyAtPercent: null, rows: [] },
});
const merged = (draft = plan(), baseline = blankDocument()) => toDay2(draft, baseline).document;
const rowOf = (document, offering) => document.consumptionPlan.groups.flatMap((group) => group.rows).find((row) => row.offering === offering);
const at = (pointer, findings) => findings.filter((finding) => finding.pointer === pointer);
const opportunityRecord = (findings, key) => at("/pipelineOpportunities", findings).filter((finding) => finding.value.key === key);
const pursuitFor = (findings, key) => at("/snapshot/pursuits", findings).find((finding) => finding.value.opportunityId === `ref:opportunity:${key}`);
const renewalRowFor = (findings, token) => at("/renewalTest/rows", findings).find((finding) => finding.value.rowId === token);
const SORS = "Salesforce is the system of record";
const REFRESHED = "refreshed from Salesforce opportunities as of 2026-08-01";
/** The AI Units row's drivers in the sized plan, and in the fixture, whose unsized line drives it too. */
const AI_DRIVERS = "Example Corp - AI Units and Robot Expansion (Oct 26); Example Corp - AI Units Phase 2 (May 27)";
const AI_DRIVERS_WITH_UNSIZED = "Example Corp - AI Units and Robot Expansion (Oct 26); Example Corp - AI Units Enterprise Agreement (Dec 26); Example Corp - AI Units Phase 2 (May 27)";
const ROW_ID = "11111111-1111-4111-8111-000000000001";
const OPP_ID = "55555555-5555-4555-8555-000000000001";
/** The sized plan with what it last wrote: the refresh rule's tests change one figure at a time. */
const withWritten = (written) => {
  const draft = sizedPlan();
  draft.pipeline.written = written;
  return draft;
};

test("findings for the fixture carry no owner and no field the account team judges", () => {
  const { findings } = numberFindings(plan(), merged());
  assert.doesNotMatch(JSON.stringify(findings), /owner/i);
  assert.doesNotMatch(JSON.stringify(findings), /cardStatus|confidence|nextGate|motions|topPursuitIds/);
});

test("they come in the order that lets every reference name a record an earlier finding made", () => {
  const { findings } = numberFindings(plan(), merged());
  assert.deepEqual(findings.map((finding) => finding.pointer), [
    "/renewalDate", "/snapshot/contractStartDate",
    ...Array(6).fill("/pipelineOpportunities"),
    ...Array(2).fill("/renewalTest/rows"),
  ], "no /snapshot/pursuits: an opportunity draws nothing");
  assert.deepEqual(findings.map((finding) => finding.op), ["set", "set", ...Array(8).fill("add")]);
});

test("the contract's dates are set from the contract, sourced to it, and need no supersedes on an empty document", () => {
  const { findings } = numberFindings(plan(), merged());
  assert.deepEqual(findings.slice(0, 2), [
    { op: "set", pointer: "/renewalDate", value: "2026-12-01", source: "Salesforce Contract 00000001", asOf: "2026-08-01" },
    { op: "set", pointer: "/snapshot/contractStartDate", value: "2025-12-01", source: "Salesforce Contract 00000001", asOf: "2026-08-01" },
  ]);
});

test("an empty contract date writes nothing", () => {
  const draft = plan();
  draft.contract.renewalDate = "";
  draft.contract.startDate = "";
  assert.deepEqual(numberFindings(draft, merged(draft)).findings.filter((finding) => finding.op === "set"), []);
});

test("only the open opportunities that are not stale and not renewals become records", () => {
  const { findings } = numberFindings(plan(), merged());
  const keys = at("/pipelineOpportunities", findings).map((finding) => finding.value.key);
  assert.deepEqual(keys, [1, 2, 3, 6, 7, 8].map((n) => `006EXAMPLE000000${n}`), "not the renewal (4) or the stale one (5); the beyond-window one (3) is open");
});

test("an opportunity's record carries Salesforce's facts, its products, the rows it touches and what it sizes", () => {
  const { findings } = numberFindings(plan(), merged());
  assert.deepEqual(opportunityRecord(findings, "006EXAMPLE0000001"), [{
    op: "add",
    pointer: "/pipelineOpportunities",
    value: {
      key: "006EXAMPLE0000001",
      name: "Example Corp - AI Units and Robot Expansion",
      stage: "Negotiation",
      status: "Open",
      estimatedIarrUsd: 120000,
      products: ["AI Units Bundle 1K", "Unattended Robot"],
      consumptionRowIds: ["ref:row:AI Units", "ref:row:Unattended Robot"],
      projectedConsumption: "AI Units: 400000 units; Unattended Robot: 20 robots",
    },
    source: "Salesforce Opportunity 006EXAMPLE0000001",
    asOf: "2026-07-20",
  }]);
});

test("an opportunity with no mapped or sized line is still a record, with only what it has", () => {
  const { findings } = numberFindings(plan(), merged());
  assert.deepEqual(opportunityRecord(findings, "006EXAMPLE0000006")[0].value, {
    key: "006EXAMPLE0000006", name: "Example Corp - Agent Pilot", stage: "Qualification", status: "Open", estimatedIarrUsd: 40000,
    products: ["Agent Units Bundle 1K"],
  });
  assert.deepEqual(opportunityRecord(findings, "006EXAMPLE0000007")[0].value.consumptionRowIds, ["ref:row:AI Units"], "a mapped row is referenced even when the line is unsized");
  assert.equal("projectedConsumption" in opportunityRecord(findings, "006EXAMPLE0000007")[0].value, false, "but nothing is sized");
  const platform = opportunityRecord(findings, "006EXAMPLE0000008")[0].value;
  assert.deepEqual(platform.consumptionRowIds, ["ref:row:Platform - Standard"]);
  assert.equal("projectedConsumption" in platform, false, "a platform tier is granted, not consumed");
});

test("a null amount is left out so Empty stays empty", () => {
  const draft = plan();
  draft.pipeline.opportunities[5].amountUsd = null;
  assert.equal("estimatedIarrUsd" in opportunityRecord(numberFindings(draft, merged(draft)).findings, "006EXAMPLE0000006")[0].value, false);
});

test("an opportunity never draws on today's consumption rows, whatever its close date or lines: its product lines are new entitlement the customer is buying", () => {
  const { findings, written } = numberFindings(plan(), merged());
  assert.deepEqual(at("/snapshot/pursuits", findings), [], "no card for the in-window (1, 2), unsized (7), beyond-window (3), unmapped (6) or platform (8) opportunities, nor the renewal (4) or the stale one (5)");
  assert.equal(Object.keys(written).some((key) => key.startsWith("draw:")), false, "and no draw is recorded as written");
  assert.deepEqual(opportunityRecord(findings, "006EXAMPLE0000001")[0].value.consumptionRowIds, ["ref:row:AI Units", "ref:row:Unattended Robot"], "its record still names the rows it touches");
  assert.equal(renewalRowFor(findings, "ref:row:Unattended Robot").value.demand12MoUnits, 20, "and its quantities still give the Renewal Test's demand");
});

test("lines of one opportunity on one row add up in its projected consumption, and still draw nothing", () => {
  const draft = plan();
  draft.pipeline.opportunities[0].lines.push({ product: "AI Units Bundle 5K", productCode: "", quantity: 1, units: 5000, row: "AI Units" });
  const { findings } = numberFindings(draft, merged(draft));
  assert.equal(pursuitFor(findings, "006EXAMPLE0000001"), undefined);
  assert.match(opportunityRecord(findings, "006EXAMPLE0000001")[0].value.projectedConsumption, /^AI Units: 405000 units;/);
});

test("each row with stated demand gets a renewal-test row: the drivers, and the demand over 6 and 12 months", () => {
  const { findings } = numberFindings(plan(), merged());
  assert.deepEqual(at("/renewalTest/rows", findings), [
    {
      op: "add",
      pointer: "/renewalTest/rows",
      value: { rowId: "ref:row:AI Units", pipelineDriver: AI_DRIVERS_WITH_UNSIZED, demand6MoUnits: null, demand12MoUnits: null },
      source: "Salesforce Opportunities closing within 12 months of 2026-08-01",
      asOf: "2026-07-30",
    },
    {
      op: "add",
      pointer: "/renewalTest/rows",
      value: { rowId: "ref:row:Unattended Robot", pipelineDriver: "Example Corp - AI Units and Robot Expansion (Oct 26)", demand6MoUnits: 20, demand12MoUnits: 20 },
      source: "Salesforce Opportunities closing within 12 months of 2026-08-01",
      asOf: "2026-07-20",
    },
  ]);
});

test("every row a finding names is a ref:row token, every opportunity a ref:opportunity token, and every finding has a source and a date", () => {
  // A use case gives the one card that names a record (an opportunity draws nothing).
  const draft = planWithUseCases(useCase());
  const { findings } = numberFindings(draft, merged(draft));
  const rowIds = [];
  const visit = (value) => {
    if (Array.isArray(value)) value.forEach(visit);
    else if (value && typeof value === "object") {
      for (const [key, inner] of Object.entries(value)) {
        if (key === "rowId") rowIds.push(inner);
        else if (key === "opportunityId") assert.match(inner, /^ref:opportunity:invoice-intake-agent$/);
        else if (key === "consumptionRowIds") rowIds.push(...inner);
        else visit(inner);
      }
    }
  };
  findings.forEach((finding) => {
    visit(finding.value);
    assert.ok(finding.source.trim(), "a source");
    assert.match(finding.asOf, /^\d{4}-\d{2}-\d{2}$/);
  });
  assert.ok(rowIds.length > 10);
  for (const id of rowIds) assert.match(id, /^ref:row:/);
});

test("the written map holds each derived value the findings put in the document", () => {
  const { written, conflicts } = numberFindings(plan(), merged());
  assert.deepEqual(conflicts, []);
  assert.equal(written["renewalTest:AI Units:demand12MoUnits"], null, "withheld by the unsized line, and recorded as written");
  assert.equal(written["renewalTest:AI Units:demand6MoUnits"], null);
  assert.equal(written["renewalTest:AI Units:pipelineDriver"], AI_DRIVERS_WITH_UNSIZED);
  assert.equal(written["renewalTest:Unattended Robot:demand12MoUnits"], 20);
  assert.equal("draw:006EXAMPLE0000002:AI Units" in written, false, "an opportunity draws nothing, so no draw is written");
  assert.equal(`draw:${UNSIZED}:AI Units` in written, false);
  assert.equal(written["opportunity:006EXAMPLE0000003:projectedConsumption"], "Unattended Robot: 10 robots");
  assert.deepEqual(Object.keys(written).sort(), [
    ...["AI Units", "Unattended Robot"].flatMap((row) => ["demand12MoUnits", "demand6MoUnits", "pipelineDriver"].map((field) => `renewalTest:${row}:${field}`)),
    "opportunity:006EXAMPLE0000001:projectedConsumption", "opportunity:006EXAMPLE0000002:projectedConsumption", "opportunity:006EXAMPLE0000003:projectedConsumption",
    ...[1, 2, 3, 6, 7, 8].map((n) => `opportunity:006EXAMPLE000000${n}:name`),
    ...[1, 2, 3, 6, 7, 8].map((n) => `opportunity:006EXAMPLE000000${n}:status`),
    ...[1, 2, 3, 6, 7, 8].map((n) => `opportunity:006EXAMPLE000000${n}:products`),
    ...[1, 2, 3, 7, 8].map((n) => `opportunity:006EXAMPLE000000${n}:consumptionRowIds`),
  ].sort());
  assert.equal(written["opportunity:006EXAMPLE0000001:name"], "Example Corp - AI Units and Robot Expansion", "the name follows the refresh rule");
  assert.equal(written["opportunity:006EXAMPLE0000001:status"], "Open");
  assert.equal(written["opportunity:006EXAMPLE0000001:products"], '["AI Units Bundle 1K","Unattended Robot"]', "a list is recorded as its sorted, canonical text");
  assert.equal(written["opportunity:006EXAMPLE0000001:consumptionRowIds"], '["AI Units","Unattended Robot"]', "by the plan's row keys, which do not change when the rows get ids");
});

test("a projected consumption too long for the card names what fits and counts the rest", () => {
  const draft = plan();
  draft.rows.push({ ...draft.rows[0], product: "Automation Developer Seats", unit: "seats" });
  draft.pipeline.opportunities[0].lines.push({ product: "Seats", productCode: "", quantity: 12, units: 12, row: "Automation Developer Seats" });
  const text = opportunityRecord(numberFindings(draft, merged(draft)).findings, "006EXAMPLE0000001")[0].value.projectedConsumption;
  assert.equal(text, "AI Units: 400000 units; Unattended Robot: 20 robots; +1 more");
  assert.ok([...text].length <= 64);
});

test("a plan the document has not been built from is refused, not half-written", () => {
  assert.throws(() => numberFindings(plan(), blankDocument()), (error) => error instanceof PipelineError && /AI Units/.test(error.message) && /to-day2/.test(error.message));
});

// --- The refresh rule ------------------------------------------------------------------------------

/** The merged document, with the AI Units row and its renewal-test row as an earlier run left them. */
function documentWithAiUnits(changes = {}) {
  const document = merged();
  rowOf(document, "AI Units").id = ROW_ID;
  document.renewalTest.rows.push({
    id: "66666666-6666-4666-8666-000000000001", rowId: ROW_ID, pipelineDriver: AI_DRIVERS, demand6MoUnits: 400000, demand12MoUnits: 999, confidence: "", ...changes,
  });
  return document;
}

test("a value that is what this plan last wrote is refreshed, saying so", () => {
  const draft = withWritten({ "renewalTest:AI Units:demand12MoUnits": 999 });
  const { findings, conflicts, written } = numberFindings(draft, documentWithAiUnits());
  const finding = renewalRowFor(findings, "ref:row:AI Units");
  assert.deepEqual(finding.value, { rowId: "ref:row:AI Units", demand12MoUnits: 1400000 }, "only the value that changed; the others already match");
  assert.equal(finding.supersedes, REFRESHED);
  assert.deepEqual(conflicts, []);
  assert.equal(written["renewalTest:AI Units:demand12MoUnits"], 1400000);
});

test("a value that is not what this plan last wrote is the team's: it is kept and reported", () => {
  const draft = withWritten({ "renewalTest:AI Units:demand12MoUnits": 500 });
  const { findings, conflicts, written } = numberFindings(draft, documentWithAiUnits());
  assert.equal(renewalRowFor(findings, "ref:row:AI Units"), undefined, "no finding for a row whose only difference is the team's number");
  assert.equal(conflicts.length, 1);
  assert.match(conflicts[0], /AI Units/);
  assert.match(conflicts[0], /999/);
  assert.match(conflicts[0], /1400000/);
  assert.equal("renewalTest:AI Units:demand12MoUnits" in written, false, "this run wrote nothing there, so the plan's record of it stands");
  assert.equal(renewalRowFor(findings, "ref:row:Unattended Robot").value.demand12MoUnits, 20, "the other rows are unaffected");
});

test("a team number with no record of this plan writing it is kept too", () => {
  const { findings, conflicts } = numberFindings(sizedPlan(), documentWithAiUnits());
  assert.equal(renewalRowFor(findings, "ref:row:AI Units"), undefined);
  assert.equal(conflicts.length, 1);
});

test("a team number where Salesforce now gives none is kept without a conflict: nothing disagrees with it", () => {
  const { findings, conflicts, written } = numberFindings(plan(), documentWithAiUnits({ pipelineDriver: AI_DRIVERS_WITH_UNSIZED, demand6MoUnits: 400000, demand12MoUnits: 1500000 }));
  assert.equal(renewalRowFor(findings, "ref:row:AI Units"), undefined, "the unsized line withholds the plan's figures, so the team's stand");
  assert.deepEqual(conflicts, []);
  assert.equal("renewalTest:AI Units:demand12MoUnits" in written, false);
});

test("a value this plan wrote that the team cleared stays blank, with a line saying so", () => {
  const draft = withWritten({ "renewalTest:AI Units:demand12MoUnits": 1400000, "renewalTest:AI Units:demand6MoUnits": 400000 });
  const { findings, conflicts, written } = numberFindings(draft, documentWithAiUnits({ demand12MoUnits: null }));
  assert.equal(renewalRowFor(findings, "ref:row:AI Units"), undefined, "no finding puts it back");
  assert.equal(conflicts.length, 1);
  assert.match(conflicts[0], /^renewalTest row "AI Units" demand12MoUnits: left blank, as the account team cleared it \(this plan wrote 1400000\); Salesforce opportunities now give 1400000\.$/);
  assert.equal("renewalTest:AI Units:demand12MoUnits" in written, false, "the plan's record of what it wrote stands");
});

test("a blank this plan wrote as no figure is filled once Salesforce sizes it, as on a first run", () => {
  const draft = withWritten({ "renewalTest:AI Units:demand12MoUnits": null });
  const { findings, conflicts } = numberFindings(draft, documentWithAiUnits({ demand12MoUnits: null }));
  assert.deepEqual(renewalRowFor(findings, "ref:row:AI Units").value, { rowId: "ref:row:AI Units", demand12MoUnits: 1400000 });
  assert.equal(renewalRowFor(findings, "ref:row:AI Units").supersedes, undefined);
  assert.deepEqual(conflicts, []);
});

test("a figure this plan wrote is withdrawn to no figure when a line on its row becomes unsized", () => {
  const draft = plan();
  draft.pipeline.written = { "renewalTest:AI Units:demand12MoUnits": 1400000, "renewalTest:AI Units:demand6MoUnits": 400000, "renewalTest:AI Units:pipelineDriver": AI_DRIVERS };
  const { findings, conflicts, written } = numberFindings(draft, documentWithAiUnits({ demand12MoUnits: 1400000 }));
  assert.deepEqual(renewalRowFor(findings, "ref:row:AI Units").value, {
    rowId: "ref:row:AI Units", pipelineDriver: AI_DRIVERS_WITH_UNSIZED, demand6MoUnits: null, demand12MoUnits: null,
  });
  assert.equal(renewalRowFor(findings, "ref:row:AI Units").supersedes, REFRESHED);
  assert.deepEqual(conflicts, []);
  assert.equal(written["renewalTest:AI Units:demand12MoUnits"], null);
});

test("the plan's record may hold no figure, but nothing else that is not a number or text", () => {
  assert.doesNotThrow(() => numberFindings(withWritten({ "draw:006EXAMPLE0000001:AI Units": null }), merged()));
  assert.throws(() => numberFindings(withWritten({ "draw:006EXAMPLE0000001:AI Units": { units: 5 } }), merged()), (error) => error instanceof PipelineError && /pipeline\.written/.test(error.message));
});

test("a value already equal to Salesforce's is left alone, and recorded so a later change refreshes it", () => {
  const { findings, conflicts, written } = numberFindings(sizedPlan(), documentWithAiUnits({ demand12MoUnits: 1400000 }));
  assert.equal(renewalRowFor(findings, "ref:row:AI Units"), undefined);
  assert.deepEqual(conflicts, []);
  assert.equal(written["renewalTest:AI Units:demand12MoUnits"], 1400000);
});

test("an empty value is written without a supersedes, beside the ones that are refreshed", () => {
  const draft = withWritten({ "renewalTest:AI Units:demand12MoUnits": 999 });
  const { findings } = numberFindings(draft, documentWithAiUnits({ demand6MoUnits: null, pipelineDriver: "" }));
  assert.deepEqual(renewalRowFor(findings, "ref:row:AI Units").value, {
    rowId: "ref:row:AI Units", pipelineDriver: AI_DRIVERS, demand6MoUnits: 400000, demand12MoUnits: 1400000,
  });
  assert.equal(renewalRowFor(findings, "ref:row:AI Units").supersedes, REFRESHED, "the empty ones do not need it, the refreshed one does");
});

test("a team edit to the driver text is kept even while the demand it explains refreshes", () => {
  const draft = withWritten({ "renewalTest:AI Units:demand12MoUnits": 999 });
  const { findings, conflicts } = numberFindings(draft, documentWithAiUnits({ pipelineDriver: "Claims extraction, per the team" }));
  assert.deepEqual(renewalRowFor(findings, "ref:row:AI Units").value, { rowId: "ref:row:AI Units", demand12MoUnits: 1400000 });
  assert.equal(conflicts.length, 1);
  assert.match(conflicts[0], /pipelineDriver/);
});

/**
 * The merged document with opportunity 2 as a run before this plan stopped drawing for opportunities left it: a record,
 * a card, and a draw on AI Units.
 */
function documentWithDraw(units) {
  const document = documentWithAiUnits({ demand12MoUnits: 1400000 });
  document.pipelineOpportunities.push({ id: OPP_ID, key: "006EXAMPLE0000002", name: "Example Corp - AI Units Phase 2", stage: "Proposal", status: "Open", estimatedIarrUsd: 100000 });
  document.snapshot.pursuits.push({ id: "77777777-7777-4777-8777-000000000001", opportunityId: OPP_ID, cardStatus: "", draw: [{ id: "88888888-8888-4888-8888-000000000001", rowId: ROW_ID, units }] });
  return document;
}
/** The line a refresh gives an opportunity whose card still holds draws an earlier run of this plan wrote. */
const NO_LONGER_DRAWS = (named, rows) => `${named}: this plan no longer draws for opportunities, since an opportunity adds its own entitlement and draws nothing from today's rows; the ${rows.length === 1 ? "draw" : "draws"} it wrote earlier on ${rows.map((row) => `"${row}"`).join(" and ")} ${rows.length === 1 ? "remains" : "remain"} on its pursuit card. The AE removes ${rows.length === 1 ? "it" : "them"} in the app.`;
const PHASE_TWO = 'Opportunity "Example Corp - AI Units Phase 2" (006EXAMPLE0000002)';

test("a draw an earlier run wrote for an opportunity is reported, never refreshed or cleared: this plan no longer draws for opportunities", () => {
  const { findings, conflicts, written } = numberFindings(withWritten({ "draw:006EXAMPLE0000002:AI Units": 1000000 }), documentWithDraw(1000000));
  assert.equal(pursuitFor(findings, "006EXAMPLE0000002"), undefined, "nothing changes or clears the draw");
  assert.deepEqual(conflicts, [NO_LONGER_DRAWS(PHASE_TWO, ["AI Units"])]);
  assert.equal("draw:006EXAMPLE0000002:AI Units" in written, false, "the plan's record of what it wrote stands");

  const unsized = numberFindings(withWritten({ "draw:006EXAMPLE0000002:AI Units": null }), documentWithDraw(null));
  assert.deepEqual(unsized.conflicts, [NO_LONGER_DRAWS(PHASE_TWO, ["AI Units"])], "a draw line it wrote with no units is still the one it wrote");
});

test("a draw on an opportunity's card that is not what this plan wrote is the team's: it stays without a line, since this plan gives no draw to disagree with it", () => {
  for (const [label, draft, units] of [
    ["changed by the team", withWritten({ "draw:006EXAMPLE0000002:AI Units": 7 }), 5],
    ["cleared by the team", withWritten({ "draw:006EXAMPLE0000002:AI Units": 1000000 }), null],
    ["never written by this plan", sizedPlan(), 5],
  ]) {
    const { findings, conflicts, written } = numberFindings(draft, documentWithDraw(units));
    assert.equal(pursuitFor(findings, "006EXAMPLE0000002"), undefined, label);
    assert.deepEqual(conflicts, [], label);
    assert.equal(Object.keys(written).some((key) => key.startsWith("draw:")), false, label);
  }
});

test("an opportunity's draws this plan wrote that the team already removed, with their line or their card, are not reported", () => {
  const lineGone = documentWithDraw(1000000);
  lineGone.snapshot.pursuits[0].draw = [];
  const cardGone = documentWithDraw(1000000);
  cardGone.snapshot.pursuits = [];
  for (const document of [lineGone, cardGone]) {
    const { findings, conflicts } = numberFindings(withWritten({ "draw:006EXAMPLE0000002:AI Units": 1000000 }), document);
    assert.equal(pursuitFor(findings, "006EXAMPLE0000002"), undefined);
    assert.deepEqual(conflicts, [], "the card holds nothing this plan wrote, so there is nothing to remove");
  }
});

test("a renewal-test row this plan added that the team deleted is not added again, and is reported once", () => {
  const { findings, conflicts } = numberFindings(withWritten({
    "renewalTest:AI Units:pipelineDriver": AI_DRIVERS, "renewalTest:AI Units:demand6MoUnits": 400000, "renewalTest:AI Units:demand12MoUnits": 1400000,
  }), merged());
  assert.equal(renewalRowFor(findings, "ref:row:AI Units"), undefined);
  assert.ok(renewalRowFor(findings, "ref:row:Unattended Robot"), "a row the plan never wrote is added");
  assert.deepEqual(conflicts, [
    'renewalTest row "AI Units", which this plan added, is no longer in the document, so it is not added again. The AE confirms the removal or adds it back in the app.',
  ]);
});

test("an opportunity record this plan added that the team deleted is not added again, with its card, and is reported once", () => {
  const { findings, conflicts } = numberFindings(withWritten({
    "opportunity:006EXAMPLE0000001:status": "Open", "opportunity:006EXAMPLE0000001:products": '["AI Units Bundle 1K","Unattended Robot"]',
    "draw:006EXAMPLE0000001:AI Units": 400000, "draw:006EXAMPLE0000001:Unattended Robot": 20,
  }), merged());
  assert.deepEqual(opportunityRecord(findings, "006EXAMPLE0000001"), []);
  assert.equal(pursuitFor(findings, "006EXAMPLE0000001"), undefined);
  assert.deepEqual(conflicts, [
    'Opportunity "Example Corp - AI Units and Robot Expansion" (006EXAMPLE0000001): its record, which this plan added, is no longer in the document, so it is not added again; Salesforce still lists it open. The AE confirms the removal or adds it back in the app.',
  ], "one line, and none for the draws it wrote");
  assert.match(renewalRowFor(findings, "ref:row:Unattended Robot").value.pipelineDriver, /AI Units and Robot Expansion/, "it is still open in Salesforce, so it still drives demand");
});

// --- An opportunity the team added in the app ------------------------------------------------------------

/** The merged document with a record the team added in the app for opportunity 2: the app gives it the key "". */
function documentWithTeamRecord(changes = {}) {
  const document = merged();
  document.pipelineOpportunities.push({ id: OPP_ID, key: "", name: "Example Corp - AI Units Phase 2", stage: "Proposal", status: "Open", estimatedIarrUsd: 100000, owner: "A. Owner", ...changes });
  return document;
}

test("a record of the same name with no key is claimed by setting its key to the Salesforce id, not added again", () => {
  const { findings, conflicts } = numberFindings(sizedPlan(), documentWithTeamRecord({ name: " example corp – AI Units PHASE 2 " }));
  const sets = at("/pipelineOpportunities/0/key", findings);
  assert.deepEqual(sets, [{ op: "set", pointer: "/pipelineOpportunities/0/key", value: "006EXAMPLE0000002", source: "Salesforce Opportunity 006EXAMPLE0000002", asOf: "2026-07-30" }], "a fill: the key is empty, so nothing is superseded");
  const firstAdd = findings.findIndex((finding) => finding.value?.key === "006EXAMPLE0000002" || finding.value?.opportunityId === "ref:opportunity:006EXAMPLE0000002");
  assert.ok(findings.indexOf(sets[0]) < firstAdd, "the key is set before anything names the record by it");
  const [record] = opportunityRecord(findings, "006EXAMPLE0000002");
  assert.equal("stage" in record.value, false, "its record is the team's: equal fields are not asked to change");
  assert.deepEqual(record.value.products, ["AI Units Bundle 1K"], "and empty ones are filled");
  assert.equal(pursuitFor(findings, "006EXAMPLE0000002"), undefined, "and, as for any opportunity, no card draws for it");
  assert.equal(conflicts.length, 1, "the team's spelling of the name is kept");
  assert.match(conflicts[0], /name: kept " example corp – AI Units PHASE 2 "/);
});

test("a record of the same name keyed otherwise is left alone, with no second record, and the AE is asked to re-key it", () => {
  const { findings, conflicts } = numberFindings(sizedPlan(), documentWithTeamRecord({ key: "ai-units-phase-2" }));
  assert.equal(findings.some((finding) => JSON.stringify(finding).includes("006EXAMPLE0000002")), false, "no record, no key, no card");
  assert.deepEqual(conflicts, [
    'Opportunity "Example Corp - AI Units Phase 2" (006EXAMPLE0000002): the document has a record of that name keyed "ai-units-phase-2", so no second record is added. The AE changes its key to 006EXAMPLE0000002 in the app, so the next run fills it.',
  ]);
});

test("a same-named record keyed to another of the plan's opportunities is that one's, and is not claimed", () => {
  const draft = sizedPlan();
  draft.pipeline.opportunities[1].name = draft.pipeline.opportunities[0].name;
  const document = merged();
  document.pipelineOpportunities.push({ id: OPP_ID, key: "006EXAMPLE0000001", name: draft.pipeline.opportunities[0].name, status: "Open" });
  const { findings, conflicts } = numberFindings(draft, document);
  assert.equal(opportunityRecord(findings, "006EXAMPLE0000002").length, 1, "opportunity 2 gets a record of its own");
  assert.equal(findings.some((finding) => /\/key$/.test(finding.pointer)), false);
  assert.equal(conflicts.some((line) => /keyed/.test(line)), false);
});

test("two opportunities of one name claim one unkeyed record between them, never both", () => {
  const draft = sizedPlan();
  draft.pipeline.opportunities[1].name = "Example Corp - AI Units Phase 2";
  draft.pipeline.opportunities[0].name = "Example Corp - AI Units Phase 2";
  const { findings } = numberFindings(draft, documentWithTeamRecord());
  assert.equal(findings.filter((finding) => finding.pointer === "/pipelineOpportunities/0/key").length, 1);
  assert.equal(opportunityRecord(findings, "006EXAMPLE0000002")[0].value.name, "Example Corp - AI Units Phase 2", "the other gets a new record");
});

// --- Salesforce's facts and the team's name ---------------------------------------------------------------

test("stage and amount that differ from the document's are Salesforce's to say, in a finding of their own; a name the team changed is kept", () => {
  const document = merged();
  document.pipelineOpportunities.push({
    id: OPP_ID, key: "006EXAMPLE0000001", name: "Team's short name", stage: "Proposal", status: "Open", estimatedIarrUsd: 90000,
    products: ["AI Units Bundle 1K", "Unattended Robot"], consumptionRowIds: [], projectedConsumption: "The team's own estimate",
  });
  const { findings, conflicts } = numberFindings(plan(), document);
  const [fresh, system] = opportunityRecord(findings, "006EXAMPLE0000001");
  assert.deepEqual(fresh.value, { key: "006EXAMPLE0000001", consumptionRowIds: ["ref:row:AI Units", "ref:row:Unattended Robot"] }, "the empty field is written; the equal ones are not asked to change");
  assert.equal(fresh.supersedes, undefined);
  assert.deepEqual(system.value, { key: "006EXAMPLE0000001", stage: "Negotiation", estimatedIarrUsd: 120000 });
  assert.equal(system.supersedes, SORS);
  assert.equal(opportunityRecord(findings, "006EXAMPLE0000001").length, 2);
  assert.equal(conflicts.length, 2, "the team's name and its own estimate are kept and reported");
  assert.match(conflicts[0], /^pipelineOpportunities "Example Corp - AI Units and Robot Expansion" name: kept "Team's short name", which this plan did not write;/);
  assert.match(conflicts[1], /projectedConsumption/);
});

test("a name the team shortened survives a refresh; one this plan wrote follows Salesforce", () => {
  const document = merged();
  document.pipelineOpportunities.push({ id: OPP_ID, key: "006EXAMPLE0000001", name: "AI and robots", stage: "Negotiation", status: "Open", estimatedIarrUsd: 120000 });
  const kept = numberFindings(withWritten({ "opportunity:006EXAMPLE0000001:name": "Example Corp - AI Units and Robot Expansion" }), document);
  assert.equal(opportunityRecord(kept.findings, "006EXAMPLE0000001").some((finding) => "name" in finding.value), false);
  assert.equal(kept.conflicts.filter((line) => /name: kept "AI and robots"/.test(line)).length, 1);
  assert.equal("opportunity:006EXAMPLE0000001:name" in kept.written, false);

  const renamed = withWritten({ "opportunity:006EXAMPLE0000001:name": "AI and robots" });
  const refreshed = opportunityRecord(numberFindings(renamed, document).findings, "006EXAMPLE0000001").find((finding) => "name" in finding.value);
  assert.equal(refreshed.value.name, "Example Corp - AI Units and Robot Expansion", "the plan wrote the old name, so it is stale, not the team's");
  assert.equal(refreshed.supersedes, REFRESHED);
});

test("a projected consumption this plan wrote is refreshed with its own reason, apart from Salesforce's facts", () => {
  const document = merged();
  document.pipelineOpportunities.push({
    id: OPP_ID, key: "006EXAMPLE0000001", name: "Example Corp - AI Units and Robot Expansion", stage: "Proposal", status: "Open", estimatedIarrUsd: 120000,
    products: ["AI Units Bundle 1K", "Unattended Robot"], consumptionRowIds: [], projectedConsumption: "AI Units: 300000 units; Unattended Robot: 20 robots",
  });
  const draft = withWritten({ "opportunity:006EXAMPLE0000001:projectedConsumption": "AI Units: 300000 units; Unattended Robot: 20 robots" });
  const { findings, conflicts } = numberFindings(draft, document);
  const records = opportunityRecord(findings, "006EXAMPLE0000001");
  assert.deepEqual(records.map((record) => record.supersedes), [undefined, SORS, REFRESHED]);
  assert.deepEqual(records[1].value, { key: "006EXAMPLE0000001", stage: "Negotiation" });
  assert.deepEqual(records[2].value, { key: "006EXAMPLE0000001", projectedConsumption: "AI Units: 400000 units; Unattended Robot: 20 robots" });
  assert.deepEqual(conflicts, []);
});

test("a status, product list or row list the team changed is kept and reported", () => {
  const document = merged();
  rowOf(document, "AI Units").id = ROW_ID;
  document.pipelineOpportunities.push({
    id: OPP_ID, key: "006EXAMPLE0000003", name: "Example Corp - Robot Expansion FY28", stage: "Prospecting", status: "On Hold", estimatedIarrUsd: 5000,
    products: ["Something else"], consumptionRowIds: [ROW_ID], projectedConsumption: "Unattended Robot: 10 robots",
  });
  const { findings, conflicts } = numberFindings(plan(), document);
  assert.deepEqual(opportunityRecord(findings, "006EXAMPLE0000003"), [], "nothing to write: every field is equal or the team's");
  assert.equal(conflicts.length, 3);
  for (const field of ["status", "products", "consumptionRowIds"]) assert.ok(conflicts.some((line) => line.includes(field)), field);
});

test("a product list and a row list this plan wrote are refreshed, apart from the sizing and Salesforce's facts", () => {
  const document = merged();
  rowOf(document, "AI Units").id = ROW_ID;
  const record = {
    id: OPP_ID, key: "006EXAMPLE0000002", name: "Example Corp - AI Units Phase 2", stage: "Proposal", status: "Open", estimatedIarrUsd: 100000,
    products: ["An earlier product"], consumptionRowIds: [], projectedConsumption: "AI Units: 1000000 units",
  };
  document.pipelineOpportunities.push(record);
  const written = {
    "opportunity:006EXAMPLE0000002:products": '["An earlier product"]',
    "opportunity:006EXAMPLE0000002:projectedConsumption": "AI Units: 1000000 units",
  };
  const refreshed = numberFindings(withWritten(written), document);
  const records = opportunityRecord(refreshed.findings, "006EXAMPLE0000002");
  assert.deepEqual(records.map((entry) => [entry.value, entry.supersedes]), [
    [{ key: "006EXAMPLE0000002", consumptionRowIds: ["ref:row:AI Units"] }, undefined],
    [{ key: "006EXAMPLE0000002", products: ["AI Units Bundle 1K"] }, REFRESHED],
  ]);
  assert.deepEqual(refreshed.conflicts, []);
  assert.equal(refreshed.written["opportunity:006EXAMPLE0000002:products"], '["AI Units Bundle 1K"]');

  const kept = numberFindings(plan(), document);
  assert.deepEqual(opportunityRecord(kept.findings, "006EXAMPLE0000002").map((entry) => Object.keys(entry.value)), [["key", "consumptionRowIds"]]);
  assert.equal(kept.conflicts.length, 1, "the team's product list stays");
  assert.match(kept.conflicts[0], /products/);
  assert.match(kept.conflicts[0], /An earlier product/);
  assert.match(kept.conflicts[0], /AI Units Bundle 1K/);
});

test("a row list is compared by the plan rows its ids name, so rows getting ids changes nothing", () => {
  const document = merged();
  rowOf(document, "AI Units").id = ROW_ID;
  rowOf(document, "Unattended Robot").id = "11111111-1111-4111-8111-000000000002";
  document.pipelineOpportunities.push({
    id: OPP_ID, key: "006EXAMPLE0000001", name: "Example Corp - AI Units and Robot Expansion", stage: "Negotiation", status: "Open", estimatedIarrUsd: 120000,
    products: ["Unattended Robot", "AI Units Bundle 1K"], consumptionRowIds: ["11111111-1111-4111-8111-000000000002", ROW_ID], projectedConsumption: "AI Units: 400000 units; Unattended Robot: 20 robots",
  });
  const { findings, conflicts, written } = numberFindings(plan(), document);
  assert.deepEqual(opportunityRecord(findings, "006EXAMPLE0000001"), [], "the same rows and products in another order are the same");
  assert.deepEqual(conflicts, []);
  assert.equal(written["opportunity:006EXAMPLE0000001:consumptionRowIds"], '["AI Units","Unattended Robot"]');
});

// --- Values the plan wrote for what has left the plan ----------------------------------------------------

const GONE_OPPORTUNITY = /^Opportunity 006GONE0000001 is no longer open in this plan; its card, draws and demand remain in the document\. The AE confirms its Salesforce status and closes or removes it in the app\.$/;

test("an opportunity the plan wrote values for that is no longer open is reported once, by its Salesforce id, and nothing is cleared", () => {
  const draft = withWritten({
    "draw:006GONE0000001:AI Units": 5,
    "draw:006GONE0000001:Unattended Robot": 2,
    "opportunity:006GONE0000001:status": "Open",
    "opportunity:006GONE0000001:projectedConsumption": "AI Units: 5 units",
    "draw:006EXAMPLE0000001:AI Units": 400000,
  });
  const { findings, conflicts } = numberFindings(draft, merged());
  assert.equal(conflicts.length, 1, "one line for the opportunity, however many values it wrote; opportunity 1 is still open");
  assert.match(conflicts[0], GONE_OPPORTUNITY);
  assert.equal(findings.some((finding) => JSON.stringify(finding).includes("006GONE")), false, "no finding clears or changes what it left");
});

test("an opportunity that is in the plan but stale or a renewal is no longer open in it, and is reported too", () => {
  const { conflicts } = numberFindings(withWritten({
    "draw:006EXAMPLE0000005:Unattended Robot": 50, "opportunity:006EXAMPLE0000004:status": "Open",
  }), merged());
  assert.equal(conflicts.length, 2);
  assert.match(conflicts[0], /006EXAMPLE0000005/);
  assert.match(conflicts[1], /006EXAMPLE0000004/);
});

test("a renewal-test row the plan wrote a driver or demand for, with no opportunity sourcing it now, is reported once", () => {
  const draft = withWritten({
    "renewalTest:Gone Row:pipelineDriver": "Gone Opp (Oct 26)",
    "renewalTest:Gone Row:demand6MoUnits": 10,
    "renewalTest:Gone Row:demand12MoUnits": 10,
    "renewalTest:AI Units:demand12MoUnits": 1400000,
  });
  const { findings, conflicts } = numberFindings(draft, documentWithAiUnits({ demand12MoUnits: 1400000 }));
  assert.equal(conflicts.length, 1, "AI Units still has demand, and its row is still in the document");
  assert.match(conflicts[0], /renewalTest row "Gone Row"/);
  assert.match(conflicts[0], /remain in the document/);
  assert.match(conflicts[0], /AE/);
  assert.equal(findings.some((finding) => JSON.stringify(finding).includes("Gone Row")), false);
});

test("draws this plan wrote for an open opportunity are one line naming each row its card still holds, sized by the opportunity or not, and are not cleared", () => {
  const ROBOT_ID = "11111111-1111-4111-8111-000000000002";
  const document = documentWithDraw(1000000);
  rowOf(document, "Unattended Robot").id = ROBOT_ID;
  document.snapshot.pursuits[0].draw.push({ id: "88888888-8888-4888-8888-000000000002", rowId: ROBOT_ID, units: 9 });
  const { findings, conflicts } = numberFindings(withWritten({ "draw:006EXAMPLE0000002:AI Units": 1000000, "draw:006EXAMPLE0000002:Unattended Robot": 9 }), document);
  assert.deepEqual(conflicts, [NO_LONGER_DRAWS(PHASE_TWO, ["AI Units", "Unattended Robot"])], "opportunity 2 never sized the robots; that draw is in the same line, not one of its own as a draw no longer in its lines");
  assert.equal(findings.some((finding) => finding.pointer === "/snapshot/pursuits"), false, "nothing clears or changes them");
});

test("an opportunity that has left the plan yields its one departure line, not one per draw it wrote", () => {
  const { conflicts } = numberFindings(withWritten({
    "draw:006GONE0000001:AI Units": 5, "draw:006GONE0000001:Unattended Robot": 2, "draw:006GONE0000001:Automation Developer": 1,
  }), merged());
  assert.equal(conflicts.length, 1);
  assert.match(conflicts[0], GONE_OPPORTUNITY);
});

test("draws this plan wrote for an opportunity that now closes beyond 12 months stay on its card, reported once as any opportunity's are", () => {
  const document = merged();
  rowOf(document, "Unattended Robot").id = ROW_ID;
  document.pipelineOpportunities.push({ id: OPP_ID, key: "006EXAMPLE0000003", name: "Example Corp - Robot Expansion FY28", stage: "Prospecting", status: "Open", estimatedIarrUsd: 5000 });
  document.snapshot.pursuits.push({ id: "77777777-7777-4777-8777-000000000001", opportunityId: OPP_ID, cardStatus: "", draw: [{ id: "88888888-8888-4888-8888-000000000001", rowId: ROW_ID, units: 10 }] });
  const { findings, conflicts } = numberFindings(withWritten({ "draw:006EXAMPLE0000003:Unattended Robot": 10 }), document);
  assert.equal(pursuitFor(findings, "006EXAMPLE0000003"), undefined, "nothing changes or clears the draw");
  assert.deepEqual(conflicts, [
    NO_LONGER_DRAWS('Opportunity "Example Corp - Robot Expansion FY28" (006EXAMPLE0000003)', ["Unattended Robot"]),
  ], "one line for the opportunity, not one per draw; its close date is no longer why it draws nothing");
});

test("a plan that has written nothing reports nothing as gone", () => {
  assert.deepEqual(numberFindings(plan(), merged()).conflicts, []);
});

test("a contract date that differs from the document's carries supersedes: Salesforce is the system of record", () => {
  const document = merged();
  document.renewalDate = "2026-11-01";
  document.snapshot.contractStartDate = "2025-12-01";
  const { findings } = numberFindings(plan(), document);
  assert.deepEqual(at("/renewalDate", findings), [
    { op: "set", pointer: "/renewalDate", value: "2026-12-01", source: "Salesforce Contract 00000001", asOf: "2026-08-01", supersedes: SORS },
  ]);
  assert.deepEqual(at("/snapshot/contractStartDate", findings), [], "already equal");
});

// --- Other pipeline activity ---------------------------------------------------------------------------

/** The merged document with a record for every open opportunity of the plan, as the numbers stage leaves it. */
function documentWithRecords(draft = sizedPlan()) {
  const document = merged(draft);
  for (const { value } of numberFindings(draft, document).findings.filter((finding) => finding.pointer === "/pipelineOpportunities")) {
    document.pipelineOpportunities.push({ id: `id-${value.key}`, key: value.key, status: value.status, estimatedIarrUsd: value.estimatedIarrUsd });
  }
  return document;
}

test("other pipeline activity prices what the Snapshot's top three cards leave out", () => {
  const { findings, conflicts, written } = otherActivityFindings(sizedPlan(), documentWithRecords());
  assert.deepEqual(findings, [{
    op: "set", pointer: "/snapshot/otherPipelineActivityUsd", value: 30000, source: "Salesforce Opportunities priced at contracted unit prices", asOf: "2026-08-01",
  }]);
  assert.deepEqual(conflicts, []);
  assert.deepEqual(written, { otherPipelineActivityUsd: 30000 });
});

test("other pipeline activity is whole US dollars", () => {
  const draft = planWith([opportunity("2026-10-01", { id: "006BIG", units: 1234567, row: "AI Units" })]);
  const { findings } = otherActivityFindings(draft, blankDocument());
  assert.equal(otherActivityUsd(draft, []).usd, 1234567 * 0.04, "the exact price is a fraction of a dollar");
  assert.equal(findings[0].value, 49383);
});

test("other pipeline activity follows the refresh rule", () => {
  const document = (value) => ({ ...documentWithRecords(), snapshot: { ...blankDocument().snapshot, otherPipelineActivityUsd: value } });
  const refreshed = otherActivityFindings(withWritten({ otherPipelineActivityUsd: 20000 }), document(20000));
  assert.equal(refreshed.findings[0].value, 30000);
  assert.equal(refreshed.findings[0].supersedes, REFRESHED);
  assert.equal(refreshed.written.otherPipelineActivityUsd, 30000);

  const kept = otherActivityFindings(withWritten({ otherPipelineActivityUsd: 10000 }), document(20000));
  assert.deepEqual(kept.findings, []);
  assert.equal(kept.conflicts.length, 1);
  assert.match(kept.conflicts[0], /otherPipelineActivityUsd/);
  assert.deepEqual(kept.written, {});

  const equal = otherActivityFindings(sizedPlan(), document(30000));
  assert.deepEqual(equal.findings, []);
  assert.deepEqual(equal.conflicts, []);
  assert.deepEqual(equal.written, { otherPipelineActivityUsd: 30000 });

  const zero = otherActivityFindings(planWith([]), document(0));
  assert.deepEqual(zero.findings, [], "a stated zero is a value: 0 equals 0");

  const cleared = otherActivityFindings(withWritten({ otherPipelineActivityUsd: 30000 }), document(null));
  assert.deepEqual(cleared.findings, [], "a figure the team cleared is not put back");
  assert.deepEqual(cleared.conflicts, ["snapshot.otherPipelineActivityUsd: left blank, as the account team cleared it (this plan wrote 30000); Salesforce opportunities now give 30000."]);
  assert.deepEqual(cleared.written, {});
});

test("other pipeline activity is not written when an unshown opportunity has an unsized line, and says which", () => {
  const { findings, conflicts, written } = otherActivityFindings(plan(), documentWithRecords(plan()));
  assert.deepEqual(findings, []);
  assert.deepEqual(written, { otherPipelineActivityUsd: null }, "no figure, recorded as what this plan gives");
  assert.deepEqual(conflicts, ["snapshot.otherPipelineActivityUsd not written: 1 line(s) have no unit volume to value them: Example Corp - AI Units Enterprise Agreement (AI Units)."]);
});

test("other pipeline activity is not written when a sized line has no price to value it, and says why", () => {
  const draft = sizedPlan();
  draft.rows.find((row) => row.product === "Unattended Robot").arrUsd = null;
  const { findings, conflicts, written } = otherActivityFindings(draft, documentWithRecords());
  assert.deepEqual(findings, []);
  assert.deepEqual(written, { otherPipelineActivityUsd: null });
  assert.equal(conflicts.length, 1);
  assert.match(conflicts[0], /Unattended Robot/);
  assert.match(conflicts[0], /Robot Expansion FY28/);
});

// --- Rows that share an offering ---------------------------------------------------------------------

/** The fixture with "AI Units" under Consumables and again under Platform / Capabilities, its lines naming the first by category. */
function planWithTwoAiUnits() {
  const draft = plan();
  draft.rows.push({
    category: "Platform / Capabilities", product: "AI Units", productCode: "", unit: "units", licensingModel: "", arrUsd: 0, discountPercent: null,
    purchasedQuantity: 500000, consumedQuantity: null, forecastUnits: { q1: null, q2: null, q3: null, q4: null }, notes: "",
  });
  for (const { lines } of draft.pipeline.opportunities) {
    for (const line of lines) if (line.row === "AI Units") line.row = "Consumables|AI Units";
  }
  return draft;
}

test("rows that share an offering are named category|offering, and the rest by offering alone", () => {
  const draft = planWithTwoAiUnits();
  assert.deepEqual([...locatePlanRows(draft, merged(draft))], [
    ["Automation Developer", "ref:row:Automation Developer"],
    ["Unattended Robot", "ref:row:Unattended Robot"],
    ["Consumables|AI Units", "ref:row:Consumables|AI Units"],
    ["Platform - Standard", "ref:row:Platform - Standard"],
    ["Platform / Capabilities|AI Units", "ref:row:Platform / Capabilities|AI Units"],
  ]);
});

test("a plan with no shared offering names every row by its offering", () => {
  assert.deepEqual([...locatePlanRows(plan(), merged()).values()], [
    "ref:row:Automation Developer", "ref:row:Unattended Robot", "ref:row:AI Units", "ref:row:Platform - Standard",
  ]);
});

test("an offering the team already has under another category makes the plan's row ambiguous, so both are named by category", () => {
  const document = merged();
  document.consumptionPlan.groups.push({ element: "Other", rows: [{ offering: "ai units" }] });
  const tokens = locatePlanRows(plan(), document);
  assert.equal(tokens.get("AI Units"), "ref:row:Consumables|AI Units");
});

test("shared offerings are told apart by category before document order, in the document the merge made", () => {
  const draft = planWithTwoAiUnits();
  draft.rows.reverse();
  const baseline = blankDocument();
  baseline.consumptionPlan.groups.push({ element: "Consumables", rows: [] }, { element: "Platform / Capabilities", rows: [{ id: ROW_ID, offering: "AI Units" }] });
  const document = merged(draft, baseline);
  assert.equal(document.consumptionPlan.groups[0].rows.length, 1, "the merge gave the Consumables row to the plan's Consumables entry");
  assert.equal(document.consumptionPlan.groups[1].rows[0].id, ROW_ID);
  assert.equal(locatePlanRows(draft, document).get("Platform / Capabilities|AI Units"), "ref:row:Platform / Capabilities|AI Units");
  assert.equal(locatePlanRows(draft, document).get("Consumables|AI Units"), "ref:row:Consumables|AI Units");
});

test("findings name a shared offering's row by category", () => {
  const draft = planWithTwoAiUnits();
  draft.pipeline.useCases = [useCase({ lines: [{ product: "AI Units", units: 200000, row: "Consumables|AI Units" }] })];
  const { findings } = numberFindings(draft, merged(draft));
  assert.ok(renewalRowFor(findings, "ref:row:Consumables|AI Units"), "the demand is keyed by the row the lines named");
  assert.deepEqual(pursuitFor(findings, "invoice-intake-agent").value.draw, [{ rowId: "ref:row:Consumables|AI Units", units: 200000 }], "and so is a use case's draw");
  assert.deepEqual(opportunityRecord(findings, "006EXAMPLE0000001")[0].value.consumptionRowIds, ["ref:row:Consumables|AI Units", "ref:row:Unattended Robot"]);
  assert.match(opportunityRecord(findings, "006EXAMPLE0000001")[0].value.projectedConsumption, /^AI Units \(Consumables\): 400000 units;/);
});

// --- A plan grouped by contract: the row's kind says what it is ---------------------------------------

const CONTRACT_ONE = "Example Corp · contract 00000001";
const CONTRACT_TWO = "Example Corp Sub · contract 00000002";
const PLATFORM_ROW = "Platform - Standard";

/**
 * The fixture as a customer on two contracts has it: each row's category is its contract's label, and its kind
 * (unless `withKinds` is false) is the product kind its category was.
 */
function groupedPlan({ withKinds = true } = {}) {
  const draft = plan();
  for (const row of draft.rows) {
    const kind = row.category;
    row.category = kind === "Users" || kind === "Robots" ? CONTRACT_ONE : CONTRACT_TWO;
    if (withKinds) row.kind = kind;
  }
  return draft;
}

test("in a plan grouped by contract, a platform-kind line adds no demand and no draw", () => {
  const draft = groupedPlan();
  const { byRow, open, unmapped, unsized } = pipelineDemand(draft);
  const platform = open.find((candidate) => candidate.salesforceId === "006EXAMPLE0000008");
  assert.ok(platform, "the opportunity is open");
  assert.equal(byRow.has(PLATFORM_ROW), false);
  assert.equal(unmapped.some(({ opportunity }) => opportunity === platform), false);
  assert.equal(unsized.some(({ opportunity }) => opportunity === platform), false);
  const [line] = platform.lines;
  assert.equal(isConsumptionLine(draft, line), false);
  assert.equal(isConsumptionLine(draft, { ...line, row: "Unattended Robot" }), true);

  const { findings } = numberFindings(draft, merged(draft));
  assert.equal(pursuitFor(findings, "006EXAMPLE0000008"), undefined, "no card draws on a platform tier");
  assert.equal(renewalRowFor(findings, `ref:row:${PLATFORM_ROW}`), undefined, "and no Renewal Test row carries its demand");
  assert.equal("projectedConsumption" in opportunityRecord(findings, "006EXAMPLE0000008")[0].value, false);
});

test("a grouped plan with kinds draws, prices and demands exactly as the ungrouped fixture does", () => {
  const grouped = groupedPlan();
  assert.deepEqual([...pipelineDemand(grouped).byRow], [...pipelineDemand(plan()).byRow]);
  assert.deepEqual([...unitPriceByRow(grouped)], [...unitPriceByRow(plan())]);
  assert.deepEqual(totals(otherActivityUsd(grouped, [])), totals(otherActivityUsd(plan(), [])));
  const [byKind, byCategory] = [numberFindings(grouped, merged(grouped)), numberFindings(plan(), merged())];
  assert.deepEqual(byKind.findings.map(({ pointer }) => pointer), byCategory.findings.map(({ pointer }) => pointer));
  assert.deepEqual(byKind.written, byCategory.written);
});

test("a plan whose rows carry kinds equal to their categories behaves as it did without them", () => {
  const withKinds = plan();
  for (const row of withKinds.rows) row.kind = row.category;
  assert.deepEqual(numberFindings(withKinds, merged(withKinds)), numberFindings(plan(), merged()));
  assert.deepEqual(otherActivityFindings(withKinds, merged(withKinds)), otherActivityFindings(plan(), merged()));
  assert.deepEqual([...pipelineDemand(withKinds).byRow], [...pipelineDemand(plan()).byRow]);
});

test("a row with no kind is decided by its category, so a grouped plan without kinds cannot tell a platform tier", () => {
  const draft = groupedPlan({ withKinds: false });
  const platform = pipelineDemand(draft).open.find((candidate) => candidate.salesforceId === "006EXAMPLE0000008");
  assert.equal(isConsumptionLine(draft, platform.lines[0]), true, "a contract label says nothing about the row");
  assert.equal(pipelineDemand(draft).byRow.has(PLATFORM_ROW), true);
  const fixture = plan();
  assert.equal(isConsumptionLine(fixture, platform.lines[0]), false, "an ungrouped row's own category still does");
});

test("a row's kind outranks its category when it names one", () => {
  const draft = plan();
  const tier = draft.rows.find((row) => row.product === PLATFORM_ROW);
  tier.kind = "Consumables";
  const line = pipelineDemand(draft).open.find((candidate) => candidate.salesforceId === "006EXAMPLE0000008").lines[0];
  assert.equal(isConsumptionLine(draft, line), true, "kind Consumables under a Platform / Capabilities category is consumed");
  const robot = draft.rows.find((row) => row.product === "Unattended Robot");
  robot.kind = "Platform / Capabilities";
  assert.equal(isConsumptionLine(draft, { ...line, row: "Unattended Robot" }), false, "kind Platform / Capabilities under Robots is granted");
  tier.kind = "";
  assert.equal(isConsumptionLine(draft, line), false, "an empty kind falls back to the category");
});

test("a kind that is not one of the four product kinds is refused wherever the plan is read", () => {
  const draft = groupedPlan();
  draft.rows[3].kind = "Platform";
  const refused = (error) => error instanceof toDay2Module.PlanError && /rows\[3\]\.kind must be/.test(error.message);
  assert.throws(() => pipelineDemand(draft), refused);
  assert.throws(() => numberFindings(draft, merged(groupedPlan())), refused);
  assert.throws(() => otherActivityFindings(draft, merged(groupedPlan())), refused);
  assert.throws(() => unitPriceByRow(draft), refused);
  assert.throws(() => locatePlanRows(draft, merged(groupedPlan())), refused);
});

// --- The team's forecast wins ---------------------------------------------------------------------------
//
// From asOf 2026-08-01 (FY27 Q3) the quarters are q1 FY27 Q4 (from 2026-11-01), q2 FY28 Q1 (2027-02-01),
// q3 FY28 Q2 (2027-05-01) and q4 FY28 Q3 (2027-08-01).

const FORECAST = "team forecast (forecastUnits)";
const FORECAST_REFRESHED = "refreshed from the team forecast (forecastUnits) as of 2026-08-01";
const OPPORTUNITIES_SOURCE = "Salesforce Opportunities closing within 12 months of 2026-08-01";

/** The sized plan with a renewal date and the given rows' quarterly forecasts (and any other row fields). */
function forecastPlan(renewalDate, rows) {
  const draft = sizedPlan();
  draft.contract.renewalDate = renewalDate;
  for (const [product, changes] of Object.entries(rows)) Object.assign(draft.rows.find((row) => row.product === product), changes);
  return draft;
}
const quarters = (q1, q2, q3, q4) => ({ forecastUnits: { q1, q2, q3, q4 } });

test("a consumable row with a team forecast takes q1 + q2 and q1..q4, counting only quarters that start before the renewal, even where an opportunity sizes it", () => {
  const draft = forecastPlan("2027-06-01", { "AI Units": quarters(100000, 150000, 200000, 250000) });
  assert.deepEqual(pipelineDemand(draft).byRow.get("AI Units"), {
    demand6MoUnits: 250000,
    demand12MoUnits: 450000,
    drivers: ["Example Corp - AI Units and Robot Expansion (Oct 26)", "Example Corp - AI Units Phase 2 (May 27)"],
    asOf: "2026-07-30",
    teamForecast: { windows: ["demand6MoUnits", "demand12MoUnits"], asOf: "2026-08-01" },
  }, "q4 starts after the 2027-06-01 renewal, so it is a renewal question; the opportunities' 400000 and 1400000 give way, and still drive the row");

  draft.pipeline.useCases = [useCase()]; // no start date: it adds no demand and no driver, and draws
  const { findings } = numberFindings(draft, merged(draft));
  assert.deepEqual(at("/renewalTest/rows", findings).filter((finding) => finding.value.rowId === "ref:row:AI Units"), [
    { op: "add", pointer: "/renewalTest/rows", value: { rowId: "ref:row:AI Units", pipelineDriver: AI_DRIVERS }, source: OPPORTUNITIES_SOURCE, asOf: "2026-07-30" },
    { op: "add", pointer: "/renewalTest/rows", value: { rowId: "ref:row:AI Units", demand6MoUnits: 250000, demand12MoUnits: 450000 }, source: FORECAST, asOf: "2026-08-01" },
  ], "the driver keeps its own source; the demand is the team's forecast, dated by the plan");
  assert.deepEqual(pursuitFor(findings, "invoice-intake-agent").value.draw, [{ rowId: "ref:row:AI Units", units: 200000 }, { rowId: "ref:row:Unattended Robot", units: 4 }], "the pursuit draws still come from the use case's lines");
  assert.equal(pursuitFor(findings, "006EXAMPLE0000001"), undefined, "and an opportunity draws nothing, forecast or not");
});

test("the team forecast's demand is dated by the row's consumed-as-of date when it has one", () => {
  const draft = forecastPlan("2027-06-01", {
    "AI Units": { ...quarters(100000, 150000, 200000, 250000), consumedQuantity: 300000, consumedBasis: "telemetry", consumedAsOf: "2026-07-15" },
  });
  assert.equal(pipelineDemand(draft).byRow.get("AI Units").teamForecast.asOf, "2026-07-15");
  const finding = at("/renewalTest/rows", numberFindings(draft, merged(draft)).findings).find((candidate) => candidate.source === FORECAST);
  assert.equal(finding.asOf, "2026-07-15");
  assert.deepEqual([finding.value.demand6MoUnits, finding.value.demand12MoUnits], [250000, 450000], "a consumable's quarters add; its consumed figure is not taken off");
});

test("a renewal inside the six-month window cuts both windows at it, and a plan with no renewal date counts all four quarters", () => {
  const forecast = quarters(100000, 150000, 200000, 250000);
  const early = pipelineDemand(forecastPlan("2026-12-01", { "AI Units": forecast })).byRow.get("AI Units");
  assert.deepEqual([early.demand6MoUnits, early.demand12MoUnits], [100000, 100000], "only q1 starts before a 2026-12-01 renewal, so +12 months still includes the +6-month units");
  const none = pipelineDemand(forecastPlan("", { "AI Units": forecast })).byRow.get("AI Units");
  assert.deepEqual([none.demand6MoUnits, none.demand12MoUnits], [250000, 700000]);
  const onStart = pipelineDemand(forecastPlan("2027-02-01", { "AI Units": forecast })).byRow.get("AI Units");
  assert.deepEqual([onStart.demand6MoUnits, onStart.demand12MoUnits], [100000, 100000], "a quarter starting on the renewal date is after it");
});

test("a renewal before q1 starts leaves the team forecast no quarter, so both windows fall back to the opportunity rule", () => {
  const before = pipelineDemand(forecastPlan("2026-10-15", { "AI Units": quarters(100000, 150000, 200000, 250000) })).byRow.get("AI Units");
  assert.deepEqual(before, pipelineDemand(sizedPlan()).byRow.get("AI Units"));
});

test("a peak row's demand is the window's busiest quarter minus its consumed figure, never below zero, and unknown with no consumed figure", () => {
  const robots = (forecast, consumedQuantity = 60) => pipelineDemand(forecastPlan("2027-12-01", { "Unattended Robot": { ...forecast, consumedQuantity } })).byRow.get("Unattended Robot");
  const peak = robots(quarters(65, 85, 70, 90));
  assert.deepEqual([peak.demand6MoUnits, peak.demand12MoUnits], [25, 30], "85 - 60 and 90 - 60, not the quarters' sums and not the opportunity's 20");
  assert.deepEqual(peak.drivers, ["Example Corp - AI Units and Robot Expansion (Oct 26)"]);
  const below = robots(quarters(50, 55, 40, 58));
  assert.deepEqual([below.demand6MoUnits, below.demand12MoUnits], [0, 0]);
  const unmeasured = robots(quarters(65, 85, 70, 90), null);
  assert.deepEqual([unmeasured.demand6MoUnits, unmeasured.demand12MoUnits], [null, null], "without a consumed figure a peak says nothing about new demand");
});

test("a user-license row is a peak row too, and a row the team forecasts that no opportunity sizes gets demand and no driver", () => {
  const draft = forecastPlan("2027-12-01", { "Automation Developer": { ...quarters(14, 15, 18, 16), consumedQuantity: 12, consumedBasis: "statement", consumedAsOf: "2026-07-20" } });
  assert.deepEqual(pipelineDemand(draft).byRow.get("Automation Developer"), {
    demand6MoUnits: 3, demand12MoUnits: 6, drivers: [], asOf: "", teamForecast: { windows: ["demand6MoUnits", "demand12MoUnits"], asOf: "2026-07-20" },
  });
  assert.deepEqual(renewalRowFor(numberFindings(draft, merged(draft)).findings, "ref:row:Automation Developer"), {
    op: "add", pointer: "/renewalTest/rows", value: { rowId: "ref:row:Automation Developer", demand6MoUnits: 3, demand12MoUnits: 6 }, source: FORECAST, asOf: "2026-07-20",
  }, "no pipeline names the row, so it has no driver to write");
});

test("a platform tier's forecast adds no demand: a tier is granted, not consumed", () => {
  const draft = forecastPlan("2027-12-01", { "Platform - Standard": quarters(1, 1, 1, 1) });
  assert.equal(pipelineDemand(draft).byRow.has("Platform - Standard"), false);
});

test("a window whose quarters are not all forecast falls back to the opportunity rule, window by window", () => {
  const draft = forecastPlan("2027-12-01", { "AI Units": quarters(100000, 150000, null, 250000) });
  const demand = pipelineDemand(draft).byRow.get("AI Units");
  assert.deepEqual([demand.demand6MoUnits, demand.demand12MoUnits], [250000, 1400000], "q3 is not set, so +12 months is the opportunities' figure");
  assert.deepEqual(demand.teamForecast.windows, ["demand6MoUnits"]);
  const rows = at("/renewalTest/rows", numberFindings(draft, merged(draft)).findings).filter((finding) => finding.value.rowId === "ref:row:AI Units");
  assert.deepEqual(rows.map(({ value, source }) => [value, source]), [
    [{ rowId: "ref:row:AI Units", pipelineDriver: AI_DRIVERS, demand12MoUnits: 1400000 }, OPPORTUNITIES_SOURCE],
    [{ rowId: "ref:row:AI Units", demand6MoUnits: 250000 }, FORECAST],
  ]);

  const noFirst = forecastPlan("2027-12-01", { "AI Units": quarters(null, 150000, 200000, 250000) });
  assert.deepEqual(pipelineDemand(noFirst).byRow.get("AI Units"), pipelineDemand(sizedPlan()).byRow.get("AI Units"), "without q1 neither window is forecast");
});

test("a row with no team forecast is decided by the opportunities exactly as before", () => {
  const blankQuarters = forecastPlan("2027-12-01", {});
  const noField = forecastPlan("2027-12-01", {});
  for (const row of noField.rows) delete row.forecastUnits;
  assert.deepEqual([...pipelineDemand(blankQuarters).byRow], [...pipelineDemand(sizedPlan()).byRow]);
  assert.deepEqual([...pipelineDemand(noField).byRow], [...pipelineDemand(sizedPlan()).byRow]);
  assert.deepEqual(numberFindings(noField, merged(noField)).findings.filter(({ pointer }) => pointer === "/renewalTest/rows"), numberFindings(sizedPlan(), merged()).findings.filter(({ pointer }) => pointer === "/renewalTest/rows"));
});

test("an opportunity figure this plan wrote is refreshed to the team forecast on the next run, and a team's own figure is kept", () => {
  const draft = forecastPlan("2027-06-01", { "AI Units": quarters(100000, 150000, 200000, 250000) });
  draft.pipeline.written = { "renewalTest:AI Units:pipelineDriver": AI_DRIVERS, "renewalTest:AI Units:demand6MoUnits": 400000, "renewalTest:AI Units:demand12MoUnits": 1400000 };
  const refreshed = numberFindings(draft, documentWithAiUnits({ demand12MoUnits: 1400000 }));
  assert.deepEqual(renewalRowFor(refreshed.findings, "ref:row:AI Units"), {
    op: "add", pointer: "/renewalTest/rows", value: { rowId: "ref:row:AI Units", demand6MoUnits: 250000, demand12MoUnits: 450000 }, source: FORECAST, asOf: "2026-08-01", supersedes: FORECAST_REFRESHED,
  }, "the driver already says the same, so only the demand changes");
  assert.deepEqual(refreshed.conflicts, []);
  assert.equal(refreshed.written["renewalTest:AI Units:demand12MoUnits"], 450000);

  const kept = numberFindings(draft, documentWithAiUnits({ demand12MoUnits: 999 }));
  assert.deepEqual(renewalRowFor(kept.findings, "ref:row:AI Units").value, { rowId: "ref:row:AI Units", demand6MoUnits: 250000 });
  assert.deepEqual(kept.conflicts, ['renewalTest row "AI Units" demand12MoUnits: kept 999, which this plan did not write; the team forecast (forecastUnits) now gives 450000.']);
});

test("the driver this plan wrote on a row now sized only by the team forecast is reported, not cleared", () => {
  const draft = forecastPlan("2027-12-01", { "Automation Developer": { ...quarters(14, 15, 18, 16), consumedQuantity: 12, consumedBasis: "statement" } });
  draft.pipeline.written = { "renewalTest:Automation Developer:pipelineDriver": "Seat expansion (Oct 26)", "renewalTest:Automation Developer:demand6MoUnits": 5, "renewalTest:Automation Developer:demand12MoUnits": 5 };
  const document = merged(draft);
  rowOf(document, "Automation Developer").id = ROW_ID;
  document.renewalTest.rows.push({ id: "66666666-6666-4666-8666-000000000002", rowId: ROW_ID, pipelineDriver: "Seat expansion (Oct 26)", demand6MoUnits: 5, demand12MoUnits: 5, confidence: "" });
  const { findings, conflicts } = numberFindings(draft, document);
  assert.deepEqual(renewalRowFor(findings, "ref:row:Automation Developer").value, { rowId: "ref:row:Automation Developer", demand6MoUnits: 3, demand12MoUnits: 6 });
  assert.equal(renewalRowFor(findings, "ref:row:Automation Developer").supersedes, FORECAST_REFRESHED);
  assert.deepEqual(conflicts, [
    'renewalTest row "Automation Developer": no open opportunity in this plan drives it any more, but the pipelineDriver this plan wrote remains in the document, beside the demand the team forecast now gives. The AE confirms it and changes or clears it in the app.',
  ]);
});

test("a forecast quarter or consumed figure that is not a number is refused, naming the field", () => {
  const draft = forecastPlan("2027-12-01", { "AI Units": quarters(100000, "150000", 200000, 250000) });
  assert.throws(() => pipelineDemand(draft), (error) => error instanceof PipelineError && /rows\[2\]\.forecastUnits\.q2/.test(error.message));
  const robots = forecastPlan("2027-12-01", { "Unattended Robot": { ...quarters(65, 85, 70, 90), consumedQuantity: "60" } });
  assert.throws(() => pipelineDemand(robots), (error) => error instanceof PipelineError && /rows\[1\]\.consumedQuantity/.test(error.message));
});

// --- Team-sized pursuits ----------------------------------------------------------------------------------

const PURSUIT_SOURCE = "Team expansion workbook, Pursuits tab (2026-07-28)";
const NO_NEW_ARR = `${PURSUIT_SOURCE} (no amount stated: draws on existing entitlement; no new ARR)`;
const USE_CASE_REFRESHED = "refreshed from the team-sized use case as of 2026-08-01";
/** A pursuit the team sized in its own workbook, with no Salesforce opportunity. */
const useCase = (changes = {}) => ({
  key: "invoice-intake-agent", name: "Invoice intake agent", source: PURSUIT_SOURCE, asOf: "2026-07-28",
  lines: [{ product: "AI Units", units: 200000, row: "AI Units" }, { product: "Unattended Robot", units: 4, row: "Unattended Robot" }],
  ...changes,
});
/** The sized plan with the given use cases. */
function planWithUseCases(...useCases) {
  const draft = sizedPlan();
  draft.pipeline.useCases = useCases;
  return draft;
}
const useCaseRecord = (findings) => opportunityRecord(findings, "invoice-intake-agent");

test("reads a plan's use cases, each with its sized lines mapped to plan rows", () => {
  const { useCases } = readPipeline(planWithUseCases(useCase({ startDate: "2026-11-01", amountUsd: 50000 })));
  assert.deepEqual(useCases, [{
    key: "invoice-intake-agent", name: "Invoice intake agent", source: PURSUIT_SOURCE, asOf: "2026-07-28", startDate: "2026-11-01", amountUsd: 50000,
    lines: [{ product: "AI Units", units: 200000, row: "AI Units" }, { product: "Unattended Robot", units: 4, row: "Unattended Robot" }],
  }]);
  assert.deepEqual(readPipeline(planWithUseCases(useCase())).useCases[0].startDate, "", "no start date");
  assert.equal(readPipeline(planWithUseCases(useCase())).useCases[0].amountUsd, null, "no amount");
  assert.deepEqual(readPipeline(sizedPlan()).useCases, [], "a plan without the section has none");
});

test("refuses a use case it cannot read, naming the field", () => {
  const cases = [
    ["a key that is not a slug", { key: "Invoice Intake" }, /useCases\[0\]\.key/],
    ["a missing key", { key: "" }, /useCases\[0\]\.key/],
    ["a key over 80 characters", { key: "a".repeat(81) }, /useCases\[0\]\.key/],
    ["a placeholder name", { name: "TBD" }, /useCases\[0\]\.name/],
    ["no source", { source: "" }, /useCases\[0\]\.source/],
    ["no as-of date", { asOf: undefined }, /useCases\[0\]\.asOf/],
    ["a start date in free text", { startDate: "Q1" }, /useCases\[0\]\.startDate/],
    ["a negative amount", { amountUsd: -5 }, /useCases\[0\]\.amountUsd/],
    ["an amount in text", { amountUsd: "5000" }, /useCases\[0\]\.amountUsd/],
    ["lines that are not a list", { lines: null }, /useCases\[0\]\.lines/],
    ["a row that is not a plan row", { lines: [{ product: "Agent Units", units: 5, row: "Agent Units" }] }, /useCases\[0\]\.lines\[0\]\.row/],
    ["negative units", { lines: [{ product: "AI Units", units: -5, row: "AI Units" }] }, /useCases\[0\]\.lines\[0\]\.units/],
    ["a line with no product", { lines: [{ product: "", units: 5, row: "AI Units" }] }, /useCases\[0\]\.lines\[0\]\.product/],
  ];
  for (const [label, changes, message] of cases) {
    assert.throws(() => pipelineDemand(planWithUseCases(useCase(changes))), (error) => error instanceof PipelineError && message.test(error.message), label);
  }
  assert.throws(() => pipelineDemand(planWithUseCases(useCase(), useCase({ name: "Another" }))), (error) => error instanceof PipelineError && /repeats key invoice-intake-agent/.test(error.message));
  assert.throws(() => pipelineDemand(planWithUseCases(useCase({ key: "006example0000001" }))), (error) => error instanceof PipelineError && /006example0000001/.test(error.message) && /opportunit/.test(error.message), "a key an opportunity already uses");
  const notList = sizedPlan();
  notList.pipeline.useCases = {};
  assert.throws(() => pipelineDemand(notList), (error) => error instanceof PipelineError && /pipeline\.useCases/.test(error.message));
});

test("a use case becomes an opportunity record: the team's sizing, no stage and no owner, and $0 iARR with its basis when the team states no amount", () => {
  const { findings } = numberFindings(planWithUseCases(useCase()), merged(planWithUseCases(useCase())));
  assert.deepEqual(useCaseRecord(findings), [
    {
      op: "add",
      pointer: "/pipelineOpportunities",
      value: {
        key: "invoice-intake-agent", name: "Invoice intake agent", status: "Open",
        products: ["AI Units", "Unattended Robot"], consumptionRowIds: ["ref:row:AI Units", "ref:row:Unattended Robot"],
        projectedConsumption: "AI Units: 200000 units; Unattended Robot: 4 robots",
      },
      source: PURSUIT_SOURCE,
      asOf: "2026-07-28",
    },
    { op: "add", pointer: "/pipelineOpportunities", value: { key: "invoice-intake-agent", estimatedIarrUsd: 0 }, source: NO_NEW_ARR, asOf: "2026-07-28" },
  ]);
  assert.doesNotMatch(JSON.stringify(useCaseRecord(findings)), /owner|motions|nextGate|stage/);
  const keys = at("/pipelineOpportunities", findings).map((finding) => finding.value.key);
  assert.deepEqual([...new Set(keys)], [1, 2, 3, 6, 8].map((n) => `006EXAMPLE000000${n}`).concat("invoice-intake-agent"), "after the opportunities' records");

  const priced = planWithUseCases(useCase({ amountUsd: 50000 }));
  assert.deepEqual(useCaseRecord(numberFindings(priced, merged(priced)).findings).map(({ value }) => value.estimatedIarrUsd), [50000], "a stated amount is its iARR, in the one finding");
});

test("a use case draws on each consumed row it sizes unless it starts more than 12 months out; unsized, platform and unmapped lines as for an opportunity", () => {
  const sized = planWithUseCases(useCase());
  assert.deepEqual(pursuitFor(numberFindings(sized, merged(sized)).findings, "invoice-intake-agent"), {
    op: "add", pointer: "/snapshot/pursuits",
    value: { opportunityId: "ref:opportunity:invoice-intake-agent", draw: [{ rowId: "ref:row:AI Units", units: 200000 }, { rowId: "ref:row:Unattended Robot", units: 4 }] },
    source: PURSUIT_SOURCE, asOf: "2026-07-28",
  }, "no start date: a use case has no close date, so the 12-month cut does not apply");
  const late = planWithUseCases(useCase({ startDate: "2027-12-01" }));
  const lateFindings = numberFindings(late, merged(late)).findings;
  assert.equal(pursuitFor(lateFindings, "invoice-intake-agent"), undefined, "one starting beyond 12 months draws nothing: it adds nothing in the window");
  assert.ok(useCaseRecord(lateFindings).length, "it is still a record");
  const lastDay = planWithUseCases(useCase({ startDate: "2027-08-01" }));
  assert.ok(pursuitFor(numberFindings(lastDay, merged(lastDay)).findings, "invoice-intake-agent"), "the window includes its last day");

  const mixed = planWithUseCases(useCase({ lines: [
    { product: "AI Units", units: null, row: "AI Units" },
    { product: "Platform - Standard", units: 1, row: "Platform - Standard" },
    { product: "Agent Units", units: 5, row: "" },
  ] }));
  const { findings } = numberFindings(mixed, merged(mixed));
  assert.deepEqual(pursuitFor(findings, "invoice-intake-agent").value.draw, [{ rowId: "ref:row:AI Units", units: null }]);
  assert.equal("projectedConsumption" in useCaseRecord(findings)[0].value, false);
  const { unsized, unmapped } = pipelineDemand(mixed);
  const ofUseCase = (entries) => entries.filter(({ opportunity }) => opportunity.key).map(({ opportunity, line }) => [opportunity.key, line.product]);
  assert.deepEqual(ofUseCase(unsized), [["invoice-intake-agent", "AI Units"]]);
  assert.deepEqual(ofUseCase(unmapped), [["invoice-intake-agent", "Agent Units"]], "reported after the opportunities' own");
  assert.equal(unmapped.at(-1).opportunity.key, "invoice-intake-agent");
  const platformOnly = planWithUseCases(useCase({ lines: [{ product: "Platform - Standard", units: 1, row: "Platform - Standard" }] }));
  assert.equal(pursuitFor(numberFindings(platformOnly, merged(platformOnly)).findings, "invoice-intake-agent"), undefined, "a tier is granted, so nothing is drawn");
});

test("a use case adds demand only when it states a start date, timed like a close date, and drives the row it sizes", () => {
  assert.deepEqual([...pipelineDemand(planWithUseCases(useCase())).byRow], [...pipelineDemand(sizedPlan()).byRow], "no start date: no demand and no driver");
  const timed = pipelineDemand(planWithUseCases(useCase({ startDate: "2026-11-01" }))).byRow;
  assert.deepEqual(timed.get("AI Units"), {
    demand6MoUnits: 600000,
    demand12MoUnits: 1600000,
    drivers: ["Example Corp - AI Units and Robot Expansion (Oct 26)", "Invoice intake agent (Nov 26)", "Example Corp - AI Units Phase 2 (May 27)"],
    asOf: "2026-07-30",
    useCaseSources: [PURSUIT_SOURCE],
  });
  assert.deepEqual([timed.get("Unattended Robot").demand6MoUnits, timed.get("Unattended Robot").demand12MoUnits, timed.get("Unattended Robot").asOf], [24, 24, "2026-07-28"]);
  const later = pipelineDemand(planWithUseCases(useCase({ startDate: "2027-05-01" }))).byRow.get("AI Units");
  assert.deepEqual([later.demand6MoUnits, later.demand12MoUnits], [400000, 1600000]);
  for (const startDate of ["2026-07-01", "2027-10-01"]) {
    assert.deepEqual([...pipelineDemand(planWithUseCases(useCase({ startDate }))).byRow], [...pipelineDemand(sizedPlan()).byRow], `starting ${startDate}: outside both windows`);
  }

  const draft = planWithUseCases(useCase({ startDate: "2026-11-01" }));
  assert.deepEqual(renewalRowFor(numberFindings(draft, merged(draft)).findings, "ref:row:AI Units"), {
    op: "add", pointer: "/renewalTest/rows",
    value: { rowId: "ref:row:AI Units", pipelineDriver: "Example Corp - AI Units and Robot Expansion (Oct 26); Invoice intake agent (Nov 26); Example Corp - AI Units Phase 2 (May 27)", demand6MoUnits: 600000, demand12MoUnits: 1600000 },
    source: `${OPPORTUNITIES_SOURCE}; ${PURSUIT_SOURCE}`, asOf: "2026-07-30",
  });
});

test("a use case adds no demand on a row the team forecasts, and still names it as a driver", () => {
  const draft = forecastPlan("2027-06-01", { "AI Units": quarters(100000, 150000, 200000, 250000) });
  draft.pipeline.useCases = [useCase({ startDate: "2026-11-01" })];
  const demand = pipelineDemand(draft).byRow.get("AI Units");
  assert.deepEqual([demand.demand6MoUnits, demand.demand12MoUnits], [250000, 450000]);
  assert.ok(demand.drivers.includes("Invoice intake agent (Nov 26)"));
  assert.equal(pipelineDemand(draft).byRow.get("Unattended Robot").demand12MoUnits, 24, "a row with no forecast takes the use case's units");
});

test("other pipeline activity counts a use case the cards do not show, as it does an opportunity", () => {
  const draft = planWithUseCases(useCase());
  const shown = ["006EXAMPLE0000001", "006EXAMPLE0000002", "006EXAMPLE0000003"];
  assert.deepEqual(totals(otherActivityUsd(draft, shown)), { usd: 200000 * 0.04 + 4 * 3000, unpriced: [], unsized: [] });
  assert.deepEqual(totals(otherActivityUsd(draft, [...shown, "invoice-intake-agent"])), { usd: 0, unpriced: [], unsized: [] }, "on a card it is not other activity");
  const unsized = planWithUseCases(useCase({ lines: [{ product: "AI Units", units: null, row: "AI Units" }] }));
  assert.equal(otherActivityUsd(unsized, shown).usd, null, "an unsized line off the cards withholds the total");

  const { findings, conflicts } = otherActivityFindings(draft, documentWithRecords(draft));
  assert.deepEqual(conflicts, []);
  assert.deepEqual(findings, [{
    op: "set", pointer: "/snapshot/otherPipelineActivityUsd", value: 50000, source: "Salesforce Opportunities and team-sized use cases priced at contracted unit prices", asOf: "2026-08-01",
  }], "the cards are opportunities 1, 2 and 6; off them, the FY28 robots (30000) and the use case at $0 iARR (20000)");
});

test("a use case the team already added in the app by name is adopted, and one keyed otherwise is not duplicated", () => {
  const draft = planWithUseCases(useCase());
  const document = merged(draft);
  document.pipelineOpportunities.push({ id: OPP_ID, key: "", name: "Invoice intake agent", stage: "", status: "Open", estimatedIarrUsd: null, owner: "A. Owner" });
  const adopted = numberFindings(draft, document);
  assert.deepEqual(at("/pipelineOpportunities/0/key", adopted.findings), [{ op: "set", pointer: "/pipelineOpportunities/0/key", value: "invoice-intake-agent", source: PURSUIT_SOURCE, asOf: "2026-07-28" }]);
  assert.deepEqual(adopted.conflicts, []);
  assert.ok(pursuitFor(adopted.findings, "invoice-intake-agent"));

  document.pipelineOpportunities[0].key = "intake";
  const withheld = numberFindings(draft, document);
  assert.equal(withheld.findings.some((finding) => JSON.stringify(finding).includes("invoice-intake-agent")), false);
  assert.deepEqual(withheld.conflicts, [
    'Use case "Invoice intake agent" (invoice-intake-agent): the document has a record of that name keyed "intake", so no second record is added. The AE changes its key to invoice-intake-agent in the app, so the next run fills it.',
  ]);
});

test("a use case's record and draws follow the refresh rule, and what the team changed or deleted stays", () => {
  const draft = planWithUseCases(useCase());
  const document = merged(draft);
  rowOf(document, "AI Units").id = ROW_ID;
  document.pipelineOpportunities.push({ id: OPP_ID, key: "invoice-intake-agent", name: "Intake agent", status: "Open", estimatedIarrUsd: 0, products: ["AI Units", "Unattended Robot"], consumptionRowIds: [], projectedConsumption: "AI Units: 100000 units; Unattended Robot: 4 robots" });
  document.snapshot.pursuits.push({ id: "77777777-7777-4777-8777-000000000001", opportunityId: OPP_ID, cardStatus: "", draw: [{ id: "88888888-8888-4888-8888-000000000001", rowId: ROW_ID, units: 100000 }] });
  draft.pipeline.written = {
    "useCase:invoice-intake-agent:name": "Invoice intake agent",
    "useCase:invoice-intake-agent:projectedConsumption": "AI Units: 100000 units; Unattended Robot: 4 robots",
    "useCase:invoice-intake-agent:draw:AI Units": 100000,
  };
  const { findings, conflicts, written } = numberFindings(draft, document);
  const records = useCaseRecord(findings);
  assert.deepEqual(records.map(({ value, supersedes }) => [value, supersedes]), [
    [{ key: "invoice-intake-agent", consumptionRowIds: ["ref:row:AI Units", "ref:row:Unattended Robot"] }, undefined],
    [{ key: "invoice-intake-agent", projectedConsumption: "AI Units: 200000 units; Unattended Robot: 4 robots" }, USE_CASE_REFRESHED],
  ]);
  assert.deepEqual(pursuitFor(findings, "invoice-intake-agent").value.draw, [{ rowId: "ref:row:AI Units", units: 200000 }, { rowId: "ref:row:Unattended Robot", units: 4 }]);
  assert.equal(pursuitFor(findings, "invoice-intake-agent").supersedes, USE_CASE_REFRESHED);
  assert.deepEqual(conflicts, ['pipelineOpportunities "Invoice intake agent" name: kept "Intake agent", which this plan did not write; the team-sized use case now gives "Invoice intake agent".']);
  assert.equal(written["useCase:invoice-intake-agent:draw:AI Units"], 200000);
  assert.equal(written["useCase:invoice-intake-agent:estimatedIarrUsd"], 0);

  const deleted = numberFindings(draft, merged(draft));
  assert.deepEqual(useCaseRecord(deleted.findings), []);
  assert.equal(pursuitFor(deleted.findings, "invoice-intake-agent"), undefined);
  assert.deepEqual(deleted.conflicts, [
    'Use case "Invoice intake agent" (invoice-intake-agent): its record, which this plan added, is no longer in the document, so it is not added again; the plan file still lists it. The AE confirms the removal or adds it back in the app.',
  ]);
});

test("a use case that has left the plan is reported once, and nothing it put in the document is cleared", () => {
  const draft = withWritten({ "useCase:old-pursuit:status": "Open", "useCase:old-pursuit:draw:AI Units": 5, "useCase:old-pursuit:draw:Unattended Robot": 1 });
  const { findings, conflicts } = numberFindings(draft, merged());
  assert.deepEqual(conflicts, [
    "Use case old-pursuit is no longer in this plan; its record, card, draws and demand remain in the document. The AE confirms with the account team whether it is still pursued and removes it in the app.",
  ]);
  assert.equal(findings.some((finding) => JSON.stringify(finding).includes("old-pursuit")), false);

  const moved = planWithUseCases(useCase({ lines: [{ product: "AI Units", units: 200000, row: "AI Units" }] }));
  moved.pipeline.written = { "useCase:invoice-intake-agent:draw:Unattended Robot": 4 };
  assert.deepEqual(numberFindings(moved, merged(moved)).conflicts.filter((line) => /earlier draw/.test(line)), [
    'Use case "Invoice intake agent" (invoice-intake-agent): its earlier draw on "Unattended Robot" is no longer in this plan\'s lines, but it remains in the document. The AE confirms or removes it in the app.',
  ]);
});

test("a use case's lines on one row add up to one draw line, and an unsized one among them makes it a line with no units", () => {
  const lines = (topUp) => [{ product: "AI Units", units: 200000, row: "AI Units" }, { product: "AI Units top-up", units: topUp, row: "AI Units" }, { product: "Unattended Robot", units: 4, row: "Unattended Robot" }];
  const summed = planWithUseCases(useCase({ lines: lines(5000) }));
  assert.deepEqual(pursuitFor(numberFindings(summed, merged(summed)).findings, "invoice-intake-agent").value.draw, [{ rowId: "ref:row:AI Units", units: 205000 }, { rowId: "ref:row:Unattended Robot", units: 4 }]);
  const partly = planWithUseCases(useCase({ lines: lines(null) }));
  const { findings, written } = numberFindings(partly, merged(partly));
  assert.deepEqual(pursuitFor(findings, "invoice-intake-agent").value.draw, [{ rowId: "ref:row:AI Units", units: null }, { rowId: "ref:row:Unattended Robot", units: 4 }]);
  assert.equal(written["useCase:invoice-intake-agent:draw:AI Units"], null, "null is what this plan wrote");
});

/**
 * The plan with a use case sizing AI Units alone, what it last wrote, and the merged document holding the use case's
 * record and card as an earlier run left them, the card's AI Units draw holding `units`.
 */
function useCaseWithDraw(units, written = {}) {
  const draft = planWithUseCases(useCase({ lines: [{ product: "AI Units", units: 200000, row: "AI Units" }] }));
  draft.pipeline.written = written;
  const document = merged(draft);
  rowOf(document, "AI Units").id = ROW_ID;
  document.pipelineOpportunities.push({ id: OPP_ID, key: "invoice-intake-agent", name: "Invoice intake agent", status: "Open", estimatedIarrUsd: 0, products: ["AI Units"], consumptionRowIds: [ROW_ID], projectedConsumption: "AI Units: 200000 units" });
  document.snapshot.pursuits.push({ id: "77777777-7777-4777-8777-000000000001", opportunityId: OPP_ID, cardStatus: "", draw: [{ id: "88888888-8888-4888-8888-000000000001", rowId: ROW_ID, units }] });
  return [draft, document];
}
const INTAKE = 'Use case "Invoice intake agent" (invoice-intake-agent)';

test("a use case's draw follows the refresh rule, read through its record, its card and the row's id", () => {
  const refreshed = numberFindings(...useCaseWithDraw(5, { "useCase:invoice-intake-agent:draw:AI Units": 5 }));
  assert.deepEqual(pursuitFor(refreshed.findings, "invoice-intake-agent").value.draw, [{ rowId: "ref:row:AI Units", units: 200000 }]);
  assert.equal(pursuitFor(refreshed.findings, "invoice-intake-agent").supersedes, USE_CASE_REFRESHED);
  assert.deepEqual(refreshed.conflicts, []);
  assert.equal(refreshed.written["useCase:invoice-intake-agent:draw:AI Units"], 200000);

  const kept = numberFindings(...useCaseWithDraw(5, { "useCase:invoice-intake-agent:draw:AI Units": 7 }));
  assert.equal(pursuitFor(kept.findings, "invoice-intake-agent"), undefined);
  assert.deepEqual(kept.conflicts, ['snapshot pursuit "Invoice intake agent" draw on "AI Units": kept 5, which this plan did not write; the team-sized use case now gives 200000.'], "reported once, as kept, not again as a draw no longer sized");

  const equal = numberFindings(...useCaseWithDraw(200000));
  assert.equal(pursuitFor(equal.findings, "invoice-intake-agent"), undefined);
  assert.deepEqual(equal.conflicts, []);
  assert.equal(equal.written["useCase:invoice-intake-agent:draw:AI Units"], 200000);
});

test("a use case's card with no draw line on a row yet gets that line without a supersedes", () => {
  const [draft, document] = useCaseWithDraw(200000);
  document.snapshot.pursuits[0].draw = [];
  const { findings } = numberFindings(draft, document);
  assert.deepEqual(pursuitFor(findings, "invoice-intake-agent").value.draw, [{ rowId: "ref:row:AI Units", units: 200000 }]);
  assert.equal(pursuitFor(findings, "invoice-intake-agent").supersedes, undefined);
});

test("use-case draw units this plan wrote that the team cleared stay blank, with a line saying so", () => {
  const { findings, conflicts, written } = numberFindings(...useCaseWithDraw(null, { "useCase:invoice-intake-agent:draw:AI Units": 200000 }));
  assert.equal(pursuitFor(findings, "invoice-intake-agent"), undefined);
  assert.deepEqual(conflicts, ['snapshot pursuit "Invoice intake agent" draw on "AI Units": left blank, as the account team cleared it (this plan wrote 200000); the team-sized use case now gives 200000.']);
  assert.equal("useCase:invoice-intake-agent:draw:AI Units" in written, false);
});

test("a use case's draw line this plan wrote that the team deleted is not drawn again, and is reported once", () => {
  const [draft, document] = useCaseWithDraw(200000, { "useCase:invoice-intake-agent:draw:AI Units": 200000 });
  document.snapshot.pursuits[0].draw = [];
  const { findings, conflicts } = numberFindings(draft, document);
  assert.equal(pursuitFor(findings, "invoice-intake-agent"), undefined);
  assert.deepEqual(conflicts, [
    `${INTAKE}: its draw on "AI Units", which this plan wrote, is no longer on its pursuit card, so it is not drawn again. The AE confirms the removal or adds it back in the app.`,
  ], "and not again as a draw that is no longer in this plan's lines");
});

test("a use case's pursuit card this plan added that the team deleted is not added again, and is reported once", () => {
  const [draft, document] = useCaseWithDraw(200000, { "useCase:invoice-intake-agent:draw:AI Units": 200000 });
  document.snapshot.pursuits = [];
  const { findings, conflicts } = numberFindings(draft, document);
  assert.equal(pursuitFor(findings, "invoice-intake-agent"), undefined);
  assert.deepEqual(conflicts, [
    `${INTAKE}: its pursuit card, which this plan added, is no longer in the document, so it is not added again. The AE confirms the removal or adds it back in the app.`,
  ]);
});

// --- Keys compared as the app compares them --------------------------------------------------------------
//
// The app treats two opportunity keys as one when they agree after NFKC normalization, trimming, en-US lower-casing,
// hyphens and underscores read as spaces, and whitespace collapsed (normalizedOpportunityKey), and blocks publication
// on such a duplicate. Every place the plan matches a record by its key compares keys that way.

const TEAM_KEY = "Invoice_Intake  Agent";

test("a record whose key the app reads as a use case's key is that use case's record: no second record, and every finding addresses it by its own key", () => {
  const draft = planWithUseCases(useCase());
  const document = merged(draft);
  document.pipelineOpportunities.push({ id: OPP_ID, key: TEAM_KEY, name: "Intake agent (team)", status: "Open", estimatedIarrUsd: null });
  const { findings, conflicts } = numberFindings(draft, document);
  assert.deepEqual(opportunityRecord(findings, "invoice-intake-agent"), [], "no record is added under the plan's spelling, which the app would read as a duplicate");
  const records = opportunityRecord(findings, TEAM_KEY);
  assert.ok(records.length > 0, "the findings fill the team's record, by the key it already has");
  assert.equal(findings.some((finding) => /\/key$/.test(finding.pointer)), false, "its key is left as the team spelled it");
  assert.ok(pursuitFor(findings, TEAM_KEY), "its card names the record by that key, the one apply-findings resolves");
  assert.equal(pursuitFor(findings, "invoice-intake-agent"), undefined);
  assert.deepEqual(conflicts, ['pipelineOpportunities "Invoice intake agent" name: kept "Intake agent (team)", which this plan did not write; the team-sized use case now gives "Invoice intake agent".']);
});

test("a same-named record keyed as the app reads a use case's key is matched by key, not withheld for re-keying", () => {
  const draft = planWithUseCases(useCase());
  const document = merged(draft);
  document.pipelineOpportunities.push({ id: OPP_ID, key: " invoice intake-agent ", name: "Invoice intake agent", status: "Open", estimatedIarrUsd: 0 });
  const { findings, conflicts } = numberFindings(draft, document);
  assert.deepEqual(conflicts, []);
  assert.ok(opportunityRecord(findings, " invoice intake-agent ").length > 0);
  assert.ok(pursuitFor(findings, " invoice intake-agent "));
});

test("a record keyed as the app reads another pursuit's key is that pursuit's, so a same-named pursuit does not claim it", () => {
  const draft = planWithUseCases(useCase(), useCase({ key: "intake-agent-two", name: "Shared name" }));
  const document = merged(draft);
  document.pipelineOpportunities.push({ id: OPP_ID, key: "Intake_Agent_Two", name: "Invoice intake agent", status: "Open" });
  const { findings, conflicts } = numberFindings(draft, document);
  assert.ok(opportunityRecord(findings, "invoice-intake-agent").length > 0, "the first use case gets a record of its own");
  assert.ok(opportunityRecord(findings, "Intake_Agent_Two").length > 0, "the record is the second use case's");
  assert.equal(conflicts.some((line) => /keyed/.test(line)), false);
});

test("two opportunity ids the app reads as one key are refused as a repeat", () => {
  const draft = sizedPlan();
  draft.pipeline.opportunities[1].salesforceId = draft.pipeline.opportunities[0].salesforceId.toLowerCase();
  assert.throws(() => readPipeline(draft), (error) => error instanceof PipelineError && /repeats Salesforce id/.test(error.message));
});

test("a shown card keyed as the app reads a use case's key keeps that use case out of other pipeline activity", () => {
  const draft = planWithUseCases(useCase());
  const shown = ["006EXAMPLE0000001", "006EXAMPLE0000002", "006EXAMPLE0000003"];
  assert.deepEqual(totals(otherActivityUsd(draft, [...shown, TEAM_KEY])), { usd: 0, unpriced: [], unsized: [] });
  assert.deepEqual(totals(otherActivityUsd(draft, [...shown.map((id) => ` ${id.toLowerCase()} `), "invoice-intake-agent"])), { usd: 0, unpriced: [], unsized: [] });
});

// --- A use case's start date and the 12-month window ------------------------------------------------------

test("a use case starting more than 12 months out is beyond the window, and one that started before asOf has started; neither adds demand", () => {
  const late = pipelineDemand(planWithUseCases(useCase({ startDate: "2027-12-01" })));
  assert.deepEqual(late.beyondWindow.map(({ key, salesforceId }) => key ?? salesforceId), ["006EXAMPLE0000003", "invoice-intake-agent"]);
  assert.deepEqual(late.started, []);
  const past = pipelineDemand(planWithUseCases(useCase({ startDate: "2026-07-01" })));
  assert.deepEqual(past.started.map(({ key }) => key), ["invoice-intake-agent"]);
  assert.deepEqual(past.beyondWindow.map(({ salesforceId }) => salesforceId), ["006EXAMPLE0000003"]);
  for (const demand of [late, past]) assert.deepEqual([...demand.byRow], [...pipelineDemand(sizedPlan()).byRow]);
  for (const startDate of [undefined, "2026-08-01", "2027-08-01"]) {
    const timed = pipelineDemand(planWithUseCases(useCase({ startDate })));
    assert.deepEqual([timed.started.length, timed.beyondWindow.length], [0, 1], `starting ${startDate}: inside the window`);
  }
});

test("draws this plan wrote for a use case that now starts more than 12 months out stay on its card, reported once", () => {
  const draft = planWithUseCases(useCase({ startDate: "2027-12-01" }));
  draft.pipeline.written = { "useCase:invoice-intake-agent:draw:AI Units": 200000, "useCase:invoice-intake-agent:draw:Unattended Robot": 4 };
  const document = merged(draft);
  document.pipelineOpportunities.push({ id: OPP_ID, key: "invoice-intake-agent", name: "Invoice intake agent", status: "Open", estimatedIarrUsd: 0 });
  const { findings, conflicts } = numberFindings(draft, document);
  assert.equal(pursuitFor(findings, "invoice-intake-agent"), undefined);
  assert.deepEqual(conflicts.filter((line) => /more than 12 months/.test(line)), [
    'Use case "Invoice intake agent" (invoice-intake-agent) now starts 2027-12-01, more than 12 months after 2026-08-01, so this plan draws nothing for it; the draws it wrote earlier remain on its pursuit card. The AE re-dates it in the plan file or removes the draws in the app.',
  ]);
  assert.equal(conflicts.some((line) => /earlier draw/.test(line)), false, "not reported again as a draw no longer in its lines");
});

// --- What the team forecast's roll-up leaves for the AE to see -----------------------------------------------

const ROBOT_DRIVER = "Example Corp - AI Units and Robot Expansion (Oct 26)";
const NO_CONSUMED = (row, fields) => `renewalTest row "${row}": the team forecast (forecastUnits) gives no ${fields}, since the plan row has no consumed figure (consumedQuantity) to take from its busiest quarter; this plan writes none and leaves the document's as it is.`;

test("a +6-month figure above the +12-month one, from windows the forecast and the pipeline give apart, is reported naming the row", () => {
  const draft = forecastPlan("2027-12-01", { "AI Units": quarters(1000000, 1000000, null, 250000) });
  const demand = pipelineDemand(draft).byRow.get("AI Units");
  assert.deepEqual([demand.demand6MoUnits, demand.demand12MoUnits], [2000000, 1400000], "q3 is not forecast, so +12 months is the opportunities'");
  const { conflicts } = numberFindings(draft, merged(draft));
  assert.deepEqual(conflicts, [
    'renewalTest row "AI Units": its demand6MoUnits (2000000) exceeds its demand12MoUnits (1400000), which includes it; the team forecast (forecastUnits) gives the first and Salesforce opportunities the second. The AE reconciles them in the plan file.',
  ]);
  const within = forecastPlan("2027-12-01", { "AI Units": quarters(100000, 150000, null, 250000) });
  assert.deepEqual(numberFindings(within, merged(within)).conflicts, [], "250000 within 6 months and 1400000 within 12 is consistent");
});

test("a peak row's forecast with no consumed figure writes no demand: a new row with nothing else to say is not added, and a line names the missing figure", () => {
  const draft = forecastPlan("2027-12-01", {
    "Unattended Robot": { ...quarters(65, 85, 70, 90), consumedQuantity: null },
    "Automation Developer": quarters(14, 15, 18, 16),
  });
  const { findings, conflicts, written } = numberFindings(draft, merged(draft));
  assert.deepEqual(at("/renewalTest/rows", findings).filter(({ value }) => value.rowId !== "ref:row:AI Units"), [
    { op: "add", pointer: "/renewalTest/rows", value: { rowId: "ref:row:Unattended Robot", pipelineDriver: ROBOT_DRIVER }, source: OPPORTUNITIES_SOURCE, asOf: "2026-07-20" },
  ], "the robots row keeps its driver and gets no all-null demand; the developer row, with no driver, is not added at all");
  assert.deepEqual(conflicts, [
    NO_CONSUMED("Unattended Robot", "demand6MoUnits or demand12MoUnits"),
    NO_CONSUMED("Automation Developer", "demand6MoUnits or demand12MoUnits"),
  ]);
  assert.equal("renewalTest:Automation Developer:demand12MoUnits" in written, false);
});

test("an opportunity figure this plan wrote is kept, not refreshed to no figure, when the forecast lacks a consumed figure, and a line says why", () => {
  const draft = forecastPlan("2027-12-01", { "Unattended Robot": { ...quarters(65, 85, 70, 90), consumedQuantity: null } });
  draft.pipeline.written = { "renewalTest:Unattended Robot:pipelineDriver": ROBOT_DRIVER, "renewalTest:Unattended Robot:demand6MoUnits": 20, "renewalTest:Unattended Robot:demand12MoUnits": 20 };
  const document = merged(draft);
  rowOf(document, "Unattended Robot").id = ROW_ID;
  document.renewalTest.rows.push({ id: "66666666-6666-4666-8666-000000000003", rowId: ROW_ID, pipelineDriver: ROBOT_DRIVER, demand6MoUnits: 20, demand12MoUnits: 20, confidence: "" });
  const { findings, conflicts, written } = numberFindings(draft, document);
  assert.equal(renewalRowFor(findings, "ref:row:Unattended Robot"), undefined, "the 20 stays: a missing consumed figure alone does not withdraw it");
  assert.deepEqual(conflicts, [NO_CONSUMED("Unattended Robot", "demand6MoUnits or demand12MoUnits")], "and it is not reported as a row nothing drives");
  assert.equal("renewalTest:Unattended Robot:demand12MoUnits" in written, false, "the record of the 20 this plan wrote stands");
});

test("a 0 the busiest-quarter roll-up gives is noted, and a row nothing in the pipeline drives says the app shows it as Not adopted", () => {
  const robots = forecastPlan("2027-12-01", { "Unattended Robot": { ...quarters(50, 55, 40, 58), consumedQuantity: 60 } });
  const driven = numberFindings(robots, merged(robots));
  assert.deepEqual(renewalRowFor(driven.findings.filter(({ source }) => source === FORECAST), "ref:row:Unattended Robot").value, { rowId: "ref:row:Unattended Robot", demand6MoUnits: 0, demand12MoUnits: 0 });
  assert.deepEqual(driven.conflicts, ['renewalTest row "Unattended Robot": the team forecast (forecastUnits) gives 0 demand6MoUnits and demand12MoUnits, since its busiest quarter there (58) is at or below the 60 already consumed.']);

  const seats = forecastPlan("2027-12-01", { "Automation Developer": { ...quarters(10, 12, 11, 12), consumedQuantity: 12, consumedBasis: "statement" } });
  assert.deepEqual(numberFindings(seats, merged(seats)).conflicts, ['renewalTest row "Automation Developer": the team forecast (forecastUnits) gives 0 demand6MoUnits and demand12MoUnits, since its busiest quarter there (12) is at or below the 12 already consumed; with no pipeline driver the app shows the row as Not adopted.']);

  const early = forecastPlan("2027-12-01", { "Automation Developer": { ...quarters(10, 11, 15, 18), consumedQuantity: 12, consumedBasis: "statement" } });
  assert.deepEqual(numberFindings(early, merged(early)).conflicts, ['renewalTest row "Automation Developer": the team forecast (forecastUnits) gives 0 demand6MoUnits, since its busiest quarter there (11) is at or below the 12 already consumed.'], "+12 months is 6, so the row is not Not adopted");

  const consumable = forecastPlan("2027-12-01", { "AI Units": quarters(0, 0, 0, 0) });
  assert.deepEqual(numberFindings(consumable, merged(consumable)).conflicts, [], "a consumable's stated 0 is the team's own, not a roll-up's floor");
});

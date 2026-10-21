// node --test consumption-plan/tests/to-day2.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { PlanError, toDay2 } from "../scripts/to-day2.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const fixture = join(here, "fixtures", "illustrative-plan.json");
const plan = () => JSON.parse(readFileSync(fixture, "utf8"));
/** The dashboard's blank template, trimmed to what the merge reads. */
const blank = () => ({
  schemaVersion: "1.11",
  customerName: "",
  renewalEconomics: { currentArrUsd: null },
  consumptionPlan: { asOf: "", forecastPeriod: "", groups: [], primaryUseCases: [] },
});
const ROW_ID = "11111111-1111-4111-8111-111111111111";
const GROUP_ID = "22222222-2222-4222-8222-222222222222";
const OTHER_ID = "44444444-4444-4444-8444-444444444444";

test("maps a plan onto a blank document in category order", () => {
  const { document } = toDay2(plan(), blank());
  assert.equal(document.customerName, "Example Corp (Illustrative)");
  assert.equal(document.consumptionPlan.asOf, "2026-08-01");
  assert.equal(document.consumptionPlan.forecastPeriod, "Q+1 FY27 Q4 → Q+4 FY28 Q3");
  assert.deepEqual(document.consumptionPlan.groups.map((group) => group.element), ["Users", "Robots", "Consumables"]);
  assert.deepEqual(document.consumptionPlan.groups[1].rows[0], {
    offering: "Unattended Robot", unit: "robots", skuCode: "UIFDUR00000", licensingModel: "capped",
    soldQuantity: 100, soldArrUsd: 300000, arrSource: "manual", discountPercent: 32.5,
    actualConsumed: 60, forecastUnits: { q1: 65, q2: 80, q3: null, q4: null },
    comments: "Illustrative: a Q3 program review puts 40 more robots live in November.",
  });
  assert.equal(document.renewalEconomics.currentArrUsd, 400000);
});

test("never writes a figure the app derives", () => {
  const { document } = toDay2(plan(), blank());
  assert.doesNotMatch(JSON.stringify(document), /arrSharePercent|consumedPercent|consumedArrUsd|"total/i);
});

test("an empty plan field never erases what the account team entered", () => {
  const baseline = toDay2(plan(), blank()).document;
  const developer = baseline.consumptionPlan.groups[0].rows[0];
  Object.assign(developer, { id: ROW_ID, actualConsumed: 18, comments: "Team count from the Orchestrator export, 2026-07-28." });
  developer.forecastUnits.q1 = 19;

  const { document } = toDay2(plan(), baseline);
  const users = document.consumptionPlan.groups[0];
  assert.equal(users.rows.length, 1, "the plan row matched the baseline row instead of duplicating it");
  assert.equal(users.rows[0].id, ROW_ID);
  assert.equal(users.rows[0].actualConsumed, 18);
  assert.equal(users.rows[0].comments, "Team count from the Orchestrator export, 2026-07-28.");
  assert.equal(users.rows[0].forecastUnits.q1, 19);
});

test("matches by SKU before name, keeps the team's label and category, and reports changes", () => {
  const baseline = blank();
  baseline.consumptionPlan.groups = [{
    id: GROUP_ID, element: "Platform",
    rows: [{ id: ROW_ID, offering: "Unattended robots", skuCode: "UIFDUR00000", soldQuantity: 90, renewalArrUsd: 310000 }],
  }];
  const { document, report } = toDay2(plan(), baseline);
  const platform = document.consumptionPlan.groups.find((group) => group.id === GROUP_ID);
  assert.equal(platform.rows.length, 1);
  assert.equal(platform.rows[0].id, ROW_ID);
  assert.equal(platform.rows[0].offering, "Unattended robots");
  assert.equal(platform.rows[0].soldQuantity, 100);
  assert.equal(platform.rows[0].renewalArrUsd, 310000);
  assert.ok(report.some((line) => line.includes("soldQuantity: 90 → 100")), report.join("\n"));
  assert.ok(report.some((line) => line.includes('kept in category "Platform"')), report.join("\n"));
});

test("keeps baseline rows the plan does not mention, and reports dangling attribution", () => {
  const baseline = blank();
  baseline.consumptionPlan.groups = [{ element: "Users", rows: [{ id: ROW_ID, offering: "Citizen Developer", soldQuantity: 5 }] }];
  baseline.consumptionPlan.primaryUseCases = [{ useCases: "Invoice intake", allocations: [{ rowId: "33333333-3333-4333-8333-333333333333" }] }];
  const { document, report } = toDay2(plan(), baseline);
  assert.ok(document.consumptionPlan.groups[0].rows.some((row) => row.id === ROW_ID));
  assert.ok(report.some((line) => line.startsWith("Citizen Developer: in the baseline but not in the plan")));
  assert.ok(report.some((line) => line.includes("33333333-3333-4333-8333-333333333333")));
});

test("leaves a differing Current ARR alone and says so", () => {
  const baseline = blank();
  baseline.renewalEconomics.currentArrUsd = 450000;
  const { document, report } = toDay2(plan(), baseline);
  assert.equal(document.renewalEconomics.currentArrUsd, 450000);
  assert.ok(report.some((line) => line.includes("sums to 400000")));
});

test("does not fill Current ARR from a short sum", () => {
  const short = plan();
  short.rows[2].arrUsd = null;
  const { document, report } = toDay2(short, blank());
  assert.equal(document.renewalEconomics.currentArrUsd, null);
  assert.equal(document.consumptionPlan.groups[2].rows[0].arrSource, "pricebook");
  assert.ok(report.some((line) => line.includes("1 plan row(s) have no ARR")));
});

test("refuses placeholders and non-numbers instead of writing them", () => {
  const placeholder = plan();
  placeholder.rows[0].notes = "TBD - team to provide";
  assert.throws(() => toDay2(placeholder, blank()), (error) => error instanceof PlanError && /rows\[0\]\.notes/.test(error.message));
  const textQuantity = plan();
  textQuantity.rows[0].purchasedQuantity = "20";
  assert.throws(() => toDay2(textQuantity, blank()), PlanError);
  const overDiscount = plan();
  overDiscount.rows[0].discountPercent = 120;
  assert.throws(() => toDay2(overDiscount, blank()), PlanError);
  const freeTextDate = plan();
  freeTextDate.asOf = "July 2026";
  assert.throws(() => toDay2(freeTextDate, blank()), /plan\.asOf/);
});

test("runs through a symlinked skill install and writes the document", () => {
  const dir = mkdtempSync(join(tmpdir(), "to-day2-"));
  const link = join(dir, "consumption-plan");
  symlinkSync(join(here, ".."), link);
  const baselinePath = join(dir, "blank.json");
  writeFileSync(baselinePath, JSON.stringify(blank()));
  const out = join(dir, "out.day2.json");
  const result = spawnSync(process.execPath, [join(link, "scripts", "to-day2.mjs"), fixture, "--baseline", baselinePath, "--out", out], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  assert.ok(existsSync(out));
  assert.match(result.stdout, /Unattended Robot: added under "Robots"/);
});

test("matches SKUs across the whole plan before names, so a SKU-less row cannot take a SKU's row", () => {
  const baseline = blank();
  baseline.consumptionPlan.groups = [{ element: "Consumables", rows: [
    { id: ROW_ID, offering: "AI Units", skuCode: "SKU-X", soldQuantity: 1000, soldArrUsd: 20000, comments: "team note" },
  ] }];
  const draft = { asOf: "2026-08-01", rows: [
    { category: "Consumables", product: "AI Units", productCode: "", unit: "units", purchasedQuantity: 500, arrUsd: 10000 },
    { category: "Consumables", product: "AI Units", productCode: "SKU-X", unit: "units", purchasedQuantity: 1000, arrUsd: 20000 },
  ] };
  const rows = toDay2(draft, baseline).document.consumptionPlan.groups[0].rows;
  assert.equal(rows.length, 2);
  assert.deepEqual([rows[0].id, rows[0].soldQuantity, rows[0].comments], [ROW_ID, 1000, "team note"]);
  assert.deepEqual([rows[1].id, rows[1].soldQuantity], [undefined, 500]);
});

test("never pairs two rows by name when their SKUs disagree", () => {
  const baseline = blank();
  baseline.consumptionPlan.groups = [{ element: "Consumables", rows: [
    { id: ROW_ID, offering: "AI Units", skuCode: "SKU-A", soldQuantity: 1 },
    { id: OTHER_ID, offering: "AI Units", skuCode: "SKU-B", soldQuantity: 2 },
  ] }];
  const draft = { asOf: "2026-08-01", rows: [
    { category: "Consumables", product: "AI Units", productCode: "SKU-C", unit: "units", purchasedQuantity: 3 },
    { category: "Consumables", product: "AI Units", productCode: "SKU-A", unit: "units", purchasedQuantity: 4 },
  ] };
  const { document, report } = toDay2(draft, baseline);
  assert.deepEqual(document.consumptionPlan.groups[0].rows.map((row) => [row.id, row.skuCode, row.soldQuantity]), [
    [ROW_ID, "SKU-A", 4], [OTHER_ID, "SKU-B", 2], [undefined, "SKU-C", 3],
  ]);
  assert.ok(report.some((line) => line.startsWith("AI Units: in the baseline but not in the plan")));
});

test("refuses placeholder values but keeps notes and names that merely start with a placeholder word", () => {
  for (const notes of ["Pending Q3 review: 40 more robots", "Unknown owner for 20 seats; confirm at QBR", "NA region rollout"]) {
    const draft = plan();
    draft.rows[0].notes = notes;
    assert.equal(toDay2(draft, blank()).document.consumptionPlan.groups[0].rows[0].comments, notes);
  }
  const named = plan();
  named.account.name = "NA Logistics";
  assert.equal(toDay2(named, blank()).document.customerName, "NA Logistics");
  for (const value of ["TBC", "Unknown", "pending", "-", "—", "N.A.", "none", "?", "to be determined", "Not available"]) {
    const draft = plan();
    draft.rows[0].unit = value;
    assert.throws(() => toDay2(draft, blank()), PlanError, value);
  }
});

test("reports a refresh that moves into a later fiscal quarter, without shifting the team's figures", () => {
  const baseline = toDay2(plan(), blank()).document;
  const later = plan();
  later.asOf = "2026-11-10";
  later.rows[1].consumedQuantity = null;
  later.rows[1].forecastUnits = { q1: null, q2: null, q3: null, q4: null };
  const { document, report } = toDay2(later, baseline);
  assert.equal(document.consumptionPlan.groups[1].rows[0].actualConsumed, 60);
  assert.ok(report.some((line) => line.startsWith("consumptionPlan.asOf moves from FY27 Q3 to FY27 Q4")), report.join("\n"));
});

test("says nothing about the window when the quarter is unchanged", () => {
  const baseline = toDay2(plan(), blank()).document;
  const sameQuarter = plan();
  sameQuarter.asOf = "2026-09-15";
  assert.ok(!toDay2(sameQuarter, baseline).report.some((line) => line.includes("moves from")));
});

test("refuses a consumed basis that is not telemetry, statement or estimate", () => {
  for (const basis of ["guess", "Estimate", "TELEMETRY", "Statement", "measured", 5]) {
    const draft = plan();
    draft.rows[1].consumedBasis = basis;
    assert.throws(() => toDay2(draft, blank()), (error) => error instanceof PlanError && /rows\[1\]\.consumedBasis/.test(error.message), String(basis));
  }
});

test("refuses an estimate that states no basis, but only when it carries a consumed figure", () => {
  for (const notes of ["", "   "]) {
    const draft = plan();
    Object.assign(draft.rows[1], { consumedBasis: "estimate", notes });
    assert.throws(() => toDay2(draft, blank()), (error) => error instanceof PlanError && /rows\[1\]\.notes/.test(error.message), JSON.stringify(notes));
  }
  const unmeasured = plan();
  Object.assign(unmeasured.rows[0], { consumedBasis: "estimate", consumedQuantity: null, notes: "" });
  assert.doesNotThrow(() => toDay2(unmeasured, blank()));
});

test("an estimate with its basis in notes maps, and the Day 2 row carries no basis or date", () => {
  const draft = plan();
  Object.assign(draft.rows[1], { consumedBasis: "estimate", consumedAsOf: "2026-07-28", notes: "Estimated from the Q3 program plan, not telemetry." });
  const row = toDay2(draft, blank()).document.consumptionPlan.groups[1].rows[0];
  assert.equal(row.actualConsumed, 60);
  assert.equal(row.comments, "Estimated from the Q3 program plan, not telemetry.");
  assert.ok(!("consumedBasis" in row) && !("consumedAsOf" in row), Object.keys(row).join(","));
  assert.doesNotMatch(JSON.stringify(toDay2(draft, blank()).document), /consumedBasis|consumedAsOf/);
});

test("accepts telemetry and statement without notes, and an empty or missing basis and date", () => {
  for (const basis of ["telemetry", "statement", "", undefined, null]) {
    const draft = plan();
    Object.assign(draft.rows[1], { consumedBasis: basis, consumedAsOf: basis === undefined ? undefined : "", notes: "" });
    assert.equal(toDay2(draft, blank()).document.consumptionPlan.groups[1].rows[0].actualConsumed, 60, String(basis));
  }
});

test("refuses a consumed-as-of date that is not a real YYYY-MM-DD date", () => {
  for (const asOf of ["2026-13-01", "2026-02-30", "Q3", "July 2026", "2026-7-28", 20260728]) {
    const draft = plan();
    draft.rows[1].consumedAsOf = asOf;
    assert.throws(() => toDay2(draft, blank()), (error) => error instanceof PlanError && /rows\[1\]\.consumedAsOf/.test(error.message), String(asOf));
  }
});

test("accepts a row's kind (one of the four product kinds, or empty or missing) and never writes it to the Day 2 row", () => {
  const without = toDay2(plan(), blank()).document;
  for (const kind of ["Users", "Robots", "Platform / Capabilities", "Consumables", "", undefined, null]) {
    const draft = plan();
    draft.rows[1].kind = kind;
    const { document } = toDay2(draft, blank());
    assert.deepEqual(document, without, `a kind of ${JSON.stringify(kind)} changes nothing in the document`);
    assert.ok(!("kind" in document.consumptionPlan.groups[1].rows[0]));
  }
});

test("refuses a kind that is not one of the four product kinds, spelled exactly", () => {
  for (const kind of ["Platform", "users", "Platform/Capabilities", "Contract 00000001", "Other", 5, true]) {
    const draft = plan();
    draft.rows[1].kind = kind;
    assert.throws(
      () => toDay2(draft, blank()),
      (error) => error instanceof PlanError && /rows\[1\]\.kind/.test(error.message),
      JSON.stringify(kind),
    );
  }
  const draft = plan();
  draft.rows[1].kind = "Platform";
  assert.throws(() => toDay2(draft, blank()), /rows\[1\]\.kind must be "Users", "Robots", "Platform \/ Capabilities", "Consumables", or empty/);
});

// --- A coverage gap is not a measured zero -----------------------------------------------------------------

/** The fixture with its robot row stated as a coverage gap: no figure, and the basis says why. */
const gapPlan = () => {
  const draft = plan();
  Object.assign(draft.rows[1], { consumedQuantity: null, consumedBasis: "coverage-gap", notes: "Illustrative: this deployment is outside the telemetry layer." });
  return draft;
};

test("a coverage gap clears the baseline's measured zero, reports it, and keeps the row's id and its other figures", () => {
  const baseline = toDay2(plan(), blank()).document;
  const robots = baseline.consumptionPlan.groups[1].rows[0];
  Object.assign(robots, { id: ROW_ID, actualConsumed: 0, soldQuantity: 90 });

  const { document, report } = toDay2(gapPlan(), baseline);
  const merged = document.consumptionPlan.groups[1].rows[0];
  assert.equal(merged.actualConsumed, null, "the 0 is erased, not kept as a measurement");
  assert.equal(merged.id, ROW_ID);
  assert.equal(merged.soldQuantity, 100, "the rest of the row merges as before");
  assert.ok(report.includes("cleared Unattended Robot actualConsumed 0: coverage gap"), report.join("\n"));
  assert.ok(!("consumedBasis" in merged), "the Day 2 row has no field for the basis");
});

test("a coverage gap clears any figure the baseline holds, not only a zero", () => {
  const baseline = toDay2(plan(), blank()).document;
  baseline.consumptionPlan.groups[1].rows[0].actualConsumed = 45;
  const { document, report } = toDay2(gapPlan(), baseline);
  assert.equal(document.consumptionPlan.groups[1].rows[0].actualConsumed, null);
  assert.ok(report.includes("cleared Unattended Robot actualConsumed 45: coverage gap"), report.join("\n"));
});

test("a coverage gap on a row the baseline holds no figure for clears and reports nothing", () => {
  const baseline = toDay2(gapPlan(), blank()).document;
  assert.equal(baseline.consumptionPlan.groups[1].rows[0].actualConsumed, null, "a new row carries no figure");
  const { document, report } = toDay2(gapPlan(), baseline);
  assert.equal(document.consumptionPlan.groups[1].rows[0].actualConsumed, null);
  assert.ok(!report.some((line) => line.startsWith("cleared")), report.join("\n"));
});

test("a coverage gap clears only the row it names", () => {
  const baseline = toDay2(plan(), blank()).document;
  baseline.consumptionPlan.groups[0].rows[0].actualConsumed = 18;
  const { document } = toDay2(gapPlan(), baseline);
  assert.equal(document.consumptionPlan.groups[0].rows[0].actualConsumed, 18, "a row whose figure the plan leaves empty keeps the team's");
});

test("a coverage gap states no figure: a consumed quantity beside it is refused", () => {
  for (const consumedQuantity of [0, 5, 60]) {
    const draft = gapPlan();
    draft.rows[1].consumedQuantity = consumedQuantity;
    assert.throws(
      () => toDay2(draft, blank()),
      (error) => error instanceof PlanError && /rows\[1\]\.consumedQuantity/.test(error.message) && /coverage-gap/.test(error.message),
      String(consumedQuantity),
    );
  }
  assert.doesNotThrow(() => toDay2(gapPlan(), blank()), "no figure, and no notes needed");
  const bare = gapPlan();
  bare.rows[1].notes = "";
  assert.doesNotThrow(() => toDay2(bare, blank()));
});

// --- Pairing by SKU takes the row in the plan row's own category first ---------------------------------------

/** Two contracts that sell the same two SKUs, the baseline listing the second contract's group first. */
function twoContracts() {
  const ids = { b1: "b0000001-0000-4000-8000-000000000001", b2: "b0000002-0000-4000-8000-000000000002", a1: "a0000001-0000-4000-8000-000000000001", a2: "a0000002-0000-4000-8000-000000000002" };
  const baseline = blank();
  baseline.consumptionPlan.groups = [
    { id: GROUP_ID, element: "Contract B", rows: [
      { id: ids.b1, offering: "Robots B", skuCode: "SKU-ROBOT", soldQuantity: 10, comments: "B robots" },
      { id: ids.b2, offering: "Units B", skuCode: "SKU-UNITS", soldQuantity: 20, comments: "B units" },
    ] },
    { id: OTHER_ID, element: "Contract A", rows: [
      { id: ids.a1, offering: "Robots A", skuCode: "SKU-ROBOT", soldQuantity: 1, comments: "A robots" },
      { id: ids.a2, offering: "Units A", skuCode: "SKU-UNITS", soldQuantity: 2, comments: "A units" },
    ] },
  ];
  const row = (category, product, productCode, purchasedQuantity) => ({ category, product, productCode, unit: "units", purchasedQuantity });
  const draft = { asOf: "2026-08-01", rows: [
    row("Contract A", "Robots", "SKU-ROBOT", 100), row("Contract A", "Units", "SKU-UNITS", 200),
    row("Contract B", "Robots", "SKU-ROBOT", 300), row("Contract B", "Units", "SKU-UNITS", 400),
  ] };
  return { baseline, draft, ids };
}

test("two contracts that share SKUs pair with their own category's rows, whatever order the baseline lists them in", () => {
  const { baseline, draft, ids } = twoContracts();
  const { document, report } = toDay2(draft, baseline);
  const quantities = Object.fromEntries(document.consumptionPlan.groups.flatMap((group) => group.rows).map((row) => [row.id, row.soldQuantity]));
  assert.deepEqual(quantities, { [ids.a1]: 100, [ids.a2]: 200, [ids.b1]: 300, [ids.b2]: 400 });
  assert.equal(document.consumptionPlan.groups.length, 2, "no row was added");
  assert.ok(!report.some((line) => line.includes("kept in category")), `no row was left in the other contract's category:\n${report.join("\n")}`);
  assert.ok(!report.some((line) => line.includes("in the baseline but not in the plan")), report.join("\n"));

  const reversed = twoContracts();
  reversed.draft.rows.reverse();
  const again = toDay2(reversed.draft, reversed.baseline).document.consumptionPlan.groups.flatMap((group) => group.rows);
  assert.deepEqual(Object.fromEntries(again.map((row) => [row.id, row.soldQuantity])), quantities, "the plan's row order does not matter either");
});

test("a SKU still pairs across categories when its own category holds no row with it", () => {
  const { baseline, draft, ids } = twoContracts();
  draft.rows = [{ category: "Contract C", product: "Robots", productCode: "SKU-ROBOT", unit: "robots", purchasedQuantity: 7 }];
  const { document, report } = toDay2(draft, baseline);
  const taken = document.consumptionPlan.groups.flatMap((group) => group.rows).filter((row) => row.soldQuantity === 7);
  assert.deepEqual(taken.map((row) => row.id), [ids.b1], "the first baseline row with the SKU, as before");
  assert.ok(report.some((line) => line.includes('kept in category "Contract B" (plan says "Contract C")')), report.join("\n"));
});

test("a category is compared ignoring case and punctuation when a SKU pairs", () => {
  const { baseline, draft, ids } = twoContracts();
  draft.rows = [{ category: "contract  a", product: "Robots", productCode: "SKU-ROBOT", unit: "robots", purchasedQuantity: 7 }];
  const rows = toDay2(draft, baseline).document.consumptionPlan.groups.flatMap((group) => group.rows);
  assert.equal(rows.find((row) => row.id === ids.a1).soldQuantity, 7);
  assert.equal(rows.find((row) => row.id === ids.b1).soldQuantity, 10);
});

// --- The merge report lists what the plan filled as well as what it changed -------------------------------------

test("the merge report lists each figure the plan filled into a matched row, and each it changed", () => {
  const baseline = blank();
  baseline.consumptionPlan.groups = [{
    id: GROUP_ID, element: "Platform",
    rows: [{ id: ROW_ID, offering: "Unattended robots", skuCode: "UIFDUR00000", soldQuantity: 90, forecastUnits: { q1: 70, q2: null } }],
  }];
  const { report } = toDay2(plan(), baseline);
  for (const line of [
    'Unattended robots unit filled: "robots"',
    'Unattended robots licensingModel filled: "capped"',
    "Unattended robots soldArrUsd filled: 300000",
    "Unattended robots discountPercent filled: 32.5",
    "Unattended robots actualConsumed filled: 60",
    'Unattended robots comments filled: "Illustrative: a Q3 program review puts 40 more robots live in November."',
    "Unattended robots forecastUnits.q2 filled: 80",
  ]) assert.ok(report.includes(line), `${line}\n${report.join("\n")}`);
  assert.ok(report.includes("Unattended robots soldQuantity: 90 → 100."), "a change to a figure the baseline held still reads as a change");
  assert.ok(report.includes("Unattended robots forecastUnits.q1: 70 → 65."), report.join("\n"));
  assert.ok(!report.some((line) => /filled/.test(line) && /soldQuantity|forecastUnits\.q1/.test(line)), "a changed figure is not also a fill");
  assert.ok(!report.some((line) => /forecastUnits\.q[34]/.test(line)), "an empty plan field writes nothing and says nothing");
});

test("the merge report says nothing about a figure the plan wrote that the baseline already holds", () => {
  const baseline = toDay2(plan(), blank()).document;
  const { report } = toDay2(plan(), baseline);
  assert.ok(!report.some((line) => /filled|→/.test(line)), report.join("\n"));
});

test("a refresh onto a blank document reports the window and the fill of each document-level field", () => {
  const { report } = toDay2(plan(), blank());
  assert.ok(report.includes('consumptionPlan.asOf filled: "2026-08-01"'), report.join("\n"));
  assert.ok(report.some((line) => line.startsWith("consumptionPlan.forecastPeriod filled:")), report.join("\n"));
});

// --- Robots on trial or unlicensed keys ------------------------------------------------------------------

const UNLICENSED = { count: 27, source: "Illustrative: Orchestrator licence export", asOf: "2026-10-15" };

test("a row may state the robots that run on trial or unlicensed keys, and the Day 2 row never carries them", () => {
  const without = toDay2(plan(), blank()).document;
  for (const unlicensedInUse of [UNLICENSED, { ...UNLICENSED, count: 1 }, null, undefined]) {
    const draft = plan();
    draft.rows[1].unlicensedInUse = unlicensedInUse;
    const { document } = toDay2(draft, blank());
    assert.deepEqual(document, without, JSON.stringify(unlicensedInUse));
    assert.doesNotMatch(JSON.stringify(document), /unlicensed|trial/i);
  }
});

test("refuses unlicensed robots that are not a positive whole count with a source and a date", () => {
  const cases = [
    ["not an object", 27, /rows\[1\]\.unlicensedInUse must be/],
    ["a list", [UNLICENSED], /rows\[1\]\.unlicensedInUse must be/],
    ["a zero count", { ...UNLICENSED, count: 0 }, /rows\[1\]\.unlicensedInUse\.count/],
    ["a negative count", { ...UNLICENSED, count: -3 }, /rows\[1\]\.unlicensedInUse\.count/],
    ["a fractional count", { ...UNLICENSED, count: 2.5 }, /rows\[1\]\.unlicensedInUse\.count/],
    ["a count in text", { ...UNLICENSED, count: "27" }, /rows\[1\]\.unlicensedInUse\.count/],
    ["no count", { source: UNLICENSED.source, asOf: UNLICENSED.asOf }, /rows\[1\]\.unlicensedInUse\.count/],
    ["no source", { ...UNLICENSED, source: "" }, /rows\[1\]\.unlicensedInUse\.source/],
    ["a placeholder source", { ...UNLICENSED, source: "TBD" }, /rows\[1\]\.unlicensedInUse\.source/],
    ["no date", { ...UNLICENSED, asOf: undefined }, /rows\[1\]\.unlicensedInUse\.asOf/],
    ["a date that is not a day", { ...UNLICENSED, asOf: "2026-02-30" }, /rows\[1\]\.unlicensedInUse\.asOf/],
  ];
  for (const [label, unlicensedInUse, message] of cases) {
    const draft = plan();
    draft.rows[1].unlicensedInUse = unlicensedInUse;
    assert.throws(() => toDay2(draft, blank()), (error) => error instanceof PlanError && message.test(error.message), label);
  }
});

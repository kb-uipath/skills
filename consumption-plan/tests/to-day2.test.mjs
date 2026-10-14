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

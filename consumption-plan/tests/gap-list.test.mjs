// node --test consumption-plan/tests/gap-list.test.mjs
// Every blank a Day 2 draft still has reaches the account team as an item with an owner role and a next step.
// The plan says why a figure is missing (no source, partial coverage, an estimate, a stale opportunity, a line
// no row can take); gap-inventory.mjs lists the blank fields; the pipeline CLI's conflicts say what was kept.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import * as gapListModule from "../scripts/gap-list.mjs";
import { PlanError, toDay2 } from "../scripts/to-day2.mjs";
import { numberFindings, otherActivityFindings } from "../scripts/pipeline.mjs";

const { GapListError, OWNER_ROLES, gapList, toMarkdown } = gapListModule;

const here = dirname(fileURLToPath(import.meta.url));
const gapListScript = join(here, "..", "scripts", "gap-list.mjs");
const gapInventoryScript = join(here, "..", "..", "enrich-day2-dashboard", "scripts", "gap-inventory.mjs");
const dir = mkdtempSync(join(tmpdir(), "gap-list-"));

const fixturePlan = () => JSON.parse(readFileSync(join(here, "fixtures", "illustrative-pipeline-plan.json"), "utf8"));
/** The document the one-run flow would hold after merging the plan into an empty baseline. */
const documentFor = (plan) => toDay2(plan, {}).document;
/** A plan with no rows and no pipeline: only what a test adds to the inventory or the document shows up. */
const barePlan = () => ({ account: { name: "Example Corp (Illustrative)" }, asOf: "2026-08-01", rows: [] });
const planRow = (plan, product) => plan.rows.find((row) => row.product === product);
const docRow = (document, offering) => document.consumptionPlan.groups.flatMap((group) => group.rows).find((row) => row.offering === offering);

/** One row as `gap-inventory.mjs --json` prints it. */
const inventoryRow = (generic, extra = {}) => ({
  tab: "Snapshot", pointer: generic.replaceAll("*", "0"), generic, who: "human", requirement: "optional", blocks: false,
  policy: "human_only", label: "", kind: "empty", recordGating: [], ...extra,
});

const whys = (items, why) => items.filter((entry) => entry.why === why);
const mentioning = (items, text) => items.filter((entry) => entry.item.includes(text));
const BLOCKS = "blocks Snapshot Consumed";
const EXPLAINED = ["no source", "partial coverage", "estimate"];

test("a row measured by estimate asks the TAM to confirm or replace it", () => {
  const plan = fixturePlan();
  Object.assign(planRow(plan, "Unattended Robot"), {
    consumedBasis: "estimate", consumedAsOf: "2026-07-15", notes: "Illustrative: 60% of the 100 licensed robots, per the Q3 program review.",
  });
  const items = gapList({ plan, document: documentFor(plan), inventory: [], conflicts: [] });
  const estimates = whys(items, "estimate");
  assert.equal(estimates.length, 1);
  assert.equal(estimates[0].ownerRole, "TAM");
  assert.match(estimates[0].item, /Unattended Robot/);
  assert.match(estimates[0].nextStep, /confirm or replace the estimate/i);
  assert.deepEqual(Object.keys(estimates[0]).sort(), ["item", "nextStep", "ownerRole", "why"]);
});

test("an estimate belongs to the TAM even on a user license row, and a measured figure raises nothing", () => {
  const plan = fixturePlan();
  Object.assign(planRow(plan, "Automation Developer"), { consumedQuantity: 12, consumedBasis: "estimate", notes: "Illustrative: 12 seats assigned by the last admin export." });
  Object.assign(planRow(plan, "Unattended Robot"), { consumedBasis: "telemetry", consumedAsOf: "2026-07-31" });
  const items = gapList({ plan, document: documentFor(plan) });
  assert.deepEqual(whys(items, "estimate").map((entry) => entry.ownerRole), ["TAM"]);
  assert.equal(mentioning(items, "Unattended Robot").filter((entry) => EXPLAINED.includes(entry.why)).length, 0);
});

test("the fixture's stale opportunity goes to the AE to re-date or close", () => {
  const plan = fixturePlan();
  const stale = whys(gapList({ plan, document: documentFor(plan) }), "stale opportunity");
  assert.equal(stale.length, 1);
  assert.match(stale[0].item, /Legacy Robot Upsell/);
  assert.equal(stale[0].ownerRole, "AE");
  assert.match(stale[0].nextStep, /re-date or close/i);
  assert.doesNotMatch(stale[0].nextStep, /draw/, "an opportunity draws nothing, re-dated or not");
});

test("the unmapped Agent Units line is a never-bought product, and the unsized line asks for its volume", () => {
  const plan = fixturePlan();
  const items = gapList({ plan, document: documentFor(plan) });
  const never = whys(items, "never-bought product");
  assert.equal(never.length, 1);
  assert.match(never[0].item, /Agent Units Bundle 1K/);
  assert.match(never[0].item, /Agent Pilot/);
  assert.equal(never[0].ownerRole, "AE");
  const unsized = whys(items, "unsized line");
  assert.equal(unsized.length, 1);
  assert.match(unsized[0].item, /AI Units Enterprise Agreement/);
  assert.equal(unsized[0].ownerRole, "AE");
  assert.match(unsized[0].nextStep, /units/i);
  assert.match(unsized[0].nextStep, /so demand and other pipeline activity can count it/, "an opportunity's line sizes no pursuit draw");
});

test("renewals, beyond-window opportunities and platform lines raise no pipeline item", () => {
  const plan = fixturePlan();
  const items = gapList({ plan, document: documentFor(plan) });
  for (const why of ["stale opportunity", "never-bought product", "unsized line"]) assert.equal(whys(items, why).length, 1, why);
  for (const name of ["Annual Renewal", "Robot Expansion FY28", "Platform Standard Tier"]) assert.equal(mentioning(items, name).length, 0, name);
});

test("a priced row with no consumed figure blocks the Snapshot's Consumed, and a $0 row does not", () => {
  const plan = fixturePlan();
  const document = documentFor(plan);
  const fixtureBlocks = whys(gapList({ plan, document }), BLOCKS);
  assert.equal(fixtureBlocks.length, 2, "Automation Developer and AI Units are priced and unmeasured; the $0 platform row and the measured robots are not");
  assert.equal(mentioning(fixtureBlocks, "Automation Developer").length, 1);
  assert.equal(mentioning(fixtureBlocks, "AI Units").length, 1);
  assert.equal(mentioning(fixtureBlocks, "Platform - Standard").length, 0);

  docRow(document, "Platform - Standard").soldArrUsd = 5000;
  const priced = whys(gapList({ plan, document }), BLOCKS);
  assert.equal(priced.length, 3);
  const platform = mentioning(priced, "Platform - Standard");
  assert.equal(platform.length, 1, "one item for the row, naming it");
  assert.equal(platform[0].ownerRole, "TAM");
  assert.match(platform[0].nextStep, /Consumed/);
});

test("a priced platform tier's blocking item asks the TAM for evidence of production use, since a tier is used whole", () => {
  const plan = fixturePlan();
  const document = documentFor(plan);
  docRow(document, "Platform - Standard").soldArrUsd = 5000;
  const [platform, ...rest] = mentioning(whys(gapList({ plan, document }), BLOCKS), "Platform - Standard");
  assert.equal(rest.length, 0, "one item for the tier");
  assert.equal(platform.ownerRole, "TAM");
  assert.match(platform.nextStep, /^Bring a dated statement or telemetry showing the platform in production use \(a tier is used whole, so Consumed is its purchased quantity\)\./);
  assert.doesNotMatch(platform.nextStep, /consumed-to-date figure from a dated source/, "not the generic step");
});

test("a row blocks the Snapshot's Consumed unless its figure is measured or the row is $0, a measured zero included", () => {
  const plan = fixturePlan();
  const document = documentFor(plan);
  docRow(document, "Automation Developer").actualConsumed = 0;
  docRow(document, "AI Units").soldArrUsd = null; // priced by the pricebook, not pinned: still a priced row
  const blocking = whys(gapList({ plan, document }), BLOCKS);
  assert.deepEqual(blocking.map((entry) => entry.item.includes("AI Units")), [true]);
  docRow(document, "AI Units").actualConsumed = 5;
  assert.equal(whys(gapList({ plan, document }), BLOCKS).length, 0, "a measured zero and a measured figure both settle a row");
  delete docRow(document, "AI Units").actualConsumed;
  assert.equal(whys(gapList({ plan, document }), BLOCKS).length, 1, "a missing key reads as null");
});

test("a priced row with no consumed figure is one item: its own reason and evidence, and the Snapshot total it blanks", () => {
  const plan = fixturePlan();
  const items = gapList({ plan, document: documentFor(plan) });
  for (const [name, owner, evidence] of [["Automation Developer", "CSM", /seats assigned/i], ["AI Units", "TAM", /consumed-to-date figure from the entitlement record/]]) {
    const rowItems = items.filter((entry) => entry.item.startsWith(`Consumed to date: ${name}`));
    assert.equal(rowItems.length, 1, `${name}: one item, not a blocking one and a no-source one`);
    const [entry] = rowItems;
    assert.equal(entry.why, BLOCKS, name);
    assert.equal(entry.item, `Consumed to date: ${name} (no source)`, "the row's own reason stays in the item");
    assert.equal(entry.ownerRole, owner, name);
    assert.match(entry.nextStep, evidence, name);
    assert.match(entry.nextStep, /the Snapshot's Consumed and Remaining stay blank/, name);
  }
  assert.equal(whys(items, "no source").filter((entry) => /Consumed to date/.test(entry.item)).length, 0);
});

test("an estimated figure on a row with no contracted price is one item that asks for both", () => {
  const plan = fixturePlan();
  Object.assign(planRow(plan, "Unattended Robot"), { consumedBasis: "estimate", consumedAsOf: "2026-07-15", notes: "Illustrative: 60 of the 100 robots run weekly." });
  const document = documentFor(plan);
  docRow(document, "Unattended Robot").soldQuantity = null;
  const robots = gapList({ plan, document }).filter((entry) => entry.item.includes("Unattended Robot") && entry.item.includes("Consumed"));
  assert.equal(robots.length, 1);
  assert.equal(robots[0].why, BLOCKS);
  assert.match(robots[0].item, /estimate/);
  assert.match(robots[0].item, /no contracted price/);
  assert.match(robots[0].nextStep, /^Confirm or replace the estimate/);
  assert.match(robots[0].nextStep, /contracted ARR and purchased quantity/);
});

test("a measured row with no contracted price blocks the Snapshot's Consumed: the app prices every row it totals", () => {
  const plan = fixturePlan();
  const document = documentFor(plan);
  for (const offering of ["Automation Developer", "AI Units"]) docRow(document, offering).actualConsumed = 5;
  assert.deepEqual(whys(gapList({ plan, document }), BLOCKS), [], "priced and measured");

  docRow(document, "Automation Developer").soldQuantity = null;
  const [unpriced, ...rest] = whys(gapList({ plan, document }), BLOCKS);
  assert.equal(rest.length, 0);
  assert.equal(unpriced.item, "Contracted price: Automation Developer");
  assert.equal(unpriced.ownerRole, "AE");
  assert.match(unpriced.nextStep, /contracted ARR and purchased quantity/);
  assert.match(unpriced.nextStep, /Consumed and Remaining stay blank/);

  docRow(document, "Automation Developer").soldQuantity = 0;
  assert.equal(whys(gapList({ plan, document }), BLOCKS).length, 1, "no positive purchased quantity is no price");

  docRow(document, "Automation Developer").soldQuantity = 20;
  docRow(document, "Automation Developer").soldArrUsd = null;
  assert.equal(whys(gapList({ plan, document }), BLOCKS).length, 0, "with the account's ARR to allocate, a row with no ARR of its own is priced");
  document.renewalEconomics.currentArrUsd = null;
  assert.equal(whys(gapList({ plan, document }), BLOCKS).length, 1, "with neither, it has no price");

  const free = documentFor(plan);
  Object.assign(docRow(free, "Platform - Standard"), { soldQuantity: null, actualConsumed: null });
  assert.equal(mentioning(whys(gapList({ plan, document: free }), BLOCKS), "Platform - Standard").length, 0, "a $0 row never blocks");
});

// --- A pursuit card the app cannot price --------------------------------------------------------------------------

const DEMAND = "blocks Known pipeline demand";
/** A use-case card's step: the team sizes the pursuit's draw on existing entitlement. */
const USE_CASE_DEMAND_STEP = "Size this pursuit's draw on the account's existing entitlement, or choose top pursuits in the app that draw on it, then rerun Step 9.5 on the exported draft; until then Known pipeline demand and Net of pipeline stay blank.";
/** An opportunity card's step: an opportunity's product lines are new entitlement, so it never draws on today's rows. */
const OPPORTUNITY_DEMAND_STEP = "This opportunity adds its own entitlement and draws nothing from today's rows; pick top pursuits in the app that draw on existing entitlement (team-sized use cases), then rerun Step 9.5 on the exported draft.";
/** An open opportunity record as the app holds it; `estimatedIarrUsd` ranks it for the Snapshot's cards. */
const opp = (n, extra = {}) => ({ id: `opp-${n}`, key: `006TEST000000${n}`, name: `Pursuit ${n}`, status: "Open", estimatedIarrUsd: 1000 * n, ...extra });
/** The fixture's document with identified rows (row-0 Automation Developer, row-1 robots, row-2 AI Units, row-3 platform) and these opportunities and pursuit entries. */
function withPursuits(opportunities, pursuits = [], topPursuitIds = []) {
  const plan = fixturePlan();
  const document = documentFor(plan);
  document.consumptionPlan.groups.flatMap((group) => group.rows).forEach((row, at) => { row.id = `row-${at}`; });
  document.pipelineOpportunities = opportunities;
  document.snapshot = { pursuits, topPursuitIds };
  return { plan, document };
}
const withheld = ({ plan, document }) => whys(gapList({ plan, document }), DEMAND);

test("a shown opportunity with no pursuit entry has no Est. rev., so Known pipeline demand stays blank, and the AE picks pursuits that draw on existing entitlement", () => {
  const { plan, document } = withPursuits([opp(1)]);
  const inventory = [inventoryRow("/accountTeam/solutionsEngineer/name", { tab: "Cover", who: "evidence", label: "cover-nonblocking" })];
  const items = gapList({ plan, document, inventory });
  const demand = whys(items, DEMAND);
  assert.equal(demand.length, 1);
  assert.equal(demand[0].ownerRole, "AE");
  assert.match(demand[0].item, /Pursuit 1/);
  assert.equal(demand[0].nextStep, OPPORTUNITY_DEMAND_STEP, "an opportunity's product lines are new entitlement: it is never sized to draw");
  const firstNonBlocking = items.findIndex((entry) => ![BLOCKS, DEMAND].includes(entry.why));
  assert.ok(items.findIndex((entry) => entry.why === DEMAND) < firstNonBlocking, "it is ordered with the other blocking items");
  assert.ok(items.findIndex((entry) => entry.why === BLOCKS) < firstNonBlocking);
  assert.ok(items.findIndex((entry) => entry.why === DEMAND) < items.findIndex((entry) => entry.item.includes("cover-nonblocking")), "even ahead of a non-blocking item on an earlier tab");
});

test("a shown opportunity whose draws are sized and priced raises nothing, a $0 row's draw included", () => {
  const sized = [{ opportunityId: "opp-1", draw: [{ rowId: "row-2", units: 400000 }, { rowId: "row-1", units: 20 }] }];
  assert.deepEqual(withheld(withPursuits([opp(1)], sized)), []);
  const allocated = withPursuits([opp(1)], sized);
  allocated.document.consumptionPlan.groups[2].rows[0].soldArrUsd = null;
  assert.deepEqual(withheld(allocated), [], "a row with no ARR of its own takes a share of the account's ARR, as the app allocates it");
  const free = [{ opportunityId: "opp-1", draw: [{ rowId: "row-3", units: 1 }] }];
  assert.deepEqual(withheld(withPursuits([opp(1)], free)), [], "a row whose ARR is 0 is priced at 0");
  const unchosen = [{ opportunityId: "opp-1", draw: [{ rowId: "row-2", units: 5 }, { rowId: "", units: null }] }];
  assert.deepEqual(withheld(withPursuits([opp(1)], unchosen)), [], "a draw line with no row chosen is an unfinished edit, not a draw");
});

test("a shown opportunity whose draw is unsized, on an unpriced row or on a row the document lacks has no Est. rev.", () => {
  const draw = (...lines) => [{ opportunityId: "opp-1", draw: lines }];
  const cases = [
    ["a draw on a row the document does not have", (documents) => documents, draw({ rowId: "row-99", units: 5 }), /no contracted price/],
    ["a draw on a row with no ARR, on an account with no ARR to allocate", (documents) => { documents.document.consumptionPlan.groups[2].rows[0].soldArrUsd = null; documents.document.renewalEconomics.currentArrUsd = null; }, draw({ rowId: "row-2", units: 5 }), /no contracted price/],
    ["a draw on a row with no purchased quantity", (documents) => { documents.document.consumptionPlan.groups[1].rows[0].soldQuantity = null; }, draw({ rowId: "row-1", units: 5 }), /no contracted price/],
    ["a draw on a row with a zero purchased quantity and a price", (documents) => { documents.document.consumptionPlan.groups[1].rows[0].soldQuantity = 0; }, draw({ rowId: "row-1", units: 5 }), /no contracted price/],
    ["one unpriced line among sized, priced ones", (documents) => { documents.document.consumptionPlan.groups[0].rows[0].soldQuantity = undefined; }, draw({ rowId: "row-2", units: 5 }, { rowId: "row-0", units: 2 }), /no contracted price/],
    ["a draw line with no units", (documents) => documents, draw({ rowId: "row-2", units: null }), /no units/],
    ["a pursuit entry with only an unfinished draw line", (documents) => documents, draw({ rowId: "", units: null }), /no (pursuit )?draw/],
    ["a pursuit entry with no draw", (documents) => documents, draw(), /no (pursuit )?draw/],
    ["another opportunity's pursuit entry", (documents) => documents, [{ opportunityId: "opp-9", draw: [{ rowId: "row-2", units: 5 }] }], /no (pursuit )?draw/],
  ];
  for (const [name, change, pursuits, reason] of cases) {
    const documents = withPursuits([opp(1)], pursuits);
    change(documents);
    const demand = withheld(documents);
    assert.equal(demand.length, 1, name);
    assert.match(demand[0].item, /Pursuit 1/, name);
    assert.match(demand[0].item, reason, name);
    assert.equal(demand[0].ownerRole, "AE", name);
  }
});

test("only the pursuits the app shows are asked for: the top three by value, or the ones the team names", () => {
  const sized = (n) => ({ opportunityId: `opp-${n}`, draw: [{ rowId: "row-2", units: 5 }] });
  const ranked = [opp(1), opp(2), opp(3), opp(4), opp(5, { status: "Closed Won", estimatedIarrUsd: 99000 })];
  assert.deepEqual(withheld(withPursuits(ranked, [sized(2), sized(3), sized(4)])), [], "opportunity 1 ranks fourth and Closed Won opportunity 5 is not a pursuit, so neither is shown");
  const [one] = withheld(withPursuits(ranked, [sized(3), sized(4)]));
  assert.match(one.item, /Pursuit 2/, "the third card is the one with no draw");

  const named = withheld(withPursuits(ranked, [], ["opp-1", "opp-2"]));
  assert.deepEqual(named.map((entry) => /Pursuit (\d)/.exec(entry.item)[1]).sort(), ["1", "2"], "the team's two named pursuits, not the ranking");
  assert.deepEqual(withheld(withPursuits([], [])), [], "a document with no opportunities shows no cards");
});

test("a shown opportunity closing beyond 12 months gets the step any opportunity gets: its close date is not why it has no draw", () => {
  const { plan, document } = withPursuits([opp(1, { key: "006EXAMPLE0000003", name: "Example Corp - Robot Expansion FY28" })]);
  const [demand, ...rest] = withheld({ plan, document });
  assert.equal(rest.length, 0);
  assert.equal(demand.item, 'Pursuit card "Example Corp - Robot Expansion FY28": Est. rev. is withheld (it has no pursuit entry or no draw)');
  assert.equal(demand.ownerRole, "AE");
  assert.equal(demand.nextStep, OPPORTUNITY_DEMAND_STEP);
});

test("a shown use-case card with no draw keeps the step to size its draw; an opportunity card gets the expansion-aware step whatever withholds its Est. rev.", () => {
  const { plan, document } = withPursuits(
    [opp(1, { key: "invoice-intake-agent", name: "Invoice intake agent", estimatedIarrUsd: 0 }), opp(2), opp(3)],
    [{ opportunityId: "opp-3", draw: [{ rowId: "row-2", units: null }] }],
  );
  plan.pipeline.useCases = [{ key: "invoice-intake-agent", name: "Invoice intake agent", source: "Team expansion workbook (2026-07-28)", asOf: "2026-07-28", lines: [{ product: "AI Units", units: 5, row: "AI Units" }] }];
  assert.deepEqual(withheld({ plan, document }).map(({ item, nextStep }) => [item, nextStep]), [
    ['Pursuit card "Pursuit 3": Est. rev. is withheld (a draw line has no units)', OPPORTUNITY_DEMAND_STEP],
    ['Pursuit card "Pursuit 2": Est. rev. is withheld (it has no pursuit entry or no draw)', OPPORTUNITY_DEMAND_STEP],
    ['Pursuit card "Invoice intake agent": Est. rev. is withheld (it has no pursuit entry or no draw)', USE_CASE_DEMAND_STEP],
  ]);
});

test("a user license row's consumed gaps go to the CSM; every other row's go to the TAM", () => {
  const plan = fixturePlan();
  const items = gapList({ plan, document: documentFor(plan) });
  const owner = (name, why) => mentioning(whys(items, why), name).map((entry) => entry.ownerRole);
  assert.deepEqual(owner("Automation Developer", BLOCKS), ["CSM"]);
  assert.deepEqual(owner("AI Units", BLOCKS), ["TAM"]);
  const $0 = fixturePlan();
  for (const product of ["Automation Developer", "AI Units"]) planRow($0, product).arrUsd = 0;
  const free = gapList({ plan: $0, document: documentFor($0) });
  const freeOwner = (name) => mentioning(whys(free, "no source"), name).map((entry) => entry.ownerRole);
  assert.deepEqual([freeOwner("Automation Developer"), freeOwner("AI Units")], [["CSM"], ["TAM"]], "a $0 row blocks nothing, and keeps its own item");
});

test("an unmeasured row says why: partial coverage when telemetry reaches only part of the account, else no source", () => {
  const plan = fixturePlan();
  const document = documentFor(plan);
  // Both rows are priced, so each is its "blocks Snapshot Consumed" item, which keeps the row's reason.
  const reasons = (draft) => gapList({ plan: draft, document }).filter((entry) => entry.item.startsWith("Consumed to date:")).map((entry) => /\(([^)]+)\)$/.exec(entry.item)?.[1]);

  assert.deepEqual(reasons(plan), ["no source", "no source"], "no telemetry section");
  for (const coverage of ["complete", "none"]) {
    assert.deepEqual(reasons({ ...plan, telemetry: { asOf: "2026-07-31", coverage, note: "" } }), ["no source", "no source"], coverage);
  }
  const partialPlan = { ...plan, telemetry: { asOf: "2026-07-31", coverage: "partial", note: "Illustrative: consumables are not captured for this deployment." } };
  assert.deepEqual(reasons(partialPlan), ["partial coverage", "partial coverage"]);
  assert.ok(gapList({ plan: partialPlan, document }).filter((entry) => entry.item.startsWith("Consumed to date:")).every((entry) => /Telemetry covers only part/.test(entry.nextStep)));
  assert.throws(() => gapList({ plan: { ...plan, telemetry: { coverage: "mostly" } }, document }), GapListError);
});

test("the next step names the evidence to bring for each kind of row", () => {
  const plan = fixturePlan();
  planRow(plan, "Unattended Robot").consumedQuantity = null;
  plan.telemetry = { asOf: "2026-07-31", coverage: "partial", note: "Illustrative: this deployment is outside the telemetry layer." };
  const items = gapList({ plan, document: documentFor(plan) });
  const step = (name) => items.find((entry) => entry.item === `Consumed to date: ${name} (partial coverage)`).nextStep;
  assert.match(step("Unattended Robot"), /allocation figure/i);
  assert.match(step("Unattended Robot"), /estimate with its basis/i);
  assert.match(step("Automation Developer"), /seats assigned/i);
  assert.match(step("AI Units"), /consumed-to-date/i);
  assert.match(step("AI Units"), /outside the telemetry layer/, "the plan's own coverage note travels with the item");
  assert.deepEqual(mentioning(whys(items, BLOCKS), "Unattended Robot").map((entry) => entry.ownerRole), ["TAM"]);
});

test("a platform row needs no consumed figure of its own", () => {
  const plan = fixturePlan();
  const document = documentFor(plan);
  const inventory = [inventoryRow("/consumptionPlan/groups/*/rows/*/actualConsumed", { tab: "Renewal Test", pointer: "/consumptionPlan/groups/3/rows/0/actualConsumed", who: "evidence", label: "Platform - Standard" })];
  const items = gapList({ plan, document, inventory });
  assert.equal(mentioning(items, "Platform - Standard").length, 0, "a $0 tier is granted, not consumed, and the Snapshot skips it");
});

test("a team's own consumed figure answers a plan row the plan left empty", () => {
  const plan = fixturePlan();
  const document = documentFor(plan);
  docRow(document, "Automation Developer").actualConsumed = 7;
  const items = gapList({ plan, document });
  assert.equal(mentioning(items, "Automation Developer").length, 0);
});

test("an inventory row for the same consumed figure the plan explains is one item, not two", () => {
  const plan = fixturePlan();
  Object.assign(planRow(plan, "Unattended Robot"), { consumedBasis: "estimate", notes: "Illustrative: 60 of the 100 robots run weekly." });
  const document = documentFor(plan);
  const consumed = (index, row, label) => inventoryRow("/consumptionPlan/groups/*/rows/*/actualConsumed", {
    tab: "Renewal Test", pointer: `/consumptionPlan/groups/${index}/rows/${row}/actualConsumed`, who: "evidence", policy: "evidence_required", label,
  });
  const inventory = [consumed(0, 0, "Automation Developer"), consumed(1, 0, "Unattended Robot"), consumed(2, 0, "AI Units")];
  const items = gapList({ plan, document, inventory });
  for (const [name, why] of [["Automation Developer", BLOCKS], ["Unattended Robot", "estimate"], ["AI Units", BLOCKS]]) {
    assert.deepEqual(items.filter((entry) => entry.item.startsWith("Consumed to date") && entry.item.includes(name)).map((entry) => entry.why), [why], name);
  }
  assert.equal(items.length, gapList({ plan, document }).length, "the inventory added nothing");
});

test("an inventory row for a consumed figure the plan knows nothing about still gets an item, owned by the row's category", () => {
  const document = {
    consumptionPlan: { groups: [
      { element: "Users", rows: [{ offering: "Seat Pack", soldArrUsd: 0, actualConsumed: null }] },
      { element: "Robots", rows: [{ offering: "Bot Pack", soldArrUsd: 0, actualConsumed: null }] },
    ] },
  };
  const inventory = ["Seat Pack", "Bot Pack"].map((label, index) => inventoryRow("/consumptionPlan/groups/*/rows/*/actualConsumed", {
    tab: "Renewal Test", pointer: `/consumptionPlan/groups/${index}/rows/0/actualConsumed`, who: "evidence", label,
  }));
  const items = gapList({ plan: barePlan(), document, inventory });
  assert.deepEqual(items.map((entry) => [entry.why, entry.ownerRole]), [["no source", "CSM"], ["no source", "TAM"]]);
  assert.match(items[0].item, /Seat Pack/);
  assert.match(items[0].nextStep, /seats assigned/i);
  assert.match(items[1].nextStep, /allocation figure/i);
});

test("an inventory row for /pipelineOpportunities/*/owner goes to the AE", () => {
  const inventory = [inventoryRow("/pipelineOpportunities/*/owner", { requirement: "block", blocks: true, label: "Example Corp - AI Units Phase 2" })];
  const items = gapList({ plan: barePlan(), document: {}, inventory });
  assert.equal(items.length, 1);
  assert.equal(items[0].ownerRole, "AE");
  assert.equal(items[0].why, "team only");
  assert.match(items[0].item, /Example Corp - AI Units Phase 2/);
});

test("the owner role of each field the brief names", () => {
  const expected = {
    "/renewalTest/healthyAtPercent": "AE + CSM + TAM",
    "/snapshot/status": "CSM",
    "/renewalTest/status": "CSM",
    "/renewalTest/verdict": "CSM",
    "/renewalTest/rows/*/confidence": "CSM",
    "/snapshot/accountPlay": "CSM",
    "/pipelineOpportunities/*/owner": "AE",
    "/pipelineOpportunities/*/nextGate": "AE",
    "/pipelineOpportunities/*/nextGateDate": "AE",
    "/pipelineOpportunities/*/motions": "AE",
    "/snapshot/topPursuitIds": "AE",
    "/consumptionPlan/groups/*/rows/*/actualConsumed": "TAM",
    "/a/field/nobody/mapped": "CSM",
  };
  for (const [generic, ownerRole] of Object.entries(expected)) {
    const rule = OWNER_ROLES[generic] ?? OWNER_ROLES["*"];
    assert.equal(rule.ownerRole, ownerRole, `OWNER_ROLES ${generic}`);
    assert.ok(typeof rule.nextStep === "string" && rule.nextStep.length > 10, `next step for ${generic}`);
    const inventory = [inventoryRow(generic, { tab: "Renewal Test", label: "Probe" })];
    const [entry] = gapList({ plan: barePlan(), document: {}, inventory });
    assert.equal(entry.ownerRole, ownerRole, `gapList ${generic}`);
    assert.equal(entry.nextStep.startsWith(rule.nextStep), true, `gapList next step for ${generic}`);
  }
  assert.equal(OWNER_ROLES["*"].ownerRole, "CSM");
  assert.match(OWNER_ROLES["/snapshot/topPursuitIds"].nextStep, /then rerun Step 9\.5 on the exported draft/, "other cards change what other pipeline activity counts");
  for (const field of ["/snapshot/pursuits", "/snapshot/pursuits/*/draw/*/units"]) {
    assert.doesNotMatch(OWNER_ROLES[field].nextStep, /from the opportunity's quantities|each top opportunity/, `${field}: an opportunity's product lines are new entitlement, never sized as a draw`);
    assert.match(OWNER_ROLES[field].nextStep, /use case/, field);
  }
});

test("a field the account team states is team only; one a source could fill and none did has no source", () => {
  const inventory = [
    inventoryRow("/snapshot/status", { who: "attest", policy: "attestation_allowed" }),
    inventoryRow("/renewalTest/healthyAtPercent", { who: "human", tab: "Renewal Test" }),
    inventoryRow("/snapshot/accountPlay", { who: "evidence", policy: "evidence_required" }),
  ];
  const items = gapList({ plan: barePlan(), document: {}, inventory });
  assert.deepEqual(items.map((entry) => entry.why).sort(), ["no source", "team only", "team only"]);
});

test("repeated records of one field are one item naming the records; an empty list says what each record needs", () => {
  const inventory = [
    ...["alpha", "beta", "gamma"].map((label, at) => inventoryRow("/strategicInitiatives/*/blocker", {
      tab: "Strategic Initiatives", pointer: `/strategicInitiatives/${at}/blocker`, who: "evidence", label,
    })),
    inventoryRow("/pipelineOpportunities", { who: "evidence", kind: "no records", recordGating: ["human: owner", "human: nextGate"] }),
  ];
  const items = gapList({ plan: barePlan(), document: {}, inventory });
  assert.equal(items.length, 2);
  const initiatives = items.find((entry) => /alpha/.test(entry.item));
  assert.match(initiatives.item, /beta/);
  assert.match(initiatives.item, /gamma/);
  const records = items.find((entry) => /no records/.test(entry.item));
  assert.equal(records.ownerRole, "AE");
  assert.match(records.nextStep, /Each record also needs: human: owner, human: nextGate\./);
});

test("a field with no name of its own reads from its pointer, without the containers or the tab's own name", () => {
  const inventory = [
    inventoryRow("/strategicInitiatives/*/milestone3Mo", { tab: "Strategic Initiatives", who: "evidence", label: "alpha" }),
    inventoryRow("/consumptionPlan/groups/*/rows/*/entitlementNote", { tab: "Renewal Test", who: "evidence", label: "Seat Pack" }),
  ];
  assert.deepEqual(gapList({ plan: barePlan(), document: {}, inventory }).map((entry) => entry.item), [
    "Renewal Test: Consumption plan entitlement note [Seat Pack]",
    "Strategic Initiatives: Milestone 3 mo [alpha]",
  ]);
});

test("fields no tab reads and system-managed fields are left out, unless a field blocks publication", () => {
  const inventory = [
    inventoryRow("/health/overall/status", { tab: "No tab today", label: "quiet" }),
    inventoryRow("/functionalNeeds/*/accountableOwner", { tab: "No tab today", blocks: true, label: "loud" }),
    inventoryRow("/snapshot/csPriorities", { who: "skip", label: "system" }),
  ];
  const items = gapList({ plan: barePlan(), document: {}, inventory });
  assert.equal(items.length, 1);
  assert.match(items[0].item, /loud/);
});

test("consumption-plan fields no v7 tab draws are left out, unless one blocks publication", () => {
  const undrawn = [
    "/consumptionPlan/groups/*/rows/*/comments",
    "/consumptionPlan/groups/*/rows/*/forecastUnits/q1",
    "/consumptionPlan/groups/*/rows/*/forecastUnits/q2",
    "/consumptionPlan/groups/*/rows/*/forecastUnits/q3",
    "/consumptionPlan/groups/*/rows/*/forecastUnits/q4",
    "/consumptionPlan/groups/*/rows/*/licensingModel",
    "/consumptionPlan/groups/*/rows/*/skuCode",
    "/consumptionPlan/groups/*/rows/*/discountPercent",
    "/consumptionPlan/businessValue/realizedUsd",
    "/consumptionPlan/businessValue/realizedOwner",
    "/consumptionPlan/businessValue/forecastedUsd",
    "/consumptionPlan/primaryUseCases",
  ];
  // instructions-lib.mjs gives all of these the Renewal Test tab, as it does every consumptionPlan field.
  const asRead = (generic, extra = {}) => inventoryRow(generic, { tab: "Renewal Test", who: "evidence", label: "Seat Pack", ...extra });
  const document = { consumptionPlan: { groups: [{ element: "Users", rows: [{ offering: "Seat Pack", soldArrUsd: 0, actualConsumed: 3 }] }] } };

  assert.deepEqual(gapList({ plan: barePlan(), document, inventory: undrawn.map((generic) => asRead(generic)) }), []);
  const blocking = gapList({ plan: barePlan(), document, inventory: undrawn.map((generic) => asRead(generic, { blocks: true })) });
  assert.equal(blocking.length, undrawn.length, "a field that blocks publication is listed whatever tab reads it");
  assert.ok(blocking.every((entry) => entry.item.includes("(required to publish)")));

  const drawn = gapList({ plan: barePlan(), document, inventory: [asRead("/renewalTest/rows/*/confidence", { who: "attest" }), asRead("/consumptionPlan/groups/*/rows/*/soldQuantity")] });
  assert.equal(drawn.length, 2, "a field the Renewal Test does draw stays");
});

test("blocking items come first, then each tab in the deck's order", () => {
  const inventory = [
    inventoryRow("/strategicInitiatives/*/blocker", { tab: "Strategic Initiatives", who: "evidence", label: "last-tab" }),
    inventoryRow("/renewalTest/verdict", { tab: "Renewal Test", label: "third-tab" }),
    inventoryRow("/accountTeam/accountExecutive/name", { tab: "Cover", who: "evidence", label: "first-tab" }),
    inventoryRow("/renewalDate", { tab: "Snapshot", who: "evidence", requirement: "block", blocks: true, label: "blocks-publication" }),
    inventoryRow("/snapshot/status", { tab: "Snapshot", label: "second-tab" }),
  ];
  const plan = fixturePlan();
  const items = gapList({ plan, document: documentFor(plan), inventory });
  const at = (text) => items.findIndex((entry) => entry.item.includes(text));
  const blocking = (entry) => entry.why === BLOCKS || entry.item.includes("blocks-publication");
  const firstNonBlocking = items.findIndex((entry) => !blocking(entry));
  const lastBlocking = items.map(blocking).lastIndexOf(true);
  assert.ok(at("blocks-publication") >= 0 && items.some((entry) => entry.why === BLOCKS));
  assert.ok(lastBlocking < firstNonBlocking, "every blocking item precedes every other");
  assert.ok(at("first-tab") < at("second-tab") && at("second-tab") < at("third-tab") && at("third-tab") < at("last-tab"), "Cover, Snapshot, Renewal Test, Strategic Initiatives");
});

test("an other pipeline activity of $0 names the open opportunities off the cards that the plan valued at $0", () => {
  const plan = fixturePlan();
  plan.pipeline.opportunities = plan.pipeline.opportunities.filter(({ salesforceId }) => !["006EXAMPLE0000003", "006EXAMPLE0000007"].includes(salesforceId));
  const records = ["006EXAMPLE0000001", "006EXAMPLE0000002", "006EXAMPLE0000006", "006EXAMPLE0000008"].map((key, at) => ({ id: `opp-${at}`, key, name: key, status: "Open", estimatedIarrUsd: 4000 - at * 1000 }));
  const document = { ...documentFor(plan), pipelineOpportunities: records, snapshot: { otherPipelineActivityUsd: 0, pursuits: [], topPursuitIds: [] } };
  const [item, ...rest] = gapList({ plan, document }).filter((entry) => /other pipeline activity is \$0/.test(entry.item));
  assert.equal(rest.length, 0);
  assert.match(item.item, /Example Corp - Platform Standard Tier/, "the one open opportunity off the cards, whose platform line draws no entitlement value");
  assert.doesNotMatch(item.item, /Agent Pilot/, "a card the app shows is not other activity");
  assert.equal(item.ownerRole, "AE");
  assert.match(item.nextStep, /^Confirm that "Example Corp - Platform Standard Tier" adds no entitlement value beyond the pursuit cards/);
  assert.doesNotMatch(item.nextStep, /there is no other pipeline activity/);
});

test("an other pipeline activity of $0 asks the AE to confirm there is none", () => {
  const plan = barePlan();
  const confirm = (value) => gapList({ plan, document: { snapshot: { otherPipelineActivityUsd: value } } });
  const [item, ...rest] = confirm(0);
  assert.equal(rest.length, 0);
  assert.equal(item.ownerRole, "AE");
  assert.equal(item.why, "team only");
  assert.match(item.nextStep, /no other (pipeline )?activity/i);
  assert.equal(confirm(30000).length, 0);
  assert.equal(confirm(null).length, 0, "an empty value is the inventory's to report, not a zero to confirm");
  assert.equal(gapList({ plan, document: {} }).length, 0);
});

test("each conflict line is one item for the AE, and a repeated line is one", () => {
  const lines = [
    'snapshot pursuit "Example Corp - AI Units Phase 2" draw on "AI Units": kept 800000, which this plan did not write; Salesforce opportunities now give 1000000.',
    'renewalTest row "Consumables|AI Units" demand12MoUnits: kept 5, which this plan did not write; Salesforce opportunities now give 9.',
  ];
  for (const conflicts of [{ conflicts: lines }, [...lines, lines[0]]]) {
    const items = gapList({ plan: barePlan(), document: {}, conflicts });
    assert.deepEqual(items.map((entry) => entry.item), lines);
    assert.ok(items.every((entry) => entry.why === "conflict" && entry.ownerRole === "AE"));
    assert.match(items[0].nextStep, /confirm which value stands/i);
  }
  assert.equal(gapList({ plan: barePlan(), document: {}, conflicts: { conflicts: [] } }).length, 0);
});

/** One conflict line of each shape pipeline.mjs writes, produced by its own functions so a change to its wording fails here. */
function conflictLines() {
  const plan = fixturePlan();
  plan.pipeline.opportunities = plan.pipeline.opportunities.filter(({ salesforceId }) => salesforceId !== "006EXAMPLE0000007");
  plan.pipeline.written = {
    "draw:006GONE0000001:AI Units": 5, // an opportunity that left the plan
    "renewalTest:Gone Row:demand12MoUnits": 10, // a renewal-test row nothing drives any more
    "renewalTest:AI Units:demand12MoUnits": 1400000, // a figure the team cleared
    "opportunity:006EXAMPLE0000006:status": "Open", // a record the team deleted
    "renewalTest:Unattended Robot:demand12MoUnits": 20, // a renewal-test row the team deleted
    "draw:006EXAMPLE0000003:Unattended Robot": 10, // a draw an earlier run wrote for an opportunity, still on its card
  };
  const document = documentFor(plan);
  const rows = document.consumptionPlan.groups.flatMap((group) => group.rows);
  rows.forEach((row, at) => { row.id = `row-${at}`; });
  const rowId = (offering) => rows.find((row) => row.offering === offering).id;
  document.pipelineOpportunities = [
    { id: "opp-1", key: "006EXAMPLE0000001", name: "Example Corp - AI Units and Robot Expansion", projectedConsumption: "The team's own wording" }, // a value the team wrote
    { id: "opp-2", key: "006EXAMPLE0000002", name: "Example Corp - AI Units Phase 2" },
    { id: "opp-3", key: "006EXAMPLE0000003", name: "Example Corp - Robot Expansion FY28" },
    { id: "opp-8", key: "platform-tier", name: "Example Corp - Platform Standard Tier" }, // a record the team keyed otherwise
  ];
  document.snapshot = { pursuits: [{ opportunityId: "opp-3", draw: [{ rowId: rowId("Unattended Robot"), units: 10 }] }] };
  document.renewalTest = { rows: [{ rowId: rowId("AI Units"), pipelineDriver: "", demand6MoUnits: null, demand12MoUnits: null }] };
  const numbers = numberFindings(plan, document).conflicts;

  // Only a use case draws, so the draw lines that leave or that the team removed are a use case's.
  const drawing = fixturePlan();
  drawing.pipeline.opportunities = [];
  const useCase = (key, name, changes = {}) => ({
    key, name, source: "Team expansion workbook (2026-07-28)", asOf: "2026-07-28",
    lines: [{ product: "AI Units", units: 5, row: "AI Units" }, { product: "Unattended Robot", units: 4, row: "Unattended Robot" }], ...changes,
  });
  drawing.pipeline.useCases = [useCase("intake-one", "Intake one"), useCase("intake-two", "Intake two"), useCase("intake-late", "Intake late", { startDate: "2027-12-01" })];
  drawing.pipeline.written = {
    "useCase:intake-one:draw:Automation Developer": 5, // a draw on a row a use case in the plan no longer sizes
    "useCase:intake-one:draw:Unattended Robot": 4, // a draw line the team deleted from its card
    "useCase:intake-two:draw:AI Units": 5, // a card the team deleted
    "useCase:intake-late:draw:AI Units": 5, // draws of a use case that now starts beyond 12 months
  };
  const drawn = documentFor(drawing);
  const drawnRows = drawn.consumptionPlan.groups.flatMap((group) => group.rows);
  drawnRows.forEach((row, at) => { row.id = `row-${at}`; });
  drawn.pipelineOpportunities = [{ id: "uc-1", key: "intake-one", name: "Intake one" }, { id: "uc-2", key: "intake-two", name: "Intake two" }];
  drawn.snapshot = { pursuits: [{ opportunityId: "uc-1", draw: [{ rowId: drawnRows.find((row) => row.offering === "AI Units").id, units: 5 }] }] };
  const draws = numberFindings(drawing, drawn).conflicts;

  const unsized = otherActivityFindings(fixturePlan(), documentFor(fixturePlan())).conflicts; // the fixture's unsized line, off every card
  const recorded = fixturePlan();
  recorded.pipeline.written = { otherPipelineActivityUsd: 30000 };
  const stale = { ...documentFor(recorded), snapshot: { otherPipelineActivityUsd: 30000 } };
  const cleared = otherActivityFindings(recorded, stale).conflicts; // the figure this plan wrote, withdrawn for that line
  planRow(plan, "AI Units").arrUsd = null; // no contracted unit price to value the other pipeline activity
  const unpriced = otherActivityFindings(plan, documentFor(plan)).conflicts;
  return [...numbers, ...draws, ...unsized, ...cleared, ...unpriced];
}

test("a conflict line gets the next step its own shape calls for", () => {
  const lines = conflictLines();
  const line = (pattern) => {
    const found = lines.filter((candidate) => pattern.test(candidate));
    assert.equal(found.length, 1, `one line of the shape ${pattern}:\n${lines.join("\n")}`);
    return found[0];
  };
  const DELETED = [/confirm the team meant to remove it/i, /add it back in the app/];
  const shapes = [
    [line(/projectedConsumption: kept "The team's own wording", which this plan did not write;/), /confirm which value stands/i, /account team's or what Salesforce now shows/],
    [line(/^Opportunity 006GONE0000001 is no longer open in this plan;/), /confirm its Salesforce status/i, /close it or remove its card, draws and demand in the app/],
    [line(/^Use case "Intake one" \(intake-one\): its earlier draw on "Automation Developer" is no longer in this plan's lines/), /confirm whether the draw still stands/i, /keep it or remove it in the app/],
    [line(/^renewalTest row "Gone Row": no open opportunity in this plan drives it any more/), /confirm the row's driver and demand/i, /change or clear them in the app/],
    [line(/^renewalTest row "AI Units" demand12MoUnits: left blank, as the account team cleared it/), /confirm the team meant to clear it/i, /enter the value Salesforce now gives in the app/],
    [line(/^Use case "Intake one" \(intake-one\): its draw on "Unattended Robot", which this plan wrote, is no longer on its pursuit card/), ...DELETED],
    [line(/^Use case "Intake two" \(intake-two\): its pursuit card, which this plan added, is no longer in the document/), ...DELETED],
    [line(/\(006EXAMPLE0000006\): its record, which this plan added, is no longer in the document/), ...DELETED],
    [line(/^renewalTest row "Unattended Robot", which this plan added, is no longer in the document/), ...DELETED],
    [line(/\(006EXAMPLE0000008\): the document has a record of that name keyed "platform-tier"/), /set that record's key in the app to the opportunity's Salesforce id/i, /instead of adding a second/],
    [line(/^Use case "Intake late" \(intake-late\) now starts 2027-12-01, more than 12 months after 2026-08-01/), /re-date the use case in the plan file/i, /remove its draws in the app/],
    [line(/^Opportunity "Example Corp - Robot Expansion FY28" \(006EXAMPLE0000003\): this plan no longer draws for opportunities/), /^Remove the draws named from the opportunity's pursuit card in the app/, /adds its own entitlement and draws nothing from today's rows/],
    [line(/^snapshot\.otherPipelineActivityUsd not written: \d+ line\(s\) have no unit volume/), /state the units of each line named/i, /enter the other pipeline activity in whole USD/],
    [line(/^snapshot\.otherPipelineActivityUsd cleared the 30000 this plan wrote earlier: \d+ line\(s\) have no unit volume/), /state the units of each line named/i, /enter the other pipeline activity in whole USD/],
    [line(/^snapshot\.otherPipelineActivityUsd not written: \d+ sized line\(s\) have no contracted unit price/), /contracted ARR and purchased quantity/i, /enter the other pipeline activity in whole USD/],
  ];
  assert.equal(lines.length, shapes.length, "every line the scenario produced has its shape here");
  const items = gapList({ plan: barePlan(), document: {}, conflicts: shapes.map(([text]) => text) });
  assert.equal(items.length, shapes.length);
  for (const [text, ...steps] of shapes) {
    const entry = items.find((candidate) => candidate.item === text);
    assert.ok(entry, text);
    assert.equal(entry.why, "conflict");
    assert.equal(entry.ownerRole, "AE");
    for (const step of steps) assert.match(entry.nextStep, step, text);
    if (!/: kept /.test(text)) assert.doesNotMatch(entry.nextStep, /which value stands/i, `only a "kept" line asks which value stands: ${text}`);
  }
  assert.equal(new Set(items.map((entry) => entry.nextStep)).size, shapes.length - 4, "each shape has a next step of its own; the four removals share one, and a withdrawn figure shares its reason's");
});

test("a use case's departure and re-key lines get next steps of their own", () => {
  const plan = fixturePlan();
  plan.pipeline.useCases = [{ key: "invoice-intake-agent", name: "Invoice intake agent", source: "Team expansion workbook (2026-07-28)", asOf: "2026-07-28", lines: [{ product: "AI Units", units: 5, row: "AI Units" }] }];
  plan.pipeline.written = { "useCase:old-pursuit:status": "Open" };
  const document = documentFor(plan);
  document.pipelineOpportunities = [{ id: "opp-u", key: "intake", name: "Invoice intake agent" }];
  const lines = numberFindings(plan, document).conflicts;
  assert.equal(lines.length, 2, lines.join("\n"));
  const items = gapList({ plan: barePlan(), document: {}, conflicts: lines });
  const step = (pattern) => items.find((entry) => pattern.test(entry.item)).nextStep;
  assert.match(step(/^Use case old-pursuit is no longer in this plan;/), /^Confirm with the account team whether the pursuit is still planned/);
  assert.match(step(/^Use case old-pursuit is no longer in this plan;/), /remove its record, card, draws and demand in the app/);
  assert.match(step(/keyed "intake", so no second record is added/), /^Set that record's key in the app to the use case's key, given in parentheses/);
  assert.ok(items.every((entry) => entry.why === "conflict" && entry.ownerRole === "AE"));
});

test("a conflict line of a shape the pipeline does not write yet gets a neutral next step", () => {
  const [item] = gapList({ plan: barePlan(), document: {}, conflicts: ["something else pipeline.mjs might say one day."] });
  assert.equal(item.why, "conflict");
  assert.doesNotMatch(item.nextStep, /which value stands|Salesforce status|unit price/i);
  assert.match(item.nextStep, /update the document or the plan so they agree/);
});

test("a schema 1.11 document gets only what its tabs show: each unmeasured row once, and no Snapshot, pursuit card or pipeline item", () => {
  const plan = fixturePlan();
  // A /day2-v6 draft: no snapshot or renewal test, an opportunity on its Sales Plan, the rows merged and nothing else run.
  const baseline = {
    schemaVersion: "1.11", customerName: "", renewalEconomics: { currentArrUsd: null }, consumptionPlan: { asOf: "", groups: [] },
    pipelineOpportunities: [{ id: "opp-a", key: "006EXAMPLE0000001", name: "Example Corp - AI Units and Robot Expansion", status: "Open", estimatedIarrUsd: 120000 }],
  };
  const document = toDay2(plan, baseline).document;
  const items = gapList({ plan, document });
  assert.deepEqual(items.map((entry) => [entry.why, entry.item]), [
    ["no source", "Consumed to date: Automation Developer"],
    ["no source", "Consumed to date: AI Units"],
  ], "the Snapshot's total, pursuit cards and pipeline demand are v7 surfaces; the plan's pipeline is not used on 1.11");
  assert.deepEqual(gapList({ plan, document: { ...document, schemaVersion: "1.12" } }).filter((entry) => entry.why === BLOCKS).length, 2, "the same rows on 1.12 block the Snapshot");
});

test("a plan with no pipeline section, or no contract, has no opportunities to list", () => {
  const plan = fixturePlan();
  delete plan.pipeline;
  const noPipeline = gapList({ plan, document: documentFor(plan) });
  assert.equal(noPipeline.filter((entry) => ["stale opportunity", "never-bought product", "unsized line"].includes(entry.why)).length, 0);
  assert.ok(whys(noPipeline, BLOCKS).length > 0, "the rest of the list still builds");

  const noContract = fixturePlan();
  delete noContract.contract;
  assert.equal(whys(gapList({ plan: noContract, document: documentFor(noContract) }), "stale opportunity").length, 0);
});

test("a plan the pipeline reader refuses is refused, not skipped", () => {
  const plan = fixturePlan();
  plan.pipeline.opportunities[0].closeDate = "next quarter";
  assert.throws(() => gapList({ plan, document: documentFor(fixturePlan()) }), /closeDate/);
});

test("the inventory must be the array gap-inventory prints", () => {
  assert.throws(() => gapList({ plan: barePlan(), document: {}, inventory: { rows: [] } }), GapListError);
  assert.throws(() => gapList({ plan: barePlan(), document: {}, inventory: [{ pointer: "/x" }] }), GapListError);
});

test("toMarkdown starts with the table header, one row per item, and keeps a pipe inside its cell", () => {
  const items = [
    { item: 'renewalTest row "Consumables|AI Units": kept 5', why: "conflict", ownerRole: "AE", nextStep: "Confirm which value stands.\nThen update the other." },
    { item: "Snapshot: status", why: "team only", ownerRole: "CSM", nextStep: "State it." },
  ];
  const lines = toMarkdown(items).split("\n");
  assert.equal(lines[0], "| Missing | Why | Owner | Next step |");
  assert.match(lines[1], /^\| ?-+ ?\| ?-+ ?\| ?-+ ?\| ?-+ ?\|$/);
  assert.equal(lines.filter((line) => line.startsWith("| ")).length, 4);
  assert.match(lines[2], /Consumables\\\|AI Units/);
  assert.match(lines[2], /Confirm which value stands\. Then update the other\./);
  assert.equal(toMarkdown(items).endsWith("\n"), true);
  assert.equal(toMarkdown([]).split("\n")[0], "| Missing | Why | Owner | Next step |");
});

// --- The CLI, fed by the real gap-inventory.mjs ------------------------------------------------------------------

const f = (type, writePolicy, extra = {}) => ({ type, requirement: "optional", writePolicy, uiVisibility: "editable", ...extra });
/** The few descriptors these fields need, standing in for the app's field contract. */
const instructions = {
  targetSchemaVersion: "1.12",
  fields: {
    "/consumptionPlan/groups/*/rows/*/actualConsumed": f("number", "evidence_required"),
    "/snapshot/otherPipelineActivityUsd": f("number", "evidence_required"),
    "/renewalTest/healthyAtPercent": f("number", "human_only"),
    "/pipelineOpportunities": f("array", "evidence_required"),
    "/pipelineOpportunities/*/owner": f("string", "human_only", { requirement: "block" }),
    "/health/overall/status": f("string", "human_only"),
  },
};

function write(name, value) {
  const path = join(dir, name);
  writeFileSync(path, typeof value === "string" ? value : `${JSON.stringify(value, null, 2)}\n`);
  return path;
}

test("gap-list.mjs turns gap-inventory's output, the plan and the conflicts into gaps.json and a Markdown table", () => {
  const plan = fixturePlan();
  const baseline = {
    schemaVersion: "1.12",
    snapshot: { otherPipelineActivityUsd: null },
    renewalTest: { healthyAtPercent: null },
    health: { overall: { status: "" } },
    pipelineOpportunities: [{ key: "006EXAMPLE0000001", name: "Example Corp - AI Units and Robot Expansion", owner: "" }],
  };
  const document = toDay2(plan, baseline).document;
  const planPath = write("plan.json", plan);
  const documentPath = write("document.json", document);

  const inventory = spawnSync(process.execPath, [gapInventoryScript, documentPath, "--instructions", write("instructions.json", instructions), "--json"], { encoding: "utf8" });
  assert.equal(inventory.status, 0, inventory.stderr);
  const inventoryPath = write("inventory.json", inventory.stdout);
  const conflictsPath = write("conflicts.json", { conflicts: ['pipelineOpportunities "Example Corp - AI Units Phase 2" stage: kept "Negotiation", which this plan did not write; Salesforce opportunities now give "Proposal".'] });
  const out = join(dir, "gaps.json");
  const markdown = join(dir, "gaps.md");

  const result = spawnSync(process.execPath, [gapListScript, planPath, "--document", documentPath, "--inventory", inventoryPath, "--conflicts", conflictsPath, "--out", out, "--markdown", markdown], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const { gaps } = JSON.parse(readFileSync(out, "utf8"));
  assert.ok(gaps.length > 0);
  assert.ok(gaps.every((entry) => ["item", "why", "ownerRole", "nextStep"].every((key) => typeof entry[key] === "string" && entry[key])));

  const owner = (text, why) => gaps.filter((entry) => entry.item.includes(text) && (!why || entry.why === why)).map((entry) => entry.ownerRole);
  assert.deepEqual(owner("Opportunity owner", "team only"), ["AE"], "the opportunity's empty owner");
  assert.deepEqual(owner("Automation Developer", BLOCKS), ["CSM"], "one item for the consumed figure, though the inventory lists it too");
  assert.deepEqual(owner("Automation Developer", "no source"), []);
  assert.deepEqual(owner("Legacy Robot Upsell"), ["AE"]);
  assert.deepEqual(owner("kept \"Negotiation\""), ["AE"]);
  assert.deepEqual(owner("Healthy threshold"), ["AE + CSM + TAM"]);
  assert.deepEqual(owner("Example Corp - AI Units and Robot Expansion", "blocks Known pipeline demand"), ["AE"], "the shown opportunity has no pursuit card to price");
  assert.equal(gaps.filter((entry) => /overall/i.test(entry.item)).length, 0, "a field no tab reads is not listed");
  assert.equal(gaps.findIndex((entry) => entry.why === BLOCKS) >= 0, true);
  assert.ok(gaps.findIndex((entry) => entry.why === BLOCKS) < gaps.findIndex((entry) => entry.why === "stale opportunity"), "blocking first");

  const table = readFileSync(markdown, "utf8");
  assert.equal(table.split("\n")[0], "| Missing | Why | Owner | Next step |");
  assert.equal(table.split("\n").filter((line) => line.startsWith("| ")).length, gaps.length + 2);
  assert.match(result.stdout, new RegExp(`${gaps.length} gap`));
});

test("gap-list.mjs accepts the conflicts of both pipeline stages, and says what it needs when called wrongly", () => {
  const plan = write("plan-bare.json", barePlan());
  const document = write("document-bare.json", {});
  const inventory = write("inventory-bare.json", []);
  const stage = (name, line) => write(name, { conflicts: [line] });
  const out = join(dir, "both.json");
  const result = spawnSync(process.execPath, [gapListScript, plan, "--document", document, "--inventory", inventory, "--conflicts", stage("c1.json", "first conflict"), "--conflicts", stage("c2.json", "second conflict"), "--out", out], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(readFileSync(out, "utf8")).gaps.map((entry) => entry.item), ["first conflict", "second conflict"]);

  const usage = spawnSync(process.execPath, [gapListScript, plan, "--document", document], { encoding: "utf8" });
  assert.equal(usage.status, 2);
  assert.match(usage.stderr, /usage: gap-list\.mjs/);

  const refused = spawnSync(process.execPath, [gapListScript, plan, "--document", document, "--inventory", write("inventory-object.json", { rows: [] }), "--out", out], { encoding: "utf8" });
  assert.equal(refused.status, 1);
  assert.match(refused.stderr, /^gap-list: /);
});

// --- A plan grouped by contract: the row's kind says what it is ---------------------------------------

const CONTRACT_ONE = "Example Corp · contract 00000001";
const CONTRACT_TWO = "Example Corp Sub · contract 00000002";

/** The fixture as a customer on two contracts has it: each row's category is its contract's label, its kind the category it had. */
function groupedPlan() {
  const plan = fixturePlan();
  for (const row of plan.rows) {
    const kind = row.category;
    row.category = kind === "Users" || kind === "Robots" ? CONTRACT_ONE : CONTRACT_TWO;
    row.kind = kind;
  }
  return plan;
}
const consumedAt = (group, row) => `/consumptionPlan/groups/${group}/rows/${row}/actualConsumed`;

test("a plan grouped by contract with kinds gets the gap list the ungrouped fixture gets", () => {
  const grouped = groupedPlan();
  const document = documentFor(grouped);
  assert.deepEqual(document.consumptionPlan.groups.map((group) => group.element), [CONTRACT_ONE, CONTRACT_TWO], "one Day 2 group per contract");
  document.consumptionPlan.groups.forEach((group, at) => assert.ok(group.rows.length > 0, `group ${at}`));
  assert.deepEqual(gapList({ plan: grouped, document }), gapList({ plan: fixturePlan(), document: documentFor(fixturePlan()) }));
});

test("in a grouped plan, an unmeasured Users-kind row goes to the CSM for seats assigned, and the other kinds to the TAM", () => {
  const plan = groupedPlan();
  const items = gapList({ plan, document: documentFor(plan) });
  const owner = (name) => mentioning(whys(items, BLOCKS), name).map((entry) => entry.ownerRole);
  assert.deepEqual(owner("Automation Developer"), ["CSM"]);
  assert.deepEqual(owner("AI Units"), ["TAM"]);
  assert.match(mentioning(whys(items, BLOCKS), "Automation Developer")[0].nextStep, /seats assigned to named users/);
  assert.match(mentioning(whys(items, BLOCKS), "AI Units")[0].nextStep, /consumed-to-date figure from the entitlement record/);

  const withoutKinds = groupedPlan();
  for (const row of withoutKinds.rows) delete row.kind;
  const fallback = whys(gapList({ plan: withoutKinds, document: documentFor(withoutKinds) }), BLOCKS);
  assert.deepEqual(mentioning(fallback, "Automation Developer").map((entry) => entry.ownerRole), ["TAM"], "with no kind the contract label decides, and says nothing");
});

test("in a grouped plan, a platform-kind row gets the platform evidence wording", () => {
  const plan = groupedPlan();
  const document = documentFor(plan);
  docRow(document, "Platform - Standard").soldArrUsd = 5000;
  const [platform, ...rest] = mentioning(whys(gapList({ plan, document }), BLOCKS), "Platform - Standard");
  assert.equal(rest.length, 0, "one item for the tier");
  assert.equal(platform.ownerRole, "TAM");
  assert.match(platform.nextStep, /^Bring a dated statement or telemetry showing the platform in production use \(a tier is used whole, so Consumed is its purchased quantity\)\./);
  assert.doesNotMatch(platform.nextStep, /consumed-to-date figure from a dated source/, "not the generic step");
});

test("in a grouped plan, a platform-kind row is not a consumed figure the plan or the inventory asks for", () => {
  const plan = groupedPlan();
  const document = documentFor(plan);
  const platformGroup = document.consumptionPlan.groups.findIndex((group) => group.rows.some((row) => row.offering === "Platform - Standard"));
  const platformRow = document.consumptionPlan.groups[platformGroup].rows.findIndex((row) => row.offering === "Platform - Standard");
  const inventory = [inventoryRow("/consumptionPlan/groups/*/rows/*/actualConsumed", {
    tab: "Renewal Test", pointer: consumedAt(platformGroup, platformRow), who: "evidence", label: "Platform - Standard",
  })];
  const items = gapList({ plan, document, inventory });
  assert.equal(mentioning(items, "Platform - Standard").length, 0, "a tier is granted, not consumed");
  const v6 = { ...document, schemaVersion: "1.11" };
  assert.equal(mentioning(gapList({ plan, document: v6, inventory }), "Platform - Standard").length, 0, "nor on a schema 1.11 draft");
});

test("in a grouped plan, a user row's missing figure goes to the CSM on a schema 1.11 draft, and by the inventory too", () => {
  const plan = groupedPlan();
  const document = { ...documentFor(plan), schemaVersion: "1.11" };
  const items = gapList({ plan, document });
  assert.deepEqual(mentioning(items, "Consumed to date: Automation Developer").map((entry) => [entry.why, entry.ownerRole]), [["no source", "CSM"]]);
  assert.deepEqual(mentioning(items, "Consumed to date: AI Units").map((entry) => entry.ownerRole), ["TAM"]);

  // The plan holds a statement the document lacks and the row is $0, so only the inventory names the blank.
  const stated = groupedPlan();
  Object.assign(planRow(stated, "Automation Developer"), { consumedQuantity: 12, consumedBasis: "statement", consumedAsOf: "2026-07-31" });
  const blank = documentFor(stated);
  Object.assign(docRow(blank, "Automation Developer"), { actualConsumed: null, soldArrUsd: 0 });
  const inventory = [inventoryRow("/consumptionPlan/groups/*/rows/*/actualConsumed", {
    tab: "Renewal Test", pointer: consumedAt(0, 0), who: "evidence", label: "Automation Developer",
  })];
  const listed = mentioning(gapList({ plan: stated, document: blank, inventory }), "Consumed to date: Automation Developer");
  assert.deepEqual(listed.map((entry) => entry.ownerRole), ["CSM"]);
  assert.match(listed[0].nextStep, /seats assigned/i);
});

test("a kind that is not one of the four product kinds is refused", () => {
  const plan = groupedPlan();
  const document = documentFor(plan);
  planRow(plan, "Platform - Standard").kind = "Platform";
  assert.throws(() => gapList({ plan, document }), (error) => error instanceof PlanError && /rows\[3\]\.kind must be/.test(error.message));
});

// --- A coverage gap is listed whatever the document holds -----------------------------------------------

/** The fixture with its robot row stated as a coverage gap (no figure), and telemetry saying nothing about coverage. */
function gapRobotPlan() {
  const plan = fixturePlan();
  Object.assign(planRow(plan, "Unattended Robot"), { consumedQuantity: null, consumedBasis: "coverage-gap", notes: "Illustrative: this deployment is outside the telemetry layer." });
  return plan;
}

test("a coverage-gap row whose document still holds a 0 is listed as partial coverage, with the usual consumed next step", () => {
  const plan = gapRobotPlan();
  const document = documentFor(plan);
  docRow(document, "Unattended Robot").actualConsumed = 0; // the baseline's measured zero, which to-day2.mjs would have cleared
  const items = gapList({ plan, document }).filter((entry) => entry.item.includes("Unattended Robot"));
  assert.equal(items.length, 1, JSON.stringify(items));
  assert.equal(items[0].why, "partial coverage");
  assert.equal(items[0].item, "Consumed to date: Unattended Robot");
  assert.equal(items[0].ownerRole, "TAM");
  assert.match(items[0].nextStep, /^Bring the allocation figure/);
  assert.match(items[0].nextStep, /not a measured zero/, "it says a 0 there is not a measurement");
});

test("a coverage-gap row the merge cleared blocks the Snapshot's Consumed as partial coverage, even when telemetry.coverage says nothing", () => {
  const plan = gapRobotPlan();
  assert.equal(plan.telemetry, undefined);
  const document = documentFor(plan);
  const [item, ...rest] = mentioning(whys(gapList({ plan, document }), BLOCKS), "Unattended Robot");
  assert.equal(rest.length, 0, "one item for the row");
  assert.equal(item.item, "Consumed to date: Unattended Robot (partial coverage)");
  assert.equal(item.ownerRole, "TAM");
  assert.match(item.nextStep, /allocation figure/i);
  const withNote = { ...plan, telemetry: { asOf: "2026-07-31", coverage: "partial", note: "Illustrative: the Public Sector deployment is not captured." } };
  assert.match(mentioning(whys(gapList({ plan: withNote, document }), BLOCKS), "Unattended Robot")[0].nextStep, /the Public Sector deployment is not captured/, "the plan's coverage note travels with it");
});

test("a coverage-gap row on a $0 contract is listed too, and a platform tier never is", () => {
  const plan = gapRobotPlan();
  planRow(plan, "Unattended Robot").arrUsd = 0;
  const document = documentFor(plan);
  docRow(document, "Unattended Robot").actualConsumed = 0;
  const robots = mentioning(gapList({ plan, document }), "Unattended Robot");
  assert.deepEqual(robots.map((entry) => entry.why), ["partial coverage"]);

  const tier = fixturePlan();
  Object.assign(planRow(tier, "Platform - Standard"), { consumedQuantity: null, consumedBasis: "coverage-gap" });
  assert.equal(mentioning(gapList({ plan: tier, document: documentFor(tier) }), "Platform - Standard").length, 0, "a tier is granted, not consumed");
});

test("a coverage gap with a consumed quantity is refused by the gap list as by the merge", () => {
  const plan = gapRobotPlan();
  planRow(plan, "Unattended Robot").consumedQuantity = 0;
  assert.throws(() => gapList({ plan, document: documentFor(fixturePlan()) }), (error) => error instanceof PlanError && /rows\[1\]\.consumedQuantity/.test(error.message));
});

// --- Gap-list noise: what no v7 tab draws, and what the document already answers -----------------------------

test("every subfield of a primary use case, and a row's forecast consumption and renewal ARR, are left out as undrawn, unless one blocks publication", () => {
  const undrawn = [
    "/consumptionPlan/primaryUseCases/*/category",
    "/consumptionPlan/primaryUseCases/*/useCases",
    "/consumptionPlan/primaryUseCases/*/arrConsumedUsd",
    "/consumptionPlan/primaryUseCases/*/customerValue",
    "/consumptionPlan/primaryUseCases/*/allocations",
    "/consumptionPlan/primaryUseCases/*/allocations/*/currentUnits",
    "/consumptionPlan/primaryUseCases/*/allocations/*/forecastUnits/q1",
    "/consumptionPlan/groups/*/rows/*/forecastConsumption",
    "/consumptionPlan/groups/*/rows/*/renewalArrUsd",
  ];
  const asRead = (generic, extra = {}) => inventoryRow(generic, { tab: "Renewal Test", who: "evidence", label: "Seat Pack", ...extra });
  const document = { consumptionPlan: { groups: [{ element: "Users", rows: [{ offering: "Seat Pack", soldArrUsd: 0, actualConsumed: 3 }] }] } };

  assert.deepEqual(gapList({ plan: barePlan(), document, inventory: undrawn.map((generic) => asRead(generic)) }), []);
  const blocking = gapList({ plan: barePlan(), document, inventory: undrawn.map((generic) => asRead(generic, { blocks: true })) });
  assert.equal(blocking.length, undrawn.length, "a field that blocks publication is listed whatever tab reads it");
  assert.ok(blocking.every((entry) => entry.item.includes("(required to publish)")));

  const lookalikes = ["/consumptionPlan/primaryUseCasesExtra", "/consumptionPlan/groups/*/rows/*/renewalArrUsdNote", "/consumptionPlan/groups/*/rows/*/soldQuantity"];
  assert.equal(gapList({ plan: barePlan(), document, inventory: lookalikes.map((generic) => asRead(generic)) }).length, lookalikes.length, "a prefix ends at a path segment: a field the Renewal Test does draw stays");
});

test("the program clock's months are not a gap when the contract dates place the clock", () => {
  const clock = ["/programClock/monthsElapsed", "/programClock/totalMonths"].map((generic) => inventoryRow(generic, { tab: "Snapshot", who: "evidence", label: "" }));
  const listed = (document, inventory = clock) => gapList({ plan: barePlan(), document, inventory }).map((entry) => entry.item);
  const dated = { renewalDate: "2027-05-31", snapshot: { contractStartDate: "2025-12-01" } };

  assert.deepEqual(listed(dated), [], "both dates place the clock");
  assert.equal(listed({}).length, 2, "no dates: the clock's months are a gap");
  assert.equal(listed({ renewalDate: "2027-05-31", snapshot: { contractStartDate: "" } }).length, 2, "no contract start");
  assert.equal(listed({ snapshot: { contractStartDate: "2025-12-01" } }).length, 2, "no renewal date");
  assert.equal(listed({ renewalDate: "  ", snapshot: { contractStartDate: "2025-12-01" } }).length, 2, "a blank renewal date places nothing");
  assert.equal(listed({ renewalDate: null, snapshot: { contractStartDate: null } }).length, 2);

  const other = [inventoryRow("/snapshot/status", { tab: "Snapshot", who: "attest" }), ...clock];
  assert.deepEqual(listed(dated, other), ["Snapshot: Bottom line health"], "only the clock's months go");
  const blocking = clock.map((entry) => ({ ...entry, blocks: true }));
  assert.equal(listed(dated, blocking).length, 2, "a field that blocks publication is listed whatever the dates say");
});

test("a Renewal Test row whose demand is stated as 0 and 0 needs no pipeline driver: the app renders it as Not adopted", () => {
  const rows = [
    { rowId: "row-0", pipelineDriver: "", demand6MoUnits: 0, demand12MoUnits: 0 }, // stated as nothing: Not adopted
    { rowId: "row-1", pipelineDriver: "", demand6MoUnits: null, demand12MoUnits: null }, // nothing stated yet
    { rowId: "row-2", pipelineDriver: "", demand6MoUnits: 0, demand12MoUnits: 40 }, // demand with nothing to name it
    { rowId: "row-3", pipelineDriver: "", demand6MoUnits: 0, demand12MoUnits: null },
    { rowId: "row-4", pipelineDriver: "", demand6MoUnits: 0, demand12MoUnits: 0 }, // also Not adopted
  ];
  const document = { renewalTest: { rows } };
  const driverGap = (at, generic = "/renewalTest/rows/*/pipelineDriver") => inventoryRow(generic, {
    tab: "Renewal Test", pointer: `/renewalTest/rows/${at}/${generic.split("/").at(-1)}`, who: "evidence", policy: "evidence_required", label: `row-${at}`,
  });
  const inventory = [0, 1, 2, 3, 4].map((at) => driverGap(at));

  const [item, ...rest] = gapList({ plan: barePlan(), document, inventory });
  assert.equal(rest.length, 0, "one item for the field");
  assert.equal(item.item, "Renewal Test: Pipeline driver [row-1; row-2; row-3]", "the 0 and 0 rows are not named");
  assert.equal(item.ownerRole, "AE");

  assert.deepEqual(gapList({ plan: barePlan(), document, inventory: [driverGap(0), driverGap(4)] }), [], "with every row Not adopted the item goes");

  const demand = [driverGap(0, "/renewalTest/rows/*/demand6MoUnits"), driverGap(0, "/renewalTest/rows/*/confidence")];
  assert.equal(gapList({ plan: barePlan(), document, inventory: demand }).length, 2, "only the driver is waived: a Not adopted row's other fields stay");
  assert.equal(gapList({ plan: barePlan(), document: {}, inventory: [driverGap(0)] }).length, 1, "a document with no such row waives nothing");
  const blocking = [{ ...driverGap(0), blocks: true }];
  assert.equal(gapList({ plan: barePlan(), document, inventory: blocking }).length, 1, "a field that blocks publication is listed");
});

test("the customer-value item asks for a validated statement of value to the customer, never the Salesforce record", () => {
  const generic = "/pipelineOpportunities/*/customerValueUsd";
  const rule = OWNER_ROLES[generic];
  assert.equal(rule.ownerRole, "AE");
  assert.match(rule.nextStep, /from a validated statement of value to the customer/);
  assert.doesNotMatch(rule.nextStep, /Salesforce record/, "customerValueUsd comes only from a validated statement");
  assert.match(rule.nextStep, /confirm it with the opportunity owner/);

  const inventory = [inventoryRow(generic, { tab: "Snapshot", who: "evidence", label: "Example Corp - AI Units Phase 2" })];
  const [item] = gapList({ plan: barePlan(), document: {}, inventory });
  assert.equal(item.item, "Snapshot: Opportunity customer value [Example Corp - AI Units Phase 2]");
  assert.equal(item.nextStep, rule.nextStep);
  assert.match(item.nextStep, /from a validated statement of value to the customer/);
  assert.doesNotMatch(item.nextStep, /Salesforce record/);

  const sibling = OWNER_ROLES["/pipelineOpportunities/*/blocker"];
  assert.match(sibling.nextStep, /opportunity's Salesforce record/, "the other opportunity fields keep their step");
});

// --- A product two rows share is named with its category -------------------------------------------------

const contractRow = (category, product, kind, extra = {}) => ({
  category, kind, product, productCode: "", unit: "units", licensingModel: "capped", arrUsd: 40000, discountPercent: 20,
  purchasedQuantity: 1000000, consumedQuantity: null, forecastUnits: { q1: null, q2: null, q3: null, q4: null }, notes: "", ...extra,
});
/** Two contracts that each carry an AI Units row, and one Unattended Robot row that only the first carries. */
function sharedProductPlan() {
  const plan = barePlan();
  plan.rows = [
    contractRow("Contract A", "AI Units", "Consumables"),
    contractRow("Contract B", "AI Units", "Consumables"),
    contractRow("Contract A", "Unattended Robot", "Robots", { unit: "robots", purchasedQuantity: 100 }),
  ];
  return plan;
}

test("a product two plan rows share is named '<category> · <product>' in the item for each; a product only one row carries keeps its name", () => {
  const plan = sharedProductPlan();
  const items = gapList({ plan, document: documentFor(plan) });
  assert.deepEqual(whys(items, BLOCKS).map((entry) => entry.item), [
    "Consumed to date: Contract A · AI Units (no source)",
    "Consumed to date: Unattended Robot (no source)",
    "Consumed to date: Contract B · AI Units (no source)",
  ], "in the document's order: Contract A's rows, then Contract B's");
});

test("every item that names a consumption row by product uses the category when the product is shared", () => {
  const plan = sharedProductPlan();
  // Contract A's row is an estimate, Contract B's is measured but has lost its price, and the robots are on a $0 row.
  Object.assign(plan.rows[0], { consumedQuantity: 5000, consumedBasis: "estimate", notes: "Illustrative: 5000 units drawn per the Q2 statement." });
  Object.assign(plan.rows[1], { consumedQuantity: 7, consumedBasis: "statement" });
  plan.rows[2].arrUsd = 0;
  const document = documentFor(plan);
  document.consumptionPlan.groups[1].rows[0].soldQuantity = null;
  const items = gapList({ plan, document }).map((entry) => entry.item);
  assert.deepEqual(items.sort(), [
    "Consumed to date (estimate): Contract A · AI Units",
    "Consumed to date: Unattended Robot",
    "Contracted price: Contract B · AI Units",
  ].sort());
});

test("a shared product named by the document alone is told apart by its group: the inventory's consumed figures and record labels", () => {
  const document = {
    consumptionPlan: { groups: [
      { element: "Contract A", rows: [{ offering: "Seat Pack", soldArrUsd: 0, actualConsumed: null }, { offering: "Bot Pack", soldArrUsd: 0, actualConsumed: null }] },
      { element: "Contract B", rows: [{ offering: "seat pack", soldArrUsd: 0, actualConsumed: null }] },
    ] },
  };
  const consumed = [[0, 0, "Seat Pack"], [0, 1, "Bot Pack"], [1, 0, "seat pack"]].map(([group, row, label]) => inventoryRow("/consumptionPlan/groups/*/rows/*/actualConsumed", {
    tab: "Renewal Test", pointer: `/consumptionPlan/groups/${group}/rows/${row}/actualConsumed`, who: "evidence", label,
  }));
  const note = [[0, 0, "Seat Pack"], [1, 0, "seat pack"]].map(([group, row, label]) => inventoryRow("/consumptionPlan/groups/*/rows/*/entitlementNote", {
    tab: "Renewal Test", pointer: `/consumptionPlan/groups/${group}/rows/${row}/entitlementNote`, who: "evidence", label,
  }));
  const items = gapList({ plan: barePlan(), document, inventory: [...consumed, ...note] }).map((entry) => entry.item);
  assert.deepEqual(items.filter((item) => item.startsWith("Consumed to date")), [
    "Consumed to date: Contract A · Seat Pack",
    "Consumed to date: Bot Pack",
    "Consumed to date: Contract B · seat pack",
  ]);
  assert.deepEqual(items.filter((item) => item.includes("entitlement note")), ["Renewal Test: Consumption plan entitlement note [Contract A · Seat Pack; Contract B · seat pack]"]);
});

test("a shared product on rows with no category to name them by keeps its plain name", () => {
  const plan = barePlan();
  plan.rows = [contractRow("", "AI Units", "Consumables"), contractRow("", "AI Units", "Consumables", { productCode: "SKU-2" })];
  const names = gapList({ plan, document: documentFor(plan) }).filter((entry) => entry.why === BLOCKS).map((entry) => entry.item);
  assert.ok(names.length > 0 && names.every((item) => !item.includes("·")), JSON.stringify(names));
});

// --- Pursuits that draw more of a row than its 12-month demand ---------------------------------------------

const OVERDRAWN = "overdrawn";
/** withPursuits' document with renewal-test rows: robots (row-1) at a 12-month demand of 5, AI Units (row-2) at 1400000. */
function overdrawnDocument(pursuits, { opportunities = [opp(1), opp(2)], topPursuitIds = [], rows = [{ rowId: "row-1", demand12MoUnits: 5 }, { rowId: "row-2", demand12MoUnits: 1400000 }] } = {}) {
  const documents = withPursuits(opportunities, pursuits, topPursuitIds);
  documents.document.renewalTest = { rows: rows.map((row) => ({ pipelineDriver: "", demand6MoUnits: null, confidence: "", ...row })) };
  return documents;
}
const overdrawn = (documents) => whys(gapList(documents), OVERDRAWN);
const draws = (id, ...lines) => ({ opportunityId: id, draw: lines.map(([rowId, units]) => ({ rowId, units })) });
/** A use case's record, as `opp` makes one, keyed to a use case of the plan's (`withUseCases`). */
const useCaseOpp = (n, extra = {}) => opp(n, { key: `use-case-${n}`, ...extra });
/** The documents, their plan given a use case for each `use-case-*` record, so the gap list words their items as a use case's. */
function withUseCases(documents) {
  documents.plan.pipeline.useCases = documents.document.pipelineOpportunities
    .filter(({ key }) => key.startsWith("use-case-"))
    .map(({ key, name }) => ({ key, name, source: "Team expansion workbook (2026-07-28)", asOf: "2026-07-28", lines: [] }));
  return documents;
}

test("a row the shown use cases draw more of than its 12-month demand is an item for the AE naming the row and the pursuits, as the app footnotes it", () => {
  const documents = withUseCases(overdrawnDocument([draws("opp-2", ["row-1", 20], ["row-2", 400000]), draws("opp-1", ["row-1", 4])], { opportunities: [useCaseOpp(1), useCaseOpp(2)] }));
  const items = gapList(documents);
  const [item, ...rest] = whys(items, OVERDRAWN);
  assert.equal(rest.length, 0, "AI Units' 400000 is within its demand");
  assert.equal(item.item, 'Top pursuits draw 24 Unattended Robot, more than its 5 12-month demand ("Pursuit 2" 20; "Pursuit 1" 4)');
  assert.equal(item.ownerRole, "AE");
  assert.equal(item.nextStep, "Reconcile the team forecast with these use cases' sizing, or date the use case: a pursuit card's draws are part of the row's 12-month demand, so they cannot exceed it. Correct the plan file (the row's forecastUnits, the use case's lines or its startDate) and rerun the numbers stage, or change the draws or the demand in the app; until then the Renewal Test footnotes the row.");
  assert.ok(items.indexOf(item) > items.findIndex((entry) => entry.why === BLOCKS), "it does not block publication");

  const [one] = overdrawn(withUseCases(overdrawnDocument([draws("opp-1", ["row-1", 6])], { opportunities: [useCaseOpp(1), useCaseOpp(2)] })));
  assert.equal(one.item, 'Top pursuits draw 6 Unattended Robot, more than its 5 12-month demand ("Pursuit 1" 6)');
  assert.match(one.nextStep, /^Reconcile the team forecast with this use case's sizing, or date the use case/);
});

test("an opportunity card's draw that overdraws a row is still counted, as the app counts it, and the AE is asked to remove it", () => {
  const [only] = overdrawn(overdrawnDocument([draws("opp-1", ["row-1", 6])]));
  assert.equal(only.item, 'Top pursuits draw 6 Unattended Robot, more than its 5 12-month demand ("Pursuit 1" 6)');
  assert.equal(only.nextStep, 'Remove the draws on the "Pursuit 1" card in the app: an opportunity adds its own entitlement and draws nothing from today\'s rows. Until then the Renewal Test footnotes the row.');

  const [both] = overdrawn(withUseCases(overdrawnDocument([draws("opp-1", ["row-1", 4]), draws("opp-2", ["row-1", 3])], { opportunities: [opp(1), useCaseOpp(2)] })));
  assert.equal(both.item, 'Top pursuits draw 7 Unattended Robot, more than its 5 12-month demand ("Pursuit 2" 3; "Pursuit 1" 4)');
  assert.match(both.nextStep, /^Remove the draws on the "Pursuit 1" card in the app: an opportunity adds its own entitlement and draws nothing from today's rows\. Reconcile the team forecast with this use case's sizing, or date the use case:/);
  assert.match(both.nextStep, /until then the Renewal Test footnotes the row\.$/);
});

test("only what the app counts makes a row overdrawn: the shown pursuits' sized, chosen draws against a stated 12-month demand", () => {
  const none = (label, documents) => assert.deepEqual(overdrawn(documents), [], label);
  none("drawing exactly the demand", overdrawnDocument([draws("opp-1", ["row-1", 5])]));
  none("an unsized draw counts nothing", overdrawnDocument([draws("opp-1", ["row-1", null], ["row-1", 4])]));
  none("a draw line with no row chosen is no draw", overdrawnDocument([draws("opp-1", ["", 50], ["row-1", 5])]));
  none("a row with no renewal-test entry has no demand to exceed", overdrawnDocument([draws("opp-1", ["row-0", 50])]));
  none("an unknown demand cannot be exceeded", overdrawnDocument([draws("opp-1", ["row-1", 50])], { rows: [{ rowId: "row-1", demand12MoUnits: null }] }));
  const ranked = [opp(1), opp(2), opp(3), opp(4)];
  none("a pursuit off the cards is not counted", overdrawnDocument([draws("opp-1", ["row-1", 50])], { opportunities: ranked }));
  assert.equal(overdrawn(overdrawnDocument([draws("opp-1", ["row-1", 50])], { opportunities: ranked, topPursuitIds: ["opp-1"] })).length, 1, "unless the team names it");
  assert.equal(overdrawn(overdrawnDocument([draws("opp-1", ["row-1", 1])], { rows: [{ rowId: "row-1", demand12MoUnits: 0 }] })).length, 1, "a stated 0 is a demand");
  const v6 = overdrawnDocument([draws("opp-1", ["row-1", 50])]);
  v6.document.schemaVersion = "1.11";
  none("a schema 1.11 draft has no Snapshot cards", v6);
});

test("a use case whose start date is before the plan's asOf is a CSM item to confirm it is live, since its use is then already in Consumed", () => {
  const withUseCase = (startDate) => {
    const plan = fixturePlan();
    plan.pipeline.useCases = [{ key: "invoice-intake-agent", name: "Invoice intake agent", source: "Team expansion workbook (2026-07-28)", asOf: "2026-07-28", startDate, lines: [{ product: "AI Units", units: 5, row: "AI Units" }] }];
    return gapList({ plan, document: documentFor(plan) });
  };
  const [item, ...rest] = whys(withUseCase("2026-07-01"), "already started");
  assert.equal(rest.length, 0);
  assert.equal(item.item, 'Use case "Invoice intake agent" (invoice-intake-agent): started 2026-07-01, before this plan\'s 2026-08-01');
  assert.equal(item.ownerRole, "CSM");
  assert.match(item.nextStep, /^Confirm with the account team that it is live\./);
  assert.match(item.nextStep, /already in Consumed to date/);
  assert.match(item.nextStep, /remove it from the plan's use cases/);
  for (const startDate of ["", "2026-08-01", "2027-12-01"]) assert.deepEqual(whys(withUseCase(startDate), "already started"), [], `starting ${startDate || "on no date"}`);
});

test("a shown use-case card starting more than 12 months out has no draw: the AE re-dates the use case or chooses other pursuits", () => {
  const { plan, document } = withPursuits([opp(1, { key: "Invoice Intake Agent", name: "Invoice intake agent" })]);
  plan.pipeline.useCases = [{ key: "invoice-intake-agent", name: "Invoice intake agent", source: "Team expansion workbook (2026-07-28)", asOf: "2026-07-28", startDate: "2027-12-01", lines: [{ product: "AI Units", units: 5, row: "AI Units" }] }];
  const [demand, ...rest] = withheld({ plan, document });
  assert.equal(rest.length, 0);
  assert.equal(demand.item, 'Pursuit card "Invoice intake agent": Est. rev. is withheld (it starts 2027-12-01, more than 12 months after 2026-08-01, so this plan gives it no draw)', "found by its key as the app compares keys");
  assert.match(demand.nextStep, /^Re-date the use case in the plan file if it starts sooner and rerun the numbers stage, or choose other top pursuits in the app, then rerun Step 9\.5 on the exported draft;/);
});

test("the line for a use case that now starts beyond 12 months gets a use-case next step", () => {
  const line = 'Use case "Invoice intake agent" (invoice-intake-agent) now starts 2027-12-01, more than 12 months after 2026-08-01, so this plan draws nothing for it; the draws it wrote earlier remain on its pursuit card. The AE re-dates it in the plan file or removes the draws in the app.';
  const [item] = gapList({ plan: barePlan(), document: {}, conflicts: [line] });
  assert.match(item.nextStep, /^Re-date the use case in the plan file if it starts sooner; otherwise remove its draws in the app/);
  assert.doesNotMatch(item.nextStep, /Salesforce/);
});

// --- Use cases are not Salesforce opportunities ------------------------------------------------------------

/** A team-sized use case for the fixture's plan. */
const intakeUseCase = (changes = {}) => ({
  key: "invoice-intake-agent", name: "Invoice intake agent", source: "Team expansion workbook (2026-07-28)", asOf: "2026-07-28",
  lines: [{ product: "AI Units", units: 5, row: "AI Units" }], ...changes,
});
const TRACKER = /from the team's own tracker; this pursuit has no Salesforce record/;

test("a use-case record's blank stage, and every other field whose step reads from Salesforce, is asked of the team's own tracker", () => {
  const plan = fixturePlan();
  plan.pipeline.useCases = [intakeUseCase()];
  const document = documentFor(plan);
  document.pipelineOpportunities = [
    { id: "opp-1", key: "006EXAMPLE0000002", name: "Example Corp - AI Units Phase 2", stage: "" },
    { id: "opp-2", key: "Invoice Intake Agent", name: "Invoice intake agent", stage: "" }, // the team's spelling of the use case's key
  ];
  const row = (field, at, label, extra = {}) => inventoryRow(`/pipelineOpportunities/*/${field}`, {
    tab: "Snapshot", pointer: `/pipelineOpportunities/${at}/${field}`, who: "evidence", policy: "evidence_required", label, ...extra,
  });
  const inventory = [
    row("stage", 0, "Example Corp - AI Units Phase 2", { blocks: true, requirement: "block" }),
    row("stage", 1, "Invoice intake agent", { blocks: true, requirement: "block" }),
    row("owner", 1, "Invoice intake agent", { who: "human", policy: "human_only" }),
    row("blocker", 1, "Invoice intake agent"),
    row("customerValueUsd", 1, "Invoice intake agent"),
  ];
  const items = gapList({ plan, document, inventory });
  const find = (text) => items.find((entry) => entry.item === text);
  const opportunityStage = find("Snapshot: Opportunity stage [Example Corp - AI Units Phase 2] (required to publish)");
  assert.match(opportunityStage.nextStep, /^Fill it from the opportunity's Salesforce record/);
  const useCaseStage = find("Snapshot: Use case stage [Invoice intake agent] (required to publish)");
  assert.ok(useCaseStage, items.map((entry) => entry.item).join("\n"));
  assert.match(useCaseStage.nextStep, TRACKER);
  assert.doesNotMatch(useCaseStage.nextStep, /Salesforce record,|opportunity's Salesforce/);
  assert.equal(useCaseStage.ownerRole, "AE");
  assert.match(find("Snapshot: Use case owner [Invoice intake agent]").nextStep, TRACKER);
  assert.match(find("Snapshot: Use case blocker [Invoice intake agent]").nextStep, TRACKER);
  assert.equal(find("Snapshot: Use case customer value [Invoice intake agent]").nextStep, OWNER_ROLES["/pipelineOpportunities/*/customerValueUsd"].nextStep, "a step that does not read from Salesforce stands");

  delete plan.pipeline.useCases;
  assert.ok(gapList({ plan, document, inventory }).some((entry) => entry.item === "Snapshot: Opportunity stage [Example Corp - AI Units Phase 2; Invoice intake agent] (required to publish)"), "with no use case in the plan, every record is an opportunity");
});

test("a use case's unsized and never-bought lines are named as the use case's, and the unsized step asks the plan file for the team's sizing", () => {
  const plan = fixturePlan();
  plan.pipeline.useCases = [intakeUseCase({ lines: [{ product: "AI Units", units: null, row: "AI Units" }, { product: "Agent Units", units: 5, row: "" }] })];
  const items = gapList({ plan, document: documentFor(plan) });
  const [unsized] = mentioning(whys(items, "unsized line"), "Invoice intake agent");
  assert.equal(unsized.item, 'Line "AI Units" on use case "Invoice intake agent": no unit volume');
  assert.match(unsized.nextStep, /^State how many units it adds to AI Units in the plan file's use case \(the team's sizing gives none\)/);
  assert.doesNotMatch(unsized.nextStep, /product name does not decode/);
  const [never] = mentioning(whys(items, "never-bought product"), "Invoice intake agent");
  assert.equal(never.item, 'Product "Agent Units" on use case "Invoice intake agent"');
  const [opportunityLine] = mentioning(whys(items, "unsized line"), "AI Units Enterprise Agreement");
  assert.match(opportunityLine.nextStep, /its product name does not decode to a quantity/, "an opportunity's line keeps its step");
});

test("an other pipeline activity of $0 names the use cases off the cards valued at $0 too", () => {
  const plan = fixturePlan();
  plan.pipeline.opportunities = plan.pipeline.opportunities.filter(({ salesforceId }) => !["006EXAMPLE0000003", "006EXAMPLE0000007", "006EXAMPLE0000008"].includes(salesforceId));
  plan.pipeline.useCases = [intakeUseCase({ lines: [{ product: "Platform - Standard", units: 1, row: "Platform - Standard" }] })];
  const records = ["006EXAMPLE0000001", "006EXAMPLE0000002", "006EXAMPLE0000006"].map((key, at) => ({ id: `opp-${at}`, key, name: key, status: "Open", estimatedIarrUsd: 4000 - at * 1000 }));
  const document = { ...documentFor(plan), pipelineOpportunities: [...records, { id: "opp-u", key: "invoice intake agent", name: "Invoice intake agent", status: "Open", estimatedIarrUsd: 0 }], snapshot: { otherPipelineActivityUsd: 0, pursuits: [], topPursuitIds: [] } };
  const [item, ...rest] = gapList({ plan, document }).filter((entry) => /other pipeline activity is \$0/.test(entry.item));
  assert.equal(rest.length, 0);
  assert.equal(item.item, 'Snapshot: other pipeline activity is $0 (use case "Invoice intake agent" valued at $0)');
  assert.match(item.nextStep, /^Confirm that use case "Invoice intake agent" adds no entitlement value beyond the pursuit cards: the team sized it, but its lines draw on no priced row/);
  assert.doesNotMatch(item.nextStep, /Salesforce lists/);

  plan.pipeline.opportunities.push(fixturePlan().pipeline.opportunities.find(({ salesforceId }) => salesforceId === "006EXAMPLE0000008"));
  const [both] = gapList({ plan, document }).filter((entry) => /other pipeline activity is \$0/.test(entry.item));
  assert.equal(both.item, 'Snapshot: other pipeline activity is $0 ("Example Corp - Platform Standard Tier" and use case "Invoice intake agent" valued at $0)');
  assert.match(both.nextStep, /Salesforce lists the opportunity open and the team sized the use case, but their lines draw on no priced row/);
});

test("a kept or cleared value's next step names what now gives the other value: a use case or the team forecast, not Salesforce", () => {
  const lines = [
    'pipelineOpportunities "Invoice intake agent" name: kept "Intake agent", which this plan did not write; the team-sized use case now gives "Invoice intake agent".',
    'renewalTest row "AI Units" demand12MoUnits: kept 999, which this plan did not write; the team forecast (forecastUnits) now gives 450000.',
    'renewalTest row "AI Units" demand12MoUnits: left blank, as the account team cleared it (this plan wrote 5); team-sized use cases now give 9.',
    'renewalTest row "AI Units" pipelineDriver: kept "A (Oct 26); B (May 27)", which this plan did not write; Salesforce opportunities and team-sized use cases now give "C (Nov 26)".',
  ];
  const steps = gapList({ plan: barePlan(), document: {}, conflicts: lines }).map((entry) => entry.nextStep);
  assert.deepEqual(steps, [
    "Confirm which value stands, the account team's or what the team-sized use case now gives, and update the other so they agree.",
    "Confirm which value stands, the account team's or what the team forecast (forecastUnits) now gives, and update the other so they agree.",
    "Confirm the team meant to clear it; if not, enter the value team-sized use cases now give in the app.",
    "Confirm which value stands, the account team's or what Salesforce opportunities and team-sized use cases now give, and update the other so they agree.",
  ]);
});

// --- Robots on trial or unlicensed keys ------------------------------------------------------------------

const UNLICENSED = { count: 27, source: "Illustrative: Orchestrator licence export", asOf: "2026-10-15" };

test("robots a row states run on trial or unlicensed keys are a TAM item: settle their licensing before they lapse or are counted", () => {
  const plan = fixturePlan();
  planRow(plan, "Unattended Robot").unlicensedInUse = UNLICENSED;
  const items = gapList({ plan, document: documentFor(plan) });
  const [item, ...rest] = whys(items, "unlicensed in use");
  assert.equal(rest.length, 0);
  assert.equal(item.item, "Unattended Robot: 27 robots run on trial or unlicensed keys beyond the 100 purchased (Illustrative: Orchestrator licence export, 2026-10-15)");
  assert.equal(item.ownerRole, "TAM");
  assert.match(item.nextStep, /^Settle their licensing with the account team before the keys lapse or the robots are counted/);
  assert.match(item.nextStep, /Robot Consumed counts contracted licences only/);
  assert.deepEqual(whys(gapList({ plan: fixturePlan(), document: documentFor(fixturePlan()) }), "unlicensed in use"), [], "a row that states none has none");

  const v6 = fixturePlan();
  planRow(v6, "Unattended Robot").unlicensedInUse = UNLICENSED;
  const draft = { ...documentFor(v6), schemaVersion: "1.11" };
  assert.equal(whys(gapList({ plan: v6, document: draft }), "unlicensed in use").length, 1, "a schema 1.11 draft lists it too");
});

test("unlicensed robots the gap list cannot read are refused, as the merge refuses them", () => {
  const plan = fixturePlan();
  planRow(plan, "Unattended Robot").unlicensedInUse = { ...UNLICENSED, count: 0 };
  assert.throws(() => gapList({ plan, document: {} }), (error) => error instanceof PlanError && /unlicensedInUse\.count/.test(error.message));
});

// --- The team forecast's roll-up -------------------------------------------------------------------------------

test("the lines a team forecast's roll-up writes get next steps of their own", () => {
  const forecastLines = (rows, renewalDate = "2027-12-01") => {
    const plan = fixturePlan();
    plan.pipeline.opportunities = plan.pipeline.opportunities.filter(({ salesforceId }) => salesforceId !== "006EXAMPLE0000007");
    plan.contract.renewalDate = renewalDate;
    for (const [product, changes] of Object.entries(rows)) Object.assign(planRow(plan, product), changes);
    return numberFindings(plan, documentFor(plan)).conflicts;
  };
  const [above] = forecastLines({ "AI Units": { forecastUnits: { q1: 1000000, q2: 1000000, q3: null, q4: 250000 } } });
  const [missing] = forecastLines({ "Unattended Robot": { forecastUnits: { q1: 65, q2: 85, q3: 70, q4: 90 }, consumedQuantity: null } });
  const [floor] = forecastLines({ "Automation Developer": { forecastUnits: { q1: 10, q2: 12, q3: 11, q4: 12 }, consumedQuantity: 12, consumedBasis: "statement" } });
  const items = gapList({ plan: barePlan(), document: {}, conflicts: [above, missing, floor] });
  const step = (line) => items.find((entry) => entry.item === line).nextStep;
  assert.match(above, /demand6MoUnits \(2000000\) exceeds its demand12MoUnits \(1400000\)/);
  assert.match(step(above), /^Forecast every quarter through the renewal in the plan file/);
  assert.match(step(above), /\+12-month demand includes the \+6-month figure/);
  assert.match(missing, /gives no demand6MoUnits or demand12MoUnits/);
  assert.match(step(missing), /^Put the row's consumed-to-date figure in the plan file \(consumedQuantity/);
  assert.match(floor, /Not adopted/);
  assert.match(step(floor), /^Confirm the forecast with the team: a busiest quarter at or below what is already consumed adds no new demand/);
  assert.ok(items.every((entry) => entry.why === "conflict" && entry.ownerRole === "AE"));
  assert.equal(new Set(items.map((entry) => entry.nextStep)).size, 3);
  assert.ok(items.every((entry) => !/update the document or the plan so they agree/.test(entry.nextStep)), "none falls back to the neutral step");
});

test("the program clock is placed only by contract dates the app reads as ISO dates, as its contractClock does", () => {
  const clock = ["/programClock/monthsElapsed", "/programClock/totalMonths"].map((generic) => inventoryRow(generic, { tab: "Snapshot", who: "evidence", label: "" }));
  const listed = (contractStartDate, renewalDate) => gapList({ plan: barePlan(), document: { renewalDate, snapshot: { contractStartDate } }, inventory: clock }).length;
  assert.equal(listed("Dec 2025", "2027-05-31"), 2, "a start date in words places nothing");
  assert.equal(listed("2025-12-01", "end of FY27"), 2, "nor a renewal in words");
  assert.equal(listed("2025-12-1", "2027-05-31"), 2, "nor a date missing a digit");
  assert.equal(listed("2025-12-01T00:00:00Z", "2027-05-31"), 2, "nor a timestamp");
  assert.equal(listed(" 2025-12-01 ", "2027-05-31 "), 0, "the app trims before it reads");
});

test("the $0 other-activity item and the plan's pricing read the cards' keys the same way, once", () => {
  const plan = fixturePlan();
  plan.pipeline.opportunities = plan.pipeline.opportunities.filter(({ salesforceId }) => ["006EXAMPLE0000001", "006EXAMPLE0000002"].includes(salesforceId));
  plan.pipeline.useCases = [intakeUseCase()];
  const records = [
    { id: "opp-1", key: "006EXAMPLE0000001", name: "One", status: "Open", estimatedIarrUsd: 3000 },
    { id: "opp-2", key: "006EXAMPLE0000002", name: "Two", status: "Open", estimatedIarrUsd: 2000 },
    { id: "opp-u", key: "-invoice-intake-agent", name: "Invoice intake agent", status: "Open", estimatedIarrUsd: 0 }, // the app reads it as " invoice intake agent"
  ];
  const document = { ...documentFor(plan), pipelineOpportunities: records, snapshot: { otherPipelineActivityUsd: 0, pursuits: [], topPursuitIds: [] } };
  const [item] = gapList({ plan, document }).filter((entry) => /other pipeline activity is \$0/.test(entry.item));
  assert.equal(item.item, "Snapshot: other pipeline activity is $0", "the use case is off the cards and priced, so the plan does not value it at $0");
});

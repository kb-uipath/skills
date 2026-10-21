#!/usr/bin/env node
/**
 * Turns everything a Day 2 draft still lacks into one list of next steps, each with
 * an owner role, for the hand-off report (Markdown) and for the workbook's red
 * "MISSING INFORMATION & RECOMMENDED NEXT STEPS (CSM / TAM)" block (JSON).
 *
 * An item is `{ item, why, ownerRole, nextStep }`. Four sources feed the list:
 *
 *   the plan        a consumed figure that is missing ("no source", or "partial coverage" when the
 *                   plan's `telemetry.coverage` says telemetry reaches only part of the account, or the
 *                   row's `consumedBasis` is "coverage-gap", which lists the row whatever figure the
 *                   document holds) or estimated ("estimate"); a stale opportunity; a pipeline line no plan row can
 *                   take ("never-bought product"); a line with no decoded volume ("unsized line"); robots a
 *                   row states run on trial or unlicensed keys (`unlicensedInUse`, "unlicensed in use").
 *   the document    a consumption row that withholds the Snapshot's Consumed and Remaining total
 *                   ("blocks Snapshot Consumed"), as the app's `contractedConsumedUsd` does: any
 *                   row but a $0 one that has no contracted price or no consumed figure. It is one
 *                   item, carrying the plan's own reason and next step for that row. An other
 *                   pipeline activity of $0 is a figure only the team can state, so the AE is asked
 *                   to confirm it, naming the open opportunities off the cards the plan valued at
 *                   $0. A pursuit card the Snapshot shows whose Est. rev. the app withholds (no
 *                   pursuit entry or draw, as for every opportunity, whose product lines are new
 *                   entitlement so the plan gives it no draw, and for a use case starting more than
 *                   12 months out; an unsized draw; or a draw on a row with no contracted price)
 *                   leaves Known pipeline demand blank ("blocks Known pipeline demand"). A row the
 *                   shown cards draw more of than its 12-month demand, which the app footnotes, is
 *                   one item ("overdrawn"); a use case whose start date is before the plan's asOf is
 *                   one for the CSM to confirm it is live ("already started").
 *   the inventory   `gap-inventory.mjs --json` rows: every field that still renders as a gap
 *                   ("team only" when the account team states it, "no source" when a dated
 *                   source could have filled it and none did). Rows of one field are one item;
 *                   a field no v7 tab draws is left out unless it blocks publication, and so are
 *                   the program clock's months when the contract dates place the clock and the pipeline
 *                   driver of a Renewal Test row whose demand is stated as 0 and 0 ("Not adopted"); a
 *                   consumed figure the plan already explains is not listed twice.
 *   the conflicts   `pipeline.mjs findings --conflicts` lines: a value kept because the account
 *                   team's differs from Salesforce's, or one that left the plan ("conflict").
 *
 * Items come blocking ones first (a field the publication rules require, a row that withholds
 * the Snapshot's Consumed, a pursuit card with no Est. rev.), then in the deck's tab order. An item
 * names a consumption row by its product, or "<category> · <product>" when two rows share the product.
 *
 * A plan with no `pipeline` or no `contract` section has no opportunities to list. A plan with
 * both goes through `pipelineDemand`, which refuses what it cannot read. A schema 1.11 document
 * (`/day2-v6`) has no Snapshot and runs no pipeline stage, so it gets only the plan's consumed
 * figures, the conflicts and the inventory.
 *
 * Usage: node gap-list.mjs <plan.json> --document <final.day2.json> --inventory <inventory.json>
 *                          [--conflicts <conflicts.json> ...] (--out <gaps.json> | --markdown <gaps.md>)
 *   --inventory  the output of `gap-inventory.mjs <final.day2.json> --json`
 *   --conflicts  the file `pipeline.mjs findings --conflicts` wrote; repeat it for each stage run
 *   --out        writes { "gaps": [ { item, why, ownerRole, nextStep } ] }
 *   --markdown   writes the same list as a table headed | Missing | Why | Owner | Next step |
 */
import { readFileSync, writeFileSync } from "node:fs";
import { isMain } from "./cli.mjs";
import { PipelineError, normalizedKey, otherActivityUsd, pipelineDemand, shownPursuitKeys, shownPursuits } from "./pipeline.mjs";
import { PlanError, kindOrCategory, locateDocumentRows, planRowKeys, planRowToDay2 } from "./to-day2.mjs";

export class GapListError extends Error {}

const isRecord = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const isBlank = (value) => value === null || value === undefined || value === "";
const normalize = (value) => String(value ?? "").normalize("NFKC").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
/** How a product name is compared: trimmed and lower-cased, as pipeline.mjs and apply-findings.mjs do. Keys go through `normalizedKey`, as the app compares them. */
const fold = (value) => String(value ?? "").trim().toLowerCase();
/** A sentence ends in a full stop, whatever the plan's note did. */
const sentence = (text) => (/[.!?]$/.test(text.trim()) ? text.trim() : `${text.trim()}.`);

const CONSUMED = "/consumptionPlan/groups/*/rows/*/actualConsumed";
/** A pointer into a consumption row of the document, or any field of one. */
const CONSUMPTION_ROW_POINTER = /^\/consumptionPlan\/groups\/(\d+)\/rows\/(\d+)(?:\/|$)/;
/** A row of this kind (its plan row's `kind`, else its category) is a platform tier or plan bundle: granted, not consumed. Mirrors pipeline.mjs. */
const PLATFORM_CATEGORY = "platform capabilities";
const USERS_CATEGORY = "users";
const COVERAGES = new Set(["complete", "partial", "none"]);
/** The tabs of schemas 1.11 and 1.12, in deck order; a tab not listed reads after them. */
const TAB_ORDER = ["Cover", "Snapshot", "Renewal Test", "Strategic Initiatives", "Background", "Sales Plan", "Consumption Plan", "Stakeholders & Actions", "No tab today"];
const NO_TAB = "No tab today";
/**
 * Fields under consumptionPlan the v7 tabs never draw. instructions-lib.mjs gives the whole consumptionPlan
 * key to the Renewal Test, but the v7 tabs read a consumption row's offering, sold quantity, actual consumed
 * and price (the Snapshot reads their totals), and nothing else under consumptionPlan. A blank one is a
 * gap nobody sees, so it is dropped like a "No tab today" field, unless it blocks publication. Each entry
 * names a field and everything beneath it (`isUndrawn` matches by path segment), so a use case's subfields
 * and the quarters of a forecast go with their parents.
 */
const UNDRAWN = [
  "/consumptionPlan/groups/*/rows/*/comments",
  "/consumptionPlan/groups/*/rows/*/forecastUnits",
  "/consumptionPlan/groups/*/rows/*/forecastConsumption",
  "/consumptionPlan/groups/*/rows/*/licensingModel",
  "/consumptionPlan/groups/*/rows/*/skuCode",
  "/consumptionPlan/groups/*/rows/*/discountPercent",
  "/consumptionPlan/groups/*/rows/*/renewalArrUsd",
  "/consumptionPlan/businessValue/realizedUsd",
  "/consumptionPlan/businessValue/realizedOwner",
  "/consumptionPlan/businessValue/forecastedUsd",
  "/consumptionPlan/primaryUseCases",
];
const isUndrawn = (generic) => UNDRAWN.some((field) => generic === field || generic.startsWith(`${field}/`));

/** A date the app reads as one (`isoParts` in src/lib/day2PlanDerivations.ts): YYYY-MM-DD once trimmed. */
const isIsoDate = (value) => typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value.trim());
const PROGRAM_CLOCK = /^\/programClock(?:\/|$)/;
/**
 * True when the document's contract start and renewal date place the program clock ("Month X of Y"), as the app's
 * `contractClock` reads them (ISO dates), so its months elapsed and total months are only for a source that states
 * them when the dates cannot (field-mapping.md).
 */
const clockPlacedByDates = (document) => isIsoDate(document.snapshot?.contractStartDate) && isIsoDate(document.renewalDate);

const PIPELINE_DRIVER = "/renewalTest/rows/*/pipelineDriver";
const PIPELINE_DRIVER_POINTER = /^\/renewalTest\/rows\/(\d+)\/pipelineDriver$/;
/**
 * True for a Renewal Test row whose demand the team stated as 0 in both windows: the app renders it "Not adopted",
 * so there is no pipeline to name and its empty driver is no gap.
 */
function isNotAdopted(document, pointer) {
  const [, at] = PIPELINE_DRIVER_POINTER.exec(typeof pointer === "string" ? pointer : "") ?? [];
  const row = at === undefined ? undefined : document.renewalTest?.rows?.[Number(at)];
  return isRecord(row) && row.demand6MoUnits === 0 && row.demand12MoUnits === 0;
}

const AE = "AE";
const CSM = "CSM";
const TAM = "TAM";
const ALL_THREE = "AE + CSM + TAM";

/** A pipeline opportunity's fields other than the four only the team can write. */
const OPPORTUNITY_FIELDS = {
  blocker: "blocker", businessProblem: "business problem", consumptionRowIds: "consumption rows", customerValueUsd: "customer value",
  estimatedIarrUsd: "estimated IARR", execAsk: "executive ask", key: "Salesforce id", liveBy: "live-by date", motionLabel: "motion label",
  name: "name", personaTarget: "target persona", phase: "phase", products: "products", projectedConsumption: "projected consumption",
  stage: "stage", status: "status", successMeasure: "success measure",
};

const OPPORTUNITY_STEP = "Fill it from the opportunity's Salesforce record, or confirm it with the opportunity owner.";
/**
 * An opportunity field the Salesforce record does not hold. The customer value is the customer's, from a validated
 * statement (a signed-off business case), never from the record and never hours converted to dollars.
 */
const OPPORTUNITY_STEPS = {
  customerValueUsd: "Fill it from a validated statement of value to the customer, or confirm it with the opportunity owner. Never convert hours to dollars.",
};

/**
 * A use case is a pursuit the team sized with no Salesforce opportunity, so a step that reads a field from Salesforce
 * reads it from the team's own tracker instead (`useCaseRule`).
 */
const USE_CASE_STEP = "Fill it from the team's own tracker; this pursuit has no Salesforce record. Or confirm it with the account team.";
const USE_CASE_STEPS = {
  owner: "Confirm the pursuit's current owner from the team's own tracker; this pursuit has no Salesforce record. Enter it in the app.",
};
const OPPORTUNITY_FIELD = /^\/pipelineOpportunities\/\*\/([^/]+)$/;
const OPPORTUNITY_RECORD = /^\/pipelineOpportunities\/(\d+)\//;

/** [generic pointer, how the field reads in an item, owner role, next step]. */
const FIELDS = [
  ["/renewalTest/healthyAtPercent", "Healthy threshold", ALL_THREE, "Agree, before looking at the pipeline, the share of each entitlement that counts as healthy for this account, and enter it in the app. It has no default."],
  ["/snapshot/status", "Bottom line health", CSM, "State the call the account team stands behind for this review (Healthy, At risk or Unhealthy) and enter it in the app. It is never derived from figures."],
  ["/renewalTest/status", "Renewal test health", CSM, "State the call the account team stands behind once the test is run (Healthy, At risk or Unhealthy) and enter it in the app."],
  ["/renewalTest/verdict", "Renewal test statement", CSM, "Run the test, then write two or three lines: the threshold agreed, where full pipeline delivery lands against it, and the one action that closes the gap."],
  ["/renewalTest/runOn", "Renewal test run date", CSM, "Record the date the team ran the renewal test."],
  ["/renewalTest/runBy", "Renewal test run by", CSM, "Record who ran the renewal test."],
  ["/renewalTest/rows/*/confidence", "Pipeline confidence", CSM, "Set High, Med or Low from whether the use case driving the line has a scope, an owner and a date."],
  ["/renewalTest/rows/*/pipelineDriver", "Pipeline driver", AE, "Name the opportunity or use case that drives this row's demand."],
  ["/renewalTest/rows/*/demand6MoUnits", "Demand within 6 months", AE, "State the units the pipeline adds within 6 months, from an opportunity's quantities or a stated forecast."],
  ["/renewalTest/rows/*/demand12MoUnits", "Demand within 12 months", AE, "State the units the pipeline adds within 12 months, from an opportunity's quantities or a stated forecast."],
  ["/snapshot/accountPlay", "Account play", CSM, "Choose the play the account plan records: Consumption, Commercial or Hybrid."],
  ["/snapshot/topPursuitIds", "Top pursuits", AE, "Confirm the three pursuits the app ranks by value, or name up to three others in the app, then rerun Step 9.5 on the exported draft so other pipeline activity follows the cards."],
  ["/snapshot/otherPipelineActivityUsd", "Other pipeline activity", AE, "Total the entitlement value of known pipeline that is not on a pursuit card, in whole USD, and enter it. Enter 0 only when the team states there is none."],
  ["/snapshot/pursuits/*/draw/*/units", "Pursuit draw units", AE, "State the units this use case draws on the row, from the team's sizing. An opportunity draws nothing from today's rows (its product lines are new entitlement), so remove a draw line on an opportunity's card instead."],
  ["/snapshot/pursuits/*/cardStatus", "Pursuit card status", AE, "Set On track, At risk or Blocked as the opportunity owner states it."],
  ["/snapshot/pursuits", "Pursuits", AE, "Add a pursuit card for each top use case the team sized, drawing on the consumption rows it will use. An opportunity's card draws nothing: its product lines are new entitlement, not use of today's rows."],
  ["/snapshot/csPriorities", "CS priorities", CSM, "Agree the run-the-account priorities with the team and enter each with a target date and a named owner."],
  ["/renewalTest/rows", "Renewal test rows", AE, "Add a row for each consumption row the pipeline will draw on, with its pipeline driver and demand."],
  ["/renewalDate", "Renewal date", AE, "Confirm the renewal date from the contract and enter it."],
  ["/pipelineOpportunities", "Pipeline opportunities", AE, "Confirm whether the account has open opportunities; if so, add each from Salesforce and have its owner supply the owner, next gate and motions."],
  ["/pipelineOpportunities/*/owner", "Opportunity owner", AE, "Confirm the opportunity's current owner (the hand-off offers the Salesforce owner as a suggestion) and enter it in the app."],
  ["/pipelineOpportunities/*/nextGate", "Opportunity next gate", AE, "Agree one specific next decision or validation gate with the owner and enter it."],
  ["/pipelineOpportunities/*/nextGateDate", "Opportunity next gate date", AE, "Give the date of that next gate."],
  ["/pipelineOpportunities/*/motions", "Opportunity motions", AE, "Select every applicable motion (M1, M2, M3) after account-team review."],
  ...Object.entries(OPPORTUNITY_FIELDS).map(([field, name]) => [
    `/pipelineOpportunities/*/${field}`, `Opportunity ${name}`, AE, OPPORTUNITY_STEPS[field] ?? OPPORTUNITY_STEP,
  ]),
  [CONSUMED, "Consumed to date", TAM, "Bring a consumed-to-date figure from a dated source, with its basis and date."],
];

/**
 * Who closes a gap and what they do, keyed by the field's generic pointer (as `gap-inventory.mjs`
 * prints it). Any other field belongs to the CSM, who runs the review. A consumed figure is the
 * TAM's, or the CSM's when its row is a user license (`gapList` decides by the row's kind, else its category).
 */
export const OWNER_ROLES = {
  ...Object.fromEntries(FIELDS.map(([pointer, , ownerRole, nextStep]) => [pointer, { ownerRole, nextStep }])),
  "*": { ownerRole: CSM, nextStep: "Ask the account team for the value, or find a dated source for it, and enter it in the app." },
};
const FIELD_NAMES = new Map(FIELDS.map(([pointer, name]) => [pointer, name]));

/** The evidence that settles a row's consumed figure, by the row's kind, else its category. */
const CONSUMED_EVIDENCE = {
  robots: "the allocation figure (robots allocated or running), or an estimate with its basis and date from the team's notes, mail or channels",
  users: "the seats assigned to named users (not monthly active users)",
  consumables: "the consumed-to-date figure from the entitlement record",
  "platform capabilities": "a dated statement or telemetry showing the platform in production use (a tier is used whole, so Consumed is its purchased quantity)",
};
const consumedStep = (kind) => {
  const evidence = CONSUMED_EVIDENCE[normalize(kind)];
  return evidence ? `Bring ${evidence}.` : OWNER_ROLES[CONSUMED].nextStep;
};
const consumedOwner = (kind) => (normalize(kind) === USERS_CATEGORY ? CSM : TAM);
const rowLabel = (row) => row.offering || row.product || "Unnamed row";

/**
 * How an item names a consumption row: its product, or "<category> · <product>" when the plan carries that product
 * on two rows or the document holds it on two, since the product alone then names both. A row with no category to
 * say keeps its product.
 */
function rowNamer(plan, document) {
  const shared = new Set(planRowKeys(plan).filter((entry) => entry.shared).map((entry) => fold(entry.product)));
  const perOffering = new Map();
  for (const group of Array.isArray(document.consumptionPlan?.groups) ? document.consumptionPlan.groups : []) {
    for (const row of Array.isArray(group?.rows) ? group.rows : []) {
      if (isRecord(row)) perOffering.set(fold(rowLabel(row)), (perOffering.get(fold(rowLabel(row))) ?? 0) + 1);
    }
  }
  for (const [offering, count] of perOffering) if (count > 1) shared.add(offering);
  return (category, product) => {
    const group = typeof category === "string" ? category.trim() : "";
    return group && shared.has(fold(product)) ? `${group} · ${product}` : product;
  };
}

/** What the plan's optional `telemetry: { asOf, coverage, note }` says about how far measurement reaches. */
function readTelemetry(plan) {
  const telemetry = plan?.telemetry;
  if (telemetry === undefined || telemetry === null) return { coverage: "", note: "" };
  if (!isRecord(telemetry)) throw new GapListError("plan.telemetry must be an object");
  const coverage = telemetry.coverage ?? "";
  if (typeof coverage !== "string" || (coverage.trim() !== "" && !COVERAGES.has(coverage.trim()))) {
    throw new GapListError(`plan.telemetry.coverage must be "complete", "partial" or "none", got ${JSON.stringify(coverage)}`);
  }
  return { coverage: coverage.trim(), note: typeof telemetry.note === "string" ? telemetry.note.trim() : "" };
}

/**
 * Why a consumed figure is missing, and what to do about it, given how far telemetry reaches. `kind` is the row's
 * kind, else its category. A row the plan states as a coverage gap is partial coverage whatever the plan's
 * `telemetry.coverage` says: that is what the basis means.
 */
function unmeasured(kind, telemetry, { coverageGap = false } = {}) {
  const partial = coverageGap || telemetry.coverage === "partial";
  return {
    why: partial ? "partial coverage" : "no source",
    nextStep: [
      consumedStep(kind),
      partial ? "Telemetry covers only part of this account's deployments, so a missing or 0 figure there is not a measured zero." : "",
      telemetry.note && (coverageGap || (telemetry.coverage !== "complete" && telemetry.coverage !== "")) ? `Telemetry note: ${sentence(telemetry.note)}` : "",
    ].filter(Boolean).join(" "),
  };
}

/** The `kind` of the plan row each located document row came from, keyed by the document row. */
const documentRowKinds = (located) => new Map([...located.values()].map(({ row, kind }) => [row, kind]));

/**
 * What a document row is: its plan row's `kind` when it has one, else its group's category. A row the plan
 * does not name has only its group's category to say.
 */
const documentRowKind = (kinds, group, row) => kindOrCategory(kinds.get(row), group?.element ?? "");

/**
 * The plan rows whose consumed figure is missing or estimated, each with the document row it explains when
 * the document has it. A platform tier is granted, not consumed, so it needs no figure of its own (a priced
 * one is listed by `consumptionItems`). A figure the team already put in the document answers the plan row,
 * unless the plan states the row as a coverage gap: then the document's figure (a baseline 0 that the merge
 * has not cleared) answers nothing, and the row is listed.
 */
function consumedEntries(plan, located, telemetry, name) {
  const entries = [];
  for (const { row, product, category, kind: planKind, key } of planRowKeys(plan)) {
    const kind = kindOrCategory(planKind, category);
    if (normalize(kind) === PLATFORM_CATEGORY) continue;
    const documentRow = located.get(key)?.row;
    // The row as the document groups it, which is how the blocking item for the same row names it.
    const named = name(located.get(key)?.category ?? category, product);
    const known = Number.isFinite(row.consumedQuantity);
    const basis = typeof row.consumedBasis === "string" ? row.consumedBasis.trim() : "";
    const asOf = typeof row.consumedAsOf === "string" ? row.consumedAsOf.trim() : "";
    if (known && basis === "estimate") {
      entries.push({
        documentRow,
        estimate: true,
        item: `Consumed to date (estimate): ${named}`,
        why: "estimate",
        ownerRole: TAM,
        nextStep: `Confirm or replace the estimate with a measured figure; its basis is in the row notes${asOf ? ` and it is dated ${asOf}` : ""}.`,
      });
    } else if (!known && basis === "coverage-gap") {
      entries.push({ documentRow, item: `Consumed to date: ${named}`, ownerRole: consumedOwner(kind), ...unmeasured(kind, telemetry, { coverageGap: true }) });
    } else if (!known && !(documentRow && !isBlank(documentRow.actualConsumed))) {
      entries.push({ documentRow, item: `Consumed to date: ${named}`, ownerRole: consumedOwner(kind), ...unmeasured(kind, telemetry) });
    }
  }
  return entries;
}

const isPositive = (value) => typeof value === "number" && Number.isFinite(value) && value > 0;

/**
 * One TAM item for each plan row that states robots running on trial or unlicensed keys (`unlicensedInUse`): they hold
 * no contracted licence, so they are not in Consumed, and they lapse or get counted unless their licensing is settled.
 * `tab` is where the row reads.
 */
function unlicensedItems(plan, located, name, tab) {
  return planRowKeys(plan).flatMap(({ row, index, product, category, kind, key }) => {
    const { unlicensedInUse } = planRowToDay2(row, index);
    if (!unlicensedInUse) return [];
    const { count, source, asOf } = unlicensedInUse;
    const robots = normalize(kindOrCategory(kind, category)) === "robots";
    const unit = robots ? "robots" : (typeof row.unit === "string" && row.unit.trim()) || "units";
    const purchased = Number.isFinite(row.purchasedQuantity) ? `the ${row.purchasedQuantity} purchased` : "those purchased";
    return [{
      item: `${name(located.get(key)?.category ?? category, product)}: ${count} ${unit} run on trial or unlicensed keys beyond ${purchased} (${source}, ${asOf})`,
      why: "unlicensed in use",
      ownerRole: TAM,
      nextStep: `Settle their licensing with the account team before the keys lapse or the ${unit} are counted: license the ones that stay in production, or retire them, and record when the keys expire. ${robots ? "Robot Consumed" : "Consumed"} counts contracted licences only, so they are not in it.`,
      tab,
      blocking: false,
    }];
  });
}

/**
 * True when the app can put a contracted unit price on the row, as its `rowUnitPriceUsd` does: a $0 row is
 * priced at $0 whatever its count; any other row needs a positive purchased quantity, and a positive ARR of
 * its own or, with none entered, the account's ARR (`anchorArrUsd`) to take a share of. Anything else, a
 * missing quantity included, is unpriced.
 */
const isPriced = (row, anchorArrUsd) => isRecord(row) && (row.soldArrUsd === 0 || (isPositive(row.soldQuantity)
  && (isPositive(row.soldArrUsd) || (isBlank(row.soldArrUsd) && Number.isFinite(anchorArrUsd)))));

const PRICE_STEP = "State the row's contracted ARR and purchased quantity, so a unit of it can be priced.";
const ALSO_PRICE = "The AE also states its contracted ARR and purchased quantity, so a unit of it can be priced.";
const SNAPSHOT_BLANK = "Until every row is priced and measured, the Snapshot's Consumed and Remaining stay blank; only a $0 row is skipped.";

/**
 * The item for a document row that withholds the Snapshot's Consumed: why its figure or its price is
 * missing, from the plan's own entry for the row (`own`) when it has one, and what that blanks. `kind` is
 * what the row is (`documentRowKind`); `label` is how the item names the row (`rowNamer`).
 */
function blockingItem(kind, label, own, { unpriced, unmeasuredRow }, telemetry) {
  const priceNote = unpriced ? "; no contracted price" : "";
  const block = (item, ownerRole, ...steps) => ({
    item, why: "blocks Snapshot Consumed", ownerRole, nextStep: [...steps, SNAPSHOT_BLANK].filter(Boolean).join(" "), tab: "Snapshot", blocking: true,
  });
  if (unmeasuredRow) {
    const reason = own && !own.estimate ? own : { ...unmeasured(kind, telemetry), ownerRole: consumedOwner(kind) };
    return block(`Consumed to date: ${label} (${reason.why})${priceNote}`, reason.ownerRole, reason.nextStep, unpriced && ALSO_PRICE);
  }
  if (own?.estimate) return block(`Consumed to date (estimate): ${label}${priceNote}`, own.ownerRole, own.nextStep, ALSO_PRICE);
  return block(`Contracted price: ${label}`, AE, PRICE_STEP);
}

/**
 * Every consumption row the list names, once. A document row that withholds the Snapshot's Consumed and
 * Remaining, as the app's `contractedConsumedUsd` does (any row but a $0 one with no contracted price or no
 * consumed figure), is one blocking item that keeps the plan's reason and next step for the row; every other
 * plan row with a missing or estimated figure is an item of its own. `explained` is every document row an
 * item names, so the inventory does not list it again. Without a Snapshot (`snapshot: false`, schema 1.11) no
 * row blocks anything, and each plan row's item reads on the Consumption Plan tab.
 */
function consumptionItems(plan, document, located, telemetry, name, { snapshot = true } = {}) {
  const entries = consumedEntries(plan, located, telemetry, name);
  const kinds = documentRowKinds(located);
  const byRow = new Map(entries.filter(({ documentRow }) => documentRow).map((entry) => [entry.documentRow, entry]));
  const anchorArrUsd = document.renewalEconomics?.currentArrUsd;
  const items = [];
  const merged = new Set();
  for (const group of snapshot && Array.isArray(document.consumptionPlan?.groups) ? document.consumptionPlan.groups : []) {
    for (const row of Array.isArray(group?.rows) ? group.rows : []) {
      if (!isRecord(row) || row.soldArrUsd === 0) continue;
      const state = { unpriced: !isPriced(row, anchorArrUsd), unmeasuredRow: isBlank(row.actualConsumed) };
      if (!state.unpriced && !state.unmeasuredRow) continue;
      const own = byRow.get(row);
      if (own) merged.add(own);
      items.push({ ...blockingItem(documentRowKind(kinds, group, row), name(group?.element, rowLabel(row)), own, state, telemetry), row });
    }
  }
  for (const entry of entries) {
    if (merged.has(entry)) continue;
    const { item, why, ownerRole, nextStep, documentRow } = entry;
    items.push({ item, why, ownerRole, nextStep, tab: snapshot ? "Renewal Test" : "Consumption Plan", blocking: false, row: documentRow });
  }
  return { items, explained: new Set(items.map(({ row }) => row).filter(Boolean)) };
}

const NO_DRAW = "it has no pursuit entry or no draw";
const PURSUIT_BLANK = "until then Known pipeline demand and Net of pipeline stay blank.";
/** An opportunity card's next step: its product lines are new entitlement, so it never draws on today's rows. */
const OPPORTUNITY_PURSUIT_STEP = "This opportunity adds its own entitlement and draws nothing from today's rows; pick top pursuits in the app that draw on existing entitlement (team-sized use cases), then rerun Step 9.5 on the exported draft.";
/** The plan's use-case keys, as the app compares keys: a record keyed by none of them is an opportunity's. */
const useCaseKeysOf = (pipeline) => new Set((pipeline?.useCases ?? []).map(({ key }) => normalizedKey(key)));
const isUseCaseRecord = (record, useCaseKeys) => normalizedKey(record?.key) !== "" && useCaseKeys.has(normalizedKey(record.key));

/**
 * Why the app withholds a pursuit card's Est. rev., or "" when it shows one. Mirrors `pursuitEstRevUsd`
 * (src/lib/day2PlanDerivations.ts): it prices each chosen draw line at its row's contracted unit price, and
 * withholds the total when the opportunity has no pursuit entry or no chosen draw line, when any line has no
 * units, or when any line's row is not in the document or has no contracted price.
 */
function withheldEstRev(record, pursuits, rows, anchorArrUsd) {
  const pursuit = typeof record.id === "string" && record.id !== "" ? pursuits.find((candidate) => candidate.opportunityId === record.id) : undefined;
  // A draw line with no row chosen yet is an unfinished edit, not a draw.
  const draw = (Array.isArray(pursuit?.draw) ? pursuit.draw : []).filter((line) => isRecord(line) && line.rowId !== "");
  if (!draw.length) return NO_DRAW;
  for (const line of draw) {
    if (!Number.isFinite(line.units)) return "a draw line has no units";
    const row = typeof line.rowId === "string" ? rows.find((candidate) => candidate.id === line.rowId) : undefined;
    if (!isPriced(row, anchorArrUsd)) return "a draw is on a row with no contracted price";
  }
  return "";
}

/**
 * One item for each pursuit card the Snapshot shows whose Est. rev. is withheld: Known pipeline demand and
 * Net of pipeline stay blank until every shown card has one. The cards are the app's default ranking, or
 * the pursuits the team names (`shownPursuitKeys`). A card whose record is not one of the plan's use cases
 * (matched by key as the app compares keys) is an opportunity's, which draws nothing from today's rows (its
 * product lines are new entitlement), so the AE picks pursuits that draw on existing entitlement. A use
 * case's card with no draw that the plan has starting more than 12 months out (`pipeline.beyondWindow`)
 * gets none from the plan: the AE re-dates it or chooses other pursuits; any other use case's draw is the
 * team's to size. Choosing other pursuits changes what other pipeline activity counts, so each next step
 * ends with rerunning the final stage.
 */
function pursuitItems(document, pipeline, asOf) {
  const opportunities = Array.isArray(document.pipelineOpportunities) ? document.pipelineOpportunities.filter(isRecord) : [];
  const pursuits = Array.isArray(document.snapshot?.pursuits) ? document.snapshot.pursuits.filter(isRecord) : [];
  const groups = Array.isArray(document.consumptionPlan?.groups) ? document.consumptionPlan.groups : [];
  const rows = groups.flatMap((group) => (Array.isArray(group?.rows) ? group.rows : [])).filter(isRecord);
  const useCaseKeys = useCaseKeysOf(pipeline);
  const beyond = new Map((pipeline?.beyondWindow ?? []).filter(isUseCase).map((item) => [normalizedKey(item.key), item]));
  const items = [];
  // A record with no key is keyed "" by shownPursuitKeys; the first such record stands for it.
  for (const key of new Set(shownPursuitKeys(document))) {
    const record = opportunities.find((candidate) => (typeof candidate.key === "string" ? candidate.key : "") === key);
    const reason = record ? withheldEstRev(record, pursuits, rows, document.renewalEconomics?.currentArrUsd) : "";
    if (!reason) continue;
    const useCase = isUseCaseRecord(record, useCaseKeys);
    const late = useCase && reason === NO_DRAW ? beyond.get(normalizedKey(key)) : undefined;
    items.push({
      item: `Pursuit card "${(typeof record.name === "string" && record.name.trim()) || key || "unnamed opportunity"}": Est. rev. is withheld (${late ? `it starts ${late.startDate}, more than 12 months after ${asOf}, so this plan gives it no draw` : reason})`,
      why: "blocks Known pipeline demand",
      ownerRole: AE,
      nextStep: !useCase
        ? OPPORTUNITY_PURSUIT_STEP
        : late
          ? `Re-date the use case in the plan file if it starts sooner and rerun the numbers stage, or choose other top pursuits in the app, then rerun Step 9.5 on the exported draft; ${PURSUIT_BLANK}`
          : `Size this pursuit's draw on the account's existing entitlement, or choose top pursuits in the app that draw on it, then rerun Step 9.5 on the exported draft; ${PURSUIT_BLANK}`,
      tab: "Snapshot",
      blocking: true,
    });
  }
  return items;
}

/**
 * One item for each consumption row the shown pursuit cards draw more of than its 12-month demand, the app's
 * "overdrawn" Renewal Test footnote (`renewalTestFindings` in src/lib/day2PlanDerivations.ts): the cards are
 * `shownPursuits`; each card's draw lines with a row chosen and units stated count against that row; the row's
 * demand is its first renewal-test entry's `demand12MoUnits`, and a row with none, or a null one, is not compared.
 * A pursuit's draws are part of its row's 12-month demand, so they cannot exceed it. Only a use case draws (the plan
 * gives an opportunity none: its product lines are new entitlement), so the cause is a team forecast below a use case's
 * sizing, or a use case with no start date (or one already started), drawing on a card while adding no demand. A draw on
 * an opportunity's card (a record keyed by none of `useCaseKeys`) still counts, as the app counts it, and the AE is
 * asked to remove it.
 */
function overdrawnItems(document, name, useCaseKeys) {
  const pursuits = Array.isArray(document.snapshot?.pursuits) ? document.snapshot.pursuits.filter(isRecord) : [];
  const entries = Array.isArray(document.renewalTest?.rows) ? document.renewalTest.rows.filter(isRecord) : [];
  const drawing = shownPursuits(document).flatMap((record) => {
    const pursuit = typeof record.id === "string" && record.id !== "" ? pursuits.find((candidate) => candidate.opportunityId === record.id) : undefined;
    const lines = (Array.isArray(pursuit?.draw) ? pursuit.draw : []).filter((line) => isRecord(line) && line.rowId !== "" && Number.isFinite(line.units));
    const label = (typeof record.name === "string" && record.name.trim()) || (typeof record.key === "string" && record.key.trim()) || "unnamed opportunity";
    const useCase = isUseCaseRecord(record, useCaseKeys);
    return lines.map((line) => ({ label, useCase, rowId: line.rowId, units: line.units }));
  });
  const items = [];
  for (const group of Array.isArray(document.consumptionPlan?.groups) ? document.consumptionPlan.groups : []) {
    for (const row of Array.isArray(group?.rows) ? group.rows : []) {
      if (!isRecord(row)) continue;
      const entry = row.id ? entries.find((candidate) => candidate.rowId === row.id) : undefined;
      const demand = entry?.demand12MoUnits;
      if (!Number.isFinite(demand)) continue;
      const lines = drawing.filter((line) => line.rowId === row.id);
      const drawn = lines.reduce((total, line) => total + line.units, 0);
      if (drawn <= demand) continue;
      const named = new Map();
      for (const line of lines) if (line.units > 0) named.set(line.label, (named.get(line.label) ?? 0) + line.units);
      const drawers = (useCase) => [...new Set(lines.filter((line) => line.units > 0 && line.useCase === useCase).map((line) => line.label))];
      const [opportunityCards, useCases] = [drawers(false), drawers(true)];
      items.push({
        item: `Top pursuits draw ${drawn} ${name(group?.element, rowLabel(row))}, more than its ${demand} 12-month demand (${[...named].map(([label, units]) => `"${label}" ${units}`).join("; ")})`,
        why: "overdrawn",
        ownerRole: AE,
        nextStep: [
          opportunityCards.length
            ? `Remove the draws on the ${listed(opportunityCards.map((label) => `"${label}"`))} ${opportunityCards.length === 1 ? "card" : "cards"} in the app: an opportunity adds its own entitlement and draws nothing from today's rows.`
            : "",
          useCases.length
            ? `Reconcile the team forecast with ${useCases.length === 1 ? "this use case's" : "these use cases'"} sizing, or date the use case: a pursuit card's draws are part of the row's 12-month demand, so they cannot exceed it. Correct the plan file (the row's forecastUnits, the use case's lines or its startDate) and rerun the numbers stage, or change the draws or the demand in the app; until then the Renewal Test footnotes the row.`
            : "Until then the Renewal Test footnotes the row.",
        ].filter(Boolean).join(" "),
        tab: "Renewal Test",
        blocking: false,
      });
    }
  }
  return items;
}

/**
 * One item for each use case whose start date is before the plan's `asOf`: it adds no demand, since its use is
 * already in the row's consumed figure if it is live, so the CSM confirms that it is.
 */
function startedItems(pipeline, asOf) {
  return (pipeline?.started ?? []).map((useCase) => ({
    item: `Use case "${useCase.name}" (${useCase.key}): started ${useCase.startDate}, before this plan's ${asOf}`,
    why: "already started",
    ownerRole: CSM,
    nextStep: `Confirm with the account team that it is live. If it is, its use is already in Consumed to date and it adds no demand: remove it from the plan's use cases, and its draws from its pursuit card in the app. If it has not started, give the plan file the date it will start (from ${asOf} on) and rerun the numbers stage.`,
    tab: "Renewal Test",
    blocking: false,
  }));
}

/**
 * True for a document of a schema before 1.12 (a `/day2-v6` draft): its tabs have no Snapshot, pursuit cards or
 * pipeline demand, and its consumption rows are on the Consumption Plan tab. A document that states no version
 * is read as 1.12.
 */
function beforeSnapshot(document) {
  const [major, minor] = String(document.schemaVersion ?? "").split(".").map(Number);
  return Number.isInteger(major) && Number.isInteger(minor) && (major < 1 || (major === 1 && minor < 12));
}

/** The plan's pipeline as `pipelineDemand` reads it, or null when it has no `pipeline` or no `contract` section. */
const readPlanPipeline = (plan) => (isRecord(plan.pipeline) && isRecord(plan.contract) ? pipelineDemand(plan) : null);

/** True for a use case the team sized, as `pipelineDemand` lists it beside the opportunities. */
const isUseCase = (pursuit) => typeof pursuit?.salesforceId !== "string";
/** "on "<opportunity>"", or "on use case "<name>"". */
const onPursuit = (pursuit) => `on ${isUseCase(pursuit) ? "use case " : ""}"${pursuit.name}"`;

/** The open opportunities and use cases the plan cannot use: stale opportunities, and lines no plan row can take or size. */
function pipelineItems(pipeline) {
  if (!pipeline) return [];
  const { stale, unmapped, unsized } = pipeline;
  const make = (item, why, nextStep) => ({ item, why, ownerRole: AE, nextStep, tab: "Snapshot", blocking: false });
  return [
    ...stale.map((opportunity) => make(
      `Opportunity "${opportunity.name}": close date ${opportunity.closeDate} has passed and it is still open`,
      "stale opportunity",
      "Re-date or close it in Salesforce. Until then it adds no demand.",
    )),
    ...unmapped.map(({ opportunity, line }) => make(
      `Product "${line.product}" ${onPursuit(opportunity)}`,
      "never-bought product",
      "Confirm the account has never bought it (if it has, map the line to its plan row). Until then it draws on no entitlement and adds no demand.",
    )),
    ...unsized.map(({ opportunity, line }) => make(
      `Line "${line.product}" ${onPursuit(opportunity)}: no unit volume`,
      "unsized line",
      `State how many units it adds to ${line.row}${isUseCase(opportunity) ? " in the plan file's use case (the team's sizing gives none), so demand, its pursuit draw" : " (its product name does not decode to a quantity), so demand"} and other pipeline activity can count it; until then they stay blank rather than understated.`,
    )),
  ];
}

/** What a kept or cleared line says gives the other value, other than Salesforce's opportunities, as pipeline.mjs words it. */
const GIVERS = [
  "Salesforce opportunities and team-sized use cases now give",
  "team-sized use cases now give",
  "the team-sized use case now gives",
  "the team forecast (forecastUnits) now gives",
];
/** "the team-sized use case now gives", or undefined when the line says Salesforce's opportunities give it. */
const giverOf = (line) => GIVERS.find((giver) => line.includes(`; ${giver} `));

/**
 * The next step for each shape of line `pipeline.mjs findings --conflicts` writes, tried in order. The
 * departure lines each end with their own action sentence for the AE; these say the same with the
 * one concrete thing to settle.
 */
const CONFLICT_STEPS = [
  // "<field>: kept <team's value>, which this plan did not write; Salesforce opportunities now give <value>."
  // (or a use case, use cases, or the team forecast "now give(s)")
  [/: kept .*, which this plan did not write;/, (line) => {
    const giver = giverOf(line);
    return `Confirm which value stands, the account team's or what ${giver ?? "Salesforce now shows"}, and update the other so they agree.`;
  }],
  // "<field>: left blank, as the account team cleared it (this plan wrote <value>); Salesforce opportunities now give <value>."
  [/: left blank, as the account team cleared it /, (line) => `Confirm the team meant to clear it; if not, enter the value ${giverOf(line) ?? "Salesforce now gives"} in the app.`],
  // "Opportunity "<name>" (<id>): its record, which this plan added, is no longer in the document, so it is not added again. ...";
  //  "Use case "<name>" (<key>): its record | its pursuit card | its draw on "<row>", which this plan added | wrote, is no longer
  //  in the document | on its pursuit card, so it is not added | drawn again. ..."; also "renewalTest row "<row>", which ..."
  [/, which this plan (?:added|wrote), is no longer (?:in the document|on its pursuit card), so it is not (?:added|drawn) again/, "Confirm the team meant to remove it; if not, add it back in the app."],
  // "Use case "<name>" (<key>): the document has a record of that name keyed "<key>", so no second record is added. ..."
  [/^Use case ".*" \(\S+\): the document has a record of that name keyed .*, so no second record is added\./, "Set that record's key in the app to the use case's key, given in parentheses, so the next run fills it instead of adding a second record."],
  // "Opportunity "<name>" (<id>): the document has a record of that name keyed "<key>", so no second record is added. ..."
  [/: the document has a record of that name keyed .*, so no second record is added\./, "Set that record's key in the app to the opportunity's Salesforce id, given in parentheses, so the next run fills it instead of adding a second record."],
  // "Use case "<name>" (<key>) now starts <date>, more than 12 months after <asOf>, so this plan draws nothing for it; ..."
  [/^Use case ".*" \(\S+\) now starts \S+, more than 12 months after \S+, so this plan draws nothing for it;/, "Re-date the use case in the plan file if it starts sooner; otherwise remove its draws in the app, since a top pursuit's draws count toward the row's 12-month demand."],
  // "Opportunity "<name>" (<id>): this plan no longer draws for opportunities, since an opportunity adds its own entitlement and
  //  draws nothing from today's rows; the draw(s) it wrote earlier on "<row>" ... remain(s) on its pursuit card. ..."
  [/^Opportunity ".*" \(\S+\): this plan no longer draws for opportunities,/, "Remove the draws named from the opportunity's pursuit card in the app: an opportunity adds its own entitlement and draws nothing from today's rows."],
  // "Opportunity <id> is no longer open in this plan; its card, draws and demand remain in the document. ..."
  [/^Opportunity \S+ is no longer open in this plan;/, "Confirm its Salesforce status, then close it or remove its card, draws and demand in the app."],
  // "Use case <key> is no longer in this plan; its record, card, draws and demand remain in the document. ..."
  [/^Use case \S+ is no longer in this plan;/, "Confirm with the account team whether the pursuit is still planned (it may now have a Salesforce opportunity of its own), then remove its record, card, draws and demand in the app."],
  // "Use case "<name>" (<key>): its earlier draw on "<row>" is no longer in this plan's lines, but it remains in the document. ..."
  [/ its earlier draw on ".*" is no longer in this plan's lines/, "Confirm whether the draw still stands, then keep it or remove it in the app; if the line was dropped by mistake, restore it in the plan."],
  // "renewalTest row "<row>": its demand6MoUnits (<n>) exceeds its demand12MoUnits (<m>), which includes it; ..."
  [/^renewalTest row ".*": its demand6MoUnits \(\S+\) exceeds its demand12MoUnits \(\S+\), which includes it;/, "Forecast every quarter through the renewal in the plan file, so the forecast gives both windows, or reconcile its quarters with the pipeline's sizing, then rerun the numbers stage: the +12-month demand includes the +6-month figure."],
  // "renewalTest row "<row>": the team forecast (forecastUnits) gives no <field(s)>, since the plan row has no consumed figure ..."
  [/^renewalTest row ".*": the team forecast \(forecastUnits\) gives no .*, since the plan row has no consumed figure/, "Put the row's consumed-to-date figure in the plan file (consumedQuantity, with its basis and date: the TAM's, or the CSM's for a user license) and rerun the numbers stage: a seat or robot forecast is new demand only above what is already consumed."],
  // "renewalTest row "<row>": the team forecast (forecastUnits) gives 0 <field(s)>, since its busiest quarter there (<n>) is at or below the <m> already consumed ..."
  [/^renewalTest row ".*": the team forecast \(forecastUnits\) gives 0 .*, since its busiest quarter there \(\S+\) is at or below/, "Confirm the forecast with the team: a busiest quarter at or below what is already consumed adds no new demand, so the row reads as Not adopted when nothing in the pipeline drives it. If the team expects growth, raise the quarters in the plan file and rerun the numbers stage; otherwise the 0 stands."],
  // "renewalTest row "<row>": no open opportunity in this plan drives it any more, but the driver and demand ... remain in the document. ..."
  [/^renewalTest row ".*": no open opportunity in this plan drives it any more/, "Confirm the row's driver and demand still hold, then change or clear them in the app."],
  // "snapshot.otherPipelineActivityUsd not written | cleared the <value> this plan wrote earlier: <n> line(s) have no unit volume
  //  to value them: <opportunity> (<row>); ..." (and, when the team's figure stays, "The account team's <value> stays.")
  [/^snapshot\.otherPipelineActivityUsd (?:not written|cleared the \S+ this plan wrote earlier): \d+ line\(s\) have no unit volume/, "State the units of each line named (its row in brackets) in the plan file, from the opportunity's quantities or the team's sizing of the use case, so it can be priced, or enter the other pipeline activity in whole USD."],
  // "snapshot.otherPipelineActivityUsd not written | cleared the <value> this plan wrote earlier: <n> sized line(s) have no
  //  contracted unit price to value them: <opportunity> (<row>); ..."
  [/^snapshot\.otherPipelineActivityUsd (?:not written|cleared the \S+ this plan wrote earlier): /, "State the contracted ARR and purchased quantity of each row named in brackets, so a unit of it can be priced, or enter the other pipeline activity in whole USD."],
];
const CONFLICT_FALLBACK = "Confirm what the line reports and update the document or the plan so they agree.";

function conflictItems(conflicts) {
  return conflicts.map((line) => {
    const step = CONFLICT_STEPS.find(([shape]) => shape.test(line))?.[1] ?? CONFLICT_FALLBACK;
    return {
      item: line,
      why: "conflict",
      ownerRole: AE,
      nextStep: typeof step === "function" ? step(line) : step,
      tab: /^renewalTest\b/.test(line) ? "Renewal Test" : "Snapshot",
      blocking: false,
    };
  });
}

/** A, A and B, or A, B and C. */
const listed = (parts) => (parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts.at(-1)}` : parts[0]);

/**
 * The other pipeline activity is 0 only when the team states there is none. When the plan valued it at $0
 * with open opportunities or use cases off the cards (only never-bought products, platform tiers, $0 rows or
 * no lines), the item names them, since the AE confirms those add nothing; otherwise it asks the AE to confirm
 * there is no other activity.
 */
function otherActivityItems(plan, document, pipeline) {
  if (document.snapshot?.otherPipelineActivityUsd !== 0) return [];
  const shownKeys = shownPursuitKeys(document);
  const shown = new Set(shownKeys.map(normalizedKey));
  const offCards = pipeline && otherActivityUsd(plan, shownKeys).usd === 0
    ? [...pipeline.open, ...pipeline.useCases].filter((item) => !shown.has(normalizedKey(item.salesforceId ?? item.key)))
    : [];
  const one = offCards.length === 1;
  const named = listed(offCards.map((item) => `${isUseCase(item) ? "use case " : ""}"${item.name}"`));
  const useCases = offCards.filter(isUseCase).length;
  const lister = useCases === 0
    ? `Salesforce lists ${one ? "it" : "them"} open`
    : useCases === offCards.length
      ? `the team sized ${one ? "it" : "them"}`
      : `Salesforce lists the ${offCards.length - useCases === 1 ? "opportunity" : "opportunities"} open and the team sized the ${useCases === 1 ? "use case" : "use cases"}`;
  return [{
    item: offCards.length ? `Snapshot: other pipeline activity is $0 (${named} valued at $0)` : "Snapshot: other pipeline activity is $0",
    why: "team only",
    ownerRole: AE,
    nextStep: offCards.length
      ? `Confirm that ${named} ${one ? "adds" : "add"} no entitlement value beyond the pursuit cards: ${lister}, but ${one ? "its" : "their"} lines draw on no priced row the account holds (never-bought products, platform tiers, $0 rows or no lines). If ${one ? "it" : "they"} will consume entitlement, enter the other pipeline activity in whole USD.`
      : "Confirm there is no other pipeline activity beyond the pursuit cards (no further open opportunity or sized use case), or enter its entitlement value in whole USD.",
    tab: "Snapshot",
    blocking: false,
  }];
}

/** A field with no name of its own, from its pointer: container segments and the tab's own name left out. */
function humanize(generic, tab) {
  const segments = generic.split("/").slice(1);
  const words = segments
    .filter((segment, at) => segment !== "*" && !(at > 0 && segments[at + 1] === "*"))
    .map((segment) => segment.replace(/([a-z])(\d+)(?=[A-Z])/g, "$1 $2").replace(/([a-z0-9])([A-Z])/g, "$1 $2").toLowerCase());
  if (words.length > 1 && words[0].replace(/ /g, "") === normalize(tab).replace(/ /g, "")) words.shift();
  const text = words.join(" ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** How a group of inventory rows of one field reads: the records it names, or how many there are. */
function records(rows) {
  const labels = [...new Set(rows.map((row) => row.label).filter(Boolean))];
  if (labels.length) return ` [${labels.length > 6 ? `${labels.slice(0, 5).join("; ")}; +${labels.length - 5} more` : labels.join("; ")}]`;
  return rows.length > 1 ? ` (x${rows.length})` : "";
}

/** The document row and its group an inventory row for a consumption row's field points at, when the document has them. */
function documentRowAt(document, pointer) {
  const [, groupAt, rowAt] = CONSUMPTION_ROW_POINTER.exec(pointer) ?? [];
  if (groupAt === undefined) return {};
  const group = document.consumptionPlan?.groups?.[Number(groupAt)];
  const row = group?.rows?.[Number(rowAt)];
  return isRecord(row) ? { group, row } : {};
}

/**
 * How an item names a field of a use-case record, and its next step: "Use case <field>", and the team's own tracker
 * wherever the opportunity's step reads from Salesforce. Null for a field that is not a record's own.
 */
function useCaseRule(generic, rule) {
  const [, field] = OPPORTUNITY_FIELD.exec(generic) ?? [];
  if (!field) return null;
  const name = field === "key" ? "Use case key" : (FIELD_NAMES.get(generic) ?? humanize(generic, "")).replace(/^Opportunity /, "Use case ");
  return { name, ownerRole: rule.ownerRole, nextStep: USE_CASE_STEPS[field] ?? (/Salesforce/.test(rule.nextStep) ? USE_CASE_STEP : rule.nextStep) };
}

function inventoryItems(inventory, document, explained, telemetry, kinds, name, useCaseKeys = new Set()) {
  const items = [];
  const grouped = new Map();
  // A field of a use-case record (its key one of the plan's use cases', as the app compares keys) is an item of its own.
  const ofUseCase = (entry) => {
    const [, at] = OPPORTUNITY_RECORD.exec(typeof entry.pointer === "string" ? entry.pointer : "") ?? [];
    const record = at === undefined ? undefined : document.pipelineOpportunities?.[Number(at)];
    return isRecord(record) && normalizedKey(record.key) !== "" && useCaseKeys.has(normalizedKey(record.key));
  };
  // A field of a consumption row is labelled by its offering; a product two rows share is told apart by the group.
  const labelled = (entry) => {
    const { group, row } = documentRowAt(document, typeof entry.pointer === "string" ? entry.pointer : "");
    return row && entry.label && fold(entry.label) === fold(rowLabel(row)) ? { ...entry, label: name(group?.element, entry.label) } : entry;
  };
  inventory.forEach((entry, index) => {
    if (!isRecord(entry) || typeof entry.generic !== "string" || typeof entry.tab !== "string") {
      throw new GapListError(`inventory[${index}] is not a row of gap-inventory.mjs --json (it needs a "generic" pointer and a "tab")`);
    }
    if (entry.who === "skip" || ((entry.tab === NO_TAB || isUndrawn(entry.generic)) && !entry.blocks)) return;
    if (!entry.blocks && PROGRAM_CLOCK.test(entry.generic) && clockPlacedByDates(document)) return;
    if (!entry.blocks && entry.generic === PIPELINE_DRIVER && isNotAdopted(document, entry.pointer)) return;
    if (entry.generic === CONSUMED) {
      const { group, row } = documentRowAt(document, typeof entry.pointer === "string" ? entry.pointer : "");
      // A platform tier is granted, not consumed; a figure the plan already explains is listed once.
      const kind = documentRowKind(kinds, group, row);
      if (group && normalize(kind) === PLATFORM_CATEGORY) return;
      if (row && explained.has(row)) return;
      const { why, nextStep } = unmeasured(kind, telemetry);
      items.push({
        item: `Consumed to date: ${(row && name(group?.element, rowLabel(row))) || entry.label || "a consumption row"}`,
        why,
        ownerRole: consumedOwner(kind),
        nextStep,
        tab: entry.tab,
        blocking: Boolean(entry.blocks),
      });
      return;
    }
    const group = `${entry.generic}${ofUseCase(entry) && OPPORTUNITY_FIELD.test(entry.generic) ? "#useCase" : ""}`;
    if (!grouped.has(group)) grouped.set(group, []);
    grouped.get(group).push(labelled(entry));
  });

  for (const [group, rows] of grouped) {
    const [first] = rows;
    const generic = first.generic;
    const opportunityRule = OWNER_ROLES[generic] ?? OWNER_ROLES["*"];
    const useCase = group.endsWith("#useCase") ? useCaseRule(generic, opportunityRule) : null;
    const rule = useCase ?? opportunityRule;
    const blocking = rows.some((row) => row.blocks);
    const needs = [...new Set(rows.flatMap((row) => (Array.isArray(row.recordGating) ? row.recordGating : [])))];
    items.push({
      item: `${first.tab}: ${useCase?.name ?? FIELD_NAMES.get(generic) ?? humanize(generic, first.tab)}${records(rows)}${first.kind === "no records" ? " (no records)" : ""}${blocking ? " (required to publish)" : ""}`,
      why: first.who === "evidence" ? "no source" : "team only",
      ownerRole: rule.ownerRole,
      nextStep: needs.length ? `${rule.nextStep} Each record also needs: ${needs.join(", ")}.` : rule.nextStep,
      tab: first.tab,
      blocking,
    });
  }
  return items;
}

/** The lines `pipeline.mjs findings --conflicts` writes (`{ conflicts: [...] }`), or just the list of them. */
function readConflicts(conflicts) {
  if (conflicts === undefined || conflicts === null) return [];
  const lines = Array.isArray(conflicts) ? conflicts : conflicts.conflicts;
  if (!Array.isArray(lines) || lines.some((line) => typeof line !== "string")) {
    throw new GapListError('conflicts must be a list of lines, or { "conflicts": [...] } as pipeline.mjs --conflicts writes it');
  }
  return [...new Set(lines.map((line) => line.trim()).filter(Boolean))];
}

/**
 * Every remaining blank of a Day 2 draft, as items blocking ones first and then by tab.
 *   plan       the consumption plan file the draft was built from
 *   document   the final Day 2 document
 *   inventory  the rows `gap-inventory.mjs <document> --json` prints
 *   conflicts  the lines `pipeline.mjs findings --conflicts` wrote ({ conflicts: [...] } or the list)
 */
export function gapList({ plan, document, inventory, conflicts } = {}) {
  if (!isRecord(plan)) throw new GapListError("plan must be the consumption plan object");
  if (document !== undefined && !isRecord(document)) throw new GapListError("document must be a Day 2 document object");
  if (inventory !== undefined && !Array.isArray(inventory)) throw new GapListError("inventory must be the array gap-inventory.mjs --json prints");
  const draft = document ?? {};
  const telemetry = readTelemetry(plan);
  const located = locateDocumentRows(plan, draft);
  // A schema 1.11 draft runs no pipeline stage and has no Snapshot: only its rows and the inventory apply.
  const snapshot = !beforeSnapshot(draft);
  const pipeline = snapshot ? readPlanPipeline(plan) : null;
  const useCaseKeys = useCaseKeysOf(pipeline);
  const name = rowNamer(plan, draft);
  const { items: consumption, explained } = consumptionItems(plan, draft, located, telemetry, name, { snapshot });

  const items = [
    ...consumption,
    ...unlicensedItems(plan, located, name, snapshot ? "Renewal Test" : "Consumption Plan"),
    ...(snapshot ? pursuitItems(draft, pipeline, plan.asOf) : []),
    ...(snapshot ? overdrawnItems(draft, name, useCaseKeys) : []),
    ...startedItems(pipeline, plan.asOf),
    ...pipelineItems(pipeline),
    ...conflictItems(readConflicts(conflicts)),
    ...(snapshot ? otherActivityItems(plan, draft, pipeline) : []),
    ...inventoryItems(inventory ?? [], draft, explained, telemetry, documentRowKinds(located), name, useCaseKeys),
  ];
  const rank = (tab) => {
    const at = TAB_ORDER.indexOf(tab);
    return at >= 0 ? at : TAB_ORDER.length - 1.5;
  };
  // Array.prototype.sort is stable, so items of one tab keep the order they were found in.
  items.sort((a, b) => Number(b.blocking) - Number(a.blocking) || rank(a.tab) - rank(b.tab));
  return items.map(({ item, why, ownerRole, nextStep }) => ({ item, why, ownerRole, nextStep }));
}

/** A table cell: one line, with any pipe escaped so a "<category>|<product>" name keeps its column. */
const cell = (text) => String(text ?? "").replace(/\s*\n\s*/g, " ").replace(/\|/g, "\\|").trim();

/** The list as the hand-off report's table. */
export function toMarkdown(items) {
  const rows = items.map(({ item, why, ownerRole, nextStep }) => `| ${cell(item)} | ${cell(why)} | ${cell(ownerRole)} | ${cell(nextStep)} |`);
  const table = ["| Missing | Why | Owner | Next step |", "| --- | --- | --- | --- |", ...rows].join("\n");
  return items.length ? `${table}\n` : `${table}\n\nNo missing information remains.\n`;
}

if (isMain(import.meta.url)) {
  const args = process.argv.slice(2);
  const optAll = (name) => args.flatMap((arg, index) => (arg === name && args[index + 1] !== undefined && !args[index + 1].startsWith("--") ? [args[index + 1]] : []));
  const opt = (name) => optAll(name)[0];
  const [planPath] = args;
  const documentPath = opt("--document");
  const inventoryPath = opt("--inventory");
  const out = opt("--out");
  const markdown = opt("--markdown");
  if (!planPath || planPath.startsWith("--") || !documentPath || !inventoryPath || !(out || markdown)) {
    console.error("usage: gap-list.mjs <plan.json> --document <final.day2.json> --inventory <inventory.json> [--conflicts <conflicts.json> ...] (--out <gaps.json> | --markdown <gaps.md>)");
    process.exit(2);
  }
  try {
    const plan = JSON.parse(readFileSync(planPath, "utf8"));
    const document = JSON.parse(readFileSync(documentPath, "utf8"));
    const inventory = JSON.parse(readFileSync(inventoryPath, "utf8"));
    const conflicts = optAll("--conflicts").flatMap((path) => readConflicts(JSON.parse(readFileSync(path, "utf8"))));
    const gaps = gapList({ plan, document, inventory, conflicts });
    if (out) writeFileSync(out, `${JSON.stringify({ gaps }, null, 2)}\n`);
    if (markdown) writeFileSync(markdown, toMarkdown(gaps));
    const owners = Object.entries(gaps.reduce((count, { ownerRole }) => ({ ...count, [ownerRole]: (count[ownerRole] ?? 0) + 1 }), {}));
    console.log([
      `Wrote ${gaps.length} gap(s) to ${[out, markdown].filter(Boolean).join(" and ")}`,
      ...(owners.length ? [`By owner: ${owners.map(([role, count]) => `${role} ${count}`).join(", ")}`] : []),
    ].join("\n"));
  } catch (error) {
    if (!(error instanceof GapListError || error instanceof PipelineError || error instanceof PlanError)) throw error;
    console.error(`gap-list: ${error.message}`);
    process.exit(1);
  }
}

#!/usr/bin/env node
/**
 * Writes a consumption plan file into the Consumption Plan tab of a Day 2 Review
 * document, merging into an existing draft when one is given.
 *
 * The plan file is the one the workbook is built from, so the workbook and the
 * dashboard cannot disagree. This script only maps and merges. It never derives
 * a figure the app computes (share of ARR, consumed percent, totals), never
 * writes a placeholder, and never lets an empty plan field erase a value the
 * account team already entered. A row it matches keeps its id, label and
 * category; every figure it changes is reported.
 *
 * Usage: node to-day2.mjs <plan.json> (--baseline <doc.day2.json> | --repo <dashboard-repo>)
 *                         --out <file.day2.json> [--report <file.md>]
 */
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { isMain } from "./cli.mjs";
import { resolveForecastWindow } from "./resolve-quarters.mjs";

const QUARTERS = ["q1", "q2", "q3", "q4"];
const PLACEHOLDER = /^(?:tbd|tba|n\/?a|unknown|placeholder|pending)\b/i;
const LICENSING_MODELS = new Set(["", "unlimited", "capped"]);
/** Fields a refresh may update on a matched row. The label and category stay the team's. */
const MERGED_FIELDS = ["unit", "skuCode", "licensingModel", "soldQuantity", "soldArrUsd", "discountPercent", "actualConsumed", "comments"];

export class PlanError extends Error {}

const normalizeName = (value) => String(value ?? "").normalize("NFKC").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const label = (row) => row.offering || row.product || "Unnamed row";

function text(value, where) {
  if (value === undefined || value === null) return "";
  if (typeof value !== "string") throw new PlanError(`${where} must be a string`);
  const trimmed = value.trim();
  if (PLACEHOLDER.test(trimmed)) {
    throw new PlanError(`${where} is placeholder text (${JSON.stringify(trimmed)}); leave it empty instead`);
  }
  return trimmed;
}

function quantity(value, where) {
  if (value === undefined || value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new PlanError(`${where} must be a non-negative number or null`);
  }
  return value;
}

function discount(value, where) {
  if (value === undefined || value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value) || value > 100) {
    throw new PlanError(`${where} must be a number no greater than 100, or null`);
  }
  return value;
}

function isoDate(value) {
  const candidate = typeof value === "string" ? value.trim() : "";
  const date = new Date(`${candidate}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(candidate) || Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== candidate) {
    throw new PlanError(`plan.asOf must be a YYYY-MM-DD date, got ${JSON.stringify(value)}`);
  }
  return candidate;
}

/** Validates one plan row and returns its category and its Day 2 row fields. */
export function planRowToDay2(row, index) {
  const where = `rows[${index}]`;
  const offering = text(row?.product, `${where}.product`);
  if (!offering) throw new PlanError(`${where}.product is required`);
  const licensingModel = text(row.licensingModel, `${where}.licensingModel`);
  if (!LICENSING_MODELS.has(licensingModel)) {
    throw new PlanError(`${where}.licensingModel must be "unlimited", "capped", or empty`);
  }
  const forecast = row.forecastUnits ?? {};
  const soldArrUsd = quantity(row.arrUsd, `${where}.arrUsd`);
  return {
    category: text(row.category, `${where}.category`),
    fields: {
      offering,
      unit: text(row.unit, `${where}.unit`),
      skuCode: text(row.productCode, `${where}.productCode`),
      licensingModel,
      soldQuantity: quantity(row.purchasedQuantity, `${where}.purchasedQuantity`),
      soldArrUsd,
      // A contracted line value is pinned; without one the app prices the row.
      arrSource: soldArrUsd === null ? "pricebook" : "manual",
      discountPercent: discount(row.discountPercent, `${where}.discountPercent`),
      actualConsumed: quantity(row.consumedQuantity, `${where}.consumedQuantity`),
      forecastUnits: Object.fromEntries(
        QUARTERS.map((quarter) => [quarter, quantity(forecast[quarter], `${where}.forecastUnits.${quarter}`)]),
      ),
      comments: text(row.notes, `${where}.notes`),
    },
  };
}

/** Writes a non-empty value, reporting any change to a non-empty one. An empty value writes nothing. */
function setReported(target, key, value, where, report) {
  if (value === null || value === undefined || value === "") return;
  const previous = target[key];
  if (previous === value) return;
  if (previous !== null && previous !== undefined && previous !== "") {
    report.push(`${where}: ${JSON.stringify(previous)} → ${JSON.stringify(value)}.`);
  }
  target[key] = value;
}

/** The first unmatched baseline row with the plan row's SKU, else its name. Removed from the pool. */
function takeMatch(candidates, fields) {
  const bySku = fields.skuCode ? candidates.findIndex(({ row }) => row.skuCode === fields.skuCode) : -1;
  const name = normalizeName(fields.offering);
  const index = bySku >= 0
    ? bySku
    : candidates.findIndex(({ row }) => [row.offering, row.product].some((value) => normalizeName(value) === name));
  return index < 0 ? null : candidates.splice(index, 1)[0];
}

function mergeRow(row, fields, report) {
  for (const key of MERGED_FIELDS) setReported(row, key, fields[key], `${label(row)} ${key}`, report);
  if (fields.soldArrUsd !== null) row.arrSource = "manual";
  row.forecastUnits ??= {};
  for (const quarter of QUARTERS) {
    setReported(row.forecastUnits, quarter, fields.forecastUnits[quarter], `${label(row)} forecastUnits.${quarter}`, report);
  }
}

function groupFor(groups, category) {
  const key = normalizeName(category);
  let group = groups.find((candidate) => normalizeName(candidate.element) === key);
  if (!group) {
    group = { element: category, rows: [] };
    groups.push(group);
  }
  group.rows ??= [];
  return group;
}

function reportDanglingAllocations(document, report) {
  const ids = new Set(document.consumptionPlan.groups.flatMap((group) => group.rows.map((row) => row.id)).filter(Boolean));
  for (const useCase of document.consumptionPlan.primaryUseCases ?? []) {
    for (const allocation of useCase.allocations ?? []) {
      if (allocation.rowId && !ids.has(allocation.rowId)) {
        report.push(`Use case "${useCase.useCases ?? ""}" attributes row ${allocation.rowId}, which is not in the plan.`);
      }
    }
  }
}

/** Fills the account's ARR anchor only from a complete sum, and only when it is empty. */
function anchorArr(document, planRows, report) {
  const values = planRows.map(({ fields }) => fields.soldArrUsd);
  const missing = values.filter((value) => value === null).length;
  if (!values.length || missing) {
    report.push(values.length
      ? `renewalEconomics.currentArrUsd not filled: ${missing} plan row(s) have no ARR, so the total would be short.`
      : "renewalEconomics.currentArrUsd not filled: the plan has no rows.");
    return;
  }
  const total = values.reduce((sum, value) => sum + value, 0);
  const economics = (document.renewalEconomics ??= {});
  const current = economics.currentArrUsd ?? null;
  if (current === null) {
    economics.currentArrUsd = total;
    report.push(`renewalEconomics.currentArrUsd set to ${total}, the sum of the plan's ARR.`);
  } else if (current !== total) {
    report.push(`renewalEconomics.currentArrUsd is ${current}; the plan's ARR sums to ${total}. Left unchanged — reconcile with the account team.`);
  }
}

export function toDay2(plan, baseline) {
  if (!Array.isArray(plan?.rows)) throw new PlanError("plan.rows must be an array");
  const asOf = isoDate(plan.asOf);
  const planRows = plan.rows.map(planRowToDay2);
  const report = [];
  const document = structuredClone(baseline);
  const consumptionPlan = (document.consumptionPlan ??= {});
  const groups = (consumptionPlan.groups ??= []);

  const accountName = text(plan.account?.name, "account.name");
  if (!String(document.customerName ?? "").trim() && accountName) {
    document.customerName = accountName;
    report.push(`customerName set to "${accountName}", the Salesforce account name.`);
  }
  setReported(consumptionPlan, "asOf", asOf, "consumptionPlan.asOf", report);
  setReported(
    consumptionPlan,
    "forecastPeriod",
    resolveForecastWindow(new Date(`${asOf}T00:00:00Z`)).forecastPeriod,
    "consumptionPlan.forecastPeriod",
    report,
  );

  const unmatched = groups.flatMap((group) => (group.rows ??= []).map((row) => ({ group, row })));
  for (const { category, fields } of planRows) {
    const match = takeMatch(unmatched, fields);
    if (match) {
      mergeRow(match.row, fields, report);
      if (category && normalizeName(category) !== normalizeName(match.group.element)) {
        report.push(`${label(match.row)}: kept in category "${match.group.element ?? ""}" (plan says "${category}").`);
      }
    } else {
      groupFor(groups, category).rows.push({ ...fields, forecastUnits: { ...fields.forecastUnits } });
      report.push(`${fields.offering}: added under "${category || "Uncategorized"}".`);
    }
  }
  for (const { row } of unmatched) report.push(`${label(row)}: in the baseline but not in the plan; kept unchanged.`);

  reportDanglingAllocations(document, report);
  anchorArr(document, planRows, report);
  return { document, report };
}

/** The blank template of the schema version a dashboard checkout ships. */
function repoTemplate(repo) {
  const source = readFileSync(path.join(repo, "src/schema/account.ts"), "utf8");
  const version = /^export const SCHEMA_VERSION\s*=\s*"([^"]+)"/m.exec(source)?.[1];
  if (!version) throw new PlanError(`${repo}: src/schema/account.ts declares no exported SCHEMA_VERSION`);
  return JSON.parse(readFileSync(path.join(repo, `src/data/day2-dashboard-template-v${version}.json`), "utf8"));
}

if (isMain(import.meta.url)) {
  const args = process.argv.slice(2);
  const opt = (name) => {
    const index = args.indexOf(name);
    return index >= 0 ? args[index + 1] : undefined;
  };
  const [planPath] = args;
  const baselinePath = opt("--baseline");
  const repo = opt("--repo");
  const out = opt("--out");
  const reportPath = opt("--report");
  if (!planPath || planPath.startsWith("--") || !out || (!baselinePath && !repo)) {
    console.error("usage: to-day2.mjs <plan.json> (--baseline <doc.day2.json> | --repo <dashboard-repo>) --out <file> [--report <file>]");
    process.exit(2);
  }
  try {
    const plan = JSON.parse(readFileSync(planPath, "utf8"));
    const baseline = baselinePath ? JSON.parse(readFileSync(baselinePath, "utf8")) : repoTemplate(repo);
    const { document, report } = toDay2(plan, baseline);
    writeFileSync(out, `${JSON.stringify(document, null, 2)}\n`);
    const lines = [`Wrote ${out}`, ...report.map((line) => `- ${line}`)];
    if (reportPath) writeFileSync(reportPath, `${lines.join("\n")}\n`);
    console.log(lines.join("\n"));
  } catch (error) {
    if (!(error instanceof PlanError)) throw error;
    console.error(`to-day2: ${error.message}`);
    process.exit(1);
  }
}

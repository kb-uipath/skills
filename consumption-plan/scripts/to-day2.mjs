#!/usr/bin/env node
/**
 * Writes a consumption plan file into the Consumption Plan tab of a Day 2 Review
 * document, merging into an existing draft when one is given.
 *
 * The plan file is the one the workbook is built from, so the workbook and the
 * dashboard cannot disagree. This script only maps and merges. It never derives
 * a figure the app computes (share of ARR, consumed percent, totals), never
 * writes a placeholder, and never lets an empty plan field erase a value the
 * account team already entered, with one exception: a row whose consumed figure
 * the plan states as a coverage gap (`consumedBasis: "coverage-gap"`, no figure)
 * has its baseline figure cleared, since a 0 from a deployment the curated layer
 * only partly captures is not a measured zero. A row it matches keeps its id,
 * label and category; every figure it fills, changes or clears is reported.
 *
 * Usage: node to-day2.mjs <plan.json> (--baseline <doc.day2.json> | --repo <dashboard-repo>)
 *                         --out <file.day2.json> [--report <file.md>]
 */
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { isMain } from "./cli.mjs";
import { resolveForecastWindow } from "./resolve-quarters.mjs";

const QUARTERS = ["q1", "q2", "q3", "q4"];
/** Tokens that make any value a placeholder, wherever they start it ("TBD - team to provide"). */
const PLACEHOLDER_PREFIX = /^(?:tbd|tba|tbc|n\/a)\b/i;
/** Words that are a placeholder only when they are the whole value ("Pending" is; "Pending Q3 review" is a note). */
const PLACEHOLDER_WHOLE = /^(?:unknown|pending|placeholder|none|null|n\.?a\.?|to be (?:determined|confirmed)|not (?:available|known|stated)|-+|—+|\?+)$/i;
const LICENSING_MODELS = new Set(["", "unlimited", "capped"]);
/**
 * How a row's consumed figure was measured, or "coverage-gap" when no measurement reaches it (Automation Suite,
 * on-premises, Public Sector cloud): then there is no figure, and a baseline figure is cleared. Plan-file only:
 * the Day 2 row has no field for it.
 */
const CONSUMED_BASES = new Set(["", "telemetry", "statement", "estimate", "coverage-gap"]);
const COVERAGE_GAP = "coverage-gap";
/**
 * What a plan row's optional `kind` may say it is. Plan-file only: the Day 2 row has no field for it. The
 * scripts decide a row's treatment by it, else by its `category`, which in a plan grouped by contract or
 * program is only a label.
 */
const ROW_KINDS = new Set(["", "Users", "Robots", "Platform / Capabilities", "Consumables"]);
/** Fields a refresh may update on a matched row. The label and category stay the team's. */
const MERGED_FIELDS = ["unit", "skuCode", "licensingModel", "soldQuantity", "soldArrUsd", "discountPercent", "actualConsumed", "comments"];

export class PlanError extends Error {}

/**
 * What decides how the scripts treat a row (a platform tier, a user license, the evidence for its consumed
 * figure): its `kind` when it has one, else its category. Every such decision goes through here.
 */
export const kindOrCategory = (kind, category) => (typeof kind === "string" && kind.trim() !== "" ? kind.trim() : category);

const normalizeName = (value) => String(value ?? "").normalize("NFKC").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
/** How apply-findings.mjs compares the names in a ref:row token: trimmed and lower-cased. */
const fold = (value) => String(value ?? "").trim().toLowerCase();
const label = (row) => row.offering || row.product || "Unnamed row";

const isEmpty = (value) => value === null || value === undefined || value === "";

function isPlaceholder(value, { prefix = true } = {}) {
  return PLACEHOLDER_WHOLE.test(value) || (prefix && PLACEHOLDER_PREFIX.test(value));
}

function text(value, where, options) {
  if (value === undefined || value === null) return "";
  if (typeof value !== "string") throw new PlanError(`${where} must be a string`);
  const trimmed = value.trim();
  if (isPlaceholder(trimmed, options)) {
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

function isoDate(value, where = "plan.asOf") {
  const candidate = typeof value === "string" ? value.trim() : "";
  const date = new Date(`${candidate}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(candidate) || Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== candidate) {
    throw new PlanError(`${where} must be a YYYY-MM-DD date, got ${JSON.stringify(value)}`);
  }
  return candidate;
}

/**
 * A plan row's optional `unlicensedInUse: { count, source, asOf }`, checked: the robots (or other units) running on
 * trial or unlicensed keys beyond those purchased, which are not Consumed, as a positive whole count with the source
 * that states it and its date. Null when the row states none. Plan-file only: the Day 2 row has no field for it, so
 * it reaches the team through the gap list.
 */
function planRowUnlicensed(row, where) {
  const value = row?.unlicensedInUse;
  if (value === undefined || value === null) return null;
  if (typeof value !== "object" || Array.isArray(value)) throw new PlanError(`${where} must be an object { count, source, asOf }, or empty`);
  if (!Number.isInteger(value.count) || value.count <= 0) throw new PlanError(`${where}.count must be a positive whole number`);
  const source = text(value.source, `${where}.source`);
  if (!source) throw new PlanError(`${where}.source is required`);
  return { count: value.count, source, asOf: isoDate(value.asOf, `${where}.asOf`) };
}

/** A plan row's `kind`, checked: one of the four product kinds, or "" when the row names none. */
function planRowKind(row, where) {
  const kind = text(row?.kind, `${where}.kind`);
  if (!ROW_KINDS.has(kind)) {
    throw new PlanError(`${where}.kind must be "Users", "Robots", "Platform / Capabilities", "Consumables", or empty`);
  }
  return kind;
}

/**
 * Validates one plan row and returns its category, its kind ("" when it has none), whether it states its consumed
 * figure as a coverage gap, the robots it states run on trial or unlicensed keys (`unlicensedInUse`, null when none),
 * and its Day 2 row fields.
 */
export function planRowToDay2(row, index) {
  const where = `rows[${index}]`;
  const offering = text(row?.product, `${where}.product`);
  if (!offering) throw new PlanError(`${where}.product is required`);
  const licensingModel = text(row.licensingModel, `${where}.licensingModel`);
  if (!LICENSING_MODELS.has(licensingModel)) {
    throw new PlanError(`${where}.licensingModel must be "unlimited", "capped", or empty`);
  }
  // consumedBasis and consumedAsOf are checked here and then dropped: the Day 2
  // row has no such fields (the dashboard's importer would strip them), so the
  // basis reaches the team through `notes`, and a later gap list reads the plan.
  const consumedBasis = text(row.consumedBasis, `${where}.consumedBasis`);
  if (!CONSUMED_BASES.has(consumedBasis)) {
    throw new PlanError(`${where}.consumedBasis must be "telemetry", "statement", "estimate", "coverage-gap", or empty`);
  }
  const consumedAsOf = text(row.consumedAsOf, `${where}.consumedAsOf`);
  if (consumedAsOf) isoDate(consumedAsOf, `${where}.consumedAsOf`);
  const actualConsumed = quantity(row.consumedQuantity, `${where}.consumedQuantity`);
  const coverageGap = consumedBasis === COVERAGE_GAP;
  if (coverageGap && actualConsumed !== null) {
    throw new PlanError(`${where}.consumedQuantity must be empty when consumedBasis is "coverage-gap": a coverage gap has no figure, and a 0 would assert a measured zero`);
  }
  const kind = planRowKind(row, where);
  const unlicensedInUse = planRowUnlicensed(row, `${where}.unlicensedInUse`);
  const comments = text(row.notes, `${where}.notes`);
  if (consumedBasis === "estimate" && actualConsumed !== null && !comments) {
    throw new PlanError(`${where}.notes must state the basis of an estimated consumed figure`);
  }
  const forecast = row.forecastUnits ?? {};
  const soldArrUsd = quantity(row.arrUsd, `${where}.arrUsd`);
  return {
    category: text(row.category, `${where}.category`),
    kind,
    coverageGap,
    unlicensedInUse,
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
      actualConsumed,
      forecastUnits: Object.fromEntries(
        QUARTERS.map((quarter) => [quarter, quantity(forecast[quarter], `${where}.forecastUnits.${quarter}`)]),
      ),
      comments,
    },
  };
}

/**
 * Writes a non-empty value, reporting a change to a non-empty one and the fill of an empty one, so the hand-off
 * shows everything the plan wrote. An empty value writes nothing, and a value already there says nothing.
 */
function setReported(target, key, value, where, report) {
  if (isEmpty(value)) return;
  const previous = target[key];
  if (previous === value) return;
  report.push(isEmpty(previous) ? `${where} filled: ${JSON.stringify(value)}` : `${where}: ${JSON.stringify(previous)} → ${JSON.stringify(value)}.`);
  target[key] = value;
}

/**
 * A refresh measured in a later fiscal quarter re-labels every quarter column, but
 * the baseline's consumption and Q+1-Q+4 figures were measured against the old
 * window. They are not shifted or cleared here -- whether each still holds is a
 * judgment about what it meant -- so the move is reported for the agent to resolve
 * in the plan file.
 */
function reportWindowShift(previousAsOf, asOf, report) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(previousAsOf)) return;
  const previous = new Date(`${previousAsOf}T00:00:00Z`);
  if (Number.isNaN(previous.getTime())) return;
  const before = resolveForecastWindow(previous).currentPeriod;
  const after = resolveForecastWindow(new Date(`${asOf}T00:00:00Z`)).currentPeriod;
  if (before === after) return;
  report.push(`consumptionPlan.asOf moves from ${before} to ${after}: the baseline's actualConsumed and forecastUnits were measured against the old quarter window. Re-express them in the plan file (or clear them) before delivering.`);
}

/**
 * Pairs plan rows with baseline rows. Every SKU is matched across the whole plan
 * before any name is, so a SKU-less plan row cannot take, by name, the row a later
 * plan row's SKU identifies; and a name never pairs two rows whose SKUs disagree.
 * Among rows that share a SKU, or a name, the one already in the plan row's category
 * is taken before the first in document order, so two contracts that sell the same
 * SKUs, or two rows an account carries under one name, are told apart whatever
 * order the baseline lists them in. A row with no match in its own category still
 * takes the first elsewhere. Matched baseline rows leave the pool, which afterwards
 * holds the unmatched ones.
 */
function pairRows(planRows, candidates) {
  const pairs = planRows.map(() => null);
  /** The first candidate that qualifies, preferring one in the plan row's category. */
  const take = (category, qualifies) => {
    const sameCategory = candidates.findIndex((candidate) => qualifies(candidate) && normalizeName(candidate.group.element) === normalizeName(category));
    return sameCategory >= 0 ? sameCategory : candidates.findIndex(qualifies);
  };
  planRows.forEach(({ category, fields }, index) => {
    if (!fields.skuCode) return;
    const at = take(category, ({ row }) => row.skuCode === fields.skuCode);
    if (at >= 0) pairs[index] = candidates.splice(at, 1)[0];
  });
  planRows.forEach(({ category, fields }, index) => {
    if (pairs[index]) return;
    const name = normalizeName(fields.offering);
    const at = take(category, ({ row }) => (
      name !== ""
      && !(fields.skuCode && row.skuCode && row.skuCode !== fields.skuCode)
      && [row.offering, row.product].some((value) => normalizeName(value) === name)
    ));
    if (at >= 0) pairs[index] = candidates.splice(at, 1)[0];
  });
  return pairs;
}

/**
 * Merges a plan row's fields into the baseline row it matched. A coverage gap is the one case where the plan
 * erases a figure: it has none to write, and the baseline's (a 0 above all) would pass for a measurement.
 */
function mergeRow(row, fields, report, { coverageGap = false } = {}) {
  for (const key of MERGED_FIELDS) setReported(row, key, fields[key], `${label(row)} ${key}`, report);
  if (coverageGap && !isEmpty(row.actualConsumed)) {
    report.push(`cleared ${label(row)} actualConsumed ${row.actualConsumed}: coverage gap`);
    row.actualConsumed = null;
  }
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

  const accountName = text(plan.account?.name, "account.name", { prefix: false });
  if (!String(document.customerName ?? "").trim() && accountName) {
    document.customerName = accountName;
    report.push(`customerName set to "${accountName}", the Salesforce account name.`);
  }
  reportWindowShift(typeof consumptionPlan.asOf === "string" ? consumptionPlan.asOf.trim() : "", asOf, report);
  setReported(consumptionPlan, "asOf", asOf, "consumptionPlan.asOf", report);
  setReported(
    consumptionPlan,
    "forecastPeriod",
    resolveForecastWindow(new Date(`${asOf}T00:00:00Z`)).forecastPeriod,
    "consumptionPlan.forecastPeriod",
    report,
  );

  const unmatched = groups.flatMap((group) => (group.rows ??= []).map((row) => ({ group, row })));
  const pairs = pairRows(planRows, unmatched);
  planRows.forEach(({ category, coverageGap, fields }, index) => {
    const match = pairs[index];
    if (match) {
      mergeRow(match.row, fields, report, { coverageGap });
      if (category && normalizeName(category) !== normalizeName(match.group.element)) {
        report.push(`${label(match.row)}: kept in category "${match.group.element ?? ""}" (plan says "${category}").`);
      }
    } else {
      groupFor(groups, category).rows.push({ ...fields, forecastUnits: { ...fields.forecastUnits } });
      report.push(`${fields.offering}: added under "${category || "Uncategorized"}".`);
    }
  });
  for (const { row } of unmatched) report.push(`${label(row)}: in the baseline but not in the plan; kept unchanged.`);

  reportDanglingAllocations(document, report);
  anchorArr(document, planRows, report);
  return { document, report };
}

/**
 * Each plan row's key: the string a pipeline line, a demand figure and a finding use
 * to name it. It is the row's product, or "<category>|<product>" when another plan
 * row carries that product (compared ignoring case and surrounding spaces). `unique`
 * is false when another row has the very same key, which then names neither of them.
 * `index` is the row's place in `plan.rows`; a row with no product has no key. `kind` is the
 * row's checked `kind` ("" when it names none); `kindOrCategory(kind, category)` says what the row is.
 */
export function planRowKeys(plan) {
  const rows = (Array.isArray(plan?.rows) ? plan.rows : [])
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => typeof row?.product === "string" && row.product.trim() !== "");
  const perProduct = new Map();
  for (const { row } of rows) perProduct.set(fold(row.product), (perProduct.get(fold(row.product)) ?? 0) + 1);
  const entries = rows.map(({ row, index }) => {
    const product = row.product.trim();
    const category = typeof row.category === "string" ? row.category.trim() : "";
    const shared = perProduct.get(fold(product)) > 1;
    return { row, index, product, category, kind: planRowKind(row, `rows[${index}]`), shared, key: shared ? `${category}|${product}` : product };
  });
  const perKey = new Map();
  for (const { key } of entries) perKey.set(fold(key), (perKey.get(fold(key)) ?? 0) + 1);
  return entries.map((entry) => ({ ...entry, unique: perKey.get(fold(entry.key)) === 1 }));
}

/**
 * Where each plan row sits in a document the plan was merged into, keyed by
 * `planRowKeys`: its ref:row token, its id (empty until the document has one) and
 * the row itself. The rows are paired the way `toDay2` paired them. A token names
 * the offering alone, or "<category>|<offering>" when two rows of the document share
 * the offering, the form apply-findings.mjs resolves. A plan row with no row in the
 * document, or one no token can name uniquely (no offering, a "|" in a name, two
 * rows of one category with one offering), is left out. Each entry also carries the category of the group the
 * row sits in and the plan row's `kind` ("" when it names none), since a document row has only its group's
 * category to say what it is.
 */
export function locateDocumentRows(plan, document) {
  if (!Array.isArray(plan?.rows)) throw new PlanError("plan.rows must be an array");
  const planRows = plan.rows.map(planRowToDay2);
  const groups = Array.isArray(document?.consumptionPlan?.groups) ? document.consumptionPlan.groups : [];
  const candidates = groups.flatMap((group) => (Array.isArray(group?.rows) ? group.rows : []).map((row) => ({ group, row })));
  const documentRows = [...candidates];
  const pairs = pairRows(planRows, candidates);
  const located = new Map();
  for (const { index, key, unique } of planRowKeys(plan)) {
    const pair = pairs[index];
    if (!pair || !unique) continue;
    const offering = typeof pair.row.offering === "string" ? pair.row.offering : "";
    const category = typeof pair.group.element === "string" ? pair.group.element : "";
    if (!offering.trim() || offering.includes("|") || category.includes("|")) continue;
    const sharing = documentRows.filter((candidate) => fold(candidate.row.offering) === fold(offering));
    const byCategory = sharing.filter((candidate) => fold(candidate.group.element) === fold(category));
    if (sharing.length > 1 && byCategory.length !== 1) continue;
    located.set(key, {
      token: sharing.length > 1 ? `ref:row:${category}|${offering}` : `ref:row:${offering}`,
      id: typeof pair.row.id === "string" ? pair.row.id : "",
      row: pair.row,
      category,
      kind: planRows[index].kind,
    });
  }
  return located;
}

/** The ref:row token of each plan row in a document the plan was merged into, keyed by `planRowKeys`. */
export function locatePlanRows(plan, document) {
  return new Map([...locateDocumentRows(plan, document)].map(([key, { token }]) => [key, token]));
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

#!/usr/bin/env node
/**
 * Reads the pipeline section of a consumption plan file, turns the account's
 * open opportunities and team-sized use cases, and the team's quarterly forecasts,
 * into stated demand, and turns that into findings for enrich-day2-dashboard's
 * apply-findings.mjs.
 *
 * The plan file carries `contract`, `pipeline.opportunities[]` and, optionally,
 * `pipeline.useCases[]` (pursuits the team sized in its own workbook or deck, with no
 * Salesforce opportunity), each with its product lines already decoded to units and
 * mapped to a plan row. Reading and counting never decodes a quantity, and an
 * opportunity's own dollar amount is not demand. The one price used is a plan row's own
 * contracted unit price (ARR over purchased quantity), to value the pipeline activity the
 * Snapshot does not show.
 *
 * The team's forecast wins. When a plan row's `forecastUnits` set every quarter a window
 * counts (q1 and q2 for +6 months, q1 to q4 for +12, each only when it starts before the
 * contract's renewal date), that window's demand is the forecast: the quarters' sum for a
 * consumable, the busiest quarter less the consumed figure for seats, robots and every other
 * consumed row. A window the forecast does not cover falls back to the rule below. The
 * opportunities and use cases landing in the window still name the row's driver.
 *
 * The rule: a non-renewal opportunity that has not gone stale (close date on or
 * after the plan's `asOf`) counts its line units toward +12-month demand when it
 * closes within 12 months of `asOf`, and also toward +6-month demand when it
 * closes within 6 months. Both windows include their last day. A line with no
 * plan row, and a line on a platform tier or plan bundle, add nothing. A line on a
 * consumed row with no decoded units withholds that row's figure in each window it
 * closes in (and the other pipeline activity it would be part of, and a use case's
 * draw): a sum without it would understate the row while looking complete. A row is a
 * platform tier by its `kind` when it has one, else by its category (in a plan grouped by
 * contract the category is only a label, so such a plan sets `kind` on every row).
 *
 * An opportunity never draws on today's consumption rows, whatever its stage or close date: its
 * product lines are new entitlement the customer is buying, and a pursuit card's draw is use of the
 * entitlement the account already holds. So no opportunity gets a `/snapshot/pursuits` draw; its
 * lines still give its record, the Renewal Test's demand and other pipeline activity.
 *
 * A use case is a pursuit keyed by its slug: a record in the document ($0 estimated iARR when
 * its source states no amount: it draws on existing entitlement), a draw on the rows it sizes
 * unless it starts more than 12 months after `asOf` (it adds nothing in the window then; with no
 * start date it draws), and other pipeline activity when the cards do not show it. It adds demand
 * only when it states a start date from `asOf` on, which times it as a close date does; one that
 * started before `asOf` adds none, since its use is already in the row's consumed figure.
 *
 * A line names its plan row by product, or by "<category>|<product>", which is
 * required when more than one plan row carries the product. Demand, prices and
 * findings key such a row by that category|product string, and any other row by
 * its product (`planRowKeys` in to-day2.mjs).
 *
 * Findings never overwrite what the account team has done. A derived value is
 * written where the document has none, unless `plan.pipeline.written` says this plan
 * wrote one there, which the team has since cleared; left alone where it already says
 * the same; refreshed (with a stated reason) where the document still holds what this
 * plan last wrote; and otherwise kept, with a line in `conflicts` saying what
 * Salesforce, the use case or the team's forecast now shows. A record this plan added
 * that the team deleted (an opportunity or use case, a pursuit card, one of its draw
 * lines, a renewal-test row) is not
 * added again, and a line says so. The contract dates and an opportunity's stage and
 * amount are Salesforce's to say, so they replace the document's; its name follows the
 * refresh rule, so a name the team shortened stands. The owner, the motions, the next
 * gate, the top pursuits and every status, confidence or card status a person judges
 * are never written.
 *
 * An opportunity is found in the document by its Salesforce id, its record's `key`, and a use case
 * by its own key. The app keys a record the team adds as "", so one of the same name with no key is
 * claimed by setting its key; one of the same name keyed otherwise gets no second record, and a line
 * asks the account executive to re-key it.
 *
 * What has left the plan is reported, never cleared. When the plan has written values for an
 * opportunity that is no longer open in it or a use case that is no longer in it, for a draw on a
 * row a use case no longer sizes (a line removed or moved to another row), for the draws of a use
 * case that now starts more than 12 months out (which draws nothing), for the draws an earlier run
 * wrote for an open opportunity that its card still holds (this plan no longer draws for
 * opportunities), or for a renewal-test row no open opportunity drives any more, a line in
 * `conflicts` says so: the card, draws and demand remain in the document for the account executive
 * to confirm and close or remove in the app.
 *
 * Usage: node pipeline.mjs findings <plan.json> --document <day2.json> --stage numbers|final
 *                          (--out <findings.json> | --record) [--conflicts <conflicts.json>]
 *   numbers  contract dates, opportunity and use-case records, use-case pursuit draws and renewal-test demand
 *   final    the other pipeline activity, once the numbers stage is in the document (the
 *            cards the app shows depend on the opportunities it holds)
 *   --out    writes the findings for apply-findings.mjs
 *   --record writes what the plan now has in the document into plan.pipeline.written. Run it
 *            after apply-findings.mjs has succeeded, with --document set to the document it
 *            wrote: every value then already matches, so each is recorded. It refuses, and
 *            leaves the plan alone, while any finding is still unapplied. --out is optional
 *            with it.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { isMain } from "./cli.mjs";
import { resolveForecastWindow } from "./resolve-quarters.mjs";
import { PlanError, kindOrCategory, locateDocumentRows, planRowKeys } from "./to-day2.mjs";

/** Tokens that make any value a placeholder, wherever they start it. Mirrors to-day2.mjs. */
const PLACEHOLDER_PREFIX = /^(?:tbd|tba|tbc|n\/a)\b/i;
/** Words that are a placeholder only when they are the whole value. Mirrors to-day2.mjs. */
const PLACEHOLDER_WHOLE = /^(?:unknown|pending|placeholder|none|null|n\.?a\.?|to be (?:determined|confirmed)|not (?:available|known|stated)|-+|—+|\?+)$/i;
/** A plan row of this kind (its `kind`, else its category) is a platform tier or plan bundle: granted, not consumed. */
const PLATFORM_CATEGORY = "platform capabilities";
/** A plan row of this kind is a consumable: its quarterly forecast adds up over a window. Every other consumed row peaks. */
const CONSUMABLE_CATEGORY = "consumables";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const QUARTERS = ["q1", "q2", "q3", "q4"];
/** A use case's key: words of lower-case letters and digits joined by hyphens, as the app's own example key is. */
const USE_CASE_KEY = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
/** The most characters the app's opportunity `key` takes (its field instructions say so). */
const KEY_LIMIT = 80;

export class PipelineError extends Error {}

const normalizeName = (value) => String(value ?? "").normalize("NFKC").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const isRecord = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

function text(value, where) {
  if (value === undefined || value === null) return "";
  if (typeof value !== "string") throw new PipelineError(`${where} must be a string`);
  const trimmed = value.trim();
  if (PLACEHOLDER_WHOLE.test(trimmed) || PLACEHOLDER_PREFIX.test(trimmed)) {
    throw new PipelineError(`${where} is placeholder text (${JSON.stringify(trimmed)}); leave it empty instead`);
  }
  return trimmed;
}

function required(value, where) {
  const result = text(value, where);
  if (!result) throw new PipelineError(`${where} is required`);
  return result;
}

function isoDate(value, where) {
  const candidate = typeof value === "string" ? value.trim() : "";
  const date = new Date(`${candidate}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(candidate) || Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== candidate) {
    throw new PipelineError(`${where} must be a YYYY-MM-DD date, got ${JSON.stringify(value)}`);
  }
  return candidate;
}

/** A date, or "" when the system of record has none. */
const optionalDate = (value, where) => (value === undefined || value === null || value === "" ? "" : isoDate(value, where));

function nonNegative(value, where, { allowNull = false } = {}) {
  if (allowNull && (value === undefined || value === null)) return null;
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new PipelineError(`${where} must be a non-negative number${allowNull ? " or null" : ""}`);
  }
  return value;
}

/** The same day of month `months` later (or earlier), clamped to that month's last day. */
export function addMonths(date, months) {
  const start = isoDate(date, "date");
  if (!Number.isInteger(months)) throw new PipelineError(`months must be a whole number, got ${JSON.stringify(months)}`);
  const [year, month, day] = start.split("-").map(Number);
  const target = year * 12 + (month - 1) + months;
  const targetYear = Math.floor(target / 12);
  const targetMonth = target - targetYear * 12;
  const lastDay = new Date(Date.UTC(targetYear, targetMonth + 1, 0)).getUTCDate();
  const pad = (value, width) => String(value).padStart(width, "0");
  return `${pad(targetYear, 4)}-${pad(targetMonth + 1, 2)}-${pad(Math.min(day, lastDay), 2)}`;
}

/** "Oct 26" for 2026-10-01. */
const monthLabel = (date) => `${MONTHS[Number(date.slice(5, 7)) - 1]} ${date.slice(2, 4)}`;

/** How a name is compared everywhere a plan row is named: trimmed and lower-cased, as apply-findings.mjs does. */
const fold = (value) => String(value ?? "").trim().toLowerCase();

/**
 * How the app compares opportunity keys (`normalizedOpportunityKey`): NFKC, trimmed, en-US lower-cased, hyphens and
 * underscores read as spaces, whitespace collapsed. Two keys that agree this way are one record to the app, which
 * blocks publication on the pair, so every match of a record by its key (a Salesforce id or a use case's key) goes
 * through here.
 */
export const normalizedKey = (value) => String(value ?? "")
  .normalize("NFKC")
  .trim()
  .toLocaleLowerCase("en-US")
  .replace(/[-_]+/g, " ")
  .replace(/\s+/g, " ");

/**
 * The plan rows `name` names: those whose product it is, or else those whose
 * "<category>|<product>" it is. More than one means the name cannot say which.
 */
function matchRows(plan, name) {
  const wanted = typeof name === "string" ? name.trim() : "";
  if (!wanted) return [];
  const entries = planRowKeys(plan);
  const byProduct = entries.filter(({ product }) => fold(product) === fold(wanted));
  if (byProduct.length) return byProduct;
  const bar = wanted.indexOf("|");
  if (bar < 0) return [];
  const category = wanted.slice(0, bar);
  const product = wanted.slice(bar + 1);
  return entries.filter((entry) => fold(entry.category) === fold(category) && fold(entry.product) === fold(product));
}

/**
 * What a line is to the demand rule: "unmapped" (no plan row), "platform" (a tier
 * or bundle the account is granted, never consumed), "unsized" (no decoded units)
 * or "consumption".
 */
function classify(plan, line) {
  const matches = matchRows(plan, line?.row);
  if (matches.length !== 1) return "unmapped";
  if (normalizeName(kindOrCategory(matches[0].kind, matches[0].category)) === PLATFORM_CATEGORY) return "platform";
  return Number.isFinite(line.units) ? "consumption" : "unsized";
}

/** True when the line is mapped to a plan row that is consumed (not a platform tier or bundle) and has units. */
export function isConsumptionLine(plan, line) {
  return classify(plan, line) === "consumption";
}

/** A sum of units that stays unknown (null) once any part of it is. */
const addKnown = (total, units) => (total === null || units === null ? null : total + units);

/**
 * What one pursuit's lines size on each consumed plan row they map to: their units summed, or null
 * when any of its lines on that row is unsized. Unmapped and platform lines size nothing. It is the
 * demand an opportunity or a timed use case adds, and a use case's draw.
 */
function drawnUnits(plan, opportunity) {
  const drawn = new Map();
  for (const line of opportunity.lines) {
    const kind = classify(plan, line);
    if (kind === "consumption" || kind === "unsized") {
      drawn.set(line.row, addKnown(drawn.get(line.row) ?? 0, kind === "unsized" ? null : line.units));
    }
  }
  return drawn;
}

function readContract(contract) {
  if (!isRecord(contract)) throw new PipelineError("plan.contract must be an object");
  return {
    contractNumber: text(contract.contractNumber, "contract.contractNumber"),
    startDate: optionalDate(contract.startDate, "contract.startDate"),
    renewalDate: optionalDate(contract.renewalDate, "contract.renewalDate"),
  };
}

/** The key of the plan row a line's `row` names, or "" when it names none. Refused when it names no plan row, or more than one. */
function readRow(plan, line, where) {
  const named = text(line.row, `${where}.row`);
  if (!named) return "";
  const matches = matchRows(plan, named);
  if (!matches.length) {
    throw new PipelineError(`${where}.row ${JSON.stringify(named)} is not a plan row's product or category|product; use "" when the account has no such row`);
  }
  if (matches.length > 1) {
    throw new PipelineError(matches.every(({ key }) => key === matches[0].key)
      ? `${where}.row ${JSON.stringify(named)} names more than one plan row (they share a category and a product), so it cannot say which row the line belongs to`
      : `${where}.row ${JSON.stringify(named)} names a product more than one plan row carries, so it cannot say which row the line belongs to; name the row "<category>|<product>"`);
  }
  return matches[0].key;
}

function readLine(plan, line, where) {
  if (!isRecord(line)) throw new PipelineError(`${where} must be an object`);
  const row = readRow(plan, line, where);
  return {
    product: required(line.product, `${where}.product`),
    productCode: text(line.productCode, `${where}.productCode`),
    quantity: nonNegative(line.quantity, `${where}.quantity`),
    units: nonNegative(line.units, `${where}.units`, { allowNull: true }),
    row,
  };
}

/** A use case's line: the product the team sized, its units (null when the team gave none) and its plan row, as an opportunity line's. */
function readUseCaseLine(plan, line, where) {
  if (!isRecord(line)) throw new PipelineError(`${where} must be an object`);
  const row = readRow(plan, line, where);
  return {
    product: required(line.product, `${where}.product`),
    units: nonNegative(line.units, `${where}.units`, { allowNull: true }),
    row,
  };
}

/**
 * A pursuit the team sized in its own workbook or deck, with no Salesforce opportunity. Its `key` is the stable slug its
 * name gives, which keys its record in the document; `source` and `asOf` name the workbook or deck and its date;
 * `startDate`, when the team gives one, times its demand as a close date times an opportunity's; `amountUsd` is the
 * new ARR the source states, if any.
 */
function readUseCase(plan, useCase, index) {
  const where = `pipeline.useCases[${index}]`;
  if (!isRecord(useCase)) throw new PipelineError(`${where} must be an object`);
  const key = required(useCase.key, `${where}.key`);
  if (!USE_CASE_KEY.test(key) || [...key].length > KEY_LIMIT) {
    throw new PipelineError(`${where}.key must be a slug of lower-case letters and digits joined by hyphens, at most ${KEY_LIMIT} characters ("invoice-intake-agent"), got ${JSON.stringify(key)}`);
  }
  if (!Array.isArray(useCase.lines)) throw new PipelineError(`${where}.lines must be an array`);
  const amount = useCase.amountUsd ?? null;
  if (amount !== null && (typeof amount !== "number" || !Number.isFinite(amount) || amount < 0)) {
    throw new PipelineError(`${where}.amountUsd must be a non-negative number or null`);
  }
  return {
    key,
    name: required(useCase.name, `${where}.name`),
    source: required(useCase.source, `${where}.source`),
    asOf: isoDate(useCase.asOf, `${where}.asOf`),
    startDate: optionalDate(useCase.startDate, `${where}.startDate`),
    amountUsd: amount,
    lines: useCase.lines.map((line, at) => readUseCaseLine(plan, line, `${where}.lines[${at}]`)),
  };
}

function readOpportunity(plan, opportunity, index) {
  const where = `pipeline.opportunities[${index}]`;
  if (!isRecord(opportunity)) throw new PipelineError(`${where} must be an object`);
  if (typeof opportunity.isRenewal !== "boolean") throw new PipelineError(`${where}.isRenewal must be true or false`);
  if (!Array.isArray(opportunity.lines)) throw new PipelineError(`${where}.lines must be an array`);
  const amount = opportunity.amountUsd ?? null;
  if (amount !== null && (typeof amount !== "number" || !Number.isFinite(amount))) {
    throw new PipelineError(`${where}.amountUsd must be a number or null`);
  }
  return {
    salesforceId: required(opportunity.salesforceId, `${where}.salesforceId`),
    name: required(opportunity.name, `${where}.name`),
    stage: text(opportunity.stage, `${where}.stage`),
    amountUsd: amount,
    closeDate: isoDate(opportunity.closeDate, `${where}.closeDate`),
    lastModifiedDate: isoDate(opportunity.lastModifiedDate, `${where}.lastModifiedDate`),
    isRenewal: opportunity.isRenewal,
    ownerName: text(opportunity.ownerName, `${where}.ownerName`),
    lines: opportunity.lines.map((line, at) => readLine(plan, line, `${where}.lines[${at}]`)),
  };
}

/**
 * Validates and normalizes the plan's `contract`, `pipeline.opportunities` and `pipeline.useCases` (none when the plan
 * has no such list). Salesforce ids are unique, and a use case's key is unique among the use cases and differs from
 * every opportunity's Salesforce id, compared as the app compares keys (`normalizedKey`), since both key records in the
 * same list of the document.
 */
export function readPipeline(plan) {
  if (!Array.isArray(plan?.rows)) throw new PipelineError("plan.rows must be an array");
  if (!Array.isArray(plan.pipeline?.opportunities)) throw new PipelineError("plan.pipeline.opportunities must be an array");
  const contract = readContract(plan.contract);
  const opportunities = plan.pipeline.opportunities.map((opportunity, index) => readOpportunity(plan, opportunity, index));
  const seen = new Set();
  for (const { salesforceId } of opportunities) {
    if (seen.has(normalizedKey(salesforceId))) throw new PipelineError(`pipeline.opportunities repeats Salesforce id ${salesforceId}`);
    seen.add(normalizedKey(salesforceId));
  }
  const listed = plan.pipeline.useCases ?? [];
  if (!Array.isArray(listed)) throw new PipelineError("plan.pipeline.useCases must be an array when the plan has one");
  const useCases = listed.map((useCase, index) => readUseCase(plan, useCase, index));
  const keys = new Set();
  for (const { key } of useCases) {
    if (keys.has(normalizedKey(key))) throw new PipelineError(`pipeline.useCases repeats key ${key}`);
    if (seen.has(normalizedKey(key))) throw new PipelineError(`pipeline.useCases key ${key} is an opportunity's Salesforce id; give the use case a key of its own`);
    keys.add(normalizedKey(key));
  }
  return { contract, opportunities, useCases };
}

/**
 * The fiscal quarters of the team's forecast (`forecastUnits.q1`..`q4`, q1 being the quarter after the one holding
 * `asOf`) each window counts: q1 and q2 for +6-month demand, all four for +12-month demand, and in both only the
 * quarters that start before the contract's renewal date (a quarter after it is a renewal question, and +12 months
 * always includes the +6-month figure). With no renewal date every quarter counts.
 */
export function forecastWindows(asOf, renewalDate = "") {
  const counted = resolveForecastWindow(new Date(`${isoDate(asOf, "asOf")}T00:00:00Z`)).quarters.slice(1)
    .map(({ start }, at) => ({ quarter: QUARTERS[at], start }))
    .filter(({ start }) => !renewalDate || start < renewalDate)
    .map(({ quarter }) => quarter);
  return { demand6MoUnits: counted.filter((quarter) => quarter === "q1" || quarter === "q2"), demand12MoUnits: counted };
}

/**
 * How a plan row's quarters roll into a window's demand. A consumable's quarters are drawn down, so they add
 * ("cumulative"); seats, robots and every other consumed row hold a standing count, so a window takes its busiest
 * quarter less what is already consumed ("peak"). The plan row carries no rollup basis of its own, so its kind (else
 * its category) decides, as the app's field instructions describe them: unit bundles cumulative, named users and
 * robots peak. A platform tier is granted, not consumed: null.
 */
function rollUp(entry) {
  const kind = normalizeName(kindOrCategory(entry.kind, entry.category));
  if (kind === PLATFORM_CATEGORY) return null;
  return kind === CONSUMABLE_CATEGORY ? "cumulative" : "peak";
}

/**
 * The demand each plan row's team forecast gives, keyed like `planRowKeys`: `{ figures, asOf }`, where `figures`
 * holds a window's figure only when every quarter it counts is set. A peak row's figure is its busiest counted
 * quarter less its consumed figure, never below 0, and null when it has no consumed figure. The demand is dated by the
 * row's `consumedAsOf`, else the plan's `asOf`. `unmeasured` lists the windows a missing consumed figure leaves with
 * no figure, and `floored` each window whose busiest quarter is at or below the consumed figure, so the roll-up gives
 * 0 (`{ field, peak, consumed }`); each is there only when it has an entry. A row with no full window, a platform tier
 * and a row no key names alone are left out.
 */
function teamForecasts(plan, asOf, renewalDate) {
  const windows = forecastWindows(asOf, renewalDate);
  const forecasts = new Map();
  for (const entry of planRowKeys(plan)) {
    const basis = rollUp(entry);
    if (!entry.unique || !basis) continue;
    const where = `rows[${entry.index}]`;
    const stated = isRecord(entry.row.forecastUnits) ? entry.row.forecastUnits : {};
    const units = Object.fromEntries(QUARTERS.map((quarter) => [quarter, nonNegative(stated[quarter], `${where}.forecastUnits.${quarter}`, { allowNull: true })]));
    const figures = {};
    const unmeasured = [];
    const floored = [];
    for (const [field, counted] of Object.entries(windows)) {
      if (!counted.length || counted.some((quarter) => units[quarter] === null)) continue;
      const values = counted.map((quarter) => units[quarter]);
      if (basis === "cumulative") {
        figures[field] = values.reduce((total, value) => total + value, 0);
        continue;
      }
      const consumed = nonNegative(entry.row.consumedQuantity, `${where}.consumedQuantity`, { allowNull: true });
      const peak = Math.max(...values);
      figures[field] = consumed === null ? null : Math.max(0, peak - consumed);
      if (consumed === null) unmeasured.push(field);
      else if (peak <= consumed) floored.push({ field, peak, consumed });
    }
    if (!Object.keys(figures).length) continue;
    const consumedAsOf = typeof entry.row.consumedAsOf === "string" ? entry.row.consumedAsOf.trim() : "";
    forecasts.set(entry.key, {
      figures,
      asOf: consumedAsOf ? isoDate(consumedAsOf, `${where}.consumedAsOf`) : asOf,
      ...(unmeasured.length ? { unmeasured } : {}),
      ...(floored.length ? { floored } : {}),
    });
  }
  return forecasts;
}

/**
 * Stated demand per plan row, and the opportunities and lines the rule set aside.
 *
 * Each window of a row takes the team's quarterly forecast when it covers that window (`teamForecasts`). Otherwise it
 * takes the pipeline: the plan's open opportunities, timed by close date, and its use cases that state a start date,
 * timed by it. The opportunities and use cases in the window drive the row either way.
 *
 * `byRow` maps a row's key to `{ demand6MoUnits, demand12MoUnits, drivers, asOf }`, where `asOf` is the latest date of
 * the pipeline that drives it ("" when none does). A pipeline window's figure is null when an unsized line on the row
 * lands in it; the opportunity or use case still drives the row. A row a use case drives also carries
 * `useCaseSources`, each such use case's source; a row whose team forecast gives a window carries
 * `teamForecast: { windows, asOf }`, the windows it gives and their date, with `unmeasured` and `floored` as
 * `teamForecasts` gives them.
 *
 * `open` is every non-renewal opportunity closing on or after `asOf`, beyond-window ones included, and `useCases`
 * every use case, timed or not. Their unmapped and unsized lines are reported (a pursuit outside the window can still
 * need them); a renewal's or a stale opportunity's are not. `beyondWindow` holds the open opportunities closing, and
 * the use cases starting, more than 12 months after `asOf` (they add no demand, and such a use case draws nothing),
 * and `started` the use cases whose start date is before `asOf` (their use is already in the consumed figure, so they
 * add no demand).
 */
export function pipelineDemand(plan) {
  const { contract, opportunities, useCases } = readPipeline(plan);
  const asOf = isoDate(plan.asOf, "plan.asOf");
  const sixMonths = addMonths(asOf, 6);
  const twelveMonths = addMonths(asOf, 12);
  const result = { byRow: new Map(), open: [], stale: [], renewals: [], beyondWindow: [], started: [], unmapped: [], unsized: [], useCases };

  for (const opportunity of opportunities) {
    if (opportunity.isRenewal) result.renewals.push(opportunity);
    else if (opportunity.closeDate < asOf) result.stale.push(opportunity);
    else {
      result.open.push(opportunity);
      if (opportunity.closeDate > twelveMonths) result.beyondWindow.push(opportunity);
    }
  }

  for (const useCase of useCases) {
    if (useCase.startDate > twelveMonths) result.beyondWindow.push(useCase);
    else if (useCase.startDate !== "" && useCase.startDate < asOf) result.started.push(useCase);
  }

  for (const opportunity of [...result.open, ...useCases]) {
    for (const line of opportunity.lines) {
      const kind = classify(plan, line);
      if (kind === "unmapped") result.unmapped.push({ opportunity, line });
      else if (kind === "unsized") result.unsized.push({ opportunity, line });
    }
  }

  const inWindow = [
    ...result.open
      .filter((opportunity) => opportunity.closeDate <= twelveMonths)
      .map((item) => ({ item, lands: item.closeDate, asOf: item.lastModifiedDate })),
    ...useCases
      .filter(({ startDate }) => startDate !== "" && startDate >= asOf && startDate <= twelveMonths)
      .map((item) => ({ item, lands: item.startDate, asOf: item.asOf, useCase: true })),
  ].sort((a, b) => (a.lands < b.lands ? -1 : a.lands > b.lands ? 1 : 0));
  for (const { item, lands, asOf: dated, useCase } of inWindow) {
    for (const [row, units] of drawnUnits(plan, item)) {
      let demand = result.byRow.get(row);
      if (!demand) {
        demand = { demand6MoUnits: 0, demand12MoUnits: 0, drivers: [], asOf: "" };
        result.byRow.set(row, demand);
      }
      demand.demand12MoUnits = addKnown(demand.demand12MoUnits, units);
      if (lands <= sixMonths) demand.demand6MoUnits = addKnown(demand.demand6MoUnits, units);
      demand.drivers.push(`${item.name} (${monthLabel(lands)})`);
      if (dated > demand.asOf) demand.asOf = dated;
      if (useCase) (demand.useCaseSources ??= []).push(item.source);
    }
  }

  // The team's forecast wins in each window it covers; a row it covers that nothing in the pipeline sizes has no
  // pipeline figure (null) in the window it leaves.
  for (const [row, { figures, asOf: dated, ...notes }] of teamForecasts(plan, asOf, contract.renewalDate)) {
    let demand = result.byRow.get(row);
    if (!demand) {
      demand = { demand6MoUnits: null, demand12MoUnits: null, drivers: [], asOf: "" };
      result.byRow.set(row, demand);
    }
    Object.assign(demand, figures);
    demand.teamForecast = { windows: Object.keys(figures), asOf: dated, ...notes };
  }
  return result;
}

/**
 * The contracted price of one unit of each plan row, keyed by the row's key (its
 * product, or "<category>|<product>" when another row carries the product): its
 * ARR over its purchased quantity. `null` when the row has no ARR or no positive
 * purchased quantity (or when another row has the very same key, so no one price
 * is the row's); `0` when the row's ARR is zero. Mirrors the app's
 * `rowUnitPriceUsd`: a row is never priced at list.
 */
export function unitPriceByRow(plan) {
  const prices = new Map();
  for (const { key, row, unique } of planRowKeys(plan)) {
    const priced = unique && Number.isFinite(row.arrUsd) && Number.isFinite(row.purchasedQuantity) && row.purchasedQuantity > 0;
    prices.set(key, priced ? row.arrUsd / row.purchasedQuantity : null);
  }
  return prices;
}

/**
 * The `key` of each pursuit the app's Snapshot shows as a card: the named
 * `snapshot.topPursuitIds` that match an opportunity's `id`, in order, or, when
 * none match, the opportunities that are neither Closed Won nor Closed Lost,
 * ranked by `customerValueUsd ?? estimatedIarrUsd ?? 0` (largest first, ties in
 * document order) and cut to `limit`. Mirrors `shownPursuits` and `topPursuits`.
 * The app's import keeps the named ids distinct and capped at the limit before
 * it matches them, so this does too. A document with no snapshot, or no
 * `topPursuitIds`, has no named pursuits and gets the ranking; one with no
 * opportunities shows none.
 */
export function shownPursuitKeys(document, limit = 3) {
  return shownPursuits(document, limit).map((item) => (typeof item.key === "string" ? item.key : ""));
}

/** The records of the pursuits the app's Snapshot shows as cards, in card order, as `shownPursuitKeys` chooses them. */
export function shownPursuits(document, limit = 3) {
  if (!Array.isArray(document?.pipelineOpportunities)) return [];
  const opportunities = document.pipelineOpportunities.filter(isRecord);
  const namedIds = Array.isArray(document.snapshot?.topPursuitIds) ? document.snapshot.topPursuitIds : [];
  const named = [...new Set(namedIds.filter((id) => typeof id === "string"))]
    .slice(0, limit)
    .flatMap((id) => opportunities.find((item) => item.id === id) ?? []);
  const rank = (item) => item.customerValueUsd ?? item.estimatedIarrUsd ?? 0;
  const shown = named.length
    ? named
    : opportunities
      .filter((item) => item.status !== "Closed Won" && item.status !== "Closed Lost")
      .sort((left, right) => rank(right) - rank(left))
      .slice(0, limit);
  return shown;
}

/**
 * What the account's other pipeline activity is worth: every open opportunity
 * whose Salesforce id is not in `shownKeys`, and every use case whose key is not (keys compared as the app compares them),
 * each sized consumption line priced at its row's contracted unit price.
 * Beyond-window opportunities are open and count, and so does a use case with no start date.
 * An unmapped line, and a line on a platform tier or bundle, add nothing. `usd` is
 * `0` when there is nothing to price, and `null` (a partial sum would understate it
 * while looking complete) when any line on a consumed row has no units, which
 * `unsized` lists, or a sized line's row has no unit price, which `unpriced` lists.
 */
export function otherActivityUsd(plan, shownKeys) {
  const { open, useCases } = pipelineDemand(plan);
  const shown = new Set((shownKeys ?? []).map(normalizedKey));
  const prices = unitPriceByRow(plan);
  let usd = 0;
  const unpriced = [];
  const unsized = [];
  for (const opportunity of [...open, ...useCases]) {
    if (shown.has(normalizedKey(opportunity.salesforceId ?? opportunity.key))) continue;
    for (const line of opportunity.lines) {
      const kind = classify(plan, line);
      if (kind === "unsized") unsized.push({ opportunity, line });
      if (kind !== "consumption") continue;
      const price = prices.get(line.row) ?? null;
      if (price === null) unpriced.push({ opportunity, line });
      else usd += line.units * price;
    }
  }
  return { usd: unpriced.length || unsized.length ? null : usd, unpriced, unsized };
}

// --- Findings --------------------------------------------------------------------------------------

/** The reason a finding gives for replacing the document's value with what Salesforce says. */
const SYSTEM_OF_RECORD = "Salesforce is the system of record";
/** What gives a derived value, as a conflict line ("... now give 5") and a refresh reason ("refreshed from ...") name it. */
const SALESFORCE = { gives: "Salesforce opportunities now give", from: "Salesforce opportunities" };
const USE_CASES = { gives: "team-sized use cases now give", from: "team-sized use cases" };
const SALESFORCE_AND_USE_CASES = { gives: "Salesforce opportunities and team-sized use cases now give", from: "Salesforce opportunities and team-sized use cases" };
const USE_CASE = { gives: "the team-sized use case now gives", from: "the team-sized use case" };
const TEAM_FORECAST = { gives: "the team forecast (forecastUnits) now gives", from: "the team forecast (forecastUnits)" };
const refreshedFrom = (asOf, giver = SALESFORCE) => `refreshed from ${giver.from} as of ${asOf}`;
/** The source of a renewal-test figure the team's quarterly forecast gives. */
const TEAM_FORECAST_SOURCE = "team forecast (forecastUnits)";
/** Why a use case whose source states no amount is $0 of estimated iARR. */
const NO_NEW_ARR = "no amount stated: draws on existing entitlement; no new ARR";
/** The most characters the app's `projectedConsumption` field takes (its field instructions say so). */
const PROJECTED_CONSUMPTION_LIMIT = 64;
const isBlank = (value) => value === null || value === undefined || value === "";
const show = (value) => (typeof value === "number" ? String(value) : JSON.stringify(value));
const sameIds = (left, right) => fold(left) !== "" && fold(left) === fold(right);
/** A list as the text `written` records: its distinct items, sorted, as JSON; empty when it has none. */
const canonicalList = (items) => (Array.isArray(items) && items.length ? JSON.stringify([...new Set(items)].sort()) : "");
const listed = (canonical) => JSON.parse(canonical).join(", ");

/** `plan.pipeline.written`: the value each derived key last held when this plan wrote it (null when it wrote no figure). */
function readWritten(plan) {
  const written = plan.pipeline?.written;
  if (written === undefined || written === null) return {};
  if (!isRecord(written) || Object.values(written).some((value) => value !== null && typeof value !== "number" && typeof value !== "string")) {
    throw new PipelineError("pipeline.written must map each key to the number, text or null this plan last wrote");
  }
  return written;
}

/**
 * The refresh rule's bookkeeping for one run. `decide` says what to do with one
 * derived value of a record the document holds, given what the document holds
 * (`baseline`) and what Salesforce's opportunities now give (`next`, null for no figure):
 *   "write"    the document has nothing there, and this plan never wrote a value there
 *   "skip"     it already says the same (both blank included)
 *   "refresh"  it holds what this plan last wrote (`plan.pipeline.written[key]`), so it is stale, not the team's
 *   "keep"     it holds something else, which is the account team's, or it is blank where this plan
 *              wrote a value, which the team cleared: it stays, and `conflicts` says so (a team value
 *              where Salesforce now gives no figure stays without a line, since nothing disagrees)
 * Every outcome but "keep" puts `next` in `written`, which `--record` stores in the plan.
 * `display` says how a value reads in a conflict line (a list is compared as canonical text), and
 * `giver` what gives `next` (Salesforce's opportunities unless a use case or the team's forecast does).
 *
 * `fresh` records a value of a record this run adds; `wrote` says whether `written` holds a
 * key; `keysOf` lists the keys it holds under a prefix; `settle` marks keys this run leaves
 * alone and has already reported, so `reportDeparted` does not report them again.
 */
function startLedger(plan) {
  const previous = readWritten(plan);
  const written = {};
  const conflicts = [];
  const decided = new Set();
  const wrote = (key) => Object.hasOwn(previous, key);
  const decide = (key, baseline, next, label, display = show, giver = SALESFORCE) => {
    decided.add(key);
    let outcome;
    if (isBlank(baseline)) {
      if (!isBlank(next) && wrote(key) && !isBlank(previous[key])) {
        conflicts.push(`${label}: left blank, as the account team cleared it (this plan wrote ${display(previous[key])}); ${giver.gives} ${display(next)}.`);
        return "keep";
      }
      outcome = isBlank(next) ? "skip" : "write";
    } else if (baseline === next) {
      outcome = "skip";
    } else if (previous[key] === baseline) {
      outcome = "refresh";
    } else {
      if (!isBlank(next)) conflicts.push(`${label}: kept ${display(baseline)}, which this plan did not write; ${giver.gives} ${display(next)}.`);
      return "keep";
    }
    written[key] = next;
    return outcome;
  };
  const fresh = (key, next) => {
    decided.add(key);
    written[key] = next;
  };
  const settle = (keys) => keys.forEach((key) => decided.add(key));
  const keysOf = (prefix) => Object.keys(previous).filter((key) => key.startsWith(prefix));
  return { previous, written, conflicts, decided, decide, fresh, settle, wrote, keysOf };
}

/**
 * `locate(key)` finds the document row of a plan row's key, or says the document was
 * not built from this plan; `keyOfId(id)` is the plan row key of a row id, when it is one.
 */
function rowLocator(plan, document) {
  const located = locateDocumentRows(plan, document);
  const keys = new Map([...located].filter(([, { id }]) => id).map(([key, { id }]) => [fold(id), key]));
  return {
    locate: (key) => {
      const found = located.get(key);
      if (!found) {
        throw new PipelineError(`plan row ${JSON.stringify(key)} has no row in the document that a reference can name; build the document from this plan with to-day2.mjs first`);
      }
      return found;
    },
    keyOfId: (id) => keys.get(fold(id)),
  };
}

/** How the AE is told an opportunity's record, card, draw line or renewal-test row stays removed. */
const REMOVED = "The AE confirms the removal or adds it back in the app.";

/**
 * How the findings name, key, source and date one pursuit: an open opportunity from Salesforce, or a use case the team
 * sized. `id` keys its record in the document (the Salesforce id, or the use case's key); `field(name)` and
 * `draw(row)` are its keys in `written`, under the prefixes `fields` and `draws`.
 */
function pursuitOf(item) {
  if (typeof item.salesforceId === "string") {
    const id = item.salesforceId;
    return {
      item, id, useCase: false, named: `Opportunity "${item.name}" (${id})`, source: `Salesforce Opportunity ${id}`, asOf: item.lastModifiedDate,
      field: (name) => `opportunity:${id}:${name}`, fields: `opportunity:${id}:`, draw: (row) => `draw:${id}:${row}`, draws: `draw:${id}:`, giver: SALESFORCE,
    };
  }
  const id = item.key;
  return {
    item, id, useCase: true, named: `Use case "${item.name}" (${id})`, source: item.source, asOf: item.asOf,
    field: (name) => `useCase:${id}:${name}`, fields: `useCase:${id}:`, draw: (row) => `useCase:${id}:draw:${row}`, draws: `useCase:${id}:draw:`, giver: USE_CASE,
  };
}

/** The keys `written` holds for a pursuit's record, its draws aside. */
const recordKeys = (book, pursuit) => book.keysOf(pursuit.fields).filter((key) => !key.startsWith(pursuit.draws));

/**
 * The document's record of a pursuit: `{ record, index, key }` for the one keyed by its id (an
 * opportunity's Salesforce id, a use case's key, compared as the app compares keys), where `key` is
 * that record's own spelling of it, by which the findings address it (apply-findings.mjs matches keys
 * trimmed and lower-cased, so the plan's spelling could miss it and add the duplicate the app refuses);
 * with `claim: true`, one the team added in the app under the same name (compared as `normalizeName`
 * does) and no key, which this run claims by setting its key; `{}` when there is none, so this run adds
 * one; `{ withheld }`, the line saying why, when no record may be written: one of that name carries
 * another key, or the team deleted the record this plan added. A record keyed to another of the plan's
 * opportunities or use cases is that one's, and one claimed this run is taken.
 */
function matchRecord({ document, book, claimed, planKeys }, pursuit) {
  const records = Array.isArray(document?.pipelineOpportunities) ? document.pipelineOpportunities : [];
  const key = pursuit.id;
  const index = records.findIndex((record) => isRecord(record) && normalizedKey(record.key) !== "" && normalizedKey(record.key) === normalizedKey(key));
  if (index >= 0) return { record: records[index], index, key: typeof records[index].key === "string" ? records[index].key : key };
  const name = normalizeName(pursuit.item.name);
  const sameName = records.flatMap((record, at) => (
    name && isRecord(record) && !claimed.has(at) && !planKeys.has(normalizedKey(record.key)) && normalizeName(record.name) === name ? [{ record, index: at }] : []
  ));
  const unkeyed = sameName.find(({ record }) => normalizedKey(record.key) === "");
  if (unkeyed) {
    claimed.add(unkeyed.index);
    return { ...unkeyed, claim: true };
  }
  if (sameName.length) {
    return { withheld: `${pursuit.named}: the document has a record of that name keyed ${JSON.stringify(sameName[0].record.key)}, so no second record is added. The AE changes its key to ${key} in the app, so the next run fills it.` };
  }
  if (recordKeys(book, pursuit).length) {
    const listed = pursuit.useCase ? "the plan file still lists it" : "Salesforce still lists it open";
    return { withheld: `${pursuit.named}: its record, which this plan added, is no longer in the document, so it is not added again; ${listed}. ${REMOVED}` };
  }
  return {};
}

/** What an opportunity sizes, per row: "AI Units: 400000 units; Unattended Robot: 20 robots". Fits the field, naming the rest as a count. */
function projectedConsumption(plan, opportunity) {
  const entries = new Map(planRowKeys(plan).map((entry) => [entry.key, entry]));
  const units = new Map();
  for (const line of opportunity.lines) {
    if (isConsumptionLine(plan, line)) units.set(line.row, (units.get(line.row) ?? 0) + line.units);
  }
  const parts = [...units].map(([key, total]) => {
    const { product, category, shared, row } = entries.get(key);
    const unit = typeof row.unit === "string" ? row.unit.trim() : "";
    return `${shared ? `${product} (${category})` : product}: ${total}${unit ? ` ${unit}` : ""}`;
  });
  const fits = (value) => [...value].length <= PROJECTED_CONSUMPTION_LIMIT;
  const all = parts.join("; ");
  if (fits(all)) return all;
  for (let count = parts.length - 1; count >= 1; count--) {
    const shorter = `${parts.slice(0, count).join("; ")}; +${parts.length - count} more`;
    if (fits(shorter) || count === 1) return shorter;
  }
  return all;
}

/** The order an opportunity record's fields are written in. */
const RECORD_FIELDS = ["name", "stage", "status", "estimatedIarrUsd", "products", "consumptionRowIds", "projectedConsumption"];

/**
 * A pursuit's record: an opportunity's Salesforce facts, or a use case's own sizing, and what its
 * lines say about the consumption rows. `context` is { plan, document, asOf, locate, keyOfId, book },
 * `pursuit` is `pursuitOf`'s and `match` is `matchRecord`'s; the findings name the record by the
 * document's own key when it has one. A record the team added under this name
 * is claimed first, by a finding setting its key. An opportunity's stage and amount are Salesforce's,
 * so they replace the document's; every other field, the name included, follows the refresh rule,
 * its list fields compared by the plan rows they name and recorded as canonical text. A use case has
 * no stage, and its amount follows the refresh rule too: the amount its source states, or 0 when it
 * states none, since it draws on existing entitlement (that finding says so in its source). The
 * values that need no reason, the ones needing "Salesforce is the system of record" and the ones
 * refreshed come as separate findings, because a finding carries one `supersedes`.
 */
function opportunityFindings({ plan, locate, keyOfId, book, asOf }, pursuit, { record = {}, index, claim, key = pursuit.id }) {
  const { item: opportunity, source } = pursuit;
  const label = (field) => `pipelineOpportunities "${opportunity.name}" ${field}`;
  const rowKeys = [...new Set(opportunity.lines.map((line) => line.row).filter(Boolean))];
  const products = [...new Set(opportunity.lines.map((line) => line.product))];
  const projected = projectedConsumption(plan, opportunity);
  const present = (value) => !isBlank(value) && !(Array.isArray(value) && value.length === 0);
  const fresh = {};
  const system = {};
  const refreshed = {};

  if (!pursuit.useCase) {
    for (const [field, value] of [["stage", opportunity.stage], ["estimatedIarrUsd", opportunity.amountUsd]]) {
      if (!present(value)) continue;
      if (isBlank(record[field])) fresh[field] = value;
      else if (record[field] !== value) system[field] = value;
    }
  }
  const amount = pursuit.useCase ? opportunity.amountUsd ?? 0 : null;
  for (const { field, value, baseline, next, display } of [
    { field: "name", value: opportunity.name, baseline: record.name, next: opportunity.name },
    { field: "status", value: "Open", baseline: record.status, next: "Open" },
    ...(pursuit.useCase ? [{ field: "estimatedIarrUsd", value: amount, baseline: record.estimatedIarrUsd, next: amount }] : []),
    { field: "products", value: products, baseline: canonicalList(record.products), next: canonicalList(products), display: listed },
    {
      field: "consumptionRowIds",
      value: rowKeys.map((rowKey) => locate(rowKey).token),
      baseline: canonicalList(Array.isArray(record.consumptionRowIds) ? record.consumptionRowIds.map((id) => keyOfId(id) ?? id) : []),
      next: canonicalList(rowKeys),
      display: listed,
    },
    { field: "projectedConsumption", value: projected, baseline: record.projectedConsumption, next: projected },
  ]) {
    if (!present(value)) continue;
    const outcome = book.decide(pursuit.field(field), baseline, next, label(field), display, pursuit.giver);
    if (outcome === "write") fresh[field] = value;
    else if (outcome === "refresh") refreshed[field] = value;
  }

  const finding = (group, { supersedes, from = source } = {}) => ({
    op: "add",
    pointer: "/pipelineOpportunities",
    value: { key, ...Object.fromEntries(RECORD_FIELDS.filter((field) => field in group).map((field) => [field, group[field]])) },
    source: from,
    asOf: pursuit.asOf,
    ...(supersedes ? { supersedes } : {}),
  });
  // A use case's $0 needs its basis beside it, so it comes in a finding of its own.
  const unstated = pursuit.useCase && opportunity.amountUsd === null;
  const apart = (group) => {
    if (!unstated || !("estimatedIarrUsd" in group)) return [group, null];
    const { estimatedIarrUsd, ...rest } = group;
    return [rest, { estimatedIarrUsd }];
  };
  const [freshRest, freshZero] = apart(fresh);
  const [refreshedRest, refreshedZero] = apart(refreshed);
  const reason = refreshedFrom(asOf, pursuit.giver);
  const basis = `${source} (${NO_NEW_ARR})`;
  return [
    // The app keys a record the team adds as "", so setting its key fills it; nothing is superseded.
    ...(claim ? [{ op: "set", pointer: `/pipelineOpportunities/${index}/key`, value: pursuit.id, source, asOf: pursuit.asOf }] : []),
    ...(Object.keys(freshRest).length ? [finding(freshRest)] : []),
    ...(Object.keys(system).length ? [finding(system, { supersedes: SYSTEM_OF_RECORD })] : []),
    ...(Object.keys(refreshedRest).length ? [finding(refreshedRest, { supersedes: reason })] : []),
    ...(freshZero ? [finding(freshZero, { from: basis })] : []),
    ...(refreshedZero ? [finding(refreshedZero, { from: basis, supersedes: reason })] : []),
  ];
}

/**
 * A use case's pursuit card: its draw on each consumed row it sizes (no units where a line there is
 * unsized, so the app withholds its Est. rev.). `record` is the document's record of it, or
 * undefined when this run adds one, and `key` the key the card names it by (the record's own,
 * `matchRecord`'s). Null when it maps to no consumed row, or every line is settled. A card or a draw
 * line this plan wrote that the team deleted is not drawn again, and a line says so. The caller
 * gives no opportunity a card (`retiredDraws`), and leaves out a use case starting more than 12
 * months out: it adds nothing in the window, so its draw would claim more of a row than the row's
 * 12-month demand.
 */
function pursuitFinding({ plan, document, asOf, locate, book }, pursuit, record, key = pursuit.id) {
  const { item: opportunity } = pursuit;
  const drawn = drawnUnits(plan, opportunity);
  if (!drawn.size) return null;
  const held = typeof record?.id === "string" && record.id !== "";
  const card = held && Array.isArray(document.snapshot?.pursuits)
    ? document.snapshot.pursuits.find((candidate) => isRecord(candidate) && sameIds(candidate.opportunityId, record.id))
    : undefined;
  const earlier = book.keysOf(pursuit.draws);
  if (held && !card && earlier.length) {
    book.conflicts.push(`${pursuit.named}: its pursuit card, which this plan added, is no longer in the document, so it is not added again. ${REMOVED}`);
    book.settle(earlier);
    return null;
  }
  const draw = [];
  let refreshing = false;
  for (const [rowKey, units] of drawn) {
    const key = pursuit.draw(rowKey);
    const { token, id: rowId } = locate(rowKey);
    const line = rowId && Array.isArray(card?.draw) ? card.draw.find((candidate) => isRecord(candidate) && sameIds(candidate.rowId, rowId)) : undefined;
    if (line) {
      const outcome = book.decide(key, line.units, units, `snapshot pursuit "${opportunity.name}" draw on "${rowKey}"`, show, pursuit.giver);
      if (outcome === "write" || outcome === "refresh") draw.push({ rowId: token, units });
      if (outcome === "refresh") refreshing = true;
    } else if (card && book.wrote(key)) {
      book.conflicts.push(`${pursuit.named}: its draw on "${rowKey}", which this plan wrote, is no longer on its pursuit card, so it is not drawn again. ${REMOVED}`);
      book.settle([key]);
    } else {
      book.fresh(key, units);
      draw.push({ rowId: token, units });
    }
  }
  if (!draw.length) return null;
  return {
    op: "add",
    pointer: "/snapshot/pursuits",
    value: { opportunityId: `ref:opportunity:${key}`, draw },
    source: pursuit.source,
    asOf: pursuit.asOf,
    ...(refreshing ? { supersedes: refreshedFrom(asOf, pursuit.giver) } : {}),
  };
}

/** "A", "A" and "B", or "A", "B" and "C". */
const quotedList = (items) => {
  const quoted = items.map((item) => `"${item}"`);
  return quoted.length > 1 ? `${quoted.slice(0, -1).join(", ")} and ${quoted.at(-1)}` : quoted[0];
};

/**
 * An open opportunity draws nothing: its product lines are new entitlement the customer is buying, and a draw is use of
 * the entitlement the account already holds. The draws an earlier run of this plan wrote for one (`draw:<id>:<row>`)
 * are reported, never cleared: one line naming each row whose draw line on its pursuit card still holds what this plan
 * wrote. A line the team changed or cleared is the team's, and nothing this plan gives disagrees with it; a line or card
 * the team removed leaves nothing to remove. Either way the keys are settled, so `reportDeparted` says nothing more.
 */
function retiredDraws({ document, book, keyOfId }, pursuit, record) {
  const earlier = book.keysOf(pursuit.draws);
  if (!earlier.length) return;
  book.settle(earlier);
  const held = typeof record?.id === "string" && record.id !== "";
  const card = held && Array.isArray(document.snapshot?.pursuits)
    ? document.snapshot.pursuits.find((candidate) => isRecord(candidate) && sameIds(candidate.opportunityId, record.id))
    : undefined;
  const rows = [];
  for (const line of Array.isArray(card?.draw) ? card.draw : []) {
    const rowKey = isRecord(line) && typeof line.rowId === "string" ? keyOfId(line.rowId) : undefined;
    if (rowKey === undefined || rows.includes(rowKey) || !book.wrote(pursuit.draw(rowKey))) continue;
    const wrote = book.previous[pursuit.draw(rowKey)];
    if (wrote === line.units || (isBlank(wrote) && isBlank(line.units))) rows.push(rowKey);
  }
  if (!rows.length) return;
  const one = rows.length === 1;
  book.conflicts.push(`${pursuit.named}: this plan no longer draws for opportunities, since an opportunity adds its own entitlement and draws nothing from today's rows; the ${one ? "draw" : "draws"} it wrote earlier on ${quotedList(rows)} ${one ? "remains" : "remain"} on its pursuit card. The AE removes ${one ? "it" : "them"} in the app.`);
}

/**
 * A renewal-test row: what will consume a plan row in the next 12 months, and how much by 6 and 12.
 * The driver names the opportunities and use cases landing in the window. Each window's demand is the
 * team's forecast where it covers that window, and otherwise the pipeline's (no figure in a window an
 * unsized line lands in). The pipeline's values and the forecast's come as separate findings, each
 * with its own source and date, since a finding carries one. A field nothing gives (the driver and a
 * window the forecast leaves, on a row only the forecast sizes) is left as the document has it, and
 * `reportDeparted` names what this plan wrote there. None when every value is settled. A row this
 * plan added that the team deleted is not added again, and a line says so.
 *
 * A seat or robot forecast with no consumed figure gives no figure: nothing is written in its window (a new row with
 * nothing else to say is not added, and a figure this plan wrote earlier stays rather than turning into no figure),
 * and a line names the missing consumed figure. A 0 the busiest-quarter roll-up gives (the forecast at or below what
 * is consumed) is written with a line saying so, since with no driver the app shows the row as Not adopted. A +6-month
 * figure above the +12-month one, possible only when the forecast gives one window and the pipeline the other, is
 * reported naming the row.
 */
function renewalRowFindings({ document, asOf, locate, book }, rowKey, demand) {
  const { token, id } = locate(rowKey);
  const existing = id && Array.isArray(document.renewalTest?.rows)
    ? document.renewalTest.rows.find((candidate) => isRecord(candidate) && sameIds(candidate.rowId, id))
    : undefined;
  const useCaseSources = demand.useCaseSources ?? [];
  const fromOpportunities = demand.drivers.length > useCaseSources.length;
  const forecast = new Set(demand.teamForecast?.windows ?? []);
  const groups = [
    {
      giver: !useCaseSources.length ? SALESFORCE : fromOpportunities ? SALESFORCE_AND_USE_CASES : USE_CASES,
      source: [...(fromOpportunities ? [`Salesforce Opportunities closing within 12 months of ${asOf}`] : []), ...new Set(useCaseSources)].join("; "),
      asOf: demand.asOf,
      fields: [],
    },
    { giver: TEAM_FORECAST, source: TEAM_FORECAST_SOURCE, asOf: demand.teamForecast?.asOf, fields: [] },
  ];
  const all = [
    ["pipelineDriver", demand.drivers.join("; ")],
    ["demand6MoUnits", demand.demand6MoUnits],
    ["demand12MoUnits", demand.demand12MoUnits],
  ].map(([field, next]) => ({ field, next, key: `renewalTest:${rowKey}:${field}` }));
  for (const entry of all) {
    if (forecast.has(entry.field)) groups[1].fields.push(entry);
    else if (demand.drivers.length) groups[0].fields.push(entry);
  }
  if (!existing) {
    const earlier = all.map(({ key }) => key).filter(book.wrote);
    if (earlier.length) {
      book.conflicts.push(`renewalTest row "${rowKey}", which this plan added, is no longer in the document, so it is not added again. ${REMOVED}`);
      book.settle(earlier);
      return [];
    }
  }
  const unmeasured = new Set(demand.teamForecast?.unmeasured ?? []);
  const findings = [];
  for (const group of groups) {
    const value = { rowId: token };
    let refreshing = false;
    for (const { field, next, key } of group.fields) {
      if (unmeasured.has(field)) {
        if (existing) book.settle([key]);
        continue;
      }
      if (!existing) {
        book.fresh(key, next);
        value[field] = next;
        continue;
      }
      const outcome = book.decide(key, existing[field], next, `renewalTest row "${rowKey}" ${field}`, show, group.giver);
      if (outcome === "write" || outcome === "refresh") value[field] = next;
      if (outcome === "refresh") refreshing = true;
    }
    if (Object.keys(value).length === 1) continue;
    findings.push({
      op: "add",
      pointer: "/renewalTest/rows",
      value,
      source: group.source,
      asOf: group.asOf,
      ...(refreshing ? { supersedes: refreshedFrom(asOf, group.giver) } : {}),
    });
  }
  const row = `renewalTest row "${rowKey}"`;
  if (unmeasured.size) {
    book.conflicts.push(`${row}: the team forecast (forecastUnits) gives no ${[...unmeasured].join(" or ")}, since the plan row has no consumed figure (consumedQuantity) to take from its busiest quarter; this plan writes none and leaves the document's as it is.`);
  }
  const floored = demand.teamForecast?.floored ?? [];
  if (floored.length) {
    const notAdopted = floored.some(({ field }) => field === "demand12MoUnits") && !demand.drivers.length;
    book.conflicts.push(`${row}: the team forecast (forecastUnits) gives 0 ${floored.map(({ field }) => field).join(" and ")}, since its busiest quarter there (${Math.max(...floored.map(({ peak }) => peak))}) is at or below the ${floored[0].consumed} already consumed${notAdopted ? "; with no pipeline driver the app shows the row as Not adopted" : ""}.`);
  }
  const { demand6MoUnits: sixMonths, demand12MoUnits: twelveMonths } = demand;
  if (Number.isFinite(sixMonths) && Number.isFinite(twelveMonths) && sixMonths > twelveMonths) {
    const giverOf = (field) => (forecast.has(field) ? TEAM_FORECAST : groups[0].giver).from;
    book.conflicts.push(`${row}: its demand6MoUnits (${sixMonths}) exceeds its demand12MoUnits (${twelveMonths}), which includes it; ${giverOf("demand6MoUnits")} gives the first and ${giverOf("demand12MoUnits")} the second. The AE reconciles them in the plan file.`);
  }
  return findings;
}

/**
 * Reports, and never clears, what the plan wrote that its opportunities and use cases no longer give:
 *   - an opportunity that is no longer open in the plan (closed, gone stale or dropped): one line,
 *     however many values it wrote (an open one's earlier draws are `retiredDraws`');
 *   - the draws of a use case that now starts more than 12 months out, which draws nothing: one line
 *     for the use case;
 *   - a use case that is no longer in the plan: one line, however many values it wrote; and a
 *     draw on a row a use case still in the plan no longer sizes (its line was removed or moved to
 *     another row);
 *   - a renewal-test row no open opportunity or use case drives any more: one line for a row with
 *     no demand at all, and one naming the fields this plan wrote for a row the team's forecast now
 *     sizes alone (its demand follows the forecast; the driver it had stays).
 * Its card, draws and demand stay in the document for the account executive to confirm and
 * close, change or remove in the app.
 */
function reportDeparted({ previous, conflicts, decided }, demand, asOf) {
  const open = new Set(demand.open.map(({ salesforceId }) => salesforceId));
  const useCases = new Map(demand.useCases.map((useCase) => [useCase.key, useCase]));
  const beyond = new Set(demand.beyondWindow.map((item) => pursuitOf(item).id));
  const opportunities = new Set();
  const goneUseCases = new Set();
  const draws = [];
  const outOfWindow = new Set();
  const rows = new Map();
  for (const key of Object.keys(previous)) {
    const opportunity = /^(?:draw|opportunity):([^:]+):/.exec(key)?.[1];
    if (opportunity !== undefined && !open.has(opportunity)) opportunities.add(opportunity);
    const useCase = /^useCase:([^:]+):/.exec(key)?.[1];
    if (useCase !== undefined && !useCases.has(useCase)) goneUseCases.add(useCase);
    const useCaseDraw = /^useCase:([^:]+):draw:(.+)$/.exec(key);
    if (useCaseDraw && useCases.has(useCaseDraw[1]) && !decided.has(key)) {
      if (beyond.has(useCaseDraw[1])) outOfWindow.add(useCases.get(useCaseDraw[1]));
      else draws.push({ pursuit: pursuitOf(useCases.get(useCaseDraw[1])), row: useCaseDraw[2] });
    }
    const row = /^renewalTest:(.+):(pipelineDriver|demand6MoUnits|demand12MoUnits)$/.exec(key);
    if (row && !decided.has(key) && !demand.byRow.get(row[1])?.drivers.length) rows.set(row[1], [...(rows.get(row[1]) ?? []), row[2]]);
  }
  for (const id of opportunities) {
    conflicts.push(`Opportunity ${id} is no longer open in this plan; its card, draws and demand remain in the document. The AE confirms its Salesforce status and closes or removes it in the app.`);
  }
  for (const key of goneUseCases) {
    conflicts.push(`Use case ${key} is no longer in this plan; its record, card, draws and demand remain in the document. The AE confirms with the account team whether it is still pursued and removes it in the app.`);
  }
  for (const { pursuit, row } of draws) {
    conflicts.push(`${pursuit.named}: its earlier draw on "${row}" is no longer in this plan's lines, but it remains in the document. The AE confirms or removes it in the app.`);
  }
  for (const item of outOfWindow) {
    conflicts.push(`${pursuitOf(item).named} now starts ${item.startDate}, more than 12 months after ${asOf}, so this plan draws nothing for it; the draws it wrote earlier remain on its pursuit card. The AE re-dates it in the plan file or removes the draws in the app.`);
  }
  for (const [row, fields] of rows) {
    if (!demand.byRow.has(row)) {
      conflicts.push(`renewalTest row "${row}": no open opportunity in this plan drives it any more, but the driver and demand this plan wrote remain in the document. The AE confirms them and changes or clears them in the app.`);
      continue;
    }
    const one = fields.length === 1;
    conflicts.push(`renewalTest row "${row}": no open opportunity in this plan drives it any more, but the ${fields.join(" and ")} this plan wrote ${one ? "remains" : "remain"} in the document, beside the demand the team forecast now gives. The AE confirms ${one ? "it" : "them"} and changes or clears ${one ? "it" : "them"} in the app.`);
  }
}

/**
 * The findings the numbers stage puts in a document built from the plan (`toDay2`'s
 * output): the contract's dates, a record for each open opportunity and then each use case
 * (claiming one the team added under its name), a pursuit card drawing on the rows each use case
 * starting (or undated) within 12 months sizes, and the renewal-test values for each row with
 * demand. No opportunity gets a card: its product lines are new entitlement, not use of today's
 * rows. They come in that order, so every `ref:` names a record an earlier finding made or keyed.
 *
 * `written` is each derived value the document now holds or is to hold, keyed
 * `renewalTest:<row>:<field>`,
 * `opportunity:<salesforceId>:<name|status|products|consumptionRowIds|projectedConsumption>`,
 * `useCase:<key>:draw:<row>` and
 * `useCase:<key>:<name|status|estimatedIarrUsd|products|consumptionRowIds|projectedConsumption>`
 * (a `draw:<salesforceId>:<row>` an earlier run recorded is reported, never written again);
 * `conflicts` lists the values kept because the account team's differ or were cleared, the
 * records it removed, and what has left the plan.
 */
export function numberFindings(plan, document) {
  const { contract, opportunities, useCases } = readPipeline(plan);
  const asOf = isoDate(plan.asOf, "plan.asOf");
  const demand = pipelineDemand(plan);
  const book = startLedger(plan);
  const context = {
    plan, document, asOf, ...rowLocator(plan, document), book,
    claimed: new Set(),
    planKeys: new Set([...opportunities.map(({ salesforceId }) => normalizedKey(salesforceId)), ...useCases.map(({ key }) => normalizedKey(key))]),
  };
  const findings = [];

  const source = `Salesforce Contract${contract.contractNumber ? ` ${contract.contractNumber}` : ""}`;
  for (const [pointer, value, current] of [
    ["/renewalDate", contract.renewalDate, document?.renewalDate],
    ["/snapshot/contractStartDate", contract.startDate, document?.snapshot?.contractStartDate],
  ]) {
    if (!value || current === value) continue;
    findings.push({ op: "set", pointer, value, source, asOf, ...(isBlank(current) ? {} : { supersedes: SYSTEM_OF_RECORD }) });
  }
  const pursuits = [...demand.open, ...demand.useCases].map(pursuitOf);
  const records = new Map();
  for (const pursuit of pursuits) {
    const match = matchRecord(context, pursuit);
    if (match.withheld) {
      book.conflicts.push(match.withheld);
      book.settle([...book.keysOf(pursuit.fields), ...book.keysOf(pursuit.draws)]);
      continue;
    }
    records.set(pursuit.id, match);
    findings.push(...opportunityFindings(context, pursuit, match));
  }
  const beyond = new Set(demand.beyondWindow.map((item) => pursuitOf(item).id));
  for (const pursuit of pursuits) {
    if (!records.has(pursuit.id)) continue;
    const { record, key } = records.get(pursuit.id);
    if (!pursuit.useCase) {
      retiredDraws(context, pursuit, record);
      continue;
    }
    if (beyond.has(pursuit.id)) continue;
    const finding = pursuitFinding(context, pursuit, record, key);
    if (finding) findings.push(finding);
  }
  for (const [rowKey, rowDemand] of demand.byRow) findings.push(...renewalRowFindings(context, rowKey, rowDemand));
  reportDeparted(book, demand, asOf);
  return { findings, conflicts: book.conflicts, written: book.written };
}

/**
 * The final stage's finding: the Snapshot's other pipeline activity, in whole US
 * dollars, from the opportunities and use cases the app's top-pursuit cards do not show. Those
 * cards depend on the opportunities the document holds, so this runs on the
 * document the numbers stage produced, and again on the app's export whenever the
 * team names other top pursuits. The value follows the refresh rule. When a line has no
 * units, or a sized line no price, to value it, the value is no figure: a figure this
 * plan wrote earlier is cleared, a team's figure stays, and `conflicts` says which lines.
 */
export function otherActivityFindings(plan, document) {
  const asOf = isoDate(plan.asOf, "plan.asOf");
  const book = startLedger(plan);
  const findings = [];
  const shown = shownPursuitKeys(document);
  const { usd, unpriced, unsized } = otherActivityUsd(plan, shown);
  const shownKeys = new Set(shown.map(normalizedKey));
  const withUseCases = readPipeline(plan).useCases.some(({ key }) => !shownKeys.has(normalizedKey(key)));
  const giver = withUseCases ? SALESFORCE_AND_USE_CASES : SALESFORCE;
  const current = document?.snapshot?.otherPipelineActivityUsd;
  const value = usd === null ? null : Math.round(usd);
  const outcome = book.decide("otherPipelineActivityUsd", current, value, "snapshot.otherPipelineActivityUsd", show, giver);
  const lines = (entries) => entries.map(({ opportunity, line }) => `${opportunity.name} (${line.row})`).join("; ");
  const reasons = [
    ...(unsized.length ? [`${unsized.length} line(s) have no unit volume to value them: ${lines(unsized)}.`] : []),
    ...(unpriced.length ? [`${unpriced.length} sized line(s) have no contracted unit price to value them: ${lines(unpriced)}.`] : []),
  ];
  for (const reason of reasons) {
    if (outcome === "refresh") book.conflicts.push(`snapshot.otherPipelineActivityUsd cleared the ${show(current)} this plan wrote earlier: ${reason}`);
    else book.conflicts.push(`snapshot.otherPipelineActivityUsd not written: ${reason}${outcome === "keep" ? ` The account team's ${show(current)} stays.` : ""}`);
  }
  if (outcome === "write" || outcome === "refresh") {
    findings.push({
      op: "set",
      pointer: "/snapshot/otherPipelineActivityUsd",
      value,
      source: `Salesforce Opportunities${withUseCases ? " and team-sized use cases" : ""} priced at contracted unit prices`,
      asOf,
      ...(outcome === "refresh" ? { supersedes: refreshedFrom(asOf, giver) } : {}),
    });
  }
  return { findings, conflicts: book.conflicts, written: book.written };
}

if (isMain(import.meta.url)) {
  const args = process.argv.slice(2);
  const opt = (name) => {
    const index = args.indexOf(name);
    const value = index >= 0 ? args[index + 1] : undefined;
    return value === undefined || value.startsWith("--") ? undefined : value;
  };
  const [command, planPath] = args;
  const documentPath = opt("--document");
  const stage = opt("--stage");
  const out = opt("--out");
  const record = args.includes("--record");
  if (command !== "findings" || !planPath || planPath.startsWith("--") || !documentPath || !(out || record) || !["numbers", "final"].includes(stage)) {
    console.error("usage: pipeline.mjs findings <plan.json> --document <day2.json> --stage numbers|final (--out <findings.json> | --record) [--conflicts <conflicts.json>]");
    process.exit(2);
  }
  try {
    const plan = JSON.parse(readFileSync(planPath, "utf8"));
    const document = JSON.parse(readFileSync(documentPath, "utf8"));
    const { findings, conflicts, written } = (stage === "numbers" ? numberFindings : otherActivityFindings)(plan, document);
    if (out) writeFileSync(out, `${JSON.stringify({ findings }, null, 2)}\n`);
    if (opt("--conflicts")) writeFileSync(opt("--conflicts"), `${JSON.stringify({ conflicts }, null, 2)}\n`);
    if (record && findings.length) {
      throw new PipelineError(`not recorded: the document does not hold ${findings.length} finding(s) yet; apply them with apply-findings.mjs, then run --record against the document it wrote`);
    }
    if (record) {
      plan.pipeline.written = { ...readWritten(plan), ...written };
      writeFileSync(planPath, `${JSON.stringify(plan, null, 2)}\n`);
    }
    console.log([
      out ? `Wrote ${findings.length} finding(s) to ${out}` : `${findings.length} finding(s) still to apply`,
      ...(record ? [`Recorded ${Object.keys(written).length} value(s) in the plan`] : []),
      ...(conflicts.length ? [`${conflicts.length} value(s) kept or left as the document has them:`, ...conflicts.map((line) => `- ${line}`)] : []),
    ].join("\n"));
  } catch (error) {
    if (!(error instanceof PipelineError || error instanceof PlanError)) throw error;
    console.error(`pipeline: ${error.message}`);
    process.exit(1);
  }
}

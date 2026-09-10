#!/usr/bin/env node
/**
 * Reports what a Day 2 document's Consumption Plan does and does not yet say.
 *
 * Three things, none of which the document itself stores:
 *   1. Attribution residuals -- how much of each row's consumption the use
 *      cases explain, and where they claim more than the row measures.
 *   2. Dangling allocations, whose rowId names no row in the plan.
 *   3. The fields still blocking publication.
 *
 * This is a report, not a fixer. It never edits the document: closing a
 * residual by adjusting numbers is exactly the fabrication the tab exists to
 * make visible.
 *
 * Usage: node reconcile.mjs <document.json> [--json]
 */
import { readFileSync } from "node:fs";

const QUARTERS = ["q1", "q2", "q3", "q4"];
const exact = (value) => (value === null || value === undefined ? "—" : Number(value).toLocaleString("en-US"));

/** Sum that withholds rather than summing short, matching how the app totals. */
function sumOrNull(values) {
  if (!values.length || values.some((value) => value === null || value === undefined)) return null;
  return values.reduce((total, value) => total + value, 0);
}

export function reconcile(account) {
  const plan = account.consumptionPlan ?? {};
  const rows = (plan.groups ?? []).flatMap((group) => group.rows ?? []);
  const useCases = plan.primaryUseCases ?? [];
  const rowIds = new Set(rows.map((row) => row.id));

  const dangling = useCases.flatMap((useCase, useCaseIndex) =>
    (useCase.allocations ?? [])
      .map((allocation, allocationIndex) => ({ allocation, allocationIndex }))
      .filter(({ allocation }) => allocation.rowId && !rowIds.has(allocation.rowId))
      .map(({ allocation, allocationIndex }) => ({
        useCase: useCase.useCases || `Use case ${useCaseIndex + 1}`,
        rowId: allocation.rowId,
        fieldId: `consumptionPlan.primaryUseCases-${useCaseIndex}.allocations-${allocationIndex}.rowId`,
      })));

  const attribution = rows.map((row) => {
    const periods = ["current", ...QUARTERS].map((period) => {
      const measured = period === "current" ? row.actualConsumed ?? null : row.forecastUnits?.[period] ?? null;
      const contributions = useCases
        .flatMap((useCase) => useCase.allocations ?? [])
        .filter((allocation) => allocation.rowId === row.id)
        .map((allocation) => (period === "current"
          ? allocation.currentUnits ?? null
          : allocation.forecastUnits?.[period] ?? null));
      const attributed = contributions.length === 0 ? null : sumOrNull(contributions);
      return {
        period,
        measured,
        attributed,
        residual: measured === null || attributed === null ? null : measured - attributed,
      };
    });
    return { offering: row.offering || "(unnamed)", unit: row.unit || "units", periods };
  });

  const blockers = [];
  if (!rows.length) blockers.push("No consumption row is recorded; at least one is required to publish.");
  rows.forEach((row, index) => {
    const label = row.offering || `row ${index + 1}`;
    for (const [field, value] of [["offering", row.offering], ["unit", row.unit]]) {
      if (!String(value ?? "").trim()) blockers.push(`${label}: ${field} is empty.`);
    }
    for (const field of ["soldQuantity", "soldArrUsd"]) {
      if (row[field] === null || row[field] === undefined) {
        blockers.push(`${label}: ${field} is not set. Pin it, or let the pricebook allocate ARR and have the account team confirm.`);
      }
    }
  });
  if (!account.renewalEconomics?.assurance) blockers.push("Renewal assurance is not set. It is a judgment field: it needs an explicit account-team statement.");
  if (!String(plan.forecastPeriod ?? "").includes("Q+")) {
    blockers.push('forecastPeriod does not name its quarters. Run resolve-quarters.mjs and stamp the window, e.g. "Q+1 FY27 Q4 → Q+4 FY28 Q3".');
  }

  return { rows: rows.length, useCases: useCases.length, attribution, dangling, blockers };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2);
  const input = args.find((value) => !value.startsWith("--"));
  if (!input) {
    console.error("Usage: node reconcile.mjs <document.json> [--json]");
    process.exit(1);
  }
  const report = reconcile(JSON.parse(readFileSync(input, "utf8")));
  if (args.includes("--json")) {
    console.log(JSON.stringify(report, null, 2));
    process.exit(0);
  }

  console.log(`${report.rows} consumption row(s), ${report.useCases} use case(s)\n`);
  console.log("ATTRIBUTION");
  for (const row of report.attribution) {
    const current = row.periods[0];
    if (current.attributed === null) {
      console.log(`  ${row.offering} — no use case attributes this row.`);
    } else if (current.residual !== null && current.residual < 0) {
      console.log(`  ${row.offering} — use cases claim ${exact(-current.residual)} ${row.unit} MORE than the row measures.`);
    } else {
      console.log(`  ${row.offering} — ${exact(current.attributed)} of ${exact(current.measured)} ${row.unit} attributed, ${exact(current.residual)} remaining.`);
    }
  }

  if (report.dangling.length) {
    console.log("\nDANGLING ALLOCATIONS");
    for (const item of report.dangling) {
      console.log(`  ${item.useCase} points at a row that is not in the plan (${item.fieldId}).`);
    }
  }

  console.log(`\nBLOCKING PUBLICATION (${report.blockers.length})`);
  for (const blocker of report.blockers) console.log(`  - ${blocker}`);
  if (!report.blockers.length) console.log("  none");
}

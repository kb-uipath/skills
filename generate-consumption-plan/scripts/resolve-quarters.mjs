#!/usr/bin/env node
/**
 * Resolves what `forecastUnits.q1`-`q4` mean for a Day 2 review.
 *
 * UiPath's fiscal year ends 31 January, so FY2027 runs 2026-02-01 to
 * 2027-01-31. `actualConsumed` is the quarter containing the review's `asOf`
 * date; Q+1 to Q+4 are the four fiscal quarters after it. The window is
 * rolling, so a Q3 review forecasts into the next fiscal year.
 *
 * Usage: node resolve-quarters.mjs [YYYY-MM-DD] [--json]
 */

/** Fiscal quarter containing a date. Feb is fiscal month 0. */
export function fiscalQuarterOf(date) {
  const month = date.getUTCMonth();
  const fiscalMonth = (month + 11) % 12;
  return {
    fiscalYear: month === 0 ? date.getUTCFullYear() : date.getUTCFullYear() + 1,
    quarter: Math.floor(fiscalMonth / 3) + 1,
  };
}

/** The calendar span of one fiscal quarter. FY y Q1 starts in February of y-1. */
export function fiscalQuarterSpan({ fiscalYear, quarter }) {
  const start = new Date(Date.UTC(fiscalYear - 1, 1 + (quarter - 1) * 3, 1));
  const end = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 3, 0));
  return { start, end };
}

export function addQuarters({ fiscalYear, quarter }, count) {
  const absolute = fiscalYear * 4 + (quarter - 1) + count;
  return { fiscalYear: Math.floor(absolute / 4), quarter: (absolute % 4) + 1 };
}

const iso = (date) => date.toISOString().slice(0, 10);
const label = ({ fiscalYear, quarter }) => `FY${String(fiscalYear).slice(2)} Q${quarter}`;

/** The full window a review's consumption columns describe. */
export function resolveForecastWindow(asOf) {
  const current = fiscalQuarterOf(asOf);
  const quarters = [0, 1, 2, 3, 4].map((offset) => {
    const period = addQuarters(current, offset);
    const { start, end } = fiscalQuarterSpan(period);
    return {
      column: offset === 0 ? "actualConsumed" : `forecastUnits.q${offset}`,
      heading: offset === 0 ? "Current" : `Q+${offset}`,
      period: label(period),
      start: iso(start),
      end: iso(end),
    };
  });
  return {
    asOf: iso(asOf),
    currentPeriod: label(current),
    forecastPeriod: `Q+1 ${quarters[1].period} → Q+4 ${quarters[4].period}`,
    quarters,
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2);
  const asOfArg = args.find((value) => !value.startsWith("--"));
  const asOf = asOfArg ? new Date(`${asOfArg}T00:00:00Z`) : new Date();
  if (Number.isNaN(asOf.getTime())) {
    console.error(`Not a date: ${asOfArg}. Use YYYY-MM-DD.`);
    process.exit(1);
  }
  const window = resolveForecastWindow(asOf);
  if (args.includes("--json")) {
    console.log(JSON.stringify(window, null, 2));
  } else {
    console.log(`Review as of ${window.asOf} — currently in ${window.currentPeriod}\n`);
    for (const q of window.quarters) {
      console.log(`  ${q.heading.padEnd(8)} ${q.period.padEnd(8)} ${q.start} → ${q.end}   ${q.column}`);
    }
    console.log(`\nWrite this into consumptionPlan.forecastPeriod:\n  "${window.forecastPeriod}"`);
  }
}

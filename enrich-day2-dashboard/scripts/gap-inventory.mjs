#!/usr/bin/env node
// Gap inventory for a schema 1.10 Day 2 dashboard JSON: step 1 of the enrichment process.
//
//   node gap-inventory.mjs <file> [--repo <dashboard-repo>] [--instructions <path-or-url>]
//                          [--base-url <deployed-route-url>] [--who evidence,attest,human] [--all] [--json]
//
// Lists every field that renders as a gap, grouped by the tab that reads it, with the app's own
// requirement and write policy, and says who may fill it:
//   evidence  the skill may fill it from a dated source
//   attest    the skill may fill it only from an explicit statement by a named person
//   human     the account team authors it; the skill reports a suggestion and never writes it
//   skip      system-managed, preserve-only, constant or unused (shown only with --all)
// BLOCKS marks a field the publication rules require. Read-only: nothing is modified.
import { readFileSync } from "node:fs";
import { loadInstructions, resolve, whoMayFill, tabOf, isEmpty, recordLabel } from "./instructions-lib.mjs";

const args = process.argv.slice(2);
const opt = (name) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : undefined; };
const flag = (name) => args.includes(name);
const file = args.find((a, i) => !a.startsWith("--") && !["--repo", "--instructions", "--base-url", "--who"].includes(args[i - 1]));
if (!file) {
  console.error("usage: gap-inventory.mjs <file> [--repo <path>] [--instructions <path-or-url>] [--base-url <url>] [--who evidence,attest,human] [--all] [--json]");
  process.exit(2);
}

const doc = JSON.parse(readFileSync(file, "utf8"));
const { json: instructions, from } = await loadInstructions({ instructions: opt("--instructions"), repo: opt("--repo"), baseUrl: opt("--base-url") });
const wanted = new Set((opt("--who") ?? "evidence,attest,human").split(","));
if (flag("--all")) wanted.add("skip");

// Rules from crossFieldRules that block publication even where a descriptor reads "conditional".
const EXTRA_BLOCKING = new Set([
  "/renewalDate", "/renewalEconomics/currentArrUsd", "/renewalEconomics/usageOnlyEstimateUsd", "/renewalEconomics/assurance",
]);

const rows = [];
for (const [pointer, spec] of Object.entries(instructions.fields ?? {})) {
  if (pointer === "" || spec.type === "object") continue;
  const who = whoMayFill(spec, pointer);
  if (!wanted.has(who)) continue;
  const nodes = resolve(doc, pointer);
  const wildcard = pointer.includes("*");
  const targets = !wildcard && nodes.length === 0 ? [{ value: undefined, at: pointer }] : nodes;
  for (const { value, at } of targets) {
    if (spec.type === "boolean" && typeof value === "boolean") continue;
    if (!isEmpty(value)) continue;
    const parentAt = at.split("/").slice(0, -1).join("/");
    // A label only helps when the field belongs to a record in a collection, not to the document root.
    const parent = parentAt ? resolve(doc, parentAt)[0]?.value : undefined;
    // For an empty collection, say which of its record fields a person must supply, so nobody adds
    // a half-complete record the publication rules would reject.
    const gating = spec.type === "array" && nodes.length >= 0
      ? Object.entries(instructions.fields)
          .filter(([p, s]) => p.startsWith(`${pointer}/*/`) && !p.slice(pointer.length + 3).includes("/")
            && s.requirement === "block" && ["human", "attest"].includes(whoMayFill(s, p)))
          .map(([p, s]) => `${whoMayFill(s, p)}: ${p.slice(pointer.length + 3)}`)
      : [];
    rows.push({
      tab: tabOf(pointer),
      pointer: at,
      generic: pointer,
      who,
      requirement: spec.requirement,
      blocks: spec.requirement === "block" || EXTRA_BLOCKING.has(pointer),
      policy: spec.writePolicy,
      label: parentAt ? recordLabel(parent) : "",
      kind: spec.type === "array" ? "no records" : (value === undefined ? "missing" : "empty"),
      recordGating: gating,
    });
  }
}

if (flag("--json")) {
  // No process.exit() here: exiting straight after a large write truncates piped output at 64 KB.
  process.stdout.write(`${JSON.stringify(rows, null, 2)}\n`);
} else {
  printReport();
}

function printReport() {
  const TAB_ORDER = ["Cover", "Background", "Sales Plan", "Consumption Plan", "Stakeholders & Actions", "No tab today"];
  const WHO_ORDER = ["evidence", "attest", "human", "skip"];
  console.log(`Gap inventory: ${file}  (schema ${doc.schemaVersion}; instructions: ${from})`);
  console.log("who: evidence = skill, from a dated source | attest = only an explicit named statement | human = account team only | BLOCKS = required for publication\n");

  const totals = { evidence: 0, attest: 0, human: 0, skip: 0, blocks: 0 };
  for (const tab of TAB_ORDER) {
    const inTab = rows.filter((r) => r.tab === tab);
    if (!inTab.length) continue;
    const count = (w) => inTab.filter((r) => r.who === w).length;
    console.log(`== ${tab}: ${inTab.length} gaps (${count("evidence")} evidence, ${count("attest")} attest, ${count("human")} human, ${inTab.filter((r) => r.blocks).length} block)`);
    // Collapse repeated records of the same field so a 9-key health block reads as one line.
    const groups = new Map();
    for (const r of inTab) {
      // /health/<key>/<field> repeats for nine fixed keys; show it once as /health/*/<field>.
      const shown = r.generic.replace(/^\/health\/[^/]+\//, "/health/*/");
      const key = `${r.who}|${shown}`;
      if (!groups.has(key)) groups.set(key, { shown, rows: [] });
      groups.get(key).rows.push(r);
    }
    const ordered = [...groups.values()].sort((a, b) =>
      WHO_ORDER.indexOf(a.rows[0].who) - WHO_ORDER.indexOf(b.rows[0].who) || a.shown.localeCompare(b.shown));
    for (const { shown, rows: g } of ordered) {
      const r = g[0];
      const where = g.length === 1
        ? `${r.pointer}${r.label ? `  [${r.label}]` : ""}${r.kind !== "empty" ? `  (${r.kind})` : ""}`
        : `${shown}  x${g.length}${g.length <= 4 && g.every((x) => x.label) ? `  [${g.map((x) => x.label).join("; ")}]` : ""}`;
      console.log(`  ${r.who.padEnd(8)} ${r.blocks ? "BLOCKS " : "       "}${where}`);
      if (r.recordGating?.length) console.log(`  ${" ".repeat(16)}each record also needs: ${r.recordGating.join(", ")}`);
      totals[r.who] += g.length;
      if (g.some((x) => x.blocks)) totals.blocks += g.filter((x) => x.blocks).length;
    }
    console.log();
  }
  console.log(`Total: ${rows.length} gaps: ${totals.evidence} evidence, ${totals.attest} attest, ${totals.human} human${wanted.has("skip") ? `, ${totals.skip} skip` : ""}; ${totals.blocks} required for publication.`);
  console.log("Fillable by the skill without a human statement: the 'evidence' rows only. 'attest' rows need a named person's explicit statement; 'human' rows get a suggestion in the report, never a value in the JSON.");
}

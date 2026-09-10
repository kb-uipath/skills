import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { describe, expect, it } from "vitest";

const appRoot = process.env.DAY2_APP_ROOT;
const dashboardPath = process.env.DAY2_DASHBOARD_JSON;

if (!appRoot || !dashboardPath) {
  throw new Error("Set DAY2_APP_ROOT and DAY2_DASHBOARD_JSON for the optional app compatibility test.");
}

const schema = await import(pathToFileURL(path.join(appRoot, "src/schema/account.ts")).href);
const validation = await import(pathToFileURL(path.join(appRoot, "src/lib/accountValidation.ts")).href);
const raw = JSON.parse(await readFile(dashboardPath, "utf8"));
const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const blank = JSON.parse(
  await readFile(
    path.join(
      scriptDirectory,
      "..",
      "salesforce-layer",
      "assets",
      "blank-dashboard-v1.4.json",
    ),
    "utf8",
  ),
);

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu;
const REPEATABLE_KEYS = ["goals", "cadenceGoals", "workstreams", "relationships", "eltAsks", "timeline", "sources"];

function collectGeneratedIds(account: Record<string, any>) {
  const ids = REPEATABLE_KEYS.flatMap((key) => account[key].map((row: { id: string }) => row.id));
  for (const group of account.consumptionPlan.groups) {
    ids.push(group.id);
    ids.push(...group.rows.map((row: { id: string }) => row.id));
  }
  return ids;
}

function projectCanonicalV14(account: Record<string, any>) {
  const projected = structuredClone(account);
  expect(projected.evidenceLedger).toEqual([]);
  expect(projected.fieldEvidenceLinks).toEqual([]);
  delete projected.evidenceLedger;
  delete projected.fieldEvidenceLinks;
  for (const key of REPEATABLE_KEYS) {
    projected[key].forEach((row: Record<string, unknown>) => delete row.id);
  }
  projected.consumptionPlan.groups.forEach((group: Record<string, any>) => {
    delete group.id;
    group.rows.forEach((row: Record<string, any>) => {
      expect(row.arr).toBe("");
      delete row.arr;
      delete row.id;
    });
  });
  projected.schemaVersion = "1.4";
  return projected;
}

function populatedV14Fixture() {
  const fixture = structuredClone(blank);
  fixture.customerName = "Synthetic Account";
  fixture.goals = [{ text: "Outcome", target: "Q4", owner: "CSM" }];
  fixture.cadenceGoals = [{ label: "Review", target: "Decision", date: "Q4", owner: "AE", status: "Planned" }];
  fixture.workstreams = [{ name: "Adoption", owner: "CSM", risk: "Access", milestones: "Baseline", outcomes: "Plan", atRisk: true }];
  fixture.consumptionPlan.groups = [{
    element: "Users",
    rows: [{
      product: "Named User",
      purchased: "100",
      utilization: "20%",
      utilizationStatus: "Orange",
      forecast: { q1: "20", q2: "30", q3: "40", q4: "50" },
      comments: "Synthetic migration fixture",
    }],
  }];
  fixture.relationships = [{ hierarchyOrder: 1, uipathName: "AE", uipathRole: "AE", customerName: "Sponsor", customerRole: "CIO", note: "Planned outreach" }];
  fixture.eltAsks = [{ type: "Decision", owner: "AE", ask: "Confirm sponsor", status: "Open" }];
  fixture.timeline = [{ date: "2026-08-01", title: "Review", description: "Synthetic event", status: "Planned" }];
  fixture.sources = [{ name: "synthetic.txt", size: 9, type: "text/plain", kind: "attached, not extracted", text: "synthetic", warning: "" }];
  return fixture;
}

describe("generated Day 2 dashboard app compatibility", () => {
  it("imports canonical schema 1.4 through the current app migration without semantic loss", () => {
    const imported = schema.importAccount(raw);
    expect(raw.schemaVersion).toBe("1.4");
    expect(schema.SCHEMA_VERSION).toBe("1.6");
    expect(imported.schemaVersion).toBe(schema.SCHEMA_VERSION);
    expect(projectCanonicalV14(imported)).toEqual(raw);
    for (const key of Object.keys(raw.health)) {
      expect(imported.health[key].status).toBe(raw.health[key].status);
    }
    const ids = collectGeneratedIds(imported);
    ids.forEach((id) => expect(id).toMatch(UUID_PATTERN));
    expect(new Set(ids).size).toBe(ids.length);
    expect(schema.importAccount(JSON.parse(JSON.stringify(imported)))).toEqual(imported);
  });

  it("adds stable IDs and blank 1.6 ARR only to populated repeatable rows", () => {
    const fixture = populatedV14Fixture();
    const imported = schema.importAccount(fixture);
    const ids = collectGeneratedIds(imported);
    expect(ids.length).toBe(9);
    ids.forEach((id) => expect(id).toMatch(UUID_PATTERN));
    expect(new Set(ids).size).toBe(ids.length);
    expect(imported.consumptionPlan.groups[0].rows[0].arr).toBe("");
    expect(projectCanonicalV14(imported)).toEqual(fixture);
    expect(schema.importAccount(JSON.parse(JSON.stringify(imported)))).toEqual(imported);
  });

  it("runs both full validation and PDF blocker validation after migration", () => {
    const imported = schema.importAccount(raw);
    const full = validation.getValidationItems(imported);
    const pdf = validation.getPdfExportBlockers(imported);
    expect(Array.isArray(full)).toBe(true);
    expect(Array.isArray(pdf)).toBe(true);
    expect(
      full.every(
        (item: { type?: unknown; text?: unknown; fieldId?: unknown }) =>
          ["ok", "warn", "block"].includes(String(item.type)) &&
          typeof item.text === "string" &&
          (item.fieldId === undefined || typeof item.fieldId === "string"),
      ),
    ).toBe(true);
    expect(
      pdf.every(
        (item: { type?: unknown; text?: unknown; fieldId?: unknown }) =>
          item.type === "block" &&
          typeof item.text === "string" &&
          typeof item.fieldId === "string",
      ),
    ).toBe(true);
    expect(
      pdf.every((blocker: { text: string; fieldId: string }) =>
        full.some(
          (item: { text: string; fieldId?: string }) =>
            item.text === blocker.text && item.fieldId === blocker.fieldId,
        )),
    ).toBe(true);

    const blankPdf = validation.getPdfExportBlockers(schema.importAccount(blank));
    expect(blankPdf.map((item: { fieldId?: string }) => item.fieldId)).toEqual([
      "tagline",
      "statusSummary",
      "useCases",
      "goals",
      "workstreams",
    ]);
  });
});

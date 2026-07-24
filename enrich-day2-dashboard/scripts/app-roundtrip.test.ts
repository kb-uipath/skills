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

describe("generated Day 2 dashboard app compatibility", () => {
  it("round-trips through the app importer without normalization or data loss", () => {
    const imported = schema.importAccount(raw);
    expect(imported).toEqual(raw);
    expect(imported.schemaVersion).toBe("1.4");
  });

  it("runs both full validation and PDF blocker validation", () => {
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

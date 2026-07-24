import { readFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { describe, expect, it } from "vitest";

const appRoot = process.env.DAY2_APP_ROOT;
const dashboardPath = process.env.DAY2_DASHBOARD_JSON;

if (!appRoot || !dashboardPath) {
  throw new Error("Set DAY2_APP_ROOT and DAY2_DASHBOARD_JSON for the optional app compatibility test.");
}

const schema = await import(pathToFileURL(path.join(appRoot, "src/schema/account.ts")).href);
const validation = await import(pathToFileURL(path.join(appRoot, "src/lib/accountValidation.ts")).href);
const raw = JSON.parse(await readFile(dashboardPath, "utf8"));

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
    expect(full.every((item: { text?: unknown }) => typeof item.text === "string")).toBe(true);
    expect(pdf.every((item: { text?: unknown }) => typeof item.text === "string")).toBe(true);
  });
});

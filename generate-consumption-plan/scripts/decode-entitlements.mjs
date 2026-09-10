#!/usr/bin/env node
/**
 * Turns raw SBQQ__Subscription__c rows into candidate Day 2 consumption rows.
 *
 * The reason this script exists: on Enterprise License Agreement contracts every
 * SBQQ__Quantity__c is 1, and the entitled volume lives in the product name
 * ("ELA - AI Unit Bundle - 60K"). Summing quantity on such an account yields a
 * confident, meaningless number -- the worst failure mode for a figure headed
 * into a CFO-chaired review, because nothing about it looks wrong.
 *
 * Decodes against the dashboard repo's pricebook snapshot and reports what it
 * could not resolve rather than guessing.
 *
 * Usage:
 *   node decode-entitlements.mjs <subscriptions.json> --pricebook <uipath-pricebook.json>
 *
 * Input is the JSON array a SOQL query returns (see
 * references/entitlement-resolution.md for the query).
 */
import { readFileSync } from "node:fs";

const SUFFIX_SCALE = { K: 1e3, M: 1e6, B: 1e9 };

/**
 * Volume encoded in a SKU name: "Bundle - 60K" -> 60000, "Pack (5)" -> 5,
 * "250 Users" -> 250. Returns null when the name states no volume, which is a
 * real and common case ("ELA - Unattended Robot") and must not be guessed.
 */
export function volumeFromName(name) {
  if (typeof name !== "string") return null;
  const suffixed = name.match(/(\d+(?:\.\d+)?)\s*([KMB])\b/i);
  if (suffixed) return Math.round(Number(suffixed[1]) * SUFFIX_SCALE[suffixed[2].toUpperCase()]);
  const parenthesised = name.match(/\((\d+)\)/);
  if (parenthesised) return Number(parenthesised[1]);
  const counted = name.match(/\b(\d+)\s+(?:Users?|Seats?|Robots?)\b/i);
  if (counted) return Number(counted[1]);
  return null;
}

const normalise = (value) => String(value ?? "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

/** Pinned product code first, then an exact normalised name match. */
export function matchSku(row, skus) {
  const code = row.SBQQ__Product__r?.ProductCode ?? row.ProductCode ?? "";
  if (code) {
    const byCode = skus.find((sku) => sku.productCode === code);
    if (byCode) return { sku: byCode, matchedBy: "productCode" };
  }
  const name = normalise(row.SBQQ__ProductName__c).replace(/^ela /, "");
  const byName = skus.find((sku) => normalise(sku.skuName).includes(name) && name.length > 4);
  return byName ? { sku: byName, matchedBy: "name" } : { sku: null, matchedBy: "unmatched" };
}

export function decodeEntitlements(rows, skus) {
  return rows.map((row) => {
    const quantity = Number(row.SBQQ__Quantity__c ?? 0);
    const { sku, matchedBy } = matchSku(row, skus);
    const named = volumeFromName(row.SBQQ__ProductName__c);
    const perSku = sku?.unitsPerSku ?? null;
    const isEla = /\bELA\b/i.test(row.SBQQ__ProductName__c ?? "");

    // An ELA line's quantity of 1 is a contract artefact, not a count, so the
    // volume has to come from the name or from a genuine bundle SKU. A matched
    // SKU with unitsPerSku of 1 is a per-unit SKU: on an ELA line that is not
    // information, and multiplying by it would report "1 robot" for a line
    // covering hundreds. Withhold instead.
    const bundleSize = perSku !== null && perSku > 1 ? perSku : null;
    const unitsPerSku = isEla ? (named ?? bundleSize) : (named ?? perSku);
    const soldQuantity = unitsPerSku === null ? (isEla ? null : quantity) : quantity * unitsPerSku;

    const notes = [];
    if (isEla && unitsPerSku === null) {
      notes.push("ELA line states no volume in its name and matched no bundle SKU, so its entitlement is not in Salesforce. Ask the account team; do not infer it from list price or from a per-unit SKU.");
    } else if (isEla) {
      notes.push(`ELA line decoded: quantity ${quantity} x ${unitsPerSku} units, from ${named !== null ? "the SKU name" : "the pricebook bundle size"}.`);
    }
    if (matchedBy === "unmatched") notes.push("No pricebook SKU matched. Pin a skuCode before trusting the ARR allocation.");

    return {
      offering: row.SBQQ__ProductName__c ?? "",
      unit: row.SBQQ__Product__r?.Unit_of_measure__c ?? "",
      licenseModel: row.SBQQ__Product__r?.License_Model__c ?? "",
      soldQuantity,
      skuCode: sku?.productCode ?? "",
      forecastBasis: "auto",
      meteringBasis: sku?.meteringBasis ?? null,
      arrSource: "pricebook",
      contractNumber: row.SBQQ__ContractNumber__c ?? "",
      matchedBy,
      needsReview: notes.length > 0,
      notes,
    };
  });
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2);
  const input = args.find((value) => !value.startsWith("--"));
  const pricebookPath = args[args.indexOf("--pricebook") + 1];
  if (!input || !args.includes("--pricebook")) {
    console.error("Usage: node decode-entitlements.mjs <subscriptions.json> --pricebook <uipath-pricebook.json>");
    process.exit(1);
  }
  const rows = JSON.parse(readFileSync(input, "utf8"));
  const pricebook = JSON.parse(readFileSync(pricebookPath, "utf8"));
  const decoded = decodeEntitlements(Array.isArray(rows) ? rows : rows.records ?? [], pricebook.skus ?? pricebook);
  const review = decoded.filter((row) => row.needsReview);
  console.log(JSON.stringify({
    pricebookEffectiveDate: pricebook.effectiveDate ?? null,
    rows: decoded,
    needsReview: review.length,
  }, null, 2));
  if (review.length) {
    console.error(`\n${review.length} of ${decoded.length} rows need a human look before their numbers are trusted.`);
  }
}

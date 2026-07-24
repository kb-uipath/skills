#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  BLANK_TEMPLATE_PATH,
  DASHBOARD_SCHEMA_VERSION,
  EnricherError,
  FIELD_MAP_PATH,
  applyProposal,
  assertNoProtectedPathCollision,
  assertWritableTargets,
  buildProposal,
  canonicalPath,
  createMappingReport,
  createPreviewDocument,
  digestObject,
  extractAccountId,
  fetchSalesforceSnapshot,
  loadDashboardInput,
  loadFieldMap,
  removePreviewFile,
  resolveOrg,
  slugifyAccountName,
  validateDashboardInput,
  validatePreview,
  verifyFreshness,
  writeProtectedJson,
} from "./day2-enricher-lib.mjs";

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const SCRIPT_DIRECTORY = path.dirname(SCRIPT_PATH);
const TEST_PATH = path.join(SCRIPT_DIRECTORY, "enrich-day2.test.mjs");

function usage() {
  return `Salesforce Day 2 Dashboard Enricher

Usage:
  node enrich-day2.mjs preview --account <001-id-or-account-lightning-url> [options]
  node enrich-day2.mjs build --preview <preview.json> [options]
  node enrich-day2.mjs self-test

Preview options:
  --target-org <org>       Salesforce alias or username. Omit only to use the configured default.
  --input <dashboard.json> Existing schema 1.4 dashboard export to preserve and enrich.
  --output-dir <directory> Preview directory. Default: output/salesforce.
  --preview-output <file>  Explicit confidential preview path.
  --overwrite              Replace the exact preview path if it already exists.

Build options:
  --approve-path <path>    Approve one current conflict. Repeat for each approved path.
  --output <file>          Importable JSON path. Default: beside the preview file.
  --report <file>          Explicit confidential mapping-report path.
  --overwrite              Replace the exact output/report paths if they already exist.

Only Salesforce Account IDs beginning with 001 and Account Lightning URLs are accepted.
There is no bulk conflict approval option.`;
}

function parseOptions(tokens, specification) {
  const values = {};
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (!token.startsWith("--")) {
      throw new EnricherError("INVALID_ARGUMENT", `Unexpected positional argument: ${token}`);
    }
    const name = token.slice(2);
    const type = specification[name];
    if (!type) throw new EnricherError("INVALID_ARGUMENT", `Unknown option: ${token}`);
    if (type === "boolean") {
      values[name] = true;
      continue;
    }
    const next = tokens[index + 1];
    if (next === undefined || next.startsWith("--")) {
      throw new EnricherError("INVALID_ARGUMENT", `${token} requires a value.`);
    }
    index += 1;
    if (type === "repeatable") {
      values[name] ??= [];
      values[name].push(next);
    } else {
      if (values[name] !== undefined) {
        throw new EnricherError("INVALID_ARGUMENT", `${token} may be supplied only once.`);
      }
      values[name] = next;
    }
  }
  return values;
}

function requireOption(options, name) {
  if (!options[name]) throw new EnricherError("MISSING_ARGUMENT", `--${name} is required.`);
  return options[name];
}

async function readPreview(previewPath) {
  const resolvedPath = await canonicalPath(previewPath);
  let value;
  try {
    value = JSON.parse(await readFile(resolvedPath, "utf8"));
  } catch {
    throw new EnricherError("INVALID_PREVIEW", `Preview is not readable JSON: ${resolvedPath}`);
  }
  return { value: validatePreview(value), path: resolvedPath };
}

function summaryCounts(candidates) {
  const counts = { "dated-current": 0, expired: 0, undated: 0 };
  for (const candidate of candidates) counts[candidate.classification] += 1;
  return counts;
}

async function previewCommand(tokens) {
  const options = parseOptions(tokens, {
    account: "value",
    "target-org": "value",
    input: "value",
    "output-dir": "value",
    "preview-output": "value",
    overwrite: "boolean",
  });
  const accountId = extractAccountId(requireOption(options, "account"));
  const [{ value: fieldMap, digest: fieldMapDigest }, input] = await Promise.all([
    loadFieldMap(),
    loadDashboardInput(options.input),
  ]);
  const org = resolveOrg(options["target-org"]);
  const snapshot = fetchSalesforceSnapshot(accountId, org.targetOrg, fieldMap);
  const proposal = buildProposal(snapshot.account, input.value);
  const outputDirectory = path.resolve(
    options["output-dir"] ?? path.join(process.cwd(), "output", "salesforce"),
  );
  const slug = slugifyAccountName(proposal.accountName, accountId);
  const previewPath = path.resolve(
    options["preview-output"] ?? path.join(outputDirectory, `${slug}-day2-preview.json`),
  );

  await assertNoProtectedPathCollision(
    previewPath,
    [input.path, FIELD_MAP_PATH, BLANK_TEMPLATE_PATH],
    "Preview output",
  );
  await assertWritableTargets([previewPath], Boolean(options.overwrite));
  const preview = createPreviewDocument({
    accountId,
    org,
    snapshot,
    input,
    fieldMap,
    fieldMapDigest,
    proposal,
  });
  await writeProtectedJson(
    previewPath,
    preview,
    Boolean(options.overwrite),
    [input.path, FIELD_MAP_PATH, BLANK_TEMPLATE_PATH],
  );

  const fillPaths = proposal.operations
    .filter((operation) => operation.action === "fill")
    .map((operation) => operation.targetPath);
  const conflictPaths = proposal.operations
    .filter((operation) => operation.action === "conflict")
    .map((operation) => operation.targetPath);
  console.log(
    JSON.stringify(
      {
        status: "preview-created",
        confidentialPreview: previewPath,
        dashboardSchemaVersion: DASHBOARD_SCHEMA_VERSION,
        fillPaths,
        conflictPaths,
        timelineEventsToAppend: proposal.timelineOperations.filter((item) => item.action === "append").length,
        skippedMappings: proposal.skips.length,
        missingOptionalAccountFields: snapshot.missingOptionalAccountFields,
        productCandidates: summaryCounts(snapshot.productCandidates),
        productCandidateNotice: "Manual review only; never written into dashboard product fields.",
        next:
          conflictPaths.length > 0
            ? `Run build with --preview ${JSON.stringify(previewPath)} and repeat --approve-path only for explicitly approved conflict paths. Unapproved conflicts are preserved.`
            : `Run build with --preview ${JSON.stringify(previewPath)}.`,
      },
      null,
      2,
    ),
  );
}

async function buildCommand(tokens) {
  const options = parseOptions(tokens, {
    preview: "value",
    "approve-path": "repeatable",
    output: "value",
    report: "value",
    overwrite: "boolean",
  });
  const previewFile = await readPreview(requireOption(options, "preview"));
  const preview = previewFile.value;
  const [{ value: fieldMap, digest: fieldMapDigest }, input] = await Promise.all([
    loadFieldMap(),
    preview.input.kind === "blank-template"
      ? loadDashboardInput()
      : loadDashboardInput(preview.input.path),
  ]);

  const org = resolveOrg(preview.org.username);
  if (org.orgId !== preview.org.orgId || org.username !== preview.org.username) {
    throw new EnricherError(
      "ORG_MISMATCH",
      "The preview's Salesforce org identity no longer matches the resolved connection.",
    );
  }

  const snapshot = fetchSalesforceSnapshot(preview.accountId, org.targetOrg, fieldMap);
  verifyFreshness(preview, {
    fieldMapVersion: fieldMap.version,
    fieldMapDigest,
    inputDigest: input.digest,
    accountLastModifiedDate: snapshot.accountLastModifiedDate,
    accountDigest: snapshot.accountDigest,
    assetDigest: snapshot.assetDigest,
    productCandidateDigest: snapshot.productCandidateDigest,
    classificationAsOf: snapshot.classificationAsOf,
    selectedAccountFields: snapshot.selectedAccountFields,
    missingOptionalAccountFields: snapshot.missingOptionalAccountFields,
    assetQueryFields: snapshot.assetQueryFields,
    assetWarnings: snapshot.assetWarnings,
  });

  const currentProposal = buildProposal(snapshot.account, input.value);
  if (digestObject(currentProposal) !== digestObject(preview.proposal)) {
    throw new EnricherError(
      "PREVIEW_TAMPERED",
      "The stored field-level proposal does not match the fresh deterministic proposal. Create a new preview.",
    );
  }

  const buildResult = applyProposal(
    input.value,
    snapshot.account,
    currentProposal,
    options["approve-path"] ?? [],
    fieldMap.version,
  );
  validateDashboardInput(buildResult.dashboard);
  const outputDirectory = path.dirname(previewFile.path);
  const slug = slugifyAccountName(currentProposal.accountName, preview.accountId);
  const dashboardOutput = path.resolve(
    options.output ?? path.join(outputDirectory, `${slug}-day2-dashboard.json`),
  );
  const reportOutput = path.resolve(
    options.report ?? path.join(outputDirectory, `${slug}-day2-mapping-report.json`),
  );

  const protectedPaths = [input.path, previewFile.path, FIELD_MAP_PATH, BLANK_TEMPLATE_PATH];
  await assertNoProtectedPathCollision(dashboardOutput, protectedPaths, "Dashboard output");
  await assertNoProtectedPathCollision(reportOutput, protectedPaths, "Mapping report output");
  await assertWritableTargets([dashboardOutput, reportOutput], Boolean(options.overwrite));

  const report = createMappingReport({
    preview,
    buildResult,
    snapshot,
    dashboardOutput,
    reportOutput,
    fieldMap,
  });
  await writeProtectedJson(
    dashboardOutput,
    buildResult.dashboard,
    Boolean(options.overwrite),
    protectedPaths,
  );
  await writeProtectedJson(
    reportOutput,
    report,
    Boolean(options.overwrite),
    [...protectedPaths, dashboardOutput],
  );
  await removePreviewFile(previewFile.path);

  console.log(
    JSON.stringify(
      {
        status: "build-complete",
        importableDashboard: dashboardOutput,
        confidentialMappingReport: reportOutput,
        removedTemporaryPreview: previewFile.path,
        unresolvedConflictsPreserved: buildResult.unresolvedConflicts,
        approvedConflictPaths: options["approve-path"] ?? [],
        productCandidates: summaryCounts(snapshot.productCandidates),
        next:
          "In the Day 2 dashboard, click Import JSON and choose the importableDashboard file. Review it, finish unsupported fields manually, then Export JSON to save the editable backup.",
      },
      null,
      2,
    ),
  );
}

function selfTestCommand(tokens) {
  if (tokens.length) throw new EnricherError("INVALID_ARGUMENT", "self-test accepts no options.");
  const result = spawnSync(process.execPath, ["--test", TEST_PATH], {
    encoding: "utf8",
    shell: false,
    stdio: "inherit",
  });
  if (result.error) throw new EnricherError("SELF_TEST_FAILURE", result.error.message);
  if (result.status !== 0) {
    throw new EnricherError("SELF_TEST_FAILURE", `Synthetic self-test exited with status ${result.status}.`);
  }
}

async function main() {
  const [command, ...tokens] = process.argv.slice(2);
  if (!command || command === "--help" || command === "help") {
    console.log(usage());
    return;
  }
  if (tokens.length === 1 && tokens[0] === "--help") {
    console.log(usage());
    return;
  }
  if (command === "preview") return previewCommand(tokens);
  if (command === "build") return buildCommand(tokens);
  if (command === "self-test") return selfTestCommand(tokens);
  throw new EnricherError("INVALID_COMMAND", `Unknown command ${JSON.stringify(command)}.\n\n${usage()}`);
}

main().catch((error) => {
  const code = error instanceof EnricherError ? error.code : "UNEXPECTED_FAILURE";
  const message = error instanceof Error ? error.message : String(error);
  console.error(`ERROR [${code}] ${message}`);
  process.exitCode = 1;
});

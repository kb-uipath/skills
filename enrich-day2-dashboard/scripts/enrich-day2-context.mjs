#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  ContextEnricherError,
  ATTESTATION_KIND,
  MAXIMUM_COVERAGE_MODE,
  PREVIEW_KIND,
  SCRIPT_DIRECTORY,
  assertSafeDerivedTargets,
  buildFromPreview,
  createAttestationBundle,
  createPreviewDocument,
  loadAttestationBundle,
  loadClarificationAnswersFile,
  loadContextPreview,
  loadDashboard,
  loadEvidenceLedger,
  loadSalesforceRevalidationReceipt,
  normalizeCoverageMode,
  slugify,
  writeJsonAtomic,
} from "./day2-context-lib.mjs";

const HELP = `Evidence-Backed Direct-JSON Day 2 Enricher

Usage:
  node enrich-day2-context.mjs preview --input <dashboard.json> --salesforce-report <mapping-report.json> --evidence <ledger.json> [options]
  node enrich-day2-context.mjs clarify --preview <preview.json> --answers <answers.json> [options]
  node enrich-day2-context.mjs build --preview <preview.json> --evidence <same-preview-bound-ledger.json> --salesforce-revalidation <receipt.json> [options]
  node enrich-day2-context.mjs self-test

Preview options:
  --coverage-mode <mode>   strict (default) or maximum evidence-backed draft coverage.
                           Repeat maximum on every re-preview in that session.
  --attestations <file>    Prior confidential clarification bundle.
  --preview-output <file>  Explicit confidential preview path.
  --output-dir <directory> Default preview directory. Default: output/day2.
  --overwrite              Replace only a prior Day 2 context preview at the exact target.

Clarify options:
  --answers <file>         One to three exact Q- answers.
  --attestations <file>    Prior bundle for a derived clarification round.
  --output <file>          New confidential bundle; existing bundles are never overwritten.

Build options:
  --salesforce-revalidation <file>
                           Fresh read-only Salesforce receipt created after this preview.
  --attestations <file>    Exact bundle bound to the preview.
  --approve-proposal <id>  Strict previews only: approve one exact contextual proposal ID.
  --output <file>          Importable schema 1.4 dashboard JSON path.
  --report <file>          Confidential evidence report Markdown path.
  --overwrite              Replace only prior derived Day 2 output/report files at exact targets.

The helper never contacts connected systems. The skill agent performs scoped read-only
collection and source revalidation, then supplies the normalized evidence ledger.
There is no bulk, wildcard, path-only, or prefix approval option. A maximum-coverage
preview includes its deterministic safe selection and rejects approval flags.`;

const PREVIEW_HELP = `Preview contextual Day 2 proposals

Required:
  --input <dashboard.json>    Schema 1.4 JSON produced by the Salesforce child layer.
  --salesforce-report <file>  Matching Salesforce child mapping report.
  --evidence <ledger.json>    Normalized day2-evidence-ledger version 2.

Optional:
  --coverage-mode <mode>     strict (default) or maximum.
  --attestations <file>
  --preview-output <file>
  --output-dir <directory>
  --overwrite`;

const BUILD_HELP = `Build contextual Day 2 JSON

Required:
  --preview <preview.json>
  --evidence <same-preview-bound-ledger.json>
  --salesforce-revalidation <receipt.json>

Optional:
  --attestations <file>          Exact bundle bound to the preview, when present.
  --approve-proposal <full-id>   Strict previews only; repeat for each approved proposal.
  --output <dashboard.json>
  --report <report.md>
  --overwrite

Before build, re-run the recorded connector discovery and re-fetch every depended-on
source. Update only verifiedAt values in the exact same ledger path when content and
scope are unchanged, then build within 60 minutes. Omit all approval flags for a
maximum-coverage preview.`;

const CLARIFY_HELP = `Record one clarification round

Required:
  --preview <preview.json>  Current policy-v3 preview.
  --answers <answers.json>  One to three exact Q- IDs with answered, unknown, or skipped status.

Optional:
  --attestations <file>     Prior bundle to derive a new bundle from.
  --output <file>           New confidential bundle path. Existing files are never overwritten.

Clarification records answers only. It does not modify the dashboard or approve any P- proposal.`;

function parseCommandLine(argv) {
  const command = argv[0] === "--help" || argv[0] === "-h" ? "help" : argv[0] ?? "help";
  const options = new Map();
  const flags = new Set();
  const repeatable = new Set(["--approve-proposal"]);
  const booleanFlags = new Set(["--overwrite", "--help"]);
  const allowedByCommand = {
    preview: new Set(["--input", "--salesforce-report", "--evidence", "--attestations", "--coverage-mode", "--preview-output", "--output-dir", "--overwrite", "--help"]),
    clarify: new Set(["--preview", "--answers", "--attestations", "--output", "--help"]),
    build: new Set(["--preview", "--evidence", "--salesforce-revalidation", "--attestations", "--approve-proposal", "--output", "--report", "--overwrite", "--help"]),
    "self-test": new Set(["--help"]),
    help: new Set(),
  };
  const allowed = allowedByCommand[command];
  if (!allowed) {
    throw new ContextEnricherError("INVALID_COMMAND", `Unknown command ${JSON.stringify(command)}.`);
  }
  for (let index = 1; index < argv.length; index += 1) {
    const token = argv[index];
    if (!allowed.has(token)) {
      throw new ContextEnricherError(
        "INVALID_OPTION",
        `Unknown or forbidden option ${JSON.stringify(token)} for ${command}.`,
      );
    }
    if (booleanFlags.has(token)) {
      if (flags.has(token)) throw new ContextEnricherError("INVALID_OPTION", `Duplicate flag ${token}.`);
      flags.add(token);
      continue;
    }
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) {
      throw new ContextEnricherError("INVALID_OPTION", `${token} requires one value.`);
    }
    index += 1;
    if (repeatable.has(token)) {
      const values = options.get(token) ?? [];
      values.push(value);
      options.set(token, values);
    } else {
      if (options.has(token)) throw new ContextEnricherError("INVALID_OPTION", `Duplicate option ${token}.`);
      options.set(token, value);
    }
  }
  return { command, options, flags };
}

function requiredOption(parsed, name) {
  const value = parsed.options.get(name);
  if (!value || Array.isArray(value)) {
    throw new ContextEnricherError("MISSING_OPTION", `${name} is required.`);
  }
  return value;
}

async function runPreview(parsed) {
  if (parsed.flags.has("--help")) {
    process.stdout.write(`${PREVIEW_HELP}\n`);
    return;
  }
  const inputPath = path.resolve(requiredOption(parsed, "--input"));
  const salesforceReportPath = path.resolve(requiredOption(parsed, "--salesforce-report"));
  const evidencePath = path.resolve(requiredOption(parsed, "--evidence"));
  const attestationsPath = parsed.options.get("--attestations")
    ? path.resolve(parsed.options.get("--attestations"))
    : "";
  const attestations = attestationsPath ? await loadAttestationBundle(attestationsPath) : null;
  const coverageMode = normalizeCoverageMode(parsed.options.get("--coverage-mode") ?? "strict");
  const [dashboard, ledger] = await Promise.all([
    loadDashboard(inputPath),
    loadEvidenceLedger(evidencePath, { attestations }),
  ]);
  const outputDirectory = path.resolve(parsed.options.get("--output-dir") ?? "output/day2");
  const previewPath = path.resolve(
    parsed.options.get("--preview-output") ??
      path.join(
        outputDirectory,
        `${slugify(ledger.account.canonicalName)}-day2-${coverageMode === MAXIMUM_COVERAGE_MODE ? "maximum-coverage-" : ""}context-preview.json`,
      ),
  );
  await assertSafeDerivedTargets([previewPath], [inputPath, salesforceReportPath, evidencePath, attestationsPath]);
  const preview = await createPreviewDocument({
    dashboard,
    inputPath,
    salesforceReportPath,
    ledger,
    evidencePath,
    attestations,
    attestationsPath,
    coverageMode,
  });
  await writeJsonAtomic(previewPath, preview, {
    overwrite: parsed.flags.has("--overwrite"),
    kind: "preview",
  });
  process.stdout.write(`${JSON.stringify({
    kind: PREVIEW_KIND,
    coverageMode: preview.coverageMode,
    maximumCoverageIncluded: preview.maximumCoverageSelection.includedProposalIds.length,
    previewPath,
    eligible: preview.proposals.filter((item) => ["eligible", "no-change"].includes(item.disposition)).length,
    rejected: preview.proposals.filter((item) => !["eligible", "no-change"].includes(item.disposition)).length,
    conflicts: preview.proposals.filter((item) => item.conflict).length,
    warnings: preview.warnings,
    nextQuestions: preview.questionPlan.questions
      .filter((question) => preview.questionPlan.nextQuestionIds.includes(question.questionId))
      .map(({ questionId, prompt }) => ({ questionId, prompt })),
  }, null, 2)}\n`);
}

async function runClarify(parsed) {
  if (parsed.flags.has("--help")) {
    process.stdout.write(`${CLARIFY_HELP}\n`);
    return;
  }
  const previewPath = path.resolve(requiredOption(parsed, "--preview"));
  const answersPath = path.resolve(requiredOption(parsed, "--answers"));
  const priorPath = parsed.options.get("--attestations")
    ? path.resolve(parsed.options.get("--attestations"))
    : "";
  const [preview, answers, priorAttestations] = await Promise.all([
    loadContextPreview(previewPath),
    loadClarificationAnswersFile(answersPath),
    priorPath ? loadAttestationBundle(priorPath) : Promise.resolve(null),
  ]);
  const bundle = await createAttestationBundle({ preview, answers, priorAttestations });
  const outputPath = path.resolve(
    parsed.options.get("--output") ??
      path.join(
        path.dirname(previewPath),
        `${slugify(preview.account.canonicalName)}-day2-attestations-${bundle.integrityDigest.slice(-10)}.json`,
      ),
  );
  await assertSafeDerivedTargets([outputPath], [previewPath, answersPath, priorPath]);
  await writeJsonAtomic(outputPath, bundle, { kind: "attestation" });
  process.stdout.write(`${JSON.stringify({
    kind: ATTESTATION_KIND,
    outputPath,
    accepted: bundle.records.filter((item) => item.status === "answered").length,
    unknown: bundle.records.filter((item) => item.status === "unknown").length,
    skipped: bundle.records.filter((item) => item.status === "skipped").length,
    note: "No dashboard fields or proposals were approved.",
  }, null, 2)}\n`);
}

function defaultBuildPaths(previewPath, preview) {
  const directory = path.dirname(previewPath);
  const slug = slugify(preview.account.canonicalName);
  const suffix = preview.coverageMode === MAXIMUM_COVERAGE_MODE ? "-maximum-coverage-draft" : "";
  return {
    outputPath: path.join(directory, `${slug}-day2${suffix}-dashboard.json`),
    reportPath: path.join(directory, `${slug}-day2${suffix}-evidence-report.md`),
  };
}

async function runBuild(parsed) {
  if (parsed.flags.has("--help")) {
    process.stdout.write(`${BUILD_HELP}\n`);
    return;
  }
  const previewPath = path.resolve(requiredOption(parsed, "--preview"));
  const evidencePath = path.resolve(requiredOption(parsed, "--evidence"));
  const salesforceRevalidationPath = path.resolve(
    requiredOption(parsed, "--salesforce-revalidation"),
  );
  const [preview, salesforceRevalidation] = await Promise.all([
    loadContextPreview(previewPath),
    loadSalesforceRevalidationReceipt(salesforceRevalidationPath),
  ]);
  const attestationsPath = parsed.options.get("--attestations")
    ? path.resolve(parsed.options.get("--attestations"))
    : "";
  const attestations = attestationsPath ? await loadAttestationBundle(attestationsPath) : null;
  const ledger = await loadEvidenceLedger(evidencePath, { attestations });
  const defaults = defaultBuildPaths(previewPath, preview);
  const outputPath = path.resolve(parsed.options.get("--output") ?? defaults.outputPath);
  const reportPath = path.resolve(parsed.options.get("--report") ?? defaults.reportPath);
  const approvedProposalIds = parsed.options.get("--approve-proposal") ?? [];
  const result = await buildFromPreview({
    preview,
    previewPath,
    ledger,
    evidencePath,
    salesforceRevalidation,
    salesforceRevalidationPath,
    attestations,
    attestationsPath,
    approvedProposalIds,
    outputPath,
    reportPath,
    overwrite: parsed.flags.has("--overwrite"),
  });
  process.stdout.write(`${JSON.stringify({
    outputPath: result.outputPath,
    reportPath: result.reportPath,
    acceptedProposalIds: result.acceptedProposalIds,
    coverageMode: result.coverageMode,
    maximumCoverageIncludedProposalIds: result.maximumCoverageIncludedProposalIds,
    unresolvedCoveragePaths: result.unresolvedCoveragePaths,
    remainingBlocks: result.readiness.blocks.length,
    remainingWarnings: result.readiness.warnings.length,
    cleanupWarnings: result.cleanupWarnings,
  }, null, 2)}\n`);
}

function runSelfTest() {
  const testPath = path.join(SCRIPT_DIRECTORY, "enrich-day2-context.test.mjs");
  const salesforceTestPath = path.join(
    path.dirname(SCRIPT_DIRECTORY),
    "salesforce-layer",
    "scripts",
    "enrich-day2.test.mjs",
  );
  const result = spawnSync(process.execPath, ["--test", testPath, salesforceTestPath], {
    cwd: process.cwd(),
    encoding: "utf8",
    stdio: "inherit",
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new ContextEnricherError("SELF_TEST_FAILED", `Synthetic self-test exited with status ${result.status}.`);
  }
}

async function main() {
  const parsed = parseCommandLine(process.argv.slice(2));
  if (parsed.command === "help" || parsed.flags.has("--help") && parsed.command === "self-test") {
    process.stdout.write(`${HELP}\n`);
    return;
  }
  if (parsed.command === "preview") await runPreview(parsed);
  else if (parsed.command === "clarify") await runClarify(parsed);
  else if (parsed.command === "build") await runBuild(parsed);
  else if (parsed.command === "self-test") runSelfTest();
}

main().catch((error) => {
  const code = error instanceof ContextEnricherError ? error.code : "UNEXPECTED_ERROR";
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`${code}: ${message}\n`);
  process.exitCode = 1;
});

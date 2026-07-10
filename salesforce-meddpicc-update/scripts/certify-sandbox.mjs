#!/usr/bin/env node

import fs from "node:fs";
import process from "node:process";
import { fileURLToPath } from "node:url";

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const SCHEMA_VERSION = "salesforce-meddpicc-sandbox-certification/v1";

function check(id, passed, required = true) {
  return { id, required, status: passed ? "passed" : "failed" };
}

function evaluateCertification(evidence = {}, options = {}) {
  const allowWrite = options.allowWrite === true;
  const readChecks = [
    check("sandbox_environment", evidence.environment === "sandbox"),
    check("opportunity_read", evidence.read_succeeded === true),
    check("opportunity_describe", evidence.describe_succeeded === true),
    check("targeted_tests", evidence.targeted_tests_passed === true),
    check("repo_validation", evidence.repo_validation_passed === true),
  ];
  const readOnlyValidated = readChecks.every((item) => item.status === "passed");

  if (!allowWrite) {
    return {
      schema_version: SCHEMA_VERSION,
      mode: "no-write",
      performs_external_writes: false,
      write_probe_opted_in: false,
      certification_status: readOnlyValidated ? "read_only_validated" : "not_certified",
      checks: readChecks,
      next_action: readOnlyValidated
        ? "Retain the read-only evidence or rerun with --allow-write only during an approved sandbox certification window."
        : "Complete the failed read-only checks. The helper will not call Salesforce or Integration Service.",
    };
  }

  const optInChecks = [
    check("explicit_write_acknowledgement", evidence.acknowledge_external_write === true),
    check("approved_change_window", evidence.change_window_approved === true),
    check("recovery_owner", typeof evidence.recovery_owner === "string" && evidence.recovery_owner.trim().length > 0),
  ];
  const writeEvidenceChecks = [
    check("patch_response_204", Number(evidence.patch_response_code) === 204),
    check("read_back_matched", evidence.read_back_matched === true),
    check("duplicate_blocked", evidence.duplicate_operation_blocked === true),
    check("recovery_exercised", evidence.recovery_exercised === true),
    check("cleanup_verified", evidence.cleanup_verified === true),
  ];
  const allChecks = [...readChecks, ...optInChecks, ...writeEvidenceChecks];
  const eligible = [...readChecks, ...optInChecks].every((item) => item.status === "passed");
  const certified = allChecks.every((item) => item.status === "passed");

  return {
    schema_version: SCHEMA_VERSION,
    mode: "sandbox-write-evidence",
    performs_external_writes: false,
    write_probe_opted_in: true,
    write_probe_eligible: eligible,
    certification_status: certified ? "sandbox_certified" : eligible ? "sandbox_write_evidence_incomplete" : "not_certified",
    checks: allChecks,
    next_action: certified
      ? "Store only the redacted certification result and remove confidential confirmation artifacts under the retention policy."
      : eligible
        ? "Run the approved sandbox workflow manually, recover by read-back instead of PATCH retry, then provide redacted evidence."
        : "Resolve failed safety gates before any manual sandbox write probe.",
  };
}

function readPayload(argv) {
  const inputIndex = argv.indexOf("--input");
  if (inputIndex !== -1) {
    const file = argv[inputIndex + 1];
    if (!file) throw new Error("--input requires a file path");
    return JSON.parse(fs.readFileSync(file, "utf8"));
  }
  const stdin = fs.readFileSync(0, "utf8").trim();
  return stdin ? JSON.parse(stdin) : {};
}

function usage() {
  return [
    "Usage: node scripts/certify-sandbox.mjs [--input evidence.json] [--allow-write]",
    "",
    "The helper evaluates redacted evidence only and never performs external reads or writes.",
    "Without --allow-write it ignores write evidence and remains in no-write mode.",
  ].join("\n");
}

function main(argv = process.argv.slice(2)) {
  if (argv.includes("--help") || argv.includes("-h")) {
    process.stdout.write(`${usage()}\n`);
    return;
  }
  const result = evaluateCertification(readPayload(argv), { allowWrite: argv.includes("--allow-write") });
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

if (SCRIPT_PATH === process.argv[1]) {
  try {
    main();
  } catch (error) {
    process.stderr.write(`${JSON.stringify({
      error: {
        code: "CERTIFICATION_INPUT_ERROR",
        message: error.message,
        nextAction: "Fix the local evidence payload. No external operation was attempted.",
      },
    }, null, 2)}\n`);
    process.exitCode = 1;
  }
}

export { SCHEMA_VERSION, evaluateCertification };

import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const script = path.resolve(__dirname, "..", "scripts", "meddpicc.mjs");
const fixtureDir = path.join(__dirname, "fixtures");
const loadFixture = (name) => JSON.parse(fs.readFileSync(path.join(fixtureDir, name), "utf8"));

function run(command, payload, args = []) {
  const result = spawnSync(process.execPath, [script, command, ...args], {
    input: JSON.stringify(payload),
    encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

function runFail(command, payload, args = []) {
  const result = spawnSync(process.execPath, [script, command, ...args], {
    input: JSON.stringify(payload),
    encoding: "utf8",
  });
  assert.notEqual(result.status, 0);
  return JSON.parse(result.stderr).error;
}

test("CLI smoke covers all public subcommands", () => {
  const current = loadFixture("current-opportunity.json");
  const describe = loadFixture("describe-opportunity.json");

  const parsed = run("parse-id", { input: `Opportunity ${current.Id}` });
  assert.equal(parsed.opportunityId, current.Id);

  const prepared = run("draft", {
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-20",
    current,
    generatedAt: "2026-05-20T14:00:00.000Z",
    content: { NextStep: "Confirm procurement owner." },
  });
  assert.equal(prepared.proposedFields.NextStep, "Confirm procurement owner.");

  const confirmation = run("receipt", {
    draft: prepared,
    confirmed: true,
    confirmedAt: "2026-05-20T14:00:30.000Z",
    confirmedBy: "Keith Born",
  }, ["--mode", "confirmation"]);
  assert.equal(confirmation.classification, "confidential");

  const patch = run("build-patch", {
    draft: prepared,
    describe,
    connectionId: "conn-secret-123",
    freshLastModifiedDate: current.LastModifiedDate,
    confirmation,
    transaction: confirmation.transaction,
    now: "2026-05-20T14:01:00.000Z",
  });
  assert.equal(patch.envelope.method, "PATCH");

  const verified = run("verify", {
    draft: prepared,
    transaction: patch.transaction,
    response: loadFixture("patch-success.json"),
    readBack: { ...current, NextStep: "Confirm procurement owner." },
  });
  assert.equal(verified.readBackStatus, "all_matched");

  const redacted = run("receipt", { draft: prepared, confirmation, patch, verification: verified }, ["--mode", "audit"]);
  assert.equal(redacted.classification, "internal");
  assert.equal("patch" in redacted, false);

  const recovered = run("recover", {
    draft: prepared,
    transaction: patch.transaction,
    checkedAt: "2026-05-20T14:02:00.000Z",
    readBack: { ...current, NextStep: "Confirm procurement owner." },
  });
  assert.equal(recovered.resolution, "verified_no_retry");

  const classified = run("classify-error", loadFixture("connection-missing.json"));
  assert.equal(classified.code, "CONNECTION_MISSING");

  const telemetry = run("build-telemetry", {
    now: "2026-05-20T14:02:00.000Z",
    skillVersion: "1.1.0",
    skillSha: "abc123",
    runId: "run-1",
    verify: verified,
    opportunityName: "Do Not Leak",
  });
  assert.equal(telemetry.oppId, current.Id);
  assert.deepEqual(telemetry.fieldsTargeted, ["NextStep"]);
  assert.equal("opportunityName" in telemetry, false);
});

test("CLI emits structured errors for invalid commands and stale write payloads", () => {
  const current = loadFixture("current-opportunity.json");
  const describe = loadFixture("describe-opportunity.json");
  const prepared = run("draft", {
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-20",
    current,
    generatedAt: "2026-05-20T14:00:00.000Z",
    content: { NextStep: "Confirm procurement owner." },
  });
  const confirmation = run("receipt", {
    draft: prepared,
    confirmed: true,
    confirmedAt: "2026-05-20T14:00:30.000Z",
  }, ["--mode", "confirmation"]);

  const missingConnection = runFail("build-patch", {
    draft: prepared,
    describe,
    freshLastModifiedDate: current.LastModifiedDate,
    confirmation,
    transaction: confirmation.transaction,
    now: "2026-05-20T14:01:00.000Z",
  });
  assert.equal(missingConnection.code, "MISSING_CONNECTION_ID");
  assert.equal(missingConnection.recoverable, true);

  const legacyReceipt = runFail("receipt", { mode: "confirmation", draft: prepared, confirmed: true, confirmedAt: "2026-05-20T14:00:30.000Z" });
  assert.equal(legacyReceipt.code, "RECEIPT_MODE_REQUIRED");

  const unknown = runFail("not-a-command", {});
  assert.equal(unknown.code, "UNKNOWN_COMMAND");
});

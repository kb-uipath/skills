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

function run(command, payload) {
  const result = spawnSync(process.execPath, [script, command], {
    input: JSON.stringify(payload),
    encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
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

  const patch = run("build-patch", {
    draft: prepared,
    describe,
    connectionId: "conn-secret-123",
    now: "2026-05-20T14:01:00.000Z",
  });
  assert.equal(patch.envelope.method, "PATCH");

  const verified = run("verify", {
    draft: prepared,
    response: loadFixture("patch-success.json"),
    readBack: { ...current, NextStep: "Confirm procurement owner." },
  });
  assert.equal(verified.readBackStatus, "all_matched");

  const redacted = run("receipt", { draft: prepared, patch });
  assert.equal(redacted.patch.connection, "[REDACTED]");

  const classified = run("classify-error", loadFixture("connection-missing.json"));
  assert.equal(classified.code, "CONNECTION_MISSING");
});

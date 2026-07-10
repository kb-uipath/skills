import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { evaluateCertification } from "../scripts/certify-sandbox.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const script = path.resolve(__dirname, "..", "scripts", "certify-sandbox.mjs");

const readEvidence = {
  environment: "sandbox",
  read_succeeded: true,
  describe_succeeded: true,
  targeted_tests_passed: true,
  repo_validation_passed: true,
};

test("sandbox certification defaults to no-write evidence evaluation", () => {
  const result = spawnSync(process.execPath, [script], {
    input: JSON.stringify({
      ...readEvidence,
      acknowledge_external_write: true,
      patch_response_code: 204,
    }),
    encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  const output = JSON.parse(result.stdout);
  assert.equal(output.mode, "no-write");
  assert.equal(output.performs_external_writes, false);
  assert.equal(output.write_probe_opted_in, false);
  assert.equal(output.certification_status, "read_only_validated");
});

test("sandbox write certification requires explicit opt-in and complete redacted evidence", () => {
  const evidence = {
    ...readEvidence,
    acknowledge_external_write: true,
    change_window_approved: true,
    recovery_owner: "assigned",
    patch_response_code: 204,
    read_back_matched: true,
    duplicate_operation_blocked: true,
    recovery_exercised: true,
    cleanup_verified: true,
  };
  const before = structuredClone(evidence);
  const output = evaluateCertification(evidence, { allowWrite: true });
  assert.equal(output.mode, "sandbox-write-evidence");
  assert.equal(output.performs_external_writes, false);
  assert.equal(output.write_probe_eligible, true);
  assert.equal(output.certification_status, "sandbox_certified");
  assert.deepEqual(evidence, before);
});

test("production evidence can never qualify for a sandbox write probe", () => {
  const output = evaluateCertification({
    ...readEvidence,
    environment: "production",
    acknowledge_external_write: true,
    change_window_approved: true,
    recovery_owner: "assigned",
  }, { allowWrite: true });
  assert.equal(output.write_probe_eligible, false);
  assert.equal(output.certification_status, "not_certified");
});

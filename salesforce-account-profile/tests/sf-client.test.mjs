import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";

import { batchIds, SfClient } from "../scripts/sf-client.mjs";
import { CONTRACTS } from "../scripts/constants.mjs";
import { preflight } from "../scripts/workflow.mjs";

function childWithJson(payload, code = 0) {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.kill = () => {};
  queueMicrotask(() => {
    child.stdout.emit("data", Buffer.from(JSON.stringify(payload)));
    child.emit("close", code);
  });
  return child;
}

test("batching handles 0, 1, 200, and 201 IDs deterministically", () => {
  assert.deepEqual(batchIds([]), []);
  assert.deepEqual(batchIds(["a"]), [["a"]]);
  assert.deepEqual(batchIds(Array.from({ length: 200 }, (_, index) => `${index}`)).map((x) => x.length), [200]);
  assert.deepEqual(batchIds(Array.from({ length: 201 }, (_, index) => `${index}`)).map((x) => x.length), [200, 1]);
});

test("Salesforce CLI uses argv arrays with shell false", async () => {
  let captured;
  const runner = (file, args, options) => {
    captured = { file, args, options };
    return childWithJson({ result: { id: "00D", username: "u", instanceUrl: "https://example.invalid" } });
  };
  const client = new SfClient({ sfPath: "synthetic-sf", targetOrg: "alias; touch CODE_EXECUTION_SENTINEL", runner });
  await client.orgDisplay();
  assert.equal(captured.file, "synthetic-sf");
  assert.deepEqual(captured.args, ["org", "display", "--target-org", "alias; touch CODE_EXECUTION_SENTINEL", "--json"]);
  assert.equal(captured.options.shell, false);
});

test("workflow test injection is explicit and never read from process environment", async () => {
  let captured;
  const runner = (file, args, options) => {
    captured = { file, args, options };
    return childWithJson({
      result: {
        id: "00D000000000001AAA",
        username: "synthetic@example.invalid",
        instanceUrl: "https://synthetic.example.invalid",
      },
    });
  };
  await preflight({
    schema_version: CONTRACTS.preflightRequest,
    target_org: "explicit-alias",
  }, { runner, sfPath: "/synthetic/test-only/sf" });
  assert.equal(captured.file, "/synthetic/test-only/sf");
  assert.equal(captured.options.shell, false);
});

test("production Salesforce client cannot be created without an enrolled command specification", () => {
  assert.throws(() => new SfClient({ targetOrg: "synthetic" }), { code: "SF_RUNTIME_NOT_ENROLLED" });
});

test("query rejects incomplete and truncated results", async () => {
  const runner = () => childWithJson({ result: { totalSize: 2, done: false, records: [{ Id: "x" }] } });
  const client = new SfClient({ sfPath: "synthetic-sf", targetOrg: "synthetic", runner });
  await assert.rejects(() => client.query("SELECT Id FROM Account"), { code: "TRUNCATED_QUERY_RESULT" });
});

test("query completeness requires explicit boolean done and integer totalSize", async () => {
  for (const result of [
    { totalSize: 0, records: [] },
    { totalSize: 0, done: "true", records: [] },
    { totalSize: "0", done: true, records: [] },
    { totalSize: -1, done: true, records: [] },
  ]) {
    const client = new SfClient({ sfPath: "synthetic-sf", targetOrg: "synthetic", runner: () => childWithJson({ result }) });
    await assert.rejects(() => client.query("SELECT Id FROM Account"), { code: "TRUNCATED_QUERY_RESULT" });
  }
});

test("CLI failures expose no raw stdout or stderr details", async () => {
  const runner = () => childWithJson({ message: "INVALID_SESSION unfamiliar-secret-shape" }, 1);
  const client = new SfClient({ sfPath: "synthetic-sf", targetOrg: "synthetic", runner });
  await assert.rejects(async () => {
    try {
      await client.query("SELECT Id FROM Account");
    } catch (error) {
      assert.equal(error.details, undefined);
      assert.equal(error.message, "Salesforce CLI command failed");
      throw error;
    }
  }, { code: "SCHEMA_OR_AUTHORIZATION_FAILURE" });
});

test("query rejects unauthorized responses without returning raw output", async () => {
  const runner = () => childWithJson({ message: "INVALID_SESSION Bearer secret.value" }, 1);
  const client = new SfClient({ sfPath: "synthetic-sf", targetOrg: "synthetic", runner });
  await assert.rejects(() => client.query("SELECT Id FROM Account"), { code: "SCHEMA_OR_AUTHORIZATION_FAILURE" });
});

test("query count cap stops the thirty-first data query", async () => {
  const runner = () => childWithJson({ result: { totalSize: 0, done: true, records: [] } });
  const client = new SfClient({ sfPath: "synthetic-sf", targetOrg: "synthetic", runner });
  for (let index = 0; index < 30; index += 1) await client.query("SELECT Id FROM Account");
  await assert.rejects(() => client.query("SELECT Id FROM Account"), { code: "QUERY_CAP_EXCEEDED" });
});

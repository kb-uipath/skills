import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import test from "node:test";

import { CONTRACTS } from "../scripts/constants.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const testCli = join(here, "fixtures", "run-cli.cjs");
const fixedNow = "2030-01-01T00:00:00.000Z";

async function invoke(command, input, stateRoot) {
  return await new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [testCli, command], {
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...process.env,
        SFAP_TEST_NOW: fixedNow,
        SFAP_TEST_STATE_ROOT: stateRoot,
      },
    });
    const stdout = [];
    const stderr = [];
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.on("error", reject);
    child.on("close", (code) => {
      resolve({
        code,
        stdout: Buffer.concat(stdout).toString("utf8"),
        stderr: Buffer.concat(stderr).toString("utf8"),
      });
    });
    child.stdin.end(JSON.stringify(input));
  });
}

async function invokeOk(command, input, stateRoot) {
  const execution = await invoke(command, input, stateRoot);
  assert.equal(execution.code, 0, execution.stderr);
  assert.equal(execution.stderr, "");
  return JSON.parse(execution.stdout);
}

async function enrolledState(t) {
  const stateRoot = await mkdtemp(join(tmpdir(), "sf-profile-cli-v2-"));
  t.after(async () => {
    await rm(stateRoot, { recursive: true, force: true });
  });
  const diagnosis = await invokeOk("doctor", {
    schema_version: CONTRACTS.doctorRequest,
    target_org: "synthetic-complete",
    friendly_label: "Synthetic UAT",
    environment: "sandbox",
  }, stateRoot);
  assert.equal(diagnosis.status, "ready");
  assert.equal(JSON.stringify(diagnosis).includes("SECRET_SHOULD_NOT_ESCAPE"), false);
  return stateRoot;
}

function startRequest() {
  return {
    schema_version: CONTRACTS.startRequest,
    target_org: "Synthetic UAT",
    account_selector: {
      mode: "exact_name",
      value: "Example Holdings",
    },
  };
}

test("public CLI resumes a selected-account pipeline across processes", async (t) => {
  const stateRoot = await enrolledState(t);
  const started = await invokeOk("start", startRequest(), stateRoot);
  assert.equal(started.status, "awaiting_decision");
  assert.equal(started.next_action, "confirm_org_and_plan");

  const resumed = await invokeOk("status", {
    schema_version: CONTRACTS.statusRequest,
    session_id: started.session_id,
  }, stateRoot);
  assert.equal(resumed.status, "active");
  assert.equal(resumed.summary.state, "org_confirmation");
  assert.equal(resumed.summary.preset, "pipeline");

  const completed = await invokeOk("continue", {
    schema_version: CONTRACTS.continueRequest,
    session_id: started.session_id,
    decision: { action: "confirm_org_and_plan" },
  }, stateRoot);
  assert.equal(completed.status, "complete");
  assert.equal(completed.next_action, null);
  assert.match(completed.message, /## Decision Summary/u);
  assert.equal(completed.message.includes("schema_version"), false);
  assert.equal(completed.message.includes("digest"), false);

  const expired = await invoke("status", {
    schema_version: CONTRACTS.statusRequest,
    session_id: started.session_id,
  }, stateRoot);
  assert.equal(expired.code, 2);
  const safeError = JSON.parse(expired.stderr);
  assert.equal(safeError.error.code, "SESSION_NOT_FOUND");
  assert.deepEqual(Object.keys(safeError.error).sort(), ["code", "message"]);
});

test("public CLI abort deletes resumable state without exposing internals", async (t) => {
  const stateRoot = await enrolledState(t);
  const started = await invokeOk("start", startRequest(), stateRoot);
  const aborted = await invokeOk("abort", {
    schema_version: CONTRACTS.abortRequest,
    session_id: started.session_id,
  }, stateRoot);
  assert.equal(aborted.status, "canceled");
  assert.equal(aborted.next_action, "cancel");
  assert.match(aborted.message, /canceled and deleted/u);
});

test("public CLI errors omit raw details and redact token-shaped text", async (t) => {
  const stateRoot = await enrolledState(t);
  const execution = await invoke("start", {
    schema_version: CONTRACTS.startRequest,
    target_org: "Synthetic UAT",
    account_selector: {
      mode: "exact_name",
      value: "Example Holdings",
    },
    access_token: "00D000000000001!SECRET_SHOULD_NOT_ESCAPE",
  }, stateRoot);
  assert.equal(execution.code, 2);
  assert.equal(execution.stdout, "");
  assert.equal(execution.stderr.includes("SECRET_SHOULD_NOT_ESCAPE"), false);
  const safeError = JSON.parse(execution.stderr);
  assert.equal(safeError.error.code, "UNKNOWN_INPUT_FIELD");
  assert.deepEqual(Object.keys(safeError.error).sort(), ["code", "message"]);
});

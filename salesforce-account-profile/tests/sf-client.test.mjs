import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";

import {
  batchIds,
  redactOrgListPayload,
  SfClient,
} from "../scripts/sf-client.mjs";
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

test("org discovery emits only redacted allowlisted identity fields", async () => {
  let captured;
  const client = new SfClient({
    commandSpec: {
      executable: "/synthetic/sf",
      fixedArgs: [],
      attestationDigest: "a".repeat(64),
    },
    targetOrg: "unused",
    runner: (file, args, options) => {
      captured = { file, args, options };
      return childWithJson({
        result: {
          sandboxes: [{
            alias: "UAT",
            username: "operator@example.invalid",
            orgId: "00D000000000001AAA",
            instanceUrl: "https://sandbox.example.invalid/services/data",
            connectedStatus: "Connected",
            accessToken: "00D000000000001!SECRET",
          }],
          other: [{
            alias: "Production",
            username: "admin@example.invalid",
            orgId: "00D000000000002AAA",
            instanceUrl: "https://production.example.invalid",
          }],
          devHubs: [],
          scratchOrgs: [],
          nonScratchOrgs: [{
            accessToken: "duplicate-secret",
          }],
        },
      });
    },
  });
  const result = await client.orgList();
  assert.deepEqual(captured.args, [
    "org",
    "list",
    "--skip-connection-status",
    "--json",
  ]);
  assert.equal(captured.options.shell, false);
  assert.deepEqual(result, [{
    alias: "Production",
    masked_username: "a***@example.invalid",
    org_id_suffix: "002AAA",
    instance_host: "production.example.invalid",
    org_type: "production_or_developer",
    status: "not_checked",
  }, {
    alias: "UAT",
    masked_username: "o***@example.invalid",
    org_id_suffix: "001AAA",
    instance_host: "sandbox.example.invalid",
    org_type: "sandbox",
    status: "Connected",
  }]);
  const serialized = JSON.stringify(result);
  for (const forbidden of [
    "operator@example.invalid",
    "admin@example.invalid",
    "00D000000000001AAA",
    "00D000000000002AAA",
    "SECRET",
    "accessToken",
    "/services/data",
  ]) {
    assert.equal(serialized.includes(forbidden), false);
  }
});

test("org discovery rejects malformed identity metadata and deterministic over-cap lists", () => {
  const base = {
    result: {
      sandboxes: [],
      other: [],
      devHubs: [],
      scratchOrgs: [],
    },
  };
  assert.throws(
    () => redactOrgListPayload({
      result: {
        ...base.result,
        other: [{
          alias: "Production",
          username: "operator@example.invalid",
          orgId: "not-an-org",
          instanceUrl: "https://example.invalid",
        }],
      },
    }),
    { code: "MALFORMED_ORG_LIST" },
  );
  assert.throws(
    () => redactOrgListPayload({
      result: {
        ...base.result,
        scratchOrgs: Array.from({ length: 201 }, () => ({})),
      },
    }),
    { code: "ORG_LIST_CAP_EXCEEDED" },
  );
  assert.throws(
    () => redactOrgListPayload({ result: { sandboxes: [] } }),
    { code: "MALFORMED_ORG_LIST" },
  );
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

test("describe exposes only sorted active Opportunity StageName values", async () => {
  const runner = () => childWithJson({
    result: {
      fields: [
        {
          name: "StageName",
          type: "picklist",
          filterable: true,
          picklistValues: [
            { active: true, label: "Qualification label", value: "Qualification" },
            { active: false, label: "Retired label", value: "Retired" },
            { active: true, label: "Discovery label", value: "Discovery" },
          ],
        },
        {
          name: "CurrencyIsoCode",
          type: "picklist",
          filterable: true,
          picklistValues: [{ active: true, label: "US Dollar", value: "USD" }],
        },
      ],
    },
  });
  const client = new SfClient({ sfPath: "synthetic-sf", targetOrg: "synthetic", runner });
  const describe = await client.describe("Opportunity");
  assert.deepEqual(
    describe.get("StageName").activePicklistValues,
    ["Discovery", "Qualification"],
  );
  assert.deepEqual(describe.get("CurrencyIsoCode").activePicklistValues, []);
  assert.equal("label" in describe.get("StageName"), false);
  assert.equal(Object.isFrozen(describe.get("StageName").activePicklistValues), true);
});

test("describe rejects malformed, unsafe, duplicate, and oversized active StageName values", async () => {
  const invalidLists = [
    null,
    [{ active: "true", value: "Qualification" }],
    [{ active: true, value: `Unsafe\u202eStage` }],
    [{ active: true, value: "x".repeat(81) }],
    [
      { active: true, value: "Qualification" },
      { active: true, value: "Qualification" },
    ],
    Array.from({ length: 1_001 }, (_, index) => ({
      active: true,
      value: `Stage ${index}`,
    })),
  ];
  for (const picklistValues of invalidLists) {
    const runner = () => childWithJson({
      result: {
        fields: [{
          name: "StageName",
          type: "picklist",
          filterable: true,
          picklistValues,
        }],
      },
    });
    const client = new SfClient({ sfPath: "synthetic-sf", targetOrg: "synthetic", runner });
    await assert.rejects(
      () => client.describe("Opportunity"),
      { code: "MALFORMED_DESCRIBE" },
    );
  }
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
  }, { code: "AUTHENTICATION_FAILURE" });
});

test("Salesforce CLI timeout kills a stalled child and exposes only a safe error", async () => {
  let killSignal = null;
  const runner = () => {
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.kill = (signal) => {
      killSignal = signal;
      return true;
    };
    queueMicrotask(() => {
      child.stdout.emit(
        "data",
        Buffer.from('{"accessToken":"SECRET_SHOULD_NOT_ESCAPE"'),
      );
      child.stderr.emit(
        "data",
        Buffer.from("Bearer secret.value"),
      );
    });
    return child;
  };
  const client = new SfClient({
    sfPath: "synthetic-sf",
    targetOrg: "synthetic",
    runner,
    commandTimeoutMs: 20,
  });
  await assert.rejects(
    () => client.query("SELECT Id FROM Account"),
    (error) => {
      assert.equal(error.code, "SF_COMMAND_TIMEOUT");
      assert.equal(
        error.message,
        "Salesforce CLI command exceeded its execution timeout",
      );
      assert.equal(error.details, undefined);
      assert.equal(
        JSON.stringify(error).includes("SECRET_SHOULD_NOT_ESCAPE"),
        false,
      );
      assert.equal(JSON.stringify(error).includes("secret.value"), false);
      return true;
    },
  );
  assert.equal(killSignal, "SIGKILL");
});

test("query rejects unauthorized responses without returning raw output", async () => {
  const runner = () => childWithJson({ message: "INVALID_SESSION Bearer secret.value" }, 1);
  const client = new SfClient({ sfPath: "synthetic-sf", targetOrg: "synthetic", runner });
  await assert.rejects(() => client.query("SELECT Id FROM Account"), { code: "AUTHENTICATION_FAILURE" });
});

test("CLI failures distinguish authentication, permissions, and schema without leaking output", async () => {
  const cases = [
    ["INVALID_SESSION_ID unfamiliar-secret-shape", "AUTHENTICATION_FAILURE"],
    ["INSUFFICIENT_ACCESS unfamiliar-secret-shape", "PERMISSION_DENIED"],
    ["INVALID_FIELD unfamiliar-secret-shape", "SCHEMA_FAILURE"],
  ];
  for (const [message, code] of cases) {
    const client = new SfClient({
      sfPath: "synthetic-sf",
      targetOrg: "synthetic",
      runner: () => childWithJson({ message }, 1),
    });
    await assert.rejects(
      () => client.query("SELECT Id FROM Account"),
      (error) => {
        assert.equal(error.code, code);
        assert.equal(error.message, "Salesforce CLI command failed");
        assert.equal(error.details, undefined);
        assert.equal(JSON.stringify(error).includes("unfamiliar-secret-shape"), false);
        return true;
      },
    );
  }
});

test("query count cap stops the thirty-first data query", async () => {
  const runner = () => childWithJson({ result: { totalSize: 0, done: true, records: [] } });
  const client = new SfClient({ sfPath: "synthetic-sf", targetOrg: "synthetic", runner });
  for (let index = 0; index < 30; index += 1) await client.query("SELECT Id FROM Account");
  await assert.rejects(() => client.query("SELECT Id FROM Account"), { code: "QUERY_CAP_EXCEEDED" });
});

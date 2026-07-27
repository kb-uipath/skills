import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { CONTRACTS } from "../scripts/constants.mjs";
import {
  abort,
  continueConversation,
  doctor,
  start,
  status,
} from "../scripts/orchestrator.mjs";
import { SafetyError } from "../scripts/security.mjs";
import { SfClient } from "../scripts/sf-client.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const fakeSf = join(here, "fixtures", "fake-sf");
const FIXED_NOW = Date.parse("2030-01-01T00:00:00.000Z");
const THIRTY_MINUTES = 30 * 60 * 1_000;

function client(targetOrg) {
  return new SfClient({
    commandSpec: {
      executable: fakeSf,
      fixedArgs: [],
      attestationDigest: "a".repeat(64),
    },
    targetOrg,
  });
}

async function syntheticJourney({
  alias = "synthetic-complete",
  friendlyLabel = "UAT",
} = {}) {
  const stateRoot = await mkdtemp(join(tmpdir(), "sf-profile-forward-"));
  let currentTime = FIXED_NOW;
  let fault = null;
  const queries = [];
  const internalErrors = [];
  const clientFactory = async (targetOrg) => {
    const instance = client(targetOrg);
    const originalQuery = instance.query.bind(instance);
    instance.query = async (soql) => {
      queries.push(soql);
      if (fault
        && (!fault.pattern || fault.pattern.test(soql))) {
        throw new SafetyError(
          fault.code,
          "synthetic failure detail must remain private",
        );
      }
      return await originalQuery(soql);
    };
    return instance;
  };
  const dependencies = {
    stateRoot,
    clientFactory,
    allowOfflineExecution: true,
    now: () => new Date(currentTime),
    onInternalError(error) {
      internalErrors.push(error);
    },
  };
  const diagnosis = await doctor({
    schema_version: CONTRACTS.doctorRequest,
    target_org: alias,
    friendly_label: friendlyLabel,
    environment: "sandbox",
  }, dependencies);
  return {
    alias,
    friendlyLabel,
    stateRoot,
    dependencies,
    diagnosis,
    queries,
    internalErrors,
    advance(milliseconds) {
      currentTime += milliseconds;
    },
    failNext(code, pattern = null) {
      fault = { code, pattern };
    },
    clearFailure() {
      fault = null;
    },
    clearQueries() {
      queries.length = 0;
    },
    freshContext() {
      return {
        stateRoot,
        clientFactory,
        allowOfflineExecution: true,
        now: () => new Date(currentTime),
        onInternalError(error) {
          internalErrors.push(error);
        },
      };
    },
    async cleanup() {
      await rm(stateRoot, { recursive: true, force: true });
    },
  };
}

function startRequest(targetOrg, overrides = {}) {
  return {
    schema_version: CONTRACTS.startRequest,
    target_org: targetOrg,
    account_selector: {
      mode: "exact_name",
      value: "Example Holdings",
    },
    ...overrides,
  };
}

function continuation(sessionId, decision) {
  return {
    schema_version: CONTRACTS.continueRequest,
    session_id: sessionId,
    decision,
  };
}

function statusRequest(sessionId) {
  return {
    schema_version: CONTRACTS.statusRequest,
    session_id: sessionId,
  };
}

function assertNoPrivateRuntimeOutput(...results) {
  const serialized = JSON.stringify(results);
  assert.doesNotMatch(serialized, /SECRET_SHOULD_NOT_ESCAPE/u);
  assert.doesNotMatch(serialized, /accessToken/iu);
  assert.doesNotMatch(serialized, /Bearer\s+[A-Za-z0-9._-]+/iu);
  assert.doesNotMatch(
    serialized,
    /00D[A-Za-z0-9]{10,}![A-Za-z0-9._-]{10,}/u,
  );
}

function assertComplete(result, run) {
  assert.equal(
    result.status,
    "complete",
    run.internalErrors.map((error) =>
      `${error.code}: ${error.message}`).join("\n"),
  );
  assert.equal(result.next_action, null);
  assertNoPrivateRuntimeOutput(result);
}

test("forward journey: a unique pipeline completes after one business confirmation", async () => {
  const run = await syntheticJourney();
  try {
    const started = await start(
      startRequest("UAT"),
      run.dependencies,
    );
    assert.equal(started.next_action, "confirm_org_and_plan");

    const completed = await continueConversation(
      continuation(started.session_id, {
        action: "confirm_org_and_plan",
      }),
      run.dependencies,
    );
    assertComplete(completed, run);
    assert.match(completed.message, /## Decision Summary/u);
    assert.match(completed.message, /Open opportunities/u);
    assert.match(completed.message, /Synthetic Owner/u);
    await assert.rejects(
      () => status(
        statusRequest(started.session_id),
        run.dependencies,
      ),
      { code: "SESSION_NOT_FOUND" },
    );
  } finally {
    await run.cleanup();
  }
});

test("forward journey: ambiguous exact Account requires an explicit chooser", async () => {
  const run = await syntheticJourney({
    alias: "synthetic-ambiguous",
    friendlyLabel: "Ambiguous UAT",
  });
  try {
    const started = await start(
      startRequest("Ambiguous UAT", {
        account_selector: {
          mode: "exact_name",
          value: "Repeated Name",
        },
      }),
      run.dependencies,
    );
    const chooser = await continueConversation(
      continuation(started.session_id, {
        action: "confirm_org_and_plan",
      }),
      run.dependencies,
    );
    assert.equal(chooser.status, "awaiting_decision");
    assert.equal(chooser.next_action, "choose_account");
    assert.equal(chooser.choices.length, 2);
    assert.equal(
      chooser.choices.every((choice) =>
        choice.Id
        && choice.Name
        && choice.OwnerName),
      true,
    );

    const completed = await continueConversation(
      continuation(started.session_id, {
        action: "choose_account",
        account_id: chooser.choices[1].Id,
      }),
      run.dependencies,
    );
    assertComplete(completed, run);
    assert.match(completed.message, /Repeated Name/u);
  } finally {
    await run.cleanup();
  }
});

test("forward journey: no exact match requires literal-prefix search and explicit selection", async () => {
  const run = await syntheticJourney({
    alias: "synthetic-no-match",
    friendlyLabel: "No Match UAT",
  });
  try {
    const started = await start(
      startRequest("No Match UAT", {
        account_selector: {
          mode: "exact_name",
          value: "Example",
        },
      }),
      run.dependencies,
    );
    const noMatch = await continueConversation(
      continuation(started.session_id, {
        action: "confirm_org_and_plan",
      }),
      run.dependencies,
    );
    assert.equal(noMatch.next_action, "choose_account");
    assert.deepEqual(noMatch.choices, []);

    const prefix = await continueConversation(
      continuation(started.session_id, {
        action: "choose_account",
        literal_prefix: "Example",
      }),
      run.dependencies,
    );
    assert.equal(prefix.next_action, "choose_account");
    assert.equal(prefix.choices.length, 1);

    const completed = await continueConversation(
      continuation(started.session_id, {
        action: "choose_account",
        account_id: prefix.choices[0].Id,
      }),
      run.dependencies,
    );
    assertComplete(completed, run);
  } finally {
    await run.cleanup();
  }
});

test("forward journey: family plan change invalidates approval, then completes with safe currency boundaries", async () => {
  const run = await syntheticJourney();
  try {
    const started = await start(
      startRequest("UAT", {
        preset: "custom",
        sections: [
          "overview",
          "family",
          "opportunities",
          "products",
          "team",
        ],
        scope: "corporate_family",
        opportunity_scope: "all",
      }),
      run.dependencies,
    );
    const family = await continueConversation(
      continuation(started.session_id, {
        action: "confirm_org_and_plan",
      }),
      run.dependencies,
    );
    assert.equal(family.next_action, "approve_family_scope");
    assert.deepEqual(family.account_ids, [
      "001000000000001AAA",
      "001000000000002AAA",
    ]);
    assert.equal(
      family.corporate_family_accounts.every((account) =>
        account.Id && account.Name),
      true,
    );

    run.failNext(
      "OPPORTUNITY_CAP_EXCEEDED",
      /\bFROM Opportunity\b/u,
    );
    const capped = await continueConversation(
      continuation(started.session_id, {
        action: "approve_family_scope",
      }),
      run.dependencies,
    );
    assert.equal(capped.status, "awaiting_decision");
    assert.equal(capped.next_action, "narrow_query");
    assert.ok(capped.narrowing_options.includes("close_date_window"));

    run.clearFailure();
    run.clearQueries();
    const changed = await continueConversation(
      continuation(started.session_id, {
        action: "narrow_query",
        filters: {
          close_date_from: "2029-01-01",
        },
      }),
      run.dependencies,
    );
    assert.equal(changed.status, "awaiting_decision");
    assert.equal(changed.next_action, "approve_family_scope");
    assert.deepEqual(run.queries, []);
    assert.deepEqual(changed.account_ids, family.account_ids);

    const completed = await continueConversation(
      continuation(started.session_id, {
        action: "approve_family_scope",
      }),
      run.dependencies,
    );
    assertComplete(completed, run);
    assert.match(completed.message, /## Opportunity line items/u);
    assert.match(completed.message, /\bUSD\b/u);
    assert.match(completed.message, /\bEUR\b/u);
    assert.match(
      completed.message,
      /Currencies are never combined; no ARR or annualized value is calculated/u,
    );
    assert.match(
      completed.message,
      /Annualized revenue is not calculated because price basis, recurrence, and duration semantics are not certified/u,
    );
    assert.doesNotMatch(completed.message, /\bARR total\b/iu);
  } finally {
    await run.cleanup();
  }
});

test("forward journey: session resumes after conversational context loss", async () => {
  const run = await syntheticJourney();
  try {
    const started = await start(
      startRequest("UAT"),
      run.dependencies,
    );
    const freshContext = run.freshContext();
    const resumed = await status(
      statusRequest(started.session_id),
      freshContext,
    );
    assert.equal(resumed.status, "active");
    assert.equal(resumed.next_action, "confirm_org_and_plan");
    assert.equal(resumed.summary.preset, "pipeline");

    const completed = await continueConversation(
      continuation(started.session_id, {
        action: resumed.next_action,
      }),
      freshContext,
    );
    assertComplete(completed, run);
  } finally {
    await run.cleanup();
  }
});

test("forward journey: abort and exact TTL cleanup remove resumable control state", async () => {
  const run = await syntheticJourney();
  try {
    const abortedStart = await start(
      startRequest("UAT"),
      run.dependencies,
    );
    const stopped = await abort({
      schema_version: CONTRACTS.abortRequest,
      session_id: abortedStart.session_id,
    }, run.dependencies);
    assert.equal(stopped.status, "canceled");
    await assert.rejects(
      () => status(
        statusRequest(abortedStart.session_id),
        run.dependencies,
      ),
      { code: "SESSION_NOT_FOUND" },
    );

    const expiringStart = await start(
      startRequest("UAT"),
      run.dependencies,
    );
    run.advance(THIRTY_MINUTES - 1);
    assert.equal(
      (await status(
        statusRequest(expiringStart.session_id),
        run.dependencies,
      )).status,
      "active",
    );
    run.advance(1);
    const cleanup = await doctor({
      schema_version: CONTRACTS.doctorRequest,
    }, run.dependencies);
    assert.equal(cleanup.expired_sessions_deleted, 1);
    await assert.rejects(
      () => status(
        statusRequest(expiringStart.session_id),
        run.dependencies,
      ),
      { code: "SESSION_NOT_FOUND" },
    );
  } finally {
    await run.cleanup();
  }
});

test("forward journey: adversarial CRM text remains inert and token-bearing CLI fields never escape", async () => {
  const run = await syntheticJourney({
    alias: "synthetic-adversarial",
    friendlyLabel: "Adversarial UAT",
  });
  try {
    const started = await start(
      startRequest("Adversarial UAT", {
        preset: "snapshot",
        account_selector: {
          mode: "id",
          value: "001000000000001AAA",
        },
      }),
      run.dependencies,
    );
    const completed = await continueConversation(
      continuation(started.session_id, {
        action: "confirm_org_and_plan",
      }),
      run.dependencies,
    );
    assertComplete(completed, run);
    assertNoPrivateRuntimeOutput(
      run.diagnosis,
      started,
      completed,
    );
    assert.doesNotMatch(completed.message, /[\u001b\u202e]/u);
    assert.doesNotMatch(completed.message, /\$\(touch/u);
    assert.match(completed.message, /\\`\$\\\(touch/u);
    assert.match(completed.message, /O'Brien/u);
    assert.match(
      completed.message,
      /CODE\\_EXECUTION\\_SENTINEL/u,
    );
    assert.doesNotMatch(
      completed.message,
      /ANNUALIZATION_NOT_CERTIFIED|MULTICURRENCY_NO_AGGREGATION/u,
    );
  } finally {
    await run.cleanup();
  }
});

test("forward journey: missing custom fields become explicit warnings without invented values", async () => {
  const run = await syntheticJourney({
    alias: "synthetic-missing",
    friendlyLabel: "Schema Drift UAT",
  });
  try {
    assert.equal(run.diagnosis.metadata_compatibility.status, "compatible");
    assert.ok(
      run.diagnosis.metadata_compatibility.optional_warning_count > 0,
    );
    const started = await start(
      startRequest("Schema Drift UAT", {
        preset: "snapshot",
      }),
      run.dependencies,
    );
    const completed = await continueConversation(
      continuation(started.session_id, {
        action: "confirm_org_and_plan",
      }),
      run.dependencies,
    );
    assertComplete(completed, run);
    assert.match(completed.message, /Optional field unavailable/u);
    assert.match(
      completed.message,
      /Account\\\.Support\\_Status\\_\\_c/u,
    );
    assert.match(completed.message, /no value was inferred/u);
    assert.doesNotMatch(completed.message, /\| Support Status \|/u);
    assert.doesNotMatch(completed.message, /\| CSM ID \|/u);
    assert.doesNotMatch(completed.message, /\| PreSales ID \|/u);
  } finally {
    await run.cleanup();
  }
});

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
import { digest } from "../scripts/security.mjs";
import { SfClient } from "../scripts/sf-client.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const fakeSf = join(here, "fixtures", "fake-sf");
const fixedNow = new Date("2030-01-01T00:00:00.000Z");

async function harness({
  alias = "synthetic-complete",
  friendlyLabel = "UAT",
} = {}) {
  const stateRoot = await mkdtemp(join(tmpdir(), "sf-profile-v2-"));
  const internalErrors = [];
  const dependencies = {
    stateRoot,
    clientFactory: async (targetOrg) => new SfClient({
      commandSpec: {
        executable: fakeSf,
        fixedArgs: [],
        attestationDigest: digest({
          synthetic_test_runtime: fakeSf,
        }),
      },
      targetOrg,
    }),
    allowOfflineExecution: true,
    now: () => new Date(fixedNow),
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
    stateRoot,
    dependencies,
    diagnosis,
    internalErrors,
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

function decision(sessionId, body) {
  return {
    schema_version: CONTRACTS.continueRequest,
    session_id: sessionId,
    decision: body,
  };
}

function assertFriendlyTranscript(message) {
  for (const forbidden of [
    "schema_version",
    "read_plan",
    "digest",
    "chmod",
    ".json",
    "node ",
    "sf ",
    "ANNUALIZATION_NOT_CERTIFIED",
    "MULTICURRENCY_NO_AGGREGATION",
  ]) {
    assert.equal(message.includes(forbidden), false, forbidden);
  }
}

test("selected-account pipeline completes with one confirmation and deletes its session", async () => {
  const run = await harness();
  try {
    assert.equal(run.diagnosis.status, "ready");
    assert.equal(
      run.diagnosis.metadata_compatibility.status,
      "compatible",
    );
    assert.equal(
      run.diagnosis.enrolled_orgs[0].metadata_verified_at,
      fixedNow.toISOString(),
    );
    assert.equal(JSON.stringify(run.diagnosis).includes("SECRET_SHOULD_NOT_ESCAPE"), false);
    const started = await start(startRequest("UAT"), run.dependencies);
    assert.equal(started.next_action, "confirm_org_and_plan");
    assertFriendlyTranscript(started.message);

    const resumable = await status({
      schema_version: CONTRACTS.statusRequest,
      session_id: started.session_id,
    }, run.dependencies);
    assert.equal(resumable.summary.state, "org_confirmation");
    assert.equal(resumable.summary.preset, "pipeline");

    const completed = await continueConversation(decision(
      started.session_id,
      { action: "confirm_org_and_plan" },
    ), run.dependencies);
    assert.equal(
      completed.status,
      "complete",
      run.internalErrors.map((error) =>
        `${error.code}: ${error.message}`).join("\n"),
    );
    assert.equal(completed.next_action, null);
    assert.match(completed.message, /## Decision Summary/u);
    assert.match(completed.message, /Open opportunities/u);
    assert.match(completed.message, /Synthetic Owner/u);
    assertFriendlyTranscript(completed.message);
    await assert.rejects(
      () => status({
        schema_version: CONTRACTS.statusRequest,
        session_id: started.session_id,
      }, run.dependencies),
      { code: "SESSION_NOT_FOUND" },
    );
  } finally {
    await run.cleanup();
  }
});

test("ambiguous exact Account adds one chooser and revalidates the chosen ID", async () => {
  const run = await harness({
    alias: "synthetic-ambiguous",
    friendlyLabel: "Ambiguous UAT",
  });
  try {
    const started = await start(startRequest("Ambiguous UAT", {
      account_selector: {
        mode: "exact_name",
        value: "Repeated Name",
      },
    }), run.dependencies);
    const chooser = await continueConversation(decision(
      started.session_id,
      { action: "confirm_org_and_plan" },
    ), run.dependencies);
    assert.equal(chooser.next_action, "choose_account");
    assert.equal(chooser.choices.length, 2);
    assert.equal(chooser.choices[0].OwnerName, "Synthetic Owner");
    assertFriendlyTranscript(chooser.message);

    const completed = await continueConversation(decision(
      started.session_id,
      {
        action: "choose_account",
        account_id: chooser.choices[0].Id,
      },
    ), run.dependencies);
    assert.equal(
      completed.status,
      "complete",
      run.internalErrors.map((error) =>
        `${error.code}: ${error.message}`).join("\n"),
    );
    assert.match(completed.message, /Repeated Name/u);
  } finally {
    await run.cleanup();
  }
});

test("no exact match requires a literal-prefix decision and still never auto-selects", async () => {
  const run = await harness({
    alias: "synthetic-no-match",
    friendlyLabel: "No Match UAT",
  });
  try {
    const started = await start(startRequest("No Match UAT", {
      account_selector: {
        mode: "exact_name",
        value: "Example",
      },
    }), run.dependencies);
    const noMatch = await continueConversation(decision(
      started.session_id,
      { action: "confirm_org_and_plan" },
    ), run.dependencies);
    assert.equal(noMatch.next_action, "choose_account");
    assert.deepEqual(noMatch.choices, []);

    const prefixChooser = await continueConversation(decision(
      started.session_id,
      {
        action: "choose_account",
        literal_prefix: "Example",
      },
    ), run.dependencies);
    assert.equal(prefixChooser.next_action, "choose_account");
    assert.equal(prefixChooser.choices.length, 1);

    const completed = await continueConversation(decision(
      started.session_id,
      {
        action: "choose_account",
        account_id: prefixChooser.choices[0].Id,
      },
    ), run.dependencies);
    assert.equal(completed.status, "complete");
  } finally {
    await run.cleanup();
  }
});

test("corporate-family profile adds exact-set approval before transaction reads", async () => {
  const run = await harness();
  try {
    const started = await start(startRequest("UAT", {
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
    }), run.dependencies);
    const family = await continueConversation(decision(
      started.session_id,
      { action: "confirm_org_and_plan" },
    ), run.dependencies);
    assert.equal(family.next_action, "approve_family_scope");
    assert.deepEqual(family.account_ids, [
      "001000000000001AAA",
      "001000000000002AAA",
    ]);
    assert.equal(family.corporate_family_accounts.length, 2);
    assertFriendlyTranscript(family.message);

    const completed = await continueConversation(decision(
      started.session_id,
      { action: "approve_family_scope" },
    ), run.dependencies);
    assert.equal(
      completed.status,
      "complete",
      run.internalErrors.map((error) =>
        `${error.code}: ${error.message}`).join("\n"),
    );
    assert.match(completed.message, /Opportunity line items/u);
    assert.match(completed.message, /Synthetic Product A/u);
    assert.match(completed.message, /USD/u);
    assert.match(completed.message, /EUR/u);
    assertFriendlyTranscript(completed.message);
  } finally {
    await run.cleanup();
  }
});

test("abort deletes active session state immediately", async () => {
  const run = await harness();
  try {
    const started = await start(startRequest("UAT"), run.dependencies);
    const stopped = await abort({
      schema_version: CONTRACTS.abortRequest,
      session_id: started.session_id,
    }, run.dependencies);
    assert.equal(stopped.status, "canceled");
    await assert.rejects(
      () => status({
        schema_version: CONTRACTS.statusRequest,
        session_id: started.session_id,
      }, run.dependencies),
      { code: "SESSION_NOT_FOUND" },
    );
  } finally {
    await run.cleanup();
  }
});

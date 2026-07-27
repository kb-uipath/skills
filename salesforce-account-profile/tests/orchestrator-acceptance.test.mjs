import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  CONTRACTS,
  SESSION_TTL_MS,
} from "../scripts/constants.mjs";
import {
  continueConversation,
  doctor,
  orchestratorInternals,
  start,
  status,
} from "../scripts/orchestrator.mjs";
import {
  issueApprovalReceipt,
  validateApprovalReceipt,
} from "../scripts/read-plan.mjs";
import {
  digest,
  SafetyError,
} from "../scripts/security.mjs";
import { SfClient } from "../scripts/sf-client.mjs";
import { createStateStore } from "../scripts/state-store.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const fakeSf = join(here, "fixtures", "fake-sf");
const START = Date.parse("2030-01-01T00:00:00.000Z");

function sfClient(targetOrg) {
  return new SfClient({
    commandSpec: {
      executable: fakeSf,
      fixedArgs: [],
      attestationDigest: digest({ synthetic_test_runtime: fakeSf }),
    },
    targetOrg,
  });
}

async function harness({
  alias = "synthetic-complete",
  friendlyLabel = "UAT",
  decorateClient = (client) => client,
} = {}) {
  const stateRoot = await mkdtemp(join(tmpdir(), "sf-profile-v2-acceptance-"));
  let clock = START;
  const internalErrors = [];
  const dependencies = {
    stateRoot,
    allowOfflineExecution: true,
    now: () => new Date(clock),
    clientFactory: async (targetOrg) =>
      decorateClient(sfClient(targetOrg), targetOrg),
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
    advance(milliseconds) {
      clock += milliseconds;
    },
    freshDependencies() {
      return {
        ...dependencies,
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

function assertTransportFree(message) {
  assert.equal(typeof message, "string");
  const forbidden = [
    [/\bJSON\b/iu, "JSON transport"],
    [/\bschema(?:_version)?\b/iu, "schema metadata"],
    [/\bread_plan\b/iu, "read-plan transport"],
    [/\b(?:plan|receipt|runtime_attestation)_digest\b/iu, "digest metadata"],
    [/\b[a-f0-9]{64}\b/iu, "digest value"],
    [/\bchmod\b/iu, "permission command"],
    [/(?:^|\s)(?:\/Users\/|\/private\/|\/tmp\/|~\/|\.codex\/)/u, "local path"],
    [/(?:^|\s)--(?:target-org|json|file)\b/u, "CLI flag"],
    [/\bsf\s+(?:org|sobject|data)\b/iu, "Salesforce CLI command"],
    [/\bnode(?:\.exe)?\s/iu, "Node CLI command"],
    [/\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b/u, "raw warning code"],
    [/salesforce-account-profile-[a-z-]+\/v\d+/iu, "contract version"],
  ];
  for (const [pattern, label] of forbidden) {
    assert.doesNotMatch(message, pattern, label);
  }
}

test("status resumes an active session after conversational context is discarded", async () => {
  const run = await harness();
  try {
    const started = await start(startRequest("UAT"), run.dependencies);
    const freshDependencies = run.freshDependencies();
    const resumed = await status(
      statusRequest(started.session_id),
      freshDependencies,
    );

    assert.equal(resumed.status, "active");
    assert.equal(resumed.next_action, "confirm_org_and_plan");
    assert.equal(resumed.summary.state, "org_confirmation");
    assert.equal(resumed.summary.preset, "pipeline");
    assert.equal(resumed.summary.account.value, "Example Holdings");
    assertTransportFree(resumed.message);

    const completed = await continueConversation(
      continuation(started.session_id, {
        action: resumed.next_action,
      }),
      freshDependencies,
    );
    assert.equal(
      completed.status,
      "complete",
      run.internalErrors.map((error) =>
        `${error.code}: ${error.message}`).join("\n"),
    );
    assertTransportFree(completed.message);
  } finally {
    await run.cleanup();
  }
});

test("session lifetime is fixed at 30 minutes and expiry cleanup removes resumable state", async () => {
  const run = await harness();
  try {
    const started = await start(startRequest("UAT"), run.dependencies);
    run.advance(SESSION_TTL_MS - 1);
    assert.equal(
      (await status(statusRequest(started.session_id), run.dependencies)).status,
      "active",
    );

    run.advance(1);
    const cleanup = await doctor({
      schema_version: CONTRACTS.doctorRequest,
    }, run.dependencies);
    assert.equal(cleanup.expired_sessions_deleted, 1);
    const store = createStateStore({
      stateRoot: run.stateRoot,
      now: run.dependencies.now,
    });
    assert.deepEqual(await store.readSessionIndex(), []);
    await assert.rejects(
      () => status(statusRequest(started.session_id), run.dependencies),
      { code: "SESSION_NOT_FOUND" },
    );
  } finally {
    await run.cleanup();
  }
});

test("family_map requires exact-set approval and completes without transaction sections", async () => {
  const run = await harness();
  try {
    const started = await start(startRequest("UAT", {
      preset: "family_map",
    }), run.dependencies);
    assertTransportFree(started.message);

    const approval = await continueConversation(
      continuation(started.session_id, {
        action: "confirm_org_and_plan",
      }),
      run.dependencies,
    );
    assert.equal(approval.next_action, "approve_family_scope");
    assert.deepEqual(approval.account_ids, [
      "001000000000001AAA",
      "001000000000002AAA",
    ]);
    assertTransportFree(approval.message);

    const completed = await continueConversation(
      continuation(started.session_id, {
        action: "approve_family_scope",
      }),
      run.dependencies,
    );
    assert.equal(
      completed.status,
      "complete",
      run.internalErrors.map((error) =>
        `${error.code}: ${error.message}`).join("\n"),
    );
    assert.match(completed.message, /## Corporate-Family Accounts/u);
    assert.match(
      completed.message,
      /## Opportunities\s+Not requested\./u,
    );
    assert.match(
      completed.message,
      /## Opportunity line items\s+Not requested\./u,
    );
    assert.match(
      completed.message,
      /## Owner Hierarchy\s+Not requested\./u,
    );
    assert.equal("structured_artifact" in completed, false);
    assertTransportFree(completed.message);
  } finally {
    await run.cleanup();
  }
});

test("a family approval captured from persisted state is stale after any material plan change", async () => {
  const run = await harness();
  try {
    const started = await start(startRequest("UAT", {
      preset: "family_map",
    }), run.dependencies);
    await continueConversation(
      continuation(started.session_id, {
        action: "confirm_org_and_plan",
      }),
      run.dependencies,
    );
    const store = createStateStore({
      stateRoot: run.stateRoot,
      now: run.dependencies.now,
    });
    const session = await store.readSession(started.session_id);
    const receipt = issueApprovalReceipt(
      session.read_plan,
      "family_scope",
      new Date(START),
    );
    assert.equal(
      validateApprovalReceipt(
        receipt,
        session.read_plan,
        "family_scope",
        new Date(START),
      ),
      receipt,
    );

    const mutations = [
      orchestratorInternals.rebuildPlan(session.read_plan, {
        preset: "custom",
        sections: ["overview", "family"],
        scope: "corporate_family",
        opportunityScope: "open",
        familyAccountIds: ["001000000000001AAA"],
      }),
      orchestratorInternals.rebuildPlan(session.read_plan, {
        preset: "custom",
        sections: ["overview", "family", "opportunities"],
        scope: "corporate_family",
        opportunityScope: "open",
      }),
      orchestratorInternals.rebuildPlan(session.read_plan, {
        preset: "custom",
        sections: ["overview", "family"],
        scope: "corporate_family",
        opportunityScope: "all",
      }),
      orchestratorInternals.rebuildPlan(session.read_plan, {
        preset: "custom",
        sections: ["overview", "family"],
        scope: "corporate_family",
        opportunityScope: "open",
        filters: {
          close_date_from: "2029-01-01",
          close_date_to: null,
          stages: [],
        },
      }),
      orchestratorInternals.rebuildPlan(session.read_plan, {
        preset: "custom",
        sections: ["overview", "family"],
        scope: "selected_account",
        opportunityScope: "open",
        familyAccountIds: [],
      }),
    ];
    for (const changedPlan of mutations) {
      assert.throws(
        () => validateApprovalReceipt(
          receipt,
          changedPlan,
          "family_scope",
          new Date(START),
        ),
        { code: "APPROVAL_RECEIPT_MISMATCH" },
      );
    }
  } finally {
    await run.cleanup();
  }
});

test("user-visible transcripts retain business language and suppress transport/security artifacts", async () => {
  const run = await harness({
    alias: "synthetic-ambiguous",
    friendlyLabel: "Ambiguous UAT",
  });
  try {
    assertTransportFree(run.diagnosis.message);
    const started = await start(startRequest("Ambiguous UAT", {
      account_selector: {
        mode: "exact_name",
        value: "Repeated Name",
      },
    }), run.dependencies);
    assertTransportFree(started.message);
    const resumable = await status(
      statusRequest(started.session_id),
      run.dependencies,
    );
    assertTransportFree(resumable.message);
    const chooser = await continueConversation(
      continuation(started.session_id, {
        action: "confirm_org_and_plan",
      }),
      run.dependencies,
    );
    assertTransportFree(chooser.message);
    const completed = await continueConversation(
      continuation(started.session_id, {
        action: "choose_account",
        account_id: chooser.choices[0].Id,
      }),
      run.dependencies,
    );
    assert.equal(completed.status, "complete");
    assertTransportFree(completed.message);
  } finally {
    await run.cleanup();
  }
});

for (const scenario of [
  {
    name: "authentication failure offers reauthentication and resumes",
    code: "AUTHENTICATION_FAILURE",
    method: "orgDisplay",
    nextAction: "reauthenticate",
    decision: { action: "reauthenticate" },
  },
  {
    name: "permission failure offers a permission request and resumes",
    code: "PERMISSION_DENIED",
    method: "describe",
    nextAction: "request_permissions",
    decision: { action: "request_permissions" },
  },
  {
    name: "atomic cap failure offers guided narrowing and resumes",
    code: "OPPORTUNITY_CAP_EXCEEDED",
    method: "opportunityQuery",
    nextAction: "narrow_query",
    decision: {
      action: "narrow_query",
      filters: {
        close_date_from: "2029-01-01",
      },
    },
  },
]) {
  test(scenario.name, async () => {
    let fault = null;
    const run = await harness({
      decorateClient(client, targetOrg) {
        if (targetOrg === null) return client;
        if (scenario.method === "orgDisplay") {
          const original = client.orgDisplay.bind(client);
          client.orgDisplay = async () => {
            if (fault) throw new SafetyError(fault, "synthetic secret detail");
            return await original();
          };
        } else if (scenario.method === "describe") {
          const original = client.describe.bind(client);
          client.describe = async (objectName) => {
            if (fault) throw new SafetyError(fault, "synthetic secret detail");
            return await original(objectName);
          };
        } else {
          const original = client.query.bind(client);
          client.query = async (soql) => {
            if (fault && /\bFROM Opportunity\b/u.test(soql)) {
              throw new SafetyError(fault, "synthetic secret detail");
            }
            return await original(soql);
          };
        }
        return client;
      },
    });
    try {
      const started = await start(startRequest("UAT"), run.dependencies);
      fault = scenario.code;
      const recoverable = await continueConversation(
        continuation(started.session_id, {
          action: "confirm_org_and_plan",
        }),
        run.dependencies,
      );
      assert.equal(recoverable.status, "awaiting_decision");
      assert.equal(recoverable.next_action, scenario.nextAction);
      assertTransportFree(recoverable.message);
      assert.doesNotMatch(recoverable.message, /synthetic secret detail/u);
      assert.equal(
        run.internalErrors.at(-1)?.code,
        scenario.code,
      );
      if (scenario.nextAction === "narrow_query") {
        assert.ok(recoverable.narrowing_options.length > 0);
      }

      fault = null;
      const completed = await continueConversation(
        continuation(started.session_id, scenario.decision),
        run.freshDependencies(),
      );
      assert.equal(
        completed.status,
        "complete",
        run.internalErrors.map((error) =>
          `${error.code}: ${error.message}`).join("\n"),
      );
      assertTransportFree(completed.message);
    } finally {
      await run.cleanup();
    }
  });
}

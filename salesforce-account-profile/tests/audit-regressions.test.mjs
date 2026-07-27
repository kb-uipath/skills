import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { CONTRACTS } from "../scripts/constants.mjs";
import {
  validateContinueRequest,
} from "../scripts/conversational-contracts.mjs";
import {
  continueConversation,
  doctor,
  start,
  status,
} from "../scripts/orchestrator.mjs";
import {
  validateRegistryEntry,
} from "../scripts/org-registry.mjs";
import {
  issueApprovalReceipt,
} from "../scripts/read-plan.mjs";
import { recoveryForError } from "../scripts/recovery.mjs";
import {
  digest,
  SafetyError,
} from "../scripts/security.mjs";
import { SfClient } from "../scripts/sf-client.mjs";
import { createStateStore } from "../scripts/state-store.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const fakeSf = join(here, "fixtures", "fake-sf");
const START = Date.parse("2030-01-01T00:00:00.000Z");
const SESSION_ID = "0123456789abcdef0123456789abcdef";

function newSfClient(targetOrg) {
  return new SfClient({
    commandSpec: {
      executable: fakeSf,
      fixedArgs: [],
      attestationDigest: digest({
        synthetic_test_runtime: fakeSf,
      }),
    },
    targetOrg,
  });
}

async function harness({
  alias = "synthetic-complete",
  friendlyLabel = "UAT",
  environment = "sandbox",
  discoveryOrgType = null,
  enroll = true,
} = {}) {
  const stateRoot = await mkdtemp(join(tmpdir(), "sf-profile-audit-"));
  let clock = START;
  let fault = null;
  const queryAttempts = [];
  const dataReads = [];
  const internalErrors = [];
  const dependencies = {
    stateRoot,
    allowOfflineExecution: true,
    now: () => new Date(clock),
    onInternalError(error) {
      internalErrors.push(error);
    },
    clientFactory: async (targetOrg) => {
      const client = newSfClient(targetOrg);
      const originalOrgList = client.orgList.bind(client);
      client.orgList = async () => {
        const rows = await originalOrgList();
        return discoveryOrgType === null
          ? rows
          : rows.map((row) => row.alias === alias
            ? { ...row, org_type: discoveryOrgType }
            : row);
      };
      const originalQuery = client.query.bind(client);
      client.query = async (soql) => {
        queryAttempts.push(soql);
        if (fault
          && (!fault.predicate || fault.predicate.test(soql))) {
          throw new SafetyError(
            fault.code,
            "synthetic internal detail that must not escape",
          );
        }
        dataReads.push(soql);
        return await originalQuery(soql);
      };
      return client;
    },
  };
  let diagnosis = null;
  if (enroll) {
    diagnosis = await doctor({
      schema_version: CONTRACTS.doctorRequest,
      target_org: alias,
      friendly_label: friendlyLabel,
      environment,
    }, dependencies);
  }
  return {
    alias,
    friendlyLabel,
    environment,
    stateRoot,
    dependencies,
    diagnosis,
    queryAttempts,
    dataReads,
    internalErrors,
    advance(milliseconds) {
      clock += milliseconds;
    },
    setFault(code, predicate = null) {
      fault = {
        code,
        predicate,
      };
    },
    clearFault() {
      fault = null;
    },
    clearQueries() {
      queryAttempts.length = 0;
      dataReads.length = 0;
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

function fullFamilyRequest(targetOrg, overrides = {}) {
  return startRequest(targetOrg, {
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
    ...overrides,
  });
}

function isFamilyTransactionOrUserQuery(soql) {
  return /\bFROM (?:Opportunity|OpportunityLineItem|User)\b/u.test(soql);
}

async function primeNarrowingRecovery(run, request = startRequest("UAT")) {
  const started = await start(request, run.dependencies);
  run.setFault(
    "OPPORTUNITY_CAP_EXCEEDED",
    /\bFROM Opportunity\b/u,
  );
  const recovery = await continueConversation(
    continuation(started.session_id, {
      action: "confirm_org_and_plan",
    }),
    run.dependencies,
  );
  run.clearFault();
  run.clearQueries();
  assert.equal(recovery.status, "awaiting_decision");
  assert.equal(recovery.next_action, "narrow_query");
  return { started, recovery };
}

test("doctor rejects production and sandbox classification mislabeling", async (t) => {
  for (const scenario of [
    {
      name: "production-like discovery cannot be declared sandbox",
      discoveryOrgType: "production_or_developer",
      environment: "sandbox",
    },
    {
      name: "sandbox discovery cannot be declared production",
      discoveryOrgType: "sandbox",
      environment: "production",
    },
  ]) {
    await t.test(scenario.name, async () => {
      const run = await harness({
        discoveryOrgType: scenario.discoveryOrgType,
        environment: scenario.environment,
        enroll: false,
      });
      try {
        await assert.rejects(
          () => doctor({
            schema_version: CONTRACTS.doctorRequest,
            target_org: run.alias,
            friendly_label: run.friendlyLabel,
            environment: scenario.environment,
          }, run.dependencies),
          { code: "INVALID_ORG_REGISTRY" },
        );
        const store = createStateStore({
          stateRoot: run.stateRoot,
          now: run.dependencies.now,
        });
        assert.deepEqual((await store.readOrgRegistry()).entries, []);
      } finally {
        await run.cleanup();
      }
    });
  }
});

test("doctor refresh preserves an existing sandbox certification", async () => {
  const run = await harness();
  try {
    const store = createStateStore({
      stateRoot: run.stateRoot,
      now: run.dependencies.now,
    });
    const registry = await store.readOrgRegistry();
    const certified = validateRegistryEntry({
      ...registry.entries[0],
      certification_state: "sandbox_read_certified",
      certification_verified_at: new Date(START).toISOString(),
    });
    await store.writeOrgRegistry({
      ...registry,
      entries: [certified],
    });

    run.advance(60_000);
    const refreshed = await doctor({
      schema_version: CONTRACTS.doctorRequest,
      target_org: run.alias,
      friendly_label: run.friendlyLabel,
      environment: run.environment,
    }, run.dependencies);
    const saved = (await store.readOrgRegistry()).entries[0];

    assert.equal(
      refreshed.enrolled_orgs[0].certification_state,
      "sandbox_read_certified",
    );
    assert.equal(saved.certification_state, "sandbox_read_certified");
    assert.equal(
      saved.certification_verified_at,
      certified.certification_verified_at,
    );
    assert.deepEqual(saved.approvals, certified.approvals);
    assert.equal(
      saved.identity_verified_at,
      new Date(START + 60_000).toISOString(),
    );
    assert.equal(
      saved.metadata_verified_at,
      new Date(START + 60_000).toISOString(),
    );
    assert.match(
      refreshed.message,
      /sandbox read certification remains in force/u,
    );
  } finally {
    await run.cleanup();
  }
});

test("missing or mutated org-plan approval blocks all Salesforce data queries", async (t) => {
  for (const scenario of [
    { name: "missing receipt", mutate: () => null },
    {
      name: "mutated receipt",
      mutate(plan) {
        return {
          ...issueApprovalReceipt(plan, "org_and_plan", new Date(START)),
          plan_digest: "f".repeat(64),
        };
      },
    },
  ]) {
    await t.test(scenario.name, async () => {
      const run = await harness();
      try {
        const started = await start(
          startRequest("UAT"),
          run.dependencies,
        );
        const store = createStateStore({
          stateRoot: run.stateRoot,
          now: run.dependencies.now,
        });
        const session = await store.readSession(started.session_id);
        await store.updateSession(started.session_id, {
          state: "account_resolution",
          org_approval_receipt: scenario.mutate(session.read_plan),
          pending_action: "request_permissions",
          recovery: {
            resume_state: "account_resolution",
            narrowing_options: [],
          },
        });
        run.clearQueries();

        const stopped = await continueConversation(
          continuation(started.session_id, {
            action: "request_permissions",
          }),
          run.dependencies,
        );
        assert.equal(stopped.status, "canceled");
        assert.equal(stopped.next_action, "cancel");
        assert.deepEqual(run.queryAttempts, []);
        assert.deepEqual(run.dataReads, []);
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
  }
});

test("family-plan narrowing re-requests exact-set approval before any family transaction read", async () => {
  const run = await harness();
  try {
    const started = await start(
      fullFamilyRequest("UAT"),
      run.dependencies,
    );
    const family = await continueConversation(
      continuation(started.session_id, {
        action: "confirm_org_and_plan",
      }),
      run.dependencies,
    );
    assert.equal(family.next_action, "approve_family_scope");
    assert.equal(
      run.dataReads.some(isFamilyTransactionOrUserQuery),
      false,
    );
    assert.equal(
      family.corporate_family_accounts.every((account) =>
        typeof account.Name === "string" && account.Name.length > 0),
      true,
    );
    assert.deepEqual(
      family.corporate_family_accounts.map((account) => account.Id).sort(),
      [...family.account_ids].sort(),
    );

    run.setFault(
      "OPPORTUNITY_CAP_EXCEEDED",
      /\bFROM Opportunity\b/u,
    );
    const recovery = await continueConversation(
      continuation(started.session_id, {
        action: "approve_family_scope",
      }),
      run.dependencies,
    );
    assert.equal(recovery.next_action, "narrow_query");
    run.clearFault();
    run.clearQueries();

    const narrowed = await continueConversation(
      continuation(started.session_id, {
        action: "narrow_query",
        filters: {
          close_date_from: "2029-06-01",
        },
      }),
      run.dependencies,
    );
    assert.equal(narrowed.status, "awaiting_decision");
    assert.equal(narrowed.next_action, "approve_family_scope");
    assert.deepEqual(run.queryAttempts, []);
    assert.deepEqual(run.dataReads, []);
    assert.equal(
      narrowed.corporate_family_accounts.every((account) =>
        typeof account.Name === "string" && account.Name.length > 0),
      true,
    );
  } finally {
    await run.cleanup();
  }
});

test("open-to-all and filter relaxation remain resumable narrowing decisions", async (t) => {
  await t.test("open cannot widen to all", async () => {
    const run = await harness();
    try {
      const { started } = await primeNarrowingRecovery(run);
      const rejected = await continueConversation(
        continuation(started.session_id, {
          action: "narrow_query",
          opportunity_scope: "all",
        }),
        run.dependencies,
      );
      assert.equal(rejected.status, "awaiting_decision");
      assert.equal(rejected.next_action, "narrow_query");
      assert.equal(rejected.session_id, started.session_id);
      assert.deepEqual(run.queryAttempts, []);
      assert.equal(
        (await status(
          statusRequest(started.session_id),
          run.dependencies,
        )).next_action,
        "narrow_query",
      );
    } finally {
      await run.cleanup();
    }
  });

  await t.test("existing date filter cannot be relaxed", async () => {
    const run = await harness();
    try {
      const { started } = await primeNarrowingRecovery(
        run,
        startRequest("UAT", {
          preset: "custom",
          sections: ["overview", "opportunities"],
          scope: "selected_account",
          opportunity_scope: "open",
          filters: {
            close_date_from: "2030-01-01",
          },
        }),
      );
      const rejected = await continueConversation(
        continuation(started.session_id, {
          action: "narrow_query",
          filters: {
            close_date_from: "2029-01-01",
          },
        }),
        run.dependencies,
      );
      assert.equal(rejected.status, "awaiting_decision");
      assert.equal(rejected.next_action, "narrow_query");
      assert.equal(rejected.session_id, started.session_id);
      assert.deepEqual(run.queryAttempts, []);
      assert.equal(
        (await status(
          statusRequest(started.session_id),
          run.dependencies,
        )).next_action,
        "narrow_query",
      );
    } finally {
      await run.cleanup();
    }
  });
});

test("every advertised recovery narrowing option has a valid continuation shape", () => {
  const capCodes = [
    "CANDIDATE_CAP_EXCEEDED",
    "FAMILY_ACCOUNT_CAP_EXCEEDED",
    "OPPORTUNITY_CAP_EXCEEDED",
    "LINE_ITEM_CAP_EXCEEDED",
    "USER_CAP_EXCEEDED",
    "QUERY_CAP_EXCEEDED",
    "FAMILY_DISCOVERY_INCOMPLETE",
    "FAMILY_CYCLE_DETECTED",
    "FAMILY_DEPTH_LIMIT_REACHED",
    "INVALID_NARROWING",
  ];
  const decisions = {
    account_selector: {
      action: "narrow_query",
      account_selector: {
        mode: "exact_name",
        value: "Narrowed Account",
      },
    },
    selected_account: {
      action: "narrow_query",
      scope: "selected_account",
    },
    open_only: {
      action: "narrow_query",
      opportunity_scope: "open",
    },
    close_date_window: {
      action: "narrow_query",
      filters: {
        close_date_from: "2030-01-01",
        close_date_to: "2030-12-31",
      },
    },
    stage: {
      action: "narrow_query",
      filters: {
        stages: ["Discovery"],
      },
    },
    remove_line_items: {
      action: "narrow_query",
      remove_sections: ["products"],
    },
    remove_team: {
      action: "narrow_query",
      remove_sections: ["team"],
    },
    reduce_sections: {
      action: "narrow_query",
      remove_sections: ["opportunities"],
    },
  };
  const advertised = new Set(capCodes.flatMap((code) =>
    recoveryForError(code).narrowing_options));
  assert.deepEqual(
    [...advertised].sort(),
    Object.keys(decisions).sort(),
  );
  for (const option of advertised) {
    const validated = validateContinueRequest({
      schema_version: CONTRACTS.continueRequest,
      session_id: SESSION_ID,
      decision: decisions[option],
    });
    assert.equal(validated.decision.action, "narrow_query");
  }
});

test("doctor reports resumable sessions without putting a session ID in its message", async () => {
  const run = await harness();
  try {
    const started = await start(
      startRequest("UAT"),
      run.dependencies,
    );
    const diagnosis = await doctor({
      schema_version: CONTRACTS.doctorRequest,
    }, run.dependencies);

    assert.equal(diagnosis.active_sessions.length, 1);
    assert.equal(
      diagnosis.active_sessions[0].session_id,
      started.session_id,
    );
    assert.match(diagnosis.message, /1 private profile session is available/u);
    assert.equal(diagnosis.message.includes(started.session_id), false);
    assert.doesNotMatch(diagnosis.message, /\b[a-f0-9]{32}\b/u);
  } finally {
    await run.cleanup();
  }
});

test("replayed stale decisions preserve the current chooser or family approval", async (t) => {
  await t.test("Account chooser", async () => {
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
      const chooser = await continueConversation(
        continuation(started.session_id, {
          action: "confirm_org_and_plan",
        }),
        run.dependencies,
      );
      run.clearQueries();
      const replay = await continueConversation(
        continuation(started.session_id, {
          action: "confirm_org_and_plan",
        }),
        run.dependencies,
      );

      assert.equal(replay.status, "awaiting_decision");
      assert.equal(replay.next_action, "choose_account");
      assert.equal(replay.session_id, started.session_id);
      assert.deepEqual(replay.choices, chooser.choices);
      assert.deepEqual(run.queryAttempts, []);
      assert.equal(
        (await status(
          statusRequest(started.session_id),
          run.dependencies,
        )).next_action,
        "choose_account",
      );
    } finally {
      await run.cleanup();
    }
  });

  await t.test("family approval", async () => {
    const run = await harness();
    try {
      const started = await start(
        fullFamilyRequest("UAT"),
        run.dependencies,
      );
      const family = await continueConversation(
        continuation(started.session_id, {
          action: "confirm_org_and_plan",
        }),
        run.dependencies,
      );
      run.clearQueries();
      const replay = await continueConversation(
        continuation(started.session_id, {
          action: "confirm_org_and_plan",
        }),
        run.dependencies,
      );

      assert.equal(replay.status, "awaiting_decision");
      assert.equal(replay.next_action, "approve_family_scope");
      assert.equal(replay.session_id, started.session_id);
      assert.deepEqual(replay.account_ids, family.account_ids);
      assert.deepEqual(
        replay.corporate_family_accounts,
        family.corporate_family_accounts,
      );
      assert.deepEqual(run.queryAttempts, []);
      assert.equal(
        (await status(
          statusRequest(started.session_id),
          run.dependencies,
        )).next_action,
        "approve_family_scope",
      );
    } finally {
      await run.cleanup();
    }
  });
});

test("friendly labels and Account selectors are Markdown and HTML inert in messages", async () => {
  const friendlyLabel = "<b>UAT</b> **bold** [click](https://evil.invalid)";
  const selector = "<script>alert(1)</script> **Account** [click](javascript:x)";
  const run = await harness({ friendlyLabel });
  try {
    assert.doesNotMatch(run.diagnosis.message, /<b>/u);
    assert.doesNotMatch(run.diagnosis.message, /\*\*bold\*\*/u);
    assert.doesNotMatch(run.diagnosis.message, /\[click\]\(/u);
    assert.match(run.diagnosis.message, /\\<b\\>/u);
    assert.match(run.diagnosis.message, /\\\*\\\*bold\\\*\\\*/u);

    const started = await start(
      startRequest(run.alias, {
        account_selector: {
          mode: "exact_name",
          value: selector,
        },
      }),
      run.dependencies,
    );
    assert.doesNotMatch(started.message, /<script>/u);
    assert.doesNotMatch(started.message, /\*\*Account\*\*/u);
    assert.doesNotMatch(started.message, /\[click\]\(/u);
    assert.match(started.message, /\\<script\\>/u);
    assert.match(started.message, /\\\*\\\*Account\\\*\\\*/u);
  } finally {
    await run.cleanup();
  }
});

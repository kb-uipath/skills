import assert from "node:assert/strict";
import { Readable, Writable } from "node:stream";
import test from "node:test";

import { main } from "../scripts/account-profile.mjs";
import {
  buildProductionApprovalEvidence,
  buildSandboxCertificationEvidence,
} from "../scripts/certification-evidence.mjs";
import { CLASSIFICATION, CONTRACTS } from "../scripts/constants.mjs";
import { orgDigest } from "../scripts/contracts.mjs";
import {
  buildOfflineRegistryEntry,
  downgradeRegistryEntry,
  emptyOrgRegistry,
  markMetadataVerified,
  markProductionReadApproved,
  markSandboxReadCertified,
} from "../scripts/org-registry.mjs";
import {
  inspectMetadataCompatibility,
} from "../scripts/metadata-compatibility.mjs";
import { attestCertificationPackage } from "../scripts/package-attestation.mjs";
import { digest, SafetyError } from "../scripts/security.mjs";
import {
  DESCRIBE,
  IDS,
  MockClient,
  receiptFor,
} from "./helpers.mjs";

const ALIAS = "synthetic";
const NOW = new Date("2030-01-01T00:00:00.000Z");
const RUNTIME_DIGEST = digest({ synthetic_advanced_runtime: "v1" });
const IDENTITY = Object.freeze({
  org_id: "00D000000000001AAA",
  username: "synthetic@example.invalid",
  instance_url: "https://synthetic.example.invalid",
  connected_status: "Connected",
});
const PRODUCTION_IDENTITY = Object.freeze({
  org_id: "00D000000000002AAA",
  username: "production@example.invalid",
  instance_url: "https://production.example.invalid",
  connected_status: "Connected",
});
const ACCOUNT = Object.freeze({
  Id: IDS.account1,
  Name: "Example",
  ParentId: null,
  OwnerId: IDS.user1,
  Ultimate_Parent_name__c: null,
});
const OPPORTUNITY = Object.freeze({
  Id: IDS.opportunity1,
  Name: "Open Synthetic Deal",
  AccountId: IDS.account1,
  OwnerId: IDS.user1,
  StageName: "Discovery",
  Amount: 100,
  CloseDate: "2030-02-01",
  IsClosed: false,
  IsWon: false,
  CurrencyIsoCode: "USD",
  HasOpportunityLineItem: false,
});
const USERS = Object.freeze({
  [IDS.user1]: {
    Id: IDS.user1,
    Name: "Synthetic Owner",
    Title: "Account Executive",
    ManagerId: IDS.user2,
  },
  [IDS.user2]: {
    Id: IDS.user2,
    Name: "Synthetic Manager",
    Title: "Manager",
    ManagerId: null,
  },
});

class Capture extends Writable {
  constructor() {
    super();
    this.chunks = [];
  }

  _write(chunk, encoding, callback) {
    this.chunks.push(Buffer.from(chunk));
    callback();
  }

  text() {
    return Buffer.concat(this.chunks).toString("utf8");
  }
}

async function invoke(command, input, dependencies) {
  const stdout = new Capture();
  const stderr = new Capture();
  const code = await main({
    argv: [command],
    stdin: Readable.from([Buffer.from(JSON.stringify(input), "utf8")]),
    stdout,
    stderr,
    dependencies,
  });
  return {
    code,
    stdout: stdout.text(),
    stderr: stderr.text(),
  };
}

function resolveRequest() {
  return {
    schema_version: CONTRACTS.resolveRequest,
    target_org: ALIAS,
    confirmed_org_digest: orgDigest(
      ALIAS,
      IDENTITY,
      RUNTIME_DIGEST,
    ),
    selector: {
      mode: "exact_name",
      value: ACCOUNT.Name,
    },
  };
}

function profileRequest() {
  const receiptClient = new MockClient({ identity: IDENTITY });
  receiptClient.attestationDigest = RUNTIME_DIGEST;
  return {
    schema_version: CONTRACTS.profileRequest,
    target_org: ALIAS,
    confirmed_org_digest: orgDigest(
      ALIAS,
      IDENTITY,
      RUNTIME_DIGEST,
    ),
    account_receipt: receiptFor(receiptClient, {
      Id: ACCOUNT.Id,
      Name: ACCOUNT.Name,
    }, ALIAS),
    sections: ["overview", "opportunities", "team"],
    scope: "selected_account",
    opportunity_scope: "open",
  };
}

function offlineEntry() {
  return markMetadataVerified(buildOfflineRegistryEntry({
    alias: ALIAS,
    friendlyLabel: "Synthetic",
    identity: IDENTITY,
    orgType: "sandbox",
    environment: "sandbox",
    now: NOW,
  }), NOW);
}

async function certifiedEntry({
  packageDigest,
  metadataCompatibilityDigest,
} = {}) {
  const entry = offlineEntry();
  const packageAttestation = await attestCertificationPackage();
  const metadataClient = new MockClient({
    identity: IDENTITY,
    describes: DESCRIBE,
  });
  const currentMetadataDigest = digest(
    await inspectMetadataCompatibility(metadataClient),
  );
  const evidence = buildSandboxCertificationEvidence({
    orgFingerprint: entry.org_fingerprint,
    runtimeAttestationDigest: RUNTIME_DIGEST,
    packageDigest: packageDigest ?? packageAttestation.package_digest,
    metadataCompatibilityDigest:
      metadataCompatibilityDigest ?? currentMetadataDigest,
    fixtureManifestDigest: "b".repeat(64),
    authorizationScopeDigest: "c".repeat(64),
    authorizationAssertionDigest: "d".repeat(64),
    queryCount: 1,
    startedAt: NOW,
    completedAt: NOW,
  });
  return markSandboxReadCertified(entry, {
    evidence,
    now: NOW,
  });
}

function dependentProductionEntry(sandboxEntry) {
  const entry = markMetadataVerified(buildOfflineRegistryEntry({
    alias: "synthetic-production",
    friendlyLabel: "Synthetic Production",
    identity: PRODUCTION_IDENTITY,
    orgType: "production_or_developer",
    environment: "production",
    now: NOW,
  }), NOW);
  const evidence = buildProductionApprovalEvidence({
    productionOrgFingerprint: entry.org_fingerprint,
    sandboxEvidenceDigest:
      sandboxEntry.certification_evidence.receipt_digest,
    runtimeAttestationDigest: RUNTIME_DIGEST,
    packageDigest: sandboxEntry.certification_evidence.package_digest,
    metadataCompatibilityDigest:
      sandboxEntry.certification_evidence.metadata_compatibility_digest,
    approvalScopeDigest: "e".repeat(64),
    administratorApproval: {
      reference: "ADMIN-RUNTIME-DRIFT",
      subject_digest: "1".repeat(64),
      issued_at: NOW.toISOString(),
      scope_digest: "e".repeat(64),
      assertion_digest: "2".repeat(64),
    },
    riskOwnerApproval: {
      reference: "RISK-RUNTIME-DRIFT",
      subject_digest: "3".repeat(64),
      issued_at: NOW.toISOString(),
      scope_digest: "e".repeat(64),
      assertion_digest: "4".repeat(64),
    },
    completedAt: NOW,
  });
  return markProductionReadApproved(entry, {
    evidence,
    now: NOW,
  });
}

function registry(entries) {
  return {
    schema_version: CONTRACTS.orgRegistry,
    classification: CLASSIFICATION,
    entries,
  };
}

function storeHarness(document) {
  let current = structuredClone(document);
  const stats = {
    guarded: 0,
    issued: 0,
    inLease: 0,
    registryUpdates: 0,
  };
  return {
    stats,
    store: {
      async initialize() {},
      async readOrgRegistry() {
        return structuredClone(current);
      },
      async updateOrgRegistry(update) {
        current = structuredClone(
          await update(structuredClone(current)),
        );
        stats.registryUpdates += 1;
        return structuredClone(current);
      },
      async withOrgRegistryReadiness(operation) {
        stats.guarded += 1;
        return await operation(structuredClone(current), {
          async issueQuery(issue) {
            stats.issued += 1;
            stats.inLease += 1;
            try {
              return await issue();
            } finally {
              stats.inLease -= 1;
            }
          },
          async updateRegistry(update) {
            current = structuredClone(
              await update(structuredClone(current)),
            );
            stats.registryUpdates += 1;
            return structuredClone(current);
          },
        });
      },
    },
    replace(next) {
      current = structuredClone(next);
    },
    snapshot() {
      return structuredClone(current);
    },
  };
}

function clientFactory(stats) {
  return async () => {
    const client = new MockClient({
      identity: IDENTITY,
      describes: DESCRIBE,
      query(soql) {
        assert.equal(
          stats.inLease,
          1,
          "underlying data query escaped the readiness issuance lease",
        );
        if (/\bFROM Account\b/u.test(soql)) return [ACCOUNT];
        if (/\bFROM Opportunity\b/u.test(soql)) return [OPPORTUNITY];
        if (/\bFROM User\b/u.test(soql)) {
          return Object.values(USERS).filter((user) =>
            soql.includes(user.Id));
        }
        return [];
      },
    });
    client.attestationDigest = RUNTIME_DIGEST;
    return client;
  };
}

test("public resolve and profile issue zero queries without current readiness", async (t) => {
  const revoked = downgradeRegistryEntry(await certifiedEntry());
  for (const scenario of [
    {
      name: "missing registry",
      document: emptyOrgRegistry(),
      code: "ORG_NOT_ENROLLED",
    },
    {
      name: "offline-only registry",
      document: registry([offlineEntry()]),
      code: "SANDBOX_NOT_CERTIFIED",
    },
    {
      name: "revoked registry",
      document: registry([revoked]),
      code: "SANDBOX_NOT_CERTIFIED",
    },
  ]) {
    await t.test(scenario.name, async (t2) => {
      for (const [command, input] of [
        ["resolve", resolveRequest()],
        ["profile", profileRequest()],
      ]) {
        await t2.test(command, async () => {
          const state = storeHarness(scenario.document);
          let clients = 0;
          const execution = await invoke(command, input, {
            stateStore: state.store,
            clientFactory: async () => {
              clients += 1;
              return await clientFactory(state.stats)();
            },
          });
          assert.equal(execution.code, 2);
          assert.equal(execution.stdout, "");
          assert.equal(JSON.parse(execution.stderr).error.code, scenario.code);
          assert.equal(clients, 0);
          assert.equal(state.stats.guarded, 0);
          assert.equal(state.stats.issued, 0);
        });
      }
    });
  }
});

test("public advanced execution rejects package drift before a data query", async () => {
  const entry = await certifiedEntry({
    packageDigest: "f".repeat(64),
  });
  const state = storeHarness(registry([entry]));
  let clients = 0;
  const execution = await invoke("resolve", resolveRequest(), {
    stateStore: state.store,
    clientFactory: async () => {
      clients += 1;
      return await clientFactory(state.stats)();
    },
  });
  assert.equal(execution.code, 2);
  assert.equal(JSON.parse(execution.stderr).error.code, "CERTIFICATION_DRIFT");
  assert.equal(clients, 1);
  assert.equal(state.stats.guarded, 0);
  assert.equal(state.stats.issued, 0);
  assert.equal(state.stats.registryUpdates, 1);
  assert.equal(
    state.snapshot().entries[0].certification_state,
    "offline_validated",
  );
});

test("public advanced execution atomically revokes runtime drift during a leased query", async () => {
  const state = storeHarness(registry([
    await certifiedEntry(),
  ]));
  const execution = await invoke("resolve", resolveRequest(), {
    stateStore: state.store,
    clientFactory: async () => {
      const client = new MockClient({
        identity: IDENTITY,
        describes: DESCRIBE,
        query() {
          throw new SafetyError(
            "SF_EXECUTABLE_REATTESTATION_REQUIRED",
            "Synthetic runtime changed before query issuance",
          );
        },
      });
      client.attestationDigest = RUNTIME_DIGEST;
      return client;
    },
  });

  assert.equal(execution.code, 2);
  assert.equal(
    JSON.parse(execution.stderr).error.code,
    "SF_EXECUTABLE_REATTESTATION_REQUIRED",
  );
  assert.equal(state.stats.issued, 1);
  assert.equal(state.stats.registryUpdates, 1);
  assert.equal(
    state.snapshot().entries[0].certification_state,
    "offline_validated",
  );
});

test("public advanced execution revokes pre-query runtime drift and dependent production approval", async (t) => {
  const scenarios = [
    {
      name: "initial org identity read",
      prepare(client) {
        client.orgDisplay = async () => {
          throw new SafetyError(
            "SF_EXECUTABLE_REATTESTATION_REQUIRED",
            "Synthetic runtime changed before initial identity verification",
          );
        };
      },
    },
    {
      name: "workflow org identity read",
      prepare(client) {
        const orgDisplay = client.orgDisplay.bind(client);
        let calls = 0;
        client.orgDisplay = async () => {
          calls += 1;
          if (calls > 1) {
            throw new SafetyError(
              "SF_EXECUTABLE_REATTESTATION_REQUIRED",
              "Synthetic runtime changed before workflow identity verification",
            );
          }
          return await orgDisplay();
        };
      },
    },
    {
      name: "workflow describe",
      prepare(client) {
        const describe = client.describe.bind(client);
        let accountDescribes = 0;
        client.describe = async (objectName) => {
          if (objectName === "Account") {
            accountDescribes += 1;
            if (accountDescribes > 1) {
              throw new SafetyError(
                "SF_EXECUTABLE_REATTESTATION_REQUIRED",
                "Synthetic runtime changed before workflow metadata verification",
              );
            }
          }
          return await describe(objectName);
        };
      },
    },
  ];

  for (const scenario of scenarios) {
    await t.test(scenario.name, async () => {
      const sandbox = await certifiedEntry();
      const production = dependentProductionEntry(sandbox);
      const state = storeHarness(registry([sandbox, production]));
      let createdClient;
      const execution = await invoke("resolve", resolveRequest(), {
        stateStore: state.store,
        clientFactory: async () => {
          createdClient = new MockClient({
            identity: IDENTITY,
            describes: DESCRIBE,
            query() {
              assert.fail(
                "pre-query runtime drift must block every data query",
              );
            },
          });
          createdClient.attestationDigest = RUNTIME_DIGEST;
          scenario.prepare(createdClient);
          return createdClient;
        },
      });

      assert.equal(execution.code, 2);
      assert.equal(
        JSON.parse(execution.stderr).error.code,
        "SF_EXECUTABLE_REATTESTATION_REQUIRED",
      );
      assert.equal(createdClient.queryCount, 0);
      assert.equal(state.stats.issued, 0);
      assert.deepEqual(
        state.snapshot().entries.map((entry) => [
          entry.alias,
          entry.certification_state,
        ]),
        [
          ["synthetic", "offline_validated"],
          ["synthetic-production", "offline_validated"],
        ],
      );
    });
  }
});

test("public advanced execution persists observed identity and metadata drift", async (t) => {
  for (const scenario of [
    {
      name: "org identity changed",
      expectedCode: "ORG_IDENTITY_MISMATCH",
      buildClient(stats) {
        const factory = clientFactory(stats);
        return async () => {
          const client = await factory();
          let displays = 0;
          client.orgDisplay = async () => {
            displays += 1;
            return displays === 1
              ? IDENTITY
              : {
                ...IDENTITY,
                username: "changed@example.invalid",
              };
          };
          return client;
        };
      },
    },
    {
      name: "required Account metadata changed",
      expectedCode: "CERTIFICATION_DRIFT",
      buildClient(stats) {
        return async () => {
          const client = new MockClient({
            identity: IDENTITY,
            describes: {
              ...DESCRIBE,
              Account: ["Id", "Name", "ParentId"],
            },
            query() {
              assert.fail(
                "metadata drift must block before a data query",
              );
            },
          });
          client.attestationDigest = RUNTIME_DIGEST;
          return client;
        };
      },
    },
  ]) {
    await t.test(scenario.name, async () => {
      const state = storeHarness(registry([
        await certifiedEntry(),
      ]));
      const execution = await invoke("resolve", resolveRequest(), {
        stateStore: state.store,
        clientFactory: scenario.buildClient(state.stats),
      });
      assert.equal(execution.code, 2);
      assert.equal(
        JSON.parse(execution.stderr).error.code,
        scenario.expectedCode,
      );
      assert.equal(state.stats.issued, 0);
      assert.equal(state.stats.registryUpdates, 1);
      assert.equal(
        state.snapshot().entries[0].certification_state,
        "offline_validated",
      );
    });
  }
});

test("public advanced execution rejects compatible optional metadata drift before a data query", async () => {
  const state = storeHarness(registry([
    await certifiedEntry(),
  ]));
  const execution = await invoke("resolve", resolveRequest(), {
    stateStore: state.store,
    clientFactory: async () => {
      const client = new MockClient({
        identity: IDENTITY,
        describes: {
          ...DESCRIBE,
          Account: [...DESCRIBE.Account, "Support_Status__c"],
        },
        query() {
          assert.fail(
            "compatible optional metadata drift must block before a data query",
          );
        },
      });
      client.attestationDigest = RUNTIME_DIGEST;
      return client;
    },
  });

  assert.equal(execution.code, 2);
  assert.equal(
    JSON.parse(execution.stderr).error.code,
    "CERTIFICATION_DRIFT",
  );
  assert.equal(state.stats.issued, 0);
  assert.equal(state.stats.registryUpdates, 1);
  assert.equal(
    state.snapshot().entries[0].certification_state,
    "offline_validated",
  );
});

test("public advanced data execution leases every underlying query", async () => {
  const entry = await certifiedEntry();
  const state = storeHarness(registry([entry]));
  const dependencies = {
    stateStore: state.store,
    clientFactory: clientFactory(state.stats),
  };

  const resolution = await invoke(
    "resolve",
    resolveRequest(),
    dependencies,
  );
  assert.equal(resolution.code, 0, resolution.stderr);
  assert.equal(JSON.parse(resolution.stdout).status, "selected");

  const profiled = await invoke(
    "profile",
    profileRequest(),
    dependencies,
  );
  assert.equal(profiled.code, 0, profiled.stderr);
  assert.equal(JSON.parse(profiled.stdout).status, "complete");
  assert(state.stats.issued > 2);
  assert.equal(state.stats.guarded, state.stats.issued);
  assert.equal(state.stats.inLease, 0);
});

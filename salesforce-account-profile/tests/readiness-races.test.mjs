import assert from "node:assert/strict";
import {
  generateKeyPairSync,
  sign as signBytes,
} from "node:crypto";
import {
  lstat,
  mkdtemp,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  buildSandboxCertificationEvidence,
} from "../scripts/certification-evidence.mjs";
import { createCertificationEngine } from "../scripts/certification.mjs";
import {
  CERTIFICATION_APPROVAL_AUDIENCE,
  CERTIFICATION_APPROVAL_ROLES,
  CLASSIFICATION,
  CONTRACTS,
  FIELD_MAP_VERSION,
  SANDBOX_SUITE_VERSION,
} from "../scripts/constants.mjs";
import {
  continueConversation,
  doctor,
  start,
} from "../scripts/orchestrator.mjs";
import {
  downgradeRegistryEntry,
  markSandboxReadCertified,
  refreshRegistryVerification,
  resolveRegistryEntry,
  upsertRegistryEntry,
  validateOrgRegistry,
} from "../scripts/org-registry.mjs";
import {
  attestCertificationPackage,
} from "../scripts/package-attestation.mjs";
import {
  canonicalJson,
  digest,
  SafetyError,
} from "../scripts/security.mjs";
import { SfClient } from "../scripts/sf-client.mjs";
import { createStateStore } from "../scripts/state-store.mjs";
import { FIELD_POLICY } from "../scripts/workflow.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const fakeSf = join(here, "fixtures", "fake-sf");
const START = Date.parse("2030-01-01T00:00:00.000Z");
const RUNTIME_DIGEST = digest({ synthetic_test_runtime: fakeSf });
const IDS = Object.freeze({
  account1: "001000000000001AAA",
  account2: "001000000000002AAA",
  account3: "001000000000003AAA",
  account4: "001000000000004AAA",
  account5: "001000000000005AAA",
});

function client(targetOrg) {
  return new SfClient({
    commandSpec: {
      executable: fakeSf,
      fixedArgs: [],
      attestationDigest: RUNTIME_DIGEST,
    },
    targetOrg,
  });
}

async function waitForPath(path) {
  for (let attempt = 0; attempt < 500; attempt += 1) {
    try {
      await lstat(path);
      return;
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
    await new Promise((resolve) => setTimeout(resolve, 2));
  }
  assert.fail(`Timed out waiting for private readiness intent ${path}`);
}

async function waitForWriterTickets(path, expected) {
  for (let attempt = 0; attempt < 500; attempt += 1) {
    const tickets = (await readdir(path)).filter((name) =>
      /^[a-f0-9]{32}\.lock$/u.test(name));
    if (tickets.length >= expected) return;
    await new Promise((resolve) => setTimeout(resolve, 2));
  }
  assert.fail(`Timed out waiting for ${expected} org-registry writer tickets`);
}

function fixtureManifest(orgFingerprint) {
  const core = {
    schema_version: CONTRACTS.sandboxFixtureManifest,
    fixture_set_id: "sap-readiness-race-fixture-001",
    org_fingerprint: orgFingerprint,
    field_map_version: FIELD_MAP_VERSION,
    suite_version: SANDBOX_SUITE_VERSION,
    created_at: new Date(START - 60_000).toISOString(),
    expires_at: new Date(START + 60 * 60_000).toISOString(),
    synthetic_marker: "SAPCERT001",
    unique_account: {
      id: IDS.account1,
      exact_name: "SAPCERT001 Unique Holdings",
    },
    ambiguous_account: {
      exact_name: "SAPCERT001 Repeated Name",
      account_ids: [IDS.account3, IDS.account4],
    },
    no_match_name: "SAPCERT001 No Exact Match",
    prefix_account: {
      literal_prefix: "SAPCERT001 Prefix",
      account_ids: [IDS.account5],
    },
    family: {
      seed_account_id: IDS.account1,
      account_ids: [IDS.account1, IDS.account2],
      expected_currencies: ["EUR", "USD"],
    },
  };
  return { ...core, manifest_digest: digest(core) };
}

function approvalTrustFixture() {
  const { privateKey, publicKey } = generateKeyPairSync("ed25519");
  const issuer = "readiness-race-approval-authority";
  const keyId = "sandbox-certifier-key";
  return {
    document: {
      schema_version: CONTRACTS.approvalTrust,
      classification: CLASSIFICATION,
      audience: CERTIFICATION_APPROVAL_AUDIENCE,
      keys: [{
        issuer,
        key_id: keyId,
        role: CERTIFICATION_APPROVAL_ROLES.sandbox,
        public_key_spki: publicKey.export({
          format: "der",
          type: "spki",
        }).toString("base64"),
        not_before: new Date(START - 60 * 60_000).toISOString(),
        expires_at: new Date(START + 60 * 60_000).toISOString(),
      }],
    },
    assertion(scope) {
      const core = {
        schema_version: CONTRACTS.approvalAssertion,
        issuer,
        key_id: keyId,
        subject_digest: "1".repeat(64),
        role: CERTIFICATION_APPROVAL_ROLES.sandbox,
        audience: CERTIFICATION_APPROVAL_AUDIENCE,
        reference: "SANDBOX-AUTHORIZATION-READINESS-RACE",
        scope_digest: scope.scope_digest,
        nonce: "readinessRaceNonce000001",
        issued_at: scope.issued_at,
        expires_at: scope.expires_at,
      };
      return {
        ...core,
        signature: signBytes(
          null,
          Buffer.from(canonicalJson(core), "utf8"),
          privateKey,
        ).toString("base64url"),
      };
    },
  };
}

async function installApprovalTrust(stateStore, trust) {
  await writeFile(
    join(stateStore.paths.skill_directory, "approval-trust.json"),
    `${canonicalJson(trust.document)}\n`,
    { encoding: "utf8", flag: "wx", mode: 0o600 },
  );
}

async function certifiedSandbox(t, {
  alias,
  friendlyLabel,
} = {}) {
  const stateRoot = await mkdtemp(join(tmpdir(), "sf-readiness-race-"));
  t.after(async () => {
    await rm(stateRoot, { recursive: true, force: true });
  });
  let current = START;
  const clock = () => new Date(current);
  const stateStore = createStateStore({
    stateRoot,
    now: clock,
  });
  const dependencies = {
    stateStore,
    now: clock,
    clientFactory: async (targetOrg) => client(targetOrg),
  };
  const diagnosis = await doctor({
    schema_version: CONTRACTS.doctorRequest,
    target_org: alias,
    friendly_label: friendlyLabel,
    environment: "sandbox",
  }, dependencies);
  const packageAttestation = await attestCertificationPackage();
  const registry = validateOrgRegistry(
    await stateStore.readOrgRegistry(),
  );
  const offline = resolveRegistryEntry(registry, alias);
  const evidence = buildSandboxCertificationEvidence({
    orgFingerprint: offline.org_fingerprint,
    runtimeAttestationDigest: RUNTIME_DIGEST,
    packageDigest: packageAttestation.package_digest,
    metadataCompatibilityDigest: digest(
      diagnosis.metadata_compatibility,
    ),
    fixtureManifestDigest: "a".repeat(64),
    authorizationScopeDigest: "b".repeat(64),
    authorizationAssertionDigest: "c".repeat(64),
    queryCount: 1,
    startedAt: clock(),
    completedAt: clock(),
  });
  const certified = markSandboxReadCertified(offline, {
    evidence,
    now: clock(),
  });
  await stateStore.updateOrgRegistry((currentRegistry) =>
    upsertRegistryEntry(
      validateOrgRegistry(currentRegistry),
      certified,
    ));
  return {
    alias,
    clock,
    stateStore,
    packageDigest: packageAttestation.package_digest,
    metadataCompatibilityDigest: digest(
      diagnosis.metadata_compatibility,
    ),
    advance(milliseconds) {
      current += milliseconds;
    },
  };
}

test("a queued readiness change blocks a query paused before issuance", async (t) => {
  const stateRoot = await mkdtemp(join(tmpdir(), "sf-readiness-issuance-"));
  t.after(async () => {
    await rm(stateRoot, { recursive: true, force: true });
  });
  const stateStore = createStateStore({
    stateRoot,
    now: () => new Date(START),
  });
  await stateStore.initialize();

  let signalPrepared;
  const prepared = new Promise((resolve) => {
    signalPrepared = resolve;
  });
  let resumeIssuance;
  const resume = new Promise((resolve) => {
    resumeIssuance = resolve;
  });
  let queryCalls = 0;
  const guarded = stateStore.withOrgRegistryReadiness(
    async (_currentRegistry, lease) => {
      signalPrepared();
      await resume;
      return await lease.issueQuery(async () => {
        queryCalls += 1;
        return [];
      });
    },
  );
  const blocked = assert.rejects(guarded, {
    code: "CERTIFICATION_CHANGE_PENDING",
  });

  await prepared;
  const writer = stateStore.updateOrgRegistry(
    async (currentRegistry) => currentRegistry,
  );
  await waitForPath(stateStore.paths.org_registry_write_pending);
  await assert.rejects(
    () => lstat(stateStore.paths.org_registry_write_intent),
    { code: "ENOENT" },
  );
  resumeIssuance();

  await blocked;
  await writer;
  assert.equal(queryCalls, 0);
});

test("a safety downgrade waits for a concurrent registry writer", async (t) => {
  const run = await certifiedSandbox(t, {
    alias: "synthetic-complete",
    friendlyLabel: "Serialized UAT",
  });
  const before = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  const original = resolveRegistryEntry(before, run.alias);
  let signalWriter;
  const writerAcquired = new Promise((resolve) => {
    signalWriter = resolve;
  });
  let releaseWriter;
  const holdWriter = new Promise((resolve) => {
    releaseWriter = resolve;
  });
  const benignWriter = run.stateStore.updateOrgRegistry(
    async (currentRegistry) => {
      signalWriter();
      await holdWriter;
      return currentRegistry;
    },
  );
  await writerAcquired;

  const downgrade = run.stateStore.updateOrgRegistry(
    (currentRegistry) => {
      const registry = validateOrgRegistry(currentRegistry);
      const current = resolveRegistryEntry(registry, run.alias);
      assert.equal(
        current.certification_evidence.receipt_digest,
        original.certification_evidence.receipt_digest,
      );
      return upsertRegistryEntry(
        registry,
        downgradeRegistryEntry(current),
      );
    },
  );
  const downgradeOutcome = downgrade.then(
    () => ({ error: null }),
    (error) => ({ error }),
  );
  await new Promise((resolve) => setImmediate(resolve));
  releaseWriter();
  await benignWriter;
  const outcome = await downgradeOutcome;

  assert.equal(outcome.error, null);
  const after = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  assert.equal(
    resolveRegistryEntry(after, run.alias).certification_state,
    "offline_validated",
  );
});

test("a queued safety downgrade blocks readiness across the writer baton", async (t) => {
  const run = await certifiedSandbox(t, {
    alias: "synthetic-complete",
    friendlyLabel: "Baton UAT",
  });
  const before = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  const original = resolveRegistryEntry(before, run.alias);
  let signalWriter;
  const writerAcquired = new Promise((resolve) => {
    signalWriter = resolve;
  });
  let releaseWriter;
  const holdWriter = new Promise((resolve) => {
    releaseWriter = resolve;
  });
  const benignWriter = run.stateStore.updateOrgRegistry(
    async (currentRegistry) => {
      signalWriter();
      await holdWriter;
      return currentRegistry;
    },
  );
  await writerAcquired;

  let signalDowngrade;
  const downgradeAcquired = new Promise((resolve) => {
    signalDowngrade = resolve;
  });
  let releaseDowngrade;
  const holdDowngrade = new Promise((resolve) => {
    releaseDowngrade = resolve;
  });
  const downgrade = run.stateStore.updateOrgRegistry(
    async (currentRegistry) => {
      signalDowngrade();
      await holdDowngrade;
      const registry = validateOrgRegistry(currentRegistry);
      const current = resolveRegistryEntry(registry, run.alias);
      assert.equal(
        current.certification_evidence.receipt_digest,
        original.certification_evidence.receipt_digest,
      );
      return upsertRegistryEntry(
        registry,
        downgradeRegistryEntry(current),
      );
    },
  );
  await waitForWriterTickets(
    run.stateStore.paths.org_registry_writer_tickets,
    2,
  );
  releaseWriter();
  await benignWriter;

  let queryCalls = 0;
  try {
    await assert.rejects(
      () => run.stateStore.withOrgRegistryReadiness(
        async (_currentRegistry, lease) =>
          await lease.issueQuery(async () => {
            queryCalls += 1;
            return [];
          }),
      ),
      { code: "CERTIFICATION_CHANGE_PENDING" },
    );
    assert.equal(queryCalls, 0);
  } finally {
    await downgradeAcquired;
    releaseDowngrade();
  }
  await downgrade;
  const after = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  assert.equal(
    resolveRegistryEntry(after, run.alias).certification_state,
    "offline_validated",
  );
});

test("a readiness lease permits exactly one concurrent query issuance", async (t) => {
  const stateRoot = await mkdtemp(join(tmpdir(), "sf-readiness-once-"));
  t.after(async () => {
    await rm(stateRoot, { recursive: true, force: true });
  });
  const stateStore = createStateStore({
    stateRoot,
    now: () => new Date(START),
  });
  await stateStore.initialize();
  let queryCalls = 0;
  const outcomes = await stateStore.withOrgRegistryReadiness(
    async (_currentRegistry, lease) =>
      await Promise.allSettled([
        lease.issueQuery(async () => {
          queryCalls += 1;
          return "first";
        }),
        lease.issueQuery(async () => {
          queryCalls += 1;
          return "second";
        }),
      ]),
  );

  assert.equal(queryCalls, 1);
  assert.equal(
    outcomes.filter((outcome) => outcome.status === "fulfilled").length,
    1,
  );
  const [rejected] = outcomes.filter((outcome) =>
    outcome.status === "rejected");
  assert.equal(
    rejected.reason.code,
    "INVALID_ORG_REGISTRY_OPERATION",
  );
});

test("runtime drift during a conversational query revokes readiness before releasing the lease", async (t) => {
  const run = await certifiedSandbox(t, {
    alias: "synthetic-complete",
    friendlyLabel: "Runtime Drift UAT",
  });
  let queryAttempts = 0;
  const dependencies = {
    stateStore: run.stateStore,
    now: run.clock,
    clientFactory: async (targetOrg) => {
      const currentClient = client(targetOrg);
      currentClient.query = async () => {
        queryAttempts += 1;
        throw new SafetyError(
          "SF_EXECUTABLE_REATTESTATION_REQUIRED",
          "Synthetic runtime changed before query issuance",
        );
      };
      return currentClient;
    },
  };
  const started = await start({
    schema_version: CONTRACTS.startRequest,
    target_org: run.alias,
    account_selector: {
      mode: "exact_name",
      value: "Example Holdings",
    },
  }, dependencies);
  const canceled = await continueConversation({
    schema_version: CONTRACTS.continueRequest,
    session_id: started.session_id,
    decision: { action: "confirm_org_and_plan" },
  }, dependencies);

  assert.equal(queryAttempts, 1);
  assert.equal(canceled.status, "canceled");
  const after = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  assert.equal(
    resolveRegistryEntry(after, run.alias).certification_state,
    "offline_validated",
  );
});

test("a continuation performs one full metadata sweep rather than one per data query", async (t) => {
  const run = await certifiedSandbox(t, {
    alias: "synthetic-complete",
    friendlyLabel: "Metadata Sweep UAT",
  });
  const describeCalls = [];
  let activeClient;
  const dependencies = {
    stateStore: run.stateStore,
    now: run.clock,
    clientFactory: async (targetOrg) => {
      const currentClient = client(targetOrg);
      const describe = currentClient.describe.bind(currentClient);
      currentClient.describe = async (objectName) => {
        describeCalls.push(objectName);
        return await describe(objectName);
      };
      activeClient = currentClient;
      return currentClient;
    },
  };
  const fullSweep = Object.keys(FIELD_POLICY);
  const countFullSweeps = () => {
    let count = 0;
    for (let start = 0;
      start <= describeCalls.length - fullSweep.length;
      start += 1) {
      if (fullSweep.every((objectName, offset) =>
        describeCalls[start + offset] === objectName)) {
        count += 1;
      }
    }
    return count;
  };

  const started = await start({
    schema_version: CONTRACTS.startRequest,
    target_org: run.alias,
    account_selector: {
      mode: "exact_name",
      value: "Example Holdings",
    },
  }, dependencies);
  assert.equal(countFullSweeps(), 1);

  describeCalls.length = 0;
  const completed = await continueConversation({
    schema_version: CONTRACTS.continueRequest,
    session_id: started.session_id,
    decision: { action: "confirm_org_and_plan" },
  }, dependencies);

  assert.equal(completed.status, "complete");
  assert(activeClient.queryCount > 1);
  assert.equal(countFullSweeps(), 1);
});

test("a downgrade initiated after query one blocks every later data query", async (t) => {
  const run = await certifiedSandbox(t, {
    alias: "synthetic-complete",
    friendlyLabel: "Guarded UAT",
  });
  const queries = [];
  let downgrade = null;
  const dependencies = {
    stateStore: run.stateStore,
    now: run.clock,
    clientFactory: async (targetOrg) => {
      const currentClient = client(targetOrg);
      const query = currentClient.query.bind(currentClient);
      currentClient.query = async (soql) => {
        queries.push(soql);
        const rows = await query(soql);
        if (queries.length === 1) {
          downgrade = run.stateStore.updateOrgRegistry(
            (currentRegistry) => {
              const registry = validateOrgRegistry(currentRegistry);
              const entry = resolveRegistryEntry(
                registry,
                run.alias,
              );
              return upsertRegistryEntry(
                registry,
                downgradeRegistryEntry(entry),
              );
            },
          );
          await waitForPath(
            run.stateStore.paths.org_registry_write_pending,
          );
        }
        return rows;
      };
      return currentClient;
    },
  };
  const started = await start({
    schema_version: CONTRACTS.startRequest,
    target_org: run.alias,
    account_selector: {
      mode: "exact_name",
      value: "Example Holdings",
    },
  }, dependencies);
  const stopped = await continueConversation({
    schema_version: CONTRACTS.continueRequest,
    session_id: started.session_id,
    decision: { action: "confirm_org_and_plan" },
  }, dependencies);
  await downgrade;

  assert.equal(queries.length, 1);
  assert.equal(stopped.status, "canceled");
  assert.notEqual(stopped.status, "complete");
  const registry = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  assert.equal(
    resolveRegistryEntry(registry, run.alias).certification_state,
    "offline_validated",
  );
});

test("a concurrent verification refresh cannot preserve old evidence after failed recertification", async (t) => {
  const run = await certifiedSandbox(t, {
    alias: "synthetic-certification",
    friendlyLabel: "Certification UAT",
  });
  const originalRegistry = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  const originalEntry = resolveRegistryEntry(
    originalRegistry,
    run.alias,
  );
  const oldEvidenceDigest =
    originalEntry.certification_evidence.receipt_digest;
  const identity = await client(run.alias).orgDisplay();
  const manifest = fixtureManifest(originalEntry.org_fingerprint);
  let phase = "prepare";
  let recertificationClientCount = 0;
  let refreshPerformed = false;
  const engine = createCertificationEngine({
    stateStore: run.stateStore,
    now: run.clock,
    packageAttestor: async () => ({
      package_digest: run.packageDigest,
    }),
    clientFactory: async (targetOrg) => {
      const currentClient = client(targetOrg);
      if (phase === "recertify") {
        recertificationClientCount += 1;
        if (recertificationClientCount === 2) {
          await run.stateStore.updateOrgRegistry(
            (currentRegistry) => {
              const registry = validateOrgRegistry(currentRegistry);
              const latest = resolveRegistryEntry(
                registry,
                run.alias,
              );
              const refreshed = refreshRegistryVerification(
                latest,
                {
                  identity,
                  orgType: "sandbox",
                  environment: "sandbox",
                  runtimeAttestationDigest: RUNTIME_DIGEST,
                  packageDigest: run.packageDigest,
                  metadataCompatibilityDigest:
                    run.metadataCompatibilityDigest,
                  now: run.clock(),
                },
              );
              refreshPerformed = true;
              return upsertRegistryEntry(registry, refreshed);
            },
          );
          throw new SafetyError(
            "SYNTHETIC_RECERTIFICATION_FAILURE",
            "Synthetic recertification failure after concurrent refresh",
          );
        }
      }
      return currentClient;
    },
  });

  run.advance(1_000);
  const trust = approvalTrustFixture();
  await installApprovalTrust(run.stateStore, trust);
  const prepared = await engine.prepareSandboxScope({
    schema_version: CONTRACTS.sandboxCertificationScopeRequest,
    target_org: run.alias,
    fixture_manifest: manifest,
  });
  phase = "recertify";
  await assert.rejects(
    () => engine.certifySandbox({
      schema_version: CONTRACTS.sandboxCertificationRequest,
      target_org: run.alias,
      fixture_manifest: manifest,
      approval_scope: prepared.approval_scope,
      authorization: trust.assertion(prepared.approval_scope),
    }),
    { code: "SYNTHETIC_RECERTIFICATION_FAILURE" },
  );

  assert.equal(refreshPerformed, true);
  const finalRegistry = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  const finalEntry = resolveRegistryEntry(finalRegistry, run.alias);
  assert.equal(finalEntry.certification_state, "offline_validated");
  assert.equal(finalEntry.certification_evidence, null);
  assert.notEqual(
    finalEntry.certification_evidence?.receipt_digest,
    oldEvidenceDigest,
  );
});

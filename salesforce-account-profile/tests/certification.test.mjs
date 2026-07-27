import assert from "node:assert/strict";
import {
  generateKeyPairSync,
  randomBytes,
  sign,
} from "node:crypto";
import {
  chmod,
  mkdtemp,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  approvalTrustPath,
} from "../scripts/approval-trust.mjs";
import {
  buildProductionApprovalEvidence,
  buildSandboxCertificationEvidence,
  validateProductionApprovalEvidence,
  validateSandboxCertificationEvidence,
} from "../scripts/certification-evidence.mjs";
import {
  validateProductionApprovalRequest,
  validateSandboxCertificationRequest,
  validateSandboxScopeRequest,
} from "../scripts/certification-contracts.mjs";
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
  assertRegistryReadiness,
  markSandboxReadCertified,
  upsertRegistryEntry,
  validateOrgRegistry,
} from "../scripts/org-registry.mjs";
import { attestCertificationPackage } from "../scripts/package-attestation.mjs";
import {
  canonicalJson,
  digest,
  SafetyError,
} from "../scripts/security.mjs";
import { SfClient } from "../scripts/sf-client.mjs";
import { createStateStore } from "../scripts/state-store.mjs";

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

function fixtureManifest(orgFingerprint, {
  familyAccountIds = [IDS.account1, IDS.account2],
  createdAt = new Date(START - 60_000),
  expiresAt = new Date(START + 60 * 60_000),
} = {}) {
  const core = {
    schema_version: CONTRACTS.sandboxFixtureManifest,
    fixture_set_id: "sap-certification-fixture-001",
    org_fingerprint: orgFingerprint,
    field_map_version: FIELD_MAP_VERSION,
    suite_version: SANDBOX_SUITE_VERSION,
    created_at: createdAt.toISOString(),
    expires_at: expiresAt.toISOString(),
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
      account_ids: familyAccountIds,
      expected_currencies: ["EUR", "USD"],
    },
  };
  return { ...core, manifest_digest: digest(core) };
}

function signer(keyId, role, subjectDigit) {
  const keys = generateKeyPairSync("ed25519");
  return {
    issuer: "synthetic-approval-authority",
    key_id: keyId,
    role,
    subject_digest: subjectDigit.repeat(64),
    public_key_spki: keys.publicKey.export({
      type: "spki",
      format: "der",
    }).toString("base64"),
    private_key: keys.privateKey,
  };
}

function signedAssertion(scope, authority, overrides = {}) {
  const core = {
    schema_version: CONTRACTS.approvalAssertion,
    issuer: authority.issuer,
    key_id: authority.key_id,
    subject_digest: authority.subject_digest,
    role: authority.role,
    audience: CERTIFICATION_APPROVAL_AUDIENCE,
    reference: `${authority.key_id}-approval`,
    scope_digest: scope.scope_digest,
    nonce: randomBytes(24).toString("base64url"),
    issued_at: scope.issued_at,
    expires_at: scope.expires_at,
    ...overrides,
  };
  return {
    ...core,
    signature: sign(
      null,
      Buffer.from(canonicalJson(core), "utf8"),
      authority.private_key,
    ).toString("base64url"),
  };
}

async function harness(t, {
  packageAttestor = attestCertificationPackage,
  clientFactory = async (targetOrg) => client(targetOrg),
} = {}) {
  const stateRoot = await mkdtemp(join(tmpdir(), "sf-profile-certification-"));
  t.after(async () => {
    await rm(stateRoot, { recursive: true, force: true });
  });
  let current = START;
  const clock = () => new Date(current);
  const stateStore = createStateStore({
    stateRoot,
    now: clock,
  });
  await stateStore.initialize();
  const authorities = {
    sandbox: signer(
      "01-sandbox",
      CERTIFICATION_APPROVAL_ROLES.sandbox,
      "1",
    ),
    administrator: signer(
      "02-administrator",
      CERTIFICATION_APPROVAL_ROLES.productionAdministrator,
      "2",
    ),
    riskOwner: signer(
      "03-risk-owner",
      CERTIFICATION_APPROVAL_ROLES.productionRiskOwner,
      "3",
    ),
  };
  const trust = {
    schema_version: CONTRACTS.approvalTrust,
    classification: CLASSIFICATION,
    audience: CERTIFICATION_APPROVAL_AUDIENCE,
    keys: Object.values(authorities).map((authority) => ({
      issuer: authority.issuer,
      key_id: authority.key_id,
      role: authority.role,
      public_key_spki: authority.public_key_spki,
      not_before: new Date(START - 60 * 60_000).toISOString(),
      expires_at: new Date(START + 24 * 60 * 60_000).toISOString(),
    })),
  };
  await writeFile(
    approvalTrustPath(stateStore),
    `${canonicalJson(trust)}\n`,
    { mode: 0o600, flag: "wx" },
  );
  const doctorDependencies = {
    stateStore,
    now: clock,
    clientFactory,
  };
  await doctor({
    schema_version: CONTRACTS.doctorRequest,
    target_org: "synthetic-certification",
    friendly_label: "Synthetic Certification",
    environment: "sandbox",
  }, doctorDependencies);
  await doctor({
    schema_version: CONTRACTS.doctorRequest,
    target_org: "synthetic-production",
    friendly_label: "Synthetic Production",
    environment: "production",
  }, doctorDependencies);
  const engine = createCertificationEngine({
    stateStore,
    clientFactory,
    packageAttestor,
    now: clock,
  });
  return {
    engine,
    stateStore,
    clock,
    authorities,
    advance(milliseconds) {
      current += milliseconds;
    },
  };
}

async function certify(run, manifest) {
  const prepared = await run.engine.prepareSandboxScope({
    schema_version: CONTRACTS.sandboxCertificationScopeRequest,
    target_org: "synthetic-certification",
    fixture_manifest: manifest,
  });
  return await run.engine.certifySandbox({
    schema_version: CONTRACTS.sandboxCertificationRequest,
    target_org: "synthetic-certification",
    fixture_manifest: manifest,
    approval_scope: prepared.approval_scope,
    authorization: signedAssertion(
      prepared.approval_scope,
      run.authorities.sandbox,
    ),
  });
}

async function approveProduction(run, sandboxEvidenceDigest) {
  const prepared = await run.engine.prepareProductionScope({
    schema_version: CONTRACTS.productionApprovalScopeRequest,
    target_org: "synthetic-production",
    sandbox_evidence_digest: sandboxEvidenceDigest,
  });
  return await run.engine.approveProduction({
    schema_version: CONTRACTS.productionApprovalRequest,
    target_org: "synthetic-production",
    sandbox_evidence_digest: sandboxEvidenceDigest,
    approval_scope: prepared.approval_scope,
    administrator_approval: signedAssertion(
      prepared.approval_scope,
      run.authorities.administrator,
    ),
    risk_owner_approval: signedAssertion(
      prepared.approval_scope,
      run.authorities.riskOwner,
    ),
  });
}

test("sandbox suite creates self-validating evidence and production approval executes zero data queries", async (t) => {
  const run = await harness(t);
  const initial = validateOrgRegistry(await run.stateStore.readOrgRegistry());
  const sandbox = initial.entries.find((entry) =>
    entry.alias === "synthetic-certification");
  const manifest = fixtureManifest(sandbox.org_fingerprint);
  const certified = await certify(run, manifest);

  assert.equal(certified.status, "sandbox_read_certified");
  assert.equal(certified.scenario_count, 9);
  assert.match(certified.evidence_digest, /^[a-f0-9]{64}$/u);
  const afterSandbox = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  const sandboxEntry = afterSandbox.entries.find((entry) =>
    entry.alias === "synthetic-certification");
  assert.equal(
    assertRegistryReadiness(sandboxEntry),
    sandboxEntry,
  );
  assert.equal(
    sandboxEntry.certification_evidence.receipt_digest,
    certified.evidence_digest,
  );

  const prepared = await run.engine.prepareProductionScope({
    schema_version: CONTRACTS.productionApprovalScopeRequest,
    target_org: "synthetic-production",
    sandbox_evidence_digest: certified.evidence_digest,
  });
  const approved = await run.engine.approveProduction({
    schema_version: CONTRACTS.productionApprovalRequest,
    target_org: "synthetic-production",
    sandbox_evidence_digest: certified.evidence_digest,
    approval_scope: prepared.approval_scope,
    administrator_approval: signedAssertion(
      prepared.approval_scope,
      run.authorities.administrator,
    ),
    risk_owner_approval: signedAssertion(
      prepared.approval_scope,
      run.authorities.riskOwner,
    ),
  });
  assert.equal(approved.status, "production_read_approved");
  assert.equal(approved.data_queries_executed, 0);
  const publicResult = JSON.stringify(approved);
  for (const forbidden of [
    "synthetic-production",
    "synthetic-certification",
    "example.invalid",
    "001000000000001AAA",
    "ADMIN-APPROVAL-001",
    "RISK-APPROVAL-001",
    fakeSf,
  ]) {
    assert.equal(publicResult.includes(forbidden), false);
  }
  const finalRegistry = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  const production = finalRegistry.entries.find((entry) =>
    entry.alias === "synthetic-production");
  assert.equal(assertRegistryReadiness(production), production);
  assert.equal(
    production.certification_evidence.data_query_count,
    0,
  );
});

test("production scope rejects a package not covered by current sandbox evidence", async (t) => {
  let packageDigest = "a".repeat(64);
  const run = await harness(t, {
    packageAttestor: async () => ({
      package_digest: packageDigest,
    }),
  });
  const initial = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  const sandbox = initial.entries.find((entry) =>
    entry.alias === "synthetic-certification");
  const certified = await certify(
    run,
    fixtureManifest(sandbox.org_fingerprint),
  );

  packageDigest = "b".repeat(64);
  await assert.rejects(
    () => run.engine.prepareProductionScope({
      schema_version: CONTRACTS.productionApprovalScopeRequest,
      target_org: "synthetic-production",
      sandbox_evidence_digest: certified.evidence_digest,
    }),
    { code: "SANDBOX_CERTIFICATION_DRIFT" },
  );
  const registry = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  assert.equal(
    registry.entries.find((entry) =>
      entry.alias === "synthetic-certification").certification_state,
    "offline_validated",
  );
  assert.equal(
    registry.entries.find((entry) =>
      entry.alias === "synthetic-production").certification_state,
    "offline_validated",
  );
});

test("sandbox metadata drift atomically revokes dependent production before any conversational query", async (t) => {
  let driftMetadata = false;
  const clientsAfterDrift = [];
  const driftClientFactory = async (targetOrg) => {
    const currentClient = client(targetOrg);
    if (driftMetadata) {
      clientsAfterDrift.push(currentClient);
    }
    if (driftMetadata
      && targetOrg === "synthetic-certification") {
      const describe = currentClient.describe.bind(currentClient);
      currentClient.describe = async (objectName) => {
        const fields = new Map(await describe(objectName));
        if (objectName === "Account") {
          fields.delete("Support_Status__c");
        }
        return fields;
      };
    }
    return currentClient;
  };
  const run = await harness(t, {
    clientFactory: driftClientFactory,
  });
  const initial = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  const sandbox = initial.entries.find((entry) =>
    entry.alias === "synthetic-certification");
  const manifest = fixtureManifest(sandbox.org_fingerprint);
  const certified = await certify(run, manifest);
  const preparedProduction = await run.engine.prepareProductionScope({
    schema_version: CONTRACTS.productionApprovalScopeRequest,
    target_org: "synthetic-production",
    sandbox_evidence_digest: certified.evidence_digest,
  });
  await run.engine.approveProduction({
    schema_version: CONTRACTS.productionApprovalRequest,
    target_org: "synthetic-production",
    sandbox_evidence_digest: certified.evidence_digest,
    approval_scope: preparedProduction.approval_scope,
    administrator_approval: signedAssertion(
      preparedProduction.approval_scope,
      run.authorities.administrator,
    ),
    risk_owner_approval: signedAssertion(
      preparedProduction.approval_scope,
      run.authorities.riskOwner,
    ),
  });
  const certifiedRegistry = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );

  driftMetadata = true;
  const preparedAgain = await run.engine.prepareSandboxScope({
    schema_version: CONTRACTS.sandboxCertificationScopeRequest,
    target_org: "synthetic-certification",
    fixture_manifest: manifest,
  });
  assert.equal(preparedAgain.status, "approval_required");

  const afterDrift = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  assert.equal(
    afterDrift.entries.find((entry) =>
      entry.alias === "synthetic-certification").certification_state,
    "offline_validated",
  );
  assert.equal(
    afterDrift.entries.find((entry) =>
      entry.alias === "synthetic-production").certification_state,
    "offline_validated",
  );

  await run.stateStore.updateOrgRegistry(() => certifiedRegistry);
  await assert.rejects(
    () => start({
      schema_version: CONTRACTS.startRequest,
      target_org: "synthetic-certification",
      account_selector: {
        mode: "exact_name",
        value: "SAPCERT001 Unique Holdings",
      },
    }, {
      stateStore: run.stateStore,
      now: run.clock,
      clientFactory: driftClientFactory,
    }),
    { code: "CERTIFICATION_DRIFT" },
  );
  const afterConversationDrift = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  assert.equal(
    afterConversationDrift.entries.find((entry) =>
      entry.alias === "synthetic-certification").certification_state,
    "offline_validated",
  );
  assert.equal(
    afterConversationDrift.entries.find((entry) =>
      entry.alias === "synthetic-production").certification_state,
    "offline_validated",
  );

  await assert.rejects(
    () => start({
      schema_version: CONTRACTS.startRequest,
      target_org: "synthetic-production",
      account_selector: {
        mode: "exact_name",
        value: "SAPCERT001 Unique Holdings",
      },
    }, {
      stateStore: run.stateStore,
      now: run.clock,
      clientFactory: driftClientFactory,
    }),
    { code: "PRODUCTION_NOT_APPROVED" },
  );
  assert.equal(
    clientsAfterDrift.reduce(
      (count, currentClient) =>
        count + currentClient.queryCount,
      0,
    ),
    0,
  );
});

test("conversational pre-query runtime drift revokes sandbox and dependent production before data reads", async (t) => {
  let driftMode = "none";
  const driftClients = [];
  const runtimeDrift = (phase) => new SafetyError(
    "SF_EXECUTABLE_REATTESTATION_REQUIRED",
    `Synthetic runtime changed during ${phase}`,
  );
  const runtimeClientFactory = async (targetOrg) => {
    const currentClient = client(targetOrg);
    if (targetOrg !== "synthetic-certification"
      || driftMode === "none") {
      return currentClient;
    }
    driftClients.push(currentClient);
    if (driftMode === "initial_org_display") {
      currentClient.orgDisplay = async () => {
        throw runtimeDrift("org identity verification");
      };
    } else if (driftMode === "workflow_describe") {
      const describe = currentClient.describe.bind(currentClient);
      let accountDescribes = 0;
      currentClient.describe = async (objectName) => {
        if (objectName === "Account") {
          accountDescribes += 1;
          if (accountDescribes > 1) {
            throw runtimeDrift("workflow metadata verification");
          }
        }
        return await describe(objectName);
      };
    }
    return currentClient;
  };
  const run = await harness(t, {
    clientFactory: runtimeClientFactory,
  });
  const initial = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  const sandbox = initial.entries.find((entry) =>
    entry.alias === "synthetic-certification");
  const certified = await certify(
    run,
    fixtureManifest(sandbox.org_fingerprint),
  );
  await approveProduction(run, certified.evidence_digest);
  const certifiedRegistry = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  const startRequest = {
    schema_version: CONTRACTS.startRequest,
    target_org: "synthetic-certification",
    account_selector: {
      mode: "exact_name",
      value: "SAPCERT001 Unique Holdings",
    },
  };
  const dependencies = {
    stateStore: run.stateStore,
    now: run.clock,
    clientFactory: runtimeClientFactory,
  };
  const assertBothRevoked = async () => {
    const current = validateOrgRegistry(
      await run.stateStore.readOrgRegistry(),
    );
    assert.equal(
      current.entries.find((entry) =>
        entry.alias === "synthetic-certification").certification_state,
      "offline_validated",
    );
    assert.equal(
      current.entries.find((entry) =>
        entry.alias === "synthetic-production").certification_state,
      "offline_validated",
    );
  };

  driftMode = "initial_org_display";
  await assert.rejects(
    () => start(startRequest, dependencies),
    { code: "SF_EXECUTABLE_REATTESTATION_REQUIRED" },
  );
  await assertBothRevoked();

  await run.stateStore.updateOrgRegistry(() => certifiedRegistry);
  driftMode = "none";
  const sessionBeforeIdentityDrift = await start(
    startRequest,
    dependencies,
  );
  driftMode = "initial_org_display";
  const identityCanceled = await continueConversation({
    schema_version: CONTRACTS.continueRequest,
    session_id: sessionBeforeIdentityDrift.session_id,
    decision: { action: "confirm_org_and_plan" },
  }, dependencies);
  assert.equal(identityCanceled.status, "canceled");
  assert.equal(identityCanceled.next_action, "cancel");
  await assertBothRevoked();

  await run.stateStore.updateOrgRegistry(() => certifiedRegistry);
  driftMode = "none";
  const sessionBeforeDescribeDrift = await start(
    startRequest,
    dependencies,
  );
  driftMode = "workflow_describe";
  const describeCanceled = await continueConversation({
    schema_version: CONTRACTS.continueRequest,
    session_id: sessionBeforeDescribeDrift.session_id,
    decision: { action: "confirm_org_and_plan" },
  }, dependencies);
  assert.equal(describeCanceled.status, "canceled");
  assert.equal(describeCanceled.next_action, "cancel");
  await assertBothRevoked();

  assert(driftClients.length >= 3);
  assert.equal(
    driftClients.reduce(
      (count, currentClient) => count + currentClient.queryCount,
      0,
    ),
    0,
  );
});

test("failed recertification downgrades the sandbox and dependent production approval", async (t) => {
  const run = await harness(t);
  const initial = validateOrgRegistry(await run.stateStore.readOrgRegistry());
  const sandbox = initial.entries.find((entry) =>
    entry.alias === "synthetic-certification");
  const manifest = fixtureManifest(sandbox.org_fingerprint);
  const certified = await certify(run, manifest);
  const preparedProduction = await run.engine.prepareProductionScope({
    schema_version: CONTRACTS.productionApprovalScopeRequest,
    target_org: "synthetic-production",
    sandbox_evidence_digest: certified.evidence_digest,
  });
  await run.engine.approveProduction({
    schema_version: CONTRACTS.productionApprovalRequest,
    target_org: "synthetic-production",
    sandbox_evidence_digest: certified.evidence_digest,
    approval_scope: preparedProduction.approval_scope,
    administrator_approval: signedAssertion(
      preparedProduction.approval_scope,
      run.authorities.administrator,
    ),
    risk_owner_approval: signedAssertion(
      preparedProduction.approval_scope,
      run.authorities.riskOwner,
    ),
  });

  run.advance(1_000);
  const wrongManifest = fixtureManifest(sandbox.org_fingerprint, {
    familyAccountIds: [IDS.account1],
  });
  const prepared = await run.engine.prepareSandboxScope({
    schema_version: CONTRACTS.sandboxCertificationScopeRequest,
    target_org: "synthetic-certification",
    fixture_manifest: wrongManifest,
  });
  await assert.rejects(
    () => run.engine.certifySandbox({
      schema_version: CONTRACTS.sandboxCertificationRequest,
      target_org: "synthetic-certification",
      fixture_manifest: wrongManifest,
      approval_scope: prepared.approval_scope,
      authorization: signedAssertion(
        prepared.approval_scope,
        run.authorities.sandbox,
      ),
    }),
    { code: "SANDBOX_CERTIFICATION_FAILED" },
  );
  const registry = validateOrgRegistry(await run.stateStore.readOrgRegistry());
  assert.equal(
    registry.entries.find((entry) =>
      entry.alias === "synthetic-certification").certification_state,
    "offline_validated",
  );
  assert.equal(
    registry.entries.find((entry) =>
      entry.alias === "synthetic-production").certification_state,
    "offline_validated",
  );
  assert.deepEqual(await run.stateStore.listSessions(), []);
});

test("successful sandbox recertification invalidates production bound to the old receipt", async (t) => {
  const run = await harness(t);
  const initial = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  const sandbox = initial.entries.find((entry) =>
    entry.alias === "synthetic-certification");
  const manifest = fixtureManifest(sandbox.org_fingerprint);
  const first = await certify(run, manifest);
  const productionScope = await run.engine.prepareProductionScope({
    schema_version: CONTRACTS.productionApprovalScopeRequest,
    target_org: "synthetic-production",
    sandbox_evidence_digest: first.evidence_digest,
  });
  await run.engine.approveProduction({
    schema_version: CONTRACTS.productionApprovalRequest,
    target_org: "synthetic-production",
    sandbox_evidence_digest: first.evidence_digest,
    approval_scope: productionScope.approval_scope,
    administrator_approval: signedAssertion(
      productionScope.approval_scope,
      run.authorities.administrator,
    ),
    risk_owner_approval: signedAssertion(
      productionScope.approval_scope,
      run.authorities.riskOwner,
    ),
  });

  run.advance(1_000);
  const second = await certify(run, manifest);
  assert.notEqual(second.evidence_digest, first.evidence_digest);
  const registry = validateOrgRegistry(
    await run.stateStore.readOrgRegistry(),
  );
  assert.equal(
    registry.entries.find((entry) =>
      entry.alias === "synthetic-certification").certification_state,
    "sandbox_read_certified",
  );
  assert.equal(
    registry.entries.find((entry) =>
      entry.alias === "synthetic-production").certification_state,
    "offline_validated",
  );
});

test("a changed certification receipt cancels an active plan before any data query", async (t) => {
  const run = await harness(t);
  const initial = validateOrgRegistry(await run.stateStore.readOrgRegistry());
  const sandbox = initial.entries.find((entry) =>
    entry.alias === "synthetic-certification");
  await certify(run, fixtureManifest(sandbox.org_fingerprint));
  const queryAttempts = [];
  const conversationDependencies = {
    stateStore: run.stateStore,
    now: run.clock,
    clientFactory: async (targetOrg) => {
      const currentClient = client(targetOrg);
      const query = currentClient.query.bind(currentClient);
      currentClient.query = async (soql) => {
        queryAttempts.push(soql);
        return await query(soql);
      };
      return currentClient;
    },
  };
  const started = await start({
    schema_version: CONTRACTS.startRequest,
    target_org: "synthetic-certification",
    account_selector: {
      mode: "exact_name",
      value: "SAPCERT001 Unique Holdings",
    },
  }, conversationDependencies);
  const before = validateOrgRegistry(await run.stateStore.readOrgRegistry());
  const currentEntry = before.entries.find((entry) =>
    entry.alias === "synthetic-certification");
  run.advance(1_000);
  const changedAt = run.clock();
  const priorEvidence = currentEntry.certification_evidence;
  const changedEvidence = buildSandboxCertificationEvidence({
    orgFingerprint: currentEntry.org_fingerprint,
    runtimeAttestationDigest:
      priorEvidence.runtime_attestation_digest,
    packageDigest: priorEvidence.package_digest,
    metadataCompatibilityDigest:
      priorEvidence.metadata_compatibility_digest,
    fixtureManifestDigest: priorEvidence.fixture_manifest_digest,
    authorizationScopeDigest: "9".repeat(64),
    authorizationAssertionDigest: "8".repeat(64),
    queryCount: priorEvidence.query_count,
    startedAt: changedAt,
    completedAt: changedAt,
  });
  const changedEntry = markSandboxReadCertified(currentEntry, {
    evidence: changedEvidence,
    now: changedAt,
  });
  await run.stateStore.updateOrgRegistry((registry) =>
    upsertRegistryEntry(validateOrgRegistry(registry), changedEntry));

  const canceled = await continueConversation({
    schema_version: CONTRACTS.continueRequest,
    session_id: started.session_id,
    decision: { action: "confirm_org_and_plan" },
  }, conversationDependencies);
  assert.equal(canceled.status, "canceled");
  assert.equal(canceled.next_action, "cancel");
  assert.deepEqual(queryAttempts, []);
});

test("certification contracts reject unknown fields, stale scopes, cross-org manifests, and reused approval identities", async (t) => {
  const run = await harness(t);
  const registry = validateOrgRegistry(await run.stateStore.readOrgRegistry());
  const sandbox = registry.entries.find((entry) =>
    entry.alias === "synthetic-certification");
  const manifest = fixtureManifest(sandbox.org_fingerprint);
  assert.throws(
    () => validateSandboxScopeRequest({
      schema_version: CONTRACTS.sandboxCertificationScopeRequest,
      target_org: "synthetic-certification",
      fixture_manifest: { ...manifest, sf_path: "synthetic-executable" },
    }),
    { code: "UNKNOWN_INPUT_FIELD" },
  );
  assert.throws(
    () => validateSandboxScopeRequest({
      schema_version: CONTRACTS.sandboxCertificationScopeRequest,
      target_org: "synthetic-certification",
      fixture_manifest: {
        ...manifest,
        org_fingerprint: "f".repeat(64),
      },
    }),
    { code: "INVALID_CERTIFICATION_REQUEST" },
  );

  const prepared = await run.engine.prepareSandboxScope({
    schema_version: CONTRACTS.sandboxCertificationScopeRequest,
    target_org: "synthetic-certification",
    fixture_manifest: manifest,
  });
  assert.throws(
    () => validateSandboxCertificationRequest({
      schema_version: CONTRACTS.sandboxCertificationRequest,
      target_org: "synthetic-certification",
      fixture_manifest: manifest,
      approval_scope: prepared.approval_scope,
      authorization: {
        ...signedAssertion(
          prepared.approval_scope,
          run.authorities.sandbox,
        ),
        client_factory: "forbidden",
      },
    }),
    { code: "UNKNOWN_INPUT_FIELD" },
  );
  run.advance(30 * 60_000);
  await assert.rejects(
    () => run.engine.certifySandbox({
      schema_version: CONTRACTS.sandboxCertificationRequest,
      target_org: "synthetic-certification",
      fixture_manifest: manifest,
      approval_scope: prepared.approval_scope,
      authorization: signedAssertion(
        prepared.approval_scope,
        run.authorities.sandbox,
      ),
    }),
    { code: "CERTIFICATION_SCOPE_EXPIRED" },
  );

  assert.throws(
    () => validateProductionApprovalRequest({
      schema_version: CONTRACTS.productionApprovalRequest,
      target_org: "synthetic-production",
      sandbox_evidence_digest: "a".repeat(64),
      approval_scope: {
        schema_version: CONTRACTS.productionApprovalScope,
        production_org_fingerprint: "1".repeat(64),
        sandbox_org_fingerprint: "2".repeat(64),
        sandbox_evidence_digest: "a".repeat(64),
        runtime_attestation_digest: "3".repeat(64),
        package_digest: "4".repeat(64),
        field_map_version: FIELD_MAP_VERSION,
        metadata_compatibility_digest: "5".repeat(64),
        issued_at: "2030-01-01T00:00:00.000Z",
        expires_at: "2030-01-01T00:30:00.000Z",
        scope_digest: "6".repeat(64),
      },
      administrator_approval: {
        reference: "SAME",
        principal_digest: "7".repeat(64),
        approved_at: "2030-01-01T00:01:00.000Z",
        scope_digest: "6".repeat(64),
      },
      risk_owner_approval: {
        reference: "SAME",
        principal_digest: "7".repeat(64),
        approved_at: "2030-01-01T00:01:00.000Z",
        scope_digest: "6".repeat(64),
      },
    }),
    { code: "INVALID_CERTIFICATION_REQUEST" },
  );
});

test("every mutation of a bound certification receipt invalidates its digest", () => {
  const sandbox = buildSandboxCertificationEvidence({
    orgFingerprint: "1".repeat(64),
    runtimeAttestationDigest: "2".repeat(64),
    packageDigest: "3".repeat(64),
    metadataCompatibilityDigest: "4".repeat(64),
    fixtureManifestDigest: "5".repeat(64),
    authorizationScopeDigest: "6".repeat(64),
    authorizationAssertionDigest: "7".repeat(64),
    queryCount: 12,
    startedAt: new Date("2030-01-01T00:00:00.000Z"),
    completedAt: new Date("2030-01-01T00:01:00.000Z"),
  });
  for (const mutation of [
    { ...sandbox, package_digest: "9".repeat(64) },
    { ...sandbox, query_count: 13 },
    { ...sandbox, completed_at: "2030-01-01T00:02:00.000Z" },
    { ...sandbox, scenario_ids: [...sandbox.scenario_ids].reverse() },
  ]) {
    assert.throws(
      () => validateSandboxCertificationEvidence(mutation),
      { code: "INVALID_CERTIFICATION_EVIDENCE" },
    );
  }

  const production = buildProductionApprovalEvidence({
    productionOrgFingerprint: "1".repeat(64),
    sandboxEvidenceDigest: sandbox.receipt_digest,
    runtimeAttestationDigest: "2".repeat(64),
    packageDigest: "3".repeat(64),
    metadataCompatibilityDigest: "4".repeat(64),
    approvalScopeDigest: "8".repeat(64),
    administratorApproval: {
      reference: "ADMIN",
      subject_digest: "5".repeat(64),
      issued_at: "2030-01-01T00:01:00.000Z",
      scope_digest: "8".repeat(64),
      assertion_digest: "a".repeat(64),
    },
    riskOwnerApproval: {
      reference: "RISK",
      subject_digest: "6".repeat(64),
      issued_at: "2030-01-01T00:01:00.000Z",
      scope_digest: "8".repeat(64),
      assertion_digest: "b".repeat(64),
    },
    completedAt: new Date("2030-01-01T00:02:00.000Z"),
  });
  for (const mutation of [
    { ...production, sandbox_evidence_digest: "9".repeat(64) },
    {
      ...production,
      risk_owner_approval: {
        ...production.risk_owner_approval,
        subject_digest: "7".repeat(64),
      },
    },
  ]) {
    assert.throws(
      () => validateProductionApprovalEvidence(mutation),
      { code: "INVALID_CERTIFICATION_EVIDENCE" },
    );
  }
});

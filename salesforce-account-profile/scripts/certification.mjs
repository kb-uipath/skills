import {
  CERTIFICATION_SCOPE_TTL_MS,
  CERTIFICATION_APPROVAL_ROLES,
  CLASSIFICATION,
  CONTRACTS,
  FIELD_MAP_VERSION,
  SANDBOX_SCENARIO_IDS,
  SANDBOX_SUITE_VERSION,
  WARNING_ANNUALIZATION,
} from "./constants.mjs";
import {
  loadApprovalTrust,
  verifyApprovalAssertion,
} from "./approval-trust.mjs";
import {
  certificationContractInternals,
  validateProductionApprovalRequest,
  validateProductionScopeRequest,
  validateSandboxCertificationRequest,
  validateSandboxScopeRequest,
} from "./certification-contracts.mjs";
import {
  buildProductionApprovalEvidence,
  buildSandboxCertificationEvidence,
} from "./certification-evidence.mjs";
import { inspectMetadataCompatibility } from "./metadata-compatibility.mjs";
import {
  appendApprovalAssertions,
  assertApprovalAssertionsUnused,
  downgradeRegistryEntry,
  downgradeRegistryReadiness,
  markProductionReadApproved,
  markSandboxReadCertified,
  refreshRegistryVerification,
  resolveRegistryEntry,
  upsertRegistryEntry,
  validateOrgRegistry,
  verifyRegistryIdentity,
} from "./org-registry.mjs";
import {
  abort,
  continueConversation,
  start,
} from "./orchestrator.mjs";
import { attestCertificationPackage } from "./package-attestation.mjs";
import {
  digest,
  SafetyError,
  sanitizeText,
} from "./security.mjs";
import { createProductionSfClient } from "./sf-client.mjs";
import { defaultSfRuntimeManifestPath } from "./sf-runtime.mjs";
import { createStateStore } from "./state-store.mjs";

const SYNTHETIC_NAME_KEYS = new Set([
  "Name",
  "AccountName",
  "OpportunityName",
  "OwnerName",
  "ManagerName",
  "ParentName",
  "ProductName",
]);

function serviceClock(now) {
  return () => {
    const value = typeof now === "function" ? now() : now ?? new Date();
    const instant = value instanceof Date
      ? new Date(value.getTime())
      : new Date(value);
    if (!Number.isFinite(instant.getTime())) {
      throw new SafetyError(
        "INVALID_CLOCK",
        "Certification clock is invalid",
      );
    }
    return instant;
  };
}

function validateClient(client) {
  if (!client
    || typeof client.orgDisplay !== "function"
    || typeof client.orgList !== "function"
    || typeof client.describe !== "function"
    || typeof client.query !== "function"
    || !/^[a-f0-9]{64}$/u.test(client.attestationDigest)
    || client.queryCount !== 0) {
    throw new SafetyError(
      "INVALID_SF_CLIENT",
      "Certification requires a fresh attested Salesforce client",
    );
  }
  return client;
}

function maskedUsername(value) {
  const safe = sanitizeText(value);
  const separator = safe.lastIndexOf("@");
  if (separator <= 0 || separator === safe.length - 1) {
    return `${safe.slice(0, 1)}***`;
  }
  return `${safe.slice(0, 1)}***@${safe.slice(separator + 1)}`;
}

function identityHost(identity) {
  let parsed;
  try {
    parsed = new URL(identity.instance_url);
  } catch {
    throw new SafetyError(
      "ORG_DISCOVERY_MISMATCH",
      "Selected-org identity has an invalid instance host",
    );
  }
  if (parsed.protocol !== "https:"
    || parsed.username
    || parsed.password
    || !parsed.hostname) {
    throw new SafetyError(
      "ORG_DISCOVERY_MISMATCH",
      "Selected-org identity has an unsafe instance host",
    );
  }
  return parsed.hostname.toLocaleLowerCase("en-US");
}

function authorizedOrgFor(entry, identity, authorizedOrgs) {
  const matches = authorizedOrgs.filter((org) => org.alias === entry.alias);
  if (matches.length !== 1) {
    throw new SafetyError(
      "ORG_DISCOVERY_MISMATCH",
      "The enrolled org must match exactly one redacted authorized-org entry",
    );
  }
  const [authorized] = matches;
  if (authorized.org_id_suffix !== entry.org_id_suffix
    || authorized.org_id_suffix !== identity.org_id.slice(-6)
    || authorized.instance_host !== entry.instance_host
    || authorized.instance_host !== identityHost(identity)
    || authorized.masked_username !== maskedUsername(identity.username)
    || authorized.org_type !== entry.org_type) {
    throw new SafetyError(
      "ORG_DISCOVERY_MISMATCH",
      "Authorized-org discovery does not match the enrolled org identity",
    );
  }
  return authorized;
}

function sameValues(actual, expected) {
  return Array.isArray(actual)
    && actual.length === expected.length
    && actual.every((value, index) => value === expected[index]);
}

function requireCondition(condition, check, code = "SANDBOX_CERTIFICATION_FAILED") {
  if (!condition) {
    throw new SafetyError(
      code,
      `Certification failed at ${check}; operational readiness was not advanced`,
    );
  }
}

function continuation(sessionId, decision) {
  return {
    schema_version: CONTRACTS.continueRequest,
    session_id: sessionId,
    decision,
  };
}

function startRequest(targetOrg, selector) {
  return {
    schema_version: CONTRACTS.startRequest,
    target_org: targetOrg,
    account_selector: selector,
    preset: "pipeline",
    output_type: "json",
  };
}

function familyStartRequest(targetOrg, accountId) {
  return {
    schema_version: CONTRACTS.startRequest,
    target_org: targetOrg,
    account_selector: { mode: "id", value: accountId },
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
    filters: {},
    output_type: "json",
  };
}

async function cleanupSessions(store, sessionIds) {
  for (const sessionId of sessionIds) {
    try {
      await store.deleteSession(sessionId, "abort");
    } catch (error) {
      if (error?.code !== "SESSION_NOT_FOUND") throw error;
    }
  }
}

function assertNoUnsafeArtifact(value) {
  const serialized = JSON.stringify(value);
  if (/(?:access[_-]?token|refresh[_-]?token|client[_-]?secret|password|Bearer\s+|00D[A-Za-z0-9]{10,}!)/iu.test(serialized)
    || /(?:\u001b\[[0-?]*[ -/]*[@-~]|[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069])/u.test(serialized)) {
    throw new SafetyError(
      "SANDBOX_CERTIFICATION_FAILED",
      "Certification artifacts contained unsafe text or token-shaped data",
    );
  }
}

function assertSyntheticNames(value, marker) {
  let checked = 0;
  function visit(node) {
    if (Array.isArray(node)) {
      node.forEach(visit);
      return;
    }
    if (!node || typeof node !== "object") return;
    for (const [key, item] of Object.entries(node)) {
      if (SYNTHETIC_NAME_KEYS.has(key)
        && typeof item === "string"
        && item.length) {
        checked += 1;
        if (!item.includes(marker)) {
          throw new SafetyError(
            "NON_SYNTHETIC_CERTIFICATION_DATA",
            "Certification returned a named CRM record without the approved synthetic marker",
          );
        }
      }
      visit(item);
    }
  }
  visit(value);
  if (checked < 1) {
    throw new SafetyError(
      "NON_SYNTHETIC_CERTIFICATION_DATA",
      "Certification did not return any marker-bound synthetic record names",
    );
  }
}

async function runSandboxJourneys(request, {
  store,
  clientFactory,
  clock,
}) {
  const sessionIds = new Set();
  const clients = [];
  const dependencies = {
    stateStore: store,
    now: clock,
    allowOfflineExecution: true,
    clientFactory: async (targetOrg) => {
      const client = validateClient(await clientFactory(targetOrg));
      clients.push(client);
      return client;
    },
  };
  const fixture = request.fixture_manifest;
  const artifacts = [];
  try {
    const selectedStart = await start(startRequest(
      request.target_org,
      {
        mode: "exact_name",
        value: fixture.unique_account.exact_name,
      },
    ), dependencies);
    sessionIds.add(selectedStart.session_id);
    const selectedComplete = await continueConversation(
      continuation(selectedStart.session_id, {
        action: "confirm_org_and_plan",
      }),
      dependencies,
    );
    requireCondition(
      selectedStart.next_action === "confirm_org_and_plan"
        && selectedComplete.status === "complete"
        && selectedComplete.structured_artifact?.selected_account?.Id
          === fixture.unique_account.id,
      "unique_pipeline",
    );
    artifacts.push(selectedStart, selectedComplete);

    const ambiguousStart = await start(startRequest(
      request.target_org,
      {
        mode: "exact_name",
        value: fixture.ambiguous_account.exact_name,
      },
    ), dependencies);
    sessionIds.add(ambiguousStart.session_id);
    const ambiguous = await continueConversation(
      continuation(ambiguousStart.session_id, {
        action: "confirm_org_and_plan",
      }),
      dependencies,
    );
    requireCondition(
      ambiguous.next_action === "choose_account"
        && sameValues(
          (ambiguous.choices ?? []).map((choice) => choice.Id).sort(),
          fixture.ambiguous_account.account_ids,
        ),
      "ambiguous_chooser",
    );
    artifacts.push(ambiguousStart, ambiguous);
    await abort({
      schema_version: CONTRACTS.abortRequest,
      session_id: ambiguousStart.session_id,
    }, dependencies);

    const noMatchStart = await start(startRequest(
      request.target_org,
      {
        mode: "exact_name",
        value: fixture.no_match_name,
      },
    ), dependencies);
    sessionIds.add(noMatchStart.session_id);
    const noMatch = await continueConversation(
      continuation(noMatchStart.session_id, {
        action: "confirm_org_and_plan",
      }),
      dependencies,
    );
    requireCondition(
      noMatch.next_action === "choose_account"
        && Array.isArray(noMatch.choices)
        && noMatch.choices.length === 0,
      "literal_prefix",
    );
    const prefix = await continueConversation(
      continuation(noMatchStart.session_id, {
        action: "choose_account",
        literal_prefix: fixture.prefix_account.literal_prefix,
      }),
      dependencies,
    );
    requireCondition(
      prefix.next_action === "choose_account"
        && sameValues(
          (prefix.choices ?? []).map((choice) => choice.Id).sort(),
          fixture.prefix_account.account_ids,
        ),
      "literal_prefix",
    );
    artifacts.push(noMatchStart, noMatch, prefix);
    await abort({
      schema_version: CONTRACTS.abortRequest,
      session_id: noMatchStart.session_id,
    }, dependencies);

    const familyStart = await start(
      familyStartRequest(
        request.target_org,
        fixture.family.seed_account_id,
      ),
      dependencies,
    );
    sessionIds.add(familyStart.session_id);
    const familyApproval = await continueConversation(
      continuation(familyStart.session_id, {
        action: "confirm_org_and_plan",
      }),
      dependencies,
    );
    requireCondition(
      familyApproval.next_action === "approve_family_scope"
        && sameValues(
          [...(familyApproval.account_ids ?? [])].sort(),
          fixture.family.account_ids,
        ),
      "family_exact_scope",
    );
    const familyComplete = await continueConversation(
      continuation(familyStart.session_id, {
        action: "approve_family_scope",
      }),
      dependencies,
    );
    const view = familyComplete.structured_artifact;
    requireCondition(
      familyComplete.status === "complete"
        && sameValues(
          (view?.currency_summaries ?? [])
            .map((summary) => summary.currency_iso_code)
            .sort(),
          fixture.family.expected_currencies,
        ),
      "multicurrency",
    );
    requireCondition(
      (view?.warnings ?? [])
        .some((warning) => warning.code === WARNING_ANNUALIZATION),
      "annualization_disabled",
    );
    artifacts.push(familyStart, familyApproval, familyComplete);

    assertNoUnsafeArtifact(artifacts);
    assertSyntheticNames(artifacts, fixture.synthetic_marker);
    await cleanupSessions(store, sessionIds);
    requireCondition(
      (await store.listSessions()).length === 0,
      "session_cleanup",
    );
    const queryCount = clients.reduce(
      (sum, client) => sum + client.queryCount,
      0,
    );
    requireCondition(queryCount > 0, "query_count");
    return {
      artifact_digest: digest(artifacts),
      query_count: queryCount,
    };
  } finally {
    await cleanupSessions(store, sessionIds);
  }
}

function scopeWindow(issuedAt, fixtureExpiry = null) {
  const maximum = new Date(
    issuedAt.getTime() + CERTIFICATION_SCOPE_TTL_MS,
  );
  if (!fixtureExpiry || fixtureExpiry >= maximum) return maximum;
  return new Date(fixtureExpiry.getTime());
}

function sandboxScope({
  entry,
  runtimeAttestationDigest,
  packageDigest,
  metadataCompatibilityDigest,
  fixtureManifestDigest,
  issuedAt,
  expiresAt,
}) {
  const core = {
    schema_version: CONTRACTS.sandboxCertificationScope,
    org_fingerprint: entry.org_fingerprint,
    runtime_attestation_digest: runtimeAttestationDigest,
    package_digest: packageDigest,
    field_map_version: FIELD_MAP_VERSION,
    metadata_compatibility_digest: metadataCompatibilityDigest,
    suite_version: SANDBOX_SUITE_VERSION,
    fixture_manifest_digest: fixtureManifestDigest,
    issued_at: issuedAt.toISOString(),
    expires_at: expiresAt.toISOString(),
  };
  return { ...core, scope_digest: digest(core) };
}

function productionScope({
  productionEntry,
  sandboxEntry,
  runtimeAttestationDigest,
  packageDigest,
  metadataCompatibilityDigest,
  issuedAt,
  expiresAt,
}) {
  const core = {
    schema_version: CONTRACTS.productionApprovalScope,
    production_org_fingerprint: productionEntry.org_fingerprint,
    sandbox_org_fingerprint: sandboxEntry.org_fingerprint,
    sandbox_evidence_digest:
      sandboxEntry.certification_evidence.receipt_digest,
    runtime_attestation_digest: runtimeAttestationDigest,
    package_digest: packageDigest,
    field_map_version: FIELD_MAP_VERSION,
    metadata_compatibility_digest: metadataCompatibilityDigest,
    issued_at: issuedAt.toISOString(),
    expires_at: expiresAt.toISOString(),
  };
  return { ...core, scope_digest: digest(core) };
}

function validateScopeWindow(scope, now) {
  const issuedAt = new Date(scope.issued_at);
  const expiresAt = new Date(scope.expires_at);
  if (expiresAt.getTime() - issuedAt.getTime()
      > CERTIFICATION_SCOPE_TTL_MS
    || issuedAt > now
    || now >= expiresAt) {
    throw new SafetyError(
      "CERTIFICATION_SCOPE_EXPIRED",
      "Certification approval scope is expired or outside its fixed validity window",
    );
  }
}

function exactScope(actual, expected, code) {
  if (digest(actual) !== digest(expected)) {
    throw new SafetyError(
      code,
      "Approval scope no longer matches the current org, runtime, package, metadata, or fixture evidence",
    );
  }
}

function certificationResult(schemaVersion, fields) {
  return {
    schema_version: schemaVersion,
    classification: CLASSIFICATION,
    ...fields,
  };
}

function findSandboxEvidence(registry, evidenceDigest) {
  const matches = registry.entries.filter((entry) =>
    entry.environment === "sandbox"
    && entry.certification_state === "sandbox_read_certified"
    && entry.certification_evidence?.receipt_digest === evidenceDigest);
  if (matches.length !== 1) {
    throw new SafetyError(
      "SANDBOX_EVIDENCE_NOT_FOUND",
      "Production approval requires one current internally stored sandbox certification receipt",
    );
  }
  return matches[0];
}

async function revokeSandboxAndDependents(store, originalEntry) {
  await store.updateOrgRegistry((current) =>
    downgradeRegistryReadiness(current, originalEntry));
}

async function revokeProduction(store, originalEntry) {
  if (originalEntry.certification_state !== "production_read_approved") {
    return;
  }
  await store.updateOrgRegistry((current) => {
    const registry = validateOrgRegistry(current);
    const latest = registry.entries.find((entry) =>
      entry.alias === originalEntry.alias);
    if (!latest || digest(latest) !== digest(originalEntry)) return registry;
    return upsertRegistryEntry(
      registry,
      downgradeRegistryEntry(latest),
    );
  });
}

async function reserveSandboxAuthorization(
  store,
  originalEntry,
  verification,
  now,
) {
  let reserved;
  await store.updateOrgRegistry((current) => {
    let registry = assertApprovalAssertionsUnused(
      validateOrgRegistry(current),
      [verification],
    );
    const latest = resolveRegistryEntry(
      registry,
      originalEntry.alias,
    );
    if (digest(latest) !== digest(originalEntry)) {
      throw new SafetyError(
        "CERTIFICATION_CONCURRENT_CHANGE",
        "Org registry changed before sandbox authorization reservation",
      );
    }
    const priorEvidenceDigest =
      latest.certification_evidence?.receipt_digest ?? null;
    reserved = appendApprovalAssertions(
      downgradeRegistryEntry(latest),
      {
        verifications: [verification],
        now,
      },
    );
    registry = upsertRegistryEntry(registry, reserved);
    if (priorEvidenceDigest !== null) {
      for (const entry of [...registry.entries]) {
        if (entry.certification_state === "production_read_approved"
          && entry.certification_evidence?.sandbox_evidence_digest
            === priorEvidenceDigest) {
          registry = upsertRegistryEntry(
            registry,
            downgradeRegistryEntry(entry),
          );
        }
      }
    }
    return registry;
  });
  return reserved;
}

async function reserveProductionApprovals(
  store,
  originalProduction,
  originalSandbox,
  verifications,
  now,
) {
  let reserved;
  await store.updateOrgRegistry((current) => {
    let registry = assertApprovalAssertionsUnused(
      validateOrgRegistry(current),
      verifications,
    );
    const latestProduction = resolveRegistryEntry(
      registry,
      originalProduction.alias,
    );
    const latestSandbox = findSandboxEvidence(
      registry,
      originalSandbox.certification_evidence.receipt_digest,
    );
    if (digest(latestProduction) !== digest(originalProduction)
      || digest(latestSandbox) !== digest(originalSandbox)) {
      throw new SafetyError(
        "CERTIFICATION_CONCURRENT_CHANGE",
        "Org registry changed before production approval reservation",
      );
    }
    reserved = appendApprovalAssertions(
      downgradeRegistryEntry(latestProduction),
      {
        verifications,
        now,
      },
    );
    registry = upsertRegistryEntry(registry, reserved);
    return registry;
  });
  return reserved;
}

export function createCertificationEngine({
  stateStore = createStateStore(),
  clientFactory = async (targetOrg) =>
    await createProductionSfClient({
      targetOrg,
      runtimeManifestPath: defaultSfRuntimeManifestPath(),
    }),
  packageAttestor = attestCertificationPackage,
  now = () => new Date(),
} = {}) {
  const clock = serviceClock(now);

  async function inspect(entry) {
    const client = validateClient(await clientFactory(entry.alias));
    const authorizedOrgs = await client.orgList();
    const identity = await client.orgDisplay();
    verifyRegistryIdentity(entry, identity);
    const authorized = authorizedOrgFor(entry, identity, authorizedOrgs);
    const metadata = await inspectMetadataCompatibility(client);
    const packageAttestation = await packageAttestor();
    if (!/^[a-f0-9]{64}$/u.test(
      packageAttestation?.package_digest ?? "",
    ) || client.queryCount !== 0) {
      throw new SafetyError(
        "INVALID_PACKAGE_ATTESTATION",
        "Certification package or metadata inspection was incomplete",
      );
    }
    return {
      authorized,
      client,
      identity,
      metadata,
      metadataDigest: digest(metadata),
      packageDigest: packageAttestation.package_digest,
    };
  }

  function sandboxInspectionMatches(entry, inspected) {
    const evidence = entry.certification_evidence;
    return entry.environment === "sandbox"
      && entry.org_type === "sandbox"
      && entry.certification_state === "sandbox_read_certified"
      && evidence?.org_fingerprint === entry.org_fingerprint
      && evidence.runtime_attestation_digest
        === inspected.client.attestationDigest
      && evidence.package_digest === inspected.packageDigest
      && evidence.metadata_compatibility_digest
        === inspected.metadataDigest
      && inspected.authorized.org_type === "sandbox"
      && inspected.client.queryCount === 0;
  }

  async function inspectSandboxForCertification(entry, {
    requireCurrent = false,
  } = {}) {
    let inspected;
    try {
      inspected = await inspect(entry);
    } catch (error) {
      if (entry.certification_state === "sandbox_read_certified") {
        await revokeSandboxAndDependents(stateStore, entry);
      }
      throw error;
    }
    if (entry.certification_state !== "sandbox_read_certified"
      || sandboxInspectionMatches(entry, inspected)) {
      return { entry, inspected };
    }
    await revokeSandboxAndDependents(stateStore, entry);
    if (requireCurrent) {
      throw new SafetyError(
        "SANDBOX_CERTIFICATION_DRIFT",
        "Referenced sandbox evidence is no longer current",
      );
    }
    const currentRegistry = validateOrgRegistry(
      await stateStore.readOrgRegistry(),
    );
    return {
      entry: resolveRegistryEntry(currentRegistry, entry.alias),
      inspected,
    };
  }

  async function inspectCurrentSandbox(entry) {
    const current = await inspectSandboxForCertification(entry, {
      requireCurrent: true,
    });
    return current.inspected;
  }

  async function prepareSandboxScope(input) {
    const request = validateSandboxScopeRequest(input);
    await stateStore.initialize();
    const registry = validateOrgRegistry(await stateStore.readOrgRegistry());
    let entry = resolveRegistryEntry(registry, request.target_org);
    if (entry.alias !== request.target_org
      || entry.environment !== "sandbox"
      || entry.org_type !== "sandbox"
      || request.fixture_manifest.org_fingerprint
        !== entry.org_fingerprint) {
      throw new SafetyError(
        "SANDBOX_CERTIFICATION_INVALID",
        "Scope preparation requires the exact enrolled sandbox and a fixture manifest bound to it",
      );
    }
    const issuedAt = clock();
    const fixtureCreatedAt = new Date(request.fixture_manifest.created_at);
    const fixtureExpiresAt = new Date(request.fixture_manifest.expires_at);
    if (fixtureCreatedAt > issuedAt || issuedAt >= fixtureExpiresAt) {
      throw new SafetyError(
        "SANDBOX_FIXTURE_EXPIRED",
        "Synthetic fixture manifest is not currently valid",
      );
    }
    const current = await inspectSandboxForCertification(entry);
    entry = current.entry;
    const { inspected } = current;
    const expiresAt = scopeWindow(issuedAt, fixtureExpiresAt);
    const scope = sandboxScope({
      entry,
      runtimeAttestationDigest: inspected.client.attestationDigest,
      packageDigest: inspected.packageDigest,
      metadataCompatibilityDigest: inspected.metadataDigest,
      fixtureManifestDigest: request.fixture_manifest.manifest_digest,
      issuedAt,
      expiresAt,
    });
    return certificationResult(
      CONTRACTS.sandboxCertificationScopeResult,
      {
        status: "approval_required",
        approval_scope: scope,
        message: "Obtain one explicit sandbox certification authorization bound to this expiring scope, then run the read-only synthetic suite.",
      },
    );
  }

  async function certifySandbox(input) {
    const request = validateSandboxCertificationRequest(input);
    await stateStore.initialize();
    const registry = validateOrgRegistry(await stateStore.readOrgRegistry());
    let entry = resolveRegistryEntry(registry, request.target_org);
    if (entry.alias !== request.target_org
      || entry.environment !== "sandbox"
      || entry.org_type !== "sandbox"
      || request.fixture_manifest.org_fingerprint
        !== entry.org_fingerprint) {
      throw new SafetyError(
        "SANDBOX_CERTIFICATION_INVALID",
        "Certification requires the exact enrolled sandbox and its bound synthetic fixture manifest",
      );
    }
    const startedAt = clock();
    validateScopeWindow(request.approval_scope, startedAt);
    const fixtureExpiresAt = new Date(request.fixture_manifest.expires_at);
    if (startedAt >= fixtureExpiresAt) {
      throw new SafetyError(
        "SANDBOX_FIXTURE_EXPIRED",
        "Synthetic fixture manifest expired before certification",
      );
    }
    const current = await inspectSandboxForCertification(entry);
    entry = current.entry;
    const { inspected } = current;
    const expectedScope = sandboxScope({
      entry,
      runtimeAttestationDigest: inspected.client.attestationDigest,
      packageDigest: inspected.packageDigest,
      metadataCompatibilityDigest: inspected.metadataDigest,
      fixtureManifestDigest: request.fixture_manifest.manifest_digest,
      issuedAt: new Date(request.approval_scope.issued_at),
      expiresAt: new Date(request.approval_scope.expires_at),
    });
    exactScope(
      request.approval_scope,
      expectedScope,
      "SANDBOX_SCOPE_MISMATCH",
    );
    const trust = await loadApprovalTrust(stateStore);
    const verifiedAuthorization = verifyApprovalAssertion(
      request.authorization,
      {
        trust,
        expectedRole: CERTIFICATION_APPROVAL_ROLES.sandbox,
        expectedScope: request.approval_scope,
        now: startedAt,
      },
    );
    const reservedEntry = await reserveSandboxAuthorization(
      stateStore,
      entry,
      verifiedAuthorization,
      startedAt,
    );

    let liveAttemptStarted = false;
    try {
      liveAttemptStarted = true;
      const journeys = await runSandboxJourneys(request, {
        store: stateStore,
        clientFactory: async (targetOrg) => {
          const client = validateClient(await clientFactory(targetOrg));
          if (client.attestationDigest
              !== inspected.client.attestationDigest) {
            throw new SafetyError(
              "SF_RUNTIME_CHANGED",
              "Salesforce runtime changed during certification",
            );
          }
          return client;
        },
        clock,
      });
      const completedAt = clock();
      if (completedAt >= new Date(request.approval_scope.expires_at)) {
        throw new SafetyError(
          "CERTIFICATION_SCOPE_EXPIRED",
          "Certification scope expired before the suite completed",
        );
      }
      const evidence = buildSandboxCertificationEvidence({
        orgFingerprint: entry.org_fingerprint,
        runtimeAttestationDigest: inspected.client.attestationDigest,
        packageDigest: inspected.packageDigest,
        metadataCompatibilityDigest: inspected.metadataDigest,
        fixtureManifestDigest:
          request.fixture_manifest.manifest_digest,
        authorizationScopeDigest:
          request.approval_scope.scope_digest,
        authorizationAssertionDigest:
          verifiedAuthorization.assertion_digest,
        queryCount: journeys.query_count,
        startedAt,
        completedAt,
      });
      let certified;
      await stateStore.updateOrgRegistry((current) => {
        const latestRegistry = validateOrgRegistry(current);
        const latest = resolveRegistryEntry(
          latestRegistry,
          request.target_org,
        );
        if (digest(latest) !== digest(reservedEntry)) {
          throw new SafetyError(
            "CERTIFICATION_CONCURRENT_CHANGE",
            "Org registry changed during sandbox certification",
          );
        }
        const refreshed = refreshRegistryVerification(latest, {
          identity: inspected.identity,
          orgType: inspected.authorized.org_type,
          environment: "sandbox",
          runtimeAttestationDigest:
            inspected.client.attestationDigest,
          packageDigest: inspected.packageDigest,
          metadataCompatibilityDigest: inspected.metadataDigest,
          now: completedAt,
        });
        certified = markSandboxReadCertified(refreshed, {
          evidence,
          now: completedAt,
        });
        return upsertRegistryEntry(latestRegistry, certified);
      });
      return certificationResult(
        CONTRACTS.sandboxCertificationResult,
        {
          status: "sandbox_read_certified",
          certification_state: certified.certification_state,
          suite_version: SANDBOX_SUITE_VERSION,
          field_map_version: FIELD_MAP_VERSION,
          scenario_count: SANDBOX_SCENARIO_IDS.length,
          verified_at: certified.certification_verified_at,
          evidence_digest: evidence.receipt_digest,
          message: "The approved sandbox synthetic-record read path passed every required check. Production remains separately blocked.",
        },
      );
    } catch (error) {
      if (liveAttemptStarted) {
        await revokeSandboxAndDependents(
          stateStore,
          reservedEntry,
        );
      }
      throw error;
    }
  }

  async function prepareProductionScope(input) {
    const request = validateProductionScopeRequest(input);
    await stateStore.initialize();
    const registry = validateOrgRegistry(await stateStore.readOrgRegistry());
    const productionEntry = resolveRegistryEntry(
      registry,
      request.target_org,
    );
    const sandboxEntry = findSandboxEvidence(
      registry,
      request.sandbox_evidence_digest,
    );
    if (productionEntry.alias !== request.target_org
      || productionEntry.environment !== "production"
      || productionEntry.org_fingerprint === sandboxEntry.org_fingerprint) {
      throw new SafetyError(
        "PRODUCTION_APPROVAL_INVALID",
        "Scope preparation requires the exact enrolled production org and separate current sandbox evidence",
      );
    }
    const sandboxInspection = await inspectCurrentSandbox(sandboxEntry);
    const inspected = await inspect(productionEntry);
    if (!["production_or_developer", "dev_hub"].includes(
      inspected.authorized.org_type,
    )
      || inspected.client.queryCount !== 0
      || inspected.client.attestationDigest
        !== sandboxInspection.client.attestationDigest
      || inspected.packageDigest !== sandboxInspection.packageDigest) {
      if (inspected.packageDigest !== sandboxInspection.packageDigest) {
        await revokeSandboxAndDependents(stateStore, sandboxEntry);
      }
      throw new SafetyError(
        "PRODUCTION_APPROVAL_INVALID",
        "Production scope preparation requires the sandbox-certified runtime and package, compatible metadata, and zero data queries",
      );
    }
    const issuedAt = clock();
    const expiresAt = scopeWindow(issuedAt);
    const scope = productionScope({
      productionEntry,
      sandboxEntry,
      runtimeAttestationDigest: inspected.client.attestationDigest,
      packageDigest: inspected.packageDigest,
      metadataCompatibilityDigest: inspected.metadataDigest,
      issuedAt,
      expiresAt,
    });
    return certificationResult(
      CONTRACTS.productionApprovalScopeResult,
      {
        status: "approvals_required",
        approval_scope: scope,
        data_queries_executed: 0,
        message: "Obtain distinct administrator and risk-owner approvals bound to this exact expiring production scope.",
      },
    );
  }

  async function approveProduction(input) {
    const request = validateProductionApprovalRequest(input);
    await stateStore.initialize();
    const registry = validateOrgRegistry(await stateStore.readOrgRegistry());
    const productionEntry = resolveRegistryEntry(
      registry,
      request.target_org,
    );
    const sandboxEntry = findSandboxEvidence(
      registry,
      request.sandbox_evidence_digest,
    );
    if (productionEntry.alias !== request.target_org
      || productionEntry.environment !== "production"
      || productionEntry.org_fingerprint === sandboxEntry.org_fingerprint) {
      throw new SafetyError(
        "PRODUCTION_APPROVAL_INVALID",
        "Production approval requires the exact enrolled production org and separate current sandbox evidence",
      );
    }
    const completedAt = clock();
    validateScopeWindow(request.approval_scope, completedAt);
    const sandboxInspection = await inspectCurrentSandbox(sandboxEntry);
    const inspected = await inspect(productionEntry);
    const expectedScope = productionScope({
      productionEntry,
      sandboxEntry,
      runtimeAttestationDigest: inspected.client.attestationDigest,
      packageDigest: inspected.packageDigest,
      metadataCompatibilityDigest: inspected.metadataDigest,
      issuedAt: new Date(request.approval_scope.issued_at),
      expiresAt: new Date(request.approval_scope.expires_at),
    });
    exactScope(
      request.approval_scope,
      expectedScope,
      "PRODUCTION_SCOPE_MISMATCH",
    );
    if (request.sandbox_evidence_digest
        !== request.approval_scope.sandbox_evidence_digest
      || inspected.client.queryCount !== 0
      || inspected.client.attestationDigest
        !== sandboxInspection.client.attestationDigest
      || inspected.packageDigest !== sandboxInspection.packageDigest) {
      if (inspected.packageDigest !== sandboxInspection.packageDigest) {
        await revokeSandboxAndDependents(stateStore, sandboxEntry);
      }
      throw new SafetyError(
        "PRODUCTION_APPROVAL_INVALID",
        "Production approval scope, sandbox dependency, or zero-data-query invariant failed",
      );
    }
    const trust = await loadApprovalTrust(stateStore);
    const administratorVerification = verifyApprovalAssertion(
      request.administrator_approval,
      {
        trust,
        expectedRole:
          CERTIFICATION_APPROVAL_ROLES.productionAdministrator,
        expectedScope: request.approval_scope,
        now: completedAt,
      },
    );
    const riskOwnerVerification = verifyApprovalAssertion(
      request.risk_owner_approval,
      {
        trust,
        expectedRole:
          CERTIFICATION_APPROVAL_ROLES.productionRiskOwner,
        expectedScope: request.approval_scope,
        now: completedAt,
      },
    );
    const reservedProduction = await reserveProductionApprovals(
      stateStore,
      productionEntry,
      sandboxEntry,
      [administratorVerification, riskOwnerVerification],
      completedAt,
    );

    let liveAttemptStarted = false;
    try {
      liveAttemptStarted = true;
      const evidence = buildProductionApprovalEvidence({
        productionOrgFingerprint: productionEntry.org_fingerprint,
        sandboxEvidenceDigest: request.sandbox_evidence_digest,
        runtimeAttestationDigest: inspected.client.attestationDigest,
        packageDigest: inspected.packageDigest,
        metadataCompatibilityDigest: inspected.metadataDigest,
        approvalScopeDigest: request.approval_scope.scope_digest,
        administratorApproval:
          administratorVerification.evidence,
        riskOwnerApproval: riskOwnerVerification.evidence,
        completedAt,
      });
      let approved;
      await stateStore.updateOrgRegistry((current) => {
        const latestRegistry = validateOrgRegistry(current);
        const latestProduction = resolveRegistryEntry(
          latestRegistry,
          request.target_org,
        );
        const latestSandbox = findSandboxEvidence(
          latestRegistry,
          request.sandbox_evidence_digest,
        );
        if (digest(latestProduction) !== digest(reservedProduction)
          || digest(latestSandbox) !== digest(sandboxEntry)) {
          throw new SafetyError(
            "CERTIFICATION_CONCURRENT_CHANGE",
            "Org registry changed during production approval",
          );
        }
        const refreshed = refreshRegistryVerification(
          latestProduction,
          {
            identity: inspected.identity,
            orgType: inspected.authorized.org_type,
            environment: "production",
            runtimeAttestationDigest:
              inspected.client.attestationDigest,
            packageDigest: inspected.packageDigest,
            metadataCompatibilityDigest: inspected.metadataDigest,
            now: completedAt,
          },
        );
        approved = markProductionReadApproved(refreshed, {
          evidence,
          now: completedAt,
        });
        return upsertRegistryEntry(latestRegistry, approved);
      });
      return certificationResult(
        CONTRACTS.productionApprovalResult,
        {
          status: "production_read_approved",
          certification_state: approved.certification_state,
          field_map_version: FIELD_MAP_VERSION,
          verified_at: approved.certification_verified_at,
          evidence_digest: evidence.receipt_digest,
          data_queries_executed: 0,
          message: "Separate sandbox, administrator, and risk-owner evidence was recorded for this exact production scope.",
        },
      );
    } catch (error) {
      if (liveAttemptStarted) {
        await revokeProduction(stateStore, reservedProduction);
      }
      throw error;
    }
  }

  return Object.freeze({
    prepareSandboxScope,
    certifySandbox,
    prepareProductionScope,
    approveProduction,
  });
}

export async function executeCertification(command, input) {
  const engine = createCertificationEngine();
  if (command === "prepare-sandbox-certification") {
    return await engine.prepareSandboxScope(input);
  }
  if (command === "certify-sandbox") {
    return await engine.certifySandbox(input);
  }
  if (command === "prepare-production-approval") {
    return await engine.prepareProductionScope(input);
  }
  if (command === "approve-production") {
    return await engine.approveProduction(input);
  }
  throw new SafetyError(
    "UNKNOWN_COMMAND",
    "Unsupported certification command",
  );
}

export const certificationInternals = Object.freeze({
  SYNTHETIC_NAME_KEYS,
  assertSyntheticNames,
  authorizedOrgFor,
  findSandboxEvidence,
  productionScope,
  runSandboxJourneys,
  sandboxScope,
  validateScopeWindow,
  validateProductionScope:
    certificationContractInternals.validateProductionScope,
  validateSandboxScope:
    certificationContractInternals.validateSandboxScope,
});

import {
  CAPS,
  CERTIFICATION_APPROVAL_ROLES,
  CERTIFICATION_STATES,
  CLASSIFICATION,
  CONTRACTS,
  FIELD_MAP_VERSION,
} from "./constants.mjs";
import {
  validateCertificationEvidence,
  validateProductionApprovalEvidence,
  validateSandboxCertificationEvidence,
} from "./certification-evidence.mjs";
import {
  assertExactKeys,
  digest,
  SafetyError,
  sanitizeText,
  validateAlias,
} from "./security.mjs";

const ENVIRONMENTS = Object.freeze([
  "production",
  "sandbox",
  "scratch",
]);
const ORG_TYPES = Object.freeze([
  "sandbox",
  "production_or_developer",
  "dev_hub",
  "scratch",
]);
const ENVIRONMENTS_BY_ORG_TYPE = Object.freeze({
  sandbox: Object.freeze(["sandbox"]),
  production_or_developer: Object.freeze(["production"]),
  dev_hub: Object.freeze(["production"]),
  scratch: Object.freeze(["scratch"]),
});
const APPROVAL_LEDGER_KEYS = Object.freeze([
  "assertion_digest",
  "replay_key_digest",
  "role",
  "scope_digest",
  "accepted_at",
  "expires_at",
]);
const APPROVAL_ROLES = new Set(
  Object.values(CERTIFICATION_APPROVAL_ROLES),
);

function safeText(value, label, maximum = 120) {
  if (typeof value !== "string"
    || value.length < 1
    || value.length > maximum
    || sanitizeText(value) !== value) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      `${label} must be safe text between 1 and ${maximum} characters`,
    );
  }
  return value;
}

function canonicalInstant(value, label, { nullable = false } = {}) {
  if (nullable && value === null) return null;
  if (typeof value !== "string") {
    throw new SafetyError("INVALID_ORG_REGISTRY", `${label} must be an ISO timestamp`);
  }
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString() !== value) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      `${label} must be a canonical ISO timestamp`,
    );
  }
  return value;
}

function validateApprovalAssertionLedger(ledger) {
  if (!Array.isArray(ledger)
    || ledger.length > CAPS.approvalAssertionsPerOrg) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Approval assertion replay ledger exceeds its safety cap",
    );
  }
  for (const [index, item] of ledger.entries()) {
    const label = `approval_assertion_ledger[${index}]`;
    assertExactKeys(
      item,
      APPROVAL_LEDGER_KEYS,
      APPROVAL_LEDGER_KEYS,
      label,
    );
    if (!/^[a-f0-9]{64}$/u.test(item.assertion_digest)
      || !/^[a-f0-9]{64}$/u.test(item.replay_key_digest)
      || !/^[a-f0-9]{64}$/u.test(item.scope_digest)
      || !APPROVAL_ROLES.has(item.role)) {
      throw new SafetyError(
        "INVALID_ORG_REGISTRY",
        `${label} contains invalid assertion metadata`,
      );
    }
    const acceptedAt = canonicalInstant(
      item.accepted_at,
      `${label}.accepted_at`,
    );
    const expiresAt = canonicalInstant(
      item.expires_at,
      `${label}.expires_at`,
    );
    if (new Date(expiresAt) <= new Date(acceptedAt)) {
      throw new SafetyError(
        "INVALID_ORG_REGISTRY",
        `${label} expiry must follow acceptance`,
      );
    }
  }
  const sorted = [...ledger].sort((left, right) =>
    left.accepted_at.localeCompare(right.accepted_at, "en-US")
    || left.assertion_digest.localeCompare(
      right.assertion_digest,
      "en-US",
    ));
  if (sorted.some((item, index) =>
    item.assertion_digest !== ledger[index].assertion_digest)) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Approval assertion replay ledger must use canonical order",
    );
  }
  if (new Set(ledger.map((item) => item.assertion_digest)).size
      !== ledger.length
    || new Set(ledger.map((item) => item.replay_key_digest)).size
      !== ledger.length) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Approval assertion replay ledger contains a duplicate",
    );
  }
  return ledger;
}

function identityHost(instanceUrl) {
  let parsed;
  try {
    parsed = new URL(instanceUrl);
  } catch {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Salesforce org identity has an invalid instance URL",
    );
  }
  if (parsed.protocol !== "https:"
    || parsed.username
    || parsed.password
    || !parsed.hostname) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Salesforce org identity has an unsafe instance URL",
    );
  }
  return parsed.hostname.toLocaleLowerCase("en-US");
}

function validateOrgClassification(orgType, environment) {
  if (!ORG_TYPES.includes(orgType)
    || !ENVIRONMENTS.includes(environment)
    || !ENVIRONMENTS_BY_ORG_TYPE[orgType].includes(environment)) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Org type and environment classification are inconsistent",
    );
  }
}

function verificationInstant(now) {
  const instant = now instanceof Date ? new Date(now.getTime()) : new Date(now);
  if (!Number.isFinite(instant.getTime())) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Registry verification time is invalid",
    );
  }
  return instant;
}

export function orgIdentityFingerprint(identity) {
  if (!identity || typeof identity !== "object" || Array.isArray(identity)
    || typeof identity.org_id !== "string"
    || identity.org_id.length !== 18
    || !/^00D[A-Za-z0-9]{15}$/u.test(identity.org_id)
    || typeof identity.username !== "string"
    || identity.username.length < 1
    || identity.username.length > 255
    || sanitizeText(identity.username) !== identity.username) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Salesforce org identity is incomplete or unsafe",
    );
  }
  const host = identityHost(identity.instance_url);
  return {
    fingerprint: digest({
      org_id: identity.org_id,
      username: identity.username,
      instance_host: host,
    }),
    org_id_suffix: identity.org_id.slice(-6),
    instance_host: host,
  };
}

function validateApprovals(approvals, certificationState, environment) {
  assertExactKeys(
    approvals,
    [
      "sandbox_evidence_digest",
      "administrator_reference",
      "administrator_approved_at",
      "risk_owner_reference",
      "risk_owner_approved_at",
    ],
    [
      "sandbox_evidence_digest",
      "administrator_reference",
      "administrator_approved_at",
      "risk_owner_reference",
      "risk_owner_approved_at",
    ],
    "org_registry.entries[].approvals",
  );
  const productionApprovalValues = [
    approvals.administrator_reference,
    approvals.administrator_approved_at,
    approvals.risk_owner_reference,
    approvals.risk_owner_approved_at,
  ];
  const productionApprovalsNull = productionApprovalValues.every(
    (value) => value === null,
  );
  if (certificationState === "offline_validated") {
    if (approvals.sandbox_evidence_digest !== null
      || !productionApprovalsNull) {
      throw new SafetyError(
        "INVALID_ORG_REGISTRY",
        "Offline-only entries cannot contain certification or production approval metadata",
      );
    }
    return;
  }
  if (certificationState === "sandbox_read_certified") {
    if (environment !== "sandbox"
      || !/^[a-f0-9]{64}$/u.test(approvals.sandbox_evidence_digest)
      || !productionApprovalsNull) {
      throw new SafetyError(
        "INVALID_ORG_REGISTRY",
        "Sandbox certification requires one redacted evidence digest and no production approval metadata",
      );
    }
    return;
  }
  if (environment !== "production"
    || !/^[a-f0-9]{64}$/u.test(approvals.sandbox_evidence_digest)
    || approvals.administrator_reference === null
    || approvals.risk_owner_reference === null) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Production approval requires separate sandbox, administrator, and risk-owner evidence",
    );
  }
  safeText(
    approvals.administrator_reference,
    "approvals.administrator_reference",
    200,
  );
  safeText(
    approvals.risk_owner_reference,
    "approvals.risk_owner_reference",
    200,
  );
  canonicalInstant(
    approvals.administrator_approved_at,
    "approvals.administrator_approved_at",
  );
  canonicalInstant(
    approvals.risk_owner_approved_at,
    "approvals.risk_owner_approved_at",
  );
}

export function validateRegistryEntry(entry) {
  assertExactKeys(
    entry,
    [
      "alias",
      "friendly_label",
      "org_fingerprint",
      "org_id_suffix",
      "instance_host",
      "org_type",
      "environment",
      "field_map_version",
      "certification_state",
      "enrolled_at",
      "identity_verified_at",
      "metadata_verified_at",
      "certification_verified_at",
      "approvals",
      "certification_evidence",
      "approval_assertion_ledger",
    ],
    [
      "alias",
      "friendly_label",
      "org_fingerprint",
      "org_id_suffix",
      "instance_host",
      "org_type",
      "environment",
      "field_map_version",
      "certification_state",
      "enrolled_at",
      "identity_verified_at",
      "metadata_verified_at",
      "certification_verified_at",
      "approvals",
      "certification_evidence",
      "approval_assertion_ledger",
    ],
    "org_registry.entries[]",
  );
  validateAlias(entry.alias);
  safeText(entry.friendly_label, "friendly_label", 80);
  if (!/^[a-f0-9]{64}$/u.test(entry.org_fingerprint)
    || !/^[A-Za-z0-9]{6}$/u.test(entry.org_id_suffix)
    || typeof entry.instance_host !== "string"
    || entry.instance_host !== entry.instance_host.toLocaleLowerCase("en-US")
    || !/^[a-z0-9.-]+$/u.test(entry.instance_host)
    || entry.field_map_version !== FIELD_MAP_VERSION
    || !CERTIFICATION_STATES.includes(entry.certification_state)) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Org registry entry metadata is invalid",
    );
  }
  validateOrgClassification(entry.org_type, entry.environment);
  canonicalInstant(entry.enrolled_at, "enrolled_at");
  canonicalInstant(entry.identity_verified_at, "identity_verified_at");
  canonicalInstant(entry.metadata_verified_at, "metadata_verified_at", {
    nullable: true,
  });
  canonicalInstant(
    entry.certification_verified_at,
    "certification_verified_at",
    { nullable: true },
  );
  if (entry.certification_state === "offline_validated") {
    if (entry.certification_verified_at !== null
      || entry.certification_evidence !== null) {
      throw new SafetyError(
        "INVALID_ORG_REGISTRY",
        "Offline-only entries cannot claim operational certification evidence",
      );
    }
  } else if (entry.certification_verified_at === null
    || entry.metadata_verified_at === null
    || entry.certification_evidence === null) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Operational certification requires metadata and certification verification dates",
    );
  }
  if (entry.certification_state === "sandbox_read_certified"
    && entry.environment !== "sandbox") {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Sandbox certification can authorize only an enrolled sandbox org",
    );
  }
  if (entry.certification_state === "production_read_approved"
    && entry.environment !== "production") {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Production approval can authorize only an enrolled production org",
    );
  }
  validateApprovals(
    entry.approvals,
    entry.certification_state,
    entry.environment,
  );
  validateApprovalAssertionLedger(entry.approval_assertion_ledger);
  if (entry.certification_evidence !== null) {
    const evidence = validateCertificationEvidence(
      entry.certification_evidence,
    );
    if (entry.certification_state === "sandbox_read_certified") {
      validateSandboxCertificationEvidence(evidence);
      if (evidence.org_fingerprint !== entry.org_fingerprint
        || evidence.receipt_digest
          !== entry.approvals.sandbox_evidence_digest
        || evidence.completed_at !== entry.certification_verified_at) {
        throw new SafetyError(
          "INVALID_ORG_REGISTRY",
          "Sandbox certification evidence does not bind this registry entry",
        );
      }
    } else if (entry.certification_state === "production_read_approved") {
      validateProductionApprovalEvidence(evidence);
      if (evidence.production_org_fingerprint
          !== entry.org_fingerprint
        || evidence.sandbox_evidence_digest
          !== entry.approvals.sandbox_evidence_digest
        || evidence.administrator_approval.reference
          !== entry.approvals.administrator_reference
        || evidence.administrator_approval.issued_at
          !== entry.approvals.administrator_approved_at
        || evidence.risk_owner_approval.reference
          !== entry.approvals.risk_owner_reference
        || evidence.risk_owner_approval.issued_at
          !== entry.approvals.risk_owner_approved_at
        || evidence.completed_at !== entry.certification_verified_at) {
        throw new SafetyError(
          "INVALID_ORG_REGISTRY",
          "Production approval evidence does not bind this registry entry",
        );
      }
    }
  }
  return entry;
}

export function emptyOrgRegistry() {
  return {
    schema_version: CONTRACTS.orgRegistry,
    classification: CLASSIFICATION,
    entries: [],
  };
}

export function validateOrgRegistry(registry) {
  assertExactKeys(
    registry,
    ["schema_version", "classification", "entries"],
    ["schema_version", "classification", "entries"],
    "org_registry",
  );
  if (![
    CONTRACTS.orgRegistry,
    CONTRACTS.orgRegistryUnsigned,
    CONTRACTS.orgRegistryLegacy,
  ]
    .includes(registry.schema_version)
    || registry.classification !== CLASSIFICATION
    || !Array.isArray(registry.entries)
    || registry.entries.length > 200) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Org registry metadata or entry count is invalid",
    );
  }
  if (registry.schema_version !== CONTRACTS.orgRegistry) {
    registry = {
      schema_version: CONTRACTS.orgRegistry,
      classification: CLASSIFICATION,
      entries: registry.entries.map((entry) => ({
        ...entry,
        certification_state: "offline_validated",
        certification_verified_at: null,
        approvals: {
          sandbox_evidence_digest: null,
          administrator_reference: null,
          administrator_approved_at: null,
          risk_owner_reference: null,
          risk_owner_approved_at: null,
        },
        certification_evidence: null,
        approval_assertion_ledger: [],
      })),
    };
  }
  if (registry.entries.some((entry) =>
    !Object.hasOwn(entry, "approval_assertion_ledger"))) {
    registry = {
      ...registry,
      entries: registry.entries.map((entry) => ({
        ...entry,
        approval_assertion_ledger:
          entry.approval_assertion_ledger ?? [],
      })),
    };
  }
  registry.entries.forEach(validateRegistryEntry);
  const aliases = registry.entries.map((entry) =>
    entry.alias.toLocaleLowerCase("en-US"));
  const labels = registry.entries.map((entry) =>
    entry.friendly_label.toLocaleLowerCase("en-US"));
  if (new Set(aliases).size !== aliases.length
    || new Set(labels).size !== labels.length) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Org aliases and friendly labels must be unique",
    );
  }
  const assertionDigests = registry.entries.flatMap((entry) =>
    entry.approval_assertion_ledger.map((item) =>
      item.assertion_digest));
  const replayKeyDigests = registry.entries.flatMap((entry) =>
    entry.approval_assertion_ledger.map((item) =>
      item.replay_key_digest));
  if (new Set(assertionDigests).size !== assertionDigests.length
    || new Set(replayKeyDigests).size !== replayKeyDigests.length) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Approval assertions cannot be consumed by more than one org",
    );
  }
  const sorted = [...registry.entries].sort((left, right) =>
    left.alias.localeCompare(right.alias, "en-US"));
  if (sorted.some((entry, index) => entry.alias !== registry.entries[index].alias)) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Org registry entries must use canonical alias order",
    );
  }
  return registry;
}

export function buildOfflineRegistryEntry({
  alias,
  friendlyLabel,
  identity,
  orgType,
  environment,
  now = new Date(),
}) {
  validateAlias(alias);
  safeText(friendlyLabel, "friendly_label", 80);
  const instant = (now instanceof Date ? now : new Date(now)).toISOString();
  const org = orgIdentityFingerprint(identity);
  return validateRegistryEntry({
    alias,
    friendly_label: friendlyLabel,
    org_fingerprint: org.fingerprint,
    org_id_suffix: org.org_id_suffix,
    instance_host: org.instance_host,
    org_type: orgType,
    environment,
    field_map_version: FIELD_MAP_VERSION,
    certification_state: "offline_validated",
    enrolled_at: instant,
    identity_verified_at: instant,
    metadata_verified_at: null,
    certification_verified_at: null,
    approvals: {
      sandbox_evidence_digest: null,
      administrator_reference: null,
      administrator_approved_at: null,
      risk_owner_reference: null,
      risk_owner_approved_at: null,
    },
    certification_evidence: null,
    approval_assertion_ledger: [],
  });
}

export function markMetadataVerified(entry, now = new Date()) {
  validateRegistryEntry(entry);
  const instant = verificationInstant(now);
  return validateRegistryEntry({
    ...entry,
    metadata_verified_at: instant.toISOString(),
  });
}

export function downgradeRegistryEntry(entry) {
  validateRegistryEntry(entry);
  return validateRegistryEntry({
    ...entry,
    certification_state: "offline_validated",
    certification_verified_at: null,
    approvals: {
      sandbox_evidence_digest: null,
      administrator_reference: null,
      administrator_approved_at: null,
      risk_owner_reference: null,
      risk_owner_approved_at: null,
    },
    certification_evidence: null,
  });
}

export function downgradeRegistryReadiness(registry, originalEntry) {
  let updated = validateOrgRegistry(registry);
  validateRegistryEntry(originalEntry);
  const latest = updated.entries.find((entry) =>
    entry.alias === originalEntry.alias);
  const sandboxEvidenceDigest =
    originalEntry.environment === "sandbox"
    && originalEntry.certification_state === "sandbox_read_certified"
      ? originalEntry.certification_evidence?.receipt_digest ?? null
      : null;

  if (sandboxEvidenceDigest !== null) {
    if (latest?.certification_state === "sandbox_read_certified"
      && latest.certification_evidence?.receipt_digest
        === sandboxEvidenceDigest) {
      updated = upsertRegistryEntry(
        updated,
        downgradeRegistryEntry(latest),
      );
    }
    for (const entry of [...updated.entries]) {
      if (entry.certification_state === "production_read_approved"
        && entry.certification_evidence?.sandbox_evidence_digest
          === sandboxEvidenceDigest) {
        updated = upsertRegistryEntry(
          updated,
          downgradeRegistryEntry(entry),
        );
      }
    }
    return updated;
  }

  if (latest
    && latest.certification_state !== "offline_validated"
    && digest(latest) === digest(originalEntry)) {
    return upsertRegistryEntry(
      updated,
      downgradeRegistryEntry(latest),
    );
  }
  return updated;
}

function ledgerEntryFor(verification, acceptedAt) {
  const assertion = verification?.assertion;
  if (!assertion
    || !/^[a-f0-9]{64}$/u.test(
      verification.assertion_digest ?? "",
    )
    || !/^[a-f0-9]{64}$/u.test(
      verification.replay_key_digest ?? "",
    )
    || !APPROVAL_ROLES.has(assertion.role)
    || !/^[a-f0-9]{64}$/u.test(assertion.scope_digest ?? "")) {
    throw new SafetyError(
      "INVALID_APPROVAL_ASSERTION",
      "Verified approval assertion metadata is incomplete",
    );
  }
  const expiresAt = canonicalInstant(
    assertion.expires_at,
    "approval_assertion.expires_at",
  );
  if (new Date(expiresAt) <= acceptedAt) {
    throw new SafetyError(
      "APPROVAL_ASSERTION_EXPIRED",
      "Approval assertion expired before replay reservation",
    );
  }
  return {
    assertion_digest: verification.assertion_digest,
    replay_key_digest: verification.replay_key_digest,
    role: assertion.role,
    scope_digest: assertion.scope_digest,
    accepted_at: acceptedAt.toISOString(),
    expires_at: expiresAt,
  };
}

export function assertApprovalAssertionsUnused(
  registry,
  verifications,
) {
  const validated = validateOrgRegistry(registry);
  if (!Array.isArray(verifications) || verifications.length < 1) {
    throw new SafetyError(
      "INVALID_APPROVAL_ASSERTION",
      "At least one verified approval assertion is required",
    );
  }
  const assertionDigests = verifications.map((verification) =>
    verification?.assertion_digest);
  const replayKeyDigests = verifications.map((verification) =>
    verification?.replay_key_digest);
  if (assertionDigests.some((value) =>
    !/^[a-f0-9]{64}$/u.test(value ?? ""))
    || replayKeyDigests.some((value) =>
      !/^[a-f0-9]{64}$/u.test(value ?? ""))
    || new Set(assertionDigests).size !== assertionDigests.length
    || new Set(replayKeyDigests).size !== replayKeyDigests.length) {
    throw new SafetyError(
      "INVALID_APPROVAL_ASSERTION",
      "Approval assertions must be complete and distinct",
    );
  }
  const consumedAssertions = new Set(
    validated.entries.flatMap((entry) =>
      entry.approval_assertion_ledger.map((item) =>
        item.assertion_digest)),
  );
  const consumedReplayKeys = new Set(
    validated.entries.flatMap((entry) =>
      entry.approval_assertion_ledger.map((item) =>
        item.replay_key_digest)),
  );
  if (assertionDigests.some((value) => consumedAssertions.has(value))
    || replayKeyDigests.some((value) => consumedReplayKeys.has(value))) {
    throw new SafetyError(
      "APPROVAL_ASSERTION_REPLAYED",
      "A signed approval assertion was already consumed",
    );
  }
  return validated;
}

export function appendApprovalAssertions(entry, {
  verifications,
  now = new Date(),
} = {}) {
  validateRegistryEntry(entry);
  if (!Array.isArray(verifications) || verifications.length < 1) {
    throw new SafetyError(
      "INVALID_APPROVAL_ASSERTION",
      "At least one verified approval assertion is required",
    );
  }
  const instant = verificationInstant(now);
  const additions = verifications.map((verification) =>
    ledgerEntryFor(verification, instant));
  const retained = entry.approval_assertion_ledger.filter((item) =>
    new Date(item.expires_at) > instant);
  const ledger = [...retained, ...additions].sort((left, right) =>
    left.accepted_at.localeCompare(right.accepted_at, "en-US")
    || left.assertion_digest.localeCompare(
      right.assertion_digest,
      "en-US",
    ));
  validateApprovalAssertionLedger(ledger);
  return validateRegistryEntry({
    ...entry,
    approval_assertion_ledger: ledger,
  });
}

export function markSandboxReadCertified(entry, {
  evidence,
  now = new Date(),
} = {}) {
  validateRegistryEntry(entry);
  validateSandboxCertificationEvidence(evidence);
  if (entry.environment !== "sandbox"
    || entry.org_type !== "sandbox"
    || evidence.org_fingerprint !== entry.org_fingerprint) {
    throw new SafetyError(
      "SANDBOX_CERTIFICATION_INVALID",
      "Sandbox certification evidence does not bind the enrolled sandbox",
    );
  }
  if (entry.metadata_verified_at === null) {
    throw new SafetyError(
      "SANDBOX_CERTIFICATION_INVALID",
      "Sandbox certification requires current compatible metadata",
    );
  }
  const instant = verificationInstant(now);
  if (evidence.completed_at !== instant.toISOString()) {
    throw new SafetyError(
      "SANDBOX_CERTIFICATION_INVALID",
      "Sandbox certification evidence does not bind the transition time",
    );
  }
  const latestPriorVerification = Math.max(
    new Date(entry.identity_verified_at).getTime(),
    new Date(entry.metadata_verified_at).getTime(),
    entry.certification_verified_at === null
      ? Number.NEGATIVE_INFINITY
      : new Date(entry.certification_verified_at).getTime(),
  );
  if (instant.getTime() < latestPriorVerification) {
    throw new SafetyError(
      "ORG_VERIFICATION_TIME_REGRESSION",
      "Sandbox certification time cannot move backwards",
    );
  }
  return validateRegistryEntry({
    ...entry,
    certification_state: "sandbox_read_certified",
    certification_verified_at: instant.toISOString(),
    approvals: {
      sandbox_evidence_digest: evidence.receipt_digest,
      administrator_reference: null,
      administrator_approved_at: null,
      risk_owner_reference: null,
      risk_owner_approved_at: null,
    },
    certification_evidence: evidence,
  });
}

export function markProductionReadApproved(entry, {
  evidence,
  now = new Date(),
} = {}) {
  validateRegistryEntry(entry);
  validateProductionApprovalEvidence(evidence);
  if (entry.environment !== "production"
    || evidence.production_org_fingerprint !== entry.org_fingerprint
    || entry.metadata_verified_at === null) {
    throw new SafetyError(
      "PRODUCTION_APPROVAL_INVALID",
      "Production approval requires current production metadata and certified sandbox evidence",
    );
  }
  const instant = verificationInstant(now);
  if (evidence.completed_at !== instant.toISOString()) {
    throw new SafetyError(
      "PRODUCTION_APPROVAL_INVALID",
      "Production approval evidence does not bind the transition time",
    );
  }
  const administratorInstant = new Date(
    evidence.administrator_approval.issued_at,
  );
  const riskOwnerInstant = new Date(
    evidence.risk_owner_approval.issued_at,
  );
  if (!Number.isFinite(administratorInstant.getTime())
    || administratorInstant.toISOString()
      !== evidence.administrator_approval.issued_at
    || !Number.isFinite(riskOwnerInstant.getTime())
    || riskOwnerInstant.toISOString()
      !== evidence.risk_owner_approval.issued_at
    || administratorInstant > instant
    || riskOwnerInstant > instant) {
    throw new SafetyError(
      "PRODUCTION_APPROVAL_INVALID",
      "Production approval timestamps must be canonical and no later than the approval operation",
    );
  }
  const latestPriorVerification = Math.max(
    new Date(entry.identity_verified_at).getTime(),
    new Date(entry.metadata_verified_at).getTime(),
    administratorInstant.getTime(),
    riskOwnerInstant.getTime(),
    entry.certification_verified_at === null
      ? Number.NEGATIVE_INFINITY
      : new Date(entry.certification_verified_at).getTime(),
  );
  if (instant.getTime() < latestPriorVerification) {
    throw new SafetyError(
      "ORG_VERIFICATION_TIME_REGRESSION",
      "Production approval time cannot move backwards",
    );
  }
  return validateRegistryEntry({
    ...entry,
    certification_state: "production_read_approved",
    certification_verified_at: instant.toISOString(),
    approvals: {
      sandbox_evidence_digest: evidence.sandbox_evidence_digest,
      administrator_reference:
        evidence.administrator_approval.reference,
      administrator_approved_at:
        evidence.administrator_approval.issued_at,
      risk_owner_reference: evidence.risk_owner_approval.reference,
      risk_owner_approved_at:
        evidence.risk_owner_approval.issued_at,
    },
    certification_evidence: evidence,
  });
}

export function refreshRegistryVerification(entry, {
  identity,
  orgType,
  environment,
  fieldMapVersion = FIELD_MAP_VERSION,
  runtimeAttestationDigest = null,
  packageDigest = null,
  metadataCompatibilityDigest = null,
  now = new Date(),
} = {}) {
  validateRegistryEntry(entry);
  verifyRegistryIdentity(entry, identity);
  validateOrgClassification(orgType, environment);
  if (orgType !== entry.org_type || environment !== entry.environment) {
    throw new SafetyError(
      "ORG_CLASSIFICATION_MISMATCH",
      "Current org type or environment does not match the enrolled org",
    );
  }
  if (fieldMapVersion !== entry.field_map_version
    || fieldMapVersion !== FIELD_MAP_VERSION) {
    throw new SafetyError(
      "ORG_METADATA_MISMATCH",
      "Current field-map metadata does not match the enrolled org",
    );
  }
  const instant = verificationInstant(now);
  const latestPriorVerification = Math.max(
    new Date(entry.identity_verified_at).getTime(),
    entry.metadata_verified_at === null
      ? Number.NEGATIVE_INFINITY
      : new Date(entry.metadata_verified_at).getTime(),
  );
  if (instant.getTime() < latestPriorVerification) {
    throw new SafetyError(
      "ORG_VERIFICATION_TIME_REGRESSION",
      "Registry verification time cannot move backwards",
    );
  }
  const refreshed = validateRegistryEntry({
    ...entry,
    identity_verified_at: instant.toISOString(),
    metadata_verified_at: instant.toISOString(),
  });
  if (refreshed.certification_state === "offline_validated") {
    return refreshed;
  }
  const evidence = refreshed.certification_evidence;
  if (!/^[a-f0-9]{64}$/u.test(runtimeAttestationDigest ?? "")
    || !/^[a-f0-9]{64}$/u.test(packageDigest ?? "")
    || !/^[a-f0-9]{64}$/u.test(metadataCompatibilityDigest ?? "")
    || evidence.runtime_attestation_digest !== runtimeAttestationDigest
    || evidence.package_digest !== packageDigest
    || evidence.metadata_compatibility_digest
      !== metadataCompatibilityDigest) {
    return downgradeRegistryEntry(refreshed);
  }
  return refreshed;
}

export function upsertRegistryEntry(registry, entry) {
  const validatedRegistry = validateOrgRegistry(registry);
  validateRegistryEntry(entry);
  const entries = validatedRegistry.entries
    .filter((candidate) => candidate.alias !== entry.alias)
    .concat([{ ...entry }])
    .sort((left, right) => left.alias.localeCompare(right.alias, "en-US"));
  return validateOrgRegistry({
    schema_version: CONTRACTS.orgRegistry,
    classification: CLASSIFICATION,
    entries,
  });
}

export function resolveRegistryEntry(registry, aliasOrLabel) {
  const validatedRegistry = validateOrgRegistry(registry);
  const key = safeText(aliasOrLabel, "org selector", 80)
    .toLocaleLowerCase("en-US");
  const matches = validatedRegistry.entries.filter((entry) =>
    entry.alias.toLocaleLowerCase("en-US") === key
    || entry.friendly_label.toLocaleLowerCase("en-US") === key);
  if (matches.length !== 1) {
    throw new SafetyError(
      matches.length ? "AMBIGUOUS_ORG" : "ORG_NOT_ENROLLED",
      matches.length
        ? "Org selector matches more than one enrolled org"
        : "Run doctor to enroll the requested org",
    );
  }
  return matches[0];
}

export function verifyRegistryIdentity(entry, identity) {
  validateRegistryEntry(entry);
  const current = orgIdentityFingerprint(identity);
  if (current.fingerprint !== entry.org_fingerprint
    || current.org_id_suffix !== entry.org_id_suffix
    || current.instance_host !== entry.instance_host) {
    throw new SafetyError(
      "ORG_IDENTITY_MISMATCH",
      "Current Salesforce identity does not match the enrolled org",
    );
  }
  return entry;
}

export function assertRegistryReadiness(entry, {
  allowOfflineExecution = false,
} = {}) {
  validateRegistryEntry(entry);
  if (allowOfflineExecution && entry.certification_state === "offline_validated") {
    return entry;
  }
  if (entry.environment === "production") {
    if (entry.certification_state !== "production_read_approved") {
      throw new SafetyError(
        "PRODUCTION_NOT_APPROVED",
        "Production reads require separate administrator and risk-owner approval",
      );
    }
    return entry;
  }
  if (entry.environment !== "sandbox"
    || entry.certification_state !== "sandbox_read_certified") {
    throw new SafetyError(
      "SANDBOX_NOT_CERTIFIED",
      "Nonproduction reads require an explicitly certified sandbox org",
    );
  }
  return entry;
}

export function registryReadinessDigest(entry) {
  validateRegistryEntry(entry);
  return digest({
    org_fingerprint: entry.org_fingerprint,
    field_map_version: entry.field_map_version,
    certification_state: entry.certification_state,
    certification_evidence_digest:
      entry.certification_evidence?.receipt_digest ?? null,
  });
}

export const orgRegistryInternals = Object.freeze({
  ENVIRONMENTS,
  ORG_TYPES,
  ENVIRONMENTS_BY_ORG_TYPE,
});

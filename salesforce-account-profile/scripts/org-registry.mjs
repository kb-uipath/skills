import {
  CERTIFICATION_STATES,
  CLASSIFICATION,
  CONTRACTS,
  FIELD_MAP_VERSION,
} from "./constants.mjs";
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
  const values = Object.values(approvals);
  const allNull = values.every((value) => value === null);
  if (certificationState !== "production_read_approved") {
    if (!allNull) {
      throw new SafetyError(
        "INVALID_ORG_REGISTRY",
        "Only production-approved entries may contain production approval metadata",
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
    if (entry.certification_verified_at !== null) {
      throw new SafetyError(
        "INVALID_ORG_REGISTRY",
        "Offline-only entries cannot claim an operational certification date",
      );
    }
  } else if (entry.certification_verified_at === null
    || entry.metadata_verified_at === null) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Operational certification requires metadata and certification verification dates",
    );
  }
  if (entry.certification_state === "sandbox_read_certified"
    && entry.environment === "production") {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Sandbox certification cannot authorize a production org",
    );
  }
  validateApprovals(
    entry.approvals,
    entry.certification_state,
    entry.environment,
  );
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
  if (registry.schema_version !== CONTRACTS.orgRegistry
    || registry.classification !== CLASSIFICATION
    || !Array.isArray(registry.entries)
    || registry.entries.length > 200) {
    throw new SafetyError(
      "INVALID_ORG_REGISTRY",
      "Org registry metadata or entry count is invalid",
    );
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

export function refreshRegistryVerification(entry, {
  identity,
  orgType,
  environment,
  fieldMapVersion = FIELD_MAP_VERSION,
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
  return validateRegistryEntry({
    ...entry,
    identity_verified_at: instant.toISOString(),
    metadata_verified_at: instant.toISOString(),
  });
}

export function upsertRegistryEntry(registry, entry) {
  validateOrgRegistry(registry);
  validateRegistryEntry(entry);
  const entries = registry.entries
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
  validateOrgRegistry(registry);
  const key = safeText(aliasOrLabel, "org selector", 80)
    .toLocaleLowerCase("en-US");
  const matches = registry.entries.filter((entry) =>
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
  if (entry.certification_state !== "sandbox_read_certified") {
    throw new SafetyError(
      "SANDBOX_NOT_CERTIFIED",
      "Nonproduction reads require sandbox read certification",
    );
  }
  return entry;
}

export const orgRegistryInternals = Object.freeze({
  ENVIRONMENTS,
  ORG_TYPES,
  ENVIRONMENTS_BY_ORG_TYPE,
});

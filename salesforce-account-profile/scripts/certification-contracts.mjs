import {
  CAPS,
  CERTIFICATION_APPROVAL_ROLES,
  CONTRACTS,
  FIELD_MAP_VERSION,
  SANDBOX_SUITE_VERSION,
} from "./constants.mjs";
import {
  validateApprovalAssertionShape,
} from "./approval-trust.mjs";
import {
  assertExactKeys,
  digest,
  SafetyError,
  sanitizeText,
  validateAlias,
} from "./security.mjs";

const ACCOUNT_ID_18 = /^001[A-Za-z0-9]{15}$/u;
const CURRENCY_CODE = /^[A-Z]{3}$/u;
const SHA256 = /^[a-f0-9]{64}$/u;
const SYNTHETIC_MARKER = /^[A-Za-z0-9][A-Za-z0-9_-]{7,63}$/u;

function safeText(value, label, maximum) {
  if (typeof value !== "string"
    || value.length < 1
    || value.length > maximum
    || sanitizeText(value) !== value) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      `${label} must be safe text between 1 and ${maximum} characters`,
    );
  }
  return value;
}

function sha256(value, label) {
  if (typeof value !== "string" || !SHA256.test(value)) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      `${label} must be a SHA-256 digest`,
    );
  }
  return value;
}

function canonicalInstant(value, label) {
  if (typeof value !== "string") {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      `${label} must be a canonical ISO timestamp`,
    );
  }
  const instant = new Date(value);
  if (!Number.isFinite(instant.getTime()) || instant.toISOString() !== value) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      `${label} must be a canonical ISO timestamp`,
    );
  }
  return instant;
}

function withoutDigest(value, key) {
  return Object.fromEntries(
    Object.entries(value).filter(([field]) => field !== key),
  );
}

function verifyDigest(value, key, code = "INVALID_CERTIFICATION_REQUEST") {
  sha256(value[key], key);
  if (digest(withoutDigest(value, key)) !== value[key]) {
    throw new SafetyError(
      code,
      `${key} does not match the canonical payload`,
    );
  }
}

function canonicalAccountIds(values, {
  label,
  minimum,
  maximum,
} = {}) {
  if (!Array.isArray(values)
    || values.length < minimum
    || values.length > maximum
    || values.some((value) =>
      typeof value !== "string" || !ACCOUNT_ID_18.test(value))
    || new Set(values).size !== values.length) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      `${label} must contain ${minimum}-${maximum} unique 18-character Account IDs`,
    );
  }
  const sorted = [...values].sort();
  if (sorted.some((value, index) => value !== values[index])) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      `${label} must use canonical Account-ID order`,
    );
  }
  return sorted;
}

function validateNamedAccount(value, label, marker) {
  assertExactKeys(
    value,
    ["id", "exact_name"],
    ["id", "exact_name"],
    label,
  );
  if (typeof value.id !== "string" || !ACCOUNT_ID_18.test(value.id)) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      `${label}.id must be an 18-character Account ID`,
    );
  }
  const exactName = safeText(value.exact_name, `${label}.exact_name`, 255);
  if (!exactName.includes(marker)) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      `${label}.exact_name must contain the synthetic fixture marker`,
    );
  }
  return { id: value.id, exact_name: exactName };
}

function validateAmbiguousAccount(value, marker) {
  assertExactKeys(
    value,
    ["exact_name", "account_ids"],
    ["exact_name", "account_ids"],
    "fixture_manifest.ambiguous_account",
  );
  const exactName = safeText(
    value.exact_name,
    "fixture_manifest.ambiguous_account.exact_name",
    255,
  );
  if (!exactName.includes(marker)) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      "ambiguous_account.exact_name must contain the synthetic fixture marker",
    );
  }
  return {
    exact_name: exactName,
    account_ids: canonicalAccountIds(value.account_ids, {
      label: "fixture_manifest.ambiguous_account.account_ids",
      minimum: 2,
      maximum: CAPS.candidates,
    }),
  };
}

function validatePrefixAccount(value, marker) {
  assertExactKeys(
    value,
    ["literal_prefix", "account_ids"],
    ["literal_prefix", "account_ids"],
    "fixture_manifest.prefix_account",
  );
  const literalPrefix = safeText(
    value.literal_prefix,
    "fixture_manifest.prefix_account.literal_prefix",
    255,
  );
  if (!literalPrefix.includes(marker)) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      "prefix_account.literal_prefix must contain the synthetic fixture marker",
    );
  }
  return {
    literal_prefix: literalPrefix,
    account_ids: canonicalAccountIds(value.account_ids, {
      label: "fixture_manifest.prefix_account.account_ids",
      minimum: 1,
      maximum: CAPS.candidates,
    }),
  };
}

function validateFamily(value) {
  assertExactKeys(
    value,
    ["seed_account_id", "account_ids", "expected_currencies"],
    ["seed_account_id", "account_ids", "expected_currencies"],
    "fixture_manifest.family",
  );
  if (typeof value.seed_account_id !== "string"
    || !ACCOUNT_ID_18.test(value.seed_account_id)) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      "family.seed_account_id must be an 18-character Account ID",
    );
  }
  const accountIds = canonicalAccountIds(value.account_ids, {
    label: "fixture_manifest.family.account_ids",
    minimum: 1,
    maximum: CAPS.familyAccounts,
  });
  if (!accountIds.includes(value.seed_account_id)) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      "family.account_ids must include the seed Account",
    );
  }
  if (!Array.isArray(value.expected_currencies)
    || value.expected_currencies.length < 2
    || value.expected_currencies.length > 20
    || value.expected_currencies.some((code) =>
      typeof code !== "string" || !CURRENCY_CODE.test(code))
    || new Set(value.expected_currencies).size !== value.expected_currencies.length) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      "family.expected_currencies must contain 2-20 unique currency codes",
    );
  }
  const currencies = [...value.expected_currencies].sort();
  if (currencies.some((code, index) =>
    code !== value.expected_currencies[index])) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      "family.expected_currencies must use canonical order",
    );
  }
  return {
    seed_account_id: value.seed_account_id,
    account_ids: accountIds,
    expected_currencies: currencies,
  };
}

export function validateFixtureManifest(manifest) {
  assertExactKeys(
    manifest,
    [
      "schema_version",
      "fixture_set_id",
      "org_fingerprint",
      "field_map_version",
      "suite_version",
      "created_at",
      "expires_at",
      "synthetic_marker",
      "unique_account",
      "ambiguous_account",
      "no_match_name",
      "prefix_account",
      "family",
      "manifest_digest",
    ],
    [
      "schema_version",
      "fixture_set_id",
      "org_fingerprint",
      "field_map_version",
      "suite_version",
      "created_at",
      "expires_at",
      "synthetic_marker",
      "unique_account",
      "ambiguous_account",
      "no_match_name",
      "prefix_account",
      "family",
      "manifest_digest",
    ],
    "fixture_manifest",
  );
  if (manifest.schema_version !== CONTRACTS.sandboxFixtureManifest
    || manifest.field_map_version !== FIELD_MAP_VERSION
    || manifest.suite_version !== SANDBOX_SUITE_VERSION) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      "Fixture manifest version metadata is invalid",
    );
  }
  safeText(manifest.fixture_set_id, "fixture_set_id", 80);
  sha256(manifest.org_fingerprint, "org_fingerprint");
  const createdAt = canonicalInstant(manifest.created_at, "created_at");
  const expiresAt = canonicalInstant(manifest.expires_at, "expires_at");
  if (expiresAt <= createdAt) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      "Fixture manifest expiry must follow creation",
    );
  }
  if (typeof manifest.synthetic_marker !== "string"
    || !SYNTHETIC_MARKER.test(manifest.synthetic_marker)) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      "synthetic_marker must be an opaque 8-64 character fixture marker",
    );
  }
  validateNamedAccount(
    manifest.unique_account,
    "fixture_manifest.unique_account",
    manifest.synthetic_marker,
  );
  validateAmbiguousAccount(
    manifest.ambiguous_account,
    manifest.synthetic_marker,
  );
  const noMatchName = safeText(
    manifest.no_match_name,
    "fixture_manifest.no_match_name",
    255,
  );
  if (!noMatchName.includes(manifest.synthetic_marker)) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      "no_match_name must contain the synthetic fixture marker",
    );
  }
  validatePrefixAccount(
    manifest.prefix_account,
    manifest.synthetic_marker,
  );
  validateFamily(manifest.family);
  verifyDigest(manifest, "manifest_digest");
  return manifest;
}

function validateSandboxScope(scope) {
  assertExactKeys(
    scope,
    [
      "schema_version",
      "org_fingerprint",
      "runtime_attestation_digest",
      "package_digest",
      "field_map_version",
      "metadata_compatibility_digest",
      "suite_version",
      "fixture_manifest_digest",
      "issued_at",
      "expires_at",
      "scope_digest",
    ],
    [
      "schema_version",
      "org_fingerprint",
      "runtime_attestation_digest",
      "package_digest",
      "field_map_version",
      "metadata_compatibility_digest",
      "suite_version",
      "fixture_manifest_digest",
      "issued_at",
      "expires_at",
      "scope_digest",
    ],
    "sandbox_scope",
  );
  if (scope.schema_version !== CONTRACTS.sandboxCertificationScope
    || scope.field_map_version !== FIELD_MAP_VERSION
    || scope.suite_version !== SANDBOX_SUITE_VERSION) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      "Sandbox certification scope metadata is invalid",
    );
  }
  for (const key of [
    "org_fingerprint",
    "runtime_attestation_digest",
    "package_digest",
    "metadata_compatibility_digest",
    "fixture_manifest_digest",
  ]) sha256(scope[key], `sandbox_scope.${key}`);
  const issuedAt = canonicalInstant(scope.issued_at, "sandbox_scope.issued_at");
  const expiresAt = canonicalInstant(
    scope.expires_at,
    "sandbox_scope.expires_at",
  );
  if (expiresAt <= issuedAt) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      "Sandbox certification scope expiry must follow issuance",
    );
  }
  verifyDigest(scope, "scope_digest");
  return scope;
}

export function validateSandboxScopeRequest(input) {
  assertExactKeys(
    input,
    ["schema_version", "target_org", "fixture_manifest"],
    ["schema_version", "target_org", "fixture_manifest"],
    "sandbox_scope_request",
  );
  if (input.schema_version !== CONTRACTS.sandboxCertificationScopeRequest) {
    throw new SafetyError(
      "CONTRACT_VERSION_MISMATCH",
      `Expected schema_version ${CONTRACTS.sandboxCertificationScopeRequest}`,
    );
  }
  validateAlias(input.target_org);
  validateFixtureManifest(input.fixture_manifest);
  return input;
}

export function validateSandboxCertificationRequest(input) {
  assertExactKeys(
    input,
    [
      "schema_version",
      "target_org",
      "fixture_manifest",
      "approval_scope",
      "authorization",
    ],
    [
      "schema_version",
      "target_org",
      "fixture_manifest",
      "approval_scope",
      "authorization",
    ],
    "sandbox_certification",
  );
  if (input.schema_version !== CONTRACTS.sandboxCertificationRequest) {
    throw new SafetyError(
      "CONTRACT_VERSION_MISMATCH",
      `Expected schema_version ${CONTRACTS.sandboxCertificationRequest}`,
    );
  }
  validateAlias(input.target_org);
  validateFixtureManifest(input.fixture_manifest);
  validateSandboxScope(input.approval_scope);
  validateApprovalAssertionShape(input.authorization, {
    expectedRole: CERTIFICATION_APPROVAL_ROLES.sandbox,
  });
  return input;
}

function validateProductionScope(scope) {
  assertExactKeys(
    scope,
    [
      "schema_version",
      "production_org_fingerprint",
      "sandbox_org_fingerprint",
      "sandbox_evidence_digest",
      "runtime_attestation_digest",
      "package_digest",
      "field_map_version",
      "metadata_compatibility_digest",
      "issued_at",
      "expires_at",
      "scope_digest",
    ],
    [
      "schema_version",
      "production_org_fingerprint",
      "sandbox_org_fingerprint",
      "sandbox_evidence_digest",
      "runtime_attestation_digest",
      "package_digest",
      "field_map_version",
      "metadata_compatibility_digest",
      "issued_at",
      "expires_at",
      "scope_digest",
    ],
    "production_approval_scope",
  );
  if (scope.schema_version !== CONTRACTS.productionApprovalScope
    || scope.field_map_version !== FIELD_MAP_VERSION) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      "Production approval scope metadata is invalid",
    );
  }
  for (const key of [
    "production_org_fingerprint",
    "sandbox_org_fingerprint",
    "sandbox_evidence_digest",
    "runtime_attestation_digest",
    "package_digest",
    "metadata_compatibility_digest",
  ]) sha256(scope[key], `production_approval_scope.${key}`);
  if (scope.production_org_fingerprint === scope.sandbox_org_fingerprint) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      "Production and sandbox fingerprints must be distinct",
    );
  }
  const issuedAt = canonicalInstant(
    scope.issued_at,
    "production_approval_scope.issued_at",
  );
  const expiresAt = canonicalInstant(
    scope.expires_at,
    "production_approval_scope.expires_at",
  );
  if (expiresAt <= issuedAt) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      "Production approval scope expiry must follow issuance",
    );
  }
  verifyDigest(scope, "scope_digest");
  return scope;
}

export function validateProductionScopeRequest(input) {
  assertExactKeys(
    input,
    ["schema_version", "target_org", "sandbox_evidence_digest"],
    ["schema_version", "target_org", "sandbox_evidence_digest"],
    "production_scope_request",
  );
  if (input.schema_version !== CONTRACTS.productionApprovalScopeRequest) {
    throw new SafetyError(
      "CONTRACT_VERSION_MISMATCH",
      `Expected schema_version ${CONTRACTS.productionApprovalScopeRequest}`,
    );
  }
  validateAlias(input.target_org);
  sha256(input.sandbox_evidence_digest, "sandbox_evidence_digest");
  return input;
}

export function validateProductionApprovalRequest(input) {
  assertExactKeys(
    input,
    [
      "schema_version",
      "target_org",
      "sandbox_evidence_digest",
      "approval_scope",
      "administrator_approval",
      "risk_owner_approval",
    ],
    [
      "schema_version",
      "target_org",
      "sandbox_evidence_digest",
      "approval_scope",
      "administrator_approval",
      "risk_owner_approval",
    ],
    "production_approval",
  );
  if (input.schema_version !== CONTRACTS.productionApprovalRequest) {
    throw new SafetyError(
      "CONTRACT_VERSION_MISMATCH",
      `Expected schema_version ${CONTRACTS.productionApprovalRequest}`,
    );
  }
  validateAlias(input.target_org);
  sha256(input.sandbox_evidence_digest, "sandbox_evidence_digest");
  validateProductionScope(input.approval_scope);
  const administratorApproval = validateApprovalAssertionShape(
    input.administrator_approval,
    {
      expectedRole:
        CERTIFICATION_APPROVAL_ROLES.productionAdministrator,
    },
  );
  const riskOwnerApproval = validateApprovalAssertionShape(
    input.risk_owner_approval,
    {
      expectedRole: CERTIFICATION_APPROVAL_ROLES.productionRiskOwner,
    },
  );
  if (administratorApproval.reference === riskOwnerApproval.reference
    || administratorApproval.subject_digest
      === riskOwnerApproval.subject_digest
    || administratorApproval.issuer === riskOwnerApproval.issuer
      && administratorApproval.key_id === riskOwnerApproval.key_id
    || administratorApproval.nonce === riskOwnerApproval.nonce) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_REQUEST",
      "Administrator and risk-owner signed assertions must be distinct",
    );
  }
  return input;
}

export const certificationContractInternals = Object.freeze({
  ACCOUNT_ID_18,
  CURRENCY_CODE,
  SHA256,
  SYNTHETIC_MARKER,
  canonicalAccountIds,
  validateProductionScope,
  validateSandboxScope,
  verifyDigest,
});

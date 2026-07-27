import {
  CAPS,
  CONTRACTS,
  FIELD_MAP_VERSION,
  SANDBOX_SCENARIO_IDS,
  SANDBOX_SUITE_VERSION,
} from "./constants.mjs";
import {
  assertExactKeys,
  digest,
  SafetyError,
  sanitizeText,
} from "./security.mjs";

const SHA256 = /^[a-f0-9]{64}$/u;

function sha256(value, label) {
  if (typeof value !== "string" || !SHA256.test(value)) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_EVIDENCE",
      `${label} must be a SHA-256 digest`,
    );
  }
  return value;
}

function canonicalInstant(value, label) {
  if (typeof value !== "string") {
    throw new SafetyError(
      "INVALID_CERTIFICATION_EVIDENCE",
      `${label} must be a canonical ISO timestamp`,
    );
  }
  const instant = new Date(value);
  if (!Number.isFinite(instant.getTime()) || instant.toISOString() !== value) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_EVIDENCE",
      `${label} must be a canonical ISO timestamp`,
    );
  }
  return instant;
}

function safeReference(value, label) {
  if (typeof value !== "string"
    || value.length < 1
    || value.length > 200
    || sanitizeText(value) !== value) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_EVIDENCE",
      `${label} must be safe opaque text`,
    );
  }
  return value;
}

function receiptCore(receipt) {
  return Object.fromEntries(
    Object.entries(receipt).filter(([key]) => key !== "receipt_digest"),
  );
}

function validateReceiptDigest(receipt) {
  sha256(receipt.receipt_digest, "receipt_digest");
  if (digest(receiptCore(receipt)) !== receipt.receipt_digest) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_EVIDENCE",
      "Certification evidence receipt digest does not match its contents",
    );
  }
}

function validateApproval(approval, label) {
  assertExactKeys(
    approval,
    [
      "reference",
      "subject_digest",
      "issued_at",
      "scope_digest",
      "assertion_digest",
    ],
    [
      "reference",
      "subject_digest",
      "issued_at",
      "scope_digest",
      "assertion_digest",
    ],
    label,
  );
  safeReference(approval.reference, `${label}.reference`);
  sha256(approval.subject_digest, `${label}.subject_digest`);
  canonicalInstant(approval.issued_at, `${label}.issued_at`);
  sha256(approval.scope_digest, `${label}.scope_digest`);
  sha256(approval.assertion_digest, `${label}.assertion_digest`);
  return approval;
}

export function validateSandboxCertificationEvidence(evidence) {
  assertExactKeys(
    evidence,
    [
      "schema_version",
      "kind",
      "org_fingerprint",
      "runtime_attestation_digest",
      "package_digest",
      "field_map_version",
      "metadata_compatibility_digest",
      "suite_version",
      "fixture_manifest_digest",
      "authorization_scope_digest",
      "authorization_assertion_digest",
      "scenario_ids",
      "query_count",
      "started_at",
      "completed_at",
      "outcome",
      "receipt_digest",
    ],
    [
      "schema_version",
      "kind",
      "org_fingerprint",
      "runtime_attestation_digest",
      "package_digest",
      "field_map_version",
      "metadata_compatibility_digest",
      "suite_version",
      "fixture_manifest_digest",
      "authorization_scope_digest",
      "authorization_assertion_digest",
      "scenario_ids",
      "query_count",
      "started_at",
      "completed_at",
      "outcome",
      "receipt_digest",
    ],
    "sandbox_certification_evidence",
  );
  if (evidence.schema_version !== CONTRACTS.sandboxCertificationEvidence
    || evidence.kind !== "sandbox_read_certification"
    || evidence.field_map_version !== FIELD_MAP_VERSION
    || evidence.suite_version !== SANDBOX_SUITE_VERSION
    || evidence.outcome !== "pass") {
    throw new SafetyError(
      "INVALID_CERTIFICATION_EVIDENCE",
      "Sandbox certification evidence metadata is invalid",
    );
  }
  for (const key of [
    "org_fingerprint",
    "runtime_attestation_digest",
    "package_digest",
    "metadata_compatibility_digest",
    "fixture_manifest_digest",
    "authorization_scope_digest",
    "authorization_assertion_digest",
  ]) {
    sha256(evidence[key], key);
  }
  if (!Array.isArray(evidence.scenario_ids)
    || evidence.scenario_ids.length !== SANDBOX_SCENARIO_IDS.length
    || evidence.scenario_ids.some((id, index) =>
      id !== SANDBOX_SCENARIO_IDS[index])) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_EVIDENCE",
      "Sandbox certification evidence must contain the exact canonical scenario set",
    );
  }
  if (!Number.isInteger(evidence.query_count)
    || evidence.query_count < 1
    || evidence.query_count > CAPS.queries * 10) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_EVIDENCE",
      "Sandbox certification evidence query count is invalid",
    );
  }
  const startedAt = canonicalInstant(evidence.started_at, "started_at");
  const completedAt = canonicalInstant(evidence.completed_at, "completed_at");
  if (completedAt < startedAt) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_EVIDENCE",
      "Sandbox certification completion cannot precede its start",
    );
  }
  validateReceiptDigest(evidence);
  return evidence;
}

export function buildSandboxCertificationEvidence(fields) {
  const core = {
    schema_version: CONTRACTS.sandboxCertificationEvidence,
    kind: "sandbox_read_certification",
    org_fingerprint: fields.orgFingerprint,
    runtime_attestation_digest: fields.runtimeAttestationDigest,
    package_digest: fields.packageDigest,
    field_map_version: FIELD_MAP_VERSION,
    metadata_compatibility_digest: fields.metadataCompatibilityDigest,
    suite_version: SANDBOX_SUITE_VERSION,
    fixture_manifest_digest: fields.fixtureManifestDigest,
    authorization_scope_digest: fields.authorizationScopeDigest,
    authorization_assertion_digest:
      fields.authorizationAssertionDigest,
    scenario_ids: [...SANDBOX_SCENARIO_IDS],
    query_count: fields.queryCount,
    started_at: fields.startedAt.toISOString(),
    completed_at: fields.completedAt.toISOString(),
    outcome: "pass",
  };
  return validateSandboxCertificationEvidence({
    ...core,
    receipt_digest: digest(core),
  });
}

export function validateProductionApprovalEvidence(evidence) {
  assertExactKeys(
    evidence,
    [
      "schema_version",
      "kind",
      "production_org_fingerprint",
      "sandbox_evidence_digest",
      "runtime_attestation_digest",
      "package_digest",
      "field_map_version",
      "metadata_compatibility_digest",
      "approval_scope_digest",
      "administrator_approval",
      "risk_owner_approval",
      "data_query_count",
      "completed_at",
      "outcome",
      "receipt_digest",
    ],
    [
      "schema_version",
      "kind",
      "production_org_fingerprint",
      "sandbox_evidence_digest",
      "runtime_attestation_digest",
      "package_digest",
      "field_map_version",
      "metadata_compatibility_digest",
      "approval_scope_digest",
      "administrator_approval",
      "risk_owner_approval",
      "data_query_count",
      "completed_at",
      "outcome",
      "receipt_digest",
    ],
    "production_approval_evidence",
  );
  if (evidence.schema_version !== CONTRACTS.productionApprovalEvidence
    || evidence.kind !== "production_read_approval"
    || evidence.field_map_version !== FIELD_MAP_VERSION
    || evidence.data_query_count !== 0
    || evidence.outcome !== "pass") {
    throw new SafetyError(
      "INVALID_CERTIFICATION_EVIDENCE",
      "Production approval evidence metadata is invalid",
    );
  }
  for (const key of [
    "production_org_fingerprint",
    "sandbox_evidence_digest",
    "runtime_attestation_digest",
    "package_digest",
    "metadata_compatibility_digest",
    "approval_scope_digest",
  ]) {
    sha256(evidence[key], key);
  }
  validateApproval(
    evidence.administrator_approval,
    "administrator_approval",
  );
  validateApproval(
    evidence.risk_owner_approval,
    "risk_owner_approval",
  );
  if (evidence.administrator_approval.reference
      === evidence.risk_owner_approval.reference
    || evidence.administrator_approval.subject_digest
      === evidence.risk_owner_approval.subject_digest
    || evidence.administrator_approval.assertion_digest
      === evidence.risk_owner_approval.assertion_digest
    || evidence.administrator_approval.scope_digest
      !== evidence.approval_scope_digest
    || evidence.risk_owner_approval.scope_digest
      !== evidence.approval_scope_digest) {
    throw new SafetyError(
      "INVALID_CERTIFICATION_EVIDENCE",
      "Production approval roles must be distinct and bind the same exact scope",
    );
  }
  canonicalInstant(evidence.completed_at, "completed_at");
  validateReceiptDigest(evidence);
  return evidence;
}

export function buildProductionApprovalEvidence(fields) {
  const core = {
    schema_version: CONTRACTS.productionApprovalEvidence,
    kind: "production_read_approval",
    production_org_fingerprint: fields.productionOrgFingerprint,
    sandbox_evidence_digest: fields.sandboxEvidenceDigest,
    runtime_attestation_digest: fields.runtimeAttestationDigest,
    package_digest: fields.packageDigest,
    field_map_version: FIELD_MAP_VERSION,
    metadata_compatibility_digest: fields.metadataCompatibilityDigest,
    approval_scope_digest: fields.approvalScopeDigest,
    administrator_approval: { ...fields.administratorApproval },
    risk_owner_approval: { ...fields.riskOwnerApproval },
    data_query_count: 0,
    completed_at: fields.completedAt.toISOString(),
    outcome: "pass",
  };
  return validateProductionApprovalEvidence({
    ...core,
    receipt_digest: digest(core),
  });
}

export function validateCertificationEvidence(evidence) {
  if (evidence?.kind === "sandbox_read_certification") {
    return validateSandboxCertificationEvidence(evidence);
  }
  if (evidence?.kind === "production_read_approval") {
    return validateProductionApprovalEvidence(evidence);
  }
  throw new SafetyError(
    "INVALID_CERTIFICATION_EVIDENCE",
    "Certification evidence kind is unsupported",
  );
}

export const certificationEvidenceInternals = Object.freeze({
  SHA256,
  receiptCore,
  validateApproval,
});

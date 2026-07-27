import {
  createPublicKey,
  verify as verifySignature,
} from "node:crypto";
import { join } from "node:path";

import {
  CAPS,
  CERTIFICATION_APPROVAL_AUDIENCE,
  CERTIFICATION_APPROVAL_ROLES,
  CERTIFICATION_SCOPE_TTL_MS,
  CLASSIFICATION,
  CONTRACTS,
} from "./constants.mjs";
import {
  assertExactKeys,
  canonicalJson,
  digest,
  readStableRegularFile,
  SafetyError,
  sanitizeText,
} from "./security.mjs";

const SHA256 = /^[a-f0-9]{64}$/u;
const OPAQUE_ID = /^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$/u;
const NONCE = /^[A-Za-z0-9_-]{22,128}$/u;
const ROLES = new Set(Object.values(CERTIFICATION_APPROVAL_ROLES));

function safeText(value, label, maximum = 200) {
  if (typeof value !== "string"
    || value.length < 1
    || value.length > maximum
    || sanitizeText(value) !== value) {
    throw new SafetyError(
      "INVALID_APPROVAL_ASSERTION",
      `${label} must be safe opaque text`,
    );
  }
  return value;
}

function opaqueId(value, label) {
  if (typeof value !== "string" || !OPAQUE_ID.test(value)) {
    throw new SafetyError(
      "INVALID_APPROVAL_ASSERTION",
      `${label} must be a bounded opaque identifier`,
    );
  }
  return value;
}

function sha256(value, label) {
  if (typeof value !== "string" || !SHA256.test(value)) {
    throw new SafetyError(
      "INVALID_APPROVAL_ASSERTION",
      `${label} must be a SHA-256 digest`,
    );
  }
  return value;
}

function canonicalInstant(value, label) {
  if (typeof value !== "string") {
    throw new SafetyError(
      "INVALID_APPROVAL_ASSERTION",
      `${label} must be a canonical ISO timestamp`,
    );
  }
  const instant = new Date(value);
  if (!Number.isFinite(instant.getTime())
    || instant.toISOString() !== value) {
    throw new SafetyError(
      "INVALID_APPROVAL_ASSERTION",
      `${label} must be a canonical ISO timestamp`,
    );
  }
  return instant;
}

function canonicalBase64(value, label, {
  url = false,
  exactBytes = null,
  maximumBytes = 1_024,
} = {}) {
  if (typeof value !== "string" || value.length < 1) {
    throw new SafetyError(
      "INVALID_APPROVAL_ASSERTION",
      `${label} must be canonical base64`,
    );
  }
  let bytes;
  try {
    bytes = Buffer.from(value, url ? "base64url" : "base64");
  } catch {
    throw new SafetyError(
      "INVALID_APPROVAL_ASSERTION",
      `${label} must be canonical base64`,
    );
  }
  const encoded = bytes.toString(url ? "base64url" : "base64");
  if (encoded !== value
    || bytes.length < 1
    || bytes.length > maximumBytes
    || (exactBytes !== null && bytes.length !== exactBytes)) {
    throw new SafetyError(
      "INVALID_APPROVAL_ASSERTION",
      `${label} must be canonical base64`,
    );
  }
  return bytes;
}

export function approvalAssertionCore(assertion) {
  return Object.fromEntries(
    Object.entries(assertion).filter(([key]) => key !== "signature"),
  );
}

export function validateApprovalAssertionShape(assertion, {
  expectedRole = null,
} = {}) {
  assertExactKeys(
    assertion,
    [
      "schema_version",
      "issuer",
      "key_id",
      "subject_digest",
      "role",
      "audience",
      "reference",
      "scope_digest",
      "nonce",
      "issued_at",
      "expires_at",
      "signature",
    ],
    [
      "schema_version",
      "issuer",
      "key_id",
      "subject_digest",
      "role",
      "audience",
      "reference",
      "scope_digest",
      "nonce",
      "issued_at",
      "expires_at",
      "signature",
    ],
    "approval_assertion",
  );
  if (assertion.schema_version !== CONTRACTS.approvalAssertion
    || assertion.audience !== CERTIFICATION_APPROVAL_AUDIENCE
    || !ROLES.has(assertion.role)
    || (expectedRole !== null && assertion.role !== expectedRole)) {
    throw new SafetyError(
      "INVALID_APPROVAL_ASSERTION",
      "Approval assertion version, audience, or role is invalid",
    );
  }
  opaqueId(assertion.issuer, "approval_assertion.issuer");
  opaqueId(assertion.key_id, "approval_assertion.key_id");
  sha256(assertion.subject_digest, "approval_assertion.subject_digest");
  safeText(assertion.reference, "approval_assertion.reference");
  sha256(assertion.scope_digest, "approval_assertion.scope_digest");
  if (typeof assertion.nonce !== "string"
    || !NONCE.test(assertion.nonce)) {
    throw new SafetyError(
      "INVALID_APPROVAL_ASSERTION",
      "approval_assertion.nonce must contain at least 128 bits of opaque text",
    );
  }
  const issuedAt = canonicalInstant(
    assertion.issued_at,
    "approval_assertion.issued_at",
  );
  const expiresAt = canonicalInstant(
    assertion.expires_at,
    "approval_assertion.expires_at",
  );
  if (expiresAt <= issuedAt
    || expiresAt.getTime() - issuedAt.getTime()
      > CERTIFICATION_SCOPE_TTL_MS) {
    throw new SafetyError(
      "INVALID_APPROVAL_ASSERTION",
      "Approval assertion validity must be positive and bounded",
    );
  }
  canonicalBase64(
    assertion.signature,
    "approval_assertion.signature",
    { url: true, exactBytes: 64 },
  );
  return assertion;
}

function validateTrustKey(key, index) {
  const label = `approval_trust.keys[${index}]`;
  assertExactKeys(
    key,
    [
      "issuer",
      "key_id",
      "role",
      "public_key_spki",
      "not_before",
      "expires_at",
    ],
    [
      "issuer",
      "key_id",
      "role",
      "public_key_spki",
      "not_before",
      "expires_at",
    ],
    label,
  );
  opaqueId(key.issuer, `${label}.issuer`);
  opaqueId(key.key_id, `${label}.key_id`);
  if (!ROLES.has(key.role)) {
    throw new SafetyError(
      "INVALID_APPROVAL_TRUST",
      `${label}.role is unsupported`,
    );
  }
  const publicKeyBytes = canonicalBase64(
    key.public_key_spki,
    `${label}.public_key_spki`,
  );
  const notBefore = canonicalInstant(key.not_before, `${label}.not_before`);
  const expiresAt = canonicalInstant(key.expires_at, `${label}.expires_at`);
  if (expiresAt <= notBefore) {
    throw new SafetyError(
      "INVALID_APPROVAL_TRUST",
      `${label} validity window is invalid`,
    );
  }
  let publicKey;
  try {
    publicKey = createPublicKey({
      key: publicKeyBytes,
      format: "der",
      type: "spki",
    });
  } catch {
    throw new SafetyError(
      "INVALID_APPROVAL_TRUST",
      `${label}.public_key_spki is not a valid public key`,
    );
  }
  if (publicKey.asymmetricKeyType !== "ed25519") {
    throw new SafetyError(
      "INVALID_APPROVAL_TRUST",
      `${label}.public_key_spki must be Ed25519`,
    );
  }
  return { key, publicKey };
}

export function validateApprovalTrust(document) {
  assertExactKeys(
    document,
    ["schema_version", "classification", "audience", "keys"],
    ["schema_version", "classification", "audience", "keys"],
    "approval_trust",
  );
  if (document.schema_version !== CONTRACTS.approvalTrust
    || document.classification !== CLASSIFICATION
    || document.audience !== CERTIFICATION_APPROVAL_AUDIENCE
    || !Array.isArray(document.keys)
    || document.keys.length < 1
    || document.keys.length > CAPS.approvalTrustKeys) {
    throw new SafetyError(
      "INVALID_APPROVAL_TRUST",
      "Approval trust metadata or key count is invalid",
    );
  }
  const validated = document.keys.map(validateTrustKey);
  const identities = validated.map(({ key }) =>
    `${key.issuer}\u0000${key.key_id}`);
  const publicKeys = validated.map(({ key }) => key.public_key_spki);
  if (new Set(identities).size !== identities.length
    || new Set(publicKeys).size !== publicKeys.length) {
    throw new SafetyError(
      "INVALID_APPROVAL_TRUST",
      "Approval trust keys and signing authorities must be unique",
    );
  }
  const sorted = [...identities].sort();
  if (identities.some((identity, index) => identity !== sorted[index])) {
    throw new SafetyError(
      "INVALID_APPROVAL_TRUST",
      "Approval trust keys must use canonical issuer and key-ID order",
    );
  }
  return Object.freeze({
    document,
    keys: validated,
  });
}

export function approvalTrustPath(stateStore) {
  const skillDirectory = stateStore?.paths?.skill_directory;
  if (typeof skillDirectory !== "string") {
    throw new SafetyError(
      "INVALID_APPROVAL_TRUST",
      "Approval trust requires the private skill state directory",
    );
  }
  return join(skillDirectory, "approval-trust.json");
}

export async function loadApprovalTrust(stateStore) {
  const path = approvalTrustPath(stateStore);
  let bytes;
  try {
    ({ bytes } = await readStableRegularFile(path, {
      maximumBytes: CAPS.approvalTrustBytes,
      requiredMode: 0o600,
    }));
  } catch (error) {
    if (error instanceof SafetyError) throw error;
    throw new SafetyError(
      "APPROVAL_TRUST_NOT_CONFIGURED",
      "Private approval trust is unavailable",
    );
  }
  let document;
  try {
    document = JSON.parse(bytes.toString("utf8"));
  } catch {
    throw new SafetyError(
      "INVALID_APPROVAL_TRUST",
      "Private approval trust is not valid JSON",
    );
  }
  return validateApprovalTrust(document);
}

export function verifyApprovalAssertion(assertion, {
  trust,
  expectedRole,
  expectedScope,
  now = new Date(),
} = {}) {
  validateApprovalAssertionShape(assertion, { expectedRole });
  if (!trust?.keys || !Array.isArray(trust.keys)) {
    throw new SafetyError(
      "INVALID_APPROVAL_TRUST",
      "Verified approval trust is required",
    );
  }
  const instant = now instanceof Date ? new Date(now.getTime()) : new Date(now);
  if (!Number.isFinite(instant.getTime())) {
    throw new SafetyError(
      "INVALID_CLOCK",
      "Approval verification clock is invalid",
    );
  }
  if (!expectedScope
    || assertion.scope_digest !== expectedScope.scope_digest) {
    throw new SafetyError(
      "APPROVAL_SCOPE_MISMATCH",
      "Approval assertion does not bind the current scope",
    );
  }
  const issuedAt = new Date(assertion.issued_at);
  const expiresAt = new Date(assertion.expires_at);
  const scopeIssuedAt = new Date(expectedScope.issued_at);
  const scopeExpiresAt = new Date(expectedScope.expires_at);
  if (issuedAt < scopeIssuedAt
    || issuedAt > instant
    || instant >= expiresAt
    || expiresAt > scopeExpiresAt) {
    throw new SafetyError(
      "APPROVAL_ASSERTION_EXPIRED",
      "Approval assertion is future-dated, expired, or outside the scope window",
    );
  }
  const matches = trust.keys.filter(({ key }) =>
    key.issuer === assertion.issuer
    && key.key_id === assertion.key_id
    && key.role === assertion.role);
  if (matches.length !== 1) {
    throw new SafetyError(
      "UNTRUSTED_APPROVAL_ASSERTION",
      "Approval assertion was not issued by an authorized role key",
    );
  }
  const [{ key, publicKey }] = matches;
  const keyNotBefore = new Date(key.not_before);
  const keyExpiresAt = new Date(key.expires_at);
  if (issuedAt < keyNotBefore
    || issuedAt >= keyExpiresAt
    || instant >= keyExpiresAt) {
    throw new SafetyError(
      "UNTRUSTED_APPROVAL_ASSERTION",
      "Approval assertion signing key is not currently trusted",
    );
  }
  const signature = canonicalBase64(
    assertion.signature,
    "approval_assertion.signature",
    { url: true, exactBytes: 64 },
  );
  const verified = verifySignature(
    null,
    Buffer.from(canonicalJson(approvalAssertionCore(assertion)), "utf8"),
    publicKey,
    signature,
  );
  if (!verified) {
    throw new SafetyError(
      "INVALID_APPROVAL_SIGNATURE",
      "Approval assertion signature is invalid",
    );
  }
  const assertionDigest = digest(assertion);
  return Object.freeze({
    assertion,
    assertion_digest: assertionDigest,
    replay_key_digest: digest({
      issuer: assertion.issuer,
      key_id: assertion.key_id,
      nonce: assertion.nonce,
    }),
    evidence: Object.freeze({
      reference: assertion.reference,
      subject_digest: assertion.subject_digest,
      issued_at: assertion.issued_at,
      scope_digest: assertion.scope_digest,
      assertion_digest: assertionDigest,
    }),
  });
}

export const approvalTrustInternals = Object.freeze({
  NONCE,
  OPAQUE_ID,
  SHA256,
  canonicalBase64,
});

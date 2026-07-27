import assert from "node:assert/strict";
import {
  generateKeyPairSync,
  sign,
} from "node:crypto";
import {
  chmod,
  mkdtemp,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  approvalTrustPath,
  loadApprovalTrust,
  validateApprovalTrust,
  verifyApprovalAssertion,
} from "../scripts/approval-trust.mjs";
import {
  CERTIFICATION_APPROVAL_AUDIENCE,
  CERTIFICATION_APPROVAL_ROLES,
  CLASSIFICATION,
  CONTRACTS,
} from "../scripts/constants.mjs";
import {
  appendApprovalAssertions,
  assertApprovalAssertionsUnused,
  buildOfflineRegistryEntry,
  emptyOrgRegistry,
  upsertRegistryEntry,
} from "../scripts/org-registry.mjs";
import { canonicalJson } from "../scripts/security.mjs";
import { createStateStore } from "../scripts/state-store.mjs";

const NOW = new Date("2030-01-01T00:10:00.000Z");
const SCOPE = Object.freeze({
  scope_digest: "a".repeat(64),
  issued_at: "2030-01-01T00:00:00.000Z",
  expires_at: "2030-01-01T00:30:00.000Z",
});

function authority({
  issuer = "synthetic-approval-authority",
  keyId = "sandbox-certifier-key",
  role = CERTIFICATION_APPROVAL_ROLES.sandbox,
} = {}) {
  const { privateKey, publicKey } = generateKeyPairSync("ed25519");
  return {
    issuer,
    key_id: keyId,
    role,
    private_key: privateKey,
    public_key_spki: publicKey.export({
      format: "der",
      type: "spki",
    }).toString("base64"),
  };
}

function trustDocument(signer) {
  return {
    schema_version: CONTRACTS.approvalTrust,
    classification: CLASSIFICATION,
    audience: CERTIFICATION_APPROVAL_AUDIENCE,
    keys: [{
      issuer: signer.issuer,
      key_id: signer.key_id,
      role: signer.role,
      public_key_spki: signer.public_key_spki,
      not_before: "2029-12-31T00:00:00.000Z",
      expires_at: "2030-01-02T00:00:00.000Z",
    }],
  };
}

function signedAssertion(signer, overrides = {}) {
  const core = {
    schema_version: CONTRACTS.approvalAssertion,
    issuer: signer.issuer,
    key_id: signer.key_id,
    subject_digest: "1".repeat(64),
    role: signer.role,
    audience: CERTIFICATION_APPROVAL_AUDIENCE,
    reference: "APPROVAL-TRUST-TEST",
    scope_digest: SCOPE.scope_digest,
    nonce: "approvalTrustNonce000001",
    issued_at: SCOPE.issued_at,
    expires_at: SCOPE.expires_at,
    ...overrides,
  };
  return {
    ...core,
    signature: sign(
      null,
      Buffer.from(canonicalJson(core), "utf8"),
      signer.private_key,
    ).toString("base64url"),
  };
}

async function privateTrustStore(t, document) {
  const stateRoot = await mkdtemp(join(tmpdir(), "sf-approval-trust-"));
  t.after(async () => {
    await rm(stateRoot, { recursive: true, force: true });
  });
  const stateStore = createStateStore({ stateRoot });
  await stateStore.initialize();
  await writeFile(
    approvalTrustPath(stateStore),
    `${canonicalJson(document)}\n`,
    { encoding: "utf8", flag: "wx", mode: 0o600 },
  );
  return stateStore;
}

test("valid Ed25519 assertion verifies against private approval trust", async (t) => {
  const signer = authority();
  const stateStore = await privateTrustStore(t, trustDocument(signer));
  const trust = await loadApprovalTrust(stateStore);
  const assertion = signedAssertion(signer);
  const verified = verifyApprovalAssertion(assertion, {
    trust,
    expectedRole: CERTIFICATION_APPROVAL_ROLES.sandbox,
    expectedScope: SCOPE,
    now: NOW,
  });

  assert.equal(verified.assertion, assertion);
  assert.match(verified.assertion_digest, /^[a-f0-9]{64}$/u);
  assert.match(verified.replay_key_digest, /^[a-f0-9]{64}$/u);
  assert.equal(verified.evidence.reference, assertion.reference);
});

test("approval assertions fail closed for malformed or unauthorized evidence", () => {
  const trustedSigner = authority();
  const trustDocumentFixture = trustDocument(trustedSigner);
  const trust = validateApprovalTrust(trustDocumentFixture);
  const verify = (assertion, expectedRole =
    CERTIFICATION_APPROVAL_ROLES.sandbox) =>
    verifyApprovalAssertion(assertion, {
      trust,
      expectedRole,
      expectedScope: SCOPE,
      now: NOW,
    });
  const valid = signedAssertion(trustedSigner);
  const {
    signature: ignoredSignature,
    ...unsigned
  } = valid;
  void ignoredSignature;
  const rogueSigner = authority({
    issuer: "untrusted-approval-authority",
    keyId: "untrusted-key",
  });
  const wrongRoleSigner = authority({
    keyId: "risk-owner-key",
    role: CERTIFICATION_APPROVAL_ROLES.productionRiskOwner,
  });

  const cases = [
    {
      name: "missing signature",
      code: "MISSING_INPUT_FIELD",
      run: () => verify(unsigned),
    },
    {
      name: "untrusted key",
      code: "UNTRUSTED_APPROVAL_ASSERTION",
      run: () => verify(signedAssertion(rogueSigner)),
    },
    {
      name: "wrong role",
      code: "INVALID_APPROVAL_ASSERTION",
      run: () => verifyApprovalAssertion(
        signedAssertion(wrongRoleSigner),
        {
          trust: validateApprovalTrust(trustDocument(wrongRoleSigner)),
          expectedRole: CERTIFICATION_APPROVAL_ROLES.sandbox,
          expectedScope: SCOPE,
          now: NOW,
        },
      ),
    },
    {
      name: "wrong scope",
      code: "APPROVAL_SCOPE_MISMATCH",
      run: () => verify(signedAssertion(trustedSigner, {
        scope_digest: "b".repeat(64),
      })),
    },
    {
      name: "bad signature",
      code: "INVALID_APPROVAL_SIGNATURE",
      run: () => verify({
        ...valid,
        reference: "TAMPERED-APPROVAL",
      }),
    },
    {
      name: "expired assertion",
      code: "APPROVAL_ASSERTION_EXPIRED",
      run: () => verify(signedAssertion(trustedSigner, {
        expires_at: "2030-01-01T00:05:00.000Z",
      })),
    },
    {
      name: "future assertion",
      code: "APPROVAL_ASSERTION_EXPIRED",
      run: () => verify(signedAssertion(trustedSigner, {
        issued_at: "2030-01-01T00:15:00.000Z",
        expires_at: "2030-01-01T00:20:00.000Z",
      })),
    },
    {
      name: "unknown nested trust-key field",
      code: "UNKNOWN_INPUT_FIELD",
      run: () => validateApprovalTrust({
        ...trustDocumentFixture,
        keys: [{
          ...trustDocumentFixture.keys[0],
          private_metadata: {},
        }],
      }),
    },
  ];

  for (const rejection of cases) {
    assert.throws(
      rejection.run,
      { code: rejection.code },
      rejection.name,
    );
  }
});

test("approval trust file rejects non-private mode", async (t) => {
  const signer = authority();
  const stateStore = await privateTrustStore(t, trustDocument(signer));
  await chmod(approvalTrustPath(stateStore), 0o644);

  await assert.rejects(
    loadApprovalTrust(stateStore),
    { code: "INSECURE_INPUT_PERMISSIONS" },
  );
});

test("approval assertion replay ledger rejects reused signed evidence", () => {
  const signer = authority();
  const trust = validateApprovalTrust(trustDocument(signer));
  const verification = verifyApprovalAssertion(signedAssertion(signer), {
    trust,
    expectedRole: CERTIFICATION_APPROVAL_ROLES.sandbox,
    expectedScope: SCOPE,
    now: NOW,
  });
  const entry = buildOfflineRegistryEntry({
    alias: "synthetic",
    friendlyLabel: "Synthetic Sandbox",
    identity: {
      org_id: "00D000000000001AAA",
      username: "synthetic@example.invalid",
      instance_url: "https://synthetic.example.invalid",
    },
    orgType: "sandbox",
    environment: "sandbox",
    now: NOW,
  });
  const reserved = appendApprovalAssertions(entry, {
    verifications: [verification],
    now: NOW,
  });
  const registry = upsertRegistryEntry(emptyOrgRegistry(), reserved);

  assert.throws(
    () => assertApprovalAssertionsUnused(registry, [verification]),
    { code: "APPROVAL_ASSERTION_REPLAYED" },
  );
});

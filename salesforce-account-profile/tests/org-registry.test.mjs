import assert from "node:assert/strict";
import test from "node:test";

import { FIELD_MAP_VERSION } from "../scripts/constants.mjs";
import {
  assertRegistryReadiness,
  buildOfflineRegistryEntry,
  emptyOrgRegistry,
  orgIdentityFingerprint,
  refreshRegistryVerification,
  resolveRegistryEntry,
  upsertRegistryEntry,
  validateOrgRegistry,
  validateRegistryEntry,
  verifyRegistryIdentity,
} from "../scripts/org-registry.mjs";

const identity = {
  org_id: "00D000000000001AAA",
  username: "synthetic@example.invalid",
  instance_url: "https://synthetic.example.invalid",
  connected_status: "Connected",
};

function offline(overrides = {}) {
  return {
    ...buildOfflineRegistryEntry({
      alias: "synthetic",
      friendlyLabel: "UAT",
      identity,
      orgType: "sandbox",
      environment: "sandbox",
      now: new Date("2030-01-01T00:00:00.000Z"),
    }),
    ...overrides,
  };
}

test("offline enrollment stores only a fingerprint and redacted identity metadata", () => {
  const entry = offline();
  const serialized = JSON.stringify(entry);
  assert.match(entry.org_fingerprint, /^[a-f0-9]{64}$/u);
  assert.equal(entry.org_id_suffix, "001AAA");
  assert.equal(entry.instance_host, "synthetic.example.invalid");
  assert.equal(serialized.includes(identity.org_id), false);
  assert.equal(serialized.includes(identity.username), false);
  assert.equal(serialized.includes(identity.instance_url), false);
  assert.equal(entry.certification_state, "offline_validated");
  assert.equal(entry.metadata_verified_at, null);
  assert.equal(entry.certification_verified_at, null);
});

test("registry is canonical, unique, and resolves friendly labels or aliases", () => {
  const first = offline();
  const secondIdentity = {
    ...identity,
    org_id: "00D000000000002AAA",
    username: "second@example.invalid",
    instance_url: "https://second.example.invalid",
  };
  const second = buildOfflineRegistryEntry({
    alias: "production",
    friendlyLabel: "Production",
    identity: secondIdentity,
    orgType: "production_or_developer",
    environment: "production",
    now: new Date("2030-01-01T00:00:00.000Z"),
  });
  const registry = upsertRegistryEntry(
    upsertRegistryEntry(emptyOrgRegistry(), first),
    second,
  );
  assert.deepEqual(
    registry.entries.map((entry) => entry.alias),
    ["production", "synthetic"],
  );
  assert.equal(resolveRegistryEntry(registry, "uat").alias, "synthetic");
  assert.equal(resolveRegistryEntry(registry, "PRODUCTION").alias, "production");
  assert.throws(
    () => validateOrgRegistry({
      ...registry,
      entries: [first, { ...second, alias: "second", friendly_label: "UAT" }],
    }),
    { code: "INVALID_ORG_REGISTRY" },
  );
});

test("identity verification fails after org drift without retaining raw identity", () => {
  const entry = offline();
  assert.equal(verifyRegistryIdentity(entry, identity), entry);
  assert.throws(
    () => verifyRegistryIdentity(entry, {
      ...identity,
      org_id: "00D000000000002AAA",
    }),
    { code: "ORG_IDENTITY_MISMATCH" },
  );
  assert.notEqual(
    orgIdentityFingerprint(identity).fingerprint,
    orgIdentityFingerprint({ ...identity, username: "other@example.invalid" })
      .fingerprint,
  );
});

test("offline validation never authorizes real reads without test-only injection", () => {
  const entry = offline();
  assert.throws(
    () => assertRegistryReadiness(entry),
    { code: "SANDBOX_NOT_CERTIFIED" },
  );
  assert.equal(
    assertRegistryReadiness(entry, { allowOfflineExecution: true }),
    entry,
  );
});

test("production approval requires separate sandbox, administrator, and risk evidence", () => {
  const base = offline({
    alias: "production",
    friendly_label: "Production",
    org_type: "production_or_developer",
    environment: "production",
    metadata_verified_at: "2030-01-02T00:00:00.000Z",
  });
  assert.throws(
    () => validateRegistryEntry({
      ...base,
      certification_state: "production_read_approved",
      certification_verified_at: "2030-01-02T00:00:00.000Z",
    }),
    { code: "INVALID_ORG_REGISTRY" },
  );
  const approved = validateRegistryEntry({
    ...base,
    certification_state: "production_read_approved",
    certification_verified_at: "2030-01-02T00:00:00.000Z",
    approvals: {
      sandbox_evidence_digest: "a".repeat(64),
      administrator_reference: "ADMIN-APPROVAL-1",
      administrator_approved_at: "2030-01-02T00:00:00.000Z",
      risk_owner_reference: "RISK-APPROVAL-1",
      risk_owner_approved_at: "2030-01-02T00:00:00.000Z",
    },
  });
  assert.equal(assertRegistryReadiness(approved), approved);
});

test("sandbox certification cannot be reused as production approval", () => {
  const sandboxCertified = {
    ...offline(),
    certification_state: "sandbox_read_certified",
    metadata_verified_at: "2030-01-02T00:00:00.000Z",
    certification_verified_at: "2030-01-02T00:00:00.000Z",
  };
  assert.equal(assertRegistryReadiness(sandboxCertified), sandboxCertified);
  assert.throws(
    () => validateRegistryEntry({
      ...sandboxCertified,
      environment: "production",
    }),
    { code: "INVALID_ORG_REGISTRY" },
  );
});

test("org type and declared environment obey a fail-closed classification matrix", () => {
  const accepted = [
    ["sandbox", "sandbox"],
    ["scratch", "scratch"],
    ["production_or_developer", "production"],
    ["dev_hub", "production"],
  ];
  for (const [orgType, environment] of accepted) {
    assert.doesNotThrow(() => buildOfflineRegistryEntry({
      alias: `accepted-${orgType}-${environment}`,
      friendlyLabel: `Accepted ${orgType} ${environment}`,
      identity,
      orgType,
      environment,
      now: new Date("2030-01-01T00:00:00.000Z"),
    }));
  }

  const rejected = [
    ["production_or_developer", "sandbox"],
    ["production_or_developer", "scratch"],
    ["production_or_developer", "development"],
    ["sandbox", "production"],
    ["sandbox", "development"],
    ["sandbox", "scratch"],
    ["scratch", "sandbox"],
    ["scratch", "production"],
    ["dev_hub", "sandbox"],
    ["dev_hub", "scratch"],
    ["dev_hub", "development"],
  ];
  for (const [orgType, environment] of rejected) {
    assert.throws(
      () => buildOfflineRegistryEntry({
        alias: `rejected-${orgType}-${environment}`,
        friendlyLabel: `Rejected ${orgType} ${environment}`,
        identity,
        orgType,
        environment,
        now: new Date("2030-01-01T00:00:00.000Z"),
      }),
      { code: "INVALID_ORG_REGISTRY" },
    );
  }
});

test("verified refresh preserves certification and approvals for an unchanged org", () => {
  const approved = validateRegistryEntry({
    ...buildOfflineRegistryEntry({
      alias: "production",
      friendlyLabel: "Production",
      identity,
      orgType: "production_or_developer",
      environment: "production",
      now: new Date("2030-01-01T00:00:00.000Z"),
    }),
    metadata_verified_at: "2030-01-02T00:00:00.000Z",
    certification_state: "production_read_approved",
    certification_verified_at: "2030-01-02T00:00:00.000Z",
    approvals: {
      sandbox_evidence_digest: "a".repeat(64),
      administrator_reference: "ADMIN-APPROVAL-1",
      administrator_approved_at: "2030-01-02T00:00:00.000Z",
      risk_owner_reference: "RISK-APPROVAL-1",
      risk_owner_approved_at: "2030-01-02T00:00:00.000Z",
    },
  });
  const original = structuredClone(approved);
  const refreshed = refreshRegistryVerification(approved, {
    identity,
    orgType: "production_or_developer",
    environment: "production",
    fieldMapVersion: FIELD_MAP_VERSION,
    now: new Date("2030-01-03T00:00:00.000Z"),
  });

  assert.deepEqual(approved, original);
  assert.equal(refreshed.identity_verified_at, "2030-01-03T00:00:00.000Z");
  assert.equal(refreshed.metadata_verified_at, "2030-01-03T00:00:00.000Z");
  assert.equal(refreshed.certification_state, approved.certification_state);
  assert.equal(
    refreshed.certification_verified_at,
    approved.certification_verified_at,
  );
  assert.deepEqual(refreshed.approvals, approved.approvals);
  assert.equal(assertRegistryReadiness(refreshed), refreshed);
});

test("verified refresh fails closed on identity, classification, metadata, or clock drift", () => {
  const entry = offline({
    metadata_verified_at: "2030-01-02T00:00:00.000Z",
  });
  const unchanged = {
    identity,
    orgType: "sandbox",
    environment: "sandbox",
    fieldMapVersion: FIELD_MAP_VERSION,
    now: new Date("2030-01-03T00:00:00.000Z"),
  };
  for (const changedIdentity of [
    { ...identity, org_id: "00D000000000002AAA" },
    { ...identity, username: "other@example.invalid" },
    { ...identity, instance_url: "https://other.example.invalid" },
  ]) {
    assert.throws(
      () => refreshRegistryVerification(entry, {
        ...unchanged,
        identity: changedIdentity,
      }),
      { code: "ORG_IDENTITY_MISMATCH" },
    );
  }
  assert.throws(
    () => refreshRegistryVerification(entry, {
      ...unchanged,
      orgType: "production_or_developer",
      environment: "production",
    }),
    { code: "ORG_CLASSIFICATION_MISMATCH" },
  );
  assert.throws(
    () => refreshRegistryVerification(entry, {
      ...unchanged,
      environment: "production",
    }),
    { code: "INVALID_ORG_REGISTRY" },
  );
  assert.throws(
    () => refreshRegistryVerification(entry, {
      ...unchanged,
      fieldMapVersion: "salesforce-account-profile-field-map/v999",
    }),
    { code: "ORG_METADATA_MISMATCH" },
  );
  assert.throws(
    () => refreshRegistryVerification(entry, {
      ...unchanged,
      now: new Date("2030-01-01T23:59:59.999Z"),
    }),
    { code: "ORG_VERIFICATION_TIME_REGRESSION" },
  );
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  buildReadPlan,
  issueApprovalReceipt,
  readPlanDigest,
  validateApprovalReceipt,
  validateReadPlan,
} from "../scripts/read-plan.mjs";
import { IDS } from "./helpers.mjs";

const orgIdentity = {
  target_org: "synthetic",
  org_id: "00D000000000001AAA",
  username: "synthetic@example.invalid",
  instance_url: "https://synthetic.example.invalid/",
  connected_status: "Connected",
};
const issuedAt = new Date("2030-01-01T00:00:00.000Z");
const base = {
  sessionId: "0123456789abcdef0123456789abcdef",
  orgIdentity,
  runtimeAttestationDigest: "a".repeat(64),
  registryReadinessDigest: "d".repeat(64),
  accountSelector: { mode: "exact_name", value: "Example Holdings" },
  issuedAt,
};

test("pipeline preset produces a complete bounded v2 read plan", () => {
  const plan = buildReadPlan(base);
  assert.deepEqual(plan.requested_sections, ["overview", "opportunities", "team"]);
  assert.equal(plan.scope, "selected_account");
  assert.equal(plan.opportunity_scope, "open");
  assert.equal(plan.output_type, "rendered");
  assert.equal(new Date(plan.expires_at) - new Date(plan.issued_at), 30 * 60 * 1_000);
  assert.equal(readPlanDigest(plan).length, 64);
});

test("custom plan validates selected Account, family set, filters, and JSON output", () => {
  const plan = buildReadPlan({
    ...base,
    preset: "custom",
    sections: ["overview", "family", "opportunities", "products", "team"],
    scope: "corporate_family",
    opportunityScope: "closed",
    selectedAccount: { Id: IDS.account1, Name: "Example Holdings" },
    accountReceiptDigest: "b".repeat(64),
    familyAccountIds: [IDS.account2, IDS.account1],
    filters: {
      close_date_from: "2029-01-01",
      close_date_to: "2030-12-31",
      stages: ["Negotiation", "Closed Won"],
    },
    outputType: "json",
  });
  assert.deepEqual(plan.family_account_ids, [IDS.account1, IDS.account2]);
  assert.deepEqual(plan.filters.stages, ["Closed Won", "Negotiation"]);
  assert.equal(validateReadPlan(plan), plan);
});

test("v2 read plan rejects preset drift, unknown fields, and invalid dates", () => {
  const plan = buildReadPlan(base);
  assert.throws(() => validateReadPlan({ ...plan, scope: "corporate_family" }), { code: "INVALID_READ_PLAN" });
  assert.throws(() => validateReadPlan({ ...plan, injected: true }), { code: "UNKNOWN_INPUT_FIELD" });
  assert.throws(() => buildReadPlan({
    ...base,
    preset: "custom",
    sections: ["overview"],
    scope: "selected_account",
    opportunityScope: "open",
    filters: { close_date_from: "2030-02-30" },
  }), { code: "INVALID_READ_PLAN" });
});

test("approval receipt binds the complete read plan and is not reusable after scope drift", () => {
  const plan = buildReadPlan({
    ...base,
    preset: "custom",
    sections: ["overview", "family", "opportunities"],
    scope: "corporate_family",
    opportunityScope: "open",
    selectedAccount: { Id: IDS.account1, Name: "Example Holdings" },
    accountReceiptDigest: "b".repeat(64),
    familyAccountIds: [IDS.account1, IDS.account2],
  });
  const receipt = issueApprovalReceipt(plan, "family_scope", new Date("2030-01-01T00:01:00.000Z"));
  assert.equal(
    validateApprovalReceipt(receipt, plan, "family_scope", new Date("2030-01-01T00:02:00.000Z")),
    receipt,
  );
  const changedPlan = {
    ...plan,
    opportunity_scope: "all",
    preset: "custom",
  };
  assert.throws(
    () => validateApprovalReceipt(receipt, changedPlan, "family_scope", new Date("2030-01-01T00:02:00.000Z")),
    { code: "APPROVAL_RECEIPT_MISMATCH" },
  );
  const validMutations = [
    { ...plan, runtime_attestation_digest: "c".repeat(64) },
    { ...plan, registry_readiness_digest: "e".repeat(64) },
    { ...plan, account_receipt_digest: "d".repeat(64) },
    { ...plan, family_account_ids: [IDS.account1] },
    { ...plan, requested_sections: ["overview", "family"] },
    { ...plan, output_type: "json" },
    { ...plan, filters: { ...plan.filters, close_date_from: "2029-06-01" } },
    {
      ...plan,
      org_identity: { ...plan.org_identity, username: "changed@example.invalid" },
    },
  ];
  for (const mutation of validMutations) {
    assert.throws(
      () => validateApprovalReceipt(receipt, mutation, "family_scope", new Date("2030-01-01T00:02:00.000Z")),
      { code: "APPROVAL_RECEIPT_MISMATCH" },
    );
  }
});

test("stage filter order is canonical before receipt hashing", () => {
  const first = buildReadPlan({
    ...base,
    preset: "custom",
    sections: ["overview", "opportunities"],
    scope: "selected_account",
    opportunityScope: "open",
    filters: { stages: ["Negotiation", "Discovery"] },
  });
  const second = buildReadPlan({
    ...base,
    preset: "custom",
    sections: ["overview", "opportunities"],
    scope: "selected_account",
    opportunityScope: "open",
    filters: { stages: ["Discovery", "Negotiation"] },
  });
  assert.deepEqual(first.filters.stages, ["Discovery", "Negotiation"]);
  assert.equal(readPlanDigest(first), readPlanDigest(second));
});

test("approval receipt expires with its 30-minute session", () => {
  const plan = buildReadPlan(base);
  const receipt = issueApprovalReceipt(plan, "org_and_plan", new Date("2030-01-01T00:01:00.000Z"));
  assert.throws(
    () => validateApprovalReceipt(receipt, plan, "org_and_plan", new Date("2030-01-01T00:30:00.000Z")),
    { code: "APPROVAL_RECEIPT_EXPIRED" },
  );
  assert.throws(
    () => validateApprovalReceipt(receipt, plan, "org_and_plan", new Date("2030-01-01T00:00:30.000Z")),
    { code: "APPROVAL_RECEIPT_EXPIRED" },
  );
});

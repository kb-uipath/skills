import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  FIELD_DEFS,
  FIELD_MAP,
  MeddpiccError,
  buildPatch,
  buildTelemetryPayload,
  classifyError,
  draft,
  duplicateStatus,
  normalizeIntegrationResponse,
  recover,
  receipt,
  verify,
} from "../scripts/meddpicc.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const fixtureDir = path.join(__dirname, "fixtures");
const loadFixture = (name) => JSON.parse(fs.readFileSync(path.join(fixtureDir, name), "utf8"));

function confirmDraft(prepared, overrides = {}) {
  return receipt({
    mode: "confirmation",
    draft: prepared,
    confirmed: true,
    confirmedAt: prepared.generatedAt,
    confirmedBy: prepared.author,
    ...overrides,
  });
}

function safeBuildPayload(prepared, describe, overrides = {}) {
  const confirmation = overrides.confirmation || confirmDraft(prepared);
  return {
    draft: prepared,
    describe,
    connectionId: "conn-123",
    freshLastModifiedDate: prepared.currentLastModifiedDate,
    confirmation,
    transaction: confirmation.transaction,
    now: prepared.generatedAt,
    ...overrides,
  };
}

test("field-map JSON is the source for exported field definitions", () => {
  assert.equal(FIELD_MAP.targetConnector, "uipath-salesforce-sfdc");
  assert.equal(FIELD_DEFS.metrics.apiName, "Metrics__c");
  assert.equal(FIELD_DEFS.compellingEvent.routeTo, "Opportunity_Next_Steps__c");
});

test("unknown content keys fail loudly with structured error", () => {
  assert.throws(
    () => draft({
      opportunityId: "006000000000001AAA",
      author: "Keith Born",
      date: "2026-05-20",
      current: loadFixture("current-opportunity.json"),
      content: { Metricz: "typo" },
    }),
    (error) => error instanceof MeddpiccError && error.code === "UNKNOWN_FIELD_KEY" && error.recoverable === true,
  );
});

test("exact duplicates block while content-only matches warn and still draft", () => {
  const current = loadFixture("current-opportunity.json");
  const exactCurrent = {
    ...current,
    Metrics__c: "Existing metrics\n\n[2026-05-20 - Keith Born]\nReduce handling time by 30%.",
  };
  assert.equal(duplicateStatus(exactCurrent.Metrics__c, "[2026-05-20 - Keith Born]", "Reduce handling time by 30%."), "exact");
  const exact = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-20",
    current: exactCurrent,
    content: { Metrics: "Reduce handling time by 30%." },
  });
  assert.equal(exact.skippedFields[0].reason, "duplicate_entry");
  assert.deepEqual(exact.proposedFields, {});

  const contentOnlyCurrent = { ...current, Metrics__c: "Prior note: Reduce handling time by 30%." };
  assert.equal(duplicateStatus(contentOnlyCurrent.Metrics__c, "[2026-05-20 - Keith Born]", "Reduce handling time by 30%."), "content");
  const contentOnly = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-20",
    current: contentOnlyCurrent,
    content: { Metrics: "Reduce handling time by 30%." },
  });
  assert.equal(Boolean(contentOnly.proposedFields.Metrics__c), true);
  assert.match(contentOnly.warnings[0], /similar content/);
});

test("confirmation receipt is confidential and audit receipt is metadata only", () => {
  const current = loadFixture("current-opportunity.json");
  const describe = loadFixture("describe-opportunity.json");
  const prepared = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-20",
    current,
    generatedAt: "2026-05-20T14:00:00.000Z",
    content: { Metrics: "Reduce handling time by 30%." },
  });
  const confirmation = confirmDraft(prepared);
  const patch = buildPatch(safeBuildPayload(prepared, describe, {
    connectionId: "conn-secret-123",
    confirmation,
    now: "2026-05-20T14:01:00.000Z",
  }));
  const audit = receipt({ mode: "audit", draft: prepared, confirmation, patch });
  assert.equal(confirmation.classification, "confidential");
  assert.equal(confirmation.opportunity.id, current.Id);
  assert.equal(Boolean(confirmation.proposedFields.Metrics__c), true);
  assert.equal(audit.classification, "internal");
  assert.equal("opportunity" in audit, false);
  assert.equal("patch" in audit, false);
  assert.equal(audit.privacy.request_bodies_removed, true);
});

test("valid Economic Buyer Contact ID writes to lookup", () => {
  const current = loadFixture("current-opportunity.json");
  const result = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-20",
    current,
    content: { "Economic Buyer": { contactId: "003Pa00000BuyerIAD" } },
  });
  assert.equal(result.proposedFields.Economic_Buyer__c, "003Pa00000BuyerIAD");
  assert.equal(result.skippedFields.length, 0);
});

test("schema drift and non-updateable fields produce structured errors", () => {
  const current = loadFixture("current-opportunity.json");
  const describe = loadFixture("describe-opportunity.json");
  const prepared = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-20",
    current,
    generatedAt: "2026-05-20T14:00:00.000Z",
    content: { Metrics: "Reduce handling time by 30%." },
  });
  assert.throws(
    () => buildPatch(safeBuildPayload(prepared, { fields: [] }, { now: "2026-05-20T14:01:00.000Z" })),
    (error) => error.code === "SCHEMA_FIELD_MISSING" && error.field === "Metrics__c",
  );

  const blockedDescribe = {
    fields: describe.fields.map((field) => field.name === "Metrics__c" ? { ...field, updateable: false } : field),
  };
  assert.throws(
    () => buildPatch(safeBuildPayload(prepared, blockedDescribe, { now: "2026-05-20T14:01:00.000Z" })),
    (error) => error.code === "FIELD_NOT_UPDATEABLE" && error.field === "Metrics__c",
  );
});

test("build-patch refuses to create a write envelope without connection id", () => {
  const current = loadFixture("current-opportunity.json");
  const describe = loadFixture("describe-opportunity.json");
  const prepared = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-20",
    current,
    generatedAt: "2026-05-20T14:00:00.000Z",
    content: { Metrics: "Reduce handling time by 30%." },
  });

  assert.throws(
    () => buildPatch(safeBuildPayload(prepared, describe, { connectionId: "", now: "2026-05-20T14:01:00.000Z" })),
    (error) => error.code === "MISSING_CONNECTION_ID" && error.recoverable === true,
  );
});

test("telemetry payload strips narrative and identity fields", () => {
  const payload = {
    now: "2026-05-20T14:02:00.000Z",
    skillVersion: "1.1.0",
    skillSha: "abc123",
    runId: "run-1",
    opportunityName: "Sensitive Opportunity",
    contactEmail: "person@example.com",
    amount: "$100,000",
    verify: {
      opportunity: { id: "006000000000001AAA", name: "Sensitive Opportunity" },
      readBackStatus: "all_matched",
      fieldsWritten: [{ field: "Metrics__c" }, { field: "NextStep" }],
      fieldsSkipped: [{ field: "Economic_Buyer__c" }],
      warnings: ["warning"],
      discrepancies: [],
    },
  };
  const before = structuredClone(payload);

  const telemetry = buildTelemetryPayload(payload);

  assert.deepEqual(telemetry, {
    schema_version: "salesforce-meddpicc-telemetry/v1",
    oppId: "006000000000001AAA",
    runTime: "2026-05-20T14:02:00.000Z",
    fieldsTargeted: ["Metrics__c", "NextStep"],
    skillVersion: "1.1.0",
    skillSha: "abc123",
    runId: "run-1",
    readBackStatus: "all_matched",
    fieldsWrittenCount: 2,
    fieldsSkippedCount: 1,
    warningsCount: 1,
    discrepanciesCount: 0,
  });
  assert.equal("opportunityName" in telemetry, false);
  assert.equal("contactEmail" in telemetry, false);
  assert.equal("amount" in telemetry, false);
  assert.deepEqual(payload, before);
});

test("classify-error normalizes mocked Integration Service and Salesforce responses", () => {
  assert.equal(classifyError(loadFixture("connection-missing.json")).code, "CONNECTION_MISSING");
  assert.equal(classifyError(loadFixture("auth-expired.json")).code, "AUTH_EXPIRED");
  assert.equal(classifyError(loadFixture("field-security-error.json")).code, "FIELD_SECURITY_BLOCK");
  assert.equal(classifyError(loadFixture("schema-drift-error.json")).code, "SCHEMA_DRIFT");
  assert.equal(classifyError(loadFixture("validation-error.json")).code, "SALESFORCE_VALIDATION_ERROR");
  assert.equal(normalizeIntegrationResponse(loadFixture("patch-success.json")).classification.code, "SUCCESS_204");
});

test("fixture e2e: next steps plus champion narrative builds patch and verifies", () => {
  const current = loadFixture("current-opportunity.json");
  const describe = loadFixture("describe-opportunity.json");
  const readAfterWrite = loadFixture("read-after-write-next-step.json");
  const prepared = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-19",
    current,
    generatedAt: "2026-05-19T15:00:00.000Z",
    content: {
      NextStep: "Confirm procurement owner and paper-process dates.",
      Champion: "Maria is coaching us through legal and procurement, but she is not yet linked as a Salesforce Contact.",
    },
  });
  const patch = buildPatch(safeBuildPayload(prepared, describe, {
    connectionId: loadFixture("connection-lookup.json").id,
    now: "2026-05-19T15:01:00.000Z",
  }));
  assert.deepEqual(Object.keys(JSON.parse(patch.envelope.body)).sort(), ["NextStep", "Opportunity_Next_Steps__c"]);
  const result = verify({
    draft: prepared,
    transaction: patch.transaction,
    response: loadFixture("patch-success.json"),
    readBack: readAfterWrite,
  });
  assert.equal(result.readBackStatus, "all_matched");
});

test("fixture e2e: full MEDDPICC with picklist validation failure", () => {
  const current = loadFixture("current-opportunity.json");
  const describe = loadFixture("describe-opportunity.json");
  const prepared = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-20",
    current,
    generatedAt: "2026-05-20T14:00:00.000Z",
    content: {
      Metrics: "Reduce handling time by 30%.",
      "Decision Criteria": "Must support Salesforce and UiPath integration.",
      "Decision Process": "Ops validates, procurement approves, VP signs.",
      "Paper Process": "Security review before order form.",
      "Identified Pain": "Manual handoffs delay claims processing.",
      Competition: "Unknown Vendor is being evaluated.",
      Competition__c: "Unknown Vendor",
      "Compelling Event": "Renewal decision due before quarter end.",
    },
  });
  assert.throws(
    () => buildPatch(safeBuildPayload(prepared, describe, { now: "2026-05-20T14:01:00.000Z" })),
    (error) => error.code === "INVALID_PICKLIST_VALUE" && error.field === "Competition__c",
  );
});

test("fixture e2e: verification mismatch is surfaced", () => {
  const current = loadFixture("current-opportunity.json");
  const describe = loadFixture("describe-opportunity.json");
  const prepared = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-20",
    current,
    content: { NextStep: "Confirm procurement owner." },
  });
  const patch = buildPatch(safeBuildPayload(prepared, describe));
  const result = verify({
    draft: prepared,
    transaction: patch.transaction,
    response: loadFixture("patch-success.json"),
    readBack: { ...current, NextStep: "Different value" },
  });
  assert.equal(result.readBackStatus, "mismatch");
  assert.equal(result.discrepancies[0].field, "NextStep");
  assert.equal(result.transaction.state, "recovery_required");
});

test("legacy receipt invocation fails with migration guidance", () => {
  assert.throws(
    () => receipt({}),
    (error) => error.code === "RECEIPT_MODE_REQUIRED" && /--mode confirmation/.test(error.message),
  );
});

test("legacy unversioned draft cannot enter the transaction workflow", () => {
  const current = loadFixture("current-opportunity.json");
  const prepared = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-20",
    current,
    content: { NextStep: "Confirm procurement owner." },
  });
  delete prepared.schema_version;
  assert.throws(
    () => confirmDraft(prepared),
    (error) => error.code === "UNSUPPORTED_DRAFT_SCHEMA" && /Regenerate/.test(error.nextAction),
  );
});

test("build-patch requires matching fresh LastModifiedDate", () => {
  const fixture = loadFixture("missing-freshness.json");
  const current = loadFixture("current-opportunity.json");
  const describe = loadFixture("describe-opportunity.json");
  const prepared = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-20",
    current,
    generatedAt: "2026-05-20T14:00:00.000Z",
    content: { NextStep: "Confirm procurement owner." },
  });
  const input = safeBuildPayload(prepared, describe, fixture);
  delete input.freshLastModifiedDate;
  assert.throws(
    () => buildPatch(input),
    (error) => error.code === fixture.expectedError && /LastModifiedDate/.test(error.nextAction),
  );

  assert.throws(
    () => buildPatch({
      draft: prepared,
      describe,
      connectionId: fixture.connectionId,
      freshLastModifiedDate: prepared.currentLastModifiedDate,
      now: fixture.now,
    }),
    (error) => error.code === "CONFIRMATION_REQUIRED" && /receipt --mode confirmation/.test(error.nextAction),
  );

  const confirmation = confirmDraft(prepared);
  assert.throws(
    () => buildPatch({
      draft: prepared,
      describe,
      connectionId: fixture.connectionId,
      freshLastModifiedDate: prepared.currentLastModifiedDate,
      confirmation,
      now: fixture.now,
    }),
    (error) => error.code === "TRANSACTION_REQUIRED",
  );

  const changed = buildPatch(safeBuildPayload(prepared, describe, {
    now: fixture.now,
    freshLastModifiedDate: "2026-05-20T14:00:30.000+0000",
  }));
  assert.equal(changed.envelope, null);
  assert.equal(changed.requiresFreshRead, true);

  assert.throws(
    () => buildPatch(safeBuildPayload(prepared, describe, { maxConfirmationAgeMinutes: "not-a-number" })),
    (error) => error.code === "INVALID_MAX_CONFIRMATION_AGE",
  );
});

test("operation_id is deterministic across object key order", () => {
  const current = loadFixture("current-opportunity.json");
  const base = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-20",
    current,
    generatedAt: "2026-05-20T14:00:00.000Z",
    content: { Metrics: "Reduce handling time by 30%.", NextStep: "Confirm procurement owner." },
  });
  const reversed = {
    ...base,
    proposedFields: Object.fromEntries(Object.entries(base.proposedFields).reverse()),
  };
  assert.equal(confirmDraft(base).operation_id, confirmDraft(reversed).operation_id);
});

test("tampered confirmation and transaction artifacts fail closed", () => {
  const fixture = loadFixture("tampered-confirmation.json");
  const current = loadFixture("current-opportunity.json");
  const describe = loadFixture("describe-opportunity.json");
  const prepared = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-20",
    current,
    generatedAt: "2026-05-20T14:00:00.000Z",
    content: { NextStep: "Confirm procurement owner." },
  });
  const confirmation = confirmDraft(prepared);
  assert.throws(
    () => buildPatch(safeBuildPayload(prepared, describe, {
      confirmation: { ...confirmation, ...fixture.confirmationMutation },
      now: "2026-05-20T14:01:00.000Z",
    })),
    (error) => error.code === fixture.expectedConfirmationError,
  );
  assert.throws(
    () => buildPatch(safeBuildPayload(prepared, describe, {
      confirmation,
      transaction: { ...confirmation.transaction, ...fixture.transactionMutation },
      now: "2026-05-20T14:01:00.000Z",
    })),
    (error) => error.code === fixture.expectedTransactionError,
  );
});

test("a prepared operation cannot emit a duplicate PATCH envelope", () => {
  const fixture = loadFixture("duplicate-operation.json");
  const current = loadFixture("current-opportunity.json");
  const describe = loadFixture("describe-opportunity.json");
  const prepared = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-20",
    current,
    generatedAt: "2026-05-20T14:00:00.000Z",
    content: { NextStep: "Confirm procurement owner." },
  });
  const confirmation = confirmDraft(prepared);
  const input = safeBuildPayload(prepared, describe, { confirmation, now: "2026-05-20T14:01:00.000Z" });
  const patch = buildPatch(input);
  assert.equal(patch.transaction.state, fixture.reusedState);
  assert.throws(
    () => verify({ draft: prepared, readBack: { ...current, ...prepared.proposedFields } }),
    (error) => error.code === "TRANSACTION_REQUIRED",
  );
  assert.throws(
    () => buildPatch({ ...input, transaction: patch.transaction }),
    (error) => error.code === fixture.expectedError && /Do not retry PATCH/.test(error.nextAction),
  );
});

test("audit receipt removes customer and connector content", () => {
  const fixture = loadFixture("privacy-redaction.json");
  const current = loadFixture("current-opportunity.json");
  const describe = loadFixture("describe-opportunity.json");
  const prepared = draft({
    opportunityId: current.Id,
    author: fixture.confirmedBy,
    date: "2026-05-20",
    current,
    generatedAt: "2026-05-20T14:00:00.000Z",
    content: { Metrics: fixture.customerNarrative },
  });
  const confirmation = confirmDraft(prepared, { confirmedBy: fixture.confirmedBy });
  const patch = buildPatch(safeBuildPayload(prepared, describe, {
    confirmation,
    connectionId: fixture.connectorId,
    now: "2026-05-20T14:01:00.000Z",
  }));
  patch.envelope.body = fixture.requestBody;
  const audit = receipt({ mode: "audit", draft: prepared, confirmation, patch });
  const serialized = JSON.stringify(audit);
  for (const literal of fixture.forbiddenAuditLiterals) {
    assert.equal(serialized.includes(literal), false, `audit leaked ${literal}`);
  }
  assert.equal(audit.privacy.customer_content_removed, true);
});

test("recovery uses read-back and never authorizes blind PATCH retry", () => {
  const fixture = loadFixture("recovery.json");
  const current = loadFixture("current-opportunity.json");
  const describe = loadFixture("describe-opportunity.json");
  const prepared = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-20",
    current,
    generatedAt: "2026-05-20T14:00:00.000Z",
    content: { NextStep: "Confirm procurement owner." },
  });
  const patch = buildPatch(safeBuildPayload(prepared, describe, { now: "2026-05-20T14:01:00.000Z" }));
  const matched = recover({
    draft: prepared,
    transaction: patch.transaction,
    checkedAt: fixture.checkedAt,
    readBack: { ...current, ...prepared.proposedFields },
  });
  assert.equal(matched.resolution, fixture.expectedMatchResolution);
  assert.equal(matched.patch_retry_allowed, fixture.patchRetryAllowed);

  const mismatch = recover({
    draft: prepared,
    transaction: patch.transaction,
    checkedAt: fixture.checkedAt,
    readBack: { ...current, ...fixture.mismatchedReadBack },
  });
  assert.equal(mismatch.resolution, fixture.expectedMismatchResolution);
  assert.equal(mismatch.read_retry_allowed, fixture.readRetryAllowed);
  assert.equal(mismatch.patch_retry_allowed, fixture.patchRetryAllowed);
  assert.equal(mismatch.transaction.state, "recovery_required");
});

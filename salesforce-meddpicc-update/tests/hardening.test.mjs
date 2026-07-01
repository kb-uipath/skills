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
  receipt,
  verify,
} from "../scripts/meddpicc.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const fixtureDir = path.join(__dirname, "fixtures");
const loadFixture = (name) => JSON.parse(fs.readFileSync(path.join(fixtureDir, name), "utf8"));

test("field-map JSON is the source for exported field definitions", () => {
  assert.equal(FIELD_MAP.targetConnector, "uipath-salesforce-sfdc");
  assert.equal(FIELD_DEFS.metrics.apiName, "Metrics__c");
  assert.equal(FIELD_DEFS.compellingEvent.routeTo, "Opportunity_Next_Steps__c");
});

test("unknown content keys fail loudly with structured error", () => {
  assert.throws(
    () => draft({
      opportunityId: "006Pa00000TNhhtIAD",
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

test("receipt redacts connection IDs and body while preserving user-facing fields", () => {
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
  const patch = buildPatch({
    draft: prepared,
    describe,
    connectionId: "conn-secret-123",
    now: "2026-05-20T14:01:00.000Z",
  });
  const generated = receipt({ draft: prepared, patch });
  assert.equal(generated.patch.connection, "[REDACTED]");
  assert.equal(generated.patch.body, "[REDACTED]");
  assert.equal(generated.opportunity.id, current.Id);
  assert.equal(Boolean(generated.proposedFields.Metrics__c), true);
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
    () => buildPatch({ draft: prepared, describe: { fields: [] }, connectionId: "conn-123", now: "2026-05-20T14:01:00.000Z" }),
    (error) => error.code === "SCHEMA_FIELD_MISSING" && error.field === "Metrics__c",
  );

  const blockedDescribe = {
    fields: describe.fields.map((field) => field.name === "Metrics__c" ? { ...field, updateable: false } : field),
  };
  assert.throws(
    () => buildPatch({ draft: prepared, describe: blockedDescribe, connectionId: "conn-123", now: "2026-05-20T14:01:00.000Z" }),
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
    () => buildPatch({ draft: prepared, describe, now: "2026-05-20T14:01:00.000Z" }),
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
      opportunity: { id: "006Pa00000TNhhtIAD", name: "Sensitive Opportunity" },
      readBackStatus: "all_matched",
      fieldsWritten: [{ field: "Metrics__c" }, { field: "NextStep" }],
      fieldsSkipped: [{ field: "Economic_Buyer__c" }],
      warnings: ["warning"],
      discrepancies: [],
    },
  };

  const telemetry = buildTelemetryPayload(payload);

  assert.deepEqual(telemetry, {
    oppId: "006Pa00000TNhhtIAD",
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
  const patch = buildPatch({
    draft: prepared,
    describe,
    connectionId: loadFixture("connection-lookup.json").id,
    now: "2026-05-19T15:01:00.000Z",
  });
  assert.deepEqual(Object.keys(JSON.parse(patch.envelope.body)).sort(), ["NextStep", "Opportunity_Next_Steps__c"]);
  const result = verify({
    draft: prepared,
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
    () => buildPatch({ draft: prepared, describe, connectionId: "conn-123", now: "2026-05-20T14:01:00.000Z" }),
    (error) => error.code === "INVALID_PICKLIST_VALUE" && error.field === "Competition__c",
  );
});

test("fixture e2e: verification mismatch is surfaced", () => {
  const current = loadFixture("current-opportunity.json");
  const prepared = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-20",
    current,
    content: { NextStep: "Confirm procurement owner." },
  });
  const result = verify({
    draft: prepared,
    response: loadFixture("patch-success.json"),
    readBack: { ...current, NextStep: "Different value" },
  });
  assert.equal(result.readBackStatus, "mismatch");
  assert.equal(result.discrepancies[0].field, "NextStep");
});

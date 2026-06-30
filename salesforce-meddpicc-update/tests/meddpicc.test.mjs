import test from "node:test";
import assert from "node:assert/strict";
import {
  buildPatch,
  draft,
  parseOpportunityId,
  verify,
} from "../scripts/meddpicc.mjs";

const describeResponse = {
  fields: [
    { name: "Metrics__c", type: "textarea", length: 32768, updateable: true },
    { name: "Economic_Buyer__c", type: "reference", length: 18, updateable: true, referenceTo: ["Contact"] },
    { name: "Required_Capabilities__c", type: "textarea", length: 10000, updateable: true },
    { name: "Decision_Process_Actual__c", type: "textarea", length: 32768, updateable: true },
    { name: "Paper_Process__c", type: "textarea", length: 32768, updateable: true },
    { name: "Pains_Challenges__c", type: "textarea", length: 32768, updateable: true },
    { name: "Champion_Actual__c", type: "reference", length: 18, updateable: true, referenceTo: ["Contact"] },
    {
      name: "Competition__c",
      type: "multipicklist",
      length: 4099,
      updateable: true,
      picklistValues: [
        { value: "Automation Anywhere", active: true },
        { value: "Blue Prism", active: true },
      ],
    },
    { name: "Competition_meddic__c", type: "textarea", length: 32768, updateable: true },
    { name: "NextStep", type: "string", length: 255, updateable: true },
    { name: "Opportunity_Next_Steps__c", type: "textarea", length: 32768, updateable: true },
  ],
};

const current = {
  Id: "006Pa00000TNhhtIAD",
  Name: "Selective Insurance",
  LastModifiedDate: "2026-05-19T14:30:00.000+0000",
  Metrics__c: "Existing metrics",
  Opportunity_Next_Steps__c: null,
};

test("parse-id accepts Lightning URL, embedded text, and rejects wrong object", () => {
  assert.equal(
    parseOpportunityId("https://uipath.lightning.force.com/lightning/r/Opportunity/006Pa00000TNhhtIAD/view").opportunityId,
    "006Pa00000TNhhtIAD",
  );
  assert.equal(parseOpportunityId("the opp is 006Pa00000TNhhtIAD").source, "embedded");
  assert.equal(parseOpportunityId("001Pa00000TNhhtIAD").valid, false);
});

test("draft appends dated text and skips duplicate content", () => {
  const first = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-19",
    current,
    generatedAt: "2026-05-19T15:00:00.000Z",
    content: { Metrics: "Reduce processing time by 30%." },
  });

  assert.equal(
    first.proposedFields.Metrics__c,
    "Existing metrics\n\n[2026-05-19 - Keith Born]\nReduce processing time by 30%.",
  );

  const duplicate = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-19",
    current: { ...current, Metrics__c: first.proposedFields.Metrics__c },
    content: { Metrics: "Reduce processing time by 30%." },
  });

  assert.deepEqual(duplicate.proposedFields, {});
  assert.equal(duplicate.skippedFields[0].reason, "duplicate_entry");
});

test("draft routes lookup narrative to Opportunity Next Steps", () => {
  const result = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-19",
    current,
    content: { Champion: "Maria is coaching us through legal and procurement." },
  });

  assert.equal(result.proposedFields.Champion_Actual__c, undefined);
  assert.match(result.proposedFields.Opportunity_Next_Steps__c, /CHAMPION STRATEGY/);
  assert.equal(result.skippedFields[0].field, "Champion_Actual__c");
});

test("draft truncates long NextStep values with warning", () => {
  const result = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-19",
    current,
    content: { NextStep: "x".repeat(300) },
  });

  assert.equal(result.proposedFields.NextStep.length, 255);
  assert.match(result.warnings[0], /truncated/);
});

test("build-patch validates describe metadata and JSON escapes multiline body", () => {
  const prepared = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-19",
    current,
    generatedAt: "2026-05-19T15:00:00.000Z",
    content: { Metrics: "Line one\nLine \"two\"" },
  });

  const result = buildPatch({
    draft: prepared,
    describe: describeResponse,
    connectionId: "conn-123",
    now: "2026-05-19T15:01:00.000Z",
  });

  assert.equal(result.requiresFreshRead, false);
  assert.equal(result.envelope.method, "PATCH");
  assert.equal(result.envelope.url, "/services/data/v60.0/sobjects/Opportunity/006Pa00000TNhhtIAD");
  assert.deepEqual(JSON.parse(result.envelope.body), result.salesforceBody);
});

test("build-patch rejects invalid multipicklist values", () => {
  const prepared = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-19",
    current,
    generatedAt: "2026-05-19T15:00:00.000Z",
    content: { Competition__c: "Unknown Vendor" },
  });

  assert.throws(
    () => buildPatch({ draft: prepared, describe: describeResponse, connectionId: "conn-123", now: "2026-05-19T15:01:00.000Z" }),
    /Invalid picklist value/,
  );
});

test("build-patch refuses stale drafts without emitting an envelope", () => {
  const prepared = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-19",
    current,
    generatedAt: "2026-05-19T15:00:00.000Z",
    content: { Metrics: "Reduce processing time by 30%." },
  });

  const result = buildPatch({
    draft: prepared,
    describe: describeResponse,
    connectionId: "conn-123",
    now: "2026-05-19T15:30:00.000Z",
  });

  assert.equal(result.requiresFreshRead, true);
  assert.equal(result.envelope, null);
});

test("verify reports matched fields and discrepancies", () => {
  const prepared = draft({
    opportunityId: current.Id,
    author: "Keith Born",
    date: "2026-05-19",
    current,
    content: { Metrics: "Reduce processing time by 30%." },
  });

  const matched = verify({
    draft: prepared,
    response: { code: 204 },
    readBack: { ...current, Metrics__c: prepared.proposedFields.Metrics__c },
  });
  assert.equal(matched.readBackStatus, "all_matched");

  const mismatch = verify({
    draft: prepared,
    response: { code: 204 },
    readBack: { ...current, Metrics__c: "different" },
  });
  assert.equal(mismatch.readBackStatus, "mismatch");
  assert.equal(mismatch.discrepancies[0].field, "Metrics__c");
});

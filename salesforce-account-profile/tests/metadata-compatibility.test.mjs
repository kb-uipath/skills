import assert from "node:assert/strict";
import test from "node:test";

import {
  inspectMetadataCompatibility,
} from "../scripts/metadata-compatibility.mjs";
import { DESCRIBE, MockClient } from "./helpers.mjs";

test("doctor metadata inspection verifies every required object without data queries", async () => {
  const client = new MockClient();
  const result = await inspectMetadataCompatibility(client);
  assert.equal(result.status, "compatible");
  assert.equal(
    result.field_map_version,
    "salesforce-account-profile-field-map/v1",
  );
  assert.deepEqual(
    result.objects.map((entry) => entry.object),
    Object.keys(DESCRIBE),
  );
  assert.equal(client.queryCount, 0);
  assert.ok(result.optional_warning_count > 0);
});

test("required type or filter drift fails metadata compatibility", async () => {
  const wrongType = new MockClient();
  wrongType.describe = async (objectName) => {
    const fields = await MockClient.prototype.describe.call(
      wrongType,
      objectName,
    );
    if (objectName === "Opportunity") {
      fields.set("CloseDate", {
        ...fields.get("CloseDate"),
        type: "string",
      });
    }
    return fields;
  };
  await assert.rejects(
    () => inspectMetadataCompatibility(wrongType),
    { code: "SCHEMA_FAILURE" },
  );

  const unfilterable = new MockClient();
  unfilterable.describe = async (objectName) => {
    const fields = await MockClient.prototype.describe.call(
      unfilterable,
      objectName,
    );
    if (objectName === "Account") {
      fields.set("ParentId", {
        ...fields.get("ParentId"),
        filterable: false,
      });
    }
    return fields;
  };
  await assert.rejects(
    () => inspectMetadataCompatibility(unfilterable),
    { code: "SCHEMA_FAILURE" },
  );
});

test("an incompatible optional family field is reported without inventing compatibility", async () => {
  const client = new MockClient();
  client.describe = async (objectName) => {
    const fields = await MockClient.prototype.describe.call(
      client,
      objectName,
    );
    if (objectName === "Account") {
      fields.set("Ultimate_Parent_name__c", {
        ...fields.get("Ultimate_Parent_name__c"),
        filterable: false,
      });
    }
    return fields;
  };
  const result = await inspectMetadataCompatibility(client);
  const account = result.objects.find((entry) =>
    entry.object === "Account");
  assert.deepEqual(
    account.optional_fields_incompatible,
    ["Ultimate_Parent_name__c"],
  );
  assert.equal(
    account.optional_fields_available.includes(
      "Ultimate_Parent_name__c",
    ),
    false,
  );
});

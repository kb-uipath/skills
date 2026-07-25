import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { FIELD_EXPECTATIONS, FIELD_POLICY } from "../scripts/workflow.mjs";

test("versioned field map stays in exact parity with runtime policy", async () => {
  const here = dirname(fileURLToPath(import.meta.url));
  const payload = JSON.parse(await readFile(join(here, "..", "references", "field-map.v1.json"), "utf8"));
  assert.equal(payload.schema_version, "salesforce-account-profile-field-map/v1");
  assert.deepEqual(payload.objects, FIELD_POLICY);
  assert.deepEqual(payload.semantic_expectations, FIELD_EXPECTATIONS);
});

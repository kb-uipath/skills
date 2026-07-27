import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  validatePreflightRequest,
  validateProfileRequest,
  validateRenderRequest,
  validateResolveRequest,
} from "../scripts/contracts.mjs";
import { validateReadPlan } from "../scripts/read-plan.mjs";

test("documented JSON request examples parse and satisfy current contracts", async () => {
  const here = dirname(fileURLToPath(import.meta.url));
  const markdown = await readFile(join(here, "..", "references", "contracts.md"), "utf8");
  const examples = [...markdown.matchAll(/```json\n([\s\S]*?)\n```/g)].map((match) => JSON.parse(match[1]));
  assert.equal(examples.length, 5);
  validatePreflightRequest(examples[0]);
  validateResolveRequest(examples[1]);
  validateProfileRequest(examples[2]);
  validateRenderRequest(examples[3]);
  validateReadPlan(examples[4]);
});

import assert from "node:assert/strict";
import { access } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import test from "node:test";

import { CONTRACTS } from "../scripts/constants.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const cli = join(here, "..", "scripts", "account-profile.mjs");
const fakeSf = join(here, "fixtures", "fake-sf");
const sentinel = join(process.cwd(), "CODE_EXECUTION_SENTINEL");

async function run(command, input) {
  return await new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [cli, command], {
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...process.env,
        NODE_ENV: "test",
        SALESFORCE_ACCOUNT_PROFILE_TEST_SF_PATH: fakeSf,
      },
    });
    const stdout = [];
    const stderr = [];
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.on("error", reject);
    child.on("close", (code) => {
      const output = Buffer.concat(stdout).toString("utf8");
      const error = Buffer.concat(stderr).toString("utf8");
      if (code !== 0) reject(new Error(`CLI failed (${code}): ${error}`));
      else resolve(JSON.parse(output));
    });
    child.stdin.end(JSON.stringify(input));
  });
}

async function staged(alias, selector) {
  const preflight = await run("preflight", {
    schema_version: CONTRACTS.preflightRequest,
    target_org: alias,
  });
  const resolved = await run("resolve", {
    schema_version: CONTRACTS.resolveRequest,
    target_org: alias,
    confirmed_org_digest: preflight.confirmed_org_digest,
    selector,
  });
  return { preflight, resolved };
}

test("fake-sf end to end builds a complete synthetic corporate-family profile", async () => {
  const { preflight, resolved } = await staged("synthetic-complete", { mode: "exact_name", value: "Example Holdings" });
  const base = {
    schema_version: CONTRACTS.profileRequest,
    target_org: "synthetic-complete",
    confirmed_org_digest: preflight.confirmed_org_digest,
    account_receipt: resolved.account_receipt,
    sections: ["overview", "family", "opportunities", "products", "team"],
    scope: "corporate_family",
    opportunity_scope: "all",
  };
  const stagedProfile = await run("profile", base);
  assert.equal(stagedProfile.status, "family_confirmation_required");
  const complete = await run("profile", {
    ...base,
    confirmed_family_digest: stagedProfile.family_confirmation.family_digest,
  });
  const rendered = await run("render", {
    schema_version: CONTRACTS.renderRequest,
    profile: complete,
  });
  assert.equal(complete.status, "complete");
  assert.equal(complete.accounts.length, 2);
  assert.equal(complete.opportunities.length, 2);
  assert.equal(complete.products.length, 2);
  assert.equal(complete.team.length, 2);
  assert(complete.warnings.includes("MULTICURRENCY_NO_AGGREGATION"));
  assert(rendered.markdown.includes("ANNUALIZATION\\_NOT\\_CERTIFIED"));
});

test("fake-sf end to end leaves an ambiguous account unselected", async () => {
  const { resolved } = await staged("synthetic-ambiguous", { mode: "exact_name", value: "Repeated Name" });
  assert.equal(resolved.status, "ambiguous");
  assert.equal(resolved.candidates.length, 2);
  assert.equal(resolved.account_receipt, undefined);
});

test("fake-sf end to end treats an adversarial account name as inert data", async () => {
  const malicious = "O'Brien `$(touch CODE_EXECUTION_SENTINEL)`\u202e\u001b[31m";
  const { resolved } = await staged("synthetic-adversarial", { mode: "exact_name", value: malicious });
  assert.equal(resolved.status, "selected");
  assert.equal(resolved.selected_account.Name.includes("\u202e"), false);
  await assert.rejects(() => access(sentinel));
});

test("fake-sf end to end warns when optional custom fields are absent", async () => {
  const { preflight, resolved } = await staged("synthetic-missing", { mode: "exact_name", value: "Example Holdings" });
  const result = await run("profile", {
    schema_version: CONTRACTS.profileRequest,
    target_org: "synthetic-missing",
    confirmed_org_digest: preflight.confirmed_org_digest,
    account_receipt: resolved.account_receipt,
  });
  assert.equal(result.status, "complete");
  assert(result.warnings.includes("OPTIONAL_FIELD_UNAVAILABLE:Account.Support_Status__c"));
  assert.equal("Support_Status__c" in result.selected_account, false);
});

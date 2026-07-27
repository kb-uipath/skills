import assert from "node:assert/strict";
import {
  access,
  mkdtemp,
  rm,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import test from "node:test";

import { CONTRACTS } from "../scripts/constants.mjs";
import {
  buildSandboxCertificationEvidence,
} from "../scripts/certification-evidence.mjs";
import { doctor } from "../scripts/orchestrator.mjs";
import { markSandboxReadCertified } from "../scripts/org-registry.mjs";
import { attestCertificationPackage } from "../scripts/package-attestation.mjs";
import { digest } from "../scripts/security.mjs";
import { SfClient } from "../scripts/sf-client.mjs";
import { createStateStore } from "../scripts/state-store.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const testCli = join(here, "fixtures", "run-cli.cjs");
const fakeSf = join(here, "fixtures", "fake-sf");
const sentinel = join(process.cwd(), "CODE_EXECUTION_SENTINEL");
const fixedNow = new Date("2030-01-01T00:00:00.000Z");
const runtimeDigest = digest({ test_runtime_path: fakeSf });

async function run(command, input, stateRoot) {
  return await new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [testCli, command], {
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...process.env,
        SFAP_TEST_NOW: fixedNow.toISOString(),
        SFAP_TEST_STATE_ROOT: stateRoot,
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

async function certifiedState(t, alias) {
  const stateRoot = await mkdtemp(join(tmpdir(), "sf-profile-cli-v1-"));
  t.after(async () => {
    await rm(stateRoot, { recursive: true, force: true });
  });
  const clientFactory = async (targetOrg) => new SfClient({
    commandSpec: {
      executable: fakeSf,
      fixedArgs: [],
      attestationDigest: runtimeDigest,
    },
    targetOrg,
  });
  const diagnosis = await doctor({
    schema_version: CONTRACTS.doctorRequest,
    target_org: alias,
    friendly_label: `Synthetic ${alias}`,
    environment: "sandbox",
  }, {
    stateRoot,
    clientFactory,
    now: () => new Date(fixedNow),
  });
  const store = createStateStore({
    stateRoot,
    now: () => new Date(fixedNow),
  });
  const registry = await store.readOrgRegistry();
  const packageAttestation = await attestCertificationPackage();
  const evidence = buildSandboxCertificationEvidence({
    orgFingerprint: registry.entries[0].org_fingerprint,
    runtimeAttestationDigest: runtimeDigest,
    packageDigest: packageAttestation.package_digest,
    metadataCompatibilityDigest: digest(
      diagnosis.metadata_compatibility,
    ),
    fixtureManifestDigest: "a".repeat(64),
    authorizationScopeDigest: "b".repeat(64),
    authorizationAssertionDigest: "c".repeat(64),
    queryCount: 1,
    startedAt: fixedNow,
    completedAt: fixedNow,
  });
  const certified = markSandboxReadCertified(registry.entries[0], {
    evidence,
    now: fixedNow,
  });
  await store.writeOrgRegistry({
    ...registry,
    entries: [certified],
  });
  return stateRoot;
}

async function staged(t, alias, selector) {
  const stateRoot = await certifiedState(t, alias);
  const preflight = await run("preflight", {
    schema_version: CONTRACTS.preflightRequest,
    target_org: alias,
  }, stateRoot);
  const resolved = await run("resolve", {
    schema_version: CONTRACTS.resolveRequest,
    target_org: alias,
    confirmed_org_digest: preflight.confirmed_org_digest,
    selector,
  }, stateRoot);
  return { preflight, resolved, stateRoot };
}

test("fake-sf end to end builds a complete synthetic corporate-family profile", async (t) => {
  const { preflight, resolved, stateRoot } = await staged(t, "synthetic-complete", { mode: "exact_name", value: "Example Holdings" });
  const base = {
    schema_version: CONTRACTS.profileRequest,
    target_org: "synthetic-complete",
    confirmed_org_digest: preflight.confirmed_org_digest,
    account_receipt: resolved.account_receipt,
    sections: ["overview", "family", "opportunities", "products", "team"],
    scope: "corporate_family",
    opportunity_scope: "all",
  };
  const stagedProfile = await run("profile", base, stateRoot);
  assert.equal(stagedProfile.status, "family_confirmation_required");
  const complete = await run("profile", {
    ...base,
    confirmed_family_digest: stagedProfile.family_confirmation.family_digest,
  }, stateRoot);
  const rendered = await run("render", {
    schema_version: CONTRACTS.renderRequest,
    profile: complete,
  }, stateRoot);
  assert.equal(complete.status, "complete");
  assert.equal(complete.accounts.length, 2);
  assert.equal(complete.opportunities.length, 2);
  assert.equal(complete.products.length, 2);
  assert.equal(complete.team.length, 2);
  assert(complete.warnings.includes("MULTICURRENCY_NO_AGGREGATION"));
  assert(rendered.markdown.includes(
    "Annualized revenue is not calculated because price basis, recurrence, and duration semantics are not certified.",
  ));
  assert.equal(
    rendered.markdown.includes("ANNUALIZATION_NOT_CERTIFIED"),
    false,
  );
});

test("fake-sf end to end leaves an ambiguous account unselected", async (t) => {
  const { resolved } = await staged(t, "synthetic-ambiguous", { mode: "exact_name", value: "Repeated Name" });
  assert.equal(resolved.status, "ambiguous");
  assert.equal(resolved.candidates.length, 2);
  assert.equal(resolved.account_receipt, undefined);
});

test("fake-sf end to end treats an adversarial account name as inert data", async (t) => {
  const malicious = "O'Brien `$(touch CODE_EXECUTION_SENTINEL)`\u202e\u001b[31m";
  const { resolved } = await staged(t, "synthetic-adversarial", { mode: "exact_name", value: malicious });
  assert.equal(resolved.status, "selected");
  assert.equal(resolved.selected_account.Name.includes("\u202e"), false);
  await assert.rejects(() => access(sentinel));
});

test("fake-sf end to end warns when optional custom fields are absent", async (t) => {
  const { preflight, resolved, stateRoot } = await staged(t, "synthetic-missing", { mode: "exact_name", value: "Example Holdings" });
  const result = await run("profile", {
    schema_version: CONTRACTS.profileRequest,
    target_org: "synthetic-missing",
    confirmed_org_digest: preflight.confirmed_org_digest,
    account_receipt: resolved.account_receipt,
  }, stateRoot);
  assert.equal(result.status, "complete");
  assert(result.warnings.includes("OPTIONAL_FIELD_UNAVAILABLE:Account.Support_Status__c"));
  assert.equal("Support_Status__c" in result.selected_account, false);
});

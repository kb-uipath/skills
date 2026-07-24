import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  chmod,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  realpath,
  rm,
  stat,
  symlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import {
  BLANK_TEMPLATE_PATH,
  DASHBOARD_SCHEMA_VERSION,
  EnricherError,
  applyProposal,
  assertAllowedSfArgs,
  assertBlankHealthTemplate,
  assertNoProtectedPathCollision,
  assertWritableTargets,
  buildAccountQuery,
  buildAssetQuery,
  buildProposal,
  classifyAssetCandidates,
  digestObject,
  extractAccountId,
  fetchSalesforceSnapshot,
  formatPercent,
  loadDashboardInput,
  resolveOrg,
  runSf,
  validateDashboardInput,
  verifyFreshness,
  writeProtectedJson,
  writeProtectedJsonPairAtomic,
} from "./day2-enricher-lib.mjs";

const TEST_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
const CLI_PATH = path.join(TEST_DIRECTORY, "enrich-day2.mjs");

const FIELD_MAP = {
  version: "salesforce-day2-field-map/v1",
  dashboardSchemaVersion: "1.4",
  account: {
    requiredFields: ["Id", "Name", "LastModifiedDate"],
    optionalFields: [
      "Segmentation_CS_3_0__c",
      "Region__c",
      "Earliest_Renewal_Expiry_Date__c",
      "Utilization_Users__c",
      "Utilization_Robots__c",
      "Utilization_Consumables__c",
      "Health_Score_Label__c",
      "Last_QBR__c",
      "Last_EBC__c",
    ],
  },
  assets: {
    directCandidateFields: [
      "Id",
      "Product2Id",
      "Quantity",
      "CurrentQuantity",
      "UsageEndDate",
      "CurrentLifecycleEndDate",
      "LifecycleEndDate",
      "End_Date__c",
      "SBQQ__SubscriptionStartDate__c",
      "SBQQ__SubscriptionEndDate__c",
    ],
    productCandidateFields: ["Name", "Family"],
    endDatePrecedence: [
      "CurrentLifecycleEndDate",
      "LifecycleEndDate",
      "UsageEndDate",
      "End_Date__c",
      "SBQQ__SubscriptionEndDate__c",
    ],
  },
};

function syntheticAccount(overrides = {}) {
  return {
    Id: "001000000000000AAA",
    Name: "Synthetic Customer",
    LastModifiedDate: "2026-07-22T15:30:00.000+0000",
    Segmentation_CS_3_0__c: "Enterprise",
    Region__c: "Public Sector",
    Earliest_Renewal_Expiry_Date__c: "2027-06-30",
    Utilization_Users__c: "125.50",
    Utilization_Robots__c: 0,
    Utilization_Consumables__c: null,
    Health_Score_Label__c: "Green",
    Last_QBR__c: "2026-03-10",
    Last_EBC__c: "2026-05-20",
    ...overrides,
  };
}

async function blankDashboard() {
  return (await loadDashboardInput()).value;
}

function operation(proposal, targetPath) {
  return proposal.operations.find((item) => item.targetPath === targetPath);
}

test("accepts only strict Account IDs and Account Lightning URLs", () => {
  assert.equal(extractAccountId("001000000000000"), "001000000000000");
  assert.equal(extractAccountId("001000000000000AAA"), "001000000000000AAA");
  assert.equal(
    extractAccountId("https://example.my.salesforce.com/lightning/r/Account/001000000000000AAA/view"),
    "001000000000000AAA",
  );
  assert.throws(() => extractAccountId("Synthetic Customer"), { code: "INVALID_ACCOUNT" });
  assert.throws(() => extractAccountId("006000000000000AAA"), { code: "INVALID_ACCOUNT" });
  assert.throws(
    () => extractAccountId("https://example.my.salesforce.com/lightning/r/Opportunity/001000000000000AAA/view"),
    { code: "INVALID_ACCOUNT" },
  );
  assert.throws(
    () => extractAccountId("http://example.my.salesforce.com/lightning/r/Account/001000000000000AAA/view"),
    { code: "INVALID_ACCOUNT" },
  );
  assert.throws(
    () => extractAccountId("https://not-salesforce.example/lightning/r/Account/001000000000000AAA/view"),
    { code: "INVALID_ACCOUNT" },
  );
});

test("formats supplied numeric percentages without calculating or clamping", () => {
  assert.equal(formatPercent("125.50"), "125.50%");
  assert.equal(formatPercent(240), "240%");
  assert.equal(formatPercent(0), "0%");
  assert.equal(formatPercent("-1.5"), "-1.5%");
  assert.equal(formatPercent(null), null);
  assert.equal(formatPercent("not numeric"), null);
  assert.equal(formatPercent(Number.POSITIVE_INFINITY), null);
});

test("bundled schema 1.4 template has explicit blank health and no starter consumption rows", async () => {
  const input = await loadDashboardInput();
  assert.equal(input.path, BLANK_TEMPLATE_PATH);
  assert.equal(input.value.schemaVersion, DASHBOARD_SCHEMA_VERSION);
  assert.equal(assertBlankHealthTemplate(input.value), true);
  assert.deepEqual(input.value.consumptionPlan.groups, []);
  assert.equal(Object.keys(input.value.health).length, 9);
});

test("maps only exact-safe fields and preserves values over 100 percent", async () => {
  const base = await blankDashboard();
  const proposal = buildProposal(syntheticAccount(), base);

  assert.equal(operation(proposal, "customerName").proposedValue, "Synthetic Customer");
  assert.equal(operation(proposal, "segment").proposedValue, "Enterprise | Public Sector");
  assert.equal(operation(proposal, "renewalDate").proposedValue, "2027-06-30");
  assert.equal(operation(proposal, "metrics.utilization.users").proposedValue, "125.50%");
  assert.equal(operation(proposal, "metrics.utilization.robots").proposedValue, "0%");
  assert.equal(operation(proposal, "metrics.utilization.consumables"), undefined);
  assert.equal(operation(proposal, "health.overall.status").proposedValue, "Green");
  assert.match(operation(proposal, "health.overall.evidence").proposedValue, /Health_Score_Label__c/);
  assert.deepEqual(operation(proposal, "executiveCadence").proposedValue, {
    type: "lastEbc",
    date: "2026-05-20",
  });

  const built = applyProposal(base, syntheticAccount(), proposal, [], FIELD_MAP.version);
  assert.equal(built.dashboard.currentArr, "");
  assert.equal(built.dashboard.motion, "");
  assert.equal(built.dashboard.soldProducts, "");
  assert.equal(built.dashboard.statusSummary, "");
  assert.deepEqual(built.dashboard.consumptionPlan.groups, []);
  assert.equal(built.dashboard.metrics.utilization.users, "125.50%");
  assert.equal(built.dashboard.timeline.length, 2);
});

test("skips nulls, invalid dates, nonnumeric utilization, and Yellow health", async () => {
  const base = await blankDashboard();
  const proposal = buildProposal(
    syntheticAccount({
      Earliest_Renewal_Expiry_Date__c: "06/30/2027",
      Utilization_Users__c: null,
      Utilization_Robots__c: "high",
      Health_Score_Label__c: "Yellow",
      Last_QBR__c: null,
      Last_EBC__c: "not-a-date",
    }),
    base,
  );
  assert.equal(operation(proposal, "renewalDate"), undefined);
  assert.equal(operation(proposal, "metrics.utilization.users"), undefined);
  assert.equal(operation(proposal, "metrics.utilization.robots"), undefined);
  assert.equal(operation(proposal, "health.overall.status"), undefined);
  assert.equal(operation(proposal, "executiveCadence"), undefined);
  assert.ok(proposal.warnings.some((warning) => warning.includes("Yellow")));
});

test("uses the newest cadence date and deterministically prefers Last EBC on a tie", async () => {
  const base = await blankDashboard();
  const laterQbr = buildProposal(
    syntheticAccount({ Last_QBR__c: "2026-06-01", Last_EBC__c: "2026-05-31" }),
    base,
  );
  assert.deepEqual(operation(laterQbr, "executiveCadence").proposedValue, {
    type: "lastQbr",
    date: "2026-06-01",
  });

  const tie = buildProposal(
    syntheticAccount({ Last_QBR__c: "2026-06-01", Last_EBC__c: "2026-06-01" }),
    base,
  );
  assert.deepEqual(operation(tie, "executiveCadence").proposedValue, {
    type: "lastEbc",
    date: "2026-06-01",
  });

  const selectedBlankDate = await blankDashboard();
  selectedBlankDate.executiveCadence = { type: "nextEbc", date: "" };
  const selectedProposal = buildProposal(syntheticAccount(), selectedBlankDate);
  assert.equal(operation(selectedProposal, "executiveCadence").action, "conflict");
  const preserved = applyProposal(
    selectedBlankDate,
    syntheticAccount(),
    selectedProposal,
    [],
    FIELD_MAP.version,
  );
  assert.deepEqual(preserved.dashboard.executiveCadence, { type: "nextEbc", date: "" });
});

test("de-duplicates timeline events and provenance blocks", async () => {
  const base = await blankDashboard();
  const account = syntheticAccount();
  const firstProposal = buildProposal(account, base);
  const first = applyProposal(base, account, firstProposal, [], FIELD_MAP.version);
  const secondProposal = buildProposal(account, first.dashboard);
  const second = applyProposal(first.dashboard, account, secondProposal, [], FIELD_MAP.version);

  assert.equal(first.dashboard.timeline.length, 2);
  assert.equal(second.dashboard.timeline.length, 2);
  assert.equal(first.provenanceAdded, true);
  assert.equal(second.provenanceAdded, false);
  assert.equal(
    second.dashboard.sourceNotes.split("[Salesforce provenance:").length - 1,
    1,
  );
});

test("updates an existing provenance block when a later build approves another source field", async () => {
  const base = await blankDashboard();
  base.segment = "Existing segment";
  const account = syntheticAccount();
  const firstProposal = buildProposal(account, base);
  const first = applyProposal(base, account, firstProposal, [], FIELD_MAP.version);
  assert.equal(first.dashboard.sourceNotes.includes("Account.Segmentation_CS_3_0__c"), false);

  const secondProposal = buildProposal(account, first.dashboard);
  const second = applyProposal(
    first.dashboard,
    account,
    secondProposal,
    ["segment"],
    FIELD_MAP.version,
  );
  assert.equal(second.provenanceAdded, false);
  assert.equal(second.provenanceUpdated, true);
  assert.match(second.dashboard.sourceNotes, /Account\.Segmentation_CS_3_0__c/);
  assert.match(second.dashboard.sourceNotes, /Account\.Region__c/);
  assert.equal(second.dashboard.sourceNotes.split("[Salesforce provenance:").length - 1, 1);
});

test("fills blanks, preserves conflicts, and permits only path-specific conflict approval", async () => {
  const base = await blankDashboard();
  base.segment = "Existing segment";
  base.metrics.utilization.users = "80%";
  const account = syntheticAccount();
  const proposal = buildProposal(account, base);
  assert.equal(operation(proposal, "segment").action, "conflict");
  assert.equal(operation(proposal, "metrics.utilization.users").action, "conflict");

  const preserved = applyProposal(base, account, proposal, [], FIELD_MAP.version);
  assert.equal(preserved.dashboard.segment, "Existing segment");
  assert.equal(preserved.dashboard.metrics.utilization.users, "80%");
  assert.deepEqual(
    preserved.unresolvedConflicts.sort(),
    ["metrics.utilization.users", "segment"],
  );

  const approvedOne = applyProposal(base, account, proposal, ["segment"], FIELD_MAP.version);
  assert.equal(approvedOne.dashboard.segment, "Enterprise | Public Sector");
  assert.equal(approvedOne.dashboard.metrics.utilization.users, "80%");
  assert.throws(
    () => applyProposal(base, account, proposal, ["renewalDate"], FIELD_MAP.version),
    { code: "INVALID_APPROVAL" },
  );
});

test("does not add contradictory health evidence when health status conflict is preserved", async () => {
  const base = await blankDashboard();
  base.health.overall.status = "Green";
  base.health.overall.evidence = "";
  const account = syntheticAccount({ Health_Score_Label__c: "Red" });
  const proposal = buildProposal(account, base);

  const preserved = applyProposal(base, account, proposal, [], FIELD_MAP.version);
  assert.equal(preserved.dashboard.health.overall.status, "Green");
  assert.equal(preserved.dashboard.health.overall.evidence, "");

  const accepted = applyProposal(
    base,
    account,
    proposal,
    ["health.overall.status"],
    FIELD_MAP.version,
  );
  assert.equal(accepted.dashboard.health.overall.status, "Red");
  assert.match(accepted.dashboard.health.overall.evidence, /Health_Score_Label__c = "Red"/);
});

test("customer name mismatch is a hard stop and cannot become a conflict", async () => {
  const base = await blankDashboard();
  base.customerName = "Different Customer";
  assert.throws(() => buildProposal(syntheticAccount(), base), {
    code: "CUSTOMER_NAME_MISMATCH",
  });
  base.customerName = "Synthetic Customer ";
  assert.throws(() => buildProposal(syntheticAccount(), base), {
    code: "CUSTOMER_NAME_MISMATCH",
  });
});

test("rejects dashboard schema mismatches instead of migrating", () => {
  assert.throws(() => validateDashboardInput({ schemaVersion: "1.3" }), {
    code: "SCHEMA_MISMATCH",
  });
  assert.throws(() => validateDashboardInput({ schemaVersion: "1.4" }), {
    code: "INVALID_INPUT_SHAPE",
  });
});

test("rejects preview-only or candidate keys from dashboard JSON", async () => {
  const base = await blankDashboard();
  assert.equal(validateDashboardInput(base).schemaVersion, "1.4");
  assert.throws(
    () => validateDashboardInput({ ...base, productCandidates: [{ productName: "Must not survive" }] }),
    { code: "INVALID_INPUT_SHAPE" },
  );
  assert.throws(
    () =>
      validateDashboardInput({
        ...base,
        executiveCadence: { type: "nextQbr", date: "not-a-date" },
      }),
    { code: "INVALID_INPUT_SHAPE" },
  );
  assert.throws(
    () =>
      validateDashboardInput({
        ...base,
        relationships: [{
          hierarchyOrder: 1.5,
          uipathName: "",
          uipathRole: "",
          customerName: "",
          customerRole: "",
          note: "",
        }],
      }),
    { code: "INVALID_INPUT_SHAPE" },
  );
  assert.throws(
    () =>
      validateDashboardInput({
        ...base,
        sources: [{
          name: "",
          size: -1,
          type: "",
          kind: "attached, not extracted",
          text: "",
          warning: "",
        }],
      }),
    { code: "INVALID_INPUT_SHAPE" },
  );
});

test("detects stale Salesforce reads, field maps, Assets, and changed input JSON", () => {
  const emptyCandidateDigest = digestObject([]);
  const preview = {
    fieldMap: { version: "v1", digest: "map-a" },
    input: { digest: "input-a" },
    productCandidates: [],
    source: {
      accountLastModifiedDate: "2026-01-01T00:00:00.000+0000",
      accountDigest: "account-a",
      assetDigest: "asset-a",
      productCandidateDigest: emptyCandidateDigest,
      classificationAsOf: "2026-07-23",
      selectedAccountFields: ["Id", "Name", "LastModifiedDate"],
      missingOptionalAccountFields: [],
      assetQueryFields: ["Id"],
      assetWarnings: [],
    },
  };
  const current = {
    fieldMapVersion: "v1",
    fieldMapDigest: "map-a",
    inputDigest: "input-a",
    accountLastModifiedDate: "2026-01-01T00:00:00.000+0000",
    accountDigest: "account-a",
    assetDigest: "asset-a",
    productCandidateDigest: emptyCandidateDigest,
    classificationAsOf: "2026-07-23",
    selectedAccountFields: ["Id", "Name", "LastModifiedDate"],
    missingOptionalAccountFields: [],
    assetQueryFields: ["Id"],
    assetWarnings: [],
  };
  assert.equal(verifyFreshness(preview, current), true);
  assert.throws(() => verifyFreshness(preview, { ...current, inputDigest: "input-b" }), {
    code: "STALE_PREVIEW",
  });
  assert.throws(
    () => verifyFreshness(preview, { ...current, accountLastModifiedDate: "changed" }),
    { code: "STALE_PREVIEW" },
  );
  assert.throws(() => verifyFreshness(preview, { ...current, assetDigest: "asset-b" }), {
    code: "STALE_PREVIEW",
  });
  assert.throws(() => verifyFreshness(preview, { ...current, fieldMapVersion: "v2" }), {
    code: "STALE_PREVIEW",
  });
  assert.throws(() => verifyFreshness(preview, { ...current, classificationAsOf: "2026-07-24" }), {
    code: "STALE_PREVIEW",
  });
});

test("dynamically skips missing optional fields but stops on missing required Account fields", () => {
  const available = new Set(["Id", "Name", "LastModifiedDate", "Region__c"]);
  const query = buildAccountQuery("001000000000000AAA", available, FIELD_MAP);
  assert.match(query.soql, /^SELECT Id, Name, LastModifiedDate, Region__c FROM Account /);
  assert.ok(query.missingOptionalFields.includes("Health_Score_Label__c"));
  assert.throws(
    () => buildAccountQuery("001000000000000AAA", new Set(["Id", "LastModifiedDate"]), FIELD_MAP),
    { code: "MISSING_REQUIRED_FIELD" },
  );
});

test("Asset query is purchased-only and candidates remain manual-review data", async () => {
  const assetFields = new Set([
    "Id",
    "AccountId",
    "Status",
    "Product2Id",
    "Quantity",
    "UsageEndDate",
  ]);
  const productFields = new Set(["Name", "Family"]);
  const query = buildAssetQuery("001000000000000AAA", assetFields, productFields, FIELD_MAP);
  assert.match(query.soql, /Status = 'Purchased'/);
  assert.match(query.soql, /Product2\.Name/);
  assert.doesNotMatch(query.soql, /\bUPDATE\b|\bDELETE\b|\bINSERT\b/i);

  const candidates = classifyAssetCandidates(
    [
      { Id: "a1", Product2: { Name: "A", Family: "F" }, Quantity: 2, UsageEndDate: "2027-01-01" },
      { Id: "a2", Product2: { Name: "B" }, UsageEndDate: "2025-01-01" },
      { Id: "a3", Product2: { Name: "C" }, CurrentLifecycleEndDate: "2027-08-01T00:00:00.000+0000" },
      { Id: "a4", Product2: { Name: "D" } },
    ],
    "2026-07-23",
    FIELD_MAP.assets.endDatePrecedence,
  );
  assert.deepEqual(candidates.map((candidate) => candidate.classification), [
    "dated-current",
    "expired",
    "dated-current",
    "undated",
  ]);
  assert.equal(candidates[2].classificationDateOnly, "2027-08-01");
  assert.ok(candidates.every((candidate) => candidate.manualReviewOnly));

  const base = await blankDashboard();
  const account = syntheticAccount();
  const proposal = buildProposal(account, base);
  const built = applyProposal(base, account, proposal, [], FIELD_MAP.version);
  assert.equal(built.dashboard.soldProducts, "");
  assert.deepEqual(built.dashboard.consumptionPlan.groups, []);
  assert.equal(JSON.stringify(built.dashboard).includes("manualReviewOnly"), false);
});

test("Salesforce CLI allowlist permits only display, describe, and query", () => {
  assert.equal(assertAllowedSfArgs(["org", "display", "--json"]), true);
  assert.equal(assertAllowedSfArgs(["sobject", "describe", "--sobject", "Account", "--json"]), true);
  assert.equal(assertAllowedSfArgs(["data", "query", "--query", "SELECT Id FROM Account", "--json"]), true);
  for (const args of [
    ["data", "update", "record"],
    ["data", "delete", "record"],
    ["data", "upsert", "bulk"],
    ["apex", "run"],
    ["org", "open"],
  ]) {
    assert.throws(() => assertAllowedSfArgs(args), { code: "UNSAFE_SF_COMMAND" });
  }
});

test("Salesforce CLI/auth process failures stop without falling back", () => {
  assert.throws(
    () => runSf(["org", "display", "--json"], { sfBinary: "/definitely/not/a/salesforce-cli" }),
    { code: "SF_CLI_FAILURE" },
  );
});

test("Salesforce CLI calls time out and redact credential-like error details", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "salesforce-day2-cli-"));
  const timeoutCli = path.join(directory, "sf-timeout");
  const secretCli = path.join(directory, "sf-secret");
  try {
    await writeFile(
      timeoutCli,
      "#!/usr/bin/env node\nsetTimeout(() => {}, 5000);\n",
      { encoding: "utf8", mode: 0o700 },
    );
    assert.throws(
      () => runSf(
        ["org", "display", "--json"],
        { sfBinary: timeoutCli, timeoutMs: 50 },
      ),
      (error) =>
        error instanceof EnricherError &&
        error.code === "SF_CLI_FAILURE" &&
        !error.message.includes("undefined"),
    );

    await writeFile(
      secretCli,
      [
        "#!/usr/bin/env node",
        "process.stdout.write(JSON.stringify({",
        "  status: 1,",
        '  message: "password=super-secret token=private-token Authorization: Bearer abcdefghijklmnop"',
        "}));",
        "",
      ].join("\n"),
      { encoding: "utf8", mode: 0o700 },
    );
    assert.throws(
      () => runSf(["org", "display", "--json"], { sfBinary: secretCli }),
      (error) =>
        error instanceof EnricherError &&
        error.code === "SF_CLI_FAILURE" &&
        !/super-secret|private-token|abcdefghijklmnop/u.test(error.message) &&
        /credential detail removed/u.test(error.message),
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("org resolution uses an explicit org or the CLI default and never injects an alias", () => {
  const calls = [];
  const runner = (args) => {
    calls.push(args);
    return { username: "user@example.com", id: "00D000000000001", alias: "configured" };
  };
  const defaultOrg = resolveOrg(undefined, runner);
  assert.equal(defaultOrg.targetOrg, "user@example.com");
  assert.deepEqual(calls[0], ["org", "display", "--json"]);

  resolveOrg("explicit-org", runner);
  assert.deepEqual(calls[1], ["org", "display", "--target-org", "explicit-org", "--json"]);
});

test("snapshot generation uses only allowlisted commands and tolerates missing optional fields", () => {
  const calls = [];
  const accountFields = FIELD_MAP.account.requiredFields.map((name) => ({ name }));
  accountFields.push({ name: "Region__c" });
  const assetFields = ["Id", "AccountId", "Status", "Product2Id", "Quantity", "UsageEndDate"].map(
    (name) => ({ name }),
  );
  const productFields = ["Name", "Family"].map((name) => ({ name }));
  const runner = (args) => {
    calls.push(args);
    assertAllowedSfArgs(args);
    if (args[0] === "sobject" && args.includes("Account")) return { fields: accountFields };
    if (args[0] === "sobject" && args.includes("Asset")) return { fields: assetFields };
    if (args[0] === "sobject" && args.includes("Product2")) return { fields: productFields };
    if (args[0] === "data" && args[args.indexOf("--query") + 1].includes("FROM Account")) {
      return {
        totalSize: 1,
        records: [
          {
            Id: "001000000000000AAA",
            Name: "Synthetic Customer",
            LastModifiedDate: "2026-07-22T15:30:00.000+0000",
            Region__c: "Public Sector",
          },
        ],
      };
    }
    return {
      totalSize: 1,
      records: [
        {
          Id: "02i000000000001AAA",
          Product2Id: "01t000000000001AAA",
          Product2: { Name: "Synthetic Product", Family: "Synthetic Family" },
          Quantity: 5,
          UsageEndDate: "2027-01-01",
        },
      ],
    };
  };

  const snapshot = fetchSalesforceSnapshot(
    "001000000000000AAA",
    "user@example.com",
    FIELD_MAP,
    { runner, asOfDate: "2026-07-23" },
  );
  assert.equal(snapshot.productCandidates.length, 1);
  assert.equal(snapshot.productCandidates[0].productName, "Synthetic Product");
  assert.ok(snapshot.missingOptionalAccountFields.includes("Health_Score_Label__c"));
  assert.ok(calls.every((args) => ["org display", "sobject describe", "data query"].includes(`${args[0]} ${args[1]}`)));
});

test("Asset or Product2 CLI failures stop the snapshot instead of creating a false zero-candidate result", () => {
  const accountFields = FIELD_MAP.account.requiredFields.map((name) => ({ name }));
  const runner = (args) => {
    if (args[0] === "sobject" && args.includes("Account")) return { fields: accountFields };
    if (args[0] === "data" && args[args.indexOf("--query") + 1].includes("FROM Account")) {
      return {
        totalSize: 1,
        records: [{
          Id: "001000000000000AAA",
          Name: "Synthetic Customer",
          LastModifiedDate: "2026-07-22T15:30:00.000+0000",
        }],
      };
    }
    throw new EnricherError("SF_CLI_FAILURE", "Synthetic Asset access failure.");
  };
  assert.throws(
    () =>
      fetchSalesforceSnapshot(
        "001000000000000AAA",
        "synthetic@example.com",
        FIELD_MAP,
        { runner, asOfDate: "2026-07-23" },
      ),
    { code: "SF_CLI_FAILURE" },
  );
});

test("runs preview and build end to end against a synthetic sf CLI fixture", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "salesforce-day2-e2e-"));
  const binDirectory = path.join(directory, "bin");
  const outputDirectory = path.join(directory, "output");
  const fakeSfPath = path.join(binDirectory, "sf");
  await mkdir(binDirectory, { recursive: true });
  const fakeSf = `#!/usr/bin/env node
const args = process.argv.slice(2);
const ok = (result) => process.stdout.write(JSON.stringify({ status: 0, result }));
if (args[0] === "org" && args[1] === "display") {
  ok({ username: "synthetic@example.com", id: "00D000000000001", alias: "synthetic-org" });
} else if (args[0] === "sobject" && args[1] === "describe") {
  const name = args[args.indexOf("--sobject") + 1];
  if (name === "Account") {
    ok({ fields: ${JSON.stringify(FIELD_MAP.account.requiredFields.concat(FIELD_MAP.account.optionalFields).map((name) => ({ name })))} });
  } else if (name === "Asset") {
    ok({ fields: ${JSON.stringify(["Id", "AccountId", "Status", ...FIELD_MAP.assets.directCandidateFields].map((name) => ({ name })))} });
  } else if (name === "Product2") {
    ok({ fields: [{ name: "Name" }, { name: "Family" }] });
  } else process.exit(2);
} else if (args[0] === "data" && args[1] === "query") {
  const query = args[args.indexOf("--query") + 1];
  if (query.includes("FROM Account")) {
    const account = ${JSON.stringify(syntheticAccount())};
    if (process.env.SF_FAKE_STALE === "1") {
      account.LastModifiedDate = "2026-07-24T15:30:00.000+0000";
    }
    if (process.env.SF_FAKE_FORMULA_DRIFT === "1") {
      account.Utilization_Users__c = "126.50";
    }
    ok({ totalSize: 1, records: [account] });
  } else if (query.includes("FROM Asset")) {
    ok({ totalSize: 1, records: [{
      Id: "02i000000000001AAA",
      Product2Id: "01t000000000001AAA",
      Product2: { Name: "Manual Candidate Product", Family: "Synthetic" },
      Quantity: 5,
      CurrentQuantity: 4,
      UsageEndDate: "2027-01-01"
    }] });
  } else process.exit(3);
} else process.exit(4);
`;
  try {
    await writeFile(fakeSfPath, fakeSf, { mode: 0o700 });
    await chmod(fakeSfPath, 0o700);
    const environment = {
      ...process.env,
      PATH: `${binDirectory}${path.delimiter}${process.env.PATH}`,
    };
    const previewRun = spawnSync(
      process.execPath,
      [
        CLI_PATH,
        "preview",
        "--account",
        "001000000000000AAA",
        "--target-org",
        "synthetic-org",
        "--output-dir",
        outputDirectory,
      ],
      { encoding: "utf8", shell: false, env: environment },
    );
    assert.equal(previewRun.status, 0, previewRun.stderr);

    const previewPath = path.join(outputDirectory, "synthetic-customer-day2-preview.json");
    const preview = JSON.parse(await readFile(previewPath, "utf8"));
    assert.equal(preview.kind, "salesforce-day2-preview/v1");
    assert.equal(preview.productCandidates.length, 1);

    const redirectedPreviewPath = path.join(outputDirectory, "redirected-preview.json");
    await writeFile(
      redirectedPreviewPath,
      JSON.stringify({ ...preview, outputDirectory: path.join(directory, "redirected") }),
      { encoding: "utf8", mode: 0o600 },
    );
    const redirectedBuild = spawnSync(
      process.execPath,
      [CLI_PATH, "build", "--preview", redirectedPreviewPath],
      { encoding: "utf8", shell: false, env: environment },
    );
    assert.notEqual(redirectedBuild.status, 0);
    assert.match(redirectedBuild.stderr, /INVALID_PREVIEW/);

    const candidateTamperPath = path.join(outputDirectory, "candidate-tamper-preview.json");
    const candidateTamper = structuredClone(preview);
    candidateTamper.productCandidates[0].productName = "Tampered Product";
    await writeFile(candidateTamperPath, JSON.stringify(candidateTamper), {
      encoding: "utf8",
      mode: 0o600,
    });
    const candidateTamperBuild = spawnSync(
      process.execPath,
      [CLI_PATH, "build", "--preview", candidateTamperPath],
      { encoding: "utf8", shell: false, env: environment },
    );
    assert.notEqual(candidateTamperBuild.status, 0);
    assert.match(candidateTamperBuild.stderr, /PREVIEW_TAMPERED/);

    const decoyInputPath = path.join(directory, "byte-identical-decoy.json");
    await writeFile(decoyInputPath, await readFile(preview.input.path), { mode: 0o600 });
    const inputPathTamperPath = path.join(outputDirectory, "input-path-tamper-preview.json");
    const inputPathTamper = structuredClone(preview);
    inputPathTamper.input.path = decoyInputPath;
    await writeFile(inputPathTamperPath, JSON.stringify(inputPathTamper), {
      encoding: "utf8",
      mode: 0o600,
    });
    const inputPathTamperBuild = spawnSync(
      process.execPath,
      [CLI_PATH, "build", "--preview", inputPathTamperPath, "--overwrite"],
      { encoding: "utf8", shell: false, env: environment },
    );
    assert.notEqual(inputPathTamperBuild.status, 0);
    assert.match(inputPathTamperBuild.stderr, /PREVIEW_TAMPERED/);

    const buildRun = spawnSync(
      process.execPath,
      [CLI_PATH, "build", "--preview", previewPath],
      { encoding: "utf8", shell: false, env: environment },
    );
    assert.equal(buildRun.status, 0, buildRun.stderr);

    const dashboardPath = path.join(outputDirectory, "synthetic-customer-day2-dashboard.json");
    const reportPath = path.join(outputDirectory, "synthetic-customer-day2-mapping-report.json");
    const dashboardText = await readFile(dashboardPath, "utf8");
    const dashboard = JSON.parse(dashboardText);
    const report = JSON.parse(await readFile(reportPath, "utf8"));
    await assert.rejects(() => readFile(previewPath, "utf8"), { code: "ENOENT" });
    assert.equal(dashboard.customerName, "Synthetic Customer");
    assert.equal(dashboard.soldProducts, "");
    assert.deepEqual(dashboard.consumptionPlan.groups, []);
    assert.equal(dashboardText.includes("Manual Candidate Product"), false);
    assert.equal(report.productCandidates[0].productName, "Manual Candidate Product");

    const revalidationPath = path.join(
      outputDirectory,
      "synthetic-customer-day2-salesforce-revalidation.json",
    );
    const revalidationRun = spawnSync(
      process.execPath,
      [
        CLI_PATH,
        "revalidate",
        "--report",
        reportPath,
        "--output",
        revalidationPath,
      ],
      { encoding: "utf8", shell: false, env: environment },
    );
    assert.equal(revalidationRun.status, 0, revalidationRun.stderr);
    const revalidation = JSON.parse(await readFile(revalidationPath, "utf8"));
    const revalidationSchema = JSON.parse(
      await readFile(
        path.join(
          TEST_DIRECTORY,
          "..",
          "references",
          "salesforce-revalidation.schema.json",
        ),
        "utf8",
      ),
    );
    assert.equal(revalidation.kind, "salesforce-day2-revalidation/v1");
    assert.equal(revalidation.accountId, "001000000000000AAA");
    assert.equal(revalidation.mappingReport.path, await realpath(reportPath));
    assert.deepEqual(
      Object.keys(revalidation).sort(),
      [...revalidationSchema.required].sort(),
    );
    assert.deepEqual(
      Object.keys(revalidation.source).sort(),
      [...revalidationSchema.properties.source.required].sort(),
    );

    const staleRevalidationRun = spawnSync(
      process.execPath,
      [
        CLI_PATH,
        "revalidate",
        "--report",
        reportPath,
        "--output",
        path.join(outputDirectory, "stale-revalidation.json"),
      ],
      {
        encoding: "utf8",
        shell: false,
        env: { ...environment, SF_FAKE_STALE: "1" },
      },
    );
    assert.notEqual(staleRevalidationRun.status, 0);
    assert.match(staleRevalidationRun.stderr, /STALE_SALESFORCE/u);

    const formulaDriftRun = spawnSync(
      process.execPath,
      [
        CLI_PATH,
        "revalidate",
        "--report",
        reportPath,
        "--output",
        path.join(outputDirectory, "formula-drift-revalidation.json"),
      ],
      {
        encoding: "utf8",
        shell: false,
        env: { ...environment, SF_FAKE_FORMULA_DRIFT: "1" },
      },
    );
    assert.notEqual(formulaDriftRun.status, 0);
    assert.match(formulaDriftRun.stderr, /STALE_SALESFORCE/u);

    const changedFieldMapReportPath = path.join(outputDirectory, "changed-field-map-report.json");
    const changedFieldMapReport = {
      ...report,
      fieldMapDigest: `sha256:${"0".repeat(64)}`,
      reportOutput: path.join(await realpath(outputDirectory), "changed-field-map-report.json"),
    };
    await writeFile(
      changedFieldMapReportPath,
      `${JSON.stringify(changedFieldMapReport, null, 2)}\n`,
      { encoding: "utf8", mode: 0o600 },
    );
    const changedFieldMapRun = spawnSync(
      process.execPath,
      [
        CLI_PATH,
        "revalidate",
        "--report",
        changedFieldMapReportPath,
        "--output",
        path.join(outputDirectory, "changed-field-map-revalidation.json"),
      ],
      { encoding: "utf8", shell: false, env: environment },
    );
    assert.notEqual(changedFieldMapRun.status, 0);
    assert.match(changedFieldMapRun.stderr, /STALE_SALESFORCE/u);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("canonical path checks stop symlink aliases from replacing protected inputs", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "salesforce-day2-symlink-"));
  const realDirectory = path.join(directory, "real");
  const aliasDirectory = path.join(directory, "alias");
  const protectedInput = path.join(realDirectory, "dashboard.json");
  const aliasedOutput = path.join(aliasDirectory, "dashboard.json");
  try {
    await mkdir(realDirectory);
    await writeFile(protectedInput, "{\"protected\":true}\n", "utf8");
    await symlink(realDirectory, aliasDirectory, "dir");
    await assert.rejects(
      () => assertNoProtectedPathCollision(aliasedOutput, [protectedInput], "Dashboard output"),
      { code: "OUTPUT_COLLISION" },
    );
    await assert.rejects(
      () => assertWritableTargets([protectedInput, aliasedOutput], true),
      { code: "OUTPUT_COLLISION" },
    );
    await assert.rejects(
      () => writeProtectedJson(aliasedOutput, { protected: false }, true, [protectedInput]),
      { code: "OUTPUT_COLLISION" },
    );
    assert.deepEqual(JSON.parse(await readFile(protectedInput, "utf8")), { protected: true });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("protects existing outputs and writes confidential JSON with explicit overwrite only", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "salesforce-day2-test-"));
  const target = path.join(directory, "result.json");
  try {
    await writeFile(target, "{}\n", "utf8");
    await assert.rejects(() => assertWritableTargets([target], false), { code: "OUTPUT_EXISTS" });
    await assertWritableTargets([target], true);
    await assert.rejects(() => writeProtectedJson(target, { value: 1 }, false), {
      code: "EEXIST",
    });
    await writeProtectedJson(target, { value: 2 }, true);
    assert.deepEqual(JSON.parse(await readFile(target, "utf8")), { value: 2 });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("atomic paired writes reject non-file overwrite targets without partial output", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "salesforce-day2-pair-"));
  const firstPath = path.join(directory, "dashboard.json");
  const directoryTarget = path.join(directory, "mapping-report.json");
  try {
    await mkdir(directoryTarget, { mode: 0o700 });
    await assert.rejects(
      () => writeProtectedJsonPairAtomic(
        [
          { filePath: firstPath, value: { first: true } },
          { filePath: directoryTarget, value: { second: true } },
        ],
        { overwrite: true },
      ),
      { code: "UNSAFE_OUTPUT_TARGET" },
    );
    await assert.rejects(() => stat(firstPath), { code: "ENOENT" });
    assert.equal((await stat(directoryTarget)).isDirectory(), true);
    const leftovers = (await readdir(directory)).filter((name) => /\.(?:tmp|bak)$/u.test(name));
    assert.deepEqual(leftovers, []);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("preserves populated supporting arrays and unsupported fields during enrichment", async () => {
  const base = await blankDashboard();
  base.customerName = "Synthetic Customer";
  base.currentArr = "$1,000,000";
  base.statusSummary = "Existing executive narrative.";
  base.goals = [{ text: "Keep this", target: "Q4", owner: "Owner" }];
  base.workstreams = [{
    name: "Existing workstream",
    owner: "Owner",
    risk: "",
    milestones: "Milestone",
    outcomes: "Outcome",
    atRisk: false,
  }];
  base.relationships = [{
    hierarchyOrder: 1,
    uipathName: "UiPath owner",
    uipathRole: "Role",
    customerName: "Customer owner",
    customerRole: "Role",
    note: "Existing",
  }];
  const account = syntheticAccount();
  const proposal = buildProposal(account, base);
  const built = applyProposal(base, account, proposal, [], FIELD_MAP.version);
  assert.equal(built.dashboard.currentArr, "$1,000,000");
  assert.equal(built.dashboard.statusSummary, "Existing executive narrative.");
  assert.deepEqual(built.dashboard.goals, base.goals);
  assert.deepEqual(built.dashboard.workstreams, base.workstreams);
  assert.deepEqual(built.dashboard.relationships, base.relationships);
});

test("error type retains stable safety codes", () => {
  const error = new EnricherError("TEST_CODE", "message");
  assert.equal(error.code, "TEST_CODE");
  assert.equal(error.name, "EnricherError");
});

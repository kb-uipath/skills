import assert from "node:assert/strict";
import test from "node:test";

import { CAPS, CONTRACTS } from "../scripts/constants.mjs";
import {
  hydrateProfileRelationships,
  PROFILE_HYDRATION_SCHEMA,
} from "../scripts/profile-hydration.mjs";
import {
  buildReadPlan,
  issueApprovalReceipt,
} from "../scripts/read-plan.mjs";
import { digest } from "../scripts/security.mjs";
import { DESCRIBE, IDS, describeMap } from "./helpers.mjs";

const NOW = new Date("2030-01-01T00:05:00.000Z");
const APPROVED_AT = new Date("2030-01-01T00:01:00.000Z");
const RUNTIME_ATTESTATION_DIGEST = "a".repeat(64);
const ORG_IDENTITY = Object.freeze({
  org_id: "00D000000000001AAA",
  username: "synthetic@example.invalid",
  instance_url: "https://synthetic.example.invalid/",
  connected_status: "Connected",
});

function sfId(prefix, index) {
  return `${prefix}${String(index).padStart(12, "0")}AAA`;
}

function profile(overrides = {}) {
  return {
    schema_version: CONTRACTS.profileResult,
    classification: "confidential",
    status: "complete",
    selected_account: {
      Id: IDS.account1,
      Name: "Example",
      ParentId: null,
      OwnerId: IDS.user1,
    },
    scope: "selected_account",
    opportunity_scope: "open",
    accounts: [],
    family_confirmation: null,
    opportunities: [],
    products: [],
    team: [],
    currencies: [],
    warnings: [],
    query_count: 1,
    ...overrides,
  };
}

function sectionsFor(sourceProfile) {
  return [
    "overview",
    ...(sourceProfile.accounts.length ? ["family"] : []),
    ...(sourceProfile.opportunities.length ? ["opportunities"] : []),
    ...(sourceProfile.products.length ? ["products"] : []),
    ...(sourceProfile.team.length ? ["team"] : []),
  ];
}

function planFor(client, sourceProfile, overrides = {}) {
  return buildReadPlan({
    sessionId: "0123456789abcdef0123456789abcdef",
    orgIdentity: {
      target_org: client.targetOrg,
      ...ORG_IDENTITY,
    },
    runtimeAttestationDigest: client.attestationDigest,
    accountSelector: {
      mode: "id",
      value: sourceProfile.selected_account.Id,
    },
    selectedAccount: {
      Id: sourceProfile.selected_account.Id,
      Name: sourceProfile.selected_account.Name,
    },
    accountReceiptDigest: "b".repeat(64),
    familyAccountIds:
      sourceProfile.family_confirmation?.account_ids ?? [],
    preset: "custom",
    sections: sectionsFor(sourceProfile),
    scope: sourceProfile.scope,
    opportunityScope: sourceProfile.opportunity_scope,
    outputType: "json",
    issuedAt: new Date("2030-01-01T00:00:00.000Z"),
    ...overrides,
  });
}

function needsFamilyApproval(readPlan) {
  return readPlan.scope === "corporate_family"
    && ["opportunities", "products", "team"].some((section) =>
      readPlan.requested_sections.includes(section));
}

function authorizationFor(
  client,
  sourceProfile,
  {
    readPlan = planFor(client, sourceProfile),
    familyApprovalReceipt,
    now = NOW,
  } = {},
) {
  return {
    readPlan,
    familyApprovalReceipt: familyApprovalReceipt === undefined
      ? (needsFamilyApproval(readPlan)
        ? issueApprovalReceipt(readPlan, "family_scope", APPROVED_AT)
        : null)
      : familyApprovalReceipt,
    now,
  };
}

async function hydrate(client, sourceProfile, authorization = {}) {
  return await hydrateProfileRelationships({
    client,
    profile: sourceProfile,
    ...authorizationFor(client, sourceProfile, authorization),
  });
}

function opportunity(overrides = {}) {
  return {
    Id: IDS.opportunity1,
    Name: "Renewal",
    AccountId: IDS.account1,
    OwnerId: IDS.user1,
    StageName: "Discovery",
    Amount: 100,
    CloseDate: "2030-01-01",
    IsClosed: false,
    IsWon: false,
    CurrencyIsoCode: "USD",
    HasOpportunityLineItem: false,
    ...overrides,
  };
}

function product(index, opportunityId) {
  return {
    Id: sfId("00k", index),
    OpportunityId: opportunityId,
    Quantity: 2,
    UnitPrice: 50,
    TotalPrice: 100,
    CurrencyIsoCode: "USD",
    PricebookEntryId: sfId("01u", index),
    Product2Id: sfId("01t", index),
    ProductName: `Product ${index}`,
  };
}

function idsFromSoql(soql) {
  return [...soql.matchAll(/'([A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?)'/gu)]
    .map((match) => match[1]);
}

class HydrationClient {
  constructor({
    accounts = [],
    opportunities = [],
    users = [],
    describeMutator = null,
    queryOverride = null,
    identity = ORG_IDENTITY,
    targetOrg = "synthetic",
    attestationDigest = RUNTIME_ATTESTATION_DIGEST,
    queryCount = 1,
  } = {}) {
    this.records = {
      Account: new Map(accounts.map((row) => [row.Id, row])),
      Opportunity: new Map(opportunities.map((row) => [row.Id, row])),
      User: new Map(users.map((row) => [row.Id, row])),
    };
    this.describeMutator = describeMutator;
    this.queryOverride = queryOverride;
    this.identity = { ...identity };
    this.targetOrg = targetOrg;
    this.attestationDigest = attestationDigest;
    this.queryCount = queryCount;
    this.orgDisplayCalls = 0;
    this.describeCalls = [];
    this.queries = [];
  }

  async orgDisplay() {
    this.orgDisplayCalls += 1;
    return { ...this.identity };
  }

  async describe(objectName) {
    this.describeCalls.push(objectName);
    const described = objectName === "Account"
      ? [
        ...(DESCRIBE[objectName] ?? []),
        "CSM__c",
        "Support_Technical_Advisor__c",
        "PreSales__c",
      ]
      : DESCRIBE[objectName] ?? [];
    const fields = describeMap(described);
    return this.describeMutator
      ? this.describeMutator(objectName, fields)
      : fields;
  }

  async query(soql) {
    this.queryCount += 1;
    this.queries.push(soql);
    const objectName = ["Opportunity", "Account", "User"]
      .find((candidate) => soql.includes(`FROM ${candidate}`));
    const defaults = idsFromSoql(soql)
      .flatMap((id) => this.records[objectName]?.has(id)
        ? [this.records[objectName].get(id)]
        : []);
    return this.queryOverride
      ? await this.queryOverride(soql, defaults, objectName)
      : defaults;
  }
}

test("hydrates exact presentation relationships without mutating profile prices", async () => {
  const user3 = sfId("005", 3);
  const user4 = sfId("005", 4);
  const user5 = sfId("005", 5);
  const user6 = sfId("005", 6);
  const user7 = sfId("005", 7);
  const user8 = sfId("005", 8);
  const sourceProfile = profile({
    selected_account: {
      Id: IDS.account1,
      Name: "Example",
      ParentId: IDS.account2,
      OwnerId: IDS.user1,
      CSM__c: user3,
      Support_Technical_Advisor__c: user4,
      PreSales__c: null,
    },
    opportunities: [opportunity({ OwnerId: user5 })],
    products: [product(1, IDS.opportunity2)],
    team: [{
      Id: IDS.user1,
      Name: "Owner",
      Title: "Account Executive",
      ManagerId: user7,
    }, {
      Id: user7,
      Name: "Sales VP",
      Title: "VP",
      ManagerId: user8,
    }, {
      Id: user8,
      Name: "Executive",
      Title: "EVP",
      ManagerId: null,
    }],
    currencies: ["USD"],
    warnings: ["ANNUALIZATION_NOT_CERTIFIED"],
  });
  const before = structuredClone(sourceProfile);
  const client = new HydrationClient({
    accounts: [
      {
        Id: IDS.account1,
        Name: "Ex\u202eample",
        ParentId: IDS.account2,
        OwnerId: IDS.user1,
        CSM__c: user3,
        Support_Technical_Advisor__c: user4,
        PreSales__c: null,
      },
      {
        Id: IDS.account2,
        Name: "Parent",
        ParentId: null,
        OwnerId: IDS.user2,
      },
    ],
    opportunities: [
      {
        Id: IDS.opportunity1,
        Name: "Renewal",
        AccountId: IDS.account1,
        OwnerId: user5,
        IsClosed: false,
      },
      {
        Id: IDS.opportunity2,
        Name: "Expansion",
        AccountId: IDS.account1,
        OwnerId: user6,
        IsClosed: false,
      },
    ],
    users: [
      {
        Id: IDS.user1,
        Name: "Ow\u202ener",
        Title: "Account Executive",
        ManagerId: user7,
      },
      { Id: user3, Name: "CSM", Title: "Customer Success", ManagerId: user7 },
      { Id: user4, Name: "Advisor", Title: "Technical Advisor", ManagerId: null },
      { Id: user5, Name: "Opportunity Owner", Title: "AE", ManagerId: user7 },
      { Id: user6, Name: "Division Owner", Title: "AE", ManagerId: user8 },
      { Id: user7, Name: "Sales VP", Title: "VP", ManagerId: user8 },
      { Id: user8, Name: "Executive", Title: "EVP", ManagerId: null },
    ],
  });

  const authorization = authorizationFor(client, sourceProfile);
  const result = await hydrate(client, sourceProfile);

  assert.equal(result.schema_version, PROFILE_HYDRATION_SCHEMA);
  assert.equal(result.classification, "confidential");
  assert.equal(result.query_count, 6);
  assert.equal(result.binding.source_profile_digest, digest(sourceProfile));
  assert.equal(
    result.binding.read_plan_digest,
    digest(authorization.readPlan),
  );
  assert.match(result.binding.binding_digest, /^[a-f0-9]{64}$/u);
  assert.deepEqual(client.describeCalls, ["Opportunity", "Account", "User"]);
  assert(client.queries.every((soql) => soql.includes("WHERE Id IN (")));
  assert(client.queries.every((soql) => !soql.includes("Amount")));
  assert(client.queries.every((soql) => !soql.includes("UnitPrice")));
  assert(client.queries.every((soql) => !soql.includes("TotalPrice")));

  const selected = result.accounts.find((row) => row.Id === IDS.account1);
  assert.equal(selected.Name, "Example");
  assert.deepEqual(selected.Parent, { Id: IDS.account2, Name: "Parent" });
  assert.equal(selected.Owner.Name, "Owner");
  assert.equal(selected.Roles.csm.available, true);
  assert.equal(selected.Roles.csm.user.Name, "CSM");
  assert.equal(selected.Roles.technical_advisor.user.Title, "Technical Advisor");
  assert.deepEqual(selected.Roles.presales, { available: true, user: null });

  const expansion = result.opportunities.find((row) => row.Id === IDS.opportunity2);
  assert.equal(expansion.Name, "Expansion");
  assert.equal(expansion.Account.Name, "Example");
  assert.equal("Owner" in expansion, false);
  assert.deepEqual(
    result.product_opportunities,
    [{ Id: IDS.opportunity2, Name: "Expansion" }],
  );

  const owner = result.users.find((row) => row.Id === IDS.user1);
  assert.equal(owner.Name, "Owner");
  assert.deepEqual(
    owner.Manager,
    { Id: user7, Name: "Sales VP", Title: "VP" },
  );
  assert.equal(owner.ManagerId, user7);
  assert(!JSON.stringify(result).includes("\u202e"));
  assert.deepEqual(sourceProfile, before);
  assert.equal(sourceProfile.products[0].UnitPrice, 50);
  assert.equal(sourceProfile.products[0].TotalPrice, 100);
});

test("minimal hydration skips Opportunity reads and reports two data queries", async () => {
  const client = new HydrationClient({
    accounts: [{
      Id: IDS.account1,
      Name: "Example",
      ParentId: null,
      OwnerId: IDS.user1,
    }],
    users: [{
      Id: IDS.user1,
      Name: "Owner",
      Title: null,
      ManagerId: IDS.user2,
    }],
  });
  const sourceProfile = profile();
  const result = await hydrate(client, sourceProfile);
  assert.equal(result.query_count, 2);
  assert.deepEqual(client.describeCalls, ["Account", "User"]);
  assert.deepEqual(result.opportunities, []);
  assert.deepEqual(result.product_opportunities, []);
  assert.deepEqual(result.users, []);
  assert(!client.queries.some((soql) => soql.includes(IDS.user2)));
});

test("exact-ID hydration batches 201 product Opportunity references", async () => {
  const opportunityRows = Array.from(
    { length: CAPS.idsPerBatch + 1 },
    (_, index) => ({
      Id: sfId("006", index + 1),
      Name: `Opportunity ${index + 1}`,
      AccountId: IDS.account1,
      OwnerId: IDS.user1,
      IsClosed: false,
    }),
  );
  const sourceProfile = profile({
    products: opportunityRows.map((row, index) => product(index + 1, row.Id)),
    currencies: ["USD"],
    warnings: ["ANNUALIZATION_NOT_CERTIFIED"],
  });
  const client = new HydrationClient({
    accounts: [{
      Id: IDS.account1,
      Name: "Example",
      ParentId: null,
      OwnerId: IDS.user1,
    }],
    opportunities: opportunityRows,
    users: [{
      Id: IDS.user1,
      Name: "Owner",
      Title: "AE",
      ManagerId: null,
    }],
  });
  const result = await hydrate(client, sourceProfile);
  assert.equal(result.product_opportunities.length, 201);
  assert.equal(result.query_count, 4);
  const opportunityQueries = client.queries.filter((soql) =>
    soql.includes("FROM Opportunity"));
  assert.equal(opportunityQueries.length, 2);
  assert(opportunityQueries[0].includes("LIMIT 201"));
  assert(opportunityQueries[1].includes("LIMIT 2"));
});

test("relationship caps fail before any describe or data query", async () => {
  const products = Array.from(
    { length: CAPS.opportunities + 1 },
    (_, index) => product(index + 1, sfId("006", index + 1)),
  );
  const client = new HydrationClient();
  const sourceProfile = profile({
    products,
    currencies: ["USD"],
    warnings: ["ANNUALIZATION_NOT_CERTIFIED"],
  });
  await assert.rejects(
    () => hydrate(client, sourceProfile),
    {
      code: "OPPORTUNITY_CAP_EXCEEDED",
      details: {
        next_action: [
          "selected_account",
          "open_only",
          "date_narrowing",
          "stage_narrowing",
        ],
      },
    },
  );
  assert.deepEqual(client.describeCalls, []);
  assert.deepEqual(client.queries, []);
});

test("line-item and confirmed family caps fail before Salesforce access", async () => {
  const lineItems = Array.from(
    { length: CAPS.lineItems + 1 },
    (_, index) => product(index + 1, IDS.opportunity1),
  );
  const lineItemProfile = profile({
    products: lineItems,
    currencies: ["USD"],
    warnings: ["ANNUALIZATION_NOT_CERTIFIED"],
  });
  const lineItemClient = new HydrationClient();
  await assert.rejects(
    () => hydrate(lineItemClient, lineItemProfile),
    { code: "LINE_ITEM_CAP_EXCEEDED" },
  );
  assert.equal(lineItemClient.orgDisplayCalls, 0);
  assert.deepEqual(lineItemClient.describeCalls, []);
  assert.deepEqual(lineItemClient.queries, []);

  const familyIds = Array.from(
    { length: CAPS.familyAccounts + 1 },
    (_, index) => sfId("001", index + 1),
  ).sort();
  const familyProfile = profile({
    scope: "corporate_family",
    family_confirmation: {
      account_ids: familyIds,
      family_digest: "c".repeat(64),
    },
  });
  const familyClient = new HydrationClient();
  await assert.rejects(
    () => hydrate(familyClient, familyProfile),
    { code: "FAMILY_ACCOUNT_CAP_EXCEEDED" },
  );
  assert.equal(familyClient.orgDisplayCalls, 0);
  assert.deepEqual(familyClient.describeCalls, []);
  assert.deepEqual(familyClient.queries, []);
});

test("plan, org, runtime, and family approval authority bind before data queries", async () => {
  const sourceProfile = profile();
  const forgedClient = new HydrationClient();
  const validPlan = planFor(forgedClient, sourceProfile);
  const forgedPlan = {
    ...validPlan,
    account_selector: { mode: "id", value: IDS.account2 },
    selected_account: { Id: IDS.account2, Name: "Other" },
  };
  await assert.rejects(
    () => hydrate(forgedClient, sourceProfile, { readPlan: forgedPlan }),
    { code: "PROFILE_PLAN_MISMATCH" },
  );
  assert.equal(forgedClient.orgDisplayCalls, 0);
  assert.deepEqual(forgedClient.queries, []);

  const crossOrgClient = new HydrationClient({
    identity: {
      ...ORG_IDENTITY,
      org_id: "00D000000000002AAA",
    },
  });
  await assert.rejects(
    () => hydrate(crossOrgClient, sourceProfile),
    { code: "READ_PLAN_MISMATCH" },
  );
  assert.equal(crossOrgClient.orgDisplayCalls, 1);
  assert.deepEqual(crossOrgClient.describeCalls, []);
  assert.deepEqual(crossOrgClient.queries, []);

  const account3 = sfId("001", 3);
  const familyProfile = profile({
    scope: "corporate_family",
    family_confirmation: {
      account_ids: [IDS.account1, account3].sort(),
      family_digest: "d".repeat(64),
    },
    products: [product(1, IDS.opportunity1)],
    currencies: ["USD"],
    warnings: ["ANNUALIZATION_NOT_CERTIFIED"],
  });
  const familyClient = new HydrationClient();
  const familyPlan = planFor(familyClient, familyProfile);
  await assert.rejects(
    () => hydrate(familyClient, familyProfile, {
      readPlan: familyPlan,
      familyApprovalReceipt: null,
    }),
    { code: "INVALID_PLAN_CONTEXT" },
  );
  assert.equal(familyClient.orgDisplayCalls, 0);
  assert.deepEqual(familyClient.queries, []);

  const staleClient = new HydrationClient();
  const stalePlan = planFor(staleClient, familyProfile);
  const futureApproval = issueApprovalReceipt(
    stalePlan,
    "family_scope",
    new Date("2030-01-01T00:10:00.000Z"),
  );
  await assert.rejects(
    () => hydrate(staleClient, familyProfile, {
      readPlan: stalePlan,
      familyApprovalReceipt: futureApproval,
      now: NOW,
    }),
    { code: "APPROVAL_RECEIPT_EXPIRED" },
  );
  assert.equal(staleClient.orgDisplayCalls, 0);
  assert.deepEqual(staleClient.queries, []);
});

test("a requested family section must contain the exact approved Account set", async () => {
  const sourceProfile = profile({
    accounts: [{
      Id: IDS.account1,
      Name: "Example",
      ParentId: null,
      OwnerId: IDS.user1,
    }],
    family_confirmation: {
      account_ids: [IDS.account1, IDS.account2],
      family_digest: "e".repeat(64),
    },
  });
  const client = new HydrationClient();
  await assert.rejects(
    () => hydrate(client, sourceProfile),
    { code: "PROFILE_PLAN_MISMATCH" },
  );
  assert.equal(client.orgDisplayCalls, 0);
  assert.deepEqual(client.describeCalls, []);
  assert.deepEqual(client.queries, []);
});

test("cumulative query budget rejects a partial hydration before Salesforce access", async () => {
  const sourceProfile = profile({ query_count: CAPS.queries - 1 });
  const client = new HydrationClient({ queryCount: CAPS.queries - 1 });
  await assert.rejects(
    () => hydrate(client, sourceProfile),
    {
      code: "QUERY_CAP_EXCEEDED",
      details: {
        next_action: [
          "selected_account",
          "remove_line_items",
          "remove_team",
          "reduce_sections",
        ],
      },
    },
  );
  assert.equal(client.orgDisplayCalls, 0);
  assert.deepEqual(client.describeCalls, []);
  assert.deepEqual(client.queries, []);

  const freshClient = new HydrationClient({ queryCount: 0 });
  await assert.rejects(
    () => hydrate(freshClient, profile()),
    { code: "INVALID_PLAN_CONTEXT" },
  );
  assert.equal(freshClient.orgDisplayCalls, 0);
  assert.deepEqual(freshClient.queries, []);
});

test("queried field metadata must have compatible types, references, and predicate filterability", async () => {
  const scenarios = [
    {
      sourceProfile: profile(),
      mutate: (objectName, fields) => {
        if (objectName === "Account") {
          fields.set("Id", { ...fields.get("Id"), filterable: false });
        }
        return fields;
      },
    },
    {
      sourceProfile: profile({
        opportunities: [opportunity()],
        currencies: ["USD"],
      }),
      mutate: (objectName, fields) => {
        if (objectName === "Opportunity") {
          fields.set("OwnerId", {
            ...fields.get("OwnerId"),
            referenceTo: ["Account"],
          });
        }
        return fields;
      },
    },
    {
      sourceProfile: profile(),
      mutate: (objectName, fields) => {
        if (objectName === "User") {
          fields.set("Title", { ...fields.get("Title"), type: "currency" });
        }
        return fields;
      },
    },
    {
      sourceProfile: profile({
        selected_account: {
          Id: IDS.account1,
          Name: "Example",
          ParentId: null,
          OwnerId: IDS.user1,
          CSM__c: IDS.user2,
        },
      }),
      mutate: (objectName, fields) => {
        if (objectName === "Account") {
          fields.set("CSM__c", {
            ...fields.get("CSM__c"),
            referenceTo: ["Account"],
          });
        }
        return fields;
      },
    },
    {
      sourceProfile: profile({
        team: [{
          Id: IDS.user1,
          Name: "Owner",
          Title: "AE",
          ManagerId: IDS.user2,
        }, {
          Id: IDS.user2,
          Name: "Manager",
          Title: "VP",
          ManagerId: null,
        }],
      }),
      mutate: (objectName, fields) => {
        if (objectName === "User") {
          fields.set("ManagerId", {
            ...fields.get("ManagerId"),
            referenceTo: ["Account"],
          });
        }
        return fields;
      },
    },
  ];
  for (const scenario of scenarios) {
    const client = new HydrationClient({ describeMutator: scenario.mutate });
    await assert.rejects(
      () => hydrate(client, scenario.sourceProfile),
      { code: "SCHEMA_FAILURE" },
    );
    assert.deepEqual(client.queries, []);
  }
});

test("missing, duplicate, extra, and invalid Account rows fail atomically", async () => {
  const valid = {
    Id: IDS.account1,
    Name: "Example",
    ParentId: null,
    OwnerId: IDS.user1,
  };
  const extra = {
    Id: IDS.account2,
    Name: "Extra",
    ParentId: null,
    OwnerId: IDS.user2,
  };
  const cases = [
    { records: [], code: "RELATIONSHIP_INCONSISTENCY" },
    { records: [valid, valid], code: "RELATIONSHIP_INCONSISTENCY" },
    { records: [valid, extra], code: "RELATIONSHIP_INCONSISTENCY" },
    { records: [{ ...valid, Name: 42 }], code: "INVALID_FIELD_TYPE" },
  ];
  for (const scenario of cases) {
    const client = new HydrationClient({
      queryOverride: (soql, defaults, objectName) =>
        objectName === "Account" ? scenario.records : defaults,
    });
    let result;
    await assert.rejects(async () => {
      result = await hydrate(client, profile());
    }, { code: scenario.code });
    assert.equal(result, undefined);
  }
});

test("known source relationship drift fails before presentation context escapes", async () => {
  const changedOwner = new HydrationClient({
    accounts: [{
      Id: IDS.account1,
      Name: "Example",
      ParentId: null,
      OwnerId: IDS.user2,
    }],
  });
  await assert.rejects(
    () => hydrate(changedOwner, profile()),
    { code: "RELATIONSHIP_INCONSISTENCY" },
  );

  const changedOpportunity = new HydrationClient({
    opportunities: [{
      Id: IDS.opportunity1,
      Name: "Changed",
      AccountId: IDS.account1,
      OwnerId: IDS.user1,
      IsClosed: false,
    }],
  });
  const changedOpportunityProfile = profile({
    opportunities: [opportunity()],
    currencies: ["USD"],
  });
  await assert.rejects(
    () => hydrate(changedOpportunity, changedOpportunityProfile),
    { code: "RELATIONSHIP_INCONSISTENCY" },
  );
});

test("missing product Opportunities fail rather than infer names", async () => {
  const missingOpportunity = new HydrationClient();
  const sourceProfile = profile({
    products: [product(1, IDS.opportunity1)],
    currencies: ["USD"],
    warnings: ["ANNUALIZATION_NOT_CERTIFIED"],
  });
  await assert.rejects(
    () => hydrate(missingOpportunity, sourceProfile),
    { code: "RELATIONSHIP_INCONSISTENCY" },
  );
});

test("Opportunity hydration cannot expand beyond the confirmed Account scope", async () => {
  const account3 = sfId("001", 3);
  const user3 = sfId("005", 3);
  const client = new HydrationClient({
    opportunities: [{
      Id: IDS.opportunity2,
      Name: "Outside Scope",
      AccountId: account3,
      OwnerId: user3,
      IsClosed: false,
    }],
  });
  const sourceProfile = profile({
    products: [product(1, IDS.opportunity2)],
    currencies: ["USD"],
    warnings: ["ANNUALIZATION_NOT_CERTIFIED"],
  });
  await assert.rejects(
    () => hydrate(client, sourceProfile),
    { code: "PREDICATE_BINDING_FAILED" },
  );
  assert.equal(
    client.queries.filter((soql) => soql.includes("FROM Opportunity")).length,
    1,
  );
  assert.equal(
    client.queries.filter((soql) => soql.includes("FROM Account")).length,
    0,
  );
  assert.equal(
    client.queries.filter((soql) => soql.includes("FROM User")).length,
    0,
  );
});

test("product Opportunity hydration reapplies every approved predicate", async () => {
  const sourceProfile = profile({
    products: [product(1, IDS.opportunity1)],
    currencies: ["USD"],
    warnings: ["ANNUALIZATION_NOT_CERTIFIED"],
  });
  const client = new HydrationClient({
    opportunities: [{
      Id: IDS.opportunity1,
      Name: "Filtered Opportunity",
      AccountId: IDS.account1,
      OwnerId: IDS.user2,
      IsClosed: false,
      CloseDate: "2030-06-01",
      StageName: "Negotiation",
    }],
  });
  const readPlan = planFor(client, sourceProfile, {
    filters: {
      close_date_from: "2030-01-01",
      close_date_to: "2030-12-31",
      stages: ["Discovery"],
    },
  });
  await assert.rejects(
    () => hydrate(client, sourceProfile, { readPlan }),
    { code: "PREDICATE_BINDING_FAILED" },
  );
  assert.equal(client.queries.length, 1);
  const [query] = client.queries;
  assert(query.includes(`AccountId IN ('${IDS.account1}')`));
  assert(query.includes("IsClosed = false"));
  assert(query.includes("CloseDate >= 2030-01-01"));
  assert(query.includes("CloseDate <= 2030-12-31"));
  assert(query.includes("StageName IN ('Discovery')"));
  assert(query.includes("SELECT Id, Name, AccountId, IsClosed, CloseDate, StageName"));
  assert(!query.includes("OwnerId"));
});

test("product-only hydration does not read or cap unrequested Opportunity owners", async () => {
  const opportunityRows = Array.from(
    { length: CAPS.users + 1 },
    (_, index) => ({
      Id: sfId("006", index + 1),
      Name: `Product Opportunity ${index + 1}`,
      AccountId: IDS.account1,
      OwnerId: sfId("005", index + 100),
      IsClosed: false,
    }),
  );
  const sourceProfile = profile({
    products: opportunityRows.map((row, index) =>
      product(index + 1, row.Id)),
    currencies: ["USD"],
    warnings: ["ANNUALIZATION_NOT_CERTIFIED"],
  });
  const client = new HydrationClient({
    accounts: [{
      Id: IDS.account1,
      Name: "Example",
      ParentId: null,
      OwnerId: IDS.user1,
    }],
    opportunities: opportunityRows,
    users: [{
      Id: IDS.user1,
      Name: "Owner",
      Title: "AE",
    }],
  });
  const result = await hydrate(client, sourceProfile);
  assert.equal(result.query_count, 3);
  assert.equal(result.opportunities.length, CAPS.users + 1);
  assert(result.opportunities.every((row) => !("Owner" in row)));
  const opportunityQueries = client.queries.filter((query) =>
    query.includes("FROM Opportunity"));
  assert(opportunityQueries.every((query) => !query.includes("OwnerId")));
  const [userQuery] = client.queries.filter((query) =>
    query.includes("FROM User"));
  assert.deepEqual(idsFromSoql(userQuery), [IDS.user1]);
});

test("corporate-family product context uses only the confirmed Account-ID set", async () => {
  const account3 = sfId("001", 3);
  const user3 = sfId("005", 3);
  const client = new HydrationClient({
    accounts: [{
      Id: IDS.account1,
      Name: "Example",
      ParentId: null,
      OwnerId: IDS.user1,
    }, {
      Id: account3,
      Name: "Division",
      ParentId: null,
      OwnerId: user3,
    }],
    opportunities: [{
      Id: IDS.opportunity2,
      Name: "Family Expansion",
      AccountId: account3,
      OwnerId: user3,
      IsClosed: false,
    }],
    users: [{
      Id: IDS.user1,
      Name: "Owner",
      Title: "AE",
    }, {
      Id: user3,
      Name: "Division Owner",
      Title: "AE",
    }],
  });
  const sourceProfile = profile({
    scope: "corporate_family",
    family_confirmation: {
      account_ids: [IDS.account1, account3].sort(),
      family_digest: "a".repeat(64),
    },
    products: [product(1, IDS.opportunity2)],
    currencies: ["USD"],
    warnings: ["ANNUALIZATION_NOT_CERTIFIED"],
  });
  const result = await hydrate(client, sourceProfile);
  assert.equal(result.query_count, 4);
  assert.deepEqual(result.accounts.map((row) => row.Id), [IDS.account1]);
  assert.deepEqual(result.product_opportunities, [{
    Id: IDS.opportunity2,
    Name: "Family Expansion",
  }]);
  assert.equal(result.opportunities[0].Account.Id, account3);
  assert.equal(result.opportunities[0].Account.Name, "Division");
  assert.equal("Owner" in result.opportunities[0], false);
});

test("Account role and team ManagerId reassignment fail closed", async () => {
  const roleProfile = profile({
    selected_account: {
      Id: IDS.account1,
      Name: "Example",
      ParentId: null,
      OwnerId: IDS.user1,
      CSM__c: IDS.user2,
    },
  });
  const roleClient = new HydrationClient({
    accounts: [{
      Id: IDS.account1,
      Name: "Example",
      ParentId: null,
      OwnerId: IDS.user1,
      CSM__c: sfId("005", 3),
    }],
  });
  await assert.rejects(
    () => hydrate(roleClient, roleProfile),
    { code: "RELATIONSHIP_INCONSISTENCY" },
  );
  assert.equal(
    roleClient.queries.filter((query) => query.includes("FROM User")).length,
    0,
  );

  const managerProfile = profile({
    team: [{
      Id: IDS.user1,
      Name: "Owner",
      Title: "AE",
      ManagerId: IDS.user2,
    }, {
      Id: IDS.user2,
      Name: "Manager",
      Title: "VP",
      ManagerId: null,
    }],
  });
  const managerClient = new HydrationClient({
    accounts: [{
      Id: IDS.account1,
      Name: "Example",
      ParentId: null,
      OwnerId: IDS.user1,
    }],
    users: [{
      Id: IDS.user1,
      Name: "Owner",
      Title: "AE",
      ManagerId: sfId("005", 3),
    }, {
      Id: IDS.user2,
      Name: "Manager",
      Title: "VP",
      ManagerId: null,
    }],
  });
  await assert.rejects(
    () => hydrate(managerClient, managerProfile),
    { code: "RELATIONSHIP_INCONSISTENCY" },
  );
  const [teamQuery] = managerClient.queries.filter((query) =>
    query.includes("FROM User"));
  assert(teamQuery.includes("ManagerId"));
});

test("manager hydration stays inside the returned v1 team boundary", async () => {
  const teamUser = {
    Id: IDS.user1,
    Name: "Owner",
    Title: "AE",
    ManagerId: IDS.user2,
  };
  const completeClient = new HydrationClient();
  const completeProfile = profile({ team: [teamUser] });
  await assert.rejects(
    () => hydrate(completeClient, completeProfile),
    { code: "RELATIONSHIP_INCONSISTENCY" },
  );
  assert.deepEqual(completeClient.describeCalls, []);
  assert.deepEqual(completeClient.queries, []);

  const incompleteClient = new HydrationClient({
    accounts: [{
      Id: IDS.account1,
      Name: "Example",
      ParentId: null,
      OwnerId: IDS.user1,
    }],
    users: [{
      Id: IDS.user1,
      Name: "Owner",
      Title: "AE",
      ManagerId: IDS.user2,
    }],
  });
  const incompleteProfile = profile({
    team: [teamUser],
    warnings: ["MANAGER_HIERARCHY_INCOMPLETE"],
  });
  const result = await hydrate(incompleteClient, incompleteProfile);
  assert.equal(result.query_count, 2);
  assert.deepEqual(result.users, [{
    Id: IDS.user1,
    Name: "Owner",
    Title: "AE",
    ManagerId: IDS.user2,
    Manager: null,
  }]);
  assert(!incompleteClient.queries.some((soql) => soql.includes(IDS.user2)));
});

test("an incomplete manager cannot leak back through an Account role overlap", async () => {
  const sourceProfile = profile({
    selected_account: {
      Id: IDS.account1,
      Name: "Example",
      ParentId: null,
      OwnerId: IDS.user1,
      CSM__c: IDS.user2,
    },
    team: [{
      Id: IDS.user1,
      Name: "Owner",
      Title: "AE",
      ManagerId: IDS.user2,
    }],
    warnings: ["MANAGER_HIERARCHY_INCOMPLETE"],
  });
  const client = new HydrationClient({
    accounts: [{
      Id: IDS.account1,
      Name: "Example",
      ParentId: null,
      OwnerId: IDS.user1,
      CSM__c: IDS.user2,
    }],
    users: [{
      Id: IDS.user1,
      Name: "Owner",
      Title: "AE",
      ManagerId: IDS.user2,
    }, {
      Id: IDS.user2,
      Name: "CSM Manager",
      Title: "VP",
    }],
  });
  const result = await hydrate(client, sourceProfile);
  assert.equal(result.query_count, 3);
  assert.equal(result.accounts[0].Roles.csm.user.Name, "CSM Manager");
  assert.equal(result.users[0].ManagerId, IDS.user2);
  assert.equal(result.users[0].Manager, null);
});

test("internal hydration rejects noncanonical 15-character relationship IDs", async () => {
  const sourceProfile = profile({
    selected_account: {
      Id: IDS.account1.slice(0, 15),
      Name: "Example",
      ParentId: null,
      OwnerId: IDS.user1,
    },
  });
  const client = new HydrationClient();
  await assert.rejects(
    () => hydrate(client, sourceProfile),
    { code: "INVALID_PLAN_CONTEXT" },
  );
  assert.equal(client.orgDisplayCalls, 0);
  assert.deepEqual(client.describeCalls, []);
  assert.deepEqual(client.queries, []);
});

test("duplicate source rows fail before Salesforce-like operations begin", async () => {
  const duplicate = opportunity();
  const client = new HydrationClient();
  const sourceProfile = profile({
    opportunities: [duplicate, { ...duplicate }],
    currencies: ["USD"],
  });
  await assert.rejects(
    () => hydrate(client, sourceProfile),
    { code: "RELATIONSHIP_INCONSISTENCY" },
  );
  assert.deepEqual(client.describeCalls, []);
  assert.deepEqual(client.queries, []);
});

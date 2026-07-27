import assert from "node:assert/strict";
import test from "node:test";

import { CONTRACTS } from "../scripts/constants.mjs";
import { buildProfileView, profileViewInternals } from "../scripts/profile-view.mjs";
import { PROFILE_HYDRATION_SCHEMA } from "../scripts/profile-hydration.mjs";
import { buildReadPlan, readPlanDigest } from "../scripts/read-plan.mjs";
import { digest } from "../scripts/security.mjs";
import { IDS } from "./helpers.mjs";

function plan(overrides = {}) {
  return buildReadPlan({
    sessionId: "a".repeat(32),
    orgIdentity: {
      target_org: "synthetic",
      org_id: "00D000000000001AAA",
      username: "synthetic@example.invalid",
      instance_url: "https://synthetic.example.invalid/",
      connected_status: "Connected",
    },
    runtimeAttestationDigest: "b".repeat(64),
    accountSelector: { mode: "exact_name", value: "Example" },
    selectedAccount: { Id: IDS.account1, Name: "Example" },
    accountReceiptDigest: "c".repeat(64),
    issuedAt: new Date("2030-01-01T00:00:00.000Z"),
    ...overrides,
  });
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
    opportunities: [{
      Id: IDS.opportunity1,
      Name: "Renewal",
      AccountId: IDS.account1,
      OwnerId: IDS.user1,
      StageName: "Discovery",
      Amount: 10.1,
      CloseDate: "2030-04-01",
      IsClosed: false,
      IsWon: false,
      CurrencyIsoCode: "USD",
      HasOpportunityLineItem: true,
    }],
    products: [],
    team: [{
      Id: IDS.user1,
      Name: "Synthetic Owner",
      Title: "Account Executive",
      ManagerId: IDS.user2,
    }, {
      Id: IDS.user2,
      Name: "Synthetic Manager",
      Title: "Manager",
      ManagerId: null,
    }],
    currencies: ["USD"],
    warnings: [],
    query_count: 7,
    ...overrides,
  };
}

function relationshipContext(currentPlan, currentProfile, overrides = {}) {
  const bindingCore = {
    source_profile_digest: digest(currentProfile),
    read_plan_digest: readPlanDigest(currentPlan),
    family_approval_receipt_digest: null,
    org_identity_digest: digest(currentPlan.org_identity),
  };
  return {
    schema_version: PROFILE_HYDRATION_SCHEMA,
    classification: "confidential",
    binding: {
      ...bindingCore,
      binding_digest: digest(bindingCore),
    },
    accounts: [{
      Id: IDS.account1,
      Name: "Example",
      Parent: null,
      Owner: {
        Id: IDS.user1,
        Name: "Synthetic Owner",
        Title: "Account Executive",
      },
      Roles: {
        csm: { available: false, user: null },
        technical_advisor: { available: false, user: null },
        presales: { available: false, user: null },
      },
    }],
    opportunities: [{
      Id: IDS.opportunity1,
      Name: "Renewal",
      Account: { Id: IDS.account1, Name: "Example" },
      Owner: {
        Id: IDS.user1,
        Name: "Synthetic Owner",
        Title: "Account Executive",
      },
    }],
    product_opportunities: [],
    users: [{
      Id: IDS.user1,
      Name: "Synthetic Owner",
      Title: "Account Executive",
      ManagerId: IDS.user2,
      Manager: {
        Id: IDS.user2,
        Name: "Synthetic Manager",
        Title: "Manager",
      },
    }, {
      Id: IDS.user2,
      Name: "Synthetic Manager",
      Title: "Manager",
      ManagerId: null,
      Manager: null,
    }],
    query_count: 4,
    ...overrides,
  };
}

test("profile view exposes scope, section states, names, and a decision summary", () => {
  const result = buildProfileView({ plan: plan(), profile: profile() });
  assert.equal(result.schema_version, CONTRACTS.profileView);
  assert.equal(result.plan.preset, "pipeline");
  assert.deepEqual(result.plan.requested_sections, ["overview", "opportunities", "team"]);
  assert.equal(result.sections.family.state, "not_requested");
  assert.equal(result.sections.products.state, "not_requested");
  assert.equal(result.sections.opportunities.records[0].AccountName, "Example");
  assert.equal(result.sections.opportunities.records[0].OwnerName, "Synthetic Owner");
  assert.equal(result.sections.team.records[0].ManagerName, "Synthetic Manager");
  assert.match(result.decision_summary, /next close date 2030-04-01/u);
  assert.equal(result.source.query_count, 7);
  assert.match(result.source.read_plan_digest, /^[a-f0-9]{64}$/u);
});

test("profile view applies exact hydrated names and query provenance", () => {
  const currentPlan = plan();
  const currentProfile = profile();
  const result = buildProfileView({
    plan: currentPlan,
    profile: currentProfile,
    relationshipContext: relationshipContext(currentPlan, currentProfile),
  });
  assert.equal(result.selected_account.OwnerName, "Synthetic Owner");
  assert.equal(result.sections.opportunities.records[0].OwnerName, "Synthetic Owner");
  assert.equal(result.sections.team.records[0].ManagerName, "Synthetic Manager");
  assert.equal(result.source.query_count, 11);
});

test("profile view rejects replayed or forged relationship bindings", () => {
  const currentPlan = plan();
  const currentProfile = profile();
  const validContext = relationshipContext(currentPlan, currentProfile);
  const cases = [
    {
      ...validContext,
      binding: {
        ...validContext.binding,
        source_profile_digest: "d".repeat(64),
      },
    },
    {
      ...validContext,
      binding: {
        ...validContext.binding,
        org_identity_digest: "e".repeat(64),
      },
    },
    {
      ...validContext,
      binding: {
        ...validContext.binding,
        binding_digest: "f".repeat(64),
      },
    },
  ];
  for (const context of cases) {
    assert.throws(
      () => buildProfileView({
        plan: currentPlan,
        profile: currentProfile,
        relationshipContext: context,
      }),
      { code: "RELATIONSHIP_CONTEXT_MISMATCH" },
    );
  }
});

test("requested empty sections differ from unrequested sections", () => {
  const result = buildProfileView({
    plan: plan(),
    profile: profile({ opportunities: [], currencies: [] }),
  });
  assert.equal(result.sections.opportunities.state, "empty");
  assert.equal(result.sections.opportunities.record_count, 0);
  assert.equal(result.sections.products.state, "not_requested");
  assert.equal(result.sections.products.record_count, 0);
});

test("incomplete manager hierarchy is explicit and warning codes remain structured", () => {
  const result = buildProfileView({
    plan: plan(),
    profile: profile({
      warnings: ["MANAGER_HIERARCHY_INCOMPLETE", "OPTIONAL_FIELD_UNAVAILABLE:Account.Support_Status__c"],
    }),
  });
  assert.equal(result.sections.team.state, "incomplete");
  assert.deepEqual(result.sections.team.reason_codes, ["MANAGER_HIERARCHY_INCOMPLETE"]);
  assert.equal(result.warnings[0].code, "MANAGER_HIERARCHY_INCOMPLETE");
  assert.match(result.warnings[0].message, /incomplete/u);
  assert.match(result.warnings[1].message, /no value was inferred/u);
});

test("currency summaries never combine currencies and use exact decimal strings", () => {
  const customPlan = plan({
    preset: "custom",
    sections: ["overview", "opportunities", "products"],
    scope: "selected_account",
    opportunityScope: "all",
  });
  const result = buildProfileView({
    plan: customPlan,
    profile: profile({
      opportunity_scope: "all",
      opportunities: [
        {
          Id: IDS.opportunity1,
          Name: "USD",
          AccountId: IDS.account1,
          OwnerId: IDS.user1,
          StageName: "Discovery",
          Amount: 0.1,
          CloseDate: "2030-04-01",
          IsClosed: false,
          IsWon: false,
          CurrencyIsoCode: "USD",
          HasOpportunityLineItem: true,
        },
        {
          Id: IDS.opportunity2,
          Name: "EUR",
          AccountId: IDS.account1,
          OwnerId: IDS.user1,
          StageName: "Discovery",
          Amount: 2,
          CloseDate: "2030-05-01",
          IsClosed: false,
          IsWon: false,
          CurrencyIsoCode: "EUR",
          HasOpportunityLineItem: false,
        },
      ],
      products: [{
        Id: "00k000000000001AAA",
        OpportunityId: IDS.opportunity1,
        Quantity: 2,
        UnitPrice: 0.1,
        TotalPrice: 0.2,
        CurrencyIsoCode: "USD",
        PricebookEntryId: "01u000000000001AAA",
        Product2Id: "01t000000000001AAA",
        ProductName: "Synthetic Product",
      }],
      team: [],
      currencies: ["EUR", "USD"],
      warnings: ["ANNUALIZATION_NOT_CERTIFIED", "MULTICURRENCY_NO_AGGREGATION"],
    }),
  });
  assert.deepEqual(result.currency_summaries.map((item) => item.currency_iso_code), ["EUR", "USD"]);
  assert.equal(result.currency_summaries[0].opportunities.sum_of_returned, "2");
  assert.equal(result.currency_summaries[1].opportunities.sum_of_returned, "0.1");
  assert.equal(result.currency_summaries[1].opportunity_line_items.sum_of_returned, "0.2");
  assert.equal(result.warnings[0].code, "ANNUALIZATION_NOT_CERTIFIED");
});

test("currency summaries count missing values without treating them as zero", () => {
  const result = buildProfileView({
    plan: plan(),
    profile: profile({
      opportunities: [
        {
          Id: IDS.opportunity1,
          Name: "Known",
          AccountId: IDS.account1,
          OwnerId: IDS.user1,
          StageName: "Discovery",
          Amount: 5,
          CloseDate: "2030-04-01",
          IsClosed: false,
          IsWon: false,
          CurrencyIsoCode: "USD",
          HasOpportunityLineItem: false,
        },
        {
          Id: IDS.opportunity2,
          Name: "Missing",
          AccountId: IDS.account1,
          OwnerId: IDS.user1,
          StageName: "Discovery",
          Amount: null,
          CloseDate: "2030-05-01",
          IsClosed: false,
          IsWon: false,
          CurrencyIsoCode: "USD",
          HasOpportunityLineItem: false,
        },
      ],
    }),
  });
  assert.equal(result.currency_summaries[0].opportunities.record_count, 2);
  assert.equal(result.currency_summaries[0].opportunities.value_present_count, 1);
  assert.equal(result.currency_summaries[0].opportunities.value_missing_count, 1);
  assert.equal(result.currency_summaries[0].opportunities.sum_of_returned, "5");
  assert.equal(result.currency_summaries[0].opportunity_line_items.state, "not_requested");
});

test("profile view rejects plan/profile scope drift", () => {
  assert.throws(
    () => buildProfileView({
      plan: plan(),
      profile: profile({ scope: "corporate_family" }),
    }),
    { code: "PROFILE_PLAN_MISMATCH" },
  );
});

test("profile view rejects records from unrequested sections", () => {
  assert.throws(
    () => buildProfileView({
      plan: plan({ preset: "snapshot" }),
      profile: profile({
        opportunities: [],
        team: [{
          Id: IDS.user1,
          Name: "Unexpected",
          Title: null,
          ManagerId: null,
        }],
        currencies: [],
      }),
    }),
    { code: "PROFILE_PLAN_MISMATCH" },
  );
});

test("decimal helper is exact across ordinary and exponent representations", () => {
  assert.equal(profileViewInternals.exactDecimalSum([0.1, 0.2]), "0.3");
  assert.equal(profileViewInternals.exactDecimalSum([1e-7, 2e-7]), "0.0000003");
  assert.equal(profileViewInternals.exactDecimalSum([-5, 2.5]), "-2.5");
});

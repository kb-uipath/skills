import assert from "node:assert/strict";
import test from "node:test";

import { CONTRACTS, WARNING_ANNUALIZATION } from "../scripts/constants.mjs";
import { buildRenderResult, renderProfile } from "../scripts/render.mjs";
import { IDS } from "./helpers.mjs";

const legacyProfile = {
  schema_version: CONTRACTS.profileResult,
  classification: "confidential",
  selected_account: {
    Id: IDS.account1,
    Name: "Legacy Account",
    ParentId: null,
    OwnerId: IDS.user1,
  },
  scope: "selected_account",
  accounts: [],
  opportunities: [],
  products: [],
  team: [],
  warnings: [],
};

test("legacy v1 overview layout remains byte-compatible", () => {
  const expected = `# Confidential Salesforce Account Profile

Account: **Legacy Account** (\`${IDS.account1}\`)

Scope: selected\\_account

## Account Overview

| Field | Value |
| --- | --- |
| Account ID | ${IDS.account1} |
| Name | Legacy Account |
| Owner ID | ${IDS.user1} |
`;

  assert.equal(renderProfile(legacyProfile), expected);
});

test("legacy v1 rendering uses line-item language and plain warnings", () => {
  const rendered = renderProfile({
    ...legacyProfile,
    products: [{
      Id: "00k000000000001AAA",
      OpportunityId: IDS.opportunity1,
      PricebookEntryId: "01u000000000001AAA",
      Product2Id: "01t000000000001AAA",
      ProductName: "Legacy Product",
      Quantity: 1,
      UnitPrice: 10,
      TotalPrice: 10,
      CurrencyIsoCode: "USD",
    }],
  });

  assert(!rendered.includes("## Products"));
  assert(rendered.includes("## Opportunity line items"));
  assert(!rendered.includes("## Decision Summary"));
  assert(rendered.includes(
    "These are raw Salesforce Opportunity line items, not entitlements, utilization, consumption, or installed-product inventory.",
  ));
  assert(rendered.includes(
    "Annualized revenue is not calculated because price basis, recurrence, and duration semantics are not certified.",
  ));
  assert(!rendered.includes(WARNING_ANNUALIZATION));
});

function completeView() {
  const selectedAccount = {
    Id: IDS.account1,
    Name: "**Example | Holdings**\u202e\u001b[31m",
    ParentId: null,
    ParentName: null,
    OwnerId: IDS.user1,
    OwnerName: "Alex | Owner",
    Region__c: "East",
  };
  return {
    schema_version: CONTRACTS.profileView,
    classification: "confidential",
    status: "complete",
    certification_state: "offline_validated",
    plan: {
      preset: "full_selected",
      requested_sections: ["overview", "family", "opportunities", "products", "team"],
      scope: "corporate_family",
      opportunity_scope: "all",
      filters: {
        close_date_from: "2029-01-01",
        close_date_to: "2030-12-31",
        stages: ["Discovery | Review", "Closed Won"],
      },
      field_map_version: "salesforce-account-profile-field-map/v1",
      output_type: "rendered",
    },
    decision_summary: "Decide **now** | using returned Salesforce evidence only.\u202e",
    selected_account: selectedAccount,
    sections: {
      overview: {
        label: "Account overview",
        state: "complete",
        record_count: 1,
        reason_codes: [],
        records: [selectedAccount],
      },
      family: {
        label: "Corporate-family accounts",
        state: "complete",
        record_count: 2,
        reason_codes: [],
        records: [
          {
            Id: IDS.account2,
            Name: "Example Division",
            ParentId: IDS.account1,
            ParentName: "Example Holdings",
            OwnerId: IDS.user2,
            OwnerName: "Casey CSM",
          },
          {
            ...selectedAccount,
            Name: "Example Holdings",
          },
        ],
      },
      opportunities: {
        label: "Opportunities",
        state: "complete",
        record_count: 2,
        reason_codes: [],
        records: [
          {
            Id: IDS.opportunity1,
            Name: "Expansion **FY30**",
            AccountId: IDS.account1,
            AccountName: "Example Holdings",
            OwnerId: IDS.user1,
            OwnerName: "Alex Owner",
            StageName: "Discovery",
            Amount: 0.1,
            CloseDate: "2030-01-01",
            IsClosed: false,
            IsWon: false,
            CurrencyIsoCode: "USD",
          },
          {
            Id: IDS.opportunity2,
            Name: "Renewal",
            AccountId: IDS.account2,
            AccountName: "Example Division",
            OwnerId: IDS.user2,
            OwnerName: "Casey CSM",
            StageName: "Closed Won",
            Amount: 200,
            CloseDate: "2029-01-01",
            IsClosed: true,
            IsWon: true,
            CurrencyIsoCode: "EUR",
          },
        ],
      },
      products: {
        label: "Opportunity line items",
        state: "complete",
        record_count: 2,
        reason_codes: [],
        records: [
          {
            Id: "00k000000000001AAA",
            OpportunityId: IDS.opportunity1,
            OpportunityName: "Expansion FY30",
            AccountId: IDS.account1,
            AccountName: "Example Holdings",
            PricebookEntryId: "01u000000000001AAA",
            Product2Id: "01t000000000001AAA",
            ProductName: "Automation *Cloud*",
            Quantity: 2,
            UnitPrice: 20,
            TotalPrice: 40,
            CurrencyIsoCode: "USD",
            ServiceDate: null,
          },
          {
            Id: "00k000000000002AAA",
            OpportunityId: IDS.opportunity2,
            OpportunityName: "Renewal",
            AccountId: IDS.account2,
            AccountName: "Example Division",
            PricebookEntryId: "01u000000000002AAA",
            Product2Id: "01t000000000002AAA",
            ProductName: "Process Mining",
            Quantity: 3,
            UnitPrice: 30,
            TotalPrice: 90,
            CurrencyIsoCode: "EUR",
            ServiceDate: "2029-01-01",
          },
        ],
      },
      team: {
        label: "Owner hierarchy",
        state: "complete",
        record_count: 2,
        reason_codes: [],
        records: [
          {
            Id: IDS.user1,
            Name: "Alex Owner",
            Title: "Account Executive",
            ManagerId: IDS.user2,
            ManagerName: "Casey CSM",
          },
          {
            Id: IDS.user2,
            Name: "Casey CSM",
            Title: "Manager",
            ManagerId: null,
            ManagerName: null,
          },
        ],
      },
    },
    currency_summaries: [
      {
        currency_iso_code: "USD",
        opportunities: {
          state: "complete",
          record_count: 2,
          value_present_count: 1,
          value_missing_count: 1,
          sum_of_returned: "0.1",
        },
        opportunity_line_items: {
          state: "complete",
          record_count: 1,
          value_present_count: 1,
          value_missing_count: 0,
          sum_of_returned: "40",
        },
      },
      {
        currency_iso_code: "EUR",
        opportunities: {
          state: "complete",
          record_count: 1,
          value_present_count: 1,
          value_missing_count: 0,
          sum_of_returned: "200",
        },
        opportunity_line_items: {
          state: "complete",
          record_count: 1,
          value_present_count: 1,
          value_missing_count: 0,
          sum_of_returned: "90",
        },
      },
    ],
    warnings: [
      { code: WARNING_ANNUALIZATION },
      {
        code: "OPTIONAL_FIELD_UNAVAILABLE:Account.Support_Status__c",
        title: "Optional field unavailable",
        message: "Salesforce did not expose optional field Account.Support_Status__c; no value was inferred.",
        impact: "The optional value is absent.",
        next_action: "Confirm permissions if required.",
      },
    ],
    source: {
      read_plan_digest: "a".repeat(64),
      profile_digest: "b".repeat(64),
      query_count: 8,
    },
    view_digest: "c".repeat(64),
  };
}

test("v2 decision context precedes escaped evidence with names and currency boundaries", () => {
  const markdown = buildRenderResult(completeView()).markdown;

  assert(markdown.indexOf("## Decision Summary") < markdown.indexOf("## Account Overview"));
  assert(markdown.includes("| Preset | full\\_selected |"));
  assert(markdown.includes("| Account scope | Corporate family |"));
  assert(markdown.includes("| Opportunity scope | All opportunities |"));
  assert(markdown.includes("2029\\-01\\-01 through 2030\\-12\\-31"));
  assert(markdown.includes("Offline validated only — not operationally certified"));
  assert(!markdown.includes("Read-plan digest"));
  assert(!markdown.includes("Field-map version"));
  assert(!markdown.includes("Output type"));
  assert(!markdown.includes("Query count"));
  assert(!markdown.includes("salesforce-account-profile-view"));
  assert(!markdown.includes("salesforce\\-account\\-profile\\-field\\-map"));
  assert(!markdown.includes("a".repeat(64)));
  assert(!markdown.includes("b".repeat(64)));
  assert(!markdown.includes("c".repeat(64)));
  assert(markdown.includes("## Opportunity line items"));
  assert(!markdown.includes("## Products"));

  assert(markdown.includes(IDS.account1));
  assert(markdown.includes("Example Holdings"));
  assert(markdown.includes(IDS.opportunity1));
  assert(markdown.includes("Expansion \\*\\*FY30\\*\\*"));
  assert(markdown.includes(IDS.user1));
  assert(markdown.includes("Alex \\| Owner"));
  assert(markdown.includes("Casey CSM"));
  assert(markdown.includes("2030\\-01\\-01"));

  const eurSummary = "| EUR | complete | 1 | 1 | 0 | 200 | complete | 1 | 1 | 0 | 90 |";
  const usdSummary = "| USD | complete | 2 | 1 | 1 | 0\\.1 | complete | 1 | 1 | 0 | 40 |";
  assert(markdown.includes(eurSummary));
  assert(markdown.includes(usdSummary));
  assert(markdown.indexOf(eurSummary) < markdown.indexOf(usdSummary));
  assert(markdown.includes("Currencies are never combined; no ARR or annualized value is calculated."));
  assert(!markdown.includes("Cross-currency total"));

  assert(markdown.includes("Annualized revenue is not calculated"));
  assert(markdown.includes("Optional field unavailable"));
  assert(!markdown.includes("ANNUALIZATION\\_NOT\\_CERTIFIED"));
  assert(!markdown.includes("ANNUALIZATION_NOT_CERTIFIED"));
  assert(!markdown.includes("OPTIONAL\\_FIELD\\_UNAVAILABLE"));
  assert(!markdown.includes("OPTIONAL_FIELD_UNAVAILABLE"));
  assert(markdown.includes("\\*\\*Example \\| Holdings\\*\\*"));
  assert(markdown.includes("Decide \\*\\*now\\*\\* \\| using returned Salesforce evidence only\\."));
  assert(!markdown.includes("\u202e"));
  assert(!markdown.includes("\u001b"));
});

test("v2 distinguishes not-requested, requested-empty, and incomplete sections", () => {
  const view = completeView();
  view.plan.requested_sections = ["overview", "opportunities", "products", "team"];
  view.plan.opportunity_scope = "open";
  view.sections.family = {
    label: "Corporate-family accounts",
    state: "not_requested",
    record_count: 0,
    reason_codes: [],
    records: [],
  };
  view.sections.opportunities = {
    label: "Opportunities",
    state: "empty",
    record_count: 0,
    reason_codes: [],
    records: [],
  };
  view.sections.products = {
    label: "Opportunity line items",
    state: "incomplete",
    record_count: 1,
    reason_codes: ["LINE_ITEM_CAP_EXCEEDED"],
    records: [{ Id: "00k000000000001AAA" }],
  };
  view.currency_summaries = [];

  const markdown = renderProfile(view);

  assert.match(markdown, /## Corporate-Family Accounts\n\nNot requested\./u);
  assert.match(markdown, /## Opportunities\n\nOpen Opportunities requested; none returned\./u);
  assert.match(markdown, /## Opportunity line items\n\nIncomplete or failed; this section is not presented as complete\./u);
  assert(markdown.includes("Opportunity line\\-item result reached its safety cap"));
  assert(!markdown.includes("LINE\\_ITEM\\_CAP\\_EXCEEDED"));
  assert(!markdown.includes("LINE_ITEM_CAP_EXCEEDED"));
  assert(!markdown.includes("00k000000000001AAA"));
  assert(markdown.includes("No per-currency records were returned."));
});

test("v2 inconsistent section counts fail closed in presentation", () => {
  const view = completeView();
  view.sections.team.record_count = 99;

  const markdown = renderProfile(view);

  assert.match(markdown, /## Owner Hierarchy\n\nIncomplete or failed; this section is not presented as complete\./u);
  assert(markdown.includes("structured section count did not match the supplied records"));
  assert(!markdown.includes("SECTION\\_RECORD\\_COUNT\\_MISMATCH"));
  assert(!markdown.includes("SECTION_RECORD_COUNT_MISMATCH"));
  assert(!markdown.includes("| Account Executive |"));
});

test("incomplete v2 views withhold evidence deterministically", () => {
  const view = {
    ...completeView(),
    status: "failed",
    decision_summary: "Source read failed; no evidence is certified.",
  };
  const first = buildRenderResult(view);
  const second = buildRenderResult(view);

  assert.deepEqual(first, second);
  assert(first.markdown.includes("## Decision Summary"));
  assert(first.markdown.includes("Status: failed"));
  assert(first.markdown.includes("Evidence tables are withheld"));
  assert(!first.markdown.includes("## Account Overview"));
  assert(first.markdown.includes("Annualized revenue is not calculated"));
  assert(!first.markdown.includes("ANNUALIZATION\\_NOT\\_CERTIFIED"));
  assert(!first.markdown.includes("ANNUALIZATION_NOT_CERTIFIED"));
});

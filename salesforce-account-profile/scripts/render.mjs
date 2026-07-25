import { CONTRACTS, WARNING_ANNUALIZATION } from "./constants.mjs";
import { digest, markdownText } from "./security.mjs";

function table(headers, rows) {
  const header = `| ${headers.join(" | ")} |`;
  const divider = `| ${headers.map(() => "---").join(" | ")} |`;
  return [header, divider, ...rows.map((row) => `| ${row.map((value) => markdownText(value ?? "Not returned")).join(" | ")} |`)].join("\n");
}

export function renderProfile(profile) {
  const overviewFields = [
    ["Account ID", "Id"], ["Name", "Name"], ["Parent ID", "ParentId"], ["Owner ID", "OwnerId"],
    ["Classification", "Classification__c"], ["Region", "Region__c"], ["Geo", "Geo__c"],
    ["Contract End Date", "Contract_End_Date__c"],
    ["Support Type", "Support_Type__c"], ["Support Status", "Support_Status__c"],
    ["CSM ID", "CSM__c"], ["Technical Advisor ID", "Support_Technical_Advisor__c"],
    ["PreSales ID", "PreSales__c"],
  ].filter(([, key]) => profile.selected_account[key] !== null && profile.selected_account[key] !== undefined);
  const lines = [
    "# Confidential Salesforce Account Profile",
    "",
    `Account: **${markdownText(profile.selected_account.Name)}** (\`${markdownText(profile.selected_account.Id)}\`)`,
    "",
    `Scope: ${markdownText(profile.scope)}`,
    "",
    "## Account Overview",
    "",
    table(["Field", "Value"], overviewFields.map(([label, key]) => [label, profile.selected_account[key]])),
    "",
  ];
  if (profile.family_confirmation || profile.accounts?.length > 1) {
    lines.push("## Corporate-Family Accounts", "", table(
      ["ID", "Name", "Parent ID", "Owner ID"],
      profile.accounts.map((account) => [account.Id, account.Name, account.ParentId, account.OwnerId]),
    ), "");
  }
  if (profile.opportunities?.length) {
    lines.push("## Opportunities", "", table(
      ["ID", "Name", "Account ID", "Owner ID", "Stage", "Closed", "Won", "Amount", "Currency"],
      profile.opportunities.map((item) => [
        item.Id, item.Name, item.AccountId, item.OwnerId, item.StageName, item.IsClosed, item.IsWon, item.Amount, item.CurrencyIsoCode,
      ]),
    ), "");
  }
  if (profile.products?.length) {
    lines.push("## Products", "", table(
      ["ID", "Opportunity ID", "Pricebook Entry ID", "Product ID", "Product", "Quantity", "Unit Price", "Total Price", "Currency"],
      profile.products.map((item) => [
        item.Id, item.OpportunityId, item.PricebookEntryId, item.Product2Id, item.ProductName, item.Quantity, item.UnitPrice, item.TotalPrice, item.CurrencyIsoCode,
      ]),
    ), "", `Warning: ${WARNING_ANNUALIZATION}`, "");
  }
  if (profile.team?.length) {
    lines.push("## Owner Hierarchy", "", table(
      ["User ID", "Name", "Title", "Manager ID"],
      profile.team.map((item) => [item.Id, item.Name, item.Title, item.ManagerId]),
    ), "");
  }
  if (profile.warnings?.length) {
    lines.push("## Warnings", "", ...profile.warnings.map((warning) => `- ${markdownText(warning)}`), "");
  }
  return `${lines.join("\n").trimEnd()}\n`;
}

export function buildRenderResult(profile) {
  const markdown = renderProfile(profile);
  return {
    schema_version: CONTRACTS.renderResult,
    classification: "confidential",
    markdown,
    profile_digest: digest(profile),
    render_digest: digest(markdown),
  };
}

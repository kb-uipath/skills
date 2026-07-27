import { CONTRACTS, WARNING_ANNUALIZATION } from "./constants.mjs";
import { digest, markdownText } from "./security.mjs";

function table(headers, rows) {
  const header = `| ${headers.join(" | ")} |`;
  const divider = `| ${headers.map(() => "---").join(" | ")} |`;
  return [header, divider, ...rows.map((row) => `| ${row.map((value) => markdownText(value ?? "Not returned")).join(" | ")} |`)].join("\n");
}

function renderLegacyProfile(profile) {
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
    lines.push("## Opportunity line items", "", table(
      ["ID", "Opportunity ID", "Pricebook Entry ID", "Product ID", "Product", "Quantity", "Unit Price", "Total Price", "Currency"],
      profile.products.map((item) => [
        item.Id, item.OpportunityId, item.PricebookEntryId, item.Product2Id, item.ProductName, item.Quantity, item.UnitPrice, item.TotalPrice, item.CurrencyIsoCode,
      ]),
    ), "",
    "These are raw Salesforce Opportunity line items, not entitlements, utilization, consumption, or installed-product inventory.",
    "",
    WARNING_MESSAGES[WARNING_ANNUALIZATION],
    "");
  }
  if (profile.team?.length) {
    lines.push("## Owner Hierarchy", "", table(
      ["User ID", "Name", "Title", "Manager ID"],
      profile.team.map((item) => [item.Id, item.Name, item.Title, item.ManagerId]),
    ), "");
  }
  if (profile.warnings?.length) {
    lines.push(
      "## Warnings",
      "",
      ...profile.warnings.map((warning) =>
        `- ${markdownText(warningMessage(warning))}`),
      "",
    );
  }
  return `${lines.join("\n").trimEnd()}\n`;
}

const SECTION_ORDER = Object.freeze([
  "overview",
  "family",
  "opportunities",
  "products",
  "team",
]);

const SECTION_LABELS = Object.freeze({
  overview: "Account overview",
  family: "Corporate-family accounts",
  opportunities: "Opportunities",
  products: "Opportunity line items",
  team: "Owner hierarchy",
});

const SECTION_HEADINGS = Object.freeze({
  overview: "## Account Overview",
  family: "## Corporate-Family Accounts",
  opportunities: "## Opportunities",
  products: "## Opportunity line items",
  team: "## Owner Hierarchy",
});

const CERTIFICATION_LABELS = Object.freeze({
  offline_validated: "Offline validated only — not operationally certified",
  sandbox_read_certified: "Sandbox read certified",
  production_read_approved: "Production read approved",
});

const WARNING_MESSAGES = Object.freeze({
  [WARNING_ANNUALIZATION]: "Annualized revenue is not calculated because price basis, recurrence, and duration semantics are not certified.",
  MULTICURRENCY_NO_AGGREGATION: "Amounts are summarized separately by currency and are never combined.",
  MANAGER_DEPTH_LIMIT_REACHED: "The owner hierarchy reached its configured depth limit; higher managers may be absent.",
  MANAGER_CYCLE_DETECTED: "The owner hierarchy contains a manager cycle; the returned reporting path is incomplete.",
  MANAGER_HIERARCHY_INCOMPLETE: "The owner hierarchy is incomplete and must not be treated as the full reporting path.",
  ULTIMATE_PARENT_FIELD_EMPTY_USING_PARENT_TRAVERSAL: "The configured family field was empty, so bounded ParentId traversal was used.",
  ULTIMATE_PARENT_FIELD_UNAVAILABLE_USING_PARENT_TRAVERSAL: "The configured family field was unavailable, so bounded ParentId traversal was used.",
});

const INCOMPLETENESS_MESSAGES = Object.freeze({
  LINE_ITEM_CAP_EXCEEDED: "The Opportunity line-item result reached its safety cap and may be incomplete.",
  OPPORTUNITY_CAP_EXCEEDED: "The Opportunity result reached its safety cap and may be incomplete.",
  FAMILY_ACCOUNT_CAP_EXCEEDED: "The corporate-family Account result reached its safety cap and may be incomplete.",
  USER_CAP_EXCEEDED: "The owner-hierarchy result reached its safety cap and may be incomplete.",
  QUERY_CAP_EXCEEDED: "The read reached its query safety cap and may be incomplete.",
  SECTION_RECORD_COUNT_MISMATCH: "The structured section count did not match the supplied records, so its evidence was withheld.",
});

function compareText(left, right) {
  const a = String(left ?? "");
  const b = String(right ?? "");
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

function sortedRecords(records, keys) {
  return [...records].sort((left, right) => {
    for (const key of keys) {
      const comparison = compareText(left?.[key], right?.[key]);
      if (comparison !== 0) return comparison;
    }
    return 0;
  });
}

function labelForScope(scope) {
  if (scope === "selected_account") return "Selected account";
  if (scope === "corporate_family") return "Corporate family";
  return scope ?? "Not reported";
}

function labelForOpportunityScope(scope) {
  if (scope === "open") return "Open opportunities";
  if (scope === "closed") return "Closed opportunities";
  if (scope === "all") return "All opportunities";
  return scope ?? "Not reported";
}

function requestedSectionsLabel(requestedSections) {
  if (!Array.isArray(requestedSections)) return "Not reported";
  const requested = new Set(requestedSections);
  const labels = SECTION_ORDER
    .filter((section) => requested.has(section))
    .map((section) => SECTION_LABELS[section]);
  const unknown = requestedSections
    .filter((section) => !SECTION_LABELS[section])
    .sort(compareText);
  return [...labels, ...unknown].join(", ") || "None";
}

function filtersLabel(filters) {
  if (!filters || typeof filters !== "object" || Array.isArray(filters)) return "Not reported";
  const parts = [];
  if (filters.close_date_from || filters.close_date_to) {
    parts.push(`Close date: ${filters.close_date_from ?? "unbounded"} through ${filters.close_date_to ?? "unbounded"}`);
  }
  if (Array.isArray(filters.stages) && filters.stages.length) {
    parts.push(`Stages: ${[...filters.stages].sort(compareText).join(", ")}`);
  }
  return parts.join("; ") || "None";
}

function decisionRows(view) {
  const plan = view.plan ?? view;
  return [
    ["Preset", plan.preset ?? "Not reported"],
    ["Requested sections", requestedSectionsLabel(plan.requested_sections)],
    ["Account scope", labelForScope(plan.scope)],
    ["Opportunity scope", labelForOpportunityScope(plan.opportunity_scope)],
    ["Filters", filtersLabel(plan.filters)],
    ["Certification", CERTIFICATION_LABELS[view.certification_state] ?? "Not operationally certified"],
  ];
}

function interimRecords(view, section) {
  if (section === "overview") return view.selected_account ? [view.selected_account] : [];
  if (section === "family") return Array.isArray(view.accounts) ? view.accounts : [];
  if (section === "opportunities") return Array.isArray(view.opportunities) ? view.opportunities : [];
  if (section === "products") return Array.isArray(view.opportunity_line_items)
    ? view.opportunity_line_items
    : (Array.isArray(view.products) ? view.products : []);
  return Array.isArray(view.team) ? view.team : [];
}

function normalizeSection(view, section) {
  const envelope = view.sections?.[section];
  const rawState = envelope?.state ?? envelope?.status;
  const stateAliases = {
    unrequested: "not_requested",
    requested_empty: "empty",
    failed: "incomplete",
  };
  const state = stateAliases[rawState] ?? rawState ?? "incomplete";
  const records = Array.isArray(envelope?.records)
    ? envelope.records
    : interimRecords(view, section);
  const reportedCount = envelope?.record_count ?? envelope?.count;
  const reasons = Array.isArray(envelope?.reason_codes)
    ? envelope.reason_codes
    : (envelope?.reason ? [envelope.reason] : []);
  const inconsistentCount = reportedCount !== null
    && reportedCount !== undefined
    && (!Number.isInteger(reportedCount) || reportedCount !== records.length);
  const inconsistentState = (state === "complete" && records.length === 0)
    || (section === "overview" && state === "complete" && records.length !== 1)
    || ((state === "empty" || state === "not_requested") && records.length > 0);
  if (inconsistentCount || inconsistentState) {
    return {
      state: "incomplete",
      records: [],
      reasonCodes: [...new Set([...reasons, "SECTION_RECORD_COUNT_MISMATCH"])].sort(compareText),
    };
  }
  return {
    state,
    records,
    reasonCodes: [...new Set(reasons)].sort(compareText),
  };
}

function overviewTable(records) {
  const account = records[0] ?? {};
  const fields = [
    ["Account ID", account.Id],
    ["Name", account.Name],
    ["Parent ID", account.ParentId],
    ["Parent name", account.ParentName],
    ["Owner ID", account.OwnerId],
    ["Owner name", account.OwnerName],
    ["Classification", account.Classification__c],
    ["Region", account.Region__c],
    ["Geo", account.Geo__c],
    ["Contract End Date", account.Contract_End_Date__c],
    ["Support Type", account.Support_Type__c],
    ["Support Status", account.Support_Status__c],
    ["CSM ID", account.CSM__c],
    ["CSM name", account.CSMName],
    ["Technical Advisor ID", account.Support_Technical_Advisor__c],
    ["Technical Advisor name", account.TechnicalAdvisorName],
    ["PreSales ID", account.PreSales__c],
    ["PreSales name", account.PreSalesName],
  ].filter(([, value]) => value !== null && value !== undefined);
  return table(["Field", "Value"], fields);
}

function familyTable(records) {
  return table(
    ["ID", "Name", "Parent ID", "Parent name", "Owner ID", "Owner name"],
    sortedRecords(records, ["Name", "Id"]).map((account) => [
      account?.Id,
      account?.Name,
      account?.ParentId,
      account?.ParentName,
      account?.OwnerId,
      account?.OwnerName,
    ]),
  );
}

function opportunitiesTable(records) {
  return table(
    ["ID", "Name", "Account ID", "Account name", "Owner ID", "Owner name", "Stage", "Close Date", "Closed", "Won", "Amount", "Currency"],
    sortedRecords(records, ["Name", "Id"]).map((item) => [
      item?.Id,
      item?.Name,
      item?.AccountId,
      item?.AccountName,
      item?.OwnerId,
      item?.OwnerName,
      item?.StageName,
      item?.CloseDate,
      item?.IsClosed,
      item?.IsWon,
      item?.Amount,
      item?.CurrencyIsoCode,
    ]),
  );
}

function lineItemsTable(records) {
  return table(
    ["ID", "Opportunity ID", "Opportunity name", "Account ID", "Account name", "Pricebook Entry ID", "Product ID", "Product", "Quantity", "Unit Price", "Total Price", "Currency", "Service Date"],
    sortedRecords(records, ["OpportunityName", "ProductName", "Id"]).map((item) => [
      item?.Id,
      item?.OpportunityId,
      item?.OpportunityName,
      item?.AccountId,
      item?.AccountName,
      item?.PricebookEntryId,
      item?.Product2Id,
      item?.ProductName,
      item?.Quantity,
      item?.UnitPrice,
      item?.TotalPrice,
      item?.CurrencyIsoCode,
      item?.ServiceDate,
    ]),
  );
}

function teamTable(records) {
  return table(
    ["User ID", "Name", "Title", "Manager ID", "Manager name"],
    sortedRecords(records, ["Name", "Id"]).map((item) => [
      item?.Id,
      item?.Name,
      item?.Title,
      item?.ManagerId,
      item?.ManagerName,
    ]),
  );
}

const SECTION_TABLES = Object.freeze({
  overview: overviewTable,
  family: familyTable,
  opportunities: opportunitiesTable,
  products: lineItemsTable,
  team: teamTable,
});

function emptySectionMessage(view, section) {
  if (section === "overview") return "Account overview requested; none returned.";
  if (section === "family") return "Corporate-family accounts requested; none returned.";
  if (section === "products") return "Opportunity line items requested; none returned.";
  if (section === "team") return "Owner hierarchy requested; no users returned.";
  const opportunityScope = (view.plan ?? view).opportunity_scope;
  const scope = opportunityScope === "closed"
    ? "Closed"
    : opportunityScope === "all"
      ? "All"
      : "Open";
  return `${scope} Opportunities requested; none returned.`;
}

function incompletenessMessage(code) {
  return INCOMPLETENESS_MESSAGES[code]
    ?? WARNING_MESSAGES[code]
    ?? "The structured view reported an unrecognized incompleteness reason; this evidence was withheld.";
}

function renderSection(view, section) {
  const normalized = normalizeSection(view, section);
  const lines = [SECTION_HEADINGS[section], ""];
  if (normalized.state === "not_requested") {
    lines.push("Not requested.");
  } else if (normalized.state === "empty") {
    lines.push(emptySectionMessage(view, section));
  } else if (normalized.state === "complete") {
    lines.push(SECTION_TABLES[section](normalized.records));
    if (section === "products") {
      lines.push(
        "",
        "These are raw Salesforce Opportunity line items, not entitlements, utilization, consumption, or installed-product inventory.",
      );
    }
  } else {
    lines.push("Incomplete or failed; this section is not presented as complete.");
    if (normalized.reasonCodes.length) {
      const explanations = [...new Set(normalized.reasonCodes.map(incompletenessMessage))];
      lines.push("", ...explanations.map((message) => `- ${markdownText(message)}`));
    }
  }
  return lines;
}

function monetaryValue(value) {
  return value === null || value === undefined ? "Not reported" : value;
}

function normalizeCurrencySummary(summary) {
  const opportunities = summary?.opportunities ?? {};
  const lineItems = summary?.opportunity_line_items ?? {};
  return {
    currency: summary?.currency_iso_code ?? summary?.currency ?? "Not reported",
    opportunityState: opportunities.state ?? summary?.opportunity_state ?? "Not reported",
    opportunityCount: monetaryValue(opportunities.record_count ?? summary?.opportunity_count),
    opportunityPresent: monetaryValue(
      opportunities.value_present_count ?? summary?.opportunity_amount_present_count,
    ),
    opportunityMissing: monetaryValue(
      opportunities.value_missing_count ?? summary?.opportunity_amount_missing_count,
    ),
    opportunityTotal: monetaryValue(
      opportunities.sum_of_returned ?? summary?.opportunity_amount,
    ),
    lineItemState: lineItems.state ?? summary?.line_item_state ?? "Not reported",
    lineItemCount: monetaryValue(lineItems.record_count ?? summary?.line_item_count),
    lineItemPresent: monetaryValue(
      lineItems.value_present_count ?? summary?.line_item_total_present_count,
    ),
    lineItemMissing: monetaryValue(
      lineItems.value_missing_count ?? summary?.line_item_total_missing_count,
    ),
    lineItemTotal: monetaryValue(
      lineItems.sum_of_returned ?? summary?.line_item_total,
    ),
  };
}

function renderCurrencySummaries(view) {
  const summaries = Array.isArray(view.currency_summaries)
    ? view.currency_summaries.map(normalizeCurrencySummary).sort((left, right) =>
      compareText(left.currency, right.currency))
    : [];
  const lines = [
    "## Per-Currency Summary",
    "",
    "Counts and raw monetary fields are shown per currency. Currencies are never combined; no ARR or annualized value is calculated.",
    "",
  ];
  if (!summaries.length) {
    lines.push("No per-currency records were returned.");
    return lines;
  }
  lines.push(table(
    [
      "Currency",
      "Opportunity state",
      "Opportunity count",
      "Amount present",
      "Amount missing",
      "Raw Opportunity Amount total",
      "Line-item state",
      "Line-item count",
      "TotalPrice present",
      "TotalPrice missing",
      "Raw TotalPrice total",
    ],
    summaries.map((summary) => [
      summary.currency,
      summary.opportunityState,
      summary.opportunityCount,
      summary.opportunityPresent,
      summary.opportunityMissing,
      summary.opportunityTotal,
      summary.lineItemState,
      summary.lineItemCount,
      summary.lineItemPresent,
      summary.lineItemMissing,
      summary.lineItemTotal,
    ]),
  ));
  return lines;
}

function warningMessage(code) {
  if (WARNING_MESSAGES[code]) return WARNING_MESSAGES[code];
  if (String(code).startsWith("OPTIONAL_FIELD_UNAVAILABLE:")) {
    const field = String(code).slice("OPTIONAL_FIELD_UNAVAILABLE:".length);
    return `Optional field ${field} was unavailable; no value was inferred.`;
  }
  return "Unrecognized warning; review the structured warning code before relying on the affected result.";
}

function normalizeWarning(warning) {
  if (typeof warning === "string") {
    return { code: warning, title: null, message: warningMessage(warning), impact: null, nextAction: null };
  }
  const code = warning?.code ?? "UNREPORTED_WARNING_CODE";
  return {
    code,
    title: warning?.title ?? null,
    message: warning?.message ?? warningMessage(code),
    impact: warning?.impact ?? null,
    nextAction: warning?.next_action ?? warning?.nextAction ?? null,
  };
}

function renderWarnings(view) {
  const warnings = Array.isArray(view.warnings)
    ? view.warnings.map(normalizeWarning).sort((left, right) =>
      compareText(left.code, right.code) || compareText(left.message, right.message))
    : [];
  const lines = ["## Warnings", ""];
  if (!warnings.length) {
    lines.push("No warnings were reported.");
    return lines;
  }
  for (const warning of warnings) {
    const title = warning.title ? `${markdownText(warning.title)} — ` : "";
    let item = `- ${title}${markdownText(warning.message)}`;
    if (warning.impact) item += ` Impact: ${markdownText(warning.impact)}`;
    if (warning.nextAction) item += ` Next action: ${markdownText(warning.nextAction)}`;
    lines.push(item);
  }
  return lines;
}

function renderProfileView(view) {
  const account = view.selected_account ?? {};
  const lines = [
    "# Confidential Salesforce Account Profile",
    "",
    `Account: **${markdownText(account.Name ?? "Not returned")}** (\`${markdownText(account.Id ?? "Not returned")}\`)`,
    "",
    "## Decision Summary",
    "",
    markdownText(view.decision_summary ?? "No decision summary was returned."),
    "",
    table(["Decision input", "Value"], decisionRows(view)),
    "",
  ];
  if (view.status !== "complete") {
    lines.push(
      `Status: ${markdownText(view.status ?? "incomplete")}`,
      "",
      "Evidence tables are withheld because the structured view is incomplete or failed.",
      "",
      ...renderWarnings(view),
    );
    return `${lines.join("\n").trimEnd()}\n`;
  }
  for (const section of SECTION_ORDER) {
    lines.push(...renderSection(view, section), "");
  }
  lines.push(...renderCurrencySummaries(view), "", ...renderWarnings(view));
  return `${lines.join("\n").trimEnd()}\n`;
}

export function renderProfile(profile) {
  return profile?.schema_version === CONTRACTS.profileView
    ? renderProfileView(profile)
    : renderLegacyProfile(profile);
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

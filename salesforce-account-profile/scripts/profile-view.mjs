import {
  CERTIFICATION_STATES,
  CLASSIFICATION,
  CONTRACTS,
  PROFILE_SECTIONS,
  WARNING_ANNUALIZATION,
} from "./constants.mjs";
import { validateCompleteProfile } from "./contracts.mjs";
import { PROFILE_HYDRATION_SCHEMA } from "./profile-hydration.mjs";
import { readPlanDigest, validateReadPlan } from "./read-plan.mjs";
import {
  assertExactKeys,
  digest,
  SafetyError,
  sanitizeText,
} from "./security.mjs";

const WARNING_CATALOG = Object.freeze({
  [WARNING_ANNUALIZATION]: Object.freeze({
    severity: "warning",
    title: "Annualization is disabled",
    message: "Annualized revenue is not calculated because price basis, recurrence, and duration semantics are not certified.",
    impact: "Unit Price and Total Price remain raw Salesforce values.",
    next_action: "Use the raw line-item prices or certify an org-versioned recurring-price field map.",
    affected_section: "products",
  }),
  MULTICURRENCY_NO_AGGREGATION: Object.freeze({
    severity: "notice",
    title: "Currencies remain separate",
    message: "Amounts are summarized separately by currency and are never combined.",
    impact: "No cross-currency total or implied conversion is shown.",
    next_action: "Review each currency summary independently.",
    affected_section: "opportunities",
  }),
  MANAGER_DEPTH_LIMIT_REACHED: Object.freeze({
    severity: "warning",
    title: "Manager depth limit reached",
    message: "The owner hierarchy reached its configured depth limit.",
    impact: "Higher managers may be absent.",
    next_action: "Treat the owner hierarchy as incomplete.",
    affected_section: "team",
  }),
  MANAGER_CYCLE_DETECTED: Object.freeze({
    severity: "warning",
    title: "Manager cycle detected",
    message: "The owner hierarchy contains a manager cycle.",
    impact: "The returned reporting path is not complete.",
    next_action: "Review the Salesforce User hierarchy.",
    affected_section: "team",
  }),
  MANAGER_HIERARCHY_INCOMPLETE: Object.freeze({
    severity: "warning",
    title: "Owner hierarchy incomplete",
    message: "The owner hierarchy is incomplete; use it only as the returned Salesforce reporting path.",
    impact: "Do not treat the last returned manager as the hierarchy root.",
    next_action: "Review the depth or cycle warning before using ownership conclusions.",
    affected_section: "team",
  }),
  ULTIMATE_PARENT_FIELD_EMPTY_USING_PARENT_TRAVERSAL: Object.freeze({
    severity: "notice",
    title: "Family fallback used",
    message: "The configured family field was empty, so corporate-family discovery used bounded ParentId traversal.",
    impact: "The result is a technical corporate-family map, not a legal-subsidiary determination.",
    next_action: "Review the returned Account set before family-wide reads.",
    affected_section: "family",
  }),
  ULTIMATE_PARENT_FIELD_UNAVAILABLE_USING_PARENT_TRAVERSAL: Object.freeze({
    severity: "notice",
    title: "Family field unavailable",
    message: "The configured family field was unavailable, so corporate-family discovery used bounded ParentId traversal.",
    impact: "The result is a technical corporate-family map, not a legal-subsidiary determination.",
    next_action: "Review the returned Account set before family-wide reads.",
    affected_section: "family",
  }),
});

const SECTION_LABELS = Object.freeze({
  overview: "Account overview",
  family: "Corporate-family accounts",
  opportunities: "Opportunities",
  products: "Opportunity line items",
  team: "Owner hierarchy",
});

function warningForCode(code) {
  if (WARNING_CATALOG[code]) return { code, ...WARNING_CATALOG[code] };
  if (code.startsWith("OPTIONAL_FIELD_UNAVAILABLE:")) {
    const field = sanitizeText(code.slice("OPTIONAL_FIELD_UNAVAILABLE:".length));
    return {
      code,
      severity: "notice",
      title: "Optional field unavailable",
      message: `Salesforce did not expose optional field ${field}; no value was inferred.`,
      impact: "The related optional value is absent rather than guessed.",
      next_action: "Confirm field availability and permissions if the value is required.",
      affected_section: field.startsWith("Account.") ? "overview" : "opportunities",
    };
  }
  return {
    code: sanitizeText(code),
    severity: "warning",
    title: "Unrecognized warning",
    message: "Salesforce returned an unrecognized stable warning that requires review.",
    impact: "No automated interpretation was applied.",
    next_action: "Review the warning code before relying on the affected result.",
    affected_section: null,
  };
}

function canonicalNumberParts(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new SafetyError("INVALID_MONETARY_VALUE", "Monetary summaries require finite numeric values");
  }
  const source = Object.is(value, -0) ? "0" : String(value);
  const match = /^(-?)(\d+)(?:\.(\d+))?(?:e([+-]?\d+))?$/i.exec(source);
  if (!match) throw new SafetyError("INVALID_MONETARY_VALUE", "Monetary value has an unsupported representation");
  const sign = match[1] === "-" ? -1n : 1n;
  const digits = `${match[2]}${match[3] ?? ""}`.replace(/^0+(?=\d)/, "");
  const exponent = Number(match[4] ?? 0);
  const scale = Math.max(0, (match[3]?.length ?? 0) - exponent);
  const shiftedDigits = exponent > (match[3]?.length ?? 0)
    ? `${digits}${"0".repeat(exponent - (match[3]?.length ?? 0))}`
    : digits;
  return { coefficient: sign * BigInt(shiftedDigits || "0"), scale };
}

function exactDecimalSum(values) {
  if (!values.length) return null;
  const parts = values.map(canonicalNumberParts);
  const scale = Math.max(...parts.map((part) => part.scale));
  const total = parts.reduce(
    (sum, part) => sum + part.coefficient * (10n ** BigInt(scale - part.scale)),
    0n,
  );
  const negative = total < 0n;
  const absolute = (negative ? -total : total).toString().padStart(scale + 1, "0");
  const rendered = scale === 0
    ? absolute
    : `${absolute.slice(0, -scale)}.${absolute.slice(-scale)}`.replace(/\.?0+$/, "");
  return `${negative ? "-" : ""}${rendered || "0"}`;
}

function uniqueContextRows(rows, label) {
  if (!Array.isArray(rows)) {
    throw new SafetyError("INVALID_RELATIONSHIP_CONTEXT", `${label} must be an array`);
  }
  const mapped = new Map();
  for (const row of rows) {
    if (!row || typeof row !== "object" || Array.isArray(row)
      || typeof row.Id !== "string" || mapped.has(row.Id)) {
      throw new SafetyError(
        "INVALID_RELATIONSHIP_CONTEXT",
        `${label} contains an invalid or duplicate ID`,
      );
    }
    mapped.set(row.Id, row);
  }
  return mapped;
}

function validateRelationshipBinding(
  binding,
  {
    plan,
    profile,
    familyApprovalReceipt,
  },
) {
  assertExactKeys(
    binding,
    [
      "source_profile_digest",
      "read_plan_digest",
      "family_approval_receipt_digest",
      "org_identity_digest",
      "binding_digest",
    ],
    [
      "source_profile_digest",
      "read_plan_digest",
      "family_approval_receipt_digest",
      "org_identity_digest",
      "binding_digest",
    ],
    "relationship_context.binding",
  );
  const core = {
    source_profile_digest: binding.source_profile_digest,
    read_plan_digest: binding.read_plan_digest,
    family_approval_receipt_digest:
      binding.family_approval_receipt_digest,
    org_identity_digest: binding.org_identity_digest,
  };
  const expected = {
    source_profile_digest: digest(profile),
    read_plan_digest: readPlanDigest(plan),
    family_approval_receipt_digest:
      familyApprovalReceipt?.receipt_digest ?? null,
    org_identity_digest: digest(plan.org_identity),
  };
  if (Object.entries(expected).some(([key, value]) => core[key] !== value)
    || binding.binding_digest !== digest(core)) {
    throw new SafetyError(
      "RELATIONSHIP_CONTEXT_MISMATCH",
      "Relationship context does not bind the current profile, plan, org, and approval",
    );
  }
}

function relationshipMaps(
  context,
  {
    plan,
    profile,
    familyApprovalReceipt,
  },
) {
  if (context === null || context === undefined) return null;
  if (!context || typeof context !== "object" || Array.isArray(context)
    || context.schema_version !== PROFILE_HYDRATION_SCHEMA
    || context.classification !== CLASSIFICATION
    || !Number.isInteger(context.query_count)
    || context.query_count < 0) {
    throw new SafetyError(
      "INVALID_RELATIONSHIP_CONTEXT",
      "Relationship context metadata is invalid",
    );
  }
  assertExactKeys(
    context,
    [
      "schema_version",
      "classification",
      "binding",
      "accounts",
      "opportunities",
      "product_opportunities",
      "users",
      "query_count",
    ],
    [
      "schema_version",
      "classification",
      "binding",
      "accounts",
      "opportunities",
      "product_opportunities",
      "users",
      "query_count",
    ],
    "relationship_context",
  );
  validateRelationshipBinding(context.binding, {
    plan,
    profile,
    familyApprovalReceipt,
  });
  uniqueContextRows(
    context.product_opportunities,
    "relationship_context.product_opportunities",
  );
  return {
    accounts: uniqueContextRows(context.accounts, "relationship_context.accounts"),
    opportunities: uniqueContextRows(
      context.opportunities,
      "relationship_context.opportunities",
    ),
    users: uniqueContextRows(context.users, "relationship_context.users"),
    queryCount: context.query_count,
  };
}

function requireContextRow(map, id, label) {
  const row = map.get(id);
  if (!row) {
    throw new SafetyError(
      "RELATIONSHIP_CONTEXT_INCOMPLETE",
      `${label} was not hydrated for deterministic presentation`,
    );
  }
  return row;
}

function enrichAccount(account, maps) {
  if (!maps) return {
    ...account,
    ParentName: null,
    OwnerName: null,
    OwnerTitle: null,
    CSMName: null,
    TechnicalAdvisorName: null,
    PreSalesName: null,
  };
  const context = requireContextRow(maps.accounts, account.Id, "Account");
  if (context.Name !== account.Name
    || (context.Parent?.Id ?? null) !== account.ParentId
    || context.Owner?.Id !== account.OwnerId) {
    throw new SafetyError(
      "PROFILE_PLAN_MISMATCH",
      "Account relationship context no longer matches the completed profile",
    );
  }
  const roleBindings = [
    ["CSM__c", "csm", "CSMName"],
    ["Support_Technical_Advisor__c", "technical_advisor", "TechnicalAdvisorName"],
    ["PreSales__c", "presales", "PreSalesName"],
  ];
  const roleNames = {};
  for (const [field, roleKey, outputKey] of roleBindings) {
    const role = context.Roles?.[roleKey];
    const fieldPresent = field in account;
    if (!role
      || role.available !== fieldPresent
      || (fieldPresent && (role.user?.Id ?? null) !== account[field])) {
      throw new SafetyError(
        "PROFILE_PLAN_MISMATCH",
        `Account ${roleKey} context no longer matches the completed profile`,
      );
    }
    roleNames[outputKey] = role.user?.Name ?? null;
  }
  return {
    ...account,
    ParentName: context.Parent?.Name ?? null,
    OwnerName: context.Owner.Name,
    OwnerTitle: context.Owner.Title,
    ...roleNames,
  };
}

function enrichRelationships(
  plan,
  profile,
  relationshipContext,
  familyApprovalReceipt,
) {
  const maps = relationshipMaps(relationshipContext, {
    plan,
    profile,
    familyApprovalReceipt,
  });
  // The family list intentionally carries only the relationship-safe core
  // fields. Preserve the richer selected Account row when the same ID appears
  // in both collections so optional role-field availability stays bound to
  // the profile that was actually completed.
  const accounts = new Map([
    ...profile.accounts.map((account) => [account.Id, account]),
    [profile.selected_account.Id, profile.selected_account],
  ]);
  const users = new Map(profile.team.map((user) => [user.Id, user]));
  const opportunities = new Map(
    profile.opportunities.map((opportunity) => [opportunity.Id, opportunity]),
  );

  const enrichedAccounts = [...accounts.values()].map((account) => {
    if (maps) return enrichAccount(account, maps);
    return {
      ...account,
      ParentName: accounts.get(account.ParentId)?.Name ?? null,
      OwnerName: users.get(account.OwnerId)?.Name ?? null,
      OwnerTitle: users.get(account.OwnerId)?.Title ?? null,
      CSMName: null,
      TechnicalAdvisorName: null,
      PreSalesName: null,
    };
  });
  const enrichedOpportunities = profile.opportunities.map((opportunity) => {
    if (!maps) {
      return {
        ...opportunity,
        AccountName: accounts.get(opportunity.AccountId)?.Name ?? null,
        OwnerName: users.get(opportunity.OwnerId)?.Name ?? null,
        OwnerTitle: users.get(opportunity.OwnerId)?.Title ?? null,
      };
    }
    const context = requireContextRow(
      maps.opportunities,
      opportunity.Id,
      "Opportunity",
    );
    if (context.Name !== opportunity.Name
      || context.Account?.Id !== opportunity.AccountId
      || context.Owner?.Id !== opportunity.OwnerId) {
      throw new SafetyError(
        "PROFILE_PLAN_MISMATCH",
        "Opportunity relationship context no longer matches the completed profile",
      );
    }
    return {
      ...opportunity,
      AccountName: context.Account.Name,
      OwnerName: context.Owner.Name,
      OwnerTitle: context.Owner.Title,
    };
  });
  const lineItems = profile.products.map((item) => {
    const opportunity = maps
      ? requireContextRow(
        maps.opportunities,
        item.OpportunityId,
        "Opportunity line-item parent Opportunity",
      )
      : opportunities.get(item.OpportunityId);
    return {
      ...item,
      OpportunityName: opportunity?.Name ?? null,
      AccountId: maps ? opportunity.Account?.Id : opportunity?.AccountId ?? null,
      AccountName: maps
        ? opportunity.Account?.Name
        : accounts.get(opportunity?.AccountId)?.Name ?? null,
    };
  });
  const team = profile.team.map((user) => {
    if (!maps) {
      return {
        ...user,
        ManagerName: users.get(user.ManagerId)?.Name ?? null,
        ManagerTitle: users.get(user.ManagerId)?.Title ?? null,
      };
    }
    const context = requireContextRow(maps.users, user.Id, "Team User");
    if (context.Name !== user.Name
      || context.Title !== user.Title
      || context.ManagerId !== user.ManagerId) {
      throw new SafetyError(
        "PROFILE_PLAN_MISMATCH",
        "Team relationship context no longer matches the completed profile",
      );
    }
    const missingAllowedManager = context.Manager === null
      && user.ManagerId !== null
      && profile.warnings.includes("MANAGER_HIERARCHY_INCOMPLETE");
    if ((user.ManagerId === null && context.Manager !== null)
      || (user.ManagerId !== null
        && context.Manager?.Id !== user.ManagerId
        && !missingAllowedManager)) {
      throw new SafetyError(
        "PROFILE_PLAN_MISMATCH",
        "Team manager context no longer matches the completed profile",
      );
    }
    return {
      ...user,
      ManagerName: context.Manager?.Name ?? null,
      ManagerTitle: context.Manager?.Title ?? null,
    };
  });
  return {
    selectedAccount: enrichedAccounts.find((account) => account.Id === profile.selected_account.Id),
    accounts: enrichedAccounts,
    opportunities: enrichedOpportunities,
    lineItems,
    team,
    hydrationQueryCount: maps?.queryCount ?? 0,
  };
}

function sectionRecords(section, related) {
  if (section === "overview") return [related.selectedAccount];
  if (section === "family") return related.accounts;
  if (section === "opportunities") return related.opportunities;
  if (section === "products") return related.lineItems;
  return related.team;
}

function buildSections(plan, profile, related) {
  const managerIncomplete = profile.warnings.includes("MANAGER_HIERARCHY_INCOMPLETE");
  return Object.fromEntries(PROFILE_SECTIONS.map((section) => {
    const requested = plan.requested_sections.includes(section);
    const records = requested ? sectionRecords(section, related) : [];
    let state = requested ? (records.length ? "complete" : "empty") : "not_requested";
    const reasonCodes = [];
    if (section === "team" && requested && managerIncomplete) {
      state = "incomplete";
      reasonCodes.push(...profile.warnings.filter((code) =>
        ["MANAGER_DEPTH_LIMIT_REACHED", "MANAGER_CYCLE_DETECTED", "MANAGER_HIERARCHY_INCOMPLETE"].includes(code)));
    }
    return [section, {
      label: SECTION_LABELS[section],
      state,
      record_count: records.length,
      reason_codes: [...new Set(reasonCodes)],
      records,
    }];
  }));
}

function monetaryCategory(requested, records, valueKey) {
  if (!requested) {
    return {
      state: "not_requested",
      record_count: null,
      value_present_count: null,
      value_missing_count: null,
      sum_of_returned: null,
    };
  }
  const values = records.flatMap((item) => item[valueKey] === null ? [] : [item[valueKey]]);
  return {
    state: records.length ? "complete" : "empty",
    record_count: records.length,
    value_present_count: values.length,
    value_missing_count: records.length - values.length,
    sum_of_returned: exactDecimalSum(values),
  };
}

function buildCurrencySummaries(plan, profile) {
  const currencies = new Set([
    ...profile.opportunities.map((item) => item.CurrencyIsoCode),
    ...profile.products.map((item) => item.CurrencyIsoCode),
  ].filter(Boolean));
  return [...currencies].sort().map((currency) => {
    const opportunities = profile.opportunities.filter((item) => item.CurrencyIsoCode === currency);
    const lineItems = profile.products.filter((item) => item.CurrencyIsoCode === currency);
    return {
      currency_iso_code: currency,
      opportunities: monetaryCategory(
        plan.requested_sections.includes("opportunities"),
        opportunities,
        "Amount",
      ),
      opportunity_line_items: monetaryCategory(
        plan.requested_sections.includes("products"),
        lineItems,
        "TotalPrice",
      ),
    };
  });
}

function buildDecisionSummary(plan, related) {
  const opportunityLabel = plan.opportunity_scope === "all"
    ? "all Opportunities"
    : `${plan.opportunity_scope} Opportunities`;
  const nextCloseDate = related.opportunities
    .map((item) => item.CloseDate)
    .filter(Boolean)
    .sort()[0] ?? null;
  const parts = [
    `${related.selectedAccount.Name}: ${plan.scope === "corporate_family" ? "corporate-family" : "selected-account"} ${plan.preset} profile`,
  ];
  if (plan.requested_sections.includes("opportunities")) {
    parts.push(`${related.opportunities.length} ${opportunityLabel}`);
    if (nextCloseDate) parts.push(`next close date ${nextCloseDate}`);
  }
  if (plan.requested_sections.includes("products")) {
    parts.push(`${related.lineItems.length} Opportunity line items`);
  }
  if (plan.requested_sections.includes("team")) {
    parts.push(`${related.team.length} users in the returned owner hierarchy`);
  }
  return `${parts.join("; ")}.`;
}

export function buildProfileView({
  plan,
  profile,
  certificationState = "offline_validated",
  relationshipContext = null,
  familyApprovalReceipt = null,
}) {
  validateReadPlan(plan);
  validateCompleteProfile(profile);
  if (!CERTIFICATION_STATES.includes(certificationState)) {
    throw new SafetyError("INVALID_CERTIFICATION_STATE", "certification state is unsupported");
  }
  if (profile.selected_account.Id !== plan.selected_account?.Id
    || profile.scope !== plan.scope
    || profile.opportunity_scope !== plan.opportunity_scope) {
    throw new SafetyError("PROFILE_PLAN_MISMATCH", "Completed profile does not match the approved read plan");
  }
  const sectionPayloads = {
    family: profile.accounts,
    opportunities: profile.opportunities,
    products: profile.products,
    team: profile.team,
  };
  for (const [section, records] of Object.entries(sectionPayloads)) {
    if (!plan.requested_sections.includes(section) && records.length) {
      throw new SafetyError(
        "PROFILE_PLAN_MISMATCH",
        `Completed profile returned unrequested ${SECTION_LABELS[section]}`,
      );
    }
  }

  const related = enrichRelationships(
    plan,
    profile,
    relationshipContext,
    familyApprovalReceipt,
  );
  const warnings = [...new Set(profile.warnings)].map(warningForCode);
  const view = {
    schema_version: CONTRACTS.profileView,
    classification: CLASSIFICATION,
    status: "complete",
    certification_state: certificationState,
    plan: {
      preset: plan.preset,
      requested_sections: [...plan.requested_sections],
      scope: plan.scope,
      opportunity_scope: plan.opportunity_scope,
      filters: {
        close_date_from: plan.filters.close_date_from,
        close_date_to: plan.filters.close_date_to,
        stages: [...plan.filters.stages],
      },
      field_map_version: plan.field_map_version,
      output_type: plan.output_type,
    },
    decision_summary: buildDecisionSummary(plan, related),
    selected_account: related.selectedAccount,
    sections: buildSections(plan, profile, related),
    currency_summaries: buildCurrencySummaries(plan, profile),
    warnings,
    source: {
      read_plan_digest: readPlanDigest(plan),
      profile_digest: digest(profile),
      query_count: profile.query_count + related.hydrationQueryCount,
    },
  };
  return { ...view, view_digest: digest(view) };
}

export const profileViewInternals = Object.freeze({
  exactDecimalSum,
  warningForCode,
});

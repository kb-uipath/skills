import {
  ACCOUNT_ID,
  CLASSIFICATION,
  CONTRACTS,
  LINE_ITEM_ID,
  OPPORTUNITY_ID,
  PRICEBOOK_ENTRY_ID,
  PRODUCT_ID,
  USER_ID,
} from "./constants.mjs";
import { assertExactKeys, digest, SafetyError, validateAlias } from "./security.mjs";

export function validateSchema(input, expected) {
  if (input.schema_version !== expected) {
    throw new SafetyError("CONTRACT_VERSION_MISMATCH", `Expected schema_version ${expected}`);
  }
}

export function validatePreflightRequest(input) {
  assertExactKeys(input, ["schema_version", "target_org"], ["schema_version", "target_org"], "request");
  validateSchema(input, CONTRACTS.preflightRequest);
  validateAlias(input.target_org);
  return input;
}

export function validateResolveRequest(input) {
  assertExactKeys(
    input,
    ["schema_version", "target_org", "confirmed_org_digest", "selector"],
    ["schema_version", "target_org", "confirmed_org_digest", "selector"],
    "request",
  );
  validateSchema(input, CONTRACTS.resolveRequest);
  validateAlias(input.target_org);
  if (!/^[a-f0-9]{64}$/.test(input.confirmed_org_digest)) {
    throw new SafetyError("INVALID_CONFIRMATION_DIGEST", "confirmed_org_digest must be a SHA-256 digest");
  }
  assertExactKeys(input.selector, ["mode", "value"], ["mode", "value"], "selector");
  if (!["id", "exact_name", "prefix"].includes(input.selector.mode)) {
    throw new SafetyError("INVALID_SELECTOR", "selector.mode must be id, exact_name, or prefix");
  }
  if (typeof input.selector.value !== "string" || input.selector.value.length < 1 || input.selector.value.length > 255) {
    throw new SafetyError("INVALID_SELECTOR", "selector.value must be 1 to 255 characters");
  }
  if (input.selector.mode === "id" && !ACCOUNT_ID.test(input.selector.value)) {
    throw new SafetyError("INVALID_ACCOUNT_ID", "Account ID must begin 001 and contain 15 or 18 Salesforce ID characters");
  }
  return input;
}

export function validateProfileRequest(input) {
  assertExactKeys(
    input,
    ["schema_version", "target_org", "confirmed_org_digest", "account_receipt", "sections", "scope", "opportunity_scope", "confirmed_family_digest"],
    ["schema_version", "target_org", "confirmed_org_digest", "account_receipt"],
    "request",
  );
  validateSchema(input, CONTRACTS.profileRequest);
  validateAlias(input.target_org);
  if (!/^[a-f0-9]{64}$/.test(input.confirmed_org_digest)) {
    throw new SafetyError("INVALID_CONFIRMATION_DIGEST", "confirmed_org_digest must be a SHA-256 digest");
  }
  assertExactKeys(
    input.account_receipt,
    ["schema_version", "classification", "org_digest", "account", "receipt_digest"],
    ["schema_version", "classification", "org_digest", "account", "receipt_digest"],
    "account_receipt",
  );
  validateSchema(input.account_receipt, CONTRACTS.accountReceipt);
  assertExactKeys(input.account_receipt.account, ["Id", "Name"], ["Id", "Name"], "account_receipt.account");
  if (input.account_receipt.classification !== CLASSIFICATION
    || !/^[a-f0-9]{64}$/.test(input.account_receipt.org_digest)
    || !/^[a-f0-9]{64}$/.test(input.account_receipt.receipt_digest)
    || !ACCOUNT_ID.test(input.account_receipt.account.Id)
    || typeof input.account_receipt.account.Name !== "string"
    || input.account_receipt.account.Name.length < 1
    || input.account_receipt.account.Name.length > 255) {
    throw new SafetyError("INVALID_ACCOUNT_RECEIPT", "Account receipt is invalid");
  }
  const sections = input.sections ?? ["overview"];
  if (!Array.isArray(sections) || sections.length === 0 || sections.some((item) => !["overview", "family", "opportunities", "products", "team"].includes(item))) {
    throw new SafetyError("INVALID_SECTIONS", "sections contains an unsupported value");
  }
  if (new Set(sections).size !== sections.length) throw new SafetyError("INVALID_SECTIONS", "sections must be unique");
  const scope = input.scope ?? "selected_account";
  if (!["selected_account", "corporate_family"].includes(scope)) throw new SafetyError("INVALID_SCOPE", "scope is invalid");
  const opportunityScope = input.opportunity_scope ?? "open";
  if (!["open", "all", "closed"].includes(opportunityScope)) throw new SafetyError("INVALID_OPPORTUNITY_SCOPE", "opportunity_scope is invalid");
  return { ...input, sections, scope, opportunity_scope: opportunityScope };
}

export function validateRenderRequest(input) {
  assertExactKeys(input, ["schema_version", "profile"], ["schema_version", "profile"], "request");
  validateSchema(input, CONTRACTS.renderRequest);
  validateCompleteProfile(input.profile);
  return input;
}

export function validateCompleteProfile(profile) {
  if (profile?.schema_version !== CONTRACTS.profileResult || profile?.classification !== CLASSIFICATION) {
    throw new SafetyError("INVALID_PROFILE_RESULT", "render requires a confidential profile result v1");
  }
  assertExactKeys(
    profile,
    ["schema_version", "classification", "status", "selected_account", "scope", "opportunity_scope", "accounts", "family_confirmation", "opportunities", "products", "team", "currencies", "warnings", "query_count"],
    ["schema_version", "classification", "status", "selected_account", "scope", "opportunity_scope", "accounts", "family_confirmation", "opportunities", "products", "team", "currencies", "warnings", "query_count"],
    "profile",
  );
  if (profile.status !== "complete") throw new SafetyError("PROFILE_NOT_COMPLETE", "render accepts only a complete final profile");
  if (!["selected_account", "corporate_family"].includes(profile.scope)
    || !["open", "all", "closed"].includes(profile.opportunity_scope)
    || !Number.isInteger(profile.query_count) || profile.query_count < 0) {
    throw new SafetyError("INVALID_PROFILE_RESULT", "profile metadata is invalid");
  }
  for (const key of ["accounts", "opportunities", "products", "team", "currencies", "warnings"]) {
    if (!Array.isArray(profile[key])) throw new SafetyError("INVALID_PROFILE_RESULT", `profile.${key} must be an array`);
  }
  validateRenderedAccount(profile.selected_account, "selected_account");
  for (const account of profile.accounts) validateRenderedAccount(account, "accounts[]");
  for (const opportunity of profile.opportunities) {
    assertExactKeys(
      opportunity,
      ["Id", "Name", "AccountId", "OwnerId", "StageName", "Amount", "CloseDate", "IsClosed", "IsWon", "CurrencyIsoCode", "HasOpportunityLineItem", "Type", "Deal_Type__c", "Contract_Start_Date__c", "Contract_End_Date__c", "Renewal_Status__c"],
      ["Id", "Name", "AccountId", "OwnerId", "StageName", "Amount", "CloseDate", "IsClosed", "IsWon", "CurrencyIsoCode", "HasOpportunityLineItem"],
      "opportunities[]",
    );
    if (!OPPORTUNITY_ID.test(opportunity.Id) || !ACCOUNT_ID.test(opportunity.AccountId) || !USER_ID.test(opportunity.OwnerId)
      || typeof opportunity.Name !== "string"
      || (opportunity.Amount !== null && (typeof opportunity.Amount !== "number" || !Number.isFinite(opportunity.Amount)))
      || typeof opportunity.IsClosed !== "boolean" || typeof opportunity.IsWon !== "boolean"
      || typeof opportunity.HasOpportunityLineItem !== "boolean"
      || typeof opportunity.StageName !== "string" || typeof opportunity.CloseDate !== "string"
      || typeof opportunity.CurrencyIsoCode !== "string"
      || ["Type", "Deal_Type__c", "Contract_Start_Date__c", "Contract_End_Date__c", "Renewal_Status__c"]
        .some((key) => key in opportunity && opportunity[key] !== null && typeof opportunity[key] !== "string")) {
      throw new SafetyError("INVALID_PROFILE_RESULT", "Opportunity relationship or status fields are invalid");
    }
  }
  for (const product of profile.products) {
    assertExactKeys(
      product,
      ["Id", "OpportunityId", "Quantity", "UnitPrice", "TotalPrice", "CurrencyIsoCode", "PricebookEntryId", "ServiceDate", "Product2Id", "ProductName"],
      ["Id", "OpportunityId", "Quantity", "UnitPrice", "TotalPrice", "CurrencyIsoCode", "PricebookEntryId", "Product2Id", "ProductName"],
      "products[]",
    );
    if (!LINE_ITEM_ID.test(product.Id) || !OPPORTUNITY_ID.test(product.OpportunityId)
      || !PRICEBOOK_ENTRY_ID.test(product.PricebookEntryId) || !PRODUCT_ID.test(product.Product2Id)
      || (product.Quantity !== null && (typeof product.Quantity !== "number" || !Number.isFinite(product.Quantity)))
      || (product.UnitPrice !== null && (typeof product.UnitPrice !== "number" || !Number.isFinite(product.UnitPrice)))
      || (product.TotalPrice !== null && (typeof product.TotalPrice !== "number" || !Number.isFinite(product.TotalPrice)))
      || typeof product.CurrencyIsoCode !== "string"
      || typeof product.ProductName !== "string"
      || ("ServiceDate" in product && product.ServiceDate !== null && typeof product.ServiceDate !== "string")) {
      throw new SafetyError("INVALID_PROFILE_RESULT", "Product relationship fields are invalid");
    }
  }
  for (const user of profile.team) {
    assertExactKeys(user, ["Id", "Name", "Title", "ManagerId"], ["Id", "Name", "Title", "ManagerId"], "team[]");
    if (!USER_ID.test(user.Id) || typeof user.Name !== "string"
      || (user.Title !== null && typeof user.Title !== "string")
      || (user.ManagerId !== null && !USER_ID.test(user.ManagerId))) {
      throw new SafetyError("INVALID_PROFILE_RESULT", "Team relationship fields are invalid");
    }
  }
  if (profile.currencies.some((value) => typeof value !== "string")
    || profile.warnings.some((value) => typeof value !== "string")) {
    throw new SafetyError("INVALID_PROFILE_RESULT", "Profile warnings or currencies are invalid");
  }
  if (profile.family_confirmation !== null) {
    assertExactKeys(profile.family_confirmation, ["account_ids", "family_digest"], ["account_ids", "family_digest"], "family_confirmation");
    if (!Array.isArray(profile.family_confirmation.account_ids)
      || profile.family_confirmation.account_ids.some((id) => !ACCOUNT_ID.test(id))
      || !/^[a-f0-9]{64}$/.test(profile.family_confirmation.family_digest)) {
      throw new SafetyError("INVALID_PROFILE_RESULT", "Family confirmation is invalid");
    }
  }
  return profile;
}

function validateRenderedAccount(account, label) {
  assertExactKeys(
    account,
    ["Id", "Name", "ParentId", "OwnerId", "Ultimate_Parent_name__c", "Classification__c", "Region__c", "Geo__c", "Contract_End_Date__c", "Support_Type__c", "Support_Status__c", "CSM__c", "Support_Technical_Advisor__c", "PreSales__c"],
    ["Id", "Name", "ParentId", "OwnerId"],
    label,
  );
  if (!ACCOUNT_ID.test(account.Id) || !USER_ID.test(account.OwnerId)
    || typeof account.Name !== "string"
    || account.Name.length < 1
    || (account.ParentId !== null && !ACCOUNT_ID.test(account.ParentId))
    || ["Ultimate_Parent_name__c", "Classification__c", "Region__c", "Geo__c", "Contract_End_Date__c", "Support_Type__c", "Support_Status__c"]
      .some((key) => key in account && account[key] !== null && typeof account[key] !== "string")) {
    throw new SafetyError("INVALID_PROFILE_RESULT", `${label} relationship fields are invalid`);
  }
  for (const key of ["CSM__c", "Support_Technical_Advisor__c", "PreSales__c"]) {
    if (key in account && account[key] !== null && !USER_ID.test(account[key])) {
      throw new SafetyError("INVALID_PROFILE_RESULT", `${label}.${key} must be a Salesforce User ID`);
    }
  }
}

export function orgDigest(targetOrg, identity, runtimeAttestationDigest = null) {
  return digest({
    target_org: targetOrg,
    org_id: identity.org_id,
    username: identity.username,
    instance_url: identity.instance_url,
    runtime_attestation_digest: runtimeAttestationDigest,
  });
}

export function validateConfirmedOrg(targetOrg, identity, confirmedDigest, runtimeAttestationDigest = null) {
  const current = orgDigest(targetOrg, identity, runtimeAttestationDigest);
  if (current !== confirmedDigest) throw new SafetyError("ORG_IDENTITY_MISMATCH", "Current Salesforce org identity does not match the confirmed receipt");
  return current;
}

export function validateIds(values, pattern, label) {
  if (!Array.isArray(values) || values.some((value) => !pattern.test(value))) {
    throw new SafetyError("INVALID_RELATIONSHIP_ID", `${label} contains an invalid Salesforce ID`);
  }
}

export const idPatterns = { account: ACCOUNT_ID, opportunity: OPPORTUNITY_ID, user: USER_ID };

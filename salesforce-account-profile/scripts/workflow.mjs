import {
  ACCOUNT_ID,
  CAPS,
  CLASSIFICATION,
  CONTRACTS,
  FIELD_MAP_VERSION,
  OPPORTUNITY_ID,
  LINE_ITEM_ID,
  PRICEBOOK_ENTRY_ID,
  PROFILE_SECTIONS,
  PRODUCT_ID,
  USER_ID,
  WARNING_ANNUALIZATION,
} from "./constants.mjs";
import {
  orgDigest,
  validateConfirmedOrg,
  validateCompleteProfile,
  validatePreflightRequest,
  validateProfileRequest,
  validateRenderRequest,
  validateResolveRequest,
} from "./contracts.mjs";
import { buildRenderResult } from "./render.mjs";
import { batchIds, createProductionSfClient, SfClient } from "./sf-client.mjs";
import { digest, escapeSoqlLikePrefix, escapeSoqlLiteral, SafetyError, sanitizeText } from "./security.mjs";

export const FIELD_POLICY = Object.freeze({
  Account: {
    required: ["Id", "Name", "ParentId", "OwnerId"],
    optional: ["Ultimate_Parent_name__c", "Classification__c", "Region__c", "Geo__c", "Contract_End_Date__c", "Support_Type__c", "Support_Status__c", "CSM__c", "Support_Technical_Advisor__c", "PreSales__c"],
  },
  Opportunity: {
    required: ["Id", "Name", "AccountId", "OwnerId", "StageName", "Amount", "CloseDate", "IsClosed", "IsWon", "CurrencyIsoCode", "HasOpportunityLineItem"],
    optional: ["Type", "Deal_Type__c", "Contract_Start_Date__c", "Contract_End_Date__c", "Renewal_Status__c"],
  },
  OpportunityLineItem: {
    required: ["Id", "OpportunityId", "Quantity", "UnitPrice", "TotalPrice", "CurrencyIsoCode", "PricebookEntryId"],
    optional: ["ServiceDate"],
  },
  PricebookEntry: { required: ["Id", "Product2Id"], optional: [] },
  Product2: { required: ["Id", "Name"], optional: [] },
  User: { required: ["Id", "Name", "Title", "ManagerId"], optional: [] },
});
const ACCOUNT_REQUIRED = FIELD_POLICY.Account.required;
const ACCOUNT_OPTIONAL = FIELD_POLICY.Account.optional;
const OPPORTUNITY_REQUIRED = FIELD_POLICY.Opportunity.required;
const OPPORTUNITY_OPTIONAL = FIELD_POLICY.Opportunity.optional;
const OPPORTUNITY_PRODUCT_LINK_REQUIRED = ["Id", "AccountId", "IsClosed", "IsWon", "CurrencyIsoCode"];
const LINE_ITEM_REQUIRED = FIELD_POLICY.OpportunityLineItem.required;
const LINE_ITEM_OPTIONAL = FIELD_POLICY.OpportunityLineItem.optional;
const PRICEBOOK_ENTRY_REQUIRED = FIELD_POLICY.PricebookEntry.required;
const USER_REQUIRED = FIELD_POLICY.User.required;
const ACCOUNT_USER_REFERENCE_FIELDS = Object.freeze([
  "CSM__c",
  "Support_Technical_Advisor__c",
  "PreSales__c",
]);
export const FIELD_EXPECTATIONS = Object.freeze({
  Account: {
    Id: { types: ["id"] }, Name: { types: ["string"] },
    ParentId: { types: ["reference"], referenceTo: "Account" },
    OwnerId: { types: ["reference"], referenceTo: "User" },
    Ultimate_Parent_name__c: { types: ["string"] },
    Classification__c: { types: ["string", "picklist"] },
    Region__c: { types: ["string", "picklist"] },
    Geo__c: { types: ["string", "picklist"] },
    Contract_End_Date__c: { types: ["date", "datetime"] },
    Support_Type__c: { types: ["string", "picklist"] },
    Support_Status__c: { types: ["string", "picklist"] },
    CSM__c: { types: ["reference"], referenceTo: "User" },
    Support_Technical_Advisor__c: { types: ["reference"], referenceTo: "User" },
    PreSales__c: { types: ["reference"], referenceTo: "User" },
  },
  Opportunity: {
    Id: { types: ["id"] }, Name: { types: ["string"] },
    AccountId: { types: ["reference"], referenceTo: "Account" },
    OwnerId: { types: ["reference"], referenceTo: "User" }, IsClosed: { types: ["boolean"] },
    IsWon: { types: ["boolean"] }, Amount: { types: ["currency", "double"] },
    StageName: { types: ["string", "picklist"] }, CloseDate: { types: ["date"] },
    CurrencyIsoCode: { types: ["picklist", "string"] },
    HasOpportunityLineItem: { types: ["boolean"] },
    Type: { types: ["picklist", "string"] },
    Deal_Type__c: { types: ["picklist", "string"] },
    Contract_Start_Date__c: { types: ["date", "datetime"] },
    Contract_End_Date__c: { types: ["date", "datetime"] },
    Renewal_Status__c: { types: ["picklist", "string"] },
  },
  OpportunityLineItem: {
    Id: { types: ["id"] }, OpportunityId: { types: ["reference"], referenceTo: "Opportunity" },
    PricebookEntryId: { types: ["reference"], referenceTo: "PricebookEntry", relationshipName: "PricebookEntry" },
    Quantity: { types: ["double", "int"] }, UnitPrice: { types: ["currency", "double"] },
    TotalPrice: { types: ["currency", "double"] },
    CurrencyIsoCode: { types: ["picklist", "string"] },
    ServiceDate: { types: ["date"] },
  },
  PricebookEntry: {
    Id: { types: ["id"] },
    Product2Id: { types: ["reference"], referenceTo: "Product2", relationshipName: "Product2" },
  },
  Product2: { Id: { types: ["id"] }, Name: { types: ["string"] } },
  User: {
    Id: { types: ["id"] }, Name: { types: ["string"] },
    ManagerId: { types: ["reference"], referenceTo: "User" }, Title: { types: ["string"] },
  },
});

function requireFields(describe, required, optional, objectName, warnings) {
  const missing = required.filter((field) => !describe.has(field));
  if (missing.length) {
    throw new SafetyError("SCHEMA_FAILURE", `${objectName} required fields are missing`, { fields: missing });
  }
  for (const field of required) validateFieldMetadata(describe.get(field), FIELD_EXPECTATIONS[objectName]?.[field], objectName);
  const availableOptional = optional.filter((field) => describe.has(field));
  for (const field of availableOptional) validateFieldMetadata(describe.get(field), FIELD_EXPECTATIONS[objectName]?.[field], objectName);
  for (const field of optional.filter((candidate) => !availableOptional.includes(candidate))) {
    warnings.push(`OPTIONAL_FIELD_UNAVAILABLE:${objectName}.${field}`);
  }
  return [...required, ...availableOptional];
}

function validateFieldMetadata(metadata, expectation, objectName) {
  if (!expectation) return;
  if (!expectation.types.includes(metadata.type)) {
    throw new SafetyError("SCHEMA_FAILURE", `${objectName}.${metadata.name} has an incompatible type`);
  }
  if (expectation.referenceTo && !metadata.referenceTo.includes(expectation.referenceTo)) {
    throw new SafetyError("SCHEMA_FAILURE", `${objectName}.${metadata.name} has an incompatible reference target`);
  }
  if (expectation.relationshipName && metadata.relationshipName !== expectation.relationshipName) {
    throw new SafetyError("SCHEMA_FAILURE", `${objectName}.${metadata.name} has an incompatible relationship name`);
  }
}

function requireFilterable(describe, fields, objectName) {
  const invalid = fields.filter((field) => describe.get(field)?.filterable !== true);
  if (invalid.length) throw new SafetyError("SCHEMA_FAILURE", `${objectName} predicate fields are not filterable`, { fields: invalid });
}

function allowlist(record, fields) {
  return Object.fromEntries(fields.map((field) => {
    const value = record[field];
    if (value === null || value === undefined) return [field, null];
    if (typeof value === "string") return [field, sanitizeText(value)];
    if (typeof value === "boolean") return [field, value];
    if (typeof value === "number" && Number.isFinite(value)) return [field, value];
    throw new SafetyError("INVALID_FIELD_TYPE", `${field} returned a non-scalar or non-finite value`);
  }));
}

function enforceCap(records, cap, code) {
  if (records.length > cap) throw new SafetyError(code, `Result exceeded deterministic cap ${cap}`);
}

function idListSoql(ids) {
  return ids.map((id) => `'${id}'`).join(",");
}

function salesforceNameKey(value) {
  return sanitizeText(value).normalize("NFKC").toLocaleLowerCase("en-US");
}

function accountReceipt(orgDigestValue, account) {
  const core = {
    schema_version: CONTRACTS.accountReceipt,
    classification: CLASSIFICATION,
    org_digest: orgDigestValue,
    account: { Id: account.Id, Name: account.Name },
  };
  return { ...core, receipt_digest: digest(core) };
}

function validateAccountRow(account, { expectedId, expectedParentIds } = {}) {
  if (!ACCOUNT_ID.test(account.Id)) throw new SafetyError("RELATIONSHIP_INCONSISTENCY", "Account result contains an invalid ID");
  if (typeof account.Name !== "string" || account.Name.length === 0) {
    throw new SafetyError("INVALID_FIELD_TYPE", "Account Name must be a non-empty string");
  }
  if (expectedId && account.Id !== expectedId) throw new SafetyError("RELATIONSHIP_INCONSISTENCY", "Account result does not match the requested ID");
  if (account.ParentId !== null && !ACCOUNT_ID.test(account.ParentId)) {
    throw new SafetyError("RELATIONSHIP_INCONSISTENCY", "Account result contains an invalid ParentId");
  }
  if (expectedParentIds && !expectedParentIds.includes(account.ParentId)) {
    throw new SafetyError("RELATIONSHIP_INCONSISTENCY", "Child Account ParentId does not match the queried parent batch");
  }
  if (!USER_ID.test(account.OwnerId)) throw new SafetyError("RELATIONSHIP_INCONSISTENCY", "Account result contains an invalid OwnerId");
  for (const field of ACCOUNT_USER_REFERENCE_FIELDS) {
    if (field in account && account[field] !== null && !USER_ID.test(account[field])) {
      throw new SafetyError("RELATIONSHIP_INCONSISTENCY", `Account result contains an invalid ${field} User ID`);
    }
  }
  return account;
}

function validateAccountReceipt(receipt, currentOrgDigest) {
  const core = {
    schema_version: receipt.schema_version,
    classification: receipt.classification,
    org_digest: receipt.org_digest,
    account: receipt.account,
  };
  if (receipt.org_digest !== currentOrgDigest || receipt.receipt_digest !== digest(core)) {
    throw new SafetyError("ACCOUNT_RECEIPT_MISMATCH", "Account receipt integrity or org binding failed");
  }
}

async function createClient(targetOrg, dependencies) {
  if (dependencies.client) return dependencies.client;
  if (dependencies.sfPath) {
    return new SfClient({
      commandSpec: {
        executable: dependencies.sfPath,
        fixedArgs: [],
        attestationDigest: digest({ test_runtime_path: dependencies.sfPath }),
      },
      targetOrg,
      runner: dependencies.runner,
    });
  }
  return await createProductionSfClient({
    targetOrg,
    runner: dependencies.runner,
    runtimeManifestPath: dependencies.runtimeManifestPath,
  });
}

function runtimeDigestFor(client) {
  return client.attestationDigest ?? null;
}

export async function preflight(input, dependencies = {}) {
  validatePreflightRequest(input);
  const client = await createClient(input.target_org, dependencies);
  const identity = await client.orgDisplay();
  const runtimeDigest = runtimeDigestFor(client);
  const confirmedOrgDigest = orgDigest(input.target_org, identity, runtimeDigest);
  return {
    schema_version: CONTRACTS.preflightResult,
    classification: CLASSIFICATION,
    target_org: input.target_org,
    org: {
      org_id: identity.org_id,
      username: identity.username,
      instance_url: identity.instance_url,
      connected_status: identity.connected_status,
    },
    runtime_attestation_digest: runtimeDigest,
    confirmed_org_digest: confirmedOrgDigest,
  };
}

export async function resolve(input, dependencies = {}) {
  validateResolveRequest(input);
  const client = await createClient(input.target_org, dependencies);
  const identity = await client.orgDisplay();
  const currentOrgDigest = validateConfirmedOrg(
    input.target_org,
    identity,
    input.confirmed_org_digest,
    runtimeDigestFor(client),
  );
  const warnings = [];
  const accountDescribe = await client.describe("Account");
  const fields = requireFields(accountDescribe, ACCOUNT_REQUIRED, [], "Account", warnings);
  const { mode, value } = input.selector;
  requireFilterable(accountDescribe, [mode === "id" ? "Id" : "Name"], "Account");
  const clause = mode === "id"
    ? `Id = '${value}'`
    : mode === "exact_name"
      ? `Name = '${escapeSoqlLiteral(value)}'`
      : `Name LIKE '${escapeSoqlLikePrefix(value)}%'`;
  const records = await client.query(`SELECT ${fields.join(", ")} FROM Account WHERE ${clause} ORDER BY Name, Id LIMIT ${CAPS.candidates + 1}`);
  enforceCap(records, CAPS.candidates, "CANDIDATE_CAP_EXCEEDED");
  const candidates = records.map((record) => validateAccountRow(allowlist(record, fields)));
  const expectedNameKey = salesforceNameKey(value);
  if (mode === "id" && candidates.some((candidate) => candidate.Id !== value)) {
    throw new SafetyError("PREDICATE_BINDING_FAILED", "Account ID result did not match the requested ID");
  }
  if (mode === "exact_name" && candidates.some((candidate) => salesforceNameKey(candidate.Name) !== expectedNameKey)) {
    throw new SafetyError("PREDICATE_BINDING_FAILED", "Account name result did not match the exact requested name");
  }
  if (mode === "prefix" && candidates.some((candidate) => !salesforceNameKey(candidate.Name).startsWith(expectedNameKey))) {
    throw new SafetyError("PREDICATE_BINDING_FAILED", "Account prefix result did not match the literal requested prefix");
  }

  if (mode === "prefix") {
    return {
      schema_version: CONTRACTS.resolveResult,
      classification: CLASSIFICATION,
      status: "chooser",
      selector_mode: mode,
      candidates,
      warnings: ["PREFIX_REQUIRES_EXPLICIT_SELECTION"],
      query_count: client.queryCount,
    };
  }
  if (candidates.length === 0) {
    return {
      schema_version: CONTRACTS.resolveResult,
      classification: CLASSIFICATION,
      status: "no_match",
      selector_mode: mode,
      candidates: [],
      warnings,
      query_count: client.queryCount,
    };
  }
  if (candidates.length !== 1) {
    return {
      schema_version: CONTRACTS.resolveResult,
      classification: CLASSIFICATION,
      status: "ambiguous",
      selector_mode: mode,
      candidates,
      warnings: [...warnings, "EXACT_NAME_REQUIRES_EXPLICIT_ID_SELECTION"],
      query_count: client.queryCount,
    };
  }
  return {
    schema_version: CONTRACTS.resolveResult,
    classification: CLASSIFICATION,
    status: "selected",
    selector_mode: mode,
    selected_account: candidates[0],
    account_receipt: accountReceipt(currentOrgDigest, candidates[0]),
    warnings,
    query_count: client.queryCount,
  };
}

async function discoverFamily(client, selected, accountFields, hasUltimate, warnings) {
  if (hasUltimate && selected.Ultimate_Parent_name__c) {
    const exactValue = escapeSoqlLiteral(selected.Ultimate_Parent_name__c);
    const records = await client.query(
      `SELECT ${accountFields.join(", ")} FROM Account WHERE Ultimate_Parent_name__c = '${exactValue}' ORDER BY Id LIMIT ${CAPS.familyAccounts + 1}`,
    );
    enforceCap(records, CAPS.familyAccounts, "FAMILY_ACCOUNT_CAP_EXCEEDED");
    const accounts = records.map((record) => validateAccountRow(allowlist(record, accountFields)));
    const ids = accounts.map((account) => account.Id);
    const expectedFamilyKey = salesforceNameKey(selected.Ultimate_Parent_name__c);
    if (new Set(ids).size !== ids.length
      || accounts.some((account) =>
        typeof account.Ultimate_Parent_name__c !== "string"
        || salesforceNameKey(account.Ultimate_Parent_name__c) !== expectedFamilyKey
      )) {
      throw new SafetyError("FAMILY_INCONSISTENCY", "Corporate-family rows did not bind uniquely to the exact selected family key");
    }
    if (!accounts.some((account) => account.Id === selected.Id)) {
      throw new SafetyError("FAMILY_INCONSISTENCY", "Corporate-family result omitted the selected Account");
    }
    return accounts;
  }

  warnings.push(hasUltimate
    ? "ULTIMATE_PARENT_FIELD_EMPTY_USING_PARENT_TRAVERSAL"
    : "ULTIMATE_PARENT_FIELD_UNAVAILABLE_USING_PARENT_TRAVERSAL");
  const byId = new Map([[selected.Id, selected]]);
  const visitedAncestors = new Set([selected.Id]);
  let root = selected;
  for (let depth = 0; root.ParentId && depth < CAPS.familyDepth; depth += 1) {
    if (!ACCOUNT_ID.test(root.ParentId)) throw new SafetyError("INVALID_RELATIONSHIP_ID", "ParentId is invalid");
    if (visitedAncestors.has(root.ParentId)) {
      throw new SafetyError(
        "FAMILY_DISCOVERY_INCOMPLETE",
        "Corporate-family discovery stopped because ParentId traversal contains a cycle",
        { next_action: "use_selected_account" },
      );
    }
    visitedAncestors.add(root.ParentId);
    const records = await client.query(
      `SELECT ${accountFields.join(", ")} FROM Account WHERE Id = '${root.ParentId}' LIMIT 1`,
    );
    if (records.length !== 1) throw new SafetyError("FAMILY_INCONSISTENCY", "Parent traversal could not resolve exactly one Account");
    root = validateAccountRow(allowlist(records[0], accountFields), { expectedId: root.ParentId });
    byId.set(root.Id, root);
    if (depth === CAPS.familyDepth - 1 && root.ParentId) {
      throw new SafetyError(
        "FAMILY_DISCOVERY_INCOMPLETE",
        "Corporate-family discovery exceeded the ParentId depth limit",
        { next_action: "use_selected_account" },
      );
    }
  }

  let frontier = [root.Id];
  const expanded = new Set();
  for (let depth = 0; frontier.length && depth < CAPS.familyDepth; depth += 1) {
    const next = [];
    for (const batch of batchIds(frontier)) {
      for (const id of batch) expanded.add(id);
      const records = await client.query(
        `SELECT ${accountFields.join(", ")} FROM Account WHERE ParentId IN (${idListSoql(batch)}) ORDER BY Id LIMIT ${CAPS.familyAccounts + 1}`,
      );
      const returnedIds = records.map((record) => record.Id);
      if (new Set(returnedIds).size !== returnedIds.length) {
        throw new SafetyError("FAMILY_INCONSISTENCY", "Parent traversal returned a duplicate Account ID");
      }
      for (const raw of records) {
        const account = validateAccountRow(allowlist(raw, accountFields), { expectedParentIds: batch });
        if (byId.has(account.Id)) {
          const known = byId.get(account.Id);
          if (visitedAncestors.has(account.Id) && known.ParentId === account.ParentId) {
            if (!expanded.has(account.Id) && !next.includes(account.Id)) next.push(account.Id);
            continue;
          }
          throw new SafetyError(
            "FAMILY_DISCOVERY_INCOMPLETE",
            "Corporate-family discovery stopped because ParentId traversal contains a cycle",
            { next_action: "use_selected_account" },
          );
        }
        byId.set(account.Id, account);
        if (!expanded.has(account.Id) && !next.includes(account.Id)) next.push(account.Id);
        enforceCap([...byId.values()], CAPS.familyAccounts, "FAMILY_ACCOUNT_CAP_EXCEEDED");
      }
    }
    frontier = next;
    if (depth === CAPS.familyDepth - 1 && frontier.length) {
      throw new SafetyError(
        "FAMILY_DISCOVERY_INCOMPLETE",
        "Corporate-family discovery exceeded the ParentId depth limit",
        { next_action: "use_selected_account" },
      );
    }
  }
  return [...byId.values()].sort((a, b) => a.Id.localeCompare(b.Id));
}

async function queryOpportunities(client, accountIds, fields, opportunityScope) {
  const all = [];
  const scopeClause = opportunityScope === "open" ? " AND IsClosed = false" : opportunityScope === "closed" ? " AND IsClosed = true" : "";
  const orderBy = fields.includes("CloseDate") ? "CloseDate DESC, Id" : "Id";
  for (const batch of batchIds(accountIds)) {
    const records = await client.query(
      `SELECT ${fields.join(", ")} FROM Opportunity WHERE AccountId IN (${idListSoql(batch)})${scopeClause} ORDER BY ${orderBy} LIMIT ${CAPS.opportunities + 1}`,
    );
    all.push(...records.map((record) => allowlist(record, fields)));
    enforceCap(all, CAPS.opportunities, "OPPORTUNITY_CAP_EXCEEDED");
  }
  if (new Set(all.map((item) => item.Id)).size !== all.length) {
    throw new SafetyError("RELATIONSHIP_INCONSISTENCY", "Opportunity query returned duplicate IDs");
  }
  if (all.some((item) => !accountIds.includes(item.AccountId) || !OPPORTUNITY_ID.test(item.Id))) {
    throw new SafetyError("RELATIONSHIP_INCONSISTENCY", "Opportunity result escaped the confirmed Account-ID set");
  }
  if (all.some((item) =>
    (opportunityScope === "open" && item.IsClosed !== false)
    || (opportunityScope === "closed" && item.IsClosed !== true)
  )) {
    throw new SafetyError("PREDICATE_BINDING_FAILED", "Opportunity result did not match the requested open/closed scope");
  }
  if (all.some((item) =>
    ("OwnerId" in item && !USER_ID.test(item.OwnerId))
    || typeof item.IsClosed !== "boolean"
    || typeof item.IsWon !== "boolean"
    || ("Amount" in item && item.Amount !== null && (typeof item.Amount !== "number" || !Number.isFinite(item.Amount)))
  )) {
    throw new SafetyError("RELATIONSHIP_INCONSISTENCY", "Opportunity result contains invalid owner or status fields");
  }
  return all;
}

async function queryProducts(client, opportunityIds, fields) {
  const all = [];
  for (const batch of batchIds(opportunityIds)) {
    const records = await client.query(
      `SELECT ${fields.join(", ")}, PricebookEntry.Product2Id, PricebookEntry.Product2.Name FROM OpportunityLineItem WHERE OpportunityId IN (${idListSoql(batch)}) ORDER BY OpportunityId, Id LIMIT ${CAPS.lineItems + 1}`,
    );
    all.push(...records.map((record) => {
      if (typeof record.PricebookEntry?.Product2Id !== "string"
        || typeof record.PricebookEntry?.Product2?.Name !== "string") {
        throw new SafetyError("INVALID_FIELD_TYPE", "Product relationship fields must be strings");
      }
      return {
        ...allowlist(record, fields),
        Product2Id: sanitizeText(record.PricebookEntry.Product2Id),
        ProductName: sanitizeText(record.PricebookEntry.Product2.Name),
      };
    }));
    enforceCap(all, CAPS.lineItems, "LINE_ITEM_CAP_EXCEEDED");
  }
  if (new Set(all.map((item) => item.Id)).size !== all.length) {
    throw new SafetyError("RELATIONSHIP_INCONSISTENCY", "Line-item query returned duplicate IDs");
  }
  if (all.some((item) =>
    !LINE_ITEM_ID.test(item.Id)
    || !opportunityIds.includes(item.OpportunityId)
    || !PRICEBOOK_ENTRY_ID.test(item.PricebookEntryId)
    || !PRODUCT_ID.test(item.Product2Id)
  )) {
    throw new SafetyError("RELATIONSHIP_INCONSISTENCY", "Line item result escaped the returned Opportunity-ID set");
  }
  return all;
}

async function queryTeam(client, seedIds, fields, warnings) {
  const users = new Map();
  let frontier = [...new Set(seedIds.filter(Boolean))];
  if (frontier.some((id) => !USER_ID.test(id))) throw new SafetyError("INVALID_RELATIONSHIP_ID", "Owner or manager ID is invalid");
  for (let depth = 0; frontier.length && depth < CAPS.managerDepth; depth += 1) {
    const next = [];
    for (const batch of batchIds(frontier)) {
      const records = await client.query(
        `SELECT ${fields.join(", ")} FROM User WHERE Id IN (${idListSoql(batch)}) ORDER BY Id LIMIT ${CAPS.users + 1}`,
      );
      const returnedIds = records.map((record) => record.Id);
      if (records.length !== batch.length || new Set(returnedIds).size !== returnedIds.length
        || batch.some((id) => !returnedIds.includes(id))) {
        throw new SafetyError("USER_FRONTIER_INCOMPLETE", "User hierarchy query did not return every requested frontier ID exactly once");
      }
      const returnedIdSet = new Set(returnedIds);
      for (const raw of records) {
        const user = allowlist(raw, fields);
        if (!batch.includes(user.Id) || !USER_ID.test(user.Id)) {
          throw new SafetyError("RELATIONSHIP_INCONSISTENCY", "User result does not match the requested ID batch");
        }
        if (users.has(user.Id)) {
          continue;
        }
        if (typeof user.Name !== "string" || user.Name.length === 0
          || (user.Title !== null && typeof user.Title !== "string")) {
          throw new SafetyError("INVALID_FIELD_TYPE", "User Name and Title have invalid types");
        }
        users.set(user.Id, user);
        enforceCap([...users.values()], CAPS.users, "USER_CAP_EXCEEDED");
        if (user.ManagerId) {
          if (!USER_ID.test(user.ManagerId)) throw new SafetyError("INVALID_RELATIONSHIP_ID", "ManagerId is invalid");
          if (!users.has(user.ManagerId) && !returnedIdSet.has(user.ManagerId)) next.push(user.ManagerId);
        }
      }
    }
    frontier = [...new Set(next)];
    if (depth === CAPS.managerDepth - 1 && frontier.length) {
      warnings.push("MANAGER_DEPTH_LIMIT_REACHED", "MANAGER_HIERARCHY_INCOMPLETE");
    }
  }
  const states = new Map();
  const visit = (id) => {
    if (states.get(id) === "visiting") return true;
    if (states.get(id) === "visited") return false;
    states.set(id, "visiting");
    const managerId = users.get(id)?.ManagerId;
    if (managerId && users.has(managerId) && visit(managerId)) return true;
    states.set(id, "visited");
    return false;
  };
  if ([...users.keys()].some(visit)) {
    warnings.push("MANAGER_CYCLE_DETECTED", "MANAGER_HIERARCHY_INCOMPLETE");
  }
  return [...users.values()];
}

function familyPlanDigest(request, currentOrgDigest, selectedAccountId, accountIds) {
  return digest({
    schema_version: "salesforce-account-profile-family-read-plan/v2",
    org_digest: currentOrgDigest,
    selected_account_id: selectedAccountId,
    account_ids: [...accountIds],
    requested_sections: PROFILE_SECTIONS.filter((section) => request.sections.includes(section)),
    scope: request.scope,
    opportunity_scope: request.opportunity_scope,
    filters: {
      close_date_from: null,
      close_date_to: null,
      stages: [],
    },
    field_map_version: FIELD_MAP_VERSION,
    output_type: "profile_result",
  });
}

export async function profile(input, dependencies = {}) {
  const request = validateProfileRequest(input);
  const client = await createClient(request.target_org, dependencies);
  const identity = await client.orgDisplay();
  const currentOrgDigest = validateConfirmedOrg(
    request.target_org,
    identity,
    request.confirmed_org_digest,
    runtimeDigestFor(client),
  );
  validateAccountReceipt(request.account_receipt, currentOrgDigest);
  const warnings = [];

  const needsFamily = request.sections.includes("family") || request.scope === "corporate_family";
  const accountDescribe = await client.describe("Account");
  const requestedSelectedOptional = [
    ...(request.sections.includes("overview") ? ACCOUNT_OPTIONAL : []),
    ...(needsFamily && !request.sections.includes("overview") ? ["Ultimate_Parent_name__c"] : []),
  ];
  const selectedFields = requireFields(accountDescribe, ACCOUNT_REQUIRED, requestedSelectedOptional, "Account", warnings);
  requireFilterable(accountDescribe, ["Id"], "Account");
  const selectedRows = await client.query(
    `SELECT ${selectedFields.join(", ")} FROM Account WHERE Id = '${request.account_receipt.account.Id}' LIMIT 1`,
  );
  if (selectedRows.length !== 1) throw new SafetyError("ACCOUNT_REVALIDATION_FAILED", "Selected Account no longer resolves exactly once");
  const selected = allowlist(selectedRows[0], selectedFields);
  validateAccountRow(selected, { expectedId: request.account_receipt.account.Id });
  if (selected.Name !== request.account_receipt.account.Name) {
    throw new SafetyError("ACCOUNT_REVALIDATION_FAILED", "Selected Account identity changed after confirmation");
  }

  let accounts = [selected];
  if (needsFamily) {
    const hasUltimate = selectedFields.includes("Ultimate_Parent_name__c");
    const familyFields = [
      ...ACCOUNT_REQUIRED,
      ...(hasUltimate && selected.Ultimate_Parent_name__c ? ["Ultimate_Parent_name__c"] : []),
    ];
    requireFilterable(
      accountDescribe,
      hasUltimate && selected.Ultimate_Parent_name__c
        ? ["Ultimate_Parent_name__c"]
        : ["ParentId"],
      "Account",
    );
    accounts = await discoverFamily(
      client,
      selected,
      familyFields,
      hasUltimate,
      warnings,
    );
  }
  const accountIds = accounts.map((account) => account.Id).sort();
  const familyDigest = familyPlanDigest(request, currentOrgDigest, selected.Id, accountIds);
  const selectedOutput = request.sections.includes("overview")
    ? selected
    : { Id: selected.Id, Name: selected.Name, ParentId: selected.ParentId, OwnerId: selected.OwnerId };
  const familyAccountsOutput = accounts.map((item) => ({
    Id: item.Id,
    Name: item.Name,
    ParentId: item.ParentId,
    OwnerId: item.OwnerId,
  }));

  const needsFamilyConfirmation = request.scope === "corporate_family"
    && ["opportunities", "products", "team"].some((section) => request.sections.includes(section))
    && request.confirmed_family_digest !== familyDigest;
  if (needsFamilyConfirmation) {
    return {
      schema_version: CONTRACTS.profileResult,
      classification: CLASSIFICATION,
      status: "family_confirmation_required",
      selected_account: selectedOutput,
      scope: request.scope,
      opportunity_scope: request.opportunity_scope,
      accounts: request.sections.includes("family") ? familyAccountsOutput : [],
      family_confirmation: { account_ids: accountIds, family_digest: familyDigest },
      opportunities: [],
      products: [],
      team: [],
      warnings,
      query_count: client.queryCount,
    };
  }
  if (request.confirmed_family_digest && request.confirmed_family_digest !== familyDigest) {
    throw new SafetyError("FAMILY_CONFIRMATION_MISMATCH", "Confirmed corporate-family Account-ID set changed");
  }

  let opportunities = [];
  if (request.sections.includes("opportunities") || request.sections.includes("products")) {
    const describe = await client.describe("Opportunity");
    const fields = request.sections.includes("opportunities")
      ? requireFields(describe, OPPORTUNITY_REQUIRED, OPPORTUNITY_OPTIONAL, "Opportunity", warnings)
      : requireFields(describe, OPPORTUNITY_PRODUCT_LINK_REQUIRED, [], "Opportunity", warnings);
    requireFilterable(describe, request.opportunity_scope === "all" ? ["AccountId"] : ["AccountId", "IsClosed"], "Opportunity");
    opportunities = await queryOpportunities(client, request.scope === "corporate_family" ? accountIds : [selected.Id], fields, request.opportunity_scope);
  }

  let products = [];
  if (request.sections.includes("products")) {
    const lineItemDescribe = await client.describe("OpportunityLineItem");
    const lineItemFields = requireFields(lineItemDescribe, LINE_ITEM_REQUIRED, LINE_ITEM_OPTIONAL, "OpportunityLineItem", warnings);
    requireFilterable(lineItemDescribe, ["OpportunityId"], "OpportunityLineItem");
    const pricebookEntryDescribe = await client.describe("PricebookEntry");
    requireFields(pricebookEntryDescribe, PRICEBOOK_ENTRY_REQUIRED, [], "PricebookEntry", warnings);
    const productDescribe = await client.describe("Product2");
    requireFields(productDescribe, FIELD_POLICY.Product2.required, FIELD_POLICY.Product2.optional, "Product2", warnings);
    products = await queryProducts(client, opportunities.map((item) => item.Id), lineItemFields);
    warnings.push(WARNING_ANNUALIZATION);
  }

  let team = [];
  if (request.sections.includes("team")) {
    const userDescribe = await client.describe("User");
    const fields = requireFields(userDescribe, USER_REQUIRED, [], "User", warnings);
    requireFilterable(userDescribe, ["Id"], "User");
    const teamSeedIds = request.scope === "corporate_family"
      ? accounts.map((account) => account.OwnerId)
      : [selected.OwnerId];
    team = await queryTeam(client, teamSeedIds, fields, warnings);
  }

  const currencies = [...new Set([
    ...(request.sections.includes("opportunities") ? opportunities.map((item) => item.CurrencyIsoCode) : []),
    ...products.map((item) => item.CurrencyIsoCode),
  ].filter(Boolean))].sort();
  if (currencies.length > 1) warnings.push("MULTICURRENCY_NO_AGGREGATION");

  const result = {
    schema_version: CONTRACTS.profileResult,
    classification: CLASSIFICATION,
    status: "complete",
    selected_account: selectedOutput,
    scope: request.scope,
    opportunity_scope: request.opportunity_scope,
    accounts: request.sections.includes("family") ? familyAccountsOutput : [],
    family_confirmation: needsFamily ? { account_ids: accountIds, family_digest: familyDigest } : null,
    opportunities: request.sections.includes("opportunities") ? opportunities : [],
    products,
    team,
    currencies,
    warnings: [...new Set(warnings)],
    query_count: client.queryCount,
  };
  validateCompleteProfile(result);
  return result;
}

export async function render(input) {
  validateRenderRequest(input);
  return buildRenderResult(input.profile);
}

export async function execute(command, input, dependencies = {}) {
  if (command === "preflight") return await preflight(input, dependencies);
  if (command === "resolve") return await resolve(input, dependencies);
  if (command === "profile") return await profile(input, dependencies);
  if (command === "render") return await render(input);
  throw new SafetyError("UNKNOWN_COMMAND", "Command must be preflight, resolve, profile, or render");
}

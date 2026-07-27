import {
  ACCOUNT_ID,
  CAPS,
  CLASSIFICATION,
  OPPORTUNITY_ID,
  USER_ID,
} from "./constants.mjs";
import { validateCompleteProfile } from "./contracts.mjs";
import {
  readPlanDigest,
  validateApprovalReceipt,
  validateReadPlan,
} from "./read-plan.mjs";
import { batchIds } from "./sf-client.mjs";
import {
  digest,
  escapeSoqlLiteral,
  SafetyError,
  sanitizeText,
} from "./security.mjs";

export const PROFILE_HYDRATION_SCHEMA = "salesforce-account-profile-relationship-context/v1";

const ACCOUNT_FIELDS = Object.freeze(["Id", "Name", "ParentId", "OwnerId"]);
const ACCOUNT_NAME_FIELDS = Object.freeze(["Id", "Name"]);
const OPPORTUNITY_FIELDS = Object.freeze(["Id", "Name", "AccountId", "OwnerId"]);
const PRODUCT_OPPORTUNITY_FIELDS = Object.freeze(["Id", "Name", "AccountId"]);
const USER_FIELDS = Object.freeze(["Id", "Name", "Title"]);
const TEAM_USER_FIELDS = Object.freeze(["Id", "Name", "Title", "ManagerId"]);
const ACCOUNT_ROLE_FIELDS = Object.freeze({
  csm: "CSM__c",
  technical_advisor: "Support_Technical_Advisor__c",
  presales: "PreSales__c",
});
const FIELD_EXPECTATIONS = Object.freeze({
  Account: Object.freeze({
    Id: Object.freeze({ types: Object.freeze(["id"]), filterable: true }),
    Name: Object.freeze({ types: Object.freeze(["string"]) }),
    ParentId: Object.freeze({ types: Object.freeze(["reference"]), referenceTo: "Account" }),
    OwnerId: Object.freeze({ types: Object.freeze(["reference"]), referenceTo: "User" }),
    CSM__c: Object.freeze({ types: Object.freeze(["reference"]), referenceTo: "User" }),
    Support_Technical_Advisor__c: Object.freeze({
      types: Object.freeze(["reference"]),
      referenceTo: "User",
    }),
    PreSales__c: Object.freeze({ types: Object.freeze(["reference"]), referenceTo: "User" }),
  }),
  Opportunity: Object.freeze({
    Id: Object.freeze({ types: Object.freeze(["id"]) }),
    Name: Object.freeze({ types: Object.freeze(["string"]) }),
    AccountId: Object.freeze({ types: Object.freeze(["reference"]), referenceTo: "Account" }),
    OwnerId: Object.freeze({ types: Object.freeze(["reference"]), referenceTo: "User" }),
    IsClosed: Object.freeze({ types: Object.freeze(["boolean"]) }),
    CloseDate: Object.freeze({ types: Object.freeze(["date"]) }),
    StageName: Object.freeze({ types: Object.freeze(["string", "picklist"]) }),
  }),
  User: Object.freeze({
    Id: Object.freeze({ types: Object.freeze(["id"]) }),
    Name: Object.freeze({ types: Object.freeze(["string"]) }),
    Title: Object.freeze({ types: Object.freeze(["string"]) }),
    ManagerId: Object.freeze({ types: Object.freeze(["reference"]), referenceTo: "User" }),
  }),
});

function relationshipError(message) {
  throw new SafetyError("RELATIONSHIP_INCONSISTENCY", message);
}

function enforceIdCap(ids, cap, code, nextAction) {
  if (ids.length > cap) {
    throw new SafetyError(
      code,
      `Relationship hydration exceeded deterministic cap ${cap}`,
      { next_action: [...nextAction] },
    );
  }
}

function validateClient(client) {
  if (!client
    || typeof client !== "object"
    || typeof client.orgDisplay !== "function"
    || typeof client.describe !== "function"
    || typeof client.query !== "function"
    || typeof client.targetOrg !== "string"
    || !/^[a-f0-9]{64}$/u.test(client.attestationDigest)
    || !Number.isInteger(client.queryCount)
    || client.queryCount < 0) {
    throw new SafetyError(
      "INVALID_PLAN_CONTEXT",
      "Relationship hydration requires the same verified SfClient continuation",
    );
  }
}

function requireDescribeFields(
  describe,
  objectName,
  fields,
  filterableFields = ["Id"],
) {
  if (!(describe instanceof Map)) {
    throw new SafetyError("SCHEMA_FAILURE", `${objectName} describe result must be a field map`);
  }
  for (const field of fields) {
    const metadata = describe.get(field);
    const expectation = FIELD_EXPECTATIONS[objectName][field];
    if (!metadata
      || metadata.name !== field
      || !expectation.types.includes(metadata.type)
      || (expectation.referenceTo
        && (!Array.isArray(metadata.referenceTo)
          || !metadata.referenceTo.includes(expectation.referenceTo)))) {
      throw new SafetyError(
        "SCHEMA_FAILURE",
        `${objectName}.${field} metadata is missing or incompatible`,
      );
    }
  }
  const invalidPredicates = filterableFields.filter((field) =>
    describe.get(field)?.filterable !== true);
  if (invalidPredicates.length) {
    throw new SafetyError(
      "SCHEMA_FAILURE",
      `${objectName} hydration predicate fields are not filterable`,
      { fields: invalidPredicates },
    );
  }
}

function requireActiveStageValues(describe, stages) {
  if (!stages.length) return;
  const metadata = describe.get("StageName");
  const values = metadata?.activePicklistValues;
  if (metadata?.type !== "picklist"
    || !Array.isArray(values)
    || values.length > 1_000
    || values.some((value) =>
      typeof value !== "string"
      || value.length < 1
      || value.length > 80
      || sanitizeText(value) !== value)
    || new Set(values).size !== values.length
    || values.some((value, index) =>
      index > 0 && values[index - 1].localeCompare(value, "en-US") > 0)) {
    throw new SafetyError(
      "SCHEMA_FAILURE",
      "Opportunity.StageName active values are missing or malformed",
    );
  }
  const activeValues = new Set(values);
  if (stages.some((stage) => !activeValues.has(stage))) {
    throw new SafetyError(
      "INVALID_STAGE_FILTER",
      "Every requested StageName must remain active at hydration time",
    );
  }
}

function idListSoql(ids) {
  return ids.map((id) => `'${id}'`).join(",");
}

function requiredId(record, field, pattern, objectName) {
  const value = record?.[field];
  if (typeof value !== "string" || !pattern.test(value)) {
    throw new SafetyError(
      "INVALID_FIELD_TYPE",
      `${objectName}.${field} must be a valid Salesforce ID`,
    );
  }
  return value;
}

function nullableId(record, field, pattern, objectName) {
  const value = record?.[field];
  if (value === null) return null;
  if (typeof value !== "string" || !pattern.test(value)) {
    throw new SafetyError(
      "INVALID_FIELD_TYPE",
      `${objectName}.${field} must be null or a valid Salesforce ID`,
    );
  }
  return value;
}

function requiredText(record, field, objectName) {
  if (typeof record?.[field] !== "string") {
    throw new SafetyError(
      "INVALID_FIELD_TYPE",
      `${objectName}.${field} must be text`,
    );
  }
  const value = sanitizeText(record[field]);
  if (!value.length) {
    throw new SafetyError(
      "INVALID_FIELD_TYPE",
      `${objectName}.${field} must not be empty after sanitization`,
    );
  }
  return value;
}

function nullableText(record, field, objectName) {
  if (record?.[field] === null) return null;
  if (typeof record?.[field] !== "string") {
    throw new SafetyError(
      "INVALID_FIELD_TYPE",
      `${objectName}.${field} must be null or text`,
    );
  }
  return sanitizeText(record[field]);
}

function requiredBoolean(record, field, objectName) {
  if (typeof record?.[field] !== "boolean") {
    throw new SafetyError(
      "INVALID_FIELD_TYPE",
      `${objectName}.${field} must be boolean`,
    );
  }
  return record[field];
}

function requiredDate(record, field, objectName) {
  const value = requiredText(record, field, objectName);
  const parsed = new Date(`${value}T00:00:00.000Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/u.test(value)
    || !Number.isFinite(parsed.getTime())
    || parsed.toISOString().slice(0, 10) !== value) {
    throw new SafetyError(
      "INVALID_FIELD_TYPE",
      `${objectName}.${field} must be a canonical calendar date`,
    );
  }
  return value;
}

function parseAccount(record, roleFields = []) {
  const row = {
    Id: requiredId(record, "Id", ACCOUNT_ID, "Account"),
    Name: requiredText(record, "Name", "Account"),
    ParentId: nullableId(record, "ParentId", ACCOUNT_ID, "Account"),
    OwnerId: requiredId(record, "OwnerId", USER_ID, "Account"),
  };
  for (const field of roleFields) {
    row[field] = nullableId(record, field, USER_ID, "Account");
  }
  return row;
}

function parseAccountName(record) {
  return {
    Id: requiredId(record, "Id", ACCOUNT_ID, "Account"),
    Name: requiredText(record, "Name", "Account"),
  };
}

function parseOpportunity(record, {
  includeOwner,
  predicateFields,
}) {
  const row = {
    Id: requiredId(record, "Id", OPPORTUNITY_ID, "Opportunity"),
    Name: requiredText(record, "Name", "Opportunity"),
    AccountId: requiredId(record, "AccountId", ACCOUNT_ID, "Opportunity"),
  };
  if (includeOwner) {
    row.OwnerId = requiredId(record, "OwnerId", USER_ID, "Opportunity");
  }
  if (predicateFields.includes("IsClosed")) {
    row.IsClosed = requiredBoolean(record, "IsClosed", "Opportunity");
  }
  if (predicateFields.includes("CloseDate")) {
    row.CloseDate = requiredDate(record, "CloseDate", "Opportunity");
  }
  if (predicateFields.includes("StageName")) {
    row.StageName = requiredText(record, "StageName", "Opportunity");
  }
  return row;
}

function parseUser(record, includeManager) {
  const row = {
    Id: requiredId(record, "Id", USER_ID, "User"),
    Name: requiredText(record, "Name", "User"),
    Title: nullableText(record, "Title", "User"),
  };
  if (includeManager) {
    row.ManagerId = nullableId(record, "ManagerId", USER_ID, "User");
  }
  return row;
}

async function queryExactRows({
  objectName,
  fields,
  ids,
  parse,
  runQuery,
  predicates = [],
}) {
  const rows = new Map();
  for (const batch of batchIds(ids)) {
    const requested = new Set(batch);
    const records = await runQuery(
      `SELECT ${fields.join(", ")} FROM ${objectName} WHERE Id IN (${idListSoql(batch)})${predicates.map((predicate) => ` AND ${predicate}`).join("")} ORDER BY Id LIMIT ${batch.length + 1}`,
    );
    if (!Array.isArray(records)) {
      throw new SafetyError(
        "INCOMPLETE_QUERY_RESULT",
        `${objectName} hydration query omitted records`,
      );
    }
    const returned = new Set();
    for (const record of records) {
      const row = parse(record);
      if (!requested.has(row.Id)) {
        relationshipError(`${objectName} hydration returned an unrequested row`);
      }
      if (returned.has(row.Id) || rows.has(row.Id)) {
        relationshipError(`${objectName} hydration returned a duplicate row`);
      }
      returned.add(row.Id);
      rows.set(row.Id, row);
    }
    if (returned.size !== batch.length
      || batch.some((id) => !returned.has(id))) {
      relationshipError(`${objectName} hydration did not return every exact requested ID`);
    }
  }
  return rows;
}

function sameCoreAccount(left, right) {
  return left.Name === right.Name
    && left.ParentId === right.ParentId
    && left.OwnerId === right.OwnerId;
}

function sourceAccount(account) {
  const normalized = {
    Id: account.Id,
    Name: sanitizeText(account.Name),
    ParentId: account.ParentId,
    OwnerId: account.OwnerId,
  };
  for (const field of Object.values(ACCOUNT_ROLE_FIELDS)) {
    if (field in account) normalized[field] = account[field];
  }
  return normalized;
}

function buildAccountSources(profile) {
  const sources = new Map();
  const add = (account) => {
    const normalized = sourceAccount(account);
    const existing = sources.get(normalized.Id);
    if (existing && !sameCoreAccount(existing, normalized)) {
      relationshipError("Profile contains inconsistent duplicate Account references");
    }
    if (!existing) {
      sources.set(normalized.Id, normalized);
      return;
    }
    for (const field of Object.values(ACCOUNT_ROLE_FIELDS)) {
      if (!(field in normalized)) continue;
      if (field in existing && existing[field] !== normalized[field]) {
        relationshipError("Profile contains inconsistent Account role references");
      }
      existing[field] = normalized[field];
    }
  };
  add(profile.selected_account);
  const seenFamilyIds = new Set();
  for (const account of profile.accounts) {
    if (seenFamilyIds.has(account.Id)) {
      relationshipError("Profile contains a duplicate Account row");
    }
    seenFamilyIds.add(account.Id);
    add(account);
  }
  return sources;
}

function accountQueryGroups(accountSources) {
  const groups = new Map();
  for (const source of accountSources.values()) {
    const roleFields = Object.values(ACCOUNT_ROLE_FIELDS)
      .filter((field) => field in source)
      .sort();
    const key = roleFields.join(",");
    const group = groups.get(key) ?? { roleFields, ids: [] };
    group.ids.push(source.Id);
    groups.set(key, group);
  }
  return [...groups.values()]
    .map((group) => ({ ...group, ids: group.ids.sort() }))
    .sort((left, right) =>
      left.roleFields.join(",").localeCompare(right.roleFields.join(",")));
}

function uniqueRowsById(records, label) {
  const rows = new Map();
  for (const record of records) {
    if (rows.has(record.Id)) relationshipError(`Profile contains a duplicate ${label} row`);
    rows.set(record.Id, record);
  }
  return rows;
}

function profilePlanMismatch(message) {
  throw new SafetyError("PROFILE_PLAN_MISMATCH", message);
}

function sameOrderedValues(left, right) {
  return left.length === right.length
    && left.every((value, index) => value === right[index]);
}

function executionTime(value) {
  if (value === undefined) {
    throw new SafetyError(
      "INVALID_PLAN_CONTEXT",
      "Relationship hydration requires an explicit execution time",
    );
  }
  const now = value instanceof Date
    ? new Date(value.getTime())
    : new Date(value);
  if (!Number.isFinite(now.getTime())) {
    throw new SafetyError(
      "INVALID_PLAN_CONTEXT",
      "Relationship hydration execution time is invalid",
    );
  }
  return now;
}

function requireCanonicalId(value, label) {
  if (value !== null && value.length !== 18) {
    throw new SafetyError(
      "INVALID_PLAN_CONTEXT",
      `${label} must use the canonical 18-character Salesforce ID form`,
    );
  }
}

function requireCanonicalRelationshipIds(profile, readPlan) {
  requireCanonicalId(readPlan.selected_account?.Id ?? null, "read_plan.selected_account.Id");
  for (const id of readPlan.family_account_ids) {
    requireCanonicalId(id, "read_plan.family_account_ids[]");
  }
  for (const [label, accounts] of [
    ["selected_account", [profile.selected_account]],
    ["accounts[]", profile.accounts],
  ]) {
    for (const account of accounts) {
      requireCanonicalId(account.Id, `${label}.Id`);
      requireCanonicalId(account.ParentId, `${label}.ParentId`);
      requireCanonicalId(account.OwnerId, `${label}.OwnerId`);
      for (const field of Object.values(ACCOUNT_ROLE_FIELDS)) {
        if (field in account) requireCanonicalId(account[field], `${label}.${field}`);
      }
    }
  }
  for (const opportunity of profile.opportunities) {
    requireCanonicalId(opportunity.Id, "opportunities[].Id");
    requireCanonicalId(opportunity.AccountId, "opportunities[].AccountId");
    requireCanonicalId(opportunity.OwnerId, "opportunities[].OwnerId");
  }
  for (const item of profile.products) {
    requireCanonicalId(item.OpportunityId, "products[].OpportunityId");
  }
  for (const user of profile.team) {
    requireCanonicalId(user.Id, "team[].Id");
    requireCanonicalId(user.ManagerId, "team[].ManagerId");
  }
}

function validatePlanProfileBinding(profile, readPlan) {
  if (readPlan.selected_account === null
    || readPlan.selected_account.Id !== profile.selected_account.Id
    || readPlan.selected_account.Name !== sanitizeText(profile.selected_account.Name)
    || readPlan.scope !== profile.scope
    || readPlan.opportunity_scope !== profile.opportunity_scope) {
    profilePlanMismatch(
      "Completed profile does not match the selected Account or scope in the read plan",
    );
  }
  const sectionRecords = {
    family: profile.accounts,
    opportunities: profile.opportunities,
    products: profile.products,
    team: profile.team,
  };
  for (const [section, records] of Object.entries(sectionRecords)) {
    if (!readPlan.requested_sections.includes(section) && records.length) {
      profilePlanMismatch(`Completed profile returned unrequested ${section} records`);
    }
  }
  const selectedOptionalFields = Object.keys(profile.selected_account)
    .filter((field) => !ACCOUNT_FIELDS.includes(field));
  if (selectedOptionalFields.length
    && !readPlan.requested_sections.includes("overview")) {
    profilePlanMismatch("Completed profile returned unrequested Account overview fields");
  }

  const needsFamilySet = readPlan.scope === "corporate_family"
    || readPlan.requested_sections.includes("family");
  const profileFamilyIds = profile.family_confirmation?.account_ids ?? null;
  if (needsFamilySet) {
    if (profileFamilyIds === null
      || !sameOrderedValues(readPlan.family_account_ids, profileFamilyIds)) {
      profilePlanMismatch(
        "Completed profile family IDs do not match the exact read-plan Account set",
      );
    }
    if (readPlan.requested_sections.includes("family")) {
      const returnedFamilyIds = profile.accounts
        .map((account) => account.Id)
        .sort();
      if (!sameOrderedValues(readPlan.family_account_ids, returnedFamilyIds)) {
        profilePlanMismatch(
          "Completed family section does not contain the exact read-plan Account set",
        );
      }
    }
  } else if (profile.family_confirmation !== null
    || readPlan.family_account_ids.length) {
    profilePlanMismatch("Unexpected family Account set for the current read plan");
  }
}

function requiresFamilyApproval(readPlan) {
  return readPlan.scope === "corporate_family"
    && ["opportunities", "products", "team"].some((section) =>
      readPlan.requested_sections.includes(section));
}

function validateFamilyApproval(
  familyApprovalReceipt,
  readPlan,
  now,
) {
  const receiptSupplied = familyApprovalReceipt !== null
    && familyApprovalReceipt !== undefined;
  if (requiresFamilyApproval(readPlan) && !receiptSupplied) {
    throw new SafetyError(
      "INVALID_PLAN_CONTEXT",
      "Corporate-family transaction hydration requires a family approval receipt",
    );
  }
  if (receiptSupplied) {
    if (readPlan.scope !== "corporate_family") {
      throw new SafetyError(
        "INVALID_PLAN_CONTEXT",
        "Family approval receipt is valid only for corporate-family scope",
      );
    }
    validateApprovalReceipt(
      familyApprovalReceipt,
      readPlan,
      "family_scope",
      now,
    );
    return;
  }
}

function validateAccountScope(
  profile,
  readPlan,
  accountSources,
  opportunitySources,
) {
  const planAccountIds = readPlan.family_account_ids.length
    ? new Set(readPlan.family_account_ids)
    : new Set([profile.selected_account.Id]);
  const accountContextIds = readPlan.scope === "corporate_family"
    || readPlan.requested_sections.includes("family")
    ? planAccountIds
    : new Set([profile.selected_account.Id]);
  if ([...accountSources.keys()].some((id) => !accountContextIds.has(id))) {
    relationshipError(
      "Profile Account context escaped its approved Account-ID set",
    );
  }
  const opportunityAccountIds = readPlan.scope === "corporate_family"
    ? planAccountIds
    : new Set([profile.selected_account.Id]);
  if ([...opportunitySources.values()].some((opportunity) =>
    !opportunityAccountIds.has(opportunity.AccountId))) {
    relationshipError(
      "Profile Opportunity escaped its approved Account scope",
    );
  }
  return opportunityAccountIds;
}

async function validateRuntimeBinding(client, readPlan) {
  const identity = await client.orgDisplay();
  const expected = readPlan.org_identity;
  if (!identity
    || typeof identity !== "object"
    || client.targetOrg !== expected.target_org
    || client.attestationDigest !== readPlan.runtime_attestation_digest
    || identity.org_id !== expected.org_id
    || identity.username !== expected.username
    || identity.instance_url !== expected.instance_url
    || identity.connected_status !== expected.connected_status) {
    throw new SafetyError(
      "READ_PLAN_MISMATCH",
      "Relationship hydration client does not match the approved org and runtime",
    );
  }
}

function opportunityPredicateFields(readPlan) {
  return [
    ...(readPlan.opportunity_scope === "all" ? [] : ["IsClosed"]),
    ...(readPlan.filters.close_date_from !== null
      || readPlan.filters.close_date_to !== null ? ["CloseDate"] : []),
    ...(readPlan.filters.stages.length ? ["StageName"] : []),
  ];
}

function opportunityPredicates(readPlan, accountIds) {
  const accountClauses = batchIds([...accountIds].sort())
    .map((batch) => `AccountId IN (${idListSoql(batch)})`);
  const predicates = [
    accountClauses.length === 1
      ? accountClauses[0]
      : `(${accountClauses.join(" OR ")})`,
  ];
  if (readPlan.opportunity_scope === "open") predicates.push("IsClosed = false");
  if (readPlan.opportunity_scope === "closed") predicates.push("IsClosed = true");
  if (readPlan.filters.close_date_from) {
    predicates.push(`CloseDate >= ${readPlan.filters.close_date_from}`);
  }
  if (readPlan.filters.close_date_to) {
    predicates.push(`CloseDate <= ${readPlan.filters.close_date_to}`);
  }
  if (readPlan.filters.stages.length) {
    predicates.push(
      `StageName IN (${readPlan.filters.stages.map((stage) =>
        `'${escapeSoqlLiteral(stage)}'`).join(",")})`,
    );
  }
  return predicates;
}

function bindOpportunityPredicate(row, readPlan, accountIds) {
  if (!accountIds.has(row.AccountId)
    || (readPlan.opportunity_scope === "open" && row.IsClosed !== false)
    || (readPlan.opportunity_scope === "closed" && row.IsClosed !== true)
    || (readPlan.filters.close_date_from
      && row.CloseDate < readPlan.filters.close_date_from)
    || (readPlan.filters.close_date_to
      && row.CloseDate > readPlan.filters.close_date_to)
    || (readPlan.filters.stages.length
      && !readPlan.filters.stages.includes(row.StageName))) {
    throw new SafetyError(
      "PREDICATE_BINDING_FAILED",
      "Hydrated Opportunity no longer matches the approved Account and filter predicates",
    );
  }
}

function bindAccountSource(row, source) {
  if (!source) return;
  if (row.Name !== source.Name
    || row.ParentId !== source.ParentId
    || row.OwnerId !== source.OwnerId) {
    relationshipError("Hydrated Account no longer matches the completed profile");
  }
  for (const field of Object.values(ACCOUNT_ROLE_FIELDS)) {
    if (field in source && row[field] !== source[field]) {
      relationshipError(
        "Hydrated Account role references no longer match the completed profile",
      );
    }
  }
}

function bindOpportunitySource(row, source) {
  if (!source) return;
  if (row.Name !== sanitizeText(source.Name)
    || row.AccountId !== source.AccountId
    || row.OwnerId !== source.OwnerId) {
    relationshipError("Hydrated Opportunity no longer matches the completed profile");
  }
}

function bindUserSource(row, source) {
  if (!source) return;
  if (row.Name !== sanitizeText(source.Name)
    || row.Title !== (source.Title === null ? null : sanitizeText(source.Title))
    || row.ManagerId !== source.ManagerId) {
    relationshipError("Hydrated User no longer matches the completed profile");
  }
}

function userSummary(user) {
  return { Id: user.Id, Name: user.Name, Title: user.Title };
}

function accountRoleContext(source, account, field, users) {
  if (!source || !(field in source)) {
    return { available: false, user: null };
  }
  if (account[field] === null) {
    return { available: true, user: null };
  }
  const user = users.get(account[field]);
  if (!user) relationshipError("Account role User was not hydrated");
  return { available: true, user: userSummary(user) };
}

function mergeRows(target, rows, label) {
  for (const [id, row] of rows) {
    if (target.has(id)) {
      relationshipError(`${label} hydration produced a duplicate row across query groups`);
    }
    target.set(id, row);
  }
}

function sourceUserIds(accountSources, opportunitySources, teamSources) {
  const ids = new Set([
    ...[...accountSources.values()].map((account) => account.OwnerId),
    ...[...opportunitySources.values()].map((opportunity) => opportunity.OwnerId),
    ...teamSources.keys(),
  ]);
  for (const source of accountSources.values()) {
    for (const field of Object.values(ACCOUNT_ROLE_FIELDS)) {
      if (field in source && source[field] !== null) ids.add(source[field]);
    }
  }
  return ids;
}

function enforceQueryBudget({
  client,
  profile,
  opportunityGroups,
  accountGroups,
  maximumNameOnlyIds,
  summaryUserIds,
  teamUserIds,
}) {
  if (client.queryCount !== profile.query_count) {
    throw new SafetyError(
      "INVALID_PLAN_CONTEXT",
      "Hydration must continue on the exact SfClient that produced the profile",
    );
  }
  const hydrationUpperBound = [
    ...opportunityGroups.map((ids) => batchIds(ids).length),
    ...accountGroups.map((group) => batchIds(group.ids).length),
    batchIds(maximumNameOnlyIds).length,
    batchIds(summaryUserIds).length,
    batchIds(teamUserIds).length,
  ].reduce((sum, count) => sum + count, 0);
  if (client.queryCount + hydrationUpperBound > CAPS.queries) {
    throw new SafetyError(
      "QUERY_CAP_EXCEEDED",
      "Relationship hydration cannot complete within the cumulative query cap",
      {
        next_action: [
          "selected_account",
          "remove_line_items",
          "remove_team",
          "reduce_sections",
        ],
      },
    );
  }
  return hydrationUpperBound;
}

/**
 * Internal continuation only. The client must be the verified, stateful
 * SfClient that produced profile; caller-supplied or freshly-created clients
 * are rejected before Salesforce data queries.
 */
export async function hydrateProfileRelationships({
  client,
  profile,
  readPlan,
  familyApprovalReceipt = null,
  now,
}) {
  validateClient(client);
  validateCompleteProfile(profile);
  validateReadPlan(readPlan);
  const currentTime = executionTime(now);
  validatePlanProfileBinding(profile, readPlan);
  requireCanonicalRelationshipIds(profile, readPlan);
  const issuedAt = new Date(readPlan.issued_at);
  const expiresAt = new Date(readPlan.expires_at);
  if (currentTime < issuedAt || currentTime >= expiresAt) {
    throw new SafetyError(
      "READ_PLAN_EXPIRED",
      "Relationship hydration read plan is not active",
    );
  }
  validateFamilyApproval(
    familyApprovalReceipt,
    readPlan,
    currentTime,
  );

  const accountSources = buildAccountSources(profile);
  const opportunitySources = uniqueRowsById(profile.opportunities, "Opportunity");
  const productSources = uniqueRowsById(
    profile.products,
    "Opportunity line item",
  );
  const teamSources = uniqueRowsById(profile.team, "User");
  const opportunityAccountIds = validateAccountScope(
    profile,
    readPlan,
    accountSources,
    opportunitySources,
  );
  const managerHierarchyIncomplete = profile.warnings.includes(
    "MANAGER_HIERARCHY_INCOMPLETE",
  );
  if (!managerHierarchyIncomplete
    && [...teamSources.values()].some((user) =>
      user.ManagerId !== null && !teamSources.has(user.ManagerId))) {
    relationshipError(
      "Complete profile team is missing a referenced manager User",
    );
  }

  enforceIdCap(
    readPlan.family_account_ids,
    CAPS.familyAccounts,
    "FAMILY_ACCOUNT_CAP_EXCEEDED",
    ["selected_account"],
  );
  enforceIdCap(
    [...productSources.keys()],
    CAPS.lineItems,
    "LINE_ITEM_CAP_EXCEEDED",
    [
      "selected_account",
      "open_only",
      "date_narrowing",
      "stage_narrowing",
      "remove_line_items",
    ],
  );
  const fullOpportunityIds = [...opportunitySources.keys()].sort();
  const productOnlyOpportunityIds = [...new Set(
    profile.products
      .map((item) => item.OpportunityId)
      .filter((id) => !opportunitySources.has(id)),
  )].sort();
  const opportunityIds = [...new Set([
    ...fullOpportunityIds,
    ...productOnlyOpportunityIds,
  ])].sort();
  enforceIdCap(
    opportunityIds,
    CAPS.opportunities,
    "OPPORTUNITY_CAP_EXCEEDED",
    ["selected_account", "open_only", "date_narrowing", "stage_narrowing"],
  );
  enforceIdCap(
    [...accountSources.keys()],
    CAPS.familyAccounts,
    "FAMILY_ACCOUNT_CAP_EXCEEDED",
    ["selected_account"],
  );

  const accountGroups = accountQueryGroups(accountSources);
  const directAccountIdSet = new Set(accountSources.keys());
  const knownNameOnlyIds = new Set([
    ...[...accountSources.values()]
      .map((account) => account.ParentId)
      .filter((id) => id !== null && !directAccountIdSet.has(id)),
    ...[...opportunitySources.values()]
      .map((opportunity) => opportunity.AccountId)
      .filter((id) => !directAccountIdSet.has(id)),
  ]);
  enforceIdCap(
    [...new Set([...directAccountIdSet, ...knownNameOnlyIds])],
    CAPS.familyAccounts,
    "FAMILY_ACCOUNT_CAP_EXCEEDED",
    ["selected_account"],
  );
  const possibleNameOnlyIds = new Set(knownNameOnlyIds);
  if (productOnlyOpportunityIds.length) {
    for (const id of opportunityAccountIds) {
      if (!directAccountIdSet.has(id)) possibleNameOnlyIds.add(id);
    }
  }
  const remainingAccountCapacity = CAPS.familyAccounts - directAccountIdSet.size;
  const maximumNameOnlyIds = [...possibleNameOnlyIds]
    .sort()
    .slice(0, remainingAccountCapacity);

  const plannedUserIds = sourceUserIds(
    accountSources,
    opportunitySources,
    teamSources,
  );
  const plannedTeamUserIds = [...teamSources.keys()].sort();
  const plannedSummaryUserIds = [...plannedUserIds]
    .filter((id) => !teamSources.has(id))
    .sort();
  enforceIdCap(
    [...plannedUserIds],
    CAPS.users,
    "USER_CAP_EXCEEDED",
    ["selected_account"],
  );
  enforceQueryBudget({
    client,
    profile,
    opportunityGroups: [
      fullOpportunityIds,
      productOnlyOpportunityIds,
    ],
    accountGroups,
    maximumNameOnlyIds,
    summaryUserIds: plannedSummaryUserIds,
    teamUserIds: plannedTeamUserIds,
  });
  await validateRuntimeBinding(client, readPlan);

  let queryCount = 0;
  const runQuery = async (soql) => {
    const records = await client.query(soql);
    queryCount += 1;
    return records;
  };

  const predicateFields = opportunityPredicateFields(readPlan);
  const fullOpportunityFields = [...new Set([
    ...OPPORTUNITY_FIELDS,
    ...predicateFields,
  ])];
  const productOpportunityFields = [...new Set([
    ...PRODUCT_OPPORTUNITY_FIELDS,
    ...predicateFields,
  ])];
  if (opportunityIds.length) {
    const opportunityDescribe = await client.describe("Opportunity");
    requireDescribeFields(
      opportunityDescribe,
      "Opportunity",
      [...new Set([
        ...(fullOpportunityIds.length ? fullOpportunityFields : []),
        ...(productOnlyOpportunityIds.length
          ? productOpportunityFields
          : []),
      ])],
      ["Id", "AccountId", ...predicateFields],
    );
    requireActiveStageValues(
      opportunityDescribe,
      readPlan.filters.stages,
    );
  }
  const accountDescribe = await client.describe("Account");
  const queriedAccountFields = [...new Set([
    ...ACCOUNT_FIELDS,
    ...accountGroups.flatMap((group) => group.roleFields),
  ])];
  requireDescribeFields(
    accountDescribe,
    "Account",
    queriedAccountFields,
  );
  const userDescribe = await client.describe("User");
  requireDescribeFields(
    userDescribe,
    "User",
    plannedTeamUserIds.length ? TEAM_USER_FIELDS : USER_FIELDS,
  );

  let opportunityRows = new Map();
  const predicates = opportunityPredicates(
    readPlan,
    opportunityAccountIds,
  );
  if (fullOpportunityIds.length) {
    const fullRows = await queryExactRows({
      objectName: "Opportunity",
      fields: fullOpportunityFields,
      ids: fullOpportunityIds,
      parse: (record) => parseOpportunity(record, {
        includeOwner: true,
        predicateFields,
      }),
      runQuery,
      predicates,
    });
    for (const row of fullRows.values()) {
      bindOpportunitySource(row, opportunitySources.get(row.Id));
      bindOpportunityPredicate(row, readPlan, opportunityAccountIds);
    }
    mergeRows(opportunityRows, fullRows, "Opportunity");
  }
  if (productOnlyOpportunityIds.length) {
    const productRows = await queryExactRows({
      objectName: "Opportunity",
      fields: productOpportunityFields,
      ids: productOnlyOpportunityIds,
      parse: (record) => parseOpportunity(record, {
        includeOwner: false,
        predicateFields,
      }),
      runQuery,
      predicates,
    });
    for (const row of productRows.values()) {
      bindOpportunityPredicate(row, readPlan, opportunityAccountIds);
    }
    mergeRows(opportunityRows, productRows, "Opportunity");
  }

  const directAccountIds = [...accountSources.keys()].sort();
  const directAccountRows = new Map();
  for (const group of accountGroups) {
    const groupRows = await queryExactRows({
      objectName: "Account",
      fields: [...ACCOUNT_FIELDS, ...group.roleFields],
      ids: group.ids,
      parse: (record) => parseAccount(record, group.roleFields),
      runQuery,
    });
    mergeRows(directAccountRows, groupRows, "Account");
  }
  for (const row of directAccountRows.values()) {
    bindAccountSource(row, accountSources.get(row.Id));
  }

  const missingParentIds = [...new Set(
    [...directAccountRows.values()]
      .map((row) => row.ParentId)
      .filter((id) => id !== null && !directAccountRows.has(id)),
  )].sort();
  const missingOpportunityAccountIds = [...new Set(
    [...opportunityRows.values()]
      .map((row) => row.AccountId)
      .filter((id) => !directAccountRows.has(id)),
  )].sort();
  const accountNameOnlyIds = [...new Set([
    ...missingParentIds,
    ...missingOpportunityAccountIds,
  ])].sort();
  enforceIdCap(
    [...new Set([...directAccountIds, ...accountNameOnlyIds])],
    CAPS.familyAccounts,
    "FAMILY_ACCOUNT_CAP_EXCEEDED",
    ["selected_account"],
  );
  const parentRows = await queryExactRows({
    objectName: "Account",
    fields: ACCOUNT_NAME_FIELDS,
    ids: accountNameOnlyIds,
    parse: parseAccountName,
    runQuery,
  });
  const accountNames = new Map([
    ...[...directAccountRows.values()].map((row) => [row.Id, { Id: row.Id, Name: row.Name }]),
    ...parentRows,
  ]);

  const directUserIds = new Set([
    ...[...directAccountRows.values()].map((row) => row.OwnerId),
    ...[...opportunityRows.values()]
      .map((row) => row.OwnerId)
      .filter((id) => id !== undefined),
    ...teamSources.keys(),
  ]);
  for (const [accountId, source] of accountSources) {
    if (!directAccountRows.has(accountId)) continue;
    for (const field of Object.values(ACCOUNT_ROLE_FIELDS)) {
      if (field in source && source[field] !== null) directUserIds.add(source[field]);
    }
  }
  const sortedDirectUserIds = [...directUserIds].sort();
  enforceIdCap(
    sortedDirectUserIds,
    CAPS.users,
    "USER_CAP_EXCEEDED",
    ["selected_account"],
  );
  const directUserRows = new Map();
  const summaryUserIds = sortedDirectUserIds
    .filter((id) => !teamSources.has(id));
  const teamUserIds = sortedDirectUserIds
    .filter((id) => teamSources.has(id));
  if (summaryUserIds.length) {
    mergeRows(
      directUserRows,
      await queryExactRows({
        objectName: "User",
        fields: USER_FIELDS,
        ids: summaryUserIds,
        parse: (record) => parseUser(record, false),
        runQuery,
      }),
      "User",
    );
  }
  if (teamUserIds.length) {
    const teamRows = await queryExactRows({
      objectName: "User",
      fields: TEAM_USER_FIELDS,
      ids: teamUserIds,
      parse: (record) => parseUser(record, true),
      runQuery,
    });
    for (const row of teamRows.values()) {
      bindUserSource(row, teamSources.get(row.Id));
    }
    mergeRows(directUserRows, teamRows, "User");
  }

  const accounts = [...directAccountRows.values()]
    .sort((left, right) => left.Id.localeCompare(right.Id))
    .map((row) => {
      const source = accountSources.get(row.Id);
      const owner = directUserRows.get(row.OwnerId);
      if (!owner) relationshipError("Account owner User was not hydrated");
      const parent = row.ParentId === null ? null : accountNames.get(row.ParentId);
      if (row.ParentId !== null && !parent) {
        relationshipError("Account parent was not hydrated");
      }
      return {
        Id: row.Id,
        Name: row.Name,
        Parent: parent ? { ...parent } : null,
        Owner: userSummary(owner),
        Roles: {
          csm: accountRoleContext(
            source,
            row,
            ACCOUNT_ROLE_FIELDS.csm,
            directUserRows,
          ),
          technical_advisor: accountRoleContext(
            source,
            row,
            ACCOUNT_ROLE_FIELDS.technical_advisor,
            directUserRows,
          ),
          presales: accountRoleContext(
            source,
            row,
            ACCOUNT_ROLE_FIELDS.presales,
            directUserRows,
          ),
        },
      };
    });

  const opportunities = [...opportunityRows.values()]
    .sort((left, right) => left.Id.localeCompare(right.Id))
    .map((row) => {
      const account = accountNames.get(row.AccountId);
      if (!account) {
        relationshipError("Opportunity Account was not hydrated");
      }
      const context = {
        Id: row.Id,
        Name: row.Name,
        Account: { ...account },
      };
      if (row.OwnerId !== undefined) {
        const owner = directUserRows.get(row.OwnerId);
        if (!owner) relationshipError("Opportunity owner User was not hydrated");
        context.Owner = userSummary(owner);
      }
      return context;
    });
  const opportunityContext = new Map(opportunities.map((row) => [row.Id, row]));
  const productOpportunities = [...new Set(
    profile.products.map((item) => item.OpportunityId),
  )].sort().map((id) => {
    const opportunity = opportunityContext.get(id);
    if (!opportunity) relationshipError("Product Opportunity was not hydrated");
    return { Id: opportunity.Id, Name: opportunity.Name };
  });

  const users = [...teamSources.values()]
    .sort((left, right) => left.Id.localeCompare(right.Id))
    .map((source) => {
      const row = directUserRows.get(source.Id);
      if (!row) relationshipError("Profile team User was not hydrated");
      const manager = source.ManagerId === null
        ? null
        : teamSources.has(source.ManagerId)
          ? directUserRows.get(source.ManagerId) ?? null
          : null;
      return {
        Id: row.Id,
        Name: row.Name,
        Title: row.Title,
        ManagerId: source.ManagerId,
        Manager: manager ? userSummary(manager) : null,
      };
    });

  const bindingCore = {
    source_profile_digest: digest(profile),
    read_plan_digest: readPlanDigest(readPlan),
    family_approval_receipt_digest:
      familyApprovalReceipt?.receipt_digest ?? null,
    org_identity_digest: digest(readPlan.org_identity),
  };
  return {
    schema_version: PROFILE_HYDRATION_SCHEMA,
    classification: CLASSIFICATION,
    binding: {
      ...bindingCore,
      binding_digest: digest(bindingCore),
    },
    accounts,
    opportunities,
    product_opportunities: productOpportunities,
    users,
    query_count: queryCount,
  };
}

import {
  ACCOUNT_ID,
  CAPS,
  USER_ID,
} from "./constants.mjs";
import { batchIds } from "./sf-client.mjs";
import {
  assertExactKeys,
  SafetyError,
  sanitizeText,
} from "./security.mjs";

const ACCOUNT_REQUIRED_FIELDS = Object.freeze([
  "Id",
  "Name",
  "ParentId",
  "OwnerId",
]);
const ACCOUNT_OPTIONAL_FIELDS = Object.freeze([
  "Type",
  "BillingCity",
  "BillingState",
  "BillingCountry",
]);
const USER_REQUIRED_FIELDS = Object.freeze([
  "Id",
  "Name",
  "Title",
]);

const FIELD_EXPECTATIONS = Object.freeze({
  Account: Object.freeze({
    Id: Object.freeze({ types: Object.freeze(["id"]), filterable: true }),
    Name: Object.freeze({ types: Object.freeze(["string"]) }),
    ParentId: Object.freeze({ types: Object.freeze(["reference"]), referenceTo: "Account" }),
    OwnerId: Object.freeze({ types: Object.freeze(["reference"]), referenceTo: "User" }),
    Type: Object.freeze({ types: Object.freeze(["picklist", "string"]) }),
    BillingCity: Object.freeze({ types: Object.freeze(["string"]) }),
    BillingState: Object.freeze({ types: Object.freeze(["string"]) }),
    BillingCountry: Object.freeze({ types: Object.freeze(["string"]) }),
  }),
  User: Object.freeze({
    Id: Object.freeze({ types: Object.freeze(["id"]), filterable: true }),
    Name: Object.freeze({ types: Object.freeze(["string"]) }),
    Title: Object.freeze({ types: Object.freeze(["string"]) }),
  }),
});

function compareText(left, right) {
  const a = String(left ?? "");
  const b = String(right ?? "");
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

function validateClient(client) {
  if (!client || typeof client.describe !== "function" || typeof client.query !== "function") {
    throw new SafetyError("INVALID_SF_CLIENT", "Resolution choices require an SfClient-like describe/query client");
  }
}

function validateMetadata(metadata, objectName, fieldName) {
  const expectation = FIELD_EXPECTATIONS[objectName][fieldName];
  if (!metadata
    || typeof metadata !== "object"
    || metadata.name !== fieldName
    || !expectation.types.includes(metadata.type)
    || (expectation.filterable === true && metadata.filterable !== true)
    || (expectation.referenceTo
      && (!Array.isArray(metadata.referenceTo)
        || !metadata.referenceTo.includes(expectation.referenceTo)))) {
    throw new SafetyError(
      "SCHEMA_FAILURE",
      `${objectName}.${fieldName} has missing or incompatible runtime metadata`,
    );
  }
}

function describedFields(describe, objectName, required, optional, warnings) {
  if (!(describe instanceof Map)) {
    throw new SafetyError("SCHEMA_FAILURE", `${objectName} describe did not return a field map`);
  }
  for (const field of required) validateMetadata(describe.get(field), objectName, field);
  const availableOptional = [];
  for (const field of optional) {
    if (!describe.has(field)) {
      warnings.push(sanitizeText(`OPTIONAL_FIELD_UNAVAILABLE:${objectName}.${field}`));
      continue;
    }
    validateMetadata(describe.get(field), objectName, field);
    availableOptional.push(field);
  }
  return [...required, ...availableOptional];
}

function requiredText(value, label, code) {
  if (typeof value !== "string") {
    throw new SafetyError(code, `${label} must be a non-empty string`);
  }
  const sanitized = sanitizeText(value);
  if (!sanitized) throw new SafetyError(code, `${label} must be a non-empty string`);
  return sanitized;
}

function optionalText(value, label) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value !== "string") {
    throw new SafetyError("INVALID_FIELD_TYPE", `${label} must be a string or null`);
  }
  return sanitizeText(value) || null;
}

function validateCandidates(candidates) {
  if (!Array.isArray(candidates)) {
    throw new SafetyError("INVALID_CANDIDATE_SET", "Resolution candidates must be an array");
  }
  if (candidates.length > CAPS.candidates) {
    throw new SafetyError(
      "CANDIDATE_CAP_EXCEEDED",
      `Resolution candidates exceed the deterministic cap ${CAPS.candidates}`,
    );
  }
  const normalized = candidates.map((candidate, index) => {
    assertExactKeys(
      candidate,
      ACCOUNT_REQUIRED_FIELDS,
      ACCOUNT_REQUIRED_FIELDS,
      `candidates[${index}]`,
    );
    if (!ACCOUNT_ID.test(candidate.Id)
      || (candidate.ParentId !== null && !ACCOUNT_ID.test(candidate.ParentId))
      || !USER_ID.test(candidate.OwnerId)) {
      throw new SafetyError(
        "INVALID_CANDIDATE_SET",
        "Resolution candidates contain an invalid Account, parent, or owner ID",
      );
    }
    return {
      Id: candidate.Id,
      Name: requiredText(candidate.Name, "Candidate Account Name", "INVALID_CANDIDATE_SET"),
      ParentId: candidate.ParentId,
      OwnerId: candidate.OwnerId,
    };
  });
  if (new Set(normalized.map((candidate) => candidate.Id)).size !== normalized.length) {
    throw new SafetyError("INVALID_CANDIDATE_SET", "Resolution candidate Account IDs must be unique");
  }
  return normalized;
}

function soqlIds(ids) {
  return ids.map((id) => `'${id}'`).join(",");
}

function exactRows(records, batch, {
  idPattern,
  code,
  objectName,
}) {
  if (!Array.isArray(records)) {
    throw new SafetyError(code, `${objectName} enrichment query did not return a record array`);
  }
  const expected = new Set(batch);
  const seen = new Set();
  for (const record of records) {
    if (!record || typeof record !== "object" || Array.isArray(record)
      || !idPattern.test(record.Id)
      || !expected.has(record.Id)
      || seen.has(record.Id)) {
      throw new SafetyError(
        code,
        `${objectName} enrichment returned an invalid, duplicate, or extra ID`,
      );
    }
    seen.add(record.Id);
  }
  if (records.length !== batch.length || batch.some((id) => !seen.has(id))) {
    throw new SafetyError(code, `${objectName} enrichment did not return every requested ID exactly once`);
  }
  return records;
}

async function queryExactRecords(client, {
  objectName,
  fields,
  ids,
  idPattern,
  code,
}) {
  const records = [];
  for (const batch of batchIds(ids)) {
    const queried = await client.query(
      `SELECT ${fields.join(", ")} FROM ${objectName} WHERE Id IN (${soqlIds(batch)}) ORDER BY Id LIMIT ${batch.length + 1}`,
    );
    records.push(...exactRows(queried, batch, { idPattern, code, objectName }));
  }
  return new Map(records.map((record) => [record.Id, record]));
}

function revalidatedCandidate(source, record, availableOptional, warnings) {
  const reread = {
    Id: record.Id,
    Name: requiredText(record.Name, "Candidate Account Name", "CANDIDATE_REVALIDATION_FAILED"),
    ParentId: record.ParentId,
    OwnerId: record.OwnerId,
  };
  if ((reread.ParentId !== null && !ACCOUNT_ID.test(reread.ParentId))
    || !USER_ID.test(reread.OwnerId)
    || reread.Name !== source.Name
    || reread.ParentId !== source.ParentId
    || reread.OwnerId !== source.OwnerId) {
    throw new SafetyError(
      "CANDIDATE_REVALIDATION_FAILED",
      "Candidate Account identity or relationships changed during display enrichment",
    );
  }
  const optional = Object.fromEntries(ACCOUNT_OPTIONAL_FIELDS.map((field) => {
    if (!availableOptional.includes(field)) return [field, null];
    const value = optionalText(record[field], `Account.${field}`);
    if (value === null) {
      warnings.push(sanitizeText(`OPTIONAL_VALUE_MISSING:Account.${field}`));
    }
    return [field, value];
  }));
  return { ...reread, ...optional };
}

/**
 * Builds display-only chooser rows with the same verified, org-bound client used
 * for v1 resolution. A chosen Account ID must be passed through v1 id-mode
 * resolution again before any Account receipt is accepted.
 */
export async function buildResolutionChoices({ candidates, client } = {}) {
  validateClient(client);
  const sourceCandidates = validateCandidates(candidates);
  if (!sourceCandidates.length) return { rows: [], warnings: [] };

  const warnings = [];
  const [accountDescribe, userDescribe] = await Promise.all([
    client.describe("Account"),
    client.describe("User"),
  ]);
  const accountFields = describedFields(
    accountDescribe,
    "Account",
    ACCOUNT_REQUIRED_FIELDS,
    ACCOUNT_OPTIONAL_FIELDS,
    warnings,
  );
  const userFields = describedFields(
    userDescribe,
    "User",
    USER_REQUIRED_FIELDS,
    [],
    warnings,
  );

  const candidateIds = sourceCandidates.map((candidate) => candidate.Id);
  const parentIds = sourceCandidates
    .map((candidate) => candidate.ParentId)
    .filter(Boolean);
  const accountIds = [...new Set([...candidateIds, ...parentIds])].sort(compareText);
  const ownerIds = [...new Set(sourceCandidates.map((candidate) => candidate.OwnerId))]
    .sort(compareText);

  const accountRecords = await queryExactRecords(client, {
    objectName: "Account",
    fields: accountFields,
    ids: accountIds,
    idPattern: ACCOUNT_ID,
    code: "ACCOUNT_ENRICHMENT_INCOMPLETE",
  });
  const rereadCandidates = new Map(sourceCandidates.map((source) => [
    source.Id,
    revalidatedCandidate(source, accountRecords.get(source.Id), accountFields, warnings),
  ]));

  const parents = new Map(parentIds.map((id) => {
    const record = accountRecords.get(id);
    return [
      id,
      requiredText(record?.Name, "Parent Account Name", "PARENT_IDENTITY_INCOMPLETE"),
    ];
  }));

  const ownerRecords = await queryExactRecords(client, {
    objectName: "User",
    fields: userFields,
    ids: ownerIds,
    idPattern: USER_ID,
    code: "OWNER_IDENTITY_INCOMPLETE",
  });
  const owners = new Map(ownerIds.map((id) => {
    const record = ownerRecords.get(id);
    return [id, {
      Name: requiredText(record?.Name, "Owner Name", "OWNER_IDENTITY_INCOMPLETE"),
      Title: optionalText(record?.Title, "User.Title"),
    }];
  }));

  const rows = sourceCandidates.map((source) => {
    const account = rereadCandidates.get(source.Id);
    const owner = owners.get(account.OwnerId);
    return {
      Id: account.Id,
      Name: account.Name,
      Type: account.Type,
      BillingCity: account.BillingCity,
      BillingState: account.BillingState,
      BillingCountry: account.BillingCountry,
      ParentId: account.ParentId,
      ParentName: account.ParentId === null ? null : parents.get(account.ParentId),
      OwnerId: account.OwnerId,
      OwnerName: owner.Name,
      OwnerTitle: owner.Title,
    };
  }).sort((left, right) => compareText(left.Name, right.Name) || compareText(left.Id, right.Id));

  return {
    rows,
    warnings: [...new Set(warnings)].sort(compareText),
  };
}

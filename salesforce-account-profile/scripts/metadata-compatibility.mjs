import { FIELD_MAP_VERSION } from "./constants.mjs";
import {
  FIELD_EXPECTATIONS,
  FIELD_POLICY,
} from "./workflow.mjs";
import { SafetyError } from "./security.mjs";

const FILTER_FIELDS = Object.freeze({
  Account: Object.freeze(["Id", "ParentId"]),
  Opportunity: Object.freeze([
    "AccountId",
    "IsClosed",
    "CloseDate",
    "StageName",
  ]),
  OpportunityLineItem: Object.freeze(["OpportunityId"]),
  PricebookEntry: Object.freeze([]),
  Product2: Object.freeze([]),
  User: Object.freeze(["Id"]),
});

function compatibleField(metadata, expectation) {
  return Boolean(
    metadata
    && metadata.name
    && expectation.types.includes(metadata.type)
    && (!expectation.referenceTo
      || (Array.isArray(metadata.referenceTo)
        && metadata.referenceTo.includes(expectation.referenceTo)))
    && (!expectation.relationshipName
      || metadata.relationshipName === expectation.relationshipName),
  );
}

function inspectObject(objectName, fields) {
  if (!(fields instanceof Map)) {
    throw new SafetyError(
      "SCHEMA_FAILURE",
      `${objectName} describe result must be a field map`,
    );
  }
  const policy = FIELD_POLICY[objectName];
  const expectations = FIELD_EXPECTATIONS[objectName];
  const requiredProblems = policy.required.filter((field) =>
    !compatibleField(fields.get(field), expectations[field]));
  const predicateProblems = FILTER_FIELDS[objectName].filter((field) =>
    fields.get(field)?.filterable !== true);
  if (requiredProblems.length || predicateProblems.length) {
    throw new SafetyError(
      "SCHEMA_FAILURE",
      `${objectName} metadata is incompatible with the required field map`,
      {
        object: objectName,
        required_fields: requiredProblems,
        filter_fields: predicateProblems,
      },
    );
  }

  const optionalAvailable = [];
  const optionalUnavailable = [];
  const optionalIncompatible = [];
  for (const field of policy.optional) {
    const metadata = fields.get(field);
    if (!metadata) {
      optionalUnavailable.push(field);
    } else if (!compatibleField(metadata, expectations[field])) {
      optionalIncompatible.push(field);
    } else {
      optionalAvailable.push(field);
    }
  }

  const preferredFamily = fields.get("Ultimate_Parent_name__c");
  if (preferredFamily
    && (preferredFamily.filterable !== true
      || !compatibleField(
        preferredFamily,
        expectations.Ultimate_Parent_name__c,
      ))) {
    if (!optionalIncompatible.includes("Ultimate_Parent_name__c")) {
      optionalIncompatible.push("Ultimate_Parent_name__c");
    }
    const index = optionalAvailable.indexOf("Ultimate_Parent_name__c");
    if (index >= 0) optionalAvailable.splice(index, 1);
  }

  return {
    object: objectName,
    required_fields_verified: policy.required.length,
    optional_fields_available: optionalAvailable.sort(),
    optional_fields_unavailable: optionalUnavailable.sort(),
    optional_fields_incompatible: optionalIncompatible.sort(),
    ...(objectName === "Opportunity"
      ? {
        active_stage_values: [
          ...(fields.get("StageName")?.activePicklistValues ?? []),
        ].sort(),
      }
      : {}),
  };
}

export async function inspectMetadataCompatibility(client) {
  if (!client || typeof client.describe !== "function") {
    throw new SafetyError(
      "INVALID_SF_CLIENT",
      "Metadata inspection requires a verified Salesforce client",
    );
  }
  const objects = [];
  for (const objectName of Object.keys(FIELD_POLICY)) {
    objects.push(inspectObject(
      objectName,
      await client.describe(objectName),
    ));
  }
  return {
    status: "compatible",
    field_map_version: FIELD_MAP_VERSION,
    objects,
    optional_warning_count: objects.reduce(
      (count, object) =>
        count
        + object.optional_fields_unavailable.length
        + object.optional_fields_incompatible.length,
      0,
    ),
  };
}

export const metadataCompatibilityInternals = Object.freeze({
  FILTER_FIELDS,
  compatibleField,
  inspectObject,
});

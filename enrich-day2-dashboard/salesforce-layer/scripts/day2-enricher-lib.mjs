import { spawnSync } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { constants as fsConstants } from "node:fs";
import {
  access,
  chmod,
  link,
  lstat,
  mkdir,
  readFile,
  realpath,
  rename,
  stat,
  unlink,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const DASHBOARD_SCHEMA_VERSION = "1.4";
export const PREVIEW_KIND = "salesforce-day2-preview/v1";
export const REPORT_KIND = "salesforce-day2-mapping-report/v1";
export const REVALIDATION_KIND = "salesforce-day2-revalidation/v1";

export const SCRIPT_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
export const SKILL_DIRECTORY = path.dirname(SCRIPT_DIRECTORY);
export const FIELD_MAP_PATH = path.join(SKILL_DIRECTORY, "references", "field-map.json");
export const BLANK_TEMPLATE_PATH = path.join(SKILL_DIRECTORY, "assets", "blank-dashboard-v1.4.json");

const ACCOUNT_ID_PATTERN = /^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
const SHA256_DIGEST_PATTERN = /^sha256:[a-f0-9]{64}$/;
const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const NUMERIC_LITERAL_PATTERN = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/;
const HEALTH_KEYS = [
  "overall",
  "agenticReadiness",
  "execSponsors",
  "effectiveAom",
  "lobEngagement",
  "valueRealization",
  "pipelineQuality",
  "resourcingModel",
  "customerAdvocacy",
];
const ALLOWED_SF_COMMANDS = new Set(["org display", "sobject describe", "data query"]);
const MAX_JSON_FILE_BYTES = 25 * 1024 * 1024;
const DEFAULT_SF_CLI_TIMEOUT_MS = 120_000;
const RECORD_OF_STRINGS = { $recordOf: "string" };
const DASHBOARD_SHAPE = {
  schemaVersion: "string",
  customerName: "string",
  tagline: "string",
  segment: "string",
  motion: "string",
  currentArr: "string",
  renewalDate: "string",
  deploymentType: "string",
  deliveryModel: "string",
  soldProducts: "string",
  useCases: "string",
  statusSummary: "string",
  sourceNotes: "string",
  healthConflictAcknowledged: "boolean",
  motionAnswers: RECORD_OF_STRINGS,
  metrics: {
    savings: { value: "string", note: "string" },
    automations: { value: "string", note: "string" },
    agentic: { value: "string", note: "string" },
    pipeline: { value: "string", note: "string" },
    utilization: { users: "string", robots: "string", consumables: "string" },
  },
  health: Object.fromEntries(
    HEALTH_KEYS.map((key) => [
      key,
      { status: "string", evidence: "string", mitigation: "string", owner: "string" },
    ]),
  ),
  goals: [{ text: "string", target: "string", owner: "string" }],
  executiveCadence: { type: "string", date: "string" },
  cadenceGoals: [{
    label: "string",
    target: "string",
    date: "string",
    owner: "string",
    status: "string",
  }],
  workstreams: [{
    name: "string",
    owner: "string",
    risk: "string",
    milestones: "string",
    outcomes: "string",
    atRisk: "boolean",
  }],
  consumptionPlan: {
    asOf: "string",
    forecastPeriod: "string",
    groups: [{
      element: "string",
      rows: [{
        product: "string",
        purchased: "string",
        utilization: "string",
        utilizationStatus: "string",
        forecast: { q1: "string", q2: "string", q3: "string", q4: "string" },
        comments: "string",
      }],
    }],
  },
  relationships: [{
    hierarchyOrder: "number",
    uipathName: "string",
    uipathRole: "string",
    customerName: "string",
    customerRole: "string",
    note: "string",
  }],
  eltAsks: [{ type: "string", owner: "string", ask: "string", status: "string" }],
  timeline: [{ date: "string", title: "string", description: "string", status: "string" }],
  sources: [{
    name: "string",
    size: "number",
    type: "string",
    kind: "string",
    text: "string",
    warning: "string",
  }],
};

export class EnricherError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "EnricherError";
    this.code = code;
  }
}

export function extractAccountId(input) {
  const candidate = String(input ?? "").trim();
  if (ACCOUNT_ID_PATTERN.test(candidate)) return candidate;

  let parsed;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new EnricherError(
      "INVALID_ACCOUNT",
      "Supply a Salesforce Account ID beginning with 001 or an HTTPS Account Lightning URL. Account names and Opportunity IDs are not accepted.",
    );
  }

  if (parsed.protocol !== "https:") {
    throw new EnricherError("INVALID_ACCOUNT", "Salesforce Account Lightning URLs must use HTTPS.");
  }
  const salesforceHostSuffixes = [".salesforce.com", ".force.com", ".salesforce.mil", ".force.mil"];
  if (!salesforceHostSuffixes.some((suffix) => parsed.hostname.toLowerCase().endsWith(suffix))) {
    throw new EnricherError(
      "INVALID_ACCOUNT",
      "The Account Lightning URL must use a recognized Salesforce or Force domain.",
    );
  }

  const match = parsed.pathname.match(
    /\/lightning\/r\/Account\/(001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?)(?:\/|$)/,
  );
  if (!match) {
    throw new EnricherError(
      "INVALID_ACCOUNT",
      "The URL must be an Account Lightning URL containing a 15- or 18-character ID beginning with 001.",
    );
  }
  return match[1];
}

export function isIsoDateOnly(value) {
  if (typeof value !== "string" || !ISO_DATE_PATTERN.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

export function formatPercent(value) {
  if (typeof value === "number") {
    return Number.isFinite(value) ? `${String(value)}%` : null;
  }
  if (typeof value !== "string") return null;
  const literal = value.trim();
  if (!NUMERIC_LITERAL_PATTERN.test(literal) || !Number.isFinite(Number(literal))) return null;
  return `${literal}%`;
}

export function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

export function sha256(value) {
  const input = Buffer.isBuffer(value) ? value : Buffer.from(String(value), "utf8");
  return createHash("sha256").update(input).digest("hex");
}

export function digestObject(value) {
  return sha256(stableStringify(value));
}

export function acceptedSourceValuesDigest(accountRecord, acceptedSourceFields) {
  if (
    !accountRecord ||
    typeof accountRecord !== "object" ||
    Array.isArray(accountRecord) ||
    !Array.isArray(acceptedSourceFields)
  ) {
    throw new EnricherError(
      "INVALID_MAPPING_REPORT",
      "Accepted Salesforce source values require an Account record and field list.",
    );
  }
  const fields = [...new Set(acceptedSourceFields)].sort();
  const values = fields.map((field) => [
    field,
    Object.hasOwn(accountRecord, field) ? deepClone(accountRecord[field]) : null,
  ]);
  return `sha256:${digestObject({ fields, values })}`;
}

export function deepClone(value) {
  if (value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value));
}

export function getAtPath(object, targetPath) {
  return targetPath.split(".").reduce((current, part) => current?.[part], object);
}

export function setAtPath(object, targetPath, value) {
  const parts = targetPath.split(".");
  let current = object;
  for (const part of parts.slice(0, -1)) {
    if (!current[part] || typeof current[part] !== "object" || Array.isArray(current[part])) {
      current[part] = {};
    }
    current = current[part];
  }
  current[parts.at(-1)] = deepClone(value);
}

export function isBlankDashboardValue(value, targetPath = "") {
  if (value === undefined || value === null) return true;
  if (typeof value === "string") return value.trim() === "";
  if (
    targetPath === "executiveCadence" &&
    value &&
    typeof value === "object" &&
    !Array.isArray(value)
  ) {
    return value.type === "nextQbr" && value.date === "";
  }
  return false;
}

function literalString(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function unique(values) {
  return [...new Set(values)];
}

function operationFor(base, targetPath, sourceFields, proposedValue, reason) {
  const existingValue = getAtPath(base, targetPath);
  let action;
  if (isBlankDashboardValue(existingValue, targetPath)) action = "fill";
  else if (stableStringify(existingValue) === stableStringify(proposedValue)) action = "no-change";
  else action = "conflict";
  return {
    targetPath,
    sourceFields,
    proposedValue: deepClone(proposedValue),
    existingValue: deepClone(existingValue),
    action,
    reason,
  };
}

function timelineSignature(event) {
  return `${event.date}\u0000${event.title}`;
}

function strictDate(record, field, warnings) {
  const value = record[field];
  if (value === undefined || value === null || value === "") return null;
  if (!isIsoDateOnly(value)) {
    warnings.push(`${field} was present but was not an exact ISO date-only value; it was skipped.`);
    return null;
  }
  return value;
}

export function buildProposal(accountRecord, baseDashboard) {
  if (!accountRecord || typeof accountRecord !== "object" || Array.isArray(accountRecord)) {
    throw new EnricherError("INVALID_SOURCE", "The Salesforce Account query did not return an object.");
  }
  if (!baseDashboard || typeof baseDashboard !== "object" || Array.isArray(baseDashboard)) {
    throw new EnricherError("INVALID_INPUT", "The dashboard input must be a JSON object.");
  }

  const accountId = extractAccountId(accountRecord.Id);
  const accountName =
    typeof accountRecord.Name === "string" && accountRecord.Name.trim()
      ? accountRecord.Name
      : null;
  if (accountName === null) {
    throw new EnricherError("MISSING_ACCOUNT_NAME", "Account.Name is required and cannot be blank.");
  }

  const existingCustomer = baseDashboard.customerName;
  if (
    typeof existingCustomer === "string" &&
    existingCustomer.trim() &&
    existingCustomer !== accountName
  ) {
    throw new EnricherError(
      "CUSTOMER_NAME_MISMATCH",
      "The exported dashboard belongs to a different customer. customerName conflicts are never approvable.",
    );
  }

  const operations = [];
  const skips = [];
  const warnings = [];
  operations.push(
    operationFor(
      baseDashboard,
      "customerName",
      ["Name"],
      accountName,
      "Exact Salesforce Account identity.",
    ),
  );

  const segmentParts = unique(
    [accountRecord.Segmentation_CS_3_0__c, accountRecord.Region__c]
      .map(literalString)
      .filter(Boolean),
  );
  if (segmentParts.length) {
    operations.push(
      operationFor(
        baseDashboard,
        "segment",
        ["Segmentation_CS_3_0__c", "Region__c"].filter((field) =>
          literalString(accountRecord[field]),
        ),
        segmentParts.join(" | "),
        "Literal Salesforce segmentation and region values joined with ' | '.",
      ),
    );
  } else {
    skips.push({
      targetPath: "segment",
      sourceFields: ["Segmentation_CS_3_0__c", "Region__c"],
      reason: "No nonblank source value.",
    });
  }

  const renewalDate = strictDate(accountRecord, "Earliest_Renewal_Expiry_Date__c", warnings);
  if (renewalDate) {
    operations.push(
      operationFor(
        baseDashboard,
        "renewalDate",
        ["Earliest_Renewal_Expiry_Date__c"],
        renewalDate,
        "Exact Salesforce ISO renewal date.",
      ),
    );
  } else {
    skips.push({
      targetPath: "renewalDate",
      sourceFields: ["Earliest_Renewal_Expiry_Date__c"],
      reason: "No valid exact ISO date-only source value.",
    });
  }

  const utilizationMappings = [
    ["Utilization_Users__c", "metrics.utilization.users"],
    ["Utilization_Robots__c", "metrics.utilization.robots"],
    ["Utilization_Consumables__c", "metrics.utilization.consumables"],
  ];
  for (const [sourceField, targetPath] of utilizationMappings) {
    const value = accountRecord[sourceField];
    const formatted = formatPercent(value);
    if (formatted !== null) {
      operations.push(
        operationFor(
          baseDashboard,
          targetPath,
          [sourceField],
          formatted,
          "Supplied Salesforce numeric percent formatted with '%' without calculation or clamping.",
        ),
      );
    } else {
      skips.push({
        targetPath,
        sourceFields: [sourceField],
        reason: value === null || value === undefined || value === ""
          ? "No source value."
          : "The source value was not a finite numeric literal.",
      });
      if (value !== null && value !== undefined && value !== "") {
        warnings.push(`${sourceField} was nonnumeric and was skipped.`);
      }
    }
  }

  const health = accountRecord.Health_Score_Label__c;
  if (health === "Red" || health === "Green") {
    operations.push(
      operationFor(
        baseDashboard,
        "health.overall.status",
        ["Health_Score_Label__c"],
        health,
        "Only exact literal Red or Green is accepted.",
      ),
    );
    operations.push({
      ...operationFor(
        baseDashboard,
        "health.overall.evidence",
        ["Health_Score_Label__c"],
        `Salesforce Account.Health_Score_Label__c = ${JSON.stringify(health)}.`,
        "Source-field evidence for the accepted overall health label.",
      ),
      requiresAcceptedPath: "health.overall.status",
    });
  } else {
    skips.push({
      targetPath: "health.overall",
      sourceFields: ["Health_Score_Label__c"],
      reason: health === null || health === undefined || health === ""
        ? "No source value."
        : "Only exact literal Red or Green is accepted.",
    });
    if (health !== null && health !== undefined && health !== "") {
      warnings.push(`Health_Score_Label__c was ${JSON.stringify(health)} and was skipped.`);
    }
  }

  const cadenceEvents = [];
  const qbrDate = strictDate(accountRecord, "Last_QBR__c", warnings);
  const ebcDate = strictDate(accountRecord, "Last_EBC__c", warnings);
  if (qbrDate) {
    cadenceEvents.push({
      sourceField: "Last_QBR__c",
      cadenceType: "lastQbr",
      date: qbrDate,
      tiePriority: 0,
      event: {
        date: qbrDate,
        title: "Last QBR",
        description: "Recorded in Salesforce Account.Last_QBR__c.",
        status: "Historical",
      },
    });
  }
  if (ebcDate) {
    cadenceEvents.push({
      sourceField: "Last_EBC__c",
      cadenceType: "lastEbc",
      date: ebcDate,
      tiePriority: 1,
      event: {
        date: ebcDate,
        title: "Last EBC",
        description: "Recorded in Salesforce Account.Last_EBC__c.",
        status: "Historical",
      },
    });
  }

  const existingTimeline = Array.isArray(baseDashboard.timeline) ? baseDashboard.timeline : [];
  const existingSignatures = new Set(existingTimeline.map(timelineSignature));
  const timelineOperations = cadenceEvents.map(({ sourceField, event }) => ({
    targetPath: `timeline[${event.title}:${event.date}]`,
    sourceFields: [sourceField],
    proposedValue: deepClone(event),
    action: existingSignatures.has(timelineSignature(event)) ? "no-change" : "append",
    reason: "Exact historical Salesforce cadence event.",
  }));

  if (cadenceEvents.length) {
    const latest = [...cadenceEvents].sort(
      (left, right) =>
        left.date.localeCompare(right.date) || left.tiePriority - right.tiePriority,
    ).at(-1);
    operations.push(
      operationFor(
        baseDashboard,
        "executiveCadence",
        cadenceEvents.map((item) => item.sourceField),
        { type: latest.cadenceType, date: latest.date },
        "Most recent exact Salesforce QBR/EBC date; Last EBC wins an exact date tie.",
      ),
    );
  } else {
    skips.push({
      targetPath: "executiveCadence",
      sourceFields: ["Last_QBR__c", "Last_EBC__c"],
      reason: "No valid exact ISO date-only source value.",
    });
  }

  return {
    accountId,
    accountName,
    operations,
    timelineOperations,
    skips,
    warnings,
  };
}

function provenanceMarker(accountRecord, fieldMapVersion) {
  return `[Salesforce provenance: ${fieldMapVersion} | ${accountRecord.Id} | ${accountRecord.LastModifiedDate}]`;
}

export function appendProvenance(existingNotes, accountRecord, acceptedFields, fieldMapVersion) {
  const notes = typeof existingNotes === "string" ? existingNotes : "";
  const marker = provenanceMarker(accountRecord, fieldMapVersion);
  const escapedMarker = marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const blockPattern = new RegExp(
    `${escapedMarker}\\n([\\s\\S]*?)\\n\\[/Salesforce provenance\\]`,
  );
  const existingBlock = notes.match(blockPattern);
  if (notes.includes(marker) && !existingBlock) {
    throw new EnricherError(
      "INVALID_PROVENANCE",
      "sourceNotes contains a malformed Salesforce provenance marker. Repair it before building.",
    );
  }
  const previousEntries = existingBlock
    ? [...existingBlock[1].matchAll(/^- Account\.([A-Za-z0-9_]+) = (.*)$/gm)]
    : [];
  const previousFields = previousEntries.map((match) => match[1]);
  const previousValues = new Map(previousEntries.map((match) => [match[1], match[2]]));
  const fields = unique(["Id", "LastModifiedDate", ...previousFields, ...acceptedFields]).sort();
  const lines = [
    marker,
    ...fields.map((field) => {
      const value = Object.hasOwn(accountRecord, field)
        ? JSON.stringify(accountRecord[field] ?? null)
        : previousValues.get(field) ?? "null";
      return `- Account.${field} = ${value}`;
    }),
    "[/Salesforce provenance]",
  ];
  const nextBlock = lines.join("\n");
  if (existingBlock) {
    const existingFullBlock = existingBlock[0];
    if (existingFullBlock === nextBlock) {
      return { value: notes, added: false, updated: false, marker };
    }
    return {
      value: notes.replace(blockPattern, nextBlock),
      added: false,
      updated: true,
      marker,
    };
  }
  return {
    value: [notes.trimEnd(), nextBlock].filter(Boolean).join("\n\n"),
    added: true,
    updated: false,
    marker,
  };
}

export function applyProposal(baseDashboard, accountRecord, proposal, approvedPaths, fieldMapVersion) {
  const approvals = new Set(approvedPaths ?? []);
  const conflictPaths = new Set(
    proposal.operations.filter((operation) => operation.action === "conflict").map((operation) => operation.targetPath),
  );
  for (const approvedPath of approvals) {
    if (!conflictPaths.has(approvedPath)) {
      throw new EnricherError(
        "INVALID_APPROVAL",
        `--approve-path ${JSON.stringify(approvedPath)} is not a current conflicting target path.`,
      );
    }
  }

  const dashboard = deepClone(baseDashboard);
  const mappingResults = [];
  const acceptedFields = new Set();
  const acceptedTargetPaths = new Set();
  const unresolvedConflicts = [];

  for (const operation of proposal.operations) {
    let applied = false;
    const blockedBy = operation.requiresAcceptedPath &&
      !acceptedTargetPaths.has(operation.requiresAcceptedPath)
      ? operation.requiresAcceptedPath
      : null;
    if (blockedBy && approvals.has(operation.targetPath)) {
      throw new EnricherError(
        "INVALID_APPROVAL_DEPENDENCY",
        `${operation.targetPath} cannot be approved unless ${blockedBy} is also accepted.`,
      );
    }
    if (blockedBy) {
      if (operation.action === "conflict") unresolvedConflicts.push(operation.targetPath);
    } else if (operation.action === "fill") {
      setAtPath(dashboard, operation.targetPath, operation.proposedValue);
      applied = true;
    } else if (operation.action === "no-change") {
      applied = true;
    } else if (operation.action === "conflict" && approvals.has(operation.targetPath)) {
      setAtPath(dashboard, operation.targetPath, operation.proposedValue);
      applied = true;
    } else if (operation.action === "conflict") {
      unresolvedConflicts.push(operation.targetPath);
    }

    if (applied) {
      operation.sourceFields.forEach((field) => acceptedFields.add(field));
      acceptedTargetPaths.add(operation.targetPath);
    }
    mappingResults.push({
      ...deepClone(operation),
      applied,
      blockedBy,
      approvedConflict: operation.action === "conflict" && approvals.has(operation.targetPath),
    });
  }

  if (!Array.isArray(dashboard.timeline)) dashboard.timeline = [];
  const signatures = new Set(dashboard.timeline.map(timelineSignature));
  for (const operation of proposal.timelineOperations) {
    const signature = timelineSignature(operation.proposedValue);
    const appended = !signatures.has(signature);
    if (appended) {
      dashboard.timeline.push(deepClone(operation.proposedValue));
      signatures.add(signature);
    }
    operation.sourceFields.forEach((field) => acceptedFields.add(field));
    mappingResults.push({
      ...deepClone(operation),
      applied: true,
      appended,
      approvedConflict: false,
    });
  }

  const provenance = appendProvenance(
    dashboard.sourceNotes,
    accountRecord,
    [...acceptedFields],
    fieldMapVersion,
  );
  dashboard.sourceNotes = provenance.value;
  dashboard.schemaVersion = DASHBOARD_SCHEMA_VERSION;

  return {
    dashboard,
    mappingResults,
    unresolvedConflicts,
    acceptedSourceFields: [...acceptedFields].sort(),
    provenanceAdded: provenance.added,
    provenanceUpdated: provenance.updated,
    provenanceMarker: provenance.marker,
  };
}

export function assertBlankHealthTemplate(template) {
  for (const key of HEALTH_KEYS) {
    if (template?.health?.[key]?.status !== "") {
      throw new EnricherError(
        "UNSAFE_TEMPLATE",
        `The bundled blank template must set health.${key}.status explicitly to an empty string.`,
      );
    }
  }
  return true;
}

export function validateDashboardInput(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new EnricherError("INVALID_INPUT", "The dashboard input must be a JSON object.");
  }
  if (value.schemaVersion !== DASHBOARD_SCHEMA_VERSION) {
    throw new EnricherError(
      "SCHEMA_MISMATCH",
      `Only dashboard schema ${DASHBOARD_SCHEMA_VERSION} is supported; received ${JSON.stringify(value.schemaVersion)}.`,
    );
  }
  assertShape(value, DASHBOARD_SHAPE, "dashboard");
  if (!["", "Re-Recruit", "Consumption", "Hybrid"].includes(value.motion)) {
    throw new EnricherError("INVALID_INPUT_SHAPE", "dashboard.motion is not a canonical schema 1.4 value.");
  }
  if (!["lastQbr", "nextQbr", "lastEbc", "nextEbc"].includes(value.executiveCadence.type)) {
    throw new EnricherError(
      "INVALID_INPUT_SHAPE",
      "dashboard.executiveCadence.type is not a canonical schema 1.4 value.",
    );
  }
  if (value.executiveCadence.date !== "" && !isIsoDateOnly(value.executiveCadence.date)) {
    throw new EnricherError(
      "INVALID_INPUT_SHAPE",
      "dashboard.executiveCadence.date must be blank or an exact ISO date-only value.",
    );
  }
  for (const [key, indicator] of Object.entries(value.health)) {
    if (!["", "Red", "Green"].includes(indicator.status)) {
      throw new EnricherError(
        "INVALID_INPUT_SHAPE",
        `dashboard.health.${key}.status is not a canonical schema 1.4 value.`,
      );
    }
  }
  for (const [groupIndex, group] of value.consumptionPlan.groups.entries()) {
    for (const [rowIndex, row] of group.rows.entries()) {
      if (!["Unset", "Green", "Orange", "Red"].includes(row.utilizationStatus)) {
        throw new EnricherError(
          "INVALID_INPUT_SHAPE",
          `dashboard.consumptionPlan.groups[${groupIndex}].rows[${rowIndex}].utilizationStatus is invalid.`,
        );
      }
    }
  }
  for (const [index, source] of value.sources.entries()) {
    if (source.size < 0) {
      throw new EnricherError(
        "INVALID_INPUT_SHAPE",
        `dashboard.sources[${index}].size must be nonnegative.`,
      );
    }
    if (!["text extracted", "attached, not extracted"].includes(source.kind)) {
      throw new EnricherError(
        "INVALID_INPUT_SHAPE",
        `dashboard.sources[${index}].kind is not a canonical schema 1.4 value.`,
      );
    }
  }
  for (const [index, relationship] of value.relationships.entries()) {
    if (!Number.isInteger(relationship.hierarchyOrder) || relationship.hierarchyOrder <= 0) {
      throw new EnricherError(
        "INVALID_INPUT_SHAPE",
        `dashboard.relationships[${index}].hierarchyOrder must be a positive integer.`,
      );
    }
  }
  return value;
}

function assertShape(value, shape, targetPath) {
  if (typeof shape === "string") {
    if (typeof value !== shape || (shape === "number" && !Number.isFinite(value))) {
      throw new EnricherError(
        "INVALID_INPUT_SHAPE",
        `${targetPath} must be a canonical schema 1.4 ${shape}.`,
      );
    }
    return;
  }
  if (Array.isArray(shape)) {
    if (!Array.isArray(value)) {
      throw new EnricherError("INVALID_INPUT_SHAPE", `${targetPath} must be a schema 1.4 array.`);
    }
    value.forEach((item, index) => assertShape(item, shape[0], `${targetPath}[${index}]`));
    return;
  }
  if (shape?.$recordOf) {
    if (!isPlainObject(value)) {
      throw new EnricherError("INVALID_INPUT_SHAPE", `${targetPath} must be a schema 1.4 object.`);
    }
    for (const [key, item] of Object.entries(value)) {
      assertShape(item, shape.$recordOf, `${targetPath}.${key}`);
    }
    return;
  }
  if (!isPlainObject(value)) {
    throw new EnricherError("INVALID_INPUT_SHAPE", `${targetPath} must be a schema 1.4 object.`);
  }
  const expectedKeys = Object.keys(shape).sort();
  const actualKeys = Object.keys(value).sort();
  if (stableStringify(expectedKeys) !== stableStringify(actualKeys)) {
    const missing = expectedKeys.filter((key) => !actualKeys.includes(key));
    const extra = actualKeys.filter((key) => !expectedKeys.includes(key));
    throw new EnricherError(
      "INVALID_INPUT_SHAPE",
      `${targetPath} has noncanonical keys. Missing: ${missing.join(", ") || "none"}. Extra: ${extra.join(", ") || "none"}.`,
    );
  }
  for (const key of expectedKeys) assertShape(value[key], shape[key], `${targetPath}.${key}`);
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

async function readBoundedFile(filePath, label, maxBytes = MAX_JSON_FILE_BYTES) {
  const resolvedPath = path.resolve(filePath);
  let details;
  try {
    details = await stat(resolvedPath);
  } catch (error) {
    throw new EnricherError("FILE_READ_FAILED", `${label} could not be read: ${error.message}`);
  }
  if (!details.isFile()) {
    throw new EnricherError("FILE_READ_FAILED", `${label} must be a regular file.`);
  }
  if (details.size > maxBytes) {
    throw new EnricherError(
      "FILE_TOO_LARGE",
      `${label} exceeds the ${maxBytes}-byte safety limit.`,
    );
  }
  return readFile(resolvedPath);
}

export async function assertPrivateArtifact(filePath, label) {
  const resolvedPath = path.resolve(filePath);
  const details = await lstat(resolvedPath);
  if (!details.isFile() || details.isSymbolicLink()) {
    throw new EnricherError("INSECURE_ARTIFACT", `${label} must be a regular, non-symlink file.`);
  }
  if (process.platform !== "win32" && (details.mode & 0o077) !== 0) {
    throw new EnricherError(
      "INSECURE_PERMISSIONS",
      `${label} exposes group or other permission bits; set mode 0600 before use.`,
    );
  }
  if (process.platform !== "win32") {
    const directoryDetails = await stat(path.dirname(resolvedPath));
    if ((directoryDetails.mode & 0o077) !== 0) {
      throw new EnricherError(
        "INSECURE_PERMISSIONS",
        `${label} is stored in a group- or other-accessible directory; use a mode 0700 working directory.`,
      );
    }
  }
  return resolvedPath;
}

export async function loadPrivateJson(filePath, label) {
  const resolvedPath = await assertPrivateArtifact(filePath, label);
  const raw = await readBoundedFile(resolvedPath, label);
  try {
    return JSON.parse(raw.toString("utf8"));
  } catch {
    throw new EnricherError("INVALID_JSON", `${label} is not valid JSON: ${resolvedPath}`);
  }
}

export async function loadFieldMap() {
  const raw = await readBoundedFile(FIELD_MAP_PATH, "Bundled Salesforce field map");
  const value = JSON.parse(raw.toString("utf8"));
  if (value.dashboardSchemaVersion !== DASHBOARD_SCHEMA_VERSION || typeof value.version !== "string") {
    throw new EnricherError("INVALID_FIELD_MAP", "The bundled field map is invalid or targets the wrong dashboard schema.");
  }
  return { value, digest: sha256(raw), path: FIELD_MAP_PATH };
}

export async function loadDashboardInput(inputPath) {
  const resolvedPath = path.resolve(inputPath ?? BLANK_TEMPLATE_PATH);
  const raw = await readBoundedFile(resolvedPath, "Dashboard input");
  let value;
  try {
    value = JSON.parse(raw.toString("utf8"));
  } catch {
    throw new EnricherError("INVALID_INPUT", `Dashboard input is not valid JSON: ${resolvedPath}`);
  }
  validateDashboardInput(value);
  if (!inputPath) assertBlankHealthTemplate(value);
  return {
    value,
    path: resolvedPath,
    kind: inputPath ? "exported-dashboard" : "blank-template",
    digest: sha256(raw),
  };
}

export function classifyAssetCandidates(records, asOfDate, endDatePrecedence) {
  if (!isIsoDateOnly(asOfDate)) {
    throw new EnricherError("INVALID_AS_OF", "Asset classification requires an ISO date-only as-of date.");
  }
  return records.map((record) => {
    const endDates = {};
    for (const field of endDatePrecedence) {
      const value = record[field];
      if (value !== null && value !== undefined && value !== "") endDates[field] = value;
    }
    const effective = endDatePrecedence
      .map((field) => ({
        field,
        value: record[field],
        dateOnly: candidateDateOnly(record[field]),
      }))
      .find(({ dateOnly }) => dateOnly);
    const classification = !effective
      ? "undated"
      : effective.dateOnly < asOfDate
        ? "expired"
        : "dated-current";
    return {
      assetId: record.Id ?? null,
      productName: record.Product2?.Name ?? null,
      productFamily: record.Product2?.Family ?? null,
      quantity: record.Quantity ?? null,
      currentQuantity: record.CurrentQuantity ?? null,
      subscriptionStartDate: record.SBQQ__SubscriptionStartDate__c ?? null,
      endDates,
      classification,
      classificationDateField: effective?.field ?? null,
      classificationDate: effective?.value ?? null,
      classificationDateOnly: effective?.dateOnly ?? null,
      manualReviewOnly: true,
    };
  });
}

function candidateDateOnly(value) {
  if (isIsoDateOnly(value)) return value;
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
    const dateOnly = value.slice(0, 10);
    if (isIsoDateOnly(dateOnly)) return dateOnly;
  }
  return null;
}

export function assertAllowedSfArgs(args) {
  if (!Array.isArray(args) || args.length < 2) {
    throw new EnricherError("UNSAFE_SF_COMMAND", "Salesforce CLI arguments must be a nonempty argument array.");
  }
  const command = `${args[0]} ${args[1]}`;
  if (!ALLOWED_SF_COMMANDS.has(command)) {
    throw new EnricherError(
      "UNSAFE_SF_COMMAND",
      `Salesforce CLI command ${JSON.stringify(command)} is not allowed by this read-only skill.`,
    );
  }
  return true;
}

function safeCliMessage(value) {
  return String(value ?? "")
    .replace(/(?:accessToken|sfdxAuthUrl|clientSecret)[^\n]*/gi, "[credential detail removed]")
    .replace(/\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~+/=-]+/gi, "[credential detail removed]")
    .replace(
      /\b(?:api[_-]?key|token|password|secret|client[_-]?secret)\s*[:=]\s*[^\s,;]+/gi,
      "[credential detail removed]",
    )
    .trim()
    .slice(0, 1200);
}

export function runSf(args, options = {}) {
  assertAllowedSfArgs(args);
  const sfBinary = options.sfBinary ?? "sf";
  const timeoutMs = options.timeoutMs ?? DEFAULT_SF_CLI_TIMEOUT_MS;
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 10 * 60_000) {
    throw new EnricherError(
      "INVALID_SF_TIMEOUT",
      "Salesforce CLI timeout must be an integer between 1 and 600000 milliseconds.",
    );
  }
  const result = spawnSync(sfBinary, args, {
    encoding: "utf8",
    shell: false,
    stdio: ["ignore", "pipe", "pipe"],
    maxBuffer: 25 * 1024 * 1024,
    timeout: timeoutMs,
    killSignal: "SIGTERM",
  });
  const category = `${args[0]} ${args[1]}`;
  if (result.error) {
    throw new EnricherError("SF_CLI_FAILURE", `Salesforce CLI ${category} failed: ${safeCliMessage(result.error.message)}`);
  }

  let payload;
  try {
    payload = JSON.parse(result.stdout);
  } catch {
    const detail = safeCliMessage(result.stderr) || "The command did not return JSON.";
    throw new EnricherError("SF_CLI_FAILURE", `Salesforce CLI ${category} failed: ${detail}`);
  }

  if (result.status !== 0 || payload.status !== 0) {
    const detail = safeCliMessage(payload.message ?? payload.name ?? result.stderr) || "Unknown CLI error.";
    throw new EnricherError("SF_CLI_FAILURE", `Salesforce CLI ${category} failed: ${detail}`);
  }
  return payload.result;
}

export function resolveOrg(targetOrg, runner = runSf) {
  const args = ["org", "display"];
  if (targetOrg) args.push("--target-org", String(targetOrg));
  args.push("--json");
  const result = runner(args);
  if (!result?.username || !result?.id) {
    throw new EnricherError(
      "ORG_NOT_RESOLVED",
      targetOrg
        ? "The supplied Salesforce org could not be resolved."
        : "No usable default Salesforce org was resolved. Supply --target-org explicitly.",
    );
  }
  return {
    username: result.username,
    orgId: result.id,
    alias: result.alias ?? null,
    targetOrg: result.username,
  };
}

function describeFields(sobject, targetOrg, runner) {
  const result = runner([
    "sobject",
    "describe",
    "--sobject",
    sobject,
    "--target-org",
    targetOrg,
    "--json",
  ]);
  if (!Array.isArray(result?.fields)) {
    throw new EnricherError("DESCRIBE_FAILURE", `Salesforce ${sobject} describe returned no fields.`);
  }
  return new Set(result.fields.map((field) => field.name).filter(Boolean));
}

function queryRecords(query, targetOrg, runner) {
  const result = runner([
    "data",
    "query",
    "--target-org",
    targetOrg,
    "--query",
    query,
    "--json",
  ]);
  if (!Array.isArray(result?.records)) {
    throw new EnricherError("QUERY_FAILURE", "Salesforce query returned no records array.");
  }
  return { records: result.records, totalSize: Number(result.totalSize ?? result.records.length) };
}

function projectRecord(record, fields) {
  return Object.fromEntries(
    fields.map((field) => {
      const value = field.split(".").reduce((current, part) => current?.[part], record);
      return [field, value ?? null];
    }),
  );
}

export function buildAccountQuery(accountId, availableFields, fieldMap) {
  const validatedId = extractAccountId(accountId);
  const required = fieldMap.account.requiredFields;
  const missingRequired = required.filter((field) => !availableFields.has(field));
  if (missingRequired.length) {
    throw new EnricherError(
      "MISSING_REQUIRED_FIELD",
      `Account describe is missing required field(s): ${missingRequired.join(", ")}.`,
    );
  }
  const optional = fieldMap.account.optionalFields.filter((field) => availableFields.has(field));
  const fields = [...required, ...optional];
  return {
    fields,
    missingOptionalFields: fieldMap.account.optionalFields.filter((field) => !availableFields.has(field)),
    soql: `SELECT ${fields.join(", ")} FROM Account WHERE Id = '${validatedId}' LIMIT 1`,
  };
}

export function buildAssetQuery(accountId, assetFields, productFields, fieldMap) {
  const validatedId = extractAccountId(accountId);
  for (const required of ["Id", "AccountId", "Status"]) {
    if (!assetFields.has(required)) {
      throw new EnricherError("ASSET_UNAVAILABLE", `Asset describe is missing ${required}; product candidates were skipped.`);
    }
  }

  const directFields = fieldMap.assets.directCandidateFields.filter((field) => assetFields.has(field));
  const relationshipFields = assetFields.has("Product2Id")
    ? fieldMap.assets.productCandidateFields
        .filter((field) => productFields.has(field))
        .map((field) => `Product2.${field}`)
    : [];
  const fields = unique([...directFields, ...relationshipFields]);
  return {
    fields,
    soql: `SELECT ${fields.join(", ")} FROM Asset WHERE AccountId = '${validatedId}' AND Status = 'Purchased' ORDER BY Id LIMIT 2001`,
  };
}

export function utcDateOnly(now = new Date()) {
  return now.toISOString().slice(0, 10);
}

export function fetchSalesforceSnapshot(accountId, targetOrg, fieldMap, options = {}) {
  const runner = options.runner ?? runSf;
  const asOfDate = options.asOfDate ?? utcDateOnly();
  const accountFields = describeFields("Account", targetOrg, runner);
  const accountQuery = buildAccountQuery(accountId, accountFields, fieldMap);
  const accountResult = queryRecords(accountQuery.soql, targetOrg, runner);
  if (accountResult.records.length !== 1) {
    throw new EnricherError(
      "ACCOUNT_NOT_FOUND",
      `Expected exactly one Salesforce Account for the supplied 001 ID; received ${accountResult.records.length}.`,
    );
  }
  const account = projectRecord(accountResult.records[0], accountQuery.fields);
  if (!literalString(account.Name)) {
    throw new EnricherError("MISSING_ACCOUNT_NAME", "Salesforce Account.Name is missing or inaccessible.");
  }
  if (!literalString(account.LastModifiedDate)) {
    throw new EnricherError("MISSING_FRESHNESS_FIELD", "Salesforce Account.LastModifiedDate is missing or inaccessible.");
  }

  let assetRecords = [];
  let assetFieldsSelected = [];
  const assetWarnings = [];
  const assetFields = describeFields("Asset", targetOrg, runner);
  let productFields = new Set();
  if (assetFields.has("Product2Id")) {
    productFields = describeFields("Product2", targetOrg, runner);
  }
  const assetQuery = buildAssetQuery(accountId, assetFields, productFields, fieldMap);
  assetFieldsSelected = assetQuery.fields;
  const assetResult = queryRecords(assetQuery.soql, targetOrg, runner);
  if (assetResult.totalSize > 2000 || assetResult.records.length > 2000) {
    assetWarnings.push("More than 2,000 purchased Assets matched; only the first 2,000 were retained for manual review.");
  }
  assetRecords = assetResult.records.slice(0, 2000).map((record) => projectRecord(record, assetQuery.fields));

  const candidates = classifyAssetCandidates(
    assetRecords.map((record) => {
      const product2 = {};
      if ("Product2.Name" in record) product2.Name = record["Product2.Name"];
      if ("Product2.Family" in record) product2.Family = record["Product2.Family"];
      return { ...record, Product2: product2 };
    }),
    asOfDate,
    fieldMap.assets.endDatePrecedence,
  );

  return {
    account,
    accountLastModifiedDate: account.LastModifiedDate,
    selectedAccountFields: accountQuery.fields,
    missingOptionalAccountFields: accountQuery.missingOptionalFields,
    accountDigest: digestObject({ fields: accountQuery.fields, record: account }),
    assetDigest: digestObject({ fields: assetFieldsSelected, records: assetRecords }),
    productCandidateDigest: digestObject(candidates),
    assetQueryFields: assetFieldsSelected,
    assetWarnings,
    productCandidates: candidates,
    classificationAsOf: asOfDate,
  };
}

export function validatePreview(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) || value.kind !== PREVIEW_KIND) {
    throw new EnricherError("INVALID_PREVIEW", "The file is not a Salesforce Day 2 preview.");
  }
  if (value.dashboardSchemaVersion !== DASHBOARD_SCHEMA_VERSION) {
    throw new EnricherError("SCHEMA_MISMATCH", "The preview does not target dashboard schema 1.4.");
  }
  const expectedTopLevelKeys = [
    "kind",
    "confidential",
    "createdAt",
    "dashboardSchemaVersion",
    "accountId",
    "org",
    "fieldMap",
    "input",
    "source",
    "proposal",
    "productCandidates",
    "productCandidateNotice",
    "integrityDigest",
  ];
  assertExactKeys(value, expectedTopLevelKeys, "preview");
  const unsignedPreview = Object.fromEntries(
    Object.entries(value).filter(([key]) => key !== "integrityDigest"),
  );
  if (
    typeof value.integrityDigest !== "string" ||
    value.integrityDigest !== digestObject(unsignedPreview)
  ) {
    throw new EnricherError(
      "PREVIEW_TAMPERED",
      "Preview integrity check failed. Create a new preview instead of editing preview metadata.",
    );
  }
  extractAccountId(value.accountId);
  if (value.confidential !== true || typeof value.createdAt !== "string") {
    throw new EnricherError("INVALID_PREVIEW", "Preview confidentiality or creation metadata is invalid.");
  }
  assertExactKeys(value.org, ["username", "orgId", "alias"], "preview.org");
  if (typeof value.org.username !== "string" || typeof value.org.orgId !== "string") {
    throw new EnricherError("INVALID_PREVIEW", "Preview Salesforce org identity is invalid.");
  }
  assertExactKeys(value.fieldMap, ["version", "digest"], "preview.fieldMap");
  assertExactKeys(value.input, ["path", "kind", "digest"], "preview.input");
  if (
    typeof value.input.path !== "string" ||
    !path.isAbsolute(value.input.path) ||
    !["blank-template", "exported-dashboard"].includes(value.input.kind)
  ) {
    throw new EnricherError("INVALID_PREVIEW", "Preview input metadata is invalid.");
  }
  assertExactKeys(
    value.source,
    [
      "accountLastModifiedDate",
      "accountDigest",
      "assetDigest",
      "productCandidateDigest",
      "classificationAsOf",
      "selectedAccountFields",
      "missingOptionalAccountFields",
      "assetQueryFields",
      "assetWarnings",
    ],
    "preview.source",
  );
  if (
    !isIsoDateOnly(value.source.classificationAsOf) ||
    !Array.isArray(value.source.selectedAccountFields) ||
    !Array.isArray(value.source.missingOptionalAccountFields) ||
    !Array.isArray(value.source.assetQueryFields) ||
    !Array.isArray(value.source.assetWarnings)
  ) {
    throw new EnricherError("INVALID_PREVIEW", "Preview source metadata is invalid.");
  }
  assertExactKeys(
    value.proposal,
    ["accountId", "accountName", "operations", "timelineOperations", "skips", "warnings"],
    "preview.proposal",
  );
  if (
    value.proposal.accountId !== value.accountId ||
    !Array.isArray(value.proposal.operations) ||
    !Array.isArray(value.proposal.timelineOperations) ||
    !Array.isArray(value.proposal.skips) ||
    !Array.isArray(value.proposal.warnings) ||
    !Array.isArray(value.productCandidates)
  ) {
    throw new EnricherError("INVALID_PREVIEW", "Preview proposal or candidate data is invalid.");
  }
  if (
    value.productCandidateNotice !==
    "Manual review only. These records are never written to soldProducts or consumptionPlan."
  ) {
    throw new EnricherError("INVALID_PREVIEW", "Preview product-candidate safety notice is invalid.");
  }
  return value;
}

function assertExactKeys(value, expectedKeys, targetPath) {
  if (!isPlainObject(value)) {
    throw new EnricherError("INVALID_PREVIEW", `${targetPath} must be an object.`);
  }
  const expected = [...expectedKeys].sort();
  const actual = Object.keys(value).sort();
  if (stableStringify(expected) !== stableStringify(actual)) {
    throw new EnricherError("INVALID_PREVIEW", `${targetPath} contains unexpected or missing keys.`);
  }
}

export function verifyFreshness(preview, current) {
  const storedCandidateDigest = digestObject(preview.productCandidates ?? []);
  const checks = [
    ["field-map version", preview.fieldMap?.version, current.fieldMapVersion],
    ["field-map digest", preview.fieldMap?.digest, current.fieldMapDigest],
    ["input JSON digest", preview.input?.digest, current.inputDigest],
    ["Account.LastModifiedDate", preview.source?.accountLastModifiedDate, current.accountLastModifiedDate],
    ["Account source digest", preview.source?.accountDigest, current.accountDigest],
    ["purchased Asset source digest", preview.source?.assetDigest, current.assetDigest],
    ["candidate classification date", preview.source?.classificationAsOf, current.classificationAsOf],
    ["stored product-candidate digest", preview.source?.productCandidateDigest, storedCandidateDigest],
    ["fresh product-candidate digest", preview.source?.productCandidateDigest, current.productCandidateDigest],
    [
      "selected Account field metadata",
      digestObject(preview.source?.selectedAccountFields),
      digestObject(current.selectedAccountFields),
    ],
    [
      "missing optional Account field metadata",
      digestObject(preview.source?.missingOptionalAccountFields),
      digestObject(current.missingOptionalAccountFields),
    ],
    [
      "Asset query field metadata",
      digestObject(preview.source?.assetQueryFields),
      digestObject(current.assetQueryFields),
    ],
    [
      "Asset warning metadata",
      digestObject(preview.source?.assetWarnings),
      digestObject(current.assetWarnings),
    ],
  ];
  const changed = checks.filter(([, expected, actual]) => expected !== actual).map(([label]) => label);
  if (changed.length) {
    throw new EnricherError(
      "STALE_PREVIEW",
      `Preview freshness check failed for: ${changed.join(", ")}. Create a new preview; do not bypass this check.`,
    );
  }
  return true;
}

export function slugifyAccountName(name, fallbackId) {
  const slug = String(name ?? "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return slug || String(fallbackId).toLowerCase();
}

export async function pathExists(filePath) {
  try {
    await access(filePath, fsConstants.F_OK);
    return true;
  } catch {
    return false;
  }
}

export async function canonicalPath(filePath) {
  const resolved = path.resolve(filePath);
  if (await pathExists(resolved)) return realpath(resolved);

  const missingParts = [];
  let cursor = resolved;
  while (!(await pathExists(cursor))) {
    const parent = path.dirname(cursor);
    if (parent === cursor) break;
    missingParts.unshift(path.basename(cursor));
    cursor = parent;
  }
  const canonicalAncestor = await realpath(cursor);
  return path.join(canonicalAncestor, ...missingParts);
}

export async function assertNoProtectedPathCollision(candidate, protectedPaths, label) {
  const candidateCanonical = await canonicalPath(candidate);
  const protectedCanonical = await Promise.all(protectedPaths.map(canonicalPath));
  const candidateIdentity = await pathIdentity(candidate);
  const protectedIdentities = await Promise.all(protectedPaths.map(pathIdentity));
  if (
    protectedCanonical.includes(candidateCanonical) ||
    (candidateIdentity !== null && protectedIdentities.includes(candidateIdentity))
  ) {
    throw new EnricherError(
      "OUTPUT_COLLISION",
      `${label} must not replace protected path ${candidateCanonical}.`,
    );
  }
  return candidateCanonical;
}

async function pathIdentity(filePath) {
  if (!(await pathExists(filePath))) return null;
  const details = await stat(filePath);
  return `${details.dev}:${details.ino}`;
}

async function inspectWritableTarget(target) {
  const resolved = path.resolve(target);
  try {
    const details = await lstat(resolved);
    if (!details.isFile() || details.isSymbolicLink()) {
      throw new EnricherError(
        "UNSAFE_OUTPUT_TARGET",
        `Existing output targets must be regular, non-symlink files: ${resolved}`,
      );
    }
    return {
      resolved,
      exists: true,
      identity: `${details.dev}:${details.ino}`,
    };
  } catch (error) {
    if (error?.code === "ENOENT") {
      return { resolved, exists: false, identity: "" };
    }
    throw error;
  }
}

async function captureWritableTargetStates(targets, overwrite) {
  const resolved = targets.map((target) => path.resolve(target));
  const canonical = await Promise.all(resolved.map(canonicalPath));
  const states = await Promise.all(resolved.map(inspectWritableTarget));
  const identities = states.filter((state) => state.exists).map((state) => state.identity);
  if (new Set(canonical).size !== canonical.length || new Set(identities).size !== identities.length) {
    throw new EnricherError("OUTPUT_COLLISION", "Output, report, preview, and input paths must be distinct.");
  }
  if (!overwrite) {
    const existing = states.filter((state) => state.exists).map((state) => state.resolved);
    if (existing.length) {
      throw new EnricherError(
        "OUTPUT_EXISTS",
        `Refusing to overwrite existing file(s): ${existing.join(", ")}. Use --overwrite only with explicit permission for these exact paths.`,
      );
    }
  }
  return states;
}

export async function assertWritableTargets(targets, overwrite) {
  const states = await captureWritableTargetStates(targets, overwrite);
  return states.map((state) => state.resolved);
}

async function ensurePrivateDirectory(directory) {
  const resolvedDirectory = path.resolve(directory);
  const existed = await pathExists(resolvedDirectory);
  await mkdir(resolvedDirectory, { recursive: true, mode: 0o700 });
  if (!existed && process.platform !== "win32") {
    await chmod(resolvedDirectory, 0o700);
  }
  const details = await stat(resolvedDirectory);
  if (!details.isDirectory()) {
    throw new EnricherError("UNSAFE_OUTPUT_DIRECTORY", `${resolvedDirectory} is not a directory.`);
  }
  if (process.platform !== "win32" && (details.mode & 0o077) !== 0) {
    throw new EnricherError(
      "INSECURE_PERMISSIONS",
      `Output directory exposes group or other permission bits; set mode 0700: ${resolvedDirectory}`,
    );
  }
  return resolvedDirectory;
}

export async function writeProtectedJson(filePath, value, overwrite = false, protectedPaths = []) {
  const resolvedPath = path.resolve(filePath);
  if (protectedPaths.length) {
    await assertNoProtectedPathCollision(resolvedPath, protectedPaths, "JSON output");
  }
  await ensurePrivateDirectory(path.dirname(resolvedPath));
  if (protectedPaths.length) {
    await assertNoProtectedPathCollision(resolvedPath, protectedPaths, "JSON output");
  }
  const content = `${JSON.stringify(value, null, 2)}\n`;
  if (!overwrite) {
    await writeFile(resolvedPath, content, { encoding: "utf8", flag: "wx", mode: 0o600 });
    return resolvedPath;
  }

  const temporary = path.join(
    path.dirname(resolvedPath),
    `.${path.basename(resolvedPath)}.${process.pid}.${randomBytes(6).toString("hex")}.tmp`,
  );
  try {
    await writeFile(temporary, content, { encoding: "utf8", flag: "wx", mode: 0o600 });
    await rename(temporary, resolvedPath);
    if (process.platform !== "win32") await chmod(resolvedPath, 0o600);
  } catch (error) {
    await unlink(temporary).catch(() => {});
    throw error;
  }
  return resolvedPath;
}

export async function writeProtectedJsonPairAtomic(
  entries,
  { overwrite = false, protectedPaths = [] } = {},
) {
  if (!Array.isArray(entries) || entries.length !== 2) {
    throw new EnricherError(
      "INVALID_OUTPUT_BATCH",
      "Salesforce build must commit exactly one dashboard and one mapping report.",
    );
  }
  const targets = entries.map((entry) => path.resolve(entry.filePath));
  const targetStates = await captureWritableTargetStates(targets, overwrite);
  const prepared = [];
  try {
    for (let index = 0; index < entries.length; index += 1) {
      const entry = entries[index];
      const resolved = targets[index];
      await ensurePrivateDirectory(path.dirname(resolved));
      await assertNoProtectedPathCollision(resolved, protectedPaths, "JSON output");
      const nonce = `${process.pid}.${randomBytes(6).toString("hex")}`;
      const temporary = path.join(
        path.dirname(resolved),
        `.${path.basename(resolved)}.${nonce}.tmp`,
      );
      const backup = path.join(
        path.dirname(resolved),
        `.${path.basename(resolved)}.${nonce}.bak`,
      );
      await writeFile(
        temporary,
        `${JSON.stringify(entry.value, null, 2)}\n`,
        { encoding: "utf8", flag: "wx", mode: 0o600 },
      );
      prepared.push({ resolved, temporary, backup, committed: false, backedUp: false });
    }

    for (let index = 0; index < prepared.length; index += 1) {
      const entry = prepared[index];
      const expected = targetStates[index];
      await assertNoProtectedPathCollision(entry.resolved, protectedPaths, "JSON output");
      const current = await inspectWritableTarget(entry.resolved);
      if (
        current.exists !== expected.exists ||
        (current.exists && current.identity !== expected.identity)
      ) {
        throw new EnricherError(
          "OUTPUT_TARGET_CHANGED",
          `Output target changed after preflight: ${entry.resolved}`,
        );
      }
      if (overwrite && await pathExists(entry.resolved)) {
        await rename(entry.resolved, entry.backup);
        entry.backedUp = true;
      }
      if (overwrite) {
        await rename(entry.temporary, entry.resolved);
      } else {
        await link(entry.temporary, entry.resolved);
      }
      entry.committed = true;
      if (process.platform !== "win32") await chmod(entry.resolved, 0o600);
    }
  } catch (error) {
    const rollbackFailures = [];
    for (const entry of [...prepared].reverse()) {
      try {
        if (entry.committed && await pathExists(entry.resolved)) {
          await unlink(entry.resolved);
        }
        if (entry.backedUp && await pathExists(entry.backup)) {
          await rename(entry.backup, entry.resolved);
        }
      } catch (rollbackError) {
        rollbackFailures.push(`${entry.resolved}: ${rollbackError.message}`);
      }
      await unlink(entry.temporary).catch(() => {});
      if (!entry.backedUp) await unlink(entry.backup).catch(() => {});
    }
    if (rollbackFailures.length) {
      throw new EnricherError(
        "ATOMIC_ROLLBACK_FAILED",
        `Salesforce output commit failed and rollback needs manual recovery. ${rollbackFailures.join(" | ")}`,
      );
    }
    if (error?.code === "EEXIST") {
      throw new EnricherError(
        "OUTPUT_EXISTS",
        "An output appeared before the atomic Salesforce pair commit.",
      );
    }
    throw error;
  }
  for (const entry of prepared) {
    await unlink(entry.temporary).catch(() => {});
    await unlink(entry.backup).catch(() => {});
  }
  return targets;
}

export async function removePreviewFile(previewPath) {
  const resolvedPath = path.resolve(previewPath);
  await unlink(resolvedPath);
  return resolvedPath;
}

export function createPreviewDocument({
  accountId,
  org,
  snapshot,
  input,
  fieldMap,
  fieldMapDigest,
  proposal,
}) {
  const document = {
    kind: PREVIEW_KIND,
    confidential: true,
    createdAt: new Date().toISOString(),
    dashboardSchemaVersion: DASHBOARD_SCHEMA_VERSION,
    accountId,
    org: {
      username: org.username,
      orgId: org.orgId,
      alias: org.alias,
    },
    fieldMap: {
      version: fieldMap.version,
      digest: fieldMapDigest,
    },
    input: {
      path: input.path,
      kind: input.kind,
      digest: input.digest,
    },
    source: {
      accountLastModifiedDate: snapshot.accountLastModifiedDate,
      accountDigest: snapshot.accountDigest,
      assetDigest: snapshot.assetDigest,
      productCandidateDigest: snapshot.productCandidateDigest,
      classificationAsOf: snapshot.classificationAsOf,
      selectedAccountFields: snapshot.selectedAccountFields,
      missingOptionalAccountFields: snapshot.missingOptionalAccountFields,
      assetQueryFields: snapshot.assetQueryFields,
      assetWarnings: snapshot.assetWarnings,
    },
    proposal,
    productCandidates: snapshot.productCandidates,
    productCandidateNotice:
      "Manual review only. These records are never written to soldProducts or consumptionPlan.",
  };
  return {
    ...document,
    integrityDigest: digestObject(document),
  };
}

export function createMappingReport({
  preview,
  buildResult,
  snapshot,
  dashboardOutput,
  reportOutput,
  fieldMap,
  fieldMapDigest,
}) {
  return {
    kind: REPORT_KIND,
    confidential: true,
    builtAt: new Date().toISOString(),
    dashboardSchemaVersion: DASHBOARD_SCHEMA_VERSION,
    accountId: snapshot.account.Id,
    org: preview.org,
    sourceLastModifiedDate: snapshot.accountLastModifiedDate,
    fieldMapVersion: fieldMap.version,
    fieldMapDigest: `sha256:${fieldMapDigest}`,
    acceptedSourceValuesDigest: acceptedSourceValuesDigest(
      snapshot.account,
      buildResult.acceptedSourceFields,
    ),
    dashboardOutput,
    reportOutput,
    mappings: buildResult.mappingResults,
    unresolvedConflicts: buildResult.unresolvedConflicts,
    acceptedSourceFields: buildResult.acceptedSourceFields,
    provenanceAdded: buildResult.provenanceAdded,
    provenanceUpdated: buildResult.provenanceUpdated,
    skippedMappings: preview.proposal.skips,
    warnings: [
      ...preview.proposal.warnings,
      ...snapshot.missingOptionalAccountFields.map(
        (field) => `Optional Salesforce Account field unavailable and skipped: ${field}.`,
      ),
      ...snapshot.assetWarnings,
    ],
    productCandidates: snapshot.productCandidates,
    productCandidateNotice:
      "Manual review only. No product candidate was written to dashboard soldProducts or consumptionPlan.",
    explicitlyNotMapped: fieldMap.neverMap,
  };
}

const MAPPING_REPORT_KEYS = [
  "kind",
  "confidential",
  "builtAt",
  "dashboardSchemaVersion",
  "accountId",
  "org",
  "sourceLastModifiedDate",
  "fieldMapVersion",
  "fieldMapDigest",
  "acceptedSourceValuesDigest",
  "dashboardOutput",
  "reportOutput",
  "mappings",
  "unresolvedConflicts",
  "acceptedSourceFields",
  "provenanceAdded",
  "provenanceUpdated",
  "skippedMappings",
  "warnings",
  "productCandidates",
  "productCandidateNotice",
  "explicitlyNotMapped",
];

export function validateMappingReport(value) {
  assertExactKeys(value, MAPPING_REPORT_KEYS, "mapping report");
  if (
    value.kind !== REPORT_KIND ||
    value.confidential !== true ||
    value.dashboardSchemaVersion !== DASHBOARD_SCHEMA_VERSION
  ) {
    throw new EnricherError(
      "INVALID_MAPPING_REPORT",
      "The Salesforce mapping report kind, confidentiality marker, or dashboard schema is invalid.",
    );
  }
  extractAccountId(value.accountId);
  assertExactKeys(value.org, ["username", "orgId", "alias"], "mapping report org");
  if (
    typeof value.org.username !== "string" ||
    !value.org.username ||
    typeof value.org.orgId !== "string" ||
    !value.org.orgId ||
    typeof value.sourceLastModifiedDate !== "string" ||
    typeof value.fieldMapVersion !== "string" ||
    !SHA256_DIGEST_PATTERN.test(value.fieldMapDigest) ||
    !SHA256_DIGEST_PATTERN.test(value.acceptedSourceValuesDigest) ||
    !Array.isArray(value.acceptedSourceFields) ||
    !Array.isArray(value.productCandidates)
  ) {
    throw new EnricherError("INVALID_MAPPING_REPORT", "The Salesforce mapping report metadata is invalid.");
  }
  return value;
}

export async function loadMappingReport(reportPath) {
  const resolvedPath = await assertPrivateArtifact(reportPath, "Salesforce mapping report");
  const value = validateMappingReport(
    await loadPrivateJson(resolvedPath, "Salesforce mapping report"),
  );
  const canonicalReportPath = await canonicalPath(resolvedPath);
  if (await canonicalPath(value.reportOutput) !== canonicalReportPath) {
    throw new EnricherError(
      "INVALID_MAPPING_REPORT",
      "The Salesforce mapping report does not identify its own canonical path.",
    );
  }
  return { value, path: canonicalReportPath };
}

export function createSalesforceRevalidationReceipt({
  report,
  reportPath,
  snapshot,
  org,
  fieldMap,
  fieldMapDigest,
  verifiedAt = new Date().toISOString(),
}) {
  validateMappingReport(report);
  if (
    report.accountId !== snapshot.account.Id ||
    report.org.orgId !== org.orgId ||
    report.org.username !== org.username ||
    report.fieldMapVersion !== fieldMap.version
  ) {
    throw new EnricherError(
      "STALE_SALESFORCE",
      "Salesforce Account, org, or field-map identity changed after the mapping report was built.",
    );
  }
  if (report.fieldMapDigest !== `sha256:${fieldMapDigest}`) {
    throw new EnricherError(
      "STALE_SALESFORCE",
      "The Salesforce field-map content changed after the mapping report was built.",
    );
  }
  if (report.sourceLastModifiedDate !== snapshot.accountLastModifiedDate) {
    throw new EnricherError(
      "STALE_SALESFORCE",
      "Salesforce Account.LastModifiedDate changed after contextual preview; regenerate the Salesforce and contextual previews.",
    );
  }
  const missingAcceptedFields = report.acceptedSourceFields.filter(
    (field) => !snapshot.selectedAccountFields.includes(field),
  );
  if (missingAcceptedFields.length) {
    throw new EnricherError(
      "STALE_SALESFORCE",
      `Previously accepted Salesforce fields are no longer readable: ${missingAcceptedFields.join(", ")}.`,
    );
  }
  const currentAcceptedSourceValuesDigest = acceptedSourceValuesDigest(
    snapshot.account,
    report.acceptedSourceFields,
  );
  if (currentAcceptedSourceValuesDigest !== report.acceptedSourceValuesDigest) {
    throw new EnricherError(
      "STALE_SALESFORCE",
      "One or more accepted Salesforce source values changed after the mapping report was built.",
    );
  }
  if (digestObject(report.productCandidates) !== snapshot.productCandidateDigest) {
    throw new EnricherError(
      "STALE_SALESFORCE",
      "Purchased-Asset candidates changed after contextual preview; regenerate the Salesforce and contextual previews.",
    );
  }
  const payload = {
    kind: REVALIDATION_KIND,
    confidential: true,
    dashboardSchemaVersion: DASHBOARD_SCHEMA_VERSION,
    verifiedAt,
    accountId: snapshot.account.Id,
    accountName: snapshot.account.Name,
    org: {
      username: org.username,
      orgId: org.orgId,
    },
    fieldMap: {
      version: fieldMap.version,
      digest: report.fieldMapDigest,
    },
    mappingReport: {
      path: path.resolve(reportPath),
      digest: `sha256:${digestObject(report)}`,
    },
    source: {
      accountLastModifiedDate: snapshot.accountLastModifiedDate,
      acceptedSourceFieldsDigest: `sha256:${digestObject(report.acceptedSourceFields)}`,
      acceptedSourceValuesDigest: report.acceptedSourceValuesDigest,
      productCandidateDigest: `sha256:${snapshot.productCandidateDigest}`,
    },
    allowedCommands: [...ALLOWED_SF_COMMANDS].sort(),
  };
  return {
    ...payload,
    integrityDigest: `sha256:${digestObject(payload)}`,
  };
}

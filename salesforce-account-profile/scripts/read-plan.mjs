import {
  ACCOUNT_ID,
  CLASSIFICATION,
  CONTRACTS,
  FIELD_MAP_VERSION,
  OPPORTUNITY_SCOPES,
  ORG_ID,
  OUTPUT_TYPES,
  PRESETS,
  PROFILE_SECTIONS,
  SESSION_TTL_MS,
} from "./constants.mjs";
import {
  assertExactKeys,
  digest,
  SafetyError,
  sanitizeText,
  validateAlias,
} from "./security.mjs";

const SESSION_ID = /^[a-f0-9]{32}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const APPROVAL_KINDS = new Set(["org_and_plan", "family_scope"]);

function validateSafeString(value, label, maximum = 255) {
  if (typeof value !== "string" || value.length < 1 || value.length > maximum || sanitizeText(value) !== value) {
    throw new SafetyError("INVALID_READ_PLAN", `${label} must be safe text between 1 and ${maximum} characters`);
  }
  return value;
}

function validateInstant(value, label) {
  if (typeof value !== "string") throw new SafetyError("INVALID_READ_PLAN", `${label} must be an ISO timestamp`);
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString() !== value) {
    throw new SafetyError("INVALID_READ_PLAN", `${label} must be a canonical ISO timestamp`);
  }
  return parsed;
}

function validateCalendarDate(value, label) {
  if (value === null) return null;
  if (typeof value !== "string" || !ISO_DATE.test(value)) {
    throw new SafetyError("INVALID_READ_PLAN", `${label} must be null or YYYY-MM-DD`);
  }
  const parsed = new Date(`${value}T00:00:00.000Z`);
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) {
    throw new SafetyError("INVALID_READ_PLAN", `${label} is not a real calendar date`);
  }
  return value;
}

function validateOrgIdentity(identity) {
  assertExactKeys(
    identity,
    ["target_org", "org_id", "username", "instance_url", "connected_status"],
    ["target_org", "org_id", "username", "instance_url", "connected_status"],
    "read_plan.org_identity",
  );
  validateAlias(identity.target_org);
  if (!ORG_ID.test(identity.org_id)) throw new SafetyError("INVALID_READ_PLAN", "org_identity.org_id is invalid");
  validateSafeString(identity.username, "org_identity.username");
  validateSafeString(identity.connected_status, "org_identity.connected_status", 80);
  let url;
  try {
    url = new URL(identity.instance_url);
  } catch {
    throw new SafetyError("INVALID_READ_PLAN", "org_identity.instance_url must be a valid HTTPS origin");
  }
  if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    throw new SafetyError("INVALID_READ_PLAN", "org_identity.instance_url must be an HTTPS origin without credentials, path, query, or fragment");
  }
}

function validateAccountSelector(selector) {
  assertExactKeys(selector, ["mode", "value"], ["mode", "value"], "read_plan.account_selector");
  if (!["id", "exact_name", "prefix"].includes(selector.mode)) {
    throw new SafetyError("INVALID_READ_PLAN", "account_selector.mode must be id, exact_name, or prefix");
  }
  validateSafeString(selector.value, "account_selector.value");
  if (selector.mode === "id" && !ACCOUNT_ID.test(selector.value)) {
    throw new SafetyError("INVALID_READ_PLAN", "account_selector.value must be an Account ID in id mode");
  }
}

function validateSelectedAccount(account) {
  if (account === null) return;
  assertExactKeys(account, ["Id", "Name"], ["Id", "Name"], "read_plan.selected_account");
  if (!ACCOUNT_ID.test(account.Id)) throw new SafetyError("INVALID_READ_PLAN", "selected_account.Id is invalid");
  validateSafeString(account.Name, "selected_account.Name");
}

function validateFilters(filters) {
  assertExactKeys(
    filters,
    ["close_date_from", "close_date_to", "stages"],
    ["close_date_from", "close_date_to", "stages"],
    "read_plan.filters",
  );
  const from = validateCalendarDate(filters.close_date_from, "filters.close_date_from");
  const to = validateCalendarDate(filters.close_date_to, "filters.close_date_to");
  if (from && to && from > to) {
    throw new SafetyError("INVALID_READ_PLAN", "filters.close_date_from must not be after close_date_to");
  }
  if (!Array.isArray(filters.stages) || filters.stages.length > 50) {
    throw new SafetyError("INVALID_READ_PLAN", "filters.stages must be an array of at most 50 values");
  }
  for (const stage of filters.stages) validateSafeString(stage, "filters.stages[]", 80);
  if (new Set(filters.stages).size !== filters.stages.length) {
    throw new SafetyError("INVALID_READ_PLAN", "filters.stages must be unique");
  }
  const canonicalStages = [...filters.stages].sort((left, right) => left.localeCompare(right, "en-US"));
  if (canonicalStages.some((stage, index) => stage !== filters.stages[index])) {
    throw new SafetyError("INVALID_READ_PLAN", "filters.stages must use canonical order");
  }
}

function validatePreset(plan) {
  if (plan.preset === "custom") return;
  const expected = PRESETS[plan.preset];
  if (!expected) throw new SafetyError("INVALID_READ_PLAN", "preset is unsupported");
  if (plan.scope !== expected.scope
    || plan.opportunity_scope !== expected.opportunity_scope
    || digest(plan.requested_sections) !== digest(expected.sections)) {
    throw new SafetyError("INVALID_READ_PLAN", `preset ${plan.preset} does not match its fixed scope`);
  }
}

export function validateReadPlan(plan) {
  assertExactKeys(
    plan,
    [
      "schema_version",
      "classification",
      "session_id",
      "org_identity",
      "runtime_attestation_digest",
      "account_selector",
      "selected_account",
      "account_receipt_digest",
      "family_account_ids",
      "preset",
      "requested_sections",
      "scope",
      "opportunity_scope",
      "filters",
      "field_map_version",
      "output_type",
      "issued_at",
      "expires_at",
    ],
    [
      "schema_version",
      "classification",
      "session_id",
      "org_identity",
      "runtime_attestation_digest",
      "account_selector",
      "selected_account",
      "account_receipt_digest",
      "family_account_ids",
      "preset",
      "requested_sections",
      "scope",
      "opportunity_scope",
      "filters",
      "field_map_version",
      "output_type",
      "issued_at",
      "expires_at",
    ],
    "read_plan",
  );
  if (plan.schema_version !== CONTRACTS.readPlan || plan.classification !== CLASSIFICATION) {
    throw new SafetyError("INVALID_READ_PLAN", "read plan schema or classification is invalid");
  }
  if (!SESSION_ID.test(plan.session_id)) throw new SafetyError("INVALID_READ_PLAN", "session_id is invalid");
  validateOrgIdentity(plan.org_identity);
  if (!SHA256.test(plan.runtime_attestation_digest)) {
    throw new SafetyError("INVALID_READ_PLAN", "runtime_attestation_digest is invalid");
  }
  validateAccountSelector(plan.account_selector);
  validateSelectedAccount(plan.selected_account);
  if (plan.account_receipt_digest !== null && !SHA256.test(plan.account_receipt_digest)) {
    throw new SafetyError("INVALID_READ_PLAN", "account_receipt_digest is invalid");
  }
  if ((plan.selected_account === null) !== (plan.account_receipt_digest === null)) {
    throw new SafetyError("INVALID_READ_PLAN", "selected_account and account_receipt_digest must be populated together");
  }
  if (!Array.isArray(plan.family_account_ids)
    || plan.family_account_ids.some((id) => !ACCOUNT_ID.test(id))
    || new Set(plan.family_account_ids).size !== plan.family_account_ids.length
    || [...plan.family_account_ids].sort().some((id, index) => id !== plan.family_account_ids[index])) {
    throw new SafetyError("INVALID_READ_PLAN", "family_account_ids must be a sorted unique Account-ID array");
  }
  if (plan.selected_account === null && plan.family_account_ids.length) {
    throw new SafetyError("INVALID_READ_PLAN", "family_account_ids require a selected Account");
  }
  if (plan.family_account_ids.length && !plan.family_account_ids.includes(plan.selected_account.Id)) {
    throw new SafetyError("INVALID_READ_PLAN", "family_account_ids must include the selected Account");
  }
  if (!Array.isArray(plan.requested_sections)
    || plan.requested_sections.length === 0
    || plan.requested_sections.some((section) => !PROFILE_SECTIONS.includes(section))
    || new Set(plan.requested_sections).size !== plan.requested_sections.length) {
    throw new SafetyError("INVALID_READ_PLAN", "requested_sections is invalid");
  }
  const canonicalSections = PROFILE_SECTIONS.filter((section) => plan.requested_sections.includes(section));
  if (canonicalSections.some((section, index) => section !== plan.requested_sections[index])) {
    throw new SafetyError("INVALID_READ_PLAN", "requested_sections must use canonical order");
  }
  if (!["selected_account", "corporate_family"].includes(plan.scope)) {
    throw new SafetyError("INVALID_READ_PLAN", "scope is invalid");
  }
  if (!OPPORTUNITY_SCOPES.includes(plan.opportunity_scope)) {
    throw new SafetyError("INVALID_READ_PLAN", "opportunity_scope is invalid");
  }
  validateFilters(plan.filters);
  if (plan.field_map_version !== FIELD_MAP_VERSION) {
    throw new SafetyError("INVALID_READ_PLAN", "field_map_version is unsupported");
  }
  if (!OUTPUT_TYPES.includes(plan.output_type)) throw new SafetyError("INVALID_READ_PLAN", "output_type is invalid");
  const issuedAt = validateInstant(plan.issued_at, "issued_at");
  const expiresAt = validateInstant(plan.expires_at, "expires_at");
  const lifetime = expiresAt.getTime() - issuedAt.getTime();
  if (lifetime <= 0 || lifetime > SESSION_TTL_MS) {
    throw new SafetyError("INVALID_READ_PLAN", "read plan lifetime must be positive and no more than 30 minutes");
  }
  validatePreset(plan);
  return plan;
}

export function buildReadPlan({
  sessionId,
  orgIdentity,
  runtimeAttestationDigest,
  accountSelector,
  selectedAccount = null,
  accountReceiptDigest = null,
  familyAccountIds = [],
  preset = "pipeline",
  sections,
  scope,
  opportunityScope,
  filters = {},
  outputType = "rendered",
  issuedAt = new Date(),
  expiresAt,
}) {
  const presetDefinition = PRESETS[preset];
  if (preset !== "custom" && !presetDefinition) {
    throw new SafetyError("INVALID_READ_PLAN", "preset is unsupported");
  }
  if (preset === "custom" && (!sections || !scope || !opportunityScope)) {
    throw new SafetyError("INVALID_READ_PLAN", "custom preset requires sections, scope, and opportunityScope");
  }
  const issued = issuedAt instanceof Date ? issuedAt : new Date(issuedAt);
  const expiry = expiresAt
    ? (expiresAt instanceof Date ? expiresAt : new Date(expiresAt))
    : new Date(issued.getTime() + SESSION_TTL_MS);
  const requestedSections = PROFILE_SECTIONS.filter((section) =>
    (sections ?? presetDefinition.sections).includes(section));
  const plan = {
    schema_version: CONTRACTS.readPlan,
    classification: CLASSIFICATION,
    session_id: sessionId,
    org_identity: { ...orgIdentity },
    runtime_attestation_digest: runtimeAttestationDigest,
    account_selector: { ...accountSelector },
    selected_account: selectedAccount ? { Id: selectedAccount.Id, Name: selectedAccount.Name } : null,
    account_receipt_digest: accountReceiptDigest,
    family_account_ids: [...familyAccountIds].sort(),
    preset,
    requested_sections: requestedSections,
    scope: scope ?? presetDefinition.scope,
    opportunity_scope: opportunityScope ?? presetDefinition.opportunity_scope,
    filters: {
      close_date_from: filters.close_date_from ?? null,
      close_date_to: filters.close_date_to ?? null,
      stages: [...(filters.stages ?? [])].sort((left, right) => left.localeCompare(right, "en-US")),
    },
    field_map_version: FIELD_MAP_VERSION,
    output_type: outputType,
    issued_at: issued.toISOString(),
    expires_at: expiry.toISOString(),
  };
  return validateReadPlan(plan);
}

export function readPlanDigest(plan) {
  return digest(validateReadPlan(plan));
}

function validateReceiptShape(receipt) {
  assertExactKeys(
    receipt,
    [
      "schema_version",
      "classification",
      "approval_kind",
      "session_id",
      "plan_digest",
      "approved_at",
      "expires_at",
      "receipt_digest",
    ],
    [
      "schema_version",
      "classification",
      "approval_kind",
      "session_id",
      "plan_digest",
      "approved_at",
      "expires_at",
      "receipt_digest",
    ],
    "approval_receipt",
  );
  if (receipt.schema_version !== CONTRACTS.approvalReceipt
    || receipt.classification !== CLASSIFICATION
    || !APPROVAL_KINDS.has(receipt.approval_kind)
    || !SESSION_ID.test(receipt.session_id)
    || !SHA256.test(receipt.plan_digest)
    || !SHA256.test(receipt.receipt_digest)) {
    throw new SafetyError("INVALID_APPROVAL_RECEIPT", "approval receipt metadata is invalid");
  }
  validateInstant(receipt.approved_at, "approval_receipt.approved_at");
  validateInstant(receipt.expires_at, "approval_receipt.expires_at");
}

export function issueApprovalReceipt(plan, approvalKind, approvedAt = new Date()) {
  validateReadPlan(plan);
  if (!APPROVAL_KINDS.has(approvalKind)) {
    throw new SafetyError("INVALID_APPROVAL_RECEIPT", "approval kind is unsupported");
  }
  const core = {
    schema_version: CONTRACTS.approvalReceipt,
    classification: CLASSIFICATION,
    approval_kind: approvalKind,
    session_id: plan.session_id,
    plan_digest: readPlanDigest(plan),
    approved_at: (approvedAt instanceof Date ? approvedAt : new Date(approvedAt)).toISOString(),
    expires_at: plan.expires_at,
  };
  const receipt = { ...core, receipt_digest: digest(core) };
  validateReceiptShape(receipt);
  return receipt;
}

export function validateApprovalReceipt(receipt, plan, approvalKind, now = new Date()) {
  validateReceiptShape(receipt);
  validateReadPlan(plan);
  const core = Object.fromEntries(
    Object.entries(receipt).filter(([key]) => key !== "receipt_digest"),
  );
  if (receipt.receipt_digest !== digest(core)
    || receipt.approval_kind !== approvalKind
    || receipt.session_id !== plan.session_id
    || receipt.plan_digest !== readPlanDigest(plan)
    || receipt.expires_at !== plan.expires_at) {
    throw new SafetyError("APPROVAL_RECEIPT_MISMATCH", "approval receipt does not bind the current read plan");
  }
  const approvedAt = new Date(receipt.approved_at);
  const expiry = new Date(receipt.expires_at);
  const current = now instanceof Date ? now : new Date(now);
  if (approvedAt < new Date(plan.issued_at) || approvedAt > current || approvedAt > expiry || current >= expiry) {
    throw new SafetyError("APPROVAL_RECEIPT_EXPIRED", "approval receipt is expired or outside the plan lifetime");
  }
  return receipt;
}

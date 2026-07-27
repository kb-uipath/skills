import {
  CONTRACTS,
  OPPORTUNITY_SCOPES,
  OUTPUT_TYPES,
  PRESETS,
  PROFILE_SECTIONS,
} from "./constants.mjs";
import {
  assertExactKeys,
  SafetyError,
  sanitizeText,
  validateAlias,
} from "./security.mjs";

const ACCOUNT_ID_18 = /^001[A-Za-z0-9]{15}$/u;
const SESSION_ID = /^[a-f0-9]{32}$/u;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/u;
const ENVIRONMENTS = Object.freeze([
  "production",
  "sandbox",
  "scratch",
]);
const DECISIONS = Object.freeze([
  "confirm_org_and_plan",
  "choose_account",
  "approve_family_scope",
  "narrow_query",
  "reauthenticate",
  "request_permissions",
  "cancel",
]);

function validateSchema(input, expected) {
  if (input.schema_version !== expected) {
    throw new SafetyError(
      "CONTRACT_VERSION_MISMATCH",
      `Expected schema_version ${expected}`,
    );
  }
}

function validateSafeString(value, label, maximum = 255, code = "INVALID_CONVERSATIONAL_REQUEST") {
  if (typeof value !== "string"
    || value.length < 1
    || value.length > maximum
    || sanitizeText(value) !== value) {
    throw new SafetyError(
      code,
      `${label} must be safe text between 1 and ${maximum} characters`,
    );
  }
  return value;
}

function validateSessionId(value) {
  if (typeof value !== "string" || !SESSION_ID.test(value)) {
    throw new SafetyError(
      "INVALID_SESSION_ID",
      "session_id must be a lowercase 32-character session identifier",
    );
  }
  return value;
}

function validateCalendarDate(value, label, code) {
  if (value === null) return null;
  if (typeof value !== "string" || !ISO_DATE.test(value)) {
    throw new SafetyError(code, `${label} must be null or YYYY-MM-DD`);
  }
  const parsed = new Date(`${value}T00:00:00.000Z`);
  if (!Number.isFinite(parsed.getTime())
    || parsed.toISOString().slice(0, 10) !== value) {
    throw new SafetyError(code, `${label} is not a real calendar date`);
  }
  return value;
}

function validateStages(stages, label, code, { allowEmpty = true } = {}) {
  if (!Array.isArray(stages)
    || stages.length > 50
    || (!allowEmpty && stages.length === 0)) {
    throw new SafetyError(
      code,
      `${label} must be an array of ${allowEmpty ? "at most" : "1 to"} 50 values`,
    );
  }
  for (const stage of stages) {
    validateSafeString(stage, `${label}[]`, 80, code);
  }
  if (new Set(stages).size !== stages.length) {
    throw new SafetyError(code, `${label} must contain unique values`);
  }
  const canonical = [...stages].sort((left, right) =>
    left.localeCompare(right, "en-US"));
  if (canonical.some((stage, index) => stage !== stages[index])) {
    throw new SafetyError(code, `${label} must use canonical order`);
  }
  return [...stages];
}

function validateFilters(
  filters,
  {
    label,
    code,
    requireAtLeastOne = false,
    allowEmptyStages = true,
  },
) {
  assertExactKeys(
    filters,
    ["close_date_from", "close_date_to", "stages"],
    [],
    label,
  );
  if (requireAtLeastOne && Object.keys(filters).length === 0) {
    throw new SafetyError(code, `${label} must include at least one narrowing filter`);
  }
  const closeDateFrom = validateCalendarDate(
    filters.close_date_from ?? null,
    `${label}.close_date_from`,
    code,
  );
  const closeDateTo = validateCalendarDate(
    filters.close_date_to ?? null,
    `${label}.close_date_to`,
    code,
  );
  if (closeDateFrom && closeDateTo && closeDateFrom > closeDateTo) {
    throw new SafetyError(
      code,
      `${label}.close_date_from must not be after close_date_to`,
    );
  }
  const stages = validateStages(
    filters.stages ?? [],
    `${label}.stages`,
    code,
    { allowEmpty: allowEmptyStages },
  );
  return {
    close_date_from: closeDateFrom,
    close_date_to: closeDateTo,
    stages,
  };
}

function validateAccountSelector(selector) {
  assertExactKeys(
    selector,
    ["mode", "value"],
    ["mode", "value"],
    "start_request.account_selector",
  );
  if (!["id", "exact_name"].includes(selector.mode)) {
    throw new SafetyError(
      "INVALID_START_REQUEST",
      "account_selector.mode must be id or exact_name; literal-prefix search is a separate decision",
    );
  }
  validateSafeString(
    selector.value,
    "account_selector.value",
    255,
    "INVALID_START_REQUEST",
  );
  if (selector.mode === "id" && !ACCOUNT_ID_18.test(selector.value)) {
    throw new SafetyError(
      "INVALID_START_REQUEST",
      "Account IDs must be 18-character Salesforce Account IDs",
    );
  }
  return { mode: selector.mode, value: selector.value };
}

function validateSections(sections) {
  if (!Array.isArray(sections)
    || sections.length === 0
    || sections.some((section) => !PROFILE_SECTIONS.includes(section))
    || new Set(sections).size !== sections.length) {
    throw new SafetyError(
      "INVALID_START_REQUEST",
      "sections must contain unique supported profile sections",
    );
  }
  const canonical = PROFILE_SECTIONS.filter((section) =>
    sections.includes(section));
  if (canonical.some((section, index) => section !== sections[index])) {
    throw new SafetyError(
      "INVALID_START_REQUEST",
      "sections must use canonical order",
    );
  }
  return [...sections];
}

export function validateDoctorRequest(input) {
  assertExactKeys(
    input,
    ["schema_version", "target_org", "friendly_label", "environment"],
    ["schema_version"],
    "doctor_request",
  );
  validateSchema(input, CONTRACTS.doctorRequest);
  const enrollmentKeys = ["target_org", "friendly_label", "environment"];
  const present = enrollmentKeys.filter((key) => key in input);
  if (present.length !== 0 && present.length !== enrollmentKeys.length) {
    throw new SafetyError(
      "INVALID_DOCTOR_REQUEST",
      "Enrollment requires target_org, friendly_label, and environment together",
    );
  }
  if (present.length) {
    validateAlias(input.target_org);
    validateSafeString(
      input.friendly_label,
      "friendly_label",
      80,
      "INVALID_DOCTOR_REQUEST",
    );
    if (!ENVIRONMENTS.includes(input.environment)) {
      throw new SafetyError(
        "INVALID_DOCTOR_REQUEST",
        "environment is unsupported",
      );
    }
  }
  return input;
}

export function validateStartRequest(input) {
  assertExactKeys(
    input,
    [
      "schema_version",
      "target_org",
      "account_selector",
      "preset",
      "sections",
      "scope",
      "opportunity_scope",
      "filters",
      "output_type",
    ],
    ["schema_version", "target_org", "account_selector"],
    "start_request",
  );
  validateSchema(input, CONTRACTS.startRequest);
  validateAlias(input.target_org);
  const accountSelector = validateAccountSelector(input.account_selector);
  const preset = input.preset ?? "pipeline";
  const definition = PRESETS[preset];
  if (preset !== "custom" && !definition) {
    throw new SafetyError("INVALID_START_REQUEST", "preset is unsupported");
  }

  let sections;
  let scope;
  let opportunityScope;
  if (preset === "custom") {
    for (const key of ["sections", "scope", "opportunity_scope"]) {
      if (!(key in input)) {
        throw new SafetyError(
          "INVALID_START_REQUEST",
          `custom preset requires ${key}`,
        );
      }
    }
    sections = validateSections(input.sections);
    scope = input.scope;
    opportunityScope = input.opportunity_scope;
  } else {
    if (["sections", "scope", "opportunity_scope"].some((key) => key in input)) {
      throw new SafetyError(
        "INVALID_START_REQUEST",
        "fixed presets do not accept sections, scope, or opportunity_scope overrides",
      );
    }
    sections = [...definition.sections];
    scope = definition.scope;
    opportunityScope = definition.opportunity_scope;
  }

  if (!["selected_account", "corporate_family"].includes(scope)) {
    throw new SafetyError("INVALID_START_REQUEST", "scope is unsupported");
  }
  if (!OPPORTUNITY_SCOPES.includes(opportunityScope)) {
    throw new SafetyError(
      "INVALID_START_REQUEST",
      "opportunity_scope is unsupported",
    );
  }
  const filters = validateFilters(
    input.filters ?? {},
    {
      label: "start_request.filters",
      code: "INVALID_START_REQUEST",
    },
  );
  const outputType = input.output_type ?? "rendered";
  if (!OUTPUT_TYPES.includes(outputType)) {
    throw new SafetyError("INVALID_START_REQUEST", "output_type is unsupported");
  }

  return {
    schema_version: CONTRACTS.startRequest,
    target_org: input.target_org,
    account_selector: accountSelector,
    preset,
    sections,
    scope,
    opportunity_scope: opportunityScope,
    filters,
    output_type: outputType,
  };
}

function validateChooseAccountDecision(decision) {
  assertExactKeys(
    decision,
    ["action", "account_id", "literal_prefix"],
    ["action"],
    "continue_request.decision",
  );
  const hasAccountId = "account_id" in decision;
  const hasLiteralPrefix = "literal_prefix" in decision;
  if (hasAccountId === hasLiteralPrefix) {
    throw new SafetyError(
      "INVALID_CONTINUE_REQUEST",
      "choose_account requires exactly one of account_id or literal_prefix",
    );
  }
  if (hasAccountId
    && (typeof decision.account_id !== "string"
      || !ACCOUNT_ID_18.test(decision.account_id))) {
    throw new SafetyError(
      "INVALID_CONTINUE_REQUEST",
      "account_id must be an 18-character Salesforce Account ID",
    );
  }
  if (hasLiteralPrefix) {
    validateSafeString(
      decision.literal_prefix,
      "decision.literal_prefix",
      255,
      "INVALID_CONTINUE_REQUEST",
    );
  }
  return hasAccountId
    ? { action: decision.action, account_id: decision.account_id }
    : { action: decision.action, literal_prefix: decision.literal_prefix };
}

function validateNarrowDecision(decision) {
  assertExactKeys(
    decision,
    [
      "action",
      "scope",
      "opportunity_scope",
      "filters",
      "account_selector",
      "remove_sections",
    ],
    ["action"],
    "continue_request.decision",
  );
  const hasScope = "scope" in decision;
  const hasOpportunityScope = "opportunity_scope" in decision;
  const hasFilters = "filters" in decision;
  const hasAccountSelector = "account_selector" in decision;
  const hasRemoveSections = "remove_sections" in decision;
  if (!hasScope
    && !hasOpportunityScope
    && !hasFilters
    && !hasAccountSelector
    && !hasRemoveSections) {
    throw new SafetyError(
      "INVALID_CONTINUE_REQUEST",
      "narrow_query requires an Account selector, scope, Opportunity scope, filters, or removable sections",
    );
  }
  if (hasScope && decision.scope !== "selected_account") {
    throw new SafetyError(
      "INVALID_CONTINUE_REQUEST",
      "narrow_query.scope must be selected_account",
    );
  }
  if (hasOpportunityScope
    && !OPPORTUNITY_SCOPES.includes(decision.opportunity_scope)) {
    throw new SafetyError(
      "INVALID_CONTINUE_REQUEST",
      "narrow_query.opportunity_scope is unsupported",
    );
  }
  const result = { action: decision.action };
  if (hasScope) result.scope = decision.scope;
  if (hasOpportunityScope) {
    result.opportunity_scope = decision.opportunity_scope;
  }
  if (hasAccountSelector) {
    result.account_selector = validateAccountSelector(
      decision.account_selector,
    );
  }
  if (hasRemoveSections) {
    const removable = PROFILE_SECTIONS.filter((section) =>
      section !== "overview");
    if (!Array.isArray(decision.remove_sections)
      || decision.remove_sections.length === 0
      || decision.remove_sections.some((section) =>
        !removable.includes(section))
      || new Set(decision.remove_sections).size
        !== decision.remove_sections.length) {
      throw new SafetyError(
        "INVALID_CONTINUE_REQUEST",
        "remove_sections must contain unique removable profile sections",
      );
    }
    const canonical = removable.filter((section) =>
      decision.remove_sections.includes(section));
    if (canonical.some((section, index) =>
      section !== decision.remove_sections[index])) {
      throw new SafetyError(
        "INVALID_CONTINUE_REQUEST",
        "remove_sections must use canonical order",
      );
    }
    result.remove_sections = canonical;
  }
  if (hasFilters) {
    const normalized = validateFilters(
      decision.filters,
      {
        label: "continue_request.decision.filters",
        code: "INVALID_CONTINUE_REQUEST",
        requireAtLeastOne: true,
      },
    );
    const filters = {};
    for (const key of [
      "close_date_from",
      "close_date_to",
      "stages",
    ]) {
      if (key in decision.filters) filters[key] = normalized[key];
    }
    if (("close_date_from" in filters
        && filters.close_date_from === null)
      || ("close_date_to" in filters
        && filters.close_date_to === null)
      || ("stages" in filters && filters.stages.length === 0)) {
      throw new SafetyError(
        "INVALID_CONTINUE_REQUEST",
        "narrow_query filters may only add a date boundary or nonempty stage set",
      );
    }
    result.filters = filters;
  }
  return result;
}

export function validateContinueRequest(input) {
  assertExactKeys(
    input,
    ["schema_version", "session_id", "decision"],
    ["schema_version", "session_id", "decision"],
    "continue_request",
  );
  validateSchema(input, CONTRACTS.continueRequest);
  validateSessionId(input.session_id);
  if (!input.decision
    || typeof input.decision !== "object"
    || Array.isArray(input.decision)
    || !DECISIONS.includes(input.decision.action)) {
    throw new SafetyError(
      "INVALID_CONTINUE_REQUEST",
      "decision.action is unsupported",
    );
  }

  let decision;
  if (input.decision.action === "choose_account") {
    decision = validateChooseAccountDecision(input.decision);
  } else if (input.decision.action === "narrow_query") {
    decision = validateNarrowDecision(input.decision);
  } else {
    assertExactKeys(
      input.decision,
      ["action"],
      ["action"],
      "continue_request.decision",
    );
    decision = { action: input.decision.action };
  }
  return {
    schema_version: CONTRACTS.continueRequest,
    session_id: input.session_id,
    decision,
  };
}

function validateSessionRequest(input, schemaVersion, label) {
  assertExactKeys(
    input,
    ["schema_version", "session_id"],
    ["schema_version", "session_id"],
    label,
  );
  validateSchema(input, schemaVersion);
  validateSessionId(input.session_id);
  return input;
}

export function validateStatusRequest(input) {
  assertExactKeys(
    input,
    ["schema_version", "session_id"],
    ["schema_version"],
    "status_request",
  );
  validateSchema(input, CONTRACTS.statusRequest);
  if ("session_id" in input) validateSessionId(input.session_id);
  return input;
}

export function validateAbortRequest(input) {
  return validateSessionRequest(
    input,
    CONTRACTS.abortRequest,
    "abort_request",
  );
}

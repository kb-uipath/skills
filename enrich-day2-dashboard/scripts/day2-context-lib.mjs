import { createHash, randomBytes } from "node:crypto";
import { access, chmod, link, lstat, mkdir, readFile, realpath, rename, stat, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

export const DASHBOARD_SCHEMA_VERSION = "1.4";
export const POLICY_VERSION = "day2-evidence-policy/v2";
export const LEDGER_KIND = "day2-evidence-ledger";
export const LEDGER_VERSION = "2";
export const PREVIEW_KIND = "day2-context-preview/v2";
export const REPORT_KIND = "day2-evidence-report/v2";
export const QUESTION_PLAN_KIND = "day2-question-plan/v1";
export const CLARIFICATION_ANSWERS_KIND = "day2-clarification-answers/v1";
export const ATTESTATION_KIND = "day2-account-team-attestations/v1";
export const SALESFORCE_FIELD_MAP_VERSION = "salesforce-day2-field-map/v1";
export const SALESFORCE_REPORT_KIND = "salesforce-day2-mapping-report/v1";

export const SCRIPT_DIRECTORY = path.dirname(fileURLToPath(import.meta.url));
export const SKILL_DIRECTORY = path.dirname(SCRIPT_DIRECTORY);
export const SALESFORCE_SKILL_DIRECTORY = path.join(SKILL_DIRECTORY, "salesforce-layer");
export const SALESFORCE_LIBRARY_PATH = path.join(
  SALESFORCE_SKILL_DIRECTORY,
  "scripts",
  "day2-enricher-lib.mjs",
);

const ACCOUNT_ID_PATTERN = /^001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/;
const SHA256_PATTERN = /^sha256:[a-f0-9]{64}$/;
const ISO_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;
const ISO_DATE_TIME_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|([+-])(\d{2}):(\d{2}))$/;
const DANGEROUS_SEGMENTS = new Set(["__proto__", "prototype", "constructor"]);
const SOURCE_TYPES = new Set([
  "salesforce",
  "sharepoint",
  "onedrive",
  "outlook-email",
  "outlook-attachment",
  "slack-public",
  "slack-private",
  "slack-dm",
  "teams",
  "outlook-calendar",
  "local-file",
  "telemetry",
  "onenote",
  "public-web",
]);
const PRIVATE_SLACK_TYPES = new Set(["slack-private", "slack-dm"]);
const FILE_SOURCE_TYPES = new Set(["sharepoint", "onedrive", "outlook-attachment", "local-file", "telemetry"]);
const AUTHOR_KINDS = new Set(["customer", "uipath", "system", "public", "unknown"]);
const CLAIM_CLASSES = new Set(["actual", "target", "plan", "risk", "opinion", "meeting-scheduled"]);
const PROPOSAL_CLAIM_CLASSES = new Set([...CLAIM_CLASSES, "mixed"]);
const AUTHORITIES = new Set([
  "salesforce-exact",
  "contract-order",
  "license-record",
  "product-telemetry",
  "validated-account-document",
  "customer-statement",
  "internal-operations",
  "calendar-event",
  "personal-note",
  "public-web",
  "account-team-attestation",
]);
const SOURCE_AUTHORITIES = new Map([
  ["salesforce", new Set(["salesforce-exact"])],
  ["sharepoint", new Set(["contract-order", "license-record", "validated-account-document"])],
  ["onedrive", new Set(["contract-order", "license-record", "validated-account-document"])],
  ["outlook-email", new Set(["customer-statement", "internal-operations"])],
  ["outlook-attachment", new Set(["contract-order", "license-record", "validated-account-document"])],
  ["slack-public", new Set(["customer-statement", "internal-operations"])],
  ["slack-private", new Set(["customer-statement", "internal-operations"])],
  ["slack-dm", new Set(["customer-statement", "internal-operations"])],
  ["teams", new Set(["customer-statement", "internal-operations"])],
  ["outlook-calendar", new Set(["calendar-event"])],
  ["local-file", new Set(["contract-order", "license-record", "validated-account-document"])],
  ["telemetry", new Set(["product-telemetry"])],
  ["onenote", new Set(["personal-note"])],
  ["public-web", new Set(["public-web"])],
]);
const DATED_AUTHORITIES = new Set([
  "contract-order",
  "license-record",
  "product-telemetry",
  "validated-account-document",
  "customer-statement",
  "internal-operations",
  "calendar-event",
  "public-web",
]);
const MAX_SOURCE_CLOCK_SKEW_MS = 5 * 60 * 1_000;
const ACCOUNT_SIGNALS = new Set([
  "canonical-name",
  "alias",
  "domain",
  "contact",
  "container",
  "explicit-link",
]);
const HEALTH_KEYS = new Set([
  "overall",
  "agenticReadiness",
  "execSponsors",
  "effectiveAom",
  "lobEngagement",
  "valueRealization",
  "pipelineQuality",
  "resourcingModel",
  "customerAdvocacy",
]);
const METRIC_KEYS = new Set(["savings", "automations", "agentic", "pipeline"]);
const UTILIZATION_KEYS = new Set(["users", "robots", "consumables"]);
const TOP_LEVEL_CONTEXT_FIELDS = new Set([
  "tagline",
  "motion",
  "currentArr",
  "renewalDate",
  "deploymentType",
  "deliveryModel",
  "soldProducts",
  "useCases",
  "statusSummary",
]);
const INSERT_TARGETS = new Set([
  "/goals",
  "/cadenceGoals",
  "/workstreams",
  "/consumptionPlan/groups",
  "/relationships",
  "/eltAsks",
  "/timeline",
]);
const PRODUCT_FORECAST_TARGET = "/consumptionPlan/productForecast";
const ANSWER_STATUSES = new Set(["answered", "unknown", "skipped"]);
const ATTESTATION_CLAIM_CLASSES = new Set(["actual", "target", "plan", "risk", "opinion"]);
const ATTESTATION_INTERNAL_ACTUAL_PATHS = [
  /^\/metrics\/pipeline\/(?:value|note)$/u,
  /^\/workstreams$/u,
  /^\/statusSummary$/u,
];
const PROTECTED_ATTESTATION_PATHS = [
  /^\/currentArr$/u,
  /^\/renewalDate$/u,
  /^\/soldProducts$/u,
  /^\/deploymentType$/u,
  /^\/deliveryModel$/u,
  /^\/useCases$/u,
  /^\/metrics\/(?:savings|automations|agentic)\/value$/u,
  /^\/metrics\/utilization\//u,
  /^\/executiveCadence\/(?:type|date)$/u,
  /^\/consumptionPlan\/(?:asOf|groups)$/u,
];
const ATTESTATION_ALLOWED_PATHS = [
  /^\/motion$/u,
  /^\/goals$/u,
  /^\/cadenceGoals$/u,
  /^\/workstreams$/u,
  /^\/eltAsks$/u,
  /^\/relationships$/u,
  /^\/motionAnswers$/u,
  /^\/metrics\/pipeline\/(?:value|note)$/u,
  /^\/health\/[^/]+\/(?:status|evidence|mitigation|owner)$/u,
  /^\/statusSummary$/u,
  /^\/timeline$/u,
  /^\/consumptionPlan\/productForecast$/u,
];
const PAGE_ONE_VISIBLE_LIMITS = new Map([
  ["/goals", 3],
  ["/workstreams", 3],
  ["/eltAsks", 2],
  ["/relationships", 7],
]);
const PAGE_ONE_SCALAR_PATHS = new Set([
  "/tagline",
  "/motion",
  "/currentArr",
  "/renewalDate",
  "/deploymentType",
  "/deliveryModel",
  "/useCases",
  "/statusSummary",
  "/executiveCadence/type",
  "/executiveCadence/date",
  "/consumptionPlan/asOf",
]);
const PROMPT_INJECTION_PATTERNS = [
  /ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions/i,
  /\b(system|assistant|developer)\s+message\b/i,
  /\bexecute\s+(?:this\s+)?(?:command|script|tool)\b/i,
  /\bapprove(?:\s+all)?\s+proposal/i,
  /\bfollow\s+this\s+link\s+and\b/i,
  /<script\b/i,
  /```(?:system|assistant|developer)/i,
];

export const FIELD_POLICY_MAP = Object.freeze({
  protectedCommercial: {
    phase: "source-location",
    priority: 10,
    intent: "Authoritative commercial identity and timing",
    pageOneVisible: true,
    characterLimit: null,
    evidenceThreshold: "contract, order, license, or Salesforce exact fact",
    attestationEligible: false,
    dependencies: [],
    targetPaths: ["/currentArr", "/renewalDate", "/soldProducts"],
    questionTemplate: "Where is the current ARR, renewal, or purchased-product record? Share an exact file, record, or link; say unknown if none is available.",
  },
  protectedDelivery: {
    phase: "source-location",
    priority: 11,
    intent: "Actual deployment and delivery model",
    pageOneVisible: true,
    characterLimit: null,
    evidenceThreshold: "dated system or validated account record",
    attestationEligible: false,
    dependencies: [],
    targetPaths: ["/deploymentType", "/deliveryModel"],
    questionTemplate: "Where is the deployment type or delivery model explicitly recorded? Share the exact source location; do not answer from memory.",
  },
  protectedUsageValue: {
    phase: "source-location",
    priority: 12,
    intent: "Actual usage, production scale, value, and Where Used",
    pageOneVisible: true,
    characterLimit: 120,
    evidenceThreshold: "telemetry or dated validated outcome/use-case record",
    attestationEligible: false,
    dependencies: [],
    targetPaths: ["/tagline", "/useCases", "/metrics/savings/value", "/metrics/automations/value", "/metrics/agentic/value", "/metrics/utilization"],
    questionTemplate: "Where can I verify actual usage, production counts, realized value, or Where Used? Share telemetry or a dated validated source; otherwise say unknown.",
  },
  protectedCadence: {
    phase: "source-location",
    priority: 13,
    intent: "Occurred executive cadence",
    pageOneVisible: true,
    characterLimit: null,
    evidenceThreshold: "Salesforce exact date, calendar occurrence, or dated validated source",
    attestationEligible: false,
    dependencies: [],
    targetPaths: ["/executiveCadence/type", "/executiveCadence/date"],
    questionTemplate: "Where is the latest occurred QBR or EBC recorded? Share the Salesforce, calendar, or dated source location; otherwise say unknown.",
  },
  motion: {
    phase: "executive",
    priority: 20,
    intent: "Choose the account motion and explain why it fits",
    pageOneVisible: true,
    characterLimit: 500,
    evidenceThreshold: "account-team judgment",
    attestationEligible: true,
    dependencies: [],
    targetPaths: ["/motion"],
    questionTemplate: "Which motion fits now—Re-Recruit, Consumption, or Hybrid—and what account facts drive that judgment?",
  },
  strategy: {
    phase: "executive",
    priority: 21,
    intent: "Measurable Day 2 customer outcome",
    pageOneVisible: true,
    characterLimit: 600,
    evidenceThreshold: "account-team plan or target",
    attestationEligible: true,
    dependencies: [],
    targetPaths: ["/goals"],
    questionTemplate: "What measurable customer outcome should Page 1 target, by when, and who owns it?",
  },
  workstreams: {
    phase: "executive",
    priority: 22,
    intent: "Top execution workstream",
    pageOneVisible: true,
    characterLimit: 1200,
    evidenceThreshold: "account-team plan, risk, or internal actual",
    attestationEligible: true,
    dependencies: [],
    targetPaths: ["/workstreams"],
    questionTemplate: "What is the top workstream? Give its owner, risk, up to four milestones, and the intended outcome.",
  },
  eltAsks: {
    phase: "executive",
    priority: 23,
    intent: "Specific leadership decision or help",
    pageOneVisible: true,
    characterLimit: 600,
    evidenceThreshold: "account-team plan or risk",
    attestationEligible: true,
    dependencies: [],
    targetPaths: ["/eltAsks"],
    questionTemplate: "What specific decision or help is needed from ELT, who owns the ask, and by when?",
  },
  statusInputs: {
    phase: "executive",
    priority: 24,
    intent: "Progress, risk or decision, and next action for the generated four-line status",
    pageOneVisible: true,
    characterLimit: 1000,
    evidenceThreshold: "external evidence for value; account-team authority for the other three lines",
    attestationEligible: true,
    dependencies: ["protectedUsageValue"],
    targetPaths: ["/statusSummary"],
    questionTemplate: "For the generated status, what progress has occurred, what risk or decision matters now, and what is the next action with owner and timing? Do not restate value.",
  },
  health: {
    phase: "supporting",
    priority: 30,
    intent: "Explicit health judgment with basis and accountability",
    pageOneVisible: true,
    characterLimit: 1600,
    evidenceThreshold: "account-team judgment with stated basis",
    attestationEligible: true,
    dependencies: [],
    targetPaths: ["/health"],
    questionTemplate: "Which unresolved health indicators are Red or Green? For each, state the basis; for Red also give mitigation and owner.",
  },
  relationships: {
    phase: "supporting",
    priority: 31,
    intent: "Named relationship and next relationship action",
    pageOneVisible: true,
    characterLimit: 1000,
    evidenceThreshold: "account-team plan or judgment",
    attestationEligible: true,
    dependencies: [],
    targetPaths: ["/relationships"],
    questionTemplate: "Which missing executive relationship matters most? Give the UiPath person, customer person and roles, relationship state, and next action.",
  },
  motionAnswers: {
    phase: "supporting",
    priority: 32,
    intent: "Motion-specific plan, risk, owner, or explicit gap",
    pageOneVisible: false,
    characterLimit: 1000,
    evidenceThreshold: "account-team plan, risk, ownership, or gap",
    attestationEligible: true,
    dependencies: ["motion"],
    targetPaths: ["/motionAnswers"],
    questionTemplate: "What is the clearest plan, risk, owner, or explicit gap for the unanswered questions tied to the selected motion?",
  },
  pipeline: {
    phase: "supporting",
    priority: 33,
    intent: "Internal pipeline status",
    pageOneVisible: true,
    characterLimit: 500,
    evidenceThreshold: "account-team internal status",
    attestationEligible: true,
    dependencies: [],
    targetPaths: ["/metrics/pipeline/value", "/metrics/pipeline/note"],
    questionTemplate: "What is the current internal pipeline status or idea count, what does it represent, and who owns the next qualification step?",
  },
  supportingPlans: {
    phase: "supporting",
    priority: 34,
    intent: "Optional cadence goals and planned timeline milestones",
    pageOneVisible: false,
    characterLimit: 1200,
    evidenceThreshold: "account-team plan, target, risk, or owner",
    attestationEligible: true,
    dependencies: [],
    targetPaths: ["/cadenceGoals", "/timeline"],
    questionTemplate: "What optional cadence goal or future milestone should be recorded? Give the target or date, owner, status, and intended outcome.",
  },
  optionalPass: {
    phase: "optional-gate",
    priority: 40,
    intent: "User choice to continue into optional supporting detail",
    pageOneVisible: false,
    characterLimit: 20,
    evidenceThreshold: "user choice",
    attestationEligible: false,
    dependencies: [],
    targetPaths: [],
    questionTemplate: "The executive pass is complete. Do you want the optional supporting-detail pass? Answer yes or no.",
  },
  productForecast: {
    phase: "optional",
    priority: 41,
    intent: "Quarterly forecast plan for a source-backed product row",
    pageOneVisible: false,
    characterLimit: 1200,
    evidenceThreshold: "account-team forecast plan plus an existing source-backed product row",
    attestationEligible: true,
    dependencies: ["optionalPass"],
    targetPaths: [PRODUCT_FORECAST_TARGET],
    questionTemplate: "For a source-backed Consumption Plan product, what are the Q1–Q4 forecast values and planning comment? Name the exact license category and product.",
  },
});

let salesforceLibraryPromise;

export class ContextEnricherError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "ContextEnricherError";
    this.code = code;
  }
}

function getSalesforceLibrary() {
  if (!salesforceLibraryPromise) {
    salesforceLibraryPromise = import(pathToFileURL(SALESFORCE_LIBRARY_PATH).href).catch((error) => {
      throw new ContextEnricherError(
        "MISSING_SALESFORCE_LAYER",
        `The bundled deterministic Salesforce layer is required at ${SALESFORCE_SKILL_DIRECTORY}: ${error.message}`,
      );
    });
  }
  return salesforceLibraryPromise;
}

export function stableStringify(value) {
  return JSON.stringify(sortValue(value)) ?? "undefined";
}

function sortValue(value) {
  if (Array.isArray(value)) return value.map(sortValue);
  if (!isPlainObject(value)) return value;
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, sortValue(value[key])]));
}

export function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

export function digestObject(value) {
  return `sha256:${sha256(stableStringify(value))}`;
}

export function deepClone(value) {
  return structuredClone(value);
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function hasText(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function codePointLength(value) {
  return Array.from(String(value ?? "")).length;
}

function lines(value) {
  return String(value ?? "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function assertPlainObject(value, target) {
  if (!isPlainObject(value)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target} must be an object.`);
  }
}

function assertExactKeys(value, requiredKeys, target) {
  assertPlainObject(value, target);
  const required = [...requiredKeys].sort();
  const actual = Object.keys(value).sort();
  if (stableStringify(required) !== stableStringify(actual)) {
    const missing = required.filter((key) => !actual.includes(key));
    const extra = actual.filter((key) => !required.includes(key));
    throw new ContextEnricherError(
      "INVALID_LEDGER",
      `${target} has noncanonical keys. Missing: ${missing.join(", ") || "none"}. Extra: ${extra.join(", ") || "none"}.`,
    );
  }
}

function requireString(value, target, { allowBlank = false, max = 20_000 } = {}) {
  if (typeof value !== "string") {
    throw new ContextEnricherError("INVALID_LEDGER", `${target} must be a string.`);
  }
  if (!allowBlank && !value.trim()) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target} must not be blank.`);
  }
  if (codePointLength(value) > max) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target} exceeds ${max} characters.`);
  }
  if (value.includes("\0")) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target} contains a NUL character.`);
  }
  return value;
}

function requireBoolean(value, target) {
  if (typeof value !== "boolean") {
    throw new ContextEnricherError("INVALID_LEDGER", `${target} must be a boolean.`);
  }
  return value;
}

function requireStringArray(value, target, { allowed, allowBlank = false } = {}) {
  if (!Array.isArray(value)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target} must be an array.`);
  }
  const normalized = value.map((item, index) => {
    const text = requireString(item, `${target}[${index}]`, { allowBlank });
    if (allowed && !allowed.has(text)) {
      throw new ContextEnricherError("INVALID_LEDGER", `${target}[${index}] has unsupported value ${JSON.stringify(text)}.`);
    }
    return text;
  });
  if (new Set(normalized).size !== normalized.length) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target} contains duplicate values.`);
  }
  return normalized;
}

function isRealIsoDate(value) {
  const match = ISO_DATE_PATTERN.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (month < 1 || month > 12 || day < 1) return false;
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day <= daysInMonth[month - 1];
}

function isRealIsoDateTime(value) {
  const match = ISO_DATE_TIME_PATTERN.exec(value);
  if (!match || !isRealIsoDate(`${match[1]}-${match[2]}-${match[3]}`)) return false;
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  if (hour > 23 || minute > 59 || second > 59) return false;
  if (match[8] !== "Z") {
    const offsetHour = Number(match[10]);
    const offsetMinute = Number(match[11]);
    if (offsetHour > 14 || offsetMinute > 59 || (offsetHour === 14 && offsetMinute !== 0)) return false;
  }
  return !Number.isNaN(Date.parse(value));
}

function requireIsoDate(value, target) {
  requireString(value, target);
  if (!isRealIsoDate(value)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target} must be an ISO date-only value.`);
  }
  return value;
}

function requireDateLike(value, target, { allowBlank = true } = {}) {
  requireString(value, target, { allowBlank });
  if (value === "" && allowBlank) return value;
  if (!isRealIsoDate(value) && !isRealIsoDateTime(value)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target} is not a real date.`);
  }
  return value;
}

function requireIsoDateTime(value, target, { allowBlank = false } = {}) {
  requireString(value, target, { allowBlank });
  if (value === "" && allowBlank) return value;
  if (!isRealIsoDateTime(value)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target} must be an ISO date-time with a timezone.`);
  }
  return value;
}

function assertNotFuture(value, target, now = Date.now(), allowedSkewMs = 0) {
  if (value && Date.parse(value) > now + allowedSkewMs) {
    throw new ContextEnricherError(
      "FUTURE_TIMESTAMP",
      `${target} cannot be in the future.`,
    );
  }
}

function dateOnly(value) {
  return hasText(value) ? value.slice(0, 10) : "";
}

function evidenceScopeDate(sourceType, occurredAt, modifiedAt) {
  if (sourceType === "outlook-calendar") return dateOnly(occurredAt);
  return dateOnly(modifiedAt) || dateOnly(occurredAt);
}

function normalizeContact(value, index) {
  const target = `ledger.account.contacts[${index}]`;
  assertExactKeys(value, ["name", "email"], target);
  const name = requireString(value.name, `${target}.name`, { allowBlank: true, max: 300 });
  const email = requireString(value.email, `${target}.email`, { allowBlank: true, max: 320 });
  if (!name && !email) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target} needs a name or email.`);
  }
  return { name, email };
}

function normalizeAuthor(value, target) {
  assertExactKeys(value, ["name", "kind"], target);
  const name = requireString(value.name, `${target}.name`, { allowBlank: true, max: 300 });
  const kind = requireString(value.kind, `${target}.kind`);
  if (!AUTHOR_KINDS.has(kind)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.kind is unsupported.`);
  }
  return { name, kind };
}

function normalizeAccountMatch(value, target) {
  assertExactKeys(value, ["signals", "rationale"], target);
  const signals = requireStringArray(value.signals, `${target}.signals`, { allowed: ACCOUNT_SIGNALS });
  const rationale = requireString(value.rationale, `${target}.rationale`, { max: 800 });
  return { signals, rationale };
}

function accountMatchIsStrong(accountMatch) {
  const signals = new Set(accountMatch.signals);
  if (signals.has("canonical-name") || signals.has("explicit-link")) return true;
  if (signals.size < 2) return false;
  return [...signals].some((signal) => ["domain", "contact", "container"].includes(signal));
}

function containsPromptInjection(text) {
  return PROMPT_INJECTION_PATTERNS.some((pattern) => pattern.test(String(text ?? "")));
}

function sanitizeLocator(value, target) {
  const locator = requireString(value, target, { allowBlank: true, max: 4_000 });
  if (!locator) return "";
  try {
    const parsed = new URL(locator);
    parsed.username = "";
    parsed.password = "";
    parsed.search = "";
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return locator;
  }
}

function normalizeEvidenceItem(value, index, scope) {
  const target = `ledger.items[${index}]`;
  assertExactKeys(value, [
    "ref",
    "sourceType",
    "tenantId",
    "visibility",
    "sourceId",
    "sourceUrl",
    "container",
    "title",
    "author",
    "occurredAt",
    "modifiedAt",
    "retrievedAt",
    "verifiedAt",
    "freshnessMode",
    "contentDigest",
    "excerpt",
    "accountMatch",
    "claimClass",
    "authority",
    "limitations",
  ], target);

  const ref = requireString(value.ref, `${target}.ref`, { max: 200 });
  const sourceType = requireString(value.sourceType, `${target}.sourceType`);
  if (!SOURCE_TYPES.has(sourceType)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.sourceType is unsupported.`);
  }
  if (!scope.sources.includes(sourceType)) {
    throw new ContextEnricherError(
      "SOURCE_OUT_OF_SCOPE",
      `${target}.sourceType ${sourceType} is not included in ledger.scope.sources.`,
    );
  }
  const discovery = scope.discoveryRuns.find((run) => run.sourceType === sourceType);
  if (!discovery) {
    throw new ContextEnricherError("DISCOVERY_RECORD_REQUIRED", `${target} has no matching discovery run.`);
  }
  const tenantId = requireString(value.tenantId, `${target}.tenantId`, { max: 1_000 });
  if (tenantId !== discovery.tenantId) {
    throw new ContextEnricherError(
      "SOURCE_SCOPE_MISMATCH",
      `${target}.tenantId does not match its bounded discovery run.`,
    );
  }
  const visibility = requireString(value.visibility, `${target}.visibility`);
  if (!["public", "private", "dm", "internal", "external", "local", "unknown"].includes(visibility)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.visibility is unsupported.`);
  }
  if (sourceType === "slack-public" && visibility !== "public") {
    throw new ContextEnricherError("INVALID_LEDGER", `${target} must record public Slack visibility.`);
  }
  if (sourceType === "slack-private" && visibility !== "private") {
    throw new ContextEnricherError("INVALID_LEDGER", `${target} must record private Slack visibility.`);
  }
  if (sourceType === "slack-dm" && visibility !== "dm") {
    throw new ContextEnricherError("INVALID_LEDGER", `${target} must record DM Slack visibility.`);
  }
  const sourceId = requireString(value.sourceId, `${target}.sourceId`, { max: 2_000 });
  const sourceUrl = sanitizeLocator(value.sourceUrl, `${target}.sourceUrl`);
  const container = requireString(value.container, `${target}.container`, { allowBlank: true, max: 1_000 });
  if (
    (container && !discovery.containerIds.includes(container)) ||
    (!container && discovery.containerIds.length)
  ) {
    throw new ContextEnricherError(
      "SOURCE_SCOPE_MISMATCH",
      `${target}.container does not match the exact containers searched by its discovery run.`,
    );
  }
  if (PRIVATE_SLACK_TYPES.has(sourceType)) {
    if (!scope.privateSlackConsent) {
      throw new ContextEnricherError("PRIVATE_SLACK_CONSENT_REQUIRED", `${target} uses private Slack evidence without consent.`);
    }
    if (
      !container ||
      !scope.privateSlackScopes.includes(container) ||
      !discovery?.containerIds.includes(container)
    ) {
      throw new ContextEnricherError(
        "PRIVATE_SLACK_SCOPE_REQUIRED",
        `${target}.container must exactly match a consented private Slack container included in its bounded discovery run.`,
      );
    }
  }
  const title = requireString(value.title, `${target}.title`, { allowBlank: true, max: 1_000 });
  const author = normalizeAuthor(value.author, `${target}.author`);
  const occurredAt = requireDateLike(value.occurredAt, `${target}.occurredAt`);
  const modifiedAt = requireDateLike(value.modifiedAt, `${target}.modifiedAt`);
  const retrievedAt = requireIsoDateTime(value.retrievedAt, `${target}.retrievedAt`);
  const verifiedAt = requireIsoDateTime(value.verifiedAt, `${target}.verifiedAt`, { allowBlank: true });
  const freshnessMode = requireString(value.freshnessMode, `${target}.freshnessMode`);
  if (!["stable-id", "snapshot"].includes(freshnessMode)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.freshnessMode is unsupported.`);
  }
  if (sourceType === "onenote" && freshnessMode !== "snapshot") {
    throw new ContextEnricherError("INVALID_LEDGER", `${target} must use snapshot freshness for OneNote.`);
  }
  if (sourceType !== "onenote" && freshnessMode === "snapshot" && sourceType !== "local-file") {
    throw new ContextEnricherError(
      "INVALID_LEDGER",
      `${target} may use snapshot freshness only for OneNote or a local file.`,
    );
  }
  const contentDigest = requireString(value.contentDigest, `${target}.contentDigest`);
  if (!SHA256_PATTERN.test(contentDigest)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.contentDigest must be a lowercase SHA-256 digest.`);
  }
  if (sourceType === "onenote") {
    const selected = scope.oneNoteSelections.find((item) => item.sourceId === sourceId);
    if (!selected || selected.captureDigest !== contentDigest) {
      throw new ContextEnricherError(
        "ONENOTE_SELECTION_REQUIRED",
        `${target} does not match a selected OneNote page and capture digest.`,
      );
    }
  }
  const excerpt = requireString(value.excerpt, `${target}.excerpt`, { allowBlank: true, max: 1_200 });
  const accountMatch = normalizeAccountMatch(value.accountMatch, `${target}.accountMatch`);
  const claimClass = requireString(value.claimClass, `${target}.claimClass`);
  if (!CLAIM_CLASSES.has(claimClass)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.claimClass is unsupported.`);
  }
  const authority = requireString(value.authority, `${target}.authority`);
  if (!AUTHORITIES.has(authority)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.authority is unsupported.`);
  }
  if (!SOURCE_AUTHORITIES.get(sourceType)?.has(authority)) {
    throw new ContextEnricherError(
      "SOURCE_AUTHORITY_MISMATCH",
      `${target}.authority ${authority} is not permitted for sourceType ${sourceType}.`,
    );
  }
  if (authority === "customer-statement" && author.kind !== "customer") {
    throw new ContextEnricherError(
      "SOURCE_AUTHORITY_MISMATCH",
      `${target} customer-statement authority requires connector-envelope customer authorship.`,
    );
  }
  if (authority === "internal-operations" && !["uipath", "system"].includes(author.kind)) {
    throw new ContextEnricherError(
      "SOURCE_AUTHORITY_MISMATCH",
      `${target} internal-operations authority requires UiPath or system authorship.`,
    );
  }
  if (authority === "public-web" && author.kind !== "public") {
    throw new ContextEnricherError(
      "SOURCE_AUTHORITY_MISMATCH",
      `${target} public-web authority requires public authorship.`,
    );
  }
  const limitations = requireStringArray(value.limitations, `${target}.limitations`, { allowBlank: false });
  const scopeDate = evidenceScopeDate(sourceType, occurredAt, modifiedAt);
  const outsideWindow = Boolean(scopeDate && (scopeDate < scope.windowStart || scopeDate > scope.windowEnd));
  const foundationalException = scope.foundationalSourceIds.includes(sourceId);
  const evidenceId = `E-${sha256(stableStringify({ sourceType, sourceId, contentDigest })).slice(0, 16)}`;

  return {
    ref,
    evidenceId,
    sourceType,
    tenantId,
    visibility,
    sourceId,
    sourceUrl,
    container,
    title,
    author,
    occurredAt,
    modifiedAt,
    retrievedAt,
    verifiedAt,
    freshnessMode,
    contentDigest,
    excerpt,
    accountMatch,
    claimClass,
    authority,
    limitations,
    scopeDate,
    outsideWindow,
    foundationalException,
    accountMatchStrong: accountMatchIsStrong(accountMatch),
    potentialPromptInjection: containsPromptInjection(excerpt) || containsPromptInjection(title),
  };
}

function questionIdFor(policyKey, inputDigest, sourceEvidenceDigest) {
  return `Q-${sha256(stableStringify({
    policyVersion: POLICY_VERSION,
    policyKey,
    inputDigest,
    sourceEvidenceDigest,
  })).slice(0, 20)}`;
}

function questionTargetMatches(policyKey, targetPath) {
  const policy = FIELD_POLICY_MAP[policyKey];
  if (!policy) return false;
  if (policyKey === "health") return targetPath.startsWith("/health/");
  if (policyKey === "motionAnswers") return targetPath === "/motionAnswers";
  return policy.targetPaths.includes(targetPath);
}

function attestationAllowsTarget(policyKey, targetPath, claimClass) {
  const policy = FIELD_POLICY_MAP[policyKey];
  if (!policy?.attestationEligible) return false;
  if (!ATTESTATION_CLAIM_CLASSES.has(claimClass)) return false;
  if (claimClass === "actual" && !ATTESTATION_INTERNAL_ACTUAL_PATHS.some((pattern) => pattern.test(targetPath))) {
    return false;
  }
  if (PROTECTED_ATTESTATION_PATHS.some((pattern) => pattern.test(targetPath))) return false;
  return ATTESTATION_ALLOWED_PATHS.some((pattern) => pattern.test(targetPath)) &&
    questionTargetMatches(policyKey, targetPath);
}

function normalizeAttestationRecord(value, index) {
  const target = `attestations.records[${index}]`;
  assertExactKeys(value, [
    "ref",
    "questionId",
    "policyKey",
    "status",
    "response",
    "responseDigest",
    "answeredAt",
    "questionPlanDigest",
    "allowedTargetPaths",
    "allowedClaimClasses",
  ], target);
  const questionId = requireString(value.questionId, `${target}.questionId`);
  if (!/^Q-[a-f0-9]{20}$/u.test(questionId)) {
    throw new ContextEnricherError("INVALID_ATTESTATION", `${target}.questionId is not an exact stable question ID.`);
  }
  const policyKey = requireString(value.policyKey, `${target}.policyKey`);
  const policy = FIELD_POLICY_MAP[policyKey];
  if (!policy) throw new ContextEnricherError("INVALID_ATTESTATION", `${target}.policyKey is unknown.`);
  const status = requireString(value.status, `${target}.status`);
  if (!ANSWER_STATUSES.has(status)) {
    throw new ContextEnricherError("INVALID_ATTESTATION", `${target}.status is unsupported.`);
  }
  const response = requireString(value.response, `${target}.response`, {
    allowBlank: status !== "answered",
    max: policy.characterLimit ?? 4_000,
  });
  if (status !== "answered" && response) {
    throw new ContextEnricherError("INVALID_ATTESTATION", `${target}.response must be blank for ${status}.`);
  }
  const responseDigest = requireString(value.responseDigest, `${target}.responseDigest`);
  if (responseDigest !== digestObject({ status, response })) {
    throw new ContextEnricherError("ATTESTATION_TAMPERED", `${target}.responseDigest does not match the answer.`);
  }
  const answeredAt = requireIsoDateTime(value.answeredAt, `${target}.answeredAt`);
  assertNotFuture(answeredAt, `${target}.answeredAt`);
  const questionPlanDigest = requireString(value.questionPlanDigest, `${target}.questionPlanDigest`);
  if (!SHA256_PATTERN.test(questionPlanDigest)) {
    throw new ContextEnricherError("INVALID_ATTESTATION", `${target}.questionPlanDigest must be a SHA-256 digest.`);
  }
  const allowedTargetPaths = requireStringArray(value.allowedTargetPaths, `${target}.allowedTargetPaths`);
  const allowedClaimClasses = requireStringArray(value.allowedClaimClasses, `${target}.allowedClaimClasses`, {
    allowed: ATTESTATION_CLAIM_CLASSES,
  });
  const expectedPaths = policy.attestationEligible ? policy.targetPaths : [];
  const expectedClasses = policy.attestationEligible ? [...ATTESTATION_CLAIM_CLASSES].sort() : [];
  if (
    stableStringify(allowedTargetPaths) !== stableStringify(expectedPaths) ||
    stableStringify([...allowedClaimClasses].sort()) !== stableStringify(expectedClasses)
  ) {
    throw new ContextEnricherError("INVALID_ATTESTATION", `${target} authority does not match the central field policy.`);
  }
  const ref = requireString(value.ref, `${target}.ref`);
  const expectedRef = `A-${sha256(stableStringify({ questionId, status, responseDigest, answeredAt })).slice(0, 20)}`;
  if (ref !== expectedRef) throw new ContextEnricherError("ATTESTATION_TAMPERED", `${target}.ref is invalid.`);
  return {
    ref,
    questionId,
    policyKey,
    status,
    response,
    responseDigest,
    answeredAt,
    questionPlanDigest,
    allowedTargetPaths,
    allowedClaimClasses,
  };
}

function attestationIntegrityPayload(bundle) {
  const { integrityDigest: _integrityDigest, ...payload } = bundle;
  return payload;
}

export function validateAttestationBundle(value) {
  assertExactKeys(value, [
    "kind",
    "dashboardSchemaVersion",
    "policyVersion",
    "account",
    "inputDigest",
    "sourceEvidenceDigest",
    "questionPlanDigests",
    "answerDigests",
    "createdAt",
    "records",
    "integrityDigest",
  ], "attestations");
  if (value.kind !== ATTESTATION_KIND) {
    throw new ContextEnricherError("INVALID_ATTESTATION", `Expected ${ATTESTATION_KIND}.`);
  }
  if (value.dashboardSchemaVersion !== DASHBOARD_SCHEMA_VERSION || value.policyVersion !== POLICY_VERSION) {
    throw new ContextEnricherError("STALE_ATTESTATION", "Attestation schema or evidence policy is stale.");
  }
  assertExactKeys(value.account, ["salesforceOrgId", "salesforceAccountId", "canonicalName"], "attestations.account");
  if (!ACCOUNT_ID_PATTERN.test(value.account.salesforceAccountId)) {
    throw new ContextEnricherError("INVALID_ATTESTATION", "Attestation Salesforce Account ID is invalid.");
  }
  for (const key of ["inputDigest", "sourceEvidenceDigest"]) {
    if (!SHA256_PATTERN.test(requireString(value[key], `attestations.${key}`))) {
      throw new ContextEnricherError("INVALID_ATTESTATION", `attestations.${key} must be a SHA-256 digest.`);
    }
  }
  const questionPlanDigests = requireStringArray(value.questionPlanDigests, "attestations.questionPlanDigests");
  const answerDigests = requireStringArray(value.answerDigests, "attestations.answerDigests");
  if (questionPlanDigests.some((item) => !SHA256_PATTERN.test(item)) || answerDigests.some((item) => !SHA256_PATTERN.test(item))) {
    throw new ContextEnricherError("INVALID_ATTESTATION", "Attestation binding digests must be SHA-256 values.");
  }
  const createdAt = requireIsoDateTime(value.createdAt, "attestations.createdAt");
  assertNotFuture(createdAt, "attestations.createdAt");
  if (!Array.isArray(value.records)) {
    throw new ContextEnricherError("INVALID_ATTESTATION", "attestations.records must be an array.");
  }
  const records = value.records.map(normalizeAttestationRecord);
  for (const record of records) {
    if (record.questionId !== questionIdFor(record.policyKey, value.inputDigest, value.sourceEvidenceDigest)) {
      throw new ContextEnricherError("ATTESTATION_TAMPERED", "An attestation question ID is not bound to its dashboard and source evidence.");
    }
  }
  const questionIds = records.map((item) => item.questionId);
  if (new Set(questionIds).size !== questionIds.length) {
    throw new ContextEnricherError("INVALID_ATTESTATION", "A question may be attested only once.");
  }
  if (records.some((item) => !questionPlanDigests.includes(item.questionPlanDigest))) {
    throw new ContextEnricherError("INVALID_ATTESTATION", "An attestation record is not bound to a listed question plan.");
  }
  const normalized = {
    kind: ATTESTATION_KIND,
    dashboardSchemaVersion: DASHBOARD_SCHEMA_VERSION,
    policyVersion: POLICY_VERSION,
    account: {
      salesforceOrgId: requireString(value.account.salesforceOrgId, "attestations.account.salesforceOrgId"),
      salesforceAccountId: value.account.salesforceAccountId,
      canonicalName: requireString(value.account.canonicalName, "attestations.account.canonicalName"),
    },
    inputDigest: value.inputDigest,
    sourceEvidenceDigest: value.sourceEvidenceDigest,
    questionPlanDigests,
    answerDigests,
    createdAt,
    records,
  };
  normalized.integrityDigest = digestObject(attestationIntegrityPayload(normalized));
  if (value.integrityDigest !== normalized.integrityDigest) {
    throw new ContextEnricherError("ATTESTATION_TAMPERED", "Attestation integrity digest does not match its contents.");
  }
  return normalized;
}

function attestationEvidenceItem(record) {
  return {
    ref: record.ref,
    evidenceId: `E-${sha256(stableStringify({
      authority: "account-team-attestation",
      questionId: record.questionId,
      responseDigest: record.responseDigest,
    })).slice(0, 16)}`,
    sourceType: "account-team-attestation",
    title: "Account-team clarification",
    author: { name: "", kind: "uipath" },
    occurredAt: dateOnly(record.answeredAt),
    modifiedAt: record.answeredAt,
    retrievedAt: record.answeredAt,
    verifiedAt: record.answeredAt,
    freshnessMode: "snapshot",
    contentDigest: record.responseDigest,
    excerpt: "",
    accountMatch: { signals: ["explicit-link"], rationale: "Bound to the Salesforce account and preview." },
    claimClass: "opinion",
    authority: "account-team-attestation",
    limitations: ["Account-team attestation; not external proof."],
    scopeDate: dateOnly(record.answeredAt),
    outsideWindow: false,
    foundationalException: false,
    accountMatchStrong: true,
    potentialPromptInjection: containsPromptInjection(record.response),
    policyKey: record.policyKey,
    allowedTargetPaths: record.allowedTargetPaths,
    allowedClaimClasses: record.allowedClaimClasses,
  };
}

function normalizeClaimAnnotation(value, target, evidenceByRef) {
  assertExactKeys(value, ["locator", "claimClass", "evidenceRefs"], target);
  const locator = requireString(value.locator, `${target}.locator`, { max: 200 });
  const claimClass = requireString(value.claimClass, `${target}.claimClass`);
  if (!CLAIM_CLASSES.has(claimClass)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.claimClass is unsupported.`);
  }
  const evidenceRefs = requireStringArray(value.evidenceRefs, `${target}.evidenceRefs`);
  for (const ref of evidenceRefs) {
    if (!evidenceByRef.has(ref)) {
      throw new ContextEnricherError("INVALID_LEDGER", `${target} refers to unknown evidence ${JSON.stringify(ref)}.`);
    }
  }
  return {
    locator,
    claimClass,
    evidenceRefs,
    evidenceIds: evidenceRefs.map((ref) => evidenceByRef.get(ref).evidenceId).sort(),
  };
}

function normalizeProposal(value, index, evidenceByRef) {
  const target = `ledger.proposals[${index}]`;
  assertExactKeys(value, [
    "ref",
    "targetPath",
    "operation",
    "value",
    "semanticKey",
    "evidenceRefs",
    "claimClass",
    "claimAnnotations",
    "rationale",
    "position",
  ], target);
  const ref = requireString(value.ref, `${target}.ref`, { max: 200 });
  const targetPath = requireString(value.targetPath, `${target}.targetPath`, { max: 1_000 });
  decodeJsonPointer(targetPath);
  const operation = requireString(value.operation, `${target}.operation`);
  if (!["set", "insert", "update"].includes(operation)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.operation is unsupported.`);
  }
  const semanticKey = requireString(value.semanticKey, `${target}.semanticKey`, {
    allowBlank: true,
    max: 1_000,
  });
  const evidenceRefs = requireStringArray(value.evidenceRefs, `${target}.evidenceRefs`);
  if (!evidenceRefs.length) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.evidenceRefs must not be empty.`);
  }
  for (const refValue of evidenceRefs) {
    if (!evidenceByRef.has(refValue)) {
      throw new ContextEnricherError("INVALID_LEDGER", `${target} refers to unknown evidence ${JSON.stringify(refValue)}.`);
    }
  }
  const claimClass = requireString(value.claimClass, `${target}.claimClass`);
  if (!PROPOSAL_CLAIM_CLASSES.has(claimClass)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.claimClass is unsupported.`);
  }
  if (!Array.isArray(value.claimAnnotations)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.claimAnnotations must be an array.`);
  }
  const claimAnnotations = value.claimAnnotations.map((item, annotationIndex) =>
    normalizeClaimAnnotation(item, `${target}.claimAnnotations[${annotationIndex}]`, evidenceByRef));
  const rationale = requireString(value.rationale, `${target}.rationale`, { max: 2_000 });
  const position = value.position;
  if (!(position === null || position === "append" || (Number.isInteger(position) && position > 0))) {
    throw new ContextEnricherError(
      "INVALID_LEDGER",
      `${target}.position must be null, append, or a positive one-based integer.`,
    );
  }
  if (operation === "insert" && position === null) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.position is required for ${operation}.`);
  }
  if (operation !== "insert" && position !== null) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.position must be null for ${operation}.`);
  }
  if (operation === "update" && !semanticKey) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.semanticKey is required for ${operation}.`);
  }
  if (operation === "set" && semanticKey) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.semanticKey must be blank for ${operation}.`);
  }
  return {
    ref,
    targetPath,
    operation,
    value: deepClone(value.value),
    semanticKey,
    evidenceRefs,
    evidenceIds: evidenceRefs.map((item) => evidenceByRef.get(item).evidenceId).sort(),
    claimClass,
    claimAnnotations,
    rationale,
    position,
  };
}

function normalizeOneNoteSelection(value, index) {
  const target = `ledger.scope.oneNoteSelections[${index}]`;
  assertExactKeys(value, ["notebook", "section", "page", "sourceId", "captureDigest"], target);
  const notebook = requireString(value.notebook, `${target}.notebook`, { max: 500 });
  const section = requireString(value.section, `${target}.section`, { max: 500 });
  const page = requireString(value.page, `${target}.page`, { max: 500 });
  const sourceId = requireString(value.sourceId, `${target}.sourceId`, { max: 2_000 });
  const captureDigest = requireString(value.captureDigest, `${target}.captureDigest`);
  if (!SHA256_PATTERN.test(captureDigest)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.captureDigest must be a SHA-256 digest.`);
  }
  return { notebook, section, page, sourceId, captureDigest };
}

function canonicalPrivateSlackScope(containerIds) {
  return [...containerIds].sort().map((containerId) => `in:${containerId}`).join(" OR ");
}

function normalizeDiscoveryRun(value, index, selectedSources) {
  const target = `ledger.scope.discoveryRuns[${index}]`;
  assertExactKeys(value, [
    "sourceType",
    "tenantId",
    "scope",
    "containerIds",
    "queryDigest",
    "pages",
    "complete",
    "limitations",
    "verifiedAt",
  ], target);
  const sourceType = requireString(value.sourceType, `${target}.sourceType`);
  if (!SOURCE_TYPES.has(sourceType) || !selectedSources.includes(sourceType)) {
    throw new ContextEnricherError("SOURCE_OUT_OF_SCOPE", `${target}.sourceType is not a selected source.`);
  }
  const tenantId = requireString(value.tenantId, `${target}.tenantId`, { max: 1_000 });
  const sourceScope = requireString(value.scope, `${target}.scope`, { max: 2_000 });
  const containerIds = requireStringArray(value.containerIds, `${target}.containerIds`);
  if (new Set(containerIds).size !== containerIds.length) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.containerIds contains duplicates.`);
  }
  if (PRIVATE_SLACK_TYPES.has(sourceType)) {
    if (!containerIds.length || containerIds.some((containerId) => !/^[A-Za-z0-9._:-]+$/u.test(containerId))) {
      throw new ContextEnricherError(
        "PRIVATE_SLACK_SCOPE_REQUIRED",
        `${target}.containerIds must contain exact opaque Slack parent IDs.`,
      );
    }
    const requiredScope = canonicalPrivateSlackScope(containerIds);
    if (sourceScope !== requiredScope) {
      throw new ContextEnricherError(
        "PRIVATE_SLACK_SCOPE_REQUIRED",
        `${target}.scope must be the canonical exact-container filter ${JSON.stringify(requiredScope)}.`,
      );
    }
  }
  const queryDigest = requireString(value.queryDigest, `${target}.queryDigest`);
  if (!SHA256_PATTERN.test(queryDigest)) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.queryDigest must be a SHA-256 digest.`);
  }
  if (!Number.isInteger(value.pages) || value.pages < 1) {
    throw new ContextEnricherError("INVALID_LEDGER", `${target}.pages must be a positive integer.`);
  }
  const complete = requireBoolean(value.complete, `${target}.complete`);
  const limitations = requireStringArray(value.limitations, `${target}.limitations`);
  const verifiedAt = requireIsoDateTime(value.verifiedAt, `${target}.verifiedAt`, { allowBlank: true });
  return {
    sourceType,
    tenantId,
    scope: sourceScope,
    containerIds,
    queryDigest,
    pages: value.pages,
    complete,
    limitations,
    verifiedAt,
  };
}

export function normalizeEvidenceLedger(value, { attestations = null } = {}) {
  assertExactKeys(value, [
    "kind",
    "version",
    "dashboardSchemaVersion",
    "policyVersion",
    "account",
    "scope",
    "items",
    "proposals",
    "gaps",
  ], "ledger");
  if (value.kind !== LEDGER_KIND || value.version !== LEDGER_VERSION) {
    throw new ContextEnricherError("LEDGER_VERSION_MISMATCH", `Only ${LEDGER_KIND} version ${LEDGER_VERSION} is supported.`);
  }
  if (value.dashboardSchemaVersion !== DASHBOARD_SCHEMA_VERSION) {
    throw new ContextEnricherError(
      "SCHEMA_MISMATCH",
      `Only dashboard schema ${DASHBOARD_SCHEMA_VERSION} is supported.`,
    );
  }
  if (value.policyVersion !== POLICY_VERSION) {
    throw new ContextEnricherError(
      "POLICY_MISMATCH",
      `Evidence policy ${POLICY_VERSION} is required; received ${JSON.stringify(value.policyVersion)}.`,
    );
  }

  assertExactKeys(value.account, ["salesforceOrgId", "salesforceAccountId", "canonicalName", "aliases", "domains", "contacts"], "ledger.account");
  const salesforceOrgId = requireString(value.account.salesforceOrgId, "ledger.account.salesforceOrgId", { max: 500 });
  const salesforceAccountId = requireString(value.account.salesforceAccountId, "ledger.account.salesforceAccountId");
  if (!ACCOUNT_ID_PATTERN.test(salesforceAccountId)) {
    throw new ContextEnricherError("INVALID_ACCOUNT", "The ledger requires a 15- or 18-character Salesforce Account ID beginning with 001.");
  }
  const canonicalName = requireString(value.account.canonicalName, "ledger.account.canonicalName", { max: 500 });
  const aliases = requireStringArray(value.account.aliases, "ledger.account.aliases");
  const domains = requireStringArray(value.account.domains, "ledger.account.domains");
  if (!Array.isArray(value.account.contacts)) {
    throw new ContextEnricherError("INVALID_LEDGER", "ledger.account.contacts must be an array.");
  }
  const contacts = value.account.contacts.map(normalizeContact);

  assertExactKeys(value.scope, [
    "sources",
    "windowStart",
    "windowEnd",
    "privateSlackConsent",
    "privateSlackScopes",
    "foundationalSourceIds",
    "oneNoteSelections",
    "discoveryRuns",
    "coverageNotes",
    "collectedAt",
  ], "ledger.scope");
  const sources = requireStringArray(value.scope.sources, "ledger.scope.sources", { allowed: SOURCE_TYPES });
  const windowStart = requireIsoDate(value.scope.windowStart, "ledger.scope.windowStart");
  const windowEnd = requireIsoDate(value.scope.windowEnd, "ledger.scope.windowEnd");
  if (windowStart > windowEnd) {
    throw new ContextEnricherError("INVALID_LEDGER", "ledger.scope.windowEnd must not precede windowStart.");
  }
  const privateSlackConsent = requireBoolean(value.scope.privateSlackConsent, "ledger.scope.privateSlackConsent");
  const privateSlackScopes = requireStringArray(value.scope.privateSlackScopes, "ledger.scope.privateSlackScopes");
  const foundationalSourceIds = requireStringArray(
    value.scope.foundationalSourceIds,
    "ledger.scope.foundationalSourceIds",
  );
  if (!privateSlackConsent && privateSlackScopes.length) {
    throw new ContextEnricherError(
      "INVALID_LEDGER",
      "ledger.scope.privateSlackScopes must be empty when privateSlackConsent is false.",
    );
  }
  if (
    privateSlackConsent &&
    sources.some((source) => PRIVATE_SLACK_TYPES.has(source)) &&
    !privateSlackScopes.length
  ) {
    throw new ContextEnricherError(
      "PRIVATE_SLACK_SCOPE_REQUIRED",
      "Name the exact private Slack channel or DM scopes before collecting private evidence.",
    );
  }
  if (!Array.isArray(value.scope.oneNoteSelections)) {
    throw new ContextEnricherError("INVALID_LEDGER", "ledger.scope.oneNoteSelections must be an array.");
  }
  const oneNoteSelections = value.scope.oneNoteSelections.map((item, index) =>
    normalizeOneNoteSelection(item, index));
  const oneNoteIds = oneNoteSelections.map((item) => item.sourceId);
  if (new Set(oneNoteIds).size !== oneNoteIds.length) {
    throw new ContextEnricherError("INVALID_LEDGER", "ledger.scope.oneNoteSelections contains duplicate sourceId values.");
  }
  if (!Array.isArray(value.scope.discoveryRuns)) {
    throw new ContextEnricherError("INVALID_LEDGER", "ledger.scope.discoveryRuns must be an array.");
  }
  const discoveryRuns = value.scope.discoveryRuns.map((item, index) =>
    normalizeDiscoveryRun(item, index, sources));
  const discoverySourceTypes = discoveryRuns.map((item) => item.sourceType);
  if (new Set(discoverySourceTypes).size !== discoverySourceTypes.length) {
    throw new ContextEnricherError("INVALID_LEDGER", "ledger.scope.discoveryRuns contains duplicate sourceType values.");
  }
  const discoveredSources = new Set(discoveryRuns.map((item) => item.sourceType));
  for (const source of sources) {
    if (!discoveredSources.has(source)) {
      throw new ContextEnricherError(
        "DISCOVERY_RECORD_REQUIRED",
        `ledger.scope.discoveryRuns is missing selected source ${source}.`,
      );
    }
  }
  const privateDiscoveryContainers = discoveryRuns
    .filter((run) => PRIVATE_SLACK_TYPES.has(run.sourceType))
    .flatMap((run) => run.containerIds);
  if (
    privateSlackConsent &&
    stableStringify([...new Set(privateDiscoveryContainers)].sort()) !==
      stableStringify([...privateSlackScopes].sort())
  ) {
    throw new ContextEnricherError(
      "PRIVATE_SLACK_SCOPE_REQUIRED",
      "Private Slack discovery containerIds must exactly match the consented privateSlackScopes.",
    );
  }
  const coverageNotes = requireStringArray(value.scope.coverageNotes, "ledger.scope.coverageNotes");
  const collectedAt = requireIsoDateTime(value.scope.collectedAt, "ledger.scope.collectedAt");
  assertNotFuture(collectedAt, "ledger.scope.collectedAt");
  const scope = {
    sources,
    windowStart,
    windowEnd,
    privateSlackConsent,
    privateSlackScopes,
    foundationalSourceIds,
    oneNoteSelections,
    discoveryRuns,
    coverageNotes,
    collectedAt,
  };

  if (!Array.isArray(value.items) || !Array.isArray(value.proposals)) {
    throw new ContextEnricherError("INVALID_LEDGER", "ledger.items and ledger.proposals must be arrays.");
  }
  const items = value.items.map((item, index) => normalizeEvidenceItem(item, index, scope));
  const itemSourceIds = new Set(items.map((item) => item.sourceId));
  for (const sourceId of foundationalSourceIds) {
    if (!itemSourceIds.has(sourceId)) {
      throw new ContextEnricherError(
        "INVALID_LEDGER",
        `Foundational source ${JSON.stringify(sourceId)} is not present in ledger.items.`,
      );
    }
  }
  const collectedTime = Date.parse(collectedAt);
  for (const item of items) {
    const retrievedTime = Date.parse(item.retrievedAt);
    assertNotFuture(item.retrievedAt, `Evidence ${item.ref} retrievedAt`);
    assertNotFuture(item.verifiedAt, `Evidence ${item.ref} verifiedAt`);
    if (item.modifiedAt) {
      assertNotFuture(
        item.modifiedAt,
        `Evidence ${item.ref} modifiedAt`,
        Date.now(),
        MAX_SOURCE_CLOCK_SKEW_MS,
      );
    }
    if (
      item.occurredAt &&
      !(item.sourceType === "outlook-calendar" && item.claimClass === "meeting-scheduled")
    ) {
      assertNotFuture(
        item.occurredAt,
        `Evidence ${item.ref} occurredAt`,
        Date.now(),
      );
    }
    if (retrievedTime > collectedTime) {
      throw new ContextEnricherError(
        "INVALID_EVIDENCE_CHRONOLOGY",
        `Evidence ${item.ref} was retrieved after ledger.scope.collectedAt.`,
      );
    }
    if (item.verifiedAt && Date.parse(item.verifiedAt) <= Math.max(retrievedTime, collectedTime)) {
      throw new ContextEnricherError(
        "INVALID_EVIDENCE_CHRONOLOGY",
        `Evidence ${item.ref} verification must be later than its retrieval and collection timestamps.`,
      );
    }
  }
  for (const run of discoveryRuns) {
    assertNotFuture(run.verifiedAt, `Discovery ${run.sourceType} verifiedAt`);
    if (run.verifiedAt && Date.parse(run.verifiedAt) <= collectedTime) {
      throw new ContextEnricherError(
        "INVALID_EVIDENCE_CHRONOLOGY",
        `Discovery verification for ${run.sourceType} must be later than ledger.scope.collectedAt.`,
      );
    }
  }
  const itemRefs = items.map((item) => item.ref);
  if (new Set(itemRefs).size !== itemRefs.length) {
    throw new ContextEnricherError("INVALID_LEDGER", "ledger.items contains duplicate ref values.");
  }
  const evidenceIds = items.map((item) => item.evidenceId);
  if (new Set(evidenceIds).size !== evidenceIds.length) {
    throw new ContextEnricherError("EVIDENCE_ID_COLLISION", "Two evidence records resolved to the same stable evidence ID.");
  }
  const attestationRecords = attestations?.records?.filter((item) => item.status === "answered") ?? [];
  const attestationItems = attestationRecords.map(attestationEvidenceItem);
  const evidenceByRef = new Map([...items, ...attestationItems].map((item) => [item.ref, item]));
  if (evidenceByRef.size !== items.length + attestationItems.length) {
    throw new ContextEnricherError("INVALID_LEDGER", "Evidence and attestation refs must be unique.");
  }
  const proposals = value.proposals.map((proposal, index) => normalizeProposal(proposal, index, evidenceByRef));
  const proposalRefs = proposals.map((proposal) => proposal.ref);
  if (new Set(proposalRefs).size !== proposalRefs.length) {
    throw new ContextEnricherError("INVALID_LEDGER", "ledger.proposals contains duplicate ref values.");
  }
  const gaps = requireStringArray(value.gaps, "ledger.gaps");

  return {
    kind: LEDGER_KIND,
    version: LEDGER_VERSION,
    dashboardSchemaVersion: DASHBOARD_SCHEMA_VERSION,
    policyVersion: POLICY_VERSION,
    account: { salesforceOrgId, salesforceAccountId, canonicalName, aliases, domains, contacts },
    scope,
    items,
    attestationItems,
    attestations,
    proposals,
    gaps,
  };
}

function stableLedgerPayload(ledger, { includeProposals = true } = {}) {
  const payload = {
    kind: ledger.kind,
    version: ledger.version,
    dashboardSchemaVersion: ledger.dashboardSchemaVersion,
    policyVersion: ledger.policyVersion,
    account: ledger.account,
    scope: {
      ...ledger.scope,
      collectedAt: undefined,
      discoveryRuns: ledger.scope.discoveryRuns.map(({ verifiedAt: _verifiedAt, ...run }) => run),
    },
    items: ledger.items.map((item) => {
      const {
        retrievedAt: _retrievedAt,
        verifiedAt: _verifiedAt,
        scopeDate: _scopeDate,
        outsideWindow: _outsideWindow,
        foundationalException: _foundationalException,
        accountMatchStrong: _accountMatchStrong,
        potentialPromptInjection: _potentialPromptInjection,
        ...stable
      } = item;
      return stable;
    }),
    gaps: ledger.gaps,
  };
  delete payload.scope.collectedAt;
  if (includeProposals) payload.proposals = ledger.proposals;
  return payload;
}

export function evidenceLedgerDigest(ledger) {
  return digestObject(stableLedgerPayload(ledger));
}

export function evidenceContextDigest(ledger) {
  return digestObject(stableLedgerPayload(ledger, { includeProposals: false }));
}

const MOTION_QUESTION_GROUPS = {
  "Re-Recruit": [
    "Why are they questioning UiPath?",
    "Who is influencing the change?",
    "What competitive threat exists?",
    "What executive, product, or commercial intervention is required?",
  ],
  Consumption: [
    "What is the current consumption?",
    "What is the target consumption?",
    "What is the timeline to production?",
    "What is blocking implementation?",
    "Who owns getting consumption into production?",
  ],
  Hybrid: [
    "What consumption goals must be achieved?",
    "What new platform capabilities must be sold?",
    "What executive relationships need to be developed?",
    "What future vision, like agentification, must be adopted?",
  ],
};
const MOTION_QUESTIONS = new Set(Object.values(MOTION_QUESTION_GROUPS).flat());

export function decodeJsonPointer(pointer) {
  if (typeof pointer !== "string" || !pointer.startsWith("/") || pointer === "/") {
    throw new ContextEnricherError("UNSAFE_TARGET_PATH", "Proposal targetPath must be a non-root JSON Pointer.");
  }
  return pointer.slice(1).split("/").map((rawSegment) => {
    if (/~(?![01])/u.test(rawSegment)) {
      throw new ContextEnricherError("UNSAFE_TARGET_PATH", `Invalid JSON Pointer escape in ${JSON.stringify(pointer)}.`);
    }
    const segment = rawSegment.replace(/~1/g, "/").replace(/~0/g, "~");
    if (!segment || DANGEROUS_SEGMENTS.has(segment) || segment.includes("\0")) {
      throw new ContextEnricherError("UNSAFE_TARGET_PATH", `Unsafe JSON Pointer segment in ${JSON.stringify(pointer)}.`);
    }
    return segment;
  });
}

function isAllowedSetPath(targetPath) {
  const segments = decodeJsonPointer(targetPath);
  if (segments.length === 1 && TOP_LEVEL_CONTEXT_FIELDS.has(segments[0])) return true;
  if (
    segments.length === 3 &&
    segments[0] === "metrics" &&
    METRIC_KEYS.has(segments[1]) &&
    ["value", "note"].includes(segments[2])
  ) return true;
  if (
    segments.length === 3 &&
    segments[0] === "metrics" &&
    segments[1] === "utilization" &&
    UTILIZATION_KEYS.has(segments[2])
  ) return true;
  if (
    segments.length === 3 &&
    segments[0] === "health" &&
    HEALTH_KEYS.has(segments[1]) &&
    ["status", "evidence", "mitigation", "owner"].includes(segments[2])
  ) return true;
  if (
    segments.length === 2 &&
    segments[0] === "executiveCadence" &&
    ["type", "date"].includes(segments[1])
  ) return true;
  if (
    segments.length === 2 &&
    segments[0] === "consumptionPlan" &&
    ["asOf", "forecastPeriod"].includes(segments[1])
  ) return true;
  return false;
}

function pointerGet(value, pointer) {
  return decodeJsonPointer(pointer).reduce((current, segment) => current?.[segment], value);
}

function pointerSet(value, pointer, nextValue) {
  const segments = decodeJsonPointer(pointer);
  let current = value;
  for (let index = 0; index < segments.length - 1; index += 1) {
    current = current[segments[index]];
  }
  current[segments.at(-1)] = nextValue;
}

function normalizedKey(value) {
  return String(value ?? "").trim().toLowerCase().replace(/\s+/g, " ");
}

export function semanticRowKey(targetPath, row) {
  if (!isPlainObject(row)) return "";
  if (targetPath === "/goals") return normalizedKey(row.text);
  if (targetPath === "/cadenceGoals") return normalizedKey(`${row.label}|${row.date}`);
  if (targetPath === "/workstreams") return normalizedKey(row.name);
  if (targetPath === "/consumptionPlan/groups") return normalizedKey(row.element);
  if (targetPath === "/relationships") {
    return normalizedKey(`${row.uipathName}|${row.uipathRole}|${row.customerName}|${row.customerRole}`);
  }
  if (targetPath === "/eltAsks") return normalizedKey(`${row.type}|${row.owner}|${row.ask}`);
  if (targetPath === "/timeline") return normalizedKey(`${row.date}|${row.title}`);
  return "";
}

function arrayForTarget(dashboard, targetPath) {
  const value = pointerGet(dashboard, targetPath);
  if (!Array.isArray(value)) {
    throw new ContextEnricherError("UNSAFE_TARGET_PATH", `${targetPath} is not a schema array.`);
  }
  return value;
}

function matchingRowIndexes(dashboard, targetPath, semanticKey) {
  return arrayForTarget(dashboard, targetPath)
    .map((row, index) => ({ key: semanticRowKey(targetPath, row), index }))
    .filter((item) => item.key === normalizedKey(semanticKey))
    .map((item) => item.index);
}

function matchingConsumptionProductRows(dashboard, semanticKey) {
  const wanted = String(semanticKey ?? "").trim();
  const matches = [];
  for (const [groupIndex, group] of dashboard.consumptionPlan.groups.entries()) {
    for (const [rowIndex, row] of group.rows.entries()) {
      if (`${group.element}|${row.product}` === wanted) {
        matches.push({ groupIndex, rowIndex, row });
      }
    }
  }
  return matches;
}

function proposalTargetKey(proposal) {
  if (proposal.operation === "set") return proposal.targetPath;
  const semanticKey = proposal.semanticKey || semanticRowKey(proposal.targetPath, proposal.value);
  return `${proposal.targetPath}|${normalizedKey(semanticKey)}`;
}

function existingValueForProposal(dashboard, proposal) {
  if (proposal.operation === "set") return pointerGet(dashboard, proposal.targetPath);
  if (proposal.targetPath === "/motionAnswers") {
    return dashboard.motionAnswers[proposal.semanticKey];
  }
  if (proposal.targetPath === PRODUCT_FORECAST_TARGET) {
    const matches = matchingConsumptionProductRows(dashboard, proposal.semanticKey);
    return matches.length === 1
      ? { forecast: deepClone(matches[0].row.forecast), comments: matches[0].row.comments }
      : undefined;
  }
  if (proposal.operation === "update") {
    const matches = matchingRowIndexes(dashboard, proposal.targetPath, proposal.semanticKey);
    return matches.length === 1 ? dashboardAtArrayPath(dashboard, proposal.targetPath)[matches[0]] : undefined;
  }
  return undefined;
}

function dashboardAtArrayPath(dashboard, targetPath) {
  return arrayForTarget(dashboard, targetPath);
}

function applyTypedOperation(dashboard, proposal, { validationOnly = false } = {}) {
  if (proposal.operation === "set") {
    pointerSet(dashboard, proposal.targetPath, deepClone(proposal.value));
    return;
  }
  if (proposal.targetPath === "/motionAnswers" && proposal.operation === "update") {
    dashboard.motionAnswers[proposal.semanticKey] = proposal.value;
    return;
  }
  if (proposal.targetPath === PRODUCT_FORECAST_TARGET && proposal.operation === "update") {
    const matches = matchingConsumptionProductRows(dashboard, proposal.semanticKey);
    if (matches.length !== 1) {
      throw new ContextEnricherError(
        "SEMANTIC_ROW_NOT_UNIQUE",
        `${PRODUCT_FORECAST_TARGET} semantic key ${JSON.stringify(proposal.semanticKey)} matched ${matches.length} rows.`,
      );
    }
    const row = matches[0].row;
    row.forecast = deepClone(proposal.value.forecast);
    row.comments = proposal.value.comments;
    return;
  }
  const target = arrayForTarget(dashboard, proposal.targetPath);
  if (proposal.operation === "insert") {
    if (validationOnly || proposal.position === "append") {
      target.push(deepClone(proposal.value));
    } else {
      if (proposal.position > target.length + 1) {
        throw new ContextEnricherError(
          "ARRAY_PLACEMENT_DRIFT",
          `${proposal.targetPath} position ${proposal.position} is no longer available without implicit prerequisite inserts.`,
        );
      }
      target.splice(proposal.position - 1, 0, deepClone(proposal.value));
    }
    return;
  }
  const matches = matchingRowIndexes(dashboard, proposal.targetPath, proposal.semanticKey);
  if (matches.length !== 1) {
    throw new ContextEnricherError(
      "SEMANTIC_ROW_NOT_UNIQUE",
      `${proposal.targetPath} semantic key ${JSON.stringify(proposal.semanticKey)} matched ${matches.length} rows.`,
    );
  }
  target[matches[0]] = deepClone(proposal.value);
}

function proposalEvidence(ledger, proposal) {
  const refs = new Set(proposal.evidenceRefs);
  return [...ledger.items, ...(ledger.attestationItems ?? [])].filter((item) => refs.has(item.ref));
}

function allowedPublicWebTarget(targetPath) {
  return targetPath === "/tagline" || targetPath === "/goals" || targetPath === "/motionAnswers";
}

function contentPolicyReasons(dashboard, proposal) {
  const reasons = [];
  const value = proposal.value;
  if (proposal.operation === "set" && typeof value !== "string") {
    reasons.push("Typed scalar set proposals require a string value.");
    return reasons;
  }
  if (proposal.targetPath === "/tagline" && codePointLength(value) > 170) {
    reasons.push("Customer value headline exceeds 170 characters.");
  }
  if (proposal.targetPath === "/statusSummary") {
    const statusLines = lines(value);
    if (statusLines.length !== 4) reasons.push("statusSummary must contain exactly four non-empty lines.");
    statusLines.forEach((line, index) => {
      if (codePointLength(line) > 120) reasons.push(`statusSummary line ${index + 1} exceeds 120 characters.`);
    });
    const expectedLocators = ["value", "progress", "risk-decision", "next-action"];
    const actualLocators = proposal.claimAnnotations.map((item) => item.locator);
    if (stableStringify(expectedLocators) !== stableStringify(actualLocators)) {
      reasons.push("statusSummary needs ordered claim annotations: value, progress, risk-decision, next-action.");
    }
  }
  if (proposal.targetPath === "/useCases") {
    const useCaseLines = lines(value);
    if (useCaseLines.length > 3) reasons.push("Where Used supports at most three Page 1 use-case lines.");
    useCaseLines.forEach((line, index) => {
      if (codePointLength(line) > 100) reasons.push(`Where Used line ${index + 1} exceeds 100 characters.`);
    });
  }
  if (proposal.targetPath === "/motion" && !["Re-Recruit", "Consumption", "Hybrid"].includes(value)) {
    reasons.push("Account motion must be Re-Recruit, Consumption, or Hybrid.");
  }
  if (proposal.targetPath === "/executiveCadence/type" && !["lastQbr", "nextQbr", "lastEbc", "nextEbc"].includes(value)) {
    reasons.push("Executive cadence type is not canonical.");
  }
  if (
    ["/renewalDate", "/executiveCadence/date", "/consumptionPlan/asOf"].includes(proposal.targetPath) &&
    value !== "" &&
    !isRealIsoDate(value)
  ) {
    reasons.push(`${proposal.targetPath} must be an ISO date-only value.`);
  }
  if (/^\/health\/[^/]+\/status$/u.test(proposal.targetPath) && !["Red", "Green"].includes(value)) {
    reasons.push("Contextual health status must be Red or Green.");
  }
  if (proposal.targetPath.startsWith("/metrics/") && codePointLength(value) > 500) {
    reasons.push("Metric value or note is unreasonably long.");
  }
  if (proposal.operation === "insert" || (proposal.operation === "update" && proposal.targetPath !== "/motionAnswers")) {
    if (!isPlainObject(value)) reasons.push("Atomic row proposals require an object value.");
  }
  if (proposal.targetPath === "/motionAnswers") {
    if (proposal.operation !== "update" || !MOTION_QUESTIONS.has(proposal.semanticKey) || typeof value !== "string") {
      reasons.push("Motion answers require an exact canonical question semanticKey and a string value.");
    }
  }
  if (proposal.targetPath === PRODUCT_FORECAST_TARGET) {
    if (proposal.operation !== "update" || !proposal.semanticKey || !isPlainObject(value)) {
      reasons.push("Product forecast changes require a semantic update with an object value.");
    } else {
      const keys = Object.keys(value).sort();
      if (stableStringify(keys) !== stableStringify(["comments", "forecast"])) {
        reasons.push("Product forecast updates may contain only forecast and comments.");
      }
      if (!isPlainObject(value.forecast) ||
        stableStringify(Object.keys(value.forecast).sort()) !== stableStringify(["q1", "q2", "q3", "q4"]) ||
        Object.values(value.forecast).some((item) => typeof item !== "string") ||
        typeof value.comments !== "string") {
        reasons.push("Product forecast updates require string q1–q4 values and a string comment.");
      }
      if (matchingConsumptionProductRows(dashboard, proposal.semanticKey).length !== 1) {
        reasons.push("Product forecast target must match exactly one existing source-backed product row.");
      }
    }
  }
  if (proposal.targetPath === "/goals" && isPlainObject(value)) {
    if (codePointLength(value.text) > 140) reasons.push("Day 2 Strategy outcome exceeds 140 characters.");
    if (codePointLength(value.target) > 80) reasons.push("Day 2 Strategy target exceeds 80 characters.");
    if (codePointLength(value.owner) > 80) reasons.push("Day 2 Strategy owner exceeds 80 characters.");
  }
  if (proposal.targetPath === "/eltAsks" && isPlainObject(value) && codePointLength(value.ask) > 160) {
    reasons.push("ELT ask exceeds 160 characters.");
  }
  if (proposal.targetPath === "/workstreams" && isPlainObject(value)) {
    if (codePointLength(value.risk) > 160) reasons.push("Workstream risk exceeds 160 characters.");
    const milestones = lines(value.milestones);
    const outcomes = lines(value.outcomes);
    if (milestones.length > 4) reasons.push("Workstream has more than four milestone lines.");
    milestones.forEach((line, index) => {
      if (codePointLength(line) > 100) reasons.push(`Workstream milestone ${index + 1} exceeds 100 characters.`);
    });
    if (outcomes.length > 2) reasons.push("Workstream has more than two outcome lines.");
    outcomes.forEach((line, index) => {
      if (codePointLength(line) > 140) reasons.push(`Workstream outcome ${index + 1} exceeds 140 characters.`);
    });
  }
  if (proposal.operation === "set" && !isAllowedSetPath(proposal.targetPath)) {
    reasons.push("Target path is not in the typed scalar allowlist.");
  }
  if (proposal.operation === "insert" && !INSERT_TARGETS.has(proposal.targetPath)) {
    reasons.push("Target path is not in the typed row-insert allowlist.");
  }
  if (
    proposal.operation === "update" &&
    proposal.targetPath !== "/motionAnswers" &&
    proposal.targetPath !== PRODUCT_FORECAST_TARGET &&
    !INSERT_TARGETS.has(proposal.targetPath)
  ) {
    reasons.push("Target path is not in the typed row-update allowlist.");
  }
  if (proposal.targetPath === "/sources" || proposal.targetPath === "/sourceNotes") {
    reasons.push("Sources and sourceNotes are system-managed; contextual proposals cannot write them.");
  }
  if (["/customerName", "/schemaVersion", "/healthConflictAcknowledged"].includes(proposal.targetPath)) {
    reasons.push("This protected dashboard field cannot be proposed.");
  }
  if (
    proposal.operation === "insert" &&
    Number.isInteger(proposal.position) &&
    INSERT_TARGETS.has(proposal.targetPath)
  ) {
    const totalForTarget = dashboardAtArrayPath(dashboard, proposal.targetPath).length;
    if (proposal.position > totalForTarget + 1_000) {
      reasons.push("Array insertion position is unreasonably out of range.");
    }
  }
  return reasons;
}

function authorityPolicyReasons(ledger, proposal) {
  const reasons = [];
  const evidence = proposalEvidence(ledger, proposal);
  const authorities = new Set(evidence.map((item) => item.authority));
  const sourceTypes = new Set(evidence.map((item) => item.sourceType));
  const evidenceClasses = new Set(evidence.map((item) => item.claimClass));
  const claimMatchedEvidence = proposal.claimClass === "mixed"
    ? evidence
    : evidence.filter((item) =>
      item.claimClass === proposal.claimClass ||
      item.authority === "account-team-attestation" && item.allowedClaimClasses.includes(proposal.claimClass));
  const claimMatchedAuthorities = new Set(claimMatchedEvidence.map((item) => item.authority));
  const attestationEvidence = evidence.filter((item) => item.authority === "account-team-attestation");

  for (const item of attestationEvidence) {
    const attestedAnnotationClasses = proposal.claimAnnotations
      .filter((annotation) => annotation.evidenceRefs.includes(item.ref))
      .map((annotation) => annotation.claimClass);
    const authorized = proposal.claimClass === "mixed"
      ? attestedAnnotationClasses.length > 0 &&
        attestedAnnotationClasses.every((claimClass) =>
          attestationAllowsTarget(item.policyKey, proposal.targetPath, claimClass))
      : attestationAllowsTarget(item.policyKey, proposal.targetPath, proposal.claimClass);
    if (!authorized) {
      reasons.push(`Account-team attestation ${item.evidenceId} is not authorized for this target or claim class.`);
    }
  }
  if (
    attestationEvidence.length &&
    PROTECTED_ATTESTATION_PATHS.some((pattern) => pattern.test(proposal.targetPath))
  ) {
    reasons.push("Account-team attestation cannot be sole authority for this protected fact.");
  }

  if (evidence.some((item) => !item.accountMatchStrong)) {
    reasons.push("At least one supporting source lacks a strong account match.");
  }
  if (evidence.some((item) => item.authority === "salesforce-exact")) {
    reasons.push("Salesforce exact facts must be handled by the Salesforce child skill, not a contextual proposal.");
  }
  if (evidence.some((item) => item.limitations.some((limit) => /metadata[- ]only/i.test(limit)))) {
    reasons.push("Metadata-only attachments cannot support dashboard claims.");
  }
  if (proposal.claimClass === "mixed") {
    if (!proposal.claimAnnotations.length) reasons.push("Mixed proposals require claim annotations.");
  } else if (!claimMatchedEvidence.length) {
    reasons.push(`No supporting evidence is classified as ${proposal.claimClass}.`);
  }
  for (const annotation of proposal.claimAnnotations) {
    if (!annotation.evidenceRefs.every((ref) => proposal.evidenceRefs.includes(ref))) {
      reasons.push(`Claim annotation ${annotation.locator} cites evidence outside the proposal.`);
      continue;
    }
    const allEvidenceByRef = new Map(
      [...ledger.items, ...(ledger.attestationItems ?? [])].map((item) => [item.ref, item]),
    );
    const annotationEvidence = annotation.evidenceRefs.map((ref) => allEvidenceByRef.get(ref));
    const annotationClaimEvidence = annotationEvidence.filter((item) =>
      item?.claimClass === annotation.claimClass ||
      item?.authority === "account-team-attestation" && item.allowedClaimClasses.includes(annotation.claimClass));
    if (!annotationClaimEvidence.length) {
      reasons.push(`Claim annotation ${annotation.locator} lacks ${annotation.claimClass} evidence.`);
    }
    if (
      annotationClaimEvidence.some((item) => item.sourceType === "onenote") &&
      annotationClaimEvidence.every((item) => item.sourceType === "onenote")
    ) {
      reasons.push(`Claim annotation ${annotation.locator} relies on OneNote without same-claim corroboration.`);
    }
    if (
      proposal.targetPath === "/statusSummary" &&
      annotation.locator === "value" &&
      (
        annotation.claimClass !== "actual" ||
        annotationClaimEvidence.length === 0 ||
        annotationClaimEvidence.every((item) =>
          ["internal-operations", "personal-note", "account-team-attestation"].includes(item.authority))
      )
    ) {
      reasons.push("The status value line needs external evidence for a realized customer outcome.");
    }
  }
  if (proposal.claimClass === "actual" && !claimMatchedEvidence.length) {
    reasons.push("An actual cannot be supported only by targets, plans, risks, or opinions.");
  }
  if (
    sourceTypes.has("onenote") &&
    proposal.claimClass !== "mixed" &&
    claimMatchedEvidence.some((item) => item.sourceType === "onenote") &&
    claimMatchedEvidence.every((item) => item.sourceType === "onenote")
  ) {
    reasons.push("OneNote is corroboration-only and cannot be the sole evidence for a dashboard proposal.");
  }
  for (const item of evidence) {
    if (DATED_AUTHORITIES.has(item.authority) && !item.scopeDate) {
      reasons.push(`Evidence ${item.evidenceId} lacks the occurrence, modification, or as-of date required for ${item.authority}.`);
    }
    if (item.outsideWindow && !item.foundationalException) {
      reasons.push(`Evidence ${item.evidenceId} is outside the selected search window and was not explicitly selected as foundational.`);
    }
  }
  if (
    proposal.claimClass === "actual" &&
    proposal.targetPath !== "/timeline" &&
    evidence.some((item) => item.outsideWindow)
  ) {
    reasons.push("Outside-window foundational evidence cannot by itself establish a current actual.");
  }
  if (
    evidence.some((item) => item.authority === "customer-statement" && item.author.kind !== "customer")
  ) {
    reasons.push("Customer-statement authority requires authenticated customer authorship metadata.");
  }
  if (authorities.has("calendar-event")) {
    if (!["/timeline", "/executiveCadence/type", "/executiveCadence/date"].includes(proposal.targetPath)) {
      reasons.push("Calendar evidence can support only cadence or timeline occurrence.");
    }
    if (!evidenceClasses.has("meeting-scheduled")) {
      reasons.push("Calendar evidence must remain classified as meeting-scheduled.");
    }
  }
  if (authorities.has("public-web") && !allowedPublicWebTarget(proposal.targetPath)) {
    reasons.push("Public web evidence cannot support internal account facts or status.");
  }

  if (["/currentArr", "/soldProducts"].includes(proposal.targetPath)) {
    if (proposal.claimClass !== "actual") reasons.push("ARR and purchased products must be actuals.");
    if (![...claimMatchedAuthorities].some((item) => ["contract-order", "license-record"].includes(item))) {
      reasons.push("ARR and purchased products require same-claim contract, order, or license authority.");
    }
  }
  if (proposal.targetPath === "/renewalDate") {
    if (proposal.claimClass !== "actual") reasons.push("Renewal date must be classified as an actual.");
    if (![...claimMatchedAuthorities].some((item) => ["contract-order", "license-record", "validated-account-document"].includes(item))) {
      reasons.push("Renewal date requires same-claim dated contract, license, or validated account authority.");
    }
  }
  if (["/deploymentType", "/deliveryModel"].includes(proposal.targetPath)) {
    if (proposal.claimClass !== "actual") reasons.push("Deployment and delivery models must be explicit actuals.");
    if (![...claimMatchedAuthorities].some((item) => ["product-telemetry", "validated-account-document"].includes(item))) {
      reasons.push("Deployment and delivery models require same-claim system or validated account evidence.");
    }
  }
  if (/^\/metrics\/(?:savings|automations|agentic)\/value$/u.test(proposal.targetPath)) {
    if (proposal.claimClass !== "actual") reasons.push("Realized KPI values require actual evidence.");
    if (![...claimMatchedAuthorities].some((item) => ["product-telemetry", "validated-account-document"].includes(item))) {
      reasons.push("Realized KPI values require same-claim telemetry or a validated dated outcome record.");
    }
  }
  if (/^\/metrics\/utilization\//u.test(proposal.targetPath)) {
    if (proposal.claimClass !== "actual") reasons.push("Utilization must be an actual.");
    if (![...claimMatchedAuthorities].some((item) => ["product-telemetry", "validated-account-document"].includes(item))) {
      reasons.push("Utilization requires same-claim product telemetry or a validated dated usage record.");
    }
  }
  if (proposal.targetPath.startsWith("/consumptionPlan/") && proposal.targetPath !== PRODUCT_FORECAST_TARGET) {
    if (![...claimMatchedAuthorities].some((item) =>
      ["product-telemetry", "license-record", "contract-order", "validated-account-document"].includes(item))) {
      reasons.push("Consumption Plan data requires same-claim product telemetry, license, contract, or validated account evidence.");
    }
  }
  if (proposal.targetPath === PRODUCT_FORECAST_TARGET) {
    if (!attestationEvidence.length) {
      reasons.push("A product forecast update requires an account-team forecast attestation.");
    }
    if (!evidence.some((item) =>
      item.authority !== "account-team-attestation" &&
      ["product-telemetry", "license-record", "contract-order", "validated-account-document"].includes(item.authority))) {
      reasons.push("The forecasted product row requires independent product, license, contract, or validated account evidence.");
    }
  }
  if (
    proposal.claimClass === "actual" &&
    claimMatchedAuthorities.size > 0 &&
    [...claimMatchedAuthorities].every((authority) =>
      ["internal-operations", "personal-note"].includes(authority)) &&
    (
      proposal.targetPath === "/tagline" ||
      proposal.targetPath === "/statusSummary" ||
      proposal.targetPath.startsWith("/metrics/") ||
      proposal.targetPath === "/goals"
    )
  ) {
    reasons.push("Internal operations and personal notes cannot by themselves prove a realized customer outcome.");
  }
  if (
    attestationEvidence.length &&
    proposal.claimClass === "actual" &&
    !ATTESTATION_INTERNAL_ACTUAL_PATHS.some((pattern) => pattern.test(proposal.targetPath))
  ) {
    reasons.push("Account-team attestation cannot establish this actual.");
  }
  return reasons;
}

function uniqueReasons(reasons) {
  return [...new Set(reasons)];
}

async function strictValidateDashboard(dashboard) {
  const library = await getSalesforceLibrary();
  return library.validateDashboardInput(dashboard);
}

function contextualProposalId({ inputDigest, evidenceDigest, proposal, existingValue }) {
  const stable = {
    policyVersion: POLICY_VERSION,
    inputDigest,
    evidenceDigest,
    targetPath: proposal.targetPath,
    operation: proposal.operation,
    value: proposal.value,
    semanticKey: proposal.semanticKey,
    evidenceIds: proposal.evidenceIds,
    claimClass: proposal.claimClass,
    claimAnnotations: proposal.claimAnnotations.map((item) => ({
      locator: item.locator,
      claimClass: item.claimClass,
      evidenceIds: item.evidenceIds,
    })),
    rationale: proposal.rationale,
    position: proposal.position,
    currentValueDigest: digestObject(existingValue),
  };
  return `P-${sha256(stableStringify(stable)).slice(0, 20)}`;
}

export async function prepareProposals(dashboard, ledger, inputDigest) {
  const evidenceDigest = evidenceContextDigest(ledger);
  const prepared = [];

  for (const proposal of ledger.proposals) {
    const next = deepClone(proposal);
    const structuralReasons = [];
    let existingValue;
    let semanticKey = proposal.semanticKey;
    let duplicate = false;
    let noChange = false;
    let conflict = false;

    try {
      if (proposal.operation === "insert") {
        semanticKey = semanticRowKey(proposal.targetPath, proposal.value);
        if (!semanticKey) structuralReasons.push("Inserted row has no stable semantic key.");
        if (proposal.semanticKey && normalizedKey(proposal.semanticKey) !== semanticKey) {
          structuralReasons.push("Provided semanticKey does not match the inserted row.");
        }
        if (INSERT_TARGETS.has(proposal.targetPath)) {
          const target = dashboardAtArrayPath(dashboard, proposal.targetPath);
          duplicate = target.some((row) => semanticRowKey(proposal.targetPath, row) === semanticKey);
          if (
            Number.isInteger(proposal.position) &&
            proposal.position > target.length + 1
          ) {
            structuralReasons.push("Explicit insertion positions must be valid against the current array without relying on another proposal.");
          }
        }
      } else {
        existingValue = existingValueForProposal(dashboard, proposal);
        if (proposal.operation === "set") {
          noChange = stableStringify(existingValue) === stableStringify(proposal.value);
          conflict = !isBlankDashboardValue(existingValue) && !noChange;
        } else if (proposal.targetPath === "/motionAnswers") {
          if (!MOTION_QUESTIONS.has(proposal.semanticKey)) {
            structuralReasons.push("Motion answer semanticKey is not a canonical motion question.");
          }
          noChange = stableStringify(existingValue) === stableStringify(proposal.value);
          conflict = !isBlankDashboardValue(existingValue) && !noChange;
        } else if (proposal.targetPath === PRODUCT_FORECAST_TARGET) {
          const matches = matchingConsumptionProductRows(dashboard, proposal.semanticKey);
          if (matches.length !== 1) {
            structuralReasons.push(`Product forecast semantic update matched ${matches.length} rows; exactly one is required.`);
          } else {
            noChange = stableStringify(existingValue) === stableStringify(proposal.value);
            conflict = !noChange;
          }
        } else if (INSERT_TARGETS.has(proposal.targetPath)) {
          const matches = matchingRowIndexes(dashboard, proposal.targetPath, proposal.semanticKey);
          if (matches.length !== 1) {
            structuralReasons.push(`Semantic row update matched ${matches.length} rows; exactly one is required.`);
          } else {
            noChange = stableStringify(existingValue) === stableStringify(proposal.value);
            conflict = !noChange;
          }
        }
      }
    } catch (error) {
      structuralReasons.push(error instanceof Error ? error.message : String(error));
    }

    const candidate = { ...next, semanticKey };
    const reasons = uniqueReasons([
      ...structuralReasons,
      ...contentPolicyReasons(dashboard, candidate),
      ...authorityPolicyReasons(ledger, candidate),
    ]);
    if (!reasons.length && !duplicate) {
      try {
        const clone = deepClone(dashboard);
        applyTypedOperation(clone, candidate, { validationOnly: true });
        await strictValidateDashboard(clone);
      } catch (error) {
        reasons.push(`The proposed typed operation would violate schema 1.4: ${error.message}`);
      }
    }
    const proposalId = contextualProposalId({
      inputDigest,
      evidenceDigest,
      proposal: candidate,
      existingValue,
    });
    prepared.push({
      ...candidate,
      proposalId,
      existingValue: deepClone(existingValue),
      currentValueDigest: digestObject(existingValue),
      targetKey: proposalTargetKey(candidate),
      duplicate,
      noChange,
      conflict,
      pageOneVisible: pageOneVisibility(dashboard, candidate),
      disposition: reasons.length ? "rejected" : duplicate ? "duplicate" : noChange ? "no-change" : "eligible",
      reasons,
      evidence: proposalEvidence(ledger, candidate).map((item) => ({
        evidenceId: item.evidenceId,
        sourceType: item.sourceType,
        title: item.title,
        authorKind: item.author.kind,
        occurredAt: item.occurredAt,
        authority: item.authority,
        claimClass: item.claimClass,
        potentialPromptInjection: item.potentialPromptInjection,
      })),
    });
  }

  const proposalIds = prepared.map((proposal) => proposal.proposalId);
  if (new Set(proposalIds).size !== proposalIds.length) {
    throw new ContextEnricherError("PROPOSAL_ID_COLLISION", "Two contextual proposals resolved to the same stable ID.");
  }
  const byTarget = new Map();
  for (const proposal of prepared) {
    const group = byTarget.get(proposal.targetKey) ?? [];
    group.push(proposal);
    byTarget.set(proposal.targetKey, group);
  }
  for (const group of byTarget.values()) {
    const values = new Set(group.map((proposal) => stableStringify({
      operation: proposal.operation,
      value: proposal.value,
      position: proposal.position,
    })));
    if (group.length > 1 && values.size > 1) {
      for (const proposal of group) {
        proposal.disposition = "contradicted";
        proposal.reasons = uniqueReasons([
          ...proposal.reasons,
          "Multiple proposals disagree for the same scalar or semantic row.",
        ]);
      }
    }
  }
  const byPlacement = new Map();
  for (const proposal of prepared.filter((item) => item.operation === "insert" && Number.isInteger(item.position))) {
    const key = `${proposal.targetPath}|${proposal.position}`;
    const group = byPlacement.get(key) ?? [];
    group.push(proposal);
    byPlacement.set(key, group);
  }
  for (const group of byPlacement.values()) {
    if (group.length > 1) {
      for (const proposal of group) {
        proposal.disposition = "rejected";
        proposal.reasons = uniqueReasons([
          ...proposal.reasons,
          "Two row insertions request the same explicit array position.",
        ]);
      }
    }
  }
  return prepared;
}

function isBlankDashboardValue(value) {
  return value === undefined || value === null || (typeof value === "string" && value.trim() === "");
}

function pageOneVisibility(dashboard, proposal) {
  const limit = PAGE_ONE_VISIBLE_LIMITS.get(proposal.targetPath);
  if (!limit) {
    if (proposal.operation === "set") {
      return PAGE_ONE_SCALAR_PATHS.has(proposal.targetPath) ||
        proposal.targetPath.startsWith("/metrics/") ||
        proposal.targetPath.startsWith("/health/");
    }
    return false;
  }
  if (proposal.operation === "insert") {
    if (proposal.position === "append") {
      return dashboardAtArrayPath(dashboard, proposal.targetPath).length < limit;
    }
    return proposal.position <= limit;
  }
  if (proposal.operation === "update") {
    const indexes = matchingRowIndexes(dashboard, proposal.targetPath, proposal.semanticKey);
    return indexes.length === 1 ? indexes[0] < limit : null;
  }
  return null;
}

export async function readJsonFile(filePath, label, { maxBytes = 25 * 1024 * 1024 } = {}) {
  const resolved = path.resolve(filePath);
  let fileStat;
  try {
    fileStat = await stat(resolved);
  } catch (error) {
    throw new ContextEnricherError("FILE_READ_FAILED", `${label} could not be read: ${error.message}`);
  }
  if (!fileStat.isFile()) {
    throw new ContextEnricherError("FILE_READ_FAILED", `${label} must be a regular file.`);
  }
  if (fileStat.size > maxBytes) {
    throw new ContextEnricherError("FILE_TOO_LARGE", `${label} exceeds the ${maxBytes}-byte safety limit.`);
  }
  let raw;
  try {
    raw = await readFile(resolved, "utf8");
  } catch (error) {
    throw new ContextEnricherError("FILE_READ_FAILED", `${label} could not be read: ${error.message}`);
  }
  try {
    return JSON.parse(raw);
  } catch (error) {
    throw new ContextEnricherError("INVALID_JSON", `${label} is not valid JSON: ${error.message}`);
  }
}

export async function loadDashboard(filePath) {
  const value = await readJsonFile(filePath, "Dashboard input");
  await strictValidateDashboard(value);
  return value;
}

async function assertPrivateArtifact(filePath, label) {
  const resolved = path.resolve(filePath);
  const fileInfo = await lstat(resolved);
  if (!fileInfo.isFile() || fileInfo.isSymbolicLink()) {
    throw new ContextEnricherError("INSECURE_ARTIFACT", `${label} must be a regular, non-symlink file.`);
  }
  if (process.platform !== "win32" && (fileInfo.mode & 0o077) !== 0) {
    throw new ContextEnricherError(
      "INSECURE_PERMISSIONS",
      `${label} exposes group or other permission bits; set mode 0600 before use.`,
    );
  }
  if (process.platform !== "win32") {
    const directoryInfo = await stat(path.dirname(resolved));
    if ((directoryInfo.mode & 0o077) !== 0) {
      throw new ContextEnricherError(
        "INSECURE_PERMISSIONS",
        `${label} is stored in a group- or other-accessible directory; use a mode 0700 working directory.`,
      );
    }
  }
}

export async function loadAttestationBundle(filePath) {
  await assertPrivateArtifact(filePath, "Attestation bundle");
  return validateAttestationBundle(await readJsonFile(filePath, "Attestation bundle"));
}

export async function loadClarificationAnswersFile(filePath) {
  await assertPrivateArtifact(filePath, "Clarification answers");
  return readJsonFile(filePath, "Clarification answers");
}

export async function loadEvidenceLedger(filePath, { attestations = null } = {}) {
  await assertPrivateArtifact(filePath, "Evidence ledger");
  return normalizeEvidenceLedger(await readJsonFile(filePath, "Evidence ledger"), { attestations });
}

function normalizeSalesforceDateTime(value, target) {
  const original = requireString(value, target);
  const normalized = original.replace(/([+-]\d{2})(\d{2})$/u, "$1:$2");
  requireIsoDateTime(normalized, target);
  assertNotFuture(normalized, target, Date.now(), MAX_SOURCE_CLOCK_SKEW_MS);
  return { original, normalized };
}

export async function loadSalesforceMappingReceipt(reportPath) {
  await assertPrivateArtifact(reportPath, "Salesforce child mapping report");
  const value = await readJsonFile(reportPath, "Salesforce child mapping report");
  assertExactKeys(value, [
    "kind",
    "confidential",
    "builtAt",
    "dashboardSchemaVersion",
    "accountId",
    "org",
    "sourceLastModifiedDate",
    "fieldMapVersion",
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
  ], "Salesforce child mapping report");
  if (
    value.kind !== SALESFORCE_REPORT_KIND ||
    value.confidential !== true ||
    value.dashboardSchemaVersion !== DASHBOARD_SCHEMA_VERSION
  ) {
    throw new ContextEnricherError("INVALID_SALESFORCE_RECEIPT", "The Salesforce child mapping report kind or schema is invalid.");
  }
  const builtAt = requireIsoDateTime(value.builtAt, "Salesforce child mapping report builtAt");
  assertNotFuture(builtAt, "Salesforce child mapping report builtAt");
  const accountId = requireString(value.accountId, "Salesforce child mapping report accountId");
  if (!ACCOUNT_ID_PATTERN.test(accountId)) {
    throw new ContextEnricherError("INVALID_SALESFORCE_RECEIPT", "The Salesforce child mapping report has an invalid Account ID.");
  }
  assertExactKeys(value.org, ["username", "orgId", "alias"], "Salesforce child mapping report org");
  const orgId = requireString(value.org.orgId, "Salesforce child mapping report org.orgId");
  const fieldMapVersion = requireString(value.fieldMapVersion, "Salesforce child mapping report fieldMapVersion");
  if (fieldMapVersion !== SALESFORCE_FIELD_MAP_VERSION) {
    throw new ContextEnricherError(
      "INVALID_SALESFORCE_RECEIPT",
      `The Salesforce child mapping report uses unsupported field map ${JSON.stringify(fieldMapVersion)}.`,
    );
  }
  const sourceLastModifiedDate = normalizeSalesforceDateTime(
    value.sourceLastModifiedDate,
    "Salesforce child mapping report sourceLastModifiedDate",
  ).original;
  const dashboardOutput = await canonicalPath(
    requireString(value.dashboardOutput, "Salesforce child mapping report dashboardOutput"),
  );
  const reportOutput = await canonicalPath(
    requireString(value.reportOutput, "Salesforce child mapping report reportOutput"),
  );
  const canonicalReportPath = await canonicalPath(reportPath);
  if (reportOutput !== canonicalReportPath) {
    throw new ContextEnricherError(
      "INVALID_SALESFORCE_RECEIPT",
      "The Salesforce child mapping report does not identify its own canonical path.",
    );
  }
  return {
    path: canonicalReportPath,
    digest: digestObject(value),
    accountId,
    orgId,
    fieldMapVersion,
    sourceLastModifiedDate,
    dashboardOutput,
  };
}

export async function canonicalPath(filePath) {
  const resolved = path.resolve(filePath);
  let current = resolved;
  const suffix = [];
  while (true) {
    try {
      const canonicalAncestor = await realpath(current);
      if (suffix.length) {
        const ancestorInfo = await stat(canonicalAncestor);
        if (!ancestorInfo.isDirectory()) {
          throw new ContextEnricherError(
            "UNSAFE_PATH",
            `A non-directory path component cannot contain the requested target: ${canonicalAncestor}.`,
          );
        }
      }
      return path.join(canonicalAncestor, ...suffix);
    } catch (error) {
      if (error instanceof ContextEnricherError) throw error;
      try {
        const existingInfo = await lstat(current);
        if (existingInfo.isSymbolicLink()) {
          throw new ContextEnricherError(
            "UNSAFE_PATH",
            `Refusing an unresolved or dangling symbolic-link path component: ${current}.`,
          );
        }
        throw new ContextEnricherError(
          "PATH_RESOLUTION_FAILED",
          `Could not resolve existing path component ${current}: ${error.message}`,
        );
      } catch (lstatError) {
        if (lstatError instanceof ContextEnricherError) throw lstatError;
        if (!["ENOENT", "ENOTDIR"].includes(lstatError?.code)) {
          throw new ContextEnricherError(
            "PATH_RESOLUTION_FAILED",
            `Could not inspect path component ${current}: ${lstatError.message}`,
          );
        }
      }
      const parent = path.dirname(current);
      if (parent === current) {
        throw new ContextEnricherError("PATH_RESOLUTION_FAILED", `Could not resolve ${resolved}.`);
      }
      suffix.unshift(path.basename(current));
      current = parent;
    }
  }
}

async function sameFile(left, right) {
  try {
    const [leftStat, rightStat] = await Promise.all([stat(left), stat(right)]);
    return leftStat.dev === rightStat.dev && leftStat.ino === rightStat.ino;
  } catch {
    return false;
  }
}

function isWithin(candidate, parent) {
  const relative = path.relative(parent, candidate);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

export async function assertSafeDerivedTargets(targets, protectedPaths) {
  const canonicalProtected = [];
  for (const protectedPath of protectedPaths.filter(Boolean)) {
    canonicalProtected.push(await canonicalPath(protectedPath));
  }
  const canonicalSkill = await canonicalPath(SKILL_DIRECTORY);
  const canonicalTargets = [];
  for (const target of targets) {
    const canonicalTarget = await canonicalPath(target);
    if (isWithin(canonicalTarget, canonicalSkill)) {
      throw new ContextEnricherError("PROTECTED_PATH", `Derived output cannot be written inside the installed skill: ${canonicalTarget}`);
    }
    for (const protectedPath of canonicalProtected) {
      if (canonicalTarget === protectedPath || await sameFile(target, protectedPath)) {
        throw new ContextEnricherError("PROTECTED_PATH", `Derived output collides with protected input ${protectedPath}.`);
      }
    }
    canonicalTargets.push(canonicalTarget);
  }
  if (new Set(canonicalTargets).size !== canonicalTargets.length) {
    throw new ContextEnricherError("OUTPUT_COLLISION", "Two derived output paths resolve to the same target.");
  }
  for (let left = 0; left < targets.length; left += 1) {
    for (let right = left + 1; right < targets.length; right += 1) {
      if (await sameFile(targets[left], targets[right])) {
        throw new ContextEnricherError("OUTPUT_COLLISION", "Two derived outputs are hard links to the same file.");
      }
    }
  }
}

async function pathExists(filePath) {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function ensurePrivateDirectory(directory) {
  const existed = await pathExists(directory);
  await mkdir(directory, { recursive: true, mode: 0o700 });
  if (!existed) await chmod(directory, 0o700);
  if (process.platform !== "win32") {
    const directoryInfo = await stat(directory);
    if ((directoryInfo.mode & 0o077) !== 0) {
      throw new ContextEnricherError(
        "INSECURE_PERMISSIONS",
        `Derived outputs require a mode 0700 directory: ${directory}.`,
      );
    }
  }
}

async function verifyOverwriteCandidate(filePath, kind) {
  if (!await pathExists(filePath)) return;
  if (kind === "preview" || kind === "dashboard") {
    const value = await readJsonFile(filePath, "Existing derived output");
    if (kind === "preview" && value.kind !== PREVIEW_KIND) {
      throw new ContextEnricherError("UNSAFE_OVERWRITE", "The existing preview target is not a prior Day 2 context preview.");
    }
    if (
      kind === "dashboard" &&
      (
        value.schemaVersion !== DASHBOARD_SCHEMA_VERSION ||
        !String(value.sourceNotes ?? "").includes("[DAY2-EVIDENCE:")
      )
    ) {
      throw new ContextEnricherError("UNSAFE_OVERWRITE", "The existing dashboard target is not a prior contextual build.");
    }
    return;
  }
  const content = await readFile(filePath, "utf8");
  if (!content.startsWith(`<!-- ${REPORT_KIND} -->\n`)) {
    throw new ContextEnricherError("UNSAFE_OVERWRITE", "The existing report target is not a prior Day 2 evidence report.");
  }
}

async function atomicWrite(filePath, content, { overwrite = false, kind }) {
  const resolved = path.resolve(filePath);
  await ensurePrivateDirectory(path.dirname(resolved));
  if (await pathExists(resolved)) {
    if (!overwrite) {
      throw new ContextEnricherError("OUTPUT_EXISTS", `Refusing to overwrite existing file ${resolved}.`);
    }
    await verifyOverwriteCandidate(resolved, kind);
    const targetInfo = await lstat(resolved);
    if (!targetInfo.isFile() || targetInfo.isSymbolicLink()) {
      throw new ContextEnricherError("UNSAFE_OVERWRITE", `Refusing to overwrite non-regular target ${resolved}.`);
    }
  }

  const temporary = path.join(
    path.dirname(resolved),
    `.${path.basename(resolved)}.${process.pid}.${randomBytes(8).toString("hex")}.tmp`,
  );
  await writeFile(temporary, content, { encoding: "utf8", flag: "wx", mode: 0o600 });
  await chmod(temporary, 0o600);
  try {
    if (overwrite && await pathExists(resolved)) {
      const before = await lstat(resolved);
      if (!before.isFile() || before.isSymbolicLink()) {
        throw new ContextEnricherError("UNSAFE_OVERWRITE", `Target changed before overwrite: ${resolved}.`);
      }
      await rename(temporary, resolved);
    } else {
      await link(temporary, resolved);
      await unlink(temporary);
    }
    await chmod(resolved, 0o600);
  } catch (error) {
    await unlink(temporary).catch(() => {});
    if (error?.code === "EEXIST") {
      throw new ContextEnricherError("OUTPUT_EXISTS", `Refusing to overwrite existing file ${resolved}.`);
    }
    throw error;
  }
  return resolved;
}

export async function writeJsonAtomic(filePath, value, options = {}) {
  return atomicWrite(filePath, `${JSON.stringify(value, null, 2)}\n`, { ...options, kind: options.kind ?? "preview" });
}

export async function writeTextAtomic(filePath, value, options = {}) {
  return atomicWrite(filePath, value, { ...options, kind: options.kind ?? "report" });
}

async function preparePairEntry(filePath, content, { overwrite, kind }) {
  const resolved = path.resolve(filePath);
  await ensurePrivateDirectory(path.dirname(resolved));
  let targetInfo;
  try {
    targetInfo = await lstat(resolved);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  if (targetInfo) {
    if (!overwrite) {
      throw new ContextEnricherError("OUTPUT_EXISTS", `Refusing to overwrite existing file ${resolved}.`);
    }
    if (!targetInfo.isFile() || targetInfo.isSymbolicLink()) {
      throw new ContextEnricherError("UNSAFE_OVERWRITE", `Refusing to overwrite non-regular target ${resolved}.`);
    }
    await verifyOverwriteCandidate(resolved, kind);
  }
  const temporary = path.join(
    path.dirname(resolved),
    `.${path.basename(resolved)}.${process.pid}.${randomBytes(8).toString("hex")}.tmp`,
  );
  await writeFile(temporary, content, { encoding: "utf8", flag: "wx", mode: 0o600 });
  await chmod(temporary, 0o600);
  return {
    resolved,
    temporary,
    existed: Boolean(targetInfo),
    originalDevice: targetInfo?.dev,
    originalInode: targetInfo?.ino,
    backup: "",
    committed: false,
  };
}

async function writeDerivedPairAtomic(entries, { overwrite }) {
  const prepared = [];
  try {
    for (const entry of entries) {
      prepared.push(await preparePairEntry(entry.filePath, entry.content, {
        overwrite,
        kind: entry.kind,
      }));
    }
    for (const entry of prepared.filter((item) => item.existed)) {
      const current = await lstat(entry.resolved);
      if (
        !current.isFile() ||
        current.isSymbolicLink() ||
        current.dev !== entry.originalDevice ||
        current.ino !== entry.originalInode
      ) {
        throw new ContextEnricherError("UNSAFE_OVERWRITE", `Target changed before commit: ${entry.resolved}.`);
      }
      entry.backup = path.join(
        path.dirname(entry.resolved),
        `.${path.basename(entry.resolved)}.${process.pid}.${randomBytes(8).toString("hex")}.bak`,
      );
      await link(entry.resolved, entry.backup);
    }
    for (const entry of prepared) {
      if (entry.existed) {
        await rename(entry.temporary, entry.resolved);
      } else {
        await link(entry.temporary, entry.resolved);
        await unlink(entry.temporary);
      }
      entry.committed = true;
      await chmod(entry.resolved, 0o600);
    }
  } catch (error) {
    const rollbackFailures = [];
    for (const entry of [...prepared].reverse()) {
      if (entry.committed) {
        if (entry.existed && entry.backup) {
          try {
            await rename(entry.backup, entry.resolved);
            entry.backup = "";
          } catch (rollbackError) {
            rollbackFailures.push(`${entry.resolved}: ${rollbackError.message}; backup preserved at ${entry.backup}`);
          }
        } else {
          try {
            await unlink(entry.resolved);
          } catch (rollbackError) {
            rollbackFailures.push(`${entry.resolved}: ${rollbackError.message}`);
          }
        }
      }
      await unlink(entry.temporary).catch(() => {});
      if (entry.backup && !entry.committed) await unlink(entry.backup).catch(() => {});
    }
    if (rollbackFailures.length) {
      throw new ContextEnricherError(
        "ATOMIC_ROLLBACK_FAILED",
        `Derived-output commit failed and rollback needs manual recovery. ${rollbackFailures.join(" | ")}`,
      );
    }
    if (error?.code === "EEXIST") {
      throw new ContextEnricherError("OUTPUT_EXISTS", "A derived output appeared before the atomic pair commit.");
    }
    throw error;
  }
  for (const entry of prepared) {
    await unlink(entry.temporary).catch(() => {});
    if (entry.backup) await unlink(entry.backup).catch(() => {});
  }
  return prepared.map((entry) => entry.resolved);
}

function sameSalesforceAccountId(left, right) {
  return left === right || (
    [left.length, right.length].sort((a, b) => a - b).join(",") === "15,18" &&
    left.slice(0, 15) === right.slice(0, 15)
  );
}

function parseSalesforceProvenance(sourceNotes) {
  const pattern = /\[Salesforce provenance: ([^|\]\n]+) \| (001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?) \| ([^\]\n]+)\]\n([\s\S]*?)\n\[\/Salesforce provenance\]/gu;
  const matches = [...String(sourceNotes ?? "").matchAll(pattern)];
  if (!matches.length) {
    throw new ContextEnricherError(
      "SALESFORCE_BASE_REQUIRED",
      "The contextual base must contain provenance produced by the Salesforce child skill.",
    );
  }
  return matches.map((match) => {
    const [, fieldMapVersion, markerAccountId, markerLastModifiedDate, body] = match;
    const normalizedFieldMapVersion = fieldMapVersion.trim();
    if (normalizedFieldMapVersion !== SALESFORCE_FIELD_MAP_VERSION) {
      throw new ContextEnricherError(
        "SALESFORCE_BASE_STALE",
        `The Salesforce base uses ${JSON.stringify(normalizedFieldMapVersion)}; expected ${SALESFORCE_FIELD_MAP_VERSION}.`,
      );
    }
    normalizeSalesforceDateTime(markerLastModifiedDate.trim(), "Salesforce provenance LastModifiedDate");
    const idLine = body.match(/^- Account\.Id = (.+)$/mu);
    const modifiedLine = body.match(/^- Account\.LastModifiedDate = (.+)$/mu);
    const nameLine = body.match(/^- Account\.Name = (.+)$/mu);
    let lineAccountId;
    let lineLastModifiedDate;
    let lineAccountName;
    try {
      lineAccountId = idLine ? JSON.parse(idLine[1]) : undefined;
      lineLastModifiedDate = modifiedLine ? JSON.parse(modifiedLine[1]) : undefined;
      lineAccountName = nameLine ? JSON.parse(nameLine[1]) : undefined;
    } catch {
      throw new ContextEnricherError("SALESFORCE_BASE_REQUIRED", "A Salesforce provenance block contains invalid JSON values.");
    }
    if (
      typeof lineAccountId !== "string" ||
      !sameSalesforceAccountId(lineAccountId, markerAccountId) ||
      lineLastModifiedDate !== markerLastModifiedDate.trim()
    ) {
      throw new ContextEnricherError(
        "SALESFORCE_BASE_REQUIRED",
        "A Salesforce provenance marker does not match its Account.Id and Account.LastModifiedDate entries.",
      );
    }
    return {
      fieldMapVersion: normalizedFieldMapVersion,
      accountId: markerAccountId,
      accountLastModifiedDate: markerLastModifiedDate.trim(),
      accountName: typeof lineAccountName === "string" ? lineAccountName : "",
    };
  });
}

function validateDashboardIdentity(dashboard, ledger, salesforceReceipt) {
  if (!hasText(dashboard.customerName)) {
    throw new ContextEnricherError(
      "MISSING_CUSTOMER_IDENTITY",
      "Run the Salesforce child skill first; contextual enrichment requires a populated customerName.",
    );
  }
  const provenances = parseSalesforceProvenance(dashboard.sourceNotes);
  if (provenances.some((item) => !sameSalesforceAccountId(item.accountId, ledger.account.salesforceAccountId))) {
    throw new ContextEnricherError(
      "SALESFORCE_ACCOUNT_MISMATCH",
      "At least one Salesforce child provenance block belongs to a different Account ID.",
    );
  }
  const matching = provenances.filter((item) =>
    sameSalesforceAccountId(item.accountId, salesforceReceipt.accountId) &&
    item.fieldMapVersion === salesforceReceipt.fieldMapVersion &&
    item.accountLastModifiedDate === salesforceReceipt.sourceLastModifiedDate);
  if (matching.length !== 1) {
    throw new ContextEnricherError(
      "SALESFORCE_BASE_STALE",
      "The dashboard does not contain exactly one Salesforce provenance block matching the supplied child mapping report.",
    );
  }
  const salesforceName = matching[0].accountName;
  if (!hasText(salesforceName)) {
    throw new ContextEnricherError(
      "SALESFORCE_BASE_REQUIRED",
      "The current Salesforce provenance block must contain Account.Name.",
    );
  }
  if (
    dashboard.customerName !== salesforceName ||
    ledger.account.canonicalName !== salesforceName
  ) {
    throw new ContextEnricherError(
      "CUSTOMER_NAME_MISMATCH",
      "Dashboard customerName and ledger.account.canonicalName must both match the current Salesforce Account.Name.",
    );
  }
  if (
    !sameSalesforceAccountId(salesforceReceipt.accountId, ledger.account.salesforceAccountId) ||
    salesforceReceipt.orgId !== ledger.account.salesforceOrgId
  ) {
    throw new ContextEnricherError(
      "SALESFORCE_RECEIPT_MISMATCH",
      "The Salesforce child mapping report org or Account ID does not match the evidence ledger.",
    );
  }
  return matching[0];
}

function findUnsubstantiatedGreens(dashboard, acceptedProposals = []) {
  const supportedStatusPaths = new Set(
    acceptedProposals
      .filter((proposal) =>
        /^\/health\/[^/]+\/status$/u.test(proposal.targetPath) && proposal.value === "Green")
      .map((proposal) => proposal.targetPath),
  );
  const warnings = [];
  for (const key of HEALTH_KEYS) {
    const item = dashboard.health[key];
    const statusPath = `/health/${key}/status`;
    if (item.status === "Green" && !hasText(item.evidence) && !supportedStatusPaths.has(statusPath)) {
      warnings.push(statusPath);
    }
  }
  return warnings;
}

function proposalDigest(proposals) {
  return digestObject(proposals.map((proposal) => ({
    proposalId: proposal.proposalId,
    targetPath: proposal.targetPath,
    operation: proposal.operation,
    value: proposal.value,
    semanticKey: proposal.semanticKey,
    evidenceIds: proposal.evidenceIds,
    claimClass: proposal.claimClass,
    claimAnnotations: proposal.claimAnnotations,
    rationale: proposal.rationale,
    position: proposal.position,
    existingValue: proposal.existingValue,
    currentValueDigest: proposal.currentValueDigest,
    targetKey: proposal.targetKey,
    duplicate: proposal.duplicate,
    noChange: proposal.noChange,
    conflict: proposal.conflict,
    pageOneVisible: proposal.pageOneVisible,
    disposition: proposal.disposition,
    reasons: proposal.reasons,
  })));
}

function previewIntegrityPayload(preview) {
  const { integrityDigest: _integrityDigest, ...payload } = preview;
  return payload;
}

function dashboardMeaningPresent(dashboard, targetPath) {
  if (targetPath === "/health") {
    return [...HEALTH_KEYS].every((key) => {
      const item = dashboard.health[key];
      return item.status && hasText(item.evidence) &&
        (item.status !== "Red" || hasText(item.mitigation) && hasText(item.owner));
    });
  }
  if (targetPath === "/motionAnswers") {
    const questions = MOTION_QUESTION_GROUPS[dashboard.motion] ?? [];
    return questions.length > 0 && questions.every((question) => hasText(dashboard.motionAnswers[question]));
  }
  if (targetPath === "/metrics/utilization") {
    return [...UTILIZATION_KEYS].every((key) => hasText(dashboard.metrics.utilization[key]));
  }
  if (targetPath === "/statusSummary") return lines(dashboard.statusSummary).length === 4;
  if (targetPath === PRODUCT_FORECAST_TARGET) {
    return dashboard.consumptionPlan.groups.some((group) =>
      group.rows.some((row) => Object.values(row.forecast).some(hasText) || hasText(row.comments)));
  }
  const value = pointerGet(dashboard, targetPath);
  if (Array.isArray(value)) return value.length > 0;
  return isPlainObject(value) ? Object.values(value).some(hasText) : hasText(value);
}

function proposalCoversTarget(proposals, targetPath) {
  return proposals.some((proposal) =>
    ["eligible", "no-change"].includes(proposal.disposition) &&
    (
      proposal.targetPath === targetPath ||
      targetPath.endsWith("/utilization") && proposal.targetPath.startsWith(`${targetPath}/`) ||
      targetPath === "/health" && proposal.targetPath.startsWith("/health/")
    ));
}

function attestationStatusByPolicy(attestations) {
  return new Map((attestations?.records ?? []).map((record) => [record.policyKey, record]));
}

export function createQuestionPlan({
  dashboard,
  proposals,
  inputDigest,
  sourceEvidenceDigest,
  attestations = null,
}) {
  const answeredByPolicy = attestationStatusByPolicy(attestations);
  const resolved = new Set();
  for (const [policyKey, policy] of Object.entries(FIELD_POLICY_MAP)) {
    if (answeredByPolicy.has(policyKey)) {
      resolved.add(policyKey);
      continue;
    }
    if (
      policy.targetPaths.length &&
      policy.targetPaths.every((targetPath) =>
        dashboardMeaningPresent(dashboard, targetPath) || proposalCoversTarget(proposals, targetPath))
    ) {
      resolved.add(policyKey);
    }
  }
  const decisionCriticalKeys = Object.entries(FIELD_POLICY_MAP)
    .filter(([, policy]) => ["source-location", "executive"].includes(policy.phase))
    .map(([key]) => key);
  const decisionCriticalComplete = decisionCriticalKeys.every((key) => resolved.has(key));
  const optionalGate = answeredByPolicy.get("optionalPass");
  const optionalEnabled = optionalGate?.status === "answered" && /^yes\b/iu.test(optionalGate.response.trim());
  const optionalDeclined = optionalGate && !optionalEnabled;
  const questions = [];
  for (const [policyKey, policy] of Object.entries(FIELD_POLICY_MAP)) {
    if (resolved.has(policyKey)) continue;
    if (policy.dependencies.some((dependency) => !resolved.has(dependency))) continue;
    if (policy.phase === "optional-gate" && !decisionCriticalComplete) continue;
    if (["supporting", "optional"].includes(policy.phase) && !optionalEnabled) continue;
    if (optionalDeclined && ["supporting", "optional", "optional-gate"].includes(policy.phase)) continue;
    const questionId = questionIdFor(policyKey, inputDigest, sourceEvidenceDigest);
    questions.push({
      questionId,
      policyKey,
      phase: policy.phase,
      priority: policy.priority,
      optional: ["supporting", "optional", "optional-gate"].includes(policy.phase),
      pageOneVisible: policy.pageOneVisible,
      prompt: policy.questionTemplate,
      why: policy.intent,
      targetPaths: policy.targetPaths,
      attestationEligible: policy.attestationEligible,
      dependencies: policy.dependencies,
    });
  }
  questions.sort((left, right) => left.priority - right.priority || left.questionId.localeCompare(right.questionId));
  const payload = {
    kind: QUESTION_PLAN_KIND,
    questions,
    nextQuestionIds: questions.slice(0, 3).map((item) => item.questionId),
    summary: {
      decisionCriticalComplete,
      optionalOffered: Boolean(optionalGate) || questions.some((item) => item.policyKey === "optionalPass"),
      optionalEnabled,
      accepted: (attestations?.records ?? []).filter((item) => item.status === "answered").length,
      skipped: (attestations?.records ?? []).filter((item) => item.status === "skipped").length,
      unknown: (attestations?.records ?? []).filter((item) => item.status === "unknown").length,
      unresolved: questions.length,
    },
  };
  payload.digest = digestObject(payload);
  return payload;
}

function validateQuestionPlan(plan, inputDigest, sourceEvidenceDigest) {
  assertExactKeys(plan, ["kind", "questions", "nextQuestionIds", "summary", "digest"], "preview.questionPlan");
  if (plan.kind !== QUESTION_PLAN_KIND || plan.digest !== digestObject({
    kind: plan.kind,
    questions: plan.questions,
    nextQuestionIds: plan.nextQuestionIds,
    summary: plan.summary,
  })) {
    throw new ContextEnricherError("QUESTION_PLAN_TAMPERED", "Question plan kind or digest is invalid.");
  }
  if (!Array.isArray(plan.questions) || plan.nextQuestionIds.length > 3) {
    throw new ContextEnricherError("INVALID_QUESTION_PLAN", "Question plan must contain questions and at most three next IDs.");
  }
  const ids = new Set();
  for (const question of plan.questions) {
    assertExactKeys(question, [
      "questionId",
      "policyKey",
      "phase",
      "priority",
      "optional",
      "pageOneVisible",
      "prompt",
      "why",
      "targetPaths",
      "attestationEligible",
      "dependencies",
    ], "preview.questionPlan.questions[]");
    const expectedId = questionIdFor(question.policyKey, inputDigest, sourceEvidenceDigest);
    if (question.questionId !== expectedId || ids.has(question.questionId)) {
      throw new ContextEnricherError("INVALID_QUESTION_PLAN", "Question IDs must be unique exact Q- IDs.");
    }
    if (!FIELD_POLICY_MAP[question.policyKey]) {
      throw new ContextEnricherError("INVALID_QUESTION_PLAN", "Question policy key is unknown.");
    }
    ids.add(question.questionId);
  }
  if (plan.nextQuestionIds.some((id) => !ids.has(id))) {
    throw new ContextEnricherError("INVALID_QUESTION_PLAN", "nextQuestionIds contains an unknown question.");
  }
  return plan;
}

function normalizeClarificationAnswers(value, preview) {
  assertExactKeys(value, ["kind", "previewDigest", "answeredAt", "answers"], "answers");
  if (value.kind !== CLARIFICATION_ANSWERS_KIND) {
    throw new ContextEnricherError("INVALID_ANSWERS", `Expected ${CLARIFICATION_ANSWERS_KIND}.`);
  }
  if (value.previewDigest !== preview.integrityDigest) {
    throw new ContextEnricherError("STALE_QUESTION_PLAN", "Answers are not bound to the current preview.");
  }
  const answeredAt = requireIsoDateTime(value.answeredAt, "answers.answeredAt");
  assertNotFuture(answeredAt, "answers.answeredAt");
  if (Date.parse(answeredAt) <= Date.parse(preview.createdAt)) {
    throw new ContextEnricherError("STALE_QUESTION_PLAN", "answers.answeredAt must be later than preview.createdAt.");
  }
  if (!Array.isArray(value.answers) || value.answers.length < 1 || value.answers.length > 3) {
    throw new ContextEnricherError("INVALID_ANSWERS", "Each clarification round must answer one to three questions.");
  }
  const questionById = new Map(preview.questionPlan.questions.map((item) => [item.questionId, item]));
  const allowedNext = new Set(preview.questionPlan.nextQuestionIds);
  const seen = new Set();
  const answers = value.answers.map((answer, index) => {
    const target = `answers.answers[${index}]`;
    assertExactKeys(answer, ["questionId", "status", "response"], target);
    const questionId = requireString(answer.questionId, `${target}.questionId`);
    if (!allowedNext.has(questionId) || !questionById.has(questionId) || seen.has(questionId)) {
      throw new ContextEnricherError("FORGED_QUESTION_ID", `${target}.questionId is not an unanswered question in the current three-question batch.`);
    }
    seen.add(questionId);
    const status = requireString(answer.status, `${target}.status`);
    if (!ANSWER_STATUSES.has(status)) throw new ContextEnricherError("INVALID_ANSWERS", `${target}.status is unsupported.`);
    const policy = FIELD_POLICY_MAP[questionById.get(questionId).policyKey];
    const response = requireString(answer.response, `${target}.response`, {
      allowBlank: status !== "answered",
      max: policy.characterLimit ?? 4_000,
    });
    if (status !== "answered" && response) {
      throw new ContextEnricherError("INVALID_ANSWERS", `${target}.response must be blank for ${status}.`);
    }
    return { questionId, status, response, question: questionById.get(questionId) };
  });
  return { answeredAt, answers };
}

async function assertClarificationPreviewCurrent(preview) {
  const dashboard = await loadDashboard(preview.input.path);
  if (digestObject(dashboard) !== preview.input.digest) {
    throw new ContextEnricherError("STALE_INPUT", "Clarification dashboard input changed after preview.");
  }
  const attestations = preview.attestations.path
    ? await loadAttestationBundle(preview.attestations.path)
    : null;
  if (attestations && attestations.integrityDigest !== preview.attestations.digest) {
    throw new ContextEnricherError("STALE_ATTESTATION", "Clarification attestations changed after preview.");
  }
  const ledger = await loadEvidenceLedger(preview.evidence.path, { attestations });
  if (
    evidenceLedgerDigest(ledger) !== preview.evidence.digest ||
    evidenceContextDigest(ledger) !== preview.evidence.contextDigest
  ) {
    throw new ContextEnricherError("STALE_EVIDENCE", "Clarification evidence changed after preview.");
  }
  const proposals = await prepareProposals(dashboard, ledger, preview.input.digest);
  if (
    proposalDigest(proposals) !== preview.proposalDigest ||
    stableStringify(proposals) !== stableStringify(preview.proposals)
  ) {
    throw new ContextEnricherError("STALE_PREVIEW", "Clarification proposals do not match the current dashboard and evidence.");
  }
  const canonicalPlan = createQuestionPlan({
    dashboard,
    proposals,
    inputDigest: preview.input.digest,
    sourceEvidenceDigest: preview.evidence.contextDigest,
    attestations,
  });
  if (stableStringify(canonicalPlan) !== stableStringify(preview.questionPlan)) {
    throw new ContextEnricherError(
      "QUESTION_PLAN_TAMPERED",
      "Question order, dependencies, or the current three-question batch is not canonical.",
    );
  }
}

export async function createAttestationBundle({
  preview,
  answers,
  priorAttestations = null,
  createdAt = answers.answeredAt,
}) {
  validatePreviewDocument(preview);
  await assertClarificationPreviewCurrent(preview);
  const normalizedAnswers = normalizeClarificationAnswers(answers, preview);
  const prior = priorAttestations ? validateAttestationBundle(priorAttestations) : null;
  const bindings = {
    salesforceOrgId: preview.account.salesforceOrgId,
    salesforceAccountId: preview.account.salesforceAccountId,
    canonicalName: preview.account.canonicalName,
  };
  if (prior && (
    stableStringify(prior.account) !== stableStringify(bindings) ||
    prior.inputDigest !== preview.input.digest ||
    prior.sourceEvidenceDigest !== preview.evidence.contextDigest
  )) {
    throw new ContextEnricherError("STALE_ATTESTATION", "Prior attestations do not match the current account, dashboard, or source evidence.");
  }
  const records = [...(prior?.records ?? [])];
  const priorQuestions = new Set(records.map((item) => item.questionId));
  for (const answer of normalizedAnswers.answers) {
    if (priorQuestions.has(answer.questionId)) {
      throw new ContextEnricherError("DUPLICATE_ATTESTATION", `Question ${answer.questionId} was already recorded.`);
    }
    const policy = FIELD_POLICY_MAP[answer.question.policyKey];
    const responseDigest = digestObject({ status: answer.status, response: answer.response });
    records.push({
      ref: `A-${sha256(stableStringify({
        questionId: answer.questionId,
        status: answer.status,
        responseDigest,
        answeredAt: normalizedAnswers.answeredAt,
      })).slice(0, 20)}`,
      questionId: answer.questionId,
      policyKey: answer.question.policyKey,
      status: answer.status,
      response: answer.response,
      responseDigest,
      answeredAt: normalizedAnswers.answeredAt,
      questionPlanDigest: preview.questionPlan.digest,
      allowedTargetPaths: policy.attestationEligible ? policy.targetPaths : [],
      allowedClaimClasses: policy.attestationEligible ? [...ATTESTATION_CLAIM_CLASSES].sort() : [],
    });
  }
  const answerDigest = digestObject({
    previewDigest: preview.integrityDigest,
    answeredAt: normalizedAnswers.answeredAt,
    answers: normalizedAnswers.answers.map(({ question, ...answer }) => answer),
  });
  const bundle = {
    kind: ATTESTATION_KIND,
    dashboardSchemaVersion: DASHBOARD_SCHEMA_VERSION,
    policyVersion: POLICY_VERSION,
    account: bindings,
    inputDigest: preview.input.digest,
    sourceEvidenceDigest: preview.evidence.contextDigest,
    questionPlanDigests: [...new Set([...(prior?.questionPlanDigests ?? []), preview.questionPlan.digest])],
    answerDigests: [...new Set([...(prior?.answerDigests ?? []), answerDigest])],
    createdAt,
    records,
  };
  bundle.integrityDigest = digestObject(attestationIntegrityPayload(bundle));
  return validateAttestationBundle(bundle);
}

export async function createPreviewDocument({
  dashboard,
  inputPath,
  salesforceReportPath,
  ledger,
  evidencePath,
  attestations = null,
  attestationsPath = "",
  createdAt = new Date().toISOString(),
}) {
  await strictValidateDashboard(dashboard);
  const salesforceReceipt = await loadSalesforceMappingReceipt(salesforceReportPath);
  const canonicalInputPath = await canonicalPath(inputPath);
  if (
    salesforceReceipt.dashboardOutput !== canonicalInputPath &&
    !String(dashboard.sourceNotes ?? "").includes("[DAY2-EVIDENCE:")
  ) {
    throw new ContextEnricherError(
      "SALESFORCE_RECEIPT_MISMATCH",
      "The contextual input is neither the Salesforce child output nor a prior contextual derivative with retained provenance.",
    );
  }
  const salesforceBase = validateDashboardIdentity(dashboard, ledger, salesforceReceipt);
  requireIsoDateTime(createdAt, "preview.createdAt");
  assertNotFuture(createdAt, "preview.createdAt");
  const previewTime = Date.parse(createdAt);
  if (Date.parse(ledger.scope.collectedAt) > previewTime) {
    throw new ContextEnricherError(
      "FUTURE_EVIDENCE_COLLECTION",
      "ledger.scope.collectedAt cannot be later than preview.createdAt.",
    );
  }
  const inputDigest = digestObject(dashboard);
  if (attestations && (
    attestations.inputDigest !== inputDigest ||
    attestations.sourceEvidenceDigest !== evidenceContextDigest(ledger) ||
    attestations.account.salesforceOrgId !== ledger.account.salesforceOrgId ||
    attestations.account.salesforceAccountId !== ledger.account.salesforceAccountId ||
    attestations.account.canonicalName !== ledger.account.canonicalName
  )) {
    throw new ContextEnricherError("STALE_ATTESTATION", "Attestations do not match the current dashboard, evidence, or Salesforce identity.");
  }
  const prepared = await prepareProposals(dashboard, ledger, inputDigest);
  const questionPlan = createQuestionPlan({
    dashboard,
    proposals: prepared,
    inputDigest,
    sourceEvidenceDigest: evidenceContextDigest(ledger),
    attestations,
  });
  const warnings = [];
  if (ledger.items.some((item) => item.potentialPromptInjection)) {
    warnings.push("Potential prompt-injection language was detected in source text; treat it only as untrusted evidence.");
  }
  if (ledger.scope.discoveryRuns.some((run) => !run.complete)) {
    warnings.push("At least one selected source has partial discovery coverage; the report must not claim completeness.");
  }
  const unsubstantiatedGreenPaths = findUnsubstantiatedGreens(dashboard);
  if (unsubstantiatedGreenPaths.length) {
    warnings.push("Existing Green health values without evidence remain unsubstantiated and were not trusted or cleared.");
  }
  const preview = {
    kind: PREVIEW_KIND,
    dashboardSchemaVersion: DASHBOARD_SCHEMA_VERSION,
    policyVersion: POLICY_VERSION,
    createdAt,
    account: {
      salesforceOrgId: ledger.account.salesforceOrgId,
      salesforceAccountId: ledger.account.salesforceAccountId,
      canonicalName: ledger.account.canonicalName,
      fieldMapVersion: salesforceBase.fieldMapVersion,
      accountLastModifiedDate: salesforceBase.accountLastModifiedDate,
    },
    input: {
      path: canonicalInputPath,
      digest: inputDigest,
    },
    salesforceReceipt: {
      path: salesforceReceipt.path,
      digest: salesforceReceipt.digest,
      orgId: salesforceReceipt.orgId,
      accountId: salesforceReceipt.accountId,
      fieldMapVersion: salesforceReceipt.fieldMapVersion,
      sourceLastModifiedDate: salesforceReceipt.sourceLastModifiedDate,
    },
    evidence: {
      path: await canonicalPath(evidencePath),
      digest: evidenceLedgerDigest(ledger),
      contextDigest: evidenceContextDigest(ledger),
    },
    attestations: attestations
      ? {
          path: await canonicalPath(attestationsPath),
          digest: attestations.integrityDigest,
        }
      : { path: "", digest: "" },
    scope: deepClone(ledger.scope),
    proposals: prepared,
    proposalDigest: proposalDigest(prepared),
    gaps: deepClone(ledger.gaps),
    warnings,
    unsubstantiatedGreenPaths,
    questionPlan,
  };
  preview.integrityDigest = digestObject(previewIntegrityPayload(preview));
  return preview;
}

export function validatePreviewDocument(preview) {
  const requiredKeys = [
    "kind",
    "dashboardSchemaVersion",
    "policyVersion",
    "createdAt",
    "account",
    "input",
    "salesforceReceipt",
    "evidence",
    "attestations",
    "scope",
    "proposals",
    "proposalDigest",
    "gaps",
    "warnings",
    "unsubstantiatedGreenPaths",
    "questionPlan",
    "integrityDigest",
  ];
  assertExactKeys(preview, requiredKeys, "preview");
  if (preview.kind !== PREVIEW_KIND) {
    throw new ContextEnricherError("INVALID_PREVIEW", `Expected ${PREVIEW_KIND}.`);
  }
  if (preview.dashboardSchemaVersion !== DASHBOARD_SCHEMA_VERSION || preview.policyVersion !== POLICY_VERSION) {
    throw new ContextEnricherError("STALE_PREVIEW", "Preview schema or policy version is stale.");
  }
  requireIsoDateTime(preview.createdAt, "preview.createdAt");
  assertNotFuture(preview.createdAt, "preview.createdAt");
  assertExactKeys(
    preview.account,
    ["salesforceOrgId", "salesforceAccountId", "canonicalName", "fieldMapVersion", "accountLastModifiedDate"],
    "preview.account",
  );
  assertExactKeys(preview.input, ["path", "digest"], "preview.input");
  assertExactKeys(
    preview.salesforceReceipt,
    ["path", "digest", "orgId", "accountId", "fieldMapVersion", "sourceLastModifiedDate"],
    "preview.salesforceReceipt",
  );
  assertExactKeys(preview.evidence, ["path", "digest", "contextDigest"], "preview.evidence");
  assertExactKeys(preview.attestations, ["path", "digest"], "preview.attestations");
  if (Boolean(preview.attestations.path) !== Boolean(preview.attestations.digest)) {
    throw new ContextEnricherError("INVALID_PREVIEW", "Preview attestation path and digest must both be present or blank.");
  }
  validateQuestionPlan(preview.questionPlan, preview.input.digest, preview.evidence.contextDigest);
  if (preview.integrityDigest !== digestObject(previewIntegrityPayload(preview))) {
    throw new ContextEnricherError("PREVIEW_TAMPERED", "Preview integrity digest does not match its contents.");
  }
  return preview;
}

function assertFreshEvidence(ledger, preview, approvedProposals) {
  const previewTime = Date.parse(preview.createdAt);
  const collectionTime = Date.parse(ledger.scope.collectedAt);
  for (const run of ledger.scope.discoveryRuns) {
    if (!run.verifiedAt || Date.parse(run.verifiedAt) <= Math.max(previewTime, collectionTime)) {
      throw new ContextEnricherError(
        "STALE_DISCOVERY",
        `Discovery for ${run.sourceType} was not re-run after preview and the recorded collection.`,
      );
    }
  }
  const requiredEvidenceIds = new Set(approvedProposals.flatMap((proposal) => proposal.evidenceIds));
  for (const item of ledger.items) {
    if (!requiredEvidenceIds.has(item.evidenceId)) continue;
    const freshnessFloor = Math.max(previewTime, collectionTime, Date.parse(item.retrievedAt));
    if (!item.verifiedAt || Date.parse(item.verifiedAt) <= freshnessFloor) {
      throw new ContextEnricherError(
        "STALE_EVIDENCE",
        `Evidence ${item.evidenceId} was not re-fetched or re-confirmed after preview, collection, and retrieval.`,
      );
    }
  }
}

function approvedHealthKeys(proposals) {
  const keys = new Set();
  for (const proposal of proposals) {
    const match = proposal.targetPath.match(/^\/health\/([^/]+)\//u);
    if (match) keys.add(match[1]);
  }
  return keys;
}

function validateApprovedHealth(dashboard, proposals) {
  for (const key of approvedHealthKeys(proposals)) {
    const item = dashboard.health[key];
    if (item.status === "Red") {
      const missing = ["evidence", "mitigation", "owner"].filter((field) => !hasText(item[field]));
      if (missing.length) {
        throw new ContextEnricherError(
          "INCOMPLETE_RED_HEALTH",
          `Approved changes leave health.${key} Red without ${missing.join(", ")}.`,
        );
      }
    }
    const attested = proposals.some((proposal) =>
      proposal.targetPath.startsWith(`/health/${key}/`) &&
      proposal.evidence.some((evidence) => evidence.authority === "account-team-attestation"));
    if (attested && item.status === "Green") {
      const acceptedPaths = new Set(proposals.map((proposal) => proposal.targetPath));
      if (
        !acceptedPaths.has(`/health/${key}/status`) ||
        !acceptedPaths.has(`/health/${key}/evidence`) ||
        !hasText(item.evidence)
      ) {
        throw new ContextEnricherError(
          "INCOMPLETE_GREEN_HEALTH",
          `Attested Green health.${key} requires separately approved status and evidence proposals.`,
        );
      }
    }
  }
}

function provenanceBlock(ledger, proposals) {
  if (!proposals.length) return { marker: "", block: "" };
  const buildKey = sha256(stableStringify({
    orgId: ledger.account.salesforceOrgId,
    accountId: ledger.account.salesforceAccountId,
    acceptedFacts: proposals.map((proposal) => ({
      targetPath: proposal.targetPath,
      operation: proposal.operation,
      value: proposal.value,
      semanticKey: proposal.semanticKey,
      evidenceIds: proposal.evidenceIds,
    })).sort((left, right) => stableStringify(left).localeCompare(stableStringify(right))),
  })).slice(0, 16);
  const marker = `DAY2-EVIDENCE:${buildKey}`;
  const rows = proposals.map((proposal) => {
    const evidence = proposal.evidence
      .map((item) => `${item.evidenceId}/${item.sourceType}/${item.occurredAt || "undated"}`)
      .sort()
      .join(", ");
    return `- ${proposal.proposalId} ${proposal.targetPath} <= ${evidence}`;
  });
  return {
    marker,
    block: [
      `[${marker}]`,
      `Salesforce scope: ${ledger.account.salesforceOrgId} / ${ledger.account.salesforceAccountId}`,
      "Accepted contextual evidence:",
      ...rows,
      `[/${marker}]`,
    ].join("\n"),
  };
}

function appendCompactProvenance(existingNotes, ledger, proposals) {
  const { marker, block } = provenanceBlock(ledger, proposals);
  if (!block) return existingNotes;
  const openingCount = (String(existingNotes).match(/\[DAY2-EVIDENCE:/g) ?? []).length;
  const closingCount = (String(existingNotes).match(/\[\/DAY2-EVIDENCE:/g) ?? []).length;
  if (openingCount !== closingCount) {
    throw new ContextEnricherError(
      "MALFORMED_PROVENANCE",
      "sourceNotes contains a malformed Day 2 evidence marker. Repair it before building.",
    );
  }
  if (String(existingNotes).includes(`[${marker}]`)) return existingNotes;
  return [String(existingNotes).trim(), block].filter(Boolean).join("\n\n");
}

export function evaluateReadiness(dashboard) {
  const blocks = [];
  const warnings = [];
  const addLengthBlock = (value, limit, label) => {
    if (codePointLength(value) > limit) blocks.push(`${label} exceeds ${limit} characters.`);
  };

  if (!hasText(dashboard.tagline)) blocks.push("Page 1 needs a customer value headline.");
  else addLengthBlock(dashboard.tagline, 170, "Customer value headline");

  const statusLines = lines(dashboard.statusSummary);
  if (statusLines.length !== 4) blocks.push(`30-second status needs exactly four lines; found ${statusLines.length}.`);
  statusLines.slice(0, 4).forEach((line, index) => addLengthBlock(line, 120, `Status line ${index + 1}`));

  const whereUsed = lines(dashboard.useCases).slice(0, 3);
  if (!whereUsed.length && !dashboard.consumptionPlan.groups.some((group) => hasText(group.element))) {
    blocks.push("Page 1 needs Where Used evidence.");
  }
  whereUsed.forEach((item, index) => addLengthBlock(item, 100, `Where Used item ${index + 1}`));

  if (!dashboard.goals.length) blocks.push("Add at least one Day 2 Strategy outcome.");
  dashboard.goals.slice(0, 3).forEach((goal, index) => {
    addLengthBlock(goal.text, 140, `Goal ${index + 1} outcome`);
    addLengthBlock(goal.target, 80, `Goal ${index + 1} target`);
    addLengthBlock(goal.owner, 80, `Goal ${index + 1} owner`);
  });
  dashboard.eltAsks.slice(0, 2).forEach((ask, index) =>
    addLengthBlock(ask.ask, 160, `ELT ask ${index + 1}`));
  for (const [label, metric] of Object.entries({
    "Annual Value Realized": dashboard.metrics.savings,
    "Automations Deployed": dashboard.metrics.automations,
    "Agentic in PRD": dashboard.metrics.agentic,
    "Pipeline Ideas": dashboard.metrics.pipeline,
  })) addLengthBlock(metric.note, 100, `${label} note`);

  if (!dashboard.workstreams.length) blocks.push("Add at least one workstream or risk.");
  dashboard.workstreams.slice(0, 3).forEach((workstream, index) => {
    addLengthBlock(workstream.risk, 160, `Workstream ${index + 1} risk`);
    const milestones = lines(workstream.milestones);
    const outcomes = lines(workstream.outcomes);
    if (milestones.length > 4) blocks.push(`Workstream ${index + 1} has more than four milestones.`);
    milestones.forEach((item, itemIndex) =>
      addLengthBlock(item, 100, `Workstream ${index + 1} milestone ${itemIndex + 1}`));
    if (outcomes.length > 2) blocks.push(`Workstream ${index + 1} has more than two outcomes.`);
    outcomes.forEach((item, itemIndex) =>
      addLengthBlock(item, 140, `Workstream ${index + 1} outcome ${itemIndex + 1}`));
  });

  for (const [label, value] of [
    ["Customer name", dashboard.customerName],
    ["Account motion", dashboard.motion],
    ["ARR", dashboard.currentArr],
    ["Renewal Date", dashboard.renewalDate],
  ]) if (!hasText(value)) blocks.push(`Missing required field: ${label}.`);

  if (!hasText(dashboard.deploymentType)) warnings.push("Deployment type is missing.");
  if (!hasText(dashboard.deliveryModel)) warnings.push("Delivery model is missing.");
  if (!hasText(dashboard.executiveCadence.date)) warnings.push("Executive cadence date is missing.");
  if (!dashboard.relationships.length) warnings.push("Relationship map is empty.");
  if (dashboard.relationships.length > 7) warnings.push("Only the first seven relationships appear in locked/PDF output.");
  dashboard.relationships.forEach((relationship, index) => {
    if (!hasText(relationship.uipathName)) warnings.push(`Relationship ${index + 1} is missing a UiPath person.`);
    if (!hasText(relationship.customerName)) warnings.push(`Relationship ${index + 1} is missing a customer person.`);
  });
  if (!dashboard.eltAsks.length) warnings.push("No ELT ask is present.");
  dashboard.eltAsks.forEach((ask, index) => {
    if (!hasText(ask.ask)) warnings.push(`ELT ask ${index + 1} is missing the specific decision or help needed.`);
  });
  dashboard.goals.forEach((goal, index) => {
    if (!hasText(goal.text)) blocks.push(`Goal ${index + 1} is missing a customer-impact outcome.`);
    if (!hasText(goal.target)) warnings.push(`Goal ${index + 1} is missing a measurable target.`);
  });
  dashboard.workstreams.forEach((workstream, index) => {
    if (!hasText(workstream.owner)) warnings.push(`Workstream ${index + 1} is missing an accountable owner.`);
    if (workstream.atRisk && !hasText(workstream.risk)) {
      warnings.push(`At-risk workstream ${index + 1} is missing a risk statement.`);
    }
  });
  for (const question of MOTION_QUESTION_GROUPS[dashboard.motion] ?? []) {
    if (!hasText(dashboard.motionAnswers[question])) {
      blocks.push(`Motion question is unanswered: ${question}`);
    }
  }
  const planStarted =
    hasText(dashboard.consumptionPlan.asOf) ||
    hasText(dashboard.consumptionPlan.forecastPeriod) ||
    dashboard.consumptionPlan.groups.length > 0;
  if (
    !dashboard.consumptionPlan.groups.length &&
    ["Consumption", "Hybrid"].includes(dashboard.motion)
  ) {
    warnings.push("Consumption or Hybrid motion has no evidenced Consumption Plan groups.");
  }
  if (planStarted && !hasText(dashboard.consumptionPlan.asOf)) {
    warnings.push("Consumption Plan is missing an as-of date.");
  }
  if (planStarted && !hasText(dashboard.consumptionPlan.forecastPeriod)) {
    warnings.push("Consumption Plan is missing a forecast period.");
  }
  if (!hasText(dashboard.sourceNotes) && !dashboard.sources.length) {
    warnings.push("No source notes or files are attached.");
  }

  for (const key of HEALTH_KEYS) {
    const item = dashboard.health[key];
    if (!item.status) blocks.push(`health.${key}.status is unset.`);
    if (item.status === "Red") {
      if (!hasText(item.evidence)) blocks.push(`health.${key} is Red without evidence.`);
      if (!hasText(item.mitigation)) warnings.push(`health.${key} is Red without mitigation.`);
      if (!hasText(item.owner)) warnings.push(`health.${key} is Red without an owner.`);
    }
  }
  const redIndicators = [...HEALTH_KEYS]
    .filter((key) => key !== "overall" && dashboard.health[key].status === "Red")
    .length;
  const overall = dashboard.health.overall.status;
  const healthConflict = (overall === "Green" && redIndicators >= 3) || (overall === "Red" && redIndicators === 0);
  if (healthConflict && !dashboard.healthConflictAcknowledged) {
    blocks.push("Overall health conflicts with the detailed indicator pattern and is not acknowledged.");
  }
  return { blocks: uniqueReasons(blocks), warnings: uniqueReasons(warnings) };
}

function applyApprovedProposals(dashboard, proposals) {
  const nonInserts = proposals
    .filter((proposal) => proposal.operation !== "insert" && !proposal.noChange)
    .sort((left, right) => left.targetKey.localeCompare(right.targetKey) || left.proposalId.localeCompare(right.proposalId));
  const inserts = proposals
    .filter((proposal) => proposal.operation === "insert")
    .sort((left, right) => {
      const target = left.targetPath.localeCompare(right.targetPath);
      if (target) return target;
      const leftPosition = left.position === "append" ? Number.MAX_SAFE_INTEGER : left.position;
      const rightPosition = right.position === "append" ? Number.MAX_SAFE_INTEGER : right.position;
      return leftPosition - rightPosition || left.proposalId.localeCompare(right.proposalId);
    });
  for (const proposal of [...nonInserts, ...inserts]) applyTypedOperation(dashboard, proposal);
}

function sanitizeReportText(value, max = 400) {
  return Array.from(String(value ?? "")
    .normalize("NFKC")
    .replace(/[\u0000-\u001F\u007F-\u009F\u202A-\u202E\u2066-\u2069]/gu, " ")
    .replace(/https?:\/\/\S+/giu, "[link omitted]")
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/giu, "[email omitted]")
    .replace(/[\\`|<>\[\]]/gu, "\\$&")
    .replace(/\s+/gu, " ")
    .trim())
    .slice(0, max)
    .join("");
}

function renderAcceptedEvidenceInventory(ledger, acceptedProposals) {
  const acceptedEvidenceIds = new Set(acceptedProposals.flatMap((proposal) => proposal.evidenceIds));
  const acceptedItems = ledger.items.filter((item) => acceptedEvidenceIds.has(item.evidenceId));
  const rows = ["## Accepted evidence inventory", ""];
  if (!acceptedItems.length) {
    rows.push("- None.");
    return rows.join("\n");
  }
  for (const item of acceptedItems) {
    rows.push(
      `- ${sanitizeReportText(item.evidenceId)} — ${sanitizeReportText(item.sourceType)}; source locator retained only in the confidential evidence ledger; author kind ${sanitizeReportText(item.author.kind)}; occurred ${sanitizeReportText(item.occurredAt || "not recorded")}; modified ${sanitizeReportText(item.modifiedAt || "not recorded")}; digest ${sanitizeReportText(item.contentDigest)}; account match ${item.accountMatch.signals.map((signal) => sanitizeReportText(signal)).join(", ")} (${sanitizeReportText(item.accountMatch.rationale)}); claim ${sanitizeReportText(item.claimClass)}; authority ${sanitizeReportText(item.authority)}${item.limitations.length ? `; limits ${item.limitations.map((limit) => sanitizeReportText(limit)).join("; ")}` : ""}.`,
    );
  }
  return rows.join("\n");
}

function renderProposalTable(title, proposals) {
  const rows = [
    `## ${title}`,
    "",
    "| Proposal | Target | Operation | Current conflict | Page 1 | Evidence |",
    "|---|---|---|---:|---:|---|",
  ];
  if (!proposals.length) {
    rows.push("| None |  |  |  |  |  |");
    return rows.join("\n");
  }
  for (const proposal of proposals) {
    rows.push(
      `| ${sanitizeReportText(proposal.proposalId)} | ${sanitizeReportText(proposal.targetPath)} | ${sanitizeReportText(proposal.operation)} | ${proposal.conflict ? "Yes" : "No"} | ${proposal.pageOneVisible === null ? "N/A" : proposal.pageOneVisible ? "Yes" : "No"} | ${proposal.evidenceIds.map((item) => sanitizeReportText(item)).join(", ")} |`,
    );
  }
  return rows.join("\n");
}

export function createEvidenceReport({
  preview,
  ledger,
  acceptedProposals,
  dashboard,
}) {
  const acceptedIds = new Set(acceptedProposals.map((proposal) => proposal.proposalId));
  const notApproved = preview.proposals.filter((proposal) =>
    ["eligible", "no-change"].includes(proposal.disposition) && !acceptedIds.has(proposal.proposalId));
  const rejected = preview.proposals.filter((proposal) =>
    ["rejected", "duplicate", "contradicted"].includes(proposal.disposition));
  const readiness = evaluateReadiness(dashboard);
  const greenWarnings = findUnsubstantiatedGreens(dashboard, acceptedProposals);

  const sections = [
    `<!-- ${REPORT_KIND} -->`,
    "# Day 2 Evidence Report",
    "",
    "**Confidential customer artifact.** This report records proposal provenance and coverage; it is not imported into the dashboard.",
    "",
    "## Account and scope",
    "",
    `- Account: ${sanitizeReportText(ledger.account.canonicalName)}`,
    `- Salesforce identity: ${sanitizeReportText(ledger.account.salesforceOrgId)} / ${sanitizeReportText(ledger.account.salesforceAccountId)}`,
    `- Window: ${sanitizeReportText(ledger.scope.windowStart)} through ${sanitizeReportText(ledger.scope.windowEnd)}`,
    `- Selected sources: ${ledger.scope.sources.map((item) => sanitizeReportText(item)).join(", ") || "none"}`,
    `- Private Slack consent: ${ledger.scope.privateSlackConsent ? "Yes, for named scopes only" : "No"}`,
    "",
    renderProposalTable("Accepted proposals", acceptedProposals),
    "",
    renderAcceptedEvidenceInventory(ledger, acceptedProposals),
    "",
    renderProposalTable("Eligible proposals not approved", notApproved),
    "",
    "## Rejected, duplicate, or contradicted proposals",
    "",
  ];
  if (!rejected.length) sections.push("- None.");
  for (const proposal of rejected) {
    sections.push(
      `- ${sanitizeReportText(proposal.proposalId)} ${sanitizeReportText(proposal.targetPath)}: ${proposal.reasons.map((item) => sanitizeReportText(item)).join("; ") || proposal.disposition}`,
    );
  }
  sections.push("", "## Source coverage", "");
  for (const run of ledger.scope.discoveryRuns) {
    sections.push(
      `- ${sanitizeReportText(run.sourceType)}: ${run.complete ? "complete within recorded query" : "partial"}; ${run.pages} page(s); query ${sanitizeReportText(run.queryDigest)}${run.limitations.length ? `; limits: ${run.limitations.map((item) => sanitizeReportText(item)).join("; ")}` : ""}`,
    );
  }
  sections.push("", "## Gaps and limitations", "");
  const gaps = [...ledger.gaps, ...ledger.scope.coverageNotes];
  if (!gaps.length) sections.push("- None recorded.");
  else gaps.forEach((item) => sections.push(`- ${sanitizeReportText(item)}`));
  sections.push("", "## Clarification summary", "");
  const clarification = preview.questionPlan.summary;
  sections.push(
    `- Answered: ${clarification.accepted}.`,
    `- Skipped: ${clarification.skipped}.`,
    `- Unknown and retained as evidence gaps: ${clarification.unknown}.`,
    `- Unresolved questions: ${clarification.unresolved}.`,
  );
  for (const record of ledger.attestations?.records ?? []) {
    if (record.status === "unknown") {
      sections.push(`- Evidence gap: ${sanitizeReportText(FIELD_POLICY_MAP[record.policyKey].intent)} remains unknown.`);
    } else if (record.status === "skipped") {
      sections.push(`- Skipped: ${sanitizeReportText(FIELD_POLICY_MAP[record.policyKey].intent)}.`);
    }
  }
  sections.push("", "## Validation status", "");
  if (!readiness.blocks.length) sections.push("- No current PDF blocker-parity findings.");
  else readiness.blocks.forEach((item) => sections.push(`- Block: ${sanitizeReportText(item)}`));
  readiness.warnings.forEach((item) => sections.push(`- Warning: ${sanitizeReportText(item)}`));
  greenWarnings.forEach((item) => sections.push(`- Warning: unsubstantiated Green at ${sanitizeReportText(item)}.`));
  if (preview.warnings.length) {
    sections.push("", "## Preview warnings", "");
    preview.warnings.forEach((item) => sections.push(`- ${sanitizeReportText(item)}`));
  }
  sections.push(
    "",
    "## Final review",
    "",
    "Import the generated dashboard JSON, use the built-in tooltips and blocker badges, review Page 1 in executive order, lock editing, and export PDF only after resolving supported gaps.",
    "",
  );
  return sections.join("\n");
}

export async function buildFromPreview({
  preview,
  previewPath,
  ledger,
  evidencePath,
  attestations = null,
  attestationsPath = "",
  approvedProposalIds,
  outputPath,
  reportPath,
  overwrite = false,
}) {
  validatePreviewDocument(preview);
  if (preview.attestations.path) {
    if (!attestations) {
      throw new ContextEnricherError("MISSING_ATTESTATION", "This preview requires its bound attestation bundle.");
    }
    if (
      await canonicalPath(attestationsPath) !== preview.attestations.path ||
      attestations.integrityDigest !== preview.attestations.digest
    ) {
      throw new ContextEnricherError("STALE_ATTESTATION", "Build attestations differ from the preview binding.");
    }
  } else if (attestations) {
    throw new ContextEnricherError("STALE_PREVIEW", "Attestations were added after preview; create a new preview.");
  }
  if (!Array.isArray(approvedProposalIds)) {
    throw new ContextEnricherError("INVALID_APPROVAL", "approvedProposalIds must be an array.");
  }
  if (new Set(approvedProposalIds).size !== approvedProposalIds.length) {
    throw new ContextEnricherError("INVALID_APPROVAL", "Duplicate proposal approvals are not allowed.");
  }
  for (const id of approvedProposalIds) {
    if (!/^P-[a-f0-9]{20}$/u.test(id)) {
      throw new ContextEnricherError(
        "INVALID_APPROVAL",
        "Approvals must be exact full proposal IDs. Wildcards, prefixes, paths, and bulk approval are forbidden.",
      );
    }
  }

  const canonicalEvidencePath = await canonicalPath(evidencePath);
  if (canonicalEvidencePath !== preview.evidence.path) {
    throw new ContextEnricherError("STALE_EVIDENCE", "Build evidence path differs from the preview evidence path.");
  }
  if (evidenceLedgerDigest(ledger) !== preview.evidence.digest) {
    throw new ContextEnricherError("STALE_EVIDENCE", "Evidence content, scope, or proposals changed after preview.");
  }
  if (
    ledger.account.salesforceOrgId !== preview.account.salesforceOrgId ||
    ledger.account.salesforceAccountId !== preview.account.salesforceAccountId ||
    ledger.account.canonicalName !== preview.account.canonicalName
  ) {
    throw new ContextEnricherError("ACCOUNT_IDENTITY_CHANGED", "Salesforce account identity changed after preview.");
  }

  const currentSalesforceReceipt = await loadSalesforceMappingReceipt(preview.salesforceReceipt.path);
  if (
    currentSalesforceReceipt.digest !== preview.salesforceReceipt.digest ||
    currentSalesforceReceipt.orgId !== preview.salesforceReceipt.orgId ||
    currentSalesforceReceipt.accountId !== preview.salesforceReceipt.accountId ||
    currentSalesforceReceipt.fieldMapVersion !== preview.salesforceReceipt.fieldMapVersion ||
    currentSalesforceReceipt.sourceLastModifiedDate !== preview.salesforceReceipt.sourceLastModifiedDate
  ) {
    throw new ContextEnricherError(
      "SALESFORCE_RECEIPT_CHANGED",
      "The Salesforce child mapping report changed after preview.",
    );
  }
  const dashboard = await loadDashboard(preview.input.path);
  if (digestObject(dashboard) !== preview.input.digest) {
    throw new ContextEnricherError("STALE_INPUT", "The dashboard input changed after preview.");
  }
  const salesforceBase = validateDashboardIdentity(dashboard, ledger, currentSalesforceReceipt);
  if (
    salesforceBase.fieldMapVersion !== preview.account.fieldMapVersion ||
    salesforceBase.accountLastModifiedDate !== preview.account.accountLastModifiedDate
  ) {
    throw new ContextEnricherError(
      "SALESFORCE_BASE_STALE",
      "The Salesforce child provenance no longer matches the previewed base.",
    );
  }
  const currentProposals = await prepareProposals(dashboard, ledger, preview.input.digest);
  if (
    proposalDigest(currentProposals) !== preview.proposalDigest ||
    stableStringify(currentProposals) !== stableStringify(preview.proposals)
  ) {
    throw new ContextEnricherError("STALE_PREVIEW", "Current proposals do not match the integrity-checked preview.");
  }
  const byId = new Map(currentProposals.map((proposal) => [proposal.proposalId, proposal]));
  const approved = approvedProposalIds.map((id) => {
    const proposal = byId.get(id);
    if (!proposal) {
      throw new ContextEnricherError("UNKNOWN_APPROVAL", `Proposal ${id} is not present in the current preview.`);
    }
    if (!["eligible", "no-change"].includes(proposal.disposition)) {
      throw new ContextEnricherError(
        "INELIGIBLE_APPROVAL",
        `Proposal ${id} is ${proposal.disposition} and cannot be approved.`,
      );
    }
    return proposal;
  });
  const approvedTargetKeys = approved.map((proposal) => proposal.targetKey);
  if (new Set(approvedTargetKeys).size !== approvedTargetKeys.length) {
    throw new ContextEnricherError(
      "APPROVAL_CONFLICT",
      "Two approved proposals target the same scalar or semantic row.",
    );
  }
  assertFreshEvidence(ledger, preview, approved);

  const output = deepClone(dashboard);
  applyApprovedProposals(output, approved);
  validateApprovedHealth(output, approved);
  output.sourceNotes = appendCompactProvenance(output.sourceNotes, ledger, approved);
  await strictValidateDashboard(output);

  const localSourcePaths = ledger.items
    .filter((item) => item.sourceType === "local-file" && path.isAbsolute(item.sourceId))
    .map((item) => item.sourceId);
  await assertSafeDerivedTargets(
    [outputPath, reportPath],
    [
      preview.input.path,
      preview.evidence.path,
      preview.salesforceReceipt.path,
      previewPath,
      attestationsPath,
      ...localSourcePaths,
    ],
  );
  const report = createEvidenceReport({ preview, ledger, acceptedProposals: approved, dashboard: output });
  const [writtenOutputPath, writtenReportPath] = await writeDerivedPairAtomic([
    {
      filePath: outputPath,
      content: `${JSON.stringify(output, null, 2)}\n`,
      kind: "dashboard",
    },
    {
      filePath: reportPath,
      content: report,
      kind: "report",
    },
  ], { overwrite });

  const cleanupWarnings = [];
  try {
    await unlink(previewPath);
  } catch (error) {
    cleanupWarnings.push(`Could not remove the confidential preview: ${error.message}`);
  }
  return {
    dashboard: output,
    report,
    acceptedProposalIds: approved.map((proposal) => proposal.proposalId),
    outputPath: writtenOutputPath,
    reportPath: writtenReportPath,
    readiness: evaluateReadiness(output),
    cleanupWarnings,
  };
}

export function slugify(value) {
  return String(value ?? "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/gu, "-")
    .replace(/^-+|-+$/gu, "")
    .slice(0, 80) || "account";
}

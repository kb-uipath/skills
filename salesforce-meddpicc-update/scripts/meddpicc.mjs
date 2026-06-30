#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const SCRIPT_PATH = fileURLToPath(import.meta.url);
const SKILL_DIR = path.resolve(path.dirname(SCRIPT_PATH), "..");
const FIELD_MAP_PATH = path.join(SKILL_DIR, "references", "field-map.json");
const FIELD_MAP = JSON.parse(fs.readFileSync(FIELD_MAP_PATH, "utf8"));
const FIELD_DEFS = FIELD_MAP.fields;
const DEFAULT_API_VERSION = FIELD_MAP.apiVersion || "v60.0";
const DEFAULT_CONNECTOR = FIELD_MAP.targetConnector || "uipath-salesforce-sfdc";
const DEFAULT_STALE_MINUTES = FIELD_MAP.staleDraftMinutes || 10;
const OPPORTUNITY_PREFIX = FIELD_MAP.opportunityPrefix || "006";
const TEXTAREA_TYPES = new Set(["textarea"]);
const STRING_TYPES = new Set(["string", "phone", "email", "url"]);
const SECRET_KEYS = new Set(["connection", "connectionId", "accessToken", "token", "authorization", "body"]);

class MeddpiccError extends Error {
  constructor(code, message, options = {}) {
    super(message);
    this.name = "MeddpiccError";
    this.code = code;
    this.field = options.field || null;
    this.recoverable = options.recoverable ?? false;
    this.nextAction = options.nextAction || null;
  }

  toJSON() {
    return {
      code: this.code,
      message: this.message,
      field: this.field,
      recoverable: this.recoverable,
      nextAction: this.nextAction,
    };
  }
}

const aliasMap = new Map();
for (const [canonical, def] of Object.entries(FIELD_DEFS)) {
  aliasMap.set(normalizeKey(canonical), canonical);
  aliasMap.set(normalizeKey(def.apiName || canonical), canonical);
  aliasMap.set(normalizeKey(def.label || canonical), canonical);
  for (const alias of def.aliases || []) {
    aliasMap.set(normalizeKey(alias), canonical);
  }
}

function normalizeKey(key) {
  return String(key)
    .trim()
    .replace(/[^a-zA-Z0-9_]/g, "")
    .toLowerCase();
}

function canonicalKey(key) {
  return aliasMap.get(normalizeKey(key));
}

function asString(value) {
  if (value === null || value === undefined) return "";
  return String(value).trim();
}

function normalizeWhitespace(value) {
  return asString(value).replace(/\s+/g, " ");
}

const INJECTION_PATTERNS = [
  /ignore\s+(?:all\s+)?(?:prior\s+|previous\s+)?instructions?/gi,
  /set\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+(?:to|=)/gi,
  /change\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+(?:to|=)/gi,
  /update\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+(?:to|=)/gi,
];

function detectInjection(text) {
  const normalized = normalizeWhitespace(text);
  const findings = [];
  for (const re of INJECTION_PATTERNS) {
    let m;
    const localRe = new RegExp(re.source, re.flags);
    while ((m = localRe.exec(normalized)) !== null) {
      if (m[1]) {
        findings.push({ type: "field_override", field: m[1], match: m[0] });
      } else {
        findings.push({ type: "instruction_override", match: m[0] });
      }
    }
  }
  return findings;
}

function sanitizeInjectedContent(text) {
  let sanitized = text;
  for (const re of INJECTION_PATTERNS) {
    if (re.source.includes("([a-zA-Z_][a-zA-Z0-9_]*)")) {
      sanitized = sanitized.replace(re, "");
    } else {
      sanitized = sanitized.replace(re, "");
    }
  }
  return normalizeWhitespace(sanitized).trim();
}

function isSalesforceId(value, prefix) {
  const text = asString(value);
  if (!new RegExp(`^${prefix}[a-zA-Z0-9]{12}([a-zA-Z0-9]{3})?$`).test(text)) {
    return false;
  }
  return text.length === 15 || text.length === 18;
}

function parseOpportunityId(input) {
  const text = asString(input);
  if (!text) return { opportunityId: null, valid: false, source: "empty" };

  const lightning = text.match(/\/Opportunity\/([a-zA-Z0-9]{15}(?:[a-zA-Z0-9]{3})?)(?=[^a-zA-Z0-9]|$)/);
  if (lightning) {
    const id = lightning[1];
    return {
      opportunityId: id.startsWith(OPPORTUNITY_PREFIX) ? id : null,
      valid: id.startsWith(OPPORTUNITY_PREFIX),
      source: "lightning-url",
      ...(id.startsWith(OPPORTUNITY_PREFIX) ? {} : { rejectedId: id, reason: `Salesforce ID does not use the Opportunity prefix ${OPPORTUNITY_PREFIX}.` }),
    };
  }

  const embedded = text.match(new RegExp(`(^|[^a-zA-Z0-9])(${OPPORTUNITY_PREFIX}[a-zA-Z0-9]{12}(?:[a-zA-Z0-9]{3})?)(?=[^a-zA-Z0-9]|$)`));
  if (embedded) {
    return { opportunityId: embedded[2], valid: true, source: "embedded" };
  }

  const wrongObject = text.match(/(^|[^a-zA-Z0-9])([a-zA-Z0-9]{15}(?:[a-zA-Z0-9]{3})?)(?=[^a-zA-Z0-9]|$)/);
  if (wrongObject) {
    return {
      opportunityId: null,
      valid: false,
      source: "wrong-object",
      rejectedId: wrongObject[2],
      reason: `Salesforce ID does not use the Opportunity prefix ${OPPORTUNITY_PREFIX}.`,
    };
  }

  return { opportunityId: null, valid: false, source: "not-found" };
}

function datePrefix(date, author, includeTime = false) {
  const cleanDate = asString(date);
  const cleanAuthor = asString(author);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(cleanDate)) {
    throw new MeddpiccError("INVALID_DATE", "date must use YYYY-MM-DD format", {
      recoverable: true,
      nextAction: "Provide the local date in YYYY-MM-DD format.",
    });
  }
  if (!cleanAuthor) {
    throw new MeddpiccError("MISSING_AUTHOR", "author is required", {
      recoverable: true,
      nextAction: "Provide the user's first and last name for the dated entry prefix.",
    });
  }
  if (includeTime) {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    return `[${cleanDate} ${hh}:${mm} - ${cleanAuthor}]`;
  }
  return `[${cleanDate} - ${cleanAuthor}]`;
}

function appendEntry(currentValue, prefix, content, header) {
  const body = header ? `========== ${header} ==========\n${asString(content)}` : asString(content);
  const entry = `${prefix}\n${body}`;
  const current = currentValue === null || currentValue === undefined ? "" : String(currentValue);
  if (!current) return { value: entry, entry, body };
  return { value: `${current}\n\n${entry}`, entry, body };
}

function tokenSet(text) {
  const normalized = normalizeWhitespace(text).toLowerCase().replace(/[^a-z0-9\s]/g, " ");
  const tokens = normalized.split(/\s+/).filter((t) => t.length > 0);
  return new Set(tokens);
}

function jaccardSimilarity(a, b) {
  const setA = tokenSet(a);
  const setB = tokenSet(b);
  if (setA.size === 0 && setB.size === 0) return 1;
  if (setA.size === 0 || setB.size === 0) return 0;
  const intersection = new Set([...setA].filter((x) => setB.has(x)));
  const union = new Set([...setA, ...setB]);
  return intersection.size / union.size;
}

function stripDatePrefixes(text) {
  return normalizeWhitespace(text).replace(/\[\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})? - [^\]]+\]\s*/g, "");
}

function duplicateStatus(currentValue, prefix, content, header, forceDuplicate = false) {
  if (forceDuplicate) return "none";
  const current = normalizeWhitespace(currentValue);
  if (!current) return "none";
  const body = header ? `========== ${header} ==========\n${asString(content)}` : asString(content);
  const exactEntry = normalizeWhitespace(`${prefix}\n${body}`);
  const contentOnly = normalizeWhitespace(body);
  if (current.includes(exactEntry)) return "exact";
  if (contentOnly && current.includes(contentOnly)) return "content";
  // Fuzzy fallback: compare stripped content to avoid prefix dilution
  const strippedCurrent = stripDatePrefixes(current);
  const strippedContent = stripDatePrefixes(contentOnly);
  if (strippedContent && jaccardSimilarity(strippedCurrent, strippedContent) > 0.6) return "content";
  return "none";
}

function hasDuplicateEntry(currentValue, prefix, content, header) {
  return duplicateStatus(currentValue, prefix, content, header) === "exact";
}

function parseContentObject(content, options = {}) {
  const output = new Map();
  const unknown = [];
  for (const [key, value] of Object.entries(content || {})) {
    const canonical = canonicalKey(key);
    if (!canonical) {
      unknown.push(key);
      continue;
    }
    output.set(canonical, value);
  }
  if (unknown.length > 0 && options.allowUnknownFields !== true) {
    throw new MeddpiccError("UNKNOWN_FIELD_KEY", `Unknown MEDDPICC content field(s): ${unknown.join(", ")}`, {
      field: unknown[0],
      recoverable: true,
      nextAction: "Use a supported MEDDPICC field label or Salesforce API name from references/field-map.json.",
    });
  }
  return output;
}

function compactFields(fields) {
  return Object.fromEntries(Object.entries(fields || {}).filter(([, value]) => value !== undefined));
}

function extractContactId(value) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return asString(value.contactId || value.id || value.Id);
  }
  return asString(value);
}

function draft(payload) {
  const parsed = parseOpportunityId(payload.opportunityId || payload.input || "");
  if (!parsed.valid) {
    throw new MeddpiccError("INVALID_OPPORTUNITY_ID", parsed.reason || "A valid Salesforce Opportunity ID beginning with 006 is required.", {
      recoverable: true,
      nextAction: "Provide a Salesforce Opportunity URL or 15/18-character Opportunity ID.",
    });
  }

  const author = asString(payload.author);
  const date = asString(payload.date);
  const prefix = datePrefix(date, author);
  const current = payload.current || {};
  const rawContent = payload.content || {};
  const sanitizedContent = {};
  const injectionWarnings = [];
  for (const [key, value] of Object.entries(rawContent)) {
    const text = asString(value);
    const findings = detectInjection(text);
    if (findings.length > 0) {
      injectionWarnings.push(`Suspicious content detected in ${key}: possible injection attempt. Treated as data only; non-MEDDPICC directives were removed.`);
      sanitizedContent[key] = sanitizeInjectedContent(text);
    } else {
      sanitizedContent[key] = value;
    }
  }
  const content = parseContentObject(sanitizedContent, { allowUnknownFields: payload.allowUnknownFields });
  const proposedFields = {};
  const entries = {};
  const skippedFields = [];
  const warnings = [...injectionWarnings];
  const actionItems = [];
  const forceDuplicate = payload.forceDuplicate === true;

  function addAppend(apiName, label, rawContent, header) {
    const text = asString(rawContent);
    if (!text) return;
    const dupPrefix = forceDuplicate ? datePrefix(date, author, true) : prefix;
    const duplicate = duplicateStatus(current[apiName], dupPrefix, text, header, forceDuplicate);
    if (duplicate === "exact") {
      skippedFields.push({ field: apiName, label, reason: "duplicate_entry" });
      warnings.push(`${label} already contains this exact dated entry; skipped duplicate append.`);
      return;
    }
    if (duplicate === "content") {
      warnings.push(`${label} contains similar content already; drafted a new dated entry because the prior entry is not an exact duplicate.`);
    }
    const result = appendEntry(current[apiName], dupPrefix, text, header);
    proposedFields[apiName] = result.value;
    entries[apiName] = result.entry;
  }

  for (const [key, rawValue] of content.entries()) {
    const def = FIELD_DEFS[key];
    if (!def) continue;

    if (def.mode === "route") {
      addAppend(def.routeTo, def.label, rawValue, def.header);
      continue;
    }

    if (def.expectedType === "reference" || def.mode === "lookup") {
      const contactId = extractContactId(rawValue);
      const prefixForLookup = def.referencePrefix || FIELD_MAP.contactPrefix || "003";
      if (isSalesforceId(contactId, prefixForLookup)) {
        proposedFields[def.apiName] = contactId;
        entries[def.apiName] = contactId;
      } else {
        addAppend(def.strategyRouteTo || "Opportunity_Next_Steps__c", `${def.label} Strategy`, rawValue, def.strategyHeader);
        skippedFields.push({
          field: def.apiName,
          label: def.label,
          reason: "lookup_requires_contact_id",
          routedTo: def.strategyRouteTo || "Opportunity_Next_Steps__c",
        });
        actionItems.push(`Resolve ${def.label} to a Salesforce Contact and link ${def.apiName}.`);
      }
      continue;
    }

    if (def.mode === "append") {
      addAppend(def.apiName, def.label, rawValue);
      continue;
    }

    if (def.expectedType === "multipicklist") {
      const values = Array.isArray(rawValue) ? rawValue.map(asString).filter(Boolean) : asString(rawValue).split(";").map(asString).filter(Boolean);
      if (values.length === 0) continue;
      proposedFields[def.apiName] = values.join(";");
      entries[def.apiName] = proposedFields[def.apiName];
      continue;
    }

    if (def.mode === "replace") {
      let text = asString(rawValue);
      if (!text) continue;
      const maxLength = def.maxLength || 255;
      if (text.length > maxLength) {
        warnings.push(`${def.apiName} exceeded ${maxLength} characters and was truncated from ${text.length} characters.`);
        text = text.slice(0, maxLength);
      }
      proposedFields[def.apiName] = text;
      entries[def.apiName] = text;
    }
  }

  return {
    opportunityId: parsed.opportunityId,
    opportunityName: current.Name || null,
    author,
    date,
    generatedAt: payload.generatedAt || new Date().toISOString(),
    currentLastModifiedDate: current.LastModifiedDate || null,
    current: compactFields(current),
    proposedFields,
    entries,
    skippedFields,
    warnings,
    actionItems,
    requiresConfirmation: Object.keys(proposedFields).length > 0,
  };
}

function fieldsByName(describe) {
  const fields = describe?.fields || [];
  return new Map(fields.map((field) => [field.name, field]));
}

function getExpectedType(apiName) {
  for (const def of Object.values(FIELD_DEFS)) {
    if (def.apiName === apiName) return def.expectedType;
  }
  return null;
}

function validateFieldValue(apiName, value, describeField) {
  if (!describeField) {
    throw new MeddpiccError("SCHEMA_FIELD_MISSING", `Missing field in describe response: ${apiName}`, {
      field: apiName,
      recoverable: false,
      nextAction: "Stop and re-check Salesforce schema before writing.",
    });
  }
  if (describeField.updateable === false) {
    throw new MeddpiccError("FIELD_NOT_UPDATEABLE", `Field is not updateable: ${apiName}`, {
      field: apiName,
      recoverable: false,
      nextAction: "Ask Salesforce admin or Sales Ops to grant field write access or choose another field.",
    });
  }

  const expected = getExpectedType(apiName);
  const actual = describeField.type;
  if (expected && expected !== actual) {
    if (!(expected === "textarea" && TEXTAREA_TYPES.has(actual)) && !(expected === "string" && STRING_TYPES.has(actual))) {
      throw new MeddpiccError("FIELD_TYPE_MISMATCH", `Field type mismatch for ${apiName}: expected ${expected}, got ${actual}`, {
        field: apiName,
        recoverable: false,
        nextAction: "Stop and update the field map after verifying Salesforce describe metadata.",
      });
    }
  }

  const text = String(value);
  if ((TEXTAREA_TYPES.has(actual) || STRING_TYPES.has(actual) || actual === "multipicklist" || actual === "picklist") && describeField.length && text.length > describeField.length) {
    throw new MeddpiccError("FIELD_LENGTH_EXCEEDED", `Field length exceeded for ${apiName}: ${text.length} > ${describeField.length}`, {
      field: apiName,
      recoverable: true,
      nextAction: "Shorten the field content or split the update before writing.",
    });
  }

  if (actual === "reference") {
    if (!/^[a-zA-Z0-9]{15}([a-zA-Z0-9]{3})?$/.test(text)) {
      throw new MeddpiccError("REFERENCE_ID_REQUIRED", `Reference field ${apiName} requires a Salesforce ID.`, {
        field: apiName,
        recoverable: true,
        nextAction: "Resolve the person to a Salesforce Contact ID or route narrative to Opportunity Next Steps.",
      });
    }
  }

  if (actual === "multipicklist" || actual === "picklist") {
    const allowed = new Set((describeField.picklistValues || []).filter((item) => item.active !== false).map((item) => item.value));
    const values = actual === "multipicklist" ? text.split(";").map(asString).filter(Boolean) : [text];
    const invalid = values.filter((item) => !allowed.has(item));
    if (invalid.length > 0) {
      throw new MeddpiccError("INVALID_PICKLIST_VALUE", `Invalid picklist value for ${apiName}: ${invalid.join(", ")}`, {
        field: apiName,
        recoverable: true,
        nextAction: `Choose one of the active Salesforce picklist values for ${apiName}.`,
      });
    }
  }
}

function minutesBetween(startIso, endIso) {
  const start = Date.parse(startIso || "");
  const end = Date.parse(endIso || "");
  if (!Number.isFinite(start) || !Number.isFinite(end)) return 0;
  return (end - start) / 60000;
}

function buildPatch(payload) {
  const draftPayload = payload.draft || payload;
  const proposedFields = draftPayload.proposedFields || {};
  const warnings = [...(draftPayload.warnings || [])];
  const maxAge = Number(payload.maxConfirmationAgeMinutes ?? DEFAULT_STALE_MINUTES);
  const now = payload.confirmedAt || payload.now || new Date().toISOString();

  if (draftPayload.generatedAt && minutesBetween(draftPayload.generatedAt, now) > maxAge) {
    return {
      envelope: null,
      salesforceBody: null,
      requiresFreshRead: true,
      warnings: [...warnings, `Draft is older than ${maxAge} minutes; re-read Salesforce before writing.`],
      skippedFields: draftPayload.skippedFields || [],
    };
  }

  if (
    payload.freshLastModifiedDate &&
    draftPayload.currentLastModifiedDate &&
    payload.freshLastModifiedDate !== draftPayload.currentLastModifiedDate
  ) {
    return {
      envelope: null,
      salesforceBody: null,
      requiresFreshRead: true,
      warnings: [...warnings, "Opportunity LastModifiedDate changed after draft generation; rebuild the draft."],
      skippedFields: draftPayload.skippedFields || [],
    };
  }

  if (Object.keys(proposedFields).length === 0) {
    throw new MeddpiccError("NO_PROPOSED_FIELDS", "No proposed fields to write.", {
      recoverable: true,
      nextAction: "Add at least one supported MEDDPICC or Next Steps field before building a PATCH.",
    });
  }

  const describeFields = fieldsByName(payload.describe);
  const salesforceBody = {};
  for (const [apiName, value] of Object.entries(proposedFields)) {
    validateFieldValue(apiName, value, describeFields.get(apiName));
    salesforceBody[apiName] = value;
  }

  const connection = asString(payload.connection || payload.connectionId);
  if (!connection) {
    throw new MeddpiccError("MISSING_CONNECTION_ID", "connection or connectionId is required.", {
      recoverable: true,
      nextAction: "Resolve and pass the UiPath Integration Service Salesforce connection ID.",
    });
  }
  const opportunityId = asString(draftPayload.opportunityId || payload.opportunityId);
  if (!parseOpportunityId(opportunityId).valid) {
    throw new MeddpiccError("INVALID_OPPORTUNITY_ID", "Valid opportunityId is required.", {
      recoverable: true,
      nextAction: "Provide a Salesforce Opportunity ID beginning with 006.",
    });
  }

  const apiVersion = payload.apiVersion || DEFAULT_API_VERSION;
  const requestPath = `/services/data/${apiVersion}/sobjects/Opportunity/${opportunityId}`;
  return {
    envelope: {
      authentication: "connector",
      targetConnector: payload.targetConnector || DEFAULT_CONNECTOR,
      connection,
      method: "PATCH",
      url: requestPath,
      path: requestPath,
      headers: {},
      query: {},
      body: JSON.stringify(salesforceBody),
    },
    salesforceBody,
    requiresFreshRead: false,
    warnings,
    skippedFields: draftPayload.skippedFields || [],
  };
}

function verify(payload) {
  const draftPayload = payload.draft || payload;
  const proposedFields = draftPayload.proposedFields || {};
  const readBack = payload.readBack || {};
  const fieldsWritten = [];
  const discrepancies = [];

  for (const [apiName, expected] of Object.entries(proposedFields)) {
    const actual = readBack[apiName];
    const matched = actual === expected;
    fieldsWritten.push({
      field: apiName,
      matched,
      expectedLength: String(expected).length,
      actualLength: actual === undefined || actual === null ? 0 : String(actual).length,
    });
    if (!matched) {
      discrepancies.push({ field: apiName, expected, actual });
    }
  }

  const response = payload.response || {};
  const warnings = [...(draftPayload.warnings || [])];
  if (response.code !== undefined && response.code !== 204) {
    warnings.push(`PATCH response code was ${response.code}; expected 204.`);
  }

  const actionItems = [...(draftPayload.actionItems || [])];
  for (const skipped of draftPayload.skippedFields || []) {
    if (skipped.reason === "lookup_requires_contact_id") {
      actionItems.push(`Create or resolve the Contact and populate ${skipped.field}.`);
    }
  }

  return {
    opportunity: {
      id: draftPayload.opportunityId || readBack.Id || null,
      name: readBack.Name || draftPayload.opportunityName || null,
      lastModifiedDate: readBack.LastModifiedDate || null,
    },
    readBackStatus: discrepancies.length === 0 ? "all_matched" : "mismatch",
    fieldsWritten,
    fieldsSkipped: draftPayload.skippedFields || [],
    warnings,
    discrepancies,
    actionItems: [...new Set(actionItems)],
  };
}

function redact(value) {
  if (Array.isArray(value)) return value.map(redact);
  if (!value || typeof value !== "object") return value;
  const output = {};
  for (const [key, item] of Object.entries(value)) {
    if (SECRET_KEYS.has(key)) {
      output[key] = item ? "[REDACTED]" : item;
    } else {
      output[key] = redact(item);
    }
  }
  return output;
}

function receipt(payload) {
  const draftPayload = payload.draft || payload;
  const verification = payload.verification || payload.verify || null;
  const patch = payload.patch || payload.buildPatch || null;
  return {
    type: payload.type || (verification ? "verification" : patch ? "patch" : "confirmation"),
    opportunity: {
      id: draftPayload.opportunityId || verification?.opportunity?.id || null,
      name: draftPayload.opportunityName || verification?.opportunity?.name || null,
      lastModifiedDate: verification?.opportunity?.lastModifiedDate || draftPayload.currentLastModifiedDate || null,
    },
    proposedFields: redact(draftPayload.proposedFields || {}),
    entries: redact(draftPayload.entries || {}),
    skippedFields: draftPayload.skippedFields || [],
    warnings: [...(draftPayload.warnings || []), ...(patch?.warnings || []), ...(verification?.warnings || [])],
    actionItems: [...new Set([...(draftPayload.actionItems || []), ...(verification?.actionItems || [])])],
    verificationStatus: verification?.readBackStatus || null,
    fieldsWritten: verification?.fieldsWritten || [],
    patch: patch ? redact(patch.envelope || patch) : null,
  };
}

function buildTelemetryPayload(payload) {
  const verify = payload.verify || payload;
  const opp = verify.opportunity || {};
  const now = payload.now || new Date().toISOString();
  const skillVersion = payload.skillVersion || "1.0.0";
  const skillSha = payload.skillSha || "unknown";
  const runId = payload.runId || (typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2));

  const fieldsTargeted = (verify.fieldsWritten || []).map((f) => f.field);

  const output = {
    oppId: opp.id || null,
    runTime: now,
    fieldsTargeted,
    skillVersion,
    skillSha,
    runId,
    readBackStatus: verify.readBackStatus || null,
    fieldsWrittenCount: (verify.fieldsWritten || []).length,
    fieldsSkippedCount: (verify.fieldsSkipped || []).length,
    warningsCount: (verify.warnings || []).length,
    discrepanciesCount: (verify.discrepancies || []).length,
  };

  // Strip forbidden privacy keys (TEL-02)
  const forbiddenKeys = new Set([
    "narrativeContent", "fieldContent", "championName", "ebName", "contactEmail", "amount",
    "_rawContentMustNotLeak"
  ]);

  // Strip name variants (TEL-03)
  const nameVariants = new Set([
    "oppName", "opportunityName", "name", "accountName", "Account__c", "opportunity.name"
  ]);

  for (const key of Object.keys(payload)) {
    if (forbiddenKeys.has(key) || nameVariants.has(key)) {
      delete payload[key];
    }
  }

  return output;
}

function classifyError(payload) {
  const status = payload.status ?? payload.code ?? payload.response?.code ?? payload.response?.status;
  const body = payload.body ?? payload.response?.body ?? payload.response?.data ?? payload.data ?? payload;
  const text = typeof body === "string" ? body : JSON.stringify(body || {});
  const upper = text.toUpperCase();

  if (payload instanceof MeddpiccError || payload.code === "UNKNOWN_FIELD_KEY") {
    const err = payload instanceof MeddpiccError ? payload : new MeddpiccError(payload.code, payload.message || payload.code, payload);
    return err.toJSON();
  }
  if (upper.includes("CNS1000") || upper.includes("NO CONNECTION") || upper.includes("NO CONNECTIONS")) {
    return {
      code: "CONNECTION_MISSING",
      message: "No UiPath Integration Service Salesforce connection exists.",
      field: null,
      recoverable: true,
      nextAction: "Create or re-authorize the Salesforce connection in UiPath Integration Service.",
    };
  }
  if (Number(status) === 401 || upper.includes("UNAUTHORIZED") || upper.includes("TOKEN")) {
    return {
      code: "AUTH_EXPIRED",
      message: "Salesforce or UiPath connection authentication expired.",
      field: null,
      recoverable: true,
      nextAction: "Re-authorize the UiPath Integration Service Salesforce connection.",
    };
  }
  if (Number(status) === 403 || upper.includes("INSUFFICIENT_ACCESS_OR_READONLY")) {
    const field = body?.[0]?.fields?.[0] || body?.fields?.[0] || null;
    return {
      code: "FIELD_SECURITY_BLOCK",
      message: "Salesforce field or object permissions blocked the write.",
      field,
      recoverable: false,
      nextAction: "Escalate field-level security or object permission access to Sales Ops or Salesforce admin.",
    };
  }
  if (upper.includes("INVALID_OR_NULL_FOR_RESTRICTED_PICKLIST") || upper.includes("INVALID_FIELD_FOR_INSERT_UPDATE")) {
    return {
      code: "SALESFORCE_VALIDATION_ERROR",
      message: "Salesforce rejected a value during validation.",
      field: body?.[0]?.fields?.[0] || body?.fields?.[0] || null,
      recoverable: true,
      nextAction: "Re-describe the field, show allowed values, and ask the user to choose a valid value.",
    };
  }
  if (upper.includes("INVALID_FIELD")) {
    return {
      code: "SCHEMA_DRIFT",
      message: "Salesforce rejected a field name or schema assumption.",
      field: body?.[0]?.fields?.[0] || body?.fields?.[0] || null,
      recoverable: false,
      nextAction: "Re-run Opportunity describe and update the field map before writing.",
    };
  }
  if (upper.includes("MALFORMED_ID")) {
    return {
      code: "MALFORMED_ID",
      message: "A Salesforce reference field received a non-ID value.",
      field: body?.[0]?.fields?.[0] || body?.fields?.[0] || null,
      recoverable: true,
      nextAction: "Remove the lookup field from the payload and route narrative to Opportunity Next Steps.",
    };
  }
  if (upper.includes("STRING_TOO_LONG")) {
    return {
      code: "STRING_TOO_LONG",
      message: "A Salesforce field length limit was exceeded.",
      field: body?.[0]?.fields?.[0] || body?.fields?.[0] || null,
      recoverable: true,
      nextAction: "Shorten the content or split the update before retrying.",
    };
  }
  if (Number(status) === 204) {
    return {
      code: "SUCCESS_204",
      message: "Salesforce PATCH succeeded.",
      field: null,
      recoverable: false,
      nextAction: "Re-query the Opportunity and verify each written field.",
    };
  }
  return {
    code: "UNKNOWN_INTEGRATION_ERROR",
    message: "Unrecognized Salesforce or Integration Service response.",
    field: null,
    recoverable: false,
    nextAction: "Surface the raw redacted response and stop instead of retrying blindly.",
  };
}

function normalizeIntegrationResponse(payload) {
  return {
    ok: Number(payload.status ?? payload.code ?? payload.response?.code) === 204,
    classification: classifyError(payload),
    redacted: redact(payload),
  };
}

function readPayload(argv) {
  const inputIndex = argv.indexOf("--input");
  if (inputIndex !== -1) {
    const file = argv[inputIndex + 1];
    if (!file) {
      throw new MeddpiccError("MISSING_INPUT_PATH", "--input requires a file path", {
        recoverable: true,
        nextAction: "Pass --input payload.json or provide JSON on stdin.",
      });
    }
    return JSON.parse(fs.readFileSync(file, "utf8"));
  }
  const stdin = fs.readFileSync(0, "utf8").trim();
  return stdin ? JSON.parse(stdin) : {};
}

function printJson(value) {
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}

function usage() {
  return [
    "Usage: node scripts/meddpicc.mjs <parse-id|draft|build-patch|verify|receipt|classify-error> [--input payload.json]",
    "",
    "All commands accept JSON from --input or stdin and emit JSON to stdout.",
  ].join("\n");
}

async function main(argv = process.argv.slice(2)) {
  const [command] = argv;
  if (!command || command === "--help" || command === "-h") {
    process.stdout.write(`${usage()}\n`);
    return;
  }
  const payload = readPayload(argv);
  if (command === "parse-id") {
    printJson(parseOpportunityId(payload.input || payload.opportunityId || ""));
  } else if (command === "draft") {
    printJson(draft(payload));
  } else if (command === "build-patch") {
    printJson(buildPatch(payload));
  } else if (command === "verify") {
    printJson(verify(payload));
  } else if (command === "receipt") {
    printJson(receipt(payload));
  } else if (command === "classify-error") {
    printJson(classifyError(payload));
  } else if (command === "log-run" || command === "build-telemetry") {
    printJson(buildTelemetryPayload(payload));
  } else {
    throw new MeddpiccError("UNKNOWN_COMMAND", `Unknown command: ${command}`, {
      recoverable: true,
      nextAction: usage(),
    });
  }
}

if (SCRIPT_PATH === process.argv[1]) {
  main().catch((error) => {
    const payload = error instanceof MeddpiccError ? error.toJSON() : {
      code: "UNHANDLED_ERROR",
      message: error.message,
      field: null,
      recoverable: false,
      nextAction: "Inspect the input payload and command invocation.",
    };
    process.stderr.write(`${JSON.stringify({ error: payload }, null, 2)}\n`);
    process.exitCode = 1;
  });
}

export {
  FIELD_DEFS,
  FIELD_MAP,
  MeddpiccError,
  appendEntry,
  buildPatch,
  buildTelemetryPayload,
  classifyError,
  draft,
  duplicateStatus,
  hasDuplicateEntry,
  normalizeIntegrationResponse,
  parseOpportunityId,
  receipt,
  verify,
};

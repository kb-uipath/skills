import { spawn } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { delimiter, dirname, isAbsolute, join } from "node:path";

import { CAPS } from "./constants.mjs";
import { redactDeep, SafetyError, sanitizeText } from "./security.mjs";
import {
  loadVerifiedSfRuntime,
  verifySfRuntimeMetadata,
} from "./sf-runtime.mjs";

const ALLOWED = new Set([
  "org display",
  "org list",
  "sobject describe",
  "data query",
]);
const MAX_DESCRIBED_PICKLIST_VALUES = 1_000;
const MAX_PICKLIST_VALUE_LENGTH = 80;
const DEFAULT_COMMAND_TIMEOUT_MS = 60_000;
const MAX_COMMAND_TIMEOUT_MS = 5 * 60_000;
const SAFE_ENV_KEYS = Object.freeze([
  "HOME",
  "USER",
  "LOGNAME",
  "TMPDIR",
  "LANG",
  "LC_ALL",
  "HTTPS_PROXY",
  "HTTP_PROXY",
  "NO_PROXY",
  "NODE_EXTRA_CA_CERTS",
  "SF_CONFIG_DIR",
  "SFDX_CONFIG_DIR",
]);

function sfEnvironment() {
  const env = {};
  for (const key of SAFE_ENV_KEYS) {
    if (typeof process.env[key] === "string") env[key] = process.env[key];
  }
  env.PATH = [...new Set([
    dirname(process.execPath),
    "/usr/local/bin",
    "/opt/homebrew/bin",
    "/usr/bin",
    "/bin",
  ])].join(delimiter);
  return env;
}

function activePicklistValues(field, objectName) {
  if (objectName !== "Opportunity" || field.name !== "StageName") {
    return Object.freeze([]);
  }
  if (field.picklistValues === undefined) return Object.freeze([]);
  if (!Array.isArray(field.picklistValues)
    || field.picklistValues.length > MAX_DESCRIBED_PICKLIST_VALUES) {
    throw new SafetyError(
      "MALFORMED_DESCRIBE",
      "Opportunity.StageName picklist values are malformed or exceed the safety cap",
    );
  }
  const values = [];
  for (const entry of field.picklistValues) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)
      || typeof entry.active !== "boolean") {
      throw new SafetyError(
        "MALFORMED_DESCRIBE",
        "Opportunity.StageName picklist values are malformed",
      );
    }
    if (!entry.active) continue;
    if (typeof entry.value !== "string"
      || entry.value.length < 1
      || entry.value.length > MAX_PICKLIST_VALUE_LENGTH
      || sanitizeText(entry.value) !== entry.value) {
      throw new SafetyError(
        "MALFORMED_DESCRIBE",
        "Opportunity.StageName has an unsafe active picklist value",
      );
    }
    values.push(entry.value);
  }
  if (new Set(values).size !== values.length) {
    throw new SafetyError(
      "MALFORMED_DESCRIBE",
      "Opportunity.StageName has duplicate active picklist values",
    );
  }
  return Object.freeze(
    values.sort((left, right) => left.localeCompare(right, "en-US")),
  );
}

function maskedUsername(value) {
  if (typeof value !== "string"
    || value.length < 1
    || value.length > 255
    || sanitizeText(value) !== value) {
    throw new SafetyError(
      "MALFORMED_ORG_LIST",
      "Salesforce org list returned an unsafe username",
    );
  }
  const separator = value.lastIndexOf("@");
  if (separator <= 0 || separator === value.length - 1) {
    return `${value.slice(0, 1)}***`;
  }
  return `${value.slice(0, 1)}***@${value.slice(separator + 1)}`;
}

function instanceHost(value) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new SafetyError(
      "MALFORMED_ORG_LIST",
      "Salesforce org list returned an invalid instance URL",
    );
  }
  if (parsed.protocol !== "https:"
    || parsed.username
    || parsed.password
    || !parsed.hostname) {
    throw new SafetyError(
      "MALFORMED_ORG_LIST",
      "Salesforce org list returned an unsafe instance URL",
    );
  }
  return parsed.hostname.toLocaleLowerCase("en-US");
}

function safeAlias(value) {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string"
    || value.length < 1
    || value.length > 80
    || sanitizeText(value) !== value) {
    return null;
  }
  return value;
}

function redactedOrgListRow(record, orgType) {
  if (!record || typeof record !== "object" || Array.isArray(record)
    || !/^00D[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?$/u.test(record.orgId)
    || record.orgId.length !== 18) {
    throw new SafetyError(
      "MALFORMED_ORG_LIST",
      "Salesforce org list returned invalid org identity metadata",
    );
  }
  const status = record.connectedStatus ?? record.status ?? "not_checked";
  if (typeof status !== "string"
    || status.length < 1
    || status.length > 80
    || sanitizeText(status) !== status) {
    throw new SafetyError(
      "MALFORMED_ORG_LIST",
      "Salesforce org list returned an unsafe status",
    );
  }
  return {
    alias: safeAlias(record.alias),
    masked_username: maskedUsername(record.username),
    org_id_suffix: record.orgId.slice(-6),
    instance_host: instanceHost(record.instanceUrl),
    org_type: orgType,
    status,
  };
}

export function redactOrgListPayload(payload) {
  const result = payload?.result ?? payload;
  if (!result || typeof result !== "object" || Array.isArray(result)) {
    throw new SafetyError(
      "MALFORMED_ORG_LIST",
      "Salesforce org list omitted its result object",
    );
  }
  const groups = [
    ["sandboxes", "sandbox"],
    ["other", "production_or_developer"],
    ["devHubs", "dev_hub"],
    ["scratchOrgs", "scratch"],
  ];
  for (const [key] of groups) {
    if (!Array.isArray(result[key])) {
      throw new SafetyError(
        "MALFORMED_ORG_LIST",
        `Salesforce org list omitted ${key}`,
      );
    }
  }
  const count = groups.reduce((total, [key]) => total + result[key].length, 0);
  if (count > CAPS.authorizedOrgs) {
    throw new SafetyError(
      "ORG_LIST_CAP_EXCEEDED",
      `Salesforce org list exceeded the ${CAPS.authorizedOrgs}-org safety cap`,
    );
  }
  const rows = groups.flatMap(([key, orgType]) =>
    result[key].map((record) => redactedOrgListRow(record, orgType)));
  return rows.sort((left, right) =>
    String(left.alias ?? "").localeCompare(String(right.alias ?? ""), "en-US")
    || left.org_type.localeCompare(right.org_type, "en-US")
    || left.org_id_suffix.localeCompare(right.org_id_suffix, "en-US"));
}

export class SfClient {
  constructor({
    commandSpec = null,
    sfPath = null,
    targetOrg,
    runner = spawn,
    runtimeVerifier = null,
    commandTimeoutMs = DEFAULT_COMMAND_TIMEOUT_MS,
  } = {}) {
    if (commandSpec) {
      if (!isAbsolute(commandSpec.executable)
        || !Array.isArray(commandSpec.fixedArgs)
        || !/^[a-f0-9]{64}$/.test(commandSpec.attestationDigest)) {
        throw new SafetyError("UNTRUSTED_SF_EXECUTABLE", "Salesforce CLI command specification is invalid");
      }
      this.sfPath = commandSpec.executable;
      this.fixedArgs = [...commandSpec.fixedArgs];
      this.attestationDigest = commandSpec.attestationDigest;
    } else if (sfPath && runner !== spawn) {
      this.sfPath = sfPath;
      this.fixedArgs = [];
      this.attestationDigest = null;
    } else {
      throw new SafetyError("SF_RUNTIME_NOT_ENROLLED", "Production Salesforce access requires a verified runtime command specification");
    }
    this.targetOrg = targetOrg;
    this.runner = runner;
    this.runtimeVerifier = runtimeVerifier;
    if (!Number.isInteger(commandTimeoutMs)
      || commandTimeoutMs < 1
      || commandTimeoutMs > MAX_COMMAND_TIMEOUT_MS) {
      throw new SafetyError(
        "INVALID_SF_TIMEOUT",
        "Salesforce CLI timeout must be a positive bounded integer",
      );
    }
    this.commandTimeoutMs = commandTimeoutMs;
    this.queryCount = 0;
  }

  async invoke(command, args) {
    if (!ALLOWED.has(command)) throw new SafetyError("SF_COMMAND_NOT_ALLOWED", "Salesforce CLI command is not allowlisted");
    if (this.runtimeVerifier) await this.runtimeVerifier();
    return await new Promise((resolve, reject) => {
      const child = this.runner(this.sfPath, [...this.fixedArgs, ...command.split(" "), ...args], {
        shell: false,
        stdio: ["ignore", "pipe", "pipe"],
        env: sfEnvironment(),
      });
      const stdout = [];
      const stderr = [];
      let size = 0;
      let settled = false;
      const settle = (operation) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        operation();
      };
      const timeout = setTimeout(() => {
        try {
          child.kill("SIGKILL");
        } catch {
          // The timeout remains authoritative even if the child exited first.
        }
        settle(() => reject(new SafetyError(
          "SF_COMMAND_TIMEOUT",
          "Salesforce CLI command exceeded its execution timeout",
        )));
      }, this.commandTimeoutMs);
      const collect = (target) => (chunk) => {
        size += chunk.length;
        if (size > 16 * 1024 * 1024) child.kill("SIGKILL");
        else target.push(chunk);
      };
      child.stdout.on("data", collect(stdout));
      child.stderr.on("data", collect(stderr));
      child.on("error", () => settle(() =>
        reject(new SafetyError(
          "SF_EXECUTION_FAILED",
          "Salesforce CLI could not be executed",
        ))));
      child.on("close", (code) => {
        if (settled) return;
        const rawOut = Buffer.concat(stdout).toString("utf8");
        const rawErr = Buffer.concat(stderr).toString("utf8");
        if (size > 16 * 1024 * 1024) {
          return settle(() => reject(new SafetyError(
            "SF_OUTPUT_TOO_LARGE",
            "Salesforce CLI output exceeded the safety cap",
          )));
        }
        if (code !== 0) {
          const failureText = rawOut + rawErr;
          const category = /INVALID_SESSION|AUTHENTICATION_FAILURE|INVALID_GRANT|AUTH_REQUIRED|EXPIRED_ACCESS_TOKEN/i.test(failureText)
            ? "AUTHENTICATION_FAILURE"
            : /INSUFFICIENT_ACCESS|NOT_AUTHORIZED|PERMISSION_DENIED/i.test(failureText)
              ? "PERMISSION_DENIED"
              : /INVALID_FIELD|MALFORMED_QUERY|INVALID_TYPE/i.test(failureText)
                ? "SCHEMA_FAILURE"
                : "SF_COMMAND_FAILED";
          return settle(() =>
            reject(new SafetyError(
              category,
              "Salesforce CLI command failed",
            )));
        }
        try {
          const parsed = JSON.parse(rawOut);
          settle(() => resolve(parsed));
        } catch {
          settle(() => reject(new SafetyError(
            "INVALID_SF_JSON",
            "Salesforce CLI did not return valid JSON",
          )));
        }
      });
    });
  }

  async orgDisplay() {
    const payload = await this.invoke("org display", ["--target-org", this.targetOrg, "--json"]);
    const result = payload.result ?? payload;
    if (!result.id || !result.username || !result.instanceUrl) {
      throw new SafetyError("INCOMPLETE_ORG_IDENTITY", "Salesforce org display omitted required identity fields");
    }
    return redactDeep({
      org_id: result.id,
      username: result.username,
      instance_url: result.instanceUrl,
      connected_status: result.connectedStatus ?? "unknown",
    });
  }

  async orgList() {
    const payload = await this.invoke("org list", [
      "--skip-connection-status",
      "--json",
    ]);
    return redactOrgListPayload(payload);
  }

  async describe(objectName) {
    const payload = await this.invoke("sobject describe", [
      "--sobject", objectName,
      "--target-org", this.targetOrg,
      "--json",
    ]);
    const result = payload.result ?? payload;
    if (!Array.isArray(result.fields)) throw new SafetyError("INCOMPLETE_DESCRIBE", `${objectName} describe omitted fields`);
    return new Map(result.fields.map((field) => [field.name, {
      name: field.name,
      type: field.type,
      filterable: field.filterable === true,
      referenceTo: Array.isArray(field.referenceTo) ? [...field.referenceTo] : [],
      relationshipName: field.relationshipName ?? null,
      activePicklistValues: activePicklistValues(field, objectName),
    }]));
  }

  async query(soql) {
    this.queryCount += 1;
    if (this.queryCount > CAPS.queries) throw new SafetyError("QUERY_CAP_EXCEEDED", "Query count exceeded 30");
    const workspace = await mkdtemp(join(tmpdir(), "sf-account-profile-"));
    const requestPath = join(workspace, "request.soql");
    try {
      await writeFile(requestPath, `${soql}\n`, { mode: 0o600, flag: "wx" });
      const payload = await this.invoke("data query", [
        "--file", requestPath,
        "--target-org", this.targetOrg,
        "--json",
      ]);
      const result = payload.result ?? payload;
      if (!Array.isArray(result.records)) throw new SafetyError("INCOMPLETE_QUERY_RESULT", "Query result omitted records");
      const totalSize = result.totalSize;
      if (result.done !== true || !Number.isInteger(totalSize) || totalSize < 0 || totalSize !== result.records.length) {
        throw new SafetyError("TRUNCATED_QUERY_RESULT", "Salesforce returned an incomplete query result");
      }
      return redactDeep(result.records);
    } finally {
      await rm(workspace, { recursive: true, force: true });
    }
  }
}

export async function createProductionSfClient({
  targetOrg,
  runner = spawn,
  runtimeManifestPath,
  commandTimeoutMs = DEFAULT_COMMAND_TIMEOUT_MS,
} = {}) {
  const { manifest, command } = await loadVerifiedSfRuntime(runtimeManifestPath);
  return new SfClient({
    commandSpec: command,
    targetOrg,
    runner,
    commandTimeoutMs,
    runtimeVerifier: async () => {
      await verifySfRuntimeMetadata(manifest);
    },
  });
}

export function batchIds(ids, size = CAPS.idsPerBatch) {
  if (!Array.isArray(ids)) throw new SafetyError("INVALID_ID_SET", "IDs must be an array");
  const unique = [...new Set(ids)];
  const batches = [];
  for (let index = 0; index < unique.length; index += size) batches.push(unique.slice(index, index + size));
  return batches;
}

export const sfClientInternals = Object.freeze({
  DEFAULT_COMMAND_TIMEOUT_MS,
  MAX_COMMAND_TIMEOUT_MS,
});

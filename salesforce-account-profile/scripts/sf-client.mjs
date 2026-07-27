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

const ALLOWED = new Set(["org display", "sobject describe", "data query"]);
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

export class SfClient {
  constructor({
    commandSpec = null,
    sfPath = null,
    targetOrg,
    runner = spawn,
    runtimeVerifier = null,
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
      const collect = (target) => (chunk) => {
        size += chunk.length;
        if (size > 16 * 1024 * 1024) child.kill("SIGKILL");
        else target.push(chunk);
      };
      child.stdout.on("data", collect(stdout));
      child.stderr.on("data", collect(stderr));
      child.on("error", () => reject(new SafetyError("SF_EXECUTION_FAILED", "Salesforce CLI could not be executed")));
      child.on("close", (code) => {
        const rawOut = Buffer.concat(stdout).toString("utf8");
        const rawErr = Buffer.concat(stderr).toString("utf8");
        if (size > 16 * 1024 * 1024) return reject(new SafetyError("SF_OUTPUT_TOO_LARGE", "Salesforce CLI output exceeded the safety cap"));
        if (code !== 0) {
          const category = /INVALID_FIELD|INSUFFICIENT_ACCESS|NOT_AUTHORIZED|INVALID_SESSION|AUTH/i.test(rawOut + rawErr)
            ? "SCHEMA_OR_AUTHORIZATION_FAILURE"
            : "SF_COMMAND_FAILED";
          return reject(new SafetyError(category, "Salesforce CLI command failed"));
        }
        try {
          resolve(JSON.parse(rawOut));
        } catch {
          reject(new SafetyError("INVALID_SF_JSON", "Salesforce CLI did not return valid JSON"));
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
} = {}) {
  const { manifest, command } = await loadVerifiedSfRuntime(runtimeManifestPath);
  return new SfClient({
    commandSpec: command,
    targetOrg,
    runner,
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
